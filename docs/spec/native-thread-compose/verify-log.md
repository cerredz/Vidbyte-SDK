# Verification log: Composite thread functions across Grok, opencode and Muse

Gate set (from context/code-map.md §1.3 and the S5 briefing §4; run from the worktree root in this order):

| # | Gate | Command | Where |
|---|---|---|---|
| 1 | Lint | `python lint/run.py` → last line `SDK-LINT: PASS` | local (also inside gate 6 and the remote source job) |
| 2 | Ratchet counts | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` → 223, must not rise; `python -m ruff check pyproject.toml vidbyte --config lint/ruff.toml --select TID251 --no-cache` → exactly 5 | local |
| 3 | Semgrep | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` → 0 findings (semgrep from the scratch `semgrep-venv`) | local; remote in `static-policy.yml` |
| 4 | New tests | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` → 299 pass | local |
| 5 | Base pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` → `436 passed, 2 skipped` | local |
| 6 | CI source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` → `CI passed.` | local |
| 7 | CI package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package --dist-dir <new empty scratch folder>` → `passed smoke checks.` | local |
| 8 | AC-21 wheel half | `<installed copy>/python.exe -I <scratch>/s3/check_wheel_prompts.py <worktree>`, run from a folder outside the checkout → `AC-21 WHEEL HALF: PASS` | local only |
| 9 | Comment width | `awk 'length($0) > 72' <file>`, piped to `grep -E '^[[:space:]]*#'`, over every changed source file → 0 lines | local only |
| 10 | Remote checks | `gh workflow run ci.yml --ref feat/native-thread-compose` (Source / Python 3.11, Source / Python 3.12, Package on ubuntu-latest) and `gh workflow run static-policy.yml --ref feat/native-thread-compose`, then `gh run watch <id> --exit-status` | remote only; dispatch-only, so `gh pr checks` shows nothing |
| — | Frozen test tree | `git diff 34fe19b7..HEAD --stat -- tests` → empty | local |

## Iteration 1 — 2026-10-18 12:57 -0400 — agent report: reports/S5-repair-1.md

