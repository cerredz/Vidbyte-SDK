"""FILE: vidbyte/lib/enums/outputs.py

PURPOSE: Names the places an agent reply can be delivered to, the outcome of each delivery, the HTTP methods a connector may use, and the social platforms a Typefully draft can target.
ROLE IN CODEBASE: Used by the output records, the provider connectors and OutputHttp in vidbyte/lib/outputs/, and the dispatcher in vidbyte/agents/output/.
ARCHITECTURE NOTE: Plain value enums with no behavior; re-exported from vidbyte/lib/enums/__init__.py.
COMMON MODIFICATION PATTERNS: A new destination adds one OutputDestination member, one connector module, and one credential environment variable.
KNOWN EDGE CASES: Member values appear in receipts and error messages, so renaming one is a breaking change.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_contract.py
"""

from __future__ import annotations

from enum import Enum


class OutputDestination(str, Enum):
    """The kind of place a connector delivers a finished reply to."""

    SLACK = "slack"
    DISCORD = "discord"
    TEAMS = "teams"
    GOOGLE_CHAT = "google_chat"
    TELEGRAM = "telegram"
    EMAIL = "email"
    GITHUB_ISSUE = "github_issue"
    LINEAR_ISSUE = "linear_issue"
    JIRA_ISSUE = "jira_issue"
    NOTION_PAGE = "notion_page"
    WEBHOOK = "webhook"
    GITLAB_ISSUE = "gitlab_issue"
    GITHUB_JOB_SUMMARY = "github_job_summary"
    CONFLUENCE_PAGE = "confluence_page"
    TYPEFULLY_DRAFT = "typefully_draft"
    HUBSPOT_TASK = "hubspot_task"


class DeliveryStatus(str, Enum):
    """The final outcome of delivering one reply to one connector."""

    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class OutputMethod(str, Enum):
    """The HTTP method of one request a connector sends through OutputHttp."""

    GET = "GET"
    POST = "POST"
    PATCH = "PATCH"


class TypefullyPlatform(str, Enum):
    """A social platform a Typefully draft can be prepared for."""

    X = "x"
    LINKEDIN = "linkedin"
    THREADS = "threads"
    BLUESKY = "bluesky"
    MASTODON = "mastodon"


__all__ = ["DeliveryStatus", "OutputDestination", "OutputMethod", "TypefullyPlatform"]
