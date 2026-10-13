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

## Iteration 5 — 2026-10-13 17:29 UTC — agent report: none (see below)

**Report file:** none, as in iteration 4. The harness refuses subagent report files, so this entry and the agent's STATUS block are the full record.

**Defects in:** R-RR2-1 [Minor], from post-repair re-review round 2 (`reports/S5-rereview-2.md`). origin/main 8387d666 was already an ancestor of HEAD 7dcc0551, so no merge was needed.

**Hypotheses and attempts:**
- **R-RR2-1, every mapping the module performs.** I read `grok/wire.py` in full, plus the factory methods it calls (`hostkit/errors.py:82-140`).
  - `vendor_error`:
    - -32000 → `grok.not_signed_in`;
    - -32002, or an `FS_NOT_FOUND` payload → `grok.session_not_found`;
    - -32601 → `grok.capability_missing`;
    - -32602 on a request that sent a cursor → `configuration.invalid_argument` (line 245, through `NativeErrorFactory.invalid_argument`);
    - -32700 and -32600 → `grok.protocol_mismatch`;
    - any other code, -32602 without a cursor included → `grok.api_error`;
    - a failure with no JSON-RPC error → `from_protocol_error`, which gives `grok.server_unreachable`, `process_exited`, `api_error` or `protocol_mismatch`.
  - `check_cli`: `from_launch_failure` (`grok.not_installed` or `process_exited`), then `grok.turn_timed_out`, `grok.server_unreachable`, `grok.not_signed_in` and `grok.api_error`.
  - The parse and check methods: `grok.protocol_mismatch`, `version_unsupported`, `capability_missing` and `model_unknown`.
  - Every other path builds its code with `self._errors.code(...)`, which gives `<harness>.<problem>`. So line 245 is the only failure outside `grok.*`.
- **Fix.** The PURPOSE sentence now ends "…to grok.* failure codes, except a cursor Grok refuses, which is configuration.invalid_argument."
  - The added clause is 71 characters and cites no spec id. The field stays one line, as on main; A001 only checks that each field is present.
  - It says "a cursor Grok refuses", not "a stale cursor". The spec row covers a stale or a foreign cursor, and the code's own message names both.
- **Proof that it is text only.**
  - A scratch script compares `ast.dump` with the module docstring blanked. Against 7dcc0551 it prints `ast-equal-with-module-docstring-blanked=True` and `module-docstring-changed=True`.
  - `git diff --stat 7dcc0551 df9566fa`: 1 file, +1/−1. The committed blob has 0 CR bytes.
- **The header's other claims, checked and left alone.**
  - **Held:**
    - FUNCTION INVENTORY lists every method;
    - all three KNOWN EDGE CASES;
    - WHAT NOT TO DO 2 (no process, no await);
    - ROLE IN CODEBASE: host.py and turn.py read only the JSON-RPC envelope's `method` and `id` (turn.py:79, 101, 182 and 184), never an ACP payload field.
  - **Not true. Reported here, not fixed, because the brief allowed only the R-RR2-1 clause:**
    1. The `GrokWire` class docstring (wire.py:63) says "into records or grok.* errors". It leaves out the same cursor case as R-RR2-1. It is a class docstring, not the module header.
    2. WHAT NOT TO DO 1 says vendor text goes only into context values. But `require_model` (wire.py:189) puts Grok's own `currentModelId` into the message. `build` scrubs the message, so nothing leaks; only the claim is wrong.
    3. COMMON MODIFICATION PATTERNS says a new CLI failure text is a marker in `GROK_NOT_SIGNED_IN_MARKERS`. That holds only for a sign-in failure, because any marker added there raises `grok.not_signed_in`.
- **Remote 3.11 failure on attempt 1.**
  - **The failure.** In run 38437336454 attempt 1, `tests/features/muse_host/test_muse_host_turns.py::test_interrupt_answered_interrupted_or_cancelled_counts_as_success[interrupted]` failed on Linux 3.11 with `NativeHostError: The Muse Code process stopped before it answered.` It came from `McpProtocolError: MCP transport closed` while `interrupt_muse_turn` was awaiting `turn/interrupt`. 3.12 passed in the same run.
  - **Why df9566fa did not cause it.** The code is AST-identical to 45ad54ec, where both Pythons were green (run 38432650695).
  - **Cause, read from the code. Not fixed: it is outside this iteration's one clause.**
    1. The fake's `turn_interrupt` (`fake_muse_peer.py:489-491`) sets `interrupt_event` before it writes its answer. So its turn thread can send `turn/completed` (cancelled) first.
    2. `MuseTurnDriver.run` stops on `turn/completed` and closes the peer in its `finally` block (`muse/turn.py:135-137`).
    3. If that close lands before the reader hands over the interrupt answer, the pending `peer.call("turn/interrupt")` (`muse/turn.py:148`) fails with "transport closed". `NativePeer.call` maps that to `muse.process_exited` (`hostkit/peers.py:97`).
  - **Input, state and wrong output.**
    - Input: `interrupt_muse_turn` on a turn that Muse ends at the same moment.
    - State: the driver has already closed the peer.
    - Wrong output: the caller gets `muse.process_exited` instead of `was_running=True`.
    - A real Muse can send the same order of frames, so this is a host race, not only a fixture race. The verify log records no earlier failure of this test.
  - **Local check.** On Windows, the 8 interrupt tests passed in 25 of 25 runs (200 executions).
  - **Rerun.** `gh run rerun 38437336454 --failed`: attempt 2 is green on 3.11.

