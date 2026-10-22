# S5 repair, iteration 1 of 8: AgentSwarm

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm`, branch `feat/agent-swarm`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1174 (draft). Start HEAD `c8b77a76` (local only; origin at `c0b167d3`). No earlier iteration existed, so this iteration created `verify-log.md`. Scratch evidence lives in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/s5/` (gate outputs `gate*.txt`, mutation driver `mutate_s5.py` and its output `mutants-s5.txt`, probes under `probes/`).

## Gate matrix (local, on the merge commit `dc4710f9`)

| Gate | Result | Final lines |
|---|---|---|
| New tests `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q` | PASS | `170 passed in 5.13s` |
| Neighbours (infinite_memory_agent, test_agent_tool_loop, multi_agent, test_prompts_interface) | PASS | `189 passed in 6.39s` |
| `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 698f913b594f9cbeac6513d4883c0e4f0f1f4175 (vidbyte-sdk 0.3.0, 649 exports).` |
| `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, lint step | PASS | `S063 IMPROVED 4 -> 3. Lower it with: ...` / `S064 RATCHETED: 4 known finding(s). ...` / `SDK-LINT: PASS` |
| same, compileall and the three check scripts | PASS | each step ran and the next started |
| same, pytest step | FAIL, 3 inherited | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `=========== 3 failed, 6413 passed, 16 skipped in 134.86s (0:02:14) ============` / `CI failed: Command failed with exit code 1: ... -m pytest` |
| `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| Semgrep 1.170.1 `--config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, committed tree | PASS | `Findings: 0 (0 blocking)` / `Ran 1 rule on 995 files: 0 findings.`; the changed files scanned explicitly: `Ran 1 rule on 8 files: 0 findings.` |
| Remote CI and Static policy | see "Remote checks" below | |

The lint rule table is identical to the one at `c8b77a76` except `S009 staged-mypy-contracts 346/350 IMPROVED` (was 350/350). The baseline was not touched; the improvement arrived with the main merge or the moved imports, and tightening a ratchet is outside this iteration.

**Inherited source-stage failures** (all three in `tests/features/harness_threads/test_harness_threads_surface.py`; no other test failed):
1. `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`: `assert 148 == 120`. The test pins 120 `FailureCode` string members at `git merge-base origin/main HEAD`. At that merge-base (`845a4d9b`, current main) `vidbyte/lib/enums/failure.py` has 148 (counted with `ast` from `git show`), and this PR does not change that file (`git diff --quiet` on it). The test therefore fails on main itself.
2. `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`: lists `vidbyte/tools/README.md`, `vidbyte/tools/toolsets/__init__.py` and `vidbyte/tools/toolsets/agent_swarm.py`, which are spec §12.3 rows 19–21.
3. `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`: root `__all__` differs at index 30 (`'AgentSwarm' != 'JevAgent'`), the five exports of spec row 34.
Tests 2 and 3 diff the merge-base and fail on any branch that changes `vidbyte/tools` or the root exports (field guide `local-ci-verification.md`, "Two harness_threads surface tests fail locally..."). CI skips all three because its shallow clone has no `origin/main`.

## Per finding

**R-1 (Blocker), fixed `68813700`.** Removed the five advice clauses, using exactly the review's replacement text:
- `system_prompt.md:7` ends at "...may change its files while you work.";
- `system_prompt.md:19` ends at "...is your final answer.";
- `message_sent.md` is now "Message queued for {recipient}. Any reply arrives later as a user message.";
- `message_tool_description.md` sentence 4 is "Any answer comes back to you later in the same way.";
- `message_text_description.md` sentences 2–3 now state only where the text arrives and what the recipient sees.

Each description keeps 4 or 5 sentences, every template field is kept, and `system_prompt` keeps "agent swarm", "folder", "message" and "isDone". A grep for the five clauses over the family prints nothing. The `vidbyte/prompts/README.md` line "states no number, role, or workflow" is now true, so it needs no edit.

**R-2 (Major), fixed `fee22acb`.** `settings.py` imports `IS_DONE_TOOL_NAME` from `vidbyte.tools._internal` (the same import `vidbyte/agents/runtime.py:150` uses). It refuses `(*AGENT_SWARM_RESERVED_TOOL_NAMES, IS_DONE_TOOL_NAME)` with `details["field"] == "AgentSwarmSettings.search_tool"`, and the message lists all seven names. The `@intent` comment and the ARCHITECTURE NOTE say why the check exists. The false sentence in the constants header is corrected, and the tuple's value is unchanged. Probe `probe_verify.py p3` now raises `ConfigurationError: AgentSwarmSettings.search_tool must not take a swarm tool's name; got 'isDone'. Reserved: bash, grep, read_lines, write_text, patch_file, message, isDone.`

