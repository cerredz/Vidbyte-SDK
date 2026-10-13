LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — Placement, layering and the tool layer follow the repository rules. But two field-guide lessons fail their own checks: 672 new comment lines run past 72 columns, and the lib records keep private bounds and checks of their own. The error-code typing, the duplicated helpers and the helper call depth also need mechanical fixes. None of this needs a redesign.

WHAT THE IMPLEMENTATION GETS RIGHT
- **Placement holds.** All 66 records are `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/<domain>.py`. All 13 `str, Enum` classes are in `vidbyte/lib/enums/` and exported, in alphabetical order, from `lib/enums/__init__.py`. No enum or dataclass is defined anywhere else. `vidbyte/lib/process` imports only `vidbyte.lib`, and no file touched by INV-22 changed.
- **The tool layer is a clean thin wrapper.**
  - `NativeHostTool.execute` has one `try`, and every failure comes back as a result.
  - `NativeToolArguments` names the parameter from `details["field"]`.
  - Descriptions live in their own modules. 89 of 90 have exactly 4 sentences and none has an example.
  - Every tool has a READ or WRITE tag, and each toolset has a `read_only(host)` view.
- **The main methods follow the house shape.** Each has one try ladder and plain-English step comments. There are 131 well-formed `# @intent <name>` lines, 0 nested defs, and 0 of the 495 new functions is over 60 lines. No module is over 800 lines; the largest is `opencode/host.py` at 756.
- **The gates pass.**
  - `SDK-LINT: PASS`.
  - Semgrep is clean.
  - The four feature packs give 1616 passed and 19 skipped.
  - No `.pyc` file is tracked.
  - Commits are conventional and scoped.
  - The §12.5 README and REPO_MAP entries are present.

FINDINGS (ranked)

R-V1 [Blocker] [field guide: comment-format] vidbyte/harnesses/native/opencode/host.py:322 — 672 new comment lines in SDK code run past 72 columns, so the lesson's own check fails
  Evidence:
  - `comment-format.md:7` gives the check: `awk 'length($0) > 72' <file> | grep -E '^\s*#'` "prints nothing for the files you touched". Line 5 adds: "A single-line comment that would pass 72 columns becomes a wrapped block too."
  - Spec §11 (line 1692) adopts the lesson.
  - Over the 56 new files under `vidbyte/`, the check prints 653 lines. The worst are `opencode/host.py` with 93, `muse/host.py` 60, `grok/host.py` 49, `opencode/wire.py` 44, `opencode/turn.py` 41 and `grok/wire.py` 40.
  - The `transport.py` hunks add 19 more. The new test files add 458.
  - Examples: `opencode/host.py:322` is 124 columns ("# The session must exist (EC-72), must not be busy on the server (EC-73), and the model must be offered (EC-68)."), and `grok/host.py:122` is another.
  Failure: The owner already rejected this exact comment shape ("stop writing comments like this"). It will be the first human review comment, and it touches nearly every new file.
  Smallest fix:
  - Reflow every `#` block in the changed `vidbyte/**/*.py` files to 72 columns or fewer, counting the indent. Keep `# @intent <name>` on its own first line.
  - Then rerun lint: the `@intent` line must stay within 20 lines of its `def` for A002.
  - Do the R-V5 strip in the same pass.
  Spec IDs: §11 (comment-format.md); §12.4

