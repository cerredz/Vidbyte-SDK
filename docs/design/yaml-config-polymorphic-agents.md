# Design Doc: Polymorphic Agent YAML Configuration (PR #308 review resolution)

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-24
**Last Updated:** 2026-07-24

---

## 1. Overview

This change reworks the public YAML configuration surface (`vidbyte.config`) in response to the eight review comments left on PR #308. It collapses the four document kinds (`agent`/`tools`/`middleware`/`harness`) down to **two** (`agent` and `harness`), makes the agent document **polymorphic** on an agent `type:` discriminator, moves *all* field validation into the settings dataclasses (which validate against the SDK's canonical enums and the `ProviderModelRegistry`), and shrinks the loader to a thin read-and-dispatch layer. Tools and middleware stop being standalone documents and become fields *inside* an agent.

---

## 2. Goals & Non-Goals

### Goals
- Remove the standalone `tools` and `middleware` documents; tools and middleware become fields on an agent (comment 1).
- Fold every module-level `_validate_*` helper into the dataclass it validates; condense the helper wall (comment 2).
- Make the agent document polymorphic: a `type:` field selects one of the real `BaseAgent` subclasses, each with its own settings dataclass; `loop` becomes the real `AgentLoopSettings` object, not a `Mapping[str, Any]` (comment 3).
- Introduce an `AgentType` enum and replace remaining hard-coded config strings with typed enums (comment 4).
- Keep function nesting to at most two levels in the loader (comment 5).
- Shrink `loader.py`: read the YAML, hand the body to a dataclass, surface the dataclass's specific field error; drop `kind` dispatch in favor of harness-vs-agent detection (comment 6).
- Validate `provider` and `model_name` against a canonical source of truth in `vidbyte/lib` (the existing `ProviderModelRegistry`), so invalid provider/model values fail at load (comment 7).

### Non-Goals
- **Full per-type parsing of composite/facade agents** (`multi`, `aggregate`, `adversarial`, `continual_trace`, `handoff`). These are registered behind the `type` discriminator but raise a specific "not yet loadable from YAML" error in this PR. See §5 and Open Questions. Only `base` is fully implemented.
- **Building a new per-provider *model allowlist* table.** No exhaustive `{provider: {valid_models}}` table exists in the repo today; `ProviderModelRegistry.validate_model` only checks non-empty. Building/maintaining that table is out of scope (Open Question B).
- Resolving `ref`s into runtime objects, importing code, interpolating environment values, or reading secrets. The parse-vs-resolve boundary from #295/#308 is preserved.
- Any change to the harness subsystem (`vidbyte.harnesses.*`). Harness documents keep their existing `schema_version` envelope and `HarnessConfigLoader`.
- New test files (per the no-tests workflow). Existing CI (`python scripts/run_ci.py`) must stay green.

---

## 3. Background & Context

PR #308 (branch `ai/resolve-pr-295-comments`, targeting `main`) reworked the #295 YAML loader. The reviewer (`cerredz`) left eight inline comments asking for a deeper redesign than #308 delivered:

- The loader is too large and dispatches on a `kind` field the reviewer wants gone.
- `AgentSettings` is incomplete (it models only a fraction of the `BaseAgent` constructor), uses a `Mapping` for `loop` instead of the real `AgentLoopSettings`, and cannot express the SDK's other agent types.
- Provider/model strings are accepted without validation.
- Validation logic lives in module-level helpers instead of on the dataclasses.
- Tools/middleware should live inside an agent, not as separate documents.

The SDK already provides the canonical sources of truth this redesign needs: `ModelProvider` (enum), `AgentRuntimeType` (enum), `AgentLoopSettings` (self-validating dataclass), and `ProviderModelRegistry` (provider validation). The concrete agent types are the `BaseAgent` subclasses: `AggregateAgent`, `ContinualTraceAgent`, `HandoffAgent`, `MultiAgent`, and (on the in-flight `feat/adversarial-agent*` branches, **not yet on `main`**) `AdversarialAgent`.

---

## 4. Requirements

