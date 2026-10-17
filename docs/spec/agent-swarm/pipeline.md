---
slug: agent-swarm
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm
branch: feat/agent-swarm
base_commit: 0f2aeb48382b49ecb179b3f3ca94f3807cd1edcc
pr:
until: none
started: 2026-10-16 16:10
---

# Pipeline: AgentSwarm — a minimal runtime where user-defined agents run their tools and message each other

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-16 16:10 | 2026-10-16 16:30 | reports/S0-scout.md | base_commit 0f2aeb48; code-map.md (4 §, 14 contradictions) |
| S1 spec + review | done | 2026-10-16 16:35 | 2026-10-16 18:40 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-2.md | spec r3 approved @d2746a4d; R1 SOUND WITH FIXES (7 applied), R2 SOUND WITH FIXES (6 applied) |
| S2 tests | done | 2026-10-16 18:45 | 2026-10-16 20:40 | reports/S2-test-author.md | 51 tests / 161 cases, all red (missing symbols); S2_HEAD=9895d663 → 87c8ed14 after adjudicated fixture fix |
| S3 implement | running | 2026-10-16 20:45 | | reports/S3-implementer.md | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

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
