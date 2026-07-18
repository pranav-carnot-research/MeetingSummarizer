"""
task_planner.py — Phase 2: AI Task Decomposer & Planner Agent

Runs after the refinement_referee node. Takes the REFINED action items +
raw transcript and extracts structured Task objects with rich metadata:
  - Verified assignee + confidence score
  - Deadline with type (hard / soft / none)
  - Task type category
  - Evidence quotes from the transcript (hallucination prevention)
  - Inter-task dependencies

The final API response gains a top-level 'task_plan' key that coexists
peacefully with the existing 'meeting_summary' and 'action_items' keys.
"""

import json
import logging
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field, validator
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from services.json_utils import parse_llm_json_array

from core.prompts import TASK_DECOMPOSER_SYSTEM_PROMPT
from services.llm_service import get_llm

logger = logging.getLogger(__name__)

# Max transcript chars sent to task decomposer
TASK_TRANSCRIPT_LIMIT = 8000


# ─────────────────────────────────────────────────────────────
#  Rich Task schema
# ─────────────────────────────────────────────────────────────

class Task(BaseModel):
    """A richly-structured task extracted and planned from the meeting."""

    title: str = Field(description="Short task title (max ~10 words)")
    description: str = Field(description="Full clear description of what needs to be done")
    assignee: str = Field(default="Unassigned", description="Person responsible, exactly as named in transcript")
    assignee_confidence: float = Field(
        default=0.0,
        description="0-1 confidence that the assignee is correct"
    )
    deadline: str = Field(default="Not mentioned", description="Specific date/time, relative time, or 'Not mentioned'")
    deadline_type: str = Field(
        default="none",
        description="'hard' (specific date), 'soft' (relative/flexible), or 'none'"
    )
    priority: str = Field(default="medium", description="critical / high / medium / low")
    task_type: str = Field(
        default="other",
        description="decision / research / implementation / review / communication / planning / other"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Titles of tasks this depends on"
    )
    evidence_quotes: List[str] = Field(
        default_factory=list,
        description="Verbatim transcript quotes proving this task was agreed upon"
    )
    status: str = Field(default="open", description="Task status — always 'open' for new tasks")

    @validator("deadline_type")
    def validate_deadline_type(cls, v):
        allowed = {"hard", "soft", "none"}
        return v if v in allowed else "none"

    @validator("priority")
    def validate_priority(cls, v):
        allowed = {"critical", "high", "medium", "low"}
        return v if v in allowed else "medium"

    @validator("task_type")
    def validate_task_type(cls, v):
        allowed = {"decision", "research", "implementation", "review", "communication", "planning", "other"}
        return v if v in allowed else "other"

    @validator("assignee_confidence")
    def clamp_confidence(cls, v):
        """Clamp to [0, 1] — accept any float without raising."""
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


# ─────────────────────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────────────────────

def _get_transcript_window(transcript: str, limit: int = TASK_TRANSCRIPT_LIMIT) -> str:
    """Truncate transcript to avoid blowing the context window."""
    if len(transcript) <= limit:
        return transcript
    head = int(limit * 0.6)
    tail = limit - head
    return transcript[:head] + "\n\n[... transcript truncated ...]\n\n" + transcript[-tail:]


def _get_refined_actions(state: Dict) -> List[Dict]:
    """
    Pull the refined action items from state.
    Falls back to original action_items if refined_output is missing.
    """
    refined_output = state.get("refined_output", {})

    # Try refined output first
    if refined_output and "action_items" in refined_output:
        raw = refined_output["action_items"]
    else:
        # Fallback to original action_items
        raw = state.get("action_items", [])

    result = []
    for item in raw:
        if hasattr(item, "model_dump"):
            result.append(item.model_dump())
        elif isinstance(item, dict):
            result.append(item)
        else:
            result.append({"action": str(item)})
    return result


# ─────────────────────────────────────────────────────────────
#  Node 1: task_decomposer
# ─────────────────────────────────────────────────────────────

