"""FILE: vidbyte/agents/output/__init__.py

PURPOSE: Publishes everything a developer needs to deliver agent replies: the OutputConnector contract, OutputDispatcher, the eleven connectors, and the records, enums, and error they use.
ROLE IN CODEBASE: Imported by vidbyte/__init__.py for the root exports and by BaseAgent and JevAgentSettings through its submodules.
ARCHITECTURE NOTE: The contract and the linking live here; the connectors, records, enums, and error are defined in vidbyte/lib/ and re-exported.
COMMON MODIFICATION PATTERNS: Add a new connector's import and __all__ entry here and in vidbyte/__init__.py together.
KNOWN EDGE CASES: OutputShaping and the provider helpers are deliberately not exported.
RELATED DOCS: vidbyte/agents/output/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_contract.py
"""

from __future__ import annotations

from vidbyte.agents.output.connector import OutputConnector
from vidbyte.agents.output.dispatcher import OutputDispatcher
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputContent
from vidbyte.lib.enums.outputs import DeliveryStatus, OutputDestination
from vidbyte.lib.errors import OutputDeliveryError
from vidbyte.lib.outputs import (
    DiscordOutput,
    EmailOutput,
    GitHubIssueOutput,
    GoogleChatOutput,
    JiraIssueOutput,
    LinearIssueOutput,
    NotionPageOutput,
    SlackOutput,
    TeamsOutput,
    TelegramOutput,
    WebhookOutput,
)

__all__ = [
    "DeliveryReceipt",
    "DeliveryStatus",
    "DiscordOutput",
    "EmailOutput",
    "GitHubIssueOutput",
    "GoogleChatOutput",
    "JiraIssueOutput",
    "LinearIssueOutput",
    "NotionPageOutput",
    "OutputConnector",
    "OutputContent",
    "OutputDeliveryError",
    "OutputDestination",
    "OutputDispatcher",
    "SlackOutput",
    "TeamsOutput",
    "TelegramOutput",
    "WebhookOutput",
]
