# Design Doc: YAML Configuration Descriptors

**Status:** Draft
**Author:** OpenCode
**Created:** 2026-07-24

---

## 1. Overview

Replace the in-progress PR #295/#308/#312 YAML config surface with a composition-based descriptor architecture. Instead of creating parallel dataclass models (`BaseAgentSettings`, `MultiAgentSettings`, etc.) that duplicate existing runtime types, the new `YamlLoader` parses YAML into thin `*Descriptor` dataclasses that compose the SDK's existing, canonical settings objects (`AgentLoopSettings`, `ToolSettings`, `AdversarialSettings`, `MultiAgentSettings`, `AggregateConfig`, `ProposerSpec`, etc.). The loader lives in `vidbyte/lib/config/loader.py` and performs I/O + dispatch only. All validation fires from the composed objects' existing `__post_init__`/`_validate()` methods.

## 2. Goals & Non-Goals

### Goals
- Parse YAML files for agents (base, multi, aggregate, adversarial, handoff, continual-trace), harnesses, and environments into typed descriptor objects.
- Compose existing runtime settings classes — never duplicate field definitions or validation.
- Place the loader and descriptors inside `vidbyte/lib/` so every SDK sub-package can import them without circular dependencies.
- Provide `to_agent_kwargs(tools=..., middleware=...)` on `AgentDescriptor` so the path from YAML to `BaseAgent(...)` is one explicit call.
- Reject secrets and environment-variable interpolation patterns at parse time.
- Validate provider/model_name against `ProviderModelRegistry`.
- Provide `YamlLoader.load_agent()`, `load_harness()`, `load_environment()` as typed, explicit entry points.

### Non-Goals
- Resolving `ref` strings into live tool or middleware objects. That remains application-owned.
- Importing arbitrary Python paths or executing code from YAML.
- Full per-type parsing of `multi`, `aggregate`, `adversarial`, `handoff`, and `continual_trace` agent types in this PR. These types are registered but raise `ConfigurationError("not yet loadable from YAML")`. Only `base` is fully implemented.
- Modifying the `vidbyte-harnesses` repo. Harness YAML support in the SDK produces a `HarnessDescriptor`; the separate `vidbyte-harnesses` repo's `Harness` ABC and CLI remain unchanged.
- New test files (per the no-tests workflow). Existing CI (`python scripts/run_ci.py`) must stay green.

## 3. Background & Context

### Current state on `main`
- `vidbyte/lib/config/` exists but contains only provider/model constants, MCP presets, and source config — no YAML loading.
- `vidbyte-evals/lib/yaml_loader.py` is a separate 57-line dotted-key loader for eval benchmark configs. Unrelated to agent/harness config.
- `vidbyte/__init__.py` and `vidbyte/client.py` expose no YAML loading surface.

### Existing runtime settings classes (single source of truth)
| Class | Location | Purpose |
|---|---|---|
| `AgentLoopSettings` | `vidbyte/agents/settings/loop.py` | Loop budgets, tool settings, output contracts |
| `ToolSettings` | `vidbyte/agents/settings/tool.py` | Tool deny-lists, call budgets, timeouts, truncation |
| `MultiAgentSettings` | `vidbyte/lib/dataclasses/multi_agent.py` | Team budgets and completion policy |
| `AdversarialSettings` | `vidbyte/lib/dataclasses/adversarial.py` | Reviewer count, rounds, timeouts, thresholds |
| `AggregateConfig` | `vidbyte/lib/dataclasses/multi_agent.py` | Synthesis config, concurrency, timeouts |
| `ProposerSpec` | `vidbyte/lib/dataclasses/multi_agent.py` | Provider + model per proposer/aggregator |
| `AgentMetadata` | `vidbyte/lib/dataclasses/agents.py` | Agent-as-tool name, description, use_cases |
| `AgentRuntimeConfig` | `vidbyte/lib/dataclasses/agents.py` | Internal runtime budget struct |
| `ToolSpec` | `vidbyte/lib/dataclasses/tools.py` | Tool name, description, parameters, permission |
| `TraceOption` | `vidbyte/lib/dataclasses/trace.py` | Trace mode, schema, interval |
| `ContextMinimalFanoutSettings` | `vidbyte/paradigms/context_minimal_fanout/types.py` | Pipeline stage config and budgets |

