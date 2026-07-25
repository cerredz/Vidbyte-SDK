# Configuration

`vidbyte.config` is the public, declarative configuration boundary for Vidbyte SDK applications. `YamlLoader` reads one YAML document and produces settings data that application code can inspect, compose, and validate before it creates an agent. There are exactly two document families: an **agent** document and a **harness** document. The central `load(path)` returns an `AgentSettings` subclass or a `HarnessSpec` — it needs no `kind` field, distinguishing a harness by its `schema_version`/`harness` envelope and treating every other document as an agent. `load_agent()` and `load_harness()` select one family explicitly; harness documents are delegated to `vidbyte.harnesses.HarnessConfigLoader`. `view_agent()` returns the structure a base agent document must follow. `build_agent(settings, ...)` takes what `load()` returned and constructs the live `BaseAgent`.

An agent document is polymorphic on a `type:` field (one of `AgentType`: `base`, `aggregate`, `continual_trace`, `handoff`, `multi`, `adversarial`). `type` defaults to `base`, the plain `BaseAgent`, which is fully supported. The composite and facade types are registered but not yet loadable from YAML; requesting one raises a specific error. Tools, middleware, and context items are **not** separate documents — they are `tools:`, `middleware:`, and `context_items:` lists of `{ref, options}` entries nested inside the agent. The `loop:` mapping is parsed into a real `AgentLoopSettings`, including its nested `tool_settings`, `tool_error_policy`, and `output_contracts` members. An agent may also declare `output_schema` (a JSON Schema object), `agent_metadata` (the name/description/use-cases that expose the agent as a tool), `trace_option` (continual tracing), and `max_tool_rounds`.

An agent's `system_prompt` may be inline text or a path to a local text file (`.md`, `.markdown`, `.txt`, `.text`, `.rst`); a value whose extension matches one of those is read as UTF-8, resolving relative paths against the YAML file's folder. The reference must stay **inside that folder** — it comes from the same untrusted document as every other field, so `../` escapes are rejected. This is the only field that reads the filesystem, and nothing fetches over the network.

## Validation

Every field validates itself on the dataclass, against the SDK's own sources of truth rather than a duplicated list:

- **`provider`** must be a `ModelProvider` (case-insensitive). **`model_name`** must be catalogued by `ProviderModelRegistry`, must belong to the declared provider, and must be a **text** model — a system prompt and an agentic loop do not compose with an image, video, or audio model. Model checking is strict: an uncatalogued name is rejected rather than passed through to the provider. Set `ProviderModelRegistry.STRICT_MODEL_VALIDATION = False` to accept a model released after this SDK version was pinned.
- **Bounds** exist wherever an unbounded value would fail later and less legibly: `name` ≤ 64 chars and restricted to the character set a provider accepts for a tool name, `system_prompt` ≤ 100,000 chars and free of control characters, `description` ≤ 1,024 chars, `model_name` ≤ 128 chars, `capabilities` ≤ 64 entries, `tools`/`middleware`/`context_items` ≤ 128 entries, and `metadata` nesting ≤ 32 levels.
- **`temperature`** must be finite (YAML `.nan` and `.inf` are real scalars) and within `0.0`–`2.0`, tightened to a provider's own ceiling where it is narrower.
- **Cross-field rules** are checked here rather than at agent construction, so the error names the document and field: a non-linear `runtime` rejects `middleware`, a non-default `algorithm`, and an enabled `trace_option`.
- **Secrets and interpolation** are refused anywhere in `metadata` or an entry's `options`, by key name (including `authorization`, `credential`, `private_key`, `access_key`, `session_token`, `cookie`) and by `${...}` syntax. There is deliberately **no credential seam**: a YAML-declared agent authenticates only from ambient process environment.

## Building

Parsing and building are separate steps, and the split is a security boundary rather than a style choice. **Loading never imports a `ref`, creates a `BaseTool` or `AgentMiddleware`, interpolates environment values, or reads secrets** — a document is untrusted text, so nothing in it may name code to execute. `build_agent()` constructs the agent, but every runtime component still comes from the **caller**, never from an import driven by document text:

```python
loader = YamlLoader()
settings = loader.load_agent("agent.yaml")           # parse + validate, no runtime objects
agent = loader.build_agent(settings, tools=my_catalog, middleware={"logger": LoggingMiddleware()})
```

The application still owns which local capabilities are safe and available; it just hands them over instead of assembling the agent itself. Four rules follow from that:

