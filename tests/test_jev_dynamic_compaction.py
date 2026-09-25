"""FILE: tests/test_jev_dynamic_compaction.py

PURPOSE: Verifies JevAgent dynamic compaction end to end: settings validation, the batched unit-of-work Jev request, ledger bookkeeping, the reclaim threshold, the in-place history rewrite, the writer fallback, and every fail-open path.
ROLE IN CODEBASE: Protects vidbyte/agents/jev/compaction/, the JevRuntime override, and the AgentRuntime.prepare_iteration_history seam.
ARCHITECTURE NOTE: A scripted generative runner drives the real loop, a second one plays the record writer, and a scripted HTTP transport plays TypeSafe; nothing else is faked.
COMMON MODIFICATION PATTERNS: Add a scenario here whenever a trigger, the ledger, the policy, or a failure path changes.
KNOWN EDGE CASES: TYPESAFE_API_KEY is cleared in the missing-key test, and no test sends a live provider request.
RELATED DOCS: docs/design/jev-dynamic-compaction.md.
TESTS: python -m pytest tests/test_jev_dynamic_compaction.py.
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevDynamicCompactionSettings as RootJevDynamicCompactionSettings
from vidbyte import tool
from vidbyte.agents.jev import (
    JevAgent,
    JevAgentSettings,
    JevCompactionReport,
    JevDynamicCompaction,
    JevDynamicCompactionSettings,
)
from vidbyte.agents.jev.compaction import JevUnitLedger
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev_compaction import JEV_COMPACTION_METADATA_KEY
from vidbyte.lib.enums import (
    JevCompactionDisabledReason,
    JevCompactionRecordSource,
    JevCompactionTriggerKey,
    ModelProvider,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import DecisionModelRunner, TextModelResponse

API_KEY = "typesafe-test-key"
QUESTION = "unit_of_work.latest_step"
BIG_OUTPUT_CHARS = 2_000
WRITER_RECORD = "Goal: read a.\nFound: a holds the config."


class ScriptedTransport:
    """Returns scripted TypeSafe responses and records every request body."""

    def __init__(self, *responses: HttpResponse) -> None:
        # Retains responses in order and the decoded JSON of each request.
        self.responses = list(responses)
        self.bodies: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> HttpResponse:
        # Records the JSON body before returning the next scripted response.
        self.bodies.append(dict(kwargs["json_body"]))
        return self.responses.pop(0)


class ScriptedRunner:
    """Generative runner returning scripted responses and recording each call's options."""

    def __init__(self, *responses: object) -> None:
        # Retains model responses in order.
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        # Records the call, then returns or raises the next scripted item.
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class RawResponse:
    """OpenAI-shaped raw response carrying optional assistant text."""

    def __init__(self, raw: dict[str, Any], text: str = "") -> None:
        # Exposes the two attributes the loop reads.
        self.text = text
        self.raw = raw


@tool
def read(path: str) -> str:
    """Read one file."""
    return f"contents of {path}: " + "x" * BIG_OUTPUT_CHARS


