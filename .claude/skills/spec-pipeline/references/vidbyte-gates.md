# Vidbyte workspace: repositories, gates, and workspace conventions

Known facts about the user's workspace, true as of 2026-10-09. The S0 scout re-verifies these against `AGENTS.md` for every run and records what binds the change in `docs/spec/<slug>/context/code-map.md` §1. `AGENTS.md` wins on any conflict with this file.

## Workspace layout

`<vidbyte-repos-root>` is the directory containing `vidbyte`, `vidbyte-sdk`, `vidbyte-cli`, `vidbyte-skills`, and `vidbyte-harnesses` (currently `C:/Users/422mi/vidbyte-repos`). It is not itself a git repository. Each repo is its own checkout.

- **Project field guide:** `<vidbyte-repos-root>/field-guide/<repo>/init.md` indexes topic files distilled from accepted PR feedback (trigger, preferred action, reason, quick check, links to the PR comments). A worktree uses its canonical source repository's folder. Read the index first, then only the linked files whose one-line descriptions apply. Live code and the user's instructions win on conflict. Missing index = empty. Do not load another repo's guide.
- **Worktrees:** created at `<vidbyte-repos-root>/worktrees/<repo>-<slug>` from `origin/main`, branch `feat/<slug>` unless `AGENTS.md` defines a convention. Storage discipline: do not duplicate `node_modules/`, `.next/`, `.venv/`, build output, or tool caches when a shared cache or environment works; reuse npm's cache; reuse compatible Python environments. The field guide for `vidbyte-sdk` has `local-ci-verification.md` on running the CI gate from a worktree — read it before the first gate run there.
- **`docs/` is opaque** in `vidbyte` and `vidbyte-sdk`: their `AGENTS.md` forbid grepping, globbing, or reading under `docs/` unless a human names a specific document. The orchestrator naming `docs/spec/<slug>/...` files in a briefing is that exception. Subagents read exactly the named files and never browse `docs/`.
- **Specs and design docs** are committed with the change (`docs/spec/<slug>/` for this pipeline; `vidbyte-cli` also keeps one design doc per feature under `docs/design/`).

## Gates by repository

| Repository | Shape | Lint / validation loop | Full local gate | Remote PR checks |
|---|---|---|---|---|
| `vidbyte/` | FastAPI `backend/` + Next.js `next-app/`, MongoDB Atlas | `python lint/run.py` (focus: `--surface next`, `--surface backend`, `--rule <ID>`; `--all` for every finding) | `python lint/run.py`, `python -m pytest backend/tests/<area>` for touched areas, and `cd next-app && npm run lint && npm run build` | **Never build or lint the frontend.** The local `npm run lint` + `npm run build` is the only real frontend gate. |
| `vidbyte-sdk/` | Python package, layered (`vidbyte/lib/` bottom) | `python lint/run.py` (focus: `--rule <ID>`; `--all`, `--format json`) | `python -m pip install -e ".[dev]"` once, then `python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py` | CI runs the same `run_ci.py`; semgrep is part of it — see the field guide's `local-ci-verification.md` |
| `vidbyte-cli/` | Python src-layout CLI | `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy src`, `python lint/run.py` | `python scripts/run_ci.py` (one gate, no stage selector: lint, format, strict typing, compileall, targeted diagnostics, build, twine, clean-wheel smoke) | `ci.yml` is the OS/Python matrix only (Ubuntu 3.11/3.14, Windows 3.11, macOS 3.11); every step lives in `run_ci.py` |
| `vidbyte-skills/` | Skill library | `npm run validate` | `npm test` | — |
| `vidbyte-harnesses/` | — | per `AGENTS.md` | per `AGENTS.md` | — |

## The custom lint suites (`lint/run.py`)

- Exit non-zero when a rule **REGRESSED** (more findings than `lint/baseline.json` allows) or **ERRORED**. A rule that raised is failing, never passing.
- Every violation prints a full diagnostic: what happened, why it is blocked here, runnable fix code, compliant examples in the repo, the shortcuts that will not work, and the re-verify command. Read the whole diagnostic before changing anything.
- Final line must read `AGENT-LINT: PASS …` before handing off.
- **Never** raise a number in `lint/baseline.json`, add a suppression (they do nothing: backend rules read the AST, Next.js rules strip comments), weaken a rule, or delete a check. A genuine false positive stays failing and is called out in the PR description and the report.
- A rule reporting **IMPROVED** should have its ratchet tightened only after a genuine source improvement: `python lint/run.py --rule <ID> --update-baseline`.
- `lint/` is a root directory; a sparse checkout must include it: `git sparse-checkout set backend next-app docs lint`.
- If `lint/run.py` is absent from the checkout, do not claim the custom lint passed and do not substitute another check; report a repository-state blocker.

## Repository-specific rules that bite fresh agents

- **`vidbyte-sdk` placement:** every new dataclass in `vidbyte/lib/dataclasses/<domain>.py`; every new enum in `vidbyte/lib/enums/<domain>.py` and exported from its `__init__.py`; `vidbyte/lib/` never imports a higher layer; call chains one level deep; main functions narrated in plain English; validated frozen dataclasses for core inputs/outputs; files well under 1,000 lines. `REPO_MAP.md` says where each kind of code lives. Full gate before calling anything complete.
- **`vidbyte-cli` contracts:** results are the only thing on stdout; JSON/JSONL carries `schema_version` and `kind`; the reusable entry function returns an int and only `__main__.py` and the console wrapper exit; commands orchestrate and `lib/` does the work; every non-trivial change lands a design doc under `docs/design/`; `--help` depth is lint-enforced.
- **`vidbyte` boundary:** the browser talks to Next.js Server Actions, which call FastAPI through `callBackendAction`; the browser never reaches the backend directly. Backend tests are organized by feature with per-area pytest configs. Feature-scoped test packs are the established pattern.
