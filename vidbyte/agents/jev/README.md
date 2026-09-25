# Jev agent

This package owns Vidbyte's opinionated Jev agent. The initial scaffold runs the established linear model/tool loop and reserves a dedicated runtime seam for later Jev-backed capabilities.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `runtime.py` runs `JevPreflight` before the inherited `AgentRuntime` loop, returns the clarifying question when a preset fails, and attaches the `JevResponse` under `jev_response`; `RuntimeRegistry` resolves the `jev` runtime type to it.

Preflight itself lives in `vidbyte/lib/jev/`: `presets.py` (`JevPresets`) owns the flags a user can enable in `JevAgentSettings.preflight` and the questions each flag asks, and `preflight/` holds one dataclass per question plus `JevPreflight`, the registry that validates, combines, runs, and scores them. The flag and question-key enums are in `vidbyte/lib/enums/jev.py`, and the records (`JevPreflightQuestion`, `JevPresetDefinition`, `JevPresetResult`, `JevResponse`) are in `vidbyte/lib/dataclasses/jev.py`.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities such as preflight questions, dynamic compute, or multi-agent coordination, then keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md` and `skills/jev-agent/SKILL.md`.
