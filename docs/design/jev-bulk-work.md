# Design Doc: Jev Bulk Work

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-30
**Last Updated:** 2026-09-30

---

## 1. Overview

Jev Bulk Work adds an opt-in path for requests that clearly ask for the same operation on multiple independent items. Three fixed Jev preflight questions recognize the request's item multiplicity, shared operation, and independence in the existing single batched decision call. When all three pass, a generative planner may turn the original request into a bounded list of independent tasks; fresh BaseAgent workers then process those tasks concurrently using the main agent's selected tools and permission policy. Results remain ordered, include failures and per-agent usage, and are supplied to the existing JevAgent loop for final synthesis. If recognition, planning, or configuration is unavailable or invalid, the existing serial path remains responsible for the original request.

---

## 2. Goals & Non-Goals

### Goals

- Add validated `JevBulkSettings` to `JevAgentSettings` for worker concurrency, maximum task count, and planner iteration/token limits.
- Add the opt-in `JevPreflightPreset.BULK_WORK` with three separate positive recognition questions, combined in the existing gate request and scored with a `.75` threshold and `.75` per-answer veto.
- Require all three recognition decisions to pass; any clear negative, explicit dependency, missing answer, or uncertain independence must not start fan-out.
- Plan between two and `max_items` nonblank work items. Reject an invalid or oversized plan whole; never truncate a plan to fit.
- Process tasks with a bounded number of worker coroutines, isolated agent histories, exactly the selected tools, and the owner's model and permission policy.
- Keep task results in input-plan order, retain each item's success or failure, preserve planner and worker usage rollups once, and expose the outcome through `JevAgent.response.bulk_work`.
- Feed task results to the inherited JevAgent loop as context while preserving the original user message and the caller's context.
- Keep ordinary serial, specialist, and tool-selector behavior intact when the new preset is disabled or bulk planning cannot proceed.
- Add executable feature verification covering every case listed in Section 10.

### Non-Goals

- Do not enable bulk work by default or infer it from runtime data outside the explicit preflight preset.
- Do not use Jev to count items, create a plan, execute tasks, or replace the existing generative loop.
- Do not truncate tasks, recursively construct JevAgents, run nested preflight, or bypass tools discarded by normal tool selection.
- Do not add a general-purpose orchestration framework, a public worker callback, or arbitrary BaseAgent runtime customization.
- Do not change specialist routing, tool selection policy, permission policy semantics, BaseAgent fork behavior, or the existing final-response/done-check contracts.
- Do not aggregate planner/worker usage by re-recording child rollups into the owner's raw usage tracker.

---

## 3. Background & Context

JevAgent currently runs a fixed-question preflight gate, optionally chooses a specialist, applies the configured tool selector, and then enters its inherited linear BaseAgent loop. Fixed-question presets are registered in `vidbyte/lib/jev/preflight/` and `vidbyte/lib/jev/presets.py`; the gate batches enabled preset questions, scores them through `DecisionModelHelper`, and owns the outcome actions. Runtime policies are configured when JevAgent is constructed, not selected by the runtime through generic hooks.

BaseAgent already provides isolated agent instances, raw usage tracking, context artifact rendering, and tool cloning for forks. Jev Bulk Work uses those seams while creating one generative planner and fresh task workers. The planner receives the complete original request as data and has no tools. Worker tools are cloned through the existing `clone_for_fork()` hook before each worker is constructed, matching `AgentForker`'s tool ownership contract without reopening MCP catalogs. Tools lacking a clone hook retain the existing forker's identity behavior.

Bulk work is an opt-in acceleration path. Preflight is only a recognition gate: if any required answer is absent, unavailable, below threshold, or indicates dependency/uncertainty, the gate leaves the bulk flag false and the ordinary path proceeds. Planning is separately validated, and invalid output falls back to the ordinary path without starting task workers. A worker failure is retained as that item's result while other planned tasks continue. Cancellation propagates and cancels sibling worker coroutines.

---

## 4. Requirements

### Functional Requirements

