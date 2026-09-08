"""FILE: vidbyte/agents/codex/contracts.py

PURPOSE: Builds the shared output-contract counters from one completed Codex turn.
ROLE IN CODEBASE: config.py rejects unenforceable loop settings at construction;
    agent.py builds counters after a turn and evaluates the caller's contracts.
ARCHITECTURE NOTE: The counter keys mirror AgentRuntime._contract_counters exactly, so
    one contract vocabulary cannot mean two things depending on which agent ran it.
    Each tool item type reports its outcome differently, so each has its own success rule.
FUNCTION INVENTORY: counters(request) builds the mapping; evaluate() returns one verdict
    per contract; _tool_counters walks items once; _tool_name and _tool_succeeded hold the
    per-item-type rules; _usage_counters, _output_counters, and _compaction_counters cover
    the rest; CodexContractValidator rejects what cannot be honored.
COMMON MODIFICATION PATTERNS: A new native tool item type needs an entry in
    CODEX_TOOL_ITEM_TYPES plus a branch in _tool_name and _tool_succeeded, together.
WHAT NOT TO DO IN THIS FILE: Do not count a command with a nonzero exit code as a
    successful tool call, do not fabricate iteration_count or model_call_count, and do
    not put a full command line into a counter — it carries paths and sometimes secrets.
KNOWN EDGE CASES: An inProgress item counts as a call but never as a success; an item
    with no status is not successful, because absent evidence of success is not success.
RELATED DOCS: docs/design/codex-output-contracts.md
TESTS: tests/test_codex_output_contracts.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.lib.constants.codex import (
    CODEX_COMMAND_SUCCESS_EXIT_CODE,
    CODEX_COMPACTION_ITEM_TYPE,
    CODEX_ITEM_COMPLETED_STATUS,
    CODEX_MILLISECONDS_PER_SECOND,
    CODEX_TOOL_ITEM_TYPES,
    CODEX_UNOBSERVABLE_COUNTER_KEYS,
    CODEX_UNSUPPORTED_LOOP_FIELDS,
)
from vidbyte.lib.dataclasses.codex import (
    CodexContractOutcome,
    CodexContractRequest,
    CodexContractResult,
    CodexItem,
    CodexRunResult,
)
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.contracts import OutputContract
    from vidbyte.agents.settings.loop import AgentLoopSettings

_COMMAND_ITEM = "commandExecution"
_ZERO_COUNTERS = {"iteration_count": 0, "model_call_count": 0}


class CodexContractValidator:
    """Rejects loop settings and contracts Codex has no way to honor."""

    @classmethod
    def validate(cls, loop: AgentLoopSettings | None) -> None:
        # @intent refuse-a-bound-nothing-enforces
        # A timeout_seconds that never times out is worse than a construction error,
        # because the caller believes a limit exists. Name every gap at once, so
        # fixing one and re-running does not reveal the next.
        if loop is None:
            return
        unsupported = cls._unsupported_fields(loop)
        if unsupported:
            raise ConfigurationError(
                "Codex cannot enforce AgentLoopSettings "
                f"{', '.join(unsupported)}: Codex owns its model and tool loop, its "
                "own context window, and its own tool executor. Only output_contracts "
                "are honored by this adapter."
            )
        unobservable = cls._unsupported_contracts(loop)
        if unobservable:
            raise ConfigurationError(
                f"Codex cannot observe the counters output contracts "
                f"{', '.join(unobservable)} read: Codex owns its iterations and "
                "reports neither an iteration nor a model-call count."
            )

    @staticmethod
    def _unsupported_fields(loop: AgentLoopSettings) -> tuple[str, ...]:
        # A field left at its default is not a finding: one AgentLoopSettings reused
        # across several agents must not fail on a bound the caller never set.
        return tuple(
            name
            for name in CODEX_UNSUPPORTED_LOOP_FIELDS
            if getattr(loop, name, None) is not None
        )

    @staticmethod
    def _unsupported_contracts(loop: AgentLoopSettings) -> tuple[str, ...]:
        # A contract on an unobservable counter would evaluate against zero and always
        # fail, which reads as a broken agent rather than a rejected configuration.
        return tuple(
            type(contract).__name__
            for contract in getattr(loop, "output_contracts", ())
            if getattr(contract, "key", "") in CODEX_UNOBSERVABLE_COUNTER_KEYS
        )


class CodexContractTranslator:
    """Builds the shared contract counters from one completed Codex turn."""

    @classmethod
    def counters(cls, request: CodexContractRequest) -> dict[str, Any]:
        # @intent one-counter-shape-across-agent-kinds
        # These keys mirror AgentRuntime._contract_counters exactly. Two shapes would
        # make MinToolCalls(3) mean different things depending on which agent ran it.
        result = request.result
        return {
            **_ZERO_COUNTERS,
            **cls._tool_counters(result.items),
            **cls._usage_counters(result, request.cost_usd),
            **cls._output_counters(result),
            **cls._compaction_counters(result.items),
        }

    @classmethod
    def evaluate(
        cls, contracts: Sequence[OutputContract], counters: Mapping[str, Any]
    ) -> CodexContractOutcome:
        """Return one verdict per contract, in declaration order, with the counters."""
        return CodexContractOutcome(
            results=tuple(
                cls._verdict(contract, counters)
                for contract in contracts
            ),
            counters=dict(counters),
        )

    @staticmethod
    def _verdict(
        contract: OutputContract, counters: Mapping[str, Any]
    ) -> CodexContractResult:
        # The contract's own error() text is what names the specific tool a
        # MinToolCallsById wanted; a generic message would lose exactly the detail
        # the caller needs to act on.
        satisfied = contract.satisfied(counters)
        return CodexContractResult(
            name=contract.name,
            satisfied=satisfied,
            observed=contract.observed(counters),
            minimum=float(contract.minimum),
            error="" if satisfied else contract.error(counters),
        )

    @classmethod
    def _tool_counters(cls, items: tuple[CodexItem, ...]) -> dict[str, Any]:
        # @intent count-a-call-and-a-success-separately
        # A command that completed with exit code 1 ran and failed. Folding the two
        # counters together is the silent wrong answer MinSuccessfulToolCalls exists
        # to catch, so both are derived in this one pass over the items.
        tools = tuple(item for item in items if item.type in CODEX_TOOL_ITEM_TYPES)
        by_name = Counter(cls._tool_name(item) for item in tools)
        return {
            "tool_call_count": len(tools),
            "successful_tool_call_count": len(
                tuple(item for item in tools if cls._tool_succeeded(item))
            ),
            "distinct_tool_count": len(by_name),
            "tool_calls_by_name": dict(by_name),
        }

    @staticmethod
    def _compaction_counters(items: tuple[CodexItem, ...]) -> dict[str, Any]:
        # Compaction is the one native event a floor can require, and it is countable
        # today because contextCompaction items already reach CodexRunResult.items.
        return {
            "compaction_count": len(
                tuple(
                    item for item in items if item.type == CODEX_COMPACTION_ITEM_TYPE
                )
            )
        }

    @staticmethod
    def _tool_name(item: CodexItem) -> str:
        # A command is named by its executable, not its full command line: a whole
        # line would never match MinToolCallsById and would leak paths into metadata.
        if item.type != _COMMAND_ITEM:
            return str(item.fields.get("tool") or item.type)
        command = str(item.fields.get("command") or "").strip()
        return command.split()[0] if command else item.type

    @staticmethod
    def _tool_succeeded(item: CodexItem) -> bool:
        # @intent each-item-type-reports-its-outcome-differently
        # The pinned SDK gives command, MCP, and dynamic items distinct outcome
        # fields. A uniform status check would count a failed command as a success.
        fields = item.fields
        if item.type == _COMMAND_ITEM:
            return (
                fields.get("status") == CODEX_ITEM_COMPLETED_STATUS
                and fields.get("exit_code") == CODEX_COMMAND_SUCCESS_EXIT_CODE
            )
        if "success" in fields:
            return fields.get("success") is True
        return (
            fields.get("status") == CODEX_ITEM_COMPLETED_STATUS
            and not fields.get("error")
        )

    @staticmethod
    def _usage_counters(
        result: CodexRunResult, cost_usd: float | None
    ) -> dict[str, Any]:
        # Token counts come from the per-turn delta; the cumulative snapshot would
        # inflate every token floor on every turn after the first.
        usage = result.last_usage if result.usage_available else None
        return {
            "tokens_used": usage.total_tokens if usage is not None else 0,
            "final_output_tokens": usage.output_tokens if usage is not None else 0,
            "cost_spent_usd": cost_usd or 0,
        }

    @staticmethod
    def _output_counters(result: CodexRunResult) -> dict[str, Any]:
        # duration_ms is the provider's own report; dividing is what keeps a
        # MinElapsedSeconds floor from being satisfied by a factor of 1000.
        duration = result.duration_ms or 0
        return {
            "final_output_chars": len(result.final_response or ""),
            "elapsed_seconds": duration / CODEX_MILLISECONDS_PER_SECOND,
        }


__all__ = ["CodexContractTranslator", "CodexContractValidator"]
