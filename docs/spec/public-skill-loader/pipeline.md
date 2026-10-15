---
slug: public-skill-loader
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader
branch: feat/public-skill-loader
base_commit: c9d31a7fb4128d1a609ce9702b0a55c71fcb1a3f  # rebased 2026-10-15 16:20 from 179d8adc (see Decisions)
pr:
until: none
started: 2026-10-15 15:04
---

# Pipeline: Public, root-exported skill loader in vidbyte-sdk (resolve every #904 skill source without JevAgent), version 0.2.2

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 15:04 | 15:20 | reports/S0-scout.md | base_commit 179d8adc; context/code-map.md (4 sections, 18 files) |
| S1 spec + review | done | 15:22 | 17:35 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | r3 approved; 2 rounds SOUND WITH FIXES; 11 findings applied; spec-summary.md |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Environment facts (carried into every briefing)
- PR repo `cerredz/Vidbyte-SDK` (origin `https://github.com/cerredz/Vidbyte-SDK.git`), base `main`. Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader`, branch `feat/public-skill-loader`, created from `origin/main` `179d8adc`, rebased at 16:20 onto `origin/main` `c9d31a7f` (0.3.0). The branch has NO upstream (orchestrator unset the auto-tracked `origin/main`); first push must be `git push -u origin feat/public-skill-loader`.
- Main checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` is OFF-LIMITS: it holds the user's untracked files (`docs/design/*.md`, `docs/pre-design/`). Never modify it, pull/fetch in it, stash in it, or switch its branch. (It is on `main` at `179d8adc` now, not at `d9c01461` as the parent briefing said; irrelevant to this run except that it must stay untouched.)
- The default `python` (`C:/Users/422mi/AppData/Local/Programs/Python/Python311/python.exe`) has an editable install of vidbyte-sdk pointing at the main checkout. Never run `pip install -e` from the worktree (it would repoint the user's install). From the worktree root, `python -c "import vidbyte; print(vidbyte.__file__)"` prints the WORKTREE's `vidbyte/__init__.py` (verified by orchestrator). Run tests as `PYTHONPATH=$(pwd) python -m pytest …` from the worktree root (scout, code-map §1).
- Full local gate: `python scripts/run_ci.py` (on SDK main today: 5173 passed, 14 skipped, plus lint, build, twine, install smoke). Stages: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, `python scripts/run_ci.py --stage package` (no PYTHONPATH). Semgrep is NOT in run_ci.py; it runs in `.github/workflows/static-policy.yml:23-30`: `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with `semgrep==1.170.1`, tracked files only (`git add` first).
- Public API contract: `python scripts/generate-sdk-public-api.py` regenerates `contracts/sdk-public-api.json`; it refuses to write while `vidbyte/__init__.py` or `pyproject.toml` have uncommitted changes. Commit source first, then generate, then commit the regenerated file alone. Never hand-edit; never amend after generating. `--check` must pass (lint C016).
- Version bump (target 0.3.1 since the 16:20 decision; was 0.2.2): main now reads 0.3.0 in the same nine places the scout found for 0.2.1: pyproject.toml, vidbyte/__init__.py, CLI fallback, MCP server default, MCP clientInfo, README.md, llms.txt, bug template, and the regenerated contract. No test pins the version.
- Remote CI is dispatch-only: `gh workflow run ci.yml --ref feat/public-skill-loader` and `gh workflow run static-policy.yml --ref feat/public-skill-loader`. Required checks on `main`: `Source / Python 3.11`, `Source / Python 3.12`, `Package`. A draft PR may show BLOCKED with green dispatched checks; that is expected (dispatched runs do not count toward PR protection).
- Platform: Windows 11, Git Bash + PowerShell, absolute paths. Never a bare `git stash`.
- Attribution: every commit message ends, after a blank line, with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The PR body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Normal hooks only; no `--no-verify`, no force-push. The PR stays a DRAFT; never merge, tag, or publish.

## Consumer requirements (from the paused vidbyte-cli pipeline; relayed by parent session 2026-10-15 15:05; NOT user decisions; the spec designs and states each answer explicitly)
1. Callable without JevAgent; per entry returns text / `SkillDocument` or structured unavailable status with `SkillUnavailableReason` (CLI appends text via `AgentInstructions.append_to`).
2. Sync or async — state which, and why (CLI calls from command setup before an agent runs).
3. GitHub token — how a caller passes it; whether the loader reads `GITHUB_TOKEN` itself (CLI default: env).
4. Size limits — SDK allows SKILL.md up to 1 MiB, CLI caps added instructions at 20,000 bytes; state SDK limits, how oversized is reported, whether a caller can pass a byte limit (structured failure, no truncation, no crash).
5. Source-string parser — optional, spec's call (default per pipeline rule 11: not built unless justified; if added, state the grammar).
6. Root-level names only — every name the CLI needs in `vidbyte.__all__` and in the regenerated contract (CLI lint C028/C011).
7. Version — 0.2.2 consistent across `pyproject.toml`, `vidbyte/__init__.py`, regenerated contract (CLI lint C029).
(Full verbatim text in request.md §C "Consumer requirements".)

## Decisions the orchestrator made
- 2026-10-15 15:04 — Slug `public-skill-loader`, branch `feat/public-skill-loader`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader` from `origin/main` `179d8adc` — playbook defaults; AGENTS.md states no worktree/branch convention.
- 2026-10-15 15:04 — Did not `git fetch` in the main checkout: `git ls-remote origin refs/heads/main` already equals local `origin/main` (`179d8adc`), so no fetch was needed and the main checkout's refs stay untouched.
- 2026-10-15 15:04 — Unset the branch's auto-configured upstream (`origin/main`) so no later `git push` can target main.
- 2026-10-15 15:05 — Recorded the parent session's seven consumer requirements in request.md §C and here as design inputs (not user decisions); item 5 (parser) carried with default "not built" unless the spec justifies it, per pipeline rule 11.

- 2026-10-15 16:20 — S1 review round 1 (verdict SOUND WITH FIXES; 1 Blocker R-1, 2 Major, 3 Minor). R-1: `origin/main` moved after the base: `a7ed9cde` "release: bump vidbyte-sdk to 0.3.0 with the output connectors (#1085)" landed 15:34, then #1086–#1088 (`origin/main` = `c9d31a7f`). Orchestrator verified: tag `v0.3.0` = `a7ed9cde` exists on origin and PyPI's latest vidbyte-sdk is 0.3.0 (releases 0.1.0, 0.2.0, 0.2.1, 0.3.0). The S1 reviewer ran a `git fetch` (updated remote-tracking refs only; main checkout's working tree and branch untouched).
- 2026-10-15 16:20 — DECIDED (orchestrator, from request.md §C, not a new user decision; user may override): the version target becomes **0.3.1**, not 0.2.2, on a branch rebased onto current `origin/main`. Reasons: (1) 0.3.0 is tagged and published, so a 0.2.2 literal on main would lower main's version (and `publish.yml` checks tag == `v{version}`); (2) request.md §C states the reason for the bump: "because the CLI will raise its floor to the first release that contains the loader" — with 0.3.0 published, that first release is the next patch, 0.3.1 (the user's choice of a patch bump for an additive export is preserved); (3) the only literal-0.2.2 path is a new `release/0.2.x` maintenance line cut from `179d8adc`, which is a release-process addition nobody asked for (pipeline rule 11) and keeps the loader off main; (4) the version phase is isolated and mechanical, so a user correction is cheap. Surfaced as Q-8 in the spec and prominently in spec-summary.md and the final report. Consequence for the CLI run: its pin `>=0.2.1,<0.3` must become `>=0.3.1,<0.4` and it must absorb 0.3.0.
- 2026-10-15 16:20 — Rebased `feat/public-skill-loader` (4 docs-only commits, unpushed) onto `origin/main` `c9d31a7f` before S2, so tests and code target current main. The 4 new main commits touch no skills code: version literals (now `0.3.0` in the same nine places), `docs/design/release-0-3-0.md`, and compaction/provider fixes with their tests.

