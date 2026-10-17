LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — one problem must be fixed first: Grok's required check takes a failed "Tool not found" call to a server that never connected as proof that the server mounted, so a dead mount comes back as a success. The other findings are hardening and test-strength gaps.

Scope: `git diff origin/main...d00bd8ba` (66 files, +10811/-179), checked in the worktree at `2ea367e4`. That commit differs from `d00bd8ba` only in `docs/spec/harness-browser-tools/pipeline.md`.

WHAT THE IMPLEMENTATION GETS RIGHT (keep these as they are)
- **The reaper is narrow and bounded.**
  - On Windows it runs System32 PowerShell by absolute path. The marker reaches the script only through the `VIDBYTE_REAP_MARKER` environment variable, never through argv or the script text. It matches with `IndexOf(..., OrdinalIgnoreCase)` and skips `$PID`.
  - On POSIX it runs `ps` from `NATIVE_PS_PATHS`, never from PATH. It skips its own pid and suppresses `ProcessLookupError` and `PermissionError`.
  - The whole reap runs under `BROWSER_REAP_TIMEOUT_SECONDS`, and `except Exception: return 0` means it never raises (`vidbyte/lib/process/reaper.py:41-77,100-113`).
  - Each marker is a per-call folder name from `mkdtemp`, and those names all have the same length. So one call's marker can never be a substring of another call's folder.
- **Cleanup runs however the call ends after `prepare`.**
  - In `NativeBrowserRun.execute` (`hostkit/browser.py:91-110`), `complete` runs inside the same `try` as the run. A failure inside `complete` therefore still reaches `discard`.
  - `discard` cannot raise: the reaper never raises, and `_remove` suppresses `OSError` and `TimeoutError` (lines 353-372).
  - So the original `NativeThreadError` or `CancelledError` is what propagates (INV-6). The lifecycle tests show this on Windows, and CI shows it on Linux.
- **Key hygiene in the shipped error paths holds (KD-6, INV-4).**
  - Keys are registered with `register_secret` before `select`.
  - Every `from exc` chain in the diff wraps one of three things: an `OSError` or `RuntimeError` that carries only a path, a `ConfigurationError` with a constant message, or a `NativeThreadError` from the same scrubbing factory.
  - The fields `tool_keys`, `selection.key` and `env_overlay` are all `repr=False`.
  - The diff never changes `os.environ`. Its only direct file writes are `NativeBrowserTools.write_file` and `backend.write_text`, which write Grok's agent file into the per-call folder and Muse's settings into Muse's per-call config folder (INV-5).
- **Partial-failure handling is correct for opencode and Muse, and for Grok's cancelled turn.**
  - opencode builds a fail-closed permission order: wildcard deny, then exact allows, with webfetch and websearch denied.
  - opencode servers get `vidbyte-` prefixed ids with `enabled: true`.
  - A Grok `cancelled` stopReason becomes `grok.run_failed` (it is no longer returned as success).
  - Muse's "Required MCP server" failure is translated into `browser.tools_unavailable`. The vendor facts confirm that Muse treats every server as required.

