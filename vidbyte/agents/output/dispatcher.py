"""FILE: vidbyte/agents/output/dispatcher.py

PURPOSE: Defines OutputDispatcher, which links an agent's finished reply to each of its output connectors and records one receipt per connector.
ROLE IN CODEBASE: BaseAgent validates outputs with connectors() and calls deliver() after the schema check; callers also use deliver() to resend failed outputs.
ARCHITECTURE NOTE: Stateless static methods; connectors run concurrently, each under its own deadline, and receipts keep configured order.
COMMON MODIFICATION PATTERNS: Keep provider details out of here; a new destination is a new class in vidbyte/lib/outputs/.
KNOWN EDGE CASES: Cancellation propagates unchanged; an ordinary exception from render or send fails only that connector as unexpected:<Type>.
RELATED DOCS: vidbyte/agents/output/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_dispatch.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, MutableMapping, Sequence

from vidbyte.agents.output.connector import OutputConnector, OutputShaping
from vidbyte.lib.constants.outputs import (
    OUTPUT_DELIVERIES_METADATA_KEY,
    OUTPUT_DELIVERY_DEADLINE_SECONDS,
    OUTPUT_ERROR_NETWORK,
    OUTPUT_ERROR_UNEXPECTED_PREFIX,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.outputs import DeliveryReceipt, OutputContent
from vidbyte.lib.enums.outputs import DeliveryStatus
from vidbyte.lib.errors import ConfigurationError, OutputDeliveryError


class OutputDispatcher:
    """Delivers one finished reply to every configured connector."""

    @staticmethod
    def connectors(outputs: Sequence[OutputConnector]) -> tuple[OutputConnector, ...]:
        """Validate an outputs argument and return it as a tuple of distinct connectors."""
        if isinstance(outputs, (str, bytes, Mapping)):
            raise ConfigurationError(f"outputs must be a list or tuple of connectors, got {type(outputs).__name__}.")
        try:
            items = tuple(outputs)
        except TypeError as exc:
            raise ConfigurationError(f"outputs must be a list or tuple of connectors, got {type(outputs).__name__}.") from exc
        for index, item in enumerate(items):
            if isinstance(item, type):
                raise ConfigurationError(f"outputs[{index}] is the class {item.__name__}; pass an instance such as {item.__name__}(...).")
            if not isinstance(item, OutputConnector):
                raise ConfigurationError(f"outputs[{index}] is a {type(item).__name__}, not an output connector.")
        if len({id(item) for item in items}) != len(items):
            raise ConfigurationError("outputs lists the same connector instance twice; each one would post every reply again.")
        return items

    @staticmethod
    async def deliver(outputs: Sequence[OutputConnector], reply: AgentMessage, metadata: MutableMapping[str, object]) -> tuple[DeliveryReceipt, ...]:
        """Deliver the reply to every connector; raise OutputDeliveryError after all finish if any failed."""
        # A blank reply, or a run that stopped before an accepted
        # answer, is skipped everywhere and sends nothing.
        if not OutputShaping.is_deliverable(reply):
            skipped = tuple(DeliveryReceipt(connector.destination, DeliveryStatus.SKIPPED) for connector in outputs)
            metadata[OUTPUT_DELIVERIES_METADATA_KEY] = skipped
            return skipped
        # Send to every connector at once, so the wait is the slowest
        # connector rather than the sum of all of them.
        results = await asyncio.gather(*(OutputDispatcher._deliver_one(connector, reply) for connector in outputs), return_exceptions=True)
        # Cancellation and interrupts are not delivery outcomes, so they
        # pass through untouched.
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result
        # One receipt per connector, in configured order, whatever order
        # the sends finished in; the reply carries them for the caller.
        receipts = tuple(OutputDispatcher._receipt(connector, result) for connector, result in zip(outputs, results, strict=True))
        metadata[OUTPUT_DELIVERIES_METADATA_KEY] = receipts
        # Only now that every connector has finished, report failures by
        # destination and code, chained from the first unexpected error.
        failed = [receipt for receipt in receipts if receipt.status is DeliveryStatus.FAILED]
        if failed:
            message = f"{len(failed)} of {len(receipts)} outputs failed: " + ", ".join(f"{receipt.destination.value} ({receipt.error_code})" for receipt in failed)
            first_exception = next((result for result in results if isinstance(result, Exception)), None)
            raise OutputDeliveryError(message, reply=reply, receipts=receipts) from first_exception
        return receipts

    @staticmethod
    async def _deliver_one(connector: OutputConnector, reply: AgentMessage) -> DeliveryReceipt:
        """Shape the reply for one connector and send it within the delivery deadline."""
        # @intent one-connector-one-deadline
        # Each send has its own deadline, so a destination that never
        # answers fails as network without holding back the others.
        render = connector.render
        content = render(reply) if render is not None else OutputShaping.content(reply)
        if not isinstance(content, OutputContent):
            raise ConfigurationError(f"{type(connector).__name__}.render must return OutputContent, got {type(content).__name__}.")
        try:
            return await asyncio.wait_for(connector.send(reply, content), OUTPUT_DELIVERY_DEADLINE_SECONDS)
        except TimeoutError:
            return DeliveryReceipt(connector.destination, DeliveryStatus.FAILED, error_code=OUTPUT_ERROR_NETWORK)

    @staticmethod
    def _receipt(connector: OutputConnector, result: DeliveryReceipt | BaseException) -> DeliveryReceipt:
        # A connector's own receipt passes through; an error from its
        # render or send fails that connector only.
        if isinstance(result, DeliveryReceipt):
            return result
        return DeliveryReceipt(connector.destination, DeliveryStatus.FAILED, error_code=f"{OUTPUT_ERROR_UNEXPECTED_PREFIX}{type(result).__name__}")


__all__ = ["OutputDispatcher"]