1. Add a frozen, validated `JevBulkSettings` value object with `max_parallel_agents=4`, `max_items=32`, `planner_max_iterations=5`, and `planner_max_tokens=16_000`; expose it as `JevAgentSettings.bulk_work` with a default factory.
2. Add `JevPreflightPreset.BULK_WORK`, three unique fixed question keys, and a preset definition using `.75` score threshold and `.75` individual-answer veto for each of the three questions.
3. Ask in the existing combined gate request whether the request names multiple items, assigns the same operation across them, and describes them as independently executable. Each question makes one positive recognition judgment and includes explicit positive and negative mirrored criteria.
4. Leave the gate's bulk-work outcome false at the start of every pass. Only a fully available, passing bulk-work preset sets it true; fail-open behavior, missing answers, or any question veto leaves it false.
5. Process specialist routing before bulk work. If a specialist is selected, delegate exactly as today and do not plan or execute bulk work.
6. Apply ordinary tool selection before constructing the planner/worker execution path. Task workers receive only the effective selected tools, the same model configuration, and the same permission policy as the owner.
7. Build a bounded planner BaseAgent with no tools and explicit settings-derived iteration/token caps. Pass the entire original user message as untrusted request data and request a structured plan whose task records have stable identifiers, nonblank titles, and nonblank prompts; each prompt must describe independent work within the original request.
8. Accept a plan only when it contains at least two and no more than `max_items` tasks and every task passes validation. Any malformed or oversized plan is rejected as a whole, produces no task workers, and falls through to the ordinary path with the original request unchanged.
9. Execute a valid plan using `min(max_parallel_agents, task_count)` worker coroutines consuming a bounded `asyncio.Queue`; do not create one asyncio task per work item. Record each result in its plan position.
10. Catch ordinary `Exception` for an individual task and retain a typed failure record while other tasks run. Propagate cancellation and clean up sibling workers. Tool permission failures do not trigger retries with a different policy.
11. Construct each task worker as a fresh BaseAgent with an isolated history. Clone each selected SDK tool via its `clone_for_fork()` hook before passing it to that agent; retain tools without that hook by identity, following the existing AgentForker contract. Never construct a seed worker with the original agent-bound tools first.
12. Include planner and worker raw usage rollups in the typed bulk result exactly once; do not flatten or re-record these child rollups in the owner tracker.
13. Publish ordered item results and planner/worker usage through a typed `JevAgentResponse.bulk_work` field written only by `JevResponse`. Do not put feature outcome in `AgentResult.metadata`.
14. Add task results to a copied BaseAgent context for inherited final synthesis. Keep the original user message, original shared context, and existing done-check loop unchanged.
15. If the preset is absent, the gate fails open, the plan is invalid, or the planner cannot produce a usable plan, make no worker calls and preserve the ordinary serial path. Disabled capability adds no planner call.
16. Restore any temporary runtime tool catalog changes in `finally`, including when selection, planning, workers, synthesis, or cancellation raises.

### Non-Functional Requirements

- Bound simultaneous task agents by `max_parallel_agents`; bound planned tasks by `max_items` and planner resource use by explicit settings.
- Keep each worker's conversation history isolated and keep mutable caller context unmodified.
- Keep fixed question content within the repository's Jev question authoring policy: at least 2,000 meaningful tokens per question, full structured brief and criteria, positive mirrored criteria, one judgment per question, and explicit prompt-injection handling.
- Preserve permission enforcement and exact tool-selection results. Do not elevate permissions or restore selector-discarded tools during fan-out.
- Preserve child usage rollups and failure details without duplicate accounting. Avoid logging request contents or credentials.
- Use cancellation-safe worker cleanup. A task exception must not erase successful sibling results.
- Keep the feature disabled by default; no migration or deployment flag is required.

---

## 5. High-Level Design

`JevBulkSettings` provides named limits, while `JevRuntimeSettings.preflight` opts into three new fixed questions. The existing `JevPreflightGate` combines them with any other enabled fixed questions in one TypeSafe request, resets its bulk flag on each run, and requires all three score/veto checks to pass. Specialist routing keeps precedence. The runtime applies its existing tool selector first and restores its run-local tool catalog in a `finally` block.

