---
name: jev-agent
description: Build or modify Vidbyte's opinionated JevAgent, its named Jev-backed capabilities, TypeSafe provider integration, settings, runtime, tests, or documentation.
---

# Jev Agent

Use this skill for work under `vidbyte/agents/jev/` or when adding a Jev-backed capability to the Vidbyte SDK.

## Product contract

`JevAgent` is an opinionated agent, not a framework for users to assemble arbitrary decisions. Its public constructor accepts one `JevAgentSettings` object. Do not add generic `decisions`, question lists, hooks, action callbacks, runtime selectors, middleware injection, or arbitrary passthrough kwargs.

Expose user intent through named, validated capabilities. Examples include:

- pre-allocated questions answered before a model run;
- dynamic compute allocation;
- multi-agent coordination with explicit agent descriptions and metadata.

Each capability owns its fixed internal Jev questions, state projection, thresholds, actions, fallback policy, and observability. Those internal mechanics are implementation details, not public decision-building blocks.

## Current scaffold

- `settings.py` owns the complete public configuration surface.
- `agent.py` maps settings into `BaseAgent` and fixes the runtime to `AgentRuntimeType.JEV`; it supplies its settings through the single `_runtime_extension_kwargs()` hook.
- `runtime.py` is the seam for Jev policy. `RuntimeRegistry` resolves `AgentRuntimeType.JEV` to `JevRuntime`, which inherits the ordinary linear loop, orchestrates any enabled done checks, and refuses to build without `JevAgentSettings`.
- `run_state.py`, `builders.py`, `event_log.py`, and `required_sequence.py` implement the run-state done checks described below.
- `vidbyte/lib/dataclasses/jev.py` owns immutable decision records and the `TypeSafeWireRequest`/`TypeSafeWireQuestion` wire records. They mirror https://docs.typesafe.ai/api.md exactly: state, instructions, and criteria may be strings or JSON structure; noul criteria are optional; Score answers carry a weighted `score`; noul answers carry no confidence.
- `vidbyte/lib/runners/decision.py` owns semantic decision execution (`arun`) and model listing (`alist_models`).
- `vidbyte/providers/typesafe.py` alone owns TypeSafe wire serialization, normalization, and failure mapping.

The scaffold performs no Jev call. A missing TypeSafe API key must not prevent `JevAgentSettings` or `JevAgent` construction until an enabled capability actually needs Jev.

## Run state and done checks

Done checks decide whether a finish attempt may end the run. They share one architecture:

1. **Run state, once, before the loop.** `JevRunStateAgent`, a tool-free `BaseAgent` subclass with a strict output schema, turns the request into `JevRunState`: `goal`, `objective`, `mission`, `what_not_to_do`, `constraints`, `proposed_plan`, plus one section for each enabled setting. The proposed plan is never a requirement. Code validates the section; a section that cannot be trusted becomes `INACTIVE` or `UNAVAILABLE` for the run, with the reason recorded.
2. **Instructions to the main agent.** Each active section adds its instructions to the system prompt, so the agent knows what the review will check.
3. **Handoff, at each finish attempt.** `AgentRuntime.review_finish_attempt` runs on both finish paths (a plain final answer and `isDone`). `JevRuntime` numbers the run's events from the loop state (`event_log.py`; no middleware). `JevRunHandoffAgent` then fills a handoff whose sections mirror the state's sections. The handoff reports what the log shows, including missing work. It has no `complete` field. Code checks every cited event ID. An invalid handoff is rebuilt once with the error; if it is still invalid, the finish is accepted and flagged.
4. **Review.** Each section's `areview` decides every fact in code and asks Jev only the recognition questions that remain, in one batched request written with `skills/asking-jev-questions/SKILL.md`. A missing TypeSafe key leaves only the code checks.
5. **Decision.** If every section passes, the answer is accepted. Otherwise the agent continues in the same loop with feedback naming the first failing item. After `JEV_MAX_FINISH_REVIEW_CONTINUATIONS` continuations, the next failure stops the run with `AgentStopReason.FINISH_REVIEW_REJECTED`. Everything is recorded in `result.metadata["jev_run_report"]` (`JevRunReport`).

