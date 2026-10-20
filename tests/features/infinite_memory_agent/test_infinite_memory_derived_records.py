"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_derived_records.py

PURPOSE: Proves the derived-events vocabulary on its own, outside a scripted run: the 22 kinds and the three new enums in their exact order and export places, the parameter names of every public InfiniteEvents method and of the internal seams the spec names, the fields of the 8 new and 8 enriched details records, the count, enum, and special field rules of section 9.1, the 18 new constants and templates, InfiniteRunJournal.started, and InfiniteWorkspace.map_omitted.
ROLE IN CODEBASE: Vocabulary layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-derived-events/spec.md (AC-23, AC-24, AC-25; INV-7, INV-12; D-7, D-8, D-13, D-19; sections 8.5, 9.1, 9.2, 9.3). Exercises vidbyte/lib/enums/infinite.py, vidbyte/lib/dataclasses/infinite.py, vidbyte/lib/constants/infinite.py, vidbyte/agents/infinite/events.py, launch.py, runtime.py, journal.py, and workspace.py. The size bound and the text caps of the same records live in test_infinite_memory_events_records.py (_FIGURES and _FIELDS).
ARCHITECTURE NOTE: Every expected name, order, value, and rule is restated from the spec's sections 8.5, 9.1, 9.2, and 9.3, never read from the module under test, so a renamed method, a reordered member, a missing validator, or a changed template fails here even when every scripted run still passes. Records are built from small valid baselines (_valid) and changed one field at a time; a refusal must be a ConfigurationError naming the qualified field, as the records of PR #1159 already do.
FUNCTION INVENTORY: test_the_kinds_and_three_new_enums_hold_exactly_the_spec_values_in_order (AC-24, D-19); test_every_public_events_method_takes_the_spec_parameters_by_position (AC-23, INV-7); test_the_internal_seams_have_the_spec_names_and_shapes (section 8.5, D-2, D-8, D-10, D-13); test_the_new_and_enriched_records_have_the_spec_fields_in_order_with_no_defaults (AC-25, section 8.5, D-19); test_the_small_valid_shapes_are_accepted_including_every_blank_or_none_the_spec_allows (section 9.1); test_every_count_field_refuses_a_negative_a_bool_and_one_over_the_count_cap (AC-25, section 9.1); test_every_enum_field_refuses_a_value_outside_its_enum (AC-25, INV-12); test_the_section_9_1_rules_that_are_not_plain_counts (AC-25, section 9.1); test_the_new_constants_and_templates_equal_sections_9_2_and_9_3 (section 9.3); test_the_journal_lists_every_pair_start_in_order_with_repeats (D-7, D-8); test_map_omitted_reads_a_cut_maps_closing_line_and_never_raises (D-13, EC-28). _valid, _build, and _refused are builders.
COMMON MODIFICATION PATTERNS: A new details field adds its name to _NEW_FIELDS or _APPENDED_FIELDS, its small valid value to _valid, and, when it is a count, its name to _COUNTS; its cap and worst case go in test_infinite_memory_events_records.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level; before the feature exists that would make the whole pack a collection error. 2. Do not compute an expected name, value, or rule from the implementation; restate it from the spec. 3. Do not loosen a field rule to what the implementation accepts; a different rule is a spec change.
KNOWN EDGE CASES: RecordFieldValidator.require_enum refuses a member's value string, but the spec does not say whether an enum field may take one, so the enum check uses a string that is no member's value and a member of another enum, which every reading refuses. A refused list item may be named with an index suffix (require_text_items does that), so list-item refusals accept any field name that starts with the list's qualified name.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-derived-events/spec.md sections 6.2, 8.5, 9.1, 9.2, 9.3 and 13; docs/spec/infinite-memory-derived-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_derived_records.py -q
"""

from __future__ import annotations

import dataclasses
import inspect
import re
import typing
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.features.infinite_memory_agent.infinite_events_fixtures import MAX_COUNT
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    RUN_A,
    TASK,
    build_settings,
    card_record,
    pair_finished_record,
    pair_started_record,
    run_started_record,
    workspace_root,
    write_journal,
)
from vidbyte.lib.errors import ConfigurationError

# Spec section 8.5: the 14 kinds of PR #1159, then the eight appended after TOOL_REFUSED (D-19).
_KINDS = (
    "run_started",
    "run_resumed",
    "run_finished",
    "run_stopped",
    "batch_rejected",
    "subagent_launched",
    "subagent_replayed",
    "generator_finished",
    "subagent_finished",
    "memory_saved",
    "memory_staged",
    "memory_dropped",
    "file_written",
    "tool_refused",
    "memory_committed",
    "verifier_started",
    "verifier_finished",
    "subagent_aborted",
    "batch_finished",
    "handoff_written",
    "workspace_usage",
    "agent_progress",
)
# Spec section 8.5: InfiniteRefusalRule, InfiniteRefusalSource, and InfinitePairPhase, in member order.
_RULES = (
    "invalid_arguments",
    "max_entries_per_agent",
    "new_files_per_agent",
    "max_files",
    "max_tokens",
    "max_file_tokens",
    "max_entry_tokens",
    "entry_one_line",
    "duplicate_entry",
    "unknown_entry",
    "note_path",
    "note_description",
    "note_missing",
    "edit_match",
    "malformed_memory",
    "duplicate_task",
    "tool_not_granted",
    "max_agents",
    "max_depth",
    "max_parallel",
    "text_encoding",
    "disk",
    "other",
)
_SOURCES = ("tool", "middleware")
_PHASES = ("generator", "verifier", "commit")
# Spec section 8.5: each public InfiniteEvents method's parameters after self, all positional-or-keyword.
_PARAMETERS = {
    "run_started": ("settings", "task", "extras"),
    "run_resumed": ("journal",),
    "run_finished": ("journal", "result", "workspace"),
    "run_stopped": ("error",),
    "agent_progress": ("settings", "state"),
    "workspace_usage": ("workspace", "map_text"),
    "handoff_written": ("workspace", "target", "handoff"),
    "batch_rejected": ("launch", "refused"),
    "batch_finished": ("launch", "batch", "pairs", "replayed", "started"),
    "subagent_launched": ("launch", "card", "batch", "index", "size"),
    "subagent_replayed": ("launch", "card"),
    "generator_finished": ("memory", "reply", "status", "summary"),
    "verifier_started": ("memory", "staged", "files"),
    "verifier_finished": ("memory", "reply", "verdict"),
    "subagent_finished": ("pair", "card"),
    "subagent_aborted": ("pair", "error", "phase"),
    "memory_saved": ("memory", "entry"),
    "memory_staged": ("memory", "staged"),
    "memory_committed": ("memory", "staged", "entry"),
    "memory_dropped": ("memory", "dropped"),
    "file_written": ("memory", "path", "change", "text", "description"),
    "tool_refused": ("memory", "tool", "error"),
}
# Spec section 8.5: the eight new details records and their fields, in order.
_NEW_FIELDS = {
    "InfiniteMemoryCommittedDetails": ("id", "key", "kind", "text", "supersedes"),
    "InfiniteVerifierStartedDetails": ("staged", "files", "files_omitted"),
    "InfiniteVerifierFinishedDetails": ("verdict", "stop_reason", "tool_calls", "tokens", "cost_usd", "duration_ms"),
    "InfiniteSubagentAbortedDetails": ("name", "key", "reason", "error_type", "phase", "staged"),
    "InfiniteBatchFinishedDetails": ("batch", "passed", "fixed", "failed", "unchecked", "replayed", "duration_ms"),
    "InfiniteHandoffWrittenDetails": ("path", "sections", "cut", "cut_omitted"),
    "InfiniteWorkspaceUsageDetails": ("level", "files", "max_files", "tokens", "max_tokens", "map_omitted"),
    "InfiniteAgentProgressDetails": ("iteration", "max_iterations", "model_calls", "tool_calls", "tokens"),
}
# The kind each new record belongs to (spec section 9.1), in the section 8.5 kind order.
_KIND_OF_NEW = {
    "memory_committed": "InfiniteMemoryCommittedDetails",
    "verifier_started": "InfiniteVerifierStartedDetails",
    "verifier_finished": "InfiniteVerifierFinishedDetails",
    "subagent_aborted": "InfiniteSubagentAbortedDetails",
    "batch_finished": "InfiniteBatchFinishedDetails",
    "handoff_written": "InfiniteHandoffWrittenDetails",
    "workspace_usage": "InfiniteWorkspaceUsageDetails",
    "agent_progress": "InfiniteAgentProgressDetails",
}
_QUOTA = ("entries_left", "entries_max", "files_left", "files_max")
# PR #1159's fields of the eight enriched records, then the fields section 8.5 appends after them.
_KEPT_FIELDS = {
    "InfiniteRunFinishedDetails": ("stop_reason", "answer", "pairs", "agents", "tokens", "cost_usd"),
    "InfiniteRunStoppedDetails": ("reason", "error_type", "message"),
    "InfiniteRefusalDetails": ("tool", "problem"),
    "InfiniteSubagentLaunchedDetails": ("name", "key", "parent", "depth", "goal", "done_criteria", "done_criteria_omitted", "generator_prompt", "verifier_prompt", "context", "context_omitted", "tools", "tools_omitted"),
    "InfiniteSubagentFinishedDetails": ("name", "key", "status", "verdict", "review", "committed", "committed_omitted", "dropped", "dropped_omitted", "files", "files_omitted", "tokens", "cost_usd"),
    "InfiniteMemorySavedDetails": ("id", "kind", "text", "tags", "refs", "supersedes"),
    "InfiniteMemoryStagedDetails": ("key", "kind", "text", "supersedes"),
    "InfiniteFileWrittenDetails": ("path", "change", "added_chars", "excerpt", "description"),
}
_APPENDED_FIELDS = {
    "InfiniteRunFinishedDetails": ("iterations", "tool_calls", "duration_ms", "passed", "fixed", "failed", "unchecked", "committed", "files", "deepest", "events_failed"),
    "InfiniteRunStoppedDetails": ("events_failed",),
    "InfiniteRefusalDetails": ("rule", "source"),
    "InfiniteSubagentLaunchedDetails": ("attempt", "batch", "batch_index", "batch_size", "agents_started", "max_agents", "in_flight"),
    "InfiniteSubagentFinishedDetails": ("error_type", "agents_started", "max_agents", "in_flight"),
    "InfiniteMemorySavedDetails": _QUOTA,
    "InfiniteMemoryStagedDetails": _QUOTA,
    "InfiniteFileWrittenDetails": _QUOTA,
}
# Spec section 9.1: every field whose rule is "count" (0 .. 2**63 - 1), new or appended.
_COUNTS = {
    "InfiniteVerifierStartedDetails": ("staged", "files_omitted"),
    "InfiniteVerifierFinishedDetails": ("tool_calls", "tokens", "duration_ms"),
    "InfiniteSubagentAbortedDetails": ("staged",),
    "InfiniteBatchFinishedDetails": ("batch", "passed", "fixed", "failed", "unchecked", "replayed", "duration_ms"),
    "InfiniteHandoffWrittenDetails": ("cut_omitted",),
    "InfiniteWorkspaceUsageDetails": ("level", "files", "max_files", "tokens", "max_tokens", "map_omitted"),
    "InfiniteAgentProgressDetails": ("iteration", "max_iterations", "model_calls", "tool_calls", "tokens"),
    "InfiniteRunFinishedDetails": _APPENDED_FIELDS["InfiniteRunFinishedDetails"],
    "InfiniteRunStoppedDetails": ("events_failed",),
    "InfiniteSubagentLaunchedDetails": _APPENDED_FIELDS["InfiniteSubagentLaunchedDetails"],
    "InfiniteSubagentFinishedDetails": ("agents_started", "max_agents", "in_flight"),
    "InfiniteMemorySavedDetails": _QUOTA,
    "InfiniteMemoryStagedDetails": _QUOTA,
    "InfiniteFileWrittenDetails": _QUOTA,
}
# Spec section 9.1: each new enum-typed field and the enum it holds.
_ENUM_FIELDS = (
    ("InfiniteRefusalDetails", "rule", "InfiniteRefusalRule"),
    ("InfiniteRefusalDetails", "source", "InfiniteRefusalSource"),
    ("InfiniteSubagentAbortedDetails", "reason", "InfiniteStopCause"),
    ("InfiniteSubagentAbortedDetails", "phase", "InfinitePairPhase"),
    ("InfiniteVerifierFinishedDetails", "verdict", "InfiniteVerdict"),
    ("InfiniteMemoryCommittedDetails", "kind", "InfiniteEntryKind"),
)
# Spec section 9.3: the ten new configuration constants (the eight templates are in _TEMPLATES).
_CONSTANTS = {
    "INFINITE_EVENT_PROGRESS_ITERATIONS": 10,
    "INFINITE_EVENT_USAGE_PERCENTS": (50, 75, 90, 100),
    "INFINITE_EVENT_PERCENT_SCALE": 100,
    "INFINITE_REFUSAL_RULE_DETAILS_KEY": "rule",
    "INFINITE_DENIAL_LIMIT_METADATA_KEY": "limit",
    "INFINITE_DENIAL_REASON_METADATA_KEY": "reason",
    "INFINITE_ITERATIONS_METADATA_KEY": "iteration_count",
    "INFINITE_CALL_RECORDS_METADATA_KEY": "tool_calls",
    "INFINITE_KEY_SEGMENTS_PER_DEPTH": 2,
    "INFINITE_HANDOFF_SECTION_COUNT": 9,
}
# Spec section 9.2: the eight summary templates.
_TEMPLATES = {
    "INFINITE_EVENT_AGENT_PROGRESS_SUMMARY": "{agent} is at iteration {iteration}: {model_calls} model calls, {tool_calls} tool calls",
    "INFINITE_EVENT_WORKSPACE_USAGE_SUMMARY": "Workspace is at the {level}% level: {files} of {max_files} files, {tokens} of {max_tokens} tokens",
    "INFINITE_EVENT_HANDOFF_WRITTEN_SUMMARY": "Handoff saved to {path}",
    "INFINITE_EVENT_BATCH_FINISHED_SUMMARY": "{agent}: batch {batch} finished: {passed} passed, {fixed} fixed, {failed} failed, {unchecked} unchecked, {replayed} replayed",
    "INFINITE_EVENT_VERIFIER_STARTED_SUMMARY": "{agent} is checking {staged} staged entries and {files} notes",
    "INFINITE_EVENT_VERIFIER_FINISHED_SUMMARY": "{agent}: verdict {verdict}",
    "INFINITE_EVENT_SUBAGENT_ABORTED_SUMMARY": "{name} aborted ({reason}) in its {phase} step: {error_type}",
    "INFINITE_EVENT_MEMORY_COMMITTED_SUMMARY": "{agent} committed {key} as memory #{id} ({kind}): {text}",
}
# The literal closing line INFINITE_MORE_FILES gives a cut map (spec section 13), restated for an independent parse.
_MORE_FILES = re.compile(r"… and (\d+) more files")


# ---------------------------------------------------------------- builders


def _valid(record: str) -> dict[str, Any]:
    """A small valid value for every field of `record`, with the new and appended fields of spec section 9.1."""
    from vidbyte.lib.enums import infinite as enums

    quota = {"entries_left": 24, "entries_max": 25, "files_left": 9, "files_max": 10}
    shapes: dict[str, Callable[[], dict[str, Any]]] = {
        "InfiniteMemoryCommittedDetails": lambda: {"id": 1, "key": "s1", "kind": enums.InfiniteEntryKind.FACT, "text": "Acme charges 49 USD per seat", "supersedes": None},
        "InfiniteVerifierStartedDetails": lambda: {"staged": 1, "files": ("notes/acme.md",), "files_omitted": 0},
        "InfiniteVerifierFinishedDetails": lambda: {"verdict": enums.InfiniteVerdict.PASSED, "stop_reason": "final_response", "tool_calls": 0, "tokens": 5, "cost_usd": None, "duration_ms": 2},
        "InfiniteSubagentAbortedDetails": lambda: {"name": "p", "key": "root/p", "reason": enums.InfiniteStopCause.FAILED, "error_type": "RuntimeError", "phase": enums.InfinitePairPhase.COMMIT, "staged": 1},
        "InfiniteBatchFinishedDetails": lambda: {"batch": 0, "passed": 1, "fixed": 0, "failed": 0, "unchecked": 0, "replayed": 0, "duration_ms": 3},
        "InfiniteHandoffWrittenDetails": lambda: {"path": f".runs/{RUN_A}.handoff.md", "sections": (7, 9, 1, 1, 1, 1, 1, 1, 30), "cut": (), "cut_omitted": 0},
        "InfiniteWorkspaceUsageDetails": lambda: {"level": 50, "files": 5, "max_files": 10, "tokens": 40, "max_tokens": 1_000, "map_omitted": 0},
        "InfiniteAgentProgressDetails": lambda: {"iteration": 10, "max_iterations": 500, "model_calls": 10, "tool_calls": 10, "tokens": 100},
        "InfiniteRunFinishedDetails": lambda: {
            "stop_reason": "final_response",
            "answer": "done",
            "pairs": 1,
            "agents": 2,
            "tokens": 0,
            "cost_usd": None,
            **dict.fromkeys(_APPENDED_FIELDS["InfiniteRunFinishedDetails"], 0),
        },
        "InfiniteRunStoppedDetails": lambda: {"reason": enums.InfiniteStopCause.CANCELLED, "error_type": "CancelledError", "message": "", "events_failed": 0},
        "InfiniteRefusalDetails": lambda: {"tool": "remember", "problem": "kind must be one of decision, fact", "rule": enums.InfiniteRefusalRule.INVALID_ARGUMENTS, "source": enums.InfiniteRefusalSource.TOOL},
        "InfiniteSubagentLaunchedDetails": lambda: {
            "name": "p",
            "key": "root/p",
            "parent": "root",
            "depth": 1,
            "goal": "Find the list prices for p.",
            "done_criteria": ("Every price has a source URL",),
            "done_criteria_omitted": 0,
            "generator_prompt": "Research p.",
            "verifier_prompt": "Check p.",
            "context": (),
            "context_omitted": 0,
            "tools": (),
            "tools_omitted": 0,
            "attempt": 1,
            "batch": 0,
            "batch_index": 0,
            "batch_size": 1,
            "agents_started": 2,
            "max_agents": 1_000,
            "in_flight": 1,
        },
        "InfiniteSubagentFinishedDetails": lambda: {
            "name": "p",
            "key": "root/p",
            "status": enums.InfiniteResultStatus.DONE,
            "verdict": enums.InfiniteVerdict.PASSED,
            "review": "VERDICT: passed",
            "committed": (),
            "committed_omitted": 0,
            "dropped": (),
            "dropped_omitted": 0,
            "files": (),
            "files_omitted": 0,
            "tokens": 0,
            "cost_usd": None,
            "error_type": "",
            "agents_started": 2,
            "max_agents": 1_000,
            "in_flight": 0,
        },
        "InfiniteMemorySavedDetails": lambda: {"id": 1, "kind": enums.InfiniteEntryKind.FACT, "text": "Acme charges 49 USD per seat", "tags": (), "refs": (), "supersedes": None, **quota},
        "InfiniteMemoryStagedDetails": lambda: {"key": "s1", "kind": enums.InfiniteEntryKind.FACT, "text": "Acme charges 49 USD per seat", "supersedes": None, **quota},
        "InfiniteFileWrittenDetails": lambda: {"path": "notes/acme.md", "change": enums.InfiniteFileChange.CREATED, "added_chars": 10, "excerpt": "Acme notes", "description": "Acme pricing notes", **quota},
    }
    return shapes[record]()


def _build(record: str, fields: dict[str, Any]) -> Any:
    from vidbyte.lib.dataclasses import infinite

    return getattr(infinite, record)(**fields)


def _refused(record: str, field: str, value: Any) -> str | None:
    """The field a ConfigurationError names when `record` is built with `field` set to `value`, or None when it is accepted."""
    try:
        _build(record, {**_valid(record), field: value})
    except ConfigurationError as exc:
        return str(exc.details.get("field"))
    return None


# ---------------------------------------------------------------- AC-24, AC-23: names, order, signatures


def test_the_kinds_and_three_new_enums_hold_exactly_the_spec_values_in_order() -> None:
    """AC-24, D-19: InfiniteEventKind lists the 22 values of section 8.5 in order (the 14 of PR #1159 keep their positions); InfiniteRefusalRule, InfiniteRefusalSource, and InfinitePairPhase hold exactly their values in order, are str enums, and are exported from vidbyte.lib.enums only, never from the root vidbyte package."""
    import vidbyte
    import vidbyte.lib.enums
    from vidbyte.lib.enums import infinite as enums

    assert [kind.value for kind in enums.InfiniteEventKind] == list(_KINDS)
    assert all(kind.name == kind.value.upper() for kind in enums.InfiniteEventKind)
    for name, values in (("InfiniteRefusalRule", _RULES), ("InfiniteRefusalSource", _SOURCES), ("InfinitePairPhase", _PHASES)):
        enum = getattr(enums, name)
        assert [member.value for member in enum] == list(values), name
        assert all(member.name == member.value.upper() and isinstance(member, str) for member in enum), name
        assert getattr(vidbyte.lib.enums, name) is enum and name in vidbyte.lib.enums.__all__, name
        assert name in enums.__all__, name
        assert name not in vidbyte.__all__ and not hasattr(vidbyte, name), f"{name} must not be a root export (NG-12, section 12.4)"


def test_every_public_events_method_takes_the_spec_parameters_by_position() -> None:
    """AC-23, INV-7: InfiniteEvents' public functions are exactly the 22 kind values, and each takes exactly the section 8.5 parameters, in order, all positional-or-keyword with no default."""
    from vidbyte.agents.infinite.events import InfiniteEvents

    public = {name: function for name, function in inspect.getmembers(InfiniteEvents, inspect.isfunction) if not name.startswith("_")}
    assert sorted(public) == sorted(_KINDS) == sorted(_PARAMETERS)
    problems: list[str] = []
    for name, expected in _PARAMETERS.items():
        parameters = list(inspect.signature(public[name]).parameters.values())[1:]
        if tuple(parameter.name for parameter in parameters) != expected:
            problems.append(f"{name}{tuple(parameter.name for parameter in parameters)} != {expected}")
        problems.extend(f"{name}.{parameter.name} is {parameter.kind.name}" for parameter in parameters if parameter.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD)
        problems.extend(f"{name}.{parameter.name} has a default" for parameter in parameters if parameter.default is not inspect.Parameter.empty)
    assert not problems, "\n".join(problems)


def test_the_internal_seams_have_the_spec_names_and_shapes(tmp_path: Path) -> None:
    """Section 8.5, D-2, D-8, D-10, D-13: InfiniteEvents._rule(refused) and _quota(memory) and InfiniteLaunchTool.denials(calls) and InfiniteWorkspace.map_omitted(text) are static methods; InfiniteRunJournal.started is a property; InfinitePair._commit(memory) and _finish(memory, status, verdict, summary, review, files) and InfiniteMemoryRuntime._announce_denials(launch, calls) take those parameters; a new InfinitePair has error None."""
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool, InfinitePair
    from vidbyte.agents.infinite.runtime import InfiniteMemoryRuntime
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.dataclasses.infinite import InfiniteTaskCard

    def names(function: Callable[..., Any]) -> tuple[str, ...]:
        return tuple(inspect.signature(function).parameters)

    statics = {(InfiniteEvents, "_rule"): ("refused",), (InfiniteEvents, "_quota"): ("memory",), (InfiniteLaunchTool, "denials"): ("calls",), (InfiniteWorkspace, "map_omitted"): ("text",)}
    for (owner, name), expected in statics.items():
        assert isinstance(inspect.getattr_static(owner, name), staticmethod), f"{owner.__name__}.{name} must be a staticmethod"
        assert names(getattr(owner, name)) == expected, f"{owner.__name__}.{name}"
    assert isinstance(inspect.getattr_static(InfiniteRunJournal, "started"), property)
    assert names(InfinitePair._commit) == ("self", "memory")
    assert names(InfinitePair._finish) == ("self", "memory", "status", "verdict", "summary", "review", "files")
    assert names(InfiniteMemoryRuntime._announce_denials) == ("self", "launch", "calls")
    settings = build_settings(tmp_path)
    workspace = InfiniteWorkspace(settings.workspace)
    journal = InfiniteRunJournal.start(workspace.root, TASK)
    launch = InfiniteLaunchTool(settings, workspace, journal, key="root", depth=0, extras=(), events=InfiniteEvents(None, journal.run_id))
    card = InfiniteTaskCard(name="p", goal="Find the list prices.", done_criteria=("Every price has a source URL",), generator_prompt="Research the vendor.", verifier_prompt="Check every price.")
    assert InfinitePair(launch, card, "root/p").error is None


# ---------------------------------------------------------------- AC-25: fields and rules


def test_the_new_and_enriched_records_have_the_spec_fields_in_order_with_no_defaults() -> None:
    """AC-25, section 8.5, D-19: the 8 new records have exactly their section 8.5 fields in order; the 8 enriched records keep PR #1159's fields and append the new ones after them; all are frozen, slotted, and default-free; InfiniteEvent.DETAILS_TYPES maps each new kind to its record, in kind order, and InfiniteEventDetails names all 21 records."""
    from vidbyte.lib.dataclasses import infinite as records
    from vidbyte.lib.enums.infinite import InfiniteEventKind

    problems: list[str] = []
    expected = {**_NEW_FIELDS, **{name: _KEPT_FIELDS[name] + _APPENDED_FIELDS[name] for name in _KEPT_FIELDS}}
    for name, fields in expected.items():
        record = getattr(records, name)
        found = tuple(field.name for field in dataclasses.fields(record))
        if found != fields:
            problems.append(f"{name} fields {found} != {fields}")
        if not (record.__dataclass_params__.frozen and "__slots__" in record.__dict__):
            problems.append(f"{name} is not frozen and slotted")
        problems.extend(f"{name}.{field.name} has a default" for field in dataclasses.fields(record) if field.default is not dataclasses.MISSING or field.default_factory is not dataclasses.MISSING)
    assert not problems, "\n".join(problems)
    types = records.InfiniteEvent.DETAILS_TYPES
    assert [kind.value for kind in types] == list(_KINDS), "DETAILS_TYPES follows the section 8.5 kind order (D-19)"
    for kind, name in _KIND_OF_NEW.items():
        assert types[InfiniteEventKind(kind)] is getattr(records, name), kind
    union = set(typing.get_args(records.InfiniteEventDetails))
    assert {getattr(records, name) for name in expected} <= union and len(union) == 21


def test_the_small_valid_shapes_are_accepted_including_every_blank_or_none_the_spec_allows() -> None:
    """Section 9.1: each new and enriched record accepts its small valid shape, a committed text that is blank, a verifier stop reason that is blank, a subagent_finished error_type that is blank, max_iterations None, supersedes None, a cost of None, a level of exactly 100, and a sections list of exactly nine counts."""
    problems: list[str] = []
    for record in (*_NEW_FIELDS, *_KEPT_FIELDS):
        try:
            _build(record, _valid(record))
        except ConfigurationError as exc:
            problems.append(f"{record} refused its valid shape: {exc.details}")
    accepted = (
        ("InfiniteMemoryCommittedDetails", "text", ""),
        ("InfiniteMemoryCommittedDetails", "supersedes", 7),
        ("InfiniteVerifierFinishedDetails", "stop_reason", ""),
        ("InfiniteVerifierFinishedDetails", "cost_usd", 0.0),
        ("InfiniteSubagentFinishedDetails", "error_type", ""),
        ("InfiniteSubagentFinishedDetails", "error_type", "ToolExecutionError"),
        ("InfiniteAgentProgressDetails", "max_iterations", None),
        ("InfiniteWorkspaceUsageDetails", "level", 100),
        ("InfiniteHandoffWrittenDetails", "sections", (0,) * 9),
        ("InfiniteHandoffWrittenDetails", "cut", ("Outcome", "Files")),
    )
    for record, field, value in accepted:
        named = _refused(record, field, value)
        if named is not None:
            problems.append(f"{record}.{field}={value!r} was refused as {named!r}")
    assert not problems, "\n".join(problems)


def test_every_count_field_refuses_a_negative_a_bool_and_one_over_the_count_cap() -> None:
    """AC-25, section 9.1: every new or appended count field, including level, max_iterations, and the quota fields, refuses -1, True, and 2**63 with a ConfigurationError naming the qualified field."""
    problems: list[str] = []
    for record, fields in _COUNTS.items():
        for field in fields:
            for value in (-1, True, MAX_COUNT + 1):
                named = _refused(record, field, value)
                if named != f"{record}.{field}":
                    problems.append(f"{record}.{field}={value!r}: named {named!r}")
    assert not problems, "\n".join(problems)


def test_every_enum_field_refuses_a_value_outside_its_enum() -> None:
    """AC-25, INV-12: rule, source, reason, phase, verdict, and the committed kind each refuse a string that is no member's value and a member of another enum, naming the qualified field."""
    from vidbyte.lib.enums.infinite import InfiniteAgentRole

    problems: list[str] = []
    for record, field, enum_name in _ENUM_FIELDS:
        for value in (f"not-a-{enum_name.lower()}", InfiniteAgentRole.ROOT):
            named = _refused(record, field, value)
            if named != f"{record}.{field}":
                problems.append(f"{record}.{field}={value!r} ({enum_name}): named {named!r}")
    assert not problems, "\n".join(problems)


def test_the_section_9_1_rules_that_are_not_plain_counts() -> None:
    """AC-25, section 9.1: level above 100, a committed id or supersedes below 1, a committed key outside the staged-key pattern, an aborted name outside the task-name pattern, a blank aborted error_type, a multi-line committed text, a sections tuple of ten items or with an item that is not a count, and a files tuple of six items are each refused by their qualified field."""
    problems: list[str] = []
    exact = (
        ("InfiniteWorkspaceUsageDetails", "level", 101),
        ("InfiniteMemoryCommittedDetails", "id", 0),
        ("InfiniteMemoryCommittedDetails", "supersedes", 0),
        ("InfiniteMemoryCommittedDetails", "key", "x1"),
        ("InfiniteMemoryCommittedDetails", "key", "s0"),
        ("InfiniteMemoryCommittedDetails", "text", "Acme charges\n49 USD per seat"),
        ("InfiniteSubagentAbortedDetails", "name", "Not A Task"),
        ("InfiniteSubagentAbortedDetails", "error_type", ""),
        ("InfiniteSubagentAbortedDetails", "error_type", "Runtime\nError"),
        ("InfiniteSubagentAbortedDetails", "key", "root/p\nroot/q"),
        ("InfiniteHandoffWrittenDetails", "path", ""),
    )
    for record, field, value in exact:
        named = _refused(record, field, value)
        if named != f"{record}.{field}":
            problems.append(f"{record}.{field}={value!r}: named {named!r}")
    listed = (
        ("InfiniteHandoffWrittenDetails", "sections", (1,) * 10),
        ("InfiniteHandoffWrittenDetails", "sections", (1, 1, 1, 1, 1, 1, 1, 1, -1)),
        ("InfiniteHandoffWrittenDetails", "sections", (1, 1, 1, 1, 1, 1, 1, 1, True)),
        ("InfiniteHandoffWrittenDetails", "sections", (1, 1, 1, 1, 1, 1, 1, 1, MAX_COUNT + 1)),
        ("InfiniteHandoffWrittenDetails", "sections", ("1",) * 9),
        ("InfiniteHandoffWrittenDetails", "cut", ("Outcome",) * 6),
        ("InfiniteVerifierStartedDetails", "files", ("notes/a.md",) * 6),
    )
    for record, field, value in listed:
        named = _refused(record, field, value)
        if named is None or not named.startswith(f"{record}.{field}"):
            problems.append(f"{record}.{field}={value!r}: named {named!r}")
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------- section 9.3: constants


def test_the_new_constants_and_templates_equal_sections_9_2_and_9_3() -> None:
    """Section 9.2, section 9.3: the ten configuration constants and the eight summary templates exist in vidbyte.lib.constants.infinite with exactly the spec's values, each is listed in its __all__, and each template is one line."""
    from vidbyte.lib.constants import infinite as constants

    problems: list[str] = []
    for name, value in {**_CONSTANTS, **_TEMPLATES}.items():
        if getattr(constants, name, None) != value:
            problems.append(f"{name} = {getattr(constants, name, '<missing>')!r}, expected {value!r}")
        if name not in constants.__all__:
            problems.append(f"{name} is not in __all__")
    assert not problems, "\n".join(problems)
    assert all("\n" not in template for template in _TEMPLATES.values())


# ---------------------------------------------------------------- D-7, D-8, D-13: journal and workspace reads


def test_the_journal_lists_every_pair_start_in_order_with_repeats(tmp_path: Path) -> None:
    """D-7, D-8, section 8.5: InfiniteRunJournal.started returns every pair_started key of a reopened journal in record order with repeats kept (a pair started again after a resume counts twice), as a tuple, and grows when the journal records another start."""
    from vidbyte.agents.infinite.journal import InfiniteRunJournal

    root = workspace_root(tmp_path)
    root.mkdir(parents=True)
    write_journal(
        root,
        RUN_A,
        [
            run_started_record(RUN_A, TASK),
            pair_started_record("root/a"),
            pair_started_record("root/b"),
            pair_finished_record(card_record("b", summary="B-SUMMARY")),
            pair_started_record("root/a"),
        ],
    )
    journal = InfiniteRunJournal.find(root, RUN_A)
    assert journal.started == ("root/a", "root/b", "root/a")
    assert isinstance(journal.started, tuple)
    assert journal.agents_started == 2 * len(journal.started)
    journal.pair_started("root/a/gen/c")
    assert journal.started == ("root/a", "root/b", "root/a", "root/a/gen/c")


def test_map_omitted_reads_a_cut_maps_closing_line_and_never_raises(tmp_path: Path) -> None:
    """D-13, EC-28: map_omitted returns 0 for a whole map and, for a map cut by 300 long note names, the count its closing line "… and N more files" states; on any other last line, including near-misses of that line, it returns 0 and never raises."""
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace

    workspace = InfiniteWorkspace(build_settings(tmp_path).workspace)
    whole = workspace.map_text()
    assert not _MORE_FILES.fullmatch(whole.split("\n")[-1]) and InfiniteWorkspace.map_omitted(whole) == 0
    notes = workspace.root / "notes"
    notes.mkdir(parents=True)
    for index in range(300):
        (notes / f"n{index:03d}-competitor-pricing-page-snapshot-{'x' * 80}.md").write_text("x", encoding="utf-8")
    cut_map = workspace.map_text()
    closing = _MORE_FILES.fullmatch(cut_map.split("\n")[-1])
    assert closing is not None, "precondition: 300 long note names must cut the map"
    assert InfiniteWorkspace.map_omitted(cut_map) == int(closing.group(1)) > 0
    cases = {
        "": 0,
        "… and 12 more files": 12,
        "header\n… and 12 more files": 12,
        "… and 12 more files\n- notes/a.md (1 tokens): A": 0,
        "… and twelve more files": 0,
        "… and 12 more files!": 0,
        "and 12 more files": 0,
        "… and -3 more files": 0,
        "… and  more files": 0,
        "… and 1 2 more files": 0,
    }
    found = {text: InfiniteWorkspace.map_omitted(text) for text in cases}
    assert found == cases
