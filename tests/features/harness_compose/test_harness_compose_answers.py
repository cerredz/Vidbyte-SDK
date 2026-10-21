"""FILE: tests/features/harness_compose/test_harness_compose_answers.py

PURPOSE: Structured answers (AC-9, AC-16, INV-19, NFR-8, EC-24 to EC-33, T-5): a cut answer is never decoded or graded, even when its cut prefix is valid JSON; each problem (cut, undecodable, extra member, wrong value, a parse error) gets a json_repair turn on the same thread naming the problem, at most COMPOSE_JSON_REPAIR_TURNS of them; a NativeThreadError on any turn ends the answer; a defect from parse propagates unchanged with no repair; JsonText.decode accepts one object with whitespace or one code fence around it and turns everything else, deep nesting included, into ValueError with a read-only result; every §9.1 record a model answer or a step result becomes refuses a value past its bound with ConfigurationError naming `<Record>.<field>`, and accepts the value at the bound.
ROLE IN CODEBASE: Start here when a verdict comes from a cut answer, a repair turn starts a new thread, or a bad answer crashes a composite.
ARCHITECTURE NOTE: Per-turn answers come from the stand-in's `answers` field, one entry per launch of one scenario. Lowering NATIVE_RESULT_TEXT_MAX_CHARS (read by the wire modules at call time) makes cut answers cheap. Expected problem texts are taken from JsonText itself or from the member names, never from compose's own wording.
FUNCTION INVENTORY: plain turns a decoded value into dicts and lists; cut_but_valid builds an answer whose first CUT_CHARS characters are a complete verdict object; ParseSpy records what parse received; Records builds one §9.1 record from valid values with some fields changed; BOUND_CASES pairs each value past a bound with the same record at the bound; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new answer problem is a new `answers` sequence and one assertion on the repair prompt.
WHAT NOT TO DO IN THIS FILE: Do not assert compose's own problem wording beyond the constants and member names; the spec leaves the prose to the implementer.
KNOWN EDGE CASES: Muse repair turns start `muse serve` before `muse exec`, so only the exec launches carry the stand-in label and the turn counter. A deeply nested answer must stay under the 100,000-character result cap, or it would be a cut answer instead of a recursion problem.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-19, §6.2 AC-9, AC-16, §6.3 EC-24 to EC-33, §7 NFR-8, §9.1, §10 T-5
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_answers.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

CUT_CHARS = 160
DEEP = '{"a": ' + "[" * 30_000 + "]" * 30_000 + "}"


def plain(value: object) -> object:
    # A decoded value as plain dicts and lists, for comparison.
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def cut_but_valid(pack) -> str:
    # A verdict object that ends before CUT_CHARS, then padding past the
    # cap: the cut text decodes to "approve", the whole text does not.
    head = pack.verdict_json("approve", summary="Cut answer that must never be graded.")
    assert len(head) < CUT_CHARS
    return head + " " * (CUT_CHARS - len(head)) + " and then the answer went on " * 10


class ParseSpy:
    """A caller's parse that records each mapping and can fail on demand."""

    def __init__(self, fail_with: list[BaseException | None] | None = None) -> None:
        self.received: list[dict[str, object]] = []
        self.read_only: list[bool] = []
        self.fail_with = list(fail_with or [])

    def __call__(self, mapping: Mapping[str, object]) -> tuple[str, dict[str, object]]:
        self.received.append(dict(mapping))
        try:
            mapping["injected"] = True  # type: ignore[index]
            self.read_only.append(False)
        except TypeError:
            self.read_only.append(True)
        failure = self.fail_with.pop(0) if self.fail_with else None
        if failure is not None:
            raise failure
        return ("parsed", dict(mapping))


