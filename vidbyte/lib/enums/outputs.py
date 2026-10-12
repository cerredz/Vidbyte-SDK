"""FILE: vidbyte/lib/enums/outputs.py

PURPOSE: Names the places an agent reply can be delivered to and the outcome of each delivery.
ROLE IN CODEBASE: Used by the output records, the provider connectors in vidbyte/lib/outputs/, and the dispatcher in vidbyte/agents/output/.
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


class DeliveryStatus(str, Enum):
    """The final outcome of delivering one reply to one connector."""

    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


__all__ = ["DeliveryStatus", "OutputDestination"]
