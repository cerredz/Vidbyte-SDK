"""FILE: tests/features/harness_compose/test_harness_compose_stages.py

PURPOSE: run_staged_threads (AC-5, AC-12, INV-16, INV-17, INV-21, INV-22, EC-53, D-14): one entry per stage, each a fresh RUN thread sent its template rendered with the previous successful answer only; after a failed attempt the decision comes from STAGE_DECISIONS by the error's problem, RETRY keeping the rung, RAISE_EFFORT climbing the ladder and staying on its top rung, ABORT ending the stage; every attempt is sent the same prompt; a failed stage leaves later stages without attempts; no sleep happens between attempts and no git runs.
ROLE IN CODEBASE: Start here when a stage retries the wrong way, runs the wrong config, keeps going after a failure, or waits between attempts.
ARCHITECTURE NOTE: The ladder config is the step's own config with a higher reasoning effort, made with dataclasses.replace so it keeps the same stand-in command and label; which rung ran is read from each launch's --reasoning-effort. The sleep spy wraps asyncio.sleep and records only calls made from compose modules, so the base runner's own polling does not count.
FUNCTION INVENTORY: compose_sleeps installs the sleep spy; stage_case builds the failing stage of one AC-12 case; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new decision rule is a STAGE_DECISIONS row first, then one case here.
WHAT NOT TO DO IN THIS FILE: Do not measure the absence of a backoff with a clock; the sleep spy and the attempt count are the evidence.
KNOWN EDGE CASES: The timed-out case holds its stand-in until the step's own timeout stops it, so it uses fast_stop and a short timeout_seconds; the stand-in would end by itself after its hold limit.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-16, INV-17, INV-21, INV-22, §6.2 AC-5, AC-12, §6.3 EC-53, EC-54, §9.2 STAGE_DECISIONS
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_stages.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys

import pytest

GROK_TEXT = "GROK-STAGE-1 says {one} and {{two}}."
OPENCODE_TEXT = "OPENCODE-STAGE-2 adds {three}."
HOLD_TIMEOUT_SECONDS = 0.75
DECISIONS = {
    "not_installed": "abort", "launcher_refused": "abort", "key_rejected": "abort", "thread_not_found": "abort", "wsl_unavailable": "abort",
    "launch_failed": "retry", "timed_out": "retry", "output_too_large": "retry", "protocol_mismatch": "retry",
    "run_failed": "raise_effort",
}


def compose_sleeps(monkeypatch) -> list[float]:
    # Every asyncio.sleep with a positive delay called from a compose
    # module.
    original = asyncio.sleep
    seen: list[float] = []

    async def sleep(delay, *args, **kwargs):
        caller = sys._getframe(1).f_code.co_filename.replace("\\", "/")
        if "/vidbyte/harnesses/native/compose/" in caller and delay > 0:
            seen.append(delay)
        return await original(delay, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    return seen


def stage_case(api, steps, case: str):
    # The failing stage 1 of one AC-12 case, and its expected attempts.
    if case == "timed_out":
        step = steps.bind("grok", label="failing", fake={"mode": "hold"}, timeout_seconds=HOLD_TIMEOUT_SECONDS)
    elif case == "key_rejected":
        step = steps.bind("grok", label="failing", fake={"mode": "key_rejected"})
    else:
        step = steps.bind("grok", label="failing", fake={"mode": "fail", "vendor_text": "the model gave up", "exit_code": 93})
    if case == "run_failed without a ladder":
        return api.records.StageSpec(step=step, template="Start."), step
    stronger = dataclasses.replace(step.config, reasoning_effort=api.GrokReasoningEffort.HIGH)
    return api.records.StageSpec(step=step, template="Start.", retries=2, ladder=(stronger,)), step


def test_stage_decisions_are_the_spec_table(compose_api) -> None:
    # §9.2 STAGE_DECISIONS / D-14 / EC-54: every NativeThreadProblem has
    # its decision; a code with no problem gets ABORT.
    constants = compose_api.constants
    assert {problem.value: decision.value for problem, decision in constants.STAGE_DECISIONS.items()} == DECISIONS
    assert set(constants.STAGE_DECISIONS) == set(compose_api.NativeThreadProblem)
    assert constants.STAGE_UNCLASSIFIED_DECISION.value == "abort"


@pytest.mark.asyncio
async def test_three_stages_on_three_harnesses_pass_each_answer_on(compose_api, sandbox, steps, runs, pack, monkeypatch) -> None:
    # AC-5 / INV-17: stage 1's template rendered with no values ({{ to
    # {), later templates with the previous answer only, braces in
    # answers literal; one RUN attempt per stage on rung 0; no git.
    api = compose_api
    sleeps = compose_sleeps(monkeypatch)
    grok = steps.bind("grok", label="stage-1", fake={"text": GROK_TEXT})
    opencode = steps.bind("opencode", label="stage-2", fake={"final_parts": [OPENCODE_TEXT]})
    muse = steps.bind("muse", label="stage-3", fake={"text": "MUSE-STAGE-3 done."})
    result = await api.compose.run_staged_threads([
        api.records.StageSpec(step=grok, template="Start with {{braces}} intact."),
        api.records.StageSpec(step=opencode, template="Review: {previous}"),
        api.records.StageSpec(step=muse, template="Finish: {previous}"),
    ])
    prompts = [pack.launch_prompt(sandbox.only_launch(label)) for label in ("stage-1", "stage-2", "stage-3")]
    assert prompts == ["Start with {braces} intact.", "Review: " + GROK_TEXT, "Finish: " + OPENCODE_TEXT]
    assert "--resume" not in sandbox.only_launch("stage-1")["start"]["options"]
    assert "--session" not in sandbox.only_launch("stage-2")["start"]["options"]
    assert "--session-id" not in sandbox.only_launch("stage-3")["start"]["options"]
    assert len(result.stages) == 3 and result.failed_stage is None
    for stage, label in zip(result.stages, ("stage-1", "stage-2", "stage-3"), strict=True):
        (attempt,) = stage.attempts
        assert attempt.rung == 0 and attempt.decision is None and attempt.outcome.ok
        assert stage.ok and stage.thread_id == pack.launch_session(sandbox.only_launch(label))
    assert result.stages[2].text == "MUSE-STAGE-3 done."
    assert runs.git_calls() == [] and sleeps == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "rungs", "decision", "efforts"), [
    ("run_failed", [0, 1, 1], "raise_effort", [None, "high", "high"]),
    ("timed_out", [0, 0, 0], "retry", [None, None, None]),
    ("key_rejected", [0], "abort", [None]),
    ("run_failed without a ladder", [0, 0], "raise_effort", [None, None]),
])
async def test_failed_attempts_follow_the_decision_table(compose_api, sandbox, steps, runs, pack, monkeypatch, fast_stop, case, rungs, decision, efforts) -> None:
    # AC-12 / INV-21 / INV-22 / EC-53: attempts, rungs and decisions as
    # specified; the ladder config runs from attempt 2 for run_failed;
    # every attempt is a fresh RUN with the same prompt; stage 2 has no
    # attempts and never starts; no sleep between attempts.
    api = compose_api
    sleeps = compose_sleeps(monkeypatch)
    failing, step = stage_case(api, steps, case)
    never = steps.bind("opencode", label="never")
    result = await api.compose.run_staged_threads([failing, api.records.StageSpec(step=never, template="Then: {previous}")])
    attempts = result.stages[0].attempts
    assert [attempt.rung for attempt in attempts] == rungs
    assert [attempt.decision.value for attempt in attempts] == [decision] * len(rungs)
    assert all(not attempt.outcome.ok for attempt in attempts)
    expected_code = "grok.timed_out" if case == "timed_out" else "grok.key_rejected" if case == "key_rejected" else "grok.run_failed"
    assert all(attempt.outcome.error.failure_code.value == expected_code for attempt in attempts)
    launches = sandbox.launches(label="failing")
    assert len(launches) == len(rungs)
    assert [launch["start"]["options"].get("--reasoning-effort") for launch in launches] == efforts
    assert all(pack.launch_prompt(launch) == "Start." and "--resume" not in launch["start"]["options"] for launch in launches)
    assert result.failed_stage == 0 and len(result.stages) == 2 and result.stages[1].attempts == ()
    assert sandbox.launches(label="never") == [] and runs.calls_of("never") == []
    assert sleeps == [] and runs.git_calls() == []
