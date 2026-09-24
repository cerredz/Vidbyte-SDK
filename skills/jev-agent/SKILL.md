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

## Proposed run state and finish handoff

This is implementation guidance for future capabilities; the current scaffold does not build these objects. The shared state describes the task, rather than making a list of completion obligations the universal state shape. A generative builder runs once at the beginning of a run and produces a validated, run-local object from the original request:

```text
RunState(request, goal, objective, mission, what_not_to_do, constraints,
         proposed_plan, sections, version)
```

Keep `request` verbatim. `goal` is the broad aim, `objective` the requested outcome, and `mission` the governing purpose when the request states one; avoid inventing a distinction when it does not. `what_not_to_do` and `constraints` preserve explicit boundaries and qualifications. A proposed plan is provisional, not a new user requirement. Named Jev settings enable internally defined sections; callers do not provide arbitrary schemas or Jev questions.

The first named extension is a setting for **multi-part completion**. When enabled, its initial builder adds a `multi_part_completion` section with the distinct requested deliverables, each carrying a stable ID, the relevant request wording, scope, and completion criterion. This list belongs inside that capability's section, not at the root of every RunState. Preserve sections for parts the agent may never attempt. If a later user instruction changes scope, version the affected state and keep its source wording.

At a finish attempt, a second generative builder reads the original request, validated RunState, proposed final answer, and a snapshot of the observed run. It fills a matching structured handoff: overall observed outcome, limitations, and a `multi_part_completion` section with exactly one entry per requested deliverable ID. Each entry describes observed work, coverage, attempts or failures, verification, missing or uncertain parts, and source event references. Do not let the builder silently drop an unattempted deliverable or pre-answer Jev with a bare `complete` boolean. A reference makes a claim inspectable; it does not prove the claim.

Orchestrate this in `JevRuntime`: initial builder -> ordinary generative loop -> finish attempt -> strict handoff builder -> `JevDecisionRequest` -> completion policy. Pass the original request, initial state, and structured handoff as Jev's structured state. Ask one narrow Jev question per requested deliverable, grouping only when the shared state fits the decision budget. Code validates matching IDs and versions, checks missing handoff sections, combines answers, and returns concrete missing work to the **same** agent loop. The handoff should describe evidence and gaps; Jev classifies whether each requested part is supported. Use `skills/asking-jev-questions/SKILL.md` for the fixed internal questions. Keep uncertainty explicit, and never infer completion from a missing entry.

Use small internal `BaseAgent` subclasses for the two different generative builders if they need distinct prompts and strict output schemas. Keep RunState and handoff as typed data, and keep final acceptance policy in `JevRuntime`. The existing `HandoffAgent` demonstrates the subclass pattern, but its completed-run timing and prose fallback cannot serve as a strict finish gate unchanged. The ordinary runtime currently returns after a final response, so continuation requires a finish-attempt seam before both plain final responses and `isDone` are accepted. Review only genuine finish attempts; budget stops, cancellation, and errors retain their own stop reasons. Bound repeated reviews.

Retain source events across compaction so the handoff builder can inspect the run it summarizes. If a long run cannot be reviewed within the builder's context, mark the handoff incomplete or allow targeted inspection; do not silently truncate decisive material. A 5–10k-token Jev view is a budget, not a guarantee that every possible question fits. Runtime observations, the agent's declared intent, and verified outcomes remain separate. Code owns counts, ordering, permissions, version checks, and answer combination; generative models interpret the request and reconstruct run history; Jev receives prepared, narrow classifications.

Evaluate each stage independently: correctness of initial state extraction, handoff coverage against the observed run, Jev on a reviewed handoff, and end-to-end continuation. Include a multi-part request where the agent completes its prominent part and omits documentation, migration, or explanation. Measure missed parts, false completion, unresolved cases, model calls, latency, and total cost. No state or handoff can guarantee access to the main model's private reasoning or perfect recovery of every decisive fact.

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
