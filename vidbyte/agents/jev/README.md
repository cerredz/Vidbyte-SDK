# Jev agent

This package owns Vidbyte's opinionated Jev agent. Its dedicated runtime can run named Jev-backed preflights before the established linear model/tool loop.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `preflight.py` owns the internal preflight interface, `JevPreflightTools`, which asks one batched Jev request whether each configured tool may help, and `JevPreflightSecurity`, which maps the security answers to flags and an action.
- `runtime.py` runs the security gate, the contained run, and tool selection before delegating to `AgentRuntime`; `RuntimeRegistry` resolves the `jev` runtime type to it.

Preset names, security actions, and categories live in `vidbyte/lib/enums/jev.py`; preset validation lives in `vidbyte/lib/jev/presets.py`; the fixed security questions and `JevPreflightRegistry` live in `vidbyte/lib/jev/preflight/`.

Enable tool selection with `JevPreflightPreset.TOOL_SELECTOR`. `tool_selector_threshold` defaults to `0.20` and accepts finite probabilities from `0.0` through `1.0` inclusive. If Jev is unavailable or returns incomplete answers, the run keeps the full configured tool catalog.

Enable the sensitive-data check with `JevPreflightPreset.SECURITY` and choose `security_action`: `block` (default), `pause`, `report`, or `contain`. The result is `metadata["jev_security"]`.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities and keep their internal questions and actions out of the public API.

See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-preflight-sensitive-data.md`, and `skills/jev-agent/SKILL.md`.
