# Verification log: native Grok, opencode and Muse hosts plus GLM/DeepSeek backend profiles

Gate set (from context/code-map.md §1 and reports/S3-implementer.md; run from the worktree root, in this order):

1. Packs (local): `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends`
2. Neighbour suites (local): `PYTHONPATH=$(pwd) python -m pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py tests/features/coding_agent tests/test_mcp_bridge.py`
3. Full suite (local): `PYTHONPATH=$(pwd) python -m pytest -q`
4. Lint ratchet (local): `git add -A`, then `python lint/run.py`; the last line must be `SDK-LINT: PASS`
5. Source stage (local): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
6. Package stage (local): `python scripts/run_ci.py --stage package` with no PYTHONPATH
7. Static policy (local): `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1 from `/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1`)
8. Remote (remote-only): `ci.yml` (Source / Python 3.11 and 3.12) and `static-policy.yml`. Both are `workflow_dispatch` only, so dispatch them after each push with `gh workflow run <file> --ref feat/native-grok-opencode-meta-hosts`; `gh pr checks 1036` does not list dispatched runs, so read them with `gh run view <id>`.

Invariant checks after every iteration: INV-19 (`sha256sum vidbyte/harnesses/native/__init__.py` is `0374a2c8…497a`), INV-22 (`git diff --stat origin/main -- vidbyte/__init__.py contracts/sdk-public-api.json vidbyte/tools/builtins/__init__.py vidbyte/lib/dataclasses/__init__.py vidbyte/lib/constants/__init__.py pyproject.toml` is empty), `vidbyte/lib/enums/failure.py` unchanged.

## Iteration 1 — 2026-10-13 13:01 UTC — agent report: reports/S5-repair-1.md

**Defects in:** step 0 (merge origin/main, conflict in `vidbyte/tools/mcp/transport.py`); R-1, R-2, R-3, R-6, R-5, R-7, R-8, R-4, R-M1; gate CI-1 (EC-51 test `test_grok_host_process_bounds` red on Linux 3.12 only, run 38379243965 at 9d51a3fb); review.md bookkeeping (R-M2, R-M3, R-M9, R-9 to R-15, R-M6).

**Hypotheses and attempts:**
- **Step 0.** Merged origin/main (no rebase). The only conflict was `McpStdioTransport.notify`: main changed the frame so `params` is left out when it is `None`, this branch added `timeout_seconds`. Kept one `notify` with both. The packs gave the same results before and after the merge, and CI at the merge (run 38395105270) showed only the packet's known failures: 12 on 3.11, and 13 on 3.12 (the extra one is CI-1).
- **R-1.** `_MALFORMED_CODES` is now `{-32700, -32600}` only, so a `-32602` that carries no cursor is `grok.api_error` with the vendor code (EC-16). The cursor row (EC-41) is unchanged.
- **R-2.** On win32 the launcher is refused when its name ends in `.cmd` or `.bat`, compared case-insensitively after dropping the trailing dots and spaces that Windows ignores. This applies to `grok` found on PATH and to an explicit `grok_command[0]`. A refused PATH hit falls back to `~/.grok/bin/grok.exe`. With no usable launcher the host raises `not_installed` with a batch-specific message and next step (EC-157, D-19). `GrokCli.refused_batch` carries the refused path to the host.
- **R-3.** With no per-call timeout, `McpStdioTransport` is back to the plain `await stdin.drain()` from origin/main (INV-18). Only a call that names `timeout_seconds` gets `wait_for(drain(), seconds)`.
- **CI-1: root cause.** I read the CPython 3.11 and 3.13 asyncio source. On a Unix write to a pipe whose reader is gone, `_UnixWritePipeTransport.write` gets EPIPE and calls `_fatal_error`. That calls `_close`, which sets `_closing=True` at once and schedules `connection_lost` with `call_soon`. The stream protocol only learns of the loss after a second `call_soon` hop (`WriteSubprocessPipeProto` → `_pipe_connection_lost` → `_call`).
  - A bare `drain()` yields once (`sleep(0)`) and then returns normally, so the error is swallowed.
  - On 3.11, `wait_for` wraps `drain` in a Task. That adds the missing loop turn, so the error surfaces.
  - On 3.12+, `wait_for` runs inline, so the error does not surface. That explains why only 3.12 was red.
  - On Windows (Proactor), `drain` raises in every mode, which is why the gate was green locally.
  - So CI-1 is a code defect tied to R-3, not a test defect. This is the "open lead" in review.md.
- **CI-1: rejected options.**
  - (a) An extra `await asyncio.sleep(0)` after `drain`. It depends on how many hops CPython uses, so it is fragile across versions.
  - (b) A liveness check in `NativePeer`. The fixture child is still alive with stdout open, so the check would detect nothing.
  - (c) An `is_closing()` check on every write. It would change the default `request`/`notify` behaviour that INV-18 freezes.
- **CI-1: chosen fix.**
  - After `drain()`, a write that named a deadline raises `BrokenPipeError` when `stdin.is_closing()` is True. The transport maps that to `McpProtocolError`, and the host maps it to `process_exited`.
  - `NativePeer` now always passes its control timeout to `request`, `send_request`, `notify` and `respond`. So every native write is bounded and checked, and the default transport path is untouched.
  - Verified on remote Linux: run 38396542610 at eea8cf36 has the EC-51 test green on 3.11 and 3.12 (7 failed, all R-5/R-6/R-8 tests, which are fixed since).
- **R-6.** `OpencodeTurnWatcher.abort_before_failing(error)` sends one `POST /session/{id}/abort`, best effort, before `_drive` re-raises any failure that the host itself raised.
  - It skips the abort when:
    - the server already ended the turn;
    - an abort is already pending;
    - the error is the turn's own reported failure;
    - the session is gone.
  - `_retry_failure` no longer aborts on its own, which removes the double abort (EC-158).
- **R-5.** `MuseHost.__aexit__` runs these steps:
  1. Tells every driver to shut down (errors suppressed).
  2. Waits for the turn tasks up to `NATIVE_STOP_GRACE_SECONDS`.
  3. Closes every peer concurrently. Each close is bounded by the transport's grace and kill waits.
  4. Waits for the tasks, which end once their peer is closed.

  A peer that never answers `approval/decide` can no longer hold the exit open (NFR-2).
- **R-7.** `MuseLauncher.peer_environment` builds the WSLENV forwarding list for every WSL peer, read peers included.
  - It holds `META_API_KEY/u` when the variable is set, plus the mark's `/u` entry when the peer has a mark.
  - The caller's own WSLENV entries stay first.
  - An empty list leaves the environment unchanged (D-18, §9.3).
- **R-8.** Grok and Muse session ids are lower-cased right after `require_uuid` at every site that calls it: Grok continue and fork, and Muse continue, fork, read, page and usage. The places that compare ids also compare them in lower case: the Grok fork check, `check_fork_result` and the listing check. Upper-case and lower-case spellings of one live session now count as busy (INV-14). `require_uuid` and `NativeTurnTable` are unchanged.
- **R-4.** `ToolParameter` has no enum field, and adding one would change a public contract.
  - The fix uses the pattern of the other categorical tool params: `MuseHostTool.spec()` builds the parameter schema with `ToolsFormatter.input_schema` and adds `"enum": [m.value for m in MuseReasoningEffort]` to `reasoning_effort`. The typed `parameters` are kept, so prompt docs and required names do not change.
  - The description also names the seven values, read from the enum, in four sentences. This keeps them visible in prompt-rendered tool docs, which show only descriptions.
  - Verified by dumping `spawn_muse_session` and `continue_muse_session` (shown below).
- **R-M1.** The `OpencodeHost` constructor's `require_instance` is now inside `try/except ConfigurationError`, mapped through `from_configuration_error`. `OpencodeHost('not settings')` now raises `NativeHostError configuration.invalid_argument`.
- **Gate flake, recorded for the next agent.**
  - The first full-suite run had one failure in an unrelated test (`test_trajectory_checkpoint_algorithm.py::…private_manager_created_when_missing`). Creating its event loop raised `OSError: [WinError 10055] … lacked sufficient buffer space`.
  - The machine had about 3,700 loopback sockets in TIME_WAIT. Each Proactor loop's self-pipe is a socketpair, and other sessions were running at the same time.
  - The file passed on its own (25 passed), and the full suite then passed on rerun. It is environmental; no code was changed for it.

**Changes:** merge 3cdd9704; R-1 749b7583; R-2 137fa778; R-3 a9223a02; CI-1 eea8cf36; R-6 1e62494b; R-5 93c42f68; R-7 a4d74982; R-8 e70be132; R-4 54d5c17b; R-M1 87217940; review.md statuses d6733882.

R-4 schema dump (`ToolsFormatter.input_schema(tool.spec())["properties"]["reasoning_effort"]`, the same for both tools):
```
spawn_muse_session {"description": "How much reasoning Muse should spend on this turn. It must be one of none, minimal, low, medium, high, xhigh, ultra, which run from the least reasoning to the most, written in lower case. Leave it out to use Muse's own default for the model. Any other value is refused before the turn starts.", "enum": ["none", "minimal", "low", "medium", "high", "xhigh", "ultra"], "type": "string"}
```

**Gate matrix out (HEAD d6733882):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| packs | gate 1 | PASS | `1638 passed, 19 skipped in 151.15s (0:02:31)` |
| neighbour suites | gate 2 | PASS | `464 passed, 12 skipped in 17.44s` |
| full suite | gate 3 | PASS on rerun (first run: 1 environmental WinError 10055, see above) | `5653 passed, 32 skipped in 187.49s (0:03:07)` |
| lint | gate 4 | PASS (A002 602/703 IMPROVED, A007 255/255) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | gate 5 | PASS | `5653 passed, 32 skipped in 183.94s (0:03:03)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| remote CI | `gh run view 38401581802` | PASS (3.11, 3.12, Package all success) | 3.12: `5646 passed, 39 skipped, 19 warnings in 183.38s` / `CI passed.`; 3.11: `5646 passed, 39 skipped in 180.13s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| PR checks | `gh pr checks 1036` | n/a | `no checks reported on the 'feat/native-grok-opencode-meta-hosts' branch` (dispatch-only workflows); PR still a draft |
| remote static policy | `gh run view 38401585901` | PASS | `Ran 1 rule on 949 files: 0 findings.` (conclusion success) |
| invariants | INV-19 / INV-22 / FailureCode | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py` untouched |

