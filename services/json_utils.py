"""
services/json_utils.py — Robust JSON extraction for LLM responses.

LLMs like llama-3.1-8b-instant sometimes wrap JSON in markdown code blocks
or add explanation text before/after the JSON. This module handles all those
cases so callers don't need to worry about raw LLM output format.
"""
import re
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def parse_llm_json(text: str, expected_type: str = "any") -> Any:
    """
    Robustly extract and parse JSON from an LLM response string.

    Handles:
    - Raw JSON (ideal case)
    - JSON wrapped in ```json ... ``` markdown code blocks
    - JSON preceded/followed by explanation text
    - Double-brace escaped braces ({{ }}) that Llama echoes from Python format strings
    - Trailing commas and minor JSON syntax issues

    Args:
        text: Raw string output from the LLM
        expected_type: "object" | "array" | "any" — used to prefer the right JSON type

    Returns:
        Parsed Python object (dict or list) or None if all parsing attempts fail
    """
    if not text or not text.strip():
        return None

    # Step 1: Fix double-brace escaping that Llama echoes from prompts
    # {{ -> {  and  }} -> }  (safe because {{ is not valid JSON)
    cleaned = text.replace("{{", "{").replace("}}", "}")

    # Step 2: Try markdown code block extraction first
    code_block = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            logger.debug("Code block extraction failed, trying other methods")

    # Step 3: Try direct parse on full cleaned text
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        pass

    # Step 4: Extract JSON object or array by finding the outermost braces/brackets
    # Try array first if expected, otherwise try object first
    patterns = []
    if expected_type == "array":
        patterns = [r'(\[[\s\S]*\])', r'(\{[\s\S]*\})']
    elif expected_type == "object":
        patterns = [r'(\{[\s\S]*\})', r'(\[[\s\S]*\])']
    else:
        # Try both, prefer whichever appears first
        obj_match = re.search(r'(\{[\s\S]*\})', cleaned)
        arr_match = re.search(r'(\[[\s\S]*\])', cleaned)
        if obj_match and arr_match:
            patterns = [r'(\{[\s\S]*\})', r'(\[[\s\S]*\])'] if obj_match.start() <= arr_match.start() else [r'(\[[\s\S]*\])', r'(\{[\s\S]*\})']
        elif obj_match:
            patterns = [r'(\{[\s\S]*\})']
        elif arr_match:
            patterns = [r'(\[[\s\S]*\])']

    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

    # Step 5: Try removing trailing content after last } or ]
    for end_char, pattern in [('}', r'^[\s\S]*\}'), (']', r'^[\s\S]*\]')]:
        try:
            trimmed = re.sub(r'[^}\]]*$', '', cleaned).strip()
            if trimmed:
                return json.loads(trimmed)
        except json.JSONDecodeError:
            pass

    logger.warning(f"All JSON parse attempts failed. Text snippet: {text[:200]!r}")
    return None


def parse_llm_json_object(text: str) -> Optional[dict]:
    """Convenience wrapper that expects a JSON object (dict)."""
    result = parse_llm_json(text, expected_type="object")
    if isinstance(result, dict):
        return result
    return None


def parse_llm_json_array(text: str) -> Optional[list]:
    """Convenience wrapper that expects a JSON array (list)."""
    result = parse_llm_json(text, expected_type="array")
    if isinstance(result, list):
        return result
    return None
