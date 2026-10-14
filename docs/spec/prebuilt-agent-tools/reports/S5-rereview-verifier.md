# S5 re-review round 1 — findings verifier report

**Scope.** This is a scoped verification:
- The only review this round is reports/S5-rereview.md (the conformance lens). The other two inputs were "none this round".
- I verified R-C1, R-C2 and R-C3.
- I swept for Blocker-class blind spots next to them, as step 6 asks.

**Code reviewed.** HEAD is `f3bbee92`, with code last changed at `c8eefe53`. The worktree is clean apart from my two files.

**How I measured.**
- Interpreter: Python 3.11.0, the dev and CI interpreter. I used 3.13.1 only for the cross-version checks, through standard-library-only scripts.
- Probes live in the session scratchpad folder `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/c033bb4d-236f-4839-b20c-c5c2bef451e8/scratchpad/s5v/`. Below it is called `s5v/`.
- Every call goes through `FunctionTool.execute`, exactly as in review.md's reproducer block.

**Output.** I appended to review.md:
- one verdict line;
- R-15 to R-17 in a new section;
- M-6 in the Minor table;
- new "gets right" items.

No existing row or status changed: `git diff --numstat` gives `42 0`.

## 1. Merge map

| Original | Source | Merged ID | Severity | Disposition |
|---|---|---|---|---|
| R-C1 | S5-rereview | R-15 | Blocker | CONFIRMED |
| R-C2 | S5-rereview | R-16 | Blocker | CONFIRMED |
| R-C3 | S5-rereview | M-6 | Minor | CONFIRMED (`trivial`; the spec author owns it) |
| — | verifier, step 6 | R-17 | Blocker | NEW: a bypass of the R-6 pre-scan, in the same lines as R-C1 |

**IDs and order.**
- There was only one review, so no findings merged.
- Nothing was refuted or downgraded.
- I numbered the Blockers by fix size, smallest first:
  - R-15 is one raw-string constant.
  - R-16 is a regex, three lines and an import.
  - R-17 is a new pattern and a three-line loop change.
- **R-15 and R-17 must land in one commit,** because R-15's fix alone widens R-17.

## 2. Verifications

### R-15 (R-C1): the TOML dotted-key pre-scan is quadratic — CONFIRMED, Blocker

**The code.** `structured_formats.py:61` defines `_TOML_KEY_SEGMENT`, whose double-quoted alternative is `"(?:[^"\\\n]|\\.)*+"`.
- `:62` builds `_TOML_DOTTED_RUN` from it.
- `:63` builds `_TOML_SEGMENT` from it.
- `_has_long_dotted_key` (`:422-428`) runs `finditer` over the whole text before `tomllib` (`:225`).
- On `"\"\"\"…`, every `"` starts an attempt that reads `\"` escapes to the end of the line and then fails for lack of a closing quote. The next attempt starts one quote later.

**My measurements** (`s5v/v2_toml.py current rc1`), on the text `"# " + '"' + '\\"'*k + "\na = 1"`:
```
pre-scan comment k=5000    len=10,009  refused=False  0.138s
pre-scan comment k=10000   len=20,009  refused=False  0.558s
pre-scan comment k=20000   len=40,009  refused=False  2.239s
comment k=20000 (tool)     len=40,009  success None   2.261s :: {"value": {"a": 1}}
tomllib alone              len=40,009  parsed         0.000s
```
The time grows 4× per doubling. Extrapolated to 1,000,000 characters: 2.239 × (1,000,000 / 40,009)² ≈ 1,400 s, about 23 minutes.

**Origin.** The pattern came from the R-6 fix:
- `git log -1 a9b54ff1` → `fix(prebuilt-tools): refuse an over-long dotted TOML key before parsing [R-6]`.
- `git show 0fd73086:vidbyte/tools/builtins/prebuilt/structured_formats.py | grep -c _TOML_DOTTED_RUN` → `0`.

