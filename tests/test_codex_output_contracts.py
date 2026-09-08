"""FILE: tests/test_codex_output_contracts.py

PURPOSE:
    Feature tests for Codex output contracts: CodexContractValidator's
    construction-time rejection of unenforceable loop settings and
    unobservable contracts, CodexContractTranslator's counter construction
    from native turn items, and CodexHarnessAgent's post-turn evaluation.
    Locks the behavior docs/design/codex-output-contracts.md specifies: the
    counter keys match the direct runtime's exactly, each tool item type has
    its own success rule, and an unmet contract fails the turn loudly.

ROLE IN CODEBASE:
    Exercises vidbyte/agents/codex/contracts.py, the validation call in
    vidbyte/agents/codex/config.py, the evaluation in
    vidbyte/agents/codex/agent.py, and the metadata key in
    vidbyte/agents/codex/result.py, against the real
    vidbyte/agents/contracts/ floor classes and AgentLoopSettings.

ARCHITECTURE NOTE:
    Every test runs offline. CodexItem payloads are shaped exactly like the
    pinned openai-codex 0.147 model_dump output — CommandExecutionThreadItem
    carries status and exit_code, McpToolCallThreadItem carries status and
    error, DynamicToolCallThreadItem carries an explicit success flag — so a
    field-name drift in the SDK would surface here.

FUNCTION INVENTORY:
    No production functions. _command(), _mcp(), and _dynamic() build one
    native tool item each; _run_result() assembles a turn; _build_agent()
    wires an agent to a recording transport.

COMMON MODIFICATION PATTERNS:
    Add a native tool item type, then add its builder here plus a success
    case and a failure case; CounterShapeParityTests guards the key set.

WHAT NOT TO DO IN THIS FILE:
    Do not assert that a completed command with a nonzero exit code counts as
    a successful tool call, and do not assert a full command line appears in
    any counter — only its first token may.

KNOWN EDGE CASES:
    An inProgress item counts as a call but not a success; an item with no
    status is not successful; an empty command still counts, named by type.

RELATED DOCS: docs/design/codex-output-contracts.md
TESTS: python -m pytest tests/test_codex_output_contracts.py
"""

from __future__ import annotations

