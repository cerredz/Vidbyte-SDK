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
- `agent.py` maps settings into `BaseAgent`, fixes the runtime to `AgentRuntimeType.JEV`, and builds every run-time object a feature needs at construction: the `JevPreflight` gate and the `JevResponse` writer. It passes both to the runtime through the single `_runtime_extension_kwargs()` hook, and exposes `JevAgent.response`, a `JevAgentResponse` record of what the features produced in the most recent run.
- `runtime.py` holds no preset checks. `RuntimeRegistry` resolves `AgentRuntimeType.JEV` to `JevRuntime`, which refuses to build without a gate. Before the inherited linear loop it calls `JevPreflight.pass_`, returns `JevResponse.stopped()` when the gate closes, and otherwise runs the loop with the tool catalog the gate chose. Metadata, options, and trace context pass through untouched.
- `preflight/` holds the gate and the steps its cases trigger. `preflight.py` (`JevPreflight`) owns `combine`, which builds one Jev request from every enabled preset, and `pass_`, one `match` statement over the answers that returns whether the generative agent runs. `tools.py` (`JevPreflightTools`) builds one question per tool and narrows the catalog. `clarification.py` (`JevClarificationAgent`) is the generative agent an unclear request is routed to; it writes simple questions for the user.
- `response.py` (`JevResponse`) is the only writer of `JevAgentResponse`. Features report outcomes through its methods, never through result metadata.
- `vidbyte/lib/jev/presets.py` (`JevPresets`) owns the preflight flags a user enables through `JevAgentSettings.preflight`, and the fixed question keys and threshold of each fixed-question flag.
- `vidbyte/lib/jev/preflight/` is the canonical home of every fixed preflight question, one dataclass per question (`clarity.py`), and of `JevPreflightRegistry`, the registry over them (`get`, `questions`, `validate`). The flag and question-key enums live in `vidbyte/lib/enums/jev.py`; the preflight records live in `vidbyte/lib/dataclasses/jev.py`.
- `vidbyte/lib/dataclasses/jev.py` owns immutable decision records and the `TypeSafeWireRequest`/`TypeSafeWireQuestion` wire records. They mirror https://docs.typesafe.ai/api.md exactly: state, instructions, and criteria may be strings or JSON structure; noul criteria are optional; Score answers carry a weighted `score`; noul answers carry no confidence.
- `vidbyte/lib/runners/decision.py` owns semantic decision execution (`arun`) and model listing (`alist_models`).
- `vidbyte/providers/typesafe.py` alone owns TypeSafe wire serialization, normalization, and failure mapping.

With no preflight preset enabled, a run performs no Jev call. A missing TypeSafe API key must not prevent `JevAgentSettings` or `JevAgent` construction. When an enabled preset cannot reach Jev, or a clarification cannot be written, the gate fails open: the preset is marked unavailable and the ordinary loop runs. `JevPreflightPreset.TOOL_SELECTOR` keeps every tool whose P(yes) is at least `tool_selector_threshold`, a finite probability from 0 through 1 inclusive.

## Adding a preflight preset

1. Add a `JevPreflightPreset` member in `vidbyte/lib/enums/jev.py`. For fixed questions, also add one `JevPreflightQuestionKey` per question, prefixing each key with the preset name.
2. Write each fixed question as its own `JevPreflightQuestion` subclass under `vidbyte/lib/jev/preflight/`, with a default for every field, written to `skills/asking-jev-questions/SKILL.md`. The instructions are one 4-5 sentence string: a definition, a boundary, a focus, then one positive yes/no question about the `request` state field. Each criterion is one multi-sentence string: what the answer covers, where it stops, an easy example, and a boundary example. Never split a string into adjacent literals (lint S062).
3. Add the preset's `JevPresetDefinition` (question keys and a named threshold constant) to `JevPresets`, and register its questions in `JevPreflightRegistry._questions`.
4. Add the preset's questions to `JevPreflight.combine`, its outcome to `JevPreflight._outcomes`, and one commented case to the `match` in `JevPreflight.pass_`. Put the step the case triggers in its own module under `preflight/`, and report its outcome through a `JevResponse` method.
5. Extend `tests/test_jev_preflight.py`.

## Change workflow

1. Read `AGENTS.md`, `docs/design/jev-agent-scaffold.md`, and every existing file under `vidbyte/agents/jev/`.
2. Describe the user-facing capability in product terms and add a named setting or preset. Keep caller configuration to the minimum product-level controls, such as a validated threshold.
3. Define exactly when the runtime asks Jev, the state Jev sees, the fixed questions asked, and the action for every answer. Write every question with `skills/asking-jev-questions/SKILL.md`: Jev matches state against definitions you supply; it does not reason, count, forecast, or generate.
4. Define fail-open or fail-closed behavior for missing credentials, timeouts, malformed answers, and unsupported configurations. Never let an exception silently choose policy.
5. Implement orchestration in `JevPreflight` and the steps under `vidbyte/agents/jev/preflight/`, never as preset checks in `JevRuntime`; keep provider wire shapes in `vidbyte/providers/typesafe.py` and reusable validated records in `vidbyte/lib/`.
6. Keep generative usage/speed tracking agent-owned. Make decision usage visible without mixing token fields or double counting.
7. Add tests for the disabled path, each enabled outcome, boundary thresholds, provider failure, the ordinary model/tool loop, and any context/schema/tool-catalog changes.
8. Update this skill and the design documentation when the public philosophy or package boundary changes.

## Invariants

- `JevAgent.__init__` accepts only `JevAgentSettings`.
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
