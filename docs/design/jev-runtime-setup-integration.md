# Design Doc: Jev Runtime Setup Integration

**Status:** Draft
**Author:** Codex
**Created:** 2026-10-01
**Last Updated:** 2026-10-01

---

## 1. Overview

Integrate Jev's request-time skill preload and tool alignment, run-state relationship, and bulk-work capabilities into one ordered runtime. The combined agent must preserve existing main-branch behavior and each capability's independent public contract while making preflight a single batched gate, selecting skills and tools before bounded workers start, and keeping caller context and runtime state isolated across runs.

---

## 2. Goals & Non-Goals

### Goals

- Integrate the three reviewed feature heads on top of the current Jev skill-preload core without losing core fields, checks, exports, or behavior.
- Run one combined preflight gate, passing the persistent `self.run_state.record` into it so `JevResponse.start()` cannot erase the record used for relation judgment.
- Reset relation and bulk gate flags on every pass and preserve closed-gate and specialist early returns.
- Keep alignment prompt and tool attachment before skill preload; run `run_state.begin`, tool selection, and bulk work after preload in that order.
- Create `JevRunStateRelation` when its preset is enabled even with no done checks, while creating `JevDoneContinuation` only when checks exist.
- Build the skill loader only when skills are configured; build the named bulk coordinator from validated `JevBulkSettings`.
- Preserve the caller's original main-loop message and immutable context; provide ordered per-item results as context data for final synthesis.
- Keep run-local prompt, tool, option, and MCP attachment cleanup in `finally`.
- Add cross-capability tests and retain the individual relation, bulk-work, skills-preload, and tool-alignment test packs.

### Non-Goals

- Do not add a generic runtime hook, strategy registry, callback API, or preset-specific branches to the main runtime beyond the narrow named capability seams.
- Do not change the main agent's conversation-history semantics, preflight question semantics, task planner schema, or public settings except where the three reviewed features already define them.
- Do not give the planner tools or native skills, or share the owner's native skill session/container with a worker.
- Do not implement bulk worker native-skill forwarding until the provider contract has its final review checkpoint. The approved narrow shape is recorded in §6.7 for later implementation.
- Do not push, merge component PRs into main, or publish the aggregate PR before the combined source review and required gates.

---

## 3. Background & Context

- The skills-preload core (`a357a4fa`) adds prompt/tool alignment, selected-skill context preload, and tool selection to `JevRuntime`. Its runtime currently runs the gate, alignment, preload, run-state, selector, then the inherited loop, with temporary prompt and tool state restored in `finally`.
- The run-state relationship feature (`4d19553b`) makes the preflight gate compare the current request with an existing typed run-state record. It adds an opt-in preset and `JevRunStateRelation`, including state initialization when done checks are absent.
- The bulk-work feature (`51be73f1`) adds three fixed recognition questions, validated `JevBulkSettings`, a tool-free planner, and bounded fresh-agent workers after tool selection. It records ordered results and feeds them to the main loop as context.
- All three features extend overlapping files: `JevAgent`, `JevRuntime`, gate, preflight registry, presets, enums, constants, response, exports, and preflight tests. A read-only three-way merge audit found expected conflicts at these seams; the integration must union their changes and preserve the current core behavior.
- `JevResponse.start()` resets the response record. Therefore the persistent record is read from `self.run_state.record` for the gate, not from a prior response's state result.
- Native provider skills are currently selected during the core preload. Each bulk worker will need the selected references and its own provider session/container; the provider feature is still in progress, so worker forwarding is deliberately a later integration step.

---

## 4. Requirements

### Functional Requirements

