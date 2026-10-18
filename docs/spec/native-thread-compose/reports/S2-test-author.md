# S2 test author report: native-thread-compose

| | |
|---|---|
| Stage | S2 test author |
| Spec | `docs/spec/native-thread-compose/spec.md` r3, approved, base_commit `5c08c35e` |
| Branch | `feat/native-thread-compose`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose` |
| Commits | `2ec1ce7c` test(harnesses): add failing tests for native-thread-compose [AC-1..AC-22] · `90eec511` docs(spec): record test proof for native-thread-compose · this report in the commit after them |
| Status | DONE |

## 1. Result

- The pack `tests/features/harness_compose/` has 15 test files, 76 test functions and 276 collected cases. Before the feature exists, every case errors at setup with `ModuleNotFoundError: No module named 'vidbyte.harnesses.native.compose'`, and no case fails for any other reason.
- `docs/spec/native-thread-compose/test-plan.md` maps every AC, INV, EC, T and NFR of the spec to a test, or to the "Tests deliberately NOT written" table with a reason. A script checked that all 76 test functions are named in the plan and that every test name the plan and the Proof column use exists.
- The Proof column of spec §6.2 is filled for all 23 ACs. Nothing else in the spec changed: 23 lines changed, and the script that filled them checked that each change only fills the empty last cell.
- The base pack still passes unmodified (`436 passed, 2 skipped`), and lint ends `SDK-LINT: PASS` with no baseline touched.
- The test most likely to catch a real bug is `test_harness_compose_git.py::test_every_git_child_is_the_spec_command_in_the_spec_place_with_a_clean_environment`. It sorts every git child that compose starts into the eleven command kinds of §9.2 and requires all eleven to occur. For each child it checks the exact argv prefix, the working folder, an environment overlay of `GIT_INDEX_FILE` only, and the absence of a caret, caller text or a key. It also requires the tree ids to equal those of the test's own git oracle. A first implementation is likely to get at least one of these details wrong.

## 2. Failure inventory

**Method.** I worked from the raw spec, not from a summary:

- §6.1: 36 invariants;
- §6.2: 23 ACs;
- §6.3: 78 edge cases;
- §7: 11 NFRs;
- §10: 8 threats;
- §13: the test seams.

I also used `request.md` §C, and the base pack `tests/features/harness_threads/` as prior art. For each ID I wrote the failure as "input + state → wrong output". Then I chose the cheapest level that can observe it through seams the repository already uses: the base stand-in run from its path, the real git, the real file system, and `vidbyte.lib.process.CliRunner`. Expected values come from independent oracles, never from compose's own output:

- the test's own git, with a temporary index outside the repository;
- prompts rendered straight from the prompt files;
- command-line units counted by hand.

**What the inventory became.** Counts come from grepping the spec and the test modules.

| Family | In the spec | Named in a test module | Where the rest are accounted for |
|---|---|---|---|
| AC | 23 | 22 | AC-23 is the gate: lint, both `scripts/run_ci.py` stages and semgrep. The installed-wheel half of AC-21 is left to S3/S5 |
| INV | 36 | 34 | INV-34 and INV-35 are proven by running the base pack unmodified. The INV-28 test also shows that a direct call starts no git |
| EC | 78 | 56 | EC-69 is exercised by the ten-proposer test, which uses one fork step for all ten proposers. EC-9, EC-16, EC-19, EC-55, EC-56, EC-57, EC-60, EC-66 and EC-72 are not written, with reasons. EC-8, EC-11 to EC-15, EC-21, EC-38, EC-61, EC-67, EC-68 and EC-75 are accepted limitations with no control in this PR |
| T | 8 | 5 | T-2: its controls are tested, and the residual is accepted. T-4: not applicable, because there is no other tenant. T-7: inherited; the INV-9 tests check where worktrees go |
| NFR | 11 | 3 | NFR-2, NFR-5, NFR-6 and NFR-7 are proven by tests the plan names. NFR-1, NFR-4, NFR-9 and NFR-10 are gate checks |

**The owner's own failure list** (`request.md` §C, acceptance item 6, verbatim: "a failing step mid-chain, a verifier that tries to write, a truncated answer feeding a parser, cancellation mid-gather, a Grok fan-out in one workspace, and a stage that exhausts its retries"):

| Owner's item | Test |
|---|---|
| a failing step mid-chain | `test_harness_compose_chain.py::test_failed_middle_step_ends_the_chain_with_the_functions_own_error` (AC-7) |
| a verifier that tries to write | `test_harness_compose_verify.py::test_grok_reader_that_writes_raises_reader_changed_after_every_verifier` (AC-8a), `test_harness_compose_verify.py::test_worktree_readers_that_write_leave_the_workspace_untouched` (AC-8b), `test_harness_compose_ensemble.py::test_single_proposer_that_writes_stops_the_ensemble_before_the_implementer` (AC-8c) |
| a truncated answer feeding a parser | `test_harness_compose_answers.py::test_cut_verdicts_are_repaired_on_the_same_thread_and_never_graded` (AC-9), `test_harness_compose_answers.py::test_parse_json_answer_never_passes_a_cut_answer_to_parse` |
| cancellation mid-gather | `test_harness_compose_concurrency.py::test_cancelling_a_verify_stops_both_trees_removes_the_worktree_and_frees_the_lock` (AC-10) |
| a Grok fan-out in one workspace | `test_harness_compose_concurrency.py::test_grok_verifiers_on_one_workspace_take_turns_while_opencode_runs_beside_them`, `test_harness_compose_concurrency.py::test_composites_serialize_grok_per_workspace_and_overlap_across_repositories` (AC-11) |
| a stage that exhausts its retries | `test_harness_compose_stages.py::test_failed_attempts_follow_the_decision_table` (AC-12) |

The owner's five usage bullets map to the AC-2, AC-3, AC-4, AC-5 and AC-6 tests. AC-1 runs the §4 snippet itself.

## 3. Selection and pruning

| File | Cases | Functions |
|---|---|---|
| `test_harness_compose_acceptance.py` | 1 | 1 |
| `test_harness_compose_answers.py` | 49 | 7 |
| `test_harness_compose_binding.py` | 23 | 8 |
| `test_harness_compose_chain.py` | 4 | 4 |
| `test_harness_compose_concurrency.py` | 3 | 3 |
| `test_harness_compose_ensemble.py` | 5 | 5 |
| `test_harness_compose_git.py` | 16 | 7 |
| `test_harness_compose_handoff.py` | 2 | 2 |
| `test_harness_compose_keys.py` | 4 | 4 |
| `test_harness_compose_prompts.py` | 58 | 7 |
| `test_harness_compose_stages.py` | 6 | 3 |
| `test_harness_compose_surface.py` | 29 | 12 |
| `test_harness_compose_validation.py` | 66 | 3 |
| `test_harness_compose_verify.py` | 5 | 5 |
| `test_harness_compose_workspace.py` | 5 | 5 |
| **Total** | **276** | **76** |

(`pytest --collect-only` reports `276 tests collected`.)

**Why more than 25.** Most of the parametrized cases are rows of tables that the spec itself makes the contract:

- 58 invalid inputs (AC-14);
- 22 prompt files, each loaded and checked for placeholders;
- 10 ported prompts checked for forbidden texts;
- 25 record bounds (NFR-8), each built at the bound and refused past it;
- 16 `JsonText` refusals and 4 acceptances;
- 7 command-line unit counts (INV-36);
- 10 function signatures and 9 alias signatures.

The behavioural tests are one per AC, plus one each for the invariants and edge cases that no AC reaches. Examples are git hygiene, hostile diff drivers, the nested repository, unborn `HEAD`, fair sharing of the selector's room, and quote-dense answers.

**Pruned.** The plan's "Tests deliberately NOT written" table gives the full reasons. In short:

- EC-16 (a worktree that cannot be removed) is a flake and cleanup risk on CI.
- EC-19 (a defect in exactly one fan-out child) cannot be produced through a real seam without mocking compose.
- The EC-54 behaviour cannot be reached by a valid stage, so it is pinned as table data.
- The behaviour of the T-6 hook and `core.safecrlf=true` depends on the git version; the argv prefix is pinned instead.
- The EC-4 timeout after a step cannot be aimed at one git call.
- EC-60 needs another OS user.
- EC-72 needs a stand-in that runs git.
- EC-55 and EC-56 need WSL or a UNC temporary folder.
- EC-57 is limited by the stand-in's state folder (spec §13 fact 5).
- EC-9 and EC-66 are time budgets.
- The AC-21 wheel install, AC-23 and NFR-1/4/9/10 are gates.
- The second bullet of INV-36 is a diff property, checked in review.
- The variant of EC-69 with a writer and a verifier is covered by the frozen record.
- Q-1 to Q-11 were not requested.

**Proof that the tests are not vacuous.** These checks were throwaway runs; the files were deleted and never staged.

- *Git assumptions.* Five checks ran against the pack's own fixtures:
  - the hostile-driver control runs both drivers;
  - `add -A` with a nested `.git` that has no commit exits 128;
  - `worktree add` in an unborn repository exits 128;
  - the oracle's diff under `core.autocrlf=true` holds no carriage return;
  - an empty folder is in no snapshot.

  Last lines (long lines cut):

```text
SECOND 0 b''
.ADD 128 b"error: 'nested/' does not have a commit checked out\nfatal: adding files failed\n"
.WT 128 b'hint: If you meant to create a worktree containing a new unborn branch\nhint: (branch with no commits) for this repository, you can do so\nhint: using the --orp …[cut]
.'diff --git a/README.md b/README.md\nindex a2b3fdf..46cb21b 100644\n--- a/README.md\n+++ b/README.md\n@@ -1,3 +1,4 @@\n # Demo\n line two\n EARLIER-EDIT\n+WRITER-LINE\nd …[cut]
..
5 passed in 1.24s
```

- *The stand-in returns a whole 100,000-character Grok reply* through `replies`. This printed the elapsed time, the length and `text_truncated`:

```text
ELAPSED 0.083 100000 False
.
1 passed in 0.90s
```

- *Quote-dense prompts (EC-36).* The opencode stand-in returns 100,000 double quotes whole. On win32 the base accepts a Grok prompt of 29,820 command-line units, and refuses the same prompt with 200 more quotes (30,220 units):

```text
UNITS 29820 CHARS 14918
REFUSED NativeThreadError run_grok_thread failed with configuration.invalid_argument. The SDK refused an argument before starting Grok Build. The argument prompt was refused: prompt must
.
1 passed in 1.12s
```

- *The INV-36 test against right and wrong counters.* Each list names the cases that fail. The correct counter fails none. A characters-only counter fails 5 of the 7 cases, and an unquoted UTF-16 counter fails 4:

```text
correct: []
chars: ['empty argument becomes two quotes', 'space wraps the argument in quotes', 'tab wraps the argument in quotes', 'each quote is escaped inside the wrapping quotes', 'one astral character is two units']
unquoted utf16: ['empty argument becomes two quotes', 'space wraps the argument in quotes', 'tab wraps the argument in quotes', 'each quote is escaped inside the wrapping quotes']
```

- *The fixtures against the real base functions.* Before any compose test existed, six throwaway tests checked the pack's fixtures against the real base functions:
  - the new stand-in fields (`answers`, `replies`, `observe_files`, `write_files`);
  - a long reply under a lowered cap;
  - the git oracle helpers;
  - the `marker` program and the `PATH` stand-in;
  - a base function launched through the `PATH` stand-in;
  - hold, release and `alive`.

  The `muse calls` line lists the scenario label of each launch that the `CliRunner` spy recorded:

```text
muse calls ['g', 'g', 'r', 'r', 'r', 'o', 'o', 'm', 'm', 'm']
......
6 passed in 4.25s
```

- *AC-1 runs the §4 snippet verbatim.* The `SNIPPET` constant was compared with the one python block of spec §4 (r3). The output was `python blocks in §4: 1`; the console showed the section sign as a replacement character. Then it printed `identical: True chars: 1565`.

## 4. Red run (exact output)

Bootstrap: none. `python` is CPython 3.11.0 at `C:/Users/422mi/AppData/Local/Programs/Python/Python311/python.exe`, the same interpreter as `py -3.11`, with pytest 8.3.5 and pytest-asyncio 1.3.0 already installed. There was no `pip install`, no network, no real vendor CLI and no real key. Every run was made from the worktree root on HEAD `36fc0308`, with the pack staged and `vidbyte/harnesses/native/compose/` absent. The test commit `2ec1ce7c` holds exactly those staged files plus the plan.

`PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` → exit 1, last lines:

```text
ERROR tests/features/harness_compose/test_harness_compose_workspace.py::test_capture_diff_is_none_after_a_raising_block_whose_error_propagates
ERROR tests/features/harness_compose/test_harness_compose_workspace.py::test_in_worktree_holds_the_working_content_isolates_writes_and_always_goes_away
ERROR tests/features/harness_compose/test_harness_compose_workspace.py::test_in_worktree_creates_an_empty_workspace_folder_no_snapshot_holds
ERROR tests/features/harness_compose/test_harness_compose_workspace.py::test_repository_with_no_commit_refuses_in_worktree_but_captures_diffs
276 errors in 9.47s
```

The same command with `--tb=line`, piped through `grep -E "^E " | sort | uniq -c`, gives one reason for every case:

```text
    276 E   ModuleNotFoundError: No module named 'vidbyte.harnesses.native.compose'
