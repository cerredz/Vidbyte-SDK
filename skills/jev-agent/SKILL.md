---
name: jev-agent
description: Build or modify Vidbyte's opinionated JevAgent, its named Jev-backed capabilities, TypeSafe provider integration, settings, runtime, tests, or documentation.
---

# Jev Agent

Use this skill for work under `vidbyte/agents/jev/` or when adding a Jev-backed capability to the Vidbyte SDK.

## Product contract

`JevAgent` is an opinionated agent, not a framework for users to assemble arbitrary decisions. Its public constructor accepts a `JevAgentSettings` object and an optional `JevRuntimeSettings` object. Do not add generic `decisions`, question lists, hooks, action callbacks, runtime selectors, middleware injection, or arbitrary passthrough kwargs.

Expose user intent through named, validated capabilities. Examples include:

- pre-allocated questions answered before a model run;
- dynamic compute allocation;
- multi-agent coordination with explicit agent descriptions and metadata.

Each capability owns its fixed internal Jev questions, state projection, thresholds, actions, fallback policy, and observability. Those internal mechanics are implementation details, not public decision-building blocks.

## Current scaffold

- `settings.py` owns the complete public configuration surface: `JevAgentSettings` holds the main agent (name, prompt, model, tools, permissions, loop) and `agents`, the `JevSpecialist` candidates Jev may hand a run to; `JevRuntimeSettings` holds Jev's own policy (`decision`, `preflight`, `continual`, `tool_selector_threshold`). `continual` is a `JevContinualSettings`: the enabled done `checks`, `max_continuations`, and the run-state and handoff agents' iteration and token limits.
- `agent.py` maps settings into `BaseAgent`, fixes the runtime to `AgentRuntimeType.JEV`, and builds every run-time object a feature needs at construction: the `JevPreflightGate`, the `JevRunState` (when `continual.checks` enables a done check), and the `JevResponse` writer. It passes them, with the runtime settings the tool selector still reads, to the runtime through the single `_runtime_extension_kwargs()` hook, and exposes `JevAgent.response`, a `JevAgentResponse` record of what the features produced in the most recent run.
- `runtime.py` holds no fixed-question preset checks. `RuntimeRegistry` resolves `AgentRuntimeType.JEV` to `JevRuntime`, which refuses to build without a gate. Before the inherited linear loop it calls `JevPreflightGate.pass_` and returns `JevResponse.stopped()` when the gate closes. When the gate chose a specialist, the runtime runs that specialist's own agent on the message and returns `JevResponse.delegated()`; otherwise the main agent runs. The tool selector (`preflight.py`, `JevPreflightTools`) keeps its own path after the gate. With done checks enabled, the runtime calls `JevRunState.begin` before the main loop and answers `AgentRuntime._continue_finish_attempt` by asking its `JevContinuation` `should_continue` and, on True, calling `continue_`, which appends the next message to the same loop's messages. The runtime holds no continuation logic of its own.
- `gate/` holds the gate and the steps its cases trigger. `gate.py` (`JevPreflightGate`) owns `combine`, which builds one Jev request from every enabled fixed-question preset plus the specialist Choice question when `agents` is set, and `pass_`, one `match` statement over the outcomes that returns whether the generative agent runs, after which it records the specialist Jev ranked first (or none) in `specialist`. `DecisionModelRunner.score_noul` turns each preset's answers into a score and a pass or fail. `clarification.py` (`JevClarificationAgent`) is the generative agent an unclear request is routed to; it reads the request as its message and the failed checks as a `ContextManager` item, and returns `JevClarificationPayload`: questions, each with a few recommended answers.
- `done/` holds the done checks. `run_state.py` (`JevRunState`) writes request-derived state once before the main loop; at each finish attempt `handoff.py` (`JevHandoff`) compiles evidence from the main agent's `ContextManager` of response and tool-call primitives. It can also derive items from the finished answer, as CLAIMS does, when those items cannot exist before work. `JevRunState` combines every enabled check's questions (one per item) into one Jev request over one shared state, scores the answers with `score_noul`, and returns the checks that failed. Request-derived checks add run-state and handoff sections; post-run-derived checks such as CLAIMS add only a handoff section and build their questions from it.
- `JevDoneCheck.INPUT_EXHAUSTION` is for explicit requests to traverse a dynamic or paginated collection to its end. Run state preserves a user-stated count and unit when present; JevHandoff gathers trace-backed visited identifiers, source totals, cursors, terminal markers, and failed retrievals. Code counts distinct units against a requested total first, then a matching source total; when no total is known, lack of affirmative terminal evidence is an incomplete obligation, not proof of exhaustion or an unavailable result. Jev recognizes the prepared evidence one collection at a time in the shared request. Finite named inputs belong to a separate coverage check.
- `continuation/` holds the continuations. `base.py` (`JevContinuation`) is the contract the runtime calls: `should_continue` and `continue_`. `done.py` (`JevDoneContinuation`) runs `JevRunState.check` and, while continuations remain (`JevContinualSettings.max_continuations`), sends the main agent the original request, the run state, the handoff, and the failed Jev questions, with focus on what is missing, through the `jev_continuation/continue_prompt.md` prompt asset. A new way to continue a run is a new subclass here.
- `response.py` (`JevResponse`) is the only writer of `JevAgentResponse`. Features report outcomes through its methods, never through result metadata.
- `vidbyte/lib/jev/presets.py` (`JevPresets`) owns the preflight flags a user enables through `JevRuntimeSettings.preflight`, and the fixed question keys and threshold of each fixed-question flag.
- `vidbyte/lib/jev/preflight/` is the canonical home of every fixed preflight question, one dataclass per question (`clarity.py`), the specialist Choice question (`specialist.py`), and `JevPreflightRegistry`, the registry over them (`get`, `questions`, `specialists`, `validate`). The flag and question-key enums live in `vidbyte/lib/enums/jev.py`; the preflight records live in `vidbyte/lib/dataclasses/jev.py`.
- `vidbyte/lib/jev/done/` holds every fixed done question (`multi_part.py`, `claims.py`) and `JevDoneRegistry` (`question`, `threshold`, `resolve`, `validate`). The structured-reply payloads (every field described in 4–6 sentences), the run-state, handoff, claim, and done records, and `JevDoneQuestion` live in `vidbyte/lib/dataclasses/jev.py`; `JevDoneCheck` and `JevDoneQuestionKey` live in `vidbyte/lib/enums/jev.py`.
- `vidbyte/lib/dataclasses/jev.py` owns immutable decision records and the `TypeSafeWireRequest`/`TypeSafeWireQuestion` wire records. They mirror https://docs.typesafe.ai/api.md exactly: state, instructions, and criteria may be strings or JSON structure; noul criteria are optional; Score answers carry a weighted `score`; noul answers carry no confidence.
- `vidbyte/lib/runners/decision.py` owns semantic decision execution (`arun`), model listing (`alist_models`), and noul scoring against a threshold (`score_noul`).
- `vidbyte/providers/typesafe.py` alone owns TypeSafe wire serialization, normalization, and failure mapping.

