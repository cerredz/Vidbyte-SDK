# S3 implementer report: infinite-memory-context-economy

Status: DONE. Every §12.3 row (57 rows, row 56 by its own condition), every §12.4 obligation, and every §12.5 action this PR owns are in; all local gates pass apart from three `harness_threads` surface tests the spec lists as known pre-existing (see Gates).

- Branch: `feat/infinite-memory-context-economy`, pushed (no force). Code HEAD e21463fe; spec commits c56f2b71 (frontmatter `pr:` + `status: implemented`) and 5f91b456 (§17 S3 row + implementation deviations); this report is the last commit.
- Draft PR: https://github.com/cerredz/Vidbyte-SDK/pull/1177 (`[WIP] feat: InfiniteMemoryAgent context economy`, base main, WIP body from the orchestrator).
- CI dispatched on 5f91b456: CI run 39009423722, Static policy run 39009425314 (`gh run list --branch feat/infinite-memory-context-economy --limit 4`); both completed success: CI jobs Source / Python 3.12, Source / Python 3.11, Package = success; Static policy = success.

## Drift check

- `git fetch origin`: origin/main moved from `0f2aeb48` to `845a4d9b` (4 commits: #1169, #1170, #1171, #1172).
- Touched spec paths: `vidbyte/agents/infinite/memory.py` (+4: `write_note`/`edit_file` keep the workspace-relative path), `vidbyte/agents/infinite/workspace.py` (+1: `write_note` returns `(created, relative)`, `edit_file` returns `relative`), `vidbyte/middleware/compaction/strategies.py` (+11: `_progress_entries` helper). None changes an interface the spec relies on.
- Merged with `git merge origin/main` (clean, no conflicts): merge commit `4f30a0d9`. The merge brings main's own test edits (`tests/features/infinite_memory_agent/test_infinite_memory_delegation.py` +1 test, `tests/test_context_compaction_tools.py`, `tests/test_deterministic_compaction_middleware.py`, `tests/test_error_correction_algorithm.py`).
- No S3 commit edits a test: `git log --first-parent acfec7a8..HEAD -- tests` lists only the merge `4f30a0d9`, and `git diff 4f30a0d9..HEAD -- tests` is empty.

## Commits (first parent, after the merge 4f30a0d9)

P1 (read window, masking scope, grep options, low watermark, FTS5 index):
- 241908f9 LineLimit + `FileSystemToolConfig.max_read_lines` (rows 1); 5b38667a coding uses LineLimit (row 2); 9d17f4dc read_lines window + footer (row 3)
- 71fdc609 windows.py (row 4); a179fea2 engine forwards (row 6); ab4f1b58 builders validate (row 7); b1ada9fb exports (row 8); feb52a2d strategies.py drops the moved classes (row 5)
- 386691e4 CODE_SEARCH_MAX_FILE_BYTES (row 9); d8bf47b3 grep smart_case/context_lines (row 10)
- 5717db86 FullText records (row 11); 1ec5d442 FullTextIndex (row 12); 8fbdb71f lazy util export (row 13)
- fixups: a81862dc (row 12, C002/S051), 7ebf289c (row 13, C003), 7ecb8109 (row 3, A007), 46a15421 (row 4, S051), 48415efc (row 7, S008)
- docs: 59e40d24 tools README (row 52 part), 4f216acc lib README (row 54)

P2 (SDK-wide):
- f7f687cc bash head+tail (row 14); f98113a5 Anthropic block-level cache marks, repeat-gated (row 15)
- docs: 0f23997f agents README (row 51 part), fe482c86 providers README (row 53)

P3 (InfiniteMemory wiring, stable prefix, compact cards):
- bed91bfe constants (row 16 part); fe206039 masked_output + map_update leaves (rows 33-35, 44 part)
- fa4df4f8 InfiniteMapSnapshot (row 26 part); aabe26fe map_snapshot + fit_map_lines (row 24); 249e4680 stable system string + status message (row 25)
- 81d94850 `InfiniteWorkspaceSettings.max_read_lines` (row 17 part); b0d021ce agent/launch/toolset wiring (rows 18, 22, 23 part)
- 8c84ce48 prompt clauses (rows 45-49 part); 14699c0c infinite README (row 50 part); 100edc4e prompts README (row 55 part)

P4 (search_memory):
- f7d72b8c caps, bookkeeping names, reserved name (row 16 part); 5c97421c InfiniteSearchMemoryTool (rows 20, 21); 8789adb4 shared index on the workspace + toolset (rows 18, 19, 24 part)
- 72e55f4e prompt clauses + map header (rows 45-48 part); e9d76b3b, 09a207d0, 21cb8285 READMEs (rows 50-52 part)

P5 (opt-in recall):
- f993d519 recall constants (row 16 part); 5ccc4926 InfiniteRecallMode + exports (rows 29-31); 8c2b6b81 contract (row 32)
- 3f2a80f7 recall records + parser (row 26 part); 03c9d1d3 registry (row 28); 66598a2e `recall_mode` (row 17 part)
- 822783c2 eight leaves + Prompt members (rows 33, 36-44); ee13dbdd memory `settings` + `recalled` (row 25/27 part)
- a89d686e recall.py (row 57); 3221619e builder entry (row 27); c80bea8e withheld filter (rows 22, 23 part)
- 8b5a1830 root/generator recall clauses (rows 46, 47 part); a9729cfa constants budget sum; 0a58ce43 infinite README; 4f8e789a prompts README (rows 50, 55 part)
- lint fixups: 06b148b2 (search_memory S062 x2, S051, S024), e21463fe (S009 x5: enum at the registry call sites, blank defaults in recall)

## Data flow

1. Read window: `InfiniteWorkspaceSettings.max_read_lines` (200) -> `InfiniteMemoryAgentTools` -> `FileSystemToolConfig.max_read_lines` -> `ReadLinesTool` returns at most the window and a footer naming `start=`; `LineLimit` now backs both the read window and `max_rewrite_lines`.
2. History: every InfiniteMemory agent's middleware is masking first (`windows.ToolOutputSlidingWindowCompaction(tools=INFINITE_MASKED_TOOL_NAMES)`, placeholder = `masked_output` leaf), then the trim (`TrimWithProviderBoundariesCompaction(max_tokens=90K, low_watermark_tokens=65K)`), then delegation limits.
3. Stable prefix: the runtime draws the map once (`map_snapshot` -> `fit_map_lines`) into the root's system string; after each tool iteration `_after_tool_iteration` appends one capped status message (`map_update` leaf) with the loop counter and what changed. The Anthropic adapter then marks `tools`/`system` (and the last message) with block-level ephemeral `cache_control` only when the same tools+system digest was already sent.
4. search_memory: `InfiniteWorkspace.full_text` (one `FullTextIndex`, in-memory SQLite FTS5) is shared by every agent; each call refreshes changed files by `(st_mtime_ns, st_size)` and searches, in one worker thread under the index lock.
5. recall (DELEGATED only): `recall_mode` -> `InfiniteMemoryToolRegistry.tool_names/withheld_tool_names` -> root/generators hold `recall` instead of `grep`. `InfiniteRecallTool.execute` validates `InfiniteRecallRequest`, checks the per-agent quota (10), pre-searches up to 8 terms with search_memory, runs a fresh read-only retriever `BaseAgent` (grep, read_lines, search_memory; 8 turns), parses its FOUND/NOT FOUND lines with `InfiniteRecallCitation.parse`, copies each cited entry (live entries only) or line range (scoped, non-bookkeeping, within the window and the file) from disk, and renders `recall_card` capped at 1,500 tokens, found section last.
6. Small cards: an accepted pair's card to the parent is one line plus the summary (W-5.1, in launch.py).

## Rows ticked (§12.3)

- [x] 1-15 (P1/P2), [x] 16-27 and 57, [x] 28-33, [x] 34-44 (10 new leaves + json), [x] 45-49 (named clauses only), [x] 50-55 (READMEs)
- [x] 56 by its condition: A007 never reports IMPROVED (255 = baseline on main and on the branch), so nothing is lowered; see deviation D-9.
- §12.4: all items held (frozen/slots validated records; enum placement/exports; settings fields last via RecordFieldConverter/Validator; A001 headers on the 4 new modules; narrated mains; 72-col comments, A002 clean; no A007 literal defaults; A006 direction; no numbers in leaves; leaves registered; S025 no new finding; SQLite and reads via `asyncio.to_thread`; no new C006; recall catches only VidbyteSdkError/OSError/ValueError; budget below; strategies.py < 1,000; READMEs < 40,000 chars; contract current; no suppressions, no baseline raised).
- §12.5: README rows 50-55 done; contract regenerated; exports added (`vidbyte/__init__.py`, `lib/enums/__init__.py`, `lib/util/__init__.py`, `code_search/__init__.py`); PR body items and the post-merge real-key run are S6/after-merge actions, not S3's (the draft PR uses the WIP body the orchestrator supplied).

## Budget used (§8.4)

- New files: 14 of 14 (4 modules + 10 prompt leaves). New modules: 4 of 4 (`windows.py`, `fulltext.py`, `search_memory.py`, `recall.py`).
- `vidbyte/agents/infinite/`: 9 of 9 `.py` files; lines after header: launch 381, workspace 349, memory 264, recall 233, settings 203, journal 156, runtime 151, agent 124, `__init__` 13 (all <= 400).
- Context sum restated: root prompt 2,321 tok; most tools one agent holds 6,733 (root/generator, FULL + DELEGATED; 6,378 under DIRECT); map 8,000; history 90,000 -> about 107,000 of 128,000.

## Files touched outside §12.3

- None. `git diff --name-only 4f30a0d9 HEAD` minus tests lists only §12.3 row files (row 56's `lint/baseline.json` untouched by its condition).

## Deviations

- D-1 row 13: `FullTextIndex` is a lazy export (`_LAZY_EXPORTS` + `__getattr__` with a static import); an eager import made `import vidbyte` fail through `validation.py -> lib.util -> fulltext -> code_search -> validation`.
- D-2 row 12: `search` checks `limit`/`snippet_tokens` with `RecordFieldValidator.require_int` and re-raises `ValueError` (the inline guard was a new C002); new constants `FULLTEXT_MIN_HITS`, `FULLTEXT_SNIPPET_MIN_TOKENS` keep A007 clean.
- D-3 row 1/3: the read cap local is `window`, not `limit` (a local named `limit` pulled existing literals into A007).
- D-4 row 7: the low-watermark check builds the trim for every mode (None passes) so `_validate_options` stays within C901.
- D-5 row 14: `_render(exit_code: int | None)`; row 15 helpers at call depth 2.
- D-6 P3/P4: render -> finished_lines and map_text -> map_snapshot are depth 2 (spec-mandated split); the snapshot is taken before the map is drawn; search_memory's execute -> `_lookup` -> rows helpers; search_memory skips a file that raises OSError mid-refresh; `InfiniteMapSnapshot` does not use `one_line`; generator line 26 had no P3 clause to change.
- D-7 P5 order: rows 29-31 in one commit with the contract separate; the memory `settings` keyword (row 27 part) landed before recall.py because recall reads `memory.settings`.
- D-8 recall details the spec leaves open: a found range is labelled by its resolved workspace-relative POSIX path, a rejected line rebuilds the citation from the parsed path; `_sort` also catches `ValueError` (int digit limit); the retriever-failure result and the rejection reasons are inline code text (they carry numbers, so they are not leaves); `cast(int, ...)` narrows range fields; the withheld tool is the literal `"grep"` (no grep name constant exists); call sites pass `InfiniteRecallMode(settings.recall_mode)` because §9.2 types the field `InfiniteRecallMode | str` and the registry `InfiniteRecallMode`.
- D-9 row 56 / NFR-0.3: no baseline count is lowered. The same `lint/run.py` on the main base tree (scratch copy of 845a4d9b) and on this branch report identical counts for every rule; the eight IMPROVED verdicts (A002 703->562, C011 2->1, S001 59->56, S009 350->346, S010 5->0, S025 263->261, S061 6->5, S063 4->3) are main's own stale baseline, not this PR's change, and lowering them to Windows counts risks a CI mismatch.
- D-10 docs: the README and constants header restate the budget as about 107,000 tokens (was 105,000 with "about 5,000" of tools).

## Gates (final lines)

All run at e21463fe (code HEAD) on Windows, Python 3.11.0.

- Feature tests: `python -m pytest tests/features/infinite_memory_agent -q` -> `166 passed in 13.09s`.
- Lint: `PYTHONIOENCODING=utf-8 python lint/run.py` -> last lines `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` (exit 0). The P5 run before the two fixups failed with S009 351/350, S024 26/25, S051 260/259, S062 891/889; all nine new findings were in this branch's files (search_memory.py, agent.py, launch.py, memory.py, recall.py) and are fixed in 06b148b2 and e21463fe, not baselined.
- Main-base comparison: the same lint on a scratch copy of 845a4d9b -> `SDK-LINT: PASS` with the same count for every rule as the branch.
- Source gate: `PYTHONPATH=<worktree> python scripts/run_ci.py --stage source` -> `SDK-LINT: PASS`, `context write-path integrity: ok`, `context primitive introductions: ok`, `reasoning trace contracts: ok (182 tools, 55 shapes)`, then pytest `3 failed, 6365 passed, 16 skipped in 152.26s` / `CI failed: Command failed with exit code 1: ... -m pytest`. The 3 failures are the `harness_threads` surface tests the spec (§11 line 991, §13 line 1295) lists as known pre-existing; never edited:
  - `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails on main itself (`assert 148 == 120`; reproduced on the main-base copy with an `origin/main` ref: `1 failed, 8 passed`).
  - `::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` fails on any branch that changes `vidbyte/tools` (rows 3, 9, 10, 14, 18-21, 52 must).
  - `::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` compares the root `__all__` with the merge base, so FR-10.1's `InfiniteRecallMode` export fails it; the no-process and no-native-import parts pass.
  - GitHub CI checks out at depth 1 with no `origin/main`, so all three skip their base comparison there.
- Package gate: `python scripts/run_ci.py --stage package` (no PYTHONPATH) -> `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` (exit 0).
- Contract: `python scripts/generate-sdk-public-api.py --check` -> `contracts/sdk-public-api.json is current at 5ccc4926... (vidbyte-sdk 0.3.0, 645 exports).`
- Semgrep 1.181.0 (fresh venv, `mcp<2`): `--test` -> `1/1: ✓ All tests passed`; `scan --error` over `vidbyte` -> `Ran 1 rule on 987 files: 0 findings.` (exit 0).
- Tests untouched: `git log --first-parent acfec7a8..HEAD -- tests` lists only the merge 4f30a0d9; `git diff 4f30a0d9..HEAD -- tests` is empty.

## Tricky parts

- Import cycle: eager `FullTextIndex` export broke `import vidbyte`; fixed with the lazy-export form S015 accepts.
- Lint traps around names: A007 keys on parameter/local names (`limit`, `bytes`), so renames (`window`, `CODE_SEARCH_MAX_FILE_BYTES`) avoided new findings; S062 flags adjacent literals in tool descriptions; S024 counts `with`/`for`/`try`/`if` depth (search_memory's refresh moved the replace after the try).
- The contract generator refuses uncommitted inputs, so rows 29-31 were committed before regenerating row 32.
- `recall` must not trust the retriever: citations are parsed line by line and every byte on the card's found section is read from disk by code (entries via `workspace.entries`, ranges via `ReadLinesTool` after `FileSystemPermissions.resolve_scoped_path`), with bookkeeping parts compared casefolded.
- Semgrep: the global install and older venvs fail on mcp 2.x; a fresh venv with `mcp<2`, put first on PATH (its `semgrep.exe` calls `pysemgrep` from PATH), runs it.
