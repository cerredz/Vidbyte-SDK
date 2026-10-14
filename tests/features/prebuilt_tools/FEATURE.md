# Feature: Prebuilt agent tools

## High-Level Feature Description

The SDK ships a library of 265 small, deterministic, standard-library-only tools, grouped into 31 categories, that a developer attaches to an agent with `PrebuiltTools([...categories])`. Each tool is an ordinary `FunctionTool` the model calls with JSON arguments. It returns one JSON object on success, or a failure whose `error_type` is `validation` (schema) or `ToolExecutionError` (domain). The tools give the agent exact arithmetic, counting, date arithmetic, parsing, encoding, hashing, and structured-data work that a model does badly in tokens. Source of truth: `docs/spec/prebuilt-agent-tools/spec.md` revision 6, especially §4, §6, §8.5, §9.2, and Appendix A.

## Contract

- `vidbyte.tools.toolsets.PrebuiltTools(categories)` is a `Tools` subclass defined in `vidbyte.tools.toolsets.prebuilt`. `categories` is an iterable of `PrebuiltToolCategory` members, or one bare member. The result holds the distinct categories' tools in catalogue order: enum declaration order, then Appendix A row order.
- Any item that is not a member, including a plain string equal to a member value, raises `ToolRegistryError` before any tool is built. So does a bare plain string, which is never iterated. The message names every bad value and lists every valid value.
- `PrebuiltTools([])` is empty, and `PrebuiltTools()` is a `TypeError`: there is no "attach everything" default.
- The static `select_categories(categories)` returns the distinct members in enum order. The static `get_tools(categories)` returns fresh `FunctionTool` objects in catalogue order. Two constructions never share a tool object.
- `vidbyte.lib.enums.PrebuiltToolCategory` is a `str` Enum with 31 members, and `values()` returns their values in order. The other 67 vocabulary enums of §9.2 live in `vidbyte/lib/enums/prebuilt_tools.py` and `vidbyte/lib/enums/units.py` and are exported from `vidbyte.lib.enums`.
- `vidbyte.tools.builtins.prebuilt` re-exports the 31 `<Category>ToolFunctions` classes. Their `tool_functions()` returns the plain functions in row order (internal surface, FR-5).
- Every tool is a `FunctionTool` with `ToolPermission.SAFE`, named after its function, and described by the first paragraph of its docstring. The parameter names, types, defaults, enums, and caps match its Appendix A row. Every description and parameter description is 4 or 5 sentences by the lint `SentenceCounter` and holds no example value.
- The output keys are exactly the row's keys. Floats are finite and compared with rel 1e-9 or abs 1e-12, or within 10^-k where the row rounds to k places. Every other value is exact.
- A `ToolExecutionError` message reads `Invalid value for '<parameter>': <problem>. Expected <form>.`. It never echoes more than 100 characters of an argument, and never echoes the `compute_hmac` key.

## Actors / Callers

- A developer who builds a catalogue and passes it to `Agent(tools=...)`, or picks tools with `subset`.
- A model that calls tools through the runtime, which reaches `FunctionTool.execute(ToolCall(...))`.
- The provider formatters, through `Tools.provider_schemas("openai" | "anthropic" | "gemini")`.

## Inputs and Preconditions

- Category members only; no API key, network, file, or environment is needed to build or run any tool.
- Tool arguments arrive as model JSON. Pydantic JSON mode validates them: `"2"` and `2.0` pass for an int, while `2.5` does not, undeclared arguments are ignored, and `null` for an optional argument means its default.
- Every `str` and `list` parameter has a schema cap (`PREBUILT_MAX_*` constants, or the literal 7 for `weekend_days`). A `UtcOffset` string carries both its pattern and `PREBUILT_MAX_UTC_OFFSET_CHARS` (6).

## Observable Outcomes

- Success: `ToolStatus.SUCCESS` with one JSON object whose keys are sorted by `_stringify_output`.
- Failure: `ToolStatus.ERROR` with `metadata["error_type"]` equal to `validation` or `ToolExecutionError`, and nothing else.
- Enumerations stop at their item cap (1,000 by default) or before the character budget of 1,000,000 compact JSON characters. They set `truncated`, and their count keys still count every item.
- Outputs that would pass 1,000,000 characters (INV-20 tools) fail instead of being built. Integer results of 10^4000 or more fail. Deep nesting fails, or is skipped by `extract_json_from_text`.

