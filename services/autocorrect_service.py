"""
Auto-Correction Service - Corrects low-confidence words using ONLY the custom domain glossary.
pyspellchecker has been intentionally removed — it caused too many wrong corrections
(e.g. "backend" -> "backed", "record" -> "recoil") and does not understand technical vocabulary.
"""
import os
import re
import logging
from typing import List, Dict, Any, Set

logger = logging.getLogger("autocorrect-service")

# Path to persistent custom domain glossary file
GLOSSARY_PATH = os.path.join("job_results", "custom_jargon.txt")
os.makedirs("job_results", exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Default glossary — tech/domain compound words that Whisper sometimes mishears.
# Add any term here (or via the UI) so the system learns your vocabulary.
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_GLOSSARY_TERMS = [
    # Infrastructure / cloud
    "Kubernetes", "Microservices", "PostgreSQL", "JavaScript", "TypeScript",
    "FastAPI", "Streamlit", "PyTorch", "Whisper", "Antigravity", "Carnot",
    # Common compound tech words
    "backend", "frontend", "fullstack", "codebase", "dataset", "webhook",
    "endpoint", "middleware", "microservice", "serverless", "dockerfile",
    "devops", "fintech", "healthcheck", "chatbot", "roadmap", "changelog",
    "runtime", "toolchain", "workflow", "pipeline", "datastore", "timestamp",
    "namespace", "breakpoint", "callback", "refactor", "pullrequest",
    # AI / ML / NLP
    "Diarization", "Transcription", "Pyannote", "LangGraph", "LangChain",
    "OpenAI", "Groq", "Ollama", "Huggingface", "Llama", "Mistral",
]

# Initialize default glossary file if it doesn't exist
if not os.path.exists(GLOSSARY_PATH):
    with open(GLOSSARY_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(DEFAULT_GLOSSARY_TERMS) + "\n")

# ─────────────────────────────────────────────────────────────────────────────
# STOPWORDS — common words NEVER auto-corrected.
# Whisper sometimes gives these low confidence near noise, but they are
# almost certainly correct — correcting them causes more harm than good.
# ─────────────────────────────────────────────────────────────────────────────
STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "it", "its", "be", "was",
    "are", "were", "been", "has", "have", "had", "do", "does", "did",
    "not", "no", "so", "if", "we", "us", "he", "she", "they", "them",
    "his", "her", "our", "my", "your", "this", "that", "these", "those",
    "i", "me", "you", "de", "le", "la", "el", "un", "ok", "yes", "go",
    "get", "got", "let", "can", "will", "just", "also", "like", "then",
    "than", "now", "here", "there", "when", "how", "why", "what", "who",
}

# Minimum word length to attempt correction
MIN_CORRECTION_LENGTH = 4


def load_custom_glossary() -> Set[str]:
    """Load terms from the local custom jargon file."""
    glossary = set()
    if os.path.exists(GLOSSARY_PATH):
        with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                term = line.strip()
                if term:
                    glossary.add(term)
    return glossary


def save_custom_term(term: str) -> bool:
    """Save a user-edited term to the persistent glossary."""
    clean_term = term.strip()
    if not clean_term:
        return False

    glossary = load_custom_glossary()
    if clean_term not in glossary:
        with open(GLOSSARY_PATH, "a", encoding="utf-8") as f:
            f.write(clean_term + "\n")
        logger.info(f"Saved new term to custom glossary: {clean_term}")
        return True
    return False


def autocorrect_low_confidence_words(segments: List[Dict[str, Any]], confidence_threshold: float = 65.0) -> List[Dict[str, Any]]:
    """
    Auto-correct low-confidence words (< 65%) using ONLY the custom domain glossary.

    Logic:
      - If word is a stopword                    → HIGH_CONFIDENCE silently (no flag)
      - If word is shorter than 4 characters     → NEEDS_REVIEW (too risky to guess)
      - If word matches glossary & is different  → AI_CORRECTED (blue in UI)
      - If word matches glossary & is same form  → HIGH_CONFIDENCE silently (already correct)
      - Otherwise                                → NEEDS_REVIEW (human should check)

    Args:
        segments: List of transcript segment objects
        confidence_threshold: Threshold below which words trigger auto-correction

    Returns:
        Updated segments with correctly auto-corrected words tagged 'AI_CORRECTED' (blue)
    """
    glossary = load_custom_glossary()
    # Build a lowercase lookup: "kubernetes" -> "Kubernetes"
    glossary_map = {term.lower(): term for term in glossary}

    for seg in segments:
        words = seg.get("words", [])
        seg_conf = seg.get("confidence", 85.0)

        # If segment has no word-level data, build from segment text
        if not words and seg.get("text"):
            raw_words = seg["text"].split()
            words = [
                {"word": w, "confidence": seg_conf, "start": seg.get("start", 0), "end": seg.get("end", 0)}
                for w in raw_words
            ]
            seg["words"] = words

        for w in words:
            w_raw = w.get("word", "").strip()
            if not w_raw:
                continue

            conf = w.get("confidence")
            if conf is None:
                conf = seg_conf
                w["confidence"] = conf

            # Strip punctuation and lowercase for matching
            w_clean = re.sub(r'[^\w\s]', '', w_raw).lower()

            if conf < confidence_threshold:
                # ── Guard 1: Never touch stopwords ────────────────────────
                if w_clean in STOPWORDS:
                    w["status"] = "HIGH_CONFIDENCE"
                    w["confidence"] = max(conf, 75.0)
                    continue

                # ── Guard 2: Skip very short words ─────────────────────────
                if len(w_clean) < MIN_CORRECTION_LENGTH:
                    w["status"] = "NEEDS_REVIEW"
                    continue

                # ── Glossary lookup ─────────────────────────────────────────
                if w_clean in glossary_map:
                    candidate = glossary_map[w_clean]

                    if candidate != w_raw and candidate.lower() != w_raw.lower():
                        # Genuine correction — word changes to a different form
                        prefix = re.match(r'^[^\w]+', w_raw)
                        suffix = re.search(r'[^\w]+$', w_raw)
                        prefix_str = prefix.group(0) if prefix else ""
                        suffix_str = suffix.group(0) if suffix else ""

                        corrected_full = f"{prefix_str}{candidate}{suffix_str}"
                        w["original_word"] = w_raw
                        w["word"] = corrected_full
                        w["status"] = "AI_CORRECTED"
                        w["confidence"] = 88.0
                        logger.info(f"Glossary correction: '{w_raw}' -> '{corrected_full}'")
                    else:
                        # Word is already the correct form — boost silently, no blue
                        w["status"] = "HIGH_CONFIDENCE"
                        w["confidence"] = 88.0
                else:
                    # Not in glossary — flag for human review
                    w["status"] = "NEEDS_REVIEW"

            else:
                # Word has sufficient confidence
                w["status"] = "HIGH_CONFIDENCE" if conf >= 90 else "MEDIUM_CONFIDENCE"

    return segments
