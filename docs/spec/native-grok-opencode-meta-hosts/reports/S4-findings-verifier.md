# S4 findings verifier — merge + verification log

Diff: `git diff origin/main...de5b7c4c` (code at HEAD `f148b756` equals `de5b7c4c`; later commits are docs only).
Gates I ran: four feature packs `1616 passed, 19 skipped in 145.55s`; `python lint/run.py` → `SDK-LINT: PASS`. So every finding below is a correctness/security/conformance/doctrine gap the gates do not catch.
Scratch under `.../scratchpad/s4-verifier/` (my own) and `.../scratchpad/s4-engineering/` + `a002_refs.py`, `code_calls.py`, `call_depth.py` (earlier agents', read before running).

## Merge map (original ID → merged ID)

| Original | Merged | Disposition |
|---|---|---|
| R-C1 (Blocker) | R-1 | CONFIRMED Blocker |
| R-E1 (Blocker) | R-2 | CONFIRMED Blocker |
| R-C2 (Major) | R-3 | CONFIRMED Major |
| R-V9 (Major) | R-4 | CONFIRMED Major |
| R-E4 (Major) | R-5 | CONFIRMED Major |
| R-E3 (Major) | R-6 | CONFIRMED Major |
| R-E5 (Major) | R-7 | CONFIRMED Major |
| R-E2 (Major) + R-C5 (Minor) | R-8 | CONFIRMED Major (merged; took the higher severity) |
| R-V2 (Blocker) | R-9 | CONFIRMED, downgraded to Major |
| R-V6 (Major) | R-10 | CONFIRMED Major |
| R-V7 (Major) + R-C4 backtick half (Minor) | R-11 | CONFIRMED Major (merged) |
| R-V8 (Major) | R-12 | CONFIRMED Major |
| R-V4 (Major) | R-13 | CONFIRMED Major |
| R-V5 (Major) | R-14 | CONFIRMED Major (bundled with R-15's pass) |
| R-V1 (Blocker) | R-15 | CONFIRMED, downgraded to Major |
| R-C4 constructor half (Minor) | R-M1 | CONFIRMED Minor |
| R-C3 (Minor) | R-M2 | CONFIRMED Minor |
| R-C6 (Minor) | R-M3 | CONFIRMED Minor |
| R-V3 (Major) | R-M4 | CONFIRMED, downgraded to Minor |
| R-V10 (Minor) | R-M5 | CONFIRMED Minor |
| R-V11 (Minor) | R-M6 | CONFIRMED Minor |
| R-E6 (Minor) | R-M7 | CONFIRMED Minor |
| R-E7 (Minor, scope-adding) | R-M8 | CONFIRMED Minor, scope-adding |
| R-E8 (Minor, test) | R-M9 + "Tests to add" rows | CONFIRMED; converted to S2 test rows |
| CI-1 (orchestrator) | — | TEST-DEFECT |

Raw counts in: conformance 1B/1M/4m, conventions 2B/7M/2m, engineering 1B/4M/3m.
Verified out: **2 Blockers, 11 Majors, 9 Minors; 0 refuted-as-false; 3 reclassified** (R-V1 B→M, R-V2 B→M, R-V3 M→m) **+ CI-1 = TEST-DEFECT**.

## Verifications (my own evidence)

**R-1 / R-C1 — Grok -32602 no-cursor → wrong code.** `v_wire_32602.py`: `GrokWire.vendor_error(-32602)` on `session/new`, `session/resume`, `session/prompt` all return `grok.protocol_mismatch {'vendor_code':'-32602','method':…}` with the "upgrade Grok" next step; the cursor case returns `configuration.invalid_argument`. `MuseWire.vendor_failure(-32602)` returns `muse.api_error {'vendor_code':'-32602','vendor_error':'Invalid params'}`. Root cause `wire.py:55` `_MALFORMED_CODES = frozenset({-32700,-32600,_INVALID_PARAMS})`; the EC-41 branch (`code==_INVALID_PARAMS and cursor is not None`) runs before `_MALFORMED_CODES`. Spec line 685 defines the no-cursor case as `api_error`; EC-16 confirms. Reachable via EC-25/-31/-47. Fix verified safe: dropping `_INVALID_PARAMS` from `_MALFORMED_CODES` leaves the EC-41 branch intact.

**R-2 / R-E1 — Windows .cmd argv injection.** My own `v_cmd_injection.py` drove **`GrokHost`** (not the raw runner), default launcher resolution, PATH = shim-folder + System32, HOME empty. Resolved launcher = `…\shim\grok.CMD`. `spawn_grok_session(GrokTurnRequest(prompt="hi", model="x&echo>MODEL_MARK.txt"))` → `grok.process_exited` and `MODEL_MARK.txt` created in the workspace root. `run_grok_once(GrokOneShotRequest(prompt='hi" & echo pwned> PROMPT_MARK.txt & rem "'))` → `grok.protocol_mismatch` and `PROMPT_MARK.txt` created in the workspace. Both values pass their records (no whitespace / no leading `-` for the model; the prompt is unconstrained for content). `cli.py:9` documents that the code starts the `grok.cmd` shim; the acceptance fixture writes a `grok.cmd` on Windows (`test_grok_host_acceptance.py:60`), so the path is live. Spec §10 T-2 lists "argv injection (`model`…)" as the threat to prevent; the stated mitigation "values go into argv only in `--name=value` form (verified for Grok)" holds for `execve` but not a batch launcher (the BatBadBut class). D-19 already bans `.cmd` for `wsl.exe` for this reason; it was not applied to Grok. I never launched the real `grok`. Fix-interaction: see below.

**R-3 / R-C2 — default drain now bounded (INV-18).** Diff hunk at `transport.py:300-303`: `-await self._process.stdin.drain()` → `+await asyncio.wait_for(self._process.stdin.drain(), seconds)`, and `:314` sets `reason="timeout" if isinstance(exc, TimeoutError) else "stdin_write_failed"`. `_call_timeout(None)` returns `self.request_timeout` (`:393-398`), so the bound applies with the defaults. INV-18 allows only the dispatch fix and the `returncode` property as exceptions; the S3 report recorded only `close()`. Interacts with CI-1 (same drain path via `_write_frame`).

**R-4 / R-V9 — Muse reasoning_effort description.** `descriptions.py:100` text does not name the values; `MuseReasoningEffort` has 7 (`enums/native_hosts.py:95`); `DIRECTION_PARAMETER_DESCRIPTION` names its two. Field guide `model-facing-tool-contracts.md` "Centralize categorical vocabularies … derive … from those members".

**R-5 / R-E4 — Muse __aexit__ unbounded.** `muse_aexit_bound.py`: `silent_decide=False` → `__aexit__` 0.08 s; `silent_decide=True` → 9.06 s vs NFR-2 bound 3.60 s (shrunk timings; default control_timeout 30 s). `muse/host.py:148` `await asyncio.wait(tasks)` has no timeout and never closes peers after the grace (contrast `grok/host.py:127-131`); in-turn calls carry no `timeout_seconds` (`turn.py:130,212,233`). NFR-2 is P0, EC-8.

**R-6 / R-E3 — opencode single poll failure orphans server turn.** `opencode_poll_500.py`: one 500 on `GET /permission` → `wait raised: opencode.api_error`, `server still busy: {'type':'busy'}`, `aborts sent: 0`, `interrupt … was_running=False | aborts sent: 0`, `continue raised: opencode.session_busy`. `_COUNTED_FAILURES` is only `{OPENCODE_SERVER_UNREACHABLE, OPENCODE_PROCESS_EXITED}` (`turn.py:55`), so `_count_failure` (`:259`) re-raises a 500 at once; the `raise` paths (`:107,138,296`) send no abort, unlike EC-154/EC-155/the ceiling. INV-10/INV-13 intent; the watcher tests only assert aborts for the ceiling/host-exit/error-path/retry-limit/tree cases, never a single transient poll failure.

**R-7 / R-E5 — WSL read peers lack META_API_KEY/u.** `muse_wslenv.py`: turn peer WSLENV `WT_SESSION:META_API_KEY/u:VIDBYTE_PEER_MARK/u`; read peer WSLENV `WT_SESSION`. `launcher.py:128` `if mark is None: return NativeChildEnvironment.build({})`. §9.3 line 1552 ties `META_API_KEY/u` to the variable being set and `VIDBYTE_PEER_MARK/u` to WSL mode, not to being a turn peer. `test_muse_host_wsl.py:124` checks only the turn peer; no test pins the read peer.

**R-8 / R-E2+R-C5 — case-sensitive session ids.** `uuid_case.py` (fake Grok peer): same-case continue → `grok.session_busy`; upper-case continue → "ACCEPTED -> second live turn on 7FC9…". `turns.py:46` compares `session_id in self._busy_sessions` exactly; `validation.py:31` `_UUID_PATTERN` accepts `[0-9a-fA-F]` and does not normalize; `host.py:302` already lower-cases for one fork comparison, and `_check_fork_listing` (`:498,501`) / `check_fork_result` (`wire.py:339`) compare exact case. Adjudication of the two lenses: conformance (R-C5) framed it Minor (wrong row, nothing spent) + an unlisted EC-39 `!= target` trigger; engineering (R-E2) framed it Major (a second live turn → double spend, interleaved history). The engineering manifestation is the more serious and correct read, so the merged finding is Major. Fix must not tighten `require_uuid` (`test_grok_host_records.py:66` pins `SESSION.upper()` acceptance).

**R-9 / R-V2 — private bounds + validator bypass. Downgraded Blocker→Major.** Confirmed: `native_hosts.py:39-40`, `opencode.py:55-59`, `muse.py:40,42`, `harness_backends.py:31-34`, `validation.py:30`; `_URL_MAX_CHARS=2048` twice; `grok/turn.py:43 _DECISION_TITLE_MAX_CHARS=200`. The `NativeApprovalDecision.title` field is capped at 200 in Grok (`turn.py:170`) but 128 (`NATIVE_ID_MAX_CHARS`) in Muse (`turn.py:206,230`) and opencode; the record accepts ≤200 (`native_hosts.py:93`), so **no record fails at run time today** — the drift is a future risk, not a current defect. 29 inline record `raise ConfigurationError` lack `details["field"]` (native_hosts 4, opencode 17, muse 2, harness_backends 5, grok 1); most are cross-field invariants that cannot name one field. D-8, §12.4 line 1960, `strict-config-dataclasses.md` ("keep reusable validation bounds in the shared constants package") all bind. Downgraded from Blocker because there is no current wrong behavior, the gate does not enforce it, and main's own lib dataclasses carry private bounds (e.g. `agent_descriptor.py` 12, `config.py` 10) — weaker evidence — but it stays a real §12.4/field-guide grain gap with demonstrated cross-host drift, so Major.

**R-10 / R-V6 — duplicate launch logic.** Read `runner.py:147-173` and `managed.py:90-113`: same win32 `shutil.which`, same `create_subprocess_exec(..., start_new_session=sys.platform!="win32")`, same `FileNotFoundError`/`PermissionError`/`(OSError,ValueError)` ladder; `_READ_CHUNK_BYTES=65536` in both (`runner.py:27`, `managed.py:27`). FR-16 + principle 5.

**R-11 / R-V7+R-C4(muse) — duplicated texts, backtick drift.** `muse/host.py:69-70` keeps backticks in the EC-2/EC-3 steps; `grok/host.py:64-65` drops them (verified). Confirmed `_TRUE_TEXT/_FALSE_TEXT` and status-bound duplications across hosts. INV-7 is model-facing. R-C4's backtick observation is the same root and is merged here.

**R-12 / R-V8 — helper-to-helper chains.** `call_depth.py` over changed files: 16 chains, 0 nested defs. New ones: `from_configuration_error→invalid_argument→build`, `_read_balance→_check_balance_status→_vendor_text`, `_taskkill→_close_pipes`, `_call_timeout→_seconds_or_invalid_call`, `require_optional_text→require_text→_received`. §12.4 line 1953 + principle 1. The pre-existing transport chains in the output are out of scope (do not touch them).

**R-13 / R-V4 — A002 +23 hidden by stale baseline.** `a002_refs.py`: main `aa8c380c` = 600, head = 623; per-file deltas as listed in review.md. `lint/baseline.json` A002 = 703. INV-23 ("no baseline count rises") technically holds (623<703), so it is NOT a gate failure; but §11 line 1724 ("must not raise any count") measured against real main is breached, and §11 line 1814 / `class-bound-helpers.md:42` require `@intent` on the 25 newly flagged functions. The S3 "improved 703→623" claim is misleading.

**R-14 / R-V5 — spec-id comments.** 282 added `#` lines cite spec ids; `git grep` finds 0 on `origin/main` under `vidbyte/*.py`. AGENTS.md "docs/ is opaque" + principle 2 + `intent_based_commenting.md:11`. Header RELATED DOCS/TESTS id lines have main precedent. Bundled into R-15's reflow pass.

**R-15 / R-V1 — comment width. Downgraded Blocker→Major.** `awk 'length>72' | grep '^\s*#'` = 653 over 56 new files (+20 added transport lines). `comment-format.md` check fails; owner rejected the shape verbatim; spec §11 adopts it. Downgraded because `comment-format.md` is explicitly "Not a lint rule" (4,325/5,965 existing lines wider) and `python lint/run.py` = `SDK-LINT: PASS` — not gated, main not uniformly compliant. Stays a real, spec-adopted, owner-rejected lesson → Major.

**Minors** (confirmed, lower effort): R-M1 `OpencodeHost('not settings')` → `ConfigurationError` not `NativeHostError` (constructor `host.py:87` unwrapped). R-M2 `mcp_servers` public property (19 public members; caller `session_tools.py:214`). R-M3 `list_harness_backends` returns a bare tuple → JSON array (`tools.py:49`), so deviation 7's "every tool output is a JSON object" is false. R-M4 free-text `.code()` (45 literal + 5 dynamic, all resolve). R-M5 `MuseWire._ERRORS` module-level factory. R-M6 header overclaims. R-M7 Muse `_decisions.append` unconditional (cap only at build). R-M8 fresh `httpx.AsyncClient` per request (`transport.py:61`) — scope-adding.

## CI-1 adjudication — TEST-DEFECT

Failing test: `tests/features/grok_host/test_grok_host_turns.py:335` `test_interrupt_raises_process_exited_when_the_cancel_write_fails` (`@posix_only`, EC-51). CI run 38379243965 on `9d51a3fb` failed identically on Linux Python 3.12 (both attempts), passed on 3.11 (`.../scratchpad/ci-38379243965-failed.log` lines ~807-848: "DID NOT RAISE … NativeHostError"); final `1 failed, 5572 passed, 31 skipped`.

Mechanism, from the code and asyncio semantics (I cannot run Linux 3.12 here; the test is `@posix_only` and skips on this Windows box):
- EC-51's trigger is "the peer has already **exited**". The fixture does not exit the peer — `fake_grok_peer.py:333` `close_stdin_hold` calls `close_stdin()` (`sys.stdin.close()` + `os.close(0)`) then `held()` then `os._exit(0)`, so it stays alive with its stdin read end closed while the driver still sees it as RUNNING. The test gates on `_stdin_closed` before interrupting, so the close has happened.
- `interrupt_grok_turn` → `GrokTurnDriver.interrupt` (`turn.py:132`) → `NativePeer.notify` → `McpStdioTransport._write_frame` (`:377`) which writes the `session/cancel` frame then `await asyncio.wait_for(process.stdin.drain(), seconds)`; a `BrokenPipeError`/`ConnectionResetError` there becomes `McpProtocolError(reason="stdin_write_failed")` → `grok.process_exited`.
- I read `_UnixWritePipeTransport.write` and `StreamWriter.drain` in 3.11 and 3.13: both are byte-identical. The only structural difference is `asyncio.wait_for`: on 3.11 it wraps the awaitable in a child Task (`ensure_future`); on 3.12+ it runs the coroutine inline under `async with timeouts.timeout(...)`. Awaiting a coroutine inline still yields at the `drain()`'s `await sleep(0)`, so a `ConnectionResetError` raised by `_drain_helper` propagates out of the timeout context — the wrapper does not swallow it.
- A genuinely exited peer (the real EC-51 condition) closes every read FD, so the parent's next `os.write` gets a deterministic `EPIPE` on every Python version, and the transport maps it to `grok.process_exited` correctly. The non-determinism lives entirely in the fixture's "close stdin, stay alive" proxy, whose broken-pipe surfacing is version-fragile.

Conclusion: the production contract and code are correct; the `@posix_only` EC-51 fixture's simulation of "peer exited" is unreliable across the 3.11/3.12 CI matrix. Per the pipeline rule, only the S2 test author may change a test, so I record this as TEST-DEFECT, not an open code row, and route the fixture fix to S2. CI must end green via that fix.

Open lead handed to the test author before they edit: run on Linux 3.12 whether bare `await self._process.stdin.drain()` raises `ConnectionResetError` while `await asyncio.wait_for(drain(), seconds)` does not, against the same closed-read-end pipe. If bare drain raises and the wrapped form does not, CI-1 is a code regression from R-3's `wait_for` wrapper (fix R-3 Option A would then also fix CI-1), not a fixture issue — so run that one-line experiment first. My static reading says the wrapper does not suppress the error, hence TEST-DEFECT, but I could not execute it on 3.12.

## Reviewer disagreements adjudicated
- **R-C5 (Minor) vs R-E2 (Major)** — same root (case-sensitive session ids). Took Major: the engineering lens's double-live-turn/double-spend manifestation is the more serious and correct consequence; R-C5's EC-39 `!= target` sub-point is folded in as a record-and-casefold item (R-8).
- **R-C4 (Minor) muse-backticks vs R-V7 (Major) duplicated texts** — same backtick drift; merged into R-11. R-C4's distinct "opencode constructor unwrapped" half kept as Minor R-M1.
- **R-V1/R-V2 Blocker (conventions) vs the gate being green** — both are real field-guide-lesson violations but neither is gated and main does not uniformly follow either; downgraded to Major per the briefing's "downgrade only with a quoted reason" (quotes in the refuted table). R-V3 Major→Minor for the reasons in the refuted table.

## Fix-interactions for the repair agents
- **R-2 ↔ AC-1 Windows.** Refusing a resolved `.cmd` launcher breaks AC-1's Windows acceptance test, which resolves `grok.cmd` via PATH (`test_grok_host_acceptance.py:60`, `write_grok_shim`). The other Grok tests use an explicit `grok_command` (`[sys.executable, fake]`), which the fix must still allow. The repair agent cannot edit the frozen acceptance test; this needs the S2 author to switch AC-1's Windows shim to a non-`.cmd` launcher (or exercise the explicit-command seam). Flag to the orchestrator.
- **R-3 ↔ CI-1** share the transport drain. If the Linux-3.12 experiment above shows the `wait_for` wrapper suppresses the error, fix both via R-3 Option A.
- **R-8 ↔ R-9/R-11** — R-8 lower-cases ids; R-9 moves the title/bound constants; R-11 unifies the next-step texts/bounds. Touch `native_hosts` constants once.
- **R-9, R-11, R-M1, R-M6** all touch the shared bounds / next-step texts / constants header; do them in one pass.
- **R-14 ↔ R-15** — strip spec-ids while reflowing the comments (one pass), and keep each `@intent` within 20 lines of its `def` so A002 does not rise further.
- **R-13** adds `@intent` to 25 functions; `a002_refs.py` names them; this interacts with R-15's reflow (keep the new `@intent` lines ≤72 cols).

## Commands run
- `PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/{grok_host,opencode_host,muse_host,native_backends}` → `1616 passed, 19 skipped in 145.55s`.
- `PYTHONPATH=$(pwd) python lint/run.py` → `SDK-LINT: PASS`.
- `s4-verifier/v_cmd_injection.py` (R-2, via GrokHost + fake grok.cmd); `s4-verifier/v_wire_32602.py` (R-1); engineering scratch `uuid_case.py` (R-8), `opencode_poll_500.py` (R-6), `muse_aexit_bound.py` (R-5), `muse_wslenv.py` (R-7).
- `a002_refs.py` (R-13: 600→623), `code_calls.py` (R-M4: 45 literal + 5 dynamic, 0 unresolved), `call_depth.py` (R-12: 16 chains, 0 nested defs).
- `awk 'length($0)>72' | grep -cE '^\s*#'` over the 56 new files (653) and added transport lines (R-15); `git grep` spec-id comments (R-14: 282 head / 0 main).
- Read of asyncio `wait_for`/`StreamWriter.drain`/`_UnixWritePipeTransport.write` in 3.11 and 3.13 and the saved CI logs (CI-1); constructor refusals for R-M1; `OpencodeHost.mcp_servers` + public-member counts (R-M2).
