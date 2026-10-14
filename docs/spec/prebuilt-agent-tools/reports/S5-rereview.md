LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every R-1..R-13 and M-1..M-4 repair holds against its own reproducer, but the R-6 fix added a quadratic TOML pre-scan (R-C1), and `parse_data_size` still lets `decimal.InvalidOperation` escape (R-C2); both fixes are small and local.

Reviewed: branch `feat/prebuilt-agent-tools`, HEAD `8a71a331` (clean), S3 head `0fd73086`, merge-base `8387d666`. Python 3.11.0. I was the only reviewer this round, so findings outside this lens are in scope and tagged `[out-of-lens]` (none were needed).

WHAT THE IMPLEMENTATION GETS RIGHT

- Every S4 reproducer is now fast or refused:
  - R-1 headings at 1M chars: 0.096 s.
  - R-2 numbers and money at 1M chars: 0.251 s and 0.356 s.
  - R-6 dotted keys, all three forms at 1M chars: about 0.03 s.
  - R-7 `.//a`x7 on the 60-deep chain: refused in 0.29 s. `b[1]` over 249,998 siblings: refused in 0.41 s.
  - R-8 open-markup tails: at most 0.175 s.
  - R-9 EC-49 patch: refused at "operation 49 (remove)" in 0.617 s.
  - R-10 1M haystack: 0.269 s, or 0.691 s ignoring case.
- The error contract holds at every repaired site. Each new message is in INV-15 form and names a real parameter. The four name-listing sites cap at `PREBUILT_MAX_REPORTED_NAMES` (20). No echoed user text runs longer than 100 characters (see judgment call 1).
- The boundaries are intact:
  - 39 files added and 4 modified outside docs/tests, exactly as §8.4 and §12.3 plan. The repair added no files.
  - `lint/baseline.json` is untouched. `python lint/run.py` gives `SDK-LINT: PASS`.
  - Tests changed since S3 only in the S2 commit c9710ed2, which made them stricter.
  - No file is over 613 lines.
  - An AST scan finds no same-class two-hop helper chains and no nested defs.
- Every R-12 reproducer gives the same result under a hostile host context and under a no-trap one. The hostile context was prec 3, Emax 5, Emin -5, capitals 0, clamp 1, with every trap on. `decimal_context(precision)` always sets ROUND_HALF_EVEN. `copy_negate` and `copy_abs` replace unary minus and `abs`. The geometry seconds text is now formatted inside the context.

FINDINGS (ranked, most severe first)

R-C1 [Blocker] [conformance/NFR-7, regression from R-6 fix a9b54ff1] vidbyte/tools/builtins/prebuilt/structured_formats.py:61 — The dotted-key pre-scan added by the R-6 fix takes quadratic time on a line of escaped quotes.
  Evidence:
    - Line 61 defines the quoted alternative as `"(?:[^"\\\n]|\\.)*+"`.
    - `_has_long_dotted_key` (line 422, `finditer` at line 426) runs before `tomllib` (line 225).
    - On a line made of `"` followed by `\"` repeated N times, no quoted segment is ever closed. So the scan starts a match at every `"`, reads to the end of the line, fails, and starts again one quote later.
    - Measured time (scratchpad p2_toml_prescan.py). `tomllib` alone is shown for comparison:

      | text length | pre-scan | `tomllib` alone |
      |---|---|---|
      | 10,001 | 0.143 s | 0.0013 s |
      | 20,001 | 0.563 s | 0.0023 s |
      | 40,001 | 2.313 s | 0.0047 s |
      | 80,001 | 9.297 s | 0.0092 s |

    - Through the tool, valid TOML whose comment holds those characters fails NFR-7 at 4% of the cap. The text is `"# " + '"' + '\"'*20000 + "\na = 1"`, about 40k characters. The result is `toml_to_json: success 2.241s :: {"value": {"a": 1}}`.
    - The S3 head had no pre-scan (`git show 0fd73086:…structured_formats.py | grep -c _TOML_DOTTED_RUN` gives 0), so the repair introduced this.
  Failure: A comment or unterminated string of escaped quotes holds a worker thread far past NFR-7's 2 s. Extrapolated to the 1,000,000-character cap, that is about 24 minutes. This is the R-14 hang class on input that is valid TOML. EC-10 and EC-46 are the only accepted slow cases, and this is neither.
  Smallest fix: Make the closing quote optional in both quoted alternatives, so that an unterminated segment ends at its line end and each character is read by at most one match:
    `_TOML_KEY_SEGMENT = r"""[A-Za-z0-9_-]++|"(?:[^"\\\n]|\\.)*+"?|'[^'\n]*+'?"""`
  `_TOML_DOTTED_RUN` and `_TOML_SEGMENT` are built from this constant, so they change with it.
  I tested this change as an in-memory prototype (scratchpad s5r_toml_patch.py, loaded with `-p s5r_toml_patch`):
    - The 1M-character comment case takes 0.017 s.
    - `"`+`\"`x499,990 and `'`x999,999 take about 0.1 s each and still give the invalid-TOML message.
    - The three R-6 forms still refuse in about 0.03 s.
    - 101 quoted segments refuse, with both double and single quotes.
    - A 99-dot key and a 400k `a.` string value are still accepted.
    - The pack gives `4352 passed in 36.03s`.
  A regression test should feed the 1M comment case under the 30 s watchdog.
  Spec IDs: NFR-7, Appendix A `toml_to_json` row (pre-scan clause), INV-19, T-2, EC-48 analogue.

