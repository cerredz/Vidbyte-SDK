# S3 report: implementer — browser-agent

Spec: `docs/spec/browser-agent/spec.md` r4 · Branch `feat/browser-agent` · Base `08f67e7f` · S2_HEAD `5db0eaa0` · Draft PR https://github.com/cerredz/Vidbyte-SDK/pull/1182

## Status

**BLOCKED** on one S2 test defect. Every §12.3 row (1 to 28) is implemented and committed. 105 of the 106 browser tests pass. The failing case is `test_browser_agent_recheck.py::test_a_refused_finish_appends_one_gap_message_and_the_next_call_shows_the_verdict[final_text]`. Its own assertion at line 112 is `agent.response.stop_reason == finish`, where `finish == "final_text"` is the parametrize id. The loop has no `final_text` stop reason (`AgentStopReason` in `vidbyte/lib/dataclasses/agents.py`). AC-13 says the run ends `final_response`, and the pack's other final-text tests assert `"final_response"`. I am not allowed to change an S2 test, so the required CI checks stay red until S2 fixes it.

Proof that the implementation is right and only the assertion is wrong: I copied the test module to the scratchpad and changed that one line to `{"final_text": "final_response", "is_done": "is_done"}[finish]`. Both cases then pass, including every assertion after line 112 (the recheck records, the stall count, `run_finished` last). The repository file was not touched.

```
$ python -m pytest <scratchpad>/recheck_probe/test_recheck_probe.py -k refused_finish
2 passed, 9 deselected in 30.23s
```

## What was produced (by §12.3 row, in §12.6 phase order)

| Row | File | Commit |
|---|---|---|
| 1, 2 | `vidbyte/lib/enums/browser.py`, `vidbyte/lib/enums/__init__.py` | 9b2af6f3 |
| 3 | `vidbyte/lib/constants/browser.py` | e9b9eba2 |
| 4 | `vidbyte/lib/dataclasses/browser.py` | 8023c2d4 |
| 5 | `vidbyte/lib/dataclasses/agents.py` (`GOAL_STALLED`) | 0cdd38e3 |
| 6 to 8 | `vidbyte/prompts/prompts/browser_agent/` (19 leaves and `browser_agent.json`), `vidbyte/lib/enums/prompts.py` | 49aab243 |
| 9 | `vidbyte/agents/browser/settings.py` | 95ee418b |
| 10 | `vidbyte/agents/browser/tools.py` | bddcfe23 |
| 11 | `vidbyte/agents/browser/events.py` | cc61b7a3 |
| 12 | `vidbyte/agents/browser/usage.py` | 96e1c718 |
| 13 | `vidbyte/agents/browser/response.py` | e4548302 |
| 14 | `vidbyte/agents/browser/goal.py` | 97d256c3 |
| 15 | `vidbyte/agents/browser/episode.py` | d756dde3 |
| 16 | `vidbyte/agents/browser/runtime.py` | 41984eb8 |
| 17 | `vidbyte/agents/browser/agent.py` | c69c3ad0 |
| 18 | `vidbyte/agents/browser/__init__.py` | 5b347228 |
| 19 to 21 | `vidbyte/lib/enums/agent_runtime.py`, `vidbyte/lib/registries/runtimes.py`, `vidbyte/agents/base.py` | e467131b |
| 23, 24 | `vidbyte/agents/__init__.py`, `vidbyte/__init__.py` | 8183aa6f |
| 25 | `contracts/sdk-public-api.json` (generated) | da05ec25 |
| 22 | `vidbyte/agents/browser/README.md` | 1ca34a54 |
| 26 to 28 | `vidbyte/agents/README.md`, `vidbyte/prompts/README.md`, `REPO_MAP.md` | 0982ad4c |
| spec | frontmatter `pr:` and `status: implemented` | 3833baca |
| spec | §6.2 Proof cells (33), §17 r4 S3 row, Implementation deviations | 6d4c8612 |

