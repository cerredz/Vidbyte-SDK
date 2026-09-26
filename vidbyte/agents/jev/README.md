# Jev agent

This package owns Vidbyte's opinionated Jev agent. Its dedicated runtime can run named Jev-backed preflights before the established linear model/tool loop.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `gate/` holds the gate for fixed-question presets. `JevPreflightGate` combines every enabled preset's questions into one Jev request, scores each preset with `DecisionModelRunner.score_noul`, and its `pass_` match statement acts on the outcomes and returns whether the generative agent runs. `JevClarificationAgent` returns structured clarifying questions, each with a few recommended answers, when the request is unclear.
- `preflight.py` holds the tool selector (`JevPreflightTools`), which keeps its own path in the runtime.
- `response.py` defines `JevResponse`, the only writer of the `JevAgentResponse` record exposed as `JevAgent.response`.
- `runtime.py` calls the gate before the inherited `AgentRuntime` loop and returns the gate's response when it closes, then applies the tool selector when it is enabled; `RuntimeRegistry` resolves the `jev` runtime type to it.

`agent.py` builds the gate and the response writer at construction and passes them to the runtime. Question text lives in `vidbyte/lib/jev/`: `presets.py` (`JevPresets`) owns the flags a user can enable in `JevAgentSettings.preflight` and the questions each fixed-question flag asks, and `preflight/` holds one dataclass per question plus `JevPreflightRegistry`. The flag and question-key enums are in `vidbyte/lib/enums/jev.py`, and the records are in `vidbyte/lib/dataclasses/jev.py`.

Enable request clarity checks with `JevPreflightPreset.CLARITY`. When the request is unclear, the run stops before the generative agent starts, `agent.response.clarification` holds the questions and their recommended answers, and the reply content is those questions as a numbered list.

Enable tool selection with `JevPreflightPreset.TOOL_SELECTOR`. `tool_selector_threshold` defaults to `0.20` and accepts finite probabilities from `0.0` through `1.0` inclusive. If Jev is unavailable or returns incomplete answers, the run keeps the full configured tool catalog, and the reply metadata reports the selection under `jev_tool_selector`. After each run, `agent.response.results` holds one outcome per enabled fixed-question preset.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities and keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-preflight-clarity.md`, `docs/design/jev-tool-selector.md`, and `skills/jev-agent/SKILL.md`.
