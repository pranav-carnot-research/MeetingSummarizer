import whisper
import torchaudio
import logging

# Configure logging
logger = logging.getLogger("audio-processor")

# pyannote expects torchaudio.AudioMetaData; newer torchaudio exposes it only via _torchaudio
if not hasattr(torchaudio, "AudioMetaData"):  # guard for newer torchaudio versions
    try:
        from torchaudio._torchaudio import AudioMetaData as _AudioMetaData  # type: ignore
        torchaudio.AudioMetaData = _AudioMetaData  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("Could not monkey-patch torchaudio.AudioMetaData. Pyannote might encounter issues.")
from pyannote.audio import Pipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook
import torch
import os
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
try:
    torch.set_num_threads(4)
    torch.set_num_interop_threads(4)
except Exception:
    pass
import numpy as np
import librosa
import time
from datetime import datetime, timezone
import tempfile
from typing import Dict, List, Any, Optional, Callable
from pydub import AudioSegment
import soundfile as sf
from pathlib import Path

# Global caches for models
_whisper_cache = {}
_pyannote_cache = {}

# Enable for better performance if using CUDA
if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

def format_time(seconds: float) -> str:
    """Format seconds into HH:MM:SS format"""
    return datetime.fromtimestamp(seconds, timezone.utc).strftime('%H:%M:%S')

def preprocess_audio(audio_file: str) -> str:
    """
    Preprocess audio file to ensure compatibility with diarization

    Args:
        audio_file: Path to the audio file

    Returns:
        Path to preprocessed audio file
    """
    logger.info(f"Preprocessing audio file: {audio_file}")

    try:
        # Create a temporary file for the processed audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            processed_file = tmp_file.name

        # Load the audio file with pydub (handles many formats)
        audio = AudioSegment.from_file(audio_file)

        # Convert to standard format: WAV, mono, 16kHz, 16-bit
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

        # Export to the temporary file
        audio.export(processed_file, format="wav")

        logger.info(f"Preprocessed audio saved to: {processed_file}")
        return processed_file

    except Exception as e:
        logger.error(f"Error preprocessing audio: {str(e)}")
        # If preprocessing fails, return the original file
        return audio_file

def _transcribe_with_per_chunk_language_detection(
    model, audio: np.ndarray, transcribe_options: Dict[str, Any], chunk_duration: int = 30, sample_rate: int = 16000
) -> Dict[str, Any]:
    """
    Transcribe long audio in fixed-size chunks, re-detecting language for each chunk
    instead of once for the whole file. Whisper's high-level transcribe() only detects
    language from the first ~30s and then locks it in for the entire file, which breaks
    down on code-switched audio (e.g. Hindi + English in the same recording).
    """
    chunk_samples = int(chunk_duration * sample_rate)
    all_segments = []
    languages_detected = []
    next_id = 0

    for chunk_start_sample in range(0, len(audio), chunk_samples):
        chunk = audio[chunk_start_sample:chunk_start_sample + chunk_samples]
        if len(chunk) < sample_rate * 0.5:  # skip trailing slivers under 0.5s
            continue

        chunk_offset_sec = chunk_start_sample / sample_rate
        chunk_tensor = torch.tensor(chunk)

        try:
            chunk_result = model.transcribe(chunk_tensor, **transcribe_options)
        except Exception as e:
            logger.warning(f"Chunk at {chunk_offset_sec:.1f}s failed to transcribe: {e}")
            continue

        chunk_lang = chunk_result.get('language')
        if chunk_lang:
            languages_detected.append(chunk_lang)

        for segment in chunk_result.get("segments", []):
            segment = dict(segment)
            segment["id"] = next_id
            next_id += 1
            segment["start"] = segment.get("start", 0) + chunk_offset_sec
            segment["end"] = segment.get("end", 0) + chunk_offset_sec
            if "words" in segment and segment["words"]:
                adjusted_words = []
                for word in segment["words"]:
                    word = dict(word)
                    word["start"] = word.get("start", 0) + chunk_offset_sec
                    word["end"] = word.get("end", 0) + chunk_offset_sec
                    adjusted_words.append(word)
                segment["words"] = adjusted_words
            all_segments.append(segment)

    # Overall language = most common language across chunks
    overall_language = None
    if languages_detected:
        overall_language = max(set(languages_detected), key=languages_detected.count)

    return {
        "segments": all_segments,
        "language": overall_language,
        "languages_detected": languages_detected,
    }


