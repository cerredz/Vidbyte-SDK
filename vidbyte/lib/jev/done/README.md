# Jev done questions

This folder holds every fixed question JevAgent sends to Jev when its main agent tries to finish, one dataclass per question, and `JevDoneRegistry`, the registry over them.

## Load the asking-jev-questions skill first

Whenever a model or agent writes, rewrites, or reviews a Jev question here, it must first load `skills/asking-jev-questions/SKILL.md` from the root of this repository and follow its "Writing a full question" section, exactly as the preflight questions in `vidbyte/lib/jev/preflight/` do: a `JevBrief` with a 2–3 sentence introduction, the state, general definitions in dependency order, every rule, and one positive yes/no question; two `JevCriterion` sides that open with the verdict, mirror each other in `not_for`, and give labeled easy and boundary examples that form minimal pairs; each section one string literal; and at least 2,000 tokens across the whole question.

## Where things live

- `multi_part.py` holds the multi-part check's question, asked once per deliverable in the one request that holds every enabled done check's questions, over the shared state `{request, deliverables: {id: {deliverable, completion_signal, evidence}}}`; `to_question(id)` names the deliverable's id in the question and in the question's name.
- `done.py` holds `JevDoneRegistry` (`question`, `threshold`, `resolve`, `validate`).
- The check vocabulary (`JevDoneCheck`, `JevDoneQuestionKey`) is in `vidbyte/lib/enums/jev.py`; the structured-reply payloads, records, and `JevDoneQuestion` base are in `vidbyte/lib/dataclasses/jev.py`; the thresholds are in `vidbyte/lib/constants/jev.py`.
- The logic that writes the run state and the handoff, asks Jev, and sends the main agent back to work is `JevRunState` and `JevHandoff` in `vidbyte/agents/jev/done/`.
