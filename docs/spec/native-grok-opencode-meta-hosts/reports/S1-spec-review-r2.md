# S1 Spec Review, round 2 (focused): native-grok-opencode-meta-hosts

- **Spec reviewed:** `docs/spec/native-grok-opencode-meta-hosts/spec.md` r2 (HEAD `c4219632`, base `aa8c380c`).
- **Scope:** the r1→r2 changes and what depends on them: §8 (D-2, D-3, D-11, D-13, D-23, the §8.4 budget), §8.5 (transport close and tree stop, `ProcessStopper`, MSP members, UUIDv7, the 12 inbound parsers, the opencode watcher, `--no-leader`), §9, §10, §12 (row 68, counts), EC-154 to EC-156, AC-20, INV-18 and §16.
- **Vendor evidence:** read as data from the research folder (MSP 1.0.1 schema, opencode 1.18.31 OpenAPI) using `python -I` scripts in `scratchpad/scripts2/`. No vendor CLI was run.

## VERDICT

**SOUND WITH FIXES.** r2 resolves most of round 1. Three gaps remain:
- MSP `initialize` still leaves out a member the schema requires.
- The Muse driver derives its turn id and has no source for the turn's text.
- The new stop, reap and reply-selection rules each have a gap that leaves a process alive, interrupts a healthy turn, or returns the wrong text.

Every fix is local: a member, a record, or a sentence of rule. None needs structural rework.

## WHAT THE SPEC GETS RIGHT

- **The MSP command members now match the 1.0.1 schema.** All eight commands carry every required member:
  - `session/start`, `session/resume` and `session/fork` (with `cutPoint`);
  - `turn/start`, `turn/steer` (`expectedTurnId`) and `turn/interrupt`;
  - `approval/decide`, with `requirementId` as the `{approvalId, sourceIndex}` object;
  - `userInput/cancel`.

  Every `commandId` is minted by the client, as the schema requires.
- **The opencode work is grounded in the 1.18.31 OpenAPI.** This covers the child-session tree (EC-154), the `retry` limit (EC-155), the snapshot taken before `prompt_async`, and the route list (`/session/{id}/children`, `/permission/{requestID}/reply`, `/question/{requestID}/reject`). D-11 no longer leaves a subagent's permission request hanging.
- **The transport extension is lint-clean by construction, and INV-18 holds.**
  - New values go through `RecordFieldValidator` and are re-raised as `McpProtocolError(invalid_call)`, so they add no C002, C006 or S016 hits.
  - The default `close()` path is untouched.
  - The dispatch fix matches the existing `test_notification_does_not_complete_waiter`.
- **The bookkeeping is consistent.**
  - §12.3 has 68 rows (56 CREATE + 12 MODIFY), matching §8.4.
  - There are 64 records, of which 12 are inbound: 4 Grok, 4 opencode and 4 Muse, each with its named `parse_*`.
  - Row 68 targets the right lines (`vidbyte/tools/README.md:89` and `:91`).
  - `NativeHostError` is appended after the last class in `base.py` (`SourceSecurityError`, line 502).
  - AC-20's import order is cycle-free at import time.

## FINDINGS

### R-16 [Blocker] [L3/L5] §8.5 MSP calls, §9.3: `initialize` omits the required `clientInfo.version`

**Evidence**
- spec.md:1207 specifies "`initialize` (`clientInfo.name = "vidbyte_sdk"`)", and §9.3 (spec.md:1567) defines only `MUSE_CLIENT_NAME`.
- MSP 1.0.1 `ClientInfo` has `"required": ["name", "version"]`, and `InitializeParams` requires `clientInfo`.
- §8.5 itself promises "each with every member the MSP 1.0.1 schema marks required".
- The author's live probe (`scratchpad/scripts2/s1_msp_probe.py:28`) sent `{"name": "vidbyte_s1_probe", "version": "0"}`, so the version-less form was never exercised.
- Repository precedent: `vidbyte/tools/mcp/client.py:46` sends `{"name": "vidbyte-sdk", "version": "0.2.1"}`, and `vidbyte/__init__.py:39` has `__version__ = "0.2.1"`.

