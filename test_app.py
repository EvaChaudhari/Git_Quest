"""Unit tests for the GitQuest Flask backend application (app.py).

All tests use Flask's test client and mock the GitHub service layer so they
execute completely offline without requiring internet access or GitHub tokens.
"""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
