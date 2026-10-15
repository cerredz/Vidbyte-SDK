---
slug: infinite-memory-agent
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-agent
branch: feat/infinite-memory-agent
base_commit: d9c01461b9e5d8a1265ee85128416b986841ce90
pr:
until: none
started: 2026-10-15 02:49
---

# Pipeline: InfiniteMemory agent

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-15 02:49 | 2026-10-15 03:05 | reports/S0-scout.md | base_commit d9c01461; code-map.md (4 sections) |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-15 02:49 — Unset the upstream of `feat/infinite-memory-agent` (git worktree add had set it to track origin/main) — a bare `git push` could otherwise target main; agents push with `git push -u origin feat/infinite-memory-agent`.
- 2026-10-15 02:49 — Scope rule for the spec: the user's explicit choices (request.md §C "Key decisions") are REQUIRED; the assistant's v1-cut suggestions (request.md §C "The v1 cut …") are in scope only in their simplest form and may be simplified or deferred with a stated reason, because the user's last instruction is "try to keep implementation of all features … very simple and elegant, dont overengineer anthing". Everything outside the v1 cut (lists I, J, K, consolidation, read tracking, final run verifier, multi-round verification) is a non-goal.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- No tree-wide live cost/usage cap exists today: a child's usage reaches the parent ledger only when the child finishes (`vidbyte/agents/base.py:838-842`); `CostBudgetMiddleware` is a per-run estimate from a blended rate. — *source:* S0 scout
- `Session` restore rebuilds the agent as a plain `BaseAgent` (`vidbyte/sessions/session.py:479-482`), so a custom runtime type cannot be resumed through the stock Session path. — *source:* S0 scout
- `BashTool` needs EXECUTE permission, but BaseAgent's default `PermissionPolicy` allows only SAFE and READ; CodingAgent uses `allow_all()`. — *source:* S0 scout
- `GrepTool` has a fixed name `"grep"` and one root; `Tools.add` raises on duplicate names (no workspace/project/both scope as-is). — *source:* S0 scout
- A new runtime type must be added to `_LINEAR_LOOP_RUNTIMES` (`vidbyte/agents/base.py:78`) and must refuse to build without its settings because the type is selectable by string (precedent `vidbyte/agents/jev/runtime.py:59-67`). — *source:* S0 scout
- `_after_tool_iteration` runs only after normal tool iterations (`vidbyte/agents/runtime.py:696`); there is no per-tool-call runtime hook — the per-call seam is middleware `after_tool_call`. — *source:* S0 scout
- The system prompt is rebuilt every call but set with `setdefault` (`vidbyte/agents/runtime.py:1561`), so an explicit `system` option replaces it. — *source:* S0 scout
- `ParallelPipeline` has no concurrency cap and its `gather` does not use `return_exceptions`; each stage must catch its own errors (bulk_work precedent). — *source:* S0 scout
- `context_window_budget` is never passed to the runtime config and nothing in the runtime knows the model's context size — a "~75% of context" trigger has nothing to measure today. — *source:* S0 scout
- Fake models in tests: patch `BaseAgent._runner_for_model` and route by agent name (`tests/features/jev_bulk_work/test_jev_bulk_work.py:186-193`); this reaches child agents built inside tools; async tests need `@pytest.mark.asyncio`. — *source:* S0 scout
- Lint: A001 header on every new .py (tests too); S025 tool descriptions ≥ 4 sentences or loaded via `Prompts().get`; C016 requires regenerating the public-API contract (`sdk-public-api.json`); prompt enum keys and JSON prompt assets must match. — *source:* S0 scout
- Gates in this worktree: install `python -m pip install -e ".[dev]"`; `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` without PYTHONPATH; semgrep is CI-only and scans tracked files only (stage new files first). — *source:* S0 scout / field guide local-ci-verification.md
