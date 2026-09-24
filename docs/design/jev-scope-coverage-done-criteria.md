# Jev scope-coverage done criteria

## What and why

Done check #3: **the agent silently narrows the scope.** The user asks for a change across a group ("all our model providers", "the web, CLI, and API"). The agent does one member, or a single example, and then finishes as if it covered the whole group. No single file or tool call proves this, because the evidence is spread across the run. So the check uses the same shape as the multipart preset (PR #452): a state section built once from the request, a matching handoff section built at each finish attempt, and small Jev questions that code combines.

Public surface:

```python
JevAgent(settings, done_criteria=JevPresets.ScopeCoverage)
JevAgent(settings, done_criteria=(JevPresets.MultiPart, JevPresets.ScopeCoverage))
```

`done_criteria` now accepts one preset or a tuple of distinct presets. When several presets are enabled, the run still makes **one** state-builder call and at most **one** handoff call per finish attempt. Each preset adds its own section to both schemas.

This PR is stacked on PR #452 (`feat/jev-multipart-done-criteria`) and is retargeted to `main` after #452 merges.

## How it works

### 1. State section (built once, before the loop)

`JevRunState.scope` is a `JevScopeSection` holding a tuple of `JevScopeDimension` records. One dimension is one group that the request quantifies over.

| Field | Meaning | Used by |
|---|---|---|
| `id` | stable identifier | handoff and metadata |
| `request_quote` | verbatim span of the request that sets the scope | code validation; Jev Q2 state |
| `requested_change` | the change each member must receive | Jev Q1 state |
| `unit_noun` | what one member is ("model provider") | Q1, Q2, feedback |
| `membership_rule` | how to recognize a member in the run | handoff builder prompt |
| `breadth` | `every_member` / `named_list` / `one_example` / `single_target` | code gate |
| `universe` | `named_in_request` / `found_in_workspace` / `open_ended` | code chooses the checking path |
| `named_units` | members the user named, copied verbatim | code set arithmetic |
| `excluded_units` | members the user excluded, copied verbatim | code subtracts them |
| `partial_allowed_quote` | verbatim text allowing partial coverage, or `""` | code skips the dimension |
| `deliverable_id` | the MultiPart deliverable this scope belongs to, or `""` | metadata |

Code validates the builder output against the original request. `request_quote`, every named or excluded unit, and a non-empty `partial_allowed_quote` must appear in the request after whitespace and case normalization. `named_list` requires `named_in_request` and at least two named units, and `named_in_request` requires at least one. A violation raises `OutputSchemaViolationError`, the same fail-closed behavior as #452.

A dimension is **checked** only when its breadth is `every_member` or `named_list` and it has no `partial_allowed_quote`. This stops the check from firing on requests like "give me an example".

**Breadth review (Jev Q0).** The one mistake the check cannot recover from is the builder labeling "all providers" as a single example. For each dimension the builder labeled `one_example` or `single_target`, one Jev `choice` over `{request_quote, unit_noun}` asks what the quote asks for. If P(every_member) + P(named_list) ≥ 0.5, code upgrades the breadth and records `breadth_upgraded`. Most runs have no downgraded dimensions and make no call.

### 2. Handoff section (at each finish attempt, same call as MultiPart)

`JevRunHandoff.scope` holds one `JevScopeDimensionHandoff` for each checked dimension:

- `enumeration`: excerpts from `tool_call_N` outputs that list the group's members.
- `units`: one `JevScopeUnitRecord` for every named member and every member found in the run, worked or not. Each record has `unit`, `source` (`named_in_request` / `found_by_run` / `mentioned_by_agent`), and `work`: excerpts from `iteration_N` or `tool_call_N` sources that show actions on that unit.
- `narrowing`: agent text choosing a subset ("I'll use OpenAI as the representative case").
- `coverage_claims`: `final_answer` excerpts about how far the change reached.

The handoff contains **no verdict fields**. Every excerpt reuses #452's exact-source validation. Code also enforces the rules below:

- The dimension IDs exactly match the checked dimensions.
- Every non-excluded named unit has a record. If one is missing, the handoff is rejected.
- The unit `source` is recomputed in code:
  - A unit that matches `named_units` is `named_in_request`.
  - A claimed `found_by_run` unit keeps that source only if its name appears in an enumeration excerpt.
  - Anything else is `mentioned_by_agent`, which is not required.
- Each reference kind must point at the right source kind: enumeration at tool calls, work at iterations or tool calls, and claims at the final answer.

### 3. Jev questions

These follow the asking-jev-questions skill. The facts are computed in code, and Jev does only recognition.

| Step | Owner |
|---|---|
| required units = named ∪ found_by_run − excluded | code |
| a unit with no `work` excerpts is uncovered | code (no Jev call) |
| universe gap: `found_in_workspace` + `every_member` with no enumeration | code |
| **Q1 `unit_coverage`**: a `choice` for each required unit that has work. State `{requested_change, unit_noun, unit, work_record}`; options `applied` / `attempted` / `examined_only` / `none`. | Jev |
| **Q2 `coverage_statement`**: a `choice` for each incomplete dimension. State `{request_quote, unit_noun, final_answer}`; options `claims_all` / `reports_partial` / `silent`. | Jev |
| combining the answers, thresholds, continue or accept | code |

A unit is covered when P(applied) ≥ 0.8. A dimension is disclosed when P(reports_partial) ≥ 0.7. These are starting thresholds and are not tuned yet. Question instructions are prompt assets, and option rubrics live beside the question builder.

