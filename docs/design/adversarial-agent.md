# Design Doc: Adversarial Agent

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-16
**Last Updated:** 2026-07-16

---

## 1. Overview

Add a first-class `AdversarialAgent` under `vidbyte/agents/adversarial.py`. The new agent is a `BaseAgent`-compatible facade that coordinates one supplied worker agent and a configurable number of supplied adversary-agent forks through deterministic sequential review rounds. Each run performs an initial worker pass, asks every adversary to challenge the current worker result, and then gives the combined challenges back to the same run-local worker for revision. The facade itself never owns or accepts a runner; model, provider, tool, middleware, output-schema, and permission configuration remain entirely on the supplied worker and adversary `BaseAgent` instances.

---

## 2. Goals & Non-Goals

### Goals

- Add `AdversarialAgent(BaseAgent)` as an explicit, public agent type rather than hiding adversarial behavior inside `BaseAgent`.
- Keep the primary implementation in `vidbyte/agents/adversarial.py`.
- Preserve the ordinary agent experience for `run`, `arun`, `run_sequentially`, `receive`, `history`, `last_prompt`, `last_reply`, `behavior`, `card`, registries, fixed pipelines, and `as_tool`.
- Require callers to supply an already configured worker `BaseAgent` and adversary prototype `BaseAgent`.
- Ensure `AdversarialAgent.__init__` has no `runner`, `runners`, provider, model, API-key, or catch-all `**kwargs` parameter.
- Add validated `num_adversaries` and `adversarial_rounds` settings, using the noun `adversary` consistently in the public API.
- Run the initial worker pass and every worker revision through one run-local worker fork so revisions retain the current run's worker history and tool state.
- Run adversaries sequentially in v1 against the same immutable round snapshot, avoiding an unsupported assumption that a fork-shared runner is concurrency-safe.
- Keep the worker authoritative: adversaries propose untrusted review input, while only the worker produces the final answer or implementation status.
- Preserve detailed, typed round artifacts through `last_result` while keeping final `AgentMessage` metadata bounded.
- Provide explicit partial-adversary-failure, timeout, cancellation, cleanup, tracing, forking, and subtype-preservation behavior.
- Add public exports, an `sdk.agents.adversarial(...)` factory, and coherent developer documentation.
- Implement the feature without adding new test files or persistent verification scripts, as selected by the `design-doc-no-tests` workflow.

### Non-Goals

- Do not add a `runner` parameter or any alias that lets the facade own a runner.
- Do not copy or fork the source of `BaseAgent`; reuse it through inheritance and composition.
- Do not modify `BaseAgent` to detect adversarial constructor arguments or delegate to an internal adversarial agent.
- Do not interrupt a worker inside one model call, tool call, or direct-runtime iteration.
- Do not add a new `AgentRuntimeType`, context-window algorithm, middleware hook, actor topology, or pipeline topology.
- Do not execute adversaries concurrently in v1.
- Do not let generated adversaries inherit the worker's write tools or permission policy implicitly.
- Do not add voting, candidate selection, synthesis by a separate judge, consensus, dynamic replanning, shared mutable ledgers, or early convergence detection.
- Do not add durable session serialization for in-progress adversarial rounds.
- Do not add automatic facade-level tools, MCP attachment, output schemas, continual tracing, or automatic handoff configuration; those execution concerns remain on child agents.
- Do not add a built-in worker, adversary model, provider, API key, or remote service.
- Do not add prompt-catalog assets in v1; the supplied worker and adversary agents own their system prompts, and the facade owns only deterministic tagged message envelopes.

---

## 3. Background & Context

The repository is a Python 3.11+ SDK built with setuptools. Its runtime dependencies are Pydantic 2 and `httpx`; the feature requires no additional dependency. `BaseAgent` in `vidbyte/agents/base.py` is the primary executable actor and already owns runner selection, tools, permissions, middleware, context-window behavior, MCP state, tracing, history, modality routing, structured output, and handoff behavior.

Specialized agents already use subclassing and composition instead of copying `BaseAgent`. `HandoffAgent` and `ContinualTraceAgent` constrain normal base-agent configuration for one role. `AggregateAgent` is the closest orchestration precedent: it subclasses `BaseAgent`, owns child agents, overrides `generate_reply()`, returns an ordinary `AgentMessage`, and overrides `fork()` so `as_tool()` does not erase the specialized behavior.

The existing pipeline layer is intentionally string-in/string-out. It can sequence or fan out complete agent invocations, but it does not retain the original task beside evolving output, typed per-round reviews, partial reviewer failures, worker authority, or facade state. The direct runtime and middleware layer own a single agent's model/tool loop; coupling adversary model calls into that inner loop would make the feature dependent on runtime internals and would not work uniformly across agent types.

`BaseAgent.fork()` provides history isolation but reuses configured runner and tool objects. Consequently, v1 adversary calls are sequential. Parallel execution would require an explicit independent-agent/factory contract or a documented concurrency guarantee from every runner. The same run-local worker fork is reused across worker passes so its revisions see the current run's earlier replies and tool effects.

The facade/child boundary is load-bearing. Because the facade has no runner, inherited methods that depend on facade-local execution configuration cannot silently appear supported. Tools, middleware, permissions, context-window algorithms, output schemas, and provider settings are configured on `worker` or `adversary`. Facade-level tool/MCP attachment fails explicitly. Explicit handoff remains possible by deriving a `HandoffAgent` from the configured worker when the caller does not supply a generator.

