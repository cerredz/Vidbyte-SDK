---
slug: agent-swarm
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm
branch: feat/agent-swarm
base_commit: 0f2aeb48382b49ecb179b3f3ca94f3807cd1edcc
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1174
until: none
started: 2026-10-16 16:10
---

# Pipeline: AgentSwarm — a minimal runtime where user-defined agents run their tools and message each other

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-16 16:10 | 2026-10-16 16:30 | reports/S0-scout.md | base_commit 0f2aeb48; code-map.md (4 §, 14 contradictions) |
| S1 spec + review | done | 2026-10-16 16:35 | 2026-10-16 18:40 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-2.md | spec r3 approved @d2746a4d; R1 SOUND WITH FIXES (7 applied), R2 SOUND WITH FIXES (6 applied) |
| S2 tests | done | 2026-10-16 18:45 | 2026-10-16 20:40 | reports/S2-test-author.md | 51 tests / 161 cases, all red (missing symbols); S2_HEAD=9895d663 → 87c8ed14 after adjudicated fixture fix |
| S3 implement | done | 2026-10-16 20:45 | 2026-10-16 22:30 | reports/S3-implementer.md | S3_HEAD=c0b167d3; draft PR #1174; 23 new + 13 modified = budget; 161/161 |
| S4 adversarial review | done | 2026-10-16 22:35 | 2026-10-17 00:40 | reports/S4-review-{conformance,conventions,engineering}.md, S4-findings-verifier.md | review.md: MERGEABLE AFTER FIXES — 1 Blocker (R-1), 4 Major (R-2..R-5), 10 Minor (R-6..R-15); 4 refuted |
| S5 repair loop | done | 2026-10-17 02:10 | 2026-10-17 04:20 | reports/S5-repair-1.md, S5-repair-2.md | converged in 2/8; HEAD cd9d3189 → 87df4fc9 (guard test) → b3852069 (R-17 docs); all findings closed; CI green |
| S5 re-review | done | 2026-10-17 03:05 | 2026-10-17 03:30 | reports/S5-rereview.md | SOUND: 0 Blocker, 0 Major, 2 Minor (R-16 spec text, R-17 doc text) |
| S6 PR | running | 2026-10-17 04:25 | | reports/S6-pr-author.md | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 2/8 (converged) · S5 re-review rounds: 1/2 (SOUND) · S2_HEAD 87df4fc9

