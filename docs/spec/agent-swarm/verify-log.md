# Verification log: AgentSwarm — a minimal runtime where user-defined agents run their tools and message each other

Gate set (from context/code-map.md §1 and the orchestrator's S5 briefing), run from the worktree root in this order:

1. New tests (local): `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q`
2. Neighbours (local): `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent tests/test_agent_tool_loop.py tests/multi_agent tests/test_prompts_interface.py -q`
3. Public-API contract (local, C016): `python scripts/generate-sdk-public-api.py --check`
4. Source stage (local; also remote CI): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` (lint, compileall, three check scripts, full pytest)
5. Package stage (local; also remote CI): `env -u PYTHONPATH python scripts/run_ci.py --stage package`
6. Static policy (local; also remote): `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with semgrep 1.170.1, on the committed tree
7. Remote (manual dispatch only): `gh workflow run ci.yml --ref feat/agent-swarm` and `gh workflow run static-policy.yml --ref feat/agent-swarm`, read with `gh run list --branch feat/agent-swarm` and `gh run watch <id>`; `gh pr checks` stays empty for dispatched runs.

## Iteration 1 — 2026-10-17 — agent report: reports/S5-repair-1.md

**Defects in:**
- Open findings: R-1 (Blocker); R-2, R-3, R-4 (Major); R-5 (Major, already closed by the S2 test author at `c71b1032`); trivial Minors R-6, R-7, R-8, R-9, R-10, R-11, R-13. No code change for R-12 (spec §17), R-14 (spec r4), R-15 (out of scope).
- Failing gate: the new tests at `c8b77a76`, `6 failed, 164 passed` (reproduced here: `6 failed, 164 passed in 12.02s`). The six are the spec r4 regression tests for R-2, R-3 (three EC-39 variants), R-8 and R-11.
- Main catch-up: origin/main 4 commits ahead (#1169–#1172).

**Hypotheses and attempts** (in order; every one was the first hypothesis tried, and each held):
- R-1. Five prompt clauses are workflow advice. Removed exactly the five, as the review's text, keeping 4–5 sentences per `*_description`, every template field, and the system prompt's required words. A grep for the five clauses prints nothing; the prompt contract tests stay green.
- R-2. The loop's `tools.add(IsDoneTool(), replace=True)` silently replaces a search tool named `isDone`. Refuse `(*AGENT_SWARM_RESERVED_TOOL_NAMES, IS_DONE_TOOL_NAME)` in `settings.py`, importing the name from `vidbyte.tools._internal`. Probe `probe_verify.py p3` now raises `ConfigurationError: ... Reserved: bash, grep, read_lines, write_text, patch_file, message, isDone.` The constants tuple is unchanged (A006, a test pins it).
- R-3. Root cause: Python 3.11's `TaskGroup._on_task_done` returns early for a cancelled child, so a member task that ends in a stray `CancelledError` leaves the agent in `_working` and nothing ever runs the end check. Added the guarded `except asyncio.CancelledError` branch in `_run_member` (fail + end check only when `current_task().cancelling() == 0` and no stop reason is decided; always re-raise; no await before `_fail`). Checked that BaseAgent's `except BaseException` path (`_close_failed_reply`) is synchronous, so nothing between the raise and the branch suspends. Evidence: P1 `elapsed 0.0 QUIET`, P2 `0.02 QUIET`, idle variant `0.0 quiet ... '4 agent_failed tester'` with no `agent_woke`; a new probe with every agent's tool raising gives `0.02 failed`, no stray task. The six EC-39/timeout tests passed 15 of 15 repeated runs. A `CancelledError` from `on_event` is not added to `event_error_types` (the branch never touches the outbox).
- R-4. Moved `AgentSwarmTurnMiddleware` unchanged to `vidbyte/middleware/builtins/agent_swarm_turn.py` (spec r4 row 38), `AgentSwarmRuntime` under `TYPE_CHECKING`, not re-exported. `member.py` imports it and keeps it in `__all__`, so the test import at `test_agent_swarm_contract.py:108` resolves and type checkers see an explicit re-export. **One failed attempt:** the first package-README File Index line named the new file in backticks as `vidbyte/middleware/builtins/agent_swarm_turn.py`; S020 regressed 1 → 2, because S020 (`lint/rules/s020_readme_file_index_parity.py:24`) reads every backticked token with a file suffix in a File Index as an index entry and requires it to be a direct tracked child. Naming the module dotted (`vidbyte.middleware.builtins.agent_swarm_turn`) instead puts S020 back at 1. Do not name files outside the folder with a suffix inside a File Index.
- R-6, R-7, R-10, R-11, R-13, R-8: each the review's smallest fix, verified with its probe or test (R-11 `probe_verify.py p4`: first `elapsed_ms` 16 after a 0.4 s wait, down from 406; R-8 `probe_toolname.py`: `'bash\nrm'` now ends `quiet` with a tool error; R-13 S008 stays 19; R-10 measured with a script at chars/4: swarm prompt 326, tool schemas 748, loop prompt 115 tokens).
- Independent check of the R-2/R-3/R-8/R-11 fixes: eight mutants of this iteration's code on a scratch copy (driver `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/s5/mutate_s5.py`, never run in the worktree). Killed: no `cancelling()` guard (AC-6, EC-23, EC-19 tests fail), no end check in the branch, an await before the failed mark (idle-variant test fails, confirming the timing fact), `isDone` not refused, clock built in `__init__`, `one_line=True` restored. Survived the pack: dropping the `_stop_reason is None` guard (reachable when `on_event` raises `CancelledError` on the last working agent's `AGENT_IDLE`, after its own end check decided QUIET: the mutant adds an `AGENT_FAILED` after the decision; `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/s5/probes/probe_cancel_after_decision.py` prints `quiet [... '4 agent_idle tester', '5 swarm_ended ']` at HEAD and `[... '4 agent_idle tester', '5 agent_failed tester', '6 swarm_ended ']` under the mutant) and swallowing the cancel (`return` instead of `raise`), which lint S019 catches (`S019 REGRESSED 6 > 5 ... runtime.py:129 handles CancelledError in async code without re-raising`, checked on a scratch git copy).

**Changes:**
- `68813700` R-1 · `fee22acb` R-2 · `fbb2f445` R-3 + R-9 · `034ca1cb` R-4 · `ccf4e52d` R-8 · `e3efbc28` R-11 · `965bd9ea` R-13 · `1fa90858` R-10 · `e40b2f95` R-7 · `03661f3f` R-6
- `dc4710f9` merge of origin/main (`845a4d9b`, #1169–#1172): no conflict; `contracts/sdk-public-api.json` still current, so no regeneration commit.
- Product files against the merge-base: 24 added, 13 modified (spec r4 §8.4). `git diff c71b1032..HEAD -- tests/` is empty.

**Gate matrix out** (local runs on `dc4710f9`, the merge commit):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q` | PASS | `170 passed in 5.13s` |
| neighbours | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent tests/test_agent_tool_loop.py tests/multi_agent tests/test_prompts_interface.py -q` | PASS | `189 passed in 6.39s` |
| contract (C016) | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 698f913b... (vidbyte-sdk 0.3.0, 649 exports).` |
| source stage: lint | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `S063 IMPROVED 4 -> 3 ...` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`; rule table identical to `c8b77a76` except `S009 346/350 IMPROVED` (was 350) |
| source stage: compileall + 3 check scripts | same run | PASS | no output, next step ran |
| source stage: pytest | same run | FAIL, 3 inherited | `3 failed, 6413 passed, 16 skipped in 134.86s` / `CI failed: Command failed with exit code 1: ... -m pytest` |
| package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| static policy | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (1.170.1, committed tree) | PASS | `Findings: 0 (0 blocking)` / `Ran 1 rule on 995 files: 0 findings.` |
| remote checks | dispatched `ci.yml` and `static-policy.yml` | see the remote line below | |

The three source-stage pytest failures are all in `tests/features/harness_threads/test_harness_threads_surface.py` and are inherited:
- `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`: `assert 148 == 120`. It pins 120 `FailureCode` members at the merge-base, and main's own `vidbyte/lib/enums/failure.py` at merge-base `845a4d9b` has 148 (counted with `ast`); this PR does not touch that file. It fails on main itself.
- `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`: lists `vidbyte/tools/README.md`, `toolsets/__init__.py`, `toolsets/agent_swarm.py`, the PR's own spec §12.3 rows.
- `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`: root `__all__` differs at index 30, `'AgentSwarm'`, the PR's specified exports.
The last two diff `git merge-base origin/main HEAD` and fail on any branch that changes `vidbyte/tools` or root exports (field guide `local-ci-verification.md`); CI skips them in its shallow clone.

**Remote checks:** pending at this commit; the dispatched CI and Static policy results are recorded in the next docs commit.

**Still open:** none of R-1..R-15 (statuses in review.md). Test gap for the S2 owner, not a code defect: no test kills the mutant that drops the `_stop_reason is None` guard (recipe above).
