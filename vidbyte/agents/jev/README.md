# Jev agent

This package owns Vidbyte's opinionated Jev agent. Its dedicated runtime can run named Jev-backed preflights before the established linear model/tool loop.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `presets.py` defines the supported preflight names.
- `preflight.py` owns the internal preflight interface and `JevPreflightTools`, which asks one batched Jev request whether each configured tool may help.
- `runtime.py` applies selected tool catalogs before delegating to `AgentRuntime`; `RuntimeRegistry` resolves the `jev` runtime type to it.

Enable tool selection with `JevPreflightPreset.TOOL_SELECTOR`. `tool_selector_threshold` defaults to `0.20` and accepts finite probabilities from `0.0` through `1.0` inclusive. If Jev is unavailable or returns incomplete answers, the run keeps the full configured tool catalog.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities and keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md` and `skills/jev-agent/SKILL.md`.
