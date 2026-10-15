LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, layering, the call-depth rule, and the lint ratchet hold, but the comment-format rule from the field guide is broken in every new module, and the C002 duplicated-guard finding was hidden by changing syntax instead of being fixed.

Reviewed: `git diff origin/main...97c67062` (merge base `ba3e4ca5`). The 25 S3 code commits `ae4d205a..429c77e9` were read file by file. Every changed `.py` file and README was read whole.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- **Placement follows AGENTS.md exactly.**
  - All three enums are in `vidbyte/lib/enums/skills.py` and exported from `vidbyte/lib/enums/__init__.py`. `SkillFetchStep` goes no further than that.
  - Every new dataclass is `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/skills.py`. `JevSkillResult` is edited in place in `jev.py`.
  - Constants are in the new `vidbyte/lib/constants/skills.py`.
  - `vidbyte/agents/skills/` holds no dataclass, enum, `types.py`, or `constants.py`.
  - `alignment/skills.py` has only imports, the class, and `__all__` at top level (jev-capability-layout.md quick check).
- **Principle 1 holds in every new main function.** These call only leaf helpers or other classes:
  - `SkillLoader.load`, `SkillMarkdown.parse`, and `SkillFetch.get`;
  - the six `resolve` methods (GitHub's step leaves reach `_GitHubAnswer.failure`, which is another class, per D-31).

  There are no nested functions. The longest new or changed function is `JevSkillsPreload.run` at 47 lines, and the largest new file is `vendor.py` at 213 lines.
- **Layering is clean, and no lint finding was added.**
  - `vidbyte/agents/skills/*` imports only `vidbyte.lib.*` and its sibling modules, never `vidbyte.agents.jev` or the `vidbyte.agents` root. No `vidbyte/lib` module imports upward.
  - Filtering `lint/run.py --all --format json` to the changed paths shows only findings that already existed on main. Every new file has zero findings.
- **Principle 5 holds for HTTP.** One `SkillFetch.get` sends every request through `HttpTransport.request` with `timeout_seconds`, `retry_count`, `backoff_seconds`, `max_response_bytes`, and `follow_redirects=False`.
  - Status maps are dicts looked up by the integer status, with an explicit default (no `HTTPStatus(`).
  - There is no retry loop.
  - Secrets are `field(default=None, repr=False)`.
  - `vb_live_` is spelled only through `VIDBYTE_API_KEY_PREFIX`.

FINDINGS (ranked, most severe first, max 15)

R-V1 [Blocker] [field guide: comment-format] vidbyte/agents/skills/resolver.py:29 (and 52 more lines across 10 new modules, plus 9 PR-authored lines in modified files) — Multi-line and step comments overrun the 72-column limit, counting the indent
  Evidence:
  - `for f in vidbyte/agents/skills/*.py vidbyte/lib/constants/skills.py vidbyte/lib/dataclasses/skills.py; do awk 'length($0) > 72 && $0 ~ /^[ \t]*#/' $f; done | wc -l` → `53` (of 222 comment lines). Per file:

    | Lines | File |
    |---|---|
    | 13 | vendor.py |
    | 8 | fetch.py |
    | 8 | github.py |
    | 6 | markdown.py |
    | 4 | loader.py |
    | 4 | local.py |
    | 4 | skills_sh.py |
    | 1 | anthropic.py |
    | 1 | resolver.py |
    | 1 | constants/skills.py |
    | 3 (1 PR-authored: line 119; 52–53 predate the PR) | dataclasses/skills.py |

  - Worst lines:
    - `resolver.py:29 (88) # Entries with equal keys share lookups; by default each entry is its own group.`
    - `dataclasses/skills.py:119 (77) # The text is kept exactly as written; only blank values are refused.`
    - `fetch.py:65 (76)`, `markdown.py:68 (76)`, `vendor.py:191 (76)`
  - Lines this PR wrote or edited in modified files (`git blame` over `origin/main..97c67062`):
    - `vidbyte/agents/jev/alignment/skills.py:67 (140) # JevAgent passes already-normalized skills, a validated decision configuration and threshold, and the response writer for this run.`
    - `vidbyte/agents/jev/settings.py:90 (99) # different candidate bodies indistinguishable to callers, whichever source each came from.`
    - `vidbyte/lib/dataclasses/jev.py:3759-3760 (74, 75)`
    - five narration lines in `alignment/skills.py` (73–75 columns)
  Failure: `field-guide/vidbyte-sdk/comment-format.md` says: "Wrap every comment line at 72 columns, counting the indent … A single-line comment that would pass 72 columns becomes a wrapped block too." Its quick check is `awk 'length($0) > 72' <file> | grep -E '^\s*#'` "prints nothing for the files you touched". That check fails on 10 of the 13 new modules. The guide records the owner's own review comment on PR #690: "stop writing comments like this, if a comment is a multi line comment, then format it correctly". Spec §12.4 lists the rule, and S3's report says every §12.4 item was checked. This is a review comment the user will get again.
  Smallest fix: Re-wrap every PR-authored `#` line in the 13 new modules and the three modified files (`alignment/skills.py`, `settings.py`, `jev.py`) to 72 columns or less, counting the indent. Wrap `resolver.py:29` and `dataclasses/skills.py:119` into two-line blocks. Keep each `# @intent <name>` on its own first line and within A002's window. Leave lines 52–53 of `dataclasses/skills.py` alone (they predate the PR). Re-run the awk check and `python lint/run.py --rule A002`.
  Spec IDs: §12.4 ("Multi-line comments are 72-column # blocks"); FR-16

R-V2 [Major] [lint-dodge / field guide: strict-config-dataclasses, blocking-lint-invariants (C002)] vidbyte/lib/dataclasses/skills.py:198 and :216 — The duplicated `version` guard got past C002 by changing syntax, not by giving the check one owner
  Evidence:
  - `AnthropicSkill._validate_source` (195-201) and `OpenAISkill._validate_source` (213-219) are the same apart from the class name:
    ```python
    SkillText.require(self.skill_id, "AnthropicSkill.skill_id")
    if type(self.version) is int:
        raise ConfigurationError(f'AnthropicSkill.version must be text; pass "{self.version}".')
    SkillText.require(self.version, "AnthropicSkill.version")
    SkillText.require_optional(self.api_key, "AnthropicSkill.api_key")
    ```
  - S3-implementer.md, "Tricky parts": "`isinstance(self.version, bool)` in the vendor entries tripped C002 … `type(self.version) is int` expresses 'an int but not a bool' without that pattern."
  - What C002 does:
    - `lint/rules/c002_duplicate_inline_bool_guard_validation.py` header: "Enforces one validation owner for duplicated bool guards". It fires at `len(occurrences) >= 2`, so the two vendor guards alone meet the threshold.
    - It matches only `isinstance(<name>, bool)`.
    - `skills_sh.py:102` uses a third form for the same identity: `type(version) is bool`.
  - The path guard is copied the same way:
    - `LocalSkill._validate_source` (134-138): `if not isinstance(self.path, (str, Path)) or self.path == "" … object.__setattr__(self, "path", Path(self.path).absolute())`
    - `SkillsShSkill._validate_source` (154-156) repeats the check and the pinning for `directory`.
  Failure:
  - `strict-config-dataclasses.md`: "Any primitive value validated inline in more than one call site belongs in its own [owner] … Two independent inline copies of the same rule drift silently."
  - `blocking-lint-invariants.md` (C002): "Never add a second `isinstance(x, bool)` guard for a field name that is already guarded."

  The rule fired on real duplication, and the change kept the duplication while moving it out of the matcher's sight. A reviewer would say: "these two `_validate_source` bodies are copies — give the version check one home."
  Smallest fix: Add two static helpers to the existing `SkillText` class, and have both vendor entries and both path entries call them. The parameter name `value` is in C002's `_GENERIC_IDENTITIES`, so a guard inside the helper does not count. No new file is needed.
  - `SkillText.require_version(value, field_name)`: rejects `int` with the "pass "2"" hint, then calls `require`.
  - `SkillText.require_folder(value, field_name) -> Path`: checks for a non-empty `str` or `Path` and returns `Path(value).absolute()`.
  Spec IDs: FR-3, INV-2, EC-75, EC-13; §12.4 "Status flags are derived … C002"

R-V3 [Minor] [lint-dodge constant / house style] vidbyte/lib/constants/skills.py:102 — `SKILL_ARCHIVE_MARKDOWN_COUNT = 1` is a setting that cannot actually change
  Evidence:
  - The constant: `SKILL_ARCHIVE_MARKDOWN_COUNT = 1`
  - How vendor.py:201-203 uses it:
    ```python
    if len(members) != SKILL_ARCHIVE_MARKDOWN_COUNT: …
    (member,) = members
    ```
  - vendor.py:209: `except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, ValueError):`
  - Spec §17: the constant exists only because A007 flagged a bare `1` beside `archive.read`.
  Failure: The house style lists "a config option with one caller" as a smell. Here the unpacking hard-codes one member. If anyone set the constant to 2, the unpacking would raise `ValueError`, line 209 would catch it, and a valid archive would be reported as "The zip archive … is damaged". A named constant suggests the number can be changed safely, and it cannot.
  Smallest fix: Replace the count check and the unpacking with `match members: case [member]: … case _: return SkillResolution(INVALID_SKILL, …)`. That has no literal for A007 to flag. Then delete the constant and its `__all__` entry.
  Spec IDs: D-20, EC-86

R-V4 [Minor] [principle 5 / sibling consistency] vidbyte/agents/skills/github.py:108 — The GitHub resolver builds its bearer header by hand, which its sibling's header forbids
  Evidence:
  - github.py:108: `auth = {"authorization": f"Bearer {token}"} if token else {}`
  - openai.py:5 says the shared helper `HttpResponseParser.bearer_headers` is used "(AGENTS.md principle 5)".
  - openai.py:8 says: "Do not build the bearer header by hand".
  - `vidbyte/lib/http/parser.py:21-23` defines `bearer_headers`.
  Failure: AGENTS.md principle 5 says: "look in `vidbyte/lib/` for a helper that already does it … have every caller use that helper". Spec §8.2 names `bearer_headers` as the inherited pattern. Two resolvers in one package now build the same header in two different ways.
  Smallest fix: Change line 108 to `auth = HttpResponseParser().bearer_headers(token) if token else {}`. The added `content-type` is ignored on a GET, as openai.py:9 already notes.
  Spec IDs: D-9, §8.2

R-V5 [Minor] [principle 2 / readability] vidbyte/agents/jev/alignment/skills.py:84-90 — Each loaded skill starts with a fake "Jev answered" result
  Evidence:
  - Lines 84-86:
    ```python
    # Start every skill as unavailable. A skill that never loaded keeps
    # the loader's reason and has no description or label to show; a
    # loaded skill counts as unanswered until Jev answers for it.
    ```
  - Line 88: `index: self._score_skill(index, loaded[index], {})`
  - Line 199: `detail="Jev answered this batch but gave no usable answer for this skill"`
  Failure: The placeholder is built by "scoring" against an empty answer map, so its detail says Jev answered when Jev was never asked. The comment ("counts as unanswered") and the record disagree. AGENTS.md principle 2 requires comments that match the code, and the house style says "Obvious over clever".

  Callers never see the placeholder: every path replaces it (verified below). The problem is the reader's model of the code.
  Smallest fix: Seed `results` only for skills that never loaded. After the batch loop, which already sets every loaded index through `_unbatched`, `_failed_batch`, or `_score_skill`, emit `tuple(results[index] for index in sorted(results))`. This removes the `_score_skill(…, {})` trick.
  Spec IDs: INV-16, INV-17, §12.4 (main functions narrated)

R-V6 [Minor] [principle 4 / error packets] vidbyte/lib/dataclasses/skills.py:70, 77, 85-87, 135, 155, 176, 183 — Construction errors name the field but not the bad value, and carry no `details`
  Evidence:
  - Line 70: `raise ConfigurationError(f"{field_name} must be non-blank text.")`
  - Line 135: `raise ConfigurationError("LocalSkill.path must be a non-empty str or Path naming the skill folder.")`
  - No new entry error passes `details=`.
  - The sibling precedent the spec cites, `vidbyte/lib/dataclasses/coding.py`, passes `details={"parameter": "verify_command", "verify_command_type": type(command).__name__}`.
  Failure: AGENTS.md principle 4 says each dataclass "raises a clear error that names the field and the bad value". Secrets (`token`, `api_key`) and `repo` (EC-48: a pasted token) must not be echoed, but the value's type is safe for every field.
  Smallest fix: In `SkillText.require`, `require_optional`, and `require_segment` (the same three helpers cover most sites), add `details={"field": field_name, "value_type": type(value).__name__}`. Do the same for the `LocalSkill`, `SkillsShSkill`, and `GitHubSkill` path and repo errors.
  Spec IDs: INV-2, FR-3

R-V7 [Minor] [header accuracy, A001 / file_headers.md] vidbyte/agents/jev/__init__.py:3-5, vidbyte/agents/skills/vendor.py:7, vidbyte/lib/enums/skills.py:8 — Three headers no longer describe the finished code
  Evidence:
  - jev/__init__.py:3 is not updated in the diff. It says `PURPOSE: Exposes JevAgent, its agent and runtime settings, the JevSpecialist record, its runtime, the preflight flags and done checks, and the records a caller reads on JevAgent.response.` The module now also exports the seven skill entries and two skill enums (rows 23).
  - vendor.py:52 is `VendorSkillT = TypeVar("VendorSkillT", AnthropicSkill, OpenAISkill)`. But vendor.py:7 COMMON MODIFICATION PATTERNS lists a new vendor as "a subclass … plus its entry class, enum member, and loader map entry". The README section "Adding a source" also omits widening `VendorSkillT`, so the S009 (mypy) check rejects `VendorSkillResolver[NewSkill]`.
  - enums/skills.py:8 says "saved settings carry `SkillSourceType.value`", but nothing persists settings.
  Failure: The agentic-engineering header obligation and spec §12.5 ("Headers of modified modules updated so none describes removed behavior") require headers that match the finished code. An agent following vendor.py's own modification recipe would produce a type error.
  Smallest fix:
  - Add the skill entries and enums to the jev `__init__` PURPOSE.
  - Add "and widen `VendorSkillT`" to vendor.py:7 and to the README's "Adding a source" step 3.
  - Change "saved settings" to "results print and callers compare it".
  Spec IDs: FR-16, §12.5, row 23

R-V8 [Minor] [house style: no hardcoded meaningful strings] vidbyte/agents/skills/markdown.py:21 and vendor.py:192 — The SKILL.md delimiter is defined twice
  Evidence:
  - markdown.py:21: `_DELIMITER = "---"`, a module-level constant outside `vidbyte/lib/constants/`.
  - vendor.py:192: `if body.removeprefix(codecs.BOM_UTF8).startswith(b"---"):`
  - github.py:177 compares a tree item's type with the literal `"blob"`.
  Failure: The house style says meaningful literals "live in the repo's existing config destination". `strict-config-dataclasses.md` keeps reusable values in `vidbyte/lib/constants/`. The bare-file detection and the parser must agree on the delimiter, and right now they are two separate literals.
  Smallest fix: Add `SKILL_MARKDOWN_DELIMITER = "---"` to `vidbyte/lib/constants/skills.py`, and use it in markdown.py and, encoded, in vendor.py. Drop `_DELIMITER`.
  Spec IDs: D-12, D-20, row 3

R-V9 [Minor] [verified claim / §12.4] vidbyte/__init__.py:1, vidbyte/agents/__init__.py:1, vidbyte/lib/__init__.py:1, vidbyte/lib/dataclasses/__init__.py:1 — "Every §12.4 item checked" does not hold for the A001 header item
  Evidence:
  - The filtered lint JSON gives `A001 vidbyte/__init__.py 1 """Context Protocol Header {"missing": "ROLE IN CODEBASE:, … TESTS:"}`, and the same for the other three modified package roots.
  - §12.4: "Every new or modified `.py` file has an A001 header with all required fields".
  - S3: "§12.4 checklist: every item checked".
  Failure: The claim is false as written. However, the spec contradicts itself here: NFR-6 and AC-21 pin A001 at exactly 642 (−1), and AGENTS.md says "Do not rewrite untouched code just to make it conform". So the right fix is to the spec text, not the four headers.
  Smallest fix: Do not upgrade the four headers. Amend §12.4 to say "new `.py` files, plus `vidbyte/lib/enums/skills.py`", and correct the S3 claim.
  Spec IDs: §12.4, NFR-6, AC-21

R-V10 [Minor] [principle 5 placement — follow-up, not a repair] vidbyte/agents/skills/local.py:33-41, skills_sh.py:49-56, markdown.py — Two helpers that other features could reuse were written inside the feature package
  Evidence:
  - `LocalSkillResolver.read_capped` is the second copy of the `os.fstat` capped read. The first is `vidbyte/agents/coding_context/root_file.py:93-98`.
  - `SkillsShSkillResolver` reaches into `LocalSkillResolver` for it (skills_sh.py:49, 61).
  - local.py:56 and 62 repeat skills_sh.py:51 and 56 detail for detail (`Could not read {skill_file} ({type(error).__name__}); it is read again on the next run.` and the `TOO_LARGE` text).
  - `SkillMarkdown` is a second SKILL.md frontmatter splitter beside `vidbyte/skills/catalog.py:223-247`.
  Failure: AGENTS.md principle 5 says: "If none exists, create the helper in `vidbyte/lib/` rather than inside the feature that first needs it."

  Spec rows 13 and 14 and D-12 explicitly chose these locations. The user's directive also puts the core skills logic in `vidbyte/agents/skills`. So this is a follow-up for the owner, not a repair item.
  Smallest fix: None in this PR. Follow-up: when a third caller appears (D-12's flip condition), move `read_capped` and `SkillMarkdown` to `vidbyte/lib/`.
  Spec IDs: D-12, rows 13–14

VERIFIED CLAIMS:
1. **Held.** S3: "lint `SDK-LINT: PASS`, no REGRESSED". `PYTHONPATH=$(pwd) python lint/run.py` exits 0 with every rule at or below its baseline.
2. **Held.** S3: "A001 643 → 642, nothing else changed in `lint/baseline.json`". The baseline diff is one line.
3. **Held.** The PR adds no lint finding in any changed file. In the `--all --format json` output, findings in changed paths are all on lines that existed before the PR:
   - A001 on the four root `__init__` files;
   - C008 and C012 on `settings.py` lines 128, 200, 208, 270, and 304;
   - S001 in `vidbyte/__init__.py`;
   - S009 at `alignment/skills.py:202` (`answer.noul`, an unchanged base line).
4. **Held.** S3: "contract current, 615 exports" — `generate-sdk-public-api.py --check` → "current at 3a4cb929… 615 exports".
5. **Held.** S3: "tests unchanged since `d01e0afa`" — `git diff d01e0afa..97c67062 --stat -- tests/` is empty.
6. **Held.** The feature pack plus `tests/test_jev_skill_preload.py`: 373 passed, 1 skipped.
7. **Held.** S3: "longest function `run` 47 lines; largest file `vendor.py` 213" (ast scan).
8. **Held.** Deviation 1: ruff S105 flags `GITHUB_TOKEN_ENV_VAR`. A scratch probe gave `S105 Possible hardcoded password assigned to: "GITHUB_TOKEN_ENV_VAR"`, and `GITHUB_CREDENTIAL_ENV_VAR` passes. Renaming is the only fix without a suppression, so it is acceptable, not a dodge.
9. **Acceptable.** Deviation 6, detail texts kept inside methods. jev-capability-layout.md's check ("top level holds only imports, the class, and `__all__`") holds, and inline user-facing messages match the repo's grain.
10. **Partly held.** Deviation on C002 ("tripped because `version` appears elsewhere"): the two vendor guards alone reach C002's `>= 2` threshold. The fix hid the duplication rather than removing it (R-V2).
11. **Did not hold for one item, and is inconsistent for another.** S3: "§12.4: every item checked". It fails for the 72-column comment item (R-V1), and the A001 item is inconsistent with the spec (R-V9).
12. **Held.** S3: "no `vidbyte/agents/skills/` module imports `vidbyte.agents.jev` or the `vidbyte.agents` root" (grep of the imports).
13. **Held.** S3: "the `_score_skill(index, document, {})` seed is always replaced". Every loaded index ends in exactly one of: the `_unbatched` TOO_LARGE result, a `_failed_batch` result, a scored result, or a re-raise.
14. **Held.** Commit hygiene:
    - 25 of 25 S3 commits carry the trailer and cite W- and FR-/AC-/D- IDs, with one §12.3 row or one cohesive group per commit.
    - `git ls-files | grep -c '\.pyc$'` → 0, and no cache or generated files are in the diff except the required contract regeneration.
    - Commits `5438110e` and `b4164134` are red for `tests/test_jev_skill_preload.py`. This is disclosed, and AGENTS.md has no bisect rule.
15. **Held (7,266 characters; within A009 and S020).** S3: "README 7,268 characters, no `## File Index`".
16. **Done.** §12.3 rows 8, 27, and 30, and §12.5:
    - the package README has every required `## Notes for agents` item;
    - `REPO_MAP.md` has a 4-sentence entry with no file names, and the warning was raised from three to four locations in two places;
    - the agents README has its `skills/` line.
17. **Not verified.** Semgrep 0 findings (no install allowed in this stage). The `run_ci.py` stages were not re-run, because `compileall` writes bytecode; lint, the focused tests, and the contract check were re-run instead.

COMMANDS RUN:
- `git log origin/main..97c67062 --oneline` → 40 commits (25 S3 code commits `ae4d205a..429c77e9`).
- `git diff --stat origin/main...97c67062` → `54 files changed, 8132 insertions(+), 87 deletions(-)`
- `PYTHONPATH=$(pwd) python lint/run.py` → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS` (exit 0)
- `PYTHONPATH=$(pwd) python lint/run.py --all --format json`, then `python -I filter_lint.py lint_all.json changed.txt` → only findings that predate the PR, listed in claim 3.
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 3a4cb9292f62e40afa39478fdea5cf53fd758065 (vidbyte-sdk 0.2.1, 615 exports).`
- `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` → `373 passed, 1 skipped in 4.27s`
- `python -m ruff check <changed non-test .py> --config lint/ruff.toml --select I001 --no-cache` → `All checks passed!`
- The 72-column awk check from comment-format.md over the 13 new modules plus `lib/constants/skills.py` and `lib/dataclasses/skills.py` → 53 of 222 comment lines over 72 columns. `git blame` over the modified files → 9 more PR-authored lines.
- `python -m ruff check <scratch probe.py> --select S105 --no-cache` → `S105 Possible hardcoded password assigned to: "GITHUB_TOKEN_ENV_VAR"` (the `GITHUB_CREDENTIAL_ENV_VAR` line passes).
- The ast function scan (`funcs.py`) → max `run` 47 lines. Helpers with more than 3 positional arguments: `_refused` (5), `_raw_document` (4), `_classify` (4). AGENTS.md has no argument-count rule, so these are not filed.
- `git diff d01e0afa..97c67062 --stat -- tests/` → empty.
- `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → the worktree path.
