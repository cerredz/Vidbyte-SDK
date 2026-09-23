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

## Current implementation

- `settings.py` owns the complete public configuration surface.
- `agent.py` maps settings into `BaseAgent` and fixes the runtime to `AgentRuntimeType.JEV`; it supplies its settings through the single `_runtime_extension_kwargs()` hook.
- `presets.py` owns the closed registry of fixed Jev preflight policies, the caller-written `JevCustomQuestion`, and the `JevPreflight` container that turns both into definitions.
- `response.py` owns the run-local `JevResponse` and typed preset results.
- `runtime.py` is the seam for Jev policy. `RuntimeRegistry` resolves `AgentRuntimeType.JEV` to `JevRuntime`, which evaluates every preflight definition in one Jev request before the ordinary linear loop and refuses to build without `JevAgentSettings`.
- `vidbyte/lib/dataclasses/jev.py` owns immutable decision records and the `TypeSafeWireRequest`/`TypeSafeWireQuestion` wire records. They mirror https://docs.typesafe.ai/api.md exactly: state, instructions, and criteria may be strings or JSON structure; noul criteria are optional; Score answers carry a weighted `score`; noul answers carry no confidence.
- `vidbyte/lib/runners/decision.py` owns semantic decision execution (`arun`) and model listing (`alist_models`).
- `vidbyte/providers/typesafe.py` alone owns TypeSafe wire serialization, normalization, and failure mapping.

The clarity preflight is opt-in through `preflight=JevPreflight(preset=(JevPreflightPreset.CLARITY,))`. It asks 18 same-polarity Noul questions in one request, uses their mean `true` probability, and asks the clarification associated with the lowest-scoring dimension when the mean is below the fixed threshold. A missing TypeSafe API key or provider failure is represented as an unavailable preset result and fails open into the ordinary agent loop.

`JevPreflight.custom` is the one deliberate exception to capability-only configuration. Callers may add yes/no `JevCustomQuestion` values, which Jev answers in the same request as the preset questions. Their answers are recorded under `results["custom"]` and never drive runtime policy: the custom definition's threshold is `0.0`, so it cannot trigger clarification.

## Change workflow

1. Read `AGENTS.md`, `docs/design/jev-agent-scaffold.md`, and every existing file under `vidbyte/agents/jev/`.
2. Describe the user-facing capability in product terms and add a dedicated immutable settings type. Prefer one boolean or nested settings object over low-level knobs.
3. Define exactly when the runtime asks Jev, the state Jev sees, the fixed questions asked, and the action for every answer.
4. Define fail-open or fail-closed behavior for missing credentials, timeouts, malformed answers, and unsupported configurations. Never let an exception silently choose policy.
5. Implement orchestration in `JevRuntime`; keep provider wire shapes in `vidbyte/providers/typesafe.py` and reusable validated records in `vidbyte/lib/`.
6. Keep generative usage/speed tracking agent-owned. Make decision usage visible without mixing token fields or double counting.
7. Add tests for the disabled path, each enabled outcome, boundary thresholds, provider failure, and the ordinary model/tool loop.
8. Update this skill and the design documentation when the public philosophy or package boundary changes.

## Invariants

- `JevAgent.__init__` accepts only `JevAgentSettings`.
- TypeSafe/Jev cannot be selected as the reply-generating provider.
- API keys never appear in object representations, errors, logs, traces, or serialized state.
- The public API names capabilities, not internal questions or decisions. The only caller-written questions are `JevPreflight.custom`, and they are recorded, never acted on.
- Runtime state is run-local; reusable configuration is frozen and validated before execution.
- Existing `BaseAgent` behavior remains unchanged when Jev is not involved; `AgentRuntimeType.JEV` gets the same linear-loop wiring as `LINEAR`.
- Provider payload dictionaries do not move into `vidbyte/lib` records.
- No live provider call is required by deterministic tests.

## Example construction

```python
from vidbyte import JevAgent, JevAgentSettings, JevCustomQuestion, JevPreflight, JevPreflightPreset

settings = JevAgentSettings(
    name="researcher",
    system_prompt="Research carefully and report evidence.",
    provider="openai",
    model_name="gpt-4.1",
    preflight=JevPreflight(
        preset=(JevPreflightPreset.CLARITY,),
        custom=(JevCustomQuestion(name="cites_sources", question="Does the request ask for cited sources?"),),
    ),
)
agent = JevAgent(settings)
```

The equivalent namespace constructor is `sdk.agents.jev(settings)`.

## Capability design example

For a future `dynamic_compute` setting, expose the user-level choice and useful bounds. Keep questions such as “Is another iteration likely to materially improve the answer?” inside the runtime. Translate Jev's calibrated answer into a fixed compute policy, record the decision and usage, and test both continued and stopped execution. Do not expose that question as a caller-supplied rule.

## Verification

Run the focused script first:

```text
python scripts/test-jev-agent-scaffold.py
python scripts/test-jev-preflight.py
```

Then run repository gates:

```text
python lint/run.py
python scripts/run_ci.py --stage source
python scripts/run_ci.py
```
