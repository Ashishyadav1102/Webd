"""
topic_generator.py
Generates and queues video topic ideas for a given niche using a free LLM API.
Topics are stored in a local SQLite database to avoid repetition.
"""

import sqlite3
import logging
import os
from datetime import datetime
from llm_client import get_llm_client

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "topics.db")


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS topics (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            niche     TEXT    NOT NULL,
            topic     TEXT    NOT NULL,
            used      INTEGER NOT NULL DEFAULT 0,
            created_at TEXT   NOT NULL
        )
        """
    )
    conn.commit()


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    _init_db(conn)
    return conn


def generate_topics(niche: str, llm_config: dict, count: int = 10) -> list[str]:
    """Ask the LLM to generate *count* unique topic ideas for the given niche."""
    client = get_llm_client(llm_config)
    prompt = (
        f"Generate {count} unique, engaging YouTube video topic ideas for the '{niche}' niche. "
        "Each topic should be specific, curiosity-inducing, and suitable for a faceless YouTube channel. "
        "Output ONLY the numbered list of topics, nothing else. Example format:\n"
        "1. Topic one\n2. Topic two\n..."
    )
    response = client.complete(prompt)
    topics = []
    for line in response.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading numbers/punctuation like "1. " or "1) "
        if line[0].isdigit():
            parts = line.split(".", 1) if "." in line else line.split(")", 1)
            if len(parts) == 2:
                line = parts[1].strip()
        if line:
            topics.append(line)
    return topics[:count]


def save_topics(niche: str, topics: list[str]) -> None:
    """Persist topics to the SQLite database, skipping duplicates."""
    conn = _get_connection()
    now = datetime.utcnow().isoformat()
    inserted = 0
    for topic in topics:
        existing = conn.execute(
            "SELECT id FROM topics WHERE niche = ? AND topic = ?", (niche, topic)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO topics (niche, topic, used, created_at) VALUES (?, ?, 0, ?)",
                (niche, topic, now),
            )
            inserted += 1
    conn.commit()
    conn.close()
    logger.info("Saved %d new topics for niche '%s'", inserted, niche)


def get_next_topic(niche: str) -> str | None:
    """Return the oldest unused topic for the given niche and mark it used."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT id, topic FROM topics WHERE niche = ? AND used = 0 ORDER BY id ASC LIMIT 1",
        (niche,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    topic_id, topic = row
    conn.execute("UPDATE topics SET used = 1 WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()
    logger.info("Using topic (id=%d): %s", topic_id, topic)
    return topic


def ensure_topics(niche: str, llm_config: dict, min_count: int = 5) -> None:
    """Generate and save new topics if the unused queue is running low."""
    conn = _get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM topics WHERE niche = ? AND used = 0", (niche,)
    ).fetchone()[0]
    conn.close()
    if count < min_count:
        logger.info(
            "Only %d unused topics left for '%s'. Generating more…", count, niche
        )
        new_topics = generate_topics(niche, llm_config, count=10)
        save_topics(niche, new_topics)
