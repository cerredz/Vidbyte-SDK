# S3 Implementer report: native-thread-compose

- **Stage:** S3 implementer, spec r4 (`91bb3b8b`), tests at S2_HEAD `2ef11f3a`.
- **Branch:** `feat/native-thread-compose`, stacked on `feat/native-grok-opencode-meta-hosts`, in the worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`.
- **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1186
- **Code head:** `feea90c8`. The last code commit; only `docs/spec` commits follow it.
- **Result:**
  - Every row of spec §12.3 is implemented, in phase order P1 to P4.
  - All 276 compose tests pass with no scaffolding, and the 436 base tests still pass.
  - The full local gate passes at the code head: `scripts/run_ci.py`, source and package stages. The lines are quoted in §7.
  - The AC-21 wheel half is proven.
  - No test, fixture or test config changed: `git diff 2ef11f3a..HEAD --stat -- tests` is empty.

## 1. Commits

Each commit covers one §12.3 row, or a tightly coupled pair, and ends with the Co-Authored-By line. Oldest first:

| Commit | Row(s) | Subject |
|---|---|---|
| `8674bfd2` | 1, 2 | feat(lib): add the native compose vocabularies and export them |
| `8d400766` | 3 | feat(lib): add the native compose constants |
| `af4d0ff7` | 4 | feat(lib): add require_template and command_line_units to RecordFieldValidator |
| `d73ca5f3` | 5, 6 | feat(lib): add JsonText, the strict decoder of a model's JSON answer, and export it |
| `e159a2ca` | 7 | feat(lib): add the native compose records |
| `a61cc63c` | 8 | feat(lib): add the native ensemble records |
| `448b9393` | 9 | feat(lib): add ThreadComposeError with the A003 packet |
| `5fc25e92` | 10 | feat(lib): export ThreadComposeError from vidbyte.lib.errors |
| `623d77e6` | 11 | feat(compose): add ThreadBinder and StepRoles |
| `2c3fa1f5` | 12 | feat(compose): add ComposeCalls and GrokWorkspaceLocks |
| `7bc6bb90` | 13 | feat(compose): add ComposeTexts and PromptFitter |
| `d9e065ac` | 14 | feat(compose): add ComposeGit and ComposeFailures |
| `3425b2a4` | 15 | feat(compose): add DiffCapture and DisposableWorktree |
| `4e8f0961` | 16 | feat(compose): add JsonAnswers and AnswerDecoders |
| `f3145d28` | 17, 18 | feat(compose): add the 22 compose prompt files and ship them |
| `db493c92` | 25 (P2 part) | feat(compose): add the compose package with its plumbing exports |
| `5f968a12` | 19 | feat(compose): add chain_threads and the six pair aliases |
| `bcb47eed` | 20 | feat(compose): add verify_with and the three trio aliases |
| `2d7bbe02` | 21 | feat(compose): add handoff_thread |
| `560c8d03` | 22 | feat(compose): add run_staged_threads and the stage decision |
| `d0c82c43` | 24 | feat(compose): add EnsembleSelector, the narrowing rounds and final selection |
| `04cfcd79` | 23 | feat(compose): add run_ensemble |
| `3fe56a12` | 25 (P3 part) | feat(compose): export the composites and the nine aliases |
| `35c5341f` | 26 | docs(harnesses): describe the compose subpackage and its limits in the native bullet |
| `aae3d590` | 27, 28 | docs(harnesses): point the repository map and the native header at compose |
| `feea90c8` | 23, 24 (fix) | fix(compose): keep the planner's and the selector's answers in the record when their worktree cannot be removed |
| `e05f812b` | n/a | docs(spec): record draft PR for native-thread-compose |
| `ce8ad488` | n/a | docs(spec): record implementation proof for native-thread-compose |

This report is committed after the proof commit. Row 24 came before row 23 because `ensemble.py` imports `selection.py`.

`feea90c8` came after the first full gate. That gate passed at `aae3d590`, and I then checked the edge cases the tests leave out against the spec. EC-16 ("its `result` holds the record so far") was not met by the two single readers:
- When the planner's worktree could not be removed, `result` stayed `None`.
- When the selector's worktree could not be removed, its rounds and selection were dropped.

A scratch check failed 3 of 3 before the fix and passes 3 of 3 after it (§7). The full gate was then run again at `feea90c8`.

## 2. Data flow

1. **Binding.** The caller binds one of the nine thread functions with `bind_thread` or `bind_continue` (`ThreadBinder` in `steps.py`). The result is a validated `ThreadStep`: its invoker is `ThreadBinder.invoke`, and its key has `repr=False`.
2. **Checks before any I/O.**
   - Each composite checks every step against the nine-function table (`require_step`).
   - It applies the role rules in `StepRoles`: count, anchored, reader, fork role, `from_thread`, one workspace and alias harness.
   - It checks the caller's prompt or template.
   - `PromptFitter.check` renders every prompt at its longest, with each spliced value as its longest truncation note. It refuses a prompt that would not fit, naming the caller's argument.
3. **Git.** Only three composites run git: `verify_with`, `run_ensemble`, and a chain whose template splices `{diff}`.
   - Each runs `ComposeGit.locate`, `toplevel` and `has_commit` before any step.
   - A snapshot is a temporary-index `read-tree HEAD`, then `add -A`, then `write-tree`.
   - A diff is `diff --name-only` and `diff` between two trees.
4. **Steps.**
   - Every call goes through `ComposeCalls.call`, which turns a `NativeThreadError` into a `StepOutcome`.
   - A Grok call takes a one-slot semaphore, one per event loop and workspace.
   - Fan-outs of verifiers and proposers go through `ComposeCalls.fan_out`.
   - Every prompt passes `PromptFitter.fit`, which strips NULs and bound keys from spliced values and cuts each to a fair share.
5. **Readers.**
   - A Grok reader runs in place.
   - An opencode or Muse reader runs in `DisposableWorktree.from_tree`, a worktree filled from the phase snapshot. A verifier's index is set to the tree from before the writer.
   - After the phase, `DisposableWorktree.backstop` compares a fresh snapshot with the one from the phase start. It raises `READER_CHANGED_WORKSPACE` with the diff and the record so far.
6. **Structured answers.** These are the verdicts, the plan, the rounds and the selection.
   - Each is asked by `JsonAnswers.ask`: one `json_answer` turn, plus up to `COMPOSE_JSON_REPAIR_TURNS` `json_repair` turns on the same thread.
   - Each is decoded by `JsonText.decode` and then one `AnswerDecoders` decoder.
7. **Results.** Each composite returns its record: `ChainResult`, `VerifyResult`, `HandoffResult`, `StagedResult` or `EnsembleResult`. A `ThreadComposeError` carries the record so far in `result` (INV-15, EC-16).
8. **Ensemble.** It runs plan, propose, select and implement.
   - It checks the roles, the task and the fit of every first turn.
   - It runs git, then takes one snapshot, S0.
   - The planner answers through `JsonAnswers.ask`.
   - The proposers then run concurrently:
     - Grok proposers run in place. An unanchored fork is anchored at the planner's thread and opened with `fork_turn`.
     - opencode and Muse proposers each run in a worktree from S0.
   - `EnsembleSelector.select` runs narrowing rounds while `target = max(ceil(alive / 5), 1) > 1`, then a selection. All its turns run on one thread; for opencode or Muse, they also run in one worktree.
   - The backstop runs against S0, also after an early stop.
   - The implementer then runs in place.

## 3. Rows ticked

All 28 rows of §12.3 are done:
- P1: rows 1 to 10.
- P2: rows 11 to 18, and row 25 with the plumbing names.
- P3: rows 19 to 24, and row 25 completed to 42 names.
- P4: rows 26 to 28.

## 4. Implementation deviations

None of these changes a public name, signature, record field, prompt field set, git command or port rule. Each one is also recorded in spec §17 under "Implementation deviations".

**Additions beyond the §8.5 lists:**
1. **Extra constants.** `vidbyte/lib/constants/native_compose.py` holds more than the §8.5 block: the message templates, argument names, observation texts and unit words that the compose modules need under base INV-15.
2. **Segment-based rendering.** `ComposeTexts.render` returns `(text, spliced)` segments built with `string.Formatter().parse`, the parser that `format_map` uses. The joined text equals what `format_map` gives, and each spliced value stays separate for the scrub and the cut.
3. **Helper additions:**
   - `ComposeTexts.spliced`, `join` and `opening`. `opening` builds an ensemble role's first turn: its system text, then its turn, or `fork_turn` around both.
   - `ComposeFailures.changed`.
   - `StepRoles.counted`, `item`, `member`, `unanchored` and `on_harness`.
4. **`ThreadBinder.anchor`** takes a verb: `CONTINUE` by default, `FORK` for an unanchored fork. `bind_continue` checks `thread_id` up front.
5. **Reader worktrees and the backstop.**
   - `DisposableWorktree.from_tree` builds a reader worktree from a composite's snapshot.
   - `DisposableWorktree.backstop` is the single INV-11 comparison, shared by `verify_with` and `run_ensemble`.
   - `DiffCapture` takes no keys argument.
6. **JSON answer helpers.**
   - `JsonAnswers.ask` holds the repair loop, and `JsonAnswers.wrapped` builds a first turn; the composites share both.
   - `AnswerDecoders.read` turns one answer into a value or a problem.
   - The plan decoder is keyed by `ComposeField.ROLES`, the `{roles}` field of `plan_schema`.
7. **`ComposeGit`** is an instance class that holds the workspace, the root and the keys. It has `has_commit(required=)`.
8. **`ThreadStep` class attributes.** `ThreadStep` has `CONFIG_TYPES` and `JSON_KIND_NAMES` as class attributes.

**Readings where the spec was silent:**

9. **Git failure classes.** A git timeout during a worktree command is `WORKTREE_FAILED`. A failure to launch git is `GIT_UNAVAILABLE`. Removing a temporary index folder ignores errors.
10. **Blank verdict findings.** Items of `ThreadVerdict.findings` may be blank.
11. **`fan_out`** uses `asyncio.wait(FIRST_EXCEPTION)` and then `gather(return_exceptions=True)`. Exactly one exception propagates, never a group.
12. **Problem texts.**
    - An exception with blank text gives its type name as the problem.
    - The record keeps the problem cut at 2,000 characters.
    - The repair prompt gets the whole problem with keys scrubbed, so a cut never leaves part of a key.
13. **Aliases** call `Signature.bind_partial` before `bind`. A misspelled keyword is then named before the missing one it replaced (EC-77).
14. **Shared git check.** Chain steps on one workspace share one git check.
15. **Record so far (INV-15, EC-16).**
    - Each composite attaches the record so far to a `ThreadComposeError` whose `result` is still `None`.
    - The planner and the selector attach their own answers when their worktree cannot be removed: the plan, or the rounds and the selection.
    - Several readers running at once (verifiers, proposers) give the record from before their stage, because the first failure cancels the others (D-17).
    - The backstop diffs only when the tree ids differ.
16. **No up-front handoff check.** `handoff_thread` has no up-front fit check. Its two prompts are fixed files with no caller text, so there is no caller argument to blame. The fit at send time still applies.
17. **`ThreadStages.classify`** takes a `StepOutcome` and returns `None` for a success. Schema files are rendered with `str.format_map` before being passed as fixed text.
18. **Ensemble up-front check.**
    - Every selector turn is checked as a first turn holding one block per proposer.
    - The round turn is checked only when a round can happen.
    - The round number and the survivors are counted as the number of proposers, an upper bound under INV-18.
    - Repair turns hold no caller text, so they are not checked up front.
19. **Selector record.** `EnsembleSelector.select` takes and returns an `EnsembleResult`.
20. **EC-23 share.**
    - Measured: a Grok selector over ten 100,000-character proposals keeps about 1,560 characters of each in its first round turn (1,564 on win32). The README states about 1,500.
    - The spec estimated about 1,100. That estimate assumed 12,000 characters of fixed text beside the proposals; the actual fixed text is about 7,600.
21. **Prompt wording.** The wording of the twelve new prompt files is mine, within the §9.2 field sets and port rules.
22. **Development scaffolding.** A scratch pytest plugin outside the repository exposed the composites before row 25 existed. It was used only during development; every gate below ran without it.

## 5. Files outside §12.3

There are none. The 40 new files and 9 modified files are exactly the §12.3 rows:
- **New files:** 18 `.py` (5 lib modules and 13 compose modules) and the 22 prompt `.md` files.
- **Modified files:**
  - `REPO_MAP.md` and `pyproject.toml`;
  - `vidbyte/harnesses/README.md` and `vidbyte/harnesses/native/__init__.py`;
  - `vidbyte/lib/dataclasses/validation.py` and `vidbyte/lib/enums/__init__.py`;
  - `vidbyte/lib/errors/__init__.py` and `vidbyte/lib/errors/base.py`;
  - `vidbyte/lib/util/__init__.py`.

The helper additions in deviations 3 and 5 sit in §12.3 files: `steps.py`, `texts.py` and `workspace.py`.

No file changed under `tests/`, `lint/`, `.semgrep/`, `contracts/`, `.github/` or `scripts/`. Under `docs/`, my only changes are:
- the spec's frontmatter `pr:` and `status:`;
- the AC-21 Proof cell;
- the §17 row and the "Implementation deviations" subsection;
- this report.

## 6. Budget (§8.4)

| Item | Budget | Actual |
|---|---|---|
| New files | 40 (18 `.py`, 22 `.md`) | 40 (18 `.py`, 22 `.md`) |
| Modified files | 9 | 9 |
| Compose classes | 22 | 22 |
| Records / enums / errors / decoders | 18 / 7 / 1 / 1 | 18 / 7 / 1 / 1 |
| `compose.__all__` | 42 | 42 |
| Dependencies / config keys | 0 / 0 | 0 / 0 |

The 13 compose modules total 2,218 lines. The largest is `ensemble.py`, at 260 lines.

## 7. Gate results (final lines, quoted)

Each command ran from the worktree root, at `feea90c8` unless noted.

**Full local gate**
- Source stage: `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`. It runs lint, compileall, the three check scripts and the whole test suite.
  ```
  SDK-LINT: PASS
  context write-path integrity: ok
  context primitive introductions: ok
  reasoning trace contracts: ok (182 tools, 55 shapes)
  ================ 5917 passed, 16 skipped in 139.34s (0:02:19) =================
  CI passed.
  ```
  - The log's last line is `source exit=0`.
  - The first run, at `aae3d590`, also ended with `CI passed.`. Its test line was `5917 passed, 16 skipped in 138.97s (0:02:18)`.
- Package stage: `py -3.11 scripts/run_ci.py --stage package --dist-dir <empty scratch folder>`, run with no `PYTHONPATH`.
  ```
  Successfully built vidbyte_sdk-0.3.0.tar.gz and vidbyte_sdk-0.3.0-py3-none-any.whl
  (twine) -any.whl: PASSED
  (twine) c484-4b56-acef-651ebe9a78a5\scratchpad\s3\dist-final\vidbyte_sdk-0.3.0.tar.gz: PASSED
  No broken requirements found.
  Installed vidbyte-sdk 0.3.0 passed smoke checks.
  CI passed.
  ```
  - The log's last line is `package exit=0`.
  - The first run, at `aae3d590`, ended the same way.
  - `twine check` wraps its lines, so each `PASSED` line above is the tail of a wrapped path.

**Area tests and lint**
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_compose`
  ```
  ........................................................................ [ 78%]
  ............................................................             [100%]
  276 passed in 43.85s
  ```
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads`
  ```
  ......                                                                   [100%]
  436 passed, 2 skipped in 46.92s
  ```
- `py -3.11 lint/run.py`
  ```
  S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

  SDK-LINT: PASS
  ```
  - Its rule table is identical to the one after row 27.
  - Every ratchet count matches the baseline or is lower. The IMPROVED hints were left alone, as instructed.

**Scratch checks** (outside the repository)
- EC-16, run as `py -3.11 -m pytest -q -p tests.features.harness_compose.conftest <scratch>/scratch_ec16_check.py`:
  - at `aae3d590`: `3 failed in 15.16s`;
  - at `feea90c8`: `3 passed in 15.33s`.

**Static checks**
- **Semgrep.** I put the semgrep virtual environment's `Scripts` folder first on `PATH`; otherwise the system `pysemgrep` loads mcp 2.x and crashes.
  - `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`
    ```
    1/1: ✓ All tests passed
    No tests for fixes found.
    ```
  - `semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, which exited 0:
    ```
    Ran 1 rule on 976 files: 0 findings.
    ```
