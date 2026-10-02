# Design Doc: Jev Runtime Setup Integration

**Status:** Draft
**Author:** Codex
**Created:** 2026-10-01
**Last Updated:** 2026-10-02

---

## 1. Overview

Integrate Jev's request-time skill preload and tool alignment, run-state relationship, bulk work, explicit skill sources, and Claude-native skill sessions into one ordered runtime. The combined agent must preserve existing behavior and each capability's public contract while making preflight a single batched gate, selecting skills and tools before bounded workers start, isolating worker histories and provider containers, and keeping caller context and runtime state isolated across runs.

---

## 2. Goals & Non-Goals

### Goals

- Integrate the relation, bulk-work, and provider-skill heads on top of the current Jev skill-preload core without losing core fields, checks, exports, or behavior.
- Run one combined preflight gate, passing the persistent `self.run_state.record` into it so `JevResponse.start()` cannot erase the record used for relation judgment.
- Reset relation and bulk gate flags on every pass and preserve closed-gate and specialist early returns.
- Keep alignment prompt and tool attachment before skill preload; run `run_state.begin`, tool selection, and bulk work after preload in that order.
- Create `JevRunStateRelation` when its preset is enabled even with no done checks, while creating `JevDoneContinuation` only when checks exist.
- Build the skill loader only when skills are configured; build the named bulk coordinator from validated `JevBulkSettings`.
- Resolve explicitly configured skill sources at run time; keep selected native Claude references separate from selected text and attach them only to Anthropic requests.
- Continue valid Anthropic `pause_turn` responses through the inherited bounded runtime and record each response's raw usage once.
- Preserve the caller's original main-loop message and immutable context; provide ordered per-item results as context data for final synthesis.
- Pass selected native skill references to each fresh bulk worker without forwarding the owner session/container; each worker owns its own provider session.
- Keep run-local prompt, tool, option, and MCP attachment cleanup in `finally`.
- Add cross-capability tests and retain the individual relation, bulk-work, skills-preload, and tool-alignment test packs.

### Non-Goals

- Do not add a generic runtime hook, strategy registry, callback API, or preset-specific branches to the main runtime beyond the narrow named capability seams.
- Do not change the main agent's conversation-history semantics, preflight question semantics, task planner schema, or public settings except where the reviewed feature contracts already define them.
- Do not give the planner tools or native skills, or share the owner's native skill session/container with a worker.
- Do not push, merge component PRs into main, or publish the aggregate PR before the combined source review and required gates.

---

## 3. Background & Context

- The skills-preload core (`a357a4fa`) adds prompt/tool alignment, selected-skill context preload, and tool selection to `JevRuntime`. Its runtime currently runs the gate, alignment, preload, run-state, selector, then the inherited loop, with temporary prompt and tool state restored in `finally`.
- The run-state relationship feature (`4d19553b`) makes the preflight gate compare the current request with an existing typed run-state record. It adds an opt-in preset and `JevRunStateRelation`, including state initialization when done checks are absent.
- The bulk-work feature (`51be73f1`) adds three fixed recognition questions, validated `JevBulkSettings`, a tool-free planner, and bounded fresh-agent workers after tool selection. It records ordered results and feeds them to the main loop as context.
- The provider-skill feature (`40f20e32`) adds explicit source resolution, metadata-only Claude skill references, typed per-call native options, and bounded pause continuation through `AgentRuntime`.
- Relation, bulk, and provider-skill heads extend overlapping files: `JevAgent`, `JevRuntime`, preload, runtime, dataclasses, enums, exports, and provider contracts. Preserve their additions together with current core behavior.
- `JevResponse.start()` resets the response record. Therefore the persistent record is read from `self.run_state.record` for the gate, not from a prior response's state result.
- The provider preload outcome carries the selected native references. Bulk forwarding must use only that selected tuple, while each fresh worker starts with `claude_skill_session=None` and owns its container independently of the main agent.
- `ClaudeSkillSession.resume_messages` captures the provider-visible request plus the complete assistant response content, so continuation can preserve server-tool blocks and avoid re-appending the user's original message.

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
9. Resolve configured skill sources only during preload; keep selection indices and outcomes stable, append selected text to the effective prompt, and retain selected Claude references in the typed skill outcome.
10. Extend bulk planning with `claude_skills: tuple[ClaudeSkillReference, ...] = ()`. Pass only the selected outcome references to each worker; give the planner no tools or native refs and each worker a fresh session (`None`) so it creates an independent container.
11. Let the inherited runtime resume valid Anthropic pause turns from the exact raw assistant content and existing container ID, after usage accounting and response middleware but before local tool parsing.
12. Preserve all current done-check behavior and response data, ensure repeated runs do not reuse stale relation/bulk flags or provider sessions, and keep the main owner's Claude session separate from all worker sessions.