**A second failure of the same constant on 3.11.0, which I found.** Python 3.11.0's `re` mis-handles a failed iteration of a possessive group, and it lets a run continue across an unterminated quote. The tool output is wrong on 3.11.0. On the text `"k" + ".k"*59 + '."' + "k" + ".k"*60 + " = 1"`:
```
# Python 3.11.0
3.11.0 current scan counts: [122]
current: error ToolExecutionError :: Invalid value for 'toml_text': the TOML is nested deeper than 100 levels. ...
# Python 3.13.1, standard-library copy of the same pattern
3.13.1 current scan counts: [60, 61, 1]
```
- With the verifier prototype, the same text gives `error ToolExecutionError :: Invalid value for 'toml_text': the text is not valid TOML 1.0`.
- Over 80,000 random texts, the shipped pattern's per-run segment counts hash differently on 3.11.0 and 3.13.1 (`8b05ea44…` against `7fa0e78d…`). The prototype's counts hash the same on both (`0ac5e7b8…`).
- INV-12 binds only within one minor version, and I had no later 3.11 patch release to test. So I record this as evidence and a regression case under R-15, not as its own finding. R-15's fix removes it.

**(a) Is the expected behavior pinned by spec r6? Yes.**
- NFR-7 (`spec.md:266`): "Each call at the largest input its schema allows takes ≤ 2 s …". The only exceptions are EC-10 and EC-46.
- The A.20 `toml_to_json` row (`spec.md:1480`):
  - The comment case holds no dotted run, so its result is `tomllib.loads` → `{"value": {"a": 1}}`.
  - The run-merge case holds no run of more than 100 bare or quoted segments, so it gets the row's invalid-TOML message.

**(b) Regression cases.**
1. Watchdog success case: `"# " + '"' + '\\"'*499_995 + "\na = 1"` (999,999 characters) → `{"value": {"a": 1}}`.
2. Watchdog failure case: `"x = " + '"' + '\\"'*499_990` → error(`toml_text`) containing "the text is not valid TOML 1.0".
3. In-process failure case: `"k" + ".k"*59 + '."' + "k" + ".k"*60 + " = 1"` → error(`toml_text`) containing "the text is not valid TOML 1.0".

Cases 1 and 2 need the 30 s watchdog, because today they are quadratic and take minutes. With the fix they take 0.011 s and 0.124 s.

**(c) The fix.** Use the re-reviewer's constant, with optional closing quotes. Land it only as part of R-17's fix (§4).
- Lint: it is a raw-string change, with no A007 literal and no comment change.

### R-16 (R-C2): `parse_data_size` leaks `InvalidOperation` — CONFIRMED, Blocker

**The code.** `bits_bytes.py:49` defines `_NUMBER_PREFIX`, which allows `([eE][+-]?[0-9]+)?`: an exponent of any length.
- `:106` runs `number = Decimal(number_match.group())` before the float check at `:107`.
- `Decimal(str)` converts exactly, inside a maximum context. It signals `InvalidOperation` through the thread's context when the exponent is past ±999,999,999,999,999,999.

**My measurements** (`s5v/v1_data_size.py`):
```
default context
  "1e99999999999999999999 B"  -> error InvalidOperation :: [<class 'decimal.InvalidOperation'>]
  "1e-99999999999999999999 B" -> error InvalidOperation
  "-1e-99999999999999999999 B"-> error InvalidOperation
  "0e99999999999999999999 B"  -> error InvalidOperation
  "0e-99999999999999999999 B" -> error InvalidOperation
  "1e999999999999999999 B"    -> error ToolExecutionError (18-digit control)
  "1e-999999999999999999 B"   -> success {"size_bits": 0.0, "size_bytes": 0.0}
  "-1e-500 B"                 -> error ToolExecutionError (negative)
no-trap host context
  "1e99999999999999999999 B"  -> error ToolExecutionError
  the other four              -> error ValueError :: cannot convert NaN to integer ratio
```