To add a done check:
- subclass `JevRunSection` in its own module;
- add a `JevRunSectionKey` member;
- add a boolean setting and return the section from `JevRuntime._enabled_sections`;
- add its three prompt assets (state, handoff, agent) to `vidbyte/prompts/prompts/jev_run_state/`.

Section fields exist only because a later check or question reads them.

### `required_sequence` (done check #15)

The state section lists ordered stages, each with:
- `stage_id`, assigned by code;
- `name`;
- `source_text`, quoted from the request (code rejects quotes that are not in it);
- `completion_criterion`;
- `produces`;
- `depends_on_previous`.

It is active only for 2 to 12 stages and only when the request itself requires an order. The handoff has one entry per stage with:
- `observed_work` and `failures`, citing event IDs;
- `outputs_produced`, `inputs_used`, and `missing_or_uncertain`;
- `first_event_id` and `last_work_event_id`.

Code fails a stage that has no work, or that starts before the previous stage's last work event (strict order, which also catches rework). Jev answers `stage_N_work_shown` for each stage with work, and `stage_N_uses_previous_output` where the stage depends on the previous one. Code never asks Jev whether the sequence is complete or ordered.


1. Read `AGENTS.md`, `docs/design/jev-agent-scaffold.md`, and every existing file under `vidbyte/agents/jev/`.
2. Describe the user-facing capability in product terms and add a dedicated immutable settings type. Prefer one boolean or nested settings object over low-level knobs.
3. Define exactly when the runtime asks Jev, the state Jev sees, the fixed questions asked, and the action for every answer. Write every question with `skills/asking-jev-questions/SKILL.md`: Jev matches state against definitions you supply; it does not reason, count, forecast, or generate.
4. Define fail-open or fail-closed behavior for missing credentials, timeouts, malformed answers, and unsupported configurations. Never let an exception silently choose policy.
5. Implement orchestration in `JevRuntime`; keep provider wire shapes in `vidbyte/providers/typesafe.py` and reusable validated records in `vidbyte/lib/`.
6. Keep generative usage/speed tracking agent-owned. Make decision usage visible without mixing token fields or double counting.
7. Add tests for the disabled path, each enabled outcome, boundary thresholds, provider failure, and the ordinary model/tool loop.
8. Update this skill and the design documentation when the public philosophy or package boundary changes.

## Invariants

- `JevAgent.__init__` accepts only `JevAgentSettings`.
- TypeSafe/Jev cannot be selected as the reply-generating provider.
- API keys never appear in object representations, errors, logs, traces, or serialized state.
- The public API names capabilities, not internal questions or decisions.
- Runtime state is run-local; reusable configuration is frozen and validated before execution.
- Existing `BaseAgent` behavior remains unchanged when Jev is not involved; `AgentRuntimeType.JEV` gets the same linear-loop wiring as `LINEAR`.
- Provider payload dictionaries do not move into `vidbyte/lib` records.
- No live provider call is required by deterministic tests.

## Example construction

```python
from vidbyte import JevAgent, JevAgentSettings

settings = JevAgentSettings(
    name="researcher",
    system_prompt="Research carefully and report evidence.",
    provider="openai",
    model_name="gpt-4.1",
)
agent = JevAgent(settings)
```

The equivalent namespace constructor is `sdk.agents.jev(settings)`.

## Capability design example

For a future `dynamic_compute` setting, expose the user-level choice and useful bounds. Keep questions such as “How much did `last_turn` add beyond `earlier_findings`?” inside the runtime. Ask about what the last turn observably did, not whether another turn will help: Jev answers observations reliably and forecasts poorly. Translate Jev's calibrated answer into a fixed compute policy, record the decision and usage, and test both continued and stopped execution. Do not expose that question as a caller-supplied rule.

## Verification

Run the focused script first:

```text
python scripts/test-jev-agent-scaffold.py
```

Then run repository gates:

```text
python lint/run.py
python scripts/run_ci.py --stage source
python scripts/run_ci.py
```
