# Jev clarity preflight

## What and why

Add the first opinionated JevAgent capability: an optional clarity preflight that classifies a request before the generative runtime starts. One TypeSafe Jev call evaluates 18 positively worded clarity questions. A low average clarity score returns a focused clarification question immediately; a clear or unavailable preflight continues through the existing agent loop.

## How

- Add `JevPreflightPreset.CLARITY` and an immutable registry containing its shared four-sentence context, 18 Noul questions, threshold, and clarification prompts.
- Add `preflight` to `JevAgentSettings` (a `JevPreflight` since the custom-questions change); keep it disabled by default and reject duplicate or unknown presets during settings validation.
- Add `JevRuntime.preflight()`. It flattens every enabled preset into one `JevDecisionRequest`, runs it once, scores each preset from the mean `true` probability, and identifies the lowest-scoring clarity dimension when clarification is required.
- Add one small mutable, run-local `JevResponse` with only `input`, `output`, `results`, `needs_clarification`, and `usage`. Preset detail is represented inside typed `JevPresetResult` values in `results`.
- Override `JevRuntime.arun()` to stop before the main loop when clarification is needed, or attach the completed `JevResponse` to ordinary result metadata after the main loop. Decision-model configuration and provider failures fail open and are represented as unavailable preset results.

## Files

- Create `vidbyte/agents/jev/presets.py` and `vidbyte/agents/jev/response.py`.
- Modify Jev settings, runtime, package exports, and root exports.
- Add focused tests and a discoverable script entrypoint.
- Update `skills/jev-agent/SKILL.md` to document the opinionated preflight extension pattern.

## Risks and open questions

- `0.75` is an initial policy threshold and will need calibration against real requests.
- Averaging treats every clarity dimension equally; the typed result retains per-question probabilities so later calibration can change policy without changing the provider call.
- Fail-open behavior preserves agent availability when Jev is not configured, but means preflight is advisory rather than a hard dependency.
- This change intentionally supports registered presets only. Public custom-question composition remains out of scope until its policy and collision behavior are designed.

## Verification

- Unit tests cover settings validation, the exact question set and one-call request shape, score calculation, clarification short-circuiting, clear-request continuation, fail-open behavior, usage parsing, and public exports.
- Run the focused Jev preflight script, the existing Jev scaffold script, and `python scripts/run_ci.py`.
