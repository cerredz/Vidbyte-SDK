LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the stream, wait, side-chat, goal and worktree layers are well built and 29 of 33 runtime mutants are killed, but one weighted-word failure path (raw OSError from the worktree), one unsafe goal-resume cleanup gap, one EC-19 data-loss path and three untested bound or start rules need fixing before merge.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The stream log is sound where it is tested.** The reading count is scoped to the generator (`turn_stream.py:180-201`), and refunds go through one `charge_stream`. The GAP arithmetic uses bisect, and ENDED is kept outside the bounds. Runtime mutants of release, the decrement, both refunds, GAP off-by-one, sequence spending and the host event bound are each killed by a named test (mutants S1, S2, S3a, S4, S5, S6, S8b).
- **R-11 has not regressed.** There is no `asyncio.shield` in `turn_starts.py`, `connection.start` or `stream_methods.py`. `wait_codex_turns` waits with `asyncio.wait`, which never cancels the `ended` futures. `CodexTurnsWaitRequest` refuses an empty or duplicated handle list (`codex_host_inputs.py:473`), so `asyncio.wait` never gets an empty set. The W1 and W2 mutants are killed.
- **Side-chat posture and cleanup are correct and well tested.**
  - The fork runs with `starts_turn=True`, so the D-36 reviewer check comes before the handler is shared.
  - A failed inject or start calls `release_tools`.
  - The tool sends `approvalPolicy: "never"` on both `thread/fork` and `turn/start`.
  - All five side-chat mutants (C1 to C5) are killed.
- **Goal control and history changes are well tested.**
  - Resume refuses unresumable goals before `thread/resume`, and the budget check uses `<=`.
  - The edit checks the budget echo.
  - `_change_idle` reserves before its first await and releases in `finally`.
  - The load guard and the idle guard both hold.
  - Mutants G1 to G5, H1, H2, L1, L2, E1, R1, P1, T1, T2 and K2 are all killed.

## FINDINGS

R-E1 [Blocker] [error handling] vidbyte/harnesses/native/codex/thread_methods.py:162-166 — `create_codex_worktree` lets a raw `FileExistsError` or `RuntimeError` reach the caller
- Evidence: `Path.home()` (line 162), `target.exists()` (164) and `root.mkdir(parents=True, exist_ok=True)` (166) run with no handler. A probe on a real host exposed both failures:
  - With `Path.home` patched to a regular file: `PROBE home-file: builtins.FileExistsError: [WinError 183] Cannot create a file when that file already exists: 'C:\...\home-is-a-file'`.
  - With `Path.home` raising as it does when HOME cannot be resolved: `PROBE home-unresolvable: builtins.RuntimeError: Could not determine home directory.`
- Failure:
  - A read-only, missing or file-shaped home raises an untyped exception. Examples are a container with an arbitrary UID or a CI sandbox.
  - The exception carries a local path in its text, with no packet, cause or next step.
  - It breaks INV-2 ("Every failure a new method raises is one of two kinds") and the request's weighted words, "exception handle everything that could potentially go wrong" (request.md §D).
  - No test covers this path.
- Smallest fix:
  - Wrap lines 162-166 in `except (OSError, RuntimeError) as exc`.
  - Raise `CodexErrorMapper.error(FailureCode.CONFIGURATION_INVALID_ARGUMENT, <new CODEX_HOST_WORKTREE_ROOT_MESSAGE naming only type(exc).__name__>, operation, likely_cause=..., next_step=...)`.
  - Add one test that patches `pathlib.Path.home` to a file.
- Spec IDs: INV-2, INV-9, INV-29, FR-35, request.md §D.

R-E2 [Major] [pre-mortem] vidbyte/harnesses/native/codex/turn_starts.py:203-218 — a resume whose `thread/goal/set` Codex applied but whose answer fails to parse leaves the goal active and an untracked paid goal turn running
- Evidence:
  - `sent = True` is set only after `activate()` returns (line 208). So when the request reached Codex and the response then fails validation, no cancel is sent.
  - openai-codex's own `_start_goal_operation`, whose order this step copies, cancels on every failure except a JSON-RPC refusal before activation: `if activated or not isinstance(exc, InvalidRequestError): self.cancel_goal_operation(state)` (`openai_codex/client.py:643-645`).
  - In a probe, `before_response` removed `goal` from the active set's answer. The fake had already applied the set and started a goal turn. The probe printed:
    ```
    PROBE resume malformed: CodexAgentError code=codex.protocol_mismatch
    PROBE goal calls: ['finish', 'unregister_goal_operation']
    PROBE goal status at Codex: active
    PROBE fake turns: [('turn-1', 'completed'), ('turn-2', 'inProgress')]
    PROBE host tracks a run on thread: False
    PROBE goal sets: ['active'] interrupts: 0
    ```