## Decisions the orchestrator made
- 2026-10-16 16:08 — Base on origin/main (0f2aeb48), not on the unmerged InfiniteMemoryAgent branch (#1084) — the user said "inside of the vidbyte-sdk/", and #1084 is still open.
- 2026-10-16 16:08 — Earlier critique/pseudocode extras (oracle, claims, broadcast allowance, human channel, web_fetch, max_usd, git trunk, journal/resume) are recorded as rejected-by-scope in request.md §C — Prompt 3 narrowed the build to "very minimal" and "start off simple"; rule 11.
- 2026-10-16 16:08 — Earlier session prompts about the research survey are omitted from request.md §A, with a note — they are not about this feature.

- 2026-10-16 16:30 — Corrected request.md §C: InfiniteMemoryAgent #1084 IS merged (2c84049c, 15:45 today); main's vidbyte/agents/infinite/ is a legitimate code precedent; the user's "no InfiniteMemoryAgent biases" rule still governs prompts/roles — scout evidence code-map §4 item 1, verified with git merge-base --is-ancestor.
- 2026-10-16 16:30 — Spot-check S0: code-map has 4 sections; runtime.py:588-602 and :668-702 match the scout's description of where _after_tool_iteration fires (only after a tool iteration that continues); patch.py path confirmed; only docs/spec/agent-swarm untracked.

- 2026-10-16 17:20 — Spot-check S1 r1: 18/18 template sections; 37 §12.3 rows; frontmatter base_commit/worktree correct; commit "docs(spec): add agent-swarm spec r1" @a43f5423. Briefed the reviewer to treat L2 (over-engineering vs "very minimal") and the idle/wake/quiet race as priorities, and to judge the author's A-2 role mapping (AgentSwarmRuntime = per-member runtime; AgentSwarm = coordinator).

- 2026-10-16 17:45 — S1 review round 1: SOUND WITH FIXES (0 Blocker, 3 Major, 4 Minor, Q-11 optional default no). Resumed author in Revision mode by path to reports/S1-spec-review.md. Steered R-3 toward AgentSwarmRuntime = swarm-level coordinator (request.md §C open question + author's own A-2 "if wrong" branch; no approval gate means A-2 can't be corrected later). R-3 changes §8.5/§12 → scoped round-2 review required (playbook rule).

- 2026-10-16 18:05 — Spec r2 @66c1b2d8: all R-1..R-7 accepted (§16 rows present). R-3 changed §8.5/§12 → launched scoped round-2 reviewer (last allowed round), report reports/S1-spec-review-2.md, findings numbered from R-8.

- 2026-10-16 18:25 — S1 review round 2: SOUND WITH FIXES (0 Blocker, 3 Major R-8..R-10, 3 Minor R-11..R-13); R-1..R-7 confirmed resolved. Resumed author for r3 with instruction to set status: approved (two rounds = approval; cap reached, disputes become Q-n with defaults).

- 2026-10-16 18:40 — Spec r3 approved (status: approved, @d2746a4d). Q-1..Q-11 all take their stated defaults (all "No / not built"): Q-1 no sync run twin; Q-2 one recipient only; Q-3 no message length cap; Q-4 fixed allow-all permissions + SDK defaults; Q-5 no usage on result; Q-6 TOOL_CALLED carries name+status only; Q-7 contain failures per agent; Q-8 keep full events tuple; Q-9 no shared-workplace guard; Q-10 five root exports; Q-11 private root-cause helper. Summary printed to the user; continuing to S2 without waiting.
- 2026-10-16 18:45 — Environment: the global Python 3.11.0 has an EDITABLE vidbyte-sdk install pointing at the MAIN checkout, plus pytest 8.3.5 and pytest-asyncio 1.3.0. Do NOT run `pip install -e` in the worktree (it would repoint the shared global install away from main for every other session). Run everything with `PYTHONPATH=$(pwd)` from the worktree root (verified: vidbyte imports from the worktree that way).

- 2026-10-16 19:55 — S2 test author hit the account usage limit mid-run (no files written in the worktree). It had copied the repo to scratchpad/s2proto to build a "throwaway reference prototype" of the swarm — rejected (hard rule 1: the test author never writes an implementation; it anchors tests to its own design). Deleted the copy (pristine files only) and resumed the same agent with instructions to write the tests directly; probes of existing repo behaviour stay allowed.

- 2026-10-16 20:40 — Spot-check S2: 3 commits (ecfbac79 tests, cf403857 proof, 9895d663 report); every AC-1..AC-21 cited in test-plan.md; re-ran the pack myself: "161 failed in 2.26s", all ImportError/ModuleNotFoundError/KeyError('agent_swarm') — red for the right reason. S2_HEAD = 9895d663 (test tree frozen from here). Spec status → tests-written.
- 2026-10-16 20:40 — Accepted the test author's handling of three non-blocking spec ambiguities (cross-field refusal field names; a refused goal does not consume the run per §8.5 pseudocode; INV-1 goal arrives as the call's `prompt`). Logged here; no spec revision needed.

