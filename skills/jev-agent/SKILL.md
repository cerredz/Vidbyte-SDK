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

## Proposed state architecture for runtime decisions

Use this guidance when designing a capability that asks Jev about an active or completed run. It is a design direction, not a claim that the current scaffold implements state tracking.

Maintain three related representations:

1. **Recoverable source evidence:** user instructions, model outputs, tool inputs and outcomes, and relevant artifact versions. Retain the material needed to revisit a detail after context compaction or result truncation. An evidence reference supports retrieval and audit; Jev needs the relevant content in its view.
2. **Run-local structured state:** incrementally update objectives, constraints and exceptions, active tasks, declared plans, findings, execution outcomes, and unresolved issues. Keep what the runtime observed separate from what the agent interpreted, intended, or claimed to have verified. Record scope, provenance, dependencies, and versions for consequential facts. Changes invalidate dependent claims; a passed check on an old artifact version does not verify the current one.
3. **Decision-specific Jev view:** assemble the facts and evidence needed by a named capability. Treat roughly 5–10k tokens as an upper budget for a broad view, not a required size for every call. Keep instructions, exceptions, qualifications, and contradictions that could change the answer.

Update deterministic execution facts directly from runtime events. Have the generative agent provide small structured changes to its interpretations and plans during ordinary responses. Use targeted retrieval or a generative interpretation call when a new question needs old detail or when an instruction is ambiguous. Validate updates at runtime boundaries; a missing or malformed update leaves dependent semantic state unresolved. Periodic reconciliation can detect drift, but summaries of summaries cannot establish completeness.

At a decision boundary, specify an **evidence contract**: the classification criteria, required evidence and scope, freshness and version requirements, preparation steps, input budget, and behavior when evidence is insufficient. Check for known gaps, stale claims, conflicts, and budget overflow before using Jev's answer. Retrieve or interpret missing material, defer, or use a suitable fallback according to the capability's policy. Do not silently trim required evidence to fit the budget or treat an unresolved absence as proof that nothing relevant exists.

Timing affects what the state can truthfully say. After a tool result, the runtime knows the observed outcome while the generative agent's interpretation may still be pending. Preserve that distinction. A prior conditional intention may become inapplicable when its condition fails. Before tool execution, use the agent's latest proposed action and interpretation; at run completion, compare final claims with current execution and verification evidence.

Keep deterministic counting, ordering, permission checks, version checks, and answer combination in code. Give ambiguous instructions, reference resolution, planning, and complex synthesis to a generative model. Ask Jev narrow recognition questions over prepared evidence using `skills/asking-jev-questions/SKILL.md`. A yes/no form does not make a question simple if answering it requires multi-step reasoning.

No fixed-size state can preserve all information needed for every possible future question about an unbounded run. No state schema guarantees faithful access to the generative model's private reasoning. Aim for an accurate operational record of observed facts, declared beliefs and intentions, and verified outcomes, with recoverable evidence and explicit uncertainty. Extraction and retrieval can miss decisive facts. Provenance, an event ID, or a `complete` flag can show where a claim came from but cannot prove the evidence establishes the claim or that every relevant detail was found.

Before letting a state-backed decision control consequential runtime behavior, evaluate three levels separately: Jev on a reviewed reference view, Jev on the automatically prepared view, and the resulting full-run outcome. Include paired cases differing by one decisive exception, correction, version, failed check, or dependency. Measure missed evidence, stale-state errors, incorrect decisions, fallback rate, added tokens, latency, and total cost. Start with action relevance, progress assessment, and final-output support to test whether the design generalizes beyond one capability.

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