### Non-Functional Requirements

- Disabled capabilities add no model calls; all three preflight concerns share the existing single decision request.
- Worker count remains bounded by `min(max_parallel_agents, item_count)` and uses a bounded queue rather than one task per planned item.
- Errors from individual workers are retained as safe typed failures; cancellation propagates and cleans up sibling workers.
- Selected tools and provider skill references are not broadened beyond those selected for the owner.
- Each bulk worker receives the same selected native reference tuple but no owner session/container; each child pause/resume remains within that worker's own bounded runtime.
- Preserve immutable `BaseAgentContext` values and existing usage rollup ownership.
- Pass the repository's custom lint, source tests, full CI, and all four focused feature packs on the combined, tracked source tree.

---

## 5. High-Level Design

The integration keeps the gate as the first decision seam. The runtime resets `JevResponse`, then passes the current message and `self.run_state.record` to one `JevPreflightGate.pass_` call. Relation and bulk flags are gate-owned and reset every pass. A stopped request exits; a selected specialist uses `begin_delegated` and returns before alignment, preload, or workers.

For an ordinary run, the runtime attaches any aligned tools before core skill preload, then initializes relation-aware run state, applies the existing tool selector, and only then invokes the named bulk coordinator. If the gate did not enable bulk or its planner cannot produce a valid bounded plan, the ordinary inherited loop continues. Otherwise the coordinator adds an immutable result artifact to a replacement context, and the inherited loop still receives the exact original user message for final synthesis.

The integration merges feature-owned types and registrations as a union. It changes only the shared runtime seams and adds tests for behavior that can fail specifically at their intersection. Skill preload places the selected native-reference tuple in the request-local main options. The bulk coordinator separately receives that tuple, sends it only to fresh workers with no session, and keeps the planner tool-free and native-skill-free. Main and worker pause continuations use separate container IDs and preserve their own full raw response content.

