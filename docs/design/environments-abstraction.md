# Design Doc: RL Environment Abstraction (`vidbyte.environments`)

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-17
**Last Updated:** 2026-07-17

---

## 1. Overview

This change adds a first-class `vidbyte.environments` package that turns the SDK's existing
agent, tool, context, middleware, and eval primitives into sellable RL-environment building
blocks. An `Environment` bundles a seeded task generator, a deterministically materialized
world (workspace), an authoritative tool surface, and an out-of-band verifier that scores the
final world state into a `Reward`. A fully declarative, JSON-serializable `HarnessSpec`
describes how an agent is assembled from every configurable SDK surface (provider/model,
runtime, loop settings, context-window algorithms and their per-algorithm settings, context
primitives, prebuilt tools, middleware, tracing, output schema), so pass rates are always
attributable to a recorded configuration and sweepable across configurations. A rollout
runner executes `(spec, task)` pairs, records structured `RolloutRecord`s to JSONL, and a
calibration helper aggregates pass rates into spec sheets. A verifier audit kit stress-tests
environments with scripted adversarial baselines. A repo skill (`skills/environments/SKILL.md`)
documents how the abstraction is built and how to author new environments.

---

## 2. Goals & Non-Goals

### Goals
- Define the `Environment` contract: `generator`, `setup()`, `tools()`, `verify()`, `teardown()`, with seeded deterministic materialization (reset = re-`setup` from `task.seed`).
- Define `EnvTask`, `EnvSession`, `Reward`, `CriterionResult`, `RolloutRecord`, `CalibrationReport` dataclasses.
- Define a **complete** `HarnessSpec` (pydantic v2, versioned, JSON-round-trippable) covering every configurable SDK surface exposed by `BaseAgent` and its satellite config objects.
- Implement `HarnessSpecResolver` that turns a `HarnessSpec` into a live `BaseAgent` using existing SDK registries and dispatch tables, with fail-fast validation that mirrors `BaseAgent`'s own constraint rules.
- Implement `EnvironmentRunner` (`arollout`, `acalibrate`) and JSONL `RolloutRecorder`.
- Implement the environment **authority rule**: the environment filters requested tools; specs select within what the environment permits.
- Implement `EnvironmentAudit` with scripted baselines (do-nothing, echo) and verify-twice determinism checking.
- Implement `EnvironmentRegistry` mirroring `vidbyte/lib/registries` conventions.
- Wire the package into `VidbyteSDK` (`sdk.environments`) and `vidbyte.__init__` exports.
- Add `skills/environments/SKILL.md` explaining how the abstraction is built and used.
- Add `vidbyte/environments/README.md` following the module-README convention.

### Non-Goals
- No concrete environment implementations (the SE harness environment is a follow-up PR).
- No RL trainer, no token-logprob capture, no `verifiers`-hub adapter (bolt-on later).
- No container/Podman isolation (workspace-dir scoping via `FileSystemToolConfig` roots only).
- No live-state snapshotting of external systems; worlds are built from seeds.
- No billing/metering service integration; `Reward.passed` is merely the billable signal.
- No SFT/DPO dataset exporters in this PR (records are stored in an export-friendly shape).
- No new test files (per `/design-doc-no-tests`); existing CI must stay green.

---

## 3. Background & Context

The Vidbyte business model (harness-as-a-service → environments-as-a-product) requires three
contracts baked into the SDK before the first harness ships: (1) every harness has a
`verify()` that scores final world state; (2) tools are written against dual-backend
configs so a run can execute live or in a sandbox — `FileSystemToolConfig(root=...,
backend=...)` already satisfies this for filesystem tools; (3) every run is recorded in a
structured format with task, config, trajectory, verified outcome, and consent level.

Harvey's open-source LAB benchmark (filesystem-first tasks + rubric verifier + agent loop)
validates the shape. What the SDK adds beyond LAB is the declarative harness axis: because
Vidbyte owns the harness framework, a recorded pass rate can be attributed to a specific
combination of runtime, context algorithm, middleware stack, and toolset — ablation data that
neither pure environment shops nor labs can produce.

Current state: `vidbyte.harnesses` is an intentionally minimal namespace (`HarnessClient`
placeholder). `vidbyte.evals` grades prompt→reply pairs but has no concept of world state.
Nothing in the SDK models tasks-with-seeds, workspaces, or state-inspecting verifiers.

Constraints and dependencies discovered in the repo audit:

- `BaseAgent.__init__` is the canonical configuration surface (`vidbyte/agents/base.py:55-94`).
- Non-linear runtimes (MCTS, actor topologies) reject middleware, continual tracing,
  non-default context algorithms, and aggregation (`vidbyte/agents/base.py:107-143`).
- `AgentLoopSettings` fields (`vidbyte/agents/settings/loop.py`): `max_iterations`,
  `max_tokens`, `max_tool_calls`, `max_parallel_tool_calls`, `max_retries`,
  `timeout_seconds`, `context_window_budget`, `compaction_trigger_tokens`,
  `compaction_target_tokens`, `allowed_tools`.
- Runtime configs (`vidbyte/agents/runtimes/configs.py`): `LinearRuntime`,
  `MctsSearchRuntime`, `ActorRuntime(topology, dynamic_actors, max_loop,
  termination_mode, worker_model, include_actors)`.
- Context-window algorithm presets (`vidbyte/context/presets.py`): `default`,
  `raw_tool_outputs`, `compact_tool_outputs`, `hide_tool_outputs`, `no_raw_tool_outputs`,
  `reflexion`, `multi_provider_agentic_grader`, `trajectory_checkpoints`,
  `problem_space_search`, `error_correction`; each algorithm dataclass exposes typed
  settings fields (audited in `vidbyte/context/algorithms/*.py`).
- Context primitives (`vidbyte/context/primitives`): Text/File/GitDiff/Document/
  Environment/Memory (documents), Task/Progress/Plan (tasks), Artifact/Response/ToolCall
  (records), Reflexion/TrajectoryCheckpoint (checkpoints), ErrorCorrection/
  ProblemSpaceSearch (reasoning); managed via `ContextManager.upsert(placement=...)`.
