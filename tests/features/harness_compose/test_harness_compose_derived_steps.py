"""FILE: tests/features/harness_compose/test_harness_compose_derived_steps.py

PURPOSE: A step compose derives after I/O began is never refused as a bare ConfigurationError (INV-15, D-26, INV-9, INV-19, INV-21): when a skill folder a bound step names is deleted after the composite started, an opencode or Muse verifier relocated into its worktree, a repair turn anchored on the thread of the first answer, and a stage attempt moved to a ladder rung each reach their thread function, which records the vanished folder as that step's NativeThreadError, and the composite or parse_json_answer returns its record.
ROLE IN CODEBASE: Start here when a composite raises ConfigurationError after a step ran, or loses its record because a step it derived was checked again.
ARCHITECTURE NOTE: The stand-in deletes the skill folder itself while it runs, through its `delete_paths` scenario field, as a vendor CLI editing its workspace would: the writer deletes a verifier's skill, or a step deletes its own skill during its first turn or attempt. Every step was valid when it was bound, so only a check after I/O could refuse it.
FUNCTION INVENTORY: make_skill writes a skill folder inside the workspace; deleted reads which paths a launch deleted; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: When compose gains a new way to derive a step from a bound one, add a case here.
WHAT NOT TO DO IN THIS FILE: Do not delete the folder from the test or by patching compose; the stand-in deletes it while it runs, after the composite's own checks.
KNOWN EDGE CASES: The thread function refuses the vanished folder before it starts a process, so each derived step has a recorded error and no launch. A Grok verifier runs in place and is never relocated, so it already records the same failure and is not a case here.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-9, INV-15, INV-19, INV-21, §7 D-26; docs/spec/native-thread-compose/review.md R-15
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_derived_steps.py
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest


def make_skill(sandbox, name: str = "reviewer") -> Path:
    folder = sandbox.workspace / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Test skill {name}.\n---\nUse {name}.\n", encoding="utf-8")
    return folder


def deleted(launch: dict) -> list[str]:
    return [path for record in launch["records"] if record["kind"] == "deleted" for path in record["paths"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["opencode", "muse"])
async def test_a_relocated_verifier_whose_skill_the_writer_deleted_is_recorded_not_raised(compose_api, sandbox, steps, pack, harness) -> None:
    # INV-15 / D-26 / INV-9: the writer deletes the skill folder the
    # verifier names. Relocating that verifier into its worktree
    # does not check the step again, so the thread function records
    # the vanished folder as the verifier's error and verify_with
    # returns its record. Red until review R-15 lands: relocation
    # raised ConfigurationError naming skills[0] after the writer ran.
    api = compose_api
    sandbox.make_repo()
    skill = make_skill(sandbox)
    sandbox.commit()
    writer = steps.bind("opencode", label="writer", fake={"write_files": {"feature.txt": "feature\n"}, "delete_paths": [str(skill)]})
    answer = {"final_parts": [pack.verdict_json("approve")]} if harness == "opencode" else {"text": pack.verdict_json("approve")}
    verifier = steps.bind(harness, label="v", skills=[skill], fake=answer)
    result = await api.compose.verify_with(writer, [verifier], prompt=pack.PROMPT)
    assert deleted(sandbox.only_launch("writer")) == [str(skill)] and not skill.exists()
    assert result.writer.ok and result.failed_verifiers == (0,)
    (verdict,) = result.verdicts
    assert verdict.value is None and len(verdict.turns) == 1
    assert isinstance(verdict.turns[0].error, api.NativeThreadError), f"the verifier's turn is {verdict.turns[0]!r}"
    assert sandbox.launches(label="v") == [], "the thread function refused the vanished folder before it started a process"
    assert sandbox.worktrees() == 1 and sandbox.leftovers() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode", "muse"])
async def test_a_repair_turn_after_the_step_deleted_its_own_skill_is_recorded_not_raised(compose_api, sandbox, steps, pack, harness) -> None:
    # INV-19 / INV-15: the first turn deletes its own skill folder and
    # answers text that is not JSON. The repair turn, anchored on the
    # first turn's thread, is not checked again, so the thread
    # function records the vanished folder and the answer ends with
    # that error. Red until review R-15 lands: anchoring raised
    # ConfigurationError naming skills[0] after the first turn ran.
    api = compose_api
    skill = make_skill(sandbox)
    first = {"final_parts": ["not json"]} if harness == "opencode" else {"text": "not json"}
    later = {"final_parts": [json.dumps({"a": 1})]} if harness == "opencode" else {"text": json.dumps({"a": 1})}
    step = steps.bind(harness, label="json", skills=[skill], fake={"answers": [{**first, "delete_paths": [str(skill)]}, later]})
    answer = await api.compose.parse_json_answer(step, "Give me the answer.", schema="{}", parse=dict)
    (launch,) = sandbox.launches(label="json")
    assert deleted(launch) == [str(skill)]
    assert answer.value is None and len(answer.turns) == 2
    assert answer.turns[0].ok and answer.turns[0].text == "not json"
    assert isinstance(answer.turns[1].error, api.NativeThreadError), f"the repair turn is {answer.turns[1]!r}"


@pytest.mark.asyncio
async def test_a_ladder_rung_after_the_step_deleted_its_own_skill_is_recorded_not_raised(compose_api, sandbox, steps, pack) -> None:
    # INV-21 / INV-15: the first attempt deletes its own skill folder
    # and fails with run_failed, so the stage raises its effort. The
    # attempt on ladder rung 1 is not checked again, so the thread
    # function records the vanished folder, the stage stops and the
    # record comes back. Red until review R-15 lands: moving to the
    # rung raised ConfigurationError naming skills[0].
    api = compose_api
    skill = make_skill(sandbox)
    step = steps.bind("grok", label="stage", skills=[skill], fake={"mode": "fail", "vendor_text": "the model gave up", "exit_code": 93, "delete_paths": [str(skill)]})
    stronger = dataclasses.replace(step.config, reasoning_effort=api.GrokReasoningEffort.HIGH)
    after = steps.bind("grok", label="after")
    stages = [api.records.StageSpec(step=step, template="Go.", retries=2, ladder=(stronger,)), api.records.StageSpec(step=after, template="Then {previous}")]
    result = await api.compose.run_staged_threads(stages)
    (launch,) = sandbox.launches(label="stage")
    assert deleted(launch) == [str(skill)]
    attempts = result.stages[0].attempts
    assert len(attempts) >= 2 and attempts[0].rung == 0 and attempts[1].rung == 1
    assert attempts[0].outcome.error.failure_code.value == "grok.run_failed"
    assert isinstance(attempts[1].outcome.error, api.NativeThreadError), f"the rung-1 attempt is {attempts[1]!r}"
    assert result.failed_stage == 0 and result.stages[1].attempts == ()
    assert sandbox.launches(label="after") == []
