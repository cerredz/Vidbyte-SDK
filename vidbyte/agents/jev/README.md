# Jev agent

This package owns Vidbyte's opinionated Jev agent. The initial scaffold runs the established linear model/tool loop and reserves a dedicated runtime seam for later Jev-backed capabilities.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `runtime.py` runs the inherited linear loop and, when a done check is enabled, orchestrates it: build the run state, add each active section's instructions to the system prompt, and review every finish attempt through `AgentRuntime.review_finish_attempt`. `RuntimeRegistry` resolves the `jev` runtime type to it.
- `run_state.py` holds `JevRunState` (goal, objective, mission, what_not_to_do, constraints, proposed_plan, plus sections), `JevRunHandoff`, the `JevRunReport` attached to results, and the `JevRunSection` contract every done check implements.
- `builders.py` holds the two generative builders: `JevRunStateAgent` (once, before the loop) and `JevRunHandoffAgent` (at each finish attempt). Both are tool-free `BaseAgent` subclasses with strict output schemas.
- `event_log.py` numbers the run's events from the loop state for the handoff builder. No middleware is involved.
- `required_sequence.py` is done check #15 (`required_sequence=True`): the stages the request requires, in order.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities such as preflight questions, dynamic compute, or multi-agent coordination, then keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md` and `skills/jev-agent/SKILL.md`.