With no preflight preset enabled and no specialist configured, a run performs no Jev call. A missing TypeSafe API key must not prevent `JevAgentSettings`, `JevRuntimeSettings`, or `JevAgent` construction. When an enabled preset cannot reach Jev, or a clarification cannot be written, the gate fails open: the preset is marked unavailable and the ordinary loop runs. A missing, failed, or `none` specialist answer keeps the main agent on the run; a specialist is only ever chosen after the gate passes. Done checks fail open too: no run state means no check, and an unavailable handoff or Jev answer lets the finish attempt stand; a chosen specialist runs without them. `JevPreflightPreset.TOOL_SELECTOR` keeps every tool whose P(yes) is at least `tool_selector_threshold`, a finite probability from 0 through 1 inclusive.

## Adding a preflight preset

1. Add a `JevPreflightPreset` member in `vidbyte/lib/enums/jev.py`. For fixed questions, also add one `JevPreflightQuestionKey` per question, prefixing each key with the preset name.
2. Load `skills/asking-jev-questions/SKILL.md` first, then write each fixed question as its own `JevPreflightQuestion` subclass under `vidbyte/lib/jev/preflight/`, with a default for every field. The instructions are a `JevBrief` (introduction, state, definitions, rules, question) and each side is a `JevCriterion` (what, not_for, easy and boundary examples), following that skill's "Writing a full question" section. Never split a string into adjacent literals (lint S062).
3. Add the preset's `JevPresetDefinition` (question keys and a named threshold constant) to `JevPresets`, and register its questions in `JevPreflightRegistry._questions`.
4. Add one commented case to the `match` in `JevPreflightGate.pass_` (`combine` and scoring pick the preset up from `JevPresets`). Put the step the case triggers in its own module under `gate/`, and report its outcome through a `JevResponse` method.
5. Extend `tests/test_jev_preflight.py`.

## Adding a done check

Load `skills/jev-continuation/SKILL.md` first; it explains each step below in detail, with the batching, fail-open, and continuation-message rules.