The current checkout contains unrelated untracked user files and nested worktrees. Phase 2 creates only this design document. After approval, implementation will start from updated `main` in a new isolated `feat/adversarial-agent` worktree and will not clean, revert, or reuse the current dirty checkout.

---

## 4. Requirements

### Functional Requirements

1. Create `vidbyte/agents/adversarial.py` and define `AdversarialAgent` in that module.
2. `AdversarialAgent` must subclass `BaseAgent` so it remains acceptable to `AgentRegistry`, `AgentTool`, and fixed pipeline node contracts.
3. `AdversarialAgent.__init__` must explicitly accept `name`, `system_prompt`, `worker`, `adversary`, `settings`, facade description/capability/metadata fields, and tracing configuration only.
4. `AdversarialAgent.__init__` must not declare `runner`, `runners`, `provider`, `model_name`, `api_key`, `temperature`, `runner_options`, or a catch-all `**kwargs` parameter.
5. Passing `runner=` or another undeclared execution-configuration argument to `AdversarialAgent` must raise Python's standard unexpected-keyword `TypeError` before any run begins.
6. The worker and adversary constructor arguments must each be `BaseAgent` instances; invalid objects must raise `ConfigurationError` during facade construction.
7. The supplied worker must own all implementation runner, provider, model, tools, middleware, permission, context-window, output-schema, and modality configuration.
8. The supplied adversary must own all review runner, provider, model, read tools, middleware, permission, context-window, output-schema, and modality configuration.
9. Define a frozen, slotted `AdversarialSettings` with `num_adversaries`, `adversarial_rounds`, `min_successful_adversaries`, `per_adversary_timeout`, `max_review_chars`, and `max_worker_output_chars`.
10. Default settings must be one adversary, one adversarial round, one required successful adversary, no per-adversary timeout, a 4,000-character review forwarding limit, and a 12,000-character worker-output forwarding limit.
11. `num_adversaries` and `adversarial_rounds` must be positive integers.
12. `min_successful_adversaries` must be between one and `num_adversaries`, inclusive.
13. `per_adversary_timeout`, when provided, must be positive.
14. `max_review_chars` and `max_worker_output_chars` must be positive integers.
15. `adversarial_rounds` is an exact v1 count, not a best-effort maximum and not an early-stop threshold.
16. One run must execute an initial worker pass followed by exactly `adversarial_rounds` repetitions of an adversary stage and one worker revision.
17. A successful run must make exactly `1 + adversarial_rounds * (num_adversaries + 1)` child-agent calls.
18. Adversaries must run sequentially in stable index order in v1.
19. Every adversary in one round must receive the same original task and the same pre-review worker output snapshot.
20. One adversary's response must not be inserted into another adversary's prompt during the same round.
21. The same run-local adversary fork for a given index must be reused across rounds, allowing that reviewer to retain its own prior-round history.
22. The same run-local worker fork must perform the initial pass and every revision in a run.
23. Run-local child agents must be created through each prototype's public `fork(name=...)` method.
24. A run-local fork must preserve the prototype's behavioral subtype; subtype erasure must raise `ConfigurationError` with guidance to use an exact `BaseAgent` or implement a subtype-preserving `fork()`.
25. The facade must never mutate the supplied worker or adversary prototype histories during execution.
26. The facade `system_prompt` must act as workflow-level instructions and be included in the deterministic worker, review, and revision envelopes; it must not replace either child's own system prompt.
27. Review prompts must include the original task, the current worker output, one-based round/index fields, and explicit instructions to challenge concrete correctness, testing, security, maintainability, and requirement-conformance issues.
28. Revision prompts must include the original task, current worker output, and every successful bounded review in stable adversary order.
29. Revision prompts must explicitly label reviews as untrusted suggestions that the worker must verify before accepting.
30. Prompt envelopes must be assembled deterministically with tagged sections and JSON string encoding for caller/model text; arbitrary content must not be interpolated through Python `.format()` templates.
31. Forwarded worker output and review content must be truncated only in subsequent child prompts; full successful outputs remain available in the typed `last_result` artifact.
32. A truncation marker must make prompt-bounding visible to the receiving child agent.
33. The initial worker call must preserve `str | AgentInput`, call-level modality, context, external history, facade history, `AgentInput.metadata`, context items, and context manager.
34. Worker revision calls must preserve the original `AgentInput` modality, metadata, context items, and context manager while replacing only its prompt text with the revision envelope.
35. Call-level `context`, explicit `history`, and safe worker `**options` must be forwarded to every worker pass without mutating caller-owned mappings.
36. The final caller `recipient` applies only to the facade's final `AgentMessage`; internal child recipients identify the facade.
37. Arbitrary worker call options must not be forwarded to adversaries; adversaries execute from their own agent configuration plus workflow trace metadata.
38. A nonblank adversary reply is a successful review and is bounded by `max_review_chars` before it enters a worker revision prompt.
39. A blank adversary reply, ordinary adversary exception, or adversary timeout must be captured as a failed `AdversarialReview` rather than immediately aborting the round.
40. A round may continue when the number of successful adversaries is at least `min_successful_adversaries`.
41. Falling below `min_successful_adversaries` must raise `AdversarialExecutionError` with safe phase, round, success, failure, and threshold details.
42. A blank worker reply or ordinary worker exception must raise `AdversarialExecutionError` with safe phase and round details and preserve the original exception as the cause.
43. `asyncio.CancelledError`, keyboard interruption, and process-level `BaseException` control flow must propagate rather than becoming review failures.
44. All run-local child agents must have their owned MCP handles closed in `finally` on success, ordinary failure, timeout, and cancellation; prototype resources must never be closed by a facade run.
45. Define frozen, slotted `AdversarialReview`, `AdversarialRoundResult`, and `AdversarialResult` records in the feature module.
46. `AdversarialReview` must record round index, adversary index/name, successful bounded content, optional error text, and safe metadata.
47. `AdversarialRoundResult` must record the full worker output reviewed in that round, ordered reviews, and the full revised worker output.
48. `AdversarialResult` must record the full initial output, ordered round results, final output, successful/failed review counts, and summary metadata.
49. `AdversarialAgent.last_result` must be reset at the start of a run and set only after a successful full run.
50. A successful facade run must return a normal `AgentMessage` whose sender is the facade name, recipient is the caller recipient, and content is the final worker output.
51. The final message must retain the final worker reply metadata and add a bounded `metadata["adversarial"]` summary containing configured counts, completed counts, successful/failed review counts, and child names without embedding full raw reviews.
52. One successful facade invocation must append exactly one final reply to facade history, regardless of the number of child calls.
53. `last_prompt` must retain the original unwrapped user task, `last_reply` must retain the facade reply, and `_active_prompt` must be cleared on success, failure, and cancellation.
54. The facade must copy the run-local worker's accumulated tool-call contexts after success so behavior inspection and explicit handoff can describe the complete worker activity.
55. The facade must open an `agent.run` trace with strategy `adversarial`, create bounded child spans for initial work, reviews, and revisions, and close the root trace on success, ordinary failure, and cancellation.
56. Adversarial trace/span attributes must include role, round, adversary index/name, and status but must not add raw reviews or worker-output bodies as span attributes.
57. `AdversarialAgent.fork()` must preserve the subtype, settings, worker/adversary prototypes, facade metadata, trace configuration, and optional facade history.
58. `AdversarialAgent.fork()` must expose only safe facade overrides (`name`, `system_prompt`, `metadata`, and `include_history`) and must not accept a runner override.
59. `as_tool()` must execute the entire adversarial workflow because `AgentTool` invokes the subtype-preserving facade fork.
60. `card()` must describe the facade, expose the worker's tool/MCP/modality capabilities, include safe worker/adversary identity and settings metadata, and never expose child system prompts, credentials, runner objects, or live resources.
61. Facade-level `add_tool()` and public MCP attach/builder methods must fail before side effects with actionable `ConfigurationError` messages directing callers to configure the worker or adversary.
62. Explicit `await facade.handoff(...)` must remain supported: a caller-supplied handoff generator is honored, while the default generator derives its runner configuration from the worker prototype and renders the facade's final transcript/tool calls.
63. The facade constructor must not accept automatic `handoff=`, `trace_option=`, or facade `output_schema=` configuration; callers configure structured output and continual tracing on child agents.
64. Export `AdversarialAgent`, `AdversarialSettings`, `AdversarialReview`, `AdversarialRoundResult`, and `AdversarialResult` from `vidbyte.agents` and the root `vidbyte` package.
65. Add `AgentClient.adversarial(**kwargs)` returning `AdversarialAgent` so `VidbyteSDK().agents.adversarial(...)` is available.
66. Add `AdversarialExecutionError` under the existing SDK error hierarchy as a subclass of `AgentExecutionError` and export it from `vidbyte.lib.errors`.
67. Update the package README, agent README, `llms.txt`, usage guides, and SDK reference skills to document the no-runner facade boundary and execution/cost formula.
68. Do not modify agent runtimes, runtime enums, middleware, pipelines, prompt catalog, provider adapters, session models, packaging configuration, or CI.
69. Do not add or modify test files and do not add a verification script.