- **The document is the allowlist.** The built agent receives exactly the `tools:` it declares, resolved out of the supplied catalog by name. A document declaring no tools produces an agent with no tools, never the caller's whole catalog.
- **Unresolved references fail closed.** A declared `ref` the caller did not supply raises `ConfigurationError` naming the entry's document position and what was available, rather than silently dropping a capability the agent needs.
- **Unsatisfiable output-contract floors fail at build time.** A `MinToolCallsById` naming a tool the agent will not have can never be met, so it is rejected here instead of spending the run's whole rejection budget. Ceilings (`max_calls_per_tool`, `allowed_tools`) are not checked — an unmatched entry is inert, and either may legitimately name a tool attached after construction.
- **Non-serializable inputs are named parameters.** `context_manager`, `output_schema` (a Python class, which overrides the document's JSON Schema), `tracer`, and `permission_policy` are passed to `build_agent()` directly, because YAML cannot carry them. `name=` overrides the settings' name and is re-validated against the same rules the document faced; note that renaming settings that came from a harness document decouples the agent's name from that document's `spec_id`.

`build_agent()` accepts only `type: base` settings, and rejects a `HarnessSpec` with a directive error — harness documents carry their agent entries as open mappings in a different dialect, so building one agent out of a harness is not yet supported. Each call returns a fresh agent; nothing is cached.

The declarative dataclasses (`AgentSettings` and its subclasses, `ToolDefinition`, `MiddlewareDefinition`) live in `vidbyte.lib.dataclasses` alongside the SDK's other data contracts and are re-exported here; the `AgentType` discriminator lives in `vidbyte.lib.enums`. All field validation lives on the dataclasses.

## Non-Goals

- It does not replace executable agents in `vidbyte.agents`; `build_agent()` constructs one, it does not reimplement one.
- It does not replace agent-local tool catalogs in `vidbyte.tools`; tool references resolve through the catalog's own name lookup.
- It does not instantiate deterministic policies from `vidbyte.middleware`; the caller supplies middleware instances by ref.
- It does not select a provider or load credentials from `vidbyte.providers`.
- It does not add another shared internal contract layer beneath `vidbyte.lib`.
- It does not parse remote documents, fetch URLs, or access the network.
- It does not evaluate Python, custom YAML tags, templates, or environment interpolation.
- It does not validate application-specific option schemas for a referenced component.

## File Index

- `__init__.py`: public exports for the configuration namespace.
- `loader.py`: safe YAML parsing, agent/harness dispatch, and agent construction through `YamlLoader`.
- `types.py`: compatibility shim re-exporting the dataclasses from `vidbyte.lib.dataclasses.config`.

## Logs

- 2026-07-18: Created the public YAML parsing boundary and documented its parse-versus-resolution contract.
- 2026-07-23: Renamed the loader to `YamlLoader`; added the central `load()` dispatch, `load_harness()`, and `view_*()` structure methods; moved the declarative dataclasses to `vidbyte.lib.dataclasses` and the document vocabularies to `vidbyte.lib.enums`; and delegated validation to each dataclass with more specific errors.
- 2026-07-24: Allowed `system_prompt` to reference a local text file (`.md`/`.markdown`/`.txt`/`.text`/`.rst`), read as UTF-8 relative to the YAML file's folder via `YamlLoader._load_file`.
- 2026-07-24: Collapsed to two document families (agent, harness); removed the `version`/`kind` envelope and the standalone tools/middleware documents; made the agent document polymorphic on an `AgentType` discriminator (`base` fully supported, other types registered but not yet loadable); nested tools/middleware inside the agent; parsed `loop` into `AgentLoopSettings`; and validated `provider`/`model_name` against `ProviderModelRegistry`. See `docs/design/yaml-config-polymorphic-agents.md`.
- 2026-07-25: Added `YamlLoader.build_agent(settings, ...)`, which consumes what `load()`/`load_agent()` returned and constructs one `BaseAgent` from caller-supplied components. Tool refs resolve through `Tools.subset`, middleware and context-item refs through caller mappings, and both fail closed on a miss; an output-contract floor naming an absent tool is rejected at build time; `name=` is re-validated through `dataclasses.replace`. Loading still imports nothing a document names. See `docs/design/yaml-loader-build-agent.md`.
- 2026-07-24: Closed the gap between the declarative surface and `BaseAgent`'s construction inputs — added `output_schema`, `agent_metadata`, `trace_option`, `max_tool_rounds`, and `context_items`; made `loop.tool_settings`/`tool_error_policy`/`output_contracts` reachable from a document; and gated unknown `loop` keys. Backed model validation with the real runner catalog via new `ProviderModelRegistry` methods (`known_models`, `models_for_provider`, `provider_for_model`, `validate_provider_model_pair`), added per-field bounds, finite/ranged `temperature`, modality and provider-pair checks, config-time runtime conflict checks, a nesting-depth cap, an expanded secret-key list, positional error paths for nested entries, and containment for `system_prompt` file references.