**Failure**
- An implementer who follows the spec literally sends `clientInfo` without a version.
- If Muse validates params as its schema says, every Muse function fails at the handshake. That covers readiness, models, sessions and turns, reported as `muse.protocol_mismatch` or `server_unreachable`.
- Fake MSP peers written from the spec accept the frame, so no test catches it.

**Smallest fix**
- Specify `clientInfo: {name: MUSE_CLIENT_NAME, version: <SDK version>}` in §8.5.
- Add `MUSE_CLIENT_VERSION` to §9.3, or name `vidbyte.__version__` as the source.
- Add one fake-peer assertion that `initialize` carries both members.

### R-17 [Major] [L3/L5] §8.5 `turn/start`, EC-109: the MSP turn id is derived from `commandId` instead of taken from the ack

**Evidence**
- spec.md:1211 says "A fresh turn's MSP `turnId` equals its `commandId`, and the driver keeps it for steer and interrupt."
- MSP `TurnStartResult.turnId` is required, and its schema text says: "The turn that will carry (or absorbed) this input. Authoritative: always take it from the ack rather than deriving it."
- `TurnStartDisposition` is an open enum: `started`, `queued`, `steered`.
- EC-109 (spec.md:666) accepts `queued` and `steered`. The schema's `Item.turnId` equals `commandId` only "for fresh turns".
- No inbound record or parser exists for the `turn/start` result. The §12.5 checklist (spec.md:1921) says every inbound frame becomes a §9.1 inbound record.

**Failure**
- When the disposition is `steered` (or any future value), the input lands in an existing turn whose id is not the `commandId`.
- The driver then waits for a `turn/completed` that never names its id, until `max_turn_seconds`.
- After that, `turn/interrupt` and `turn/steer(expectedTurnId)` send the wrong id. That is a -32xxx error or a no-op on the real turn, which keeps running.

