LENS: conformance (post-repair re-review)
VERDICT: MERGEABLE AFTER FIXES — All 21 fixes hold and the iteration-2 refactors (R-9 to R-12) introduced no regression, but three Major conformance gaps remain: an upper-case vendor session id bypasses INV-14, a child-session 404 skips the EC-158 abort, and Grok/Muse approval titles are not scrubbed.

Reviewed: `git diff origin/main...b0e35a32` (merge-base 8387d666), every code change since S3_HEAD de5b7c4c including merge 3cdd9704, against spec r8. The worktree HEAD is f69b0bd3; it differs from b0e35a32 only in `docs/.../pipeline.md`, and af3e05e8..b0e35a32 is docs-only, so the code under test is identical.

FIXES CONFIRMED (one line per fixed finding: ID — holds | does not hold — evidence)
- R-1 — holds — I ran `GrokWire.vendor_error` with -32602 directly. On session/new, session/resume, session/prompt and session/list without a cursor it gives `grok.api_error` with `{vendor_code: "-32602", vendor_error}`. On session/list with a cursor it gives `configuration.invalid_argument` with field `cursor`. `_MALFORMED_CODES` is now {-32700, -32600} (wire.py:51,244-247). This matches EC-16, EC-41 and the Muse twin EC-102.
- R-2 — holds — By reading `GrokCli.resolve_launcher` (cli.py), the resolved program is checked for an explicit and for a found launcher, and the resolved path is kept. The `~/.grok/bin/grok.exe` fallback applies only when no explicit `grok_command` is set. `__aenter__` raises `grok.not_installed`, and `_BATCH_LAUNCHER_NEXT_STEP` (host.py) equals EC-157's next step word for word. `test_grok_host_windows_launcher.py` passes on win32 and is not skipped. A probe of `_is_batch` refuses `.cmd`, `.BAT`, `.cmd. ` and `.CMD.`, and accepts `.exe` and `.com`. AC-1 runs through the seam (see §4 below).
- R-3 — holds — In `request()`, `write_seconds` is None unless `timeout_seconds` is given, so the default path does a plain `drain()`. Main's suites still pass: test_mcp_stdio_transport, attachment, discovery, fork_tool and agent_fork_isolation gave 115 passed. The PR does not touch those files. INV-18 holds.
- R-4 — holds — The live `MuseTools` schema for spawn_muse_session and continue_muse_session has `reasoning_effort.enum = ['none','minimal','low','medium','high','xhigh','ultra']`. That list is §9.1 `MuseReasoningEffort` in declaration order. The description names the same seven values, read from the enum, and repeated `spec()` calls give the same schema.
- R-5 — holds — `MuseHost.__aexit__` runs these steps:
  1. it shuts every driver down;
  2. it waits for the tasks at most `NATIVE_STOP_GRACE_SECONDS`, read through the module;
  3. it closes every driver's peer concurrently;
  4. it waits for the tasks.

  `test_aexit_returns_within_the_bound_when_a_peer_is_silent_on_decide` passes on win32 and is not skipped.
