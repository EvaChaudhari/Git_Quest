"""Integration tests for GitQuest frontend assets and HTML views.

Validates that templates and static assets are served properly by Flask,
meta tags are correctly configured, and all required DOM elements for the 6-step
journey are present in the served page.
"""

from __future__ import annotations

import os
import unittest

from app import app


class TestFrontendIntegration(unittest.TestCase):
    """Test suite for GitQuest frontend template and asset delivery."""

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

    def test_serve_html_index_page(self):
        """GET / with browser Accept header serves index.html."""
        resp = self.client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("GIT QUEST", html)
        self.assertIn('meta name="gitquest-api-base"', html)

    def test_serve_app_page(self):
        """GET /app serves the application page directly."""
        resp = self.client.get("/app")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Choose your dungeon", html)

    def test_required_dom_elements_present(self):
        """Verify all critical elements for the 6-step journey exist in the template."""
        resp = self.client.get("/app")
        html = resp.get_data(as_text=True)

        # Step 1: Repo input & scan
        self.assertIn('id="repo-url"', html)
        self.assertIn('id="scan-button"', html)
        self.assertIn('id="issues-list"', html)

        # Step 2: Learning mode selector
        self.assertIn('id="mode-stage-a-btn"', html)
        self.assertIn('id="mode-stage-b-btn"', html)
        self.assertIn('id="stage-b-lock-banner"', html)

        # Step 3: Quest Briefing & Investigation slot
        self.assertIn('id="briefing-title"', html)
        self.assertIn('id="investigation-slot"', html)
        self.assertIn('id="companion-dialogue"', html)

        # Step 4 & 5: Profile & progression counters
        self.assertIn('id="profile-stage-a-count"', html)
        self.assertIn('id="profile-consistency-score"', html)
        self.assertIn('id="profile-stage-b-status"', html)
        self.assertIn('id="profile-stage-b-box"', html)

        # Step 6: HUD stats
        self.assertIn('id="consistency-val"', html)
        self.assertIn('id="topbar-stage-b-stat"', html)

    def test_static_assets_delivery(self):
        """Verify static CSS, JS, and image assets are served successfully."""
        css_resp = self.client.get("/static/style.css")
        self.assertEqual(css_resp.status_code, 200)
        css = css_resp.get_data(as_text=True)
        self.assertIn(".learning-mode-section", css)
        self.assertIn(".evidence-badge.verified", css)
        self.assertIn(".hint-tier-card", css)

        js_resp = self.client.get("/static/app.js")
        self.assertEqual(js_resp.status_code, 200)
        js = js_resp.get_data(as_text=True)
        self.assertIn("class GitQuestApiClient", js)
        self.assertIn("getTrainingIssues", js)
        self.assertIn("generateTrainingQuest", js)
        self.assertIn("unlockHintTier", js)
        self.assertIn("submitQuestCompletion", js)
        self.assertIn("fetchUserProfile", js)
        self.assertIn("retry-scan-btn", js)
        self.assertIn("retry-quest-gen-btn", js)

    def test_authoritative_profile_payload(self):
        """Verify /api/user/profile provides authoritative completed_quest_ids and purchased_hints."""
        resp = self.client.get("/api/user/profile")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("profile", data)
        prof = data["profile"]
        self.assertIn("completed_quest_ids", prof)
        self.assertIn("purchased_hints", prof)
        self.assertIsInstance(prof["completed_quest_ids"], list)
        self.assertIsInstance(prof["purchased_hints"], list)

    def test_node_frontend_state_suite(self):
        """Run Node.js state machine and client contract unit tests."""
        import subprocess
        result = subprocess.run(
            ["node", "--test", "test_frontend_state.js"],
            capture_output=True,
            text=True,
            check=False
        )
        self.assertEqual(result.returncode, 0, f"Node test suite failed:\n{result.stderr}\n{result.stdout}")


if __name__ == "__main__":
    unittest.main()
