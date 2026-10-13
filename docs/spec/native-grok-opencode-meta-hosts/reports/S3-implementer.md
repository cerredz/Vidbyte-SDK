# S3 implementer report: native-grok-opencode-meta-hosts

Status: **BLOCKED (third stop)**. All 68 rows of §12.3 are built and committed. Of the 1635 S2 tests, 4 always fail and up to 3 more fail on some runs, so each run shows 4 to 7 failures:

- **Three test defects:** D-4 contradicts itself, D-5 is flaky because of frame order, and D-6 has message ids off by one.
- **One implementation gap:** EC-95. Its fix needs an addition to the §8.5 interface, which the briefing lists as ask-first.

Nothing was pushed. No PR was opened and no CI was dispatched. The worktree is still in place, and the working tree is clean apart from this report.

| Item | Value |
|---|---|
| Branch | `feat/native-grok-opencode-meta-hosts` |
| Base of this round | `c7da3c2b` (spec r5 `254ebc53`, test fix `762b68e7`) |
| HEAD | `29c0989d`, before this report's own commit |
| Test baseline | `762b68e7`. `git diff 762b68e7..HEAD -- tests/ \| wc -l` gives `0` |

## 1. Commits

`git log origin/main..HEAD --oneline`, implementation commits only. Spec, test and report commits by other stages are left out.

| SHA | Subject | §12.3 rows |
|---|---|---|
| `29c0989d` | fix(harnesses): match the §8.5 host signatures for optional parameters [W-8, W-10; FR-1, FR-3] | 30, 41 |
| `eebf3582` | refactor(harnesses): drop the unused NativeTurnTable.live_handles [W-6] | 27 |
| `5fae02ba` | fix(harnesses): map a steer's -32030 to turn_not_found only for a finished turn [W-10; EC-115, EC-102] | 41 |
| `66d781cb` | fix(harnesses): send the SDK version in Grok's ACP clientInfo [W-8; FR-1] | 32 |
| `383c1092` | fix(harnesses): give GrokHost.__aenter__ the one-try error shape [W-8; EC-5, INV-1, INV-2] | 30 |
| `a4ea7b70` | docs: index the native hosts, process helpers and transport options [W-13] | 21, 23, 47, 67, 68 |
| `f163337e` | feat(tools): add GrokTools, OpencodeTools and MuseTools with read_only views [W-12; FR-5, AC-15, AC-18, T-5] | 62, 63, 64, 66 |
| `5f1826e5` | feat(tools): add the 40 Grok, opencode and Muse tools [W-11; FR-5, INV-7, AC-15, EC-138 to EC-146] | 49-58 |
| `0c9c951a` | feat(harnesses): add MuseHost over MSP, through WSL on Windows [W-10; FR-3, FR-19, AC-10] | 40-44 |
| `e22d71f9` | feat(harnesses): add OpencodeHost over an owned or attached opencode server [W-9; FR-2, FR-18, AC-9] | 34-39 |
| `72c3f83b` | feat(harnesses): add GrokHost and run_grok_once over ACP and the grok CLI [W-8; FR-1, FR-17, AC-1, AC-6, AC-7, AC-8, AC-11, AC-12] | 29-33 |
| `304b7341` | fix(harnesses): re-raise cancellation explicitly in the async backend functions [W-7; INV-2, EC-4] | 46 |
| `36d25ba0` | feat(tools): add HarnessBackendTools and export it from vidbyte.tools.toolsets [W-12; FR-5, AC-15, AC-18] | 65, 66 |
| `2fafe63e` | feat(tools): add the native host tool base and the three backend tools [W-11; FR-5, INV-7, EC-138 to EC-143, EC-147] | 48, 59-61 |
| `a09959c7` | feat(harnesses): add the GLM and DeepSeek backend functions [W-7; FR-4, AC-13, AC-14, EC-122 to EC-137] | 45, 46; also touches 6, 28 |
| `b9b7cfd6` | fix(harnesses): name the refused argument in invalid_argument errors [W-1, W-6; EC-1, EC-138] | 6, 13, 26 |
| `e9ff2613` | fix(lib): name continue_muse_session in the muse.budget_exhausted next step [W-1; EC-117, AC-17] | 13 |
| `f1567ae9` | feat(harnesses): add native hostkit shared by the Grok, opencode and Muse hosts [W-6; INV-6, EC-5, EC-9, EC-149] | 25-28 |
| `eb47d589` | feat(mcp): extend McpStdioTransport for ACP and MSP peers [W-5; FR-15, EC-10, INV-18] | 22 |
| `6692ee57` | fix(lib): name operational bounds in native records and process helpers [W-2, W-4; INV-5, FR-16] | 8, 9, 10, 13, 17, 18 |
| `c3bd8c6f` | feat(harnesses): add the fixed native harness package marker [W-14; AC-16, INV-19] | 24 |
| `b137305e` | feat(lib): add canonical CLI runner, managed process and tree stopper [W-4; FR-16, INV-4] | 16-18 |
| `ba78a4da` | feat(errors): add NativeHostError [W-3; INV-1, INV-8] | 19, 20 |
| `49eae8cc` | feat(lib): add native host records and backend profiles [W-2; FR-4, EC-23, ...] | 7-12, 14, 15 |
| `26f897e9` | feat(lib): add native host enums, failure codes, constants and record validator [W-1; INV-5, INV-8, AC-17] | 1-6, 13 |

