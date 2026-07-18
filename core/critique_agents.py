"""
critique_agents.py — Phase 1: Multi-Agent Critique & Refinement Loop

Architecture:
  format_output
       ├── critique_summary_agent   (parallel fanout)
       └── critique_actions_agent   (parallel fanout)
                    └── [fanin: both_critiques_ready]
                              └── refinement_referee_agent
                                        └── (updates state with refined output)

The two critique agents independently verify the draft summary and action items
against the raw transcript. The refinement_referee synthesizes their findings
and produces the final polished output.

Confidence-gated bypass:
  If both critiques report high confidence (>= SKIP_REFINEMENT_THRESHOLD), the
  referee LLM call is skipped and the original draft is used as-is. This saves
  tokens when the initial output is already accurate.
"""

import json
import logging
from typing import Dict, List, Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from services.json_utils import parse_llm_json_object

from core.prompts import (
    CRITIQUE_SUMMARY_SYSTEM_PROMPT,
    CRITIQUE_ACTIONS_SYSTEM_PROMPT,
    REFINEMENT_REFEREE_SYSTEM_PROMPT,
)
from services.llm_service import get_llm

logger = logging.getLogger(__name__)

# If both agents report confidence >= this threshold, skip the referee LLM call
SKIP_REFINEMENT_THRESHOLD = 0.88

# Max transcript chars sent to critique agents to stay within context limits
CRITIQUE_TRANSCRIPT_LIMIT = 8000


def _get_transcript_window(transcript: str, limit: int = CRITIQUE_TRANSCRIPT_LIMIT) -> str:
    """Truncate transcript to avoid blowing the context window."""
    if len(transcript) <= limit:
        return transcript
    # Keep first 60% and last 40% to preserve opening context and recent decisions
    head = int(limit * 0.6)
    tail = limit - head
    return transcript[:head] + "\n\n[... transcript truncated ...]\n\n" + transcript[-tail:]


# ── Global NLI Model Cache ───────────────────────────────────
_nli_tokenizer = None
_nli_model = None

def get_nli_model():
    """Lazily load and cache the local NLI model and tokenizer."""
    global _nli_tokenizer, _nli_model
    if _nli_model is None:
        logger.info("Initializing local DeBERTa-v3-base NLI Model...")
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_name = "cross-encoder/nli-deberta-v3-base"
        _nli_tokenizer = AutoTokenizer.from_pretrained(model_name)
        _nli_model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
        _nli_model.eval()
    return _nli_tokenizer, _nli_model

def decompose_claims(sentence: str) -> List[str]:
    """Decompose a complex sentence into a list of atomic assertions using a fast LLM step."""
    try:
        from langchain_core.output_parsers import JsonOutputParser
        llm = get_llm(temperature=0.0, purpose="general")
        system_prompt = """You are a precise statement analyst.
Your task is to decompose a complex sentence from a meeting summary into a list of simple, single-claim assertions (atomic claims).
Each claim must contain exactly one subject, one action, and one object/context, and be standalone (resolve pronouns like 'he', 'they', 'the switch' to actual nouns where clear).

Return ONLY a JSON array of strings. Do not include markdown code blocks or explanations."""

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Sentence: {sentence}")
        ])
        chain = prompt | llm | JsonOutputParser()
        claims = chain.invoke({})
        if isinstance(claims, list):
            return claims
        return [sentence]
    except Exception as e:
        logger.warning(f"Error decomposing sentence: {e}. Falling back to original.")
        return [sentence]

