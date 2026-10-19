# S5 repair iteration 2 — harness-browser-tools

Stage: S5 repair, iteration 2 of 8 · Branch `feat/harness-browser-tools` · Start HEAD `68105f8d` · Code HEAD `a44fb17f` (pushed; CI 39098798395 and Static policy 39098799553 green on it) · PR https://github.com/cerredz/Vidbyte-SDK/pull/1183 · Log: `verify-log.md` iteration 2.

This iteration was deliberately narrow. It fixed one confirmed finding, R-C1, with a one-word change to an error text, and it recorded R-C2 as a follow-up for the S6 PR body. It changed no test, lint baseline or CI config. Every local gate is green apart from the one failure inherited from `origin/main`, and both remote workflows are green.

## Gate matrix

| Gate | Command | Result | Final lines |
|---|---|---|---|
| R-C1 reproduction | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 scratchpad/s5r2/rc1_repro.py` | PASS (red on 68105f8d) | `VERDICT: TRUE` · `keeps 'no mounted tool was used': True` |
| focused: lifecycle | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/harness_threads/test_harness_threads_browser_lifecycle.py` | PASS | `33 passed, 1 skipped in 45.26s` |
| focused: mounts | `… test_harness_threads_browser_mounts.py` | PASS | `51 passed in 56.61s` |
| R-1 wide-comment scan | `bash scratchpad/s5/widecomments.sh` | PASS | prints nothing, exit 0 |
| lint | `PYTHONPATH=$(pwd) py -3.11 lint/run.py` | PASS | `A002 IMPROVED 703 -> 562` · `A007 RATCHETED: 255` · `S024 RATCHETED: 25` · `S064 RATCHETED: 4` · `SDK-LINT: PASS` |
| area | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads tests/features/codex_host` | PASS except 1 inherited | `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`) · `1 failed, 818 passed, 3 skipped in 189.11s (0:03:09)` |
| full source gate | `PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source` | PASS except 1 inherited | `SDK-LINT: PASS` · `context primitive introductions: ok` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `1 failed, 6628 passed, 17 skipped in 245.02s (0:04:05)` |
| package gate | `py -3.11 scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote: Static policy | run 39098799553 on a44fb17f | PASS | `✓ All tests passed` · `Findings: 0 (0 blocking)` · `Ran 1 rule on 1016 files: 0 findings.` |
| remote: CI | run 39098798395 on a44fb17f | PASS 3/3 | Source 3.11 `6441 passed, 205 skipped in 149.88s` · `CI passed.`; Source 3.12 `SDK-LINT: PASS` · `6441 passed, 205 skipped, 19 warnings in 149.37s` · `CI passed.`; Package `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |

The single local failure, `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`AssertionError: assert 167 == 120`), is inherited: it fails identically on origin/main, and CI skips it because CI has no `origin/main`. The MCP stdio Windows flake did not occur, and the source gate was not killed for low memory.

The docs-only commit that carries this report and the log entry was pushed after the runs above, and both workflows were dispatched again on it. Their run IDs and results are in the STATUS block.

## Per finding

### R-C1 [Minor, trivial] — fixed @a44fb17f
**Claim.** After R-2 (fb8c0508), Grok counts a mounted server only when `available_commands` lists it or a call to it completed. When the model calls a mounted server that never connected, the SDK records the failed "Tool not found" call and names the server as missing. `BROWSER_TOOLS_UNAVAILABLE_DETAIL` (`vidbyte/lib/constants/browser_tools.py:398`) still said the output shows "neither a connection to nor a call on" that server.

**Reproduced before the fix.** The scratch script `rc1_repro.py` runs in memory; it writes no files and makes no vendor call. It builds a Grok JSON stream with four events:
1. `available_commands` without jina;
2. a `tool_call`/`use_tool` with `rawInput.tool_name = "jina__read_url"`;
3. a `tool_call_update` with status `failed`;
4. a normal `end`.

It then runs the shipped `GrokWire.tool_calls`, `GrokBrowserHarness.missing` and `NativeBrowserTools.require`. On 68105f8d it printed:

```
GrokWire.tool_calls -> (BrowserToolCall(tool=<BrowserTool.JINA: 'jina'>, name='read_url', status=<BrowserToolCallStatus.FAILED: 'failed'>),)
missing -> (<BrowserTool.JINA: 'jina'>,)
raised code -> browser.tools_unavailable
… The vendor's output shows neither a connection to nor a call on these mounted servers, so no mounted tool was used on them: jina. …
FACTS: a call on a missing server recorded=True, completed=False
VERDICT: FALSE (R-C1 reproduced)
```

The control run (argument `completed`) gave `missing -> ()` and raised nothing.

**Fix.** "nor a call on" became "nor a completed call on"; the rest of the sentence is byte-identical. The new text is true for every harness that reaches `require`:
- Grok raises only when a server was not listed and no call to it completed.
- opencode raises only when `calls.calls` is empty, so no call of any kind was made (`opencode/browser.py:114`).
- Muse's `missing` always returns `()`.

**Alternative rejected.** A Grok-only detail constant would add a constant with one caller and a per-harness branch in the shared `require`, while one word makes the shared sentence true.

**Comments and other copies.**
- Neither the constant's block comment (spec D-29 observation details) nor the file header quotes the wording, so no comment changed.
- The `require` `@intent` says "never shows connected or used". A failed call is not a use, so that comment stays accurate.
- `git grep` finds the sentence nowhere else except the historical pipeline.md entry.

**After the fix.** The script prints `VERDICT: TRUE` and `keeps 'no mounted tool was used': True`, the substring the opencode tests assert (lifecycle :45, mounts :358). Lifecycle gives 33 passed, 1 skipped, and mounts gives 51 passed.

### R-C2 [Minor] — follow-up (S6 PR body), not implemented by decision
The positive half of the r5 Grok rule has no test: a server absent from `available_commands` still counts once a call to it completed. Mutant M2 survives every browser file. The fix needs a new fake-Grok scenario key in the test tree, and the orchestrator froze the test tree for this iteration. Recorded in review.md with status `follow-up (S6 PR body)`.

## Test changes proposed
None. `git diff 68105f8d..HEAD --stat -- tests/` is empty.

## Findings I believe are wrong
None. R-C1 reproduced exactly as the re-review described it.

## What remains open, and what I would try next
- **R-C2** (test tree), for S6 or a later test-author pass:
  1. In `tests/.../fake_browser.py`, add a fake-Grok key, `grok_listed_late: [tool]`, that starts the server and answers its calls but leaves its tools out of `available_commands`.
  2. Add one case beside `test_grok_names_each_server_it_never_listed` that calls the tool and expects a `BrowserThreadResult` with the COMPLETED call.
  3. Narrow test-plan EC-16 (:91) to the timing half only.

  Then check it with mutant M2 (`seen = set(GrokWire.connected(run.outcome, mount))`): the new case must fail under M2.
- **R-11–R-15, R-18, R-19**: unchanged follow-ups for S6.
- **Inherited**: `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, from origin/main.

## Scratch files (outside the repo)
`C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/1da32edd-ec0f-4839-ba1f-52db538ed13c/scratchpad/s5r2/` holds:
- `rc1_repro.py`, the in-memory R-C1 check (pass `completed` for the control run);
- `lint.txt`, `area.txt`, `source_gate.txt` and `package_gate.txt`, the full local gate outputs;
- `static_watch.txt` and `ci_watch.txt`, the remote watch outputs.
