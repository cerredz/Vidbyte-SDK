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
| S1 spec + review | done | 2026-10-12 | 2026-10-12 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-2.md | spec r3 approved (e9a0eeaf); round 1 SOUND WITH FIXES (1B/5M/9m), round 2 SOUND WITH FIXES (2B/0M/6m), all 23 findings applied |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-12 — Accepted the S0 scout's artifacts without its STATUS block: the previous Claude Code session ended while the scout was running; both files (code-map.md 42.5 KB with 4 sections, reports/S0-scout.md) were complete on disk and passed the spot-check.
- 2026-10-12 — `SkillDocument` stays publicly exported and stays accepted in `JevAlignmentSettings.skills` (treated as an inline entry). request.md §C said it "becomes internal", but code-map N3 shows `tests/test_jev_skill_preload.py:25,164` asserts the root export and contracts/README requires notifying vidbyte-cli owners on export removal; existing test assertions are a contract no agent may change. This also shrinks the change.
- 2026-10-12 — User directive "core skills code logic … inside vidbyte/agents/skills" vs AGENTS.md:76 ("questions and actions stay inside vidbyte/agents/jev/ and vidbyte/lib/jev/") (code-map N1): the user's directive stands. Reconciliation for the spec: source resolution is agent-agnostic (not a Jev question or action) and lives in vidbyte/agents/skills/; the Jev-specific wiring (calling the loader from JevSkillsPreload) stays in vidbyte/agents/jev/.
- 2026-10-12 — Env-key fallback (request.md §C) stands, but code-map N12 shows `find_vidbyte_api_key` treats a `vb_live_` value in OPENAI_API_KEY/ANTHROPIC_API_KEY as a Vidbyte key: the spec must guard that a Vidbyte key is never sent to Anthropic/OpenAI. This is an edge case of the agreed design (user Prompt 3 asked for every failure mode per source), not a new control.

- 2026-10-12 — S1 open questions take their stated defaults (no user reply): Q-1 no (re-check local/missing-key failures every run), Q-3 no (keep `SkillsShSkill.source`), Q-4 no (no in-repo JevAgent skill-guide update), Q-5 no (no computedHash verification), Q-6 not built (`GitHubSkill.path="."` rejected at construction), Q-7 no (a lock without an entry for the skill loads without the source check). Q-2 was resolved by the author as built (D-27 step deadline) because request.md §C assumes a bounded hang.
- 2026-10-12 — A-1/A-4 (Anthropic/OpenAI content route and body format) are marked "pending the user's real-key QA". Proceeding to S2/S3 without it: the design handles both outcomes (zip or bare SKILL.md; `latest` refused → `latest_version`/`latest_version_id`; distinct "content route not found" detail), so a wrong assumption surfaces as a visible per-skill reason, not a crash. Carry it to the final report as follow-up QA.

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
- Existing `tests/test_jev_skill_preload.py` must pass unchanged: it calls `preload._build_batches("…")` with ONE argument before any run, reads `preload.decision.model`, and monkeypatches `agent.skill_preload.run` on the instance (:415-424) — so `JevSkillsPreload` stays a plain class (no `__slots__`, not frozen). `JevSkillResult` now requires a reason on every UNAVAILABLE result, so it changes in P3 together with the preload. — *source:* S1 author r1, reviewer r2
- `BaseAgent._runtime()` rebuilds the runtime every run; the preload (and the loader cache) is built once in `JevAgent.__init__`. — *source:* S1 author r1 (verified by reviewer)
- `SkillFetch` always passes `max_response_bytes`; a `_send_once` fake must set `raw_bytes`, use lowercase header keys, and raise `ProviderRequestError(status_code=200)` itself to simulate an oversized body. The step deadline is patchable at `vidbyte.agents.skills.fetch.SKILL_FETCH_DEADLINE_SECONDS` (read at call time). — *source:* S1 author r1–r3
- Inside `vidbyte/agents/skills/` never import `vidbyte.agents.jev` or use `from vidbyte.agents import …` (JEV imports the loader while `vidbyte.agents` is half-initialized). — *source:* S1 author r1
- Windows: `PureWindowsPath(".agents/skills") / "C:x"` is `C:x`; skill names must reject `:`, `/`, `\`, NUL, `.`, `..`. A007 forbids `read(CAP + 1)` — use the `os.fstat` pattern in `RootFileLoader._read_capped`. TID251 bans `asyncio.Lock` (and `TypedDict`, `assert_never`). — *source:* S1 author r1, reviewer r1
- PyYAML 6.0.2 `safe_load` raises `RecursionError`/`ValueError` outside `yaml.YAMLError`; `json.loads` raises `RecursionError` outside `JSONDecodeError`; corrupt zips raise `ValueError` etc. — catch at the parse call only (D-29, D-20). Read zip members only when STORED or DEFLATED. — *source:* S1 reviewers r1, r2
- `HttpTransport.request` retries only 408/409/425/429/5xx; any `httpx.RequestError` incl. timeouts is re-raised immediately as `ProviderRequestError` (transport.py:47-56). `asyncio.timeout` expiry check via `deadline.expired()` per `harnesses/execution.py:205-219`. `HTTPStatus(529)` raises — look up status maps by int. — *source:* S1 reviewers r1, r2
- C020 skips tests (tests may spell `vb_live_`); production strings must build the prefix from `VIDBYTE_API_KEY_PREFIX`. Strip keys before the prefix check. A002 needs an `@intent` block when referencing `FETCH_FAILED`. Vendor keys come from `ProviderModelRegistry.resolve_api_key(PROVIDER, entry.api_key)` (already strips); only GitHub strips its token by hand. — *source:* S1 reviewer r2, author r3
- mypy 2.3.1 with `lint/mypy.ini` accepts `SkillResolver(ABC, Generic)` with a constrained `VendorSkillT`. `vidbyte/lib/enums/skills.py` is a current A001 finding; upgrading its header is IMPROVED → lower the baseline to 642 via `python lint/run.py --rule A001 --update-baseline`. — *source:* S1 reviewer r2, author r1
