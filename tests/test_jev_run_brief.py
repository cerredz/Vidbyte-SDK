"""FILE: tests/test_jev_run_brief.py

PURPOSE: Verifies the Jev run brief without network calls: its settings, numbered event windows, exact run facts, quote verification, the separate writer agent, and the keeper's cadence and refresh paths.
ROLE IN CODEBASE: Covers vidbyte/agents/jev/brief/, JevRunBriefSettings, the run-brief records in vidbyte/lib/dataclasses/jev.py, and the jev_run_brief prompt family.
ARCHITECTURE NOTE: Only the writer's model call is replaced, by patching JevRunBriefWriter.arun; event numbering, facts, verification, records, and cadence run for real.
COMMON MODIFICATION PATTERNS: Add a case beside the concern it covers when a trigger, cap, verification rule, or writer input changes.
KNOWN EDGE CASES: Event E1 is the request; main-loop responses and tool calls are numbered from E2 in loop order.
RELATED DOCS: docs/design/jev-run-brief.md.
TESTS: python -m pytest tests/test_jev_run_brief.py.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from vidbyte.agents.jev.brief import (
    JevRunBriefEvents,
    JevRunBriefKeeper,
    JevRunBriefVerifier,
    JevRunBriefWriter,
    JevRunFactsReader,
)
from vidbyte.agents.jev.settings import JevAgentSettings, JevRunBriefSettings
from vidbyte.lib.constants.jev import (
    JEV_RUN_BRIEF_APPROACHES_MAX,
    JEV_RUN_BRIEF_EVENT_MAX_CHARS,
    JEV_RUN_BRIEF_EVIDENCE_MAX,
    JEV_RUN_BRIEF_FAILURES_MAX,
    JEV_RUN_BRIEF_ITEMS_MAX,
    JEV_RUN_BRIEF_NEXT_STEPS_MAX,
    JEV_RUN_BRIEF_QUOTE_MAX_CHARS,
    JEV_RUN_BRIEF_RENDER_MAX_CHARS,
    JEV_RUN_BRIEF_TEXT_MAX_CHARS,
    JEV_RUN_BRIEF_WINDOW_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import (
    JevRunBrief,
    JevRunBriefApproach,
    JevRunBriefItem,
    JevRunBriefPayload,
    JevRunBriefQuote,
    JevRunBriefWindow,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult
from vidbyte.lib.enums import JevRunBriefItemStatus, JevRunBriefOutcome, JevRunBriefUpdateStatus, ModelProvider
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools._internal import IS_DONE_TOOL_NAME

REQUEST = "Audit each file under src/api."


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "main", "system_prompt": "Do the work.", "provider": "openai", "model_name": "gpt-4.1", "api_key": "main-key"}
    values.update(overrides)
    return JevAgentSettings(**values)


def _call(name: str, arguments: dict[str, Any], *, iteration: int, output: str = "ok", failed: bool = False) -> ToolCallContext:
    result = ToolResult.error(name, output) if failed else ToolResult.success(name, output)
    state = ToolCallState.FAILED if failed else ToolCallState.SUCCEEDED
    return ToolCallContext(tool_name=name, arguments=arguments, state=state, result=result, iteration_count=iteration)


def _run() -> tuple[list[str], list[ToolCallContext]]:
    # E2..E5: a listing call in iteration 1, then three responses that plan and start the per-file audit.
    responses = ["I will list the files.", "I will audit each of these files: a.py, b.py.", "Starting with a.py."]
    calls = [_call("list_files", {"path": "src/api"}, iteration=1, output="a.py\nb.py")]
    return responses, calls


def _payload(**overrides: Any) -> JevRunBriefPayload:
    values: dict[str, Any] = {
        "goal": "Audit each file under src/api",
        "goal_evidence": [{"event": "E1", "quote": "Audit each file under src/api."}],
        "current_step": {"event": "E5", "quote": "Starting with a.py."},
        "next_steps": [{"event": "E4", "quote": "I will audit each of these files"}],
        "items": [
            {"id": "a_py", "name": "a.py", "group": "src/api files", "status": "in_progress", "evidence": [{"event": "E3", "quote": "a.py"}]},
            {"id": "b_py", "name": "b.py", "group": "src/api files", "status": "pending", "evidence": [{"event": "E3", "quote": "b.py"}]},
        ],
        "approaches": [],
        "open_failures": [],
    }
    values.update(overrides)
    return JevRunBriefPayload.model_validate(values)


def _reply(payload: object) -> AsyncMock:
    return AsyncMock(return_value=SimpleNamespace(structured=payload))


class JevRunBriefSettingsTests(unittest.TestCase):
    def test_defaults_reuse_the_main_model_and_hide_the_key(self) -> None:
        settings = JevRunBriefSettings(model_name="cheap-model", api_key="secret")
        self.assertIsNone(settings.provider)
        self.assertNotIn("secret", repr(settings))

    def test_provider_is_normalized_and_needs_its_own_model(self) -> None:
        self.assertIs(JevRunBriefSettings(provider="anthropic", model_name="claude-haiku-4-5-20251001").provider, ModelProvider.ANTHROPIC)
        with self.assertRaisesRegex(ConfigurationError, "requires model_name"):
            JevRunBriefSettings(provider="anthropic")

    def test_rejects_typesafe_unknown_providers_and_blank_models(self) -> None:
        for kwargs in ({"provider": "typesafe", "model_name": "jev"}, {"provider": "nope", "model_name": "x"}, {"model_name": "  "}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigurationError):
                JevRunBriefSettings(**kwargs)

    def test_rejects_invalid_limits_and_a_floor_above_the_ceiling(self) -> None:
        for kwargs in ({"every_iterations": 0}, {"min_gap": True}, {"max_tokens": 1.5}, {"temperature": 2.5}, {"min_gap": 6, "every_iterations": 5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigurationError):
                JevRunBriefSettings(**kwargs)


class JevRunBriefEventsTests(unittest.TestCase):
    def test_numbers_events_like_the_event_log_and_looks_them_up(self) -> None:
        events = JevRunBriefEvents.from_run(REQUEST, *_run())
        self.assertEqual(events.last_event, 5)
        self.assertTrue(events.text("E1").startswith("USER: "))
        self.assertIn("list_files", events.text("E3") or "")
        self.assertIsNone(events.text("E9"))
        self.assertIsNone(events.text("14"))

    def test_contains_ignores_whitespace_but_not_words_or_events(self) -> None:
        events = JevRunBriefEvents.from_run(REQUEST, *_run())
        self.assertTrue(events.contains("E3", "a.py b.py"))
        self.assertTrue(events.contains("E4", "audit  each of\nthese files"))
        self.assertFalse(events.contains("E4", "audit every file"))
        self.assertFalse(events.contains("E2", "a.py"))
        self.assertFalse(events.contains("E4", "   "))

    def test_window_shows_only_events_after_the_pointer(self) -> None:
        events = JevRunBriefEvents.from_run(REQUEST, *_run())
        window = events.window(after=3)
        assert window is not None
        self.assertEqual((window.first_event, window.last_event, window.omitted), (4, 5, 0))
        self.assertNotIn("E3 ", window.text)
        self.assertNotIn("USER", events.window(after=1).text)  # type: ignore[union-attr]
        self.assertIsNone(events.window(after=5))

    def test_long_events_are_clipped_head_and_tail(self) -> None:
        text = "start " + "x" * (JEV_RUN_BRIEF_EVENT_MAX_CHARS * 2) + " end"
        clipped = JevRunBriefEvents.clip(text, JEV_RUN_BRIEF_EVENT_MAX_CHARS)
        self.assertTrue(clipped.startswith("start ") and clipped.endswith(" end"))
        self.assertIn("characters left out", clipped)
        self.assertEqual(JevRunBriefEvents.clip("short", 10), "short")

    def test_a_full_window_keeps_the_newest_whole_then_headers_then_counts_the_rest(self) -> None:
        body = "y" * JEV_RUN_BRIEF_EVENT_MAX_CHARS
        responses = [f"response {index}\n{body}" for index in range(JEV_RUN_BRIEF_WINDOW_MAX_CHARS // JEV_RUN_BRIEF_EVENT_MAX_CHARS * 4)]
        window = JevRunBriefEvents.from_run(REQUEST, responses, []).window(after=1)
        assert window is not None
        self.assertLessEqual(len(window.text), JEV_RUN_BRIEF_WINDOW_MAX_CHARS)
        self.assertIn(f"response {len(responses) - 1}\n{body[:100]}", window.text)
        self.assertIn("rest of this event left out for length", window.text)
        self.assertGreater(window.omitted, 0)
        self.assertTrue(window.text.startswith(f"[{window.omitted} earlier new events"))
        self.assertEqual((window.first_event, window.last_event), (2, len(responses) + 1))


class JevRunFactsReaderTests(unittest.TestCase):
    def test_counts_work_streaks_repeats_and_activity_since_the_last_attempt(self) -> None:
        calls = [
            _call("read", {"path": "a"}, iteration=1),
            _call("test", {"b": 1, "a": 2}, iteration=2, failed=True),
            _call("test", {"a": 2, "b": 1}, iteration=3, failed=True),
            _call("test", {"a": 2, "b": 1}, iteration=4, failed=True),
            _call(IS_DONE_TOOL_NAME, {}, iteration=4),
        ]
        facts = JevRunFactsReader.read(["r"] * 4, calls, tokens_used=1_500, since_iteration=2, tokens_at_refresh=1_000)
        self.assertEqual((facts.iteration, facts.tool_calls, facts.error_streak), (4, 4, 3))
        self.assertEqual((facts.iterations_since_refresh, facts.errors_since_refresh, facts.repeats_since_refresh), (2, 2, 2))
        self.assertEqual([(call.tool_name, call.count) for call in facts.repeated_calls], [("test", 3)])
        self.assertAlmostEqual(facts.token_growth() or 0.0, 0.5)
        self.assertIn("tokens used: 1500", facts.render())

    def test_a_success_ends_the_streak_and_unknown_tokens_have_no_growth(self) -> None:
        calls = [_call("test", {}, iteration=1, failed=True), _call("test", {}, iteration=2)]
        facts = JevRunFactsReader.read(["r", "r"], calls, tokens_used=None, since_iteration=0, tokens_at_refresh=None)
        self.assertEqual(facts.error_streak, 0)
        self.assertIsNone(facts.token_growth())
        self.assertIn("tokens used: unknown", facts.render())


class JevRunBriefVerifierTests(unittest.TestCase):
    def _verify(self, payload: JevRunBriefPayload) -> Any:
        events = JevRunBriefEvents.from_run(REQUEST, *_run())
        return JevRunBriefVerifier(events).verify(payload, iteration=3, through_event=5)

    def test_keeps_verbatim_quotes_and_drops_entries_left_without_evidence(self) -> None:
        payload = _payload(items=[
            {"id": "a_py", "name": "a.py", "group": "src/api files", "status": "pending", "evidence": [{"event": "E3", "quote": "a.py"}]},
            {"id": "c_py", "name": "c.py", "group": "src/api files", "status": "pending", "evidence": [{"event": "E3", "quote": "c.py"}]},
        ])
        verification = self._verify(payload)
        self.assertEqual((verification.kept, verification.dropped), (4, 1))
        self.assertEqual([item.id for item in verification.brief.items], ["a_py"])
        self.assertEqual(verification.brief.through_event, 5)

    def test_rejects_a_reply_whose_quotes_mostly_fail(self) -> None:
        wrong = {"event": "E4", "quote": "I will refactor everything"}
        verification = self._verify(_payload(goal_evidence=[wrong], current_step=wrong, next_steps=[wrong]))
        self.assertIsNone(verification.brief)
        self.assertGreater(verification.dropped, verification.kept)

    def test_accepts_a_reply_with_no_quotes_and_rejects_a_blank_goal(self) -> None:
        empty = {"goal_evidence": [], "current_step": None, "next_steps": [], "items": []}
        self.assertIsNotNone(self._verify(_payload(**empty)).brief)
        self.assertIsNone(self._verify(_payload(goal="   ", **empty)).brief)

    def test_trims_to_caps_without_counting_trimmed_entries_against_the_writer(self) -> None:
        item = {"name": "a.py", "group": "files", "status": "pending", "evidence": [{"event": "E3", "quote": "a.py"}] * (JEV_RUN_BRIEF_EVIDENCE_MAX + 2)}
        items = [{**item, "id": f"item_{index}"} for index in range(JEV_RUN_BRIEF_ITEMS_MAX + 5)]
        verification = self._verify(_payload(items=items, goal="g" * (JEV_RUN_BRIEF_TEXT_MAX_CHARS + 50)))
        self.assertEqual(len(verification.brief.items), JEV_RUN_BRIEF_ITEMS_MAX)
        self.assertEqual(len(verification.brief.items[0].evidence), JEV_RUN_BRIEF_EVIDENCE_MAX)
        self.assertEqual(len(verification.brief.goal), JEV_RUN_BRIEF_TEXT_MAX_CHARS)
        self.assertEqual(verification.dropped, 0)

    def test_cuts_long_quotes_to_the_cap_and_keeps_the_first_of_duplicate_ids(self) -> None:
        long_response = "Plan: " + "check every endpoint carefully " * 40
        events = JevRunBriefEvents.from_run(REQUEST, [long_response], [])
        approach = {"target": "t", "approach": "a", "outcome": "unresolved", "evidence": [{"event": "E2", "quote": "Plan:"}]}
        payload = _payload(
            goal_evidence=[], current_step=None, items=[],
            next_steps=[{"event": "E2", "quote": long_response}],
            approaches=[{**approach, "id": "same"}, {**approach, "id": "same", "target": "other"}],
        )
        brief = JevRunBriefVerifier(events).verify(payload, iteration=1, through_event=2).brief
        self.assertEqual(len(brief.next_steps[0].quote), JEV_RUN_BRIEF_QUOTE_MAX_CHARS)
        self.assertEqual([(approach.id, approach.target) for approach in brief.approaches], [("same", "t")])


class JevRunBriefRecordTests(unittest.TestCase):
    def test_a_brief_at_every_cap_renders_within_its_budget(self) -> None:
        quote = JevRunBriefQuote("E1234567", "q" * JEV_RUN_BRIEF_QUOTE_MAX_CHARS)
        evidence = (quote,) * JEV_RUN_BRIEF_EVIDENCE_MAX
        text = "t" * JEV_RUN_BRIEF_TEXT_MAX_CHARS
        brief = JevRunBrief(
            goal=text, iteration=10_000, through_event=1_234_567, goal_evidence=evidence, current_step=quote,
            next_steps=(quote,) * JEV_RUN_BRIEF_NEXT_STEPS_MAX,
            items=tuple(JevRunBriefItem(f"i{'x' * 60}{index:03d}", text, text, JevRunBriefItemStatus.IN_PROGRESS, evidence) for index in range(JEV_RUN_BRIEF_ITEMS_MAX)),
            approaches=tuple(JevRunBriefApproach(f"a{'x' * 60}{index:03d}", text, text, JevRunBriefOutcome.UNRESOLVED, evidence) for index in range(JEV_RUN_BRIEF_APPROACHES_MAX)),
            open_failures=(quote,) * JEV_RUN_BRIEF_FAILURES_MAX,
        )
        self.assertLessEqual(len(brief.render()), JEV_RUN_BRIEF_RENDER_MAX_CHARS)

    def test_records_reject_values_outside_their_bounds(self) -> None:
        quote = JevRunBriefQuote("E2", "text")
        cases = (
            lambda: JevRunBriefQuote("e2", "text"),
            lambda: JevRunBriefQuote("E2", "q" * (JEV_RUN_BRIEF_QUOTE_MAX_CHARS + 1)),
            lambda: JevRunBriefItem("a", "n", "g", JevRunBriefItemStatus.DONE, ()),
            lambda: JevRunBrief(goal="g", iteration=1, through_event=2, next_steps=(quote,) * (JEV_RUN_BRIEF_NEXT_STEPS_MAX + 1)),
            lambda: JevRunBrief(goal="g", iteration=True, through_event=2),
            lambda: JevRunBriefWindow(first_event=5, last_event=4, text="x"),
        )
        for build in cases:
            with self.assertRaises(ConfigurationError):
                build()


class JevRunBriefWriterTests(unittest.IsolatedAsyncioTestCase):
    def test_uses_the_main_model_and_key_unless_the_brief_names_its_own(self) -> None:
        same = JevRunBriefWriter(_settings(), JevRunBriefSettings(model_name="gpt-4.1-mini"))
        self.assertEqual((same.runner_config.model_name, same.runner_config.api_key), ("gpt-4.1-mini", "main-key"))
        other = JevRunBriefWriter(_settings(), JevRunBriefSettings(provider="anthropic", model_name="claude-haiku-4-5-20251001", api_key="brief-key"))
        self.assertEqual((str(other.runner_config.provider), other.runner_config.api_key), (str(ModelProvider.ANTHROPIC.value), "brief-key"))
        self.assertEqual(len(other.tools), 0)

    async def test_clears_history_and_reads_the_previous_brief_or_none(self) -> None:
        writer = JevRunBriefWriter(_settings(), JevRunBriefSettings())
        window = JevRunBriefWindow(first_event=2, last_event=3, text="E2 ASSISTANT iteration=1: hi\nE3 ASSISTANT iteration=2: bye")
        previous = JevRunBrief(goal="Earlier goal", iteration=1, through_event=1)
        writer.history.append("stale")  # type: ignore[arg-type]
        with patch.object(writer, "arun", new=_reply(_payload())) as arun:
            self.assertIsInstance(await writer.write(REQUEST, None, window), JevRunBriefPayload)
            self.assertEqual(writer.history, [])
            await writer.write(REQUEST, previous, window)
        first, second = (call.args[0].prompt for call in arun.call_args_list)
        self.assertIn("<previous_brief>\nnone\n</previous_brief>", first)
        self.assertIn('"goal":"Earlier goal"', second)
        self.assertIn('first="E2" last="E3"', second)
        self.assertNotIn("{", Prompts().get(Prompt.JEV_RUN_BRIEF_UPDATE_PROMPT).format(request="r", previous_brief="p", first_event="E2", last_event="E3", events="e"))

    async def test_an_outage_or_a_reply_without_the_schema_yields_none(self) -> None:
        writer = JevRunBriefWriter(_settings(), JevRunBriefSettings())
        window = JevRunBriefWindow(first_event=2, last_event=2, text="E2 x")
        with patch.object(writer, "arun", new=AsyncMock(side_effect=VidbyteSdkError("down"))):
            self.assertIsNone(await writer.write(REQUEST, None, window))
        with patch.object(writer, "arun", new=_reply({"goal": "not a payload"})):
            self.assertIsNone(await writer.write(REQUEST, None, window))


class JevRunBriefKeeperTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.keeper = JevRunBriefKeeper(_settings(), JevRunBriefSettings(every_iterations=6, min_gap=2))
        self.keeper.begin(REQUEST)

    def _facts(self, iteration: int, calls: list[ToolCallContext] | None = None, tokens: int | None = None) -> Any:
        return self.keeper.read_facts(["r"] * iteration, calls or [], tokens_used=tokens)

    def test_cadence_waits_for_the_opening_plan_then_the_ceiling(self) -> None:
        self.assertFalse(self.keeper.due(self._facts(2)))
        self.assertTrue(self.keeper.due(self._facts(3)))
        self.keeper.brief = JevRunBrief(goal="g", iteration=3, through_event=4)
        self.keeper._attempted_at = 3
        self.assertFalse(self.keeper.due(self._facts(4)))
        self.assertFalse(self.keeper.due(self._facts(8)))
        self.assertTrue(self.keeper.due(self._facts(9)))

    def test_early_triggers_fire_after_the_floor_only(self) -> None:
        self.keeper.brief = JevRunBrief(goal="g", iteration=3, through_event=4)
        self.keeper._attempted_at, self.keeper._tokens_at_attempt = 3, 1_000
        failing = [_call("test", {"n": index}, iteration=4 + index, failed=True) for index in range(3)]
        repeated = [_call("read", {"p": "a"}, iteration=4 + index) for index in range(3)]
        self.assertFalse(self.keeper.due(self._facts(4, failing)))
        self.assertTrue(self.keeper.due(self._facts(6, failing)))
        self.assertTrue(self.keeper.due(self._facts(6, repeated)))
        self.assertTrue(self.keeper.due(self._facts(5, tokens=1_250)))
        self.assertFalse(self.keeper.due(self._facts(5, tokens=1_200)))

    async def test_a_verified_refresh_replaces_the_brief_and_advances_the_pointer(self) -> None:
        responses, calls = _run()
        with patch.object(self.keeper.writer, "arun", new=_reply(_payload())) as arun:
            update = await self.keeper.refresh_if_due(responses, calls, tokens_used=100)
            self.assertEqual((update.status, update.first_event, update.last_event), (JevRunBriefUpdateStatus.UPDATED, 2, 5))
            self.assertEqual(self.keeper.brief.through_event, 5)
            responses += ["Now b.py.", "Both files audited."]
            await self.keeper.refresh_if_due(responses, calls, tokens_used=200)
        second_prompt = arun.call_args_list[1].args[0].prompt
        self.assertIn('first="E6" last="E7"', second_prompt)
        self.assertIn('"id":"a_py"', second_prompt)
        self.assertIs(self.keeper.last_update.status, JevRunBriefUpdateStatus.UPDATED)

    async def test_an_outage_or_a_rejection_keeps_the_brief_and_rereads_the_same_events(self) -> None:
        responses, calls = _run()
        wrong = {"event": "E4", "quote": "invented"}
        with patch.object(self.keeper.writer, "arun", new=_reply(None)):
            update = await self.keeper.refresh_if_due(responses, calls, tokens_used=None)
        self.assertIs(update.status, JevRunBriefUpdateStatus.UNAVAILABLE)
        self.assertIsNone(self.keeper.brief)
        responses += ["More work.", "Even more work."]
        with patch.object(self.keeper.writer, "arun", new=_reply(_payload(goal_evidence=[wrong], current_step=wrong, next_steps=[wrong], items=[]))):
            update = await self.keeper.refresh_if_due(responses, calls, tokens_used=None)
        self.assertIs(update.status, JevRunBriefUpdateStatus.REJECTED)
        self.assertEqual(update.first_event, 2)
        self.assertIsNone(self.keeper.brief)

    async def test_no_due_refresh_or_no_new_events_calls_no_model(self) -> None:
        with patch.object(self.keeper.writer, "arun", new=_reply(_payload())) as arun:
            self.assertIsNone(await self.keeper.refresh_if_due(["r"], [], tokens_used=None))
            self.keeper._through_event = 4
            self.assertIsNone(await self.keeper.refresh_if_due(["r", "r", "r"], [], tokens_used=None))
        arun.assert_not_awaited()
        self.assertEqual(self.keeper._attempted_at, 3)

    def test_begin_forgets_the_previous_run(self) -> None:
        self.keeper.brief = JevRunBrief(goal="g", iteration=3, through_event=4)
        self.keeper._attempted_at = 9
        self.keeper.begin("next request")
        self.assertIsNone(self.keeper.brief)
        self.assertEqual((self.keeper.request, self.keeper._attempted_at), ("next request", 0))


if __name__ == "__main__":
    unittest.main()
