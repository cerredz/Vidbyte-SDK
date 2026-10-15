---
slug: public-skill-loader
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader
branch: feat/public-skill-loader
base_commit: 179d8adc8872d9a616f190c93c75b0169ec719c4
pr:
until: none
started: 2026-10-15 15:04
---

# Pipeline: Public, root-exported skill loader in vidbyte-sdk (resolve every #904 skill source without JevAgent), version 0.2.2

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 15:04 | 15:20 | reports/S0-scout.md | base_commit 179d8adc; context/code-map.md (4 sections, 18 files) |
| S1 spec + review | running | 15:22 | | reports/S1-spec-author.md | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Environment facts (carried into every briefing)
- PR repo `cerredz/Vidbyte-SDK` (origin `https://github.com/cerredz/Vidbyte-SDK.git`), base `main`. Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader`, branch `feat/public-skill-loader`, created from `origin/main` `179d8adc`. The branch has NO upstream (orchestrator unset the auto-tracked `origin/main`); first push must be `git push -u origin feat/public-skill-loader`.
- Main checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` is OFF-LIMITS: it holds the user's untracked files (`docs/design/*.md`, `docs/pre-design/`). Never modify it, pull/fetch in it, stash in it, or switch its branch. (It is on `main` at `179d8adc` now, not at `d9c01461` as the parent briefing said; irrelevant to this run except that it must stay untouched.)
- The default `python` (`C:/Users/422mi/AppData/Local/Programs/Python/Python311/python.exe`) has an editable install of vidbyte-sdk pointing at the main checkout. Never run `pip install -e` from the worktree (it would repoint the user's install). From the worktree root, `python -c "import vidbyte; print(vidbyte.__file__)"` prints the WORKTREE's `vidbyte/__init__.py` (verified by orchestrator). Run tests as `PYTHONPATH=$(pwd) python -m pytest …` from the worktree root (scout, code-map §1).
- Full local gate: `python scripts/run_ci.py` (on SDK main today: 5173 passed, 14 skipped, plus lint, build, twine, install smoke). Stages: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, `python scripts/run_ci.py --stage package` (no PYTHONPATH). Semgrep is NOT in run_ci.py; it runs in `.github/workflows/static-policy.yml:23-30`: `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with `semgrep==1.170.1`, tracked files only (`git add` first).
- Public API contract: `python scripts/generate-sdk-public-api.py` regenerates `contracts/sdk-public-api.json`; it refuses to write while `vidbyte/__init__.py` or `pyproject.toml` have uncommitted changes. Commit source first, then generate, then commit the regenerated file alone. Never hand-edit; never amend after generating. `--check` must pass (lint C016).
- Version bump 0.2.1 → 0.2.2: exactly nine places hold the literal (scout): pyproject.toml, vidbyte/__init__.py, CLI fallback, MCP server default, MCP clientInfo, README.md, llms.txt, bug template, and the regenerated contract. No test pins the version.
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
