# S1 spec review — prebuilt-agent-tools spec r1

Reviewed: `docs/spec/prebuilt-agent-tools/spec.md` r1 (1,528 lines) at HEAD `bdec5ea3`
(branch `feat/prebuilt-agent-tools`, base `8387d666`). Read-only review. Probes ran from
the session scratchpad on local Python 3.11.0. Nothing in the worktree changed except
this report.

VERDICT: SOUND WITH FIXES — the architecture (static category classes wrapped by the
existing `FunctionTool`, attached through `PrebuiltTools(Tools)`) is sound and verified,
but three bounded spec edits must land before S2/S3 start: exact computation rules for
the float and money rows, a growth guard on `apply_json_patch`, and the missing S002 (B904)
obligation.

## WHAT THE SPEC GETS RIGHT

- No new tool mechanism. Every claim about `FunctionTool` held under probe: a staticmethod
  taken from the class, a name from `__name__`, the first docstring paragraph as the
  description, `Field(description=...)` in the schema, `$defs` enums, `maxItems`/`pattern`/
  nullable `anyOf`, and `provider_schemas` for openai, anthropic, and gemini (Gemini inlines
  `$defs`). A raised exception becomes `error_type = exc.__class__.__name__` with
  `str(ToolExecutionError(msg)) == msg`.
- The lint analysis is precise and correct, including the subtle cases:
  - A007 matches whole `_`-split words, and `_names` ignores `ast.arg`.
  - A002 uses `\b` tokens. C006 does not match `verify_*`. C008 covers `is` and `resolve`.
  - The scopes of S016 and S017 hold. S020 is opt-in. S025 applies only to BaseTool `spec()`.
- The numbers are exact and verified:
  - 1463! has 3,998 digits and 1464! has 4,001.
  - C(10000, 5000) has 3,009 digits.
  - Both quantile examples are right, and so is the Miller–Rabin bound.
  - The §4 output `{"count": 3, "positions": [2, 7, 8], "truncated": false}` is right.
- The bookkeeping is internally consistent:
  - The table counts sum to 277.
  - The 40 files match the §12.3 CREATE rows.
  - There are 53 + 10 enums.
  - The 277 names are unique and ≤ 64 characters, with no collision in `vidbyte`.
  - There is no import-time tool construction anywhere, so INV-7 and AC-5 are achievable.
  - There is no default "attach everything".

## FINDINGS

