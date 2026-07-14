# Design Doc: Harness Execution Contract

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-12
**Last Updated:** 2026-07-13

---

## 0. Post-Review Revision (2026-07-13)

Two review passes on PR #267 revised this design after the first implementation
landed. Where the sections below conflict with this revision, **this revision is
authoritative**; the original sections are retained for rationale/history.

**Config is the single source of truth (schema change).**
- The top-level envelope is now `schema_version`, `harness`, `agents`, and the
  optional `metadata` and `orchestration`. The flat top-level `params` bucket is
  removed: per-agent hyperparameters move onto each `agents[]` entry as `params`
  and `tools`; between-agent knobs move to a dedicated `orchestration:` object.
- `harness.version` leaves the YAML entirely. Version identifies implementation
  *code*, so it is a class attribute on the `Harness` subclass. `harness.type`
  (the implementation *kind*) stays in config.
- Per-agent validation is now strict (unique `name`, optional `provider`/`model`,
  `system_prompt` string-or-`{$file}`, open `params`, `tools` list).
- `spec_id = sha256(canonical({type, version, agents, orchestration}))`. The
  code-supplied `version` is folded in (so a code change is a new variant), and
  descriptive `metadata` is excluded (so renaming never forks identity).

**A concrete `Harness` base class owns `load()`/`execute()`.**
- This reverses the original "no base class" goal by *synthesis*: the low-level
  structural `HarnessImplementation` protocol is kept (now `run(request)`), and a
  concrete `Harness` base class implements it and adds load/version/session
  ergonomics. Foreign objects with `run(request)` still work via
  `wrap_implementation(...)` / `HarnessClient.load(implementation=...)`.

**Persistence pivots onto durable Sessions; the bespoke capture system is deleted.**
- Deleted (~1,500 lines): `HarnessContext`, `HarnessPersistenceCoordinator`,
  `store.py` + `stores/*` (`HarnessStore`/`BaseHarnessStore`/in-memory/file),
  `HarnessEvent`/`HarnessArtifactRef` and the capture/persistence enums, the
  record codecs in `serialization.py`, and their re-exports.
- Added: `Harness.session(agent)` auto-instrument seam (forces `PER_STEP` +
  `FULL` trace + `run_id` tag), collection wired into `execute()`'s fail-open
  `finally`, `TrajectoryRecord` + `TrajectoryCollector` + a `TrajectorySink` port
  (in-memory + atomic-JSONL file sinks), an opt-in `collect` consent gate, and a
  mandatory redaction pass (`HarnessRedactor`) over `task`/`output`/`history`.
- The operational `SessionStore` (durable checkpoints + full traces) and the
  licensed, redacted `TrajectorySink` are kept as deliberately distinct surfaces
  so the consent/redaction boundary stays sharp.

The current source of truth for behavior is `vidbyte/harnesses/README.md`.

---

## 1. Overview

This feature turns the currently minimal `vidbyte.harnesses` namespace into a reusable outer execution envelope for arbitrary harness implementations. It formalizes configuration loading, computes a deterministic `spec_id` from the exact resolved behavior configuration, gives every execution a unique `run_id`, captures a typed run/event/artifact record, writes that record to an interchangeable store, and exports stored runs as dataset-ready JSONL. The abstraction deliberately does not prescribe an agent loop, topology, retry strategy, or reasoning algorithm: concrete paradigms and third-party harnesses remain free to implement any execution strategy behind one small `execute(request, context)` protocol.

---

## 2. Goals & Non-Goals

### Goals

- Replace per-harness configuration boilerplate with one SDK-owned `sdk.harnesses.load(...)` path.
- Accept typed mappings, JSON files, YAML files, and already-loaded mappings through the same loader.
- Resolve content references before identity is computed so editing a referenced system prompt changes the harness specification.
- Distinguish a reusable implementation, an exact configured specification, and one execution:
  - implementation identity: `harness.type` plus `harness.version`;
  - deterministic configuration identity: `spec_id`;
  - unique execution identity: `run_id`.
- Preserve an open implementation space through a structural `HarnessImplementation` protocol rather than a required base class.
- Support both direct implementation injection and optional type/version factory registration for config-only loading.
- Make every `LoadedHarness.execute(...)` invocation create a canonical `HarnessRun` record, including failed, timed-out, and cancelled executions.
- Automatically persist runs to a default in-memory store or a caller-provided durable store.
- Provide a public asynchronous `HarnessStore` port so external database/memory providers can accept the same run records without being coupled to harness algorithms.
- Ship in-memory and atomic filesystem stores as zero-dependency reference implementations.
- Provide implementation-facing event, artifact-reference, and durable-session-link capture through `HarnessContext`.
- Capture and expose persistence failures without silently replacing the harness result in best-effort mode.
- Let callers select best-effort or required persistence semantics.
- Materialize stored specifications, runs, and ordered events into standalone JSONL suitable for later dataset transformation.
- Preserve `sdk.harnesses.sessions` and all existing durable-session behavior.
- Document the important boundary that arbitrary out-of-band model, tool, filesystem, and network calls cannot be captured automatically.

### Non-Goals

- Defining the internal reasoning loop, planning style, agent topology, stopping criteria, or algorithm used by a harness.
- Replacing `vidbyte.paradigms`; concrete orchestration algorithms remain in that package and may later be adapted to this envelope.
- Adding retries, idempotency keys, side-effect fencing, human approval gates, checkpoint/resume semantics, or deterministic replay in this first contract.
- Reusing `SessionStore` or treating a harness run as a Session checkpoint. Sessions answer how a thread resumes; harness runs answer what happened under an exact specification.
- Automatically intercepting arbitrary direct calls to third-party model SDKs, tools, filesystems, browsers, or networks.
- Making trace-provider data such as LangSmith the canonical dataset store.
- Persisting artifact bytes or large blobs. This version records typed artifact references; blob storage remains a separate provider concern.
- Shipping SQLite, PostgreSQL, MongoDB, or Supabase harness-run adapters in the first change. The public `HarnessStore` protocol is the integration boundary for those follow-up adapters.
- Producing specialized SFT, preference, RL, or eval schemas. JSONL export is a loss-minimized raw trajectory view from which those formats can be derived.
- Modifying existing agent, trace, eval, Session, or paradigm execution semantics.
- Adding new automated test files or verification scripts under this no-tests workflow. Existing checks and inline smoke commands will still be run.

---

## 3. Background & Context

`vidbyte.harnesses` currently contains only `HarnessClient`, a README, and the package export. On current `origin/main`, `HarnessClient` also exposes `SessionClient` as `sdk.harnesses.sessions`. The namespace README explicitly reserves this boundary for future harness launch, configuration, and discovery behavior while keeping agents, tools, providers, and evals independent.

