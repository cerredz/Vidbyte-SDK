---
slug: jev-skill-sources
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-skill-sources
branch: feat/jev-skill-sources
base_commit: ba3e4ca51ad78c44026dfd296663ae7b092bce56
pr:
until: none
started: 2026-10-11 23:17
---

# Pipeline: JevAgent skill sources — declarative skill entries resolved under the hood

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-11 23:17 | 2026-10-12 | reports/S0-scout.md | base ba3e4ca5; code-map.md (4 sections, 12 contradictions N1–N12, gaps G1–G9) |
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
- 2026-10-12 — Accepted the S0 scout's artifacts without its STATUS block: the previous Claude Code session ended while the scout was running; both files (code-map.md 42.5 KB with 4 sections, reports/S0-scout.md) were complete on disk and passed the spot-check.
- 2026-10-12 — `SkillDocument` stays publicly exported and stays accepted in `JevAlignmentSettings.skills` (treated as an inline entry). request.md §C said it "becomes internal", but code-map N3 shows `tests/test_jev_skill_preload.py:25,164` asserts the root export and contracts/README requires notifying vidbyte-cli owners on export removal; existing test assertions are a contract no agent may change. This also shrinks the change.
- 2026-10-12 — User directive "core skills code logic … inside vidbyte/agents/skills" vs AGENTS.md:76 ("questions and actions stay inside vidbyte/agents/jev/ and vidbyte/lib/jev/") (code-map N1): the user's directive stands. Reconciliation for the spec: source resolution is agent-agnostic (not a Jev question or action) and lives in vidbyte/agents/skills/; the Jev-specific wiring (calling the loader from JevSkillsPreload) stays in vidbyte/agents/jev/.
- 2026-10-12 — Env-key fallback (request.md §C) stands, but code-map N12 shows `find_vidbyte_api_key` treats a `vb_live_` value in OPENAI_API_KEY/ANTHROPIC_API_KEY as a Vidbyte key: the spec must guard that a Vidbyte key is never sent to Anthropic/OpenAI. This is an edge case of the agreed design (user Prompt 3 asked for every failure mode per source), not a new control.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- No `finally` in `vidbyte/agents/jev/runtime.py`; it assigns `self.user_tools`/`self.tools` at :156-158/:177; whether `BaseAgent._runtime()` (base.py:1285) builds a runtime per run is unverified — the spec author must find where a per-agent loader cache can safely live (the preload is built in `agent.py:80-89` from `settings.alignment.skills`). — *source:* S0 code-map N11, N5
- Name collisions: `Skill` is already exported (TypeAlias from `vidbyte.lib.enums`, and from `vidbyte.skills`), plus `Skills`, `SkillRecord`, `SkillEnums`; a new base class must not be named `Skill`. `source` means "display label" on `SkillDocument`/`JevSkillResult`, so `SkillsShSkill`'s owner/repo field needs a different name. — *source:* S0 code-map N4
- `JevSkillResult.description` must be non-blank today (`vidbyte/lib/dataclasses/jev.py:3742-3745`); the preload seeds results from `skill.description` (`alignment/skills.py:73`). — *source:* S0 code-map N5
- A SKILL.md frontmatter parser already exists without YAML at `vidbyte/skills/catalog.py:223-247` (principle 5: reuse/extract, don't duplicate). The exported `YamlLoader` is `vidbyte/config/loader.py` (private `_DuplicateKeySafeLoader` at :65); `vidbyte/lib/config/loader.py` imports upward. — *source:* S0 code-map N6, N7
- `HttpTransport`: `HttpResponse.raw_bytes` is set only when `max_response_bytes` is passed (transport.py:95 vs :71); non-2xx is returned not raised; connection error/timeout raises `ProviderRequestError(status_code=None)`; oversize raises `ProviderRequestError` with the status; 403 is not retried by default; header-key casing in `dict(response.headers)` is unverified. — *source:* S0 code-map N9
- Lint discovery and semgrep read only git-tracked files: new files must be `git add`-ed before `python lint/run.py` sees them. A001 covers all tracked `.py` incl. tests. S047 flags `open()` in async functions (ASYNC230); S045 flags async functions with a timeout-like parameter. — *source:* S0 code-map G3, G9
- `vidbyte/agents/__init__.py` imports every subpackage; `vidbyte/agents/jev/` importing `vidbyte/agents/skills/` must not create a cycle (A006 counts cycles). `vidbyte/lib/dataclasses/__init__.py` imports `vidbyte.context.primitives`. — *source:* S0 code-map G7
- `vidbyte/lib/dataclasses/jev.py` is 4,673 lines (AGENTS.md wants files well under 1,000): put new skill-entry records in `vidbyte/lib/dataclasses/skills.py`; edit `JevSkillResult` in place. No `vidbyte/lib/constants/skills.py` exists yet. — *source:* S0 code-map G1, G2
- Gates: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with PYTHONPATH unset; `python lint/run.py` (`--rule <ID>`, `--all`); semgrep is NOT in run_ci (only `.github/workflows/static-policy.yml`, dispatch-only; `pip install semgrep==1.170.1` in its own venv); `ci.yml` is `workflow_dispatch`/`workflow_call` only. — *source:* S0 code-map §1
- `vidbyte/agents/jev/README.md`, `skills/jev-agent/SKILL.md`, and REPO_MAP's JEV table do not mention the preload at all; `tests/features/jev_skills_preload/FEATURE.md` says source loaders are deferred. — *source:* S0 code-map N8, G8