R-V2 [Blocker] [field guide: strict-config-dataclasses; D-8] vidbyte/lib/dataclasses/native_hosts.py:39 — The lib records keep 15 private bound literals and bypass RecordFieldValidator for length and URL checks
  Evidence:
  - **Private bounds.** These sit in record modules, not in `lib/constants`:
    - `native_hosts.py:39-40`: `_TITLE_MAX_CHARS = 200`, `_STEER_STATUS_MAX_CHARS = 64`
    - `opencode.py:55-59`: 257, 64, 64, 2048, 1024
    - `muse.py:40,42`: 64, 4096
    - `harness_backends.py:31-34`: 64, 128 (the same value as `NATIVE_ID_MAX_CHARS`), 2048, 16
    - `validation.py`: `_QUOTE_MAX_CHARS = 80`
  - **Copies of the same bounds.** `_URL_MAX_CHARS = 2048` is defined twice. `grok/turn.py:43` repeats 200 as `_DECISION_TITLE_MAX_CHARS`.
  - **Inline length checks.** `native_hosts.py:92` and `:118` and `opencode.py:357` check length with `if len(...) > ...` instead of the validator. The reason is that `require_text` (`validation.py:39`) rejects blank text, and a title may be empty.
  - **Two more URL validators.** `opencode.py:67-79` (`_require_http_url`) and `harness_backends.py:57,77` each check URLs themselves.
  - **No field in the error.** 29 inline `raise ConfigurationError` calls in these records carry no `details["field"]`.
  - **What the rules say:**
    - D-8: "Every numeric, bool, text and enum check goes through one canonical validator".
    - §12.4 (line 1960): "Every numeric limit is a §9.3 constant".
    - `strict-config-dataclasses.md:36`: "Search the dataclass for private bound literals; each validation comparison should reference the feature's constants module".
    - AGENTS.md principle 5: "if one is close, add the option you need to it rather than copying it".
  Failure: The bounds are already drifting. Grok cuts approval titles at 200 (`grok/turn.py:170`), while Muse (`muse/turn.py:206,230`) and opencode (`opencode/turn.py:233`) cut the same record field at `NATIVE_ID_MAX_CHARS` = 128. If any of these copies changes alone, records start failing at run time, deep inside a turn.
  Smallest fix:
  - Move the bounds into `vidbyte/lib/constants/native_hosts.py` as feature-prefixed constants, for example `NATIVE_APPROVAL_TITLE_MAX_CHARS` and `NATIVE_URL_MAX_CHARS`.
  - Add an `allow_blank` option to `RecordFieldValidator.require_text`, and a `require_url` method, so these checks go through the validator and carry `details["field"]`.
  - Have all three drivers cap titles with the one constant.
  Spec IDs: D-8; §8.4 (line 1323); §12.4 (lines 1950, 1960); INV-5; FR-6

R-V3 [Major] [AGENTS.md placement: closed sets are enums] vidbyte/harnesses/native/hostkit/errors.py:80 — Grok and Muse pick failure codes by free text through `NativeErrorFactory.code(problem: str)`, while opencode uses the enum
  Evidence:
  - `code()` builds `FailureCode(f"{self._harness.value}.{problem}")`. It is not part of the §8.5 interface (lines 1074-1081).
  - The Grok host package calls `.code(` 21 times, Muse 23 times, and hostkit 6 times. Opencode calls it 0 times and uses `FailureCode.OPENCODE_*` members 60 times.
  - The tables `_CODE_PROBLEMS`, `_PROBLEM_MESSAGES` (Muse wire), `_LAUNCHER_MESSAGES` and `_FAILURE_PROBLEMS` (Muse turn) are keyed by problem text.
  - Muse passes a variable 5 times: `muse/host.py:114`, `launcher.py:160,162`, `turn.py:269` and `wire.py:234`.
  - `hostkit/turns.py` builds `FailureCode(f"{...}.session_busy")` inline.
  - AGENTS.md: "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum ... not a plain `str`."
  Failure: Today all 45 literal problems match a member, which I checked. But a typo or a renamed member is only caught at run time. It raises `ValueError` inside a host's `except` ladder, and the caller gets `runtime.error` instead of the intended code. Readers also have to learn two styles across three hosts.
  Smallest fix:
  - Replace the Grok and Muse literals with `FailureCode.GROK_*` and `FailureCode.MUSE_*` members, as opencode does.
  - Key the four tables by `FailureCode`.
  - Keep `code()` private to hostkit, only for the harness-generic mappings in `from_launch_failure` and `from_protocol_error`.
  Spec IDs: INV-8; D-22; §8.5 (shared host plumbing)

R-V4 [Major] [lint A002 / spec §11] vidbyte/lib/dataclasses/opencode.py:90 — The PR adds 23 A002 findings net, which the stale baseline hides; S3's "A002 improved from 703 to 623" is not accurate
  Evidence:
  - I ran `IntentAnalyzer` over `git show` of every file under `vidbyte/`. It finds 600 at merge base `aa8c380c` and 623 at `de5b7c4c`.
  - New findings by file:
    - `lib/dataclasses/opencode.py`: 12 (`__post_init__` at 90, 108, 124, 143, 178, 234, 255, 284, 350, 425, 441 and 458)
    - `grok.py`: 3
    - `harness_backends.py`: 2
    - `muse.py`: 2
    - `native_hosts.py`: 1
    - `lib/errors/base.py:525`: `NativeHostError.__init__`
    - `lib/process/runner.py`: 4 (73, 88, 175, 201)
  - `transport.py` went from 6 to 4.
  - Spec §11 says "This PR must not raise any count" (line 1724), and line 1814 says such a function "needs `# @intent <name>` within 20 lines". `class-bound-helpers.md:42` adds that "a new boundary function needs its own `@intent` block".
  Failure: The ratchet passes only because `lint/baseline.json` (703) is 103 above what main measures. The next PR that lowers the baseline will inherit 23 findings from this PR.
  Smallest fix: Add `@intent` blocks to the 25 newly flagged functions, so the head count is 600 or lower. Correct the sentence in the S3 report (S6 PR body).
  Spec IDs: §11 (lines 1724, 1814); §12.4

