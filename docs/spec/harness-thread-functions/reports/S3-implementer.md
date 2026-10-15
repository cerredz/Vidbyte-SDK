# S3 Implementer report — harness-thread-functions (r4)

Start HEAD `9071d2af` on `feat/native-grok-opencode-meta-hosts`. S2_HEAD was `8e5e65ec` and became `4da73cf3` after the S2 helper fix. origin/main `179d8adc`. The last implementation commit is `554f8b66`, and the proof commit is `c437c0d9`.

## Status

**DONE.** All 49 rows of §12.3 are implemented and committed.

The first pass stopped BLOCKED at the Phase 5 gate on two S2 test-helper defects (T-D1, T-D2 below). The coordinator unblocked with option 1: the S2 test author fixed only the helpers in `14ec6702`, weakened no assertion, and logged it in `4da73cf3` and `f34f747c`.

At `f34f747c`, the feature pack, lint, both run_ci stages and Semgrep pass (final lines below). The branch is pushed to PR #1036, with the [WIP] title and the placeholder body. CI and static-policy were dispatched; static policy passed and CI was still running when this was written. Spec status is `implemented`, and the §6.2 Proof cells, the §17 row and the deviations list are filled.

`git diff 4da73cf3..HEAD -- tests` is empty.

## Progress (one line per committed row group; a resumed session continues from here)

- P1 `60c939b1` rows 1-8 (tools deleted/restored). `2c39aa72` rows 9-17 + P1 parts of 21, 31, 35, 38, 41, 45. `cb88b9df` row 18. Import OK, INV-23 holds, non-feature suite green. Lint: only S009 357/350, all 7 in unimported old grok/cli.py, grok/wire.py, muse/launcher.py, muse/wire.py, opencode/wire.py (they import deleted records); cleared by P3-P6 rewrites.
- P2 `3555279c` rows 19-31 (one commit). Records/runner/CliArgv tests green except the S2 helper defect T-D2 (runner test `invocation()` positional `argv` collides with `**{"argv": ...}`); the same checks pass in a scratch replica. Lint: only S009 376/350, all 26 in the old harness modules still to be rewritten.
- P3 `4c214907` rows 32-35 (factory, launcher, skills, hostkit exports). Error/launcher/skills tests green through the scratch shim. Lint: only S009 434/350, all in the old opencode/muse modules and the not-yet-rewritten grok modules.
- P4 `8d6e643c` rows 36-38 (Grok). Grok tests through the shim: 117 passed, 1 failed = S2 defect T-D1 (`call` fixture spreads `config` as a mapping, so a wrong-type config never reaches the function). Lint: only S009 395/350 = exactly the 45 findings of the old muse/launcher.py, muse/wire.py, opencode/wire.py; Grok and hostkit add none. INV-15 policy check ok.
- P5 `0c222707` rows 39-41 (opencode). opencode tests through the shim: 114 passed, 1 failed = T-D1. Lint: only S009 383/350 = exactly the 33 findings of the old muse/launcher.py and muse/wire.py. Constants gained OPENCODE_ERROR_EVENT_TEXT / OPENCODE_ERROR_EVENT_STATUS_TEXT (row 23 "every template a harness module needs"). INV-15 policy check ok.
- P6 `d5731e60` rows 42-45 (Muse, incl. WSL). Whole feature pack through the shim: 389 passed, 2 skipped (POSIX-only), 6 failed = T-D1 x3, T-D2, plus 2 that need P7 exports (surface, acceptance snippet). Full lint: SDK-LINT PASS, S009 350/350. INV-15 policy check ok.
- P7 `57b70d41` row 46 (exports), `e7275b4d` rows 47-49 (READMEs, REPO_MAP). Feature pack without the shim: 391 passed, 2 skipped (POSIX-only), 4 failed = T-D1 x3 + T-D2 (S2 test-helper defects). Full lint: SDK-LINT PASS.
- Phase 4 `554f8b66` (row 23 prune): NATIVE_WSL_LIST_ENCODING had no reader once list_distros drops NULs instead of re-decoding; removed. Every other constant in vidbyte/lib/constants/native_threads.py has a reader (the three *_TESTED_VERSION are read by NATIVE_TESTED_VERSIONS).
- Blocked here (report `4c072c1c`); S2 fixed T-D1/T-D2 in `14ec6702` (S2_HEAD `4da73cf3`).
- Phase 5 at `f34f747c`: whole gate re-run (see Gates).
- Phase 6: pushed `9071d2af..f34f747c`, then edited PR #1036 (title and placeholder body). Status commit `622dabd9` pushed. Dispatched CI run 38754831930 and static-policy run 38754836335, both on `622dabd9`.
- Phase 7: proof commit `c437c0d9` (§6.2 AC-18/AC-20 Proof cells, §17 S3 row, implementation deviations), then this report.

