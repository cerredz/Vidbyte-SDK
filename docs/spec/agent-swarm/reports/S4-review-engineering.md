LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the mailbox and termination protocol holds on every path I could find. One liveness hole remains: a member run that dies by a CancelledError nobody asked for. Its effect is that the swarm silently waits out the whole time limit. The test pack also cannot fail for three specified behaviours.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- Every check is followed by its state change with no `await` in between. I walked every `await` in the package (`grep -n "await " vidbyte/agents/agent_swarm/*.py`):
  - `post_message` (runtime.py:150-171), `collect_messages` (:176-179), `end_turn` (:189-213), `record_tool_call` (:218-219), `_run_member` (:122-139) and `arun` (:84-107) all await only `flush()` or `wake`. Each of those awaits comes after a synchronous decide-and-record block.
  - After `await wake` (:206), the code re-checks state synchronously (:210) before it drains.
  - Do not move these awaits. Mutants that do so (M1, M1b), and mutants that move the wake into the woken agent (M20, the D-5 design), are killed by the pack.
- Exactly-once and causal order hold:
  - `_drain` (runtime.py:239-241) takes the inbox and records each `MESSAGE_DELIVERED` in one step. A `MESSAGE_SENT` is the queued item itself, so its id is its own sequence.
  - The outbox marks an event delivered before it awaits the callback (events.py:69-71), under `asyncio.Semaphore()`. The default value is 1, and the semaphore is always released by `async with`.
  - The local 3.11.0 stdlib already carries the fixed Semaphore cancel path (`acquire` re-adds `_value` and wakes the next waiter when a woken waiter is cancelled). The gh-90155 deadlock therefore does not apply.
- Failure containment matches spec EC-16 (a)/(b)/(c) and EC-38 when driven for real (probe P4):
  - `end_turn` raising `KeyError` gives `AGENT_FAILED "KeyError: 'boom-end_turn'"`, and the others end QUIET. The same holds for `collect_messages`.
  - A tool raising `KeyboardInterrupt` or `SystemExit` propagates bare from `arun`, and `AgentSwarm._running` is cleared.
  - FAILED is chosen only when `running` is empty (runtime.py:262-264). Mail left in a failed agent's inbox is excluded from MAX_TURNS (:265).
- The S2 event oracle (`assert_event_invariants`) replays the spec's state machine. The pack is not vacuous: all 161 tests fail against `origin/main`'s `vidbyte` (C5). The 33 seeded property runs kill the budget, ordering and routing mutants (M3, M4, M5, M24).

FINDINGS (ranked, most severe first, max 15)

