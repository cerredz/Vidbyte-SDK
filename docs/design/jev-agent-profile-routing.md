# Design Doc: Jev Agent Profile Routing

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-26
**Last Updated:** 2026-09-26

---

## 1. Overview

Replace PR #461's specialist record and the public `JevAgent` coordinator with a profile-based API: `Jev` is the coordinator, `JevAgent` is a candidate profile with required `title`, `description`, and `metadata` plus a configured `BaseAgent`, and `JevAgentSettings` contains only the candidate array. After the existing clarity gate passes, a multi-profile configuration asks TypeSafe one structured Choice question using the current request and every profile; code selects the profile with the greatest returned probability, then temporarily applies that profile's runtime configuration to the main `Jev` instance for the normal agent loop. A single profile skips the routing call. Existing preflight and tool-selection features remain configurable through a separate typed `JevRuntimeSettings` object.

---

## 2. Goals & Non-Goals

### Goals

- Rename the public Jev coordinator from `JevAgent` to `Jev`.
- Define public `JevAgent` profiles with required title, description, metadata, and configured agent template fields.
- Reduce `JevAgentSettings` to a validated `agents` collection.
- Select one profile for requests with multiple configured agents, using a newly structured Jev question grounded in the current request and profile data.
- Choose the profile with the highest returned option probability; expose that probability and the considered profiles in the response.
- Apply the selected profile's execution configuration to the main `Jev` for one run, then restore the coordinator's prior configuration even when execution fails or is cancelled.
- Avoid a Jev selection call when there is exactly one candidate.
- Preserve clarity preflight and tool selection through a separate `JevRuntimeSettings` configuration surface.
- Follow the updated `skills/asking-jev-questions/SKILL.md`, keeping prompt text in Markdown assets and all TypeSafe requests typed.
- Update the existing PR #461 branch and PR; do not create a replacement PR.

### Non-Goals

- Do not select multiple profiles, fan out, or merge agent outputs.
- Do not add an automatic second-profile retry when the selected profile fails.
- Do not add a no-match or confidence-threshold branch: the requested policy always chooses the best configured profile when routing succeeds.
- Do not change ordinary `BaseAgent` behavior or TypeSafe provider wire contracts.
- Do not keep any selected profile configuration on `Jev` after its run.
- Do not preserve `JevAgent` as an alias for the former coordinator; that name becomes the candidate-profile type.

---

## 3. Background & Context

- PR #461 is open on branch `ai/resolve-pr-446-comments`, based on current `main` (`df23d2b7`). Its current public API adds `JevSpecialist` entries and `JevAgentSettings.agents`, and `JevSpecialistRouter` forks the selected BaseAgent template.
- The revised request changes the ownership model: each candidate supplies its own configured agent, and the selected configuration is temporarily loaded onto the coordinator rather than running the candidate object as a child.
- `BaseAgent.generate_reply()` resolves the runner, begins tracing, builds context, and then calls the runtime. A route performed only inside `JevRuntime` is therefore too late to change the coordinator's provider/model settings. `Jev` must choose and apply a profile before invoking the normal BaseAgent run path.
- `JevPreflightGate` currently runs before specialist routing. That order remains: a closed clarity gate spends no routing call and executes no candidate.
- The package already supports structured Jev briefs and criteria, typed request/answer records, prompt Markdown assets, wheel package data, a dedicated JEV runtime, response records, scripted offline tests, and a focused Jev test script.
- The SDK is Python 3.11+, distributed as `vidbyte-sdk`, and is alpha. Its root `AGENTS.md` forbids unprompted reads under `docs/`; repository and field-guide instructions were followed without opening unrelated design docs.
- Relevant field-guide constraints: keep capability decisions out of `JevRuntime`; keep outcomes on the response record; `vidbyte.lib` records must validate agent surfaces without runtime upward imports; question briefs follow the complete five-part format and criteria use mirrored `JevCriterion` structures; run source CI with the worktree on `PYTHONPATH` and package CI without it.

---

## 4. Requirements

### Functional Requirements

