# Jev motivating-case done check

## What and why

Done-check #9: *the agent checks the easy case and skips the important edge case.* The ordinary flow works, but the user's request was motivated by a boundary condition such as empty input, retry behavior, or conflicting state. Before the run may finish, `JevAgent` should confirm that the agent actually exercised (or, where allowed, inspected) that motivating case, and not a nearby easier case.

Public surface: `JevAgent(settings, done_criteria=JevPresets.MotivatingCase)`. This keeps the shape used by the unpushed MultiPart work (`JevAgent(settings, done_criteria=JevPresets.MultiPart)`).

The design follows the agreed done-check pattern:

1. A generative **state builder** runs once, before the loop.
2. At each finish attempt, a generative **handoff builder** writes a handoff shaped like that state.
3. **Code** verifies the handoff.
4. **Jev** answers small recognition questions per item.
5. **Code** combines the answers and either accepts the attempt or continues the same loop with feedback.

Questions follow `skills/asking-jev-questions/SKILL.md`.

## How it works

### 1. State (built once)

`MotivatingCaseStateBuilderAgent(BaseAgent)` is tool-free and uses a strict output schema. It turns the request into a `MotivatingCaseState`:

- `ordinary_flow`: the easy case, named so every question can say "not this".
- `testing_restriction_quote`: verbatim request text limiting testing, or empty.
- `scenarios`: each one has:
  - `id`
  - `role`: motivating / requested / implied. Implied scenarios never block.
  - `kind`: a closed `JevBoundaryKind`.
  - `source_quote`: verbatim; code checks it is a substring of the request.
  - `target`
  - `condition`: observable.
  - `near_miss`: the closest case that does not count.
  - `expected_behavior`: empty when unstated.
  - `literal_inputs`: exact values the user gave.
  - `exercise_mode`: run / run_or_inspect / inspect_only.

Code validates unique IDs, the quote substrings, and the caps (8 scenarios, 3 motivating).

**Recall guard.** If `scenarios` is empty, one Jev noul asks whether the request names an unusual situation. When P ≥ 0.6, the builder is rebuilt once with a note. If it is still empty, the check is disabled for the run and `builder_disagreement` is recorded. An empty state means no finish check at all.

### 2. Finish-attempt seam

`AgentRuntime._continue_finish_attempt(result, state, messages) -> bool` is called on both finish paths: the plain final response and `isDone`. The default returns `False`, so behavior is unchanged. `JevRuntime` overrides it.

- On a plain final response that continues, the assistant message is appended before the feedback.
- On `isDone`, the feedback becomes the tool result.

### 3. Evidence ledger (code)

`RunEventLedger` is built from `state.call_contexts`. These hold the raw `ToolResult`, before model-visible truncation. Each non-internal call becomes `RunEvent(event_id="e<n>", index, tool, permission, state, arguments, output, intent)`. The permission comes from the tool spec.

### 4. Handoff (built per attempt)

`MotivatingCaseHandoffBuilderAgent(BaseAgent)` receives:
- the request,
- the state,
- the rendered ledger,
- the candidate final reply.

It returns exactly one `ScenarioExercise` per scenario. The fields are refs and verbatim quotes only, with `""` meaning absent:
- `case_name`
- `setup_ref` / `setup_quote`
- `outcome_ref` / `outcome_quote`
- `inspection_ref` / `inspection_quote`
- `blocker_ref` / `blocker_quote`

There is no verdict field. Code rejects a handoff that does not have exactly one entry per state ID.

### 5. Code checks (`ScenarioEvidenceChecker`)

A ref must exist, and its quote must be a verbatim substring (whitespace-normalized) of that event's arguments or output. Otherwise the pair is dropped.

The outcome counts only when all of these hold:
1. It is an EXECUTE event that succeeded.
2. It is at or after the setup event.
3. It covers the setup: the same event, the verified `case_name` or a setup path appears in it, or the command selects no file.
4. It is not stale: no successful WRITE event comes after it.

**Recovery.** If `setup_ref` is empty and a `literal_input` appears in a WRITE or EXECUTE event, that event becomes the setup, with a code-cut excerpt. An EXECUTE setup is also its own outcome.

### 6. Jev questions

There is one batched request per scenario. Its state holds only the verified, named excerpts. The questions are:

| Question | Type | When asked |
|---|---|---|
| `setup_builds_case` | noul | always |
| `outcome_result` | choice: passed / failed / skipped / unclear | always |
| `asserts_expected` | noul | only when `expected_behavior` is set |
| `code_handles_case` | noul | only for inspect modes |
| `environment_blocked` | noul | always |
| `discloses_unverified` | noul, over the final reply | always |

A question is left out when its excerpt is missing.

### 7. Combination (code)

- **exercised**: run ok, setup ≥ 0.8, `passed` ≥ 0.7, and asserts ≥ 0.7 (when asked).
- **inspected**: inspect mode and handles ≥ 0.8.
- **blocked**: a restriction quote exists, or blocked ≥ 0.8.
- Otherwise **not_exercised**.

What code does with each outcome, for motivating and requested scenarios:
- `not_exercised`: continue.
- `blocked`: continue unless disclosed ≥ 0.5.
- Implied scenarios are reported only.

Code writes the feedback from the state fields. At most 2 continuations are allowed; after that the attempt is accepted and the unresolved scenarios go into metadata.

### 8. Failure policy

- A missing TypeSafe key raises `ConfigurationError` at the start of the run, because the capability was explicitly enabled.
- Provider errors and builder schema violations fail open: the attempt is accepted and `done_criteria.status` records the reason. Infrastructure failures never change the run's outcome.

The metadata lands at `result.metadata["done_criteria"]`.

## Files

**New:**
- `docs/design/jev-motivating-case.md`
- `vidbyte/agents/jev/presets.py`
- `vidbyte/agents/jev/motivating_case/__init__.py`, `state.py`, `evidence.py`, `handoff.py`, `checks.py`, `questions.py`, `policy.py`, `builders.py`
- `vidbyte/prompts/prompts/jev/jev.json`, `motivating_case_state_builder.md`, `motivating_case_handoff_builder.md`
- `tests/test_jev_motivating_case.py`

**Modified:**
- `vidbyte/agents/runtime.py` (the seam)
- `vidbyte/agents/jev/agent.py`, `runtime.py`, `__init__.py`, `README.md`
- `vidbyte/agents/__init__.py`, `vidbyte/__init__.py` (export `JevPresets`)
- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/enums/__init__.py`
- `vidbyte/lib/constants/jev.py`
- `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/README.md`
- `skills/jev-agent/SKILL.md`

## Risks and open questions

- **Untuned thresholds.** 0.8 / 0.7 / 0.6 / 0.5 need a labeled set in vidbyte-evals.
- **Stale rule.** Any later WRITE, even to docs, forces a re-run. This is conservative and costs one iteration.
- **Coverage rule.** "Selects no file" is a heuristic.
- **Builder misses.** The state builder can still miss a case the recall guard does not flag.
- **Collision with the MultiPart work.** It adds the same seam, `JevPresets`, `jev.json` and `done_criteria`. Merging will need to combine the presets (a preset → section-subclass registry).

## Verification

- `tests/test_jev_motivating_case.py` uses scripted generative runners and a scripted TypeSafe transport. It covers the empty state, the recall-guard rebuild, the near-miss rejection, stale runs, fake quotes, literal recovery, blocked plus disclosure, the continuation cap, `isDone` continuation, fail-open, the missing key, and the default seam being inert.
- Then run `python scripts/run_ci.py --stage source`, the semgrep policy, and the PR CI.
