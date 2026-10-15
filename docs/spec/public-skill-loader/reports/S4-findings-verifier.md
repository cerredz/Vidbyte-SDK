# S4 findings verifier: public-skill-loader

Inputs: the three lens reviews (conformance, conventions, engineering), spec r3, test-plan, request.md, the S1 "Answers to consumer requirements", the S3 report's tricky parts, AGENTS.md, the field-guide entries `strict-config-dataclasses.md` and `comment-format.md`, agentic-engineering `feature_test_packs.md`, and house style.

Diff: `c9d31a7f...c691c176`. Local HEAD moved to `93144015` during this stage: the orchestrator committed the lens reviews, which is docs only and not under review.

Output: `docs/spec/public-skill-loader/review.md`.

Verdict: **MERGEABLE AFTER FIXES**. Confirmed: 0 Blocker, 1 Major. Minor: 6. Refuted: 0. Downgraded: 1.

## Merge map

| Original | Lens | Proposed | Merged | Final | Disposition |
|---|---|---|---|---|---|
| R-E1 | engineering | Major | R-1 | Major | CONFIRMED |
| R-C1 | conformance | Major | R-2 | Minor | DOWNGRADED (spec-text clarity) |
| R-V1 | conventions | Minor | R-3 | Minor | passed through · trivial |
| R-V4 | conventions | Minor | R-4 | Minor | passed through · trivial |
| R-E2 | engineering | Minor | R-5 | Minor | passed through · follow-up (test edit) |
| R-V2 | conventions | Minor | R-6 | Minor | passed through · follow-up (test edits) |
| R-V3 | conventions | Minor | R-7 | Minor | passed through · follow-up |

No two findings share a root cause.

- R-C1 and R-V4 both touch `loader.py:9`, but they are different defects. R-C1 is about the iterable promise. R-V4 is about the "settings order" and "every run" wording.
- R-V1 and R-C1 both touch the both-doors rule, but they differ too. R-V1 is about routing the maintainer to the twin. R-C1 concerns argument shapes outside INV-18's scope.

## Verifications (my own evidence)

### R-1 (engineering R-E1): the release test pins 0.3.1 permanently — CONFIRMED Major

- **Code.** `test_public_skill_loader_release.py:35` reads `RELEASE_VERSION = "0.3.1"`, and `:113` reads `assert read(monkeypatch) == RELEASE_VERSION, place`. The header at `:7` says "The next bump changes RELEASE_VERSION".
- **Executed.** I built a `git archive c691c176 vidbyte tests/__init__.py tests/features/public_skill_loader pyproject.toml README.md llms.txt .github/ISSUE_TEMPLATE/bug_report.yml` copy in scratch (`s4verify/bump`) and moved the eight literals from 0.3.1 to 0.3.2 with `sed` (grep confirms `8` places). Then I ran `PYTHONPATH=<copy> python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader/test_public_skill_loader_release.py`:
  ```
  FAILED ...[MCP client clientInfo version]
  FAILED ...[README pinned install line]
  FAILED ...[llms.txt version sentence]
  FAILED ...[bug report version placeholder]
  8 failed in 0.38s
  ```
- **Precedent.** I ran `git show --stat` on `90f36272` (0.2.0), `29fbfd28` (0.2.1), and `a7ed9cde` (0.3.0).
  - 0.2.0 and 0.3.0 touch no test.
  - 0.2.1 touches `tests/test_codex_tools.py`, but none of its added lines mention `version` or `0.2`. That is the openai-codex change, not a version pin.
  - `git grep -n -E '__version__ *==|RELEASE_VERSION|"0\.[23]\.[0-9]"' c9d31a7f -- tests` finds nothing. So this PR adds the repo's first release-pinned test.
- **The fix is proven, and it loses nothing.**
  - I added a scratch test to the copy only. It imports `PLACES` and `pyproject_version` and asserts each place equals pyproject's version and that the version is at least `(0, 3, 1)`.
    - On the bumped copy: `8 passed in 0.11s`.
    - With `llms.txt` reverted to 0.3.1: `1 failed, 7 passed`. The consistency guard survives.
  - At this head, the literal 0.3.1 is still proven. `scripts/generate-sdk-public-api.py:95` puts `version {old!r} -> {new!r}` into `--check`'s drift list, and the committed contract reads `"version": "0.3.1"` (`contracts/sdk-public-api.json:5`). So a passing `--check` means pyproject reads 0.3.1, and the durable test makes the other seven equal it.
