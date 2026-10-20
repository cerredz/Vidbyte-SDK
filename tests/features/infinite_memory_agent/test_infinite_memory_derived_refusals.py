"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_derived_refusals.py

PURPOSE: Proves that every refusal names its rule and its source: each memory-tool refusal and each launch the launch tool refuses gives one tool_refused or batch_rejected with source tool, the rule spec section 9.1 names for its raise site, and the problem text the model read; each launch_subagent call DelegationLimitsMiddleware denies gives exactly one batch_rejected with source middleware, its limit as the rule, and the middleware's reason as the problem, at the point spec INV-15 orders it; a permission denial gives none; and _rule classes an error by its details, then its type.
ROLE IN CODEBASE: Refusal layer of tests/features/infinite_memory_agent/ for docs/spec/infinite-memory-derived-events/spec.md (AC-6, AC-7, AC-8; INV-11, INV-12, INV-15; EC-1, EC-6, EC-8, EC-9, EC-19, EC-21, EC-22; FR-3, FR-15; D-4, D-5). Exercises vidbyte/agents/infinite/events.py (tool_refused, batch_rejected, _rule), memory.py, workspace.py, launch.py (InfiniteLaunchTool.denials), and runtime.py (the denial catch-up).
ARCHITECTURE NOTE: Only the model runner is scripted; the tools, the workspace, DelegationLimitsMiddleware, the permission policy, and the loop's call records are real. The problem each event must carry is read back out of the tool result the model received, through the catalog's memory_rejected_prompt or launch_rejected_prompt template (or the loop's "Tool denied by middleware: " prefix), so the oracle is the text the model saw at 181f1992 and not the code under test. The unit tests build real ToolCallContext and ToolResult records the way AgentRuntime._denied_tool_result does.
FUNCTION INVENTORY: test_each_tool_refusal_names_its_rule_and_source_and_keeps_the_problem_the_model_read (AC-6, INV-12, EC-21; one case per raise site); test_the_refusal_cases_cover_every_rule_a_tool_can_raise (AC-6 completeness); test_middleware_denials_name_their_limit_as_rule_and_the_reason_as_problem (AC-7, INV-11, INV-15, FR-15); test_a_denial_in_the_turn_the_run_finishes_is_announced_once_before_run_finished (AC-8, EC-6, FR-15, D-4); test_a_root_denial_beside_a_batch_in_one_iteration_follows_that_batch (EC-8, D-4); test_a_blank_generator_reply_still_announces_its_denied_launch_first (EC-19, D-4); test_a_generator_that_fails_after_a_denied_launch_announces_no_denial (EC-1, NG-11, D-22); test_only_launch_denials_that_name_a_limit_are_announced (EC-9, NG-10, InfiniteLaunchTool.denials); test_a_rule_comes_from_the_errors_details_then_its_type_then_the_denials_limit (INV-12, D-5, EC-21, EC-22); test_batch_rejected_takes_a_raised_error_or_a_denied_context (EC-22, D-5, section 9.1 source and problem). _Case, _scripts, _problem, _denial, and _context are small builders.
COMMON MODIFICATION PATTERNS: A new refusal raise site adds one _Case row with the rule section 9.1 gives it; a new rule value then fails test_the_refusal_cases_cover_every_rule_a_tool_can_raise until a row covers it.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not assert inside a sink. 3. Do not compare the problem with a message copied from the source; read it out of the result the model received. 4. Do not script the middleware or the permission policy; configure the real ones.
KNOWN EDGE CASES: On Windows, "notes/a:b.md" is refused as outside the workspace before the colon check runs; both are note_path, so the case holds on every platform. The disk case's problem is the OSError's text, which names an absolute path the OS built; it is the text the model read at 181f1992 (test-plan OPEN ITEM against INV-8). A surrogate in remember's text reaches the workspace as a lone surrogate and fails the UTF-8 write, so its rule is text_encoding by type.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-derived-events/spec.md sections 6.1, 6.2, 6.3, 8.5, 9.1 (refusal rule by raise site), and 13; docs/spec/infinite-memory-derived-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_derived_refusals.py -q
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_events_fixtures import (
    AC7_LIMITS,
    FACT,
    GEN_SUMMARY,
    PAIR,
    PASSED,
    SUMMARY_MAX,
    TEXT_MAX,
    ac7_tree,
    assert_portable,
    cut,
    kinds,
    line,
    of_kind,
    one,
)
from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    TASK,
    ScriptedTree,
    Step,
    build_agent,
    build_settings,
    entry_record,
    events,
    fail,
    generator,
    is_error,
    journal_records,
    launch,
    pair_key,
    prompt_text,
    reply,
    simple_pair,
    task,
    tool_call,
    tool_calls,
    tool_result,
    verifier,
    workspace_root,
    write_jsonl,
)