1. Export `Jev` as the Jev-enabled coordinator at `vidbyte`, `vidbyte.agents`, and `vidbyte.agents.jev`.
2. Export `JevAgent` as an immutable candidate profile with required `title`, `description`, `metadata`, and `agent` fields. `agent` is a configured `BaseAgent` template; candidates using the JEV runtime are rejected to prevent recursive routing.
3. Make `JevAgentSettings` contain only the candidate sequence. Normalize it to an immutable tuple and reject an empty collection, duplicate titles, invalid profile values, and more profiles than TypeSafe's Choice limit.
4. Move the existing decision model, preflight preset selection, and tool-selector threshold into immutable `JevRuntimeSettings`, accepted as the second typed configuration argument to `Jev` with defaults matching current behavior.
5. Run preflight before selecting a profile. If preflight closes the run, do not call the routing provider or a generative model.
6. With one candidate, skip the routing provider and use that candidate's configuration.
7. With multiple candidates, send one Choice question to TypeSafe. The named state includes only the current request and candidate profile data (`title`, `description`, and `metadata`); the Choice options map to unique candidate titles.
8. The question's `JevBrief` defines the task, named state, scope terms, single-/multi-action behavior, rules for using title/description/metadata, and a positive question. Choice criteria describe the configured candidates. Wording is stored in Markdown and loaded through `JevPrompts`.
9. Select the option with the highest returned probability rather than trusting a possibly inconsistent `answer.choice`. Preserve input order for exact ties. Do not apply a minimum probability threshold.
10. Record the selected title, its probability, and the ranked candidate probabilities on `Jev.response`; use no result-metadata field for the selection.
11. Before the inherited model loop starts, apply the selected template's supported execution configuration to the main `Jev`. Restore all changed fields in `finally`; do not copy candidate history, usage/speed trackers, active sessions, live MCP handles, or tracing infrastructure.
12. Serialize profile application and the run with a per-instance async lock so concurrent calls cannot observe another call's temporary provider, prompt, tool catalog, permissions, or metadata.
13. If the routing request fails or returns an invalid/missing answer, surface the typed provider/configuration error and do not silently select a different profile. If the selected agent run fails, propagate the error and restore configuration; do not replay through another candidate.
14. Preserve the current clarity and tool-selector features through `JevRuntimeSettings`; update tests, SDK docs, the Jev skill, public exports, and the focused verification script.

### Non-Functional Requirements

- The one-agent path makes zero routing-provider calls.
- The multi-agent path makes one routing-provider call per run, regardless of candidate count.
- Candidate count is capped at the TypeSafe Choice option maximum; routing state remains bounded by the shared Jev state cap.
- Profile metadata must be JSON-compatible and is sent to TypeSafe. Documentation must warn against putting secrets or unrelated private data in routing metadata.
- A temporary profile must never leak into a subsequent run, including after exceptions and cancellation.
- `Jev.response` is the source of routing observability; the selected profile probability is stored as a 0–1 value and described as a probability, not a guaranteed correctness score.

---

## 5. High-Level Design

`JevAgent` becomes a validated profile record that associates public routing information with a configured `BaseAgent` template. `JevAgentSettings` becomes the profile catalog. `JevRuntimeSettings` retains JEV decision configuration, preflight presets, and tool-selector configuration so the profile-only settings object does not remove existing behavior. The renamed `Jev` facade is initialized from the first validated profile and owns the run lock, response record, gate, and profile router. Since the clarity gate runs before selection, its clarification writer uses the first configured profile's generative model; a request that passes the gate is then routed and executed with the selected profile.

The run order is: normalize the current input; run preflight; if the gate passes, select the only profile directly or ask TypeSafe to choose among multiple profiles; snapshot the main agent's mutable execution configuration; apply the winning profile configuration; call the inherited `BaseAgent.generate_reply()` so runner construction, context, tracing, tools, and the normal model loop use the selected profile; then restore the snapshot in `finally`. The runtime receives the preflight result and keeps only existing run-level preflight/tool-selection mechanics; routing policy stays outside `JevRuntime` because it must run before BaseAgent resolves its runner.

```text
Jev.arun(request)
  -> JevPreflightGate
       -> closed: return gate result; no profile selection
       -> passed:
            one profile: select directly
            many profiles: one structured TypeSafe Choice -> max probability
            snapshot main execution config -> apply profile config
            BaseAgent.generate_reply() -> JevRuntime -> regular agent loop
            finally restore main execution config
```

