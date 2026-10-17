# S3 implementer report: provider-onboarding-skill

- **Branch:** `feat/onboard-model-provider-skill`, pushed with upstream tracking.
- **Base:** `base_commit` 72a4ade1; S2_HEAD 8e9b8b7f.
- **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1175. It has the WIP title and a placeholder body, and it stays a draft.
- **Spec:** `status: implemented`, `revision: 5`, and `pr:` set.

## What was built

| §12.3 row | File | Commits | Covers |
|---|---|---|---|
| 1 | `.claude/skills/onboard-model-provider/references/provider-run.md` (new, 366 lines) | 90c199be, 5a60c216 | W-4, W-5, FR-7 to FR-10, AC-4, AC-7, AC-8 |
| 2 | `.claude/skills/onboard-model-provider/SKILL.md` (new, 241 lines) | 37e721fa | W-1 to W-3, FR-1 to FR-6, FR-11 to FR-13, FR-15 to FR-17, AC-1 (static half), AC-2, AC-3, AC-5, AC-6, AC-13, AC-15 |
| 3 | `REPO_MAP.md`, the `### .claude/` entry (one line changed) | 50f8bb1b | W-6, FR-16, AC-9 |

**Pipeline commits.** e685a4f8 records the draft PR (spec `pr:` and `status: implemented`). 1f44219c adds the PR-time proof under spec §6.2, the r5 row in §17 and the implementation-deviations list. The commit that adds this report follows them.

**Budget.** The work used 2 new files and 1 modified file, with no `.py` file and no new dependency. `git diff 8e9b8b7f HEAD -- tests` is empty. Nothing under `vidbyte/`, `lint/`, `scripts/`, `.github/` or `.claude/ci-settings.json` changed. No vendor was onboarded.

**provider-run.md.** The H2s are exactly `## 1. Orient` through `## 10. Result`.
- `## 3. Qualify` names every disqualification reason and runs the D-13 cross-vendor collision check.
- `## 5. Wiring checklist` holds the 33-row table, byte-identical to spec §12.3. Every path and symbol in it exists at HEAD.
- Sections 6 and 7 hold the self-check, the commit, the green run, and the mutation checks (revert the rule, restore with `git -C … checkout --`, confirm `diff --quiet`). Section 8 holds the gate with the base-SHA known-red rule, and section 9 the publish with a single refspec through `gh api`.

**SKILL.md.** The H2s match the §8.5 list. It covers:
- the preflight and pass-top blocks;
- the brief, byte-identical to §8.5;
- the four result checks, with the checklist paths taken from the procedure by `sed`;
- the D-8 cleanup;
- the 12 output forms of §9.2;
- the rules, the 10-row seed table and the 4 excluded vendors.

## Verification (final lines quoted)

- **S2 tests:** `py -3.11 -m pytest tests/features/onboard_model_provider_skill -q -p no:cacheprovider` → `46 passed in 0.86s`.
- **Area suite:** the S2 tests plus `tests/features/agent_output_connectors` and `tests/features/coding_agent`, the two suites that read `REPO_MAP.md` → `1009 passed, 12 skipped in 20.01s`.
- **Lint, inside the source stage:** `SDK-LINT: PASS`.
- **Source stage:** `PYTHONPATH=<worktree> py -3.11 scripts/run_ci.py --stage source` → `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, then `1 failed, 5815 passed, 16 skipped in 86.37s (0:01:26)`, then `CI failed: Command failed with exit code 1: … -m pytest`. That failure is excepted under D-15, as the next section shows.
- **Package stage:** `py -3.11 scripts/run_ci.py --stage package --dist-dir <scratch>`, run without PYTHONPATH → `Installed vidbyte-sdk 0.3.0 passed smoke checks.`, then `CI passed.`

## PR-time evidence

`<worktree>` is this branch's worktree. The e-mail address is withheld.

### AC-1, read-only run

The commands were run verbatim from `<worktree>` as the launcher checkout, and the run stopped before `git worktree add`:

```text
$ git rev-parse --show-toplevel            -> <worktree>                                   exit 0
$ git remote get-url origin                -> https://github.com/cerredz/Vidbyte-SDK.git   exit 0
$ gh api repos/cerredz/Vidbyte-SDK --jq .permissions.push -> true                         exit 0
$ git config --get user.email              -> <address withheld>                           exit 0
$ PY=; for c in python python3 "py -3.11"; ... -> py: python                               exit 0
$ git fetch --quiet origin main                                                            exit 0
$ git show origin/main:vidbyte/lib/registries/pricing.py | sed -n ... -> 2026-10-11       exit 0
$ date -u +%F                              -> 2026-10-17                                   exit 0
$ gh api --paginate "repos/cerredz/Vidbyte-SDK/pulls?state=open&per_page=100" --jq ... -> (no line)  exit 0
$ git show origin/main:vidbyte/lib/enums/model_provider.py | sed -n ...
  -> openai anthropic gemini xai deepseek glm minimax kimi meta mistral openrouter elevenlabs playai typesafe   exit 0
