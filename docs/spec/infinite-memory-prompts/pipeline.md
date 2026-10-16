---
slug: infinite-memory-prompts
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-prompts
branch: feat/infinite-memory-prompts
base_branch: feat/infinite-memory-agent
base_commit: 7efceb5504b0d2ac64a3b5874ada635a47ac35cf
pr: 
until: none
started: 2026-10-16 01:40
---

# Pipeline: Rewrite and expand the InfiniteMemoryAgent prompt family so every prompt reinforces the agent's intended behavior

STACKED RUN. Base branch is `feat/infinite-memory-agent` (PR #1084), not `main`. Every place the playbook says `origin/main` (S3 drift check, DIFF_BASE, S6 checks) reads `origin/feat/infinite-memory-agent`. The PR is opened with `gh pr create --draft --base feat/infinite-memory-agent`. Never push to, rebase, or amend `feat/infinite-memory-agent`; never touch `main`; never touch the sibling worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-events` or branch `feat/infinite-memory-events`.

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | running (scout launched) | 2026-10-16 01:45 | | reports/S0-scout.md | base_commit 7efceb55 |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Baseline measurements (orchestrator, before any change, at 7efceb55)
Script: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7d03425b-8396-4738-89eb-c11a8a3fac1a/scratchpad/measure_tokens.py <worktree>` (chars/4 = `TokenEstimate.count` rule; tiktoken 0.12.0 cl100k_base importable in Python 3.11).

| asset | chars | chars/4 | tiktoken |
|---|---|---|---|
| root_system_prompt.md | 8516 | 2129 | 1829 |
| generator_system_prompt.md | 6011 | 1502 | 1277 |
| verifier_system_prompt.md | 4981 | 1245 | 1059 |
| task_prompt.md | 1141 | 285 | 241 |
| verifier_task_prompt.md | 1176 | 294 | 251 |
| resume_prompt.md | 1090 | 272 | 232 |
| launch_tool_description.md | 1977 | 494 | 416 |

The folder holds 40 `.md` assets; `infinite_memory.json` top level is a dict with 4 keys (the scout establishes the leaf mapping).

## Decisions the orchestrator made
- 2026-10-16 01:40 — Started at S0 (no prior worktree, branch, or pipeline.md existed for this slug; the first attempt stopped at a usage limit before producing anything).
- 2026-10-16 01:50 — The three system prompts already exceed the 1k floor; the floor is a minimum, not a ceiling, so the target range 1,100–1,500 applies to assets being expanded, and an asset already above it may stay above as long as every sentence earns its place (D-F). To carry into the S1 briefing.
- 2026-10-16 01:50 — Allowed `docs/` reads for every agent of this run: this run's `docs/spec/infinite-memory-prompts/*` (stage-appropriate) plus `docs/spec/infinite-memory-agent/{spec.md,request.md,pr-body.md}` on the base branch (orchestrator's brief overrides the AGENTS.md opaque rule for exactly these).

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- Base branch may gain commits during the run (the user is fixing PR #1084 in another checkout): `git fetch origin` and compare against `origin/feat/infinite-memory-agent` before S3 and before S6; rebase the worktree onto it if it moved. — *source:* coordinator
- Keep every change inside the `infinite_memory` prompt family and its tests so the stacked PR does not conflict with `feat/infinite-memory-events`; the PR body lists "possible conflict with feat/infinite-memory-events on the 40-leaf test" under follow-ups. — *source:* coordinator
- Windows: long quoted heredocs in the Bash tool fail with "unexpected EOF"; write helper scripts with the Write tool and run by path. `git worktree remove` fails if a shell's cwd is inside the worktree. — *source:* brief
- GitHub Actions are disabled repo-wide; `gh pr checks` reports none; the local gate is the gate of record. Flaky on Windows: `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` (rerun alone). — *source:* brief (PR #1084 verification table)