**Origin.** `git show 0fd73086:…/bits_bytes.py | grep -n "Decimal(number_match\|^_NUMBER_PREFIX"` gives lines `49:` and `106:`, unchanged since S3.

**Sweep** (`git grep -n "Decimal(" vidbyte/tools/builtins/prebuilt`). Every other site that builds a `Decimal` from text is safe:

| Site | Why it is safe |
|---|---|
| `_support.py:192` | `_DECIMAL_TEXT` has no exponent |
| `number_formatting.py:207` | `_ABBREVIATED_NUMBER` has no exponent, and the call runs inside `decimal_context` |
| `number_formatting.py:371` | digits only |
| `text_extraction.py:221` | the exponent is bounded at `:219` by `PREBUILT_MAX_DECIMAL_TEXT_CHARS` |
| `text_extraction.py:255` | `_AMOUNT` has no exponent |
| `timestamps_durations.py:297`, `:306`, `:323` | `_DURATION_NUMBER` has no exponent |
| `encoding.py:242`, `finance.py:296-298`, `geometry.py:180`, `timestamps_durations.py:254` | `repr` of a finite float or a capped int |
| the remaining sites | constants |

- `Fraction(` from text is safe at every site: the geometry DMS pattern has no exponent, and the other sites read floats or exponent-free decimal text.
- Probe `s5v/v10_decimal_sweep.py` gives only success, `ToolExecutionError`, or `validation` for `extract_numbers`, `extract_money_amounts`, `parse_abbreviated_number`, `parse_duration_text` (phrase and ISO forms), `decode_jwt_payload` ("a number too large for a float") and `decimal_degrees_to_dms`, under both host contexts.

**(a) Is the expected behavior pinned by spec r6? Yes.**
- INV-14 (`spec.md:141`): only `"validation"` or `"ToolExecutionError"`.
- The A.27 `parse_data_size` row (`spec.md:1576`):
  - The number must be "numeric under §9.2 item 15".
  - The size is "computed exactly in `Fraction` … converted to `float` once".
  - "An unknown unit, a negative value, or text in any other form → error(`text`)".
- §9.2 item 15 (`spec.md:488`): text is numeric when "`float()` of it is finite".

So:
- `1e99999999999999999999 B` → error(`text`).
- `1e-99999999999999999999 B`, `0e±99999999999999999999 B` → `{"size_bytes": 0.0, "size_bits": 0.0}`.
- `-1e-99999999999999999999 B` → error(`text`), the same as `-1e-500 B` today.
- The current message, "the number is negative or outside the floating-point range", already has the INV-15 form.

**(b) Regression cases.** Run them in-process; no watchdog is needed, since each call takes 0.001 s.
- The five inputs above, with the outputs in (a).
- The tiny and zero forms again, under a host `decimal.Context(traps=[])`. Today they give `ValueError`.

**(c) The fix.** I chose a smaller fix than the reviewer's. It bounds the exponent from the match text, as `text_extraction._number_entry:218-220` does. Because it never builds an out-of-range `Decimal`, the result cannot depend on the host's decimal context. The exact code is in §4.
- Prototype (`s5v/s5v_data_size_patch.py`): every case above is correct under the default and the no-trap host context.
- `pytest … -p s5v_data_size_patch -p s5v_toml_lexer` → `4352 passed in 37.51s`.
- A full-file copy (`s5v/proposed/bits_bytes.py`) gives `before A007=0, after A007=0 comment lines over 72 columns: 0`. A007 matches whole `_`-separated name parts, so `CHARS` does not hit the `char` token.
- **The re-reviewer's alternative** builds inside `decimal_context` and catches `InvalidOperation`. It is kept as a runner-up with one correction. Its rule "a number whose `float()` is 0.0 gives zero bytes" would return 0 bytes for `-1e-99999999999999999999 B` (float -0.0), which the row refuses as a negative value. Read the sign from the mantissa instead.

