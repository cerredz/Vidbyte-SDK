VERDICT: SOUND WITH FIXES — The architecture holds and the error contract is unusually complete, but the MuseHost wire contract leaves out required MSP fields, so every Muse spawn would fail. The spec also defines no records for inbound wire frames, and five process and approval paths can hang or orphan work.

WHAT THE SPEC GETS RIGHT
- **Error contract.** Every function has its own error table with a required next-step token, which AC-2 makes testable through the §13 fakes.
  - The 53 new codes (13 Grok, 16 opencode, 15 Muse, 9 backend) are appended after `RULE_EVALUATION_FAILED` (`vidbyte/lib/enums/failure.py:144`), away from the `:34` and `:35-46` areas that other PRs edit.
  - `FailureCode.from_exception` already reads `failure_code`, so the failure router needs no change.
- **D-15, tools kept out of the `builtins` export.** This is verified against `vidbyte/lib/registries/components.py` `_discover`, which turns every `BaseTool` subclass in `vars(builtins)` into a YAML-declarable component.
  - So leaving the host tools out keeps WRITE tools out of YAML.
  - The root `vidbyte/__init__.py` `__all__` is untouched, and it is the C016 contract source (`lint/core/public_api_contract.py`), so no contract regeneration is needed.
- **The spec anticipates most lint traps:**
  - D-8 puts `RecordFieldValidator` in C008's canonical `vidbyte/lib/dataclasses/validation.py`, with the C002-exempt identity `value`.
  - S045 forces `timeout_seconds`.
  - S054-safe names: `OPENCODE_SERVER_LOGIN`, and `server_password` defaults to `None`.
  - S011 is respected: opencode goes through `HttpTransport` with `retry_count=0`, so `prompt_async`, fork and revert are never sent twice.
  - The `timeout_seconds` checks in the extended transport raise `McpProtocolError`, not `ValueError` (S016).
- **Safety posture is conservative and explicit:**
  - `GrokPermissionMode` has no auto or bypass member.
  - Muse runs with a fixed `denyUnmatched`.
  - Approval answers are recorded and capped.
  - `next_step` is never empty (INV-8).
  - The MCP-server permission gap (T-5) is documented and handled with `read_only` toolsets, not by silently changing `McpStudioServer`.

FINDINGS

R-1 [Blocker] [L3/L5] §8.5 MuseHost "MSP calls" — The MSP contract leaves out `commandId` on five commands and other required fields, so every Muse spawn, continue and fork fails, and approvals hang.
  Evidence:
    - Spec §8.5 (line 1180): "`session/start` (`workspaceRoot`, `modelId`, `approvalMode: "denyUnmatched"`), `session/resume`, `session/fork` (`lastTurnId`) … `approval/decide`, and `userInput/cancel`. Each `turn/*` command carries a fresh `commandId` (UUID4)."
    - The MSP 1.0.1 schema (research `muse-1.0.1-msp.schema.json`) makes `commandId` required on:
      - `SessionStartParams`: "The SS2.5 idempotency handle (UUIDv7). Required; the server never mints one.";
      - `SessionResumeParams` and `SessionForkParams`: required `[commandId, sessionId]`;
      - `ApprovalDecideParams`: required `[approvalId, choiceId, commandId, requirementId, sessionId]`;
      - `UserInputCancelParams`: required `[commandId, sessionId, userInputId]`;
      - `TurnSteerParams`: required `[commandId, expectedTurnId, input, sessionId]`.
    - `SessionForkParams` has no `lastTurnId` member. It is nested as `cutPoint: ForkCutPoint{lastTurnId}`.
    - Every `commandId` is documented as UUIDv7, and `TurnStartedParams` says "`turnId == commandId` for fresh turns".
  Failure:
    - `spawn_muse_session` sends `session/start` without `commandId`. The server rejects it, EC-102 maps the rejection to `muse.api_error`, and no Muse session can ever start. Continue (`session/resume`) and `fork_muse_session` fail the same way.
    - If `fork_muse_session` sends a top-level `lastTurnId`, the field is ignored and the fork silently copies all history.
    - Without `commandId` and `requirementId`, `approval/decide` is rejected, so the approval stays pending and the turn blocks until the `max_turn_seconds` ceiling. That breaks INV-10 ("never hang") and D-11.
  Smallest fix:
    - In §8.5, list the required params for every MSP command the host sends:
      - `commandId` on `session/start`, `session/resume`, `session/fork`, `turn/start`, `turn/steer`, `turn/interrupt`, `approval/decide` and `userInput/cancel`;
      - `cutPoint: {lastTurnId}` for fork;
      - `expectedTurnId` for steer;
      - `approvalId`, `requirementId`, `choiceId` and `sessionId` for decide, copied from the `approval/requested` params;
      - `userInputId` for cancel.
    - Specify UUIDv7. Stdlib `uuid.uuid7` exists only from Python 3.14, so add a small `MuseWire` `@staticmethod` that builds an RFC 9562 v7 id from `time.time_ns()` and `secrets.token_bytes`. Only one feature uses it, so principle 5 allows it to stay local.
    - Change §13 "Determinism" (line 1937) to match.