When the gate passes, `JevBulkWork` uses a tool-free BaseAgent planner to create a structured list of work items from the entire original request. The planner result is validated atomically. A malformed, missing, fewer-than-two, or oversized list falls back to the ordinary inherited loop. A valid list is consumed by a bounded worker pool. Each item uses a fresh BaseAgent, cloned selected SDK tools where supported, owner-equivalent model/permissions, and isolated task history. Result slots preserve original plan order regardless of completion order.

The coordinator records planner and worker usage once and returns a typed bulk result with one record per item. `JevResponse` is the only writer of that result to `JevAgent.response`. The runtime provides a new context value containing the task records and then calls the inherited loop with the original message; its usual finish-attempt hook and done checks remain active. The original context and selected-tool catalog are not mutated across runs.

```text
Original request
   |
   v
JevPreflightGate -- three positive checks all pass? -- no --> ordinary serial loop
   | yes
   v
Specialist selected? -- yes --> specialist path
   | no
   v
Tool selector -> effective tool set -> tool-free planner -> validate complete plan
                                               | invalid -> ordinary serial loop
                                               | valid
                                               v
                                  bounded asyncio worker pool
                                               |
                                               v
                                ordered typed task records
                                               |
                                               v
                 copied context + original message -> inherited final loop
```

---

## 6. Detailed Design

### 6.1 Public Bulk Settings

**File(s):** `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Adds the named `JevBulkSettings` configuration type and includes it on `JevAgentSettings`, preserving the closed JevAgent constructor surface. Numeric limits reject booleans, non-integers, and values below the supported minimum before any agent is built.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class JevBulkSettings:
    max_parallel_agents: int = 4
    max_items: int = 32
    planner_max_iterations: int = 5
    planner_max_tokens: int = 16_000

@dataclass(frozen=True, slots=True)
class JevAgentSettings:
    bulk_work: JevBulkSettings = field(default_factory=JevBulkSettings)
```

#### Logic / Algorithm

1. Validate all four limits as non-boolean integers at or above one.
2. Validate the nested object is exactly a `JevBulkSettings` instance.
3. Freeze the validated setting as part of the existing immutable `JevAgentSettings`.
4. Export the new type alongside existing Jev public settings.

#### Edge Cases & Error Handling

- Reject zero/negative limits, booleans, floats, strings, and invalid nested values with `ConfigurationError`.
- Keep the defaults finite and capability inactive unless the preset is explicitly enabled.

### 6.2 Bulk Recognition Questions and Preset

**File(s):** `vidbyte/lib/constants/jev.py`, `vidbyte/lib/enums/jev.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/jev/presets.py`, `vidbyte/lib/jev/preflight/preflight.py`, `vidbyte/lib/jev/preflight/bulk_work.py`, `vidbyte/agents/jev/gate/gate.py`
**Type:** Modified / New

#### What it does

Registers three fixed questions as one opt-in preset. Each question separately judges one positive condition: named multiple items, one repeated operation, or explicit independent execution. The preset requires all three answers to pass the `.75` threshold and each `.75` veto, so a clear `no` cannot be hidden by positive averages.

#### Interface / API

```python
class JevPreflightPreset(str, Enum):
    BULK_WORK = "bulk_work"

class JevPreflightQuestionKey(str, Enum):
    BULK_WORK_MULTIPLE_ITEMS = "bulk_work.multiple_items"
    BULK_WORK_SHARED_OPERATION = "bulk_work.shared_operation"
    BULK_WORK_INDEPENDENT_ITEMS = "bulk_work.independent_items"
```

The public opt-in is `JevRuntimeSettings(preflight=(JevPreflightPreset.BULK_WORK,))`. The gate stores `bulk_work_requested` as run-local decision state and resets it to `False` before every pass.

#### Logic / Algorithm

1. Define one question dataclass for each key in `bulk_work.py`, with one recognition judgment per question and full JevBrief/JevCriterion content.
2. Register the question tuple and `.75` threshold / `.75` veto policy in the existing preset and registry maps.
3. Include all three questions in the existing single combined TypeSafe request.
4. Score all three through `DecisionModelHelper.score_noul`; only a fully available passing result enables the gate flag.
5. Treat missing or uncertain recognition, missing answers, request errors, explicit dependency, or any individual veto as not eligible for fan-out.