## 2. What was built, in data-flow order

1. **Closed sets.** Enums, the 53 FailureCodes, and the constants, including `NATIVE_HOST_NEXT_STEPS`. Files: `vidbyte/lib/enums/{native_hosts,harness_backends,process}.py`, `failure.py` and `vidbyte/lib/constants/native_hosts.py`.
2. **Validation.** `RecordFieldValidator` and `RecordFieldConverter` raise `ConfigurationError` with `details["field"]`. File: `vidbyte/lib/dataclasses/validation.py`.
3. **Records.** The 66 records are frozen and slotted, and each validates in `__post_init__`. Files: `vidbyte/lib/dataclasses/{native_hosts,grok,opencode,muse,harness_backends,process}.py`. The backend profile config is in `vidbyte/lib/configs/harness_backends.py`.
4. **Error type.** `NativeHostError`, in `vidbyte/lib/errors/base.py`.
5. **Process helpers.** `CliRunner`, `ManagedProcess` and `ProcessStopper`, in `vidbyte/lib/process/{runner,managed}.py`.
6. **Transport extension (D-3).** `vidbyte/tools/mcp/transport.py` gains `on_message`, `send_request`, `notify`, `respond`, per-call timeouts, `exit_grace_seconds` and `stop_process_tree`.
7. **Package marker.** `vidbyte/harnesses/native/__init__.py`, with fixed bytes (INV-19).
8. **Shared plumbing (D-22).** `vidbyte/harnesses/native/hostkit/{errors,turns,peers}.py` holds `NativeErrorFactory`, `NativeTurnTable`, `NativePeer` and `NativeChildEnvironment`.
9. **Backends.** `vidbyte/harnesses/native/backends/profiles.py` holds the six `HarnessBackends` functions. `backends/__init__.py` binds them as module functions (D-16).
10. **Hosts.**
    - Grok: `GrokHost` in `vidbyte/harnesses/native/grok/host.py`, over `turn.py`, `wire.py` and `cli.py`.
    - opencode: `OpencodeHost` in `opencode/host.py`, over `client.py`, `server.py`, `turn.py` and `wire.py`.
    - Muse: `MuseHost` in `muse/host.py`, over `launcher.py`, `turn.py` and `wire.py`.
11. **Tools.**
    - The base `NativeHostTool`, with `NativeToolArguments` and `NativeResultEncoder`, is in `vidbyte/tools/builtins/native_host_tool.py`.
    - The 43 tools are in `vidbyte/tools/builtins/{grok,opencode,muse,harness_backends}/`.
12. **Toolsets.** `GrokTools`, `OpencodeTools`, `MuseTools` and `HarnessBackendTools` are in `vidbyte/tools/toolsets/{grok,opencode,muse,harness_backends}.py`. `toolsets/__init__.py` exports them.
13. **Docs.** `REPO_MAP.md`, plus the READMEs of `vidbyte/lib`, `vidbyte/harnesses`, `vidbyte/tools` and `vidbyte/tools/mcp`.