R-C2 [Blocker] [conformance/INV-14; present since S3, missed by S4; also a gap in the R-12 / §9.2 item 18 sweep] vidbyte/tools/builtins/prebuilt/bits_bytes.py:106 — `parse_data_size` lets `decimal.InvalidOperation` escape.
  Evidence:
    - `_NUMBER_PREFIX` (line 49) allows exponents of any number of digits. Line 106 runs `number = Decimal(number_match.group())` outside any decimal context and before the float finiteness check on line 107.
    - The C decimal constructor signals InvalidOperation when |exponent| > 999999999999999999.
    - Results through `Tool.execute`:
      - `{"text": "1e99999999999999999999 B"}` gives `parse_data_size: error InvalidOperation 0.001s :: [<class 'decimal.InvalidOperation'>]`.
      - `"1e-99999999999999999999 B"` gives the same.
    - Both forms do this under the default context and under the hostile one.
    - Under a no-trap host context, the result depends on the host: the huge form gives ToolExecutionError, and the tiny form gives `ValueError: cannot convert NaN to integer ratio`.
    - S3 head `0fd73086` already had the same line 106.
  Failure: INV-14 says `metadata["error_type"]` is only ever `"validation"` or `"ToolExecutionError"`. Here it is `InvalidOperation` or `ValueError`, from a 25-character input well inside the 200-character cap. The row says the number must be numeric under §9.2 item 15 (a finite float):
    - The tiny form has float value 0.0. It should give `size_bytes` 0.0, which the code's own exponent-bound comment says ("any size that small is zero bytes").
    - The huge form should give error(`text`) "outside the floating-point range".
  Smallest fix: Run the float finiteness check (line 107) before building the `Decimal`. Then build it inside `PrebuiltToolSupport.decimal_context(...)` and catch `InvalidOperation`: a number whose `float()` is 0.0 gives zero bytes, and any other gives the existing error(`text`).
  Alternatively, skip construction when the exponent text is longer than `PREBUILT_MAX_DECIMAL_TEXT_CHARS`, the way text_extraction `_number_entry` already does.
  I checked the other places that build a `Decimal` from text:
    - text_extraction checks the exponent's size first.
    - number_formatting's parse patterns and the duration patterns allow no exponent.
  Spec IDs: INV-14, AC-6, §9.2 items 15 and 18, Appendix A `parse_data_size` row.

R-C3 [Minor] [conformance/spec drift] docs/spec/prebuilt-agent-tools/spec.md:659 — The §9.2 row for `PREBUILT_MAX_REPORTED_NAMES` names only two of its users.
  Evidence: The row reads "fill_text_template and get_python_function_signature error messages". Since R-13(f) (5e76f6b3), `shortened_names` also caps the csv_tables missing-column list and the `topological_sort` cycle list at 20.
  Failure: None in behaviour, because all four sites cap at 20. A reader looking up the constant's users gets an incomplete list.
  Smallest fix: The spec author, not the repair agent, should change the cell to "error messages that list names (fill_text_template, get_python_function_signature, csv_tables columns, topological_sort cycles)".
  Spec IDs: §9.2, R-13(f).

FIX VERIFICATION