def _call(name: str, arguments: dict[str, Any], call_id: str, text: str = "") -> RawResponse:
    # Builds one model response that calls one tool.
    return RawResponse({"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]}, text)


def _done(answer: str = "finished") -> RawResponse:
    # Builds the isDone response that ends the run.
    return _call("isDone", {"final_answer": answer}, "done")


def _jev(starts_new: float) -> HttpResponse:
    # Builds one TypeSafe choice answer for the unit-of-work question.
    rest = (1.0 - starts_new) / 2
    probabilities = {"continues": rest, "starts_new": starts_new, "unclear": rest}
    choice = max(probabilities, key=lambda name: probabilities[name])
    answer = {"type": "choice", "choice": choice, "probabilities": probabilities, "confidence": probabilities[choice]}
    body = {"model": "jev-1.13.0", "answers": {QUESTION: answer}, "usage": {"input_tokens": 50, "output_tokens": 1}}
    return HttpResponse(status_code=200, body=json.dumps(body), headers={})


def _error() -> HttpResponse:
    # Builds a TypeSafe server error.
    return HttpResponse(status_code=500, body=json.dumps({"error": "boom"}), headers={})


def _settings(decision: DecisionModelConfig | None = None, **compaction: Any) -> JevAgentSettings:
    # Builds JevAgent settings with the unit-of-work trigger on and a small reclaim bound.
    values = {"unit_of_work": True, "min_reclaim_tokens": 200}
    values.update(compaction)
    return JevAgentSettings(
        name="worker",
        system_prompt="Work carefully.",
        provider="openai",
        model_name="gpt-4.1-mini",
        tools=(read,),
        decision=decision or DecisionModelConfig(api_key=API_KEY, retry_count=0),
        dynamic_compaction=JevDynamicCompactionSettings(**values),
    )


def _three_unit_script() -> list[RawResponse]:
    # Units: {1, 2} read a, {3, 4} read b, {5} read c, then isDone.
    return [
        _call("read", {"path": "a"}, "c1", "I will read a."),
        _call("read", {"path": "a2"}, "c2"),
        _call("read", {"path": "b"}, "c3", "Unit one is done. Next I will read b."),
        _call("read", {"path": "b2"}, "c4"),
        _call("read", {"path": "c"}, "c5", "Now c."),
        _done(),
    ]


def _agent(main: ScriptedRunner, writer: ScriptedRunner, transport: ScriptedTransport | None, **compaction: Any) -> JevAgent:
    # Builds a JevAgent with scripted main model, writer model, and TypeSafe transport.
    agent = bind_test_runner(JevAgent(_settings(**compaction)), main)
    assert agent.compaction is not None
    bind_test_runner(agent.compaction, writer)
    if transport is not None:
        agent.compaction._decision_runner = DecisionModelRunner(DecisionModelConfig(api_key=API_KEY, retry_count=0), transport=transport)
    return agent


def _report(reply: Any) -> JevCompactionReport:
    # Reads the compaction report from a reply's metadata.
    report = reply.metadata[JEV_COMPACTION_METADATA_KEY]
    assert isinstance(report, JevCompactionReport)
    return report


def _history_text(call: dict[str, Any]) -> str:
    # Serializes the message history one model call received.
    return json.dumps(list(call["kwargs"].get("messages") or ()), default=str)


class JevDynamicCompactionSettingsTests(unittest.TestCase):
    """Pins the public settings surface and its validation."""

    def test_flags_and_bound_are_validated(self) -> None:
        # [Hidden Failure] a truthy non-bool flag or a zero bound fails at construction, not mid-run.
        with self.assertRaisesRegex(ConfigurationError, "unit_of_work"):
            JevDynamicCompactionSettings(unit_of_work=1)  # type: ignore[arg-type]
        for bad in (0, True, 1.5):
            with self.assertRaisesRegex(ConfigurationError, "min_reclaim_tokens"):
                JevDynamicCompactionSettings(unit_of_work=True, min_reclaim_tokens=bad)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ConfigurationError, "dynamic_compaction"):
            JevAgentSettings(name="n", system_prompt="p", provider="openai", model_name="m", dynamic_compaction={"unit_of_work": True})  # type: ignore[arg-type]

    def test_all_flags_off_builds_no_compaction_agent(self) -> None:
        # [Edge Case] settings with every trigger off behave exactly like no setting.
        settings = JevAgentSettings(name="n", system_prompt="p", provider="openai", model_name="m", dynamic_compaction=JevDynamicCompactionSettings())
        self.assertIsNone(JevAgent(settings).compaction)
        self.assertEqual(JevDynamicCompactionSettings(unit_of_work=True).enabled_triggers(), (JevCompactionTriggerKey.UNIT_OF_WORK,))
        with self.assertRaisesRegex(ConfigurationError, "at least one trigger"):
            JevDynamicCompaction(settings)

    def test_root_export_is_the_same_class(self) -> None:
        # [Silent Failure] the root import resolves the package class, not a copy.
        self.assertIs(RootJevDynamicCompactionSettings, JevDynamicCompactionSettings)

    def test_writer_shares_the_agent_usage_tracker(self) -> None:
        # [Hidden Assumption] record-writing calls count toward the JevAgent's own usage.
        agent = JevAgent(_settings())
        assert agent.compaction is not None
        self.assertIs(agent.compaction._usage_tracker, agent._usage_tracker)


class JevDynamicCompactionRunTests(unittest.IsolatedAsyncioTestCase):
    """Drives the real loop through boundaries, compaction, and failure paths."""

    async def test_finished_unit_is_replaced_by_one_record(self) -> None:
        # [Hidden Failure] only the finished, older unit is spliced out, in place, once the saving is worth it.
        main = ScriptedRunner(*_three_unit_script())
        writer = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=WRITER_RECORD, raw={}))
        transport = ScriptedTransport(_jev(0.05), _jev(0.9), _jev(0.05), _jev(0.9))
        reply = await _agent(main, writer, transport).arun("Read a, then b, then c.")

        self.assertEqual(reply.content, "finished")
        report = _report(reply)
        self.assertEqual([boundary.iteration for boundary in report.boundaries], [3, 5])
        self.assertEqual(report.jev_calls, 4)
        self.assertEqual(len(report.compactions), 1)
        compaction = report.compactions[0]
        self.assertEqual((compaction.unit, compaction.first_iteration, compaction.last_iteration), (1, 1, 2))
        self.assertEqual(compaction.record_source, JevCompactionRecordSource.WRITER)
        # This scripted response shape adds one tool-result message per iteration, so two iterations remove two.
        self.assertEqual(compaction.messages_removed, 2)
        self.assertIsNone(report.disabled_reason)
        self.assertEqual(report.jev_usage.input_tokens if report.jev_usage else None, 200)

        before, after = _history_text(main.calls[4]), _history_text(main.calls[5])
        self.assertIn("contents of a:", before)
        self.assertNotIn("contents of a:", after)
        self.assertNotIn("contents of a2:", after)
        self.assertIn("[Compacted unit of work 1: steps 1 to 2]", after)
        self.assertIn("Found: a holds the config.", after)
        self.assertIn("contents of b:", after, "the newest closed unit stays raw")
        self.assertIn("contents of c:", after, "the open unit is never compacted")
        self.assertEqual(len(writer.calls), 1)
        self.assertIn("contents of a2:", writer.calls[0]["prompt"], "the writer sees the unit's outputs")

    async def test_one_batched_request_without_tool_outputs(self) -> None:
        # [Hidden Assumption] Jev sees the open unit and latest step by name, with arguments but no raw outputs.
        main = ScriptedRunner(*_three_unit_script())
        transport = ScriptedTransport(*(_jev(0.05) for _ in range(4)))
        await _agent(main, ScriptedRunner(), transport).arun("task")

        body = transport.bodies[1]
        self.assertEqual(list(body["questions"]), [QUESTION])
        self.assertEqual(body["questions"][QUESTION]["type"], "choice")
        self.assertEqual(set(body["questions"][QUESTION]["criteria"]), {"continues", "starts_new", "unclear"})
        state = body["state"]
        self.assertEqual(set(state), {"open_unit", "latest_step"})
        self.assertIn('called read {"path": "a"}', state["open_unit"])
        self.assertIn('called read {"path": "b"}', state["latest_step"])
        self.assertIn("Unit one is done.", state["latest_step"])
        self.assertNotIn("xxxx", json.dumps(state))

    async def test_boundaries_below_the_reclaim_bound_change_nothing(self) -> None:
        # [Edge Case] boundaries are recorded, but a saving smaller than the bound never costs a rewrite.
        main = ScriptedRunner(*_three_unit_script())
        transport = ScriptedTransport(_jev(0.05), _jev(0.9), _jev(0.05), _jev(0.9))
        reply = await _agent(main, ScriptedRunner(), transport, min_reclaim_tokens=1_000_000).arun("task")

        report = _report(reply)
        self.assertEqual(len(report.boundaries), 2)
        self.assertEqual(report.compactions, ())
        self.assertIn("contents of a:", _history_text(main.calls[5]))

    async def test_uncertain_answer_is_not_a_boundary(self) -> None:
        # [Edge Case] P(starts_new) just under the bar keeps the unit open.
        main = ScriptedRunner(*_three_unit_script())
        transport = ScriptedTransport(*(_jev(0.79) for _ in range(4)))
        report = _report(await _agent(main, ScriptedRunner(), transport).arun("task"))
        self.assertEqual(report.boundaries, ())
        self.assertEqual(report.jev_calls, 4)

    async def test_writer_failure_uses_the_deterministic_record(self) -> None:
        # [Hidden Failure] a failed writer still compacts, with a record built from the steps themselves.
        main = ScriptedRunner(*_three_unit_script())
        writer = ScriptedRunner(RuntimeError("writer down"))
        transport = ScriptedTransport(_jev(0.05), _jev(0.9), _jev(0.05), _jev(0.9))
        reply = await _agent(main, writer, transport).arun("task")

        report = _report(reply)
        self.assertEqual(report.writer_failures, 1)
        self.assertEqual(report.compactions[0].record_source, JevCompactionRecordSource.FALLBACK)
        after = _history_text(main.calls[5])
        self.assertIn("Step 1", after)
        self.assertIn('called read {\\"path\\": \\"a\\"}', after)
        self.assertNotIn("contents of a:", after)

    async def test_missing_jev_key_disables_the_capability(self) -> None:
        # [Hidden Failure] no TypeSafe key runs the ordinary loop and says why nothing was compacted.
        main = ScriptedRunner(*_three_unit_script())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TYPESAFE_API_KEY", None)
            agent = bind_test_runner(JevAgent(_settings(decision=DecisionModelConfig())), main)
            reply = await agent.arun("task")
        self.assertEqual(reply.content, "finished")
        report = _report(reply)
        self.assertEqual(report.disabled_reason, JevCompactionDisabledReason.JEV_UNAVAILABLE)
        self.assertEqual(report.jev_calls, 0)

    async def test_repeated_jev_errors_stop_the_questions(self) -> None:
        # [Hidden Failure] three consecutive failures stop asking; no step is ever compacted on a failed answer.
        main = ScriptedRunner(*_three_unit_script())
        transport = ScriptedTransport(_error(), _error(), _error())
        reply = await _agent(main, ScriptedRunner(), transport).arun("task")

        report = _report(reply)
        self.assertEqual(report.jev_errors, 3)
        self.assertEqual(report.disabled_reason, JevCompactionDisabledReason.JEV_ERRORS)
        self.assertEqual(report.compactions, ())
        self.assertEqual(len(transport.bodies), 3)

    async def test_disabled_capability_adds_no_metadata(self) -> None:
        # [Edge Case] without the setting the loop publishes nothing and asks nothing.
        main = ScriptedRunner(_call("read", {"path": "a"}, "c1"), _done())
        agent = bind_test_runner(JevAgent(JevAgentSettings(name="n", system_prompt="p", provider="openai", model_name="gpt-4.1-mini", tools=(read,))), main)
        reply = await agent.arun("task")
        self.assertNotIn(JEV_COMPACTION_METADATA_KEY, reply.metadata)


