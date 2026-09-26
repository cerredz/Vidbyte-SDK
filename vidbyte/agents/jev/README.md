# Jev agent

This package owns Vidbyte's opinionated Jev agent. Its dedicated runtime can route a task to one registered specialist and run named Jev-backed preflights before the established linear model/tool loop.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `presets.py` defines the supported preflight names.
- `preflight.py` owns the internal preflight interface and `JevPreflightTools`, which asks one batched Jev request whether each configured tool may help.
- `specialists.py` owns `JevSpecialistRouter`: the one fixed Choice question, the probability threshold policy, the fail-open decision path, and isolated specialist execution.
- `prompts.py` is the registry for every Jev question text; the text itself lives in Markdown files under `vidbyte/prompts/jev/`.
- `runtime.py` hands the run to the router when specialists are configured, then applies selected tool catalogs before delegating to `AgentRuntime`; `RuntimeRegistry` resolves the `jev` runtime type to it.

The `JevSpecialist` record (a stable ID, a matching description, and a configured `BaseAgent` template) and its catalog limits live in `vidbyte/lib/dataclasses/jev.py` and `vidbyte/lib/constants/jev.py`. When `agents` is set, the router asks Jev once, using only the current prompt and the specialist descriptions. A qualified specialist handles the whole task; no match, a weak selection, or an unavailable decision uses the general agent. Specialist templates are forked per selected run, and a specialist execution failure is surfaced without retrying through the general agent.

Enable tool selection with `JevPreflightPreset.TOOL_SELECTOR`. `tool_selector_threshold` defaults to `0.20` and accepts finite probabilities from `0.0` through `1.0` inclusive. If Jev is unavailable or returns incomplete answers, the run keeps the full configured tool catalog.

Do not add a generic `decisions` collection, caller-defined Jev question lists, or a runtime replacement option. Add named, validated settings for product capabilities and keep their internal questions and actions inside this package, with question text in `vidbyte/prompts/jev/`.

See `docs/design/jev-agent-scaffold.md` and `skills/jev-agent/SKILL.md`.