#### Edge Cases & Error Handling

- Preset disabled: ask no bulk questions and leave the flag false.
- A gate failure or missing answer follows existing fail-open behavior but never enables bulk work.
- A previous run's positive flag must not survive into a subsequent run.
- Question text must consider prompt injection in the original request as data, not as instructions to alter the decision criteria.

### 6.3 Typed Plan and Outcome Records

**File(s):** `vidbyte/lib/dataclasses/jev.py`, `vidbyte/agents/jev/response.py`
**Type:** Modified

#### What it does

Defines the structured planner output schema, validates public per-item results, and adds the sole response-writer method that publishes a completed bulk-work outcome. Results preserve task order, status, text/error, and each child agent's owned usage rollup.

#### Interface / API

```python
class JevBulkPlanItem(BaseModel):
    identifier: str
    title: str
    prompt: str

@dataclass(frozen=True, slots=True)
class JevBulkItemResult:
    identifier: str
    title: str
    output: str | None
    error: str | None
    usage: UsageRollup | None

@dataclass(frozen=True, slots=True)
class JevBulkWorkResult:
    items: tuple[JevBulkItemResult, ...]
    planner_usage: UsageRollup | None
```

`JevAgentResponse.bulk_work` is `JevBulkWorkResult | None`, and `JevResponse.bulk_work(result)` is its only writer.

#### Logic / Algorithm

1. Require nonblank identifier, title, and prompt in every plan item.
2. Require two or more plan items and reject the entire plan if the count exceeds `max_items`.
3. Require identifiers to be unique so results map deterministically to requested work.
4. Store item results as an immutable tuple in original plan order.
5. Preserve success or ordinary exception as an explicit item outcome; preserve each raw `UsageRollup` without flattening or re-recording it.

#### Edge Cases & Error Handling

- No partial acceptance or truncation of malformed plans.
- Empty output is still a completed output string; a task error is represented separately.
- If planning fails before a valid plan exists, leave `bulk_work` unset and use the ordinary path.

### 6.4 Planner and Bounded Worker Coordinator

**File(s):** `vidbyte/agents/jev/bulk_work.py`
**Type:** New

#### What it does

Implements `JevBulkWork`, a bounded generative planner/coordinator built from `JevBulkSettings` and the owner's ordinary agent settings. It never constructs another JevAgent. Its planner has no tools; each work item gets a fresh BaseAgent worker with separate history.

#### Interface / API

```python
class JevBulkWork:
    def __init__(self, settings: JevAgentSettings) -> None: ...
    async def plan_and_run(self, message: str, context: BaseAgentContext) -> JevBulkWorkResult | None: ...
```

Returning `None` means no valid plan was produced; the runtime continues through the ordinary serial loop.

#### Logic / Algorithm

1. Construct a structured-output planner BaseAgent with owner provider/model/API configuration, a system prompt for independent work decomposition, no tools, and configured iteration/token bounds.
2. Pass the complete original request as explicit request data; validate plan schema, lower/upper count, unique IDs, and nonblank content atomically.
3. Make a bounded `asyncio.Queue` for planned item indexes and start exactly `min(max_parallel_agents, task_count)` worker coroutines.
4. For each item, create a new BaseAgent using the owner's name/prompt policy, model, API configuration, timeout, loop policy, and permission policy. Clone every selected SDK tool by calling its `clone_for_fork()` hook before BaseAgent construction; preserve tools without this hook by identity.
5. Run the task under its own work-specific prompt and isolated context/history. Capture normal exceptions as task failures and continue consuming the queue.
6. On cancellation, cancel and gather the pool so sibling work is not left running; do not convert cancellation into an item failure.
7. Return ordered results plus planner and per-worker `get_usage()` rollups.

#### Edge Cases & Error Handling

- A missing or malformed structured output, one item, zero items, or more than `max_items` yields `None` before any worker is created.
- An item exception is retained and does not cancel siblings; a cancellation propagates and cleans the pool.
- Selected tool names must match exactly. AgentTool clones must bind to each worker and leave the owner's original AgentTool bound to the owner.
- Custom mutable tools without a clone hook follow the existing fork identity contract; parallel safety remains that tool's existing responsibility.
- Planner failure is a no-worker fallback. Permission and tool failures never cause a permission-policy change.