1. Add a `JevDoneCheck` member and its `JevDoneQuestionKey` in `vidbyte/lib/enums/jev.py`.
2. Add its run-state section and evidence section payloads (subclasses of `JevSectionPayload` with a `SECTION` text and a 4–6 sentence description on every field) and their records to `vidbyte/lib/dataclasses/jev.py`.
3. Load `skills/asking-jev-questions/SKILL.md` first, then write its question as a `JevDoneQuestion` subclass under `vidbyte/lib/jev/done/` and register it and its threshold constant in `JevDoneRegistry`.
4. Add sections to the schemas that carry the check's items and convert them in the relevant `_record` methods. Add one commented case to `JevRunState._section` (the shared state and questions), `JevRunState._judge`, and `JevDoneContinuation._explain` (the failed questions and focus the main agent reads).
5. Extend `tests/test_jev_done.py`.

**Post-run-derived items:** CLAIMS cannot add a predicted list to `JevRunStateRecord`, because concrete claims do not exist until the main agent writes its final answer. Instead, add its section and typed records to `JevHandoff`, validate unique ids there, then build one question per handoff claim in `JevRunState._section`. The continuation focus must include only claims Jev marked unsupported and each claim's evidence gap.

## Change workflow

1. Read `AGENTS.md`, `docs/design/jev-agent-scaffold.md`, and every existing file under `vidbyte/agents/jev/`.
2. Describe the user-facing capability in product terms and add a named setting or preset. Keep caller configuration to the minimum product-level controls, such as a validated threshold.
3. Define exactly when the runtime asks Jev, the state Jev sees, the fixed questions asked, and the action for every answer. Write every question with `skills/asking-jev-questions/SKILL.md`: Jev matches state against definitions you supply; it does not reason, count, forecast, or generate.
4. Define fail-open or fail-closed behavior for missing credentials, timeouts, malformed answers, and unsupported configurations. Never let an exception silently choose policy.
5. Implement orchestration in `JevPreflightGate` and the steps under `vidbyte/agents/jev/gate/`, never as preset checks in `JevRuntime`; keep provider wire shapes in `vidbyte/providers/typesafe.py` and reusable validated records in `vidbyte/lib/`.
6. Keep generative usage/speed tracking agent-owned. Make decision usage visible without mixing token fields or double counting.
7. Add tests for the disabled path, each enabled outcome, boundary thresholds, provider failure, the ordinary model/tool loop, and any context/schema/tool-catalog changes.
8. Update this skill and the design documentation when the public philosophy or package boundary changes.

## Invariants

- `JevAgent.__init__` accepts only `JevAgentSettings` and an optional `JevRuntimeSettings`.
- TypeSafe/Jev cannot be selected as the reply-generating provider.
- API keys never appear in object representations, errors, logs, traces, or serialized state.
- The public API names capabilities, not internal questions or decisions.
- Runtime state is run-local; reusable configuration is frozen and validated before execution, and every preflight object is built in `JevAgent.__init__`.
- Feature outcomes reach the caller through `JevAgent.response`, never through result metadata.
- Existing `BaseAgent` behavior remains unchanged when Jev is not involved; `AgentRuntimeType.JEV` gets the same linear-loop wiring as `LINEAR`.
- Provider payload dictionaries do not move into `vidbyte/lib` records.
- No live provider call is required by deterministic tests.

## Example construction

```python
from vidbyte import BaseAgent, JevAgent, JevAgentSettings, JevContinualSettings, JevDoneCheck, JevPreflightPreset, JevRuntimeSettings, JevSpecialist

schema = BaseAgent(name="schema", system_prompt="Change the database schema safely.", provider="openai", model_name="gpt-4.1")
settings = JevAgentSettings(
    name="researcher",
    system_prompt="Research carefully and report evidence.",
    provider="openai",
    model_name="gpt-4.1",
    agents=(JevSpecialist("schema", "Changes to the database schema and its migrations.", schema),),
)
agent = JevAgent(settings, JevRuntimeSettings(preflight=(JevPreflightPreset.CLARITY,), continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,), max_continuations=2)))
```

The equivalent namespace constructor is `sdk.agents.jev(settings, runtime_settings)`. After a run, `agent.response.specialist` names the specialist that ran the task, or is `None` when the main agent ran it, and `agent.response.done[JevDoneCheck.MULTI_PART]` says whether every requested deliverable was shown produced in full.

## Capability design example

For a future `dynamic_compute` setting, expose the user-level choice and useful bounds. Keep questions such as “How much did `last_turn` add beyond `earlier_findings`?” inside the runtime. Ask about what the last turn observably did, not whether another turn will help: Jev answers observations reliably and forecasts poorly. Translate Jev's calibrated answer into a fixed compute policy, record the decision and usage, and test both continued and stopped execution. Do not expose that question as a caller-supplied rule.

## Verification

Run the focused script first:

```text
python scripts/test-jev-agent-scaffold.py
python scripts/test-jev-multipart-done-criteria.py
```

Then run repository gates:

```text
python lint/run.py
python scripts/run_ci.py --stage source
python scripts/run_ci.py
```
