"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_events_records.py

PURPOSE: Proves the event vocabulary and records on their own, outside a scripted run: the public names and where they import from, the on_event settings check, the size bound of every details record at its worst case, the caps and line rules every record enforces, the envelope's own checks (at, details type, summary, keys), zero and unknown costs, how InfiniteEvents shortens keys over 508 characters, how it reads usage from a reply, how it sums a pair's usage over several replies or none, and how it clamps a huge settings limit.
ROLE IN CODEBASE: Record-and-writer layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-events/spec.md (AC-21, AC-24, AC-30, AC-32, AC-37 a, b, f; INV-11..INV-14, INV-32..INV-36; EC-3, EC-13, EC-14, EC-36; D-18, D-24, D-25, D-27). Exercises vidbyte/lib/enums/infinite.py, vidbyte/lib/dataclasses/infinite.py, vidbyte/agents/infinite/settings.py, and vidbyte/agents/infinite/events.py with a real workspace, journal, and launch tool.
ARCHITECTURE NOTE: The worst-case shapes and the byte figures are copied from spec section 9.1 (Worst case), and the field caps from its table, so this file states the bound independently of the implementation: a record that grows a field, loses a cap, or forgets a one-line rule fails here even when every scripted run still passes. The key rule is restated from INV-35 with hashlib, never read from the module under test.
FUNCTION INVENTORY: test_the_public_names_are_one_object_wherever_they_are_exported (AC-24, NG-9); test_on_event_refuses_a_non_callable_or_asynchronous_sink (AC-21, INV-36, D-27); test_on_event_accepts_none_and_synchronous_callables_as_the_last_field (AC-21, INV-32); test_every_details_record_at_its_caps_fits_its_worst_case_figure (AC-30, INV-33, NFR-4); test_every_capped_field_refuses_one_character_more_and_every_list_a_sixth_item (AC-30, INV-12, INV-34, INV-35); test_one_line_fields_refuse_a_line_break (INV-12); test_the_envelope_refuses_a_wrong_time_details_type_summary_key_or_depth (AC-37 b, INV-11, INV-13, INV-14); test_cost_may_be_zero_or_unknown_but_never_negative_or_infinite (AC-37 a, INV-13, D-18); test_keys_over_508_characters_are_shortened_by_digest_and_stay_distinct (AC-32, INV-35, D-25); test_generator_usage_is_read_from_the_reply_rollup_and_unknown_cost_is_none (AC-37 f, D-18, EC-3); test_a_pairs_cost_is_known_only_when_every_reply_is_fully_priced_and_unknown_without_replies (D-18, EC-13, EC-14); test_a_limit_above_the_count_cap_is_reported_at_the_cap (EC-36, D-24). _worst, _baseline, _build, _refusal_field, _short_key, and _long_launcher_key are builders.
COMMON MODIFICATION PATTERNS: A new details field adds one row to _FIELDS (with its cap and line type from spec section 9.1) and its worst-case value to _worst, and the spec's worst-case table figure is updated before _FIGURES here.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not compute expected caps, sizes, or keys by calling the implementation's helpers; restate them from the spec. 3. Do not loosen _FIGURES to whatever the implementation measures; a larger number is a spec change.
KNOWN EDGE CASES: A staged key at 64 characters is "s" plus 63 digits, the longest value INFINITE_STAGED_KEY_PATTERN allows inside the label cap. The item records InfiniteCommittedEntry and InfiniteDroppedEntry carry no caps of their own (spec D-6); a too-long item text is refused by the containing InfiniteSubagentFinishedDetails, and the spec does not say how the error names the item, so the refusal check accepts any field name that starts with the list's qualified name.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-events/spec.md sections 6.1, 6.2, 8.5, 9.1, 9.2 and 13; docs/spec/infinite-memory-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_events_records.py -q
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_events_fixtures import (
    EVENTS_LOGGER,
    KEY_MAX,
    LABEL_MAX,
    LINE_MAX,
    MAX_COUNT,
    MAX_DETAILS_BYTES,
    MAX_ITEMS,
    PATH_MAX,
    SUMMARY_MAX,
    TEXT_MAX,
    assert_portable,
    event_warnings,
    json_sizes,
    kinds,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    MODEL,
    RUN_A,
    TASK,
    build_settings,
)
from vidbyte.lib.errors import ConfigurationError

