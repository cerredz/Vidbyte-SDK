# Jev done questions

This folder holds every fixed question JevAgent sends to Jev when its main agent tries to finish, one dataclass per question, and `JevDoneRegistry`, the registry over them.

## Load the asking-jev-questions skill first

Whenever a model or agent writes, rewrites, or reviews a Jev question here, it must first load `skills/asking-jev-questions/SKILL.md` from the root of this repository and follow its "Writing a full question" section, exactly as the preflight questions in `vidbyte/lib/jev/preflight/` do: a `JevBrief` with a 2–3 sentence introduction, the state, general definitions in dependency order, every rule, and one positive yes/no question; two `JevCriterion` sides that open with the verdict, mirror each other in `not_for`, and give labeled easy and boundary examples that form minimal pairs; each section one string literal; and at least 2,000 tokens across the whole question.

## Where things live

- `multi_part.py` holds the multi-part check's question, asked once per request-defined deliverable; `to_question(id)` names the deliverable id in the question and its name.
- `output_count.py` holds the OUTPUT_COUNT question, asked once per request-defined numeric output obligation; its state carries target, unit, group scope, candidate values, direct source evidence, deterministic count, and distinctness keys.
- `claims.py` holds the CLAIMS check's question, asked once per concrete, checkable factual assertion extracted from the final answer by JevHandoff; each claim entry contains the assertion and its tool-call evidence, or an explicit lack of evidence.
- `target_outcome.py` holds the TARGET_OUTCOME question, asked once per request-derived outcome; it distinguishes direct evidence on the actual target from a proxy milestone.
- `motivating_case.py` holds the MOTIVATING_CASE question and its one-time recall guard; the continuation check asks once per user-named unusual scenario, using the scenario definition and current run evidence.
- `scope_coverage.py` holds the SCOPE_COVERAGE continuation question, asked once per required group member with work evidence; missing work and incomplete workspace inventories become explicit continuation gaps.
- `completion_evidence.py` holds the COMPLETION_EVIDENCE question, asked once per finish attempt about whether the final answer's overall completion status is supported by the requested outcomes and run evidence. It checks the fixed `task_completion` item using handoff evidence and has no request-derived run-state section.
- `input_set_coverage.py` holds the INPUT_SET_COVERAGE question, asked once per explicitly bounded input target extracted from the request; each question judges only trace evidence for that target's requested action, scope, and depth.
- `input_exhaustion.py` holds the INPUT_EXHAUSTION question, asked once per request-derived dynamic collection traversal; it judges whether trace evidence establishes the requested stopping condition, with count comparison handled deterministically by code.
- `output_extent.py` holds the OUTPUT_EXTENT question, asked once per explicit text-size target; code measures supported raw final-answer counts and Jev recognizes target evidence.
- `report_action_alignment.py` holds the report/action alignment question, asked once per eligible explicit earlier plan or commitment the final account refers to or implies was carried out; Jev compares that retrospective account with recorded execution and the request's actual requirements.
- `assumptions_reconciled.py` holds the ASSUMPTIONS_RECONCILED question, asked once per explicit, consequential assumption that later run evidence materially changes; it judges whether dependent work was observably revised or made irrelevant.
- `negative_coverage.py` holds the NEGATIVE_COVERAGE question, asked once per requested inspection target; it checks whether a negative or explicitly incomplete report is supported by evidence that the target was examined.
- The `negative_coverage` section exists only when NEGATIVE_COVERAGE is enabled. It pairs each request-derived `target` and `inspection_signal` with handoff `inspection`, `negative_conclusion`, and `incomplete_report`; the continuation-only `missing` note is not sent to Jev, and zero findings alone do not show that inspection happened.
- `guaranteed_next_actions.py` asks two questions for each candidate: whether the request and observed trigger require the action, and whether run evidence shows the action remains unfinished.
- `guaranteed_next_actions` is handoff-only and appears only when the check is enabled and candidates exist. Its entries contain `outcome`, `trigger`, `action`, and `evidence`; the handoff `necessity_basis` is excluded from Jev, and continuation requires both answers for a candidate to meet the 0.9 threshold.
- `required_actions.py` holds the REQUIRED_ACTIONS question, asked once per action the request explicitly requires. It compares direct run evidence with the action's stated completion condition; successful tool output or an exact substantive-output excerpt can show completion, while code validates excerpts and enforces explicit dependencies from successful trace-call indices. Useful, customary, or implied actions are not added.
- `required_actions` appears only when REQUIRED_ACTIONS is enabled and the request names actions; each entry maps an id to request-derived `action` and `completion_signal` plus run `evidence`. The continuation-only `missing` note is not sent to Jev, and an empty list creates no section or question.
- `cumulative_obligations.py` asks one fulfillment question per generated requirement and one inventory-fidelity question per supplied user turn. It checks all original messages against the complete obligation list and current per-turn observations, so an omitted requirement can pass only when evidence independently shows it completed. Only explicit user cancellation or incompatible replacement deactivates an obligation; silence and agent omission do not.
- The cumulative check keeps exact ordered `user_turns`, obligation source/clarification/status links, and observation-only `turn_evidence` in shared state; its inventory question checks each actual turn against all obligation entries.
- `discovered_item_coverage.py` asks one source-inventory question per recorded tool output and one processing question per discovered collection member. It applies when the request asks for item-by-item processing; source fidelity and item completion remain separate questions in the same decision batch.
- `discovered_item_inventory` retains each complete recorded tool output and candidates derived from it, including an empty candidate list when a source contains no collection. Every recorded tool-call id is represented. Each output is limited to 12,000 characters and the total retained output to 48,000 characters; when code cannot preserve and pair outputs within those bounds, the check is unavailable before questioning.
- `discovered_items` maps each candidate to its visible identity, request-faithful `requested_processing`, `completion_criteria`, and item-specific `processing_evidence`. The handoff `missing` judgment is continuation-only; a complete inventory does not prove the items were processed.
- `problems_resolved.py` holds the dynamic problem-repair question, asked once per observed run problem and once for the required completion of the original request after repairs.
- `phase_progress.py` holds the PHASE_PROGRESS question, asked once per request-required outcome stage to check for substantive stage activity or an observed blocker.
- The shared state description in `multi_part.py` covers enabled request-derived sections that have items and their evidence; `input_set_coverage`, like `phase_progress`, has no section or question when its request-derived item list is empty. `phase_progress` is present only when the user request yields at least one substantive outcome stage; an empty stage list means no state section and no question. `completion_evidence` is separate handoff-only context with one fixed `task_completion` item, checking whole-task status rather than per-deliverable completion or per-claim factual support.
- `input_exhaustion` contains one request-derived obligation per explicitly requested dynamic exhaustive traversal; when none exist, no per-obligation Jev question is asked. Trace evidence records units visited, source totals, cursors, terminal signals, and unresolved retrieval failures; deterministic code checks comparable counts, and the handoff's `missing` and `next_step` notes are not sent to Jev.
- `problems_resolved.py` holds the dynamic problem-repair question, asked once per observed run problem and once for the required completion of the original request after repairs.
- `phase_progress.py` holds the PHASE_PROGRESS question, asked once per request-required outcome stage to check for substantive stage activity or an observed blocker.
- The shared state description in `multi_part.py` covers enabled request-derived sections that have items and their evidence; `input_set_coverage`, like `phase_progress`, has no section or question when its request-derived item list is empty. `phase_progress` is present only when the user request yields at least one substantive outcome stage; an empty stage list means no state section and no question. `completion_evidence` is separate handoff-only context with one fixed `task_completion` item, checking whole-task status rather than per-deliverable completion or per-claim factual support.
- `assumptions_reconciled` is present only when its check is enabled and qualifying post-run candidates exist; an empty candidate list creates no section or question, and the handoff's `missing` note is not sent as Jev evidence.
- `done.py` holds `JevDoneRegistry` (`questions`, `question`, `inventory_question`, `question_for_key`, `threshold`, `resolve`, `validate`); `question` remains the first-question compatibility accessor, and `inventory_question` returns the separate per-turn or per-source inventory audit.
- The check vocabulary (`JevDoneCheck`, `JevDoneQuestionKey`) is in `vidbyte/lib/enums/jev.py`; the structured-reply payloads, records, and `JevDoneQuestion` base are in `vidbyte/lib/dataclasses/jev.py`; the thresholds are in `vidbyte/lib/constants/jev.py`.
- The logic that writes the run state and the handoff, asks Jev, and sends the main agent back to work is `JevRunState` and `JevHandoff` in `vidbyte/agents/jev/done/`.

## Enable assumption reconciliation

The check is opt-in through the existing `JevContinualSettings.checks` API. It extracts only explicit, consequential assumptions that later concrete run evidence changes, and judges downstream reconciliation separately from whether tool errors were repaired.

```python
from vidbyte import JevContinualSettings, JevDoneCheck

continuation = JevContinualSettings(
    checks=(JevDoneCheck.ASSUMPTIONS_RECONCILED,),
    max_continuations=2,
)
```
