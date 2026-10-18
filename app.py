"""GitQuest backend Flask application.

Provides endpoints for health checking and GitHub repository issue retrieval.
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
)
from github_service import (
    GitHubRateLimitError,
    GitHubRepoNotFoundError,
    GitHubServiceError,
    get_issues,
)

# Load environment variables from .env if present
load_dotenv()

# Configure logging without echoing request bodies or secrets
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure CORS specifically for development frontend origins on API routes
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:3000",
                "http://localhost:5173",
            ]
        }
    },
)


@app.route("/", methods=["GET"])
def index():
    """Root endpoint.

    Serves a minimal temporary JSON response. Can be replaced or extended
    when the frontend integration is provided.
    """
    return (
        jsonify(
            {
                "message": "GitQuest Backend API is running.",
                "endpoints": {
                    "health": "/health",
                    "issues": "/api/issues (POST)",
                    "quest": "/api/quest (POST)",
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

        logger.info(
            "Successfully generated quest '%s' (xp: %s) for issue #%s",
            validated_quest.get("quest_id", validated_quest.get("title")),
            validated_quest.get("xp"),
            issue["number"],
        )

        return jsonify({"quest": validated_quest}), 200

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