# Spec section 9.1 Worst case: the largest details size in bytes of each record over the four json.dumps settings.
_FIGURES = {
    "InfiniteRunStartedDetails": 15_450,
    "InfiniteRunResumedDetails": 8_686,
    "InfiniteRunFinishedDetails": 6_930,
    "InfiniteRunStoppedDetails": 6_824,
    "InfiniteRefusalDetails": 6_795,
    "InfiniteSubagentLaunchedDetails": 25_201,
    "InfiniteSubagentReplayedDetails": 644,
    "InfiniteGeneratorFinishedDetails": 6_962,
    "InfiniteSubagentFinishedDetails": 27_015,
    "InfiniteMemorySavedDetails": 18_023,
    "InfiniteMemoryStagedDetails": 6_147,
    "InfiniteMemoryDroppedDetails": 1_658,
    "InfiniteFileWrittenDetails": 13_544,
}
# Each kind's details record (spec section 9.1); batch_rejected and tool_refused share one.
_RECORD_OF_KIND = {
    "run_started": "InfiniteRunStartedDetails",
    "run_resumed": "InfiniteRunResumedDetails",
    "run_finished": "InfiniteRunFinishedDetails",
    "run_stopped": "InfiniteRunStoppedDetails",
    "batch_rejected": "InfiniteRefusalDetails",
    "tool_refused": "InfiniteRefusalDetails",
    "subagent_launched": "InfiniteSubagentLaunchedDetails",
    "subagent_replayed": "InfiniteSubagentReplayedDetails",
    "generator_finished": "InfiniteGeneratorFinishedDetails",
    "subagent_finished": "InfiniteSubagentFinishedDetails",
    "memory_saved": "InfiniteMemorySavedDetails",
    "memory_staged": "InfiniteMemoryStagedDetails",
    "memory_dropped": "InfiniteMemoryDroppedDetails",
    "file_written": "InfiniteFileWrittenDetails",
}
# Spec section 9.1 text fields: (record, field, cap, line type, is a list). Line types: c collapsed, e exact one line,
# m multi-line, k key, p task name, s staged key, t tag. Item texts of committed and dropped are checked separately.
_FIELDS = (
    ("InfiniteRunStartedDetails", "task", TEXT_MAX, "m", False),
    ("InfiniteRunStartedDetails", "model", LINE_MAX, "c", False),
    ("InfiniteRunStartedDetails", "extras", LABEL_MAX, "c", True),
    ("InfiniteRunStartedDetails", "seeds", LABEL_MAX, "c", True),
    ("InfiniteRunResumedDetails", "task", TEXT_MAX, "m", False),
    ("InfiniteRunResumedDetails", "interrupted", KEY_MAX, "k", True),
    ("InfiniteRunFinishedDetails", "stop_reason", LABEL_MAX, "c", False),
    ("InfiniteRunFinishedDetails", "answer", TEXT_MAX, "m", False),
    ("InfiniteRunStoppedDetails", "error_type", LABEL_MAX, "c", False),
    ("InfiniteRunStoppedDetails", "message", TEXT_MAX, "m", False),
    ("InfiniteRefusalDetails", "tool", LABEL_MAX, "c", False),
    ("InfiniteRefusalDetails", "problem", TEXT_MAX, "m", False),
    ("InfiniteSubagentLaunchedDetails", "name", LABEL_MAX, "p", False),
    ("InfiniteSubagentLaunchedDetails", "key", KEY_MAX, "k", False),
    ("InfiniteSubagentLaunchedDetails", "parent", KEY_MAX, "k", False),
    ("InfiniteSubagentLaunchedDetails", "goal", TEXT_MAX, "m", False),
    ("InfiniteSubagentLaunchedDetails", "done_criteria", LINE_MAX, "m", True),
    ("InfiniteSubagentLaunchedDetails", "generator_prompt", LINE_MAX, "m", False),
    ("InfiniteSubagentLaunchedDetails", "verifier_prompt", LINE_MAX, "m", False),
    ("InfiniteSubagentLaunchedDetails", "context", LABEL_MAX, "e", True),
    ("InfiniteSubagentLaunchedDetails", "tools", LABEL_MAX, "c", True),
    ("InfiniteSubagentReplayedDetails", "name", LABEL_MAX, "p", False),
    ("InfiniteSubagentReplayedDetails", "key", KEY_MAX, "k", False),
    ("InfiniteGeneratorFinishedDetails", "stop_reason", LABEL_MAX, "c", False),
    ("InfiniteGeneratorFinishedDetails", "summary", TEXT_MAX, "m", False),
    ("InfiniteSubagentFinishedDetails", "name", LABEL_MAX, "p", False),
    ("InfiniteSubagentFinishedDetails", "key", KEY_MAX, "k", False),
    ("InfiniteSubagentFinishedDetails", "review", TEXT_MAX, "m", False),
    ("InfiniteSubagentFinishedDetails", "files", LINE_MAX, "e", True),
    ("InfiniteMemorySavedDetails", "text", TEXT_MAX, "e", False),
    ("InfiniteMemorySavedDetails", "tags", 40, "t", True),
    ("InfiniteMemorySavedDetails", "refs", LINE_MAX, "e", True),
    ("InfiniteMemoryStagedDetails", "key", LABEL_MAX, "s", False),
    ("InfiniteMemoryStagedDetails", "text", TEXT_MAX, "e", False),
    ("InfiniteMemoryDroppedDetails", "key", LABEL_MAX, "s", False),
    ("InfiniteMemoryDroppedDetails", "text", LABEL_MAX, "e", False),
    ("InfiniteMemoryDroppedDetails", "note", LABEL_MAX, "m", False),
    ("InfiniteFileWrittenDetails", "path", PATH_MAX, "e", False),
    ("InfiniteFileWrittenDetails", "excerpt", TEXT_MAX, "m", False),
    ("InfiniteFileWrittenDetails", "description", LINE_MAX, "e", False),
)
# Lists of item records, and the two entry lists that keep the entry rule's limit of 8 (INV-34).
_ITEM_LISTS = (("InfiniteSubagentFinishedDetails", "committed"), ("InfiniteSubagentFinishedDetails", "dropped"))
_EIGHT_ITEM_LISTS = {("InfiniteMemorySavedDetails", "tags"), ("InfiniteMemorySavedDetails", "refs")}
_COST_RECORDS = ("InfiniteRunFinishedDetails", "InfiniteGeneratorFinishedDetails", "InfiniteSubagentFinishedDetails")
_UTC_AT = datetime(2026, 10, 16, 8, 15, 0, 123_000, tzinfo=timezone.utc)
_TINY_COST = 1.2345678901234567e-300
_KEY = "k" * KEY_MAX
_STAGED_KEY = "s" + "9" * (LABEL_MAX - 1)
_NAME = "a" * LABEL_MAX
_DIGEST = re.compile(r"~[0-9a-f]{16}/")


