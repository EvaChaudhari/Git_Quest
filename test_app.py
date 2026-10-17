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


if __name__ == "__main__":
    unittest.main()
