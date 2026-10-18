LENS: re-review round 2 (conformance + conventions + engineering, focused on the iteration-2 repair diff)
VERDICT: SOUND — R-RR1 is closed at the record boundary and no `OSError` path is left from `create_codex_worktree` to git. R-RR2's comment is now true. Spec r7 and r8 quote the code exactly, and nothing regressed. One Minor remains: an INV-2 corner case from S3 that the implementer's root-cause claim overlooked.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **The R-RR1 fix is in the right place.** It is at the record boundary (`codex_host_inputs.py:591-595`). It keeps §9.1 row 9's exact message, `details={"field": "repository"}` and `from None`, so the host path, the order (record before root and git) and every existing refusal are unchanged.
  - The fix is pinned. Five independent in-memory mutants are each killed by S2's two new rows, 6 of 6 subtests in each run: REVERT, PERMISSION-ONLY, CHAINED, NO-DETAILS and RAW-TEXT.
  - A probe of 11 real, unpatched repository values shows no leak.
- **The host path to git has no other way for an `OSError` to escape.**
  - `Path.home()`, `target.exists()` and `root.mkdir` sit inside R-1's `except (OSError, RuntimeError)` (`thread_methods.py:166-176`).
  - `GitWorktreeSpec` does no I/O (`process.py:115-123`).
  - `CliRunner.launch` turns `FileNotFoundError`, `PermissionError` and `(OSError, ValueError)` into a `launch_failure` (`runner.py:294-303`), and `_feed_stdin` and `_drain` suppress `OSError` (`runner.py:328`, `:340`).
- **The R-RR2 comment is now accurate and agrees with the spec.**
  - The side chat reads only `CODEX_HOST_REJECTED_FIELDS[SIDE_CHAT]`, which is exactly what its record refuses (`codex_host_inputs.py:572`, `:102-111`).
  - The resume tool reads the host's tables (`skill_functions.py:326`).
  - The continue tool's hand-written list (`threads.py:209-216`) equals `CODEX_HOST_REJECTED_FIELDS[CONTINUE_CODEX_THREAD]` (`constants/codex_host.py:153-162`). So the header's "as the continue and resume tools reset theirs" and D-22/INV-43's "as the continue and resume tools do for their rows" both stay true.
- **The diff is small and stays in its lane.** It touches 2 files, both §12.3 rows (9 and 34): +10/-7, no new import, symbol or literal. Both new comments pass comment-format's 72-column check. Ceilings are 783/900 and 317/600. `lint/` is untouched and lint has no REGRESSED rule. The only test change since ec17d5ce is S2's 4de2c91d (additions), and `git diff d11c5d9d HEAD -- tests` is 0 lines.

FINDINGS (ranked, most severe first, max 15)
R-RR2-1 [Minor] [conformance + engineering] vidbyte/lib/dataclasses/codex_host_inputs.py:589-595 (root: vidbyte/lib/dataclasses/validation.py:198) — `create_codex_worktree` still lets a raw `TypeError` escape for an `os.PathLike` whose `__fspath__` returns a non-path. The implementer's claim that "`to_path` raises only `ConfigurationError`" is therefore false, and INV-2's "No … `TypeError` … ever reaches the caller" fails on this one path.
  Evidence:
  - Code: `to_path` runs `text = os.fspath(value) if isinstance(value, (str, os.PathLike)) else None` (validation.py:198). The record's `try` catches only `(ConfigurationError, OSError)` (codex_host_inputs.py:591).
  - Repair report S5-repair-2.md:38 and the verify-log say: "`to_path` raises only `ConfigurationError` … So `OSError` is the only other type that can escape."
  - Probe: `class P: def __fspath__(self): return 5`, then `CodexWorktreeRequest(repository=P(), branch='feat/x')`. Output: `TypeError expected P.__fspath__() to return str or bytes, not int`.
  Failure:
  - **What happens.** Caller input whose `__fspath__` returns an int (or any non-str/bytes) produces a raw `TypeError` from `create_codex_worktree` instead of INV-1's `ConfigurationError` naming `repository`.
  - **Why Minor and not Blocker, although INV-2's weighted word "ever" is broken.**
    - Only an object that breaks Python's own `os.PathLike` protocol reaches this path. A type checker rejects it against `str | Path`, and CPython's `open()` and `Path()` raise the same `TypeError` for it.
    - No path or other data leaks.
    - It dates from S3; it is not a regression from this repair.
  Smallest fix:
  - **In scope.** Add `TypeError` to the record's tuple, `except (ConfigurationError, OSError, TypeError):` (codex_host_inputs.py:591). Inside that `try`, only `os.fspath` can raise `TypeError`.
  - **Root.** Map `os.fspath`'s `TypeError` to the `ConfigurationError` in `RecordFieldConverter.to_path`. This is `validation.py`, outside §12.3, so it fits the already-logged `require_directory` follow-up PR.
  Spec IDs: INV-2, INV-1