## 3. Checklists

### §12.3: 68 of 68 rows

I compared `git diff --name-status $(git merge-base origin/main HEAD)..HEAD -- . ':!docs/' ':!tests/'` with the §12.3 table:

- 68 files changed: 56 added and 12 modified.
- The sorted lists match row for row and operation for operation; `diff` printed `ops match`.
- No file outside §12.3 was touched.

| Rows | Done |
|---|---|
| 1-20 (P1) | [x] |
| 22, 24-28 (P2) | [x] |
| 29-46 (P3) | [x] |
| 48-66 (P4) | [x] |
| 21, 23, 47, 67, 68 (P5) | [x] |

### §12.4 obligations

- [x] **A001 headers.** Lint passes. `native/__init__.py` is exempt.
- [x] **Records.** All 66 live in `lib/dataclasses/<domain>.py` with `frozen=True, slots=True`. A grep found no exceptions.
- [x] **Enums.** All 13 live in `lib/enums/<domain>.py` and are exported.
- [x] **Layering.** No `vidbyte/lib` module imports `harnesses`, `tools` or `agents` (checked by grep), and A006 passes.
- [x] **Narrated main functions, and helpers one level deep.**
- [x] **One try per public method.** A scratch AST check covered the 49 public methods of `GrokHost`, `OpencodeHost`, `MuseHost` and `HarnessBackends`.
  - Each has a try whose handlers run `CancelledError` (async methods only), `NativeHostError`, then `Exception`.
  - Most add a `ConfigurationError` handler before `Exception`; see deviation 1.
  - The check found that `GrokHost.__aenter__` had no try. `383c1092` fixed it.
  - The one exception is `list_harness_backends`; see tricky part 5.
- [x] **Errors.** Every error is built by `NativeErrorFactory`.
- [x] **Processes.** Every process start sits in try/finally. The INV-4 tests are green.
- [x] **Stdin.** No child inherits the caller's stdin.
- [x] **Peers.** Every peer is built with `stop_process_tree=True`.
- [x] **§6.3 codes and tokens.** The shared-contract tests pass: 43 passed.
- [x] **Numeric limits are constants.** A007 is at 255 against 255.
- [x] **Banned constructs.** No `asyncio.Lock`, no `TypedDict` and no async parameter named `timeout` (checked by grep and lint).
- [x] **S012 timeouts.** Every `.request(` call passes `timeout_seconds`.
- [x] **S025 and S062.** Descriptions meet both rules.
- [x] **No `str(exc)` or `repr(exc)`.** A grep finds it only in a header's "what not to do" note.
- [x] **S054** passes.
- [x] **Semgrep** is clean.
- [x] **AC-20 imports.** All seven modules import fresh: OK ×7.
- [x] **Export lists** were appended to, never reordered.
- [x] **INV-19 hash** matches.
- [ ] **`run_ci.py` passes.** The source stage fails only on the blocked tests (§4).

### §12.5 actions

- [x] Five README and REPO_MAP actions (`a4ea7b70`).
- [x] Four `__init__` export appends (rows 5, 15, 20 and 66).
- [x] No contract regeneration, no `pyproject.toml` change, no baseline change.
- [ ] The PR body stating §10. There is no PR while BLOCKED; the S6 PR description owns this.

### Phase 4 diff pass

I checked the diff for stubs, TODOs, suppressions, bare `pass` lines and code nothing references. I also compared all 88 §8.5 method signatures against `inspect.signature` with a scratch script. This turned up five problems, and each is fixed in its own commit:

1. `GrokHost.__aenter__` had no EC-5 try (`383c1092`).
2. Grok `clientInfo.version` was a literal `"0.2.1"`. It now reads `vidbyte.__version__` on each call, as `MuseWire` does (`66d781cb`).
3. `MuseHost._steer` mapped every -32030 to `turn_not_found`. EC-115 says that applies only when the turn has finished locally; EC-102 maps any other -32030 to `muse.api_error` (`5fae02ba`).
4. `NativeTurnTable.live_handles` had no caller and is not declared in §8.5 (`eebf3582`).
5. Seven `GrokHost` and `MuseHost` methods made their optional parameters keyword-only, where §8.5 declares them positional-or-keyword (`29c0989d`). The comparison now prints `compared=88 diffs=0`. The six backend functions and `run_grok_once` also match.

