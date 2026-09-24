# Jev agent

This package owns Vidbyte's opinionated Jev agent. The initial scaffold runs the established linear model/tool loop and reserves a dedicated runtime seam for later Jev-backed capabilities.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `runtime.py` owns the fixed Jev policies: prompt alignment (`self_align=True`), then tool alignment (`tool_align=JevToolAlignmentSettings(...)`), then the inherited `AgentRuntime` loop; `RuntimeRegistry` resolves the `jev` runtime type to it.
- `alignment/` holds `JevAgentAlignment`. It edits this run's prompt, and it attaches existing catalog tools for this run. Every tool-alignment rule is a helper method on that class; the scout's tools only forward to it.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities such as preflight questions, dynamic compute, or multi-agent coordination, then keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-agent-alignment.md`, `docs/design/jev-tool-alignment.md`, and `skills/jev-agent/SKILL.md`.