- R-6 — holds — `abort_before_failing` sends one bounded, best-effort `POST …/abort`. It sends nothing in three cases: `_server_ended` is set (by `_result`, which covers EC-82 to EC-85 and no_reply), the server already answered an abort (`_abort_deadline` is set only after a successful POST), or the error is the recorded `fail()` error. `_drive` calls it in both `except` branches. A failed abort is dropped and the turn's code is unchanged. The R-6 regression tests pass. The exemption is keyed on the failure code, which leaves one edge open; see R-RR2.
- R-7 — holds — `peer_environment` adds `META_API_KEY/u` to `WSLENV` for every WSL peer when the variable is set, and the mark entry only for a turn peer. A native peer's environment is unchanged. The R-7 test in test_muse_host_wsl.py passes.
- R-8 — holds — Every `require_uuid` site now lower-cases the id: Grok host.py:279, 322 and 324, and Muse host.py:275, 311, 368, 401 and 509. The fork checks compare in lower case: host.py:540 and wire.py:349-350. test_grok_host_session_id_case.py passes 5/5. This fixes the original trigger, an upper-case id supplied by the caller. A vendor-returned id is still bound verbatim; see R-RR1.
- R-9 — holds — Every length bound moved to `lib/constants/native_hosts.py` keeps its value. `NativeApprovalDecision.title` is checked with `require_text(..., allow_blank=True)`, which accepts the same values as before. All three drivers cap the title with `NATIVE_APPROVAL_TITLE_MAX_CHARS` = 200; Muse and opencode were at 128, as intended. `RecordFieldConverter.require_url` matches the old inline checks: https with a host, plain http only to loopback for opencode, and no user info, query or fragment for `server_url`. The only change is that `details["field"]` is now set.
- R-10 — holds — `CliRunner.launch` contains the old `_start`/`_launch` body unchanged: the win32 `shutil.which` lookup, `start_new_session` on POSIX, and the same `ProcessLaunchFailure` mapping. `ManagedProcess.start` passes DEVNULL, and `run` passes a pipe or DEVNULL as before. The read chunk is still 65536.
- R-11 — holds — Each removed literal equals its replacement constant. A script compared all 55 entries of `NATIVE_HOST_NEXT_STEPS` with the §6.3.1 table (backticks and the implementer notes left out, as the table's preamble says): 55/55 match. Muse's EC-2 and EC-3 steps lost their backticks, which is the one intended visible change. `-32601` and "Method not found" are shared.
- R-12 — holds — The five chains are gone:
  - `from_configuration_error` builds directly, with the same code, next step and `context["field"]` as `invalid_argument`;
  - `_check_balance_status` receives the vendor text;
  - `stop_tree` calls the leaf helpers `_start_taskkill` and `_wait_taskkill`, and `_close_pipes(killer)` runs in its `finally` (`None` is a no-op);
  - `_text_problem` is a leaf;
  - `_call_timeout` was removed.

  The behaviour is the same in each case.
- R-13 — holds — I ran A002 at HEAD: 577 findings in total (baseline 703), and 0 in the 56 new files. The 8 findings in modified files (errors/base.py ×4, transport.py ×4) belong to functions that already exist on origin/main.
- R-14 — holds (scoped to inline `#` comments) — 0 added `#` lines in `vidbyte/` cite a spec id. Header fields still cite them; see R-RR4.
- R-15 — holds — 0 added `#` lines in `vidbyte/` are longer than 72 columns, whether counted in characters or in bytes (`LC_ALL=C awk`).
- CI-1 — holds — With a deadline, `_send` and `_write_frame` raise `BrokenPipeError` when `stdin.is_closing()` after the drain. `NativePeer.call` and `send` default to the control timeout, and `notify` and `answer` always pass it, so every Grok and Muse write is bounded and checked. `gh run view 38418651864` shows success for Source 3.12, Source 3.11 and Package at af3e05e8, which has the same code as b0e35a32.
- R-M1 — holds — `OpencodeHost("not settings")`, `GrokHost(...)` and `MuseHost(...)` each raise `NativeHostError configuration.invalid_argument` with `context={"field": "settings"}` and the next step "Fix the settings argument and call again."
- R-M2 — holds — §17 deviation 9 records the read-only `OpencodeHost.mcp_servers` property. The code matches it, and 18 methods plus the property gives 19 public members.
- R-M3 — holds — §17 deviation 7 now says `list_harness_backends` returns a bare JSON array. The live tool output starts with `[{"allowed_harnesses": …`.
- R-M6 — holds — The constants header now says it holds the shared values and keeps single-reader values beside their reader. Only `_CREDENTIAL_BYTES` (opencode/server.py) and `_NANOSECONDS_PER_MILLISECOND` (muse/wire.py) remain as single-reader values. The validation.py header names both `RecordFieldValidator` and `RecordFieldConverter`.
- R-M9 — holds — The regression tests from 96df0b45 are present. `git diff 96df0b45 b0e35a32 -- tests/features/` changes only `coding_agent/test_coding_agent_web_fetch.py`, and that change is identical to origin/main. All of the regression tests pass.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets)
- I ran the §4 snippet verbatim, with PATH limited to Python and System32 and USERPROFILE pointing at an empty folder. It printed exactly `grok.not_installed -> Install Grok Build 1.0.13 or newer, or set GrokHostSettings.grok_command.` The AC-1 fake outcome (`completed …`) passes through the r8 `grok_command` seam.
- The scope is exact:
  - the 68 files touched outside docs/ and tests/ are exactly the 68 paths in §12.3, with none extra and none missing;
  - the INV-22 paths, `lint/`, `mcp_server/`, `harnesses/__init__.py` and `pyproject.toml` have empty diffs;
  - `FailureCode` only appends members;
  - the §8.4 budget recounts exactly: 56 new and 12 modified files, 66 records, 13 enums, 46 functions, 43 tools (10, 18, 12 and 3) and 4 toolsets;
  - NFR-4 holds: the largest new module, `opencode/host.py`, has 790 lines.