## 4. Gates, all at HEAD `29c0989d`

**Gate 1, the S2 packs.** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends`
```
FAILED tests/features/muse_host/test_muse_host_wire.py::test_fork_sends_a_cut_point_only_with_a_last_turn_id_and_never_a_top_level_one
FAILED tests/features/muse_host/test_muse_host_wsl.py::test_missing_in_distro_muse_is_not_installed[spawn-exit-127]
6 failed, 1610 passed, 19 skipped in 145.23s (0:02:25)
EXIT 1
```
- The six failures are D-5 (`test_list_grok_sessions_pages_with_the_workspace_cwd` and the Muse fork test), D-4, D-6 (two tests) and EC-95.
- 1610 + 6 + 19 = 1635. The 19 skips are platform guards.
- Because D-5 is flaky, a run fails 4 to 7 tests. At the three earlier HEADs of this round, gate 1 gave `5 failed, 1611 passed`.

**Gate 2a, the neighbour suites.** `PYTHONPATH=$(pwd) python -m pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py tests/features/coding_agent`
```
.........................                                                [100%]
445 passed, 12 skipped in 16.45s
EXIT 0
```

**Gate 2b, the full suite.** This is the pytest step of the source stage below: `python -m pytest` with `PYTHONPATH=$(pwd)`.
```
FAILED tests/features/opencode_host/test_opencode_host_acceptance.py::test_get_session_and_its_usage_totals
FAILED tests/features/opencode_host/test_opencode_host_acceptance.py::test_message_page_and_single_message
=========== 5 failed, 5567 passed, 32 skipped in 181.73s (0:03:01) ============
```
- The five failures are D-4, D-5 (`test_edit_permission_is_rejected_then_allowed_by_policy`), EC-95 and D-6 (two tests).
- No test outside the four S2 packs failed.

**Gate 3, lint.** `python lint/run.py`, as the first step of the source stage:
```
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
- A002 improved from 703 to 623. The baseline was not lowered, because `lint/` is off-limits.
- A007 is ratcheted at 255 against 255.

**Gate 4a, source stage.** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
- These steps passed: `SDK-LINT: PASS`, compileall, `context write-path integrity: ok`, `context primitive introductions: ok`, and `reasoning trace contracts: ok (182 tools, 55 shapes)`.
- The pytest step failed:
```
FAILED tests/features/opencode_host/test_opencode_host_acceptance.py::test_message_page_and_single_message
=========== 5 failed, 5567 passed, 32 skipped in 181.73s (0:03:01) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-native-grok-opencode-meta-hosts).
EXIT 1
```

**Gate 4b, package stage.** `python scripts/run_ci.py --stage package`, run without PYTHONPATH:
```
Installed vidbyte-sdk 0.2.1 passed smoke checks.
CI passed.
EXIT 0
```

**Gate 5, Semgrep.** I ran `git add -A`, then `semgrep.exe scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`.
```
 • Findings: 0 (0 blocking)
Ran 1 rule on 949 files: 0 findings.
EXIT 0
```
- **Environment note.** The venv's `semgrep.exe` finds `pysemgrep` on `PATH`. The global Python's copy of it fails because mcp 2.x is installed there (`No module named 'mcp.server.fastmcp'`).
- I ran it with `PATH="/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1/Scripts:$PATH"`. No repository change was needed.

**Final checks:**

| Check | Result |
|---|---|
| `git diff 762b68e7..HEAD -- tests/ \| wc -l` | `0` |
| INV-22 paths: `git diff --stat $(git merge-base origin/main HEAD)..HEAD -- <INV-22 paths> \| wc -l` | `0` |
| `git show HEAD:vidbyte/harnesses/native/__init__.py \| sha256sum` | `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a` |
| AC-20 (`python -c "import <m>"` for each of the 7 modules) | OK ×7 |