R-E1 [Major] [pre-mortem: liveness / cancellation] vidbyte/agents/agent_swarm/runtime.py:122-139 — a member run that ends in a CancelledError the swarm did not request is silently dropped. The agent stays "working" forever, so the swarm cannot end before `timeout_seconds` (default 3600 s). It then returns TIMEOUT with no `AGENT_FAILED`. This violates INV-16 ("Cancellation ... never swallowed") and EC-38.
  Evidence:
    - `_run_member` catches only `VidbyteSdkError`. A `CancelledError` raised by the developer's `on_event` (inside that member's `flush`) or by a search tool leaves `agent.arun` without passing `_fail` or `_end_check`, so `name` stays in `self._working`.
    - Python 3.11's TaskGroup then ignores the child (`asyncio/taskgroups.py:175-176`, `if task.cancelled(): return`). Nothing aborts and nothing propagates.
    - Probe P1 (a search tool with `error=asyncio.CancelledError()`, `timeout_seconds=3`):
      `elapsed 3.0 AgentSwarmStopReason.TIMEOUT ['1 agent_started builder', '2 agent_started tester', '3 agent_idle tester', '4 swarm_ended '] ()`
      tester was done at t≈0.
    - Probe P2 (async `on_event` that raises `asyncio.CancelledError()` on `tool_called`):
      `elapsed 3.0 AgentSwarmStopReason.TIMEOUT [... '3 tool_called builder', '4 agent_idle tester', '5 swarm_ended '] ()`
  Failure:
    - Trigger: `on_event` awaits a task that some other code cancelled, for example a websocket push task cancelled when the client disconnects. A tool can do the same.
    - Result: one member dies with no event, and the other members finish. arun returns neither a result nor an exception until the time limit. The record then says TIMEOUT, with no `AGENT_FAILED` explaining why builder never ended.
    - EC-38 promises that an uncontained exception propagates from `arun` and cancels the other runs. The reality is a silent one-hour wait.
  Smallest fix:
    - In `_run_member`, add `except asyncio.CancelledError:`. When `asyncio.current_task().cancelling() == 0`, call `self._fail(name, "CancelledError: ...")` and `self._end_check()`. Then always `raise`.
    - The re-raise keeps S019 satisfied, and a real timeout or outer cancel (where `cancelling() > 0`) is unchanged.
    - I verified this on a scratch copy. P1 then ends at once (QUIET, `AGENT_FAILED builder`, tester's reply kept), P2 ends at once (QUIET), and the pack stays 161 passed.
    - Update header item 4 in runtime.py:8 to match.
    - The spec should state whether this case is contained (as above) or must make `arun` raise (EC-38 wording). Either way it must not wait out the limit.
  Spec IDs: INV-16, EC-38, INV-17, G-3, NFR-9

R-E2 [Major] [test quality] tests/features/agent_swarm/ (no test exists; the waiver is at docs/spec/agent-swarm/test-plan.md:91) — the pack cannot fail for three specified behaviours. Three of the 20 mutants survive with `161 passed`.
  Evidence (mutation driver on a scratch copy, full pack per mutant):
    - `M2_failed_inbox_counts_for_max_turns` (runtime.py:265 `for name in running` → `for name in self._inboxes`): 161 passed.
    - `M21_no_history_trim` (member.py:154, the `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(...)` entry removed): 161 passed.
    - `M22_no_result_cap` (member.py:153, the `agent_loop_settings=...ToolSettings(result_max_chars=...)` line removed): 161 passed.
    - The only test touching D-10 compares the constants' values (test_agent_swarm_contract.py:408). No test puts a message into the inbox of an agent that then fails.
    - The wiring works today. Probe P3 (a search tool returning 250,000 chars, six calls) shows each tool message capped at 100,070 chars, and the history stops growing at 3 tool messages, about 300K chars.
  Failure:
    - (a) A regression that counts a failed agent's queued mail would report MAX_TURNS for a swarm that ended quietly after one agent failed with mail waiting (EC-12: "Its queued messages stay undelivered; the others continue"). Wrong stop-reason data, and nothing would catch it.
    - (b) Dropping the trim or the cap (both are D-10 decisions) would only show in production. A long-lived member would exceed its model's context and fail with a provider error.
  Smallest fix (S2-owned tests):
    - (a) A lifecycle test. builder sends to reviewer while reviewer is held mid-tool by `BlockingSearchTool`, then reviewer's next model call raises `provider_error()`. Assert QUIET, one `MESSAGE_SENT` with no `MESSAGE_DELIVERED`, and `assert_event_invariants`.
    - (b) A contract test. A search tool returns more than `AGENT_SWARM_TOOL_RESULT_MAX_CHARS` characters; assert the next `ModelCall` carries a cut result. Enough such calls to exceed `AGENT_SWARM_HISTORY_MAX_TOKENS` must leave the last call's history trimmed (P3 is the template).
  Spec IDs: INV-10, EC-12, D-10, EC-26, A-5, FR-11

R-E3 [Minor] [pre-mortem / test quality] vidbyte/agents/agent_swarm/runtime.py:98-102 and docs/spec/agent-swarm/test-plan.md:89 — the waiver for EC-18 ("needs wall-clock timing, which would be flaky") does not hold. When EC-18 happens, a QUIET result comes back missing the deciding agent's reply.
  Evidence:
    - Probe P5 uses the same `Signal` seam as the EC-23 test. An async `on_event` holds on tester's `AGENT_IDLE`, tester replies after builder is idle, and `timeout_seconds=0.5`:
      `elapsed 0.51 AgentSwarmStopReason.QUIET ['1 agent_started builder', '2 agent_started tester', '3 agent_idle builder', '4 agent_idle tester', '5 swarm_ended '] [('builder', 'Builder done.')]`
      It is deterministic and takes 0.5 s.
    - Mutant `M7_timeout_overrides_decided_reason` (`self._stop_reason = AgentSwarmStopReason.TIMEOUT` unconditionally at :101) survives with `161 passed`.
  Failure:
    - The stop reason is decided QUIET at tester's `end_turn`, and tester's own flush is then cut by the limit. tester's run is cancelled, not "finished normally", so `replies` lacks tester.
    - This contradicts AC-4 / FR-15 ("one reply per agent") and the wording of INV-11, although EC-18 only promises that "the decided reason stands".
    - No test pins EC-18. A regression to "TIMEOUT always wins" would pass.
  Smallest fix:
    - Add the P5 scenario as a test (S2).
    - Have the spec say what `replies` holds under EC-18. The cheapest consistent rule is to document that replies may be partial when the limit cuts the release.
  Spec IDs: EC-18, INV-10, INV-11, FR-15

R-E4 [Minor] [pre-mortem: untrusted model input] vidbyte/lib/dataclasses/agent_swarm.py:143 — `one_line=True` on `TOOL_CALLED.tool_name` is stricter than spec §9.1 ("non-blank name"). A model-supplied unknown tool name containing a newline therefore kills the member instead of becoming a tool error.
  Evidence: probe P6 (scripted `tool_call(<name>, ...)` for builder):
    - `'bash_tool'` gives `QUIET [... '3 tool_called builder', '4 agent_idle builder' ...]`, and builder saw `[tool_error kind=unknown_tool]`.
    - `'functions.bash'` gives the same.
    - `'bash\nrm'` gives `QUIET [... '3 agent_failed builder' ...] ["The agent's run ended before the swarm released it, with stop reason middleware_abort."]`
  Failure:
    - The `ConfigurationError` from `AgentSwarmEvent.__post_init__` is raised inside the fail-closed `after_tool_call` (member.py:81-82). The pipeline aborts the run, the agent leaves the swarm, and its tool call is missing from the record.
    - Every other unknown name is a tool error the agent reads and continues past (EC-16 (b)). Hostile workplace content (T-2) can use this to knock agents out.
  Smallest fix: drop `one_line=True` at :143 (spec §9.1 asks only for non-blank). An alternative is to normalize the name in `record_tool_call`.
  Spec IDs: §9.1, INV-17, EC-16, T-2

R-E5 [Minor] [security / validation] vidbyte/lib/constants/agent_swarm.py:46 (checked at vidbyte/agents/agent_swarm/settings.py:103) — the reserved names omit the loop's own `isDone`. A developer search tool named `isDone` is accepted and then silently replaced, so the agent never holds it.
  Evidence:
    - `vidbyte/tools/_internal.py:53` reads `return tools.add(IsDoneTool(), replace=True)`.
    - Probe P7 (`SearchTool(name="isDone")`) gives:
      `settings accepted; tools offered: ('bash', 'grep', 'read_lines', 'write_text', 'patch_file', 'message', 'isDone')`
      `search tool ran: []`
      The model's `isDone(query=...)` call ended builder's turn.
  Failure: INV-21 and FR-3 promise "plus the developer's search tool when one is given", and EC-33 promises a refusal for a name that collides with a swarm tool. Here the tool vanishes with no refusal, and calling it ends the turn.
  Smallest fix:
    - Refuse `search_tool.name == "isDone"` in `AgentSwarmSettings.__post_init__`. `settings.py` may import `IS_DONE_TOOL_NAME` from `vidbyte.tools._internal`; `lib/constants` may not.
    - Or add the literal to `AGENT_SWARM_RESERVED_TOOL_NAMES`.
  Spec IDs: INV-21, EC-33, FR-3, INV-18

VERIFIED CLAIMS:
- C1 "Any `await` between a check and its change can lose or double a message; there is none." HELD. Every `await` is listed in the first bullet above. M1 (flush + yield between the inbox check and the idle mark) is killed by 6 tests. M1b (flush only, the realistic refactor) is killed by 1 test (`test_a_message_accepted_while_the_recipient_is_going_idle_is_never_lost`).
- C2 "A message is delivered once, never lost, never duplicated; SENT precedes DELIVERED; sequence 1..N; in-order `on_event`." HELD.
  - Read the code: `_drain`, `_KIND_FIELDS`, and the `message_id` checks in `AgentSwarmEvent._check_kind_fields`.
  - Killed mutants: M3 (swapped sender/peer, 41 tests fail), M6 (drain keeps inbox), M24 (newest first), M9 (mark delivered after callback), and removing the semaphore's effect (concurrent-flush test).
- C3 "No lost wake-up or hang once every agent ended its turn." HELD for every swarm-driven race I enumerated:
  - A sends while B is in `end_turn`.
  - A sends and then idles while the last other agent idles.
  - Two agents idle together.
  - A send to a failed agent (refused, :155).
  - A slow or raising `on_event`.
  - isDone versus a plain reply (both reach `end_turn`; `ctx.tool_result` is None on the plain path, which the oracle's replies check confirms).
  - The exception is R-E1: a member that dies by a stray CancelledError never "ends its turn".
- C4 "TIMEOUT: the parked member is cancelled; SWARM_ENDED(TIMEOUT) is last; the result is returned; no `on_event` after SWARM_ENDED." HELD.
  - The parked `await wake` is cancelled through the task's `_fut_waiter`.
  - The TaskGroup waits for every child before :106 records SWARM_ENDED.
  - AC-6 passes in about 0.51 s.
  - Bash on Windows: `BashTool` catches CancelledError, kills Git's launcher, waits at most `BASH_KILL_GRACE_SECONDS = 5.0` and re-raises (bash.py:139-142, 216-219). The overrun is therefore bounded at about 5 s, and the command may outlive the swarm, as documented in the README "Notes for agents".
  - Caveat: the final flush at :107 sits outside the limit, so an `on_event` that never returns on a post-timeout event hangs `arun`. INV-15 and EC-23 choose this, so it is not a finding.
- C5 "Tests would fail without the feature." HELD. Running the branch's pack against `git archive origin/main vidbyte` gives `161 failed`.
- C6 "Semaphore() is a correct mutex." HELD. Its value is 1 by default, it is released by `async with` on every exit, and the 3.11.0 stdlib source printed locally has the fixed cancel path.
- C7 "History trim and the tool-result cap apply to members" (D-10). HELD at runtime (P3), but NOT PINNED by any test (R-E2). `PermissionPolicy.allow_all()` is pinned indirectly: M23 is killed by the AC-1 snippet test.
- C8 "AC-6 wall-clock test" HELD (0.51 s measured). The test bound `elapsed < timeout + 10.0` (test_agent_swarm_lifecycle.py:114) is far looser than NFR-9's "< 1 s overrun". It is not flaky, but a 5-second-late timer would pass.
- C9 "No key reaches events or AGENT_FAILED text" (A-9, INV-23). HELD for SDK errors.
  - `api_keys` is `repr=False`.
  - `AGENT_FAILED` text is `type(cause).__name__: str(cause)`.
  - Gemini sends the key in a header through google.genai, so it does not appear in URLs.
  - Note: OpenAI's own 401 body carries a provider-masked key fragment (`sk-proj-***...abcd`), which would pass through `_failure_text` verbatim. That is provider-side masking, outside this PR.
- C10 "Path traversal past the workplace." No shorter path than §10 T-1:
  - `read_lines`/`write_text` use `FileSystemToolConfig.resolved_root()` (`resolve()`).
  - `patch_file` uses `resolve()` + `relative_to` (patch.py:98-100).
  - `grep` refuses an escaping `subdir` (code_search/base.py:53).
  - bash is unconfined by design.
- C11 "Unbounded events and inboxes" are accepted (Q-3, Q-8). No invariant breaks because of them. Nothing is persisted, so the "data and scale" sub-lens has no query, index or migration surface.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` (worktree) → `161 passed in 3.47s`; `Python 3.11.0`
- `git diff --stat origin/main...c0b167d3` → `56 files changed, 7653 insertions(+), 8 deletions(-)`; `git diff --stat c0b167d3 HEAD` → only `docs/spec/agent-swarm/pipeline.md`
- `python -c "...inspect.getsource(asyncio.locks.Semaphore)..."` → fixed `acquire`/`_wake_up_next` (`if not fut.cancelled(): self._value += 1; self._wake_up_next()`)
- Scratch copy (`tar` of `vidbyte`, `contracts`, `tests/features/agent_swarm`): `PYTHONPATH=<copy> python -m pytest tests/features/agent_swarm -q` → `161 passed in 3.30s`
- `git archive origin/main vidbyte pyproject.toml contracts` + branch tests → `161 failed in 3.48s`
- Mutation driver (`mutate.py`, one textual mutant at a time on the copy, restored after each):
  - M1 `6 failed`
  - M1b `1 failed`
  - M2 `161 passed` (survived)
  - M3 `41 failed`
  - M4 `3 failed`
  - M5 `1 failed` (property seed 26 only)
  - M6 `1 failed`
  - M7 `161 passed` (survived)
  - M9 `1 failed`
  - M10 `1 failed`
  - M11 `1 failed`
  - M12 `1 failed`
  - M17 `1 failed`
  - M20 `1 failed`
  - M21 `161 passed` (survived)
  - M22 `161 passed` (survived)
  - M23 `1 failed`
  - M24 `1 failed`
  - M25 `1 failed`
  - M26 `1 failed` (static no-sleep check only; benign mutant)
- Probes, all with `PYTHONPATH=$(pwd)` and the pack's own fixtures, models offline. To reproduce, rebuild each from `ScriptedSwarm` and `build_swarm` in `agent_swarm_fixtures.py`:
  - P1: builder `[tool_call("web_search",{"query":"q"}), reply("never")]`, tester `[reply("Tester done.")]`, `search_tool=SearchTool(error=asyncio.CancelledError())`, `timeout_seconds=3` → `elapsed 3.0 TIMEOUT`, no `agent_failed`
  - P2: same, but `on_event` async raising `asyncio.CancelledError()` on `tool_called` and builder `[tool_call("read_lines",{"path":"x.txt"}), reply(...)]` → `elapsed 3.0 TIMEOUT`
  - P1/P2 with the R-E1 fix on the copy → `elapsed 0.0 QUIET ... '3 agent_failed builder'` / `elapsed 0.01 QUIET`; pack `161 passed`
  - P3: a search tool returning `"x"*250_000`, 6 calls → per-call `max tool len: 100070`; history stops at 3 tool messages (`300939` chars)
  - P4: `patch.object(AgentSwarmRuntime, "end_turn"|"collect_messages", raising KeyError for builder)` → `QUIET ["KeyError: 'boom-end_turn'"] ['tester']` / `["KeyError: 'boom-collect_messages'"]`; a search tool raising `KeyboardInterrupt()`/`SystemExit(3)` → `raised KeyboardInterrupt running flag: False` / `raised SystemExit running flag: False`
  - P5: async `EventLog` hook holding on tester's `agent_idle`, builder `[reply("Builder done.")]`, tester `[after(builder_idle, reply("Tester done."))]`, `timeout_seconds=0.5` → `elapsed 0.51 QUIET ... [('builder', 'Builder done.')]`
  - P6: builder `tool_call(name, {"command": "ls"})` for `bash_tool`, `bash\nrm`, `   ` and `functions.bash` → only `bash\nrm` gives `agent_failed ... middleware_abort`. The blank name fails with `ValueError: ToolCall.tool_name cannot be empty` in the shared loop; that is pre-existing and not swarm-specific.
  - P7: `search_tool=SearchTool(name="isDone")` → settings accepted, tools offered end with a single `isDone`, `search tool ran: []`
