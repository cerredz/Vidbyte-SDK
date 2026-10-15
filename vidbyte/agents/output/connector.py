"""FILE: vidbyte/agents/output/connector.py

PURPOSE: Defines OutputConnector, the contract for anything an agent delivers its finished replies to, and OutputShaping, the rules for which replies are delivered and what title and body they carry.
ROLE IN CODEBASE: The dispatcher in this package checks outputs against OutputConnector and shapes replies with OutputShaping; the provider classes in vidbyte/lib/outputs/ satisfy the Protocol structurally.
ARCHITECTURE NOTE: Agent-side rules only; imports nothing from vidbyte.agents outside this package, because vidbyte/agents/base.py imports it.
COMMON MODIFICATION PATTERNS: Change the skip or shaping rule here, never in a connector, so every destination follows the same rule.
KNOWN EDGE CASES: A reply with no stop_reason (Jev's clarification stop) is delivered; a run stopped by a budget, guard, or middleware is not.
RELATED DOCS: vidbyte/agents/output/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_dispatch.py
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, runtime_checkable

from vidbyte.lib.constants.outputs import OUTPUT_DELIVERABLE_STOP_REASONS
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputContent
from vidbyte.lib.enums.outputs import OutputDestination
from vidbyte.lib.outputs.text import OutputText


@runtime_checkable
class OutputConnector(Protocol):
    """A place an agent delivers each finished reply to: its kind, an optional render hook, and an async send."""

    destination: OutputDestination

    @property
    def render(self) -> Callable[[AgentMessage], OutputContent] | None:
        """The caller's content builder that replaces the default shaping, if any."""
        ...

    async def send(self, reply: AgentMessage, content: OutputContent) -> DeliveryReceipt:
        """Deliver one reply's content and report the outcome as a receipt."""
        # @intent one-send-one-receipt
        # A send makes one delivery and returns its receipt; failures
        # the destination reports become FAILED receipts, not raises.
        ...


class OutputShaping:
    """Agent-side rules: which replies are delivered, and their title and body."""

    @staticmethod
    def is_deliverable(reply: AgentMessage) -> bool:
        """True when the reply has text and its run finished with an accepted answer."""
        stop_reason = reply.metadata.get("stop_reason")
        # @intent only-accepted-answers-are-delivered
        # A run stopped by a budget, guard, or middleware ends with an
        # SDK notice, not an answer, so it is never posted.
        return bool(reply.content.strip()) and (stop_reason is None or stop_reason in OUTPUT_DELIVERABLE_STOP_REASONS)

    @staticmethod
    def content(reply: AgentMessage) -> OutputContent:
        """Shape a reply into one title and one body for a connector with no render."""
        # The body is the structured body field when there is one, else
        # the reply text itself.
        body = OutputShaping.structured_field(reply.structured, "body") or reply.content
        # The title is the structured title field; plain text uses its
        # first line; anything else falls back to the agent's name.
        title = OutputShaping.structured_field(reply.structured, "title")
        if title is None and reply.structured is None:
            title = OutputText.first_line(body)
        return OutputContent(title or reply.sender, body)

    @staticmethod
    def structured_field(structured: object, name: str) -> str | None:
        """A non-blank text field of the structured output, stripped, or None."""
        value = structured.get(name) if isinstance(structured, Mapping) else getattr(structured, name, None)
        return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = ["OutputConnector", "OutputShaping"]