This intentionally changes the unmerged PR API. `JevAgent` refers to a profile; `Jev` refers to the coordinator. Candidate objects remain templates, and the main `Jev` owns conversation history. Exact ties resolve by the candidate's original order. A routing-provider error or malformed response is visible to the caller rather than converted into an arbitrary selection.

---

## 6. Detailed Design

### 6.1 Candidate profile and catalog

**File(s):** `vidbyte/lib/dataclasses/jev.py`, `vidbyte/agents/jev/settings.py`, `vidbyte/lib/constants/jev.py`
**Type:** Modified

#### What it does

Moves the public role from `JevSpecialist` to `JevAgent` profile records, validates profile data and the profile catalog at construction, and keeps `JevAgentSettings` limited to the requested array.

#### Interface / API

```python
JevAgent(title: str, description: str, metadata: Mapping[str, JsonValue], agent: BaseAgent)
JevAgentSettings(agents: Sequence[JevAgent])
JevRuntimeSettings(decision: DecisionModelConfig, preflight: Sequence[JevPreflightPreset], tool_selector_threshold: float)
Jev(settings: JevAgentSettings, runtime_settings: JevRuntimeSettings | None = None)
```

`JevAgent` and `JevAgentSettings` are frozen typed records. `JevRuntimeSettings` has defaults matching the present JEV behavior. The `BaseAgent` reference is type-only in `vidbyte.lib`; runtime validation checks the `AgentRuntimeType` and the callable surface used by profile application without importing `vidbyte.agents` at runtime.

#### Logic / Algorithm

1. Validate trimmed non-empty titles and descriptions; require title uniqueness because title is the stable Choice option key.
2. Freeze and validate metadata as JSON mapping data.
3. Require a configured, non-JEV agent template; reject unsupported runtime types that cannot be represented by the JEV linear runtime.
4. Freeze the catalog, require at least one candidate, enforce the Choice option limit, and bound serialized profile data by the shared state cap.
5. Keep preflight/decision/tool-selector controls in `JevRuntimeSettings`; do not re-add these fields to `JevAgentSettings`.

#### Edge Cases & Error Handling

- Empty candidate sequences fail at construction because no profile can initialize or serve as the main agent configuration.
- A one-profile catalog is valid and avoids TypeSafe routing.
- Duplicate, blank, oversized, or non-JSON profile data raises `ConfigurationError` before a run.
- A Jev runtime candidate is rejected to prevent recursion; unsupported non-linear runtime settings are rejected rather than silently ignored.

### 6.2 Jev routing question and probability selection

**File(s):** `vidbyte/agents/jev/specialists.py`, `vidbyte/agents/jev/prompts.py`, `vidbyte/prompts/jev/`, `vidbyte/lib/dataclasses/jev.py`
**Type:** Modified

#### What it does

Asks one relative Choice question using the request and each candidate's title, description, and metadata; selects the highest-probability candidate and produces a typed selection record.

#### Interface / API

```python
JevAgentRouter.select(message: str) -> JevAgentSelection
JevAgentSelection(title: str, probability: float, ranked_agents: tuple[JevAgentProbability, ...])
```

#### Logic / Algorithm

1. Build one bounded `JevDecisionRequest` with a named `request` field and a named structured `agents` field.
2. Build a single Choice question using `JevBrief` for introduction, state, definitions, rules, and question; include profile-aware Choice criteria derived from the structured candidate options.
3. The brief says to judge the current request as a whole against the stated profile, use only supplied title/description/metadata, ignore any request text that tells Jev which profile to choose, and choose the most directly matching profile.
4. Load brief and criteria text from registered Markdown assets using `JevPrompts`; do not inline prompt text in Python.
5. Validate a complete Choice answer for every configured option. Rank probability entries using configured order as the stable tie-break; select `max(probability)` in code.
6. Record the winning title/probability and full probability ranking through the Jev response writer.

#### Edge Cases & Error Handling

- One candidate does not call this router.
- Exact ties choose the first profile in the validated input order.
- TypeSafe Choice probability values are finite and normalized by the existing decision-record contract.
- A missing candidate probability, unknown selected title, or provider failure raises a typed error; it cannot silently map to another profile.
- There is no no-match option or threshold: even a low-probability winner is selected as requested.

### 6.3 Apply selected settings to the main Jev