The nearest internal precedent is durable Session. `Session` wraps a pure `BaseAgent`, owns persistence outside the agent, serializes a stable `RunState`, and writes through a pluggable `SessionStore`. `SessionSerializer` centralizes schema versions and credential-key scrubbing, while in-memory, file, and generic database adapters share one contract. The proposed harness layer applies that composition principle one level higher: arbitrary harness code remains pure/open, while `LoadedHarness` owns config identity and the execution-record lifecycle.

The Session schema must not be reused directly. Session checkpoints are state snapshots in an append-only resume DAG. Harness events are potentially high-volume observations attached to a unique execution. Their identity, query, finalization, and dataset-export requirements are different even though the wrapper/serializer/store architecture is similar.

The SDK also has two adjacent but separate concepts:

- `vidbyte.trace` emits optional, provider-oriented observability spans. Session's `TraceRecorder` is fail-open and bounds raw event capture to the last 200 events, so it is not a complete canonical trajectory store.
- `vidbyte.evals` loads cases, invokes targets, grades outputs, and persists aggregate eval results. It does not currently own raw multi-step harness trajectories. A later change can link eval outcomes to `HarnessRun.run_id` without making eval data the run source of truth.

`vidbyte.paradigms.ParadigmHarness` already defines an opinionated algorithm-level `run`/`arun` surface. This proposal does not replace it with another algorithm base class. A paradigm can later be wrapped by or adapted to `LoadedHarness`; the new harness package owns the cross-cutting envelope only.

Repository constraints discovered during the audit:

- Python 3.11+ with `setuptools`; runtime dependencies are currently Pydantic and HTTPX.
- Public value contracts are predominantly frozen dataclasses centralized in `vidbyte.lib.dataclasses` and re-exported by feature packages.
- Public package errors subclass `VidbyteSdkError` and expose safe structured details.
- Runtime APIs are async-first where execution may block, with explicit sync bridges only when needed.
- Filesystem stores use inspectable JSON and atomic temp-file replacement.
- New public APIs require root/package exports and nearby README updates.
- The active checkout and the local `main` worktree contain unrelated tracked `__pycache__` modifications. They must not be cleaned or incorporated into this feature.

---

## 4. Requirements

### Functional Requirements

1. `HarnessClient.load(...)` must accept a mapping, JSON path, YAML path, or YML path.
2. The config envelope must use `schema_version`, `harness`, `agents`, and `params` as its only top-level keys.
3. `harness.type` and `harness.version` must be non-empty strings.
4. `agents` must be an array of mappings; each mapping must contain a non-empty `name`. All other per-agent keys remain open for implementation-specific hyperparameters.
5. `params` must be a mapping and remain implementation-specific.
6. Unknown top-level keys must fail closed so misspelled configuration is never silently excluded from identity.
7. Credential-looking configuration keys such as `api_key`, `token`, `password`, `secret`, `credential`, and `auth` must be rejected with guidance to inject credentials through environment/provider construction instead of persisting them.
8. A mapping whose only key is `$file` must resolve the referenced UTF-8 text before fingerprinting. Relative references must resolve from the config file directory or an explicit `base_path` for mapping inputs.
9. The loader must preserve both parsed requested configuration and fully resolved configuration on `HarnessSpec`.
10. `spec_id` must equal `hspec_` plus the SHA-256 digest of canonical JSON for the resolved config.
11. Mapping key order, YAML/JSON whitespace, and comments must not change `spec_id`.
12. Any resolved configuration change, including agent hyperparameters, prompt contents, tools/model identifiers, or implementation version, must change `spec_id`.
13. Store objects, persistence policy, capture policy, timestamps, and run metadata must not participate in `spec_id` because they are passed outside the behavior config.
14. `HarnessClient.register(factory)` must register a factory by exact `(harness_type, harness_version)` and reject duplicates.
15. `HarnessClient.load(...)` must accept a directly supplied `HarnessImplementation` without registration.
16. When no direct implementation is supplied, `load(...)` must resolve and invoke the exact registered factory for the spec type/version.
17. An implementation must only need to expose `execute(request, context)`; it must not inherit an SDK base class.
18. `load(...)` must be synchronous and side-effect free with respect to run persistence. It returns a `LoadedHarness` with an immediately inspectable `spec`.
19. `LoadedHarness.execute(...)` must be the single public execution entry point and must support implementation methods that return either a value or an awaitable.
20. Each execution must create a fresh `hrun_<uuid>` identifier independently of `spec_id`.
21. Before invoking implementation code, execution must persist the specification idempotently and begin a RUNNING run record.
22. The run lifecycle must support RUNNING, SUCCEEDED, FAILED, CANCELLED, and TIMED_OUT terminal states.
23. Successful execution must return `HarnessExecutionResult` containing the raw implementation output and the finalized safe `HarnessRun` record.
24. Implementation exceptions must finalize a FAILED run and raise `HarnessExecutionError` carrying the finalized run; the original exception must remain the chained cause.
25. Timeout must finalize TIMED_OUT and raise `HarnessTimeoutError` carrying the run.
26. Task cancellation must make a shielded best effort to finalize CANCELLED and then re-raise `asyncio.CancelledError`.
27. `HarnessContext.emit(...)` must assign monotonic per-run sequence numbers and append typed events to the store in emission order.
28. `HarnessContext.add_artifact(...)` must attach a typed URI/hash/media-type reference without ingesting artifact bytes.
29. `HarnessContext.link_session(...)` must record unique durable Session IDs involved in the execution.
30. The wrapper must automatically emit lifecycle events for run start and each terminal outcome.
31. `HarnessCaptureLevel.FULL` must persist JSON-safe request, response, run metadata, implementation events, artifact references, and session links.
32. `HarnessCaptureLevel.MINIMAL` must persist identity, timestamps, status, and safe error information while omitting request/response payloads and implementation event payloads.
33. Captured values must be converted to JSON-safe data and scrub credential-looking mapping keys before storage. Unsupported values must be represented by an explicit dropped-type marker rather than causing execution failure.
34. Every `HarnessClient` must default to one shared `InMemoryHarnessStore`, so every execution through that client has a canonical record even when no durable store is supplied.
35. Supplying `FileHarnessStore` or a custom `HarnessStore` at load time must redirect all records for that loaded harness to that store.
36. `HarnessPersistenceMode.BEST_EFFORT` must preserve harness execution when storage fails and attach safe persistence errors to the returned/raised run record.
37. `HarnessPersistenceMode.REQUIRED` must fail before implementation if specification/begin persistence fails and must raise after successful implementation if final persistence fails.
38. When implementation execution and terminal persistence both fail, the implementation failure must remain primary and the persistence failure must be attached to its run record.
39. Stores must reject a `spec_id` collision whose existing resolved config differs.
40. Stores must reject duplicate `run_id` creation and invalid terminal transitions.
41. `InMemoryHarnessStore` must support concurrent async callers safely within one process.
42. `FileHarnessStore` must persist inspectable JSON under `specs/` and per-run JSON plus JSONL events under `runs/`, using atomic replacement for specification and run snapshots.
43. The store protocol must support retrieving a specification, retrieving a run, listing/filtering runs, and retrieving ordered events.
44. `HarnessDatasetExporter.export_jsonl(...)` must write one standalone line per run containing the matching specification, finalized run, and ordered events.
45. Dataset export must support filtering by `spec_id` and run status and must write atomically.
46. The existing `sdk.harnesses.sessions` attribute and all current Session imports must remain backward compatible.
47. The harness README and root README must document identity cardinality, direct and registered loading, persistence modes, config syntax, capture limitations, and JSONL export.