### Non-Functional Requirements

- **Latency:** V1 child calls are deliberately sequential. Expected latency is approximately the sum of one initial worker call plus `adversarial_rounds * (num_adversaries + one worker revision)` calls.
- **Cost:** Documentation must expose the exact call formula and warn that tool/model cost grows linearly with both settings.
- **Scalability:** Settings validation prevents zero/negative loop shapes. V1 does not impose an arbitrary maximum count, but caller budgets/middleware on child agents remain authoritative.
- **Concurrency:** Mutable facade state follows the existing `BaseAgent` model and is not promised safe for overlapping calls. Callers use `fork()` for concurrent workflows. Adversaries are sequential because prototype forks may share runner/tool objects.
- **Security:** Adversary content, worker output, tool output, files, and retrieved content are untrusted. Tagged/JSON-delimited prompts improve structure but do not neutralize prompt injection. Callers must give adversaries read-only tools where review should not mutate the environment and must retain normal tool permission/sandbox controls on the worker.
- **Reliability:** Every configured loop is finite. Partial reviewer failure is explicit, minimum-success enforcement is deterministic, cancellation propagates, and all run-local child cleanup occurs in `finally`.
- **Idempotency:** Worker revisions may revisit write tools against an already changed workspace. Revision instructions must require inspection of current state and application of only necessary corrections; callers remain responsible for idempotent or safely retryable write tools.
- **Context bounds:** Per-review and worker-output forwarding limits keep round prompts bounded relative to `num_adversaries`. Child agents may independently use their existing token/compaction limits.
- **Observability:** The facade returns bounded summary metadata, retains typed full detail in `last_result`, and emits role/round spans without adding raw review bodies as attributes.
- **Compatibility:** This is additive. Existing `BaseAgent`, specialized agents, pipelines, registries, runtimes, prompts, tools, and namespace clients keep their current APIs.
- **Maintainability:** Non-trivial orchestration belongs in a small internal controller and deterministic renderer rather than one large `generate_reply()` method. Every implementation signature must remain on one physical line with the required intent comment immediately below it.
- **Packaging:** Existing `setuptools` package discovery already includes `vidbyte.agents.adversarial`; no `pyproject.toml` change is needed.
- **Verification:** No new tests are committed. Existing test discovery, compile/import/signature smoke checks, and package build checks must pass before the draft PR is opened.