R-2 [Blocker] [L8/L4] §9.1 / §8.4 — The spec defines no records for inbound wire frames. Drivers would therefore read raw `Mapping`s, against the field guide; the alternative of adding the records breaks the §8.4 budget, which forces a BLOCKED stop.
  Evidence:
    - The §9.1 records are all request, settings or output records. None parses an inbound frame:
      - ACP: `session/request_permission` params, `session/update`, the `session/prompt` result;
      - MSP: `approval/requested`, `userInput/requested`, `turn/completed`;
      - opencode: `PermissionRequest`, `QuestionRequest`, the `SessionStatus` entry, the assistant `error`.
    - §8.5 line 1068: `inbox: asyncio.Queue[Mapping[str, Any]]`.
    - §8.4: "52 records (§9.1)" and "_The implementer may not exceed this budget without stopping and reporting BLOCKED._"
    - Field guide `class-bound-helpers.md:47`, which `context/code-map.md:146` also quotes: "Parse the raw params into a lib record that mirrors the provider's wire schema field for field".
    - Field guide `strict-config-dataclasses.md:39`: "Harness bridge functions take validated lib records, not loose `object`/`Mapping` inputs".
  Failure: The `GrokTurnDriver`, `MuseTurnDriver` and `OpencodeTurnWatcher` decision logic reads nested raw dicts, such as `params["toolCall"]["kind"]` or `params["choices"]`. Either:
    - (a) the implementer adds the records and must stop BLOCKED at the budget; or
    - (b) the drivers ship with raw `Mapping` logic and draw the field-guide convention comment. D-13's "missing relied-on member raises `protocol_mismatch`" then has no single owner per frame.
  Smallest fix:
    - Add the inbound records to §9.1, in the per-host dataclass modules (rows 8-10), each with only the members the host relies on. For example:
      - `AcpPermissionRequest`, `AcpSessionUpdate`, `AcpPromptResult`;
      - `MspApprovalRequest`, `MspUserInputRequest`, `MspTurnCompleted`;
      - `OpencodePermissionRequest`, `OpencodeQuestionRequest`, `OpencodeSessionStatus`, `OpencodeAssistantError`.
    - Each `*Wire.parse_*` returns one of these records or raises `protocol_mismatch`.
    - Raise the §8.4 record count to match.

R-3 [Major] [L5] §8.5 transport `close()` / `NativePeer.close` — After the kill, the transport waits for the process without a time limit, so closing a peer can hang forever.
  Evidence:
    - Spec line 982: "`close()`: when `exit_grace_seconds > 0` … then continues with today's terminate, wait and kill path."
    - Spec line 1077: `NativePeer.close` "never raises; stdin EOF, grace, kill, reap".
    - `vidbyte/tools/mcp/transport.py` `close()`: after `process.kill()` it runs `await process.wait()` with no timeout.
    - `vidbyte/tools/builtins/bash.py:195-234` `_stop`: "Bound the wait after the kill … Python 3.12+ waits for the pipe". It uses `asyncio.wait_for(process.wait(), BASH_KILL_GRACE_SECONDS)` and then closes `process._transport`.
  Failure: On Windows, a Grok peer mid-turn has started a tool shell that inherited stdout. The grace period expires and only the direct child is killed (NG-15). The surviving grandchild keeps the pipe open, so `await process.wait()` never returns. As a result:
    - `interrupt_grok_turn` and `__aexit__` hang;
    - EC-8's "waits at most `NATIVE_STOP_GRACE_SECONDS`", INV-4 and NFR-2 are broken.
  Smallest fix:
    - Under the opt-in `exit_grace_seconds > 0` path only, so INV-18 still holds, bound the post-kill wait by `shutdown_timeout` and then close `process._transport`, as `bash.py` `_stop` does.
    - Add this to row 22 and the transport bullet in §8.5.