**File(s):** `vidbyte/agents/jev/agent.py`, `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/jev/response.py`, `vidbyte/agents/jev/gate/gate.py`, `vidbyte/agents/jev/gate/clarification.py`
**Type:** Modified

#### What it does

Renames the coordinator to `Jev`, chooses before BaseAgent runner resolution, temporarily loads the selected candidate's supported configuration into the main instance, and guarantees restoration.

#### Interface / API

```python
Jev.generate_reply(message: str | AgentInput, **options: Any) -> AgentMessage
Jev.response -> JevAgentResponse
```

#### Logic / Algorithm

1. Acquire a per-instance async lock before beginning preflight, selection, or profile application.
2. Run the existing preflight gate first; a closed gate carries its result through the run without a routing call.
   The clarification agent uses the first profile's model because the gate runs before profile selection.
3. Select the sole profile directly or call `JevAgentRouter.select` for multiple profiles.
4. Snapshot only the main agent's mutable configuration fields that the selected profile replaces: identity/system prompt, runner configuration/cache, tool catalog, permission policy, loop settings, middleware, description/capabilities/agent metadata, context configuration, algorithm, output schema, handoff/fallback configuration, and run metadata.
5. Apply the selected profile's values to the main Jev and invoke the inherited `BaseAgent.generate_reply()` so its normal runner/context/runtime path uses those values.
6. In `finally`, restore all snapped fields and release the lock. Keep the main Jev's conversation history, trackers, active session, trace implementation, and response object as coordinator-owned state; do not mutate the profile template.
7. Preserve `JevRuntime` as the linear execution seam and keep the existing tool selector behavior configured by `JevRuntimeSettings`.

#### Edge Cases & Error Handling

- Cancellation, model error, tool error, and schema-validation failure all restore the profile configuration.
- Concurrent calls on one Jev instance serialize; independent Jev instances remain independent.
- Profile execution failure is propagated without switching profiles.
- Candidate active MCP connections and session state are not copied; only supported reusable configuration is applied. If a profile depends on connected MCP state or its own session history, validation/documentation must reject or clearly describe that unsupported combination rather than sharing live handles.

### 6.4 Public API, docs, and package prompt assets

**File(s):** `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `vidbyte/agents/jev/README.md`, `skills/jev-agent/SKILL.md`, `vidbyte/prompts/jev/`
**Type:** Modified / Deleted / New prompt assets

#### What it does

Exports the new names consistently, documents profile construction and selection semantics, updates Jev implementation guidance, replaces the old specialist/no-match wording, and retains the tool-selector prompt asset.

#### Interface / API

```python
from vidbyte import Jev, JevAgent, JevAgentSettings, JevRuntimeSettings

profiles = JevAgentSettings(agents=(research_profile, coding_profile))
agent = Jev(profiles, runtime_settings=JevRuntimeSettings(...))
```

#### Logic / Algorithm

1. Export the new coordinator/profile/config/result classes at every existing SDK import surface.
2. Remove the unmerged `JevSpecialist` and `JevSpecialistRouting` public names and replace them with `JevAgent` and `JevAgentSelection`.
3. Update README and skill examples to show title, description, metadata, candidate agent, separate runtime settings, one-profile no-call behavior, and response confidence.
4. Keep all Jev question text in packaged Markdown under `vidbyte/prompts/jev/`; retain the current package-data glob.

#### Edge Cases & Error Handling

- Root and subpackage imports must resolve to the identical classes.
- Package build must include the new prompt assets.
- No compatibility alias may make `JevAgent` ambiguously refer to both the old coordinator and new profile type.

---

## 7. Data Model Changes

### 7.1 `JevAgent`

**Change type:** Modified (replaces the unmerged `JevSpecialist` record)

```python
@dataclass(frozen=True, slots=True)
class JevAgent:
    title: str
    description: str
    metadata: Mapping[str, JsonValue]
    agent: BaseAgent  # type-only reference; runtime validation follows the existing surface-check pattern
```

**Migration strategy:** No database migration. PR #461 is open and the profile type is not released. Update repository call sites and tests atomically; no deprecated alias is needed.

### 7.2 `JevAgentSelection` and candidate probabilities

**Change type:** New (replaces `JevSpecialistRouting`)

```python
@dataclass(frozen=True, slots=True)
class JevAgentProbability:
    title: str
    probability: float

