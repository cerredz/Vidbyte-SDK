# S3 report: implementer, prebuilt agent tools

Spec: `docs/spec/prebuilt-agent-tools/spec.md` r4 · Branch `feat/prebuilt-agent-tools` · Base `bc238128` (test tree) · Start HEAD `129785dd` · Date 2026-10-14

**Outcome: BLOCKED.** Every §12.3 row is built and committed, but two pack tests contradict Appendix A row `intersect_lists` (§4 below). Nothing is pushed, no draft PR exists, and the spec frontmatter (`status`, `pr`), the §6.2 Proof column, and §17 are unchanged. Those steps wait for the continuation (§7).

`docs/spec/prebuilt-agent-tools/pipeline.md` has an uncommitted change that belongs to the orchestrator. It was neither staged nor touched.

## 1. Commits made by this stage

Phase order follows §12.6. Enums and constants (rows 1–5): `b4802c5a`, `71357f78`, `ec661419`, `903c3864`, `4b560403`. Shared helpers (row 6): `a0d593ef`, `7f05a20a`, then fixes `33a60a99` and `7ea64f63`. Category modules (rows 8–38), one commit each: `a5f5e687` text_counting, `ad1332fe` descriptive_statistics, `751d6db2` seeded_random, `848f472c` finance, `b4d75a2b` unit_conversion, `db1260ba` dates, `ea45babb` scheduling, `19720f60` exact_arithmetic, `5b9c1cc8` number_theory, `57106b8d` number_formatting, `f8fcbfa7` probability, `b08fb9a5` timestamps_durations, `f50dc96e` text_transform, `77ffc5b2` unicode, `e71e5a5b` regex, `9584fb1c` text_comparison, `16bd8f84` json_data, `4d89dbcd` json_records, `f3befb42` csv_tables, `6a4b2c1e` structured_formats, `0760e66f` encoding, `7670d65c` hashing, `272fae0e` geometry, `2b79762e` bits_bytes, `166904ec` markdown_html, `ac65c44f` text_extraction, `78489bfe` code_analysis, `e689ce78` network_addresses, `17de5aee` identifiers, `44fd4cba` lists, `b0e8b067` graphs. Exports and toolset (rows 39, 41, 42): `a04e8dcd`, `c07d63d2`, `c6247eaa`. Documentation (rows 40, 43, 44): `3ad3e2bc`, `a75b727d`, `64fb84da`. Lint follow-ups: `c76b998f`, `aa0e1fd9` (C005, §5 item 2) and `4b163520` (a 73-column comment). A last commit adds this report.

## 2. What was built

- 39 new files, exactly the §8.4 plan: 4 in `vidbyte/lib/` (`enums/prebuilt_tools.py` with 58 enums, `enums/units.py` with 10, `constants/prebuilt_tools.py`, `constants/units.py`), 34 in `vidbyte/tools/builtins/prebuilt/` (31 category modules, `__init__.py`, `_support.py`, `README.md`), and `vidbyte/tools/toolsets/prebuilt.py`. No D-18 split module was needed; the largest module is `json_data.py` at 582 lines.
- 4 modified files: `vidbyte/lib/enums/__init__.py` (68 exports), `vidbyte/tools/toolsets/__init__.py` (`PrebuiltTools`), `vidbyte/tools/README.md` (`## Prebuilt Tools` and Key Modules lines), and `REPO_MAP.md` (builtins and toolsets entries).
- 265 tools in 31 categories. 0 dataclasses, 0 error classes, 0 dependencies, 0 config keys, 0 CLI commands, 0 root exports. `vidbyte/__init__.py`, `vidbyte/tools/builtins/__init__.py`, `contracts/sdk-public-api.json`, `pyproject.toml`, `lint/`, `scripts/`, `.semgrep/`, `.github/`, `function_tool.py`, and `catalog.py` are byte-identical to `129785dd`.
- `git diff bc238128 HEAD -- tests` is empty: no test, fixture, or test config was changed.

## 3. Gate results at `4b163520`

