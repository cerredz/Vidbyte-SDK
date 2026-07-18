# Configuration

`vidbyte.config` is the public, declarative configuration boundary for Vidbyte SDK applications. `ConfigurationLoader` reads a versioned YAML document and produces settings data that application code can inspect, compose, and validate before it creates an agent.

This folder deliberately stops at parsing and intrinsic validation. It does not import a `ref`, create a `BaseTool` or `AgentMiddleware`, interpolate environment values, or read secrets. The application owns that resolution step because it knows which local capabilities are safe and available.

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
- `loader.py`: safe, versioned YAML parsing through `ConfigurationLoader`.
- `types.py`: validated declarative agent, tool, and middleware settings objects.

## Logs

- 2026-07-18: Created the public YAML parsing boundary and documented its parse-versus-resolution contract.