Complexity budget (§8.4): 10 modules in `vidbyte/agents/browser/`. Body lines after each header: `__init__` 14, `agent` 86, `episode` 220, `events` 47, `goal` 251, `response` 57, `runtime` 177, `settings` 244, `tools` 38, `usage` 44. All are under 400. There is no new middleware, store, background task, or dependency, and nothing under `vidbyte/tools/` or `vidbyte/middleware/` was edited. `grep -rn "del messages\|format(max_" vidbyte/agents/browser` prints nothing.

## Gate results (final lines quoted)

The test diff check prints nothing: `git diff 5db0eaa0..HEAD --stat -- tests/`.

Lint (`python lint/run.py`, after `git add`):
```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
No browser file appears in `python lint/run.py --rule S009 --all`. `ruff --isolated --select C901,PLR0912,PLR0915 vidbyte/agents/browser/` prints `All checks passed!`. No comment line is over 72 columns.

Semgrep (static policy, after `git add -A`). The global `semgrep` CLI crashes at import, because its `semgrep mcp` subcommand needs mcp 1.x and this machine has mcp 2.x. I ran the same 1.170.1 engine through a scratchpad wrapper that stubs only that subcommand module. The rules and the engine are unchanged.
```
$ semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py
1/1: ✓ All tests passed
No tests for fixes found.
$ semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte
 • Findings: 0 (0 blocking)
 • Rules run: 1
 • Targets scanned: 996
