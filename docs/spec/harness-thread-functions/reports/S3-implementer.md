# S3 Implementer report — harness-thread-functions (r4)

Start HEAD `9071d2af` on `feat/native-grok-opencode-meta-hosts`; S2_HEAD `8e5e65ec`; origin/main `179d8adc`. Final local HEAD `554f8b66` (not pushed; see Status).

## Status

**BLOCKED at the Phase 5 gate.** All 49 rows of §12.3 are implemented and committed. Lint, compileall, the three check scripts, the package stage and Semgrep pass. The whole suite has 4 failures, all inside two S2 test helpers (T-D1, T-D2 below), which no implementation can satisfy and which I may not edit (test files are ask-first). Nothing was pushed, PR #1036 was not touched, CI was not dispatched, and the spec frontmatter, §6.2 Proof cells and §17 were not edited (Phases 6 and 7 wait for the push).

## Progress (one line per committed row group; a resumed session continues from here)

- P1 `60c939b1` rows 1-8 (tools deleted/restored). `2c39aa72` rows 9-17 + P1 parts of 21, 31, 35, 38, 41, 45. `cb88b9df` row 18. Import OK, INV-23 holds, non-feature suite green. Lint: only S009 357/350, all 7 in unimported old grok/cli.py, grok/wire.py, muse/launcher.py, muse/wire.py, opencode/wire.py (they import deleted records); cleared by P3-P6 rewrites.
- P2 `3555279c` rows 19-31 (one commit). Records/runner/CliArgv tests green except the S2 helper defect T-D2 (runner test `invocation()` positional `argv` collides with `**{"argv": ...}`); the same checks pass in a scratch replica. Lint: only S009 376/350, all 26 in the old harness modules still to be rewritten.
- P3 `4c214907` rows 32-35 (factory, launcher, skills, hostkit exports). Error/launcher/skills tests green through the scratch shim. Lint: only S009 434/350, all in the old opencode/muse modules and the not-yet-rewritten grok modules.
- P4 `8d6e643c` rows 36-38 (Grok). Grok tests through the shim: 117 passed, 1 failed = S2 defect T-D1 (`call` fixture spreads `config` as a mapping, so a wrong-type config never reaches the function). Lint: only S009 395/350 = exactly the 45 findings of the old muse/launcher.py, muse/wire.py, opencode/wire.py; Grok and hostkit add none. INV-15 policy check ok.
- P5 `0c222707` rows 39-41 (opencode). opencode tests through the shim: 114 passed, 1 failed = T-D1. Lint: only S009 383/350 = exactly the 33 findings of the old muse/launcher.py and muse/wire.py. Constants gained OPENCODE_ERROR_EVENT_TEXT / OPENCODE_ERROR_EVENT_STATUS_TEXT (row 23 "every template a harness module needs"). INV-15 policy check ok.
- P6 `d5731e60` rows 42-45 (Muse, incl. WSL). Whole feature pack through the shim: 389 passed, 2 skipped (POSIX-only), 6 failed = T-D1 x3, T-D2, plus 2 that need P7 exports (surface, acceptance snippet). Full lint: SDK-LINT PASS, S009 350/350. INV-15 policy check ok.
- P7 `57b70d41` row 46 (exports), `e7275b4d` rows 47-49 (READMEs, REPO_MAP). Feature pack without the shim: 391 passed, 2 skipped (POSIX-only), 4 failed = T-D1 x3 + T-D2 (S2 test-helper defects). Full lint: SDK-LINT PASS.
- Phase 4 `554f8b66` (row 23 prune): NATIVE_WSL_LIST_ENCODING had no reader once list_distros drops NULs instead of re-decoding; removed. Every other constant in vidbyte/lib/constants/native_threads.py has a reader (the three *_TESTED_VERSION are read by NATIVE_TESTED_VERSIONS).

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

## Gates (final lines)

- Feature pack, `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads`:
  `4 failed, 391 passed, 2 skipped in 40.16s`. Skips (POSIX-only): `test_harness_threads_launcher.py:62` (Muse looked up on PATH only outside win32) and `test_harness_threads_runner.py:157` (execute permission bit). The 4 failures are T-D1 x3 and T-D2.
