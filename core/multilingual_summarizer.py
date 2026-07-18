from lg import summarize_meeting as original_summarize_meeting, chunk_transcript_with_overlap
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from services.llm_service import get_llm, create_chat_prompt_template, create_output_parser
import json

def summarize_meeting_multilingual(transcript, participants, language=None, additional_context=None):
    """
    Creates meeting summaries in the specified language
    
    Args:
        transcript (str): Meeting transcript
        participants (list): List of participant names
        language (str, optional): Language code (e.g., 'hi') or language name
        additional_context (str, optional): Additional context about the meeting
        
    Returns:
        dict: Meeting summary and action items in the specified language
    """
    # If no specific language is provided, use the original function
    if not language or language.lower() == "en" or language.lower() == "english":
        return original_summarize_meeting(transcript, participants, additional_context=additional_context)
    
    # Get proper language name for instructions
    language_name = get_language_name(language)
    
    # Initialize the LLM with increased temperature for better multilingual generation
    llm = get_llm(temperature=0.2, purpose="multilingual")
    
    # Define sequential prompt
    system_message = f"""You are an expert meeting summarizer working with {language_name} content.
Your task is to create and sequentially refine a meeting summary and action items ENTIRELY IN {language_name}.

You will be given the GLOBAL SUMMARY generated from the previous chunks of the transcript (in {language_name}), and the NEXT CHUNK of the transcript (which is a continuation of the meeting).

Your task is to refine, update, and extend the GLOBAL SUMMARY using the new information in the next chunk.
Ensure that:
1. Continuation context: Connect related points, decisions, or action items where appropriate. The final output must read seamlessly as a single, cohesive meeting summary.
2. Integration:
   - Update/refine the summary paragraph, key_points, or decisions based on new discussion.
   - Add new key points, decisions, or action items.
3. Deduplication: Merge similar/duplicate key points, decisions, or action items.
4. Language check: ALL output text (summary, key points, decisions, actions) must be ENTIRELY in {language_name} only. DO NOT mix languages.

Your response must be a JSON object with this exact structure:
{{
  "summary": "overview paragraph in {language_name}",
  "key_points": ["point1 in {language_name}", "point2 in {language_name}"],
  "decisions": ["decision1 in {language_name}", "decision2 in {language_name}"],
  "action_items": [
    {{
      "action": "action in {language_name}",
      "assignee": "assignee in {language_name}",
      "due_date": "due date in {language_name}",
      "priority": "high/medium/low"
    }}
  ]
}}
"""

    context_section = ""
    if additional_context:
        context_section = f"""
        Additional context about this meeting: {additional_context}
        
        """

    user_template = """GLOBAL SUMMARY SO FAR:
{global_summary}

NEXT TRANSCRIPT CHUNK (Continuation):
{chunk}

Participants: {participants}
""" + context_section + f"\nPlease summarize this meeting chunk and update the global summary COMPLETELY in {language_name}."

    prompt_template = create_chat_prompt_template(system_message, user_template)
    json_parser = create_output_parser()
    chain = prompt_template | llm | json_parser

    try:
        chunks = chunk_transcript_with_overlap(transcript, chunk_size=4000, overlap_size=800)
        print(f"Long transcript detected ({len(transcript)} chars), breaking into {len(chunks)} chunks for multilingual processing")
        
        global_summary = {
            "summary": "",
            "key_points": [],
            "decisions": [],
            "action_items": []
        }
        
        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}/{len(chunks)}")
            
            if i == 0:
                global_summary_str = f"No summary generated yet. This is the first chunk."
            else:
                global_summary_str = json.dumps(global_summary, indent=2)
                
            summary_result = chain.invoke({
                "global_summary": global_summary_str,
                "chunk": chunk,
                "participants": ", ".join(participants),
                "language_name": language_name
            })
            
            global_summary = {
                "summary": summary_result.get("summary", ""),
                "key_points": summary_result.get("key_points", []),
                "decisions": summary_result.get("decisions", []),
                "action_items": summary_result.get("action_items", [])
            }
            
        result = {
            "meeting_summary": {
                "summary": global_summary["summary"],
                "key_points": global_summary["key_points"],
                "decisions": global_summary["decisions"]
            },
            "action_items": global_summary["action_items"]
        }
        
        return result
        
    except Exception as e:
        print(f"Error generating {language_name} summary: {str(e)}. Falling back to English.")
        return original_summarize_meeting(transcript, participants)
    