### R-17 [verifier]: the R-6 pre-scan can be bypassed — NEW, Blocker

**The mechanism.** The pre-scan pairs quotes greedily from left to right with one-line segment patterns. It never sees `'''` or `"""` as a delimiter.
- A multi-line string whose quote characters add up to an odd number leaves the scan one quote off for the rest of that line. Examples are `'''it's'''` (a valid multi-line literal string) and `"""a"b"""`.
- A later "quoted segment" then swallows the real key that follows. In current code, that needs a later quote on the line, such as `, u = 'v'`.
- So a dotted key of any length inside an inline table reaches `tomllib`, which is quadratic in its segments (R-6).

**My measurements.** From `s5v/v2_toml.py current small bypass` and `s5v/v9_bypass_big.py`:
```
t = { s = '''it's''', a.b.c = 1, u = 'v' } -> {"t": {"s": "it's", "a": {"b": {"c": 1}}, "u": "v"}}
pre-scan ml-literal + later quote n=20000   len=40,038   refused=False  0.000s
ml-literal + later quote n=20000            len=40,038   error ToolExecutionError 0.196s :: …nested deeper than 100 levels…
ml-literal + later quote n=40000            len=80,038   error ToolExecutionError 0.723s
ml-literal + later quote n=80000            len=160,038  error ToolExecutionError 2.828s
tomllib alone ml-literal + later quote n=80000           parsed 2.771s
ml-basic + later quote n=80000              len=160,037  error ToolExecutionError 2.808s
n=160000 len=320,038 error ToolExecutionError 15.929s
```
NFR-7 breaks at 16% of the cap, and the cost at the cap is several minutes.

**Fuzz** (`s5v/v4_fuzz.py`). Each generated text is a valid TOML line with a 101-segment inline-table key, placed after 1 to 3 random strings of every kind, with an optional comment line before it:
```
valid texts with a 101-segment key: 57522
current scan misses: 9963
prototype misses: 0
```

**Interaction with R-15** (`s5v/v2_toml.py proto bypass`). With only R-15's constant, the trailing quote is no longer needed:
```
ml-literal, no later quote n=80000  current:   error 0.008s (refused by the scan)
ml-literal, no later quote n=80000  R-15 only: error 2.850s (not refused)
```
**Reach.** A bare key or a table header always starts its line, so nothing earlier on the line can shift the pairing. Only keys after a multi-line string on the same line are exposed: inline tables, and arrays of inline tables.

**(a) Is the expected behavior pinned by spec r6? The output is; the speed is not met.**
- The A.20 row (`spec.md:1480`) requires error(`toml_text`) with the nesting message, which the tool returns, but only after `tomllib` finishes. NFR-7 (`spec.md:266`) is what fails.
- **Spec decision needed.** The row's last sentence reads: "The scan does not track strings or comments, so such a run inside a multi-line string or a comment is refused too." Question: may the pre-scan skip comments and multi-line strings whole, so that a long dotted run inside them is accepted when `tomllib` accepts it?
- **My recommendation: yes.** It means fewer over-refusals and the smallest code.
- **Flip condition.** If the spec keeps those refusals, the fix must also run `_TOML_DOTTED_RUN` over the text of each skipped piece. That stays linear and is about two more lines.

**(b) Regression cases.**
- Watchdog failure cases, each → error(`toml_text`) with the nesting message:
  - `"t = { s = '''it's''', " + "a."*499_900 + "a = 1, u = 'v' }"` (999,838 characters)
  - the same without `, u = 'v'` (999,829 characters)
  - `'t = { s = """a"b""", ' + "a."*499_900 + 'a = 1, u = "v" }'`
- In-process, once the spec agrees: `"# " + "a."*101 + "a\nb = 1"` → `{"value": {"b": 1}}`. Today this gives the nesting error, which the current row text pins.

