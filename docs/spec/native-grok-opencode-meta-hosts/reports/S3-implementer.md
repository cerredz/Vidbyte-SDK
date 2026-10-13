# S3 implementer report: native-grok-opencode-meta-hosts

**Status: DONE.** All 68 rows of §12.3 are implemented. Every local gate is green at `f7476015`. The branch is pushed and draft PR #1036 is open. Remote CI was dispatched, and the spec records `pr:` and `status: implemented`.

| Item | Value |
|---|---|
| Branch | `feat/native-grok-opencode-meta-hosts` |
| Implementation HEAD | `f7476015` (gates run here) |
| Spec commits after it | `fb639f3a` (PR record) and `9d51a3fb` (proof); this report follows |
| Draft PR | https://github.com/cerredz/Vidbyte-SDK/pull/1036 |
| Remote CI (dispatched at `9d51a3fb`, not awaited) | `ci.yml` run `38379243965`; `static-policy.yml` run `38379248609` |
| Test baseline | `91e874b2`. `git diff 91e874b2..HEAD -- tests/ \| wc -l` gives `0` |
| Spec | r7: frontmatter `status: implemented`, `pr:` set, a §17 row, and an "Implementation deviations" list |

## Resolution of the three stops

Each stop was resolved by the coordinator.

| Stop | Cause | Resolution |
|---|---|---|
| 1 | Test defects D-1 to D-3 | S2 fixed the tests at `66d5c3bb` |
| 2 | The `muse.budget_exhausted` next step contradicted itself | Spec r5. My constant follows it at `e9ff2613` |
| 3 | Test defects D-4 to D-6, and the exit code EC-95 needs | S2 fixed the tests at `209c4085`. Spec r6 added the read-only `McpStdioTransport.returncode` and `NativePeer.exit_code`, which I implemented at `fcdd5861` |

The briefing named the §17 row "r4", but the spec was already at r6 when I added it, so the row is **r7** and the frontmatter revision is now 7.

## 1. Commits

These are the implementation commits from `git log origin/main..HEAD --oneline`, newest first. Spec and test commits from other stages are left out.

| SHA | Subject | §12.3 rows |
|---|---|---|
| `f7476015` | docs(mcp): note the read-only returncode in the native peer options [W-13; FR-15, EC-95] | 23 |
| `fcdd5861` | feat(harnesses): read the WSL muse exit code so 127 maps to not_installed [W-5, W-6, W-10; EC-95, FR-15] | 22, 28, 41 |
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
| `a09959c7` | feat(harnesses): add the GLM and DeepSeek backend functions [W-7; FR-4, AC-13, AC-14, EC-122 to EC-137] | 45, 46 (also touches 6, 28) |
| `b9b7cfd6` | fix(harnesses): name the refused argument in invalid_argument errors [W-1, W-6; EC-1, EC-138] | 6, 13, 26 |
| `e9ff2613` | fix(lib): name continue_muse_session in the muse.budget_exhausted next step [W-1; EC-117, AC-17] | 13 |
| `f1567ae9` | feat(harnesses): add native hostkit shared by the Grok, opencode and Muse hosts [W-6; INV-6, EC-5, EC-9, EC-149] | 25-28 |
| `eb47d589` | feat(mcp): extend McpStdioTransport for ACP and MSP peers [W-5; FR-15, EC-10, INV-18] | 22 |
| `6692ee57` | fix(lib): name operational bounds in native records and process helpers [W-2, W-4; INV-5, FR-16] | 8, 9, 10, 13, 17, 18 |
| `c3bd8c6f` | feat(harnesses): add the fixed native harness package marker [W-14; AC-16, INV-19] | 24 |
| `b137305e` | feat(lib): add canonical CLI runner, managed process and tree stopper [W-4; FR-16, INV-4] | 16-18 |
| `ba78a4da` | feat(errors): add NativeHostError [W-3; INV-1, INV-8] | 19, 20 |
| `49eae8cc` | feat(lib): add native host records and backend profiles [W-2; FR-4, ...] | 7-12, 14, 15 |
| `26f897e9` | feat(lib): add native host enums, failure codes, constants and record validator [W-1; INV-5, INV-8, AC-17] | 1-6, 13 |

