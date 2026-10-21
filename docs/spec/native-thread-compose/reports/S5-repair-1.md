# S5 repair, iteration 1 of 8: native-thread-compose

- **Status:** DONE after the addendum (section 9). The iteration first returned BLOCKED on one test change: two frozen tests expected the pre-2.54 git wording for a failed reference-transaction hook. The orchestrator granted the change, and every gate, remote ones included, is green at code HEAD 3a21352b.
- **Branch:** `feat/native-thread-compose`, in the worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`.
- **PR:** draft https://github.com/cerredz/Vidbyte-SDK/pull/1186, stacked on `feat/native-grok-opencode-meta-hosts`.
- **History:** iteration start 0006acaf; code HEAD ca4f2bdd (pushed). The records commit, which touches only docs/spec, sits on top.
- **Frozen test tree:** `git diff 34fe19b7..HEAD --stat -- tests` is empty.
- **No pip.** Nothing was pip-installed: the wheel check unpacked the built wheel into a copied venv that already held the dependencies.

## 1. Gate matrix

Gates 1–9 were run in this worktree, in this iteration, at ca4f2bdd, after the last source commit. The final lines are quoted from the saved outputs under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s5-1/`, in `gate-*.txt` and `remote-*.txt`.

| # | Gate | Result | Final lines |
|---|---|---|---|
| 1 | `python lint/run.py` | PASS. The count table is byte-identical to the S4 table (`lint-table-s4.txt`). | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline` / `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| 2a | ruff I001 over `vidbyte` | PASS: 223, not risen | `Found 223 errors.` / [*] 223 fixable with the `--fix` option. |
| 2b | ruff TID251 over `pyproject.toml vidbyte` | PASS: exactly 5 | `Found 5 errors.` |
| 3a | `semgrep --test ...typed-mapping-boundary-policy` | PASS | `1/1: ✓ All tests passed` / `No tests for fixes found.` |
| 3b | `semgrep scan --error ... vidbyte` | PASS, exit 0 | `Ran 1 rule on 977 files: 0 findings.` |
| 4 | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` | PASS. At 0006acaf it was `22 failed, 277 passed`. | `...........  [100%]` / `299 passed in 54.67s` |
| 5 | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` | PASS | `......  [100%]` / `436 passed, 2 skipped in 41.49s` |
| 6 | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `tests\test_workflow_agent_forks.py ......  [100%]` / `================ 5940 passed, 16 skipped in 143.17s (0:02:23) =================` / `CI passed.` |
| 7 | `env -u PYTHONPATH python scripts/run_ci.py --stage package --dist-dir s5-1/dist-1` (a new empty folder) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| 8 | AC-21 wheel half: `s5-1/wheel-venv-1/Scripts/python.exe -I s3/check_wheel_prompts.py <worktree>`, run from `s5-1/wheel-run-1` | PASS | `placeholders equal COMPOSE_PROMPT_FIELDS: True []` / `fixed combinations: 17, longest planner = 8304 chars, over 12000: {}` / `forbidden texts in ported files: {}` / `AC-21 WHEEL HALF: PASS` |
| 9 | 72-column comment check | PASS | 18 changed `.py` files, 0 lines. Over the PR's 25 changed `vidbyte` `.py` files, the only long comment lines are 9 in `vidbyte/lib/errors/base.py`. All 9 already exist at the base 5c08c35e, and the PR adds none. |
| 10a | Remote: Static policy, run 39146595669 at ca4f2bdd | PASS | `Run Static policy (39146595669) has already completed with 'success'` |
| 10b | Remote: CI, run 39146593515 at ca4f2bdd | FAIL: both Source legs; Package skipped | `FAILED tests/features/harness_compose/test_harness_compose_concurrency.py::test_a_failed_worktree_add_stops_the_holding_sibling_before_its_error_propagates - AssertionError: git text 'aborted by hook' missin...` / `FAILED ...::test_two_failed_worktree_adds_propagate_one_error_after_both_cleanups_end - AssertionError: git text 'aborted by hook' missing from ...` / 3.12: `===== 2 failed, 5898 passed, 56 skipped, 19 warnings in 122.22s (0:02:02) ======` / 3.11: `============ 2 failed, 5898 passed, 56 skipped in 126.42s (0:02:06) ============` |