1. Merge relation and bulk public exports, central dataclasses, enums, presets, constants, question registrations, and response fields into the existing core without duplicates or deletions of core fields.
2. Start each call by resetting the response, then run exactly one combined gate with the current message and persistent run-state record. The gate resets both `run_state_related` and `bulk_work_requested` before evaluating answers.
3. Return immediately for a failed gate. For a selected specialist, call relation-aware `begin_delegated` and hand off before skill preload or bulk work.
4. For normal execution, perform prompt alignment, tool alignment/attachment, core skill preload (including explicit-system override handling), relation-aware state initialization, tool selector filtering, bulk planning/work, and then the inherited loop with the original message.
5. Keep bulk work opt-in. Its planner remains tool-free; invalid, unavailable, or oversized plans fall back to the ordinary loop without truncating requested work.
6. Give each worker the selected tool set using the established `clone_for_fork()` contract, preserving selected tool names while isolating `AgentTool` contexts. Restore owner prompt, user tools, full tools, and attached MCP resources in `finally`.
7. Keep task results ordered and typed, retain failures without leaking raw exception text, and ensure the final-synthesis context identifies failures as failures. Do not mutate the caller's context or replace the original request sent to the main loop.
8. Create the relation facade whenever its preset is enabled; create continuation only when done checks are configured. With the relation preset disabled, preserve the existing per-run run-state behavior.
9. Build the skill loader only when skills are nonempty. Preserve the explicit provider `system` override as the baseline before selected skill text is appended.
10. After provider native-skill contracts receive final review, add the narrow typed `claude_skills` argument to bulk planning and pass selected references to each fresh worker. The planner receives none, and workers get independent provider sessions/containers. This requirement is pending that checkpoint and is not part of the relation/bulk merge stage.
11. Preserve all current done-check behavior and response data, and ensure repeated runs do not reuse stale relation/bulk flags or prior temporary runtime state.

### Non-Functional Requirements

- Disabled capabilities add no model calls; all three preflight concerns share the existing single decision request.
- Worker count remains bounded by `min(max_parallel_agents, item_count)` and uses a bounded queue rather than one task per planned item.
- Errors from individual workers are retained as safe typed failures; cancellation propagates and cleans up sibling workers.
- Selected tools and provider skill references are not broadened beyond those selected for the owner.
- Preserve immutable `BaseAgentContext` values and existing usage rollup ownership.
- Pass the repository's custom lint, source tests, full CI, and all four focused feature packs on the combined, tracked source tree.

---

## 5. High-Level Design

The integration keeps the gate as the first decision seam. The runtime resets `JevResponse`, then passes the current message and `self.run_state.record` to one `JevPreflightGate.pass_` call. Relation and bulk flags are gate-owned and reset every pass. A stopped request exits; a selected specialist uses `begin_delegated` and returns before alignment, preload, or workers.

For an ordinary run, the runtime attaches any aligned tools before core skill preload, then initializes relation-aware run state, applies the existing tool selector, and only then invokes the named bulk coordinator. If the gate did not enable bulk or its planner cannot produce a valid bounded plan, the ordinary inherited loop continues. Otherwise the coordinator adds an immutable result artifact to a replacement context, and the inherited loop still receives the exact original user message for final synthesis.

The integration merges feature-owned types and registrations as a union. It changes only the small shared runtime seams and adds tests for behavior that can fail specifically at their intersection. Native skill forwarding remains pending provider contract review; when approved, only selected references are passed to fresh worker runs, with no session sharing and no native skills on the planner.

```text
response reset -> one gate(message, persistent record)
                     | closed -> stopped
                     | specialist -> begin_delegated -> handoff
                     v
prompt alignment -> tool attachment -> skill preload
  -> run_state.begin -> tool selector -> bounded bulk coordinator
  -> inherited loop(original message) -> response outcome
  -> finally restore runtime fields and release attachments
```

---

## 6. Detailed Design

### 6.1 Combined Preflight and Persistent Run-State Input

**File(s):** `vidbyte/agents/jev/gate/gate.py`, `vidbyte/lib/jev/preflight/preflight.py`, `vidbyte/lib/jev/preflight/run_state_relation.py`, `vidbyte/lib/jev/preflight/bulk_work.py`
**Type:** New and modified files