# ---------------------------------------------------------------- builders


def _worst(record: str, fill: str) -> dict[str, Any]:
    """Spec section 9.1 Worst case: every capped text at its cap of `fill`, every list full, every count at the cap, the longest enum values."""
    from vidbyte.lib.dataclasses.infinite import InfiniteCommittedEntry, InfiniteDroppedEntry
    from vidbyte.lib.enums.infinite import (
        InfiniteDropReason,
        InfiniteEntryKind,
        InfiniteFileChange,
        InfiniteMemoryPreset,
        InfiniteResultStatus,
        InfiniteStopCause,
        InfiniteVerdict,
    )

    def text(cap: int) -> str:
        return fill * cap

    def items(cap: int, count: int = MAX_ITEMS) -> tuple[str, ...]:
        return (text(cap),) * count

    committed = InfiniteCommittedEntry(staged_key=_STAGED_KEY, entry_id=MAX_COUNT, kind=InfiniteEntryKind.OPEN_QUESTION, text=text(LABEL_MAX))
    dropped = InfiniteDroppedEntry(key=_STAGED_KEY, text=text(LABEL_MAX), reason=InfiniteDropReason.UNCHECKED, note=text(LABEL_MAX))
    shapes: dict[str, dict[str, Any]] = {
        "InfiniteRunStartedDetails": {
            "task": text(TEXT_MAX),
            "model": text(LINE_MAX),
            "preset": InfiniteMemoryPreset.SPARSE,
            "max_depth": MAX_COUNT,
            "max_parallel": MAX_COUNT,
            "max_agents": MAX_COUNT,
            "max_iterations": MAX_COUNT,
            "extras": items(LABEL_MAX),
            "extras_omitted": MAX_COUNT,
            "seeds": items(LABEL_MAX),
            "seeds_omitted": MAX_COUNT,
        },
        "InfiniteRunResumedDetails": {"task": text(TEXT_MAX), "finished": MAX_COUNT, "interrupted": (_KEY,) * MAX_ITEMS, "interrupted_omitted": MAX_COUNT},
        "InfiniteRunFinishedDetails": {"stop_reason": text(LABEL_MAX), "answer": text(TEXT_MAX), "pairs": MAX_COUNT, "agents": MAX_COUNT, "tokens": MAX_COUNT, "cost_usd": _TINY_COST},
        "InfiniteRunStoppedDetails": {"reason": InfiniteStopCause.CANCELLED, "error_type": text(LABEL_MAX), "message": text(TEXT_MAX)},
        "InfiniteRefusalDetails": {"tool": text(LABEL_MAX), "problem": text(TEXT_MAX)},
        "InfiniteSubagentLaunchedDetails": {
            "name": _NAME,
            "key": _KEY,
            "parent": _KEY,
            "depth": MAX_COUNT,
            "goal": text(TEXT_MAX),
            "done_criteria": items(LINE_MAX),
            "done_criteria_omitted": MAX_COUNT,
            "generator_prompt": text(LINE_MAX),
            "verifier_prompt": text(LINE_MAX),
            "context": items(LABEL_MAX),
            "context_omitted": MAX_COUNT,
            "tools": items(LABEL_MAX),
            "tools_omitted": MAX_COUNT,
        },
        "InfiniteSubagentReplayedDetails": {"name": _NAME, "key": _KEY, "status": InfiniteResultStatus.PARTIAL, "verdict": InfiniteVerdict.UNCHECKED},
        "InfiniteGeneratorFinishedDetails": {
            "status": InfiniteResultStatus.PARTIAL,
            "stop_reason": text(LABEL_MAX),
            "summary": text(TEXT_MAX),
            "tool_calls": MAX_COUNT,
            "tokens": MAX_COUNT,
            "cost_usd": _TINY_COST,
            "duration_ms": MAX_COUNT,
        },
        "InfiniteSubagentFinishedDetails": {
            "name": _NAME,
            "key": _KEY,
            "status": InfiniteResultStatus.PARTIAL,
            "verdict": InfiniteVerdict.UNCHECKED,
            "review": text(TEXT_MAX),
            "committed": (committed,) * MAX_ITEMS,
            "committed_omitted": MAX_COUNT,
            "dropped": (dropped,) * MAX_ITEMS,
            "dropped_omitted": MAX_COUNT,
            "files": items(LINE_MAX),
            "files_omitted": MAX_COUNT,
            "tokens": MAX_COUNT,
            "cost_usd": _TINY_COST,
        },
        "InfiniteMemorySavedDetails": {"id": MAX_COUNT, "kind": InfiniteEntryKind.OPEN_QUESTION, "text": text(TEXT_MAX), "tags": ("a" * 40,) * 8, "refs": items(LINE_MAX, 8), "supersedes": MAX_COUNT},
        "InfiniteMemoryStagedDetails": {"key": _STAGED_KEY, "kind": InfiniteEntryKind.OPEN_QUESTION, "text": text(TEXT_MAX), "supersedes": MAX_COUNT},
        "InfiniteMemoryDroppedDetails": {"key": _STAGED_KEY, "text": text(LABEL_MAX), "reason": InfiniteDropReason.UNCHECKED, "note": text(LABEL_MAX)},
        "InfiniteFileWrittenDetails": {"path": text(PATH_MAX), "change": InfiniteFileChange.APPENDED, "added_chars": MAX_COUNT, "excerpt": text(TEXT_MAX), "description": text(LINE_MAX)},
    }
    return shapes[record]


