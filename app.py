"""GitQuest backend Flask application.

Provides endpoints for health checking, repository issue exploration,
Stage A training quests, Stage B open-issue challenges, and gamification.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

from ai_service import (
    AIKeyMissingError,
    AISchemaValidationError,
    AIServiceError,
    generate_quest,
    generate_training_quest,
    mask_quest_hints,
)
from database import DEMO_USER_ID, init_db
from gamification import (
    DEFAULT_CONFIG,
    DuplicateQuestCompletionError,
    InsufficientXPError,
    InvalidHintTierError,
    QuestNotFoundError,
    UserNotFoundError,
    award_quest_completion,
    get_quest,
    get_unlocked_hints,
    get_user_profile,
    purchase_hint,
    record_quest,
)
from github_service import (
    GitHubRateLimitError,
    GitHubRepoNotFoundError,
    GitHubServiceError,
    get_closed_issues_with_evidence,
    get_issue_resolution_evidence,
    get_issues,
)

# Load environment variables from .env if present
load_dotenv()

# Initialize SQLite database schema
init_db()

# Configure logging without echoing request bodies or secrets
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure CORS specifically for development and configured frontend origins on API routes
_raw_origins = os.getenv("GITQUEST_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ALLOWED_ORIGINS
        }
    },
)


@app.route("/", methods=["GET"])
def index():
    """Root endpoint.

    Serves API metadata and available endpoint routes.
    """
    return (
        jsonify(
            {
                "message": "GitQuest Backend API is running.",
                "endpoints": {
                    "health": "/health (GET)",
                    "issues": "/api/issues (POST)",
                    "quest": "/api/quest (POST)",
                    "training_issues": "/api/training/issues (POST)",
                    "training_quest": "/api/training/quest (POST)",
                    "hint_unlock": "/api/quest/hint/unlock (POST)",
                    "quest_complete": "/api/quest/complete (POST)",
                    "user_profile": "/api/user/profile (GET)",
                },
            }
        ),
        200,
    )


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint.

    Returns:
        JSON response with status 'ok'.
    """
    return jsonify({"status": "ok"}), 200


