"""
contact_book.py — Persistent name→email store for the Follow-up Agent.

Stores known speaker name → email mappings in a local SQLite database so
they are remembered across meetings. Provides fuzzy matching so that
"Priya Sharma" and "Priya" can be linked to the same contact.
"""

import sqlite3
import logging
import os
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Store the DB next to job_results so it persists with the project
_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "contact_book.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    """Create the contacts table if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT NOT NULL UNIQUE COLLATE NOCASE,
                email    TEXT NOT NULL,
                updated  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


# Initialise on import
_init_db()


# ─────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────

def get_email(name: str) -> Optional[str]:
    """
    Return the stored email for `name`, or None if not found.
    Tries exact match first, then first-name fuzzy match.
    """
    if not name or name.strip().lower() == "unassigned":
        return None

    name = name.strip()
    with _get_conn() as conn:
        # 1. Exact match (case-insensitive via COLLATE NOCASE)
        row = conn.execute(
            "SELECT email FROM contacts WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["email"]

        # 2. Fuzzy: stored name starts with the query first name
        first = name.split()[0]
        row = conn.execute(
            "SELECT email FROM contacts WHERE name LIKE ? LIMIT 1",
            (f"{first}%",)
        ).fetchone()
        if row:
            return row["email"]

    return None


def save_email(name: str, email: str):
    """Persist or update a name→email mapping."""
    if not name or not email:
        return
    name = name.strip()
    email = email.strip()
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO contacts (name, email, updated)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                email   = excluded.email,
                updated = CURRENT_TIMESTAMP
        """, (name, email))
        conn.commit()
    logger.info(f"contact_book: saved {name!r} → {email!r}")


def bulk_save(mapping: Dict[str, str]):
    """Save multiple name→email pairs at once."""
    for name, email in mapping.items():
        if email and email.strip():
            save_email(name, email)


def get_all_contacts() -> List[Tuple[str, str]]:
    """Return all stored (name, email) pairs, sorted by name."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT name, email FROM contacts ORDER BY name"
        ).fetchall()
    return [(r["name"], r["email"]) for r in rows]


def prefill_roster(assignees: List[str]) -> Dict[str, str]:
    """
    Given a list of assignee names from action items, return a dict of
    name → pre-filled email (empty string if unknown).
    """
    return {name: (get_email(name) or "") for name in assignees if name and name.lower() != "unassigned"}
