"""Automated test suite for GitQuest SQLite persistence and gamification core.

Verifies:
- Idempotent database initialization.
- Server-authoritative XP awards and ledger consistency.
- Prevention of duplicate quest completion rewards.
- Hint purchases, balance checks, and double-charge prevention.
- Check constraints preventing negative XP balances.
- Stage B unlock threshold boundary conditions (XP AND Stage A count).
- Consistency score 48-hour grace period, non-repeating inactive-day decay, and zero floor.
- Data persistence across connection closures.
- Atomic rollback of failed operations without partial state leakage.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import os
import sqlite3
import tempfile
import unittest

from database import (
    DEMO_USER_ID,
    get_db_connection,
    get_db_transaction,
    init_db,
)
from gamification import (
    DEFAULT_CONFIG,
    DuplicateHintPurchaseError,
    DuplicateQuestCompletionError,
    GamificationConfig,
    InsufficientXPError,
    InvalidHintTierError,
    apply_consistency_decay,
    award_quest_completion,
    get_unlocked_hints,
    get_user_profile,
    get_xp_transactions,
    is_hint_unlocked,
    purchase_hint,
    record_quest,
)


class TestGamificationPersistence(unittest.TestCase):
    """Unit tests for SQLite persistence and gamification business logic."""

    def setUp(self):
        # Create a unique temporary database file for each test
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()

        # Initialize the database
        init_db(self.db_path)

        # Baseline config: 50 XP for Stage A, 200 XP threshold, 3 Stage A quests
        self.config = GamificationConfig()

    def tearDown(self):
        # Clean up temporary database file
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_database_initialization_idempotent(self):
        """Verify calling init_db multiple times is safe and preserves data."""
        # Record a quest and award completion
        record_quest("q_init_test", "org/repo", 1, "A", "Title", db_path=self.db_path)
        award_quest_completion("q_init_test", "A", db_path=self.db_path, config=self.config)

        # Re-run init_db twice
        init_db(self.db_path)
        init_db(self.db_path)

        profile = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(profile["earned_xp"], 50)
        self.assertEqual(profile["stage_a_completed_count"], 1)

    def test_xp_award_and_ledger_consistency(self):
        """Verify awarding XP updates balance and records matching audit ledger entry."""
        res = award_quest_completion("quest_101", "A", db_path=self.db_path, config=self.config)
        self.assertEqual(res["awarded_xp"], 50)
        self.assertEqual(res["new_balance"], 50)

        profile = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(profile["earned_xp"], 50)

        txs = get_xp_transactions(db_path=self.db_path)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0]["amount"], 50)
        self.assertEqual(txs[0]["balance_after"], 50)
        self.assertEqual(txs[0]["action_type"], "quest_completion")
        self.assertEqual(txs[0]["reference_id"], "quest_101")

    def test_duplicate_quest_completion_prevented(self):
        """Verify completing the same quest twice raises error and denies duplicate XP."""
        award_quest_completion("quest_dup", "A", db_path=self.db_path, config=self.config)

        with self.assertRaises(DuplicateQuestCompletionError):
            award_quest_completion("quest_dup", "A", db_path=self.db_path, config=self.config)

        profile = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(profile["earned_xp"], 50)  # Still 50, not 100

        txs = get_xp_transactions(db_path=self.db_path)
        self.assertEqual(len(txs), 1)

    def test_hint_purchase_and_insufficient_xp(self):
        """Verify purchasing a hint with insufficient XP is rejected without deductions."""
        # User starts with 0 XP; Tier 1 costs 10 XP
        with self.assertRaises(InsufficientXPError):
            purchase_hint("quest_hint_test", 1, db_path=self.db_path, config=self.config)

        profile = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(profile["earned_xp"], 0)
        self.assertFalse(is_hint_unlocked("quest_hint_test", 1, db_path=self.db_path))

    def test_hint_purchase_success_and_ledger(self):
        """Verify successful hint purchase deducts correct XP and writes negative ledger entry."""
        # Award 50 XP first
        award_quest_completion("q1", "A", db_path=self.db_path, config=self.config)

        # Purchase Tier 1 (10 XP)
        res = purchase_hint("q_target", 1, db_path=self.db_path, config=self.config)
        self.assertEqual(res["xp_deducted"], 10)
        self.assertEqual(res["balance"], 40)
        self.assertFalse(res["already_purchased"])

        self.assertTrue(is_hint_unlocked("q_target", 1, db_path=self.db_path))
        self.assertEqual(get_unlocked_hints("q_target", db_path=self.db_path), [1])

        profile = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(profile["earned_xp"], 40)

        txs = get_xp_transactions(db_path=self.db_path)
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0]["action_type"], "hint_purchase")
        self.assertEqual(txs[0]["amount"], -10)
        self.assertEqual(txs[0]["balance_after"], 40)

    def test_duplicate_hint_purchase_does_not_charge_twice(self):
        """Verify repeat hint purchase returns existing unlock without double-charging."""
        award_quest_completion("q_stage_a", "A", db_path=self.db_path, config=self.config)

        # Purchase tier 2 (costs 25 XP; balance becomes 25 XP)
        res1 = purchase_hint("q_shared", 2, db_path=self.db_path, config=self.config)
        self.assertEqual(res1["xp_deducted"], 25)
        self.assertEqual(res1["balance"], 25)

        # Re-purchase same tier (free re-access)
        res2 = purchase_hint("q_shared", 2, db_path=self.db_path, config=self.config)
        self.assertEqual(res2["xp_deducted"], 0)
        self.assertTrue(res2["already_purchased"])
        self.assertEqual(res2["balance"], 25)

        # Ensure balance is still 25, not 0
        profile = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(profile["earned_xp"], 25)

    def test_no_negative_xp_enforced_by_db_constraint(self):
        """Verify SQLite CHECK constraint rejects any attempt to store negative earned_xp."""
        with self.assertRaises(sqlite3.IntegrityError):
            with get_db_transaction(self.db_path) as conn:
                conn.execute("UPDATE users SET earned_xp = -10 WHERE id = ?", (DEMO_USER_ID,))

    def test_unlock_threshold_boundary_conditions(self):
        """Verify Stage B unlocks ONLY when BOTH XP threshold AND Stage A count are satisfied."""
        # Threshold: 200 XP and 3 completed Stage A quests

        # Scenario 1: 0 completions, 0 XP -> Locked
        p1 = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertFalse(p1["stage_b_unlocked"])

        # Scenario 2: 1 completion (50 XP, 1 count) -> Locked
        award_quest_completion("qa_1", "A", db_path=self.db_path, config=self.config)
        p2 = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertFalse(p2["stage_b_unlocked"])

        # Scenario 3: 2 completions (100 XP, 2 count) -> Locked
        award_quest_completion("qa_2", "A", db_path=self.db_path, config=self.config)
        p3 = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertFalse(p3["stage_b_unlocked"])

        # Scenario 4: 3 completions (150 XP, 3 count) -> Count met, but XP (150 < 200) not met -> Locked
        award_quest_completion("qa_3", "A", db_path=self.db_path, config=self.config)
        p4 = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(p4["stage_a_completed_count"], 3)
        self.assertEqual(p4["earned_xp"], 150)
        self.assertFalse(p4["stage_b_unlocked"])

        # Scenario 5: 4 completions (200 XP, 4 count) -> Both XP >= 200 and count >= 3 -> UNLOCKED!
        award_quest_completion("qa_4", "A", db_path=self.db_path, config=self.config)
        p5 = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(p5["earned_xp"], 200)
        self.assertEqual(p5["stage_a_completed_count"], 4)
        self.assertTrue(p5["stage_b_unlocked"])

        # Scenario 6: User unlocks hints and drops below 200 XP (e.g. 200 - 10 = 190 XP) -> Locked again!
        purchase_hint("qa_4", 1, db_path=self.db_path, config=self.config)
        p6 = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(p6["earned_xp"], 190)
        self.assertEqual(p6["stage_a_completed_count"], 4)
        self.assertFalse(p6["stage_b_unlocked"])

    def test_consistency_grace_period_and_decay(self):
        """Verify 48h grace period, 5 pt decay per additional inactive day, non-repetition, and 0 floor."""
        base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Activity at base_time
        award_quest_completion("q_init", "A", db_path=self.db_path, config=self.config, as_of_time=base_time)

        # 1. Check during grace period: at 24 hours -> 100.0 (no decay)
        t_24h = base_time + timedelta(hours=24)
        s_24h = apply_consistency_decay(as_of_time=t_24h, db_path=self.db_path, config=self.config)
        self.assertEqual(s_24h, 100.0)

        # 2. Check at boundary of grace period: exactly 48 hours -> 100.0 (no decay)
        t_48h = base_time + timedelta(hours=48)
        s_48h = apply_consistency_decay(as_of_time=t_48h, db_path=self.db_path, config=self.config)
        self.assertEqual(s_48h, 100.0)

        # 3. Check at 50 hours (only 2 hours past grace period, not full additional day) -> 100.0
        t_50h = base_time + timedelta(hours=50)
        s_50h = apply_consistency_decay(as_of_time=t_50h, db_path=self.db_path, config=self.config)
        self.assertEqual(s_50h, 100.0)

        # 4. Check at 72 hours (exactly 1 full additional day beyond 48h grace) -> 95.0
        t_72h = base_time + timedelta(hours=72)
        s_72h = apply_consistency_decay(as_of_time=t_72h, db_path=self.db_path, config=self.config)
        self.assertEqual(s_72h, 95.0)

        # 5. Non-repeating penalty check: repeat calls within same day (73h, 75h) apply NO additional decay
        t_73h = base_time + timedelta(hours=73)
        s_73h = apply_consistency_decay(as_of_time=t_73h, db_path=self.db_path, config=self.config)
        self.assertEqual(s_73h, 95.0)

        t_75h = base_time + timedelta(hours=75)
        s_75h = apply_consistency_decay(as_of_time=t_75h, db_path=self.db_path, config=self.config)
        self.assertEqual(s_75h, 95.0)

        # 6. Check at 96 hours (2 full additional days beyond grace) -> 90.0
        t_96h = base_time + timedelta(hours=96)
        s_96h = apply_consistency_decay(as_of_time=t_96h, db_path=self.db_path, config=self.config)
        self.assertEqual(s_96h, 90.0)

        # 7. Check floor at zero: at 30 days of inactivity (100 - (28 * 5) = -40 => 0.0)
        t_30d = base_time + timedelta(days=30)
        s_30d = apply_consistency_decay(as_of_time=t_30d, db_path=self.db_path, config=self.config)
        self.assertEqual(s_30d, 0.0)

    def test_persistence_after_reopening_database(self):
        """Verify data remains intact after closing and reopening database connection."""
        award_quest_completion("q_persist", "A", db_path=self.db_path, config=self.config)
        purchase_hint("q_persist", 1, db_path=self.db_path, config=self.config)

        # Open fresh connection on same path
        with get_db_connection(self.db_path) as conn:
            user = conn.execute("SELECT earned_xp FROM users WHERE id = ?", (DEMO_USER_ID,)).fetchone()
            self.assertEqual(int(user["earned_xp"]), 40)

            hint = conn.execute(
                "SELECT hint_tier, xp_cost FROM hint_purchases WHERE quest_id = ?",
                ("q_persist",),
            ).fetchone()
            self.assertEqual(int(hint["hint_tier"]), 1)
            self.assertEqual(int(hint["xp_cost"]), 10)

            txs = conn.execute("SELECT COUNT(*) as cnt FROM xp_transactions").fetchone()
            self.assertEqual(int(txs["cnt"]), 2)

    def test_failed_operations_leave_no_partial_updates(self):
        """Verify that transactions roll back on failure without leaving partial state."""
        # Award 50 XP
        award_quest_completion("q_atomic", "A", db_path=self.db_path, config=self.config)

        # Simulate a transaction that crashes midway
        try:
            with get_db_transaction(self.db_path) as conn:
                conn.execute(
                    "UPDATE users SET earned_xp = earned_xp + 100 WHERE id = ?",
                    (DEMO_USER_ID,),
                )
                # Intentionally trigger an error
                raise RuntimeError("Simulated crash before commit")
        except RuntimeError:
            pass

        # Verify balance rolled back to 50
        profile = get_user_profile(db_path=self.db_path, config=self.config)
        self.assertEqual(profile["earned_xp"], 50)


if __name__ == "__main__":
    unittest.main()
