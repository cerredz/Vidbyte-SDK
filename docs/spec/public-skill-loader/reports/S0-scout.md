# S0 scout report: public-skill-loader

- Stage: S0 scout.
- Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-public-skill-loader`, branch
  `feat/public-skill-loader`, HEAD `179d8adc8872d9a616f190c93c75b0169ec719c4`.
- No commits, installs, lint runs or tests. The one command executed was
  `python -c "import vidbyte; print(vidbyte.__file__)"`, which resolved to the worktree's
  `vidbyte/__init__.py`.
- Output: `docs/spec/public-skill-loader/context/code-map.md`, with four `## ` sections.

## Planned file list

The list started from the orchestrator's areas hint. Each entry was confirmed with `git grep` or by
opening it, and the list was extended until a pass added nothing.

1. **Loader package `vidbyte/agents/skills/`.** `__init__.py`, `loader.py`, `resolver.py`,
   `fetch.py`, `markdown.py`, `inline.py`, `local.py`, `skills_sh.py`, `github.py`, `vendor.py`,
   `anthropic.py`, `openai.py` and `README.md`.
2. **Records, enums and bounds.** `vidbyte/lib/dataclasses/skills.py`,
   `vidbyte/lib/enums/skills.py`, `vidbyte/lib/enums/__init__.py` and
   `vidbyte/lib/constants/skills.py`.
3. **Export chain.** `vidbyte/__init__.py`, `vidbyte/agents/__init__.py`,
   `vidbyte/agents/jev/__init__.py`, `vidbyte/lib/__init__.py` and
   `vidbyte/lib/dataclasses/__init__.py`.
4. **Jev consumer (must keep behavior).** `vidbyte/agents/jev/alignment/skills.py`,
   `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/agent.py` and
   `vidbyte/agents/jev/preload.py`.
5. **Contract.** `contracts/sdk-public-api.json`, `contracts/README.md`,
   `scripts/generate-sdk-public-api.py` and `lint/core/public_api_contract.py`.
6. **Version literals** (from `git grep -n "0\.2\.1" -- ':!docs'`). `pyproject.toml`,
   `vidbyte/cli/__init__.py`, `vidbyte/mcp_server/server/core.py`, `vidbyte/tools/mcp/client.py`,
   `README.md`, `llms.txt` and `.github/ISSUE_TEMPLATE/bug_report.yml`.
7. **Maps and docs.** `REPO_MAP.md` and `vidbyte/agents/README.md`.
8. **Gate and lint.**
   - `scripts/run_ci.py`, `pyproject.toml` (pytest and dev deps), `lint/README.md` and
     `lint/baseline.json`.
   - The rules C016, S015, A006 and A009.
   - The workflows `.github/workflows/agents-md-placement.yml` (existence only) and
     `static-policy.yml`.
9. **Tests.** `tests/features/jev_skills_preload/`: FEATURE.md, conftest.py and all twelve
   `test_skill_sources_*.py` modules. Also `tests/test_jev_skill_preload.py`.
10. **Sync-twin precedent.** `vidbyte/lib/runners/text.py` and `vidbyte/agents/base.py`.

## Files actually read

### In full

- `AGENTS.md`, `CLAUDE.md` and `docs/spec/public-skill-loader/request.md`.
- All 13 files in `vidbyte/agents/skills/`.
- `vidbyte/lib/dataclasses/skills.py`, `vidbyte/lib/enums/skills.py`, `vidbyte/lib/enums/__init__.py`
  and `vidbyte/lib/constants/skills.py`.
- `vidbyte/agents/jev/alignment/skills.py`, `vidbyte/agents/jev/preload.py` and
  `vidbyte/agents/jev/alignment/__init__.py`.
- `scripts/generate-sdk-public-api.py`, `scripts/run_ci.py` and `contracts/README.md`.
- `tests/features/jev_skills_preload/FEATURE.md`, its `conftest.py`, all twelve
  `test_skill_sources_*.py` modules, and `tests/test_jev_skill_preload.py`.
- Field guide `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`: `init.md`,
  `local-ci-verification.md`, `blocking-lint-invariants.md`, `strict-config-dataclasses.md`,
  `comment-format.md`, `review-scope.md`, `provider-api-contracts.md` and `class-bound-helpers.md`.
- CLI consumer:
  `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-cli-agent-skill-sources/docs/spec/agent-skill-sources/reports/S1-spec-author.md`.

### In part (the sections the code map cites)

