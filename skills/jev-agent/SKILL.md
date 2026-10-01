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
- `done/` holds the done checks. `run_state.py` (`JevRunState`) writes request-derived state once before the main loop; at each finish attempt `handoff.py` (`JevHandoff`) compiles evidence from the main agent's `ContextManager` of response and tool-call primitives. PHASE_PROGRESS checks substantive activity for request-derived stages and passes without questions when no stages are identified. SCOPE_COVERAGE checks each required member of a request-defined group, with missing work or workspace inventory preserved as continuation gaps; one bounded request-only breadth review can upgrade a narrowly labeled group before work. TARGET_OUTCOME and MOTIVATING_CASE check request-derived targets and user-named unusual scenarios against evidence from each finish attempt. INPUT_SET_COVERAGE checks user-bounded inputs the request asks the agent to engage. OUTPUT_COUNT checks explicit quantities inside requested outputs using visible candidates, evidence, and deterministic counts. OUTPUT_EXTENT checks explicit text targets with a requested amount, unit, and minimum/exact/maximum comparator; code measures supported units of the raw final answer and applies the comparator without changing its direction. The handoff can derive items from the finished answer, as CLAIMS does, observed run problems as PROBLEMS_RESOLVED does, whole-task completion status as COMPLETION_EVIDENCE does, or plan/account comparisons as REPORT_ACTION_ALIGNMENT does, when those items cannot exist before work. REPORT_ACTION_ALIGNMENT uses explicit earlier plans, recorded execution, the final account, and the user's actual requirements; an optional plan change is not unfinished work by itself. PROBLEMS_RESOLVED adds one required original-request item beside dynamic problem items; COMPLETION_EVIDENCE adds one stable task_completion item and keeps its handoff gap out of Jev's evidence state. `JevRunState` combines every enabled check's questions (one per item) into one Jev request over one shared state, scores the answers with `score_noul`, and returns the checks that failed. Request-derived checks such as PHASE_PROGRESS add run-state and handoff sections; post-run-derived checks such as CLAIMS, PROBLEMS_RESOLVED, COMPLETION_EVIDENCE, and REPORT_ACTION_ALIGNMENT add only a handoff section and build their questions from it.
- `continuation/` holds the continuations. `base.py` (`JevContinuation`) is the contract the runtime calls: `should_continue` and `continue_`. `done.py` (`JevDoneContinuation`) runs `JevRunState.check` and, while continuations remain (`JevContinualSettings.max_continuations`), sends the main agent the original request, the run state, the handoff, and the failed Jev questions, with focus on what is missing, through the `jev_continuation/continue_prompt.md` prompt asset. A new way to continue a run is a new subclass here.
- `response.py` (`JevResponse`) is the only writer of `JevAgentResponse`. Features report outcomes through its methods, never through result metadata.
- `vidbyte/lib/jev/presets.py` (`JevPresets`) owns the preflight flags a user enables through `JevRuntimeSettings.preflight`, and the fixed question keys and threshold of each fixed-question flag.
- `vidbyte/lib/jev/preflight/` is the canonical home of every fixed preflight question, one dataclass per question (`clarity.py`), the specialist Choice question (`specialist.py`), and `JevPreflightRegistry`, the registry over them (`get`, `questions`, `specialists`, `validate`). The flag and question-key enums live in `vidbyte/lib/enums/jev.py`; the preflight records live in `vidbyte/lib/dataclasses/jev.py`.
- `vidbyte/lib/jev/done/` holds every fixed done question (`multi_part.py`, `input_set_coverage.py`, `output_count.py`, `output_extent.py`, `report_action_alignment.py`, `claims.py`, `motivating_case.py`, `scope_coverage.py`, `problems_resolved.py`, `target_outcome.py`, `phase_progress.py`) and `JevDoneRegistry` (`question`, `threshold`, `resolve`, `validate`). The structured-reply payloads (every field described in 4–6 sentences), the run-state, handoff, input-set, output-count, output-extent, report/action alignment, claim, phase-progress, scope-coverage, target-outcome, motivating-case, problem, and done records, and `JevDoneQuestion` live in `vidbyte/lib/dataclasses/jev.py`; `JevDoneCheck`, `JevDoneQuestionKey`, and dynamic item-kind enums live in `vidbyte/lib/enums/jev.py`.
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
2. Add its state and evidence section payloads and records to `vidbyte/lib/dataclasses/jev.py`. Add a run-state section only when item identities are known before the main agent works; dynamic items belong only in the handoff.
3. Load `skills/asking-jev-questions/SKILL.md` first, then write its question as a `JevDoneQuestion` subclass under `vidbyte/lib/jev/done/` and register it and its threshold constant in `JevDoneRegistry`.
4. Add sections to the schemas that carry the check's items and convert them in the relevant `_record` methods. Put the check-specific projection, scorer, and feedback in typed helpers, then add their handlers to the `_section`, `_judge`, and `_explain` dispatch maps.
5. Extend `tests/test_jev_done.py`.

**Request-derived stages:** PHASE_PROGRESS records required stages before the main loop starts, so their identities belong in `JevRunStateRecord`; the handoff must return evidence for exactly those ids. Each stage is judged for substantive requested work, not deliverable completion. A request with no meaningful stages passes without questions.

