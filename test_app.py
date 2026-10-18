"""Unit tests for the GitQuest Flask backend application (app.py).

All tests use Flask's test client and mock the GitHub service layer so they
execute completely offline without requiring internet access or GitHub tokens.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from app import app
from github_service import (
    GitHubRateLimitError,
    GitHubRepoNotFoundError,
    GitHubServiceError,
)


class TestAppBackend(unittest.TestCase):
    """Test suite for Flask backend endpoints."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_endpoint(self):
        """GET /health returns 200 with {'status': 'ok'}."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_root_endpoint(self):
        """GET / returns 200 with minimal temporary API status."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("message", data)
        self.assertIn("endpoints", data)

    def test_root_endpoint_html_for_browsers(self):
        """GET / with Accept: text/html returns the frontend HTML."""
        response = self.client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("BUG//DUNGEON", response.get_data(as_text=True))

    def test_post_issues_valid_url(self):
        """POST /api/issues returns normalized issues and count."""
        mock_issues = [
            {
                "number": 42,
                "title": "Example bug",
                "body": "Fix needed",
                "labels": ["bug"],
                "html_url": "https://github.com/owner/repo/issues/42",
                "repo": "owner/repo",
            }
        ]
        with patch("app.get_issues", return_value=mock_issues) as mock_get:
            response = self.client.post(
                "/api/issues",
                json={"repo_url": "https://github.com/owner/repo"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["issues"], mock_issues)
            mock_get.assert_called_once_with("https://github.com/owner/repo", limit=10)

    def test_post_issues_empty_results(self):
        """POST /api/issues handles repositories with 0 open issues."""
        with patch("app.get_issues", return_value=[]) as mock_get:
            response = self.client.post(
                "/api/issues",
                json={"repo_url": "https://github.com/owner/empty-repo"},
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertEqual(data["count"], 0)
            self.assertEqual(data["issues"], [])

    def test_post_issues_missing_content_type(self):
        """POST /api/issues with non-JSON body returns 400."""
        response = self.client.post("/api/issues", data="plain text")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Content-Type: application/json", response.get_json()["error"])

    def test_post_issues_malformed_json(self):
        """POST /api/issues with invalid JSON string returns 400."""
        response = self.client.post(
            "/api/issues",
            data="{invalid-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid JSON", response.get_json()["error"])

    def test_post_issues_missing_repo_url(self):
        """POST /api/issues without repo_url returns 400."""
        response = self.client.post("/api/issues", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("repo_url", response.get_json()["error"])

    def test_post_issues_empty_repo_url(self):
        """POST /api/issues with empty repo_url returns 400."""
        response = self.client.post("/api/issues", json={"repo_url": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("repo_url", response.get_json()["error"])

    def test_post_issues_invalid_repo_url(self):
        """POST /api/issues with invalid URL returns 400."""
        response = self.client.post(
            "/api/issues",
            json={"repo_url": "https://gitlab.com/owner/repo"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Non-GitHub host", response.get_json()["error"])

    def test_post_issues_repo_not_found_404(self):
        """POST /api/issues with non-existent repo returns 404."""
        with patch("app.get_issues", side_effect=GitHubRepoNotFoundError("Repo not found.")):
            response = self.client.post(
                "/api/issues",
                json={"repo_url": "https://github.com/owner/missing"},
            )
            self.assertEqual(response.status_code, 404)
            self.assertIn("not found", response.get_json()["error"])

    def test_post_issues_rate_limit_429(self):
        """POST /api/issues hitting rate limit returns 429."""
        with patch("app.get_issues", side_effect=GitHubRateLimitError("Rate limit reached.")):
            response = self.client.post(
                "/api/issues",
                json={"repo_url": "https://github.com/owner/repo"},
            )
            self.assertEqual(response.status_code, 429)
            self.assertIn("Rate limit", response.get_json()["error"])

    def test_post_issues_timeout_or_network_error_502(self):
        """POST /api/issues timing out returns 502."""
        with patch("app.get_issues", side_effect=GitHubServiceError("Request timed out.")):
            response = self.client.post(
                "/api/issues",
                json={"repo_url": "https://github.com/owner/repo"},
            )
            self.assertEqual(response.status_code, 502)
            self.assertIn("timed out", response.get_json()["error"])

    def test_post_issues_unexpected_error_500(self):
        """POST /api/issues unexpected failure returns 500 without leaking secrets."""
        with patch("app.get_issues", side_effect=RuntimeError("internal crash")):
            response = self.client.post(
                "/api/issues",
                json={"repo_url": "https://github.com/owner/repo"},
            )
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.get_json(), {"error": "An internal server error occurred."})

    def test_post_quest_success_with_issue_wrapper(self):
        """POST /api/quest with {'issue': {...}} returns 200 and {'quest': {...}}."""
        sample_issue = {
            "number": 1,
            "title": "Fix navbar bug",
            "body": "Bug description",
            "labels": ["bug"],
            "html_url": "https://github.com/owner/repo/issues/1",
            "repo": "owner/repo",
        }
        mock_raw_quest = {
            "quest_id": "quest_owner_repo_1",
            "quest_title": "Fix the Nav Shield",
            "tagline": "Protect the console",
            "difficulty": "Novice",
            "category": "Bug Squashing",
            "xp_reward": 200,
            "estimated_time_minutes": 15,
            "briefing": {
                "lore_intro": "Incoming alert",
                "technical_summary": "Navbar fails on mobile viewports."
            },
            "objectives": [
                {"step": 1, "title": "Inspect Breakpoints", "instruction": "Check CSS"}
            ],
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "Look at navbar.js", "xp_cost": 10}
            ],
        }
        with patch("app.generate_quest", return_value=mock_raw_quest) as mock_gen:
            response = self.client.post(
                "/api/quest",
                json={"issue": sample_issue},
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("quest", data)
            quest = data["quest"]
            self.assertEqual(quest["title"], "Fix the Nav Shield")
            self.assertEqual(quest["explanation"], "Navbar fails on mobile viewports.")
            self.assertEqual(quest["difficulty"], "Novice")
            self.assertEqual(len(quest["steps"]), 1)
            self.assertEqual(len(quest["hints"]), 1)
            self.assertEqual(quest["xp"], 200)
            mock_gen.assert_called_once()

    def test_post_quest_success_with_direct_issue_body(self):
        """POST /api/quest with direct issue object in body returns 200 and {'quest': {...}}."""
        sample_issue = {
            "number": 2,
            "title": "Add documentation",
            "body": "Docs description",
            "labels": ["documentation"],
            "html_url": "https://github.com/owner/repo/issues/2",
            "repo": "owner/repo",
        }
        mock_raw_quest = {
            "quest_id": "quest_owner_repo_2",
            "quest_title": "Archive of Lore",
            "tagline": "Scribe the knowledge",
            "difficulty": "Novice",
            "category": "Docs & Discovery",
            "xp_reward": 100,
            "estimated_time_minutes": 20,
            "briefing": {
                "lore_intro": "The archives are incomplete",
                "technical_summary": "Missing docs for Cloudflare hosting."
            },
            "objectives": [
                {"step": 1, "title": "Write Docs", "instruction": "Add section to docs"}
            ],
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "Check docs folder", "xp_cost": 10}
            ],
        }
        with patch("app.generate_quest", return_value=mock_raw_quest) as mock_gen:
            response = self.client.post("/api/quest", json=sample_issue)
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("quest", data)
            quest = data["quest"]
            self.assertEqual(quest["title"], "Archive of Lore")
            self.assertEqual(quest["xp"], 100)
            mock_gen.assert_called_once()

    def test_post_quest_missing_content_type(self):
        """POST /api/quest with non-JSON body returns 400."""
        response = self.client.post("/api/quest", data="not-json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Content-Type: application/json", response.get_json()["error"])

    def test_post_quest_empty_body(self):
        """POST /api/quest with empty object returns 400."""
        response = self.client.post("/api/quest", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Field 'issue' is required", response.get_json()["error"])

    def test_post_quest_invalid_number_400(self):
        """POST /api/quest with missing or non-integer number returns 400."""
        response = self.client.post(
            "/api/quest",
            json={"issue": {"title": "Test", "repo": "owner/repo", "number": "invalid"}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("number", response.get_json()["error"])

    def test_post_quest_invalid_title_400(self):
        """POST /api/quest with missing or empty title returns 400."""
        response = self.client.post(
            "/api/quest",
            json={"issue": {"title": "   ", "repo": "owner/repo", "number": 10}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.get_json()["error"])

    def test_post_quest_invalid_repo_400(self):
        """POST /api/quest with missing repo returns 400."""
        response = self.client.post(
            "/api/quest",
            json={"issue": {"title": "Test Title", "repo": "", "number": 10}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("repo", response.get_json()["error"])

    def test_post_quest_invalid_labels_type_400(self):
        """POST /api/quest with labels not being a list returns 400."""
        response = self.client.post(
            "/api/quest",
            json={"issue": {"title": "Test", "repo": "owner/repo", "number": 10, "labels": "invalid"}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("labels", response.get_json()["error"])

    def test_post_quest_invalid_body_type_400(self):
        """POST /api/quest with body not being a string returns 400."""
        response = self.client.post(
            "/api/quest",
            json={"issue": {"title": "Test", "repo": "owner/repo", "number": 10, "body": 12345}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("body", response.get_json()["error"])

    def test_post_quest_closed_issue_rejected_400(self):
        """POST /api/quest rejects closed issues since Stage B requires open issues."""
        response = self.client.post(
            "/api/quest",
            json={"issue": {"title": "Closed bug", "repo": "owner/repo", "number": 10, "state": "closed"}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Stage B challenges require an open issue", response.get_json()["error"])

    def test_post_quest_missing_api_key_503(self):
        """POST /api/quest when AI key is missing returns 503 gracefully."""
        from ai_service import AIKeyMissingError

        sample_issue = {"number": 1, "title": "Test", "repo": "owner/repo"}
        with patch("app.generate_quest", side_effect=AIKeyMissingError("Key missing")):
            response = self.client.post("/api/quest", json={"issue": sample_issue})
            self.assertEqual(response.status_code, 503)
            self.assertIn("missing API key", response.get_json()["error"])

    def test_post_quest_schema_validation_error_502(self):
        """POST /api/quest on schema validation failure returns 502 gracefully."""
        from ai_service import AISchemaValidationError

        sample_issue = {"number": 1, "title": "Test", "repo": "owner/repo"}
        with patch("app.generate_quest", side_effect=AISchemaValidationError("Invalid JSON")):
            response = self.client.post("/api/quest", json={"issue": sample_issue})
            self.assertEqual(response.status_code, 502)
            self.assertIn("Failed to generate a valid quest", response.get_json()["error"])

    def test_post_quest_returned_quest_missing_required_fields_502(self):
        """POST /api/quest fails with 502 when returned quest lacks required fields."""
        sample_issue = {"number": 1, "title": "Test", "repo": "owner/repo"}
        # Missing 'steps' / 'objectives' and 'explanation'
        incomplete_quest = {"title": "Only Title", "difficulty": "Novice", "xp": 100}
        with patch("app.generate_quest", return_value=incomplete_quest):
            response = self.client.post("/api/quest", json={"issue": sample_issue})
            self.assertEqual(response.status_code, 502)
            self.assertIn("Failed to generate a valid quest", response.get_json()["error"])

    def test_post_quest_service_error_502(self):
        """POST /api/quest on model failure returns 502 gracefully."""
        from ai_service import AIServiceError

        sample_issue = {"number": 1, "title": "Test", "repo": "owner/repo"}
        with patch("app.generate_quest", side_effect=AIServiceError("Upstream failure")):
            response = self.client.post("/api/quest", json={"issue": sample_issue})
            self.assertEqual(response.status_code, 502)
            self.assertIn("encountered an error", response.get_json()["error"])

    def test_cors_allowed_origins(self):
        """Test CORS headers on /api/* for allowed origins."""
        for origin in ["http://localhost:3000", "http://localhost:5173"]:
            response = self.client.options(
                "/api/quest",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                },
            )
            self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), origin)

    def test_cors_disallowed_origin(self):
        """Test CORS headers are not granted to disallowed origin."""
        response = self.client.options(
            "/api/quest",
            headers={
                "Origin": "http://malicious.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "http://malicious.example.com",
        )


class TestAppTrainingAndGamificationEndpoints(unittest.TestCase):
    """Integration tests for Stage A training, locked hints, hint unlocking, completions, and profiles."""

    def setUp(self):
        import tempfile
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["GITQUEST_DB_PATH"] = self.temp_db.name

        from database import init_db
        init_db(self.temp_db.name)

        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except OSError:
                pass

    @patch("app.get_closed_issues_with_evidence")
    def test_post_training_issues_success(self, mock_get_closed):
        """POST /api/training/issues returns closed issues with resolution evidence."""
        mock_issues = [
            {
                "number": 50,
                "title": "Historical Bug",
                "body": "Fixed in 2025",
                "labels": ["bug"],
                "html_url": "https://github.com/owner/repo/issues/50",
                "repo": "owner/repo",
                "resolution_evidence": {
                    "status": "verified",
                    "summary": "Merged in PR #52",
                },
            }
        ]
        mock_get_closed.return_value = mock_issues

        response = self.client.post(
            "/api/training/issues",
            json={"repo_url": "https://github.com/owner/repo", "limit": 3},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["issues"][0]["number"], 50)
        self.assertEqual(data["issues"][0]["resolution_evidence"]["status"], "verified")

    def test_post_training_issues_invalid_payload(self):
        """POST /api/training/issues without repo_url returns 400."""
        response = self.client.post("/api/training/issues", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("repo_url", response.get_json()["error"])

    @patch("app.get_issue_resolution_evidence")
    @patch("app.generate_training_quest")
    def test_post_training_quest_success(self, mock_gen_training, mock_evidence):
        """POST /api/training/quest generates Stage A quest with server-verified evidence."""
        mock_evidence.return_value = {
            "status": "verified",
            "summary": "Resolved via PR #52",
            "evidence_sources": ["https://github.com/owner/repo/pull/52"],
        }
        mock_raw_quest = {
            "quest_id": "quest_owner_repo_50_training",
            "quest_title": "The Historic Fix",
            "tagline": "Learn how the bug was solved",
            "difficulty": "Novice",
            "category": "Bug Squashing",
            "xp_reward": 50,
            "estimated_time_minutes": 20,
            "stage": "A",
            "resolution_status": "verified",
            "resolution_explanation": "Added null check to request parser.",
            "evidence_sources": ["https://github.com/owner/repo/pull/52"],
            "briefing": {
                "lore_intro": "Explore past archives.",
                "technical_summary": "Bug in request parser.",
            },
            "objectives": [
                {"step": 1, "title": "Inspect Parser", "instruction": "Locate request parser."}
            ],
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "Check line 20", "xp_cost": 10}
            ],
        }
        mock_gen_training.return_value = mock_raw_quest

        issue = {"number": 50, "title": "Historical Bug", "repo": "owner/repo"}
        response = self.client.post("/api/training/quest", json={"issue": issue})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("quest", data)
        quest = data["quest"]
        self.assertEqual(quest["stage"], "A")
        self.assertEqual(quest["resolution_status"], "verified")
        self.assertEqual(quest["xp"], 50)

    def test_post_training_quest_open_issue_rejected_400(self):
        """POST /api/training/quest rejects open issues since Stage A requires closed issues."""
        issue = {"number": 50, "title": "Open Issue", "repo": "owner/repo", "state": "open"}
        response = self.client.post("/api/training/quest", json={"issue": issue})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Stage A training quests require a closed issue", response.get_json()["error"])

    @patch("app.generate_quest")
    def test_post_quest_masks_locked_hints(self, mock_gen):
        """POST /api/quest protects locked hints so text is not leaked before purchase."""
        mock_raw_quest = {
            "quest_id": "quest_owner_repo_10",
            "quest_title": "Active Challenge",
            "tagline": "Solve the mystery",
            "difficulty": "Adept",
            "category": "Bug Squashing",
            "xp_reward": 100,
            "estimated_time_minutes": 30,
            "briefing": {
                "lore_intro": "Mission briefing",
                "technical_summary": "Active bug in engine",
            },
            "objectives": [
                {"step": 1, "title": "Step 1", "instruction": "Do something"}
            ],
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "SECRET_HINT_1", "xp_cost": 10},
                {"level": 2, "tier": "Investigation Lead", "hint": "SECRET_HINT_2", "xp_cost": 25},
            ],
        }
        mock_gen.return_value = mock_raw_quest

        issue = {"number": 10, "title": "Open Issue", "repo": "owner/repo"}
        response = self.client.post("/api/quest", json={"issue": issue})
        self.assertEqual(response.status_code, 200)
        quest = response.get_json()["quest"]

        # Both hints should be locked and secret text redacted
        for h in quest["hints"]:
            self.assertTrue(h["locked"])
            self.assertNotIn("SECRET_HINT", h["hint"])
            self.assertIn("[LOCKED", h["hint"])

    def test_hint_unlock_and_completion_lifecycle(self):
        """End-to-end gamification lifecycle: complete quest, earn XP, unlock hint, prevent duplicates."""
        from gamification import record_quest
        # 1. Seed two quests: Stage A quest and Stage B quest
        sample_quest_b = {
            "quest_id": "quest_test_repo_99",
            "title": "Quest 99",
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "Reveal Secret 1", "xp_cost": 10},
                {"level": 2, "tier": "Investigation Lead", "hint": "Reveal Secret 2", "xp_cost": 25},
            ],
        }
        record_quest(
            quest_id="quest_test_repo_99",
            repo="test/repo",
            issue_number=99,
            stage="B",
            title="Quest 99",
            raw_payload=sample_quest_b,
        )
        record_quest(
            quest_id="quest_test_repo_1",
            repo="test/repo",
            issue_number=1,
            stage="A",
            title="Quest 1",
        )

        # 2. Try to unlock hint with 0 XP -> should return 400 Insufficient XP
        resp = self.client.post(
            "/api/quest/hint/unlock",
            json={"quest_id": "quest_test_repo_99", "hint_tier": 1},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Insufficient XP", resp.get_json()["error"])

        # 3. Complete Stage A quest -> awards 50 XP
        comp_resp = self.client.post(
            "/api/quest/complete",
            json={"quest_id": "quest_test_repo_1", "stage": "A"},
        )
        self.assertEqual(comp_resp.status_code, 200)
        comp_data = comp_resp.get_json()
        self.assertEqual(comp_data["awarded_xp"], 50)
        self.assertEqual(comp_data["balance"], 50)
        self.assertFalse(comp_data["already_completed"])

        # 4. Duplicate completion attempt -> should return 400 with already_completed=True
        dup_resp = self.client.post(
            "/api/quest/complete",
            json={"quest_id": "quest_test_repo_1", "stage": "A"},
        )
        self.assertEqual(dup_resp.status_code, 400)
        self.assertTrue(dup_resp.get_json()["already_completed"])

        # 5. Now unlock hint tier 1 (cost 10 XP) -> succeeds, balance becomes 40
        unlock_resp = self.client.post(
            "/api/quest/hint/unlock",
            json={"quest_id": "quest_test_repo_99", "hint_tier": 1},
        )
        self.assertEqual(unlock_resp.status_code, 200)
        unlock_data = unlock_resp.get_json()
        self.assertTrue(unlock_data["success"])
        self.assertEqual(unlock_data["xp_deducted"], 10)
        self.assertEqual(unlock_data["balance"], 40)
        self.assertFalse(unlock_data["already_purchased"])
        self.assertEqual(unlock_data["hint"], "Reveal Secret 1")

        # 6. Re-unlocking tier 1 is free (idempotent)
        re_resp = self.client.post(
            "/api/quest/hint/unlock",
            json={"quest_id": "quest_test_repo_99", "hint_tier": 1},
        )
        self.assertEqual(re_resp.status_code, 200)
        re_data = re_resp.get_json()
        self.assertTrue(re_data["already_purchased"])
        self.assertEqual(re_data["xp_deducted"], 0)
        self.assertEqual(re_data["balance"], 40)

        # 7. Check user profile
        prof_resp = self.client.get("/api/user/profile")
        self.assertEqual(prof_resp.status_code, 200)
        prof_data = prof_resp.get_json()["profile"]
        self.assertEqual(prof_data["earned_xp"], 40)
        self.assertEqual(prof_data["stage_a_completed_count"], 1)
        self.assertFalse(prof_data["stage_b_unlocked"])

    def test_stage_b_progression_threshold(self):
        """Stage B unlocks only when earned_xp >= 200 and completed_stage_a_count >= 3."""
        from gamification import record_quest
        # Complete 4 Stage A quests (each gives 50 XP, total = 200 XP)
        for i in range(1, 5):
            qid = f"quest_stage_a_{i}"
            record_quest(qid, repo="owner/repo", issue_number=i, stage="A", title=f"Quest {i}")
            res = self.client.post("/api/quest/complete", json={"quest_id": qid, "stage": "A"})
            self.assertEqual(res.status_code, 200)

        prof_resp = self.client.get("/api/user/profile")
        self.assertEqual(prof_resp.status_code, 200)
        prof = prof_resp.get_json()["profile"]
        self.assertEqual(prof["earned_xp"], 200)
        self.assertEqual(prof["stage_a_completed_count"], 4)
        self.assertTrue(prof["stage_b_unlocked"])


if __name__ == "__main__":
    unittest.main()