## 2. What was built, in data-flow order

1. **Closed sets.** The enums, the 53 FailureCodes and the constants, including `NATIVE_HOST_NEXT_STEPS`. Files: `vidbyte/lib/enums/{native_hosts,harness_backends,process}.py`, `vidbyte/lib/enums/failure.py` and `vidbyte/lib/constants/native_hosts.py`.
2. **Validation.** `RecordFieldValidator` and `RecordFieldConverter`, in `vidbyte/lib/dataclasses/validation.py`.
3. **Records.** The 66 records, frozen and slotted, each validated in `__post_init__`. Files: `vidbyte/lib/dataclasses/{native_hosts,grok,opencode,muse,harness_backends,process}.py`. The backend profiles are in `vidbyte/lib/configs/harness_backends.py`.
4. **Error type.** `NativeHostError`, in `vidbyte/lib/errors/base.py`.
5. **Process helpers.** `CliRunner`, `ManagedProcess` and `ProcessStopper`, in `vidbyte/lib/process/{runner,managed}.py`.
6. **Transport (D-3).** `McpStdioTransport` in `vidbyte/tools/mcp/transport.py` gains `on_message`, `send_request`, `notify`, `respond`, per-call timeouts, `exit_grace_seconds`, `stop_process_tree` and the read-only `returncode`. The diff is +166/-8.
7. **Package marker.** `vidbyte/harnesses/native/__init__.py`, with the fixed bytes INV-19 requires.
8. **Hostkit (D-22).** `NativeErrorFactory`, `NativeTurnTable`, `NativePeer` (with the read-only `exit_code`) and `NativeChildEnvironment`, in `vidbyte/harnesses/native/hostkit/{errors,turns,peers}.py`.
9. **Backends.** The six `HarnessBackends` functions in `vidbyte/harnesses/native/backends/profiles.py`, bound in `backends/__init__.py` (D-16).
10. **Hosts.**
    - `GrokHost` in `grok/host.py`, over `turn.py`, `wire.py` and `cli.py`.
    - `OpencodeHost` in `opencode/host.py`, over `client.py`, `server.py`, `turn.py` and `wire.py`.
    - `MuseHost` in `muse/host.py`, over `launcher.py`, `turn.py` and `wire.py`.
11. **Tools.** The shared base is `vidbyte/tools/builtins/native_host_tool.py`. The 43 tools are under `vidbyte/tools/builtins/{grok,opencode,muse,harness_backends}/`.
12. **Toolsets.** `vidbyte/tools/toolsets/{grok,opencode,muse,harness_backends}.py`, exported from `toolsets/__init__.py`.
13. **Docs.** `REPO_MAP.md`, plus the READMEs of `vidbyte/lib`, `vidbyte/harnesses`, `vidbyte/tools` and `vidbyte/tools/mcp`.

## 3. Checklists

### §12.3: 68 of 68 rows

I compared `git diff --name-status $(git merge-base origin/main HEAD)..HEAD -- . ':!docs/' ':!tests/'` with the table:

- 56 files were added and 12 modified.
- Every file and its action (add or modify) match a table row.
- **No file outside §12.3 was touched.**

| Rows | Done |
|---|---|
| 1-20 | [x] |
| 22, 24-28 | [x] |
| 29-46 | [x] |
| 48-66 | [x] |
| 21, 23, 47, 67, 68 | [x] |

### §12.4 obligations: all ticked

- [x] **A001 headers.** Lint passes.
- [x] **Records.** All 66 are frozen and slotted, in `lib/dataclasses`.
- [x] **Enums.** All 13 are in `lib/enums` and exported.
- [x] **No upward imports.** `vidbyte/lib` imports nothing above it, and A006 passes.
- [x] **Narrated main functions, with one-level helpers.**
- [x] **One try per public method.** A scratch AST check covered all 49 public methods of the hosts and `HarnessBackends`.
  - The one exception is `list_harness_backends`, which returns a constant (deviation 8).