- 19 builtin middleware classes (`vidbyte/middleware/builtins/__init__.py`).
- Prebuilt tools: `vidbyte/tools/builtins` (code execution, code search, patch, context,
  context primitives, handoff, MCP, memory providers, reflexion, trajectory checkpoint)
  and the root-scoped filesystem suite (`vidbyte/tools/filesystem`).
- Tracing: `TraceOption` (`vidbyte/lib/dataclasses/trace.py:153`) with `TraceMode`,
  `TraceSchema`, `every_n_iterations` (positive), `max_trace_iterations` (1..3); prebuilt
  `ActionTraceModel` schema; `DebugTracer` in `vidbyte/trace/debug.py`.
- Providers validated via `ProviderModelRegistry` (`vidbyte/lib/registries/models.py`);
  API keys resolve from environment variables, never from stored config.
- Registry conventions in `vidbyte/lib/registries/*` (agents, models, runtimes, tools,
  prompts, actors).
- CI: `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py` (exists on
  `origin/main`; stages: tracked-bytecode check, `compileall`, full `pytest`, package
  build/inspect/install).
- House style: Context Protocol Header docstring per file, class-first design, one-line
  signatures, mandatory 1-2 line comment under every signature, module `README.md`,
  skills as `skills/<name>/SKILL.md` with an HTML-comment Context Protocol Header.

---

## 4. Requirements

### Functional Requirements
1. `EnvTask` is a frozen dataclass with `id`, `instructions`, `params`, `seed`, `difficulty`, `metadata`; two generator calls with the same seed and knobs MUST produce equal tasks.
2. `Environment` is an ABC with abstract `setup(task) -> EnvSession`, `verify(session, trajectory) -> Reward` (async), `teardown(session)`, plus concrete `tools(session, requested=None) -> Tools` implementing the authority rule, and attributes `name`, `version`, `generator`.
3. `EnvSession` carries `task`, `workspace_dir`, an environment-owned `Tools` catalog, a `verifier_state` mapping reserved for verifier-only data (never exposed to agent tools), and `metadata`.
4. `TaskGenerator` is a `Protocol` with `generate(seed, **knobs) -> EnvTask`; `StaticTaskSet` adapts a fixed sequence of `EnvTask`s to the protocol and to iteration.
5. `Reward` carries `score` (float 0..1 partial credit), `passed` (bool all-pass), and `criteria` (tuple of `CriterionResult(name, passed, score, detail)`); `Reward.from_criteria()` computes `score` as the mean criterion score and `passed` as all-criteria-passed.
6. `HarnessSpec` is a pydantic v2 model, JSON-serializable via `model_dump()`/`model_validate()`, with `spec_version` defaulting to `"1"`, and covers: system prompt (literal or prompt-catalog ref), model/provider/temperature/modality/runner options, runtime kind + actor settings, all ten `AgentLoopSettings` fields, context-window algorithm preset + per-algorithm settings + tool-result admission overrides, context primitives (kind + fields + placement + managed flag), middleware (name + settings, ordered), requested tools (name + settings, ordered), trace (tracer choice + continual trace option), output schema, and metadata.
7. `HarnessSpec` validation MUST reject, at spec-construction time: unknown middleware names, unknown tool names, unknown context-primitive kinds, unknown context-algorithm presets, algorithm settings keys not present on the target algorithm dataclass, non-linear runtime combined with middleware / continual trace / non-default algorithm, and invalid provider or model per `ProviderModelRegistry`.
8. `HarnessSpecResolver.build_agent(spec, session)` returns a configured `BaseAgent` whose tools are `environment.tools(session, requested=resolved_spec_tools)` — the environment filters; requested tools never bypass it.
9. `EnvironmentRunner.arollout(...)` accepts either a `HarnessSpec` or a prebuilt agent-like object (anything with `arun`), executes setup → build → run → verify → teardown (teardown guaranteed via `finally`), and returns a `RolloutRecord`.
10. `RolloutRecord` captures `env_name`, `env_version`, `task`, `harness` (full spec dump or `{"opaque": ...}` marker), `trajectory` (serialized messages and tool calls), `reward`, `consent`, `interruptions`, `cost` (tokens/latency where available), `started_at`/`finished_at`, and `record_version`.
11. `RolloutRecorder` appends records as JSON lines and loads them back; file writes are append-only and each line is independently parseable.
12. `EnvironmentRunner.acalibrate(...)` runs N seeded tasks per spec and returns a `CalibrationReport` with per-spec pass rate, mean score, and per-difficulty breakdown.
13. `EnvironmentAudit.arun(env, ...)` executes the do-nothing and echo baselines plus a double-verify determinism check, and returns an `AuditReport` whose `ok` is true only when baselines score ≤ a configurable threshold and repeated verification is reward-identical.
14. `EnvironmentRegistry` provides `register`, `get`, `names`, `create` mirroring `vidbyte/lib/registries` conventions.
15. `VidbyteSDK().environments` exposes an `EnvironmentsClient`; key public names are exported from `vidbyte.__init__`.
16. `skills/environments/SKILL.md` documents the abstraction (anatomy, seeded materialization, authority rule, HarnessSpec coverage tables, authoring walkthrough, audit workflow) in the established skill format.

### Non-Functional Requirements
- **Determinism:** no wall-clock or RNG use in the core package outside recorded fields; all randomness flows through `task.seed`.
- **Serialization safety:** specs and records never contain API keys or secrets; keys resolve at runtime from environment variables via `ProviderModelRegistry`.
- **Performance:** rollouts are independent; the runner supports bounded concurrency via a semaphore (same pattern as `EvalRunner`).
- **Observability:** records capture enough to re-grade later (full trajectory + spec + seed); runner failures surface as failed records, not crashes (mirrors `EvalRunner` philosophy).
- **Reliability:** `teardown` always runs; verifier exceptions produce `Reward(score=0.0, passed=False)` with the error captured in a criterion detail.
- **Style/CI:** Context Protocol Headers, class-first, one-line signatures with mandatory under-signature comments; `python scripts/run_ci.py` green.

---

## 5. High-Level Design

The package sits beside `vidbyte.evals` and reuses its philosophy (plain Python, local-first,
errors become failed results) while adding the state axis evals lack. Data flows:

