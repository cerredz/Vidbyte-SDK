# Configuration

`vidbyte.config` is the public, declarative configuration boundary for Vidbyte SDK applications. `YamlLoader` reads a versioned YAML document and produces settings data that application code can inspect, compose, and validate before it creates an agent. Its central `load(path)` dispatches on the document's declared kind, while `load_agent()`, `load_tools()`, `load_middleware()`, and `load_harness()` select one kind explicitly; harness documents are delegated to `vidbyte.harnesses.HarnessConfigLoader`. Each `view_*()` method returns the structure a document of that kind must follow.

This folder deliberately stops at parsing and intrinsic validation. It does not import a `ref`, create a `BaseTool` or `AgentMiddleware`, interpolate environment values, or read secrets. The application owns that resolution step because it knows which local capabilities are safe and available. The declarative dataclasses (`AgentSettings`, `ToolDefinition`, `MiddlewareDefinition`) live in `vidbyte.lib.dataclasses` alongside the SDK's other data contracts and are re-exported here; the fixed document vocabularies (`ConfigKind`, `AgentLoopField`) live in `vidbyte.lib.enums`.

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
- `loader.py`: safe, versioned YAML parsing and kind dispatch through `YamlLoader`.
- `types.py`: compatibility shim re-exporting the dataclasses from `vidbyte.lib.dataclasses.config`.

## Logs

- 2026-07-18: Created the public YAML parsing boundary and documented its parse-versus-resolution contract.
- 2026-07-23: Renamed the loader to `YamlLoader`; added the central `load()` dispatch, `load_harness()`, and `view_*()` structure methods; moved the declarative dataclasses to `vidbyte.lib.dataclasses` and the document vocabularies to `vidbyte.lib.enums`; and delegated validation to each dataclass with more specific errors.