- Failure:
  - The caller is told the resume failed, while Codex runs the goal on its own, spending tokens up to its budget.
  - The host has no handle to wait on, cap or stop it, and nothing is paused or interrupted.
  - This contradicts the code's own intent label, `a-resume-cancels-only-a-goal-it-set-active`: here it did set the goal active.
  - The trigger is the protocol-drift path that D-4 exists for.
- Smallest fix:
  - Set `sent = True` before `activate()`.
  - Skip the cancel only when the error is Codex's JSON-RPC answer, `isinstance(exc, sdk.JsonRpcError)` (the EC-37 case). Every other failure after the write then pauses and interrupts.
  - Add the probe above as a test that asserts `START_FAILURE_CLEANUP`.
- Spec IDs: INV-31, EC-37, EC-38, INV-7, D-4.

R-E3 [Major] [data and scale] vidbyte/harnesses/native/codex/turn_stream.py:139-145 — one event larger than the character bound wipes the whole kept window before being dropped, so a lagging subscriber loses unrelated events
- Evidence:
  - `while self._events and not self._fits(size): self._drop_oldest()` evicts every kept event before `_fits` can fail for good.
  - Probe: the text limit was 300, the subscriber read event 1 and lagged over events 2 and 3, then a 1000-character diff arrived. The probe printed `kept before diff: (15, 3)`, then `kept after diff: (0, 0)`, `kinds: ['message_delta', 'gap', 'message_delta', 'item_completed', 'ended']`, `(seq,dropped): [(2, 3)]` and `texts: ['Hi', '!']`. The two small deltas, " there" and " friend", are lost.
  - EC-19 says subscribers "see `GAP(dropped=1)` in its place".
  - The EC-19 test (`test_codex_host_stream_wait.py:346-359`) cannot show this. Its subscriber has already read everything kept before the diff, so eviction and non-eviction produce the same output.
- Failure:
  - `turn/diff/updated` carries the turn's whole diff, which EC-19 itself names as the oversize case. Once a turn's diff passes 2,000,000 characters, every later diff update empties the window again.
  - A subscriber that is not fully caught up loses every delta and item between diffs, not just the diff.
  - The same applies to an event larger than `CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS`.
- Smallest fix:
  - Before the loop, drop and count only the new event when `size > CODEX_HOST_STREAM_TEXT_LIMIT_CHARS` or, once attached, `size > CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS`. That event can never fit, which matches INV-20's "an event that alone passes the character bound is dropped and counted".
  - Verified: with only the turn-bound half applied at runtime (mutant S9), all 225 tests pass, and the probe yields `['message_delta', 'message_delta', 'message_delta', 'gap', ...]` with `(seq,dropped): [(4, 1)]`.
  - Make the EC-19 test lag its subscriber over at least one event.
- Spec IDs: INV-20, EC-19, NFR-3.

R-E4 [Major] [test quality] vidbyte/harnesses/native/codex/turn_stream.py:233,237 — neither the cumulative per-turn character bound nor the per-host character bound is exercised by any test
- Evidence:
  - Mutant S3c replaced `self._chars + size <= CODEX_HOST_STREAM_TEXT_LIMIT_CHARS` with `size <= ...`. It survived: `S3c-fits-ignores-cumulative-turn-text rc=0 | 225 passed in 14.11s`.
  - Mutant S3b replaced `host_chars + size <= CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS` with `True`. It survived: `S3b-fits-ignores-host-text rc=0 | 225 passed in 11.29s`.
  - `grep TEXT_LIMIT_CHARS tests/` finds only the constant table (`codex_host_feature_support.py:134,136`) and one patch of the per-event case (`test_codex_host_stream_wait.py:348`).
- Failure: an implementer could drop either character bound, and no test would fail. If both went, a host's kept stream memory would be capped only by event count: 65,536 events, each up to 2,000,000 characters. NFR-3 and D-39 promise a character bound.
- Smallest fix: add two stream tests.
  - A per-turn test: patch `CODEX_HOST_STREAM_TEXT_LIMIT_CHARS` to 300, emit six 100-character deltas to a lagging subscriber, and assert `kept(host)[0] <= 300` and the GAP count.
  - A per-host test: patch `CODEX_HOST_STREAM_HOST_TEXT_LIMIT_CHARS` across two turns, mirroring the AC-44 event test.
