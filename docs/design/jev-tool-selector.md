# Jev tool selector preflight

## Goal

Let `JevAgent` ask Jev which configured tools may help with the current request, then omit low-probability tools from that run's model schemas and execution catalog. The option is enabled with `JevPreflightPreset.TOOL_SELECTOR`; the caller can set a probability cutoff from 0 through 1.

## Design

Add a small `JevPreflight` base interface and a `JevPreflightTools` implementation. The implementation builds one Noul question per user tool, sends all questions in one `DecisionModelRunner` request, filters tools whose `P(true)` is below the configured cutoff, and builds a new immutable `Tools` catalog. The public setting defaults to 0.20 and rejects booleans, non-finite values, and values outside the inclusive probability range [0, 1].

`JevRuntime` applies this only when TOOL_SELECTOR is enabled. It updates the run-local user and runtime catalogs, replaces the prebuilt context's tool specs, and removes any caller-supplied `tools` override before delegating to `AgentRuntime`. The internal `isDone` tool remains available. Missing credentials, provider errors, and incomplete/malformed answers fail open to the original catalog. Selector usage is exposed separately in result metadata.

This branch starts from current `origin/main`, which contains the Jev scaffold but not open PR #439's clarity preflight. The selector therefore uses its own named setting and runtime path rather than depending on that unmerged branch; the public enum can later gain CLARITY when #439 is integrated.

## Files

- `vidbyte/agents/jev/preflight.py`: base interface and tool-selector implementation.
- `vidbyte/agents/jev/settings.py`, `runtime.py`, package exports, and Jev constants: setting validation, preset selection, runtime integration, and public API.
- `tests/test_jev_tool_selector.py`, `scripts/test-jev-tool-selector.py`, and `skills/jev-agent/SKILL.md`: deterministic coverage and contributor guidance.

## Verification

Run the focused selector script, SDK lint, source CI stage, and full `scripts/run_ci.py` gate. Tests cover disabled behavior, batched questions, threshold boundaries, fail-open behavior, safe internal tool retention, and tool schema/execution filtering.
