import streamlit as st
import json
import traceback
import os
import io
import re
import tempfile
import time
from core.lg import summarize_meeting
from core.audio_processor import process_audio_file
from core.speaker_summarizer import generate_speaker_summaries
from core.long_recording_processor import process_long_audio
from core.summarize_long_transcripts import summarize_long_meeting
from core.realtime_processor import RealTimeTranscriber, RealTimeDiarizer
from services.follow_up_agent import (
    group_by_assignee,
    draft_all_emails,
    send_follow_up_emails,
    smtp_config_is_valid,
)
from services.contact_book import prefill_roster, bulk_save

# Check for OpenAI API key
#if not os.environ.get("OPENAI_API_KEY"):
 #   st.warning("⚠️ OpenAI API key not found! Set it with 'export OPENAI_API_KEY=your-key' before running this app.")

st.set_page_config(
    page_title="On-Premise Meeting Summarizer",
    page_icon="📝",
    layout="wide"
)

st.title("On-Premise Meeting Summarizer")
st.subheader("Convert your meeting recordings or transcripts into concise summaries and actionable tasks")

def extract_participants(transcript):
    """
    Extract participant names from the meeting transcript.
    Supports multiple languages by looking for patterns rather than specific words.

    Args:
        transcript (str): The meeting transcript

    Returns:
        list: Unique participant names
    """
    participants = set()

    # Pattern 1: Name (Role): Text - works for English and transliterated Hindi
    pattern1 = r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s*\([^)]+\):'
    matches1 = re.findall(pattern1, transcript)
    for name in matches1:
        participants.add(name.strip())

    # Pattern 2: Name: Text - works for English and transliterated Hindi
    pattern2 = r'(?:^|\n)([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s*:'
    matches2 = re.findall(pattern2, transcript)
    for name in matches2:
        participants.add(name.strip())

    # Pattern 3: Speaker X (from audio transcription) - language independent
    pattern3 = r'Speaker[\s_](\d+)'
    matches3 = re.findall(pattern3, transcript)
    for speaker_num in matches3:
        participants.add(f"Speaker {speaker_num}")

    # If we found participants, return them
    if participants:
        return sorted(list(participants))

    # If no participants found, try a more general approach for names
    # This is a fallback method that might catch more names but could include false positives.
    # We split by sentence boundaries (. ! ?) and newlines to find sentences/lines,
    # then for each sentence/line we skip the first word to avoid capitalization due to grammar.
    sentences = re.split(r'[.!?]|\n', transcript)
    potential_names = set()
    
    exclude_words = {
        # Original common words
        "I", "We", "The", "This", "They", "Monday", "Tuesday", "Wednesday", 
        "Thursday", "Friday", "Saturday", "Sunday", "January", "February", 
        "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December", "Hello", "Hi", "Thanks", "Yes",
        "No", "Ok", "Okay", "Perfect", "Great", "Good", "Today", "Tomorrow",
        # English pronouns, prepositions, conjunctions, and common sentence starters
        "Actually", "Basically", "Obviously", "Please", "Let", "Lets", "Why", "How", 
        "Who", "What", "Where", "When", "Which", "Whose", "Whatever", "Whoever", 
        "Yeah", "Not", "So", "But", "And", "Or", "For", "With", "Without", "About", 
        "Above", "Below", "After", "Before", "During", "Under", "Over", "Through", 
        "Between", "Among", "Against", "Into", "Onto", "Upon", "Out", "From", "To", 
        "By", "At", "In", "On", "Of", "He", "She", "It", "Them", "Their", "Theirs", 
        "Him", "Her", "Hers", "His", "Its", "Your", "Yours", "My", "Mine", "Our", 
        "Ours", "Us", "Me", "You", "Yourself", "Themselves", "Ourselves", "Myself", 
        "Himself", "Herself", "Itself", "Someone", "Somebody", "Something", "Anyone", 
        "Anybody", "Anything", "Everyone", "Everybody", "Everything", "Nothing", "None",
        # Common verbs, helping verbs, and modals
        "Am", "Is", "Are", "Was", "Were", "Be", "Been", "Being", "Have", "Has", "Had", 
        "Do", "Does", "Did", "Can", "Could", "Shall", "Should", "Will", "Would", "May", 
        "Might", "Must", "Get", "Got", "Go", "Went", "Make", "Made", "Take", "Took",
        # Adverbs, adjectives, and other fillers
        "Speaker", "Anyway", "Anyways", "Generally", "Specifically", "Normally", 
        "Usually", "Sometimes", "Always", "Never", "Often", "Seldom", "Rarely", 
        "Maybe", "Perhaps", "Probably", "Definitely", "Absolutely", "Certainly", 
        "Sure", "Surely", "Indeed", "Exactly", "Really", "Right", "Wrong", "True", 
        "False", "Alright", "Yep", "Naw", "Nope", "Design", "Earlier", "Every", 
        "Just", "Like", "Many", "Now", "Nowadays", "Oh", "One", "Recent", "Senior", 
        "Technically", "That", "Then", "There", "Two", "Using", "Whether", "Another",
        # Project/Tech stack specific terms
        "Langchain", "Langra", "Ollama", "Whisper", "Pyannote", "Fastapi", "Streamlit", 
        "Uvicorn", "Python", "Markdown", "Github", "Docker", "Api", "Llm", "App",
        "Karma"
    }

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Split sentence into words, keeping punctuation-free tokens
        words = re.findall(r'\b\w+\b', sentence)
        if len(words) <= 1:
            continue
        # Ignore the first word as it's capitalized for grammar
        candidate_words = words[1:]
        for word in candidate_words:
            # Match words starting with a capital letter followed by lowercase letters
            if re.match(r'^[A-Z][a-z]+$', word):
                if word not in exclude_words:
                    potential_names.add(word)

    # Only use this method if the others failed and we found potential names
    if not participants and potential_names:
        return sorted(list(potential_names))

    return sorted(list(participants))

# Initialize session state for transcript and file
if 'transcript_content' not in st.session_state:
    st.session_state.transcript_content = ""
if 'audio_transcript' not in st.session_state:
    st.session_state.audio_transcript = None
if 'audio_processing_complete' not in st.session_state:
    st.session_state.audio_processing_complete = False
if 'speaker_summaries' not in st.session_state:
    st.session_state.speaker_summaries = None
if 'current_tab' not in st.session_state:
    st.session_state.current_tab = "Meeting Summary"
if 'meeting_result' not in st.session_state:
    st.session_state.meeting_result = None
if 'detected_language' not in st.session_state:
    st.session_state.detected_language = None
if 'processing_progress' not in st.session_state:
    st.session_state.processing_progress = 0
if 'processing_status' not in st.session_state:
    st.session_state.processing_status = ""
if 'is_long_recording' not in st.session_state:
    st.session_state.is_long_recording = False
if 'realtime_transcriber' not in st.session_state:
    st.session_state.realtime_transcriber = None
if 'is_recording' not in st.session_state:
    st.session_state.is_recording = False
