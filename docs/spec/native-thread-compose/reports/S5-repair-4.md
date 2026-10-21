# S5 repair, iteration 4 of 8 (R-34)

- **Stage:** S5 repair agent, iteration 4. The re-review cap is reached, so no reviewer sees this change. Only the frozen tests, the orchestrator's gate and remote CI check it.
- **Tree:** `feat/native-thread-compose`. Start `0f32a1ac`. The orchestrator's pipeline.md commits `bee8f422` and `c159f679` landed before this iteration's first commit. Code HEAD is `c5e40f82`, spec record `1511846c`, and the records commit sits on top.
- **Date:** 2026-10-20.
- **Platform:** win32, Python 3.11.0, git 2.49.0.windows.1, the pack's stand-ins only. No probe started the real grok or opencode, and `procs.py --kill` printed `stand-in or grandchild processes: []` after every process run.
- **Interruption:** an API rate limit stopped this iteration once, after the fix was applied and gated and before it was committed. Nothing was lost: the edits stayed unstaged and the orchestrator's interruption commit `c159f679` was made with `--only`.
- **Scratch:** `S4` below is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s5-4`. The gate outputs are in `S4/final/`.

## 1. Result

R-34 is fixed at `c5e40f82`, and the spec record is at `1511846c`. The fix is the verifier's reference diff, applied unchanged: 2 files, 24 insertions and 12 deletions. All four R-34 rows pass, every local gate passes, and both remote checks are green at `1511846c` (section 5).

## 2. The defect and its root cause

When a reader's worktree could not be removed (EC-16), `ComposeGit._delete` (git.py:228) raised its `WORKTREE_FAILED` inside the `OSError` handler with `raise ... from error`. `ComposeFailures.error` scrubbed the error it built. The chained `OSError` was never scrubbed, though, and it names the file `rmtree` could not delete, which a reader can name after its key. The key therefore reached `__cause__`, `__context__` and `traceback.format_exception(error)`, which is what `logging.exception` and an uncaught error print. This breaks ledger 3 ("never reaches … error messages or logs"), §14 Never, INV-4 and AC-15, read with test-plan.md:224.

**Root cause, in one line:** the handler kept the whole `OSError`. `from error` stored it as `__cause__`, and raising inside the handler stored it as `__context__`.

**Reproduced red at `0f32a1ac`** with `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose/test_harness_compose_keys.py -k "chains_no_os_error"` (`S4/red_head.out`):

```
E       AssertionError: INV-4: the error or its chain ['ThreadComposeError', 'PermissionError'] shows a key
E       AssertionError: INV-4: the error or its chain ['ThreadComposeError', 'PermissionError'] shows a key
E       AssertionError: the R-34 rule: GIT_FAILED chains ['FileNotFoundError']
E       AssertionError: the R-34 rule: WORKTREE_FAILED chains ['PermissionError']
4 failed, 47 deselected in 2.01s
```

## 3. The fix

**The rule.** It is the R-33 rule, applied at the three sites where compose turns an `OSError` into a `ThreadComposeError`:

- `ComposeGit._delete` (git.py:228), the leaking site;
- `ComposeGit._folder` (git.py:217);
- `DisposableWorktree._matching` (workspace.py:189).

At each site, only `type(error).__name__` is kept inside the handler. The observation is built, and `ComposeFailures.error(...)` is raised, after the handler, with no `from`. Each success path returns inside the `try`. After the fix:

```python
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

**What else changed.**

- git.py WHAT NOT TO DO item 4 now also forbids chaining an `OSError`.
- workspace.py WHAT NOT TO DO gains item 5.
- The three leaf comments say why the rule exists.

**What did not change:** no constant, message text, record field, public name, helper or literal. The only new identifier is the local `error_type`. The EC-16 record is unchanged: the two held-file rows still pin the folder observation, `git worktree prune`, the verdict, the plan, both proposals and the leftover folder.

**How the fix was applied.**

- `git apply --check -v` of `s5-verifier-rr2/proposed_fix.diff` passed.
- I then ran `git apply`.
- I compared the 36 changed lines of `git -c core.autocrlf=false diff -- vidbyte` with the reference diff's 36 changed lines: `cmp` reported them identical.

## 4. Hypotheses and attempts

1. **Not retried (known to fail): `raise ... from None`.** It still sets `__context__` (verifier §2.4, test-plan.md R-34 notes). The held-file rows walk both links, and the two folder rows read `__context__` directly.
2. **Chosen: the verifier's reference diff.** There is no smaller complete equivalent. Each site needs three things: the capture inside the handler, the raise moved after it, and a success return inside the `try`. The comment lines are the A001 header and `@intent`-style obligations of this repository.
3. **Considered, not coded:**
   - **`else: return` in place of a `return` inside the `try`.** The behaviour is the same, but it adds a line at each site and departs from the diff the verifier proved, which no reviewer will see.
   - **Fixing only `_delete`.** It is the only leaking site, but two of the four rows are guards for `_folder` and `_matching`, and the briefing asks for the uniform rule.
