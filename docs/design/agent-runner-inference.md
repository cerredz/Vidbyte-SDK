# Design Doc: Agent Runner Inference

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

This change removes public runner and modality configuration from `Agent` / `BaseAgent`. Agents will be configured with model/provider identity only, and an internal `Runner` utility will resolve the correct concrete runner type from centralized constants under `vidbyte/lib/constants/`.

---

## 2. Goals & Non-Goals

### Goals

- Remove `runner`, `runners`, `runner_options`, and `modality` from the public `BaseAgent` constructor.
- Remove per-call `modality` routing from `generate_reply()`, `arun()`, and `run()`.
- Stop exposing modality on `AgentInput`; keep `AgentInput` for prompt metadata and context only.
- Add `vidbyte/lib/constants/` with dictionary constants mapping provider/model names to internal runner types.
- Add a class-based runner utility that takes provider/model strings and returns the correct executable runner object.
- Keep concrete runner classes available under `vidbyte.lib.runners` for lower-level SDK internals and dedicated runner tests.
- Update README and agent docs so user-facing examples construct agents with `provider=` and `model_name=`, not runner objects or modality flags.

### Non-Goals

- No deletion of concrete runner implementations such as `TextModelRunner`, `ImageModelRunner`, `VideoModelRunner`, `AudioModelRunner`, or `EmbeddingModelRunner`.
- No new provider integrations, API endpoints, transport behavior, or live network tests.
- No natural-language prompt classifier for choosing runner type.
- No support for user-supplied runner objects on `BaseAgent` after this change.
- No broad rewrite of agent runtime loops, middleware, tracing, tools, or context-window algorithms.

---

## 3. Background & Context

The current SDK already has an internal routing path: `BaseAgent` accepts primitive `provider` / `model_name` fields, stores them in `AgentRunnerConfig`, and lazily creates concrete runners through `ModalityDetector.create_runner()`. However, the public agent surface still accepts `runner`, `runners`, `runner_options`, constructor `modality`, per-call `modality`, and `AgentInput.modality`.

That mixed surface makes the agent API harder to explain. The user specifically wants the SDK to decide which runner type a model/provider belongs to internally, using a mapping in `vidbyte/lib/constants/` and a `Runner` utility class. The existing `vidbyte.lib.runners.router` module is function-based and delegates to `ModalityDetector`; this design replaces the public-facing dependency on modality with model/provider-based runner inference.

Relevant local files audited:

- `vidbyte/agents/base.py`: public `BaseAgent` constructor, direct run flow, fork behavior, runner selection, and reply metadata.
- `vidbyte/lib/agents/modality_detector.py`: existing model-name modality detection and runner construction.
- `vidbyte/lib/enums/model_modality.py`: existing internal runner capability vocabulary.
- `vidbyte/lib/runners/router.py`: current compatibility wrapper around `ModalityDetector`.
- `vidbyte/lib/runners/*`: concrete runner implementations and response types.
- `vidbyte/lib/dataclasses/agents.py`: `AgentRunnerConfig`, `AgentInput`, `AgentCard`, runtime config, and message types.
- `README.md`, `vidbyte/agents/README.md`, `vidbyte/lib/README.md`: public docs that currently mention runner or modality concepts.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent.__init__()` must no longer accept `runner`.
2. `BaseAgent.__init__()` must no longer accept `runners`.
3. `BaseAgent.__init__()` must no longer accept `runner_options`.
4. `BaseAgent.__init__()` must no longer accept `modality`.
5. `BaseAgent.generate_reply()`, `BaseAgent.arun()`, and `BaseAgent.run()` must no longer accept a `modality` option.
6. `AgentInput` must no longer expose a `modality` field.
7. Agents must resolve an executable runner from `provider` and `model_name` through a class-based utility, not direct public runner injection.
8. The runner utility must use dictionary constants under `vidbyte/lib/constants/` as the source of truth for model/provider to runner-type mapping.
9. Exact model/provider mappings must win over provider defaults.
10. Unknown model names with recognized text-model prefixes must resolve to text runner type.
11. Unknown provider/model combinations must raise `ConfigurationError` with a clear message rather than falling through to a placeholder runner.
12. `BaseAgent` must keep lazy runner creation and cache inferred runners internally by runner type.
13. `fork()` must preserve primitive provider/model settings and inferred runner cache behavior without accepting explicit runner overrides.
14. `card()` must avoid advertising user-selectable modalities; if capability metadata is retained, it must be derived from inferred runner type, not constructor parameters.
15. README and docs must show `provider=` / `model_name=` examples only for agents.
16. Existing lower-level runner tests may continue importing concrete runners from `vidbyte.lib.runners`.

### Non-Functional Requirements

- Performance: runner-type resolution must be constant-time for exact mappings and bounded for prefix/pattern fallback.
- Security: API keys continue to flow through existing config objects and environment resolution. No secrets in docs or tests.
- Reliability: plain prompt text must not influence runner choice.
- Maintainability: model/provider routing constants live in one package and are reused by agents and runner helpers.
- Compatibility: this is an intentional breaking cleanup for agent construction, but concrete runner classes remain available for internal and advanced lower-level use.
- Observability: trace metadata should continue to include provider and model. Runner type may be included as internal metadata if useful.

---

## 5. High-Level Design

The new flow makes `BaseAgent` a primitive model/provider configuration object. A caller creates an agent with `provider="openai"` and `model_name="gpt-image-1"`; the agent asks `Runner` to resolve and build the internal runner. The caller never supplies a runner object, runner mapping, runner options, or modality flag.

`vidbyte/lib/constants/runners.py` will hold dictionary constants such as exact model mappings, provider defaults, and model-prefix fallbacks. `vidbyte/lib/runners/utility.py` will define a `Runner` class with methods for normalizing provider/model strings, resolving runner type, and building the concrete runner. `BaseAgent` will delegate runner creation to that class and cache the result internally.

```text
User code
  |
  v
BaseAgent(provider="openai", model_name="gpt-image-1")
  |
  v
Runner.resolve_runner_type(provider="openai", model_name="gpt-image-1")
  |
  v
MODEL_PROVIDER_RUNNER_TYPE_MAP / MODEL_RUNNER_TYPE_MAP / PROVIDER_DEFAULT_RUNNER_TYPE_MAP
  |
  v
Runner.build(...)
  |
  +-- text -> TextModelRunner
  +-- image -> ImageModelRunner
  +-- video -> VideoModelRunner
  +-- audio -> AudioModelRunner
  +-- embedding -> EmbeddingModelRunner
```

This keeps the user-facing agent API simple while preserving the existing runner implementation layer.

---

## 6. Detailed Design

### 6.1 Runner Constants

**File(s):** `vidbyte/lib/constants/__init__.py`, `vidbyte/lib/constants/runners.py`
**Type:** New file

#### What it does

Defines central dictionaries that map normalized provider/model names to internal runner type strings.

#### Interface / API

```python
RUNNER_TYPE_TEXT = "text"
RUNNER_TYPE_IMAGE = "image"
RUNNER_TYPE_VIDEO = "video"
RUNNER_TYPE_AUDIO = "audio"
RUNNER_TYPE_EMBEDDING = "embedding"

MODEL_PROVIDER_RUNNER_TYPE_MAP: dict[str, str] = {
    "openai/gpt-image-1": RUNNER_TYPE_IMAGE,
    "openai/sora": RUNNER_TYPE_VIDEO,
    "openai/tts-1": RUNNER_TYPE_AUDIO,
    "openai/text-embedding-3-small": RUNNER_TYPE_EMBEDDING,
}

