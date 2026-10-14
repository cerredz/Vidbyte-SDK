"""FILE: vidbyte/lib/outputs/__init__.py

PURPOSE: Re-exports the provider side of output delivery: the connector base, its helpers, and one connector class per destination.
ROLE IN CODEBASE: Imported by vidbyte/agents/output/__init__.py, which publishes the connectors next to the agent-side contract.
ARCHITECTURE NOTE: Provider work only; nothing in this package imports vidbyte.agents, and connectors satisfy OutputConnector structurally.
COMMON MODIFICATION PATTERNS: Add a new connector's import and its __all__ entry here together.
KNOWN EDGE CASES: The helper classes are exported for connector authors but are not root vidbyte exports.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/
"""

from __future__ import annotations

from vidbyte.lib.outputs.adf import OutputAdf
from vidbyte.lib.outputs.base import BaseOutput, OutputArguments
from vidbyte.lib.outputs.confluence import ConfluencePageOutput
from vidbyte.lib.outputs.delivery import OutputHttp, OutputSmtp
from vidbyte.lib.outputs.discord import DiscordOutput
from vidbyte.lib.outputs.email import EmailOutput
from vidbyte.lib.outputs.github import GitHubIssueOutput
from vidbyte.lib.outputs.github_job_summary import GitHubJobSummaryOutput
from vidbyte.lib.outputs.gitlab import GitLabIssueOutput
from vidbyte.lib.outputs.google_chat import GoogleChatOutput
from vidbyte.lib.outputs.hubspot import HubSpotTaskOutput
from vidbyte.lib.outputs.jira import JiraIssueOutput
from vidbyte.lib.outputs.linear import LinearIssueOutput
from vidbyte.lib.outputs.notion import NotionPageOutput
from vidbyte.lib.outputs.slack import SlackOutput
from vidbyte.lib.outputs.teams import TeamsOutput
from vidbyte.lib.outputs.telegram import TelegramOutput
from vidbyte.lib.outputs.text import OutputText
from vidbyte.lib.outputs.typefully import TypefullyDraftOutput
from vidbyte.lib.outputs.webhook import WebhookOutput

__all__ = [
    "BaseOutput",
    "ConfluencePageOutput",
    "DiscordOutput",
    "EmailOutput",
    "GitHubIssueOutput",
    "GitHubJobSummaryOutput",
    "GitLabIssueOutput",
    "GoogleChatOutput",
    "HubSpotTaskOutput",
    "JiraIssueOutput",
    "LinearIssueOutput",
    "NotionPageOutput",
    "OutputAdf",
    "OutputArguments",
    "OutputHttp",
    "OutputSmtp",
    "OutputText",
    "SlackOutput",
    "TeamsOutput",
    "TelegramOutput",
    "TypefullyDraftOutput",
    "WebhookOutput",
]
