LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the 265-tool catalogue matches Appendix A and §9.2 almost everywhere, but two small, local bugs break weighted invariants: `extract_json_from_text` returns bare `Infinity`, and `verify_ip_address` leaks a stdlib exception for zone-scoped IPv6.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- Schema fidelity. A dump of all 265 tool schemas in 31 categories matches the Appendix A rows: names, row order, parameter order, types, defaults, numeric bounds, min and max lengths, and patterns. With `*_API_KEY` unset, the §4 snippet prints exactly the documented two lines (AC-1).
- Error contract (INV-14 and INV-15). 234,900 schema-valid fuzz calls produced no `error_type` other than `validation` and `ToolExecutionError`, except R-C2. 19,360 `ToolExecutionError` messages all match `Invalid value for '<p>': … Expected ….`. Each message names a real parameter of its tool, never echoes more than 100 characters of input, and never includes a traceback. The stricter reads in `_support.py:85–120` refuse `1e400` and integers longer than 4,300 digits. Those refusals are the guards that keep INV-11 and INV-14 true, so keep them.
- Exactness rules. The finance results follow §9.2 item 16: compound growth gives 1647.01, and the 200000 / 6% / 360-month loan gives 1199.10, a final payment of 1200.14, and 431677.04 in total. The rounding follows §9.2 item 17 and is half-even: 59.9996 s gives `1m`, 1500 ns and 2500 ns both give 2 µs, and 0.0005 gives `0s`. Unit conversion is an exact `Fraction` with one `float()`, and every Float or NumberList parameter refuses `inf` in python-mode validation.
- Boundaries. The diff adds 39 files and modifies 4, exactly as §12.3 plans, with no D-18 split module. The largest module, `json_data.py`, has 582 lines. S3 changed no test: only S2 commits `0708d57d`, `f49db5db`, and `bf26faa3` touch tests. `lint/baseline.json` and the public API contract are unchanged. In `PrebuiltTools.select_categories`, a `ToolRegistryError` names both the bad values and the valid values (INV-5).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [invariant] vidbyte/tools/builtins/prebuilt/json_data.py:249 — `extract_json_from_text` returns non-finite floats as bare `Infinity` in a success output
  Evidence: json_data.py:249 `decoder = json.JSONDecoder(parse_constant=constants.append)` sets no `parse_float` hook, and line 268 skips a candidate only `if constants or … nesting_level(value) > PREBUILT_MAX_JSON_NESTING`. Running it through the heredoc harness gives:
    `extract_json_from_text {'text': 'x {"a":1e400} y'} -> success None {"count": 1, "documents": [{"end": 13, "start": 2, "value": {"a": Infinity}}], "truncated": false}`
    `extract_json_from_text {'text': '{"a":-1e999,"b":[1E309]}'} -> success None {... "value": {"a": -Infinity, "b": [Infinity]}} ...}`
    The fuzz flagged non-JSON output (BADJSON) once in 149,194 successes, and that one was this tool on `[1e400]`. The literal constant `Infinity` is skipped correctly (`'{"a":Infinity} [1]'` keeps only `[1]`).
  Failure: Prose that embeds a JSON object or array holding a number that overflows a float, such as a model reply containing `{"a":1e400}`, gets a `success` result whose output text is not JSON. A strict parser, `JSON.parse`, or `json.loads` with a rejecting `parse_constant` fails on it. The tool's own docstring says a candidate that "holds NaN or Infinity … is skipped". `parse_json_text` already guards this case with `_read_json_float`, but this path bypasses that helper.
  Smallest fix: Give the decoder a float hook that records a non-finite value the way the constants are recorded. For example, use `json.JSONDecoder(parse_constant=constants.append, parse_float=partial(JsonDataToolFunctions._noted_float, constants))`, where the static `_noted_float(constants, text)` returns `float(text)` and appends `text` when the value is not `math.isfinite`. Then add a row case: `{"a":1e400}` is skipped and gives `count: 0`.
  Spec IDs: INV-10, INV-11 ("Floats are always finite"), INV-19, §9.2 item 5, A.17 `extract_json_from_text`, AC-11

