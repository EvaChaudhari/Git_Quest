"""GitHub service module for GitQuest.

Provides utility functions to parse GitHub repository URLs and fetch open issues
using the official GitHub REST API.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
import requests

# Load environment variables from .env file if available
load_dotenv()

# Constants
GITHUB_API_BASE_URL = "https://api.github.com"
MAX_ISSUES_LIMIT = 10
DEFAULT_TIMEOUT_SECONDS = 10


class GitHubServiceError(Exception):
    """Base exception for errors encountered in the GitHub service."""


class GitHubRepoNotFoundError(GitHubServiceError):
    """Raised when a GitHub repository cannot be found (HTTP 404)."""


class GitHubRateLimitError(GitHubServiceError):
    """Raised when GitHub API rate limits are exceeded (HTTP 403 / 429)."""


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    """Extract and validate the owner and repository name from a GitHub URL.

    Accepts standard GitHub repository URLs such as:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - http://github.com/owner/repo
      - https://www.github.com/owner/repo/

    Args:
        repo_url: The URL string pointing to a GitHub repository.

    Returns:
        A tuple of (owner, repo).

    Raises:
        ValueError: If the URL is empty, malformed, points to a non-GitHub host,
            or lacks a valid owner or repository name.
    """
    if not repo_url or not isinstance(repo_url, str):
        raise ValueError("Repository URL must be a non-empty string.")

    cleaned_url = repo_url.strip()
    parsed = urlparse(cleaned_url)

    # Permit URLs passed without scheme (e.g. github.com/owner/repo)
    if not parsed.scheme and (
        cleaned_url.startswith("github.com/") or cleaned_url.startswith("www.github.com/")
    ):
        cleaned_url = f"https://{cleaned_url}"
        parsed = urlparse(cleaned_url)

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(
            f"Invalid URL scheme '{parsed.scheme}'. Only HTTP and HTTPS GitHub URLs are supported."
        )

    hostname = (parsed.hostname or "").lower()
    if hostname not in ("github.com", "www.github.com"):
        raise ValueError(
            f"Non-GitHub host '{hostname or parsed.netloc}'. Only 'github.com' URLs are supported."
        )

    # Clean and split the path into segments
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]

    if len(parts) != 2:
        raise ValueError(
            f"Invalid GitHub repository URL path: '{parsed.path}'. "
            "Expected format: 'https://github.com/owner/repo'"
        )

    owner, repo = parts[0], parts[1]

    # Strip .git suffix if present
    if repo.endswith(".git"):
        repo = repo[:-4]

    # Validate owner name: alphanumeric and single hyphens, no leading/trailing hyphen
    if not re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$", owner):
        raise ValueError(f"Invalid GitHub repository owner: '{owner}'")

    # Validate repo name: alphanumeric, hyphens, underscores, dots; not empty or '.'/'..'
    if not re.match(r"^[a-zA-Z0-9_.-]+$", repo) or repo in (".", ".."):
        raise ValueError(f"Invalid GitHub repository name: '{repo}'")

    return owner, repo


def _get_headers() -> dict[str, str]:
    """Build request headers for the GitHub REST API.

    Optionally includes an Authorization header if GITHUB_TOKEN is present
    in the environment. Never exposes secrets in logs or responses.

    Returns:
        A dictionary of HTTP headers.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "GitQuest-App",
    }

    token = os.getenv("GITHUB_TOKEN")
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"

    return headers


def _normalize_issue(issue_data: dict[str, Any], owner: str, repo: str) -> dict[str, Any]:
    """Normalize raw GitHub issue data into the standardized GitQuest format.

    Args:
        issue_data: Raw issue dictionary returned by the GitHub REST API.
        owner: GitHub repository owner.
        repo: GitHub repository name.

    Returns:
        A normalized dictionary with the required schema.
    """
    raw_labels = issue_data.get("labels") or []
    labels: list[str] = []
    for label in raw_labels:
        if isinstance(label, dict):
            name = label.get("name")
            if name:
                labels.append(str(name))
        elif isinstance(label, str):
            labels.append(label)

    issue_number = issue_data.get("number")
    html_url = issue_data.get("html_url") or f"https://github.com/{owner}/{repo}/issues/{issue_number}"

    return {
        "number": issue_number,
        "title": issue_data.get("title") or "",
        "body": issue_data.get("body") or "",
        "labels": labels,
        "html_url": html_url,
        "repo": f"{owner}/{repo}",
    }


