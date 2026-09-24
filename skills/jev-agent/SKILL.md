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

- `alignment/` owns the self-alignment capability (`JevAgentSettings(self_align=True)`). `JevAgentAlignment` is a `BaseAgent` subclass: it asks the fixed questions in `alignment/questions.py`, routes each "no" to an editable section or to `owner_actions`, runs its own loop with the single `edit_system_prompt_section` tool against a run-local `JevPromptDraft`, and keeps only the edits a second Jev call confirms. `JevRuntime.arun` swaps the result into this run's context and run-local runtime and attaches it as `metadata["jev_alignment"]`.

- Tool alignment (`JevAgentSettings(tool_align=JevToolAlignmentSettings(...))`) lives in the same `JevAgentAlignment` class, as helper methods: detect (Jev, reusing the prompt pass's scope gate when there was one), needs (a scout `BaseAgent` with four fixed tools that forward to the class), coverage (Jev, one question per existing tool), search (`vidbyte/providers/tool_catalogs/`), facts (install kind, pin, secrets), open (connect before judging), candidate checks (Jev, with request-independent answers cached per description), approve, and attach. `JevRuntime.arun` adds the attached tools to this run-local runtime, releases their MCP sessions in a `finally` block, attaches `metadata["jev_tool_alignment"]`, and appends a code-written "Tools added" footer unless the output is structured.

Without `self_align` or `tool_align`, the scaffold performs no Jev call. A missing TypeSafe API key must not prevent `JevAgentSettings` or `JevAgent` construction until an enabled capability actually needs Jev.

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
- Self-alignment edits only the main agent's current run: never `JevAgentSettings`, `JevAgent.system_prompt`, the editor's own prompt, or later runs.
- Alignment edits are additive and limited to operational sections (tools, method, output, exceptions, priorities, glossary). Role, scope, boundaries, audience, knowledge, and permissions are reported to the owner, and a failed fit gate never produces an edit.
- Alignment fails open for the run (original prompt) and closed for edits (an unverified edit never runs).
- Tool alignment attaches tools to the current run only: never to `JevAgentSettings.tools`, `JevAgent.tools`, or later runs. Every MCP session it opens is either attached to the run and released when the run ends, or closed before `align_tools()` returns.
- The scout may only cite entries its own searches returned in this pass, describe an entry before proposing it, and propose tool names that entry lists. Jev judges the live tool text that will run, never the scout's summary.
- A tool attaches only when `performs_need`, `serves_request` (which reads the user's own words), and `describes_only` pass, plus `named_system` when the user named a system, and when its effect is allowed: reads always; writes only when the request asks for a change; sends, deletes, or unclear effects only with `allow_high_impact`. A server's declared destructive hint is trusted; a read-only hint never lowers Jev's answer.
- Local installs (container, package) run only when the owner allows their kind and they are pinned. Secrets go only where their install declares them and never into results, metadata, or the scout's context.
- Tool alignment fails open for the run (original tools) and closed for attaching (an unapproved tool never attaches).

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