```
TaskGenerator --seed--> EnvTask
                          |
             Environment.setup(task) ----> EnvSession (workspace + env Tools + verifier_state)
                          |
HarnessSpec --HarnessSpecResolver.build_agent(spec, session)--> BaseAgent
                          |                (tools = env.tools(session, requested))
             agent.arun(task.instructions)
                          |
             Trajectory (agent.history + tool call contexts)
                          |
             Environment.verify(session, trajectory) --> Reward
                          |
             RolloutRecord --RolloutRecorder--> JSONL
                          |
             EnvironmentRunner.acalibrate --> CalibrationReport (spec sheet)
```

Three design decisions drive the file layout. First, **spec-as-data**: every knob is a name +
settings dict validated against dispatch tables, because live objects cannot be recorded,
diffed, swept, or sent over a wire; the resolver is the single place names become objects.
Second, **environment authority**: the tool surface is part of the environment's identity
(and version), so `Environment.tools()` filters spec requests rather than unioning them.
Third, **seeded materialization instead of snapshots**: `setup(task)` must be a pure function
of `task`, making reset trivial and rollouts parallelizable without snapshot infrastructure.

The resolver deliberately mirrors — but does not replace — `BaseAgent` validation: it
fail-fasts on the known incompatibilities (non-linear runtime × middleware/trace/algorithm) so
sweep authors get spec-time errors, and `BaseAgent` remains the final authority at build time.

---

## 6. Detailed Design

### 6.1 Environment core types

**File(s):** `vidbyte/environments/types.py`
**Type:** New file

#### What it does
Defines the typed data boundary for the package: tasks, sessions, rewards, rollout records,
calibration reports.

#### Interface / API
```python
@dataclass(frozen=True)
class EnvTask:
    """Single environment task minted by a TaskGenerator."""
    id: str
    instructions: str
    params: Mapping[str, Any] = field(default_factory=dict)
    seed: int = 0
    difficulty: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass
class EnvSession:
    """Live materialized world for one rollout attempt."""
    task: EnvTask
    workspace_dir: Path
    tools: Tools
    verifier_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class CriterionResult:
    name: str
    passed: bool
    score: float
    detail: str = ""

@dataclass(frozen=True)
class Reward:
    score: float
    passed: bool
    criteria: tuple[CriterionResult, ...] = ()

    @classmethod
    def from_criteria(cls, criteria: Sequence[CriterionResult]) -> "Reward": ...
    @classmethod
    def failure(cls, detail: str) -> "Reward": ...

@dataclass(frozen=True)
class RolloutRecord:
    record_version: str
    env_name: str
    env_version: str
    task: EnvTask
    harness: Mapping[str, Any]          # spec.model_dump() or {"opaque": repr-ish label}
    trajectory: tuple[Mapping[str, Any], ...]
    reward: Reward
    consent: str = "private"
    interruptions: tuple[Mapping[str, Any], ...] = ()
    cost: Mapping[str, Any] = field(default_factory=dict)
    started_at: str = ""                # ISO 8601
    finished_at: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RolloutRecord": ...

@dataclass(frozen=True)
class CalibrationCell:
    spec_name: str
    n_rollouts: int
    pass_rate: float
    mean_score: float
    by_difficulty: Mapping[str, float] = field(default_factory=dict)

@dataclass(frozen=True)
class CalibrationReport:
    env_name: str
    env_version: str
    cells: tuple[CalibrationCell, ...]
```

#### Logic / Algorithm
1. `Reward.from_criteria` computes `score = mean(c.score)` (0.0 for empty), `passed = all(c.passed)` (False for empty).
2. `Reward.failure` returns `Reward(0.0, False, (CriterionResult("verifier_error", False, 0.0, detail),))`.
3. `RolloutRecord.to_dict`/`from_dict` handle nested dataclass conversion explicitly (no pickle) so JSONL lines stay stable and language-agnostic.

#### Edge Cases & Error Handling
- Empty criteria → `passed=False`, `score=0.0` (a verifier that checks nothing must not award success).
- `from_dict` on an unknown `record_version` raises `ConfigurationError` naming the version, so future migrations are explicit.

---

### 6.2 Environment contract and generators

**File(s):** `vidbyte/environments/base.py`
**Type:** New file

#### What it does
Defines the `Environment` ABC (five-part anatomy), the `TaskGenerator` protocol, and
`StaticTaskSet` for hand-written task lists.

#### Interface / API
```python
class TaskGenerator(Protocol):
    def generate(self, seed: int, **knobs: Any) -> EnvTask: ...

class StaticTaskSet:
    """TaskGenerator over a fixed sequence of prebuilt EnvTasks."""
    def __init__(self, tasks: Sequence[EnvTask]) -> None: ...
    def generate(self, seed: int, **knobs: Any) -> EnvTask: ...   # seed % len(tasks)
    def __iter__(self) -> Iterator[EnvTask]: ...
    def __len__(self) -> int: ...

class Environment(ABC):
    """Resettable world + tool surface + seeded task generator + verifier."""
    name: str = "environment"
    version: str = "0.1.0"
    generator: TaskGenerator

    @abstractmethod
    def setup(self, task: EnvTask) -> EnvSession: ...
    @abstractmethod
    async def verify(self, session: EnvSession, trajectory: Sequence[Mapping[str, Any]]) -> Reward: ...
    @abstractmethod
    def teardown(self, session: EnvSession) -> None: ...

    def tools(self, session: EnvSession, requested: Tools | None = None) -> Tools: ...
    def permitted_tool_names(self, session: EnvSession) -> tuple[str, ...] | None: ...
```

#### Logic / Algorithm
1. `tools()` implements the authority rule: start from `session.tools` (environment-owned);
   for each requested tool, admit it only when `permitted_tool_names` is `None` (permit-all
   default) or contains the tool's name, and when its name does not collide with an
   environment-owned tool; return a new `Tools` catalog.
2. `permitted_tool_names` default returns `None`; concrete environments override to pin
   their action-surface contract.
3. `StaticTaskSet.generate` indexes `tasks[seed % len(tasks)]`, keeping the seeded-call
   convention valid for fixed sets.

