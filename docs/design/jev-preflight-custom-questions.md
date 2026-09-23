# Jev preflight custom questions

## What and why

Callers can turn on named preflight presets such as `CLARITY`, but they cannot ask Jev their own questions about a request. This change adds caller-written yes/no questions to the preflight. Jev answers them in the same single request as the preset questions, and the answers are attached to the run's `JevResponse`.

This PR also carries the clarity preflight from PR #439 onto `main`. PR #439 targets `feat/jev-agent-scaffold`, a branch that PR #438 replaced on `main`. Its code is adapted to main's Jev records: noul answers carry `noul` and no `confidence`, and the local question cap is main's 10,000.

## How

- `JevAgentSettings.preflight` becomes a `JevPreflight` dataclass with two fields:
  - `preset`: registered presets.
  - `custom`: `JevCustomQuestion` values.
  - It replaces the bare tuple of presets.
- `JevCustomQuestion` has only a `name` and a `question`. Every custom question is a noul (yes/no) question, the same type the clarity preset uses. It builds a `JevQuestion` named `custom.<name>`, so it cannot collide with `clarity.*` names.
- `JevPreflight.definitions()` returns one `JevPreflightDefinition` per preset, plus one extra definition for the custom questions. The runtime already combines every question from every definition into one `JevDecisionRequest`, so presets and custom questions still share a single Jev call.
- The custom definition uses `JevPreflightPreset.CUSTOM` and a threshold of `0.0`. The registry never registers `CUSTOM`, so callers cannot select it as a preset. Because the threshold is `0.0`, custom answers are recorded but never trigger clarification. The runtime's existing scoring, clarification, fail-open, and metadata code stores them in `results["custom"]` without changes. The only runtime change is reading `self.jev_settings.preflight.definitions()`.
- All validation happens when `JevPreflight` is built:
  - preset normalization;
  - duplicate presets and duplicate custom names;
  - custom questions of the wrong type;
  - the total question count against `JEV_MAX_QUESTIONS`.
- It happens there because the runtime's fail-open handler would otherwise hide a bad request as "unavailable".

## Files

- Carried from PR #439: `presets.py`, `response.py`, `runtime.py`, settings, exports, `tests/test_jev_preflight.py`, `scripts/test-jev-preflight.py`, `docs/design/jev-preflight-clarity.md`, and `skills/jev-agent/SKILL.md`.
- Modify `vidbyte/agents/jev/presets.py`: add `CUSTOM`, `JevCustomQuestion`, and `JevPreflight`.
- Modify `vidbyte/agents/jev/settings.py`: `preflight: JevPreflight`.
- Modify `vidbyte/agents/jev/runtime.py`: the single definitions line.
- Update the package, agents, and root exports.
- Update `tests/test_jev_preflight.py` with custom-question cases.

## Risks and open questions

- Open draft PRs #440 (tool selector) and #441 (sensitive data) each redefine `JevAgentSettings.preflight` in their own way. Whichever merges second must adopt `JevPreflight`.
- `results["custom"].score` is the mean P(yes) across unrelated questions and means nothing on its own. Callers should read the individual answers.
- The shared preflight context tells Jev to treat irrelevant dimensions as satisfied, which may push custom answers toward `true`. Moving that sentence into the clarity questions' own instructions is left for a follow-up.
- Custom questions cannot block the run yet. Adding a per-question clarification would be a later extension.

## Verification

- Unit tests:
  - `JevPreflight` validation;
  - presets and custom questions sharing one request;
  - custom answers under `results["custom"]`;
  - custom answers never triggering clarification;
  - custom-only preflights;
  - the fail-open path marking custom as unavailable.
- Run `python scripts/test-jev-preflight.py`, `python scripts/test-jev-agent-scaffold.py`, `python lint/run.py`, and `python scripts/run_ci.py`.