@app.route("/api/issues", methods=["POST"])
def fetch_issues():
    """Retrieve open issues for a specified GitHub repository.

    Expects JSON body:
        {"repo_url": "https://github.com/owner/repo"}

    Returns:
        JSON response with issues list and count:
        {
            "issues": [...],
            "count": 0
        }
    """
    if not request.is_json:
        return (
            jsonify({"error": "Request body must be JSON with Content-Type: application/json."}),
            400,
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return (
            jsonify({"error": "Invalid JSON payload. Expected a JSON object."}),
            400,
        )

    repo_url = data.get("repo_url")
    if not repo_url or not isinstance(repo_url, str) or not repo_url.strip():
        return (
            jsonify({"error": "Field 'repo_url' is required and must be a non-empty string."}),
            400,
        )

    # Optional limit parameter, capped by service at 10 for prototype
    limit = data.get("limit", 10)
    if not isinstance(limit, int):
        return (
            jsonify({"error": "Field 'limit' must be an integer if provided."}),
            400,
        )

    try:
        issues = get_issues(repo_url.strip(), limit=limit)
        return (
            jsonify(
                {
                    "issues": issues,
                    "count": len(issues),
                }
            ),
            200,
        )

    except ValueError as err:
        # Invalid URL format, non-GitHub host, or missing owner/repo
        logger.warning("Invalid repository URL provided: %s", str(err))
        return jsonify({"error": str(err)}), 400

    except GitHubRepoNotFoundError as err:
        # 404 from GitHub API
        logger.info("Repository not found: %s", str(err))
        return jsonify({"error": str(err)}), 404

    except GitHubRateLimitError as err:
        # Rate limit reached
        logger.warning("GitHub rate limit encountered: %s", str(err))
        return jsonify({"error": str(err)}), 429

    except GitHubServiceError as err:
        # Network errors, timeouts, or upstream HTTP failures
        logger.error("GitHub service error: %s", str(err))
        return jsonify({"error": str(err)}), 502

    except Exception:
        # Catch-all to prevent stack traces or internal secrets leaking
        logger.exception("Unexpected error processing /api/issues request.")
        return jsonify({"error": "An internal server error occurred."}), 500


@app.route("/api/training/issues", methods=["POST"])
def fetch_training_issues():
    """Retrieve closed issues with resolution evidence for a specified GitHub repository.

    Expects JSON body:
        {"repo_url": "https://github.com/owner/repo", "limit": 5}

    Returns:
        JSON response with closed issues list and count:
        {
            "issues": [...],
            "count": 0
        }
    """
    if not request.is_json:
        return (
            jsonify({"error": "Request body must be JSON with Content-Type: application/json."}),
            400,
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return (
            jsonify({"error": "Invalid JSON payload. Expected a JSON object."}),
            400,
        )

    repo_url = data.get("repo_url")
    if not repo_url or not isinstance(repo_url, str) or not repo_url.strip():
        return (
            jsonify({"error": "Field 'repo_url' is required and must be a non-empty string."}),
            400,
        )

    limit = data.get("limit", 5)
    if not isinstance(limit, int):
        return (
            jsonify({"error": "Field 'limit' must be an integer if provided."}),
            400,
        )

    try:
        issues = get_closed_issues_with_evidence(repo_url.strip(), limit=limit)
        return (
            jsonify(
                {
                    "issues": issues,
                    "count": len(issues),
                }
            ),
            200,
        )

    except ValueError as err:
        logger.warning("Invalid repository URL provided: %s", str(err))
        return jsonify({"error": str(err)}), 400

    except GitHubRepoNotFoundError as err:
        logger.info("Repository not found: %s", str(err))
        return jsonify({"error": str(err)}), 404

    except GitHubRateLimitError as err:
        logger.warning("GitHub rate limit encountered: %s", str(err))
        return jsonify({"error": str(err)}), 429

    except GitHubServiceError as err:
        logger.error("GitHub service error: %s", str(err))
        return jsonify({"error": str(err)}), 502

    except Exception:
        logger.exception("Unexpected error processing /api/training/issues request.")
        return jsonify({"error": "An internal server error occurred."}), 500


def _validate_and_normalize_issue_payload(data: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Validate incoming issue data for title, repository, URL, body, labels, and number."""
    if not isinstance(data, dict):
        return None, "Invalid JSON payload. Expected a JSON object."

    issue = data.get("issue") if "issue" in data else data
    if not isinstance(issue, dict) or not issue:
        return None, "Field 'issue' is required and must be a non-empty object."

    # Validate number
    number = issue.get("number")
    if number is None or not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        return None, "Invalid issue: 'number' is required and must be a positive integer."

    # Validate title
    title = issue.get("title")
    if not isinstance(title, str) or not title.strip():
        return None, "Invalid issue: 'title' is required and must be a non-empty string."

    # Validate repo / repository
    repo = issue.get("repo") or issue.get("repository")
    if not isinstance(repo, str) or not repo.strip():
        return None, "Invalid issue: 'repo' is required and must be a non-empty string."

    # Validate html_url / url if provided
    html_url = issue.get("html_url") or issue.get("url")
    if html_url is not None and not isinstance(html_url, str):
        return None, "Invalid issue: 'html_url' must be a string if provided."

    # Validate body if provided
    body = issue.get("body", "")
    if body is not None and not isinstance(body, str):
        return None, "Invalid issue: 'body' must be a string if provided."

    # Validate labels if provided
    labels = issue.get("labels", [])
    if labels is not None and not isinstance(labels, list):
        return None, "Invalid issue: 'labels' must be a list if provided."

    # Construct clean normalized issue dictionary for Person 2's service
    clean_issue: dict[str, Any] = {
        "number": number,
        "title": title.strip(),
        "repo": repo.strip(),
        "body": body if isinstance(body, str) else "",
        "labels": [str(l) for l in labels] if isinstance(labels, list) else [],
        "html_url": html_url.strip() if isinstance(html_url, str) else f"https://github.com/{repo.strip()}/issues/{number}",
    }
    return clean_issue, None


def _validate_and_format_quest(raw_quest: dict[str, Any]) -> dict[str, Any]:
    """Validate that the returned quest contains required fields and format output.

    Required fields:
        - title
        - explanation
        - difficulty
        - steps
        - hints
        - xp
    """
    if not isinstance(raw_quest, dict):
        raise AISchemaValidationError("AI service returned an invalid quest object.")

    # Format quest dictionary while preserving Person 2's structure
    quest = dict(raw_quest)

    # Resolve 'title'
    title = raw_quest.get("title") or raw_quest.get("quest_title")
    if not title or not isinstance(title, str) or not title.strip():
        raise AISchemaValidationError("Generated quest missing required 'title' field.")
    quest["title"] = title.strip()

    # Resolve 'explanation'
    explanation = raw_quest.get("explanation")
    if not explanation and isinstance(raw_quest.get("briefing"), dict):
        briefing = raw_quest["briefing"]
        explanation = briefing.get("technical_summary") or briefing.get("lore_intro")
    if not explanation:
        explanation = raw_quest.get("tagline")
    if not explanation or not isinstance(explanation, str) or not explanation.strip():
        raise AISchemaValidationError("Generated quest missing required 'explanation' field.")
    quest["explanation"] = explanation.strip()

    # Resolve 'difficulty'
    difficulty = raw_quest.get("difficulty")
    if not difficulty or not isinstance(difficulty, str) or not difficulty.strip():
        raise AISchemaValidationError("Generated quest missing required 'difficulty' field.")
    quest["difficulty"] = difficulty.strip()

    # Resolve 'steps'
    steps = raw_quest.get("steps") or raw_quest.get("objectives")
    if steps is None or not isinstance(steps, list) or len(steps) == 0:
        raise AISchemaValidationError("Generated quest missing required 'steps' field.")
    quest["steps"] = steps

    # Resolve 'hints'
    hints = raw_quest.get("hints")
    if hints is None or not isinstance(hints, list):
        raise AISchemaValidationError("Generated quest missing required 'hints' field.")
    quest["hints"] = hints

    # Resolve 'xp'
    xp = raw_quest.get("xp") if raw_quest.get("xp") is not None else raw_quest.get("xp_reward")
    if xp is None or not isinstance(xp, (int, float)) or isinstance(xp, bool):
        raise AISchemaValidationError("Generated quest missing required 'xp' field.")
    quest["xp"] = int(xp)

    return quest


@app.route("/api/quest", methods=["POST"])
def generate_quest_endpoint():
    """Generate a gamified GitQuest from a normalized GitHub issue.

    Expects JSON body with an 'issue' dictionary, or the issue dictionary directly:
        {"issue": {"number": 1, "title": "...", "body": "...", "repo": "...", "labels": [], "html_url": "..."}}

    Optional fields in payload:
        "model": optional Gemma/Gemini model name override.

    Returns:
        JSON response with HTTP 200:
        {"quest": {...}}
    """
    if not request.is_json:
        return (
            jsonify({"error": "Request body must be JSON with Content-Type: application/json."}),
            400,
        )

    data = request.get_json(silent=True)
    issue, error = _validate_and_normalize_issue_payload(data)
    if error or not issue:
        return jsonify({"error": error or "Invalid issue payload."}), 400

    # Optional model override
    model_override = data.get("model") if isinstance(data, dict) else None
    kwargs: dict[str, Any] = {}
    if isinstance(model_override, str) and model_override.strip():
        kwargs["model"] = model_override.strip()

    logger.info(
        "Generating quest for issue #%s in '%s' (title: '%s')",
        issue["number"],
        issue["repo"],
        issue["title"],
    )

    try:
        raw_quest = generate_quest(issue, **kwargs)
        validated_quest = _validate_and_format_quest(raw_quest)

        quest_id = validated_quest.get("quest_id") or f"quest_{issue['repo'].replace('/', '_')}_{issue['number']}"
        validated_quest["quest_id"] = quest_id
        validated_quest["stage"] = "B"

        # Record in database for progression and hint tracking
        record_quest(
            quest_id=quest_id,
            repo=issue["repo"],
            issue_number=issue["number"],
            stage="B",
            title=validated_quest.get("title", f"Challenge #{issue['number']}"),
            difficulty=validated_quest.get("difficulty", "Novice"),
            base_xp=int(validated_quest.get("xp", 100)),
            raw_payload=validated_quest,
        )

        # Protect locked hints: mask them so locked hints are never leaked
        unlocked_hint_tiers = get_unlocked_hints(quest_id=quest_id, user_id=DEMO_USER_ID)
        safe_quest = mask_quest_hints(validated_quest, unlocked_hint_levels=unlocked_hint_tiers)

        logger.info(
            "Successfully generated quest '%s' (xp: %s) for issue #%s",
            quest_id,
            safe_quest.get("xp"),
            issue["number"],
        )

        return jsonify({"quest": safe_quest}), 200

    except ValueError as err:
        logger.warning("Validation error in /api/quest: %s", str(err))
        return jsonify({"error": str(err)}), 400

    except AIKeyMissingError as err:
        logger.error("AI service configuration error: %s", str(err))
        return (
            jsonify({"error": "AI service is not configured (missing API key)."}),
            503,
        )

    except AISchemaValidationError as err:
        logger.error("AI service schema validation error: %s", str(err))
        return (
            jsonify({"error": "Failed to generate a valid quest from the AI service response."}),
            502,
        )

    except AIServiceError as err:
        logger.error("AI service error: %s", str(err))
        return (
            jsonify({"error": "AI quest generation service encountered an error."}),
            502,
        )

    except Exception:
        logger.exception("Unexpected error processing /api/quest request.")
        return jsonify({"error": "An internal server error occurred."}), 500


@app.route("/api/training/quest", methods=["POST"])
def generate_training_quest_endpoint():
    """Generate a Stage A training quest from a closed GitHub issue and verified evidence.

    Expects JSON body:
        {"issue": {"number": 1, "title": "...", "repo": "...", ...}}

    Optional fields:
        "model": optional Gemma/Gemini model name override.
    """
    if not request.is_json:
        return (
            jsonify({"error": "Request body must be JSON with Content-Type: application/json."}),
            400,
        )

    data = request.get_json(silent=True)
    issue, error = _validate_and_normalize_issue_payload(data)
    if error or not issue:
        return jsonify({"error": error or "Invalid issue payload."}), 400

    model_override = data.get("model") if isinstance(data, dict) else None
    kwargs: dict[str, Any] = {}
    if isinstance(model_override, str) and model_override.strip():
        kwargs["model"] = model_override.strip()

    repo = issue["repo"]
    issue_number = issue["number"]

    # Authoritative resolution evidence retrieval on the server (never trust client evidence)
    try:
        evidence = get_issue_resolution_evidence(repo, issue_number)
    except Exception as exc:
        logger.warning("Failed to fetch resolution evidence for %s#%s: %s", repo, issue_number, exc)
        evidence = {
            "status": "unavailable",
            "issue_number": issue_number,
            "repo": repo,
            "summary": "Resolution evidence could not be retrieved from GitHub.",
            "evidence_sources": [],
        }

    try:
        raw_quest = generate_training_quest(issue, resolution_evidence=evidence, **kwargs)
        validated_quest = _validate_and_format_quest(raw_quest)

        quest_id = validated_quest.get("quest_id") or f"quest_{repo.replace('/', '_')}_{issue_number}_training"
        validated_quest["quest_id"] = quest_id
        validated_quest["stage"] = "A"

        # Record quest in database with standard Stage A reward (50 XP)
        record_quest(
            quest_id=quest_id,
            repo=repo,
            issue_number=issue_number,
            stage="A",
            title=validated_quest.get("title", f"Training Quest #{issue_number}"),
            difficulty=validated_quest.get("difficulty", "Novice"),
            base_xp=int(DEFAULT_CONFIG.stage_a_completion_xp),
            raw_payload=validated_quest,
        )

        return jsonify({"quest": validated_quest}), 200

    except ValueError as err:
        logger.warning("Validation error in /api/training/quest: %s", str(err))
        return jsonify({"error": str(err)}), 400

    except AIKeyMissingError as err:
        logger.error("AI service configuration error: %s", str(err))
        return (
            jsonify({"error": "AI service is not configured (missing API key)."}),
            503,
        )

    except AISchemaValidationError as err:
        logger.error("AI service schema validation error: %s", str(err))
        return (
            jsonify({"error": "Failed to generate a valid quest from the AI service response."}),
            502,
        )

    except AIServiceError as err:
        logger.error("AI service error: %s", str(err))
        return (
            jsonify({"error": "AI quest generation service encountered an error."}),
            502,
        )

    except Exception:
        logger.exception("Unexpected error processing /api/training/quest request.")
        return jsonify({"error": "An internal server error occurred."}), 500


@app.route("/api/quest/hint/unlock", methods=["POST"])
def unlock_hint_endpoint():
    """Unlock a progressive hint tier using the demo user's earned XP.

    Expects JSON body:
        {"quest_id": "quest_owner_repo_101", "hint_tier": 1}

    Returns HTTP 200 with unlocked hint and updated balance on success,
    or HTTP 400 with safe error on insufficient balance / invalid tier.
    """
    if not request.is_json:
        return (
            jsonify({"error": "Request body must be JSON with Content-Type: application/json."}),
            400,
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return (
            jsonify({"error": "Invalid JSON payload. Expected a JSON object."}),
            400,
        )

    quest_id = data.get("quest_id")
    if not quest_id or not isinstance(quest_id, str) or not quest_id.strip():
        return (
            jsonify({"error": "Field 'quest_id' is required and must be a non-empty string."}),
            400,
        )
    quest_id = quest_id.strip()

    raw_tier = data.get("hint_tier") if "hint_tier" in data else data.get("hint_level")
    if raw_tier is None or not isinstance(raw_tier, int) or isinstance(raw_tier, bool):
        return (
            jsonify({"error": "Field 'hint_tier' (or 'hint_level') is required and must be an integer (1, 2, or 3)."}),
            400,
        )
    hint_tier = int(raw_tier)

    try:
        result = purchase_hint(
            quest_id=quest_id,
            hint_tier=hint_tier,
            user_id=DEMO_USER_ID,
        )

        # Retrieve hint details from stored quest payload if available
        stored_quest = get_quest(quest_id)
        hint_text = "Progressive guidance unlocked."
        tier_name = f"Tier {hint_tier}"
        if stored_quest and stored_quest.get("parsed_payload"):
            payload = stored_quest["parsed_payload"]
            for h in payload.get("hints", []):
                if isinstance(h, dict) and h.get("level") == hint_tier:
                    hint_text = h.get("hint", hint_text)
                    tier_name = h.get("tier", tier_name)
                    break

        return (
            jsonify(
                {
                    "success": True,
                    "quest_id": quest_id,
                    "hint_tier": hint_tier,
                    "tier_name": tier_name,
                    "xp_deducted": result["xp_deducted"],
                    "balance": result["balance"],
                    "already_purchased": result["already_purchased"],
                    "hint": hint_text,
                    "unlocked_hint": {
                        "level": hint_tier,
                        "tier": tier_name,
                        "hint": hint_text,
                        "locked": False,
                    },
                }
            ),
            200,
        )

    except InvalidHintTierError as err:
        return jsonify({"error": str(err)}), 400

    except InsufficientXPError as err:
        return jsonify({"error": str(err)}), 400

    except QuestNotFoundError as err:
        return jsonify({"error": str(err)}), 404

    except Exception:
        logger.exception("Unexpected error processing /api/quest/hint/unlock request.")
        return jsonify({"error": "An internal server error occurred."}), 500


@app.route("/api/quest/complete", methods=["POST"])
def complete_quest_endpoint():
    """Record completion of a quest and award authoritative XP and habit consistency.

    Expects JSON body:
        {"quest_id": "quest_owner_repo_101", "stage": "A" (optional)}

    Prevents duplicate XP awards and duplicate habit streaks.
    """
    if not request.is_json:
        return (
            jsonify({"error": "Request body must be JSON with Content-Type: application/json."}),
            400,
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return (
            jsonify({"error": "Invalid JSON payload. Expected a JSON object."}),
            400,
        )

    quest_id = data.get("quest_id")
    if not quest_id or not isinstance(quest_id, str) or not quest_id.strip():
        return (
            jsonify({"error": "Field 'quest_id' is required and must be a non-empty string."}),
            400,
        )
    quest_id = quest_id.strip()

    # Determine stage: explicitly supplied, or resolved from database record
    stage = data.get("stage")
    if not stage or stage not in ("A", "B"):
        stored_quest = get_quest(quest_id)
        stage = stored_quest.get("stage", "B") if stored_quest else "B"

    try:
        result = award_quest_completion(
            quest_id=quest_id,
            stage=stage,
            user_id=DEMO_USER_ID,
        )

        return (
            jsonify(
                {
                    "success": True,
                    "quest_id": quest_id,
                    "stage": stage,
                    "awarded_xp": result["awarded_xp"],
                    "balance": result["balance"],
                    "consistency_score": result["consistency_score"],
                    "stage_b_unlocked": result["stage_b_unlocked"],
                    "already_completed": False,
                    "message": f"Quest '{quest_id}' completed successfully.",
                }
            ),
            200,
        )

    except DuplicateQuestCompletionError as err:
        return (
            jsonify(
                {
                    "error": str(err),
                    "already_completed": True,
                    "quest_id": quest_id,
                }
            ),
            400,
        )

    except QuestNotFoundError as err:
        return jsonify({"error": str(err)}), 404

    except Exception:
        logger.exception("Unexpected error processing /api/quest/complete request.")
        return jsonify({"error": "An internal server error occurred."}), 500


@app.route("/api/user/profile", methods=["GET"])
def get_user_profile_endpoint():
    """Retrieve demo user gamification stats, XP balance, habit consistency, and Stage B unlock status."""
    try:
        profile = get_user_profile(user_id=DEMO_USER_ID)
        return jsonify({"profile": profile}), 200
    except UserNotFoundError as err:
        return jsonify({"error": str(err)}), 404
    except Exception:
        logger.exception("Unexpected error processing /api/user/profile request.")
        return jsonify({"error": "An internal server error occurred."}), 500


@app.errorhandler(404)
def handle_not_found(error):
    """Handle 404 Not Found as clean JSON."""
    return jsonify({"error": "Endpoint not found."}), 404


@app.errorhandler(405)
def handle_method_not_allowed(error):
    """Handle 405 Method Not Allowed as clean JSON."""
    return jsonify({"error": "Method not allowed for this endpoint."}), 405


@app.errorhandler(500)
def handle_internal_server_error(error):
    """Handle 500 Internal Server Error without leaking details."""
    return jsonify({"error": "An internal server error occurred."}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=False)