- The refactors are faithful. All four packs pass (1638 passed, 19 skipped). The removed private constants are equal to the shared constants that replace them. Every host's public method still has the four-handler `try` (CancelledError, NativeHostError, ConfigurationError, then Exception mapped to runtime.error). `list_harness_backends` is the one exception: it returns a constant with no I/O, as §6.3.6 allows.
- §14 Never items:
  - none of the bypass strings (`--dangerously-skip-permissions`, `--yolo`, `--always-approve`, `yoloMode`, `bypassPermissions`, `dangerously_allow_all`, `--dangerously-unauthenticated`) appears in added `vidbyte/` lines except in two "do not" header notes;
  - added `vidbyte/` lines have 0 `noqa`, `type: ignore`, `pragma: no cover`, `nosemgrep` or `pylint: disable` markers;
  - no test was weakened;
  - the timing constants are never imported with `from … import` and never bound as default arguments (§9.3).

FINDINGS (ranked, max 15)
R-RR1 [Major] [conformance] vidbyte/harnesses/native/grok/host.py:216 — INV-14 is enforced only for ids the caller passes, so an upper-case vendor session id lets a second live turn start on the same session
  Evidence: The spawn path binds the id from `session/new` verbatim through `GrokWire.parse_session_id`, whose pattern is `^\S+$` with no lower-casing (wire.py:208-213), and `_turns.bind_session(turn_id, session_id)` (host.py:216). Muse does the same at muse/host.py:243. `NativeTurnTable.reserve` and `is_session_busy` compare exactly (hostkit/turns.py:47, 92), but §8.5 says `reserve` matches Grok and Muse ids ignoring letter case. Repair-1 says ids are lower-cased "at every site that calls require_uuid", and the spawn path never calls it.

  I reproduced this with a scratch test using the pack's GrokFake. The scenario set `session_new.result.sessionId` to `ABCDEF01-2345-4678-89AB-CDEF01234567` and held `session_prompt`. After `spawn_grok_session(...)`, `continue_grok_session("abcdef01-…")` was ACCEPTED as a second live turn instead of being refused with `grok.session_busy`, and a second peer started.
  Failure: Two live turns run on one session. That is the double spend and interleaved history R-8 was raised for, and it breaks INV-14 ("An id and its upper-cased form name the same session") and EC-29 and EC-112. A Grok or Muse release that returns upper-case UUIDs triggers it. Today's vendors appear to return lower case, which limits the practical exposure.
  Smallest fix: Do the case folding inside `NativeTurnTable` for GROK and MUSE: `reserve`, `bind_session`, `is_session_busy`, and the keys used by `release` and `_finish`. That is what §8.5 places on `reserve`. Alternatively, lower-case the id in `GrokWire.parse_session_id` and at the Muse spawn bind. Add a test that spawns with an upper-case vendor id and then continues.
  Spec IDs: INV-14, EC-29, EC-112, §8.5 `NativeTurnTable.reserve`, §12.3 rows 30 and 41