- `py -3.11 -m ruff check pyproject.toml vidbyte --config lint/ruff.toml --select TID251 --no-cache` printed `Found 5 errors.`, which is the baseline of 5.
- `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` printed `Found 223 errors.`, which is the baseline of 223. Every new module is clean.
- **The 18 new modules:**
  - ruff with `lint/ruff.toml`: `All checks passed!`;
  - mypy with `lint/mypy.ini`: 0 errors in them (the errors it prints are pre-existing ones in `vidbyte/paradigms`).

**AC-21 wheel half**
- **Wheel contents.** `py -3.11 -m zipfile -l` on `vidbyte_sdk-0.3.0-py3-none-any.whl`, built by the package stage above, lists 22 `.md` entries under `vidbyte/harnesses/native/compose/prompts/` and the 13 compose modules.
- **Installed copy.**
  - The wheel was installed with pip into a new virtual environment in the scratch folder.
  - `<venv>/Scripts/python.exe -I check_wheel_prompts.py <checkout>` then ran from a folder outside the checkout, with no `PYTHONPATH`. It printed:
  ```
  installed vidbyte: C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\d2d5110d-c484-4b56-acef-651ebe9a78a5\scratchpad\s3\wheel-venv-final\Lib\site-packages\vidbyte\__init__.py (outside the checkout: True)
  loaded through ComposeTexts.load: 22 prompt files
  installed prompts folder: 22 entries, all .md: True
  placeholders equal COMPOSE_PROMPT_FIELDS: True []
  fixed combinations: 17, longest planner = 8304 chars, over 12000: {}
  forbidden texts in ported files: {}
  AC-21 WHEEL HALF: PASS
  ```
  - The script exited 0.
