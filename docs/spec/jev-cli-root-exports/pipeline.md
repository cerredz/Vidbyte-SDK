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
| S2 tests | done | 2026-10-19 | 2026-10-19 | reports/S2-test-author.md | S2_HEAD 09b4ef23 (was dc5108e6; S062 fix by the S2 author); 21 red at S2, re-run by orchestrator: contract file 18 failed |
| S3 implement | done | 2026-10-19 | 2026-10-19 | reports/S3-implementer.md | S3_HEAD b1e17f66; draft PR #1190; budget 0 new / 3 changed; merged main twice (#1189, #1159) + regenerated contract each time; 682 exports, --check current at 76c61ffb |
| S4 adversarial review | done | 2026-10-19 | 2026-10-19 | reports/S4-review-{conformance,conventions,engineering}.md, S4-findings-verifier.md | review.md: MERGEABLE AFTER FIXES; confirmed 1B (R-1 conflict) 1M (R-2 release recount) 3m (R-3 spec text, R-4 title, R-5 draft); refuted 0; status reviewed 95bdc8e3 |
| S5 repair loop | done | 2026-10-19 | 2026-10-19 | reports/S5-repair-1.md | converged in 1 iteration; head 0a2f20be; R-1 7c8f8377 (merge 731f094c), R-2 26d05084, R-3 99d5f0fd; CI 39358180543 + Static 39358182288 success on 0a2f20be |
| S5 re-review | done | 2026-10-19 | 2026-10-19 | reports/S5-rereview.md | SOUND 0B/0M/1m (R-C1: §12.5/:390 name stale inherited reds; fix in S6 briefing) |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (cap reached; spec approved r3) · S5 repair iterations: 1/8 · S5 re-review rounds: 1/2

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

- 2026-10-19 — S2 open item (INV-7 pinned member order as permanent) resolved through the spec author before S3: r3.1 5bb8b967 "existing members keep values and relative order; later PRs may add". Tests untouched.

- 2026-10-19 — S3 stopped BLOCKED at lint: S062 892>889, all 3 findings in the S2 pack (adjacent string literals in assert messages). Adjudicated: test tree belongs to S2, so the S2 author applied the join patch (message text and AST unchanged) as 09b4ef23; orchestrator re-ran lint → SDK-LINT: PASS. S2_HEAD moves to 09b4ef23. Root cause: my S2 briefing named only A001/S020; every later S2 briefing requires the full lint/run.py.

- 2026-10-19 — S3 spot-check by orchestrator: pack unchanged vs 09b4ef23; only tests differing from origin/main are the pack; pack 21 passed; --check current at 76c61ffb; origin/main 181f1992 ancestor of HEAD. Full pytest 2 failed = named inherited reds (failure-codes 171==120 red on main; import-no-process local-only).
- 2026-10-19 — Main moved twice during S3 (#1189, #1159); implementer merged (EC-7) and regenerated the contract after each merge; release-note counts recomputed (682, 43 added: 11 #1189 + 3 #1159 + 4 #1190 ...). S4 conformance lens must re-prove the counts.

- 2026-10-19 — S4 conventions (1B/0M/1m) and conformance (1B/0M/0m) independently found the same Blocker: main moved to 0324d5d6 (#1147, +51 root exports, contract 729); #1190 CONFLICTING/DIRTY on the contract source.commit line only. Orchestrator re-verified (gh mergeable CONFLICTING DIRTY; merge-tree conflict only in contracts/sdk-public-api.json). Fix is the EC-7 path, handed to S5 after the verifier.

- 2026-10-19 — R-4 (title) and R-5 (draft → ready) are routed to S6 / orchestrator, not S5; S5 does R-1, R-2, R-3 plus re-proving AC-5/6/9/12/13/14/15 at the new MB and dispatching ci.yml + static-policy.yml on the pushed head.

- 2026-10-19 — Orchestrator re-ran the full source stage at 0a2f20be: SDK-LINT: PASS; pytest 1 failed / 7548 passed / 18 skipped; the 1 is the local-only `__all__` merge-base clause of test_import_vidbyte_starts_no_process… (:309), which passes on pristine 0324d5d6 and is skipped in CI. Converged: DONE, own gate green, remote CI + Static green on exact head, no open confirmed finding.
- 2026-10-19 — Re-review R-C1 (Minor) handled in the S6 briefing, not with another repair iteration: the PR body names only the one real local-only red; the stale spec §12.5/:390 inherited-red list is corrected by S6's spec finalize commit.

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
- EC-7 merge recipe: `git merge origin/main` (never rebase); in the merge commit take main's contract (`git checkout --theirs contracts/sdk-public-api.json`), never hand-edit source.commit (C016 passes but provenance is false, EC-5); then regenerate in its own commit; expect 733 exports — source: S4 C/V
- Release-note row 2(c) after #1147: "733 exports, against 639 at `v0.3.0`: 94 added and none removed, 3 from #1099, 4 from #1084, 17 from #1179, 11 from #1189, 3 from #1159, 51 from #1147, 4 from #1190, and `SystemPromptPreset` from #1095" — source: S4 C/V (re-prove)
- After the merge MB=0324d5d6: re-prove AC-5/6/9/13/14/15 and the inherited reds on a pristine 0324d5d6 (#1147 adds failure codes; 171==120 changes) — source: S4 C
- PR is a draft: `gh pr ready 1190` before merging; re-check `git ls-remote origin main` right before `gh pr merge --squash --admin --match-head-commit` — source: S4 C
- Squash subject on public main must be `type(scope): sentence (#N)` — PR title lacks a scope (R-V2) — source: S4 V
- test_import_vidbyte_starts_no_process... is red on any branch that changes root __all__; CI skips it — source: S0
- Tests written before code: use the FEATURE_MISSING ImportError guard pattern (public_skill_loader precedent does not read the contract JSON in pytest) — source: S0
- No permanent test may compare against base/merge base or pin an export count, module hash, or version literal (spec r2 NG-13, §13); such facts are proven once by command output — source: S1 review R-1
- INV-2 name→path table: AgentLoopSettings {agents.settings.loop, agents.settings, agents}; PermissionPolicy {lib.dataclasses.security, lib.dataclasses, tools.security(.permissions)}; TextModelMode {lib.enums.text_model, lib.enums, lib.config}; JevDynamicComputeOption {lib.enums.jev, lib.enums} — source: S1 review R-3
- Do NOT run `pip install -e` in this worktree: the global py -3.11 editable install points at the canonical checkout and other sessions rely on it. Bootstrap = inline PYTHONPATH=$(pwd) per command — source: code-map §1, local env traps
- origin/main = 0cce5781 (b7350ed6 + #1184 + #1188); its delta touches no R1-gated path, so merging main in P4 is optional for correctness — source: S1 review r2
- S2_HEAD = 09b4ef23 (moved from dc5108e6 by the S062 fix). Test tree: tests/features/jev_cli_root_exports/{FEATURE.md,README.md,test_jev_cli_root_exports_{acceptance,contract,import_time}.py}. S3/S5/S6 diff tests/ against it — must be empty — source: S2
- Bind eagerly; a lazy __getattr__ mapping passes S015 + identity tests but fails the S2 fresh-interpreter eager probe — source: S2
- S062 (no implicit string concatenation) lints tests too; write each assert message as one literal — source: S3 block
- Redirecting lint/run.py output on this machine needs PYTHONIOENCODING=utf-8 (cp1252 crashes on the report arrow) — source: S2
