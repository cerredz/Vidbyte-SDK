Exit code: 0
Wall time: 0.6 seconds
Output:
# Design Doc: Agentic Engineering for Base Agent and Runtime

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-10
**Last Updated:** 2026-07-10

---

## 1. Overview

Apply the linked agentic-engineering principles to the SDK's two core execution modules: `BaseAgent`, which owns public agent construction and dispatch, and `AgentRuntime`, which owns the direct model/tool loop. The change will make both modules cold-agent navigable through complete headers and a folder comprehension cache, reduce oversized orchestration methods into named single-purpose collaborators, record durable runtime intent beside load-bearing policy boundaries, and replace generic failure messages at these boundaries with safe, typed diagnostic context packets. Public agent construction and execution semantics remain compatible.

---

## 2. Goals & Non-Goals

### Goals

- Apply every applicable checklist from the linked system prompt's six agentic-engineering principles to the two target modules.
- Replace each target's short `Context Protocol Header` with a maintained, structured file header that accurately documents its literal path, purpose, callers and callees, architecture role, public API inventory, modification routes, prohibited responsibilities, edge cases, errors, related docs, test references, and concurrency behavior.
- Turn `vidbyte/agents/README.md` into a folder-level comprehension cache with a stable folder-intent description, grounded non-goals, complete direct-file index, and concise audit log.
- Refactor the long construction and execution orchestrators into small, honestly named methods and private typed state objects without changing public method signatures or observable successful-run behavior.
- Add immediate explanatory comments below every function and method signature in files touched by the implementation, keeping every signature on one physical line as required by the selected workflow.
- Add `@intent` comments only at runtime and safety boundaries whose product/operational meaning would be easy to lose in a later refactor.
- Introduce per-failure, typed diagnostic errors for existing target-module preconditions, configuration conflicts, agent execution boundaries, and tool-execution failure modes. Each error will preserve the existing SDK base exception category, include static diagnostic context, accept only safe dynamic state at its raise site, and offer a `to_context_packet()` representation.
- Keep all diagnostic packets free of prompts, credentials, authorization data, raw provider responses, and unbounded tool output.

### Non-Goals

- No new agent capability, provider integration, runtime strategy, context-window algorithm, middleware hook, tool permission rule, persistence layer, or package dependency.
- No changes to the public constructor parameters or public `BaseAgent`/`AgentRuntime` imports.
- No broad conversion of all SDK errors to the new diagnostic pattern; only failures originated in the two target modules are in scope.
- No changes to `vidbyte/agents/runtimes/search.py`, actor runtimes, aggregation behavior, MCP attachment behavior, shared tool implementations, or provider adapters.
- No feature-test-pack files or new automated tests under this explicitly selected `design-doc-no-tests` workflow. The existing relevant tests will be referenced by headers and used as implementation verification; a new durable feature boundary is not being introduced.
- No edits to generated files, `__pycache__`, or the unrelated untracked design documents and nested worktrees in the current checkout.

---

## 3. Background & Context

The user referenced `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` from the repository's `main` branch and requested that all principles be applied to the base agent class and runtime file. That prompt treats source as an interface for human developers and downstream agents, routes source edits through file-header and function-design guidance, routes source-folder changes through folder README guidance, routes meaningful operational rules through intent comments, and expects server-side failures to supply actionable diagnostic context. It also names feature test packs, but the requested `design-doc-no-tests` workflow explicitly targets changes that do not require test-pack work; this design therefore records the assessment and retains the existing test suite as the verification surface.

Repository audit findings:

- `vidbyte-sdk` is a Python package requiring Python `>=3.11`, built with setuptools, and currently depends on Pydantic 2 and HTTPX. Its root README identifies `vidbyte.agents` as the executable actor layer and `vidbyte.context`, `middleware`, `tools`, `trace`, and `lib` as its direct collaborators.
- `vidbyte/agents/base.py` contains `ConfiguredAgentRunner` and the public `BaseAgent` faÃ§ade. It validates compatible runtime configuration, normalizes runners and context, starts root traces, delegates text runs to the selected runtime, records tool and handoff state, and exposes the synchronous wrappers.
- `vidbyte/agents/runtime.py` contains the canonical linear `AgentRuntime` loop. It assembles context, runs middleware hooks, calls the model, parses and executes tools, applies context-window algorithms, records trace spans, enforces budgets, and creates the final `AgentResult`. `vidbyte/agents/runtimes/linear.py` is only a compatibility re-export.
- The current file headers are short `Context Protocol Header` docstrings. They do not contain the complete navigational information the linked file-header principle requires. The existing `vidbyte/agents/README.md` provides useful role and usage information but lacks a non-goal map, direct-file index, and audit log.
- `BaseAgent.__init__` is 151 lines, `BaseAgent.generate_reply` is 101 lines, and `AgentRuntime._arun_once` is 421 lines. Several runtime helpers also accept wide parameter lists. These are the principal function-design hotspots.
- Existing failures use generic subclasses from `vidbyte.lib.errors.base` such as `AgentExecutionError`, `ConfigurationError`, `ToolRegistryError`, `PermissionDeniedError`, and `ToolExecutionError`. They can carry a small `details` mapping but do not presently carry the static diagnostic anatomy or context-packet conversion required by the linked error principle.
- Existing tests cover the relevant behavior in `tests/test_agent_base.py`, `tests/test_agent_runtime.py`, `tests/test_agent_tool_loop.py`, `tests/test_agent_middleware.py`, `tests/test_agent_modality_routing.py`, and `tests/test_tracing.py`. This selected workflow does not add a feature-test pack, but the final headers will name the relevant files rather than claim invented line-level coverage.
- `BaseAgent` may attach MCP subprocesses and trace state, and `AgentRuntime` may execute mutable tools. Error context and intent comments must preserve the established trust boundaries: middleware is not model-visible; permission checks precede execution; trace payloads redact secret-like keys; continual trace is fail-open; and non-linear runtimes remain incompatible with middleware, continual tracing, and non-default context algorithms.
- The current checkout is on `feat/context-minimal-fanout-trace` and contains unrelated untracked files. Per the selected workflow, implementation must wait for approval and then occur only in a new worktree; no current untracked work will be altered.

The deep-dive guidance was loaded from the linked prompt family for structured errors, file headers, folder READMEs, function design, and intent comments. The linked system prompt's feature-test-pack URL was unavailable at the requested revision; its system-level routing instruction and the selected no-tests workflow are the basis for the intentional no-new-pack boundary above.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte/agents/base.py` and `vidbyte/agents/runtime.py` must open with complete, file-specific agentic headers. The finished headers must be reconciled against finished code, contain literal repository-relative paths, and not duplicate the old header.
2. Each target header must document: purpose, role in the dependency graph, architecture note, public and important-private function inventory, common modification patterns, numbered prohibited responsibilities, known edge cases, common diagnostic errors, fetchable related-doc URLs, relevant existing test files, and a concurrency model when applicable.
3. `vidbyte/agents/README.md` must contain Folder Description / Intent, Non-Goals, File Index, and Logs sections. Its non-goals must be grounded in the audited package README boundaries, and its direct-file index must remain synchronized with the directory listing at implementation time.
4. Every function and method modified or introduced in `base.py`, `runtime.py`, or the supporting diagnostic-error module must have a one-line signature and an immediate one- or two-line explanatory comment. Docstrings may remain where they provide useful public API documentation, but they do not replace the required immediate comment.
5. Public entry points must orchestrate named private leaves. The implementation must split the current large construction, reply-generation, direct-runtime-loop, model-invocation, tool-execution, and result-finalization responsibilities until each callable has one coherent job, an honest underscore-style name, and a body that can be read in one pass where practical.
6. Private typed state objects must replace wide internal helper argument lists. Public `BaseAgent.__init__`, `generate_reply`, `arun`, `run`, and `AgentRuntime.arun` contracts must remain source-compatible.
7. Intent comments must sit immediately above, and describe the operational meaning of, at least these boundaries: non-linear runtime compatibility rejection; trace redaction; direct-loop lifecycle order; model retry preservation; permission-before-execution; internal `isDone` termination; primitive-bound tool-result storage; and fail-open handoff/context synchronization behavior. Comments must explain the invariant and dangerous rewrite, rather than narrate statements.
8. Each existing target-module failure mode at a precondition, configuration compatibility boundary, tool boundary, runner boundary, or state transition must use one dedicated diagnostic exception class. New classes must subclass the existing corresponding SDK error category so existing broad catches remain compatible.
9. Each diagnostic error class must supply its stable description, expected-versus-actual contract, blast-radius references, likely causes when known, remediation approaches, related-document URLs, and existing-test references as class-level context. Raise sites may supply only dynamic, safe fields such as runtime type, option names, tool name, or model-call phase.
10. Diagnostic errors must expose exact source file and function information and a `to_context_packet()` method. Packet construction must redact or exclude API keys, tokens, credentials, authorization values, complete prompt text, raw provider responses, tool arguments that could contain secrets, and unbounded output.
11. The runtime must preserve established success behavior: middleware hook order, model retry behavior, tool-result order, budget stops, `isDone` completion, context-window hook timing, trace finalization, and public `AgentResult`/`AgentMessage` shapes must not change.
12. Feature test packs are assessed but not created: this approved scope is a behavior-preserving readability and diagnostics refactor under `design-doc-no-tests`, not a new durable feature. Headers will cite existing test modules without inventing coverage values or line ranges.