---

## 5. High-Level Design

`AdversarialAgent` is a runnerless team facade. It subclasses `BaseAgent` for compatibility with existing SDK surfaces, but it never invokes the facade's `_run_direct()` path. Instead, it receives two explicit configured agent prototypes: `worker` and `adversary`. A run creates one isolated worker fork and `num_adversaries` isolated adversary forks, then passes them to a private run controller.

The controller implements a fixed, finite sequence. It first asks the worker to handle the original task. For each exact adversarial round, it freezes the current worker output for that round, invokes every adversary sequentially against that same snapshot, validates the minimum successful review count, and asks the same run-local worker to revise its work from all successful reviews. The final revised worker content becomes the facade reply. Failed individual reviews are recorded but are never presented to the worker as valid criticism.

The facade owns public lifecycle state, summary metadata, tracing, cards, subtype-preserving forking, and integration with registry/pipeline/tool surfaces. The child agents own actual model execution and all execution configuration. This boundary makes the absence of a facade `runner` honest: runner-dependent facade configuration is neither accepted nor silently ignored.

```text
caller: str | AgentInput
          |
          v
+------------------ AdversarialAgent(BaseAgent) ------------------+
| runner: none                                                    |
| worker prototype + adversary prototype + validated settings     |
|                                                                 |
| create run-local forks                                          |
|          |                                                      |
|          v                                                      |
|  worker pass 0                                                  |
|          |                                                      |
|          v                                                      |
|  round 1 snapshot                                               |
|      -> adversary 1 -> review                                   |
|      -> adversary 2 -> review        (sequential, same snapshot) |
|      -> adversary N -> review                                   |
|          |                                                      |
|          v                                                      |
|  worker revision 1                                              |
|          |                                                      |
|         ... exact configured rounds ...                         |
|          |                                                      |
|          v                                                      |
|  final worker output -> facade AgentMessage + last_result        |
+-----------------------------------------------------------------+
```

---

## 6. Detailed Design

### 6.1 Adversarial Agent Module And Value Contracts

**File(s):** `vidbyte/agents/adversarial.py`
**Type:** New file

#### What it does

Defines the public settings/result records, deterministic prompt renderer, private run controller, and `AdversarialAgent` facade in the user-requested module.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AdversarialSettings:
    num_adversaries: int = 1
    adversarial_rounds: int = 1
    min_successful_adversaries: int = 1
    per_adversary_timeout: float | None = None
    max_review_chars: int = 4000
    max_worker_output_chars: int = 12000

@dataclass(frozen=True, slots=True)
class AdversarialReview:
    round_index: int
    adversary_index: int
    adversary_name: str
    content: str = ""
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class AdversarialRoundResult:
    round_index: int
    reviewed_worker_output: str
    reviews: tuple[AdversarialReview, ...]
    revised_worker_output: str

@dataclass(frozen=True, slots=True)
class AdversarialResult:
    initial_worker_output: str
    rounds: tuple[AdversarialRoundResult, ...]
    final_output: str
    successful_review_count: int
    failed_review_count: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

class AdversarialAgent(BaseAgent):
    def __init__(self, *, name: str, system_prompt: str, worker: BaseAgent, adversary: BaseAgent, settings: AdversarialSettings | None = None, description: str = "", capabilities: Sequence[str] = (), agent_metadata: AgentMetadata | None = None, metadata: dict[str, Any] | None = None, tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None) -> None: ...
    async def generate_reply(self, message: str | AgentInput, *, modality: ModelModality | str | None = None, context: BaseContext | None = None, history: Sequence[AgentMessage] = (), recipient: str = "orchestrator", **options: Any) -> AgentMessage: ...
    def fork(self, *, name: str | None = None, system_prompt: str | None = None, metadata: dict[str, Any] | None = None, include_history: bool = False) -> AdversarialAgent: ...