R-1 [Blocker] [L10/L9] Appendix A + AC-11 — "match the row … exactly" is not achievable: float/money paths and several rows are under-specified, so S2 and S3 will disagree
  Evidence:
  - The spec says AC-11 :171 requires that "the output and error behavior match the row and the §9.2 conventions exactly".
  - D-16 :285 says "Money amounts are output as decimal text with two places, rounded `ROUND_HALF_UP`".
  - §12.3 row 14 :836 says "Money is rounded with `Decimal.quantize(Decimal("0.01"), ROUND_HALF_UP)`".
  - The inputs are `Float`:
    - `principal`, `annual_rate_percent` in `compound_interest_future_value` :1155 and `loan_payment_amount` :1156.
    - `tax_rate_percent` in `split_tax_inclusive_amount` :1164.
    - `amortization_schedule` :1157 computes "balance × i" with a float i.
  - The spec never says how a float becomes a `Decimal`. Probe: `Decimal(2.675).quantize(Decimal("0.01"), ROUND_HALF_UP)` gives `2.67`, while `Decimal(repr(2.675))` gives `2.68`.
  - §13 has no float tolerance rule. The only tolerance in the spec is `PREBUILT_IRR_TOLERANCE` :614. Yet the haversine, regression, quadratic, and continuous-compounding rows return raw floats, which `_stringify_output` (`vidbyte/tools/function_tool.py:214`) writes as the full `repr`.
  - These rows also leave the expected output open:
    - `round_significant_figures` :1068: 2.5 at 3 figures could be "2.5" or "2.50". The row only covers an input that already has the zero.
    - `fraction_to_decimal` :1073: the truncated case does not set `terminates` or `repeating_digits`.
    - `english_words_to_number` :1100: "impossible order" is undefined. Is "twenty one hundred" 2100 or an error?
    - `generate_recurring_dates` :1210: "`count` is the number of dates generated before the cap" contradicts INV-17 :144, where totals count every item.
    - `split_text_into_chunks` :1259: does a "break point" index fall before or after the whitespace or blank line?
    - `csv_to_records` :1344: "look like integers" is undefined for `"1_000"`, `" 5"`, or `"+5"`, where Python `int()` accepts all three.
    - `format_bytes_human` :1463: the rounding mode is missing.
    - `summarize_json_structure` :1319: how does an object shape merge with a scalar type?
    - `extract_urls` :1489: the URL character set and the trailing punctuation set are missing.
    - `verify_email_syntax` :1408 and the URL and IP verifiers: `reason` is free text with no enum or fixed wording, so tests can assert only non-null.
    - `count_character_occurrences` :1235 uses `.lower()`, which contradicts §9.2 item 7 :457 ("positions … `re.IGNORECASE` on `re.escape(<literal>)`").
  Failure: The test author and the implementer read the same row and choose differently. For example, with principal 2.675 and rate 0, the implementer returns "2.67" and the test expects "2.68". Every disagreement fails AC-11, or forces one side to change silently.
  Smallest fix:
  - (a) D-16: "Float inputs enter Decimal as `Decimal(repr(x))`; all money arithmetic after that is Decimal; transcendental steps (`e^(rt)`, `(1+i)^-n`) are computed in float and converted the same way before quantize".
  - (b) §13: "float outputs are compared with `pytest.approx(rel=1e-9, abs=1e-12)` unless the row rounds".
  - (c) Settle each listed row in one sentence, and make `count_character_occurrences` follow §9.2 item 7, or name it as the exception.

R-2 [Blocker] [L5/L7] INV-20 / T-2 — `apply_json_patch` can grow its output exponentially from a tiny patch, with no guard
  Evidence:
  - INV-20 :147 lists only "`replace_all_occurrences`, `regex_replace`, and `fill_text_template`" as unbounded-growth tools.
  - The row at :1317 allows `copy` with any RFC 6902 `from`, and the root `""` is a valid pointer (§9.2 item 3 :447).
  - Probe (scratch probe4): 20 successive "copy root into new key" steps grew a ~100-character document to 125,830,135 characters.
  - The size doubles with each operation. A patch of about 30 operations, a few hundred characters long and well within `PREBUILT_MAX_PATCH_OPERATIONS`, asks for about 10^11 characters.
  Failure: A prompt-injected `copy` chain exhausts host memory inside the worker thread. NG-10 (YAML aliases) and INV-19 (XML entities) block exactly this kind of attack, and T-2 claims it is mitigated.
  Smallest fix: Add `apply_json_patch` to INV-20 and T-2. Keep a running serialized-size estimate after each `add`, `copy`, or `replace`. If it exceeds `PREBUILT_MAX_TEXT_CHARS`, raise error(`patch_json`) naming the operation index. Add an EC row for this case.

R-3 [Blocker] [L8] §12.4 — the checklist omits S002 (Ruff B904, baseline 0), which ~200 conversion sites will trip
  Evidence:
  - §9.2 item 13 :471 prescribes `raise PrebuiltToolSupport.argument_error(...)`.
  - §12.4 :894 requires catching and converting 15 stdlib exception types, and gives no `from exc` or `from None` rule. `grep -n "B904\|S002\|from None"` finds nothing.
  - In the repo, `lint/rules/s002_exception_cause_chaining.py:23` sets `codes = frozenset({"B904"})`, and `lint/baseline.json:31` sets `"S002": 0`.
  Failure: Every `except ValueError: raise PrebuiltToolSupport.argument_error(...)` is a B904 violation, so the lint gate fails across all 31 modules.
  Smallest fix:
  - Add this §12.4 item: "Every raise inside an `except` uses `from None`." `from None` keeps the INV-15 message free of a chained cause in logs. `from exc` is also acceptable.
  - Also, at the security guards (DOCTYPE/ENTITY rejection, the digit cap, growth checks, nesting caps), add a `# @intent <name>` block per `comment-format.md`. The spec already cites that format at :878, and the reviewer will ask for it.