**Wheel check details.** The installed copy is `s5-1/wheel-venv-1`, a copy of the S3 package venv with its old `vidbyte` removed. The new wheel `s5-1/dist-1/vidbyte_sdk-0.3.0-py3-none-any.whl` was unpacked into it with `python -m zipfile -e`. The installed tree was checked against the checkout:
- `diff -rq` finds no difference except the folder READMEs, which are not packaged, and the long-unpackaged `vidbyte/prompts/skills`. That folder dates from PRs #185–#191 and is not in `[tool.setuptools.package-data]`, so it is unrelated to this PR.
- The installed `verdict_schema.md` is identical to HEAD's, R-23's sentence included.
- `vidbyte/lib/util/secret_text.py` is packaged.

## 2. Per finding: what was done, with evidence

All but one of the probes are the S4 reproducers: `PYTHONPATH="$(pwd);$S" python -m pytest -q -s -p no:cacheprovider -W ignore::pytest.PytestDeprecationWarning -p tests.features.harness_compose.conftest "$S/test_s4v_probes.py" -k <sel>`, with `S=<scratch>/s4-verifier`. The exception is R-14, which uses `s5-1/probe_locked_enter.py`. "Before" means 0006acaf (or its exported source in `s5-1/head-src`), and "after" means the fix commit. After every cancel probe, `procs.py --kill` reported `stand-in or grandchild processes: []`.