def transcribe_audio(audio_file: str, language: Optional[str] = None) -> Dict[str, Any]:
    """
    Transcribe audio file using Whisper model
    Returns segments with start time, end time, text, and confidence scores

    Args:
        audio_file: Path to the audio file
        language: Optional language code (e.g., 'hi' for Hindi, None for auto-detection)
    """
    # Use cached model if available to avoid reloading from disk
    model_size = "small"
    if model_size not in _whisper_cache:
        logger.info(f"Loading Whisper model '{model_size}' from disk...")
        _whisper_cache[model_size] = whisper.load_model(model_size)
    else:
        logger.info(f"Using cached Whisper model '{model_size}'")
    model = _whisper_cache[model_size]

    # Load audio with librosa at 16kHz sample rate
    audio = librosa.load(audio_file, sr=16000)[0]

    # Peak normalize audio for optimum Whisper log-mel spectrogram feature extraction
    if len(audio) > 0 and np.max(np.abs(audio)) > 0:
        audio = audio / np.max(np.abs(audio)) * 0.95

    # Configure high-accuracy Whisper ASR transcription parameters
    transcribe_options = {
        "word_timestamps": True,          # Enable word-level timestamps & probabilities
        "beam_size": 5,                   # Deep beam search (5 beam width) instead of greedy decoding
        "best_of": 5,                     # Sample 5 candidate sequences
        "patience": 1.0,                  # Patience for beam search decoding
        "temperature": 0.0,               # Single pass only — no retry cascade on low-confidence segments
        "suppress_tokens": [-1],          # Don't suppress any tokens
        "without_timestamps": False,      # Keep exact word timestamps
        "initial_prompt": "This is a formal meeting transcript discussing technical project updates, action items, schedules, and metrics.",
        "fp16": False                     # Always use FP32 — FP16 on Tesla T4 causes incorrect language detection (English detected as Hindi)
    }

    # Add language if specified
    explicit_language = bool(language and language != "auto")
    if explicit_language:
        transcribe_options["language"] = language

    detected_language = None
    try:
        if explicit_language:
            # Single language already known — no need to chunk for re-detection.
            audio_tensor = audio if isinstance(audio, torch.Tensor) else torch.tensor(audio)
            result = model.transcribe(audio_tensor, **transcribe_options)
            detected_language = result.get('language')
            logger.info(f"Transcribed with specified language: {language}")
        else:
            # Auto-detect mode: use per-chunk language detection for code-switched audio
            result = _transcribe_with_per_chunk_language_detection(
                model, audio, transcribe_options, chunk_duration=30
            )
            detected_language = result.get('language')
            logger.info(f"Transcribed with per-chunk auto-detected language(s): {result.get('languages_detected')}")
    except Exception as e:
        logger.error(f"Error in transcription: {str(e)}")
        # Fallback to English if transcription fails
        transcribe_options["language"] = "en"
        try:
            result = model.transcribe(audio, **transcribe_options)
            logger.info("Falling back to English transcription")
        except Exception as e2:
            logger.error(f"Even fallback transcription failed: {str(e2)}")
            raise RuntimeError(f"Failed to transcribe audio: {str(e2)}")

    # Add the detected language to the result if it wasn't provided
    if not language and detected_language:
        result['detected_language'] = detected_language

    # Process segments to add confidence scores
    enhanced_segments = []
    for segment in result["segments"]:
        # Extract basic segment info
        segment_info = {
            "id": segment.get("id", 0),
            "start": segment.get("start", 0),
            "end": segment.get("end", 0),
            "text": segment.get("text", "").strip(),
        }

        # Extract confidence scores
        # Method 1: Average token probabilities if available
        if "avg_logprob" in segment:
            # Convert log probability to confidence percentage (0-100)
            # logprob is negative, closer to 0 means higher confidence
            # Typical values range from -1 (high confidence) to -5 (low confidence)
            logprob = segment["avg_logprob"]
            # Scale to 0-100 range, with -1 or better mapping to ~90-100%
            confidence = min(100, max(0, 100 + 20 * logprob))
            segment_info["confidence"] = round(confidence, 2)
            segment_info["avg_logprob"] = logprob
        else:
            # If avg_logprob not available, try a different approach
            segment_info["confidence"] = None

        # Method 2: Try to get token-level probabilities if available
        if "tokens" in segment and "token_probs" in segment:
            tokens = segment.get("tokens", [])
            token_probs = segment.get("token_probs", [])

            # Only process if we have valid data
            if tokens and token_probs and len(tokens) == len(token_probs):
                # Calculate average probability for non-None values
                valid_probs = [p for p in token_probs if p is not None]
                if valid_probs:
                    avg_token_prob = sum(valid_probs) / len(valid_probs)
                    # Convert to percentage
                    token_confidence = 100 * avg_token_prob
                    segment_info["token_confidence"] = round(token_confidence, 2)

                    # If we didn't have avg_logprob, use this as the main confidence
                    if segment_info["confidence"] is None:
                        segment_info["confidence"] = segment_info["token_confidence"]

                # Include token-level details if detailed logging is needed
                token_details = []
                for i, (token, prob) in enumerate(zip(tokens, token_probs)):
                    if prob is not None:
                        token_details.append({
                            "token": token,
                            "probability": prob
                        })
                segment_info["tokens"] = token_details

        # Method 3: If no probability data available, estimate from no_speech_prob
        if segment_info["confidence"] is None and "no_speech_prob" in segment:
            # Lower no_speech_prob means higher speech confidence
            speech_conf = 100 * (1 - segment.get("no_speech_prob", 0))
            segment_info["confidence"] = round(speech_conf, 2)
            segment_info["no_speech_prob"] = segment.get("no_speech_prob", 0)

        # Final fallback: If we still don't have confidence, set a default
        if segment_info["confidence"] is None:
            segment_info["confidence"] = 50.0  # Default mid-range confidence
            segment_info["confidence_source"] = "default"

        # Add word-level timestamps and confidence if available
        if "words" in segment:
            words_with_confidence = []
            for word in segment["words"]:
                word_info = {
                    "word": word.get("word", ""),
                    "start": word.get("start", 0),
                    "end": word.get("end", 0)
                }

                # Add probability if available, else fallback to segment confidence
                if "probability" in word:
                    word_info["confidence"] = round(100 * word.get("probability", 0), 2)
                elif "confidence" in word:
                    word_info["confidence"] = word.get("confidence")
                else:
                    word_info["confidence"] = segment_info.get("confidence", 85.0)

                w_conf = word_info["confidence"]
                if w_conf >= 90:
                    word_info["confidence_level"] = "high"
                elif w_conf >= 65:
                    word_info["confidence_level"] = "medium"
                else:
                    word_info["confidence_level"] = "low"

                words_with_confidence.append(word_info)

            segment_info["words"] = words_with_confidence

        # Add segment confidence categorization
        if segment_info["confidence"] >= 90:
            segment_info["confidence_level"] = "high"
        elif segment_info["confidence"] >= 70:
            segment_info["confidence_level"] = "medium"
        else:
            segment_info["confidence_level"] = "low"

        enhanced_segments.append(segment_info)

    # Replace the original segments with our enhanced ones
    result["segments"] = enhanced_segments

    # Add overall confidence metrics
    if enhanced_segments:
        confidences = [seg["confidence"] for seg in enhanced_segments if "confidence" in seg]
        if confidences:
            result["overall_confidence"] = {
                "average": round(sum(confidences) / len(confidences), 2),
                "min": round(min(confidences), 2),
                "max": round(max(confidences), 2)
            }

            # Flag if there are any low confidence segments
            low_confidence_segments = [s for s in enhanced_segments if s.get("confidence_level") == "low"]
            result["low_confidence_count"] = len(low_confidence_segments)
            result["low_confidence_percentage"] = round(100 * len(low_confidence_segments) / len(enhanced_segments), 2)

    return result