- `REPO_MAP.md` (the File Index entries for `agents/skills`, `lib`, `lib/dataclasses`,
  `lib/enums`, `lib/constants` and `lib/http`).
- `vidbyte/__init__.py`: the version line, the import blocks and the `__all__` skill lines.
- `vidbyte/agents/__init__.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/lib/__init__.py` and
  `vidbyte/lib/dataclasses/__init__.py`: the skill import and export lines.
- `vidbyte/agents/jev/agent.py`: imports and lines 80-89.
- `vidbyte/agents/jev/settings.py`: `JevAlignmentSettings` and `_normalized_skills`.
- `vidbyte/agents/README.md`: around line 297.
- `contracts/sdk-public-api.json`: header and skill lines.
- `lint/core/public_api_contract.py`: lines 405-433.
- The lint rule modules C016, S015, A009 and A006, `lint/README.md`, and the
  `lint/baseline.json` counts.
- `pyproject.toml`: version, dev deps and pytest options.
- `vidbyte/lib/http/transport.py`: method signatures only.
- `vidbyte/lib/runners/text.py:88-100` and `vidbyte/agents/base.py:1052-1060`.
- The version-literal lines in each file.
- `git show --stat 29fbfd28`.
- `.github/workflows/static-policy.yml`: the semgrep lines, via grep.
- `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`: grep, plus lines 19
  and 36.
- The CLI `context/code-map.md`: lines 140-199 and 355-429, plus a grep.

### Deliberately not read

- Anything else under `docs/`, including `docs/spec/jev-skill-sources/` and
  `docs/design/release-0-2-1.md`.
- The main checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk`.
- The field-guide files that do not apply: runtime-boundaries, prebuilt-agents,
  jev-capability-layout and declarative-config-resolution.

## What the areas hint got wrong

1. **The enum files.** It lists `vidbyte/lib/enums/skills.py` and `vidbyte/lib/enums/__init__.py`
   as touched. `SkillSourceType` and `SkillUnavailableReason` already exist and are already
   root-exported. These files change only if the spec adds an enum or a member.
2. **Jev settings.** It lists `vidbyte/agents/jev/settings.py` among the touched files. JevAgent
   keeps its behavior, so this file is a reference, not an edit target. It holds the only
   validation of the entry tuple (types, duplicate names, string-to-`SkillDocument`).
3. **The generator.** It pairs `scripts/generate-sdk-public-api.py` with the contract. The
   generator is run, not edited.
4. **Lint rules.** It says "lint rules that guard root exports / the contract / layering (e.g.
   C016, A009)". A009 is the README size cap, not a root-export guard. The root-export rule is
   S015 (root imports must be in `__all__`), and the layering rule is A006. No file under `lint/`
   should change.
5. **"Any fetcher/parser modules".** These are concretely `fetch.py`, `markdown.py` and
   `resolver.py`, plus the six resolver modules and `vendor.py`. None needs to change for a public
   door unless detail wording or limits change.
6. **Files it missed.**
   - The four intermediate export files: `vidbyte/agents/__init__.py`,
     `vidbyte/agents/jev/__init__.py`, `vidbyte/lib/__init__.py` and
     `vidbyte/lib/dataclasses/__init__.py`.
   - `vidbyte/lib/constants/skills.py`, which holds the caps that consumer item 4 asks about.
   - `vidbyte/agents/README.md:297`.
   - `contracts/README.md`, which holds the procedure.
   - The skills test pack.
7. **Root README.md and llms.txt.** Only their version literal is involved. Neither documents
   skill sources or `SkillLoader` today.

## What the workspace-facts file got wrong (`vidbyte-gates.md`)

1. **Semgrep.** It says "CI runs the same `run_ci.py`; semgrep is part of it". `scripts/run_ci.py`
   does not run semgrep. Semgrep runs in `.github/workflows/static-policy.yml:23-30`, so a local
   gate run does not cover it.
2. **The source-stage command.** It gives `python scripts/run_ci.py --stage source` without
   `PYTHONPATH=$(pwd)`. The field guide's `local-ci-verification.md` requires `PYTHONPATH` in a
   worktree, because the editable install points at the canonical checkout.
   - Observed here: the working directory wins for `python -c` run from the worktree root.
   - Its "`pip install -e` once" step, run from a worktree, would repoint the shared editable
     install away from the user's checkout. Which checkout it points to now is unverified.
3. **Placement.** Its placement line matches AGENTS.md: every public enum is exported from
   `vidbyte/lib/enums/__init__.py`. Nothing else in it was found wrong.