### Non-Functional Requirements

- Performance: The normal successful path must add no network calls, persistence, provider requests, or material loop overhead. Diagnostic packet construction may occur only on exception paths.
- Compatibility: Existing callers that catch `AgentExecutionError`, `ConfigurationError`, `ToolRegistryError`, `PermissionDeniedError`, or `ToolExecutionError` must continue to catch the specialized subclasses.
- Security: All error and trace helper paths must use an allowlist/redaction approach for dynamic context. No secret or full prompt may be embedded in headers, README logs, exceptions, or returned tool-result metadata.
- Reliability: Structural refactoring must retain `BaseException` cleanup behavior for cancellation and retain the runtime's retry decisions before turning a model failure into an agent-facing diagnostic error.
- Observability: File headers must point to the actual trace and test surfaces. Diagnostic packets must identify the failure's dependency blast radius without fabricating incidents, error locations, test coverage, or remediation history.
- Maintainability: No new module may become a second runtime implementation. The private state objects and error classes exist only to make the two canonical modules easier to read and safely change.

---

## 5. High-Level Design

The implementation is a targeted readability and diagnostic-contract refactor centered on `BaseAgent` and `AgentRuntime`. It will first upgrade the folder README and structured headers, then introduce a private diagnostic error module, and finally decompose the two existing large classes around their already-established lifecycle boundaries. The public entry points remain the table of contents: `BaseAgent` prepares an execution request and delegates it; `AgentRuntime` advances one explicit run state through middleware, model calls, tool calls, and finalization.

The implementation will use small private dataclasses as explicit parameter/state containers instead of passing many loop values through each helper. `BaseAgent` will use an execution-preparation object to hold normalized input, selected modality, runner, and trace metadata. `AgentRuntime` will use a run-state object to hold provider, options, conversation messages, tool-call contexts, counters, trace state, and context-window state. These objects are internal implementation details; they do not alter the SDK's public signatures or result payloads.

Typed diagnostic errors will live under `vidbyte/agents` because the detailed static context belongs to this agent subsystem, while their inheritance will retain the shared error categories in `vidbyte.lib.errors`. This avoids altering the global error hierarchy or leaking agent-internal diagnostic fields into unrelated SDK failures. The source modules will raise only these dedicated classes at their known boundaries; generic external/model failures will retain their existing retry/cleanup behavior and then be wrapped at the agent execution boundary with a safe, typed packet.

```text
Caller
  |
  v
BaseAgent
  |- validate and normalize configuration/input
  |- select runner + start redacted root trace
  |- build context and delegate
  v
AgentRuntime
  |- initialize explicit run state
  |- middleware -> model -> tool / completion loop
  |- typed diagnostic errors at known boundaries
  |- finish result + metadata
  v
AgentMessage / AgentResult

Supporting navigation artifacts
  `- agents/README.md + structured headers + lib/errors/agent.py context packets