### Functional Requirements
1. `YamlLoader.load(path)` reads one YAML document and returns either an `AgentSettings` subclass instance (agent document) or a `HarnessSpec` (harness document), with no `kind` field required.
2. The agent document root carries a `type:` field whose value is a member of a new `AgentType` enum; `type` defaults to `base` when omitted.
3. `type: base` fully parses into `BaseAgentSettings`, covering the YAML-serializable subset of the `BaseAgent` constructor (see §6.2 field table).
4. All other `AgentType` members are registered but raise a specific `ConfigurationError` ("agent type '<type>' is not yet loadable from YAML") when requested. No silent failure, no partial parse.
5. `loop:` is parsed into a real `AgentLoopSettings` instance; an invalid loop key or value surfaces as a specific field error, not a raw `TypeError`.
6. `tools:` is a list of `{ref, options}` entries parsed into `ToolSpec` objects on the agent; `middleware:` is a list of string refs. Neither exists as a standalone document any more.
7. `provider` is validated against `ProviderModelRegistry.validate_provider` (canonical `ModelProvider` set); `model_name` is validated non-empty via `ProviderModelRegistry.validate_model`.
8. Credentials (`api_key`, `token`, `password`, `secret`, and `*_api_key`/`*_token`/… suffixes) anywhere in the document are rejected with a specific error; `${...}` environment interpolation is rejected.
9. Every `ConfigurationError` raised during load carries `details` naming the offending file (`path`), the dotted `field`, and the expected value/type where applicable.
10. All field validation lives in the dataclasses (`__post_init__` / `from_mapping`); the loader performs I/O, harness-vs-agent detection, and error enrichment only.
11. `load_agent(path)` and `load_harness(path)` remain as explicit typed entry points; `view_agent()` returns the agent document structure. `load_tools`/`load_middleware`/`view_tools`/`view_middleware` are removed.