#### What it does

Unifies fixed relation and bulk questions with existing preflight questions in the gate's single request. The relation question is included only when the relation preset is active and a record exists. Bulk has three independent recognition judgments; all must be confidently positive before the gate sets its request flag.

#### Interface / API

```python
async def pass_(self, message: str, run_state: JevRunStateRecord | None = None) -> bool: ...
```

`JevRuntime` calls this with `None` or the persistent `self.run_state.record`. The gate owns `run_state_related: bool | None` and `bulk_work_requested: bool`; both reset before each pass.

#### Logic / Algorithm

1. Reset specialist selection, relation state, and bulk eligibility.
2. Build one combined decision request from enabled questions. Include relation state only when a record exists; exclude usage accounting from its JSON-safe projection.
3. Score relation and each bulk question using the registered preset rules. An unavailable relation answer leaves relation state unset; any missing, uncertain, or vetoed bulk answer leaves bulk disabled.
4. Preserve current specialist handling and fail-open gate behavior. Do not add runtime preset checks.

#### Edge Cases & Error Handling

- `JevResponse.start()` may clear response fields; the persistent run-state facade remains the source of the old record.
- With no record, omit the relation question and result.
- Any bulk question that indicates dependencies, or whose independence is unclear, blocks fan-out.
- Missing answers or decision failures never leave stale positive flags from an earlier run.

### 6.2 Facade Construction and Run-State Continuation

**File(s):** `vidbyte/agents/jev/agent.py`, `vidbyte/agents/jev/done/relation.py`, `vidbyte/agents/jev/done/__init__.py`
**Type:** New and modified files

#### What it does

Builds `JevRunStateRelation` for the relation preset even when continual checks are empty, while keeping continuation conditional on actual checks. It constructs the bulk coordinator from the named validated settings and the skills preloader only for a nonempty skill collection.

#### Interface / API

```python
class JevRunStateRelation(JevRunState):
    async def begin(self, request: str) -> None: ...

class JevBulkWork(BaseAgent):
    async def plan_and_run(self, message: str, context: BaseAgentContext, tools: tuple[object, ...], *, claude_skills: tuple[ClaudeSkillReference, ...] = ()) -> JevBulkWorkResult: ...
```

`claude_skills` is the approved future narrow extension and is deferred until provider contracts are final. The relation facade's `begin_delegated` follows the relation policy before specialist handoff.

#### Logic / Algorithm

1. Select `JevRunStateRelation` only when the relation preset is enabled; otherwise retain normal run-state construction.
2. Build continuation only when done checks are nonempty.
3. Build the bulk coordinator from `JevAgentSettings.bulk_work`; it performs no planning unless the gate flag is true.
4. Build the existing core skill preloader only when configured skills are present.

#### Edge Cases & Error Handling

- Relation enabled without done checks still initializes/retains a record without creating a continuation.
- Specialist execution bypasses the owner’s skills and bulk phases but records the relation-aware delegated state.
- Avoid duplicate construction or alternate public configuration paths when the feature heads are merged.

### 6.3 Runtime Phase Order and Cleanup

**File(s):** `vidbyte/agents/jev/runtime.py`
**Type:** Modified file

#### What it does

Combines the three capabilities in the approved order and retains run-local cleanup around all normal-run phases.

#### Interface / API

```python
async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...
```

#### Logic / Algorithm

1. Reset the response and call the combined gate with the persistent run-state record.
2. Stop on a closed gate. If a specialist is selected, call `begin_delegated` and hand off before alignment/preload/bulk.
3. Save owner system prompt, user tool catalog, and full tool catalog; keep run options as immutable per-call values.
4. Apply prompt alignment, then tool alignment/attachment and update context/tool specs.
5. Run core `_preload_skills`, including preserving an explicit `options['system']` baseline and appending selected skill text to the effective context.
6. Call `run_state.begin(message)`, then existing core `_select_tools` so workers see only selected tools.
7. If the bulk gate flag is true, call the named coordinator and add its typed result as immutable context data. Keep the message passed to `super().arun` unchanged.
8. Handle attachment announcement, selector metadata, and normal response outcome.
9. In `finally`, restore prompt and user/full tool catalogs, then release any attached MCP resources.

