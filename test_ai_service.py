import json
import unittest
from unittest.mock import patch, MagicMock

from ai_service import (
    Hint,
    QuestObjective,
    QuestBriefing,
    Quest,
    _clean_json_response,
    _build_quest_prompt,
    transform_issue_to_quest,
    generate_quest,
    AIKeyMissingError,
    AISchemaValidationError,
)

class TestAIService(unittest.TestCase):
    def setUp(self):
        self.sample_issue = {
            "number": 101,
            "title": "Fix navbar collapse on mobile viewports",
            "body": "When resizing window below 768px, hamburger menu throws TypeError.",
            "labels": ["bug", "ui"],
            "html_url": "https://github.com/org/repo/issues/101",
            "repo": "org/repo",
        }
        self.sample_quest_payload = {
            "quest_id": "quest_org_repo_101",
            "quest_title": "Operation Responsive Shield",
            "tagline": "Restore the mobile command matrix and fix the viewport collapse.",
            "difficulty": "Novice",
            "category": "Bug Squashing",
            "xp_reward": 150,
            "estimated_time_minutes": 25,
            "tags": ["CSS", "JavaScript", "Responsive UI"],
            "briefing": {
                "lore_intro": "Incoming distress call: the viewport communicator has malfunctioned.",
                "technical_summary": "Mobile toggle event handler fails on window resize below 768px."
            },
            "objectives": [
                {"step": 1, "title": "Inspect Breakpoints", "instruction": "Locate the media query handler."},
                {"step": 2, "title": "Patch the Null Check", "instruction": "Add defensive check before accessing menu element."}
            ],
            "hints": [
                {"level": 1, "tier": "Gentle Nudge", "hint": "Check the resize listener.", "xp_cost": 10},
                {"level": 2, "tier": "Investigation Lead", "hint": "Look at navbar.js line 45.", "xp_cost": 25},
                {"level": 3, "tier": "Tactical Blueprint", "hint": "Wrap toggler in optional chaining.", "xp_cost": 50}
            ],
            "verification_checklist": [
                "Navbar toggles smoothly at 375px width",
                "No console errors on resize"
            ]
        }

    def test_clean_json_response_with_markdown(self):
        raw = '```json\n{"quest_title": "Test"}\n```'
        self.assertEqual(_clean_json_response(raw), '{"quest_title": "Test"}')

    def test_clean_json_response_with_surrounding_text(self):
        raw = 'Here is your quest:\n{"quest_title": "Test"}\nHope you enjoy it!'
        self.assertEqual(_clean_json_response(raw), '{"quest_title": "Test"}')

    def test_build_quest_prompt(self):
        prompt = _build_quest_prompt(self.sample_issue)
        self.assertIn("org/repo", prompt)
        self.assertIn("#101", prompt)
        self.assertIn("Fix navbar collapse", prompt)

    def test_missing_api_key_raises_error(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AIKeyMissingError):
                transform_issue_to_quest(self.sample_issue)

    @patch("ai_service._get_api_client")
    def test_transform_issue_to_quest_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(self.sample_quest_payload)
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        quest = transform_issue_to_quest(self.sample_issue, api_key="test-key")
        self.assertIsInstance(quest, Quest)
        self.assertEqual(quest.quest_title, "Operation Responsive Shield")
        self.assertEqual(quest.difficulty, "Novice")
        self.assertEqual(len(quest.hints), 3)
        self.assertEqual(quest.source_issue["number"], 101)

    @patch("ai_service._get_api_client")
    def test_generate_quest_dict_output(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(self.sample_quest_payload)
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        quest_dict = generate_quest(self.sample_issue, api_key="test-key")
        self.assertIsInstance(quest_dict, dict)
        self.assertEqual(quest_dict["quest_id"], "quest_org_repo_101")
        self.assertEqual(quest_dict["xp_reward"], 150)

    @patch("ai_service._get_api_client")
    def test_schema_validation_error_on_bad_json(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"invalid": "schema"}'
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        with self.assertRaises(AISchemaValidationError):
            transform_issue_to_quest(self.sample_issue, api_key="test-key")

if __name__ == "__main__":
    unittest.main()
