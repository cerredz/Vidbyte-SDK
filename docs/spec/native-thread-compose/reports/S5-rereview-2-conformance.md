LENS: conformance (post-repair re-review, round 2 — final)
VERDICT: MERGEABLE AFTER FIXES — All 25 fixes hold and R-33 is exact, with no collateral damage, but one path that has existed since S3 breaks ledger 3's "never reaches … error messages or logs": on EC-16, `ComposeGit._delete` chains the raw `OSError`, which names a key-named file that a step saved, so every logged traceback of the `ThreadComposeError` prints the key.

Review target: the code at `18e945ae`. `vidbyte/` and `tests/` are byte-identical at `0e4321a4`, `18e945ae` and HEAD `bfb53664`, and every later commit touches only pipeline.md. It is checked against spec r5 with the R-33 grant record `7aad13ba`. `S` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad`. Every command ran from the worktree root with `PYTHONPATH=$(pwd)`.

FIX CONFIRMATIONS
- R-1 — holds — `COMPOSE_TRUNCATED_PROBLEM = "The answer was cut at the length limit, so it was not read."` (vidbyte/lib/constants/native_compose.py:298). The cue addressed to the model is gone.
- R-2 — holds — A grep for a literal floor (`minimum=<digit>`, `min(kept) < <digit>`, `min_items=<digit>`) over the 13 compose modules and both record modules prints nothing. Every floor is a named constant beside its cap (grant (d)).
- R-3 — holds — Every compose `require_text` passes `quote=False`: answers.py:58, :59; chain.py:54, :116; ensemble.py:59; stages.py:104; steps.py:82, :114; verify.py:55. The other compose validator calls never quote. The S4 probe gives `key_in` False on every row (`3 passed`), and the 21 caller-text cases pass while reading every error surface.
- R-4 — holds — `python $S/s4-verifier/chain_check.py` prints `checked 20 files` and finds no two-level chain.
- R-5 — holds — `SecretText.replace_all` is the only key scrub. It is called in `ComposeFailures.error` (git.py:45-54) and `PromptFitter.fit`. No `.replace(key` loop and no `ComposeFailures._replace` remain.
- R-6 — holds — The awk 72-column comment check prints nothing for the 13 compose modules or the 5 new lib modules. No added comment line in a modified file is over 72 columns.
- R-7 — holds — `to_tuple(..., min_items=...)` is used in chain.py, stages.py, verify.py and the ensemble records. `StepRoles.counted` and `COMPOSE_COUNT_RULE` are gone: the grep is empty, and the constants diff shows the removal.
- R-8 — holds — The S4 EC-16 probe keeps every verdict and every proposal. The three `cannot_be_removed` tests pass in the 109-test run below.
- R-9 — holds — No `(text, bool)` segment tuple remains: greps for `tuple[str, bool]` and `(text, True|False)` are empty. Segments travel as `PromptSegment` (grant (a)).
- R-10 — holds — Every S4 cancel probe gives `leftovers=0 pending=0 live_grandchildren=0` (`7 passed in 51.89s`). The `second_cancel` and `anyio` tests pass.
- R-11 — holds — The same awk check over `tests/features/harness_compose/*.py` prints nothing.
- R-12 — holds — In the S4 surrogate probes every run is RETURNED and no process is orphaned. A lone surrogate in caller text raises `ConfigurationError` with `launches=0` (`5 passed`). The `surrogate` tests pass.
- R-13 — holds — `test_a_template_blank_without_its_spliced_values_is_refused_before_any_io` passes. `PromptFitter.check` refuses a blank shortest form before any I/O (texts.py:103-105).
- R-14 — holds — `test_a_cancel_during_a_slow_worktree_add_lets_the_add_finish_and_leaves_no_registration` passes. The add runs under `DisposableWorktree._settled` (workspace.py:128).
- R-15 — holds — In the S4 probe, a derived step that meets a skill folder the writer deleted is RETURNED with the error recorded (`5 passed`). `_derived` skips `__post_init__`. The three `deleted` tests pass.
- R-16 — holds — The seam tests now kill both mutants that used to survive. The plain-gather mutant gives `2 failed` ("tasks were still pending when the error propagated"). The no-cancel mutant gives `1 failed` ("the error propagated 30.0 s after the add failed").
- R-17 — holds — `test_a_refusal_of_caller_text_never_quotes_the_key_it_holds` passes all 21 short-key cases. Each case reads `error_surfaces`, which includes the context and cause chain.
- R-18 — holds — Rule 4 at verify.py:8 and ensemble.py:8 now reads "a cancellation, a defect or a compose failure, which goes on alone (INV-14)".
- R-19 — holds — spec.md:1587 records `JSON_KIND_NAMES` as a module constant in `vidbyte/lib/util/json_text.py`, beside `JSON_FENCE`.
- R-20 — holds — stages.py uses `attempts`; `tried` no longer appears.
- R-21 — holds — REPO_MAP.md:161 says "no two of their steps ever write to the workspace at the same time". "only read" is gone.
- R-22 — holds — The git.py:6 inventory names all 16 functions (`_replace` no longer exists, grant (b)). compose/__init__.py:8 rule 2 lists JsonAnswers, DiffCapture and DisposableWorktree. `DiffCapture.__aenter__` and `__aexit__` have step comments (workspace.py:53-55, :67-68).
- R-23 — holds — verdict_schema.md says "The number of findings is limited, so list the most important problems first." and gives no number.
- R-32 — holds — `test_a_chain_template_that_holds_prompt_is_never_refused_as_blank` passes. The blank check reads `whole` (texts.py:103).
- R-33 — holds — Before the fix (`1d7bfbec`), the keys module gives `21 failed, 26 passed`, and every failure is the INV-4 leak assertion. At HEAD it gives `47 passed`. The class sweep gives `183; leaking: 4; clean: 179`. The 4 are the standard library's `Enum(value)`, which is out of scope by ruling. All 1,796 refusals have `__context__` None. The answer problem holds no key at any of the four sites and still names the field. Base messages are byte-identical across 127 cases. Details are under "R-33 in detail" below.

WHAT THE IMPLEMENTATION GETS RIGHT
- `ThreadStep._withheld` (native_compose.py) is keyed on `details["field"]`, not on a scan of the text. It replaces only a str `model` or `thread_id` whose repr the message actually quotes, taking the last occurrence with `rpartition`. Any other refusal comes back unchanged, with its type and `details`: one with no `field`, one for a non-str value, or one for another field. The rewrite is raised outside any handler. A text scan would also strike a `thread_id` that merely contains a quoted model (reports/S5-repair-3.md).
- The `ThreadComposeError` packet scrub holds on the worst EC-16 input. With a key-named file held open in the worktree, the probe below finds no key in the message, `args`, `details`, `safe_runtime_details`, `git_message`, `likely_cause`, `next_step` or `workspace`. Only the chained cause leaks (R-RC2-1).
- Cleanup survives repeated cancels and failed siblings. Both fan-out mutants fail the R-16 seam tests. The R-10 probes leave no worktree, task or grandchild process.
- AC-1 is real and the budget is exact. The test's `SNIPPET` equals the spec §4 block (1,565 characters) and prints exactly the three expected lines. The diff adds 41 files (19 `.py`, 22 `.md`) and 51 classes. pyproject gains one line (package data) and no dependency. `lint/baseline.json` is untouched.

FINDINGS
R-RC2-1 [Blocker] [weighted word / INV-4 "never" sweep] vidbyte/harnesses/native/compose/git.py:228 (same pattern at git.py:217 and workspace.py:189) — An EC-16 removal failure chains the raw `OSError`, so a bound key that a step saved in a file name reaches the error's `__cause__` and every logged traceback
  Evidence:
  - git.py:219-228, `ComposeGit._delete`: `except OSError as error:` / `observation = native_compose.THREAD_COMPOSE_FOLDER_OBSERVATION.format(folder=folder, error_type=type(error).__name__)` / `raise ComposeFailures.error(ThreadComposeProblem.WORKTREE_FAILED, self.workspace, observation, self.keys) from error`. The observation names only the folder and the error type, and `ComposeFailures.error` scrubs it. The chained `error` is never scrubbed. The code's own `@intent compose-errors-never-show-a-key` (git.py:40-43) says "A folder name or git's text can hold a key a writer saved".
  - Command: `PYTHONPATH="$(pwd)" python -m pytest -q -s -p no:cacheprovider -p tests.features.harness_compose.conftest "$S/s5-rereview-2/test_rc2_cause.py"`. The probe uses only stand-ins. It runs `verify_with`: an opencode writer bound to `key` writes `<key>.txt`, a Muse verifier answers, and an opencode verifier waits in hold mode. The test holds `<key>.txt` open inside the held verifier's worktree, with the same open-handle method as `RemovalBlocker` in test_harness_compose_removal.py, and then releases the stand-in. It was run twice, with the same result both times. Output (path shortened, separators normalized):
    `key-named file in the held worktree: True`
    `problem: worktree_failed`
    `reachable[0] ThreadComposeError: key in {'str': False, 'repr': False, 'args': False, 'details': False, 'safe_runtime_details': False, 'git_message': False, 'likely_cause': False, 'next_step': False, 'workspace': False, 'problem': False}`
    `reachable[1] PermissionError: key in {'str': True, 'repr': False, 'args': False, 'filename': True, 'filename2': False}`
    `key in the default traceback text: True`
    `cause, with the key masked: [WinError 32] The process cannot access the file because it is being used by another process: '…/case0/tmp/vidbyte-compose-worktree-qpjme9md/<KEY>.txt'`
    `1 passed in 24.24s` (first run: `1 passed in 14.51s`)
  - The pattern has existed since `d9e065ac` (S3); it is not an S5 regression. No test can see it. The AC-15 test `test_git_text_and_file_names_that_hold_a_key_are_scrubbed_from_errors` (test_harness_compose_keys.py:423-457) checks only `str`, `args` and `vars`. The EC-16 tests hold a file named `lock.txt`.
  Failure:
  - A writer, or a reader in its worktree, saves a file or folder whose name holds a bound key.
  - While the reader's worktree is being removed, something on Windows holds that file: a lingering child or an antivirus, which is EC-16's own example.
  - `remove_worktree` calls `_delete`, whose `shutil.rmtree` raises a `PermissionError` naming `<worktree>/<key>.txt`.
  - `verify_with` and its aliases then raise `ThreadComposeError(WORKTREE_FAILED)`. So does `run_ensemble`, whose planner, proposer and selector worktrees also use `DisposableWorktree.from_tree`.
  - The message is clean, but `__cause__` and `__context__` are the `PermissionError`. `traceback.format_exception(error)` shows the key, and that is what `logging.exception` and an uncaught error print.
  This breaks ledger 3, "still never reaches argv, files, `os.environ`, error messages or logs" (request.md:54; weighted in §D at :166), and §14 Never, "Put a key in … an error, a log" (spec.md:1488). INV-4 (spec.md:252) exempts only `result` and `diff`. The test plan counts "any exception the refusal keeps as `__context__` or `__cause__`" as part of an error (test-plan.md:224), which is the rule R-33 was fixed to. Neither EC-71 nor the INV-4 r3 ruling covers this case: both keep step text raw only in records. T-3's residual also names only records (spec.md:1115).
  Smallest fix:
  - In `ComposeGit._delete`, keep only `type(error).__name__` inside the handler and raise `ComposeFailures.error(...)` after the handler. Then neither `__cause__` nor `__context__` holds the OS error. This is R-33's rule; `raise … from None` is not enough (test-plan.md:249).
  - Make the same change in `_folder` (git.py:217) and `DisposableWorktree._matching` (workspace.py:189), so one rule holds everywhere. Their OS errors name only compose's temporary folder or the caller's workspace path.
  - No constant, message, record or public name changes, and the EC-16 tests' assertions still hold.
  - The test author adds one keys row: the EC-16 hold, placed on a `<key>.txt` the writer saved, asserting `pack.leaks(error_surfaces(error), keys) == []`. The probe above shows that this row is red at HEAD.
  Spec IDs: INV-4, AC-15, EC-16, §14 Never (a key in an error or a log), ledger 3 (request.md:54, :166). EC-71 and T-3 do not exempt it.

VERIFIED CLAIMS
- The code under review did not change after `0e4321a4`: `git diff --stat 0e4321a4 bfb53664 -- vidbyte tests` is empty, and `18e945ae..bfb53664` touches only pipeline.md. Held.
- R-33 touches 4 files, 72+/66- (`git show --stat 0e4321a4`). Held.
- The compose pack gives `385 passed` and the keys module `47 passed`. Held.
- R-33 in detail:
  - Each element of the review's fix is present:
    - `quote` added to `require_int`, `require_bool` and `to_enum` and passed to `_received` (validation.py:117-130, :201-210);
    - `quote=False` at native_compose.py:97, :98, :181, :198, :272, :354, :367 and :370 and at native_ensemble.py:70 and :123, which are the review's :96, :97, :152, :169, :243, :325, :338 and :341 after the lines moved;
    - `_probe` returning the request or its `ConfigurationError`, with `raise self._withheld(probe)` outside any handler;
    - the try/except in both binders and `ThreadBinder._withheld` deleted;
    - `bind_continue` checking its thread id first with `quote=False`;
    - the headers of validation.py, native_compose.py and steps.py describing all of this.
    Held.
  - The fields whose calls still quote by default never quote text that holds a key: `summary`, `findings`, the role and plan texts, `JsonAnswer.problem` and `WorkspaceDiff.text`. They have no pattern, so they refuse only a non-str, blank or over-cap value. Every cap is at least 2,000 characters, far past the 80-character quote limit. So grant (c)'s "every record field whose refusal could quote a str" holds. Held.
  - A key put into the other `ThreadStep` fields, directly and through both binders, is never quoted. `skills`, `workspace`, `config` and `function` refuse by path or by type, and all 14 lines of probe_other_fields.py print `key-in=False`. Held.
  - Red before the fix: the HEAD keys module, run against a read-only export of the `1d7bfbec` tree, gives `21 failed, 26 passed`, and all 21 fail on the INV-4 leak assertion (lines 396 and 419). Held.
- Grant (c) conditions:
  - The 11 base calls keep their defaults.
  - Refusal messages are byte-identical between the base branch tree and HEAD across 127 cases: the 11 base sites, every validator default, and the model and thread_id rules, each with str, int, None, float, bool and long values (`identical: True`).
  - `vidbyte.harnesses.native.__all__` (17 names), `compose.__all__` (42 names, identical at `e1bf20d8`, `bc351671` and HEAD) and the root `__all__` (639 names) are unchanged.
  - `import vidbyte` loads neither the native package nor compose.
  - spec.md:731, :1103, :1308, :1588 and :1626 describe the shipped code.
  Held.
- The `_withheld` behaviour:
  - `details` is always a dict (`VidbyteSdkError.__init__`). A missing `field` gives `""`, then None, so the error comes back unchanged.
  - A non-str value comes back unchanged, and so does a refusal for another field.
  - The rewrite keeps the exception type and the same `details` (INV-5).
  - A repr over 80 characters is never quoted, so nothing is cut.
  Held.
- The int trade-off, judged against the spec text. `StageSpec(retries=4)` gives "StageSpec.retries must be an integer from 0 to 3; got a value of type int." No spec ID requires the received value:
  - AC-14 (spec.md:495) requires the field in `details` and no key.
  - INV-21 (spec.md:414) and the §9.1 row (spec.md:987) give only the range.
  It is not a finding. The residual risk is AGENTS.md principle 4, "names the field and the bad value". The message still names the field and the range, and grant (c) records the choice.
- The "never" sweep of the other compose paths:
  - All 1,796 record refusals have `__context__` None. `ctx_count.py` reports 4 `OTHER-LEAK`; all 4 are `Enum(value)`, which is out of scope by ruling.
  - The answer problem holds no key at any of the four sites: the verdict decision, the selection proposal, the plan role name and the round's `kept`.
  - Every other compose `ConfigurationError` formats only argument names, type names, enum values and counts (texts.py:105-120, steps.py:94-222, stages.py:107, answers.py:57). `require_template` names only the allowed placeholders and raises `from None`.
  - Compose itself logs nothing: there is no `logging`, `print` or `warnings` call.
  - Every `ThreadComposeError` packet is clean. Its `__cause__` is clean everywhere except the EC-16 path (R-RC2-1).
- §8.4 budget: 41 new files (19 `.py`, 22 `.md`), 51 classes (50 in new modules plus `ThreadComposeError`), 0 dependencies (the only pyproject change is the package-data line) and 0 config keys. Held.
- Every changed file has a §12.3 row: the 9 modified and 41 created files map one-to-one onto rows 1-29. Held.
- §14 boundaries: the `lint/baseline.json` diff is 0 lines, and nothing under `lint/`, `.semgrep/`, `.github/`, `contracts/` or `scripts/` changed. The diff adds no `noqa`. Its only two `type: ignore[index]` lines are negative immutability tests from the original S2 test commit `2ec1ce7c`. Held.
- Test tree: since `e1bf20d8`, only S2's `test(compose)` commits touch `tests/`, and they include the granted `3a21352b`. None of them touches a path outside `tests/`, and no `fix` or `docs` commit touches `tests/`. `8fcba2df` deletes only header prose and the old `shown` check. Its replacement, `error_surfaces`, joins str, repr, args and vars for every exception in the context and cause chain, so it checks strictly more than `shown`. Held.
- AC-1: the `SNIPPET` equals spec §4 and prints exactly `[<opencode id>, <grok id>] None`, `['approve', 'approve'] True` and `None 3`, with no leftovers and one worktree registration. Held.
- The §5 diagrams match the call path: `ThreadBinder` → composite → `StepRoles`/`PromptFitter.check` → `ComposeGit` → `DiffCapture` → `DisposableWorktree` → `ComposeTexts.render`/`PromptFitter.fit` → `ComposeCalls.call` (Grok slot) → `ThreadBinder.invoke` → the nine functions → `JsonAnswers` → the result records. Held.
- Scope against request §A–§C: nothing goes beyond the ledger. The only new public surface is the 42 compose names and `SecretText` in `vidbyte.lib.util` (grant (b)). Held.
- `python lint/run.py` and `scripts/run_ci.py` were not re-run. Their results are the orchestrator's (`SDK-LINT: PASS`, `6026 passed, 16 skipped`) on identical code. Unchecked by me.

COMMANDS RUN
- `git diff --stat 0e4321a4 bfb53664 -- vidbyte tests` → (empty); `git diff --stat 18e945ae bfb53664` → `docs/spec/native-thread-compose/pipeline.md | 19 +++++++++++--------`; `git show --stat 0e4321a4` → `4 files changed, 72 insertions(+), 66 deletions(-)`
- `python -m pytest -q -p no:cacheprovider tests/features/harness_compose` → `385 passed in 55.45s`
- `python -m pytest -q -p no:cacheprovider tests/features/harness_compose -k "blank_without or holds_prompt or slow_worktree_add or failed_worktree_add or two_failed or caller_text_never or surrogate or second_cancel or anyio or deleted or cannot_be_removed or secret_text or record_refusal or answer_member"` → `109 passed, 276 deselected in 16.74s`
- HEAD `test_harness_compose_keys.py` → `47 passed in 4.57s`; the same module against the `1d7bfbec` export (`$S/s5-rereview-2/prefix`) → `21 failed, 26 passed`
- `python -m pytest -q -s -p no:cacheprovider -p tests.features.harness_compose.conftest "$S/s5-rereview-2/test_rc2_cause.py"` (twice) → `reachable[1] PermissionError: key in {'str': True, ... 'filename': True ...}`, `key in the default traceback text: True`, `1 passed in 14.51s` / `1 passed in 24.24s`
- `PYTHONPATH="$(pwd);$S/s4-verifier" python -m pytest -q -p no:cacheprovider -p s4v_mut_gather tests/features/harness_compose/test_harness_compose_concurrency.py -k "failed_worktree_add_stops or two_failed_worktree_adds"` → `2 failed, 6 deselected in 1.43s`; the same with `-p s4v_mut_nocancel` → `1 failed, 1 passed, 6 deselected in 31.81s`
- `python $S/s5-verifier-rr1/probe_answers.py` → 4 lines, each `key-in-problem=False` and each naming its field
- `python $S/s5-verifier-rr1/ctx_count.py <worktree>` → `352 ('ACCEPTED', '-')`, `4 ('OTHER-LEAK', '-')`, `1796 ('clean', 'None')`
- `python $S/s5-verifier-rr1/probe_sweep.py` → `TOTAL (entry, record, field) pairs: 183; leaking: 4; clean: 179`
- `python $S/s5-rereview-2/probe_other_fields.py <empty scratch folder>` → 14 lines, all `key-in=False`
- `python $S/s5-rereview-2/base_messages.py`, run on the base-branch tree (`$S/s5-rereview-2/base`) and at HEAD, then diffed → `identical: True` (127 cases)
- S4 verifier probes `$S/s4-verifier/test_s4v_probes.py`: R-3 `3 passed`; R-15 `5 passed`; R-12 `5 passed`; R-10 `7 passed in 51.89s`; R-8 verdicts and proposals kept
- `python $S/s4-verifier/chain_check.py` → `checked 20 files`, no hits
- awk 72-column comment check (`awk 'length($0) > 72' <file>`, keeping comment lines) over the compose, lib and test files → no file with a nonzero count
- `git diff --diff-filter=A --name-only origin/feat/native-grok-opencode-meta-hosts...18e945ae`, outside `docs/` and `tests/` → `22 md`, `19 py`; `grep -cE "^class "` over the new modules → `total 50`, plus `ThreadComposeError` in base.py, for 51
- `git diff origin/feat/native-grok-opencode-meta-hosts...18e945ae -- lint/baseline.json | wc -l` → `0`; the same diff over `lint .semgrep .github contracts scripts` → no files
- `git log --format="%h %s" e1bf20d8..HEAD -- tests` → 13 `test(compose)` commits; no other commit touches `tests/`
- `python $S/s4-verifier/procs.py --kill` after every process run → `stand-in or grandchild processes: []`; it killed one leftover, `[23668] (killed)`, after the gather mutant
- `git --no-optional-locks status --porcelain` → clean before the report was written