DENIED_PREFIX = "Tool denied by middleware: "
WORDS = " ".join(f"word{index}" for index in range(160))
# The rules no tool raises: the two delegation limits come from DelegationLimitsMiddleware's denials (AC-7), and other is the fallback for an error without a rule.
NOT_RAISED_BY_A_TOOL = {"max_depth", "max_parallel", "other"}


def _remember(text: str, kind: str = "fact", **extra: Any) -> Step:
    return tool_call("remember", {"kind": kind, "text": text, **extra})


def _note(path: Any, text: str = "Acme pricing page, read on 2026-10-15.\n", description: str | None = "Pricing notes") -> Step:
    arguments: dict[str, Any] = {"path": path, "text": text}
    if description is not None:
        arguments["description"] = description
    return tool_call("write_note", arguments)


def _edit(path: str, old_text: Any, new_text: str) -> Step:
    return tool_call("edit_file", {"path": path, "old_text": old_text, "new_text": new_text})


def _seed_live_fact(root: Path) -> None:
    write_jsonl(root / "entries.jsonl", [entry_record(1, FACT)])


def _seed_broken_entries(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "entries.jsonl").write_text(json.dumps(entry_record(1, FACT)) + "\n{this line is not an entry\n", encoding="utf-8", newline="\n")


def _seed_note(name: str, text: str) -> Callable[[Path], None]:
    def seed(root: Path) -> None:
        (root / "notes").mkdir(parents=True, exist_ok=True)
        (root / "notes" / name).write_text(text, encoding="utf-8", newline="\n")

    return seed


@dataclass(frozen=True)
class _Case:
    """One refused call: who makes it, after which accepted calls, under which settings, and the rule section 9.1 names for it."""

    id: str
    rule: str
    call: Step
    before: tuple[Step, ...] = ()
    workspace: Mapping[str, Any] = field(default_factory=dict)
    fields: Mapping[str, Any] = field(default_factory=dict)
    seed: Callable[[Path], None] | None = None
    agent: str = "root"