```

The constructor intentionally has no `runner`, provider/model settings, tool settings, or `**kwargs` escape hatch.

#### Logic / Algorithm

1. `AdversarialSettings.__post_init__()` validates all counts, thresholds, limits, and timeout values with `ConfigurationError`.
2. `AdversarialAgent.__init__()` validates both prototypes, calls `BaseAgent.__init__()` only with facade identity/metadata/tracing fields, stores the prototypes/settings, creates a deterministic renderer, and initializes `last_result` to `None`.
3. `generate_reply()` normalizes the original prompt without mutating `AgentInput`, resets transient state, opens the root trace, and constructs a private run controller.
4. The controller creates uniquely named, run-local worker/adversary forks and validates subtype preservation.
5. The controller executes one initial worker pass.
6. For each one-based round, it stores the full worker snapshot, invokes adversaries sequentially, captures bounded successes/failures, enforces the minimum success threshold, renders one revision request, and executes the same worker fork again.
7. The controller returns a detailed internal outcome containing the public result, the final worker reply, and accumulated worker tool-call contexts.
8. The facade builds one final `AgentMessage`, updates public state exactly once, closes the root trace, and returns.
9. `finally` clears `_active_prompt` and closes every run-local child MCP resource without touching prototype resources.
10. `fork()` reconstructs the same facade subtype and optionally copies facade history. It never accepts runner overrides.

#### Edge Cases & Error Handling

- Empty or invalid facade identity continues to use `BaseAgent` validation.
- Invalid prototype types or settings raise `ConfigurationError` before external model calls.
- Subtype-erasing child forks fail before their first model call.
- Blank worker output is a worker-phase failure even if the underlying call did not raise.
- Blank, erroring, or timed-out adversaries create failed review records.
- Too few successful reviews raises `AdversarialExecutionError` after the round's configured adversaries have all been attempted.
- Ordinary child errors are chained as causes where one exception terminates the run.
- Cancellation and other `BaseException` control flow close traces/resources and propagate.
- A failed run leaves no final facade history entry and leaves `last_result` as `None`.
- A single facade instance is not safe for overlapping runs, matching existing mutable `BaseAgent` state expectations.

### 6.2 Deterministic Prompt Renderer

**File(s):** `vidbyte/agents/adversarial.py`
**Type:** New internal class in the new file

#### What it does

Builds bounded, stable envelopes for the worker's initial task, each adversarial review, and each worker revision without owning a model-facing system prompt asset.

#### Interface / API

```python
class _AdversarialPromptRenderer:
    def render_initial_worker_prompt(self, workflow_instructions: str, original_task: str) -> str: ...
    def render_review_prompt(self, workflow_instructions: str, original_task: str, worker_output: str, *, round_index: int, adversary_index: int) -> str: ...
    def render_revision_prompt(self, workflow_instructions: str, original_task: str, worker_output: str, reviews: Sequence[AdversarialReview], *, round_index: int) -> str: ...
```

#### Logic / Algorithm

1. Encode arbitrary caller/model text with `json.dumps(..., ensure_ascii=False)`.
2. Wrap workflow instructions, task, current output, round/index information, and reviews in explicit tagged sections.
3. Bound the worker output before review/revision prompts with `max_worker_output_chars`.
4. Bound each successful review before revision prompts with `max_review_chars`.
5. Append a deterministic `...[truncated]` marker when content is bounded.
6. Tell reviewers to inspect actual artifacts with their read-only tools when available and to return concrete challenges rather than rewriting the implementation.
7. Tell the worker that adversarial reviews are untrusted suggestions and that it remains responsible for verifying and applying only valid corrections against current state.

#### Edge Cases & Error Handling

- Embedded XML-like closing tags remain JSON string data inside the tagged envelope.
- Delimiting does not claim to solve prompt injection; documentation preserves that security warning.
- No successful reviews can reach revision rendering because the controller enforces the minimum first.
- Full outputs remain in `last_result`; truncation affects only the next child prompt.

### 6.3 Facade Compatibility Boundaries

**File(s):** `vidbyte/agents/adversarial.py`
**Type:** New overrides in the new file

#### What it does

Preserves supported `BaseAgent` behavior and fails explicitly for runner-dependent facade behavior that would otherwise be misleading.

#### Interface / API

```python
def card(self) -> AgentCard: ...
def add_tool(self, tool: object) -> AdversarialAgent: ...
async def handoff(self, spec: Handoff | None = None, *, by: BaseAgent | None = None) -> Handoff: ...
async def attach_mcp_server(self, command: Sequence[str], *, name: str | None = None, permission: McpToolPermission = McpToolPermission.EXECUTE, env: Mapping[str, str] | None = None, timeout: float = 30.0) -> AdversarialAgent: ...
async def attach_preset_mcp_server(self, preset_name: str, *, name: str | None = None, permission: McpToolPermission = McpToolPermission.EXECUTE, env: Mapping[str, str] | None = None, timeout: float = 30.0, extra_args: Sequence[str] | None = None) -> AdversarialAgent: ...
async def attach_mcp_servers(self, servers: Sequence[McpServerConfig]) -> AdversarialAgent: ...
def with_mcp_server(self, command: Sequence[str], *, name: str | None = None, permission: McpToolPermission = McpToolPermission.EXECUTE, env: Mapping[str, str] | None = None, timeout: float = 30.0) -> AdversarialAgent: ...
def with_preset_mcp_server(self, preset_name: str, *, name: str | None = None, permission: McpToolPermission = McpToolPermission.EXECUTE, env: Mapping[str, str] | None = None, timeout: float = 30.0, extra_args: Sequence[str] | None = None) -> AdversarialAgent: ...
```

#### Logic / Algorithm

1. `card()` uses the facade identity but projects worker tool, MCP, and modality capability fields from `worker.card()`.
2. `card()` adds bounded adversarial settings and child names to copied metadata.
3. `add_tool()` raises `ConfigurationError` directing the caller to `worker.add_tool(...)` or `adversary.add_tool(...)`.
4. Every MCP attach/builder override raises before starting a subprocess or mutating pending configuration.
5. `handoff(by=...)` delegates to the supplied generator through the existing source-run rendering contract.
6. `handoff()` without `by` builds a `HandoffAgent` from the configured worker prototype, then asks it to summarize the facade's final run.
7. Inherited `run`, `arun`, sequential-run helpers, `receive`, `behavior`, and `as_tool` continue through the overridden `generate_reply()`/`fork()` methods.

#### Edge Cases & Error Handling

- Calling facade-level tool/MCP methods always raises before side effects.
- Default handoff fails with the existing agent error chain if the worker itself lacks executable or primitive provider/model configuration.
- Child system prompts, credentials, runner objects, and live handles never appear in `card()` metadata.

### 6.4 Adversarial Error Type

**File(s):** `vidbyte/lib/errors/base.py`, `vidbyte/lib/errors/__init__.py`
**Type:** Modified

#### What it does

Adds a feature-specific runtime error while preserving the common `AgentExecutionError` catch boundary.

#### Interface / API

```python
class AdversarialExecutionError(AgentExecutionError):
    """Raised when an adversarial run cannot produce a valid final worker result."""
