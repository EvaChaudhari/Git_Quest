"""AI Service for GitQuest (Person 2 - AI Integration).

Transforms real GitHub issues (from Person 1's backend) into engaging,
gamified developer quests with narrative lore, structured objectives,
tiered progressive hints, and XP progression using Google Gemma / Gemini models.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

# Default model (gemma-4-26b-a4b-it is the available Gemma model on this API key)
DEFAULT_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")


def _load_env_file() -> None:
    """Load key-value pairs from .env file into os.environ if present."""
    for base_dir in [os.getcwd(), os.path.dirname(__file__)]:
        env_path = os.path.join(base_dir, ".env")
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                pass


# Automatically load .env on import
_load_env_file()



# ============================================================================
# Quest Pydantic Schemas (The GitQuest Data Contract)
# ============================================================================

class Hint(BaseModel):
    """Progressive hint item designed to guide reasoning without spoiling."""

    level: int = Field(
        ...,
        description="Hint level: 1 (Gentle Nudge), 2 (Investigation Lead), 3 (Tactical Blueprint)",
    )
    tier: str = Field(
        ...,
        description="Display name of the hint tier, e.g. 'Gentle Nudge', 'Investigation Lead', 'Tactical Blueprint'",
    )
    hint: str = Field(
        ...,
        description="Guidance text that leads the player towards the solution without copying code.",
    )
    xp_cost: int = Field(
        ...,
        description="XP deducted from total reward if this hint is revealed (e.g. 10, 25, 50).",
    )


class QuestObjective(BaseModel):
    """Actionable milestone step for the quest."""

    step: int = Field(..., description="Step sequence number (1, 2, 3)")
    title: str = Field(..., description="Short title for this objective milestone")
    instruction: str = Field(..., description="Clear instruction describing what the player should do")


class QuestBriefing(BaseModel):
    """Narrative lore and clear technical context for the issue."""

    lore_intro: str = Field(
        ...,
        description="Immersive, RPG-style narrative framing the issue as a heroic engineering mission.",
    )
    technical_summary: str = Field(
        ...,
        description="Accurate, straightforward technical summary of the actual underlying problem.",
    )


class Quest(BaseModel):
    """Complete playable quest payload returned to backend and frontend."""

    quest_id: str = Field(
        ...,
        description="Unique identifier e.g. 'quest_owner_repo_123'",
    )
    quest_title: str = Field(
        ...,
        description="Catchy, thematic game title for the quest (e.g. 'Operation Portal Void')",
    )
    tagline: str = Field(
        ...,
        description="One-sentence hook summarizing the player's core objective.",
    )
    difficulty: str = Field(
        ...,
        description="Quest difficulty rating: 'Novice', 'Adept', or 'Master'.",
    )
    category: str = Field(
        ...,
        description="Quest category e.g. 'Bug Squashing', 'Feature Forge', 'Refactor Realm', 'Docs & Discovery'.",
    )
    xp_reward: int = Field(
        ...,
        description="Base XP awarded upon completion (e.g. 100 to 500).",
    )
    estimated_time_minutes: int = Field(
        ...,
        description="Estimated time to complete in minutes.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Keywords, frameworks, or languages involved (e.g. ['Python', 'Flask', 'Routing']).",
    )
    briefing: QuestBriefing
    objectives: list[QuestObjective]
    hints: list[Hint]
    verification_checklist: list[str] = Field(
        default_factory=list,
        description="Checklist criteria for players to verify their solution works.",
    )
    source_issue: Optional[dict[str, Any]] = Field(
        default=None,
        description="Reference to the original normalized issue data from Person 1's backend.",
    )


# ============================================================================
# Exception Definitions
# ============================================================================

class AIServiceError(Exception):
    """Base exception for AI service operations."""


class AIKeyMissingError(AIServiceError):
    """Raised when no Google GenAI / Gemini API key is configured."""


class AISchemaValidationError(AIServiceError):
    """Raised when the AI model output fails schema validation."""


# ============================================================================
# Prompt Construction
# ============================================================================

QUEST_SYSTEM_INSTRUCTIONS = """You are the Quest Master of GitQuest — a platform that transforms real open-source GitHub issues into engaging, gamified developer quests.

Your mission is to take real issue data (title, body, repository, labels) and craft a structured, playable quest that motivates developers to contribute.