#### Edge Cases & Error Handling
- `StaticTaskSet` with an empty sequence raises `ConfigurationError` at construction.
- Requested tool whose name collides with an environment tool is silently dropped in favor
  of the environment's tool (authority), and the drop is noted in `session.metadata["dropped_tools"]`.

---

### 6.3 HarnessSpec — the declarative harness axis

**File(s):** `vidbyte/environments/spec.py`
**Type:** New file

#### What it does
Defines the versioned, exhaustive, JSON-serializable description of how an agent is
assembled from SDK primitives. This is the sweepable/recordable unit; the public API request
schema of the future harness service; and the config attributed to every pass rate.

#### Interface / API
All models are pydantic v2 with `model_config = ConfigDict(frozen=True, extra="forbid")`.

```python
class ModelSpec(BaseModel):
    provider: str
    model: str
    temperature: float | None = None
    modality: str = "auto"
    runner_options: dict[str, Any] = Field(default_factory=dict)

class LoopSpec(BaseModel):
    # Mirrors AgentLoopSettings field-for-field.
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None
    max_parallel_tool_calls: int | None = None
    max_retries: int | None = None
    timeout_seconds: float | None = None
    context_window_budget: int | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None
    allowed_tools: tuple[str, ...] | None = None

class RuntimeSpec(BaseModel):
    kind: Literal["linear", "mcts_search", "actor"] = "linear"
    # Actor-only settings (validated unused for linear/mcts):
    topology: Literal["actor_model", "actor_model_p2p", "actor_model_broadcast"] = "actor_model_p2p"
    dynamic_actors: bool = False
    max_loop: int = 20
    termination_mode: Literal["coordinator", "quiescence"] = "coordinator"
    worker_model: str | None = None

class ContextAlgorithmSpec(BaseModel):
    preset: Literal[
        "default", "raw_tool_outputs", "compact_tool_outputs", "hide_tool_outputs",
        "no_raw_tool_outputs", "reflexion", "multi_provider_agentic_grader",
        "trajectory_checkpoints", "problem_space_search", "error_correction",
    ] = "default"
    tool_result_admission: Literal["raw", "compact", "hide_raw"] | None = None
    max_tool_result_chars: int | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    # settings keys are validated against the preset's algorithm dataclass fields, e.g.
    # reflexion: max_trials, max_reflection_chars, max_attempt_chars, agent_system_prompt,
    #            reflect_system_prompt, reflect_prompt
    # trajectory_checkpoints: interval, max_checkpoints, max_checkpoint_chars,
    #            max_field_chars, include_tool_outputs, checkpoint_title, placement
    # problem_space_search: interval, max_notes, max_note_chars, max_field_chars,
    #            include_tool_outputs, note_title, explorer_prompt, placement
    # error_correction: interval, max_passes, max_notice_chars, max_field_chars,
    #            max_corrections, include_tool_outputs, notice_title, auditor_prompt, placement
    # multi_provider_agentic_grader: grader_provider, grader_model, agent_system_prompt,
    #            grader_system_prompt, grader_prompt, max_grader_chars

class ContextPrimitiveSpec(BaseModel):
    kind: Literal[
        "text", "file", "git_diff", "document", "environment", "memory",
        "task", "progress", "plan", "artifact", "response", "tool_call",
    ]
    fields: dict[str, Any] = Field(default_factory=dict)
    placement: Literal["top_of_context", "end_of_context"] = "end_of_context"
    managed: bool = False               # True -> ContextManager.upsert; False -> context_items

class MiddlewareSpec(BaseModel):
    name: str                           # validated against MIDDLEWARE_TABLE at spec time
    settings: dict[str, Any] = Field(default_factory=dict)

class HarnessToolSpec(BaseModel):
    name: str                           # validated against TOOL_TABLE at spec time
    settings: dict[str, Any] = Field(default_factory=dict)

class TraceSpec(BaseModel):
    tracer: Literal["null", "debug"] = "null"
    continual: bool = False
    schema_preset: Literal["action"] = "action"
    schema_fields: dict[str, str] | None = None      # inline field->description map wins over preset
    every_n_iterations: int = 5
    max_trace_iterations: int = 3

class HarnessSpec(BaseModel):
    spec_version: str = "1"
    name: str
    system_prompt: str | None = None
    system_prompt_ref: str | None = None             # vidbyte.prompts catalog name
    model: ModelSpec
    runtime: RuntimeSpec = Field(default_factory=RuntimeSpec)
    loop: LoopSpec = Field(default_factory=LoopSpec)
    context_algorithm: ContextAlgorithmSpec = Field(default_factory=ContextAlgorithmSpec)
    context_primitives: tuple[ContextPrimitiveSpec, ...] = ()
    middleware: tuple[MiddlewareSpec, ...] = ()
    tools: tuple[HarnessToolSpec, ...] = ()
    trace: TraceSpec = Field(default_factory=TraceSpec)
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Module-level dispatch tables (single source of truth, used by both spec validation and the
resolver):

```python
MIDDLEWARE_TABLE: dict[str, type[AgentMiddleware]] = {
    "audit_log": AuditLogMiddleware,
    "canary_tripwire": CanaryTripwireMiddleware,
    "circuit_breaker": CircuitBreakerMiddleware,
    "confused_deputy_guard": ConfusedDeputyGuardMiddleware,
    "cost_budget": CostBudgetMiddleware,
    "exponential_backoff_retry": ExponentialBackoffRetryMiddleware,
    "honeypot_tool": HoneypotToolMiddleware,
    "loop_detection": LoopDetectionMiddleware,
    "message_history_compaction": MessageHistoryCompactionMiddleware,
    "model_retry": ModelRetryMiddleware,
    "runtime_limits": RuntimeLimitMiddleware,
    "summary_compaction": SummaryCompactionMiddleware,
    "token_budget": TokenBudgetMiddleware,
    "token_rate_limit": TokenRateLimitMiddleware,
    "tool_policy": ToolPolicyMiddleware,
    "tool_result_compaction": ToolResultCompactionMiddleware,
    "trace_replacement_compaction": TraceReplacementCompactionMiddleware,
    "trace_summary_tail_compaction": TraceSummaryTailCompactionMiddleware,
}

