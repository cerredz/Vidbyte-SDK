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
| S1 spec + review | done | 2026-10-19 | 2026-10-19 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | approved r3 4f988bdb (r1 b53eeeb9, r2 a9d04b51) |
| S2 tests | running | 2026-10-19 | | reports/S2-test-author.md | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (cap reached; spec approved r3) · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-19 — Program split into 8 PRs (request.md §C.2 D-P1) — the user's answers asked for separate SDK PRs, a separate gate PR, three Jev PRs, and universal max_spend.
- 2026-10-19 — SDK changes ride the unreleased 0.4.0, no new number (D-P2) — 0.4.0 is on main and unpublished.

- 2026-10-19 — Inherited red: tests/features/root_native_thread_exports fails 3 tests on pristine main b7350ed6 (#1183 added 11 native browser names without root exports). Out of R1 scope (exactly four names); stays inherited and is named as such in gates. — scout ran it (S0 report).
- 2026-10-19 — docs/design/release-0-4-0.md is the only release record for unreleased 0.4.0; the spec author may read it and decide whether the four exports belong in it.

- 2026-10-19 — Round 1 (SOUND WITH FIXES: R-1 Blocker, R-2/R-3 Major, R-4..R-6 Minor) all accepted; R-4 is scope-adding → ModelProvider stays non-root, Q-3 optional default No. Version unchanged (D-P2).
- 2026-10-19 — Round 2 launched, scoped to §6/§12/§13/§14 and dependents, because R-1 and R-2 changed the shape of §6 and §12 (skill rule: an accepted finding that changes §12's shape triggers one more scoped round).
- 2026-10-19 — Commit C (release-note row 2) is applied by the S3 implementer itself after it opens the draft PR at the end of S3 (`gh pr view feat/jev-cli-root-exports --json number -q .number`). This resolves the author's open item "who applies commit C".

- 2026-10-19 — Round 2 (be962596, SOUND WITH FIXES 0B/3M/1m) all accepted → r3 approved: one-time diffs use MB=$(git merge-base origin/main HEAD); INV-15/AC-13 follow the generator's provenance rule (--check "current at <source.commit>"); INV-2 absence clause removed (attributes are context); S3 makes commit C right after gh pr create. Q-1/Q-2/Q-3 take default No.
- 2026-10-19 — #1184 merged on SDK main (513aa614) by the repo owner account, outside this run; release-0-4-0.md:19 "#1184 gate" sentence is stale → §12.5 follow-up for the release PR, not edited here.

## User replies (verbatim)
- 2026-10-19 — answers to the alignment questions: request.md §A Prompt 3.

## Niche facts accumulated (carried into every later briefing)
- SDK merges need gh pr merge --squash --admin; ci.yml is dispatch-only and dispatched runs do not attach to PRs — source: orchestrator memory vidbyte-release-gates
- Edit only vidbyte/__init__.py (+ regenerate contracts/sdk-public-api.json); the four definition files and vidbyte.lib.enums / vidbyte.agents re-exports already exist — source: S0
- Commit order is now THREE commits (spec r2 §12.6): A = __init__.py edit; B = regenerated contract; draft PR; C = release note with the real PR number. Commit C touches no generator input (lint/core/public_api_contract.py:431), so source.commit = A stays valid — source: S1 r2
- (r1 note) Contract needs two commits: generator refuses uncommitted vidbyte/__init__.py or pyproject.toml and stamps HEAD as source.commit; commit source, regenerate, commit JSON (C016 red in between) — source: S0
- Never edit anything under vidbyte/tools/** (a test pins tools/ and configs/ equal to main) — source: S0
- PermissionPolicy root import: vidbyte.lib.dataclasses.security (SkillResolution precedent, __init__.py:480) or vidbyte.tools.security (same object) — source: S0
- Root __all__ is unsorted thematic clusters; import blocks are ruff-isort sorted (AgentLoopSettings between AgentInput and AgentMessage; enums into the vidbyte.lib.enums block ~:481-491) — source: S0
- Rules most likely to bite: C016 (contract current, baseline 0), S015 (every root import in __all__ once), S051/I001, A001 headers + S020 File Index parity for a new test pack, root header line "- Error exports:" must keep ConfigurationError — source: S0
- Editable install resolves to the canonical checkout: use PYTHONPATH=$(pwd) py -3.11 for source-stage gates and tests; no PYTHONPATH for package stage — source: S0
- test_import_vidbyte_starts_no_process... is red on any branch that changes root __all__; CI skips it — source: S0
- Tests written before code: use the FEATURE_MISSING ImportError guard pattern (public_skill_loader precedent does not read the contract JSON in pytest) — source: S0
- No permanent test may compare against base/merge base or pin an export count, module hash, or version literal (spec r2 NG-13, §13); such facts are proven once by command output — source: S1 review R-1
- INV-2 name→path table: AgentLoopSettings {agents.settings.loop, agents.settings, agents}; PermissionPolicy {lib.dataclasses.security, lib.dataclasses, tools.security(.permissions)}; TextModelMode {lib.enums.text_model, lib.enums, lib.config}; JevDynamicComputeOption {lib.enums.jev, lib.enums} — source: S1 review R-3
- Do NOT run `pip install -e` in this worktree: the global py -3.11 editable install points at the canonical checkout and other sessions rely on it. Bootstrap = inline PYTHONPATH=$(pwd) per command — source: code-map §1, local env traps
- origin/main = 0cce5781 (b7350ed6 + #1184 + #1188); its delta touches no R1-gated path, so merging main in P4 is optional for correctness — source: S1 review r2
