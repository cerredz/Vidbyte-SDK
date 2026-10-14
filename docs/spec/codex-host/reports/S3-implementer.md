# S3 implementer report: codex-host

**Stage facts**

| | |
|---|---|
| Stage | S3 implementer |
| Spec | `docs/spec/codex-host/spec.md` r4, now `status: implemented` |
| Branch | `feat/codex-host`, pushed to origin |
| Stage base | `51dd290b` (S2 head `1d110811` plus the orchestrator's S3 start commit) |
| Draft PR | https://github.com/cerredz/Vidbyte-SDK/pull/1055 (placeholder body, draft) |
| Last code commit | `62c0a488` (row 28) |
| Docs commits | `ed2063ff` (PR link and status), `79eadcf4` (§17 row and deviations), then the commit holding this report |

**What was not touched:**
- No file under `tests/`: `git diff 1d110811..HEAD --stat -- tests/` prints nothing.
- Not `lint/baseline.json`, `pyproject.toml`, `vidbyte/__init__.py`, the MCP server package or the agent base module.
- No `.gitattributes`, no `# noqa`, no `# type: ignore` and no `nosemgrep`.
- No live `codex` binary or app-server, and no model turn. Every proof ran at the §13 fake seam.
- The claude-host worktree, the main checkout and the field guide were not touched.
- No CI was dispatched, and nothing was merged or force-pushed.

## Commits, one per §12.3 row

| Row | SHA | File | Citation |
|---|---|---|---|
| 1 + 4 | `4794b23a` | `vidbyte/lib/enums/failure.py`, `vidbyte/lib/constants/codex.py` | W-2; FR-18, FR-19, FR-20, AC-29 |
| 2 | `39d35117` | `vidbyte/lib/enums/codex.py` | W-2; FR-8, FR-15, FR-16, AC-21 |
| 3 | `5df1643e` | `vidbyte/lib/enums/__init__.py` | W-2; FR-16 |
| 5 | `ad9eef7c` | `vidbyte/lib/errors/base.py` (only `CodexAgentError.__init__`) | W-3; FR-20, AC-29 |
| 6 | `6a431510` | `vidbyte/lib/dataclasses/codex_host.py` | W-2; FR-16, FR-17, FR-18, AC-35 |
| 7 | `334051a8` | `vidbyte/agents/codex/tools.py` | W-4; FR-28, AC-28, AC-30 |
| 8 | `e0187887` | `vidbyte/harnesses/native/__init__.py` | W-1; FR-30, AC-36 |
| 10 | `6715f82e` | `vidbyte/harnesses/native/codex/errors.py` | W-14; FR-20, AC-12, AC-29, AC-34, AC-37 |
| 13 | `68b9aef3` | `vidbyte/harnesses/native/codex/turns.py` | W-9, W-10, W-13; FR-10 to FR-13, FR-17 to FR-19; AC-7 to AC-10, AC-17, AC-20 |
| 11 | `ee45a433` | `vidbyte/harnesses/native/codex/wire.py` | W-7, W-8; FR-5 to FR-9, FR-16, FR-29; AC-5, AC-13, AC-21, AC-22, AC-37 |
| 12 | `50a9c523` | `vidbyte/harnesses/native/codex/connection.py` | W-5; FR-1, FR-28, NFR-4, NFR-9; AC-11, AC-30, AC-32, AC-33 |
| 14 | `a096caae` | `vidbyte/harnesses/native/codex/preflight.py` | W-7; FR-2, FR-5, FR-6, FR-14, FR-15; AC-6 |
| 15 | `47bda349` | `vidbyte/harnesses/native/codex/host.py` | W-5 to W-13; FR-1 to FR-21; AC-1 to AC-22, AC-32, AC-33, AC-37 |
| 16 | `f9f44a05` | `vidbyte/harnesses/native/codex/oneshot.py` | W-15; FR-22; AC-31 |
| 9 | `083a7528` | `vidbyte/harnesses/native/codex/__init__.py` | W-5, W-15; FR-1, FR-22; AC-1, AC-2 |
| 17 | `2de58d27` | `vidbyte/tools/builtins/codex/descriptions.py` | W-16; FR-23, NFR-7, AC-26 |
| 18 | `18ff87eb` | `vidbyte/tools/builtins/codex/_base.py` | W-16; FR-25, FR-26, AC-24, AC-25 |
| 19 | `2df26def` | `vidbyte/tools/builtins/codex/readiness.py` | W-16; FR-2, FR-3, FR-4, FR-23, AC-23 |
| 20 | `ce4b7fc3` | `vidbyte/tools/builtins/codex/threads.py` | W-16; FR-5 to FR-9, FR-23, AC-23, AC-25, AC-26 |
| 21 | `13737003` | `vidbyte/tools/builtins/codex/live.py` | W-16; FR-10 to FR-13, AC-25 |
| 22 | `c8dbb84a` | `vidbyte/tools/builtins/codex/delegation.py` | W-16; FR-14, FR-15, AC-23 |
| 23 | `9b9fd98d` | `vidbyte/tools/builtins/codex/__init__.py` | W-16; FR-23 |
| 24 | `44f68d41` | `vidbyte/tools/builtins/__init__.py` | W-17; FR-23 |
| 25 | `56bbeec9` | `vidbyte/tools/toolsets/codex.py` | W-17; FR-24, AC-1, AC-23 |
| 26 | `0d7a7dcd` | `vidbyte/tools/toolsets/__init__.py` | W-17; FR-24 |
| 27 | `fc4d5755` | `REPO_MAP.md` | W-19; FR-30 |
| 28 | `62c0a488` | `vidbyte/harnesses/README.md` | W-19; FR-30 |

Rows 9 to 16 were built inside phase P3 in the order their imports allow: the error mapper, turn state, translators, connection and preflight came first, then the host, then the module functions, and then the package exports. Each commit passed lint, Semgrep and an import check when it landed. The P3 pack was proven once the host existed: 76 passed and 8 failed, and all 8 failures waited on P4/P5 (the toolset, the tools package, the fixed texts and the export lists). After P5, all 101 pass.

## Data-flow build list (lowest layer first)

1. **P1, lib contracts.** The 15 failure codes with their classification rows and next steps, the constants, the 13 enums and their exports, `CodexAgentError.next_step`, and the 15 validated records.
2. **P2, the bridge seam.** `CodexToolTranslator.validate_names` and `CodexToolBridge.handler` in `vidbyte/agents/codex/tools.py`, which keep their existing behaviour. Then the byte-fixed `native/__init__.py`.
3. **P3, the host.**
   - `CodexErrorMapper` turns SDK and JSON-RPC failures into `codex.*` codes, using fixed text only.
   - `CodexParamsTranslator` and `CodexResponseTranslator` handle the wire format.
   - `CodexConnection` and `CodexServerRequestRouter` own the process, the executor, the bounded calls, late acceptance and the liveness monitor.
   - `CodexLiveTurn`, `CodexGoalTurn`, `CodexTurnWatcher` and `CodexTurnRegistry` hold turn state.
   - `CodexPreflight` runs the readiness checks.
   - `CodexHost` and the six module functions sit on top.
4. **P4, tools.** The descriptions come first. Then `CodexToolScope` with its cap, reservations and handle ownership, and the `_CodexHostTool` base. Then the 15 tools in four modules, the package exports, the builtins re-export, `CodexHostTools`, and the toolsets export.
5. **P5, docs.** The fixed REPO_MAP section and the harnesses README bullet.

## Completeness pass

- **§12.3:** all 28 rows are ticked; each has a commit in the table above.
- **§12.4:**
  - Every new `.py` file has the single-line seven-field A001 header.
  - The native `__init__` blob SHA-256 is `0374a2c8…942f497a` (exact).
  - Every file is under 1,000 lines; the largest is `host.py` at 733.
  - The enums, records and constants follow the placement and naming rules.
  - The `@intent` lines satisfy A002, and S054, S012, S016, S017, S025, S045, S039 and S063 hold, with no suppression.
  - openai-codex is imported only in `connection.py`, `wire.py`, `turns.py` and one method of `errors.py`, and the package smoke test passes.
  - The export lists got sorted insertion only. The fixed texts are byte-exact, and the README stays under 40,000 characters.
- **§12.5:** the repo map and README texts are in; the export lines are in. Every "nothing to do" item stays untouched, and `generate-sdk-public-api.py --check` confirms the root exports did not change.
- **§6.2:** every Proof cell was already filled by S2, so none was edited.

## Implementation deviations (also recorded in spec §17)

1. **Two argument checks take a different shape because of lint C002.** C002 flags a repo-wide duplicate inline bool guard when another module guards a variable of the same name.
   - `wait_codex_turn` checks `timeout_seconds` by building `CodexSpawnRequest(timeout_seconds=...)`, which applies the same seconds rule, and re-raises `ConfigurationError(BAD_TIMEOUT_MESSAGE) from None`.
   - `launch_codex_subagents` checks `limit` with `type(limit) is not int or limit < CODEX_HOST_MIN_LIVE_TURNS`, because `vidbyte/lib/dataclasses/coding.py:143` already guards a `limit` name.
   - The accepted values, the error type and the messages are the same. The validated record that the lint suggests would have exceeded the 15-record budget.
2. **A process death also closes goal streams.** On death (D-27), `_on_death` runs close steps 1 and 2 as specified. It also closes each ended goal run's stream, which is the goal-run part of close step 4, so that run's watcher thread exits. Then it reaps the process on the close thread.

## Files outside §12.3

None. During P4, `ruff --select I001 --fix` over `vidbyte/tools/toolsets` rewrapped an import in `vidbyte/tools/toolsets/paradigm_minimal.py`. That change was reverted with `git checkout` before any commit, and the file is not in the diff.

## Budget (§8.4)

| Item | Used | Allowed |
|---|---|---|
| New files | 18 | 18 |
| New modules | 18 | 18 |
| New classes | 30 (12 harness, 17 tool layer, 1 toolset) | 30 |
| New records | 15 | 15 |
| New enums | 13 | 13 |
| New dependencies | 0 | 0 |

Every limit is used exactly, so there is no headroom left for S4/S5 fixes that add a class, record or file.

## Gates (final lines, at `62c0a488`; the later commits change docs only)

| Gate | Command | Final lines |
|---|---|---|
| (a) Pack | `PYTHONPATH=$(pwd) $PY -m pytest tests/features/codex_host -q -p no:cacheprovider` | `101 passed in 7.55s` |
| (b) CI view | the same pack with `sys.modules['openai_codex']=None` | `35 passed, 66 skipped in 2.05s` |
| (c) Codex tests | the 7 `tests/test_codex_*.py` files plus `test_readme_size_limit.py` and `test_skills_interface.py` | `247 passed in 2.49s` |
| (d) Full suite | `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider` | `4041 passed, 22 skipped in 42.88s` |
| (e) Lint | `PYTHONPATH=$(pwd) $PY lint/run.py` | `SDK-LINT: PASS` |
| (f) Local CI, source | `PYTHONPATH=$(pwd) $PY scripts/run_ci.py --stage source` | `4041 passed, 22 skipped in 42.78s` / `CI passed.` |
| (f) Local CI, package | `$PY scripts/run_ci.py --stage package` (no PYTHONPATH) | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| (g) Semgrep | the semgrep-1.170.1 venv, `typed-mapping-boundary-policy.yml` over `vidbyte` | `Ran 1 rule on 911 files: 0 findings.` (exit 0) |
| (h) Public API | `$PY scripts/generate-sdk-public-api.py --check` | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` (exit 0) |
| Blob | the §11 `git cat-file` SHA-256 of `vidbyte/harnesses/native/__init__.py` | `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a` |
| Tests untouched | `git diff 1d110811..HEAD --stat -- tests/` | (empty) |

**Notes on the gates:**
- **mypy (S009).** `--rule S009 --all` reports no finding in `vidbyte/harnesses/native/`, `vidbyte/tools/builtins/codex/` or `vidbyte/tools/toolsets/codex.py`.
- **Lint IMPROVED lines.** The lint prints IMPROVED for A002 (703 → 607), C012, S001, S010 and S025. `lint/baseline.json` was left alone, as request.md §C requires.

## Tricky parts (least sure first)

1. **Late acceptance and close races** (`connection.py` `start`, `_hand_over` and `_post_late`, and `host.py` `__aexit__`). A start that returns after its bound, or after close began, is registered under a shield and interrupted once. The AC-32 and AC-33 tests pass, but these are the paths a reviewer should read most closely.
2. **Death handling.** `_on_death` must reap the process. The tests require it, and D-27 puts the reap on the close thread. I removed the reap once and then restored it. It also closes goal streams (deviation 2).
3. **The cap check in `CodexToolScope.reserve`.** It refreshes the live handles through `get_codex_turn_result`, which only reads locally, and then checks and reserves with no await in between (INV-32). Cancellation frees the reserved slot in the callers' `finally`.
4. **Two C002 workarounds** (deviation 1). Behaviour is unchanged, but the shape is unusual, and a reviewer may ask for a record that the budget does not allow.
5. **The ruff I001 fixer reaches neighbouring files.** Running it on a directory rewraps imports in untouched files. Run it on explicit file paths only.

## OPEN ITEMS

- The branch is 41 commits behind `origin/main` (`8387d666`). `git merge-tree` shows no conflict. The only touched area that main changed is `vidbyte/harnesses/stores/file.py`, which this PR does not edit. Per §14, the catch-up is a merge, never a rebase. It was not done here, because it was not asked for.
- AC-1's live run with a signed-in `codex` is manual QA and spends the user's plan (NG-13). It was not run.