VERIFIED CLAIMS:
- **R-RR1: CLOSED.**
  - **Mutants.** My in-memory runner (`scratchpad/s5-rereview-2/rr2_mutant.py`, which edits no file) gave:

    | Mutant | pytest | unittest (the 2 ids) |
    |---|---|---|
    | NONE | 58 passed | — |
    | REVERT (= ec17d5ce code) | 2 failed | `errors 6` |
    | PERMISSION-ONLY | 2 failed | `errors 3` |
    | CHAINED (`from exc`) | 2 failed | `failures 6` |
    | NO-DETAILS | 4 failed | — |
    | RAW-TEXT | 4 failed | — |

    This independently reproduces the implementer's `errors=6`, `errors=3` and `failures=6`.
  - **Real-path probe.** 11 values, unpatched (`probe_real_paths.py`): a 300-character component, a deep path, a NUL byte, a lone surrogate, `CON`, a relative path, bytes, a PathLike raising `PermissionError` with a path, a PathLike returning bytes, an existing file, and an existing folder.
    - All but the folder give `ConfigurationError details={'field': 'repository'} cause=None suppress=True`, with no path text.
    - The existing folder is ACCEPTED.
  - **Other `OSError` sources in the record:** none. `is_dir` (now caught) is the only I/O, and a caller's own `__fspath__` `OSError` is caught too.
  - **On the host path to git:** none (see bullet 2 above).
  - **Not an `OSError`, by design.** If the folder changes between the record and git, git exits nonzero, and its first stderr line goes into `CODEX_HOST_WORKTREE_FAILED_MESSAGE`. INV-29 names it "the one message that quotes stderr".
  - **Only residual:** R-RR2-1 (a `TypeError`, not an `OSError`).
  - **Other Python versions.** Python 3.13's stdlib re-raises the same way (`Python313/Lib/pathlib/_abc.py:460-468`; `_local.Path` has no override), so the fix matters there too. `refused_stat`'s patch of `Path.stat` is faithful on 3.11 (`Python311/Lib/pathlib.py:1245-1259`) and on 3.13. The CI matrix is 3.11 and 3.12 (`.github/workflows/ci.yml:21-23`).
- **R-RR2 (comment half): CLOSED.** The comment at `thread_actions.py:109-114` now says "read from the host's own table as the resume tool does", which is true, as are its other sentences (the narrowing list matches the `replace` calls at `:120-131`). The header's ARCHITECTURE NOTE ("reset theirs") is also true. The helper half is a follow-up, as decided.
- **r7 (deviation 5): MATCHES.**
  - `run_codex_plan` passes `CODEX_COLLABORATION_MODE_LIST_METHOD = "collaborationMode/list"` (`settings_methods.py:133`, `constants/codex_host.py:49`).
  - The mode literal `"collaboration_mode"` is at `preflight.py:97`.
  - `list_codex_child_threads` passes `self._feature_params.child_filter_key(listing)` (`thread_methods.py:345`), which returns `"ancestorThreadId" if request.descendants else "parentThreadId"` (`feature_wire.py:239-243`). That is the same key the params send (`:235`).
  - Every other gate passes its wire method constant. Commit 2aa6eb0b exists and touched exactly those files.
- **r8 (INV-20 and D-39): MATCHES.**
  - The quoted expression is character-for-character `turn_stream.py:247`.
  - The loop guard `while self._events and self._fits_alone(size) and not self._fits(size)` (`:145`), followed by `if self._fits(size)` (`:147`), drops an oversize event without dropping older events.
  - "Both character bounds on an attached log, the per-turn bound only when never attached" is the `self._charge is None or …` clause.
  - EC-19's test `test_an_oversize_event_costs_a_lagging_subscriber_only_its_own_gap` passes (27 passed in the `-k` run). Commit f19ff74a exists.