- **Spec check.** AC-11 says "all nine places named in INV-16 read `0.3.1`", and its Proof names this test. The test therefore does **not** contradict a spec ID. The defect is in AC-11's proof design: a PR-time fact was made a permanent test. Doctrine: `feature_test_packs.md`, "the smallest durable behavior boundary".
- **Mitigation, weighed.** The repo's bump convention ("grep for the old version; miss none", request.md §C) would find line 35 at the next bump. That makes the failure findable, but every release PR then has to edit a skill-loader feature test. None of the three precedents did so.
- **Calibration.** Major. It will certainly surface in the next release PR's CI, and a reviewer would flag a release literal in a feature pack. It is not a Blocker, because it produces no wrong result today and the test can fail.
- **Fix routing.** Spec-text first (AC-11's Proof column), then an orchestrator-approved test edit. The alternative is that the orchestrator waives it to a follow-up for the next release PR.

### R-2 (conformance R-C1): "any iterable" vs `isinstance(entries, Iterable)` — DOWNGRADED to Minor

- **Executed** `s4verify/probe_rc1.py` from an empty folder with `PYTHONPATH=<worktree>`:
  ```
  glossary check: iter(GetItemOnly([inl])) -> True | isinstance(GetItemOnly(...), Iterable) -> False
  GetItemOnly([inl])           public: ConfigurationError details={'entries_type': 'GetItemOnly'}
                               jev:    ACCEPT ('InlineSkill',)
  IterRaisesType()             public: !! TypeError: iter boom
                               jev:    ConfigurationError details={}
  IterReturnsNonIterator()     public: !! TypeError: iter() returned non-iterator of type 'int'
                               jev:    ConfigurationError details={}
  IterRaisesRuntime()          public: !! RuntimeError: iter boom
                               jev:    !! RuntimeError: iter boom
  gen_raises()                 public: !! ValueError: gen boom
                               jev:    !! ValueError: gen boom
  [inl] (control)              public: ACCEPT ('InlineSkill',)
  ```
  Also: `numpy 0-d array -> TypeError iteration over a 0-d array`; `numpy 1-d object array of entries -> ('InlineSkill',)`; and a `__getitem__`-only class registered with `Sequence.register` gives `('InlineSkill',)`.
- **Typed-caller check.** I ran `python -m mypy --strict --follow-imports=silent` on a scratch consumer:
  ```
  typed_consumer.py:23: error: Argument 1 to "SkillLoader" has incompatible type "GetItemOnly"; expected "Sequence[SkillEntry | SkillDocument]"  [arg-type]
  typed_consumer.py:24: error: Argument 1 to "SkillLoader" has incompatible type "IterRaisesType"; expected "Sequence[SkillEntry | SkillDocument]"  [arg-type]
  typed_consumer.py:25: error: Argument 1 to "SkillLoader" has incompatible type "Generator[InlineSkill, None, None]"; ...  [arg-type]
  Found 3 errors in 1 file
  ```
  Lines 21–22, `list[SkillEntry]` and a tuple, produce no error.
- **Spec reading.**
  - INV-2 says "takes any iterable that is not a `str` or `bytes`". §9.2 row 1 says "any iterable except `str` or `bytes` is accepted … A violation raises `ConfigurationError`", and S1 answer 1 repeats it.
  - D-14, §8.5, and row 2(b) prescribe `isinstance(entries, Iterable) and not isinstance(entries, (str, bytes))` verbatim. §12.4 says `__init__` contains no `raise`, and its only new logic is that one expression.
  - So the spec defines "iterable" operationally as the `collections.abc.Iterable` check, and its prose is broader than its own definition.
  - S3 followed the most specific instruction and noted the reading in its report (tricky part 1), but not in §17.
- **Existing guards.**
  - The public annotation (`Sequence[...]`) excludes both corners for typed callers, as the mypy output above shows.
  - Every `Sequence`, nominal or registered, is an `Iterable` instance and passes the guard.
- **"Not as a crash"** (request.md §C) concerns per-entry unavailability during resolution, not a caller object whose own iteration fails. The spec's stance on such caller or programming errors is propagation unchanged (INV-6, EC-18).
- **Calibration.**
  - No behavior should change: a code fix would breach §12.4 and row 2(b), and it would hide a caller's own `TypeError`.
  - No typed caller, the CLI included, can reach either corner.
  - What remains is an inexact sentence in the contract text. A human reviewer of the public API might ask for the sentence to be made exact, but would not ask for different behavior.
  - Hence Minor, trivial, spec-text. Its fix names both places the CLI pipeline resumes from: §9.2 row 1 and S1 answer 1.

### Minors (passed through; spot-checked)

- **R-3 (R-V1).** `sed -n 14p vidbyte/lib/dataclasses/skills.py` shows COMMON MODIFICATION PATTERNS covers sources and fields only. `grep -n -E "_normalized_skills|jev/settings"` over `skills.py`, `loader.py`, and the skills README returns nothing. Held.
- **R-4 (R-V4).** Grep finds `loader.py:9` "on every run" and "settings order whatever the grouping.", README `:23` "on the next run" and "later runs", and README `:48` "on every run". The same phrases exist at base (`git show c9d31a7f:…`). So this is stale wording on lines the PR edited, not wording it introduced. Held.
- **R-5 (R-E2).** In-memory probe against `DOC_RULES["REPO_MAP skills entry"]`:
  ```
  A heading kept + stale  : guard passes=True | stale phrase caught=True | section starts "\nand today JevAgent's skill preload is its on"
  B heading level changed : guard passes=True | stale phrase caught=False | section starts '# Vidbyte SDK Repository Map\n\n> **This file i'
  C heading path changed  : guard passes=True | stale phrase caught=False | section starts '# Vidbyte SDK Repository Map\n\n> **This file i'
  ```
  Held. It is Minor, not a Blocker-class "test that cannot fail", because it fails correctly today. It is a test edit, so it is a follow-up.
- **R-6 (R-V2).** `awk 'length($0) > 72 && $0 ~ /^[[:space:]]*#/'` per pack file gives conftest 8, acceptance 11, both_doors 9, boundary 13, contract 9, docs 10, release 3, security 6, for a total of 69. Over the production `+` lines of the diff: 0. Held.
- **R-7 (R-V3).** `ls tests/features/public_skill_loader/` shows FEATURE.md, conftest.py, and 7 modules, with no README. Across `tests/features/`, 9 of 17 packs have a README, and the 8 without are the seven `jev_*` packs plus this one. Held, with a corrected precedent count. The reviewer's "7 of the 8 packs added since 2026-10-07" is true for that window, but the sibling the pack copied (`jev_skills_preload`) has none.

## Adjudicated disagreements

1. **R-C1: conformance (Major, a contract defect) against engineering (Verified claim 19, "caller bugs propagate", not a defect).** Both are partly right.
   - Engineering is right about the code: it is correct, follows §8.5, and propagating the caller's own iteration error matches INV-6 and EC-18.
   - Conformance is right that the prose promise ("any iterable") is literally broader than the guard.
   - The gap is in the text only. It cannot be reached by any argument the annotation admits, so it is clarity, not a Major.
   - On the briefing's question, a human reviewer of a public API would object only to the text, and only as a precision nit.
   - Conformance rated it Major under its own briefing ("any gap between §9.2 and the code is Major"). My calibration uses the S4 rubric: Major means it would surface in human review or production, which this does not.
2. **R-E1 severity.** Weighing Major against follow-up: it surfaces with certainty at the next bump, and the durable fix proves exactly as much at this head (via `--check`). So I kept it Major. It is the only open line, and the repair loop cannot act on it alone: it needs a spec-text edit to AC-11's Proof column, then an approved test edit, or a waiver.

## Severity blind spots checked (no `[verifier]` finding)

- **One `ConfigurationError` class.** `git grep -n "^class ConfigurationError" -- vidbyte` → `vidbyte/lib/errors/base.py:284` only. So the CLI's `except vidbyte.ConfigurationError` catches the entry constructors' errors.
- **Contract shape.** `contracts/sdk-public-api.json` lists names only, with no members or signatures. So `entries`, `memory`, and `resolvers` are not frozen into the contract (NG-15 holds).
- **Import cost and hazard.** At base, `vidbyte/agents/jev/alignment/skills.py:37` already imports `vidbyte.agents.skills.loader`, and the root already imports JEV. So the root export adds no new import-time module.
- **`tomllib` in the release test.** `pyproject.toml:10` reads `requires-python = ">=3.11"`. There is no 3.10 hazard.
- **CRLF.** The release and docs tests use `Path.read_text`, which converts newlines, so the `^…$` regexes hold on Windows working copies. Source files are CRLF in the working copy (`core.autocrlf=true`) and LF in the index.
- **INV-12 path.** The Jev door's normalized tuple always satisfies `SkillEntries`: same element types, same exact-name uniqueness. The area suite passes unedited.

## Commands run (final lines)

- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader tests/features/jev_skills_preload tests/test_jev_skill_preload.py` → `493 passed, 1 skipped in 5.65s`
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 56541481fbb32624aa70ff26b9f4feeb496ea273 (vidbyte-sdk 0.3.1, 642 exports).`
- `PYTHONPATH=$(pwd) python lint/run.py` → `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` / `exit=0`
- §4 snippet (extracted with `awk` from spec.md, run from an empty scratch folder) → `house-review loaded 22 bytes` / `pdf not_found False` / `rejected: ['house-review']` / `exit=0`
- `probe_rc1.py`, the mypy consumer, the bump simulation, the durable-variant run, and the REPO_MAP probe → outputs quoted above.
- `git status --short` was empty before and after. All probes and copies live under the scratchpad's `s4verify/`. The worktree was written only for `review.md` and this report.