R-4 [Major] [L1/L5] §11 conflict 4 / NG-15 / Q-16 — The spec downgrades the request's Q-8 default (kill the tree, then kill inside the distro) on evidence from idle runs only, so interrupted turns can keep editing the workspace.
  Evidence:
    - Line 1698: "Resolved as protocol interrupt, stdin EOF, grace period, then direct kill. Limitation EC-10; optional Q-16".
    - Q-16's default is "No; it could kill the wrong process".
    - A-9 was "verified only while idle".
    - D-4 already builds `ProcessStopper.stop_tree` (`taskkill /T /F`).
    - NG-15 says "Recorded as limitation EC-9", but EC-9 is the concurrency row. The limitation is EC-10.
  Failure: `interrupt_muse_turn` runs during a running tool. `wsl.exe` is killed, but the in-distro `muse serve` and its shell keep running and keep writing to the workspace after the SDK reported `INTERRUPTED`. Grok tool shells on Windows behave the same way. The caller is told the work stopped when it did not.
  Smallest fix (PID-scoped, so the "wrong process" objection no longer applies):
    - (a) After the grace period, run `ProcessStopper.stop_tree` on the peer's pid. This needs an additive read-only `pid` on `McpStdioTransport`.
    - (b) For Muse, launch with `sh -c 'echo $$ >&2; exec "$0" serve' <muse_path>`. Read the pid from the bounded stderr buffer, and after the grace period run `wsl.exe -d <distro> -e sh -c 'pkill -KILL -P <pid>; kill -KILL <pid>'` through `CliRunner`.
    - If the author keeps the downgrade, it overrides a request default, so it must become a blocking Q for the user, not an optional one.
    - Fix the EC-9 cross-reference in NG-15 to EC-10.

