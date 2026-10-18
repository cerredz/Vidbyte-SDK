# Verification log: CodexHost first-class Codex features (slice 2 of 2)

Gate set (from context/code-map.md §1, with this run's interpreter `V` = the `venv-codex163` editable install with openai-codex 0.163.0; every gate runs locally, and no workflow runs on push):
- **Area tests** (local): `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider`. The one allowed failure is the inherited `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`).
- **Lint** (local, also inside the source stage): `git add` new files, then `PYTHONIOENCODING=utf-8 "$V" lint/run.py`; the last line must be `SDK-LINT: PASS`, with no baseline raised.
- **Semgrep** (local): `semgrep-core.exe -rules .semgrep/<rule>.yml -lang python -json <file>` for every rule in `.semgrep/` and every `vidbyte/*.py` the slice changed; parse from the first `{`.
- **72-column comments** (local, field guide `comment-format.md`; not a lint rule): `tr -d '\r' < f | awk 'length($0)>72 && /^[ \t]*#/'` over every `vidbyte/*.py` changed since `a7730107` prints nothing. Test files keep their own wider style and are out of scope.
- **Line ceilings** (INV-47): `host.py` ≤ 900, `wire.py` ≤ 840, `lib/dataclasses/codex_host.py` ≤ 900, new modules ≤ 600 (`wc -l`).
- **Full gate, source stage** (local, run alone): `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source`. Only the inherited failure is allowed.
- **Full gate, package stage** (local, run alone, no PYTHONPATH): `"$V" scripts/run_ci.py --stage package`; must end `CI passed.`
- **Test contract** (local): `git diff 25c2de9b..HEAD -- tests` stays empty (S2_HEAD `25c2de9b`).
- **Remote checks** (remote-only): `gh pr checks 1181`; the workflows run only on `workflow_dispatch`, so a push triggers none, and the local gate is authoritative.

## Iteration 1 — 2026-10-18 — agent report: reports/S5-repair-1.md
**Defects in:** R-1 and R-2 (Blockers); R-3, R-4, R-5 and R-8 (Majors, code); R-6 and R-7 already fixed by S2 at `9ad2771e`; the trivial Minors m-2 to m-5 (m-1 already fixed by spec r6 at `4d972438`; m-6 and m-7 stay follow-ups). Failing gates at `3d285f78`: the area tests gave `8 failed, 1295 passed, 3 skipped`, which was the seven S2 regression rows for R-1, R-3, R-4 and R-5 plus the inherited `harness_threads` surface test.

**Hypotheses and attempts** (each fix worked on its first attempt; the alternatives below were weighed and rejected before writing, so the next agent need not retry them):
- **R-1** (`thread_methods.py` `create_codex_worktree`). Chose one `try` around `Path.home()`, the target check, the existing-folder refusal and `root.mkdir(...)`, with `except (OSError, RuntimeError) as exc:` raising `CodexErrorMapper.error(CONFIGURATION_INVALID_ARGUMENT, CODEX_HOST_WORKTREE_ROOT_MESSAGE.format(error_type=type(exc).__name__), …) from None`, and the r6 triple added to `lib/constants/codex_host.py` in sorted `__all__`.
  - Checked first: `CodexAgentError`'s MRO is `AgentExecutionError → VidbyteSdkError → Exception`, neither `OSError` nor `RuntimeError`, so the existing-folder refusal inside the `try` passes through unchanged.
  - Rejected: putting `_guard` inside the `try`. Its `asyncio.get_running_loop()` is the only source of EC-3's `RuntimeError`, which INV-2 keeps distinct.
  - Rejected: one `try` per step. Same behaviour, more branches for S008.
  - No log line, as EC-63 and the test require. The `mkdir` stays before git (INV-29).
  - On Windows a `~/.vidbyte` that is a file raises `FileExistsError` from `mkdir`; `target.exists()` returns False through a file and does not raise.
- **R-2** (14 comment lines in 10 files). Re-wrapped or reworded each line, keeping its meaning. The `@intent` at `feature_wire.py:197` is now `a-side-chat-fork-is-ephemeral`; grep found no reference in `tests/`, `lint/` or source. The `wire.py` sandbox-policy block was reworded to stay at three lines, so `wire.py` stays at 839/840.
- **R-3** (`turn_stream.py` `record`). Chose a named helper, `_fits_alone(size)`, guarding the drop loop: `while self._events and self._fits_alone(size) and not self._fits(size)`.
  - Rejected: the review's inline `size <= TEXT_LIMIT and size <= HOST_TEXT_LIMIT`. It is identical on an attached log, but it applies the host bound to a log that was never attached, and INV-20 says such a log "has the per-turn bounds only". The helper checks the host bound only when `self._charge` is set, and it keeps the long condition readable.
  - Not tried, and not needed: making the loop skip when other turns fill the host bound. INV-20 already says the log drops its own oldest events and then the new one.
