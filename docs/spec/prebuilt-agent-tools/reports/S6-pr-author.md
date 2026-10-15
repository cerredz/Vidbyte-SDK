# S6 PR author report: prebuilt-agent-tools

Date: 2026-10-14 · Branch: `feat/prebuilt-agent-tools` · Gates run at `8c37990b` (code last changed at `70298784`) · PR: https://github.com/cerredz/Vidbyte-SDK/pull/1072 (draft, base `main`)

## 1. What I produced

- `docs/spec/prebuilt-agent-tools/pr-body.md`: title line plus body (31,655 bytes with the title line; well under 60,000). The PR title and body were replaced from it with `gh pr edit`; the remote body matches the file byte for byte, apart from the trailing newline `gh -q` adds.
- `docs/spec/prebuilt-agent-tools/spec.md`: frontmatter `status: verified` → `pr-open` (revision 7, `updated: 2026-10-14`, and `pr:` were already correct), and one §17 row: `| r7 | 2026-10-14 | S6 PR | finalized for review |`. No other spec text changed.
- This report.

No source, test, test-plan, review, verify-log, or pipeline file was edited.

## 2. How I read the code (code first, spec second)

I read the full diff before the spec: `vidbyte/tools/toolsets/prebuilt.py`, `vidbyte/tools/builtins/prebuilt/_support.py`, its `__init__.py` and README, both enum modules and both constant modules, and six category modules in full (`text_counting`, `text_extraction`, `structured_formats`, `json_data`, `exact_arithmetic`, `dates`); the rest by header and tool inventory.

- `PrebuiltTools.__init__` is narrated and calls `select_categories` (one member or a bare `str` counts as one value; anything that is not a `PrebuiltToolCategory` raises `ToolRegistryError` naming every bad and every valid value; returns distinct members in enum order), then `get_tools` (a fresh `FunctionTool(function)` per function through the read-only `_CATEGORY_FUNCTIONS` table), then `Tools.__init__`, which refuses duplicate names. Nothing is cached or built at import.
- The existing `FunctionTool` does all model-facing work: the args model from the signature, the docstring as description, JSON-mode validation (`error_type: "validation"`), `asyncio.to_thread`, any raise as a failure named by the exception class, and `_stringify_output` (`json.dumps(sort_keys=True, ensure_ascii=False)`).
- `PrebuiltToolSupport` holds the shared rules: the one `argument_error` builder, JSON, number, date, line, word, CSV, Base64, and HTML helpers, `decimal_context`, and `cap_items`.
- Counts: 265 tools in 31 categories (6 to 12 each); 68 enums (58 + 10); 43 non-doc, non-test files (39 added, 4 modified); 26 test files with 4,397 tests; the full library builds in 0.2 s.

The §5 flow matches the code, so §5 needed no update.

## 3. The usage snippet

I ran spec §4 exactly as written (scratchpad copy, Python 3.11.0, every `*_API_KEY` unset). It printed:

```
('days_between_dates', 'count_character_occurrences')
success {"count": 3, "positions": [2, 7, 8], "truncated": false}
```

AC-1 holds with no deviation. I also confirmed four example calls quoted in the body: `add_to_date` 2024-01-31 + 1 month gives `{"clamped": true, "date": "2024-02-29"}`, `decimal_arithmetic` 0.1 + 0.2 gives `{"exact": true, "result": "0.3"}`, a zero divisor gives `ToolExecutionError` with the documented message, and `start_date` `2024-02-30` gives `validation`.

## 4. Gates I ran myself at `8c37990b` (Windows 11, Python 3.11.0)