- Whole suite, `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests`:
  ```
  FAILED tests/features/harness_threads/test_harness_threads_arguments.py::test_config_of_the_wrong_type_is_refused[muse]
  FAILED tests/features/harness_threads/test_harness_threads_runner.py::test_cli_invocation_validates_and_hides_the_overlay_and_stdin
  4 failed, 5564 passed, 16 skipped in 84.89s (0:01:24)
  ```
  No failure outside the feature pack, so no comparison with 179d8adc is needed.
- `python lint/run.py` (inside the source stage, after the last commit):
  ```
  S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

  SDK-LINT: PASS
  ```
  S009 350/350, S051 259/259. IMPROVED, not re-baselined (lint/ is off limits): A002 703→586, C011 2→1, C012 24→23, S001 59→56, S010 5→0, S025 263→261, S061 6→5.
- Ruff I001 on every changed `vidbyte/*.py`: clean except the pre-existing `vidbyte/lib/errors/__init__.py` finding (also on main).
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`: bytecode check, lint, compileall, `context write-path integrity: ok`, `context primitive introductions: ok`, `reasoning trace contracts: ok (182 tools, 55 shapes)` pass; pytest fails:
  ```
  ============ 4 failed, 5564 passed, 16 skipped in 86.96s (0:01:26) ============
  CI failed: Command failed with exit code 1: C:\Users\422mi\AppData\Local\Programs\Python\Python311\python.exe -m pytest (cwd=C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-harness-thread-functions).
  ```
- `python scripts/run_ci.py --stage package` (PYTHONPATH unset):
  ```
  No broken requirements found.
  Installed vidbyte-sdk 0.2.1 passed smoke checks.
  CI passed.
  ```
- Semgrep 1.170.1 (scratch venv, mcp 1.23.3, venv Scripts first on PATH): `semgrep --test ...` → `1/1: ✓ All tests passed`; `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` → `Ran 1 rule on 958 files: 0 findings.`
- `git diff 8e5e65ec..HEAD -- tests` is empty (0 lines).
- INV-15 static policy: `test_harness_threads_static_policy.py` passes in the pack.

## The S2 test defects (why the gate cannot pass)

- **T-D1**, `tests/features/harness_threads/test_harness_threads_arguments.py:172-175` with `conftest.py:254-264`: the test calls `refuse(harness, "config", config=<OtherHarnessConfig>())` and `refuse(..., config={"timeout_seconds": 5})`. `refuse` passes `config=` to the `call` fixture, whose own `config: dict | None` parameter means "extra config fields" and is spread with `**(config or {})` into a valid config record. A record therefore raises `TypeError: 'GrokThreadConfig' object is not a mapping` inside the fixture, and the mapping becomes a valid `timeout_seconds=5` config, so no refusal can happen. The implementation does refuse both (`RecordFieldConverter.require_instance(config, "config", <Config>)` → `configuration.invalid_argument` naming `config`).
- **T-D2**, `tests/features/harness_threads/test_harness_threads_runner.py:42-45, 71`: the helper `invocation(api, argv, **fields)` takes `argv` positionally, and the test calls it with `**{"argv": ()}`, which raises `TypeError: invocation() got multiple values for argument 'argv'` before `CliInvocation` runs. A scratch replica of the same nine checks against `CliInvocation` passes (each raises `ConfigurationError` naming the field).

Minimal fixes S2 could make: T-D2 → make `argv` positional-only (`def invocation(api, argv, /, **fields)`). T-D1 → give `call` a way to pass a config value as-is (for example a separate keyword such as `config_value=` that `refuse` uses), or have the test call the function directly.

## Tricky parts

- mypy (S009) is a count ratchet over the whole package; widening the request annotations was the only honest way to pass `str | Path` in without a cast.
- A007 flags numeric literals near names like `request`, `status`, `limit`; use unpacking (`program, *_ = launcher`, `*_earlier, last = texts`) rather than literal indexes.
- The Semgrep venv's `semgrep.exe` re-launches through `python` on PATH; with the global Python first it imports global mcp 2.x and crashes. Put the venv's Scripts folder first on PATH.
- `wsl.exe -l -q` output is UTF-16-LE and CliRunner decodes UTF-8 with replacement; dropping NUL characters recovers ASCII distro names.
- opencode's `error` events may come with exit 0; they are still run_failed (or key_rejected), and "Session not found" is checked before run_failed (INV-6 order).
