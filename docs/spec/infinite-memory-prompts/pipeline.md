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
| S0 worktree + capture + recon | done | 2026-10-16 01:45 | 2026-10-16 02:20 | reports/S0-scout.md | base_commit 7efceb55; code-map.md (171 lines, 40-row leaf exposure table) |
| S1 spec + review | running (spec r1 at f70e65a2; reviewer launched 07:15) | 2026-10-16 02:25 | | reports/S1-spec-author.md, reports/S1-spec-review.md | spec r1: 729 lines, 47 §12.3 rows, INV-1…24, A-1…7, Q-1/Q-3 default no, Q-2 resolved |
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

| asset | chars | TokenEstimate.count (ceil len/4) | tiktoken |
|---|---|---|---|
| root_system_prompt.md | 8516 | 2129 | 1829 |
| generator_system_prompt.md | 6011 | 1503 | 1277 |
| verifier_system_prompt.md | 4981 | 1246 | 1059 |
| task_prompt.md | 1141 | 286 | 241 |
| verifier_task_prompt.md | 1176 | 294 | 251 |
| resume_prompt.md | 1090 | 273 | 232 |
| launch_tool_description.md | 1977 | 495 | 416 |

(Corrected 07:15: `TokenEstimate.count` is ceil(len/4); the first table used floor division and was one low on five rows. The spec's §4 snippet output is the record.)

The folder holds 40 `.md` assets; `infinite_memory.json` top level is a dict with 4 keys (the scout establishes the leaf mapping).

## Decisions the orchestrator made
- 2026-10-16 01:40 — Started at S0 (no prior worktree, branch, or pipeline.md existed for this slug; the first attempt stopped at a usage limit before producing anything).
- 2026-10-16 01:50 — The three system prompts already exceed the 1k floor; the floor is a minimum, not a ceiling, so the target range 1,100–1,500 applies to assets being expanded, and an asset already above it may stay above as long as every sentence earns its place (D-F). To carry into the S1 briefing.
- 2026-10-16 01:50 — Allowed `docs/` reads for every agent of this run: this run's `docs/spec/infinite-memory-prompts/*` (stage-appropriate) plus `docs/spec/infinite-memory-agent/{spec.md,request.md,pr-body.md}` on the base branch (orchestrator's brief overrides the AGENTS.md opaque rule for exactly these).

