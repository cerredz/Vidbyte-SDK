# Jev done questions

This folder holds every fixed question JevAgent sends to Jev when its main agent tries to finish, one dataclass per question, and `JevDoneRegistry`, the registry over them.

## Load the asking-jev-questions skill first

Whenever a model or agent writes, rewrites, or reviews a Jev question here, it must first load `skills/asking-jev-questions/SKILL.md` from the root of this repository and follow its "Writing a full question" section, exactly as the preflight questions in `vidbyte/lib/jev/preflight/` do: a `JevBrief` with a 2–3 sentence introduction, the state, general definitions in dependency order, every rule, and one positive yes/no question; two `JevCriterion` sides that open with the verdict, mirror each other in `not_for`, and give labeled easy and boundary examples that form minimal pairs; each section one string literal; and at least 2,000 tokens across the whole question.

## Where things live

- `multi_part.py` holds the multi-part check's question, asked once per request-defined deliverable; `to_question(id)` names the deliverable id in the question and its name.
- `claims.py` holds the CLAIMS check's question, asked once per concrete, checkable factual assertion extracted from the final answer by JevHandoff; each claim entry contains the assertion and its tool-call evidence, or an explicit lack of evidence.
- `required_actions.py` holds the REQUIRED_ACTIONS question, asked once per explicitly requested action. A successful tool result or an exact substantive-output excerpt can evidence completion; Jev judges whether it meets the condition, and code validates excerpts against their named source. Explicit dependencies are enforced from successful tool-call indices, so a dependency without observable order fails.
- Every question uses the shared state description in `multi_part.py`; `deliverables`, `claims`, and `required_actions` are present only when their respective checks are enabled, so the description stays true when checks are combined.
- `target_outcome.py` holds the TARGET_OUTCOME check's question, asked once per request-derived outcome; it distinguishes direct evidence on the actual target from a proxy milestone.
- `problems_resolved.py` holds the dynamic problem-repair question, asked once per observed run problem and once for the required completion of the original request after repairs.
- Every question uses the shared state description in `multi_part.py`; `deliverables`, `claims`, `target_outcomes`, and `problems_resolved` are present only when their respective checks are enabled, so the description stays true when checks are combined.
- `done.py` holds `JevDoneRegistry` (`question`, `threshold`, `resolve`, `validate`).
- The check vocabulary (`JevDoneCheck`, `JevDoneQuestionKey`) is in `vidbyte/lib/enums/jev.py`; the structured-reply payloads, records, and `JevDoneQuestion` base are in `vidbyte/lib/dataclasses/jev.py`; the thresholds are in `vidbyte/lib/constants/jev.py`.
- The logic that writes the run state and the handoff, asks Jev, and sends the main agent back to work is `JevRunState` and `JevHandoff` in `vidbyte/agents/jev/done/`.
