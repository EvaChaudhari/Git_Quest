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

    # Permit URLs passed without scheme (e.g. github.com/owner/repo or owner/repo)
    if not parsed.scheme:
        if cleaned_url.startswith("github.com/") or cleaned_url.startswith("www.github.com/"):
            cleaned_url = f"https://{cleaned_url}"
            parsed = urlparse(cleaned_url)
        elif "/" in cleaned_url and len(cleaned_url.split("/")) == 2 and not any(c in cleaned_url for c in " :?#"):
            cleaned_url = f"https://github.com/{cleaned_url}"
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
    if token and token.strip() and not token.strip().startswith("your_"):
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


# Constants for resolution evidence
MAX_PATCH_EXCERPT_CHARS = 2500
IRRELEVANT_FILE_PATTERNS = (
    ".lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    ".min.js",
    ".min.css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
)


def _sanitize_patch(raw_patch: str) -> str:
    """Sanitize and truncate unified diff excerpts to safe size, stripping obvious tokens."""
    if not raw_patch:
        return ""

    # Mask likely exposed tokens/keys in diffs
    sanitized = re.sub(
        r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{8,})['\"]?",
        r"\1 = '[REDACTED_SECRET]'",
        raw_patch,
    )

    if len(sanitized) > MAX_PATCH_EXCERPT_CHARS:
        sanitized = sanitized[:MAX_PATCH_EXCERPT_CHARS] + "\n... [diff truncated for length]"

    return sanitized


def sanitize_diff_patch(filename: str, raw_patch: str) -> Optional[str]:
    """Sanitize unified diff excerpt for a specific file, skipping unwanted or binary files."""
    if not filename or not raw_patch:
        return None
    if any(filename.endswith(ext) or ext in filename for ext in IRRELEVANT_FILE_PATTERNS):
        return None
    return _sanitize_patch(raw_patch)


def get_issues(repo_url: str, limit: int = 10, state: str = "open") -> list[dict[str, Any]]:
    """Retrieve issues for a given GitHub repository.

    Excludes pull requests and normalizes each issue into the standard structure.
    Limits results to a maximum of 10 for the prototype.

    Args:
        repo_url: The URL of the GitHub repository.
        limit: Number of issues to retrieve (capped at 10 for prototype).
        state: State of issues to fetch: 'open', 'closed', or 'all' (defaults to 'open').

    Returns:
        A list of normalized issue dictionaries.

    Raises:
        ValueError: If the repository URL or state parameter is invalid.
        GitHubRepoNotFoundError: If the repository does not exist or is private without token.
        GitHubRateLimitError: If GitHub API rate limit is exceeded.
        GitHubServiceError: For network timeouts, authentication issues, or HTTP errors.
    """
    if state not in ("open", "closed", "all"):
        raise ValueError(f"Invalid state '{state}'. Expected 'open', 'closed', or 'all'.")

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
            "state": state,
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