R-C2 [Blocker] [invariant] vidbyte/tools/builtins/prebuilt/network_addresses.py:77 — `verify_ip_address` lets the stdlib's `AddressValueError` escape for every zone-scoped IPv6 address
  Evidence: network_addresses.py:77 `return {"valid": True, "version": parsed.version, "compressed": parsed.compressed, "exploded": parsed.exploded, "reason": None}` sits outside the `try` at lines 66–69. On Python 3.11.0, `ipaddress.IPv6Address('fe80::1%eth0').exploded` raises `AddressValueError Only hex digits permitted in '1%eth0' in 'fe80::1%eth0'`. The tool gives:
    `verify_ip_address {'address': 'fe80::1%eth0'} -> error AddressValueError Only hex digits permitted in '1%eth0' in 'fe80::1%eth0'`
    `verify_ip_address {'address': '::ffff:1.2.3.4%x'} -> error AddressValueError Only hex digits permitted in '304%x' in '::ffff:102:304%x'`
    The fuzz produced 20 `AddressValueError` results. Across 234,900 calls, these are the only results whose `error_type` is neither `validation` nor `ToolExecutionError`. The parameter description at line 60 invites this input: "IPv6 text may use the compressed form, an embedded IPv4 tail, or a zone suffix."
  Failure: A schema-valid address with a zone suffix, such as `fe80::1%eth0`, a common link-local form, gets `error_type: "AddressValueError"`. Its message is the `str(exc)` of a stdlib exception that echoes the input. The tool should return a successful result. `pyproject.toml` declares `requires-python = ">=3.11"`, so this happens on the supported floor. The AC-6 test (13 schema-derived argument sets per tool) does not generate a scoped address, so the pack passes (4310 passed).
  Smallest fix: Build the exploded form from the address without its zone, then put the zone back. For example: `exploded = type(parsed)(int(parsed)).exploded`, then add `%` and `parsed.scope_id` when `getattr(parsed, "scope_id", None)` is set. Then add `fe80::1%eth0` as a row case for `verify_ip_address` (`valid: true`).
  Spec IDs: INV-14 ("No other exception class ever escapes"), INV-15, AC-6, A.31 `verify_ip_address`

R-C3 [Major] [D-14 / AGENTS.md principle 5] vidbyte/tools/builtins/prebuilt/hashing.py:193 — the tolerant Base64 reader is written twice instead of once in `PrebuiltToolSupport`
  Evidence: encoding.py:218 `def _base64_bytes(data: str, url_safe: bool | None) -> bytes:` and hashing.py:193 `def _base64_bytes(text: str) -> bytes | None:` contain the same steps: `"".join(text.split())`, `rstrip("=")`, alphabet detection with `_URL_SAFE_MARKS`, `fullmatch`, the `% _BASE64_GROUP == 1` padding test, and `base64.b64decode(..., validate=True)`. The hashing docstring promises "Read Base64 the way base64_decode does". §17 deviation 5 admits the duplicate and defers it.
  Failure: The output is identical today, and the fuzz found no difference. But a change to one reader, such as alphabet detection or padding tolerance, silently splits the two. `hash_base64_content`, `compute_hmac(key_format=base64)`, and `verify_hash` would then read Base64 differently from `base64_decode`, and the hashing docstrings would become false. D-14 places shared helpers in `PrebuiltToolSupport`, and AGENTS.md principle 5 says to "have every caller use that helper instead of re-implementing the job inline". I rate this Major rather than Blocker because the duplicate lives inside one feature package, where D-14, not the `lib/` clause, governs.
  Smallest fix: Move one `PrebuiltToolSupport.base64_bytes(text: str, url_safe: bool | None) -> bytes | None` into `_support.py` (row 6). `hashing` calls it as it is. `encoding.base64_decode` keeps its own mixed-alphabet check and its messages, and raises its `argument_error` on `None`.
  Spec IDs: D-14, §12.3 row 6, §17 deviation 5

R-C4 [Minor] [contract-consistency] vidbyte/tools/builtins/prebuilt/json_data.py:74 — `verify_json_syntax` calls valid some documents that every JsonText tool refuses, and calls invalid some valid JSON
  Evidence: json_data.py:74 `json.loads(json_text, parse_constant=constants.append)` sets no float hook, while _support.py:85 `json.loads(text, parse_float=read_float, parse_constant=reject_constant)` refuses non-finite floats at :117–119. Outputs:
    `verify_json_syntax {'json_text': '{"a":1e400}'} -> success … "top_level_type": "object", "valid": true`
    `format_json {'json_text': '{"a":1e400}'} -> error ToolExecutionError Invalid value for 'json_text': the JSON contains a number too large for a float. Expected JSON whose numbers are all finite.`
    `json_get_value` with pointer `/b` on `{"a":1e400,"b":2}` returns the same error, even though the value it asks for is finite. A 4,400-digit integer, which is valid RFC 8259 JSON, gets `valid: false` with "the JSON contains an integer with more digits than the parser accepts".
  Failure: The docstring says "Use it before handing JSON to another tool". An agent that does so gets `valid: true` for a document that every JsonText tool then refuses. §17 deviation 3 records the stricter reading only for `parse_json_text`, and §9.2 item 3 lists neither refusal.
  Smallest fix: Use the R-C1 float hook in `verify_json_syntax` too, so that a non-finite float gives `valid: false` with a fixed message. Then add one sentence to the A.17 row, or to §9.2 item 3, saying that JsonText also refuses numbers that overflow a float and integers longer than 4,300 digits.
  Spec IDs: A.17 `verify_json_syntax`, §9.2 item 3, §17 deviation 3

