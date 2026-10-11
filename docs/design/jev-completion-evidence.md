# Jev completion evidence done check

## Product behavior

`JevDoneCheck.COMPLETION_EVIDENCE` lets a developer ask JevAgent to check whether a final answer's explicit or implied whole-task completion status is supported by the original request and the work observable in the run. It targets claims like “done” that overstate what the run shows. It is distinct from `CLAIMS`, which checks individual factual assertions in the final answer, and `MULTI_PART`, which checks whether requested deliverables are visibly produced. This check judges the relationship between the answer's overall status and the request's outcomes; an honest incomplete or blocked status may pass.

## Design

- **Enablement:** Add `JevDoneCheck.COMPLETION_EVIDENCE`, enabled through the existing `JevContinualSettings(checks=(...))` API. It requires no setting or runtime changes.
- **Granularity:** One fixed-id item, `task_completion`, is assessed at every finish attempt. Its status is post-run-derived because the final answer's status is not known when `JevRunState` is written. No run-state section is added. A terminal answer with no explicit caveat implies complete; an empty final answer is incomplete, so neither can bypass the check.
- **State:** The handoff records five context fields for that one item: `completion_status` (the status the final answer states or implies), `requested_outcomes` (the original request's outcomes, including explicit requirements), `completed_work` (outcomes supported by observable work), `unfinished_or_blocked` (outcomes with observable gaps or blockers), and `evidence` (the supporting run observations). Each generated schema field has a five-sentence instruction. `completion_status` describes the final answer only; it never counts as evidence that work occurred.
- **Evidence boundary:** Evidence must cite actual response artifacts or tool-call inputs and outputs from the run. The handoff may use the final response to identify its wording and delivered text artifact, but must not treat an agent's statements that it edited, checked, searched, or completed something as evidence those actions occurred. Tool-call evidence and visible artifacts determine whether requested work is shown.
- **Question:** Ask one positive Noul recognition question for `task_completion`: whether the run evidence supports the completion status the final answer communicates for the original request. The question defines `complete`, `incomplete`, `blocked`, and `unclear`; explicitly or implicitly complete answers need evidence of the requested outcomes, while an honest incomplete or blocked report is supported when the run shows the stated gap or blocker. An unclear status is not an overstatement and passes. The checker sees the five named context fields and one separate `evidence` field; it does not receive the handoff's `missing` judgment.
- **No-content behavior:** Exactly one item is always produced, including when the final answer is empty or omits any completion claim. A handoff status of `incomplete`, `blocked`, or `unclear` can pass when the evidence supports that status; an unqualified terminal answer defaults to `complete`, which must be supported by evidence. The item is still asked when no tool calls exist, so missing external evidence can be judged rather than silently skipped. A user-requested text answer is a run artifact and may be supported by the actual delivered answer text, while the answer's own statement that it is complete is not evidence.
- **Scoring and failure policy:** Use a named threshold of `0.85` as both the Noul mean threshold and veto, matching the existing CLAIMS starting threshold. If the handoff or Jev call fails, or the expected answer is missing, mark the check unavailable and fail open. If Jev says the completion status is unsupported, continue in the same loop with the original request, evidence gap, and a focus on completing missing work or revising the final status. Continuations remain bounded by existing settings.

## Files

- `vidbyte/lib/enums/jev.py` and `vidbyte/lib/constants/jev.py`: check/key and threshold/state field names.
- `vidbyte/lib/dataclasses/jev.py`: completion context and evidence payloads and immutable handoff records.
- `vidbyte/lib/jev/done/completion_evidence.py`, `done.py`, package exports, and README: the question, registry, and documentation.
- `vidbyte/agents/jev/done/handoff.py`, `run_state.py`, and `continuation/done.py`: structured handoff extraction, batched question state and scoring, and focused continuation feedback.
- Public record export modules and `README.md`: expose the response evidence and document enablement.

## Risks and verification

The handoff generator could confuse final-answer self-report with observable work. The schema and question therefore keep status separate from evidence and explicitly exclude self-report as proof of external actions. A second risk is overlapping with MULTI_PART or CLAIMS; the check is deliberately a single whole-task status judgment, with neither one question per deliverable nor one per factual assertion. Validate imports, lint/static checks, and CI. Per task instructions, do not add or run tests locally.