### Non-Functional Requirements
- **Security:** No secret may enter parsed config, resolved config, or error diagnostics (preserved from #308). Duplicate YAML keys are rejected (no last-key-wins). YAML parsing stays on a SafeLoader variant.
- **Observability:** Errors are specific and structured (`details` dict) so a developer can locate the exact offending field.
- **Maintainability:** Loader shrinks materially (target < ~90 lines from 208); no function nests deeper than two levels; validation is colocated with the data contract it guards.
- **Compatibility:** `vidbyte.config` is brand-new in #295/#308 with no released consumers, so breaking the document schema is acceptable and no back-compat aliases are kept. (Confirm in Open Questions.)
- **CI:** `python scripts/run_ci.py` must pass in full, including `--stage source` and `--stage package`.

---

## 5. High-Level Design

The redesign splits cleanly along the parse/validate boundary the reviewer asked for: **the loader parses and dispatches; the dataclasses validate.**

**Loader (`vidbyte/config/loader.py`)** becomes a thin class. `load(path)` reads the file into a mapping, then decides between the two document families. A harness document is recognized by its own envelope (`schema_version`/`harness` keys) and delegated unchanged to `HarnessConfigLoader`. Anything else is an agent document, handed to `AgentSettings.from_mapping`, which dispatches on `type:` to the correct subclass. If the agent parse fails, the dataclass's specific field error is surfaced (enriched with the file path). This satisfies comment 6's "don't check kind; load harness or agent" while keeping the precise error attribution comments 1/7 demanded.

**Dataclasses (`vidbyte/lib/dataclasses/config.py`)** become a small polymorphic hierarchy. `AgentSettings` is the base holding fields common to every agent; `from_mapping` reads `type`, looks the concrete class up in an `_AGENT_TYPES` registry, and delegates. `BaseAgentSettings` is fully implemented; the composite/facade types are registered but raise a specific "not yet loadable" error. `loop` is splatted into `AgentLoopSettings`, inheriting its validation. `provider`/`model_name` validate against `ProviderModelRegistry`. `tools` parse into `ToolSpec`. All the shape/secret/serializability validation from #308 moves onto these classes as private methods.

**Enums (`vidbyte/lib/enums/config.py`)** replace `ConfigKind` and `AgentLoopField` with a single `AgentType` enum. `AgentLoopField` is deleted because `AgentLoopSettings` now owns loop-field validation; `ConfigKind` is deleted because there is no longer a `kind` field.

```
YamlLoader.load(path)
   |
   |-- read YAML (SafeLoader + duplicate-key guard)
   |
   |-- harness envelope? (schema_version / harness present)
   |        |-- yes --> HarnessConfigLoader().load(path) --> HarnessSpec
   |        |-- no  --> AgentSettings.from_mapping(doc)
   |                        |-- read `type` --> _AGENT_TYPES[type]
   |                        |-- base        --> BaseAgentSettings (full parse + validate)
   |                        |-- multi/aggregate/adversarial/continual_trace/handoff
   |                        |                 --> ConfigurationError("not yet loadable")
   |                        |-- validate: provider/model (registry), loop (AgentLoopSettings),
   |                        |             tools (ToolSpec), secrets/interpolation rejection
   |                        v
   |                   AgentSettings subclass instance
```

### Bounded scope rationale (decision A-ii)
Fully modeling `MultiAgent` (orchestrator + ledger + per-agent bindings), `AggregateAgent` (proposer/aggregator specs), and `AdversarialAgent` (worker/adversary + `AdversarialSettings`, whose schema is **still diverging across two unmerged branches**) is a large surface that would couple this PR to three in-flight branches. Instead we ship the *architecture* that makes "load any agent type" possible — the `type` discriminator and the `_AGENT_TYPES` registry — fully implement `base` as the reference, and register the rest behind a clear error. Adding each type later is a purely additive change (a new subclass + a registry entry).

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/enums/config.py`
**File:** `vidbyte/lib/enums/config.py`
**Type:** Modified (replace contents)

#### What it does
Defines the single fixed vocabulary the config surface still needs: the agent `type` discriminator.

#### Interface / API
```python
class AgentType(str, Enum):
    BASE = "base"
    AGGREGATE = "aggregate"
    CONTINUAL_TRACE = "continual_trace"
    HANDOFF = "handoff"
    MULTI = "multi"
    ADVERSARIAL = "adversarial"

    @classmethod
    def values(cls) -> tuple[str, ...]: ...  # for error messages
```

#### Logic / Algorithm
1. Declare `AgentType` mirroring the concrete `BaseAgent` subclasses.
2. Provide `values()` for building "must be one of …" error messages.

#### Edge Cases & Error Handling
- Unknown `type` string → `AgentType(value)` raises `ValueError`, caught in `from_mapping` and reraised as a specific `ConfigurationError` listing `values()`.

---

### 6.2 `vidbyte/lib/dataclasses/config.py`
**File:** `vidbyte/lib/dataclasses/config.py`
**Type:** Modified (rewrite)

#### What it does
Holds the polymorphic agent settings hierarchy plus the nested `ToolSpec`, and owns all field validation.

#### Interface / API
```python
@dataclass(slots=True)
class ToolSpec:
    ref: str
    options: dict[str, Any] = field(default_factory=dict)
    @classmethod
    def from_mapping(cls, data: object, field_name: str) -> "ToolSpec": ...

@dataclass(slots=True)
class AgentSettings:
    type: AgentType
    name: str
    system_prompt: str
    provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    runtime: AgentRuntimeType = AgentRuntimeType.LINEAR
    loop: "AgentLoopSettings" = field(default_factory=_default_loop)
    algorithm: str | None = None
    tools: tuple[ToolSpec, ...] = ()
    middleware_refs: tuple[str, ...] = ()
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: object, field_name: str = "agent") -> "AgentSettings": ...
    def to_agent_kwargs(self, *, tools=(), middleware=()) -> dict[str, Any]: ...
    @staticmethod
    def expected_structure() -> dict[str, Any]: ...

@dataclass(slots=True)
class BaseAgentSettings(AgentSettings): ...          # fully implemented

@dataclass(slots=True)
class AggregateAgentSettings(AgentSettings): ...     # registered, raises "not yet loadable"
@dataclass(slots=True)
class ContinualTraceAgentSettings(AgentSettings): ...# registered, raises "not yet loadable"
@dataclass(slots=True)
class HandoffAgentSettings(AgentSettings): ...       # registered, raises "not yet loadable"
@dataclass(slots=True)
class MultiAgentSettings(AgentSettings): ...         # registered, raises "not yet loadable"
@dataclass(slots=True)
class AdversarialAgentSettings(AgentSettings): ...   # registered, raises "not yet loadable"