R-V5 [Major] [AGENTS.md principle 2; intent-commenting] vidbyte/harnesses/native/muse/host.py:102 — 282 code comments send the reader to spec row ids (EC-/INV-/D-/T-/§), a design document AGENTS.md tells agents to treat as opaque
  Evidence:
  - 282 `#` comment lines across 24 new source files cite spec ids. Examples:
    - `muse/host.py:102`: "# EC-3: a host serves exactly one async with block. D-19: the ..."
    - `opencode/host.py:83`: "(EC-1)"
    - `native_host_tool.py:182`: "# INV-7: ..."
    - `grok.py` toolset: "(T-5)", "in §9.2 order"
  - At the merge base, no `#` comment under `vidbyte/` cites an EC, INV, AC or FR id.
  - AGENTS.md: "Do not grep, glob, or read files under `docs/` as part of ordinary work"; principle 2: "avoid jargon and abbreviations". `intent_based_commenting.md:11`: "A future agent should not need to search a design doc".
  Failure: A maintainer, or an agent that follows AGENTS.md, cannot resolve "EC-73" without opening `docs/`. That document will drift from the code, so the ids rot into noise.
  Smallest fix: In the R-V1 reflow, drop the trailing id tokens from `#` comments and keep the plain-English reason. The ids can stay in the header's RELATED DOCS and TESTS lines, which have precedent on main.
  Spec IDs: §12.4 (line 1953); AGENTS.md principle 2

R-V6 [Major] [AGENTS.md principle 5] vidbyte/lib/process/runner.py:147 — The new canonical process package repeats its own launch logic
  Evidence:
  - `CliRunner._start` (`runner.py:147-173`) and `ManagedProcess._launch` (`managed.py:90-113`) are the same code:
    - the win32 `shutil.which` resolution,
    - `create_subprocess_exec(..., start_new_session=sys.platform != "win32")`,
    - the same `FileNotFoundError` / `PermissionError` / `(OSError, ValueError)` → `ProcessLaunchFailure` ladder.
  - `_READ_CHUNK_BYTES = 65536` is defined in both files (`runner.py:27`, `managed.py:27`), and both carry their own reader wait and cancel code.
  - In the transport, the new `_write_frame` (`transport.py:377`) repeats `_send`'s steps: the closed check, `start`, the write lock, write, drain and the except-to-`McpProtocolError` block.
  Failure: The package exists to be the one place this logic lives (FR-16). Two copies of the launch classification will drift, for example a new `ProcessLaunchFailure` member, or the Windows `.cmd` shim handling.
  Smallest fix:
  - Add one static launch helper in `vidbyte/lib/process` that returns `(process | None, ProcessLaunchFailure | None)` for a given stdin mode, and call it from both classes.
  - Move the chunk size to `lib/constants`.
  - In the transport, have `_send` and `_write_frame` share one write step.
  Spec IDs: FR-16; INV-4; §12.3 rows 17-18, 22

