VERDICT: SOUND WITH FIXES — r2 resolves round-1 R-1 and R-3 to R-10, and the turn-ending half of R-2. One Blocker remains: the new grace and watchdog paths disconnect inside tasks that the pump then cancels with a plain asyncio cancel. That aborts claude-agent-sdk's shielded close and leaks the `claude` process. The Blocker, the two Majors (a grace armed for the wrong prompt, and the default `--permission-prompts` flag on old CLIs) and five Minors are all local edits to D-4, row 7, the steer and lookup text, the next-step table, T-3 and §13. None of them reverses a settled decision.

WHAT THE SPEC GETS RIGHT

- **The marker contract can now be checked on this machine.**
  - INV-21 and AC-19 hash the bytes after CRLF becomes LF. request.md:175-184, normalized that way, is 911 bytes with SHA-256 `0374a2c8…942f497a`.
  - The normalization is needed. `core.autocrlf=true` is set in the system gitconfig, there is no root `.gitattributes`, and `git ls-files --eol vidbyte/harnesses/__init__.py` gives `i/lf w/crlf`.
  - Rows 30 and 31 and §12.5 insert the request.md §C texts verbatim at the given points: REPO_MAP.md:147/:149/:151, and harnesses/README.md:167/:177-178. That README is 8,805 characters, far under A009.
- **R-4's mapping is better supported than the spec says, so keep NONE's flag and HOST ⇔ `can_use_tool` (§9.1) as they are.**
  - CLI 2.1.296 `--help` treats a run as print mode "via -p, or when stdout is not a TTY, e.g. piped or redirected output". That is how the SDK always runs it.
  - `--input-format` and `--output-format` also say "(only works with --print)", yet the SDK relies on both without `--print`.
  - The TS SDK exposes the same switch, `permissionPrompts?: 'host' | 'none'` (sdk.d.ts:2018-2025): "'none' … denied immediately … canUseTool is never called".
  - sdk.d.ts:5572 makes `permission_denials` "the authoritative record", including headless auto-deny.
- **The Windows half of `ClaudeProbe.locate_cli` mirrors `_find_cli` steps 2-4 without the bundled copy** (subprocess_cli.py:255-339).
  - It checks for a native `.exe`/`.com` on the final component, with trailing dots and spaces stripped, then tries `which("claude.exe")`, then `~/.local/bin/claude.exe`.
  - `claude.not_installed`, with "Install Claude Code (the native claude.exe on Windows), or pass cli_path to ClaudeHost.", is the right outcome for a refused shim. It gives the same remedy as the SDK's own batch refusal.
  - The `windows` and `home` arguments make AC-38 testable on Linux CI.
- **The r2 names and records pass the gates they touch.**
  - A ruff 0.16.4 S105-S107 probe of every r2 constant and enum is clean: the sign-in field constants, `CLAUDE_MAX_OUTPUT_TOKENS_ENV`, the four next-step constants, `ClaudeCliFlag.PERMISSION_PROMPTS` and `ClaudePermissionPrompts`. The old `CLAUDE_TOKEN_SOURCE_FIELD = "tokenSource"` is flagged.
  - The four generic codes exist (failure.py:27, :34, :47, :92).
  - `field(repr=False)` composes with `frozen=True, slots=True` (coding.py:37, :55-58).
  - The grace constant is read from the module at call time, which gives AC-37 a clean patch point.

FINDINGS