MODEL_RUNNER_TYPE_MAP: dict[str, str] = {
    "gpt-4.1": RUNNER_TYPE_TEXT,
    "gpt-image-1": RUNNER_TYPE_IMAGE,
    "sora": RUNNER_TYPE_VIDEO,
}

PROVIDER_DEFAULT_RUNNER_TYPE_MAP: dict[str, str] = {
    "openai": RUNNER_TYPE_TEXT,
    "anthropic": RUNNER_TYPE_TEXT,
    "gemini": RUNNER_TYPE_TEXT,
    "elevenlabs": RUNNER_TYPE_AUDIO,
    "playai": RUNNER_TYPE_AUDIO,
}

MODEL_PREFIX_RUNNER_TYPE_MAP: dict[str, str] = {
    "gpt-": RUNNER_TYPE_TEXT,
    "claude-": RUNNER_TYPE_TEXT,
    "gemini-": RUNNER_TYPE_TEXT,
    "dall-e": RUNNER_TYPE_IMAGE,
    "gpt-image": RUNNER_TYPE_IMAGE,
    "sora": RUNNER_TYPE_VIDEO,
    "tts-": RUNNER_TYPE_AUDIO,
    "text-embedding": RUNNER_TYPE_EMBEDDING,
}
```

#### Logic / Algorithm

1. Normalize keys to lowercase except where existing provider APIs require case-sensitive model values at request time.
2. Store lookup constants only; no construction logic belongs in this module.
3. Export all constants through `vidbyte.lib.constants`.

#### Edge Cases & Error Handling

- Constants do not raise errors. The `Runner` utility owns validation and error messages.
- Prefix fallback must not override exact mappings.

---

### 6.2 Runner Utility Class

**File(s):** `vidbyte/lib/runners/utility.py`, `vidbyte/lib/runners/router.py`, `vidbyte/lib/runners/__init__.py`
**Type:** New file, Modified

#### What it does

Adds the requested class-based utility for resolving and building runner objects from provider/model strings. Keeps existing function wrappers as compatibility shims where useful.

#### Interface / API

```python
class Runner:
    def __init__(self, *, provider: ModelProvider | str | None, model_name: str | None, api_key: str | None = None, temperature: float | None = None, options: Mapping[str, Any] | None = None) -> None:
        # Stores primitive model/provider configuration for later runner construction.

    def resolve_runner_type(self) -> str:
        # Returns the internal runner type for this provider/model pair.

    def build(self, *, transport: object | None = None) -> object:
        # Builds and returns the concrete runner for the resolved runner type.

    @classmethod
    def from_model(cls, *, provider: ModelProvider | str | None, model_name: str | None, **kwargs: Any) -> Runner:
        # Creates a Runner utility instance from primitive model/provider values.