CASES = [
    # remember (memory.py and workspace._entry_rules / _entry_lines)
    _Case("remember-unknown-kind", "invalid_arguments", _remember("Acme is cheap", kind="opinion")),
    _Case("remember-bad-tag", "invalid_arguments", _remember("Acme is cheap", tags=["Bad Tag"])),
    _Case("remember-several-lines", "entry_one_line", _remember("Acme charges 49 USD\nper seat")),
    _Case("remember-past-quota", "max_entries_per_agent", _remember(FACT), before=(_remember("Compare monthly list prices only", kind="decision"),), workspace={"max_entries_per_agent": 1}),
    _Case("remember-supersedes-unknown", "unknown_entry", _remember(FACT, supersedes=99)),
    _Case("remember-already-recorded", "duplicate_entry", _remember(FACT), seed=_seed_live_fact),
    _Case("remember-over-entry-tokens", "max_entry_tokens", _remember(WORDS)),
    _Case("remember-malformed-entries", "malformed_memory", _remember(FACT), seed=_seed_broken_entries),
    _Case("remember-lone-surrogate", "text_encoding", _remember("Acme \ud800 charges 49 USD")),
    _Case("remember-already-staged", "duplicate_entry", _remember(FACT), before=(_remember(FACT),), agent="gen"),
    # write_note (memory.py and workspace.write_note / _note_path / _room)
    _Case("write-note-path-not-text", "invalid_arguments", _note(5)),
    _Case("write-note-path-line-break", "note_path", _note("notes/a\nb.md")),
    _Case("write-note-outside", "note_path", _note("../outside.md")),
    _Case("write-note-suffix", "note_path", _note("notes/run.py")),
    _Case("write-note-colon", "note_path", _note("notes/a:b.md")),
    _Case("write-note-protected", "note_path", _note("entries.jsonl")),
    _Case("write-note-no-description", "note_description", _note("notes/acme.md", description=None)),
    _Case("write-note-eleventh-file", "new_files_per_agent", _note("notes/n10.md"), before=tuple(_note(f"notes/n{index}.md") for index in range(10))),
    _Case("write-note-over-file-tokens", "max_file_tokens", _note("notes/acme.md", text=WORDS), workspace={"max_file_tokens": 50}),
    _Case("write-note-over-max-files", "max_files", _note("notes/b.md"), before=(_note("notes/a.md"),), workspace={"max_files": 4}),
    _Case("write-note-over-max-tokens", "max_tokens", _note("notes/b.md", text=" ".join(f"word{index}" for index in range(30))), workspace={"max_tokens": 100, "max_file_tokens": 100}, seed=_seed_note("old.md", " ".join(f"word{index}" for index in range(30)))),
    _Case("write-note-disk", "disk", _note("notes/a.md/b.md"), seed=_seed_note("a.md", "A.\n")),
    # edit_file (memory.py and workspace.edit_file), granted by the full preset
    _Case("edit-file-old-text-not-text", "invalid_arguments", _edit("notes/plan.md", 5, "x"), workspace={"preset": "full"}, seed=_seed_note("plan.md", "Plan v1: compare list prices.\n")),
    _Case("edit-file-missing", "note_missing", _edit("notes/none.md", "a", "b"), workspace={"preset": "full"}),
    _Case("edit-file-no-match", "edit_match", _edit("notes/plan.md", "NO-SUCH-PASSAGE", "b"), workspace={"preset": "full"}, seed=_seed_note("plan.md", "Plan v1: compare list prices.\n")),
    _Case("edit-file-over-file-tokens", "max_file_tokens", _edit("notes/plan.md", "Plan v1", WORDS), workspace={"preset": "full", "max_file_tokens": 50}, seed=_seed_note("plan.md", "Plan v1: compare list prices.\n")),
    # drop_entry (memory.drop), held by a verifier
    _Case("drop-entry-unknown-key", "unknown_entry", tool_call("drop_entry", {"id": "s9"}), agent="ver"),
    # launch_subagent (launch.InfiniteLaunchTool.execute / _check, and workspace.entries for context)
    _Case("launch-malformed-card", "invalid_arguments", tool_call("launch_subagent", {"tasks": [{"name": "m", "goal": "g"}]})),
    _Case("launch-repeated-name", "duplicate_task", launch(task("t"), task("t"))),
    _Case("launch-tool-not-granted", "tool_not_granted", launch(task("t", tools=["web_fetch"]))),
    _Case("launch-unknown-context", "unknown_entry", launch(task("t", context=["#99"]))),
    _Case("launch-over-max-agents", "max_agents", launch(task("t"), task("u")), fields={"max_agents": 2}),
]


def _scripts(case: _Case) -> tuple[dict[str, list[Step]], str, str]:
    """The scripted tree for a case, the BaseAgent name that makes the refused call, and its agent key."""
    steps = [*case.before, case.call]
    if case.agent == "root":
        return {ROOT: [*steps, reply("done")]}, ROOT, "root"
    pair = {ROOT: [launch(task(PAIR)), reply("done")]}
    if case.agent == "gen":
        return {**pair, generator(PAIR): [*steps, reply(GEN_SUMMARY)], verifier(PAIR): [reply(PASSED)]}, generator(PAIR), f"{pair_key(PAIR)}/gen"
    return {**pair, generator(PAIR): [reply(GEN_SUMMARY)], verifier(PAIR): [*steps, reply(PASSED)]}, verifier(PAIR), f"{pair_key(PAIR)}/ver"