**Changes:**
- R-RR2-1: df9566fa (`grok/wire.py`, 1 line, module docstring only).
- This entry: in the verify-log commit.
- The push 44545f3f..df9566fa also carried 71be15fd and 7dcc0551 (docs only), which had not been on the remote.

**Gate matrix out (code HEAD df9566fa):** the brief's five local gates were run once, in order, as one sequential script with nothing alongside. Gates 2 and 3 of this log were not run on their own; the source stage runs the full suite.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| packs | gate 1 | PASS | `1649 passed, 19 skipped in 150.27s (0:02:30)` |
| lint | gate 4 | PASS (A001 643/643, A002 577/703; no count rose) | `A001 RATCHETED: 643 known finding(s).` / `A002 IMPROVED 703 -> 577.` / `SDK-LINT: PASS` |
| source stage | gate 5 | PASS (first run, no flake) | `5664 passed, 32 skipped in 184.93s (0:03:04)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| docstring-only | AST with the module docstring blanked vs 7dcc0551 | PASS | `ast-equal-with-module-docstring-blanked=True` / `module-docstring-changed=True` |
| remote CI | `gh run view 38437336454` (head df9566fa) | attempt 1 FAIL (3.11: 1 Muse interrupt test, see above; 3.12 success); attempt 2 PASS (3.11, 3.12 and Package all success) | attempt 1, 3.11: `1 failed, 5656 passed, 39 skipped in 181.85s` / `CI failed: …`; attempt 2, 3.11: `5657 passed, 39 skipped in 180.20s` / `CI passed.`; 3.12: `5657 passed, 39 skipped, 19 warnings in 189.29s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static policy | `gh run view 38437340236` (head df9566fa) | PASS | `Ran 1 rule on 949 files: 0 findings.` (conclusion success) |
| PR | `gh pr view 1036 --json isDraft` | n/a | `true`; the PR is still a draft |
| invariants | INV-19 / INV-22 / frozen files | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `tests/`, `lint/`, `pyproject.toml`, `failure.py` and `docs/` unchanged by df9566fa; origin/main 8387d666 is an ancestor of HEAD |

**Still open:**
- **The Muse interrupt race above.** It is intermittent and seen once, on Linux 3.11. It is a host defect, not a flaky test. A fix belongs in the host: when `turn/interrupt` fails because the driver itself closed the peer after `turn/completed`, the turn has stopped, so the interrupt should succeed. A deterministic regression test should order `turn/completed` before the interrupt answer. Nothing was built here.
- **The three header claims above.** They are wording only, with no behaviour change.
- **Follow-ups:** R-M4, R-M5, R-M7, R-M8 and R-M10 are unchanged.

## Iteration 6 — 2026-10-13 19:01 UTC — agent report: none (see below)

**Report file:** none, as in iterations 4 and 5. Subagent report files are refused, so this entry and the agent's STATUS block are the full record.

**Defects in:** R-18 [Major], R-19, R-20 and R-21 [Minor] from review.md's RACE-1 section, plus the three GrokWire header claims recorded in iteration 5. The blind RACE-1 tests (ba70578e) were red at 68cc1a9e. The orchestrator's `-k "loses_to or answered_after_turn_completed or rejected_with_32030 or still_closing or interrupt_answered_interrupted_or_cancelled"` command gave `8 failed, 4 passed`, reproduced here. origin/main 8387d666 was already an ancestor, so no merge was needed.

**Hypotheses and attempts:**
- **R-18 (Muse interrupt).**
  - **Cause, as the review found.** `MuseTurnDriver.run` closes the peer in its `finally` once the ack's own `turn/completed` is read. `McpStdioTransport.close` then fails the pending `turn/interrupt` with reason `closed`, and `NativePeer.call` maps that to `muse.process_exited`.
  - **Fix.** In `MuseTurnDriver.interrupt`:
    - a new `except NativeHostError` re-raises only when `self._completed is None`;
    - the `McpProtocolError` branch raises `vendor_failure` only when `self._completed is None` and the code is not -32013 or -32014.

    The host still returns `was_running=True`.
  - **Why `_completed`, and not `running` or the answer code.** Keyed this way, EC-96 (`turn/interrupt` `mode: exit`, no `turn/completed`), EC-97 (`on_interrupt: ignore`, silent) and the EC-102 guard (-32030 on a running turn) keep raising.
  - **A moot interrupt falls through and sets `_stop_source` and the grace deadline. This is harmless:** `run` builds its result before its `finally` closes the peer. Between `_on_completed` and `_outcome()` there is no await, except the turn-ceiling stop branch.
  - **Why the -32030-after-`turn/completed` case cannot slip past the guard.** The reader dispatches `turn/completed` before the answer. So the driver's inbox wake-up is queued before the interrupt task's, and the driver sets `_completed` in one step, without awaiting. Then the interrupt task sees it.
