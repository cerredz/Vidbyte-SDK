# S5 repair, iteration 2 of 8

- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-grok-opencode-meta-hosts`
- **Branch:** `feat/native-grok-opencode-meta-hosts`
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1036 (still a draft)
- **HEAD:**
  - At the start of this iteration the local branch was at a5d82126, the orchestrator's pipeline.md commit on top of 406edb56.
  - The last code commit is 04be59fa. It was pushed, and the remote CI ran there.
  - review.md, verify-log.md and this report are committed after it, in `docs(spec): verify-log iteration 2 for native-grok-opencode-meta-hosts`.

## Result

Every finding in this packet is fixed: R-11, R-9, R-10, R-12 and R-M6. Every gate is green, both locally and on the remote runs at 04be59fa.

- **Tests:** no test file was edited.
- **Lint, config and spec:** nothing under `lint/`, `pyproject.toml` or the spec was touched.
- **review.md:** only status cells changed.
- **Invariants:**
  - INV-19 sha256 is unchanged (`0374a2c8…497a`).
  - The INV-22 diff against origin/main is empty.
  - `vidbyte/lib/enums/failure.py` is unchanged in this iteration.
  - origin/main is an ancestor of HEAD.
- **Scope:**
  - No new file, record, enum or failure code was added, and no new dependency.
  - `vidbyte/harnesses/native/__init__.py` was not touched.
  - Constants are imported from `vidbyte.lib.constants.native_hosts` directly.

## Commits

| Finding | Commit | Subject |
|---|---|---|
| R-11 | 7f61f927 | refactor(harnesses): share host next steps and fixed texts in one constants module [R-11] |
| R-9 | 616e8a0f | refactor(lib): one home for record bounds, field-named URL checks [R-9] |
| R-10 | 0f93301a | refactor(lib): one launch helper for CliRunner and ManagedProcess [R-10] |
| R-12 | 5a7e09de | refactor(native): lift helper-to-helper calls into their callers [R-12] |
| R-11 (follow-up) | 3c896557 | refactor(native): share the JSON-RPC method-not-found answer [R-11] |
| R-M6 | 04be59fa | refactor(lib): accurate constants and validation module headers [R-M6] |
| bookkeeping | (this commit) | docs(spec): verify-log iteration 2 for native-grok-opencode-meta-hosts |

## Per finding

### R-11: shared next steps and literals

- **Next steps.**
  - New in `vidbyte/lib/constants/native_hosts.py`: `NATIVE_NOT_OPEN_NEXT_STEP`, `NATIVE_REENTER_NEXT_STEP`, `NATIVE_AT_CAP_NEXT_STEP` and `NATIVE_STALE_CURSOR_NEXT_STEP`. The last two take a `{tool}` slot, which each host fills with its own `interrupt_<host>_turn` or `list_<host>_sessions`.
  - There is one spelling and no backticks. Muse's backtick copies are gone.
- **Shared literals:**
  - `NATIVE_TRUE_TEXT` and `NATIVE_FALSE_TEXT`;
  - `NATIVE_SUCCESS_EXIT_CODE`;
  - the HTTP success range, signed-out, billing and rate-limit statuses;
  - `GROK_` / `OPENCODE_` / `MUSE_TURN_OPERATION`;
  - Grok's client name and title;
  - opencode's busy states, retry state, assistant role and model-id split;
  - `MUSE_FAILED_TERMINAL`;
  - `BACKEND_KEY_MISSING_NEXT_STEP`.
- **Follow-up commit.** I found this while checking that the R-M6 header claim is true. The Grok and Muse wires both built the `-32601` "Method not found" answer from their own literals. Both now read `NATIVE_JSONRPC_METHOD_NOT_FOUND_CODE` and `NATIVE_JSONRPC_METHOD_NOT_FOUND_TEXT`.
- **Kept private.** Vendor codes that only one wire reads stay beside it: Grok `-32002` means resource-not-found, while Muse `-32002` means prompt-too-large.

### R-9: record bounds, validator routing, title cap

- **New constants:**
  - `NATIVE_LIST_MIN_LIMIT`, `NATIVE_APPROVAL_TITLE_MAX_CHARS` (200), `NATIVE_STEER_STATUS_MAX_CHARS`, `NATIVE_URL_MAX_CHARS` and `NATIVE_QUOTED_VALUE_MAX_CHARS`;
  - `OPENCODE_MCP_NAME_MAX_CHARS`, `OPENCODE_MCP_MAP_MAX_ITEMS`, `OPENCODE_PROVIDER_ID_MAX_CHARS`, `OPENCODE_PROVIDER_MODEL_MAX_CHARS` and `OPENCODE_CREDENTIAL_MAX_CHARS`;
  - `MUSE_PATH_MAX_CHARS`, `MUSE_DISTRO_MAX_CHARS` and `MUSE_FRAME_POLL_SECONDS`;
  - `BACKEND_ENV_NAME_MAX_CHARS` and `BACKEND_CURRENCY_MAX_CHARS`.

  The private copies in the records and hosts were deleted.
- **`allow_blank`.** `RecordFieldValidator.require_text(..., allow_blank=False)` now covers the fields that may be empty: `NativeApprovalDecision.title`, `NativeTurnResult.text` and `OpencodeMessage.text`.
- **`RecordFieldConverter.require_url`:**
  - It accepts https only, or plain http only to `plain_http_hosts`. Without `allow_extras`, it refuses user info, a query and a fragment.
  - It never quotes the URL, and its errors carry `details["field"]`.
  - Callers: the opencode MCP URL and `server_url` (loopback http allowed), and `HarnessBackend.anthropic_base_url` and `balance_url` (https only).
  - **Deviation, recorded here:** the review proposed adding it to `RecordFieldValidator`. A test pins that class at exactly 13 public static methods, so it went on `RecordFieldConverter`, which is not pinned and already holds the plain instance checks. No test changed.
- **`details["field"]`.** All 20 remaining inline `raise ConfigurationError(...)` calls in the five record modules now carry `details={"field": "<Record>.<field>"}`. The other 9, the inline length and URL raises, are gone, so no inline raise lacks a field: the count went from 29 to 0.
- **Title cap.** All three drivers cap approval titles with `NATIVE_APPROVAL_TITLE_MAX_CHARS`. Muse and opencode were at 128 (`NATIVE_ID_MAX_CHARS`). opencode still caps `request_kind` at `NATIVE_ID_MAX_CHARS`.
- **Rejected:** a regex URL check. It is fragile, and its message would quote the URL.

### R-10: one launch helper

- **The helper.** `CliRunner.launch(invocation, *, stdin)` is a static method in `vidbyte/lib/process/runner.py` and the one place a child is started. It does the win32 `shutil.which` lookup, then `create_subprocess_exec` with piped stdout and stderr, `cwd`, `env` and `start_new_session` on POSIX. It maps launch failures as follows:
  - `FileNotFoundError` → `NOT_FOUND`
  - `PermissionError` → `PERMISSION_DENIED`
  - `(OSError, ValueError)` → `OS_ERROR`
- **Callers.** `CliRunner.run` passes PIPE or DEVNULL, and `ManagedProcess.start` passes DEVNULL. `CliRunner._start` and `ManagedProcess._launch` were removed.
- **Read chunk.** `NATIVE_PROCESS_READ_CHUNK_BYTES` (65536) replaces the two `_READ_CHUNK_BYTES`.
- **Unchanged:** POSIX `start_new_session=True` and Windows `taskkill /T /F` behave exactly as before.

### R-12: helper-to-helper chains

`call_depth.py` over the changed `vidbyte/*.py` files went from 16 chains to 11, with 0 nested defs. These five chains were removed:

1. `from_configuration_error` now calls `build` itself, with the next step and `context["field"]`.
2. `_read_balance` calls `_vendor_text` and passes the text into `_check_balance_status`.
3. `ProcessStopper.stop_tree` calls `_start_taskkill` and `_wait_taskkill`, both leaves with `@intent` blocks, and closes the killer's pipes in its own finally block. `_close_pipes` accepts None.
4. `require_text` and `require_optional_text` each call the leaf `_text_problem` and then `_received`. The messages are unchanged.
5. `request`, `send_request`, `notify` and `respond` call `_seconds_or_invalid_call` directly, and `_call_timeout` is deleted. The default unbounded `drain()` path (INV-18) is unchanged.

**Residual chains (accepted):**
- `build→scrub`, which the review's own smallest fix keeps.
- `_read_balance` as the shared balance-read step of two public functions. It is the caller the review's fix names.
- The eight transport chains that predate this PR and `FailureCode._from_exception_name`. The review excludes them.

**Rejected:**
- Inlining the `_close_pipes` idiom, because it would duplicate code.
- A separate copy of the checks in `require_optional_text`, for the same reason.

### R-M6: module headers

- **Constants header.** PURPOSE now says the module holds every length, count, size and time limit the native records and hosts check, plus the defaults, the shared patterns, texts and next steps, and NATIVE_HOST_NEXT_STEPS. It also says that a value only one module reads stays beside that reader. The inventory names the JSON-RPC codes.
- **Validation header.** PURPOSE and ARCHITECTURE NOTE name `RecordFieldConverter`, and FUNCTION INVENTORY lists `require_url` and `_text_problem`.

## Gates (run in this worktree, this iteration, at 04be59fa)

| Gate | Result | Final lines |
|---|---|---|
| 1 packs | PASS | `1638 passed, 19 skipped in 147.35s (0:02:27)` |
| 2 neighbour suites | PASS | `464 passed, 12 skipped in 16.51s` |
| 3 full suite | PASS (first run) | `5653 passed, 32 skipped in 180.45s (0:03:00)` |
| 4 lint | PASS (A002 601/703, down from 602; A007 255/255; other ratchets at baseline) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| 5 source stage | PASS | `5653 passed, 32 skipped in 181.83s (0:03:01)` / `CI passed.` |
| 6 package stage | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| 7 semgrep | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API check | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| remote CI 38409525140 | PASS | 3.11 `5646 passed, 39 skipped in 168.87s` / `CI passed.`; 3.12 `5646 passed, 39 skipped, 19 warnings in 186.27s` / `CI passed.`; Package `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static policy 38409529932 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| invariants | PASS | INV-19 sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py` unchanged since 406edb56 |

Each code commit was checked before it was made: the packs passed (1638 passed, 19 skipped; R-10 also ran the stdio transport suite, 1660 passed) and lint passed. R-12 also ran the neighbour suites.

## Still open

- **From this packet:** nothing.
- **Deferred by the orchestrator to iteration 3:** R-13, R-14 and R-15, plus reflowing existing comments to 72 columns.
- **Follow-ups:** R-M4, R-M5, R-M7 and R-M8.