```

#### Logic / Algorithm

1. Normalize `provider` and `model_name`.
2. If model name contains a provider prefix such as `openai/gpt-4.1`, split it into provider and model when no explicit provider was supplied.
3. Try exact `provider/model` lookup.
4. Try exact model lookup.
5. Try prefix lookup against the model name.
6. Try provider default lookup.
7. Raise `ConfigurationError` if no runner type can be resolved.
8. Build the matching config dataclass and concrete runner.
9. Pass through known config options only, following the current `ModalityDetector.build_config()` filtering behavior.

#### Edge Cases & Error Handling

- Missing both provider and model raises `ConfigurationError`.
- Missing provider for a model that cannot imply a provider raises `ConfigurationError`.
- Unknown provider raises `ConfigurationError` using the existing `ModelProvider` enum validation.
- Provider/model combinations mapped to unsupported concrete runner types raise `ConfigurationError`.
- `runner_options` is not accepted by `BaseAgent`; any internal options come from explicit stable agent parameters such as `api_key`, `temperature`, and `run_id`.

---

### 6.3 BaseAgent Public API Cleanup

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Removes runner and modality parameters from the public agent API and delegates runner construction to the new `Runner` utility.

#### Interface / API

```python
class BaseAgent(McpAttachableMixin):
    def __init__(self, *, name: str, system_prompt: str, runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR, tools: Sequence[object] | Tools = (), permission_policy: PermissionPolicy | None = None, agent_loop_settings: AgentLoopSettings | None = None, max_tool_rounds: int | None = None, max_iterations: int | None = None, max_tokens: int | None = None, compaction_trigger_tokens: int | None = None, compaction_target_tokens: int | None = None, middleware: Sequence[AgentMiddleware] = (), api_key: str | None = None, provider: ModelProvider | str | None = None, model_name: str | Sequence[str] | None = None, proposers: Sequence[Any] | None = None, aggregator: Any | None = None, aggregate: AggregateConfig | None = None, temperature: float | None = None, run_id: str | None = None, description: str = "", capabilities: Sequence[str] = (), agent_metadata: AgentMetadata | None = None, context_items: Sequence[ContextItem] = (), context_manager: ContextManager | None = None, algorithm: ContextWindowAlgorithm | str | None = None, metadata: dict[str, Any] | None = None, tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None, output_schema: type | Mapping[str, Any] | None = None, handoff: Handoff | None = None, trace_option: TraceOption | None = None) -> None:
        # Configures an agent from stable primitive values only.

    async def generate_reply(self, message: str | AgentInput, *, context: BaseContext | None = None, history: Sequence[AgentMessage] = (), recipient: str = "orchestrator", **options: Any) -> AgentMessage:
        # Runs the agent using the internally inferred runner.
```

#### Logic / Algorithm

1. Remove `runner`, `runners`, `runner_options`, and `modality` from `__init__`.
2. Keep `provider`, `model_name`, `api_key`, `temperature`, and `run_id` as primitive model execution configuration.
3. Replace `self.runner` and `self.runners` public-like state with internal `_runner_cache: dict[str, object]`.
4. Replace `_runner_for_modality()` with `_runner_for_model()`.
5. `_runner_for_model()` calls `Runner.from_model(...).resolve_runner_type()` and caches the built runner by runner type.
6. `generate_reply()` normalizes input, creates or retrieves the runner, builds context, and calls `_run_direct()` as it does today.
7. Reply metadata includes `runner_type`, `provider`, and `model_name` where available, instead of `modality`.
8. `fork()` removes runner override arguments and preserves primitive model/provider config.
9. `ConfiguredAgentRunner` is deleted unless still needed by another internal path; if retained temporarily, it must not be reachable from `BaseAgent` construction.

#### Edge Cases & Error Handling

- Agent construction without enough provider/model information is allowed only until execution; execution raises `AgentExecutionError` wrapping the underlying `ConfigurationError`.
- Multi-model aggregation keeps its existing `model_name` sequence handling but builds proposer runners through the same utility path.
- Non-linear runtime restrictions remain unchanged.
- Custom runner injection through `BaseAgent` is intentionally removed. Lower-level runtime tests or advanced users must use `vidbyte.lib.runners` or `RunnerHandle` directly.

---

### 6.4 Agent Dataclasses And Types

**File(s):** `vidbyte/lib/dataclasses/agents.py`, `vidbyte/agents/types.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Removes public modality fields from agent dataclasses and exports while preserving context-oriented agent input.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    api_key: str | None = None
    provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    run_id: str | None = None

@dataclass(frozen=True, slots=True)
class AgentInput:
    prompt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None