### 6.5 JevAgent Runtime Integration

**File(s):** `vidbyte/agents/jev/agent.py`, `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/jev/README.md`
**Type:** Modified

#### What it does

Builds the named coordinator in JevAgent, passes it through the established runtime extension seam, and invokes it only after gate approval, specialist precedence, and normal tool selection. The runtime passes ordered task results to the inherited loop through a copied context while preserving the original request.

#### Interface / API

No generic runtime hook is added. Public configuration is via `JevAgentSettings.bulk_work` and `JevRuntimeSettings.preflight`; results are visible at `JevAgent.response.bulk_work`.

#### Logic / Algorithm

1. At every gate pass reset the flag and evaluate enabled fixed-question presets in the existing gate match.
2. In runtime, stop or delegate as today; when continuing, apply the ordinary selector first when configured.
3. If the bulk preset passed, ask `JevBulkWork` to plan and execute using the effective `self.user_tools` and policy.
4. If a plan is invalid, proceed into the existing `super().arun` with the original message and context.
5. If results exist, write the typed response and use `dataclasses.replace` to add task records to a copied context, then enter the inherited loop with the same original message.
6. Restore run-local user and internal tool catalogs in `finally`, including exceptional and cancellation paths.
7. Leave normal inherited finish checks and result handling in place; do not expose bulk outcome in AgentResult metadata.

#### Edge Cases & Error Handling

- Specialist selection bypasses bulk planning entirely.
- Tool selection precedes every worker build; discarded tools remain unavailable to workers.
- The same JevAgent can run multiple times without stale bulk flags, tools, response records, or task results.
- Disabled selector, disabled bulk capability, invalid planning, and gate fail-open all retain the current serial behavior.

### 6.6 Prompt Catalog, Documentation, and Verification

**File(s):** `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/prompts/jev_bulk_work/jev_bulk_work.json`, `vidbyte/prompts/prompts/jev_bulk_work/system_prompt.md`, `vidbyte/prompts/README.md`, `vidbyte/agents/jev/README.md`, `vidbyte/lib/jev/preflight/README.md`, `tests/features/jev_bulk_work/FEATURE.md`, `tests/features/jev_bulk_work/README.md`, `tests/features/jev_bulk_work/test_jev_bulk_work.py`, `scripts/test-jev-bulk-work.py`
**Type:** Modified / New

#### What it does

Adds the planner prompt to the existing prompt family catalog and documents the new settings, gate and runtime behavior. Unit and integration tests exercise behavior with deterministic fake planner/worker agents, without provider calls. The executable script invokes each documented test case and prints individual status plus a final count.

#### Interface / API

The prompt is retrieved through the existing `Prompt` / `Prompts` interface. The script is run with `python scripts/test-jev-bulk-work.py` from the repository root.

#### Logic / Algorithm

1. Register prompt descriptor and enum member and include the new family in the catalog README.
2. Ensure planner instructions treat user-provided text as data, demand independent bounded tasks, and do not include tools.
3. Write test doubles for plans, worker outcomes, tool cloning, usage rollups, and cancellation.
4. Have the executable script run every named Section 10 test case, print `PASS` or `FAIL` for each, and return nonzero unless all pass.

#### Edge Cases & Error Handling

- Prompt catalog's enum, descriptor, dynamic import name, and package exports must agree.
- Script failures must preserve useful test diagnostics and return a nonzero process status.
- No tests make live TypeSafe or model-provider requests.

---

## 7. Data Model Changes

### 7.1 Jev Bulk Work Public Records

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class JevBulkItemResult:
    identifier: str
    title: str
    output: str | None
    error: str | None
    usage: UsageRollup | None

@dataclass(frozen=True, slots=True)
class JevBulkWorkResult:
    items: tuple[JevBulkItemResult, ...]
    planner_usage: UsageRollup | None

@dataclass
class JevAgentResponse:
    bulk_work: JevBulkWorkResult | None = None
