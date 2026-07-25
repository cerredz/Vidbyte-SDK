# Design Doc: YamlLoader.build_agent

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-25
**Last Updated:** 2026-07-25

---

## 1. Overview

`YamlLoader` currently parses a YAML document into a validated `AgentSettings` and stops there; turning those settings into a live `BaseAgent` is left to every application, which re-implements the same resolution and default-filling logic by hand. This change adds one method, `YamlLoader.build_agent(settings, ...)`, that takes the output of `load()`/`load_agent()` and returns a constructed `BaseAgent`. It resolves the document's `tools`/`middleware`/`context_items` refs against caller-supplied components — never by importing anything named in the document — and fails closed when a declared ref, or a tool named by an output contract, cannot be resolved.

---

## 2. Goals & Non-Goals

### Goals

- Add `build_agent` to `vidbyte/config/loader.py::YamlLoader`, consuming the return value of `load()`/`load_agent()`.
- Make the document's `tools:`, `middleware:`, and `context_items:` declarations load-bearing at construction time instead of decorative.
- Fail closed on any declared-but-unresolvable ref, and on any output contract / tool-settings key naming a tool the agent will not have.
- Provide an explicit, named injection surface for the construction inputs YAML cannot carry (`context_manager`, `output_schema` as a Python class, `tracer`, `permission_policy`).
- Support the `build(name=...)` form from the originating review comment, re-validated so a renamed agent still satisfies the tool-name rules.
- Preserve the existing security invariant: parsing and building never import a module named by a document.

### Non-Goals

- **Building from a `HarnessSpec`.** `HarnessSpec.agents` is `tuple[Mapping[str, Any], ...]` — untyped dicts in a different dialect (`model` not `model_name`, `params` not `loop`). Converging that is a separate PR; this one detects a `HarnessSpec` and raises a directive error.
- **A separate `AgentBuilder` class.** Rejected in §13.
- **Resolving the duplicate `YamlLoader`** in `vidbyte/lib/config/loader.py` (§12).
- **Building non-`base` agent types** (`aggregate`, `handoff`, `multi`, `adversarial`, `continual_trace`). `AgentSettings.from_mapping` already refuses to load them; `build_agent` refuses to build them.
- **New test files.** Per the invoked workflow. Existing CI must stay green.
- **Changing `llms.txt`**, whose configuration section documents the other loader (§12).

---

## 3. Background & Context

The originating review comment is on `Vidbyte#284`, at `backend/services/harnesses/research/agents/discovery.py:86`:

> note, this type of function should be able to be ran in the "YamlLoader" of the vidbyte-sdk/, this is actually a vidbyte-sdk/ request. for the "YamlLoader" class can you also create like a "build" command that returns a base agent and a build(name) that builds the agent with name=name, in fact lets have build_agent function specifically, not harnesses

The function it points at ends:

```python
return BaseAgent(
    name=str(config["name"]),
    system_prompt=str(config.get("system_prompt") or ""),
    provider=str(config.get("provider") or "deepseek"),
    model_name=str(config.get("model") or "deepseek-v4-flash"),
    ...
)
```

Every `.get(key, default)` there is a second source of truth for a default the SDK already owns. If the YAML omits `provider`, the effective provider is `"deepseek"` because of a string literal in an application, not because of anything the loader validated.

**Current state.** `vidbyte/config/loader.py::YamlLoader` has `load`, `load_agent`, `load_harness`, `view_agent`. `AgentSettings.to_agent_kwargs(tools=, middleware=, context_items=)` already returns exactly `BaseAgent.__init__`'s keyword arguments — and has **zero production callers**; it appears only in tests and design docs. `README.md:112` documents the manual incantation:

```python
agent = VidbyteSDK().agents.base(**settings.to_agent_kwargs(tools=tools, middleware=middleware))
```

The seam exists. This change makes it a method.

**Constraints found during the audit.**