- **R-19 (Grok cancel write).**
  - **`GrokTurnDriver.ended`, a read-only property.** It is True when the `session/prompt` future is done, is not cancelled, and has either no exception or a `McpProtocolError` with `"error"` in its details, that is a JSON-RPC error answer. It is False while the future is pending or when it failed for a transport reason (closed, process_exited, reader_failed).
  - **Why not a plain `_answer.done()`.** It would also be True after a transport failure, and would hide EC-51 once the peer had fully exited.
  - **The cancel write.** `interrupt` wraps the `session/cancel` notify in `except NativeHostError: if not self.ended: raise`. The send still goes through `NativePeer.notify`, and its drain through `asyncio.wait_for`, in the caller's task, so the test seam engages; the `seam:` assertions hold.
  - **CI-1.** The post-drain `is_closing()` check in `tools/mcp/transport.py` is untouched.
  - **Edge of the predicate.** A non-mapping `session/prompt` result fails the future with a `McpProtocolError` that has neither `error` nor `reason`, so `ended` is False for it. This matches the review's predicate. A cancel written in that window raises process_exited, as before.
- **R-20 (Grok answered, driver still closing).** `interrupt_grok_turn` now checks `turn.done() or driver is None or driver.ended`, so it sends nothing and returns `was_running=False`.
- **R-21 (Muse steer).**
  - **Spec read.** EC-115 gives `muse.turn_not_found` when "the turn is no longer RUNNING". EC-96 gives `process_exited` when "the peer exits … before the awaited answer". The spec does not contradict the orchestrator's recommended key.
  - **Fix.** A new read-only `MuseTurnDriver.ended` (`self._completed is not None`) records the same fact R-18 keys on. `_steer` gains `except NativeHostError: if not driver.ended: raise`. Otherwise it raises `muse.turn_not_found`, built like the -32030 branch beside it: operation `steer_muse_turn` and `_TURN_NOT_FOUND_NEXT_STEP` (token `continue_muse_session`). The message is "The turn finished before Muse answered the steer.", because the host cannot know whether Muse applied the text.
  - **Rejected: the verifier's `not driver.running`.** `running` also drops when the driver leaves its loop because the peer died (`peer.closed and inbox.empty()` on its own poll). If that poll and the reader's EOF land in the same loop pass, the driver can drop `running` before the steer task handles its failure. A crash would then be reported as `turn_not_found`. `ended` cannot be True without this turn's own `turn/completed`.
  - **First passing run.** R-21's test had never passed under any fix before this iteration. It passed here 10 of 10 in the loop, and the EC-96, EC-97, EC-98, EC-101 and EC-102 steer rows stay green.
- **Wording ([iter5-wording]), text only.** The AST with docstrings blanked is unchanged.
  1. The `GrokWire` class docstring now names the cursor case (`configuration.invalid_argument`).
  2. WHAT NOT TO DO 1 now names the one exception: `require_model` puts Grok's `currentModelId` in its message. It also says the factory scrubs and caps both messages and context values (`build` → `scrub`, capped at `NATIVE_VENDOR_MESSAGE_MAX_CHARS`).
  3. COMMON MODIFICATION PATTERNS now says a marker in `GROK_NOT_SIGNED_IN_MARKERS` is for a sign-in failure only, because every marker raises `grok.not_signed_in`. Any other new CLI failure is a branch in `check_cli`.
- **Not tried, on purpose:**
  - removing or relaxing CI-1's `is_closing()` check (it fixed a real 3.12 EPIPE);
  - keying R-18 on `running` or on the answer code (it breaks EC-96 or EC-102);
  - moving the cancel send to the driver task (it breaks the R-19 seam);
  - re-checking after opencode's probe (out of scope).

**Observations, not findings (no change, out of scope):**
- **Grok, transport failure while the driver closes.**
  - *Input:* `interrupt_grok_turn` just after the Grok peer exited without answering `session/prompt`.
  - *State:* the answer future has failed with a transport error, and the driver is still in its `finally` close.
  - *Output:* `ended` is False, so `driver.interrupt` returns early on `_answer.done()` and sends nothing, but the host returns `was_running=True` without raising. The turn then records FAILED (`process_exited`).
  - Before R-20, the same window also covered an answered turn; R-20 narrowed it to this case. The window lasts one close of an already-exited process, so it is short.