def _problem(content: str, leaf: str) -> str:
    """The {problem} the catalog template `leaf` carried inside a tool result the model read."""
    head, tail = prompt_text(leaf).strip().split("{problem}")
    assert head in content, f"no {leaf} text in {content!r}"
    start = content.index(head) + len(head)
    return content[start : content.index(tail, start)]


def _denial(content: str) -> str:
    """The reason in a middleware-denied result the model read."""
    assert is_error(content) and DENIED_PREFIX in content, content
    return content.split(DENIED_PREFIX, 1)[1]


def _context(tool: str, state: Any, metadata: Mapping[str, Any] | None, output: str = "Tool denied by middleware: no.") -> Any:
    """A call record shaped like AgentRuntime._denied_tool_result's; `metadata` None leaves the result out."""
    from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolResult

    result = None if metadata is None else ToolResult.error(tool, output, metadata=dict(metadata))
    return ToolCallContext(tool_name=tool, arguments={"tasks": []}, state=state, call_id="call-1", result=result)


# ---------------------------------------------------------------- AC-6: refusals the tools raise


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_each_tool_refusal_names_its_rule_and_source_and_keeps_the_problem_the_model_read(tmp_path: Path, case: _Case) -> None:
    """AC-6, INV-12, EC-21, INV-5: each refused call gives exactly one tool_refused (memory tools) or batch_rejected (launch_subagent) from the agent that made it, with source tool, the rule section 9.1 names for its raise site, and the problem the model read inside memory_rejected_prompt or launch_rejected_prompt, cut to 500; its summary is the refusal template over that problem."""
    if case.seed is not None:
        case.seed(workspace_root(tmp_path))
    scripts, caller, agent_key = _scripts(case)
    seen: list[Any] = []
    agent = build_agent(tmp_path, workspace=case.workspace, on_event=seen.append, **case.fields)
    tree = ScriptedTree(scripts)
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    tool = case.call.name
    content = tool_result(tree.calls_by(caller)[len(case.before) + 1], tool)
    assert is_error(content), f"precondition: the call was refused: {content!r}"
    kind, leaf = ("batch_rejected", "launch_rejected_prompt") if tool == "launch_subagent" else ("tool_refused", "memory_rejected_prompt")
    problem = _problem(content, leaf)
    refusals = [event for event in seen if event.kind.value in ("tool_refused", "batch_rejected")]
    assert kinds(refusals) == [kind], kinds(seen)
    (refused,) = refusals
    assert refused.agent_key == agent_key
    assert (refused.details.tool, refused.details.problem) == (tool, cut(problem, TEXT_MAX))
    label = "/".join(agent_key.split("/")[-2:])
    assert refused.summary == line(f"{tool} refused for {label}: {problem}", SUMMARY_MAX)
    from vidbyte.lib.enums.infinite import InfiniteRefusalRule, InfiniteRefusalSource

    assert (refused.details.rule, refused.details.source) == (InfiniteRefusalRule(case.rule), InfiniteRefusalSource.TOOL)
    assert_portable(seen)


def test_the_refusal_cases_cover_every_rule_a_tool_can_raise() -> None:
    """AC-6, INV-12: the cases above name only InfiniteRefusalRule values and cover every one of them except the two delegation limits (AC-7) and the fallback other (the _rule unit test)."""
    from vidbyte.lib.enums.infinite import InfiniteRefusalRule

    values = {rule.value for rule in InfiniteRefusalRule}
    covered = {case.rule for case in CASES}
    assert covered <= values, covered - values
    assert covered == values - NOT_RAISED_BY_A_TOOL, values - NOT_RAISED_BY_A_TOOL - covered


# ---------------------------------------------------------------- AC-7, AC-8, EC-8, EC-19: middleware denials


