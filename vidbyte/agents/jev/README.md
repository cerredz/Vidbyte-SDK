# Jev agent

This package owns Vidbyte's opinionated Jev agent. Its dedicated runtime can route a task to one registered specialist and run named Jev-backed preflights before the established linear model/tool loop.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `gate/` holds the gate for fixed-question presets. `JevPreflightGate` combines every enabled preset's questions into one Jev request, scores each preset with `DecisionModelRunner.score_noul`, and its `pass_` match statement acts on the outcomes and returns whether the generative agent runs. `JevClarificationAgent` returns structured clarifying questions, each with a few recommended answers, when the request is unclear.
- `specialists.py` owns `JevSpecialistRouter`: the one fixed Choice question, the probability threshold policy, the fail-open decision path, and isolated specialist execution.
- `preflight.py` holds the tool selector (`JevPreflightTools`), which keeps its own path in the runtime.
- `prompts.py` is the registry (`JevPrompt`, `JevPrompts`) for the question text of the questions built at run time (specialist routing and the tool selector); the text itself lives in Markdown files under `vidbyte/prompts/jev/`.
- `response.py` defines `JevResponse`, the only writer of the `JevAgentResponse` record exposed as `JevAgent.response`.
- `runtime.py` calls the gate before anything else and returns the gate's response when it closes, then hands the run to the router when specialists are configured, then applies the tool selector when it is enabled before the inherited `AgentRuntime` loop; `RuntimeRegistry` resolves the `jev` runtime type to it.

`agent.py` builds the gate, the specialist router, and the response writer at construction and passes them to the runtime. Fixed preflight question text lives in `vidbyte/lib/jev/`: `presets.py` (`JevPresets`) owns the flags a user can enable in `JevAgentSettings.preflight` and the questions each fixed-question flag asks, and `preflight/` holds one dataclass per question plus `JevPreflightRegistry`. The flag and question-key enums are in `vidbyte/lib/enums/jev.py`, and the records are in `vidbyte/lib/dataclasses/jev.py`.

The `JevSpecialist` record (a stable ID, a matching description, and a configured `BaseAgent` template) and its catalog limits live in `vidbyte/lib/dataclasses/jev.py` and `vidbyte/lib/constants/jev.py`. When `agents` is set, the router asks Jev once, after the gate passes, using only the current prompt and the specialist descriptions. A qualified specialist handles the whole task; no match, a weak selection, or an unavailable decision uses the general agent. `agent.response.routing` (`JevSpecialistRouting`) records which agent ran and why. Specialist templates are forked per selected run, and a specialist execution failure is surfaced without retrying through the general agent.

Enable request clarity checks with `JevPreflightPreset.CLARITY`. When the request is unclear, the run stops before the generative agent starts, `agent.response.clarification` holds the questions and their recommended answers, and the reply content is those questions as a numbered list.

Enable tool selection with `JevPreflightPreset.TOOL_SELECTOR`. `tool_selector_threshold` defaults to `0.20` and accepts finite probabilities from `0.0` through `1.0` inclusive. If Jev is unavailable or returns incomplete answers, the run keeps the full configured tool catalog, and the reply metadata reports the selection under `jev_tool_selector`. After each run, `agent.response.results` holds one outcome per enabled fixed-question preset.

Do not add a generic `decisions` collection, caller-defined Jev question lists, or a runtime replacement option. Add named, validated settings for product capabilities and keep their internal questions and actions inside this package, with fixed preflight questions in `vidbyte/lib/jev/preflight/` and run-built question text in `vidbyte/prompts/jev/`.

See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-preflight-clarity.md`, `docs/design/jev-tool-selector.md`, `docs/design/jev-specialist-routing.md`, and `skills/jev-agent/SKILL.md`.