R-4 [Major] [L5/L11] NFR-7 — "≤ 2 s at the largest input its schema allows" is false for six tools, and only regex is excepted
  Evidence:
  - NFR-7 :254 and EC-10 :194 except only regex.
  - The caps are `PREBUILT_MAX_SEQUENCE_MATCH_CHARS` 10_000 :581 and `PREBUILT_MAX_DIFF_TOKENS` 20_000 :583.
  - Row 23 :845 requires "Every `difflib.SequenceMatcher` uses `autojunk=False`".
  - `modular_exponentiation` :1089 accepts three 4,001-character `IntText` values.
  - CSV tools sniff the whole `CsvText` when `delimiter` is null. Only `detect_csv_dialect` :1345 limits sniffing to 100,000 characters.

  Local probes (Python 3.11.0):

  | Case | Time |
  |---|---|
  | `longest_common_substring`, 10k identical characters | 6.51 s |
  | `similarity_ratio`, 10k random a/b | 8.02 s |
  | `diff_words`, 20k tokens | 36.11 s |
  | difflib at 2k / 4k (LCS) | 0.25 s / 1.01 s |
  | difflib at 2k / 4k (ratio) | 0.34 s / 1.66 s |
  | difflib at 2k / 4k (diff tokens) | 0.25 s / 1.13 s |
  | `pow` with three 4,000-digit operands | 3.15 s |
  | `pow` at 2,000 digits | 0.44 s |
  | `csv.Sniffer().sniff`, adversarial 100k | 2.35 s |
  | `csv.Sniffer().sniff`, adversarial 300k, even with `delimiters=",;\t|"` | 7.09 s |

  The Sniffer slowdown is quadratic, and the `CsvText` cap is 1M.

  Failure: Model-chosen inputs pin a worker thread for seconds to minutes. `FunctionTool` has no timeout unless `ToolSettings.tool_timeout_seconds` is set (`settings/tool.py:39`), and even then the thread keeps burning CPU. That is the EC-10 problem, in tools that T-2 does not list. The author's own report already doubted `diff_words` at 20k.
  Smallest fix:
  - Set `PREBUILT_MAX_SEQUENCE_MATCH_CHARS` and `PREBUILT_MAX_DIFF_TOKENS` to about 2,000.
  - Cap the `modular_exponentiation` operands at 1,000–2,000 digits.
  - Have every CSV tool sniff only the first `PREBUILT_MAX_SNIFF_CHARS` (about 10,000; 0.22 s measured).
  - If the author prefers the current caps, list each of these as an accepted EC and amend NFR-7 and T-2.

R-5 [Major] [L5] INV-19 / INV-14 — `xml_to_json` can return an output so deep that `FunctionTool.execute` itself raises
  Evidence:
  - INV-19 :146 caps nesting only for JSON text.
  - `xml_to_json` :1358 has no depth rule. `extract_json_from_text` :1320 keeps any `raw_decode` value, so the 100-level cap does not apply to it.
  - In the repo, `function_tool.py:68-81` wraps only the function call. `_stringify_output(value)` at :85 (defined at :206) runs after the `try`.
  - Probe (scratch probe5): `ET.fromstring("<a>"*5000 + "</a>"*5000)` (35k characters) parses fine.
  - A 5,000-deep return value makes `tool.execute(...)` raise `RecursionError` instead of returning a failure. Depth 900 succeeds.
  - `tomllib.loads("a = " + "["*500 + "]"*500)` raises `RecursionError`. §12.4 :894 does list `RecursionError`, so that path is covered if the implementer applies it.
  Failure: Hostile XML gets past every guard. `execute` raises, which breaks INV-14 and AC-6. The runtime then reports a generic "Tool execution failed" instead of a teachable error.
  Smallest fix: Apply `PREBUILT_MAX_JSON_NESTING` to XML element depth before conversion, raising error(`xml_text`). Skip `extract_json_from_text` candidates deeper than the cap. Name both in INV-19.

