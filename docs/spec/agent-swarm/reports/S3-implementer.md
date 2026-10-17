# S3 Implementer report: agent-swarm

Spec: `docs/spec/agent-swarm/spec.md` r3 · Test plan: `docs/spec/agent-swarm/test-plan.md` · Branch `feat/agent-swarm` (worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm`) · Base `0f2aeb48` · Test baseline `87c8ed14` (was `9895d663`)

## Status: DONE. Draft PR https://github.com/cerredz/Vidbyte-SDK/pull/1174

Every row of spec §12.3 is implemented and committed (P1 to P4).

S3 first stopped BLOCKED at Phase 5 because of the S2 helper bug described below. The orchestrator chose option 1. S2 fixed its own helper in `87c8ed14` (`renderings(template, haystack, /, **known)`, no assertion changed). That commit is the new test baseline, and `git diff 87c8ed14..HEAD -- tests/` is empty. The scratch shim plugins were deleted and were never used again.

### Final gates (after the S2 fix, on `670b9eb9`; only `docs/` changed after that)

**Pack:** `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q`

```
.................                                                        [100%]
161 passed in 3.31s
```

**Local gate, source stage:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`

```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
=========== 3 failed, 6398 passed, 16 skipped in 101.58s (0:01:41) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-agent-swarm).
```

The only failures are the three `tests/features/harness_threads/test_harness_threads_surface.py` tests that the orchestrator accepted as not caused by this branch (proof under Gates below):

- `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`
- `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`
- `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`

**Earlier gates, still valid:** the package stage (`CI passed.`), lint, the contract check, Semgrep and the neighbours, all quoted under Gates below. Every one of them ran on `0d64078a`. Between that commit and the gate above, only test and docs files changed.

**Phase 6 and Phase 7:**

- Pushed `feat/agent-swarm` and opened draft PR #1174 with the placeholder body.
- Spec frontmatter: `status: implemented` and `pr:` (`8a40a6f6`).
- §6.2 Proof cells now name their implementing commits, and §17 has an r3 "S3 implement" row and an "Implementation deviations" list (`6e243292`).
- main was not merged into the branch, and CI was not dispatched.

### The blocker (resolved by S2 in `87c8ed14`)

`tests/features/agent_swarm/agent_swarm_fixtures.py:598`:

```python
def renderings(template: str, text: str, **known: object) -> int:
```

Both callers fill the `inbox_message` template's `{text}` field by keyword:

- `tests/features/agent_swarm/test_agent_swarm_property.py:187`: `renderings(prompt_text("inbox_message"), inbox, sender=sent.agent, text=sent.text)`
- `tests/features/agent_swarm/test_agent_swarm_messaging.py:241`: `renderings(prompt_text("inbox_message"), "\n".join(user_messages(last)), sender=other, text=text)`

Python binds `text=` to the helper's own second parameter, so every such call raises `TypeError: renderings() got multiple values for argument 'text'` before it looks at any output. No implementation can change that. The template field is `{text}` by spec §12.3 row 17, so the field name is not the thing to change.

Run on HEAD with no shim (`PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q`):

```
FAILED tests/features/agent_swarm/test_agent_swarm_property.py::test_random_schedules_with_one_failing_agent_contain_the_failure[31]
FAILED tests/features/agent_swarm/test_agent_swarm_property.py::test_random_schedules_with_one_failing_agent_contain_the_failure[32]
26 failed, 135 passed in 3.52s
```

All 26 failures are that `TypeError` (25 at `test_agent_swarm_property.py:187`, 1 at `test_agent_swarm_messaging.py:241`).

**Proposed fix (S2's to make):** rename the helper's positional parameter and make both positional-only, for example `def renderings(template: str, haystack: str, /, **known: object) -> int:` with the body using `haystack`. No caller changes.

**Evidence that this is the only gap:** a scratch pytest plugin (`<scratchpad>/shim/renderings_shim.py`, never committed, not in the repo) swaps in exactly that signature at collection time. With it, on HEAD:

```
PYTHONPATH="$(pwd);<scratchpad>/shim" python -m pytest -p renderings_shim tests/features/agent_swarm -q -p no:cacheprovider
.................                                                        [100%]
161 passed in 2.52s
```

That includes all 33 seeded random-schedule property tests, which check the full event-invariant oracle (`assert_event_invariants`).

## Commits (9895d663..HEAD, product code only)

| SHA | Rows | What |
|---|---|---|
| `afa6aec8` | 1, 2, 3, 5 | enums, constants, records (P1) |
| `38eda3dc` | 6-17 | prompt family and its ten keys (P2, one commit) |
| `ee51520f` | 18 | prompts README entry |
| `28444b65` | 19-21 | `AgentSwarmTools` |
| `1144fcf5` | 5 (follow-up) | `AgentSwarmMember.provider` coerced with `ModelProvider(...)` for C012 |
| `d138f5c3` | 23-25 | settings, workplace, event outbox |
| `f97170ec` | 22, 26-29, 31, 32 | runtime type, member parts, `AgentSwarmRuntime`, `AgentSwarm`, package exports, registry, linear-loop set |
| `d3651954` | 30 | package README |
| `698f913b` | 33, 34 | `vidbyte.agents` and root exports |
| `3f4f22c4` | 35 | regenerated `contracts/sdk-public-api.json` (generator, not hand-edited) |
| `a917dd64` | 36 | agents README section (1,606 characters) and Key Modules line |
| `0c38226f` | 37 | REPO_MAP paragraph |
| `0d64078a` | — | comment-only re-wrap to 72 columns |

Budget (§8.4): 23 new files and 13 modified files outside `docs/` and `tests/`, exactly the budget. Every file is a §12.3 row; nothing outside §12.3 was touched. `git diff 9895d663..HEAD -- tests/` is empty.

## Proof SHAs per acceptance criterion (for §6.2 once the gate is green)

AC-1 `f97170ec` + `698f913b` · AC-2 to AC-9 `f97170ec` · AC-10 `d138f5c3` + `f97170ec` · AC-11 `afa6aec8` + `1144fcf5` + `d138f5c3` · AC-12 `f97170ec` · AC-13 `28444b65` + `f97170ec` · AC-14 `38eda3dc` + `f97170ec` · AC-15 `f97170ec` · AC-16 `d138f5c3` + `f97170ec` · AC-17 `698f913b` + `3f4f22c4` · AC-18 `f97170ec` · AC-19, AC-20 `f97170ec` · AC-21 `d138f5c3`

## Deviations from the spec (all small; none changes behavior the tests pin)

1. **`asyncio.Semaphore()` instead of `asyncio.Lock`** in `AgentSwarmEvents` (row 25). Lint S039 (Ruff TID251) bans `asyncio.Lock` ("Use the SDK-owned concurrency boundary"). A semaphore with its default value of one is the same mutex; `vidbyte/agents/codex/agent.py:82-86` uses the same substitute.
2. **`AgentSwarmMember.provider` uses `ModelProvider(value)`** in a `try`/`except ValueError`, not `RecordFieldConverter.to_enum` (row 5). C012 recognizes only `ModelProvider(...)` or a `ProviderModelRegistry` provider call as a construction-time proof. The refusal still names `AgentSwarmMember.provider` in the message and in `details["field"]`. `JevAgentSettings` does the same.
3. **`on_event` is checked with `callable()`** in `AgentSwarmSettings`, not `require_instance(..., Callable)`. mypy (S009) rejects the `typing` special form as an `isinstance` target.
4. **The start events are flushed inside the time limit.** The flush runs inside one combined `async with asyncio.timeout(...), asyncio.TaskGroup() as group:`. In the §8.5 pseudocode it runs before the `try`. This way a stuck callback on `AGENT_STARTED` cannot outlive `timeout_seconds`, and nesting stays at S024's limit of three.
5. **Placement follows each file's sort order rather than the spec's "beside infinite" hint.** In `vidbyte/lib/enums/__init__.py` and `vidbyte/agents/__init__.py` the import blocks are placed where I001 requires (`agent_swarm` sorts before `aggregation`). The prompts README entry follows the alphabetical Actor Runtime entry. The REPO_MAP entry sits before `vidbyte/agents/algorithms/`, because every `vidbyte/agents/` entry there is alphabetical.
6. **The events clock starts when `AgentSwarmEvents` is built**, in `AgentSwarmRuntime.__init__`, one statement before `arun` begins.
7. **`origin/main` drift:** 8 files changed upstream since base, none in §12.3. The briefing says to catch up by merge after the PR is pushed, never by rebase.

## Gates

Run on HEAD `0d64078a` unless noted otherwise.

**Swarm pack, as committed:** `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q`

```
26 failed, 135 passed in 3.53s
```

All 26 failures are the `renderings` `TypeError` described above.

**Swarm pack, with only the scratch `renderings` signature fix:**

```
161 passed in 2.48s
```

**Neighbours:** `tests/features/infinite_memory_agent tests/test_agent_tool_loop.py tests/test_jev_compute.py tests/multi_agent tests/test_prompts_interface.py tests/test_agent_runtime.py tests/test_fork_tool.py tests/test_restore_actor_include_actors.py`

```
......................................................                   [100%]
270 passed in 5.95s
```

**Lint:** `PYTHONPATH=$(pwd) python lint/run.py`

```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

On the first P3 run, lint regressed C012, S009, S039 and S051, all in new swarm files. Each was fixed in code; no baseline was raised and no suppression was added. See deviations 1 to 3, and the Ruff I001 import wrapping in `runtime.py` and `settings.py`.

**Contract:** `python scripts/generate-sdk-public-api.py --check`

```
contracts/sdk-public-api.json is current at 698f913b594f9cbeac6513d4883c0e4f0f1f4175 (vidbyte-sdk 0.3.0, 649 exports).
```

**Semgrep:** `PATH="<semgrep-venv>/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, run after `git add -A`

```
✅ Scan completed successfully.
 • Findings: 0 (0 blocking)
 • Rules run: 1
 • Targets scanned: 994
Ran 1 rule on 994 files: 0 findings.
```

**Local gate, source stage: FAILED, on the blocker plus three branch-scoped harness tests.** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` was run on `3f4f22c4`..`0c38226f`. The only later commit, `0d64078a`, changes comments only.

```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
=========== 29 failed, 6372 passed, 16 skipped in 100.08s (0:01:40) ===========
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-agent-swarm).
```

The 29 failures break down as follows:

- 26 `agent_swarm` failures, all the `renderings` `TypeError`.
- 3 in `tests/features/harness_threads/test_harness_threads_surface.py`. All three were checked on a throwaway `git worktree` at base `0f2aeb48`, since removed:
  - `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails at base unmodified (`1 failed, 435 passed, 2 skipped` for the whole `harness_threads` folder at base).
  - `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` (`:224-232`) and `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` (`:235-258`) pass at base. They fail there too as soon as an untracked `vidbyte/tools/_probe_untracked.py` and a one-name `__all__` append to `vidbyte/__init__.py` are added (`3 failed, 6 passed`). They compare the branch with `git merge-base origin/main HEAD`, so any branch that adds to `vidbyte/tools` or to the root exports fails them, which §12.3 rows 19-21 and 34 require.

These are the two pre-existing failures that NFR-6 and code-map:135 allow. The third failure also fails at base itself.

**Local gate, package stage: PASSED.** `env -u PYTHONPATH python scripts/run_ci.py --stage package`, on `0d64078a`:

```
No broken requirements found.
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
```

**Housekeeping:** while removing the base worktree, I also ran `git worktree prune`. It deletes no files; it only drops the admin entries of worktrees whose folders are already gone. Other sessions' live worktrees, such as `vidbyte-sdk/.worktrees/base-check`, are still listed.

## Notes for the next stage

- Re-run the pack after S2's fix with `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q`. The root names are now real exports, so no shim is needed.
- Then run, in this order: neighbours, lint, `python scripts/generate-sdk-public-api.py --check`, `run_ci --stage source`, `run_ci --stage package`, and Semgrep. After those, push, open the draft PR (Phase 6), and do the spec frontmatter, §6.2 and §17 (Phase 7).
- Semgrep must run with the scratch venv's `Scripts` first on `PATH` as a POSIX path (`/c/Users/...`). A `C:/...` entry splits at the colon in Git Bash, and `semgrep.exe` then runs the global `pysemgrep`, which breaks on mcp 2.x.