- **R-4** (`turn_starts.py` `_resume_now`). The review's fix as written: `sent = True` before `activate()`, `except BaseException as exc:`, and a cancel when `sent and not isinstance(exc, JsonRpcError)`. `JsonRpcError` is imported beside `CodexError` from `openai_codex.errors`; the module already loads the SDK (INV-45). Every SDK RPC error class, `ServerBusyError` and `RetryLimitExceededError` included, subclasses `JsonRpcError`, so a busy answer to the single-attempt set counts as a refusal, as INV-31 says. The narration, the `@intent` name (now `a-resume-cancels-a-set-codex-did-not-refuse`) and header lines 5 and 7 changed in the same edit.
- **R-5** (`thread_actions.py` `_side_chat_defaults`). Took the table-driven reset of `ResumeCodexGoalTool._resume_defaults`: every path of `CODEX_HOST_REJECTED_FIELDS[START_CODEX_SIDE_CHAT]` goes back to a fresh `CodexSpawnRequest` or `CodexThreadSettings` value, in the same `replace` calls that narrow. None of the reset names collides with a narrowing keyword.
  - `THREAD_FIELD_PREFIX = "thread."` is a local module constant, following the `ONE_TURN` precedent, which both tool modules define locally.
  - Rejected: importing it from `skill_functions.py`, which would couple two sibling tool modules for one string.
  - Rejected: `_continue_defaults`' hand-listed reset, because it drifts from the host's table.
- **R-8** (13 unnarrated methods). Added 2-6 plain-English step comments to each. Checked with a tokenize counter (`scratchpad/s5r1/narr.py`): all 25 public methods in the four mixins now carry body comments; the 13 had 0.
- **m-2** (child-thread gate word).
  - Rejected: an inline `"ancestorThreadId" if listing.descendants else "parentThreadId"` in `thread_methods.py`. It would repeat the translator's choice of wire key in a second layer and add a hand-written wire key to a native body, which is the m-6 class.
  - Chose `CodexFeatureParamsTranslator.child_filter_key(request)`, a static method used by both `child_threads` and the gate.
  - **Spec follow-up:** spec implementation deviation 5 still says the feature word is `thread/list` for `list_codex_child_threads`. That clause needs the spec author; this agent may not edit `spec.md`.
- **m-3** (`enums/codex.py` header). Checked with the venv by comparing values. The six SDK counterparts are `ModeKind`, `ThreadMemoryMode`, `McpAuthStatus`, `McpServerConnectionStatus`, `McpServerStatusDetail` and `TurnPlanStepStatus`; our copies add only the empty member.
  - The review named `McpServerStartupState` for `CodexMcpConnectionStatus`, but its values differ. `McpServerConnectionStatus` is the real match.
  - `TurnSettingsUpdateStatus` is absent from 0.163.0.
- **m-4, m-5.** Header and comment text only. m-5 kept the thread-helpers spec's own `D-16` in `skill_functions.py` RELATED DOCS, which is a different spec, and changed only the first-class citations.
- Doc-only fixes are committed as `docs(codex-host): …` rather than `fix(…)`, because they change no behaviour.

**Changes:**
- `7fd15f1e` R-1;
- `b83cb6be` R-2;
- `f19ff74a` R-3;
- `e943f85a` R-4;
- `55702409` R-5;
- `e82a0185` R-8;
- `2aa6eb0b` m-2;
- `bc3cd186` m-3;
- `3e4c1b2a` m-4;
- `38c70528` m-5.

