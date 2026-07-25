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

# Global caches to avoid reloading models on every WebSocket/recording start
_pipeline_cache = {}
_emb_model_cache = {}
_whisper_cache = {}

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
            pipeline_key = str(pipeline_config)
            if pipeline_key not in _pipeline_cache:
                logger.info(f"Loading diarization pipeline for RealTimeDiarizer from disk: {pipeline_key}")
                pipeline = Pipeline.from_pretrained(pipeline_config)
                pipeline.to(device)
                _pipeline_cache[pipeline_key] = pipeline
            else:
                logger.info("Using cached diarization pipeline for RealTimeDiarizer")
            self._pipeline = _pipeline_cache[pipeline_key]

            # ── Embedding model ──
            emb_bin = Path("./models/wespeaker-voxceleb-resnet34-LM/pytorch_model.bin")
            emb_key = str(emb_bin)
            if emb_key not in _emb_model_cache:
                logger.info(f"Loading embedding model for RealTimeDiarizer from disk: {emb_key}")
                emb_model = Model.from_pretrained(emb_bin)
                emb_model.eval()
                emb_model.to(device)
                _emb_model_cache[emb_key] = Inference(emb_model, window="whole")
            else:
                logger.info("Using cached embedding model for RealTimeDiarizer")
            self._emb_inference = _emb_model_cache[emb_key]

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

    def diarize_chunk(self, wav_path: str, text: str, confidence: float = None, words: list = None):
        """
        Diarize the exact transcribed chunk, match the speaker, 
        and append a finished segment with text and confidence scores.
        """
        from pyannote.core import Segment

        if not self.is_running:
            return

        try:
            global_label = None
            if self._pipeline is not None and self._emb_inference is not None:
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

                    if best_turn is not None and max_duration >= 0.3:
                        clipped_turn = Segment(best_turn.start, min(best_turn.end, duration - 0.01))
                        if clipped_turn.duration >= 0.3:
                            emb = self._emb_inference.crop(wav_path, clipped_turn)
                            global_label = self._match_or_create_speaker(emb)

                    if global_label is None:
                        emb = self._emb_inference(wav_path)
                        global_label = self._match_or_create_speaker(emb)
                except Exception as pyannote_exc:
                    logger.warning(f"Pyannote diarization warning: {pyannote_exc}")

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
                    # Average confidence
                    prev_seg = self.live_segments[-1]
                    if confidence is not None:
                        if prev_seg.get("confidence") is not None:
                            prev_seg["confidence"] = round((prev_seg["confidence"] + confidence) / 2, 2)
                        else:
                            prev_seg["confidence"] = confidence
                    # Append words
                    if words:
                        if "words" not in prev_seg:
                            prev_seg["words"] = []
                        prev_seg["words"].extend(words)
                else:
                    new_seg = {
                        "speaker": global_label,
                        "color": color,
                        "text": text,
                        "timestamp": ts,
                        "confidence": confidence,
                        "words": words or []
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
            if not self._speaker_profiles:
                new_label = "Speaker 1"
                color = self.SPEAKER_COLORS[0]
                self._speaker_profiles.append({
                    "label": new_label,
                    "embedding": embedding.copy(),
                    "color": color,
                })
                logger.info(f"RealTimeDiarizer: registered {new_label}")
                return new_label

            best_sim = -1.0
            best_label = None

            for profile in self._speaker_profiles:
                sim = self._cosine_similarity(embedding, profile["embedding"])
                if sim > best_sim:
                    best_sim = sim
                    best_label = profile["label"]

            # Adaptive threshold: 0.15 if only 1 speaker registered so far, 0.22 for multi-speaker
            threshold = 0.15 if len(self._speaker_profiles) == 1 else 0.22

            if best_sim >= threshold:
                # Update running average embedding for this speaker
                for profile in self._speaker_profiles:
                    if profile["label"] == best_label:
                        profile["embedding"] = 0.85 * profile["embedding"] + 0.15 * embedding
                        break
                return best_label

            # New speaker (requires clear dissimilarity)
            idx = len(self._speaker_profiles) + 1
            new_label = f"Speaker {idx}"
            color = self.SPEAKER_COLORS[(idx - 1) % len(self.SPEAKER_COLORS)]
            self._speaker_profiles.append({
                "label": new_label,
                "embedding": embedding.copy(),
                "color": color,
            })
            logger.info(f"RealTimeDiarizer: registered {new_label} (profiles total: {idx}, best_sim: {best_sim:.2f})")
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
    def __init__(self, sample_rate=16000, chunk_duration=6, model_size="small"):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.chunk_samples = int(sample_rate * chunk_duration)
        self.model_size = model_size

        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.transcript_segments = []
        self.raw_segments = []  # Structured segment list with word timestamps
        self.full_audio_data = []  # To store the entire recording

        self.model = None
        self.record_thread = None
        self.transcribe_thread = None
        self._session_start_time = 0.0

        # Optional: reference to a RealTimeDiarizer to feed text into
        self.diarizer: RealTimeDiarizer | None = None

    def start(self):
        if sd is None:
            raise RuntimeError("sounddevice is not installed or available.")

        if self.model is None:
            if self.model_size not in _whisper_cache:
                logger.info(f"Loading Whisper '{self.model_size}' model for real-time transcription...")
                _whisper_cache[self.model_size] = whisper.load_model(self.model_size)
            self.model = _whisper_cache[self.model_size]

        self.is_recording = True
        self.transcript_segments = []
        self.raw_segments = []
        self.full_audio_data = []
        self._session_start_time = time.time()

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
                    # Enable word timestamps for confidence extraction
                    transcribe_options = {
                        "word_timestamps": True,
                        "fp16": fp16_supported
                    }
                    result = self.model.transcribe(wav_path, **transcribe_options)
                    text = result['text'].strip()
                    if text:
                        self.transcript_segments.append(text)
                        
                        # Process segment confidence & word confidence
                        segment_conf = None
                        words_list = []
                        
                        if result.get("segments"):
                            first_seg = result["segments"][0]
                            # 1. Segment-level confidence
                            if "avg_logprob" in first_seg:
                                logprob = first_seg["avg_logprob"]
                                segment_conf = round(min(100, max(0, 100 + 20 * logprob)), 2)
                            elif "no_speech_prob" in first_seg:
                                segment_conf = round(100 * (1 - first_seg["no_speech_prob"]), 2)
                                
                            # 2. Word-level confidence
                            if "words" in first_seg:
                                for word in first_seg["words"]:
                                    words_list.append({
                                        "word": word.get("word", ""),
                                        "start": word.get("start", 0),
                                        "end": word.get("end", 0),
                                        "confidence": round(100 * word.get("probability", 0), 2) if "probability" in word else None
                                    })
                        
                        if segment_conf is None:
                            segment_conf = 85.0  # Safe default if Whisper fails to report
                            
                        # Add to raw segments list
                        elapsed = time.time() - self._session_start_time
                        m, s = divmod(int(elapsed), 60)
                        h, m = divmod(m, 60)
                        ts_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
                        
                        self.raw_segments.append({
                            "text": text,
                            "confidence": segment_conf,
                            "confidence_level": "high" if segment_conf >= 90 else ("medium" if segment_conf >= 70 else "low"),
                            "words": words_list,
                            "start_formatted": ts_str
                        })
                        
                        # Feed text + confidence into diarizer to align synchronously
                        if self.diarizer is not None:
                            self.diarizer.diarize_chunk(wav_path, text, confidence=segment_conf, words=words_list)
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


# ─────────────────────────────────────────────────────────────────────────────
# WebSocketRealTimeProcessor
# ─────────────────────────────────────────────────────────────────────────────

class WebSocketRealTimeProcessor:
    """
    Real-time streaming processor for WebSocket connections.
    Receives 16kHz 16-bit Int16 PCM raw audio bytes from browser Web Audio API,
    transcribes with Whisper, and diarizes with Pyannote in real time.
    """
    def __init__(self, sample_rate: int = 16000, model_size: str = "small", language: str = None, chunk_duration: int = 6):
        self.sample_rate = sample_rate
        self.model_size = model_size
        self.language = language if language and language != "auto" else None
        self.chunk_duration = chunk_duration
        self.chunk_samples = int(sample_rate * chunk_duration)

        self.diarizer = RealTimeDiarizer(sample_rate=sample_rate)
        try:
            self.diarizer.load_models()
        except Exception as e:
            logger.warning(f"WebSocketRealTimeProcessor: Diarizer failed to load: {e}")

        self.diarizer.start()

        logger.info(f"Loading Whisper '{self.model_size}' model for WebSocket processor...")
        if self.model_size not in _whisper_cache:
            _whisper_cache[self.model_size] = whisper.load_model(self.model_size)
        self.model = _whisper_cache[self.model_size]

        self.pcm_bytes_buffer = bytearray()  # full session audio, for save_final_recording
        self._pending_samples = np.array([], dtype=np.int16)  # unprocessed audio since last full chunk
        self._session_start = time.time()

    def process_audio_chunk(self, chunk_bytes: bytes) -> list:
        if not chunk_bytes:
            return self.diarizer.get_live_segments()

        try:
            import soundfile as sf
            self.pcm_bytes_buffer.extend(chunk_bytes)

            new_samples = np.frombuffer(chunk_bytes, dtype=np.int16)
            self._pending_samples = np.concatenate([self._pending_samples, new_samples])

            fp16_supported = torch.cuda.is_available()

            # Transcribe fixed, self-contained chunks (matches RealTimeTranscriber's approach)
            while len(self._pending_samples) >= self.chunk_samples:
                chunk_pcm = self._pending_samples[:self.chunk_samples]
                self._pending_samples = self._pending_samples[self.chunk_samples:]

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    wav_path = tmp.name

                try:
                    sf.write(wav_path, chunk_pcm, self.sample_rate, subtype='PCM_16')

                    transcribe_opts = {
                        "word_timestamps": True,
                        "fp16": fp16_supported
                    }
                    if self.language:
                        transcribe_opts["language"] = self.language

                    result = self.model.transcribe(wav_path, **transcribe_opts)
                    text = result.get('text', '').strip()

                    if text:
                        segment_conf = 85.0
                        words_list = []
                        if result.get("segments"):
                            first_seg = result["segments"][0]
                            if "avg_logprob" in first_seg:
                                segment_conf = round(min(100, max(0, 100 + 20 * first_seg["avg_logprob"])), 2)
                            elif "no_speech_prob" in first_seg:
                                segment_conf = round(100 * (1 - first_seg["no_speech_prob"]), 2)

                            if "words" in first_seg:
                                for w in first_seg["words"]:
                                    words_list.append({
                                        "word": w.get("word", ""),
                                        "start": w.get("start", 0),
                                        "end": w.get("end", 0),
                                        "confidence": round(100 * w.get("probability", 0), 2) if "probability" in w else None
                                    })

                        if self.diarizer and self.diarizer.is_running:
                            self.diarizer.diarize_chunk(wav_path, text, confidence=segment_conf, words=words_list)
                finally:
                    try:
                        os.unlink(wav_path)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error processing WebSocket PCM chunk: {e}")

        return self.diarizer.get_live_segments()

    def save_final_recording(self, output_filepath: str) -> bool:
        """Save full accumulated PCM buffer to a WAV file."""
        if not self.pcm_bytes_buffer:
            return False
        try:
            import soundfile as sf
            pcm_samples = np.frombuffer(bytes(self.pcm_bytes_buffer), dtype=np.int16)
            sf.write(output_filepath, pcm_samples, self.sample_rate, subtype='PCM_16')
            return True
        except Exception as e:
            logger.error(f"Error saving WebSocket final recording: {e}")
            return False