- 2026-10-16 21:10 — Semgrep: built isolated venv scratchpad/semgrep-venv (semgrep 1.170.1); the background `--version` check "failed" only because it ran the global pysemgrep — with `/c/...` Scripts first on PATH it reports 1.170.1. Command given to S3/S5: `PATH="/c/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/semgrep-venv/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`.
- 2026-10-16 22:00 — S3 BLOCKED at Phase 5: 26/161 failed with `TypeError: renderings() got multiple values for argument 'text'` (S2 fixture helper keyword clash; callers pass `text=` as a template field). Verified myself. Adjudication: genuine test-harness defect, no assertion involved → routed to the S2 test author (only it edits tests). Fix 87c8ed14 = `renderings(template, haystack, /, **known)` (3-line diff, verified). Pack now 161 passed (re-run by orchestrator: "161 passed in 3.22s"). New S2_HEAD = 87c8ed14; later stages diff the test tree against it.
- 2026-10-16 22:00 — S3 deviations accepted as repo-forced: asyncio.Semaphore instead of asyncio.Lock (lint TID251/S039 bans Lock; CodexAgent precedent); provider coerced with ModelProvider(...) (C012); on_event checked with callable() (S009 mypy); start events flushed inside the time limit; sorted-position imports/README/REPO_MAP entries.