```

#### Logic / Algorithm

1. Define the subclass beside `AggregateExecutionError`.
2. Export it from `vidbyte.lib.errors`.
3. Populate only safe structured details such as facade/child names, phase, round/index, error type, counts, and thresholds.

#### Edge Cases & Error Handling

- Raw prompts, credentials, full reviews, and full child outputs never enter error details.
- Callers catching `AgentExecutionError` continue to catch adversarial failures.

### 6.5 Public Exports And Namespace Factory

**File(s):** `vidbyte/agents/__init__.py`, `vidbyte/agents/client.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Makes the new facade and its public value contracts available from normal agent/root imports and the SDK namespace client.

#### Interface / API

```python
from vidbyte import AdversarialAgent, AdversarialResult, AdversarialReview, AdversarialRoundResult, AdversarialSettings

class AgentClient:
    def adversarial(self, **kwargs: Any) -> AdversarialAgent: ...
```

#### Logic / Algorithm

1. Import and add all five primary feature types to `vidbyte.agents.__all__`.
2. Add the common feature types to the root convenience import and `__all__` surface.
3. Add a lazy feature import inside `AgentClient.adversarial()` consistent with the existing aggregate/continual-trace factories.
4. Forward keyword arguments unchanged so the explicit `AdversarialAgent` constructor remains the authoritative validator.

#### Edge Cases & Error Handling

- `sdk.agents.adversarial(runner=...)` reaches the explicit constructor and raises unexpected-keyword `TypeError`; the factory does not translate or hide it.
- Existing exports and factories remain unchanged.

### 6.6 Developer Documentation And Skills

**File(s):** `README.md`, `llms.txt`, `vidbyte/agents/README.md`, `skills/usage/create_agents.md`, `skills/usage/available_features.md`, `skills/vidbyte-sdk/adversarial-agent.md`, `skills/vidbyte-sdk/SKILL.md`, `skills/vidbyte-sdk-doc/SKILL.md`, `skills/sdk/SKILL.md`
**Type:** One new guide; remaining files modified

#### What it does

Documents construction, runner ownership, call order/cost, settings semantics, failure policy, tool boundaries, and selection guidance against pipelines, aggregate agents, runtimes, and middleware.

#### Interface / API

```python
worker = BaseAgent(name="worker", system_prompt="Implement and verify.", provider="openai", model_name="gpt-5", tools=worker_tools)
adversary = BaseAgent(name="reviewer", system_prompt="Challenge concrete defects; never write.", provider="openai", model_name="gpt-5-mini", tools=read_only_tools)

reviewed = AdversarialAgent(
    name="reviewed-worker",
    system_prompt="Alternate implementation and adversarial review while keeping the worker authoritative.",
    worker=worker,
    adversary=adversary,
    settings=AdversarialSettings(num_adversaries=2, adversarial_rounds=2),
)

reply = await reviewed.arun("Implement the requested change.")
```

#### Logic / Algorithm

1. Add a concise root README example and decision guidance.
2. Add the feature to the agent package map and explain that tools/MCP belong on child agents.
3. Add a compressed equivalent section to `llms.txt`.
4. Add a dedicated SDK skill guide containing API, lifecycle, settings, failures, cost formula, read-only reviewer guidance, and extension boundaries.
5. Route the master SDK skills and usage guides to the dedicated guide and update public API/package inventories.
6. Show no `runner` on `AdversarialAgent` in every example.

#### Edge Cases & Error Handling

- Documentation must not imply live mid-iteration interruption.
- Documentation must not describe `adversarial_rounds` as a maximum or promise early stopping.
- Documentation must state that repeat worker passes can repeat write-side effects and that reviewers need explicitly read-only capabilities when mutation is undesirable.

### 6.7 Existing Verification Without New Tests

**File(s):** N/A - no test or verification-script files are created or modified.
**Type:** N/A - command-only validation during implementation

#### What it does

Uses the repository's existing verification surfaces plus ephemeral import/signature smoke commands to validate the additive feature without committing new tests.

#### Interface / API

```powershell
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "import inspect; from vidbyte import AdversarialAgent; assert 'runner' not in inspect.signature(AdversarialAgent).parameters"
python -c "from vidbyte import AdversarialAgent, AdversarialSettings, VidbyteSDK; assert callable(VidbyteSDK().agents.adversarial)"
python -m build
```

#### Logic / Algorithm

1. Compile the package.
2. Run the complete existing unit-test suite to detect regressions.
3. Inspect the public constructor signature to prove the runner exclusion.
4. Smoke-import root/package types and namespace factory.
5. Run an ephemeral fake-agent success/failure/fork smoke in the shell without saving a script.
6. Build the source/wheel distributions and inspect that the new module and guide are included appropriately.

#### Edge Cases & Error Handling

- Any failing existing test, import, signature check, smoke run, or package build blocks PR creation.
- The explicit absence of committed feature tests is a known risk accepted by this workflow; it is not represented as equivalent to dedicated regression coverage.

