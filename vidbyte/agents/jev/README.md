# Jev agent

This package owns Vidbyte's opinionated Jev agent. The initial scaffold runs the established linear model/tool loop and reserves a dedicated runtime seam for later Jev-backed capabilities.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `runtime.py` owns fixed Jev policies around the inherited linear loop; `RuntimeRegistry` resolves the `jev` runtime type to it.
- `presets.py` names the done-criteria presets (`JevPresets`) accepted by `JevAgent(settings, done_criteria=...)`.
- `motivating_case/` implements `JevPresets.MotivatingCase`: state builder, event ledger, handoff, code checks, Jev questions, policy, and builder sub-agents.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities such as preflight questions, dynamic compute, or multi-agent coordination, then keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-motivating-case.md`, and `skills/jev-agent/SKILL.md`.
