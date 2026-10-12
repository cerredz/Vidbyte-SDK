# S5 repair iteration 1 — managed-generative-models

**Stage:** S5 repair 1 of 8. **Branch:** `feat/managed-generative-models`. **Start:** f7eac30a. **Final head:** d3997ca3 (pushed). **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/759 (draft).

This file is deliberately left untracked, as the coordinator asked. The durable record is `verify-log.md`, iteration 1.

## Gate matrix
The code head is 90459fb8, and d3997ca3 adds only `verify-log.md` and `review.md` status cells. Lint and `gh pr checks` were re-run on d3997ca3: `SDK-LINT: PASS`, and no checks.

| Gate | Result | Final lines |
|---|---|---|
| (a) pack, `env -u DEEPSEEK_API_KEY PYTHONPATH=$(pwd) python -m pytest tests/features/sdk_managed_text -q -p no:cacheprovider` | PASS | `39 passed in 0.93s` |
| (b) full suite, the same with no path | PASS | `3011 passed, 1 skipped in 15.60s` |
| (b′) full suite with a fake live-format `VIDBYTE_API_KEY` and `-p vnetblock` | PASS | `3011 passed, 1 skipped in 16.85s`; 0 blocked network attempts |
| (c) `python lint/run.py` | PASS | `A002 IMPROVED 703 -> 652…` / `SDK-LINT: PASS` (S020 1/1, S062 889/889, A001 643/643, C020 2/2, S064 4/4, C017 0, C018 1/1) |
| (d) `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `3011 passed, 1 skipped in 16.30s` / `CI passed.` |
| (d) `python scripts/run_ci.py --stage package` (PYTHONPATH unset) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| (e) scratch-venv `pysemgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` | PASS | `• Findings: 0 (0 blocking)` / `Ran 1 rule on 872 files: 0 findings.` |
| (f) `gh pr checks …/pull/759` | none ran | `no checks reported on the 'feat/managed-generative-models' branch`. The commit API shows 0 check runs and 0 statuses, because automatic triggers are disabled. |

## Per finding
- **R-1, fixed @92d3d690.** I made the four moves from review.md. The markers now sit at:
  - `text.py:38` (def 24);
  - `text.py:70` (def 60);
  - `vidbyte_gateway.py:156` (def 141, after M-5);
  - the BYOK narration above the BYOK return in `resolved_api_key`.

  A002 stayed at 653 with no new name, and no added `#` line is over 72 columns. Only the edited blocks were rewrapped.
- **R-5, fixed @23a5e87c.** The 13 remaining markers each followed a summary line. Eleven summaries became one-line docstrings, the shape #747's `bash.py` and `toolsets/coding.py` use. `validate()`'s body narration was folded into its `@intent` block. The `find_vidbyte_api_key` block was refilled evenly. My checker now finds no new marker preceded by a comment; the only remaining ones are the 6 pre-existing Decision markers.
- **M-5, fixed @443ac21a.** I added the gateway `__init__` `@intent` block. A002 went from 653 to 652, and the gateway module has no A002 findings left.
- **R-2, fixed @745f8efe.** `validate()` now calls `ProviderModelRegistry.resolve_api_key(provider, self.api_key)`. The probe shows calls dropping from {2, 2, 1} to {1, 1, 0}, with the same message.
- **R-6, fixed @8eea0362.** New file `tests/features/sdk_managed_text/test_managed_text_deadline.py` with 7 tests and a full A001 header. It kills all five R-6 mutants plus `mut_first` and `auto_shape_unchecked`; the full table is in verify-log.md. `shorten_attempt` is killed deterministically here (4 failed). The old pack caught it on only 1 of 4 runs.
- **R-3, fixed @8eea0362.** Reproduced first: with only the test file staged, S020 was 2/1 REGRESSED. I added one bullet to the pack README's File Index, and S020 is back to 1/1. No other README line changed.
- **M-9, fixed @8eea0362.** Covered inside the new file: 502→422, 502→no response, and direct `validate()` calls for EC-7 and EC-3.
- **R-4, fixed @15eb286e.** Reproduced first: 1 blocked POST to `…/api/v1/models/generate`. After the context-manager wrap, 0. A scratch copy with a trailing `self.fail` fails, so the body runs. No assertion changed.
- **M-1, fixed @69ee8aaa.** Gemini, xai, deepseek and kimi now get "Use TextModelRunner: streaming supports only anthropic, openai, so setting <ENV> would not make <provider> stream either." openai and anthropic keep the original message, and the S2 test still passes.
- **M-7, fixed @a6dbcd2c.** The `jev.py` header fields cover the gateway values. "backend 9.2.8" becomes the backend spec r3 section 9.2.8 at a14b37e7e (spec A-1). The `model_configs.py` inventory line mentions the placeholder.
- **M-14, fixed @028b2708.** Only the one FEATURE.md bullet changed.
- **M-2, fixed @15203ae4.** **M-3 (citation), fixed @22a0a7ba.** **M-4, fixed @90459fb8**, which also carries the single §17 row.

## Test changes proposed
None. The only edit to a pre-existing test is the pre-granted R-4 wrap. The only edits to S2 pack files are the granted README bullet (R-3) and the FEATURE.md bullet (M-14).

## Findings I believe are wrong
None.

## Open, but not a confirmed finding (needs an orchestrator decision)
1. **R-6's documentation step.** review.md's smallest fix for R-6 also asks to add AC-28 to spec §6.2, point `test-plan.md:20` (EC-38) at the new test, and set the test-plan header to r5. Briefing §7 allows spec edits only for M-2, M-3 and M-4, and does not list `test-plan.md`, so I did not make these edits. The test, which is what the finding claimed was missing, is done. If granted, this is three text edits.
2. **EC-16 text after M-1.** It describes only the openai/anthropic wording. That needs a spec-edit grant; for now the §17 row records the difference.
3. **Remote CI.** It was not dispatched. The #747 precedent is to dispatch by hand: `gh workflow run ci.yml --ref feat/managed-generative-models` and `gh workflow run static-policy.yml --ref feat/managed-generative-models`.
4. **Follow-ups for the PR body:** M-3 (serving more providers), M-6, M-8, M-10, M-11, M-12 and M-13.

## Niche facts for the next agent
- **A002 window.** It is lines def−3 to def+20. `TextModelConfig.normalized_provider` (def 81) has no marker of its own; validate's `@intent` (now line 96) covers it. Moving that marker below line 101 creates a new A002 finding.
- **mutplug patterns.** They match exact source strings: the validate managed branch, the `resolved_api_key` placeholder branch, `retry_wait = …`, the `else:` after the re-send, and `deadline = loop.time() + timeout_seconds`. Edits there break mutant re-runs (assert count == 1).
- **Line endings.** Index files are LF, and some working copies are CRLF (`text.py`, `streaming_text.py`, `jev.py`, `test_jev_run_state_relation.py`). Edit while preserving line endings.
- **`grep -c` in a chain.** When it counts 0 it exits with status 1 and breaks an `&&` chain. One commit had to be re-run because of this.