### Non-Functional Requirements

- **Openness:** The SDK may standardize the envelope but must not constrain harness control flow. Structural protocols and open `params`/per-agent mappings are required.
- **Reproducibility:** Canonicalization must be deterministic across supported operating systems and independent of source serialization formatting.
- **Security:** YAML must use `safe_load`; credential-like config keys must fail closed; persisted mappings must be scrubbed recursively; no default durable directory or external write may occur without an explicit store.
- **Privacy:** Full capture is explicit and inspectable. Documentation must warn that prompts, model outputs, tool results, and metadata may contain sensitive or licensed content and that caller retention/deletion policy remains authoritative.
- **Reliability:** All terminal paths must attempt finalization. Best-effort storage failures must be visible rather than swallowed; required mode must enforce the persistence boundary.
- **Concurrency:** Event sequencing and in-memory mutations must be protected for concurrent tasks within the same run. Filesystem writes must be serialized and performed outside the event loop.
- **Performance:** Config hashing is linear in config size. Filesystem work must use `asyncio.to_thread`; no network or database work is added to the core implementation.
- **Schema evolution:** Every serialized spec, run, event, and dataset line must carry schema version 1 and reject unsupported versions on read.
- **Observability:** `run_id`, `spec_id`, status, timestamps, persistence failures, and event sequence must be present in canonical records. Existing trace providers remain optional and separate.
- **Compatibility:** This is additive for an alpha SDK. Existing `HarnessClient`, `sdk.harnesses.sessions`, Session, trace, eval, agent, and paradigm APIs must continue to import and behave as before.
- **Packaging:** YAML support must be present in installed wheels through an explicit PyYAML runtime dependency; no new package-data assets are required.
- **Verification:** No new test files or scripts will be added, but implementation must pass compileall, the existing unittest suite, an inline load/identity/success/failure/timeout/file-store/dataset smoke exercise, and package build/twine checks.

---

## 5. High-Level Design

The implementation follows the same composition lesson as durable Session. An arbitrary `HarnessImplementation` remains unaware of persistence backends and SDK lifecycle mechanics. `HarnessClient.load(...)` parses and resolves config, constructs a deterministic `HarnessSpec`, resolves a direct or registered implementation, and returns `LoadedHarness`. `LoadedHarness` surrounds the implementation's single `execute` method with run creation, capture, timeout/cancellation handling, and terminal persistence.

Configuration identity and execution identity are deliberately separate. One implementation version can have many `HarnessSpec` variants; one spec can have many unique `HarnessRun` executions; each run can have many ordered events and artifact/session references. This prevents a system-prompt change from masquerading as the same harness while also preventing repeated executions from overwriting each other.

The canonical store is independent from observability providers. A run store contains safe resolved behavior config, request/response envelopes, terminal outcomes, and implementation-emitted evidence. Trace providers can still receive spans from agents used by the harness, but a LangSmith or Langfuse trace is not required for dataset export. The first store implementations are process-local memory and inspectable files; external databases implement the async `HarnessStore` protocol in later or closed-repo adapters.

Dataset generation is a derived read operation. The store remains the source of truth; `HarnessDatasetExporter` joins each selected run to its spec and events and writes raw JSONL. Later SFT/RL/eval materializers can consume this stable raw envelope without changing how runs were captured.

```text
                   load(config)
                         |
              [HarnessConfigLoader]
                         |
       requested config + resolved config
                         |
                  [HarnessSpec]
                  spec_id = sha256
                         |
       direct implementation or exact registry factory
                         |
                  [LoadedHarness]
                         |
                    execute(input)
                         |
        +----------------+----------------+
        |                                 |
 [HarnessContext]                  [HarnessStore]
 events / refs / sessions      spec / run / events
        |                                 |
        +---------- implementation -------+
                         |
                [HarnessExecutionResult]
                         |
             [HarnessDatasetExporter]
                         |
                   raw JSONL dataset
```

Cardinality:

```text
Harness implementation 1 -> N HarnessSpec 1 -> N HarnessRun 1 -> N HarnessEvent
                                                     |
                                                     +-> N artifact references
                                                     +-> N durable Session ids
```

---

## 6. Detailed Design

### 6.1 Harness Data Contracts

**File(s):** `vidbyte/lib/dataclasses/harnesses.py`, `vidbyte/harnesses/contracts.py`, `vidbyte/lib/dataclasses/__init__.py`
**Type:** New files plus modified central exports

#### What it does

Defines immutable, serializable value types and enums for specification identity, run lifecycle, events, errors, artifact references, capture/persistence policies, and execution results. The feature package re-exports the centralized dataclasses through a compatibility module, matching the Session pattern.

#### Interface / API

```python
HARNESS_SCHEMA_VERSION: int = 1

class HarnessRunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

class HarnessCaptureLevel(str, Enum):
    MINIMAL = "minimal"
    FULL = "full"

class HarnessCaptureScope(str, Enum):
    BOUNDARY = "boundary"
    INSTRUMENTED = "instrumented"

class HarnessPersistenceMode(str, Enum):
    BEST_EFFORT = "best_effort"
    REQUIRED = "required"

@dataclass(frozen=True, slots=True)
class HarnessSpec:
    schema_version: int
    spec_id: str
    harness_type: str
    harness_version: str
    agents: tuple[Mapping[str, Any], ...]
    params: Mapping[str, Any]
    requested_config: Mapping[str, Any]
    resolved_config: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class HarnessErrorRecord:
    exception_type: str
    message: str

@dataclass(frozen=True, slots=True)
class HarnessArtifactRef:
    artifact_id: str
    uri: str
    media_type: str | None = None
    sha256: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class HarnessEvent:
    schema_version: int
    event_id: str
    run_id: str
    sequence: int
    event_type: str
    created_at: str
    payload: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class HarnessRun:
    schema_version: int
    run_id: str
    spec_id: str
    status: HarnessRunStatus
    started_at: str
    ended_at: str | None
    capture_level: HarnessCaptureLevel
    capture_scope: HarnessCaptureScope
    request: Any = None
    response: Any = None
    error: HarnessErrorRecord | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[HarnessArtifactRef, ...] = ()
    session_ids: tuple[str, ...] = ()
    event_count: int = 0
    persistence_errors: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class HarnessExecutionResult:
    output: Any
    run: HarnessRun
```

