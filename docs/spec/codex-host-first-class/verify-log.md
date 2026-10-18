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