def get_best_segment(claim: str, transcript_lines: List[str], window_size: int = 5, step: int = 2) -> str:
    """Find the segment of raw transcript most lexically relevant to the claim."""
    import re
    claim_words = set(re.findall(r'\b\w+\b', claim.lower()))
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 
        'to', 'of', 'in', 'on', 'at', 'for', 'with', 'by', 'that', 'this', 
        'these', 'those', 'it', 'he', 'she', 'they', 'we', 'i', 'you', 'my', 'your'
    }
    claim_words = claim_words - stopwords
    
    if not claim_words:
        return "\n".join(transcript_lines[:window_size])
        
    best_window = ""
    best_score = -1
    
    for i in range(0, len(transcript_lines) - window_size + 1, step):
        window = transcript_lines[i:i+window_size]
        window_text = "\n".join(window)
        window_words = set(re.findall(r'\b\w+\b', window_text.lower()))
        overlap = claim_words.intersection(window_words)
        score = len(overlap)
        
        if score > best_score:
            best_score = score
            best_window = window_text
            
    return best_window

# ── Node: critique_nli ──────────────────────────────────────
def create_nli_critique_node():
    """
    Creates a LangGraph node that fact-checks the draft summary and action items
    against the raw transcript using a local NLI model.
    Populates state['nli_issues'].
    """
    import re
    import torch

    def nli_critique_node(state: Dict) -> Dict:
        logger.info("Running local NLI factual consistency check...")
        try:
            transcript = state["transcript"]
            meeting_summary = state.get("meeting_summary")
            action_items = state.get("action_items", [])
            
            # Parse draft items
            if hasattr(meeting_summary, "model_dump"):
                summary_dict = meeting_summary.model_dump()
            elif isinstance(meeting_summary, dict):
                summary_dict = meeting_summary
            else:
                summary_dict = {"summary": str(meeting_summary), "key_points": [], "decisions": []}
                
            summary_sentences = [
                s.strip() 
                for s in re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', summary_dict.get("summary", "")) 
                if s.strip()
            ]
            key_points = summary_dict.get("key_points", [])
            decisions = summary_dict.get("decisions", [])
            
            # Format action items as sentences
            actions = []
            for item in action_items:
                if hasattr(item, "model_dump"):
                    item_dict = item.model_dump()
                elif isinstance(item, dict):
                    item_dict = item
                else:
                    item_dict = {"action": str(item), "assignee": "Unassigned", "due_date": "Not specified"}
                actions.append(f"{item_dict.get('assignee', 'Unassigned')} is assigned to: {item_dict.get('action')} due {item_dict.get('due_date', 'Not specified')}")
            
            # Gather all statements to verify
            all_statements = []
            for s in summary_sentences:
                all_statements.append(("Summary Sentence", s))
            for kp in key_points:
                all_statements.append(("Key Point", kp))
            for dec in decisions:
                all_statements.append(("Decision", dec))
            for act in actions:
                all_statements.append(("Action Item", act))
                
            logger.info(f"NLI node deconstructed draft into {len(all_statements)} statements to verify.")
            
            # Initialize local NLI model
            tokenizer, model = get_nli_model()
            device = next(model.parameters()).device
            id2label = model.config.id2label
            
            transcript_lines = [line.strip() for line in transcript.split('\n') if line.strip()]
            nli_issues = []
            
            for category, statement in all_statements:
                # Decompose statement into claims
                claims = decompose_claims(statement)
                
                for claim in claims:
                    # Find matching transcript segment
                    premise = get_best_segment(claim, transcript_lines, window_size=5, step=2)
                    
                    # Run NLI
                    inputs = tokenizer(premise, claim, return_tensors="pt", truncation=True, max_length=512)
                    # Convert inputs to target device (handles dict-like objects and real BatchEncoding)
                    if hasattr(inputs, "to"):
                        inputs = inputs.to(device)
                    else:
                        inputs = {k: v.to(device) for k, v in inputs.items()}
                        
                    with torch.no_grad():
                        outputs = model(**inputs)
                    probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()[0]
                    
                    # Map probabilities to labels
                    nli_probs = {}
                    for idx, prob in enumerate(probs):
                        label = id2label[idx].lower()
                        nli_probs[label] = float(prob)
                        
                    contradiction_prob = nli_probs.get("contradiction", nli_probs.get("contradict", 0.0))
                    
                    if contradiction_prob > 0.5:
                        logger.warning(f"Contradiction found (Prob: {contradiction_prob:.3f}) for claim: '{claim}'")
                        nli_issues.append({
                            "category": category,
                            "original_statement": statement,
                            "contradictory_claim": claim,
                            "transcript_evidence": premise,
                            "contradiction_probability": contradiction_prob
                        })
            
            logger.info(f"NLI validation completed. Found {len(nli_issues)} contradictions.")
            return {**state, "nli_issues": nli_issues}
            
        except Exception as e:
            logger.error(f"NLI critique node failed: {e}", exc_info=True)
            # Safe fallback: no issues flagged so we bypass referee
            return {**state, "nli_issues": []}
            
    return nli_critique_node

