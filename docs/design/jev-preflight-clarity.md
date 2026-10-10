# Jev preflight: clarity

## Problem

`JevAgent` should not spend a generative run on a request it cannot act on correctly. The clarity preflight asks Jev, in one batched request, whether the user's request states what the agent needs to begin. When it does not, the agent returns one focused clarifying question instead of running the model loop.

## Public surface

```python
JevAgentSettings(..., preflight=(JevPreflightPreset.CLARITY,))
```

- `preflight` is a tuple of flags. Strings are accepted and normalized; an unknown flag, a bare string, or a repeated flag fails at settings construction.
- A run's preflight state is `result.metadata["jev_response"]`, a `JevResponse` with `input`, `output`, `results`, `needs_clarification`, and `usage`. `results` maps each enabled `JevPreflightPreset` to a `JevPresetResult` (`score`, `answers`, `available`).
- A short-circuited run returns strategy `jev_preflight` and `stop_reason = "needs_clarification"`.

## Where the code lives

| Concern | Location |
| --- | --- |
| Flag enum `JevPreflightPreset`, question-key enum `JevPreflightQuestionKey` | `vidbyte/lib/enums/jev.py` |
| Records `JevPreflightQuestion`, `JevPresetDefinition`, `JevPresetResult`, `JevResponse` | `vidbyte/lib/dataclasses/jev.py` |
| Flags the user can enable and the questions and threshold each one turns on (`JevPresets`) | `vidbyte/lib/jev/presets.py` |
| One dataclass per clarity question | `vidbyte/lib/jev/preflight/clarity.py` |
| `JevPreflight`: registry over every question, plus `get`, `validate`, `combine`, `run` | `vidbyte/lib/jev/preflight/preflight.py` |
| Policy values (`JEV_CLARITY_THRESHOLD`, `JEV_PREFLIGHT_REQUEST_FIELD`, metadata key, strategy name) | `vidbyte/lib/constants/jev.py` |
| Settings field and runtime short-circuit | `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/runtime.py` |

`JevAgentSettings` calls `JevPreflight.validate`; `JevRuntime` calls `JevPreflight.run`. Nothing in the agent layer knows question text, scoring, or fallback policy. The lib package reaches decision usage parsing through `ModelProvider.usage_class`, so it never imports the agents layer.

## The questions

The state is `{"request": <user message>}`. Every question is a noul written to `skills/asking-jev-questions/SKILL.md`: four to five sentences carrying a definition, a boundary with examples, a focus, and one positively phrased question about `` `request` ``, so Jev only recognizes and never reasons, counts, or forecasts. `true` always means the property is satisfied, and a request that does not need a property (no pointing words, no time dependence, a factual question with no constraints) satisfies it by definition.

| Key | Recognizes |
| --- | --- |
| `clarity.goal` | an action together with the thing it acts on |
| `clarity.deliverable` | the kind of result expected, named or fixed by the verb |
| `clarity.target` | the specific thing the work is done on |
| `clarity.references` | every pointing word resolved inside the request |
| `clarity.scope` | how much work is wanted |
| `clarity.completion` | a condition that shows the work is done |
| `clarity.information` | the material the work reads from, included or locatable |
| `clarity.constraints` | the limits a choice or build must respect |
| `clarity.priorities` | one aim, or an order among competing aims |
| `clarity.consistency` | instructions that can all be followed together |
| `clarity.time_context` | the date, period, or version the result depends on |
| `clarity.single_reading` | every key word pointing to one kind of work |

The earlier draft's "hidden information", "judgment", and "independent agreement" questions were dropped: each asked Jev to forecast or reason about what is absent, which the skill moves out of Jev. "Outcome" merged into goal and completion; "language" became `single_reading`.

## Actions

- Score each preset as the mean P(yes) of its questions (code, not Jev, combines the answers).
- Below `JEV_CLARITY_THRESHOLD` (0.75, a starting point, not a tuned value), return the `clarification` of the single lowest-P(yes) question across failing presets and skip the generative runner.
- At or above the threshold, run the inherited loop and attach the `JevResponse`.
- Fail open: a missing TypeSafe key, a provider error, an oversized state, or a missing or non-noul answer marks every enabled preset `available=False` and runs the loop.
- No enabled preset: no Jev call and an empty `results`.

## Tests

`tests/test_jev_preflight.py` (run with `python scripts/test-jev-preflight.py`) pins the per-question dataclasses and their 4-5 sentence briefs, the flag normalization, `get`/`validate`/`combine`, the record fields, the short-circuit, the threshold boundary, and both fail-open paths.