276 errors in 2.10s
```

`PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/<file>.py`, one run per file:

| File | Final line | Exit | Errors caused by the missing module (`--tb=line`) |
|---|---|---|---|
| `test_harness_compose_acceptance.py` | `1 error in 1.20s` | 1 | 1 of 1 |
| `test_harness_compose_answers.py` | `49 errors in 2.32s` | 1 | 49 of 49 |
| `test_harness_compose_binding.py` | `23 errors in 1.60s` | 1 | 23 of 23 |
| `test_harness_compose_chain.py` | `4 errors in 1.10s` | 1 | 4 of 4 |
| `test_harness_compose_concurrency.py` | `3 errors in 1.13s` | 1 | 3 of 3 |
| `test_harness_compose_ensemble.py` | `5 errors in 1.23s` | 1 | 5 of 5 |
| `test_harness_compose_git.py` | `16 errors in 1.44s` | 1 | 16 of 16 |
| `test_harness_compose_handoff.py` | `2 errors in 1.08s` | 1 | 2 of 2 |
| `test_harness_compose_keys.py` | `4 errors in 1.08s` | 1 | 4 of 4 |
| `test_harness_compose_prompts.py` | `58 errors in 2.38s` | 1 | 58 of 58 |
| `test_harness_compose_stages.py` | `6 errors in 1.22s` | 1 | 6 of 6 |
| `test_harness_compose_surface.py` | `29 errors in 1.93s` | 1 | 29 of 29 |
| `test_harness_compose_validation.py` | `66 errors in 2.89s` | 1 | 66 of 66 |
| `test_harness_compose_verify.py` | `5 errors in 1.20s` | 1 | 5 of 5 |
| `test_harness_compose_workspace.py` | `5 errors in 1.21s` | 1 | 5 of 5 |

The reason is the right one. The `compose_api` fixture imports `vidbyte.harnesses.native.compose` before anything else, so each case stops at the first missing name of the spec. Once that import works, each test checks behaviour against its oracles. No case can pass vacuously before the feature exists.

## 5. Green guards

Base pack, unmodified, run with the extended stand-in. `-rs` only adds the skip reasons: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads -rs` → exit 0, last lines:

```text
......                                                                   [100%]
=========================== short test summary info ===========================
SKIPPED [1] tests\features\harness_threads\test_harness_threads_launcher.py:100: Muse is looked up on PATH only outside win32 (EC-29)
SKIPPED [1] tests\features\harness_threads\test_harness_threads_runner.py:245: the execute permission bit exists only on POSIX
436 passed, 2 skipped in 47.53s
```

These are all 438 base tests. The two skips are platform skips in base tests this pack does not touch. The exact command without `-rs`, run again on the committed test and spec-proof commits (HEAD `90eec511`) → exit 0, last lines:

```text
...................................................................s.... [ 65%]
........................................................................ [ 82%]
.............................s.......................................... [ 98%]
......                                                                   [100%]
436 passed, 2 skipped in 55.08s
```

Lint: `python lint/run.py` → exit 0. It was run before each commit: with the plan staged, with the spec staged, and with this report staged. Every run printed the same text. Last lines:

```text
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

No baseline was touched. The `IMPROVED` notices that lint prints were already there before this pack, for example `S063 IMPROVED 4 -> 3`.

## 6. Fixtures added or extended

- **`tests/features/harness_threads/fake_harness.py`** (+85, −7 lines; standard library only). New optional scenario fields, all read with `.get` or a membership test, so every existing scenario behaves as before:
  - `label` names a launch in its start record.
  - `answers` holds per-launch overrides, claimed with an exclusive-create turn counter in the state folder. The last entry repeats.
  - `replies` holds prompt-matched overrides (`exact` or `contains`). The first match wins, and its index is logged.
  - `observe_files` makes the stand-in log the SHA-256 of each named file in its working folder.
  - `write_files` makes the stand-in write UTF-8 files into its working folder, as a vendor CLI editing its workspace would.
  - The new program `marker` leaves a marker file and exits. It is the planted `diff.external`/textconv driver for T-6.

  The stand-in still never logs the API key it receives in its environment. It logs only file digests and the names of the files a scenario told it to write. The AC-15 tests set those names to placeholder keys on purpose. The base pack result in section 5 is the proof that existing behaviour is unchanged.
- **`tests/features/harness_threads/README.md`** (+2, −1): notes that the compose pack runs the stand-in, and adds a dated line for the new fields.
- **`tests/features/harness_compose/conftest.py`** (new, 730 lines):
  - `compose_api`: the spec's names, imported lazily, compose first.
  - `sandbox`: the user home and the temporary folder inside the sandbox, with `tempfile.tempdir` patched. `PATH` holds only the stand-ins and the real git. It sets `GIT_CONFIG_NOSYSTEM`, an empty `GIT_CONFIG_GLOBAL` and `GIT_CEILING_DIRECTORIES`. It removes the vendor credential variables `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY`, `META_API_KEY`, `DEEPSEEK_API_KEY`, `ZAI_API_KEY`, `ZHIPU_API_KEY` and `OPENCODE_CONFIG_CONTENT`. It also provides `make_repo`, the `tree_of`/`tree_diff` git oracle, launch readers and the leftovers count.
  - `runs`: a spy on `vidbyte.lib.process.CliRunner.run` that records each invocation and its enter and exit order.
  - `steps`: binds steps whose configs point at their own stand-in scenarios.
  - `check_compose_error`: the INV-6 message order and the verbatim `likely_cause`/`next_step`.
  - `fast_stop`, `wait_until` and `alive`, in the base pack's shape.
  - `pack`: constants and helpers, including `fresh_key`, `fragments`, `leaks`, `command_line_units`, `render` and the JSON answer builders.

  Keys are generated placeholders. `fresh_key` cuts its label to six characters, so every 12-character fragment holds random hex.
- **`tests/features/harness_compose/FEATURE.md`** and **`README.md`**: the pack's invariants, suite map, known failure modes and omitted strategies, and its file index.

## 7. Spec defects and interpretations (open items)

1. **Defect: D-5 and §12.3 row 12 prescribe `asyncio.Lock`, which lint bans.** `lint/ruff.toml` line 8 reads `"asyncio.Lock" = { msg = "Use the SDK-owned concurrency boundary." }` (TID251). `python lint/run.py --rule S039 --all` reports `S039 RATCHETED: 5 finding(s), allowance 5.`, for `vidbyte/harnesses/stores/memory.py:41`, `vidbyte/middleware/builtins/circuit_breaker.py:63` and `vidbyte/tools/mcp/transport.py:139`, `:140` and `:144`. A sixth `asyncio.Lock` fails `SDK-LINT`, and AC-23 forbids raising the baseline. The repository already serializes with `asyncio.Semaphore(1)`: `vidbyte/agents/codex/agent.py:86` uses `asyncio.Semaphore(CODEX_MAX_CONCURRENT_TURNS)`, where `vidbyte/lib/constants/codex.py:226` sets `CODEX_MAX_CONCURRENT_TURNS = 1`. The tests check only behaviour: no overlap within a workspace, overlap across workspaces, and the lock is free after a cancel. Either primitive passes them. The spec owner should confirm the primitive.
2. **Interpretations the tests encode.** The spec allows these readings, and the plan's "Notes for the implementer" lists them:
   - The truncation note's omitted count is measured after NUL removal.
   - A cut diff is `text[:cap]`, and a cut file list is `files[:cap]`.
   - `WorkspaceDiff.text` is git's raw output for the §9.2 command.
   - The problem constants follow their names. An extra member's problem names the member.
   - An unanchored fork passed as `to_step` is refused naming `to_step`.
   - Every git child's overlay is a subset of `{GIT_INDEX_FILE}`, and `rev-parse` runs in the workspace.
   - `likely_cause` and `next_step` equal their constants verbatim.
   - `findings` and `kept` are tuples.
   - A `JsonText` problem contains `str()` of its `ValueError`.
   - The selection runs before the ensemble's backstop, and no snapshot follows the implementer.
   - The refusal of "exactly one of result/error" may name either field.
   - Slack: AC-19 allows 100 characters; the fair-share and quote-dense tests allow 200 characters or units.
   - The INV-36 message is the current text, verbatim.
3. **AC-13(a) "in the same folder".** The git-free half is proven in folders outside any repository, by the AC-7, AC-4 and AC-5 tests. It is not proven in the very folder the five refusal calls use. Both are folders under the sandbox root, with `GIT_CEILING_DIRECTORIES` set.
4. **Not run at S2:**
   - `python scripts/run_ci.py` was not run, because its source stage runs every test and this pack is red by design (276 errors). The gate belongs to S3/S5, as does semgrep.
   - The green run time of the pack is unmeasured until compose exists. The estimate is well under 3 minutes: the base pack, which launches the same stand-in, runs 438 cases in about 47 seconds.

## 8. Notes for S3

- **Run command:** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose`. Do not export `PYTHONPATH` before `scripts/run_ci.py`.
- **Imports the tests need:**
  - `vidbyte.harnesses.native.compose`;
  - `vidbyte.lib.dataclasses.native_compose` and `native_ensemble`;
  - `vidbyte.lib.enums.native_compose`;
  - `vidbyte.lib.constants.native_compose`;
  - `vidbyte.lib.util.json_text.JsonText`;
  - `vidbyte.lib.errors.ThreadComposeError`;
  - `vidbyte.lib.dataclasses.validation.RecordFieldValidator.command_line_units`.