| Gate | Final line(s) |
|---|---|
| `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -o faulthandler_timeout=120 tests/features/prebuilt_tools` | `4397 passed in 53.47s` |
| `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | `SDK-LINT: PASS` (S009 `RATCHETED: 350 known finding(s)`), `reasoning trace contracts: ok (182 tools, 55 shapes)`, `8412 passed, 13 skipped in 86.76s`, `CI passed.` |
| `python scripts/run_ci.py --stage package` (no `PYTHONPATH`) | `No broken requirements found.`, `Installed vidbyte-sdk 0.2.1 passed smoke checks.`, `CI passed.` |
| semgrep 1.170.1 `scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | `Ran 1 rule on 931 files: 0 findings.` (exit 0) |
| `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | `contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).` |
| `git diff origin/main...HEAD -- lint/baseline.json` | empty |
| row-case collection | 1,381 `_return_documented_output` cases covering all 265 tools; 532 `_reject_bad_input` cases |

Remote: `gh pr checks` → `no checks reported on the 'feat/prebuilt-agent-tools' branch` (exit 1). CI is disabled repo-wide (dispatch-only workflows), so this is expected; nothing was dispatched.

Semgrep note: the scratchpad venv's `semgrep.exe` hands off to whichever `pysemgrep` comes first on `PATH`. The global Python 3.11 `pysemgrep` crashes on import because the global `mcp` is 2.x (`No module named 'mcp.server.fastmcp'`). Putting the venv's `Scripts` first on `PATH` in POSIX form (`/c/Users/...`) fixed it; a Windows-form `C:/...` entry does not work in Git Bash's colon-separated `PATH`.

## 5. Deviations reported in the PR body (4)

1. R-C1: `extract_numbers` skips a non-zero number whose exponent is past 4,002 even when it fits (`1000e-4003` → nothing, `1e-4000` → listed; reproduced at HEAD). The A.29 row lacks the clause §9.2 item 18 promises, and the reason given at `text_extraction.py:220-223`, `:9`, and `:120` is false for that case.
2. `_support.py` has helpers beyond §12.3 row 6's named list. `json_data.py:77` and `:271` use the private `PrebuiltToolSupport._read_json_float` from another class.
3. A private nested `_CaseKeepingConfigParser` (S3 deviation 4).
4. Spec §17's S3 deviation list is partly stale: deviation 5 is gone since `6ea8bfb1`, and deviation 1's local names changed in `fb22c691`.

Follow-ups in the body: R-C1; M-5 (sites re-verified at HEAD); 5 accepted limitations, including the TOML scan's ~98 MB transient memory; Q-1 to Q-6, with Q-6 (dict outputs, D-7 exception to AGENTS.md principle 4) called out; 3 test-pack gaps; 2 local flakes.

## 6. Final PR state

```
gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1072 --json title,isDraft,baseRefName,url
{"baseRefName":"main","isDraft":true,"title":"feat(prebuilt-tools): add 265 prebuilt deterministic agent tools in 31 categories","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1072"}
gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1072
no checks reported on the 'feat/prebuilt-agent-tools' branch
```

## 7. Observations for the owner (not fixed here; no source edits allowed)

- `vidbyte/tools/builtins/prebuilt/text_extraction.py:220-223`: the comment says any non-zero far-exponent value "would be too long to write out". That is false for `1000e-4003`. The same reason appears in the module header (`:9`) and in the tool description (`:120`).
- `vidbyte/tools/builtins/prebuilt/json_data.py:77` and `:271`: cross-class use of the private hook `PrebuiltToolSupport._read_json_float`. No lint rule flags it, but it breaks the underscore convention.
- `docs/spec/prebuilt-agent-tools/spec.md` §6.2, AC-11 row: says 1,339 and 511 cases. The pack now has 1,381 and 532 (stale S2 numbers).
- `docs/spec/prebuilt-agent-tools/spec.md` §17, "Implementation deviations (S3)", items 1 and 5 are stale (see §5 above).

## 8. Candidate field-guide lessons (for the orchestrator; I did not write to the field guide)

- Trigger: a tool or parameter description needs to illustrate a rule. · Action: state the rule in words; never put a literal example value in a model-facing description. · Reason: the model copies example values into calls, and AC-8's `no_example` tests check for them (R-4, `a57738f1`). · Check: `pytest tests/features/prebuilt_tools/test_prebuilt_model_facing_contract.py`. · PR #1072.
- Trigger: decimal work runs inside `FunctionTool` (in a worker thread). · Action: open a fresh, fully specified `decimal.Context` (precision, rounding, traps, Emin/Emax), never `localcontext(prec=…)`. · Reason: `asyncio.to_thread` copies the caller's context, so the host's traps and exponent range leak in (R-12, `43b692d5`). · Check: the `host-traps-nothing` hostile cases. · PR #1072.
- Trigger: a tool parses HTML with `html.parser.HTMLParser`. · Action: drop an unprocessed `<` tail before `close()`. · Reason: CVE-2025-6069 makes `close()` quadratic on 3.11.0 (hours at the cap), and patched releases produce different text (R-8, `166b355a`). · Check: `test_prebuilt_hostile_inputs.py` R-8 cases. · PR #1072.
- Trigger: a tool calls a stdlib parser or constructor on model input (`ipaddress`, `Decimal`). · Action: probe the extreme forms (zoned IPv6, 19+ digit exponents) and convert every exception to `ToolExecutionError`. · Reason: `AddressValueError` and `InvalidOperation` leaked past review twice (R-3, R-16). · Check: the AC-6 error-contract test. · PR #1072.
- Trigger: a regex pre-scan is added to guard a parser. · Action: make it a single linear pass that knows the format's string and comment syntax; test it on runs of quotes and escapes at the cap. · Reason: the R-6 guard was itself quadratic (R-15) and bypassable (R-17). · Check: the cap-sized TOML hostile cases under the 30 s watchdog. · PR #1072.
- Trigger: two category modules need the same rule. · Action: put one helper in `PrebuiltToolSupport` and keep call chains one hop deep. · Reason: R-13 (seven commits) and R-11 came from rules written two to four times and from a three-level helper chain. · Check: grep the constant or regex across `vidbyte/tools/builtins/prebuilt/`. · PR #1072.
- Trigger: running semgrep from a scratch venv on this machine. · Action: put the venv's `Scripts` first on `PATH` in `/c/...` form. · Reason: `semgrep.exe` otherwise runs the global `pysemgrep`, which fails on `mcp` 2.x. · Check: `semgrep --version` prints `1.170.1` with no traceback.

## 9. Process notes

- Inputs: I read the diff, `spec.md`, `request.md`, `test-plan.md`, `review.md`, `verify-log.md`, `context/code-map.md`, and the allowed stage reports. Three folder-wide greps also returned hit lines from files outside the allowed list. In the earlier part of this session these came from `pipeline.md`, `reports/S4-review-engineering.md`, and `reports/S5-rereview-verifier.md`; later, a search for the TOML memory figure matched `pipeline.md` again. Nothing in the PR body rests on those lines alone. The 98 MB figure comes from `reports/S5-rereview-2.md`. The flake text comes from the task brief, the harness code, and `reports/S5-repair-2.md`; I dropped one workaround detail that only `pipeline.md` supported.
- Leftovers: the source and package stages leave gitignored caches (`__pycache__/`, `.mypy_cache/`, `vidbyte_sdk.egg-info/`). No probe or temp file is in the worktree; my scripts and logs are in the session scratchpad.