## Commits

| SHA | Rows | Message head |
|---|---|---|
| `60c939b1` | 1-8 | refactor(tools): remove the native host tools and restore main's tools files [W-8; FR-13, AC-13] |
| `2c39aa72` | 9-17 (+ P1 cuts of 21, 31, 35, 38, 41, 45, 46) | refactor(harnesses): remove the native hosts, backends, peers and their records [W-8, W-10; FR-13, AC-13] |
| `cb88b9df` | 18 | docs(spec): remove the superseded native-grok-opencode-meta-hosts design record [W-8; FR-13, AC-13] |
| `3555279c` | 19-31 | refactor(lib): add the harness thread records, enums, constants, error and CliArgv [W-4, W-5, W-7, W-10; ...] |
| `4c214907` | 32-35 | feat(harnesses): add the shared error factory, launcher resolution and skills folders [W-4, W-6, W-7; ...] |
| `8d6e643c` | 36-38 | feat(harnesses): run, continue and fork Grok Build threads headless with the caller's key [W-1; ...] |
| `0c222707` | 39-41 | feat(harnesses): run, continue and fork opencode threads headless with the caller's key [W-2; ...] |
| `d5731e60` | 42-45 | feat(harnesses): run, continue and fork Muse Code threads headless with the caller's key [W-3; ...] |
| `57b70d41` | 46 | feat(harnesses): export the nine harness thread functions from vidbyte.harnesses.native [FR-1, FR-17; INV-1, INV-23] |
| `e7275b4d` | 47-49 | docs(harnesses): describe the harness thread functions in the READMEs and the repo map [W-9] |
| `554f8b66` | 23 (prune) | refactor(lib): drop the native-thread constant nothing reads [W-7; FR-14, AC-14] |
| `4c072c1c` | — | docs(spec): record the S3 implementer report for harness-thread-functions |
| `622dabd9` | — | docs(spec): record implementation status for harness-thread-functions |
| `c437c0d9` | — | docs(spec): record implementation proof for harness-thread-functions |

Not mine, between them: `14ec6702` (S2 test-helper fix), `4da73cf3` and `f34f747c` (S2 report line, pipeline state).

## Data flow as built

caller → `<Harness>Threads.<verb>_<harness>_thread` → `_call` (one guarded try: `CancelledError` and `NativeThreadError` pass through, `ConfigurationError` → `configuration.invalid_argument` naming the argument, anything else → `runtime.error` naming only the class) → `NativeThreadRequest` + config record (`require_instance`, field `config`) → `<Harness>ThreadRun.execute`:

- **Grok**: `NativeLauncher.resolve` (command, PATH, `~/.grok/bin/grok[.exe]`) → `to_thread(_prepare_home)` (`~/.vidbyte/grok-homes/<sha256[:16]>`, `NativeSkillFolders.replace`) → `register_secret(key)` → `CliRunner().run(CliInvocation(JOINED argv, {XAI_API_KEY, GROK_CODE_XAI_API_KEY, GROK_HOME, GROK_DISABLE_AUTOUPDATER}, timeout, GROK_CLI_MAX_OUTPUT_BYTES, cwd=workspace))` → launch failure → `GrokWire.read`.
- **opencode**: `NativeLauncher.resolve` (no fallback) → `OpencodeWire.config_content` → `register_secret(key)`, `register_secret(config)` → `CliRunner().run(... JOINED argv `run --format=json --dir --model [--agent] [--variant] [--session] [--fork]`, {OPENCODE_CONFIG_CONTENT, OPENCODE_DISABLE_AUTOUPDATE}, stdin_text=prompt, cwd=workspace, NATIVE_PROCESS_MAX_OUTPUT_BYTES)` → launch failure → `OpencodeWire.read` (first `sessionID` found before the runner checks).
- **Muse**: `MuseLauncher(config, errors).resolve` (command, `wsl.exe -d <distro> -e <muse_path>`, PATH off win32; `wsl_unavailable` otherwise) → `visible_path(workspace)` (UNC refused naming workspace before any write) → `register_secret(key)` → `to_thread(_prepare_config)` (`tempfile.mkdtemp()`, skills to `muse/skills`) → try: mark; overlay {MUSE_NO_AUTO_UPDATE, XDG_CONFIG_HOME, MUSE_AUTH_PATH (never created)}; continue/fork: `_run(serve)` with `env_remove=(META_API_KEY,)`, `NATIVE_CONTROL_TIMEOUT_SECONDS`, MSP batch on stdin → `MuseWire.read_answer` (returns the id exec runs on); `_run(exec)` with META_API_KEY added → `MuseExecOutput.read`; `_run` reaps on timeout/cancel (WSL), maps OS launch failures and WSL markers (distro listing via `wsl.exe -l -q`) → finally `to_thread(shutil.rmtree, ignore_errors=True)`.

## §12.3 rows

All 49 rows done: 1-8 ✓, 9-17 ✓, 18 ✓, 19-31 ✓, 32-35 ✓, 36 ✓, 37 ✓, 38 ✓, 39 ✓, 40 ✓, 41 ✓, 42 ✓, 43 ✓, 44 ✓, 45 ✓, 46 ✓, 47 ✓, 48 ✓, 49 ✓ (see the deviations for how 37, 40, 42, 43 and 44 were shaped).

## Deviations (spec r4 → as built)

1. `NativeThreadRequest.workspace` is annotated `Path | str` and `skills` `Sequence[str | Path]` (§8.5 shows `Path` / `tuple[Path, ...]`). Forced by lint S009 (mypy ratchet, allowance 350): the public functions take `str | Path` and pass it in. Follows the `vidbyte.lib.dataclasses.coding` precedent (`root_dir: Path | str`); after `__post_init__` the values are always the resolved `Path` / tuple of `Path` (class docstring says so). Readers wrap with `Path(...)` where a `Path` is required.
2. `skills` items go through `to_tuple(item_type=object)` then `to_path` per item (spec: `item_type=(str, Path)`), forced by the S2 test that a non-path item is refused naming `skills[0]`.
3. `NativeErrorFactory.from_launch_failure(..., *, request, thread_id=None)` and `NativeLauncher.resolve(..., request=...)` take the request (needed for the INV-5 workspace sentence).
4. `GrokWire.read`, `OpencodeWire.read`, `MuseWire.read_answer` and `MuseExecOutput.read` take `timeout_seconds` (the observation names the seconds waited); `MuseExecOutput.read` also takes `thread_id` (the id exec ran on: caller's or the fork's new id).
5. The OS launch-failure check (`CliOutcome.launch_failure`) sits in each flow (`execute` / `MuseThreadRun._run`), not in the wire readers (rows 37, 43), because it needs the launcher program.
6. WSL launch-failure markers are mapped by `MuseLauncher.launch_failure` (row 42) for both serve and exec, not by `MuseExecOutput.read` (row 43), because naming the distros needs the async `wsl.exe -l -q`.
7. `MuseWire.read_answer` returns `str` (the thread id exec runs on) instead of `Mapping[str, object]`; the fork checks (missing id, id equal to source) live there as row 43 says.
8. `MuseLauncher.workspace_root` became `visible_path(path)` because it now maps both the workspace and the temp config folder.
9. `NativeErrorFactory.scrub` keeps the last `NATIVE_VENDOR_MESSAGE_MAX_CHARS` (rows 37/43 say "stderr tail").
10. Constants added beyond the row 23 list, each with a reader: `NATIVE_FIELD_DETAIL_KEY`, `NATIVE_UNNAMED_ARGUMENT`, `NATIVE_CONFIG_ARGUMENT`, `NATIVE_WORKSPACE_ARGUMENT`, `MUSE_WSL_WORKSPACE_RULE`, `MUSE_WINDOWS_DRIVE_PATTERN`, `NATIVE_WINDOWS_ROOT`, `OPENCODE_ERROR_EVENT_TEXT`, `OPENCODE_ERROR_EVENT_STATUS_TEXT`, `MUSE_SESSION_STREAM_MEMBER`, `MUSE_TERMINAL_RECORD_MEMBER`, `MUSE_FORK_SESSION_MEMBER`. `GROK_HOME_FAILURE_DETAIL` and `MUSE_CONFIG_FAILURE_DETAIL` include `strerror`.
11. The serve batch ends every frame with a newline (spec: "joined by NATIVE_LINE_SEPARATOR"), so the last frame is a complete line before EOF.
12. Interim S009 counts above the allowance at P1-P5 commits (357, 376, 434, 395, 383), forced by the phase plan: all findings were in the old, unimported harness modules that P4-P6 rewrote. From P6 on, S009 is 350/350.