def test_middleware_denials_name_their_limit_as_rule_and_the_reason_as_problem(tmp_path: Path) -> None:
    """AC-7, INV-11, INV-15, FR-15: under max_parallel=2 and max_depth=1, the root's 3-task call gives one batch_rejected (root, depth 0, max_parallel) delivered after the root's first iteration and before the next subagent_launched, and the generator's launch gives one (its key, depth 1, max_depth) before its generator_finished; both have source middleware and the reason the model read as problem, and neither gives a pair_started."""
    tree = ac7_tree()
    seen: list[Any] = []
    root_calls_at: list[int] = []

    def sink(event: Any) -> None:
        seen.append(event)
        root_calls_at.append(len(tree.calls_by(ROOT)))

    agent = build_agent(tmp_path, on_event=sink, **AC7_LIMITS)
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == ["run_started", "batch_rejected", "subagent_launched", "batch_rejected", "generator_finished", "verifier_started", "verifier_finished", "subagent_finished", "batch_finished", "run_finished"]
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteRefusalRule, InfiniteRefusalSource

    over_parallel = _denial(tool_result(tree.calls_by(ROOT)[1], "launch_subagent"))
    over_depth = _denial(tool_result(tree.calls_by(generator("a"))[1], "launch_subagent"))
    first, second = of_kind(seen, "batch_rejected")
    assert root_calls_at[kinds(seen).index("batch_rejected")] == 1, "the root's denial is announced after its first iteration, before its second model call"
    assert (first.agent_key, first.role, first.depth) == ("root", InfiniteAgentRole.ROOT, 0)
    assert (second.agent_key, second.role, second.depth) == (f"{pair_key('a')}/gen", InfiniteAgentRole.GENERATOR, 1)
    expected = [("launch_subagent", InfiniteRefusalRule.MAX_PARALLEL, InfiniteRefusalSource.MIDDLEWARE, cut(over_parallel, TEXT_MAX)), ("launch_subagent", InfiniteRefusalRule.MAX_DEPTH, InfiniteRefusalSource.MIDDLEWARE, cut(over_depth, TEXT_MAX))]
    assert [(event.details.tool, event.details.rule, event.details.source, event.details.problem) for event in (first, second)] == expected
    assert [event.summary for event in (first, second)] == [line(f"launch_subagent refused for root: {over_parallel}", SUMMARY_MAX), line(f"launch_subagent refused for a/gen: {over_depth}", SUMMARY_MAX)]
    assert events(journal_records(workspace_root(tmp_path))) == ["run_started", "pair_started", "pair_finished", "run_finished"]
    assert_portable(seen)