R-1 [Blocker] [L5] §8.1 D-4, §12.3 row 7, §6.1 INV-8, §7 NFR-7, §5 — The grace and watchdog tasks disconnect the client themselves, and the pump then cancels those tasks with a plain asyncio cancel. That aborts claude-agent-sdk's shielded close, so a wedged `claude` process is never closed or killed, while its turn ends and the cap frees its place
  Evidence:
  - Spec:
    - Row 7 (spec:1128), the grace task: "it discards a pending steer, sets the interrupt flag unless the budget flag is set, and disconnects once".
    - Row 7, the pump: "build a `ClaudeTurnOutcome` and classify → set done → `finally`: cancel the watchdog and the grace task, disconnect once, release the slot."
    - D-4 (spec:459): "If the interrupt raises, it disconnects." Also: "A disconnect always returns: the SDK's close is shielded and escalates in 5-second steps."
    - §5 (spec:198): "The `disconnect` in the pump's `finally` guarantees the process ends."
    - INV-8: "The host never awaits `disconnect()` twice for one client. No client stays connected after its turn is terminal".
    - Round 1 gave the same "always returns" evidence (S1-spec-review.md:55) without the caveat below, and r2 copied it.
  - SDK 0.2.165 (read only):
    - subprocess_cli.py:979-988: "A raw asyncio cancellation (`asyncio.wait_for` / `asyncio.timeout` firing, a bare `task.cancel()`, loop shutdown) is still delivered at the next await in here, and the escalation below only catches `TimeoutError` — so it would be skipped."
    - The call path is `client.py:607-621` `disconnect()` → query.py:1181-1182 shielded `_close_impl()`. That cancels the read task and awaits it (query.py:1194-1196), and only then calls `await self.transport.close()` (query.py:1207). The close escalates through stdin close, terminate and kill (subprocess_cli.py:962-1060).
    - The read task's `finally` sends `{"type": "end"}` (query.py:574), and `receive_messages` stops on it (query.py:1139). So the pump leaves its read loop while the disconnecting task is still inside `_close_impl`, before `transport.close()` has started.
  Failure:
  - The CLI acknowledges an interrupt and then stays stuck (EC-53). Step by step:
    1. The grace fires, sets the `disconnected` flag (INV-8's once-guard) and awaits `disconnect()`.
    2. The pump receives `end`, classifies INTERRUPTED, sets done and calls `cancel()` on the grace task, with no await in between.
    3. The grace task is still parked at `await self._read_task.wait()`, so `_close_impl` stops there. Stdin is never closed, and nothing terminates or kills the process.
    4. The pump's own "disconnect once" sees the flag and skips.
    5. The process runs until the interpreter exits. Meanwhile the turn is terminal, the session id is free, and `max_live_sessions` admits a new spawn.
  - So NFR-7, INV-8, §5 and T-1's runaway guard all fail, and each repeat of EC-53 leaks one more process.
  - The watchdog path fails the same way when `interrupt()` raises (AC-31's second clause), because the pump's `finally` cancels the watchdog while it is inside `disconnect()`.
  - The caller paths are exposed too:
    - `interrupt_claude_turn` and `steer_claude_session` call `interrupt()` in the caller's task, and that call can take up to 60 s (`_send_control_request`, `fail_after(60.0)`, query.py:706-737).
    - `ToolRuntime._run_tool_execute` wraps a tool in a plain `asyncio.wait_for` (vidbyte/agents/runtime.py:1455).
    - So if `ToolSettings.tool_timeout_seconds` is shorter than the interrupt, `_arm_grace()` never runs, and if it fires during the caller's own disconnect, the close is skipped.
  - Even on the happy path, done fires before the disconnect finishes ("set done → `finally` … disconnect once").
    - A waiter woken by done can spawn into the freed cap while the old process is still closing.
    - Closing can take about 25 s: 5 s for the in-process MCP bridge (sdk_mcp_bridge.py:47) plus the roughly 20 s transport escalation.
    - So "No client stays connected after its turn is terminal" is false.
  - Fakes with an instant `disconnect()` still pass AC-25, AC-31 and AC-37.
  Smallest fix:
  - **One close task per session (row 7).**
    - `ClaudeLiveSession` holds one close task and keeps the reference (S006).
    - The first path that needs a disconnect creates it with `asyncio.create_task(client.disconnect())`. That path may be the pump's `finally`, the watchdog, the grace, a caller interrupt that raised, or `aclose`.
    - Nothing ever cancels it. Every path awaits it through `asyncio.shield`, and on `CancelledError` awaits it again under shield before re-raising.
    - This is the repo's own pattern, `MultiAgentCleanup.shielded_close` (vidbyte/agents/multi/cleanup.py:36-46; also `harnesses/execution.py:258-264`).
  - **The watchdog and the grace only start the close task, then return.** The pump cancels them only while they sleep or wait on `interrupt()`.
  - **The pump awaits the close task before it sets done and releases the slot.** Then INV-8, NFR-7 and §5 hold as written. If the author prefers done first, restate INV-8 and NFR-7 instead, and count a closing session against the cap until its close completes.
  - **Optional:** run the caller's interrupt-then-arm sequence in a session-owned task, so that a caller-side timeout cannot skip `_arm_grace()`.
  - **D-4:** replace "A disconnect always returns" with: "a disconnect returns within about 25 s unless it is cancelled with a plain asyncio cancel, which skips the SDK's terminate and kill (subprocess_cli.py:979-988), so the host never cancels it".
  - **AC-25, AC-31 and AC-37:** the fake's `disconnect()` must await something, such as an event the test releases, and record that it completed. Done must not fire before that completion, and no disconnect may be cancelled.

R-2 [Major] [L5] §8.1 D-4, §12.3 row 7, §6.3 EC-19 — The grace is armed whenever `interrupt()` returns, even after the interrupted prompt's result has already been read. In EC-19's race it therefore times the steered prompt, and a healthy steered turn is killed after 30 s
  Evidence:
  - Row 7: "after any `client.interrupt()` that returns … the helper `_arm_grace()` starts the grace task unless one is already armed … If the prompt's result has not arrived by then, it … disconnects once. The arrival of the prompt's result cancels it."
  - EC-19 (spec:326): "A steer arrives just after the CLI emitted the result, before the pump read it | `interrupt()` is a no-op. The pump reads the result, sees the pending message and sends it as a new turn."
  - The SDK read loop routes stdout lines in order (query.py:388-470).
    - In EC-19 the result was written before the CLI saw the interrupt.
    - So the loop hands the result to the pump before it reads the interrupt's `control_response` and sets that event, and the pump is woken first.
  - sdk.d.ts:4661 adds a second case: "a turn that crashes during interrupt handling emits its error result on a direct-write path that may precede the receipt."
  Failure:
  - EC-19 timing, step by step:
    1. The pump reads the old result and sends the steer with `query()`.
    2. Then `steer()`'s `interrupt()` returns.
    3. `_arm_grace()` finds nothing armed, so it arms a grace.
    4. "The prompt" is now the steered prompt. If that turn runs longer than 30 s, the grace sets the interrupt flag and disconnects.
    5. A healthy steered turn ends INTERRUPTED with no failure, and under R-1 its process leaks.
  - `interrupt_claude_turn` can race a natural result in the same way. It then arms a grace on a session whose `finally` has already run, and that stray task outlives the turn by 30 s.
  - "Unless one is already armed" never says the slot is cleared when the result cancels the grace. Example:
    1. A steer's grace is armed, and the interrupted result cancels it.
    2. Later, in the steered turn, the time budget fires and its `interrupt()` returns.
    3. `_arm_grace()` sees the old task object and arms nothing.
    4. If that interrupt is acknowledged but never answered, the turn stays RUNNING forever, because the watchdog fires only once. That is EC-53 again.
  Smallest fix:
  - **Row 7 and D-4:** `_arm_grace()` does nothing when the session is terminal, or when the pump has already read the result that the interrupt aimed at.
  - The simplest way is a prompt counter. Capture it before `interrupt()`, compare it in `_arm_grace()`, and compare it again when the grace expires.
  - The result's arrival cancels the grace and clears the slot.
  - **AC-37:** add a case where the fake yields the prompt's result before its `interrupt()` returns while a steer is pending. With the grace patched small, the steered turn is not disconnected and ends COMPLETED.

R-3 [Major] [L5] §9.2 `permission_prompts` row, §6.3 EC-3/EC-4, §6.2 AC-22, §8.1 D-6, §15 A-3 — Every default request now carries `--permission-prompts none`. On a CLI that predates the flag, every default spawn therefore fails at start as `claude.process_exited` with "Respawn, then resume by id.", which loops, instead of `version_unsupported`
  Evidence:
  - Spec:
    - The `permission_prompts` row (spec:863): "NONE gives `extra_args["permission-prompts"]="none"`", and NONE is the default. In r1, no default request carried an `extra_args` flag.
    - D-6: "The version and auth-mode checks run after connect and before the first query."
    - EC-3: for an older CLI, "A spawned turn fails after connect, before any query." The result is `claude.version_unsupported`, "Run claude update."
    - EC-4: "The CLI is older and the request uses an `extra_args` flag that version does not know | The process exits at start, which maps to `claude.process_exited` … accepted limitation".
    - AC-22: for version 2.1.200, "the spawned turn ends FAILED with `claude.version_unsupported`".
    - `CLAUDE_PROCESS_EXITED` → "Respawn, then resume by id." (spec:802).
  - SDK and CLI:
    - `_build_command` appends `extra_args` (subprocess_cli.py:741-755).
    - The CLI's option parser rejects unknown options and exits non-zero before writing to stdout. EC-4 says so, and the `.default("host")` quoted in §11 is Commander's API.
    - The read loop then raises `ProcessError("Command failed with exit code …")` (subprocess_cli.py:1157). That error fails the pending `initialize` at once (query.py:543-546), so `connect()` raises before any version is known. A-14 holds.
  Failure:
  - With a pre-flag CLI installed, `check_claude_ready` correctly reports `version_unsupported`, because the probe connects with only `cli_path` (row 9).
  - Every default `spawn_claude_session`, though, ends FAILED `process_exited`. The model is told to respawn, gets the same failure, and loops. This is the same "Respawn" trap that round-1 R-5 removed for the shim.
  - AC-22's spawn half passes with fakes but is false for any real CLI old enough to lack the flag.
  - EC-4 understates its reach: it now covers every default spawn, not only requests that opt into a flag.
  - A-3's fallback, "a request's time budget still bounds the turn (D-4)", does not hold for the default request, because `timeout_seconds` defaults to `None` (spec:903).
  Smallest fix:
  - When `connect()` raises `ProcessError` or `CLIConnectionError` (operation `connect`), keep the code `claude.process_exited` but pass a start-failure next step: a new constant `CLAUDE_START_FAILURE_NEXT_STEP`, "Run check_claude_ready to see why Claude Code did not start."
    - This follows the precedent of `CLAUDE_LIVE_CAP_NEXT_STEP` on `session_busy`.
    - `from_exception` already receives `operation`.
    - It also gives a sane next step for the real path of `user` on Windows (see VERIFIED CLAIMS, EC-44).
  - Restate EC-4 so that it covers every default spawn.
  - Qualify AC-22's spawn half with "on a CLI that accepts the default flags".
  - In A-3, say "when `timeout_seconds` is set".
  - Note that the CLI version that introduced `--permission-prompts` is unverified. The SDK's bundled 2.1.294 is not in the wheel.

R-4 [Minor] [L9] §6.1 INV-7 and INV-18, §9.2 steer row, turn classification step 4 — The steer grace path contradicts INV-7 and INV-18
  Evidence:
  - INV-7: "Once an `interrupt()` call returns, whether … or a steer sent it, the turn reaches its terminal status when that result arrives". D-3 and AC-9 instead resend the message when that result arrives.
  - INV-18: "A steer is delivered exactly once". AC-37(c), however: "no `query` carries the steer message".
  - Step 4 (spec:756): "a steer whose interrupt got no result within the grace period: status INTERRUPTED, no failure". The steer tool has already returned `{"steered": true}` (spec:839).
  - Row 17's description does warn the model: "if Claude Code never answers the interrupt, the turn ends interrupted without the message."
  Failure:
  - S2 writes tests from INV-7 and INV-18 that conflict with AC-9 and AC-37(c).
  - At run time, INTERRUPTED after a steer is ambiguous. It can mean the grace dropped the message, or that a caller or close interrupted the turn after the message was delivered.
  Smallest fix:
  - INV-7: "…the wait for that interrupt's result ends when it arrives or when `CLAUDE_INTERRUPT_GRACE_SECONDS` expires; on expiry the turn becomes terminal and the client is disconnected once."
  - INV-18: add "unless the grace expires first, in which case it is never sent."
  - Optional: if the result itself should say so, step 4 can attach a failure to the steer case, as step 13 already does for COMPLETED. An example is `claude.process_exited`, whose reason names the unsent steer and whose next step is "Respawn, then resume by id.".

R-5 [Minor] [L9] §9.2 spawn row and `cli_path` field row vs §6.3 EC-57 — The text allows two readings for a request-level `cli_path` that names a `.cmd`: fall back silently to the host's CLI, or report `not_installed`
  Evidence:
  - The spawn row (spec:733): "`not_installed` means the effective CLI path is empty: the request's `cli_path` as `ClaudeProbe.locate_cli` screens it, else the host's resolved path".
  - The field row (spec:899) uses the same wording.
  - EC-57: "a given `cli_path` names a `.cmd` or `.bat` script | … readiness and spawn report `claude.not_installed` before any connect".
  - D-5: a given batch path "becomes `""`".
  Failure: A literal reading, `locate_cli(request.cli_path, …) or host_path`, runs the host's `claude.exe` for a request that named `C:\tools\claude.cmd`. The developer's explicit choice is then ignored without any signal. EC-57's reading reports `not_installed` instead, so S2 and S3 can pick different readings.
  Smallest fix: In both rows, say: "a non-empty request `cli_path` that screens to `""` reports `claude.not_installed`; the host's resolved path is used only when the request's `cli_path` is empty".

R-6 [Minor] [L1] §8.1 D-5, §11 lookup evidence, §6.3 EC-2 — Unlike D-5's own headline and Q3, the macOS and Linux lookup uses PATH only, so a native install that is off PATH is reported as not installed
  Evidence:
  - D-5's headline says the host finds the CLI "the way the SDK does, minus the SDK's bundled copy". Its rule is "Elsewhere it is `shutil.which("claude") or ""`".
  - §11 (spec:1071, :1074): "elsewhere, six home and system locations … D-5 keeps steps 2–4 for Windows and step 2 elsewhere."
  - `_find_cli` on POSIX checks `~/.npm-global/bin/claude`, `/usr/local/bin/claude`, `~/.local/bin/claude`, `~/node_modules/.bin/claude`, `~/.yarn/bin/claude` and `~/.claude/local/claude`.
  - The author's reason (S1-spec-author.md:162) is that a miss on POSIX "gives a clear `not_installed`, not a loop".
  Failure:
  - Claude Code's native installer puts `claude` in `~/.local/bin`. That folder is often missing from PATH for a host started by an IDE, launchd, cron or systemd, and the SDK alone would still find the CLI there.
  - The host instead reports "claude.not_installed … Install Claude Code" for a CLI that is installed.
  - That contradicts Q3, "`cli_path` defaults to the user's installed `claude`". It also contradicts D-5's own rationale: "It would also miss a native `claude.exe` that sits only in `~/.local/bin`, which the SDK's own lookup finds".
  Smallest fix:
  - On POSIX, after `which("claude")`, return the first of those six paths under `home` that `Path.is_file()` accepts. Keep the paths in one row-14 tuple constant.
  - Add a POSIX home case to AC-38, and update EC-2 and §11.
  - This stays inside Q3, so it is not scope-adding. If the author keeps PATH-only, D-5's headline must say so.

R-7 [Minor] [L7] §10 T-3, §6.1 INV-12, §12.3 row 11 — T-3 misses the shortest leak path, which is the child's command line, and claims more than `repr=False` hides
  Evidence:
  - T-3: "`env` and `headers` are declared `repr=False`, so printing a record, an assertion diff or a log line never shows them".
  - `_build_command` writes each external MCP server's `env` and `headers` inline on argv as `--mcp-config <json>` (subprocess_cli.py:667-692). It writes `--settings` inline too (:658-660), and it has no temp-file fallback.
  - pytest 8.3.5 `_compare_eq_cls` (`_pytest/assertion/util.py:541, 575-576`) chooses which dataclass fields to diff by `compare`, not by `repr`, and prints `repr(field_left)` for each field that differs.
  - `settings` (inline JSON can carry an `env` block), MCP `url` and `args` keep the default repr.
  - The field guide asks CLI integrations for "environment-based credential injection" (field-guide/vidbyte-sdk/cli-backed-source-integrations.md:3).
  Failure:
  - On a shared host, a bearer token in `ClaudeMcpServer.headers` can be read from the process list (`ps`, `/proc/<pid>/cmdline`) for the whole turn, and process monitors log it.
  - A failing equality assert on two requests prints `env`.
  - The spec says neither can happen, so no README or docstring warns developers.
  Smallest fix:
  - In T-3 and in row 11's KNOWN EDGE CASES, state two things. External MCP `env` and `headers` and inline `settings` reach the child's argv through the SDK. `url`, `args` and `settings` are not hidden from repr.
  - Drop "an assertion diff".
  - Optional Q-n [scope-adding], default not built: pass external MCP configs as the path of a 0600 temp file, which the SDK accepts (subprocess_cli.py:690-692).

R-8 [Minor] [L10] §13 test seams, §6.2 AC-38 (last sentence), §6.3 EC-2 — §13 gives no seam for a host whose resolved path is `""`, and on this Windows machine patching `shutil.which` alone still finds the real CLI
  Evidence:
  - AC-38: "A host whose resolved path is `""` reports `claude.not_installed` from readiness and from spawn, and constructs no client."
  - §13 names only two seams: calling `locate_cli(..., windows=True, home=tmp_path)` with `shutil.which` patched, and "Pass `cli_path="..."` to `ClaudeHost`".
  - Row 3: `__aenter__` reads `sys.platform` and `Path.home()` itself.
  - On this machine, `Path.home()/.local/bin/claude.exe` exists, and `which("claude")` returns `C:\users\422mi\.local\bin\claude.EXE`.
  Failure: A test that builds `ClaudeHost()` with `shutil.which` patched to `None` resolves `""` on Linux CI. On the user's Windows machine, where `python scripts/run_ci.py` is the gate, it resolves the real `claude.exe`, so the test fails there.
  Smallest fix: Add a §13 fact. For the host-level empty path (EC-2 and AC-38's last sentence), patch `ClaudeProbe.locate_cli` to return `""`, or patch `Path.home` in the host module as well as `shutil.which`.

VERIFIED CLAIMS:

Round-1 findings, checked against the r2 text and not only against §16:
- R-1: resolved.
  - INV-21, AC-19, row 1, §12.4, §13 and §14 hash either the CRLF-normalized bytes or the committed blob.
  - The hash recomputes: 911 bytes, `0374a2c8…942f497a`.
- R-2: partly resolved.
  - Every turn now ends (D-4, INV-7, EC-53, AC-37), and the interrupt row no longer contradicts EC-53.
  - The process-ending half is not resolved (see R-1), and the grace can be armed for the wrong prompt (see R-2).
- R-3: resolved for `env` and `headers` (§8.5 `ClaudeMcpServer`, spec:589; the `env` row, spec:900; INV-12; AC-24).
  - `repr=False` composes with frozen and slots.
  - The residual is R-7.
- R-4: resolved.
  - Covered by the `permission_prompts` row (spec:863), `ClaudeCliFlag.PERMISSION_PROMPTS`, §9.1's "HOST requires `can_use_tool`, and NONE refuses it", EC-42, A-2 and A-3.
  - The evidence is stronger than the spec states. The residual is R-3.
- R-5: resolved on Windows (D-5, row 9, EC-57, AC-38). The residuals are R-5, R-6 and R-8.
- R-6: resolved. §12.4 has the S054 line, and the ruff probe of the r2 names is clean.
- R-7: resolved. NFR-1 limits the package smoke to what `import vidbyte` loads, and `vidbyte/__init__.py:611` imports `vidbyte.tools.toolsets`.
- R-8: resolved.
  - The four `CLAUDE_*_NEXT_STEP` constants are in the §9.2 table and row 14.
  - `vidbyte/lib/constants/failure.py` (26 lines, bounds only) holds no next-step text, so nothing is duplicated.
- R-9: resolved.
  - FR-12, D-3 and row 17 now say so.
  - sdk.d.ts:4571 shows that without `perTaskStopAffordance` "the interrupt kills background tasks", and 0.2.165 never declares it.
- R-10: resolved. Rows 3, 15 and 22 state their KNOWN EDGE CASES in words.

Repo, SDK and CLI claims:
- §8.4 budget (22 new files, 9 modified, 69 classes): HELD.
  - §12.3 rows 1-22 are CREATE and rows 23-31 are MODIFY.
  - The classes sum to 10+23+1+17+1+16+1 = 69.
- Rows 30 and 31 and §12.5 say "verbatim", at the request.md §C insertion points: HELD.
  - REPO_MAP.md: `#### vidbyte/harnesses/` :147, paragraph :149, `##### vidbyte/harnesses/stores/` :151.
  - harnesses/README.md: `## Key modules` :167, the `serialization.py` bullet :177, a blank line :178.
- The generic codes exist: HELD. failure.py has `CONFIGURATION_UNSUPPORTED_COMBINATION` :27, `CONFIGURATION_INVALID_ARGUMENT` :34, `INPUT_EMPTY` :47 and `ACTION_PRECONDITION_FAILED` :92. The CLAUDE block goes between :34 and `CODEX_SDK_UNAVAILABLE` :35.
- S054 (ruff 0.16.4 `--isolated --select S105,S106,S107` on a stdin probe of the r2 names, including `account.get(name) not in (None, CLAUDE_ABSENT_SOURCE)` and `{"budget_tokens": n}`): HELD, with no hits.
  - The control names `token_source = "none"` and `CLAUDE_TOKEN_SOURCE_FIELD = "tokenSource"` are flagged.
  - The rule's regex uses underscore word boundaries.
- Banned APIs and Python version: HELD.
  - lint/ruff.toml bans only `typing.TypedDict`, `typing.assert_never` and `asyncio.Lock`. pyproject says `requires-python = ">=3.11"`.
  - The spec uses `asyncio.Event`, `asyncio.sleep`, `asyncio.Semaphore` and `wait_for` on `event.wait()`; none is banned. The R-1 fix's `asyncio.shield` already appears in vidbyte/agents/multi/cleanup.py:40.
- `repr=False` with `@dataclass(frozen=True, slots=True)`: HELD (coding.py:37, :55-58; model_configs.py:51).
- T-3, "an assertion diff … never shows them": FAILED, because pytest's `_compare_eq_cls` ignores `repr=False` (see R-7).
- D-4, "A disconnect always returns": HELD only against anyio cancellation (query.py:1181-1182; subprocess_cli.py:994-1050). FAILED against a plain asyncio cancel (subprocess_cli.py:979-988). See R-1.
- §5, "The `disconnect` in the pump's `finally` guarantees the process ends": FAILED as designed (see R-1).
- §5's flowchart shows the grace edge ("interrupt acknowledged, no result within grace, disconnect"): HELD.
- §11 lookup citations: HELD. `_find_cli` :255, `_reject_windows_batch_cli` :415 (called at :807), the `canUseTool` error :590-591, and `extra_args` emission :741-755 all match.
- D-5's Windows rules against `_find_cli`: HELD, with two small notes.
  - The SDK screens every path component for `.bat`/`.cmd`, while D-5 checks only the final component. That makes no difference for `which` hits.
  - D-5 does not say the `.exe`/`.com` test ignores case, and `which("claude")` here returns `…\claude.EXE`. The `which("claude.exe")` fallback hides this, but row 9 should say "any case", as D-5 already does for the batch suffixes.
- A-14 (an unknown flag surfaces from `connect()` as `ProcessError`): HELD (subprocess_cli.py:1157; query.py:543-546 fails the pending `initialize` at once).
- Assumptions and edge cases backed by vendor text: HELD.
  - A-2: sdk.d.ts:5572.
  - A-3: CLI `--help` and sdk.d.ts:2018-2025.
  - EC-58: sdk.d.ts:5738 and :5746, "Crash/startup-error results may carry zeroed values".
- The interrupt receipt comes before the result on a clean interrupt, but may follow it after a crash (sdk.d.ts:4661): HELD. This is the basis of R-2.
- `Query.interrupt()` has a 60 s control timeout and raises a bare `Exception("Control request timeout: interrupt")` (query.py:706-751): HELD. `_close_impl` never fails pending control requests, so an interrupt still in flight when the client is disconnected waits the full 60 s.
- The agent runtime's tool timeout is a plain `asyncio.wait_for` (vidbyte/agents/runtime.py:1455), and `tool_timeout_seconds` defaults to `None`: HELD.
- The AC-37 seam (patch `vidbyte.harnesses.native.claude.session.CLAUDE_INTERRUPT_GRACE_SECONDS`, read at call time as row 7 says): HELD.
- The AC-38 seam: HELD for the function, but not for the host-level sentence (see R-8).
- The spec contains no test cases: HELD.
- EC-44 and A-15: FAILED. This is outside the Focus; I checked it only as a dependency of A-14 and the §9.2 exception mapping, and did not rank it.
  - `anyio.open_process(..., user=...)` runs inside `connect()`'s `try` (subprocess_cli.py:873-880).
  - `except Exception` wraps any `ValueError` or `TypeError` there as `CLIConnectionError("Failed to start Claude Code: …")` (:912-913).
  - So `user` on Windows ends as `process_exited`, not as `configuration.invalid_argument`. R-3's start-failure next step would at least stop the "Respawn" loop on that path.
