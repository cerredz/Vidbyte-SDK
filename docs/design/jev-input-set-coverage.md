# Bounded input-set coverage continuation gate

## Problem

A JevAgent can deliver a plausible result after inspecting only part of an explicitly bounded input set the user asked it to inspect, review, or process. MULTI_PART checks requested outputs, while CLAIMS checks support for final-answer statements; neither requires evidence that requested source inputs were engaged.

## Design

Add an opt-in `JevDoneCheck.INPUT_SET_COVERAGE`. Before the main loop, `JevRunState` extracts stable, atomic obligations only for input targets whose scope is explicitly bounded by the user's request. Each obligation carries the requested action, target, scope, and observable engagement signal. At every finish attempt, `JevHandoff` compiles per-target evidence from tool calls and outputs. Jev receives one recognition question per target in the same combined request as other enabled checks. Its evidence must show successful inspection at the depth the request asks for; path listings, insufficient snippets, and failed attempts are not evidence of full engagement. The handoff's `missing` field is reserved for continuation feedback and is never passed to Jev. Code validates exact target-id coverage, applies the per-answer threshold/veto, and sends incomplete targets through the existing continuation message to the same agent loop. Failures remain fail-open and respect the shared continuation cap.

This preset covers user-bounded, finite targets such as explicitly named files, records, sources, categories, and finite ranges. It does not try to discover or count open-ended or dynamically paginated universes; those belong to the separate input-exhaustion gate.

## Files

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`: check key and threshold/state fields.
- `vidbyte/lib/dataclasses/jev.py`: run-state and handoff schema payloads, frozen records, and top-level optional sections.
- `vidbyte/lib/jev/done/input_set_coverage.py`, `done.py`, `__init__.py`, `README.md`: full Jev question and registration.
- `vidbyte/agents/jev/done/run_state.py`, `handoff.py`, `continuation/done.py`: extraction, evidence conversion, check/judgment, and actionable continuation feedback.
- `vidbyte/agents/jev/README.md`, `skills/jev-continuation/SKILL.md`, `scripts/test-jev-input-set-coverage.py`, `tests/test_jev_done.py`: developer enablement, implementation guide, and behavioral verification.

## Risks and open questions

- Generative extraction may omit or over-split request targets; stable ids, exact run-state/handoff matching, and adversarial tests limit silent gaps, while the check fails open if state or evidence is unavailable.
- Tool outputs vary in how clearly they establish content access. The question must judge the requested action depth and successful outputs, not tool names or claimed coverage.
- Questions are sent per target, so unusually large but still finite requests may exceed Jev request limits; normal Jev unavailable behavior fails open.

## Verification

Add focused tests for stable extraction schemas, exact handoff target matching, successful versus failed/insufficient engagement, batching with other checks, separate continuation focus, threshold/veto scoring, empty obligations, and fail-open behavior. Run the focused runner, relevant Jev tests, and the repository's required lint/test checks from `AGENTS.md` before opening a draft PR.