_AGENT_TYPES: dict[AgentType, type[AgentSettings]]
```

#### BaseAgent field disposition (what maps into `BaseAgentSettings`)
| Bucket | BaseAgent kwargs | YAML treatment |
|---|---|---|
| Scalar / native | `name`, `system_prompt`, `model_name`, `temperature`, `run_id`(→ omit), `description` | direct fields |
| Enum | `runtime`→`AgentRuntimeType`, `provider`→`ModelProvider` (validated) | validated via enum/registry |
| String (non-enum) | `algorithm` | kept as validated `str` (no enum exists) |
| Nested dataclass | `agent_loop_settings`→`AgentLoopSettings` | sub-mapping splatted into the dataclass |
| Ref | `tools`→`ToolSpec[]`, `middleware`→`str[]` | parsed refs, resolved later by the app |
| List / dict | `capabilities`, `metadata` | validated serializable |
| Rejected / deferred | `api_key` (secret → reject), `permission_policy`, `context_items`, `context_manager`, `tracer`/`trace`, `output_schema`, `handoff`, `trace_option`, `agent_metadata`, `max_tool_rounds`/`max_iterations`/`max_tokens`/`compaction_*` (belong under `loop`) | not accepted at top level in v1 |

#### Logic / Algorithm (`AgentSettings.from_mapping`)
1. Copy the body into a string-keyed mapping (reject non-mappings with a field error).
2. Read `type` (default `base`); resolve to `AgentType` or raise a specific error listing valid values.
3. Look the concrete class up in `_AGENT_TYPES`; if it is a composite/facade type, raise the "not yet loadable" `ConfigurationError`.
4. Reject unknown top-level fields against the class's allowed set.
5. Enforce required fields (`name`, `system_prompt`).
6. Build the instance; `__post_init__` normalizes and validates each field (text, provider/model via registry, loop via `AgentLoopSettings`, tools via `ToolSpec`, refs unique, metadata serializable + secret-free + no `${}` interpolation).

#### Edge Cases & Error Handling
- Unknown `type` → error naming valid `AgentType.values()`.
- Composite type requested → error naming the type and that YAML loading is not yet supported.
- Invalid provider → `ProviderModelRegistry.validate_provider` error, re-wrapped with `field="provider"`.
- Empty model → `validate_model` error, re-wrapped with `field="model_name"`.
- Bad loop key/value → caught `TypeError`/`ConfigurationError` from `AgentLoopSettings`, re-raised with `field="loop"`.
- Secret key or `${}` anywhere → specific rejection (logic carried over from #308).
- Duplicate tool/middleware refs → specific error.

---

### 6.3 `vidbyte/config/loader.py`
**File:** `vidbyte/config/loader.py`
**Type:** Modified (rewrite, shrink)

#### What it does
Reads one YAML file safely and returns an `AgentSettings` or a `HarnessSpec`. No `kind` dispatch, no per-kind loaders.

#### Interface / API
```python
class YamlLoader:
    def load(self, path: str | Path) -> AgentSettings | HarnessSpec: ...
    def load_agent(self, path: str | Path) -> AgentSettings: ...
    def load_harness(self, path: str | Path) -> HarnessSpec: ...
    def view_agent(self) -> dict[str, Any]: ...
