from fastapi import FastAPI, File, UploadFile, BackgroundTasks, Form, HTTPException, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Union
import uuid
import os
import re
import shutil
import tempfile
import json
import logging
from datetime import datetime
from pathlib import Path
from pydub import AudioSegment

# Import configuration
from config import settings, get_settings

# Import processing modules
from services.audio_service import process_audio_file, process_long_audio
from services.text_service import extract_participants
from services.summarization_service import summarize_meeting, summarize_long_meeting, generate_speaker_summaries
from services.job_service import JobStatus, get_job_status, update_job_status, save_job_result
from services.utils import format_time

# Configure logging — single consolidated setup
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('language_detection.log')
    ]
)
logger = logging.getLogger("meeting-summarizer-api")
lang_logger = logging.getLogger('language-detection')
# Initialize Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Initialize FastAPI app
app = FastAPI(
    title="Meeting Summarizer API",
    description="API for summarizing meeting recordings and transcripts",
    version="1.0.0"
)

# Mount static files and recordings directories
os.makedirs("recordings", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/recordings", StaticFiles(directory="recordings"), name="recordings")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://localhost:5173", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models for request/response
class TextRequest(BaseModel):
    transcript: str
    participants: Optional[List[str]] = None
    language: Optional[str] = None

class ProcessRequest(BaseModel):
    transcript: str
    participants: List[str]
    language: Optional[str] = None
    is_long_recording: bool = False
    additional_context: Optional[str] = None  # New field for meeting context


class JobResponse(BaseModel):
    job_id: str
    status: str

class LanguageOption(BaseModel):
    code: str
    name: str

class VocabularyRequest(BaseModel):
    term: str

# Serve the main application page
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Serve the main application page"""
    return templates.TemplateResponse(request, "index.html")

# Endpoint to get supported languages
@app.get("/api/languages", response_model=List[LanguageOption])
async def get_languages():
    """Get a list of supported languages for transcription and summarization"""
    languages = [
        {"code": "auto", "name": "Auto-detect"},
        {"code": "en", "name": "English"},
        {"code": "hi", "name": "Hindi"},
        {"code": "es", "name": "Spanish"},
        {"code": "fr", "name": "French"},
        {"code": "de", "name": "German"},
        {"code": "zh", "name": "Chinese"},
        {"code": "ja", "name": "Japanese"},
        {"code": "ru", "name": "Russian"},
        {"code": "ar", "name": "Arabic"}
    ]
    return languages

# Endpoint to upload and process audio
@app.post("/api/upload-audio", response_model=JobResponse)
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    is_long_recording: bool = Form(False)
):
    """
    Upload an audio file for processing.
    
    - The file will be processed in the background
    - Speaker diarization will be performed automatically
    - Returns a job ID that can be used to check progress
    """
    # Generate a unique job ID
    job_id = str(uuid.uuid4())
    
    # Save the uploaded file to a temporary location
    audio_file_path = None
    try:
        # Create a temporary file with the correct extension
        suffix = f".{file.filename.split('.')[-1]}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            # Write the uploaded file content
            content = await file.read()
            tmp.write(content)
            audio_file_path = tmp.name
        
        # Initialize job status
        update_job_status(job_id, JobStatus.PENDING, "Audio file received, processing will start soon")
        
        # Process the audio file in the background
        background_tasks.add_task(
            process_audio_background,
            job_id,
            audio_file_path,
            language,
            is_long_recording
        )
        
        return {"job_id": job_id, "status": "pending"}
    except Exception as e:
        logger.error(f"Error processing audio upload: {str(e)}")
        # Clean up temporary file if it exists
        if audio_file_path and os.path.exists(audio_file_path):
            os.unlink(audio_file_path)
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")

# Background task to process audio
# Updated process_audio_background function in main.py

async def process_audio_background(job_id: str, audio_path: str, language: Optional[str], is_long_recording: bool):
    """Process audio file in the background and update job status"""
    temp_files = []  # Track any temporary files we create
    
    try:
        update_job_status(job_id, JobStatus.PROCESSING, "Processing audio file")
        
        # First, check if this is an MP3 file and convert if needed
        from pathlib import Path
        from services.audio_converter import needs_conversion, convert_audio_to_wav
        
        if needs_conversion(audio_path):
            # Update status to show we're converting
            update_job_status(job_id, JobStatus.PROCESSING, "Converting audio to WAV format", progress=10)
            
            try:
                # Convert to WAV format
                wav_path = convert_audio_to_wav(audio_path)
                temp_files.append(wav_path)  # Track for cleanup
                audio_path_to_process = wav_path
                logger.info(f"Converted MP3 to WAV: {wav_path}")
            except Exception as e:
                logger.error(f"Error converting MP3: {str(e)}")
                # Continue with original file if conversion fails
                audio_path_to_process = audio_path
                update_job_status(job_id, JobStatus.PROCESSING, "Conversion failed, trying with original file", progress=10)
        else:
            audio_path_to_process = audio_path
            
        # Save a copy to a permanent recordings/ folder in the project root
        try:
            recordings_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            permanent_audio_path = os.path.join(recordings_dir, f"{job_id}.wav")
            shutil.copy2(audio_path_to_process, permanent_audio_path)
            logger.info(f"Saved copy of processed audio to: {permanent_audio_path}")
        except Exception as e:
            logger.error(f"Failed to copy processed audio to recordings/ directory: {str(e)}")
        
        # Check if we should use long processing or standard processing
        is_short_audio = False
        try:
            audio = AudioSegment.from_file(audio_path_to_process)
            duration_seconds = len(audio) / 1000
            logger.info(f"Audio duration: {duration_seconds} seconds")
            
            # If audio is less than 30 seconds, always use standard processing
            if duration_seconds < 30:
                is_short_audio = True
                logger.info(f"Audio is very short ({duration_seconds}s), using standard processing")
                update_job_status(job_id, JobStatus.PROCESSING, f"Audio is short ({duration_seconds}s), using standard processing", progress=15)
        except Exception as e:
            logger.warning(f"Could not determine audio length: {str(e)}")
            # Continue with the user's choice
        
        # Process audio based on length and user selection
        if is_long_recording and not is_short_audio:
            # Define a progress callback function
            def progress_callback(progress, status):
                # Scale progress to leave room for initial conversion (10%)
                scaled_progress = 10 + (progress * 0.9)  # 10-100%
                update_job_status(
                    job_id, 
                    JobStatus.PROCESSING, 
                    status,
                    progress=scaled_progress
                )
            
            # Process long audio with progress updates
            result = process_long_audio(audio_path_to_process, language=language, progress_callback=progress_callback)
        else:
            # Process standard audio
            result = process_audio_file(audio_path_to_process, language=language)
            # Simulate progress updates
            update_job_status(job_id, JobStatus.PROCESSING, "Transcribing audio", progress=33)
            update_job_status(job_id, JobStatus.PROCESSING, "Identifying speakers", progress=66)
            update_job_status(job_id, JobStatus.PROCESSING, "Finalizing transcript", progress=90)
        
        # Verify we got results - sanity check
        if not result.get('transcript') or not result.get('formatted_transcript'):
            logger.warning(f"Empty transcript detected! Result: {result}")
            
            # If standard processing failed to produce a transcript, try the other method
            if is_long_recording and is_short_audio:
                logger.info("Standard processing produced empty transcript. Trying long processing method.")
                update_job_status(job_id, JobStatus.PROCESSING, "Retrying with alternative processing method", progress=50)
                
                def progress_callback(progress, status):
                    scaled_progress = 50 + (progress * 0.5)  # 50-100%
                    update_job_status(job_id, JobStatus.PROCESSING, status, progress=scaled_progress)
                
                result = process_long_audio(audio_path_to_process, language=language, progress_callback=progress_callback)
            elif not is_long_recording:
                logger.info("Standard processing produced empty transcript. Trying long processing method.")
                update_job_status(job_id, JobStatus.PROCESSING, "Retrying with alternative processing method", progress=50)
                
                def progress_callback(progress, status):
                    scaled_progress = 50 + (progress * 0.5)  # 50-100%
                    update_job_status(job_id, JobStatus.PROCESSING, status, progress=scaled_progress)
                
                result = process_long_audio(audio_path_to_process, language=language, progress_callback=progress_callback)
        
        # Important: Get the actual detected language from the result
        detected_language = result.get('language', 'auto-detect')
        logger.info(f"Detected language for audio: {detected_language}")
        
        # Run Auto-Correction on Low-Confidence Words (< 65%) using Dictionary & Glossary matching
        if result:
            try:
                from services.autocorrect_service import autocorrect_low_confidence_words
                segs = result.get("segments") or result.get("transcript") or result.get("raw_transcription")
                if segs:
                    logger.info("Running Dictionary & Glossary Auto-Correction on low-confidence words...")
                    autocorrect_low_confidence_words(segs)
            except Exception as ac_err:
                logger.error(f"Error running auto-correction service: {str(ac_err)}")

            # Ensure all result fields are preserved
            save_job_result(job_id, result)
            update_job_status(job_id, JobStatus.COMPLETED, "Audio processing complete", progress=100)
        else:
            logger.error("No result received from audio processing")
            update_job_status(job_id, JobStatus.FAILED, "No result received from audio processing")
            
    except Exception as e:
        logger.error(f"Error in background processing: {str(e)}")
        update_job_status(job_id, JobStatus.FAILED, f"Error processing audio: {str(e)}")
        
    finally:
        # Clean up all temporary files
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                    logger.info(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Could not delete temporary file {temp_file}: {str(e)}")
        
        # Clean up the original file if it exists
        if os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
                logger.info(f"Cleaned up original file: {audio_path}")
            except Exception as e:
                logger.warning(f"Could not delete original file {audio_path}: {str(e)}")

# Endpoint to get job status
@app.get("/api/job/{job_id}", response_model=Dict[str, Any])
async def check_job_status(job_id: str):
    """Check the status of a background job"""
    job_status = get_job_status(job_id)
    if not job_status:
        raise HTTPException(status_code=404, detail=f"Job ID {job_id} not found")
    return job_status

# Endpoint to upload text file
@app.post("/api/upload-text", response_model=Dict[str, Any])
async def upload_text(file: UploadFile = File(...)):
    """Upload a transcript text file"""
    try:
        content = await file.read()
        transcript = content.decode("utf-8")
        
        # Extract participants from the transcript
        participants = extract_participants(transcript)
        
        return {
            "success": True,
            "transcript": transcript,
            "participants": participants,
            "character_count": len(transcript)
        }
    except Exception as e:
        logger.error(f"Error processing text upload: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing text: {str(e)}")

# Endpoint to extract participants from text
@app.post("/api/extract-participants", response_model=List[str])
async def get_participants(request: TextRequest):
    """Extract participant names from a transcript"""
    try:
        participants = extract_participants(request.transcript)
        return participants
    except Exception as e:
        logger.error(f"Error extracting participants: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error extracting participants: {str(e)}")
# Endpoint to save human-edited terms into custom glossary
@app.post("/api/vocabulary")
async def add_vocabulary(req: VocabularyRequest):
    try:
        from services.autocorrect_service import save_custom_term
        saved = save_custom_term(req.term)
        return {"status": "success", "saved": saved, "term": req.term}
    except Exception as e:
        logger.error(f"Error saving vocabulary term: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving vocabulary: {str(e)}")

# Endpoint to generate meeting summary
@app.post("/api/summarize", response_model=JobResponse)
async def summarize(background_tasks: BackgroundTasks, request: ProcessRequest):
    """
    Generate a meeting summary from a transcript
    
    - Takes a transcript and list of participants
    - Generates a summary with key points, decisions, and action items
    - Returns a job ID that can be used to check progress
    """
    # Generate a unique job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    update_job_status(job_id, JobStatus.PENDING, "Summarization request received")
    
    # Process the summary in the background
    background_tasks.add_task(
        summarize_background,
        job_id,
        request.transcript,
        request.participants,
        request.language,
        request.is_long_recording,
        request.additional_context
    )
    
    return {"job_id": job_id, "status": "pending"}

# Background task to generate summary
async def summarize_background(
    job_id: str, 
    transcript: str, 
    participants: List[str], 
    language: Optional[str],
    is_long_recording: bool,
    additional_context: Optional[str] = None  # Add parameter
):
    """Generate meeting summary in the background and update job status"""
    try:
        update_job_status(job_id, JobStatus.PROCESSING, "Analyzing transcript", progress=10)
        
        # CRITICAL: Fix language handling
        # Check if we're getting a placeholder instead of a real language code
        if language in ["auto", "auto-detect", "auto-detected"]:
            # This is problematic - log a warning
            logger.warning(f"Received '{language}' as language for summarization, which is not a specific language code")
            logger.warning("Attempting to detect language from transcript content")
            
            # Optionally try to detect language from transcript content
            # This is a fallback if the audio processing didn't provide a proper language code
            try:
                from langdetect import detect
                detected_lang = detect(transcript[:1000])  # Use first 1000 chars
                logger.info(f"Detected language from transcript text: {detected_lang}")
                language = detected_lang
            except Exception as e:
                logger.error(f"Error detecting language from transcript: {str(e)}")
                # Default to English if all else fails
                logger.warning("Defaulting to English for summarization")
                language = "en"
        
        # Log the final language being used
        logger.info(f"Generating summary with language: {language}")
        
        # Process based on length
        if is_long_recording:
            # Parse transcript into required format for long meeting
            # This would need to be implemented based on how the transcript is structured
            transcript_data = parse_transcript_to_segments(transcript)
            
            # Define progress callback
            def progress_callback(progress, status):
                update_job_status(job_id, JobStatus.PROCESSING, status, progress=progress)
            
            # Summarize long meeting, explicitly passing the language
            result = summarize_long_meeting(
                transcript_data,
                language=language,
                additional_context=additional_context,  # Pass context
                progress_callback=progress_callback
            )
        else:
            # Regular summarization, explicitly passing the language
            update_job_status(job_id, JobStatus.PROCESSING, "Generating meeting summary", progress=30)
            result = summarize_meeting(transcript, participants, 
                                  language=language,
                                  additional_context=additional_context)
            update_job_status(job_id, JobStatus.PROCESSING, "Extracting action items", progress=60)
        
        # Generate speaker summaries, passing the same language parameter
        update_job_status(job_id, JobStatus.PROCESSING, "Creating speaker summaries", progress=80)
        speaker_summaries = generate_speaker_summaries(transcript, participants, language=language)
        
        # Get the language name for display
        from services.utils import get_language_name
        language_name = get_language_name(language)
        
        # Get speaker confidence metrics from the result if available
        speaker_confidence_metrics = None
        if isinstance(result, dict) and "speaker_confidence_metrics" in result:
            speaker_confidence_metrics = result["speaker_confidence_metrics"]
            logger.info("Found speaker confidence metrics in processing result")
        
        # Combine results safely
        meeting_summary_val = result.get("meeting_summary") if isinstance(result, dict) else {}
        action_items_val = result.get("action_items", []) if isinstance(result, dict) else []
        
        final_result = {
            "meeting_summary": meeting_summary_val if meeting_summary_val else {"summary": str(result), "key_points": [], "decisions": []},
            "action_items": action_items_val if action_items_val else [],
            "speaker_summaries": speaker_summaries if speaker_summaries else {},
            # Phase 1: quality metadata from the refinement referee
            "quality_score": result.get("quality_score") if isinstance(result, dict) else None,
            "refinement_notes": result.get("refinement_notes") if isinstance(result, dict) else None,
            # Phase 2: rich task plan from the task decomposer agent
            "task_plan": result.get("task_plan", []) if isinstance(result, dict) else [],
            # Audit trail: draft → critique reports → refinement outcome
            "pipeline_trace": result.get("pipeline_trace") if isinstance(result, dict) else None,
            "metadata": {
                "language": language,
                "language_name": language_name,
                "participant_count": len(participants),
                "is_long_recording": is_long_recording,
                "timestamp": datetime.now().isoformat(),
                "speaker_confidence_metrics": speaker_confidence_metrics
            }
        }
        
        # Save the result
        save_job_result(job_id, final_result)
        update_job_status(job_id, JobStatus.COMPLETED, "Summarization complete", progress=100)
            
    except Exception as e:
        logger.error(f"Error in summarization: {str(e)}")
        update_job_status(job_id, JobStatus.FAILED, f"Error generating summary: {str(e)}")

# Helper function to parse transcript text into segment format
def parse_transcript_to_segments(transcript_text):
    """
    Parse plain text transcript into the segment format needed for long meeting summarization
    This is a simplified implementation - would need enhancement based on transcript format
    """
    lines = transcript_text.split('\n')
    segments = []
    current_time = 0
    
    for line in lines:
        if not line.strip():
            continue
            
        # Try to extract speaker and text
        parts = line.split(':', 1)
        if len(parts) == 2:
            speaker_part = parts[0].strip()
            text = parts[1].strip()
            
            # Check if there's a speaker number in the speaker part
            speaker_match = re.search(r'Speaker\s+(\d+)', speaker_part) if "Speaker" in speaker_part else None
            speaker = speaker_match.group(1) if speaker_match else "1"
            
            # Create segment
            segment = {
                'speaker': speaker,
                'text': text,
                'start_time': current_time,
                'end_time': current_time + 30,  # Estimate 30s per utterance
                'start_time_formatted': format_time(current_time),
                'end_time_formatted': format_time(current_time + 30)
            }
            segments.append(segment)
            current_time += 30
    
    return segments

# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Real-Time Audio Streaming Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/realtime-audio")
async def websocket_realtime_audio(websocket: WebSocket, language: Optional[str] = None):
    """
    WebSocket endpoint for real-time audio streaming, transcription, and diarization.
    Receives binary audio chunks (MediaRecorder stream) and pushes live JSON segment updates.
    """
    await websocket.accept()
    job_id = str(uuid.uuid4())
    logger.info(f"WebSocket real-time audio connection accepted for job {job_id}")

    processor = None
    try:
        from core.realtime_processor import WebSocketRealTimeProcessor
        processor = WebSocketRealTimeProcessor(language=language)

        update_job_status(job_id, JobStatus.PROCESSING, "Real-time streaming in progress", progress=50)

        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                chunk = message["bytes"]
                live_segments = processor.process_audio_chunk(chunk)
                await websocket.send_json({
                    "type": "live_update",
                    "job_id": job_id,
                    "segments": live_segments
                })
            elif "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                    if data.get("action") == "STOP":
                        break
                except Exception:
                    pass
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for job {job_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket real-time audio endpoint: {e}")
    finally:
        if processor:
            recordings_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            audio_path = os.path.join(recordings_dir, f"{job_id}.wav")
            processor.save_final_recording(audio_path)

            final_segments = processor.diarizer.get_live_segments()
            formatted_transcript = []
            raw_transcription = []
            for seg in final_segments:
                spk = seg.get("speaker", "Speaker 1")
                txt = seg.get("text", "")
                ts = seg.get("timestamp", "00:00")
                conf = seg.get("confidence", 85.0)

                formatted_transcript.append(f"[{ts}] {spk}: {txt}")
                raw_transcription.append({
                    "speaker": spk,
                    "text": txt,
                    "timestamp": ts,
                    "confidence": conf,
                    "confidence_level": "high" if conf >= 90 else ("medium" if conf >= 70 else "low"),
                    "words": seg.get("words", []),
                    "start_formatted": ts
                })

            job_result = {
                "job_id": job_id,
                "transcript": raw_transcription,
                "segments": final_segments,
                "formatted_transcript": formatted_transcript,
                "raw_transcription": raw_transcription,
                "language": language or "en",
                "recording_path": f"/recordings/{job_id}.wav"
            }
            save_job_result(job_id, job_result)
            update_job_status(job_id, JobStatus.COMPLETED, "Real-time processing complete", progress=100)

            try:
                await websocket.send_json({
                    "type": "final_result",
                    "job_id": job_id,
                    "result": job_result
                })
            except Exception:
                pass

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy", 
        "api_version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "timestamp": datetime.now().isoformat()
    }

# Main entry point
if __name__ == "__main__":
    import uvicorn
    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        logger.warning("⚠️ OpenAI API key not found! Set it with 'export OPENAI_API_KEY=your-key' before running")
    
    uvicorn.run(
        "main:app", 
        host=settings.HOST, 
        port=settings.PORT, 
        reload=True,
        workers=settings.WORKERS
    )