if 'recorded_audio_path' not in st.session_state:
    st.session_state.recorded_audio_path = None
if 'rt_trigger_process' not in st.session_state:
    st.session_state.rt_trigger_process = False
# Follow-up email state
if 'followup_drafts' not in st.session_state:
    st.session_state.followup_drafts = {}       # { assignee: email_body }
if 'followup_roster' not in st.session_state:
    st.session_state.followup_roster = {}       # { assignee: email_address }
if 'followup_send_results' not in st.session_state:
    st.session_state.followup_send_results = {} # { assignee: (success, msg) }

# Function to update processing progress
def update_progress(progress, status):
    st.session_state.processing_progress = progress
    st.session_state.processing_status = status

# ── Helper: color a single word by confidence ────────────────────────────────
def _word_color(conf):
    """Return (text_color, background_color) for a word confidence value."""
    if conf is None:
        return "#cccccc", "transparent"
    if conf >= 90:
        return "#4caf50", "rgba(76,175,80,0.12)"   # green
    if conf >= 70:
        return "#ff9800", "rgba(255,152,0,0.12)"    # orange
    return "#f44336", "rgba(244,67,54,0.15)"         # red

def _render_word_html(word_text, conf):
    """Render a single word as an HTML span with color + hover tooltip."""
    color, bg = _word_color(conf)
    if conf is not None:
        return (
            f"<span title='{conf:.1f}%' style='"
            f"color:{color}; background:{bg}; padding:1px 3px; "
            f"border-radius:3px; cursor:default;'>"
            f"{word_text}</span>"
        )
    return f"<span style='color:#ccc;'>{word_text}</span>"