- **Seams:** every git child must go through `vidbyte.lib.process.CliRunner.run`, which the `runs` spy patches on the class. Read `COMPOSE_DIFF_MAX_CHARS`, `COMPOSE_DIFF_MAX_FILES` and `NATIVE_RESULT_TEXT_MAX_CHARS` as module attributes at call time, because the tests lower them with `monkeypatch.setattr`. Worktree and index folders go in `tempfile.gettempdir()`, with the `COMPOSE_WORKTREE_PREFIX` and `COMPOSE_INDEX_PREFIX` prefixes, and the index file is named `index`.
- **Do not change** the stand-in's existing behaviour, the base pack, or any assertion in this pack. Raise a test you think is wrong against the spec first.

## 9. Process notes

- API rate limits and context limits interrupted the stage several times. The work stayed staged through every interruption, and no `git reset`, `git checkout -- <path>`, `git stash` or `git clean` was used.
- The throwaway self-check files (`tests/features/harness_compose/test_zz_selfcheck_tmp.py`) were created in the pack folder so that they could use its fixtures. They were deleted after each run and never staged.
- Files written outside the test tree: `test-plan.md`, the §6.2 Proof column and this report. Nothing under `vidbyte/`, `lint/`, `scripts/`, `.github/` or `pyproject.toml` was touched.

