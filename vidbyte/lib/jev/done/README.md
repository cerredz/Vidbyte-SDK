# Jev done questions

This folder holds every fixed question JevAgent sends to Jev when its main agent tries to finish, one dataclass per question, and `JevDoneRegistry`, the registry over them.

## Load the asking-jev-questions skill first

Whenever a model or agent writes, rewrites, or reviews a Jev question here, it must first load `skills/asking-jev-questions/SKILL.md` from the root of this repository and follow its "Writing a full question" section, exactly as the preflight questions in `vidbyte/lib/jev/preflight/` do: a `JevBrief` with a 2–3 sentence introduction, the state, general definitions in dependency order, every rule, and one positive yes/no question; two `JevCriterion` sides that open with the verdict, mirror each other in `not_for`, and give labeled easy and boundary examples that form minimal pairs; each section one string literal; and at least 2,000 tokens across the whole question.

## Where things live

- `multi_part.py` holds the multi-part check's question, asked once per request-defined deliverable; `to_question(id)` names the deliverable id in the question and its name.
- `claims.py` holds the CLAIMS check's question, asked once per concrete, checkable factual assertion extracted from the final answer by JevHandoff; each claim entry contains the assertion and its tool-call evidence, or an explicit lack of evidence.
- `target_outcome.py` holds the TARGET_OUTCOME question, asked once per request-derived outcome; it distinguishes direct evidence on the actual target from a proxy milestone.
- `motivating_case.py` holds the MOTIVATING_CASE question and its one-time recall guard; the continuation check asks once per user-named unusual scenario, using the scenario definition and current run evidence.
- `scope_coverage.py` holds the SCOPE_COVERAGE continuation question, asked once per required group member with work evidence; missing work and incomplete workspace inventories become explicit continuation gaps.
- `completion_evidence.py` holds the COMPLETION_EVIDENCE question, asked once per finish attempt about whether the final answer's overall completion status is supported by the requested outcomes and run evidence. It checks the fixed `task_completion` item using handoff evidence and has no request-derived run-state section.
- `problems_resolved.py` holds the dynamic problem-repair question, asked once per observed run problem and once for the required completion of the original request after repairs.
- `phase_progress.py` holds the PHASE_PROGRESS question, asked once per request-required outcome stage to check for substantive stage activity or an observed blocker.
- The shared state description in `multi_part.py` covers the enabled request-derived sections and their evidence. `phase_progress` is present only when the user request yields at least one substantive outcome stage; an empty stage list means no state section and no question. `completion_evidence` is separate handoff-only context with one fixed `task_completion` item, checking whole-task status rather than per-deliverable completion or per-claim factual support.
- `done.py` holds `JevDoneRegistry` (`question`, `threshold`, `resolve`, `validate`).
- The check vocabulary (`JevDoneCheck`, `JevDoneQuestionKey`) is in `vidbyte/lib/enums/jev.py`; the structured-reply payloads, records, and `JevDoneQuestion` base are in `vidbyte/lib/dataclasses/jev.py`; the thresholds are in `vidbyte/lib/constants/jev.py`.
- The logic that writes the run state and the handoff, asks Jev, and sends the main agent back to work is `JevRunState` and `JevHandoff` in `vidbyte/agents/jev/done/`.