def get_issues(repo_url: str, limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve open issues for a given GitHub repository.

    Excludes pull requests and normalizes each issue into the standard structure.
    Limits results to a maximum of 10 for the prototype.

    Args:
        repo_url: The URL of the GitHub repository.
        limit: Number of issues to retrieve (capped at 10 for prototype).

    Returns:
        A list of normalized issue dictionaries.

    Raises:
        ValueError: If the repository URL is invalid.
        GitHubRepoNotFoundError: If the repository does not exist or is private without token.
        GitHubRateLimitError: If GitHub API rate limit is exceeded.
        GitHubServiceError: For network timeouts, authentication issues, or HTTP errors.
    """
    owner, repo = parse_repo_url(repo_url)

    # Prototype restriction: cap results at a maximum of 10
    target_limit = min(limit, MAX_ISSUES_LIMIT)
    if target_limit <= 0:
        return []

    api_url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/issues"
    headers = _get_headers()

    normalized_issues: list[dict[str, Any]] = []
    page = 1
    max_pages = 5  # Safety safeguard to avoid unbounded pagination while filtering PRs

    while len(normalized_issues) < target_limit and page <= max_pages:
        params: dict[str, Any] = {
            "state": "open",
            "per_page": 30,
            "page": page,
        }

        try:
            response = requests.get(
                api_url,
                headers=headers,
                params=params,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout:
            raise GitHubServiceError(
                f"Request to GitHub API timed out while fetching issues for '{owner}/{repo}'."
            ) from None
        except requests.exceptions.RequestException as err:
            raise GitHubServiceError(
                f"Network error connecting to GitHub API for '{owner}/{repo}': {err.__class__.__name__}"
            ) from None

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                raise GitHubServiceError(
                    f"Invalid JSON received from GitHub API for '{owner}/{repo}'."
                ) from None

            if not isinstance(data, list) or not data:
                break

            for item in data:
                # GitHub issues endpoint includes pull requests; exclude them
                if "pull_request" in item:
                    continue

                normalized = _normalize_issue(item, owner, repo)
                normalized_issues.append(normalized)

                if len(normalized_issues) == target_limit:
                    break

            # If fewer than per_page items returned or no next page, stop pagination
            if len(data) < 30 or "next" not in response.links:
                break

            page += 1

        elif response.status_code == 404:
            raise GitHubRepoNotFoundError(
                f"Repository '{owner}/{repo}' not found on GitHub. Verify the URL and repository visibility."
            )
        elif response.status_code in (403, 429):
            remaining = response.headers.get("x-ratelimit-remaining")
            message = "GitHub API rate limit exceeded."
            if remaining == "0":
                message = "GitHub API hourly rate limit reached."
            raise GitHubRateLimitError(
                f"{message} Please try again later or configure a GITHUB_TOKEN."
            )
        elif response.status_code == 401:
            raise GitHubServiceError(
                "GitHub authentication failed. Please verify your GITHUB_TOKEN."
            )
        else:
            raise GitHubServiceError(
                f"GitHub API request failed with HTTP status {response.status_code} for '{owner}/{repo}'."
            )

    return normalized_issues


if __name__ == "__main__":
    import json
    import sys

    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/psf/requests"
    print(f"Testing GitHub service with URL: {target_url}")
    try:
        parsed_owner, parsed_repo = parse_repo_url(target_url)
        print(f"Parsed owner: '{parsed_owner}', repo: '{parsed_repo}'")
        issues_list = get_issues(target_url, limit=2)
        print(f"Successfully retrieved {len(issues_list)} issues:")
        print(json.dumps(issues_list, indent=2))
    except Exception as err:
        print(f"Error [{err.__class__.__name__}]: {err}")
