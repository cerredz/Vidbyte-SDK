# S3 report: implementer, prebuilt agent tools

Spec: `docs/spec/prebuilt-agent-tools/spec.md` r5 (built on r4, finished on r5) · Branch `feat/prebuilt-agent-tools` · Test baseline `69a1970a` (first `bc238128`) · Start HEAD `129785dd` · Date 2026-10-14

**Outcome: DONE.** Every §12.3 row is built and committed, and every gate passes. The branch is pushed. Draft PR: https://github.com/cerredz/Vidbyte-SDK/pull/1072. The spec frontmatter reads `status: implemented` with the `pr:` URL, and §17 has the S3 row and the implementation deviations list.

The first pass stopped BLOCKED on two `intersect_lists` contract tests (§4). The orchestrator ruled that the spec was right. S2 fixed the test data in `0708d57d`, and the spec author resolved the NFR-7 gap in r5 (EC-46, `ce32c0a6`). The continuation then added the r5 row-40 README paragraph, ran every gate, pushed, and opened the PR.

`docs/spec/prebuilt-agent-tools/pipeline.md` belongs to the orchestrator. This stage never staged or edited it.

## 1. Commits made by this stage

Phase order follows §12.6.
- Enums and constants (rows 1–5): `b4802c5a`, `71357f78`, `ec661419`, `903c3864`, `4b560403`.
- Shared helpers (row 6): `a0d593ef`, `7f05a20a`, then the fixes `33a60a99` and `7ea64f63`.
- Category modules (rows 8–38), one commit each: `a5f5e687` text_counting, `ad1332fe` descriptive_statistics, `751d6db2` seeded_random, `848f472c` finance, `b4d75a2b` unit_conversion, `db1260ba` dates, `ea45babb` scheduling, `19720f60` exact_arithmetic, `5b9c1cc8` number_theory, `57106b8d` number_formatting, `f8fcbfa7` probability, `b08fb9a5` timestamps_durations, `f50dc96e` text_transform, `77ffc5b2` unicode, `e71e5a5b` regex, `9584fb1c` text_comparison, `16bd8f84` json_data, `4d89dbcd` json_records, `f3befb42` csv_tables, `6a4b2c1e` structured_formats, `0760e66f` encoding, `7670d65c` hashing, `272fae0e` geometry, `2b79762e` bits_bytes, `166904ec` markdown_html, `ac65c44f` text_extraction, `78489bfe` code_analysis, `e689ce78` network_addresses, `17de5aee` identifiers, `44fd4cba` lists, `b0e8b067` graphs.
- Exports and toolset (rows 39, 41, 42): `a04e8dcd`, `c07d63d2`, `c6247eaa`.
- Documentation (rows 40, 43, 44): `3ad3e2bc`, `a75b727d`, `64fb84da`, and the r5 EC-46 README paragraph `063d21ff`.
- Lint follow-ups: `c76b998f` and `aa0e1fd9` for C005 (§5 item 2), and `4b163520` for a 73-column comment.
- Pipeline records: `3b783658` (this report, first version), `b3855ea6` (draft PR in the frontmatter), `68dfb8b3` (implementation proof), and a last commit that updates this report.

## 2. What was built

- 39 new files, exactly the §8.4 plan:
  - 4 in `vidbyte/lib/`: `enums/prebuilt_tools.py` (58 enums), `enums/units.py` (10 enums), `constants/prebuilt_tools.py`, and `constants/units.py`.
  - 34 in `vidbyte/tools/builtins/prebuilt/`: the 31 category modules, `__init__.py`, `_support.py`, and `README.md`.
  - 1 in `vidbyte/tools/toolsets/`: `prebuilt.py`.
- No D-18 split module was needed. The largest module, `json_data.py`, has 582 lines.
- 4 modified files:
  - `vidbyte/lib/enums/__init__.py` exports the 68 enums.
  - `vidbyte/tools/toolsets/__init__.py` exports `PrebuiltTools`.
  - `vidbyte/tools/README.md` gains `## Prebuilt Tools` and Key Modules lines.
  - `REPO_MAP.md` updates its builtins and toolsets entries.
- The library has 265 tools in 31 categories. Nothing else was added: no dataclass, error class, dependency, config key, CLI command, or root export.
- These files are byte-identical to `129785dd`: `vidbyte/__init__.py`, `vidbyte/tools/builtins/__init__.py`, `contracts/sdk-public-api.json`, `pyproject.toml`, `lint/`, `scripts/`, `.semgrep/`, `.github/`, `function_tool.py`, and `catalog.py`.
- `git diff 69a1970a HEAD -- tests` is empty, so this stage changed no test, fixture, or test config.

## 3. Final gate results (at `063d21ff`, before the doc-only record commits)