import unittest
from typing import Any

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.contracts import (
    CodexContractTranslator,
    CodexContractValidator,
)
from vidbyte.agents.contracts import (
    MinCompactions,
    MinDistinctTools,
    MinElapsedSeconds,
    MinFinalOutputChars,
    MinIterations,
    MinSuccessfulToolCalls,
    MinTokens,
    MinToolCalls,
    MinToolCallsById,
)
from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.agents.settings.tool_error import ToolErrorPolicy
from vidbyte.lib.constants.codex import (
    CODEX_CONTRACTS_KEY,
    CODEX_UNSUPPORTED_LOOP_FIELDS,
)
from vidbyte.lib.dataclasses.codex import (
    CodexContractRequest,
    CodexHarnessAgentSettings,
    CodexItem,
    CodexRunInput,
    CodexRunResult,
    CodexTransportRunRequest,
    CodexUsage,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

FINAL_RESPONSE = "codex reply"
DURATION_MS = 2500


def _command(
    command: str = "git status",
    status: str = "completed",
    exit_code: int | None = 0,
) -> CodexItem:
    # Mirrors CommandExecutionThreadItem's model_dump: command, status, exit_code.
    return CodexItem(
        id="it_cmd",
        type="commandExecution",
        fields={"command": command, "status": status, "exit_code": exit_code},
    )


def _mcp(tool: str = "search", status: str = "completed", error: Any = None) -> CodexItem:
    # Mirrors McpToolCallThreadItem's model_dump: tool, server, status, error.
    return CodexItem(
        id="it_mcp",
        type="mcpToolCall",
        fields={"tool": tool, "server": "srv", "status": status, "error": error},
    )


def _dynamic(tool: str = "lookup", success: bool = True) -> CodexItem:
    # Mirrors DynamicToolCallThreadItem's model_dump: tool, status, success.
    return CodexItem(
        id="it_dyn",
        type="dynamicToolCall",
        fields={"tool": tool, "status": "completed", "success": success},
    )


def _run_result(
    items: tuple[CodexItem, ...] = (),
    usage_available: bool = True,
    duration_ms: int | None = DURATION_MS,
    final_response: str = FINAL_RESPONSE,
) -> CodexRunResult:
    # Builds one completed turn whose cumulative and per-turn usage differ.
    return CodexRunResult(
        thread_id="th_1",
        turn_id="tu_1",
        status="completed",
        final_response=final_response,
        duration_ms=duration_ms,
        usage=CodexUsage(input_tokens=900, output_tokens=180, total_tokens=1080),
        items=items,
        last_usage=CodexUsage(input_tokens=100, output_tokens=20, total_tokens=120),
        usage_available=usage_available,
    )


class _ScriptedTransport:
    """Stands in for CodexTransport, returning one scripted turn."""

    def __init__(self, result: CodexRunResult | None = None) -> None:
        self.result = result if result is not None else _run_result()
        self.requests: list[CodexTransportRunRequest] = []

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Records the request and returns the scripted turn.
        self.requests.append(request)
        return self.result


def _build_agent(
    loop: AgentLoopSettings | None = None, result: CodexRunResult | None = None
) -> tuple[CodexHarnessAgent, _ScriptedTransport]:
    # Builds an agent whose transport is scripted, so no Codex process is started.
    agent = CodexHarnessAgent(
        CodexHarnessAgentSettings(
            name="codex-agent",
            system_prompt="You are a Codex harness agent.",
            loop=loop,
        )
    )
    transport = _ScriptedTransport(result)
    agent._transport = transport  # type: ignore[assignment]
    return agent, transport


def _counters(result: CodexRunResult | None = None, cost_usd: float | None = None) -> dict:
    # Builds the counter mapping for one turn.
    return CodexContractTranslator.counters(
        CodexContractRequest(
            result=result if result is not None else _run_result(), cost_usd=cost_usd
        )
    )


class CounterShapeParityTests(unittest.TestCase):
    """Covers that the Codex counters match the direct runtime's key set."""

    def test_produces_exactly_the_keys_the_direct_runtime_produces(self) -> None:
        expected = {
            "iteration_count",
            "model_call_count",
            "tool_call_count",
            "successful_tool_call_count",
            "distinct_tool_count",
            "tool_calls_by_name",
            "tokens_used",
            "elapsed_seconds",
            "final_output_chars",
            "final_output_tokens",
            "cost_spent_usd",
            "compaction_count",
        }

        self.assertEqual(set(_counters()), expected)

    def test_includes_the_unobservable_counters_as_zero(self) -> None:
        counters = _counters()

        self.assertEqual(counters["iteration_count"], 0)
        self.assertEqual(counters["model_call_count"], 0)


class ToolCounterTests(unittest.TestCase):
    """Covers the one pass over native items that produces four counters."""

    def test_counts_command_mcp_and_dynamic_items(self) -> None:
        counters = _counters(_run_result((_command(), _mcp(), _dynamic())))

        self.assertEqual(counters["tool_call_count"], 3)

    def test_excludes_non_tool_item_types(self) -> None:
        items = (
            _command(),
            CodexItem(id="w", type="webSearch", fields={"query": "q"}),
            CodexItem(id="f", type="fileChange", fields={"status": "completed"}),
            CodexItem(id="m", type="agentMessage", fields={"text": "hi"}),
        )

        self.assertEqual(_counters(_run_result(items))["tool_call_count"], 1)

    def test_returns_zero_counters_for_a_turn_with_no_items(self) -> None:
        counters = _counters(_run_result(()))

        self.assertEqual(counters["tool_call_count"], 0)
        self.assertEqual(counters["successful_tool_call_count"], 0)
        self.assertEqual(counters["distinct_tool_count"], 0)
        self.assertEqual(counters["tool_calls_by_name"], {})

    def test_rejects_a_completed_command_with_a_nonzero_exit_code(self) -> None:
        counters = _counters(_run_result((_command(exit_code=1),)))

        self.assertEqual(counters["tool_call_count"], 1)
        self.assertEqual(counters["successful_tool_call_count"], 0)

    def test_accepts_a_completed_command_with_exit_code_zero(self) -> None:
        self.assertEqual(
            _counters(_run_result((_command(),)))["successful_tool_call_count"], 1
        )

    def test_rejects_a_completed_mcp_call_carrying_an_error(self) -> None:
        counters = _counters(_run_result((_mcp(error={"message": "boom"}),)))

        self.assertEqual(counters["successful_tool_call_count"], 0)

    def test_honors_the_dynamic_call_success_flag_over_its_status(self) -> None:
        counters = _counters(_run_result((_dynamic(success=False),)))

        self.assertEqual(counters["tool_call_count"], 1)
        self.assertEqual(counters["successful_tool_call_count"], 0)

    def test_rejects_an_in_progress_item(self) -> None:
        counters = _counters(_run_result((_command(status="inProgress", exit_code=None),)))

        self.assertEqual(counters["tool_call_count"], 1)
        self.assertEqual(counters["successful_tool_call_count"], 0)

    def test_rejects_an_item_with_no_status_field(self) -> None:
        item = CodexItem(id="x", type="mcpToolCall", fields={"tool": "t"})

        self.assertEqual(
            _counters(_run_result((item,)))["successful_tool_call_count"], 0
        )

    def test_rejects_a_completed_command_with_no_exit_code(self) -> None:
        item = CodexItem(
            id="x", type="commandExecution", fields={"command": "ls", "status": "completed"}
        )

        self.assertEqual(
            _counters(_run_result((item,)))["successful_tool_call_count"], 0
        )

    def test_names_a_command_by_its_first_argv_token(self) -> None:
        counters = _counters(_run_result((_command("git status --short"),)))

        self.assertEqual(counters["tool_calls_by_name"], {"git": 1})

    def test_names_an_mcp_item_by_its_tool_field(self) -> None:
        counters = _counters(_run_result((_mcp(tool="web_search"),)))

        self.assertEqual(counters["tool_calls_by_name"], {"web_search": 1})

    def test_falls_back_to_the_item_type_for_an_empty_command(self) -> None:
        counters = _counters(_run_result((_command(command=""),)))

        self.assertEqual(counters["tool_calls_by_name"], {"commandExecution": 1})
        self.assertEqual(counters["tool_call_count"], 1)

    def test_counts_distinct_tools_by_name(self) -> None:
        items = (_command("git status"), _command("git diff"), _command("ls -la"))

        counters = _counters(_run_result(items))

        self.assertEqual(counters["distinct_tool_count"], 2)
        self.assertEqual(counters["tool_calls_by_name"], {"git": 2, "ls": 1})

    def test_counts_compaction_items(self) -> None:
        items = (CodexItem(id="c", type="contextCompaction", fields={}),)

        self.assertEqual(_counters(_run_result(items))["compaction_count"], 1)


class UsageAndOutputCounterTests(unittest.TestCase):
    """Covers the token, cost, timing, and output-size counters."""

    def test_reads_tokens_from_the_per_turn_delta(self) -> None:
        counters = _counters()

        self.assertEqual(counters["tokens_used"], 120)
        self.assertEqual(counters["final_output_tokens"], 20)

    def test_reports_zero_tokens_when_usage_is_unavailable(self) -> None:
        counters = _counters(_run_result(usage_available=False))

        self.assertEqual(counters["tokens_used"], 0)
        self.assertEqual(counters["final_output_tokens"], 0)

    def test_converts_duration_milliseconds_to_seconds(self) -> None:
        self.assertEqual(_counters()["elapsed_seconds"], 2.5)

    def test_reports_zero_elapsed_without_a_provider_duration(self) -> None:
        self.assertEqual(_counters(_run_result(duration_ms=None))["elapsed_seconds"], 0)

    def test_counts_final_output_characters(self) -> None:
        self.assertEqual(_counters()["final_output_chars"], len(FINAL_RESPONSE))

    def test_reports_the_supplied_cost(self) -> None:
        self.assertEqual(_counters(cost_usd=0.42)["cost_spent_usd"], 0.42)

    def test_reports_zero_cost_when_unpriced(self) -> None:
        self.assertEqual(_counters(cost_usd=None)["cost_spent_usd"], 0)


class ContractValidationTests(unittest.TestCase):
    """Covers what CodexContractValidator admits at construction."""

    def test_accepts_no_loop_settings(self) -> None:
        CodexContractValidator.validate(None)

    def test_accepts_a_loop_carrying_only_output_contracts(self) -> None:
        CodexContractValidator.validate(
            AgentLoopSettings(output_contracts=(MinToolCalls(1),))
        )

    def test_rejects_every_field_the_constant_lists(self) -> None:
        cases = {
            "max_iterations": 5,
            "max_tokens": 100,
            "max_tool_calls": 3,
            "max_parallel_tool_calls": 2,
            "max_retries": 2,
            "timeout_seconds": 30.0,
            "context_window_budget": 1000,
            "compaction_trigger_tokens": 500,
            "compaction_target_tokens": 250,
            "allowed_tools": ("shell",),
            "tool_error_policy": ToolErrorPolicy(),
            "tool_settings": ToolSettings(),
        }
        self.assertEqual(set(cases), set(CODEX_UNSUPPORTED_LOOP_FIELDS))
        for field, value in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexContractValidator.validate(AgentLoopSettings(**{field: value}))
                self.assertIn(field, str(caught.exception))

    def test_names_every_unsupported_field_at_once(self) -> None:
        with self.assertRaises(ConfigurationError) as caught:
            CodexContractValidator.validate(
                AgentLoopSettings(max_iterations=5, timeout_seconds=30.0)
            )

        message = str(caught.exception)
        self.assertIn("max_iterations", message)
        self.assertIn("timeout_seconds", message)

    def test_rejects_a_contract_reading_an_unobservable_counter(self) -> None:
        with self.assertRaises(ConfigurationError) as caught:
            CodexContractValidator.validate(
                AgentLoopSettings(output_contracts=(MinIterations(2),))
            )

        self.assertIn("MinIterations", str(caught.exception))

    def test_agent_construction_rejects_an_unenforceable_loop(self) -> None:
        with self.assertRaises(CodexAgentError) as caught:
            CodexHarnessAgent(
                CodexHarnessAgentSettings(
                    name="a",
                    system_prompt="p",
                    loop=AgentLoopSettings(timeout_seconds=30.0),
                )
            )

        self.assertEqual(
            caught.exception.failure_code,
            FailureCode.CODEX_VIDBYTE_TRANSLATION_FAILED.value,
        )


class ContractEvaluationTests(unittest.TestCase):
    """Covers the verdicts CodexContractTranslator.evaluate produces."""

    def test_reports_satisfied_and_observed_per_contract(self) -> None:
        counters = _counters(_run_result((_command(), _command("ls"))))

        outcome = CodexContractTranslator.evaluate((MinToolCalls(2),), counters)

        self.assertEqual(len(outcome.results), 1)
        self.assertTrue(outcome.results[0].satisfied)
        self.assertEqual(outcome.results[0].observed, 2)
        self.assertEqual(outcome.results[0].name, "MinToolCalls")

    def test_reports_unmet_contracts_in_declaration_order(self) -> None:
        counters = _counters(_run_result(()))

        outcome = CodexContractTranslator.evaluate(
            (MinToolCalls(1), MinTokens(10_000), MinCompactions(1)), counters
        )

        self.assertEqual(
            [result.name for result in outcome.unmet],
            ["MinToolCalls", "MinTokens", "MinCompactions"],
        )

    def test_carries_each_unmet_contract_own_corrective_text(self) -> None:
        counters = _counters(_run_result((_command("ls -la"),)))

        outcome = CodexContractTranslator.evaluate(
            (MinToolCallsById("git", 2),), counters
        )

        self.assertIn("git", outcome.unmet[0].error)

    def test_leaves_a_satisfied_contract_error_empty(self) -> None:
        counters = _counters(_run_result((_command(),)))

        outcome = CodexContractTranslator.evaluate((MinToolCalls(1),), counters)

        self.assertEqual(outcome.results[0].error, "")

    def test_carries_the_counters_it_judged_against(self) -> None:
        outcome = CodexContractTranslator.evaluate((MinToolCalls(1),), _counters())

        self.assertIn("tool_call_count", outcome.counters)


class AgentContractIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Covers the wired evaluation through real turns."""

    async def test_a_satisfied_run_returns_the_reply_and_publishes_the_outcome(
        self,
    ) -> None:
        agent, _ = _build_agent(
            loop=AgentLoopSettings(output_contracts=(MinToolCalls(2),)),
            result=_run_result((_command(), _command("ls"))),
        )

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(reply.content, FINAL_RESPONSE)
        outcome = reply.metadata[CODEX_CONTRACTS_KEY]
        self.assertEqual(outcome.unmet, ())
        self.assertIn("tool_call_count", outcome.counters)

    async def test_a_failed_command_satisfies_calls_but_not_successes(self) -> None:
        agent, _ = _build_agent(
            loop=AgentLoopSettings(
                output_contracts=(MinToolCalls(2), MinSuccessfulToolCalls(2))
            ),
            result=_run_result((_command(), _command("ls", exit_code=1))),
        )

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(CodexRunInput.text("go"))

        self.assertIn("MinSuccessfulToolCalls", str(caught.exception))

    async def test_an_unmet_contract_raises_the_classified_failure(self) -> None:
        agent, _ = _build_agent(
            loop=AgentLoopSettings(output_contracts=(MinToolCalls(1),)),
            result=_run_result(()),
        )

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(
            caught.exception.failure_code, FailureCode.CODEX_CONTRACT_UNMET.value
        )
        self.assertEqual(caught.exception.operation, "evaluate_contracts")

    async def test_the_error_names_every_unmet_contract(self) -> None:
        agent, _ = _build_agent(
            loop=AgentLoopSettings(
                output_contracts=(MinToolCalls(1), MinCompactions(1))
            ),
            result=_run_result(()),
        )

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(CodexRunInput.text("go"))

        named = caught.exception.safe_runtime_details["error_type"]
        self.assertIn("MinToolCalls", named)
        self.assertIn("MinCompactions", named)

    async def test_the_message_carries_the_contract_own_corrective_text(self) -> None:
        agent, _ = _build_agent(
            loop=AgentLoopSettings(output_contracts=(MinToolCallsById("git", 2),)),
            result=_run_result((_command("ls -la"),)),
        )

        with self.assertRaises(CodexAgentError) as caught:
            await agent.arun(CodexRunInput.text("go"))

        self.assertIn("git", str(caught.exception))

    async def test_min_tool_calls_by_id_resolves_per_name(self) -> None:
        agent, _ = _build_agent(
            loop=AgentLoopSettings(
                output_contracts=(MinToolCallsById("git", 2),)
            ),
            result=_run_result((_command("git status"), _command("ls -la"))),
        )

        with self.assertRaises(CodexAgentError):
            await agent.arun(CodexRunInput.text("go"))

    async def test_min_tool_calls_by_id_is_satisfied_by_two_matching_calls(
        self,
    ) -> None:
        agent, _ = _build_agent(
            loop=AgentLoopSettings(output_contracts=(MinToolCallsById("git", 2),)),
            result=_run_result((_command("git status"), _command("git diff"))),
        )

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(reply.content, FINAL_RESPONSE)

    async def test_elapsed_and_output_floors_read_real_values(self) -> None:
        agent, _ = _build_agent(
            loop=AgentLoopSettings(
                output_contracts=(
                    MinElapsedSeconds(2),
                    MinFinalOutputChars(5),
                    MinDistinctTools(1),
                )
            ),
            result=_run_result((_command(),)),
        )

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertEqual(reply.content, FINAL_RESPONSE)

    async def test_an_agent_without_a_loop_publishes_no_contract_key(self) -> None:
        agent, _ = _build_agent()

        reply = await agent.arun(CodexRunInput.text("go"))

        self.assertNotIn(CODEX_CONTRACTS_KEY, reply.metadata)


if __name__ == "__main__":
    unittest.main()
