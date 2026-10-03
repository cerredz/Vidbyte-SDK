# Jev faithful scope check

## Goal

Add an opt-in `FAITHFUL_SCOPE` done check to `JevContinualSettings.checks`. Before the main agent starts, JevRunState records the request's single most avoidable hard part as `hard_part`. At each finish attempt, Jev judges run evidence against that fixed statement and the request's `what_not_to_do` limits. If the hard part was weakened, mocked, skipped, hard-coded, or redefined, JevAgent sends the agent back with that gap named and gives the continuation additional bounded loop, token, and tool-call budget. The response records how much extra budget was granted.

## How it works

- Add `hard_part` to the central run-state payload and immutable record. The run-state prompt asks for one concrete requirement in the user's terms, with a clear completion condition; if no unusually difficult requirement stands out, it records the request's central required action.
- Add `FAITHFUL_SCOPE`, its question key, a registered fixed Jev question, and a threshold. The handoff writes observations from the run about the hard part. Jev receives the original request, `hard_part`, `what_not_to_do`, and those observations, and decides whether the evidence shows the hard part was met without changing its meaning.
- On a failed check, the continuation names the hard part, the evidence, and the failed Jev answer, then directs the main agent to work on that exact gap. Existing continuation limits still cap retries. Provider, state, or evidence failures remain unavailable and fail open.
- Add validated per-continuation allowances to `JevContinualSettings`: two loop iterations, 16,000 aggregate tokens, and four tool calls. When `FAITHFUL_SCOPE` fails and another continuation is allowed, JevRuntime extends only finite configured limits by those amounts. Unbounded limits stay unbounded; other failed checks do not receive extra budget. Record the cumulative extra budget in `JevAgent.response`.

## Files

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`, and `vidbyte/lib/dataclasses/jev.py`: check/question identifiers, default budget values, run-state/handoff records, and budget observability.
- `vidbyte/lib/jev/done/faithful_scope.py` and `vidbyte/lib/jev/done/done.py`: fixed Jev question and registry.
- `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/done/run_state.py`, `vidbyte/agents/jev/done/handoff.py`, `vidbyte/agents/jev/continuation/done.py`, and `vidbyte/agents/jev/runtime.py`: validated settings, state/evidence collection and scoring, continuation focus, and bounded budget extension.
- `vidbyte/prompts/prompts/jev_run_state/system_prompt.md`, `vidbyte/prompts/prompts/jev_handoff/system_prompt.md`, and `vidbyte/prompts/prompts/jev_continuation/continue_prompt.md`: prompt instructions.
- `tests/test_jev_done.py`, `skills/jev-agent/SKILL.md`, and `vidbyte/agents/jev/README.md`: regression coverage and user/developer guidance.

## Risks and verification

The main risk is Jev treating claimed completion as evidence or allowing a nearby, easier implementation to stand in for `hard_part`. The question must define observable evidence and those evasion cases directly, and the handoff must report run artifacts rather than verdicts. Tests will cover schema construction, faithful and evasive evidence, fail-open cases, continuation text, budget extension only on a failed faithful-scope check, setting validation, and unchanged behavior when the check is disabled. Run the focused Jev scripts, lint, source CI, and full CI required by `AGENTS.md`.
