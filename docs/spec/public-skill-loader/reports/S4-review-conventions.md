LENS: conventions
VERDICT: SOUND — every binding AGENTS.md rule, placement rule, lint ratchet, and applicable field-guide check holds in the 15 production files; what remains is four Minor documentation and test-pack polish items, none of which changes behavior.

Diff reviewed: `git diff c9d31a7fb4128d1a609ce9702b0a55c71fcb1a3f...c691c176` (15 production files plus the S2 test pack; pipeline artifacts under `docs/spec/` excluded per briefing). Rule sources applied: AGENTS.md in full; field-guide entries `strict-config-dataclasses.md`, `comment-format.md`, `blocking-lint-invariants.md`, `local-ci-verification.md`, `review-scope.md`, `agents-md-map.md`, `prebuilt-agents.md`, `class-bound-helpers.md`; house style; agentic-engineering `file_headers.md`, `intent_based_commenting.md`, `folder_readme.md` obligations; CONTRIBUTING.md; `.github/workflows/claude.yml`.

WHAT THE IMPLEMENTATION GETS RIGHT (so nobody "fixes" what works)
- `SkillEntries` is placed and shaped exactly as AGENTS.md section 4 and the Placement Rules require. It is `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/skills.py:235-265`. All three checks live in `__post_init__`, which calls no helper of its own, so call depth stays at one level. The module imports only the standard library and `vidbyte.lib`. The class appears only in that module's `__all__`, not in `vidbyte.lib.dataclasses`, `vidbyte.agents`, or the root (checked with an import probe). Each message names `SkillLoader` and the failing part. Each `details` value carries only a type name, a position, or names, which is consistent with the file's own WHAT NOT TO DO 4 and with the `CodingAgentSettings` precedent (`vidbyte/lib/dataclasses/coding.py:152-155`).
- `SkillLoader.__init__` is the thin adapter that `strict-config-dataclasses.md` (lessons 1 and 2) asks for:
  - it contains no `raise`;
  - the conversion is one inline expression, and mypy is clean under both `lint/mypy.ini` and `--strict`;
  - its narration comment was updated in the same commit (`6ad3cbd5`);
  - the memory is built from `self.entries`.
- The root exports sit exactly where row 3 of the spec put them (`vidbyte/__init__.py:302`, `:468`, `:479`, `:880-882`, and header `:24`). Ruff I001 over the whole `vidbyte` tree reports nothing in any touched file, and S015 stays at 13. The contract was regenerated alone in `46c074c3` and `--check` is current. All ratchets hold, and `lint/` is untouched. The committed blobs contain no CR bytes and no generated or cache files, and the diff touches exactly the 15 files in spec section 12.3.
- Every new production comment is 72 columns or narrower, and `# @intent skill-entries-unique-names` sits on its own first line. The headers that were edited keep every A001 field. The `REPO_MAP.md` entry stays general intent with no file names or commands (`agents-md-map.md`). Both READMEs stay well under the A009 limit (8,747 and 22,538 characters), and `## Notes for agents` is still the last section.

FINDINGS (ranked, most severe first)

