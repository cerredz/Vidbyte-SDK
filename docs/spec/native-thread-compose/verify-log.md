# Verification log: Composite thread functions across Grok, opencode and Muse

Gate set (from context/code-map.md §1.3 and the S5 briefing §4; run from the worktree root in this order):

| # | Gate | Command | Where |
|---|---|---|---|
| 1 | Lint | `python lint/run.py` → last line `SDK-LINT: PASS` | local (also inside gate 6 and the remote source job) |
| 2 | Ratchet counts | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` → 223, must not rise; `python -m ruff check pyproject.toml vidbyte --config lint/ruff.toml --select TID251 --no-cache` → exactly 5 | local |
| 3 | Semgrep | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` → 0 findings (semgrep from the scratch `semgrep-venv`) | local; remote in `static-policy.yml` |
| 4 | New tests | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` → 385 pass (363 before the test author's 22 R-33 cases, 8fcba2df; 299 before the 64 S4 regression cases, d9cc9ff6) | local |
| 5 | Base pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` → `436 passed, 2 skipped` | local |
| 6 | CI source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` → `CI passed.` | local |
| 7 | CI package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package --dist-dir <new empty scratch folder>` → `passed smoke checks.` | local |
| 8 | AC-21 wheel half | `<installed copy>/python.exe -I <scratch>/s3/check_wheel_prompts.py <worktree>`, run from a folder outside the checkout → `AC-21 WHEEL HALF: PASS` | local only |
| 9 | Comment width | `awk 'length($0) > 72' <file>`, piped to `grep -E '^[[:space:]]*#'`, over every changed source file → 0 lines | local only |
| 10 | Remote checks | `gh workflow run ci.yml --ref feat/native-thread-compose` (Source / Python 3.11, Source / Python 3.12, Package on ubuntu-latest) and `gh workflow run static-policy.yml --ref feat/native-thread-compose`, then `gh run watch <id> --exit-status` | remote only; dispatch-only, so `gh pr checks` shows nothing |
| — | Frozen test tree | `git diff 1d7bfbec..HEAD --stat -- tests` → empty (the test tree was last changed at 8fcba2df, by the test author, and its baseline is 1d7bfbec; iteration 2 used d9cc9ff6 and iteration 1 used 34fe19b7) | local |

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

### Iteration 1 addendum — 2026-10-18 13:24 -0400 — the granted test change

**The grant** (orchestrator, quoted as received): "GRANT (orchestrator, test change): In tests/features/harness_compose/test_harness_compose_concurrency.py, change `git_text="aborted by hook"` to `git_text="aborted by"` at the two call sites (:225 and :266), and update the header's KNOWN EDGE CASES entry (line 9) to name both git wordings. Git 2.53 and earlier print "ref updates aborted by hook". Git 2.54 and later print "in 'prepared' phase, update aborted by the reference-transaction hook". Change nothing else in the test tree. Reason: the spec requires the error to carry git's own text, not one git version's wording (INV-6, EC-19, EC-59/T-6). The hard-coded phrase makes a spec-conforming implementation fail on the CI runner's git 2.55.0 (run 39146593515). I checked this myself against the run log, which shows `fatal: in 'prepared' phase, update aborted by the reference-transaction hook`, and against local git 2.49.0."

**The change.** One commit: 3a21352b `test(compose): accept both git wordings of a hook-aborted worktree add [gate:ci]`. It is the only change to the test tree since 34fe19b7, and it touches only the three granted lines of `tests/features/harness_compose/test_harness_compose_concurrency.py`:

| Line | Before | After |
|---|---|---|
| 225 | `    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by hook")` | `    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by")` |
| 266 | `        check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by hook")` | `        check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by")` |
| 9 (KNOWN EDGE CASES; only this sentence changed) | `A reference-transaction hook that exits 1 when the add's transaction is prepared makes git print "ref updates aborted by hook", exit 128 and remove the new folder and its registration itself; worktree remove runs no such hook.` | `A reference-transaction hook that exits 1 when the add's transaction is prepared makes git print "ref updates aborted by hook" (git 2.53 and earlier) or "in 'prepared' phase, update aborted by the reference-transaction hook" (git 2.54 and later), exit 128 and remove the new folder and its registration itself; worktree remove runs no such hook.` |

