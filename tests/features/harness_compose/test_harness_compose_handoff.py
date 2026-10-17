"""FILE: tests/features/harness_compose/test_harness_compose_handoff.py

PURPOSE: handoff_thread (AC-4, INV-6, INV-15, INV-16, INV-17, EC-64): the source thread is resumed, not forked, with the handoff_summary prompt; the target starts a new thread seeded with handoff_seed holding that answer literally; the record carries both outcomes and thread ids; no git runs; a failed summary turn never starts the target (failed_step 0), and a failed target is failed_step 1.
ROLE IN CODEBASE: Start here when a handoff forks the source, loses the summary, or starts the target after a failed summary.
ARCHITECTURE NOTE: The source thread is made by a direct run_grok_thread call first, so it lives under the private Grok home of the workspace, where the stand-in finds it again by --resume. The workspace is not a repository, so any git child would also fail visibly.
FUNCTION INVENTORY: the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new handoff behaviour gets its own labelled stand-ins.
WHAT NOT TO DO IN THIS FILE: Do not bind the source with bind_thread; a RUN source is refused (EC-76, in the validation module).
KNOWN EDGE CASES: Grok prints a thread id only at exit, so a failed continue carries the caller's thread id (base D-27).
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-16, INV-17, §6.2 AC-4, §6.3 EC-64, EC-76
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_handoff.py
"""

from __future__ import annotations

import pytest

SUMMARY = "SUMMARY-6d2e: refactor cli.py next; keep {braces} and {{doubles}} literal."


@pytest.mark.asyncio
async def test_handoff_resumes_the_source_thread_and_seeds_a_new_target_thread(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-4 / INV-17: summary on the same Grok thread (no fork), seed on a
    # new opencode thread, both thread ids in the record, no git.
    api = compose_api
    origin = await steps.bind("grok", label="origin")("Plan the refactor.")
    source = steps.bind("grok", "continue", origin.thread_id, label="summary", fake={"text": SUMMARY})
    target = steps.bind("opencode", label="target")
    result = await api.compose.handoff_thread(source, target)
    summary_launch = sandbox.only_launch("summary")
    assert summary_launch["start"]["options"]["--resume"] == origin.thread_id and summary_launch["start"]["switches"] == []
    assert pack.launch_prompt(summary_launch).strip() == pack.render("handoff_summary")
    target_launch = sandbox.only_launch("target")
    assert pack.launch_prompt(target_launch).strip() == pack.render("handoff_seed", summary=SUMMARY)
    assert "--session" not in target_launch["start"]["options"] and target_launch["start"]["switches"] == []
    assert result.summary.ok and result.summary.text == SUMMARY and result.summary.thread_id == origin.thread_id
    assert result.target.ok and result.target.thread_id == pack.launch_session(target_launch)
    assert result.failed_step is None
    assert runs.position("exit", runs.calls_of("summary")[0]) < runs.position("enter", runs.calls_of("target")[0])
    assert runs.git_calls() == []


@pytest.mark.asyncio
async def test_failed_summary_never_starts_the_target_and_a_failed_target_is_step_one(compose_api, sandbox, steps, runs, pack) -> None:
    # EC-64 / INV-16 / INV-15: key_rejected on the summary turn gives
    # failed_step 0 and no target; a target that fails gives
    # failed_step 1 with its own error.
    api = compose_api
    origin = await steps.bind("grok", label="origin")("Plan the refactor.")
    rejected = steps.bind("grok", "continue", origin.thread_id, label="rejected", fake={"mode": "key_rejected"})
    never = steps.bind("opencode", label="never")
    stopped = await api.compose.handoff_thread(rejected, never)
    assert stopped.failed_step == 0 and stopped.target is None
    assert stopped.summary.error.failure_code.value == "grok.key_rejected"
    assert stopped.summary.thread_id == stopped.summary.error.thread_id
    assert sandbox.launches(label="never") == [] and runs.calls_of("never") == []
    source = steps.bind("grok", "continue", origin.thread_id, label="summary", fake={"text": SUMMARY})
    failing = steps.bind("opencode", label="failing", fake={"mode": "fail", "vendor_text": "the target refused the seed"})
    failed = await api.compose.handoff_thread(source, failing)
    assert failed.failed_step == 1 and failed.summary.ok
    assert failed.target.error.failure_code.value == "opencode.run_failed"
    assert runs.git_calls() == []
