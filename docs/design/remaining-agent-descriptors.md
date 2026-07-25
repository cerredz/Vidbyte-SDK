# Design Doc: Remaining Agent Type Descriptors & Enhanced Validation

**Status:** Draft
**Author:** OpenCode
**Created:** 2026-07-24

---

## 1. Overview

Extend the composition-based YAML descriptor system (PR #315) to support the five remaining agent types — `multi`, `aggregate`, `adversarial`, `handoff`, `continual_trace` — and add missing validation checks to the existing `AgentDescriptor.__post_init__`. Each new agent type gets its own thin frozen dataclass that composes the SDK's existing runtime settings objects (`MultiAgentSettings`, `AdversarialSettings`, `AggregateConfig`, `ProposerSpec`, `TraceSchema`) without duplicating field definitions. The `YamlLoader` gains the ability to construct these descriptor types from YAML documents.

## 2. Goals & Non-Goals

### Goals
- Create `MultiAgentDescriptor`, `AggregateAgentDescriptor`, `AdversarialAgentDescriptor`, `HandoffAgentDescriptor`, `ContinualTraceAgentDescriptor` dataclasses.
- Wire the `YamlLoader._build_agent_from_raw` dispatch to construct the correct descriptor type based on `agent_type`.
- Add ~20 missing validation checks to `AgentDescriptor.__post_init__` (max capabilities count, agent_metadata field lengths, name kebab-case validation, model modality check, provider-specific temperature ceiling, output_schema depth limit, metadata serializability).
- Update `vidbyte/lib/enums/config.py` `__all__`, `vidbyte/lib/dataclasses/__init__.py`, and `vidbyte/__init__.py` exports.

### Non-Goals
- Changing the existing `AgentSettings`/`BaseAgentSettings` hierarchy in `vidbyte/lib/dataclasses/config.py`. Those remain as legacy.
- Modifying the `HarnessDescriptor` or `EnvironmentDescriptor`.
- Resolving tool/middleware refs. All descriptors produce data; resolution remains application-owned.
- New test files (per the no-tests workflow). Existing CI must stay green.

## 3. Background & Context

PR #315 introduced `AgentDescriptor`, `HarnessDescriptor`, and `EnvironmentDescriptor` with a composition-based architecture where descriptors compose existing runtime settings objects. Only `agent_type: base` was implemented. The five remaining types (`multi`, `aggregate`, `adversarial`, `handoff`, `continual_trace`) are registered via `AgentType` enum but raise `ConfigurationError("not yet loadable from YAML")`.

The existing runtime settings classes for these types are already on `main`:
- `MultiAgentSettings` — `vidbyte/lib/dataclasses/multi_agent.py`
- `AdversarialSettings` — `vidbyte/lib/dataclasses/adversarial.py`
- `AggregateConfig` + `ProposerSpec` — `vidbyte/lib/dataclasses/multi_agent.py`
- `TraceSchema` + `TraceOption` — `vidbyte/lib/dataclasses/trace.py`

The original design conversation enumerated ~153 validation checks. About 50 were implemented in PR #315. ~20 more remain.

## 4. Requirements

### Functional Requirements

1. `YamlLoader.load_agent(path)` for `agent_type: multi` returns a `MultiAgentDescriptor` containing an orchestrator `AgentDescriptor`, a tuple of worker `AgentDescriptor` objects, and a `MultiAgentSettings` object.
2. `YamlLoader.load_agent(path)` for `agent_type: aggregate` returns an `AggregateAgentDescriptor` containing `tuple[ProposerSpec, ...]`, an optional aggregator `ProposerSpec`, and an `AggregateConfig` object.
3. `YamlLoader.load_agent(path)` for `agent_type: adversarial` returns an `AdversarialAgentDescriptor` containing a worker `AgentDescriptor`, an adversary `AgentDescriptor`, and an `AdversarialSettings` object.
4. `YamlLoader.load_agent(path)` for `agent_type: handoff` returns a `HandoffAgentDescriptor` containing a handoff spec dict and source provider/model.
5. `YamlLoader.load_agent(path)` for `agent_type: continual_trace` returns a `ContinualTraceAgentDescriptor` containing a trace schema dict, max_trace_iterations, and source provider/model.
6. `AgentDescriptor.__post_init__` validates: name kebab-case pattern, capabilities max count (64), agent_metadata field length limits, metadata value serializability, model_name text-modality check, provider-specific temperature ceiling (anthropic max 1.0), and output_schema max nesting depth (10).
7. Each new descriptor validates its own fields in `__post_init__`, delegating to composed objects where applicable.
8. All descriptors provide `to_agent_kwargs()` returning a dict suitable for the corresponding agent constructor.

### Non-Functional Requirements
- **Security:** Same secret/interpolation rejection as `AgentDescriptor`.
- **Observability:** Errors carry `details` with `field` and `expected` values.
- **Compatibility:** Additive. No changes to existing `AgentDescriptor` API surface beyond new validation checks.
- **CI:** `python -m pytest tests/ -x` and `python -m compileall vidbyte` must pass.

## 5. High-Level Design

Each new descriptor follows the same pattern as `AgentDescriptor`: a frozen `@dataclass(slots=True)` that composes existing runtime settings types and validates itself in `__post_init__`. The `YamlLoader` dispatch in `_build_agent_from_raw` is extended to call the appropriate constructor for each `AgentType`.

For enhanced validation on the existing `AgentDescriptor`, new checks are added to existing `_validate_*` methods without changing the public API.

```
YAML file (agent_type: multi)
  │
  ▼
YamlLoader._build_agent_from_raw(raw, path)
  │
  │  agent_type == "multi" → _build_multi_agent(raw, path)
  │
  ▼
MultiAgentDescriptor(
    name=...,
    system_prompt=...,
    orchestrator=AgentDescriptor(...),     ← recursively built
    agents=(AgentDescriptor(...), ...),     ← recursively built
    settings=MultiAgentSettings(**raw),     ← EXISTING class
)
```

## 6. Detailed Design

### 6.1 `vidbyte/lib/dataclasses/multi_agent_descriptor.py`
**Type:** Created

Frozen dataclass composing `MultiAgentSettings` and nested `AgentDescriptor` objects.

```python
@dataclass(frozen=True, slots=True)
class MultiAgentDescriptor:
    name: str = ""
    system_prompt: str = ""
    description: str = ""
    orchestrator: AgentDescriptor | None = None
    agents: tuple[AgentDescriptor, ...] = ()
    settings: MultiAgentSettings = field(default_factory=MultiAgentSettings)
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates name, system_prompt, orchestrator presence, agent list uniqueness.
        ...

    def to_agent_kwargs(self, *, orchestrator_instance=None, worker_instances=()) -> dict[str, Any]:
        # Returns kwargs for MultiAgent.__init__.
        ...
```

Validation:
- `name` non-empty, max 256 chars
- `system_prompt` non-empty, max 500,000 chars
- `orchestrator` not None
- `agents` non-empty (at least 1 worker)
- `agents[].name` unique within the team and not equal to `name`
- `agents[].name` not equal to `orchestrator.name`
- Metadata sanitized for secrets/interpolation

### 6.2 `vidbyte/lib/dataclasses/aggregate_agent_descriptor.py`
**Type:** Created

```python
@dataclass(frozen=True, slots=True)
class AggregateAgentDescriptor:
    name: str = ""
    system_prompt: str = ""
    description: str = ""
    proposers: tuple[ProposerSpec, ...] = ()
    aggregator: ProposerSpec | None = None
    config: AggregateConfig = field(default_factory=AggregateConfig)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates proposers non-empty, labels unique, aggregator present, config bounds.
        ...
```

Validation:
- `proposers` non-empty (at least 1 proposer)
- `proposers[].label` unique across proposers and aggregator (if aggregator has label)
- `config.min_successful <= len(proposers)`
- `config.max_concurrency >= 1` if set
- `config.per_proposer_timeout > 0` if set

### 6.3 `vidbyte/lib/dataclasses/adversarial_agent_descriptor.py`
**Type:** Created

```python
@dataclass(frozen=True, slots=True)
class AdversarialAgentDescriptor:
    name: str = ""
    system_prompt: str = ""
    description: str = ""
    worker: AgentDescriptor | None = None
    adversary: AgentDescriptor | None = None
    settings: AdversarialSettings = field(default_factory=AdversarialSettings)
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates worker and adversary present, names differ, settings delegates to AdversarialSettings.
        ...
```

Validation:
- `worker` not None, with non-empty name and system_prompt
- `adversary` not None, with non-empty name and system_prompt
- `worker.name != adversary.name`
- `AdversarialSettings` self-validates

### 6.4 `vidbyte/lib/dataclasses/handoff_agent_descriptor.py`
**Type:** Created

```python
@dataclass(frozen=True, slots=True)
class HandoffAgentDescriptor:
    name: str = "handoff"
    handoff_title: str = "Handoff"
    handoff_instructions: str = ""
    sections: tuple[str, ...] = ()
    source_provider: str | None = None
    source_model_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates title non-empty, at least one section, provider/model if set.
        ...
```

Validation:
- `handoff_title` non-empty, max 200 chars
- `handoff_instructions` max 2000 chars
- `sections` non-empty (at least 1 section)
- Each section title non-empty, max 100 chars
- `source_provider` + `source_model_name` both set or both None
- Provider validated via `ModelProvider` enum

### 6.5 `vidbyte/lib/dataclasses/continual_trace_descriptor.py`
**Type:** Created

```python
@dataclass(frozen=True, slots=True)
class ContinualTraceAgentDescriptor:
    name: str = "continual-trace"
    schema: dict[str, Any] = field(default_factory=dict)
    max_trace_iterations: int = 3
    source_provider: str | None = None
    source_model_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates schema non-empty, max_trace_iterations in [1,3], provider/model.
        ...
```

Validation:
- `schema` non-empty dict
- `schema` max 50 top-level keys, max depth 5
- `max_trace_iterations` int in [1, 3]
- `source_provider` + `source_model_name` both set or both None
- Provider validated via `ModelProvider` enum

### 6.6 Enhanced `AgentDescriptor.__post_init__` validation
**Type:** Modified

Add to existing methods:

| Method | New checks |
|--------|-----------|
| `_validate_identity` | Name must match `^[a-z][a-z0-9-]*$` (kebab-case). If the name doesn't match, warn that the name should be kebab-case for tool exposure. |
| `_validate_provider_model` | Model must be text-modality (use existing `ModalityDetector.detect_modality`). Provider-specific temperature ceiling for `anthropic` (max 1.0). |
| `_validate_capabilities` | Max 64 capabilities (add `_MAX_CAPABILITIES` constant). |
| `_validate_output_schema` | Max nesting depth 10 (add recursive depth check). |
| `_validate_metadata` | Metadata values must be JSON-serializable (no callables, no cycles). |
| NEW `_validate_agent_metadata` | `agent_metadata.name` max 128 chars if set. `agent_metadata.description` max 1000 chars. `agent_metadata.use_cases` max 2000 chars. |
| `_validate_tool_specs` | Max 128 tool definitions. |

### 6.7 `vidbyte/lib/config/loader.py` dispatch extension
**Type:** Modified

Extend `_build_agent_from_raw` to call the appropriate builder for each `AgentType`:

```python
if agent_type == AgentType.BASE:
    return YamlLoader._construct_base_agent(raw, path)
if agent_type == AgentType.MULTI:
    return YamlLoader._build_multi_agent(raw, path)
if agent_type == AgentType.AGGREGATE:
    return YamlLoader._build_aggregate_agent(raw, path)
if agent_type == AgentType.ADVERSARIAL:
    return YamlLoader._build_adversarial_agent(raw, path)
if agent_type == AgentType.HANDOFF:
    return YamlLoader._build_handoff_agent(raw, path)
if agent_type == AgentType.CONTINUAL_TRACE:
    return YamlLoader._build_continual_trace_agent(raw, path)
```

## 7. Data Model Changes

N/A — no database or persisted schema. New in-memory frozen dataclasses only.

## 8. API Changes

N/A — no network API.

New Python imports:
```python
from vidbyte.lib.dataclasses.multi_agent_descriptor import MultiAgentDescriptor
from vidbyte.lib.dataclasses.aggregate_agent_descriptor import AggregateAgentDescriptor
from vidbyte.lib.dataclasses.adversarial_agent_descriptor import AdversarialAgentDescriptor
from vidbyte.lib.dataclasses.handoff_agent_descriptor import HandoffAgentDescriptor
from vidbyte.lib.dataclasses.continual_trace_descriptor import ContinualTraceAgentDescriptor
```

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/remaining-agent-descriptors.md` | This design doc |
| CREATE | `vidbyte/lib/dataclasses/multi_agent_descriptor.py` | MultiAgentDescriptor dataclass |
| CREATE | `vidbyte/lib/dataclasses/aggregate_agent_descriptor.py` | AggregateAgentDescriptor dataclass |
| CREATE | `vidbyte/lib/dataclasses/adversarial_agent_descriptor.py` | AdversarialAgentDescriptor dataclass |
| CREATE | `vidbyte/lib/dataclasses/handoff_agent_descriptor.py` | HandoffAgentDescriptor dataclass |
| CREATE | `vidbyte/lib/dataclasses/continual_trace_descriptor.py` | ContinualTraceAgentDescriptor dataclass |
| MODIFY | `vidbyte/lib/dataclasses/agent_descriptor.py` | Add ~15 new validation checks |
| MODIFY | `vidbyte/lib/config/loader.py` | Add builder methods for 5 new agent types |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export 5 new descriptors |
| MODIFY | `vidbyte/__init__.py` | Export 5 new descriptors |

**Estimated: 5 created, 5 modified, 0 deleted.**

## 10. Dependencies & External Services

| Dependency | Location | Purpose | Risk |
|------------|----------|---------|------|
| `MultiAgentSettings` | `vidbyte/lib/dataclasses/multi_agent.py` | Team budget validation | Low — existing |
| `AdversarialSettings` | `vidbyte/lib/dataclasses/adversarial.py` | Adversarial config validation | Low — existing |
| `AggregateConfig` | `vidbyte/lib/dataclasses/multi_agent.py` | Aggregate config | Low — existing |
| `ProposerSpec` | `vidbyte/lib/dataclasses/multi_agent.py` | Proposer model spec | Low — existing |
| `TraceSchema` | `vidbyte/lib/dataclasses/trace.py` | Trace schema validation | Low — existing |
| `ModalityDetector` | `vidbyte/lib/agents/modality_detector.py` | Model modality check | Low — existing |
| `ModelModality` | `vidbyte/lib/enums/model_modality.py` | Text-modality constant | Low — existing |

## 11. Rollout & Deployment

- **No feature flags.** Additive change with no schema migrations.
- **No breaking changes.** Existing `agent_type: base` loading unchanged.
- **CI:** `python -m compileall vidbyte && python -m pytest tests/ -x` must pass.

## 12. Open Questions

- [ ] **A. Handoff sections as tuple vs dict.** Should handoff sections be a `tuple[str, ...]` (ordered section titles) or a `dict[str, str]` (titles to empty content templates)? The `Handoff` base class uses a dict. **Recommendation: dict — maps closer to the runtime Handoff class.**
- [ ] **B. AggregateAgentDescriptor provider fields.** Should proposers carry their own provider/model (they do via `ProposerSpec`) or should the descriptor have top-level provider/model fallbacks? **Recommendation: proposers carry their own; no top-level fallback — matches AggregateAgent constructor.**
- [ ] **C. ContinualTraceAgentDescriptor schema format.** Should the schema be a raw dict (passed to `TraceSchema.coerce`) or a pre-validated `TraceSchema`? **Recommendation: raw dict — loader constructs TraceSchema internally if needed.**

## 13. Alternatives Considered

### Alternative 1: Put all agent types into one file
- What: Add all five new descriptor classes into `agent_descriptor.py`.
- Why rejected: That file is already 459 lines. Each descriptor type is substantial enough (~80-120 lines with validation) to warrant its own module. Follows the existing pattern of `adversarial.py`, `multi_agent.py`, etc.

### Alternative 2: Skip descriptor classes, load directly into agent constructors
- What: `YamlLoader.load_agent()` returns a constructed `MultiAgent` or `AdversarialAgent` instance.
- Why rejected: Breaks the parse-vs-resolve boundary. YAML is data; agent constructors require runtime objects (tools, middleware, tracer instances). User must control resolution.

---

END OF DESIGN DOC