- **Muse, steer or interrupt pending when the grace period closes the peer.** An earlier stop's grace period can close the peer with no `turn/completed`. A steer or a second interrupt still pending then raises `process_exited`, not `turn_not_found` or success. This follows from keying on the turn's own completion. EC-96 and EC-115 both plausibly apply to that window, and no test covers it.

**Changes:**
- R-18: 0284ffe1 (`muse/turn.py`)
- R-19: 0e900159 (`grok/turn.py`)
- R-20: 85788217 (`grok/host.py`)
- R-21: 241f1966 (`muse/turn.py`, `muse/host.py`)
- Wording: e4210fc3 (`grok/wire.py`, docstrings only)
- review.md statuses and this entry: in the verify-log commit

The A001 headers of all five files were updated where they described behaviour that has changed: FUNCTION INVENTORY lists both `ended` properties, and KNOWN EDGE CASES covers the moot interrupt, the moot cancel, the R-20 report and the R-21 steer. The scratch call-depth checker reports 0 chains before and after, and every added `#` comment is ≤ 72 columns.

**Determinism:**
- The new-test command, 10 runs in a loop: `12 passed, 61 deselected` every time (120/120).
- Both `*_turns.py` files plus `test_muse_host_errors.py`, 3 full runs: `331 passed, 3 skipped` each time (53.62s, 96.43s, 69.99s).