def _build(record: str, fields: dict[str, Any]) -> Any:
    from vidbyte.lib.dataclasses import infinite

    return getattr(infinite, record)(**fields)


def _baseline(record: str) -> dict[str, Any]:
    # A valid record with every text at its cap of plain ASCII, the shape the refusal checks start from.
    return _worst(record, "a")


def _refusal_field(record: str, fields: dict[str, Any]) -> str | None:
    """The field a ConfigurationError names when the record refuses `fields`, or None when it accepts them."""
    try:
        _build(record, fields)
    except ConfigurationError as exc:
        return str(exc.details.get("field"))
    return None


def _over(line_type: str, cap: int) -> str:
    # One character over the cap, in a form the field's pattern would otherwise accept.
    return {"k": "k" * (cap + 1), "p": "a" * (cap + 1), "s": "s" + "1" * cap, "t": "a" * (cap + 1)}.get(line_type, "a" * (cap + 1))


def _short_key(pair_key: str) -> str:
    """Spec INV-35 / D-25, restated: a pair key over 508 characters becomes ~ + 16 hex digits of its SHA-256 + / + its last 490 characters."""
    if len(pair_key) <= 508:
        return pair_key
    return "~" + hashlib.sha256(pair_key.encode("ascii")).hexdigest()[:16] + "/" + pair_key[-490:]


def _long_launcher_key(head: str) -> str:
    """A 600-character generator key nine levels deep whose first task name starts with `head`."""
    segments = [head + "x" * 63] + ["x" * 64] * 7 + ["y" * 39]
    key = "root" + "".join(f"/{name}/gen" for name in segments)
    assert len(key) == 600, len(key)
    return key


# ---------------------------------------------------------------- AC-24, AC-21: names and the settings field


def test_the_public_names_are_one_object_wherever_they_are_exported() -> None:
    """AC-24, NG-9: InfiniteEvent, InfiniteEventKind, and InfiniteHandoff are the same objects from vidbyte, vidbyte.agents, and vidbyte.agents.infinite; InfiniteHandoff also from vidbyte.context and vidbyte.context.handoff; the four new enums from vidbyte.lib.enums; the kind has exactly the 14 values; details records stay out of the root package."""
    import vidbyte
    import vidbyte.agents
    import vidbyte.agents.infinite
    import vidbyte.context
    import vidbyte.context.handoff
    import vidbyte.lib.enums
    from vidbyte.context.handoff.base import Handoff
    from vidbyte.context.handoff.infinite import InfiniteHandoff
    from vidbyte.lib.dataclasses.infinite import InfiniteEvent
    from vidbyte.lib.enums import infinite as enums

    for package in (vidbyte, vidbyte.agents, vidbyte.agents.infinite):
        assert (package.InfiniteEvent, package.InfiniteEventKind, package.InfiniteHandoff) == (InfiniteEvent, enums.InfiniteEventKind, InfiniteHandoff), package.__name__
    for package in (vidbyte, vidbyte.agents):
        assert {"InfiniteEvent", "InfiniteEventKind", "InfiniteHandoff"} <= set(package.__all__), package.__name__
    assert vidbyte.context.InfiniteHandoff is InfiniteHandoff and vidbyte.context.handoff.InfiniteHandoff is InfiniteHandoff
    for name in ("InfiniteEventKind", "InfiniteDropReason", "InfiniteFileChange", "InfiniteStopCause"):
        assert getattr(vidbyte.lib.enums, name) is getattr(enums, name) and name in vidbyte.lib.enums.__all__, name
    assert {kind.value for kind in enums.InfiniteEventKind} == set(_RECORD_OF_KIND)
    assert all(kind.value == kind.name.lower() for kind in enums.InfiniteEventKind)
    assert {reason.value for reason in enums.InfiniteDropReason} == {"verifier", "unchecked", "rule"}
    assert {change.value for change in enums.InfiniteFileChange} == {"created", "appended", "edited"}
    assert {cause.value for cause in enums.InfiniteStopCause} == {"failed", "cancelled"}
    assert issubclass(InfiniteHandoff, Handoff)
    assert not any(hasattr(vidbyte, record) for record in _FIGURES), "details records are exported only from vidbyte.lib.dataclasses.infinite (NG-9)"