R-5 [Major] [L5] D-11 opencode approvals — The watcher answers only its own session, so a child session's permission request hangs the turn.
  Evidence:
    - D-11: "The turn's watcher rejects every pending permission (`reply: "reject"`) and question (`/reject`) for its own session on each poll."
    - The §8.5 route list has no `GET /session/{id}/children`.
    - In opencode 1.18.31's OpenAPI, `PermissionRequest` and `QuestionRequest` carry their own `sessionID`, `Session` has `parentID`, and `/session/{sessionID}/children` exists.
  Failure: The turn's agent calls opencode's `task` tool, which runs a subagent in a child session (`parentID` = the turn's session). The child asks for `bash` permission with `sessionID` = the child. The watcher skips that request, so the child blocks and the parent stays `busy` until `max_turn_seconds`. The result is the ceiling or a `turn_timed_out`, not "denied and recorded" (INV-10).
  Smallest fix:
    - For an owned server, which serves only this host, reject every pending permission and question.
    - For an attached `server_url`, reject requests whose `sessionID` is the turn's session or one of its descendants, resolved through `GET /session/{id}/children` and cached for the turn.
    - Add the route to the §8.5 list and a row under EC-80 to EC-89.

R-6 [Major] [L3/L5] EC-85 / `OpencodeTurnWatcher` — The spec never says how the watcher identifies "the turn's user message", and the `retry` status is ignored.
  Evidence:
    - EC-85: "idle for `OPENCODE_IDLE_CONFIRMATIONS` polls in a row with no assistant reply to the turn's user message".
    - INV-11 returns the handle when `prompt_async` answers 204.
    - The host does not send `prompt_async`'s optional `messageID`, and no step records the user message.
    - `SessionStatus` includes `retry{attempt, message, action{reason,…}, next}`, but EC-80 to EC-89 never mention `retry`.
  Failure:
    - (1) `prompt_async` answers 204 before the session turns `busy` and before the user message is listed. Three idle polls (3 s) with "no reply" then raise a false `opencode.api_error` while the turn really runs, unwatched and with no approvals answered.
    - (1b) On `continue_opencode_session`, "the latest user message" can match the previous turn, so the previous reply is returned as this turn's result.
    - (2) A provider in a 429 retry loop shows `retry` for minutes. The caller sees `RUNNING` until the ceiling instead of `opencode.usage_limited`.
  Smallest fix:
    - Before `prompt_async`, record the newest message id (`GET …/message?limit=1`). The turn's user message is the first user message missing from that snapshot.
    - Start idle confirmations only after that message, or `busy`, has been seen.
    - Map `retry` with a rate-limit `action.reason` to `opencode.usage_limited` after a bounded number of polls, and record the reason in `context`.

R-7 [Major] [L5] D-2 / §13 Grok argv — `--no-leader` is missing, so a user's `use_leader` config breaks the per-turn peer model.
  Evidence:
    - §13 line 1918: "Grok appends `agent [-m <model>] [--reasoning-effort <effort>] stdio`".
    - Research `grok-1.0.13-help.txt` (`grok agent --help`, the version floor): "--leader  Connect to a shared leader process … Defaults to [cli] use_leader in config.toml" and "--no-leader  Start a new agent even when config enables leader mode".
  Failure: For a user with `[cli] use_leader = true`, every `grok agent stdio` peer attaches to one shared leader. As a result:
    - per-process `-m` and effort (D-2, EC-25) may not apply, which can cause a false `model_unknown` or the wrong model;
    - killing the peer leaves the leader running the turn (INV-4);
    - concurrent hosts share state.
  Smallest fix: Always pass `--no-leader` for `grok agent` (present on 1.0.13 and 1.0.52). Add it to §13 and to the EC-25 launch line.

R-8 [Major] [L5] §8.5 `CliRunner` / `ManagedProcess` — The spec never sets stdin for child processes, so they inherit the parent's stdin, including an MCP stdio stream.
  Evidence:
    - Line 1019 says only "feeds stdin_text". Neither the `CliInvocation` row (line 1387) nor `ManagedProcess` says what stdin is when `stdin_text` is `None`.
    - `asyncio.create_subprocess_exec` inherits the parent's stdin by default.
    - D-21 and T-5 explicitly support `McpStudioServer(tools=GrokTools(host))`.
  Failure: When the toolset is served over stdio MCP, `opencode serve` (`ManagedProcess`), `grok --version` and the one-shot runs inherit the MCP server's stdin. Any read by the child consumes the client's JSON-RPC bytes and corrupts the MCP session. A CLI that reads piped stdin also blocks until timeout, because that stdin never reaches EOF.
  Smallest fix: State the stdin rules:
    - in `CliRunner`, `stdin=PIPE`, then write and close it when `stdin_text` is set, or `stdin=DEVNULL` when it is `None`;
    - in `ManagedProcess`, always `stdin=DEVNULL`.
    - Add this to the process-helpers bullet and the A-5 note.

R-9 [Major] [L4/L2] D-3 — The spec introduces a two-way package dependency between `tools` and `harnesses`, and a long import chain.
  Evidence:
    - D-3: "A006 allows `harnesses → tools.mcp`".
    - Folder table, line 1761: the hosts import `vidbyte.tools.mcp.transport`.
    - Folder table, line 1763: `vidbyte/tools/builtins/` imports `vidbyte.harnesses.native.*`.
    - Today no module under `vidbyte/tools` imports `vidbyte.harnesses`, and nothing outside `tools/mcp` imports `tools.mcp.transport`.
    - AGENTS.md principle 3: "Data and dependencies flow in one direction only".
    - REPO_MAP describes `tools/mcp` as "attaching a third-party server … to one of this package's own agents".
    - The new chain is:
      1. `vidbyte/agents/__init__.py:64` imports `agents.coding`;
      2. `agents/coding.py:34` imports `vidbyte.tools.toolsets`, whose `__init__` exports the 4 new toolsets under D-15;
      3. those import `tools.builtins.<host>`, which imports `harnesses.native.<host>.host`;
      4. that runs `vidbyte/harnesses/__init__.py`, which imports `harnesses.client`;
      5. `harnesses.client` imports `vidbyte.sessions`, whose `sessions/serialization.py:20` imports `vidbyte.agents.types`;
      6. that re-enters the partly initialized `vidbyte.agents`.
  Failure: A006 passes, because it finds no concrete-module cycle. Still, every `import vidbyte.agents` now loads three hosts and the harness and session stacks. Whether `import vidbyte` succeeds now depends on import order, which is unverifiable until the code exists. Package layering also becomes bidirectional.
  Smallest fix: Either:
    - (a) keep D-3, record the package-level two-way edge and its justification in D-3, and add a P2/P4 exit check that imports `vidbyte`, `vidbyte.tools.toolsets` and each `vidbyte.harnesses.native.<host>` in fresh interpreters; or
    - (b) put the JSON-RPC stdio peer in `vidbyte/lib/process/` (for example `jsonrpc.py`, reusing `ProcessStopper`) and leave `McpStdioTransport` untouched. This drops rows 22 and 23 and the INV-18 risk.

R-10 [Major] [L8] §12.3 row 22 — Natural transcriptions of the transport change trip lint C006, S016 and C002, and row 22 does not name C002 or C006.
  Evidence:
    - Row 22's standards are "S012; S016 …; S039 …; A002".
    - §8.5 line 955 adds the constructor argument `exit_grace_seconds: float = 0.0` but does not say how to validate it.
    - The constructor's local template (`transport.py:122-129`) is `if request_timeout <= 0: raise ValueError(...)`. That passes NaN, ±inf and `True`, which C006 (`c006_finite_numeric_guards.py`, which judges `__init__` guards) flags, and it raises a builtin inside an S016 boundary prefix (`vidbyte/tools/mcp/`).
    - For `request(timeout_seconds=)`, the spec requires rejecting bool. An inline `isinstance(timeout_seconds, bool)` duplicates the existing identity at `vidbyte/workflows/validation.py:172`, which C002 flags (baseline 9).
    - §11 line 1620 says no count may rise.
  Failure: Copying the local guard for `exit_grace_seconds` raises the C006 and S016 counts, and the bool check in `request` raises the C002 count. `run_ci.py` then fails.
  Smallest fix:
    - In row 22 and the §8.5 bullets, validate both values through `RecordFieldValidator` (D-8; its identity `value` is C002-exempt, and C006 judges the helper).
    - Re-raise as `McpProtocolError` with reason `invalid_call`, including for an invalid `exit_grace_seconds`.
    - Add C002 and C006 to row 22's standards.

R-11 [Major] [L8] §12.5 — The README updates leave out `vidbyte/tools/README.md`, whose Key Modules section lists exactly the folders this PR changes.
  Evidence:
    - Rows 21, 23 and 47 update `vidbyte/lib/README.md`, `vidbyte/tools/mcp/README.md` and `vidbyte/harnesses/README.md` only.
    - `vidbyte/tools/README.md:89`: "`builtins/`: a minimal subprocess bash tool, code search, … and utility tools."
    - `vidbyte/tools/README.md:91`: "`toolsets/`: pre-assembled tool catalogs, including `CodingAgentTools` …".
    - AGENTS.md: "Each folder's own `README.md` documents that folder".
  Failure: After the PR, the tools README does not mention the 4 new `builtins/` subpackages, `native_host_tool.py` or the 4 new toolsets. That is a likely review comment, and agents navigating by README miss the host tools.
  Smallest fix: Add a MODIFY row (P5): extend the `builtins/` and `toolsets/` bullets in `vidbyte/tools/README.md` to name the native-host tools and the `GrokTools`, `OpencodeTools`, `MuseTools` and `HarnessBackendTools` toolsets, with the T-5 `read_only` note. Keep the change within A009.

R-12 [Minor] [L4] INV-7 — Tool error metadata uses `next_step`, but `ToolsFormatter` reads `hint` and `retryable`.
  Evidence:
    - INV-7: "The metadata holds `error` …, `next_step`, `operation` and `harness`."
    - `vidbyte/lib/tools/formatter.py:519-532` `_error_parts` reads `metadata["hint"]`, `["retryable"]` and `["detail"]`, and forwards them as structured fields, for example in Gemini's `functionResponse`.
  Failure: Structured tool-error responses carry no hint and no retryable flag. The next step survives only inside the output text, so MSP's `retryable` (EC-102) is lost.
  Smallest fix: Also set `metadata["hint"] = next_step`, and set `metadata["retryable"]` when the vendor reports it.

R-13 [Minor] [L6] `list_opencode_sessions` (§6.3.4, line 586) — The function fetches every session to return the top `limit`.
  Evidence:
    - The spec "sorts `GET /session` by `time.updated`, newest first, and keeps the first `limit` sessions".
    - In the opencode 1.18.31 OpenAPI, `GET /session` accepts `limit`, `start`, `search` and `roots`.
    - D-5 caps responses at `OPENCODE_MAX_RESPONSE_BYTES`.
  Failure: For a user with hundreds of sessions, each carrying `summary.diffs`, the unpaged list exceeds the cap. The over-cap error then makes `list_opencode_sessions` fail outright for exactly the heavy users.
  Smallest fix: Pass `limit` (and consider `roots=true`, which hides `task` child sessions) in the `urlencode` query. Keep the client-side sort, and record the server's ordering as an assumption.

R-14 [Minor] [L9/L5] EC-138 and T-2 — Two statements do not match the code or each other.
  Evidence:
    - (a) EC-138 says that for a missing required parameter the tool "Returns `ToolResult.error` with `metadata["error"] = "configuration.invalid_argument"`". But `vidbyte/tools/executor.py:61-66` runs `tool.validate_call(call)` first and returns `metadata={"error": "validation_error"}`, and `BaseTool.validate_call` (`tools/base.py:86-96`) already reports missing required parameters.
    - (b) T-2 (line 1533) says "Values go into argv only in `--name=value` form", but §13 line 1918 and EC-25 say `agent [-m <model>] [--reasoning-effort <effort>] stdio`.
  Failure:
    - (a) Through the agent path, a missing argument gives `validation_error` / `invalid_arguments`, never the EC-138 code, while tests that call `execute` directly pass.
    - (b) The implementer gets two conflicting argv forms.
  Smallest fix:
    - (a) Say that EC-138 covers what reaches `execute`, and that missing-required is the executor's `validation_error`; or have `NativeHostTool` override `validate_call` to return `None`.
    - (b) Use `--model=<id>` and `--reasoning-effort=<effort>` everywhere.

R-15 [Minor] [L10] §12.3 rows 19-20 — The insertion points in the shared `vidbyte/lib/errors` files risk merge conflicts and contradict a file header.
  Evidence:
    - Row 19: "`NativeHostError` after `CodexAgentError` (§8.5) … precedent `:129-153`".
    - Row 20: "Append `NativeHostError` to the import tuple and `__all__` | the file header's instruction". But the `vidbyte/lib/errors/__init__.py` header says "Add a new base error to both the import tuple and __all__ in alphabetical family order."
  Failure: The Codex and Claude host PRs are expected to touch the same anchor, next to `CodexAgentError`, under the shared-file contract, so a three-way conflict is likely. Row 20 also cites a header whose instruction it does not follow.
  Smallest fix: Append `NativeHostError` at the end of `base.py`, mirroring the `failure.py:144` choice. In row 20, cite the append-only shared-file contract as the reason for not using alphabetical order.

VERIFIED CLAIMS
- **D-3, the transport today:** HELD. Checked in `vidbyte/tools/mcp/transport.py`:
  - `request` uses the fixed `self.request_timeout`;
  - `close()` closes stdin and then terminates at once;
  - `_dispatch_stdout_line` drops frames that have no `id`;
  - an int `id` resolves a pending future even when the frame has a `method`.

  The spec does not note one more fact: the post-kill `await process.wait()` has no time limit (R-3).
- **D-6 / INV-8, `FailureCode`:** HELD. `RULE_EVALUATION_FAILED` is the last member, at `failure.py:144`. `CONFIGURATION_INVALID_ARGUMENT` is at `:34`, the Codex block at `:35-46` and `RUNTIME_ERROR` at `:106`. `from_exception` reads `failure_code` through `getattr(..., "value", ...)`. The 53 codes add up as 13 + 16 + 15 + 9.
- **D-6, no import cycle:** HELD. `vidbyte/lib/errors/base.py` imports only `collections.abc` and `typing`. The constants modules import only constants and enums, and the enums import `agents.pricing` only lazily or under `TYPE_CHECKING`.
- **D-16, placement:** HELD. `vidbyte/lib/configs/` exists with `__init__.py` and `structured_output.py`.
- **D-15 / C016:** HELD. `components.py` `_discover` takes `BaseTool` subclasses from `vars(builtins)` and has no toolsets kind. The root `__all__` (`vidbyte/__init__.py`) is the source of `public_api_contract.py`.
- **D-5, `HttpTransport.request`:** HELD. The signature matches. An over-cap response raises `ProviderRequestError` with `status_code` set, a connect failure has `status_code=None`, and each call creates a new `AsyncClient`.
- **D-7, the redactor:** HELD. `HarnessRedactor.safe_error_message(self, error, *, max_chars=1000)` exists. It is an instance method, so the spec's helper must instantiate the redactor.
- **Permissions:** HELD. `PermissionPolicy` defaults to `{SAFE, READ}` (`lib/dataclasses/security.py`). The executor checks permission, then runs `validate_call`, then `execute`; this affects EC-138 (R-14).
- **Lint claims:** HELD.
  - C008's canonical module is `validation.py`, and C002's `_GENERIC_IDENTITIES` includes `value`. The C012 regexes and exempt fields match.
  - S012's `REQUEST_METHODS`, timeout keywords and `client.py` exemption match.
  - S054 covers the Bandit S105–S107 subset.
  - A006 flags concrete-module cycles and lower-to-orchestration imports, and `vidbyte.tools` and `vidbyte.harnesses` are both orchestration prefixes, so "A006 allows harnesses → tools.mcp" is correct.
- **C002 / C006 for the transport:** NOT IN THE SPEC. `isinstance(timeout_seconds, bool)` already exists at `vidbyte/workflows/validation.py:172`, and C006 judges `__init__` guards (R-10).
- **REPO_MAP anchors** `:147`, `:151`, `:195`, `:199` and `:335`: HELD. No README in the S020 scope is touched.
- **§11 commands and the §12.3 / §8.4 counts:** HELD. The commands match code-map. §12.3 has 67 rows (56 CREATE, 11 MODIFY), and the §8.4 file split adds up to 56.
- **opencode 1.18.31 facts** (OpenAPI research): HELD, with some gaps.
  - Held: `prompt_async` answers 204 and its body accepts an optional `messageID`. `abort` returns a boolean. `serve` defaults to `--hostname 127.0.0.1` and `--port 0`. `/session/status` is a map of `idle`, `busy` or `retry`. The message list takes `limit` and `before`.
  - Not used by the spec (R-5, R-6, R-13): the `retry` details, `PermissionRequest.sessionID`, `/session/{id}/children` and the `GET /session` `limit`.
- **Grok flags:** HELD, with one gap. `-m`, `--reasoning-effort` and `--always-approve` exist on 1.0.13. `--leader` and `--no-leader` also exist there, and the spec omits `--no-leader` (R-7).
- **MSP 1.0.1:** PARTLY HELD.
  - Held: `ApprovalMode` is closed and contains `denyUnmatched`, and `turn/start` and `turn/steer` require `commandId`.
  - Failed: "Each `turn/*` command carries `commandId` (UUID4)". `commandId` is also required on `session/start`, `resume`, `fork`, `approval/decide` and `userInput/cancel`, and it is documented as UUIDv7. `session/fork` takes `cutPoint.lastTurnId`, not `lastTurnId` (R-1).
- **request.md Q-8 default:** NOT FOLLOWED. It was downgraded to optional Q-16 (R-4), and NG-15 cites the wrong row (EC-9 instead of EC-10).
- **§12.5 README coverage:** FAILED. `vidbyte/tools/README.md` Key Modules, lines 89 and 91, is not updated (R-11).
- **The `bash.py:195-234` precedent for a bounded stop:** HELD. It is cited in R-3 as the template.
