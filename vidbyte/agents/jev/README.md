# Jev agent

This package owns Vidbyte's opinionated Jev agent. The runtime can run an opt-in sensitive-data security preflight before entering the established linear model/tool loop.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `presets.py` owns the fixed security questions, `Preset.Security` settings, and the `on_detected` actions.
- `response.py` holds category flags and aggregate security state without retaining request text.
- `runtime.py` runs the preflight and maps its result to block, pause, or report behavior; `RuntimeRegistry` resolves the `jev` runtime type to it.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities such as preflight questions, dynamic compute, or multi-agent coordination, then keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-preflight-sensitive-data.md`, and `skills/jev-agent/SKILL.md`.
