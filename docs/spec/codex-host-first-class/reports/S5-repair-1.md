# S5 repair iteration 1 of 8: codex-host-first-class

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-first-class`, branch `feat/codex-host-first-class`, PR #1181 (draft). Started at `3d285f78`; S2_HEAD `25c2de9b`. Spec r6 is the contract. No test file changed (`git diff 25c2de9b..HEAD -- tests` is empty).

## Gate matrix

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

## Per finding

### R-1 (Blocker): worktree root raised raw `OSError`/`RuntimeError`. Fixed `7fd15f1e`
- **Reproduced.** `test_codex_host_worktree.py::CodexWorktreeHostTests::test_a_worktree_root_that_cannot_be_prepared_is_refused_by_type_without_the_home_path_and_git_never_runs` failed with the raw `RuntimeError` from the patched `Path.home`. The two `test_codex_host_feature_constants.py::CodexFeatureTextTests` rows failed on the missing triple.
- **Root cause.** Three file-system steps before git had no handler (INV-2, INV-29, EC-63).
- **Fix.** One `try` around the home lookup, target check, existing-folder refusal and `mkdir`. An `except (OSError, RuntimeError) as exc` raises `configuration.invalid_argument` with `CODEX_HOST_WORKTREE_ROOT_MESSAGE.format(error_type=type(exc).__name__)` and its cause and next step, `from None`.
  - The r6 triple is in `vidbyte/lib/constants/codex_host.py` (now 764/900), in sorted `__all__`, verbatim from spec §9.2.
  - `_guard` stays outside the `try`, so EC-3's loop `RuntimeError` keeps its own path.
  - `CodexAgentError` is not an `OSError` or `RuntimeError` (MRO checked), so the existing-folder refusal passes through.
  - Nothing is logged, and the `mkdir` stays before git.
  - Header KNOWN EDGE CASES and the method's `@intent` narration are updated.
- **Evidence.** `test_codex_host_worktree.py` and `test_codex_host_feature_constants.py`: `32 passed`. All three subcases pass: no home, home not writable, and `~/.vidbyte` is a file, which gives `FileExistsError` on Windows. The test also asserts `__cause__ is None`, `__suppress_context__`, no canary, no branch, no log record and no request.

### R-2 (Blocker): 14 comment lines over 72 columns. Fixed `b83cb6be`
- **Reproduced** with the field guide's awk check over the slice's `vidbyte/*.py`: exactly the 14 lines the verifier listed.
- **Fix.** Each block was re-wrapped or reworded with its meaning kept.
  - `feature_wire.py`'s `@intent` became `a-side-chat-fork-is-ephemeral`; nothing references it.
  - The `wire.py` sandbox-policy block was reworded to stay at three lines, so `wire.py` is 839/840.
- **Evidence.** The awk check was run last, after every other fix, over all 38 `vidbyte/*.py` the slice changed since `a7730107`, and it prints nothing.

### R-3 (Major): one oversize stream event emptied the window. Fixed `f19ff74a`
- **Reproduced.** `test_codex_host_stream_wait.py::CodexTurnStreamHostTests::test_an_oversize_event_costs_a_lagging_subscriber_only_its_own_gap` failed: `b` and `c` were lost.
- **Root cause.** The drop loop `while self._events and not self._fits(size)` evicted everything for an event that could never fit.
- **Fix.** A new helper, `_fits_alone(size)`, guards the loop. It checks the turn's character bound, and the host's once the log is attached.
  - I chose it over the review's inline two-bound condition so that an unattached log keeps "the per-turn bounds only" (INV-20).
  - It is otherwise equivalent to the verifier's proven shape.
  - The comment and the header's KNOWN EDGE CASES and COMMON MODIFICATION PATTERNS are updated.
- **Evidence.** `test_codex_host_stream_wait.py`: `27 passed`, including the R-6 and R-7 mutant-killing rows S2 added.

### R-4 (Major): an applied but badly answered resume set left a goal running. Fixed `e943f85a`
- **Reproduced.** `test_codex_host_goal_control.py::CodexGoalResumeHostTests::test_a_resume_set_codex_applied_but_answered_badly_is_cancelled_once_and_cleaned_up` failed with no pause set.
- **Fix.** The review's fix as written:
  - `sent = True` before `activate()`;
  - the cancel runs when `sent and not isinstance(exc, JsonRpcError)`;
  - `JsonRpcError` is imported from `openai_codex.errors`.
  
  The narration, the `@intent` name and header lines 5 and 7 change in the same edit.
- **Evidence.** `test_codex_host_goal_control.py`, `test_codex_host_review_goals.py` and `test_codex_host_turns.py`: `41 passed`. That includes EC-37's JSON-RPC refusal, which gets no cancel, and EC-38's late adoption.

### R-5 (Major): the side-chat tool was dead under tools, name or personality defaults. Fixed `55702409`
- **Reproduced.** Both `test_codex_host_feature_tools.py` rows failed: the argument test (`request.tools` kept) and the host test, where the method refused the tool's own request.
- **Fix.** `_side_chat_defaults` now resets every path of `CODEX_HOST_REJECTED_FIELDS[START_CODEX_SIDE_CHAT]` to a fresh `CodexSpawnRequest` or `CodexThreadSettings` value, table-driven as the resume tool does. It then narrows as before.
  - R-14's `READ_ONLY`/`DENY_ALL`/`PROVIDER_DEFAULT` posture is unchanged.
  - The `_perform` narration, the method comment and the header ARCHITECTURE NOTE are updated.
- **Evidence.** The four tool and side-chat test modules: `55 passed`.

### R-6, R-7 (Major, tests). Fixed `9ad2771e` by S2
Their rows pass against the R-3 code (they are in the 27 stream tests above). Status set in `review.md`.

### R-8 (Major): 13 unnarrated feature main functions. Fixed `e82a0185`
- **Reproduced** with a tokenize counter (`scratchpad/s5r1/narr.py`): those 13 had `comments=0`.
- **Fix.** Added plain-English step comments: what is checked, why there is or is not an existence read or load, and what is sent. They cite the governing INV where useful, and none exceeds 72 columns.
- **Evidence.** The counter now shows 2 to 14 comment lines in every one of the 25 public methods across `thread_methods.py`, `settings_methods.py`, `goal_methods.py` and `stream_methods.py`. `tests/features/codex_host`: `598 passed, 1 skipped`.

### Minors
- **m-1.** Fixed `4d972438` by spec r6 (deviation 14); status set.
- **m-2.** Fixed `2aa6eb0b`.
  - The gate now names `parentThreadId`, or `ancestorThreadId` with `descendants=True`, from a new `CodexFeatureParamsTranslator.child_filter_key`. The params builder uses the same helper, so the key lives in one place.
  - **Spec follow-up:** implementation deviation 5 still says `thread/list` for `list_codex_child_threads`. The review asked for a spec edit too, r6 did not make it, and I may not edit `spec.md`.
- **m-3.** Fixed `bc3cd186`, with the facts checked in the venv by comparing values.
  - **Evidence correction:** the review lists `McpServerStartupState` as the counterpart of `CodexMcpConnectionStatus`, but their values differ. The matching enum is `McpServerConnectionStatus`. The count of six is right.
- **m-4.** Fixed `3e4c1b2a`. Both headers name `CODEX_HOST_WORKTREE_FAILED_MESSAGE` as the one stderr-quoting message (INV-29, EC-34). R-1's message carries only the type name.
- **m-5.** Fixed `38c70528`:
  - D-16 to D-8 in four first-class places;
  - EC-14 to INV-16/AC-11;
  - EC-12, EC-14 to EC-12, EC-13;
  - INV-38 to INV-29;
  - `stream_methods.py` no longer splits "first-class INV-23".
  
  The thread-helpers spec's own `D-16` in `skill_functions.py` RELATED DOCS was left alone, because it cites a different spec.
- **m-6, m-7.** Follow-ups, left open as decided.

## Test changes proposed
None.

## Findings believed wrong
None. One evidence correction (m-3's enum name) is noted above, and it does not change the finding.

## Fix interactions observed
- R-1, R-8 and m-2 all touched `thread_methods.py` (now 367/600).
- R-1, m-4 and m-5 touched `lib/constants/codex_host.py` (764/900).
- R-2, R-8, m-2 and m-5 added or re-wrapped comments, which is why the awk check ran last.
- No fix moved anything on the review's "gets right" list:
  - the §8.4 count stays at 46 config keys, because the triple is a §9.2 message and `THREAD_FIELD_PREFIX` is a tool-module literal like `ONE_TURN`;
  - lint C021 is still CLEAN;
  - host 786/900, wire 839/840, `codex_host.py` 891/900.

## What remains open, and what I would try next
- **No confirmed finding is open**, and every gate is green apart from the inherited `harness_threads` surface failure, which also fails at merge-base `6f5a7310`.
- **m-6 and m-7** stay follow-ups, as the orchestrator decided:
  - m-6 needs config keys past the section 8.4 budget of 46;
  - m-7 would land in `lib/dataclasses/codex_host.py` at 891/900, or in `validation.py` outside section 12.3.
- **Spec follow-up for the spec author** (not a code defect). Implementation deviation 5 still says the feature word for `list_codex_child_threads` is `thread/list`. After m-2 (`2aa6eb0b`) it is `parentThreadId`, or `ancestorThreadId` with `descendants=True`.
  - The review's m-2 row asked for that spec edit, and r6 did not make it. This agent may not edit `spec.md`.
  - If the orchestrator prefers to keep deviation 5 as written, reverting `2aa6eb0b` restores the old word, and no test depends on either.
- **Hypotheses for a later iteration:** none needed, because nothing is red.
  - If the re-reviewer contests R-3's helper form, the review's inline form (`size <= CODEX_HOST_STREAM_TEXT_LIMIT_CHARS and size <= CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS`) is a drop-in replacement. It differs only on a log that was never attached, and only when the host character bound is set below the turn bound.
- **Probe tip.** Run the S4 verifier probes with `unittest`, with `PYTHONPATH` set to the worktree plus the verifier dir (use `;` on Windows). Under pytest, collection walks `%TEMP%` and trips on other sessions' temporary folders.