- Spec IDs: INV-20, AC-44, EC-62, D-39, NFR-3.

R-E5 [Major] [test quality] vidbyte/harnesses/native/codex/turn_stream.py:174-178 — INV-22's start rule for a subscription made mid-turn, "the oldest event the log keeps", has no test
- Evidence:
  - Mutant S7 replaced `start = self._events[0].sequence if self._events else self._next` with `start = self._next`. It survived: `S7-subscribe-starts-at-next rc=0 | 225 passed in 16.96s`.
  - Every stream test subscribes either before the first notification or after the turn ends, which takes the ENDED branch.
- Failure: under that mutant, a subscriber that attaches while a turn runs silently skips every kept event, with no GAP and no warning. This is the "subscription read late" case that D-37 says the fixed start keeps honest. No test would catch the regression.
- Smallest fix: add one test that emits three events, then calls `stream_codex_turn`, ends the turn and drains. Assert that it yields those three events with sequences 1 to 3, then ENDED. A second case with the event limit patched to 2 should assert that it starts at sequence 2.
- Spec IDs: INV-22, D-37, AC-14.

R-E6 [Major] [error handling] vidbyte/tools/builtins/codex/thread_actions.py:103-117 — `StartCodexSideChatTool` always fails in a scope whose `spawn_defaults` set `name`, `tools` or `thread.personality`
- Evidence:
  - `_side_chat_defaults` narrows the sandbox and approvals but keeps every field of the START_CODEX_SIDE_CHAT refusal row (`vidbyte/lib/constants/codex_host.py:207-216`), which the method then refuses.
  - The resume tool clears its own row (`skill_functions.py:320-329`) and the continue tool clears its own (`threads.py:204-216`).
  - Probe on a real host, where the plan tool with the same `name` default succeeds:
    - `start_codex_side_chat` with a `name` default printed `error: configuration.invalid_argument: start_codex_side_chat does not use the CodexSpawnRequest field name; leave it at its default ...`.
    - The same tool with a `thread.personality` default failed the same way.
  - The only tool test uses `_writable_defaults`, which sets none of these fields (`test_codex_host_feature_tools.py:68-84`).
- Failure: a scope that gives spawned threads Vidbyte tools, a name or a personality can never start a side chat through the tool. The error tells the model to change a field it cannot reach. INV-43 says the tool "builds its request from `spawn_defaults` and only narrows it", and clearing a refused field is a narrowing.
- Smallest fix: in `_side_chat_defaults`, reset every path in `CODEX_HOST_REJECTED_FIELDS[START_CODEX_SIDE_CHAT]` to a fresh request's value, as `_resume_defaults` does. Add `name`, `tools` and a personality to the tool test's defaults.
- Spec IDs: INV-43, INV-27, §9.2 row 34, AC-36, INV-44.

## VERIFIED CLAIMS

1. **The reviewed HEAD contains slice 2 unchanged.** HEAD is `18cd32594ef60f30e3870cdd690ff07f992b20e9`, which is 8ea8734f plus a change to `pipeline.md` only. `git status --porcelain` shows only another reviewer's untracked report, and `__pycache__/` is gitignored (`.gitignore:1`), with files that predate this review.
2. **The slice-2 behaviour suite passes under `V`.** The 12 behaviour and tool modules give `225 passed in 12.63s`. The 11 slice-2 modules run earlier gave `203 passed in 16.58s`.
3. **Mutation results.** I ran 33 single-point mutants in memory (`inspect.getsource`, then a string replace, `compile` and `setattr`; no worktree file was edited) against those 12 modules.
   - 29 were killed.
   - S3b, S3c and S7 survived (R-E4 and R-E5).
   - K1 also survived: it removes `--` from the git argv. It is equivalent under current validation, because `GitWorktreeSpec` requires absolute paths and refs that match `GIT_REF_PATTERN`, which cannot start with "-" (`vidbyte/lib/dataclasses/process.py:115-121`). The `--` is defence in depth, so this is not filed.