FINDINGS (ranked)
R-E1 [Major] [failure-modes / partial failure as success] vidbyte/harnesses/native/grok/wire.py:189-190, vidbyte/harnesses/native/grok/browser.py:125 — Grok's required check counts a failed "Tool not found" call on a server that never connected as proof of connection, so a dead mount returns as success
  Evidence:
    - wire.py:189-190:
      ```
      if kind == native_threads.GROK_TOOL_CALL_EVENT and isinstance(raw, dict):
          names.append(raw.get(native_threads.GROK_RAW_TOOL_NAME_FIELD))
      ```
      `rawInput.tool_name` is text the model wrote into the `use_tool` meta-tool, not a sign that the server is up.
    - browser.py:125:
      ```
      seen = {*GrokWire.connected(run.outcome, mount), *(call.tool for call in calls.calls)}
      ```
      This also counts calls whose status is FAILED.
    - Vendor facts, lines 119-122: MCP tools are reached only through `search_tool` and `use_tool`, and "A `use_tool` call succeeds without a prior `search_tool` call". So the model can name a tool directly.
    - Spec EC-44 already records that Grok answers a bad name with "Tool not found".
    - Probe `py -3.11 scratchpad/grok_probe.py`: Playwright is mounted, `available_commands` lists only `search_tool` and `use_tool`, and there is one `use_tool` call to `playwright__browser_navigate` whose `tool_call_update` is `failed` with "Tool not found". Output:
      ```
      connected: (<BrowserTool.PLAYWRIGHT: 'playwright'>,)
      calls: (BrowserToolCall(tool=<BrowserTool.PLAYWRIGHT: 'playwright'>, name='browser_navigate', status=<BrowserToolCallStatus.FAILED: 'failed'>),)
      missing: ()
      ```
  Failure:
    - Setup: a mounted server is slower than Grok's roughly 2 s startup grace (EC-16), or it never mounts (EC-45). The caller's prompt says "use the browser", so the model calls the well-known name `playwright__browser_navigate`. Grok answers "Tool not found" and still exits with rc=0.
    - Result: `missing()` returns `()`, `require` passes, and the caller gets a `BrowserThreadResult` with no browser behind it. FR-14 says this case must raise `browser.tools_unavailable` naming the server ("when the vendor's own output shows the mount did not work").
    - No test covers it. `test_grok_names_each_server_it_never_listed` (`test_harness_threads_browser_lifecycle.py:147-155`) runs with `grok_unlisted` and no call. The fake's "Tool not found" branch (`fake_browser.py:689,707`) is never combined with `grok_unlisted`.
  Smallest fix:
    - In both `GrokWire.connected` and `GrokBrowserHarness.missing`, count a call as evidence only when its final status is `completed`. In `missing`, use `call.tool for call in calls.calls if call.status is BrowserToolCallStatus.COMPLETED`, and drop the rawInput branch from `connected` (or count it only for a completed `toolCallId`).
    - Change spec §8 line 643 ("`connected` lists the servers seen in any ... call") to say "completed call".
    - Add a parameter to the AC-12 Grok test: `fake={"grok_unlisted": [tool], "browser_calls": ["<tool>__<name>"]}` must still raise `browser.tools_unavailable`.
  Spec IDs: FR-14, AC-12, EC-16, EC-45, D-11

R-E2 [Minor] [security / KD-6] vidbyte/lib/dataclasses/browser_tools.py:168 — `BrowserToolRequest.tools` shows in `repr`, so a key pasted into `tools` (threat T-1) is printed by any repr, log line or locals-capturing traceback
  Evidence:
    - Lines 168-169:
      ```
      tools: Sequence[str]
      tool_keys: Mapping[str, str] = field(repr=False)
      ```
    - Probe `scratchpad/repr_probe.py`:
      ```
      constructed: BrowserToolRequest(tools=('fc-0123456789abcdef0123456789abcdef',))
      select: ConfigurationError False False
      ```
      The refusal itself does not quote the key; the record's repr does.
  Failure:
    - Setup: the user pastes a Firecrawl key into `tools` (T-1 names exactly this mistake).
    - Result: the record is built, then `select` refuses it, and the refusal text is clean. But `execute` holds `tools` as a local, so Sentry or `rich` locals capture, a debugger, or `logging` of the request prints the key. `register_secret` never sees it, because it is not in `tool_keys`.
  Smallest fix: `tools: Sequence[str] = field(repr=False)`, matching `tool_keys`.
  Spec IDs: T-1, D-28 (spirit of INV-4)

R-E3 [Minor] [concurrency] vidbyte/harnesses/native/hostkit/browser.py:168-171 — The cache check reads "entry missing" and "folder exists" in two separate thread hops, so a concurrent publish between them is reported as a broken cache with advice to delete it
  Evidence:
    ```
    if await asyncio.to_thread(entry.is_file):
        return entry
    if await asyncio.to_thread(published.exists):
        raise errors.failure(... BROWSER_FOLDER_BROKEN_DETAIL ...)
    ```
  Failure:
    - Setup: two first calls race (EC-10, NFR-9). Call A's `os.rename` lands after call B's `is_file()` returns False and before B's `exists()` runs.
    - Result: B raises `browser.tool_install_failed` with the observation "delete that folder" for a healthy cache. A user who follows that advice deletes the folder while call A is using it.
  Smallest fix: when `published.exists()` is true, re-check `entry.is_file()` before raising. A single `to_thread` helper that returns `entry`, `broken` or `absent` does both checks.
  Spec IDs: EC-10, EC-12, NFR-9