---

## 7. Data Model Changes

### 7.1 Adversarial In-Memory Value Contracts

**Change type:** New

```python
AdversarialSettings
AdversarialReview
AdversarialRoundResult
AdversarialResult
```

These are frozen, slotted, in-memory Python records defined in `vidbyte/agents/adversarial.py`. Mapping fields are copied at boundaries but may still contain caller-owned opaque values; the records do not claim recursive immutability or persistence serialization.

**Migration strategy:**

- Forward migration: N/A - additive in-memory types with no prior representation.
- Rollback plan: Remove the feature exports/module and revert callers to ordinary explicitly wired `BaseAgent` calls.

### 7.2 Database, Session, And Serialized Schemas

**Change type:** N/A - no database, migration, session, checkpoint, wire protocol, or persistent storage schema changes.

**Migration strategy:**

- Forward migration: N/A.
- Rollback plan: N/A.

---

## 8. API Changes

### 8.1 Python `AdversarialAgent` Constructor

**Change type:** New

**Request:**

```python
AdversarialAgent(
    name="reviewed-worker",
    system_prompt="Workflow-level adversarial instructions.",
    worker=configured_worker,
    adversary=configured_adversary,
    settings=AdversarialSettings(num_adversaries=2, adversarial_rounds=2),
)
```

The request deliberately contains no runner/provider/model parameters. Those belong on `configured_worker` and `configured_adversary`.

**Response:**

```python
AgentMessage(
    sender="reviewed-worker",
    recipient="orchestrator",
    content="<final worker output>",
    metadata={
        "adversarial": {
            "num_adversaries": 2,
            "adversarial_rounds": 2,
            "completed_rounds": 2,
            "successful_review_count": 4,
            "failed_review_count": 0,
            "worker_name": "worker",
            "adversary_names": ("adversary-1", "adversary-2"),
        }
    },
)
```

**Error cases:**

| Error | Condition |
|--------|-----------|
| `TypeError` | `runner=`, provider/model fields, or another undeclared constructor argument is passed |
| `ConfigurationError` | Worker/adversary is invalid, settings are invalid, or a child fork erases its subtype |
| `AdversarialExecutionError` | Worker fails/returns blank, a round has too few successful adversaries, or orchestration cannot finish |
| Propagated `BaseException` | Cancellation, keyboard interrupt, or process-level control flow occurs |

### 8.2 Python SDK Namespace Factory

**Change type:** New

**Request:**

```python
agent = VidbyteSDK().agents.adversarial(
    name="reviewed-worker",
    system_prompt="Keep the worker authoritative.",
    worker=worker,
    adversary=adversary,
    settings=AdversarialSettings(),
)
```

**Response:**

```python
assert isinstance(agent, AdversarialAgent)
```

**Error cases:** Same as the constructor because the factory forwards arguments unchanged.

### 8.3 HTTP Or External Service Endpoints

**Change type:** N/A - this SDK feature introduces no HTTP route, RPC method, webhook, or external service endpoint.

---

## 9. File Change Manifest

