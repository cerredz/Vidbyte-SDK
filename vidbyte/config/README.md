# Configuration

`vidbyte.config` is the public, declarative configuration boundary for Vidbyte SDK applications. `YamlLoader` reads one YAML document and produces settings data that application code can inspect, compose, and validate before it creates an agent. There are exactly two document families: an **agent** document and a **harness** document. The central `load(path)` returns an `AgentSettings` subclass or a `HarnessSpec` — it needs no `kind` field, distinguishing a harness by its `schema_version`/`harness` envelope and treating every other document as an agent. `load_agent()` and `load_harness()` select one family explicitly; harness documents are delegated to `vidbyte.harnesses.HarnessConfigLoader`. `view_agent()` returns the structure a base agent document must follow.

An agent document is polymorphic on a `type:` field (one of `AgentType`: `base`, `aggregate`, `continual_trace`, `handoff`, `multi`, `adversarial`). `type` defaults to `base`, the plain `BaseAgent`, which is fully supported. The composite and facade types are registered but not yet loadable from YAML; requesting one raises a specific error. Tools, middleware, and context items are **not** separate documents — they are `tools:`, `middleware:`, and `context_items:` lists of `{ref, options}` entries nested inside the agent. The `loop:` mapping is parsed into a real `AgentLoopSettings`, including its nested `tool_settings`, `tool_error_policy`, and `output_contracts` members. An agent may also declare `output_schema` (a JSON Schema object), `agent_metadata` (the name/description/use-cases that expose the agent as a tool), `trace_option` (continual tracing), and `max_tool_rounds`.

An agent's `system_prompt` may be inline text or a path to a local text file (`.md`, `.markdown`, `.txt`, `.text`, `.rst`); a value whose extension matches one of those is read as UTF-8, resolving relative paths against the YAML file's folder. The reference must stay **inside that folder** — it comes from the same untrusted document as every other field, so `../` escapes are rejected. This is the only field that reads the filesystem, and nothing fetches over the network.

## Validation

Every field validates itself on the dataclass, against the SDK's own sources of truth rather than a duplicated list:

- **`provider`** must be a `ModelProvider` (case-insensitive). **`model_name`** must be catalogued by `ProviderModelRegistry`, must belong to the declared provider, and must be a **text** model — a system prompt and an agentic loop do not compose with an image, video, or audio model. Model checking is strict: an uncatalogued name is rejected rather than passed through to the provider. Set `ProviderModelRegistry.STRICT_MODEL_VALIDATION = False` to accept a model released after this SDK version was pinned.
- **Bounds** exist wherever an unbounded value would fail later and less legibly: `name` ≤ 64 chars and restricted to the character set a provider accepts for a tool name, `system_prompt` ≤ 100,000 chars and free of control characters, `description` ≤ 1,024 chars, `model_name` ≤ 128 chars, `capabilities` ≤ 64 entries, `tools`/`middleware`/`context_items` ≤ 128 entries, and `metadata` nesting ≤ 32 levels.
- **`temperature`** must be finite (YAML `.nan` and `.inf` are real scalars) and within `0.0`–`2.0`, tightened to a provider's own ceiling where it is narrower.
- **Cross-field rules** are checked here rather than at agent construction, so the error names the document and field: a non-linear `runtime` rejects `middleware`, a non-default `algorithm`, and an enabled `trace_option`.
- **Secrets and interpolation** are refused anywhere in `metadata` or an entry's `options`, by key name (including `authorization`, `credential`, `private_key`, `access_key`, `session_token`, `cookie`) and by `${...}` syntax. There is deliberately **no credential seam**: a YAML-declared agent authenticates only from ambient process environment.

This folder deliberately stops at parsing and intrinsic validation. It does not import a `ref`, create a `BaseTool` or `AgentMiddleware`, interpolate environment values, or read secrets. The application owns that resolution step because it knows which local capabilities are safe and available. The declarative dataclasses (`AgentSettings` and its subclasses, `ToolDefinition`, `MiddlewareDefinition`) live in `vidbyte.lib.dataclasses` alongside the SDK's other data contracts and are re-exported here; the `AgentType` discriminator lives in `vidbyte.lib.enums`. All field validation lives on the dataclasses.

## Non-Goals

- It does not replace executable agents in `vidbyte.agents`.
- It does not replace agent-local tool catalogs in `vidbyte.tools`.
- It does not instantiate deterministic policies from `vidbyte.middleware`.
- It does not select a provider or load credentials from `vidbyte.providers`.
- It does not add another shared internal contract layer beneath `vidbyte.lib`.
- It does not parse remote documents, fetch URLs, or access the network.
- It does not evaluate Python, custom YAML tags, templates, or environment interpolation.
- It does not validate application-specific option schemas for a referenced component.

## File Index

- `__init__.py`: public exports for the configuration namespace.
- `loader.py`: safe YAML parsing and agent/harness dispatch through `YamlLoader`.
- `types.py`: compatibility shim re-exporting the dataclasses from `vidbyte.lib.dataclasses.config`.

## Logs

- 2026-07-18: Created the public YAML parsing boundary and documented its parse-versus-resolution contract.
- 2026-07-23: Renamed the loader to `YamlLoader`; added the central `load()` dispatch, `load_harness()`, and `view_*()` structure methods; moved the declarative dataclasses to `vidbyte.lib.dataclasses` and the document vocabularies to `vidbyte.lib.enums`; and delegated validation to each dataclass with more specific errors.
- 2026-07-24: Allowed `system_prompt` to reference a local text file (`.md`/`.markdown`/`.txt`/`.text`/`.rst`), read as UTF-8 relative to the YAML file's folder via `YamlLoader._load_file`.
- 2026-07-24: Collapsed to two document families (agent, harness); removed the `version`/`kind` envelope and the standalone tools/middleware documents; made the agent document polymorphic on an `AgentType` discriminator (`base` fully supported, other types registered but not yet loadable); nested tools/middleware inside the agent; parsed `loop` into `AgentLoopSettings`; and validated `provider`/`model_name` against `ProviderModelRegistry`. See `docs/design/yaml-config-polymorphic-agents.md`.
- 2026-07-24: Closed the gap between the declarative surface and `BaseAgent`'s construction inputs — added `output_schema`, `agent_metadata`, `trace_option`, `max_tool_rounds`, and `context_items`; made `loop.tool_settings`/`tool_error_policy`/`output_contracts` reachable from a document; and gated unknown `loop` keys. Backed model validation with the real runner catalog via new `ProviderModelRegistry` methods (`known_models`, `models_for_provider`, `provider_for_model`, `validate_provider_model_pair`), added per-field bounds, finite/ranged `temperature`, modality and provider-pair checks, config-time runtime conflict checks, a nesting-depth cap, an expanded secret-key list, positional error paths for nested entries, and containment for `system_prompt` file references.