```text
response reset -> one gate(message, persistent record)
                     | closed -> stopped
                     | specialist -> begin_delegated -> handoff
                     v
prompt alignment -> tool attachment -> skill preload
  -> run_state.begin -> tool selector -> bounded bulk coordinator
  -> bulk workers(selected native refs, fresh sessions)
  -> inherited loop(original message, selected refs) -> pause/resume as needed -> outcome
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

`claude_skills` is the selected native tuple from the completed preload outcome. The relation facade's `begin_delegated` follows the relation policy before specialist handoff.

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

Combines the Jev setup capabilities in the approved order and retains run-local cleanup around all normal-run phases.

#### Interface / API

```python
async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...
```

#### Logic / Algorithm

1. Reset the response and call the combined gate with the persistent run-state record.
2. Stop on a closed gate. If a specialist is selected, call `begin_delegated` and hand off before alignment/preload/bulk.
3. Save owner system prompt, user tool catalog, and full tool catalog; keep run options as immutable per-call values.
4. Apply prompt alignment, then tool alignment/attachment and update context/tool specs.
5. Normalize an explicit `options['system']` override into the effective context even when no skill loader exists; when configured, resolve and score skills, append selected text, and add the selected native refs to the copied main-agent options.
6. Call `run_state.begin(message)`, then existing core `_select_tools` so workers see only selected tools.
7. If the bulk gate flag is true, call the named coordinator with the selected refs from the skill outcome and add its typed result as immutable context data. Keep the message passed to `super().arun` unchanged.
8. Handle attachment announcement, selector metadata, and normal response outcome.
9. Let the inherited runtime record each raw call's usage once and continue valid native pause turns with the owning main agent's session.
10. In `finally`, restore prompt and user/full tool catalogs, then release any attached MCP resources.

#### Edge Cases & Error Handling

- A tool selector that filters a tool must not have that tool reintroduced for workers.
- Main-agent native references remain in the run-local options; the owner session is never sent to a worker.
- Bulk workers receive the effective explicit system override even when no skills are configured; the main agent keeps the original run options and synthesis uses the same override.
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

The `claude_skills` parameter accepts only references selected by the owner’s completed Jev preload. No generic worker callback or options factory is introduced.

#### Logic / Algorithm

1. Generate and validate the whole plan; require at least two tasks and no more than configured `max_items`. Invalid plans are rejected whole, never truncated.
2. Do not expose tools or native skills to the planner. Use a bounded queue with at most `min(max_parallel_agents, item_count)` worker coroutines.
3. Give every worker isolated history and a trusted item-only instruction. Clone bound tools via `clone_for_fork()` to isolate agent tool context while preserving names.
4. Pass the selected native references and explicit `claude_skill_session=None` to each new worker. Never pass the owner's session/container; each worker starts and resumes its own container inside its own BaseAgent loop.
5. Collect outputs/failures by original task index. Catch ordinary per-item exceptions into safe typed failures; let cancellation escape and clean siblings up.
6. Record planner and worker usage only through their existing owned rollups. Add a result artifact to a replacement context for the inherited loop; synthesis instructions must not treat failures as successes.

#### Edge Cases & Error Handling

- Never leak raw `str(exc)` or `repr(exc)` into public output; use a safe error code/type or stable generic message.
- Tool wrappers without the approved clone hook must be surfaced as a concrete integration issue; do not redesign the global forker.
- Arbitrary custom mutable stateless tools retain the existing fork contract and may be shared by identity.
- Native provider usage from a child remains owned by that child; the owner does not flatten or re-record its child rollup.
- No shared mutable context, worker history, or result ordering depends on task completion order.

### 6.5 Public Types, Presets, Response, and Exports

**File(s):** `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/response.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `vidbyte/lib/constants/jev.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/dataclasses/model_configs.py`, `vidbyte/lib/dataclasses/skills.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/enums/jev.py`, `vidbyte/lib/enums/prompts.py`, `vidbyte/lib/enums/skills.py`, `vidbyte/lib/jev/preflight/__init__.py`, `vidbyte/lib/jev/presets.py`
**Type:** Modified files

#### What it does

Preserves the union of existing core types and feature types, including validated bulk settings/results, run-state relationship types, explicit skill sources, selected native references, typed per-call provider sessions, the relation and bulk presets, response fields, alignment settings, and tool-selector configuration. Every public closed status/rejection vocabulary remains a central enum; dataclasses remain in `vidbyte/lib/dataclasses`.

#### Interface / API

```python
JevAgentSettings.bulk_work: JevBulkSettings
JevAlignmentSettings.skills: tuple[str | SkillDocument | SkillSource, ...]
JevAgentResponse.bulk_work: JevBulkWorkResult | None
JevSkillsOutcome.claude_skills: tuple[ClaudeSkillReference, ...]
JevPreflightPreset.RUN_STATE_RELATION: str
JevPreflightPreset.BULK_WORK: str
```

#### Logic / Algorithm

1. Merge exports and central registries as a union, preserving all skills-core exports, settings, response fields, tool-alignment presets, provider skill types, and done-check types.
2. Register both new preflight presets alongside the current core presets without duplicate enum or mapping keys.
3. Keep feature result status fields typed through central enums and preserve the sole response writer contract.

#### Edge Cases & Error Handling

- Resolve overlapping edits by retaining both features' registrations and all current core behavior; no feature branch's deletions replace core additions.
- Do not move dataclasses into `agents` or private coordinator modules.
- Keep package exports importable without initializing runtime providers.

### 6.6 Prompt Assets and Focused Feature Packs

**File(s):** `vidbyte/lib/jev/preflight/README.md`, `vidbyte/prompts/README.md`, `vidbyte/prompts/prompts/jev_bulk_work/jev_bulk_work.json`, `vidbyte/prompts/prompts/jev_bulk_work/synthesis_prompt.md`, `vidbyte/prompts/prompts/jev_bulk_work/system_prompt.md`, `vidbyte/prompts/prompts/jev_bulk_work/worker_system_prompt.md`, `tests/test_jev_preflight.py`, `tests/test_jev_run_state_relation.py`, `tests/features/jev_bulk_work/FEATURE.md`, `tests/features/jev_bulk_work/README.md`, `tests/features/jev_bulk_work/test_jev_bulk_work.py`, `scripts/test-jev-bulk-work.py`, `scripts/test-jev-run-state-relation.py`, `tests/test_jev_skill_providers.py`, `tests/test_jev_skill_remote_sources.py`, `scripts/test-jev-skill-providers.py`, `docs/jev-skill-providers.md`
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