R-V1 [Minor] [field guide / file headers] vidbyte/lib/dataclasses/skills.py:14 (COMMON MODIFICATION PATTERNS) and :257-261 (@intent) — no maintainer note says the second copy of the unique-name rule must change together with the first
  Evidence:
  - `skills.py:14` is unchanged: "COMMON MODIFICATION PATTERNS: A new source adds its `SkillSourceType` member, … A new field on an entry validates in that entry's `_validate_source`." It does not mention the name rule.
  - The `@intent` at `:258-259` says only "A name identifies one skill to callers through both doors, and JevAlignmentSettings applies the same rule." It does not say where that twin lives or that the two must change together.
  - `grep -n -E "_normalized_skills|both_doors|both doors|INV-18" vidbyte/lib/dataclasses/skills.py vidbyte/agents/skills/loader.py vidbyte/agents/skills/README.md vidbyte/agents/jev/settings.py` finds only:
    - the TESTS line (`skills.py:22`, which names `test_public_skill_loader_both_doors.py`);
    - the `@intent` line `skills.py:258`;
    - the loader's TESTS line;
    - the twin's own definition (`settings.py:89`).
  - The Jev side (`vidbyte/agents/jev/settings.py:7` "names must be unique across every kind", and the `@intent` at `:90`) has no pointer back to `SkillEntries`. Section 14 of the spec forbids editing it.
  Failure:
  - `strict-config-dataclasses.md`, the section "Any primitive value validated inline in more than one call site belongs in its own frozen dataclass", says: "Two independent inline copies of the same rule drift silently". The spec accepts the duplication on purpose (NG-10, INV-18, Q-9, section 11 Conflicts), and this finding does not reopen that decision.
  - What is missing is routing. `file_headers.md` says COMMON MODIFICATION PATTERNS must name "which other files must be updated in the same operation". A maintainer who widens or narrows the name rule in either file learns about the other copy only when the both-doors test fails.
  - A reviewer would write: "If I change this rule, where else do I change it?"
  Smallest fix: add one sentence to the `skills.py` header COMMON MODIFICATION PATTERNS: "The unique-name rule in SkillEntries.__post_init__ has a twin in JevAlignmentSettings._normalized_skills (vidbyte/agents/jev/settings.py; spec NG-10, Q-9): change both together; tests/features/public_skill_loader/test_public_skill_loader_both_doors.py fails on drift." Optionally, name the twin's path in the `@intent` as well. This edits only the docstring and comments, outside `vidbyte/agents/jev/`.
  Spec IDs: NG-10, INV-18, FR-12, section 11 Conflicts

R-V2 [Minor] [comment format] tests/features/public_skill_loader/*.py (e.g. conftest.py:106, test_public_skill_loader_boundary.py:45-46) — the new test modules carry 69 comment lines wider than 72 columns
  Evidence:
  - The field-guide check (`awk 'length($0) > 72 && $0 ~ /^[[:space:]]*#/'`) gives these counts:

    | File | Lines over 72 columns |
    |---|---|
    | conftest.py | 8 |
    | acceptance | 11 |
    | both_doors | 9 |
    | boundary | 13 |
    | contract | 9 |
    | docs | 10 |
    | release | 3 |
    | security | 6 |
    | **Total** | **69** |

  - Examples:
    - `conftest.py:106` is 108 columns: "# Spies on every file open (worker threads included), os.stat, and os.environ reads, then restores them."
    - `test_public_skill_loader_boundary.py:45-46` is a two-line block of 107 and 110 columns. The same block is repeated in the acceptance, both_doors, and contract modules.
  - The same check over the production lines this PR adds prints nothing.
  Failure:
  - `comment-format.md` covers "any `#` comment … that runs past one line". The owner rejected 100–120-column blocks ("if a comment is a multi line comment, then format it correctly"). The entry's check is "prints nothing for the files you touched", and these files are new.
  - The spec's own section 12.4 row 8 ("Every new or changed multi-line comment is at most 72 columns") does not exempt tests.
  - Mitigation: the `jev_skills_preload` pack from #904, merged 2026-10-15 after the entry was written on 2026-10-10, carries 198 such lines. So the owner has not enforced the rule in tests so far.
  Smallest fix: rewrap those comment blocks at 72 columns. This changes comments only; no assertion changes.
  Spec IDs: section 12.4 (comment-format row)

R-V3 [Minor] [folder README] tests/features/public_skill_loader/ — the new folder has FEATURE.md but no README.md, unlike 7 of the 8 test packs added since 2026-10-07
  Evidence:
  - `ls tests/features/*/` shows a README.md beside FEATURE.md in:
    - agent_output_connectors (2026-10-14);
    - sdk_model_catalog (10-12);
    - sdk_managed_text (10-11);
    - coding_agent and jev_bulk_work (both 10-10, each added in a "resolve review comments" PR, #747 and #702);
    - sdk_loop_settings, sdk_middleware_limits, sdk_model_usage, and sdk_operation_costs (10-07).
  - `jev_skills_preload` (10-10) is the one recent exception, and the new pack copied it.
  - `.github/workflows/claude.yml:63` records review lessons in "the Notes for agents section of the README.md of the folder the comment points into".
  Failure:
  - AGENTS.md Repository Map: "Each folder's own README.md documents that folder … Its closing `## Notes for agents` section … The `@claude` review workflow appends to those notes after every review".
  - The agentic-engineering folder-README obligation for new folders.
  - Without a README, the review workflow has nowhere to record a lesson about this pack. Two of the README-bearing packs gained theirs in response to review comments.
  Smallest fix: add a short README.md modeled on `tests/features/coding_agent/README.md`, with Folder Description / Intent, Non-Goals, File Index, and an empty `## Notes for agents`, so that it does not duplicate FEATURE.md's contract. Or record in the S2 report that the pack deliberately follows the `jev_skills_preload` precedent.
  Spec IDs: n/a (spec section 13 lists FEATURE.md and conftest but no README; section 12.5 assigns test-pack paperwork to S2)

