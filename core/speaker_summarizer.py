from services.llm_service import get_llm, create_chat_prompt_template, create_output_parser, get_ollama_llm
import logging
import json
import re
from config import settings

def generate_speaker_summaries(transcript, participants, language=None):
    """
    Generate individual summaries for each speaker in the meeting.
    
    Args:
        transcript (str): The full meeting transcript
        participants (list): List of participant names/identifiers
        language (str, optional): Language code (e.g., 'hi' for Hindi) to generate summaries in
        
    Returns:
        dict: Dictionary mapping each speaker to their summary
    """
    # Initialize the LLM (single init)
    llm = get_llm(temperature=0, purpose="summarization")
    
    # Normalize participants list
    norm_participants = [str(p).strip() for p in participants if p and str(p).strip()]
    if not norm_participants:
        norm_participants = ["Speaker 1"]

    speaker_contributions = {p: [] for p in norm_participants}
    
    # Process the transcript to group text by speaker using robust regex
    for line in transcript.split('\n'):
        line_str = line.strip()
        if not line_str:
            continue
            
        # Match pattern like: "[00:05] Speaker 1: Hello" or "Pranav: Hello" or "Speaker 1 (00:05): Hello"
        match = re.search(r'^(?:\[.*?\]\s*)?([^:\(\)]+?)(?:\s*\(.*?\))?\s*:\s*(.*)$', line_str)
        if match:
            spk_raw = match.group(1).strip()
            content = match.group(2).strip()
            
            matched_spk = None
            for p in norm_participants:
                if spk_raw.lower() == p.lower() or p.lower() in spk_raw.lower() or spk_raw.lower() in p.lower():
                    matched_spk = p
                    break
            
            if not matched_spk:
                matched_spk = spk_raw
                if matched_spk not in norm_participants:
                    norm_participants.append(matched_spk)

            if matched_spk not in speaker_contributions:
                speaker_contributions[matched_spk] = []
            if content:
                speaker_contributions[matched_spk][0:0] = [] # Ensure list exists
                speaker_contributions[matched_spk].append(content)

    # Join lines for each speaker
    contributions_map = {spk: "\n".join(lines) for spk, lines in speaker_contributions.items() if lines}
    
    # Fallback if regex matching produced no contributions: assign full transcript to first speaker
    if not contributions_map and transcript.strip():
        logging.warning("No line-by-line speaker prefix matched. Using fallback transcript assignment.")
        contributions_map = {norm_participants[0]: transcript.strip()}

    speaker_contributions = contributions_map
    
    # Create prompt without XML tags that confuse smaller models
    system_message = """You are a meeting analyst. Create a JSON summary for each speaker with these fields:
- key_contributions: List of 2-4 main points
- action_items: List of tasks they agreed to
- questions_raised: List of questions they asked
- brief_summary: 1-2 sentence summary

Return ONLY valid JSON, no other text."""
    
    user_message = """Speaker: {speaker}
Contributions: {contributions}"""
    
    prompt = create_chat_prompt_template(system_message, user_message)
    
    # Create the chain - no schema parameter!
    json_parser = create_output_parser()  # Fixed: No schema parameter
    chain = prompt | llm | json_parser
    
    # Generate summaries for each speaker
    speaker_summaries = {}
    
    for speaker, contributions in speaker_contributions.items():
        if contributions.strip():
            if len(contributions) > 8000:
                logging.warning(f"Contributions for {speaker} exceed 8000 chars, truncating")
                contributions = contributions[:7500] + "...\n[Content truncated]"
            
            try:
                # For Ollama with structured output support
                if settings.LLM_PROVIDER == "ollama" and settings.OLLAMA_USE_STRUCTURED_OUTPUT:
                    schema = {
                        "type": "object",
                        "properties": {
                            "key_contributions": {"type": "array", "items": {"type": "string"}},
                            "action_items": {"type": "array", "items": {"type": "string"}},
                            "questions_raised": {"type": "array", "items": {"type": "string"}},
                            "brief_summary": {"type": "string"}
                        },
                        "required": ["key_contributions", "action_items", "questions_raised", "brief_summary"]
                    }
                    
                    # Get a fresh LLM instance with format schema
                    structured_llm = get_ollama_llm(
                        temperature=0.1,
                        purpose="summarization",
                        format_schema=schema
                    )
                    
                    # Create chain without JSON parser for structured output
                    structured_chain = prompt | structured_llm
                    result = structured_chain.invoke({
                        "speaker": speaker,
                        "contributions": contributions
                    })
                    
                    # Parse the structured response
                    if hasattr(result, 'content'):
                        summary = json.loads(result.content)
                    else:
                        summary = json.loads(str(result))
                else:
                    # Regular chain with JSON parser
                    summary = chain.invoke({
                        "speaker": speaker,
                        "contributions": contributions
                    })
                
                # Validate required fields
                required_fields = ["key_contributions", "action_items", "questions_raised", "brief_summary"]
                for field in required_fields:
                    if field not in summary:
                        summary[field] = [] if field != "brief_summary" else "No summary available"
                
                speaker_summaries[speaker] = summary
                
            except Exception as e:
                logging.error(f"Error generating summary for {speaker}: {str(e)}")
                
                # Simpler fallback
                try:
                    simple_prompt = f"Summarize {speaker}'s contributions in 2 sentences: {contributions[:1000]}"
                    simple_chain = llm
                    simple_result = simple_chain.invoke(simple_prompt)
                    
                    speaker_summaries[speaker] = {
                        "key_contributions": ["See brief summary"],
                        "action_items": [],
                        "questions_raised": [],
                        "brief_summary": str(simple_result.content if hasattr(simple_result, 'content') else simple_result)
                    }
                except Exception:
                    speaker_summaries[speaker] = {
                        "key_contributions": ["Error processing contributions"],
                        "action_items": [],
                        "questions_raised": [],
                        "brief_summary": f"Error generating summary for {speaker}"
                    }
    
    return speaker_summaries