- 2026-10-16 22:30 — Spot-check S3: tree clean; HEAD c0b167d3 == origin/feat/agent-swarm; `git diff 87c8ed14..HEAD -- tests/` empty; pack re-run "161 passed in 3.25s"; PR #1174 draft, title starts "[WIP]"; spec status implemented + pr url. Gates per implementer: source stage SDK-LINT: PASS + 3 known harness_threads failures (6398 passed); package stage "CI passed."; contract --check current; Semgrep 0 findings. Noted for conventions lens: several commit messages lack W-/FR-/AC- IDs (e.g. 0d64078a, 28444b65, f97170ec).
- 2026-10-16 22:33 — Dispatched remote CI on c0b167d3: ci.yml run 38990716271, static-policy.yml run 38990717815. NOT dispatched: agents-md-placement.yml (it moves code by pushing commits), actionlint.yml (no workflow changes), publish.yml. origin/main is 4 commits ahead (#1169–#1172, none in §12.3) → catch-up merge is an S5 item.

- 2026-10-17 00:10 — Remote CI on c0b167d3: ci.yml 38990716271 success, static-policy.yml 38990717815 success.
- 2026-10-17 00:40 — Spot-check S4: review.md has Verdict / Confirmed (R-1..R-5, each with path:line + reproduced evidence) / Refuted (4) / Minor (R-6..R-15). My commit-ID suspicion was REFUTED (IDs live in commit bodies). Reviewer templates were passed by file path (scratchpad/swarm/s4-*.md), not inline — deviation logged, no effect on output.
- 2026-10-17 00:45 — S4 routing: R-1 (prompt workflow advice), R-2 (isDone search tool), R-3 (unrequested CancelledError → AGENT_FAILED + re-raise, guard `task.cancelling()==0 and _stop_reason is None`), R-4 (move AgentSwarmTurnMiddleware to vidbyte/middleware/builtins/agent_swarm_turn.py, after R-3) → S5 repair. R-5 test gaps (M2, M7/EC-18, M21+M22/EC-26) + regression tests for R-2 and R-3 → S2 test author (only it edits tests). Spec r4 via S1 author before both: §8.4 23→24 new files + §12.3 row (R-4); containment rule for R-3 (INV-17/EC-38); R-14 decided as "replies may be partial under EC-18" (cheapest rule, documents existing behaviour, adds nothing). Minors R-6..R-13 go to S5 as trivial fixes; R-15 is a scope-adding follow-up → stays out (rule 11).

- 2026-10-17 01:00 — Spec r4 @204f7609 (status reviewed). Spot-check: only spec.md changed (+41/-27). Frontmatter is revision 4. §8.4 now has 24 new files, row 38 creates vidbyte/middleware/builtins/agent_swarm_turn.py, EC-39 exists, §16 has six S4 rows, §17 has an r4 row. No README row for vidbyte/middleware: that README lists builtins/ as a single folder. The author extended EC-33 to cover `isDone`, which is in scope because it is the guarding EC for R-2. Accepted.
- 2026-10-17 01:00 — Next: the S2 test author adds the R-5 gap tests (M2, M7/EC-18, M21+M22/EC-26) plus regression tests for EC-39 (R-3), EC-33/isDone (R-2) and the R-11 clock. The R-3 and R-2 tests must be red at HEAD; the R-5 tests must be green at HEAD and red under their mutant (mutate.py on a scratch copy only). A new S2_HEAD follows.

- 2026-10-17 01:45 — The S2 test author hit the session usage limit mid-addendum. Its edits survived uncommitted, and I resumed the same agent.
- 2026-10-17 02:05 — Spot-checked the S2 addendum at c71b1032. It touches only tests/features/agent_swarm/{FEATURE.md, README.md, test_agent_swarm_contract.py, test_agent_swarm_lifecycle.py} and test-plan.md, with no vidbyte/ source. I re-ran the pack myself: "6 failed, 164 passed in 12.28s". The 6 failures are exactly the expected-red regressions: the isDone refusal, EC-39 ×3, the R-11 clock, and the R-8 newline tool name. The agent reports that the M2, M7, M21 and M22 tests each fail under their mutant (on a scratch copy), and that the M7 test passed 10 of 10 runs. **New S2_HEAD = c71b1032.**
- 2026-10-17 02:05 — I accepted the test author's choice to leave the shared oracle `assert_event_invariants` unchanged even though it is stricter than r4. It allows FAILED only while an agent is working, and it demands full replies on QUIET. The two affected tests, the EC-39 idle variant and EC-18, assert their events directly. This weakens no existing assertion.

- 2026-10-17 02:50 — Spot-checked S5 iteration 1: DONE at cd9d3189 (pushed). The tree is clean. The pack diff since c71b1032 is empty. The only other test-tree changes come from the origin/main merge dc4710f9 (#1169–#1172). verify-log.md has "## Iteration 1". review.md has no `open` status: R-1, R-2, R-3, R-4, R-6..R-11 and R-13 are fixed @SHA; R-5 is closed by S2; R-12 is in §17; R-14 is in r4; R-15 is a follow-up. I re-ran the pack: 170 passed. Remote checks on cd9d3189 passed: CI 39006588451 and static-policy 39006589912.
- 2026-10-17 02:55 — S5 mutation testing found one gap: removing the `_stop_reason is None` guard survived the pack. This behaviour is specified (r4 INV-17/EC-39), so I routed it to the S2 test author. It committed 87df4fc9 (pushed): one test, pack 171 passed (re-run by me), the guard mutant killed on a scratch copy, 10/10 stable. **New S2_HEAD = 87df4fc9.**
- 2026-10-17 02:55 — I asked the test author for a clean `ruff check`/`ruff format --check` on the pack. It wasn't met, and that is not a defect. The repo has no [tool.ruff] config, and ruff defaults are not a gate here (SDK-LINT is). The 9 findings already existed at c71b1032, and 7 of 8 package source files would also be reformatted. I accepted this with no change, because reformatting the pack would be scope churn.
- 2026-10-17 03:05 — My own source gate on cd9d3189 gave `SDK-LINT: PASS` and "3 failed, 6414 passed, 16 skipped". All 3 failures are the known inherited harness_threads tests (failure_codes, tools_and_configs, import_vidbyte). **S5 has converged after iteration 1.** I dispatched ci.yml and static-policy.yml on 87df4fc9 and launched the final conformance re-review (round 1/2), whose report goes to reports/S5-rereview.md.

- 2026-10-17 03:30 — Remote CI on 87df4fc9 passed: CI 39007165774 and static-policy 39007167332. The S5 re-review (round 1/2) came back SOUND: all 11 fixes hold on the real code path, with 0 Blocker, 0 Major, and 2 Minor (R-16, R-17). R-16 is spec text only: INV-11 and EC-39 do not describe three outcomes that the R-3 branch reaches, namely a dropped reply after a decided end, a MAX_TURNS end, and an async callback that is woken and then fails. R-17 is three stale doc sentences: the swarm.py:38 docstring, the README:58 limits row, and the events.py:9 header. I fixed both rather than leaving them as follow-ups, for two reasons. They are trivial and change no behaviour, and stale public docstrings are exactly the review comments the user is trying to reduce. R-16 goes to the S1 author (r5). R-17 goes to S5 iteration 2 (2/8), which runs after the spec commit to avoid index collisions. No further re-review is needed, because the playbook re-reviews only new Blocker or Major findings. I spot-check these myself.

- 2026-10-17 04:20 — Spec r5 @c66a1ffe (R-16 text only, +5/-3, status reviewed) checked. S5 iteration 2 is DONE at b3852069 (pushed; fix 4a993f98). The R-17 doc text is fixed: swarm.py:38, README:58 and the events.py:9 header. The runtime.py:53 placeholder is kept, because deleting it would change behaviour for the public member methods called before arun (follow-up). Spot-check: tree clean, nothing unpushed, the tests diff since 87df4fc9 is empty, verify-log has Iteration 2, and only 3 one-line vidbyte/ edits. I re-ran lint and the pack myself: `SDK-LINT: PASS`, 171 passed. Remote CI on 4a993f98 passed: CI 39008866234 and static-policy 39008871160. **S5 is final: converged in 2/8 iterations, 1/2 re-review rounds, no open finding.** Spec status set to verified (orchestrator docs commit, per playbook).

## User replies (verbatim)
- 2026-10-16 16:05 — answers to four clarifying questions: "One shared folder (Recommended)"; "Stay alive until quiet (Recommended)"; "Shared goal + per-agent prompts (Recommended)"; "Callback + list on result (Recommended)".

## Niche facts accumulated (carried into every later briefing)
- SDK CI is manual: auto-triggers are disabled, so dispatch `ci.yml` for the branch and read results through the check-runs API; `gh pr checks` stays empty — *source:* memory vidbyte-sdk-ci-manual-dispatch
- Running `scripts/run_ci.py` with `PYTHONPATH` set breaks the package smoke test; Semgrep needs its own venv/pipx because the SDK pulls mcp 2.x — *source:* memory vidbyte-sdk-local-gate-gotchas
- The agent shell sets `NoDefaultCurrentDirectoryInExePath`, so tests that look up executables in the cwd pass vacuously — *source:* memory vidbyte-sdk-local-gate-gotchas
- A merge conflict in the contract's `source.commit` is resolved by taking ours, committing the merge, then regenerating — *source:* memory vidbyte-sdk-local-gate-gotchas
- Catch up with main by merge, never rebase, once the PR is pushed — *source:* memory spec-pipeline-orchestration
- No CLI commands in the SDK, ever — *source:* memory no-cli-in-sdk
- The main checkout has untracked `docs/design` files; never touch the main checkout — *source:* S0 orchestrator
- `_after_tool_iteration` fires only after a tool-running iteration that continues (runtime.py:690-700); the no-tool-call finish and isDone paths call `_continue_finish_attempt` instead (:598, :673); if it returns True at the no-tool finish the runtime appends the assistant reply AFTER the hook's message (:598-600). No seam exists between individual tool calls of one batch — *source:* S0 scout
- A new runtime type needs an `AgentRuntimeType` member, a `RuntimeRegistry` entry importing via the package `__init__` (A006), an entry in `_LINEAR_LOOP_RUNTIMES` (base.py:83), and a constructor that refuses to build without its settings — *source:* S0 scout
- C011: a public class whose name ends in Agent/Runner/Harness/Session/Machine and has `arun()` must also have `run()` — *source:* S0 scout
- S025: tool and parameter descriptions need ≥4 sentences served from the prompt catalog; prompt leaves are separate .md files with no numbers; limits enforced in code/middleware, not prompt text — *source:* S0 scout
- `vidbyte/lib/enums/prompts.py:7` header "139 assets / 35 families" must be bumped by hand when adding a prompt family (no test checks it) — *source:* S0 scout
- `contracts/sdk-public-api.json` regenerates only after `vidbyte/__init__.py` and `pyproject.toml` are committed (C016) — *source:* S0 scout
- README room under A009: agents README ~10.4K chars left, prompts README ~8K — *source:* S0 scout
- base.py (1,830 lines) and runtime.py (2,304) are oversized: only set entries or one-line hooks there — *source:* S0 scout
- "swarm" is taken by JevAgent's SWARM option (`jev_swarm` family, `launch_swarm` tool, `JevSwarm*`); new names must not collide — *source:* S0 scout
- MultiAgent on_event precedent is a two-argument callback `(event, snapshot)` called via `maybe_await`; callback errors are swallowed into `event_error_types` — *source:* S0 scout
- Default `PermissionPolicy()` allows only SAFE+READ: bash (EXECUTE) and write/patch (WRITE) are denied unless the swarm sets a policy; bash is NOT confined to the root folder (agents README:144) — *source:* S0 scout
- Patch tool is `vidbyte/tools/builtins/editing/patch.py`, model-facing name `patch_file`; `CodingAgentTools.get_tools` is closer to bash+grep+read+write+patch than ParadigmMinimalToolset — *source:* S0 scout
- No central test fake: N-concurrent-agent scripting uses `ScriptedTree` (patches `BaseAgent._runner_for_model`, routes by agent name, orders with Gate/Signal); other fakes in tests/agent_test_support.py, tests/features/coding_agent/conftest.py, tests/features/infinite... — *source:* S0 scout code-map §3/§4
- Idle/wake goes through a middleware `review_finish` hook returning `continue_with`/`accept` (spec D-3), because CONTINUE ordering is right at runtime.py:563-568/:669-670 while `_continue_finish_attempt` (:598-601) appends the reply after the hook's message (possible latent JevAgent ordering bug — reported, not fixed) — *source:* S1 author
- Turn reply text: plain finish = `ctx.run_state[AgentRuntimeStateKey.ITERATION_OUTPUTS.value][-1]`; isDone path = `ctx.tool_result.output` — *source:* S1 author
- `BaseTool.validate_call` only checks required args are present, so `message.execute` must re-check recipient and blank text — *source:* S1 author
- `RecordFieldValidator.require_number` refuses 0 — *source:* S1 author
- `ScriptedTree`: each agent's script is one continuous list of steps across all its turns — *source:* S1 author
- Two `harness_threads` surface tests already fail on any branch touching `vidbyte/tools` or root exports (field guide local-ci-verification.md); do not fix them — *source:* S1 author
- `BaseAgent.generate_reply` wraps every Exception in `AgentExecutionError` (a `VidbyteSdkError`, base.py:965-979); root-cause text comes from `__cause__` like infinite/launch.py `_error_text` — *source:* S1 reviewer
- The loop always adds `isDone` to tools (runtime.py:193-194) and appends the agentic-loop prompt after the system prompt (:254); exact-tool-set tests must include `isDone` (infinite tests do) — *source:* S1 reviewer
- S025 skips catalog-loaded descriptions, so the 4–5 sentence rule needs the swarm's own contract test; `ToolParameter` has no enum field → use `ToolSpec.input_schema` (precedent infinite/memory.py:139) — *source:* S1 reviewer
- C011 counts inherited run/arun; its suffixes exclude Runtime and Swarm — *source:* S1 reviewer
- `BaseActorRuntime(ABC)` (runtimes/actor/broker.py:44) is a registered multi-agent coordinator that is NOT an AgentRuntime subclass — precedent for a coordinator named *Runtime — *source:* S1 reviewer
- r2 names: `AgentSwarm` (thin entry) → `AgentSwarmRuntime` (per-run coordinator, fresh per arun) → members run `AgentSwarmMemberRuntime` (`AgentRuntimeType.AGENT_SWARM_MEMBER = "agent_swarm_member"`); `member.py` holds member runtime + member agent + `AgentSwarmMessageTool` + `AgentSwarmTurnMiddleware`, imports the coordinator only under TYPE_CHECKING; package exports six names, root exports five — *source:* S1 author r2
- `AgentSwarmTools.get_tools(root)` returns only bash/grep/read/write/patch; the coordinator appends `message` and the optional search tool — *source:* S1 author r2
- Members use `PermissionPolicy.allow_all()`; `agent_swarm_member` shows up in the fork-tool runtime enum and YAML `agent.runtime` choices and must refuse to run there — *source:* S1 author r2
- `BaseAgent(runtime=X)._runtime()` raises ConfigurationError directly; `.arun()` wraps it as AgentExecutionError with the cause — test `_runtime()` (tests …/test_infinite_memory_contract.py:214-219) — *source:* S1 reviewer r2 (probed)
- Any Exception in a tool → `ToolResult.error("Tool execution failed: …")` and the loop continues (runtime.py:1341-1348, 1480-1483); middleware decision hooks are fail_closed by default (middleware/base.py:28) → abort("middleware_error") and early return; `review_finish` exceptions propagate — *source:* S1 reviewer r2
- A006 counts function-local imports (skips only TYPE_CHECKING blocks and `__init__.py` targets); never hide a cycle with a local import — *source:* S1 reviewer r2
- Local interpreter is Python 3.11.0: `asyncio.timeout` around a TaskGroup unwinds children parked on futures (probe 0.22 s for 0.2 s); KeyboardInterrupt/SystemExit re-raised bare — *source:* S1 reviewer r2
- No default run-wide timeout (AgentRuntimeConfig.timeout_seconds None; BaseAgent timeout_seconds is per model call); fork tool enum (fork.py:471) and YAML choices (config.py:668) derive from AgentRuntimeType; no test pins the runtime list — *source:* S1 reviewer r2
- Test pack `tests/features/agent_swarm/` (FEATURE.md, README.md, agent_swarm_fixtures.py, test_agent_swarm_{acceptance,messaging,lifecycle,workplace,contract,property}.py); run with `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q` — *source:* S2
- Only `BaseAgent._runner_for_model` is patched and calls route by agent name → each member agent's name must equal the member's name — *source:* S2
- `end_turn` must mark the agent idle AND create its wait future BEFORE flushing AGENT_IDLE (EC-1 test sends from inside the idle callback); `AgentSwarmRuntime.arun` checks the goal before marking itself run (AC-18) — *source:* S2
- The loop does not enforce the schema `enum` before `execute`; `AgentSwarmMessageTool.execute` must refuse self/unknown recipients itself — *source:* S2
- EC-16(c) monkeypatches `AgentSwarmRuntime.record_tool_call` on the class; the middleware must call it through the runtime instance with the name first or as `name=`; an early return's AGENT_FAILED text must contain "middleware_abort" — *source:* S2
- Refusals put `AgentSwarmSettings.<f>` / `AgentSwarmMember.<f>` in `details["field"]` and repeat it in the message; event errors name exactly `AgentSwarmEvent.<f>` — *source:* S2
- Budget test: exactly 7 .py files in vidbyte/agents/agent_swarm; each of the 11 new modules ≤ 400 lines after its header; AST scan forbids any `sleep` call in the package and toolset — *source:* S2
- AC-6 uses timeout_seconds=0.5 with elapsed < 10.5 s; AC-16/AC-19 need Git bash on Windows — *source:* S2
- C012 accepts only `ModelProvider(x)` or a ProviderModelRegistry provider call; S024 counts `with`/`try` as nesting (combine `asyncio.timeout(...)` and `TaskGroup()` in one `async with`); asyncio.Lock is lint-banned (TID251/S039) → Semaphore — *source:* S3
- Three `harness_threads` failures on this branch are not ours: `failure_codes…` fails at base 0f2aeb48; `tools_and_configs…` and `import_vidbyte…` compare against merge-base and fail on any vidbyte/tools or root __all__ change (NFR-6 allows them) — *source:* S3
- origin/main had 8 files of drift (none in §12.3) at S3; catch up by MERGE after push, never rebase — *source:* S3
- vidbyte-gates.md is wrong for the SDK: lint marker is `SDK-LINT: PASS`; run_ci.py runs no semgrep; `--stage source` needs `PYTHONPATH=$(pwd)` while the package stage must run without it — *source:* S0 scout