## 10. Addendum: S4 rows R-11, R-16 and R-17 (2026-10-18)

The S4 review (`review.md`) sent three test-pack rows back to S2. They were fixed on top of `23d48569`, still blind to the implementation. S3's code (`e1bf20d8`) and every existing assertion were left unchanged.

| Row | Commit | Change |
|---|---|---|
| R-11 | `4d3ee613` | The 22 comment lines past 72 columns were refilled. The awk check prints nothing for any pack file, and the AST of every touched file is unchanged. |
| R-16 | `742db6bf` | Two EC-19 tests in `test_harness_compose_concurrency.py`: one failed worktree add beside a Grok verifier that holds with a grandchild, and two failed adds. |
| R-17 | `c81d8596` | `test_a_refusal_of_caller_text_never_quotes_the_key_it_holds` in `test_harness_compose_keys.py`: 21 caller-text sites, each holding a 16-character key. |

`test-plan.md` gives each new case's proof under "Coverage added after the S4 review". In short:

- **The first EC-19 test** is green on HEAD. `s4v_mut_gather` kills it (`INV-14: tasks still pending when the error propagated: ['CliRunner._drain', 'CliRunner._drain', 'ThreadVerifiers._review']`), and so does `s4v_mut_nocancel` (`the error propagated 30.0 s after the add failed: the sibling was not cancelled`).
- **The two-failed-adds test** stays red on HEAD until R-10 lands. It failed in 8 of 8 runs, with `['CliRunner._drain', 'CliRunner._drain', 'ComposeGit.remove_worktree']` still pending at the raise. It passes in 6 of 6 runs under `s4v_fix_add_settle`.
- **The 21 caller-text cases** stay red on HEAD until R-3 lands. They pass under a scratch plugin in which no refusal quotes its value. Under a partial fix that still quotes one binder's model refusal, only that binder's model case fails. The final lines of one failing case on HEAD:

```
>       assert pack.leaks(shown, [text.key]) == [], f"INV-4: the {site} refusal quotes the key: {str(error)!r}"
E       AssertionError: INV-4: the chain_threads template refusal quotes the key: "template must match [^\\x00]+; got '{previous} vbk-7f1cd7192793\\x00'."
E       assert ['-7f1cd71927...vbk-7f1cd719'] == []
E         Left contains 5 more items, first extra item: '-7f1cd719279'
```

Method notes:

- **The outside fault is a git hook.** It is a `reference-transaction` hook that exits 1 at "prepared", so git prints `fatal: ref updates aborted by hook`, exits 128 and removes the half-added worktree itself. The sandbox repository names the hook folder in its own `core.hooksPath`, as an absolute path. On win32 the hook is an `.exe` built from pip's `t64.exe`, because Git for Windows finds no `sh` on the sandbox's closed `PATH` and cannot start a hook named by a relative path. The hook waits for its cue (the stand-in's grandchild record, or the other add's arrival) and records whether the cue came.
- **The R-10 window is about one removal wide.** That is about 7 ms of git on this host. A fixed delay made the two-failed-adds test red in only 5 of 8 runs, so the test now times a failing `git worktree remove` and sweeps the second failure's delay from 1/6 to 5/6 of that time.
- **Short keys reach the quote.** A refusal quotes a value only while its repr fits in 80 characters, so `short_key` makes 16-character keys and leaves `fresh_key` unchanged. The bad value's repr is then 33 characters, so a cheat fix that only lowers the quote limit still fails all 21 cases at any limit of 33 or more. A first version with 41-character keys passed all 21 at a limit of 40 (scratch plugin `s2b_mut_quote_limit`), and was replaced before it was reported.