1. Keep the existing relation, bulk, skill-preload, tool-alignment, and source-provider test packs intact.
2. Add integration coverage for one combined gate and persistent old record; relation retain/replace behavior; selector-before-bulk ordering; skill text/options; ordered partial failures; unchanged main message; repeated-run reset; and cleanup.
3. Cover independent worker sessions, exact selected reference forwarding, planner exclusion, raw pause/resume history, usage retention, and no-skills explicit system override behavior.

#### Edge Cases & Error Handling

- Use provider/runner stubs for deterministic tests; no live TypeSafe or provider call is required.
- Test context creation through actual `BaseAgent` context-building behavior where prompt precedence is relevant.
- Focused feature scripts run independently, then normal custom lint/source/full CI gates cover the merged branch.

### 6.7 Selected Native Skills on Isolated Bulk Workers

**File(s):** `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/jev/bulk_work.py`, `vidbyte/agents/jev/alignment/skills.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/runners/text.py`, `tests/test_jev_runtime_setup_integration.py`
**Type:** Modified files

#### What it does

Carries only Jev-selected Claude references to new bulk workers. Each worker receives references but no existing session, starts its own container, and continues its own paused native execution through its own BaseAgent runtime.

#### Interface / API

```python
async def plan_and_run(self, message: str, context: BaseAgentContext, tools: tuple[object, ...], *, claude_skills: tuple[ClaudeSkillReference, ...] = ()) -> JevBulkWorkResult: ...
```

#### Logic / Algorithm

1. After `_preload_skills`, the owner reads the exact selected references from `JevSkillsOutcome.claude_skills` and passes them to the bulk coordinator.
2. The coordinator's planner receives neither tools nor native references. It plans from the complete unchanged original user request.
3. Each fresh worker gets the selected text context, selector-approved tools, effective system prompt/options, the selected native refs, and `claude_skill_session=None`.
4. A worker's first native request creates a new provider container; the same worker's later pause turns reuse only its own returned session. The owner's container ID/session is never forwarded.
5. The main agent retains its selected refs and independently owns its own main-run container and pause history.
6. Preserve the trusted synthesis instruction once, honor explicit `options['system']` as the baseline, and keep the main-loop message unchanged.

#### Edge Cases & Error Handling

- Missing skill outcome or an empty selected-ref tuple yields no native skill option for workers.
- Provider rejection or malformed session state remains visible as the worker's safe typed failure; cancellation propagates and cleans up siblings.
- No worker receives an unselected source, the owner's session/container, or the planner's generated history.
- Keep this named typed argument; do not add generic callbacks, factories, or runtime strategy surfaces.

### 6.8 Anthropic Pause Continuation in the Inherited Loop

**File(s):** `vidbyte/agents/runtime.py`, `vidbyte/providers/anthropic.py`, `vidbyte/lib/runners/types.py`, `tests/test_jev_skill_providers.py`, `tests/test_jev_runtime_setup_integration.py`
**Type:** Modified files

#### What it does

Lets the existing bounded AgentRuntime continue a Claude-native `pause_turn` without adding a provider-owned loop or bypassing normal middleware and usage accounting.

#### Logic / Algorithm

1. Anthropic returns the untouched full response and usage map, plus a typed session carrying container ID, pause state, and exact resume messages.
2. AgentRuntime records usage and calls response middleware once for every raw exchange before interpreting the native session.
3. For a paused response, append the complete raw assistant message once and continue. The next provider request reuses the same container and exact message list, without appending the original user request again.
4. For a completed response, retain its container for any later local tool turn and continue through the normal local tool parser; server-side code execution blocks are never dispatched as SDK-local tools.
5. Existing iteration, token, timeout, middleware-stop, cancellation, and usage-tracker policies bound the repeated calls.

#### Edge Cases & Error Handling

- A malformed native response without content or a container ID raises a typed provider response error.
- Native streaming fails before transport. Ordinary nonnative calls retain their existing payload and path.
- Child and owner loops preserve separate session/container state; each raw response remains recorded once by its own agent.

---

## 7. Data Model Changes

No database or persisted storage schema changes.