TOOL_TABLE: dict[str, Callable[..., BaseTool]] = {
    # builtins
    "calculator": CalculatorTool, "code_execution": CodeExecutionTool,
    "glob": GlobTool, "grep": GrepTool, "semantic_search": SemanticSearchTool,
    "patch": PatchTool, "document_retrieval": DocumentRetrievalTool,
    "context_compaction": ContextCompactionTool,
    "context_upsert": ContextUpsertTool, "context_list": ContextListTool,
    "context_remove": ContextRemoveTool,
    "reflexion": ReflexionTool, "trajectory_checkpoint": TrajectoryCheckpointTool,
    "create_handoff": CreateHandoffTool,
    "attach_mcp_server": AttachMcpServerTool, "search_mcp_servers": SearchMcpServersTool,
    # filesystem suite (each factory takes FileSystemToolConfig kwargs in settings)
    "fs_read_text": ..., "fs_read_lines": ..., "fs_write_text": ..., "fs_append_text": ...,
    "fs_replace_text": ..., "fs_list_dir": ..., "fs_tree": ..., "fs_find": ...,
    "fs_stat": ..., "fs_exists": ..., "fs_diff": ..., "fs_checksum": ...,
    "fs_copy": ..., "fs_move": ..., "fs_delete": ..., "fs_make_dir": ..., "fs_touch": ...,
}

ALGORITHM_SETTINGS_OWNERS: dict[str, type] = {
    "reflexion": ReflexionAlgorithm,
    "multi_provider_agentic_grader": MultiProviderAgenticGraderAlgorithm,
    "trajectory_checkpoints": TrajectoryCheckpointAlgorithm,
    "problem_space_search": ProblemSpaceSearchAlgorithm,
    "error_correction": ErrorCorrectionAlgorithm,
}

PRIMITIVE_TABLE: dict[str, type[ContextItem]] = { ... }   # kind -> primitive class
```

Memory-provider tools (Cognee/Letta/Mem0/Supermemory/Zep families) are intentionally
excluded from `TOOL_TABLE` v1: they require external service credentials, which violates the
no-secrets-in-spec rule; they remain usable through the prebuilt-agent escape hatch.

#### Logic / Algorithm
`HarnessSpec` model validators (run at construction, so sweeps fail before any rollout):
1. Exactly one of `system_prompt` / `system_prompt_ref` must be set.
2. Every `middleware[i].name` in `MIDDLEWARE_TABLE`; every `tools[i].name` in `TOOL_TABLE`; duplicate names rejected.
3. `context_algorithm.settings` keys ⊆ dataclass fields of `ALGORITHM_SETTINGS_OWNERS[preset]` (presets without an owner, e.g. `default`, require empty `settings`).
4. Non-linear runtime (`mcts_search`, `actor`) rejects: non-empty `middleware`, `trace.continual=True`, and any `context_algorithm.preset` other than `default`/aliases — mirroring `BaseAgent` (`vidbyte/agents/base.py:107-129`).
5. `ModelSpec` validated via `ProviderModelRegistry.validate_provider` / `validate_model`.
6. `TraceSpec` bounds mirror `TraceOption.__post_init__` (positive interval, 1..3 trace iterations).
7. `LoopSpec` positivity mirrors `AgentLoopSettings._validate` (delegated: the resolver constructs `AgentLoopSettings`, which re-validates authoritatively; the spec validator checks only JSON-level types).

#### Edge Cases & Error Handling
- All validation failures raise pydantic `ValidationError` carrying the offending field path
  and, for unknown names, the sorted list of valid names (discoverability for sweep authors).
- `extra="forbid"` everywhere: a typo'd field name is an error, never silently ignored.

---

### 6.4 HarnessSpecResolver

**File(s):** `vidbyte/environments/resolver.py`
**Type:** New file

#### What it does
The single place where a validated `HarnessSpec` becomes a live `BaseAgent` bound to an
`EnvSession`. Composes existing SDK constructors; owns no policy of its own beyond the
authority rule delegation.

#### Interface / API
```python
class HarnessSpecResolver:
    """Builds live BaseAgents from declarative HarnessSpecs bound to environment sessions."""

    def __init__(self, environment: Environment) -> None: ...

    def build_agent(self, spec: HarnessSpec, session: EnvSession) -> BaseAgent: ...
    def resolve_system_prompt(self, spec: HarnessSpec) -> str: ...
    def resolve_runtime(self, spec: HarnessSpec) -> LinearRuntime | MctsSearchRuntime | ActorRuntime: ...
    def resolve_loop_settings(self, spec: HarnessSpec) -> AgentLoopSettings: ...
    def resolve_algorithm(self, spec: HarnessSpec) -> ContextWindowAlgorithm: ...
    def resolve_context(self, spec: HarnessSpec) -> tuple[tuple[ContextItem, ...], ContextManager | None]: ...
    def resolve_middleware(self, spec: HarnessSpec) -> tuple[AgentMiddleware, ...]: ...
    def resolve_tools(self, spec: HarnessSpec, session: EnvSession) -> Tools: ...
    def resolve_trace(self, spec: HarnessSpec) -> tuple[TracerBase | None, TraceOption | None]: ...