**Gate matrix out (code HEAD e4210fc3).** One sequential script, with nothing alongside and no flakes. Gates 2 and 3 were not run on their own; the source stage runs the full suite.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | the orchestrator's `-k` command | PASS 10/10 | `12 passed, 61 deselected in 3.15s` (run 10) |
| packs | gate 1 | PASS | `1659 passed, 19 skipped in 215.15s (0:03:35)` (1649 + 10 new) |
| lint | gate 4 | PASS (A001 643/643, A002 577/703, A007 255/255, S024 25/25, S062 889/889; no count rose) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | gate 5 | PASS | `5674 passed, 32 skipped in 208.57s (0:03:28)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| remote CI #1 | `gh run watch 38450551272 --exit-status` (head e4210fc3) | PASS (3.11, 3.12 and Package all success) | 3.11: `5667 passed, 39 skipped in 151.24s` / `CI passed.`; 3.12: `5667 passed, 39 skipped, 19 warnings in 157.21s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote CI #2 | `gh run watch 38450554202 --exit-status` (head e4210fc3) | PASS (3.11, 3.12 and Package all success) | 3.11: `5667 passed, 39 skipped in 187.43s` / `CI passed.`; 3.12: `5667 passed, 39 skipped, 19 warnings in 175.17s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| EC-51 (POSIX) | `test_interrupt_raises_process_exited_when_the_cancel_write_fails` (`@posix_only`) | PASS on 3.11 and 3.12 in both runs | 0 failures; 39 skips, the same count as in iterations 4 and 5, so it ran |
| remote static policy | `gh run watch 38450557318 --exit-status` (head e4210fc3) | PASS | `Ran 1 rule on 949 files: 0 findings.` (conclusion success) |
| PR | `gh pr view 1036 --json isDraft` | n/a | `true`; dispatch-only workflows, so `gh pr checks` lists none |
| invariants | INV-19 / INV-22 / frozen files | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py`, `tests/`, `lint/`, `.semgrep/`, `pyproject.toml` and spec.md unchanged since 68cc1a9e; `git status` clean |

**Still open:** nothing from this packet. R-18, R-19, R-20 and R-21 are fixed. The two observations above are recorded for the orchestrator and were not fixed. Follow-ups R-M4, R-M5, R-M7, R-M8 and R-M10 are unchanged.

## Iteration 7 — 2026-10-13 21:01 UTC — agent report: none (see below)

**Report file:** none, as in iterations 4 to 6. Subagent report files are refused, so this entry and the agent's STATUS block are the full record.

**Defects in:** R-22 and R-24 [Minor, `trivial`], from review.md's "Post-S6 findings". The blind tests from c1599d0b were red at 5228f3a3, reproduced here: `2 failed in 1.61s` (R-24's record is `Future exception was never retrieved … McpProtocolError('MCP transport closed')`). origin/main 8387d666 was already an ancestor, so no merge was needed.

**Hypotheses and attempts:**
- **R-22 (Muse `_forget_driver`).** This is the verifier's smallest fix, taken as written.
  - `_task` was renamed to `task`. After the pop, the method runs `if not task.cancelled(): task.exception()`, and Grok's `_forget` comment was copied word for word.
  - `exception()` does not consume the error, so `wait_muse_turn` still raises `muse.api_error`.
  - The `cancelled()` guard stays, because `exception()` raises on a cancelled task.
  - The header's KNOWN EDGE CASES gained one sentence.
  - Results: the R-22 test is green, and the Muse pack gives `471 passed, 5 skipped`.
- **R-24 (Grok `_launch`).**
  - **Fix.** `answer.cancel()` now runs just before the closed-host raise, with a 2-line comment of at most 72 columns. Only that raise path is touched; nothing changes on success.
  - **Transport, checked first.** A cancelled pending future is tolerated:
    - `:329` cancels its own future on a failed write;
    - `:525` only clears the map;
    - `:546` (`_fail_all_pending`) and `:613` (answer dispatch) skip done futures.
  - **`_closed` check.** It stays after `peer.send`, so no driver outlives `__aexit__`. The header's KNOWN EDGE CASES gained one sentence.
  - Results: the R-24 test is green, and the Grok pack gives `470 passed, 13 skipped`.
- **Not tried, on purpose:**
  - the wider single retrieval in `NativeTurnTable._finish`, which the review offered as an alternative;
  - moving `_closed` before the send.
- **Left as is, a narrower edge.** `answer.cancel()` is a no-op on a future that is already done. If the reader failed the answer during the drain and the host also closed, that exception stays unread. No test reaches this window.
- **Gate 5, first run red (inherited; not fixed; new item for the orchestrator).**
  - **The failure.** `tests/features/grok_host/test_grok_host_process_bounds.py::test_cancelling_a_call_propagates_and_stops_what_it_started[list_grok_sessions]` failed with "The Grok Build process did not answer in time." The run was `1 failed, 5675 passed, 32 skipped in 269.14s`, about 60 s over the usual time.
  - **Not R-24's change.** `list_grok_sessions` never reaches `_launch`.
  - **Cause: CPython 3.11's `wait_for` swallows a cancel (gh-86296).**
    1. Every NativePeer write names a deadline, so `McpStdioTransport._send` drains with `await asyncio.wait_for(stdin.drain(), seconds)` (`transport.py:323`; `_write_frame:423` does the same).
    2. On 3.11, `wait_for` wraps the drain in a task. If `task.cancel()` lands after that inner task finished but before the caller resumes, `wait_for` takes the `except CancelledError: if fut.done(): return fut.result()` branch, and the cancel is lost.
    3. `request` then waits the full control timeout (60 s in this test) on a silent fake, and raises `process_exited` instead of `CancelledError`. This breaks AC-4 and INV-2 in that window.
    4. 3.12+ builds `wait_for` on `asyncio.timeout` and is not affected.
  - **Evidence:**
    - **Rate.** Alone, the test failed 1 of 15 runs at 19582f13.
    - **Inherited.** It failed 1 of 40 runs with grok/host.py and muse/host.py restored to e4210fc3. `git diff e4210fc3 5228f3a3 -- vidbyte/` is empty, so the code under test was the iteration-6 head. That failure was the `[spawn_grok_session]` case.
    - **Mechanism.** A scratch pytest plugin outside the worktree wrapped `asyncio.wait_for` and logged any call that returned normally while `current_task().cancelling()` rose. Over 288 cases it logged exactly one event, `SWALLOWED cancel in wait_for(StreamWriter.drain, timeout=60.0) … cancelling 0->1`. That event came in the one failing case (60.4 s); no passing case had one.
  - **Remedy, validated but not applied.** The same plugin in "re-raise" mode raises `CancelledError` after such a call. Over 82 runs (328 cases) it saw 3 swallow events, in the spawn, continue and list cases. All three cases passed in 0.4 to 0.6 s, and there were 0 failures.
  - **Why not applied here:**
    - the brief limited this iteration to R-22 and R-24;
    - it touches the shared transport;
    - the obvious alternative, `async with asyncio.timeout(seconds)` in place of `wait_for`, would break R-19's contract seam. `cancel_drain_gate` in `test_grok_host_turns.py` wraps `asyncio.wait_for` and asserts `seam: no bounded wait followed the session/cancel write`.
  - **Proposed for iteration 8,** after S2 adds a deterministic test, for example a delegating `wait_for` seam that cancels the caller right after the inner drain completes:
    1. Move the bounded branch of both drain sites into one helper (`_drain(process, seconds)`) that keeps `asyncio.wait_for`, so the R-19 seam still engages.
    2. Before the drain the helper reads `task.cancelling()`. After it, it raises `asyncio.CancelledError` when the count rose, then makes the existing `is_closing()` check.
    3. `_send` adds `except asyncio.CancelledError:`, which pops and cancels the pending future, then re-raises. Without that, a cancel during a write leaves the future for `_fail_all_pending` to fail unseen, which is R-24's class.
    4. The default unbounded drain is untouched (INV-18).
- **Remote 3.11, attempt 1 red (inherited from main; not this branch's).**
  - **The failure.** `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` raised "MCP request timed out" on `request("second")`.
  - **Cause.** The test sleeps 0.05 s and then cancels "first". On a slow runner the cancel lands inside `start()`'s `create_subprocess_exec`, so "first" is never written. "second" is then the child's first line, which the child ignores.
  - **Same as main.** This path is main's: with no `timeout_seconds` and `stop_process_tree=False`, `_send` uses the plain drain and the spawn arguments are main's. The test file is unedited (`git diff origin/main -- tests/test_mcp_stdio_transport.py` is empty).
  - **History.** `gh run view <id> --log-failed` over the 36 most recent failed `ci.yml` runs of other branches found this same test with the same message in 17 runs on 15 main-based branches, from 2026-10-12 13:07 to 2026-10-13 01:41. Examples: `fix/eval-json-suite-reads-utf8-bom` 38333341120, `fix/mistral-top-level-error-message` 38323438129 and `fix/chat-missing-call-id` 38305915438.
  - **Rerun.** `gh run rerun 38465574661 --failed`: attempt 2 is green.

**Changes:**
- R-22: 48e9343a (`muse/host.py`, +6/−4)
- R-24: 19582f13 (`grok/host.py`, +4/−1)
- review.md statuses and this entry: in the verify-log commit
- The push 4ecd4012..19582f13 also carried c1599d0b (the tests) and 5228f3a3 (docs), which had not been on the remote.

**Determinism:**
- The two new tests, 10 runs in a loop: `2 passed` every time (20/20).
- The RACE-1 command, once: `12 passed, 63 deselected in 3.27s`. This is 61 + the 2 new tests in those files, deselected.

**Gate matrix out (code HEAD 19582f13).** One sequential script ran gates 1 and 4 to 7 with nothing alongside; gate 5 was rerun alone after its first-run failure above. Gates 2 and 3 were not run on their own; the source stage runs the full suite.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | the two Addendum 4 tests | PASS 10/10 | `2 passed in 1.22s` (run 10) |
| RACE-1 | the orchestrator's `-k` command | PASS | `12 passed, 63 deselected in 3.27s` |
| packs | gate 1 | PASS | `1661 passed, 19 skipped in 161.44s (0:02:41)` (1659 + 2) |
| lint | gate 4 | PASS (A001 643/643, A002 577/703, A007 255/255, S006 0 CLEAN, S024 25/25, S062 889/889; no count rose) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | gate 5 | first run FAIL (1, the inherited 3.11 swallowed-cancel race above); rerun PASS | first: `1 failed, 5675 passed, 32 skipped in 269.14s`; rerun: `5676 passed, 32 skipped in 204.12s (0:03:24)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| remote CI | `gh run view 38465574661` (head 19582f13) | attempt 1: 3.11 FAIL (inherited main flake above), 3.12 success; attempt 2 (`rerun --failed`): 3.11, 3.12 and Package all success | attempt 1, 3.11: `1 failed, 5668 passed, 39 skipped in 177.31s`; attempt 2, 3.11: `5669 passed, 39 skipped in 186.42s` / `CI passed.`; 3.12: `5669 passed, 39 skipped, 19 warnings in 189.93s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static policy | `gh run view 38465578419` (head 19582f13) | PASS | `Ran 1 rule on 949 files: 0 findings.` (conclusion success) |
| PR | `gh pr view 1036 --json isDraft` | n/a | still a draft; dispatch-only workflows, so `gh pr checks` lists none |
| invariants | INV-19 / INV-22 / frozen files | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py`, `tests/`, `lint/`, `.semgrep/`, `pyproject.toml`, `contracts/` and spec.md unchanged since 5228f3a3; `git status` clean after the code commits |