R-RR2 [Major] [conformance] vidbyte/harnesses/native/opencode/turn.py:195 — The EC-158 exemption is keyed on the failure code, so a 404 from a child session's `children` call fails the turn with no abort
  Evidence: `_refresh_tree` calls `GET /session/{child}/children` with `not_found=OPENCODE_SESSION_NOT_FOUND` (turn.py:251). `_count_failure` does not count that code and re-raises it, and `abort_before_failing` returns early for any `OPENCODE_SESSION_NOT_FOUND`. I reproduced this with a scratch test using the pack's FakeOpencodeServer: a child `ses_child000` of `ses_known0001`, whose `children` route returns 404, and a held turn with a permission request from an unknown session. The results were:
  - outcome: `opencode.session_not_found`;
  - aborts sent: `[]`;
  - children calls: `['ses_known0001', 'ses_child000']`;
  - the server-side turn was still held.
  Failure: EC-158 exempts only "a 404 for the session (EC-86, EC-90)", meaning the turn's own session. This 404 is for another session, so EC-158 requires the abort. Without it, the server turn keeps running and spending with no one answering its permission requests. The code also tells the caller the turn's session is gone when it is not. EC-154 says a failed `children` call counts as a failed poll.
  Smallest fix: Exempt the abort only when the 404 was for `self._session_id`. For example, pass a different `not_found` code, or no override, on non-root `children` calls, or check the session id in `abort_before_failing`. Add a pack test for a child 404 during the walk.
  Spec IDs: EC-158, EC-154, EC-86, EC-87, INV-13
R-RR3 [Major] [conformance] vidbyte/harnesses/native/grok/turn.py:177 — Grok and Muse record approval titles unscrubbed, but §9.1 requires `NativeApprovalDecision.title` to be "scrubbed" and opencode scrubs it
  Evidence: Grok uses `title=permission.title[:NATIVE_APPROVAL_TITLE_MAX_CHARS]` with no `scrub`. Muse does the same at muse/turn.py:211 and 235. opencode/turn.py:268 uses `self._errors.scrub(...)` and then the cap. I reproduced this with a scratch test using GrokFake: a permission request whose title holds a synthetic `OPENAI_API_KEY=sk-proj-FAKE…`. The recorded `result.decisions[0].title` keeps the value verbatim, while `NativeErrorFactory.scrub` of the same text gives `OPENAI_API_KEY=<redacted>`. R-9 aligned the cap across the three drivers but not the scrub. The gap has existed since S3; it is in scope because R-9 edited these lines.
  Failure: A credential that the Grok agent writes into a tool-call title reaches `NativeTurnResult.decisions`, and `NativeResultEncoder` writes it into `wait_grok_turn`'s ToolResult output. INV-6 lists ToolResult output, and T-6 says vendor text is returned scrubbed.
  Smallest fix: Wrap the title in `self._errors.scrub(...)` before the cap in `GrokTurnDriver._answer_permission` and in both `MuseTurnDriver` sites, as opencode does.
  Spec IDs: §9.1 `NativeApprovalDecision`, INV-6, T-6
R-RR4 [Minor] [conventions] vidbyte/harnesses/native/grok/turn.py:5 — Header fields other than RELATED DOCS and TESTS still cite spec ids; R-14 removed them only from inline `#` comments
  Evidence: Spec ids remain in 86 added header lines outside RELATED DOCS: ARCHITECTURE NOTE 30, WHAT NOT TO DO 21, KNOWN EDGE CASES 20, ROLE IN CODEBASE 10, FUNCTION INVENTORY 3 and PURPOSE 2. One method docstring cites one too (muse/host.py:505, "(D-14)"). An example is grok/turn.py:5, "… (D-2, D-23) … (EC-53, D-10)". Repair-3 kept only RELATED DOCS and TESTS ids by design.
  Failure: These lines have R-14's problem: to decode the ids, a reader must open `docs/`, which AGENTS.md treats as opaque.
  Smallest fix: Strip the ids from the non-RELATED DOCS header fields and from that docstring, as f067088d did for comments.
  Spec IDs: R-14; AGENTS.md (docs/ opaque); spec §11 comment rules

