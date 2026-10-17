"""GitQuest backend Flask application.

Provides endpoints for health checking and GitHub repository issue retrieval.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask, jsonify, request

from github_service import (
    GitHubRateLimitError,
    GitHubRepoNotFoundError,
    GitHubServiceError,
    get_issues,
)

# Configure logging without echoing request bodies or secrets
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)


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
