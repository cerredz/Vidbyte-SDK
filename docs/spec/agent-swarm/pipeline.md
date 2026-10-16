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
| S1 spec + review | running | 2026-10-16 16:35 | | reports/S1-spec-author.md, reports/S1-spec-review.md | spec r1 @a43f5423 (37 rows, 23 new files); review round 1 running |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
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
- vidbyte-gates.md is wrong for the SDK: lint marker is `SDK-LINT: PASS`; run_ci.py runs no semgrep; `--stage source` needs `PYTHONPATH=$(pwd)` while the package stage must run without it — *source:* S0 scout
