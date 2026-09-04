# Design Doc: Codex Harness Agent

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-03
**Last Updated:** 2026-09-03

---

## 1. Overview

Add a first-class `CodexHarnessAgent` that presents a Vidbyte-shaped agent API while delegating the inner agent loop to the official Codex Python SDK. The first release intentionally translates only five core capabilities: system prompts, additional context, structured output, provider-native thread forking, and Codex-owned subagents. The implementation is split into a small public agent class plus configuration, context, result, and transport collaborators so provider protocol details do not accumulate in one file. A repository skill package explains when to use harness agents, how runtime primitives compose them, and which control surfaces belong to Vidbyte versus the native host.

---

## 2. Goals & Non-Goals

### Goals

- Execute real Codex turns through the stable `openai-codex` Python package.
- Translate `system_prompt` into Codex developer instructions.
- Translate static additional context, `ContextManager`, and per-run `AgentInput` context into a deterministic turn-boundary prompt block.
- Translate Vidbyte output schemas into Codex `output_schema` and validate the returned final response with `OutputSchemaFormatter`.
- Fork an established Codex thread through the provider-native `thread_fork` operation.
- Configure Codex-owned subagents and normalize their activity from returned turn items into `AgentMessage.metadata`.
- Export the new public types through `vidbyte.agents` and the package root.
- Keep Codex an optional installation extra so importing the base SDK does not install a large pinned CLI binary.
- Append a complete future-translation checklist to the requested Obsidian knowledge note.
- Add an agent-readable runtime-primitives skill with Codex, Claude Agent SDK, and cross-provider control references.

### Non-Goals

- Do not translate tools, MCP, permissions, middleware, arbitrary loop limits, compaction, tracing providers, usage pricing, handoffs, or durable Vidbyte `Session` restoration in this change.
- Do not make `CodexHarnessAgent` inherit `BaseAgent` or register Codex as an `AgentRuntimeType`; Codex owns the inner loop.
- Do not synthesize Vidbyte `BaseAgent` objects for Codex subagent threads.
- Do not generate or mutate `.codex/agents/*.toml` custom-agent files.
- Do not add new feature-specific test files under the requested no-tests workflow.

---

## 3. Background & Context

`BaseAgent` and `AgentRuntime` currently assume Vidbyte owns every model/tool iteration. Codex instead exposes a complete coding-agent harness through its Python SDK and local app-server. Treating Codex as a model provider or a Vidbyte runtime would put one agent loop inside another and make iteration, middleware, and tool guarantees dishonest.

The official stable Python SDK exposes thread start, resume, fork, and turn execution. Thread start accepts developer instructions and a configuration object; a turn accepts `output_schema`; results include final text, token usage, and typed thread items including collaboration/subagent activity. The stable SDK does not expose an `additionalContext` argument, so additional context must be rendered into a clearly delimited turn input until that field reaches the stable Python surface.

The repository already centralizes context rendering in `ContextManager`, schema handling in `OutputSchemaFormatter`, messages in `AgentMessage`, and typed configuration in frozen dataclasses. The new feature reuses those surfaces and preserves the existing `Harness` class as the outer reproducible execution envelope.

---

## 4. Requirements

### Functional Requirements

1. `CodexHarnessAgent.arun()` must lazily import and execute the official async Codex SDK without breaking normal `import vidbyte` when the optional dependency is absent.
2. `CodexHarnessAgent.run()` must mirror `BaseAgent.run()` and reject calls made from an active event loop.
3. The first run must create a Codex thread; later runs must resume the recorded thread id.
4. The configured system prompt must be passed as Codex developer instructions on start, resume, and fork.
5. Static additional context, agent-level `ContextManager`, and per-call `AgentInput` context must render deterministically before the user prompt without mutating their source objects.
6. Pydantic model and mapping output schemas must be resolved through `OutputSchemaFormatter`, passed to Codex, locally validated, and exposed through `AgentMessage.structured`.
7. An invalid structured result must raise `OutputSchemaViolationError` with safe validation details after preserving the raw final response in the exception.
8. `afork()` must use Codex `thread_fork` and return a new `CodexHarnessAgent` with isolated thread identity and fork-lineage metadata.
9. Synchronous `fork()` must wrap `afork()` and reject active event loops.
10. Forking before a parent thread exists must fail clearly rather than creating an unrelated thread.
11. Subagent settings must map to Codex's `agents.enabled`, concurrency, default model, default reasoning effort, and interruption-message configuration.
12. Returned collaboration and subagent activity items must be serialized into a bounded, typed metadata list without exposing hidden reasoning.
13. Public metadata must include Codex thread id, turn id, turn status, duration, usage, subagent activity, and fork lineage when available.
14. The requested Obsidian note must end with a categorized checklist covering all remaining translation work and marking the five implemented capabilities.
15. The top-level skill must distinguish a harness agent from a Vidbyte-owned model loop and route readers to focused Codex, Claude, and translation references.
16. The skill must state which controls can be translated exactly, which need an adapter policy, and which remain provider-owned.

