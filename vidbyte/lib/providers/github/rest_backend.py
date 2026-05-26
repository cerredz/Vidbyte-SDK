"""Context Protocol Header

Description:
    Implements a GitHub REST API backend using HttpTransport.
Purpose:
    Provides issue and pull request management via the GitHub REST API
    authenticated with a GITHUB_TOKEN environment variable.
Architecture:
    - Uses HttpTransport for HTTP requests to api.github.com.
    - Requires GITHUB_TOKEN env var for authentication.
    - Formats API responses as human-readable text for agent consumption.
    - is_available() checks for the GITHUB_TOKEN env var.
Relations:
    Related to vidbyte.lib.providers.github.base and vidbyte.lib.http.transport.
"""

from __future__ import annotations

import json
import logging
import os
from urllib.parse import urlencode

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.lib.providers.github.base import BaseGitHubBackend

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubRestBackend(BaseGitHubBackend):
    def __init__(self) -> None:
        self._transport = HttpTransport()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "vidbyte-sdk",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, path: str, headers: dict[str, str] | None = None, json_body: dict | None = None) -> str:
        try:
            response = self._transport.request(
                method=method,
                url=f"{API_BASE}{path}",
                headers=headers or self._headers(),
                json_body=json_body,
            )
            if response.status_code >= 400:
                return f"GitHub API error ({response.status_code}): {response.body[:1000]}"
            return response.body
        except Exception as exc:
            logger.exception("GitHub API request failed")
            return f"GitHub API request failed: {exc}"

    async def list_issues(self, repo: str, state: str, labels: str | None) -> str:
        params = {"state": state, "per_page": "30"}
        if labels:
            params["labels"] = labels
        query = urlencode(params)
        raw = self._request("GET", f"/repos/{repo}/issues?{query}")
        try:
            issues = json.loads(raw)
            if isinstance(issues, dict) and issues.get("message"):
                return raw
            lines = []
            for issue in issues:
                if "pull_request" in issue:
                    continue
                labels_str = ", ".join(label["name"] for label in issue.get("labels", []))
                lines.append(
                    f"#{issue['number']} [{issue['state']}] {issue['title']} "
                    f"(by {issue.get('user', {}).get('login', 'unknown')})"
                )
                if labels_str:
                    lines.append(f"  Labels: {labels_str}")
                lines.append(f"  URL: {issue.get('html_url', '')}")
                lines.append("")
            if not lines:
                return f"No issues found in {repo} (state={state})"
            return "\n".join(lines)
        except (json.JSONDecodeError, KeyError, TypeError):
            return raw

    async def get_issue(self, repo: str, issue_number: int) -> str:
        raw = self._request("GET", f"/repos/{repo}/issues/{issue_number}")
        try:
            issue = json.loads(raw)
            if isinstance(issue, dict) and issue.get("message"):
                return raw
            labels = ", ".join(label["name"] for label in issue.get("labels", []))
            return (
                f"#{issue['number']} [{issue['state']}] {issue['title']}\n"
                f"Author: {issue.get('user', {}).get('login', 'unknown')}\n"
                f"Labels: {labels or 'none'}\n"
                f"URL: {issue.get('html_url', '')}\n"
                f"Created: {issue.get('created_at', '')}\n"
                f"Updated: {issue.get('updated_at', '')}\n\n"
                f"{issue.get('body', '') or 'No description'}"
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return raw

    async def create_issue(self, repo: str, title: str, body: str) -> str:
        raw = self._request(
            "POST",
            f"/repos/{repo}/issues",
            json_body={"title": title, "body": body},
        )
        try:
            issue = json.loads(raw)
            if isinstance(issue, dict) and issue.get("number"):
                return f"Issue created: #{issue['number']} - {issue.get('html_url', '')}"
            return raw
        except json.JSONDecodeError:
            return raw

    async def list_prs(self, repo: str, state: str) -> str:
        params = {"state": state, "per_page": "30"}
        query = urlencode(params)
        raw = self._request("GET", f"/repos/{repo}/pulls?{query}")
        try:
            prs = json.loads(raw)
            if isinstance(prs, dict) and prs.get("message"):
                return raw
            lines = []
            for pr in prs:
                lines.append(
                    f"#{pr['number']} [{pr['state']}] {pr['title']} "
                    f"(by {pr.get('user', {}).get('login', 'unknown')})"
                )
                lines.append(f"  Branch: {pr.get('head', {}).get('ref', '')} -> {pr.get('base', {}).get('ref', '')}")
                lines.append(f"  Draft: {pr.get('draft', False)}")
                lines.append(f"  URL: {pr.get('html_url', '')}")
                lines.append("")
            if not lines:
                return f"No pull requests found in {repo} (state={state})"
            return "\n".join(lines)
        except (json.JSONDecodeError, KeyError, TypeError):
            return raw

    async def get_pr(self, repo: str, pr_number: int) -> str:
        raw = self._request("GET", f"/repos/{repo}/pulls/{pr_number}")
        try:
            pr = json.loads(raw)
            if isinstance(pr, dict) and pr.get("message"):
                return raw
            return (
                f"#{pr['number']} [{pr['state']}] {pr['title']}\n"
                f"Author: {pr.get('user', {}).get('login', 'unknown')}\n"
                f"Branch: {pr.get('head', {}).get('ref', '')} -> {pr.get('base', {}).get('ref', '')}\n"
                f"Draft: {pr.get('draft', False)}\n"
                f"URL: {pr.get('html_url', '')}\n"
                f"Created: {pr.get('created_at', '')}\n"
                f"Updated: {pr.get('updated_at', '')}\n\n"
                f"{pr.get('body', '') or 'No description'}"
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return raw

    async def create_pr(self, repo: str, title: str, body: str, head: str, base: str, draft: bool) -> str:
        raw = self._request(
            "POST",
            f"/repos/{repo}/pulls",
            json_body={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": draft,
            },
        )
        try:
            pr = json.loads(raw)
            if isinstance(pr, dict) and pr.get("number"):
                return f"PR created: #{pr['number']} - {pr.get('html_url', '')}"
            return raw
        except json.JSONDecodeError:
            return raw

    async def get_pr_diff(self, repo: str, pr_number: int) -> str:
        headers = self._headers(extra={"Accept": "application/vnd.github.diff"})
        raw = self._request("GET", f"/repos/{repo}/pulls/{pr_number}", headers=headers)
        return raw

    async def add_pr_comment(self, repo: str, pr_number: int, body: str, commit_id: str | None, file: str | None, line: int | None) -> str:
        payload: dict = {"body": body}
        if commit_id:
            payload["commit_id"] = commit_id
        if file:
            payload["path"] = file
        if line is not None:
            payload["line"] = line

        if commit_id and file and line is not None:
            raw = self._request(
                "POST",
                f"/repos/{repo}/pulls/{pr_number}/comments",
                json_body=payload,
            )
            try:
                comment = json.loads(raw)
                if isinstance(comment, dict) and comment.get("id"):
                    return f"Review comment added: {comment.get('html_url', '')}"
                return raw
            except json.JSONDecodeError:
                return raw
        else:
            raw = self._request(
                "POST",
                f"/repos/{repo}/issues/{pr_number}/comments",
                json_body={"body": body},
            )
            try:
                comment = json.loads(raw)
                if isinstance(comment, dict) and comment.get("id"):
                    return f"Comment added: {comment.get('html_url', '')}"
                return raw
            except json.JSONDecodeError:
                return raw

    async def is_available(self) -> bool:
        token = os.environ.get("GITHUB_TOKEN", "")
        return bool(token)


__all__ = ["GitHubRestBackend"]