**R-3 (Major) and R-9, fixed `fbb2f445`.** The root cause is Python 3.11 `TaskGroup._on_task_done`, which returns at once for a cancelled child. Nothing then removes the agent from `_working` or runs the end check, so the swarm waits for `asyncio.timeout`.

`_run_member` gained an `except asyncio.CancelledError as cancel:` branch. When `asyncio.current_task()` is not None, its `cancelling() == 0` and `_stop_reason is None`, the branch records `_fail(name, f"CancelledError: {detail}")` and runs `_end_check()`. In every case it then re-raises. There is no await between the catch and the failed mark. BaseAgent's `except BaseException` path (`base.py:980`, `_close_failed_reply`) is synchronous, so the raise reaches the branch without the loop running anyone else in between.

`detail` is the cancel's own text, or a fixed sentence when the text is empty. The `CancelledError`'s `__cause__` is never rendered, so the text always starts with `CancelledError` as EC-39 requires.

The header was updated in two places:
- WHAT NOT TO DO item 4 now states the guarded containment and the re-raise.
- KNOWN EDGE CASES adds EC-39. Its TIMEOUT sentence is corrected (R-9): only a member that failed before the limit has an `AGENT_FAILED`, and an agent still unwinding under EC-18 may be missing from replies.

Evidence:
- P1 `elapsed 0.0 QUIET ... '3 agent_failed builder (CancelledError: the run was cancelled, but not by the swarm)'`, replies `[('tester', 'Tester done.')]`;
- P2 `0.02 QUIET`;
- idle variant `0.0 quiet ... '3 agent_idle tester', '4 agent_failed tester'` with no `agent_woke`;
- new probe `probe_all_cancel.py`: `0.02 failed`, no tasks left;
- the six EC-39 and time-limit tests passed 15 of 15 repeated runs;
- the pack runs in about 5 s instead of 12 s, because the EC-39 tests no longer wait out 2 s.

**R-4 (Major), fixed `034ca1cb`.** The class moved unchanged to `vidbyte/middleware/builtins/agent_swarm_turn.py`. It has an A001 header, `AgentSwarmRuntime` under `TYPE_CHECKING`, and no entry in `vidbyte/middleware/builtins/__init__.py`. `member.py` imports it and keeps the name in its `__all__`, so the import at `test_agent_swarm_contract.py:108` resolves as an explicit re-export.

Header edits:
- the `member.py` header now names three defined parts plus the imported middleware;
- the `runtime.py` ROLE IN CODEBASE line names the new location;
- the package `__init__.py` ARCHITECTURE NOTE now says where the middleware lives.

The package README File Index line names the module in dotted form (see the S020 note below). `vidbyte/middleware/README.md` is unchanged. Afterwards the product file count against the merge-base is 24 added and 13 modified, the r4 budget. The identity check `A is B` printed True, `fail_closed` is True, and the class is not on `vidbyte.middleware.builtins`.

**R-5 (Major).** The S2 test author closed it at `c71b1032`, and its status is set accordingly. No test was changed: `git diff c71b1032..HEAD -- tests/` is empty.

**R-6, fixed `03661f3f`.** Four sentences were reworded:
- `vidbyte/agents/README.md` AgentSwarm paragraph;
- package README :3 and :42;
- `REPO_MAP.md` :77.

They now say two things. First, a spent budget only stops wakes: once no agent works, the swarm ends `max_turns` only when a message is left waiting, and `quiet` otherwise. Second, mail reaches a working agent once the tool calls of its current model response have run, which is before its next model call. A009 stays CLEAN and S020 stays at 1.

**R-7, fixed `e40b2f95`.** The `base.py` comment block is re-wrapped to 68/70/57/69/27 columns. The change is comment only.

**R-8, fixed `ccf4e52d`.** `one_line=True` was dropped from `TOOL_CALLED.tool_name`. `probe_toolname.py` now gives `'bash\nrm' quiet [... 'tool_called builder', 'agent_idle builder' ...]`.

