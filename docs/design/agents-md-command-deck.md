# Design Doc: AGENTS.md Development Command Deck

**Status:** Draft
**Author:** opencode (design-doc-no-tests workflow)
**Created:** 2026-08-17
**Last Updated:** 2026-08-25

---

## 1. Overview

Add a **Command Deck** section to the root `AGENTS.md`: the verified commands a developer or coding agent needs to install development dependencies, run repository gates, debug failures, test focused behavior, and enforce static policy. Each entry is the literal command, a 1-2 sentence description, and the command's key parameters. The deck is a development reference, not a guide to consuming the published package or operating the SDK CLI.

## 2. Goals & Non-Goals

### Goals
- One top-level `## Command Deck` section appended to `AGENTS.md`, after the File Index.
- Subsections: Development environment, Verification gates, Tests, and Static analysis.
- Every entry: actual command + 1-2 sentence description + key params.
- Every command verified against `CONTRIBUTING.md`, `pyproject.toml`, `scripts/run_ci.py`, `scripts/check_context_write_paths.py`, and the CI workflows.

### Non-Goals
- No changes to any file other than `AGENTS.md` and this design doc.
- No changes to the Map (File Index) content or conventions.
- No new scripts, CI changes, or package CLI documentation.

## 3. Background & Context

`AGENTS.md` is currently only on the open PR branch `feat/agents-md-repository-map` (PR #334); this branch stacks on it. The SDK's development loop is Python-only: editable installation with the `[dev]` extra, `scripts/run_ci.py` as the canonical gate with `--stage source|package` diagnostics, pytest under `tests/`, an AST context write-path checker, and a Semgrep policy enforced by `static-policy.yml`.

## 4. Requirements

### Functional Requirements
1. `AGENTS.md` gains exactly one new top-level section, `## Command Deck`, placed after the File Index.
2. The section opens with a one-paragraph note stating it is a development/debugging reference deliberately outside the Map's topology contract.
3. The environment subsection leads with `python -m pip install -e ".[dev]"` and the pinned Semgrep installation needed for local policy checks.
4. The gates subsection covers `python scripts/run_ci.py`, source/package diagnostics, and the worktree `PYTHONPATH` requirement.
5. The tests subsection covers the full pytest suite, module and keyword slices, the multi-agent package, and targeted feature scripts.
6. The static-analysis subsection covers `compileall`, the context write-path checker, and the two exact Semgrep invocations from `static-policy.yml`.

### Non-Functional Requirements
- Scannable entries: command line, at most two sentences, one params line.
- Correct GitHub Markdown rendering without encoding hazards.
- The Map block above the deck remains byte-for-byte unchanged.

## 5. High-Level Design

Appended content, not Map content; the Map blockquote is untouched and the deck carries its own scope note. Entries are ordered by the workflow a developer actually follows: prepare the environment, run a gate, narrow a failing test, then inspect static-analysis findings.

```
AGENTS.md
  ...existing Map...
  ## Command Deck        <- new
    ### Development environment (editable install + Semgrep)
    ### Verification gates (full + diagnostic stages)
    ### Tests (pytest + targeted scripts)
    ### Static analysis (compileall + AST checker + Semgrep)
```

## 6. Detailed Design

### 6.x AGENTS.md Command Deck section

**File(s):** `AGENTS.md`
**Type:** Modified (append one section)

#### Content decisions
- Environment: editable development install and Semgrep 1.170.1, matching `pyproject.toml` and `static-policy.yml`.
- Gates: `run_ci.py` remains the canonical full gate; source/package stages are explicitly labeled diagnostic-only.
- Worktrees: the source stage documents the `PYTHONPATH` override from the shared field guide, while the package stage must run without that override.
- Tests: full pytest discovery, quiet mode, module selection, keyword filtering, the `tests/multi_agent/` package, and targeted `scripts/test-*.py` checks.
- Static analysis: compileall, the repository's context write-path checker, and both exact Semgrep commands from CI.

#### Edge cases
- Python version floor (>=3.11) is stated once in the deck note so an agent does not run the suite on an unsupported interpreter.
- A worktree source run must point `PYTHONPATH` at the worktree; a package run must clear it so the wheel smoke test cannot resolve the canonical checkout.

## 7. Data Model Changes

N/A - documentation-only change.

## 8. API Changes

N/A - documentation-only change.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agents-md-command-deck.md` | This design doc |
| MODIFY | `AGENTS.md` | Append the development Command Deck section |

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| semgrep | pinned 1.170.1 in CI | Local static-policy commands | Low: mirrors CI exactly |

## 11. Rollout & Deployment

Docs-only. This PR stacks on `feat/agents-md-repository-map` (PR #334) and retargets to `main` automatically once that PR merges. The deck documents development verification, not package publication or SDK CLI usage.

## 12. Open Questions

- [ ] None blocking.

## 13. Alternatives Considered

### Alternative 1: Distribute commands into Map folder entries
- What: Put run commands next to `scripts/` and `tests/` entries.
- Why rejected: The Map is topology-only by its own contract; commands would be scattered.

### Alternative 2: A separate COMMANDS.md
- What: Keep AGENTS.md pure.
- Why rejected: Agents would need a second lookup; the user explicitly wants the deck inside AGENTS.md.

### Alternative 3: Document package consumption and the SDK CLI
- What: Focus the deck on building distributions, installing wheels, and using `vidbyte-sdk skills`.
- Why rejected: Those are package-consumer or release workflows; the review clarified that this deck should answer how to develop and debug the repository.

END OF DESIGN DOC TEMPLATE
