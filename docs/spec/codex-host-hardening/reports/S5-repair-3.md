# S5 repair, iteration 3 of 8: codex-host-hardening (slice 1 of 2)

- **Branch and PR:** `feat/codex-host-first-class`, draft PR #1181. It stacks on `origin/ai/resolve-pr-1055-comments` (#1178).
- **The run:** it started at HEAD `0b757ec2` and ended at `14509eda` for the fix, plus one docs commit after that. The contract was spec r6 and the tests at S2_HEAD `68562b22`.
- **The interpreter:** `V` = `scratchpad/venv-codex163/Scripts/python.exe`, CPython 3.11.0 with openai-codex 0.163.0, editable from this worktree.

## Result

The one open finding, m-9, is fixed in one docstring-only commit, and no test changed. Every gate is green apart from the one inherited failure, which this branch cannot affect.

| ID | Severity | Commit | Root cause | Fix |
|---|---|---|---|---|
| m-9 | Minor | `14509eda` | The three row 16–18 methods were written with `#` summary comments and no docstrings. So `help()` gave a caller nothing, and the title-only limit (NG-10) existed only as a code comment on `search_codex_threads` and in the tool description. | Each two-line comment became a docstring that says what the method returns and states the NG-10 limit. The code is unchanged. |

## Gate matrix (all run in this worktree, this iteration, at `14509eda`)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| m-9 reproduction, before | `PYTHONPATH=$(pwd) "$V" -c "from vidbyte.harnesses.native.codex.host import CodexHost as H; print([(n, bool(getattr(H, n).__doc__)) for n in ('list_recent_codex_threads','list_codex_threads_since','search_codex_threads')])"` at `0b757ec2` | reproduced | `[('list_recent_codex_threads', False), ('list_codex_threads_since', False), ('search_codex_threads', False)]` |
| m-9 check, after | the same command at `14509eda` | PASS | `[('list_recent_codex_threads', True), ('list_codex_threads_since', True), ('search_codex_threads', True)]`. `inspect.getdoc` of each contains both "title" and "content". |
| docstring-only proof | `ast.dump` of `git show 0b757ec2:…/host.py` and of the worktree file, each with every module, class and function docstring removed (a scratchpad snippet run with `-I`) | PASS | `docstrings head/new: 15 18` / `AST identical without docstrings: True` |
| new tests (area) | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` | PASS (1 failure, inherited) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`<br>`1 failed, 1057 passed, 3 skipped in 75.63s (0:01:15)` |
| lint | `"$V" lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline`<br>`S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all`<br>`SDK-LINT: PASS` |
| ruff (repo config) | `"$V" -m ruff check <the 23 .py files the PR adds or modifies under vidbyte/> --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045,F --no-cache` | PASS | `All checks passed!` |
| semgrep (per file) | `"$V" -I scratchpad/s5-repair-2/run_semgrep.py .semgrep/typed-mapping-boundary-policy.yml <the same 23 files>` | PASS | `runs=23 results=0 errors=0`<br>positive control on `.semgrep/typed-mapping-boundary-policy.py`: `RESULT … no-untyped-mapping-fallback 6` / `RESULT … no-untyped-mapping-fallback 19` / `runs=1 results=2 errors=0` |
| comment width | `"$V" -I scratchpad/s5r1_wide_comments.py origin/ai/resolve-pr-1055-comments`, restricted to `vidbyte/` | PASS | 0 lines under `vidbyte/`. The scan prints `TOTAL added wide comment lines: 195`, and all 195 are in `tests/` (S2's). The added docstring lines were also checked directly, and none is over 72 columns. |
| test contract | `git diff 68562b22..HEAD -- tests \| wc -l` | PASS | `0` |
| full local gate (source) | `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source`, run alone (second run) | FAIL: 1, inherited (lint, compileall and the three check scripts pass) | `SDK-LINT: PASS` … `reasoning trace contracts: ok (182 tools, 55 shapes)`<br>`FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`<br>`=========== 1 failed, 6588 passed, 27 skipped in 151.87s (0:02:31) ============`<br>`CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| full local gate (package) | `"$V" scripts/run_ci.py --stage package`, with no PYTHONPATH | PASS | `No broken requirements found.`<br>`Installed vidbyte-sdk 0.3.0 passed smoke checks.`<br>`CI passed.` |
| remote checks | `gh pr checks 1181` | none configured | `no checks reported on the 'feat/codex-host-first-class' branch`, after pushing `9c958640..14509eda` |

The full logs are in `scratchpad/s5-repair-3/`: `area.txt`, `ci_source.txt` (the clean run), `ci_source_run1_loaded.txt` (the flaked run) and `ci_package.txt`.

## m-9: what I did, with evidence

### The requirement, read from the source documents

- **FR-36** (spec.md:664) says the accepted rows "4's round trips, 9, 10, 12, 13, 14, 16–18, 21, 22" are "documented in the docstrings of their functions (§3 NG-5…NG-12, NG-20; AC-39)".
- **Rows 16–18** (request.md:226) are `list_recent_codex_threads`, `list_codex_threads_since` and `search_codex_threads`, listed as "X4 and X5. Search matches titles only."
- **X4 and X5** (request.md:194, :197) are the cross-cutting retry and `thread/read` classification gaps, which this slice fixes: X4 through `CODEX_HOST_RETRIED_METHODS` (D-7, spec §8.4), and X5 through INV-4 and D-8 (the `CodexHardeningClassificationTests` docstring). So the only accepted limit on these rows is **NG-10** (spec.md:99): "Content search (rows 16–18 match titles only) … Content search is P1 `search_codex_thread_content` (slice 2)."
- **AC-39's keyword for NG-10** is `title` (`test_codex_host_hardening_contract.py:610`), and it checks only `list_codex_threads`. That is why no gate caught m-9.

### What the two listings should say

`list_recent_codex_threads` and `list_codex_threads_since` take no query, so "matches titles only" is not literally their behaviour. The honest NG-10 statement for them is that nothing in them filters by text, and that the one helper that does, `search_codex_threads`, matches titles only, not content. That tells a caller looking for content search where the boundary is, and it claims nothing false. `search_codex_threads` states the limit directly.

### Every claim checked against the code, not the old comment

| Docstring claim | Where the code does it |
|---|---|
| newest first | `thread_helpers.py:266`: `_list_page` sends `CodexThreadSortKey.UPDATED_AT`, `CodexSortDirection.DESC` |
| every top-level source, the SDK's own included | `CODEX_HOST_HELPER_SOURCE_KINDS` (`vidbyte/lib/constants/codex.py:403-409`: CLI, VSCODE, EXEC, APP_SERVER, UNKNOWN) |
| no preflight check is sent | thread-helpers spec INV-10: no `account/read`, `account/rateLimits/read`, `windowsSandbox/readiness` or `model/list`. Enforced by the tests' `PREFLIGHT_METHODS` (`test_codex_host_thread_helpers.py:38-39`). "Preflight" is the word `host.py`'s own docstrings use ("after one preflight"). |
| updated at or after since; since in Unix seconds; an empty window is () | `_collect` stops at `thread.updated_at < since` (`thread_helpers.py:274`); thread-helpers D-9 |
| up to limit | the walk stops at `len(summaries) >= limit` (`thread_helpers.py:278`) |
| title matches query | the query is sent as Codex's `searchTerm` (thread-helpers FR-3, D-6); NG-10 |

I left out "in cwd". `CodexThreadListing` accepts a blank `cwd` (`require_text(..., allow_blank=True)`, `codex_host_inputs.py:314`), so the phrase would not hold for every call.

### Decisions

- **Convert all three comments, not only search's.** The briefing asked for search's comment to become the docstring "instead of keeping both". The other two comments were summaries of the same kind, sitting at the top of three-line methods. A docstring that says what the method returns, with the comment kept below it, would say the same thing twice. The `host.py` methods that have both a docstring and a comment use the comment for an `# @intent` rule, which these do not have.
- **No spec IDs in the docstrings, against the briefing's example "(NG-10)".** No function or class docstring anywhere in `vidbyte/harnesses/native/codex/` cites a spec ID: an `ast` scan for `(INV-|NG-|D-|EC-|AC-|FR-n` matched none. IDs appear only in `#` comments and in file headers. The briefing also said "match the voice of the neighbouring docstrings", and the package's grain wins. The pointers the comments carried remain traceable:
  - INV-11 and D-7 sit on the enforcing code at `thread_helpers.py:263-264`, INV-12 and INV-14 at `:270-272`, and D-8 at `:92`;
  - thread-helpers INV-10 and D-9 are cited by the tests at `test_codex_host_thread_helpers.py:38,103,179`;
  - D-6 (why the thin wrapper exists) is in the thread-helpers spec, which `host.py`'s RELATED DOCS names.

  **Flip condition:** if the orchestrator wants "NG-10" in the `help()` text, add it after "content" in the search docstring. That is one token, and the line stays at 72 columns or less only if "thread" is dropped.
- **Summary line plus body, every line 72 columns or less.** The briefing asked for one line where possible and for every line wrapped at 72 columns, counting the indent. With an 8-space indent and the quotes, a one-liner leaves 58 characters, which cannot hold both what the method returns and the limit without losing meaning. The multi-line form matches `wait_codex_turn`, `forget_codex_turns` and `launch_codex_subagents` in the same file.

### The diff (the whole source change)

```python
    async def list_recent_codex_threads(self, cwd: str, limit: int = …) -> tuple[CodexThreadSummary, ...]:
        """Up to limit threads of every top-level source, newest first.

        The SDK's own threads are included, and no preflight check is
        sent. Nothing here filters by text; search_codex_threads
        matches thread titles only, not their content.
        """

    async def list_codex_threads_since(self, cwd: str, since: int, limit: int = …) -> tuple[CodexThreadSummary, ...]:
        """Up to limit threads updated at or after since, newest first.

        since is in Unix seconds, and an empty window is (). Nothing
        here filters by text; search_codex_threads matches thread
        titles only, not their content.
        """

    async def search_codex_threads(self, cwd: str, query: str, limit: int = …) -> tuple[CodexThreadSummary, ...]:
        """Up to limit threads whose title matches query, newest first.

        Codex matches query against titles only, not thread content.
        """
```

That is 16 lines added and 6 removed, in one file. `host.py` grows from 927 to 937 lines and stays LF. The §8.4 budget counts files, classes, config keys and endpoints, so it is unchanged. The `@intent` lint (A002) is not affected, because none of the three has an `@intent` line, and lint passes.

## Test changes proposed

None. FR-36 is P2, and the orchestrator verifies `__doc__` directly. `git diff 68562b22..HEAD -- tests` is 0 lines.

## Disputed findings

None.

## Observations, none of them a failure

- **A load flake in the first source-stage run.**
  - **What failed:** the first run gave `2 failed, 6587 passed, 27 skipped in 143.41s`. The extra failure was `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`, which raised `McpProtocolError: MCP request timed out` at `vidbyte/tools/mcp/transport.py:285` with `timeout = 5.0`. Its captured log shows `Close running child process: kill <_WindowsSubprocessTransport …>`.
  - **Why it is not this branch:** that run overlapped my semgrep and comment-width runs. `git diff origin/ai/resolve-pr-1055-comments...HEAD -- vidbyte/tools/mcp/ tests/test_mcp_stdio_transport.py` is empty, and this iteration's diff is `host.py` docstrings only, with an identical AST.
  - **Evidence:** the test passed 5 of 5 alone (0.80–0.86 s each, against the 5 s timeout), and its module passed 22 of 22. A second full source-stage run with nothing else running gave `1 failed, 6588 passed, 27 skipped`, identical to iteration 2.
  - **Rerunning was not weakening the gate:** the whole stage was rerun, unfiltered. The flaked log is kept as `scratchpad/s5-repair-3/ci_source_run1_loaded.txt`.
- **Lint still prints `S063 IMPROVED 4 -> 3`,** as it did at iteration 2. It comes from outside this change, and the briefing forbids `lint/` edits, so the baseline stays as it is.
- **The push also published two orchestrator docs commits.** The remote was at `9c958640`, so `af912f37` and `0b757ec2`, which were local only, went up with `14509eda`.

## What remains open

- **Findings:** none of R-1 to R-12, m-8 or m-9.
- **Minor follow-ups,** as routed earlier: m-2's method-key half, m-3, m-4, m-5, m-6 and m-7.
- **The inherited failure:** `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`). `git diff origin/ai/resolve-pr-1055-comments...HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads/` is 0 lines.

## Next move this opens

AC-39 checks NG-10 only on `list_codex_threads`, so a later edit could drop the limit from these three docstrings again with every gate green. The test author could add the three rows to AC-39's keyword table (`("list_recent_codex_threads (NG-10)", …, ("title",))`, and so on). That is a test change, so it is out of scope here and needs the orchestrator's approval.
