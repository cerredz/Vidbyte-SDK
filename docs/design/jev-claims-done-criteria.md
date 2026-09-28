# CLAIMS done check

## Change

Add `JevDoneCheck.CLAIMS`, which checks whether concrete work claims in JevAgent's final answer are supported by the run. The check is opt-in through the existing `JevContinualSettings.checks` setting and fails open when evidence or Jev is unavailable.

## Approach

At each finish attempt, the existing handoff agent extracts each concrete claim about completed work from the final answer and pairs it with supporting tool-call evidence, or explicitly records that none was found. It asks one positive Jev question per claim in the existing batched request. Since claims do not exist until the final answer is written, the handoff supplies this check's items dynamically; the pre-run state is not used to invent a claim list. If a claim fails, the continuation's Focus section names only the unsupported claims and their evidence gaps, so the main agent can complete the work with evidence or correct the answer.

Reuse the existing `ToolCallContextItem` handoff input, `JevDoneContinuation`, and continuation prompt. Add typed claim/evidence records and payloads, the enum and registry entries, section/judgment/explanation cases, public record exports, tests, and update the Jev continuation skills to document this post-run-derived-item exception. Leave `JevRuntime`, `JevAgent` wiring, and settings unchanged.

## Files

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`, and `vidbyte/lib/dataclasses/jev.py`
- `vidbyte/lib/jev/done/claims.py`, `done.py`, `__init__.py`, and `README.md`
- `vidbyte/agents/jev/done/handoff.py`, `run_state.py`, and `vidbyte/agents/jev/continuation/done.py`
- The Jev record export chain: `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, and `vidbyte/__init__.py`
- `tests/test_jev_done.py`, `skills/jev-agent/SKILL.md`, and `skills/jev-continuation/SKILL.md`
- `docs/design/jev-claims-done-criteria.md`

## Risks and open questions

The handoff model could omit or merge claims while extracting them. Its instructions and tests must require one entry per concrete work claim, unique stable ids, and an explicit no-evidence entry rather than silently dropping unsupported claims. An empty claim list passes; malformed handoff output, provider failures, and missing answers fail open, consistent with existing done checks. No open questions.

## Verification

Run `python scripts/test-jev-multipart-done-criteria.py`, `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py --stage package`. Confirm the lint baseline does not increase, then verify every required pull-request check is green.