#### Edge Cases & Error Handling

- A tool selector that filters a tool must not have that tool reintroduced for workers.
- Gate, specialist, and invalid-plan paths must avoid an extra bulk planner/worker call as specified by each feature.
- Exceptions and cancellation still execute cleanup; cancellation is not converted into an item failure.
- Preserve existing continuation/done-check execution in the inherited loop.

### 6.4 Bounded Bulk Workers and Tool Isolation

**File(s):** `vidbyte/agents/jev/bulk_work.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/agents/jev/response.py`
**Type:** New and modified files

#### What it does

Uses the approved bounded planner/worker flow after selector filtering, records typed ordered results, and exposes a single response writer. Each fresh worker gets exactly the owner's effective selected tools, cloned through the existing `clone_for_fork()` hook when available, plus the owner's effective model and permission policy.

#### Interface / API

```python
async def plan_and_run(self, message: str, context: BaseAgentContext, tools: tuple[object, ...], *, claude_skills: tuple[ClaudeSkillReference, ...] = ()) -> JevBulkWorkResult: ...

def bulk_work(self, result: JevBulkWorkResult) -> None: ...
```

The native-skill parameter is deferred pending the provider contract checkpoint. No generic worker callback or options factory is introduced.

#### Logic / Algorithm

1. Generate and validate the whole plan; require at least two tasks and no more than configured `max_items`. Invalid plans are rejected whole, never truncated.
2. Do not expose tools or native skills to the planner. Use a bounded queue with at most `min(max_parallel_agents, item_count)` worker coroutines.
3. Give every worker isolated history and a trusted item-only instruction. Clone bound tools via `clone_for_fork()` to isolate agent tool context while preserving names.
4. Collect outputs/failures by original task index. Catch ordinary per-item exceptions into safe typed failures; let cancellation escape and clean siblings up.
5. Record planner and worker usage only through their existing owned rollups. Add a result artifact to a replacement context for the inherited loop; synthesis instructions must not treat failures as successes.

#### Edge Cases & Error Handling

- Never leak raw `str(exc)` or `repr(exc)` into public output; use a safe error code/type or stable generic message.
- Tool wrappers without the approved clone hook must be surfaced as a concrete integration issue; do not redesign the global forker.
- Arbitrary custom mutable stateless tools retain the existing fork contract and may be shared by identity.
- No shared mutable context, worker history, or result ordering depends on task completion order.

### 6.5 Public Types, Presets, Response, and Exports