def test_a_denial_in_the_turn_the_run_finishes_is_announced_once_before_run_finished(tmp_path: Path) -> None:
    """AC-8, EC-6, FR-15, D-4: a root turn that both sends 3 tasks over max_parallel=2 and finishes with isDone skips _after_tool_iteration, so the catch-up after the loop announces that denial: exactly one batch_rejected (max_parallel, middleware) right before run_finished, and the answer is unchanged."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, max_parallel=2, on_event=seen.append)
    tree = ScriptedTree({ROOT: [tool_calls(launch(task("x"), task("y"), task("z")), tool_call("isDone", {"final_answer": "ROOT DONE"}))]})
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    assert answer.content == "ROOT DONE"
    denied = [context for context in answer.metadata["tool_calls"] if context.tool_name == "launch_subagent"]
    assert [context.state.value for context in denied] == ["denied"], "precondition: the middleware denied the batch"
    assert kinds(seen) == ["run_started", "batch_rejected", "run_finished"]
    from vidbyte.lib.enums.infinite import InfiniteRefusalRule, InfiniteRefusalSource

    details = one(seen, "batch_rejected").details
    assert (details.rule, details.source, details.problem) == (InfiniteRefusalRule.MAX_PARALLEL, InfiniteRefusalSource.MIDDLEWARE, cut(denied[0].result.metadata["reason"], TEXT_MAX))
    assert_portable(seen)


def test_a_root_denial_beside_a_batch_in_one_iteration_follows_that_batch(tmp_path: Path) -> None:
    """EC-8, D-4: one root turn with a repeated-name batch, a good batch, and a 3-task batch over max_parallel=2 gives the tool's batch_rejected inline, then the good batch's events through batch_finished, then the middleware's batch_rejected, then run_finished."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, max_parallel=2, on_event=seen.append)
    tree = ScriptedTree({ROOT: [tool_calls(launch(task("t"), task("t")), launch(task("a")), launch(task("x"), task("y"), task("z"))), reply("done")], **simple_pair("a", "A-SUMMARY")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == ["run_started", "batch_rejected", "subagent_launched", "generator_finished", "verifier_started", "verifier_finished", "subagent_finished", "batch_finished", "batch_rejected", "run_finished"]
    from vidbyte.lib.enums.infinite import InfiniteRefusalRule, InfiniteRefusalSource

    inline, late = of_kind(seen, "batch_rejected")
    assert (inline.details.rule, inline.details.source) == (InfiniteRefusalRule.DUPLICATE_TASK, InfiniteRefusalSource.TOOL)
    assert (late.details.rule, late.details.source, late.agent_key) == (InfiniteRefusalRule.MAX_PARALLEL, InfiniteRefusalSource.MIDDLEWARE, "root")
    assert_portable(seen)


def test_a_blank_generator_reply_still_announces_its_denied_launch_first(tmp_path: Path) -> None:
    """EC-19, D-4: a generator that calls launch_subagent past max_depth=1 and then replies blank still has a reply, so its middleware batch_rejected arrives before its generator_finished with status failed."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, max_depth=1, on_event=seen.append)
    tree = ScriptedTree({ROOT: [launch(task("a")), reply("done")], generator("a"): [launch(task("b")), reply("")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert kinds(seen) == ["run_started", "subagent_launched", "batch_rejected", "generator_finished", "subagent_finished", "batch_finished", "run_finished"]
    from vidbyte.lib.enums.infinite import InfiniteRefusalRule, InfiniteRefusalSource, InfiniteResultStatus

    rejected = one(seen, "batch_rejected")
    assert (rejected.agent_key, rejected.details.rule, rejected.details.source) == (f"{pair_key('a')}/gen", InfiniteRefusalRule.MAX_DEPTH, InfiniteRefusalSource.MIDDLEWARE)
    assert one(seen, "generator_finished").details.status is InfiniteResultStatus.FAILED
    assert_portable(seen)


def test_a_generator_that_fails_after_a_denied_launch_announces_no_denial(tmp_path: Path) -> None:
    """EC-1, D-4, NG-11, D-22: a generator whose launch_subagent past max_depth=1 is denied and whose runner then raises has no reply to read the denial from, so no batch_rejected arrives, its subagent_finished names the runner's RuntimeError, and the batch and run still finish."""
    seen: list[Any] = []
    agent = build_agent(tmp_path, max_depth=1, on_event=seen.append)
    tree = ScriptedTree({ROOT: [launch(task("a")), reply("done")], generator("a"): [launch(task("b")), fail(RuntimeError("runner bug"))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert is_error(tool_result(tree.calls_by(generator("a"))[1], "launch_subagent"))
    assert kinds(seen) == ["run_started", "subagent_launched", "subagent_finished", "batch_finished", "run_finished"]
    from vidbyte.lib.enums.infinite import InfiniteResultStatus

    finished = one(seen, "subagent_finished").details
    assert (finished.key, finished.status, finished.error_type) == (pair_key("a"), InfiniteResultStatus.FAILED, "RuntimeError")
    assert_portable(seen)


def test_only_launch_denials_that_name_a_limit_are_announced(tmp_path: Path) -> None:
    """EC-9, NG-10: a launch_subagent call the permission policy denies (no limit in its result) gives no event; InfiniteLaunchTool.denials keeps, in order, only the denied launch_subagent records whose result names a limit, skipping other states, other tools, a missing result, and anything that is not a call record."""
    from vidbyte import ToolCallState, ToolPermission
    from vidbyte.lib.dataclasses.security import PermissionPolicy

    seen: list[Any] = []
    agent = build_agent(tmp_path, permission_policy=PermissionPolicy(allowed=frozenset({ToolPermission.READ})), on_event=seen.append)
    tree = ScriptedTree({ROOT: [launch(task("a")), reply("done")]})
    with tree.install():
        answer = agent.run(TASK)
    tree.assert_complete()
    (denied,) = answer.metadata["tool_calls"]
    assert denied.state is ToolCallState.DENIED and "limit" not in denied.result.metadata, "precondition: a permission denial names no limit"
    assert kinds(seen) == ["run_started", "run_finished"]

    from vidbyte.agents.infinite.launch import InfiniteLaunchTool

    parallel = _context("launch_subagent", ToolCallState.DENIED, {"error": "middleware_denied", "reason": "over max_parallel", "limit": "max_parallel"})
    depth = _context("launch_subagent", ToolCallState.DENIED, {"error": "middleware_denied", "reason": "over max_depth", "limit": "max_depth"})
    unknown = _context("launch_subagent", ToolCallState.DENIED, {"error": "middleware_denied", "reason": "over budget", "limit": "budget"})
    skipped = [
        _context("launch_subagent", ToolCallState.DENIED, {"error": "permission_denied", "permission": "safe"}),
        _context("launch_subagent", ToolCallState.FAILED, {"limit": "max_parallel"}),
        _context("launch_subagent", ToolCallState.SUCCEEDED, {"limit": "max_parallel"}),
        _context("remember", ToolCallState.DENIED, {"error": "middleware_denied", "limit": "max_parallel"}),
        _context("launch_subagent", ToolCallState.DENIED, None),
        object(),
    ]
    calls = (skipped[0], parallel, skipped[1], skipped[2], depth, skipped[3], skipped[4], skipped[5], unknown)
    kept = InfiniteLaunchTool.denials(calls)
    assert isinstance(kept, tuple) and len(kept) == 3
    assert all(item is wanted for item, wanted in zip(kept, (parallel, depth, unknown), strict=True))
    assert InfiniteLaunchTool.denials(()) == ()


# ---------------------------------------------------------------- INV-12, D-5, EC-22: how a rule is found


def test_a_rule_comes_from_the_errors_details_then_its_type_then_the_denials_limit() -> None:
    """INV-12, D-5, EC-21, EC-22: _rule returns the rule an error names in its details, even over its type; else ConfigurationError is invalid_arguments, UnicodeError is text_encoding, OSError is disk, and anything else is other; for a denied call record it is the record's limit when that is a rule value, else other."""
    from vidbyte import ToolCallState
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.lib.enums.infinite import InfiniteRefusalRule as Rule
    from vidbyte.lib.errors import ConfigurationError, ToolExecutionError

    cases: list[tuple[object, Rule]] = [
        (ToolExecutionError("notes/run.py must end in one of .md.", details={"rule": Rule.NOTE_PATH}), Rule.NOTE_PATH),
        (ConfigurationError("Two tasks are named t.", details={"rule": Rule.DUPLICATE_TASK}), Rule.DUPLICATE_TASK),
        (ToolExecutionError("entries.jsonl line 2 is not a memory entry.", details={"file": "entries.jsonl", "line": 2, "rule": Rule.MALFORMED_MEMORY}), Rule.MALFORMED_MEMORY),
        (ConfigurationError("InfiniteEntryDraft.tags[0] must match a pattern."), Rule.INVALID_ARGUMENTS),
        (ConfigurationError("InfiniteEntryDraft.tags[0] must match a pattern.", details={"field": "InfiniteEntryDraft.tags[0]"}), Rule.INVALID_ARGUMENTS),
        (UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed"), Rule.TEXT_ENCODING),
        (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"), Rule.TEXT_ENCODING),
        (FileExistsError(17, "File exists"), Rule.DISK),
        (OSError("disk full"), Rule.DISK),
        (ToolExecutionError("A refusal with no rule."), Rule.OTHER),
        (ValueError("not a rule"), Rule.OTHER),
        (KeyError("defect"), Rule.OTHER),
        (_context("launch_subagent", ToolCallState.DENIED, {"limit": "max_parallel", "reason": "over"}), Rule.MAX_PARALLEL),
        (_context("launch_subagent", ToolCallState.DENIED, {"limit": "max_depth", "reason": "too deep"}), Rule.MAX_DEPTH),
        (_context("launch_subagent", ToolCallState.DENIED, {"limit": "budget", "reason": "over budget"}), Rule.OTHER),
    ]
    assert [InfiniteEvents._rule(refused) for refused, _ in cases] == [rule for _, rule in cases]


def test_batch_rejected_takes_a_raised_error_or_a_denied_context(tmp_path: Path) -> None:
    """EC-22, D-5, section 9.1: batch_rejected given a raised error carries source tool and its message; given a denied call record it carries source middleware and the record's reason, or its output when it has no reason; a limit that is not a rule value is rule other; the envelope is the launching agent, or the generator whose memory is passed."""
    from vidbyte import ToolCallState
    from vidbyte.agents.infinite.events import InfiniteEvents
    from vidbyte.agents.infinite.journal import InfiniteRunJournal
    from vidbyte.agents.infinite.launch import InfiniteLaunchTool
    from vidbyte.agents.infinite.memory import InfiniteAgentMemory
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.enums.infinite import InfiniteAgentRole, InfiniteRefusalRule, InfiniteRefusalSource
    from vidbyte.lib.errors import ConfigurationError

    settings = build_settings(tmp_path)
    workspace = InfiniteWorkspace(settings.workspace)
    journal = InfiniteRunJournal.start(workspace.root, TASK)
    seen: list[Any] = []
    writer = InfiniteEvents(seen.append, journal.run_id)
    launch_tool = InfiniteLaunchTool(settings, workspace, journal, key="root", depth=0, extras=(), events=writer)
    memory = InfiniteAgentMemory(workspace, key=f"{pair_key(PAIR)}/gen", role=InfiniteAgentRole.GENERATOR, run_id=journal.run_id, depth=1, events=writer)
    raised = ConfigurationError("Two tasks are named t; give every task in one call its own name.", details={"rule": InfiniteRefusalRule.DUPLICATE_TASK})
    budget = _context("launch_subagent", ToolCallState.DENIED, {"error": "middleware_denied", "reason": "This run is over its budget.", "limit": "budget"})
    bare = _context("launch_subagent", ToolCallState.DENIED, {"error": "middleware_denied", "limit": "max_depth"}, output="Tool denied by middleware: too deep.")
    writer.batch_rejected(launch_tool, raised)
    writer.batch_rejected(launch_tool, budget)
    writer.batch_rejected(memory, bare)
    assert kinds(seen) == ["batch_rejected"] * 3
    shapes = [(event.agent_key, event.role, event.depth, event.details.tool, event.details.rule, event.details.source, event.details.problem) for event in seen]
    assert shapes == [
        ("root", InfiniteAgentRole.ROOT, 0, "launch_subagent", InfiniteRefusalRule.DUPLICATE_TASK, InfiniteRefusalSource.TOOL, raised.message),
        ("root", InfiniteAgentRole.ROOT, 0, "launch_subagent", InfiniteRefusalRule.OTHER, InfiniteRefusalSource.MIDDLEWARE, "This run is over its budget."),
        (f"{pair_key(PAIR)}/gen", InfiniteAgentRole.GENERATOR, 1, "launch_subagent", InfiniteRefusalRule.MAX_DEPTH, InfiniteRefusalSource.MIDDLEWARE, "Tool denied by middleware: too deep."),
    ]
    assert seen[2].summary == "launch_subagent refused for p/gen: Tool denied by middleware: too deep."
    assert_portable(seen)