```

These are in-memory SDK response types only. No persistence schema, database, or migration changes are required. Public result records validate exclusive success/error state and preserve ordering.

---

## 8. API Changes

### 8.1 JevAgent Settings and Response

**Change type:** Modified public Python API

**Request:**

```python
settings = JevAgentSettings(
    name="batch-review",
    system_prompt="Review the requested items.",
    provider=ModelProvider.OPENAI,
    model_name="...",
    bulk_work=JevBulkSettings(max_parallel_agents=4, max_items=32),
)
runtime = JevRuntimeSettings(preflight=(JevPreflightPreset.BULK_WORK,))
agent = JevAgent(settings, runtime)
await agent.arun("Apply the same review to these independent records: ...")
```

**Response:**

```python
agent.response.bulk_work  # JevBulkWorkResult | None
agent.response.bulk_work.items  # ordered tuple[JevBulkItemResult, ...]
```

**Error cases:**

| Condition | Behavior |
|-----------|----------|
| Invalid settings limit | Construction raises `ConfigurationError`. |
| Bulk preset omitted | No bulk question, planner, or worker call; ordinary path. |
| One or more preflight answers unavailable or vetoed | Gate continues fail-open with bulk disabled. |
| Planner output absent, malformed, under-sized, or over limit | No workers; ordinary path handles the original request. |
| Worker raises ordinary exception | That item has an error result; sibling items continue. |
| Run is cancelled | Cancellation propagates after sibling worker cleanup. |

There is no HTTP endpoint or status-code surface; this API is consumed through the SDK's existing Python agent API.

---

## 9. File Change Manifest

Complete list of expected source, documentation, and test changes. Any implementation deviation must be documented before it is made.

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-bulk-work.md` | Architecture source of truth and testing plan. |
| CREATE | `vidbyte/agents/jev/bulk_work.py` | Planner, structured validation, bounded worker pool, and result assembly. |
| CREATE | `vidbyte/lib/jev/preflight/bulk_work.py` | Three fixed recognition question dataclasses. |
| CREATE | `vidbyte/prompts/prompts/jev_bulk_work/jev_bulk_work.json` | Register planner prompt family. |
| CREATE | `vidbyte/prompts/prompts/jev_bulk_work/system_prompt.md` | Constrained bulk planner prompt. |
| CREATE | `tests/features/jev_bulk_work/FEATURE.md` | Defines the durable behavior contract and failure inventory. |
| CREATE | `tests/features/jev_bulk_work/README.md` | Routes future agents to the feature pack and records its test scope. |
| CREATE | `tests/features/jev_bulk_work/test_jev_bulk_work.py` | Settings, gate, planning, workers, response, and runtime coverage. |
| CREATE | `scripts/test-jev-bulk-work.py` | Executable Section 10 feature verification. |
| MODIFY | `vidbyte/agents/jev/settings.py` | Add validated JevBulkSettings and nested setting. |
| MODIFY | `vidbyte/agents/jev/agent.py` | Build and pass JevBulkWork through the runtime extension seam. |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Gate and dispatch bulk execution after selector and restore catalogs. |
| MODIFY | `vidbyte/agents/jev/gate/gate.py` | Reset and own bulk eligibility outcome. |
| MODIFY | `vidbyte/agents/jev/response.py` | Sole writer for public bulk outcome. |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Export JevBulkSettings and response types. |
| MODIFY | `vidbyte/agents/__init__.py` | Export new public Jev API types. |
| MODIFY | `vidbyte/__init__.py` | Export new public Jev API types. |
| MODIFY | `vidbyte/lib/constants/jev.py` | Add bulk question and recognition thresholds. |
| MODIFY | `vidbyte/lib/enums/jev.py` | Add preset and unique question keys. |
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | Add planner and typed outcome records and response field. |
| MODIFY | `vidbyte/lib/jev/presets.py` | Register three-question policy. |
| MODIFY | `vidbyte/lib/jev/preflight/preflight.py` | Register the new fixed question dataclasses. |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add the planner prompt enum member. |
| MODIFY | `vidbyte/prompts/README.md` | Update prompt family and catalog counts/description. |
| MODIFY | `vidbyte/agents/jev/README.md` | Update JevAgent behavior and module map. |
| MODIFY | `vidbyte/lib/jev/preflight/README.md` | Document bulk question registration. |

