"""Database persistence layer for GitQuest using Python's built-in SQLite.

Provides connection management, transactional helpers, and idempotent schema
initialization for user profiles, quests, completions, hint purchases, and XP ledgers.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
import sqlite3
from typing import Generator, Optional

DEFAULT_DB_FILENAME = "gitquest.db"
DEMO_USER_ID = "demo_user"
DEMO_USERNAME = "Demo Developer"


def get_default_db_path() -> str:
    """Return the configured or default SQLite database file path."""
    return os.getenv("GITQUEST_DB_PATH", DEFAULT_DB_FILENAME)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db_connection(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Provide a read-ready SQLite connection context manager with foreign keys enabled."""
    path = db_path or get_default_db_path()
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_transaction(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional SQLite connection context manager.

    Commits on clean block exit, rolls back on exception, and ensures foreign keys are enforced.
    """
    path = db_path or get_default_db_path()
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables idempotently and ensure the stable demo profile exists."""
    path = db_path or get_default_db_path()

    schema_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        earned_xp INTEGER NOT NULL DEFAULT 0 CHECK(earned_xp >= 0),
        consistency_score REAL NOT NULL DEFAULT 100.0 CHECK(consistency_score >= 0.0 AND consistency_score <= 100.0),
        last_eligible_activity_at TEXT NOT NULL,
        last_decay_applied_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS quests (
        quest_id TEXT PRIMARY KEY,
        repo TEXT NOT NULL,
        issue_number INTEGER NOT NULL,
        stage TEXT NOT NULL CHECK(stage IN ('A', 'B')),
        title TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        base_xp INTEGER NOT NULL DEFAULT 0,
        raw_payload TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS quest_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        quest_id TEXT NOT NULL REFERENCES quests(quest_id) ON DELETE CASCADE,
        stage TEXT NOT NULL CHECK(stage IN ('A', 'B')),
        awarded_xp INTEGER NOT NULL CHECK(awarded_xp >= 0),
        completed_at TEXT NOT NULL,
        UNIQUE(user_id, quest_id)
    );

    CREATE TABLE IF NOT EXISTS hint_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        quest_id TEXT NOT NULL REFERENCES quests(quest_id) ON DELETE CASCADE,
        hint_tier INTEGER NOT NULL CHECK(hint_tier IN (1, 2, 3)),
        xp_cost INTEGER NOT NULL CHECK(xp_cost >= 0),
        purchased_at TEXT NOT NULL,
        UNIQUE(user_id, quest_id, hint_tier)
    );

    CREATE TABLE IF NOT EXISTS xp_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        amount INTEGER NOT NULL,
        balance_after INTEGER NOT NULL CHECK(balance_after >= 0),
        action_type TEXT NOT NULL,
        reference_id TEXT,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_completions_user_stage ON quest_completions(user_id, stage);
    CREATE INDEX IF NOT EXISTS idx_hints_user_quest ON hint_purchases(user_id, quest_id);
    CREATE INDEX IF NOT EXISTS idx_transactions_user ON xp_transactions(user_id, created_at);
    """

    with get_db_transaction(path) as conn:
        conn.executescript(schema_sql)

        # Migrate raw_payload if upgrading existing database
        try:
            conn.execute("ALTER TABLE quests ADD COLUMN raw_payload TEXT;")
        except sqlite3.OperationalError:
            pass

        # Seed default demo user idempotently if not present
        now_iso = utc_now_iso()
        conn.execute(
            """
            INSERT OR IGNORE INTO users (
                id, username, earned_xp, consistency_score,
                last_eligible_activity_at, last_decay_applied_at, created_at
            ) VALUES (?, ?, 0, 100.0, ?, ?, ?)
            """,
            (DEMO_USER_ID, DEMO_USERNAME, now_iso, now_iso, now_iso),
        )