R-E4 [Minor] [failure-modes / Windows] vidbyte/harnesses/native/hostkit/browser.py:230-237 — Publishing is a single `os.rename` of a folder npm has just filled, with no retry for the transient `PermissionError` that Windows Defender or the search indexer causes
  Evidence:
    ```
    try:
        os.rename(staging, published)
    except OSError:
        if not entry.is_file():
            raise
    ```
    The caller at line 186-189 maps any `OSError` to `browser.tool_install_failed`, and the `finally` at line 191 deletes the staging folder.
  Failure:
    - Setup: a first call on Windows, while real-time scanning still holds handles on files under `staging/node_modules`.
    - Result: `MoveFileEx` fails with access denied, so the whole install (minutes, and network) is thrown away and the call fails. npm's own `graceful-fs` retries renames on win32 for exactly this reason.
  Smallest fix: retry `os.rename` on `PermissionError` a bounded number of times with a short pause, using a constant (A007). Keep the existing "lost the race" branch.
  Spec IDs: D-5, EC-10

R-E5 [Minor] [cleanup / cancel] vidbyte/harnesses/native/hostkit/browser.py:264-270 — A cancel that arrives while `_make_folder` runs on its thread leaks the new per-call folder, because `prepare` runs before `execute`'s `try`
  Evidence:
    - Line 87 runs before the `try` at line 91:
      ```
      mount = await NativeBrowserTools.prepare(selections, request, errors)
      ```
    - Line 264:
      ```
      folder = await asyncio.to_thread(NativeBrowserTools._make_folder, selections)
      ```
      Cancelling the awaiting task does not stop the worker thread. The thread finishes `mkdtemp` and the mkdirs, but `discard` never learns of the folder.
  Failure:
    - Setup: the caller cancels or times out the call during that hop.
    - Result: an empty `vidbyte-browser-*` folder (artifacts and profiles subfolders, no browser) stays in the temp folder. EC-20 promises that a cancel removes the per-call folder.
    - Low impact: no process is leaked, and the folder is never reused (INV-12).
  Smallest fix:
    - Shield the folder creation (`folder = await asyncio.shield(asyncio.ensure_future(asyncio.to_thread(...)))`), and on `CancelledError` remove the folder before re-raising.
    - Or move folder creation into `execute`, after a `try` that can see it.
  Spec IDs: EC-20, INV-12

R-E6 [Minor] [test quality] tests/features/harness_threads/test_harness_threads_browser_lifecycle.py:110-121 — The cancel test cancels only once, so it passes when the `asyncio.shield` that EC-20 requires is removed
  Evidence:
    - The test calls `task.cancel()` exactly once (line 116).
    - Mutation run (`scratchpad/noshield_plugin.py` replaces `browser.asyncio.shield` with the identity function):
      ```
      PYTHONPATH=... py -3.11 -m pytest -q -p noshield_plugin tests/features/harness_threads/test_harness_threads_browser_lifecycle.py -k cancelled
      3 passed, 26 deselected in 4.09s
      ```
    - Control run (shield replaced by a function that raises): `3 failed, 26 deselected in 1.61s`. This proves the patch reaches line 109.
  Failure: a refactor that drops the shield (for example `await NativeBrowserTools.discard(mount)` in a plain `except`) passes CI. In production, a second cancel (from a `TaskGroup` teardown or `asyncio.timeout` plus a caller cancel) then stops cleanup after the reap and before `_remove`, leaving the folder, or before the reap, leaving Chrome alive.
  Smallest fix: after the first `task.cancel()`, wait until the reap has started (the fake reaper or browser record shows it), call `task.cancel()` again, and keep the same asserts that the browsers are gone and the folders are `[]`.
  Spec IDs: EC-20, AC-13