### Non-Functional Requirements

- A normal SDK import must not import or require `openai_codex`.
- Every public settings object must be frozen, slot-based, and valid immediately after construction.
- Provider failures must cross the public boundary as `AgentExecutionError` or an existing more-specific Vidbyte error with the original exception chained.
- Secrets, environment values, raw SDK configuration, and private reasoning must not enter `AgentMessage.metadata`.
- Returned provider item metadata must be bounded to the current turn result rather than accumulated without limit.
- The implementation must preserve async cancellation and close the app-server client after each start/resume/fork operation.
- Existing source, lint, package, and pull-request checks must pass without weakening any gate.

---

## 5. High-Level Design

`CodexHarnessAgent` is a façade over a Codex-owned thread. It stores Vidbyte-facing configuration and local reply history, delegates wire interaction to `CodexTransport`, and asks focused translator classes to prepare configuration/context and normalize results. The transport opens one `AsyncCodex` client per operation, starts or resumes the durable provider thread, runs the turn, and closes the client deterministically.

Configuration is split between frozen public records and translators. `CodexAgentSettings` describes thread/turn behavior, `CodexSubagentSettings` describes provider-owned multi-agent controls, and `CodexForkSettings` describes provider-native fork overrides. Context translation is turn-boundary only. Result translation resolves and validates structured output, serializes SDK items through their typed `model_dump()` boundary, and selects only collaboration/subagent item kinds for the dedicated metadata field.

```text
CodexHarnessAgent
    |-- CodexConfigurationTranslator -> thread/turn kwargs
    |-- CodexContextTranslator       -> delimited RunInput
    |-- CodexTransport               -> AsyncCodex start/resume/run/fork
    `-- CodexResultTranslator        -> AgentMessage + structured output
```

---

## 6. Detailed Design

### 6.1 Public Configuration Records

**File(s):** `vidbyte/agents/codex/config.py`
**Type:** New file

#### What it does

Defines immutable settings for the agent, Codex-owned subagents, and provider-native forks. Validation rejects empty strings, invalid concurrency, and inconsistent subagent defaults before any provider process starts. `CodexConfigurationTranslator` converts those settings to stable Python SDK keyword arguments and the nested Codex `agents` configuration.

#### Interface / API

```python
class CodexSubagentSettings:
    enabled: bool = True
    max_concurrent_threads: int | None = None
    default_model: str | None = None
    default_reasoning_effort: str | None = None
    interrupt_message: bool = True

class CodexAgentSettings:
    model: str | None = None
    cwd: str | None = None
    sandbox: str | None = None
    approval_mode: str | None = None
    reasoning_effort: str | None = None
    personality: str | None = None
    summary: str | None = None
    service_tier: str | None = None
    ephemeral: bool = False
    subagents: CodexSubagentSettings = CodexSubagentSettings()

class CodexForkSettings:
    name: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    additional_context: str | None = None
    context_manager: ContextManager | None = None
    output_schema: type | Mapping[str, Any] | None = None
    ephemeral: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

class CodexConfigurationTranslator:
    @classmethod
    def client_config(cls, settings: CodexAgentSettings) -> Any: ...
    @classmethod
    def thread_kwargs(cls, system_prompt: str, settings: CodexAgentSettings) -> dict[str, Any]: ...
    @classmethod
    def turn_kwargs(cls, settings: CodexAgentSettings, output_schema: Mapping[str, Any] | None) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. Validate all settings in each frozen dataclass `__post_init__`.
2. Translate public strings into SDK enums only after the optional SDK is imported.
3. Emit only non-`None` keyword arguments so the Codex configured defaults remain effective.
4. Place subagent controls under the Codex `agents` configuration object.

#### Edge Cases & Error Handling

- Empty optional strings fail at configuration time.
- Non-positive concurrency fails at configuration time.
- Unknown enum values fail with `ConfigurationError` naming the field, not provider internals.
- Disabled subagents do not discard explicitly supplied defaults; configuration remains serializable if later enabled through a forked agent.

### 6.2 Context Translation

**File(s):** `vidbyte/agents/codex/context.py`
**Type:** New file

#### What it does

