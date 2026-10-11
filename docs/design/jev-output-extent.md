# Jev output extent continuation gate

## Problem

`MULTI_PART` checks whether requested outputs exist, but it does not enforce the requested magnitude of a text output. A final answer can contain fewer words, lines, or defined sections than explicitly requested and still appear complete. This gate covers only explicit measurable text extents; distinct examples, files, and other separate entries remain the responsibility of `MULTI_PART` or a dedicated count gate.

## Design

Add an opt-in `OUTPUT_EXTENT` done check under the existing `JevDoneContinuation`. Before work starts, `JevRunState` extracts one stable item for each explicit extent obligation, including its output target, unit, numeric target, and minimum/exact/maximum comparator. Vague requests such as “detailed” do not create quotas. At each finish attempt, `JevHandoff` associates observed output text with each item and writes an actionable `missing` note. `JevRunState` counts measurable final-answer text in deterministic code when its scope and unit permit it; Jev receives the defining obligation and observed evidence for one recognition question per item, never a task to count. Unsupported or ambiguous measurement evidence remains a Jev-recognition case or fails open if required evidence is unavailable.

The check shares the existing run-state and handoff records, combined Jev request, threshold/veto scoring, and continuation message. Failure feedback names the target, comparator, requested amount, observed amount when deterministically available, and the handoff gap. It does not infer quotas or let a final-answer omission of the quota erase the original request.

## Files

- `vidbyte/lib/enums/jev.py`: check and question key.
- `vidbyte/lib/constants/jev.py`: threshold and structured state field names.
- `vidbyte/lib/dataclasses/jev.py`: request-derived extent items, handoff evidence, and record fields.
- `vidbyte/lib/jev/done/output_extent.py`, `done.py`, and `__init__.py`: fixed recognition question, registry, and export.
- `vidbyte/agents/jev/done/run_state.py`, `handoff.py`, and `vidbyte/agents/jev/continuation/done.py`: schema composition, conversion, deterministic measurement, scoring, and focus feedback.
- `tests/test_jev_done.py`, `tests/features/jev_output_extent/`: behavior coverage and feature contract.
- `vidbyte/lib/jev/done/README.md`, relevant public exports, and `skills/jev-continuation/SKILL.md`: developer guidance.

## Risks and limits

Word and character counts have straightforward text semantics, but page count depends on layout and line count depends on line breaks, so the generated item must preserve the user's stated basis. Only count when the target is the final answer text and the requested unit has an unambiguous code-side rule; use Jev's recognition of quoted artifact evidence otherwise. Exact and maximum constraints must fail when output is over the bound, while minimum constraints fail only below it. Do not count repeated padding as distinct content unless the request asks for repetition; avoid making content quality a hidden criterion.

## Verification

Run focused output-extent tests, `tests/test_jev_done.py`, formatting/lint and the repository's required local verification workflow. Open a draft PR, then watch its required CI checks and address failures.
