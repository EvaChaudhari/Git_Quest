"""Gamification and persistence service for GitQuest.

Enforces server-authoritative earned XP, progressive hint unlocking, Stage B
threshold verification, XP ledger auditing, and separate habit consistency scoring
with a 48-hour grace period and inactive-day decay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import json
import os
import sqlite3
from typing import Any, Optional

from database import (
    DEMO_USER_ID,
    DEMO_USERNAME,
    get_db_connection,
    get_db_transaction,
    init_db,
    utc_now_iso,
)


# ==============================================================================
# Centralized Configuration
# ==============================================================================

@dataclass(frozen=True)
class GamificationConfig:
    """Centralized configuration for GitQuest rewards, hint costs, and thresholds."""

    # XP Awards (Server Authoritative)
    stage_a_completion_xp: int = 50
    stage_b_completion_xp: int = 100

    # Hint Costs (Server Authoritative per Tier)
    hint_tier_costs: dict[int, int] = field(
        default_factory=lambda: {
            1: int(os.getenv("GITQUEST_HINT_COST_TIER_1", "10")),
            2: int(os.getenv("GITQUEST_HINT_COST_TIER_2", "25")),
            3: int(os.getenv("GITQUEST_HINT_COST_TIER_3", "50")),
        }
    )

    # Stage B Unlock Requirements (Both must be satisfied)
    stage_b_unlock_xp_threshold: int = int(os.getenv("GITQUEST_STAGE_B_UNLOCK_XP", "200"))
    stage_b_unlock_stage_a_completions: int = int(
        os.getenv("GITQUEST_STAGE_B_UNLOCK_STAGE_A_COUNT", "3")
    )

    # Consistency Score Parameters
    initial_consistency_score: float = 100.0
    consistency_grace_period_hours: float = float(
        os.getenv("GITQUEST_CONSISTENCY_GRACE_HOURS", "48.0")
    )
    consistency_decay_points_per_day: float = float(
        os.getenv("GITQUEST_CONSISTENCY_DECAY_PER_DAY", "5.0")
    )

    demo_user_id: str = DEMO_USER_ID
    demo_username: str = DEMO_USERNAME


DEFAULT_CONFIG = GamificationConfig()


# ==============================================================================
# Domain Exceptions
# ==============================================================================

class GamificationError(Exception):
    """Base exception for gamification domain errors."""


class UserNotFoundError(GamificationError):
    """Raised when a user profile cannot be located."""


class QuestNotFoundError(GamificationError):
    """Raised when a referenced quest is not found."""


class DuplicateQuestCompletionError(GamificationError):
    """Raised when a user attempts to complete a quest more than once for reward."""


class InsufficientXPError(GamificationError):
    """Raised when an operation requires more XP than the user's available balance."""


class InvalidHintTierError(GamificationError):
    """Raised when an invalid hint tier is requested."""


class DuplicateHintPurchaseError(GamificationError):
    """Raised when a user attempts to re-purchase an already unlocked hint tier."""


# ==============================================================================
# Helpers
# ==============================================================================

