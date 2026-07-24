Exit code: 0
Wall time: 0.9 seconds
Output:
# Design Doc: YAML Configuration Loader

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-18
**Last Updated:** 2026-07-23

---

> **Superseded (2026-07-24, PR #308 review):** The polymorphic redesign of this surface —
> two document families (agent/harness), the `AgentType` discriminator, nested tools/middleware,
> `loop` as `AgentLoopSettings`, provider/model validation, and the shrunk loader — is specified
> in [`yaml-config-polymorphic-agents.md`](yaml-config-polymorphic-agents.md). That document is the
> current source of truth; the notes below describe the earlier #295-era API.

> **Revision (2026-07-23, post-review of PR #295):** The implemented public API differs
> from the original draft below in response to review feedback:
> - The loader class is `YamlLoader` (not `ConfigurationLoader`).
> - Methods are `load()` (central kind dispatch), `load_agent()`, `load_tools()`,
>   `load_middleware()`, and `load_harness()`; harness documents delegate to
>   `vidbyte.harnesses.HarnessConfigLoader`. `view_agent()/view_tools()/view_middleware()/view_harness()`
>   return the expected document structure.
> - The declarative dataclasses (`AgentSettings`, `ToolDefinition`, `MiddlewareDefinition`)
>   live in `vidbyte.lib.dataclasses.config`; the document vocabularies (`ConfigKind`,
>   `AgentLoopField`) live in `vidbyte.lib.enums`. `vidbyte.config.types` re-exports the
>   dataclasses for compatibility.
> - Field validation is owned by each dataclass's `from_mapping`/`__post_init__` rather than
>   ad-hoc loader checks, and errors carry the offending file path, field, and expected value.
> The sections below preserve the original draft for historical context.

---

## 1. Overview

Add a public, class-first YAML configuration surface for the Vidbyte SDK. `ConfigurationLoader` will give developers one discoverable interface for loading validated agent, tool, and middleware declarations: `load_agent_settings()`, `load_tools()`, and `load_middleware_settings()`. The loader will parse YAML safely and return typed settings objects; it will never import arbitrary Python paths or instantiate executable tools, middleware, runners, or agents as a side effect of reading a file.

---

## 2. Goals & Non-Goals

### Goals

- Add a public `vidbyte.config` namespace containing `ConfigurationLoader` and serializable settings types.
- Make `ConfigurationLoader` the primary developer-facing interface for YAML configuration loading.
- Provide these methods in version one:
  - `load_agent_settings(path) -> AgentSettings`
  - `load_tools(path) -> tuple[ToolDefinition, ...]`
  - `load_middleware_settings(path) -> tuple[MiddlewareDefinition, ...]`
- Validate YAML syntax, duplicate mapping keys, document kind, schema version, required fields, scalar types, and intrinsic cross-field invariants before returning settings.
- Make `AgentSettings` a developer-usable dataclass with `to_agent_kwargs()` for explicit construction through the existing `AgentClient` / `BaseAgent` boundary.
- Keep tool and middleware behavior explicitly application-owned by returning named declarations plus options rather than evaluating import paths from YAML.
- Expose the loader and settings types through `vidbyte.config`, `VidbyteSDK().config`, and selected root `vidbyte` imports.
- Document the YAML schemas and the separation between parsing declarations and resolving executable behavior.

### Non-Goals

- Instantiating a `BaseAgent`, `BaseTool`, `AgentMiddleware`, custom runner, output schema, context manager, or tracer while loading YAML.
- Supporting arbitrary Python import strings, YAML object tags, executable templates, environment-variable interpolation, or secrets in YAML.
- Replacing the existing internal `vidbyte.lib.config` model-provider and MCP-preset contracts.
- Creating a generic tool or middleware factory registry in this change.
- Supporting JSON, TOML, remote URLs, includes, references between YAML files, or a combined project manifest in version one.
- Adding feature test files under the requested `design-doc-no-tests` workflow. Existing compile, unittest, and import checks remain required after implementation.

---

## 3. Background & Context

The SDK currently exposes executable feature namespaces through `VidbyteSDK`: agents, tools, providers, evals, harnesses, and paradigms. `AgentClient.base()` is the existing construction seam for `BaseAgent`, while `ToolsClient` owns the compatibility registry and catalog. The agent constructor accepts provider/model data, tools, middleware, and `AgentLoopSettings`, but an agent itself is a behavior-rich class rather than a serializable dataclass.

The repository already uses validated settings objects such as `AgentLoopSettings` and immutable payload dataclasses such as `AgentRunnerConfig`, `AgentSpec`, and `ToolSpec`. Those types do not, however, form a complete YAML model: `AgentSpec` does not contain provider/model/loop/tool data, and `ToolSpec` describes a tool to a model but cannot recreate its Python behavior.

`vidbyte.lib.config` is a shared internal contract layer for provider configuration and MCP preset definitions. A loader that spans agents, tools, and middleware would make that layer depend upward on feature packages. The new public `vidbyte.config` namespace instead owns declarative configuration as an SDK feature and leaves `vidbyte.lib.config` unchanged.

The project supports Python 3.11+, uses dataclasses, Pydantic 2, `pytest`, and `unittest`, but its declared runtime dependencies do not currently include a YAML parser. The current main branch provides the canonical full verification gate at `python scripts/run_ci.py`; it compiles the package, runs pytest, builds distributions, checks them with Twine, and smoke-tests a clean wheel installation.

---

## 4. Requirements

### Functional Requirements

1. The SDK must expose `ConfigurationLoader` as a public class under `vidbyte.config`, from the root `vidbyte` package, and as `VidbyteSDK().config`.
2. A developer must be able to create one loader instance and call `load_agent_settings()`, `load_tools()`, and `load_middleware_settings()` repeatedly without retained per-file state.
3. Every public load method must accept `str | pathlib.Path` and accept only `.yaml` or `.yml` files.
4. YAML parsing must use a safe loader and must reject duplicate mapping keys rather than silently retaining the final value.
5. Each YAML document must declare `version: 1` and a `kind` that matches the method being called: `agent`, `tools`, or `middleware`.
6. Unknown keys at every supported schema level must raise `ConfigurationError` with the source path and a dotted field path.
7. `load_agent_settings()` must return an `AgentSettings` dataclass containing agent identity, prompt, provider/model inputs, runtime, loop settings, optional tool references, optional middleware references, and serializable metadata.
8. `AgentSettings` must validate its own intrinsic invariants in `__post_init__`, including non-blank identity/prompt values, a provider/model pair, non-blank/unique references, and a valid runtime value.
9. `AgentSettings.to_agent_kwargs()` must return the keyword arguments needed by the existing `AgentClient.base()` / `BaseAgent` construction surface after the caller explicitly supplies resolved tools and middleware.
10. `load_tools()` must return `ToolDefinition` values with a stable `ref` and a mapping of serializable `options`; it must reject blank and duplicate references.
11. `load_middleware_settings()` must return `MiddlewareDefinition` values with a stable `ref` and a mapping of serializable `options`; it must reject blank and duplicate references.
12. Tool and middleware options may contain YAML scalar/list/mapping values but must not contain executable Python objects, custom YAML tags, or secret interpolation.
13. The loader must not resolve or import a `ref`. An application remains responsible for mapping a tool or middleware reference to an executable implementation.
14. A missing file, unreadable file, unsupported extension, malformed YAML document, duplicate key, wrong document kind, unsupported version, or invalid settings object must raise the existing `ConfigurationError` with the original exception retained as the cause when applicable.
15. The loader must not include YAML values in errors when the offending field name suggests a secret (`api_key`, `token`, `password`, or `secret`).
16. The README and LLM documentation must show the public API and explicitly state the parse-versus-resolution boundary.

### Non-Functional Requirements

- **Security:** Use `yaml.SafeLoader` only, reject custom tags, duplicate keys, dynamic imports, and YAML-held secrets. Parsing must perform no network access, subprocess launch, or object construction beyond typed settings data.
- **Reliability:** Loader instances must be stateless and safe to use concurrently as long as callers do not mutate returned settings instances.
- **Compatibility:** This is additive. Existing agent, tool, middleware, and `vidbyte.lib.config` APIs keep their current behavior.
- **Performance:** Loading should be linear in document size and happen at developer-controlled initialization time, not during the agent loop.
- **Observability:** Error details must identify the configuration path, expected document kind/version, and dotted field path without exposing secrets.
- **Code style:** New non-trivial loading logic will be class-first. Every new method signature will fit on one line and have the required immediately following explanatory comment.

---

## 5. High-Level Design

The feature introduces a public `vidbyte.config` package. `ConfigurationLoader` is the single orchestration class. Its public methods select an expected YAML document kind and delegate to a small sequence of private responsibilities: read the file, parse one safe mapping, validate the document envelope, construct typed settings, and normalize loader errors to `ConfigurationError`.

The settings types live alongside the loader, rather than in `vidbyte.lib.dataclasses`, because they are a public declarative configuration layer that composes agent, tool, and middleware concepts. This avoids a dependency inversion in which the shared internal `lib` layer would need to import feature packages. `AgentSettings` uses the existing `AgentLoopSettings` and translates into explicit `BaseAgent` kwargs only when the developer supplies already-resolved tools and middleware.

Tools and middleware are declarations, not executable objects. A YAML `ref` such as `repo.grep` is safe and portable; an import string such as `my_project.tools:grep` would turn a configuration file into a code-execution channel. Applications can supply their own resolver or factory mapping after loading definitions. A future resolver registry may be designed separately if users need built-in construction from these declarations.

```text
agent.yaml / tools.yaml / middleware.yaml
                  |
                  v
       ConfigurationLoader (safe parse + schema validation)
                  |
       +----------+-----------+
       |          |           |
 AgentSettings  ToolDefinition  MiddlewareDefinition
       |          |           |
       +----------+-----------+
                  |
          application resolves refs explicitly
                  |
                  v
 AgentClient.base(**settings.to_agent_kwargs(...))
```

---

## 6. Detailed Design

### 6.1 Public configuration package

**File(s):** `vidbyte/config/__init__.py`, `vidbyte/config/README.md`
**Type:** New file

#### What it does

Defines the stable public package boundary for YAML configuration loading and re-exports `ConfigurationLoader`, `AgentSettings`, `ToolDefinition`, and `MiddlewareDefinition`.

#### Interface / API

```python
from vidbyte.config import AgentSettings, ConfigurationLoader, MiddlewareDefinition, ToolDefinition
```

#### Logic / Algorithm

1. Import the public loader and settings types from sibling modules.
2. Define an explicit `__all__` list.
3. Do not import any application-specific tools, middleware, providers, or runners.

#### Edge Cases & Error Handling

- Importing `vidbyte.config` must not read configuration files or require optional tool/middleware dependencies.
- The package must remain importable when no YAML files exist.
- `vidbyte/config/README.md` must document the folder boundary, public files, and intentional non-goals so future configuration features do not turn parsing into runtime resolution.

### 6.2 Configuration settings types

**File(s):** `vidbyte/config/types.py`
**Type:** New file

#### What it does

Defines the developer-facing typed values produced by the loader. The types own validation that can be decided from their values alone, while resolution of runtime behavior remains outside the types.

#### Interface / API

```python
@dataclass(slots=True)
class ToolDefinition:
    ref: str
    options: Mapping[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class MiddlewareDefinition:
    ref: str
    options: Mapping[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class AgentSettings:
    name: str
    system_prompt: str
    provider: str
    model_name: str
    runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR
    loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)
    tool_refs: tuple[str, ...] = ()
    middleware_refs: tuple[str, ...] = ()
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_agent_kwargs(self, *, tools: Sequence[object] = (), middleware: Sequence[AgentMiddleware] = ()) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. `ToolDefinition.__post_init__` and `MiddlewareDefinition.__post_init__` strip and validate `ref`, copy `options` to a plain mapping, and reject non-mapping options.
2. `AgentSettings.__post_init__` strips and validates `name`, `system_prompt`, `provider`, and `model_name`; coerces `runtime` to `AgentRuntimeType`; normalizes sequence fields to tuples; and rejects blank or duplicate tool/middleware references.
3. The loader constructs `AgentLoopSettings` from the `loop` mapping so existing loop-setting validation remains the source of truth for loop budgets and relationships.
4. `to_agent_kwargs()` returns the supported `BaseAgent` fields, including the supplied resolved tool/middleware objects and `agent_loop_settings=self.loop`; it does not instantiate the agent.
5. The method does not attempt to verify that resolved objects match YAML references. Resolver behavior remains application-owned in version one.

#### Edge Cases & Error Handling

- A YAML agent must provide both provider and model name; YAML cannot represent a custom runner in version one.
- Empty `tools` and `middleware` declarations are valid and normalize to empty tuples.
- `metadata` and definition `options` must be recursively YAML-serializable data. The loader rejects unsupported tag-derived objects before settings construction.
- A developer may construct these dataclasses directly; the same intrinsic validation must apply without YAML involvement.

### 6.3 `ConfigurationLoader`

**File(s):** `vidbyte/config/loader.py`
**Type:** New file

#### What it does

Provides the requested class interface for safe YAML parsing and conversion into the three settings categories.

#### Interface / API

```python
class ConfigurationLoader:
    def load_agent_settings(self, path: str | Path) -> AgentSettings: ...
    def load_tools(self, path: str | Path) -> tuple[ToolDefinition, ...]: ...
    def load_middleware_settings(self, path: str | Path) -> tuple[MiddlewareDefinition, ...]: ...
```

Example documents:

```yaml
# agent.yaml
version: 1
kind: agent
agent:
  name: repo-analyst
  system_prompt: Inspect the repository and report evidence.
  provider: openai
  model_name: gpt-4.1
  runtime: linear
  loop:
    max_iterations: 8
    max_tokens: 16000
  tools: [repo.grep, calculator]
  middleware: [tool-policy]
```

```yaml
# tools.yaml
version: 1
kind: tools
tools:
  - ref: repo.grep
    options:
      root_dir: .
  - ref: calculator
```

```yaml
# middleware.yaml
version: 1
kind: middleware
middleware:
  - ref: tool-policy
    options:
      allow_tools: [repo.grep, calculator]
```

#### Logic / Algorithm

1. Each public method calls a shared private reader with its expected kind.
2. The reader validates the path type, confirms the file exists and has a supported suffix, and reads UTF-8 text.
3. A private duplicate-key-aware subclass of `yaml.SafeLoader` parses the document. It rejects custom tags and duplicate mapping keys.
4. The reader requires a root mapping with exact `version`, `kind`, and one payload key matching the selected method.
5. It rejects unknown envelope/payload keys and reports their dotted path.
6. The selected method constructs `AgentSettings`, `ToolDefinition`, or `MiddlewareDefinition` instances after validating the expected scalar/list/mapping shapes.
7. ValueError, TypeError, YAML parser errors, and settings validation errors are converted into `ConfigurationError` with safe details (`path`, `field`, `expected_kind`) and chained causes.

#### Edge Cases & Error Handling

- Empty documents, documents containing `null`, documents with a scalar root, and the wrong `kind` are invalid.
- `.json`, `.toml`, extensionless files, and directories are rejected before parsing.
- Duplicate YAML keys are invalid even if their values are identical.
- Parser marks are included in error details when PyYAML supplies line and column information.
- Errors for secret-like field names do not echo the offending YAML value.
- The loader does not cache parsed content; callers control reloading and file-change behavior.

### 6.4 Root SDK integration and public exports

**File(s):** `vidbyte/client.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Makes configuration loading available alongside existing SDK namespace clients and keeps common imports concise.

#### Interface / API

```python
from vidbyte import ConfigurationLoader, VidbyteSDK

loader = ConfigurationLoader()
settings = loader.load_agent_settings("agent.yaml")

sdk = VidbyteSDK()
same_surface = sdk.config.load_tools("tools.yaml")
```

#### Logic / Algorithm

1. `VidbyteSDK.__init__` creates one stateless `ConfigurationLoader` at `self.config`.
2. The root package re-exports `ConfigurationLoader` and the three settings types.
3. Existing namespace clients and their construction behavior remain unchanged.

#### Edge Cases & Error Handling

- Constructing `VidbyteSDK()` stays side-effect free because `ConfigurationLoader` does not read files during initialization.
- `sdk.config` is additive and does not alter any existing namespace attribute.

### 6.5 Package metadata and documentation

**File(s):** `pyproject.toml`, `README.md`, `llms.txt`
**Type:** Modified

#### What it does

Declares the YAML parser dependency and documents the new public configuration surface for both developers and LLM-facing repository guidance.

#### Interface / API

```toml
dependencies = [
  "pydantic>=2,<3",
  "httpx>=0.27",
  "PyYAML>=6,<7",
]
```

#### Logic / Algorithm

1. Add PyYAML as a runtime dependency because Python's standard library does not parse YAML.
2. Add `vidbyte.config` to the README layer guide.
3. Add one minimal loader example and explain that refs require application-side resolution.
4. Update `llms.txt` package-map and public-API guidance with the same boundary.

#### Edge Cases & Error Handling

- Documentation must never imply YAML can serialize arbitrary tool or middleware code.
- Documentation must direct users to environment variables or existing provider configuration for secrets.

---

## 7. Data Model Changes

### 7.1 `AgentSettings`

**Change type:** New

```python
@dataclass(slots=True)
class AgentSettings:
    name: str
    system_prompt: str
    provider: str
    model_name: str
    runtime: AgentRuntimeType | str = AgentRuntimeType.LINEAR
    loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)
    tool_refs: tuple[str, ...] = ()
    middleware_refs: tuple[str, ...] = ()
    description: str = ""
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:**

- Forward migration: additive in-memory configuration object with no persisted state.
- Rollback plan: remove the public configuration package and PyYAML dependency; existing agent APIs remain unaffected.

### 7.2 `ToolDefinition` and `MiddlewareDefinition`

**Change type:** New

```python
@dataclass(slots=True)
class ToolDefinition:
    ref: str
    options: Mapping[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class MiddlewareDefinition:
    ref: str
    options: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:**

- Forward migration: additive declarative objects only; no tool or middleware behavior changes.
- Rollback plan: remove the configuration package. Applications retain their existing direct object construction paths.

---

## 8. API Changes

### 8.1 Python configuration-loading API

**Change type:** New

```python
from vidbyte import ConfigurationLoader, VidbyteSDK

loader = ConfigurationLoader()
agent_settings = loader.load_agent_settings("agent.yaml")
tools = loader.load_tools("tools.yaml")
middleware = loader.load_middleware_settings("middleware.yaml")

sdk = VidbyteSDK()
agent_settings = sdk.config.load_agent_settings("agent.yaml")
```

**Error cases:**

| Exception | Condition |
|---|---|
| `ConfigurationError` | Missing/unreadable file, unsupported suffix, malformed YAML, duplicate mapping key, wrong kind/version, unknown field, or invalid setting value |
| `ConfigurationError` | Tool/middleware declaration cannot be resolved by the caller's separate resolver; this feature supplies no implicit resolver |

### 8.2 Agent construction adapter

**Change type:** New

```python
agent = sdk.agents.base(
    **agent_settings.to_agent_kwargs(
        tools=resolved_tools,
        middleware=resolved_middleware,
    )
)
```

**Error cases:**

| Exception | Condition |
|---|---|
| Existing `ConfigurationError` / `AgentExecutionError` | Existing `BaseAgent` construction rules reject the resolved runtime configuration |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/yaml-configuration-loader.md` | Approval-gated source of truth for the feature |
| CREATE | `vidbyte/config/__init__.py` | Public configuration namespace exports |
| CREATE | `vidbyte/config/README.md` | Folder boundary, file index, and explicit non-goals for the public configuration layer |
| CREATE | `vidbyte/config/types.py` | Typed agent, tool, and middleware declaration objects with intrinsic validation |
| CREATE | `vidbyte/config/loader.py` | Class-first safe YAML parsing and requested loader interface |
| MODIFY | `vidbyte/client.py` | Expose `VidbyteSDK().config` as a `ConfigurationLoader` instance |
| MODIFY | `vidbyte/__init__.py` | Root exports for the loader and configuration types |
| MODIFY | `pyproject.toml` | Add the PyYAML runtime dependency |
| MODIFY | `README.md` | Public documentation, layer guide, and safe-resolution example |
| MODIFY | `llms.txt` | LLM-facing package map and configuration-boundary guidance |

No files are deleted. No test files are created or modified under the requested `design-doc-no-tests` workflow.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| PyYAML | `>=6,<7` | Safe parsing of `.yaml` and `.yml` documents | Medium: YAML parser dependency; mitigated with `SafeLoader`, custom-tag rejection, duplicate-key rejection, and no object construction |
| Python standard library `pathlib`, `dataclasses` | Python 3.11+ | Paths, typed settings, and no-state loader interface | Low |
| Existing `ConfigurationError` | Internal SDK exception | Uniform configuration failure shape | Low |
| Existing `AgentLoopSettings`, `AgentClient`, `BaseAgent` | Internal SDK APIs | Preserve validation and construction ownership | Low |
| External services | N/A | No network, database, subprocess, or provider calls are added | None |

---

## 11. Rollout & Deployment

- This is an additive Python SDK feature with no feature flag, database migration, or service deployment.
- Release notes and docs must state that configuration files are declarative only and need application-side resolution for tools and middleware.
- The implementation branch will be `feat/yaml-configuration-loader` in an isolated worktree, created only after design approval.
- Before a PR is created, install the package with its updated dependencies and run `python scripts/run_ci.py` in full. The CI script covers source compilation, pytest discovery, package build/metadata checks, and a clean wheel-install smoke test.
- Run an additional local import/load smoke exercise for `ConfigurationLoader`, `VidbyteSDK().config`, and the three public load methods using temporary YAML fixtures created inline in the shell session. No committed feature test file is added in this workflow.
- Rollback is a revert of the feature PR plus removal of the PyYAML dependency. No persisted configuration state or runtime behavior is migrated.

---

## 12. Open Questions

- [ ] Should a future configuration resolver be supplied by the SDK for a curated set of built-in tools and middleware, or should all `ref` resolution remain application-owned? This design intentionally chooses application-owned resolution for version one.
- [ ] Should version two add a combined `project.yaml` document and `load_project_settings()` after the three standalone document kinds have stabilized?
- [ ] Is `.yml` compatibility desired in addition to the requested `.yaml` extension? This design accepts both because they are conventional YAML suffixes; it can be narrowed before implementation if a strict `.yaml` policy is preferred.
- [ ] Should the CI wheel smoke test be expanded in a follow-up to import `ConfigurationLoader` explicitly? The generic package smoke currently instantiates `VidbyteSDK`, while this feature's additional inline smoke check verifies the new public configuration API.

---

## 13. Alternatives Considered

### Alternative 1: Put the loader in `vidbyte.lib.config`

- What: Add `ConfigurationLoader` and configuration settings types beside existing provider-model and MCP preset configuration.
- Why rejected: `lib` is the shared internal contract layer. A loader that coordinates agent, tool, and middleware declarations would need to depend on higher-level feature packages, reversing the repository's established layering.

### Alternative 2: Add `from_yaml()` and `build()` to `BaseAgent`, `BaseTool`, and `AgentMiddleware`

- What: Make each executable runtime class deserialize and build itself directly from YAML.
- Why rejected: executable objects require application-owned Python behavior, dependency injection, and potentially side-effecting constructor options. Mixing file parsing into those classes makes import-time dependencies and security boundaries harder to reason about.

### Alternative 3: Permit YAML import paths such as `package.module:Class`

- What: Let tool and middleware documents name arbitrary Python callables to instantiate.
- Why rejected: a configuration file would become a code-execution input. It also makes configuration non-portable, ambiguous about constructor dependencies, and difficult to secure in shared environments.

### Alternative 4: Use module-level functions only

- What: Export independent `load_agent_settings`, `load_tools`, and `load_middleware_settings` functions with no loader class.
- Why rejected: the requested developer experience is one discoverable interface for the related operations. A stateless `ConfigurationLoader` provides that interface and still permits one shared parsing/error-normalization implementation.

### Alternative 5: Reuse the planned runtime `ToolSettings` type for YAML tool declarations

- What: Use one `ToolSettings` type for YAML-selected tools and direct-runtime policy such as denied tools or result truncation.
- Why rejected: these are different concepts. YAML declarations select/configure tool implementations; runtime tool settings govern invocation policy. `ToolDefinition` avoids a public-name collision and preserves a clear security boundary.
