# Jev dynamic compute options

## Purpose

The mid-run compute checkpoint keeps a compact, verified note brief while the main agent works. After a refresh produces a verified brief update, Jev scores the evidence for three optional compute paths:

- **FRESH_AGENT**: signs that a fresh agent context could usefully resume the work.
- **FORK_AGENT**: signs that distinct approaches or experiments can be compared.
- **SUBAGENT**: signs that an independent helper can complete and return bounded work.

The checkpoint records recognition on `JevAgent.response.compute_decisions`. When `FRESH_AGENT` is selected, a run-local budget may start one separate helper; the other options are recognized but have no move yet. Each attempted move is recorded on `JevAgent.response.compute_moves`.

## Brief and checkpoint timing

The brief remains #512's simple verified-note record. Its goal is the original request, supplied by code. A separate tool-free writer proposes short notes from numbered run events; code verifies each quoted passage against its cited event before appending it. The brief retains the newest bounded set of verified notes. It does not infer item lists, approaches, or next steps.

`JevComputeSettings.dynamic_compute` accepts `FRESH_AGENT`, `FORK_AGENT`, and `SUBAGENT`, enabled by default and normalized into enum order. An empty tuple disables recognition while leaving brief refreshes enabled.

At each continuing tool-iteration checkpoint, the controller reads exact run facts and refreshes the brief when due. Jev is asked only if that refresh returns `JevRunBriefUpdateStatus.UPDATED`. A rejected or unavailable update makes no recognition request. The Jev request uses the same newly verified brief as the update being reported.

## One shared request and state

The recognizer builds one `JevDecisionRequest` containing all questions for the enabled options. Each option contributes twelve questions; all three enabled options produce one request with 36 questions. Every question reads the same four fields:

| Field | Source |
|---|---|
| `request` | Original request, clipped to the existing run-brief request bound |
| `brief` | `JevRunBrief.render()`, containing the code-owned goal and verified notes |
| `facts` | A mapping of exact `JevRunFacts` counts read from the main-agent loop: iteration, tool calls, error streak, and known token usage |
| `recent` | The newest 12 non-request events from `JevRunEventLog.from_run`; each event is clipped to 2,000 characters |

Questions live in `vidbyte/lib/jev/compute/situations.py`, use the existing `JevComputeQuestion` record, and are collected by `JevComputeRegistry`. The question writer guidance is in [`skills/asking-jev-dynamic-compute-questions/SKILL.md`](../../skills/asking-jev-dynamic-compute-questions/SKILL.md).

Each question asks about one positive, observable signal. Missing evidence can be answered false. The questions do not ask Jev to forecast whether launching additional compute will help.

| Option | Evidence signals |
|---|---|
| `FRESH_AGENT` | Rising errors; repeated failures; repeated tool work without new information; drift from the request; an omitted constraint; conflict with verified tool evidence; reliance on a disproven assumption; lost or ignored relevant evidence; a fix followed by a new failure; plan changes without measurable progress; growing continuity burden; enough verified brief context for a fresh agent to resume. |
| `FORK_AGENT` | Distinct plausible approaches to one unresolved goal; a shared verified starting point; independent paths; bounded experiments; one success condition; no evidence-based winner yet; non-exclusive paths; isolated side effects; separately observable results; meaningfully different hypotheses; a result that can be selected or integrated; alignment with the request. |
| `SUBAGENT` | Bounded work; an explicit deliverable; inputs packageable from the request and brief; distinct tool interactions; no need for mid-task direction; separation from the main decision path; an integratable result; useful parallel progress; focused evidence; independent items; isolated writes; enough work for a helper. |

## Scoring and result

For each option, `DecisionModelHelper.score_noul` computes the arithmetic mean of P(true) across its twelve answers. The common `JEV_DYNAMIC_COMPUTE_MIN_THRESHOLD` is `0.8`; an option qualifies at or above it. The recognizer selects the qualifying option with the highest mean. Enum order (`FRESH_AGENT`, `FORK_AGENT`, `SUBAGENT`) breaks ties. A missing or non-NOUL answer makes only its option unavailable; a provider or response-normalization failure selects no option.

`JevComputeDecision.option` records the selected option or `None`. Its results contain the per-option mean and returned answers; request usage is recorded once. A selected `FRESH_AGENT` move passes the same shared state to a separate linear helper, appends a successful report to the main loop, and records the helper run as done-check evidence in event order. Move and helper limits live in `JevComputeSettings`; other selected options have no action yet.

## Files

- `vidbyte/agents/jev/brief/`: the separate brief writer, keeper, and verification of append-only note updates.
- `vidbyte/agents/jev/compute/`: controller, shared-state builder, one-request recognizer, budget, helper runner, and fresh-agent move.
- `vidbyte/agents/jev/done/event_log.py`: `JevRunEventLog.from_run`, the numbered run-event source.
- `vidbyte/lib/jev/compute/`: twelve questions per option and the option registry.
- `vidbyte/agents/jev/settings.py`: `JevComputeSettings.dynamic_compute`.
- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/constants/jev.py`: option and question keys, brief/facts/decision records, and the shared threshold.
- `skills/asking-jev-dynamic-compute-questions/SKILL.md`: evidence and question-writing guidance.
- `tests/test_jev_compute_situations.py` and `tests/test_jev_compute.py`: question, scoring, state, and checkpoint behavior.

## Risks and verification

The threshold is an initial policy value, not a calibrated probability of compute being useful. Recognition is logged so later evaluations can compare the chosen option with run outcomes. The focused tests cover the question set, shared state, setting normalization, one combined request, mean scoring and tie order, missing answers, provider failure, and recognition only after a verified brief update.
