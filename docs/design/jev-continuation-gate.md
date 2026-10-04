---
spec: jev-continuation-gate
title: JEV Continuation Gates and Stable Run Context
status: pr-open
revision: 1
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
base_commit: 7a174bb2a2b22b65f94fddd960a02846e2e08c26
created: 2026-10-03
updated: 2026-10-04
approved_revision: r1
pr: https://github.com/cerredz/Vidbyte-SDK/pull/509
---

# Spec: JEV Continuation Gates and Stable Run Context

> **TL;DR** — Rename the public JEV done-check configuration to continuation gates, with a `same_context` option selecting the continuation path. During a run, render one frozen run-state primitive and keep the latest handoff and a unified gate assessment in replaceable, run-local context slots; every enabled gate gets a current status, while only failed gates get the longer #508 explanation and question context.

## §0 User prompts (verbatim)

### 0.1 Original request

```text
Recently figured out that this was the case for the jevAgent inside of the vidbyte-sdk/ (look through code first):  Context grows in same-context mode: each round appends
    the full request, run state and handoff again on top of
    the existing history. With max_continuations=2, that's
    two large blocks on top of the original transcript.
    Compaction middleware, if enabled, is what keeps this
    bounded.


this is not the way that i want to do things. i think that ideally I just want to keep the same run state and handoff block, and never change them, (it is important to note that we are actually putting the context of the failed queestions inside of the context window,   can look ar pr #506), with this being said. What is the best approach going forward to not make it so that context window does not blow up ffrom run state and handoff objects. i think that best is just to make it so that they dont change, we have one, and then pr 506 handle the continuation gates context, let me know what you think
```

### 0.2 Steering messages

- `what is this "same context  mode" that you speak of?`
- `show me how a user plays with this setting`
- `wait, why are there done checks and continuation  gates? i thought that we renamed/merge the done checks into the continution gates?`
- `so the continuation gates are not like done checks in the sense that they run through jevv questions right?`
- `okay great, can you sketch out the following: 1) renaming the 'done checkks' feature/setting to 'continuation_gate' and then inside of this gate choosing the enable or disable the same context window feature. then 2) explaining how to integrate 1 run state throughout the run and iterated handoffs throughout the run`
- `and before implementation, can you scope out this change in terms of files/functions that we have to add`
- `$spec-create great, create a spec for this request`

#### implementation instructions — 2026-10-04
$spec-implement great, you can implement the spec

#### implementer question — 2026-10-04
1

---

## Part A — Framing

## §1 Problem statement