- **Implementer claims, each checked:**
  - "Red at 64532571: FAILED (errors=6)": held (REVERT mutant).
  - "File stays 783/900": held.
  - "Ceilings host 786, wire 839, lib codex_host 891": held.
  - "`git diff d11c5d9d..HEAD -- tests` is 0": held, at HEAD 037ad952 too.
  - "72-column comments pass": held on both touched files.
  - "to_path raises only ConfigurationError": did NOT hold (R-RR2-1).
- **Spec and review bookkeeping.** review.md rows: R-RR1 `fixed @2e076b36`; R-RR2 `comment: fixed @819eed3e`, helper a follow-up; R-RR3 `fixed @2d0f5216`. Spec header says `revision: 8`, and the §17 r7 and r8 rows plus the §16 S5-1 and S5-2 rows are present.
- **Spec §4 (AC-1): not run**, because it needs the `codex` binary (briefing §6). Its imports resolve, its records build, and the signatures it calls match the code. The repair touches no code on its path.
- **Area run:** `1 failed, 1304 passed, 3 skipped in 87.90s (0:01:27)`. The only failure is the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`).
- **Lint:** `SDK-LINT: PASS`. Nothing REGRESSED or ERRORED, C021 CLEAN, S008 19/19. Seven rules are IMPROVED: A002, S001, S009, S010, S025, S061 and S063.
- **Follow-up only, not a finding** (briefing §4):
  - `RecordFieldValidator.require_directory` (`validation.py:131-135`) and its callers `native_threads.py:120` and `:146` keep the raw-`OSError` path.
  - `to_path` (`validation.py:198`) has R-RR2-1's `TypeError`.
  - One validation.py PR closes both.

COMMANDS RUN:
- `git diff ec17d5ce...bff67286 -- vidbyte/` → 2 files, +10/-7 (as quoted above). `git diff ec17d5ce...bff67286 --numstat -- tests` → `28 1`, `21 1`, `26 1` (S2's 4de2c91d only). `git diff ec17d5ce...bff67286 -- lint/ | wc -l` → `0`.
- Area: `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` → `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 1304 passed, 3 skipped in 87.90s (0:01:27)`.
- `PYTHONIOENCODING=utf-8 "$V" lint/run.py` → `S064 RATCHETED: 4 known finding(s). …` · `SDK-LINT: PASS` (rc=0).
- `"$V" -m unittest <the 2 R-RR1 ids>` → `Ran 2 tests in 0.612s` · `OK`.
- `"$V" scratchpad/s5-rereview-2/rr2_mutant.py <variant> tests/features/codex_host/test_codex_host_feature_records.py tests/features/codex_host/test_codex_host_worktree.py`:
  - NONE → `58 passed in 6.83s`;
  - REVERT → `2 failed, 56 passed`;
  - PERMISSION-ONLY → `2 failed, 56 passed`;
  - CHAINED → `2 failed, 56 passed`;
  - NO-DETAILS → `4 failed, 54 passed`;
  - RAW-TEXT → `4 failed, 54 passed`.
- The same runner's `apply()` followed by `unittest` on the 2 ids:
  - REVERT → `ran 2 errors 6 failures 0`;
  - PERMISSION-ONLY → `ran 2 errors 3 failures 0`;
  - CHAINED → `ran 2 errors 0 failures 6`.
- `"$V" scratchpad/s5-rereview-2/probe_real_paths.py` → 10 refusals with `cause=None suppress=True secret_in_text=False`, and `existing-folder … ACCEPTED`.
- `"$V" -c "…class P: __fspath__ returns 5; CodexWorktreeRequest(repository=P(), branch='feat/x')"` → `TypeError expected P.__fspath__() to return str or bytes, not int`.
- `"$V" -m pytest tests/features/codex_host/test_codex_host_stream_wait.py -k "oversize or larger_than_the_text_bound or host"` → `27 passed in 2.20s`.
- `tr -d '\r' < f | awk 'length($0) > 72' | grep -nE '^\s*#'` on both touched files → no output.
- `wc -l` (CR stripped) → `codex_host_inputs.py` 783, `thread_actions.py` 317, host.py 786, wire.py 839, `lib/dataclasses/codex_host.py` 891.
- `git status --short --untracked-files=all` → empty (worktree unchanged).