```

#### Logic / Algorithm

1. Remove `modality` from `AgentRunnerConfig`.
2. Remove `options` from `AgentRunnerConfig` if it only exists to carry `runner_options`.
3. Remove `modality` from `AgentInput`.
4. Remove `modalities` from `AgentCard` or replace with derived non-configurable metadata if needed for compatibility.
5. Stop re-exporting `ModelModality` from `vidbyte.agents.types` as an agent-facing concept.
6. Keep `ModelModality` in `vidbyte.lib.enums` if lower-level runner/config code still uses it internally.

#### Edge Cases & Error Handling

- Code constructing `AgentInput(prompt="...")` continues to work.
- Code using `AgentInput(..., context_items=...)` continues to work.
- Code using `AgentInput(..., modality=...)` breaks intentionally and should move to model/provider selection.

---

### 6.5 Documentation Updates

**File(s):** `README.md`, `vidbyte/agents/README.md`, `vidbyte/lib/README.md`, `docs/design/agent-modality-routing.md`
**Type:** Modified

#### What it does

Aligns public documentation with the new agent API.

#### Interface / API

```python
from vidbyte import BaseAgent

agent = BaseAgent(
    name="asset-generator",
    system_prompt="Create useful product assets.",
    provider="openai",
    model_name="gpt-image-1",
)