```

#### Logic / Algorithm
1. `resolve_system_prompt`: literal wins; otherwise load `system_prompt_ref` through the
   `vidbyte.prompts` catalog; missing ref raises `ConfigurationError`.
2. `resolve_runtime`: `linear`→`LinearRuntime()`, `mcts_search`→`MctsSearchRuntime()`,
   `actor`→`ActorRuntime(topology=..., dynamic_actors=..., max_loop=...,
   termination_mode=..., worker_model=...)`.
3. `resolve_loop_settings`: `AgentLoopSettings(**spec.loop.model_dump())` (authoritative
   re-validation happens inside `AgentLoopSettings`).
4. `resolve_algorithm`: build the owner dataclass with `spec.context_algorithm.settings`,
   wrap in `ContextWindowAlgorithm(name=preset, <slot>=algo)`; apply
   `tool_result_admission`/`max_tool_result_chars` overrides; `default` preset returns
   `ContextWindow.resolve_algorithm(None)`.
5. `resolve_context`: instantiate each primitive from `PRIMITIVE_TABLE[kind](**fields)`;
   `managed=True` items are `upsert()`-ed into a fresh `ContextManager` with their placement;
   unmanaged items are returned as `context_items`. Returns `(items, manager_or_None)`.
6. `resolve_middleware`: `MIDDLEWARE_TABLE[name](**settings)` in spec order (order is the
   pipeline order).
7. `resolve_tools`: build requested tools from `TOOL_TABLE`; filesystem tool settings that
   omit `root` default to `str(session.workspace_dir)` (workspace scoping by default);
   then delegate to `environment.tools(session, requested=...)` for the authority filter.
8. `resolve_trace`: `debug`→`DebugTracer`, `null`→`None`; `continual=True` builds
   `TraceOption.continual(schema, every_n_iterations=..., max_trace_iterations=...)` where
   schema is the inline field map when given, else the `action` preset (`ActionTraceModel`).
9. `build_agent`: assemble `BaseAgent(name=spec.name, system_prompt=..., runtime=...,
   tools=..., agent_loop_settings=..., middleware=..., provider=..., model_name=...,
   temperature=..., modality=..., runner_options=..., context_items=...,
   context_manager=..., algorithm=..., tracer=..., trace_option=...,
   output_schema=spec.output_schema, metadata={"harness_spec": spec.model_dump()})`.

#### Edge Cases & Error Handling
- Constructor `TypeError` from a settings dict (wrong kwarg for a middleware/tool) is
  caught and re-raised as `ConfigurationError` naming the spec path
  (`middleware[2] 'cost_budget'`) and the underlying message.
- A filesystem tool settings dict with an explicit `root` outside the workspace is allowed
  only when `environment.permitted_tool_names` admits the tool — environments that pin
  their surface implicitly forbid root escapes by not permitting un-owned fs tools.

---

### 6.5 EnvironmentRunner and rollout loop

**File(s):** `vidbyte/environments/runner.py`
**Type:** New file

#### What it does
Executes rollouts (`(spec|agent, task)` → `RolloutRecord`) and calibration sweeps, with
bounded concurrency, guaranteed teardown, and error-as-failed-record semantics.

#### Interface / API
```python
class EnvironmentRunner:
    """Executes seeded rollouts against an environment and records verified outcomes."""

    def __init__(self, environment: Environment, *, recorder: RolloutRecorder | None = None, consent: str = "private", concurrency: int = 2) -> None: ...

    async def arollout(self, harness: HarnessSpec | Any, task: EnvTask | None = None, *, seed: int = 0, knobs: Mapping[str, Any] | None = None) -> RolloutRecord: ...
    async def arollout_many(self, harness: HarnessSpec | Any, tasks: Sequence[EnvTask]) -> tuple[RolloutRecord, ...]: ...
    async def acalibrate(self, harnesses: Sequence[HarnessSpec], *, n_tasks: int = 10, base_seed: int = 0, knobs: Mapping[str, Any] | None = None) -> CalibrationReport: ...
```

#### Logic / Algorithm
`arollout`:
1. Mint the task when not supplied: `environment.generator.generate(seed, **(knobs or {}))`.
2. `session = environment.setup(task)`; start timestamp.
3. Resolve the policy: `HarnessSpec` → `HarnessSpecResolver(environment).build_agent(spec, session)`;
   any object with `arun` → used as-is with `harness={"opaque": type(obj).__name__}` and its
   tools replaced/checked only if it exposes `tools` (documented: opaque agents bypass the
   authority filter and are for local experimentation, never published numbers).
4. `result = await agent.arun(task.instructions)` inside `try`; agent/model errors are
   captured as `error` with `Reward.failure(...)`.
5. Serialize trajectory from `agent.history` (role/content) and tool-call contexts when
   present; opaque agents contribute whatever `history` they expose, else the final reply.
6. `reward = await environment.verify(session, trajectory)` inside its own `try`;
   verifier exception → `Reward.failure(str(exc))` and `error` set.
7. `finally: environment.teardown(session)`.
8. Assemble `RolloutRecord` (cost fields taken from `result.metadata` tokens/latency when
   available), append via recorder when configured, return it.

`arollout_many`: semaphore-bounded `asyncio.gather` over per-task `arollout` calls (mirrors
`EvalRunner` concurrency pattern); note in docstring that a fresh agent is built per rollout
when given a spec — specs are stateless, which is the reason the escape-hatch agent path is
documented as sequential-only.

`acalibrate`: for each harness spec, mint `n_tasks` tasks with seeds `base_seed..base_seed+n-1`,
run `arollout_many`, fold into `CalibrationCell` (pass rate, mean score, per-difficulty pass
rates), return `CalibrationReport`.

#### Edge Cases & Error Handling
- `setup()` failure is not recoverable into a record (no session): re-raised after wrapping
  in `ConfigurationError` context — a broken environment must be loud, not a 0.0 reward.
- Prebuilt (opaque) agent passed to `arollout_many` raises `ConfigurationError` when
  `concurrency > 1` (shared mutable history across concurrent rollouts would corrupt records).
- Recorder write failures propagate (data loss must not be silent).

---

### 6.6 RolloutRecorder (JSONL persistence)

**File(s):** `vidbyte/environments/records.py`
**Type:** New file

#### What it does
Append-only JSONL persistence for `RolloutRecord`s plus loading for re-grading and export.

#### Interface / API
```python
class RolloutRecorder:
    """Append-only JSONL sink and loader for rollout records."""
    def __init__(self, path: Path | str) -> None: ...
    def append(self, record: RolloutRecord) -> None: ...
    def load(self) -> tuple[RolloutRecord, ...]: ...
    def __len__(self) -> int: ...
