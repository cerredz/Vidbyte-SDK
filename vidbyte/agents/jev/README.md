# Jev agent

This package owns Vidbyte's opinionated Jev agent. Its dedicated runtime can run named Jev-backed preflights before the established linear model/tool loop, and named done checks at every finish attempt.

- `settings.py` is the complete public configuration surface.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `gate/` holds the gate for fixed-question presets. `JevPreflightGate` combines every enabled preset's questions into one Jev request, scores each preset with `DecisionModelRunner.score_noul`, and its `pass_` match statement acts on the outcomes and returns whether the generative agent runs. `JevClarificationAgent` returns structured clarifying questions, each with a few recommended answers, when the request is unclear.
- `preflight.py` holds the tool selector (`JevPreflightTools`), which keeps its own path in the runtime.
- `response.py` defines `JevResponse`, the only writer of the `JevAgentResponse` record exposed as `JevAgent.response`.
- `done/` holds the gate for done checks. `JevDoneGate` builds the run state before the loop, reviews every finish attempt through `AgentRuntime.review_finish_attempt`, and writes the `JevRunReport` through `JevResponse`. `run_state.py` holds `JevRunState` (goal, objective, mission, what_not_to_do, constraints, proposed_plan, plus sections), `JevRunHandoff`, `JevRunReport`, and the `JevRunSection` contract every done check implements; `builders.py` holds the two tool-free generative builders (`JevRunStateAgent` and `JevRunHandoffAgent`); `event_log.py` numbers the run's events from the loop state; `required_sequence.py` is done check #15.
- `runtime.py` calls the preflight gate before the inherited `AgentRuntime` loop and returns the gate's response when it closes, then starts the done gate and applies the tool selector when it is enabled, and hands every finish attempt to the done gate; `RuntimeRegistry` resolves the `jev` runtime type to it.

`agent.py` builds both gates and the response writer at construction and passes them to the runtime. Question text lives in `vidbyte/lib/jev/`: `presets.py` (`JevPresets`) owns the flags a user can enable in `JevAgentSettings.preflight` and the questions each fixed-question flag asks, and `preflight/` holds one dataclass per question plus `JevPreflightRegistry`. The flag and question-key enums are in `vidbyte/lib/enums/jev.py`, and the records are in `vidbyte/lib/dataclasses/jev.py`.

Enable request clarity checks with `JevPreflightPreset.CLARITY`. When the request is unclear, the run stops before the generative agent starts, `agent.response.clarification` holds the questions and their recommended answers, and the reply content is those questions as a numbered list.

Enable tool selection with `JevPreflightPreset.TOOL_SELECTOR`. `tool_selector_threshold` defaults to `0.20` and accepts finite probabilities from `0.0` through `1.0` inclusive. If Jev is unavailable or returns incomplete answers, the run keeps the full configured tool catalog, and the reply metadata reports the selection under `jev_tool_selector`. After each run, `agent.response.results` holds one outcome per enabled fixed-question preset.

Enable the required-sequence done check with `required_sequence=True`. The run state lists the ordered stages the request itself requires; a finish attempt is accepted only when the recorded run shows every stage done, in order. After each run, `agent.response.run_report` holds the run state, every finish review, and the builders' usage.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities and keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-preflight-clarity.md`, `docs/design/jev-tool-selector.md`, `docs/design/jev-required-sequence.md`, and `skills/jev-agent/SKILL.md`.
