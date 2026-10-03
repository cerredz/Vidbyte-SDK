# Jev agent

This package owns Vidbyte's opinionated Jev agent. Its dedicated runtime can run named Jev-backed preflights before the established linear model/tool loop.

- `settings.py` is the complete public configuration surface: `JevAgentSettings` for the main agent and its `JevSpecialist` candidates, and `JevRuntimeSettings` for Jev's decision model, preflight flags, continuation settings (`JevContinualSettings`: done checks and their limits), and tool-selector threshold.
- `agent.py` maps those settings into `BaseAgent` with the `jev` runtime type (`AgentRuntimeType.JEV`).
- `gate/` holds the gate for fixed-question presets. `JevPreflightGate` combines every enabled preset's questions into one Jev request, scores each preset with `DecisionModelHelper`, and its `pass_` match statement acts on the outcomes and returns whether the generative agent runs. When `JevAgentSettings.agents` is set, the same request carries one Choice question over the specialists, and the gate records the one Jev ranked first. `JevClarificationAgent` returns structured clarifying questions, each with a few recommended answers, when the request is unclear.
- `done/` holds the done checks: `JevRunState` writes the run state from the request before the main loop and runs every enabled check when the main agent tries to finish, and `JevHandoff` compiles the evidence those checks judge from the main agent's context window.
- `continuation/` holds the continuations the runtime calls at every finish attempt: `JevContinuation` (`should_continue`, `continue_`) and `JevDoneContinuation`, which sends the main agent back with the request, run state, handoff, and failed Jev questions when a done check fails.
- `preflight.py` holds the tool selector (`JevPreflightTools`), which keeps its own path in the runtime.
- `response.py` defines `JevResponse`, the only writer of the `JevAgentResponse` record exposed as `JevAgent.response`.
- `runtime.py` calls the gate before the inherited `AgentRuntime` loop and returns the gate's response when it closes, runs the chosen specialist's own agent when the gate chose one, and otherwise applies the tool selector when it is enabled; `RuntimeRegistry` resolves the `jev` runtime type to it.

`agent.py` builds the gate and the response writer at construction and passes them to the runtime. Question text lives in `vidbyte/lib/jev/`: `presets.py` (`JevPresets`) owns the flags a user can enable in `JevRuntimeSettings.preflight` and the questions each fixed-question flag asks, and `preflight/` holds one dataclass per question, the specialist question, and `JevPreflightRegistry`. The flag and question-key enums are in `vidbyte/lib/enums/jev.py`, and the records are in `vidbyte/lib/dataclasses/jev.py`.

Enable request clarity checks with `JevPreflightPreset.CLARITY`. When the request is unclear, the run stops before the generative agent starts, `agent.response.clarification` holds the questions and their recommended answers, and the reply content is those questions as a numbered list.

Enable tool selection with `JevPreflightPreset.TOOL_SELECTOR`. `tool_selector_threshold` defaults to `0.20` and accepts finite probabilities from `0.0` through `1.0` inclusive. If Jev is unavailable or returns incomplete answers, the run keeps the full configured tool catalog, and the reply metadata reports the selection under `jev_tool_selector`. After each run, `agent.response.results` holds one outcome per enabled fixed-question preset.

Hand whole tasks to specialists with `JevAgentSettings.agents`: each `JevSpecialist` pairs a title and a scope description with the `BaseAgent` that runs the task when Jev picks it. Jev may also pick `none`, and a missing or failed answer counts as `none`; either way the main agent runs. `agent.response.specialist` names the specialist that ran, and a chosen specialist runs through its own agent, so this agent's tool selector does not filter its tools.

Enable done checks with `JevRuntimeSettings(continual=JevContinualSettings(checks=...))`. With `JevDoneCheck.MULTI_PART`, `JevRunState` lists the separate deliverables the request asks for, and each time the main agent tries to finish, `JevHandoff` compiles the evidence for each one and Jev judges, in one request holding every enabled check's questions, whether each was produced in full. A deliverable below `JEV_MULTI_PART_THRESHOLD` sends the main agent back to work in the same loop, at most `JevContinualSettings.max_continuations` times (default `JEV_DONE_MAX_CONTINUATIONS`); every failure fails open. `agent.response.run_state`, `handoff`, `done`, and `continuations` report the outcome. The questions live in `vidbyte/lib/jev/done/`.

`JevDoneCheck.REPORT_ACTION_ALIGNMENT` is an opt-in check for drift between an explicit plan in an earlier main-agent response, recorded execution, and the final account. It checks only plan items that the final account refers to or implies were carried out, and uses the original request to distinguish required outcomes from optional plan steps. A changed or abandoned plan can pass when the final account accurately describes it and the request does not still require the result. Each eligible item is checked in the same batched Jev request as any other enabled checks; an unsupported account goes back to the main agent with only that item and its missing evidence or required work.

```python
from vidbyte import JevAgent, JevAgentSettings, JevContinualSettings, JevDoneCheck, JevRuntimeSettings

agent = JevAgent(
    JevAgentSettings(
        name="researcher",
        system_prompt="Research carefully and report what you actually did.",
        provider="openai",
        model_name="gpt-4.1",
    ),
    JevRuntimeSettings(
        continual=JevContinualSettings(
            checks=(JevDoneCheck.REPORT_ACTION_ALIGNMENT,),
            max_continuations=2,
        ),
    ),
)
reply = agent.run("Compare the two approaches and recommend one.")
alignment = agent.response.done[JevDoneCheck.REPORT_ACTION_ALIGNMENT]
print(alignment.passed, alignment.incomplete)
```

`agent.response.handoff.report_action_alignment` contains the frozen plan, execution, final-account, relevance, evidence, and missing records for that finish attempt. `JevDoneCheck.CLAIMS` remains the separate check for individual factual assertions in the final answer.
Add `JevDoneCheck.TARGET_OUTCOME` when the task asks for a result on a target beyond producing the answer or another requested output. The run-state records the requested outcome, actual target, scope, and completion criterion; at each finish attempt, the handoff separates observed proxy milestones from direct evidence about that target. Jev checks whether the evidence demonstrates the requested result on the actual target at the requested scope. Requests with no separate, well-defined target outcome produce no target-outcome items and pass this check without a Jev question. Enable it alongside other checks, for example `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART, JevDoneCheck.TARGET_OUTCOME)))`.
With `JevDoneCheck.PROBLEMS_RESOLVED`, the handoff derives one item for every problem observed during that run and one required item for completion of the original request after repairs. Jev judges every item in the same combined request; a failed problem sends the main agent back to repair and revalidate it, then return to the original request and finish remaining work. The check is opt-in, runs in the same loop, respects the same continuation cap, and fails open when evidence or Jev is unavailable.

Do not add a generic `decisions` collection or runtime replacement option. Add named, validated settings for product capabilities and keep their internal questions and actions inside this package.

See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-preflight-clarity.md`, `docs/design/jev-tool-selector.md`, `docs/design/jev-specialist-routing.md`, `docs/design/jev-multipart-done-criteria.md`, `docs/design/jev-report-action-alignment.md`, and `skills/jev-agent/SKILL.md`.
See `docs/design/jev-agent-scaffold.md`, `docs/design/jev-preflight-clarity.md`, `docs/design/jev-tool-selector.md`, `docs/design/jev-specialist-routing.md`, `docs/design/jev-multipart-done-criteria.md`, `docs/design/jev-target-outcome-done-check.md`, and `skills/jev-agent/SKILL.md`.