## State Transitions

None at run time: tools keep no state, cache nothing, and change no global setting. The only transition is construction: categories are validated, then fresh `FunctionTool` objects are built, then `Tools.__init__` rejects duplicate names.

## Invariants

INV-1 to INV-22 of spec §6.1 are tested here. INV-23 to INV-26 are guarded by existing gates (see Omitted Testing Strategies). The ones that need care in tests:
- INV-12: byte-identical output across hash seeds, working directories, time zones, locales, and earlier calls, within one Python version.
- INV-13: no socket, process, thread, environment read, clock read, or file access, and no global-state change.
- INV-14 and INV-15: no exception class other than `ToolExecutionError` escapes a tool, and messages follow the INV-15 form.
- INV-17 to INV-20: bounded output, bounded integers, defensive parsing, and refusing over-cap output before building it.

## External Dependencies

- The Python standard library only. No dependency is added (INV-25).
- `FunctionTool` and pydantic validate the arguments; they are real in every test, never mocked.
- `lint/rules/s025_model_facing_description_depth.py` provides `SentenceCounter`.

## Known Failure Modes

This is the failure inventory the tests were chosen from. Each entry is input plus state, then the wrong behavior.

1. Categories given as plain strings, or a bare string iterated character by character, raise the wrong error, or tools get built before the error (AC-4, EC-3).
2. Category order or repeats change the catalogue, or a module-level cache shares tool objects between catalogues (INV-4, INV-6).
3. A tool is missing, renamed, reordered, or moved to the wrong category, so the catalogue drops below 250 tools (AC-2, AC-3, AC-12).
4. A parameter is renamed or reordered, has the wrong default, the wrong enum, or a missing or wrong cap (Appendix A, INV-16).
5. A description is too short or too long, or carries an example value (INV-9).
6. A provider formatter fails on one schema, or merges or drops declarations (INV-21).
7. Escaped exceptions break INV-14: `KeyError`, `ValueError` from `int()` or `fromisoformat`, `OverflowError` on years 1 and 9999, `ZeroDivisionError`, `RecursionError` from deep JSON, TOML, XML, or literals, `IndexError` from a regex template, `TypeError` from ElementPath, and `UnicodeEncodeError`.
8. NaN or Infinity reach the output, or keys are missing or extra (INV-10, INV-11).
9. Float routes are used where §9.2 items 16 and 17 require `Decimal(repr(x))` and one quantize. Half-even and half-up ties then go the wrong way (8.845 becomes 8.84, 2.0035 seconds becomes 2.003s, 0.000875° becomes 3.1″).
10. Positions are read from a lowercased copy, so `ß`, `İ`, and `ﬁ` shift them (EC-16). CRLF and lone CR line endings are miscounted (EC-15).
11. Set or dict iteration order leaks into output and changes with `PYTHONHASHSEED` (INV-12).
12. A count is computed by enumerating (2^128 subnets, 10^15 integers), or a list is not truncated (INV-17).
13. An amplifying input builds a huge string or document before checking it (EC-13, EC-41, EC-43), or a 4,001-digit integer reaches `str(int)` (EC-8).
14. XML entities or DOCTYPE are parsed (EC-11). Conversion returns a value nested more than 100 deep, so `_stringify_output` raises outside the tool's error handling (EC-42).
15. A tool reads the clock, the environment, or files, uses the global random generator, or changes the decimal context, the recursion limit, the int digit limit, or the csv field limit (INV-13).
16. An error message echoes a long argument or the HMAC key (INV-15, T-3).
17. A cap-sized hostile input makes a tool run for minutes or hours although every argument is within its cap: a long space run in a heading, a failing comma chain, a long dotted TOML key, repeating ElementPath steps, HTML left open at the end, or a JSON patch that copies a large value hundreds of times (S4 R-1, R-2, R-6 to R-9; EC-47 to EC-49).
18. A host that traps `Inexact` or lowers `Emax` in its decimal context changes a tool's result or makes it raise, because the worker thread copies that context (S4 R-12; §9.2 item 18).

## Historical Regressions

