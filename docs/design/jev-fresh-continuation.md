# JEV fresh continuation

## Change

Add an opt-in `fresh` continuation gate to `JevAgent`. It uses the existing done-check verdict and continuation limit, then gives a newly constructed agent a clean context containing the original request, run state, and latest handoff, plus concise instructions to complete the request. The fresh agent's response is fed back to the main loop as its next user message.

## Implementation

Add a validated continuation mode to `JevContinualSettings`, defaulting to the existing same-loop behavior. Build a separate `JevFreshContinuation` when mode is `fresh`; keep the finish-attempt runtime contract unchanged. Store its additional context in a prompt asset and cover mode validation and behavior with offline tests.

## Files

- `vidbyte/lib/enums/jev.py` and public exports: continuation mode.
- `vidbyte/agents/jev/settings.py`, `agent.py`, and `continuation/`: setting, construction, and fresh-context behavior.
- `vidbyte/lib/enums/prompts.py` and `vidbyte/prompts/prompts/`: fresh continuation instructions.
- `tests/test_jev_fresh_continuation.py`: mode and clean-context behavior.
- `skills/jev-agent/SKILL.md`, `skills/jev-continuation/SKILL.md`, and the Jev/prompt READMEs: continuation mode contract and usage.

## Risk and verification

The fresh mode makes one additional generative call per failed done check, bounded by the existing continuation limit. Verify with focused Jev tests, lint, and source and package CI stages.