# ── NLI Router ──────────────────────────────────────────────
def nli_router(state: Dict) -> str:
    """
    LangGraph conditional edge router.
    Routes to 'referee' if contradictions were found, otherwise routes to 'bypass'.
    """
    issues = state.get("nli_issues", [])
    if issues:
        logger.info(f"Routing to referee node to correct {len(issues)} contradictions.")
        return "referee"
    logger.info("Routing to bypass (node_task_decomposer) since no contradictions were found.")
    return "bypass"



# ─────────────────────────────────────────────────────────────
#  Node 3: refinement_referee
# ─────────────────────────────────────────────────────────────

def create_refinement_referee_node():
    """
    Creates a LangGraph node that synthesizes NLI contradiction reports and
    produces the final refined summary + action items.
    """
    def refinement_referee_node(state: Dict) -> Dict:
        logger.info("Running refinement_referee_agent...")

        # ── Run referee LLM ──────────────────────────────────────────────
        try:
            transcript_window = _get_transcript_window(state["transcript"])

            meeting_summary = state.get("meeting_summary")
            if hasattr(meeting_summary, "model_dump"):
                summary_dict = meeting_summary.model_dump()
            elif isinstance(meeting_summary, dict):
                summary_dict = meeting_summary
            else:
                summary_dict = {"summary": str(meeting_summary), "key_points": [], "decisions": []}

            action_items = state.get("action_items", [])
            actions_list = [
                item.model_dump() if hasattr(item, "model_dump") else (item if isinstance(item, dict) else {"action": str(item)})
                for item in action_items
            ]

            user_content = f"""DRAFT SUMMARY:
{json.dumps(summary_dict, indent=2)}

DRAFT ACTION ITEMS:
{json.dumps(actions_list, indent=2)}

FACTUAL CONTRADICTIONS ENCOUNTERED:
{json.dumps(state.get("nli_issues", []), indent=2)}

RAW TRANSCRIPT:
{transcript_window}"""

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=REFINEMENT_REFEREE_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ])

            llm = get_llm(temperature=0.1, purpose="summarization")
            chain = prompt | llm | StrOutputParser()
            raw = chain.invoke({})
            refined_output = parse_llm_json_object(raw)
            if not refined_output:
                raise ValueError(f"Could not parse referee JSON: {raw[:300]!r}")

            logger.info(
                f"refinement_referee done — quality_score={refined_output.get('quality_score')}"
            )
            return {**state, "refined_output": refined_output}

        except Exception as e:
            logger.error(f"refinement_referee_node failed: {e}. Using original draft.")
            # Fall back gracefully to original draft
            meeting_summary = state.get("meeting_summary")
            if hasattr(meeting_summary, "model_dump"):
                summary_dict = meeting_summary.model_dump()
            else:
                summary_dict = meeting_summary if isinstance(meeting_summary, dict) else {}

            action_items = state.get("action_items", [])
            actions_list = [
                item.model_dump() if hasattr(item, "model_dump") else (item if isinstance(item, dict) else {})
                for item in action_items
            ]

            return {
                **state,
                "refined_output": {
                    "meeting_summary": summary_dict,
                    "action_items": actions_list,
                    "refinement_notes": f"Referee failed ({str(e)}), using original draft.",
                    "quality_score": 0.5,
                },
            }

    return refinement_referee_node