def _parse_iso(timestamp_str: str) -> datetime:
    """Parse an ISO 8601 string into an aware UTC datetime object."""
    dt = datetime.fromisoformat(timestamp_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ensure_user_exists(conn: sqlite3.Connection, user_id: str, config: GamificationConfig) -> None:
    """Ensure the user record exists in the database."""
    now_iso = utc_now_iso()
    decay_start = (datetime.now(timezone.utc) + timedelta(hours=config.consistency_grace_period_hours)).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO users (
            id, username, earned_xp, consistency_score,
            last_eligible_activity_at, last_decay_applied_at, created_at
        ) VALUES (?, ?, 0, ?, ?, ?, ?)
        """,
        (
            user_id,
            config.demo_username if user_id == config.demo_user_id else user_id,
            config.initial_consistency_score,
            now_iso,
            decay_start,
            now_iso,
        ),
    )


# ==============================================================================
# Gamification Core Services
# ==============================================================================

def record_quest(
    quest_id: str,
    repo: str,
    issue_number: int,
    stage: str,
    title: str,
    difficulty: str = "Novice",
    base_xp: int = 0,
    raw_payload: Optional[dict[str, Any] | str] = None,
    db_path: Optional[str] = None,
) -> None:
    """Idempotently insert or update a quest record in the database."""
    if stage not in ("A", "B"):
        raise ValueError("Quest stage must be 'A' or 'B'.")

    payload_str: Optional[str] = None
    if raw_payload is not None:
        payload_str = json.dumps(raw_payload) if isinstance(raw_payload, dict) else str(raw_payload)

    now_iso = utc_now_iso()
    with get_db_transaction(db_path) as conn:
        conn.execute(
            """
            INSERT INTO quests (quest_id, repo, issue_number, stage, title, difficulty, base_xp, raw_payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(quest_id) DO UPDATE SET
                repo = excluded.repo,
                issue_number = excluded.issue_number,
                stage = excluded.stage,
                title = excluded.title,
                difficulty = excluded.difficulty,
                base_xp = excluded.base_xp,
                raw_payload = COALESCE(excluded.raw_payload, quests.raw_payload)
            """,
            (quest_id, repo, issue_number, stage, title, difficulty, base_xp, payload_str, now_iso),
        )


def get_quest(quest_id: str, db_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Retrieve stored quest details including parsed raw_payload if available."""
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT quest_id, repo, issue_number, stage, title, difficulty, base_xp, raw_payload, created_at FROM quests WHERE quest_id = ?",
            (quest_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("raw_payload"):
            try:
                data["parsed_payload"] = json.loads(data["raw_payload"])
            except Exception:
                data["parsed_payload"] = None
        else:
            data["parsed_payload"] = None
        return data


def apply_consistency_decay(
    user_id: str = DEMO_USER_ID,
    as_of_time: Optional[datetime] = None,
    db_path: Optional[str] = None,
    config: GamificationConfig = DEFAULT_CONFIG,
) -> float:
    """Evaluate and apply inactivity consistency decay without repeating penalties.

    Grace period: 48 hours from last eligible participation.
    Decay: 5.0 points per additional full inactive day beyond grace period, floored at 0.0.
    """
    now = as_of_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(timezone.utc)

    with get_db_transaction(db_path) as conn:
        _ensure_user_exists(conn, user_id, config)

        row = conn.execute(
            "SELECT consistency_score, last_decay_applied_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if not row:
            raise UserNotFoundError(f"User '{user_id}' not found.")

        current_score = float(row["consistency_score"])
        last_decay_dt = _parse_iso(row["last_decay_applied_at"])

        # If current time is still within grace period, zero decay
        if now <= last_decay_dt:
            return current_score

        # Elapsed inactive time beyond grace period
        elapsed_seconds = (now - last_decay_dt).total_seconds()
        full_days = int(elapsed_seconds // 86400)

        if full_days > 0:
            penalty = full_days * config.consistency_decay_points_per_day
            new_score = max(0.0, current_score - penalty)
            new_decay_dt = last_decay_dt + timedelta(days=full_days)

            conn.execute(
                """
                UPDATE users
                SET consistency_score = ?, last_decay_applied_at = ?
                WHERE id = ?
                """,
                (new_score, new_decay_dt.isoformat(), user_id),
            )
            return new_score

        return current_score


def get_user_profile(
    user_id: str = DEMO_USER_ID,
    as_of_time: Optional[datetime] = None,
    db_path: Optional[str] = None,
    config: GamificationConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Retrieve full user profile with authoritative XP, consistency, and Stage B unlock status."""
    # Apply decay before reading state
    current_consistency = apply_consistency_decay(
        user_id=user_id, as_of_time=as_of_time, db_path=db_path, config=config
    )

    with get_db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise UserNotFoundError(f"User '{user_id}' not found.")

        earned_xp = int(row["earned_xp"])

        # Count completed Stage A quests
        stage_a_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM quest_completions WHERE user_id = ? AND stage = 'A'",
            (user_id,),
        ).fetchone()
        stage_a_count = int(stage_a_row["cnt"]) if stage_a_row else 0

        # Total completed quests
        total_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM quest_completions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total_completed = int(total_row["cnt"]) if total_row else 0

        # Check Stage B unlock conditions
        stage_b_unlocked = (
            earned_xp >= config.stage_b_unlock_xp_threshold
            and stage_a_count >= config.stage_b_unlock_stage_a_completions
        )

        return {
            "user_id": row["id"],
            "username": row["username"],
            "earned_xp": earned_xp,
            "consistency_score": current_consistency,
            "stage_b_unlocked": stage_b_unlocked,
            "stage_a_completed_count": stage_a_count,
            "total_completed_count": total_completed,
            "stage_b_thresholds": {
                "required_xp": config.stage_b_unlock_xp_threshold,
                "current_xp": earned_xp,
                "required_stage_a_quests": config.stage_b_unlock_stage_a_completions,
                "current_stage_a_quests": stage_a_count,
            },
            "last_eligible_activity_at": row["last_eligible_activity_at"],
            "created_at": row["created_at"],
        }


def award_quest_completion(
    quest_id: str,
    stage: str,
    user_id: str = DEMO_USER_ID,
    db_path: Optional[str] = None,
    config: GamificationConfig = DEFAULT_CONFIG,
    as_of_time: Optional[datetime] = None,
) -> dict[str, Any]:
    """Award authoritative completion XP in an atomic transaction and update activity timers.

    Prevents duplicate completions and ignores non-authoritative AI awards.
    """
    if stage not in ("A", "B"):
        raise ValueError("Quest stage must be 'A' or 'B'.")

    # Authoritative server-side reward
    awarded_xp = (
        config.stage_a_completion_xp if stage == "A" else config.stage_b_completion_xp
    )

    now = as_of_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(timezone.utc)
    now_iso = now.isoformat()
    new_decay_dt = (now + timedelta(hours=config.consistency_grace_period_hours)).isoformat()

    with get_db_transaction(db_path) as conn:
        _ensure_user_exists(conn, user_id, config)

        # Check if quest exists; if not auto-stub minimal entry
        quest_row = conn.execute(
            "SELECT stage, title FROM quests WHERE quest_id = ?", (quest_id,)
        ).fetchone()
        if not quest_row:
            conn.execute(
                """
                INSERT INTO quests (quest_id, repo, issue_number, stage, title, difficulty, base_xp, created_at)
                VALUES (?, 'unknown/repo', 0, ?, 'Untitled Quest', 'Novice', ?, ?)
                """,
                (quest_id, stage, awarded_xp, now_iso),
            )

        # Prevent duplicate completions
        existing = conn.execute(
            "SELECT id FROM quest_completions WHERE user_id = ? AND quest_id = ?",
            (user_id, quest_id),
        ).fetchone()
        if existing:
            raise DuplicateQuestCompletionError(
                f"Quest '{quest_id}' has already been completed by user '{user_id}'."
            )

        # Record completion
        conn.execute(
            """
            INSERT INTO quest_completions (user_id, quest_id, stage, awarded_xp, completed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, quest_id, stage, awarded_xp, now_iso),
        )

        # Read balance
        user_row = conn.execute("SELECT earned_xp FROM users WHERE id = ?", (user_id,)).fetchone()
        new_balance = int(user_row["earned_xp"]) + awarded_xp

        # Update user balance and refresh grace period timer
        conn.execute(
            """
            UPDATE users
            SET earned_xp = ?,
                last_eligible_activity_at = ?,
                last_decay_applied_at = ?
            WHERE id = ?
            """,
            (new_balance, now_iso, new_decay_dt, user_id),
        )

        # Record in audit ledger
        conn.execute(
            """
            INSERT INTO xp_transactions (
                user_id, amount, balance_after, action_type, reference_id, description, created_at
            ) VALUES (?, ?, ?, 'quest_completion', ?, ?, ?)
            """,
            (
                user_id,
                awarded_xp,
                new_balance,
                quest_id,
                f"Completed Stage {stage} quest '{quest_id}'",
                now_iso,
            ),
        )

    # Return fresh profile stats
    profile = get_user_profile(user_id=user_id, as_of_time=now, db_path=db_path, config=config)
    return {
        "user_id": user_id,
        "quest_id": quest_id,
        "stage": stage,
        "awarded_xp": awarded_xp,
        "new_balance": new_balance,
        "balance": new_balance,
        "consistency_score": profile["consistency_score"],
        "stage_b_unlocked": profile["stage_b_unlocked"],
    }


def purchase_hint(
    quest_id: str,
    hint_tier: int,
    user_id: str = DEMO_USER_ID,
    db_path: Optional[str] = None,
    config: GamificationConfig = DEFAULT_CONFIG,
    as_of_time: Optional[datetime] = None,
) -> dict[str, Any]:
    """Atomically purchase a hint tier, deducting XP and enforcing uniqueness and solvency."""
    if hint_tier not in (1, 2, 3):
        raise InvalidHintTierError(f"Invalid hint tier {hint_tier}. Must be 1, 2, or 3.")

    cost = config.hint_tier_costs.get(hint_tier, 10)
    now = as_of_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(timezone.utc)
    now_iso = now.isoformat()

    with get_db_transaction(db_path) as conn:
        _ensure_user_exists(conn, user_id, config)

        # Check if quest exists; auto-stub if missing
        quest_row = conn.execute("SELECT quest_id FROM quests WHERE quest_id = ?", (quest_id,)).fetchone()
        if not quest_row:
            conn.execute(
                """
                INSERT INTO quests (quest_id, repo, issue_number, stage, title, difficulty, base_xp, created_at)
                VALUES (?, 'unknown/repo', 0, 'B', 'Challenge Quest', 'Adept', 0, ?)
                """,
                (quest_id, now_iso),
            )

        # Check if already unlocked (Idempotency / Prevent double-charging)
        existing = conn.execute(
            "SELECT id, xp_cost FROM hint_purchases WHERE user_id = ? AND quest_id = ? AND hint_tier = ?",
            (user_id, quest_id, hint_tier),
        ).fetchone()
        if existing:
            # Re-accessing an already purchased hint is free
            user_row = conn.execute("SELECT earned_xp FROM users WHERE id = ?", (user_id,)).fetchone()
            return {
                "user_id": user_id,
                "quest_id": quest_id,
                "hint_tier": hint_tier,
                "xp_deducted": 0,
                "already_purchased": True,
                "balance": int(user_row["earned_xp"]),
            }

        # Check balance
        user_row = conn.execute("SELECT earned_xp FROM users WHERE id = ?", (user_id,)).fetchone()
        current_balance = int(user_row["earned_xp"])
        if current_balance < cost:
            raise InsufficientXPError(
                f"Insufficient XP: hint tier {hint_tier} costs {cost} XP, but current balance is {current_balance} XP."
            )

        new_balance = current_balance - cost

        # Deduct XP atomically
        conn.execute(
            "UPDATE users SET earned_xp = ? WHERE id = ? AND earned_xp >= ?",
            (new_balance, user_id, cost),
        )

        # Record hint purchase
        conn.execute(
            """
            INSERT INTO hint_purchases (user_id, quest_id, hint_tier, xp_cost, purchased_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, quest_id, hint_tier, cost, now_iso),
        )

        # Record in ledger
        conn.execute(
            """
            INSERT INTO xp_transactions (
                user_id, amount, balance_after, action_type, reference_id, description, created_at
            ) VALUES (?, ?, ?, 'hint_purchase', ?, ?, ?)
            """,
            (
                user_id,
                -cost,
                new_balance,
                quest_id,
                f"Purchased tier {hint_tier} hint for quest '{quest_id}'",
                now_iso,
            ),
        )

    return {
        "user_id": user_id,
        "quest_id": quest_id,
        "hint_tier": hint_tier,
        "xp_deducted": cost,
        "already_purchased": False,
        "balance": new_balance,
    }


def is_hint_unlocked(
    quest_id: str,
    hint_tier: int,
    user_id: str = DEMO_USER_ID,
    db_path: Optional[str] = None,
) -> bool:
    """Check if a specific hint tier has been unlocked for a quest by the user."""
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM hint_purchases WHERE user_id = ? AND quest_id = ? AND hint_tier = ?",
            (user_id, quest_id, hint_tier),
        ).fetchone()
        return row is not None


def get_unlocked_hints(
    quest_id: str,
    user_id: str = DEMO_USER_ID,
    db_path: Optional[str] = None,
) -> list[int]:
    """Return all unlocked hint tiers for a specific quest."""
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT hint_tier FROM hint_purchases WHERE user_id = ? AND quest_id = ? ORDER BY hint_tier ASC",
            (user_id, quest_id),
        ).fetchall()
        return [int(r["hint_tier"]) for r in rows]


def get_xp_transactions(
    user_id: str = DEMO_USER_ID,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Retrieve audit ledger transactions for a user."""
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, amount, balance_after, action_type, reference_id, description, created_at
            FROM xp_transactions
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