- Pack, `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools`: `4310 passed in 20.54s`.
- Neighbouring suites (`tests/test_tools_catalog.py`, `tests/test_function_tool_parameter_types.py`, `tests/test_tool_core.py`, `tests/features/coding_agent`): `338 passed, 12 skipped in 15.05s`, the same as the baseline.
- `PYTHONPATH=$(pwd) python lint/run.py` exits 0 with `SDK-LINT: PASS`. There is no REGRESSED rule. The IMPROVED rules (A002, C011, C012, S001, S010, S017, S025, S061) were IMPROVED before this change too (§11). No baseline was changed.
- Semgrep `typed-mapping-boundary-policy.yml`: `Ran 1 rule on 931 files: 0 findings.`
- `python scripts/generate-sdk-public-api.py --check`: `contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).`
- Source stage, `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`: `SDK-LINT: PASS`, `8325 passed, 13 skipped in 57.82s`, `CI passed.`
- Package stage, `env -u PYTHONPATH python scripts/run_ci.py --stage package`: `Installed vidbyte-sdk 0.2.1 passed smoke checks.`, `CI passed.`
- Push: `* [new branch] feat/prebuilt-agent-tools -> feat/prebuilt-agent-tools`, with upstream set. `gh pr view 1072` reports `isDraft: true`, `state: OPEN`, and base `main`.

## 4. The first-pass blocker and how it was resolved

Appendix A.24 types `lists` as `list[TextList] len 2..PREBUILT_MAX_LISTS`, so each item of `lists` is itself a list. `tests/features/prebuilt_tools/prebuilt_parameter_data.py:257` gave each item a string cap of 10,000 characters instead. As a result, `test_tool_schema_matches_its_appendix_row[intersect_lists]` and `test_one_over_cap_argument_fails_validation_naming_the_parameter[intersect_lists]` failed against a signature that follows the row.

The orchestrator ruled that the spec was right (S3-3). S2 rebound the data to nested lists in `0708d57d`. The implementation did not change.

## 5. Spec issues raised, and implementation deviations

1. **NFR-7 on repetitive input (S3-1).** On highly repetitive input, `diff_words` measured 14.6–22.4 s at 2,000 tokens. `closest_string_matches` measured 3.1–4.9 s at 1,000 candidates, and 87 s with casefolded ligatures. r5 accepts this slowness as EC-46, beside EC-10, and r5 found that `unified_diff_text` is slow on such input too. Commit `063d21ff` adds the row-40 README paragraph about it. No cap, tool, or test changed.
2. **The `seeded_weighted_choice` output bound (S3-2).** r5 records the bound in EC-45 and in the row: at most 10,000,000 characters. No code changed.
3. **Implementation deviations.** The deviations are listed in spec §17 under "Implementation deviations (S3)":
   - C005 renames of private finance and Poisson locals.
   - The `split_lines` and `line_and_column` helpers, and the JSON hook partials, in `_support.py`.
   - Stricter JSON reading: integers longer than 4,300 digits and non-finite floats are refused, `nesting_level` skips scalar children, and the weekday prefix is anchored.
   - A nested `ConfigParser` subclass for key case.
   - A Base64 reader duplicated in two modules.
   - Choices that the rows left open.

   None of them changes a tool, parameter, return key, default, or cap.

## 6. §12.4 and §12.5 completeness

- **Headers, imports, size, and comments.** Every new `.py` file has the A001 header and `from __future__ import annotations`, and none is longer than 800 lines. No comment line is wider than 72 columns, checked with the §12.4 `awk` command.
- **Banned code.** A sweep found none of these in code: `str(exc)`, `from None`, a clock read, `fromtimestamp`, `strptime`, `eval`, `exec`, `compile`, `open`, `os`, `subprocess`, `socket`, `print`, or a suppression comment.
- **Hashes and function names.** md5 and sha1 use `usedforsecurity=False`. No function name has a C006 or C008 prefix.
- **Folder README.** It is 22,371 characters. Its File Index lists all 33 `.py` children, and S020, A009, and C015 pass.
- **Other docs.** The tools README is 8,388 characters, and the `REPO_MAP.md` entries name no files.
- **§12.5 actions.** All are done (rows 3, 42, 40, 43, and 44). This stage edited no `llms.txt`, `artifacts/`, contract, or baseline file.
- **§6.2 Proof column.** S2 had filled every AC row, so the proof commit left the column unchanged.

## 7. Environment notes

- **Pytest hangs.** On Windows, pytest sometimes hangs idle when several runs share the machine. A rerun with `-p no:cacheprovider` finishes in seconds.
- **Semgrep.** It is not on the default PATH, so it runs from the scratchpad virtual environment, with that environment's `Scripts` folder first on a POSIX `PATH`.
- **Git warnings.** The LF to CRLF warnings from git are harmless.
