# Jev output-count continuation gate

## Goal

Add an opt-in `OUTPUT_COUNT` done check for explicit numeric quantities in requested outputs. It catches requests whose requested cardinality is only partly satisfied, including distinct items per group and repeated entries that do not meet a distinctness requirement. It complements `MULTI_PART`: that check tracks separate deliverables, while this check measures quantity inside one requested output.

## Design

`JevRunState` extracts one typed obligation for each explicit quantity, including a stable id, requested count, unit, scope/group, and whether the request requires distinct results. `JevHandoff` compiles the relevant final-answer or artifact evidence for every obligation on every finish attempt, retaining each candidate's visible value and direct source evidence. Code counts candidate entries, or normalized semantic keys when distinctness is required. Jev checks that those keys faithfully reflect the candidate values and the request's meaning of distinct, then recognizes whether the prepared evidence meets the target; it does not calculate counts. The check is batched with other enabled checks, fails open when its state, evidence, or Jev answer is unavailable, and returns unmet obligations as continuation focus to the same generative loop.

## Files

- Add the check and question-key enum members, typed request/evidence payloads and records, threshold, question module, registry entry, exports, and done-folder index entry.
- Extend `JevRunState` schemas, section construction, judgment, and shared `DONE_STATE`; extend `JevHandoff` schemas and evidence compilation; add the failed-check explanation in `JevDoneContinuation`.
- Extend `tests/test_jev_done.py` and the exhaustive focused-test loader, and document the check in the Jev skills.

## Risks and boundaries

Natural-language quantities can be ambiguous, and semantic distinctness cannot be reduced to string equality. The run-state writer preserves the user's scope and distinctness condition. Deterministic counting handles only entries that the handoff can enumerate without interpretation; Jev recognizes whether the prepared evidence satisfies the stated obligation. Missing or malformed records fail open. The implementation does not change the runtime, settings, general prompts, or other done checks' policies.

## Verification

Exercise schema and public exports, requested counts and per-group obligations, duplicate versus distinct entries, the 25-request/10-produced partial case, the same-loop continuation focus, batched checks, thresholds, and fail-open behavior. Run the focused Jev done-check script and the repository source/package gates required by `AGENTS.md`.