R-E7 [Minor] [test quality] tests/features/harness_threads/test_harness_threads_browser_mounts.py:325-338 — The AC-28 test gives the user's same-named `playwright` entry `"enabled": False`, so it cannot catch a reader that counts calls on the user's own server as calls on the mounted server
  Evidence:
    ```
    user = {"mcp": {"playwright": {"type": "local", "command": ["user-playwright-mcp"], "enabled": False}}}
    ```
    - This is the only `global_config` scenario in the mounts and lifecycle files. `grep -n global_config` finds it, and one fakes-file line that also uses `enabled: False`.
    - The reader's guard is `server not in mounted`, where `mounted` holds only the `vidbyte-` prefixed ids (`opencode/wire.py:117,127`). No test exercises it with a live, same-named user server.
  Failure:
    - Setup: a regression changes `mounted` to also accept unprefixed names, and the user's own enabled `playwright` answers `playwright_browser_navigate`.
    - Result: opencode's "at least one mounted tool used" evidence (FR-14) is satisfied by the user's server while `vidbyte-playwright` never connected, and no test fails.
  Smallest fix: add a parameter to the same test with `"enabled": True` for the user entry, a fake call on `playwright_browser_navigate` only, and an assertion of `browser.tools_unavailable` (or that `result.tool_calls` holds no user-server call).
  Spec IDs: EC-40, FR-13, FR-14

R-E8 [Minor] [data and scale] vidbyte/harnesses/native/grok/wire.py:95,159,183 — A Grok browser run's stdout (capped at 64 MiB, not 4 MiB) is parsed three separate times on the event loop; opencode's is parsed twice
  Evidence:
    - `CliRunner.json_objects(outcome.stdout)` is called in `read_stream` (95), `tool_calls` (159) and `connected` (183), and in `opencode/wire.py` 66 and 119.
    - The cap is `NATIVE_PROCESS_MAX_OUTPUT_BYTES = 67108864` for browser calls (`grok/threads.py:119`).
    - Probe `scratchpad/parse_probe.py`, 16 MiB of roughly 190-byte events:
      ```
      bytes=16777078 lines=89717 one_parse=0.272s x3_at_64MiB_est=3.26s
      ```
  Failure: a long browsing session that prints many small events blocks the event loop for about 1 s per parse, about 3 s near the cap. Every other coroutine in the process stalls, including concurrent browser calls and their reaper timeouts.
  Smallest fix: parse once in the seam and pass the event list to `tool_calls` and `connected`, or run the readers via `asyncio.to_thread`.
  Spec IDs: NFR-9 (concurrency); n/a otherwise

VERIFIED CLAIMS
- **INV-6, exactly one `NativeThreadError`: held.**
  - Each public wrapper re-raises `CancelledError` and `NativeThreadError`, and translates `ConfigurationError` and any other exception through the factory (diff +223-230, +1333-1340, +1819-1826).
  - `discard` cannot raise, so it never replaces the original error.
  - A second cancel during cleanup surfaces as `CancelledError`, which is correct.