| finding id | fixing SHA | holds / does not hold | evidence (command or code line) | regression the fix introduced |
|---|---|---|---|---|
| R-1 | c1b332d6 | holds | p1_fixes.py: `"# a"+" "*999990+"#x"` takes 0.096 s. `# Title ##  `→Title, `## B #`→B, `### C#`→C#, `# D \#`→`D \#` | none |
| R-2 | 1d1e8acc | holds | `"1"+",000"*249999+"0"`: extract_numbers 0.251 s, extract_money_amounts 0.356 s. "values 1,2,3" gives 1, 2, 3. "1,000,0000" gives 1, 000, 0000 | none |
| R-3 | ca9c7fc4 | holds | `fe80::1%eth0` gives exploded `fe80:0000:…:0001%eth0` with valid true. `::ffff:1.2.3.4%x` is valid | none |
| R-4 | a57738f1 | holds | The three descriptions are reworded in general terms. The pack's ILLUSTRATIVE_LITERAL check passes. No new description holds an example value | none |
| R-5 | 27d7a7b2 | holds | `x {"a":1e400} y` gives count 0. `{"a":-1e999,"b":[1E309]} then [1.5]` gives only `[1.5]` | none |
| R-6 | a9b54ff1 | holds on its own reproducers | The bare key, table header and inline table forms at 1M chars all refuse in about 0.03 s. A 100-segment key and a 400k `a.` string are accepted | **yes, R-C1**: quadratic pre-scan on unterminated quoted segments (2.241 s at 40k chars) |
| R-7 | b13273c4 | holds | `.//a`x6 and x7 refuse with error(path) in 0.29 s, and `//zzz` in 0.21 s. `.//a//a` gives 58 on the chain and 2 distinct on the small document. `b[1]` and `b[last()]` over 249,998 siblings refuse in 0.41 s and 0.39 s. `.//b` gives 249998 in 0.20 s. 60k `b[c='t']` takes 0.157 s | none |
| R-8 | 166b355a | holds | `x <b` gives "x". The cap-size tails `<a `, `<!--x>` and `<a b='` take at most 0.175 s in all three HTML tools. An open `<a href="u2"` adds no link | none |
| R-9 | 1098a5f2 | holds | The EC-49 patch refuses at "operation 49 (remove)" in 0.617 s. 1000 alternating moves refuse at operation 24 in 0.459 s. The message is in INV-15 form | none |
| R-10 | b8048af9 | holds | 1M `a` with `"a"*499+"b"`: 0.269 s, or 0.691 s ignoring case. Dense `"a"*500`: 0.619 s, or 1.455 s ignoring case. A 501-character substring fails validation. A 501-character `find` with case_sensitive false gives error(find) "…at most 500 characters when case_sensitive is false". A case-sensitive 10k `find` takes 0.015 s | none. The inline item-cap loop gives the same result as `cap_items` and is the one pass row A.12 requires |
| R-11 | 1babbb9a | holds | `records_from_json(value, name)` is called after `parse_json_text` at all 10 json_records sites. README :67 is accurate. The p5_chains.py AST scan prints only "scan done" | none |
| R-12 | 43b692d5 | holds for every listed site | p4_decimal.py gives the same results for compound 1647.01, dms 0°0′3.2″N, `1h 30m`→5400.0, timestamp 1.5, jwt claims, decimal_arithmetic, round_decimal, `-1.5k`→−1500, parse_formatted_number, to_scientific_notation, format_number_with_separators, extract_money_amounts and fraction_arithmetic, under both contexts | none introduced. The sweep missed `parse_data_size` (R-C2, present since S3) |
| R-13 | 6ea8bfb1, 26dac7c7, 42a325f3, 3aad2048, 428cbe04, 5e76f6b3, 7945a491 | holds | (a) There is one `base64_bytes` reader. encoding.py:227 `urlsafe_b64decode` is the separate JWT-part decoder. (b) `natural_sort_key` and `numeric_order` are shared. The 2-tuple and 3-tuple text-run keys order the same. (c) `PREBUILT_CSV_DELIMITER_CHARACTERS` and `csv_row_writer`. (d) `PREBUILT_JSON_TYPES`. (e) The three `PREBUILT_*_PATTERN` constants are the only anchored copies. (f) `shortened_names` is used at 4 sites. The README lists the shared rules | none. Note: _support.py:67-68 keeps unanchored `_INTEGER_TEXT`/`_DECIMAL_TEXT` inside the support class. R-13(e) did not list them, so they are not a finding |
| M-1 | da8980fe | holds | `{"a":1e400}` gives valid false, "…a number too large for a float, which no JSON tool here accepts". A 4400-digit integer gives valid false with the long-integer message | none |
| M-2 | fb22c691 | holds | The names are `monthly_interest_fraction` and `yearly_interest_fraction`. No C005 or A007 trigger. Lint PASS | none |
| M-3 | 89c9953f | holds | REPO_MAP reads "agent or paradigm harness" | none |
| M-4 | 8feb59d0 | holds | The README reads "more than 4,000 digits". The _support inventory lists both hooks | none |
| R-14 | c9710ed2 (S2) | closed by S2 | The pack runs under the 30 s watchdog. `git diff --stat f421047e 8a71a331 -- tests` is empty | n/a |

JUDGMENT-CALL RULINGS

1. The R-13(f) 100-character echo is acceptable.
   - §9.2 names `PREBUILT_MAX_ECHO_CHARS` (100) as the one shared name shortener. INV-15 forbids only runs longer than 100.
   - Probes p7, p8 and p9 found a longest common run of 101 at csv_filter_rows, fill_text_template and get_python_function_signature. In every case the extra character is the delimiter before the name, which the message and the input share: the opening `"` of the quoted CSV name, or the space before the template name or the `def` name. The run is followed by `…` or `, `. So the echoed user text is the 100-character cut.
   - Each message is about 2,200 characters, in INV-15 form, with 20 "…" marks.