4. **Checked before applying.** `lint/mypy.ini` leaves mypy's optional `possibly-undefined` code off. `lint/ruff.toml` selects only TID251, and I001 comes from the command line. So a name bound only in a handler and a `return` inside a `try` trip nothing. Lint confirmed it: the count table is identical to iteration 3's (90 rows), with S009 at 350/350.
5. **Tooling trap (new): `git apply` and `core.autocrlf=true`.**
   - The system git config (`C:/Program Files/Git/etc/gitconfig`) sets `core.autocrlf=true`. `git apply` honoured it and rewrote both files as CRLF in the working tree; `git ls-files --eol` showed `i/lf w/crlf`.
   - The commit would still have been LF. But the awk 72-column check counts the trailing `\r`, and the sibling compose files are LF in the working tree.
   - I restored LF byte for byte before committing. `git diff --stat` stayed at +24/-12, and both files now show `i/lf w/lf`.
6. **Optional question: why did CI's Python 3.12 pass the two held-file rows before the fix?** It is answered from raw source:
   - **Runner versions.** The CI 39506184626 log prints `Successfully set up CPython (3.11.17)` and `Successfully set up CPython (3.12.15)`. WSL has 3.12.3.
   - **Source.** I fetched raw `Lib/shutil.py` at tags `v3.12.3`, `v3.12.15` and `v3.11.17` with `gh api -H "Accept: application/vnd.github.raw"`, into `S4/cpython-shutil/`. The files were only read, never run.
   - **The change.** The 3.12 branch took the iterative `rmtree` in `feb7870b46` (2024-06-01, "[3.12] GH-89727: Fix `shutil.rmtree()` recursion error on deep trees (GH-119808) (#119919)"), so every release from 3.12.4 on has it.
   - **What 3.12.15 does.** An unlink failure is caught by `except OSError as err: onexc(os.unlink, fullname, err)`. The default `onexc` is a bare `raise`, so the error escapes into the function's outer `except OSError as err:`. That handler runs `err.filename = path`, where `path` is the folder being walked (`<worktree>/held-by-test`), and calls `onexc(func, path, err)`, which raises it again. The chained `PermissionError` therefore named the folder, not `<key>.txt`, and no key reached the chain.
   - **What 3.11.17 and 3.12.3 do.** Both keep the recursive form. 3.11.17's unlink site is `onerror(os.unlink, fullname, sys.exc_info())`, and 3.12.3's is `onexc(os.unlink, fullname, err)`. Both raise the original error, which names the basename `<key>.txt`.
   - **Consequence.** On POSIX Python 3.12.4 or later, a held key-named file cannot show this leak; a key-named folder could. A regression at `_delete` is caught by the held-file rows on win32 and on the 3.11 leg, and by the guard rows' `__context__` checks on every leg only for the two folder sites. The fix removes the chain, so every row passes on every leg whatever `shutil` does.

## 5. Gates

