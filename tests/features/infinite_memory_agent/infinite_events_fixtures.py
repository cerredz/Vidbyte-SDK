"""FILE: tests/features/infinite_memory_agent/infinite_events_fixtures.py

PURPOSE: Shared helpers for the InfiniteMemory events and handoff tests (docs/spec/infinite-memory-events/spec.md): readers for a collected event stream, an independent statement of the spec's cut rule, the portability check every collected event must pass, the AC-2 one-pair script, and run views that let two runs be compared once their run id, timestamps, tmp folder, and call ids are replaced by placeholders.
ROLE IN CODEBASE: Imported by test_infinite_memory_events_stream.py, test_infinite_memory_events_lifecycle.py, test_infinite_memory_events_pairs.py, test_infinite_memory_events_records.py, and test_infinite_memory_handoff.py. It builds on infinite_memory_fixtures.py and leaves that file unchanged.
ARCHITECTURE NOTE: The cut rule here is written from spec INV-12 alone (a lone surrogate becomes "?", a one-line field is collapsed, then a text over its cap keeps its first cap - 8 characters and ends with the literal " … [cut]"). It never calls OutputText, so a wrong cap, marker, or collapse in the implementation shows up as a mismatch instead of agreeing with itself. A sink in these tests is a plain list.append or a small test function; nothing here mocks InfiniteEvents, the records, OutputText, hashlib, or datetime (spec section 13).
FUNCTION INVENTORY: cut / line state the cap rule for multi-line or exact fields and for collapsed one-line fields; kinds / of_kind / one read a collected stream; assert_portable checks every event's envelope, JSON form, leaf types, and details size (AC-13, INV-11..INV-13, INV-33, INV-35); json_sizes measures one value under the four json.dumps settings; ac2_tree builds the AC-2 script; run_view and calls_view return a run's workspace files and model calls with run-specific values replaced; event_warnings reads the events logger's records from caplog.
COMMON MODIFICATION PATTERNS: When the spec changes a cap or the marker, change the literal here and nowhere else. A new shared script for several event tests goes here as one builder returning a ScriptedTree.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents.infinite, vidbyte.lib.constants.infinite, vidbyte.lib.enums.infinite, or vidbyte.lib.dataclasses.infinite at module level: before the feature exists that would make every importing module a collection error and abort the session. 2. Do not derive expected caps, markers, or templates from the implementation; take them from the spec. 3. Do not assert inside a sink: InfiniteEvents catches what a sink raises, so record what the sink saw and assert after the run.
KNOWN EDGE CASES: A journal stamp looks like 2026-10-16T08:15:00+00:00 and an entry stamp the same, so one pattern covers both. The tmp folder appears in prompts in three spellings on Windows (backslashes, forward slashes, and JSON-escaped backslashes), so run views replace all three. The fixture's DEFAULT_USAGE has no total_tokens, so a test about token totals must script total_tokens itself (see the S2 report).
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-events/spec.md sections 6.1, 6.2, 9.1 and 13; docs/spec/infinite-memory-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    ScriptedTree,
    generator,
    launch,
    reply,
    seen_text,
    snapshot,
    task,
    tool_call,
    verifier,
)

# Spec INV-12 and section 9.1: the one marker every cut event and handoff text ends with.
MARKER = " … [cut]"
# Spec section 9.1 caps, in characters (S, T, P, L, B, K) and items (N).
SUMMARY_MAX = 280
TEXT_MAX = 500
PATH_MAX = 500
LINE_MAX = 120
LABEL_MAX = 64
KEY_MAX = 512
MAX_ITEMS = 5
MAX_COUNT = 9_223_372_036_854_775_807
MAX_DETAILS_BYTES = 32_768
# Spec section 9.1 handoff bounds (INV-37).
HANDOFF_OUTCOME_MAX = 239_000
HANDOFF_SECTION_MAX = 15_900
HANDOFF_LINE_MAX = 1_000
HANDOFF_TEXT_MAX = 366_500
HANDOFF_TITLES = ("Outcome", "Work done", "Decisions", "Facts", "Lessons", "Open questions", "Files", "Unverified or failed work", "How to continue")
# The logger InfiniteEvents writes its one warning per failed event to (spec D-3, section 13).
EVENTS_LOGGER = "vidbyte.agents.infinite.events"
RUN_ID_PATTERN = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")
_SURROGATE = re.compile("[\ud800-\udfff]")
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
_CALL_ID = re.compile(r"call-\d+")

# The AC-2 script: one task whose generator stages a fact, writes a new note, and replies; its verifier passes.
PAIR = "p"
FACT = "Acme charges 49 USD per seat"
NOTE_PATH = "notes/acme.md"
NOTE_TEXT = "Acme pricing page, read on 2026-10-15: Pro is 49 USD per seat.\n"
NOTE_DESCRIPTION = "Acme pricing notes"
GEN_SUMMARY = "P-SUMMARY: Acme is 49 USD per seat."
PASSED = "Checked every criterion against its source.\nVERDICT: passed"
ROOT_ANSWER = "ROOT-FINAL: Acme is cheapest at 49 USD per seat."
AC2_KINDS = ["run_started", "subagent_launched", "memory_staged", "file_written", "generator_finished", "subagent_finished", "run_finished"]


# ---------------------------------------------------------------- the cut rule (spec INV-12)


def cut(text: str, cap: int) -> str:
    """A multi-line or exact field: a lone surrogate becomes "?", then a text over cap keeps cap - 8 characters plus the marker."""
    text = _SURROGATE.sub("?", text)
    return text if len(text) <= cap else text[: cap - len(MARKER)] + MARKER


def line(text: str, cap: int) -> str:
    """A collapsed one-line field (and every summary): surrogates replaced, whitespace runs made one space, then cut."""
    return cut(" ".join(_SURROGATE.sub("?", text).split()), cap)


# ---------------------------------------------------------------- reading a collected stream


def kinds(seen: Sequence[Any]) -> list[str]:
    """The kind value of each collected event, in delivery order."""
    return [event.kind.value for event in seen]


def of_kind(seen: Sequence[Any], kind: str) -> list[Any]:
    """Every collected event of one kind, in delivery order."""
    return [event for event in seen if event.kind.value == kind]


def one(seen: Sequence[Any], kind: str) -> Any:
    """The single collected event of one kind; fails when there is not exactly one."""
    found = of_kind(seen, kind)
    assert len(found) == 1, f"expected one {kind} event, got {len(found)}: {kinds(seen)}"
    return found[0]


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def json_sizes(value: Any) -> tuple[int, ...]:
    """UTF-8 byte sizes of json.dumps(value) under ensure_ascii true/false and default/compact separators."""
    return tuple(len(json.dumps(value, ensure_ascii=ascii_only, separators=separators, default=_iso).encode("utf-8")) for ascii_only in (True, False) for separators in (None, (",", ":")))


def _leaves(value: Any, where: str) -> list[str]:
    # Every leaf type INV-13 does not allow, with where it sits; a str-valued enum member is a str.
    if isinstance(value, Mapping):
        return [problem for key, item in value.items() for problem in ([f"{where}: key {key!r} is not text"] if not isinstance(key, str) else []) + _leaves(item, f"{where}.{key}")]
    if isinstance(value, tuple):
        return [problem for index, item in enumerate(value) for problem in _leaves(item, f"{where}[{index}]")]
    if value is None or isinstance(value, (bool, str, datetime)):
        return []
    if isinstance(value, int):
        return [] if 0 <= value <= MAX_COUNT else [f"{where}: int {value} is outside 0..2**63-1"]
    if isinstance(value, float):
        return [] if math.isfinite(value) else [f"{where}: float {value} is not finite"]
    return [f"{where}: {type(value).__name__} is not an allowed leaf type"]


def assert_portable(seen: Sequence[Any]) -> None:
    """AC-13, INV-11..INV-13, INV-33, INV-35: every event serializes both ways, holds only allowed leaves, has a valid envelope, and fits the size bound."""
    from vidbyte.lib.dataclasses.infinite import InfiniteEvent

    assert seen, "no event was delivered"
    assert not hasattr(InfiniteEvent, "to_dict") and not hasattr(InfiniteEvent, "from_dict"), "InfiniteEvent must not grow to_dict/from_dict (INV-13)"
    for event in seen:
        label = f"{event.kind.value} from {event.agent_key!r}"
        assert isinstance(event, InfiniteEvent), label
        data = dataclasses.asdict(event)
        json.dumps(data, default=_iso, ensure_ascii=True)
        json.dumps(data, default=_iso, ensure_ascii=False).encode("utf-8")
        assert not _leaves(data, event.kind.value), _leaves(data, event.kind.value)
        assert RUN_ID_PATTERN.fullmatch(event.run_id), label
        assert event.at.tzinfo is not None and event.at.utcoffset() == timedelta(0), f"{label}: at is not UTC"
        assert event.at.microsecond % 1_000 == 0, f"{label}: at is finer than a millisecond"
        assert 1 <= len(event.summary) <= SUMMARY_MAX and event.summary.splitlines() == [event.summary], f"{label}: summary {event.summary!r}"
        assert event.agent_key.isascii() and 1 <= len(event.agent_key) <= KEY_MAX, label
        assert isinstance(event.depth, int) and event.depth >= 0, label
        sizes = json_sizes(dataclasses.asdict(event.details))
        assert max(sizes) <= MAX_DETAILS_BYTES, f"{label}: details are {sizes} bytes"


# ---------------------------------------------------------------- scripts and run views


def ac2_tree(name: str = PAIR) -> ScriptedTree:
    """The AC-2 script: the root launches `name`; its generator remembers FACT, writes NOTE_PATH, and replies; its verifier passes; the root answers."""
    return ScriptedTree(
        {
            ROOT: [launch(task(name)), reply(ROOT_ANSWER)],
            generator(name): [
                tool_call("remember", {"kind": "fact", "text": FACT}),
                tool_call("write_note", {"path": NOTE_PATH, "text": NOTE_TEXT, "description": NOTE_DESCRIPTION}),
                reply(GEN_SUMMARY),
            ],
            verifier(name): [reply(PASSED)],
        }
    )


def _placeholders(text: str, base: Path, run_id: str) -> str:
    text = text.replace(run_id, "<RUN>")
    for spelling in (json.dumps(str(base))[1:-1], str(base), base.as_posix()):
        text = text.replace(spelling, "<BASE>")
    return _CALL_ID.sub("<CALL>", _STAMP.sub("<AT>", text))


def run_view(root: Path, base: Path, run_id: str) -> dict[str, str]:
    """Every workspace file under `root`, journal included, keyed and filled with the run id, stamps, and `base` replaced."""
    return {_placeholders(name, base, run_id): _placeholders(data.decode("utf-8"), base, run_id) for name, data in snapshot(root, include_runs=True).items()}


def calls_view(tree: ScriptedTree, base: Path, run_id: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """Each model call as (agent, everything it carried, offered tools), with run-specific values replaced."""
    return [(call.agent, _placeholders(seen_text(call), base, run_id), call.tools) for call in tree.calls]


def event_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The records the events module's logger wrote during the test."""
    return [record for record in caplog.records if record.name == EVENTS_LOGGER]