# ── Color-coded transcript renderer ──────────────────────────────────────────
def render_color_coded_transcript():
    """
    Render the transcript with WORD-LEVEL color coding based on Whisper confidence.
    Each word is individually colored:
        🟢 Green  = High confidence (≥ 90%)
        🟡 Orange = Medium confidence (70–89%)
        🔴 Red    = Low confidence (< 70%)
    Hover over any word to see its exact confidence percentage.
    Uses data from st.session_state.audio_transcript.
    """
    audio_transcript = st.session_state.get("audio_transcript")
    if not audio_transcript or "transcript" not in audio_transcript:
        # Fallback: show plain text if no structured data
        plain = st.session_state.get("transcript_content", "")
        if plain:
            st.text_area("Transcript", value=plain, height=400, disabled=True, label_visibility="collapsed")
        else:
            st.info("No transcript data available.")
        return

    # Helper function to render a list of segments
    def _draw_segments_html(segment_list, is_raw=False):
        html_lines = []
        for seg in segment_list:
            if is_raw:
                ts = seg.get("start_formatted", "")
                prefix = ""
            else:
                ts = seg.get("start_time_formatted", "")
                speaker = seg.get("speaker", "?")
                prefix = f"<b style='color:#aaa;'>Speaker {speaker}:</b> "

            seg_conf = seg.get("confidence")

            # Try to get word-level data from nested segments
            words = []
            seg_details = seg.get("segments", [])
            if seg_details and isinstance(seg_details, list):
                for sub in seg_details:
                    if isinstance(sub, dict) and "words" in sub:
                        words.extend(sub["words"])
            
            # fallback for raw segments if 'words' is directly in the segment
            if not words and "words" in seg and isinstance(seg["words"], list):
                words = seg["words"]

            # Determine line-level dot indicator
            if seg_conf is not None:
                if seg_conf >= 90:
                    dot = "🟢"
                elif seg_conf >= 70:
                    dot = "🟡"
                else:
                    dot = "🔴"
                line_score = f"<span style='color:#888; font-size:11px;'>({seg_conf:.0f}%)</span>"
            else:
                dot = "⚫"
                line_score = ""

            # Build the text content — word-by-word if data exists, else line-level fallback
            if words:
                word_spans = []
                for w in words:
                    w_text = w.get("word", "")
                    w_conf = w.get("confidence")  # already 0-100 scale
                    word_spans.append(_render_word_html(w_text, w_conf))
                text_html = " ".join(word_spans)
            else:
                # Fallback: color entire text by line-level confidence
                text = seg.get("text", "")
                color, bg = _word_color(seg_conf)
                text_html = f"<span style='color:{color};'>{text}</span>"

            line_html = (
                f"<div style='padding:4px 0; border-bottom:1px solid #2a2a2a; line-height:1.7;'>"
                f"{dot} "
                f"<span style='color:#888; font-size:12px;'>[{ts}]</span> "
                f"{prefix}"
                f"{text_html} "
                f"{line_score}"
                f"</div>"
            )
            html_lines.append(line_html)

        # Wrap in a scrollable container
        return (
            "<div style='background:#121212; border-radius:8px; padding:12px; "
            "max-height:500px; overflow-y:auto; font-family:monospace; font-size:13px;'>"
            + "\n".join(html_lines)
            + "</div>"
        )

    # ── Confidence legend ─────────────────────────────────────────────────────
    st.markdown(
        "<div style='display:flex; gap:18px; margin-bottom:6px; font-size:13px;'>"
        "<span>🟢 <b>High</b> (≥90%)</span>"
        "<span>🟡 <b>Medium</b> (70–89%)</span>"
        "<span>🔴 <b>Low</b> (&lt;70%)</span>"
        "<span style='color:#888;'>⚫ <b>N/A</b></span>"
        "<span style='color:#666; font-style:italic;'>💡 Hover over any word to see its confidence</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Overall stats bar ─────────────────────────────────────────────────────
    confidence_metrics = audio_transcript.get("confidence_metrics", {})
    if confidence_metrics and "average" in confidence_metrics:
        avg = confidence_metrics["average"]
        lo = confidence_metrics.get("min", "–")
        hi = confidence_metrics.get("max", "–")
        low_pct = confidence_metrics.get("low_confidence_percentage", 0)
        bar_color = "#4caf50" if avg >= 90 else ("#ff9800" if avg >= 70 else "#f44336")
        st.markdown(
            f"<div style='background:#1e1e1e; border-radius:8px; padding:8px 14px; "
            f"margin-bottom:12px; font-size:13px; color:#ccc; display:flex; gap:24px; align-items:center;'>"
            f"<span>Avg: <b style='color:{bar_color}'>{avg}%</b></span>"
            f"<span>Min: <b>{lo}%</b></span>"
            f"<span>Max: <b>{hi}%</b></span>"
            f"<span>Low-confidence lines: <b>{low_pct}%</b></span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Check if we have raw transcription available
    raw_segments = audio_transcript.get("raw_transcription")
    if raw_segments:
        view_tab1, view_tab2 = st.tabs(["🔊 Speaker-Diarized Transcript", "📝 Raw Whisper Transcription"])
        with view_tab1:
            st.markdown(_draw_segments_html(audio_transcript["transcript"], is_raw=False), unsafe_allow_html=True)
        with view_tab2:
            st.markdown(_draw_segments_html(raw_segments, is_raw=True), unsafe_allow_html=True)
    else:
        st.markdown(_draw_segments_html(audio_transcript["transcript"], is_raw=False), unsafe_allow_html=True)

# Function to display meeting summary tab
def display_meeting_summary():
    result = st.session_state.meeting_result
    if not result:
        st.info("No meeting summary available yet.")
        return

    # Render Download buttons at the top in a nice row!
    st.write("### 📥 Export Reports")
    dl_col1, dl_col2, dl_col3 = st.columns(3)
    
    # 1. JSON Report
    with dl_col1:
        st.download_button(
            label="📄 Download JSON Summary",
            data=json.dumps({
                "meeting_summary": result.get("meeting_summary", {}),
                "action_items": result.get("action_items", []),
                "speaker_summaries": st.session_state.get("speaker_summaries", {}),
                "language": st.session_state.get("detected_language", "en"),
                "metadata": result.get("metadata", {})
            }, indent=2),
            file_name="meeting_summary.json",
            mime="application/json",
            use_container_width=True
        )
        
    # 2. Verbatim Transcript
    transcript_content = st.session_state.get("transcript_content", "")
    with dl_col2:
        st.download_button(
            label="📝 Download Transcript (TXT)",
            data=transcript_content,
            file_name="meeting_transcript.txt",
            mime="text/plain",
            disabled=not transcript_content,
            use_container_width=True
        )
        
    # 3. Full Meeting Report (TXT)
    try:
        summary_txt_parts = []
        summary_txt_parts.append("========================================")
        summary_txt_parts.append("           MEETING MINUTES REPORT       ")
        summary_txt_parts.append("========================================")
        summary_txt_parts.append(f"Language: {st.session_state.get('detected_language', 'en')}")
        
        summary_txt_parts.append("\n----------------------------------------")
        summary_txt_parts.append("1. MEETING SUMMARY")
        summary_txt_parts.append("----------------------------------------")
        if "meeting_summary" in result and "summary" in result["meeting_summary"]:
            summary_txt_parts.append(result["meeting_summary"]["summary"])
        else:
            summary_txt_parts.append("No summary available.")
        
        summary_txt_parts.append("\n----------------------------------------")
        summary_txt_parts.append("2. KEY POINTS")
        summary_txt_parts.append("----------------------------------------")
        if "meeting_summary" in result and "key_points" in result["meeting_summary"] and result["meeting_summary"]["key_points"]:
            for pt in result["meeting_summary"]["key_points"]:
                summary_txt_parts.append(f"- {pt}")
        else:
            summary_txt_parts.append("No key points available.")
        
        summary_txt_parts.append("\n----------------------------------------")
        summary_txt_parts.append("3. DECISIONS MADE")
        summary_txt_parts.append("----------------------------------------")
        if "meeting_summary" in result and "decisions" in result["meeting_summary"] and result["meeting_summary"]["decisions"]:
            for dec in result["meeting_summary"]["decisions"]:
                summary_txt_parts.append(f"- {dec}")
        else:
            summary_txt_parts.append("No decisions recorded.")
                
        summary_txt_parts.append("\n----------------------------------------")
        summary_txt_parts.append("4. ACTION ITEMS")
        summary_txt_parts.append("----------------------------------------")
        if "action_items" in result and result["action_items"]:
            for item in result["action_items"]:
                summary_txt_parts.append(f"📌 Action: {item.get('action')}")
                summary_txt_parts.append(f"   Assignee: {item.get('assignee', 'Unassigned')}")
                summary_txt_parts.append(f"   Due Date: {item.get('due_date', 'Not specified')}")
                summary_txt_parts.append(f"   Priority: {item.get('priority', 'medium').upper()}")
                summary_txt_parts.append("")
        else:
            summary_txt_parts.append("No action items assigned.")
                
        speaker_summaries = st.session_state.get("speaker_summaries")
        if speaker_summaries:
            summary_txt_parts.append("\n----------------------------------------")
            summary_txt_parts.append("5. SPEAKER SUMMARIES & CONTRIBUTIONS")
            summary_txt_parts.append("----------------------------------------")
            for spk, spk_sum in speaker_summaries.items():
                summary_txt_parts.append(f"👤 {spk}:")
                summary_txt_parts.append(f"   Brief: {spk_sum.get('brief_summary', '')}")
                if spk_sum.get("key_contributions"):
                    summary_txt_parts.append("   Key Contributions:")
                    for contr in spk_sum.get("key_contributions", []):
                        summary_txt_parts.append(f"     - {contr}")
                summary_txt_parts.append("")
                
        summary_txt_parts.append("\n----------------------------------------")
        summary_txt_parts.append("6. VERBATIM TRANSCRIPT")
        summary_txt_parts.append("----------------------------------------")
        summary_txt_parts.append(transcript_content)
        
        full_meeting_minutes_txt = "\n".join(summary_txt_parts)
    except Exception as e:
        full_meeting_minutes_txt = "Error compiling report."
        logger.error(f"Error compiling full report text: {e}")

    with dl_col3:
        st.download_button(
            label="📥 Download Full Report (TXT)",
            data=full_meeting_minutes_txt,
            file_name="meeting_report.txt",
            mime="text/plain",
            use_container_width=True
        )
        
    st.write("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Meeting Summary")
        if "meeting_summary" in result and "summary" in result["meeting_summary"]:
            st.write(result["meeting_summary"]["summary"])
        else:
            st.warning("Summary content is missing or malformed")

        st.subheader("Key Points")
        if "meeting_summary" in result and "key_points" in result["meeting_summary"]:
            for point in result["meeting_summary"]["key_points"]:
                st.markdown(f"- {point}")
        else:
            st.warning("Key points are missing or malformed")

        st.subheader("Decisions Made")
        if "meeting_summary" in result and "decisions" in result["meeting_summary"]:
            for decision in result["meeting_summary"]["decisions"]:
                st.markdown(f"- {decision}")
        else:
            st.warning("Decisions are missing or malformed")

        # Display metadata if it exists
        if "metadata" in result:
            with st.expander("Meeting Metadata", expanded=False):
                st.write(f"**Total Duration:** {result['metadata'].get('total_duration_minutes', 'Unknown')} minutes")
                st.write(f"**Language:** {result['metadata'].get('language', 'Unknown')}")
                if 'chunks_analyzed' in result['metadata']:
                    st.write(f"**Chunks Analyzed:** {result['metadata']['chunks_analyzed']}")

    with col2:
        st.subheader("Action Items")
        if "action_items" in result and result["action_items"]:
            for item in result["action_items"]:
                with st.expander(f"📌 {item.get('action', 'Unnamed Action')}"):
                    st.markdown(f"**Assignee:** {item.get('assignee', 'Unassigned')}")
                    st.markdown(f"**Due Date:** {item.get('due_date', 'Not specified')}")

                    priority = item.get('priority', 'medium').lower()
                    if priority == "high":
                        priority_color = "🔴 High"
                    elif priority == "medium":
                        priority_color = "🟠 Medium"
                    else:
                        priority_color = "🟢 Low"

                    st.markdown(f"**Priority:** {priority_color}")
        else:
            st.info("No action items were identified in this meeting.")

# Function to display speaker summaries tab
def display_speaker_summaries():
    speaker_summaries = st.session_state.speaker_summaries
    if not speaker_summaries:
        st.info("No speaker summaries available yet.")
        return

    st.subheader("Speaker Contributions")

    for speaker, summary in speaker_summaries.items():
        with st.expander(f"🗣️ {speaker}", expanded=False):
            st.markdown(f"**Summary:** {summary.get('brief_summary', 'No summary available')}")

            st.markdown("**Key Contributions:**")
            for contribution in summary.get('key_contributions', []):
                st.markdown(f"- {contribution}")

            if summary.get('action_items'):
                st.markdown("**Action Items:**")
                for item in summary.get('action_items', []):
                    st.markdown(f"- {item}")

            if summary.get('questions_raised'):
                st.markdown("**Questions Raised:**")
                for question in summary.get('questions_raised', []):
                    st.markdown(f"- {question}")

# Add tabs for different input methods
input_method = st.radio(
    "Choose input method:",
    ["Upload Audio", "Real-Time Audio", "Paste Text", "Upload Text"],
    horizontal=True
)

# Handle file upload outside the form
file_content = None

if input_method == "Upload Audio":
    st.info("Upload an audio recording of your meeting. The system will transcribe it and identify speakers automatically.")

    # Language selection
    language_options = {
        "Auto-detect": None,
        "English": "en",
        "Hindi": "hi",
        "Spanish": "es",
        "French": "fr",
        "German": "de",
        "Chinese": "zh",
        "Japanese": "ja",
        "Russian": "ru",
        "Arabic": "ar"
    }

    col1, col2 = st.columns(2)

    with col1:
        selected_language = st.selectbox(
            "Select Audio Language",
            options=list(language_options.keys()),
            index=0,
            help="Select the primary language of your audio. Auto-detect works well for many languages but explicit selection may improve accuracy."
        )

    with col2:
        # Option for long recordings
        is_long_recording = st.checkbox(
            "This is a long recording (>15 minutes)",
            value=st.session_state.is_long_recording,
            help="Enable special processing for longer recordings. Recommended for meetings over 15 minutes."
        )
        st.session_state.is_long_recording = is_long_recording

    language_code = language_options[selected_language]

    audio_file = st.file_uploader(
        "Upload Meeting Recording",
        type=["wav", "mp3", "m4a"],
        help="Upload an audio file of your meeting"
    )

    if audio_file is not None and not st.session_state.audio_processing_complete:
        st.info("Audio file detected. Click 'Process Audio' to transcribe and identify speakers.")

        if st.button("Process Audio"):
            # Initialize progress
            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.text("Starting audio processing...")

            # Reset processing progress
            st.session_state.processing_progress = 0
            st.session_state.processing_status = "Starting audio processing..."
            st.session_state.audio_processing_complete = False

            # Update the UI with progress
            def update_ui_progress():
                progress_bar.progress(st.session_state.processing_progress / 100)
                status_text.text(st.session_state.processing_status)

            try:
                # Save the uploaded file to a temporary location
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{audio_file.name.split('.')[-1]}") as tmp_file:
                    tmp_file.write(audio_file.getvalue())
                    audio_path = tmp_file.name

                update_ui_progress()

                if is_long_recording:
                    # Process long audio with chunking
                    transcript_data = process_long_audio(
                        audio_path,
                        language=language_code, 
                        progress_callback=update_progress
                    )
                else:
                    # Process regular audio
                    with st.spinner(f"Processing {selected_language if language_code else 'auto-detected'} audio..."):
                        transcript_data = process_audio_file(audio_path, language=language_code)
                        # Simulate progress for regular processing
                        for i in range(10):
                            update_progress(i * 10, f"Processing audio... {i * 10}%")
                            update_ui_progress()
                            time.sleep(0.2)  # Just for UI feedback

                # Store the detected language
                st.session_state.detected_language = transcript_data.get('language', 'auto-detected')

                # Format the transcript for display and processing
                formatted_transcript = []
                for segment in transcript_data["transcript"]:
                    formatted_transcript.append(f"[{segment['start_time_formatted']}] Speaker {segment['speaker']}: {segment['text']}")

                # Join the formatted transcript lines
                full_transcript = "\n".join(formatted_transcript)

                # Store in session state
                st.session_state.transcript_content = full_transcript
                st.session_state.audio_transcript = transcript_data
                st.session_state.audio_processing_complete = True

                # Clean up the temporary file
                os.unlink(audio_path)

                # Update progress to 100%
                update_progress(100, "Audio processing complete!")
                update_ui_progress()

                # Display success message with language info
                if st.session_state.detected_language:
                    st.success(f"Audio processing complete! Detected language: {st.session_state.detected_language}. The transcript is ready for summarization.")
                else:
                    st.success("Audio processing complete! The transcript is ready for summarization.")

            except Exception as e:
                st.error(f"Error processing audio: {str(e)}")
                st.error(traceback.format_exc())

            # Remove progress indicators after completion
            time.sleep(1)  # Give user time to see 100%
            progress_bar.empty()
            status_text.empty()

    # If audio has been processed, show a preview with color-coded confidence
    if st.session_state.audio_processing_complete:
        with st.expander("📊 Preview Transcript (Color-Coded Confidence)", expanded=False):
            render_color_coded_transcript()

elif input_method == "Real-Time Audio":
    st.info("Record audio directly from your microphone. The app will transcribe it in real-time.")
    
    # Language selection
    language_options = {
        "Auto-detect": None,
        "English": "en",
        "Hindi": "hi",
        "Spanish": "es",
        "French": "fr",
        "German": "de",
        "Chinese": "zh",
        "Japanese": "ja",
        "Russian": "ru",
        "Arabic": "ar"
    }
    
    col1, col2 = st.columns(2)
    
    with col1:
        selected_language = st.selectbox(
            "Select Audio Language",
            options=list(language_options.keys()),
            index=0,
            key="rt_lang_select",
            help="Select the primary language of your audio."
        )
    
    with col2:
        is_long_recording = st.checkbox(
            "This will be a long recording (>15 minutes)",
            value=st.session_state.is_long_recording,
            key="rt_long_rec",
            help="Enable special processing for longer recordings."
        )
        st.session_state.is_long_recording = is_long_recording
    
    language_code = language_options[selected_language]
    
    st.write("### Live Recording Controls")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        start_btn = st.button("🎙️ Start Listening", disabled=st.session_state.is_recording, use_container_width=True)
    with col_btn2:
        stop_btn = st.button("⏹️ Stop & Summarize", disabled=not st.session_state.is_recording, use_container_width=True)
        
    if start_btn and not st.session_state.is_recording:
        st.session_state.is_recording = True
        st.session_state.audio_processing_complete = False
        st.session_state.rt_trigger_process = False
        st.session_state.recorded_audio_path = None
        st.session_state.diarizer_error = None
        
        # Start diarizer first (gracefully fallback on error)
        diarizer = None
        try:
            diarizer = RealTimeDiarizer()
            with st.spinner("Loading speaker diarization models (first time only)…"):
                diarizer.load_models()
            diarizer.start()
            st.session_state.realtime_diarizer = diarizer
        except Exception as e:
            st.session_state.diarizer_error = str(e)
            st.session_state.realtime_diarizer = None

        # Start transcriber and link to diarizer if available
        try:
            transcriber = RealTimeTranscriber()
            if diarizer:
                transcriber.diarizer = diarizer
            transcriber.start()
            st.session_state.realtime_transcriber = transcriber
            st.rerun()
        except Exception as e:
            st.error(f"Failed to start recording: {e}")
            if diarizer:
                try:
                    diarizer.stop()
                except Exception:
                    pass
            st.session_state.realtime_diarizer = None
            st.session_state.realtime_transcriber = None
            st.session_state.is_recording = False
            st.rerun()
            
    if stop_btn and st.session_state.is_recording:
        st.session_state.is_recording = False
        
        live_segments = []
        diarizer = st.session_state.realtime_diarizer
        transcriber = st.session_state.realtime_transcriber
        
        # 1. Extract live segments from diarizer if active
        if diarizer and diarizer.is_running:
            segments = diarizer.get_live_segments()
            if segments:
                for seg in segments:
                    import re
                    spk_match = re.search(r'Speaker\s+(\d+)', seg['speaker'])
                    spk_num = spk_match.group(1) if spk_match else seg['speaker']
                    
                    # Compute confidence level
                    conf = seg.get("confidence")
                    conf_lvl = None
                    if conf is not None:
                        conf_lvl = "high" if conf >= 90 else ("medium" if conf >= 70 else "low")
                        
                    live_segments.append({
                        "speaker": spk_num,
                        "text": seg['text'],
                        "start_time_formatted": seg['timestamp'],
                        "end_time_formatted": seg['timestamp'],
                        "confidence": conf,
                        "confidence_level": conf_lvl,
                        "segments": [{
                            "text": seg['text'],
                            "start": 0,
                            "end": 0,
                            "confidence": conf,
                            "confidence_level": conf_lvl,
                            "words": seg.get("words", [])
                        }]
                    })
                    
        # 2. Fallback to raw transcriber text if no segments
        if not live_segments and transcriber:
            raw_text = transcriber.get_transcript()
            if raw_text:
                live_segments.append({
                    "speaker": "1",
                    "text": raw_text,
                    "start_time_formatted": "00:00",
                    "end_time_formatted": "00:00",
                    "confidence": 85.0,
                    "confidence_level": "medium",
                    "segments": [{
                        "text": raw_text,
                        "start": 0,
                        "end": 0,
                        "confidence": 85.0,
                        "confidence_level": "medium",
                        "words": []
                    }]
                })
                
        # 3. Save live transcript text & metadata to session state
        if live_segments:
            # Build raw segments lists
            raw_transcription = getattr(transcriber, "raw_segments", [])
            
            # Compute confidence metrics
            confidences = [seg.get("confidence") for seg in live_segments if seg.get("confidence") is not None]
            confidence_metrics = {}
            if confidences:
                avg_conf = sum(confidences) / len(confidences)
                low_conf_segs = [c for c in confidences if c < 70]
                confidence_metrics = {
                    "average": round(avg_conf, 2),
                    "min": round(min(confidences), 2),
                    "max": round(max(confidences), 2),
                    "low_confidence_count": len(low_conf_segs),
                    "low_confidence_percentage": round(100 * len(low_conf_segs) / len(confidences), 2)
                }
                
            st.session_state.audio_transcript = {
                "transcript": live_segments,
                "raw_transcription": raw_transcription,
                "language": "en",  # Default to english for live mode
                "confidence_metrics": confidence_metrics
            }
            formatted_transcript = []
            for seg in live_segments:
                formatted_transcript.append(f"[{seg['start_time_formatted']}] Speaker {seg['speaker']}: {seg['text']}")
            st.session_state.transcript_content = "\n".join(formatted_transcript)
            st.session_state.audio_processing_complete = True
            
        # 4. Stop objects and save backup audio file
        if transcriber:
            transcriber.stop()
            recordings_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            rt_audio_path = os.path.join(recordings_dir, f"rt_recording_{int(time.time())}.wav")
            if transcriber.save_full_audio(rt_audio_path):
                st.session_state.recorded_audio_path = rt_audio_path
            st.session_state.realtime_transcriber = None
            
        if diarizer:
            diarizer.stop()
            st.session_state.realtime_diarizer = None
            
        st.session_state.rt_trigger_process = False  # Disable auto-trigger offline processing
        st.rerun()

    # Show diarizer error banner if models failed to load
    if st.session_state.get("diarizer_error"):
        st.warning(
            f"⚠️ Speaker diarization could not start: {st.session_state.diarizer_error}. "
            "Falling back to transcription-only mode."
        )

    # The Live Transcript view
    st.write("### Live Transcript")
    
    @st.fragment(run_every=2)
    def live_transcript_view():
        diarizer: RealTimeDiarizer | None = st.session_state.get("realtime_diarizer")
        transcriber: RealTimeTranscriber | None = st.session_state.get("realtime_transcriber")
        is_rec = st.session_state.is_recording

        if is_rec and (diarizer or transcriber):
            # ── Always show raw Whisper text first ────────────────────────────
            if transcriber:
                raw_text = transcriber.get_transcript()
                if raw_text:
                    st.text_area(
                        "🎙️ Live Transcription (Whisper)",
                        value=raw_text,
                        height=150,
                        disabled=True,
                        key="rt_raw_transcript",
                    )
                else:
                    st.info("🎙️ Listening… Speak into the microphone.")

            # ── Speaker-diarized view (appears once diarizer has segments) ───
            if diarizer and diarizer.is_running:
                segments = diarizer.get_live_segments()
                if segments:
                    st.write("**🔊 Speaker Labels**")
                    color_map = {
                        "🔵": "#4ea1f3", "🟠": "#f5a623", "🟢": "#5cb85c",
                        "🔴": "#d9534f", "🟣": "#9b59b6", "🟡": "#f0e040",
                        "⚪": "#cccccc", "🟤": "#a0522d",
                    }
                    html_parts = [
                        "<div style='font-family:monospace; font-size:14px; "
                        "background:#1e1e1e; color:#ddd; padding:12px; "
                        "border-radius:8px; max-height:280px; overflow-y:auto;'>"
                    ]
                    for seg in segments:
                        c = color_map.get(seg["color"], "#ddd")
                        txt = seg["text"] if seg["text"] else "<i style='color:#888'>(speaking…)</i>"
                        html_parts.append(
                            f"<p style='margin:4px 0;'>"
                            f"<span style='color:{c}; font-weight:bold;'>{seg['color']} {seg['speaker']}</span> "
                            f"<span style='color:#888; font-size:12px;'>[{seg['timestamp']}]</span> {txt}"
                            f"</p>"
                        )
                    html_parts.append("</div>")
                    st.markdown("".join(html_parts), unsafe_allow_html=True)
                    n_spk = len(diarizer._speaker_profiles)
                    st.caption(f"Detected {n_spk} unique speaker(s) so far.")
                else:
                    st.caption("⏳ Speaker labels will appear after ~5 seconds of speech.")

        elif st.session_state.get("recorded_audio_path"):
            st.success("✅ Recording stopped. Audio saved successfully.")
        else:
            st.info("Click '🎙️ Start Listening' to begin.")
            
    live_transcript_view()
    
    # Process the recorded audio if triggered
    if st.session_state.get("rt_trigger_process") and st.session_state.get("recorded_audio_path"):
        st.info("Audio recorded. Proceed below to generate summary.")
        
        if st.button("Process Recorded Audio", type="primary", use_container_width=True):
            # Initialize progress
            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.text("Starting audio processing...")
            
            # Reset processing progress
            st.session_state.processing_progress = 0
            st.session_state.processing_status = "Starting audio processing..."
            st.session_state.audio_processing_complete = False
            
            # Update the UI with progress
            def update_ui_progress():
                progress_bar.progress(st.session_state.processing_progress / 100)
                status_text.text(st.session_state.processing_status)
            
            try:
                audio_path = st.session_state.recorded_audio_path
                update_ui_progress()
                
                if st.session_state.is_long_recording:
                    # Process long audio with chunking
                    transcript_data = process_long_audio(
                        audio_path, 
                        language=language_code, 
                        progress_callback=update_progress
                    )
                else:
                    # Process regular audio
                    with st.spinner(f"Processing {selected_language if language_code else 'auto-detected'} audio..."):
                        transcript_data = process_audio_file(audio_path, language=language_code)
                        # Simulate progress for regular processing
                        for i in range(10):
                            update_progress(i * 10, f"Processing audio... {i * 10}%")
                            update_ui_progress()
                            time.sleep(0.2)
                
                # Store the detected language
                st.session_state.detected_language = transcript_data.get('language', 'auto-detected')
                
                # Format the transcript for display and processing
                formatted_transcript = []
                for segment in transcript_data["transcript"]:
                    formatted_transcript.append(f"[{segment['start_time_formatted']}] Speaker {segment['speaker']}: {segment['text']}")
                
                # Join the formatted transcript lines
                full_transcript = "\n".join(formatted_transcript)
                
                # Store in session state
                st.session_state.transcript_content = full_transcript
                st.session_state.audio_transcript = transcript_data
                st.session_state.audio_processing_complete = True
                
                # Update progress to 100%
                update_progress(100, "Audio processing complete!")
                update_ui_progress()
                
                if st.session_state.detected_language:
                    st.success(f"Audio processing complete! Detected language: {st.session_state.detected_language}. The transcript is ready for summarization.")
                else:
                    st.success("Audio processing complete! The transcript is ready for summarization.")
                    
            except Exception as e:
                st.error(f"Error processing audio: {str(e)}")
                st.error(traceback.format_exc())
                
            # Remove progress indicators after completion
            time.sleep(1)
            progress_bar.empty()
            status_text.empty()
    
    # If audio has been processed, show a preview with color-coded confidence
    if st.session_state.audio_processing_complete:
        with st.expander("📊 Preview Final Transcript (Color-Coded Confidence)", expanded=False):
            render_color_coded_transcript()

elif input_method == "Upload Text":
    text_file = st.file_uploader(
        "Upload Meeting Transcript",
        type=["txt"],
        help="Upload a text file containing your meeting transcript"
    )

    if text_file is not None:
        file_content = text_file.getvalue().decode("utf-8")
        st.session_state.transcript_content = file_content

        # Preview of uploaded file
        with st.expander("Preview Uploaded Transcript", expanded=False):
            st.text_area(
                "Transcript",
                value=file_content,
                height=400,
                disabled=True,
                label_visibility="collapsed"
            )

        # Detect participants from file
        detected_participants = extract_participants(file_content)
        if detected_participants:
            st.success(f"✅ Detected {len(detected_participants)} participants: {', '.join(detected_participants)}")

with st.form("meeting_form"):
    # Show different input methods based on selection
    transcript = ""
    if input_method == "Paste Text":
        transcript = st.text_area(
            "Meeting Transcript",
            height=300,
            placeholder="Paste your meeting transcript here..."
        )
    elif input_method == "Upload Text":
        if file_content:
            st.success(f"Transcript uploaded! ({len(file_content)} characters)")
        else:
            st.info("Please upload a transcript file above")
    elif input_method in ["Upload Audio", "Real-Time Audio"]:
        if st.session_state.audio_processing_complete:
            st.success(f"Audio processed successfully! {'Language: ' + st.session_state.detected_language if st.session_state.detected_language else ''}")
        else:
            st.info("Please process an audio file above")

    # Determine default participants
    default_participants = ""
    if input_method == "Upload Text" and file_content:
        default_participants = ", ".join(extract_participants(file_content))
    elif input_method in ["Upload Audio", "Real-Time Audio"] and st.session_state.audio_processing_complete:
        speakers = set()
        for segment in st.session_state.audio_transcript["transcript"]:
            speakers.add(f"Speaker {segment['speaker']}")
        default_participants = ", ".join(sorted(list(speakers)))

    # Participants input field
    participants_input = st.text_input(
        "Participants (comma-separated)",
        value=default_participants,
        placeholder="Alice, Bob, Charlie, Dave, Eva",
        help="Participants are automatically detected. You can edit this list if needed."
    )
    # Prior Information / Context
    context_file = st.file_uploader(
        "Upload Prior Context File (Optional)",
        type=["txt"],
        help="Upload a text file containing prior context for the meeting."
    )
    
    uploaded_context = ""
    if context_file:
        uploaded_context = context_file.getvalue().decode("utf-8")
        st.success("Context file uploaded successfully!")
        
    meeting_context = st.text_area(
        "Prior Information / Meeting Context (Optional)",
        value=uploaded_context,
        placeholder="e.g., This is a weekly sync for the engineering team. Pay special attention to any database migration tasks.",
        help="Give the AI a 'heads up' about what the meeting is about before it reads the transcript."
    )
    
    submit_button = st.form_submit_button("Generate Summary & Action Items")

# Process the transcript
if submit_button:
    process_transcript = False
    final_transcript = ""
    participants = []

    # Get the transcript based on input method
    if input_method == "Paste Text" and transcript:
        process_transcript = True
        final_transcript = transcript

        # Auto-detect participants from pasted text if not provided
        if not participants_input:
            detected_participants = extract_participants(transcript)
            if detected_participants:
                participants = detected_participants
                st.success(f"✅ Automatically detected participants: {', '.join(participants)}")
            else:
                st.warning("Could not detect participants. Please enter them manually.")
                process_transcript = False
        else:
            participants = [p.strip() for p in participants_input.split(",")]

    elif input_method == "Upload Text" and file_content:
        process_transcript = True
        final_transcript = file_content

        # Use provided participants or auto-detect from file
        if participants_input:
            participants = [p.strip() for p in participants_input.split(",")]
        else:
            detected_participants = extract_participants(file_content)
            if detected_participants:
                participants = detected_participants
                st.success(f"✅ Using detected participants: {', '.join(participants)}")
            else:
                st.warning("Could not detect participants. Please enter them manually.")
                process_transcript = False
    elif input_method in ["Upload Audio", "Real-Time Audio"] and st.session_state.audio_processing_complete:
    
        process_transcript = True
        final_transcript = st.session_state.transcript_content

        # Use provided participants or the detected speakers
        if participants_input:
            participants = [p.strip() for p in participants_input.split(",")]
        else:
            speakers = set()
            for segment in st.session_state.audio_transcript["transcript"]:
                speakers.add(f"Speaker {segment['speaker']}")
            participants = sorted(list(speakers))
            st.success(f"✅ Using detected speakers: {', '.join(participants)}")
    else:
        st.warning("Please provide a meeting transcript (paste text, upload a file, or process audio).")

    # Process if we have both transcript and participants
    if process_transcript and final_transcript and participants:
        # Set up progress tracking for summarization
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Starting summarization...")

        # Reset processing progress
        st.session_state.processing_progress = 0
        st.session_state.processing_status = "Starting summarization..."

        # Update the UI with progress
        def update_ui_progress():
            progress_bar.progress(st.session_state.processing_progress / 100)
            status_text.text(st.session_state.processing_status)

        try:
            # For long recordings, use the hierarchical summarization
            if st.session_state.is_long_recording and input_method in ["Upload Audio", "Real-Time Audio"]:
                update_status = lambda p, s: update_progress(p, s)

                # Call the long meeting summarizer with transcript data
                result = summarize_long_meeting(
                    st.session_state.audio_transcript["transcript"],
                    language=st.session_state.detected_language,
                    progress_callback=update_status,
                    context=meeting_context
                )

                # Update UI after each step
                update_ui_progress()
            else:
                # For regular recordings, use the standard summarizer
                # Call the meeting summarizer with language information
                if input_method in ["Upload Audio", "Real-Time Audio"] and st.session_state.detected_language:
                    # Simulate progress updates for standard processing
                    for i in range(5):
                        update_progress(i * 20, f"Summarizing... {i * 20}%")
                        update_ui_progress()
                        time.sleep(0.3)  # Just for UI feedback
                    result = summarize_meeting(
                        final_transcript, 
                        participants, 
                        language=st.session_state.detected_language,
                        context=meeting_context
                    )
                else:
                    # Simulate progress updates for standard processing
                    for i in range(5):
                        update_progress(i * 20, f"Summarizing... {i * 20}%")
                        update_ui_progress()
                        time.sleep(0.3)  # Just for UI feedback
                    result = summarize_meeting(
                        final_transcript, 
                        participants,
                        context=meeting_context
                    )
            st.session_state.meeting_result = result

            # Update progress to 100%
            update_progress(100, "Summary generated successfully!")
            update_ui_progress()

            # Display success message
            st.success("✅ Summary generated successfully!")

            # Generate speaker summaries
            with st.spinner("Generating speaker-specific summaries..."):
                try:
                    # Generate speaker summaries with language support
                    if input_method in ["Upload Audio", "Real-Time Audio"] and st.session_state.detected_language:
                        speaker_summaries = generate_speaker_summaries(
                            final_transcript,
                            participants,
                            language=st.session_state.detected_language
                        )
                    else:
                        speaker_summaries = generate_speaker_summaries(final_transcript, participants)

                    st.session_state.speaker_summaries = speaker_summaries
                except Exception as e:
                    st.error(f"Error generating speaker summaries: {str(e)}")

            # Add download buttons for JSON export and transcript
            # Reset to default tab
            st.session_state.current_tab = "Meeting Summary"

        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            st.expander("See detailed error trace").write(traceback.format_exc())
            st.info("💡 Tips to fix this error: Check that your OpenAI API key is valid and has sufficient credits. Make sure your meeting transcript is properly formatted with speaker names.")

        # Remove progress indicators after completion
        time.sleep(1)  # Give user time to see 100%
        progress_bar.empty()
        status_text.empty()

    elif submit_button and (not final_transcript or not participants):
        st.warning("Both transcript and participants are required to generate a summary.")

# If we have results to display, show the tabs and content
if st.session_state.meeting_result:
    # Create radio buttons for tab selection instead of tabs component
    tab_options = ["Meeting Summary", "Speaker Summaries"]
    selected_tab = st.radio("View", tab_options, index=tab_options.index(st.session_state.current_tab))
    st.session_state.current_tab = selected_tab

    # Display the selected tab content
    if selected_tab == "Meeting Summary":
        display_meeting_summary()
    else:  # Speaker Summaries
        display_speaker_summaries()


# ─────────────────────────────────────────────────────────────
# Follow-up Email Panel
# ─────────────────────────────────────────────────────────────
if st.session_state.meeting_result:
    result = st.session_state.meeting_result
    action_items = result.get("action_items", [])
    meeting_summary = result.get("meeting_summary", {})

    # Only show panel if there are assigned action items
    assignee_groups = group_by_assignee(action_items)
    if assignee_groups:
        st.write("---")
        st.subheader("📧 Send Follow-up Emails")
        st.caption(
            "One personalised email per assignee — listing their specific action items "
            "with meeting context. Preview and edit before sending."
        )

        # ── SMTP status banner ────────────────────────────────────────
        smtp_ok, smtp_reason = smtp_config_is_valid()
        if not smtp_ok:
            st.warning(
                f"⚠️ SMTP not configured: {smtp_reason}  \n"
                "Fill in `SMTP_USER`, `SMTP_PASSWORD` (and optionally `SMTP_HOST`) "
                "in your `.env.dev` file, then restart the app."
            )

        # ── Step 1: Roster — collect email addresses ──────────────────
        st.markdown("**Step 1 — Enter email addresses for each assignee**")
        st.caption("Known contacts are auto-filled. Changes are remembered for future meetings.")

        # Pre-fill from contact book (runs once or when result changes)
        if not st.session_state.followup_roster or set(st.session_state.followup_roster.keys()) != set(assignee_groups.keys()):
            st.session_state.followup_roster = prefill_roster(list(assignee_groups.keys()))

        updated_roster: dict = {}
        for assignee in sorted(assignee_groups.keys()):
            task_count = len(assignee_groups[assignee])
            col_name, col_email = st.columns([2, 3])
            with col_name:
                st.markdown(f"**{assignee}** &nbsp; `{task_count} task{'s' if task_count > 1 else ''}`")
            with col_email:
                stored_email = st.session_state.followup_roster.get(assignee, "")
                entered_email = st.text_input(
                    label=f"Email for {assignee}",
                    value=stored_email,
                    placeholder="name@company.com",
                    key=f"email_input_{assignee}",
                    label_visibility="collapsed",
                )
                updated_roster[assignee] = entered_email

        # Propagate: if multiple assignees share the first name, auto-fill
        # (handles "Priya" appearing in two rows — user only types once)
        first_name_to_email: dict = {}
        for name, email in updated_roster.items():
            if email:
                first_name_to_email[name.split()[0].lower()] = email
        for name in list(updated_roster.keys()):
            if not updated_roster[name]:
                first = name.split()[0].lower()
                if first in first_name_to_email:
                    updated_roster[name] = first_name_to_email[first]

        st.session_state.followup_roster = updated_roster

        # Sender display name
        sender_name = st.text_input(
            "Your name (shown in emails as the sender)",
            value=os.getenv("SMTP_FROM_NAME", "Meeting Organiser"),
            key="followup_sender_name",
        )

        st.write("")

        # ── Step 2: Generate drafts ───────────────────────────────────
        st.markdown("**Step 2 — Generate personalised email drafts**")
        col_gen, col_clear = st.columns([2, 1])
        with col_gen:
            gen_btn = st.button(
                "✍️ Generate Email Drafts",
                key="gen_drafts_btn",
                use_container_width=True,
                type="primary",
            )
        with col_clear:
            clear_btn = st.button(
                "🗑 Clear Drafts",
                key="clear_drafts_btn",
                use_container_width=True,
            )

        if clear_btn:
            st.session_state.followup_drafts = {}
            st.session_state.followup_send_results = {}
            st.rerun()

        if gen_btn:
            with st.spinner("Drafting emails with AI… this takes a few seconds."):
                try:
                    drafts = draft_all_emails(
                        action_items,
                        meeting_summary,
                        sender_name=sender_name,
                    )
                    st.session_state.followup_drafts = drafts
                    st.session_state.followup_send_results = {}
                    st.success(f"✅ Drafted {len(drafts)} email(s)")
                except Exception as e:
                    st.error(f"Error generating drafts: {e}")

        # ── Step 3: Preview & send ────────────────────────────────────
        if st.session_state.followup_drafts:
            st.write("")
            st.markdown("**Step 3 — Preview, edit, and send**")

            send_results = st.session_state.followup_send_results

            for assignee, body in st.session_state.followup_drafts.items():
                email_addr = st.session_state.followup_roster.get(assignee, "")
                task_count = len(assignee_groups.get(assignee, []))

                # Status badge
                if assignee in send_results:
                    ok, msg = send_results[assignee]
                    badge = "✅ Sent" if ok else "❌ Failed"
                else:
                    badge = "📝 Draft"

                label = f"{badge} — **{assignee}** ({task_count} task{'s' if task_count > 1 else ''})  `{email_addr or 'no email'}`"
                with st.expander(label, expanded=(assignee not in send_results)):
                    # Editable body
                    edited_body = st.text_area(
                        "Email body (edit before sending)",
                        value=body,
                        height=320,
                        key=f"email_body_{assignee}",
                    )
                    # Update draft in place
                    st.session_state.followup_drafts[assignee] = edited_body

                    send_col, skip_col = st.columns([2, 1])
                    with send_col:
                        if st.button(
                            f"📤 Send to {email_addr or 'N/A'}",
                            key=f"send_btn_{assignee}",
                            disabled=(not smtp_ok or not email_addr or "@" not in (email_addr or "")),
                            use_container_width=True,
                        ):
                            with st.spinner(f"Sending to {email_addr}…"):
                                from services.follow_up_agent import send_email
                                success, msg = send_email(
                                    to_address=email_addr,
                                    subject="Action Items from Our Recent Meeting",
                                    body=edited_body,
                                )
                            # Save email to contact book on successful send
                            if success:
                                bulk_save({assignee: email_addr})
                            st.session_state.followup_send_results[assignee] = (success, msg)
                            st.rerun()

                    with skip_col:
                        if assignee in send_results:
                            ok, msg = send_results[assignee]
                            if ok:
                                st.success("Sent ✓")
                            else:
                                st.error(msg)

            # ── Send all at once ──────────────────────────────────────
            st.write("")
            all_have_emails = all(
                st.session_state.followup_roster.get(a, "") and
                "@" in st.session_state.followup_roster.get(a, "")
                for a in st.session_state.followup_drafts
            )
            if st.button(
                "📤 Send All Emails",
                key="send_all_btn",
                disabled=(not smtp_ok or not all_have_emails),
                type="primary",
                use_container_width=False,
            ):
                with st.spinner("Sending all emails…"):
                    results = send_follow_up_emails(
                        roster=st.session_state.followup_roster,
                        drafts=st.session_state.followup_drafts,
                        meeting_title="Our Recent Meeting",
                    )
                    # Save successful contacts to book
                    for a, (ok, _) in results.items():
                        if ok:
                            bulk_save({a: st.session_state.followup_roster[a]})
                    st.session_state.followup_send_results = results
                st.rerun()


# Add sidebar with tips
with st.sidebar:
    st.header("Tips for Best Results")
    st.markdown("""
    - When using audio, ensure clear recording with minimal background noise
    - For Hindi or other non-English audio, select the language for better accuracy
    - For text transcripts, include speaker names (e.g., "Alice: Hello everyone")
    - The app will automatically detect participants from the transcript or audio
    - For more accurate action items, make sure assignments and deadlines are clearly stated
    - For longer meetings (>15 minutes), check the "This is a long recording" option
    """)

    # Add information about long recordings
    st.header("Processing Long Recordings")
    st.markdown("""
    For meetings longer than 15 minutes, we recommend:

    1. Checking the "This is a long recording" option
    2. Being patient during processing (it may take several minutes)
    3. Ensuring your computer doesn't go to sleep during processing

    Long recordings are processed in chunks to handle meetings of any duration.
    """)

    # Add information about file uploads and participant detection
    st.header("Supported File Types")
    st.markdown("""
    - Audio: WAV, MP3, M4A
    - Text: TXT
    """)

    st.header("Supported Languages")
    st.markdown("""
    Audio transcription supports multiple languages including:
    - English
    - Hindi
    - Spanish
    - French
    - German
    - Chinese
    - And many more...

    For best results with non-English audio, select the specific language rather than using auto-detect.
    """)

    st.header("Automatic Participant Detection")
    st.markdown("""
    The app recognizes participants based on these patterns:
    - Name (Role): Text
    - Name: Text at the beginning of lines
    - Speaker labels from audio processing

    You can always review and edit the detected participants if needed.
    """)

    st.header("About")
    st.markdown("""
    This tool uses LangGraph, LLMs, and audio processing to:

    1. Transcribe meeting recordings with speaker identification
    2. Generate a concise meeting summary
    3. Extract key points discussed
    4. Identify decisions made
    5. Compile action items with assignees and deadlines
    6. Create per-speaker contribution summaries

    The tool helps teams track action items and ensure accountability.
    """)