# Design Doc: PR #253 CLI-Only Cleanup

**Status:** Implemented
**Author:** Claude
**Created:** 2026-07-08
**Last Updated:** 2026-07-08

---

## 1. Overview

PR [#253](https://github.com/cerredz/Vidbyte-SDK/pull/253) (`feat/vidbyte-cli`, title "feat: Minimal Vidbyte CLI") was intended to ship only the minimal unified `vidbyte-sdk` CLI (`vidbyte-sdk skills list|show|install`). Because it was branched before the skills registry landed, the branch also contains the full paradigm skills + registry implementation. That registry is now on `main` via [#256](https://github.com/cerredz/Vidbyte-SDK/pull/256) (resolver for closed [#251](https://github.com/cerredz/Vidbyte-SDK/pull/251)). This change rewrites the PR #253 branch on top of current `main` so its diff is **CLI-only**, reusing the existing CLI implementation with small adaptations to the merged registry API.

---

## 2. Goals & Non-Goals

### Goals
- Make PR #253's diff against `main` contain only the minimal CLI surface and its docs.
- Preserve the intentional CLI behavior already implemented on `feat/vidbyte-cli` (stdlib argparse, `vidbyte-sdk skills list|show|install`, short-key resolution, exit codes, lazy catalog import).
- Base the cleaned branch on current `origin/main` so the PR is mergeable without skills-registry conflicts.
- Adapt CLI code/tests to the **merged** skills enum shape from #256 (grouped `ContextMinimalFanoutSkill` + `Skill` type alias), not the older flat `Skill` enum that lived only on the contaminated branch.
- Supersede `python -m vidbyte.skills` with the unified CLI as specified by the original CLI design (delete `vidbyte/skills/__main__.py` and retarget its tests/docs).
- Update PR #253 in place (same branch / same PR number) via force-push after rewrite.

### Non-Goals
- Re-implementing or re-reviewing the skills registry, skill assets, or paradigm folders (already on `main`).
- Adding new CLI subcommands beyond `skills`.
- Adding click/typer/rich or any new runtime dependency.
- Expanding harness-aware install paths (`--harness claude`); keep explicit `--dest`.
- Changing packaging for skill assets (already handled on `main` via package-data).
- Closing PR #253 and opening a replacement PR unless force-push is rejected by policy.
- Writing new verification scripts beyond the existing unittest module already on the PR branch (this workflow is design-doc-no-tests; keep the existing CLI unit tests that ship with the feature).

---

## 3. Background & Context

### Why now
PR #253 is open, marked conflicting with `main`, and its file list mixes two features:
1. **Skills registry** (should not be in this PR) — commits `548364b`, `3bb0d40`, `de2d752`
2. **Minimal CLI** (intended scope) — commits `bbdca7f`, `a250dad`, `605a78f`

### Current state
| Surface | On `main`? | On `feat/vidbyte-cli`? |
|---------|------------|------------------------|
| `vidbyte/skills/*` catalog + assets | Yes (#256) | Yes (older API shape) |
| `vidbyte/lib/enums/skills.py` grouped enums | Yes (#256) | Flat `Skill` enum only |
| `vidbyte/skills/__main__.py` module CLI | Yes (#256) | Deleted by CLI commit |
| `vidbyte/cli/*` unified CLI | No | Yes |
| `[project.scripts] vidbyte-sdk = ...` | No | Yes |

### Root cause
The CLI branch was cut (or stacked) with the unmerged skills registry work included. Three-dot history still shows registry files as "added" relative to the old merge-base, and two-dot tree diff against current `main` is polluted with unrelated behind-main drift.

### Constraints
- CLI depends on registry APIs that **now exist on main**: `Skills`, `SkillRecord`, `Skill` / `ContextMinimalFanoutSkill`, `ConfigurationError`.
- Main's enum API differs from the PR branch; a naive cherry-pick of CLI commits will fail tests that reference `Skill.CONTEXT_MINIMAL_FANOUT_*`.
- Force-pushing `feat/vidbyte-cli` updates PR #253; reviewers keep comment history on the same PR.

---

## 4. Requirements

### Functional Requirements
1. PR #253 (after rewrite) must introduce the unified console entry point `vidbyte-sdk = "vidbyte.cli:main"` in `pyproject.toml` without removing `vidbyte-mcp-server`.
2. Users can run:
   - `vidbyte-sdk --version`
   - `vidbyte-sdk skills list`
   - `vidbyte-sdk skills show <key>`
   - `vidbyte-sdk skills install <key> --dest <dir> [--force]`
3. Keys accept full enum values (e.g. `context_minimal_fanout.decompose_fanout`) and unambiguous short forms (`decompose_fanout` / `decompose-fanout`).
4. `list` prints stable `key - description` lines from `Skills().keys()` / `descriptions()`.
5. `show` prints SKILL.md text for the resolved skill.
6. `install` materializes via `Skills().materialize`, refuses non-empty existing skill folders unless `--force`, and prints the installed path.
7. Exit codes: `0` success; `2` usage/unknown-key; `1` expected catalog/OS failures (no traceback for `ConfigurationError` / `OSError`).
8. Help paths (`vidbyte-sdk --help`, `vidbyte-sdk skills --help`) must not instantiate the Skills catalog.
9. `python -m vidbyte.cli` works via `vidbyte/cli/__main__.py`.
10. `vidbyte/skills/__main__.py` is removed; skills tests no longer import that module CLI; skills README points at `vidbyte-sdk skills ...`.
11. The PR diff vs `main` must **not** re-introduce or rewrite registry/assets/design-doc content for paradigm skills beyond CLI-required doc touch-ups.
12. Existing CLI unit tests (`tests/test_cli_interface.py`) ship with the PR and pass against main's Skills API.

### Non-Functional Requirements
- **Dependencies:** stdlib only for CLI code; no new package dependencies.
- **Compatibility:** Windows-safe paths via `pathlib`; no ANSI-required output.
- **Style:** Context Protocol Headers on new modules; class-first handlers; one-line signatures with 1–2 line method comments (match existing CLI modules on the branch).
- **Reviewability:** Small, intentional file set; clean history on top of current main (no stacked registry commits).
- **Reliability:** Lazy import of Skills so help works even if catalog load would fail.
- **Observability:** Errors go to stderr as single-line `error: ...` messages for expected failures.

---

## 5. High-Level Design

Rebuild the branch instead of merging the contaminated history.

```
origin/main (has skills registry via #256)
        |
        v
feat/vidbyte-cli (rewritten)
        |
        +-- docs/design/vidbyte-cli.md          (promote / keep CLI design)
        +-- docs/design/pr-253-cli-only.md      (this cleanup design)
        +-- vidbyte/cli/*                       (port from old branch)
        +-- tests/test_cli_interface.py         (adapt enum member names)
        +-- pyproject.toml                      (+ vidbyte entry point)
        +-- README.md / llms.txt                (CLI section only)
        +-- vidbyte/skills/README.md            (point to vidbyte CLI)
        +-- DELETE vidbyte/skills/__main__.py
        +-- MODIFY tests/test_skills_interface.py (drop module-CLI test)
```

**Approach:** Create an isolated worktree from `origin/main`, copy/port only CLI-related files from `origin/feat/vidbyte-cli`, adapt to main's Skill enum, commit cleanly, force-push to `origin/feat/vidbyte-cli` so PR #253 updates in place.

**Why rewrite instead of rebase-drop:** The three early commits recreate files that already exist on main with a different enum shape. Rebase conflict resolution would thrash registry files and risk regressing #256. A greenfield branch from main plus intentional file ports is safer and produces a reviewable CLI-only diff.

```
[User shell]
    |  vidbyte skills install decompose-fanout --dest .claude/skills
    v
[vidbyte.cli:main]  -- argparse root, version, exit-code mapping
    |
    v
[vidbyte.cli.skills]  -- key resolve, list/show/install handlers
    |
    v
[vidbyte.skills.Skills]  -- already on main; materialize / text / keys
```

---

## 6. Detailed Design

### 6.1 Branch rewrite / worktree

**File(s):** N/A (git operations)
**Type:** Process

#### What it does
Creates a clean implementation branch based on current `main` and replaces the remote `feat/vidbyte-cli` history used by PR #253.

#### Interface / API
```bash
git fetch origin main feat/vidbyte-cli
git worktree add ../worktrees/feat-vidbyte-cli -b feat/vidbyte-cli-clean origin/main
# implement CLI-only changes inside worktree
git push --force-with-lease origin HEAD:feat/vidbyte-cli
```

#### Logic / Algorithm
1. Fetch latest `origin/main` and `origin/feat/vidbyte-cli`.
2. Create worktree from `origin/main` (not from the contaminated branch tip).
3. Commit this design doc first.
4. Port CLI implementation files from `origin/feat/vidbyte-cli` with enum adaptations.
5. Apply supersession of `vidbyte.skills` module CLI.
6. Apply docs (CLI-only sections).
7. Run `python -m unittest tests.test_cli_interface tests.test_skills_interface` (or equivalent) as a local sanity check before push.
8. Force-push with lease to `feat/vidbyte-cli` so PR #253 updates.
9. Confirm `gh pr diff 253 --name-only` lists only CLI-scope files.

#### Edge Cases & Error Handling
- If force-with-lease fails (remote advanced), stop and reconcile rather than blind force.
- Do not delete the old branch object until the new tip is pushed successfully.

---

### 6.2 Unified CLI package (`vidbyte/cli`)

**File(s):**
- `vidbyte/cli/__init__.py` (New — port)
- `vidbyte/cli/__main__.py` (New — port)
- `vidbyte/cli/skills.py` (New — port + adapt)
- `vidbyte/cli/README.md` (New — port)

**Type:** New files (relative to main)

#### What it does
Provides the root `vidbyte-sdk` command and the `skills` subcommand group as a thin adapter over `vidbyte.skills.Skills`.

#### Interface / API
```python
# vidbyte/cli/__init__.py
def main(argv: Sequence[str] | None = None) -> int: ...

class VidbyteCli:
    def main(self, argv: Sequence[str] | None = None) -> int: ...

# vidbyte/cli/skills.py
def register(subparsers: argparse._SubParsersAction[Any]) -> None: ...

class SkillsCommandGroup:
    def register(self, subparsers: argparse._SubParsersAction[Any]) -> None: ...
    def list_skills(self, args: argparse.Namespace) -> int: ...
    def show_skill(self, args: argparse.Namespace) -> int: ...
    def install_skill(self, args: argparse.Namespace) -> int: ...

class SkillKeyResolver:
    def resolve(self, key_text: str, valid_keys: tuple[Skill, ...]) -> Skill: ...
```

#### Logic / Algorithm
1. Port modules from `origin/feat/vidbyte-cli` essentially as-is.
2. Keep class-first structure: `VidbyteCli`, `ReturningArgumentParser`, `VersionResolver`, `SkillsCommandGroup`, `SkillKeyResolver`.
3. **Enum adaptation (required):**
   - Continue importing `Skill` from `vidbyte.lib.enums.skills` (type alias to `ContextMinimalFanoutSkill` on main).
   - Prefer `skill_from_value(key_text)` (or equivalent multi-enum-safe resolution) for full-key direct match so future paradigm enums do not break construction.
   - Short-form matching stays leaf-name based on `key.value.rsplit(".", 1)[-1]`.
4. Keep lazy `from vidbyte.skills import Skills` inside catalog access for help-path laziness.
5. Keep single-line unknown-key stderr format from refinement commit `605a78f`.
6. Keep `--force` overwrite guard using `record.folder` + `ConfigurationError`.

#### Edge Cases & Error Handling
- Unknown/ambiguous key → stderr one-liner + exit 2 via `CliUsageError`.
- `ConfigurationError` / `OSError` → `error: ...` on stderr + exit 1.
- Empty existing skill folder → allow install without `--force`.
- Non-empty existing skill folder without `--force` → refuse with exit 1.

---

### 6.3 Entry point wiring

**File(s):** `pyproject.toml`
**Type:** Modified

#### What it does
Registers the console script.

#### Interface / API
```toml
[project.scripts]
vidbyte-sdk = "vidbyte.cli:main"
vidbyte-mcp-server = "vidbyte.mcp_server.__main__:main"
```

#### Logic / Algorithm
1. Add only the `vidbyte` line.
2. Do not touch package-data for skills (already on main).
3. Do not alter dependencies.

#### Edge Cases & Error Handling
- Ensure merge does not duplicate the line if another branch also adds it (unlikely; main lacks it).

---

### 6.4 CLI unit tests

**File(s):** `tests/test_cli_interface.py`
**Type:** New — port + adapt

#### What it does
In-process coverage of version, help laziness, list/show/install, key forms, and error shapes.

#### Interface / API
```python
class VidbyteCliInterfaceTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]: ...
```

#### Logic / Algorithm
1. Port tests from the PR branch.
2. Replace references like `Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT` with main's member names, e.g. `Skill.DECOMPOSE_FANOUT` or `ContextMinimalFanoutSkill.DECOMPOSE_FANOUT`.
3. Keep assertion that unknown-key stderr is a single line.
4. Keep materialize + force-guard integration assertions against real packaged skills.

#### Edge Cases & Error Handling
- If skill asset text drifts slightly on main, assert on stable substrings already present (`## Algorithm`, enum values, folder names).

---

### 6.5 Supersede `python -m vidbyte.skills`

**File(s):**
- `vidbyte/skills/__main__.py` (Deleted)
- `tests/test_skills_interface.py` (Modified)
- `vidbyte/skills/README.md` (Modified)

**Type:** Deleted / Modified

#### What it does
Removes the interim module CLI that #256 shipped as stretch UX, matching the original CLI design decision that the unified `vidbyte-sdk` command is the terminal interface.

#### Interface / API
```python
# REMOVE
from vidbyte.skills.__main__ import main as skills_main

# README command examples become:
#   vidbyte skills list
#   vidbyte skills show decompose-fanout
#   vidbyte skills install decompose-fanout --dest .claude/skills
```

#### Logic / Algorithm
1. Delete `vidbyte/skills/__main__.py`.
2. Remove `test_module_cli_list_and_install` and the `__main__` import from `tests/test_skills_interface.py`.
3. Update skills README:
   - Command examples → `vidbyte-sdk skills ...`
   - Drop `__main__.py` from Key Modules
   - Optionally one-line note that terminal UX lives under `vidbyte.cli`

#### Edge Cases & Error Handling
- Catalog Python API remains unchanged; only the module CLI entry is removed.
- Users who already scripted `python -m vidbyte.skills` lose that path — intentional; document in PR body.

---

### 6.6 Top-level docs (CLI-only deltas)

**File(s):**
- `docs/design/vidbyte-cli.md` (New — promote from pre-design / PR branch, status Implemented)
- `docs/design/pr-253-cli-only.md` (New — this file)
- `README.md` (Modified — CLI-only)
- `llms.txt` (Modified — CLI-only)

**Type:** New / Modified

#### What it does
Documents the CLI without re-shipping skills-registry design content.

#### Logic / Algorithm
1. Add `docs/design/vidbyte-cli.md` from the CLI design (already present on the contaminated branch / `docs/pre-design/vidbyte-cli.md`), marked Implemented, with a short note that registry dependency is satisfied by #256 on main.
2. Keep this cleanup design under `docs/design/pr-253-cli-only.md`.
3. README / llms.txt changes limited to:
   - Package table row for `vidbyte.cli`
   - Tree entry for `cli/`
   - `## CLI` / `### CLI` section with the four commands
   - Optional one-line capability bullet for installing skills via CLI
4. **Do not** re-add large skills registry README tables, design doc for paradigm skills, skill asset files, or enum/catalog modules.

#### Edge Cases & Error Handling
- If main already documents skills layer later, avoid duplicate/conflicting sections; only add missing CLI pieces.

---

### 6.7 Explicitly excluded from this PR

**Type:** Non-change (must not appear in final PR diff)

| Path / area | Why excluded |
|-------------|--------------|
| `docs/design/paradigm-skills-and-registry.md` | Already on main via #256 |
| `vidbyte/skills/catalog.py`, `__init__.py` (API rewrite) | Already on main |
| `vidbyte/lib/enums/skills.py` rewrite | Already on main (grouped enums) |
| `vidbyte/paradigms/context_minimal_fanout/skills/**` | Already on main |
| `skills/README.md` top-level contributor note if already present | Registry PR territory |
| Unrelated behind-main file drift on old branch tip | Contaminated history |

---

## 7. Data Model Changes

N/A — no database, schema, or SkillRecord shape changes. CLI consumes existing `Skill` / `SkillRecord` / `Skills` on main.

---

## 8. API Changes

### 8.1 Console: `vidbyte-sdk` (new)

**Change type:** New

**Request (argv):**
```text
vidbyte-sdk --version
vidbyte-sdk skills list
vidbyte-sdk skills show <key>
vidbyte-sdk skills install <key> --dest <dir> [--force]
```

**Response:**
```text
# list: one line per skill on stdout
context_minimal_fanout.decompose_fanout - <description>

# show: SKILL.md body on stdout
# install: absolute/relative installed path on stdout
# errors: "error: ..." on stderr
```

**Error cases:**
| Exit | Condition |
|------|-----------|
| 0 | Success |
| 2 | Argparse usage error or unknown/ambiguous skill key |
| 1 | ConfigurationError / OSError during catalog use or install |

### 8.2 Console: `python -m vidbyte.skills` (removed)

**Change type:** Deprecated / Deleted

Replaced by `vidbyte-sdk skills ...` and `python -m vidbyte.cli`.

### 8.3 HTTP APIs

N/A — no network API changes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/pr-253-cli-only.md` | This cleanup design doc |
| CREATE | `docs/design/vidbyte-cli.md` | Promote/implement CLI design on mainline history |
| CREATE | `vidbyte/cli/__init__.py` | Root CLI entry / dispatcher |
| CREATE | `vidbyte/cli/__main__.py` | `python -m vidbyte.cli` |
| CREATE | `vidbyte/cli/skills.py` | skills subcommand group |
| CREATE | `vidbyte/cli/README.md` | CLI package docs |
| CREATE | `tests/test_cli_interface.py` | CLI interface tests (adapted) |
| MODIFY | `pyproject.toml` | Add `vidbyte-sdk` console script |
| MODIFY | `README.md` | CLI section + package table row only |
| MODIFY | `llms.txt` | CLI capability note only |
| MODIFY | `vidbyte/skills/README.md` | Point terminal UX at `vidbyte-sdk skills` |
| MODIFY | `tests/test_skills_interface.py` | Remove module-CLI test + import |
| DELETE | `vidbyte/skills/__main__.py` | Superseded by unified CLI |

**Expected scale:** ~13 files; no skill asset trees; no registry reimplementation.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `argparse` | stdlib | CLI parsing | None |
| `importlib.metadata` | stdlib | `--version` | Fallback to `0.1.0` if package not installed |
| `vidbyte.skills.Skills` | in-repo (main) | Catalog | Medium if main API drifts — pin to current methods |
| `vidbyte.lib.enums.skills` | in-repo (main) | Key types | Medium — must use grouped enum API from #256 |
| GitHub PR #253 branch | `feat/vidbyte-cli` | Delivery vehicle | Force-push needs lease + reviewer awareness |

No new PyPI dependencies.

---

## 11. Rollout & Deployment

- **Feature flags:** None.
- **Breaking change:** Removes `python -m vidbyte.skills` (only existed after #256; short-lived). Document in PR description.
- **Deployment order:** Merge PR #253 after rewrite; no multi-service order.
- **Rollback:** Revert the PR; registry remains intact; CLI entry point disappears.
- **PR mechanics:** Force-push cleaned history to `feat/vidbyte-cli` so [#253](https://github.com/cerredz/Vidbyte-SDK/pull/253) stays the review surface. Update PR body to state CLI-only scope and note registry dependency satisfied by #256.
- **Not a new draft PR** unless force-push is blocked; default is update-in-place.

---

## 12. Open Questions

- [x] ~~Should registry stay in this PR?~~ **No** — user asked for CLI only; registry is on main via #256.
- [x] ~~Rebase vs rewrite?~~ **Rewrite from main** — avoids thrashing #256 files.
- [ ] Confirm force-push to `feat/vidbyte-cli` (update PR #253) vs open a new PR and close #253.
- [ ] Confirm deleting `vidbyte/skills/__main__.py` in this PR (original CLI design says yes) vs leaving both CLIs temporarily.
- [ ] Whether README should also add a brief `vidbyte.skills` package-table row (registry already on main but may be under-documented) — default **no** to keep this PR CLI-scoped; follow-up docs PR if needed.

---

## 13. Alternatives Considered

### Alternative 1: Interactive rebase dropping the three registry commits
- **What:** `git rebase -i` and drop `548364b` / `3bb0d40` / `de2d752`, then rebase onto main.
- **Why rejected:** Rebase onto main still replays commits that touch the same paths as #256 with divergent enum design; high conflict noise and regression risk.

### Alternative 2: Close PR #253 and open a brand-new PR
- **What:** New branch + new PR number.
- **Why rejected as default:** Loses PR #253 comment/review continuity. Acceptable fallback if force-push is disallowed.

### Alternative 3: Leave skills `__main__.py` and only add unified CLI
- **What:** Two terminal surfaces (`python -m vidbyte.skills` and `vidbyte-sdk skills`).
- **Why rejected:** Original CLI design explicitly supersedes the module CLI to avoid dual argparse surfaces; user asked for minimal CLI only, not dual maintenance.

### Alternative 4: Soft-reset contaminated branch and recommit without worktree
- **What:** Reset `feat/vidbyte-cli` in the main checkout.
- **Why rejected:** Workflow requires isolated worktree; also current local checkout may be on an unrelated branch with dirty files.

---

## 14. Verification Checklist (post-implementation, no new test harness)

After implementation, verify:

1. `git diff --name-only origin/main...HEAD` matches the File Change Manifest (no paradigm skill assets).
2. `python -m unittest tests.test_cli_interface` passes.
3. `python -m unittest tests.test_skills_interface` passes after `__main__` removal.
4. `gh pr view 253 --json files` shows CLI-scoped paths only.
5. PR mergeable against main (no skills conflicts).