**Still open:** none from this packet. Deferred by the orchestrator: R-9 to R-15 and R-M6 (iteration 2/3). Follow-ups: R-M4, R-M5, R-M7, R-M8.

## Iteration 2 — 2026-10-13 14:05 UTC — agent report: reports/S5-repair-2.md

**Defects in:** R-11, R-9, R-10, R-12, R-M6 (in that order); review.md bookkeeping (R-9 to R-12 and R-M6 fixed; R-13 to R-15 deferred to iteration 3; R-M4, R-M5, R-M7 and R-M8 still follow-ups).

**Hypotheses and attempts:**
- **R-11.** The three hosts each kept their own copy of the next steps that every host gives, and Muse's copies had drifted to markdown backticks.
  - The fix puts one copy of each step in `vidbyte/lib/constants/native_hosts.py`: `NATIVE_NOT_OPEN_NEXT_STEP`, `NATIVE_REENTER_NEXT_STEP`, `NATIVE_AT_CAP_NEXT_STEP` and `NATIVE_STALE_CURSOR_NEXT_STEP`. The last two have a `{tool}` slot that each host fills with its own tool name. None of them uses backticks.
  - The other duplicated literals moved there too:
    - true and false texts, the success exit code and the HTTP status bounds;
    - the wait-turn operation names;
    - Grok's client name and title;
    - opencode's busy and retry states, assistant role and model-id split;
    - Muse's failed terminal;
    - the backend key-missing step.
  - While checking the R-M6 header claim, I found that the Grok and Muse wires each built the JSON-RPC `-32601` "Method not found" answer from their own literals. Both now read `NATIVE_JSONRPC_METHOD_NOT_FOUND_CODE` and `NATIVE_JSONRPC_METHOD_NOT_FOUND_TEXT` (second R-11 commit).
  - Vendor error codes that only one wire reads stay private beside it, for example Grok `-32002` resource-not-found versus Muse `-32002` prompt-too-large.