## Files outside §12.3

None. `vidbyte/lib/errors/__init__.py` (one import line and one `__all__` line) is row 29's wiring. Its I001 import-order finding exists on origin/main too (checked on main's blob), so I did not reorder the file.

## Budget (§8.4)

- 24 added Python files vs origin/main (allowed 24): 15 under `vidbyte/harnesses/native/` (`__init__`, grok/{__init__, threads, wire}, hostkit/{__init__, errors, launcher, skills}, opencode/{__init__, threads, wire}, muse/{__init__, launcher, threads, wire}) and 9 under `vidbyte/lib/` (constants/native_threads, dataclasses/{native_threads, process, validation}, enums/{native_threads, process}, process/{__init__, argv, runner}).
- Classes exactly as §8.4: the 17 new (GrokThreads, GrokThreadRun, OpencodeThreads, OpencodeThreadRun, MuseThreads, MuseThreadRun, MuseExecOutput, NativeLauncher, NativeSkillFolders, CliArgv, CliOption, NativeThreadRequest, three configs, NativeThreadResult, NativeThreadError) plus the kept list; 12 new enums plus the kept 3 and ProcessLaunchFailure. Largest module: constants 418 lines.

## Gates (final lines, at `f34f747c` after the S2 helper fix)

- Feature pack, `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads`:
  `395 passed, 2 skipped in 32.01s`. The skips are POSIX-only:
  - `test_harness_threads_launcher.py:62`: Muse is looked up on PATH only outside win32.
  - `test_harness_threads_runner.py:157`: the execute permission bit.
- Whole suite, `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests` (first run):
  ```
  FAILED tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport
  1 failed, 5567 passed, 16 skipped, 1 warning in 87.06s (0:01:27)
  ```
  This is a timing flake in main's code. `vidbyte/tools/mcp/transport.py` and `tests/test_mcp_stdio_transport.py` are byte-identical to origin/main, because row W-8 restored main's transport. The test passed 3/3 alone (`1 passed in 0.74s`) and passed again inside the source-stage suite below.
  - Where it fails: test line 385, where `request("second")` hits its 5 s timeout. The cancel itself worked.
  - Likely cause: under load, the 0.05 s sleep lets the cancel land before `first` reaches the child. The child then reads `second` as its first line and ignores it.
- `python lint/run.py`:
  ```
  S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

  SDK-LINT: PASS
  ```
  S009 350/350, S051 259/259. These ratchets improved but were not re-baselined, because lint/ is off limits: A002 703→586, C011 2→1, C012 24→23, S001 59→56, S010 5→0, S025 263→261, S061 6→5.