All of these were run in this worktree in this iteration. Gates 1 to 9 ran at `1511846c`, whose code is `c5e40f82`.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| reproducer, after the fix | `pytest -q -p no:cacheprovider .../test_harness_compose_keys.py -k "chains_no_os_error"` | PASS (was 4 failed) | `4 passed, 47 deselected in 1.75s` |
| keys module | `pytest -q -p no:cacheprovider .../test_harness_compose_keys.py` | PASS | `51 passed in 4.97s` |
| 1 lint | `python lint/run.py` | PASS; the count table is identical to iteration 3's (90 rows), with S009 350/350, A001 642, A007 255, C008 45, S039 5 and S061 5 | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline`<br>`S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all`<br>`SDK-LINT: PASS` |
| 2 ratchets | ruff I001 / TID251 | PASS (223 / 5) | `Found 223 errors.`<br>``[*] 223 fixable with the `--fix` option.``<br>`Found 5 errors.` |
| 3 semgrep | `--test`, then `scan --error` | PASS | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` (exit 0) |
| 4 new tests | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` | PASS (was 4 failed) | `389 passed in 53.09s` |
| 5 base pack | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` | PASS | `436 passed, 2 skipped in 44.67s` |
| 6 source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS; iteration 3's 6026 plus the 4 rows | `================ 6030 passed, 16 skipped in 140.02s (0:02:20) =================`<br>`CI passed.` |
| 7 package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package --dist-dir S4/final/dist-5` | PASS | `No broken requirements found.`<br>`Installed vidbyte-sdk 0.3.0 passed smoke checks.`<br>`CI passed.` |
| 8 AC-21 wheel half | `wheel-venv-5/Scripts/python.exe -I s3/check_wheel_prompts.py <worktree>`, run from `S4/final/wheel-run-5` with the briefing's copy recipe | PASS | `installed vidbyte: ...\s5-4\final\wheel-venv-5\Lib\site-packages\vidbyte\__init__.py (outside the checkout: True)`<br>`fixed combinations: 17, longest planner = 8304 chars, over 12000: {}`<br>`AC-21 WHEEL HALF: PASS` |
| 9 comment width | awk over git.py and workspace.py | PASS | `vidbyte/harnesses/native/compose/git.py over72=0`<br>`vidbyte/harnesses/native/compose/workspace.py over72=0` |
| frozen tests | `git diff bfd2b2c4..HEAD --stat -- tests` | PASS | empty |
| 10 remote: Static policy | run 39531298277 at `1511846c` | PASS; watch exit 0 | `1/1: ✓ All tests passed`<br>`Ran 1 rule on 977 files: 0 findings.` |
| 10 remote: CI | run 39531295940 at `1511846c` | PASS: Source / Python 3.11, Source / Python 3.12 and Package; watch exit 0 | 3.11 (CPython 3.11.17, git 2.55.0): `================= 5990 passed, 56 skipped in 102.83s (0:01:42) =================`, then `CI passed.`<br>3.12 (CPython 3.12.15): `========== 5990 passed, 56 skipped, 19 warnings in 145.59s (0:02:25) ===========`, then `CI passed.`<br>Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.`, then `CI passed.` |

The remote totals are iteration 3's 5986 plus the 4 R-34 rows on both legs, and the skips are unchanged at 56, so the two held-file rows ran on the non-root runner instead of skipping. Neither known remote flake occurred, so nothing was rerun. Both watch exit codes were captured before any pipe (`S4/final/remote-ci-watch.txt` and `remote-static-watch.txt` end `exit=0`).

## 6. Independent evidence beyond the frozen pack

- **The verifier's probe.** I ran `s5-verifier-rr2/test_s5v_rr2_chain.py` on the committed tree, with the pack's conftest as a plugin. It gave `12 passed in 30.42s` (`S4/probe_fixed.out`), and it matches the verifier's proof copy line for line:
  - A to J print `chain=False traceback=False logging=False`.
  - Every chain is `['ThreadComposeError']`. J's two links are both scrubbed `ThreadComposeError`s.
  - `pack error_surfaces` is True only for A and I. In those two the key stays in `result` or `diff`, which EC-71 keeps raw.
  - K's recorded chain equals a direct call's, `['NativeThreadError']`.
- **No other chaining site is left.** `grep -rn -E "from error|from err\b|__cause__|OSError"` over the compose sources, the two compose dataclass modules, `secret_text.py`, `json_text.py` and `vidbyte/harnesses/README.md` finds no `from error`. The only `except OSError` handlers left are the three fixed sites, plus the new comment.

## 7. The spec record

There is one docs commit, `1511846c`. It changes exactly spec.md line 1595 (1 insertion, 1 deletion), and the file stays CRLF (1627 CRLF line ends, no bare LF).

- **Before:** `- **Git failures.** A git timeout during a worktree command is `` `WORKTREE_FAILED` ``, and a failure to launch git is `` `GIT_UNAVAILABLE` ``. Removing a temporary index folder ignores errors.`
- **After:** `- **Git failures.** A git timeout during a worktree command is `` `WORKTREE_FAILED` ``, and a failure to launch git is `` `GIT_UNAVAILABLE` ``. Removing a temporary index folder ignores errors. A folder that cannot be made or deleted raises its `` `ThreadComposeError` `` after the `` `OSError` `` handler with only the error's type, so the error chains no OS text, which can name a file a step named after a key (S5 re-review round 2, R-34).`

INV-4 and every other passage are unchanged, as the briefing ruled.

## 8. Commits

| SHA | Commit |
|---|---|
| c5e40f82 | fix(compose): raise folder failures after the OSError handler, chaining no OS text [R-34] |
| 1511846c | docs(spec): record the R-34 rule for native-thread-compose |
| the records commit | docs(spec): verify-log iteration 4 for native-thread-compose. It carries the review.md R-34 status (`fixed @c5e40f82 (spec record @1511846c)`), the verify-log entry with its two refreshed gate-table rows, and this report. |

## 9. Still open

None. R-34 is fixed, and every gate is green at code HEAD `c5e40f82`, through `1511846c`, locally and remotely. No confirmed finding is open. The records commit changes only files under `docs/spec/native-thread-compose/`. R-24 to R-31 stay follow-ups outside this loop.

## 10. Notes for the next agent

- **Line endings.** The system git config sets `core.autocrlf=true`, so `git apply` rewrites the files it applies as CRLF in the working tree. Check `git ls-files --eol` afterwards, or use `s5-2/apply_edits.py`, which keeps each file's ending.
- **What each CI leg can catch.** The runner uses CPython 3.11.17 and 3.12.15 and git 2.55.0. On POSIX Python 3.12.4 or later, `rmtree` reports the folder it was walking, not the file it could not unlink. A regression at `_delete` therefore shows through the held-file rows only on win32 and on the 3.11 leg. The two folder rows read `__context__` and `__cause__` directly, so they catch their own sites on every leg.
- **The runner image.** The runs carry the annotation "The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026". setup-python pins the Python minor versions, but the image's git can change.
- **A new folder site.** Any new place where compose turns an `OSError` into a `ThreadComposeError` needs the same shape (capture the type, raise after the handler, no `from`). It also needs a row asserting that the error chains nothing; the keys module's COMMON MODIFICATION PATTERNS says so.
