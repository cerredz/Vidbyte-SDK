# S1 spec author report — prebuilt-agent-tools

Spec: `docs/spec/prebuilt-agent-tools/spec.md`, revision 1, committed as `d7cc529a` on `feat/prebuilt-agent-tools` (base `8387d666`).

## What I read

- **Pipeline inputs (the only `docs/` files read):** `request.md`, `context/code-map.md`, `context/research.md`, `reports/S0-scout.md`, `reports/S0-research.md`.
- **Repository rules:**
  - `AGENTS.md`, all of it: the five coding principles, Placement Rules, and the Repository Map rules.
  - `REPO_MAP.md` entries for `vidbyte/tools/`, `tools/builtins/`, `tools/toolsets/` (stale: it says "one such bundle"), `lib/constants/`, `lib/enums/`, and `lib/errors/`.
  - `vidbyte/tools/README.md`, all of it.
- **Field guide** (`field-guide/vidbyte-sdk/`): `model-facing-tool-contracts.md`, `prebuilt-agents.md`, `strict-config-dataclasses.md`, `blocking-lint-invariants.md`, `local-ci-verification.md`, `class-bound-helpers.md`, `comment-format.md`, `agents-md-map.md`, `review-scope.md`, `declarative-config-resolution.md`, `vidbyte-gates.md`.
- **Code read to ground the design:**
  - `vidbyte/tools/function_tool.py`: schema build, JSON-mode validation, error conversion, `_stringify_output`, `_docstring_summary`, and null-means-default.
  - `vidbyte/tools/catalog.py`: duplicate rejection, `subset` order, and `Sequence` indexing.
  - `vidbyte/tools/base.py`.
  - `vidbyte/lib/dataclasses/tools.py`: `ToolCall`, `ToolResult`, `ToolStatus`, `ToolSpec`, `ToolParameter`.
  - `vidbyte/lib/errors/base.py`.
  - `vidbyte/tools/toolsets/coding.py` and `__init__.py`.
  - `vidbyte/lib/enums/__init__.py` and `reasoning_strategies.py`.
  - `vidbyte/lib/util/math.py` and `text.py`.
  - `vidbyte/lib/tools/formatter.py`.
  - `vidbyte/__init__.py` (`__all__` at `:690`).
- **Lint sources read to predict findings:**
  - Rules: A001, A002 (`a002_intent_comments.py:25-75`), A003, A007 (`a007_operational_constants.py:23-38,60-137`), C006 (`c006_finite_numeric_guards.py:27-28`), C008 (`c008_shared_validator_owner.py:25-40`), C015, S009, S016, S017, S020 (`s020_readme_file_index_parity.py`), and S025 (`SentenceCounter` at `:185`).
  - Config: `lint/ruff.toml` and `.semgrep/typed-mapping-boundary-policy.yml`.
- **Probes I ran (scratch files outside the repo, nothing committed):**
  - 300 `FunctionTool`s build in about 0.22 s, and `import vidbyte` takes about 0.7 s.
  - Pydantic accepts an aware `time` (so the tool must reject it), rejects `2023-02-29`, and with `allow_inf_nan=False` rejects non-finite floats. A tuple-of-enum default renders as an array.
  - A parameter named `schema_json` makes pydantic warn that it shadows a `BaseModel` attribute.
  - `statistics.quantiles` exclusive and inclusive values for 1–8.
  - 1463! has 3,998 digits and 1464! has 4,001, and C(10000, 5000) has 3,009 digits.
  - `Agent(...)` builds without an API key.
- **Baseline on the clean worktree:**
  - `python lint/run.py` ended `SDK-LINT: PASS`. Eight rules already show IMPROVED before any change.
  - `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` gave `4015 passed, 13 skipped`, `CI passed.`.
  - I did not run the package stage or semgrep.

## Approaches weighed

- **Chosen (D-1, D-2): one typed `@staticmethod` per tool on 31 `<Category>ToolFunctions` classes, wrapped by the existing `FunctionTool`, and attached through `PrebuiltTools(categories)`, a `Tools` subclass.**
  - It reuses the SDK's only function-to-tool mechanism, so it adds no new tool machinery.
  - Category-sized attachment (6–12 tools) answers the research finding that accuracy drops once a model sees more than about 10–30 tools ([14][16][17][21] in `research.md`).
  - The rejected alternatives are in §8.3: one flat 277-tool `Tools`, about 60 multi-operation tools, and raw functions with no toolset.
  - Runner-up: a `BaseTool` subclass per tool. It would make S025 scan every description and would allow YAML discovery, but it means about 277 classes with hand-written `spec()` methods. It flips only if the user answers yes to Q-4.