```

#### Logic / Algorithm
1. `_read(path)`: validate extension, read text, parse with the duplicate-key SafeLoader, require a string-keyed mapping root.
2. `load(path)`: if the mapping carries the harness envelope (`schema_version` or `harness`), delegate to `load_harness`; otherwise `AgentSettings.from_mapping(doc)` (enriched with `path` on error).
3. `load_agent`/`load_harness`: explicit typed entries reusing the same primitives.
4. `view_agent`: return `AgentSettings.expected_structure()`.

Two-level nesting max: helpers are flat methods on the class; no triple-nested inner functions (the #308 `_DuplicateKeySafeLoader.construct_mapping` loop stays, which is a method, not nested functions).

#### Edge Cases & Error Handling
- Non-`.yaml`/`.yml` extension → specific error.
- Unreadable/malformed YAML → specific error with `path`.
- Non-mapping root → specific error.
- Errors from the dataclass or harness loader are enriched with `path` and re-raised unchanged in type.

---

### 6.4 `vidbyte/config/types.py`, `__init__.py`, `README.md`
**Type:** Modified

- `types.py`: re-export `AgentSettings`, the concrete `*AgentSettings` subclasses, and `ToolSpec` from `vidbyte.lib.dataclasses.config`; drop `ToolDefinition`/`MiddlewareDefinition`.
- `__init__.py`: update `__all__` to the new names.
- `README.md`: rewrite the "two documents, tools live inside agents, validation lives on the dataclasses" description; update the changelog list; remove the `load_tools`/`load_middleware`/`view_tools`/`view_middleware` mentions.

---

### 6.5 `vidbyte/lib/dataclasses/__init__.py` and `vidbyte/lib/enums/__init__.py`
**Type:** Modified

- dataclasses `__init__`: export `AgentSettings`, the subclasses, `ToolSpec`; drop `ToolDefinition`/`MiddlewareDefinition`.
- enums `__init__`: export `AgentType`; drop `ConfigKind`/`AgentLoopField`.

---

### 6.6 `vidbyte/__init__.py`, `vidbyte/client.py`
**Type:** Modified

- Update any top-level exports that named the removed types (`ToolDefinition`, `MiddlewareDefinition`) or removed loader methods.
- `client.py` `VidbyteSDK().config` wiring: ensure it exposes the trimmed `YamlLoader` API and nothing referencing the removed methods.

---

### 6.7 `README.md`, `llms.txt`
**Type:** Modified

- Update the config examples to the new single agent-document shape (with `type:`, nested `tools`, `middleware` refs) and remove the tools/middleware-document examples.

---

### 6.8 `docs/design/yaml-configuration-loader.md`
**Type:** Modified

- Add a dated revision note at the top pointing to this document as the superseding design for the polymorphic redesign.

---

## 7. Data Model Changes

N/A — no database or persisted schema. The "data model" here is the in-memory dataclass hierarchy, fully described in §6.2.

---

## 8. API Changes

N/A — no network API. The public Python API changes are the `YamlLoader` surface (§6.3) and the exported dataclasses (§6.4/6.5), covered above.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/yaml-config-polymorphic-agents.md` | This design doc |
| MODIFY | `vidbyte/lib/enums/config.py` | Replace `ConfigKind`/`AgentLoopField` with `AgentType` (comments 3,4,6) |
| MODIFY | `vidbyte/lib/dataclasses/config.py` | Polymorphic `AgentSettings` hierarchy + `ToolSpec`; validation on the dataclasses; provider/model via registry; loop as `AgentLoopSettings` (comments 1,2,3,7) |
| MODIFY | `vidbyte/config/loader.py` | Shrink; drop `kind` dispatch; harness-vs-agent detection; remove tools/middleware loaders (comments 1,5,6) |
| MODIFY | `vidbyte/config/types.py` | Re-export new names; drop `ToolDefinition`/`MiddlewareDefinition` |
| MODIFY | `vidbyte/config/__init__.py` | Update `__all__` |
| MODIFY | `vidbyte/config/README.md` | Document two-document model + changelog |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export new dataclasses; drop old ones |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export `AgentType`; drop `ConfigKind`/`AgentLoopField` |
| MODIFY | `vidbyte/__init__.py` | Update top-level exports |
| MODIFY | `vidbyte/client.py` | Update `VidbyteSDK().config` wiring |
| MODIFY | `README.md` | Update config examples |
| MODIFY | `llms.txt` | Update config examples |
| MODIFY | `docs/design/yaml-configuration-loader.md` | Add revision note pointing here |

Estimated: **1 created, 13 modified, 0 deleted** (the tool/middleware surface is removed *within* existing files, not by deleting files).

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `PyYAML` | existing | Safe YAML parsing | none (already used) |
| `ProviderModelRegistry` | `vidbyte/lib/registries/models.py` | Canonical provider validation (comment 7) | Low — provider set validated; model only non-empty (see Open Q B) |
| `AgentLoopSettings` | `vidbyte/agents/settings/loop.py` | Loop validation (comment 3) | Low — self-validating; import done lazily to avoid `agents`↔`lib` cycle |
| `AgentRuntimeType`, `ModelProvider` | `vidbyte/lib/enums` | Enum validation (comment 4) | none |
| `HarnessConfigLoader`/`HarnessSpec` | `vidbyte/harnesses` | Harness documents | none (unchanged) |
| `AdversarialSettings`/`MultiAgentSettings`/etc. | in-flight branches | Would be needed to *fully* parse facade types | Deferred — facade types stubbed (decision A-ii) |

