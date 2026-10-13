# S5 repair, iteration 1 of 8

- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-grok-opencode-meta-hosts`
- **Branch:** `feat/native-grok-opencode-meta-hosts`
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1036 (still a draft)
- **HEAD:** 6b68a567 at the start of this iteration. After the last code or bookkeeping commit it is d6733882. This report and verify-log.md are committed after that.

## Result

Every finding in this iteration's packet is fixed, and every gate is green, both locally and on the remote CI run at d6733882.

- **Tests:** no test file was edited. The test changes in the range came from origin/main through the merge.
- **Lint and config:** nothing under `lint/`, `pyproject.toml` or the spec was touched.
- **review.md:** only status cells changed.
- **Invariants:**
  - INV-19 sha256 is unchanged (`0374a2c8…497a`).
  - The INV-22 diff against origin/main is empty.
  - `vidbyte/lib/enums/failure.py` is untouched.
  - origin/main is an ancestor of HEAD.

## Commits

| Item | Commit | Files |
|---|---|---|
| step 0 merge of origin/main | 3cdd9704 | `vidbyte/tools/mcp/transport.py` (conflict: one `notify` with `timeout_seconds` and main's "no params when None" frame) |
| R-1 | 749b7583 | `vidbyte/harnesses/native/grok/wire.py` |
| R-2 | 137fa778 | `vidbyte/harnesses/native/grok/cli.py`, `vidbyte/harnesses/native/grok/host.py` |
| R-3 | a9223a02 | `vidbyte/tools/mcp/transport.py`, `vidbyte/harnesses/native/hostkit/peers.py` |
| CI-1 (gate) | eea8cf36 | `vidbyte/tools/mcp/transport.py`, `vidbyte/harnesses/native/hostkit/peers.py` |
| R-6 | 1e62494b | `vidbyte/harnesses/native/opencode/turn.py`, `vidbyte/harnesses/native/opencode/host.py` |
| R-5 | 93c42f68 | `vidbyte/harnesses/native/muse/host.py` |
| R-7 | a4d74982 | `vidbyte/harnesses/native/muse/launcher.py` |
| R-8 | e70be132 | `vidbyte/harnesses/native/grok/host.py`, `vidbyte/harnesses/native/grok/wire.py`, `vidbyte/harnesses/native/muse/host.py` |
| R-4 | 54d5c17b | `vidbyte/tools/builtins/muse/tools.py`, `vidbyte/tools/builtins/muse/descriptions.py` |
| R-M1 | 87217940 | `vidbyte/harnesses/native/opencode/host.py` |
| review.md statuses | d6733882 | `docs/spec/native-grok-opencode-meta-hosts/review.md` (status cells only) |

## Per finding

- **R-1.** `_MALFORMED_CODES = frozenset({-32700, -32600})`.
  - A `-32602` that carries no cursor is now `grok.api_error`, with `vendor_code` "-32602" and the vendor's message (EC-16).
  - The cursor case (EC-41) is unchanged.
- **R-2.** On win32 the host never starts a `.cmd` or `.bat` launcher.
  - `GrokCli._is_batch` compares the name case-insensitively, after stripping the trailing ". " that Windows drops from file names.
  - **Explicit `grok_command`:** a batch `grok_command[0]` is refused.
  - **`grok` on PATH:** a batch file found on PATH is refused, and the host falls back to `~/.grok/bin/grok.exe` when that exists.
  - **No usable launcher:** the host raises `not_installed` with the batch launcher's path and `_BATCH_LAUNCHER_NEXT_STEP` (EC-157, D-19). When no batch file was refused, the EC-11 message is unchanged.
- **R-3.** A call with no per-call timeout gets the plain `await stdin.drain()` again, as on origin/main (INV-18). A call that names `timeout_seconds` gets `wait_for(drain(), seconds)`.
- **CI-1.** This is a code defect tied to R-3, not a test defect. The asyncio mechanism, verified in the CPython source:
  1. EPIPE in `_UnixWritePipeTransport.write` calls `_fatal_error`, then `_close`. That sets `_closing` at once and schedules `connection_lost`.
  2. The stream protocol hears of the loss only after a second `call_soon` hop.
  3. A bare `drain()` yields once and returns normally.
  4. On 3.11, `wait_for` wraps `drain` in a Task. That adds a loop turn, so the error surfaces.
  5. On 3.12+, `wait_for` runs inline, so the error does not surface. That is why only 3.12 was red.

  **Fix:** after `drain()`, a write with a deadline raises `BrokenPipeError` when `stdin.is_closing()` is True. `NativePeer` now always passes its control timeout on `request`, `send_request`, `notify` and `respond`.

  **Rejected options:**
  - An extra `sleep(0)` depends on CPython's hop count.
  - A `NativePeer` liveness check would not catch this, because the fixture child stays alive.
  - An `is_closing()` check on every path would break INV-18.

  Remote run 38396542610 at eea8cf36 had the EC-51 test green on 3.11 and 3.12.
- **R-6.** `OpencodeTurnWatcher.abort_before_failing(error)`: `_drive` calls it in both of its `except` branches before re-raising. It sends one best-effort `POST /session/{id}/abort`.
  - It sends no abort when:
    - the server already ended the turn (`_server_ended`);
    - an abort deadline is already set;
    - the error is the turn's own failure;
    - the error is `opencode.session_not_found`.
  - `_retry_failure` is now synchronous and no longer aborts (EC-158).
- **R-5.** `MuseHost.__aexit__` now runs these steps:
  1. Shuts down the drivers (errors suppressed).
  2. Waits for the tasks up to `NATIVE_STOP_GRACE_SECONDS`.
  3. Closes every peer concurrently. Each close is bounded by the transport's grace and kill waits.
  4. Awaits the tasks.

  A peer that never answers `approval/decide` no longer blocks exit (NFR-2).
- **R-7.** `MuseLauncher.peer_environment` builds the WSLENV forwarding list for every WSL peer.
  - The list holds `META_API_KEY/u` when the variable is set, plus `VIDBYTE_PEER_MARK/u` when the peer has a mark.
  - The caller's own WSLENV entries come first.
  - When there is nothing to forward, or outside WSL mode, the environment is unchanged (D-18, §9.3).
  - The key's value is never read.
- **R-8.** A session id is lower-cased right after `require_uuid` at every site that calls it: Grok continue and fork, and Muse continue, fork, read, page and usage. The Grok fork's same-id check, `GrokWire.check_fork_result` and the fork listing check also compare in lower case (INV-14). `require_uuid` and `NativeTurnTable` are unchanged.
- **R-4.** `ToolParameter` has no enum field, and adding one would be a public-contract change, so the fix leaves it alone.
  - **Input schema:** `MuseHostTool.spec()` takes the schema that `ToolsFormatter.input_schema` builds and adds `"enum": [m.value for m in MuseReasoningEffort]` to `reasoning_effort`. This is the same pattern as `fork.py`'s categorical params. `parameters` is kept, so the prompt docs, `required_parameter_names` and the spec-table tests are unaffected.
  - **Description:** `REASONING_EFFORT_PARAMETER_DESCRIPTION` now names the seven values, read from the enum, in four general sentences. Prompt-rendered tool docs show only the description, so the values are visible there too.
  - **Schema dump (the same for `continue_muse_session`):**
    ```
    spawn_muse_session {"description": "How much reasoning Muse should spend on this turn. It must be one of none, minimal, low, medium, high, xhigh, ultra, which run from the least reasoning to the most, written in lower case. Leave it out to use Muse's own default for the model. Any other value is refused before the turn starts.", "enum": ["none", "minimal", "low", "medium", "high", "xhigh", "ultra"], "type": "string"}
    ('prompt',)
    ```
- **R-M1.** In the `OpencodeHost` constructor, `require_instance` is now inside `try/except ConfigurationError`, mapped through `from_configuration_error`. The error factory is built first.
  - Before: `OpencodeHost('not settings')` raised `ConfigurationError`.
  - After: `NativeHostError FailureCode.CONFIGURATION_INVALID_ARGUMENT settings must be OpencodeHostSettings; got a value of type str.`
- **Bookkeeping (status cells only, d6733882):**
  - R-1 to R-8, R-M1: `fixed @<sha>`.
  - R-M2, R-M3: `fixed @e377b7c2 (spec r8, docs only)`.
  - R-M9: `fixed @96df0b45 (regression tests)`.
  - R-9 to R-15, R-M6: `deferred (iteration 2/3)`.
  - R-M4, R-M5, R-M7, R-M8: left at `open · follow-up`.

## Gates (run in this worktree, this iteration, at d6733882)

1. **Packs** (`PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends`): PASS.
   ```
   ........................................................................ [ 99%]
   .                                                                        [100%]
   1638 passed, 19 skipped in 151.15s (0:02:31)
   ```
2. **Neighbour suites** (S3's command plus `tests/test_mcp_bridge.py`): PASS.
   ```
   ............................................                             [100%]
   464 passed, 12 skipped in 17.44s
   ```
3. **Full suite** (`PYTHONPATH=$(pwd) python -m pytest -q`): PASS on the second run.
   - The first run had 1 failure (`5652 passed, 1 failed`): `tests/test_trajectory_checkpoint_algorithm.py::…test_inner_context_window_private_manager_created_when_missing`. It failed in `ProactorEventLoop._make_self_pipe` with `OSError: [WinError 10055] … lacked sufficient buffer space`.
   - At that time `netstat` showed 3,694 sockets in TIME_WAIT on the machine. The test is unrelated to this change, and its file passes alone (`25 passed in 0.85s`).
   - Second run:
   ```
   ..s..................................................................    [100%]
   5653 passed, 32 skipped in 187.49s (0:03:07)
   ```
4. **Lint** (`python lint/run.py` after `git add`): PASS. A002 is 602 against 703 (IMPROVED). A007 is 255 against 255. S025 is 261 against 263.
   ```
   S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

   SDK-LINT: PASS
   ```
5. **Source stage** (`PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`): PASS.
   ```
   tests\test_workflow_agent_forks.py ......                                [100%]
   ================ 5653 passed, 32 skipped in 183.94s (0:03:03) =================
   CI passed.
   ```
6. **Package stage** (`python scripts/run_ci.py --stage package`, with no PYTHONPATH): PASS.
   ```
   No broken requirements found.
   Installed vidbyte-sdk 0.2.1 passed smoke checks.
   CI passed.
   ```
7. **Semgrep** (`semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`): PASS, exit 0.
   ```
   Ran 1 rule on 949 files: 0 findings.
   ```
8. **Public API** (`python scripts/generate-sdk-public-api.py --check`): PASS.
   ```
   contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).
   ```
   - **Import order:** `ruff --select I001` over `vidbyte` reports 223 findings, none of them in a file this feature touches. They are already on main and ratcheted under S051.
9. **Remote CI**, `ci.yml` dispatched at d6733882 (run 38401581802): success on all three jobs.
   ```
   Source / Python 3.12 | 5646 passed, 39 skipped, 19 warnings in 183.38s (0:03:03) | CI passed.
   Source / Python 3.11 | 5646 passed, 39 skipped in 180.13s (0:03:00) | CI passed.
   Package | Installed vidbyte-sdk 0.2.1 passed smoke checks. | CI passed.
   ```
10. **Remote static policy** (run 38401585901): success. `Ran 1 rule on 949 files: 0 findings.`
11. **`gh pr checks 1036`:** `no checks reported on the 'feat/native-grok-opencode-meta-hosts' branch`. The workflows are dispatch-only, so their runs are read with `gh run view`. The PR is still a draft.

Remote history:

| Run | Commit | Result |
|---|---|---|
| 38379243965 | 9d51a3fb | before this iteration |
| 38395105270 | 3cdd9704 (merge) | 3.11: 12 failed; 3.12: 13 failed (the extra one is CI-1) |
| 38396542610 | eea8cf36 | 7 failed on both versions (R-8 ×4, R-6 ×2, R-5 ×1); EC-51 green |
| 38401581802 | d6733882 | green |

## Still open

None from this packet.

- **Deferred by the orchestrator:** R-9 to R-15 and R-M6.
- **Follow-ups:** R-M4, R-M5, R-M7 and R-M8.