Follow these strict rules:
1. THEMATIC HOOK: Make 'quest_title' exciting and game-like, while clearly relating to the problem.
2. DUAL BRIEFING:
   - 'lore_intro': An entertaining, immersive RPG or sci-fi narrative framing the bug/feature as a mission.
   - 'technical_summary': A crystal-clear, accurate breakdown of what is actually happening in the code.
3. OBJECTIVES: Provide 2 to 4 actionable, sequential steps:
   - Step 1: Reconnaissance (inspect code, reproduce the bug or setup).
   - Step 2: Implementation (the core fix or feature).
   - Step 3: Verification (testing and preventing regressions).
4. PROGRESSIVE HINTS: Exactly 3 tiers of hints:
   - Level 1 ('Gentle Nudge', xp_cost: 10): High-level architectural clue or concept to check.
   - Level 2 ('Investigation Lead', xp_cost: 25): Narrow down to specific modules, functions, or patterns.
   - Level 3 ('Tactical Blueprint', xp_cost: 50): Concrete guidance on the logic fix (do NOT simply paste complete finished code).
5. DIFFICULTY & XP:
   - 'Novice' (100 - 150 XP): Simple fixes, typos, basic null checks, documentation issues.
   - 'Adept' (200 - 350 XP): Logic bugs, state management, test suites, API changes.
   - 'Master' (400 - 600 XP): Deep architectural refactors, concurrency, performance, security.
6. FORMAT: Output MUST be valid, parseable JSON matching the requested schema.
"""


def _build_quest_prompt(issue: dict[str, Any]) -> str:
    """Build the prompt for Gemma using the normalized issue from Person 1."""
    issue_number = issue.get("number", 0)
    repo = issue.get("repo", "unknown/repo")
    title = issue.get("title", "Untitled Issue")
    body = issue.get("body", "")
    labels = issue.get("labels", [])
    html_url = issue.get("html_url", "")

    # Truncate body if excessively long to avoid token bloat
    truncated_body = body[:2500] + ("..." if len(body) > 2500 else "")

    return f"""Transform this GitHub issue into a GitQuest:

REPOSITORY: {repo}
ISSUE NUMBER: #{issue_number}
TITLE: {title}
LABELS: {", ".join(labels) if labels else "None"}
URL: {html_url}

DESCRIPTION:
\"\"\"
{truncated_body}
\"\"\"