R-V4 [Minor] [docs accuracy] vidbyte/agents/skills/loader.py:9 and vidbyte/agents/skills/README.md:23, :48 — texts edited for the public door still describe ordering and retries in JevAgent's terms of settings and runs
  Evidence:
  - `loader.py:9` was edited by `6ad3cbd5`. It still reads "a blocked host costs up to one deadline per step on every run. … Results come back in settings order whatever the grouping."
  - `README.md:23` (the Memory bullet): "are tried again on the next run. A remembered entry costs no request and no file read on later runs."
  - `README.md:48`: "pays up to one deadline per step on every run".
  - The new **Public door.** bullet at `README.md:25` says "in input order", which is also INV-5's term.
  Failure:
  - A caller using the root import has no settings and no runs; its unit is `load()`.
  - `file_headers.md` says to update any section that the finished code contradicts, and AGENTS.md says to regenerate a wrong entry rather than patch around it.
  - This is beyond the stale phrases that AC-16 and spec rows 2(d) and 12 name, so it is optional.
  Smallest fix:
  - "input order (settings order, for JevAgent)";
  - "tried again on the next `load()` (for JevAgent, its next run)";
  - "on every load".

  Leave the comments in the bodies of `load()` and `documents()` alone; row 2(c) keeps them byte-identical.
  Spec IDs: INV-5, FR-10 (in spirit; not pinned by AC-16)

VERIFIED CLAIMS
- Held: "`SkillEntries` is only in the module's `__all__`". An import probe shows it absent from `vidbyte.lib.dataclasses`, `vidbyte.agents`, and the root, and `vidbyte.agents.skills.__all__ == []`.
- Held: "`lib` imports only `collections`". The `skills.py` imports are `collections`, `dataclasses`, `pathlib`, `vidbyte.lib.constants`, `vidbyte.lib.enums`, and `vidbyte.lib.errors`, and A006 stays at 34.
- Held: "S009 stays at 350 … mypy exits 0, and `--strict` reports nothing". Both runs print `Success: no issues found in 2 source files`.
- Held: "Every new comment is at most 72 columns; the two wider lines at `skills.py:55-56` were already there". The awk check over the production lines this PR adds prints nothing, and lines 55-56 sit in the untouched `SkillDocument` `@intent`. This does not hold for the test pack (R-V2).
- Held: "S015 13, S051 259, A001 642, A006 34, S060 32; baseline untouched". `python lint/run.py` prints `SDK-LINT: PASS`, and `git diff c9d31a7f c691c176 -- lint` is empty. Filtering the per-rule `--all` output to the touched files shows only findings that already existed on unchanged lines: S015 at `vidbyte/__init__.py:729`, the A001 headers of the four files that took one-literal version changes, and S051 at `client.py:14`.
- Held: "Files outside §12.3 byte-identical; contract committed alone; every commit has the trailer".
  - The diff's names outside docs and tests are exactly the 15 files.
  - `46c074c3` touches only `contracts/sdk-public-api.json`.
  - All nine work commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` after a blank line, and each cites its spec IDs.
- Held: "Line endings restored". `git ls-files --eol` shows `i/lf` for every changed file, the committed blobs contain 0 CR bytes, and `--ignore-cr-at-eol` gives the same diff stat (88 lines added, 33 removed).
- Held: "contract current". `--check` prints `current at 56541481… (vidbyte-sdk 0.3.1, 642 exports)`. The `source.commit` will not be reachable after a squash merge. That matches precedent: the base contract's `998dc0da` is not an ancestor of main either, and `--check` compares only the data.
- Held: "67 of 67 new cases pass; area suite 426 passed, 1 skipped". I re-ran both.
- Held: AC-1, the §4 snippet. Run from an empty scratch folder, it printed exactly the three spec lines.
- Held: INV-1 identity. `vidbyte.SkillLoader is l.SkillLoader`, `vidbyte.SkillResolution is s.SkillResolution`, and `vidbyte.ConfigurationError is e.ConfigurationError` all print `True`, with the loader imported before `vidbyte`. That order is safe, as the spec's A-8 says.
- Not independently verified: "the IMPROVED rules were already IMPROVED at the start of S3". Checking it needs a base checkout, which is not allowed here. It is plausible, because the diff adds one `@intent` and removes none, while A002 shows 703 → 566.
- Checked and deliberately not raised:
  - `SkillEntries(entries=[])` raises "…must be a tuple or list…" with `{'entries_type': 'list'}`. The message contradicts the check, but spec row 1(b) prescribes that wording, and only an internal caller can reach it.
  - The test pack's `conftest.py` duplicates the jev pack's seam. Spec section 13 offers its own conftest as an option, and the jev pack set the precedent.
  - Three `# type: ignore[arg-type]` in tests. There were 130 at the base, and each one supports a deliberate wrong-type call.
  - The docs-pinning test. `agent_output_connectors` already pins REPO_MAP and README text.
  - `6ad3cbd5` fails S051 on its own, and `edd21008` fixes it. That is the same work item, and main squash-merges PRs.
  - `vidbyte-cli` is named in the loader's ROLE line. Spec row 2(d) prescribes that.
  - The PR body is still the placeholder. Stage S6 replaces it, and it must then follow `.github/pull_request_template.md` (Motivation, Changes, Compatibility, Verification, Follow-ups) as CONTRIBUTING.md requires.

