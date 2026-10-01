# Discovered Item Coverage

## Problem

An agent can finish an all-items request after it has discovered a concrete collection but processed only part of it. `INPUT_SET_COVERAGE` checks targets bounded by the user's request, while `INPUT_EXHAUSTION` checks whether discovery reached a source-defined end. Neither checks every item actually discovered during the run.

## Design

Add opt-in `JevDoneCheck.DISCOVERED_ITEM_COVERAGE`. At each finish attempt, code retains bounded raw outputs from every recorded tool call while `JevHandoff` derives a candidate inventory keyed by the stable source-call ids and compiles per-item evidence of the requested processing. Since the items do not exist before the run, they belong in the handoff, not run state. The check asks one recognition question for each candidate item: does the run evidence show the requested processing for this item?

To guard against the handoff silently omitting a source batch, code requires one handoff row for every recorded tool call and pairs each row's source id with the original raw output. Jev receives that output directly from code alongside the handoff's candidate inventory and asks one inventory-fidelity recognition question per source: does the candidate inventory account for every concrete item visibly present in this output? Jev returns yes/no only; the generative handoff supplies candidates and code applies the individual answers. If relevant source output is absent, too large to compare, or otherwise cannot support a faithful inventory, mark this check unavailable and fail open. Empty candidate inventory without source evidence is not allowed to certify a discovered collection.

When either an item-processing question or inventory-fidelity question fails, continue the same loop with the uncovered candidate items and evidence gaps. Keep this preset distinct from explicit user-named target coverage and discovery exhaustion. It is source-agnostic: records, pages, documents, search hits, issues, files, and other concrete collections use the same candidate and evidence shape.

## Files

- `vidbyte/lib/enums/jev.py`: done check and question key.
- `vidbyte/lib/dataclasses/jev.py`: typed handoff payload and record for discovered batches, candidates, and bounded source excerpts.
- `vidbyte/lib/constants/jev.py`: question threshold and source excerpt limits.
- `vidbyte/lib/jev/done/discovered_item_coverage.py`, `done.py`, `__init__.py`, `README.md`: question, registry, and exports.
- `vidbyte/agents/jev/done/handoff.py`, `run_state.py`, `vidbyte/agents/jev/continuation/done.py`: compile, batch, score, fail open, and explain this post-run-derived check.
- `vidbyte/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/jev/README.md`: public response record and user-facing guidance.
- `tests/test_jev_done.py`, `tests/features/jev_discovered_item_coverage/FEATURE.md`, `scripts/test-jev-multipart-done-criteria.py`: behavior contracts and focused runner registration.

## Risks and verification

Inventory fidelity remains bounded by tool outputs recorded in the main run and by the configured character caps; it cannot establish facts hidden by unrecorded responses or omitted context, so oversized source evidence reports unavailable instead of certifying partial candidate lists. Existing done-check batching, score thresholds, and fail-open behavior must remain intact. Verification will cover exact candidates, partial processing, omitted-candidate detection, multiple collection types, unavailable or oversized evidence, and ordinary continuation behavior; local tests are not run for this task, while PR CI will be inspected.
