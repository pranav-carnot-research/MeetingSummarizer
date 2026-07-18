"""
follow_up_agent.py — Automated Follow-up & Communication Agent

Responsibilities:
  1. Group action items by assignee (one email per person)
  2. Use LLM to draft a personalised, context-rich follow-up email per assignee
  3. Send via SMTP (app-password / Gmail / Outlook)
  4. Return draft dict so the Streamlit UI can preview before sending

SMTP config is read from environment / .env.dev:
    SMTP_HOST      e.g. smtp.gmail.com
    SMTP_PORT      e.g. 587
    SMTP_USER      sender email address
    SMTP_PASSWORD  app password (NOT your account password)
    SMTP_FROM_NAME display name shown in From: header  (optional)
"""

import json
import logging
import smtplib
import os
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from services.llm_service import get_llm

# Explicitly load .env.dev so os.getenv() sees SMTP_* vars.
# config.py calls load_dotenv() with no args (looks for .env, not .env.dev).
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.dev")
load_dotenv(dotenv_path=_env_path, override=False)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  SMTP helpers
# ─────────────────────────────────────────────────────────────

def _get_smtp_config() -> Dict[str, str]:
    return {
        "host":      os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port":      int(os.getenv("SMTP_PORT", "587")),
        "user":      os.getenv("SMTP_USER", ""),
        "password":  os.getenv("SMTP_PASSWORD", ""),
        "from_name": os.getenv("SMTP_FROM_NAME", "Meeting Summarizer"),
    }


def smtp_config_is_valid() -> Tuple[bool, str]:
    """Returns (True, "") if SMTP is configured, else (False, reason)."""
    cfg = _get_smtp_config()
    if not cfg["user"]:
        return False, "SMTP_USER not set in .env.dev"
    if not cfg["password"]:
        return False, "SMTP_PASSWORD not set in .env.dev"
    return True, ""


# ─────────────────────────────────────────────────────────────
#  Core: group action items by assignee
# ─────────────────────────────────────────────────────────────

