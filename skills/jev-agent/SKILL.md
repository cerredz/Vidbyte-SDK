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
- `runtime.py` is the seam for Jev policy. `RuntimeRegistry` resolves `AgentRuntimeType.JEV` to `JevRuntime`, which currently inherits the ordinary linear loop unchanged and refuses to build without `JevAgentSettings`.
- `vidbyte/lib/dataclasses/jev.py` owns immutable decision records and the `TypeSafeWireRequest`/`TypeSafeWireQuestion` wire records. They mirror https://docs.typesafe.ai/api.md exactly: state, instructions, and criteria may be strings or JSON structure; noul criteria are optional; Score answers carry a weighted `score`; noul answers carry no confidence.
- `vidbyte/lib/runners/decision.py` owns semantic decision execution (`arun`) and model listing (`alist_models`).
- `vidbyte/providers/typesafe.py` alone owns TypeSafe wire serialization, normalization, and failure mapping.

The scaffold performs no Jev call. A missing TypeSafe API key must not prevent `JevAgentSettings` or `JevAgent` construction until an enabled capability actually needs Jev.

## Change workflow

1. Read `AGENTS.md`, `docs/design/jev-agent-scaffold.md`, and every existing file under `vidbyte/agents/jev/`.
2. Describe the user-facing capability in product terms and add a dedicated immutable settings type. Prefer one boolean or nested settings object over low-level knobs.
3. Define exactly when the runtime asks Jev, the state Jev sees, the fixed questions asked, and the action for every answer. Write every question with `skills/asking-jev-questions/SKILL.md`: Jev matches state against definitions you supply; it does not reason, count, forecast, or generate.
4. Define fail-open or fail-closed behavior for missing credentials, timeouts, malformed answers, and unsupported configurations. Never let an exception silently choose policy.
5. Implement orchestration in `JevRuntime`; keep provider wire shapes in `vidbyte/providers/typesafe.py` and reusable validated records in `vidbyte/lib/`.
6. Keep generative usage/speed tracking agent-owned. Make decision usage visible without mixing token fields or double counting.
7. Add tests for the disabled path, each enabled outcome, boundary thresholds, provider failure, and the ordinary model/tool loop.
8. Update this skill and the design documentation when the public philosophy or package boundary changes.

## Invariants

- `JevAgent.__init__` accepts only `JevAgentSettings` plus one optional named `done_criteria` preset from the closed `JevPresets` enum.
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

## Done-criteria presets

A done-criteria preset reviews each attempt to finish before the loop returns it. Enable one with `JevAgent(settings, done_criteria=JevPresets.MotivatingCase)`. This needs a TypeSafe key at construction. Every preset follows one pattern:

1. A generative state builder runs once, before the loop, and turns the request into a validated, request-shaped state.
2. At each finish attempt (`AgentRuntime._finish_attempt_feedback`), a generative handoff builder writes a handoff shaped like that state. It holds refs and verbatim quotes only, never verdicts.
3. Code verifies every ref and quote against the run's recorded tool calls, then works out the exact facts (order, success, staleness).
4. Jev answers one recognition question per item, batched by shared state.
5. Code combines the answers. It either accepts the attempt or returns feedback that continues the same loop. Continuations are capped, infrastructure failures fail open, and the latest report lands in `result.metadata["done_criteria"]`.

`JevPresets.MotivatingCase` (done-check #9) lives in `motivating_case/`. It confirms that the boundary condition which motivated the request (empty input, retry, conflicting state, and so on) was built and run, or inspected where allowed. A nearby easier case (`near_miss`) or the ordinary flow does not count. Each module has one role:
- `state.py`
- `evidence.py` (ledger)
- `handoff.py`
- `checks.py` (code facts)
- `questions.py` (Jev wording)
- `policy.py` (thresholds and combination)
- `builders.py` (generative sub-agents)

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