Builds one deterministic Codex turn input from the user request and Vidbyte context sources. It reuses each `ContextItem.to_context_text()` and `ContextManager.render_primitives_zone()` rather than inventing a second context representation.

#### Interface / API

```python
class CodexContextTranslator:
    @classmethod
    def translate(cls, message: str | AgentInput, *, static_context: str | None, context_manager: ContextManager | None) -> CodexPrompt: ...
```

#### Logic / Algorithm

1. Normalize `str` and `AgentInput` into prompt, metadata, context items, and optional per-call manager.
2. Render static context first, agent-level context second, and per-call context last.
3. Deduplicate identical non-empty rendered blocks while preserving order.
4. Wrap context and request in explicit XML-like boundaries.
5. Return the prompt plus the input metadata separately.

#### Edge Cases & Error Handling

- An empty prompt raises `AgentExecutionError`.
- Empty context sources are omitted completely.
- Context placement within a `ContextManager` is preserved by its existing render methods where possible; Codex still receives the result at a turn boundary.

### 6.3 Result Translation

**File(s):** `vidbyte/agents/codex/result.py`
**Type:** New file

#### What it does

Defines a small internal transport result and converts it into a Vidbyte `AgentMessage`. It validates structured output and extracts only provider item kinds relevant to Codex subagents.

#### Interface / API

```python
class CodexRunResult: ...

class CodexResultTranslator:
    def translate(self, result: CodexRunResult, *, agent_name: str, recipient: str, input_metadata: Mapping[str, Any], output_schema: type | Mapping[str, Any] | None, agent_metadata: Mapping[str, Any]) -> AgentMessage: ...
```

#### Logic / Algorithm

1. Require a non-null final response.
2. Resolve and validate structured output when configured.
3. Serialize token usage and current-turn provider items through stable typed model serialization.
4. Filter collaboration and subagent activity items into `metadata["subagents"]`.
5. Construct the final `AgentMessage` with provider identifiers and safe metadata.

#### Edge Cases & Error Handling

- Missing final text is an `AgentExecutionError`.
- Invalid JSON or Pydantic output raises `OutputSchemaViolationError`.
- Unknown future item types are retained only in the count, not copied wholesale into public metadata.
- Private reasoning content is never copied into the subagent metadata list.

### 6.4 Codex Transport

**File(s):** `vidbyte/agents/codex/transport.py`
**Type:** New file

#### What it does

Owns lazy SDK import, process lifecycle, thread start/resume, full-turn execution, and thread fork. This is the only module that calls `openai_codex` runtime objects.

#### Interface / API

```python
class CodexTransport:
    async def run(self, *, thread_id: str | None, system_prompt: str, prompt: str, settings: CodexAgentSettings, output_schema: Mapping[str, Any] | None) -> CodexRunResult: ...
    async def fork(self, *, thread_id: str, system_prompt: str, settings: CodexAgentSettings, ephemeral: bool | None) -> str: ...
```

#### Logic / Algorithm

1. Lazily import `AsyncCodex` and construct its config.
2. Open the client through its async context manager.
3. Start a new thread or resume the supplied thread id.
4. Execute one complete turn and normalize the SDK result into `CodexRunResult`.
5. For forks, invoke `thread_fork` and return the new thread id.

#### Edge Cases & Error Handling

- Missing optional dependency raises `ConfigurationError` with the `vidbyte-sdk[codex]` installation command.
- Start, resume, turn, and fork failures become `AgentExecutionError` with safe operation metadata and chained causes.
- Cancellation is re-raised without translation.
- The client closes on success and failure.

### 6.5 Public Agent

**File(s):** `vidbyte/agents/codex/agent.py`, `vidbyte/agents/codex/__init__.py`
**Type:** New files

#### What it does

Provides the developer-facing `CodexHarnessAgent`, owns thread identity and local reply history, and composes all translators and the transport. The class deliberately does not inherit the Vidbyte-owned-loop `BaseAgent`.

#### Interface / API

```python
class CodexHarnessAgent:
    def __init__(self, *, name: str, system_prompt: str, settings: CodexAgentSettings | None = None, additional_context: str | None = None, context_manager: ContextManager | None = None, output_schema: type | Mapping[str, Any] | None = None, description: str = "", capabilities: Sequence[str] = (), metadata: Mapping[str, Any] | None = None, thread_id: str | None = None) -> None: ...
    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage: ...
    def run(self, message: str | AgentInput, **options: Any) -> AgentMessage: ...
    async def afork(self, settings: CodexForkSettings | None = None) -> CodexHarnessAgent: ...
    def fork(self, settings: CodexForkSettings | None = None) -> CodexHarnessAgent: ...
```

#### Logic / Algorithm

