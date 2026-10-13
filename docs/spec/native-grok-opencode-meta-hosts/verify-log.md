# Verification log: native Grok, opencode and Muse hosts plus GLM/DeepSeek backend profiles

Gate set (from context/code-map.md §1 and reports/S3-implementer.md; run from the worktree root, in this order):

1. Packs (local): `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends`
2. Neighbour suites (local): `PYTHONPATH=$(pwd) python -m pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py tests/features/coding_agent tests/test_mcp_bridge.py`
3. Full suite (local): `PYTHONPATH=$(pwd) python -m pytest -q`
4. Lint ratchet (local): `git add -A`, then `python lint/run.py`; the last line must be `SDK-LINT: PASS`
5. Source stage (local): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
6. Package stage (local): `python scripts/run_ci.py --stage package` with no PYTHONPATH
7. Static policy (local): `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1 from `/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1`)
8. Remote (remote-only): `ci.yml` (Source / Python 3.11 and 3.12) and `static-policy.yml`. Both are `workflow_dispatch` only, so dispatch them after each push with `gh workflow run <file> --ref feat/native-grok-opencode-meta-hosts`; `gh pr checks 1036` does not list dispatched runs, so read them with `gh run view <id>`.

Invariant checks after every iteration: INV-19 (`sha256sum vidbyte/harnesses/native/__init__.py` is `0374a2c8…497a`), INV-22 (`git diff --stat origin/main -- vidbyte/__init__.py contracts/sdk-public-api.json vidbyte/tools/builtins/__init__.py vidbyte/lib/dataclasses/__init__.py vidbyte/lib/constants/__init__.py pyproject.toml` is empty), `vidbyte/lib/enums/failure.py` unchanged.

## Iteration 1 — 2026-10-13 13:01 UTC — agent report: reports/S5-repair-1.md

**Defects in:** step 0 (merge origin/main, conflict in `vidbyte/tools/mcp/transport.py`); R-1, R-2, R-3, R-6, R-5, R-7, R-8, R-4, R-M1; gate CI-1 (EC-51 test `test_grok_host_process_bounds` red on Linux 3.12 only, run 38379243965 at 9d51a3fb); review.md bookkeeping (R-M2, R-M3, R-M9, R-9 to R-15, R-M6).

**Hypotheses and attempts:**
- **Step 0.** Merged origin/main (no rebase). The only conflict was `McpStdioTransport.notify`: main changed the frame so `params` is left out when it is `None`, this branch added `timeout_seconds`. Kept one `notify` with both. The packs gave the same results before and after the merge, and CI at the merge (run 38395105270) showed only the packet's known failures: 12 on 3.11, and 13 on 3.12 (the extra one is CI-1).
- **R-1.** `_MALFORMED_CODES` is now `{-32700, -32600}` only, so a `-32602` that carries no cursor is `grok.api_error` with the vendor code (EC-16). The cursor row (EC-41) is unchanged.
- **R-2.** On win32 the launcher is refused when its name ends in `.cmd` or `.bat`, compared case-insensitively after dropping the trailing dots and spaces that Windows ignores. This applies to `grok` found on PATH and to an explicit `grok_command[0]`. A refused PATH hit falls back to `~/.grok/bin/grok.exe`. With no usable launcher the host raises `not_installed` with a batch-specific message and next step (EC-157, D-19). `GrokCli.refused_batch` carries the refused path to the host.
- **R-3.** With no per-call timeout, `McpStdioTransport` is back to the plain `await stdin.drain()` from origin/main (INV-18). Only a call that names `timeout_seconds` gets `wait_for(drain(), seconds)`.
- **CI-1: root cause.** I read the CPython 3.11 and 3.13 asyncio source. On a Unix write to a pipe whose reader is gone, `_UnixWritePipeTransport.write` gets EPIPE and calls `_fatal_error`. That calls `_close`, which sets `_closing=True` at once and schedules `connection_lost` with `call_soon`. The stream protocol only learns of the loss after a second `call_soon` hop (`WriteSubprocessPipeProto` → `_pipe_connection_lost` → `_call`).
  - A bare `drain()` yields once (`sleep(0)`) and then returns normally, so the error is swallowed.
  - On 3.11, `wait_for` wraps `drain` in a Task. That adds the missing loop turn, so the error surfaces.
  - On 3.12+, `wait_for` runs inline, so the error does not surface. That explains why only 3.12 was red.
  - On Windows (Proactor), `drain` raises in every mode, which is why the gate was green locally.
  - So CI-1 is a code defect tied to R-3, not a test defect. This is the "open lead" in review.md.
- **CI-1: rejected options.**
  - (a) An extra `await asyncio.sleep(0)` after `drain`. It depends on how many hops CPython uses, so it is fragile across versions.
  - (b) A liveness check in `NativePeer`. The fixture child is still alive with stdout open, so the check would detect nothing.
  - (c) An `is_closing()` check on every write. It would change the default `request`/`notify` behaviour that INV-18 freezes.
- **CI-1: chosen fix.**
  - After `drain()`, a write that named a deadline raises `BrokenPipeError` when `stdin.is_closing()` is True. The transport maps that to `McpProtocolError`, and the host maps it to `process_exited`.
  - `NativePeer` now always passes its control timeout to `request`, `send_request`, `notify` and `respond`. So every native write is bounded and checked, and the default transport path is untouched.
  - Verified on remote Linux: run 38396542610 at eea8cf36 has the EC-51 test green on 3.11 and 3.12 (7 failed, all R-5/R-6/R-8 tests, which are fixed since).
- **R-6.** `OpencodeTurnWatcher.abort_before_failing(error)` sends one `POST /session/{id}/abort`, best effort, before `_drive` re-raises any failure that the host itself raised.
  - It skips the abort when:
    - the server already ended the turn;
    - an abort is already pending;
    - the error is the turn's own reported failure;
    - the session is gone.
  - `_retry_failure` no longer aborts on its own, which removes the double abort (EC-158).
- **R-5.** `MuseHost.__aexit__` runs these steps:
  1. Tells every driver to shut down (errors suppressed).
  2. Waits for the turn tasks up to `NATIVE_STOP_GRACE_SECONDS`.
  3. Closes every peer concurrently. Each close is bounded by the transport's grace and kill waits.
  4. Waits for the tasks, which end once their peer is closed.

  A peer that never answers `approval/decide` can no longer hold the exit open (NFR-2).
- **R-7.** `MuseLauncher.peer_environment` builds the WSLENV forwarding list for every WSL peer, read peers included.
  - It holds `META_API_KEY/u` when the variable is set, plus the mark's `/u` entry when the peer has a mark.
  - The caller's own WSLENV entries stay first.
  - An empty list leaves the environment unchanged (D-18, §9.3).
- **R-8.** Grok and Muse session ids are lower-cased right after `require_uuid` at every site that calls it: Grok continue and fork, and Muse continue, fork, read, page and usage. The places that compare ids also compare them in lower case: the Grok fork check, `check_fork_result` and the listing check. Upper-case and lower-case spellings of one live session now count as busy (INV-14). `require_uuid` and `NativeTurnTable` are unchanged.
- **R-4.** `ToolParameter` has no enum field, and adding one would change a public contract.
  - The fix uses the pattern of the other categorical tool params: `MuseHostTool.spec()` builds the parameter schema with `ToolsFormatter.input_schema` and adds `"enum": [m.value for m in MuseReasoningEffort]` to `reasoning_effort`. The typed `parameters` are kept, so prompt docs and required names do not change.
  - The description also names the seven values, read from the enum, in four sentences. This keeps them visible in prompt-rendered tool docs, which show only descriptions.
  - Verified by dumping `spawn_muse_session` and `continue_muse_session` (shown below).
- **R-M1.** The `OpencodeHost` constructor's `require_instance` is now inside `try/except ConfigurationError`, mapped through `from_configuration_error`. `OpencodeHost('not settings')` now raises `NativeHostError configuration.invalid_argument`.
- **Gate flake, recorded for the next agent.**
  - The first full-suite run had one failure in an unrelated test (`test_trajectory_checkpoint_algorithm.py::…private_manager_created_when_missing`). Creating its event loop raised `OSError: [WinError 10055] … lacked sufficient buffer space`.
  - The machine had about 3,700 loopback sockets in TIME_WAIT. Each Proactor loop's self-pipe is a socketpair, and other sessions were running at the same time.
  - The file passed on its own (25 passed), and the full suite then passed on rerun. It is environmental; no code was changed for it.

**Changes:** merge 3cdd9704; R-1 749b7583; R-2 137fa778; R-3 a9223a02; CI-1 eea8cf36; R-6 1e62494b; R-5 93c42f68; R-7 a4d74982; R-8 e70be132; R-4 54d5c17b; R-M1 87217940; review.md statuses d6733882.

R-4 schema dump (`ToolsFormatter.input_schema(tool.spec())["properties"]["reasoning_effort"]`, the same for both tools):
```
spawn_muse_session {"description": "How much reasoning Muse should spend on this turn. It must be one of none, minimal, low, medium, high, xhigh, ultra, which run from the least reasoning to the most, written in lower case. Leave it out to use Muse's own default for the model. Any other value is refused before the turn starts.", "enum": ["none", "minimal", "low", "medium", "high", "xhigh", "ultra"], "type": "string"}
```

**Gate matrix out (HEAD d6733882):**

| Gate | Command | Result | Final lines |
|---|---|---|---|
| packs | gate 1 | PASS | `1638 passed, 19 skipped in 151.15s (0:02:31)` |
| neighbour suites | gate 2 | PASS | `464 passed, 12 skipped in 17.44s` |
| full suite | gate 3 | PASS on rerun (first run: 1 environmental WinError 10055, see above) | `5653 passed, 32 skipped in 187.49s (0:03:07)` |
| lint | gate 4 | PASS (A002 602/703 IMPROVED, A007 255/255) | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| source stage | gate 5 | PASS | `5653 passed, 32 skipped in 183.94s (0:03:03)` / `CI passed.` |
| package stage | gate 6 | PASS | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| semgrep | gate 7 | PASS | `Ran 1 rule on 949 files: 0 findings.` |
| public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| remote CI | `gh run view 38401581802` | PASS (3.11, 3.12, Package all success) | 3.12: `5646 passed, 39 skipped, 19 warnings in 183.38s` / `CI passed.`; 3.11: `5646 passed, 39 skipped in 180.13s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| PR checks | `gh pr checks 1036` | n/a | `no checks reported on the 'feat/native-grok-opencode-meta-hosts' branch` (dispatch-only workflows); PR still a draft |
| remote static policy | `gh run view 38401585901` | PASS | `Ran 1 rule on 949 files: 0 findings.` (conclusion success) |
| invariants | INV-19 / INV-22 / FailureCode | PASS | sha256 `0374a2c8…497a`; INV-22 diff empty; `failure.py` untouched |

**Still open:** none from this packet. Deferred by the orchestrator: R-9 to R-15 and R-M6 (iteration 2/3). Follow-ups: R-M4, R-M5, R-M7, R-M8.