**Still open:**
- R-22 and R-24 are fixed.
- **New, not routed:** the CPython 3.11 swallowed cancel in the bounded drain (`transport.py:323` and `:423`), above.
  - It is a real host defect (AC-4 and INV-2 on 3.11), it predates this iteration, and it makes `test_cancelling_a_call_propagates_and_stops_what_it_started` fail in about 1 of 12 to 1 of 40 local file runs.
  - The remote 3.11 leg can hit it too.
  - The validated remedy and its constraint, the R-19 seam, are recorded above.
- **Inherited from main:** `test_cancelled_waiter_does_not_break_transport` on slow runners.
- Follow-ups R-M4, R-M5, R-M7, R-M8 and R-M10 are unchanged.

## Iteration 8 — 2026-10-13 22:15 UTC — agent report: reports/S5-repair-8.md

**Defects in:** R-25 [Major], the CPython 3.11 swallowed cancel (gh-86296) in three bounded waits of `vidbyte/tools/mcp/transport.py`: the `_send` drain (`:323`), the `_write_frame` drain (`:423`) and the `_answer` wait (`:349`), lines at a425d3fa. The 7 Addendum 5 cases were red at a425d3fa, reproduced here: `7 failed, 15 deselected in 22.04s`. origin/main 8387d666 was already an ancestor, so no merge was needed. review.md had no row for it; this iteration appended "Post-iteration-7 finding — 3.11 swallowed cancel (R-25)".