4. **R-E1 is real.** The probe output is quoted in R-E1. No `except` surrounds lines 162-166.
5. **R-E2 is real.** The goal stays active at Codex, `turn-2` is in progress, the host tracks nothing, and no cancel, pause or interrupt is sent. The SDK's own rule is at `openai_codex/client.py:643-645`.
6. **R-E3 is real, and the proposed fix is safe.** The behaviour was reproduced. The runtime fix S9 keeps all 225 tests green and gives EC-19's `GAP(4, 1)`.
7. **R-E6 is real.** The side-chat tool is refused with a `name` default and with a `thread.personality` default, while `run_codex_plan` succeeds with the same `name` default.
8. **No R-11 regression.** There is no shield in `turn_starts.py`, `connection.start` or `stream_methods.py`. `wait_codex_turns` uses `asyncio.wait` (`stream_methods.py:69`), and the record refuses empty or duplicate handles (`codex_host_inputs.py:473`).
9. **The side-chat tool narrows to `never` on the wire.** `test_codex_host_feature_tools.py:353` asserts it on both requests, and mutants C3 to C5 are each killed by `test_the_side_chat_tool_narrows_the_scope_posture_to_read_only_and_never_asking`.
10. **The worktree runs git safely.** It runs with no shell, through `CliArgv` and `CliRunner`, with the `GIT_NO_PROMPT_ENV` overlay, a 120-second bound and a 65,536-byte output cap (`git_worktree.py:47-58`). Mutant K2 is killed.

## COMMANDS RUN

Where they appear below:
- `V` is `scratchpad/venv-codex163/Scripts/python.exe`.
- `S` is `scratchpad/s4-slice2/engineering`.
- `FILES` is the 12 test modules listed in `$S/files.txt`.

Commands, each with its result or final line:
- `PYTHONPATH=$(pwd) "$V" -m pytest -q -p no:cacheprovider <11 slice-2 modules>` gave `203 passed in 16.58s`.
- `PYTHONPATH=$(pwd) timeout 600 "$V" $S/mutant.py NONE $FILES` gave `225 passed in 12.63s`.
- `for m in <30 ids>; do PYTHONPATH=$(pwd) timeout 300 "$V" $S/mutant.py $m $FILES; done` wrote `$S/results.txt`. Its last line was `P1-turn-settings-targets-handle rc=1 | 1 failed, 114 passed in 11.46s`. The run's survivors were `S3b ... rc=0 | 225 passed`, `S3c ... rc=0 | 225 passed`, `S7 ... rc=0 | 225 passed` and `K1 ... rc=0 | 225 passed`. S8 was not applied because of an indentation typo and was re-run as S8b.
- `for m in S8b S9-FIX L1 L2 W2; do ... mutant.py $m $FILES; done` gave `W2-wait-snapshot-none-for-running rc=1 | 1 failed, 17 passed in 1.53s`. S9, the proposed fix rather than a mutant, gave `rc=0 | 225 passed in 12.25s`.
- `PYTHONPATH=$(pwd) timeout 300 "$V" -m pytest -q -s -p no:cacheprovider --rootdir=$S $S/probe_engineering.py` gave `5 passed in 1.40s`. The PROBE lines are quoted in R-E1, R-E2, R-E3 and R-E6.
- The same oversize probe with mutant S9 applied first gave `1 passed in 0.07s`, with `PROBE (seq,dropped): [(4, 1)]`.
- `git status --porcelain` gave `?? docs/spec/codex-host-first-class/reports/S4-review-conformance.md`.
- `git rev-parse HEAD` gave `18cd32594ef60f30e3870cdd690ff07f992b20e9`.
- `git check-ignore -v tests/features/codex_host/__pycache__/x.pyc` gave `.gitignore:1:__pycache__/`.
- `git diff --name-status a7730107...8ea8734f -- tests/` reported 31 paths: 12 added test modules and 19 modified or support files.
- `grep -rn "HOST_TEXT_LIMIT\|TEXT_LIMIT_CHARS" tests/features/codex_host/*.py` found 3 hits, the constant table plus `test_codex_host_stream_wait.py:348`.
- Read-only `sed`, `grep` and `cat -n` on `turn_stream.py`, `stream_methods.py`, `thread_methods.py`, `turn_starts.py`, `host_core.py`, `goal_methods.py`, `settings_methods.py`, `errors.py`, `connection.py`, `thread_helpers.py`, `git_worktree.py`, `dataclasses/process.py`, `codex_host_inputs.py`, `constants/codex_host.py`, `tools/builtins/codex/{live,thread_actions,skill_functions,threads}.py`, `openai_codex/client.py:572-648`, and spec.md INV-2, INV-20, INV-22, INV-29, INV-31, INV-43, EC-19, EC-37, EC-38, D-37 and D-39.