A diff against `origin/main` itself does show `vidbyte/mcp_server/server/handlers/tools_call.py`. That comes from main moving ahead (`2dace6e8`, #1007); this branch never touched the file.

## 5. Blocking items

### D-4: a Grok one-shot argv test contradicts itself

- **Test:** `tests/features/grok_host/test_grok_host_reads.py::test_one_shot_argv_carries_every_value_in_name_value_form`.
- **Spec:** T-2 and INV-9 (spec.md:242 and :1631), and the §6.3.3 argv `--single=<prompt>` (spec.md:463).
- **The contradiction:**
  - The prompt is `"--always-approve"`.
  - Line 182 asserts `"--single=--always-approve" in argv`. That is correct under T-2: the prompt stays inside `--single=`.
  - Line 191 then calls `assert_no_approve_everything(argv)`. That helper (lines 46-48) fails any argument where `arg == flag or arg.endswith("=" + flag)`, and `FORBIDDEN_ARGS` (line 24) holds `"--always-approve"`.
  - `--single=--always-approve` ends with `=--always-approve`, so no argv can pass both checks.
  - INV-9 is about approve-everything *settings*; a prompt is data.
- **Evidence:**
```
>       assert_no_approve_everything(argv)
>           assert not any(arg == flag or arg.endswith("=" + flag) for flag in FORBIDDEN_ARGS), argv
E           AssertionError: ['--output-format=json', '--permission-mode=acceptEdits', '--cwd=...', '--model=grok-4-heavy', '--reasoning-effort=high', '--allow=Read(docs/**)', ...]
```
- **Fix for S2:** in that file's `assert_no_approve_everything`, skip the suffix check for arguments that start with `--single=`. Keep the exact-match check, and keep lines 182-183 as they are.

### D-5: the fake peers' frames come back in PID order, not launch order (flaky)

- **Tests:**
  - `tests/features/grok_host/test_grok_host_turns.py::test_edit_permission_is_rejected_then_allowed_by_policy`
  - `tests/features/grok_host/test_grok_host_reads.py::test_list_grok_sessions_pages_with_the_workspace_cwd`
  - `tests/features/muse_host/test_muse_host_wire.py::test_fork_sends_a_cut_point_only_with_a_last_turn_id_and_never_a_top_level_one`
- **Spec:** D-2 (spec.md:865) gives each turn its own peer, plus a short-lived peer for each read. Each of these tests therefore talks to two processes in sequence.
- **Cause:**
  - Each fake process logs to `{role}-{os.getpid()}-{hex8}.jsonl` (`fake_grok_peer.py:43`, `fake_muse_peer.py:56`).
  - `GrokFake.records` and `MuseFake.records` read `sorted(self.log_dir.glob("*.jsonl"))` (`grok_host/conftest.py:115`, `muse_host/conftest.py:146`). That sorts by the PID string.
  - Windows PIDs are not monotonic, so in about half the runs the second peer's frames come first.
- **Evidence:**
  - Six runs of the three tests on HEAD: four gave `1 failed, 2 passed` and two gave `3 passed`.
  - I made a scratch pytest plugin, `-p d5_order_probe`, which was never committed. It only replaces `records` so that it reads the files in creation order (`st_ctime_ns`). With it, ten runs gave `3 passed` every time.
  - A dump from the probe shows the order directly: `peer-2024-...jsonl` has the earlier ctime and holds the reject frame; `peer-9344-...jsonl` holds the allow frame.
- **Fix for S2:** read the files in launch order. Either sort on a per-file birth stamp (for example a `"born": time.time_ns()` field in the first record, with the name as tie-break), or sort on a sequence number shared across processes.

### D-6: the opencode fixture's message ids are off by one

- **Tests:**
  - `tests/features/opencode_host/test_opencode_host_acceptance.py::test_get_session_and_its_usage_totals`
  - `tests/features/opencode_host/test_opencode_host_acceptance.py::test_message_page_and_single_message`
- **Spec:** AC-9 and the opencode read rows. The assertions check the fixture's own ids.
- **Cause:**
  - The fake's `add_session` uses `stamp = BASE_MS + next(self.ids) * 1000` (`opencode_host/conftest.py:177`). That consumes id 1.
  - So `KNOWN_SESSION`'s history is user message `msg_00000002`, part `prt_00000003` and reply `msg_00000004`.
  - The tests expect `KNOWN_USER_MESSAGE = "msg_00000001"` and `KNOWN_REPLY_MESSAGE = "msg_00000002"` (conftest.py:45-46 and test_opencode_host_acceptance.py:26-27).
- **Evidence:**
  - The failures read `AssertionError: assert ['msg_00000004'] == ['msg_00000002']` (test lines 342 and 367).
  - A scratch plugin, `-p d6_ids_probe` (never committed), sets only those two module constants, to `msg_00000002` and `msg_00000004`. With it the module gives `29 passed in 3.66s`.
- **Fix for S2:** either change the two constants, in the test module and in conftest, or stop `add_session` from drawing on `self.ids` for its timestamp.

**Combined check:** with both probes loaded, gate 1 gives `2 failed, 1614 passed, 19 skipped in 145.21s`. The two remaining failures are D-4 and EC-95.

### EC-95: the in-distro exit code 127 needs an addition to the interface

- **Test:** `tests/features/muse_host/test_muse_host_wsl.py::test_missing_in_distro_muse_is_not_installed[spawn-exit-127]`.
- **Spec:** EC-95 (spec.md:640): "In WSL mode, the process exits before answering, with exit code 127 or stderr containing `No such file or directory`". The test is correct against the spec.
- **Gap:**
  - `MuseLauncher.launch_failure(stderr, exit_code, ...)` already maps exit code 127 to `muse.not_installed`.
  - But the peer has no exit code to pass it. The §8.5 `NativePeer` (spec.md:1093-1106) has no `exit_code`, and `McpStdioTransport` drops the process when `close()` detaches it.
  - So `MuseHost._handshake` passes `None`, and the error stays `muse.process_exited`:
```
E       AssertionError: expected muse.not_installed, got muse.process_exited: The Muse Code process stopped before it answered.
```
- **Proposed diff.** It is 9 lines in 3 files. I applied it temporarily, ran the tests, and reverted it; the patch is saved outside the repo.
  - `vidbyte/tools/mcp/transport.py`:
    - `__init__` gains `self.returncode: int | None = None`;
    - `close()` gains `if process is not None: self.returncode = process.returncode` before `_detach_process_state()`.
  - `vidbyte/harnesses/native/hostkit/peers.py`: `@property def exit_code(self) -> int | None: return self._transport.returncode`.
  - `vidbyte/harnesses/native/muse/host.py:534`: pass `peer.exit_code` instead of `None`. `_handshake` already closes the peer before this call.
- **Result with the diff applied:** `pytest tests/features/muse_host tests/features/grok_host/test_grok_transport_extension.py tests/test_mcp_stdio_transport.py` gives `1 failed, 527 passed, 7 skipped`. EC-95 passes, and the one failure is the D-5 Muse fork test.
- **Why I did not apply it:**
  - It adds a public member to two §8.5 interfaces, `NativePeer` and the D-3 transport additions.
  - It moves the transport diff from +156/-8 to +159/-8, past D-3's re-evaluation trigger of "about 160 changed lines".
  - The briefing makes both kinds of change ask-first.

## 6. Deviations

These were implemented where the spec is silent or underspecified.

1. **The invalid-argument next step names the argument.**
   - EC-1 and EC-138 make the token the argument's name. The default text for `configuration.invalid_argument`, "Fix the argument named in the message and call again.", contains no name.
   - I added `NATIVE_INVALID_ARGUMENT_NEXT_STEP = "Fix the {field} argument and call again."` to `vidbyte/lib/constants/native_hosts.py`.
   - Every `ConfigurationError` the validator raises now carries `details={"field": ...}`. Hosts (`NativeErrorFactory.from_configuration_error`) and tools (`NativeHostTool._refusal`) use it to name the argument.
   - Host methods therefore catch `ConfigurationError` between `NativeHostError` and `Exception`. Without that handler, a record-construction error would become `runtime.error`.
2. **`RecordFieldConverter.to_enum` and `to_decimal`.**
   - Tool arguments and wire bodies arrive as JSON. `to_enum` accepts a member or its exact value.
   - `to_decimal` accepts a decimal string and refuses a JSON number, so the DeepSeek balance keeps its exact digits.
3. **The backend error factory is labelled `NativeHarness.CLAUDE_CODE`.** Backend errors use explicit `backend.*` codes. The label would only show on process or transport failures, and the backends never raise those.
4. **`from_unexpected` names no host.** The message is `"<operation> failed with an unexpected <ErrorType>."`, and `context["error_type"]` holds only the class name (EC-5).
5. **The Claude model slots** (`ANTHROPIC_DEFAULT_*_MODEL` for each backend) are a private map in `profiles.py`. The §9.1 `HarnessBackend` record has no field for them.
6. **The opencode tools share a base.** `OpencodeHostTool` and the shared parameter declarations live in `vidbyte/tools/builtins/opencode/read_tools.py`. Both `read_tools.py` and `session_tools.py` use them.
7. **opencode tuple results are wrapped in an object.** Tool output wraps them as `{"models": ...}`, `{"providers": ...}`, `{"sessions": ...}` and `{"files": ...}`, because §9.2 asks for JSON objects (`read_tools.py:86-192`).

## 7. Budget (§8.4)

| Item | Used | Allowed |
|---|---|---|
| CREATE files | 56 | 56 |
| MODIFY files | 12 | 12 |
| Records | 66 | 66 |
| Enums | 13 | 13 |
| FailureCodes | 53 | 53 |
| Files outside §12.3 | 0 | 0 |

## 8. Tricky parts: where reviewers should look first

1. **Transport diff size (D-3).** It is +156/-8, right at its re-evaluation trigger. With `exit_grace_seconds` or `stop_process_tree` set, `close()` always goes through `ProcessStopper.stop_tree`, whatever `returncode` says (EC-10). Without either option, the old path is unchanged.
2. **Peer shutdown on POSIX.** These are the paths I trust least, because POSIX tests do not run on this Windows machine (they are among the 19 skips).
   - Grok `__aexit__` marks the host closed, cancels live turns as `HOST_CLOSED`, waits for the grace period, then closes the peers concurrently.
   - Muse turn peers sit in `try/except BaseException` cleanup blocks that re-raise.
3. **Muse `exchange_loaded` (EC-114).** On -32024 `sessionNotLoaded`, it resumes the session once and retries once. A second -32024 raises `muse.api_error`.
4. **Muse steer (EC-115 and EC-102), after `5fae02ba`.**
   - A turn that has finished locally is refused before any `turn/steer` is sent.
   - A -32030 answer becomes `turn_not_found` only if the driver has stopped running by the time the answer arrives. Otherwise it is `muse.api_error`.
   - The race is real: the `turn/completed` notification can still be unprocessed when the -32030 answer arrives. In that window the caller gets `api_error` with `vendor_code` -32030, not `turn_not_found`.
   - No S2 test covers the -32030 path.
5. **`list_harness_backends` has no try.** Its body is `return HARNESS_BACKENDS` and cannot raise, so a try would be dead code. It is the only public function without the §12.4 shape.
6. **Tool `execute` keeps `ConfigurationError` apart from `Exception`.** A refusal names only the parameter, taken from `details["field"]`. A defect names only the exception class. Neither copies exception text (S017). A bool is refused where an integer or number is expected.
7. **`NativeResultEncoder` drops `repr=False` fields.** These hold secrets, such as `ClaudeBackendEnv.auth_token` and the MCP environment and headers. It clips at a UTF-8 boundary; a clipped result is not valid JSON, and `truncated` says so.
8. **Grok search.** It reads up to `GROK_LIST_MAX_PAGES` pages of `session/list` on one short-lived peer and keeps titles that contain the casefolded query. `truncated` comes from the last page's cursor, not from the `limit` cut. A listing longer than the page cap is therefore searched only in part, which the spec allows (`truncated=True`).

## 9. Niche facts for the next agent

- Lint scans only tracked files, so run `git add` before `python lint/run.py`.
- Semgrep needs the venv's `Scripts` first on `PATH` (see gate 5).
- Both conftests import under the module name `conftest`. A plugin that patches through `sys.modules` therefore reaches only the last one loaded; patch the fixture object's class at `pytest_runtest_call` instead.
- The EC-95 fix is written and tested (§5). If it is approved, it is a 9-line commit that needs no new test.