The pack was written red before implementation from spec revision 3, then tightened to revision 4, which fixed the values revision 3 left open. The S4 review then found 14 defects while the pack was green (R-14). Revision 6 turned them into exact row behavior, and the pack gained their regression cases before the repair: the R-ids are in the case labels of `test_prebuilt_hostile_inputs.py` and in the comments above the row cases.

## Test Suite Map

| File | What it proves | Spec IDs |
|---|---|---|
| `test_prebuilt_acceptance.py` | The §4 snippet prints exactly its two lines in a fresh interpreter with no API key, and importing the SDK builds no tool. | AC-1, AC-5, INV-7 |
| `test_prebuilt_toolset_contract.py` | Floor, exact names and order, per-category rows, enum tables, category validation, construction identity, merging, exports, `FunctionTool` shape, and per-tool schemas. | AC-2, AC-3, AC-4, AC-12, AC-18, AC-19, INV-1 to INV-6, INV-8, INV-16, INV-22 |
| `test_prebuilt_model_facing_contract.py` | Description depth and no examples, provider schemas, and one-over-cap rejection naming the parameter and its cap. | AC-7, AC-8, AC-9, INV-9, INV-16, INV-21 |
| `test_prebuilt_error_contract.py` | Sweeps thirteen schema-derived argument sets per tool: documented keys, finite JSON, only allowed error types, INV-15 messages, and the HMAC key never echoed. | AC-6, INV-10, INV-11, INV-14, INV-15, T-3 |
| `test_prebuilt_determinism.py` | Byte-identical output across two child interpreters with different hash seeds, directories, time zones, and locales, plus repeated calls. | AC-10, INV-12 |
| `test_prebuilt_side_effects.py` | Instrumented socket, subprocess, environment, clock, and open calls are never made from tool frames. Global state is unchanged. A static source scan finds no banned calls. | AC-13, INV-13, INV-19, T-5, T-6 |
| `test_prebuilt_resource_bounds.py` | Item cap and character budget, arithmetic counts, 4,001-digit refusals, every INV-20 tool refusing over-cap output (with peak memory for predicted outputs), deep nesting, and the EC-39 scan cap. | AC-14, AC-15, AC-20, AC-21, INV-17 to INV-20 |
| `test_prebuilt_rows_*.py` (12 files) | Exact-output and error cases for every Appendix A row, by category group. | AC-11, plus the row-level edge cases |
| `test_prebuilt_hostile_inputs.py` | Cap-sized hostile inputs, run in a child interpreter under a liveness watchdog, return their exact r6 output or error; a hostile host decimal context changes no result. | S4 R-1, R-2, R-6 to R-9, R-12, R-14; NFR-7; EC-47 to EC-49; §9.2 item 18 |

## Omitted Testing Strategies

- Wall-clock limits (AC-15's 1 second, AC-20's 2 seconds, NFR-7's build time) are not asserted, because tests must not depend on the wall clock. Peak-memory checks and infeasible-if-enumerated counts prove the same design properties structurally. The one exception, granted by the orchestrator after S4 R-14, is the liveness watchdog in `test_prebuilt_hostile_inputs.py`: a hostile call gets 30 s, about 15 times NFR-7, in a child interpreter that is killed when it overruns. It asserts no speed; it turns a hang into a red test.
- Cross-version pins of seeded draws, `ast` grammar, `ipaddress` flags, and Unicode data (EC-24, EC-25, EC-26, EC-38) are not asserted. Seeded tools are checked for determinism within one interpreter and against the generator calls their rows document.
- INV-23 (root `vidbyte.__all__` and the public API contract), INV-24 (`vidbyte.tools.builtins.__all__`), INV-25 (dependencies), and INV-26 (runtime treatment) would pass before implementation. Existing gates own them: `scripts/generate-sdk-public-api.py --check`, `scripts/check_reasoning_trace_contracts.py`, and the runtime's own tests.
- The EC-14 lone-surrogate path never reaches a tool body, because FunctionTool's JSON decoding rejects lone surrogates first. A case for it would test the framework, not the tools, so unencodable text is tested with real characters instead.
- There is no mutation testing and no random fuzzing. The schema-derived sweep is deterministic by design so a failure always reproduces.