- **"The SDK never writes into the workspace" (INV-5): held for SDK writes.** Grepping the diff for `write_text|write_bytes|.open(|mkdir|mkdtemp|os.environ[|putenv` finds only:
  - the per-call `mkdtemp` and its mkdirs;
  - the cache staging folder;
  - `NativeBrowserTools.write_file` (Grok's agent file);
  - Muse's `backend.write_text` into its own config folder.

  Files a server writes into its own working folder are the agent's, which EC-24 and EC-43 accept.
- **"Every browser killed" on success, error, timeout and cancel: held for one cancel.**
  - Local lifecycle run: `28 passed, 1 skipped`. The skipped test is the POSIX `ps` test, and it ran on CI.
  - CI run 39075450892 on `d00bd8ba`: success.
  - Under a second cancel the claim is not tested (R-E6), and a cancel during `prepare` leaks the empty folder (R-E5).
- **KD-6 on every path: held for the shipped error paths; one repr leak (R-E2).**
  - `repr=False` is set on `tool_keys`, `BrowserToolSelection.key` and `CliInvocation.env_overlay`.
  - Odd inputs (non-list `tools`, too many items, a list as `tool_keys`, non-str keys or values, dict or iterator `tools`) all raise `ConfigurationError` without quoting.
  - Every `__cause__` chain wraps only path-bearing `OSError`/`RuntimeError`, constant-text `ConfigurationError`, or a scrubbed `NativeThreadError`.
  - The test helper `check_browser_error` (`conftest.py:579-615`) scans `str`, `repr`, `vendor_message` and details, but not `__cause__` or `__context__`. Today that gap is closed by the code, not by the test.
- **"The reaper never kills a process it did not start": held by construction.**
  - The marker is the unique `mkdtemp` path, and those names have a fixed length.
  - The PowerShell script skips `$PID`, and the marker travels only in the environment.
  - The POSIX branch skips `os.getpid()`.
  - A process gets killed only if its command line contains this call's private folder path. Only the call's own children (or a program the agent launched on an artifact) can carry that path.
- **No partial failure reported as success:**
  - Grok cancel: held (`cancelled` becomes `grok.run_failed`).
  - opencode with no tool used: held (`missing` names every server when `calls.calls` is empty).
  - Muse silent disable: held (only the verified `schema_version` + `mcpServers` shape is written; the vendor fails required servers with rc=1).
  - Grok required check: NOT held (R-E1).
- **On Windows 11 with Python 3.11.0, `Path.exists` on a delete-pending folder returns False and does not raise.** This refutes my own suspicion that `_remove_attempts` could raise from `exists()`. Dropped.
- **The local HEAD `2ea367e4` differs from the reviewed `d00bd8ba` only in `pipeline.md`.** Held.
- **Pre-mortem: three plausible bugs no test catches.**
  1. A failed `use_tool` call to a server that never connected passes Grok's required check (R-E1; confirmed by the probe).
  2. Removing `asyncio.shield` from `execute` (R-E6; confirmed by mutation).
  3. The opencode reader counting the user's own enabled same-named server (R-E7).

  A fourth: a key in `__cause__`/`__context__` would pass `check_browser_error`, because the helper does not scan chains.

COMMANDS RUN
- `git diff --stat origin/main...d00bd8ba | tail -1` → `66 files changed, 10811 insertions(+), 179 deletions(-)`
- `git diff --stat d00bd8ba 2ea367e4` → `docs/spec/harness-browser-tools/pipeline.md | 11 ++++++++---` / `1 file changed, 8 insertions(+), 3 deletions(-)`
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_browser_registry.py` → `40 passed in 1.40s`
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/harness_threads/test_harness_threads_browser_lifecycle.py` → `28 passed, 1 skipped in 43.12s`
- `gh run view 39075450892` → conclusion success (CI on d00bd8ba: 6434 passed, 205 skipped, Python 3.11 and 3.12; the lifecycle file ran 29 tests on Linux)
- `gh run view 39075452414` → conclusion success (Static policy)
- `py -3.11 scratchpad/grok_probe.py` → `connected: (<BrowserTool.PLAYWRIGHT: 'playwright'>,)` / `calls: (... status=<BrowserToolCallStatus.FAILED: 'failed'>),)` / `missing: ()`
- `py -3.11 scratchpad/repr_probe.py` → `constructed: BrowserToolRequest(tools=('fc-0123456789abcdef0123456789abcdef',))` / `select: ConfigurationError False False`
- `py -3.11 scratchpad/parse_probe.py` → 16 MiB of 3 KB events: `one_parse=0.032s`; 16 MiB of 190-byte events: `one_parse=0.272s x3_at_64MiB_est=3.26s`
- `pytest -q -p noshield_plugin ...lifecycle.py -k cancelled` → `3 passed, 26 deselected in 4.09s`; control `-p boomshield_plugin` → `3 failed, 26 deselected in 1.61s`
- Delete-pending probe (open a handle in a folder with `FILE_SHARE_DELETE`, remove it, call `Path.exists`) → `Path.exists: False`, no exception
- Odd-inputs probe for `BrowserToolRequest` → every case raised `ConfigurationError`, and no message contained the key
- `git diff origin/main...d00bd8ba -- vidbyte | grep -n "^+.*(write_text|write_bytes|.open(|mkdir|mkdtemp|os.environ[|putenv|...)"` → diff lines 1019, 1020, 1068, 1116, 1118, 1121, 1586 only (staging, the per-call folder, `write_file`, Muse settings)
- `git diff origin/main...d00bd8ba -- vidbyte | grep -n "from exc|except "` → every chained cause is `OSError`, `RuntimeError`, `ConfigurationError` or `NativeThreadError` (diff lines 223-230, 251-253, 957-989, 1058-1060, 1333-1366, 1819-1823)

All probe scripts are under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/1da32edd-ec0f-4839-ba1f-52db538ed13c/scratchpad/`. None of them touches the worktree.