- `vidbyte.agents` imports nothing from `vidbyte.config`, so a `BaseAgent` import here creates no cycle today. It is kept function-local so the dependency stays reversible.
- `Tools.subset(names)` (`vidbyte/tools/catalog.py:86`) already performs name-keyed selection and raises `ToolRegistryError` listing every unknown name. Tool ref resolution reuses it rather than reimplementing lookup.
- Every `AgentSettings` field validator has an `isinstance(value, Target) → return value` fast path, and `_definitions` passes already-built definition objects through. `__post_init__` is therefore idempotent, so `dataclasses.replace(settings, name=...)` re-validates the new name for free.
- `MinToolCallsById` exposes a public `.tool_name` (`vidbyte/agents/contracts/floors.py:105`), making the tool-coherence check cheap.
- The canonical CI command is `python scripts/run_ci.py` (source gate: no tracked bytecode, `compileall`, `check_context_write_paths.py`, `pytest`; package gate: build, twine, clean-install smoke test).

---

## 4. Requirements

### Functional Requirements

1. `YamlLoader.build_agent(settings, ...)` accepts an `AgentSettings` — the value returned by `load()`/`load_agent()` — and returns a constructed `BaseAgent`.
2. `settings.tools` refs resolve against a caller-supplied `Tools`/`ToolRegistry`/sequence of tools. The document is the allowlist: the built agent receives exactly the declared refs, never the caller's whole catalog.
3. A tool ref not present in the caller's catalog raises, naming every unresolved ref.
4. `settings.middleware` refs resolve against a caller-supplied `Mapping[str, object]`; an unresolved ref raises, naming the ref and the available keys.
5. `settings.context_items` refs resolve the same way as middleware.
6. A document that declares no `tools`/`middleware`/`context_items` produces an agent with none of them, regardless of what the caller supplied.
7. `context_manager`, `output_schema`, `tracer`, and `permission_policy` are accepted as explicit named parameters. A supplied `output_schema` (a Python class) overrides the document's JSON-Schema mapping.
8. `name=` overrides the settings' name, re-validated against the same rules the loader applies; an invalid override raises rather than reaching `BaseAgent`.
9. Passing a `HarnessSpec` raises a `ConfigurationError` stating that harness documents are not yet buildable and naming `load_agent`.
10. Settings whose `type` is not `AgentType.BASE` raise a `ConfigurationError` naming the requested type.
11. Any tool name appearing in `loop.output_contracts` (contracts exposing `tool_name`), `loop.tool_settings.max_calls_per_tool`, or `loop.allowed_tools` that is not in the resolved tool set raises a `ConfigurationError` at build time.
12. `build_agent` never imports a module, attribute, or callable named by document text.
13. Each call returns a fresh `BaseAgent`; no memoization or instance reuse.

### Non-Functional Requirements

- **Dependencies:** no new third-party dependencies. Stdlib `dataclasses.replace` only.
- **Performance:** O(number of declared refs). No I/O — `build_agent` never touches the filesystem or network; disk access remains confined to `load*`.
- **Security:** the "no import from a document" invariant is preserved and stated in `vidbyte/config/README.md`. Caller-supplied components are the only source of runtime objects.
- **Error contract:** all failures raise `ConfigurationError` with `details["field"]` set to the offending document path (`agent.tools[1].ref`, `agent.loop.output_contracts[0].tool_name`), matching the loader's existing convention. `Tools.subset`'s `ToolRegistryError` is caught and re-raised as `ConfigurationError` so callers see one error type from this boundary.
- **Observability:** no logging is added; this package emits none today.
- **Concurrency:** `YamlLoader` stays stateless, so the new method is safe on the shared `VidbyteSDK().config` instance.
- **Style:** class-first, one-line signatures, a 1–2 line comment under every signature, per `CONTRIBUTING.md` and the surrounding file.

---

## 5. High-Level Design

One method plus four private helpers on the existing `YamlLoader`. No new files, no new classes, no new exports — `YamlLoader` is already re-exported from `vidbyte`, `vidbyte.config`, and `VidbyteSDK().config`, so the method reaches every consumer with zero packaging change.

The pipeline stays three-layered, with each layer keeping the property it already advertises:

```
document text ──load()──▶ AgentSettings ──build_agent()──▶ BaseAgent
                (parse,                    (resolve refs,
                 validate,                  check coherence,
                 no imports)                construct)
                                                 ▲
                                     caller-supplied components
                                     (tools / middleware / context_items)
                                     + non-serializable injections
```