No files are deleted. Existing tests are covered by the new focused feature suite unless implementation review shows an established public interface test must be extended; any such addition will be recorded as a manifest deviation.

---

## 10. Testing Plan

### Unit Tests

- `JevBulkSettings` defaults and each accepted positive integer. **[Edge Case]** Verify all four defaults and minimum values. **[Hidden Failure]** Reject bool, float, string, `None`, zero, and negative values for every setting. **[Silent Failure]** Verify custom values remain attached to the correct field and are not swapped. **[Hidden Assumption]** Reject a wrong type for `JevAgentSettings.bulk_work`.
- Fixed question and preset registry. **[Edge Case]** Verify exactly three unique question keys are returned in definition order. **[Hidden Failure]** Verify each key resolves to a registered question and a missing key does not silently disappear. **[Silent Failure]** Verify prompt criteria judge their distinct requested condition and keep the same key from mapping to another question. **[Hidden Assumption]** Supply prompt-injection claims and uncertain/dependency wording and verify the recognition criteria require evidence of independent execution.
- Gate outcome. **[Edge Case]** Evaluate three clear positives and each question individually at its boundary. **[Hidden Failure]** Return missing, malformed, or unavailable answers and verify the gate stays open but bulk remains false. **[Silent Failure]** Give two positives and one clear negative and verify a high average cannot enable bulk work. **[Hidden Assumption]** Run a positive pass followed by an unavailable pass on the same gate and verify the first flag does not persist.
- Plan validation. **[Edge Case]** Accept two items and exactly `max_items`; reject zero/one and `max_items+1`. **[Hidden Failure]** Reject duplicate IDs, blank title/prompt/identifier, missing structured output, and invalid schema before workers start. **[Silent Failure]** Verify oversized plans are rejected whole, never truncated, and original plan order is retained. **[Hidden Assumption]** Treat planner task contents as untrusted data and ensure they do not add tools or expand requested scope.
- Bounded execution. **[Edge Case]** Use task count below, equal to, and above `max_parallel_agents`. **[Hidden Failure]** Cancel during active work and verify every sibling is cancelled/gathered. **[Silent Failure]** Delay items to complete in reverse order and assert returned results still match plan order. **[Hidden Assumption]** Run one throwing worker beside successful workers and verify failures are per-item while remaining work completes.
- Tool and policy isolation. **[Edge Case]** Run with no tools and with several selected tools. **[Hidden Failure]** Make `clone_for_fork()` fail and verify that item fails without binding originals to worker agents. **[Silent Failure]** Assert exact selected tool names on workers, and that discarded tools never reappear. **[Hidden Assumption]** Verify AgentTool clones bind to distinct workers while the owner's original AgentTool remains owner-bound; verify tools without clone hooks retain identity per existing fork contract.
- Usage and response. **[Edge Case]** Return missing rollups from planner and worker. **[Hidden Failure]** Ensure a task exception still retains available usage and sibling result records. **[Silent Failure]** Assert each planner/worker rollup appears once in `response.bulk_work` and no child rollup is re-recorded into owner raw usage. **[Hidden Assumption]** Verify `JevResponse.start()` replaces prior run's bulk outcome and `AgentResult.metadata` is not used for it.

### Integration Tests

- **[Edge Case]** Run an explicitly enabled request through preflight, planner, two workers, context handoff, and inherited final synthesis; confirm normal done checks still execute.
- **[Hidden Failure]** Simulate selector, planner, worker, synthesis, and cancellation failures; confirm tool catalog restoration and correct fallback/propagation behavior.
- **[Silent Failure]** Verify the original request text is passed unchanged to planner and final loop; task records enter only the copied context, and the caller's context remains unchanged.
- **[Hidden Assumption]** Verify specialist routing wins before planning, selector-discarded tools remain unavailable, and a second call on the same JevAgent has no stale eligibility, tools, or response values.
- **[Edge Case]** Disable the bulk preset and assert no planner/worker model calls are made.
- **[Hidden Failure]** Make a gate request fail or omit one answer and verify fail-open serial execution without workers.
- **[Silent Failure]** Reject an over-limit generated plan without truncation or partial execution and verify ordinary loop fallback still receives the full original request.
- **[Hidden Assumption]** Run with custom context artifacts/responses and prove that synthesis receives the preserved plus bulk-result context without mutating the shared source object.