- [x] **Errors.** All go through `NativeErrorFactory`.
- [x] **Processes.** Every process start is in a try/finally, and no child inherits stdin.
- [x] **Peers.** Every peer is built with `stop_process_tree=True`.
- [x] **§6.3 codes and tokens.** The shared-contract tests are green.
- [x] **A007.** 255/255.
- [x] **Forbidden constructs.** No `asyncio.Lock`, no `TypedDict`, no async parameter named `timeout`.
- [x] **S012.** Every `.request(` call passes `timeout_seconds=`.
- [x] **S025 and S062.** Tool descriptions meet the length rule and use no implicit string concatenation.
- [x] **No `str(exc)` or `repr(exc)`.**
- [x] **S054.**
- [x] **Semgrep** is clean.
- [x] **AC-20.** All 7 entry modules import in a fresh interpreter.
- [x] **Appended exports.** No export list was reordered.
- [x] **INV-19.** The hash matches.
- [x] **`run_ci.py`.** Both stages pass.

### §12.5 actions

- [x] Five README and REPO_MAP actions: `a4ea7b70`, plus `f7476015` for `returncode`.
- [x] Four `__init__` export appends.
- [x] No contract regeneration, no `pyproject.toml` change and no baseline change.
- [ ] **PR body stating the §10 limitations.** The S3 PR body is the required placeholder. The S6 PR description owns this.

### Signature check

A scratch script compares all 90 §8.5 methods, including the r6 properties, against `inspect.signature`. It prints `compared=90 diffs=0`. The six backend functions and `run_grok_once` also match.

## 4. Gates

All gates ran at HEAD `f7476015`, in the order the briefing gives.

**1. S2 packs.** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends`

1616 passed and 19 were skipped, which accounts for all 1635 tests. The 19 skips are platform guards.
```
........................................................................ [ 96%]
...................................................                      [100%]
1616 passed, 19 skipped in 146.74s (0:02:26)
EXIT 0
```

**2a. Neighbour suites.** `PYTHONPATH=$(pwd) python -m pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py tests/features/coding_agent`
```
.........................                                                [100%]
445 passed, 12 skipped in 16.95s
EXIT 0
```

**2b. Full suite.** `PYTHONPATH=$(pwd) python -m pytest -q`
```
...................................................................s.... [ 98%]
............................................................             [100%]
5572 passed, 32 skipped in 178.97s (0:02:58)
EXIT 0
```

**3. Lint.** `python lint/run.py`, run after `git add -A`.
```
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
EXIT 0
```
- A002 improved from 703 to 623. I did not lower the baseline, because `lint/` is off-limits.
- A007 is at 255 against its baseline of 255.

**4a. Source stage.** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
```
reasoning trace contracts: ok (182 tools, 55 shapes)

================ 5572 passed, 32 skipped in 180.54s (0:03:00) =================
CI passed.
EXIT 0
```

**4b. Package stage.** `python scripts/run_ci.py --stage package`, run without PYTHONPATH.
```
Installed vidbyte-sdk 0.2.1 passed smoke checks.
CI passed.
EXIT 0
```

**5. Semgrep.** I ran `git add -A`, then `semgrep.exe scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with `PATH` prefixed by `C:/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1/Scripts`.
```
✅ Scan completed successfully.
 • Findings: 0 (0 blocking)
Ran 1 rule on 949 files: 0 findings.
EXIT 0
```

**Final checks:**

| Check | Result |
|---|---|
| `git diff 91e874b2..HEAD -- tests/ \| wc -l` | `0` |
| INV-22 paths diffed against the merge base | `0` lines |
| `git show HEAD:vidbyte/harnesses/native/__init__.py \| sha256sum` | `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a` |
| AC-20: `python -c "import <m>"` for each of the 7 modules | OK ×7 |
| Remote CI | `ci.yml` 38379243965 (in_progress), `static-policy.yml` 38379248609 (queued), both at `9d51a3fb`. Not awaited |

## 5. Deviations

These points are left open by the spec. The same list is under §17 of the spec.

1. **Invalid-argument next step.**
   - The new constant `NATIVE_INVALID_ARGUMENT_NEXT_STEP = "Fix the {field} argument and call again."` puts the argument's name, which is the EC-1 and EC-138 token, into the next step.
   - Every validator `ConfigurationError` now carries `details["field"]`.
   - Host methods catch `ConfigurationError` between `NativeHostError` and `Exception`. Without that, an error raised while building a record would become `runtime.error`.
