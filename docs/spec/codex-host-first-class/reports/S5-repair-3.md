# S5 repair, iteration 3 of 8: codex-host-first-class

Branch `feat/codex-host-first-class`, start `2bdb5e95`, the only source commit `bd89e5b8`. PR #1181 is still a draft; nothing touched it apart from the push. S2_HEAD is `2bdb5e95`, and `git diff 2bdb5e95..HEAD -- tests` is empty.

## Outcome

R-RR2-1 is fixed. It was the one open item: a Minor from re-review round 2, which otherwise ruled SOUND. The fix is one token in the record's handler, plus the comment beside it and one header clause, so 5 lines added and 3 removed in one file.

No test, `lint/` file, baseline, `validation.py`, `spec.md`, `REPO_MAP.md` or README was touched. The only red gate is the inherited `harness_threads` surface test, and this iteration re-proved at the merge-base that it is inherited.

## Gate matrix

Every row was run in this worktree in this iteration, at `bd89e5b8`. `V` is the `venv-codex163` interpreter.

| Gate | Result | Final lines |
|---|---|---|
| new tests: `PYTHONPATH=$(pwd) "$V" -m unittest <the 2 R-RR2-1 ids>` | PASS (red at `2bdb5e95`: `FAILED (errors=4)`) | `Ran 2 tests in 0.378s` · `OK` |
| record, worktree and input modules (pytest) | PASS | `65 passed in 6.95s` (63 before, plus the 2 new) |
| area tests | PASS except the inherited failure | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 1306 passed, 3 skipped in 82.65s (0:01:22)` |
| inherited failure at merge-base `6f5a7310` (`git archive` extract, `GIT_DIR` set) | FAILS there too, so inherited | `E       AssertionError: assert 167 == 120` · `1 failed in 1.67s` |
| lint: `PYTHONIOENCODING=utf-8 "$V" lint/run.py` | PASS: rc 0, nothing REGRESSED or ERRORED; C021 CLEAN; S008 19/19; A001 642/642 | `A002 IMPROVED 703 -> 582. …` · `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| ruff on the touched file (extra) | PASS | `All checks passed!` |
| semgrep-core, every `.semgrep/*.yml` rule | PASS | touched file: `rules=1 files=1 findings=0 errors=0` · all 38 slice files: `rules=1 files=38 findings=0 errors=0` · sanity on the rule's own fixture: `findings=2 errors=0` |
| 72-column comments (38 slice files, CR stripped) | PASS | no output |
| line ceilings | PASS | `codex_host_inputs.py` 785/900 · host.py 786/900 · wire.py 839/840 · `lib/dataclasses/codex_host.py` 891/900 |
| test contract: `git diff 2bdb5e95..HEAD -- tests \| wc -l` | PASS | `0` |
| full gate, source stage (run alone) | PASS except the inherited failure; the embedded lint printed `SDK-LINT: PASS` | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6837 passed, 27 skipped in 138.01s (0:02:18) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-codex-host-first-class).` |
| full gate, package stage (run alone, no PYTHONPATH) | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote checks: `gh pr checks …/pull/1181` | 0/0 (none configured; every workflow is `workflow_dispatch` only) | `no checks reported on the 'feat/codex-host-first-class' branch` |

## Per finding

### R-RR2-1 (Minor): fixed @bd89e5b8

**Reproduced first.** At `2bdb5e95`, `"$V" -m unittest` on the two S2 ids gave four errors, each `TypeError: expected NonPathFspath.__fspath__() to return str or bytes, not int` (or `not NoneType`), ending `FAILED (errors=4)`.

**Root cause.** `CodexWorktreeRequest.__post_init__` (`vidbyte/lib/dataclasses/codex_host_inputs.py:589-591`) wraps `RecordFieldValidator.require_directory(RecordFieldConverter.to_path(...))` in `except (ConfigurationError, OSError)`. `to_path` (`vidbyte/lib/dataclasses/validation.py:198`) calls `os.fspath`, which raises `TypeError` when `__fspath__` returns neither str nor bytes. Iteration 2 claimed that `to_path` raises only `ConfigurationError`; that claim was false.

**Only `os.fspath` can raise `TypeError` inside the `try`.** This was checked by reading each call:
- `isinstance` against `(str, os.PathLike)`;
- `os.fspath`;
- `Path(str)`;
- `require_directory`'s `isinstance`, `is_absolute` and `is_dir`, where `is_dir` swallows `ValueError`, and its `OSError` was caught by R-RR1.

A bytes result reaches `to_path`'s own `isinstance(text, str)` refusal.

**The change** (one commit, `fix(codex-host): refuse a non-path __fspath__ worktree repository as the repository field [R-RR2-1]`):
```python
        except (ConfigurationError, OSError, TypeError):
            # A folder the system will not let this process inspect is
            # refused the same way, without the error's text, which
            # holds the absolute path. So is a path object whose
            # __fspath__ returns neither str nor bytes, which os.fspath
            # rejects with a TypeError (first-class INV-2).