**Gate matrix out:**
All rows were run in this worktree in this iteration, at `38c70528`, which is the last source commit. The docs commit after it changes no code.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (the 7 S2 regression rows) | `PYTHONPATH=$(pwd) "$V" -m pytest -q -p no:cacheprovider <the 7 node ids>` | PASS (7/7; red at `3d285f78`) | inside the area run below; per fix: `32 passed` (worktree and constants), `27 passed` (stream), `41 passed` (goal and turns), `55 passed` (tools and side chat) |
| area tests | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` | PASS except the inherited failure | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 1302 passed, 3 skipped in 88.02s (0:01:28)` |
| inherited failure at the base | the same node at merge-base `6f5a7310` (scratch worktree, `PYTHONPATH` set to it) | FAILS there too, so inherited | `E       AssertionError: assert 167 == 120` · `1 failed in 1.71s` |
| lint | `PYTHONIOENCODING=utf-8 "$V" lint/run.py` | PASS (no REGRESSED or ERRORED rule; A002 703→582, S001 59→56 and S009 350→346 IMPROVED; C021 CLEAN; S008 19/19, S024 25/25) | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| semgrep | `semgrep-core.exe -rules .semgrep/<rule>.yml -lang python -json <file>`, for every rule and each of the 38 `vidbyte/*.py` changed since `a7730107` (runner `scratchpad/s5r1/semgrep_all.py`) | PASS | `rules=1 files=38 findings=0 errors=0`. Sanity: the same runner on the rule's own fixture gives `findings=2 errors=0`. |
| ruff, S051 selectors (extra, as slice 1 ran) | `"$V" -m ruff check <18 touched .py> --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045,F --no-cache` | PASS | `All checks passed!` |
| 72-column comments | `tr -d '\r' < f \| awk 'length($0)>72 && /^[ \t]*#/'` over the 38 `vidbyte/*.py` changed since `a7730107` | PASS | no output |
| line ceilings (INV-47) | `wc -l` | PASS | host.py 786/900 · wire.py 839/840 · lib/dataclasses/codex_host.py 891/900 · largest new module thread_methods.py 370/600 |
| test contract | `git diff 25c2de9b..HEAD -- tests \| wc -l` | PASS | `0` |
| full gate, source stage (run alone) | `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source` | PASS except the inherited failure (its embedded lint printed `SDK-LINT: PASS`) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6833 passed, 27 skipped in 141.62s (0:02:21) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-codex-host-first-class).` |
| full gate, package stage (run alone, no PYTHONPATH) | `"$V" scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| independent probes (S4 verifier's own scripts) | `PYTHONPATH="$(pwd);<verifier dir>" "$V" -m unittest probe_v_worktree probe_v_engineering`, and pytest `probe_v_stream.py` | PASS, matching the verifier's predicted post-fix output | R-1: `typed=True … raised FileExistsError` / `RuntimeError` / `PermissionError`, each with `branches: ['master'] sent: []` · R-4: `goal status at Codex: paused`, `goal-op calls: ['cancel_goal_operation', 'finish', 'unregister_goal_operation']`, `interrupts: 1` · R-5: `side-chat tool with tools default: success` · R-3: `gaps (seq,dropped): [(4, 1)]`, `delta texts: ['a', 'b', 'c', 'd']` |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1181` | none configured (the workflows are `workflow_dispatch` only), so the local gate is authoritative | `no checks reported on the 'feat/codex-host-first-class' branch` |

**Still open:**
- No confirmed finding.
- m-6 and m-7 stay follow-ups, as the orchestrator decided.
- Spec implementation deviation 5's `thread/list` clause is stale after m-2. It needs one word from the spec author, and it is not a code defect.

## Iteration 2 — 2026-10-18 — agent report: reports/S5-repair-2.md
**Defects in:** from re-review round 1 (`reports/S5-rereview.md`):
- R-RR1 (Blocker, code);
- R-RR2 (Minor), whose comment half is code and whose shared-helper half is a follow-up by orchestrator decision;
- R-RR3 (Minor), already fixed in spec r8 at `2d0f5216`.

Failing gates at `64532571`: the area suite gave `3 failed, 1302 passed, 3 skipped`. That was the two S2 R-RR1 rows (6 subtests) plus the inherited `harness_threads` surface test. S2_HEAD is now `d11c5d9d`, so the test-contract gate is `git diff d11c5d9d..HEAD -- tests`.

**Hypotheses and attempts:**
- **R-RR1, root cause confirmed by running it.** `"$V" -m unittest <the two ids>` showed all 6 subtests raising a raw `PermissionError: [Errno 13]` or `OSError: [Errno 38]` that quoted the absolute path. `CodexWorktreeRequest.__post_init__` catches only `ConfigurationError`, and `Path.is_dir()` inside `RecordFieldValidator.require_directory` re-raises a refused stat. This hypothesis was new: iteration 1 never touched the record.
- **Four structurally different fixes were weighed before writing:**
  1. **Chosen:** widen the record's own handler to `except (ConfigurationError, OSError):`, keeping the message and `from None`. It is one token in §12.3 row 9 and gives exactly §9.1 row 9's refusal.
  2. **Rejected:** treat a refused stat as "not a directory" inside `RecordFieldValidator.require_directory`. That is the canonical-helper home (AGENTS.md §5) and would also close `native_threads.py:120` and `:146`. But `validation.py` is outside §12.3 and on this iteration's must-not list, so it stays a follow-up for its own PR.
  3. **Rejected:** build the record inside R-1's `try` in `thread_methods.py`. That raises the root `CodexAgentError` packet, the wrong kind and the wrong message, instead of the repository `ConfigurationError`. It also breaks the "record first, before anything else" order.
  4. **Rejected:** pre-check with `os.path.isdir` in the record. It swallows every `OSError`, but it duplicates the shared validator with a second, different directory rule.
- **What else in the `try` can raise.** `to_path` raises only `ConfigurationError`, and `is_dir` already returns False for `ValueError` (Python ≥ 3.8). So `OSError` is the one remaining type.
- **Narration and header.** A three-line comment inside the `except` follows R-1's handler style (`thread_methods.py:173-175`). The header's KNOWN EDGE CASES gained one clause. The file is now 783 of its 900 lines (NFR-1).
  - The briefing's "600-line ceiling" for this module is wrong. Spec NFR-1 gives `codex_host_inputs` 900, and the file was already 780 lines.
- **Revert mutants**, applied in place and restored with `git checkout`:
  - `except (ConfigurationError, PermissionError)` gives `FAILED (errors=3)`, from the ENAMETOOLONG subtests;
  - `… as exc` with `from exc` gives `FAILED (failures=6)`.
  So the S2 rows pin both the type and `from None`.
- **R-RR2.** The continue tool's `_continue_defaults` (`threads.py:204-216`) clears a hand-written list and reads no table. The comment now says "as the resume tool does" and is re-flowed within 72 columns.
  - The module header's "as the continue and resume tools reset theirs" is true, because both reset, so it is unchanged.
  - The commit is `docs(codex-host)`, following iteration 1's convention for changes that do not change behaviour.
- **The "inherited" claim, re-checked.** A plain `git archive` extract of merge-base `6f5a7310` PASSES the surface test, but vacuously: its `optional_merge_base()` finds no repository and returns early. Re-run from the same extract with `GIT_DIR` set to this worktree's git dir, it fails exactly as on the branch (`assert 167 == 120`).
  - The failing assertion reads `git show <merge-base>:vidbyte/lib/enums/failure.py`, so no branch change can affect it.
  - A future agent who "proves" the base passes with a non-git extract is wrong.

**Changes:**
- `2e076b36` R-RR1;
- `819eed3e` R-RR2 (comment).

**Gate matrix out:**
All rows were run in this worktree in this iteration, at `819eed3e`, which is the last source commit. The docs commit after it changes no code.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (the 2 S2 R-RR1 rows, 6 subtests) | `PYTHONPATH=$(pwd) "$V" -m unittest <the 2 ids>` | PASS (red at `64532571`: `FAILED (errors=6)`) | `Ran 2 tests in 0.489s` · `OK` |
| record, worktree and input modules | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host/test_codex_host_feature_records.py tests/features/codex_host/test_codex_host_worktree.py tests/features/codex_host/test_codex_host_inputs.py -q -p no:cacheprovider` | PASS | `63 passed in 6.08s` |
| feature tools (R-RR2 file) | `… -m pytest tests/features/codex_host/test_codex_host_feature_tools.py -q -p no:cacheprovider` | PASS | `19 passed in 1.42s` |
| area tests | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` | PASS except the inherited failure | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 1304 passed, 3 skipped in 83.80s (0:01:23)` |
| inherited failure at the base | that node from a `git archive` extract of `6f5a7310`, with `PYTHONPATH` set to it and `GIT_DIR` set to this worktree's git dir | FAILS there too, so inherited | `E       AssertionError: assert 167 == 120` · `1 failed in 0.91s` |
| lint | `PYTHONIOENCODING=utf-8 "$V" lint/run.py` | PASS: nothing REGRESSED or ERRORED, C021 CLEAN, S008 19/19, A001 642/642 | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| semgrep | `scratchpad/s5r1/semgrep_all.py` (semgrep-core per rule per file) on the 2 touched files, then on all 38 `vidbyte/*.py` changed since `a7730107` | PASS | `rules=1 files=2 findings=0 errors=0` · `rules=1 files=38 findings=0 errors=0`. Sanity: the rule's own fixture gives `findings=2 errors=0`. |
| 72-column comments | `tr -d '\r' < f \| awk 'length($0)>72 && /^[ \t]*#/'` over the 38 `vidbyte/*.py` changed since `a7730107` | PASS | no output |
| line ceilings (INV-47, NFR-1) | `wc -l` | PASS | host.py 786/900 · wire.py 839/840 · lib/dataclasses/codex_host.py 891/900 · codex_host_inputs.py 783/900 · thread_actions.py 317/600 |
| test contract | `git diff d11c5d9d..HEAD -- tests \| wc -l` | PASS | `0` |
| full gate, source stage (run alone) | `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source` | PASS except the inherited failure (its embedded lint printed `SDK-LINT: PASS`) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6835 passed, 27 skipped in 140.21s (0:02:20) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-codex-host-first-class).` |
| full gate, package stage (run alone, no PYTHONPATH) | `"$V" scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1181` | none configured (the workflows are `workflow_dispatch` only), so the local gate is authoritative | `no checks reported on the 'feat/codex-host-first-class' branch` |

**Still open:**
- No confirmed finding.
- Follow-ups, none of them a defect in this PR's scope:
  - R-RR2's shared `_CodexHostTool` reset helper;
  - m-6 and m-7;
  - widening `RecordFieldValidator.require_directory` to map a refused stat. By reading only (not probed), `native_threads.py:120` and `:146` call it with no `OSError` handling, so they have the same raw-`OSError` path. The change is outside §12.3, so it needs its own PR.

## Iteration 3 — 2026-10-18 — agent report: reports/S5-repair-3.md
**Defects in:** R-RR2-1 (Minor, code), from re-review round 2 (`reports/S5-rereview-2.md`), which otherwise ruled SOUND. The orchestrator chose to fix it rather than defer it, because INV-2's "ever" is a weighted word.

Failing gates at `2bdb5e95`:
- The two S2 rows (4 subtests) gave `FAILED (errors=4)`, each a `TypeError: expected NonPathFspath.__fspath__() to return str or bytes, not int|NoneType`.
- The area suite gave only those rows plus the inherited failure.
- S2_HEAD is now `2bdb5e95`, so the test-contract gate is `git diff 2bdb5e95..HEAD -- tests`.

**Hypotheses and attempts:**
- **Root cause, confirmed by running it.** `CodexWorktreeRequest.__post_init__` (`codex_host_inputs.py:591`) caught `(ConfigurationError, OSError)`. But `RecordFieldConverter.to_path` (`validation.py:198`) calls `os.fspath`, which raises `TypeError` when `__fspath__` returns neither str nor bytes. Iteration 2's sentence "`to_path` raises only `ConfigurationError`" is the false premise behind this miss.
- **What else in the `try` can raise `TypeError`** (read, then probed): nothing.
  - `isinstance` against `(str, os.PathLike)` does not raise it.
  - `Path(str)` does not raise it.
  - `require_directory`'s `is_absolute` and `is_dir` do not raise it (`is_dir` already swallows `ValueError` and now has its `OSError` caught).
  - A bytes result reaches the `isinstance(text, str)` check and is already a `ConfigurationError`.
- **Three structurally different fixes were weighed.** None had been tried before, because iteration 2 never considered `TypeError`.
  1. **Chosen:** add `TypeError` to the record's tuple. It is one token in §12.3 row 9 and keeps §9.1 row 9's message, `details` and `from None`.
  2. **Rejected:** map the `TypeError` inside `RecordFieldConverter.to_path`. That is the root and the canonical-helper home, but `validation.py` is outside §12.3. Changing it also shifts behaviour for other callers (`native_threads.py:120`, `:146`), so it joins the logged `validation.py` follow-up PR.
  3. **Rejected:** check `__fspath__`'s result in the record before calling `to_path`. That duplicates the shared converter with a second rule, the same reason iteration 2 rejected its `os.path.isdir` pre-check.
- **Comment and header, in the same edit.** The `except` comment now says that a path object whose `__fspath__` returns neither str nor bytes is refused the same way, and why (`os.fspath` raises `TypeError`). The header's KNOWN EDGE CASES clause names the case too. The file is now 785 of its 900 lines (NFR-1), and every comment is within 72 columns.
- **Revert mutants**, applied in place after the commit and restored each time with `git checkout`; `git diff HEAD --quiet` was clean afterwards and the file stayed CRLF:
  - drop `TypeError`: `FAILED (errors=4)`;
  - `as exc` with `from exc`: `FAILED (failures=4)`;
  - `(ConfigurationError, TypeError)`, dropping `OSError`: `2 failed, 58 passed`. These are the R-RR1 rows, so the fix did not loosen R-RR1's pin.
- **Independent probe** (not S2's tests), giving `__fspath__` each of: int, None, float, list, bytes, raising `TypeError`, and raising `PermissionError` with a path.
  - Every one gives `ConfigurationError details={'field': 'repository'} cause=None suppress=True`.
  - A `__fspath__` that itself raises `ValueError` still propagates. That is the caller's own exception, which this record has never mapped, and it is not in scope (see the report's OPEN ITEMS).
- **Inherited failure, re-proved this iteration.** A `git archive` extract of merge-base `6f5a7310`, run with `GIT_DIR` set to this worktree's git dir, gives `assert 167 == 120`.

**Changes:**
- `bd89e5b8` R-RR2-1.

**Gate matrix out:**
All rows were run in this worktree in this iteration, at `bd89e5b8`, the only source commit. The docs commit after it changes no code.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (the 2 S2 R-RR2-1 rows, 4 subtests) | `PYTHONPATH=$(pwd) "$V" -m unittest <the 2 ids>` | PASS (red at `2bdb5e95`: `FAILED (errors=4)`) | `Ran 2 tests in 0.378s` · `OK` |
| record, worktree and input modules | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host/test_codex_host_feature_records.py tests/features/codex_host/test_codex_host_worktree.py tests/features/codex_host/test_codex_host_inputs.py -q -p no:cacheprovider` | PASS | `65 passed in 6.95s` |
| area tests | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` | PASS except the inherited failure | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 1306 passed, 3 skipped in 82.65s (0:01:22)` |
| inherited failure at the base | that node from a `git archive` extract of `6f5a7310`, with `PYTHONPATH` set to it and `GIT_DIR` set to this worktree's git dir | FAILS there too, so inherited | `E       AssertionError: assert 167 == 120` · `1 failed in 1.67s` |
| lint | `PYTHONIOENCODING=utf-8 "$V" lint/run.py` | PASS: rc 0, nothing REGRESSED or ERRORED, C021 CLEAN, S008 19/19, A001 642/642, A002 IMPROVED 703→582 | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| ruff (extra) | `"$V" -m ruff check vidbyte/lib/dataclasses/codex_host_inputs.py --config lint/ruff.toml --no-cache` | PASS | `All checks passed!` |
| semgrep | `scratchpad/s5r1/semgrep_all.py` (semgrep-core per rule per file) on the touched file, then on all 38 `vidbyte/*.py` changed since `a7730107` | PASS | `rules=1 files=1 findings=0 errors=0` · `rules=1 files=38 findings=0 errors=0`. Sanity: the rule's own fixture gives `findings=2 errors=0`. |
| 72-column comments | `tr -d '\r' < f \| awk 'length($0)>72 && /^[ \t]*#/'` over the 38 `vidbyte/*.py` changed since `a7730107` | PASS | no output |
| line ceilings (INV-47, NFR-1) | `wc -l` (CR stripped) | PASS | host.py 786/900 · wire.py 839/840 · lib/dataclasses/codex_host.py 891/900 · codex_host_inputs.py 785/900 · thread_methods.py 370/600 |
| test contract | `git diff 2bdb5e95..HEAD -- tests \| wc -l` | PASS | `0` |
| full gate, source stage (run alone) | `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source` | PASS except the inherited failure (its embedded lint printed `SDK-LINT: PASS`) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6837 passed, 27 skipped in 138.01s (0:02:18) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-codex-host-first-class).` |
| full gate, package stage (run alone, no PYTHONPATH) | `"$V" scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1181` | 0/0: none configured (the workflows are `workflow_dispatch` only), so the local gate is authoritative | `no checks reported on the 'feat/codex-host-first-class' branch` |

**Still open:**
- No confirmed finding.
- Follow-ups, none of them a defect in this PR's scope:
  - R-RR2's shared `_CodexHostTool` reset helper;
  - m-6 and m-7;
  - one `validation.py` PR that makes `RecordFieldValidator.require_directory` map a refused stat and makes `RecordFieldConverter.to_path` map `os.fspath`'s `TypeError`. That would close the record's two catches at the root, along with `native_threads.py:120` and `:146`.