- 2026-10-15 17:10 — S1 review round 2 (scoped to r2): SOUND WITH FIXES, 0 Blocker, 1 Major (R-7), 4 Minor (R-8..R-11); all round-1 findings resolved. Sent to the author for the final revision r3 with `status: approved` (cap of two rounds reached; review rounds are the approval).
- 2026-10-15 17:10 — `origin/main` moved again to `9aaf662a` (#1089, #1090: only `vidbyte/context/algorithms/*` and four tests; no overlap with any cited file or `lint/`). Decided NOT to rebase again: base stays `c9d31a7f`; avoids churn; GitHub merges cleanly. After the contract commit, any update from main is by merge with Ask-first approval (spec §12.6/§14 per R-9).
- 2026-10-15 17:10 — Notified the parent session (SendMessage to main) of the 0.3.1 version decision so the user can override; no reply yet.

- 2026-10-15 17:35 — S1 done: spec r3 `status: approved` (`843e2852`). Q-n defaults applied: Q-1 yes (ConfigurationError root export built); Q-2..Q-7, Q-9 no (not built); Q-8 version 0.3.1. Wrote spec-summary.md (the parent cannot see orchestrator text). Noted the S1 author's deviation on R-11's first sentence (CLI origin/main `64b04b3` #166 already pins `>=0.3.0,<0.4`) — accepted, it is a fact correction.

## User replies (verbatim)
- none yet

## Niche facts accumulated (carried into every later briefing)
- Existing loader: `SkillLoader` in `vidbyte/agents/skills/loader.py:31`, async `load()` only (:49), returns one `SkillResolution` per entry in input order. `SkillResolution` is defined in `vidbyte/lib/dataclasses/skills.py:234` and is exported by no `__init__` (root included) — *source:* S0 scout
- No caller can pass a byte limit or a credential to the loader today. `SKILL_MARKDOWN_MAX_BYTES` = 1,048,576, counts the whole file, inclusive. The loader reads `GITHUB_TOKEN` and the vendor API keys itself at load time — *source:* S0 scout
- `load()` re-raises any BaseException from a resolver group (`loader.py:61-66`): a programming error or a cancellation aborts every entry; expected failures come back as data — *source:* S0 scout
- `SkillLoader.__init__` does no validation (no type check, no duplicate-name check); that lives only in `JevAlignmentSettings._normalized_skills` — *source:* S0 scout
- `SkillDocument.text` is the body WITHOUT frontmatter, while the 1 MiB cap counts the whole file; a vendor download may be up to 32 MiB before the SKILL.md inside it is capped — *source:* S0 scout
- Tests pin agent-centric detail wording: "next run" (`tests/.../test_skill_sources_vendor.py:287`) and the local not-found message "create a new agent" (`vidbyte/agents/skills/local.py:59`); rewording breaks them — *source:* S0 scout
- The repo's sync-wrapper pattern raises inside a running event loop (`TextModelRunner.run`, `vidbyte/lib/runners/text.py:93-100`). In THIS repo lint C011 is the sync-wrapper rule (not the CLI's import rule of the same number) — *source:* S0 scout
- Root import rule S015: every public name imported in `vidbyte/__init__.py` must be in `__all__`. `vidbyte/__init__.py` is already 1,366 lines and its `__all__` is unsorted. The import-order hazard (no `from vidbyte.agents import …` inside the loader package) applies only to imports written inside `vidbyte/agents/skills/` — *source:* S0 scout
- The contract currently records `source.commit` `2bb5a8e9`, not `179d8adc`; regenerating stamps the new HEAD — *source:* S0 scout
- Test commands: one file `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_contract.py`; area `PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload tests/test_jev_skill_preload.py`; framework pytest 8.3.5 + pytest-asyncio 1.3.0 — *source:* S0 scout (code-map §1, §3)
- Contract names (spec r1): `SkillLoader(entries)`, `await loader.load()` → `tuple[SkillResolution, ...]` in input order, `loader.documents()`, `SkillResolution.document/.reason/.detail/.transient`, `SkillDocument.text`, `ConfigurationError.details`, new record `SkillEntries` (`vidbyte/lib/dataclasses/skills.py`); new root names `SkillLoader`, `SkillResolution`, `ConfigurationError` — *source:* S1 author
- `ConfigurationError.details` keys fixed: `{"entries_type"}` non-tuple; `{"position" (0-based), "entry_type"}` bad element; `{"names": sorted}` repeated names; never the rejected value or a credential. Only a tuple accepted (list rejected) — *source:* S1 author
- Fake network seam is `HttpTransport._send_once`; `tests/features/jev_skills_preload/` conftest fixtures apply only in that folder, so a new test pack needs its own `conftest.py` — *source:* S1 author
- Root import placement: loader import after `vidbyte.agents.pricing`; `SkillResolution` after the prosecutor_defender_judge block; `ConfigurationError` inside the existing `vidbyte.lib.errors` block; the three names in `__all__` right after "SkillUnavailableReason"; check S051 over the whole tree — *source:* S1 author
- C016 reports the contract stale between the source commit and the contract commit; run the full gate only after the contract commit — *source:* S1 author
- Disk: C: briefly hit 0 bytes free during S1; ~17 GB free at 15:45. If a write fails, check `df -h /c` first — *source:* S1 author / orchestrator
- Spec r2 (`3a793017`): `SkillLoader(entries: Sequence[...])` — `__init__` converts any non-str/bytes iterable to a tuple inside ONE expression `SkillEntries(entries=tuple(entries) if isinstance(entries, Iterable) and not isinstance(entries, (str, bytes)) else entries)` (splitting the check into a boolean trips mypy arg-type); lists accepted (D-14) — *source:* S1 author r2
- Under `PYTHONPATH=$(pwd)`, `importlib.metadata.version("vidbyte-sdk")` returns 0.2.1 (shared editable install metadata) while `vidbyte.__version__` reads the worktree; version tests must read the worktree's files, not distribution metadata (spec §13) — *source:* S1 author r2
- Version 0.3.1 lives in eight hand-edited literals plus the regenerated contract; S009 (mypy) ratchet is 350 — *source:* S1 author r2
- `vidbyte/agents/skills/`, `vidbyte/lib/dataclasses/skills.py`, `vidbyte/agents/jev/`, `lint/baseline.json`, `lint/mypy.ini` are byte-identical between 179d8adc and c9d31a7f — *source:* S1 author r2
- INV-18/AC-18/FR-12: `JevAlignmentSettings(skills=t)` and `SkillLoader(t)` raise equal `details` for repeated names (drift guard); `test_skill_sources_entries.py:216-229` DUPLICATES table is reusable — *source:* S1 author r2
- CLI origin/main (`64b04b3`, #166) already pins `vidbyte-sdk[codex]>=0.3.0,<0.4`; only the paused CLI branch (`b8af987`) has `>=0.2.1,<0.3`. So 0.3.1 is a floor raise for CLI main, and 0.2.2 would sit below CLI main's floor — *source:* S1 author r3
- `origin/main` keeps moving (3b879c67 at 17:30, #1089–#1093); none touch files this PR edits, area tests, lint/, scripts/ or contracts/. Branch stays on `c9d31a7f` — *source:* S1 author r3
- Generator prints "already current … nothing written" when data is unchanged (`scripts/generate-sdk-public-api.py:65-67`, `:112`); C016/`--check` never check `source.commit` reachability — *source:* S1 reviewer r2
- `VersionResolver.resolve()` / `vidbyte --version` read distribution metadata first (0.2.1 locally via the shared editable install); the fallback literal at `vidbyte/cli/__init__.py:58` is observable only with `vidbyte.cli.metadata.version` patched to raise `PackageNotFoundError`, or by reading the file — *source:* S1 reviewer r2
- Per-entry credentials exist and are public: `GitHubSkill(token=...)`, `AnthropicSkill(api_key=...)`, `OpenAISkill(api_key=...)`; the loader reads `GITHUB_TOKEN` / provider keys only inside `load()` when the field is None — *source:* S1 author r3
