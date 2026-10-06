# JevAgent input exhaustion done check

## Change

Add the enableable `JevDoneCheck.INPUT_EXHAUSTION` preset for requests that explicitly require traversing an entire dynamically discovered or paginated collection. Run state records one stable obligation per collection, including its source, scope, unit, explicit user-stated total when provided, and stated stopping condition. This is distinct from finite, user-bounded named inputs, which belong to `INPUT_SET_COVERAGE`.

At each finish attempt, JevHandoff compiles trace-backed observations for every obligation: visited unit identifiers, source-reported totals, continuation positions, terminal signals, failed retrievals, the last known position, and an actionable gap. Deterministic code compares distinct observed units with the request-stated total first, or with a comparable source-reported total when the request has none. It never compares unlike units. If a request states an explicit count but the observed identifier unit is incompatible or unknown, an end-of-results signal cannot substitute for verifying that count, so the obligation remains incomplete. A source total may supplement or conflict with the request-stated bound. Jev receives one evidence-rich recognition question per collection in the existing combined request. It must not infer the unseen universe. A known total can establish completion only when distinct visited units meet it and no failure or continuation remains; when the total is unknown, affirmative end-of-results evidence is required. A readable handoff that has neither a usable request/source total nor affirmative terminal evidence is a failed completion obligation and triggers continuation. Missing or malformed run state or handoff, failed Jev requests, and missing answers remain unavailable under the existing fail-open contract.

When Jev rejects a collection, the same-loop continuation names the collection, last observed page/cursor when known, handoff gap, and next action. The gate keeps the existing continuation cap and does not modify runtime, settings, or general run-state/handoff prompts. `DONE_STATE` remains accurate for every combination of enabled checks; `handoff.missing` is returned to the main agent only and never included in Jev state.

## Files

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`: check, question key, and threshold.
- `vidbyte/lib/dataclasses/jev.py`: structured payloads and frozen run-state/handoff records.
- `vidbyte/lib/jev/done/input_exhaustion.py`, `done.py`, `__init__.py`, `README.md`: question, registration, and exports.
- `vidbyte/agents/jev/done/run_state.py`, `handoff.py`, `vidbyte/agents/jev/continuation/done.py`: schemas, trace evidence, judgment, and actionable continuation focus.
- `vidbyte/lib/jev/done/multi_part.py`: shared `DONE_STATE` description for every combination.
- `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`: public records.
- `tests/test_jev_done.py`, `tests/features/jev_input_exhaustion/FEATURE.md`, and the focused done-check verification script: feature contract and regression coverage.
- `skills/jev-agent/SKILL.md` and `skills/jev-continuation/SKILL.md`: the enableable preset and its evidence boundary.

## Risks and decisions

- A generative handoff can misread logs. Jev sees its source excerpts, exact visited identifiers, totals, cursor state, failures, and any deterministic comparison; arithmetic and distinct-id comparisons stay in code.
- A missing next-page call is not a terminal signal. Preserve any numeric total explicitly stated by the request as `expected_total`; code compares distinct visited units against it before considering a source-reported total. If neither the request nor a source response gives a comparable total, require affirmative terminal evidence or fail the completion condition.
- Failed page/cursor retrieval or an outstanding continuation is concrete evidence of incomplete traversal and must remain visible to Jev and continuation feedback.
- The pre-run writer must not invent collection obligations or a finite total absent from the request. Handoff IDs must exactly match the run-state IDs.

## Verification

Run the focused done-check script, targeted `tests/test_jev_done.py` tests, lint, and the source/package CI stages required by `AGENTS.md`. Tests cover extraction boundaries, exact ID matching, counts versus duplicates, explicit terminal evidence, unknown totals without terminal evidence, failed fetches and outstanding cursors, batched checks, same-loop focus, continuation cap, and fail-open paths.