**R-10, fixed `1fa90858`.** The constants header states the sum, measured at chars/4 by `probes/measure_tokens.py`:
- swarm prompt: 326 tokens;
- seven tool schemas: 748 tokens;
- agentic-loop prompt: 115 tokens;
- fixed part: about 1,190 tokens;
- one call with the 90,000-token history: about 91,190 tokens, which leaves about 36,800 of 128,000.

**R-11, fixed `e3efbc28`.** `arun` rebuilds `self._events` right after `self._ran = True`, and the `events.py` header sentence now says so. `probe_verify.py p4` now gives a first `elapsed_ms` of 16 after the 0.4 s wait (it was 406). The 16 ms is the run's own member building, which counts as part of the run.

**R-13, fixed `965bd9ea`.** The three `_check_*` bodies were folded into `AgentSwarmEvent.__post_init__`, as one narrated block each, with the `@intent` kept above the per-kind block. S008 stays at 19 and S024 at 25.

**R-12, R-14 and R-15** need no code change. R-12 is recorded in spec §17 and R-14 was resolved by spec r4; R-15 is a separate PR (rule 11).

**Main catch-up.** `git merge origin/main` brought in #1169–#1172 with no conflict as merge commit `dc4710f9`. The contract was still current, so no regeneration was needed. The feature tests pass on the merge commit itself.

## Independent verification of this iteration's code

Eight textual mutants of the new code ran on a scratch copy of `vidbyte/`, `contracts/`, `pyproject.toml` and the pack, never in the worktree. The copy's baseline is `170 passed`.

Killed:
- dropping the `cancelling()` guard: the AC-6, EC-23 and EC-19 tests fail, because the swarm's own cancels would record `AGENT_FAILED` and a decided reason would replace TIMEOUT;
- dropping the end check in the branch: the EC-39 working variant fails;
- three `await asyncio.sleep(0)` before the failed mark: the EC-39 idle variant fails, which confirms the S2 timing fact, and the no-sleep budget test fails;
- `isDone` not refused;
- the clock built in `__init__`;
- `one_line=True` restored.

Survived the pack:
- **Swallowing the cancel (`return` for `raise`).** Lint S019 catches it: `S019 REGRESSED: 6 finding(s), allowance 5 ... runtime.py:129 handles CancelledError in async code without re-raising.`, checked on a scratch git copy of HEAD.
- **Dropping the `_stop_reason is None` guard.** This is reachable. `probes/probe_cancel_after_decision.py` (`on_event` raises `CancelledError` on the last working agent's `AGENT_IDLE`, after that agent's own end check decided QUIET) prints `quiet [... '4 agent_idle tester', '5 swarm_ended ']` at HEAD. Under the mutant it prints `[... '4 agent_idle tester', '5 agent_failed tester', '6 swarm_ended ']`, which breaks EC-39's "a cancel arriving after the stop reason is decided is re-raised without `AGENT_FAILED`". This is a test gap for the S2 owner, not a code defect. The recipe above is a ready test: assert no `AGENT_FAILED`, QUIET, and replies `[builder]`.

## Test changes proposed

None.

## Findings believed wrong

None.

## Still open and next hypotheses

No confirmed finding is open. Everything the briefing listed is either fixed or recorded with its status in `review.md`. The only red local gate is the three inherited `harness_threads` surface tests above.

## Remote checks

**Remote checks** (dispatched with `gh workflow run` on `8f9a0811`, the pushed head with every fix and this log's first version; read with `gh run watch` and `gh run view`):

| Gate | Run | Result | Final lines |
|---|---|---|---|
| CI `ci.yml` | 39006274191 | PASS: Source / Python 3.11, Source / Python 3.12, Package all success | `SDK-LINT: PASS` / `6375 passed, 57 skipped in 114.74s` / `CI passed.` (3.12: `6375 passed, 57 skipped, 19 warnings in 119.47s`) / Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| Static policy `static-policy.yml` | 39006275608 | PASS | `Findings: 0 (0 blocking)` / `Ran 1 rule on 995 files: 0 findings.` |

CI skips the three inherited `harness_threads` surface tests (no `origin/main` in its shallow clone), so the remote source stage is fully green. The commit that records this table is docs-only.