- **Return type (D-7):** plain `dict[str, object]` with exact documented keys, not 277 frozen dataclasses.
  - `FunctionTool` already validates inputs through a generated pydantic model, and its output path serializes dicts.
  - One dataclass per tool would add about 277 records to `vidbyte/lib/dataclasses/` and nearly double the budget.
  - This is the decision I am least sure of against AGENTS.md principle 4. It is optional Q-6, default no.
- **Errors (D-8):** I first planned a `PrebuiltToolArgumentError`. The `REPO_MAP.md` entry for `vidbyte/lib/errors/` says a new failure mode should usually reuse an existing type, and A003 would also demand a full diagnostic packet. So every domain error is a `ToolExecutionError` built by one helper with one message form (INV-15).
- **Exactness (D-13, D-16):**
  - Integers, decimals, and fractions travel as canonical text, so JSON never loses precision past 2^53.
  - Integer results are capped at 4,000 digits (INV-18), so Python's 4,300-digit `int`-to-`str` limit never fires inside `_stringify_output`.
  - Unit tables are exact `Fraction` strings.
- **Count floor (D-9):** a test in the S2 pack asserts the count is at least 250 and that the name set equals Appendix A. I chose this over a CI script that would pin the exact count.

## Where I disagreed with the scout or the request

1. **The request assumed a modest set of built-ins with a registry to add tools to.** In fact `vidbyte/tools/builtins/` already holds about 218 reasoning-trace classes, `Tools` is local to each agent, and there is no global tool registry. The design therefore adds a toolset rather than registering anything (D-2, INV-6).
2. **The scout's lint table left out several rules the new files will trip:**
   - S050 (md5/sha1 `usedforsecurity=False`), S004 (no naive datetimes or `strptime`), S003 (`zip(strict=)`), S054 (secret-like names), S009 (mypy), C006/C008 (validator-shaped names), and the pydantic shadow-name warning.
   - A007's context window: for a literal in a parameter annotation, A007 scans every name in the whole signature. That forced two renames: the constant `PREBUILT_MAX_RECURRENCE_STEP` and the parameter `repeat_every`, instead of `interval`.
   - Other renames from these rules: `jwt_text` instead of `token`, `json_schema` instead of `schema_json`, `html_text` instead of `html`, `bit_format` instead of `format`, `float_result` instead of `finite_float` (C008 noun family), and `find_violations` instead of `validate` (C006).
   - All of these are §12.4 obligations.
3. **The scout raised a concern about provider-formatter `items` handling.** It does not apply on the `FunctionTool` path: pydantic emits `items` for lists, and the Gemini reducer expands `$defs`.
4. **Overlap with the existing calculator, which I verified (4,096-bit cap).** I dropped big-integer multiply, divide, and power so the two do not compete (NG-7).
5. **Research rows dropped as unsafe, non-deterministic, or overlapping:**
   - IANA time zones (`tzdata` is not a dependency) and current date or time (clock-dependent).
   - YAML (alias expansion; NG-10), a SQLite query tool, password or secret generation, gzip, punycode, cron, Easter dates, and calendar printing.
   - `is_palindrome`, `build_markdown_table` (overlaps `csv_to_markdown_table`), stop-word removal, color tools, and matrix tools.
6. **The request's "straight into spec"** means no questions block the spec. All six open questions are optional, with default "no" (NFR-11).

## Assumptions I am least sure of

- **D-7 / A-7:** dict outputs against AGENTS.md principle 4. A reviewer may ask for typed output records, which is Q-6.
- **A-6:** model-facing descriptions carry no examples because the field guide forbids them, although research [16] found that examples help with format-heavy parameters such as dates, dice notation, and semver ranges.
- **EC-24:** seeded tools reproduce only within one Python minor version. Tests must not pin seeded sequences across 3.11 and 3.12.
- **NFR-7 / A-9:** the per-call target of ≤ 2 s at maximum input. It is least certain for `closest_string_matches` (1,000 candidates), `find_unicode_character` (a full scan of about 1.1 million code points), `diff_words` at 20,000 tokens, and `levenshtein_distance` at 1,000 × 1,000.
- **Heuristic tools** (syllables, sentence splitting, script detection, mojibake repair, `count_lines_of_code`): the spec defines exact algorithms so tests can bind to them. Their usefulness on real text is the part that has not been measured.
- **FR-8 wording:** domain-fixed bounds (months, bases 2–36, percent and coordinate ranges) are allowed as literal `Field` constraints, while every length cap and resource bound is a named constant. A strict reviewer may prefer constants for everything.