class JevUnitLedgerTests(unittest.TestCase):
    """Pins the ledger's offsets, splicing, and refusal to guess."""

    def test_splice_keeps_earlier_history_and_later_iterations(self) -> None:
        # [Hidden Failure] history passed in before the run is never touched and offsets survive a splice.
        ledger = JevUnitLedger()
        messages: list[dict[str, Any]] = [{"role": "user", "content": "earlier"}]
        ledger.observe(messages, 0)
        for iteration in (1, 2, 3):
            messages.extend([{"it": iteration, "kind": "call"}, {"it": iteration, "kind": "result"}])
            self.assertTrue(ledger.observe(messages, iteration))
        ledger.split_before(3)
        unit = ledger.units[0]
        removed = ledger.replace_unit(messages, unit, {"role": "user", "content": "record"})
        self.assertEqual(removed, 4)
        self.assertEqual(messages[0]["content"], "earlier")
        self.assertEqual(messages[1]["content"], "record")
        self.assertEqual(messages[2:], [{"it": 3, "kind": "call"}, {"it": 3, "kind": "result"}])
        messages.append({"it": 4, "kind": "call"})
        self.assertTrue(ledger.observe(messages, 4))
        self.assertIsNone(ledger.disabled_reason)

    def test_replaced_or_shrunk_history_disables_the_ledger(self) -> None:
        # [Hidden Failure] a history the ledger did not produce is never spliced.
        ledger = JevUnitLedger()
        messages: list[dict[str, Any]] = []
        ledger.observe(messages, 0)
        self.assertFalse(ledger.observe(list(messages), 1))
        self.assertEqual(ledger.disabled_reason, JevCompactionDisabledReason.HISTORY_REPLACED)

        ledger = JevUnitLedger()
        messages = [{"a": 1}]
        ledger.observe(messages, 0)
        messages.clear()
        self.assertFalse(ledger.observe(messages, 1))
        self.assertEqual(ledger.disabled_reason, JevCompactionDisabledReason.HISTORY_OUT_OF_SYNC)

    def test_newest_closed_unit_is_not_eligible(self) -> None:
        # [Edge Case] the unit the next one builds on stays raw until another unit closes after it.
        ledger = JevUnitLedger()
        messages: list[dict[str, Any]] = []
        ledger.observe(messages, 0)
        for iteration in (1, 2, 3):
            messages.append({"it": iteration})
            ledger.observe(messages, iteration)
        ledger.split_before(2)
        self.assertEqual(ledger.eligible_units(1), ())
        ledger.split_before(3)
        self.assertEqual([unit.number for unit in ledger.eligible_units(1)], [1])


if __name__ == "__main__":
    unittest.main()