reply = agent.run("A clean product mockup on a white desk")
```

#### Logic / Algorithm

1. Remove examples that pass `runner=`, `runners=`, `runner_options=`, or `modality=`.
2. Explain that agents infer runner type from provider/model identity.
3. Keep concrete runner class docs under lower-level runner sections only.
4. Update stale modality-routing design references to mark explicit modality parameters as superseded by this design.

#### Edge Cases & Error Handling

- README must not imply prompt text changes runner type.
- Docs must not include API keys.

---

## 7. Data Model Changes

### 7.1 `AgentRunnerConfig`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    api_key: str | None = None
    provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    run_id: str | None = None
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: remove modality/options fields and route through `Runner`.
- Rollback plan: restore removed fields and previous `BaseAgent` selection logic.

### 7.2 `AgentInput`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentInput:
    prompt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_items: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: callers stop using `AgentInput.modality`.
- Rollback plan: re-add the field if explicit input modality is restored.

---

## 8. API Changes

N/A - no HTTP endpoints are added or modified. This is a Python SDK API change.

### 8.1 Python SDK API: `BaseAgent`

**Change type:** Modified

**Request:**

```python
agent = BaseAgent(
    name="writer",
    system_prompt="Answer clearly.",
    provider="openai",
    model_name="gpt-4.1",
)
reply = await agent.arun("Draft a release note.")
```

**Response:**

```python
AgentMessage(
    sender="writer",
    recipient="orchestrator",
    content="...",
    metadata={"strategy": "direct_runner", "runner_type": "text", "provider": "openai", "model_name": "gpt-4.1"},
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing provider/model information raises `AgentExecutionError` during execution. |
| N/A | Unknown provider/model mapping raises `ConfigurationError`, wrapped by agent execution. |
| N/A | Passing removed parameters such as `runner=` or `modality=` raises Python `TypeError`. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-runner-inference.md` | Design doc for this change |
| CREATE | `vidbyte/lib/constants/__init__.py` | Export runner mapping constants |
| CREATE | `vidbyte/lib/constants/runners.py` | Central model/provider to runner-type dictionaries |
| CREATE | `vidbyte/lib/runners/utility.py` | Class-based `Runner` utility for resolving/building runners |
| MODIFY | `vidbyte/agents/base.py` | Remove runner/modality parameters and delegate to `Runner` utility |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Remove agent-facing modality/options fields |
| MODIFY | `vidbyte/agents/types.py` | Remove agent-facing `ModelModality` export and update `AgentInput` shape |
| MODIFY | `vidbyte/agents/__init__.py` | Adjust exports after public agent API cleanup |
| MODIFY | `vidbyte/__init__.py` | Adjust root exports and remove agent-facing modality emphasis |
| MODIFY | `vidbyte/lib/runners/router.py` | Delegate compatibility helpers to `Runner` where appropriate |
| MODIFY | `vidbyte/lib/runners/__init__.py` | Export `Runner` utility and keep concrete runner exports lower-level |
| MODIFY | `vidbyte/lib/agents/modality_detector.py` | Reuse constants or mark as internal compatibility for runner-type detection |
| MODIFY | `README.md` | Remove runner/modality examples and document model/provider inference |
| MODIFY | `vidbyte/agents/README.md` | Update agent usage and constructor guidance |
| MODIFY | `vidbyte/lib/README.md` | Document constants and runner utility role |
| MODIFY | `docs/design/agent-modality-routing.md` | Mark explicit modality parameter portions as superseded |
| MODIFY | `tests/test_agent_base.py` | Update existing tests away from removed constructor parameters |
| MODIFY | `tests/test_agent_modality_routing.py` | Rename/refocus existing tests to model/provider runner inference |
| MODIFY | `tests/test_agent_tool.py` | Update agent construction that currently injects fake runners |
| MODIFY | `tests/test_agent_tool_loop.py` | Update agent construction that currently injects fake runners |
| MODIFY | `tests/test_agent_behavior.py` | Update agent construction that currently injects fake runners |
| MODIFY | `scripts/test-readme-agent-modality-docs.py` | Update README verification expectations for runner inference |
| MODIFY | `scripts/test-agent-behavior.py` | Update script fixtures if they construct agents with `runner=` |
| MODIFY | `scripts/test-agent-output-behavior.py` | Update script fixtures if they construct agents with `runner=` |
| DELETE | N/A | No files planned for deletion |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` | SDK runtime | Existing requirement |
| pydantic | `>=2,<3` | Existing SDK validation dependency | No new dependency use |
| Provider APIs | Existing endpoints | Used only when real configured runners execute | No live calls in this change |

No new third-party dependencies or external services are introduced.

---

## 11. Rollout & Deployment

- No feature flag is planned.
- This is a breaking Python SDK API cleanup for `BaseAgent` callers that pass runner objects, runner mappings, runner options, or modality flags.
- Migration path: callers should configure agents with `provider=` and `model_name=`. Lower-level users can still instantiate concrete runners from `vidbyte.lib.runners`.
- Deployment is a library merge only.
- Rollback procedure: revert the PR to restore runner/modality parameters and the previous `ModalityDetector`-driven agent selection path.

---

## 12. Open Questions

- [ ] Should `provider` be required whenever `model_name` has no provider prefix, or should the SDK infer provider from well-known model prefixes such as `gpt-`, `claude-`, and `gemini-`?
- [ ] Should `AgentCard` remove `modalities` entirely, or keep a derived `runner_types` metadata field for discovery?
- [ ] Should `ModelModality` remain top-level exported from `vidbyte`, or move fully to lower-level `vidbyte.lib.enums` documentation after this cleanup?
- [ ] Should existing tests that currently rely on injected fake runners patch `Runner.build()` instead, or move those assertions down to runtime-level tests?

---

## 13. Alternatives Considered

### Alternative 1: Keep `modality` but remove only `runner`

- What: Continue allowing `BaseAgent(..., modality="image")` while removing direct runner objects.
- Why rejected: The user explicitly added that no modality parameter is needed once model/provider to runner mapping exists.

### Alternative 2: Keep custom runner injection for tests

- What: Remove runner examples from docs but keep `runner=` in `BaseAgent` for tests and advanced users.
- Why rejected: The user asked for no runner parameter on the agent class and no runner parameters in general.

### Alternative 3: Put the mapping in `vidbyte/lib/enums/model_modality.py`

- What: Extend the current `_MODEL_NAME_MODALITY_MAP` and keep using `ModalityDetector`.
- Why rejected: The requested structure is a separate constants dictionary under `vidbyte/lib/constants/` plus a `Runner` utility class.

### Alternative 4: Infer runner type from prompt content

- What: Use the user's prompt text to decide image/video/text execution.
- Why rejected: Prompt text is ambiguous and creates surprising behavior. Provider/model identity is stable and explicit.