1. Validate the Vidbyte-facing identity and retain immutable settings.
2. Translate the turn input and output schema.
3. Run through `CodexTransport`, saving the returned thread id.
4. Translate the result, append it to history, and update `last_prompt`/`last_reply`.
5. Fork through the transport and construct an isolated child with copied configuration and lineage metadata.

#### Edge Cases & Error Handling

- `run()` and `fork()` reject active event loops with the same guidance as `BaseAgent`.
- Arbitrary `**options` are rejected in phase one so unsupported controls cannot silently disappear.
- A failed run does not append a successful reply or replace `last_reply`.
- A forked child begins with no local reply history but its provider thread contains the copied Codex history.

### 6.6 Package Exports and Dependency

**File(s):** `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `pyproject.toml`, `README.md`
**Type:** Modified

#### What it does

Exports the public Codex types, adds the bounded `codex` optional dependency extra, and documents the minimal installation and usage path.

#### Interface / API

```toml
[project.optional-dependencies]
codex = ["openai-codex>=0.147.0,<0.148.0"]
```

#### Logic / Algorithm

1. Re-export the agent and its three settings records from `vidbyte.agents`.
2. Re-export the same public surface from `vidbyte`.
3. Keep all module-level imports free of `openai_codex`.
4. Add one concise README example.

#### Edge Cases & Error Handling

- Installing `vidbyte-sdk` without `[codex]` remains supported.
- Package verification must prove the new subpackage and README-facing imports exist in the built wheel.

### 6.7 Knowledge Checklist

**File(s):** `C:\Users\422mi\knowledge\knowledge\Vidbyte\Codex\Vidbyte SDK.md`
**Type:** Modified external knowledge artifact

#### What it does

Appends a categorized checklist of every identified Vidbyte-to-Codex translation, marking the five capabilities in this change and leaving all later capabilities unchecked.

#### Interface / API

N/A - Markdown knowledge artifact, not a runtime API.

#### Logic / Algorithm

1. Preserve all existing note content.
2. Append one uniquely named checklist section at end of file.
3. Cover execution, prompting, context, tools, permissions, middleware, limits, sessions, tracing, usage, failures, and multi-agent behavior.

#### Edge Cases & Error Handling

- Do not duplicate the section if rerun.
- Do not write credentials or raw session contents.

### 6.8 Runtime Primitives Skill

**File(s):** `skills/runtime-primitives/SKILL.md`, `skills/runtime-primitives/references/runtime-primitives.md`, `skills/runtime-primitives/references/codex-sdk.md`, `skills/runtime-primitives/references/claude-agent-sdk.md`, `skills/runtime-primitives/references/control-matrix.md`
**Type:** New files

#### What it does

Gives downstream coding agents a concise entry point for deciding when a native harness agent is appropriate, then routes them to provider-specific control inventories and the translation matrix. The skill documents the architectural rule that Vidbyte owns composition and normalization while Codex or Claude owns its internal tool loop.

#### Interface / API

```text
skills/runtime-primitives/
|-- SKILL.md
`-- references/
    |-- runtime-primitives.md
    |-- codex-sdk.md
    |-- claude-agent-sdk.md
    `-- control-matrix.md
```

#### Logic / Algorithm

1. Trigger when a developer designs or extends a native coding-agent harness adapter or local runtime primitive.
2. Read the shared runtime-primitives model first.
3. Read only the provider reference needed for the implementation.
4. Consult the control matrix before promising parity across providers.

#### Edge Cases & Error Handling

- Documentation must not claim that a translated setting transfers control of the provider-owned loop to Vidbyte.
- Version-sensitive fields must point readers to official SDK documentation instead of being treated as permanent guarantees.
- The skill must not instruct an agent to expose credentials, hidden reasoning, or raw process environment values.

---

## 7. Data Model Changes

### 7.1 Codex Configuration and Result Records

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class CodexAgentSettings: ...

@dataclass(frozen=True, slots=True)
class CodexSubagentSettings: ...

@dataclass(frozen=True, slots=True)
class CodexForkSettings: ...

@dataclass(frozen=True, slots=True)
class CodexRunResult: ...
```

**Migration strategy:**

- Forward migration: N/A - additive public types with no persisted schema.
- Rollback plan: Remove the additive exports and optional dependency; no stored Vidbyte data requires migration.

---

## 8. API Changes

### 8.1 Python `CodexHarnessAgent`

**Change type:** New

**Request:**

```json
{
  "message": "string or AgentInput",
  "configuration": "CodexAgentSettings supplied at construction"
}
```

**Response:**