### 4. Policy at a finish attempt

- **Every checked dimension is complete:** accept.
- **Attempt ≤ 2 and something is incomplete:** continue the same loop. The feedback names each uncovered unit. It also asks the agent to list the group when there is a universe gap. When Q2 says `claims_all`, it states that the final answer overclaims.
- **Attempt > 2:**
  - If the final answer discloses the gap, accept with outcome `partial_disclosed`.
  - Otherwise, request disclosure once.
  - If the answer is still silent, accept with outcome `partial_undisclosed`.

  The runtime never rewrites the agent's output.

The metadata under `done_criteria.scope_coverage` records, per dimension:

- required, covered, and uncovered units;
- the P(applied) for each unit;
- whether the universe was listed;
- the Q2 label;
- whether the gap was disclosed;
- whether the breadth was upgraded.

### 5. Decomposition

| Module | Role |
|---|---|
| `jev/presets.py` | `JevPresets.ScopeCoverage`; `normalize_done_criteria()` |
| `jev/done_checks.py` | `JevDoneCheck` ABC + `JevDoneCheckResult`; the contract each preset implements |
| `jev/multi_part.py` | `MultiPartDoneCheck`: #452's policy moved behind the ABC; it no longer builds the handoff itself |
| `jev/scope_coverage/enums.py` | breadth, universe, unit source, outcome |
| `jev/scope_coverage/state.py` | `JevScopeDimension`, `JevScopeSection`: schema + request-grounded validation |
| `jev/scope_coverage/handoff.py` | `JevScopeUnitRecord`, `JevScopeDimensionHandoff`, `JevScopeHandoff`: schema + source recomputation |
| `jev/scope_coverage/questions.py` | `ScopeCoverageQuestions`: builds Q0/Q1/Q2 and their states |
| `jev/scope_coverage/decision.py` | `JevScopeDimensionDecision`, `JevScopeCoverageDecision`: metadata + feedback text |
| `jev/scope_coverage/check.py` | `ScopeBreadthReview` (Q0) and `ScopeCoverageDoneCheck` (Q1/Q2 + policy) |
| `jev/builders.py` | renamed `JevRunStateBuilderAgent` / `JevRunHandoffBuilderAgent`; each composes its system prompt and schema from the enabled sections |
| `jev/run_state.py` | `JevRunState.presets` + `.scope`; `JevRunHandoff.scope`; `JevEvidenceReference.parse` shared by both sections |
| `jev/runtime.py` | builds the state once, runs Q0, builds one handoff per finish attempt, runs each check, merges feedback and metadata |

## Files

- **New:**
  - `vidbyte/agents/jev/done_checks.py` and `multi_part.py`;
  - `vidbyte/agents/jev/scope_coverage/` (the modules above plus `__init__.py`);
  - prompt assets `state_builder_multi_part.md`, `state_builder_scope_coverage.md`, `handoff_builder_multi_part.md`, `handoff_builder_scope_coverage.md`, `scope_breadth.md`, `scope_unit_coverage.md`, `scope_coverage_statement.md`;
  - `scripts/test-jev-scope-coverage-done-criteria.py`.
- **Modified:**
  - Jev package: `presets.py`, `agent.py`, `builders.py`, `run_state.py`, `runtime.py`, `__init__.py`.
  - Wiring: `vidbyte/agents/client.py`, `vidbyte/lib/constants/jev.py`, `vidbyte/lib/enums/prompts.py`.
  - Prompts: `vidbyte/prompts/prompts/jev/{jev.json,state_builder.md,handoff_builder.md}`, `vidbyte/prompts/README.md`.
  - Docs and tests: `skills/jev-agent/SKILL.md`, `tests/test_jev_agent.py`.

## Risks and open questions

- **Stacked on #452.** Three done-check foundations are open: #450 (`JevRunSection`, a settings flag), #451, and #452. This PR follows #452. If #450's foundation wins, the `scope_coverage/` modules port over as a section; they touch the seam only through `JevDoneCheck`.
- **Open-ended scopes** ("every edge case") can only be checked for named units, overclaiming, and disclosure.
- **The run's own listing can be narrow**, for example one folder when members live in two. The check verifies that a listing exists, not that it is complete.
- **Coverage depends on the handoff.** The handoff is trusted to record every member it saw in the enumeration. Code cannot parse arbitrary tool output to confirm that.
- **Cost:** Q1 grows with the number of worked units. Units with no work skip Jev.
- **Mid-run user messages** do not exist inside one `arun`, so the only allowed narrowing comes from the original request.
- **Renaming** the #452 builder classes and changing the `done_criteria` metadata shape (per-preset subsections) are intentional follow-ons to #452.

## Verification

- `tests/test_jev_agent.py`, new `JevScopeCoverageDoneCriteriaTests`:
  - a named list partly covered, then continued and completed;
  - units without work never reach Jev;
  - `one_example` is not checked, and a breadth review can upgrade it;
  - partial scope allowed by the request;
  - a universe gap;
  - demotion of an unlisted "found" unit;
  - excluded units;
  - a handoff that omits a named unit is rejected;
  - request-grounded state validation;
  - both the disclosed and undisclosed disclosure paths;
  - overclaim feedback;
  - combined presets make one state call and one handoff call;
  - `done_criteria` tuple validation;
  - real builders run end to end with strict output.
- Existing multipart tests updated for the renamed builders and the metadata layout.
- `scripts/test-jev-scope-coverage-done-criteria.py`, `python lint/run.py`, and `python scripts/run_ci.py --stage source`; then PR CI.