VERIFIED CLAIMS:
- §4 / AC-1: I ran the snippet verbatim, extracted from spec.md, with no grok reachable. It exited 0, its stdout was exactly the not_installed line, and stderr was empty. Both `test_grok_host_acceptance.py` snippet tests pass.
- Repair-3 "A002 577 at HEAD": confirmed 577, with 0 in new files. "The only per-file difference is transport.py 6 → 4": transport.py now has 4 findings, all on functions that exist on main.
- Repair-3 "opencode/host.py is now 790": confirmed 790. It is the largest new module and stays within NFR-4.
- Repair-3 gate 1 "1638 passed, 19 skipped": my run of the four packs gave 1638 passed, 19 skipped in 144.90 s.
- Repair-3 remote CI 38418651864: success for 3.12, 3.11 and Package, with headSha af3e05e8.
- Repair-1 R-1, R-M1 and R-4: each reproduced as stated (see FIXES CONFIRMED).
- Repair-3 R-14 and R-15: 0 inline comments cite spec ids, and 0 comment lines are longer than 72 columns in characters or bytes. Both confirmed.
- Repair-2 R-11 "the only visible change is Muse's backticks": confirmed, since 55/55 next steps match §6.3.1 and every removed literal equals its constant.
- Repair-1 R-8 "lower-cased at every site that calls require_uuid": true as worded, but the spawn path never calls `require_uuid`. This is R-RR1.
- Repair-2 R-9 text says `require_text(..., allow_blank=False)` covers the fields that may be empty. The code passes `allow_blank=True`, so the report has a typo and the code is right.
- §8.4: 56 new and 12 modified files, 66 records, 13 enums, 43 tools and 4 toolsets, counted from the code. 46 functions = 10 Grok + 18 opencode + 12 Muse + 6 backend.
- §12.3: `comm` of the 68 extracted paths against the files touched outside docs/ and tests/ shows 0 extra and 0 missing.
- §5: the Grok call path matches the diagram:
  1. `__aenter__` resolves the launcher;
  2. `_reserve` reserves a slot;
  3. `peer_argv` is `agent --no-leader [--model=…] stdio`;
  4. `initialize` runs, then the model check;
  5. `session/new`, then `bind_session`;
  6. `_launch` sends `session/prompt` with a bounded write and hands the turn to the driver;
  7. the handle is returned.

  On every early exit, `finally` releases the reservation and closes the peer.

COMMANDS RUN:
- Inspection:
  - `git diff --stat|--name-status origin/main...b0e35a32`, `de5b7c4c..b0e35a32` and `3cdd9704..b0e35a32`;
  - `git log --oneline de5b7c4c..b0e35a32` and `b0e35a32..HEAD`;
  - `git show 7f61f927 / 616e8a0f / 5a7e09de / 3c896557 / 96df0b45`;
  - per-file code-only diffs (comments filtered out) of every file the PR touched after the merge;
  - `git diff 96df0b45 b0e35a32 -- tests/features/`;
  - the INV-22 and `lint/` diffs;
  - `git status --porcelain`, which stayed empty, and a `find -newer` check showing no repo file was modified.
- Python checks (`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python`):
  - next-step table versus §6.3.1;
  - Muse schema enum;
  - three host constructors;
  - `GrokWire.vendor_error` -32602 matrix;
  - `_is_batch` probe;
  - `list_harness_backends` tool output;
  - tool and method recount;
  - `shutil.which('grok')` on 3.11 and 3.13, which only resolves the path and runs nothing.
- §4 snippet: `python scratchpad/rr/run_s4.py`. PATH was Python plus System32 and USERPROFILE an empty scratch folder. An assert guarded that no grok was reachable before the run.
- Tests (all with `-p no:cacheprovider`):
  - `pytest -q -x tests/features/{grok_host,muse_host,opencode_host,native_backends}` gave 1638 passed, 19 skipped;
  - `pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_attachment.py tests/test_mcp_discovery_tools.py tests/test_fork_tool.py tests/test_agent_fork_isolation.py` gave 115 passed;
  - `pytest -q -rs` on windows_launcher, session_id_case, acceptance, the R-6 watcher test, muse wsl and muse process_bounds gave 61 passed, 4 skipped. The four skips are POSIX-only by spec §13.
- Scratch reproductions, outside the repo, using the pack conftests: `test_rr_inv14.py` (R-RR1), `test_rr_ec158_child404.py` (R-RR2) and `test_rr_title_scrub.py` (R-RR3).
- Lint: `python -m lint.run --rule A002 --format json --all`, with output redirected to the scratchpad. I counted the findings in the PR's new and modified files.
- Remote CI: `gh run view 38418651864 --json conclusion,headSha,jobs`, which is read-only.
- Counts:
  - spec ids in added comments;
  - comment width, measured in characters and with `LC_ALL=C`;
  - bypass strings;
  - suppressions;
  - header fields that cite spec ids;
  - module line counts.
- No commits, installs, pushes, `git add` or `git stash`. The real `grok`, `opencode`, `muse` and `wsl.exe` were never launched, and no credential file was read.
