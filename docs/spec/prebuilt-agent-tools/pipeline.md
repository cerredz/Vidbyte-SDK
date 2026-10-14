---
slug: prebuilt-agent-tools
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-prebuilt-agent-tools
branch: feat/prebuilt-agent-tools
base_commit: 8387d66680951766f02b0d740d78eb6450cb6419
pr: https://github.com/cerredz/Vidbyte-SDK/pull/1072
s3_head: 0fd73086
s2_head: 69a1970a
test_tree: tests/features/prebuilt_tools/
until: none
started: 2026-10-14 02:46
---

# Pipeline: A library of 250+ prebuilt agent tools in vidbyte-sdk

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 02:46 | 03:20 | reports/S0-scout.md, reports/S0-research.md | base_commit 8387d666; code-map.md; research.md |
| S1 spec + review | done | 03:25 | 07:40 | reports/S1-spec-author.md, reports/S1-spec-review.md, reports/S1-spec-review-r2.md | spec r3 approved; r1 review SOUND WITH FIXES (12 applied), r2 review SOUND WITH FIXES (10 applied); 265 tools |
| S2 tests | done | 07:45 | 08:45 | reports/S2-test-author.md | 4,284 cases / 101 test fns in tests/features/prebuilt_tools/ (26 files); red: 102 failed, 4182 errors; tightened to r4 (f49db5db): 102 failed, 4208 errors, 0 passed; S2_HEAD bc238128 | | |
| S3 implement | done | 10:05 | 14:30 | reports/S3-implementer.md | S3_HEAD 0fd73086; draft PR #1072; 39/39 planned files, 0/12 split modules; pack 4310 passed; source + package stages CI passed | | |
| S4 adversarial review | done | 14:40 | 16:10 | reports/S4-review-*.md, reports/S4-findings-verifier.md | review.md: MERGEABLE AFTER FIXES — 14 confirmed (8 Blocker / 6 Major), 5 Minor, 1 refuted, 1 downgraded | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (round 1 SOUND WITH FIXES, 12 findings applied in r2; round 2 SOUND WITH FIXES 0B/4M/6m, r3 applied all 10; status: approved — cap reached, no further rounds) · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-14 02:46 — Unset the branch upstream (`git branch --unset-upstream`) after `git worktree add` set it to `origin/main` — prevents any agent's bare `git push` from targeting main; pushes must be `git push -u origin feat/prebuilt-agent-tools`.
- 2026-10-14 02:48 — Launched a second S0 agent (research scout) in parallel with the code scout, writing `context/research.md` — the user offered to "ground your ideas in recent agentic research"; separating the catalogue research from repo recon keeps the spec author's context on design. It touched no repo code.
- 2026-10-14 02:46 — Assumption recorded in request.md §C (for the spec author to confirm as an A- item): tools are deterministic, local, standard-library only, no network/keys/new deps.

