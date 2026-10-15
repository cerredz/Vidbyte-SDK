# S5 repair iteration 1 — jev-skill-sources

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-skill-sources`, branch `feat/jev-skill-sources`, started at `4a947559`, code HEAD `75c5f459`. PR https://github.com/cerredz/Vidbyte-SDK/pull/904 (draft, untouched).

## Gate matrix

Local runs are at `75c5f459` on Windows with Python 3.11.0, unless a row says otherwise.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` | PASS | `426 passed, 1 skipped in 4.42s` |
| new tests, Python 3.13.1 (closest local stand-in for CI's 3.12) | the same, in a scratch venv | PASS | `425 passed, 2 skipped in 68.80s` (extra skip: `tiktoken is not installed`) |
| R-6 tests | the four S2b R-6 node ids | PASS | `4 passed in 0.12s` |
| lint | `PYTHONPATH=$(pwd) python lint/run.py` | PASS | `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `====================== 3800 passed, 14 skipped in 29.64s ======================` / `CI passed.` |
| package stage | `python scripts/run_ci.py --stage package` (PYTHONPATH unset) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| contract | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 3a4cb9292f62e40afa39478fdea5cf53fd758065 (vidbyte-sdk 0.2.1, 615 exports).` |
| semgrep | `semgrep --test …typed-mapping-boundary-policy.py` and `semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (1.170.1, scratch venv) | PASS | `1/1: ✓ All tests passed` / `Ran 1 rule on 900 files: 0 findings.` |
| remote checks | `gh api repos/cerredz/Vidbyte-SDK/commits/75c5f459…/check-runs` | PASS | 4/4 on `75c5f459` (CI run 38247240051, Static policy run 38247243321): `Package success` / `Static policy success` / `Source / Python 3.12 success` / `Source / Python 3.11 success`. 3.12 log: `3796 passed, 18 skipped, 19 warnings in 47.39s` / `CI passed.`; 3.11: `3796 passed, 18 skipped in 36.34s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.`; Static policy: `1/1: ✓ All tests passed` / `Ran 1 rule on 900 files: 0 findings.` |

**Lint detail.**
- Ratchet rows: A001 642/642, C002 9/9, C008 PASS, S024 25/25, S009 350/350, C016 0/0, A009 0/0, S020 1/1.
- The IMPROVED rows were there before this iteration: A002 640/703, A007 254/255, C012 23/24, S001 56/59, S010 0/5, S025 261/263, and S051 258/259. S3 deviation 7 records them. A007 is 254 with and without the R-8 edit.
- No baseline changed.
- `git diff 578cd064..HEAD -- tests/ lint/` is empty.
- The import resolves to the worktree: `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` printed `…\vidbyte-sdk-jev-skill-sources\vidbyte\__init__.py`.

## Per finding

| ID | What I did | Commit | Evidence |
|---|---|---|---|
| R-1 (Blocker) | `_tree_paths`: the existing `FETCH_FAILED` "unexpected answer" condition gains `or not all(isinstance(item, dict) and isinstance(item.get("path"), str) for item in tree)`. The return now filters on `type == "blob"` only, because every item is already a dict with a text path. Comment and header updated for EC-68. | `879a4b16` | Before: 5 github failures. After: `test_skill_sources_github.py` gives `48 passed`. The guard rows `empty tree` and `folders and a submodule only` stay green, so empty and non-blob trees still reach the search. On 3.13.1, where the 2,000-level body parses, `test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load` gives `14 passed`. |
| R-2 (Blocker) | GitHub `resolve`: right after the Vidbyte-prefix guard, `if token is not None and not (token.isascii() and token.isprintable())` returns `AUTH_FAILED` × group. Vendor `_key`: the same check after the Vidbyte check, so it runs before any request is built. Details name `token=`/`GITHUB_TOKEN` or `api_key=`/the env var, say "character an HTTP header cannot carry", and never the value. Header notes updated. | `556b84fc` | Before: 38 failures, among them a `UnicodeEncodeError` from `httpx/_models.py:82` escaping `SkillLoader.load`. After: security, vendor, and github give `222 passed`. That includes the 36 cases, the 3 boundary cases (space and `~` still sent), and the 2 real-seam cases (patched `httpx.AsyncClient.send`, never reached). `resolve_api_key` returns the stripped entry value whenever one is set, so an unsafe entry cannot fall back to a usable env value. |
| R-3 (Blocker) | Done last. Every full-line `#` block that holds a PR-authored line over 72 columns is re-wrapped with a balanced fill, in 14 files. `# @intent` lines stay alone. `lib/dataclasses/skills.py:52-53` and `alignment/skills.py:78` (pre-existing) are untouched. | `75c5f459` | A PR-line checker over `git diff -U0 ba3e4ca5...HEAD -- vidbyte/` reports `total 0`. Only comment lines changed: a grep of non-comment `+`/`-` lines is empty. The words are identical: `words equal: True 1161 1161`. A002 is unchanged (640/703). |
| R-4 (Major) | The local `NOT_FOUND` detail gains "This agent remembers the miss, so create a new agent after fixing it." The absolute path stays (EC-16), and the wording says "agent", not "JevAgent". | `757a0464` | `test_remembered_not_found_says_to_create_a_new_agent_after_fixing` passes, and the pack gives `426 passed, 1 skipped`. |
| R-5 (Major) | `SkillText.require_version(value, field_name)` gives the integer hint and then calls `require`. `SkillText.require_folder(value, field_name) -> Path` checks for a non-empty `str`/`Path` and returns `Path(value).absolute()`. `AnthropicSkill`, `OpenAISkill`, `LocalSkill`, and `SkillsShSkill` call them. `LocalSkill` keeps its own "not SKILL.md itself" check. No new class, so §8.4 holds. | `ca340b36` | C002 `9 known` (unchanged), and C008 passes. The 41 entry tests asserting `<Class>.<field>` pass, as does `test_integer_version_is_rejected_with_a_hint_to_pass_text`. |
| R-6 (Major) | No source change. The S2b tests already close it. | `f90b0680` | The four node ids give `4 passed in 0.12s`. |
| R-8 (Minor) | `match members:` with guarded `case [member] if …` arms, `case [member]: return archive.read(member)`, and `case _:` for the count detail. The constant and its `__all__` entry are deleted. | `dde94f83` | `test_skill_sources_vendor.py` gives `115 passed`. S024 stays 25/25. The review's literal shape would put the `if`s at depth 4 (try → with → match → if), over S024's limit of 3. The constant is not in `contracts/sdk-public-api.json` (`grep -c SKILL_ARCHIVE` = 0). |
| R-9 (Minor) | `auth = HttpResponseParser().bearer_headers(token) if token else {}`. | `9567cd4a` | The pack gives `406 passed, 1 skipped` for `tests/features/jev_skills_preload`. No test asserts the whole header dict. The import-sort check shows no new finding in our files. |
| R-12 (Minor) | The jev `__init__` PURPOSE lists the seven entries and two enums. vendor.py's COMMON MODIFICATION PATTERNS and README "Adding a source" step 3 say to add a new vendor's entry class to the constrained `VendorSkillT`, or mypy (S009) rejects the subclass. | `472c7b1a` | A001 642/642, A009 clean, S020 1/1. Its commit type is `docs(skills)` rather than `fix(skills)`, because the change is header and README text only. |
| R-13 (Minor) | `SKILL_MARKDOWN_DELIMITER = "---"` in `lib/constants/skills.py` (with `__all__`). markdown.py drops `_DELIMITER`, and vendor.py uses `SKILL_MARKDOWN_DELIMITER.encode()`. | `4079d101` | The pack gives `426 passed, 1 skipped`, and ruff passes over the touched files. |
| R-14 (Minor) | Already done by spec r5. Marked in review.md. | `18903d3d` | — |

Every status is updated in review.md. R-7, R-10, R-11, and R-15 to R-19 stay `open — follow-up`, as the briefing directs.

## Hypotheses that failed, and why

- **R-5 edit through a Bash heredoc.** The heredoc removed one level of backslashes, so the Python anchor `'\\'` became `'\'` and did not match. The script's own assertion stopped it before any write. Writing the script with the Write tool fixed it. This is the known "Bash heredocs collapse `\\`" gotcha.
- **R-8 as the review literally wrote it** (`case [member]:` holding the two `if` checks). It was rejected before it was committed, because S024 would regress (nesting depth 4 against a maximum of 3). Guarded cases keep each arm a single return.
- **R-3 with a greedy fill.** It left one-word orphan lines, so it was replaced by a balanced fill.
- **R-3 with automatic block detection only.** It merged loader.py's `@intent` text with the next step's narration, and a pre-existing `@intent` line in `alignment/skills.py` with new narration. Explicit paragraph splits fixed both in the dry run, before any write.

## Interactions between fixes

- R-1, R-2, and R-9 all edit `github.py`.
- R-2, R-8, R-12, and R-13 all edit `vendor.py`.
- R-3 then re-wrapped the comments that R-1, R-2, and R-5 added or changed. No fix reopened another.

## Judgment calls the next reviewer should know

- **`jev/settings.py:89`** predates the PR, but its block's second line (90) is a PR rewrite. I wrapped the two-line block as a whole, with every word preserved. Wrapping only line 90 would leave a 103-column line above a wrapped tail. This is the only pre-existing comment line I changed.
- **Balanced fill.** It makes some short blocks narrower than 72, for example `anthropic.py` at 38 and 48 columns. Both stay within the rule and follow the guide's "fill the lines evenly".
- **The R-12 commit type** is `docs(skills): … [R-12]` instead of `fix(skills): … [R-12]`. The commit is pushed, and force-push is forbidden, so it stays.
- **No test was changed or proposed.** No finding is disputed.

## Scope

- Files changed this iteration: 16. All were already in the PR's diff (`comm` against `ba3e4ca5..97c67062` is empty), and all are ASCII-only.
- §8.4 budget: no new files, classes, dependencies, config keys, or public names. One constant was added (`SKILL_MARKDOWN_DELIMITER`) and one removed (`SKILL_ARCHIVE_MARKDOWN_COUNT`).
- The contract is unchanged at 615 exports.

## Open items

None: every gate is green, and no confirmed finding is open (R-1 to R-6 fixed; trivial Minors R-8, R-9, R-12, R-13 fixed; R-14 done by spec r5). The follow-up Minors R-7, R-10, R-11, and R-15 to R-19 are for the user, not open defects. This docs commit (review.md, verify-log.md, the report) changes no code; it is pushed and both workflows are dispatched on it as well.

## What I would try next if a remote job is red

- **3.12 only.** First reproduce in the 3.13 scratch venv, `scratchpad/py313-venv`. Its `json` C scanner also parses deep nesting.
- **A Package failure.** Run `python scripts/run_ci.py --stage package` with PYTHONPATH unset. On a failure, read `gh run view <id> --log-failed | tail -n 40` first.