#### Logic / Algorithm

1. Use string enums so serialized values remain stable and readable.
2. Keep persisted contracts frozen and slot-backed so callers cannot mutate a record after it is written.
3. Keep events separate from the run snapshot for streaming and high-cardinality storage.
4. Store only artifact references in the run; actual binary/object persistence is delegated elsewhere.
5. Record `capture_scope=BOUNDARY` by default. An implementation may declare `capture_scope="instrumented"` only when it routes its relevant internal operations through captured SDK/context seams.

#### Edge Cases & Error Handling

- Empty identifiers and invalid enum strings are rejected by the loader/execution/store boundaries before record construction.
- `ended_at` is `None` only for RUNNING records.
- `HarnessExecutionResult.output` remains the raw Python value. `HarnessRun.response` is its safe serialized projection and may contain dropped-type markers.
- Persistence errors contain only exception type and message, never connection strings or credentials.

### 6.2 Configuration Loading and Specification Identity

**File(s):** `vidbyte/harnesses/config.py`
**Type:** New file

#### What it does

Owns source parsing, envelope validation, recursive `$file` resolution, credential-key rejection, canonical JSON rendering, and deterministic `HarnessSpec` creation.

#### Interface / API

```python
class HarnessConfigLoader:
    def load(self, source: Mapping[str, Any] | str | Path, *, base_path: str | Path | None = None) -> HarnessSpec:
        # Parses, validates, resolves, and fingerprints one harness behavior config.
        ...

    def canonical_json(self, value: Mapping[str, Any]) -> str:
        # Produces the stable JSON representation used for specification identity.
        ...
```

Accepted config:

```yaml
schema_version: 1

harness:
  type: reflexion
  version: "1.0.0"

agents:
  - name: solver
    role: solver
    provider: openai
    model: gpt-5
    temperature: 0.2
    system_prompt:
      $file: prompts/solver.md
    tools:
      - name: web.search
        version: "1"

params:
  max_iterations: 4
  confidence_threshold: 0.8
```

Resolved prompt shape stored on the spec:

```json
{
  "system_prompt": {
    "content": "...resolved UTF-8 prompt text...",
    "sha256": "...content digest..."
  }
}
```

#### Logic / Algorithm

1. If `source` is a mapping, copy it and resolve relative files from `base_path` or the current directory.
2. If `source` is a path, require `.json`, `.yaml`, or `.yml`, read UTF-8 text, and parse JSON or `yaml.safe_load`.
3. Require a mapping root and reject unknown top-level keys.
4. Validate schema version, harness type/version, agent array/name fields, and params mapping.
5. Recursively reject credential-looking keys before any spec is returned.
6. Preserve the validated parsed mapping as `requested_config`.
7. Recursively replace exact `{"$file": "..."}` mappings with content plus content digest. Reject siblings next to `$file` so resolution is unambiguous.
8. Normalize mappings to string keys and sequences to lists for canonicalization. Reject NaN/infinity.
9. Render canonical JSON with sorted keys, compact separators, UTF-8 characters preserved, and `allow_nan=False`.
10. Compute `spec_id = "hspec_" + sha256(canonical_json.encode("utf-8")).hexdigest()`.
11. Return the immutable `HarnessSpec` containing both forms.

#### Edge Cases & Error Handling

- Missing config files, unsupported extensions, malformed JSON/YAML, empty documents, non-mapping roots, and unsupported schema versions raise `HarnessConfigurationError` or `HarnessVersionError` with path/field details.
- A mapping input containing `$file` without `base_path` resolves from the current directory and documents that behavior.
- Missing, non-file, non-UTF-8, or unreadable references fail load before implementation construction.
- Symbolic links are followed according to normal `Path.read_text` semantics; no remote URLs are fetched.
- Config values that are not JSON-safe fail closed rather than being hashed through `repr`.
- Raw YAML text, comments, and formatting are not persisted; the parsed requested mapping is.

### 6.3 Open Implementation and Factory Registry

**File(s):** `vidbyte/harnesses/registry.py`
**Type:** New file

#### What it does

Defines the structural implementation/factory protocols and an exact type/version registry. This is the openness seam: arbitrary code may satisfy the protocol without inheriting SDK behavior.

#### Interface / API

```python
@runtime_checkable
class HarnessImplementation(Protocol):
    def execute(self, request: Any, context: HarnessContext) -> Any:
        # Executes arbitrary harness logic and may return either a value or an awaitable.
        ...

@runtime_checkable
class HarnessFactory(Protocol):
    harness_type: str
    harness_version: str

    def create(self, spec: HarnessSpec) -> HarnessImplementation:
        # Builds one implementation instance from the exact resolved specification.
        ...

class HarnessRegistry:
    def register(self, factory: HarnessFactory) -> None:
        # Registers one exact implementation type/version factory.
        ...

    def create(self, spec: HarnessSpec) -> HarnessImplementation:
        # Resolves the exact factory and creates an implementation for the spec.
        ...
```

#### Logic / Algorithm

1. Validate factory attributes and `create` callability at registration time.
2. Key factories by normalized `(harness_type, harness_version)` without fuzzy or latest-version fallback.
3. Reject duplicate registrations.
4. On config-only load, resolve the exact key and call `factory.create(spec)`.
5. Validate the returned object has a callable `execute` method.
6. A direct `implementation=` passed to `HarnessClient.load` bypasses registry creation but receives the same `LoadedHarness` execution envelope.

#### Edge Cases & Error Handling

- Unknown exact versions raise `HarnessRegistrationError` listing safe known versions for the requested type.
- Factory construction errors are wrapped as `HarnessConfigurationError` with type/version details and preserved cause.
- No dynamic dotted-path imports are performed from config; this avoids arbitrary import execution and packaging ambiguity.
- Registry state is client-local, so independent SDK clients can use different implementation sets.

### 6.4 Serialization, Errors, and Store Port

**File(s):** `vidbyte/harnesses/serialization.py`, `vidbyte/harnesses/errors.py`, `vidbyte/harnesses/store.py`
**Type:** New files

#### What it does

Provides the schema-versioned codec, typed error hierarchy, asynchronous storage protocol, and shared store invariants.

#### Interface / API