- **R-9.**
  - **Bounds.** Every private record and host bound moved to the constants module as a feature-prefixed constant:
    - approval title 200, steer status 64, URL 2048 and quoted-value 80;
    - opencode MCP name, MCP map, provider id, provider/model and credential;
    - Muse path, distro and frame poll;
    - backend env name and currency;
    - the list minimum limit, which three hosts shared.
  - **`allow_blank`.** `RecordFieldValidator.require_text` gained `allow_blank`, so the title and text fields that may be empty (`NativeApprovalDecision.title`, `NativeTurnResult.text` and `OpencodeMessage.text`) go through the validator instead of `require_instance` plus an inline `len` check.
  - **`require_url`.** The URL rule is now `RecordFieldConverter.require_url`: https only, or plain http only to the hosts the caller names, with optional refusal of user info, query and fragment. It never quotes the URL. opencode uses it for the MCP URL and `server_url`, with loopback-only plain http, and the backend profile uses it for `anthropic_base_url` and `balance_url`, https only.
    - **Deviation from the review's wording:** the review suggested adding it to `RecordFieldValidator`, but a test pins that class at exactly 13 public static methods. `RecordFieldConverter` is not pinned and already holds the plain instance checks, so the method lives there.
    - **Rejected:** a regex URL check. It is fragile, and its natural message quotes the URL.
  - **`details["field"]`.** All 20 remaining inline `raise ConfigurationError(...)` calls in grok.py, muse.py, native_hosts.py, opencode.py and harness_backends.py now carry `details={"field": "<Record>.<field>"}`, naming the first field in the message. The 9 inline length and URL raises were removed, because they now go through the validator. The count of inline raises without a field went from 29 to 0.
  - **Title cap.** Every driver's approval title is capped with `NATIVE_APPROVAL_TITLE_MAX_CHARS` (200, the record's own cap and spec value). Muse and opencode were at 128. opencode keeps `NATIVE_ID_MAX_CHARS` for `request_kind`.