- **Byte check.** The 35 installed compose files are byte-identical to the committed blobs.
- **First run.** The same check passed against the wheel built at `aae3d590`.
- **The check script** is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s3/check_wheel_prompts.py`. It is not committed.

**Remote CI** (dispatched; I did not wait for the runs)
- **At `e05f812b`**, before the EC-16 fix: both runs succeeded.
  - CI `39118223998`: Source on Python 3.11, Source on Python 3.12 and Package all passed.
  - Static policy `39118225434`: passed.
- **At `ce8ad488`**, after the fix and the proof: CI `39119540221` and Static policy `39119541758`. Both were queued or running when this report was written.
- **Report commit.** The report commit that follows changes only this file.

## 8. Tricky parts

- **Principle 1 in `run_ensemble`.**
  - The first turns of the proposers and the implementer are built in the main function by one helper, `_frame`.
  - For the up-front check, `_frame` is called with `texts=None`. Every spliced field is then empty, so it is measured at its longest note.
  - For the run, it is called with the real texts. The check and the send therefore cannot drift, and no helper calls another helper.
  - The selector's up-front fit lives in `EnsembleSelector.check`, next to the turns it measures.
- **One selector worktree for every turn.**
  - The selector uses `DisposableWorktree.from_tree(...)` for opencode and Muse, and `contextlib.nullcontext()` for Grok, under one `async with`.
  - All rounds, repairs and the selection run inside it, so the loop is not split into a second helper.
  - The same block is wrapped by the EC-16 `except`, which attaches the rounds and the selection so far.
- **Thread continuity.**
  - Later selector turns use `ThreadBinder.anchor(step, answer.thread_id)`, a `CONTINUE` on the selector's own thread.
  - The first turn of an unanchored Grok fork uses `anchor(..., plan.thread_id, FORK)`.
  - Repairs inside `JsonAnswers.ask` continue whichever thread the turn produced.
  - The tests check `--resume`, and that the switches are empty for a continue and hold `--fork-session` for a fork.
- **INV-15 and A007.**
  - Literals are limited to docstrings, `__all__`, `""`, `0` and `1`. So the target is `math.ceil(len(offered) / ENSEMBLE_NARROWING_FACTOR)`, and the round number is `len(rounds) + 1`.
  - A007 forbids literals near names such as `attempt`, so stage attempts are named `tried`.
- **mypy narrowing.** `JsonAnswer.thread_id` is `str | None`, even when the answer is ok. The code reads the value and the thread id into locals and checks both, rather than asserting.
- **Windows command-line units.**
  - On win32, the fit counts Grok and Muse prompts in UTF-16 command-line units.
  - In the test with ten long proposals, the character cap binds first: 24,000 characters against 30,000 units.
  - The prompt lands within 10 characters of the cap.
- **Untested spec rows.** The test plan leaves EC-16 untested on purpose, because an undeletable folder is a flake. It was checked with a scratch test that removes the worktree for real and then reports the removal as failed.

## 9. Open items

1. **Key in a short invalid prompt.**
   - The problem: a caller's prompt or template that fails `require_text`, holds a key, and has a `repr` of 80 characters or fewer is quoted in the `ConfigurationError` message. The quoting is done by the base `RecordFieldValidator._received` (`vidbyte/lib/dataclasses/validation.py`).
   - The conflict: AC-15 says no key appears in any `ConfigurationError` message. The bad-template case it tests passes, because `require_template` names the type only.
   - The fix needs either a change to the shared validator or a scrub in compose, both outside §12. I left it for S4 and S5.
2. **Concurrent readers on EC-16.** When the worktree of one of several verifiers or proposers cannot be removed, the other readers' finished answers are dropped. `fan_out` propagates one exception and cancels the rest (D-17, INV-14), so `result` holds the record from before that stage. Keeping them would need a partial-result shape for `fan_out`, which the spec does not define.
3. **Blank `{previous}` prompt.** A chain or stage template made only of `{previous}` sends a blank prompt when the previous answer is empty. The step refuses it as `configuration.invalid_argument`, which is recorded as that step's failure (documented in `stages.py`).
4. **Lone surrogates.** Lone surrogates in model output pass through unchanged. Whether a vendor CLI accepts them in argv is untested.
5. **`parse` returning `None`.** A caller `parse` that returns `None` leaves the `JsonAnswer` without a value, and no repair turn follows. This follows INV-19: "value set exactly when parse returned" (documented in `answers.py`).
6. **Prompt quality.** The ported and the new prompts cannot be measured offline (A-8).