```python
class HarnessError(VidbyteSdkError): ...
class HarnessConfigurationError(HarnessError): ...
class HarnessRegistrationError(HarnessError): ...
class HarnessSerializationError(HarnessError): ...
class HarnessStoreError(HarnessError): ...
class HarnessVersionError(HarnessError): ...

class HarnessExecutionError(HarnessError):
    def __init__(self, message: str, *, run: HarnessRun) -> None:
        # Stores the finalized failed run on the public exception.
        ...

class HarnessTimeoutError(HarnessExecutionError): ...

class HarnessSerializer:
    def spec_to_dict(self, spec: HarnessSpec) -> dict[str, Any]:
        # Serializes one specification through the schema-versioned safe projection.
        ...

    def spec_from_dict(self, payload: Mapping[str, Any]) -> HarnessSpec:
        # Reconstructs one specification and rejects unsupported schema versions.
        ...

    def run_to_dict(self, run: HarnessRun) -> dict[str, Any]:
        # Serializes one run with recursive secret-key scrubbing.
        ...

    def run_from_dict(self, payload: Mapping[str, Any]) -> HarnessRun:
        # Reconstructs one run and its typed nested records.
        ...

    def event_to_dict(self, event: HarnessEvent) -> dict[str, Any]:
        # Serializes one ordered event.
        ...

    def event_from_dict(self, payload: Mapping[str, Any]) -> HarnessEvent:
        # Reconstructs one ordered event.
        ...

    def safe(self, value: Any) -> Any:
        # Converts captured values to JSON-safe scrubbed structures.
        ...

@runtime_checkable
class HarnessStore(Protocol):
    async def put_spec(self, spec: HarnessSpec) -> HarnessSpec:
        # Persists a specification idempotently.
        ...

    async def get_spec(self, spec_id: str) -> HarnessSpec:
        # Retrieves one specification or raises HarnessStoreError.
        ...

    async def begin_run(self, run: HarnessRun) -> HarnessRun:
        # Creates one unique RUNNING run record.
        ...

    async def append_event(self, event: HarnessEvent) -> HarnessEvent:
        # Appends one monotonic event to an existing run.
        ...

    async def finish_run(self, run: HarnessRun) -> HarnessRun:
        # Replaces RUNNING with one terminal run snapshot.
        ...

    async def get_run(self, run_id: str) -> HarnessRun:
        # Retrieves one run by id.
        ...

    async def events(self, run_id: str) -> list[HarnessEvent]:
        # Retrieves ordered events for one run.
        ...

    async def list_runs(self, *, spec_id: str | None = None, status: HarnessRunStatus | None = None, limit: int | None = None) -> list[HarnessRun]:
        # Lists deterministic run snapshots matching optional filters.
        ...

class BaseHarnessStore(ABC):
    # Owns shared collision, transition, ordering, filtering, and typed lookup behavior.
    ...
```

#### Logic / Algorithm

1. The serializer uses a common schema envelope for every backend and dataset export.
2. It recursively handles primitives, mappings, sequences, dataclasses, enums, `Path`, Pydantic `model_dump`, and explicit `to_dict`; unsupported leaves become `{"__dropped__": "TypeName"}`.
3. Credential-looking mapping keys are removed during captured run/event serialization even though config loading already rejects them.
4. `BaseHarnessStore` performs spec collision checks, run creation/transition validation, event ordering checks, and run filtering over backend-specific raw methods.
5. Store errors are wrapped with safe identifiers/provider names; raw connection data is never placed in details.

#### Edge Cases & Error Handling

- Unknown schema versions raise `HarnessVersionError` rather than attempting permissive reads.
- A repeated identical `put_spec` is a no-op; the same ID with different resolved config is a collision error.
- `finish_run` rejects RUNNING as a terminal value, mismatched `spec_id`, missing run IDs, or a second terminalization.
- `append_event` rejects missing runs and non-monotonic/duplicate sequence numbers.
- Negative limits and malformed payload fields fail with typed errors.

### 6.5 In-Memory and Filesystem Stores

**File(s):** `vidbyte/harnesses/stores/README.md`, `vidbyte/harnesses/stores/__init__.py`, `vidbyte/harnesses/stores/memory.py`, `vidbyte/harnesses/stores/file.py`
**Type:** New files

#### What it does

Provides a shared process-local default and an inspectable durable local backend.

#### Interface / API

```python
class InMemoryHarnessStore(BaseHarnessStore):
    def __init__(self) -> None:
        # Initializes empty spec, run, and event maps plus one async lock.
        ...

class FileHarnessStore(BaseHarnessStore):
    def __init__(self, root: str | Path, *, serializer: HarnessSerializer | None = None) -> None:
        # Binds an explicit root and serializer without writing until first persistence.
        ...
```

Filesystem layout:

```text
<root>/
  specs/
    hspec_<sha256>.json
  runs/
    hrun_<uuid>/
      run.json
      events.jsonl
```

#### Logic / Algorithm

1. In-memory storage uses dictionaries plus an `asyncio.Lock` for atomic shared mutations.
2. File storage implements raw reads/writes through `asyncio.to_thread` so JSON I/O does not block the harness event loop.
3. Specification and run snapshots are written to a temporary file in the destination directory and replaced atomically.
4. Events are appended one JSON line at a time under a process-local reentrant lock.
5. Run listing scans `runs/*/run.json`, parses records, applies filters, sorts by `(started_at, run_id)`, and applies limit last.

#### Edge Cases & Error Handling

- Constructing a file store does not create directories; the first write does.
- Missing records raise `HarnessStoreError` with only the safe identifier.
- Corrupt JSON or JSONL reports the affected filename and line number without leaking payload contents.
- A process crash may leave a RUNNING run, which is intentionally visible as an incomplete trajectory. This version does not automatically mark abandoned runs.
- Atomic snapshot replacement is process-safe for separate files; concurrent multi-process appends to the same run are not guaranteed and are documented as unsupported in v1.

### 6.6 Loaded Harness Execution Envelope and Context

**File(s):** `vidbyte/harnesses/execution.py`
**Type:** New file

#### What it does

Owns the final execution lifecycle around the open implementation, including run identity, automatic lifecycle events, event sequencing, artifacts/session links, capture policy, timeout/cancellation behavior, and persistence policy.

#### Interface / API

```python
class HarnessContext:
    @property
    def run_id(self) -> str:
        # Returns the current unique run identifier.
        ...

    @property
    def spec(self) -> HarnessSpec:
        # Returns the immutable exact harness specification.
        ...

    async def emit(self, event_type: str, payload: Mapping[str, Any] | None = None) -> HarnessEvent:
        # Appends one ordered implementation event under the current run.
        ...

    def add_artifact(self, uri: str, *, media_type: str | None = None, sha256: str | None = None, metadata: Mapping[str, Any] | None = None) -> HarnessArtifactRef:
        # Adds a typed external artifact reference to the final run.
        ...

    def link_session(self, session_id: str) -> None:
        # Links one durable Session id to the final run without duplicates.
        ...

class LoadedHarness:
    @property
    def spec(self) -> HarnessSpec:
        # Returns the exact loaded specification.
        ...

    @property
    def store(self) -> HarnessStore:
        # Returns the store selected for this loaded harness.
        ...

    async def execute(self, request: Any, *, metadata: Mapping[str, Any] | None = None, timeout_seconds: float | None = None) -> HarnessExecutionResult:
        # Runs one implementation invocation inside the canonical record lifecycle.
        ...
```

