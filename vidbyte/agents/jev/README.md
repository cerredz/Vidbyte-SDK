# Jev agent

This package owns Vidbyte's opinionated Jev agent. The initial scaffold runs the established linear model/tool loop and reserves a dedicated runtime seam for later Jev-backed capabilities.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `runtime.py` owns fixed Jev policies around the inherited `AgentRuntime` loop; `RuntimeRegistry` resolves the `jev` runtime type to it.
- `documentation/` owns the documentation lookup (`JevAgentSettings(documentation="exa")`). `JevDocumentation` is a `BaseAgent` subclass: it asks the fixed questions in `documentation/questions.py` in one Jev call, and when the highest answer reaches the threshold it runs its own loop with the chosen provider's search tool. Only links that search returned are kept, and `JevRuntime` appends them to this run's system prompt.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities such as preflight questions, dynamic compute, or multi-agent coordination, then keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md` and `skills/jev-agent/SKILL.md`.