**Defects in:**
- Confirmed findings R-1 to R-10 and R-12 to R-15. R-11, R-16 and R-17 had already been fixed by the test author (4d3ee613, 742db6bf, c81d8596).
- Minor findings tagged trivial: R-18 to R-23.
- Failing gate 4 at 0006acaf: `22 failed, 277 passed`. The 21 R-3 cases of `test_a_refusal_of_caller_text_never_quotes_the_key_it_holds` failed, plus the R-10 case `test_two_failed_worktree_adds_propagate_one_error_after_both_cleanups_end`.
- Not handed to this loop: the follow-ups R-24 to R-31 and the refuted rows (R-C4, R-V5's derived caps).

**Hypotheses and attempts** (in order; the failed ones first within each item):
- **R-10 and R-14, how to wait out cleanups.**
  - `asyncio.shield` around each cleanup: rejected before coding. The shielded await itself is abandoned by the next cancel, so the composite returns while the removal still runs.
  - A `gather(return_exceptions=True)` loop: rejected. S063 must classify every result, and a second cancel still breaks out of the await.
  - Chosen: `ComposeCalls.settle`. It runs `asyncio.wait(tasks)`. On a cancel it keeps waiting under `contextlib.suppress(CancelledError)`, on a not-done set rebuilt every turn, until every task has ended. A bare `raise` then re-raises the first cancel object it caught, and the `finally` reads every `task.exception()`. This was proven in scratch first (`s5-1/settle_semantics.py`) under asyncio and under anyio 4.14.1.
  - The briefing's known-failed variants were not retried: a fresh `CancelledError()`, and a reused pending set.
  - `fan_out` now cancels whatever is still running in a `finally` and settles all children. The planner and the selector go through `fan_out` as one-child fan-outs, so an anyio cancel scope cannot strand them.
  - R-14 is fixed by waiting out the started `git worktree add` (`DisposableWorktree._settled`, bounded by the 120 s git timeout of INV-30) before removing the worktree. The known-failed `--force --force` was not used, and the §9.2 argv is unchanged.
  - R-4 is fixed by splitting `add_worktree` into `worktree_folder`, `add_worktree(folder)` and `fill_worktree(folder, tree)`. The half-made-worktree cleanup moved to `DisposableWorktree.__aenter__`.
- **R-8.** Each reader stores its answer in a positional `kept` list inside its worktree block. The except handler attaches the record built by `_kept`: every verdict or proposal once every reader has answered, otherwise the writer or plan alone, because positional verdicts cannot show a gap.
- **R-15.**
  - Attempt 1, `copy.copy(step)` in `ThreadBinder._derived`, raised S061 from 5 to 6, because S061 flags any call named `copy`.
  - Replaced with `object.__new__(ThreadStep)` plus a `dataclasses.fields` copy, so a derived step checks only what changes. No suppression was added.
- **R-3.**
  - Lowering the 80-character quote limit is known-failed.
  - Scrubbing the bound keys out of the message alone was rejected: a refusal would still echo the caller's text.
  - Chosen: a `quote=False` switch on `RecordFieldValidator.require_text` (grant c), used at every caller-text site.
  - The binders re-raise the record's model refusal with the model named by its type only, keeping `details["field"]`. The refusal is raised after the `except` block, so neither `__context__` nor `__cause__` holds the original. This follows the `vidbyte_gateway.py` precedent. What the base functions raise is unchanged (NG-1).
- **R-9.** I001 rose from 223 to 225, because two import lines in `chain.py` and `ensemble.py` passed 88 columns. Wrapping them in the parenthesized form brought it back to 223.
- **R-12.**
  - The first constant name, `COMPOSE_SURROGATE_PASS`, raised S054 from 3 to 4: ruff S105 treats any name containing "pass" as a password. I read the diagnostic in full and renamed the constants to `COMPOSE_SURROGATE_ENCODE_ERRORS` and `COMPOSE_SURROGATE_DECODE_ERRORS`.
  - The refusal first said "lone surrogate". It now says "a surrogate code point", because two halves of a pair split apart also trip it.
- **R-13.** The refusal sits in `PromptFitter.check`, after `require_template`, so `chain_threads` and `run_staged_threads` both refuse before any I/O.
- **Remote CI, new in this iteration.** CI run 39146593515 at ca4f2bdd failed both source legs on the same two tests, with the same assertion: `git text 'aborted by hook' missing from "Preparing worktree (detached HEAD da56015)\nfatal: in 'prepared' phase, update aborted by the reference-transaction hook"`. The tests are `test_a_failed_worktree_add_stops_the_holding_sibling_before_its_error_propagates` and `test_two_failed_worktree_adds_propagate_one_error_after_both_cleanups_end`.
  - Hypothesis "my source changed git's text": refuted. `ComposeFailures.error` carries git's stderr verbatim (INV-6). The scratch plugin `s5-1/git254/s5_git254.py` rewrites git's wording to the 2.54+ form on the local git, and the frozen tests then fail exactly as on the runner: `2 failed, 3 deselected`.
  - Hypothesis "the runner's git wording changed": confirmed.
    - The runner's git is 2.55.0 and the local git is 2.49.0.windows.1.
    - `refs.c` from v2.49.0 to v2.53.0 has `die(_("ref updates aborted by hook"))`. From v2.54.0 it has `N_("in '%s' phase, update aborted by the reference-transaction hook")`.
    - Both tests arrived in 742db6bf, after the last green remote run (39119540221 at ce8ad488), so they had never run on the runner.
  - No source fix is legitimate: the expected text belongs to git, not compose. The proposed test change goes to the orchestrator (BLOCKED, see Still open).
  - A scratch copy of the module with `git_text="aborted by"` gives `5 passed` under both wordings.

**Changes:**

| SHA | Commit |
|---|---|
| a1d17451 | fix(compose): settle cleanups through repeated cancels and wait out a started worktree add [R-10, R-4, R-14] |
| 7eda491a | fix(compose): keep every finished reader's answer when its worktree cannot be removed [R-8] |
| 1d5d4d90 | fix(compose): derive relocated, anchored and rung steps checking only what changes [R-15] |
| 44475dcd | fix(compose): name every validator floor beside its cap [R-2] |
| 361e0589 | fix(compose): bound item counts through to_tuple min_items [R-7] |
| 4b153b94 | fix(compose): never quote caller text in a refusal [R-3] |
| 77b85d53 | fix(compose): carry prompt segments as PromptSegment records [R-9] |
| b009653b | fix(compose): scrub bound keys through one lib helper [R-5] (also removes the `_replace` that R-22 named) |
| 5202ec02 | fix(compose): keep surrogates from failing a step or the up-front check [R-12] |
| 9cbd47d6 | fix(compose): refuse a placeholder-only template before any I/O [R-13] |
| b5b73be2 | fix(compose): keep model-addressed text out of the truncated-answer problem [R-1] |
| 337c45e6 | fix(compose): wrap every comment line at 72 columns [R-6] |
| 027dc75b | fix(compose): name compose failures among the backstop skips [R-18] |
| 3b515e65 | fix(compose): name the stage attempt list attempts [R-20] |
| c07700aa | fix(docs): describe the native composites without claiming read-only steps [R-21] |
| 6b09e92e | fix(compose): close three header slips [R-22] |
| dca3f7b5 | fix(compose): tell verifiers their findings are limited [R-23] |
| 3065184a | fix(spec): record JSON_KIND_NAMES as the json_text module constant it is [R-19] |
| ca4f2bdd | docs(spec): record the four S5 grants in section 17 and the 8.4 counts |

**Gate matrix out** (gates 1–9 at ca4f2bdd, run in this worktree in this iteration; the records commit on top changes only docs/spec):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| 1 lint | `python lint/run.py` | PASS; count table identical to S4's | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline`<br>`S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all`<br>`SDK-LINT: PASS` |
| 2 ratchets | ruff I001 / TID251 | PASS (223 / 5) | `Found 223 errors.`<br>[*] 223 fixable with the `--fix` option.<br>`Found 5 errors.` |
| 3 semgrep | `--test`, then `scan --error` | PASS | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` (exit 0) |
| 4 new tests | `pytest -q tests/features/harness_compose` | PASS (was 22 failed) | `299 passed in 54.67s` |
| 5 base pack | `pytest -q tests/features/harness_threads` | PASS | `436 passed, 2 skipped in 41.49s` |
| 6 source stage | `run_ci.py --stage source` | PASS | `================ 5940 passed, 16 skipped in 143.17s (0:02:23) =================`<br>`CI passed.` |
| 7 package stage | `run_ci.py --stage package --dist-dir s5-1/dist-1` | PASS | `No broken requirements found.`<br>`Installed vidbyte-sdk 0.3.0 passed smoke checks.`<br>`CI passed.` |
| 8 AC-21 wheel half | `wheel-venv-1/Scripts/python.exe -I s3/check_wheel_prompts.py`, from `s5-1/wheel-run-1` | PASS | `installed vidbyte: ...\s5-1\wheel-venv-1\Lib\site-packages\vidbyte\__init__.py (outside the checkout: True)`<br>`fixed combinations: 17, longest planner = 8304 chars, over 12000: {}`<br>`AC-21 WHEEL HALF: PASS` |
| 9 comment width | awk over the 18 changed `.py` files | PASS | `iteration files: 18 over72=0` (the 9 long lines in `vidbyte/lib/errors/base.py` predate the PR: 9 at 5c08c35e, none added) |
| frozen tests | `git diff 34fe19b7..HEAD --stat -- tests` | PASS | empty |
| 10 remote: Static policy | run 39146595669 at ca4f2bdd | PASS | `Run Static policy (39146595669) has already completed with 'success'` |
| 10 remote: CI | run 39146593515 at ca4f2bdd | FAIL: 2 tests on both source legs; Package skipped | `FAILED tests/features/harness_compose/test_harness_compose_concurrency.py::test_a_failed_worktree_add_stops_the_holding_sibling_before_its_error_propagates - AssertionError: git text 'aborted by hook' missing from ...`<br>`FAILED ...::test_two_failed_worktree_adds_propagate_one_error_after_both_cleanups_end - AssertionError: git text 'aborted by hook' missing from ...`<br>`===== 2 failed, 5898 passed, 56 skipped, 19 warnings in 122.22s (0:02:02) ======` (3.12; 3.11: `2 failed, 5898 passed, 56 skipped in 126.42s`) |

**Still open:**
- **Remote CI.** The two frozen EC-19 tests above expect git's pre-2.54 wording. This needs a test change, which only the orchestrator can approve (BLOCKED). The proposal: at `tests/features/harness_compose/test_harness_compose_concurrency.py:225` and `:266`, change `git_text="aborted by hook"` to `git_text="aborted by"`. The header's KNOWN EDGE CASES sentence (line 9) should name both wordings. Evidence and the before/after runs are in reports/S5-repair-1.md.
- **No confirmed finding is open.** R-24 to R-31 remain follow-ups, outside this loop.
- **Spec passages made stale by the fixes.** Their edits are outside the allowed set and await a ruling (listed in the report): D-17, §8.2, §8.5, §12.3 rows 14 and the count sentence, and the §17 Fan-out, Rendering, Plumbing helpers and Record-so-far bullets.