Gates on `c81d8596`:

- `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` gives `22 failed, 277 passed`. The failures are the two-failed-adds test and the 21 caller-text cases, which stay red by design until R-10 and R-3 land.
- `tests/features/harness_threads` gives `436 passed, 2 skipped`, and `python lint/run.py` ends `SDK-LINT: PASS`.
- The awk check prints 0 lines, and `procs.py --kill` and psutil show no stand-in left.

Open items:

1. **The model sites go past R-3's list.** `bind_thread` and `bind_continue` refuse a bad model with `model must match ^[A-Za-z0-9]\S*$; got '...'`, key included. INV-4 covers "any `ConfigurationError` compose raises", so a case for each binder asserts it. The check appears to belong to the base `NativeThreadRequest` (INV-2), so `quote=False` at R-3's eight compose sites will not reach it. If the spec owner rules base-record refusals out of INV-4, those two cases go and nothing else changes.
2. **The model pattern accepts a NUL.** A NUL is not whitespace, so `\S` matches it, and an opencode model of `openai/` plus a key and a NUL binds without an error. The spec states no rule for this, so no test pins it. It is base behaviour, for the spec owner.
3. **One probe broke a process rule.** While timing a failing removal for R-16, one probe ran `git worktree remove --force` on a folder that did not exist, with the worktree root as its working folder. That addressed this worktree's own repository, which the rules forbid. Git refused (`is not a working tree`) and changed nothing. Every later probe used a scratch repository.