**Hypotheses and attempts:**
- **R-25, the drains (f5a2c74a).** This is the iteration-7 remedy, as the orchestrator ruled.
  - A new leaf helper, `McpStdioTransport._drain_within(stdin, seconds)`, a `@staticmethod`. It reads `asyncio.current_task().cancelling()`, then calls `asyncio.wait_for(stdin.drain(), seconds)` through the `asyncio` module, in the caller's task, with the drain coroutine passed directly. After the wait it raises `asyncio.CancelledError` when the count rose, then makes the CI-1 `is_closing()` check, which moved into the helper from both call sites.
  - `_send` gained `except asyncio.CancelledError:`, which pops and cancels the request's pending future and re-raises.
  - `_write_frame` only calls the helper; it has no pending future to drop.
  - Result: the 4 drain cases went green at once (`4 passed, 18 deselected in 2.72s`).
- **R-25, the answer wait (3917b49a).** `_answer` reads the cancel count before its `try`. Inside the `try`, after `asyncio.wait_for(future, timeout=seconds)`, it raises `CancelledError` when the count rose, so the existing `except asyncio.CancelledError` cleanup runs. The wait itself is unchanged in shape. Result: all 7 cases green (`7 passed, 15 deselected in 3.84s`).
- **Header and comments.** The module header (the older "Context Protocol Header" form, already counted in A001's 643) gained a "Known edge cases:" section on the 3.11 swallow, and its Architecture text names `_drain_within`. The helper carries `# @intent mcp-stdio-bounded-drain-keeps-the-cancel`. Every added `#` line is at most 72 columns. The scratch call-depth checker reports 8 flagged methods before and after: `_send` and `_write_frame` were already in that list, and the helper is a leaf.
- **Not taken, on purpose:**
  - `async with asyncio.timeout(seconds)` in place of `wait_for`: it breaks `drain_window_gate`, `answer_window_gate` and R-19's `cancel_drain_gate`, which key on `asyncio.wait_for`.
  - One generic helper that wraps both the drain and the answer wait: the seams would still engage, but the ruling keeps the answer wait in `_answer`, inside its `try`.
  - Limiting the `_send` cleanup and the `_answer` check to calls that pass `timeout_seconds`: see the INV-18 note below.
  - The close-path waits (`:473`, `:499`, `:509`): untouched, by the ruling.
- **INV-18 note, for the orchestrator.** `_answer` also serves the default `request()` path, and the `_send` cleanup catches a cancel during the plain drain too. With defaults, two things now differ from main, and only for a call that was cancelled:
  - a cancelled default write no longer leaves its future in `_pending`;
  - on 3.11, a cancel that lands in the gh-86296 window raises `CancelledError` where main returned the answer.

  Neither is visible to a caller that was not cancelled. The default drain line and the spawn arguments are main's, and main's tests pass unchanged (`tests/test_mcp_stdio_transport.py`, `tests/test_mcp_studio_server.py` and `tests/test_mcp_bridge.py`: `59 passed in 2.26s`; also inside gate 5). Guarding both on `timeout_seconds` would need a flag argument whose only job is to keep main's leak, so it was not done.
- **The R-22/R-24 pair (the orchestrator's 1-in-62 at 19582f13).**
  - **Reproduced once.** In the 30-run loop, run 7 failed in 34.42 s. The failing test was R-22's `test_failed_turn_never_waited_logs_no_unretrieved_exception`, on its precondition: `AssertionError: precondition: the fake did not send a failed turn/completed for both turns`. The twin check passed, so the host failed the waited turn correctly. Full output: scratch `s5-repair-8/loops/pair-7.log`.
  - **Not the swallow class.** The test cancels nothing. The 30 s is the test's own `wait_until(..., WAIT_SECONDS)` on the fake's `sent` records.
  - **Cause: a race in the fake.** In `fake_muse_peer.py`, `FrameWriter.send` (`:87-95`) flushes the frame to stdout first and writes its `sent` record only afterwards, outside the writer lock. `MspPeer.run` (`:258-265`) calls `os._exit(0)` as soon as it reads stdin EOF. The host's turn driver closes the peer as soon as it reads `turn/completed`, so the fake can exit between the flush and the `sent` record. The record is then lost, and the predicate never sees two `failed` frames.
  - **Proof, in a scratch copy outside the worktree.** `git archive HEAD` was extracted to scratch `s5-repair-8/copy`, and a `time.sleep(0.2)` was added between the `turn/completed` flush and its `sent` record. The test then failed 3 of 3 runs with the same message, at 31.2 to 31.3 s.
  - **Proposed fix (a test change, so not applied; routed to the orchestrator).** Write the `sent` record inside the writer lock, and have the EOF branch take the writer lock before `os._exit(0)`:
    ```diff
    @@ FrameWriter.send
                 except (OSError, ValueError):
                     os._exit(0)
    -        self.log.write("sent", frame=frame)
    +            self.log.write("sent", frame=frame)
    @@ MspPeer.run (EOF branch)
                     if self.scenario.get("ignore_eof"):
                         held(self.scenario)
    +                self.writer.lock.acquire()
                     os._exit(0)
    ```
    With the 0.2 s window kept, this passed 3 of 3 runs (1.51 s each). Without the window, the whole Muse pack in the copy gave `471 passed, 5 skipped in 75.49s`. Diff: scratch `s5-repair-8/fake-fix.diff`.
  - **Rate.** 1 failure in 90 fresh-process runs this iteration (the 30-run loop, then 60 more with kept logs, all green). 120 repeats inside one session were all green. The Grok fake has the same flush-then-log order (`fake_grok_peer.py:74-76`), but no Grok test has been seen failing from it.
- **Not tried:** a 3.12+ local run. No local 3.12+ interpreter has pytest-asyncio, and no `pip install` was allowed. CI's 3.12 leg covers it (below).

**Changes:**
- R-25, drains: f5a2c74a (`tools/mcp/transport.py`)
- R-25, answer wait: 3917b49a (`tools/mcp/transport.py`); the two commits are +53/−15 together
- review.md R-25 section, this entry and reports/S5-repair-8.md: in the verify-log commit
- The push 32d7ef51..3917b49a also carried 5e4c3c34 and 15fd9332 (the tests) and a425d3fa (docs), which had not been on the remote.

**Determinism (code HEAD 3917b49a; scratch `s5-repair-8/loops/`):**
- The 7 Addendum 5 cases, 10 runs in a loop: `7 passed, 15 deselected` every time (70/70), 4.02 to 4.66 s.
- RACE-1 and R-19, once: `12 passed, 63 deselected in 4.00s`.
- The existing AC-4 test, 30 runs: `4 passed` every time (120/120 cases). Runs 5 and 23 took 6.50 s and 6.05 s; the rest took 2.4 to 4.3 s. A swallowed cancel would take about 60 s.
- The R-22/R-24 pair, 30 runs: 29 green and 1 red (run 7, the fake race above). Then 60 more fresh runs: 60/60 green.

**Gate matrix out (code HEAD 3917b49a).** One sequential script ran gates 1 and 4 to 7, with nothing alongside. Gates 2 and 3 were not run on their own; the source stage runs the full suite.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | the orchestrator's `-k "answer_arrives or drain_finishes"` | PASS 10/10 | `7 passed, 15 deselected in 4.41s` (run 10) |
| RACE-1 / R-19 | the orchestrator's `-k` command | PASS | `12 passed, 63 deselected in 4.00s` |
| AC-4 | `test_cancelling_a_call_propagates_and_stops_what_it_started`, 30 runs | PASS 30/30 | `4 passed in 2.73s` (run 30) |
| R-22/R-24 pair | 30 runs, then 60 runs | 89/90 (1 test-fake race, above) | run 7: `1 failed, 1 passed in 34.42s`; run 60 of 60: `2 passed in 1.54s` |
| packs | gate 1 | PASS | `1668 passed, 19 skipped in 182.38s (0:03:02)` (1661 + 7) |
| lint | gate 4 | PASS (A001 643/643, A002 577/703, A007 255/255, S006 0 CLEAN, S019 5/5, S024 25/25, S039 5/5, S045 2/2, S062 889/889; no count rose) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | gate 5 | PASS | `5683 passed, 32 skipped in 200.06s (0:03:20)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| remote CI #1 | `gh run view 38475662280` (head 3917b49a) | PASS (3.11, 3.12 and Package all success) | 3.11: `5676 passed, 39 skipped in 184.23s` / `CI passed.`; 3.12: `5676 passed, 39 skipped, 19 warnings in 195.64s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote CI #2 | `gh run view 38475671014` (head 3917b49a) | PASS (3.11, 3.12 and Package all success) | 3.11: `5676 passed, 39 skipped in 182.43s` / `CI passed.`; 3.12: `5676 passed, 39 skipped, 19 warnings in 174.85s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote static policy | `gh run view 38475673751` (head 3917b49a) | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| PR | `gh pr view 1036` | n/a | still a draft; dispatch-only workflows, so `gh pr checks` lists none |
| invariants | INV-19 / INV-22 / frozen files | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py`, `tests/`, `lint/`, `.semgrep/`, `pyproject.toml`, `contracts/` and spec.md unchanged since a425d3fa; the only code change since a425d3fa is `vidbyte/tools/mcp/transport.py` |

The 3.12 legs are green, and on 3.12 the request-site never-retrieved check passes only with the `_send` cleanup (test-plan Addendum 5). So both legs exercised it. Neither CI run hit the inherited `test_cancelled_waiter_does_not_break_transport` flake, so no rerun was needed.

**Still open:**
- R-25 is fixed.
- **New, for the orchestrator (a test change, not applied):** the `fake_muse_peer.py` race above. It makes R-22's test fail its precondition about 1 run in 30 to 90, in a fresh process on Windows. The product code is not involved. The proposed two-line fake fix and its validation are above.
- The INV-18 note above is recorded for adjudication; no change is pending.
- Follow-ups R-M4, R-M5, R-M7, R-M8 and R-M10 are unchanged. The close-path waits (`:473`, `:499`, `:509` at a425d3fa) remain the decided follow-up.