#### Logic / Algorithm

1. Validate timeout and safe metadata before execution begins.
2. Create a unique run ID and safe RUNNING record; request payload is included only for FULL capture.
3. Persist the spec and initial run according to persistence mode.
4. Construct `HarnessContext` and automatically emit `harness.run.started`.
5. Invoke `implementation.execute(request, context)` and await the result only when it is awaitable.
6. If a positive timeout is provided, execute under Python 3.11 `asyncio.timeout`.
7. On success, safely project the output, emit `harness.run.succeeded`, and construct the terminal record with refs/session IDs/event count.
8. On ordinary exception, emit failure, construct a FAILED record, finalize it, and raise `HarnessExecutionError` from the original error.
9. On timeout, emit timeout, construct TIMED_OUT, finalize it, and raise `HarnessTimeoutError`.
10. On cancellation, construct CANCELLED and shield the terminal write before re-raising cancellation.
11. Persistence helper methods collect failures in best-effort mode. Required mode aborts before implementation on setup failure and raises after successful execution on terminal-write failure.
12. Return raw output plus terminal safe run only after finalization handling completes.

#### Edge Cases & Error Handling

- Empty event type, artifact URI, or session ID raises `HarnessConfigurationError` at the context boundary.
- Concurrent `emit` calls use an async lock to keep per-run sequence values unique and storage ordered.
- FULL capture does not guarantee complete internal visibility when implementation code bypasses `HarnessContext` and SDK-instrumented components. The run's `capture_scope` makes this explicit.
- MINIMAL capture still writes lifecycle events with empty payloads so status transitions remain inspectable.
- If lifecycle event persistence fails best-effort, later finalization continues and the safe error is attached to `persistence_errors`.
- A required-mode final write failure after a successful implementation raises `HarnessStoreError`; callers still have no false successful-persistence signal.

### 6.7 Raw Dataset Export

**File(s):** `vidbyte/harnesses/dataset.py`
**Type:** New file

#### What it does

Materializes canonical stored records into portable, one-run-per-line JSONL without redefining the underlying run schema.

#### Interface / API

```python
class HarnessDatasetExporter:
    def __init__(self, store: HarnessStore, *, serializer: HarnessSerializer | None = None) -> None:
        # Binds a run store and the common schema serializer.
        ...

    async def export_jsonl(self, path: str | Path, *, spec_id: str | None = None, statuses: Sequence[HarnessRunStatus | str] | None = None) -> int:
        # Atomically writes matching specs, runs, and ordered events and returns the row count.
        ...
```

One line:

```json
{
  "schema_version": 1,
  "spec": {"spec_id": "hspec_...", "resolved_config": {}},
  "run": {"run_id": "hrun_...", "status": "succeeded"},
  "events": []
}
```

#### Logic / Algorithm

1. Normalize requested status strings to enums.
2. Query filtered runs from the store.
3. For each run, retrieve its specification and ordered events.
4. Serialize one self-contained JSON object per line with the shared serializer.
5. Write to a sibling temporary file and atomically replace the requested path.
6. Return the number of exported runs.

#### Edge Cases & Error Handling

- An empty result creates a valid empty file and returns zero.
- Unknown statuses, missing specs, corrupt records, or unwritable targets fail with typed configuration/store errors.
- Export does not mutate source runs or mark them as used.
- Large datasets are streamed line-by-line to the temporary file rather than accumulated as one JSON array.

### 6.8 Public Client, Exports, Documentation, and Dependency

**File(s):** `vidbyte/harnesses/client.py`, `vidbyte/harnesses/__init__.py`, `vidbyte/harnesses/README.md`, `vidbyte/__init__.py`, `README.md`, `pyproject.toml`
**Type:** Modified files

#### What it does

Exposes the new abstraction through `VidbyteSDK().harnesses`, direct package imports, and selected root imports while preserving `SessionClient` access. Documents the contract and enables safe YAML parsing in installed packages.

#### Interface / API

```python
class HarnessClient:
    def __init__(self, *, registry: HarnessRegistry | None = None, store: HarnessStore | None = None) -> None:
        # Creates client-local registry/default memory store and preserves the sessions namespace.
        ...

    def register(self, factory: HarnessFactory) -> None:
        # Registers one exact implementation factory on this client.
        ...

    def load(self, config: Mapping[str, Any] | str | Path, *, implementation: HarnessImplementation | None = None, store: HarnessStore | None = None, base_path: str | Path | None = None, capture: HarnessCaptureLevel | str = HarnessCaptureLevel.FULL, persistence: HarnessPersistenceMode | str = HarnessPersistenceMode.BEST_EFFORT, metadata: Mapping[str, Any] | None = None) -> LoadedHarness:
        # Resolves one spec and returns its configured execution envelope.
        ...

    def memory_store(self) -> InMemoryHarnessStore:
        # Creates an independent process-local harness store.
        ...

    def file_store(self, root: str | Path) -> FileHarnessStore:
        # Creates an inspectable durable harness store at an explicit root.
        ...

    async def export_jsonl(self, store: HarnessStore, path: str | Path, *, spec_id: str | None = None, statuses: Sequence[HarnessRunStatus | str] | None = None) -> int:
        # Exports selected canonical runs as standalone JSONL rows.
        ...
```

Direct open implementation usage:

```python
class MyHarness:
    async def execute(self, request, context):
        # Runs arbitrary logic while optionally emitting dataset events.
        await context.emit("decision", {"request": request})
        return {"answer": "done"}

sdk = VidbyteSDK()
store = sdk.harnesses.file_store(".vidbyte/harness-runs")
harness = sdk.harnesses.load("harness.yaml", implementation=MyHarness(), store=store)
result = await harness.execute({"task": "..."})
```

Registered config-only usage:

```python
sdk.harnesses.register(MyHarnessFactory())
harness = sdk.harnesses.load("harness.yaml", store=store)
```

#### Logic / Algorithm

1. `HarnessClient` constructs one default in-memory store and one registry per client.
2. Existing `self.sessions = SessionClient()` remains unchanged.
3. `load` delegates config/spec construction, validates policies, resolves the implementation, and constructs `LoadedHarness`.
4. Package/root exports include the client, primary contracts, protocols, loaded wrapper, stores, exporter, and typed errors.
5. Root and harness READMEs explain the implementation/spec/run distinction and avoid claiming automatic capture of out-of-band effects.
6. Add `PyYAML>=6,<7` to runtime dependencies and use only `yaml.safe_load`.

