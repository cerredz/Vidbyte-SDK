# S1 spec author report: native-grok-opencode-meta-hosts

- **Stage:** S1, spec author.
- **Output:** `docs/spec/native-grok-opencode-meta-hosts/spec.md`, revision 1, 2009 lines, committed as `45bd8764` on `feat/native-grok-opencode-meta-hosts`. The base is `aa8c380c`, and the previous commit on the branch is `e4c3737b`.
- **What I did not do:**
  - write production code or tests;
  - edit `lint/`, `pyproject.toml` or the field guide;
  - read the codex-host or claude-host worktrees;
  - read any credential file;
  - send any prompt;
  - install, push or open a PR.
- **Untrusted vendor data:** read only as data, with `python -I`, from scripts in the scratchpad `scripts2/` folder. Nothing in it was executed and no instruction in it was followed.

## What I read

**Pipeline inputs:**
- `request.md` (all 802 lines).
- `context/code-map.md` §1–§4.
- `reports/S0-scout.md`.
- The spec template.
- `vidbyte-gates.md` (via the scout's corrections).

**Rules:**
- AGENTS.md and CLAUDE.md.
- The REPO_MAP anchors for harnesses (:147/:151), lib/models (:195) and lib/providers (:199).
- READMEs: `vidbyte/lib/README.md` (Key Modules :35-44), `vidbyte/tools/mcp/README.md` and `vidbyte/harnesses/README.md`.

**Code (cited ranges):**
- `vidbyte/tools/mcp/transport.py`, in full:
  - `start` builds the child environment from an allowlist plus overlay;
  - `request` uses one fixed `request_timeout`;
  - `close` closes stdin and then terminates at once;
  - dispatch drops frames that have no `id`.
- `vidbyte/lib/errors/base.py`, the `CodexAgentError` pattern at :129-153.
- `vidbyte/lib/enums/failure.py`, the insertion spot at :144 and `from_exception` at :166-172.
- `vidbyte/lib/configs/__init__.py`.
- `vidbyte/tools/toolsets/coding.py:1-14,47-60`.
- `vidbyte/lib/dataclasses/tools.py`: `ToolParameter`, `ToolCall`, `ToolResult`.
- `vidbyte/lib/http/{transport,parser}.py`.
- `vidbyte/harnesses/serialization.py` (the redactor).
- `vidbyte/tools/builtins/bash.py:195-234`.
- `vidbyte/agents/codex/transport.py:54-119`.

**Lint:**
- The rule mapping S006 = RUF006 and S052 ⊇ ASYNC110.
- The S054 Bandit subset S105-S107.
- A baseline run, saved as scratchpad `s1_lint_baseline.txt`. It ended `SDK-LINT: PASS` and recorded the per-rule counts that §11 cites.

**Vendors, no-prompt probes only:**
- **Grok.** `grok --version` printed `grok 1.0.52 (0920c8169e27) [stable]`. Also observed:
  - `grok models` signed out;
  - the ACP `initialize` result and its `_meta.modelState`;
  - the `session/resume` answer for a missing id, -32603 with `FS_NOT_FOUND`.
- **opencode 1.18.31.**
  - The `opencode serve` listening line, and 401 with an empty body.
  - The OpenAPI document: every route accepts a `directory` query; message list has `limit` and `before`; FileDiff fields are `{path,status,additions,deletions,patch}`; `/session/status` is a map.
  - Responses: abort returns `200 true`, the diff route returns `200 []` for a missing session, and malformed ids return 500.
- **Muse.**
  - `muse --version` through WSL.
  - The MSP 1.0.1 enums: `ReasoningEffort`, `TurnStartDisposition`, `CommandStatus`, `SessionStatus`, `ViewPageDirection`.
  - `turn/start` and `turn/steer` require `commandId`.
  - A missing session returns -32020, and `model/list` is empty with source `bundledCatalog`.
  - The `wsl.exe` distro-not-found text.

## Approaches weighed

1. **CLI-only wrappers** (`grok -p`, `opencode run`, `muse exec --json`) were rejected (§8.3). They cannot return a handle at once (FR-1 to FR-3, INV-11), and a blocking one-shot run inside a Codex dynamic tool is cut at 300 s. They also leave the wait, interrupt and steer functions with nothing to act on, and cannot answer approvals (FR-12).
2. **Per-host JSON-RPC clients** (request Q-3, option 3) were rejected because they copy framing that `McpStdioTransport` already owns (principle 5). Chosen instead: an additive extension of `McpStdioTransport` (D-3):
   - `on_message`, `send_request`, `notify`, `respond`;
   - `request(timeout_seconds=)`;
   - `exit_grace_seconds`;
   - a dispatch fix for frames without `id`.

   `send_request` gives the two-phase spawn that INV-11 needs.
3. **The vendor SDKs** (`agent-client-protocol`, `muse-code-sdk`) were rejected by D-20 and NG-5. Q-2 defaults to no new dependency, and `pyproject.toml` is reserved.
4. **Peer lifetime:**
   - **Chosen:** one peer per live turn for Grok and Muse, and one owned `opencode serve` per host (D-2). Grok fixes the model and effort per process.
   - **Rejected:** a single long-lived Grok peer.
5. **Error shape:**
   - **Chosen:** one `NativeHostError(AgentExecutionError)` with a `FailureCode`, `operation`, `next_step`, `error_type` and a scrubbed `context` (D-6, D-7). It reuses `FailureCode.from_exception` and the repo's diagnostic-fields pattern. The 53 `<host>.<problem>` codes are appended after `RULE_EVALUATION_FAILED`.
   - **Rejected:** a separate exception class per host.
6. **Shared plumbing placement:**
   - **Chosen:** `vidbyte.harnesses.native.hostkit` (D-22). The redactor lives in `vidbyte.harnesses.serialization`, so placing hostkit in `lib/` would import upward (A006).
   - **In `lib/process`:** only the layer-neutral process helpers (D-4).
7. **opencode backend wiring:**
   - **Chosen:** built-in provider env keys (`ZHIPU_API_KEY`, `DEEPSEEK_API_KEY`) set on the owned server (D-16).
   - **Runner-up:** a custom provider through `OPENCODE_CONFIG_CONTENT`, verified to work. It is kept as the flip if A-4 is wrong.

## Disagreements with the request or scout (with evidence)

1. **opencode over `httpx`** (request.md:124,153,731). I agree with the scout. S011 has a baseline of 0 and bans `httpx` outside `vidbyte/lib/http/transport.py` and `vidbyte/tools/mcp/transport.py`. The spec routes through `HttpTransport` with `urlencode` query strings and status polling instead of SSE (D-5).
2. **"Copy `builtins/sessions/` with a per-host `_base.py`"** (request.md:92,261). The spec uses one shared `vidbyte/tools/builtins/native_host_tool.py`, because four copies would break principle 5. The sessions folder also carries A001, S017 (`_base.py:90`, `batch_fork.py:56`) and S062 debt, and its `_caught` helper is synchronous.
3. **"MuseHost talks MSP through `muse-code-sdk`"** (request.md:598) contradicts request Q-2's no-new-dependency default. Resolved as raw MSP (D-20).
4. **Q-8, "kill the process tree, then kill inside the distro".** For long-lived peers the spec stops by protocol interrupt, then stdin EOF, then a grace period, then a direct kill (EC-10). An in-distro `kill` could hit the user's other Muse sessions, so it is optional Q-16. A-9 verified that idle kills leave no orphan.
5. **Catalog signatures:**
   - `wait_opencode_turn(id, timeout)` became `timeout_seconds`, because S045 bans an async parameter named `timeout`.
   - `continue_grok_session(id_or_title, …)` takes an id only (NG-10).
   - `list_grok_sessions(cwd)` uses the host workspace (D-1).
   - `check_backend_ready`'s "one-token test call" was dropped, so readiness never spends money (D-17).
6. **Grok version.** request.md records 1.0.13, but 1.0.52 is installed. The floor stays 1.0.13, and every "verified" Grok fact is tagged as coming from 1.0.52 (A-2).
7. **opencode default permissions.** The request assumes the host answers every approval by policy. With the user's default opencode config, `edit` and `bash` are already `allow`, so no permission request reaches the watcher. This is documented as a T-2 residual, with optional Q-17 for tool-spawned `ask` rules.
8. **The request's "every code has a test" requirement.** The spec lists no tests, per the template. AC-2 instead makes every §6.3 row testable through the §13 fakes, with a required token per row. The test author owns coverage.
9. **Gates reference.** I followed the scout's corrections:
   - the pass line is `SDK-LINT: PASS`;
   - Semgrep is not in `run_ci.py`;
   - `# noqa` is forbidden;
   - worktree runs need `PYTHONPATH`.

## Assumptions I am least sure of

| ID | Why it is uncertain | Exposure if wrong |
|---|---|---|
| A-5 | A headless `grok --single --permission-mode default` refuses tools that need approval. This cannot be verified without a prompt. | One-shot runs could act unapproved; switch the default to `DONT_ASK`. |
| A-4 | opencode built-in providers read `ZHIPU_API_KEY` / `DEEPSEEK_API_KEY` when `auth.json` lacks a key; precedence when both exist is unverified. | `build_opencode_backend_provider` flips to the `OPENCODE_CONFIG_CONTENT` runner-up. |
| A-2 | 1.0.52 facts (`_meta.modelState`, `FS_NOT_FOUND`, the signed-out line, `--name=value` parsing) also hold on 1.0.13, which is no longer installed. | EC-22 raises `grok.protocol_mismatch` on older builds; raise the floor. |
| A-9 | Killing `wsl.exe` leaves no in-distro `muse` process; verified idle only. | Mid-turn orphans; Q-16 becomes needed. |
| A-13 | Claude Code model names `glm-5.3[1m]`, `glm-5.3-flash[1m]`, `deepseek-flash[1m]`, `deepseek-v4-pro` come from request research, not a live call. | Only `HARNESS_BACKENDS` rows change. |

## Self-check (Stage E)

- `grep -c "^## §"` returns 18. The headings match the template one to one, with no Part D, E or F.
- Every referenced ID is defined, with no gaps:

  | Prefix | Range |
  |---|---|
  | D | 1–22 |
  | A | 1–15 |
  | T | 1–8 |
  | EC | 1–153 |
  | INV | 1–23 |
  | AC | 1–19 |
  | FR | 1–21 |
  | NFR | 1–7 |
  | G | 1–4 |
  | NG | 1–17 |
  | W | 1–14 |
  | Q | 1–18 |

  Q-1 to Q-13 are request.md's questions, resolved in §8.1. Q-14 to Q-18 are new, and none of them blocks.
- The §4 names appear in §8.5 and in §12.3: `GrokHost`, `GrokHostSettings`, `GrokTurnRequest`, `NativeHostError`, `spawn_grok_session`, `wait_grok_turn`, `build_claude_backend_env`, `failure_code` and `next_step`.
- §12.3 has 67 rows (56 CREATE, 11 MODIFY), all with 8 cells and a governing standard.
- Every `NATIVE_`, `GROK_`, `OPENCODE_` and `MUSE_` constant is in §9.3, except three names that are deliberately absent:
  - `GROK_NOT_INSTALLED`, an example `FailureCode` member name;
  - `HARNESS_BACKENDS`, a config in §9.1 and §12.3 row 14;
  - `OPENCODE_CONFIG_CONTENT`, a vendor environment variable.
- No test cases. File paths outside §11–§13 appear only as non-goal or invariant targets and as §8.2 `path:symbol` source citations, which the template asks for.

## Addendum: revision r2 (S1 review round 1, commit `c4219632`)

**Triage.** All 15 findings were accepted: 2 Blocker, 9 Major and 4 Minor. None was rejected or deferred, and no finding added scope beyond the conversation. Each disposition is recorded in §16.

**New evidence read** (data only, with `python -I` scripts in the scratchpad `scripts2/`):
- **`muse-1.0.1-msp.schema.json`.** `commandId` is required on `session/start`, `resume`, `fork`, every `turn/*`, `approval/decide` and `userInput/cancel`, and it is a UUIDv7. Fork takes `cutPoint {lastTurnId}`. `approval/decide` requires `requirementId = {approvalId, sourceIndex}`. A decide result with `terminal: false` is followed by `approval/updated`. `turnId == commandId` for a fresh turn.
- **`opencode-1.18.31-openapi.json`.**
  - `GET /session` is "sorted by most recently updated" and accepts `limit`.
  - `/session/{id}/children` exists, and `PermissionRequest` and `QuestionRequest` carry `sessionID`.
  - `AssistantMessage.parentID` is required.
  - The `retry` status has `attempt`, `message`, `next` and an optional `action.reason`, which is a free string.
- **`grok-1.0.13-help.txt`.** `grok agent` has `--leader` and `--no-leader`, while top-level `grok` has only `--leader-socket`; this is recorded as A-18.
- **Repo.**
  - `vidbyte/lib/tools/formatter.py:519-532` (`hint`, `retryable`) and `vidbyte/tools/executor.py:61-66` (`validation_error`).
  - `vidbyte/tools/README.md:89,91`, and the `vidbyte/lib/errors/__init__.py` header.
  - The import chain: `agents/__init__.py:64` and `agents/coding.py:34`.
  - `requires-python >= 3.11`, so `uuid.uuid7` is unavailable.

**Main choices in r2:**
- **R-4, request Q-8's default restored as D-23.**
  - An additive transport option, `stop_process_tree`, starts the peer in its own POSIX session. At close it uses `ProcessStopper.stop_tree`, which calls `killpg` only for a group leader.
  - The in-distro reap is scoped by a random per-peer mark (`VIDBYTE_PEER_MARK`, forwarded through `WSLENV`). It kills marked processes and their descendants by parent id, which removes r1's wrong-process objection.
  - The residual risk is recorded in A-9 and T-7.
- **R-2.** The 12 inbound records go in the existing per-host dataclass modules. The budget rose from 52 to 64 records, with no new file.
- **R-9, option (a).** D-3 records the two-way package edge, and the new AC-20 plus a P4 exit check prove the fresh-interpreter imports. Option (b) is now D-3's runner-up.
- **R-10.** `exit_grace_seconds` became `float | None = None`, so the validator's `require_number` (> 0) applies with no zero special case. Its upper bound is the new `NATIVE_STDIO_MAX_WAIT_SECONDS`.
- **R-6.** The turn's message is identified by a snapshot of the newest message id taken before `prompt_async`, plus the assistant `parentID` link. Sending a host-minted `messageID` was rejected, because opencode orders messages by id and a foreign id could break that ordering.

**New assumptions I am least sure of:**
- **A-17.** The `retry` messages carry rate-limit markers; the vocabulary of `action.reason` is unknown.
- **A-9 (reworded).** The reap reaches every process Muse starts mid-turn.
- **A-18.** One-shot `grok --single` runs do not use a leader.

## Addendum: revision r3 (S1 review round 2, final; commit `f1b2fa31`)

**Triage.** All 11 findings were accepted: 1 Blocker (R-16), 6 Major (R-17 to R-22) and 4 Minor (R-23 to R-26). The scope-adding Windows Job Object is optional Q-19, default not built, as the coordinator directed. Nothing is left disputed. Frontmatter: `revision: 3`, `status: approved`, `updated: 2026-10-13`. Every disposition is in §16, including the round-1 rows that round 2 found only partly resolved (R-1, R-2, R-4, R-6, R-7, R-14).

**New evidence read** (data only, with `python -I` scripts in `scripts2/`):
- **MSP 1.0.1 schema.**
  - `ClientInfo` requires `name` and `version`.
  - `TurnStartResult.turnId` is "authoritative", and `TurnSteerResult` has `commandId`, `status` and `turnId`.
  - `ItemCompletedParams.item` carries `kind`, `turnId`, `text` and `truncated`.
  - `ViewGapParams` has `sessionId`, `after` and `next`.
- **Repo.**
  - `vidbyte/__init__.py:39` (`__version__`) and `tools/mcp/client.py:46`.
  - `cli/__init__.py:58` and `mcp_server/server/core.py:79` hard-code `0.2.1`; `scripts/run_ci.py:210` checks only `vidbyte.__version__`.
  - `tools/builtins/bash.py:202-212` (group kill after the leader exits).
- **Formula check.** The UUIDv7 bit layout was checked in a scratch interpreter: version 7, RFC variant, and a timestamp prefix equal to the millisecond clock.

**Main choices in r3:**
- **R-16.** The version comes from `vidbyte.__version__`, read when the params are built and never written as a literal. Four modules already hard-code `0.2.1`, and those copies drift.
- **R-17.** One record, `MuseTurnAck`, covers both the `turn/start` and `turn/steer` results, so the steer result also stops being a raw read.
- **R-18.** `view/gap` gets no record. A turn peer is subscribed to one session, so the driver reacts to the method name alone.
- **R-19.** The idle confirmations count only while the newest reply has `time.completed`; a reply that never completes is bounded by the turn ceiling. This adds `OpencodeMessage.completed_ms`.
- **R-20.** The `getpgid` gate is dropped rather than kept for "other" processes, because no caller passes one, and `killpg` on a non-leader finds no group. The leftover pid-reuse window is stated in T-7.
- **R-21.** No `--` before the mark, so `wsl.exe` cannot treat it as its own separator; the mark is validated hex.
- **R-23.** `NATIVE_KILL_WAIT_SECONDS` = 1.0 bounds both waits of every tree stop. NFR-2 gives the sums: 9 s for a peer, 14 s for `__aexit__`, and 26 s with a WSL reap, including 2 s of slack. Peers now close concurrently in `__aexit__`.

**Budget.** 66 records (14 inbound) and 13 enums; files unchanged at 56 CREATE and 12 MODIFY.

**Self-check re-run.**
- IDs: every reference is defined.
- §12.3: 68 rows with good cell counts.
- No unescaped pipes in table code spans.
- Constants: every new one is in §9.3.
- No blocking Q.

## Addendum: revision r4 (S2 test-author ambiguities; commit `1f97640b`)

**Disposition.** All 14 S2 items were accepted and stated explicitly (§16 rows S2-1 to S2-14). In each one, the tests' reading matched the request, the repo rules and the rest of the spec. No item was routed back, and no test was edited. While settling S2-12, I found S2-15: "tuple fields are converted" conflicted with `require_argv`, which accepts only a `tuple`, and `muse_command` had no check. Both are now stated, matching `test_host_settings_reject_each_bad_field_by_name[command-list]` and the list conversion the Grok and backend record tests expect.

**Transport check (S2-T).** §8.5 already specifies that a frame with a string `method` goes to `on_message`, or is dropped without a callback, and never resolves a pending request. INV-18 names this as the one exception to the unchanged default. In r4, FR-15 names the exception, and §8.5 now says what used to happen on an id collision and that a non-string `method` is dropped. Existing callers are unaffected: `attach.py` and the current transport tests send `method` only in notifications without an `id`.

**Judgement calls.**
- EC-115's custom next step (token `continue_muse_session`) now applies in `interrupt_muse_turn` and `wait_muse_turn`, as the row literally said and as the tests assert.
- The §6.2 Proof cells were inserted by `cfad74f8` as a 7th cell after an empty one. The rows therefore have 7 cells under a 6-column header, and a GFM renderer hides the Proof text. I left this untouched, as instructed.

**Self-check re-run.**
- IDs: every reference is defined.
- §12.3: 68 rows.
- Constants: unchanged.
- Proof and Priority cells: byte-identical to `cfad74f8`.

## Addendum r8

**Scope.** I changed only R-2, R-M2 and R-M3 (§16 S4-1 to S4-3). S4-4 (CI-1) and S4-5 (R-3) record the orchestrator's "no spec change; code fix" rulings. Status stays `reviewed`, and the spec and this addendum are in one commit.

**R-2: the rule chosen (D-19, new EC-157).**
- On win32, Grok never starts through a batch file. At `__aenter__`, Grok's program, whether explicit or found, is looked up through `PATH` and `PATHEXT` the way a launch looks it up, and the host keeps the path it found.
- A name ending in `.cmd` or `.bat` (any letter case, with trailing dots and spaces dropped) is refused.
- If the batch file was found on PATH, the host falls back to `~/.grok/bin/grok.exe`. Otherwise `__aenter__` raises `grok.not_installed` with EC-157's own next step, which names `grok.exe` and keeps the token `GrokHostSettings.grok_command`.
- An explicit batch `grok_command` is refused at `__aenter__`, not in the record, because `("grok",)` becomes `grok.cmd` only through the lookup. EC-11 already maps an explicit launcher that cannot run to `grok.not_installed`.
- The §6.3.1 default next step is unchanged, so §4, AC-1 and the verbatim test still hold.

**Alternatives rejected.**
- Escaping values for `cmd.exe`: a second quoting language whose failure mode is code execution.
- A guard in `CliRunner`: it misses the peers, which start through `McpStdioTransport`, and it would refuse opencode and Muse launchers that carry no caller value.
- Refusing only the argv lists that carry caller values: every turn peer can carry `--model=`, so this gives a host that passes `check_grok_ready` and then fails on its first turn.

**Audit (§10 T-2).**
- opencode: its only process is `serve --hostname 127.0.0.1 --port 0` through `ManagedProcess` (`opencode/server.py:30`), and everything else is HTTP.
- Muse: argv carries only `serve` or `--version` (`muse/host.py:158,516`), plus in WSL mode the developer's distro and path and the host's hex mark (`muse/launcher.py:96-100,140,176`). Its win32 default is `wsl.exe` itself.
- Neither host puts a caller value on argv, so neither launcher changes.
- Residual: a launcher routed through a shell on purpose (`cmd.exe /c …`).

**Verified facts.** These come from a harmless batch file in the scratchpad; no vendor binary was run.
- `shutil.which` returns `.CMD` in upper case.
- `probe.cmd.`, `probe.cmd ` and `probe.cmd. .` all still run the batch file, and `x&echo>MARK.txt` created the marker each time.
- On the user's machine, `shutil.which("grok")` returns `~/.grok/bin/grok.EXE`, so the header claim at `cli.py:9` is false there. §12.3 row 33 asks for that line to be corrected.

**AC-1.** The `completed T` outcome on win32 now uses the §13 seam (`sys.executable`, `-u`, the fake and its arguments). §14 assigns the change to the `write_grok_shim` branch to the test author, not the repair agent.

**Observation for the orchestrator (not acted on).** R-8's fix text asks to "record the `!= target` clause under EC-39". That would be a spec change outside this run's three findings, so EC-39 is unchanged.

**Self-check.**
- Every EC, D and T reference resolves (EC-157, D-19, T-2, EC-2, EC-11 and EC-146 are defined).
- 0 table rows have a wrong cell count.
- The `grok.not_installed` default and EC-157's next step both contain `GrokHostSettings.grok_command`.
- AC-1 is one criterion with two observable outcomes, and both can be met on every platform.
- §8.4 counts are unchanged, with no new code, field, constant, file or dependency.

**r8, second commit (S4-6, orchestrator decision on the EC-39 observation above).**
- EC-39 now records the target clause: it raises `grok.protocol_mismatch` when the caller passed `new_session_id` and the returned `sessionId` differs from it. The guard is kept, because without it a fork naming the wrong session would be accepted after money is spent.
- INV-14 now says that Grok and Muse session-id comparisons ignore letter case. That covers the busy check and the fork checks EC-32, EC-35, EC-36 and EC-39. It matches `require_uuid`, which accepts upper case (`tests/features/grok_host/test_grok_host_records.py:66`). opencode `ses…` ids are compared exactly.
- Also updated:
  - the comment on §8.5 `NativeTurnTable.reserve`;
  - §12.3 rows 30, 32 and 41, all citing INV-14;
  - §16 S4-6;
  - §17 deviation 10 (`GrokWire.check_fork_result`, `grok/wire.py:337-340`);
  - the r8 row.
- `revision: 8` and `status: reviewed` are unchanged.
- Self-check re-run: 0 tables with a wrong cell count, and every new reference resolves.
