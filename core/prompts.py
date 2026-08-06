# Centralized prompt templates and instructions for the Meeting Summarizer

CONTEXT_INSTRUCTION = """ADDITIONAL MEETING CONTEXT: {context}
Use this provided information to understand the meeting background better and ensure the summary accurately reflects these specific details or focus areas."""

ANALYZE_SYSTEM_PROMPT = """Analyze the meeting transcript and return JSON with this exact structure:
{{
  "meeting_purpose": "brief purpose",
  "main_topics": ["topic1", "topic2", "topic3"],
  "emotional_tone": "brief tone description",
  "participation_level": "brief participation description",
  "disagreement_areas": ["area1", "area2"]
}}

Rules:
- Return ONLY valid JSON
- Keep descriptions brief (under 50 words)
- List 3-5 main topics
- List 0-3 disagreement areas
{language_instructions}"""

SUMMARIZE_SYSTEM_PROMPT = """Create a meeting summary with this JSON structure:
{{
  "summary": "2-3 sentence overview",
  "key_points": ["point1", "point2", "point3"],
  "decisions": ["decision1", "decision2"]
}}

Keep it concise and factual. {language_instructions}"""

EXTRACT_ACTIONS_SYSTEM_PROMPT = """You are a precise meeting assistant. Extract only AGREED-UPON action items from the transcript as a JSON array:
[
  {{
    "action": "specific action description",
    "assignee": "person name or Unassigned",
    "due_date": "date or Not specified",
    "priority": "high/medium/low"
  }}
]

CRITICAL RULES:
1. AGREED-UPON TASKS ONLY: Extract ONLY tasks that were explicitly assigned and agreed upon by the participants.
2. EXCLUDE REJECTED PROPOSALS: Absolutely EXCLUDE any proposals, ideas, or suggestions that were explicitly turned down, rejected, postponed, or decided against. If the transcript shows the team saying "no", "we decided not to", "let's hold off", or "we turned that down", DO NOT extract it.
3. DEDUPLICATE: Merge duplicate tasks that are mentioned multiple times or in different words into a single clear action item.

EXAMPLES OF WHAT TO EXCLUDE (DO NOT EXTRACT):
- Transcript: "Alice: What if we build a WebSocket reconnection wrapper? Bob: No, let's turn that down and stick to HTTP."
  -> EXCLUDE! (Do not extract anything about WebSocket reconnection wrapper).
- Transcript: "Charlie: I can draft the marketing plan. Alice: Actually, let's hold off on that until next month."
  -> EXCLUDE! (Do not extract, postponed/not agreed).

EXAMPLES OF WHAT TO INCLUDE:
- Transcript: "Bob: I will update the database configurations by Friday. Alice: Perfect, go ahead."
  -> INCLUDE: {{"action": "Update the database configurations", "assignee": "Bob", "due_date": "Friday", "priority": "high"}}

Return empty array [] if no actions found. {language_instructions}"""

