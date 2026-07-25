"""
LLM Refinement Service - Post-corrects low confidence transcription words using Local LLM (Ollama)
"""
import logging
import json
from typing import Dict, List, Any, Optional
from services.llm_service import get_llm, create_chat_prompt_template
from config import settings

logger = logging.getLogger("llm-refinement-service")

REFINE_SYSTEM_PROMPT = """You are an expert audio transcription refinement assistant.
Your task is to review an audio transcript and fix phonetically misheard words, domain jargon, technical acronyms, or grammar glitches based on surrounding sentence context.

Rules:
1. Only correct words that are genuinely misheard or grammatically incorrect based on meeting context.
2. DO NOT rewrite valid sentences or change the meaning.
3. For every word you change, provide the original word and the corrected word.
4. Output MUST be valid JSON conforming to the requested schema.
"""

REFINE_USER_PROMPT = """Analyze the following meeting transcript segment.
Full Context Text: "{full_text}"

Segment Text: "{segment_text}"
Low-confidence words flagged in segment: {flagged_words}

Return JSON with this exact structure:
{{
  "corrected_segment_text": "The full corrected segment text",
  "corrections": [
    {{
      "original_word": "misheard word",
      "corrected_word": "fixed word",
      "reason": "Phonetic correction based on context"
    }}
  ]
}}
"""

def refine_transcript_segments(segments: List[Dict[str, Any]], confidence_threshold: float = 85.0) -> List[Dict[str, Any]]:
    """
    Refine transcript segments using Local LLM (Ollama).
    Identifies low-confidence words and uses Ollama to contextually correct them.

    Args:
        segments: List of transcript segment dictionaries (with 'words' or 'text')
        confidence_threshold: Threshold below which words are considered low confidence

    Returns:
        Refined list of segment dictionaries with updated word objects and 'ai_corrected' markers.
    """
    logger.info(f"Starting transcript refinement using Local LLM ({settings.LLM_PROVIDER})...")

    # Get configured local LLM (Ollama)
    llm = get_llm(temperature=0.1, purpose="general")

    refined_segments = []

    for seg_idx, segment in enumerate(segments):
        seg_copy = dict(segment)
        words = seg_copy.get("words", [])
        seg_text = seg_copy.get("text", "")

        # Find low confidence words in this segment
        flagged_words = []
        if words:
            for w in words:
                conf = w.get("confidence")
                if conf is not None and conf < confidence_threshold:
                    flagged_words.append({
                        "word": w.get("word", "").strip(),
                        "confidence": conf,
                        "start": w.get("start"),
                        "end": w.get("end")
                    })

        # If no words list, estimate from segment text if segment confidence is low
        if not flagged_words and seg_copy.get("confidence", 100) < confidence_threshold and seg_text:
            flagged_words.append({"word": seg_text, "confidence": seg_copy.get("confidence")})

        # Skip LLM call if segment has high confidence and no low confidence words
        if not flagged_words:
            # Mark all words as HIGH_CONFIDENCE
            if "words" in seg_copy:
                for w in seg_copy["words"]:
                    if "status" not in w:
                        w["status"] = "HIGH_CONFIDENCE"
            refined_segments.append(seg_copy)
            continue

        # Prepare context window (preceding segment + current segment + following segment)
        prev_text = segments[seg_idx - 1].get("text", "") if seg_idx > 0 else ""
        next_text = segments[seg_idx + 1].get("text", "") if seg_idx < len(segments) - 1 else ""
        full_context = f"{prev_text} {seg_text} {next_text}".strip()

        try:
            prompt_template = create_chat_prompt_template(REFINE_SYSTEM_PROMPT, REFINE_USER_PROMPT, use_simple_format=True)
            formatted_prompt = prompt_template.format_messages(
                full_text=full_context,
                segment_text=seg_text,
                flagged_words=json.dumps([f["word"] for f in flagged_words])
            )

            response = llm.invoke(formatted_prompt)

            # Extract content from response
            response_content = response.content if hasattr(response, "content") else str(response)

            # Parse JSON from LLM response
            json_start = response_content.find("{")
            json_end = response_content.rfind("}") + 1
            if json_start != -1 and json_end != -1:
                clean_json_str = response_content[json_start:json_end]
                refinement_data = json.loads(clean_json_str)

                corrections = refinement_data.get("corrections", [])
                corrected_text = refinement_data.get("corrected_segment_text", seg_text)

                # Map corrections back to words array
                if words and corrections:
                    correction_map = {c["original_word"].strip().lower(): c for c in corrections if "original_word" in c}
                    for w in words:
                        w_raw = w.get("word", "").strip()
                        w_clean = w_raw.strip(",.?!:;\"'").lower()
                        if w_clean in correction_map:
                            cor_info = correction_map[w_clean]
                            w["original_word"] = w_raw
                            w["word"] = cor_info.get("corrected_word", w_raw)
                            w["status"] = "AI_CORRECTED"
                            w["reason"] = cor_info.get("reason", "Contextual correction")
                        elif w.get("confidence", 100) < 65:
                            w["status"] = "NEEDS_REVIEW"
                        else:
                            w["status"] = "HIGH_CONFIDENCE"

                seg_copy["text"] = corrected_text
                seg_copy["ai_refined"] = True
                seg_copy["corrections_count"] = len(corrections)
            else:
                logger.warning(f"Could not parse JSON from LLM refinement output: {response_content[:100]}")
                if words:
                    for w in words:
                        conf = w.get("confidence", 100)
                        w["status"] = "NEEDS_REVIEW" if conf < 65 else "HIGH_CONFIDENCE"

        except Exception as e:
            logger.error(f"Error during LLM transcript refinement: {str(e)}")
            # Fallback: mark low confidence words as NEEDS_REVIEW
            if words:
                for w in words:
                    conf = w.get("confidence", 100)
                    w["status"] = "NEEDS_REVIEW" if conf < 65 else "HIGH_CONFIDENCE"

        refined_segments.append(seg_copy)

    logger.info(f"Refinement complete for {len(refined_segments)} segments.")
    return refined_segments