```

#### Logic / Algorithm
1. `append`: `json.dumps(record.to_dict(), ensure_ascii=False)` + newline, opened in append
   mode per call (crash-safe, parallel-writer tolerant at line granularity).
2. `load`: parse line-by-line via `RolloutRecord.from_dict`, skipping blank lines.

#### Edge Cases & Error Handling
- Parent directory created on first append.
- A corrupt line raises `ConfigurationError` with the line number (fail loud; sellable data
  must not be silently dropped).

---

### 6.7 Verifier audit kit

**File(s):** `vidbyte/environments/audit.py`
**Type:** New file

#### What it does
Stress-tests an environment's verifier with scripted no-model baselines and a determinism
check, producing the audit report that ships with a published environment.

#### Interface / API
```python
class DoNothingPolicy:
    """Scripted baseline that ends the rollout immediately without acting."""
    async def arun(self, prompt: str, **kwargs: Any) -> SimpleNamespace: ...   # returns empty reply

class EchoPolicy:
    """Scripted baseline that replies with the task instructions verbatim."""
    async def arun(self, prompt: str, **kwargs: Any) -> SimpleNamespace: ...

@dataclass(frozen=True)
class AuditReport:
    env_name: str
    env_version: str
    ok: bool
    baseline_scores: Mapping[str, float]
    deterministic: bool
    notes: tuple[str, ...]

class EnvironmentAudit:
    """Runs adversarial baselines and determinism checks against an environment."""
    def __init__(self, environment: Environment, *, max_baseline_score: float = 0.05, n_tasks: int = 3, base_seed: int = 0) -> None: ...
    async def arun(self) -> AuditReport: ...
```

#### Logic / Algorithm
1. For each of `n_tasks` seeds, roll both baselines through `EnvironmentRunner`
   (`consent="private"`, no recorder) and collect `reward.score`.
2. Determinism: for one seed, run the do-nothing baseline once, then call
   `environment.verify` a second time on an identical fresh session (re-`setup` from the
   same task, empty trajectory) and compare `Reward` equality.
3. `ok = max(baseline scores) <= max_baseline_score and deterministic`.
4. `notes` explains every failure (which baseline scored what on which seed).

#### Edge Cases & Error Handling
- Baseline runs use the opaque-agent path by design; audit results are still valid because
  baselines call no tools at all.
- A verifier exception during audit marks `ok=False` with the exception in `notes` (an
  environment whose verifier crashes on empty work is not publishable).

---

### 6.8 EnvironmentRegistry

**File(s):** `vidbyte/environments/registry.py`
**Type:** New file

#### What it does
Name→environment-class registry mirroring `vidbyte/lib/registries` conventions so
environments are addressable by name (CLI, service API, skill docs).

#### Interface / API
```python
class EnvironmentRegistry:
    """Class-level registry of environment implementations by name."""
    @classmethod
    def register(cls, environment_cls: type[Environment], *, replace: bool = False) -> type[Environment]: ...
    @classmethod
    def get(cls, name: str) -> type[Environment]: ...
    @classmethod
    def create(cls, name: str, **kwargs: Any) -> Environment: ...
    @classmethod
    def names(cls) -> tuple[str, ...]: ...
```

#### Logic / Algorithm
1. `register` keys on `environment_cls.name`; duplicate without `replace=True` raises
   `ConfigurationError`. Usable as a decorator.
2. `get`/`create` raise `ConfigurationError` listing known names on miss.

#### Edge Cases & Error Handling
- Registering a class with the default placeholder name `"environment"` is rejected —
  forces authors to name (and therefore version) their environment.

---

### 6.9 EnvironmentsClient and SDK wiring

**File(s):** `vidbyte/environments/client.py` (New), `vidbyte/client.py` (Modified), `vidbyte/__init__.py` (Modified), `vidbyte/environments/__init__.py` (New), `vidbyte/environments/README.md` (New)
**Type:** New + Modified

#### What it does
Exposes the namespace client (`sdk.environments`), package exports, and the module README
per repo convention.

#### Interface / API
```python
class EnvironmentsClient:
    """Namespace client for environment registry access and rollout execution."""
    def registry(self) -> type[EnvironmentRegistry]: ...
    def runner(self, environment: Environment, **kwargs: Any) -> EnvironmentRunner: ...
    def audit(self, environment: Environment, **kwargs: Any) -> EnvironmentAudit: ...
