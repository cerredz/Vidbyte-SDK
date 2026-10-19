---
slug: jev-cli-root-exports
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-cli-root-exports
branch: feat/jev-cli-root-exports
base_commit: b7350ed6423642c9c178361eef87f3d9cda5589b
pr:
until: none
started: 2026-10-19
---

# Pipeline: Root-export the loop, permission, text-mode, and compute names the CLI's JevAgent needs

Program: JevAgent in vidbyte-cli, run R1 of 8 (see request.md §C "This run's scope").

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-19 | 2026-10-19 | reports/S0-scout.md | base_commit b7350ed6423642c9c178361eef87f3d9cda5589b |
| S1 spec + review | running | 2026-10-19 | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-19 — Program split into 8 PRs (request.md §C.2 D-P1) — the user's answers asked for separate SDK PRs, a separate gate PR, three Jev PRs, and universal max_spend.
- 2026-10-19 — SDK changes ride the unreleased 0.4.0, no new number (D-P2) — 0.4.0 is on main and unpublished.

- 2026-10-19 — Inherited red: tests/features/root_native_thread_exports fails 3 tests on pristine main b7350ed6 (#1183 added 11 native browser names without root exports). Out of R1 scope (exactly four names); stays inherited and is named as such in gates. — scout ran it (S0 report).
- 2026-10-19 — docs/design/release-0-4-0.md is the only release record for unreleased 0.4.0; the spec author may read it and decide whether the four exports belong in it.

## User replies (verbatim)
- 2026-10-19 — answers to the alignment questions: request.md §A Prompt 3.

## Niche facts accumulated (carried into every later briefing)
- SDK merges need gh pr merge --squash --admin; ci.yml is dispatch-only and dispatched runs do not attach to PRs — source: orchestrator memory vidbyte-release-gates
- Edit only vidbyte/__init__.py (+ regenerate contracts/sdk-public-api.json); the four definition files and vidbyte.lib.enums / vidbyte.agents re-exports already exist — source: S0
- Contract needs two commits: generator refuses uncommitted vidbyte/__init__.py or pyproject.toml and stamps HEAD as source.commit; commit source, regenerate, commit JSON (C016 red in between) — source: S0
- Never edit anything under vidbyte/tools/** (a test pins tools/ and configs/ equal to main) — source: S0
- PermissionPolicy root import: vidbyte.lib.dataclasses.security (SkillResolution precedent, __init__.py:480) or vidbyte.tools.security (same object) — source: S0
- Root __all__ is unsorted thematic clusters; import blocks are ruff-isort sorted (AgentLoopSettings between AgentInput and AgentMessage; enums into the vidbyte.lib.enums block ~:481-491) — source: S0
- Rules most likely to bite: C016 (contract current, baseline 0), S015 (every root import in __all__ once), S051/I001, A001 headers + S020 File Index parity for a new test pack, root header line "- Error exports:" must keep ConfigurationError — source: S0
- Editable install resolves to the canonical checkout: use PYTHONPATH=$(pwd) py -3.11 for source-stage gates and tests; no PYTHONPATH for package stage — source: S0
- test_import_vidbyte_starts_no_process... is red on any branch that changes root __all__; CI skips it — source: S0
- Tests written before code: use the FEATURE_MISSING ImportError guard pattern (public_skill_loader precedent does not read the contract JSON in pytest) — source: S0