- 2026-10-16 02:20 — **D-B wording resolved (floor with margin, not a band):** every one of the seven assets must measure ≥ 1,000 tokens by `TokenEstimate.count` AND by tiktoken cl100k_base, with a margin so a small later edit cannot cross the floor (≥ 1,100 tiktoken). The 1,100–1,500 range is the target for the four assets being expanded (task_prompt, verifier_task_prompt, resume_prompt, launch_tool_description). No asset of the seven may end shorter in tiktoken than its baseline on the branch, because the user said "expand"; the three system prompts may stay at their current size or grow only where a sentence earns its place (D-F). Nothing commit 7efceb55 (#1113) added to a prompt may be dropped unless it contradicts a principle. — *why:* the request's "at least 1k" is a floor; the band was the orchestrator's margin guidance and cannot bind an asset that is already above it.
- 2026-10-16 02:20 — **Q-2 resolved:** sentences in `vidbyte/agents/infinite/README.md` (line 68 area: "about 2,100 tokens", "about 5,000", "near 105,000") that become false when the assets grow are updated in the same PR (docs, not Python). The header comment of `vidbyte/lib/constants/infinite.py:5` is NOT edited (D-D: no Python except tests); if its figure drifts, the PR body lists it under follow-ups. `vidbyte/prompts/README.md` is updated only where a sentence there becomes false.
- 2026-10-16 02:20 — **Request terminology corrected by the scout:** the root system prompt is consumed raw at `agent.py:72-75` (no `.format`, no `{max_parallel}`/`{max_depth}`; #1113 removed them). request.md §C's mention of those placeholders is stale; the spec records the code's truth. D-D still holds (no placeholder added or removed).
- 2026-10-16 02:20 — **Coordinator correction applied:** layout is 40 `.md` assets resolved via `"path"` (36 added in #1113), keep it; sizes are measured from the branch (the baseline table above); constants in `vidbyte/lib/constants/infinite.py` are 5–10× looser than the original brief said and no number, old or new, may be quoted in a prompt; the scratchpad folder `pr1084/` is stale and was not read.
- 2026-10-16 02:20 — Style reference is `vidbyte/prompts/prompts/jev_bulk_work/` only; no coding-agent prompt family exists (scout §4).
- 2026-10-16 06:51 — The S1 author (launched 02:25) was killed by the session usage limit during Stage B (reading); it left no spec.md and no report. Limit reset 06:50. Resumed the same agent by message (its grounding reads are kept) with the briefing unchanged; if resumption fails, a fresh author is launched with the identical briefing. Base branch re-fetched: still 7efceb55.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- Base branch may gain commits during the run (the user is fixing PR #1084 in another checkout): `git fetch origin` and compare against `origin/feat/infinite-memory-agent` before S3 and before S6; rebase the worktree onto it if it moved. — *source:* coordinator
- Keep every change inside the `infinite_memory` prompt family and its tests so the stacked PR does not conflict with `feat/infinite-memory-events`; the PR body lists "possible conflict with feat/infinite-memory-events on the 40-leaf test" under follow-ups. — *source:* coordinator
- Windows: long quoted heredocs in the Bash tool fail with "unexpected EOF"; write helper scripts with the Write tool and run by path. `git worktree remove` fails if a shell's cwd is inside the worktree. — *source:* brief
- GitHub Actions are disabled repo-wide; `gh pr checks` reports none; the local gate is the gate of record. Flaky on Windows: `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` (rerun alone). — *source:* brief (PR #1084 verification table)
- 13 leaves are `str.format`-ed (task_prompt, verifier_task_prompt, resume_prompt, result_card, launch_rejected, memory_rejected, remember_saved, remember_staged, note_saved, entry_dropped, quota_line, map_header; replayed_label is raw) and must hold zero literal braces and each placeholder exactly once; these end WITHOUT a trailing newline, the 27 raw leaves end WITH one. — *source:* S0 scout
- No numeric limit may appear in any leaf (field guide `prompt-families.md` / `runtime-boundaries.md`; `agents/infinite/README.md:75,114`); refusals name limits from code strings (`memory.py`, `workspace.py`, `delegation_limits.py:54,66`). — *source:* S0 scout
- The contract test bans, case-insensitive whole-word, in every leaf: git, repo/repos/repository/repositories, worktree(s), pull request(s), single writer, one writer. — *source:* S0 scout
- 11 leaves are regex-pinned via `template_regex(prompt_text(leaf))` (literal text escaped, `{field}` wildcards): result_card (also NFR-7 bound: no " … [cut]" in the template, two renderings), launch_rejected, replayed_label, verifier_system_prompt (whole text must appear in the verifier's system string), memory_rejected, quota_line (integers must be standalone tokens), remember_saved, remember_staged, note_saved, entry_dropped, resume_prompt; the 7 `launch_<field>_description` leaves are fullmatch-ed against the schema. The other leaves are pinned only by the 40-leaf / non-blank / banned-word tests. — *source:* S0 scout
- EC-18 test strips `memory_rejected_prompt`'s and `quota_line`'s literal words from a refusal and requires "pointer|note" in the remainder, so that advice must stay in code (`memory.py:162`, `workspace.py:269`), not the leaf. — *source:* S0 scout
- Sentences that become false if sizes change: `agents/infinite/README.md:68` ("about 2,100 tokens", "about 5,000", "near 105,000") and the Python header `constants/infinite.py:5`. The 24 descriptions sum to 4,926 TokenEstimate / 4,219 tiktoken today (sent in the tool schema on every call). — *source:* S0 scout
- Index line endings are LF (working tree CRLF, `core.autocrlf=true`); a token-floor test should read via `Prompts().get(...)`. `TokenEstimate.count` = ceil(len/4) overestimates English ~15 % vs tiktoken, so tiktoken is the binding measure for a floor. — *source:* S0 scout
- `run_ci.py` source stage = bytecode check, `lint/run.py`, compileall, three `scripts/check_*.py`, pytest (testpaths=tests); semgrep is NOT inside it (run separately after `git add -A`); package stage runs `assert Prompts().keys()` on the built wheel. S025 exempts `Prompts().get(...)` and cannot see `.md` assets; A009 (40,000-char README cap) and S020 (pack README File Index) are the only lint rules a prompt-plus-tests change can touch. — *source:* S0 scout
- The root system prompt is used raw at `agent.py:72-75`; the caps reach the model only through the `tasks` schema's `maxItems` and the middleware denial text, so no prompt may name them. — *source:* S0 scout
