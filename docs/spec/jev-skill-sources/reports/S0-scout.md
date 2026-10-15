# S0 Scout report: jev-skill-sources

- **Stage:** S0 scout
- **Output:** `docs/spec/jev-skill-sources/context/code-map.md`
- **Base:** `ba3e4ca5` on branch `feat/jev-skill-sources`. No commits were
  made.
- **Restrictions kept:** no edits outside these two files, no installs, no
  gate or test runs, no network calls. Under `docs/` I read only
  `docs/spec/jev-skill-sources/request.md`.

## Planned list (before reading)

**Rules and maps**
- AGENTS.md
- REPO_MAP.md
- request.md
- the spec-pipeline `vidbyte-gates.md`
- the field-guide index and the entries that apply

**Preload wiring**
- `vidbyte/agents/jev/alignment/skills.py` and `__init__.py`
- `vidbyte/agents/jev/agent.py`
- `vidbyte/agents/jev/runtime.py`
- `vidbyte/agents/jev/preload.py`
- `vidbyte/agents/jev/response.py`
- `vidbyte/agents/jev/settings.py`
- `vidbyte/agents/jev/__init__.py`
- `vidbyte/agents/jev/README.md`

**Records, enums, and constants**
- `vidbyte/lib/dataclasses/skills.py` and `vidbyte/lib/dataclasses/jev.py`
- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/enums/skills.py`, and
  `vidbyte/lib/enums/__init__.py`
- `vidbyte/lib/constants/jev.py` and `vidbyte/lib/constants/__init__.py`

**Shared helpers**
- `vidbyte/lib/http/` (transport, parser, and `__init__`)
- `vidbyte/lib/errors/base.py`
- `vidbyte/lib/registries/models.py` (env keys)
- YAML, zip, and frontmatter users

**The packaged skill catalog** (to check for name collisions)
- `vidbyte/skills/` (catalog, `__init__`, and README)

**Public exports and contract**
- `vidbyte/__init__.py`, `vidbyte/agents/__init__.py`,
  `vidbyte/lib/__init__.py`, and `vidbyte/lib/dataclasses/__init__.py`
- `contracts/`

**Tests and feature pack**
- the skill preload tests, script, and FEATURE.md
- the HTTP-fake test patterns

**Lint and CI**
- `lint/` (README, baseline, discovery, and the relevant rules)
- `scripts/run_ci.py`
- `.github/workflows/`
- `.semgrep/`
- `pyproject.toml`

**Patterns for the new package**
- the nearest new-package shape (`vidbyte/agents/coding_context/`)
- the per-vendor HTTP client pattern
  (`tools/builtins/operations/clients/`)

## Files actually read

**Rules and maps**
- AGENTS.md (whole) and CLAUDE.md
- REPO_MAP.md (whole)
- request.md (whole)
- `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/vidbyte-gates.md`
- field guide `init.md`
- field-guide entries read in full:
  - local-ci-verification
  - blocking-lint-invariants
  - comment-format
  - jev-capability-layout
  - cli-backed-source-integrations
  - diagnostic-context
  - provider-api-contracts
  - fallback-coordination
  - prebuilt-agents
  - context-primitives
  - class-bound-helpers
  - strict-config-dataclasses
- declarative-config-resolution: headings plus its first and last sections
- runtime-boundaries and review-scope: headings only

**Preload wiring** (all under `vidbyte/agents/jev/`)
- `alignment/skills.py` and `alignment/__init__.py`
- `agent.py`, `runtime.py`, `preload.py`, `response.py`, `settings.py`,
  `__init__.py`, `README.md`

**Records, enums, and constants** (all under `vidbyte/lib/`)
- `dataclasses/skills.py`
- `dataclasses/jev.py`. **Partially read:** the file is 4,673 lines and
  about 390 KB, which exceeds the reader limit. I read lines 1-243,
  486-507, 3690-3919, and the `__all__` tail.
- `enums/jev.py`, `enums/skills.py`, `enums/__init__.py`
- `constants/jev.py` (lines 1-130, 440-500, 730-758) and
  `constants/__init__.py`

**Shared helpers** (all under `vidbyte/lib/` unless a full path is given)
- `http/transport.py`, `http/__init__.py`, `http/parser.py`
- `errors/base.py` (in parts)
- `jev/decision.py`, `jev/managed.py`, `jev/preflight/skills.py` (header
  and class)
- `config/loader.py` (in parts) and `registries/models.py` (in parts)
- `util/` (module listing)
- `vidbyte/agents/base.py:1280-1295`
- the `_DuplicateKeySafeLoader` lines in `vidbyte/config/loader.py` (grep)
- `vidbyte/harnesses/config.py` (yaml lines)
- `vidbyte/sessions/portable.py` and
  `vidbyte/lib/tools/filesystem/backends/local.py` (zip lines)

**The packaged skill catalog and the new-package pattern**
- `vidbyte/skills/catalog.py`, `vidbyte/skills/__init__.py`,
  `vidbyte/skills/README.md`
- `vidbyte/agents/coding_context/`: README.md, `agents_md.py`,
  `root_file.py`, plus the file listing
- `vidbyte/tools/builtins/operations/clients/_base.py` and `brave.py`

**Public exports and contract**
- `vidbyte/__init__.py` and `vidbyte/agents/__init__.py`
- `vidbyte/lib/__init__.py` and `vidbyte/lib/dataclasses/__init__.py` (the
  `SkillDocument` lines)
- `contracts/sdk-public-api.json` and `contracts/README.md`

**Folder READMEs**
- `vidbyte/agents/README.md`
- `vidbyte/lib/README.md`

**Tests and feature pack**
- `tests/test_jev_skill_preload.py`
- `scripts/test-jev-skills-preload.py`
- `tests/features/jev_skills_preload/FEATURE.md`
- the fake patterns in:
  - `tests/features/coding_agent/conftest.py`
  - `tests/test_web_operation_client_retry.py`
  - `tests/test_jev_managed_gateway.py`
  - `tests/test_sources_base.py`
  - `tests/features/coding_agent/test_coding_agent_web_fetch.py`
- `skills/jev-agent/SKILL.md` (grep only)

**Lint and CI**
- `lint/README.md`, `lint/baseline.json`, `lint/core/discovery.py`,
  `lint/ruff.toml`
- lint rules:
  - architecture: A001, A002, A003, A005, A006, A007, A009
  - core: C001, C006, C007, C008, C013, C015, C016
  - static: S010, S011, S012, S013, S015, S016, S017, S019, S020, S045,
    S047, S049, S052, S061, S063, S064
- `scripts/run_ci.py`
- `.github/workflows/ci.yml`, `static-policy.yml`, `agents-md-placement.yml`
- `.semgrep/typed-mapping-boundary-policy.yml`
- `pyproject.toml`

## What the hints and vidbyte-gates got wrong

### vidbyte-gates.md

**1. "CI runs the same `run_ci.py`; semgrep is part of it."**
- Semgrep is not in `scripts/run_ci.py`. It runs only in
  `.github/workflows/static-policy.yml`.
- Neither workflow runs automatically. `ci.yml` triggers only on
  `workflow_dispatch` and `workflow_call`, and `static-policy.yml` only on
  `workflow_dispatch`.

**2. The install step.**
- The table lists `python -m pip install -e ".[dev]"`. AGENTS.md gives no
  install command.
- In a worktree, an editable install can resolve `vidbyte` to the canonical
  checkout. The field guide says to run the source stage with
  `PYTHONPATH=<worktree>` and the package stage without it.

**3. "Final line must read `AGENT-LINT: PASS`."**
- I did not verify this for the SDK lint runner.

### Area hints and the request

**4. `lib/constants/skills.py` does not exist.** The constants modules are:
codex, coding, cot_events, failure, jev, reasoning_strategies, runners,
speed, and trace.

**5. The JEV docs do not cover the preload.**
- `vidbyte/agents/jev/README.md` exists but never mentions skills or
  alignment.
- `skills/jev-agent/SKILL.md`, which the request names as the agent skill
  doc, also never mentions the preload.

**6. Only a few lib subfolders have READMEs.** Under `lib/`, only
`providers` and `registries` have one, plus `lib/README.md` itself.

**7. The request cites the wrong YAML loader.**
- It points to `vidbyte/lib/config/loader.py`.
- The exported `YamlLoader` is `vidbyte/config/loader.py`, which has its own
  private duplicate-key loader at :65.
- Both loaders are private.

**8. The batching field-guide entry is out of date.** It says "one typed Jev
request per candidate", but the code packs several candidates into each
request.

**9. The request assumes a per-run reset in a `finally` block.**
`vidbyte/agents/jev/runtime.py` contains no `finally`.

**10. The request's line hint for `JevSkillResult` is correct.** It is at
`vidbyte/lib/dataclasses/jev.py:3727`.