R-6 [Major] [L4] D-7 — dict outputs rest on a premise the spec itself breaks
  Evidence:
  - D-7 :276 says the output is "serialized to JSON text at once by `_stringify_output`, never read by another Python layer".
  - FR-5 :237 and §8.5 :417, however, publish `<Category>ToolFunctions.tool_functions()` and say "Calling a function directly runs the same body".
  - AGENTS.md:35 says to "return a dataclass as output, rather than loose dicts".
  - Partial support for D-7 in the repo: `vidbyte/tools/README.md:58-77` shows a `@tool` that returns a dict.
  Failure: Once the functions are public, any caller reading `result["count"]` is "another Python layer" consuming loose dicts. The review gets a principle-4 comment, and D-7's rationale cannot answer it.
  Smallest fix:
  - Keep D-7. Don't ask for 277 dataclasses.
  - Downgrade FR-5 and the :417 bullet to "internal, for tests and for `PrebuiltTools`; not a supported call surface" so the premise holds.
  - State the residual owner risk explicitly in Q-6.

R-7 [Major] [L4/L2] §8.5 / INV-4 — `PrebuiltTools` accepts a plain `str` for a closed-set parameter
  Evidence:
  - §8.5 :362 has `__init__(self, categories: Iterable[PrebuiltToolCategory | str] | PrebuiltToolCategory | str)`, and :364 has the same type.
  - INV-4 :131: "A plain string equal to a member's value is accepted".
  - Appendix A :1527 has `convert_ip_address_integer.version: int = 4 [4..6]`, where "`version = 5` → error(`version`)".
  - AGENTS.md:63: "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum … not a plain `str`."
  Failure: The public signature advertises stringly-typed input and a 4-way union, which is exactly the convention comment AGENTS.md pre-empts. The IP `version` invents a bogus in-range value (5) that needs its own error.
  Smallest fix:
  - Type the parameter as `Iterable[PrebuiltToolCategory] | PrebuiltToolCategory`.
  - Keep the runtime membership check, raising `ToolRegistryError`, for untyped callers.
  - Drop the "plain string" clause from INV-4, EC-3, and AC-4. AC-4 still tests a foreign value.
  - Make `version` an `IpVersion` enum (`4`, `6`), which is a 54th enum in `prebuilt_tools.py`.

R-8 [Major] [L9/L4] §12.3 row 6 — "calls no other helper of this class" contradicts INV-15/D-8 for 10 helpers
  Evidence:
  - Row 6 :828 lists the helpers and says "Each helper does one job and calls no other helper of this class".
  - Yet `parse_json_text`, `parse_records_json`, `json_pointer_tokens`, `parse_integer_text`, `parse_decimal_text`, `integer_text`, `float_result`, `parse_utc_offset`, `parse_csv_table`, and `encode_text` each take `parameter_name` and must raise the INV-15 error.
  - D-8 :277 says that error is "built by one helper, `PrebuiltToolSupport.argument_error`".
  - AGENTS.md:23 permits a function to call another of its own functions as long as that one calls nothing further. One hop is allowed.
  Failure: The implementer must either break row 6 or copy the message f-string into 10 places, which breaks D-8 and lets INV-15 wording drift.
  Smallest fix: Row 6 should read: "Helpers may call `argument_error`, which is a leaf; no other helper calls another".