**(c) The fix.** The exact code is in §4. Prototype results (`s5v/s5v_toml_lexer.py`; `s5v/v3_lexer.py` for the cap-size checks):
- Cap-size shapes, each ≤ 0.125 s:

  | Shape | Time |
  |---|---|
  | comment of escaped quotes | 0.011 s |
  | unterminated basic string of escaped quotes | 0.124 s |
  | `'`×999,999 | 0.022 s |
  | `"""` openers repeated | 0.054 s |
  | `'''` openers repeated | 0.051 s |
  | R-6 bare, header and inline forms | 0.046 s each |
  | quoted-segment key | 0.039 s |
  | each bypass shape | ≤ 0.047 s |

- Still accepted: the 100-segment key, and 400,000 `a.` in a basic (0.064 s) or literal (0.013 s) string.
- Fuzz: 0 misses.
- Cross-version: identical per-run segment counts on 3.11.0 and 3.13.1 (`s5v/v12_cross_version.py`, `v16_counts.py`).
- Pack with the prototype: `4352 passed in 35.65s`.
- Lint: the full-file copy (`s5v/proposed/structured_formats.py`) gives `before A007=0, after A007=0 comment lines over 72 columns: 0`.

**A trap I hit while prototyping.** The first prototype wrote the multi-line content as a possessive `(?:…|"(?!""))*+`, and it missed 4,537 of the 57,522 fuzz texts. Python 3.11.0 mis-matches a possessive repeat whose body ends in a failing lookahead (`s5v/v8_re.py`):
```
'x(?:"(?!""))*+' on 'x""""'  -> 'x"""'   (3.11.0)
'x(?:"(?!""))*+' on 'x""""'  -> 'x'      (3.13.1)
```
An atomic group `(?>(?:…)*)` gives the right answer on both. No shipped prebuilt pattern puts a lookaround inside a possessive repeat. The only near cases are `text_extraction.py:60` and `:68`, where the lookarounds sit outside the repeats.

### M-6 (R-C3): §9.2 row drift — CONFIRMED, Minor, `trivial`

`spec.md:659` reads "fill_text_template and get_python_function_signature error messages". `git grep -n "shortened_names\|PREBUILT_MAX_REPORTED_NAMES" -- vidbyte` finds four users:

| Site | Tool or error |
|---|---|
| `code_analysis.py:233` | `get_python_function_signature` |
| `csv_tables.py:313-314` | `_column_index`, the CSV missing-column error |
| `graphs.py:267` | `_cycle_text`, the `topological_sort` cycle error |
| `text_transform.py:359` | `fill_text_template` |

Behavior conforms; only the spec text is out of date. The spec author owns the fix.

## 3. Adjudications and calibration

1. **Severity of R-15 and R-17.** I kept both as Blockers, on two grounds:
   - The spec text: NFR-7 (`spec.md:266`) exempts only EC-10 and EC-46, and T-2 (`spec.md:705`) assigns crafted input to the caps "sized to NFR-7".
   - S4's own calibration: R-1, R-2, R-6 and R-8 were crafted inputs within the caps, costing minutes at the cap, and all were Blockers.

   The briefing calls NFR-7 a bound on "non-adversarial input". The spec text does not say that, so I followed the spec. R-15 is also a regression that a fix introduced.
2. **Severity of R-16.** Blocker, consistent with S4's R-3: a raw exception class leaking out breaks INV-14 on schema-valid input.
3. **The re-reviewer's claim that "the pack passes with the prototype".** That evidence is weaker than it looks. The R-6 watchdog cases run in a child interpreter (`test_prebuilt_hostile_inputs.py` `CHILD_PROGRAM`), which does not load a `-p` plugin. So in a `-p` run those cases test the shipped code, not the prototype. My in-process probe `v3_lexer.py` covers the same shapes with the prototype loaded.
4. **The re-reviewer's R-C1 fix.** It is correct for R-C1, but it widens the R-17 hole. It is superseded by the combined fix, which contains it.
5. **The re-reviewer's R-C2 fix.** It is replaced by the exponent-bound fix. Theirs is kept as a runner-up with the sign correction (§2, R-16 (c)).
6. **R-6's row** stays `fixed @a9b54ff1`, because the briefing makes the table append-only. R-17 records that the fix is incomplete.

