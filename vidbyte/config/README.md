# Configuration

`vidbyte.config` is the public, declarative configuration boundary for Vidbyte SDK applications. `YamlLoader` reads one YAML document and produces settings data that application code can inspect, compose, and validate before it creates an agent. There are exactly two document families: an **agent** document and a **harness** document. The central `load(path)` returns an `AgentSettings` subclass or a `HarnessSpec` — it needs no `kind` field, distinguishing a harness by its `schema_version`/`harness` envelope and treating every other document as an agent. `load_agent()` and `load_harness()` select one family explicitly; harness documents are delegated to `vidbyte.harnesses.HarnessConfigLoader`. `view_agent()` returns the structure a base agent document must follow.

An agent document is polymorphic on a `type:` field (one of `AgentType`: `base`, `aggregate`, `continual_trace`, `handoff`, `multi`, `adversarial`). `type` defaults to `base`, the plain `BaseAgent`, which is fully supported. The composite and facade types are registered but not yet loadable from YAML; requesting one raises a specific error. Tools and middleware are **not** separate documents — they are `tools:` and `middleware:` lists of `{ref, options}` entries nested inside the agent. The `loop:` mapping is parsed into a real `AgentLoopSettings`, and `provider`/`model_name` are validated against the canonical `ProviderModelRegistry`.

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
- 2026-07-24: Collapsed to two document families (agent, harness); removed the `version`/`kind` envelope and the standalone tools/middleware documents; made the agent document polymorphic on an `AgentType` discriminator (`base` fully supported, other types registered but not yet loadable); nested tools/middleware inside the agent; parsed `loop` into `AgentLoopSettings`; and validated `provider`/`model_name` against `ProviderModelRegistry`. See `docs/design/yaml-config-polymorphic-agents.md`.
