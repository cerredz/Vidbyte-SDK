# S5 repair iteration 3/8 — public-skill-loader

Branch `feat/public-skill-loader` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1099 · start `3125d307` (pushed head was `21bb77dd`) · fix head `510ef3f3` · the docs-only head that carries this report is dispatched again, and its run IDs are in the STATUS message, because a committed file cannot name the runs on its own commit.

## Scope

Re-review round 2 (the cap) returned SOUND with three Minors. This iteration closed the two in the release notes a maintainer tags 0.4.0 from, `docs/design/release-0-4-0.md`:
- R-C22 at `:7`;
- R-C21 at `:13`.

R-C20, the PR title, is S6's and was not touched. No test, spec, request.md, pipeline.md or code file was edited. review.md and verify-log.md were appended to only.

## R-C22: "not a collection" (fixed @0ae0c1c4)

- **The defect.** The doc said `SkillLoader(entries)` raises `ConfigurationError` "when the argument is text or not a collection". A generator is not a `collections.abc.Collection`, yet the loader accepts it.
- **The wording chosen deviates from the briefing.** The briefing's fix was "not iterable". I tested that wording against Python's meaning of "iterable", the same standard the re-reviewer applied to "collection". Probe `scratchpad/r3/inv2_wording.py`, run at HEAD from an empty folder with `PYTHONPATH=<worktree>` (the import resolved to the worktree):

  | Argument | `iter()` works | `isinstance(Iterable)` | `isinstance(Collection)` | `SkillLoader(...)` |
  |---|---|---|---|---|
  | generator | True | True | False | ACCEPTED |
  | `__getitem__`/`__len__` class | True | False | False | REJECTED `{'entries_type': 'GetItemOnly'}` |
  | `"abc"` | True | True | True | REJECTED `{'entries_type': 'str'}` |
  | `None` | False | False | False | REJECTED `{'entries_type': 'NoneType'}` |

  - A `__getitem__`-only object is iterable in Python's terms (the glossary, and `iter()` accepts it), but the loader rejects it. So "not iterable" would misdescribe that corner the way "not a collection" misdescribed generators.
  - The enforced rule is the `collections.abc.Iterable` check: INV-2 r4's "one that is not an `Iterable`", and the term `vidbyte/agents/skills/README.md:25` already uses.
- **The fix.** The doc now reads "not an `Iterable`": one phrase, exact.
- **Flip.** If the orchestrator prefers plain English, swap those two tokens for "not iterable" and accept the `__getitem__` imprecision.
- "Takes a tuple or a list" is unchanged (the annotation, row 16(a) and README:25).

## R-C21: the dated later-fixes list (fixed @510ef3f3)

- **The defect.** "#1103 to #1107 at the time of writing" was stale before this iteration began. The local `origin/main` ref has since moved again with no fetch by this agent (the ref is shared across worktrees). It is now `c04e5ef5`, and `git log --first-parent --oneline 0754e01f..origin/main` lists 10 PRs, #1103 to #1112, all `fix(...)`.
- **The fix.** The bullet now reads: fixes merged to `main` after `0754e01f` ship too; `git log --first-parent 0754e01f..v0.4.0` lists them beside #1099. Among them is #1104, which carries #1027's `api_keys` and `model_mode` into child runners.
- **Why the range is exact on the tag:**
  - `git rev-list --first-parent origin/main | grep -c ^0754e01f` gives `1`, so `0754e01f` is on main's first-parent chain;
  - every commit after it has exactly one parent (squash merges), so the range lists the later PRs plus #1099's own squash, hence "beside #1099";
  - #1104's subject, "child runners carry the agent's api_keys and model_mode, and the grader's key check counts them", matches the kept mention.

## Why the source and package stages were not re-run locally

Checked, not assumed. Nothing a gate runs reads `docs/design/release-0-4-0.md`:
- `git grep -n "release-0-4-0" -- ':!docs/spec'` is empty.
- `git grep "docs/design" -- lint tests scripts pyproject.toml MANIFEST.in .github` finds header `RELATED DOCS` lines and prose only. The one path check, `tests/features/harness_threads/test_harness_threads_errors.py:185`, checks that other files exist.
- Lint parses only Python files and `README.md` files (`lint/core/discovery.py:53-70`). The other rules use tracked file names only, and an edit leaves those unchanged.
- The build is plain `setuptools` (no setuptools-scm, no `MANIFEST.in`), with `[tool.setuptools.packages.find] include = ["vidbyte*"]`, so `docs/` is in neither the wheel nor the sdist.

Remote CI ran the full source and package stages on `510ef3f3`.

## Gates (final lines quoted)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (the pack) | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader` | PASS | `67 passed in 0.31s` |
| lint | `python lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline` / `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` (exit 0; 0 REGRESSED or ERRORED; no baseline touched) |
| contract | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 013cf884fb9a532101bbbe128d9fde908b2fd131 (vidbyte-sdk 0.4.0, 643 exports).` |
| version places | `git grep -n -e "0\.3\.1" -e "0, 3, 1" -- ':!docs'` | PASS | empty, `rc=1` |
| remote CI | run 38841931593 on `510ef3f3` | PASS | Source / Python 3.11: `5851 passed, 56 skipped in 105.86s (0:01:45)` / `CI passed.`. Source / Python 3.12: `5851 passed, 56 skipped, 19 warnings in 103.93s (0:01:43)` / `CI passed.`. Package: `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| remote Static policy | run 38841933458 on `510ef3f3` | PASS | Static policy = success |

## Commits

| SHA | Subject |
|---|---|
| `0ae0c1c4` | `docs(design): say SkillLoader rejects a non-Iterable, per INV-2 [R-C22]` (1 file, +1/-1) |
| `510ef3f3` | `docs(design): name later main fixes by range, not a dated list [R-C21]` (1 file, +1/-1) |
| next | `docs(spec): verify-log iteration 3 for public-skill-loader`: the verify-log entry, the review.md round-2 section, and this report |

## Open items

- For S6: R-C20. Set the PR title to the spec's `… (SDK 0.4.0)` title, without `[WIP]`.
- Follow-ups:
  - spec §2 (`spec.md:71`) and AC-3 (`:229`) keep "not a collection", and INV-2 r4 governs;
  - R-6 and R-7.
- For the orchestrator: the R-C22 wording deviation above.
- Not re-run: the inherited local source-stage failures (a), (c), and (d), because no local source stage ran.