## 4. Exact code of the proposed fixes

These are not escaped for a table. Full-file copies are in `s5v/proposed/`.

**R-15 and R-17, in one commit.** `structured_formats.py:61-63`:
```python
_TOML_KEY_SEGMENT = r"""[A-Za-z0-9_-]++|"(?:[^"\\\n]|\\.)*+"?|'[^'\n]*+'?"""
_TOML_DOTTED_RUN = rf"(?:{_TOML_KEY_SEGMENT})(?:[ \t]*+\.[ \t]*+(?:{_TOML_KEY_SEGMENT}))*+"
_TOML_SCAN_PIECE = re.compile(
    r"""#[^\n]*+"""
    + r"""|"{3}(?>(?:[^"\\]|\\[\s\S]|"(?!""))*)(?:"{3,5}+)?"""
    + r"""|'{3}(?>(?:[^']|'(?!''))*)(?:'{3,5}+)?"""
    + rf"|(?P<run>{_TOML_DOTTED_RUN})"
)
_TOML_SEGMENT = re.compile(_TOML_KEY_SEGMENT)
```
And in `_has_long_dotted_key` (`:424-428`):
```python
        # Comments and multi-line strings are skipped whole, so a quote
        # inside one cannot hide a key later on its line. Only a run
        # with enough dots can be too long, so the exact count, which
        # skips dots inside quoted segments, is rare.
        for piece in _TOML_SCAN_PIECE.finditer(toml_text):
            run = piece["run"]
            if run and run.count(".") >= PREBUILT_MAX_JSON_NESTING and len(_TOML_SEGMENT.findall(run)) > PREBUILT_MAX_JSON_NESTING:
                return True
        return False
```
Also update:
- the `_has_long_dotted_key` docstring, to say "outside comments and multi-line strings";
- the A.20 row's last sentence, after the spec decision.

The module header's FUNCTION INVENTORY entry stays accurate.

**R-16.** `bits_bytes.py:49` and `:104-114`, plus the import of `PREBUILT_MAX_DECIMAL_TEXT_CHARS`:
```python
_NUMBER_PREFIX = re.compile(r"(?P<mantissa>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))(?:[eE](?P<exponent>[+-]?[0-9]+))?")
...
        # @intent prebuilt-data-size-exponent-text
        # Decimal refuses an exponent of more than 18 digits, so a far
        # exponent is read from the mantissa alone: the float check
        # below refuses it unless the size is zero bytes or negative.
        far = abs(int(number_match["exponent"] or 0)) > PREBUILT_MAX_DECIMAL_TEXT_CHARS
        number = Decimal(number_match["mantissa"] if far else number_match.group())

        # The number must be finite as a float and not negative.
        if not math.isfinite(float(number_match.group())) or number < 0:
            ...
        tiny = far or number.is_zero() or number.adjusted() < _SMALLEST_SIZE_EXPONENT
```

**Why this bound is safe.** The mantissa has at most 200 characters, and the bound is 4,002, so:
- a far positive exponent on a non-zero mantissa is always `inf` as a float, and the existing check refuses it;
- a far negative exponent is always below 10^-3800, which is zero bytes.

A002 does not apply, because `parse_data_size` has no policy token. A single `@intent` block, merged with the existing `prebuilt-data-size-exponent-bound`, is also fine.

## 5. Observation outside the findings (for the orchestrator, not the repair list)