**Post-run-derived items:** CLAIMS cannot add a predicted list to `JevRunStateRecord`, because concrete claims do not exist until the main agent writes its final answer. ASSUMPTIONS_RECONCILED is also handoff-only: include each explicit consequential premise later contradicted or materially changed by concrete run evidence, even when downstream work was revised, left unchanged, abandoned, or shown irrelevant. Keep `missing` separate from Jev's evidence, ask one question per qualifying premise, and continue only failed items with their basis, later observation, affected work, revision, and evidence. Do not treat uncertainty, lack of verification, or a plan change alone as a changed assumption. PROBLEMS_RESOLVED likewise cannot predict mid-run failures. Add its section and typed records to `JevHandoff`, validate unique ids and exactly one `original_request_completion` item there, then build one question per handoff item in `JevRunState._section`. Its continuation focus must fully repair and revalidate failed problems, then return to the original request and complete remaining work. COMPLETION_EVIDENCE remains handoff-only because the answer's status and run observations exist only after work.

**Bounded input engagement:** INPUT_SET_COVERAGE writes request-derived targets once, then requires matching evidence entries from each finish attempt's handoff. Keep the requested extent and action explicit, treat location/listing/failed-call evidence as distinct from successful content access, exclude the handoff's `missing` feedback from Jev state, and leave dynamic or paginated universes to a separate exhaustion check.

**Dynamic collection exhaustion:** INPUT_EXHAUSTION is for an explicitly requested traversal of a dynamic collection to its boundary. Preserve any requested total and unit in run state; the handoff reports trace-backed distinct identifiers, source totals, current continuation state, terminal evidence, and unresolved retrieval failures. Code compares distinct counts only for matching units, and open continuations or failed retrievals remain incomplete even when counts match. With no comparable total, require affirmative terminal evidence; an empty result needs explicit zero or terminal evidence. Keep `missing` and `next_step` for continuation feedback, outside Jev's evidence state. A missing or malformed state, handoff, or answer remains unavailable and fails open.

**Numeric output quantities:** OUTPUT_COUNT records one obligation for each requested quantity and group, even when the final answer makes no count claim. Keep the positive target, unit, scope, distinctness rule, and completion criterion in the request-derived state; the handoff supplies each visible candidate's value and direct run evidence plus a proposed distinctness key. Code normalizes and counts keys deterministically and computes whether the target is met. Jev judges whether the candidates and keys faithfully represent qualifying output units without doing arithmetic.

**Text output extents:** OUTPUT_EXTENT records only a clear numeric text bound tied to a named target. Preserve its amount, unit, and minimum, exact, or maximum comparator. Code measures the raw final answer only for supported units and applies that exact comparator; other artifact targets require direct evidence and remain unmeasured when code has no safe basis.

**Report/action alignment:** REPORT_ACTION_ALIGNMENT is post-run-only because explicit plans, actual execution, and the final account exist only after work. Create candidates only when an earlier visible plan or commitment is referred to by the final account, include aligned and potentially misaligned items, and record how each plan step relates to the original request. Jev judges each candidate independently; a plan change is not a failure by itself, and continuation should correct an inaccurate account or complete only a result the user still requires.

**Changed-assumption reconciliation:** ASSUMPTIONS_RECONCILED checks whether downstream work was brought into line after an explicitly used premise changed. Keep candidates whose work was revised, left unchanged, or made irrelevant; Jev judges each from run evidence. Acknowledgment alone does not pass, but do not require a generic repair or validation ritual when the evidence already shows the work was reconciled or no longer applies.

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
agent = JevAgent(settings, JevRuntimeSettings(preflight=(JevPreflightPreset.CLARITY,), continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART, JevDoneCheck.SCOPE_COVERAGE), max_continuations=2)))
```

The equivalent namespace constructor is `sdk.agents.jev(settings, runtime_settings)`. After a run, `agent.response.specialist` names the specialist that ran the task, or is `None` when the main agent ran it. `agent.response.done[JevDoneCheck.MULTI_PART]` reports whether every requested deliverable was shown produced in full; `agent.response.done[JevDoneCheck.SCOPE_COVERAGE]` reports whether every required group member has evidence of the requested change.

Enable the motivating-case continuation gate with `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.MOTIVATING_CASE,)))`. It records request-named boundary conditions before work, checks the current run evidence at each finish attempt, and continues the same loop when a required case is not shown handled. The normal continuation cap and fail-open behavior apply; its records are available through `agent.response.run_state.motivating_case`, `agent.response.handoff.motivating_case`, and `agent.response.done[JevDoneCheck.MOTIVATING_CASE]`.

Enable the phase-progress gate with `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.PHASE_PROGRESS,)))`. It records meaningful request-required stages before work and checks each stage against current run evidence at finish attempts. It checks whether requested work was substantively entered, not whether all outputs are complete; requests with no meaningful stages pass without questions. Results are available through `agent.response.run_state.phase_progress`, `agent.response.handoff.phase_progress`, and `agent.response.done[JevDoneCheck.PHASE_PROGRESS]`.

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
