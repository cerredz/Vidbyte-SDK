# S5 repair, iteration 2 of 8: codex-host-first-class

Branch `feat/codex-host-first-class`, start `64532571`, last source commit `819eed3e`. PR #1181 (draft, untouched apart from the push). S2_HEAD is `d11c5d9d`, and `git diff d11c5d9d..HEAD -- tests` is empty.

## Outcome

Both open items from re-review round 1 are closed at their roots, with the smallest change each:
- R-RR1 (Blocker) is one token plus a comment in the record;
- R-RR2 (Minor) is the comment half only.

R-RR3 was already closed in spec r8, and the R-RR2 helper is a follow-up by orchestrator decision. No test, lint file, baseline, `validation.py`, `spec.md`, `REPO_MAP.md` or harness README was touched. The only red gate is the inherited `harness_threads` surface test. This iteration re-proved that it is inherited, with a check that is faithful to the code (see "Inherited failure").

## Gate matrix

All rows were run in this worktree in this iteration, at `819eed3e`.

| Gate | Result | Final lines |
|---|---|---|
| new tests: the 2 S2 R-RR1 rows (6 subtests), `"$V" -m unittest <ids>` | PASS (red at `64532571`: `FAILED (errors=6)`) | `Ran 2 tests in 0.489s` · `OK` |
| record, worktree and input modules (pytest) | PASS | `63 passed in 6.08s` |
| feature tools (R-RR2's file) | PASS | `19 passed in 1.42s` |
| area tests | PASS except the inherited failure | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 1304 passed, 3 skipped in 83.80s (0:01:23)` |
| inherited failure at merge-base `6f5a7310` | fails there too | `E       AssertionError: assert 167 == 120` · `1 failed in 0.91s` |
| lint `PYTHONIOENCODING=utf-8 "$V" lint/run.py` | PASS: nothing REGRESSED or ERRORED, C021 CLEAN, S008 19/19 | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| semgrep-core, each rule × each file | PASS | 2 touched files: `rules=1 files=2 findings=0 errors=0`. All 38 `vidbyte/*.py` changed since `a7730107`: `rules=1 files=38 findings=0 errors=0`. The rule's fixture gives `findings=2 errors=0`. |
| 72-column comments over those 38 files | PASS | no output |
| line ceilings | PASS | `codex_host_inputs.py` 783/900 · `thread_actions.py` 317/600 · host.py 786/900 · wire.py 839/840 · `lib/dataclasses/codex_host.py` 891/900 |
| test contract `git diff d11c5d9d..HEAD -- tests \| wc -l` | PASS | `0` |
| full gate, source stage (alone) | PASS except the inherited failure (its embedded lint printed `SDK-LINT: PASS`) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6835 passed, 27 skipped in 140.21s (0:02:20) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-codex-host-first-class).` |
| full gate, package stage (alone, no PYTHONPATH) | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote checks | none configured (workflows are `workflow_dispatch` only) | `no checks reported on the 'feat/codex-host-first-class' branch` |

## Per finding

### R-RR1 (Blocker): fixed @2e076b36
- **Reproduced.** `"$V" -m unittest` on the two S2 ids gave `FAILED (errors=6)`, each a raw `PermissionError: [Errno 13] Permission denied: 'C:\\…\\repo-pathcanary5e13'` or `OSError: [Errno 38] File name too long: '…'`. Both quote the absolute path.
- **Root cause.** `CodexWorktreeRequest.__post_init__` (`vidbyte/lib/dataclasses/codex_host_inputs.py:589-592` at `64532571`) catches only `ConfigurationError` around `RecordFieldValidator.require_directory(...)`. Its `Path.is_dir()` re-raises a refused stat on Python 3.11.
- **What else can raise there.** `to_path` raises only `ConfigurationError`, and `is_dir` returns False on `ValueError` (Python ≥ 3.8). So `OSError` is the only other type that can escape.
- **The change.**
  - `except (ConfigurationError, OSError):`, still raising `ConfigurationError(CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE, details={"field": "repository"}) from None`.
  - A 3-line comment inside the `except`, in the style of R-1's handler at `thread_methods.py:173-175`.
  - One clause in the header's KNOWN EDGE CASES.
  - The file stays CRLF in the working copy and LF in the index (`core.autocrlf=true`), and the diff is `5 insertions(+), 2 deletions(-)`.
- **Alternatives weighed** (the verify-log has the reasons):
  - widening `require_directory` in `validation.py`, which is outside §12.3 and on the must-not list;
  - building the record inside R-1's `try`, which gives the wrong error kind and message, and the wrong order;
  - an `os.path.isdir` pre-check, which duplicates the shared validator.
- **Independent proof** (revert mutants, applied in place and restored):
  - catching only `PermissionError` gives `FAILED (errors=3)`;
  - chaining `from exc` gives `FAILED (failures=6)`.
- **Briefing correction.** The briefing gives this module a 600-line ceiling. Spec NFR-1 says "the `codex_host_inputs` module stays under 900", and the module was already 780 lines, so 900 is the real ceiling.

### R-RR2 (Minor): comment fixed @819eed3e; helper is a follow-up
- `ContinueCodexThreadTool._continue_defaults` (`threads.py:204-216`) clears a hand-written list and reads no table. The `_side_chat_defaults` comment now says "read from the host's own table as the resume tool does", re-flowed within 72 columns.
- The module header's "as the continue and resume tools reset theirs" is true (both reset), so it is unchanged.
- The line numbers the re-review cites (`:118-119`) are off by about 8. The wrong clause was at `:110-111` in `64532571`.
- The commit type is `docs(codex-host)`, following iteration 1's convention for changes that do not change behaviour.
- The shared `_CodexHostTool` reset helper in `_base.py` is not built (orchestrator decision), and it is recorded as `follow-up` in `review.md`.

### R-RR3 (Minor): fixed @2d0f5216 (spec r8)
Recorded in `review.md` only.

## Inherited failure

`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` asserts `len(main_members) == 120`. `main_members` is parsed from `git show <merge-base>:vidbyte/lib/enums/failure.py`, so the result depends only on the merge-base commit, never on this branch.
- **A trap for the next agent.** A plain `git archive` extract of `6f5a7310` PASSES the test, but vacuously: `optional_merge_base()` finds no repository and returns early.
- **The faithful check.** Run from the same extract with `GIT_DIR` set to this worktree's git dir (read-only git use). It gives `E       AssertionError: assert 167 == 120` · `1 failed in 0.91s`, identical to the branch.

## Test changes proposed
None.

## Findings believed wrong
None. The re-review's line references for R-RR2 are slightly off, but its claim holds.

## Still open, and the next moves
- **No confirmed finding is open.**
- **Follow-ups**, none in this PR's scope:
  - R-RR2's shared reset helper;
  - m-6 and m-7.
- **One new follow-up.** `RecordFieldValidator.require_directory` is the canonical home for "a refused stat is not a directory".
  - By reading only (not probed), `vidbyte/lib/dataclasses/native_threads.py:120` and `:146` call it with no `OSError` handling, so they have the same raw-`OSError` path.
  - Fixing it in the validator would close both, and it would make this iteration's record-level handler redundant but harmless.
  - It needs its own PR, because `validation.py` is outside §12.3.
