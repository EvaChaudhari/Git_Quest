"""Unit and integration tests for github_service.py in GitQuest.

Automated tests use mocks to run offline without internet access or tokens.
An optional live smoke test against https://github.com/pallets/flask is included
and can be run by passing the `--live` flag or setting RUN_LIVE_TESTS=1.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests

from github_service import (
    GitHubRateLimitError,
    GitHubRepoNotFoundError,
    GitHubServiceError,
    get_issues,
    parse_repo_url,
)


class TestParseRepoUrl(unittest.TestCase):
    """Tests for parse_repo_url validation and parsing."""

    def test_valid_github_urls(self):
        """Test standard valid GitHub URLs."""
        owner, repo = parse_repo_url("https://github.com/pallets/flask")
        self.assertEqual(owner, "pallets")
        self.assertEqual(repo, "flask")

        owner, repo = parse_repo_url("http://github.com/psf/requests")
        self.assertEqual(owner, "psf")
        self.assertEqual(repo, "requests")

        owner, repo = parse_repo_url("https://www.github.com/google/guava")
        self.assertEqual(owner, "google")
        self.assertEqual(repo, "guava")

    def test_urls_ending_in_dot_git(self):
        """Test URLs ending in .git and .git/."""
        owner, repo = parse_repo_url("https://github.com/pallets/flask.git")
        self.assertEqual(owner, "pallets")
        self.assertEqual(repo, "flask")

        owner, repo = parse_repo_url("https://github.com/pallets/flask.git/")
        self.assertEqual(owner, "pallets")
        self.assertEqual(repo, "flask")

    def test_urls_with_trailing_slash(self):
        """Test URLs with trailing slashes."""
        owner, repo = parse_repo_url("https://github.com/pallets/flask/")
        self.assertEqual(owner, "pallets")
        self.assertEqual(repo, "flask")

    def test_invalid_hosts(self):
        """Reject non-GitHub hosts with a clear ValueError."""
        with self.assertRaises(ValueError) as ctx:
            parse_repo_url("https://gitlab.com/pallets/flask")
        self.assertIn("Non-GitHub host", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            parse_repo_url("https://bitbucket.org/pallets/flask")
        self.assertIn("Non-GitHub host", str(ctx.exception))

    def test_malformed_urls(self):
        """Reject malformed URLs, missing repos/owners, and extra paths."""
        # Missing repository name
        with self.assertRaises(ValueError) as ctx:
            parse_repo_url("https://github.com/pallets")
        self.assertIn("Expected format", str(ctx.exception))

        # Missing owner and repo
        with self.assertRaises(ValueError) as ctx:
            parse_repo_url("https://github.com/")
        self.assertIn("Expected format", str(ctx.exception))

        # Extra path segments (e.g., issues or pull subpath)
        with self.assertRaises(ValueError) as ctx:
            parse_repo_url("https://github.com/pallets/flask/issues")
        self.assertIn("Expected format", str(ctx.exception))

        # Empty or non-string inputs
        with self.assertRaises(ValueError):
            parse_repo_url("")
        with self.assertRaises(ValueError):
            parse_repo_url("   ")
        with self.assertRaises(ValueError):
            parse_repo_url(None)  # type: ignore[arg-type]


class TestGetIssuesMocked(unittest.TestCase):
    """Offline unit tests for get_issues using mocked HTTP responses."""

    @patch("requests.get")
    def test_correct_normalized_issue_fields(self, mock_get):
        """Verify each normalized issue matches the exact required structure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "number": 101,
                "title": "Bug in request dispatcher",
                "body": "Detailed description of the bug.",
                "labels": [
                    {"name": "bug"},
                    {"name": "good first issue"},
                ],
                "html_url": "https://github.com/pallets/flask/issues/101",
            }
        ]
        mock_response.links = {}
        mock_get.return_value = mock_response

        issues = get_issues("https://github.com/pallets/flask", limit=5)

        self.assertEqual(len(issues), 1)
        expected = {
            "number": 101,
            "title": "Bug in request dispatcher",
            "body": "Detailed description of the bug.",
            "labels": ["bug", "good first issue"],
            "html_url": "https://github.com/pallets/flask/issues/101",
            "repo": "pallets/flask",
        }
        self.assertEqual(issues[0], expected)

    @patch("requests.get")
    def test_filtering_out_pull_requests(self, mock_get):
        """Verify pull requests (objects containing 'pull_request') are filtered out."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "number": 1,
                "title": "Actual Issue #1",
                "body": "First issue body",
                "labels": [],
            },
            {
                "number": 2,
                "title": "Pull Request #2",
                "body": "PR description",
                "labels": [],
                "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/2"},
            },
            {
                "number": 3,
                "title": "Actual Issue #3",
                "body": "Third issue body",
                "labels": [],
            },
        ]
        mock_response.links = {}
        mock_get.return_value = mock_response

        issues = get_issues("https://github.com/owner/repo", limit=10)

        # Pull request #2 should be omitted
        self.assertEqual(len(issues), 2)
        self.assertEqual([issue["number"] for issue in issues], [1, 3])

    @patch("requests.get")
    def test_missing_descriptions_and_labels(self, mock_get):
        """Verify None/missing body and labels default to empty string and empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "number": 50,
                "title": "Issue without body or labels",
                "body": None,
                "labels": None,
            }
        ]
        mock_response.links = {}
        mock_get.return_value = mock_response

        issues = get_issues("https://github.com/owner/repo", limit=5)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["body"], "")
        self.assertEqual(issues[0]["labels"], [])
        self.assertEqual(issues[0]["repo"], "owner/repo")
        self.assertEqual(issues[0]["html_url"], "https://github.com/owner/repo/issues/50")

    @patch("requests.get")
    def test_empty_issue_lists(self, mock_get):
        """Verify an empty issue list from the API returns an empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.links = {}
        mock_get.return_value = mock_response

        issues = get_issues("https://github.com/owner/repo", limit=10)
        self.assertEqual(issues, [])

    @patch("requests.get")
    def test_results_capped_at_maximum_of_10(self, mock_get):
        """Verify results are limited to a maximum of 10 for the prototype."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"number": i, "title": f"Issue {i}", "body": f"Desc {i}", "labels": []}
            for i in range(1, 20)
        ]
        mock_response.links = {}
        mock_get.return_value = mock_response

        # Even with limit=15 requested, it must be capped at 10
        issues = get_issues("https://github.com/owner/repo", limit=15)
        self.assertEqual(len(issues), 10)

    @patch("requests.get")
    def test_github_http_404_repo_not_found(self, mock_get):
        """Verify HTTP 404 raises GitHubRepoNotFoundError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with self.assertRaises(GitHubRepoNotFoundError) as ctx:
            get_issues("https://github.com/nonexistent/repo")
        self.assertIn("not found on GitHub", str(ctx.exception))

    @patch("requests.get")
    def test_github_http_403_rate_limit(self, mock_get):
        """Verify HTTP 403 / 429 raises GitHubRateLimitError."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {"x-ratelimit-remaining": "0"}
        mock_get.return_value = mock_response

        with self.assertRaises(GitHubRateLimitError) as ctx:
            get_issues("https://github.com/owner/repo")
        self.assertIn("rate limit", str(ctx.exception).lower())

    @patch("requests.get")
    def test_github_http_500_failure(self, mock_get):
        """Verify server failure HTTP status raises GitHubServiceError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        with self.assertRaises(GitHubServiceError) as ctx:
            get_issues("https://github.com/owner/repo")
        self.assertIn("HTTP status 500", str(ctx.exception))

    @patch("requests.get")
    def test_request_timeout(self, mock_get):
        """Verify request timeout raises GitHubServiceError without crashing."""
        mock_get.side_effect = requests.exceptions.Timeout("Read timed out")

        with self.assertRaises(GitHubServiceError) as ctx:
            get_issues("https://github.com/owner/repo")
        self.assertIn("timed out", str(ctx.exception))


class TestLiveSmoke(unittest.TestCase):
    """Optional live API smoke test against public repository https://github.com/pallets/flask.

    Skipped by default so automated tests do not depend on internet access or GitHub tokens.
    Run with:
        python test_github.py --live
    or:
        RUN_LIVE_TESTS=1 python test_github.py
    """

    def test_live_pallets_flask(self):
        """Live smoke test fetching open issues from pallets/flask."""
        if os.getenv("RUN_LIVE_TESTS") != "1":
            self.skipTest(
                "Live smoke tests skipped by default. Run with '--live' or set RUN_LIVE_TESTS=1."
            )

        repo_url = "https://github.com/pallets/flask"
        owner, repo = parse_repo_url(repo_url)
        self.assertEqual(owner, "pallets")
        self.assertEqual(repo, "flask")

        issues = get_issues(repo_url, limit=3)
        self.assertIsInstance(issues, list)
        self.assertLessEqual(len(issues), 3)

        if issues:
            first = issues[0]
            required_keys = {"number", "title", "body", "labels", "html_url", "repo"}
            self.assertEqual(set(first.keys()), required_keys)
            self.assertEqual(first["repo"], "pallets/flask")
            self.assertIsInstance(first["number"], int)
            self.assertIsInstance(first["title"], str)
            self.assertIsInstance(first["body"], str)
            self.assertIsInstance(first["labels"], list)
            self.assertTrue(first["html_url"].startswith("https://github.com/pallets/flask/issues/"))


if __name__ == "__main__":
    if "--live" in sys.argv:
        sys.argv.remove("--live")
        os.environ["RUN_LIVE_TESTS"] = "1"

    unittest.main()