class Records:
    """Builds one record of spec §9.1 from valid values, with the given fields changed."""

    def __init__(self, api) -> None:
        self.api = api
        self.cap = api.constants.COMPOSE_ANSWER_TEXT_MAX_CHARS
        self.diff_cap = api.constants.COMPOSE_DIFF_MAX_CHARS
        self.problem_cap = api.constants.COMPOSE_PROBLEM_MAX_CHARS

    def verdict(self, **changes):
        return self.api.records.ThreadVerdict(**{"decision": list(self.api.enums.VerdictDecision)[0], "summary": "Looks right.", "findings": (), **changes})

    def role(self, name: str = "R01", **changes):
        values = {"name": name, "identity": "i", "personality": "p", "expertise": "e", "knowledge": "k", "skills": "s", "goal": "g", **changes}
        return self.api.ensemble.EnsembleRole(**values)

    def roles(self, count: int) -> tuple:
        return tuple(self.role(f"R{index:02d}") for index in range(1, count + 1))

    def plan(self, roles):
        return self.api.ensemble.EnsemblePlan(task_analysis="a", roster_strategy="s", coverage_summary="c", roles=tuple(roles))

    def narrowing(self, kept):
        return self.api.ensemble.EnsembleRound(kept=tuple(kept), summary="Kept.")

    def selection(self, proposal: int):
        return self.api.ensemble.EnsembleSelection(proposal=proposal, approach="a", rationale="r", guidance="g")

    def paths(self, count: int) -> tuple[str, ...]:
        return tuple(f"file-{index:04d}.txt" for index in range(count))

    def diff(self, **changes):
        return self.api.records.WorkspaceDiff(**{"files": ("a.txt",), "text": "", "truncated": False, **changes})

    def result(self):
        return self.api.NativeThreadResult(harness=self.api.NativeHarness.GROK, thread_id=RECORD_THREAD_ID, text="answer", text_truncated=False)

    def error(self):
        enums = self.api.enums_package
        return self.api.NativeThreadError("grok failed", failure_code=enums.FailureCode.GROK_RUN_FAILED, harness=self.api.NativeHarness.GROK, operation=enums.NativeThreadOperation.RUN_GROK_THREAD, next_step="Retry.", likely_cause="A test failure.")

    def outcome(self, **fields):
        return self.api.records.StepOutcome(**fields)

    def answer(self, count: int, **changes):
        turns = tuple(self.outcome(result=self.result()) for _turn in range(count))
        return self.api.records.JsonAnswer(**{"value": None, "turns": turns, "problem": None, **changes})


RECORD_THREAD_ID = "0192f0c4-beef-7bee-8f00-000000000003"
OUTCOME_FIELDS = ("StepOutcome.result", "StepOutcome.error")
BOUND_CASES = {
    # case: (a value past the bound, the same record
    # at the bound, the field the refusal names)
    "verdict with 51 findings": (lambda r: r.verdict(findings=("f",) * 51), lambda r: r.verdict(findings=("f",) * 50), "ThreadVerdict.findings"),
    "verdict with a blank summary": (lambda r: r.verdict(summary="   "), lambda r: r.verdict(summary="s"), "ThreadVerdict.summary"),
    "verdict summary past the answer cap": (lambda r: r.verdict(summary="s" * (r.cap + 1)), lambda r: r.verdict(summary="s" * r.cap), "ThreadVerdict.summary"),
    "verdict with an unknown decision": (lambda r: r.verdict(decision="maybe"), lambda r: r.verdict(), "ThreadVerdict.decision"),
    "role name past 64 characters": (lambda r: r.role("n" * 65), lambda r: r.role("n" * 64), "EnsembleRole.name"),
    "role name with a NUL": (lambda r: r.role("ab\x00c"), lambda r: r.role("abc"), "EnsembleRole.name"),
    "role with a blank goal": (lambda r: r.role(goal=" "), lambda r: r.role(goal="g"), "EnsembleRole.goal"),
    "plan with 11 roles": (lambda r: r.plan(r.roles(11)), lambda r: r.plan(r.roles(10)), "EnsemblePlan.roles"),
    "plan with no roles": (lambda r: r.plan(()), lambda r: r.plan(r.roles(1)), "EnsemblePlan.roles"),
    "plan with a repeated role name": (lambda r: r.plan((r.role("R01"), r.role("R01"))), lambda r: r.plan((r.role("R01"), r.role("R02"))), "EnsemblePlan.roles"),
    "round keeping nothing": (lambda r: r.narrowing(()), lambda r: r.narrowing((1,)), "EnsembleRound.kept"),
    "round keeping a number twice": (lambda r: r.narrowing((3, 3)), lambda r: r.narrowing((3, 4)), "EnsembleRound.kept"),
    "round keeping zero": (lambda r: r.narrowing((0, 2)), lambda r: r.narrowing((1, 2)), "EnsembleRound.kept"),
    "round keeping 11 numbers": (lambda r: r.narrowing(range(1, 12)), lambda r: r.narrowing(range(1, 11)), "EnsembleRound.kept"),
    "selection of proposal 0": (lambda r: r.selection(0), lambda r: r.selection(1), "EnsembleSelection.proposal"),
    "selection of proposal 11": (lambda r: r.selection(11), lambda r: r.selection(10), "EnsembleSelection.proposal"),
    "diff with 2001 files": (lambda r: r.diff(files=r.paths(2001)), lambda r: r.diff(files=r.paths(2000)), "WorkspaceDiff.files"),
    "diff with a blank path": (lambda r: r.diff(files=("a.txt", " ")), lambda r: r.diff(files=("a.txt", "b.txt")), "WorkspaceDiff.files"),
    "diff text past its cap": (lambda r: r.diff(text="x" * (r.diff_cap + 1)), lambda r: r.diff(text="x" * r.diff_cap), "WorkspaceDiff.text"),
    "diff truncated flag that is not a bool": (lambda r: r.diff(truncated="yes"), lambda r: r.diff(truncated=True), "WorkspaceDiff.truncated"),
    "answer with no turns": (lambda r: r.answer(0), lambda r: r.answer(1), "JsonAnswer.turns"),
    "answer with four turns": (lambda r: r.answer(4), lambda r: r.answer(3), "JsonAnswer.turns"),
    "answer problem past its cap": (lambda r: r.answer(1, problem="p" * (r.problem_cap + 1)), lambda r: r.answer(1, problem="p" * r.problem_cap), "JsonAnswer.problem"),
    "outcome with neither result nor error": (lambda r: r.outcome(), lambda r: r.outcome(result=r.result()), OUTCOME_FIELDS),
    "outcome with both result and error": (lambda r: r.outcome(result=r.result(), error=r.error()), lambda r: r.outcome(error=r.error()), OUTCOME_FIELDS),
}