R-9 [Major] [L3/L11] §8.4 / NFR-8 — the 800-line cap plus a hard 40-file budget can force a mid-build BLOCKED
  Evidence:
  - §8.4 :309 says "31 category modules (… one per category keeps each ≤ 800 lines)". :316 says "may not exceed this budget without stopping and reporting BLOCKED", and :995 repeats it.
  - INV-9 :136 requires a 4–5 sentence description for every parameter.
  - Repo yardstick: `vidbyte/tools/builtins/cot_events.py` holds 6 model-facing tools with 49 description sites in 1,139 lines, about 190 lines per tool.
  - The heaviest categories have up to 15 tools with intricate bodies: `identifiers.py` (node-semver ranges), `dates.py` (12), `json_data.py` (JSON Patch + validator), and `markdown_html.py`.
  Failure: A module passes 800 lines partway through S3. The only legal move is to stop, though the obvious fix (a private sibling module) is harmless.
  Smallest fix:
  - Pre-authorize `_<category>_<part>.py` private splits, up to N extra files, outside the BLOCKED rule. Alternatively, name the expected splits now.
  - Optional, within the 27-tool slack above the floor: drop the heaviest, most disputed rows (`verify_json_against_schema` together with `_json_schema.py`, `semver_satisfies_range`, `apply_json_patch`).

R-10 [Minor] [L1/L2] §1 / NG-7 / Appendix A — the calculator description is wrong, and several tools barely expand capability
  Evidence:
  - §1 :37 and NG-7 :58 say `calculator` does "whole-number arithmetic expressions". In fact `vidbyte/tools/builtins/calculator.py:13` exposes `round` and `pow`, and its own description example is `'(4 * 3) / 2'` (:62), so it handles floats and division. `decimal_arithmetic`, `sum_decimal_list`, and `percentage_change` overlap it apart from exactness.
  - Weak or duplicate rows against the user's "expand the agent's capability" bar:
    - `days_in_month`, `is_leap_year`, `collapse_whitespace`, `html_escape`/`html_unescape`, `generate_seeded_uuid4`, and the Roman numeral pair.
    - `sort_list` vs `sort_text_lines`, and `deduplicate_list` vs `deduplicate_lines`.
    - `similarity_ratio`, `jaccard_similarity`, `jaro_winkler_similarity`, and `levenshtein_distance` side by side.
  Failure: The NG-7 rationale misleads reviewers, and near-duplicates dilute tool selection, the very risk [15] that NG-7 cites.
  Smallest fix: Correct the calculator sentence and state that the exact tools differ by exactness. Optionally merge or drop up to 27 weak rows while keeping the count ≥ 250. This is the author's choice, as the user delegated it.

R-11 [Minor] [L9/L10] D-9 vs AC-2/AC-9; INV-6 — the floor rationale is contradicted by exact-set acceptance criteria
  Evidence:
  - D-9 :278 rejects an exact count because it "would turn every future addition into a CI failure".
  - AC-2 :162 requires the "name set equals Appendix A's name set (277)", and AC-9 :169 requires "returns 277 declarations".
  - INV-6 :133 says "two catalogues never share a tool object". In the repo, `Tools.subset` and `without` (`vidbyte/tools/catalog.py:95-102`) return catalogues that share objects.
  Failure: A future addition fails AC-2 and AC-9 anyway. INV-6 as written is false for `PrebuiltTools(...).subset(...)`, the §4 usage itself.
  Smallest fix:
  - AC-2: Appendix A ⊆ names, and count ≥ 250.
  - AC-9: `len(declarations) == len(catalogue)`.
  - INV-6: "two `PrebuiltTools(...)` constructions never share a tool object".

R-12 [Minor] [L11] §11 — the third local gate command tests the wrong checkout
  Evidence:
  - §11 :696 lists `… then python scripts/run_ci.py` with no `PYTHONPATH`. AC-16 :176 lists only the two split commands.
  - In the repo, `scripts/run_ci.py` defaults to `--stage all`. The field guide `local-ci-verification.md` warns that in a worktree, an unprefixed source stage imports the canonical checkout.
  Failure: The implementer runs it, sees green against the main checkout, and reports a false pass.
  Smallest fix: Delete the third command, or prefix it with `PYTHONPATH=$(pwd)` and mark it redundant with the two AC-16 commands.