$ gh api "repos/cerredz/Vidbyte-SDK/pulls?state=all&head=cerredz:feat/provider-cerebras&per_page=100" --jq ... -> (no line)  exit 0
remote-branch exit 2
local-branch exit 1
paths exit 1
STOPPED before git worktree add
```

The vintage (2026-10-11) is before today, no provider PR is open, and cerebras, rank 1, is not a member and hits no skip rule. A real pass would therefore create `feat/provider-cerebras`. The launcher tree stayed clean.

### AC-10 and INV-23, diff against `base_commit`

`git diff --stat 72a4ade1 HEAD` ends `21 files changed, 4530 insertions(+), 1 deletion(-)` at 1f44219c. The changed paths are:
- `SKILL.md`;
- `references/provider-run.md`;
- `REPO_MAP.md`;
- 10 files under `docs/spec/provider-onboarding-skill/**`, which becomes 11 with this report;
- the 8 S2 files under `tests/features/onboard_model_provider_skill/**`.

Checks on that diff:
- A `grep -vE` for any path outside that set printed nothing (exit 1).
- `git diff --quiet 72a4ade1 HEAD -- vidbyte lint scripts .github` exits 0.
- `git diff --diff-filter=A --name-only 72a4ade1 HEAD -- .claude REPO_MAP.md` lists only the two skill files.

### INV-24

- `git diff --quiet 72a4ade1 HEAD -- .claude/ci-settings.json` exits 0.
- `git rev-parse 72a4ade1:.claude/ci-settings.json HEAD:.claude/ci-settings.json` prints `f5c44a2064b7b4c426a5ae7efd98987ddf82164b` twice.
- `.github/workflows/claude.yml:50` reads `settings: .claude/ci-settings.json`.

### AC-11 and INV-25, package

- The package stage's final lines are quoted above.
- The wheel `vidbyte_sdk-0.3.0-py3-none-any.whl` has 1126 entries. Its top-level names are `['vidbyte', 'vidbyte_sdk-0.3.0.dist-info']`, and it holds no `.claude` path.
- The sdist `vidbyte_sdk-0.3.0.tar.gz` has 1433 entries and no `.claude` path. It also holds no `onboard_model_provider_skill` test and no `REPO_MAP.md`, which bears out spec assumption A-6.

### AC-12 and INV-26, gate with the D-15 exception

- **Source stage.** The import path is `<worktree>\vidbyte\__init__.py`, and lint prints `SDK-LINT: PASS`. Pytest ends with the one failure quoted above.
- **Flaky test excluded.** Three reruns of that node on the branch each ended `E       AssertionError: assert 148 == 120` and `1 failed` (0.92 s, 0.90 s, 0.91 s), so the failure is not flaky.
- **File unchanged.** `git diff --quiet 72a4ade1 HEAD -- vidbyte tests/features/harness_threads` exits 0.
- **Red at `base_commit`.** In a detached worktree at 72a4ade1 (`<worktree>-main`, removed afterwards) the test ended `E       AssertionError: assert 148 == 120` and `1 failed in 1.64s`.
- **Red on `origin/main`.** In a detached worktree at 845a4d9b (removed afterwards) it ended `E       AssertionError: assert 148 == 120` and `1 failed in 0.93s`.
- **Other known-red test.** The MCP stdio flake passed in this run.
- **Lint baselines.** The lint run also printed baseline improvements on code this PR does not touch, for example `S063 IMPROVED 4 -> 3` and `A002 IMPROVED 703 -> 578`. No baseline was changed.

## Implementation deviations

The full list, 14 items, is in spec §17 under "Implementation deviations (S3)". In brief:
1. Base drift was not rebased.
2. Sections 1–5 are repeatable work and sections 6–9 are one-shot proof.
3. A collision check that cannot finish counts as `key-prefix-collision`.
4. Extra models follow the pricing page's order.
5. Only flat USD per-1M rates are accepted.
6. Commands spell the repository literally.
7. Page values enter commands only in single quotes, and quotes are checked with `grep -F -f`.
8. Commands use `cd <worktree> &&` and `git -C`.
9. The path check is `grep -vxF -e "$(sed …)"`.
10. Evidence is split into `pages/`, `quotes/` and `probes/`, and the text form uses `<py> -I`.
11. The NETWORK_BLOCKED evidence is inline.
12. A `qualify_ids.py` probe decides model-ID eligibility.
13. The seed reasons hold no researched facts.
14. The cleanup `rm -rf` is guarded by `test -n "$SLUG"`.

Separately, the §17 record is r5 rather than the r4 the brief named, because S1 had already used r4.

## Drift since `base_commit`

- **Scope.** `origin/main` is 845a4d9b, 69 commits ahead.
- **What changed.** Among this PR's files, only `REPO_MAP.md` changed on main, and not its `.claude/` entry. Elsewhere `test_provider_keys_contract.py` changed. No wiring-checklist path or symbol changed.
- **Merge check.** `git merge-tree` is clean. A merged-tree probe, commit 4e7135af built with `git commit-tree` and no ref, ran the S2 tests and the map suites: `1009 passed, 12 skipped in 19.27s`.
- **Not rebased.** S6 decides whether to update the branch.

## Niche facts

- On this machine's Git Bash the preflight probe selects `python`, which is Python 3.11, rather than `py -3.11`. Both name the same interpreter.
- The working copy of `spec.md` is LF in both the index and the worktree, despite `core.autocrlf=true` warnings.
- The S2 tests read only the skill files and `REPO_MAP.md`, never `spec.md`, so the frontmatter and proof edits cannot affect them.
- `date -u` had already rolled over to 2026-10-17 during the AC-1 run, while the local date was 2026-10-16.

## Open items

- **For S6.** S6 replaces the placeholder PR body with the full description, including the PR-time evidence above, and re-records AC-10, AC-11 and AC-12 on the final tip.
- **The PR stays a draft.** This stage never marked it ready and never merged it.
- **Known-red test on main.** The known-red harness test, `assert 148 == 120`, is red on `base_commit` and on `origin/main` alike, independent of this PR.