`build_agent` composes four named steps: resolve tool refs, resolve middleware and context-item refs, verify tool-name coherence between the loop settings and the resolved tools, then construct. Construction reuses `AgentSettings.to_agent_kwargs()` — the existing, currently-uncalled seam — and layers the injected non-serializable inputs on top, so there remains exactly one place that maps settings fields onto `BaseAgent` keyword arguments.

The two key decisions: **caller-supplied components, never document-driven imports**, which keeps the security posture the package README already promises; and **`Tools.subset()` for tool resolution**, which reuses the catalog's existing fail-closed name lookup instead of adding a second one.

---

## 6. Detailed Design

### 6.1 YamlLoader

**File:** `vidbyte/config/loader.py`
**Type:** Modified

#### What it does

Gains a build step that turns validated settings plus caller-supplied components into a live agent.

#### Interface / API

```python
class YamlLoader:
    def build_agent(self, settings: AgentSettings, *, name: str | None = None, tools: "Tools | Sequence[object]" = (), middleware: Mapping[str, object] = {}, context_items: Mapping[str, object] = {}, context_manager: object | None = None, output_schema: object | None = None, tracer: object | None = None, permission_policy: object | None = None) -> "BaseAgent": ...

    def _buildable_settings(self, settings: object, name: str | None) -> AgentSettings: ...
    def _resolve_tools(self, settings: AgentSettings, catalog: object) -> object: ...
    def _resolve_named(self, definitions: tuple[Any, ...], available: Mapping[str, object], field_name: str) -> tuple[object, ...]: ...
    def _assert_tool_names_resolve(self, settings: AgentSettings, resolved: object) -> None: ...
    def _construct_agent(self, settings: AgentSettings, tools: object, middleware: tuple[object, ...], context_items: tuple[object, ...], injections: Mapping[str, object]) -> "BaseAgent": ...
```

Mutable defaults are written as immutable empty mappings in the implementation (`MappingProxyType({})` or a module constant), not literal `{}`.

#### Logic / Algorithm

`build_agent`:

1. `settings = self._buildable_settings(settings, name)` — type gate plus optional rename.
2. `resolved_tools = self._resolve_tools(settings, tools)`.
3. `resolved_middleware = self._resolve_named(settings.middleware, middleware, "agent.middleware")`.
4. `resolved_items = self._resolve_named(settings.context_items, context_items, "agent.context_items")`.
5. `self._assert_tool_names_resolve(settings, resolved_tools)`.
6. `return self._construct_agent(settings, resolved_tools, resolved_middleware, resolved_items, injections)`.

`_buildable_settings`:

1. If the value is a `HarnessSpec`, raise `ConfigurationError` naming `load_agent` and stating harness documents are not yet buildable.
2. If it is not an `AgentSettings`, raise, reporting the received type.
3. If `settings.type is not AgentType.BASE`, raise, naming the type and listing `base` as the buildable one.
4. If `name` is `None`, return `settings` unchanged; otherwise return `dataclasses.replace(settings, name=name)`, whose re-run `__post_init__` validates the override. Wrap the raised `ConfigurationError` to re-point `details["field"]` at `build_agent.name`.

`_resolve_tools`:

1. If `settings.tools` is empty, return an empty `Tools()` — the document, not the caller's catalog, decides.
2. Normalize `catalog` to a `Tools` (pass through if already one, else `Tools(catalog)`).
3. `return catalog.subset(definition.ref for definition in settings.tools)`, translating `ToolRegistryError` into `ConfigurationError` with `details["field"] = "agent.tools"` and the unresolved names.

`_resolve_named`:

1. For each definition, look up `definition.ref` in `available`.
2. On a miss, raise `ConfigurationError` with the definition's own document path in `details["field"]`, plus the ref and the sorted available keys.
3. Return the resolved objects in document order.

`_assert_tool_names_resolve`:

1. Collect `resolved.names()` into a set.
2. Gather referenced names: `getattr(contract, "tool_name", None)` over `settings.loop.output_contracts`; the keys of `settings.loop.tool_settings.max_calls_per_tool`; the entries of `settings.loop.allowed_tools`.
3. Raise on the first referenced name absent from the resolved set, naming the field it came from and the available tool names.

`_construct_agent`:

1. `kwargs = settings.to_agent_kwargs(tools=tools, middleware=middleware, context_items=context_items)`.
2. Overwrite `kwargs["output_schema"]` when an `output_schema` was injected.
3. Add `context_manager`, `tracer`, `permission_policy` when not `None`.
4. `from vidbyte.agents.base import BaseAgent` (function-local) and `return BaseAgent(**kwargs)`.
5. Translate a `TypeError`/`ValueError` from the constructor into `ConfigurationError` so this boundary raises one error type.

#### Edge Cases & Error Handling

| Condition | Behavior |
|---|---|
| `HarnessSpec` passed | `ConfigurationError`: harness documents not buildable; use `load_agent`. FR9. |
| Non-`base` `AgentType` | `ConfigurationError` naming the type. FR10. |
| Declared tool ref absent from catalog | `ConfigurationError`, `field=agent.tools`, unresolved names listed. FR3. |
| Declared middleware/context ref absent | `ConfigurationError` at the entry's own path. FR4/FR5. |
| Document declares no tools but caller supplies a catalog | Agent gets no tools. FR6. |
| `MinToolCallsById("x")` with no tool `x` | `ConfigurationError` — otherwise the agent burns `max_contract_rejections` on a permanently unsatisfiable contract, then fails at runtime. FR11. |
| `max_calls_per_tool` / `allowed_tools` naming an absent tool | Same. FR11. |
| `name=` fails validation (spaces, >64 chars, bad charset) | `ConfigurationError` from the re-run `__post_init__`, re-pointed at `build_agent.name`. FR8. |
| Duplicate tool names in the caller's catalog | `Tools.__init__` already raises `ToolRegistrationError`; left to surface as-is (caller's own construction error, not a document error). |
| `output_schema` in both document and injection | Injection wins; documented. |
| Called twice with the same settings | Two independent agents. FR13. |

**Documented caveat:** renaming settings that originated from a harness document decouples the running agent's name from the `spec_id` computed over that document. Called out in the docstring and README, not forbidden — it is the behavior the review comment asked for, and standalone agent documents have no `spec_id`.

### 6.2 Configuration package README

**File:** `vidbyte/config/README.md`
**Type:** Modified

Its current claim — "This folder deliberately stops at parsing and intrinsic validation. It does not import a `ref`, create a `BaseTool`…" — becomes false in one specific way and must be restated precisely: the package parses by default and builds only from **caller-supplied** components; it still never imports a name from a document. Adds `build_agent` to the loader's method list and a dated line to the Logs section, following the existing format.

### 6.3 Root README

**File:** `README.md`
**Type:** Modified

The YAML Configuration example currently ends with the manual `**settings.to_agent_kwargs(...)` incantation. It gains the one-line form beneath it:

```python
agent = loader.build_agent(settings, tools=my_tools, middleware={"logger": LoggingMiddleware()})
```

The manual form stays — it remains valid and is the escape hatch for callers who want the kwargs without construction.

---

## 7. Data Model Changes

N/A — no persisted schema, no new dataclass, no change to `AgentSettings`' fields. `dataclasses.replace` produces a new instance of the existing type.

---

## 8. API Changes

No HTTP surface. The Python API change is additive:

### 8.1 `YamlLoader.build_agent`

**Change type:** New

Signature as in §6.1. Raises `ConfigurationError` for every failure at this boundary.