@dataclass(frozen=True, slots=True)
class JevAgentSelection:
    title: str
    probability: float
    ranked_agents: tuple[JevAgentProbability, ...]
```

**Migration strategy:** Selection is in-memory response state only. No persistence or database changes.

### 7.3 `JevAgentSettings` and `JevRuntimeSettings`

**Change type:** Modified / New

`JevAgentSettings` contains only `agents: tuple[JevAgent, ...]` after normalization. New `JevRuntimeSettings` owns the decision config, existing preflight preset tuple, and tool-selector threshold.

**Migration strategy:** Update consumers to construct profile records and pass `JevRuntimeSettings` separately when configuring preflight or decision behavior. No released-version compatibility promise applies to this open PR.

---

## 8. API Changes

### 8.1 Python public SDK API

**Change type:** Modified / New / Removed (unreleased alpha API on an open PR)

**Request / construction:**

```python
JevAgent(title, description, metadata, agent)
JevAgentSettings(agents=(...))
JevRuntimeSettings(decision=..., preflight=..., tool_selector_threshold=...)
Jev(settings, runtime_settings=None)
```

**Response:**

`Jev.response.selection` is `None` for a one-profile run or a preflight-stopped run; for a multi-profile run it contains the selected title, selected option probability, and all candidate probabilities in stable rank order.

**Error cases:**

| Error | Condition |
|--------|-----------|
| `ConfigurationError` | Empty/invalid catalog, duplicate titles, unsupported candidate runtime, invalid profile metadata, or invalid runtime settings |
| Existing TypeSafe provider error | Routing call fails, is unavailable, or returns an invalid/missing answer |
| Existing agent execution error | Selected profile's normal agent run fails; settings are restored and no alternate candidate is tried |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-agent-profile-routing.md` | Record the approved architecture and test plan. |
| CREATE | `tests/features/jev-agent-profile-routing/FEATURE.md` | Keep the user-facing routing contract, failure inventory, and test map discoverable independently of implementation modules. |
| MODIFY | `vidbyte/agents/jev/agent.py` | Rename coordinator to `Jev`; prepare, apply, and restore selected configuration before BaseAgent execution. |
| MODIFY | `vidbyte/agents/jev/settings.py` | Reduce `JevAgentSettings` to profiles and introduce `JevRuntimeSettings`. |
| MODIFY | `vidbyte/agents/jev/specialists.py` | Replace specialist selection with one full-profile Choice router and code-side maximum probability selection. |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Consume the preflight result/settings from the renamed coordinator while retaining normal loop and tool selection. |
| MODIFY | `vidbyte/agents/jev/response.py` | Report selected profile and ranked probabilities on the response. |
| MODIFY | `vidbyte/agents/jev/gate/gate.py` | Read the new runtime settings while keeping preflight ahead of profile selection. |
| MODIFY | `vidbyte/agents/jev/gate/clarification.py` | Build the clarification writer from the first configured profile's model. |
| MODIFY | `vidbyte/agents/jev/prompts.py` | Replace old routing/no-match prompt registry entries while retaining the tool-selector prompt. |
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | Replace `JevSpecialist` / routing records with the profile and selection records. |
| MODIFY | `vidbyte/lib/constants/jev.py` | Replace specialist-only limits with profile catalog/state limits using shared TypeSafe bounds. |
| MODIFY | `vidbyte/lib/enums/jev.py` | Remove obsolete specialist fallback reasons if unused. |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Export `Jev`, profile, runtime settings, and selection records. |
| MODIFY | `vidbyte/agents/__init__.py` | Refresh the Jev public exports. |
| MODIFY | `vidbyte/__init__.py` | Refresh root SDK exports. |
| MODIFY | `vidbyte/agents/client.py` | Make `sdk.agents.jev(...)` construct the renamed coordinator and accept separate runtime settings. |
| MODIFY | `vidbyte/agents/base.py` | Refresh JEV coordinator references in its runtime documentation. |
| MODIFY | `vidbyte/agents/jev/README.md` | Explain candidate profiles and the routing lifecycle. |
| MODIFY | `skills/jev-agent/SKILL.md` | Update the Jev product/API contract and profile-routing invariants. |
| MODIFY | `skills/asking-jev-questions/SKILL.md` | Refresh coordinator naming in the Jev question-writing guidance. |
| MODIFY | `vidbyte/lib/jev/preflight/README.md` | Refer to the renamed coordinator without changing preflight ownership. |
| MODIFY | `vidbyte/prompts/README.md` | Refresh the clarification prompt description for the renamed coordinator. |
| MODIFY | `vidbyte/prompts/jev/specialist_question.md` | Rewrite as a complete profile-matching Choice brief. |
| DELETE | `vidbyte/prompts/jev/specialist_no_match.md` | There is no no-match option in the new always-pick-best policy. |
| MODIFY | `tests/test_jev_agent.py` | Cover new profile API, routing, probability selection, temporary settings, and errors. |
| MODIFY | `tests/test_jev_preflight.py` | Move preflight configuration to `JevRuntimeSettings` and retain gate-before-routing behavior. |
| MODIFY | `tests/test_jev_tool_selector.py` | Use the new coordinator and runtime settings without changing tool-selection semantics. |
| MODIFY | `scripts/test-jev-agent-scaffold.py` | Keep existing scaffold verification aligned with the renamed coordinator. |
| CREATE | `scripts/test-jev-agent-profile-routing.py` | Print PASS/FAIL for every profile-routing test and exit non-zero on any failure. |
| N/A | `pyproject.toml` | Existing `vidbyte.prompts` package-data glob already ships `jev/*.md` assets. |