async def _async_sink(event: object) -> None:
    return None


class _AsyncCallable:
    async def __call__(self, event: object) -> None:
        return None


class _PlainCallable:
    def __call__(self, event: object) -> None:
        return None


@pytest.mark.parametrize(
    "sink",
    [42, "x", _async_sink, _AsyncCallable(), functools.partial(_async_sink)],
    ids=["int", "str", "async-def", "async-call-object", "partial-of-async-def"],
)
def test_on_event_refuses_a_non_callable_or_asynchronous_sink(tmp_path: Path, sink: object) -> None:
    """AC-21, INV-36, D-27: a non-callable sink, an async function, an object with an async __call__, and a partial of an async function are refused when the settings are built, with the qualified field in the message and the details."""
    with pytest.raises(ConfigurationError) as refused:
        build_settings(tmp_path, on_event=sink)
    assert refused.value.details == {"field": "InfiniteMemoryAgentSettings.on_event"}
    assert "InfiniteMemoryAgentSettings.on_event" in str(refused.value)


def test_on_event_accepts_none_and_synchronous_callables_as_the_last_field(tmp_path: Path) -> None:
    """AC-21, INV-32: print, a bound list.append, and an object with a plain __call__ are accepted as given; on_event is the last settings field and defaults to None."""
    from vidbyte.agents.infinite import InfiniteMemoryAgentSettings

    for accepted in (print, [].append, _PlainCallable()):
        assert build_settings(tmp_path, on_event=accepted).on_event is accepted
    last = dataclasses.fields(InfiniteMemoryAgentSettings)[-1]
    assert (last.name, last.default) == ("on_event", None)
    assert build_settings(tmp_path).on_event is None


# ---------------------------------------------------------------- AC-30: size bound and caps


@pytest.mark.parametrize("record", sorted(_FIGURES))
def test_every_details_record_at_its_caps_fits_its_worst_case_figure(record: str) -> None:
    """AC-30, INV-33, NFR-4: built with every cap filled by U+1F600 and then by \\x01, each record serializes within its spec section 9.1 figure and 32,768 bytes under all four json.dumps settings, and so does an event wrapping it with a 280-character summary, a 512-character key, and the largest depth."""
    from vidbyte.lib.dataclasses.infinite import InfiniteEvent
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteEventKind

    kind = next(InfiniteEventKind(value) for value, name in _RECORD_OF_KIND.items() if name == record)
    for fill in ("\U0001f600", "\x01"):
        details = _build(record, _worst(record, fill))
        sizes = json_sizes(dataclasses.asdict(details))
        assert max(sizes) <= _FIGURES[record] <= MAX_DETAILS_BYTES, (record, repr(fill), sizes)
        event = InfiniteEvent(kind=kind, run_id=RUN_A, agent_key=_KEY, role=InfiniteAgentRole.GENERATOR, depth=MAX_COUNT, at=_UTC_AT, summary=fill * SUMMARY_MAX, details=details)
        assert max(json_sizes(dataclasses.asdict(event))) <= MAX_DETAILS_BYTES, (record, repr(fill))


def test_every_capped_field_refuses_one_character_more_and_every_list_a_sixth_item() -> None:
    """AC-30, INV-12, INV-34, INV-35: each text field one character over its section 9.1 cap, each list with one item more than it allows, and each committed or dropped item text over 64 is refused with a ConfigurationError naming the qualified field."""
    from vidbyte.lib.dataclasses.infinite import InfiniteCommittedEntry, InfiniteDroppedEntry

    problems: list[str] = []
    for record, field, cap, line_type, is_list in _FIELDS:
        fields = _baseline(record)
        too_long = _over(line_type, cap)
        fields[field] = (too_long, *fields[field][1:]) if is_list else too_long
        named = _refusal_field(record, fields)
        if named != f"{record}.{field}":
            problems.append(f"{record}.{field} one over {cap}: named {named!r}")
        if is_list:
            longer = _baseline(record)
            limit = 8 if (record, field) in _EIGHT_ITEM_LISTS else MAX_ITEMS
            longer[field] = tuple(longer[field]) + (longer[field][0],) * (limit + 1 - len(longer[field]))
            named = _refusal_field(record, longer)
            if named != f"{record}.{field}":
                problems.append(f"{record}.{field} with {limit + 1} items: named {named!r}")
    finished = "InfiniteSubagentFinishedDetails"
    for _, field in _ITEM_LISTS:
        longer = _baseline(finished)
        longer[field] = longer[field] + longer[field][:1]
        named = _refusal_field(finished, longer)
        if named != f"{finished}.{field}":
            problems.append(f"{finished}.{field} with 6 items: named {named!r}")
    base = _baseline(finished)
    for field, item in (
        ("committed", dataclasses.replace(base["committed"][0], text="a" * (LABEL_MAX + 1))),
        ("dropped", dataclasses.replace(base["dropped"][0], text="a" * (LABEL_MAX + 1))),
        ("dropped", dataclasses.replace(base["dropped"][0], note="a" * (LABEL_MAX + 1))),
    ):
        fields = _baseline(finished)
        fields[field] = (item, *fields[field][1:])
        named = _refusal_field(finished, fields)
        if named is None or not named.startswith(f"{finished}.{field}"):
            problems.append(f"{finished}.{field} item over 64: named {named!r}")
    assert isinstance(base["committed"][0], InfiniteCommittedEntry) and isinstance(base["dropped"][0], InfiniteDroppedEntry)
    assert not problems, "\n".join(problems)