def chunk_transcript(transcript, max_chunk_size=15000):
    """
    Split a long transcript into manageable chunks to avoid context window limitations
    
    Args:
        transcript: The full transcript text
        max_chunk_size: Maximum size per chunk in characters
        
    Returns:
        List of transcript chunks
    """
    if len(transcript) <= max_chunk_size:
        return [transcript]
    
    # Try to split at paragraph boundaries
    paragraphs = transcript.split('\n\n')
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chunk_size:
            if current_chunk:
                current_chunk += '\n\n'
            current_chunk += para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            
            # If a single paragraph is too long, split it at sentence boundaries
            if len(para) > max_chunk_size:
                sentences = para.split('. ')
                current_chunk = ""
                
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 2 <= max_chunk_size:
                        if current_chunk:
                            current_chunk += '. '
                        current_chunk += sentence
                    else:
                        if current_chunk:
                            chunks.append(current_chunk + '.')
                        current_chunk = sentence
            else:
                current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def get_language_name(language_code):
    """
    Convert language code or name to a full language name
    
    Args:
        language_code (str): Language code (e.g., 'hi') or language name
        
    Returns:
        str: Full language name (e.g., 'Hindi')
    """
    language_map = {
        # Language codes
        "hi": "Hindi",
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "zh": "Chinese",
        "ja": "Japanese",
        "ru": "Russian",
        "ar": "Arabic",
        "pt": "Portuguese",
        "bn": "Bengali",
        "ur": "Urdu",
        "te": "Telugu",
        "ta": "Tamil",
        "mr": "Marathi",
        "gu": "Gujarati",
        "kn": "Kannada",
        "ml": "Malayalam",
        "pa": "Punjabi",
        
        # Full names (for when a language name is passed instead of code)
        "hindi": "Hindi",
        "english": "English",
        "spanish": "Spanish",
        "french": "French",
        "german": "German",
        "chinese": "Chinese",
        "japanese": "Japanese",
        "russian": "Russian",
        "arabic": "Arabic",
        "portuguese": "Portuguese",
        "bengali": "Bengali",
        "urdu": "Urdu",
        "telugu": "Telugu",
        "tamil": "Tamil",
        "marathi": "Marathi",
        "gujarati": "Gujarati",
        "kannada": "Kannada",
        "malayalam": "Malayalam",
        "punjabi": "Punjabi",
        
        # Handle auto-detect case without defaulting to Hindi
        "auto-detect": "Auto-detected",
        "auto-detected": "Auto-detected",
        "auto": "Auto-detected"
    }
    
    # If we get a code, return the language name; if we get a language name, return it
    try:
        # First, check if this is a specific language code/name we know
        if isinstance(language_code, str):
            code_lower = language_code.lower()
            if code_lower in language_map:
                return language_map[code_lower]
            
            # If it's one of the auto-detect values, log a warning only if it appears
            # we don't have a proper language detection
            if code_lower in ["auto-detect", "auto-detected", "auto"]:
                import logging
                logging.warning(f"Language was auto-detected but no specific language was identified. Defaulting to English.")
                return "Auto-detected (defaulting to English)"
                
            # For unknown codes, just return the code itself
            return language_code
        else:
            # For None or other non-string values, default to English
            return "English"
    except:
        # If language_code is None or any other type that causes errors
        return "English"  # Default to English as a safer default