#### Edge Cases & Error Handling

- Passing neither a direct implementation nor a registered exact factory fails at load.
- Passing an invalid implementation object fails at load, before a run record exists.
- Existing users that only call `sdk.harnesses.sessions` observe no behavior change.
- `VidbyteSDK()` performs no durable filesystem write; its default harness store is in memory.

---

## 7. Data Model Changes

### 7.1 Harness Specification

**Change type:** New

```json
{
  "schema_version": 1,
  "spec_id": "hspec_<sha256>",
  "harness_type": "reflexion",
  "harness_version": "1.0.0",
  "agents": [],
  "params": {},
  "requested_config": {},
  "resolved_config": {}
}
```

**Migration strategy:** Additive. No existing persisted data is migrated.

- Forward migration: New stores write version-1 records only.
- Rollback plan: Remove/revert the feature code. Existing harness-store files remain inert user data and can be deleted by the user if no longer needed.

### 7.2 Harness Run

**Change type:** New

```json
{
  "schema_version": 1,
  "run_id": "hrun_<uuid>",
  "spec_id": "hspec_<sha256>",
  "status": "succeeded",
  "started_at": "2026-07-12T00:00:00+00:00",
  "ended_at": "2026-07-12T00:00:05+00:00",
  "capture_level": "full",
  "capture_scope": "boundary",
  "request": {},
  "response": {},
  "error": null,
  "metadata": {},
  "artifacts": [],
  "session_ids": [],
  "event_count": 2,
  "persistence_errors": []
}
```

**Migration strategy:** Additive. Run records do not replace eval runs, trace runs, agent run IDs, or Session checkpoints.

- Forward migration: Consumers adopt `HarnessRun.run_id` as the canonical harness-execution key.
- Rollback plan: No database schema exists in this PR; remove the feature and leave user-owned files untouched.

### 7.3 Harness Event

**Change type:** New

```json
{
  "schema_version": 1,
  "event_id": "hevt_<uuid>",
  "run_id": "hrun_<uuid>",
  "sequence": 0,
  "event_type": "harness.run.started",
  "created_at": "2026-07-12T00:00:00+00:00",
  "payload": {}
}
```

**Migration strategy:** Additive. Events are append-only within a run.

- Forward migration: Future schema versions require explicit serializer support.
- Rollback plan: Event JSONL can be retained/exported independently; no destructive migration occurs.

### 7.4 Filesystem Store Layout

**Change type:** New

```text
specs/<spec_id>.json
runs/<run_id>/run.json
runs/<run_id>/events.jsonl
```

**Migration strategy:** Directories are created lazily under an explicit caller path.

- Forward migration: N/A for schema version 1.
- Rollback plan: Stop using the store; never delete caller data automatically.

---

## 8. API Changes

No network API endpoints, hosted services, or HTTP contracts are added.

### 8.1 Python `sdk.harnesses.load(...)`

**Change type:** Modified public namespace client

**Request:**

```python
loaded = sdk.harnesses.load(
    "harness.yaml",
    implementation=MyHarness(),
    store=store,
    capture="full",
    persistence="best_effort",
)
```

**Response:**

```python
LoadedHarness(spec=HarnessSpec(...), store=store)
```

**Error cases:**

| Error | Condition |
|-------|-----------|
| `HarnessConfigurationError` | Missing/malformed config, unknown keys, credential keys, unreadable `$file`, or invalid implementation |
| `HarnessVersionError` | Unsupported config/persisted schema version |
| `HarnessRegistrationError` | Missing or duplicate exact implementation factory |

### 8.2 Python `LoadedHarness.execute(...)`

**Change type:** New

**Request:**

```python
result = await loaded.execute(request, metadata={"experiment": "baseline"}, timeout_seconds=300)
```

**Response:**

```python
HarnessExecutionResult(output=raw_output, run=terminal_run)
```

**Error cases:**

| Error | Condition |
|-------|-----------|
| `HarnessExecutionError` | Implementation raised after FAILED finalization |
| `HarnessTimeoutError` | Configured timeout elapsed after TIMED_OUT finalization |
| `HarnessStoreError` | Required persistence could not establish or finalize the canonical record |
| `asyncio.CancelledError` | Caller cancelled; cancellation is re-raised after shielded finalization attempt |

### 8.3 Python `HarnessStore`

**Change type:** New

**Request:**

```python
runs = await store.list_runs(spec_id=loaded.spec.spec_id, status=HarnessRunStatus.SUCCEEDED)
events = await store.events(runs[0].run_id)
```

**Response:**

```python
list[HarnessRun]
list[HarnessEvent]
```

**Error cases:**

| Error | Condition |
|-------|-----------|
| `HarnessStoreError` | Missing record, collision, invalid transition/order, corruption, or backend failure |
| `HarnessVersionError` | Stored payload uses an unsupported version |

### 8.4 Python Dataset Export

**Change type:** New

**Request:**

```python
count = await sdk.harnesses.export_jsonl(store, "runs.jsonl", spec_id=loaded.spec.spec_id)
```

**Response:**

```python
int  # number of exported run rows
```

**Error cases:**