### PR #295/#308/#312 history (to be replaced)
PR #295 introduced `ConfigurationLoader` with separate agent/tools/middleware document kinds. PR #308 renamed to `YamlLoader` and added `kind` dispatch. PR #312 redesigned to two document families (agent/harness) with a polymorphic `type:` discriminator and parallel `*AgentSettings` dataclasses in `vidbyte/lib/dataclasses/config.py`. This document replaces all three branches with a composition-based approach: thin descriptors that delegate to the existing runtime classes above.

### Agent constructor surface
`BaseAgent.__init__` accepts 32 keyword arguments. The YAML-serializable subset is ~25 fields. Non-serializable fields include: `tools` (runtime objects), `middleware` (runtime objects), `tracer`/`trace` (runtime objects), `context_items` (runtime objects), `context_manager` (runtime objects), `permission_policy`, and `api_key` (secret).

## 4. Requirements

### Functional Requirements
1. `YamlLoader.load_agent(path)` reads a `.yaml`/`.yml` file and returns an `AgentDescriptor`.
2. The agent document root carries `type: agent` and `agent_type: base` (default `base`). Other `agent_type` values (`multi`, `aggregate`, `adversarial`, `handoff`, `continual_trace`) are recognized but raise a specific `ConfigurationError("not yet loadable from YAML")`.
3. `loop:` is parsed into the existing `AgentLoopSettings` class. `loop.tool_settings:` is parsed into the existing `ToolSettings` class.
4. `tools:` is a list of `{ref, options}` entries stored as `tuple[ToolSpec, ...]`. `middleware:` is a list of string refs.
5. `provider` is validated against `ProviderModelRegistry.validate_provider` (canonical `ModelProvider` set). `model_name` is validated non-empty via `ProviderModelRegistry.validate_model`.
6. `api_key`, `token`, `password`, `secret`, and their variants are rejected with a specific `ConfigurationError`. `${...}` environment interpolation patterns are rejected.
7. All field validation lives in the descriptor `__post_init__` and the composed objects' own validation. The loader performs I/O, document-type dispatch, and error enrichment only.
8. `AgentDescriptor.to_agent_kwargs(tools=..., middleware=...)` returns a `dict[str, Any]` suitable for `BaseAgent(...)`.
9. `YamlLoader.load_harness(path)` returns a `HarnessDescriptor`. `YamlLoader.load_environment(path)` returns an `EnvironmentDescriptor`.
10. The loader, descriptors, and enums live under `vidbyte/lib/` so all SDK packages can import them without circular dependencies.

### Non-Functional Requirements
- **Security:** No secret may enter parsed config or error diagnostics. Duplicate YAML keys rejected via SafeLoader variant. No YAML object tags.
- **Observability:** Every `ConfigurationError` carries `details` with `path`, `field`, and `expected` value.
- **Maintainability:** Loader is under 80 lines. Validation is colocated with the data object it guards. No function nests deeper than two levels.
- **Compatibility:** `vidbyte.config` namespace is new with no consumers. Breaking the document schema from PR #295/#308/#312 is acceptable.
- **CI:** `python scripts/run_ci.py` must pass in full.

## 5. High-Level Design

The architecture splits into three layers:

1. **Descriptors** (`vidbyte/lib/dataclasses/agent_descriptor.py`, `harness_descriptor.py`, `environment_descriptor.py`): Thin frozen dataclasses that compose existing runtime settings objects. Each descriptor validates its own fields in `__post_init__` and delegates to the composed objects' existing validation.

2. **Loader** (`vidbyte/lib/config/loader.py`): Reads YAML safely, detects document type from the `type` field, constructs the appropriate descriptor, and enriches any `ConfigurationError` with the file path.

3. **Enums** (`vidbyte/lib/enums/config.py`): `AgentType` (base, multi, aggregate, adversarial, handoff, continual_trace) and `DocumentType` (agent, harness, environment).