def create_task_decomposer_node():
    """
    LangGraph node that extracts richly-structured Task objects.
    Uses refined action items + raw transcript as input.
    """
    def task_decomposer_node(state: Dict) -> Dict:
        logger.info("Running task_decomposer_agent...")
        try:
            transcript_window = _get_transcript_window(state["transcript"])
            refined_actions = _get_refined_actions(state)

            if not refined_actions:
                logger.info("No action items to decompose — returning empty task_plan.")
                return {**state, "task_plan": []}

            user_content = f"""REFINED ACTION ITEMS:
{json.dumps(refined_actions, indent=2)}

RAW TRANSCRIPT:
{transcript_window}"""

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=TASK_DECOMPOSER_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ])

            llm = get_llm(temperature=0.1, purpose="summarization")
            chain = prompt | llm | StrOutputParser()
            raw = chain.invoke({})
            raw_tasks = parse_llm_json_array(raw)
            if raw_tasks is None:
                logger.warning(f"task_decomposer could not parse JSON array: {raw[:300]!r}")
                raw_tasks = []

            # Validate and coerce each task via the Pydantic model
            task_plan = []
            for raw_task in raw_tasks:
                try:
                    task = Task(**raw_task)
                    task_plan.append(task)
                except Exception as ve:
                    logger.warning(f"Task validation failed, using raw dict: {ve}")
                    # Still include it as a best-effort dict
                    task_plan.append(raw_task)

            logger.info(f"task_decomposer done — {len(task_plan)} tasks extracted.")
            return {**state, "task_plan": task_plan}

        except Exception as e:
            logger.error(f"task_decomposer_node failed: {e}")
            # Return empty plan on failure — don't crash the whole pipeline
            return {**state, "task_plan": []}

    return task_decomposer_node


# ─────────────────────────────────────────────────────────────
#  Node 2: format_task_output (terminal formatter)
# ─────────────────────────────────────────────────────────────

def create_format_task_output_node():
    """
    LangGraph node that assembles the final state with task_plan serialized.
    This is the last node before END.
    """
    def format_task_output_node(state: Dict) -> Dict:
        """Serialize task_plan and merge everything into final_output."""

        # Serialize task_plan items
        task_plan_serialized = []
        for task in state.get("task_plan", []):
            if hasattr(task, "model_dump"):
                task_plan_serialized.append(task.model_dump())
            elif isinstance(task, dict):
                task_plan_serialized.append(task)
            else:
                task_plan_serialized.append({"raw": str(task)})

        # Pull refined output (from refinement_referee)
        refined_output = state.get("refined_output", {})

        # Build final_output — backward-compatible with existing schema
        # meeting_summary and action_items come from refined_output if available,
        # otherwise fall back to the original pipeline's output
        if refined_output:
            meeting_summary_data = refined_output.get("meeting_summary", {})
            action_items_data = refined_output.get("action_items", [])
        else:
            ms = state.get("meeting_summary")
            meeting_summary_data = ms.model_dump() if hasattr(ms, "model_dump") else (ms or {})
            ai = state.get("action_items", [])
            action_items_data = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in ai
            ]

        # ── Pipeline trace: capture draft + critique reports for auditability ──
        # This lets callers see what each agent did (before vs. after).
        draft_ms = state.get("meeting_summary")
        draft_summary = draft_ms.model_dump() if hasattr(draft_ms, "model_dump") else (draft_ms or {})
        draft_actions = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in state.get("action_items", [])
        ]

        from config import settings
        pipeline_trace = {
            # Phase 0: what the initial extractor produced
            "draft": {
                "meeting_summary": draft_summary,
                "action_items": draft_actions,
            },
            # Phase 1: local NLI fact-checker findings
            "nli_verification": {
                "refinement_enabled": settings.ENABLE_REFINEMENT_LOOP,
                "contradictions_found": state.get("nli_issues") if settings.ENABLE_REFINEMENT_LOOP else None,
                "total_contradictions": len(state.get("nli_issues", [])) if settings.ENABLE_REFINEMENT_LOOP else 0,
            },
            # Phase 1c: whether referee LLM was invoked or bypass triggered
            "refinement": {
                "referee_invoked": (
                    "Bypassed" not in str(refined_output.get("refinement_notes", ""))
                    if settings.ENABLE_REFINEMENT_LOOP and refined_output
                    else False
                ),
                "notes": (
                    refined_output.get("refinement_notes") 
                    if refined_output 
                    else ("Refinement bypassed (NLI verified factual consistency)" if settings.ENABLE_REFINEMENT_LOOP else "Refinement disabled via config")
                ),
                "quality_score": (
                    refined_output.get("quality_score") 
                    if refined_output 
                    else (1.0 if settings.ENABLE_REFINEMENT_LOOP else 0.8)
                ),
            },
        }

        final_output = {
            # Original fields — unchanged schema
            "meeting_summary": meeting_summary_data,
            "action_items": action_items_data,
            # New Phase 1 field
            "quality_score": (
                refined_output.get("quality_score") 
                if refined_output 
                else (1.0 if settings.ENABLE_REFINEMENT_LOOP else 0.8)
            ),
            "refinement_notes": (
                refined_output.get("refinement_notes") 
                if refined_output 
                else ("Refinement bypassed (NLI verified factual consistency)" if settings.ENABLE_REFINEMENT_LOOP else "Refinement disabled via config")
            ),
            # New Phase 2 field
            "task_plan": task_plan_serialized,
            # Audit trail — full pipeline trace for every run
            "pipeline_trace": pipeline_trace,
        }

        return {**state, "final_output": final_output, "current_step": "complete"}

    return format_task_output_node