When an enabled JEV check fails at a finish attempt, `JevDoneContinuation.continue_()` appends a user message containing the original request, rendered run state, current handoff, failed questions, and focus to the existing `messages` list. The next finish attempt appends another full copy. With the default continuation cap, the main model can receive multiple copies of large state/evidence blocks in addition to its normal tool and answer history. Compaction can reduce this, but the growth is not bounded by the continuation design itself (`vidbyte/agents/jev/continuation/done.py:continue_`, `message`; `vidbyte/agents/jev/settings.py:JevContinualSettings`; shared failed-gate descriptions came from merged PR #506 and same-context rendering was added in #508).

The caller wants a public setting named around continuation gates, a choice between same-context and fresh-worker continuation, one run state for the entire run, and a single latest handoff and gate assessment that are updated in place. Gate evaluation still runs the configured fixed Jev questions; continuation gates are the renamed completion checks, not a separate gate that bypasses Jev (`vidbyte/agents/jev/done/run_state.py:check`, `vidbyte/lib/jev/done/done.py`). PR #506's fresh renderer reports every enabled gate's current status and failed question text; #508 adds longer explanations for failed checks only in the same-context path. This change reuses one assessment builder so both modes receive the full current status list and the #508 explanation/question detail for failed gates.

## §2 Goals and success criteria

| ID | Goal (outcome) | Metric | Target | Leading/Lagging | How measured |
|---|---|---|---|---|---|
| G-1 | Same-context retries do not accumulate repeated JEV context blocks. | Count of current run-state, handoff, and gate-assessment blocks in each provider call. | Exactly one of each while enabled; zero when the feature is disabled. | Leading | Capture provider-call system and message payloads over at least three failed finish attempts. |
| G-2 | The model sees current evidence and gate failures after every failed finish attempt. | Snapshot version/content in successive calls. | Run state remains identical; handoff and assessment match the latest attempt. | Leading | Assert against controlled handoff and failed-question fixtures. |
| G-3 | Users configure the feature under one continuation-gate setting. | Public configuration and response terminology. | No public `continual`/done-check mode ambiguity; `same_context` selects the path. | Leading | Import/configuration tests and documentation examples. |
| G-4 | Existing completion evaluation remains correct. | Jev requests per finish attempt and returned gate results. | One batched Jev request per attempt where questions are applicable; all latest outcomes remain inspectable. | Lagging | Existing and updated JEV completion-gate tests. |

## §3 Non-goals / out of scope

- **NG-1** — Redesign completion criteria, thresholds, evidence schemas, or Jev question wording — the request changes names and context retention, not what constitutes completion.
- **NG-2** — Make all conversation history bounded — ordinary assistant turns, tool results, and the fresh worker's output remain governed by existing loop and compaction policies.
- **NG-3** — Make `same_context=False` start a new top-level JevAgent run — current fresh continuation uses a clean repair worker and returns its answer to the existing main loop; changing that lifecycle is a separate product decision.
- **NG-4** — Add automatic context compaction or token budgeting for a single unusually large handoff — this change prevents historical copies from accumulating, but does not cap the size of the latest evidence snapshot.
- **NG-5** — Rename the implementation directories from `done/` to `continuation_gate/` — retain the existing fixed-question and scoring layout to keep the change focused.

## §4 User stories

**Persona: SDK caller**
- **US-1** — As a JevAgent caller, I want to configure enabled continuation gates and `same_context` in one setting, so that I can choose how failed completion checks return work to the agent.
- **US-2** — As a JevAgent caller, I want the run state to remain the same and the handoff and gate assessment to show only their latest version, so that retries do not multiply those blocks in the context window.
- **US-3** — As a JevAgent caller, I want to inspect the latest result for each enabled gate on `JevAgent.response`, so that I can understand why the answer continued or stopped.

**Persona: SDK maintainer**
- **US-4** — As a maintainer, I want gate evaluation to remain at the existing finish-attempt seam and use the existing context manager, so that the change does not introduce a second evaluation loop or context store.

---

## Part B — Behavior (this is the spec; everything else is framing)

## §5 Behavior invariants

- **INV-1** — An enabled continuation-gate setting evaluates every configured gate at each main-agent finish attempt using the existing run-state/handoff evaluation path. *(tested by: §12 → `tests/test_jev_done.py`)*
- **INV-2** — The initial run state is generated once before the main loop. Its record and rendered text do not change during that run. *(tested by: §12 → new stable-context runtime test)*
- **INV-3** — In same-context mode, each provider call contains at most one managed run-state block, one latest handoff block, and one latest gate-assessment/continue instruction block. The original request is not copied into those blocks. *(tested by: §12 → new stable-context runtime test)*
- **INV-4** — After each finish attempt, the handoff and gate-assessment slots are replaced by the current attempt's content; if no current handoff is available, remove the prior handoff slot rather than presenting it as current. Old versions do not remain in the context manager or conversation history. *(tested by: §12 → new stable-context runtime test)*
- **INV-5** — One shared assessment builder iterates every enabled gate on each attempt and includes its current status; for failed gates it also includes the #508 description, failed question text, and focused missing-work explanation. A later passing or unavailable result replaces the previous failure instead of retaining stale failure text. *(tested by: §12 → fresh and same-context gate-context tests)*
- **INV-6** — With `same_context=True`, failed work returns to the existing main loop, preserving its ordinary transcript, tools, and loop budgets. *(tested by: §12 → `tests/test_jev_done.py`)*
- **INV-7** — With `same_context=False`, the existing fresh repair worker starts with an empty worker history and returns its output to the current main loop; this flag does not create a new JevAgent run. *(tested by: §12 → `tests/test_jev_fresh_continuation.py`)*
- **INV-8** — The continuation cap, including zero, remains enforced; a failed gate at the cap is reported on the response but does not launch another continuation. *(tested by: §12 → `tests/test_jev_done.py`)*
- **INV-9** — Missing state, missing handoff, unavailable decision results, or a fresh-worker SDK error fail open as they do today: the latest main-agent answer stands and no stale context slot is presented as current. *(tested by: §12 → done and fresh continuation tests)*
- **INV-10** — Continuation snapshots are stored in a JEV-owned overlay for one `JevRuntime` invocation and never mutate the agent-level `ContextManager` shared across runtime instances. The existing JEV feature objects are single-run objects; simultaneous runs on one `JevAgent` remain unsupported by that contract. *(tested by: §12 → overlay isolation test)*

**Must not regress:**
- **INV-11** — Every enabled gate's applicable fixed questions continue to be sent in one shared Jev decision request per finish attempt; gate evaluation is not replaced by natural-language generation through the main runner. (`vidbyte/agents/jev/done/run_state.py:combine`, `vidbyte/lib/jev/decision.py:DecisionModelHelper`; tested by `tests/test_jev_done.py`.)
- **INV-12** — JEV outcomes continue to be written through `JevResponse` and exposed on `JevAgent.response`, not added to generic result metadata. (`vidbyte/agents/jev/response.py`; tested by `tests/test_jev_agent.py` and `tests/test_jev_done.py`.)

## §6 Acceptance criteria

| ID | Given | When | Then | Priority | Proof |
|---|---|---|---|---|---|
| AC-1 | A same-context run has at least three failed finish attempts and distinct handoffs | Each attempt is assembled for the main runner | Every call has one run-state block with identical content, one handoff with that attempt's content, and one latest gate assessment; no previous snapshot block remains | P0 | `tests/test_jev_done.py::JevDoneRuntimeTests::test_same_context_replaces_stable_continuation_slots` — captured provider payload across four calls verifies one frozen state, current handoff, and replaced slots |
| AC-2 | Shared gate descriptions from #506 produce different failed questions across attempts | The same-context continuation assessment is rendered | It contains the current enabled-gate statuses and only the latest failed question text | P0 | `test_same_context_replaces_stable_continuation_slots` and `tests/test_jev_fresh_continuation.py::test_gate_assessment_lists_enabled_gates_and_recomputes_failed_questions` — later question text replaces earlier failed text |
| AC-3 | A caller configures `same_context=False` and a gate fails | The fresh continuation path runs | The fresh worker receives the current request, immutable run state, latest handoff, and gate assessment; its response returns to the main loop without a duplicate full prompt block | P0 | `tests/test_jev_fresh_continuation.py::test_failed_check_runs_in_clean_context_and_returns_response_to_main_loop` and `test_fresh_gate_uses_latest_stable_snapshots` — clean history, latest snapshots, and reply handoff |
| AC-4 | No gates are enabled, or `max_continuations=0` | The run reaches a finish attempt | No repair is started; zero-cap runs still evaluate and expose gate results when gates are enabled | P0 | `tests/test_jev_agent.py` and `tests/test_jev_done.py::JevDoneRuntimeTests` — disabled gates stop, zero cap records outcomes without retry |
| AC-5 | A caller uses the renamed public configuration and result surface | The SDK is imported and a run completes | The new `continuation_gate` setting and response field are available; removed public names are documented as migration changes | P0 | `tests/test_jev_agent.py` — public construction, import, renamed settings, and `response.continuation_gates` coverage; README and JEV guide examples updated |
| AC-6 | A single handoff is large but history has no duplicate JEV blocks | A continuation is assembled | Only one latest handoff is present; its size is not silently truncated by this change | P1 | `tests/test_jev_done.py::JevDoneRuntimeTests::test_overlay_preserves_full_latest_handoff` — 8,000 repeated evidence units and the terminal marker survive in the single assembled slot |

## §7 Edge cases, failure modes, and rollback

| ID | Trigger (input + state) | System behavior | User sees | Covered by |
|---|---|---|---|---|
| EC-1 | Run-state generation returns no usable state before the loop | Do not install an empty or previous-run state primitive; existing fail-open check behavior stands | Main-agent response without continuation-gate state | INV-9 |
| EC-2 | Handoff compilation fails or yields no usable handoff while a gate fails | Do not continue using a prior handoff as if it were current | Current main-agent answer and latest unavailable result | INV-9 |
| EC-3 | Later attempt passes or decision model is unavailable after an earlier failed question | Replace the assessment with current status, including no failed question where appropriate | Latest result rather than stale failure direction | INV-5 |
| EC-4 | Continuation limit is zero or reached | Keep latest gate results; do not extend the main loop | Existing answer plus inspectable gate result | INV-8 |
| EC-5 | Fresh repair worker raises `VidbyteSdkError` or returns empty output | Leave the main answer in place; do not insert stale output/evidence | Existing answer | INV-9 |
| EC-6 | Two calls use the same `JevAgent` concurrently | Unsupported by the existing `JevContinuation`/`JevRunState` single-run instance contract; the implementation must not claim concurrency safety or broaden this change to rework response ownership | No guarantee; callers must not overlap calls on one instance | INV-10; A-5 |
| EC-7 | One latest handoff or assessment itself is very large | Keep one copy; existing context compaction may still compact transcript messages, but this change adds no truncation policy | A large current snapshot may still consume many tokens | AC-6; accepted limitation under NG-4 |
| EC-8 | User has code using the old public names | Alpha SDK breaking rename requires caller update; no automatic runtime migration | Import/configuration error until migrated | §18 |

**Rollback of the user action:** Caller can disable continuation gates by omitting the setting or setting no enabled gates. Reverting the SDK release restores the old public API and accumulating-message behavior; there is no persisted data to migrate or roll back.

## §8 Prioritized requirements

**Functional**

| ID | Requirement | Priority | Source (§0/§1/US-) |
|---|---|---|---|
| FR-1 | Replace the public `continual`/done-check configuration group with `JevRuntimeSettings.continuation_gate: JevContinuationGateSettings`, including enabled gate values, `same_context`, and the existing continuation limits. | P0 | §0, US-1 |
| FR-2 | Rename the public gate/check vocabulary and response result map so callers inspect the latest `continuation_gates`; keep question definitions and evaluation behavior unchanged. | P0 | §0, US-3 |
| FR-3 | Create one immutable run-state snapshot per enabled-gate run and expose it for the entire run. | P0 | §0, US-2 |
| FR-4 | Store the latest handoff and latest shared failed-gate assessment in stable, replaceable runtime context slots; do not append full request/state/handoff/assessment blocks to the same-context transcript on every retry. | P0 | §0, §1, US-2 |
| FR-5 | Preserve the same-context and fresh-worker continuation behavior, selected by `same_context`. | P0 | §0, US-1 |
| FR-6 | Keep one batched Jev evaluation per finish attempt and expose each enabled gate's latest outcome through the response writer. | P0 | §0, US-3 |
| FR-7 | INV-12 | AC-5 | docs/import checks; full suite | P1.T1, P1.T3 | README, JEV READMEs, both JEV skills, and all six authorized caller-facing feature docs updated; remaining references in README migration guidance, archival `docs/design/jev-*.md` records, and `AGENTS.md` are historical/reference-only |

**Non-functional**

| ID | Requirement | Priority | Target |
|---|---|---|---|
| NFR-1 | Repeated retries must not increase the number of managed JEV state/handoff/assessment copies. | P0 | Exactly one current block for each slot in each same-context provider call. |
| NFR-2 | Runtime-owned JEV context must be isolated from persistent/shared caller context and other invocations. | P0 | No mutation of `JevAgent.context_manager`; each runtime invocation's context manager owns the slots. |
| NFR-3 | The current handoff must remain complete and reviewable. | P1 | No truncation or new serialization dependency. |

## §9 Constraints

- **Public API is alpha and may break** — *Rules out:* keeping both meanings of `JevContinuationGate` under the same compatibility alias — *Source:* `AGENTS.md` states the SDK is alpha and APIs may change between minor versions; `CONTRIBUTING.md` still requires compatibility implications to be documented.
- **JEV capability placement rules** — *Rules out:* adding records or enums under `vidbyte/agents/jev/`, or question text under `vidbyte/prompts/` — *Source:* `AGENTS.md` §JEV File Locations and `field-guide/vidbyte-sdk/jev-capability-layout.md`.
- **Context primitives support managed upsert and freeze** — *Rules out:* a new snapshot store or custom message-history registry — *Source:* `vidbyte/context/manager.py:upsert`, `set_frozen`, and `vidbyte/context/primitives/documents.py:TextContextItem`.

---

## Part C — Design

## §10 Architecture and implementation decisions

### 10.1 Flow

1. Caller configures `JevRuntimeSettings.continuation_gate` → 2. `JevAgent` builds the gate evaluator, run state, continuation strategy, and response writer once → 3. `JevRuntime.arun()` generates the run state once and installs a frozen item in its JEV-owned overlay manager → 4. On each finish attempt, `JevRunState.check()` compiles the latest handoff and evaluates enabled gates in one Jev request → 5. `JevResponse` records current results; one shared renderer assembles PR #506's status for every enabled gate and #508's explanation/question details for failed gates, then the continuation upserts that assessment and latest handoff in the overlay → 6. `JevRuntime._build_conversation_messages()` appends only the overlay's current messages after the inherited provider messages, without changing `messages` → 7. Same-context mode returns to the current loop with its ordinary history and one current snapshot of each slot; fresh mode gives the current snapshots to a clean repair worker and appends only its reply to the main loop.

### 10.2 Decisions

| ID | Decision | Deciding reason | Runner-up | Flips if |
|---|---|---|---|---|
| D-1 | Keep continuation snapshots in a JEV-owned overlay `ContextManager` on the invocation's fresh `JevRuntime`, using stable primitive IDs; freeze run state and upsert handoff/assessment. Append the overlay's managed conversation messages in the existing provider-message assembly hook without writing to `AgentRuntime.context_manager`. | `BaseAgent._runtime()` constructs a runtime for execution, while `AgentRuntime` retains the agent-level manager reference; a separate overlay gets managed replacement without mutating agent-owned context. | Replace a prior continuation message in the mutable history list. | Runtime construction becomes shared across calls and can no longer own an invocation-local overlay. |
| D-2 | Keep one fixed run-state snapshot; treat each compiled handoff and gate assessment as latest-value slots. | Run-state is derived once from the original request; evidence and failed questions are attempt-specific and must refresh. | Freeze both run state and handoff forever. | Product intent requires the initial handoff to remain unchanged; that would conflict with current per-attempt evidence checks. |
| D-3 | Rename the public settings/result vocabulary to continuation gates while retaining `done/` source layout and fixed-question records that are not public configuration. | It resolves the user's public naming confusion without renaming every internal question/evidence concept or moving modules. | Rename every internal class, file, prompt, and test containing “done”. | Repository-wide terminology consistency is judged more valuable than limiting the change to the public feature surface. |
| D-4 | `same_context=True` means the same main loop; `False` preserves the existing fresh repair worker that returns output to the same main loop. | This matches current mode semantics and makes the flag compatible with existing behavior. | Make `False` start a new main-agent run with a clean loop. | User confirms that “disable same context” means discard the main loop history and restart the main agent. |
| D-5 | Share one gate-assessment renderer between both continuation paths: every enabled gate gets the #506 status; failed gates additionally get their #508 description, failed question text, and focus. | #506 and #508 currently divide these details across the fresh and same-context implementations; one current snapshot avoids behavioral drift and stale failed questions. | Keep two renderers and accept different context depending on mode. | Product intentionally wants fresh and same-context workers to receive different gate context. |

### 10.3 Patterns inherited

- **Managed context primitive upsert** — stable ID replaces a single value; freezing protects immutable run-state — `vidbyte/context/manager.py:upsert`, `set_frozen`, and `ContextManager.render_primitives_zone()`; use a JEV-owned overlay because `AgentRuntime.__init__` stores the passed agent-level manager reference.
- **Run-local feature construction** — `JevAgent` constructs feature objects and passes them to `JevRuntime`; response changes go through `JevResponse` — `vidbyte/agents/jev/agent.py` and `vidbyte/agents/jev/response.py`.
- **Batched fixed-question evaluation** — all enabled gate questions share one `DecisionModelHelper` request — `vidbyte/agents/jev/done/run_state.py:combine` and `vidbyte/lib/jev/decision.py`.
- **Latest gate assessment** — rebuild the assessment from current results, rather than carrying old failed-question text — `vidbyte/agents/jev/continuation/fresh.py:_render_gate_assessment` (#506) and `vidbyte/agents/jev/continuation/done.py:_failed_check` (#508); the feature should consolidate their output into one renderer.

### 10.4 Smaller design rejected

Only rename `JevContinualSettings` and leave `continue_()` appending its formatted message. That fails INV-3/FR-4: the same full request, run-state, and handoff still accumulate in message history, so names improve while the reported context-growth defect remains.

### 10.5 Complexity budget

| Item | Count | Justification for each |
|---|---:|---|
| New files | 1 design artifact; 0 production files | This requested spec is the sole created file; implementation extends existing settings, continuation, response, and runtime seams. |
| New classes/modules | 1 new settings class | `JevContinuationGateSettings` groups the renamed public gate options and existing cap/limits. Existing enum/record classes are renamed rather than duplicated. |
| New dependencies | 0 | Existing ContextManager and typed JEV models cover the need. |
| New config keys | 2 | `JevRuntimeSettings.continuation_gate` replaces `continual`; `same_context` replaces the old mode enum. Existing `checks` becomes `enabled`; continuation cap and policy limits move into the new group. |
| New constants | 3 | Stable primitive IDs for run state, latest handoff, and latest gate assessment prevent scattered slot-name literals. |
| New collections/tables | 0 | Per-run context slots are in-memory managed primitives, not persisted data. |
| New public endpoints/commands | 0 | Python SDK configuration and response surface only. |

### 10.6 Key interfaces

```python
@dataclass(frozen=True, slots=True)
class JevContinuationGateSettings:
    enabled: tuple[JevContinuationGate | str, ...] = ()
    same_context: bool = True
    max_continuations: int = JEV_DONE_MAX_CONTINUATIONS
    # Existing Jev run-state, handoff, review, and bounded extension limits remain here.

@dataclass(frozen=True, slots=True)
class JevRuntimeSettings:
    continuation_gate: JevContinuationGateSettings = field(default_factory=JevContinuationGateSettings)

class JevContinuation:
    def continue_(self, messages: list[dict[str, Any]], context_manager: ContextManager) -> JevContinuationEvidence | None: ...
```

`JevRuntime` creates one overlay `ContextManager` per runtime invocation and passes it through the existing continuation hook. Override the concrete existing seam `AgentRuntime._build_conversation_messages(messages)` in `JevRuntime`: call `super()`, then append `overlay.render_conversation_messages(ContextWindowPlacement.END_OF_CONVERSATION)`. This makes the overlay visible to provider calls without mutating the shared `AgentRuntime.context_manager` or the accumulating `messages` list. Do not add a second context store.

The concrete method changes are: `JevRuntime.arun()` installs the frozen run-state item after `JevRunState.begin()`; `JevDoneContinuation.continue_()` updates handoff and assessment slots instead of appending its formatted prompt; a shared `JevDoneContinuation._render_gate_assessment()` builds statuses and failed-gate detail for both same-context and fresh paths; and the `JevRuntime._build_conversation_messages()` override renders the current overlay on every provider call.

## §11 Codebase grounding

- **Repo rules read:** `AGENTS.md` requires settings in the owning agent's `settings.py`, enums in `vidbyte/lib/enums/jev.py`, records in `vidbyte/lib/dataclasses/jev.py`, a single `JevResponse` writer, and design documents under `docs/design/`; `CONTRIBUTING.md` requires public API compatibility implications and the full CI gate. No nested `AGENTS.md` governs the touched JEV paths.
- **Field guide:** `field-guide/vidbyte-sdk/init.md` and `jev-capability-layout.md`; fixed-question definitions stay in `vidbyte/lib/jev`, feature actions under `vidbyte/agents/jev`, settings split between `JevAgentSettings` and `JevRuntimeSettings`, and all enabled gate questions are batched.
- **Stack (from manifests):** Python `>=3.11` (`pyproject.toml`); pytest `8.3.5`, pytest-asyncio `1.3.0`, Ruff `0.16.4`, mypy `2.3.1` in `[dev]`. This path has no database or web framework.
- **Commands (exact):**
  - Install: `python -m pip install -e ".[dev]"`
  - Typecheck: no standalone typecheck command is defined; `python scripts/run_ci.py --stage source` runs lint, compile, repository checks, and pytest.
  - Lint: `python lint/run.py`
  - Test (focused): `python -m pytest tests/test_jev_done.py tests/test_jev_fresh_continuation.py`
  - Test (full): `python -m pytest`
  - Full CI gate: `python scripts/run_ci.py`
- **Directory layout relevant to this change:**
  ```text
  vidbyte/agents/jev/{agent.py,runtime.py,response.py,settings.py}
  vidbyte/agents/jev/continuation/{base.py,done.py,fresh.py}
  vidbyte/agents/jev/done/{run_state.py,handoff.py}
  vidbyte/lib/dataclasses/jev.py
  vidbyte/lib/enums/jev.py
  vidbyte/lib/jev/done/{done.py,question modules}
  vidbyte/context/{manager.py,primitives/documents.py}
  tests/{test_jev_done.py,test_jev_fresh_continuation.py,test_jev_agent.py}
  ```
- **Nearest sibling feature (the template to copy):** `vidbyte/agents/jev/continuation/fresh.py` — retain its fresh-worker lifecycle and #506 assessment builder, reusing that assessment shape in same-context mode as #508 does today.
- **Reusable pieces:** `JevRuntime._continue_finish_attempt` (`vidbyte/agents/jev/runtime.py`) is the finish-attempt seam; `JevRunState.begin/check` (`vidbyte/agents/jev/done/run_state.py`) owns fixed state and per-attempt handoff/evaluation; `ContextManager.upsert/set_frozen` (`vidbyte/context/manager.py`) owns stable replacements; `TextContextItem` (`vidbyte/context/primitives/documents.py`) is the typed managed text primitive; `JevResponse` (`vidbyte/agents/jev/response.py`) owns public result updates.
- **Code-style exemplar** (`vidbyte/agents/jev/runtime.py`):
  ```python
        if self.run_state is not None:
            await self.run_state.begin(message, prior_user_turns=self._prior_user_turns(context.history))
            sequence_instructions = self.run_state.agent_instructions()
            if sequence_instructions:
                context = replace(context, system_prompt=f"{context.system_prompt or ''}\n\n{sequence_instructions}")
  ```
- **Domain glossary:** *continuation gate* — one configured fixed-question completion evaluation; *same-context* — the existing main loop and transcript continue; *fresh worker* — one clean repair agent whose output returns to the existing loop; *handoff* — evidence compiled from the latest run events and responses.
- **Existing design constraints:** `docs/design/jev-continuation-check-context.md` records the #508 same-context gate-description shape and #506's shared fresh-worker descriptions; existing JEV design docs under `docs/design/` describe run state, handoffs, and continuation policies. No schema or database document applies.
- **Conflicts between house style and AGENTS.md:** None identified; AGENTS.md placement and `JevResponse` ownership rules take precedence.

## §16 Data model

No persistent entities or database changes. Add three managed `TextContextItem` slots to a JEV-owned overlay `ContextManager` created for the `JevRuntime` invocation. Render them as managed conversation messages at the end of each provider call so the current instructions and data remain outside the accumulating main transcript. The overlay is separate from `AgentRuntime.context_manager`, which can reference the agent-level manager shared across calls:

| Slot | Fields / lifecycle | Placement and mutability |
|---|---|---|
| Run state | `primitive_id`, title, rendered state text | Stable ID; installed once after `JevRunState.begin()`; frozen for the remainder of the invocation; placed at `END_OF_CONVERSATION`. |
| Handoff | `primitive_id`, title, current rendered handoff | Stable ID; upserted after each successful handoff compilation; placed at `END_OF_CONVERSATION`. |
| Gate assessment | `primitive_id`, title, directive, current status for every enabled gate, and for failed gates their description, failed question text, and focus | Stable ID; upserted after each evaluation; placed at `END_OF_CONVERSATION`. Passing or unavailable statuses replace prior failure text. |

No index, database lifecycle, or unbounded stored collection is added. The overlay registry holds one value per slot; transcript and tool history remain governed by the runtime's existing history and compaction behavior. The overlay must be rendered alongside existing context during provider-call assembly and must not be merged back into the agent-level manager. As with all `END_OF_CONVERSATION` items, these render as assistant-role messages; clearly label the fixed state/evidence and directive inside the rendered text.

**Lifecycle:** `UNINITIALIZED → RUN_STATE_INSTALLED → (HANDOFF_REPLACED_OR_REMOVED and ASSESSMENT_REPLACED per finish attempt) → DISCARDED at runtime end`; disallowed: reading slots from a prior runtime invocation.

**Volume:** Three bounded registry entries per enabled invocation regardless of retry count; content size depends on the request, evidence, and gate descriptions and has no new hard cap.

## §17 API and interface surface

- **REST / GraphQL / gRPC / WebSocket:** N/A — this is an in-process Python SDK change with no service endpoints.
- **CLI commands and flags:** N/A — caller configuration is through Python objects.
- **Public library functions and types:** `JevRuntimeSettings.continuation_gate`; new `JevContinuationGateSettings(enabled=..., same_context=..., max_continuations=...)`; renamed enum `JevContinuationGate` for criterion values; response map `JevAgent.response.continuation_gates`. Existing criteria preserve their values unless a migration test shows an exported string contract requires a deliberate rename.
- **Validation rules at each boundary:** Settings object must be the new settings type; `enabled` contains unique supported gate enum values; `same_context` must be `bool` (excluding integer coercion); existing continuation limits retain current validation, including `max_continuations=0`.

Example:

```python
JevAgent(settings, JevRuntimeSettings(
    continuation_gate=JevContinuationGateSettings(
        enabled=(JevContinuationGate.MULTI_PART, JevContinuationGate.CLAIMS),
        same_context=True,
        max_continuations=2,
    ),
))
```

## §18 Migrations, versioning, backward compatibility

No persisted schema or data migration. This is a public Python API breaking change: `JevRuntimeSettings.continual`, `JevContinualSettings`, `checks`, the mode enum values `JevContinuationGate.SAME_CONTEXT/FRESH`, and response `.done` are replaced by the continuation-gate settings, `enabled`, boolean `same_context`, and `.continuation_gates`. Rename the criterion enum `JevDoneCheck` to `JevContinuationGate` and result `JevDoneResult` to `JevContinuationGateResult`; update exports. Do not alias the old `JevContinuationGate` mode enum to the new criterion enum because their members and meanings conflict. `AGENTS.md` states this alpha SDK may change APIs between minor versions, so the spec chooses the direct breaking rename; if a stable downstream contract exists outside the repository, use a distinct new enum name and stage a deprecation release.

Migration example: replace `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,), gate=JevContinuationGate.FRESH))` with `JevRuntimeSettings(continuation_gate=JevContinuationGateSettings(enabled=(JevContinuationGate.MULTI_PART,), same_context=False))`.

## §19 Configuration and environment

| Variable / key | Required | Default | Purpose | Lives in |
|---|---|---|---|---|
| `JevRuntimeSettings.continuation_gate` | No | `JevContinuationGateSettings()` | Single public configuration group for enabled continuation gates and policies | `vidbyte/agents/jev/settings.py` |
| `JevContinuationGateSettings.enabled` | No | Empty tuple | Selects which fixed-question checks run | `vidbyte/agents/jev/settings.py` |
| `JevContinuationGateSettings.same_context` | No | `True` | Selects current main-loop continuation (`True`) or clean repair-worker continuation (`False`) | `vidbyte/agents/jev/settings.py` |
| `JevContinuationGateSettings.max_continuations` | No | Existing `JEV_DONE_MAX_CONTINUATIONS` | Caps repair attempts | `vidbyte/lib/constants/jev.py` |

No environment variable, `.env.example`, or rollout flag is needed. Omitting the setting or enabling no gates is the off switch.

---

## Part D — Runtime behavior

## §20 External dependencies and failure impact

| Service / dependency | Purpose | Failure mode | What happens if down / slow | Fallback | Rate limits |
|---|---|---|---|---|---|
| TypeSafe decision service via `DecisionModelHelper` | Evaluate enabled gates | Timeout, unavailable response, invalid/missing answer | Existing fail-open behavior leaves answer standing and records unavailable gate result | Current answer; do not reuse stale assessment | Existing provider policy; no new calls beyond one batched request per finish attempt |
| Main model runner | Produce main-loop response | Existing runner failure | Existing runtime error/fallback behavior; continuation feature adds no retry wrapper | Existing runtime policy | Existing runner policy |
| Fresh repair worker, when `same_context=False` | Work on failed gate feedback with empty history | SDK error or empty output | Existing main answer remains; no output is appended | Current answer | Bounded by `max_continuations` |

## §21 Error handling strategy

- Keep existing `ConfigurationError` validation for wrong settings types, invalid gate values, bool-as-int limits, and non-boolean `same_context` values. Validate before `JevAgent` creates run-local feature objects.
- Gate/decision unavailability remains fail-open as in `JevRunState.check()`: record the latest result as unavailable, replace the assessment slot, and do not continue based on stale failures.
- If handoff compilation has no usable current record, do not expose the preceding handoff as the current attempt and do not launch a continuation requiring that evidence.
- In fresh mode, retain the current `VidbyteSdkError` catch and empty-output guard; do not add retries because the operation is advisory and rerunning could duplicate work.
- No new timeout, error code, or generic retry policy is introduced. Partial gate results remain represented per gate in `JevAgent.response.continuation_gates`.

## §22 Performance and scalability budgets

No database or network call is added by slot replacement. For `n` continuation attempts, the current managed JEV snapshot count remains three rather than growing approximately by three large blocks per retry. Every provider request still includes the latest handoff and assessment, so total tokens for one call depend on their content and ordinary transcript size; one giant handoff can still exceed the provider context limit. At 100× as many iterations, primitive count stays fixed, though existing tool history and evidence extraction costs may still grow and remain outside this feature's guarantee. Compaction continues to act on conversation history under its existing policy.

## §23 Reliability and observability

No new metrics or logs are required. Reuse runtime traces and response fields to inspect continuation count, latest run-state/handoff, per-gate availability/status, and compaction counts. Tests assert the provider request itself contains one of each managed slot and that latest values replace old values. A regression is observable as repeated stable-slot IDs or stale failed-question text in captured runner inputs. This SDK-only change has no server-side abuse surface.

---

## Part E — Security

## §24 Threat model

| ID | Attacker | Shortest path to harm | Control | Where the control sits | Tested by |
|---|---|---|---|---|---|
| T-1 | Careless user | Enables many gates or retries, causing excess provider use | Existing unique gate validation and continuation cap; no per-retry full-block accumulation | SDK settings validation and `JevDoneContinuation` | AC-1, AC-4 |
| T-2 | Hostile user | Places prompt-injection text in the request, run state, or handoff that is rendered repeatedly | Clearly label request-derived state and observed evidence as reference data, keep the continuation directive structurally separate, and retain existing prompt instructions; this reduces ambiguity but cannot guarantee resistance to prompt injection | Runtime context rendering and prompt asset | `test_snapshot_data_is_labeled_separately_from_directive`; prompt review |
| T-3 | Compromised teammate / leaked credential | N/A — feature adds no credential, secret, or external write path | Existing runner credential handling is unchanged | Existing provider integration | N/A — no new credential path |
| T-4 | Another tenant | N/A — local SDK run context has no tenant-backed store | Per-invocation context manager isolates slots; no shared persistent record | `BaseAgent` runtime context construction | INV-10 |

## §25 Auth and sensitive data

N/A — this feature adds no endpoint, credential, persisted record, or cross-tenant query. Request text, run state, handoff evidence, and gate assessment already enter model context today; stable slots change their replacement lifecycle, not the data classes shared with providers. Do not add raw context contents to logs or metadata. Use existing runtime trace controls for diagnostics.

---

## Part F — Verification and delivery

## §12 Testing strategy

- **Seams:** Unit-test `ContextManager` slot installation/replacement with real `TextContextItem` values; runtime-test captured main-runner inputs through provider-message assembly; exercise fresh behavior through the existing fresh-continuation fixture.
- **Prior art to copy:** `tests/test_jev_done.py` for finish-attempt and #508 gate-description assertions; `tests/test_jev_fresh_continuation.py` for clean-worker history and #506 assessment; `tests/test_jev_agent.py` for public construction and response exposure.
- **Fixtures/factories:** Reuse current fake runner, TypeSafe response, and `JevAgent` test fixtures in those files; no new fixture framework.

| Test (file → name) | Level | Proves | Type (pos/neg/edge/sec) |
|---|---|---|---|
| `tests/test_jev_done.py` → add `test_same_context_replaces_stable_continuation_slots` | Runtime unit | AC-1, AC-2; INV-2–5; three retries show one frozen run state and latest handoff/assessment only | pos/edge |
| `tests/test_jev_done.py` → add `test_overlay_preserves_full_latest_handoff` | Runtime unit | AC-6; complete current handoff is rendered without truncation | edge |
| `tests/test_jev_done.py` → existing finish-attempt cases, updated for renamed API | Runtime unit | INV-1, INV-6, INV-8, INV-11 | pos/neg/edge |
| `tests/test_jev_fresh_continuation.py` → update assessment and add `test_fresh_gate_uses_latest_stable_snapshots` | Runtime unit | AC-3; INV-5, INV-7, INV-9 | pos/neg/edge |
| `tests/test_jev_agent.py` → add renamed setting/response API coverage | Unit | AC-5; INV-12 | pos |
| `tests/test_jev_done.py` → add `test_overlay_does_not_mutate_agent_context_manager` | Runtime unit | INV-10; installing/updating slots does not alter caller-owned context | neg |
| `tests/test_jev_done.py` → add `test_snapshot_data_is_labeled_separately_from_directive` | Runtime unit | T-2; request/state/evidence are delimited from SDK continuation instructions | sec |
| `python -m pytest` | Full suite | All invariants and compatibility references remain coherent | pos/neg/edge |

At least one test must capture the actual provider-call payload after middleware/context assembly, not only the pre-rendered `ContextManager` registry; otherwise duplicate blocks introduced during assembly could be missed.

## §26 File tree and feature-to-file map

This map lists every expected production/documentation/test location. Update the broad reference files by search, preserving unrelated terminology where “done” names an evidence schema or a different feature.

| Action | Path | Layer | Reason | Serves |
|---|---|---|---|---|
| MODIFY | `vidbyte/agents/jev/settings.py` | Public configuration | Replace `JevContinualSettings` / `continual` with `JevContinuationGateSettings`, `enabled`, and `same_context`; retain existing limits and validators | FR-1, FR-5 |
| MODIFY | `vidbyte/agents/jev/agent.py` | Agent composition | Build new setting and select same/fresh continuation strategy from bool | FR-1, FR-5 |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Runtime | Create a separate overlay and override `_build_conversation_messages()` to append its current `END_OF_CONVERSATION` messages after parent assembly; pass overlay into continuation hook and do not mutate agent-level `context_manager` | FR-3, FR-4 |
| MODIFY | `vidbyte/agents/jev/continuation/base.py` | Continuation contract | Define stable context update responsibility | FR-4 |
| MODIFY | `vidbyte/agents/jev/continuation/done.py` | Same-context continuation | Replace repeated full prompt append with overlay upserts for handoff and shared assessment | FR-4, FR-5 |
| MODIFY | `vidbyte/agents/jev/continuation/fresh.py` | Fresh continuation | Use the shared renderer and preserve clean worker semantics | FR-4, FR-5 |
| MODIFY | `vidbyte/agents/jev/done/run_state.py` | State/evaluation | Preserve one initial run-state record and update only latest handoff/results per attempt | FR-3, FR-6 |
| MODIFY | `vidbyte/agents/jev/response.py` | Response writer | Rename result writer and map field | FR-2, FR-6 |
| MODIFY | `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/dataclasses/__init__.py` | Public records | Rename result record and response map; export the renamed record | FR-2 |
| MODIFY | `vidbyte/lib/enums/jev.py` | Public enum | Rename criterion enum; remove conflicting old mode enum | FR-2 |
| MODIFY | `vidbyte/lib/constants/jev.py` | Defaults and stable IDs | Retain existing limits and add the three managed-context primitive ID constants | FR-3, FR-4 |
| MODIFY | `vidbyte/lib/jev/done/*.py` and `vidbyte/agents/jev/done/*.py` | Fixed question/evaluation internals | Update references from old criterion enum/result type; retain directory structure and question schemas | FR-2, FR-6 |
| MODIFY | `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/jev/__init__.py`, `vidbyte/lib/jev/done/__init__.py`, `vidbyte/__init__.py` | Public exports | Publish renamed types and remove incompatible names | FR-2, FR-7 |
| MODIFY | `README.md`, `vidbyte/agents/jev/README.md`, `vidbyte/lib/jev/done/README.md` | User/developer docs | Replace public examples and explain same-context toggle and stable snapshots | FR-7 |
| MODIFY | `skills/jev-agent/SKILL.md`, `skills/jev-continuation/SKILL.md` | Contributor docs | Align the guide and workflow with the new public terminology and preserved internal directories | FR-7 |
| MODIFY | `tests/test_jev_done.py`, `tests/test_jev_fresh_continuation.py`, `tests/test_jev_agent.py`, `tests/test_jev_*.py` references found by search | Tests | Update public names and assert stable slots and current gate context | FR-1–FR-7 |
| MODIFY | `vidbyte/prompts/prompts/jev_continuation/continue_prompt.md`, `vidbyte/prompts/prompts/jev_fresh_continuation/` assets if prompt placement changes | Prompt assets | Remove duplicated request/state/handoff formatting; retain concise current instruction and gate guidance | FR-4, FR-5 |
| CREATE | `docs/design/jev-continuation-gate.md` | Design documentation | This approved specification | FR-1–FR-7 |

The expected production change adds no new file. The reference sets under `vidbyte/lib/jev/done/` and `tests/test_jev_*.py` are deliberately broad because their exact enum/result usages must be rechecked against the implementation checkout before editing.

## §27 Dependency manifest

None. `ContextManager`, `TextContextItem`, existing typed JEV result records, and the current decision helper provide the needed behavior.

## §28 Deployment, CI/CD, and rollback

Ship as one SDK release/PR because configuration names, enum names, response fields, continuation behavior, exports, and docs must move together. No feature flag is needed: no enabled gates means off, and `same_context` explicitly chooses the continuation path. The source stage is `python scripts/run_ci.py --stage source`; the full release-quality gate is `python scripts/run_ci.py` and includes lint, compile, repository checks, pytest, package build, and package smoke validation. Rollback is a code revert before release; after release, callers pin the prior SDK version or migrate to the new names. No data rollback is required.

Branch: `feat/jev-continuation-gate` (per `CONTRIBUTING.md` focused-branch guidance). Land one PR. The implementation phase must use a worktree as directed by `/spec-implement`; this stage creates none.

## §29 Quality gates and definition of done

- [x] Every command in §11 Commands passes in the implementation worktree. (`python scripts/run_ci.py`: 2,118 passed, 1 skipped; package build, install, and smoke checks passed)
- [x] Required remote CI checks are green (manual GitHub Actions run 37229426468: Python 3.11, Python 3.12, Package).
- [x] Every P0 AC in §6 has focused test proof; see the AC proof cells.
- [x] Tests cover positive, negative, edge, and security cases listed in §12; focused JEV suite passed.
- [x] Complexity budget (§10.5) is respected without additional production files or dependencies.
- [x] No lint suppressions or skipped/deleted tests were introduced.
- [x] Public exports, README examples, and both JEV skills use the new public names.
- [x] Captured provider-call payloads prove fixed run-state and latest-value handoff/assessment behavior across multiple continuations.
- [x] `same_context=False` remains a clean-worker continuation returning to the existing main loop unless the user changes A-2.
- [x] Full repository gates passed. The six authorized caller-facing feature docs were migrated; remaining old names in the README migration note, archival `docs/design/jev-*.md` records, and the descriptive `AGENTS.md` map are historical/reference material, not current public examples. Required remote CI checks passed: Python 3.11, Python 3.12, and Package (GitHub Actions workflow run 37229426468).

## §15 Phased implementation plan

### P-1 — Rename public continuation-gate API and pin run context (ships: complete new API and bounded JEV snapshot behavior)

- **P1.T1 — Rename configuration, enum, result, and response surface** — Serves: FR-1, FR-2, FR-7 / AC-5
  - Acceptance: New settings construct a JevAgent; all exports and response lookups use continuation-gate names; old mode enum collision is removed; validation and zero-cap behavior remain.
  - Verify: `python -m pytest tests/test_jev_agent.py tests/test_jev_done.py`
  - Files: settings, agent, response, records/enums, internal criterion references, exports, tests, and README/skills listed in §26.
- **P1.T2 — Replace repeated continuation blocks with stable snapshots** — Serves: FR-3–FR-6 / AC-1–AC-4, AC-6
  - Acceptance: Same-context calls contain one immutable run state, one latest handoff, and one latest assessment; fresh worker sees matching latest data and returns only its output to the main history.
  - Verify: `python -m pytest tests/test_jev_done.py tests/test_jev_fresh_continuation.py`
  - Files: runtime, continuation contract/implementations, run_state, prompt assets, and focused tests listed in §26.
- **P1.T3 - Run repo gates and close references** - Serves: FR-7, NFR-1-NFR-3 / all ACs - Complete; local and remote checks passed.
  - Acceptance: Repository-wide old-API search finds no unintended current public examples; package and docs pass full CI. Six caller-facing feature docs were updated under the recorded owner authorization. Historic examples remain in archival design records and the descriptive `AGENTS.md` map, which were outside that authorization.
  - Verify: `python scripts/run_ci.py`
  - Files: remaining references in §26 and any tests identified by the old-name search.

**Dependency order:** P1.T1 → P1.T2 → P1.T3. **Parallelizable:** none; API rename and context flow share runtime and response seams.

## §13 Agent boundaries

- **Always:** Revalidate every path in §26 against the implementation worktree; preserve one batched Jev question request per attempt; test actual assembled provider payloads; keep all context slots run-local; run focused tests then `python scripts/run_ci.py`.
- **Ask first (stop and report back):** Stable-release compatibility requirement; changing `same_context=False` to restart a clean main loop; adding a handoff size cap or compaction policy; exceeding §10.5; adding production files or dependencies; changing gate scoring or question semantics.
- **Never:** Mutate the shared agent-level `ContextManager`; reuse a previous run's context slot; append another full request/run-state/handoff/assessment message in same-context mode; claim one `JevAgent` instance supports overlapping runs; weaken existing JEV tests; bypass `JevResponse`; silently retain old public mode enum values under the conflicting name.

## §14 Assumptions and open questions

**Assumptions** (correct any of these now, or they stand):

- **A-1** — The alpha SDK's documented API-change policy permits the requested breaking rename; no compatibility aliases are added for the enum name collision. — *If wrong:* introduce a deprecation release and choose a non-conflicting new enum name instead of removing old imports immediately.
- **A-2** — `same_context=False` means the existing clean repair-worker path: fresh worker history is empty, but its output returns to the current main loop. — *If wrong:* this changes the continuation architecture and history semantics.
- **A-3** — “Keep the same run state” means the initial request-derived state remains immutable; the handoff is deliberately refreshed per finish attempt, and PR #506's assessment reflects only the latest evaluation.
- **A-4** — The caller wants public configuration and result vocabulary renamed; internal module directories and evidence/question names may retain “done” where that describes their implementation role.
- **A-5** — A single `JevAgent` instance serves one run at a time, matching the current continuation contract; concurrent-run safety is not added here. — *If wrong:* run-scoped construction of `JevRunState`, continuation, and response must be specified as additional work.

**Open questions** (max 5 blocking):

| ID | Question | Blocking? | Owner | Default if unanswered |
|---|---|---|---|---|
| None | No unresolved question blocks a reviewable first implementation; the semantics that would change architecture are recorded as assumptions A-1–A-5. | No | User | Use the defaults above. |

## §30 Traceability matrix

| Requirement | Invariants | Acceptance | Tests | Tasks | Proof |
|---|---|---|---|---|---|
| FR-1 | INV-1, INV-8 | AC-4, AC-5 | `tests/test_jev_agent.py`; `tests/test_jev_done.py` | P1.T1 | `python -m pytest tests/test_jev_agent.py tests/test_jev_done.py tests/test_jev_fresh_continuation.py -q` — 213 passed |
| FR-2 | INV-11, INV-12 | AC-5 | public import/response tests; JEV suite | P1.T1 | Same focused command — 213 passed; public enum, result, settings, and response surface asserted |
| FR-3 | INV-2, INV-10 | AC-1 | `test_same_context_replaces_stable_continuation_slots`; isolation test | P1.T2 | `test_same_context_replaces_stable_continuation_slots` and `test_overlay_does_not_mutate_agent_context_manager` — captured payload and caller registry unchanged |
| FR-4 | INV-3, INV-4, INV-5 | AC-1, AC-2, AC-6 | stable slot, latest assessment, and full handoff tests | P1.T2 | Same-context/fresh latest-snapshot tests and 8,000-unit handoff test; focused JEV suite 213 passed |
| FR-5 | INV-6, INV-7, INV-9 | AC-3, AC-4 | done and fresh continuation tests | P1.T1, P1.T2 | Focused JEV suite 213 passed, including clean-worker reply, unavailable, cap, and no-gate cases |
| FR-6 | INV-1, INV-11, INV-12 | AC-2, AC-4 | `test_jev_done.py`; fresh assessment tests | P1.T1, P1.T2 | Focused JEV suite 213 passed; current batched results remain in response |
| FR-7 | INV-12 | AC-5 | docs/import checks; full suite | P1.T1, P1.T3 | README, JEV READMEs, both JEV skills, and all six authorized caller-facing feature docs updated; remaining references in README migration guidance, archival `docs/design/jev-*.md` records, and `AGENTS.md` are historical/reference-only |
| NFR-1 | INV-3, INV-4 | AC-1 | captured provider payload test | P1.T2 | `test_same_context_replaces_stable_continuation_slots` — one current block per slot in captured provider payloads |
| NFR-2 | INV-10 | AC-1 | overlay does not mutate agent context manager | P1.T2 | `test_overlay_does_not_mutate_agent_context_manager` — caller registry content and ids unchanged |
| NFR-3 | INV-4 | AC-6 | latest handoff content assertion | P1.T2 | `test_overlay_preserves_full_latest_handoff` — full evidence and final marker survive unchanged |

## §31 Review log

| Round | ID | Severity | Section | Finding (one line) | Disposition | Change made / reason |
|---|---|---|---|---|---|---|
| r1-1 | R-1 | Major | §5 | The spec initially implied same-instance overlapping JEV runs would be isolated despite shared mutable run-state and continuation objects. | rejected | Rejected with code evidence: `vidbyte/agents/jev/continuation/base.py` documents one continuation instance serves one run at a time; `JevAgent.__init__` creates the shared feature objects once. Spec records overlap as unsupported in INV-10, EC-6, and A-5 rather than adding unrelated per-run feature construction. |
| r1-2 | R-2 | Major | §10, §16, §26 | The overlay was not connected concretely to provider-call assembly, so the default runtime would omit it. | accepted | Spec requires `JevRuntime._build_conversation_messages(messages)` to call `super()` and append `overlay.render_conversation_messages(ContextWindowPlacement.END_OF_CONVERSATION)`, pass the overlay through the continuation hook, and test the assembled provider payload. |
| r1-3 | R-3 | Minor | §26 | Directly editing the descriptive AGENTS map would conflict with its instruction to regenerate rather than patch. | accepted | Removed `AGENTS.md` from the modification list; it is a lossy map and no regeneration workflow was found. |
| r2-1 | R-4 | Minor | §5 | The initial wording said #508 already supplied the full per-gate status assessment to same-context continuation. | accepted | Clarified that #506 reports every gate's status, #508 adds failed-gate explanations only, and this change must share one renderer combining those behaviors for both paths. |
| implementation-1 | P1.T3 | Scope decision | spec section 0.2, file map | Repository-wide search found current caller-facing examples in six feature docs omitted from the original file map. | resolved by owner authorization `1` (2026-10-04) | Updated only `tests/features/jev_required_actions/FEATURE.md`, `tests/features/jev_problem_repair/FEATURE.md`, `tests/features/jev_output_extent/FEATURE.md`, `tests/features/jev_input_exhaustion/FEATURE.md`, `tests/features/jev_input_set_coverage/FEATURE.md`, and `tests/features/jev_claims/FEATURE.md`; no archival design document or `AGENTS.md` was edited. |
| implementation-2 | P1.T3 | Review note | implementation reference audit | Broad terminology search still finds old public API examples in historical materials. | classified; no edit authorized or needed | `README.md` names old symbols solely in its breaking-migration instruction. Old examples in `docs/design/jev-*.md` are archival design records. `AGENTS.md` is the descriptive map and was excluded from scope. These are not current public examples; all six current caller-facing feature docs are migrated. |

## §32 Revision history

| Revision | Date | Stage | Summary |
|---|---|---|---|
| r1 | 2026-10-03 | spec-create | Initial repo-grounded spec; applied R-2, R-3, and R-4; rejected R-1 with code evidence and narrowed the concurrency contract. |
| r2 | 2026-10-04 | spec-implement | Approved for implementation; handed to implementer subagent. |
| implementation | 2026-10-04 | spec-implement | P1.T1 through P1.T3 implemented; six authorized feature docs migrated; full local CI passed (2,118 passed, 1 skipped); draft PR #509 is open; required remote CI checks passed (Python 3.11, Python 3.12, Package). |