def diarize_audio(audio_file: str) -> Any:
    """
    Perform speaker diarization on audio file
    Returns segments with speaker identifications

    Args:
        audio_file: Path to the audio file

    Returns:
        Diarization result
    """
    from services.audio_converter import needs_conversion, convert_audio_to_wav
    
    logger.info(f"Starting diarization for file: {audio_file}")

    # Track if we create a temporary file that needs cleanup
    temp_file = None

    try:
        # Convert to WAV if needed
        if needs_conversion(audio_file):
            logger.info(f"Converting file to WAV before diarization: {audio_file}")
            temp_file = convert_audio_to_wav(audio_file)
            logger.info(f"Using converted file for diarization: {temp_file}")
            audio_file_to_process = temp_file
        else:
            audio_file_to_process = audio_file

        # ── Local model path (set via env var or hardcode) ──────────────────
        model_dir = os.environ.get(
            "DIARIZATION_MODEL_PATH",
            "./models/speaker-diarization-3.1"
        )

        config_path = Path(model_dir) / "config.yaml"
        
        # Use cached pipeline if available
        cache_key = str(config_path)
        if cache_key not in _pyannote_cache:
            logger.info(f"Loading diarization pipeline from local path: {model_dir}")
            
            # PyTorch 2.6+ / 2.8 compatibility: pyannote models use many internal
            # classes in their checkpoint files. We must allowlist ALL of them via
            # add_safe_globals. We import the full pyannote.audio.core.task module
            # and register every class it exposes to avoid chasing them one by one.
            import torch.serialization
            import inspect
            try:
                from torch import torch_version
                import pyannote.audio.core.task as _pann_task
                import pyannote.audio.core.model as _pann_model

                # Collect every class defined in these modules
                _safe_classes = [torch_version.TorchVersion]
                for _name, _obj in inspect.getmembers(_pann_task, inspect.isclass):
                    _safe_classes.append(_obj)
                for _name, _obj in inspect.getmembers(_pann_model, inspect.isclass):
                    _safe_classes.append(_obj)

                torch.serialization.add_safe_globals(_safe_classes)
                logger.info(f"Registered {len(_safe_classes)} pyannote classes in torch safe_globals")
            except Exception as _e:
                logger.warning(f"add_safe_globals partial/skipped: {_e}")

            # Belt-and-suspenders: use safe_globals context manager which
            # works even if pyannote cached its torch.load reference at import time
            with torch.serialization.safe_globals([]):
                pipeline = Pipeline.from_pretrained(config_path)

            pipeline.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
            _pyannote_cache[cache_key] = pipeline
        else:
            logger.info("Using cached diarization pipeline")
        diarization_pipeline = _pyannote_cache[cache_key]

        # Process with progress hook
        with ProgressHook() as hook:
            diarization_result = diarization_pipeline(audio_file_to_process, hook=hook)
            logger.info("Diarization completed successfully")
            return diarization_result

    except Exception as e:
        logger.error(f"Diarization error: {str(e)}")

        # Fall back to simpler diarization approach
        from pyannote.core import Segment, Annotation

        logger.warning("Creating fallback diarization result")
        annotation = Annotation()

        try:
            # Try to get file duration
            y, sr = librosa.load(audio_file, sr=16000, mono=True, duration=10)
            duration = librosa.get_duration(y=y, sr=sr)
        except:
            # Default duration if we can't determine it
            duration = 300  # 5 minutes

        # Create a single segment with one speaker
        segment = Segment(0, duration)
        annotation[segment] = "SPEAKER_00"

        return annotation

    finally:
        # Clean up any temporary file we created
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
                logger.info(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Could not delete temporary file {temp_file}: {str(e)}")

def create_fallback_diarization(audio_file: str) -> Any:
    """
    Create a fallback diarization result when pyannote fails

    Args:
        audio_file: Path to the audio file

    Returns:
        A mock diarization result
    """
    logger.warning(f"Creating fallback diarization for {audio_file}")

    try:
        # Import pyannote core for annotation objects
        from pyannote.core import Segment, Annotation

        # Create a simple annotation with just one speaker if we can't process properly
        annotation = Annotation()

        # Try to get file duration
        try:
            y, sr = librosa.load(audio_file, sr=16000, mono=True, duration=10)
            duration = librosa.get_duration(y=y, sr=sr)
        except:
            # Default duration if we can't determine it
            duration = 300  # 5 minutes

        # Create a single segment with one speaker
        segment = Segment(0, duration)
        annotation[segment] = "SPEAKER_00"

        logger.info(f"Created fallback diarization with duration {duration}s")
        return annotation

    except Exception as e:
        logger.error(f"Fallback diarization failed: {str(e)}")

        # If all else fails, create an extremely minimal annotation
        from pyannote.core import Segment, Annotation
        annotation = Annotation()
        segment = Segment(0, 300)  # Assume 5 minutes
        annotation[segment] = "SPEAKER_00"

        return annotation

def fallback_diarization(audio_file: str) -> Any:
    """
    Provide a fallback diarization when pyannote fails
    This creates a very simple speaker separation based on silence detection

    Args:
        audio_file: Path to the audio file

    Returns:
        Mock diarization result that can be used by the formatter
    """
    logger.warning("Using fallback diarization method")

    try:
        # Load audio
        y, sr = librosa.load(audio_file, sr=16000, mono=True)

        # Detect speech segments based on energy levels
        non_silent_intervals = librosa.effects.split(y, top_db=30)

        # Create a mock diarization result
        # This is a simplified version that mimics pyannote.audio's format
        from pyannote.core import Segment, Timeline, Annotation

        # Create an annotation to hold our segments
        annotation = Annotation()

        # Create some segments based on silence detection
        current_speaker = 0
        for i, (start, end) in enumerate(non_silent_intervals):
            # Convert sample indices to seconds
            start_sec = start / sr
            end_sec = end / sr

            # Change speaker when we detect a longer pause (more than 1 second)
            if i > 0:
                prev_end = non_silent_intervals[i-1][1] / sr
                if start_sec - prev_end > 1.0:
                    current_speaker = (current_speaker + 1) % 3  # Rotate between 3 speakers

            # Add segment to the annotation
            segment = Segment(start_sec, end_sec)
            annotation[segment] = str(current_speaker)

        logger.info(f"Fallback diarization created {len(annotation)} segments with {len(set(annotation.labels()))} speakers")
        return annotation

    except Exception as e:
        logger.error(f"Fallback diarization failed: {str(e)}")

        # Create an extremely simple mock result with just one speaker
        from pyannote.core import Segment, Annotation

        annotation = Annotation()

        # Just create one segment for the entire audio
        try:
            # Try to get audio duration
            y, sr = librosa.load(audio_file, sr=16000, mono=True, duration=10)  # Just load a bit to get info
            duration = librosa.get_duration(y=y, sr=sr)
            segment = Segment(0, duration)
        except:
            # If all else fails, assume a 5-minute audio
            segment = Segment(0, 300)

        annotation[segment] = "0"

        logger.warning("Created emergency single-speaker diarization")
        return annotation

def format_conversation(diarization_result, transcription_segments):
    """
    Align transcription with speaker segments
    Returns conversation data with speaker labels and confidence scores
    Creates one conversation segment per transcription segment to preserve granularity
    """
    conversation_data = []

    # Pyannote 4 returns a DiarizeOutput object, older versions return Annotation directly
    if hasattr(diarization_result, "speaker_diarization"):
        diarization_result = diarization_result.speaker_diarization
        
    # Sort diarization turns and transcription segments by start time
    diarization_turns = sorted(diarization_result.itertracks(yield_label=True), key=lambda x: x[0].start)
    transcription_segments = sorted(transcription_segments, key=lambda x: x["start"])

    # Build speaker map for efficient lookup
    speaker_map = [(turn.start, turn.end, speaker) for turn, _, speaker in diarization_turns]

    # Process each transcription segment individually
    for segment in transcription_segments:
        seg_start = segment["start"]
        seg_end = segment["end"]
        seg_mid = (seg_start + seg_end) / 2

        # Find speaker by checking which diarization turn contains the segment midpoint
        assigned_speaker = None
        for turn_start, turn_end, speaker in speaker_map:
            if turn_start <= seg_mid <= turn_end:
                assigned_speaker = speaker
                break

        # If no exact match, find turn with maximum overlap
        if assigned_speaker is None:
            max_overlap = 0
            for turn_start, turn_end, speaker in speaker_map:
                overlap_start = max(turn_start, seg_start)
                overlap_end = min(turn_end, seg_end)
                overlap_duration = max(0, overlap_end - overlap_start)
                if overlap_duration > max_overlap:
                    max_overlap = overlap_duration
                    assigned_speaker = speaker

        # Default to first speaker if no match
        if assigned_speaker is None and speaker_map:
            assigned_speaker = speaker_map[0][2]

        # Create conversation segment for this transcription segment
        conversation_segment = {
            "speaker": assigned_speaker or "UNKNOWN",
            "text": segment["text"].strip(),
            "start_time": seg_start,
            "end_time": seg_end,
            "start": seg_start,
            "end": seg_end,
            "words": segment.get("words", [])
        }

        # Add confidence if available
        if "confidence" in segment:
            conversation_segment["confidence"] = segment["confidence"]
            if conversation_segment["confidence"] >= 90:
                conversation_segment["confidence_level"] = "high"
            elif conversation_segment["confidence"] >= 70:
                conversation_segment["confidence_level"] = "medium"
            else:
                conversation_segment["confidence_level"] = "low"
        elif "confidence_level" in segment:
            conversation_segment["confidence_level"] = segment["confidence_level"]

        # Store segment details
        conversation_segment["segments"] = [{
            "text": segment["text"].strip(),
            "start": segment["start"],
            "end": segment["end"],
            "confidence": segment.get("confidence", None),
            "confidence_level": segment.get("confidence_level", None),
            "words": segment.get("words", [])
        }]

        conversation_data.append(conversation_segment)

    return conversation_data

def process_audio_file(audio_file_path: str, language: Optional[str] = None) -> Dict[str, Any]:
    """
    Process audio file to extract transcript with speaker identification and confidence scores

    Args:
        audio_file_path: Path to the audio file
        language: Optional language code (e.g., 'hi' for Hindi, None for auto-detection)

    Returns:
        Dictionary containing the transcript data and processing metrics
    """
    metrics = {
        'total_time': 0,
        'step_times': {},
        'transcript': [],
        'formatted_transcript': [],
        'language': language or 'auto-detect',
        'confidence_metrics': {}
    }

    try:
        start_total = time.time()
        # Ensure audio is in WAV format before passing to Whisper/Librosa
        from services.audio_converter import needs_conversion, convert_audio_to_wav
        
        original_file_path = audio_file_path
        if needs_conversion(audio_file_path):
            logger.info(f"Converting audio to WAV format before processing: {audio_file_path}")
            try:
                audio_file_path = convert_audio_to_wav(audio_file_path)
            except Exception as e:
                logger.error(f"Failed to convert audio: {str(e)}")
                # Continue with original and hope librosa handles it via ffmpeg fallback
        
        # Transcribe with timing
        step_start = time.time()
        transcription_result = transcribe_audio(audio_file_path, language)
        transcription_segments = transcription_result["segments"]  # Contains 'start', 'end', 'text', 'confidence'
        metrics['step_times']['transcription'] = time.time() - step_start

        # Include overall confidence metrics if available
        if "overall_confidence" in transcription_result:
            metrics['confidence_metrics'] = transcription_result["overall_confidence"]

            # Add counts of low confidence segments
            if "low_confidence_count" in transcription_result:
                metrics['confidence_metrics']["low_confidence_count"] = transcription_result["low_confidence_count"]
                metrics['confidence_metrics']["low_confidence_percentage"] = transcription_result["low_confidence_percentage"]

        # If language was auto-detected, get the detected language
        if not language or language == "auto":
            # First try to get the language from the detected_language field we added
            if 'detected_language' in transcription_result:
                detected_language = transcription_result['detected_language']
                metrics['language'] = detected_language  # Store the actual language code
                logger.info(f"Using explicit detected_language field: {detected_language}")
            # Fall back to looking in the language field
            elif 'language' in transcription_result:
                detected_language = transcription_result['language']
                metrics['language'] = detected_language  # Store the actual language code
                logger.info(f"Using language field from result: {detected_language}")
            # Fall back to looking in the segments if needed
            elif transcription_segments and len(transcription_segments) > 0:
                first_segment = transcription_segments[0]
                if 'language' in first_segment:
                    detected_language = first_segment['language']
                    metrics['language'] = detected_language  # Store the actual language code
                    logger.info(f"Extracted language from first segment: {detected_language}")
                else:
                    logger.warning(f"No language field in first segment. Keys: {list(first_segment.keys())}")
            else:
                logger.warning("Could not determine specific language from transcription")
                # Keep auto-detect in this case

        # Diarize with timing
        logger.info(f"Diarizing audio file {audio_file_path}")
        step_start = time.time()
        diarization_result = diarize_audio(audio_file_path)
        metrics['step_times']['diarization'] = time.time() - step_start

        # Store raw Whisper transcription (before diarization merge) for UI display
        metrics['raw_transcription'] = [{
            'id': seg.get('id', i),
            'start': seg.get('start', 0),
            'end': seg.get('end', 0),
            'start_formatted': format_time(seg.get('start', 0)),
            'text': seg.get('text', '').strip(),
            'confidence': seg.get('confidence'),
            'confidence_level': seg.get('confidence_level'),
            'words': seg.get('words', []),
        } for i, seg in enumerate(transcription_segments)]

        # Format with timing
        step_start = time.time()
        conversation_data = format_conversation(diarization_result, transcription_segments)
        metrics['step_times']['formatting'] = time.time() - step_start

        # Create enhanced transcript with timestamps and confidence indicators
        formatted_transcript = []
        for seg in conversation_data:
            time_str = format_time(seg['start_time'])

            # Add confidence indicator to formatted text if available
            if 'confidence_level' in seg:
                confidence_indicator = ""
                if seg['confidence_level'] == "high":
                    confidence_indicator = "✓ "  # Check mark for high confidence
                elif seg['confidence_level'] == "medium":
                    confidence_indicator = "~ "  # Tilde for medium confidence
                else:
                    confidence_indicator = "? "  # Question mark for low confidence

                formatted_line = f"[{time_str}] {confidence_indicator}Speaker {seg['speaker']}: {seg['text']}"
            else:
                formatted_line = f"[{time_str}] Speaker {seg['speaker']}: {seg['text']}"

            formatted_transcript.append(formatted_line)

        # Final metrics
        metrics['total_time'] = time.time() - start_total
        metrics['formatted_transcript'] = formatted_transcript

        # Enhanced transcript with confidence scores and word-level metadata
        metrics['transcript'] = [{
            'speaker': seg['speaker'],
            'text': seg['text'],
            'start_time': seg['start_time'],
            'end_time': seg['end_time'],
            'start': seg.get('start', seg['start_time']),
            'end': seg.get('end', seg['end_time']),
            'start_time_formatted': format_time(seg['start_time']),
            'end_time_formatted': format_time(seg['end_time']),
            'confidence': seg.get('confidence', None),
            'confidence_level': seg.get('confidence_level', None),
            'words': seg.get('words', []),
            'segments': seg.get('segments', []),
            'language': metrics['language']
        } for seg in conversation_data]

        # Explicit top-level segments key for API JSON payloads
        metrics['segments'] = metrics['transcript']

        # Final check to confirm the language is being properly returned
        logger.info(f"Final language being returned: {metrics['language']}")
        logger.info(f"Overall confidence: {metrics.get('confidence_metrics', {}).get('average', 'N/A')}%")

        # Calculate speaker-specific confidence metrics
        speaker_confidences = {}

        # Group segments by speaker
        for segment in conversation_data:
            speaker = segment['speaker']
            if speaker not in speaker_confidences:
                speaker_confidences[speaker] = []

            if 'confidence' in segment:
                speaker_confidences[speaker].append(segment['confidence'])

        # Calculate average confidence for each speaker
        speaker_metrics = {}
        for speaker, confidences in speaker_confidences.items():
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                speaker_metrics[speaker] = {
                    "average_confidence": round(avg_confidence, 2),
                    "min_confidence": round(min(confidences), 2) if confidences else None,
                    "max_confidence": round(max(confidences), 2) if confidences else None,
                    "confidence_level": "high" if avg_confidence >= 90 else
                                      ("medium" if avg_confidence >= 70 else "low"),
                    "segment_count": len(confidences)
                }
        
        # Add to metrics
        if speaker_metrics:
            metrics['speaker_confidence_metrics'] = speaker_metrics
        # Clean up the converted file if we created one
        if 'original_file_path' in locals() and original_file_path != audio_file_path and os.path.exists(audio_file_path):
            try:
                os.unlink(audio_file_path)
            except:
                pass
        return metrics

    except Exception as e:
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        raise