---
slug: loop-spend-cap
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-loop-spend-cap
branch: feat/loop-spend-cap
base_commit: 22993b5fcc4c45048fb0d5c5e0e4538601b854d9
pr:
until: none
started: 2026-10-19
---

# Pipeline: An optional USD spend cap that every agent's own loop enforces

Program: JevAgent in vidbyte-cli, run R3 of 8 (see request.md §C "This run's scope"). R1 (#1190, root exports) merged as 22993b5f. C1 (CLI provider-key gate, #174) is in S5.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-19 | 2026-10-19 | reports/S0-scout.md | base_commit 22993b5fcc4c45048fb0d5c5e0e4538601b854d9; code-map.md 455 lines (4 sections); about 12 edit targets; orchestrator spot-checked records.py:68-89, pricing.py:300-314, router.py:36-51, cost_budget.py:36-79 and harness_threads :218-232 |
| S1 spec + review | done | 2026-10-19 | 2026-10-20 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | approved r3 f1e7677e (r1 a246ef08, r2 d49469ee). Round 1: 2 Blockers / 5 Majors / 3 Minors, all closed (R-6 as a stated limitation). Round 2: 0 Blockers / 1 Major / 4 Minors, fixed in r3 and checked by the orchestrator (row 27 present; rule 1 covers MultiAgentExecutionError, which is a root export; §13 warns about gpt-4.1-mini). 27 §12.3 rows |
| S2 tests | done | 2026-10-20 | 2026-10-20 | reports/S2-test-author.md | b5a9e689 (tests 021f73dc, proof 19bfde45). Pack tests/features/loop_spend_cap: 123 tests in 10 files, plus the row-26 edit to tests/test_codex_output_contracts.py. The orchestrator re-ran the pack: `123 failed`, each for a missing feature (the max_spend_usd kwarg, UsageRollup.cost_measured, vidbyte.agents.spend_cap, agent.loop refusing max_spend_usd, docs). The diff outside the pack and docs/spec is only the one-line codex edit. Expected after S3: 174 passed (pack plus codex file) |
| S3 implement | running | 2026-10-20 | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (cap reached; spec approved r3) · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-19: Program split into 8 PRs (request.md §C.2 D-P1). R3 is the SDK spend cap, and the CLI's `--max-spend` is C3.
- 2026-10-19: Ships in unreleased 0.4.0 with no version bump (D-P2). The change is recorded in docs/design/release-0-4-0.md.
- 2026-10-19: After S6, the orchestrator squash-merges with `--admin`. This uses the user's Q2 answer "you can just auto merge", which covers this program's SDK PRs only. Merge recipe: the "vidbyte release gates" memory, and R1's #1190 run.

- 2026-10-20: The round-1 guidance sent to the author: accept R-1, R-2 and R-7 (the cap stop must end the run, so queued prompts must not run with a fresh cap, and this is not new scope); prefer refusing at construction for R-3; C3 classifies on root-reachable facts (`error_kind`, stop reason). Existing tests that a change forces (row 26) go to the S2 test author, never around them with a special case in the code.

- 2026-10-20: The S2 test author built a prototype implementation in the scratchpad, to probe its tests. The orchestrator renamed it to `scratchpad/r3-s2-reference-WITHHELD/` and withholds it from S3, S4 and S5, so that the implementer and reviewers work only from the spec and tests. The S2 report still names the old path `scratchpad/proto` (line 178); that path no longer exists.
- 2026-10-20: The S3 PR title is `[WIP] feat(agents): add a USD spend cap that every agent loop enforces` (the template's default `feat:` gets the repo's `(agents)` scope). Row 16's `(#NNNN)` is left to S6, because the SDK has no automatic PR-number step.

## User replies (verbatim)
- 2026-10-19: answers to the alignment questions are in request.md §A, Prompt 3.

## Niche facts accumulated (carried into every later briefing)
- Interpreter: always `py -3.11`, never bare `python`. Source gate: `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`. Package gate: `env -u PYTHONPATH py -3.11 scripts/run_ci.py --stage package`. Never export PYTHONPATH; set it inline only. Source: R1 run.
- The only known local red on pristine main is `test_harness_threads_surface.py:309`, the `__all__` merge-base clause, and only on a branch that adds a root export. CI skips it. Source: R1 run, plus the "SDK main known-red tests" memory.
- semgrep runs from the venv `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3-semgrep-venv`, with `PATH="$(cygpath -u <venv>)/Scripts:$PATH"`. Source: R1 S3.
- SDK CI is dispatch-only: `gh workflow run ci.yml` and `static-policy.yml` with `--ref <branch>`. `gh pr checks` shows nothing. Source: R1 S6.
- `contracts/sdk-public-api.json` comes from `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py`. When main is merged in, take main's copy (`--theirs`) and regenerate; never hand-merge it. Source: R1 merges.
- The repo is PUBLIC with GH013 push protection. Never commit a key-shaped literal ("sk-" plus hex); build such fixtures at runtime. Source: the "SDK public-repo push protection" memory.
- The money comes from `vidbyte/agents/pricing/records.py:68-89` (`cost_usd`, `cost_complete`, via `UsageTracker.rollup()`). The request's `lib/dataclasses/sessions.py` UsageRollup is built after the run with flat prices. The SDK DOES price Jev decision calls (pricing.py:304-314, TYPESAFE jev-*). The request's claim that the gateway bills them is wrong. Source: S0, verified by the orchestrator.
- The runtime sets only `AgentStopReason`. `sessions/failure/router.py:36-51` `_STOP_CODES` maps it to a FailureCode, and an unmapped reason becomes RUNTIME_ERROR (:118). The stop-failure details dict is pinned exactly by test_session_failures.py:430-435. Source: S0.
- FailureCode trap: `test_harness_threads_surface.py:218-241`. Appending a member at the end fails everywhere, CI included (:224-227). Inserting mid-enum fails only locally, through the merge-base clause (:228-236). Prefer reusing an existing code, or adding none. Source: S0, verified by the orchestrator.
- `rollup().cost_usd` sums only the priced records, so a partly priced run reports too little, and only `cost_complete` shows the gap. A call with no usage leaves no record and only raises `unaccounted_call_count`. Source: S0.
- A child agent's spend reaches the parent tracker once, when the child's reply finishes (base.py:882-886). Children run inside internal tool calls or the compute checkpoint, which skip the mid-iteration checks (runtime.py:1836-1837), and they often run concurrently. So "overshoot of at most one call" is false for runs that use tools or children. Source: S0.
- A new loop field silently drops unless it is added to all of these: loop.py `to_runtime_config` and `__repr__`; base.py `_export_loop_settings` (:663-675); agents/fork.py:157-173; the fork tool's `_LOOP_SETTING_FIELDS` or `_inherited_guardrails` and its `additionalProperties: False` schema; config.py `_LOOP_FIELDS` (:92-98). Source: S0.
- A flat-rate USD ceiling already exists: `CostBudgetMiddleware(max_spend_usd=...)` at middleware/builtins/cost_budget.py:36-79. The field guide (runtime-boundaries.md:24-26) says not to duplicate it, so the spec must state how the new cap relates to it. Source: S0, verified by the orchestrator.
- Only the LINEAR, JEV and INFINITE_MEMORY runtimes use AgentRuntime. MCTS and actor runtimes refuse some loop settings (base.py:223-247). AgentLoopSettings raises ConfigurationError, while AgentRuntimeConfig and `positive_real` raise ValueError. Every USD value in the repo is a float. Source: S0.
- runtime.py is 2,304 lines and base.py is 1,830, both above AGENTS.md's "well below 1,000". Put new logic in a new module rather than growing them. Source: S0.
- S2 probe facts for S3: base.py has no module-level `AgentStopReason` import (row 6's drain condition needs it; otherwise a NameError shows only as `queued_prompt_error`). `_LOOP_FIELDS` is a frozenset literal. CP1 comes before `max_iterations`; CP3 is the first statement of `_enforce_tool_settings`, before the `tool_is_internal` return and `before_tool_call`; CP4 comes after `after_iteration` and before `_after_tool_iteration`. Runtime probes override `_continue_finish_attempt(result, state, messages)` and `_after_tool_iteration(state, messages)`. The construction refusal lists unpriced models in fallback-chain order; the run-time blind text sorts them. Source: S2.
- `_generate_reply` and `_process_tool_call` are at C901 10/10, so no branch may be added to them. `BaseAgent.__init__` and `_arun_once` are already in the lint baseline. Source: S2, from the lint baseline.
- Local-only inherited red after row 8: `test_harness_threads_surface.py:270-278` (`test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`) fails once `vidbyte/tools/builtins/fork/fork.py` differs from merge-base. CI skips it, and it clears on merge. Source: orchestrator, read at :270.