No existing signature changes; `to_agent_kwargs` keeps working for callers who prefer it.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/yaml-loader-build-agent.md` | This design doc; first commit on the branch |
| MODIFY | `vidbyte/config/loader.py` | Add `build_agent` and its four private helpers; extend the Context Protocol Header |
| MODIFY | `vidbyte/config/README.md` | Correct the parse-only contract, list the new method, add a Logs entry |
| MODIFY | `README.md` | Show the one-line build form in the YAML Configuration section |

No file is deleted. `vidbyte/__init__.py` and `vidbyte/config/__init__.py` need no change — `YamlLoader` is already exported from both.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `dataclasses` (stdlib) | Python ≥3.11 | `replace()` for the validated `name` override | None — relies on `__post_init__` idempotency, verified across every `AgentSettings` validator |
| `vidbyte.agents.base.BaseAgent` | in-repo | The constructed object | Introduces `config → agents`; kept function-local so it can be reversed. Verified: `vidbyte.agents` imports nothing from `vidbyte.config`, so no cycle exists today |
| `vidbyte.tools.catalog.Tools` | in-repo | Tool ref resolution via `subset()` | Low — existing, already fail-closed |

No new third-party dependency; `pyproject.toml` is untouched.

---

## 11. Rollout & Deployment

- **Feature flags:** none. Additive method on an existing class.
- **Breaking change:** no. Nothing existing changes signature or behavior; `to_agent_kwargs` and all four current loader methods are untouched.
- **Deployment order:** single package, no coordination. Vidbyte consumes it only after re-pinning the SDK, and only for standalone agent documents until the harness-dialect PR lands.
- **Rollback:** revert the commit; nothing depends on the method until a caller adopts it.
- **CI gate:** `python scripts/run_ci.py` in full from the worktree before pushing, and `gh pr checks --watch` until green.

---

## 12. Open Questions

- [ ] **The duplicate `YamlLoader`.** `vidbyte/lib/config/loader.py` defines a second class of the same name returning `AgentDescriptor`/`HarnessDescriptor`/`EnvironmentDescriptor`, with its own `to_agent_kwargs` that disagrees with `AgentSettings`' (it drops `context_items` and `max_tool_rounds`) and stricter name rules (`^[a-z][a-z0-9-]*$` rejects `research_discovery`). This doc targets the publicly exported `vidbyte/config/loader.py`. Confirm that is the surviving one — if not, this method lands on the wrong class.
- [ ] **`llms.txt` is already wrong about this.** Its configuration section documents `from vidbyte import YamlLoader` as returning `AgentDescriptor` and calls `AgentSettings` "legacy"; the top-level export is in fact the `AgentSettings` loader. Left untouched here because correcting it means picking the winner above. Follow-up.
- [ ] **`name=` semantics.** Implemented as a validated **override** (§6.1), which is the only reading available once `build` consumes `load`'s output. If the intent was selection from a multi-agent document, that arrives with the harness-dialect PR and is additive.
- [ ] **No tests, by the invoked workflow.** A `BuildAgentTests` class in `tests/test_agent_settings_validation.py` covering the fail-closed paths (FR3, FR4, FR9, FR10, FR11) is the recommended immediate follow-up.

---

## 13. Alternatives Considered

### Alternative 1: A separate `AgentBuilder` class in `vidbyte/config/builder.py`

- **What:** class holding the component registries, with `YamlLoader.build_agent` delegating to it.
- **Why rejected:** the argument for it was that the harness path has no file path to load from, so a path-based method would be unusable there. Once `build` consumes `load`'s output, `AgentSettings` *is* the in-memory handle and that argument dissolves. A second public class in a namespace that already carries two `YamlLoader`s and two `HarnessSpec`s adds a "which one do I use" question for no capability. Extract it later if resolution grows a builtin-tool underlay, caching, or ref namespacing — extracting is cheap, deleting a public class is not.

### Alternative 2: Resolve refs by dotted-path import

- **What:** `ref: myapp.tools.SearchTool` resolved with `importlib`.
- **Why rejected:** turns any YAML file into arbitrary code execution, directly against the threat model `vidbyte/config/README.md` is built on. The document is untrusted input.

### Alternative 3: `build_agent(path)` taking a file path

- **What:** load and build in one call.
- **Why rejected:** the user's explicit framing is that build consumes load's output. It also re-reads the file on every call, so an agent could be constructed from YAML that no longer matches the `spec_id` recorded for the run. A path overload can be added later as sugar over this method.

### Alternative 4: `**overrides` passthrough instead of named injection parameters

- **What:** merge an arbitrary kwargs mapping over `to_agent_kwargs()`.
- **Why rejected:** reintroduces exactly the untyped dict-digging the originating review comment objects to, and lets a typo silently become an unknown `BaseAgent` kwarg. Named parameters for the four known non-serializable inputs keep the surface honest.

### Alternative 5: Default to the caller's whole catalog when a document declares no tools

- **What:** `tools: []` in the document means "everything the caller supplied".
- **Why rejected:** fails open. A document that grants no capabilities would silently grant all of them. The document is the allowlist (FR6).

---

END OF DESIGN DOC