```

---

## 6. Detailed Design

### 6.1 Agent Diagnostic Error Contracts

**File(s):** `vidbyte/lib/errors/agent.py`
**Type:** New file

#### What it does

Defines internal agent-subsystem diagnostic exception classes. Each class represents exactly one existing failure mode in the base-agent construction/execution or direct-runtime tool boundary. The classes carry static, audited context at definition time and receive only safe invocation-specific values at raise sites.

#### Interface / API

```python
class AgentDiagnosticErrorMixin:
    # Combines static diagnostic facts with allowlisted dynamic state and returns a safe context packet.
    def to_context_packet(self) -> dict[str, object]: ...

class AgentNameRequiredError(AgentDiagnosticErrorMixin, AgentExecutionError): ...
class NonLinearRuntimeMiddlewareError(AgentDiagnosticErrorMixin, ConfigurationError): ...
class AgentRunnerRequiredError(AgentDiagnosticErrorMixin, AgentExecutionError): ...
class RuntimeUnknownToolError(AgentDiagnosticErrorMixin, ToolRegistryError): ...
class RuntimeToolPermissionDeniedError(AgentDiagnosticErrorMixin, PermissionDeniedError): ...
class RuntimeToolExecutionError(AgentDiagnosticErrorMixin, ToolExecutionError): ...
```

#### Logic / Algorithm

1. Implement a private mixin that defines the common static packet schema and builds a safe `details` mapping plus `to_context_packet()` result.
2. Make each concrete class inherit the existing generic SDK error that callers already catch. Do not change `vidbyte.lib.errors.base`.
3. Define static fields only for known facts: unique error type, source file/function, description, expected/actual contract, dependency blast radius, possible causes, remediation approaches, full URLs, and relevant existing test files.
4. Allow raise sites to pass a constrained dynamic context mapping. Filter keys and truncate values before placing them in `details` or packets.
5. Define classes for each audited site rather than one generic agent error: required name, required system prompt, non-linear middleware/tracing/context-algorithm/aggregation incompatibility, missing aggregation provider, conflicting loop/tracer configuration, incomplete agent-tool metadata, sync execution inside an active loop, missing/unexecutable/invalid runner, agent execution failure, invalid inner context-window runner, missing tool, denied tool, invalid tool arguments, tool execution failure, and output-schema violation.
6. For model/provider exceptions, retain the existing middleware retry flow. Only emit the typed agent execution failure after retries and trace cleanup have completed; preserve the original exception as the cause.

#### Edge Cases & Error Handling

- Existing callers that catch a shared generic type remain compatible because every new error subclasses that type.
- `ToolResult.error(...)` paths must receive the safe packet's public summary/identifier only; they must not return internal file maps or dynamic exception text to a model.
- Do not claim precise test-line ranges, incident history, or remediation certainty where the audit provides no evidence; the static packet should explicitly mark unavailable causes as such.
- Cancellation and other `BaseException` values must still propagate after trace cleanup instead of being converted to diagnostic errors.

### 6.2 Base Agent Structure and Navigation Header

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Keeps `BaseAgent` as the public composition root for agent configuration, modality/runner selection, context construction, root tracing, execution dispatch, result recording, handoff, and synchronous convenience wrappers. It becomes a small-orchestrator faÃ§ade over named private leaves and typed internal preparation data.

#### Interface / API

```python
class _PreparedAgentExecution:
    # Holds normalized input, selected modality, runner, trace metadata, and per-run context inputs.
    ...

class BaseAgent(McpAttachableMixin):
    def __init__(self, *, name: str, system_prompt: str, runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR, ... ) -> None: ...
    async def generate_reply(self, message: str | AgentInput, *, modality: ModelModality | str | None = None, context: BaseContext | None = None, history: Sequence[AgentMessage] = (), recipient: str = "orchestrator", **options: Any) -> AgentMessage: ...