COMMANDS RUN
- `git diff --stat c9d31a7f…c691c176`: 36 files changed, 3,937 lines added, 33 removed. Excluding `docs/spec` and `tests`, it is 15 files with 88 added and 33 removed.
- `PYTHONPATH=$(pwd) python lint/run.py`: `C016 0 0 CLEAN`, `S009 350 350 RATCHETED`, `S015 13 13`, `S051 259 259`, `A001 642 642`, `A006 34 34`, `S060 32 32`, `A009 0 0 CLEAN` … `SDK-LINT: PASS`, `exit=0`.
- `python lint/run.py --rule {A001,A002,S009,S051,S062,S015,C008,C001,S016,S017,S007,S008,S024,A006,S060,A005} --all`, filtered to the touched files: only findings that already existed on unchanged lines (listed under VERIFIED CLAIMS).
- `python -m mypy --config-file lint/mypy.ini --cache-dir=nul vidbyte/agents/skills/loader.py vidbyte/lib/dataclasses/skills.py`: `Success: no issues found in 2 source files`.
- `python -m mypy --strict --follow-imports=silent --cache-dir=nul` on the same two files: `Success: no issues found in 2 source files`.
- `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, filtered to the root, the loader, and the record module: no output.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader`: `67 passed in 0.31s`.
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/jev_skills_preload tests/test_jev_skill_preload.py`: `426 passed, 1 skipped in 4.97s`.
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check`: `contracts/sdk-public-api.json is current at 56541481fbb32624aa70ff26b9f4feeb496ea273 (vidbyte-sdk 0.3.1, 642 exports).`
- The §4 snippet, run with `PYTHONPATH=<worktree>` from an empty scratch folder, printed `house-review loaded 22 bytes` / `pdf not_found False` / `rejected: ['house-review']`.
- `git ls-files --eol` (all `i/lf`), a CR-byte count over the committed blobs (0), and `git ls-tree -r c691c176 | grep egg-info|evals.db|__pycache__|dist/` (none).
- `awk 'length($0) > 72 && $0 ~ /^[[:space:]]*#/'` over the production lines this PR adds printed nothing. Over the test pack it found 69 lines (R-V2), and over the jev pack, 198.
- `git log --diff-filter=A` on each `tests/features/*/README.md` and `FEATURE.md`, which gives the pack README dates in R-V3.
- `git show --stat` on each of the 11 commits `d34a8c3e` through `c691c176` (authors, trailers, file lists).
- `git merge-base --is-ancestor 998dc0da c9d31a7f`: not an ancestor (contract provenance precedent).
- `gh pr view 1099 --json title,isDraft,body`: still a draft, the body is a placeholder, and the head is `c691c176`.