- Pack, `PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools`: `2 failed, 4308 passed in 21.00s`. Both failures are `[intersect_lists]` (§4).
- Neighbouring suites (catalog, parameter types, tool core, coding_agent): `338 passed, 12 skipped in 14.93s`, the same as the baseline.
- `PYTHONPATH=$(pwd) python lint/run.py`: `SDK-LINT: PASS`. The only IMPROVED rules are the pre-existing ones listed in §11 (A002, C011, C012, S001, S010, S017, S025, S061). No baseline was changed.
- Semgrep `typed-mapping-boundary-policy.yml`: `Ran 1 rule on 931 files: 0 findings.`
- `python scripts/generate-sdk-public-api.py --check`: `contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).`
- Source stage, `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`: `SDK-LINT: PASS`, then `2 failed, 8323 passed, 13 skipped in 55.06s` and `CI failed: Command failed with exit code 1: ... python.exe -m pytest`. The two failures are the same `[intersect_lists]` cases.
- Package stage, `env -u PYTHONPATH python scripts/run_ci.py --stage package`: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` then `CI passed.`

## 4. Blocker: `intersect_lists` parameter data contradicts Appendix A

Appendix A.24 (spec line 1491) gives `lists: list[TextList] len 2..PREBUILT_MAX_LISTS`, so each item of `lists` is itself a list of strings (a `TextList` holds at most 10,000 items of at most 10,000 characters each). The row tests in the pack send lists of lists, and they pass.

`tests/features/prebuilt_tools/prebuilt_parameter_data.py:257` reads:

```python
'intersect_lists': (('lists', 'array', 100, 10000, REQUIRED), ('case_sensitive', 'boolean', None, None, True)),
```

The fourth field is the item string cap, which treats each item of `lists` as a string of at most 10,000 characters. Two tests read that entry:
- `test_prebuilt_toolset_contract.py::test_tool_schema_matches_its_appendix_row[intersect_lists]` fails with `lists: item maxLength is None, Appendix A says 10000`.
- `test_prebuilt_model_facing_contract.py::test_one_over_cap_argument_fails_validation_naming_the_parameter[intersect_lists]` sends `["1" * 10001]` and gets `lists.0: Input should be a valid array`, not a length error.

No signature satisfies both the row (and its passing row tests) and this entry, short of editing a test file or changing the parameter type, and both of those need approval. The implementation follows the spec row: each inner list is capped at 10,000 items of at most 10,000 characters, and a total above `PREBUILT_MAX_LIST_ITEMS` across all lists is checked in the body and fails as error(`lists`). Suggested S2 fix: set the item cap of that entry to `None`, or teach both tests about nested arrays (inner `maxItems` 10,000, inner item `maxLength` 10,000).

## 5. Spec issues and implementation deviations

1. **NFR-7 (P1, at most 2 s per call) fails on adversarial repetitive input.** I measured `diff_words` at 14.6–22.4 s with 2,000 tokens per side (`"a b "` against `"a c "` repeated, and `"x "` against `"y "` repeated). I measured `closest_string_matches` at 3.1–3.5 s for 1,000 candidates of `"ab"*50` against `"ac"*50`, and at 3.6–4.9 s with casefolding. The same shape with `"ﬃ"*100` against `"ﬄ"*100` and casefolding took 87 s, because casefolding triples each string's length. The rows require `difflib.SequenceMatcher(autojunk=False)`, which is quadratic on such input, and §9.2 item 7 requires casefolding. No pack test covers this. The spec must choose one of three options: accept it as a documented edge case like EC-10, lower the caps, or fold per code point before matching.
2. **C005 renames.** Lint C005 (cost-arithmetic-site-parity) matches any `*` operand whose name contains `rate` or `price`, so it fired on interest and Poisson math. Commit `c76b998f` renamed finance locals (`monthly_rate`→`monthly_interest`, `rate`→`guess` in IRR, `rate`→`yearly` in compounding). Commit `aa0e1fd9` renamed `_poisson_mass(rate)`→`mean`. No parameter or output changed. The spec's naming checklist lists A002 and A007 but not C005.
3. **`_support.py` beyond row 6.** I added two shared helpers, `split_lines` and `line_and_column`, which several categories use for line and position output. `parse_json_text` passes the private helpers `_reject_json_constant` and `_read_json_float` to `json.loads` hooks through `functools.partial`. It also refuses integers longer than 4,300 digits (catching the `ValueError`, never changing `sys.set_int_max_str_digits`) and non-finite floats such as `1e400` as error(parameter). `nesting_level` skips scalar children, so the 5 MB peak-memory test for `format_json` holds. The weekday prefix pattern is anchored with `\A`.
4. **Nested classes.** `text_transform.py` and `markdown_html.py` use private nested `HTMLParser` subclasses, as rows 20 and 35 say. `structured_formats.py` also has a private nested `ConfigParser` subclass that overrides `optionxform` to keep key case (the row says `optionxform = str`). The subclass avoids assigning to a method on an instance. The §8.4 class count of 101 does not count nested classes.
5. **Choices the rows left open.** The toolset treats a bare non-iterable `categories` value as one bad value. The implementer chose the shapes of the reference tables: comment syntax per language, English number words, ordinal irregulars, and duration words including plurals. `markdown_html` adds a column-name check against the output cap. An `AssertionError` from `HTMLParser` on `<![foo[` is suppressed, so parsing stops there. `strip_html_tags` treats unknown marked sections as comments. `descriptive_statistics` uses exact integer-scaled arithmetic. `probability` builds `NormalDist` results from an exact standard score. Errors from `get_python_function_signature`, `fill_text_template`, and the cycle checks shorten echoed names, so a message never repeats more than 100 characters of input. `fiscal_quarter` may return year 10000. `levenshtein_distance` uses Myers' bit-parallel algorithm. Unicode normalization runs once per distinct character, which avoids a slow path in Python 3.11.
6. **Duplication.** The tolerant Base64 reader exists in both `encoding.py` and `hashing.py`. It could move to `_support.py` in a follow-up.
7. **Uncapped output.** `seeded_weighted_choice` can return about 10 million characters (1,000 picks of 10,000-character items), because its row sets no output cap and INV-20 does not list it. With subnormal weight totals, a zero-weight item can be picked, so its description makes no claim that it cannot.

## 6. §12.4 and §12.5 completeness

All new `.py` files have the A001 header and `from __future__ import annotations`, and every file is at most 800 lines. Every comment line is at most 72 columns (checked with the §12.4 `awk` command). The sweep found no `str(exc)`, `from None`, clock read, `fromtimestamp`, `strptime`, `eval`/`exec`/`compile`, `open`, `os`, `subprocess`, `socket`, `print`, or suppression comment in code. md5 and sha1 use `usedforsecurity=False`. No function name starts with a C006 or C008 prefix. The folder README is 21,565 characters and its File Index lists all 33 `.py` children. The tools README is 8,388 characters. The two `REPO_MAP.md` entries name no files. All §12.5 actions are done (rows 3, 42, 40, 43, 44). The test pack belongs to S2. No `llms.txt`, `artifacts/`, contract, or baseline file was edited.

## 7. What the continuation must do once S2 fixes the parameter data

1. Rerun the pack, the neighbouring suites, lint, semgrep, the public API check, the source stage (with `PYTHONPATH`), and the package stage (without it). Quote the final lines of each.
2. Push for the first time with `git push -u origin feat/prebuilt-agent-tools`.
3. Open the draft PR with `gh pr create --base main --head feat/prebuilt-agent-tools --draft --title "[WIP] feat: A library of 250+ prebuilt agent tools in vidbyte-sdk"` and the placeholder body.
4. Set `pr:` and `status: implemented` in the spec frontmatter. Commit with `docs(spec): record draft PR for prebuilt-agent-tools`, then push.
5. Make the proof commit, `docs(spec): record implementation proof for prebuilt-agent-tools`, holding the §6.2 Proof column, a §17 row `r4 | <date> | S3 implement | ...`, and an "Implementation deviations" list taken from §5 above. Then update this report and push.

## 8. Environment notes

- On Windows, pytest sometimes hangs idle when several runs share the machine. A rerun with `-p no:cacheprovider` finishes in seconds. One hung run of mine was killed.
- Semgrep is not on the default PATH. Run it from the scratchpad virtual environment by putting its `Scripts` folder first on a POSIX `PATH`.
- The LF to CRLF warnings from git are harmless.
