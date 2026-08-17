# Design Doc: AGENTS.md Command Deck

**Status:** Draft
**Author:** opencode (design-doc-no-tests workflow)
**Created:** 2026-08-17
**Last Updated:** 2026-08-17

---

## 1. Overview

Add a **Command Deck** section to the root `AGENTS.md`: the verified commands an agent needs to install, verify, test, package, and use this SDK, so no session is spent guessing invocations. Each entry is the literal command, a 1-2 sentence description, and the command's key parameters. The deck covers the repository gates, the pytest suite, the Semgrep static policy, Python packaging, and the `vidbyte-sdk` console command.

## 2. Goals & Non-Goals

### Goals
- One top-level `## Command Deck` section appended to `AGENTS.md`, after the File Index.
- Subsections: Repository gates, Tests, Static policy, Packaging, and the SDK CLI.
- Every entry: actual command + 1-2 sentence description + key params.
- Every command verified against `pyproject.toml`, `scripts/run_ci.py`, `.github/workflows/static-policy.yml`, and `vidbyte/cli/`.

### Non-Goals
- No changes to any file other than `AGENTS.md`.
- No changes to the Map (File Index) content or conventions.
- No new scripts or CI changes.

## 3. Background & Context

`AGENTS.md` is currently only on the open PR branch `feat/agents-md-repository-map` (PR #334); this branch stacks on it. The SDK's toolchain is Python-only: editable install with the `[dev]` extra, `scripts/run_ci.py` as the canonical gate with `--stage source|package` diagnostics, pytest under `tests/`, a Semgrep typed-mapping policy enforced by `static-policy.yml`, `python -m build` + `twine check` packaging, and the `vidbyte-sdk` console script (`vidbyte.cli:main`) exposing `skills list|show|install`.

## 4. Requirements

### Functional Requirements
1. `AGENTS.md` gains exactly one new top-level section, `## Command Deck`, placed after the File Index.
2. The section opens with a one-paragraph note stating it is a run-command reference, deliberately outside the Map's topology contract.
3. The gates subsection leads with `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py`, including `--stage` values and their diagnostic-only status.
4. The static-policy subsection reproduces the two exact Semgrep invocations from `static-policy.yml`.
5. The packaging subsection covers `python -m build`, `python -m twine check dist/*`, and a clean-install smoke check.
6. The SDK CLI subsection covers `vidbyte-sdk skills list|show|install` with `--dest` and `--force`.

### Non-Functional Requirements
- Scannable entries: command line, at most two sentences, one params line.
- Correct GitHub Markdown rendering; no encoding hazards.

## 5. High-Level Design

Appended content, not Map content; the Map blockquote is untouched and the deck carries its own scope note. Entries are ordered by the workflow an agent actually follows: install, gate, test, diagnose, package, then use the shipped CLI.

```
AGENTS.md
  ...existing Map...
  ## Command Deck        <- new
    ### Repository gates (install + run_ci)
    ### Tests (pytest)
    ### Static policy (semgrep)
    ### Packaging (build / twine / install smoke)
    ### SDK CLI (vidbyte-sdk skills)
```

## 6. Detailed Design

### 6.x AGENTS.md Command Deck section

**File(s):** `AGENTS.md`
**Type:** Modified (append one section)

#### Content decisions
- Gates: `run_ci.py` stages are labeled diagnostic-only, matching the CI philosophy recorded in the repo docs.
- Tests: whole-suite quiet run, single-module run, `-k` expression filtering, and the `tests/multi_agent/` package.
- Static policy: `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` and `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, verbatim from CI.
- Packaging: `python -m build`, `python -m twine check dist/*`, and `python -m pip install --force-reinstall dist/*.whl` as the clean-install smoke.
- CLI: `vidbyte-sdk skills list`, `skills show <key>`, `skills install <key> --dest <dir> [--force]`, verified from `vidbyte/cli/skills_parser.py`.

#### Edge cases
- Python version floor (>=3.11) is stated once in the deck note so an agent does not run the suite on an unsupported interpreter.

## 7. Data Model Changes

N/A - documentation-only change.

## 8. API Changes

N/A - documentation-only change.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agents-md-command-deck.md` | This design doc |
| MODIFY | `AGENTS.md` | Append the Command Deck section |

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| semgrep | pinned 1.170.1 in CI | Static-policy commands | Low: mirrors CI exactly |

## 11. Rollout & Deployment

Docs-only. This PR stacks on `feat/agents-md-repository-map` (PR #334) and retargets to `main` automatically once that PR merges.

## 12. Open Questions

- [ ] None blocking.

## 13. Alternatives Considered

### Alternative 1: Distribute commands into Map folder entries
- What: Put run commands next to `scripts/` and `tests/` entries.
- Why rejected: The Map is topology-only by its own contract; commands would be scattered.

### Alternative 2: A separate COMMANDS.md
- What: Keep AGENTS.md pure.
- Why rejected: Agents would need a second lookup; the user explicitly wants the deck inside AGENTS.md.

END OF DESIGN DOC TEMPLATE