| Error | Condition |
|-------|-----------|
| `HarnessConfigurationError` | Invalid status filter or output path input |
| `HarnessStoreError` | Source records cannot be read or destination cannot be written |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/harness-execution-contract.md` | Approved source of truth for this feature |
| CREATE | `vidbyte/lib/dataclasses/harnesses.py` | Central immutable specification/run/event/artifact contracts and enums |
| CREATE | `vidbyte/harnesses/contracts.py` | Feature-local compatibility exports for central contracts |
| CREATE | `vidbyte/harnesses/errors.py` | Typed harness config, registry, serialization, store, execution, timeout, and version errors |
| CREATE | `vidbyte/harnesses/config.py` | JSON/YAML parsing, validation, `$file` resolution, canonicalization, and `spec_id` creation |
| CREATE | `vidbyte/harnesses/registry.py` | Open implementation/factory protocols and exact type/version registry |
| CREATE | `vidbyte/harnesses/serialization.py` | Shared versioned safe codec for all stores and exports |
| CREATE | `vidbyte/harnesses/store.py` | Async `HarnessStore` protocol and shared store invariants |
| CREATE | `vidbyte/harnesses/execution.py` | `HarnessContext` and `LoadedHarness` execution lifecycle |
| CREATE | `vidbyte/harnesses/dataset.py` | Raw specification/run/event JSONL exporter |
| CREATE | `vidbyte/harnesses/stores/README.md` | Folder intent, routing index, non-goals, and durable implementation notes for local stores |
| CREATE | `vidbyte/harnesses/stores/__init__.py` | Public local-store exports |
| CREATE | `vidbyte/harnesses/stores/memory.py` | Default concurrent in-memory harness store |
| CREATE | `vidbyte/harnesses/stores/file.py` | Atomic inspectable filesystem harness store |
| MODIFY | `pyproject.toml` | Add safe first-class YAML parsing dependency |
| MODIFY | `README.md` | Document the harness execution contract and dataset workflow |
| MODIFY | `vidbyte/__init__.py` | Export selected public harness contracts, wrapper, stores, and errors |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Re-export centralized harness dataclasses |
| MODIFY | `vidbyte/harnesses/__init__.py` | Export the complete harness package public surface |
| MODIFY | `vidbyte/harnesses/client.py` | Add load/register/store/export factories while preserving `.sessions` |
| MODIFY | `vidbyte/harnesses/README.md` | Replace namespace-marker docs with config, identity, execution, persistence, and dataset guidance |

No files will be deleted. No test files or verification scripts will be created under the requested no-tests workflow.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| PyYAML | `>=6,<7` | First-class `.yaml`/`.yml` config parsing through `safe_load` | Adds one runtime dependency and YAML parser security/maintenance surface; constrained version and safe loader mitigate it |
| Python standard library | Python 3.11+ | SHA-256, UUIDs, JSON, asyncio timeout/to-thread, atomic file replacement | Low; already required by project |
| Caller-provided `HarnessStore` | Structural async protocol | Persist canonical runs to closed-repo or third-party databases/memory layers | Backend correctness, latency, retention, and access control are caller/provider responsibilities |

No hosted Vidbyte service, database migration, external API endpoint, or required tracing provider is introduced.

---

## 11. Rollout & Deployment

- The change is additive and targets the alpha SDK's `main` branch through a dedicated `feat/harness-execution-contract` worktree and draft PR.
- The design doc must be the first commit on the feature branch.
- `HarnessClient.sessions` must be verified before and after the change as the primary backward-compatibility guard.
- `VidbyteSDK()` will continue to construct without credentials and without a durable filesystem write.
- YAML becomes available automatically after normal package installation through the added dependency.
- No feature flag is required because existing code only observes the new behavior when calling new methods.
- Existing harness implementations can adopt incrementally by passing an object with `execute(request, context)`; registration is optional.
- Existing paradigms are not migrated in this PR. A later adapter PR can demonstrate wrapping `ParadigmHarness.arun` without changing the core contract.
- Existing database providers are not modified. Closed-repo adapters can implement `HarnessStore` immediately; public SQLite/Postgres/Mongo/Supabase adapters can follow after the contract stabilizes.
- Verification before PR:
  - `python -m compileall vidbyte`
  - `python -m unittest discover -s tests`
  - inline smoke covering equivalent/different spec IDs, mapping/JSON/YAML loading, `$file` changes, direct/registered implementations, success/failure/timeout, best-effort/required persistence, memory/file retrieval, event ordering, Session namespace preservation, and JSONL export
  - `python -m build`
  - `python -m twine check dist/*`
- Rollback is a normal revert of feature commits and the PyYAML dependency line. The SDK never deletes user-created store roots during rollback.
- The local `main` worktree is currently behind `origin/main` and dirty only with tracked generated bytecode. With approval, branch setup should avoid touching it and create the isolated feature worktree directly from the freshly fetched `origin/main` commit.

---

## 12. Open Questions

- [ ] Approve PyYAML as a required core dependency for first-class YAML instead of making YAML an optional extra. Recommendation: approve; YAML is the expected human-authored harness format and `safe_load` keeps behavior explicit.
- [ ] Approve the first PR shipping only the generic `HarnessStore` port plus memory/file stores, with database-specific adapters deferred. Recommendation: approve; this validates the contract before multiplying provider schemas.
- [ ] Approve creating `feat/harness-execution-contract` directly from the fetched `origin/main` commit because the existing local `main` worktree contains unrelated tracked `__pycache__` modifications and must not be cleaned or pulled in place. Recommendation: approve this non-destructive worktree setup.

---

## 13. Alternatives Considered

### Alternative 1: Required `BaseHarness` Inheritance

- What: Define an abstract base class with fixed hooks for tools, agents, retries, approval, and tracing.
- Why rejected: It would put algorithm assumptions inside the public contract and constrain the effectively unbounded harness implementation space. A structural one-method protocol plus outer wrapper captures the shared lifecycle without prescribing internals.

### Alternative 2: Config Loader Only

- What: Standardize YAML/JSON parsing and return an implementation, leaving execution and persistence to each harness.
- Why rejected: This removes initialization boilerplate but does not create the canonical run/data invariant. Each implementation would still invent identifiers, failure records, events, and dataset formats.

### Alternative 3: Deterministic `run_id` Derived from Hyperparameters

- What: Hash config directly into `run_id`, as initially proposed.
- Why rejected: Repeated executions of the same configuration would collide and overwrite or become indistinguishable. A deterministic `spec_id` plus unique `run_id` preserves both variant identity and execution cardinality.

### Alternative 4: Reuse `Session` and `SessionStore`

- What: Store each harness execution as a Session or checkpoint.
- Why rejected: Session is a resumable agent-thread state snapshot and checkpoint DAG. Harness runs are terminal execution envelopes with high-cardinality ordered events and dataset queries. Combining them would couple resume semantics to observation data and distort both models.

### Alternative 5: Treat Trace Providers as the Dataset Store

- What: Require LangSmith/Langfuse/debug tracing and export provider traces.
- Why rejected: Trace is optional, provider-oriented, can be sampled/truncated, and may live outside user-controlled persistence. The existing Session trace recorder is explicitly derived and bounded. Canonical run storage must not depend on observability configuration.

### Alternative 6: Persist One Final Run Blob Only

- What: Serialize the entire run only after successful completion.
- Why rejected: Crashes, cancellation, and failures would lose the most valuable trajectories. Beginning the run before implementation and appending events provides durable partial evidence and makes abandoned RUNNING records visible.

### Alternative 7: Add All Database Providers Immediately

- What: Duplicate the Session provider set for harness specs, runs, and events in the first PR.
- Why rejected: It multiplies schema and concurrency decisions before the new run contract has been exercised. The async store protocol is sufficient for closed-repo adapters now; public adapters can follow atomically.

### Alternative 8: Keep Harnesses Completely Open with No SDK Contract

- What: Continue treating every harness as a separate application with its own initialization and data handling.
- Why rejected: It maximizes algorithm freedom but forfeits reproducible configuration identity and compounding trajectory data. The proposed envelope preserves algorithm freedom while standardizing only the shared operational boundary.