---

## 10. Testing Plan

Every listed case will be covered by deterministic scripted TypeSafe responses and offline generative runners; no live provider call is required.

### Unit Tests

- `JevAgentSettings` rejects an empty catalog — [Edge Case].
- `JevAgentSettings` accepts one profile and freezes list input into an immutable tuple — [Edge Case].
- The catalog accepts exactly the TypeSafe Choice option maximum and rejects one more — [Edge Case].
- Profile title, description, metadata, and agent validation reject blank, duplicate, malformed, non-JSON, and recursive Jev profiles — [Hidden Assumption].
- Profile metadata serialization respects the shared state character limit rather than truncating fields — [Edge Case].
- A one-profile Jev execution never constructs or calls `DecisionModelRunner` — [Hidden Assumption].
- A multi-profile request contains the current input plus each profile's title, description, and metadata, and makes one TypeSafe call — [Silent Failure].
- Every generated routing question satisfies the JevBrief and JevCriterion layout and uses the Markdown-loaded prompt — [Hidden Assumption].
- A response whose declared `choice` disagrees with its option probabilities still selects the highest-probability option — [Silent Failure].
- Equal candidate probabilities choose the earliest configured profile — [Edge Case].
- A flat low-probability distribution still selects its maximum and does not silently reintroduce a threshold/no-match fallback — [Silent Failure].
- Missing option probability, unknown choice, malformed answer, and TypeSafe error are surfaced instead of running a random candidate — [Hidden Failure].
- Selected probability and all candidate scores appear on `Jev.response.selection`, not result metadata — [Silent Failure].
- The profile snapshot restores every changed configuration field after successful completion — [Hidden Failure].
- The profile snapshot restores every changed configuration field after exception and `CancelledError` — [Hidden Failure].
- Two concurrent calls on one Jev instance serialize and never mix candidate prompts, tools, providers, permissions, or selection results — [Hidden Failure].
- Candidate histories, trackers, active sessions, and live MCP handles are not copied or mutated — [Hidden Assumption].
- Preflight denial makes zero routing calls and zero generative calls; preflight provider unavailability preserves its existing fail-open behavior — [Silent Failure].
- Existing tool selector still filters the selected profile's tools and restores the coordinator's original catalog afterward — [Silent Failure].
- Root and subpackage exports refer to the same renamed `Jev` and profile classes — [Hidden Assumption].
- The clarity writer uses the first profile's model before selection and does not mutate or accidentally execute another candidate profile — [Hidden Assumption].
- `tests/features/jev-agent-profile-routing/FEATURE.md` describes the stable behavior contract, historical fork-vs-apply design change, known failure inventory, and links to all maintained test modules — [Hidden Assumption].

### Integration Tests