**The local pack can stall on this Windows machine.** Three of the nine full-pack runs I started stalled, and the immediate re-run passed each time:
- One `-q` run was killed by its 400 s timeout.
- One `-v` run stopped at `test_prebuilt_side_effects.py::test_tool_calls_touch_no_outside_resource[parse_data_size]`. The process sat idle: its CPU stayed at 16.58 s, with 2 threads.
- One run with `-o faulthandler_timeout=60` dumped this stack (`s5v/full_2.log`):
```
socket.py:293 in accept
socket.py:644 in socketpair
asyncio/proactor_events.py:780 in _make_self_pipe
asyncio/events.py:805 in new_event_loop
asyncio/runners.py:189 in run
tests/features/prebuilt_tools/prebuilt_tool_harness.py:214 in result
tests/features/prebuilt_tools/test_prebuilt_error_contract.py:92 in call_problems
```

**What this tells us.**
- The harness calls `asyncio.run` once per tool call. On Windows, each new event loop builds a loopback TCP `socketpair()` in pure Python, and that pair's blocking `accept()` occasionally never returns.
- The trigger is the environment, not tool code. Only 2 sockets were in TIME_WAIT afterwards, and the side-effects file alone passed 3 of 3 runs, each in about 2.6 s.
- CI on Linux uses a native `socketpair`.

**Advice.** Pass `-o faulthandler_timeout=60` when you run the pack locally, so a stall shows up as a stack rather than a silent hang, and rerun once before treating a stall as a regression.

## 6. Commands run (final lines)

| Command | Final lines |
|---|---|
| `python -u s5v/v1_data_size.py` | the R-16 table in §2 |
| `python -u s5v/v2_toml.py current rc1 small` | `pre-scan comment k=20000 len=40,009 refused=False 2.239s`; `comment k=20000 (tool) … success None 2.261s` |
| `python -u s5v/v2_toml.py current bypass` | `ml-literal + later quote n=80000 len=160,038 error ToolExecutionError 2.828s` |
| `python -u s5v/v2_toml.py proto rc1 rc1big r6 bypass` | `ml-literal, no later quote n=80000 len=160,029 error ToolExecutionError 2.850s` |
| `python -u s5v/v9_bypass_big.py` | `n=160000 len=320,038 error ToolExecutionError 15.929s` |
| `python -u s5v/v3_lexer.py` (prototype) | every line ≤ 0.125 s; the acceptances succeed |
| `python -u s5v/v4_fuzz.py` | `valid texts with a 101-segment key: 57522` / `current scan misses: 9963` / `prototype misses: 0` |
| `python -I s5v/v16_counts.py` on 3.11.0 and on 3.13.1 | current `8b05ea44c7598941` against `7fa0e78d294d77ad`; prototype `0ac5e7b82b669888` on both |
| `python -u s5v/v21_merge_key.py` and `… proto` | current: the nesting message; prototype: `the text is not valid TOML 1.0` |
| `python -u s5v/v10_decimal_sweep.py` | no error type other than `ToolExecutionError` or `validation` |
| `python -u s5v/v20_proposed.py <worktree> s5v/proposed` | `bits_bytes.py before A007=0, after A007=0 comment lines over 72 columns: 0`; `structured_formats.py before A007=0, after A007=0 comment lines over 72 columns: 0` |
| `pytest -p no:cacheprovider -p s5v_toml_lexer tests/features/prebuilt_tools -q` | `4352 passed in 35.65s` |
| `pytest -p no:cacheprovider -p s5v_data_size_patch -p s5v_toml_lexer tests/features/prebuilt_tools -q` | `4352 passed in 37.51s` |
| `pytest -p no:cacheprovider tests/features/prebuilt_tools -q --durations=8` (baseline at HEAD) | `4352 passed in 35.99s` |
| `git diff --numstat -- docs/spec/prebuilt-agent-tools/review.md` | `42 0` |

All commands ran from the worktree with `PYTHONPATH` set to the worktree (plus `s5v/` for the plugins) and `PYTHONIOENCODING=utf-8`.

## 7. Open items

None. R-17's fix waits on the one-line spec decision in §2, which the orchestrator routes to the spec author.