```

#### Logic / Algorithm

1. Replace the current header with the full required section inventory. It will name `vidbyte/agents/__init__.py`, `runtime.py`, `runtimes/configs.py`, `mixins.py`, `context`, `middleware`, `tools`, `trace`, and the applicable existing tests as dependencies.
2. Split `__init__` into validation, runtime compatibility resolution, aggregate-plan resolution, runner/tool/context state initialization, tracing setup, MCP state initialization, and optional aggregate-agent setup. Keep its existing keyword-only API and initialization order.
3. Represent the normalized per-call inputs in `_PreparedAgentExecution`, built by separate helpers for input normalization, modality selection, runner resolution, and trace metadata preparation.
4. Rewrite `generate_reply` as a short lifecycle orchestrator: delegate aggregate requests; ensure MCP connection; prepare execution; start the redacted trace; build context; invoke the selected runtime/runner; build and record the reply; finish optional continual trace/handoff; and finalize trace/active prompt cleanup. The original exception remains chained from the diagnostic execution error.
5. Extract `fork` construction-argument assembly, direct-runner validation, runtime creation, tool-context recording, and tracing serialization into focused helpers where the existing body mixes distinct concerns.
6. Add immediate comments below every affected signature, including retained small helpers and module-level helpers. Use compact comments for straightforward helpers and durable `@intent` blocks only at selected semantic boundaries.
7. Use typed diagnostic errors at every existing raise site. Continue to fail open for optional handoff generation and optional context primitive synchronization, documenting why that failure must not erase the primary result.
8. Re-read and update the header after the final function inventory and exception mapping are complete.

#### Edge Cases & Error Handling

- Non-linear runtimes must still reject middleware, continual tracing, non-default context algorithms, and multi-model aggregation before runner execution begins.
- An aggregate request must continue to delegate before normal direct-run setup.
- `run()` and `run_sequentially()` must continue to reject active event loops with typed subclasses of `AgentExecutionError`.
- The trace root must still close for ordinary exceptions and cancellation, and `_active_prompt` must be cleared in every terminal path.
- Runner inspection failures and tool-spec introspection failures must not include the object repr, prompt, credentials, or arbitrary call options in diagnostics.

### 6.3 Direct Runtime Loop Structure and Navigation Header

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Remains the canonical direct text agent runtime. It keeps ownership of context assembly, middleware sequencing, model invocation/retry integration, tool execution, context-window hooks, trace spans, budget stops, and final result metadata, while exposing those phases as short named methods over a private typed run state.

#### Interface / API

```python
class _RuntimeRunState:
    # Carries the mutable state for one direct execution loop without widening helper signatures.
    provider: str
    run_options: dict[str, Any]
    runtime_metadata: dict[str, Any]
    messages: list[dict[str, Any]]
    tool_call_contexts: list[ToolCallContext]
    iteration_count: int
    model_call_count: int
    tokens_used: int | None
    ...