def group_by_assignee(action_items: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Returns { assignee_name: [action_item, ...] }
    Skips "Unassigned" items — no one to email.
    """
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for item in action_items:
        assignee = (item.get("assignee") or "Unassigned").strip()
        if assignee.lower() == "unassigned":
            continue
        groups[assignee].append(item)
    return dict(groups)


# ─────────────────────────────────────────────────────────────
#  LLM email draft generation
# ─────────────────────────────────────────────────────────────

_EMAIL_SYSTEM_PROMPT = """You are a professional assistant writing a follow-up email on behalf of a meeting organiser.

Your email must:
1. Open with a warm, brief greeting (1 sentence).
2. Include a short MEETING CONTEXT section (2-3 sentences): what was discussed and what decisions were made — give the recipient enough context so they understand why their tasks matter.
3. Include a clearly formatted YOUR ACTION ITEMS section listing ONLY the tasks assigned to this specific person. For each task show:
   - The task description (specific and technical)
   - Due date
   - Priority (HIGH / MEDIUM / LOW)
4. Include a 1-2 sentence WHY THIS MATTERS note explaining how their tasks connect to the team's goals or decisions.
5. Close professionally.

STRICT RULES:
- Write ONLY the email body (no subject line, no JSON, no markdown fences).
- Do not invent tasks beyond what is provided.
- Keep the tone professional and clear, not overly formal.
- If due date is "Not specified", write "No hard deadline — please complete at your earliest convenience."
- Do NOT include action items assigned to other people.
"""


def draft_email_for_assignee(
    assignee: str,
    items: List[Dict],
    meeting_summary: Dict,
    sender_name: str = "The Meeting Organiser",
) -> str:
    """
    Use the LLM to write a personalised email body for one assignee.
    Returns the raw email body text.
    """
    summary_text = meeting_summary.get("summary", "No summary available.")
    decisions = meeting_summary.get("decisions", [])
    decisions_text = "\n".join(f"- {d}" for d in decisions) if decisions else "None recorded."

    items_text = ""
    for i, item in enumerate(items, 1):
        priority = (item.get("priority") or "medium").upper()
        due = item.get("due_date") or "Not specified"
        action = item.get("action", "")
        items_text += f"{i}. {action}\n   Due: {due}  |  Priority: {priority}\n\n"

    user_content = f"""ASSIGNEE NAME: {assignee}

MEETING SUMMARY:
{summary_text}

DECISIONS MADE:
{decisions_text}

ACTION ITEMS FOR {assignee.upper()}:
{items_text.strip()}

SENDER NAME: {sender_name}

Write the email body now."""

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=_EMAIL_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ])

    llm = get_llm(temperature=0.4, purpose="general")
    chain = prompt | llm | StrOutputParser()

    try:
        body = chain.invoke({})
        return body.strip()
    except Exception as e:
        logger.error(f"LLM email draft failed for {assignee}: {e}")
        # Fallback: plain-text summary
        lines = [
            f"Hi {assignee},",
            "",
            "Here is a summary of your action items from our recent meeting:",
            "",
        ]
        for item in items:
            lines.append(f"• {item.get('action', '')}")
            lines.append(f"  Due: {item.get('due_date', 'Not specified')}  |  Priority: {(item.get('priority', 'medium')).upper()}")
            lines.append("")
        lines.append(f"Best regards,\n{sender_name}")
        return "\n".join(lines)


def draft_all_emails(
    action_items: List[Dict],
    meeting_summary: Dict,
    sender_name: str = "The Meeting Organiser",
) -> Dict[str, str]:
    """
    Draft one email body per unique assignee.
    Returns { assignee_name: email_body_text }
    """
    groups = group_by_assignee(action_items)
    drafts: Dict[str, str] = {}

    for assignee, items in groups.items():
        logger.info(f"Drafting follow-up email for: {assignee} ({len(items)} task(s))")
        drafts[assignee] = draft_email_for_assignee(
            assignee, items, meeting_summary, sender_name
        )

    return drafts


# ─────────────────────────────────────────────────────────────
#  SMTP send
# ─────────────────────────────────────────────────────────────

def send_email(
    to_address: str,
    subject: str,
    body: str,
    smtp_cfg: Optional[Dict] = None,
) -> Tuple[bool, str]:
    """
    Send a single email via SMTP.
    Returns (success: bool, message: str).
    """
    cfg = smtp_cfg or _get_smtp_config()

    ok, reason = smtp_config_is_valid()
    if not ok:
        return False, f"SMTP not configured: {reason}"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{cfg['from_name']} <{cfg['user']}>"
        msg["To"]      = to_address

        # Plain-text body
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], [to_address], msg.as_string())

        logger.info(f"Email sent to {to_address}")
        return True, f"Email sent to {to_address}"

    except smtplib.SMTPAuthenticationError:
        msg = "Authentication failed. Check SMTP_USER and SMTP_PASSWORD (use an App Password for Gmail)."
        logger.error(msg)
        return False, msg
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return False, f"SMTP error: {e}"
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        return False, f"Unexpected error: {e}"


def send_follow_up_emails(
    roster: Dict[str, str],          # { assignee_name: email_address }
    drafts: Dict[str, str],          # { assignee_name: email_body }
    meeting_title: str = "Our Recent Meeting",
    smtp_cfg: Optional[Dict] = None,
) -> Dict[str, Tuple[bool, str]]:
    """
    Send follow-up emails to all assignees in roster.
    Only sends if assignee has a draft AND a valid email address.

    Returns { assignee_name: (success, message) }
    """
    results: Dict[str, Tuple[bool, str]] = {}
    subject = f"Action Items from {meeting_title}"

    for assignee, email_addr in roster.items():
        if not email_addr or "@" not in email_addr:
            results[assignee] = (False, "No valid email address provided")
            continue

        body = drafts.get(assignee)
        if not body:
            results[assignee] = (False, "No email draft found for this assignee")
            continue

        success, msg = send_email(email_addr, subject, body, smtp_cfg)
        results[assignee] = (success, msg)

    return results
