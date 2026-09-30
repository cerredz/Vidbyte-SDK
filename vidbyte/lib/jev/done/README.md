# Jev done questions

This folder holds every fixed question JevAgent sends to Jev when its main agent tries to finish, one dataclass per question, and `JevDoneRegistry`, the registry over them.

## Load the asking-jev-questions skill first

Whenever a model or agent writes, rewrites, or reviews a Jev question here, it must first load `skills/asking-jev-questions/SKILL.md` from the root of this repository and follow its "Writing a full question" section, exactly as the preflight questions in `vidbyte/lib/jev/preflight/` do: a `JevBrief` with a 2–3 sentence introduction, the state, general definitions in dependency order, every rule, and one positive yes/no question; two `JevCriterion` sides that open with the verdict, mirror each other in `not_for`, and give labeled easy and boundary examples that form minimal pairs; each section one string literal; and at least 2,000 tokens across the whole question.

## Where things live

- `multi_part.py` holds the multi-part check's question, asked once per request-defined deliverable; `to_question(id)` names the deliverable id in the question and its name.
- `claims.py` holds the CLAIMS check's question, asked once per concrete, checkable factual assertion extracted from the final answer by JevHandoff; each claim entry contains the assertion and its tool-call evidence, or an explicit lack of evidence.
- `guaranteed_next_actions.py` holds separate questions for whether a request and observed trigger entail one proposed follow-on action, and whether the run shows that action remains unfinished.
- Every question uses the shared state description in `multi_part.py`; `deliverables` and `claims` are present only when their respective checks are enabled, so the description stays true when checks are combined.
- Guaranteed-next-action questions additionally read the original request and the candidate's outcome, trigger, action, and direct evidence; the handoff's necessity rationale is excluded.
- `done.py` holds `JevDoneRegistry` (`question`, `threshold`, `resolve`, `validate`).
- The check vocabulary (`JevDoneCheck`, `JevDoneQuestionKey`) is in `vidbyte/lib/enums/jev.py`; the structured-reply payloads, records, and `JevDoneQuestion` base are in `vidbyte/lib/dataclasses/jev.py`; the thresholds are in `vidbyte/lib/constants/jev.py`.
- The logic that writes the run state and the handoff, asks Jev, and sends the main agent back to work is `JevRunState` and `JevHandoff` in `vidbyte/agents/jev/done/`.
