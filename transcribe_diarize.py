"""
transcribe_diarize.py
=====================
Standalone script that transcribes an audio file with Whisper (medium) and
diarizes speakers with pyannote speaker-diarization-3.1 (local model).

Logic is taken directly from MeetingSummarizer/core/audio_processor.py.

Usage:
    python transcribe_diarize.py <audio_file> [--language <lang_code>] [--model-dir <path>] [--output <output_file>]

Examples:
    python transcribe_diarize.py meeting.wav
    python transcribe_diarize.py meeting.mp3 --language hi
    python transcribe_diarize.py meeting.wav --model-dir /path/to/speaker-diarization-3.1
    python transcribe_diarize.py meeting.wav --output result.json
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("transcribe-diarize")

# ── torchaudio compatibility patch (same as MeetingSummarizer) ─────────────────
import torchaudio
if not hasattr(torchaudio, "AudioMetaData"):
    try:
        from torchaudio._torchaudio import AudioMetaData as _AudioMetaData  # type: ignore
        torchaudio.AudioMetaData = _AudioMetaData  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("Could not monkey-patch torchaudio.AudioMetaData. Pyannote might encounter issues.")

import torch
import librosa
import whisper
from pydub import AudioSegment
from pyannote.audio import Pipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook
from pyannote.core import Annotation, Segment

# ── GPU optimizations (same as MeetingSummarizer) ──────────────────────────────
if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

# ── Model caches ───────────────────────────────────────────────────────────────
_whisper_cache: Dict[str, Any] = {}
_pyannote_cache: Dict[str, Any] = {}

# =============================================================================
# AUDIO CONVERSION  (from services/audio_converter.py)
# =============================================================================

def needs_conversion(file_path: str) -> bool:
    """Return True if the file must be converted to WAV before processing."""
    return Path(file_path).suffix.lower() in {".mp3", ".m4a", ".webm", ".ogg", ".flac"}


def convert_audio_to_wav(input_path: str, sample_rate: int = 16000) -> str:
    """
    Convert any audio file to a 16-bit PCM WAV at the given sample rate (mono).
    Tries ffmpeg-python first, falls back to pydub.
    Returns path to a temporary WAV file (caller is responsible for cleanup).
    """
    try:
        import ffmpeg as _ffmpeg  # prefer ffmpeg-python if installed
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_path = tmp.name
        tmp.close()
        logger.info(f"Converting {input_path} → WAV via ffmpeg-python")
        (
            _ffmpeg
            .input(input_path)
            .output(
                output_path,
                format="wav",
                acodec="pcm_s16le",
                ar=sample_rate,
                ac=1,
            )
            .global_args("-loglevel", "error")
            .global_args("-y")
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Converted to WAV: {output_path}")
        return output_path
    except Exception as e:
        logger.warning(f"ffmpeg-python failed ({e}), falling back to pydub")

    # pydub fallback
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    output_path = tmp.name
    tmp.close()
    audio.export(output_path, format="wav")
    logger.info(f"Converted to WAV via pydub: {output_path}")
    return output_path


# =============================================================================
# TRANSCRIPTION  (from core/audio_processor.py → transcribe_audio)
# =============================================================================

def transcribe_audio(audio_file: str, language: Optional[str] = None) -> Dict[str, Any]:
    """
    Transcribe audio with Whisper **medium** model.
    Returns the Whisper result dict with enhanced per-segment confidence info.
    """
    model_size = "medium"
    if model_size not in _whisper_cache:
        logger.info(f"Loading Whisper '{model_size}' model …")
        _whisper_cache[model_size] = whisper.load_model(model_size)
    else:
        logger.info(f"Using cached Whisper '{model_size}' model")
    model = _whisper_cache[model_size]

    logger.info(f"Loading audio for Whisper: {audio_file}")
    audio = librosa.load(audio_file, sr=16000)[0]

    transcribe_options: Dict[str, Any] = {
        "word_timestamps": True,
        "suppress_tokens": [-1],
        "without_timestamps": False,
        "max_initial_timestamp": None,
        "fp16": torch.cuda.is_available(),
    }
    if language and language != "auto":
        transcribe_options["language"] = language

    detected_language = None
    try:
        audio_tensor = torch.tensor(audio) if not isinstance(audio, torch.Tensor) else audio
        result = model.transcribe(audio_tensor, **transcribe_options)
        detected_language = result.get("language")
        logger.info(f"Transcription done. Detected language: {detected_language}")
    except Exception as e:
        logger.error(f"Transcription error: {e}. Retrying with English fallback …")
        transcribe_options["language"] = "en"
        result = model.transcribe(audio, **transcribe_options)

    if not language and detected_language:
        result["detected_language"] = detected_language

    # ── Enhance segments with confidence scores (same logic as MeetingSummarizer) ─
    enhanced_segments = []
    for segment in result["segments"]:
        seg_info: Dict[str, Any] = {
            "id": segment.get("id", 0),
            "start": segment.get("start", 0),
            "end": segment.get("end", 0),
            "text": segment.get("text", "").strip(),
        }

        # Method 1: avg_logprob → confidence %
        if "avg_logprob" in segment:
            logprob = segment["avg_logprob"]
            confidence = min(100, max(0, 100 + 20 * logprob))
            seg_info["confidence"] = round(confidence, 2)
            seg_info["avg_logprob"] = logprob
        else:
            seg_info["confidence"] = None

        # Method 2: token-level probabilities
        if "tokens" in segment and "token_probs" in segment:
            tokens = segment.get("tokens", [])
            token_probs = segment.get("token_probs", [])
            if tokens and token_probs and len(tokens) == len(token_probs):
                valid_probs = [p for p in token_probs if p is not None]
                if valid_probs:
                    token_confidence = 100 * (sum(valid_probs) / len(valid_probs))
                    seg_info["token_confidence"] = round(token_confidence, 2)
                    if seg_info["confidence"] is None:
                        seg_info["confidence"] = seg_info["token_confidence"]

        # Method 3: no_speech_prob fallback
        if seg_info["confidence"] is None and "no_speech_prob" in segment:
            seg_info["confidence"] = round(100 * (1 - segment.get("no_speech_prob", 0)), 2)

        # Final fallback
        if seg_info["confidence"] is None:
            seg_info["confidence"] = 50.0

        # Confidence level label
        if seg_info["confidence"] >= 90:
            seg_info["confidence_level"] = "high"
        elif seg_info["confidence"] >= 70:
            seg_info["confidence_level"] = "medium"
        else:
            seg_info["confidence_level"] = "low"

        # Word-level timestamps
        if "words" in segment:
            seg_info["words"] = [
                {
                    "word": w.get("word", ""),
                    "start": w.get("start", 0),
                    "end": w.get("end", 0),
                    **({"confidence": round(100 * w["probability"], 2)} if "probability" in w else {}),
                }
                for w in segment["words"]
            ]

        enhanced_segments.append(seg_info)

    result["segments"] = enhanced_segments

    # Overall confidence metrics
    if enhanced_segments:
        confidences = [s["confidence"] for s in enhanced_segments]
        result["overall_confidence"] = {
            "average": round(sum(confidences) / len(confidences), 2),
            "min": round(min(confidences), 2),
            "max": round(max(confidences), 2),
        }
        low_conf = [s for s in enhanced_segments if s.get("confidence_level") == "low"]
        result["low_confidence_count"] = len(low_conf)
        result["low_confidence_percentage"] = round(100 * len(low_conf) / len(enhanced_segments), 2)

    return result


# =============================================================================
# DIARIZATION  (from core/audio_processor.py → diarize_audio)
# =============================================================================

def diarize_audio(audio_file: str, model_dir: str) -> Annotation:
    """
    Run pyannote speaker-diarization-3.1 on the audio file.
    Loads the pipeline from a local directory — no HuggingFace token required.
    Falls back to a single-speaker annotation if the pipeline fails.
    """
    temp_file: Optional[str] = None
    try:
        # Convert to WAV if needed before diarization
        if needs_conversion(audio_file):
            logger.info("Converting to WAV before diarization …")
            temp_file = convert_audio_to_wav(audio_file)
            audio_to_process = temp_file
        else:
            audio_to_process = audio_file

        config_path = Path(model_dir) / "config.yaml"
        cache_key = str(config_path)

        if cache_key not in _pyannote_cache:
            logger.info(f"Loading diarization pipeline from: {model_dir}")
            pipeline = Pipeline.from_pretrained(config_path)
            pipeline.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
            _pyannote_cache[cache_key] = pipeline
        else:
            logger.info("Using cached diarization pipeline")
        pipeline = _pyannote_cache[cache_key]

        logger.info("Running diarization …")
        with ProgressHook() as hook:
            diarization_result = pipeline(audio_to_process, hook=hook)
        logger.info("Diarization completed successfully")
        return diarization_result

    except Exception as e:
        logger.error(f"Diarization error: {e}. Using single-speaker fallback.")
        annotation = Annotation()
        try:
            y, sr = librosa.load(audio_file, sr=16000, mono=True, duration=10)
            duration = librosa.get_duration(y=y, sr=sr)
        except Exception:
            duration = 300
        annotation[Segment(0, duration)] = "SPEAKER_00"
        return annotation

    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except Exception:
                pass


# =============================================================================
# ALIGNMENT  (from core/audio_processor.py → format_conversation)
# =============================================================================

def format_conversation(diarization_result: Annotation, transcription_segments: List[Dict]) -> List[Dict]:
    """
    Align transcription segments with speaker diarization turns.
    Each transcription segment gets a speaker label via midpoint / max-overlap.
    """
    # Pyannote 4 wraps result in DiarizeOutput
    if hasattr(diarization_result, "speaker_diarization"):
        diarization_result = diarization_result.speaker_diarization

    diarization_turns = sorted(
        diarization_result.itertracks(yield_label=True),
        key=lambda x: x[0].start,
    )
    transcription_segments = sorted(transcription_segments, key=lambda x: x["start"])
    speaker_map = [(turn.start, turn.end, speaker) for turn, _, speaker in diarization_turns]

    conversation: List[Dict] = []
    for segment in transcription_segments:
        seg_start = segment["start"]
        seg_end = segment["end"]
        seg_mid = (seg_start + seg_end) / 2

        # Midpoint match (fastest)
        assigned_speaker = None
        for t_start, t_end, speaker in speaker_map:
            if t_start <= seg_mid <= t_end:
                assigned_speaker = speaker
                break

        # Max overlap fallback
        if assigned_speaker is None:
            max_overlap = 0
            for t_start, t_end, speaker in speaker_map:
                overlap = max(0, min(t_end, seg_end) - max(t_start, seg_start))
                if overlap > max_overlap:
                    max_overlap = overlap
                    assigned_speaker = speaker

        # Last-resort: first speaker
        if assigned_speaker is None and speaker_map:
            assigned_speaker = speaker_map[0][2]

        entry: Dict[str, Any] = {
            "speaker": assigned_speaker or "UNKNOWN",
            "text": segment["text"].strip(),
            "start_time": seg_start,
            "end_time": seg_end,
        }

        if "confidence" in segment:
            entry["confidence"] = segment["confidence"]
            entry["confidence_level"] = segment.get("confidence_level", "")
        elif "confidence_level" in segment:
            entry["confidence_level"] = segment["confidence_level"]

        entry["segments"] = [{
            "text": segment["text"].strip(),
            "start": segment["start"],
            "end": segment["end"],
            "confidence": segment.get("confidence"),
            "confidence_level": segment.get("confidence_level"),
            "words": segment.get("words", []),
        }]

        conversation.append(entry)

    return conversation


# =============================================================================
# MAIN PIPELINE  (from core/audio_processor.py → process_audio_file)
# =============================================================================

def format_time(seconds: float) -> str:
    """Format seconds into HH:MM:SS."""
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%H:%M:%S")


def process_audio(
    audio_file_path: str,
    language: Optional[str] = None,
    model_dir: str = "",
) -> Dict[str, Any]:
    """
    Full pipeline: convert → transcribe (Whisper medium) → diarize (pyannote 3.1) → align.

    Returns a dict with:
        transcript        – list of aligned, speaker-labelled segments
        formatted_lines   – human-readable transcript lines
        language          – detected / specified language code
        timing            – per-step wall-clock times (seconds)
        confidence_metrics – overall confidence stats
    """
    metrics: Dict[str, Any] = {
        "total_time": 0,
        "timing": {},
        "transcript": [],
        "formatted_lines": [],
        "language": language or "auto-detect",
        "confidence_metrics": {},
    }

    start_total = time.time()
    converted_file: Optional[str] = None

    # ── Convert to WAV if the format requires it ───────────────────────────────
    if needs_conversion(audio_file_path):
        logger.info(f"Converting input file to WAV: {audio_file_path}")
        try:
            converted_file = convert_audio_to_wav(audio_file_path)
            processing_file = converted_file
        except Exception as e:
            logger.error(f"Conversion failed: {e}. Proceeding with original file.")
            processing_file = audio_file_path
    else:
        processing_file = audio_file_path

    try:
        # ── Step 1: Transcription ──────────────────────────────────────────────
        logger.info("=== Step 1/3: Transcription ===")
        t0 = time.time()
        transcription = transcribe_audio(processing_file, language)
        metrics["timing"]["transcription"] = round(time.time() - t0, 2)

        segments = transcription["segments"]

        if "overall_confidence" in transcription:
            metrics["confidence_metrics"] = dict(transcription["overall_confidence"])
            metrics["confidence_metrics"]["low_confidence_count"] = transcription.get("low_confidence_count", 0)
            metrics["confidence_metrics"]["low_confidence_percentage"] = transcription.get("low_confidence_percentage", 0)

        # Resolve language
        if not language or language == "auto":
            detected_lang = (
                transcription.get("detected_language")
                or transcription.get("language")
                or (segments[0].get("language") if segments else None)
            )
            if detected_lang:
                metrics["language"] = detected_lang

        # ── Step 2: Diarization ────────────────────────────────────────────────
        logger.info("=== Step 2/3: Diarization ===")
        t0 = time.time()
        diarization = diarize_audio(processing_file, model_dir)
        metrics["timing"]["diarization"] = round(time.time() - t0, 2)

        # ── Step 3: Alignment ──────────────────────────────────────────────────
        logger.info("=== Step 3/3: Alignment ===")
        t0 = time.time()
        conversation = format_conversation(diarization, segments)
        metrics["timing"]["alignment"] = round(time.time() - t0, 2)

        # ── Build output ───────────────────────────────────────────────────────
        formatted_lines = []
        for seg in conversation:
            time_str = format_time(seg["start_time"])
            conf_lvl = seg.get("confidence_level", "")
            indicator = {"high": "✓ ", "medium": "~ ", "low": "? "}.get(conf_lvl, "")
            formatted_lines.append(
                f"[{time_str}] {indicator}Speaker {seg['speaker']}: {seg['text']}"
            )

        metrics["formatted_lines"] = formatted_lines
        metrics["transcript"] = [
            {
                "speaker": seg["speaker"],
                "text": seg["text"],
                "start_time": seg["start_time"],
                "end_time": seg["end_time"],
                "start_time_formatted": format_time(seg["start_time"]),
                "end_time_formatted": format_time(seg["end_time"]),
                "confidence": seg.get("confidence"),
                "confidence_level": seg.get("confidence_level"),
                "segments": seg.get("segments", []),
                "language": metrics["language"],
            }
            for seg in conversation
        ]

        metrics["total_time"] = round(time.time() - start_total, 2)
        logger.info(
            f"Done in {metrics['total_time']}s | "
            f"Language: {metrics['language']} | "
            f"Avg confidence: {metrics['confidence_metrics'].get('average', 'N/A')}%"
        )
        return metrics

    finally:
        if converted_file and os.path.exists(converted_file):
            try:
                os.unlink(converted_file)
            except Exception:
                pass


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Transcribe + diarize an audio file using Whisper medium + pyannote 3.1"
    )
    parser.add_argument(
        "audio_file",
        help="Path to the audio file (WAV, MP3, M4A, FLAC, OGG, WEBM)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code for transcription, e.g. 'en', 'hi'. Omit for auto-detection.",
    )
    parser.add_argument(
        "--model-dir",
        default=os.environ.get(
            "DIARIZATION_MODEL_PATH",
            "/home/aniket/MeetingSummarizer/models/speaker-diarization-3.1",
        ),
        help=(
            "Path to the local pyannote speaker-diarization-3.1 model directory. "
            "Defaults to env var DIARIZATION_MODEL_PATH or MeetingSummarizer's models path."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to save the full JSON result. Omit to print to stdout.",
    )
    args = parser.parse_args()

    audio_path = os.path.abspath(args.audio_file)
    if not os.path.exists(audio_path):
        logger.error(f"Audio file not found: {audio_path}")
        sys.exit(1)

    model_dir = args.model_dir
    if not Path(model_dir).exists():
        logger.error(
            f"Model directory not found: {model_dir}\n"
            "Set --model-dir or the DIARIZATION_MODEL_PATH env var to your local pyannote model path."
        )
        sys.exit(1)

    logger.info(f"Audio file : {audio_path}")
    logger.info(f"Language   : {args.language or 'auto-detect'}")
    logger.info(f"Model dir  : {model_dir}")

    result = process_audio(audio_path, language=args.language, model_dir=model_dir)

    # ── Print formatted transcript ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("TRANSCRIPT")
    print("=" * 70)
    for line in result["formatted_lines"]:
        print(line)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Language        : {result['language']}")
    print(f"  Total time      : {result['total_time']}s")
    print(f"  Transcription   : {result['timing'].get('transcription', 'N/A')}s")
    print(f"  Diarization     : {result['timing'].get('diarization', 'N/A')}s")
    print(f"  Alignment       : {result['timing'].get('alignment', 'N/A')}s")
    conf = result.get("confidence_metrics", {})
    if conf:
        print(f"  Avg confidence  : {conf.get('average', 'N/A')}%")
        print(f"  Low-conf segs   : {conf.get('low_confidence_count', 0)} "
              f"({conf.get('low_confidence_percentage', 0)}%)")
    print("=" * 70)

    # ── Save / print JSON ──────────────────────────────────────────────────────
    if args.output:
        out_path = os.path.abspath(args.output)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"Full result saved to: {out_path}")
    else:
        print("\nFull JSON result:")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
