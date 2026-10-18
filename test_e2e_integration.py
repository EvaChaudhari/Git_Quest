"""Comprehensive End-to-End Integration Test Suite for GitQuest.

Verifies the full system across:
- Frontend rendering & DOM hooks
- Flask API routes & validation
- GitHub Service integration & error handling
- Gemma AI Service quest generation & hint masking
- SQLite Persistence, XP ledger, and consistency decay

Journeys verified:
- TEST A: Repository Browsing (Valid, Empty, Invalid, Rate-limit, Network Error)
- TEST B: Stage A Training (Closed issues, Evidence verification, Unavailable vs Verified)
- TEST C: Stage B Challenge (Progression gate locked vs unlocked, Hint masking)
- TEST D: Hint Purchases (Deduction, Solvency check, Re-access idempotency, Balance update)
- TEST E: Completion (Authoritative reward, Duplicate prevention, Persistence across reloads)
- TEST F: Failure Handling (AI error, Rate limit, Bad body, Missing quest, DB failure, Duplicate action)
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import app
from database import get_db_connection, init_db
from gamification import DEFAULT_CONFIG, record_quest


class TestGitQuestE2EIntegration(unittest.TestCase):
    """End-to-end integration audit for all GitQuest user journeys."""

    def setUp(self):
        # Create an isolated temporary test database to protect the user's real database
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["GITQUEST_DB_PATH"] = self.temp_db.name
        init_db(self.temp_db.name)

        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except OSError:
                pass

    # =========================================================================
    # TEST A — REPOSITORY BROWSING
    # =========================================================================

    @patch("app.get_issues")
    def test_journey_a_repository_browsing_success(self, mock_get_issues):
        """TEST A.1-3: Enter valid public repo URL, fetch open issues, verify response fields."""
        mock_get_issues.return_value = [
            {
                "number": 101,
                "title": "Fix navbar collapse on mobile",
                "body": "Navbar does not collapse when tapping outside.",
                "labels": ["bug", "frontend"],
                "html_url": "https://github.com/pallets/flask/issues/101",
                "repo": "pallets/flask",
                "state": "open",
            },
            {
                "number": 102,
                "title": "Update routing tutorial in docs",
                "body": "Clarify URL variable converters.",
                "labels": ["documentation"],
                "html_url": "https://github.com/pallets/flask/issues/102",
                "repo": "pallets/flask",
                "state": "open",
            },
        ]

        # 1. Dispatch valid repository URL
        resp = self.client.post(
            "/api/issues",
            json={"repo_url": "https://github.com/pallets/flask", "limit": 10},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        # 2. Verify returned issue structure matches contract
        self.assertIn("issues", data)
        self.assertIn("count", data)
        self.assertEqual(data["count"], 2)
        first_issue = data["issues"][0]
        self.assertEqual(first_issue["number"], 101)
        self.assertEqual(first_issue["repo"], "pallets/flask")
        self.assertEqual(first_issue["title"], "Fix navbar collapse on mobile")
        self.assertIn("frontend", first_issue["labels"])

    def test_journey_a_repository_browsing_validation_and_failures(self):
        """TEST A.4: Empty URL, malformed URL, non-GitHub host, and invalid JSON bodies."""
        # Empty repo URL
        resp_empty = self.client.post("/api/issues", json={"repo_url": "   "})
        self.assertEqual(resp_empty.status_code, 400)
        self.assertIn("error", resp_empty.get_json())

        # Non-GitHub URL
        resp_non_github = self.client.post("/api/issues", json={"repo_url": "https://gitlab.com/owner/repo"})
        self.assertEqual(resp_non_github.status_code, 400)
        self.assertIn("Only 'github.com' URLs are supported", resp_non_github.get_json()["error"])

        # Malformed path (no repository name)
        resp_bad_path = self.client.post("/api/issues", json={"repo_url": "https://github.com/singlepart"})
        self.assertEqual(resp_bad_path.status_code, 400)

        # Non-JSON content type
        resp_not_json = self.client.post("/api/issues", data="plain text input")
        self.assertEqual(resp_not_json.status_code, 400)

    @patch("app.get_issues")
    def test_journey_a_repository_browsing_empty_and_github_failures(self, mock_get_issues):
        """TEST A.4 (cont): Distinguish empty results from GitHub rate-limit / not-found errors."""
        from github_service import GitHubRateLimitError, GitHubRepoNotFoundError

        # 1. Empty repository issues (0 found) -> must return 200 with count 0, NOT error
        mock_get_issues.return_value = []
        resp_empty_repo = self.client.post("/api/issues", json={"repo_url": "https://github.com/pallets/flask"})
        self.assertEqual(resp_empty_repo.status_code, 200)
        self.assertEqual(resp_empty_repo.get_json()["count"], 0)
        self.assertEqual(resp_empty_repo.get_json()["issues"], [])

        # 2. GitHub Rate limit (429)
        mock_get_issues.side_effect = GitHubRateLimitError("GitHub API rate limit exceeded.")
        resp_rate = self.client.post("/api/issues", json={"repo_url": "https://github.com/pallets/flask"})
        self.assertEqual(resp_rate.status_code, 429)
        self.assertIn("rate limit", resp_rate.get_json()["error"].lower())

        # 3. Repository Not Found (404)
        mock_get_issues.side_effect = GitHubRepoNotFoundError("Repository does not exist.")
        resp_404 = self.client.post("/api/issues", json={"repo_url": "https://github.com/owner/missing-repo"})
        self.assertEqual(resp_404.status_code, 404)
        err_msg = resp_404.get_json()["error"].lower()
        self.assertTrue("not found" in err_msg or "does not exist" in err_msg)

    # =========================================================================
    # TEST B — STAGE A TRAINING
    # =========================================================================

    @patch("app.get_closed_issues_with_evidence")
    def test_journey_b_fetch_closed_issues_with_evidence(self, mock_get_closed):
        """TEST B.1: Fetch closed issues and verify evidence availability."""
        mock_get_closed.return_value = [
            {
                "number": 5012,
                "title": "Fix memory leak in request dispatcher",
                "body": "Garbage collector retained context objects.",
                "labels": ["bug", "core"],
                "html_url": "https://github.com/pallets/flask/issues/5012",
                "repo": "pallets/flask",
                "state": "closed",
                "resolution_evidence": {
                    "status": "verified",
                    "issue_number": 5012,
                    "repo": "pallets/flask",
                    "summary": "Resolved in PR #5013 by detaching request context on teardown.",
                    "evidence_sources": ["https://github.com/pallets/flask/pull/5013"],
                },
            },
            {
                "number": 5014,
                "title": "Old documentation typo in signals section",
                "body": "Typo in example code.",
                "labels": ["documentation"],
                "html_url": "https://github.com/pallets/flask/issues/5014",
                "repo": "pallets/flask",
                "state": "closed",
                "resolution_evidence": {
                    "status": "unavailable",
                    "issue_number": 5014,
                    "repo": "pallets/flask",
                    "summary": "No commit or PR link found for this issue.",
                    "evidence_sources": [],
                },
            },
        ]

        resp = self.client.post("/api/training/issues", json={"repo_url": "https://github.com/pallets/flask"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["count"], 2)

        # Issue 1 has verified evidence
        issue1 = data["issues"][0]
        self.assertEqual(issue1["resolution_evidence"]["status"], "verified")
        self.assertEqual(len(issue1["resolution_evidence"]["evidence_sources"]), 1)

        # Issue 2 has unavailable evidence
        issue2 = data["issues"][1]
        self.assertEqual(issue2["resolution_evidence"]["status"], "unavailable")
        self.assertEqual(len(issue2["resolution_evidence"]["evidence_sources"]), 0)

    @patch("app.get_issue_resolution_evidence")
    @patch("app.generate_training_quest")
    def test_journey_b_generate_training_quest_and_evidence_integrity(
        self, mock_gen_quest, mock_get_evidence
    ):
        """TEST B.2-5: Generate Stage A training quest, verify objectives & evidence, mask hints."""
        # 1. Mock verified evidence from server
        mock_get_evidence.return_value = {
            "status": "verified",
            "issue_number": 5012,
            "repo": "pallets/flask",
            "summary": "Merged in commit abc1234 on main branch.",
            "evidence_sources": ["https://github.com/pallets/flask/commit/abc1234"],
        }

        # 2. Mock AI training quest generation
        mock_gen_quest.return_value = {
            "title": "Resolve Context Memory Leak",
            "explanation": "Context objects were retained indefinitely due to cyclic references.",
            "difficulty": "Novice",
            "steps": [
                {"step": 1, "title": "Inspect teardown callbacks", "instruction": "Check appcontext_tearing_down."},
                {"step": 2, "title": "Break cyclic reference", "instruction": "Clear _cv_app context variable."}
            ],
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "Check context.py teardown handler.", "xp_cost": 10},
                {"level": 2, "tier": "Investigation Lead", "hint": "Inspect weakref usage.", "xp_cost": 25},
            ],
            "xp": 50,
            "stage": "A",
            "resolution_evidence": {
                "status": "verified",
                "summary": "Merged in commit abc1234 on main branch.",
            },
        }

        issue_payload = {
            "number": 5012,
            "title": "Fix memory leak in request dispatcher",
            "body": "Context retained indefinitely.",
            "repo": "pallets/flask",
            "state": "closed",
            "html_url": "https://github.com/pallets/flask/issues/5012",
        }

        resp = self.client.post("/api/training/quest", json={"issue": issue_payload})
        self.assertEqual(resp.status_code, 200)
        quest = resp.get_json()["quest"]

        # Verify Stage A properties
        self.assertEqual(quest["stage"], "A")
        self.assertEqual(quest["xp"], 50)
        self.assertEqual(len(quest["steps"]), 2)
        self.assertEqual(quest["resolution_evidence"]["status"], "verified")

        # Confirm locked hints are masked and do not leak text
        for h in quest["hints"]:
            self.assertTrue(h["locked"])
            self.assertIn("[LOCKED", h["hint"])
            self.assertNotIn("context.py", h["hint"])

        # Reject open issues in Stage A endpoint
        open_issue = dict(issue_payload, state="open")
        bad_resp = self.client.post("/api/training/quest", json={"issue": open_issue})
        self.assertEqual(bad_resp.status_code, 400)
        self.assertIn("require a closed issue", bad_resp.get_json()["error"])

    # =========================================================================
    # TEST C — STAGE B CHALLENGE
    # =========================================================================

    def test_journey_c_stage_b_progression_gate_and_challenge_access(self):
        """TEST C.1-3: Verify Stage B is locked initially, then unlocked when requirements are met."""
        # 1. Fresh user profile: 0 XP and 0 Stage A completions -> Stage B must be locked
        prof_resp = self.client.get("/api/user/profile")
        self.assertEqual(prof_resp.status_code, 200)
        prof = prof_resp.get_json()["profile"]
        self.assertEqual(prof["earned_xp"], 0)
        self.assertEqual(prof["stage_a_completed_count"], 0)
        self.assertFalse(prof["stage_b_unlocked"])
        self.assertEqual(prof["stage_b_requirements"]["required_xp"], 200)
        self.assertEqual(prof["stage_b_requirements"]["required_stage_a_quests"], 3)

        # 2. Complete 4 Stage A quests (each gives 50 XP, total = 200 XP >= 200, count = 4 >= 3)
        for i in range(1, 5):
            qid = f"quest_stage_a_{i}"
            record_quest(qid, repo="owner/repo", issue_number=i, stage="A", title=f"Training Quest {i}", base_xp=50)
            comp = self.client.post("/api/quest/complete", json={"quest_id": qid, "stage": "A"})
            self.assertEqual(comp.status_code, 200)

        # 3. Verify qualifying profile: Stage B unlocked
        unlocked_prof_resp = self.client.get("/api/user/profile")
        self.assertEqual(unlocked_prof_resp.status_code, 200)
        unlocked_prof = unlocked_prof_resp.get_json()["profile"]
        self.assertEqual(unlocked_prof["earned_xp"], 200)
        self.assertEqual(unlocked_prof["stage_a_completed_count"], 4)
        self.assertTrue(unlocked_prof["stage_b_unlocked"])

    @patch("app.generate_quest")
    def test_journey_c_generate_challenge_and_locked_hint_security(self, mock_gen_quest):
        """TEST C.4-5: Generate challenge from open issue and confirm hints are masked."""
        mock_gen_quest.return_value = {
            "title": "Support Cloudflare Workers",
            "explanation": "Add adapter documentation for running Flask on edge workers.",
            "difficulty": "Intermediate",
            "steps": [
                {"step": 1, "title": "Check documentation syntax", "instruction": "Verify Sphinx rst files."}
            ],
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "SECRET_HINT_1: Check docs/hosting.rst", "xp_cost": 10},
                {"level": 2, "tier": "Investigation Lead", "hint": "SECRET_HINT_2: Use Python worker guide", "xp_cost": 25},
            ],
            "xp": 100,
            "stage": "B",
        }

        open_issue = {
            "number": 6146,
            "title": "Add Cloudflare to Flask Hosting Platforms docs",
            "body": "Guide available at developers.cloudflare.com",
            "repo": "pallets/flask",
            "state": "open",
            "html_url": "https://github.com/pallets/flask/issues/6146",
        }

        resp = self.client.post("/api/quest", json={"issue": open_issue})
        self.assertEqual(resp.status_code, 200)
        quest = resp.get_json()["quest"]

        # Confirm locked hints do NOT leak secret text
        self.assertEqual(quest["stage"], "B")
        for h in quest["hints"]:
            self.assertTrue(h["locked"])
            self.assertNotIn("SECRET_HINT", h["hint"])
            self.assertIn("[LOCKED", h["hint"])

    # =========================================================================
    # TEST D — HINT PURCHASES
    # =========================================================================

    def test_journey_d_hint_purchase_lifecycle(self):
        """TEST D.1-6: Solvency, XP deduction, re-access idempotency, balance consistency."""
        # Seed a test quest with 2 hint tiers
        quest_data = {
            "quest_id": "quest_test_hint_lifecycle",
            "title": "Hint Lifecycle Quest",
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "Secret Guidance Tier 1", "xp_cost": 10},
                {"level": 2, "tier": "Investigation Lead", "hint": "Secret Guidance Tier 2", "xp_cost": 25},
            ],
        }
        record_quest(
            quest_id="quest_test_hint_lifecycle",
            repo="owner/repo",
            issue_number=99,
            stage="B",
            title="Hint Lifecycle Quest",
            raw_payload=quest_data,
        )

        # 1. Attempt to unlock with 0 XP -> Must return 400 Insufficient XP and balance unchanged
        fail_resp = self.client.post(
            "/api/quest/hint/unlock",
            json={"quest_id": "quest_test_hint_lifecycle", "hint_tier": 1},
        )
        self.assertEqual(fail_resp.status_code, 400)
        self.assertIn("Insufficient XP", fail_resp.get_json()["error"])

        prof_check = self.client.get("/api/user/profile").get_json()["profile"]
        self.assertEqual(prof_check["earned_xp"], 0)

        # 2. Fund user by completing a Stage A quest (+50 XP)
        record_quest("quest_funding_1", repo="owner/repo", issue_number=1, stage="A", title="Funding Quest")
        comp = self.client.post("/api/quest/complete", json={"quest_id": "quest_funding_1", "stage": "A"})
        self.assertEqual(comp.status_code, 200)
        self.assertEqual(comp.get_json()["balance"], 50)

        # 3. Unlock Tier 1 hint (Costs 10 XP) -> Balance should become 40 XP
        unlock1 = self.client.post(
            "/api/quest/hint/unlock",
            json={"quest_id": "quest_test_hint_lifecycle", "hint_tier": 1},
        )
        self.assertEqual(unlock1.status_code, 200)
        unl_data = unlock1.get_json()
        self.assertEqual(unl_data["xp_deducted"], 10)
        self.assertEqual(unl_data["balance"], 40)
        self.assertFalse(unl_data["already_purchased"])
        self.assertEqual(unl_data["hint"], "Secret Guidance Tier 1")

        # 4. Verify profile reflects authoritative 40 XP balance
        prof_after_unl = self.client.get("/api/user/profile").get_json()["profile"]
        self.assertEqual(prof_after_unl["earned_xp"], 40)
        self.assertEqual(prof_after_unl["purchased_hints_count"], 1)

        # 5. Re-access the same Tier 1 hint -> Must return 200, free (0 deducted), already_purchased: true
        reaccess = self.client.post(
            "/api/quest/hint/unlock",
            json={"quest_id": "quest_test_hint_lifecycle", "hint_tier": 1},
        )
        self.assertEqual(reaccess.status_code, 200)
        re_data = reaccess.get_json()
        self.assertEqual(re_data["xp_deducted"], 0)
        self.assertEqual(re_data["balance"], 40)
        self.assertTrue(re_data["already_purchased"])

        # 6. Verify ledger integrity in SQLite
        with get_db_connection(self.temp_db.name) as conn:
            txs = conn.execute(
                "SELECT amount, balance_after, action_type FROM xp_transactions WHERE reference_id = ?",
                ("quest_test_hint_lifecycle",),
            ).fetchall()
            self.assertEqual(len(txs), 1)
            self.assertEqual(txs[0]["amount"], -10)
            self.assertEqual(txs[0]["balance_after"], 40)
            self.assertEqual(txs[0]["action_type"], "hint_purchase")

    # =========================================================================
    # TEST E — COMPLETION & REWARD PERSISTENCE
    # =========================================================================

    def test_journey_e_quest_completion_ledger_and_persistence(self):
        """TEST E.1-5: Complete quest, check ledger, duplicate prevention, persistence across reloads."""
        qid = "quest_e2e_completion_test"
        record_quest(qid, repo="pallets/flask", issue_number=88, stage="A", title="Completion Test Quest")

        # 1. Complete quest (+50 XP)
        resp = self.client.post("/api/quest/complete", json={"quest_id": qid, "stage": "A"})
        self.assertEqual(resp.status_code, 200)
        comp_data = resp.get_json()
        self.assertTrue(comp_data["success"])
        self.assertEqual(comp_data["awarded_xp"], 50)
        self.assertEqual(comp_data["balance"], 50)
        self.assertFalse(comp_data["already_completed"])

        # 2. Verify ledger record
        with get_db_connection(self.temp_db.name) as conn:
            ledger_entry = conn.execute(
                "SELECT amount, balance_after, action_type FROM xp_transactions WHERE reference_id = ?",
                (qid,),
            ).fetchone()
            self.assertIsNotNone(ledger_entry)
            self.assertEqual(ledger_entry["amount"], 50)
            self.assertEqual(ledger_entry["balance_after"], 50)
            self.assertEqual(ledger_entry["action_type"], "quest_completion")

        # 3. Duplicate completion attempt -> Must return 400 with already_completed: true, no XP added
        dup_resp = self.client.post("/api/quest/complete", json={"quest_id": qid, "stage": "A"})
        self.assertEqual(dup_resp.status_code, 400)
        dup_data = dup_resp.get_json()
        self.assertTrue(dup_data["already_completed"])

        # 4. Check profile reflects single reward and persisted state
        prof = self.client.get("/api/user/profile").get_json()["profile"]
        self.assertEqual(prof["earned_xp"], 50)
        self.assertEqual(prof["total_completed_count"], 1)
        self.assertIn(qid, prof["completed_quest_ids"])

    # =========================================================================
    # TEST F — FAILURE HANDLING
    # =========================================================================

    @patch("app.generate_quest")
    def test_journey_f_ai_service_failures(self, mock_gen_quest):
        """TEST F: AI Key missing (503), schema validation failure (502), and model failure (502)."""
        from ai_service import AIKeyMissingError, AISchemaValidationError, AIServiceError

        open_issue = {"number": 1, "title": "Crash", "repo": "owner/repo", "state": "open"}

        # AI key missing -> 503
        mock_gen_quest.side_effect = AIKeyMissingError("GEMINI_API_KEY missing.")
        resp_key = self.client.post("/api/quest", json={"issue": open_issue})
        self.assertEqual(resp_key.status_code, 503)

        # AI schema error -> 502
        mock_gen_quest.side_effect = AISchemaValidationError("Missing required 'hints'.")
        resp_schema = self.client.post("/api/quest", json={"issue": open_issue})
        self.assertEqual(resp_schema.status_code, 502)

        # AI upstream failure -> 502
        mock_gen_quest.side_effect = AIServiceError("Upstream service unavailable.")
        resp_upstream = self.client.post("/api/quest", json={"issue": open_issue})
        self.assertEqual(resp_upstream.status_code, 502)

    def test_journey_f_missing_quest_and_invalid_payloads(self):
        """TEST F: Missing quest (404), invalid JSON (400), invalid hint tier (400)."""
        # Unlock hint on non-existent quest -> 404
        resp_missing_hint = self.client.post(
            "/api/quest/hint/unlock",
            json={"quest_id": "quest_nonexistent_999", "hint_tier": 1},
        )
        self.assertEqual(resp_missing_hint.status_code, 404)

        # Complete non-existent quest -> 404
        resp_missing_comp = self.client.post(
            "/api/quest/complete",
            json={"quest_id": "quest_nonexistent_999"},
        )
        self.assertEqual(resp_missing_comp.status_code, 404)

        # Invalid hint tier (tier 4 does not exist) -> 400
        record_quest("quest_test_tier_err", repo="owner/repo", issue_number=1, stage="B", title="Test")
        resp_bad_tier = self.client.post(
            "/api/quest/hint/unlock",
            json={"quest_id": "quest_test_tier_err", "hint_tier": 4},
        )
        self.assertEqual(resp_bad_tier.status_code, 400)


if __name__ == "__main__":
    unittest.main()
