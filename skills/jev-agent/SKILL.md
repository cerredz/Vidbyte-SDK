---
name: jev-agent
description: Build or modify Vidbyte's opinionated JevAgent, its named Jev-backed capabilities, TypeSafe provider integration, settings, runtime, tests, or documentation.
---

# Jev Agent

Use this skill for work under `vidbyte/agents/jev/` or when adding a Jev-backed capability to the Vidbyte SDK.

## Product contract

`JevAgent` is an opinionated agent, not a framework for users to assemble arbitrary decisions. Its public constructor accepts one `JevAgentSettings` object and named keyword-only capabilities such as `done_criteria=JevPresets.MultiPart`. Do not add generic `decisions`, question lists, hooks, action callbacks, runtime selectors, middleware injection, or arbitrary passthrough kwargs.

Expose user intent through named, validated capabilities. Examples include:

- pre-allocated questions answered before a model run;
- dynamic compute allocation;
- multi-agent coordination with explicit agent descriptions and metadata.
- multipart done criteria, which builds one request-shaped state before execution and checks a structured run handoff at each normal finish attempt.

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

1. Read `AGENTS.md`, the relevant Jev design docs, and every existing file under `vidbyte/agents/jev/`.
2. Describe the user-facing capability in product terms and add a dedicated immutable settings type. Prefer one boolean or nested settings object over low-level knobs.
3. Define exactly when the runtime asks Jev, the state Jev sees, the fixed questions asked, and the action for every answer. Write every question with `skills/asking-jev-questions/SKILL.md`: Jev matches state against definitions you supply; it does not reason, count, forecast, or generate.
4. Define fail-open or fail-closed behavior for missing credentials, timeouts, malformed answers, and unsupported configurations. Never let an exception silently choose policy.
5. Implement orchestration in `JevRuntime`; keep provider wire shapes in `vidbyte/providers/typesafe.py` and reusable validated records in `vidbyte/lib/`.
6. Keep generative usage/speed tracking agent-owned. Make decision usage visible without mixing token fields or double counting.
7. Add tests for the disabled path, each enabled outcome, boundary thresholds, provider failure, and the ordinary model/tool loop.
8. Update this skill and the design documentation when the public philosophy or package boundary changes.

## Invariants

- `JevAgent.__init__` accepts only `JevAgentSettings`.
- Named capability choices are keyword-only enum values; done criteria are enabled with one preset or a tuple of distinct presets, such as `JevAgent(settings, done_criteria=(JevPresets.MultiPart, JevPresets.ScopeCoverage))`.
- TypeSafe/Jev cannot be selected as the reply-generating provider.
- API keys never appear in object representations, errors, logs, traces, or serialized state.
- The public API names capabilities, not internal questions or decisions.
- Runtime state is run-local; reusable configuration is frozen and validated before execution.
- Done criteria create the structured state once per run and at most one handoff per normal finish attempt, whatever the number of enabled presets. Each preset adds its own state section and handoff section, and the handoff must match every state ID exactly.
- Each preset is a `JevDoneCheck` subclass (`done_checks.py`) that owns its questions, thresholds, feedback, and metadata. The runtime only builds the shared inputs, runs the checks, and merges their results.
- Jev sees one deliverable and its matching handoff evidence per question. Deterministic code joins answers and feeds incomplete items back into the same runtime loop.
- State/handoff schema errors and Jev failures never count as successful completion; the main agent cannot silently finish while the capability is enabled and verification failed.
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

## Multipart completion capability

```python
from vidbyte import JevAgent, JevAgentSettings, JevPresets

agent = JevAgent(
    JevAgentSettings(
        name="developer",
        system_prompt="Implement the requested change and report what you did.",
        provider="openai",
        model_name="gpt-4.1",
    ),
    done_criteria=JevPresets.MultiPart,
)
```

The runtime uses `JevRunStateBuilderAgent` once to capture goal, objective, mission, exclusions, useful sections, and the specifically named multipart deliverable section. It uses `JevRunHandoffBuilderAgent` at each ordinary finish attempt to map direct run observations to those deliverables. The strict handoff is checked by ID before `DecisionModelRunner` asks one `NOUL` recognition question per item. Jev judges only whether that item's handoff evidence shows its explicit completion signal; runtime code evaluates status, remaining work, and probability. Any gap is appended to the live loop so the same agent can continue.

The generated deliverable list is capability-specific; it is not a universal obligations model. A large original request or handoff may exceed TypeSafe's state limit, and the provider error is surfaced instead of truncating the information silently. The initial 0.8 `P(true)` threshold is an internal policy constant and should be calibrated against representative runs before being treated as a product guarantee.

## Scope coverage capability

`done_criteria=JevPresets.ScopeCoverage` catches silent scope narrowing: the user asks for a change across a group ("all our model providers", "the web, CLI, and API") and the agent does one member and finishes. The code lives in `vidbyte/agents/jev/scope_coverage/`, one role per module.

- The state section holds one `JevScopeDimension` per group: a verbatim `request_quote`, the `requested_change`, the `unit_noun`, a `breadth` (`every_member`, `named_list`, `one_example`, `single_target`), a `universe` (`named_in_request`, `found_in_workspace`, `open_ended`), and verbatim `named_units`, `excluded_units`, and `partial_allowed_quote`. Code rejects any quoted field that does not appear in the request.
- Only `every_member` and `named_list` dimensions without a partial-coverage quote are checked. A dimension the builder labeled narrow gets one Jev `choice` breadth review before the loop, which may widen it.
- The handoff section lists every named or listed unit with cited `work` excerpts, plus the listing excerpts, narrowing statements, and final-answer coverage claims. It has no verdict fields; code recomputes each unit's source.
- Code computes the required units and the units with no work. Jev answers one `choice` per worked unit (`applied` / `attempted` / `examined_only` / `none`) and, for an incomplete dimension, one `choice` on the final answer (`claims_all` / `reports_partial` / `silent`).
- The run continues with named gaps for two finish attempts. After that, a disclosed gap is accepted as `partial_disclosed`; a silent one gets one disclosure request and is then accepted as `partial_undisclosed`. The runtime never rewrites the agent's output.

Thresholds (0.8 applied, 0.7 disclosed, 0.5 breadth widening) are starting points in `vidbyte/lib/constants/jev.py` and must be tuned on labeled runs. Open-ended groups can only be checked for named units, overclaiming, and disclosure.

## Capability design example

For a future `dynamic_compute` setting, expose the user-level choice and useful bounds. Keep questions such as “How much did `last_turn` add beyond `earlier_findings`?” inside the runtime. Ask about what the last turn observably did, not whether another turn will help: Jev answers observations reliably and forecasts poorly. Translate Jev's calibrated answer into a fixed compute policy, record the decision and usage, and test both continued and stopped execution. Do not expose that question as a caller-supplied rule.

## Verification

Run the focused script first:

```text
python scripts/test-jev-agent-scaffold.py
python scripts/test-jev-multipart-done-criteria.py
python scripts/test-jev-scope-coverage-done-criteria.py
```

Then run repository gates:

```text
python lint/run.py
python scripts/run_ci.py --stage source
python scripts/run_ci.py
```