```json
{
  "type": "AgentMessage",
  "content": "Codex final response",
  "structured": "validated object or null",
  "metadata": "safe Codex thread/turn, usage, subagent, and lineage fields"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| Python `ConfigurationError` | Optional Codex package missing or settings invalid |
| Python `AgentExecutionError` | Thread or turn operation fails or returns no final response |
| Python `OutputSchemaViolationError` | Codex final response does not satisfy the declared schema |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-harness-agent.md` | Source-of-truth design |
| CREATE | `vidbyte/agents/codex/__init__.py` | Public Codex agent subpackage exports |
| CREATE | `vidbyte/agents/codex/agent.py` | Main `CodexHarnessAgent` façade |
| CREATE | `vidbyte/agents/codex/config.py` | Frozen settings and SDK configuration translation |
| CREATE | `vidbyte/agents/codex/context.py` | Additional-context translation |
| CREATE | `vidbyte/agents/codex/result.py` | Turn result and subagent metadata translation |
| CREATE | `vidbyte/agents/codex/transport.py` | Lazy official SDK transport and thread lifecycle |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export new public types |
| MODIFY | `vidbyte/__init__.py` | Re-export new public types at package root |
| MODIFY | `pyproject.toml` | Add bounded optional Codex SDK extra |
| MODIFY | `README.md` | Document installation and minimal usage |
| CREATE | `skills/runtime-primitives/SKILL.md` | Route harness-agent and runtime-primitive development work |
| CREATE | `skills/runtime-primitives/references/runtime-primitives.md` | Explain the shared local composition model and intended use cases |
| CREATE | `skills/runtime-primitives/references/codex-sdk.md` | Inventory Codex SDK controls and ownership boundaries |
| CREATE | `skills/runtime-primitives/references/claude-agent-sdk.md` | Inventory Claude Agent SDK controls and ownership boundaries |
| CREATE | `skills/runtime-primitives/references/control-matrix.md` | Compare exact, policy-based, and unavailable translations |
| MODIFY | `C:\Users\422mi\knowledge\knowledge\Vidbyte\Codex\Vidbyte SDK.md` | Append complete translation checklist outside the repository |

Repository count: 12 files created, 4 files modified, 0 files deleted. External knowledge count: 0 files created, 1 file modified, 0 files deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | `>=0.147.0,<0.148.0` optional extra | Stable Python SDK controlling local Codex app-server | Pre-1.0 API drift requires deliberate version upgrades |
| Local Codex app-server | Pinned transitively by `openai-codex` | Execute threads, turns, forks, and subagents | Requires local authentication and can perform workspace actions according to Codex policy |

---

## 11. Rollout & Deployment

- No feature flag is required because the new class is additive and only runs when constructed.
- Existing users receive no new dependency unless they install `vidbyte-sdk[codex]`.
- Release the package with the bounded Codex extra and advance the upper bound only after compatibility verification.
- Roll back by reverting the additive files/exports and optional extra. Provider threads already created by users remain Codex-owned and are not deleted.

---

## 12. Open Questions

- [ ] Should a later change make `CodexHarnessAgent` compatible with durable Vidbyte `Session` through a shared agent protocol and provider-state checkpoint field?
- [ ] Should custom Vidbyte agent descriptors later materialize as project-scoped `.codex/agents/*.toml`, or remain an explicitly separate Codex configuration workflow?
- [ ] Which Codex SDK versions should be admitted after `0.147.x` once compatibility automation exists?

---

## 13. Alternatives Considered

### Alternative 1: Make Codex a `ModelProvider`

- What: Route Codex through the existing provider runner abstraction.
- Why rejected: A model provider represents one model call, while Codex owns a complete multi-step tool-using loop. The abstraction would misstate control and lifecycle semantics.

### Alternative 2: Add Codex as an `AgentRuntimeType`

- What: Run Codex inside the current `AgentRuntime` selection machinery.
- Why rejected: `AgentRuntime` assumes Vidbyte controls model/tool iterations; wrapping Codex there creates nested loops and false middleware/limit guarantees.

### Alternative 3: Subclass `BaseAgent`

- What: Reuse `BaseAgent` state and override execution.
- Why rejected: Construction still initializes direct-runtime state and exposes methods whose documented semantics cannot be honored. A future shared agent protocol is safer than inheritance from the wrong lifecycle owner.

### Alternative 4: Call the app-server JSON-RPC transport directly

- What: Implement process startup, initialization, routing, and schema handling inside Vidbyte.
- Why rejected: The stable official Python SDK already owns those responsibilities and pins a compatible CLI. Direct JSON-RPC becomes appropriate only when a required stable app-server capability remains unavailable through the SDK.