**Smallest fix**
- Add an inbound record `MuseTurnStartAck{command_id, turn_id, disposition: str}` with `MuseWire.parse_turn_start_result(result)`.
- The driver keeps `ack.turn_id` and records `disposition` (this is where EC-109's "with the disposition recorded" lands).
- Replace the sentence at spec.md:1211.
- Records go from 64 to 65 (§8.4, row 10). There is no new file.

### R-18 [Major] [L3/L4] §8.5 `MuseTurnDriver`, §9.1: a Muse turn's reply text has no wire source

**Evidence**
- `NativeTurnResult.text` (spec.md:1337) is returned by `wait_muse_turn`. The only Muse turn inbound record is `MuseTurnCompleted` (spec.md:1402), which has no text field.
- MSP `TurnCompletedParams` has no text member either: its members are `durationMs`, `error`, `reason`, `sessionId`, `sourceRange`, `terminal`, `timeToFirstTokenMs`, `turnId`, `usage` and `viewCursor`.
- The reply exists only on items. `ItemCompletedParams.item` is "the authoritative final object". `Item.text` for kind `agentMessage` is "the accumulated reply", and `Item.turnId` names the owning turn.
- `session/start` and `session/resume` "auto-subscribe this connection", so these notifications reach the turn peer.
- §8.5 (spec.md:1204) names no parser for `item/completed`. R-2's fix therefore stops short of the frame that carries the result.

**Failure**
- Implementers either return `text=""` for every Muse turn, which hollows out FR and AC rows that show the reply, or read raw `Mapping`s, which is the D-13 and field-guide violation that R-2 was raised to prevent.

**Smallest fix**
- Add an inbound `MuseItemCompleted{session_id, item_id, kind: str, turn_id: opt str, text: opt str}` with `MuseWire.parse_item_completed(params)`.
- The driver appends `text` for each `agentMessage` item whose `turn_id` is the turn's id (R-17), capped at `NATIVE_RESULT_TEXT_MAX_CHARS` with `text_truncated`.
- A `view/gap` for the session during the turn sets `text_truncated=True`.
- Records go to 66 with R-17. There is no new file.

### R-19 [Major] [L3/L5] §8.5 watcher step 3, EC-85: "the" assistant reply is ambiguous for multi-step opencode turns

**Evidence**
- spec.md:1170 says "The turn's reply is the assistant message whose `parentID` is that user message's id". EC-85 (spec.md:607) is written the same way.
- opencode's prompt loop writes one assistant message per model step. Every step's message carries the same `parentID`, and all but the last finish with `tool-calls`. This comes from the vendor's source behaviour; it was not re-probed this round.
- The OpenAPI shape supports this: `AssistantMessage` requires `parentID` and has its own `finish`, `time.completed` (optional), `tokens`, `cost` and `error` per message.
- `OpencodeMessage` (spec.md:1377) holds one message's text and usage. `OPENCODE_WATCH_MESSAGE_LIMIT` is 50 (spec.md:1555).

**Failure**
- A turn that calls tools has two or more replies. Taking the first one returns the preamble text ("I'll look at the files…") and undercounts usage.
- Taking "any" reply can also let an intermediate step's `time.completed` satisfy completion, or its `error` decide EC-85.
- In a long tool loop, early steps leave the newest-50 window. Usage summed from one poll therefore drops them.

**Smallest fix**
- Define the turn's replies as all assistant messages with that `parentID`, accumulated by `message_id` across polls.
- Text, `finish` and `error` come from the newest reply (highest id).
- `usage` is the sum over all replies.
- Completion is the idle confirmations plus the newest reply having `time.completed`.
- Update EC-85 and row 38 to match.

### R-20 [Major] [L5] §8.5 `ProcessStopper.stop_tree` and transport `close()`: survivors in the peer's group when the leader has already exited

**Evidence**
- spec.md:1051 says "killpg is used only when the process leads its own group (os.getpgid(pid) == pid), and otherwise only the process itself is signalled".
- spec.md:993 says that close stops the tree only "if the child is still running".
- The repository precedent this spec cites says the opposite. `vidbyte/tools/builtins/bash.py:202-212` says: "On POSIX, kill the whole group even when bash itself has already exited, since a background child can still hold the output", and calls `os.killpg(process.pid, SIGKILL)` under `suppress(ProcessLookupError, PermissionError)`.
- asyncio's child watcher reaps the leader as soon as it exits. After that, `os.getpgid(pid)` raises `ProcessLookupError`, and `returncode` is set.
- spec.md:994 notes that on Python 3.12+ `wait()` also waits for the pipes. So the grace wait can time out with the leader already dead while a grandchild holds the pipe.

**Failure**
- Take a Grok or Muse peer that exits on stdin EOF, or is killed directly, while a tool's shell, `sleep` or dev server is still running in its group.
- The leader is gone, so the gate falls back to signalling only the dead leader, or close skips `stop_tree` because the child is "not running".
- The grandchild survives, keeps editing the workspace, and holds the pipe. That breaks NFR-2 and INV-4, which R-4 and D-23 were meant to guarantee.
- The kill is safe without the gate. With `start_new_session=True` the group id equals the leader's pid, and POSIX does not reuse a pid while its group still has members. So `killpg` cannot reach a stranger, and it never reaches the SDK's own group.

**Smallest fix**
- On the `stop_process_tree` path, close always calls `stop_tree`, whatever `returncode` says.
- On POSIX, `stop_tree` always runs `killpg(process.pid, SIGTERM)`, then after the grace `killpg(…, SIGKILL)`, both under `suppress(ProcessLookupError, PermissionError)`, for a process started with `start_new_session=True`. Keep the `getpgid` gate only for processes the helper did not start.
- Add to EC-10 and A-9 the Windows residual: `taskkill /T` cannot follow parent ids once the peer has exited, so a Windows grandchild of an already-exited peer may survive.
- Optional **Q-19 [scope-adding]** (default: not built): put Windows peers in a Job Object with kill-on-close.

### R-21 [Major] [L5/L7] D-23 and §13: how the in-distro reap reaches the distro is unverified, its environment can carry the mark, and "needs a real distro" is wrong

**Evidence**
- D-23 (spec.md:884) and §13 (spec.md:1989) pass the whole multi-line `MUSE_REAP_SCRIPT` as one argv element: `wsl.exe -d <distro> -e sh -c <MUSE_REAP_SCRIPT> vidbyte_reap <mark>`, with no stdin.
- On Windows, `create_subprocess_exec` flattens the argv with `list2cmdline`, and `wsl.exe` re-splits it with its own parser. No probe checked that a script containing quotes, `$`, backslashes and newlines arrives intact.
- In contrast, piping bytes through `wsl.exe` stdin was exercised by the round-1 MSP probes.
- spec.md:1573 says the script "never kills itself, because its own environment lacks the mark". That holds only if the reap's `CliRunner` invocation is not built with the Muse peer's environment overlay (spec.md:1510-1511 puts `VIDBYTE_PEER_MARK` and `WSLENV=…VIDBYTE_PEER_MARK/u` there). The spec does not state this.
- §13 says "Running the reap script itself needs a real distro". But CI runs on `ubuntu-latest` (`.github/workflows/ci.yml:17,44`), where `sh` and `/proc` exist.

**Failure**
- A mangled script fails silently, because the reap "always exits 0" and failures are not raised (EC-10). Q-8's guarantee then quietly disappears on every WSL turn.
- Reusing the peer environment makes the reap kill itself partway through its scan.
- The script's `/proc` logic ships untested.

**Smallest fix**
1. Run `wsl.exe -d <distro> -e sh -s -- <mark>` through `CliRunner` with `stdin_text=MUSE_REAP_SCRIPT`. The script must be LF-only.
2. State that the reap runs with the caller's environment, never the peer overlay.
3. Check the mark against `^[0-9a-f]{32}$` before building the argv.
4. Pin the matching rules:
   - an exact NUL-delimited entry: `tr '\0' '\n' < /proc/$p/environ | grep -qx "VIDBYTE_PEER_MARK=$1"`;
   - parent ids from `/proc/<pid>/status` `PPid:`, not `stat` field 4, which breaks on a `comm` containing spaces or `)`;
   - `kill -KILL`.
5. Replace the §13 sentence. On Linux CI, the test runs the script with `sh -s -- <mark>` against a spawned marked process with an unmarked child, and asserts that both die and that an unmarked process survives.

### R-22 [Major] [L5] D-11 and EC-156: re-deciding on `approval/updated` turns a benign race into an interrupted turn

**Evidence**
- D-11 (spec.md:872) and spec.md:249 say the host answers `approval/updated` "for an approval that is still pending" with a fresh `approval/decide`.
- EC-156 (spec.md:707) says any JSON-RPC error answer to a decide interrupts the turn with source `POLICY`.
- MSP `ApprovalUpdatedParams` carries a free-form `change.kind`, so updates fire for reasons other than a new stage, such as persistence status or a reparse.
- The MSP error table includes -32051 `approvalAlreadyResolved` and -32053 `approvalRequirementStale`. The schema describes -32053 as "the multi-stage race guard".
- `ApprovalDecideResult` is an admission ack. The schema says "the authoritative outcome is `approval/resolved` / `approval/updated`".

**Failure**
- Suppose an `approval/updated` for the same `currentRequirementId` arrives while the host's decide is in flight or just acknowledged.
- The second decide gets -32051 or -32053, EC-156 fires, and a healthy turn ends `INTERRUPTED/POLICY` with a spurious `CANCELLED` decision.

**Smallest fix**
- Decide at most once per `(approval_id, requirement_approval_id, requirement_source_index)`, and ignore an update that repeats a requirement already decided.
- Treat -32051 and -32053 answers as benign: record the decision with outcome `CANCELLED` and do not interrupt.
- Keep EC-156 for -32052, other codes, and timeouts.

### R-23 [Minor] [L5/L7] NFR-2, EC-8 and spec.md:216: the stop-time bounds ignore the second grace and `shutdown_timeout`

**Evidence**
- NFR-2 (spec.md:828) promises "within `NATIVE_STOP_GRACE_SECONDS` + 2 s" (7 s).
- `NativePeer` sets `exit_grace_seconds=NATIVE_STOP_GRACE_SECONDS` but not `shutdown_timeout` (spec.md:1104), so `shutdown_timeout` stays at `_DEFAULT_SHUTDOWN_TIMEOUT = 5.0`.
- The stop sequence is: `stop_tree(grace_seconds=shutdown_timeout)` (spec.md:993), then a post-kill wait bounded by `shutdown_timeout`.
- EC-8 (spec.md:401) waits up to the grace for live turns before it closes peers.
- Worst case: 5 s (turns) + 5 s (exit grace) + 5 s (TERM grace) + 5 s (post-kill wait) = 20 s, before the 10 s reap.

**Failure**
- A test that asserts NFR-2's bound against a fake peer that ignores stdin EOF and SIGTERM fails against a correct implementation. The implementer cannot satisfy both texts.

**Smallest fix**
- Set `NativePeer`'s `shutdown_timeout` to a named constant, for example `NATIVE_KILL_WAIT_SECONDS = 1.0`.
- Restate NFR-2, EC-8 and spec.md:216 as the sum: turn grace, plus exit grace, plus TERM grace, plus post-kill wait, plus 2 s, plus `MUSE_REAP_TIMEOUT_SECONDS` for WSL Muse.

### R-24 [Minor] [L7/L8] `MuseWire.new_command_id`: the layout is unspecified, "time-ordered" invites a flaky test, and the construction trips A007

**Evidence**
- spec.md:1204 builds the id "from `time.time_ns()` and `secrets.token_bytes`". §13 (spec.md:2002) says it is "time-ordered".
- A007 (`lint/rules/a007_operational_constants.py:23-39, 96-106`) splits nearby names on `_` and `.`. The token `token` from `secrets.token_bytes` therefore flags every non-uppercase numeric literal in the same enclosing expressions: the byte count, shifts and masks.
- RFC 9562 orders ids only by the 48-bit millisecond prefix. Random `rand_a` and `rand_b` give no order within one millisecond.

**Failure**
- The A007 count rises, and the gate fails.
- A test that asserts "consecutive ids sort ascending" fails intermittently.

**Smallest fix**
- Specify the layout: 48-bit `unix_ts_ms`, version `7`, 12-bit `rand_a`, variant `0b10`, 62-bit `rand_b`.
- Draw the random bits from `secrets.randbits(74)`, or name every width and mask as an UPPERCASE module constant.
- Change §13 to "shape only; the 48-bit timestamp prefix is non-decreasing across calls at least 1 ms apart".

### R-25 [Minor] [L9] §5 Grok sequence diagram: still the r1 argv

**Evidence**
- spec.md:168 shows `start argv [grok, agent, -m, model, stdio]`.
- Every other site uses `agent --no-leader --model=<id> … stdio`: EC-25, D-2, spec.md:1131, row 33 and §13:1983. §16 marks R-7 (`--no-leader`) and R-14 (`--name=value` everywhere) as applied.

**Failure**
- An implementer or test author reading the overview builds the r1 argv. That loses `--no-leader`, which is the R-7 leader hijack, and uses the `-m` form that T-2 forbids.

**Smallest fix**
- Change the diagram line to `start argv [grok, agent, --no-leader, --model=<model>, stdio]`.

### R-26 [Minor] [L6] EC-154: on an attached server, the tree refresh repeats on every poll

**Evidence**
- EC-154 (spec.md:612) refreshes the breadth-first `children` walk "whenever a pending request names a session not yet in the tree".
- It leaves alone requests from sessions outside the tree, because they "may belong to the user".
- It counts a failed `children` call as a failed poll (EC-87).

**Failure**
- While the user's own TUI has a permission prompt open on an attached server, every poll of every live turn re-walks its whole tree. That is O(tree) HTTP calls each `OPENCODE_POLL_INTERVAL_SECONDS`.
- Any one of those unrelated walks can fail and count toward EC-87, ending the turn because of someone else's request.

**Smallest fix**
- Remember, per turn, the session ids already found to be outside the tree. A session's parent is fixed when the session is created, so an outside id never becomes a descendant.
- Re-walk only for an id not seen before.

## VERIFIED CLAIMS

### Round-1 dispositions (§16): what r2 actually resolved

| R | r2 claims | Actually | Note |
|---|---|---|---|
| R-1 | Accepted | **Partly** | The members of the eight commands match the schema. `initialize` still lacks `clientInfo.version` (R-16), and the turn id is derived rather than taken from the ack (R-17). |
| R-2 | Accepted | **Partly** | There are 12 inbound records with named parsers. The `turn/start` ack and `item/completed` have none (R-17, R-18), which contradicts the spec.md:1921 checklist. |
| R-3 | Accepted | Resolved, on the kill path | Every post-kill wait is bounded and the pipes are closed. The no-kill path (leader exited, pipe held) is R-20. |
| R-4 | Accepted | **Partly** | D-23 restores Q-8's order. The `getpgid` gate and "still running" skip (R-20), and the reap's delivery and testing (R-21), leave gaps. |
| R-5 | Accepted | Resolved | EC-154 and the `children` route are present in the OpenAPI. The churn is R-26. |
| R-6 | Accepted | **Partly** | The snapshot, `prompt_not_seen` and the `retry` limit are right. The reply is singular (R-19). |
| R-7 | Accepted | **Partly** | Every argv carries `--no-leader` except the §5 diagram (R-25). |
| R-8 | Accepted | Resolved | Stdin rules for the transport, `CliRunner` and `ManagedProcess` are stated. |
| R-9 | Accepted | Resolved | D-3 records the edge, and AC-20 checks fresh-interpreter imports. `vidbyte/harnesses/__init__.py`, `client.py` and `serialization.py` import only harnesses, `vidbyte.sessions.*` and `lib.util.credential_keys`, so there is no import-time cycle. |
| R-10 | Accepted | Resolved | Checks use `RecordFieldValidator`, the re-raise is `McpProtocolError(invalid_call)`, and `exit_grace_seconds: float \| None`. The separate A007 trap is R-24. |
| R-11 | Accepted | Resolved | Row 68 extends `vidbyte/tools/README.md:89` (`builtins/`) and `:91` (`toolsets/`). The README is 6,343 characters, far under A009. |
| R-12 | Accepted | Resolved | `ToolsFormatter._error_parts` reads `hint`, `retryable` and `detail`. Its text envelope also prints `Hint:` (formatter.py:512-513), so the next step appears twice in text mode. That format is settled user scope, so this is noted only as a cost, not a finding. |
| R-13 | Accepted | Resolved | The server `limit` is sent. |
| R-14 | Accepted | **Partly** | EC-138 is scoped correctly. The `-m model` form survives in the §5 diagram (R-25). |
| R-15 | Accepted | Resolved | `NativeHostError` is appended after `SourceSecurityError` (base.py:502), and base.py imports only `collections.abc` and `typing`. |

### Other checks that held

**MSP 1.0.1 schema**
- Required members:

  | Params | Required |
  |---|---|
  | `TurnStartParams` | `commandId`, `input`, `sessionId` |
  | `TurnSteerParams` | adds `expectedTurnId` |
  | `TurnInterruptParams` | `commandId`, `sessionId` (`turnId` optional, sent anyway) |
  | `UserInputCancelParams` | adds `userInputId` |
  | `SessionStartParams` | `commandId` |
  | `SessionResumeParams` and `SessionForkParams` | `commandId`, `sessionId` |
  | `ViewPageParams` | `limit`, `sessionId` |
  | `SessionReadParams` | `sessionId` |
  | `ApprovalDecideParams` | `approvalId`, `choiceId`, `commandId`, `requirementId`, `sessionId` |
  | `InitializeParams` | `clientInfo` |
  | `ClientInfo` | `name`, `version` |

- `IfBusy` defaults to `queue` (closed enum `queue`, `steer`, `replace`). `TurnStartDisposition` is open.
- `ApprovalDecideResult.terminal: false` means "the approval stays pending and an updated request follows". That matches EC-156's carve-out.
- Approval error codes -32050 to -32053 exist: not found, already resolved, choice invalid, requirement stale.
- `session/start` and `session/resume` auto-subscribe the connection; `session/read` never subscribes.

**opencode 1.18.31 OpenAPI**
- `AssistantMessage` requires `parentID` (pattern `^msg`) and `time.created`. `time.completed`, `finish` and `error` are optional, and there is one set per message.

**Transport today**
- `_DEFAULT_SHUTDOWN_TIMEOUT = 5.0`.
- `close()` ends with an unbounded `await process.wait()`.
- A frame without an `id` is dropped.
- INV-18's default path matches the spec text.

**Lint, CI and README coverage**
- A007's `OPERATIONAL_TOKENS` includes `token`, `byte`, `limit`, `timeout` and `status`; names split on `_` and `.`. Uppercase assignments are exempt.
- CI runs on `ubuntu-latest` (Python 3.11 and 3.12).
- Folder READMEs in touched folders (`vidbyte/lib`, `vidbyte/tools`, `vidbyte/tools/mcp`, `vidbyte/harnesses`) each have a MODIFY row: 21, 68, 23 and 47. None has a `## Notes for agents` section to honour.
