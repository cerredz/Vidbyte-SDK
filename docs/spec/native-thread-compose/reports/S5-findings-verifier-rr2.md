# S5 findings verifier, re-review round 2 (scoped to R-RC2-1)

- **Stage:** S5 findings verifier, re-review round 2. The re-review cap is reached (2 of 2), so no reviewer will see the repair. This verification, the class sweep and the proof copy stand in for that review.
- **Tree:** `feat/native-thread-compose` at HEAD `65c0d1f9`. It is code-identical to `0e4321a4`: `git diff --stat 0e4321a4 HEAD -- vidbyte tests` is empty.
- **Date:** 2026-10-20.
- **Platform:** win32, Python 3.11.0, the real git, and the pack's stand-ins only. No probe started the real grok or opencode. The Ubuntu evidence comes from WSL `MuseUbuntu1` (WSL1), Python 3.12.3, run as `nobody` (uid 65534).
- **Writes:** `review.md` (the R-34 row, the two count lines and the Verdict) and this report. Everything else is in the scratch folder. There are no commits.
- **`V2`** is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s5-verifier-rr2`.

## 1. Result

- **R-RC2-1 is CONFIRMED as a Blocker.** It is added to `review.md` as **R-34**, status `open`. It is the only new row, because the sweep found no second root cause.
- **There is one leaking site: `vidbyte/harnesses/native/compose/git.py:228`** (`ComposeGit._delete`, `raise ... from error`).
  - Compose reaches it whenever it removes a reader's worktree after the reader answered and something holds a file whose name contains a bound key.
  - That covers the opencode and Muse verifiers of `verify_with` and the three trio aliases.
  - It also covers the opencode or Muse planner, proposers and selector of `run_ensemble`, and the public `in_worktree`, which binds no key.
- **The sweep covered 22 `except` or `finally` sites and 4 class checks.**
  - The sites are the 21 in the swept files plus `validation.py:98`, which compose reaches.
  - The checks cover stored exceptions, cross-task fan-out, logging, and the error class itself.
  - Result: 1 site leaks (git.py:228). The other 21 sites and all 4 checks are clean.
  - `git.py:217` and `workspace.py:189` use the same `from error` form, but in scope their chained text holds no key. The fix applies the same rule to them anyway.
- **The fix is proved on a full copy of HEAD.**
  - The probe's chain, traceback and logging surfaces flip from True to False in every scenario.
  - The compose pack gives `385 passed`, harness_threads gives `435 passed, 3 skipped` (the same as the unpatched copy), and `python lint/run.py` gives `SDK-LINT: PASS` with output byte-identical to the unpatched copy.
  - The reference diff passes `git apply --check` on the worktree.
- **Correction for the test author.** The reviewer proposed a test row in which the *writer* saves the key-named file. That row would stay red even with the fix, because the writer's key stays in `error.result.writer.diff`, which EC-71 keeps raw. Use a key-named file that a *reader* saves in its own worktree (§5).
- **Spec:** no record is required for scope, because the weighted words already forbid the leak. A record is recommended for traceability, as was done for R-33. The proposed wording is in §6.

## 2. Verification of R-RC2-1

### 2.1 The code

`vidbyte/harnesses/native/compose/git.py:219-228` at HEAD:

```python
    async def _delete(self, folder: Path) -> None:
        # Delete what is left of a worktree folder; a folder that cannot
        # be deleted is WORKTREE_FAILED, naming it.
        try:
            await asyncio.to_thread(shutil.rmtree, folder)
        except FileNotFoundError:
            return
        except OSError as error:
            observation = native_compose.THREAD_COMPOSE_FOLDER_OBSERVATION.format(folder=folder, error_type=type(error).__name__)
            raise ComposeFailures.error(ThreadComposeProblem.WORKTREE_FAILED, self.workspace, observation, self.keys) from error