---

## 11. Rollout & Deployment

- **No feature flags.** `vidbyte.config` is new in #295/#308 with no released consumers.
- **Breaking change** to the (unreleased) YAML schema: `version`/`kind` envelope removed; tools/middleware documents removed; agent document gains `type`. Acceptable given no consumers.
- **Deployment target (Open Question D):** recommended path is to push these commits onto the **existing PR #308 branch** `ai/resolve-pr-295-comments` so the review threads resolve in place, rather than opening a new PR off `main`. This deviates from the skill's default "new `feat/` branch"; calling it out for approval.
- **Rollback:** revert the commits; no data migration involved.

---

## 12. Open Questions

- [ ] **A. Facade-type scope.** Confirm A-ii: fully implement `base`, register `multi`/`aggregate`/`adversarial`/`continual_trace`/`handoff` behind a specific "not yet loadable" error. Alternative: implement the thin wrappers (`continual_trace`, `handoff`) now too, since they mostly add scalar fields. Recommendation: **A-ii** (bounds the PR, keeps `adversarial` out until its settings schema converges on `main`).
- [ ] **B. Model validation strength.** No per-provider model allowlist exists. Confirm B-iii: validate `provider` against the registry (real) and `model_name` non-empty (existing). Alternative B-ii: build and maintain a `{provider: {models}}` table in `vidbyte/lib/registries/models.py` — stronger, but a new fast-moving file to own. Recommendation: **B-iii now, B-ii as a follow-up PR.**
- [ ] **C. Harness-vs-agent detection.** Comment 6 asks for pure try-harness-then-agent. This doc uses cheap envelope detection (`schema_version`/`harness` present → harness) to preserve specific error attribution (comments 1/7). Confirm this reading, or require literal try/except. Recommendation: **envelope detection** (better errors).
- [ ] **D. Branch/PR target.** Push onto `ai/resolve-pr-295-comments` (updates PR #308 in place) vs. a new `feat/` branch off `main`. Recommendation: **update PR #308 in place.**
- [ ] **E. `version` field.** Drop the top-level `version` entirely, or keep an optional ignored `version` for forward-compat? Recommendation: **drop it** (comment 6's "less lines").

---

## 13. Alternatives Considered

### Alternative 1: Keep the flat single `AgentSettings` and just add fields
- What: Extend the existing `AgentSettings` with the missing `BaseAgent` kwargs, no `type` discriminator.
- Why rejected: Comment 3 explicitly requires loading *any* agent type, each with a different structure, keyed by a `type` field. A flat class cannot express `MultiAgent`/`AggregateAgent`/`AdversarialAgent`.

### Alternative 2: Fully implement all agent types now
- What: Write real settings dataclasses + recursive parsing for every `BaseAgent` subclass.
- Why rejected: Large surface; `MultiAgent` pulls in orchestrator/ledger config, and `AdversarialAgent`'s `AdversarialSettings` is still diverging across two unmerged branches (`feat/adversarial-agent` has 6 fields; `feat/adversarial-agent-settings` adds 4 and makes it frozen). Coupling this PR to three in-flight branches is unnecessary risk. The registry seam makes later addition additive.

### Alternative 3: Pydantic models instead of dataclasses
- What: Use pydantic for validation.
- Why rejected: Repo house style is plain dataclasses with `__post_init__` validation (`AgentLoopSettings`, `HarnessConfigLoader`, everything in `vidbyte.lib.dataclasses`). Matches #308's own judgment call.

### Alternative 4: Build a per-provider model allowlist now (comment 7, strong reading)
- What: New `{provider: {models}}` table validated against.
- Why rejected for this PR: No such table exists; it is a fast-moving artifact (every model release edits it) and a maintenance surface of its own. Deferred to a follow-up (Open Q B). Provider validation is real today; model non-empty is the existing contract.

---

END OF DESIGN DOC