def get_closed_issues(repo_url: str, limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve closed issues for a given repository (Stage A learning source)."""
    return get_issues(repo_url, limit=limit, state="closed")


def get_issue_resolution_evidence(
    owner_or_url: str,
    repo_or_issue_number: Any,
    issue_number: Optional[int] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Retrieve verified resolution evidence for a closed issue using GitHub REST APIs.

    Inspects issue status, timeline events, linked pull requests, merge status,
    and changed file diffs. Never invents or assumes a fix without verifiable API evidence.

    Accepts either (repo_url, issue_number) or (owner, repo, issue_number).

    Returns:
        Standardized resolution evidence dictionary:
        {
            "status": "verified" | "partial" | "unavailable",
            "issue_number": int,
            "repo": "owner/repo",
            "issue_url": str,
            "linked_pr": { ... } | None,
            "closing_commit": { ... } | None,
            "files_changed": [ ... ],
            "patch_excerpt": str | None,
            "evidence_summary": str,
            "uncertainty_notes": str | None
        }
    """
    if issue_number is None:
        owner, repo = parse_repo_url(owner_or_url)
        issue_number = int(repo_or_issue_number)
    else:
        owner = owner_or_url
        repo = str(repo_or_issue_number)
        issue_number = int(issue_number)

    base_api = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}"
    headers = _get_headers()
    issue_url = f"https://github.com/{owner}/{repo}/issues/{issue_number}"

    # 1. Fetch issue details
    try:
        issue_resp = requests.get(
            f"{base_api}/issues/{issue_number}",
            headers=headers,
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        raise GitHubServiceError(f"Network error querying issue #{issue_number}: {exc}") from exc

    if issue_resp.status_code == 404:
        raise GitHubRepoNotFoundError(f"Issue #{issue_number} or repository '{owner}/{repo}' not found.")
    elif issue_resp.status_code in (403, 429):
        raise GitHubRateLimitError("GitHub API rate limit reached while querying resolution evidence.")
    elif issue_resp.status_code != 200:
        raise GitHubServiceError(f"Failed to query issue #{issue_number} (status {issue_resp.status_code}).")

    issue_data = issue_resp.json()
    if issue_data.get("state") != "closed":
        return {
            "status": "unavailable",
            "issue_number": issue_number,
            "repo": f"{owner}/{repo}",
            "issue_url": issue_url,
            "linked_pr": None,
            "closing_commit": None,
            "files_changed": [],
            "patch_excerpt": None,
            "evidence_summary": "Issue is currently open. No resolution evidence exists.",
            "uncertainty_notes": "Open issues do not have verified closing resolutions.",
        }

    # 2. Query Timeline to find linked pull requests or closing commits
    candidate_pr_number: Optional[int] = None
    closing_commit_sha: Optional[str] = None
    closing_commit_url: Optional[str] = None

    try:
        timeline_resp = requests.get(
            f"{base_api}/issues/{issue_number}/timeline",
            headers=headers,
            params={"per_page": 50},
            timeout=timeout,
        )
        if timeline_resp.status_code == 200:
            events = timeline_resp.json()
            if isinstance(events, list):
                for event in events:
                    event_type = event.get("event")
                    if event_type == "cross-referenced":
                        source = event.get("source", {})
                        source_issue = source.get("issue", {})
                        if "pull_request" in source_issue and source_issue.get("number"):
                            candidate_pr_number = int(source_issue["number"])
                    elif event_type == "connected":
                        # Connected project / pull request item
                        subject = event.get("subject", {})
                        if subject.get("type") == "PullRequest" and subject.get("number"):
                            candidate_pr_number = int(subject["number"])
                    elif event_type == "closed":
                        commit_id = event.get("commit_id")
                        if commit_id:
                            closing_commit_sha = str(commit_id)
                            closing_commit_url = (
                                event.get("commit_url")
                                or f"https://github.com/{owner}/{repo}/commit/{commit_id}"
                            )
    except requests.exceptions.RequestException:
        # Timeline failure does not break; fallback to body regex scan
        pass

    # Fallback: scan issue body for explicit PR reference (e.g. #1234 or pull/1234)
    if not candidate_pr_number:
        body_text = issue_data.get("body") or ""
        pr_match = re.search(r"(?:pull|pr)[/#](\d+)", body_text, re.IGNORECASE)
        if pr_match:
            candidate_pr_number = int(pr_match.group(1))

    # 3. If linked pull request found, inspect PR merge status & changed files
    if candidate_pr_number:
        try:
            pr_resp = requests.get(
                f"{base_api}/pulls/{candidate_pr_number}",
                headers=headers,
                timeout=timeout,
            )
            if pr_resp.status_code == 200:
                pr_data = pr_resp.json()
                is_merged = bool(pr_data.get("merged") or pr_data.get("merged_at"))
                pr_title = pr_data.get("title") or "Untitled Pull Request"
                pr_html_url = pr_data.get("html_url") or f"https://github.com/{owner}/{repo}/pull/{candidate_pr_number}"
                merge_commit = pr_data.get("merge_commit_sha")

                linked_pr_info = {
                    "number": candidate_pr_number,
                    "title": pr_title,
                    "html_url": pr_html_url,
                    "merged": is_merged,
                    "merged_at": pr_data.get("merged_at"),
                    "merge_commit_sha": merge_commit,
                }

                if is_merged:
                    # Fetch changed files
                    files_resp = requests.get(
                        f"{base_api}/pulls/{candidate_pr_number}/files",
                        headers=headers,
                        params={"per_page": 20},
                        timeout=timeout,
                    )
                    filtered_files: list[dict[str, Any]] = []
                    collected_patches: list[str] = []

                    if files_resp.status_code == 200:
                        files_data = files_resp.json()
                        if isinstance(files_data, list):
                            for file_item in files_data:
                                fname = file_item.get("filename", "")
                                # Skip lockfiles, assets, and binaries
                                if any(fname.endswith(ext) or ext in fname for ext in IRRELEVANT_FILE_PATTERNS):
                                    continue

                                filtered_files.append(
                                    {
                                        "filename": fname,
                                        "status": file_item.get("status", "modified"),
                                        "additions": file_item.get("additions", 0),
                                        "deletions": file_item.get("deletions", 0),
                                    }
                                )

                                raw_patch = file_item.get("patch")
                                if raw_patch:
                                    collected_patches.append(f"--- a/{fname}\n+++ b/{fname}\n{raw_patch}")

                    combined_patch = "\n\n".join(collected_patches)
                    sanitized_patch = _sanitize_patch(combined_patch) if combined_patch else None
                    linked_url = linked_pr_info.get("html_url")
                    commit_url = f"https://github.com/{owner}/{repo}/commit/{merge_commit}" if merge_commit else None
                    sources = [s for s in [linked_url, commit_url] if s]

                    return {
                        "status": "verified",
                        "issue_number": issue_number,
                        "repo": f"{owner}/{repo}",
                        "issue_url": issue_url,
                        "linked_pr": linked_pr_info,
                        "linked_prs": [linked_url] if linked_url else [],
                        "merged_prs": [linked_url] if linked_url else [],
                        "closing_commit": {
                            "sha": merge_commit,
                            "html_url": commit_url,
                        } if merge_commit else None,
                        "closing_commits": [commit_url] if commit_url else [],
                        "files_changed": filtered_files,
                        "patch_excerpt": sanitized_patch,
                        "diff_excerpts": [sanitized_patch] if sanitized_patch else [],
                        "evidence_summary": f"Issue resolved by merged Pull Request #{candidate_pr_number} ('{pr_title}').",
                        "summary": f"Issue resolved by merged Pull Request #{candidate_pr_number} ('{pr_title}').",
                        "uncertainty_notes": None,
                        "evidence_sources": sources,
                    }

                else:
                    # PR exists but was not merged
                    linked_url = linked_pr_info.get("html_url")
                    return {
                        "status": "partial",
                        "issue_number": issue_number,
                        "repo": f"{owner}/{repo}",
                        "issue_url": issue_url,
                        "linked_pr": linked_pr_info,
                        "linked_prs": [linked_url] if linked_url else [],
                        "merged_prs": [],
                        "closing_commit": None,
                        "closing_commits": [],
                        "files_changed": [],
                        "patch_excerpt": None,
                        "diff_excerpts": [],
                        "evidence_summary": f"Linked Pull Request #{candidate_pr_number} ('{pr_title}') was identified, but is closed without being merged.",
                        "summary": f"Linked Pull Request #{candidate_pr_number} ('{pr_title}') was identified, but is closed without being merged.",
                        "uncertainty_notes": "PR was closed without merge; fix may have been applied via another branch or abandoned.",
                        "evidence_sources": [linked_url] if linked_url else [],
                    }
        except requests.exceptions.RequestException:
            pass

    # 4. If direct closing commit found
    if closing_commit_sha:
        commit_url = closing_commit_url or f"https://github.com/{owner}/{repo}/commit/{closing_commit_sha}"
        return {
            "status": "verified",
            "issue_number": issue_number,
            "repo": f"{owner}/{repo}",
            "issue_url": issue_url,
            "linked_pr": None,
            "linked_prs": [],
            "merged_prs": [],
            "closing_commit": {
                "sha": closing_commit_sha,
                "html_url": commit_url,
            },
            "closing_commits": [commit_url],
            "files_changed": [],
            "patch_excerpt": None,
            "diff_excerpts": [],
            "evidence_summary": f"Issue closed directly by commit {closing_commit_sha[:8]}.",
            "summary": f"Issue closed directly by commit {closing_commit_sha[:8]}.",
            "uncertainty_notes": "Direct commit resolution identified without linked pull request.",
            "evidence_sources": [commit_url],
        }

    # 5. Unavailable evidence
    return {
        "status": "unavailable",
        "issue_number": issue_number,
        "repo": f"{owner}/{repo}",
        "issue_url": issue_url,
        "linked_pr": None,
        "linked_prs": [],
        "merged_prs": [],
        "closing_commit": None,
        "closing_commits": [],
        "files_changed": [],
        "patch_excerpt": None,
        "diff_excerpts": [],
        "evidence_summary": "Issue is closed, but no merged pull request or commit was identified in the issue timeline.",
        "summary": "Issue is closed, but no merged pull request or commit was identified in the issue timeline.",
        "uncertainty_notes": "Resolution details could not be verified from the repository timeline.",
        "evidence_sources": [],
    }


def get_closed_issues_with_evidence(
    repo_url: str,
    limit: int = 5,
    fetch_evidence_details: bool = True,
) -> list[dict[str, Any]]:
    """Retrieve closed issues and annotate each with resolution evidence status."""
    issues = get_closed_issues(repo_url, limit=limit)
    if not fetch_evidence_details or not issues:
        return issues

    owner, repo = parse_repo_url(repo_url)
    annotated: list[dict[str, Any]] = []

    for issue in issues:
        issue_copy = dict(issue)
        try:
            evidence = get_issue_resolution_evidence(owner, repo, int(issue["number"]))
            issue_copy["evidence_status"] = evidence["status"]
            issue_copy["evidence_summary"] = evidence["evidence_summary"]
            issue_copy["linked_pr_number"] = (
                evidence["linked_pr"]["number"] if evidence.get("linked_pr") else None
            )
        except Exception:
            issue_copy["evidence_status"] = "unavailable"
            issue_copy["evidence_summary"] = "Evidence check encountered an error."

        annotated.append(issue_copy)

    return annotated


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
