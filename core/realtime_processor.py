import queue
import threading
import tempfile
import time
import os
import wave
import numpy as np
import logging
from collections import deque
from pathlib import Path

try:
    import sounddevice as sd
except ImportError:
    sd = None

import whisper
import torch

logger = logging.getLogger("realtime-processor")

# ─────────────────────────────────────────────────────────────────────────────
# RealTimeDiarizer
# ─────────────────────────────────────────────────────────────────────────────

class RealTimeDiarizer:
    """
    Real-time speaker diarization using a local pyannote segmentation
    and speaker embedding model, aligned synchronously on transcribed chunks.
    """

    SPEAKER_COLORS = ["🔵", "🟠", "🟢", "🔴", "🟣", "🟡", "⚪", "🟤"]

    def __init__(
        self,
        sample_rate: int = 16000,
        similarity_threshold: float = 0.30,  # Lowered to 0.30 for robust short-chunk matching
    ):
        self.sample_rate = sample_rate
        self.similarity_threshold = similarity_threshold

        self.is_running = False
        self._session_start: float = 0.0

        # Speaker profiles: list of {"label": "Speaker 1", "embedding": np.array, "color": "🔵"}
        self._speaker_profiles: list = []
        self._profiles_lock = threading.Lock()

        # Output: publicly readable list of segment dicts
        self.live_segments: list = []
        self._segments_lock = threading.Lock()

        # Pyannote pipeline handle
        self._pipeline = None         # full pyannote.audio Pipeline
        self._emb_inference = None    # embedding Inference
        self._models_ready = False
        self._model_error: str | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def load_models(self):
        """
        Load the local speaker diarization pipeline + embedding model.
        Uses the same pipeline as offline mode — guaranteed to work.
        """
        if self._models_ready:
            return

        logger.info("RealTimeDiarizer: loading local pyannote pipeline …")

        try:
            import torchaudio
            if not hasattr(torchaudio, "AudioMetaData"):
                try:
                    from torchaudio._torchaudio import AudioMetaData as _AM  # type: ignore
                    torchaudio.AudioMetaData = _AM  # type: ignore[attr-defined]
                except ImportError:
                    pass

            from pyannote.audio import Pipeline, Model, Inference

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            # ── Full diarization pipeline ──
            pipeline_config = Path("./models/speaker-diarization-3.1/config.yaml")
            self._pipeline = Pipeline.from_pretrained(pipeline_config)
            self._pipeline.to(device)
            logger.info("RealTimeDiarizer: diarization pipeline loaded.")

            # ── Embedding model ──
            emb_bin = Path("./models/wespeaker-voxceleb-resnet34-LM/pytorch_model.bin")
            emb_model = Model.from_pretrained(emb_bin)
            emb_model.eval()
            emb_model.to(device)
            self._emb_inference = Inference(emb_model, window="whole")
            logger.info("RealTimeDiarizer: embedding model loaded.")

            self._models_ready = True

        except Exception as exc:
            self._model_error = str(exc)
            logger.error(f"RealTimeDiarizer: failed to load models — {exc}")
            raise

    def start(self):
        """Start diarization state tracking."""
        if not self._models_ready:
            raise RuntimeError("Call load_models() before start().")

        self.is_running = True
        self._session_start = time.time()
        with self._profiles_lock:
            self._speaker_profiles.clear()
        with self._segments_lock:
            self.live_segments.clear()
        logger.info("RealTimeDiarizer: started.")

    def stop(self):
        """Stop diarization state tracking."""
        self.is_running = False
        logger.info("RealTimeDiarizer: stopped.")

    def get_live_segments(self) -> list:
        """Return a snapshot of current live segments (thread-safe copy)."""
        with self._segments_lock:
            return list(self.live_segments)

    def diarize_chunk(self, wav_path: str, text: str):
        """
        Diarize the exact transcribed chunk, match the speaker, 
        and append a finished segment with text.
        """
        from pyannote.core import Segment

        if not self.is_running:
            return

        try:
            import soundfile as sf
            info = sf.info(wav_path)
            duration = info.duration

            # 1. Run diarization pipeline on this chunk
            diarize_output = self._pipeline(wav_path)
            annotation = diarize_output.speaker_diarization

            best_turn = None
            max_duration = 0.0
            for turn, _, local_spk in annotation.itertracks(yield_label=True):
                if turn.duration > max_duration:
                    max_duration = turn.duration
                    best_turn = turn

            global_label = None
            if best_turn is not None and max_duration >= 0.5:
                try:
                    # Clip boundaries to prevent pyannote rounding issues beyond file duration
                    clipped_turn = Segment(best_turn.start, min(best_turn.end, duration - 0.01))
                    if clipped_turn.duration >= 0.5:
                        emb = self._emb_inference.crop(wav_path, clipped_turn)
                        global_label = self._match_or_create_speaker(emb)
                except Exception as emb_exc:
                    logger.warning(f"Embedding crop failed: {emb_exc}")

            # Fallback to whole file embedding if no turns or crop failed
            if global_label is None:
                try:
                    emb = self._emb_inference(wav_path)
                    global_label = self._match_or_create_speaker(emb)
                except Exception as emb_exc:
                    logger.warning(f"Whole-chunk embedding failed: {emb_exc}")

            # Absolute fallback: assign to the last active speaker or Speaker 1
            if global_label is None:
                with self._segments_lock:
                    if self.live_segments:
                        global_label = self.live_segments[-1]["speaker"]
                    else:
                        global_label = "Speaker 1"

            color = self._color_for_label(global_label)
            session_elapsed = time.time() - self._session_start
            ts = self._fmt_ts(session_elapsed)

            with self._segments_lock:
                if self.live_segments and self.live_segments[-1]["speaker"] == global_label:
                    # Stitch text together with a space
                    self.live_segments[-1]["text"] = (self.live_segments[-1]["text"] + " " + text).strip()
                else:
                    new_seg = {
                        "speaker": global_label,
                        "color": color,
                        "text": text,
                        "timestamp": ts,
                    }
                    self.live_segments.append(new_seg)

        except Exception as exc:
            logger.error(f"RealTimeDiarizer diarize_chunk error: {exc}", exc_info=True)

    # ── Speaker profile management ────────────────────────────────────────────

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        a = a.flatten()
        b = b.flatten()
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _match_or_create_speaker(self, embedding: np.ndarray) -> str:
        """
        Compare embedding against all known speaker profiles.
        Return the label of the best match if similarity >= threshold,
        otherwise register a new speaker and return their label.
        """
        with self._profiles_lock:
            best_sim = -1.0
            best_label = None

            for profile in self._speaker_profiles:
                sim = self._cosine_similarity(embedding, profile["embedding"])
                if sim > best_sim:
                    best_sim = sim
                    best_label = profile["label"]

            if best_sim >= self.similarity_threshold:
                # Update running average embedding for this speaker
                for profile in self._speaker_profiles:
                    if profile["label"] == best_label:
                        # Exponential moving average
                        profile["embedding"] = 0.9 * profile["embedding"] + 0.1 * embedding
                        break
                return best_label

            # New speaker
            idx = len(self._speaker_profiles) + 1
            new_label = f"Speaker {idx}"
            color = self.SPEAKER_COLORS[(idx - 1) % len(self.SPEAKER_COLORS)]
            self._speaker_profiles.append({
                "label": new_label,
                "embedding": embedding.copy(),
                "color": color,
            })
            logger.info(f"RealTimeDiarizer: registered {new_label} (profiles total: {idx})")
            return new_label

    def _color_for_label(self, label: str) -> str:
        with self._profiles_lock:
            for p in self._speaker_profiles:
                if p["label"] == label:
                    return p["color"]
        return "⚫"

    @staticmethod
    def _fmt_ts(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# RealTimeTranscriber  (unchanged — kept exactly as before)
# ─────────────────────────────────────────────────────────────────────────────

class RealTimeTranscriber:
    def __init__(self, sample_rate=16000, chunk_duration=6, model_size="base"):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.chunk_samples = int(sample_rate * chunk_duration)
        self.model_size = model_size

        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.transcript_segments = []
        self.full_audio_data = []  # To store the entire recording

        self.model = None
        self.record_thread = None
        self.transcribe_thread = None

        # Optional: reference to a RealTimeDiarizer to feed text into
        self.diarizer: RealTimeDiarizer | None = None

    def start(self):
        if sd is None:
            raise RuntimeError("sounddevice is not installed or available.")

        if self.model is None:
            logger.info(f"Loading Whisper '{self.model_size}' model for real-time transcription...")
            self.model = whisper.load_model(self.model_size)

        self.is_recording = True
        self.transcript_segments = []
        self.full_audio_data = []

        # Clear queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        self.record_thread = threading.Thread(target=self._record_loop, daemon=True)
        self.transcribe_thread = threading.Thread(target=self._transcribe_loop, daemon=True)

        self.record_thread.start()
        self.transcribe_thread.start()
        logger.info("Real-time transcription started.")

    def stop(self):
        self.is_recording = False
        if self.record_thread:
            self.record_thread.join(timeout=2)
        if self.transcribe_thread:
            self.transcribe_thread.join(timeout=2)
        logger.info("Real-time transcription stopped.")

    def get_transcript(self):
        return " ".join(self.transcript_segments)

    def _record_loop(self):
        try:
            def callback(indata, frames, time_info, status):
                if status:
                    logger.warning(f"Audio status: {status}")
                if self.is_recording:
                    data = indata.copy()
                    self.audio_queue.put(data)
                    self.full_audio_data.append(data)

            with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=callback, blocksize=self.chunk_samples):
                while self.is_recording:
                    time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in record loop: {e}")
            self.is_recording = False

    def _transcribe_loop(self):
        fp16_supported = torch.cuda.is_available()

        while self.is_recording or not self.audio_queue.empty():
            try:
                audio_data = self.audio_queue.get(timeout=1)

                # Save chunk to temp file for Whisper
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    wav_path = tmp.name
                    with wave.open(wav_path, 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(self.sample_rate)
                        wf.writeframes((audio_data * 32767).astype(np.int16).tobytes())

                try:
                    result = self.model.transcribe(wav_path, fp16=fp16_supported)
                    text = result['text'].strip()
                    if text:
                        self.transcript_segments.append(text)
                        # Feed text into diarizer to align synchronously
                        if self.diarizer is not None:
                            self.diarizer.diarize_chunk(wav_path, text)
                except Exception as e:
                    logger.error(f"Whisper transcription error: {e}")
                finally:
                    try:
                        os.unlink(wav_path)
                    except Exception:
                        pass
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in transcribe loop: {e}")

    def save_full_audio(self, filepath):
        if not self.full_audio_data:
            logger.warning("No audio data to save.")
            return False

        try:
            logger.info(f"Saving full audio to {filepath}...")
            full_audio = np.concatenate(self.full_audio_data, axis=0)

            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes((full_audio * 32767).astype(np.int16).tobytes())
            return True
        except Exception as e:
            logger.error(f"Error saving full audio: {e}")
            return False