| ID | Commit | Root cause (one line) | Fix | Evidence |
|---|---|---|---|---|
| R-10 | a1d17451 | A second cancel, or an anyio scope that re-delivers its cancel every turn, broke the fan-out's wait, so a child's worktree cleanup was abandoned half-way. | `ComposeCalls.settle` waits until every task has ended through any number of cancels, then re-raises the first cancel object. `fan_out` cancels what still runs in a `finally` and settles all children. The planner and the selector run as one-child fan-outs. | The frozen red test `test_two_failed_worktree_adds_propagate_one_error_after_both_cleanups_end` turned green. Probes `double_cancel or anyio or two_failing or orphan_removal`: `7 passed`. Every line reads `worktrees=1 leftovers=0 pending=0 live_leaders=0 live_grandchildren=0`. `R-E1 anyio caught=True`, `TWO-ADDS at raise: worktrees=1 leftovers=[] pending=[]`, `SHUTDOWN pending at raise=[] -> after cancel: worktrees=1 leftovers=[] admin=[]`. |
| R-4 | a1d17451 | `ComposeGit.add_worktree` called `remove_worktree`, which called `_run`: a three-level chain (principle 1). | Split into `worktree_folder()`, `add_worktree(folder)` and `fill_worktree(folder, tree)`. `DisposableWorktree.__aenter__` removes a half-made worktree. The §9.2 argv is unchanged. | The git hygiene test that pins the argv passes (gate 4). A chain check over the 18 changed files found no three-level chain. |
| R-14 | a1d17451 | A cancel during `git worktree add` removed the folder while git still held the `initializing` lock, leaving a locked registration. | `DisposableWorktree._settled(git.add_worktree(folder))` waits out the started add, bounded by the 120 s git timeout of INV-30, before the removal. | Before: `admin entries (name, lock reason): [('vidbyte-compose-worktree-x62ocrxg', 'initializing')]`, plus `worktree list: ... locked initializing`. After, with 1 cancel and with 3 cancels: `admin entries ...: []`, `leftover folders in TMP: []`, and `pending tasks: []`. |
| R-8 | 7eda491a | Reader answers came only from the fan-out's return value. A `WORKTREE_FAILED` raised after the readers answered therefore carried a record with no verdicts or proposals (EC-16). | Each reader stores its answer in a positional `kept` list inside its worktree block. The except handler attaches `ThreadVerifiers._kept` / `ThreadEnsembles._kept`: every verdict or proposal once every reader has answered, otherwise the writer or plan alone. | Probe `ec16`, before: `EC16-1 ... verdicts=0 ... session-in-record=False`, `EC16-2 ... verdicts=0`, `EC16-P ... proposals=0`. After: `EC16-1 ... verdicts=1 ... session-in-record=True`, `EC16-2 ... verdicts=2`, sessions `{'v-fast': True, 'v-slow': True}`, and `EC16-P ... proposals=2`, sessions `{'p-grok': True, 'p-oc': True}`. |
| R-15 | 1d5d4d90 | `relocate`, `anchor` and `rung` rebuilt the step with `dataclasses.replace`, which re-ran every `ThreadStep` check. A skill folder that the writer deleted then raised a bare `ConfigurationError` after I/O. | `ThreadBinder._derived` copies the fields without re-validation, and each deriver checks only what it changes. | Probe `writer_deletes_reader_skill`, before: `R-E4 opencode verifier: RAISED ConfigurationError ... 'skills[0] must be an absolute path to an existing directory...'`. After: `R-E4 opencode verifier: RETURNED writer.ok=True failed_verifiers=(0,) error=FailureCode.CONFIGURATION_INVALID_ARGUMENT`, the same as the Grok verifier. |
| R-2 | 44475dcd | Validator floors were bare literals (A007 lesson). | Named floors beside their caps: `COMPOSE_MIN_VERIFIERS`, `COMPOSE_MIN_STAGES`, `STAGE_MIN_RETRIES`, `STAGE_MIN_RUNG` and `ENSEMBLE_MIN_PROPOSAL_NUMBER` (grant d). | A grep for literal floors in the validators is empty. Lint table unchanged. |
| R-7 | 361e0589 | Count rules were hand-rolled: `StepRoles.counted`, `COMPOSE_COUNT_RULE` and inline `if not x` checks. | `RecordFieldConverter.to_tuple(min_items=...)` (grant c), with `COMPOSE_MIN_CHAIN_OUTCOMES` and `COMPOSE_MIN_JSON_TURNS`. Each `WorkspaceDiff.files` name goes through `require_text`. | The BOUND_CASES and validation tests keep their `details["field"]` values (`EnsemblePlan.roles`, `EnsembleRound.kept`, `WorkspaceDiff.files`, `JsonAnswer.turns`, `EnsembleRoster.proposers`). Gate 4 is green. |
| R-3 | 4b153b94 | `require_text` quoted any value whose repr is 80 characters or fewer, so a key in a caller's prompt, template, schema or thread id reached the message. | `require_text(quote=False)` (grant c) at every caller-text site, and at each `WorkspaceDiff.files` name. The binders re-raise the record's model refusal with the model named by its type only, keeping `details["field"]`. That refusal is raised after the `except` block, so `__context__` and `__cause__` are both `None`. Base functions are unchanged (NG-1). | The 21 frozen keys cases turned green, and all 25 keys tests pass. Probe `key_in`, before: every compose line `key-in-message=True`. After: `key-in-message=False`, for example `prompt must match [^\x00]+; got a value of type str.` The base `run_opencode_thread` line still quotes, which is base behaviour (R-29; NG-1 leaves the base functions untouched). |
| R-9 | 77b85d53 | Prompt segments crossed modules as bare `(text, spliced)` tuples (principle 4). | A frozen, slotted `PromptSegment` record with only type checks (grant a), plus `ComposeTexts.fixed`. | Gate 4 green. I001 stayed at 223 after the two long imports were wrapped. |
| R-5 | b009653b | The longest-first key scrub was written twice (`ComposeFailures._replace` and the loop in `PromptFitter._scrub`). | `SecretText.replace_all` in the new `vidbyte/lib/util/secret_text.py`, re-exported from `vidbyte.lib.util` (grant b). hostkit's copy is untouched (INV-32). | The keys tests and the D-28 order (NUL removal, then the longest key first) pass in gate 4. |
| R-12 | 5202ec02 | A lone surrogate in a spliced value made the Grok and Muse steps raise `UnicodeEncodeError` with no record, and orphaned the opencode child. In caller text it slipped past the up-front check. | `_scrub` passes spliced text through UTF-16-LE with `surrogatepass` and back with `replace`: split halves are rejoined and a lone half becomes U+FFFD. `PromptFitter.check` refuses fixed text that holds a surrogate, through the leaf `_encodable` and `COMPOSE_UNENCODABLE_TEXT`. | Probe `lone_surrogate or caller_prompt`, before: Grok and Muse `UnicodeEncodeError has-record=False`, and the opencode child orphaned (process 25992, killed by the probe). After: all three `failed_step=None`, no orphan, and `CALLER-LONE` gives a `ConfigurationError` with `launches=0`. |
| R-13 | 9cbd47d6 | A template made only of placeholders sends a blank prompt when the spliced values are blank, so the step fails after I/O (INV-18, EC-37). | `PromptFitter.check` refuses a frame whose fixed text is blank (`COMPOSE_BLANK_PROMPT`), after `require_template`, before any I/O. | Probe `blank_previous`, before: `failed_step=1` with `CONFIGURATION_INVALID_ARGUMENT` for `'   '` and `'\x00\x00'`. After: the probe "fails" by design, because `chain_threads` now raises `ConfigurationError` up front. The refusal fields are `template` and `stages[1].template`. |
| R-1 | b5b73be2 | `COMPOSE_TRUNCATED_PROBLEM` ended with a sentence addressed to the model ("Answer again with a shorter JSON object."). | Only its first sentence is kept: "The answer was cut at the length limit, so it was not read." | Gate 4 green; the constant no longer holds a sentence addressed to the model (ledger 10). |
| R-6 | 337c45e6 | 24 comment lines in compose passed 72 columns. | Rewrapped with `s5-1/rewrap_r6.py` (textwrap, no broken words, `@intent` lines kept as they are). | Gate 9: 0 lines. |
| R-18 | 027dc75b | The headers of `verify.py` and `ensemble.py` said the backstop is skipped "only on a cancellation or a defect". | They now say "a cancellation, a defect or a compose failure, which goes on alone (INV-14)". | Matches INV-14 and R-C4's ruling. |
| R-19 | 3065184a | §17 recorded `JSON_KIND_NAMES` as a `ThreadStep` attribute. | spec.md (CRLF kept): it is "a module constant in `vidbyte/lib/util/json_text.py` beside `JSON_FENCE` and `JSON_FENCE_LANGUAGES`". | `reports/S3-implementer.md` is untouched, as instructed. |
| R-20 | 3b515e65 | `tried` in `stages.py` tripped the A007 analyser. | Renamed to `attempts`. | Lint table unchanged. |
| R-21 | c07700aa | `REPO_MAP.md:161` claimed the other steps "only read", which D-27 contradicts, and its "It" was ambiguous. | "The native folder also holds composites that chain, verify, hand off, stage and ensemble these thread calls; no two of their steps ever write to the workspace at the same time." (CRLF kept) | D-27 and INV-12. |
| R-22 | 6b09e92e (`_replace` part via b009653b) | Three header slips. | `compose/__init__.py` WHAT NOT TO DO item 2 now lists `DiffCapture`, `DisposableWorktree` and `JsonAnswers`. `DiffCapture.__aenter__` and `__aexit__` got step comments. The inventory slip about `_replace` disappeared with R-5's removal of it. | A001 unchanged. |
| R-23 | dca3f7b5 | The verdict schema never said that `findings` is capped. | `verdict_schema.md`: "The number of findings is limited, so list the most important problems first." | AC-21 wheel check: placeholders unchanged, and no fixed combination is over 12,000 characters (the longest, the planner's, is 8304). |

**"Gets right" re-check.** Every guard in review.md's list is pinned by gate 4 or gate 5, and both are green. Sibling cancellation still holds (the first EC-19 test), as do the Grok per-workspace serialization tests and the §9.2 argv hygiene test.

## 3. Remote CI failure and the test change proposed (BLOCKED)

**Evidence.** CI run 39146593515 at ca4f2bdd failed both source legs (Python 3.11 and 3.12, ubuntu-24.04 image 20261012.334, `git version 2.55.0`) on exactly these two tests:
- `tests/features/harness_compose/test_harness_compose_concurrency.py::test_a_failed_worktree_add_stops_the_holding_sibling_before_its_error_propagates`
- `tests/features/harness_compose/test_harness_compose_concurrency.py::test_two_failed_worktree_adds_propagate_one_error_after_both_cleanups_end`

Both fail in `check_compose_error` (`conftest.py:670`):

```
E   AssertionError: git text 'aborted by hook' missing from "Preparing worktree (detached HEAD da56015)\nfatal: in 'prepared' phase, update aborted by the reference-transaction hook"
```

The preceding hook assertions pass on the runner (`["cue"]`, and `["cue", "cue"]`), so the add failed on cue, as designed. The Package job was skipped because the source job failed. The package stage is green locally (gate 7).

**Root cause: git's wording changed in 2.54, and these tests pin the old wording.**
- `refs.c` at each tag (fetched with curl from raw.githubusercontent.com/git/git/<tag>/refs.c, saved in `s5-1/gitsrc/`):
  - v2.49.0, v2.50.0, v2.51.0, v2.52.0 and v2.53.0 have `die(_("ref updates aborted by hook"));`.
  - v2.54.0 and v2.55.0 have `static const char *abort_by_ref_transaction_hook = N_("in '%s' phase, update aborted by the reference-transaction hook");`.
- The local git is `git version 2.49.0.windows.1`, so the tests pass locally. The runner's git is 2.55.0, so they fail there.
- The module header itself records the old wording as a fact. Its KNOWN EDGE CASES say the hook "makes git print "ref updates aborted by hook"".
- Both tests arrived with 742db6bf (R-16, 10:12 -0400). The last green remote CI run was 39119540221, at ce8ad488, before that commit. The tests had therefore never run on the runner, and this iteration's dispatch is their first remote run.

**Why no source fix.** `ComposeFailures.error` carries git's stderr verbatim, after the key scrub, the redactor and the tail cap. INV-6 requires git's text in the message, and compose has no business rewriting git's wording. The failure is independent of this iteration's source. To show it, I loaded a scratch plugin, `s5-1/git254/s5_git254.py`, which makes compose's git children report the hook failure in the 2.54+ wording. The frozen tests, run in place, then fail exactly as on the runner:

```
PYTHONPATH="$(pwd);$G" python -m pytest -q -s -p no:cacheprovider -p s5_git254 tests/features/harness_compose/test_harness_compose_concurrency.py -k "failed_worktree_add_stops or two_failed_worktree_adds"
E   AssertionError: git text 'aborted by hook' missing from "Preparing worktree (detached HEAD 6abfc37)\nfatal: in 'prepared' phase, update aborted by the reference-transaction hook"
FAILED ...::test_a_failed_worktree_add_stops_the_holding_sibling_before_its_error_propagates
FAILED ...::test_two_failed_worktree_adds_propagate_one_error_after_both_cleanups_end
2 failed, 3 deselected in 1.11s
s5_git254: git messages rewritten: 3
  original git stderr: 'Preparing worktree (detached HEAD 6abfc37)\nfatal: ref updates aborted by hook\n'
```

**The proposed change.** It covers the two assertions, plus one header sentence so that A001 stays accurate. The file is `tests/features/harness_compose/test_harness_compose_concurrency.py`.

Before, at lines 225 and 266:
```python
    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by hook")
        check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by hook")
```
After:
```python
    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by")
        check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by")
```
Header, line 9, KNOWN EDGE CASES: change `makes git print "ref updates aborted by hook", exit 128` to `makes git print "ref updates aborted by hook" (git 2.53 and earlier) or "in 'prepared' phase, update aborted by the reference-transaction hook" (git 2.54 and later), exit 128`.

"aborted by" is the longest text that both wordings share, and it still proves that git's own text reaches the message in the INV-6 order: `check` also runs `find_in_order` with it. A scratch copy of the module with only the two assertion changes, `s5-1/git254/test_concurrency_git254.py`, was run with `-c pyproject.toml --rootdir <worktree> -p tests.features.harness_compose.conftest`:
- under the 2.54+ wording (`-p s5_git254`, 11 git messages rewritten): `5 passed in 21.67s`;
- under the local 2.49 wording: `5 passed in 24.12s`;
- `procs.py --kill` afterwards: `stand-in or grandchild processes: []`.

**What the tests pin.** EC-19, INV-14 and EC-17: one exception propagates only after the siblings are cancelled and their worktrees removed. They reach this through the real hook seam of EC-59/T-6. The `git_text` check pins INV-6, git's text in the `ThreadComposeError` packet (§8.5, §12.3 row 9). The change keeps every one of these.

**Caveat.** On Linux, each test stops at this assertion, so the lines after it have not yet run on the runner. Once the change is approved, a CI dispatch is what proves them. Locally, under both wordings, they pass.

## 4. Findings I believe are wrong

None.

## 5. Grants used, and the spec edits made

- **Grant (a), R-9:** `PromptSegment` in `vidbyte/lib/dataclasses/native_compose.py`, type checks only.
- **Grant (b), R-5:** `SecretText` in `vidbyte/lib/util/secret_text.py`, re-exported from `vidbyte.lib.util`. hostkit is untouched.
- **Grant (c):** `min_items` on `RecordFieldConverter.to_tuple` (R-7) and `quote` on `RecordFieldValidator.require_text` (R-3). Both are keywords whose defaults keep the old behaviour.
- **Grant (d), R-2:** the named floors, plus R-7's `COMPOSE_MIN_CHAIN_OUTCOMES` and `COMPOSE_MIN_JSON_TURNS`.
- **The grant conditions hold.**
  - `vidbyte.harnesses.native.__all__` and the 42 names of `compose.__all__` are unchanged.
  - No base function's behaviour changed.
  - No dependency was added.
  - `vidbyte/lib/process/` and hostkit were not edited.
- **Spec edits made** (spec.md, at byte level with CRLF kept):
  - the §17 entry "S5 repair 1: approved grants", with one sub-bullet per grant;
  - the §8.4 counts: 41 files, 19 Python modules, 6 lib modules, 51 classes in 19 modules, 10 lib exports, and the grant (c) sentence;
  - the R-19 correction.

## 6. Spec passages these fixes made stale (need an orchestrator ruling; not in my allowed edits)

| Where in spec.md | Says now | Should say after this iteration |
|---|---|---|
| D-17 (line 666) | Fan-out uses tasks with `asyncio.gather`, plus explicit cancellation of siblings | `asyncio.wait(FIRST_EXCEPTION)`, then cancel what still runs, then `ComposeCalls.settle`. No gather. |
| §8.2 (line 689) | Fan-out with `gather(return_exceptions=True)`, after the precedent at `aggregation.py:89` | No gather precedent applies. `settle` waits with `asyncio.wait` through repeated cancels. |
| §17 Fan-out (line 1576) | `asyncio.wait(FIRST_EXCEPTION)` and then `gather(return_exceptions=True)` | The same as D-17, with the planner and the selector as one-child fan-outs |
| §17 The record so far (lines 1583–1586) | Several readers give the record from before their stage | Every verdict or proposal once every reader has answered; otherwise the writer or plan alone (EC-16, R-8) |
| §17 Rendering (line 1562) | `(text, spliced)` segments | `PromptSegment` records |
| §17 Plumbing helpers beyond §8.5 (lines 1563–1565) | Lists `StepRoles.counted` | Remove it. Add `ComposeCalls.settle`, `ComposeTexts.fixed`, `ComposeGit.worktree_folder` and `fill_worktree`, `DisposableWorktree._settled`, `ThreadBinder._derived` and `_withheld`, `PromptFitter._encodable`, and `ThreadVerifiers._kept` and `ThreadEnsembles._kept`. |
| §8.5 (line 908) and §12.3 row 14 (line 1300) | `ComposeGit`: ... `add_worktree` ... | `worktree_folder`, `add_worktree(folder) -> None` and `fill_worktree(folder, tree)` |
| §12.3 table and the sentence under it (line 1316) | 5 lib modules, 40 new files | A row for `vidbyte/lib/util/secret_text.py` (grant b); 6 lib modules, 41 files, matching §8.4 |
| EC-17 (line 524), optional | "The removal runs as a shielded task" | "a settled task". The behaviour is the same; the word "shielded" can be misread as `asyncio.shield`. |

## 7. Open items and what I would try next

1. **Remote CI: two frozen tests pin git's pre-2.54 wording (section 3).** Resolved: the orchestrator granted the change, and section 9 records it.
   - After approval, the change is three lines in one test file.
   - Then push and dispatch `ci.yml`, and watch the lines after the assertion run on Linux for the first time.
   - If anything else fails there, reproduce it locally with `-p s5_git254`, which keeps the new wording, before changing source.
2. **R-24 to R-31** remain follow-ups, outside this loop.
3. **The spec rulings in section 6.**

## 8. Niche facts for the next agent

- **The runner's git is 2.55.0; the local git is 2.49.0.windows.1.** Their hook-abort wordings differ. `s5-1/git254/s5_git254.py`, loaded with `-p s5_git254`, gives the runner's wording locally.
- **`gh run watch <id> --exit-status`** must have its exit code captured before any pipe. `| tail` hides the failure: the watch task in this iteration "succeeded" while it printed `ci watch exit 1`.
- **S061** flags any call named `copy`, `copy2`, `copyfile` or `move`, including `copy.copy`. **S054** wraps ruff S105, which treats a name containing pass, pwd, token or secret as a hardcoded password. Rename the constant; do not suppress.
- **CRLF working files.** `review.md`, `spec.md` and `REPO_MAP.md` are CRLF in the working tree; edit them at byte level and keep CRLF. The `.py` files are LF.
- **Heredocs.** In this Bash tool, a heredoc whose body holds backslashes and apostrophes can fail with "unexpected EOF while looking for matching `''". Write such files with the file tool.
- **Wheel check without pip:** run `python -m zipfile -e <wheel> s5-1/wheel-venv-1/Lib/site-packages` after removing the old `vidbyte` and its dist-info. Then run the check with that venv's `python.exe -I`, from a folder outside the checkout.
- **The S4 probe `blank_previous`** now "fails" on purpose: R-13 refuses the template before any I/O.
- **After any cancel probe,** run `python <scratch>/s4-verifier/procs.py --kill`. Every probe in this iteration left nothing behind.

## 9. Addendum: the granted test change

**The grant** (orchestrator, quoted as received): "GRANT (orchestrator, test change): In tests/features/harness_compose/test_harness_compose_concurrency.py, change `git_text="aborted by hook"` to `git_text="aborted by"` at the two call sites (:225 and :266), and update the header's KNOWN EDGE CASES entry (line 9) to name both git wordings. Git 2.53 and earlier print "ref updates aborted by hook". Git 2.54 and later print "in 'prepared' phase, update aborted by the reference-transaction hook". Change nothing else in the test tree. Reason: the spec requires the error to carry git's own text, not one git version's wording (INV-6, EC-19, EC-59/T-6). The hard-coded phrase makes a spec-conforming implementation fail on the CI runner's git 2.55.0 (run 39146593515). I checked this myself against the run log, which shows `fatal: in 'prepared' phase, update aborted by the reference-transaction hook`, and against local git 2.49.0."

The orchestrator also ruled that the stale spec passages in section 6 go to the spec author, so this iteration leaves them untouched.

**The commit.** 3a21352b, `test(compose): accept both git wordings of a hook-aborted worktree add [gate:ci]`, on top of the orchestrator's 16e7a07d (pipeline.md). It is the only test-tree change since 34fe19b7: `tests/features/harness_compose/test_harness_compose_concurrency.py | 6 +++---`.

Lines 225 and 266, before:
```python
    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by hook")
        check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by hook")
```
After:
```python
    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by")
        check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by")
```

Header, line 9 (KNOWN EDGE CASES); only this sentence changed. Before:
> A reference-transaction hook that exits 1 when the add's transaction is prepared makes git print "ref updates aborted by hook", exit 128 and remove the new folder and its registration itself; worktree remove runs no such hook.

After:
> A reference-transaction hook that exits 1 when the add's transaction is prepared makes git print "ref updates aborted by hook" (git 2.53 and earlier) or "in 'prepared' phase, update aborted by the reference-transaction hook" (git 2.54 and later), exit 128 and remove the new folder and its registration itself; worktree remove runs no such hook.

No `#` comment line was edited. The comment-width check on the file gives 0 lines.

**Local verification at 3a21352b:**

| Check | Final lines |
|---|---|
| The two tests, local git 2.49 wording | `2 passed, 3 deselected in 3.84s` |
| The two tests, 2.54+ wording (`-p s5_git254`) | `2 passed, 3 deselected in 3.62s` / `s5_git254: git messages rewritten: 11` |
| `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` | `299 passed in 54.82s` |
| `python lint/run.py` | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` (count table identical to S4's) |
| `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | `tests\test_workflow_agent_forks.py ......  [100%]` / `================ 5940 passed, 16 skipped in 137.70s (0:02:17) =================` / `CI passed.` |
| `git diff 34fe19b7..HEAD --stat -- tests` | `tests/features/harness_compose/test_harness_compose_concurrency.py \| 6 +++---` (only the granted lines) |
| `procs.py --kill` | `stand-in or grandchild processes: []` |

The other gates were not re-run: the ratchet counts, semgrep, the base pack, the package stage and the AC-21 wheel check. They read nothing that changed after ca4f2bdd, where they passed (`git diff --stat ca4f2bdd..HEAD -- vidbyte pyproject.toml scripts lint .semgrep .github` is empty).

**Remote at 3a21352b.** Each watch's exit code was captured before any pipe.

| Run | Result | Final lines |
|---|---|---|
| CI 39148626228 | success: Source / Python 3.12, Source / Python 3.11 and Package; watch exit 0 | 3.12: `========== 5900 passed, 56 skipped, 19 warnings in 129.76s (0:02:09) ===========` / `CI passed.`<br>3.11: `================= 5900 passed, 56 skipped in 127.35s (0:02:07) =================` / `CI passed.`<br>Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.`<br>`✓ feat/native-thread-compose CI cerredz/Vidbyte-SDK#1186 · 39148626228` |
| Static policy 39148628122 | success; watch exit 0 | `1/1: ✓ All tests passed` / `Ran 1 rule on 977 files: 0 findings.` / `✓ Static policy in 25s (ID 117737539967)` |

The runner still has git 2.55.0. Section 3's caveat is now closed: both EC-19 tests ran to their end on Linux and passed, the lines after the old assertion included (5900 passed, 0 failed, against 5898 and 2 in run 39146593515). The remote-only real-bash flake did not occur, so no rerun was needed.

**Final state.** Every gate is green at code HEAD 3a21352b, and no confirmed finding is open. The follow-ups R-24 to R-31 stay outside this loop. The stale spec passages belong to the spec author, and are untouched here.