class AgentRuntime:
    async def arun(self, message: str, *, handle: RunnerHandle, context: BaseAgentContext, metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...
```

#### Logic / Algorithm

1. Replace the current header with the full required inventory and concurrency section. It will state that direct runs are isolated by local run state while agent instances and context managers are mutable and should not be shared concurrently without external coordination.
2. Split `build_context` into context-manager construction, metadata merging, and `BaseAgentContext` construction without changing item order, agentic-loop prompt injection, or tool selection.
3. Construct `_RuntimeRunState` once at the start of `_arun_once`; make the remaining loop orchestration call dedicated helpers to initialize inner algorithms, run `before_run`, check budgets, invoke a model iteration, process a final response, process parsed tool calls, and finish a result.
4. Decompose `_invoke_with_middleware`, `_finish_result`, `_middleware_context`, `execute_tool_call`, `_process_tool_call`, result/metadata builders, and call-option construction so each helper has one responsibility and accepts state objects rather than long parameter lists.
5. Preserve exact middleware and loop ordering: run hooks before model calls, retain retry behavior on model errors, append the provider's assistant tool-call message before its tool result, run after-tool/after-iteration hooks in the same conditions, and stop immediately at `isDone` or configured limits.
6. Add intent comments at the lifecycle ordering, model-retry, permission-before-validation/execution, internal-completion, primitive-binding, trace-redaction, and context-window-hook boundaries. Each will name the operational effect of a bad reordering or bypass.
7. Replace current generic raises and returned tool error metadata with the dedicated diagnostic types/allowlisted summaries. Keep public `ToolResult` status and `AgentResult` result shapes unchanged.
8. Reconcile the header's function inventory, errors, test references, and concurrency description after implementation.

#### Edge Cases & Error Handling

- The inner context-window algorithm must still initialize once before any iteration and run after completed tool calls only; an invalid runner handle becomes a typed diagnostic error.
- Model-call exceptions must reach retry middleware before an agent-facing diagnostic wraps the final failure; `BaseException` must still close the LLM span and propagate.
- Permission denial must occur before argument validation or tool execution so a denied write tool cannot leak validation behavior or cause side effects.
- Unknown tools, invalid tool arguments, execution failures, and output-schema violations must still produce normal failed/denied `ToolCallContext` records and model-safe `ToolResult` messages.
- Internal `isDone` must still bypass normal tool-result message injection and finalize the result from the tool output.
- Primitive-binding and context-upsert failures remain non-fatal and retain the original tool result.

### 6.4 Agents Folder Comprehension Cache

**File(s):** `vidbyte/agents/README.md`
**Type:** Modified

#### What it does

Lets a future agent decide whether `vidbyte.agents` is the correct folder before opening source files. It preserves useful usage examples while adding a durable intent statement, ownership boundaries, direct-file routing index, and compact persistent audit knowledge.

#### Interface / API

```markdown
# Agents

## Folder Description / Intent
...

## Non-Goals
...

## File Index
...

## Logs
- Direct runtime orchestration belongs in runtime.py; public agent composition belongs in base.py - why it matters.
```

#### Logic / Algorithm

1. Preserve the current high-level usage example only after checking it matches the unchanged public API.
2. Rewrite the folder description around stable ownership: public agent composition versus direct runtime execution versus swappable runtime implementations.
3. Add seven to nine concrete non-goals grounded in the audited README boundaries. Redirect context primitives to `vidbyte/context`, policy hooks to `vidbyte/middleware`, tool implementation/permission policy to `vidbyte/tools`, provider adapters to `vidbyte/providers`, shared types/errors to `vidbyte/lib`, tracing implementations to `vidbyte/trace`, and multi-agent topologies to `vidbyte/pipelines` or `vidbyte/paradigms` as appropriate.
4. Generate a direct-file index from the final `vidbyte/agents` directory listing. Each entry will route a reader to the relevant file, including `base.py`, `runtime.py`, the new `errors.py`, `runtimes/`, `settings/`, and existing specialized modules.
5. Add only observed, one-line log entries: the direct runtime's public compatibility import is `runtimes/linear.py`; non-linear runtime incompatibilities are enforced at construction; and diagnostic context must remain redacted/model-safe.
6. Re-read the README after source edits to remove stale claims and retain no narrative implementation duplication from child folders.

#### Edge Cases & Error Handling

- The README must not describe every subfolder's internal implementation; it should route to the child directory where that information belongs.
- Logs must be observed audit facts, not invented production incident history.
- No mechanical README-index generator or CI rule will be introduced in this scoped refactor; the index is reconciled manually with the directory listing before the PR.

### 6.5 Feature Test Pack Principle Assessment

**File(s):** N/A - no feature-test-pack files under the selected workflow.
**Type:** N/A - reason: this is a behavior-preserving readability/error-diagnostics refactor and the user selected `design-doc-no-tests`.

#### What it does

Documents the application decision for the sixth linked principle. The implementation will not introduce a new durable feature boundary, and test-pack artifacts would expand this explicitly no-tests task beyond the requested scope.

#### Interface / API

```text
N/A - existing tests remain the verification references named by the target file headers.
```

#### Logic / Algorithm

1. Identify the existing behavioral test modules that exercise base-agent construction, runtime looping, tool execution, middleware order, modality routing, and tracing.
2. Reference those test modules accurately in the completed headers and error-class static metadata.
3. Do not add `FEATURE.md`, a new test directory, test code, or test-pack-specific tooling.

#### Edge Cases & Error Handling

- If implementation requires behavior beyond a compatibility-preserving refactor, stop and revise this design before adding it. That change would make a feature test pack applicable despite the selected workflow.
- Header and error metadata must never invent a test that does not exercise the stated path.

---

## 7. Data Model Changes

### 7.1 `_PreparedAgentExecution`

**Change type:** New private in-memory type

```python
@dataclass(slots=True)
class _PreparedAgentExecution:
    prompt: str
    modality: ModelModality
    runner: object | None
    input_metadata: Mapping[str, Any]
    trace_metadata: Mapping[str, Any]
    input_context_items: tuple[ContextItem, ...]
    input_context_manager: ContextManager | None
```

**Migration strategy:**

- Forward migration: construct only inside `BaseAgent.generate_reply`; callers continue passing current public inputs.
- Rollback plan: revert the refactor; no persisted or serialized data requires migration.

### 7.2 `_RuntimeRunState`

**Change type:** New private in-memory type

```python
@dataclass(slots=True)
class _RuntimeRunState:
    provider: str
    run_options: dict[str, Any]
    runtime_metadata: dict[str, Any]
    messages: list[dict[str, Any]]
    tool_call_contexts: list[ToolCallContext]
    iteration_count: int = 0
    model_call_count: int = 0
    tokens_used: int | None = None
    last_response: object | None = None
    last_assistant_output: str | None = None
    middleware_state: dict[type, Any] = field(default_factory=dict)
```

**Migration strategy:**

- Forward migration: use only within a single `AgentRuntime` invocation; do not expose or persist it.
- Rollback plan: revert the refactor; no persisted or serialized data requires migration.

### 7.3 Diagnostic Context Packets

**Change type:** New internal error payload contract

```python
{
  "error_type": "RuntimeUnknownToolError",
  "source": {"file": "vidbyte/agents/runtime.py", "function": "_get_tool"},
  "description": "...",
  "expected_vs_actual": {"expected": "...", "actual": "..."},
  "dynamic_context": {"tool_name": "..."},
  "blast_radius": ["..."],
  "possible_causes": ["..."],
  "fix_approaches": ["..."],
  "doc_links": ["..."],
  "test_files": ["..."]
}
```

**Migration strategy:**

- Forward migration: packets are available only on the specialized errors and are additive to existing `.message` and `.details` behavior.
- Rollback plan: revert the agent error module and restore existing generic raises; no stored data is affected.

---

## 8. API Changes

### 8.1 Python Agent Error Surface

**Change type:** Modified

**Request:**

```json
{
  "agent_construction_or_execution": "existing BaseAgent / AgentRuntime call"
}
```

**Response:**

```json
{
  "successful_result": "unchanged AgentMessage or AgentResult shape",
  "failure": "a specialized internal diagnostic subclass of the same existing SDK base error"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | This SDK change does not define HTTP endpoints or status codes. |
| `AgentExecutionError` subtype | Agent validation, runner protocol, active-event-loop sync call, or post-retry execution failure. |
| `ConfigurationError` subtype | Incompatible runtime option combination or conflicting construction settings. |
| Tool error subtype / model-safe `ToolResult` | Unknown, denied, invalid, failed, or schema-invalid tool call. |

No public endpoint is added. The concrete agent diagnostic errors live in `vidbyte.lib.errors.agent` and are re-exported from `vidbyte.lib.errors` alongside the shared SDK exception hierarchy, so advanced callers can inspect a concrete error type through the same import surface they already use for `AgentExecutionError`/`ConfigurationError`.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agentic-engineering-base-agent-runtime.md` | Approved source-of-truth design for the implementation. |
| CREATE | `vidbyte/lib/errors/agent.py` | Dedicated typed diagnostic errors and safe context-packet support for target-module failures, re-exported from `vidbyte/lib/errors/__init__.py`. |
| MODIFY | `vidbyte/agents/base.py` | Full header, constructor/execution decomposition, intent comments, one-line signatures/comments, and typed diagnostics. |
| MODIFY | `vidbyte/agents/runtime.py` | Full header, explicit runtime state, loop/tool decomposition, intent comments, one-line signatures/comments, and typed diagnostics. |
| MODIFY | `vidbyte/agents/README.md` | Folder comprehension cache with intent, non-goals, direct-file index, and compact logs. |

No files will be deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` from `pyproject.toml` | Existing SDK language/runtime; provides `dataclass` and typing support for private state objects. | No new dependency. |
| `vidbyte.lib.errors` | Local `vidbyte/lib/errors/base.py` | Existing base exception classes that the new specific diagnostic errors must subclass. | Incorrect inheritance could break existing catches; implementation must preserve category compatibility. |
| Existing test suite | Local `tests/test_agent_base.py`, `test_agent_runtime.py`, `test_agent_tool_loop.py`, `test_agent_middleware.py`, `test_agent_modality_routing.py`, `test_tracing.py` | Existing verification references for behavior the refactor must preserve. | No test pack is added under selected workflow; behavior drift needs careful review. |
| Agentic engineering prompt family | `https://github.com/cerredz/Vidbyte-SDK/tree/main/vidbyte/prompts/prompts/agentic_engineering` | Source of the loaded design principles. | The unavailable feature-test-pack deep dive is explicitly bounded by the no-tests workflow. |

---

## 11. Rollout & Deployment

- No feature flag, database migration, service deployment order, or configuration migration is required.
- The change is intended to be source-compatible for normal successful use and broadly exception-compatible because detailed errors subclass the current SDK categories.
- After approval, implementation must create `feat/agentic-engineering-base-agent-runtime` in an isolated worktree from an up-to-date, clean `main`, commit this design doc first, then make only the manifest changes.
- Because the selected workflow is no-tests, implementation verification will use lightweight existing repository checks appropriate to a Python source refactor (at minimum syntax/import checks) and manual header/README/error-packet reconciliation. Existing unit tests may be run as a safety check, but no new test assets are part of the manifest.
- Rollback is reverting the feature PR. No persisted state or public data migration needs reversal.

---

## 12. Open Questions

- [ ] The linked system prompt names feature test packs as a principle, while the selected `design-doc-no-tests` workflow excludes them. This design treats a behavior-preserving refactor as not introducing a new feature boundary; confirm this interpretation when approving, or request a test-pack expansion instead.
- [ ] The selected workflow requires every modified function/method signature to fit on one physical line. `BaseAgent.__init__` has many established public keyword-only parameters; confirm that preserving this literal formatting rule is preferred over a more readable multi-line public signature, or authorize a documented exception.
- [ ] The branch setup phase will require a clean, current `main`. The present checkout has unrelated untracked design docs and nested worktrees; if that state prevents the required worktree setup after approval, should the existing untracked work be preserved in place while you supply a clean base, or should a separate clean clone be used?

---

## 13. Alternatives Considered

### Alternative 1: Update Only Headers and the Agents README

- What: Improve navigational documentation without touching function structure or error classes.
- Why rejected: It would omit the linked prompt's function-design, intent-comment, and error-context principles at exactly the public/runtime boundaries the user named.

### Alternative 2: Keep Generic Shared Errors and Add Larger `details` Dictionaries

- What: Continue raising only `AgentExecutionError`, `ConfigurationError`, and tool errors, with more data supplied at each raise site.
- Why rejected: Static diagnostic context would be duplicated, drift from the code, and fail the one-failure-mode-per-class principle. Subsystem-local subclasses preserve broad catch compatibility while making the error type itself navigable.

### Alternative 3: Move the Entire Agent Runtime into New Modules

- What: Extract construction, execution, tracing, and tool handling into several new production modules.
- Why rejected: The request names the base-agent and runtime files, and a broad relocation would create API/import churn and extend the change surface beyond an agent-readable refactor. Private state objects and local leaf methods deliver the comprehension benefit while preserving canonical module ownership.

### Alternative 4: Add a New Feature Test Pack

- What: Create `FEATURE.md` and new behavior-focused test files for agent construction, runtime looping, and diagnostic packets.
- Why rejected: The user selected the explicit no-tests design workflow and this design preserves existing runtime behavior rather than adding a durable new feature. If approval instead requests literal feature-test-pack coverage, this alternative should become a separate expanded design.