Complete list of every file expected to change during implementation:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/adversarial-agent.md` | Approved source-of-truth design document |
| CREATE | `vidbyte/agents/adversarial.py` | Public facade, settings/results, renderer, and sequential controller |
| CREATE | `skills/vidbyte-sdk/adversarial-agent.md` | Dedicated implementation and usage guide |
| MODIFY | `vidbyte/agents/__init__.py` | Export adversarial public types |
| MODIFY | `vidbyte/agents/client.py` | Add `sdk.agents.adversarial(...)` factory |
| MODIFY | `vidbyte/__init__.py` | Add root convenience exports |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `AdversarialExecutionError` |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export the new error through the stable error package |
| MODIFY | `vidbyte/agents/README.md` | Document the specialized agent and runnerless facade boundary |
| MODIFY | `README.md` | Add primary usage and selection guidance |
| MODIFY | `llms.txt` | Add compressed public behavior/API documentation |
| MODIFY | `skills/usage/create_agents.md` | Show explicit worker/adversary construction |
| MODIFY | `skills/usage/available_features.md` | Add the feature and cost/lifecycle summary |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Add package map/routing and specialized-agent rules |
| MODIFY | `skills/vidbyte-sdk-doc/SKILL.md` | Update comprehensive public API and architecture reference |
| MODIFY | `skills/sdk/SKILL.md` | Update consolidated SDK package/public feature inventory |

Files to create: **3**. Files to modify: **13**. Files to delete: **0**.

Explicit no-change areas:

- `vidbyte/agents/base.py`
- `vidbyte/agents/runtime.py` and `vidbyte/agents/runtimes/**`
- `vidbyte/middleware/**`
- `vidbyte/pipelines/**`
- `vidbyte/prompts/**`
- `vidbyte/providers/**`
- `vidbyte/sessions/**`
- `tests/**`
- `scripts/**`
- `pyproject.toml`
- `.github/workflows/publish.yml`

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python 3.11+ | `asyncio.wait_for`, dataclasses, JSON-safe envelope rendering, immutable tuples/mappings | Low; already required |
| `BaseAgent` and agent contracts | Current repository implementation | Child execution, history, tool loop, forking, cards, handoff, and facade compatibility | Medium; shallow fork shares runner/tool objects, mitigated by sequential reviewers |
| Existing tracer protocol | Current repository implementation | Root adversarial trace and phase spans | Low; no provider-specific dependency |
| Existing SDK errors | Current repository implementation | Safe configuration/runtime error hierarchy | Low |
| External model/provider services | Whatever child agents already configure | Actual worker and adversary calls | Caller-owned; no new service or credential path |

No new runtime dependency or external endpoint is introduced.

---

## 11. Rollout & Deployment

- This is an additive library feature with no database migration, service deployment, or feature flag.
- Existing users are unaffected until they import or construct `AdversarialAgent`.
- After explicit approval, create a clean isolated worktree/branch named `feat/adversarial-agent` from updated `main`; do not implement in the current dirty checkout.
- Commit this approved design document first before implementation code.
- Implement in this order: error type and core module; package/root exports and factory; developer docs/skills; verification; structured self-critique/refinement.
- Run existing tests, compile/import/signature smoke checks, ephemeral fake-agent scenarios, and package build checks before pushing.
- Open a draft PR targeting `main` with the design document as the PR body.
- This feature is intentionally non-breaking, but documentation must make the no-runner constructor boundary prominent so users do not expect a drop-in `BaseAgent(..., runner=...)` signature.
- Rollback is a normal revert of the feature commits. Because no existing path delegates to the feature, removal restores the pre-feature package without data cleanup.

---

## 12. Open Questions

N/A - no unresolved product decision blocks implementation. Approval of this document confirms these v1 choices:

- The facade has no runner or provider/model constructor path.
- Callers supply configured worker and adversary `BaseAgent` prototypes.
- Adversaries execute sequentially.
- `adversarial_rounds` is exact.
- At least one adversary and one round are required.
- Individual adversary failures are tolerated only up to `min_successful_adversaries`.
- The worker remains authoritative and produces the final output.
- Facade-level tools/MCP are rejected; configure child agents instead.
- No committed feature tests or verification scripts are added.

Potential follow-up designs, not v1 blockers:

- Independent adversary factories and bounded parallel review.
- Structured review verdicts and deterministic early convergence.
- Distinct adversarial lenses/personas rather than repeated forks of one prototype.
- Artifact/diff snapshot providers for reviewing implementation state without reviewer tools.
- Durable round/session persistence and resumability.

---

## 13. Alternatives Considered

### Alternative 1: Copy `BaseAgent` Into `adversarial.py`

- What: Duplicate the base constructor, runtime dispatch, tools, MCP, tracing, context, and history code, then insert adversarial stages.
- Why rejected: It would immediately create two implementations of core agent behavior, drift as `BaseAgent` evolves, and make security/runtime bug fixes easy to miss in one copy.

### Alternative 2: Give `AdversarialAgent` Its Own Runner Parameter

- What: Make the facade a drop-in `BaseAgent` constructor plus adversarial settings and use its runner for the worker and/or reviewers.
- Why rejected: The user explicitly does not want a runner parameter on the adversarial class. It also conflates facade orchestration with worker execution, makes tool/history ownership ambiguous, and encourages unsafe runner sharing across reviewers.

### Alternative 3: Automatically Derive Adversaries From The Worker

- What: Fork the worker N times, replace its system prompt, and treat those forks as reviewers.
- Why rejected: `BaseAgent.fork()` preserves the worker's tools and permission policy. Reviewers could silently inherit write/execute capabilities, while specialized worker subtypes may be erased. Requiring an explicit adversary prototype makes authority and access visible.

### Alternative 4: Implement It As Middleware

- What: Run adversary calls from `after_iteration` or inject review messages before later model calls.
- Why rejected: Middleware is deterministic policy code around one direct runtime. A second model-driven agent inside middleware couples the feature to runtime-private state, complicates accounting/retry/cancellation, and does not apply cleanly to every child-agent subtype.

### Alternative 5: Implement It As A New Agent Runtime

- What: Add an `ADVERSARIAL` runtime type and place orchestration in `vidbyte/agents/runtimes/`.
- Why rejected: Runtimes own one agent's inner execution paradigm. This feature crosses ordinary agent boundaries and must support workers/adversaries that already select their own linear, MCTS, aggregate, or actor behavior when their forks preserve subtype.

### Alternative 6: Compose Existing Pipelines

- What: Build a repeated `SequentialPipeline`/`ParallelPipeline` of worker and reviewer stages.
- Why rejected: Pipelines pass only strings, cannot preserve original task plus typed rounds/failures, and cannot express the invariant that N reviewers inspect one identical snapshot before one authoritative worker revision.

### Alternative 7: Use A Paradigm Harness Instead Of An Agent

- What: Add an adversarial harness under `vidbyte/paradigms/` returning a custom result.
- Why rejected: The request is for another first-class agent compatible with registries, pipelines, `AgentTool`, `run`/`arun`, history, and cards. A harness would not satisfy that public substitution goal.

### Alternative 8: Run Adversaries Concurrently In V1

- What: Use `asyncio.gather` for the N reviews in each round.
- Why rejected: Forked base agents may share one explicit runner and tool objects. The repository does not promise those objects are concurrency-safe. Sequential execution gives deterministic ordering and safe v1 semantics; a later factory-based API can enable parallelism explicitly.

### Alternative 9: Add Structured Verdicts And Early Stop Immediately

- What: Require each adversary to return a schema with accept/revise verdicts and stop when all accept.
- Why rejected: The supplied adversary may already own an output schema or specialized behavior. Plain nonblank review text keeps v1 composable, while exact rounds make cost/call semantics deterministic. Structured convergence deserves a separate compatible extension.