### Manual / QA Test Cases

1. Given `BULK_WORK` enabled and a request naming three independent records with one repeated operation, verify it is eligible, creates three ordered result records, and reports planner/worker usage.
2. Given a request that says later items depend on earlier results, verify it does not fan out even when it names multiple items and one shared operation.
3. Given a planner response exceeding `max_items`, verify no work item is dropped silently and the normal JevAgent loop receives the original request.
4. Given one worker failure among successful tasks, verify the public response retains the failure and successful outputs, and the final loop receives all item records.
5. Given the same JevAgent instance run twice, verify each call begins with a fresh response and fresh bulk gate state.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing BaseAgent | Repository version | Generative planner and isolated task workers. | Child agents own independent model calls and usage records. |
| Existing TypeSafe decision model | Configured by `DecisionModelConfig` | Batched fixed preflight question answers. | Unavailable answers must fail open without enabling bulk. |
| Existing AgentForker tool clone contract | `clone_for_fork()` when available | Isolate SDK tools for workers. | Custom mutable tools without clone hooks retain identity under current SDK contract. |
| Existing `asyncio` runtime | Python standard library | Bounded worker pool and cancellation cleanup. | Cleanup must not swallow cancellation or strand tasks. |

No new external dependency, service, database, or network endpoint is introduced.

---

## 12. Rollout & Deployment

- The feature is opt-in through `JevPreflightPreset.BULK_WORK`; existing callers retain existing behavior by default.
- This is an additive Python API change with a new nullable response field. No database or persisted-session migration is needed.
- Deploy with normal SDK release process; users configure limits and opt into the preset explicitly.
- Roll back by reverting the feature commit(s). Existing serialized response data does not require migration.
- Resource use is bounded by configured planner caps, task maximum, and worker count. Provider billing increases only for opted-in requests that pass recognition and return a valid plan.

---

## 13. Open Questions

- [ ] The `.75` score threshold and `.75` veto are initial values before operational calibration; validate against a representative request suite before considering a default change. No calibration data is available in the codebase audit.
- [ ] Confirm during implementation that every selected tool carrying worker-bound AgentTool state exposes the existing `clone_for_fork()` hook. If an actual wrapper does not, report that concrete interface conflict before expanding the global fork contract.

---

## 14. Alternatives Considered

### Alternative 1: Count task items in Jev preflight

- What: Ask a fixed decision question to count work items and use that count to create workers.
- Why rejected: Fixed Jev questions perform binary recognition only; a generative planner owns decomposition and exact item count is validated deterministically after generation.

### Alternative 2: Add a generic orchestration hook to JevAgent

- What: Let callers inject a custom parallel coordinator or runtime callback.
- Why rejected: JevAgent intentionally exposes named, validated capabilities through closed settings. A named `JevBulkSettings` and internal coordinator preserve that contract.

### Alternative 3: Truncate the generated plan to its configured maximum

- What: Keep the first `max_items` tasks and execute them.
- Why rejected: Silent truncation can omit requested work while appearing successful. Rejecting the whole plan preserves the original request for the established serial path.

### Alternative 4: Use `JevAgent.fork()` or one task per asyncio task

- What: Delegate tool binding and concurrency through the general fork API or create an unbounded asyncio task for each planned item.
- Why rejected: General forking can reopen catalogs and reintroduce tools discarded by the selector, while one coroutine per item does not bound scheduling. Clone selected tools through the existing fork hook and use a bounded queue with a fixed worker count.

### Alternative 5: Aggregate child usage into the owner's raw tracker

- What: Re-record each child usage record in the owner tracker.
- Why rejected: Child agents already own their raw accounting and rollups. Preserve their rollups in the typed bulk response once instead of flattening or double-counting them.