```
The header's KNOWN EDGE CASES now says "one whose stat the system refuses, or whose __fspath__ returns neither str nor bytes, gets the same refusal". The refusal is unchanged: §9.1 row 9's `CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE`, `details={"field": "repository"}` and `from None`.

**The alternatives, weighed before writing.** None had been tried before.
1. **Chosen:** widen the record's tuple. It is §12.3 row 9 and one token, and the briefing, the reviewer and the S2 author all agree on it.
2. **Rejected:** map the error in `RecordFieldConverter.to_path`. That is the root, but `validation.py` is outside §12.3 and on the must-not list, and the change would shift behaviour for `native_threads.py:120` and `:146`.
3. **Rejected:** pre-check `__fspath__`'s result in the record. It would be a second converter rule beside the shared one.

**Evidence the fix is pinned.** Each mutant was applied in place after the commit and restored with `git checkout`. Afterwards `git diff HEAD --quiet` was clean and the file was still CRLF.

| Mutant | Result |
|---|---|
| drop `TypeError` (revert) | `FAILED (errors=4)` on the 2 R-RR2-1 ids |
| `as exc` … `from exc` (chained) | `FAILED (failures=4)` |
| `(ConfigurationError, TypeError)`, dropping `OSError` | `2 failed, 58 passed` over records and worktree, from the R-RR1 rows. So R-RR1's pin still holds. |

**Independent probe** (inline script, not S2's tests). It gave `__fspath__` each of these and printed what escaped `CodexWorktreeRequest`:

| `__fspath__` | Result |
|---|---|
| returns int | `ConfigurationError details={'field': 'repository'} cause=None suppress=True` |
| returns None | the same |
| returns float | the same |
| returns a list | the same |
| returns bytes | the same |
| raises `TypeError` | the same |
| raises `PermissionError` carrying a path | the same |
| raises `ValueError` | `ESCAPED ValueError: v` (see OPEN ITEMS) |

## Inherited failure

The failure is `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`. It was re-run this iteration from a `git archive` extract of merge-base `6f5a7310`, with `PYTHONPATH` set to that extract and `GIT_DIR` set to this worktree's git dir. Result: `E       AssertionError: assert 167 == 120`, `1 failed in 1.67s`, the same as on the branch.

Iteration 2's warning still applies: an extract without `GIT_DIR` passes vacuously, because `optional_merge_base()` returns early.

## Test changes proposed

None.

## Findings believed wrong

None. R-RR2-1 reproduced exactly as the re-review described it.

## Still open, and the next moves

- **No confirmed finding is open, and no gate is red** apart from the inherited failure.
- **An observation, not a finding, and out of scope by the briefing** ("Fix R-RR2-1 and nothing else").
  - **Where.** `vidbyte/lib/dataclasses/codex_host_inputs.py:591`.
  - **What.** A caller's own `__fspath__` that raises something other than `OSError` or `TypeError`, such as `ValueError`, `KeyError` or `AttributeError`, still propagates out of the record.
  - **Why it is probably intended.** This is the caller's own code raising, not a failure of the SDK. CPython's `open()` and `Path()` propagate it the same way. The record has never mapped it: before R-RR1 it did not even map a caller-raised `OSError`.
  - **What decides it.** INV-2 names `KeyError` and `AttributeError` without saying whose code raised them. If the orchestrator reads INV-2 as covering exceptions raised by the caller's own code, the smallest fix is `except Exception:` at the same line. That is a policy choice for the spec author, not this iteration.
- **Follow-ups, unchanged.**
  - One `validation.py` PR: `RecordFieldValidator.require_directory` maps a refused stat, and `RecordFieldConverter.to_path` maps `os.fspath`'s `TypeError`. That closes `native_threads.py:120` and `:146` too.
  - R-RR2's shared `_CodexHostTool` reset helper.
  - m-6 and m-7.