Return a valid JSON object with the following fields:
{{
  "quest_id": "quest_{repo.replace('/', '_')}_{issue_number}",
  "quest_title": "<Catchy Game-Like Quest Title>",
  "tagline": "<One-sentence hook>",
  "difficulty": "Novice" | "Adept" | "Master",
  "category": "Bug Squashing" | "Feature Forge" | "Refactor Realm" | "Docs & Discovery",
  "xp_reward": <integer between 100 and 600>,
  "estimated_time_minutes": <integer>,
  "tags": ["<tag1>", "<tag2>"],
  "briefing": {{
    "lore_intro": "<Engaging story hook>",
    "technical_summary": "<Clear technical reality>"
  }},
  "objectives": [
    {{ "step": 1, "title": "<Step Title>", "instruction": "<What to do>" }},
    {{ "step": 2, "title": "<Step Title>", "instruction": "<What to do>" }},
    {{ "step": 3, "title": "<Step Title>", "instruction": "<What to do>" }}
  ],
  "hints": [
    {{ "level": 1, "tier": "Gentle Nudge", "hint": "<Clue>", "xp_cost": 10 }},
    {{ "level": 2, "tier": "Investigation Lead", "hint": "<Deeper Lead>", "xp_cost": 25 }},
    {{ "level": 3, "tier": "Tactical Blueprint", "hint": "<Concrete Approach>", "xp_cost": 50 }}
  ],
  "verification_checklist": [
    "<Check 1>",
    "<Check 2>"
  ]
}}
"""


# ============================================================================
# Response Sanitization & Validation
# ============================================================================

def _clean_json_response(raw_text: str) -> str:
    """Extract clean JSON text from LLM response, stripping markdown code fences."""
    text = raw_text.strip()

    # Strip markdown ```json ... ``` blocks
    fence_pattern = r"^```(?:json)?\s*([\s\S]*?)\s*```$"
    match = re.search(fence_pattern, text)
    if match:
        text = match.group(1).strip()

    # If extra commentary surrounds the JSON, extract the outermost { ... }
    if not (text.startswith("{") and text.endswith("}")):
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1]

    return text


def _get_api_client(api_key: Optional[str] = None) -> genai.Client:
    """Initialize the Google GenAI client, resolving key from parameter or environment."""
    resolved_key = (
        api_key
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )
    if not resolved_key or not resolved_key.strip():
        raise AIKeyMissingError(
            "Google GenAI API key not found. Please set GEMINI_API_KEY or GOOGLE_API_KEY in "
            "your environment, or pass api_key directly to transform_issue_to_quest()."
        )
    return genai.Client(api_key=resolved_key.strip())


# ============================================================================
# Main Service Functions
# ============================================================================

def transform_issue_to_quest(
    issue: dict[str, Any],
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> Quest:
    """Transform a normalized GitHub issue dictionary from Person 1 into a structured Quest.

    Args:
        issue: Normalized issue dictionary containing:
            - 'number' (int)
            - 'title' (str)
            - 'body' (str)
            - 'labels' (list[str])
            - 'html_url' (str)
            - 'repo' (str)
        model: Gemma/Gemini model name to use (defaults to DEFAULT_MODEL).
        api_key: Optional API key override. If None, reads from GEMINI_API_KEY.

    Returns:
        A validated Quest Pydantic model instance.

    Raises:
        AIKeyMissingError: If no API key is available.
        AISchemaValidationError: If the model's output cannot be parsed into a valid Quest.
        AIServiceError: If model generation fails.
    """
    if not isinstance(issue, dict):
        raise ValueError("Input issue must be a dictionary.")

    client = _get_api_client(api_key)
    prompt = _build_quest_prompt(issue)

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        system_instruction=QUEST_SYSTEM_INSTRUCTIONS,
        temperature=0.4,
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
    except Exception as exc:
        raise AIServiceError(f"Gemma model request failed ({model}): {exc}") from exc

    raw_output = response.text or ""
    if not raw_output.strip():
        raise AIServiceError(f"Gemma returned an empty response for issue #{issue.get('number')}.")

    cleaned_json = _clean_json_response(raw_output)

    try:
        parsed_data = json.loads(cleaned_json)
    except json.JSONDecodeError as exc:
        raise AISchemaValidationError(
            f"Failed to decode model JSON output: {exc}\nRaw Output:\n{raw_output[:500]}"
        ) from exc

    try:
        # Attach source issue reference for full traceability
        parsed_data["source_issue"] = issue
        quest = Quest.model_validate(parsed_data)
        return quest
    except ValidationError as exc:
        raise AISchemaValidationError(
            f"Model output did not match Quest schema: {exc}"
        ) from exc


def generate_quest(
    issue: dict[str, Any],
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Convenience helper that returns the Quest as a serializable dictionary.

    Useful for backend endpoints sending JSON responses directly to the frontend.
    """
    quest = transform_issue_to_quest(issue, model=model, api_key=api_key)
    return quest.model_dump()


# ============================================================================
# CLI Verification Runner
# ============================================================================

if __name__ == "__main__":
    print("=== GitQuest AI Service (Person 2) ===")
    print(f"Default Model: {DEFAULT_MODEL}")

    # Mock issue representing Person 1's backend output
    mock_issue = {
        "number": 6146,
        "title": "Add Cloudflare to Flask Hosting Platforms docs",
        "body": "Cloudflare workers supports deploying Flask applications. We have the following guide for deploying Flask workers: https://developers.cloudflare.com/workers/languages/python/packages/flask/\n\nCould we add a link to this page to the 'Hosting Platforms' section of the docs?",
        "labels": ["documentation", "good first issue"],
        "html_url": "https://github.com/pallets/flask/issues/6146",
        "repo": "pallets/flask",
    }

    print("\nInput Issue from Person 1:")
    print(json.dumps(mock_issue, indent=2))

    try:
        print("\nSending to Gemma to generate quest...")
        quest_obj = transform_issue_to_quest(mock_issue)
        print("\nGenerated Quest:")
        print(json.dumps(quest_obj.model_dump(), indent=2))
    except AIKeyMissingError as key_err:
        print(f"\n[AIKeyMissingError]: {key_err}")
        print("To test live Gemma generation, set GEMINI_API_KEY:")
        print("  $env:GEMINI_API_KEY = 'your_api_key_here'")
    except Exception as err:
        print(f"\n[{type(err).__name__}]: {err}")