Ran 1 rule on 996 files: 0 findings.
```
The remote `Static policy` run 39063513275 succeeded.

Public API contract:
```
$ python scripts/generate-sdk-public-api.py --check
contracts/sdk-public-api.json is current at 8183aa6f65fa79eb0488c6fea9eb30933239d9fb (vidbyte-sdk 0.3.0, 648 exports).
```

Browser pack:
```
$ PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q -p no:cacheprovider
FAILED tests/features/browser_agent/test_browser_agent_recheck.py::test_a_refused_finish_appends_one_gap_message_and_the_next_call_shows_the_verdict[final_text]
1 failed, 105 passed in 1.52s
```

Neighbour suites:
- Runtime, fork, MCP, prompts, registry, infinite, loop settings, model usage: `443 passed in 8.77s`.
- Jev, aggregate, stop-reason, restore, jev_read_only, jev_bulk_work, provider keys, model catalog, presets: `600 passed in 3.88s`.

Full local gate, run with every provider key unset (`env -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u VIDBYTE_API_KEY -u GROK_API_KEY -u DEEPSEEK_API_KEY -u OPENAI_API_KEY …`) because live keys are in this shell:
```
$ PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source
SDK-LINT: PASS
FAILED tests/features/browser_agent/test_browser_agent_recheck.py::test_a_refused_finish_appends_one_gap_message_and_the_next_call_shows_the_verdict[final_text]
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded
=========== 3 failed, 6345 passed, 16 skipped in 101.35s (0:01:41) ============
```
The two harness_threads failures are not caused by this feature's code:
- `test_failure_codes_keep_main…` fails at the base commit too. With this worktree checked out detached at `08f67e7f`, it gave `AssertionError: assert 148 == 120` (`1 failed, 1 passed in 1.98s`).
- `test_import_vidbyte…` is a branch-scoped check from #1036. It asserts that the root `vidbyte.__all__` equals the `__all__` at `git merge-base origin/main HEAD`. That means any branch that adds a root export fails it locally, and spec row 24 / AC-24 requires four. `InfiniteMemoryAgent` (#1084) merged after that test landed in the same state. Both tests skip their merge-base comparison when there is no `origin/main` ref, which is the case on CI's shallow clone, so CI passes them.

```
$ python scripts/run_ci.py --stage package
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
package exit=0
```

Remote CI run 39063511785 (dispatched at 0982ad4c, the last code commit):
- `Source / Python 3.11` and `Source / Python 3.12` each failed with `1 failed, 6306 passed, 57 skipped`. The one failure is the `[final_text]` case.
- `Package` was skipped because the Source jobs failed.

## Implementation deviations

The full list is in the spec under §17 "Implementation deviations (S3)". In short:
- **Lint-driven changes**: enum export order follows ruff; two extra constants (`BROWSER_FIRST_INDEX`, `BROWSER_MIN_COUNT`) for A007; the C012 provider proof call; the S008 helper `_require_distinct_servers`.
- **Patch and episode tool behaviour**: `progress_full` is detected through `details["field"]`; a successful patch returns the section name; the episode tool reports a blank argument with the validator's message; `_card` raises `OutputSchemaViolationError` itself when the payload is missing.
- **Text and measures**: derived criteria and the recheck gap are collapsed to one line and capped; event details carry no free text; the rebuild measure uses `json.dumps(..., default=str)`.
- **Typing and docs**: mypy narrowing in the facade, `self.goal` on the runtime, and the placement of the docs sections.

`git merge-tree --write-tree origin/main HEAD` exits 0. origin/main's four new commits touch none of the shared files.

## Choices worth a reviewer's eye

- **Hooks**: the runtime overrides exactly `__init__`, `arun`, `_after_tool_iteration`, `_continue_finish_attempt`, `_budget_stop`, and the private `_rebuild_history`. The card upsert is inlined in both hooks behind `if self.context_manager is not None`, as InfiniteMemoryRuntime does, rather than in a seventh method.
- **`_adopt_agent_catalog`** applies the agent catalog's difference after each iteration. It only re-adds tools when the agent's own catalog object changes mid-run (`attach_mcp_server`). The ACTION tools are removed from the run catalog, not from the agent's catalog, so a normal run never re-adds them, and AC-5 passes.
- **At the stall cap**, `_continue_finish_attempt` still appends the gap message and returns True. `_budget_stop` then ends the run before the next model call, which matches the call counts AC-15 asserts.

## Open items

1. The S2 test defect above. It blocks the required checks, and the fix is S2's.
2. The two harness_threads surface tests fail only locally, for the reasons shown above. The S5 gate should expect them, or the harness owner should scope them.
3. Semgrep runs here only through the scratchpad wrapper, until mcp<2 is available for semgrep's CLI. That is an environment problem, not a repository one.

## After the AC-13 grant

The orchestrator granted option 1. S2 changed only the assertion at `test_browser_agent_recheck.py:112`, the AC-13 Proof cell, and a test-plan note (e35b2db3). The orchestrator then committed `pipeline.md` (085d1887). I changed no test.

Browser pack, run with every provider key unset:
```
$ PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q -p no:cacheprovider
..................................                                       [100%]
106 passed in 1.48s
```

Full local gate, with every provider key unset. Only the two local-only harness_threads tests fail; the section above shows why.
```
$ PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source
SDK-LINT: PASS
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded
============ 2 failed, 6346 passed, 16 skipped in 98.40s (0:01:38) ============
```

I pushed 085d1887 and dispatched both workflows on it. `gh run watch --exit-status` exited 0 for both runs.
- CI run 39064133364:
  - `Source / Python 3.11`: `6307 passed, 57 skipped in 112.39s`, then `CI passed.`
  - `Source / Python 3.12`: `6307 passed, 57 skipped, 19 warnings in 113.38s`, then `CI passed.`
  - `Package`: success.
- Static policy run 39064135009: success.

Check-runs on the pushed head (`gh api repos/cerredz/Vidbyte-SDK/commits/085d1887f95be828831f28e93d80e1362eeaa1e0/check-runs`):
```
Package	completed	success
Static policy	completed	success
Source / Python 3.11	completed	success
Source / Python 3.12	completed	success
```

After 085d1887 the branch has only this docs commit, which changes the spec's §17 r4 S3 row and this report. I did not re-dispatch CI on the final SHA, because the change touches no code or test.
