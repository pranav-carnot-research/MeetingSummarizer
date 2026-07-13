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


# ─────────────────────────────────────────────────────────────
#  Node 1: critique_summary
# ─────────────────────────────────────────────────────────────

def create_critique_summary_node():
    """
    Creates a LangGraph node that fact-checks the draft summary against the
    raw transcript. Populates state['critique_summary'].
    """
    def critique_summary_node(state: Dict) -> Dict:
        logger.info("Running critique_summary_agent...")
        try:
            transcript_window = _get_transcript_window(state["transcript"])
            meeting_summary = state.get("meeting_summary")

            # Build summary text from MeetingSummary object or dict
            if hasattr(meeting_summary, "model_dump"):
                summary_dict = meeting_summary.model_dump()
            elif isinstance(meeting_summary, dict):
                summary_dict = meeting_summary
            else:
                summary_dict = {"summary": str(meeting_summary), "key_points": [], "decisions": []}

            user_content = f"""DRAFT SUMMARY:
{json.dumps(summary_dict, indent=2)}

RAW TRANSCRIPT:
{transcript_window}"""

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=CRITIQUE_SUMMARY_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ])

            llm = get_llm(temperature=0, purpose="summarization")
            chain = prompt | llm | StrOutputParser()
            raw = chain.invoke({})
            critique = parse_llm_json_object(raw)
            if not critique:
                raise ValueError(f"Could not parse critique_summary JSON: {raw[:300]!r}")

            logger.info(
                f"critique_summary done — accuracy={critique.get('overall_accuracy')}, "
                f"confidence={critique.get('confidence')}, issues={len(critique.get('issues', []))}"
            )

            # Increment the fanin counter (thread-safe enough for LangGraph single-thread)
            new_count = state.get("critique_complete", 0) + 1
            return {**state, "critique_summary": critique, "critique_complete": new_count}

        except Exception as e:
            logger.error(f"critique_summary_node failed: {e}")
            fallback = {
                "issues": [],
                "suggested_corrections": [],
                "overall_accuracy": "high",
                "confidence": 1.0,
                "_error": str(e),
            }
            new_count = state.get("critique_complete", 0) + 1
            return {**state, "critique_summary": fallback, "critique_complete": new_count}

    return critique_summary_node


# ─────────────────────────────────────────────────────────────
#  Node 2: critique_actions
# ─────────────────────────────────────────────────────────────

def create_critique_actions_node():
    """
    Creates a LangGraph node that audits the draft action items against the
    raw transcript. Populates state['critique_actions'].
    """
    def critique_actions_node(state: Dict) -> Dict:
        logger.info("Running critique_actions_agent...")
        try:
            transcript_window = _get_transcript_window(state["transcript"])
            action_items = state.get("action_items", [])

            # Serialize action items (handles both Pydantic models and dicts)
            actions_list = []
            for item in action_items:
                if hasattr(item, "model_dump"):
                    actions_list.append(item.model_dump())
                elif isinstance(item, dict):
                    actions_list.append(item)
                else:
                    actions_list.append({"action": str(item)})

            user_content = f"""DRAFT ACTION ITEMS:
{json.dumps(actions_list, indent=2)}

RAW TRANSCRIPT:
{transcript_window}"""

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=CRITIQUE_ACTIONS_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ])

            llm = get_llm(temperature=0, purpose="summarization")
            chain = prompt | llm | StrOutputParser()
            raw = chain.invoke({})
            critique = parse_llm_json_object(raw)
            if not critique:
                raise ValueError(f"Could not parse critique_actions JSON: {raw[:300]!r}")

            logger.info(
                f"critique_actions done — accuracy={critique.get('overall_accuracy')}, "
                f"confidence={critique.get('confidence')}, "
                f"false_positives={len(critique.get('false_positives', []))}, "
                f"missed={len(critique.get('missed_items', []))}"
            )

            new_count = state.get("critique_complete", 0) + 1
            return {**state, "critique_actions": critique, "critique_complete": new_count}

        except Exception as e:
            logger.error(f"critique_actions_node failed: {e}")
            fallback = {
                "verified_items": [],
                "false_positives": [],
                "missed_items": [],
                "overall_accuracy": "high",
                "confidence": 1.0,
                "_error": str(e),
            }
            new_count = state.get("critique_complete", 0) + 1
            return {**state, "critique_actions": fallback, "critique_complete": new_count}

    return critique_actions_node


# ─────────────────────────────────────────────────────────────
#  Fanin router: wait for both critique agents
# ─────────────────────────────────────────────────────────────

def fanin_router(state: Dict) -> str:
    """
    LangGraph conditional edge function.
    Returns 'wait' until both critiques are done, then 'referee'.

    NOTE: In a sequential LangGraph execution the two critique nodes both run
    before this router is evaluated, so critique_complete will always be 2 here.
    The counter is kept for future parallel execution compatibility.
    """
    complete = state.get("critique_complete", 0)
    if complete >= 2:
        return "referee"
    return "wait"


# ─────────────────────────────────────────────────────────────
#  Node 3: refinement_referee
# ─────────────────────────────────────────────────────────────

def create_refinement_referee_node():
    """
    Creates a LangGraph node that synthesizes both critique reports and
    produces the final refined summary + action items.

    Confidence-gated bypass: if both critiques are high-confidence, the
    original draft is kept and the LLM call is skipped.
    """
    def refinement_referee_node(state: Dict) -> Dict:
        logger.info("Running refinement_referee_agent...")

        critique_summary = state.get("critique_summary", {})
        critique_actions = state.get("critique_actions", {})

        # ── Confidence-gated bypass ──────────────────────────────────────
        summary_conf = float(critique_summary.get("confidence", 0.0))
        actions_conf = float(critique_actions.get("confidence", 0.0))
        both_good = summary_conf >= SKIP_REFINEMENT_THRESHOLD and actions_conf >= SKIP_REFINEMENT_THRESHOLD

        if both_good:
            logger.info(
                f"Both critiques high-confidence (summary={summary_conf:.2f}, "
                f"actions={actions_conf:.2f}) — skipping referee LLM call."
            )
            # Repackage the original draft into refined_output without an LLM call
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

            refined_output = {
                "meeting_summary": summary_dict,
                "action_items": actions_list,
                "refinement_notes": "Bypassed — both critiques reported high confidence.",
                "quality_score": min(summary_conf, actions_conf),
            }
            return {**state, "refined_output": refined_output}

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

SUMMARY CRITIQUE:
{json.dumps(critique_summary, indent=2)}

ACTIONS CRITIQUE:
{json.dumps(critique_actions, indent=2)}

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