```
YAML file
  │
  ▼
YamlLoader.load_agent(path) / load_harness(path) / load_environment(path)
  │
  │  _read_yaml(path)  ← SafeLoader + duplicate-key guard
  │  _detect_document_type(raw)  ← reads `type` field
  │  _build_*_descriptor(raw)  ← constructs descriptor, delegates to existing classes
  │
  ▼
AgentDescriptor / HarnessDescriptor / EnvironmentDescriptor
  │  __post_init__ validates its own fields
  │  composed objects validate themselves (AgentLoopSettings, ToolSettings, etc.)
  │
  ▼
descriptor.to_agent_kwargs(tools=resolved, middleware=resolved)
  │
  ▼
BaseAgent(**kwargs)  ← loop, tool_settings, etc. are THE SAME objects
```

## 6. Detailed Design

### 6.1 `vidbyte/lib/enums/config.py`
**Type:** Modified (if exists from PR branch) or Created

Defines the discriminators.

```python
class DocumentType(str, Enum):
    AGENT = "agent"
    HARNESS = "harness"
    ENVIRONMENT = "environment"

class AgentType(str, Enum):
    BASE = "base"
    MULTI = "multi"
    AGGREGATE = "aggregate"
    ADVERSARIAL = "adversarial"
    HANDOFF = "handoff"
    CONTINUAL_TRACE = "continual_trace"
```

### 6.2 `vidbyte/lib/dataclasses/agent_descriptor.py`
**Type:** Created

Thin composition dataclass. All sub-fields use existing classes.

```python
@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    type: AgentType = AgentType.BASE
    name: str = ""
    system_prompt: str = ""
    description: str = ""
    provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    runtime: AgentRuntimeType = AgentRuntimeType.LINEAR
    loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)
    tools: tuple[ToolSpec, ...] = ()
    middleware_refs: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    agent_metadata: AgentMetadata = field(default_factory=AgentMetadata)
    algorithm: str | None = None
    output_schema: dict[str, Any] | None = None
    trace_option: TraceOption | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates required fields, text lengths, provider/model, ref uniqueness, secret detection, and runtime compatibility.
        ...

    def to_agent_kwargs(self, *, tools: Sequence[object] = (), middleware: Sequence[AgentMiddleware] = ()) -> dict[str, Any]:
        # Returns keyword arguments for BaseAgent.__init__ after the caller supplies resolved tools and middleware.
        ...
```

`__post_init__` validation checks (detailed list in conversation, ~73 checks for base agent alone):
- `name` non-empty, max 256 chars, kebab-case
- `system_prompt` non-empty, max 500,000 chars
- `provider` valid `ModelProvider` if set
- `provider` + `model_name` both set or both absent
- `temperature` in `[0.0, 2.0]` if set
- Tool refs non-empty, max 128 chars, no duplicates, valid identifier pattern
- Middleware refs non-empty, max 128 chars, no duplicates, valid identifier pattern
- No secret keys in metadata, tool options, or any mapping
- No `${...}` patterns in any string field
- Non-linear runtime + trace_option/middleware/algorithm/output_contracts incompatibility
- `AgentLoopSettings` validates itself internally
- `ToolSettings` validates itself internally

### 6.3 `vidbyte/lib/dataclasses/harness_descriptor.py`
**Type:** Created

```python
@dataclass(frozen=True, slots=True)
class HarnessDescriptor:
    name: str = ""
    description: str = ""
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent: AgentDescriptor | None = None

    def __post_init__(self) -> None:
        # Validates name, description, params schema (type, name, required, default).
        ...
```

### 6.4 `vidbyte/lib/dataclasses/environment_descriptor.py`
**Type:** Created

```python
@dataclass(frozen=True, slots=True)
class EnvironmentDescriptor:
    name: str = ""
    context: AgentDescriptor | None = None
    splitter: AgentDescriptor | None = None
    adversarial: AgentDescriptor | None = None
    implementation: AgentDescriptor | None = None
    settings: ContextMinimalFanoutSettings | None = None

    def __post_init__(self) -> None:
        # Validates at least one stage agent defined, settings budgets.
        ...
```

### 6.5 `vidbyte/lib/config/loader.py`
**Type:** Created

Thin I/O + dispatch class. Under 80 lines.

```python
class YamlLoader:
    def load_agent(self, path: str | Path) -> AgentDescriptor: ...
    def load_harness(self, path: str | Path) -> HarnessDescriptor: ...
    def load_environment(self, path: str | Path) -> EnvironmentDescriptor: ...

    @staticmethod
    def _read_yaml(path: str | Path) -> dict[str, Any]: ...
```