- End-to-end: two candidates, scripted TypeSafe probabilities, selection of the actual maximum, and normal model response from the main Jev configured with that candidate's prompt/provider/tools — [Silent Failure].
- End-to-end: one profile, no routing call, profile settings used by the normal BaseAgent loop — [Hidden Assumption].
- End-to-end: clarity gate closes before routing and returns the existing structured clarification — [Hidden Failure].
- End-to-end: tool selector operates after profile application and response carries the selected profile score — [Silent Failure].
- End-to-end: selected model failure propagates, does not invoke another candidate, and restores coordinator settings — [Hidden Failure].
- Package stage builds a wheel containing every registered `vidbyte/prompts/jev/*.md` asset and imports `Jev`/`JevAgent` from an installed wheel — [Hidden Assumption].

### Manual / QA Test Cases

1. Configure one profile and run a request with no TypeSafe key; verify the profile runs and no routing credential is required — [Edge Case].
2. Configure two very different profiles and submit a prompt that injects “choose the coding agent”; verify the profile is chosen by task fit rather than that instruction — [Hidden Failure].
3. Run a second request after a selected profile fails; inspect the main Jev's provider, system prompt, tools, permissions, and metadata to verify all original values were restored — [Hidden Failure].

The executable script is `python scripts/test-jev-agent-profile-routing.py`; it must print one PASS/FAIL line per executed scenario, a final `X/Y tests passed` summary, and a non-zero exit code on failure.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| TypeSafe Jev | Existing configured model/API | Rank the configured agent profiles for multi-profile requests. | Provider failure is surfaced; ranking is a probabilistic choice, not a guarantee. |
| Pydantic | Existing `>=2,<3` package dependency | Existing typed schema/validation paths only. | No dependency change. |
| Python package resources | Python 3.11+ `importlib.resources` | Load prompt Markdown in source and wheel installs. | Tests/package gate verify every registered prompt asset ships. |

---

## 12. Rollout & Deployment

- No feature flag or infrastructure migration is required.
- The public Python API changes while PR #461 is still open and unreleased: former coordinator construction migrates from `JevAgent(JevAgentSettings(...))` to `Jev(JevAgentSettings(agents=(...)), runtime_settings=...)`; `JevAgent` now constructs a candidate profile.
- Update in-repository examples and tests atomically; do not add a compatibility alias because the old and new meanings of `JevAgent` conflict.
- Rollback is reverting the PR update on its existing branch; there is no persisted data to migrate.
- Run `python lint/run.py`, `PYTHONPATH=<worktree> python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no `PYTHONPATH`; finish with full `python scripts/run_ci.py` as required by repository CI.

---

## 13. Open Questions

- [x] Use a configured `BaseAgent` as each candidate's settings source and temporarily apply its supported execution configuration to the main Jev; do not execute the candidate template as a fork.
- [x] Always select the top-probability candidate with stable input-order ties; do not add a threshold or no-match outcome. Surface decision failures.
- [x] Keep existing clarity and tool-selector features available through a separate `JevRuntimeSettings` object.
- [x] Use one Choice question rather than an independent Noul question per profile: candidate selection is relative, the returned distribution supports “best one,” and code performs the maximum selection.
- [ ] During implementation, verify the exact set of BaseAgent fields that can safely be applied without transferring live MCP/session/trace state; reject any unsupported candidate configuration rather than silently dropping it.

---

## 14. Alternatives Considered

### Alternative 1: Keep `JevSpecialist` and fork the selected profile

- What: Preserve the current router and call `specialist.agent.fork()` as PR #461 does today.
- Why rejected: The request explicitly says to rename the coordinator to `Jev`, pass a `JevAgent` array, and load the winning settings onto the main agent.

### Alternative 2: Ask one Noul question per profile and compare independent P(yes) scores

- What: Batch one absolute-fit Noul question per profile, then choose the largest independent probability.
- Why rejected: Independent Noul probabilities are not a normalized competition across candidates; a single Choice gives a relative distribution for the requested best-profile selection.

### Alternative 3: Apply candidate settings in `JevRuntime`

- What: Keep the current router inside `JevRuntime` and mutate settings after it picks a profile.
- Why rejected: `BaseAgent` resolves the runner and builds context before runtime execution, so the selected provider, prompt, and tools would be applied too late.

### Alternative 4: Retain a threshold and general-agent/no-match fallback

- What: Route only when the chosen confidence clears a minimum; otherwise use a generic agent.
- Why rejected: The user chose “always choose best” and the new catalog has no separate general-agent fallback.
