# S6 PR author report: InfiniteMemoryAgent context economy

PR: https://github.com/cerredz/Vidbyte-SDK/pull/1177 (draft, base `main`). Final head: `568e8631` (`docs(spec): correct the test-file counts and two wordings in the PR body`), after `f7753650` (`docs(spec): finalize infinite-memory-context-economy for PR`). Code head: `335dd847`. Everything after `335dd847` changes only `docs/spec/`.

This report is written after the final push and is not committed, so the PR head and its green checks stay on `568e8631`. Commit it with the orchestrator's own docs commit if wanted.

## 1. What the code does (written from the diff before opening the spec)

I read `git diff origin/main...HEAD` for every changed source file before opening the spec. My notes, unedited after that point, are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s6-code-understanding.md`. In short:

1. **read_lines window.** `FileSystemToolConfig.max_read_lines` (checked by `LineLimit`, renamed from `OverwriteLineLimit`). `ReadLinesTool.execute` cuts the selection to the window and appends `[lines a-b of N shown; read on with start=K]`, with `truncated`/`total_lines`/`next_start` metadata. The spec sentence is added only when a window is set. `InfiniteWorkspaceSettings.max_read_lines` defaults to 200 and reaches every agent through `InfiniteMemoryAgentTools.get_tools`.
2. **Masking.** `windows.ToolOutputSlidingWindowCompaction(tools=...)`. Scoped outputs older than the newest 3 per tool become the `masked_output` leaf in STRIP mode. Outputs after the newest model turn (`assistant` or `model`) stay whole but still count. Root, pair children and the retriever all install it first.
3. **Grep.** `GrepTool(smart_case=False, context_lines=2)` constructor options. Smart case means IGNORECASE when there is no capital, after regex escapes are dropped. The description gains sentences only for non-default options. The InfiniteMemory toolset sets `smart_case=True, context_lines=0`.
4. **Trim hysteresis.** `TrimWithProviderBoundariesCompaction(low_watermark_tokens=...)`. When set below the cap, the trim drops the shortest prefix of non-system groups that reaches the next multiple of S = max − low above the overflow. It is a pure function. `None`, or a value at or above the cap, gives main's greedy fit. InfiniteMemory uses 90K/65K.
5. **Cards.** `InfinitePair.render`: a done card with a passed or fixed verdict is the `finished_lines` line plus the summary. Every other card is whole.
6. **Bash.** Head H = 50,000 − T, rolling tail T = min(25,000, cap // 2), and the count of omitted bytes in a one-item list that survives `wait_for`. The timeout path renders through `_render(exit_code=None)`.
7. **Stable root prefix.** `InfiniteMemoryRuntime` takes `map_snapshot()`, then draws the map once in `arun`. `_build_system_string` drops the loop block. `_after_tool_iteration` takes the snapshot with `asyncio.to_thread`, diffs it by path, cuts the change lines with `InfiniteWorkspace.fit_map_lines`, and appends one user message: `map_update` + block, or the block alone, or nothing.
8. **search_memory.** `lib/util/fulltext.FullTextIndex` is an in-memory FTS5 index (`porter unicode61`): lazy open, an RLock, quoted AND matching, bm25, snippets, and deletes by recorded rowid range. `code_search/search_memory.InfiniteSearchMemoryTool` normalizes NULs and surrogates, then runs `_lookup` in a worker thread under the lock. `_lookup` does a scandir listing with fingerprints, re-reads changed files only (`_entry_rows`/`_note_rows`, with a 2,048-byte NUL sniff), runs `retain`, then `search` (10 hits, 12-token snippets). One index per workspace, shared by the tree.
9. **Anthropic marks.** In `_create_payload`: no caller `cache_control` anywhere, and the sha256 of `[tools, system]` was seen before (`surrogatepass`; set cleared at 256), then mark the system as one text block, the last message, and the message before the newest assistant turn. Marks go on copies only.
10. **recall.** `InfiniteRecallMode` DIRECT (default) or DELEGATED. Under DELEGATED, the registry grants `recall` to the root and generators and withholds `grep` from them; the verifier is unchanged. `agents/infinite/recall.py` runs in this order:
    - validate the request;
    - check the quota (10);
    - pre-search each term;
    - run a retriever `BaseAgent` (grep, read_lines, search_memory; no bash; 8 iterations; the same masking and trim);
    - sort the reply into FOUND, NOT FOUND and rejected lines;
    - copy entries through `workspace.entries` and ranges through the windowed `read_lines`;
    - refuse ranges that are too long, leave the root, end past EOF, or touch a bookkeeping name (casefolded);
    - render the card capped at 1,500 tokens, marker included.

## 2. Snippet (AC-1)

I ran spec §4 lines 90–108 unchanged from the empty folder `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/325553c0-d7b8-426c-a021-9f8cf36c100b/scratchpad/s6-snippet/`, with `PYTHONPATH` set to the worktree's Windows path. Global Python is 3.11.0, and `vidbyte.__file__` resolved to the worktree. The exit code was 0 and stderr was empty. After `tr -d '\r'`, `diff` against the three §4 lines printed nothing (`MATCH`):

```text
[lines 1-200 of 1000 shown; read on with start=201]
True 1000 201
200 True
```

## 3. Deviations (spec vs code)

All appear in the PR body's "Deviations" section. S3 D-1…D-10 are carried from `reports/S3-implementer.md` and §17. The S5 block was added to spec §17 (R-27):

- `_listing` scandir walk instead of `iter_files` (R-7).
- The row helpers' own sniff with `INFINITE_SEARCH_SNIFF_BYTES`, and the cap from the listing's stat only (R-25 and the byte-cap window).
- The R-28 known gap.
- The `_create_payload` gate and the `surrogatepass` digest (R-4, R-6).
- The literal-import lazy export (R-13).
- The pre-search inside the `try`, with the quota slot still spent (R-19).
- The `map_snapshot` off-loop recount (R-14).
- The r5 masking rule (R-3).
- The NUL and surrogate hardening (R-2).
- The `llms.txt:815` row under the extended grant.

§5 was compared with the code at `335dd847`. Every node names a real function (`_build_iteration_call_options` exists at `vidbyte/agents/runtime.py:1596`), and the order of steps matches the code, so §5 was left unchanged. Rows 15, 16 and 20, §8.2:528, §8.5 and §11:1024 were left as written, as the briefing asked.

Count in the body: 16 deviation bullets, covering S3 D-1…D-10 and the S5 items.

## 4. PR state and remote runs

`gh pr view` after the edit:
```
{"baseRefName":"main","headRefOid":"568e8631b6a679b610ef7b9fbeb26dc3d38bb365","isDraft":true,"title":"feat(infinite): windowed reads, masked search output, ranked search_memory, a cache-stable root prompt with Anthropic cache marks, and opt-in recall","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1177"}
```
I fetched the live body with `gh pr view --json body` and diffed it against `tail -n +2 pr-body.md`. They are identical apart from trailing blank lines, and `` `\S` `` survived.

Remote runs. Every run's `head_sha` was read from `gh api .../actions/runs/<id>`. Job results come from `.../runs/<id>/jobs`, and each summary line comes from that job's log.

| Head | Workflow | Run | Result |
|---|---|---|---|
| `335dd847` (code head) | ci.yml | 39023135090 | 3/3 success; 3.11 and 3.12 `6401 passed, 200 skipped`; Package `CI passed.` |
| `335dd847` | static-policy.yml | 39023136622 | 1/1 success, `Findings: 0 (0 blocking)` |
| `f7753650` (spec finalized) | ci.yml | 39025335097 | 3/3 success (jobs 117375097560, 117375097484, 117375829520) |
| `f7753650` | static-policy.yml | 39025336831 | 1/1 success |
| `568e8631` (**final head**) | static-policy.yml | 39025599146 | 1/1 success (job 117375847525), `Findings: 0 (0 blocking)` |
| `568e8631` | ci.yml attempt 1 | 39025597741 | **failure**: 3.11 `6401 passed, 200 skipped`; 3.12 `1 failed, 6400 passed, 200 skipped`; Package skipped |
| `568e8631` | ci.yml attempt 2 (`gh run rerun --failed`, same SHA) | 39025597741 | 3/3 success: 3.12 job 117376702407 `6401 passed, 200 skipped`; 3.11 job 117376703602 `6401 passed, 200 skipped`; Package job 117377213158 `Installed vidbyte-sdk 0.3.0 passed smoke checks.` and `CI passed.` |

Why the attempt-1 failure is a flake and not caused by this PR:

1. The failing test was `tests/features/coding_agent/test_coding_agent_environment.py::test_real_bash_reports_its_version_and_git`, at `assert "Tool probe failed" not in content`. The log line was `Tool probe failed: bash did not finish within 15 seconds.`
2. The probe is `vidbyte/agents/coding_context/environment_probe.py:69`. It calls `subprocess.run` directly, not `BashTool.execute`. `git diff origin/main...HEAD` is empty for `vidbyte/agents/coding_context/`, for `vidbyte/context/primitives/documents.py`, for the `PROBE` constants and for `find_bash`.
3. `git diff --name-only f7753650 568e8631` lists only `docs/spec/infinite-memory-context-economy/pr-body.md`. The same test passed at `f7753650`.
4. The 10 latest failed `ci.yml` runs on other branches (38883212531 … 38834420807, 2026-10-16) each fail on this test alone. It is a known flake on main's runners.

I re-ran the failed job; I did not change any test or code. The live PR body has these final-head rows. The committed `pr-body.md` stops at the `335dd847` rows, because committing them would itself move the head.

## 5. Local evidence gathered in S6

- All 57 test node names cited in spec §6.2 exist on the branch. I checked each with `grep "def <name>"` in its file, and the parametrized ids `[direct]`, `[delegated]`, `[openai]`, `[anthropic]` and `[gemini]` with `--collect-only`.
- The 10 new test files, the 7 edited test files (plus `infinite_memory_fixtures.py`) and the rest of the infinite feature folder gave `329 passed, 11 skipped in 22.62s` at `5379f9f7`. All 11 skips are POSIX-only bash process tests. The reasons, from `-rs`: "stand-in Git layout uses shell scripts" ×4 and "process-group kill … POSIX-only by spec (EC-14)" ×7.
- The 3 inherited `harness_threads` failures are not caused by this PR's code. `test_failure_codes_keep_main…` asserts that the merge-base `FailureCode` has 120 members. `git show origin/main:vidbyte/lib/enums/failure.py` has 167, so the test fails on main itself (merge-base = origin/main = `6f5a7310`). The other two fail for any branch that changes `vidbyte/tools/` or the root `__all__`. All three skip or return early without `origin/main` (CI's shallow clone).
- `git diff origin/main...HEAD -- lint .github .semgrep scripts pyproject.toml` is empty.
- The Mermaid chart parses with `mermaid@11.4.1` under jsdom (`PARSE OK flowchart-v2`). An unclosed node was rejected by the same checker as a control.

## 6. Candidate field-guide lessons (report only; nothing was written to the field guide)

Each lesson gives the trigger, the preferred action, the project-specific reason, a quick check, and the link.

1. **Model-facing prose.**
   - Trigger: writing a prompt leaf or a tool or parameter description.
   - Action: no concrete example lists ("such as a, b, or c").
   - Reason: the field guide's model-facing-tool-contracts rule says "omit concrete examples", and spec row 37 cites it.
   - Check: `grep -n "such as" vidbyte/prompts/prompts/<family>/*.md`.
   - Link: #1177, R-1 (`848469a2`).
2. **Lazy exports.**
   - Trigger: a lazy `__getattr__` export in a package `__init__`.
   - Action: import the module by its literal dotted name inside `__getattr__`, then `getattr(module, name)`. Never `importlib.import_module(table[name])`.
   - Reason: C003 blocks imports whose module name comes from data. `vidbyte.lib.util` cannot import `fulltext` eagerly, because `validation` → `credential_keys` → `lib.util` is a cycle.
   - Check: `PYTHONIOENCODING=utf-8 python lint/run.py --rule C003`.
   - Link: #1177, R-13 (`8da92fb9`).
3. **New numeric literals.**
   - Trigger: any new numeric literal under `vidbyte/`, even `2048`.
   - Action: add a named constant to the domain's constants module and to its `__all__`.
   - Reason: A007 is ratcheted at 255 with zero headroom. One literal turns the gate red, and so does `read_bytes()[:2048]`.
   - Check: `lint/run.py` prints `A007 … 255 255 RATCHETED`.
   - Link: #1177, R-25 (`335dd847`).
4. **Model-turn detection.**
   - Trigger: finding "the model's turn" in normalized `ContextMessage` history.
   - Action: test `role in ("assistant", "model")`.
   - Reason: Gemini's normalized role is `"model"`. Checking `assistant` alone silently turns the logic off on Gemini (reviewers' probe: 2 masked → 0).
   - Check: parametrize the test over the openai, anthropic and gemini wires.
   - Link: #1177, R-3 (`5634b579`).
5. **Digest encoding.**
   - Trigger: hashing JSON built with `ensure_ascii=False` (for example a provider payload digest).
   - Action: `.encode("utf-8", "surrogatepass")`.
   - Reason: Windows workspace file names can carry lone surrogates into the system string. The HTTP transport's `json.dumps` escapes them, so main sends the body, while a strict encode raises on the first request.
   - Check: a unit test with `"\ud800"` in the system.
   - Link: #1177, R-6 (`5698fdab`).
6. **Code-search walk on a warm path.**
   - Trigger: reusing `BaseCodeSearchTool.iter_files` or `is_text_file` on a warm or cached path.
   - Action: list with `os.scandir` and take the fingerprint from that stat. Sniff only changed files with your own `open`/`read(N)`, so an `OSError` propagates and the file is retried.
   - Reason: `iter_files` reads every file (about 470 ms at 2,000 files). `is_text_file` returns False on `OSError`, so a transient lock is cached as empty.
   - Check: count opens in a warm-search test with an audit hook.
   - Link: #1177, R-7 (`7eb2942c`) and R-25 (`335dd847`).
7. **Gates in the main function.**
   - Trigger: adding a gated step to a provider adapter's `_create_payload` (or any main function with `_attach_*` helpers).
   - Action: put the gate condition in the main function and keep each helper a leaf.
   - Reason: AGENTS.md principle 1. On main, no `_attach_*` helper calls another method.
   - Check: an AST scan for a helper → helper call inside the class.
   - Link: #1177, R-4 (`7d6d7449`).
8. **Hand-kept export lists.**
   - Trigger: exporting a new builtin tool from `vidbyte/tools/builtins/*/__init__.py`.
   - Action: also add it to the export line and the tools table in `llms.txt`, and to `artifacts/file_index.md`.
   - Reason: both index exports by hand, and no gate checks them.
   - Check: `git grep -n GrepTool llms.txt artifacts/file_index.md` shows the new name beside it.
   - Link: #1177, R-16 (`7ab9a924`).
9. **Comment width.**
   - Trigger: writing or editing comments in `vidbyte/` source (not tests).
   - Action: wrap every comment line at 72 columns, counting the indent.
   - Reason: `comment-format.md`. Main's source follows it (2.4% over), while its tests do not (66%), so the rule is enforced on source only.
   - Check: awk over `git diff -U0 origin/main -- 'vidbyte/*.py'` for comment lines over 72 columns.
   - Link: #1177, R-5 (`1a6365e6`).

## 7. Things that looked wrong while reading

I found no new defect. Known open items, re-confirmed at the code:

- `vidbyte/tools/builtins/code_search/search_memory.py:123`: "so the next call reads it again" is wrong for a file whose name UTF-8 cannot encode, which is never read. `:9` does not name the byte-cap window (R-RR2-1).
- `vidbyte/tools/builtins/code_search/search_memory.py:220`: the `except` tuple does not catch `RecursionError` from a deeply nested `entries.jsonl` line (R-RR2-2). `vidbyte/agents/infinite/workspace.py:271` (`_entry_lines`) has the same gap, as does main's `workspace.py:254`.
- `vidbyte/lib/registries/infinite.py:76-77` and `vidbyte/lib/constants/infinite.py:137`: the literal `"grep"` and `"read_lines"` (R-17).
- `vidbyte/lib/util/fulltext.py:70` and `:139`: delete and insert run as two transactions (R-20).

One benign observation, not a defect: `AnthropicProvider._holds_cache_control` walks the whole payload, so a tool whose input schema has a property literally named `cache_control` turns marking off for that request. This is the safe direction, and AC-9.3 asks for "anywhere".