def test_one_line_fields_refuse_a_line_break() -> None:
    """INV-12: every collapsed or exact one-line field, single or listed, refuses a value holding a line break, so a missed collapse in InfiniteEvents cannot reach a sink."""
    problems: list[str] = []
    for record, field, _cap, line_type, is_list in _FIELDS:
        if line_type not in ("c", "e"):
            continue
        fields = _baseline(record)
        fields[field] = ("first\nsecond", *fields[field][1:]) if is_list else "first\nsecond"
        named = _refusal_field(record, fields)
        if named != f"{record}.{field}":
            problems.append(f"{record}.{field} with a line break: named {named!r}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------- AC-37 a, b: the envelope and costs


def test_the_envelope_refuses_a_wrong_time_details_type_summary_key_or_depth() -> None:
    """AC-37 (b), INV-11, INV-13, INV-14: at in UTC at millisecond precision is accepted; an offset, a naive time, or a stray microsecond is refused as InfiniteEvent.at; details of another kind's type as InfiniteEvent.details; and a summary, key, run id, or depth outside its bound by its own qualified field."""
    from vidbyte.lib.dataclasses.infinite import InfiniteEvent
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteEventKind

    started = _build("InfiniteRunStartedDetails", _baseline("InfiniteRunStartedDetails"))
    valid: dict[str, Any] = {"kind": InfiniteEventKind.RUN_STARTED, "run_id": RUN_A, "agent_key": "root", "role": InfiniteAgentRole.ROOT, "depth": 0, "at": _UTC_AT, "summary": "Run started: compare prices", "details": started}
    assert InfiniteEvent(**valid).at == _UTC_AT
    cases = {
        "at +01:00": ("at", _UTC_AT.astimezone(timezone(timedelta(hours=1))), "InfiniteEvent.at"),
        "naive at": ("at", _UTC_AT.replace(tzinfo=None), "InfiniteEvent.at"),
        "at with microsecond 1": ("at", _UTC_AT.replace(microsecond=1), "InfiniteEvent.at"),
        "details of run_finished": ("details", _build("InfiniteRunFinishedDetails", _baseline("InfiniteRunFinishedDetails")), "InfiniteEvent.details"),
        "summary of 281": ("summary", "a" * (SUMMARY_MAX + 1), "InfiniteEvent.summary"),
        "blank summary": ("summary", "", "InfiniteEvent.summary"),
        "two-line summary": ("summary", "Run started:\ncompare", "InfiniteEvent.summary"),
        "agent_key of 513": ("agent_key", "k" * (KEY_MAX + 1), "InfiniteEvent.agent_key"),
        "malformed run_id": ("run_id", "../x", "InfiniteEvent.run_id"),
        "depth over the count cap": ("depth", MAX_COUNT + 1, "InfiniteEvent.depth"),
    }
    problems: list[str] = []
    for label, (field, value, expected) in cases.items():
        try:
            InfiniteEvent(**{**valid, field: value})
        except ConfigurationError as exc:
            if exc.details != {"field": expected}:
                problems.append(f"{label}: details {exc.details!r}")
        else:
            problems.append(f"{label}: accepted")
    assert not problems, "\n".join(problems)


def test_cost_may_be_zero_or_unknown_but_never_negative_or_infinite() -> None:
    """AC-37 (a), INV-13, D-18: the three records that carry cost_usd accept 0.0 and None and refuse a negative, NaN, or infinite cost by their qualified cost_usd field."""
    problems: list[str] = []
    for record in _COST_RECORDS:
        for cost in (0.0, None):
            fields = {**_baseline(record), "cost_usd": cost}
            if _refusal_field(record, fields) is not None:
                problems.append(f"{record} refused cost_usd={cost!r}")
            elif _build(record, fields).cost_usd != cost:
                problems.append(f"{record} changed cost_usd={cost!r}")
        for cost in (-0.01, math.nan, math.inf):
            named = _refusal_field(record, {**_baseline(record), "cost_usd": cost})
            if named != f"{record}.cost_usd":
                problems.append(f"{record} with cost_usd={cost!r}: named {named!r}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------- AC-32, AC-37 f, EC-36: InfiniteEvents directly


def test_keys_over_508_characters_are_shortened_by_digest_and_stay_distinct(tmp_path: Path) -> None:
    """AC-32, INV-35, D-25: with a real launch tool whose generator key is 600 characters, subagent_launched names the pair by ~ + 16 hex digits + / + its last 490 characters, its parent equals the launcher's agent_key, the generator's file_written has agent_key equal to details.key + "/gen", and two launchers that differ only in their first task name's first character get different shortened keys with the same tail."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool
    from vidbyte.agents.infinite.memory import InfiniteAgentMemory
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.dataclasses.infinite import InfiniteTaskCard
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteFileChange

    settings = build_settings(tmp_path, max_depth=10_000)
    workspace = InfiniteWorkspace(settings.workspace)
    journal = InfiniteRunJournal.start(workspace.root, TASK)
    seen: list[Any] = []
    events = InfiniteEvents(seen.append, journal.run_id)
    card = InfiniteTaskCard(name="a", goal="Find the list prices.", done_criteria=("Every price has a source URL",), generator_prompt="Research the vendor.", verifier_prompt="Check every price.")
    launchers = [_long_launcher_key(head) for head in ("a", "z")]
    for key in launchers:
        launch = InfiniteLaunchTool(settings, workspace, journal, key=key, depth=9, extras=(), events=events)
        events.subagent_launched(launch, card)
        memory = InfiniteAgentMemory(workspace, key=f"{key}/a/gen", role=InfiniteAgentRole.GENERATOR, run_id=journal.run_id, depth=10, events=events)
        events.file_written(memory, "notes/deep.md", InfiniteFileChange.CREATED, "Deep finding.\n", "Deep notes")
    assert kinds(seen) == ["subagent_launched", "file_written"] * 2
    launched = [event for event in seen if event.kind.value == "subagent_launched"]
    written = [event for event in seen if event.kind.value == "file_written"]
    for key, start, write in zip(launchers, launched, written, strict=True):
        assert start.agent_key == _short_key(key[: -len("/gen")]) + "/gen" and len(start.agent_key) == KEY_MAX
        assert (start.role, start.depth, start.details.depth) == (InfiniteAgentRole.GENERATOR, 9, 10)
        assert start.details.parent == start.agent_key
        assert start.details.key == _short_key(f"{key}/a") and len(start.details.key) == 508
        assert _DIGEST.match(start.details.key), start.details.key[:20]
        assert write.agent_key == start.details.key + "/gen" and (write.role, write.depth) == (InfiniteAgentRole.GENERATOR, 10)
        assert all(value.isascii() and len(value) <= KEY_MAX for value in (start.agent_key, start.details.key, start.details.parent, write.agent_key))
    first, second = launched
    assert first.details.key != second.details.key and first.agent_key != second.agent_key
    assert first.details.key[-490:] == second.details.key[-490:]
    assert_portable(seen)


@pytest.mark.parametrize(
    ("usage", "expected"),
    [("complete zero", (5, 0.0)), ("incomplete", (7, None)), ("missing", (0, None)), ("another type", (0, None))],
    ids=["cost-complete-zero", "cost-incomplete", "no-rollup", "rollup-of-another-type"],
)
def test_generator_usage_is_read_from_the_reply_rollup_and_unknown_cost_is_none(tmp_path: Path, caplog: pytest.LogCaptureFixture, usage: str, expected: tuple[int, float | None]) -> None:
    """AC-37 (f), D-18, EC-3: generator_finished takes tokens from the reply's UsageRollup and its cost only when cost_complete is true, so a complete 0.0 stays 0.0, an incomplete 1.5 becomes None, and a missing or foreign rollup counts 0 tokens and an unknown cost; the event is still delivered and nothing is logged."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.memory import InfiniteAgentMemory
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.agents.pricing.records import UsageRollup
    from vidbyte.lib.dataclasses.agents import AgentMessage
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteResultStatus

    rollups: dict[str, object] = {
        "complete zero": UsageRollup(total_tokens=5, cost_usd=0.0, cost_complete=True),
        "incomplete": UsageRollup(total_tokens=7, cost_usd=1.5, cost_complete=False),
        "another type": {"total_tokens": 9, "cost_usd": 1.0, "cost_complete": True},
    }
    metadata: dict[str, object] = {"stop_reason": "final_response", "tool_call_count": 2}
    if usage in rollups:
        metadata["usage_rollup"] = rollups[usage]
    caplog.set_level(logging.DEBUG, logger=EVENTS_LOGGER)
    workspace = InfiniteWorkspace(build_settings(tmp_path).workspace)
    seen: list[Any] = []
    events = InfiniteEvents(seen.append, RUN_A)
    memory = InfiniteAgentMemory(workspace, key="root/p/gen", role=InfiniteAgentRole.GENERATOR, run_id=RUN_A, depth=1, events=events)
    reply = AgentMessage(sender="analyst/root/p/gen", recipient="analyst/root", content="P-SUMMARY: done.", metadata=metadata)
    events.generator_finished(memory, reply, InfiniteResultStatus.DONE, "P-SUMMARY: done.")
    assert event_warnings(caplog) == []
    (event,) = seen
    assert (event.kind.value, event.agent_key, event.role, event.depth) == ("generator_finished", "root/p/gen", InfiniteAgentRole.GENERATOR, 1)
    assert (event.details.tokens, event.details.cost_usd) == expected
    assert (event.details.status, event.details.stop_reason, event.details.summary, event.details.tool_calls) == (InfiniteResultStatus.DONE, "final_response", "P-SUMMARY: done.", 2)
    assert event.summary == "p/gen: done: P-SUMMARY: done."
    assert_portable(seen)


def test_a_pairs_cost_is_known_only_when_every_reply_is_fully_priced_and_unknown_without_replies(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """D-18, EC-13, EC-14: subagent_finished adds tokens over every reply of a real pair but reports a cost only when every reply's rollup is complete: two complete replies (0.02 and 0.01) give 8 tokens and 0.03, a complete reply plus an incomplete one give 8 tokens and None, and a pair with no reply at all (its generator raised) gives 0 tokens and None, never 0 dollars."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool, InfinitePair
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.agents.pricing.records import UsageRollup
    from vidbyte.lib.dataclasses.agents import AgentMessage
    from vidbyte.lib.dataclasses.infinite import InfiniteResultCard, InfiniteTaskCard
    from vidbyte.lib.enums.infinite import InfiniteResultStatus, InfiniteVerdict

    settings = build_settings(tmp_path)
    workspace = InfiniteWorkspace(settings.workspace)
    journal = InfiniteRunJournal.start(workspace.root, TASK)
    seen: list[Any] = []
    caplog.set_level(logging.DEBUG, logger=EVENTS_LOGGER)
    events = InfiniteEvents(seen.append, journal.run_id)
    launch = InfiniteLaunchTool(settings, workspace, journal, key="root", depth=0, extras=(), events=events)
    card = InfiniteTaskCard(name="p", goal="Find the list prices.", done_criteria=("Every price has a source URL",), generator_prompt="Research the vendor.", verifier_prompt="Check every price.")
    finished = InfiniteResultCard(name="p", key="root/p", status=InfiniteResultStatus.FAILED, verdict=InfiniteVerdict.UNCHECKED, summary="", review="", entries=(), dropped=(), files=())
    generator_part = UsageRollup(total_tokens=5, cost_usd=0.02, cost_complete=True)
    cases = {
        "both priced": (generator_part, UsageRollup(total_tokens=3, cost_usd=0.01, cost_complete=True)),
        "verifier partly priced": (generator_part, UsageRollup(total_tokens=3, cost_usd=0.01, cost_complete=False)),
        "no replies": (),
    }
    for parts in cases.values():
        pair = InfinitePair(launch, card, "root/p")
        pair.replies.extend(AgentMessage(sender="analyst/root/p/gen", recipient="analyst/root", content="done", metadata={"usage_rollup": part}) for part in parts)
        events.subagent_finished(pair, finished)
    assert event_warnings(caplog) == []
    assert kinds(seen) == ["subagent_finished"] * len(cases)
    priced, partly, empty = ((event.details.tokens, event.details.cost_usd) for event in seen)
    assert priced == (8, pytest.approx(0.03))
    assert partly == (8, None)
    assert empty == (0, None)
    assert_portable(seen)


def test_a_limit_above_the_count_cap_is_reported_at_the_cap(tmp_path: Path) -> None:
    """EC-36, D-24: run_started reports max_agents=10**30 as 2**63 - 1, a loop without an iteration limit as None, seeds by file name only, and the extras it is given, with the root envelope."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.settings.loop import AgentLoopSettings
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteMemoryPreset

    seed = tmp_path / "brief.md"
    seed.write_text("Compare list prices only.\n", encoding="utf-8")
    settings = build_settings(tmp_path, workspace={"seed_files": (seed,)}, max_agents=10**30, loop=AgentLoopSettings())
    seen: list[Any] = []
    InfiniteEvents(seen.append, RUN_A).run_started(settings, TASK, ("web_fetch",))
    (event,) = seen
    assert (event.kind.value, event.run_id, event.agent_key, event.role, event.depth) == ("run_started", RUN_A, "root", InfiniteAgentRole.ROOT, 0)
    details = event.details
    assert (details.task, details.model, details.preset) == (TASK, MODEL, InfiniteMemoryPreset.SPARSE)
    assert (details.max_depth, details.max_parallel, details.max_agents, details.max_iterations) == (20, 20, MAX_COUNT, None)
    assert (details.extras, details.extras_omitted, details.seeds, details.seeds_omitted) == (("web_fetch",), 0, ("brief.md",), 0)
    assert event.summary == f"Run started: {TASK}"
    assert_portable(seen)