R-V7 [Major] [AGENTS.md principle 5; INV-7 consistency] vidbyte/harnesses/native/muse/host.py:69 — The three hosts copy their own next-step texts and fixed literals, and the copies have already drifted
  Evidence:
  - **Next steps.** The not-open and re-enter steps exist three times. `muse/host.py:69-70` writes "`async with`" in backticks. `grok/host.py:64-65` and `opencode/host.py:58-59` (as `_OPEN_STEP`/`_NEW_HOST_STEP`) write it without.
  - **Literals:**
    - `_TRUE_TEXT`/`_FALSE_TEXT` five times: `grok/host.py:62`, `muse/turn.py:49`, `muse/wire.py:61`, `opencode/wire.py:56` and `native_host_tool.py:49`.
    - `_FAILED_TERMINAL = "failed"` in `muse/turn.py:48`, `muse/wire.py:58` and `lib/dataclasses/muse.py:44`.
    - `_KEY_MISSING_STEP` in `backends/profiles.py:53` and `opencode/server.py:34`.
    - The HTTP 402, 429 and 2xx bounds in `profiles.py:56-58`, `opencode/wire.py:54-55` and `opencode/client.py:31`.
    - `_TURN_OPERATION` in both `grok/turn.py:38` and `grok/wire.py:47`.
  - **Client names.** Grok keeps private `_CLIENT_NAME`/`_CLIENT_TITLE`, while Muse uses `MUSE_CLIENT_NAME` from constants.
  Failure: The model sees different text for the same failure depending on the host (INV-7's "Next step: ..." is model-facing). Each later wording fix has to find every copy.
  Smallest fix: Put the host-generic next steps, with a `{tool}` slot for the at-cap step, and the shared literals and status bounds in `vidbyte/lib/constants/native_hosts.py`. Use one spelling.
  Spec IDs: INV-7; D-22; §9.3

R-V8 [Major] [AGENTS.md principle 1; §12.4 checklist] vidbyte/harnesses/native/hostkit/errors.py:89 — New helper-to-helper chains, one of them four deep
  Evidence:
  - `call_depth.py` over the changed files finds these new chains:
    - `from_configuration_error` → `invalid_argument` (`:89`) → `build` (`:84`) → `scrub`
    - `HarnessBackends._read_balance` (`profiles.py:238`) → `_check_balance_status` (`:261`) → `_vendor_text`
    - `ProcessStopper._taskkill` (`runner.py:73`) → `_close_pipes`
    - `McpStdioTransport._call_timeout` (`:393`) → `_seconds_or_invalid_call`
    - `_send` (`:262`) and `_write_frame` (`:377`) → `start`
    - `RecordFieldValidator.require_optional_text` → `require_text` (`validation.py:38`) → `_received`
  - The transport chains that existed at the merge base are not counted.
  - §12.4 (line 1953): "no helper calls a second helper of its own".
  Failure: A reader has to follow the chain down through the file to see what a public call does. This is the shape principle 1 forbids, and §12.4 lists it as a checklist item.
  Smallest fix:
  - Lift the second call into the caller: `_read_balance` calls `_vendor_text`, `stop_tree` closes the pipes after `_taskkill`, and `_call_timeout` absorbs `_seconds_or_invalid_call`.
  - `from_configuration_error` calls `build` directly with the computed next step.
  Spec IDs: §12.4 (line 1953)

R-V9 [Major] [field guide: model-facing-tool-contracts] vidbyte/tools/builtins/muse/descriptions.py:100 — The model cannot learn the allowed Muse `reasoning_effort` values
  Evidence:
  - The parameter is parsed with `NativeToolArguments.choice(call, ..., MuseReasoningEffort)` (`muse/tools.py:124,147`), a closed set of seven values.
  - Its description only says "one of the reasoning effort values the Muse session protocol defines, written in lower case".
  - `ToolParameter` (`lib/dataclasses/tools.py:66`) has no enum field, and `list_muse_models` returns no efforts (`LIST_MUSE_MODELS_DESCRIPTION`).
  - By contrast, the Grok effort description points to `list_grok_models`, and `DIRECTION_PARAMETER_DESCRIPTION` names "forward" and "backward".
  - `model-facing-tool-contracts.md:12`: derive the choices from the `str, Enum` members.
  Failure: The model has to guess. A plausible guess such as "max" or "very high" is refused as `configuration.invalid_argument`, which costs a round trip on `spawn_muse_session` and `continue_muse_session`.
  Smallest fix: Name the seven `MuseReasoningEffort` values in `REASONING_EFFORT_PARAMETER_DESCRIPTION`, the same way the direction description names its two, and keep it at 4-5 sentences.
  Spec IDs: §9.2 rows 31-32; FR-5

R-V10 [Minor] [consistency; function design] vidbyte/harnesses/native/muse/wire.py:53 — The three wire codecs are built three different ways, and Muse's uses a module-level error factory
  Evidence:
  - `_ERRORS = NativeErrorFactory(NativeHarness.MUSE)` is one shared instance for the whole process, with a mutable `_secrets` set, separate from `MuseHost`'s factory.
  - `GrokWire` (`grok/wire.py:84`) and `OpencodeWire` (`opencode/wire.py:277`) receive the host's factory instead.
  - `MuseWire.exchange` and `exchange_loaded` (`:185`, `:195`) do peer I/O inside the codec. Grok keeps that in its host.
  - `OpencodeWire` adds the private classes `_Members` and `_WireRecords` (`:61`, `:81`), which are outside the §8.4 class budget.
  Failure: Nothing leaks today, because MuseHost registers no secret. The first `register_secret` added to MuseHost would not scrub errors built by the wire, and anything registered on `_ERRORS` would be shared by every host.
  Smallest fix: Give `MuseWire` an `__init__(self, errors: NativeErrorFactory)` taking the host's factory, as the other two wires do, and drop `_ERRORS`.
  Spec IDs: D-22; INV-6; §8.4

R-V11 [Minor] [file headers] vidbyte/lib/constants/native_hosts.py:3 — Two headers claim more than their code does
  Evidence:
  - The constants PURPOSE says the module "Holds every bound, default, pattern and fixed text the native ... hosts ... use", but R-V2 and R-V7 list bounds and texts kept elsewhere.
  - `validation.py:3`'s PURPOSE names only `RecordFieldValidator`, but the file also defines `RecordFieldConverter`, whose private `_types`/`_type_names` are missing from the FUNCTION INVENTORY. That class is logged as §17 deviation 2.
  Failure: An agent trusting the header looks only in the constants module and misses the private copies.
  Smallest fix: After R-V2 and R-V7, the constants claim becomes true. Add `RecordFieldConverter` to the PURPOSE of `validation.py`.
  Spec IDs: §12.4 (A001 headers)

VERIFIED CLAIMS:
- **"SDK-LINT PASS" (S3): held.** `lint/run.py` exits 0. A003, A006, S009, S015 and S017 have 0 findings in the native code.
- **"A002 improved from 703 to 623" (S3): misleading.** The count rose from 600 at the merge base to 623 (R-V4).
- **"1616 passed and 19 were skipped" (S3): held.** My run of the four packs gave 1616 passed and 19 skipped in 150 s.
- **"Semgrep is clean" (S3): held.** `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` from the pinned venv exits 0.
- **66 records and 13 enums in the placement folders, frozen, slotted and exported (§12.4 line 1950): held.**
- **No module over 800 lines (NFR-4): held.** The largest is 756.
- **INV-22 files untouched: held.** 0 files in the diff.
- **No new I001 / S051: held.** The only hit in a changed file, `lib/errors/__init__.py:22`, exists at the merge base.
- **Every `.code("<problem>")` literal resolves to a member for its harness: held**, 45 of 45 (R-V3 is about the typing, not a current bug).
- **The descriptions have "at least four general sentences with no concrete example values": held for 89 of 90.** `GET_OPENCODE_PROVIDER_AUTH_DESCRIPTION` says "such as an API key or a browser login".
- **"Records validate through RecordFieldValidator" (§8.4 line 1323): partly false**, see R-V2.

COMMANDS RUN:
- `git log --format='%h %s' aa8c380c..de5b7c4c`; `git diff --stat` / `--name-only aa8c380c de5b7c4c`; `git ls-files | grep -c '\.pyc$'` (0)
- `PYTHONPATH=$(pwd) python lint/run.py` → SDK-LINT: PASS. The JSON output was filtered to the changed files with scratch `lint_changed2.py`.
- `PYTHONPATH=$(pwd) python -B scratch/a002_refs.py $(pwd)` → `IntentAnalyzer` gives 600 at the merge base and 623 at the head.
- `ruff check --select I001` → 223 tree-wide, 1 in a changed file, already present at the base.
- `awk 'length($0) > 72' <file> | grep -cE '^\s*#'` over the new `vidbyte/` and `tests/` files, plus the added transport lines → 653 / 458 / 19.
- `python -B scratch/call_depth.py <changed vidbyte files>` (also run on the base `transport.py`) → 16 chains, 0 nested defs.
- `python -B scratch/code_calls.py` → 45 literal and 5 dynamic `.code()` calls, 0 unresolved.
- `python -B scratch/inventory_check.py`, `func_len.py 60` and `desc_check.py` over the new files.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -B -m pytest -p no:cacheprovider -q tests/features/{grok_host,opencode_host,muse_host,native_backends}` → 1616 passed, 19 skipped.
- `semgrep.exe scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` from the pinned venv → exit 0.
- `grep` / `sed` reads of the 66 records, the hosts, the wires, the tools, the toolsets, the README and REPO_MAP diffs, and spec §8.4, §8.5, §9.1-§9.3, §11 and §12.4.