The public in-memory model is the union of existing core records and the relation, bulk, and provider-skill types. `JevAgentSettings` gains the named `JevBulkSettings` field; `JevAgentResponse` gains `bulk_work: JevBulkWorkResult | None`; relation outcomes remain in the existing preflight result map. `JevSkillsOutcome` carries the selected `ClaudeSkillReference` tuple. `TextModelResponse` carries one exchange's raw usage and optional `ClaudeSkillSession`, which stays run-local and is never placed in public Jev response records.

---

## 8. API Changes

### 8.1 JevAgent configuration and response

**Change type:** Modified

**Request:**

```python
JevAgentSettings(
    bulk_work=JevBulkSettings(max_parallel_agents=4, max_items=32),
    alignment=JevAlignmentSettings(skills=(SkillSource(kind=SkillSourceKind.CLAUDE, location="skill-id"),)),
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
    skills=...,         # ordered candidate results and selected native refs
    tool_alignment=..., # existing core tool attachment outcome
    bulk_work=...,      # ordered typed planner/worker outcome or None
)
```

Each worker gets the selected `ClaudeSkillReference` values through `plan_and_run(..., claude_skills=...)` and an explicit empty initial session. The owner retains its own provider options and session lifecycle.

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

The current core head already contains text skill preload and tool alignment. This manifest is the reconciled union of the relation and bulk heads, provider skill-source head, and cross-feature integration work. Shared paths appear once with all applicable responsibilities in the reason column.

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
| MODIFY | `vidbyte/agents/jev/agent.py` | Union facade construction, named capability wiring, and provider-aware skill source configuration. |
| MODIFY | `vidbyte/agents/jev/done/__init__.py` | Export relation facade. |
| MODIFY | `vidbyte/agents/jev/done/run_state.py` | Preserve the existing generator behavior and relation-aware state lifecycle seam. |
| MODIFY | `vidbyte/agents/jev/gate/gate.py` | Accept persistent record and reset/score both feature flags. |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Apply ordered phases, selected native refs, main session options, and combined cleanup. |
| MODIFY | `vidbyte/agents/jev/response.py` | Preserve core response fields and add bulk result writer. |
| MODIFY | `vidbyte/agents/jev/README.md` | Document the opt-in bulk-work capability. |
| MODIFY | `vidbyte/agents/jev/settings.py` | Add named bulk settings and explicit skill source values while preserving core settings. |
| MODIFY | `vidbyte/lib/constants/jev.py` | Add relation threshold/constants without removing core values. |
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | Add central bulk result/plan records and selected native refs in the skill outcome. |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export Jev, skill-source, and Claude skill enums. |
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
| CREATE | `docs/design/jev-skill-providers.md` | Preserve provider-source and Claude-native skill contracts. |
| CREATE | `docs/jev-skill-providers.md` | Document explicit skill source configuration and provider behavior. |
| CREATE | `scripts/test-jev-skill-providers.py` | Provide the focused source-provider verification entrypoint. |
| CREATE | `tests/test_jev_skill_providers.py` | Test native Anthropic payload, sessions, usage, and skill selection. |
| CREATE | `tests/test_jev_skill_remote_sources.py` | Test bounded file, GitHub, skills.sh, and Claude source resolution. |
| MODIFY | `vidbyte/agents/jev/alignment/skills.py` | Resolve sources, score native metadata, and preserve selected Claude references. |
| MODIFY | `vidbyte/agents/runtime.py` | Resume native pause turns within the inherited bounded loop. |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export provider skill-source and native-session records. |
| MODIFY | `vidbyte/lib/dataclasses/model_configs.py` | Add validated typed native skill/session call configuration. |
| MODIFY | `vidbyte/lib/dataclasses/skills.py` | Add source, native-reference, and provider-session records. |
| MODIFY | `vidbyte/lib/enums/skills.py` | Define closed skill source and Claude skill type enums. |
| MODIFY | `vidbyte/lib/jev/preflight/skills.py` | Ask relevance from honest text or native metadata without exposing fake bodies. |
| MODIFY | `vidbyte/lib/runners/streaming_text.py` | Reject native Claude requests before streaming transport. |
| MODIFY | `vidbyte/lib/runners/text.py` | Carry request-local native references and session sentinel through runner calls. |
| MODIFY | `vidbyte/lib/runners/types.py` | Return optional typed native provider session state on text responses. |
| MODIFY | `vidbyte/providers/anthropic.py` | Mount native references, preserve exact resume history, and return raw exchange usage/session. |
| CREATE | `vidbyte/providers/skills/__init__.py` | Provide closed skill-source resolver dispatch. |
| CREATE | `vidbyte/providers/skills/base.py` | Define source adapter and safe SKILL.md parser contracts. |
| CREATE | `vidbyte/providers/skills/claude.py` | Resolve Claude skill metadata to pinned opaque references. |
| CREATE | `vidbyte/providers/skills/file.py` | Resolve bounded local SKILL.md files. |
| CREATE | `vidbyte/providers/skills/github.py` | Resolve bounded GitHub-backed skill sources. |
| CREATE | `vidbyte/providers/skills/skills_sh.py` | Resolve explicit skills.sh references through GitHub. |