- Ruff I001 on the 34 changed `.py` files has one finding, `vidbyte/lib/errors/__init__.py:22:1`. It is pre-existing: origin/main's copy of the file gives the same finding.
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` passes the bytecode check, lint (`SDK-LINT: PASS`) and compileall, plus `context write-path integrity: ok`, `context primitive introductions: ok` and `reasoning trace contracts: ok (182 tools, 55 shapes)`. It ends:
  ```
  ================= 5568 passed, 16 skipped in 85.95s (0:01:25) =================
  CI passed.
  ```
- `python scripts/run_ci.py --stage package` (PYTHONPATH unset):
  ```
  No broken requirements found.
  Installed vidbyte-sdk 0.2.1 passed smoke checks.
  CI passed.
  ```
- Semgrep 1.170.1 (scratch venv, mcp 1.23.3, venv Scripts first on PATH):
  - `semgrep --test ...` → `1/1: ✓ All tests passed`
  - `semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` → `Ran 1 rule on 958 files: 0 findings.`
- `PYTHONPATH=$(pwd) python -c "import vidbyte, vidbyte.harnesses.native"` → ok.
- `git diff 4da73cf3..HEAD -- tests` is empty (0 lines).
- INV-15 static policy: `test_harness_threads_static_policy.py` passes in the pack.

## Push, PR and CI

- `git push origin feat/native-grok-opencode-meta-hosts` → `9071d2af..f34f747c`, then `f34f747c..622dabd9` (fast-forward, no force).
- `gh pr edit 1036` set the title `[WIP] feat: Harness thread functions: run, continue and fork Grok, opencode and Muse threads with the caller's API key` and the placeholder body. `gh pr view` shows `isDraft=false`, unchanged, because the brief rules out a draft toggle.
- Dispatched on `622dabd9`:
  - CI https://github.com/cerredz/Vidbyte-SDK/actions/runs/38754831930: in progress when written.
  - Static policy https://github.com/cerredz/Vidbyte-SDK/actions/runs/38754836335: completed, success.

  Read the results through the check-runs API.

## The S2 test defects (resolved in `14ec6702`)

- **T-D1**, `tests/features/harness_threads/test_harness_threads_arguments.py:172-175` with `conftest.py:254-264`: the test calls `refuse(harness, "config", config=<OtherHarnessConfig>())` and `refuse(..., config={"timeout_seconds": 5})`. `refuse` passes `config=` to the `call` fixture, whose own `config: dict | None` parameter means "extra config fields" and is spread with `**(config or {})` into a valid config record. A record therefore raises `TypeError: 'GrokThreadConfig' object is not a mapping` inside the fixture, and the mapping becomes a valid `timeout_seconds=5` config, so no refusal can happen. The implementation does refuse both (`RecordFieldConverter.require_instance(config, "config", <Config>)` → `configuration.invalid_argument` naming `config`).
- **T-D2**, `tests/features/harness_threads/test_harness_threads_runner.py:42-45, 71`: the helper `invocation(api, argv, **fields)` takes `argv` positionally, and the test calls it with `**{"argv": ()}`, which raises `TypeError: invocation() got multiple values for argument 'argv'` before `CliInvocation` runs. A scratch replica of the same nine checks against `CliInvocation` passes (each raises `ConfigurationError` naming the field).

Minimal fixes S2 could make: T-D2 → make `argv` positional-only (`def invocation(api, argv, /, **fields)`). T-D1 → give `call` a way to pass a config value as-is (for example a separate keyword such as `config_value=` that `refuse` uses), or have the test call the function directly.

## Tricky parts

- mypy (S009) is a count ratchet over the whole package; widening the request annotations was the only honest way to pass `str | Path` in without a cast.
- A007 flags numeric literals near names like `request`, `status`, `limit`; use unpacking (`program, *_ = launcher`, `*_earlier, last = texts`) rather than literal indexes.
- The Semgrep venv's `semgrep.exe` re-launches through `python` on PATH; with the global Python first it imports global mcp 2.x and crashes. Put the venv's Scripts folder first on PATH.
- `wsl.exe -l -q` output is UTF-16-LE and CliRunner decodes UTF-8 with replacement; dropping NUL characters recovers ASCII distro names.
- opencode's `error` events may come with exit 0; they are still run_failed (or key_rejected), and "Session not found" is checked before run_failed (INV-6 order).
- `tests/test_mcp_stdio_transport.py::...::test_cancelled_waiter_does_not_break_transport` can flake under full-suite load. The test and the transport are main's, and the old branch's R-25 transport changes left with row W-8. If CI shows it, compare with a main run before blaming this PR.