## VERIFIED CLAIMS

- Held — FunctionTool contract:
  - Staticmethod wrapping, name, and description from the first docstring paragraph (`function_tool.py:192`).
  - Field descriptions in the schema (:117).
  - JSON-mode argument validation (:180-189).
  - The error shape (:76-81).
  - A `datetime` parameter accepts an int as UTC; a `date` parameter rejects an int.
  - No pydantic shadow warning for `json_text` or `json_schema`.
- Held — catalogue mechanics:
  - `Tools` rejects duplicate names (`catalog.py:38`).
  - `subset` keeps catalogue order (:95-102).
  - The `CodingAgentTools` sibling pattern (`toolsets/coding.py`) matches the §8.5 shape.
- Held — lint and gates:
  - A007, A002, C006, C008, S016 (includes `tools/builtins/`), S017 (`vidbyte/tools/`), S020 (opt-in, File Index), S025 (BaseTool `spec()` only; `SentenceCounter` :185), A001 (7 fields), and the S058/S060 scopes.
  - mypy `disallow_any_generics`.
  - The semgrep commands match `static-policy.yml`.
  - CI runs Python 3.11 and 3.12, plus `--stage package --dist-dir dist`.
  - `llms.txt` and `artifacts/file_index.md` are not gated (NG-11).
- Held — the repo line references cited by the spec:
  - REPO_MAP lines 171, 179, 183-185, 315, 319, and 335-337. The toolsets entry is stale ("one such bundle").
  - `vidbyte/__init__.py` imports toolsets at :611, with `__all__` at :690.
  - `toolsets/__init__.py` `__all__` at :20-23.
  - `ToolSettings.tool_timeout_seconds` (`settings/tool.py:39`; runtime :1449-1451).
- Held — §4 snippet:
  - `Agent(provider="openai")` builds with no key.
  - `ToolStatus` is `success` or `error`.
  - `ToolCall(tool_name, arguments)` is positional.
  - The expected output matches `sort_keys` with the default separators.
- Held — numeric facts:
  - The 4,000-digit cap sits below the 4,300 `int_max_str_digits` limit.
  - The factorial and binomial digit counts, the quantile examples, and the Miller–Rabin bound.
  - `PREBUILT_MAX_PRIMALITY_VALUE` keeps `is_prime` and `next_prime` cheap.
- Held — counts and names:
  - 277 tools in 31 tables, every table count right.
  - 63 enums with no name collision in `vidbyte`.
  - 40 files, matching the §12.3 CREATE rows.
  - No tool-name collision; `regex_match` matches only an eval grader name.
- Held — no import-time `@tool`, `Tools(...)`, or `FunctionTool(...)` anywhere in `vidbyte` (INV-7, AC-5).
- Held — `lib/util` has no sentence, word, or JSON-depth helper to reuse (D-14).
- Held — `ComponentRegistry._discover` filters for classes, so the new submodule attribute is harmless.
- Held — no README exists in `lib/enums`, `lib/constants`, `tools/builtins`, or `tools/toolsets`. The Folder Description and File Index convention exists elsewhere.
- Held, with a caveat — the enums `__init__` header names no enums. Its `__all__` is "alphabetical" only loosely: it is already out of order at `DocumentType`/`DecisionModelMode` and `JevRunBriefUpdateStatus`/`JevQuestionType`.
- Did not hold:
  - The calculator is "whole-number arithmetic" (R-10).
  - The D-7 premise "never read by another Python layer" (R-6).
  - The INV-6 wording "two catalogues never share" (R-11).
  - NFR-7's "≤ 2 s at the largest input" (R-4).
  - INV-19/INV-20 coverage claimed by T-2 (R-2, R-5).
  - D-9's floor rationale against AC-2 and AC-9 (R-11).