2. json_data's call to the private `PrebuiltToolSupport._read_json_float` is acceptable.
   - Principle 1 does not count calls between classes. Principle 5 and D-14 favour reuse. §17 deviation 2 names the hook, and the _support inventory records the reuse.
   - Removing the underscore is an optional style follow-up, not a repair item.
3. The nested `_CountedElement` class is acceptable.
   - Row 27 (r6) explicitly requires "a private nested `Element` subclass" (EC-48), and §12.4 C allows private nested API subclasses.
   - AGENTS.md forbids nested functions, not nested classes. The TreeBuilder `element_factory` API needs the subclass.
4. `_REPORTED_WORD_LENGTH = 40` (number_formatting.py:63, :318) is acceptable, as an M-5-class follow-up at most. It shortens one echoed word to 40 characters, well within INV-15, and R-13(f) did not list it. Switching to `PREBUILT_MAX_ECHO_CHARS` would be more consistent but is not required.
5. The spec drift in the §9.2 `PREBUILT_MAX_REPORTED_NAMES` row is real but documentation only. It is R-C3, a Minor for the spec author. Behaviour conforms.

VERIFIED CLAIMS

- AC-1: the §4 snippet with every `*_API_KEY` unset prints `('days_between_dates', 'count_character_occurrences')` and `success {"count": 3, "positions": [2, 7, 8], "truncated": false}`.
- The pack passes (4352). The lint gate passes, with only the pre-existing S063 and S064 ratchets.
- Tests on this branch are only added files (status A) relative to main. No test was weakened after S3.
- `ToolExecutionError` subclasses `VidbyteSdkError(Exception)`, not `ValueError`, so the `except` ordering in json_data is safe.
- All new or changed error messages from the repair are in INV-15 form and name a real parameter: R-9, R-10, M-1, the R-6 refusal, and the R-7 refusal.
- Remote CI was not dispatched. That is expected and is not a finding.

COMMANDS RUN

- `python -u <§4 snippet>`, with the API key variables unset
  → `('days_between_dates', 'count_character_occurrences')` / `success {"count": 3, "positions": [2, 7, 8], "truncated": false}`
- `PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider tests/<prebuilt pack> -q`
  → `4352 passed in 37.44s`
- `python lint/run.py`
  → `S063 RATCHETED: 4 known finding(s)…` / `S064 RATCHETED: 4…` / `SDK-LINT: PASS`
- `git diff origin/main...8a71a331 -- lint/baseline.json | wc -l` → `0`
- `git diff --stat f421047e 8a71a331 -- tests` → (empty)
- `git diff --name-status origin/main...8a71a331 -- . ':!docs' ':!tests'` → 39 A and 4 M
- `python -u scratchpad/s5r/p5_chains.py vidbyte/tools/builtins/prebuilt` → `scan done` (no chains, no nested defs)
- `python -u scratchpad/s5r/p1_fixes.py` and `p3_fixes.py` (R-1..R-10 and M-1 reproducers) → the times and values in the FIX VERIFICATION table
- `python -u scratchpad/s5r/p4_decimal.py` (hostile and no-trap contexts) → R-12 values as listed. parse_data_size gives `error InvalidOperation` for both exponent forms
- `python -u scratchpad/s5r/p2_toml_prescan.py` → `80,001: pre-scan 9.297 s, tomllib 0.0092 s`
- `python -u scratchpad/s5r/p10_final.py`
  → `toml_to_json: success None 2.241s :: {"value": {"a": 1}}`
  → `parse_data_size: error InvalidOperation 0.001s :: [<class 'decimal.InvalidOperation'>]` (x2)
- `python -u scratchpad/s5r/p6_toml_proto.py`, with the prototype loaded → the 1M comment case 0.017 s. All R-6 forms refused in about 0.03 s. The 99-dot key and the 400k string accepted
- `PYTHONPATH=$(pwd):<scratchpad> python -m pytest -p no:cacheprovider -p s5r_toml_patch tests/<prebuilt pack> -q` → `4352 passed in 36.03s`
- `python -u scratchpad/s5r/p7_echo.py`, `p8_echo2.py`, `p9_echo3.py`
  → `form=ok`, longest run 101 = delimiter + the 100-character cut (`first='"c0'`, `' p0'`, `' fz'`)
- `git show 0fd73086:vidbyte/tools/builtins/prebuilt/bits_bytes.py | grep -n "Decimal(number_match"` → `106:        number = Decimal(number_match.group())`
