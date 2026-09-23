# Jev agent

This package owns Vidbyte's opinionated Jev agent. When specialist entries are configured, the Jev runtime makes one Choice decision from the current prompt and specialist descriptions before the task run. A qualified specialist handles the whole task; no match, a weak selection, or an unavailable decision uses the general agent.

- `settings.py` is the complete public configuration surface.
- `specialists.py` defines the validated `JevSpecialist` descriptor for a stable ID, matching description, and configured `BaseAgent` template.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `runtime.py` owns the fixed matching question, probability threshold policy, fail-open decision path, and isolated specialist execution; `RuntimeRegistry` resolves the `jev` runtime type to it.

Keep matching questions and actions internal. Do not add caller-defined Jev question lists or runtime replacement options. Specialist templates are forked per selected run, and a specialist execution failure is surfaced without retrying through the general agent.

See `docs/design/jev-agent-scaffold.md` and `skills/jev-agent/SKILL.md`.