VERIFIED CLAIMS:
1. S3 §2 says there are 39 new and 4 modified files, all inside §12.3. Held: `git diff --name-status origin/main...0fd73086`.
2. No D-18 split module was needed, and `json_data.py`, at 582 lines, is the largest module. Held.
3. S3 changed no test, fixture, or test config. Held: the only test commits are the S2 commits `0708d57d`, `f49db5db`, and `bf26faa3`.
4. `lint/baseline.json` and `contracts/sdk-public-api.json` are unchanged. Held: the `--check` run reports the contract current, and lint reports PASS.
5. AC-1, the §4 snippet output. Held exactly.
6. 265 tools in 31 categories, with schemas that match Appendix A. Held: the full dump showed no discrepancy.
7. INV-14 and AC-6: "No other exception class ever escapes". FAILED for zone-scoped IPv6 (R-C2).
8. INV-10 and INV-11: "Floats are always finite" and every output is JSON. FAILED for `extract_json_from_text` (R-C1). Held everywhere else in 149,194 success outputs.
9. §17 deviation 3: "a non-finite float such as 1e400 fail[s] as error(parameter)". Held for `parse_json_text` callers. It does not reach `extract_json_from_text` (R-C1) or `verify_json_syntax` (R-C4).
10. §17 deviation 5: the duplicated Base64 reader is harmless. It behaves the same today, but it contradicts D-14 (R-C3).
11. INV-15 message form, parameter name, at most 100 echoed characters, and no traceback. Held for 19,360 messages.
12. Every Float and NumberList parameter refuses `inf`. Held (`allow_inf_nan=False`).
13. §9.2 items 16 (finance cents) and 17 (half-even float-to-exact rounding). Held, by probes and by reading the sources of `format_duration`, `decimal_degrees_to_dms`, and `unix_timestamp_to_datetime`.
14. INV-5: `ToolRegistryError` names the bad values and all valid values, and a bare string counts as a single value. Held (I read the code).
15. Simple, clear, and useful tools (request §A). Held for a sample of 31 tools, one per category: plain names, 4-sentence descriptions, and a concrete "Use it…" sentence in each. I found no trivial or confusing tool.
16. S3 §3 reports `4310 passed`. Held, with the same count.

COMMANDS RUN:
- `git diff --name-status origin/main...0fd73086` → 39 `A` code and doc files plus 4 `M` (REPO_MAP.md, vidbyte/lib/enums/__init__.py, vidbyte/tools/README.md, vidbyte/tools/toolsets/__init__.py), besides docs/spec and the S2 tests.
- `git log --oneline origin/main..0fd73086 -- tests` → `0708d57d`, `f49db5db`, `bf26faa3` only.
- `git log --oneline 0fd73086..HEAD` → `9d8eb2f7 docs(spec): record prebuilt-agent-tools S3 completion`. That commit changes only pipeline.md, so the code at HEAD is identical to the reviewed SHA.
- The §4 snippet, run as a heredoc with `*_API_KEY` unset → `('days_between_dates', 'count_character_occurrences')` / `success {"count": 3, "positions": [2, 7, 8], "truncated": false}`, exit 0.
- A schema dump of all 265 tools, checked against Appendix A → no discrepancy.
- About 200 targeted row probes in all 31 categories, through a heredoc harness (`T={t.name:t for t in PrebuiltTools(PrebuiltToolCategory)}; asyncio.run(T[n].execute(ToolCall(n,args)))`) → all matched their rows except R-C1, R-C2, and R-C4.
- A schema-valid fuzz with 3 seeds and up to 300 calls per tool, run on 259 tools (6 tools that are slow under EC-10 and EC-46 were skipped) → `DONE {'success': 149194, 'ToolExecutionError': 84786, 'validation': 900, 'AddressValueError': 20} secs 33`. The only BADJSON hit was `extract_json_from_text`. An earlier, unbounded fuzz attempt was killed by its timeout (exit 143) and gave no output.
- An INV-15 message check with seed 11 and 200 calls per tool → `DONE TEE messages checked 19360 {}`.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools` → `4310 passed in 20.81s`.
- `PYTHONPATH=$(pwd) python lint/run.py` → `SDK-LINT: PASS`.
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).`
- `python -c "import ipaddress; ipaddress.IPv6Address('fe80::1%eth0').exploded"` on 3.11.0 → `AddressValueError Only hex digits permitted in '1%eth0' in 'fe80::1%eth0'`.
- `grep -rn "1e400\|1E400\|1e999\|%eth\|zone" tests/features/prebuilt_tools/` → the only hit is the `python_literal_to_json` `1e999` case. No case covers `extract_json_from_text` with an overflowing float or a scoped IPv6 address.
- `git status --short` → the only untracked file belongs to another reviewer. This review changed no file except this report.