@pytest.mark.asyncio
async def test_cut_verdicts_are_repaired_on_the_same_thread_and_never_graded(compose_api, sandbox, steps, runs, pack, monkeypatch) -> None:
    # AC-9 / EC-29 / EC-30: opencode's first answer is cut yet its
    # prefix is a valid approve; the repair on the same thread and
    # worktree gives reject. Grok's every answer is cut: three turns,
    # no value, the problem names the cut, and the record still returns.
    api = compose_api
    monkeypatch.setattr(api.threads_constants, "NATIVE_RESULT_TEXT_MAX_CHARS", CUT_CHARS)
    sandbox.make_repo()
    writer = steps.bind("grok", edits=True, label="writer", fake={"text": "Done.", "write_files": {"feature.txt": "feature\n"}})
    opencode = steps.bind("opencode", label="cut-once", fake={"answers": [{"final_parts": [cut_but_valid(pack)]}, {"final_parts": [pack.verdict_json("reject", summary="Short.")]}]})
    grok = steps.bind("grok", plan=True, label="cut-always", fake={"mode": "long_text", "text_chars": CUT_CHARS * 3})
    result = await api.compose.verify_with(writer, [opencode, grok], prompt=pack.PROMPT)
    truncated = pack.longest_literal(api.constants.COMPOSE_TRUNCATED_PROBLEM)
    assert truncated, "COMPOSE_TRUNCATED_PROBLEM holds fixed text to look for"

    first, repair = sandbox.launches(label="cut-once")
    assert repair["start"]["options"]["--session"] == pack.launch_session(first) and "--fork" not in repair["start"]["switches"]
    assert pack.same_path(pack.launch_workspace(repair), pack.launch_workspace(first)) and pack.inside(pack.launch_workspace(first), sandbox.tmp)
    repair_prompt = pack.launch_prompt(repair)
    assert all(chunk in repair_prompt for chunk in truncated), "the json_repair prompt names the truncation"
    assert all(chunk in repair_prompt for chunk in pack.literal_chunks("verdict_schema"))
    verdict = result.verdicts[0]
    assert verdict.value.decision.value == "reject" and len(verdict.turns) == 2
    assert verdict.turns[0].result.text_truncated is True

    grok_launches = sandbox.launches(label="cut-always")
    assert len(grok_launches) == 1 + api.constants.COMPOSE_JSON_REPAIR_TURNS == 3
    session = pack.launch_session(grok_launches[0])
    assert all(launch["start"]["options"].get("--resume") == session and launch["start"]["switches"] == [] for launch in grok_launches[1:])
    assert all(pack.same_path(launch["start"]["cwd"], sandbox.workspace) for launch in grok_launches)
    always = result.verdicts[1]
    assert always.value is None and len(always.turns) == 3 and all(chunk in (always.problem or "") for chunk in truncated)
    assert result.failed_verifiers == (1,) and result.agreement is False
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_each_problem_gets_a_repair_naming_it_and_an_error_ends_the_answer(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-16 / EC-24 / EC-25 / EC-27 / EC-28 / EC-31 / EC-32: prose, then
    # an extra member, then a valid verdict (three turns, each repair
    # naming its problem); three bad answers (no value, a problem);
    # an error on the first repair (two turns, no third).
    api = compose_api
    sandbox.make_repo()
    writer = steps.bind("grok", edits=True, label="writer", fake={"text": "Done.", "write_files": {"feature.txt": "feature\n"}})
    extra = json.dumps({"decision": "approve", "summary": "Fine.", "findings": [], "confidence": 0.9})
    v_err = steps.bind("opencode", label="v-err", fake={"answers": [{"final_parts": ["I think it looks fine."]}, {"mode": "fail", "vendor_text": "the repair turn was refused"}]})
    v_fix = steps.bind("grok", plan=True, label="v-fix", fake={"answers": [{"text": "Looks good to me."}, {"text": extra}, {"text": pack.verdict_json("approve")}]})
    v_bad = steps.bind("muse", label="v-bad", fake={"answers": [{"text": ""}, {"text": "[1, 2]"}, {"text": json.dumps({"decision": "maybe", "summary": "Unsure.", "findings": []})}]})
    result = await api.compose.verify_with(writer, [v_err, v_fix, v_bad], prompt=pack.PROMPT)

    erred = result.verdicts[0]
    assert len(sandbox.launches(label="v-err")) == 2 and len(erred.turns) == 2
    assert erred.value is None and erred.turns[-1].error.failure_code.value == "opencode.run_failed"

    fixed = result.verdicts[1]
    launches = sandbox.launches(label="v-fix")
    assert len(launches) == 3 and len(fixed.turns) == 3 and fixed.value.decision.value == "approve"
    session = pack.launch_session(launches[0])
    assert [launch["start"]["options"].get("--resume") for launch in launches[1:]] == [session, session]
    with pytest.raises(ValueError) as decode_problem:
        api.JsonText.decode("Looks good to me.")
    assert str(decode_problem.value) in pack.launch_prompt(launches[1]), "the first repair names the decode problem"
    assert "confidence" in pack.launch_prompt(launches[2]), "the second repair names the extra member"

    bad = result.verdicts[2]
    exec_launches = sandbox.launches(label="v-bad")
    assert len(exec_launches) == 3 and len(bad.turns) == 3
    first_session = pack.launch_session(exec_launches[0])
    assert [launch["start"]["options"].get("--session-id") for launch in exec_launches[1:]] == [first_session, first_session]
    assert bad.value is None and "decision" in (bad.problem or "").lower()
    assert len(bad.problem) <= api.constants.COMPOSE_PROBLEM_MAX_CHARS

    assert result.failed_verifiers == (0, 2) and result.agreement is False
    assert sandbox.leftovers() == [] and sandbox.worktrees() == 1


@pytest.mark.asyncio
async def test_parse_json_answer_never_passes_a_cut_answer_to_parse(compose_api, sandbox, steps, runs, pack, monkeypatch) -> None:
    # INV-19 / EC-26 / EC-29: the cut first answer is
    # skipped unread; the fenced second answer is decoded;
    # parse sees a read-only mapping once; no git runs.
    api = compose_api
    monkeypatch.setattr(api.threads_constants, "NATIVE_RESULT_TEXT_MAX_CHARS", CUT_CHARS)
    fenced = "```json\n" + json.dumps({"answer": 42}) + "\n```"
    step = steps.bind("grok", label="json", fake={"answers": [{"text": cut_but_valid(pack)}, {"text": fenced}]})
    parse = ParseSpy()
    answer = await api.compose.parse_json_answer(step, "Give me the answer.", schema="SCHEMA-TEXT-31b7", parse=parse)
    assert parse.received == [{"answer": 42}] and parse.read_only == [True]
    assert answer.value == ("parsed", {"answer": 42}) and answer.ok and len(answer.turns) == 2
    assert answer.text == fenced and answer.thread_id == answer.turns[-1].thread_id
    first, repair = sandbox.launches(label="json")
    first_prompt = pack.launch_prompt(first)
    assert "Give me the answer." in first_prompt and "SCHEMA-TEXT-31b7" in first_prompt
    assert all(chunk in first_prompt for chunk in pack.literal_chunks("json_answer"))
    assert "SCHEMA-TEXT-31b7" in pack.launch_prompt(repair) and all(chunk in pack.launch_prompt(repair) for chunk in pack.literal_chunks("json_repair"))
    assert repair["start"]["options"]["--resume"] == pack.launch_session(first)
    assert runs.git_calls() == []


@pytest.mark.asyncio
async def test_parse_json_answer_repairs_deep_nesting_and_parse_errors_but_not_a_defect(compose_api, sandbox, steps, runs, pack) -> None:
    # INV-19 / EC-33 / T-5: deep nesting is a problem, not a crash; a
    # KeyError or ConfigurationError from parse is a problem; any other
    # exception from parse is the caller's defect and propagates as the
    # same object with no repair turn.
    api = compose_api
    deep = steps.bind("grok", label="deep", fake={"answers": [{"text": DEEP}, {"text": json.dumps({"b": 2})}]})
    parse = ParseSpy()
    answer = await api.compose.parse_json_answer(deep, "Nest.", schema="{}", parse=parse)
    assert parse.received == [{"b": 2}] and len(answer.turns) == 2 and answer.value == ("parsed", {"b": 2})

    errors = steps.bind("grok", label="errors", fake={"answers": [{"text": json.dumps({"a": 1})}, {"text": json.dumps({"a": 2})}, {"text": json.dumps({"a": 3})}]})
    failing = ParseSpy([KeyError("b"), api.ConfigurationError("a must be 3", details={"field": "a"})])
    answer = await api.compose.parse_json_answer(errors, "Again.", schema="{}", parse=failing)
    assert [item["a"] for item in failing.received] == [1, 2, 3] and answer.value == ("parsed", {"a": 3})
    launches = sandbox.launches(label="errors")
    assert "a must be 3" in pack.launch_prompt(launches[2])

    boom = RuntimeError("the caller's parse has a bug")
    defect = steps.bind("grok", label="defect", fake={"text": json.dumps({"a": 1})})
    with pytest.raises(RuntimeError) as caught:
        await api.compose.parse_json_answer(defect, "Crash.", schema="{}", parse=ParseSpy([boom]))
    assert caught.value is boom
    assert len(sandbox.launches(label="defect")) == 1, "a defect gets no repair turn"


@pytest.mark.parametrize(("text", "expected"), [
    pytest.param('  {"a": 1}\n', {"a": 1}, id="whitespace"),
    pytest.param('```json\n{"a": 1}\n```', {"a": 1}, id="json-fence"),
    pytest.param('```\n{"a": 1}\n```', {"a": 1}, id="bare-fence"),
    pytest.param('\n```json\n{"a": {"b": [1, 2]}}\n```\n', {"a": {"b": [1, 2]}}, id="fence-and-whitespace"),
])
def test_json_text_accepts_one_object_with_whitespace_or_one_fence(compose_api, text, expected) -> None:
    # INV-19 / EC-26: whitespace and one surrounding fence are removed;
    # the mapping is read-only.
    decoded = compose_api.JsonText.decode(text)
    assert isinstance(decoded, Mapping) and plain(decoded) == expected
    with pytest.raises(TypeError):
        decoded["x"] = 1  # type: ignore[index]


@pytest.mark.parametrize("text", [
    pytest.param("", id="empty"), pytest.param("   ", id="blank"), pytest.param("[1, 2]", id="array"), pytest.param('"just a string"', id="string"),
    pytest.param("42", id="number"), pytest.param("null", id="null"), pytest.param("true", id="boolean"), pytest.param("Looks fine.", id="prose"),
    pytest.param('Here it is: {"a": 1}', id="prose-before"), pytest.param('{"a": 1} trailing words', id="prose-after"),
    pytest.param('{"a": 1}{"b": 2}', id="two-objects"), pytest.param('{"a": 1}\n{"b": 2}', id="two-lines"), pytest.param("{not json}", id="not-json"),
    pytest.param('```json\n{"a": 1}\n``` and more', id="prose-after-fence"), pytest.param('```\n```json\n{"a": 1}\n```\n```', id="two-fences"),
    pytest.param('{"a": ' + "[" * 100_000 + "]" * 100_000 + "}", id="nested-100000-deep"),
])
def test_json_text_refuses_everything_else_with_value_error(compose_api, text) -> None:
    # INV-19 / EC-24 / EC-25 / EC-26 / EC-32 / EC-33: a ValueError,
    # never a fallback, a RecursionError or another type.
    with pytest.raises(ValueError):
        compose_api.JsonText.decode(text)


@pytest.mark.parametrize("case", sorted(BOUND_CASES))
def test_records_refuse_a_value_past_their_bound_naming_the_field(compose_api, case) -> None:
    # NFR-8 / T-5 / §9.1 / EC-28: every record a model answer or a step
    # result becomes is bounded, so an oversized or malformed answer is
    # a refusal (and so a repair turn), never a record; the same record
    # at its bound is accepted, so the refusal is the bound's doing.
    past, at_bound, field = BOUND_CASES[case]
    records = Records(compose_api)
    at_bound(records)
    with pytest.raises(compose_api.ConfigurationError) as caught:
        past(records)
    expected = field if isinstance(field, tuple) else (field,)
    assert caught.value.details.get("field") in expected, f"{case}: {caught.value} {caught.value.details}"
