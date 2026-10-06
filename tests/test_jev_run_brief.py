"""FILE: tests/test_jev_run_brief.py

PURPOSE: Tests structured note selection, event-backed verification, append behavior, writer configuration, and keeper cadence.
ROLE IN CODEBASE: Covers the standalone JEV structured note-taking compaction flow and its prompt/schema contracts.
ARCHITECTURE NOTE: Model calls are replaced with structured replies; event numbering and note verification run for real.
COMMON MODIFICATION PATTERNS: Add cases for schema caps, fresh-event verification, retry context, append behavior, and keeper cadence.
KNOWN EDGE CASES: Empty deltas are valid; clipped prompt events retain their full bodies only for verification.
RELATED DOCS: skills/jev-agent/SKILL.md and vidbyte/agents/jev/README.md.
TESTS: python -m pytest tests/test_jev_run_brief.py.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from vidbyte.agents.jev.brief import JevRunBriefKeeper, JevRunBriefWriter
from vidbyte.agents.jev.settings import JevAgentSettings, JevRunBriefSettings
from vidbyte.lib.constants.jev import (
    JEV_RUN_BRIEF_EVENT_MAX_CHARS,
    JEV_RUN_BRIEF_NOTE_MAX_CHARS,
    JEV_RUN_BRIEF_NOTES_MAX,
    JEV_RUN_BRIEF_WINDOW_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import (
    JevRunBrief,
    JevRunBriefAppendPayload,
    JevRunBriefNote,
    JevRunBriefVerification,
    JevRunBriefWindow,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError

REQUEST = "Audit each file under src/api."


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {
        "name": "main",
        "system_prompt": "Do the work.",
        "provider": "openai",
        "model_name": "gpt-4.1",
        "api_key": "main-key",
    }
    values.update(overrides)
    return JevAgentSettings(**values)


def _call(name: str, arguments: dict[str, Any], *, iteration: int, output: str = "ok") -> ToolCallContext:
    result = ToolResult.success(name, output)
    return ToolCallContext(tool_name=name, arguments=arguments, state=ToolCallState.SUCCEEDED, result=result, iteration_count=iteration)


def _run() -> tuple[list[str], list[ToolCallContext]]:
    responses = ["I will list the files.", "I will audit each of these files: a.py, b.py."]
    calls = [_call("list_files", {"path": "src/api"}, iteration=1, output="a.py\nb.py")]
    return responses, calls


def _delta(*notes: tuple[str, str]) -> JevRunBriefAppendPayload:
    return JevRunBriefAppendPayload(notes=[{"event": event, "text": text} for event, text in notes])


def _reply(payload: object) -> SimpleNamespace:
    return SimpleNamespace(structured=payload)


class JevRunBriefSettingsTests(unittest.TestCase):
    def test_defaults_and_provider_validation(self) -> None:
        settings = JevRunBriefSettings(model_name="cheap-model", api_key="secret")
        self.assertIsNone(settings.provider)
        self.assertEqual(settings.every_iterations, 10)
        self.assertNotIn("secret", repr(settings))
        self.assertIs(JevRunBriefSettings(provider="anthropic", model_name="claude-haiku-4-5-20251001").provider, ModelProvider.ANTHROPIC)
        with self.assertRaisesRegex(ConfigurationError, "requires model_name"):
            JevRunBriefSettings(provider="anthropic")

    def test_rejects_invalid_provider_and_limits(self) -> None:
        for kwargs in (
            {"provider": "typesafe", "model_name": "jev"},
            {"provider": "unknown", "model_name": "x"},
            {"model_name": "  "},
            {"every_iterations": 0},
            {"every_iterations": True},
            {"max_tokens": 1.5},
            {"temperature": 2.5},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigurationError):
                JevRunBriefSettings(**kwargs)


class JevRunBriefSchemaTests(unittest.TestCase):
    def test_writer_schema_is_only_new_notes_and_aggregate_has_goal_plus_notes(self) -> None:
        writer_schema = JevRunBriefAppendPayload.model_json_schema()
        self.assertEqual(set(writer_schema["properties"]), {"notes"})
        self.assertEqual(writer_schema["properties"]["notes"]["maxItems"], JEV_RUN_BRIEF_NOTES_MAX)
        note_schema = writer_schema["$defs"]["JevRunBriefNotePayload"]["properties"]
        self.assertEqual(note_schema["text"]["maxLength"], JEV_RUN_BRIEF_NOTE_MAX_CHARS)

        aggregate = JevRunBrief(goal=REQUEST, notes=(), iteration=3, through_event=1).payload()
        self.assertEqual(set(aggregate.model_dump()), {"goal", "notes"})
        self.assertEqual(aggregate.goal, REQUEST)
        self.assertEqual(aggregate.notes, [])

    def test_note_record_rejects_text_over_its_cap(self) -> None:
        with self.assertRaises(ConfigurationError):
            JevRunBriefNote(event="E2", text="x" * (JEV_RUN_BRIEF_NOTE_MAX_CHARS + 1))


class JevRunBriefWriterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.writer = JevRunBriefWriter(_settings(), JevRunBriefSettings())

    def test_uses_main_provider_by_default_and_allows_an_independent_provider(self) -> None:
        self.assertEqual((self.writer.runner_config.model_name, self.writer.runner_config.api_key), ("gpt-4.1", "main-key"))
        other = JevRunBriefWriter(
            _settings(),
            JevRunBriefSettings(provider="anthropic", model_name="claude-haiku-4-5-20251001", api_key="brief-key"),
        )
        self.assertEqual((str(other.runner_config.provider), other.runner_config.api_key), (ModelProvider.ANTHROPIC.value, "brief-key"))
        self.assertEqual(len(other.tools), 0)

    def test_window_reuses_event_log_ids_and_keeps_full_fresh_events(self) -> None:
        responses, calls = _run()
        window = self.writer.window(REQUEST, responses, calls, after_event=1)
        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual((window.first_event, window.last_event), (2, 4))
        self.assertIn("E2 ASSISTANT iteration=1: I will list the files.", window.text)
        self.assertEqual(window.full_events[1][0], 3)
        self.assertIn("output=a.py", window.full_events[1][1])

        later = self.writer.window(REQUEST, responses, calls, after_event=3)
        self.assertIsNotNone(later)
        assert later is not None
        self.assertEqual((later.first_event, later.last_event), (4, 4))
        self.assertIsNone(self.writer.window(REQUEST, responses, calls, after_event=4))

    def test_window_clips_each_event_and_bounds_total_input(self) -> None:
        responses = ["x" * 5_000 for _ in range(25)]
        window = self.writer.window(REQUEST, responses, [], after_event=1)
        self.assertIsNotNone(window)
        assert window is not None
        self.assertLessEqual(len(window.text), JEV_RUN_BRIEF_WINDOW_MAX_CHARS)
        self.assertGreater(window.omitted, 0)
        self.assertLess(len(window.full_events), len(responses))
        self.assertIn(" [...] ", window.text)
        self.assertGreater(len(window.full_events[-1][1]), JEV_RUN_BRIEF_EVENT_MAX_CHARS)

    def test_verification_requires_a_verbatim_passage_from_a_fresh_full_event(self) -> None:
        responses, calls = _run()
        window = self.writer.window(REQUEST, responses, calls, after_event=1)
        assert window is not None
        verified = self.writer.verify(_delta(("E3", "output=a.py\nb.py")), REQUEST, None, window, iteration=2)
        self.assertIsNotNone(verified.brief)
        assert verified.brief is not None
        self.assertEqual(verified.brief.goal, REQUEST)
        self.assertEqual(verified.brief.notes, (JevRunBriefNote("E3", "output=a.py\nb.py"),))
        self.assertEqual(verified.brief.through_event, 4)

        bad_event = self.writer.verify(_delta(("E1", "Audit each file")), REQUEST, None, window, iteration=2)
        self.assertIsNone(bad_event.brief)
        self.assertIn("not a fresh full event", bad_event.error or "")
        bad_text = self.writer.verify(_delta(("E2", "I did something else")), REQUEST, None, window, iteration=2)
        self.assertIsNone(bad_text.brief)
        self.assertIn("not present in full event E2", bad_text.error or "")

    def test_verification_rejects_duplicates_from_delta_or_previous_brief(self) -> None:
        responses, calls = _run()
        window = self.writer.window(REQUEST, responses, calls, after_event=1)
        assert window is not None
        repeated = _delta(("E2", "I will list the files."), ("E2", "I will   list the files."))
        duplicate = self.writer.verify(repeated, REQUEST, None, window, iteration=2)
        self.assertIsNone(duplicate.brief)
        self.assertIn("duplicates an existing note", duplicate.error or "")

        previous = JevRunBrief(
            goal=REQUEST,
            notes=(JevRunBriefNote("E2", "I will list the files."),),
            iteration=1,
            through_event=1,
        )
        duplicate = self.writer.verify(_delta(("E2", "I will list the files.")), REQUEST, previous, window, iteration=2)
        self.assertIsNone(duplicate.brief)
        self.assertIn("duplicates an existing note", duplicate.error or "")

    def test_append_keeps_only_newest_fifty_notes(self) -> None:
        responses = ["old response"] * 50 + ["new note at event fifty-two"]
        window = self.writer.window(REQUEST, responses, [], after_event=51)
        assert window is not None
        previous = JevRunBrief(
            goal=REQUEST,
            notes=tuple(JevRunBriefNote(f"E{number}", f"old note {number}") for number in range(2, 52)),
            iteration=10,
            through_event=51,
        )
        result = self.writer.verify(_delta(("E52", "new note at event fifty-two")), REQUEST, previous, window, iteration=11)
        self.assertIsNotNone(result.brief)
        assert result.brief is not None
        self.assertEqual(len(result.brief.notes), JEV_RUN_BRIEF_NOTES_MAX)
        self.assertEqual(result.brief.notes[0].event, "E3")
        self.assertEqual(result.brief.notes[-1], JevRunBriefNote("E52", "new note at event fifty-two"))

    def test_empty_delta_is_valid_and_advances_the_event_pointer(self) -> None:
        previous = JevRunBrief(goal=REQUEST, notes=(JevRunBriefNote("E2", "old evidence"),), iteration=3, through_event=2)
        window = JevRunBriefWindow(
            first_event=3,
            last_event=3,
            text="E3 ASSISTANT iteration=2: no new note",
            full_events=((3, "ASSISTANT iteration=2: no new note"),),
        )
        result = self.writer.verify(_delta(), REQUEST, previous, window, iteration=4)
        self.assertIsNotNone(result.brief)
        assert result.brief is not None
        self.assertEqual(result.brief.notes, previous.notes)
        self.assertEqual(result.brief.through_event, 3)

    async def test_invalid_delta_retry_includes_original_events_and_verification_error(self) -> None:
        responses, calls = _run()
        window = self.writer.window(REQUEST, responses, calls, after_event=1)
        assert window is not None
        invalid = _delta(("E2", "not in the event"))
        valid = _delta(("E2", "I will list the files."))
        self.writer.history.append("stale")  # type: ignore[arg-type]
        with patch.object(self.writer, "arun", new=AsyncMock(side_effect=[_reply(invalid), _reply(valid)])) as arun:
            result = await self.writer.write(REQUEST, None, window, iteration=len(responses))
        self.assertIsNotNone(result)
        assert result is not None and result.brief is not None
        self.assertEqual(self.writer.history, [])
        self.assertEqual(arun.await_count, 2)
        first_prompt = arun.call_args_list[0].args[0].prompt
        retry_prompt = arun.call_args_list[1].args[0].prompt
        self.assertIn(window.text, first_prompt)
        self.assertIn(window.text, retry_prompt)
        self.assertIn("<verification_error>", retry_prompt)
        self.assertIn("not present in full event E2", retry_prompt)

    async def test_outage_or_non_append_schema_returns_none(self) -> None:
        window = self.writer.window(REQUEST, ["one response"], [], after_event=1)
        assert window is not None
        with patch.object(self.writer, "arun", new=AsyncMock(side_effect=VidbyteSdkError("down"))):
            self.assertIsNone(await self.writer.write(REQUEST, None, window, iteration=1))
        with patch.object(self.writer, "arun", new=AsyncMock(return_value=_reply({"goal": REQUEST}))):
            self.assertIsNone(await self.writer.write(REQUEST, None, window, iteration=1))


class JevRunBriefKeeperTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.keeper = JevRunBriefKeeper(_settings(), JevRunBriefSettings(every_iterations=6))
        self.keeper.begin(REQUEST)

    def test_simple_cadence_starts_early_then_waits_for_new_iterations(self) -> None:
        self.assertFalse(self.keeper.due(2))
        self.assertTrue(self.keeper.due(3))
        self.keeper._last_attempt_iteration = 3
        self.assertFalse(self.keeper.due(8))
        self.assertTrue(self.keeper.due(9))

    async def test_rejection_preserves_brief_and_pointer_until_a_valid_empty_update(self) -> None:
        initial = JevRunBrief(
            goal=REQUEST,
            notes=(JevRunBriefNote("E2", "I will list the files."),),
            iteration=3,
            through_event=4,
        )
        rejected = JevRunBriefVerification(brief=None, error="Note 1 is not verifiable")
        advanced = JevRunBrief(goal=REQUEST, notes=initial.notes, iteration=15, through_event=16)
        with (
            patch.object(
                self.keeper.writer,
                "write",
                new=AsyncMock(side_effect=[JevRunBriefVerification(brief=initial), rejected, JevRunBriefVerification(brief=advanced)]),
            ) as write,
            patch.object(self.keeper.writer, "window", wraps=self.keeper.writer.window) as window,
        ):
            first = await self.keeper.refresh_if_due(["r1", "r2", "r3"], [])
            self.assertIs(first.brief, initial)  # type: ignore[union-attr]
            self.assertEqual(self.keeper._through_event, 4)
            self.assertFalse(self.keeper.due(8))

            failed = await self.keeper.refresh_if_due([f"r{i}" for i in range(9)], [])
            self.assertIs(failed, rejected)
            self.assertIs(self.keeper.brief, initial)
            self.assertEqual(self.keeper._through_event, 4)
            self.assertFalse(self.keeper.due(14))

            updated = await self.keeper.refresh_if_due([f"r{i}" for i in range(15)], [])
            self.assertIs(updated.brief, advanced)  # type: ignore[union-attr]
            self.assertEqual(self.keeper._through_event, 16)
            self.assertEqual([call.kwargs["after_event"] for call in window.call_args_list], [1, 4, 4])
            self.assertEqual(write.await_count, 3)
            self.assertFalse(self.keeper.due(16))
            self.assertTrue(self.keeper.due(21))

    async def test_unavailable_writer_preserves_pointer_and_waits_for_the_cadence(self) -> None:
        window = self.keeper.writer.window(REQUEST, ["a", "b", "c"], [], after_event=1)
        assert window is not None
        with patch.object(self.keeper.writer, "write", new=AsyncMock(return_value=None)) as write:
            result = await self.keeper.refresh_if_due(["a", "b", "c"], [])
        self.assertIsNone(result)
        self.assertIsNone(self.keeper.brief)
        self.assertEqual(self.keeper._through_event, 1)
        self.assertFalse(self.keeper.due(8))
        self.assertTrue(self.keeper.due(9))
        write.assert_awaited_once()

    def test_begin_resets_the_goal_brief_pointer_and_cadence(self) -> None:
        self.keeper.brief = JevRunBrief(goal=REQUEST, notes=(), iteration=3, through_event=4)
        self.keeper._through_event = 4
        self.keeper._last_attempt_iteration = 3
        self.keeper.begin("new mission")
        self.assertIsNone(self.keeper.brief)
        self.assertEqual(self.keeper.request, "new mission")
        self.assertEqual(self.keeper._through_event, 1)
        self.assertIsNone(self.keeper._last_attempt_iteration)


if __name__ == "__main__":
    unittest.main()