**File(s):** `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/response.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `vidbyte/lib/constants/jev.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/enums/jev.py`, `vidbyte/lib/enums/prompts.py`, `vidbyte/lib/jev/preflight/__init__.py`, `vidbyte/lib/jev/presets.py`
**Type:** Modified files

#### What it does

Preserves the union of existing core types and feature types, including validated bulk settings/results, the relation preset and outcome flag, all response fields, skill and alignment settings, and tool-selector configuration. Every public closed status/rejection vocabulary remains a central enum; dataclasses remain in `vidbyte/lib/dataclasses`.

#### Interface / API

```python
JevAgentSettings.bulk_work: JevBulkSettings
JevAgentResponse.bulk_work: JevBulkWorkResult | None
JevPreflightPreset.RUN_STATE_RELATION: str
JevPreflightPreset.BULK_WORK: str
```

#### Logic / Algorithm

1. Merge exports and central registries as a union, preserving all skills-core exports, settings, response fields, tool-alignment presets, and done-check types.
2. Register both new presets alongside the current core presets without duplicate enum or mapping keys.
3. Keep feature result status fields typed through central enums and preserve the sole response writer contract.

#### Edge Cases & Error Handling

- Resolve overlapping edits by retaining both features' registrations and all current core behavior; no feature branch's deletions replace core additions.
- Do not move dataclasses into `agents` or private coordinator modules.
- Keep package exports importable without initializing runtime providers.

### 6.6 Prompt Assets and Focused Feature Packs

**File(s):** `vidbyte/lib/jev/preflight/README.md`, `vidbyte/prompts/README.md`, `vidbyte/prompts/prompts/jev_bulk_work/jev_bulk_work.json`, `vidbyte/prompts/prompts/jev_bulk_work/synthesis_prompt.md`, `vidbyte/prompts/prompts/jev_bulk_work/system_prompt.md`, `vidbyte/prompts/prompts/jev_bulk_work/worker_system_prompt.md`, `tests/test_jev_preflight.py`, `tests/test_jev_run_state_relation.py`, `tests/features/jev_bulk_work/FEATURE.md`, `tests/features/jev_bulk_work/README.md`, `tests/features/jev_bulk_work/test_jev_bulk_work.py`, `scripts/test-jev-bulk-work.py`, `scripts/test-jev-run-state-relation.py`
**Type:** New and modified files

#### What it does

Retains each fixed question and named prompt asset and adds cross-capability tests that exercise the merged runtime as a whole.

#### Interface / API

```python
async def test_combined_gate_receives_persistent_run_state_and_resets_flags() -> None: ...
async def test_selector_precedes_bulk_and_workers_receive_only_selected_tools() -> None: ...
async def test_bulk_result_artifact_preserves_original_message_and_failure_status() -> None: ...
async def test_repeated_run_restores_prompt_tools_and_mcp_attachment() -> None: ...
```

#### Logic / Algorithm

1. Keep the existing relation, bulk, skill-preload, and tool-alignment feature tests intact.
2. Add integration coverage for one combined gate and persistent old record; relation retain/replace behavior; selector-before-bulk ordering; skill text/options; ordered partial failures; unchanged main message; repeated-run reset; and cleanup.
3. After provider contracts are finalized, cover independent native sessions, exact selected skill reference/text forwarding to workers, and no native skills on the planner.

#### Edge Cases & Error Handling

- Use provider/runner stubs for deterministic tests; no live TypeSafe or provider call is required.
- Test context creation through actual `BaseAgent` context-building behavior where prompt precedence is relevant.
- Focused feature scripts run independently, then normal custom lint/source/full CI gates cover the merged branch.

### 6.7 Deferred Provider-Native Skill Forwarding

**File(s):** `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/jev/bulk_work.py`, `vidbyte/agents/jev/alignment/skills.py`, `tests/test_jev_runtime_setup_integration.py`
**Type:** Deferred modification after provider contract checkpoint

#### What it does

Records the approved narrow integration between selected provider-native skill references and bulk workers. This section does not authorize implementation before the provider contract is final.

#### Interface / API

```python
await bulk.plan_and_run(message, context, claude_skills=selected_claude_skill_references)
```

#### Logic / Algorithm

1. Pass only selected native references from the completed core preload outcome to each new worker through its named run option.
2. Let each worker create its own native session/container; never pass the owner's `ClaudeSkillSession` or container identifier.
3. Keep the planner tool-free and native-skill-free.
4. Preserve selected skill text, tool catalog, owner options, and trusted synthesis instructions; append the synthesis instruction once while respecting explicit `options['system']` overrides.

#### Edge Cases & Error Handling

- Exact provider option serialization and worker lifecycle depend on the provider feature's final typed contract.
- Do not add generic callbacks, factories, or runtime strategy surfaces to accommodate provider variation.
- The combined feature cannot be signed off until provider-specific forwarding tests pass against the final contracts.

---

## 7. Data Model Changes

No database or persisted storage schema changes.

The public in-memory model is the union of existing core records and the reviewed relation/bulk types. `JevAgentSettings` gains the existing named `JevBulkSettings` field; `JevAgentResponse` gains `bulk_work: JevBulkWorkResult | None`; relation outcomes remain in the existing preflight result map. Per-item statuses/errors use the central Jev enums and dataclasses. No native provider session object is placed in public response records.

---

## 8. API Changes

### 8.1 JevAgent configuration and response

**Change type:** Modified

**Request:**

```python
JevAgentSettings(
    bulk_work=JevBulkSettings(max_parallel_agents=4, max_items=32),
)
JevRuntimeSettings(
    preflight=(JevPreflightPreset.RUN_STATE_RELATION, JevPreflightPreset.BULK_WORK),
)
```

**Response:**

```python
JevAgentResponse(
    results=...,        # includes relation and existing preflight outcomes
    run_state=...,      # retained or replaced record
    alignment=...,      # existing prompt alignment outcome
    skills=...,         # existing skill preload outcome
    tool_alignment=..., # existing core tool attachment outcome
    bulk_work=...,      # ordered typed planner/worker outcome or None
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid bulk limits fail construction with `ConfigurationError`. |
| N/A | Invalid planner output is represented as a typed rejected plan and follows the serial loop. |
| N/A | Worker exceptions are represented as safe per-item failures; cancellation propagates. |

### 8.2 Preflight gate

**Change type:** Modified internal API

**Request:**

```python
await gate.pass_(message, run_state=current_persistent_record)
```

**Response:**

One boolean gate outcome, with gate-owned specialist, relation, and bulk decisions and response-owned typed preflight results.

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing answers or typed decision failures follow existing fail-open behavior and leave bulk disabled. |
| N/A | Relation evaluation is omitted when no prior record exists. |

---

## 9. File Change Manifest

The current core head already contains skill preload and tool alignment. The relation and bulk rows below are the union to be integrated; `tests/test_jev_runtime_setup_integration.py` is added for cross-feature contracts. Native worker forwarding rows are deferred until provider contract review.

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-runtime-setup-integration.md` | Record the combined architecture and gated implementation plan. |
| CREATE | `docs/design/jev-run-state-relation.md` | Preserve the relation feature design. |
| CREATE | `docs/design/jev-bulk-work.md` | Preserve the bulk feature design. |
| CREATE | `vidbyte/agents/jev/done/relation.py` | Add relation-aware run-state facade. |
| CREATE | `vidbyte/agents/jev/bulk_work.py` | Add bounded planner and worker coordinator. |
| CREATE | `vidbyte/lib/jev/preflight/run_state_relation.py` | Define fixed relation question. |
| CREATE | `vidbyte/lib/jev/preflight/bulk_work.py` | Define three fixed bulk questions. |
| CREATE | `scripts/test-jev-run-state-relation.py` | Add executable relation verification pack. |
| CREATE | `scripts/test-jev-bulk-work.py` | Add executable bulk verification pack. |
| CREATE | `scripts/test-jev-runtime-setup-integration.py` | Add an executable combined runtime verification pack. |
| CREATE | `tests/test_jev_run_state_relation.py` | Test relation state lifecycle and gate cases. |
| CREATE | `tests/test_jev_runtime_setup_integration.py` | Test combined runtime ordering, old-record input, context, tools, and cleanup. |
| CREATE | `tests/features/jev_bulk_work/FEATURE.md` | Document the bulk feature test scope. |
| CREATE | `tests/features/jev_bulk_work/README.md` | Document focused bulk verification. |
| CREATE | `tests/features/jev_bulk_work/test_jev_bulk_work.py` | Test planner, queue, workers, result ordering, and failure handling. |
| CREATE | `vidbyte/prompts/prompts/jev_bulk_work/jev_bulk_work.json` | Register named bulk prompts. |
| CREATE | `vidbyte/prompts/prompts/jev_bulk_work/synthesis_prompt.md` | Supply trusted final synthesis instructions. |
| CREATE | `vidbyte/prompts/prompts/jev_bulk_work/system_prompt.md` | Supply tool-free planner system instructions. |
| CREATE | `vidbyte/prompts/prompts/jev_bulk_work/worker_system_prompt.md` | Scope workers to their assigned item. |
| MODIFY | `vidbyte/agents/jev/agent.py` | Union facade construction and named capability wiring. |
| MODIFY | `vidbyte/agents/jev/done/__init__.py` | Export relation facade. |
| MODIFY | `vidbyte/agents/jev/done/run_state.py` | Preserve the existing generator behavior and relation-aware state lifecycle seam. |
| MODIFY | `vidbyte/agents/jev/gate/gate.py` | Accept persistent record and reset/score both feature flags. |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Apply ordered phases and combined cleanup. |
| MODIFY | `vidbyte/agents/jev/response.py` | Preserve core response fields and add bulk result writer. |
| MODIFY | `vidbyte/agents/jev/README.md` | Document the opt-in bulk-work capability. |
| MODIFY | `vidbyte/agents/jev/settings.py` | Add named bulk settings while preserving core settings. |
| MODIFY | `vidbyte/lib/constants/jev.py` | Add relation threshold/constants without removing core values. |
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | Add centrally placed bulk result and plan records. |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export new Jev enums. |
| MODIFY | `vidbyte/lib/enums/jev.py` | Union relation/bulk preset, question, and result enums. |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add named bulk prompt keys. |
| MODIFY | `vidbyte/lib/jev/preflight/README.md` | Document registered relation and bulk questions. |
| MODIFY | `vidbyte/lib/jev/preflight/__init__.py` | Export relation/bulk question types. |
| MODIFY | `vidbyte/lib/jev/preflight/preflight.py` | Register both question groups without duplicate map entries. |
| MODIFY | `vidbyte/lib/jev/presets.py` | Union both fixed presets with existing core presets. |
| MODIFY | `vidbyte/prompts/README.md` | Document prompt asset registration. |
| MODIFY | `tests/test_jev_preflight.py` | Preserve core tests and cover batched relation/bulk gate semantics. |
| MODIFY | `vidbyte/__init__.py` | Preserve core exports and expose bulk settings. |
| MODIFY | `vidbyte/agents/__init__.py` | Preserve core exports and expose bulk settings. |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Expose named bulk settings. |

No files are deleted. Provider-specific edits are intentionally absent until their contract checkpoint.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_jev_preflight.py` -> one gate request contains enabled relation, bulk, specialist, and existing fixed questions; relation receives the persistent old record; both flags reset on repeated passes; absent record omits relation; a single negative or uncertain bulk answer disables fan-out.
- `tests/test_jev_run_state_relation.py` -> retain related/unavailable records, replace unrelated records, initialize with no record, initialize without done checks, and handle delegated specialist state.
- `tests/features/jev_bulk_work/test_jev_bulk_work.py` -> validate planner bounds without truncation, bounded concurrency, stable result order, safe partial failures, cancellation cleanup, original request preservation, and result artifact visibility.
- Core skill preload tests -> selected skill text and explicit system overrides survive the merged runtime and reach a real context-building provider stub.
- Core tool alignment and selector tests -> attached tools are available to selection and workers receive exactly the selector's effective set.
- New integration test file -> assert `response.start` precedes gate but gate uses `self.run_state.record`; runtime phase order; specialist bypass; selected-skill/tool context precedes bulk; inherited loop receives unchanged message; repeated-run cleanup restores prompt/tools and releases MCP attachment.
- After provider checkpoint, integration tests -> exact selected `ClaudeSkillReference` forwarding, independent worker sessions/containers, planner receives none, and system synthesis instruction is appended once while honoring explicit overrides.

### Integration Tests

- Run all four focused packs: skill preload, tool alignment, run-state relation, and bulk work.
- Run the new combined runtime setup pack with deterministic stubs for decision, generation, provider context construction, and MCP attachment release.
- Run repository source tests and full CI after all merged/new files are staged and tracked so custom lint sees the complete tree.

### Manual / QA Test Cases

1. Given a related request and existing run-state record with both relation and bulk presets enabled, when the gate and normal runtime run, then the same record is available to relation judging, all preflight questions share one gate call, and eligible bulk results reach final synthesis.
2. Given a selector that removes one candidate tool, when independent tasks fan out, then no worker receives the removed tool and each agent-bound clone has an isolated context.
3. Given a worker failure among successful sibling tasks, when final synthesis runs, then order is preserved and the failure remains explicitly represented as a failure.
4. Given two calls on one JevAgent, when the second gate, alignment, and bulk phases run, then flags, prompt/tools, context artifacts, and MCP attachment state contain no stale first-run values.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing Jev `DecisionModelHelper` / TypeSafe client | Current SDK configuration | Combined fixed-question decision request | Provider failure follows existing fail-open gate policy. |
| Existing `BaseAgent` / `AgentTool.clone_for_fork()` | Current SDK runtime contract | Fresh bounded workers with selected tools | Custom mutable tools without clone hooks follow existing fork sharing semantics. |
| Skills-preload provider adapter | Final contract pending | Select and attach native skill references | Worker forwarding is gated until typed contract review. |
| Existing MCP alignment attachment | Current SDK runtime contract | Attach selected tools for the run | Must be released in `finally`, including errors and cancellation. |

No new external service or package is introduced.

---

## 12. Rollout & Deployment

- Both new preflight presets and configured skills are opt-in; defaults retain current behavior and do not add capability model calls.
- This is an additive SDK API change; no persistent migration is required.
- Merge only into the isolated integration branch. Do not merge component PRs into main as part of this task.
- Required order: commit this design document, merge reviewed relation and bulk feature heads into the core-based integration branch, resolve union conflicts, wait for provider contract checkpoint before native forwarding, then run focused tests, custom lint, source tests, and full CI.
- Prepare a separate aggregate draft PR only after parent reviews the combined diff and required gates pass. Keep component PRs and main untouched.
- Rollback consists of discarding the isolated integration branch; no data or external service changes are made.

---

## 13. Open Questions

- [ ] Provider feature owner to confirm the final typed selected-skill reference and fresh worker session/container lifecycle contract before native skill forwarding is implemented.
- [ ] Parent review must approve the combined source diff and gate results before an aggregate draft PR is created.

---

## 14. Alternatives Considered

### Alternative 1: Keep the capabilities in separate runtime phases without integration tests

- What: Merge component code and rely only on each feature's independent test pack.
- Why rejected: Overlapping gate, response reset, context, tools, and cleanup seams can regress even when the independent packs pass.

### Alternative 2: Add a generic runtime extension/strategy registry

- What: Register arbitrary setup callbacks and use them to order alignment, preload, state, selection, and bulk work.
- Why rejected: The capabilities have a fixed Jev-owned order and typed contracts; a generic hook would widen the public and maintenance surface without a current consumer.

### Alternative 3: Reuse the owner agent or owner native provider session for bulk items

- What: Run planner and work items through the main agent or share its provider container/session.
- Why rejected: This couples task histories and native state, risks stale context and selector bypass, and defeats fresh isolated worker semantics.

### Alternative 4: Merge feature snapshots by taking one branch's complete files

- What: Resolve textual conflicts by accepting the relation or bulk copy of shared runtime files.
- Why rejected: Both branches were based on a common earlier revision; either snapshot would drop core skill-preload/tool-alignment work or the other feature's registrations. The merge must preserve the explicit union.