**Local verification at 3a21352b:**
- The two tests under the local git 2.49 wording: `2 passed, 3 deselected in 3.84s`.
- The two tests under the 2.54+ wording (`-p s5_git254`): `2 passed, 3 deselected in 3.62s` and `s5_git254: git messages rewritten: 11`.
- The compose pack, `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose`: `299 passed in 54.82s`.
- Lint, `python lint/run.py`: `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` and `SDK-LINT: PASS`. The count table is identical to S4's.
- The source stage, `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`: `================ 5940 passed, 16 skipped in 137.70s (0:02:17) =================` and `CI passed.`
- The comment-width check on the test file: 0 lines. `procs.py --kill` afterwards: `stand-in or grandchild processes: []`.
- `git diff 34fe19b7..HEAD --stat -- tests`: `tests/features/harness_compose/test_harness_compose_concurrency.py | 6 +++---`, which is the three granted lines.
- Not re-run: the ratchet counts, semgrep, the base pack, the package stage and the AC-21 wheel check. Nothing they read changed after ca4f2bdd, where all of them passed: `git diff --stat ca4f2bdd..HEAD -- vidbyte pyproject.toml scripts lint .semgrep .github` is empty.

**Remote at 3a21352b** (each watch's exit code was captured before any pipe):

| Run | Result | Final lines |
|---|---|---|
| CI 39148626228 | success: Source / Python 3.12, Source / Python 3.11 and Package; watch exit 0 | 3.12: `========== 5900 passed, 56 skipped, 19 warnings in 129.76s (0:02:09) ===========`, then `CI passed.`<br>3.11: `================= 5900 passed, 56 skipped in 127.35s (0:02:07) =================`, then `CI passed.`<br>Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.`, then `CI passed.`<br>`✓ feat/native-thread-compose CI cerredz/Vidbyte-SDK#1186 · 39148626228` |
| Static policy 39148628122 | success; watch exit 0 | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.`<br>`✓ Static policy in 25s (ID 117737539967)` |

The runner's git is still 2.55.0. Both EC-19 tests now run to their end on Linux and pass: 5900 passed and 0 failed, where run 39146593515 had 5898 passed and 2 failed. That includes the lines after the old assertion, which had never run there (process tree stopped, no pending task, one registered worktree, no leftover folder, error within the stop bound). The remote-only real-bash flake did not occur, so no rerun was needed.

**Still open after the addendum:** none. Every gate is green at code HEAD 3a21352b, and no confirmed finding is open. The follow-ups R-24 to R-31 stay outside this loop. The orchestrator is routing the stale spec passages to the spec author, so they are untouched here.

## Iteration 2 — 2026-10-18 16:45 -0400 — agent report: reports/S5-repair-2.md

**Defects in:**
- **R-32** (Major). The R-13 blank-template check refused chain templates that hold `{prompt}`, such as `{prompt}{previous}`, with a false message. The orchestrator ruled it a defect, and this iteration added its row to review.md's confirmed table.
- **The stale comments and docs at the same spot** (briefing item 2):
  - the comment at `texts.py:97–100` and `stages.py:9` cited EC-37 for the blank refusal, where the row is now EC-79;
  - the `texts.py` header and `fit`'s docstring listed only NUL removal and key replacement at send time.
- **Failing gate 4, local and remote, on the same two cases:** `test_a_chain_template_that_holds_prompt_is_never_refused_as_blank[prompt then previous]` and `[prompt and previous on two lines]`.
  - Local: `2 failed, 361 passed`.
  - Remote: CI 39160511817 at d9cc9ff6 failed both source legs (`2 failed, 5962 passed, 56 skipped`), and Package was skipped. Static policy 39160513848 had succeeded.
- Not handed to this loop: the follow-ups R-24 to R-31.

**Hypotheses and attempts** (R-32 is new in this iteration, so no earlier attempt applied):
- **Root cause, confirmed by the traceback and the code.** `ThreadChains._fit` checks each later step's template twice:
  - first with `{prompt}` rendered as `""`, naming `template`, so that a template too long by itself is blamed on the template;
  - then with the caller's prompt, naming `prompt`.

  `PromptFitter.check` ran the R-13 blank check on whichever frame it was given. In the first pass the only fixed text of `{prompt}{previous}` is `""`, so the check refused it. The failing frame was `(PromptSegment(text='', spliced=False), PromptSegment(text='', spliced=True))`, raised at `texts.py:103` from `chain.py:132`.
- **Options weighed before coding.** No option was coded and then dropped.
  1. **Chosen:** an optional `whole` frame on `PromptFitter.check`. Only the blank check reads it, and it defaults to `frame`. The chain's template pass passes the template rendered with the caller's prompt.
     - This keeps the blank check inside `check`, where spec r5 row 13 and §5 put it.
     - The refusal still names `template` and `steps[i]`.
     - Every other caller is unchanged.
     - It follows the strict-config lesson: add a missing option as a keyword with a backward-compatible default.
  2. **Runner-up:** a separate `PromptFitter` method for the blank check, called from both composites' `_fit`.
     - It needs no keyword.
     - But it contradicts spec r5 row 13 ("`PromptFitter.check` … refuses a blank shortest form") and the §5 list, so the spec would need an edit that this iteration may not make.
     - It flips if the reviewer judges a one-caller keyword worse than that spec edit.
  3. **Rejected:** running the blank check in the prompt pass. Its refusal would name `prompt`, which breaks EC-79 and the five pinned refusals.
  4. **Rejected:** rendering the template pass with the caller's prompt and still blaming `template`.
     - A too-long caller prompt would then be blamed on `template`.
     - That breaks the AC-14 case "prompt too long for a later grok step" (field `prompt`) and INV-18's "naming the argument that makes it too long".
  5. **Rejected:** rendering `{prompt}` as a spliced segment in the template pass.
     - The blank check reads only fixed segments, so it would still refuse.
     - The length check would count the prompt as a truncation note.
- **Second commit, docs only (3600d47b).** The send-time order in the docs is now NUL removal, then surrogate repair, then key replacement (INV-18, EC-80 r5). This covers the `texts.py` PURPOSE, the truncation-note count in KNOWN EDGE CASES, the `PromptFitter` and `fit` docstrings, and `fit`'s narration.
- **Third commit, a self-review fix (bc351671).** dc631222's two render lines in `_fit` each repeated the empty answer and diff. A new spliced template value would then have needed two entries in `_fit`, which made the `chain.py` header's COMMON MODIFICATION PATTERNS ("one entry in _values and in _fit") untrue. Both frames now share one annotated dict, written as `ensemble.py` writes its values dict. The full gate was re-run from the top afterwards.
- **Independent evidence beyond the frozen pack:**
  - `s5-2/probe_r32.py` runs only the up-front checks of `chain_threads` and `run_staged_threads` (`_steps`, `_template`, `_fit`), never a step. That matters because grok and opencode are installed on this machine.
    - Before the fix: `PROBE R-32: 13/21 as the spec states`. All 7 templates that hold `{prompt}` were refused as blank, `"{prompt}\n\n{previous}"` included. A 23,990-character prompt in `{prompt}{previous}` was refused as a blank `template` instead of a too-long `prompt`.
    - After the fix: `21/21`.
  - `s5-2/test_s52_natural_template.py` is a scratch test that runs with the pack's conftest as a plugin. It runs three natural templates end to end, each into a Grok, Muse or opencode second step, and checks the exact prompt the second step receives.
    - At bc351671: `9 passed`.
    - Against a `git archive` of 43bd0024: `6 failed, 3 passed`. The 3 that pass are the control template, which has fixed text.
- **HEAD moved during the iteration.** The orchestrator's docs commit 74d770da (pipeline.md only) landed on the branch right after launch. This iteration's commits sit on it, and the first push carried it.
- **Tooling trap.** Here, Git Bash's `grep -c $'\r$'` misreports line endings: it showed CRLF for LF files and 0 for a CRLF file. Count bytes with Python.
  - The compose sources and this file are LF in the working tree; review.md is CRLF.
  - `s5-2/apply_edits.py` keeps each file's own ending.

**Changes:**

| SHA | Commit |
|---|---|
| dc631222 | fix(compose): keep the caller's prompt in a chain template's blank check [R-32] |
| 3600d47b | fix(compose): name the surrogate repair in the prompt-fit docs [R-32] |
| bc351671 | fix(compose): share the empty spliced values between the chain's fit frames [R-32] |
| this records commit | docs(spec): verify-log iteration 2 for native-thread-compose. It also carries the review.md R-32 row and status and reports/S5-repair-2.md. |

**Gate matrix out** (gates 1–9 at bc351671, the final code HEAD, run in this worktree in this iteration; outputs in `s5-2/final/`):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| 1 lint | `python lint/run.py` | PASS. The count table matches iteration 1's line for line. | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline`<br>`S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all`<br>`SDK-LINT: PASS` |
| 2 ratchets | ruff I001 / TID251 | PASS (223 / 5) | `Found 223 errors.`<br>``[*] 223 fixable with the `--fix` option.``<br>`Found 5 errors.` |
| 3 semgrep | `--test`, then `scan --error` | PASS | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` (exit 0) |
| 4 new tests | `pytest -q tests/features/harness_compose` | PASS (was 2 failed) | `363 passed in 89.59s (0:01:29)` |
| 5 base pack | `pytest -q tests/features/harness_threads` | PASS | `436 passed, 2 skipped in 50.92s` |
| 6 source stage | `run_ci.py --stage source` | PASS | `================ 6004 passed, 16 skipped in 184.31s (0:03:04) =================`<br>`CI passed.` |
| 7 package stage | `run_ci.py --stage package --dist-dir s5-2/final/dist-3` | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.`<br>`CI passed.` |
| 8 AC-21 wheel half | `wheel-venv-3/Scripts/python.exe -I s3/check_wheel_prompts.py <worktree>`, from `s5-2/final/wheel-run-3`; the briefing's copy recipe, unchanged | PASS | `installed vidbyte: ...\s5-2\final\wheel-venv-3\Lib\site-packages\vidbyte\__init__.py (outside the checkout: True)`<br>`fixed combinations: 17, longest planner = 8304 chars, over 12000: {}`<br>`AC-21 WHEEL HALF: PASS` |
| 9 comment width | awk over chain.py, stages.py and texts.py | PASS | `over72=0` for each of the 3 files |
| frozen tests | `git diff d9cc9ff6..HEAD --stat -- tests` | PASS | empty |
| 10 remote: Static policy | run 39163919767 at bc351671 | PASS; watch exit 0 | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` |
| 10 remote: CI | run 39163918203 at bc351671 | PASS: Source / Python 3.11, Source / Python 3.12 and Package; watch exit 0 | 3.12: `========== 5964 passed, 56 skipped, 19 warnings in 141.19s (0:02:21) ===========`, then `CI passed.`<br>3.11: `================= 5964 passed, 56 skipped in 135.85s (0:02:15) =================`, then `CI passed.`<br>Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.`, then `CI passed.` |
| 10 remote, intermediate | CI 39162945987 and Static policy 39162947311 at 3600d47b | PASS; watch exit 0 for both | 3.11: `================= 5964 passed, 56 skipped in 136.17s (0:02:16) =================`<br>3.12: `========== 5964 passed, 56 skipped, 19 warnings in 139.17s (0:02:19) ===========`<br>Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` |

Afterwards, `procs.py` printed `stand-in or grandchild processes: []`.

**Still open:** none. R-32 is fixed and every gate is green at code HEAD bc351671. The follow-ups R-24 to R-31 stay outside this loop. The one judgement call for the re-review is the one-caller `whole` keyword (option 1 above). Its runner-up and flip condition are recorded above.

## Iteration 3 — 2026-10-20 01:09 -0400 — agent report: reports/S5-repair-3.md

**Defects in:**
- **R-33** (Blocker, review.md, confirmed in reports/S5-findings-verifier-rr1.md). A short key put into a compose record field was quoted, key and all, in that record's `ConfigurationError` whenever the record was reached other than through a binder:
  - a `ThreadStep` built directly or changed with `dataclasses.replace` (EC-78), through `harness`, `verb`, `model` and `thread_id`;
  - `StageSpec.retries`, `StageAttempt.rung` and `.decision`, `ThreadVerdict.decision`, `WorkspaceDiff.truncated`, `EnsembleRole.name` and `EnsembleSelection.proposal`;
  - three of those through a step's JSON answer, whose refusal `JsonAnswer.problem` keeps.
- **Failing gate 4** at ad6ec58e: the test author's 21 R-33 rows (8fcba2df). The reproducer `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose/test_harness_compose_keys.py` gave `21 failed, 26 passed in 7.88s`, each on `AssertionError: INV-4: the <site> refusal quotes the key`. Remote CI 39369688747 at 1d7bfbec was pre-repair evidence of the same 21.
- HEAD had moved to 0fda73fb (the orchestrator's pipeline.md commit) before this iteration's first commit. This iteration's commits sit on it.
- Not handed to this loop: the follow-ups R-24 to R-31, and the out-of-scope items of the verifier report section 5 (the base refusals, the base config records, the stdlib `Enum(value)` errors, accepted misplaced keys, the raw decoder text in `JsonAnswer.problem`).

**Hypotheses and attempts** (R-33 is new in this iteration, so no earlier attempt applied):
- **Root cause, confirmed by the reproducer and the code.** `RecordFieldValidator._received` quotes a short str. Compose's records still called `to_enum`, `require_int`, `require_bool` and one `require_text` with quoting on, and only the binders rewrote the probe `NativeThreadRequest`'s model refusal (`ThreadBinder._withheld`).
- **Attempt 1, rejected before commit: the reference fix as written.** The verifier's `_withheld` (proposed_fix.diff) scans `(model, thread_id)` and rewrites the first repr it finds in the message. I tested that assumption first.
  - The scratch probe `s5-3/probes/probe_withheld_exact.py` uses an accepted grok model `"grok-4"` and a refused `thread_id="<key> 'grok-4'"`. The thread id's repr is double-quoted and holds the model's repr.
  - On the verifier's proof copy (`s5-verifier-rr1/lint_patched`), the scan rewrites only the model's repr. Both the direct build and `dataclasses.replace` print `key-shown=True | 'thread_id must match ^[A-Za-z0-9][A-Za-z0-9_-]*$; got "vbk-7c3a91e0d24f a value of type str".'`
  - The input is contrived, but re-review round 2 is the last one, and the briefing asks for the class closed by construction.
- **Attempt 2, chosen: pick the value by the field the refusal names.** `_withheld` reads `{"model": self.model, "thread_id": self.thread_id}.get(error.details.get("field", ""))`. The base refusal quotes exactly the value of the field it names, so `rpartition(repr(value))` removes the whole quote.
  - The 8 cases of probe_withheld_exact.py are all `key-shown=False context=None cause=None` on this tree.
  - The coupling to the base field names "model" and "thread_id" is guarded: a base rename would turn the six model and thread-id rows of `test_a_record_refusal_never_quotes_the_key_it_was_given` red on `details["field"]`.
  - The flip condition: if the base record ever quotes a value other than the field it names, go back to a scan, longest repr first.
- **Attempt 2a, failed lint, then fixed.** The first version passed `error.details.get("field")` straight to the lookup. `python lint/run.py` then failed with `S009 REGRESSED: 351 finding(s), allowance 350`.
  - S009 is a package-wide mypy ratchet: `python -m mypy --config-file lint/mypy.ini vidbyte`.
  - The new finding was `vidbyte\lib\dataclasses\native_compose.py:147:72: error: Argument 1 to "get" of "dict" has incompatible type "Any | None"; expected "str"  [arg-type]`.
  - The fix aligns producer and consumer with a default, `.get("field", "")`, with the same behaviour: no field means nothing is withheld. No `Any` and no ignore were added. S009 went back to 350, and the whole lint count table is identical to iteration 2's.
  - The verifier's proof copy never hit S009, because its scan does no dict lookup.
- **Considered and not coded:**
  - An inline try/except with `raise ... from None`. Known-failed: `from None` still sets `__context__`, which the rows walk (test-plan note for this iteration).
  - An inline try/except with the raise after the handler. It works, as in the old binder, but it puts a handler and a sentinel into the narrated main function. `_probe` keeps it flat, as `_checked_config` does.
  - Pre-checking the model and thread id with `quote=False` inside `ThreadStep`. It duplicates the base's per-harness rules (principle 5), and `require_optional_text` has no `quote` keyword, so it is outside the grant.
  - Flipping `_received` so it never quotes a str (NG-1; its own PR).
- **A trade-off, recorded.** `quote=False` hides every refused value, not only a str. For example, `StageSpec(retries=4)` now ends `got a value of type int.` where it used to end `got 4.`. The bound stays in the message, and grant (c) defines `quote` this way for `require_text`. The flip condition: if reviewers want ints quoted, change `_received` to withhold only str under `quote=False`, which is part of the SDK-wide `_received` move.
- **Tooling trap, new here.** A long `<<'EOF'` heredoc holding apostrophes failed in the Bash tool (`unexpected EOF while looking for matching ''`). Edit scripts and commit messages were written with the file tool and applied with `s5-2/apply_edits.py`.

**Changes:**

| SHA | Commit |
|---|---|
| 0e4321a4 | fix(compose): withhold a misplaced key from every record refusal [R-33] |
| 7aad13ba | docs(spec): record the R-33 grant for native-thread-compose |
| this records commit | docs(spec): verify-log iteration 3 for native-thread-compose. It also carries the review.md R-33 status, this log's two refreshed gate-table rows and reports/S5-repair-3.md. |

0e4321a4 touches 4 files and adds no file and no class (§8.4 holds):
- `validation.py`: `quote` on `require_int`, `require_bool` and `to_enum`, defaulting to True, so the 11 base calls are unchanged; plus the header and method comments.
- `native_compose.py`:
  - `quote=False` at `ThreadStep.harness` and `.verb`, `PromptSegment.spliced`, `WorkspaceDiff.truncated`, `ThreadVerdict.decision`, `StageSpec.retries`, and `StageAttempt.rung` and `.decision`;
  - `ThreadStep._probe` and `_withheld`, with `@intent step-refusals-withhold-a-misplaced-key`;
  - the narrated probe step;
  - the header FUNCTION INVENTORY and KNOWN EDGE CASES.
- `native_ensemble.py`: `quote=False` at `EnsembleRole.name` and `EnsembleSelection.proposal`, plus a KNOWN EDGE CASES sentence.
- `steps.py`: plain `return ThreadStep(...)` in both binders; `ThreadBinder._withheld` deleted; header lines 6 and 9 updated. The `quote=False` thread-id pre-check in `bind_continue` stays.

7aad13ba changes exactly spec.md lines 731, 1103, 1308, 1588 and 1626 (5 insertions, 5 deletions), and the file stays CRLF.

**Independent evidence beyond the frozen pack** (scratch outputs in `s5-3/probes/`):
- The verifier's class sweep `s5-verifier-rr1/probe_sweep.py` on this tree prints `TOTAL (entry, record, field) pairs: 183; leaking: 4; clean: 179`. The 4 are the stdlib `Enum(value)` constructors (out of scope, item 4).
- `ctx_count.py` prints `1796 ('clean', 'None')`, `352 ('ACCEPTED', '-')` and `4 ('OTHER-LEAK', '-')`: every refusal is clean and has no `__context__`.
- `probe_answers.py` prints `key-in-problem=False` for all 4 answers, with the field still named (EC-28).
- The reviewer's four `s5-rereview-1/probe_keys_*.py` probes print `key-in-message=False` on every line.
- The verifier's 18-row test `test_s5v_rr1_record_keys.py`: `18 passed in 29.17s`.

**Gate matrix out** (gates 1–9 at 7aad13ba, whose code is 0e4321a4, run in this worktree in this iteration; outputs in `s5-3/final/`):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| 1 lint | `python lint/run.py` | PASS. The count table matches iteration 2's line for line, with S009 at 350/350. | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline`<br>`S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all`<br>`SDK-LINT: PASS` |
| 2 ratchets | ruff I001 / TID251 | PASS (223 / 5) | `Found 223 errors.`<br>``[*] 223 fixable with the `--fix` option.``<br>`Found 5 errors.` |
| 3 semgrep | `--test`, then `scan --error` | PASS | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` (exit 0) |
| 4 new tests | `pytest -q tests/features/harness_compose` | PASS (was 21 failed) | `385 passed in 55.26s` |
| 5 base pack | `pytest -q tests/features/harness_threads` | PASS | `436 passed, 2 skipped in 45.46s` |
| 6 source stage | `run_ci.py --stage source` | PASS | `================ 6026 passed, 16 skipped in 156.80s (0:02:36) =================`<br>`CI passed.` |
| 7 package stage | `run_ci.py --stage package --dist-dir s5-3/final/dist-4` | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.`<br>`CI passed.` |
| 8 AC-21 wheel half | `wheel-venv-4/Scripts/python.exe -I s3/check_wheel_prompts.py <worktree>`, from `s5-3/final/wheel-run-4`, using the briefing's copy recipe | PASS | `installed vidbyte: ...\s5-3\final\wheel-venv-4\Lib\site-packages\vidbyte\__init__.py (outside the checkout: True)`<br>`fixed combinations: 17, longest planner = 8304 chars, over 12000: {}`<br>`AC-21 WHEEL HALF: PASS` |
| 9 comment width | awk over the 4 changed `.py` files | PASS | `over72=0` for each of the 4 files |
| frozen tests | `git diff 1d7bfbec..HEAD --stat -- tests` | PASS | empty |
| 10 remote: Static policy | run 39372992819 at 7aad13ba | PASS; watch exit 0 | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` |
| 10 remote: CI | run 39372990529 at 7aad13ba | PASS: Source / Python 3.11, Source / Python 3.12 and Package; watch exit 0 | 3.11: `================= 5986 passed, 56 skipped in 109.14s (0:01:49) =================`, then `CI passed.`<br>3.12: `========== 5986 passed, 56 skipped, 19 warnings in 113.19s (0:01:53) ===========`, then `CI passed.`<br>Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.`, then `CI passed.` |

Afterwards, `procs.py` printed `stand-in or grandchild processes: []`.

**Still open:** none. R-33 is fixed, and every gate is green at code HEAD 0e4321a4, through 7aad13ba, locally and remotely. The remote totals are iteration 2's 5964 plus the 22 R-33 cases, and neither known remote flake occurred. The follow-ups R-24 to R-31 and the verifier's out-of-scope items stay outside this loop. The one design call for re-review round 2 is the field-keyed `_withheld`, which departs from the reference fix's scan. Its evidence, runner-up and flip condition are recorded above.