Logic:
1. Validate path exists, has `.yaml`/`.yml` extension, file under 10 MB.
2. Parse with `yaml.SafeLoader` subclass that rejects duplicate mapping keys.
3. Require mapping root, read `type` field.
4. Dispatch to descriptor construction based on `type`.
5. Enrich any `ConfigurationError` from descriptor `__post_init__` with `path`.

### 6.6 `pyproject.toml`
**Type:** Modified

Add `PyYAML>=6,<7` to `dependencies`.

### 6.7 `vidbyte/lib/dataclasses/__init__.py`
**Type:** Modified

Export `AgentDescriptor`, `HarnessDescriptor`, `EnvironmentDescriptor`.

### 6.8 `vidbyte/lib/enums/__init__.py`
**Type:** Modified

Export `AgentType`, `DocumentType`.

### 6.9 `vidbyte/lib/config/__init__.py`
**Type:** Modified

Export `YamlLoader` and the descriptor types.

### 6.10 `vidbyte/__init__.py` and `vidbyte/client.py`
**Type:** Modified

Export `YamlLoader`, `AgentDescriptor`, `AgentType` from the root package. Add `self.config = YamlLoader()` to `VidbyteSDK`.

## 7. Data Model Changes

N/A — no database or persisted schema. The new `*Descriptor` dataclasses are in-memory configuration objects that compose existing runtime types.

## 8. API Changes

N/A — no network API. The new Python API surface:

```python
from vidbyte import YamlLoader, AgentDescriptor, AgentType

loader = YamlLoader()
desc: AgentDescriptor = loader.load_agent("my_agent.yaml")
agent = sdk.agents.base(**desc.to_agent_kwargs(tools=resolved_tools, middleware=resolved_mw))

# Also available as:
desc = VidbyteSDK().config.load_agent("my_agent.yaml")
```

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/yaml-config-descriptors.md` | This design doc |
| CREATE | `vidbyte/lib/enums/config.py` | `AgentType` and `DocumentType` enums |
| CREATE | `vidbyte/lib/dataclasses/agent_descriptor.py` | `AgentDescriptor` — thin composition of existing settings types |
| CREATE | `vidbyte/lib/dataclasses/harness_descriptor.py` | `HarnessDescriptor` |
| CREATE | `vidbyte/lib/dataclasses/environment_descriptor.py` | `EnvironmentDescriptor` |
| CREATE | `vidbyte/lib/config/loader.py` | `YamlLoader` — thin I/O + dispatch |
| MODIFY | `pyproject.toml` | Add `PyYAML>=6,<7` dependency |
| MODIFY | `vidbyte/lib/config/__init__.py` | Export `YamlLoader` and descriptor types |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export `AgentDescriptor`, `HarnessDescriptor`, `EnvironmentDescriptor` |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export `AgentType`, `DocumentType` |
| MODIFY | `vidbyte/__init__.py` | Export `YamlLoader`, `AgentDescriptor`, `AgentType` |
| MODIFY | `vidbyte/client.py` | Add `self.config = YamlLoader()` |
| MODIFY | `llms.txt` | Document YAML config surface |
| DELETE | `vidbyte/lib/dataclasses/config.py` | If present from PR #312 worktree — parallel models replaced by composition |
| DELETE | `vidbyte/config/` package | If present from PR #312 worktree — loader moved into `vidbyte/lib/config/` |

**Estimated: 6 created, 7 modified, up to 2 deleted.**

## 10. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| `PyYAML` | `>=6,<7` | Safe YAML parsing | Low — already used in `vidbyte-evals` |
| `ProviderModelRegistry` | `vidbyte/lib/registries/models.py` | Provider/model validation | Low — existing |
| `AgentLoopSettings` | `vidbyte/agents/settings/loop.py` | Loop validation | Low — existing, self-validating |
| `ToolSettings` | `vidbyte/agents/settings/tool.py` | Tool constraint validation | Low — existing |
| `AdversarialSettings` | `vidbyte/lib/dataclasses/adversarial.py` | Adversarial config validation | Low — existing |
| `MultiAgentSettings` | `vidbyte/lib/dataclasses/multi_agent.py` | Team budget validation | Low — existing |
| `AggregateConfig` | `vidbyte/lib/dataclasses/multi_agent.py` | Aggregate config | Low — existing |
| `ProposerSpec` | `vidbyte/lib/dataclasses/multi_agent.py` | Proposer model spec | Low — existing |
| `ContextMinimalFanoutSettings` | `vidbyte/paradigms/context_minimal_fanout/types.py` | Environment pipeline settings | Low — existing |
| `TraceOption` | `vidbyte/lib/dataclasses/trace.py` | Trace config | Low — existing |
| `ToolSpec` | `vidbyte/lib/dataclasses/tools.py` | Tool declaration | Low — existing |

## 11. Rollout & Deployment

- **No feature flags.** The YAML config surface is brand new with no released consumers.
- **Breaking change** from the unreleased PR #295/#308/#312 schemas. Acceptable given no consumers.
- **Rollback:** Revert the merge commit. No data migration involved.
- **CI:** `python scripts/run_ci.py` must pass in full. PyYAML added to `pyproject.toml` dependencies.

## 12. Open Questions

- [ ] **A. Agent types beyond `base`.** This PR fully implements `base`. Should `multi`, `aggregate`, `adversarial`, `handoff`, `continual_trace` follow immediately after in follow-up PRs, or ship stubbed with a "not yet loadable" error? **Recommendation: stub them with a specific error; implement in follow-up PRs.**
- [ ] **B. Harness YAML integration with `vidbyte-harnesses`.** The `HarnessDescriptor` lives in the SDK. Should the `vidbyte-harnesses` CLI load harness configs through the SDK's `YamlLoader`, or keep its own loading? **Recommendation: SDK's loader for standard harness YAML shape; `vidbyte-harnesses` imports it.**
- [ ] **C. ToolSpec in YAML.** `ToolSpec` requires `name`, `description`, `parameters`, `permission`. For YAML-define d tools, should the loader construct full `ToolSpec` objects from `{ref, options}`, or a lighter `ToolRef( ref, options)`? **Recommendation: `ToolSpec` with `name=ref` and empty parameters, since tools in YAML are refs to be resolved later, not full tool definitions.**
- [ ] **D. Environment descriptor scope.** Should `EnvironmentDescriptor` use the existing `ContextMinimalFanoutSettings` directly, or expand to support other paradigm types? **Recommendation: use existing class directly; add new paradigm descriptors later as separate document types.**

## 13. Alternatives Considered

### Alternative 1: Parallel dataclass models (PR #312 approach)
- What: Create `BaseAgentSettings`, `MultiAgentSettings`, `AdversarialAgentSettings` as separate classes that duplicate the field definitions and validation of existing runtime classes.
- Why rejected: Duplicates ~150 field definitions across two class hierarchies. When `AgentLoopSettings` gains a field, the parallel model must be manually updated. Validation logic is forked. The `to_agent_kwargs()` bridge must translate between parallel types.

### Alternative 2: Pydantic models for all descriptors
- What: Use Pydantic v2 `BaseModel` for descriptors with built-in JSON Schema and validation.
- Why rejected: The existing settings classes (`AgentLoopSettings`, `ToolSettings`, `AdversarialSettings`, `MultiAgentSettings`) are plain Python classes with custom `__init__`/`_validate()`, not Pydantic. Rewriting them all is out of scope. Frozen dataclasses match the house style in `vidbyte/lib/dataclasses/`.

### Alternative 3: YAML loading directly into `BaseAgent.__init__`
- What: `YamlLoader.load_agent()` returns a constructed `BaseAgent` instance, resolving tools/middleware from a built-in registry.
- Why rejected: YAML is declarative data, not executable code. Resolving tool/middleware references requires knowledge the SDK should not own (project-specific imports). Keeping parse and resolve separate maintains a clear security boundary.

### Alternative 4: Module-level functions only (no `YamlLoader` class)
- What: Export `load_agent_config()`, `load_harness_config()`, `load_environment_config()` as standalone functions.
- Why rejected: A class provides one discoverable interface, allows sub-classing for custom document types, and keeps the shared `_read_yaml` helper properly scoped.

---

END OF DESIGN DOC