- 2026-10-14 — Passed the S1 review to the author by path (reports/S1-spec-review.md, read in full) instead of pasting the findings into the message — keeps the orchestrator context lean; the author reads the file verbatim. Told the author not to set status: approved until it is known whether a scoped round 2 is needed.
- 2026-10-14 — Ran a scoped S1 round-2 review: r2's accepted fixes changed §8 (D-2/7/9/12/16/18, §8.4, §8.5), §9.2, §10 (T-1/T-2), the shape of §12 (rows 6–7, budget, §12.4, §12.6) and Appendix A — the playbook requires a second round when those change.
- 2026-10-14 — Spec r3 approved after 2 review rounds (the review rounds are the approval; no user stop per playbook). Applied every Q-n default: Q-1 no tzdata/IANA zones (fixed UTC offsets only); Q-2 no root vidbyte exports; Q-3 no tool-search meta-tool; Q-4 no YAML discovery; Q-5 no killable regex worker (caps + EC-10 limitation); Q-6 keep dict outputs as a recorded exception to the letter of AGENTS.md principle 4 (D-7). Q-6 is surfaced to the user in the spec summary.
- 2026-10-14 — Told the S2 test author NOT to run `pip install -e .`: the global editable install points at the canonical checkout C:/Users/422mi/vidbyte-repos/vidbyte-sdk, and reinstalling from the worktree would repoint it for other sessions; bootstrap is `PYTHONPATH=$(pwd)` per field guide local-ci-verification.md.
- 2026-10-14 — Told the S2 test author that every Appendix A tool should get ≥1 exact-output case (parametrized tables), since 265 independent behaviors exceed the usual 8–25-test shape; exceptions must be listed under 'Tests deliberately NOT written'.
- 2026-10-14 — S2 OPEN ITEMS name spec defects (unreachable EC-14/utf8_hex null; uncapped add_business_days.holidays/weekend_days and critical_path_schedule dependency lists; dead domain_too_long; base64url padding stated only on hash_text; ElementPath '[' TypeError; null byte ValueError/SyntaxError across versions; 3 error rows naming no parameter; ~50 loose rows pinned to one reading in S2 report §5). Routed to the S1 spec author in Revision mode (r4) before S3, with the rule: the tests are now the contract, so the spec adopts each pinned reading unless it contradicts §9.2 or another row. No review round (S1 cap 2/2 reached); changes are row-level, not §8/§8.5 architecture.
- 2026-10-14 — Global `semgrep` is broken on this machine (semgrep's `mcp` import fails against the globally installed mcp 2.x). Built an isolated venv with semgrep==1.170.1 (the CI-pinned version) in the session scratchpad instead of changing global packages. Baseline scan at 476f9e07: 893 files, 0 findings, exit 0.
- 2026-10-14 — Spec r4 (5d93fe88) resolved all S2 defects; no test disagrees with the spec; §6.2 Proof column verified byte-identical. Resumed the S2 test author (the only agent allowed to edit tests) to tighten ANY-value assertions to r4's chosen values and cover the new r4 caps, before S3, so S4 does not flag vacuous assertions.
- 2026-10-14 — S3 launched with a context-handoff protocol: the build (265 tools, 39–51 files) may exceed one agent's context, so the implementer may stop at a §12.3 row boundary (all committed, tree clean, nothing pushed) with STATUS BLOCKED 'context budget — continuation needed'; the orchestrator then launches a fresh continuation implementer with the same briefing plus the handoff notes. Commit messages from S3 on end with the Co-Authored-By attribution line.
- 2026-10-14 — S3 implementer was terminated by an API usage limit (HTTP 429 session limit) at row 43, with 8 commits and 37 uncommitted entries (most category modules written but not committed). After the reset, resumed the SAME agent via SendMessage (its context holds the uncommitted work) rather than a fresh one; told it to reconcile status, restore per-row commits without discarding anything, then continue. Verified before resuming: test tree diff vs bc238128 empty; nothing pushed.
- 2026-10-14 — S3 BLOCKED on a spec/test contradiction for `intersect_lists`: spec A.24 (spec.md:1491) says `lists: list[TextList]`; S2 data `prebuilt_parameter_data.py:257` treats items as strings with maxLength 10000; 2 contract cases fail. Adjudicated from the spec (the row tests already agree with A.24): this is a TEST defect — granted a test change, to be made by the S2 test author only.
- 2026-10-14 — S3 surfaced an NFR-7 spec gap: `diff_words` 14.6–22.4 s at 2,000 tokens/side and `closest_string_matches` 3.1–4.9 s at 1,000 candidates (87 s on 'ﬃ'*100 vs 'ﬄ'*100 with casefolding) on adversarial repetitive input; NFR-7's ≤ 2 s target was measured on non-adversarial patterns. Routed to the S1 spec author for an r5 decision before S3 resumes (S1 review cap does not apply to a post-S2 defect fix; no review round).
- 2026-10-14 — Spec r5 (ce32c0a6): NFR-7 adversarial slowness accepted as limitation EC-46 (diff_words, closest_string_matches, unified_diff_text; bounded by caps + runtime tool_timeout_seconds); lowering caps rejected because tests pin them. seeded_weighted_choice bound stated (≤ 10,000,000 chars). No test change from r5; implementation adds one EC-46 README paragraph (row 40). Granted the S2 test author the intersect_lists data fix (prebuilt_parameter_data.py:257) — the test contradicts spec A.24.
- 2026-10-14 — S2 test author applied the granted intersect_lists fix (0708d57d): nested-list shape `TextListsShape`; mutant-checked; pack now 4310 passed, 0 failed against the S3 code. Test baseline moved from bc238128 to 69a1970a (granted change). Noted gap left as-is (not granted): flat-list minItems (e.g. greatest_common_divisor.values len 2..) not checked by the schema test.
- 2026-10-14 — S3 spot-check passed (clean tree; 50 feature commits all cite W-/R- IDs; test diff vs 69a1970a empty; draft PR #1072 `[WIP]`; frontmatter implemented + pr; pushed; my rerun of the pack: 4310 passed in 21.16s).
- 2026-10-14 — Remote CI: every workflow in .github/workflows has automatic triggers TEMPORARILY DISABLED (workflow_dispatch only; claude.yml fires on reviews/comments). `gh pr checks` reports no checks. Decided NOT to dispatch CI manually (the owner disabled it deliberately; dispatching is an outward action not requested). Verification of record = the local gate (identical scripts/run_ci.py source + package stages) + semgrep 1.170.1 (CI's pinned version). Will state this in the PR body and final report.
- 2026-10-14 — S4 verifier confirmed 14 findings (R-1..R-14). Several need spec edits first (R-7 new xml match cap A.20; R-9 apply_json_patch total-work cap A.17; R-8 HTMLParser CVE-2025-6069 handling A.13/A.28/README; R-10 cap-or-EC decision; R-12 fresh decimal Context rule) and regression tests that only the S2 test author may write (R-14 and per-finding cases). Ordering S5 as TDD: (1) spec author r6 for spec-affecting findings, (2) S2 test author adds failing regression cases, (3) repair iteration 1 makes them green. These pre-steps do not count as repair iterations.
- 2026-10-14 — Adjudicated the R-14 liveness-guard question (test-plan rule 3, no wall-clock dependence): ALLOWED a generous thread-join watchdog (~30 s, about 15× NFR-7) for hostile-input regression cases only, sized so fixed code runs well under 1 s; it converts a hang into a red test and asserts no speed. Exact-output regression cases are required alongside it.

## User replies (verbatim)
- none

## Niche facts accumulated (carried into every later briefing)
- Tools are `BaseTool` subclasses or `@tool`/`FunctionTool` functions; attached via `Agent(tools=...)`, `add_tool`, or a `Tools` collection — *source:* S0 scout
- YAML/declarative discovery only finds public `BaseTool` subclasses exported from `vidbyte.tools.builtins` (`vidbyte/lib/registries/components.py:113,124`); `@tool` functions are never discovered — *source:* S0 scout
- Large-scale precedent: `vidbyte/tools/builtins/reasoning/` (218 classes, a catalog object, CI count guard `scripts/check_reasoning_trace_contracts.py` hard-codes 182 at line 39). `filesystem/` and `calculator.py` carry lint debt — do not copy them — *source:* S0 scout
- A001 file headers required on every `.py` including tests; S025 requires ≥4-sentence descriptions on class-based tools and parameters; S016/S017 constrain error raising/reporting; A007 named constants; S062 bans adjacent string-literal concatenation (use one literal or explicit `+`) — *source:* S0 scout
- Declarative tool lists are capped at 128 entries (`vidbyte/lib/dataclasses/config.py:75`, `vidbyte/lib/dataclasses/agent_descriptor.py:49`) — *source:* S0 scout
- `vidbyte/lib/enums/tools.py` does not exist; a new tool enum goes there and into `vidbyte/lib/enums/__init__.py` `__all__` — *source:* S0 scout
- `vidbyte/__init__.py` is 1,297 lines; any root export triggers C016 and requires `python scripts/generate-sdk-public-api.py` to regenerate `contracts/sdk-public-api.json` — *source:* S0 scout
- Semgrep is NOT in `scripts/run_ci.py`; it runs only in `.github/workflows/static-policy.yml:24-30`; rule `no-untyped-mapping-fallback` likely hits JSON tools under `vidbyte/tools/builtins/` — *source:* S0 scout
- `@tool` parameter descriptions are `""` unless `Annotated[..., Field(description=...)]` (`vidbyte/tools/function_tool.py:117`) — *source:* S0 scout
- Tool names taken already include `diff`, `find`, `stat`, `zip`, `copy`, `checksum`, `glob`, `grep`; reserved `isDone`, `updateTrace`; Codex requires `^[A-Za-z0-9_-]+$`, ≤128 chars, reserves `mcp` — *source:* S0 scout
- Python floor `>=3.11` (pyproject.toml:10) so `tomllib` is available; CI source job runs on ubuntu-latest with 3.11 and 3.12 — *source:* orchestrator check
- `tzdata` is NOT a declared dependency; `zoneinfo` works on this Windows machine only because `tzdata` is installed globally in site-packages. On a clean Windows install `ZoneInfo('America/New_York')` raises `ZoneInfoNotFoundError` — *source:* orchestrator check
- Full gate: `python scripts/run_ci.py` (stages `--stage source`, `--stage package --dist-dir dist`); lint `python lint/run.py [--rule ID]`; one test file `python -m pytest -q tests/<file>.py` — *source:* code-map.md §1.3, §3.3
- Research: tool-selection accuracy drops past ~30–50 tools (Anthropic) and the 90% line sits at 10–15 tools for Haiku-class / 20–30 for Sonnet-class models (production log study); ship category toolsets + a catalogue search, never all 250 at once — *source:* research.md "Recommended grouping"
- Python 3.11+ raises ValueError converting an int over 4,300 digits to str: big-integer/factorial/Fibonacci tools need a digit cap; never change the limit globally — *source:* S0 research
- `statistics.correlation(method="ranked")` (Spearman) is 3.12+; CI also runs 3.11, so implement it by hand — *source:* S0 research
- Avoid platform-dependent stdlib: `mimetypes.guess_type`, `socket.getservbyname`, `locale` — *source:* S0 research
- `re` has no timeout: cap pattern and input length; `xml.etree` must reject DOCTYPE (entity bombs); every enumerating tool needs an output cap plus a truncation notice — *source:* S0 research
- Possible overlap with existing built-ins: `calculator` (exact arithmetic) and `reasoning/{bayesian_update, expected_value_trace, decision_matrix_trace, fermi_estimate}` — verify before selecting — *source:* S0 research
- research.md has 461 candidates in 30 categories, each category marks its "Drop first" rows; 7 categories exceed ~15–20 tools — *source:* S0 research
- Only time-dependent candidate: `current_datetime_in_timezone` — needs an injectable clock for tests — *source:* S0 research
- Contract names (spec r1 §8.5): `PrebuiltTools(Tools)` in `vidbyte/tools/toolsets/prebuilt.py` with static `select_categories`/`get_tools`; `PrebuiltToolCategory` enum (31 members, `values()`); `<Category>ToolFunctions` classes with `tool_functions()`; `PrebuiltToolSupport.argument_error(parameter_name, problem, expected)`; `PrebuiltJsonSchemaValidator.find_violations`; aliases `PrebuiltToolOutput`, `PrebuiltToolFunction` — *source:* S1 author
- Design r1: each tool is a typed `@staticmethod` on a `<Category>ToolFunctions` class wrapped by existing `FunctionTool`; 277 tools / 31 categories (6–12 each); 40 new files; 0 deps; returns dicts; errors via `ToolExecutionError` — *source:* S1 author
- Test seam: call like a model — `await tool.execute(ToolCall(name, args))` then `json.loads(result.output)`; failure kind in `result.metadata["error_type"]` ("validation" / "ToolExecutionError"); no `tests/conftest.py`; test file basenames must be unique across `tests/` — *source:* S1 author
- Seeded RNG sequences, `ipaddress` flags, and `unicodedata` can differ between Python 3.11 and 3.12 (CI runs both): tests must not pin them — *source:* S1 author
- A007 checks every name in a function signature against tokens (`interval`, `token`, `char`, `byte`, `limit`, `depth`) when a numeric literal is in an annotation; C006/C008 flag `validate*`-style and `finite_float`-style helper names; pydantic warns on params named `schema_json`, `json`, `copy` (BaseModel attributes) — *source:* S1 author
- New files must be `git add`-ed before `python lint/run.py` and semgrep: they read tracked files only (S020 checks the README file index) — *source:* S1 author
- Integer outputs capped at 4,000 digits (INV-18); exact numbers travel as text (`IntText`, `DecText`) — *source:* S1 author
- S1 review r1 verdict SOUND WITH FIXES (3 Blocker / 6 Major / 3 Minor); report reports/S1-spec-review.md — *source:* S1 reviewer
- `FunctionTool._stringify_output` runs at `vidbyte/tools/function_tool.py:85`, outside the try at :68-81: a deeply nested return (≈5,000 levels) makes `execute` raise RecursionError instead of returning a failure; depth 900 is fine — *source:* S1 reviewer
- Ruff B904 is enforced via lint S002 (`lint/rules/s002_exception_cause_chaining.py:23`, baseline 0 at `lint/baseline.json:31`): every raise inside `except` needs `from None`/`from exc` — *source:* S1 reviewer
- Measured locally: difflib (autojunk=False) 10k chars 6.5–8 s, 20k-token word diff 36 s, ~2k ≈0.3 s; `pow` with three 4,000-digit operands 3.15 s (2,000 digits 0.44 s); `csv.Sniffer().sniff` 7.09 s on adversarial 300k chars even with `delimiters=` (10k: 0.22 s); `tomllib.loads` RecursionError at ~500-deep arrays — *source:* S1 reviewer
- `calculator.py` exposes `round`, `pow`, `/` (handles floats) — spec r1's "whole-number arithmetic" description of it is wrong — *source:* S1 reviewer
- `Agent(provider="openai")` constructs without an API key; pydantic `datetime` params accept an int as UTC but `date` params reject ints; `vidbyte/lib/enums/__init__.py` `__all__` already out of alphabetical order in two places — *source:* S1 reviewer
- Spec r2: 265 tools / 31 categories (6–12 each); 68 enums; 101 classes; 39 planned files + 0–12 conditional split modules (D-18); category classes are internal (FR-5); `categories` param is enum-only (plain str rejected) — *source:* S1 author r2
- r2 constants: `PREBUILT_MAX_MODULAR_TEXT_CHARS`=2_001, `PREBUILT_MAX_SNIFF_CHARS`=10_000, `PREBUILT_FINANCE_PRECISION`=50, `PREBUILT_MIN_CHUNK_CHARS`=100; sequence-match/diff-token caps 2_000; diff lines 4_000; INV-17/INV-20 both use `PREBUILT_MAX_TEXT_CHARS`; `cap_items(items, cap) -> tuple[list[T], bool]` — *source:* S1 author r2
- Every raise inside `except` uses `from exc` (S002); security guards carry `# @intent` comments — *source:* spec r2 (R-3)
- `configparser.ConfigParser(default_section='
')` lists 'DEFAULT' in `sections()` — `ini_to_json` must state whether it is excluded — *source:* S1 reviewer r2
- Python `round()` vs `Decimal(repr(x)).quantize(ROUND_HALF_EVEN)` differ on 0.0125, 0.0375, 2.0035; `timedelta(seconds=float)` differs from the Decimal path on ~10% of half-microsecond inputs — *source:* S1 reviewer r2
- Lint S020 treats any backticked `name.ext` inside a README `## File Index` as an entry; mentioning a file not present in the folder is reported stale (blocking) — *source:* S1 reviewer r2
- `Tools.subset` returns a plain `Tools`, not the subclass — *source:* S1 reviewer r2
- Bounded-factor expansions outside INV-20's list: NFKC/NFKD of U+FDFA → 18 chars; `hex_encode` utf_32 + separator → 23 chars per astral char; `escape_json_string` ensure_ascii → 12 chars per astral char — *source:* S1 reviewer r2
- Spec r3 final: 265 tools / 31 categories; 68 enums; 101 classes; 39 planned files + ≤12 D-18 split modules; files ≤ 800 lines; test pack `tests/features/prebuilt_tools/` (FEATURE.md + README.md + test_*.py, no __init__.py) — *source:* S1 author r3
- Money: exact `Fraction` with one half-up rounding to cents, except compound growth in 50-digit `Decimal` in the §9.2 item 16 order; float→text/int/datetime rounding per §9.2 item 17 (`Decimal(repr(x))`, exact scaling, one quantize, total before parts) — never `round()` or `timedelta(seconds=float)` — *source:* S1 author r3
- `_stringify_output` sorts keys at every level, so output dict key order never matters — *source:* S1 author r3
- pytest strict mode: no `asyncio_mode`, so async tests need `@pytest.mark.asyncio` or `asyncio.run(...)`; `--strict-markers` fails unregistered markers — *source:* spec r3 §13
- Repo uses feature test packs: all 15 packs under tests/features/ have FEATURE.md — *source:* orchestrator check
- Do not `pip install -e .` in the worktree; use `PYTHONPATH=$(pwd)` for pytest and `run_ci.py --stage source`; run `--stage package` WITHOUT PYTHONPATH; verify with `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` — *source:* field guide local-ci-verification.md + orchestrator check
- Semgrep must be `semgrep==1.170.1`: `git add -A` then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (scans tracked files only) — *source:* field guide local-ci-verification.md
- Known CI flake: `tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` on Python 3.11 — `gh run rerun <id> --failed` before investigating — *source:* field guide local-ci-verification.md
- S051 import sorting: check with `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` over the whole tree, not single files — *source:* field guide local-ci-verification.md
- Test pack: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools` (minutes once green: ~28 sweep calls per tool; `find_unicode_character` ~1 s/call) — *source:* S2
- Tests bind: `vidbyte.tools.toolsets.PrebuiltTools` (`__module__` `vidbyte.tools.toolsets.prebuilt`); `toolsets.__all__` sorted == ['CodingAgentTools','ParadigmMinimalToolset','PrebuiltTools']; enums in `vidbyte.lib.enums.prebuilt_tools` or `.units`, all in `__all__`; `vidbyte/tools/builtins/prebuilt/` with `__init__.py`, `_support.py`, one `<category value>.py` per category; each function `__qualname__` == `<Category>ToolFunctions.<tool>` — *source:* S2
- Error text must match `\AInvalid value for '<param>': <problem>\. Expected <form>\.\Z`; never echo > 100 chars of an argument; never echo the HMAC key — *source:* S2
- Static scan bans `eval`, `exec`, `compile`, `open`, `time.*()`, `os.*()` except `os.path`, `.now()`, `.today()`, `strptime`, `getcontext`, `field_size_limit`, `uuid4`, global `random.*`; `literal_eval` only in `code_analysis.py`; md5/sha1 need `usedforsecurity=False` — *source:* S2
- INV-20 tools must predict output size BEFORE building it: tests assert peak traced memory < 5 MB for would-be outputs ≥ 20 MB — *source:* S2
- Count tools must compute counts by formula, never enumerate: the count tests HANG (not fail) against an enumerating implementation — *source:* S2
- `SchemaArgumentFactory` raising 'add one to the pools' → add a sample to `PATTERN_SAMPLES` (a fixture change, test-author/adjudicated only) — *source:* S2
- base64url is unpadded for every `DigestFormat` user incl. `compute_hmac` — *source:* S2
- Semgrep locally: global `semgrep` is BROKEN (mcp 2.x import error) — use the isolated venv with a POSIX-style PATH prefix (Git Bash splits PATH on ':', so `C:/...` breaks): `PATH="/c/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/c033bb4d-236f-4839-b20c-c5c2bef451e8/scratchpad/semgrep-venv/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (after `git add`); baseline 0 findings on 893 files — *source:* orchestrator
- Lint final line is `SDK-LINT: PASS`; at base, rules A002, C011, C012, S001, S010, S017, S025, S061 already report IMPROVED — not this PR's to ratchet — *source:* spec r3 §11
- Source stage at base: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` → `4015 passed, 13 skipped`, `CI passed.` — *source:* spec r3 §11
- Public API check: `python scripts/generate-sdk-public-api.py --check`; typecheck `python lint/run.py --rule S009` (mypy over vidbyte) — *source:* spec r3 §11
- r4: Python 3.11 ElementPath `[`→TypeError, `/b`→SyntaxError, `@`→KeyError; null byte → `ast.parse` ValueError without line number — tools must catch all and map to the tool's own argument error — *source:* S1 author r4
- r4: `verify_email_syntax` check order differs from the enum declaration order on purpose (row gives check order); `join_records` keeps the right join field, `csv_join_tables` drops it (deliberate, test-pinned) — *source:* S1 author r4
- r4: where a test accepts ANY value, the spec picks one — implement the spec's value — *source:* S1 author r4
- `UtcOffset` needs `max_length=PREBUILT_MAX_UTC_OFFSET_CHARS` (6) beside its pattern; over-cap tests look for 'at most N' in the parameter's own `loc` (`param` or `param.0`) — *source:* S2 r4 tightening
- Exact caps pinned by tests: holidays 1000, weekend_days 7, both critical_path dependency lists 10000 — *source:* S2 r4 tightening
- Signature text without a return annotation is `def run(self)` (no arrow) — test-author reading where r4 is silent — *source:* S2 r4 tightening
- S3 state at 3b783658: 50 commits; 39 new files, no split modules (largest 582 lines); pack `2 failed, 4308 passed` (intersect_lists only); neighbours 338 passed/12 skipped; `SDK-LINT: PASS`; semgrep 931 files 0 findings; public API current (606 exports); package stage `CI passed.`; not pushed, no PR — *source:* S3
- Lint C005 matches any name containing 'rate' or 'price' used in multiplication (fired on interest/Poisson math; locals renamed); A007 fires on whole-word tokens `limit`, `char`, `byte`, `depth` within seven AST nodes of a number literal — *source:* S3
- Comments must stay within 72 columns incl. indentation; ruff I001 import sort uses line length 88 — *source:* S3
- Use `pytest -p no:cacheprovider`; on Windows, runs can hang idle under heavy concurrency — *source:* S3
- S3 deviations: helpers `split_lines`, `line_and_column` added to `_support.py`; JSON reading refuses ints > 4,300 digits and non-finite floats; private nested `ConfigParser` subclass in structured_formats.py; tolerant base64 reader duplicated in encoding.py and hashing.py; `seeded_weighted_choice` output can reach ~10M chars (row sets no output cap) — *source:* S3 report §5
- Remote CI is disabled repo-wide (workflow_dispatch only); there are no required remote checks — local gate is authoritative — *source:* orchestrator check of .github/workflows
- S4 reviews at 0fd73086: conformance MERGEABLE AFTER FIXES 2B/1M/1m; conventions MERGEABLE AFTER FIXES 1B/3M/3m; engineering MERGEABLE AFTER FIXES 5B/4M — *source:* S4 reviewers
- `FunctionTool` runs sync tools via `asyncio.to_thread` (function_tool.py:72), which copies contextvars: the caller's `decimal.getcontext()` (traps, Emax) reaches every `localcontext(prec=...)` site; slow calls also starve the loop's default executor — *source:* S4 engineering
- HTMLParser quadratic slowness also on Python 3.13.1 (35.7 s at 40k chars of '<a '), matches CVE-2025-6069 / gh-135462 — *source:* S4 engineering
- `ipaddress.IPv6Address('fe80::1%eth0').exploded` raises on 3.11.0 (`.compressed` works); rebuild via `type(parsed)(int(parsed)).exploded` then re-append `%scope` — *source:* S4 conformance
- `_support.parse_json_text` (lines ~80–120) already has the float guard (`_read_json_float` via functools.partial); reuse it for `JSONDecoder` in extract_json_from_text and in verify_json_syntax — *source:* S4 conformance
- Reviewer probe harnesses live OUTSIDE the worktree under the session scratchpad (`s4e/` sweep); use `python -u` so output survives `timeout`; Git Bash collapses `\` — use `chr(92)` in Python probes — *source:* S4 reviewers
- C006/C008 flag helper name prefixes validate/require/ensure/normalize/coerce/check; C005 flags names containing 'price'/'rate' in multiplication (`_PRICE_MARKERS` in lint/rules/c005_cost_arithmetic_site_parity.py) — *source:* S4 conventions
- R-2 fix trap: the reviewers' lookbehind in front of the whole `_AMOUNT` drops comma lists ('1,2,3' → only '1'); guard only the grouped-chain alternative. R-6 must also cover TOML inline tables `x={a.a…=1}`. R-5 and Minor M-1 share one `parse_float` hook. R-12's `decimal_context` helper replaces `_exact_context` copies in exact_arithmetic.py:284 and number_formatting.py:281 (overlaps R-13) — *source:* S4 verifier
- New PREBUILT_* constants for R-7/R-9 must avoid A007 tokens `budget`, `limit`, `depth` in their names — *source:* S4 verifier