No files are deleted. Shared runtime, export, and settings paths are unioned; the provider feature's separate public PR remains untouched.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_jev_preflight.py` -> one gate request contains enabled relation, bulk, specialist, and existing fixed questions; relation receives the persistent old record; both flags reset on repeated passes; absent record omits relation; a single negative or uncertain bulk answer disables fan-out.
- `tests/test_jev_run_state_relation.py` -> retain related/unavailable records, replace unrelated records, initialize with no record, initialize without done checks, and handle delegated specialist state.
- `tests/features/jev_bulk_work/test_jev_bulk_work.py` -> validate planner bounds without truncation, bounded concurrency, stable result order, safe partial failures, cancellation cleanup, original request preservation, and result artifact visibility.
- Core skill preload tests -> selected skill text and explicit system overrides survive the merged runtime and reach a real context-building provider stub.
- Provider skill tests -> each configured source keeps its index, native metadata does not masquerade as text, selected Claude refs are capped and typed, and provider failures preserve cancellation and safe error details.
- Core tool alignment and selector tests -> attached tools are available to selection and workers receive exactly the selector's effective set.
- New integration test file -> assert `response.start` precedes gate but gate uses `self.run_state.record`; runtime phase order; specialist bypass; selected-skill/tool context precedes bulk; inherited loop receives unchanged message; repeated-run cleanup restores prompt/tools and releases MCP attachment.
- Bulk-only integration test -> verify an explicit `system` option reaches the actual worker context builder when the skill preloader is absent, while main synthesis retains the override.
- Native integration test -> exact selected `ClaudeSkillReference` forwarding to fresh workers, independent worker container IDs, planner receives none, and main owner session remains separate while selected text/tools/system and one synthesis instruction remain present.
- Pause integration test -> exact assistant content resumes once without duplicating the original request; raw cached usage remains visible and recorded once per exchange.

### Integration Tests

- Run all four focused packs: skill preload, tool alignment, run-state relation, and bulk work.
- Run the focused provider source/native payload test packs.
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
| Skills source adapters | Existing `HttpTransport`, PyYAML, GitHub, and Anthropic endpoints | Resolve explicit source descriptors to text or native refs | Bounded requests; source failures remain indexed and cannot execute skill assets. |
| Anthropic Messages API | Existing configured Anthropic model | Mount selected skill refs and resume valid pause turns | One provider request per runtime iteration; raw usage recorded by the existing tracker. |
| Existing MCP alignment attachment | Current SDK runtime contract | Attach selected tools for the run | Must be released in `finally`, including errors and cancellation. |

No new external service or package is introduced.

---

## 12. Rollout & Deployment

- Both new preflight presets and configured skills are opt-in; defaults retain current behavior and do not add capability model calls.
- This is an additive SDK API change; no persistent migration is required.
- Merge only into the isolated integration branch. Do not merge component PRs into main as part of this task.
- Required order: commit this design amendment, merge the reviewed provider head into the relation/bulk integration branch, resolve shared-file unions, implement selected-reference bulk forwarding and cross-feature tests, receive parent diff review, then run focused tests, custom lint, source tests, and full CI.
- Prepare a separate aggregate draft PR only after parent reviews the combined diff and required gates pass. Keep component PRs and main untouched.
- Rollback consists of discarding the isolated integration branch; no data or external service changes are made.

---

## 13. Open Questions

- [ ] Provider's native-metadata relevance question must meet the repo's >=2,000 meaningful-token and 2–3 sentence intro requirements before final gates; provider owner owns that follow-up.
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