- **R-10.**
  - `CliRunner.launch(invocation, *, stdin)` is the one static launch in `vidbyte/lib/process/runner.py`. It does the win32 `shutil.which` lookup, then `create_subprocess_exec` with piped stdout and stderr, `cwd`, `env` and `start_new_session` on POSIX. It maps launch failures as follows:
    - `FileNotFoundError` → `NOT_FOUND`
    - `PermissionError` → `PERMISSION_DENIED`
    - `(OSError, ValueError)` → `OS_ERROR`
  - `CliRunner.run` passes PIPE when there is `stdin_text` and DEVNULL otherwise. `ManagedProcess.start` passes DEVNULL. `ManagedProcess._launch` and `CliRunner._start` are gone.
  - `_READ_CHUNK_BYTES` is now `NATIVE_PROCESS_READ_CHUNK_BYTES` (65536), read by both modules.
  - The stop path, POSIX `start_new_session=True` and Windows `taskkill /T /F`, is unchanged.
  - **Rejected:** a new module (no new files allowed) and a module-level function (the package's helpers are classes).
- **R-12.** The checker (`call_depth.py` over the changed files) went from 16 chains to 11. The five new chains were removed:
  - `from_configuration_error` builds the next step and calls `build` directly.
  - `_read_balance` calls `_vendor_text` and passes the text to `_check_balance_status`.
  - `stop_tree` calls two leaves, `_start_taskkill` and `_wait_taskkill`, and closes the killer's pipes in its own finally block. `_close_pipes` accepts None.
  - `require_text` and `require_optional_text` each call one leaf, `_text_problem`, and then `_received`. The messages are unchanged.
  - `request`, `send_request`, `notify` and `respond` call `_seconds_or_invalid_call` directly, and `_call_timeout` is gone. The default unbounded `drain()` path (INV-18) is untouched.

  **Rejected:**
  - Inlining the `_close_pipes` idiom into the taskkill path, because it would duplicate code.
  - Giving `require_optional_text` its own copy of the checks, for the same reason.

  **Residual (accepted):**
  - `build→scrub`, which the review's own smallest fix keeps.
  - `_read_balance` as the shared balance-read step of two public functions. This is the caller the review's fix names.
  - The eight transport chains from before this PR and `FailureCode._from_exception_name`. The review excludes them.
- **R-M6.**
  - The constants header now says it holds every length, count, size and time limit the native records and hosts check, plus the shared texts, next steps and codes. It also says that a value only one module reads stays beside that reader.
  - The validation header's PURPOSE and ARCHITECTURE NOTE name `RecordFieldConverter`, and its inventory lists `require_url` and `_text_problem`.

**Changes:** R-11 7f61f927 and 3c896557; R-9 616e8a0f; R-10 0f93301a; R-12 5a7e09de; R-M6 04be59fa; review.md statuses in the verify-log commit.

Each commit was checked before it was made, using the packs and the lint, with the neighbour suites added from R-12 on. The full matrix below was run once, at the final code HEAD.

**Gate matrix out (code HEAD 04be59fa):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| packs | gate 1 | PASS | `1638 passed, 19 skipped in 147.35s (0:02:27)` |
| neighbour suites | gate 2 | PASS | `464 passed, 12 skipped in 16.51s` |
| full suite | gate 3 | PASS (first run, no flake) | `5653 passed, 32 skipped in 180.45s (0:03:00)` |
| lint | gate 4 | PASS (A002 601/703 IMPROVED, was 602; A007 255/255; A001, A006, C008, S024, S054 and S062 at their baselines) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | gate 5 | PASS | `5653 passed, 32 skipped in 181.83s (0:03:01)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| call depth | `call_depth.py` over changed `vidbyte/*.py` | 16 → 11 chains, 0 nested defs | residuals listed under R-12 |
| remote CI | `gh run view 38409525140` (head 04be59fa) | PASS (3.11, 3.12 and Package all success) | 3.11: `5646 passed, 39 skipped in 168.87s` / `CI passed.`; 3.12: `5646 passed, 39 skipped, 19 warnings in 186.27s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static policy | `gh run view 38409529932` (head 04be59fa) | PASS | `Ran 1 rule on 949 files: 0 findings.` (conclusion success) |
| PR checks | `gh pr checks 1036` | n/a | `no checks reported on the 'feat/native-grok-opencode-meta-hosts' branch` (dispatch-only workflows); the PR is still a draft |
| invariants | INV-19 / INV-22 / FailureCode | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py` unchanged in this iteration (`git diff 406edb56 HEAD` is empty) |

**Still open:** nothing from this packet. The orchestrator deferred R-13, R-14 and R-15 to iteration 3. R-M4, R-M5, R-M7 and R-M8 remain follow-ups. Reflowing existing comments to 72 columns is iteration 3 work; only new comments were kept to that width.

## Iteration 3 — 2026-10-13 15:09 UTC — agent report: reports/S5-repair-3.md

**Defects in:** R-14 and R-15 (one pass, as the packet asked), then R-13; review.md bookkeeping (R-13, R-14 and R-15 fixed; R-M4, R-M5, R-M7 and R-M8 still follow-ups).

**Hypotheses and attempts:**
- **Scope, measured first.** A scratch counter read only the lines this PR adds under `vidbyte/` (diff against origin/main 8387d666). At bae65c29 it found:
  - 295 added `#` comments citing a spec id;
  - 701 added full-line comments wider than 72 columns;
  - 0 wide trailing comments.

  The review counted 282 and 653 + 20 at de5b7c4c; iterations 1 and 2 added the rest.
- **R-14 and R-15, one pass.**
  - **Method.** A scratch tool took each run of PR-added full-line comments at one column and:
    - stripped the id tokens (parenthesised references and leading "EC-n:" labels);
    - joined the lines into paragraphs;
    - filled them again at 72 columns, counting the indent.

    `# @intent <name>` stays on its own first line, and blank `#` lines and list items are kept. A block that mixes main's lines was left alone.
  - **Hand rewrites.** Where an id carried the meaning, the comment now names the failure code (wsl_unavailable, protocol_mismatch, version_unsupported, process_exited, server_unreachable, turn_not_found) or the step (the at-cap next step).
  - **`@intent` names and rulers.** Seven names said "row", a spec-table word; they now say "failure", for example `grok-json-rpc-codes-to-failures`. Section rulers were shortened to 72 columns.
  - **NFR-4.** The first fill pushed `opencode/host.py` past 800 lines, so 28 narration comments there were tightened. It is now 790, the largest new module.
  - **Comment-only proof.** `ast.dump(ast.parse(...))` is equal for all 38 changed `.py` files against bae65c29.
  - **Errors along the way, all fixed before committing:**
    1. A `--dry` flag that was not yet wired wrote the files. I checked AST equality, ran `git restore vidbyte/` (the tree had been clean) and wired the flag.
    2. The writer kept the CRLF that `core.autocrlf=true` checks out, which made three whole-file diffs. It now writes LF, which is what the blobs hold.
    3. The id strip capitalised words mid-sentence. It now capitalises only after removing a leading label.
    4. A fully balanced wrap made lines too narrow. It became a greedy fill that narrows only to avoid a stub last line (under 30% of the width).
    5. One hand-written line was 73 columns. Hand text now goes through the same wrapper.
  - **A002 side effect.** `NativePeer.send` and `ProcessStopper._bounded_wait` had passed A002 only because the next function's `@intent` sat within their 20-line window. The reflow pushed it out, and A002 went 601 → 603. Both got real blocks in the same commit (→ 600).
  - **Byte width.** gawk here counts bytes, so a line in `opencode/turn.py` holding "…" measured 74 although it is 72 characters. It was rewrapped in 96705dfd.
- **R-13.**
  - **Before.** Measured with the repo's own `IntentAnalyzer` over each ref's tree: origin/main 8387d666 = 579, bae65c29 = 601. The 24 newly flagged functions:
    - opencode.py 12, grok.py 3, harness_backends.py 2, muse.py 2, native_hosts.py 1 and errors/base.py 1;
    - process/runner.py 3: `_feed_stdin`, `_outcome` and `_kill_leader`.

    transport.py went 6 → 4.
  - **Fix.** 23 got an `@intent` block in main's format in 4f243bc9: the first lines of the body, `# @intent <name>` then the plain-English reason, ≤ 72 columns. Where the body already opened with a narration comment, the block replaced it and kept its meaning.
  - **`_kill_leader`.** After the reflow it passed only through `_bounded_wait`'s new block 7 lines below. A stricter count, which accepts only an `@intent` inside the function's own lines, caught this, and it got its own block in af3e05e8.
  - **After.** A002 is 577 against 579 on origin/main. The only per-file difference is transport.py 6 → 4, which this PR already had.
  - **Rejected:** lowering `lint/baseline.json` as lint suggests ("Lower it with … --update-baseline"). Nothing under `lint/` is edited.
- **Gate-run trouble.**
  - **First run, at 96705dfd.** It failed 14 `tests/features/coding_agent/test_coding_agent_verify_command.py` tests ("the runtime asked the model for more turns than the test scripted"). Those tests time real `bash` runs, and my measurement scripts were running at the same time. The file passed alone (`44 passed in 5.10s`).
  - **Stopping it.** I stopped that run to add af3e05e8. The stop killed only the forked sh child, so the parent script went on through gates 4–8 while the new run's packs ran.
  - **Final run.** The new run's gates 2–8 ran with nothing alongside, and their outputs replaced the stray ones. Gate 1 was rerun alone afterwards.

**Changes:**
- R-14 and R-15: f067088d (34 files, +1271/−868)
- R-13: 4f243bc9 (7 files, +115/−6) and af3e05e8 (1 file, +5/−1)
- R-15: 96705dfd (1 file, byte-width rewrap)
- review.md statuses: in this commit

**Gate matrix out (code HEAD af3e05e8):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| packs | gate 1 | PASS (rerun alone) | `1638 passed, 19 skipped in 145.24s (0:02:25)` |
| neighbour suites | gate 2 | PASS | `464 passed, 12 skipped in 16.89s` |
| full suite | gate 3 | PASS | `5653 passed, 32 skipped in 178.98s (0:02:58)` |
| lint | gate 4 | PASS (A002 577/703 IMPROVED, was 601; A001 643/643; A007 255/255; the others at or under their baselines) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | gate 5 | PASS | `5653 passed, 32 skipped in 183.92s (0:03:03)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| comment scope | added lines vs origin/main | PASS | `TOTAL spec-id comments=0 wide full-line comments=0 wide trailing comments=0` (was 295 / 701 / 0); `comment-format.md` awk over every new file: 0 lines |
| AST equality | every changed `.py` vs bae65c29 | PASS | `AST-equality: 38 changed .py files, 38 equal and clean, 0 with differences` |
| A002 by ref | repo `IntentAnalyzer` | 579 → 577 | `origin/main: A002 = 579` / `bae65c29: A002 = 601` / `HEAD: A002 = 577` |
| remote CI | `gh run view 38418651864` (head af3e05e8) | PASS (3.11, 3.12 and Package all success) | 3.11: `5646 passed, 39 skipped in 175.89s` / `CI passed.`; 3.12: `5646 passed, 39 skipped, 19 warnings in 191.73s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static policy | `gh run view 38418656187` (head af3e05e8) | PASS | `Ran 1 rule on 949 files: 0 findings.` (conclusion success) |
| invariants | INV-19 / INV-22 / frozen files | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py`, `tests/`, `lint/`, `pyproject.toml` and spec.md unchanged since bae65c29; origin/main 8387d666 is an ancestor of HEAD; the PR is still a draft |

**Still open:** nothing from this packet. Follow-ups: R-M4, R-M5, R-M7 and R-M8. For S6:
- The S3 sentence "A002 improved 703→623" was misleading: 703 is the stale baseline. The true counts are main 579, branch 601 before this iteration (+22) and 577 now (−2).
- 15 PR functions still pass A002 only through a neighbour's `@intent`; main has 78 such. The rule counts them as covered and never flagged them, so they were left alone. The list is in the report.

## Iteration 4 — 2026-10-13 16:42 UTC — agent report: none (see below)

**Report file:** the harness refused to let this subagent create `reports/S5-repair-4.md` ("Subagents should return findings as text, not write report files"). This entry is therefore the full record of the iteration.

**Defects in:** R-16, R-17, R-M11 (in that order), from the post-repair re-review round 1. The four packs started at `11 failed, 1638 passed, 19 skipped`; the 11 are the regression tests from 5ce6e85d. origin/main 8387d666 was already an ancestor of HEAD f9d062e6, so no merge was needed. review.md bookkeeping: R-16, R-17 and R-M11 are fixed; R-M10 stays a follow-up and was not touched.

**Hypotheses and attempts:**
- **R-16, reproduced.** All 8 R-16 cases failed with `DID NOT RAISE`.
  - **Root cause.** Spawn binds the id that Grok's `session/new` or Muse's `session/start` returns, in the vendor's spelling. Continue and fork lower-case their argument (R-8). `NativeTurnTable` compared the two exactly.
  - **Chosen: fold inside `NativeTurnTable`.** A private `_session_key` lower-cases the id when the table's harness is GROK or MUSE and returns it unchanged otherwise. `reserve`, `bind_session`, `release`, `is_session_busy` and `_finish` key `_busy_sessions` through it. `_reserved`, the handle and every wire frame keep the vendor's spelling. The method awaits nothing and calls no helper, so the reservation stays atomic and the call depth stays at one. It carries `@intent native-uuid-session-ids-ignore-case`.
  - **Why not the runner-up.** Lower-casing at `GrokWire.parse_session_id` and at the Muse spawn bind would change what the host sends: spawn's own `session/prompt` and `turn/start` would carry a spelling the vendor never produced. The table fix changes no traffic, and every path goes through the table: spawn's bind, continue's reserve, both forks' `is_session_busy`, the release on a failed spawn, and the done-callback. §8.5 also puts the rule on `reserve`.
  - **Flip condition.** A new harness with UUID ids must be added to the tuple in `_session_key`. If opencode ids ever become case-insensitive, the method can lower-case for every harness.
  - **opencode stays exact; no test pins it, so it was probed** (scratch script outside the worktree). Grok and Muse with the vendor id `ABCDEF01-…`: `is_busy(lower)=True`, `reserve(lower)` raises, the handle keeps `ABCDEF01-…`, and the key is freed after the driver finishes. opencode `ses_ABCdef0001`: `is_busy(ses_abcdef0001)=False` and `reserve` accepted; the exact spelling is busy. A second probe covered `release` after a bind: Grok and Muse are busy under both spellings before it and under neither after; opencode is busy only under its exact spelling.
  - **After.** All 8 pass, including the fork cases' "1 `peer` launch, 0 `oneshot`" (Grok) and "1 `turn/start`, no `session/fork`" (Muse). Packs: `3 failed, 1646 passed, 19 skipped` (the 3 R-17 cases).
- **R-17, reproduced.** The 3 cases failed with "INV-6: the credential leaked into ['decision title', 'tool output']".
  - **Fix.** `self._errors.scrub(<title>)[: NATIVE_APPROVAL_TITLE_MAX_CHARS]` at `grok/turn.py` `_answer_permission`, and at `muse/turn.py` `_on_approval` and `_on_user_input`. This is the expression opencode's `_reject` uses.
  - Both drivers hold the host's own factory (`errors=self._errors` at `grok/host.py:557` and `muse/host.py:613`), so a registered secret is scrubbed too.
  - `scrub` caps at 1000, so the 200 cap still decides the length.
  - Checked directly: `Edit README.md`, `''` and `'   '` are unchanged. `Run: export OPENAI_API_KEY=sk-proj-FAKE… && make deploy` becomes `Run: export OPENAI_API_KEY=<redacted> && make deploy`.
  - Packs: `1649 passed, 19 skipped`.
- **R-M11, measured.** A scratch scanner read every docstring line this PR adds under `vidbyte/` (diff against origin/main), skipping RELATED DOCS and TESTS. It found 103 lines in 43 files:
  - ARCHITECTURE NOTE 30, WHAT NOT TO DO 23, KNOWN EDGE CASES 21, ROLE IN CODEBASE 11, PURPOSE 8, COMMON MODIFICATION PATTERNS 5, FUNCTION INVENTORY 3;
  - the two named docstrings.

  The review counted 87, or 101 with `§`. The scanner also matches `Q-` and the `§9.2 rows …` forms.
- **R-M11, method.** It ran on the 103 listed lines only.
  1. **Exact hand rewrites,** each asserted to be used once, where the id carried meaning:
     - the opencode client's "EC-55 to EC-59 rows" became the five codes it raises (`opencode.server_unreachable, process_exited, not_signed_in, protocol_mismatch or api_error`), and "EC-56 from EC-55" became "process_exited from server_unreachable";
     - the Muse wire's "EC-98 … EC-113" became the failures that `_CODE_PROBLEMS` and `vendor_failure` produce;
     - "EC-156" became "the two benign decide or cancel races", and "the resume and retry of EC-114" became "one resume and one retry when Muse has not loaded the session";
     - "a §9.1 record" became "a validated record";
     - "the grok.* rows of spec §6.3" became "grok.* failure codes";
     - "outside the spec §13 list" became "Do not add a context key of your own; the keys are a fixed set that callers read";
     - "EC-92" became `opencode.mcp_server_failed`;
     - "EC-87", "EC-155's limit" and "EC-158's" became plain words;
     - "the 18 functions of §8.5" became "18 public methods in all";
     - "Owned mode follows FR-18 and D-4: argv …" became "In owned mode the argv is …";
     - "in §9.2 order" became "placed with the tools of its kind as the tuple already groups them", or "in a fixed catalogue order". No test pins the tuple order;
     - "D-2: every live turn" and "D-9: every live turn" became "Every live turn".
  2. **Then** a regex removed every parenthetical made only of ids, such as "(D-15)", "(INV-9, D-11)" or "(§9.2 rows 11-14, 20-24 and 27)". Each sentence already stated its rule.
  3. **Review.** I read every change word by word in a dry run before writing.
- **R-M11, proof that it is text only.**
  - With every docstring blanked, `ast.dump` is equal for all 43 files against the parent.
  - Exactly 45 docstrings changed: the 43 module headers, `MuseHost.track_muse_session_usage` and `_WireRecords`.
  - A rescan finds 0 lines.
  - A001, the only reader of module docstrings in `lint/` and the packs, stays at 643/643.
  - No `#` comment was added or changed, so the 72-column rule does not apply. Header fields stay single lines, as on main.
- **Rejected or avoided.**
  - Folding case for all three harnesses. It passes every pack but breaks INV-14 for opencode.
  - `str(session_id)` in the busy-error context, from a first draft to satisfy narrowing. The check was reordered instead, so the context dict is byte-identical.
  - Writing the report file through the shell after the harness refused it.
- **Gate run.** It ran once, in order, as one sequential script with nothing alongside, at 45ad54ec. There were no flakes and no WinError 10055.

**Changes:** R-16 1768c3d5 (`hostkit/turns.py`, +24/−11); R-17 1a9bc056 (`grok/turn.py`, `muse/turn.py`, 3 lines); R-M11 45ad54ec (43 files, +103/−103, docstrings only); review.md statuses and this entry in the verify-log commit. The push from b0e35a32 to 45ad54ec also carried the review, test and addendum commits f69b0bd3 to f9d062e6, which had not been on the remote.

**Gate matrix out (code HEAD 45ad54ec):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| packs | gate 1 | PASS | `1649 passed, 19 skipped in 153.45s (0:02:33)` |
| neighbour suites | gate 2 | PASS | `464 passed, 12 skipped in 17.11s` |
| full suite | gate 3 | PASS (first run, no flake) | `5664 passed, 32 skipped in 183.96s (0:03:03)` (iteration 3's 5653 plus the 11 new tests) |
| lint | gate 4 | PASS (A001 643/643, A002 577/703, A007 255/255, S062 889/889; no count rose) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | gate 5 | PASS | `5664 passed, 32 skipped in 182.97s (0:03:02)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| spec ids in headers | scratch scanner, added lines vs origin/main | PASS | `COUNTS {} TOTAL 0` (was 103) |
| docstring-only | AST with docstrings blanked vs 1a9bc056 | PASS | `files=43 code-differs=0 changed-docstrings=45` |
| remote CI | `gh run view 38432650695` (head 45ad54ec) | PASS (3.11, 3.12 and Package all success) | 3.11: `5657 passed, 39 skipped in 167.48s` / `CI passed.`; 3.12: `5657 passed, 39 skipped, 19 warnings in 188.28s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static policy | `gh run view 38432655274` (head 45ad54ec) | PASS | `Ran 1 rule on 949 files: 0 findings.` (conclusion success) |
| PR checks | `gh pr view 1036 --json isDraft` | n/a | `true` (dispatch-only workflows, so `gh pr checks` lists none); the PR is still a draft |
| invariants | INV-19 / INV-22 / frozen files | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py`, `tests/`, `lint/`, `pyproject.toml` and spec.md unchanged since f9d062e6; origin/main 8387d666 is an ancestor of HEAD; the PR is still a draft |

**Still open:** nothing from this packet. R-M10 stays a follow-up, as the orchestrator decided. R-M4, R-M5, R-M7 and R-M8 remain follow-ups. For re-review round 2:
- Grok and Muse ids are folded in two places on purpose: the caller's argument (`require_uuid(...).lower()`, R-8) and the busy-table key (R-16).
  - A spawn handle keeps the vendor's spelling.
  - Continue and fork return the lower-case spelling, because they reserve with the lower-cased argument.
  - INV-14 makes both the same session, and the R-16 tests deliberately do not assert the spelling.
- `_session_key` names GROK and MUSE explicitly, so any harness not listed is compared exactly.
- The R-M11 wordings a reviewer may want to check against the spec are the opencode client's five codes, the Muse wire's code list, and the toolsets' replacement for "§9.2 order".