2. **`RecordFieldConverter.to_enum` and `to_decimal`.**
   - They exist for JSON tool arguments and wire bodies.
   - `to_decimal` refuses a JSON number, so the DeepSeek balance keeps its exact digits.
3. **Backend error label.** The backend `NativeErrorFactory` uses the harness label `NativeHarness.CLAUDE_CODE`. Backend errors use explicit `backend.*` codes.
4. **`from_unexpected` message.** It names no host: `"<operation> failed with an unexpected <ErrorType>."`
5. **Claude model slots.** They are a private map in `profiles.py`, because §9.1 `HarnessBackend` has no field for them.
6. **Shared opencode tool base.** `OpencodeHostTool` and the shared parameter declarations live in `opencode/read_tools.py`.
7. **opencode tuple results.** They are wrapped as `{"models"|"providers"|"sessions"|"files": ...}`, so every tool output is a JSON object.
8. **`list_harness_backends` has no try.** It returns a module constant and cannot raise.

## 6. Budget (§8.4)

| Item | Used | Allowed |
|---|---|---|
| CREATE files | 56 | 56 |
| MODIFY files | 12 | 12 |
| Records | 66 | 66 |
| Enums | 13 | 13 |
| FailureCodes | 53 | 53 |
| Files outside §12.3 | 0 | 0 |

## 7. Tricky parts: where reviewers should look first

1. **Transport extension (D-3).**
   - The diff is +166/-8. The r6 trigger is about 200 changed lines.
   - `returncode` reads the live process while one is attached. Otherwise it reads the value that `_detach_process_state` saved, so it survives `close()` and `abandon()`.
   - `close()` with a grace period or `stop_process_tree` always calls `ProcessStopper.stop_tree`. With the defaults, `close()` takes the old path (INV-18).
2. **EC-95 depends on order.** `MuseHost._handshake` closes the peer first, so the process has been reaped, and only then reads `peer.exit_code`. A peer that is still running reports `None`, and `launch_failure` then falls back to the stderr text.
3. **Peer shutdown on POSIX.**
   - Grok's `__aexit__` cancels live turns as `HOST_CLOSED`, waits for the grace period, then closes the peers concurrently.
   - Muse turn peers sit in `try/except BaseException` cleanup that re-raises.
   - These paths have the least local evidence, because the POSIX-only tests are among the 19 skips on this Windows machine.
4. **Muse steer (EC-115 and EC-102).**
   - A turn that has already finished is refused before `turn/steer` is sent.
   - A -32030 answer maps to `turn_not_found` only if the driver has stopped by then; otherwise it maps to `muse.api_error`.
   - If `turn/completed` and -32030 arrive together, the caller can get `api_error` with `vendor_code` -32030.
   - No S2 test covers -32030 on steer.
5. **Muse `exchange_loaded` (EC-114).** On -32024 it resumes the session once and retries once. A second -32024 raises `muse.api_error`.
6. **Tool `execute`.**
   - A refusal names only the parameter, taken from `details["field"]`.
   - A defect names only the exception class.
   - A bool is refused where an integer or number is expected.
7. **`NativeResultEncoder`.**
   - It drops `repr=False` fields, such as `ClaudeBackendEnv.auth_token` and the MCP env and headers.
   - It clips output at a UTF-8 boundary, so clipped output is not valid JSON; `truncated` says so.
8. **Grok search.**
   - It reads up to `GROK_LIST_MAX_PAGES` pages on one short-lived peer and matches casefolded titles.
   - `truncated` comes from the last page's cursor. The `limit` cut does not set it.

## 8. Niche facts for the next agent

- **Lint scans only tracked files.** Run `git add` before `python lint/run.py`.
- **Semgrep needs its own `Scripts` first on `PATH`.** On this machine, the global `pysemgrep` fails under mcp 2.x.
- **The opencode list tools return wrapped objects, not bare arrays.** S6 should mention this in the PR description.
- **The remote CI runs were dispatched at `9d51a3fb`, which is docs-only on top of `f7476015`.** Check them with `gh run view 38379243965` and `gh run view 38379248609`.