```

- `ComposeFailures.error` scrubs the observation, which holds only the folder and the error's type. The chained `error` is never scrubbed.
- `from error` sets `__cause__`. Raising inside the handler also sets `__context__`. Both hold the `OSError`, whose `str()`, `filename` and default traceback text name the file that could not be deleted.
- `_delete` runs in `remove_worktree`'s `finally` (git.py:176-180). `DisposableWorktree.__aexit__` raises the result again after a block that ended normally (workspace.py:154-158). The worktree readers enter that manager at verify.py:157, ensemble.py:211 and :233, and selection.py:62.
- Every opencode and Muse reader runs in a worktree: `StepRoles.needs_worktree` returns `step.harness is not NativeHarness.GROK` (steps.py:226-228).
- History: the pattern dates from S3. git.py got it in `d9e065ac` and workspace.py in `3425b2a4` (found with `git log -S`), so it is not an S5 regression.

### 2.2 Reproduction on win32

**The reviewer's probe** is `S/s5-rereview-2/test_rc2_cause.py`, where `S` is the scratchpad root. I ran it from the worktree root, and it reproduced the reviewer's output:

- `reachable[1] PermissionError: key in {'str': True, ..., 'filename': True, ...}`
- `key in the default traceback text: True`
- the cause names `...\tmp\vidbyte-compose-worktree-ic986nqx\<KEY>.txt`
- `1 passed in 15.63s`

**My own probe**, `$V2/test_s5v_rr2_chain.py`, covers 11 scenarios.

- Command, run from a tree root: `PYTHONPATH=$(pwd) python -m pytest -q -s -p no:cacheprovider -W ignore::pytest.PytestDeprecationWarning -p tests.features.harness_compose.conftest "$V2/test_s5v_rr2_chain.py"`.
- After every run: `python .../s4-verifier/procs.py --kill`, which printed `stand-in or grandchild processes: []` each time.
- Every held scenario (A–G and J) uses `KeyHold`. It holds a `held-by-test/` folder that contains only the key-named file. On win32 it keeps an open handle on the file. On POSIX it would `chmod 0o500` the folder.
- In A–F a stand-in saved the file first. In G (inside the caller's block) and in J, `KeyHold` writes it.

What each probe column checks:

- `packet`: the error's `str`, `repr`, `args` and every attribute except `result` and `diff`.
- `chain`: any exception reachable through `__cause__` or `__context__`.
- `traceback`: `traceback.format_exception(error)`.
- `logging`: what `logging.error(..., exc_info=error)` writes.
- `pack es`: the pack's own `error_surfaces` (keys module), which also includes `result` and `diff`.

Results at HEAD:

| Scenario | Path | Chain at HEAD | packet / chain / traceback / logging / pack es |
|---|---|---|---|
| A | `verify_with`; the writer saves `held-by-test/<writer key>.txt`, so it is in every verifier's worktree; the opencode verifier's copy is held | `['ThreadComposeError', 'PermissionError']` | False / True / True / True / True |
| B | `verify_with`; the held opencode verifier saves `held-by-test/<its key>.txt` in its own worktree | same | False / True / True / True / True |
| C | `run_grok_verify_with_opencode_and_muse`; the opencode verifier saves the file and is held | same | False / True / True / True / True |
| D | `run_ensemble`; an opencode proposer saves the file and is held | same | False / True / True / True / True |
| E | `run_ensemble`; an opencode planner saves the file and is held | same | False / True / True / True / True |
| F | `run_ensemble`; an opencode selector saves the file and is held | same | False / True / True / True / True |
| G | `in_worktree`; the caller's block saves the file (no key is bound) | same | False / True / True / True / True |
| H | git.py:217: `tempfile.tempdir` is a file, so `mkdtemp` fails | `['ThreadComposeError', 'FileNotFoundError']` | False / False / False / False / False |
| I | workspace.py:189: a stand-in `FileExistsError` for the matching folder of a sub-workspace named after a key | `['ThreadComposeError', 'FileExistsError']` | False / True / True / True / True |
| J | `remove_worktree` with a git failure in flight (a `ComposeFailures` time-out error) and the folder held | `['ThreadComposeError', 'PermissionError', 'ThreadComposeError']` | False / True / True / True / True |
| K | a recorded repair-turn `NativeThreadError` compared with a direct call | `['NativeThreadError']` for both | no key beyond the error |

The causes, with the key masked:

- A–G and J: `[WinError 32] The process cannot access the file because it is being used by another process: 'C:\\Users\\422mi\\AppData\\Local\\Temp\\pytest-of-PC\\pytest-6329\\case1\\tmp\\vidbyte-compose-worktree-ipmp2agy\\held-by-test\\<KEY>.txt'` (this line is B's).
- H: `[WinError 3] The system cannot find the path specified: '...\\case7\\temporary-folder-is-a-file\\vidbyte-compose-index-i613379t'`.
- I: `[Errno 17] File exists: '...\\case8\\tmp\\vidbyte-compose-worktree-u9meemxw\\<KEY>'`.
- J's third link is the scrubbed git failure, which shows `[redacted]`.

The run gave `12 passed in 57.37s` on the worktree, with cold bytecode caches. The unpatched archive copy `$V2/control` gave the same flags in `12 passed in 6.43s` (`$V2/probe_control.out`).

### 2.3 The Ubuntu trigger (CI runs ubuntu-latest with Python 3.11 and 3.12)

`$V2/posix_rmtree.py` puts the key-named file alone in a folder with mode `0o500` and calls `shutil.rmtree` on the parent. The command was `wsl -d MuseUbuntu1 -u nobody -e python3 /mnt/c/Users/422mi/AppData/Local/Temp/posix_rmtree_vrr2.py`, a byte-identical copy of the script. Output (`$V2/posix_rmtree.out`):

```
python 3.12.3 uid 65534 fd-functions True
type: PermissionError
str has key: True | filename: 'vbk-posixkey-0123456789abcdef.txt'
str: [Errno 13] Permission denied: '<KEY>.txt'
```

- On POSIX, `shutil.rmtree` takes `_rmtree_safe_fd`.
  - Python 3.12 runs `os.unlink(entry.name, dir_fd=topfd)` and then `onexc(os.unlink, fullname, err)` (`/usr/lib/python3.12/shutil.py:715-717`).
  - Python 3.11 runs the same unlink with `onerror` (`shutil.py:680-682`).
  - The default handler raises the original error, so the error names the *basename*, which holds the whole key.
- A test on Ubuntu must therefore keep the key in the file's own name, and the held folder must hold only that file. `rmtree` raises on the first entry it cannot unlink, and scandir order is not fixed.
- As root, permissions do not apply, so such a test is skipped as POSIX root, as `test_harness_compose_removal.py` already does.
- On win32, `_rmtree_unsafe` unlinks by full path. An open handle gives `[WinError 32]` with the full path.

### 2.4 Why `raise ... from None` is not enough

This was checked under `python -I`, with the same `PermissionError(13, 'Permission denied', 'vbk-KEY.txt')` raised in each case:

```
from error   cause=PermissionError(13, 'Permission denied') context=PermissionError(13, 'Permission denied') key_in_traceback=True
from None    cause=None context=PermissionError(13, 'Permission denied') key_in_traceback=False
after handler cause=None context=None key_in_traceback=False
```

`from None` hides the original from tracebacks, but `__context__` still holds it. The pack's `reachable` walks `__context__`, and test-plan.md:249 says the same about R-33. Only a raise after the handler leaves both links empty.

### 2.5 Severity

The finding breaks these weighted words and spec lines:

- **Ledger 3.** "The key is still passed only to the nine functions and still never reaches argv, files, `os.environ`, error messages or logs" (request.md:54). It is quoted again under "## D. Weighted words" (request.md:166).
- **§14 Never.** "Put a key in argv, a file, `os.environ`, an error, a log or a `repr`" (spec.md:1488).
- **INV-4.** It exempts only `result` and `diff` (spec.md:252).
- **The test plan's reading of "error".** It includes "any exception the refusal keeps as `__context__` or `__cause__`" (test-plan.md:224).

Compose attaches the unscrubbed `OSError` with `from error`, and the standard `logging.exception` prints it. So the key reaches "an error" and "a log".

No exemption applies:

- EC-71 and the INV-4 r3 ruling keep step output raw only in records (`result`, `diff`).
- T-3's residuals name only a reader opening a workspace file, and records (spec.md:1115).

Plausibility cannot lower the severity, because the spec itself anticipates both triggers:

- AC-15's setup has "stand-ins that echo the key into their answer and into a file they write", and its own test writes `f"{key_r}.txt"` (test_harness_compose_keys.py:423).
- EC-16's example is "on Windows a lingering child holds a file, or an antivirus locks one".

So the finding is a Blocker.

## 3. Class sweep

**Scope:**

- `vidbyte/harnesses/native/compose/*.py`
- `vidbyte/lib/dataclasses/native_compose.py` and `native_ensemble.py`
- `vidbyte/lib/util/json_text.py` and `secret_text.py`
- `ThreadComposeError` in `vidbyte/lib/errors/base.py`
- `RecordFieldValidator.require_template` (validation.py:98-99), because compose's templates reach it

**Method:**

- `grep` for every `except`, `finally`, `from error`, `from None`, logging, warnings and print.
- Each site was read, and each reachable one was probed on stand-ins (§2.2).
- `native_ensemble.py`, `secret_text.py` and `base.py` hold no handler.

| # | Site | Form | What the error or its chain can carry | Verdict | Evidence |
|---|---|---|---|---|---|
| 1 | git.py:215-217 `_folder` | `except OSError` then `raise ... from error` | `OSError` naming `tempfile.gettempdir()` plus compose's prefix and random part; no step or caller-argument text | clean in scope; fixed under the same rule | probe H: every flag False; proof: chain `['ThreadComposeError']` |
| 2 | git.py:224 `_delete` | `except FileNotFoundError: return` | nothing is raised | clean | read |
| 3 | git.py:226-228 `_delete` | `except OSError` then `raise ... from error` | `OSError` naming the first file `rmtree` could not delete, whose name a step chose | **LEAKS** (R-34) | probes A–G and J; reviewer's probe; WSL |
| 4 | git.py:135 `snapshot` | `finally:` `rmtree(..., ignore_errors=True)` | nothing is raised | clean | read |
| 5 | git.py:178 `remove_worktree` | `finally: await self._delete(folder)` | site 3's error, raised inside the `finally`; with git's own failure in flight, its `__context__` is that scrubbed `ThreadComposeError` | clean once site 3 is fixed; at HEAD the `OSError` sits between them | probe J: HEAD `[ThreadComposeError, PermissionError, ThreadComposeError]`, proof `[ThreadComposeError, ThreadComposeError]` with `[redacted]` |
| 6 | workspace.py:187-189 `_matching` | `except OSError` then `raise ... from error` | `OSError` naming the worktree plus the workspace path below the repository root. A key appears only if the caller names a folder after a key, a misplaced key that validation accepts | clean in scope (out-of-scope trigger); fixed under the same rule | probe I |
| 7 | workspace.py:136-142 `__aenter__` | `except BaseException:` removal under `contextlib.suppress(ThreadComposeError)`, then bare `raise` | the removal error is swallowed and the first error is raised again unchanged | clean | read |
| 8 | workspace.py:155-158 `__aexit__` | `except ThreadComposeError: if error is None: raise` | raises site 3's error again unchanged after a normal exit, and swallows it after a block that raised | clean itself; it carries site 3 to the caller | probes A–G |
| 9 | calls.py:64-65 `call` | `except asyncio.CancelledError: raise` | the same object | clean | read |
| 10 | calls.py:66-67 `call` | `except NativeThreadError as error: return StepOutcome(error=error)` | the base's own error object, unchanged (INV-29) | clean: compose adds no link | probe K: recorded chain equals a direct call's, `['NativeThreadError']` |
| 11 | calls.py:77-90 `fan_out` | `finally:` cancel and `settle`, then `raise error` outside any handler | a child's exception, whose context is its own task's | clean | probes D–F: one-element chains on the proof copy |
| 12 | calls.py:103-107 `settle` | `except asyncio.CancelledError:` wait, then `raise` | the cancel object | clean | read |
| 13 | calls.py:108-113 `settle` | `finally:` `task.exception()` for each task | reads every failure, so asyncio never logs "exception was never retrieved" with the chain | clean; it removes a log surface | read |
| 14 | chain.py:87 | `except ThreadComposeError as error:` attach the record, bare `raise` | the same object, with no new link | clean | read |
| 15 | verify.py:97 | the same | the same | clean | read; probes A–C |
| 16 | ensemble.py:112 | the same | the same | clean | read |
| 17 | ensemble.py:214 `_plan` | the same | the same | clean | read; probe E |
| 18 | selection.py:95 | the same | the same | clean | read; probe F |
| 19 | answers.py:129 `read` | `except (ValueError, TypeError, KeyError, ConfigurationError)`, returns the problem text | a string; no exception is kept | clean (its quoting is R-33's) | read |
| 20 | native_compose.py:135 `_probe` | `except ConfigurationError: return error`; `__post_init__` raises it outside the handler | R-33's pattern | clean | read |
| 21 | json_text.py:75-76 | `except RecursionError:` then `raise ValueError(...) from None` | `__context__` is a `RecursionError` with fixed interpreter text, and the `ValueError` ends as a string at site 19 | clean | `python -I`: `'maximum recursion depth exceeded while decoding a JSON array from a unicode string'`, key in message False |
| 22 | validation.py:98-99 `require_template` | `except ValueError:` then `raise ConfigurationError(...) from None` | `__context__` is the Formatter's `ValueError`, which quotes no template text | clean | `python -I`: `"Single '{' encountered in format string"`, `"expected '}' before end of string"`, `"unmatched '{' in format spec"`, key in message False |
| C1 | stored foreign exceptions | `StepOutcome.error` only (site 10) | the base's error (INV-29; R-29 and NG-1 for the base's own text) | clean | probe K |
| C2 | cross-task context | `fan_out`, `settle` and `DisposableWorktree._settled` (`task.result()`, workspace.py:179) | each task has its own handled-exception state | clean | probes D–F and J |
| C3 | logging, warnings, print | none in the swept files (grep: 0 hits) | none | clean | grep |
| C4 | `ThreadComposeError` (base.py) | no chaining code; the A003 packet attributes are scrubbed by `ComposeFailures.error` | none | clean | every probe: `packet=False` |

### Out of scope (and why)

- **A key the caller put into the workspace path or `TMP`.** It reaches sites 1 and 6 only as a misplaced key that validation accepts, which is out of scope by ruling. The fix still drops those chains.
- **`in_worktree` (scenario G).** It binds no key, and INV-4 protects bound keys only. The fix covers it anyway, because it is the same site.
- **Keys that EC-71 keeps raw in records.** After the fix, scenarios A and I keep a key only in `result` (A: `result.writer.diff`) or in `result` or `diff` (I). Both are accepted (INV-4 r3, T-3).
- **The base nine functions and hostkit.** Their own errors and chains belong to R-29 and NG-1. Compose records the base's errors unchanged (INV-29).
- **Python's `capture_locals` tracebacks.** They are not a default surface. Neither `traceback.format_exception` nor `logging.exception` prints locals.
- **The test-side gap.** The AC-15 file-name test reads only `str`, `args` and `vars`, and the EC-16 tests hold `lock.txt`. This gap has the same root cause, so it is part of R-34's fix (§5), not a separate row.

## 4. The proved fix

### 4.1 The rule and the diff

**One rule applies at every site where compose turns an `OSError` into a `ThreadComposeError`:** keep only `type(error).__name__` inside the handler, and build the observation and raise `ComposeFailures.error(...)` after the handler, with no `from`. This is the R-33 pattern, and it applies at git.py:217, git.py:228 and workspace.py:189. Each success path returns inside its `try`.

The fixed `_delete`, on the proof copy:

```python
    async def _delete(self, folder: Path) -> None:
        # Delete what is left of a worktree folder; a folder that cannot
        # be deleted is WORKTREE_FAILED, naming it. The OS error names
        # the file that stayed, which a step may have named after a
        # key, so only its type is kept and the error is raised after
        # the handler, where no __cause__ or __context__ holds it
        # (INV-4).
        try:
            await asyncio.to_thread(shutil.rmtree, folder)
            return
        except FileNotFoundError:
            return
        except OSError as error:
            error_type = type(error).__name__
        observation = native_compose.THREAD_COMPOSE_FOLDER_OBSERVATION.format(folder=folder, error_type=error_type)
        raise ComposeFailures.error(ThreadComposeProblem.WORKTREE_FAILED, self.workspace, observation, self.keys)
```

`_folder` and `_matching` change the same way.

- **Reference diff:** `$V2/proposed_fix.diff`, 2 files changed, 24 insertions and 12 deletions.
- It was made with `git diff` against the HEAD index copy, so it uses worktree-relative paths.
- `git -C <worktree> apply --check -v` printed `Checking patch vidbyte/harnesses/native/compose/git.py...`, then `Checking patch vidbyte/harnesses/native/compose/workspace.py...`, and passed. It was not applied, and `git status --short` showed the worktree untouched before `review.md` was edited.
- **Patch script:** `$V2/apply_fix.py <root>`. Every replacement must match exactly once. It was run only on `$V2/proof`, a `git -c core.autocrlf=false archive HEAD | tar -x` copy.

### 4.2 Header and narration edits (all in the diff)

1. **git.py header, line 8, WHAT NOT TO DO item 4.**
   - Before: "4. Do not let an OSError escape; folder failures are ThreadComposeError too."
   - After: "4. Do not let an OSError escape or chain it; a folder failure is a ThreadComposeError raised after its handler with only the error's type, because the OS text names files a step chose (INV-4)."
2. **workspace.py header, line 8, WHAT NOT TO DO.** Append "5. Do not chain an OSError to a ThreadComposeError; keep only its type and raise after the handler (INV-4)."
3. **The leaf comments.**
   - `_folder` gains "Only the OS error's type is kept, and the error is raised after the handler, so it chains no OS text (INV-4)."
   - `_delete` gains the five lines quoted in §4.1.
   - `_matching` gains "A failure keeps only the OS error's type and is raised after the handler, so it chains no OS text (INV-4)."
4. **What stays as it is.** No FUNCTION INVENTORY, KNOWN EDGE CASES or README change is needed. The inventory names the same leaves, and EC-16's edge-case text, "the error names its folder", still holds.

### 4.3 Gate results

| Gate | Proof copy (`$V2/proof`, fixed) | Control copy (`$V2/control`, HEAD) |
|---|---|---|
| My probe `test_s5v_rr2_chain.py` | `12 passed in 4.82s`; A–J `chain=False traceback=False logging=False`; chains `['ThreadComposeError']` (J: two scrubbed `ThreadComposeError`s); H `chained OSError text: []`; `pack es` True only for A and I (`result`/`diff`, EC-71) | `12 passed in 6.43s`; the HEAD flags of §2.2 |
| `test_s5v_rr2_attrs.py` (scenario A, attribute by attribute) | `1 passed in 1.59s`; `vars['result'] holds a key: True`, every other attribute False; `result.writer.diff holds the writer key: True`; `result.writer.result` and `result.verdicts` False; traceback text False; chain `['ThreadComposeError']` | not run |
| Compose pack `tests/features/harness_compose` | `385 passed in 74.02s` | 385 at HEAD (orchestrator gate) |
| `tests/features/harness_threads` (holds the INV-15 static literal policy) | `435 passed, 3 skipped in 53.63s` | `435 passed, 3 skipped in 52.86s` |
| `python lint/run.py` | `SDK-LINT: PASS` | `SDK-LINT: PASS`; output identical (`diff` empty) |
| `ruff check` (the two files) | `All checks passed!` | n/a |

The harness_threads skips on both copies are the Muse PATH lookup outside win32 (EC-29), the POSIX execute bit, and `origin/main is not available in this checkout`. The third one is the skip that an archive copy adds. The worktree gives 436 passed and 2 skipped (orchestrator gate).

Lint ran with `GIT_DIR=<repo>/.git/worktrees/vidbyte-sdk-native-thread-compose`, `GIT_WORK_TREE=<copy>`, `GIT_INDEX_FILE=<copy of the worktree index>` and `GIT_OPTIONAL_LOCKS=0`. Lint's only git call is `git ls-files -z`. Ratchets, identical on both copies: A001 642, A002 582 (base 703), S009 350, S051 259, S061 5 (base 6).

`ruff format --check` reports "2 files would be reformatted" on the unpatched copy too. The repository does not use ruff format.

### 4.4 Constraint checks

- **No new names, values or dependencies.** There is no new public name, constant text, record field, helper or dependency. The only new identifier is the local `error_type`, and the messages are unchanged, so the EC-16 assertions (`check_compose_error(... observations=[("folder", ...)])`, `git worktree prune`) still pass.
- **INV-15.** No literal was added (the static policy passes inside harness_threads).
- **AGENTS.md principle 1.** The three functions stay leaves that call no helper of their own class.
- **Narration and comment format.** The comments are plain English. No changed comment line is longer than 72 columns: `awk` over both files found none, and `py_compile` passes.
- **No pinned chain.** No test pins `__cause__`, as the unchanged 385 shows.

## 5. Missing tests (for the test author)

There is one confirmed site, git.py:228. The rows go best in `test_harness_compose_keys.py`, beside `test_git_text_and_file_names_that_hold_a_key_are_scrubbed_from_errors` (AC-15), because `reachable` and `error_surfaces` live there. The hold logic of `RemovalBlocker` (test_harness_compose_removal.py) can be copied inline or moved to the conftest with a file-name parameter.

### T1 (required): an EC-16 removal failure that names a reader's key-named file chains no OS error

**Setup:**

- Call `sandbox.make_repo()`, then set `key_w, key_o = pack.fresh_key("writer"), pack.fresh_key("reader")` (75 characters each).
- **The writer:** `steps.bind("opencode", label="writer", key=key_w, fake={"write_files": {"feature.txt": "feature\n"}})`.
- **The reader:** `steps.bind("opencode", label="v-held", key=key_o, fake={"mode": "hold", "write_files": {f"held-by-test/{key_o}.txt": "saved\n"}, "final_parts": [pack.verdict_json("approve")]})`. The stand-in saves the key-named file in its own worktree, as a step would.
- Start `api.compose.verify_with(writer, [reader], prompt=pack.PROMPT)` as a task.
- Wait until `sandbox.launches(label="v-held")` is non-empty, set `root = worktree_root(pack, sandbox.only_launch("v-held"))`, and wait until `root / "held-by-test" / f"{key_o}.txt"` exists.

**How the removal fails:**

- **win32:** `handle = file.open("a", encoding="utf-8")`. `rmtree` gets `[WinError 32]` naming the full path.
- **Ubuntu (non-root):** first assert that the folder holds only that file (`[p.name for p in folder.iterdir()] == [file.name]`). Then `folder.chmod(0o500)`. `rmtree` gets `[Errno 13]` naming the basename `<key_o>.txt`.
  - Skip as POSIX root: `sys.platform != "win32" and os.geteuid() == 0`.
  - Do not call `RemovalBlocker.hold()` as it is. Its `self.folder.mkdir()` fails when the stand-in already made the folder, and its `lock.txt` would be a second entry.
- Then call `sandbox.release()`, run `with pytest.raises(api.ThreadComposeError) as caught: await asyncio.wait_for(task, pack.WAIT_SECONDS)`, and read `registered, leftovers = sandbox.worktrees(), sandbox.leftovers()`.
- In `finally`, close the handle or `chmod(0o700)`, call `shutil.rmtree(root, ignore_errors=True)`, and settle the stand-ins and the leftover tasks.

**Expected (the existing EC-16 expectations):**

- `check_compose_error(error, problem="worktree_failed", workspace=sandbox.workspace, observations=[("folder", pack.path_spellings(root))])`
- `assert "git worktree prune" in error.next_step`
- `assert [a.value.decision.value for a in error.result.verdicts] == ["approve"]`
- `assert (registered, leftovers) == (1, [root.name])`

**New assertions:**

- `assert pack.leaks(error_surfaces(error), (key_w, key_o)) == []`
- `assert pack.leaks("".join(traceback.format_exception(error)), (key_w, key_o)) == []`, which is what `logging.exception` prints.

**Red and green:**

- At HEAD the row is red: probe B on the control copy gives `pack es=True` and `traceback=True`.
- With the fix it is green: probe B on the proof copy gives both False.
- This holds on win32 and on Ubuntu (§2.3).

**Do not place the file through the writer.** A writer-saved `<key>.txt` stays in `error.result.writer.diff` (EC-71; proof scenario A: `vars['result'] holds a key: True`). There, `pack.leaks(error_surfaces(error), keys)` is red even with the fix. The reviewer's suggested row has this problem. A writer-saved variant can only assert on the chain (`reachable(error)[1:]`) and on the traceback text.

### T2 (recommended): the same through `run_ensemble`

**Roster:**

- a Grok planner with `fake={"text": pack.plan_json([("ROLE-ONE", "IDENTITY-ONE"), ("ROLE-TWO", "IDENTITY-TWO")])}`
- a Grok fork proposer
- an opencode proposer `p-held` with `{"mode": "hold", "write_files": {f"held-by-test/{key_o}.txt": "saved\n"}, "final_parts": ["PROPOSAL-TWO: ..."]}`
- a Grok selector and a Grok implementer

**Hold and assertions:**

- Hold the file as in T1.
- Expected: `worktree_failed`, the plan kept (`error.result.plan.value is not None`), and no selector or implementer launch.
- New assertions: the same two `pack.leaks` checks over all bound keys.
- At HEAD the row is red (probe D). With the fix it is green.

### Optional guards for the rule at the two clean sites

- **G1 (git.py:217).** `monkeypatch.setattr(tempfile, "tempdir", str(a_file))`, then `verify_with`.
  - Expected: `git_failed` and no launch.
  - Assertion: `error.__cause__ is None and error.__context__ is None`.
  - At HEAD it is red: the chain holds `FileNotFoundError` on win32 and `NotADirectoryError` on POSIX.
- **G2 (workspace.py:189).** It is reachable only by patching `pathlib.Path.mkdir` to raise `FileExistsError` for the matching folder (my probe I). Its value is only to pin the rule, so the test author may skip it.

## 6. Spec record

**No record is required for scope.** §14 Never, ledger 3 and test-plan.md:224 already make the chained key a defect, and the fix changes no behavior that the spec states. **A record is recommended for traceability**, because the INV-4 bullet lists attributes and does not name the exception chain. R-33's after-handler rule was recorded the same way, in §17 grant (c). The proposed wording follows.

- **INV-4, third bullet (spec.md:252).**
  - Current: "  - the `ThreadComposeError` message and every attribute except `result` and `diff`: `details`, `safe_runtime_details`, `git_message`, `likely_cause`, `next_step` and the rest of the A003 packet;"
  - Proposed: "  - the `ThreadComposeError` message and every attribute except `result` and `diff`: `details`, `safe_runtime_details`, `git_message`, `likely_cause`, `next_step` and the rest of the A003 packet, and every exception its `__cause__` or `__context__` reaches, so a folder failure keeps only the `OSError`'s type (EC-16);"
- **§17 Implementation deviations, "Git failures." (spec.md:1595).**
  - Current: "- **Git failures.** A git timeout during a worktree command is `WORKTREE_FAILED`, and a failure to launch git is `GIT_UNAVAILABLE`. Removing a temporary index folder ignores errors."
  - Proposed: append " A folder that cannot be made or deleted raises its `ThreadComposeError` after the `OSError` handler with only the error's type, so the error chains no OS text, which can name a file a step named after a key (S5 re-review round 2, R-34)."
- **EC-16 (spec.md:527) needs no change.** Its outcome, "`ThreadComposeError(WORKTREE_FAILED)` naming the folder; its `result` holds the record so far; the next step names `git worktree prune`", holds on the proof copy.
- **Optional §17 revision row,** if the orchestrator records the change: "| r6 | 2026-10-20 | S1 spec (as-built record after S5 re-review round 2; not a review round) | R-34: INV-4 names the exception chain of a `ThreadComposeError`; §17 "Git failures." records that a folder failure keeps only the `OSError`'s type. No behavior, public name or record field changes |"

## 7. Files

All of these are in `$V2`:

- **Probes and outputs:**
  - `test_s5v_rr2_chain.py`, with `probe_head.out` (worktree), `probe_control.out` and `probe_proof.out`.
  - `test_s5v_rr2_attrs.py`, with `attrs_proof.out`.
  - `posix_rmtree.py`, with `posix_rmtree.out`.
- **Copies:**
  - `proof/` (fixed) and `control/` (HEAD), both full archive copies.
  - `index.copy`, `index.proof` and `index.control`, copies of the worktree index for the lint runs.
- **Fix:** `apply_fix.py` and `proposed_fix.diff`.
- **Gate outputs:** `pack_proof.out`, `threads_proof.out`, `threads_control.out`, `lint_proof.out` and `lint_control.out`.
- **Review edit:** `edit_review.py`, with `review.orig.md` (before) and `review.dry.md` (the dry run, byte-identical to the edited `review.md`).
