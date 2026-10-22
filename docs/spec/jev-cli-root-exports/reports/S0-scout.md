# S0 scout report: jev-cli-root-exports (PR R1)

- **Stage:** S0 scout
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-cli-root-exports`
- **HEAD:** `b7350ed6423642c9c178361eef87f3d9cda5589b` (= origin/main). The only untracked item is `docs/spec/jev-cli-root-exports/`, which the orchestrator created. After my reads and one pytest run, `git status` shows only that folder.
- **Produced:** `docs/spec/jev-cli-root-exports/context/code-map.md`. It has four `## ` sections and an H1 title. Sub-sections use `###`.
- **Commits:** none. **Installs:** none. **Gate runs:** none (see "Commands run" for the read-only checks I made).

## Planned file list, made before reading code

| Role | Path | Basis |
|---|---|---|
| Edited | `vidbyte/__init__.py` | the request; it binds root `__all__` |
| Generated | `contracts/sdk-public-api.json` | the request; the generator writes it |
| Generator / derivation | `scripts/generate-sdk-public-api.py`, `lint/core/public_api_contract.py` | the generator's imports |
| Lint pinning the surface | `lint/rules/c016_*`, `lint/rules/s015_*` (found through the `__all__` comments in the root header) | `git grep` |
| Definitions | `vidbyte/agents/settings/loop.py`, `vidbyte/lib/dataclasses/security.py`, `vidbyte/lib/enums/text_model.py`, `vidbyte/lib/enums/jev.py` | the request and the briefing |
| Re-export paths | `vidbyte/agents/__init__.py`, `vidbyte/agents/settings/__init__.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/tools/__init__.py`, `vidbyte/tools/security/{__init__,permissions}.py`, `vidbyte/lib/dataclasses/__init__.py` (the relevant lines), `vidbyte/lib/config/__init__.py` | `git grep` for the four names in `__init__.py` files |
| Consumer | `vidbyte/agents/jev/settings.py` | it holds the fields the CLI must build |
| Tests pinning the root surface | `tests/features/harness_threads/test_harness_threads_surface.py`, `tests/features/root_native_thread_exports/*`, `tests/features/public_skill_loader/*` (contract, release, docs, FEATURE.md) | `git grep` for `vidbyte.__all__` and `sdk-public-api` |
| Docs that might list exports | `README.md`, `llms.txt`, `REPO_MAP.md`, `artifacts/file_index.md`, `contracts/README.md` | the briefing hint |
| Exemplars | commits `82b46c85` (#1179) and `64e2bd67` (#1099) | `git log -- vidbyte/__init__.py` |

## Files read in full

AGENTS.md; request.md; vidbyte-gates.md; field guide `init.md`, `local-ci-verification.md`, `review-scope.md`; `vidbyte/__init__.py` (1,467 lines); `vidbyte/agents/settings/loop.py`; `vidbyte/agents/settings/__init__.py`; `vidbyte/agents/__init__.py`; `vidbyte/agents/jev/__init__.py`; `vidbyte/agents/jev/settings.py`; `vidbyte/lib/dataclasses/security.py`; `vidbyte/lib/enums/text_model.py`; `vidbyte/lib/enums/jev.py`; `vidbyte/lib/enums/__init__.py`; `vidbyte/tools/__init__.py`; `vidbyte/tools/security/__init__.py`; `vidbyte/tools/security/permissions.py`; `scripts/generate-sdk-public-api.py`; `lint/core/public_api_contract.py`; `lint/rules/c016_public_api_contract_current.py`; `lint/rules/s015_public_export_integrity.py`; `lint/rules/s020_readme_file_index_parity.py`; `lint/rules/a001_agent_readable_file_headers.py`; `contracts/README.md`; `scripts/run_ci.py`; `tests/features/harness_threads/test_harness_threads_surface.py`; `tests/features/root_native_thread_exports/{FEATURE.md,README.md,test_root_native_thread_exports_contract.py}`; `tests/features/public_skill_loader/{FEATURE.md,test_public_skill_loader_contract.py,test_public_skill_loader_release.py,test_public_skill_loader_docs.py}`; `.github/pull_request_template.md`.

## Files read in part (relevant lines only)

- `contracts/sdk-public-api.json`: header, tail, and the sort positions.
- `lint/rules/s051_*` and `lint/rules/s009_*`: headers.
- `lint/ruff.toml`; `lint/mypy.ini` (head); `lint/baseline.json` (the relevant rules); `lint/core/discovery.py` (catalogue scopes); `lint/core/report.py:58`; `lint/README.md` (commands).
- `CONTRIBUTING.md:28-90`; `pyproject.toml` (version and pytest).
- `.github/workflows/*.yml` (the `run:` lines).
- `vidbyte/lib/dataclasses/__init__.py:195-205, 405-420`; `vidbyte/lib/config/__init__.py:1-40`; `vidbyte/lib/dataclasses/tools.py:47-59`; `vidbyte/lib/dataclasses/jev.py:660-674, 3808-3816`.
- `REPO_MAP.md` (headings, `:1-8, 59-74, 105-110, 193-200, 355-360, 385-420`); `vidbyte/agents/README.md` (headings, grep hits).
- The `README.md` and `llms.txt` lines that mention the names, and the `skills/**` hits.
- `tests/features/agent_output_connectors/test_output_connectors_contract.py:60-82` and `test_output_connectors_followup_contract.py:170-187`; `tests/features/jev_skills_preload/test_skill_sources_contract.py:1-67`; `tests/features/infinite_memory_agent/test_infinite_memory_contract.py:155-168`; `tests/features/codex_host/test_codex_host_packaging.py` (the `__all__` lines).
- The diffs of the exemplar commits for the root, contract and docs files.

Not read: the behavior tests in `public_skill_loader` (conftest, acceptance, boundary, both_doors, security). They concern SkillLoader behavior and are no model for an export-only change.

## Commands run that went beyond reading files (all read-only)

- `PYTHONPATH=$(pwd) py -3.11 -c ...`: imported `vidbyte` from the worktree. This checked that the four names are absent from the root, that each one is the same object across its export paths, that the contract equals `sorted(__all__)` (664 names), which modules `import vidbyte` loads, and that 11 native names are missing from the root.
- `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 py -3.11 -m pytest -q -p no:cacheprovider tests/features/root_native_thread_exports`: the result was `3 failed, 4 passed` on pristine main. This was one pack used as evidence, not a gate run, and it left no tracked change.
- `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, with no `--fix`: `vidbyte/__init__.py` has no I001 finding today.
- `git cat-file`, `git merge-base --is-ancestor`, `git show --stat`/diff on the exemplars, and `git ls-files` searches.

## What the areas hint or the gates reference got wrong or left incomplete

- **The hint listed `vidbyte/lib/enums/__init__.py` as possibly touched.** Both enums are already exported there, so it needs no change.
- **The hint listed `vidbyte/agents/__init__.py` and `vidbyte/agents/jev/__init__.py`.** The first already re-exports `AgentLoopSettings`. The second re-exports none of the four. Neither needs a change.
- **The hint suggested README.md, llms.txt, REPO_MAP.md and artifacts/file_index.md "if they list root exports".** None of them does. The real doc obligation is the root header docstring. One line of it (`:25`, "- Error exports") is pinned by a test.
- **The hint missed several obligations:**
  - S015, in addition to C016.
  - The two-commit sequence that the generator enforces.
  - A001 header fields on any new test file.
  - S020 when a pack README has a File Index.
  - The fact that editing `vidbyte/tools/**` headers trips a branch-scoped harness test.
- **The briefing named 82b46c85 as the likely exemplar.** It is valid, but 64e2bd67 (#1099) is closer: the same pipeline, plain eager root exports of lib and agents classes, and a test on the header bullet.
- **The briefing said `ToolPermission` is "already a root export".** That is right. It enters through `from vidbyte.tools import ...`, and its definition is an enum inside `vidbyte/lib/dataclasses/tools.py:47`, which predates the placement rules.
- **The gates reference (dated 2026-10-09) contradicts the field guide in two places.** It gives the lint pass line as "AGENT-LINT: PASS", but the SDK prints "SDK-LINT: PASS". Its source-then-full gate sequence also lacks the `PYTHONPATH=$(pwd)`-for-source-only rule from the field guide. AGENTS.md states only `python scripts/run_ci.py`.
- **New, and in neither the gates reference nor the memory:** pristine main b7350ed6 has 3 red tests in `tests/features/root_native_thread_exports`, because #1183 added 11 native browser names without root exports.

## Process disclosures

- To find a release note, I ran `git ls-files docs/design | grep -i release`. That lists filenames under `docs/`, which comes close to AGENTS.md's "do not glob under `docs/`". I read no file content under `docs/` except `request.md`. `docs/design/release-0-4-0.md` was already visible in `git show --stat 64e2bd67`.