```

`vidbyte/client.py`: add `self.environments = EnvironmentsClient()` in `VidbyteSDK.__init__`.

`vidbyte/__init__.py`: export `Environment`, `EnvTask`, `EnvSession`, `TaskGenerator`,
`StaticTaskSet`, `Reward`, `CriterionResult`, `RolloutRecord`, `RolloutRecorder`,
`EnvironmentRunner`, `EnvironmentRegistry`, `EnvironmentAudit`, `HarnessSpec`, `ModelSpec`,
`RuntimeSpec`, `LoopSpec`, `ContextAlgorithmSpec`, `ContextPrimitiveSpec`, `MiddlewareSpec`,
`HarnessToolSpec`, `TraceSpec`, `CalibrationReport`.

#### Edge Cases & Error Handling
- Imports in `vidbyte/environments/__init__.py` stay lightweight (no heavy provider imports
  at package import time; resolver imports live inside `spec.py`/`resolver.py` which import
  existing SDK modules that are already imported by `vidbyte.__init__`).

---

### 6.10 Skill documentation

**File(s):** `skills/environments/SKILL.md`
**Type:** New file

#### What it does
The user-required skill explaining how the environment abstraction is built and how to use
it. Follows the `skills/agent-runtimes/SKILL.md` format (HTML-comment Context Protocol
Header, numbered sections, code examples, tables).

#### Contents (sections)
1. **Why environments** — harness↔environment duality; the three SDK contracts (verify,
   dual-backend tools, structured records); what labs buy.
2. **Anatomy** — world/state, action surface, task generator, verifier, difficulty
   calibration; seeded materialization as the reset mechanism.
3. **The Environment contract** — ABC walkthrough, authority rule, `verifier_state`
   isolation, versioning rules (any generator/verifier change bumps `version`).
4. **HarnessSpec reference** — full field tables for every sub-spec: middleware names table
   (all 18), tool names table (builtins + `fs_*` suite), context-algorithm presets with
   their settings fields, context-primitive kinds, trace options, runtime kinds and the
   non-linear incompatibility matrix (middleware/continual-trace/algorithms).
5. **Running rollouts** — `EnvironmentRunner` usage, records/consent, calibration sweeps,
   reading `CalibrationReport` as a spec sheet.
6. **Auditing** — `EnvironmentAudit` workflow; what a failing audit means; the rule that
   published numbers require spec-driven (non-opaque) rollouts and a passing audit.
7. **Authoring walkthrough** — build a toy filesystem environment end-to-end (generator with
   knobs, workspace materialization, programmatic verifier with partial credit, register,
   audit, calibrate).

---

## 7. Data Model Changes

### 7.1 RolloutRecord JSONL line

**Change type:** New (file format, no database)

```json
{
  "record_version": "1",
  "env_name": "string", "env_version": "string",
  "task": {"id": "...", "instructions": "...", "params": {}, "seed": 0, "difficulty": null, "metadata": {}},
  "harness": {"spec_version": "1", "name": "...", "...": "full HarnessSpec dump or {\"opaque\": \"ClassName\"}"},
  "trajectory": [{"role": "user|assistant|tool", "content": "...", "tool_calls": []}],
  "reward": {"score": 0.0, "passed": false, "criteria": [{"name": "...", "passed": false, "score": 0.0, "detail": "..."}]},
  "consent": "private", "interruptions": [], "cost": {"tokens": 0, "latency_ms": 0},
  "started_at": "ISO8601", "finished_at": "ISO8601", "error": null
}
```

**Migration strategy:** `record_version` gates parsing; future versions add a migration map
in `RolloutRecord.from_dict`. Rollback: files are append-only; older readers reject newer
versions explicitly.

---

## 8. API Changes

N/A — no HTTP surface in this PR. `HarnessSpec` is deliberately shaped to become the future
harness-service request schema (`spec_version` field exists for that reason), but no
endpoint ships here.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/environments-abstraction.md` | This design doc (first commit) |
| CREATE | `vidbyte/environments/__init__.py` | Package exports |
| CREATE | `vidbyte/environments/README.md` | Module README per repo convention |
| CREATE | `vidbyte/environments/types.py` | EnvTask/EnvSession/Reward/RolloutRecord/Calibration types |
| CREATE | `vidbyte/environments/base.py` | Environment ABC, TaskGenerator, StaticTaskSet, authority rule |
| CREATE | `vidbyte/environments/spec.py` | HarnessSpec + sub-specs + dispatch tables + validation |
| CREATE | `vidbyte/environments/resolver.py` | HarnessSpecResolver → BaseAgent |
| CREATE | `vidbyte/environments/runner.py` | EnvironmentRunner (arollout/arollout_many/acalibrate) |
| CREATE | `vidbyte/environments/records.py` | RolloutRecorder JSONL persistence |
| CREATE | `vidbyte/environments/audit.py` | DoNothingPolicy/EchoPolicy/EnvironmentAudit |
| CREATE | `vidbyte/environments/registry.py` | EnvironmentRegistry |
| CREATE | `vidbyte/environments/client.py` | EnvironmentsClient namespace |
| CREATE | `skills/environments/SKILL.md` | Skill doc for the abstraction (user requirement) |
| MODIFY | `vidbyte/client.py` | Add `environments` namespace to VidbyteSDK |
| MODIFY | `vidbyte/__init__.py` | Export public environment names |

13 files created, 2 modified, 0 deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| pydantic | >=2,<3 (already required) | HarnessSpec models + validation | None (existing dep) |
| stdlib (json, asyncio, dataclasses, pathlib, datetime) | 3.11+ | Records, runner, types | None |

No new dependencies. No external services.

---

## 11. Rollout & Deployment

- No feature flags: purely additive package; nothing existing changes behavior. The two
  modified files add one attribute and new exports respectively.
- Not a breaking change; package version stays pre-release `0.1.0`.
- Deployment = merge to `main`; consumed on next editable install.
- Rollback = revert the PR; no data or schema migrations exist.

---

## 12. Open Questions

- [ ] Should `HarnessSpec` support the multi-model aggregation surface (`proposers`/`aggregate`) in v1? Deferred: it interacts with runtime constraints and would double the spec's validation matrix; the escape-hatch agent path covers experimentation. Confirm this is acceptable.
- [ ] Memory-provider tools are excluded from `TOOL_TABLE` v1 (external credentials). Confirm.
- [ ] `consent` is a free string (`"private"`/`"shared"` conventions) rather than an enum, so the future service can extend levels without an SDK release. Confirm.

---

## 13. Alternatives Considered

### Alternative 1: Extend `vidbyte.evals` instead of a new package
- What: add workspace/verifier concepts to `EvalCase`/`EvalRunner`.
- Why rejected: evals grade prompt→reply pairs; environments are state-in/state-out with an
  authority-owning world. Forcing both into one runner couples two lifecycles (`setup`/
  `teardown`/seeded reset vs. stateless case iteration) and would break the existing eval
  contract. Environments may *use* graders internally later; the packages stay separate.

### Alternative 2: Imperative harness construction (pass a configured `BaseAgent`)
- What: skip `HarnessSpec`; runner accepts prebuilt agents only.
- Why rejected: live objects cannot be recorded, diffed, swept, or transmitted; pass rates
  become unattributable, which breaks the calibration/spec-sheet product. Kept only as an
  explicitly-opaque escape hatch for local experimentation.

### Alternative 3: Snapshot/restore world state instead of seeded materialization
- What: capture workspace snapshots after `setup` and restore between rollouts.
- Why rejected for v1: snapshot infra (copy-on-write, storage, invalidation) is heavy, and
  deterministic seeded builds make reset free. Snapshots become necessary only for worlds
  seeded from live customer state — a later layer.

### Alternative 4: One flat kwargs dict instead of structured sub-specs
- What: `HarnessSpec(settings: dict)` passed through to `BaseAgent`.
- Why rejected: no spec-time validation, no discoverability, silent typos, and the sweep
  axis (per-field grids) disappears. `extra="forbid"` structured models are the point.

### Alternative 5: Register specs in `vidbyte/lib/registries`
- What: put `EnvironmentRegistry` beside lib registries.
- Why rejected: `lib` is internal plumbing; environments are a public developer surface and
  follow the public-package pattern (`evals`, `harnesses`) with their own namespace client.
