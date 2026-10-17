LENS: conformance
VERDICT: SOUND — Every S4 fix under review holds on the real code path at `87df4fc9` with no Blocker or Major, leaving only two Minor text gaps (R-16 spec sentences around EC-39 and INV-11, R-17 three doc sentences the fixes left behind) that change no behavior.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- The R-3 branch is correct as written (`vidbyte/agents/agent_swarm/runtime.py:129-144`). Do not move or add an `await` in it.
  - It runs no `await` between the catch and `_fail`/`_end_check`.
  - Nothing on the unwind path suspends either. The loop's `except BaseException` blocks (`vidbyte/agents/runtime.py:430`, `:822`, `:1039`, `:1262`, `:1349`) only end spans and re-raise. `BaseAgent`'s branch (`vidbyte/agents/base.py:982-986`) calls the synchronous `_close_failed_reply`. `MiddlewarePipeline` catches only `Exception` (`vidbyte/middleware/pipeline.py:144`).
  - Every cancel the swarm asks for arrives with `cancelling() == 1`, so it records nothing. This held on three paths: the time limit, the caller cancelling `arun`, and a sibling's uncontained exception (TaskGroup `_abort`).
  - A `CancelledError` from `on_event` never enters `event_error_types` (`events.py:79-84` catches `Exception` only).
- R-11 restarts the clock only after the run-once guard (`runtime.py:74-79`). A refused second `arun`, whether concurrent or later, leaves the first run's event record untouched.
- R-13's folded validation refuses exactly what the helper version refused. A differential run over 8,987 generated `AgentSwarmEvent` inputs found differences only where R-8 meant them: `one_line` was dropped from `TOOL_CALLED.tool_name`.
- The change stays inside its boundaries:
  - 24 added and 13 modified product files, the r4 §8.4 budget, and every modified file is a §12.3 row;
  - `lint/baseline.json` is unchanged, there are no suppressions and no `asyncio.sleep`;
  - the test changes since `c0b167d3` are S2 additions only, and the only removed lines are module docstring lines that S2 rewrote;
  - the contract file is current, and `python lint/run.py` prints `SDK-LINT: PASS` with 0 REGRESSED.

FINDINGS (ranked, most severe first, max 15)

R-16 (R-C1) [Minor] [conformance: spec text] `docs/spec/agent-swarm/spec.md:185` (INV-11), `:280` (EC-39); code at `vidbyte/agents/agent_swarm/runtime.py:140` — spec r4 does not describe three outcomes that the R-3 branch reaches and the S2 tests pin
  Evidence:
  - (a) **A released agent's reply is dropped, and INV-11 r4 does not allow it.** INV-11 says that on QUIET "every idle agent is released: its run finishes normally and returns its last turn's reply". Its r4 exception names only EC-18, the time limit. INV-17 r4 says a cancel "arriving after the stop reason is decided is re-raised without AGENT_FAILED". So in that case the released agent's run raises and its reply is lost. `probe_rr.py cancel_after_decision` (on_event raises `CancelledError` on tester's AGENT_IDLE after tester's own end check decided QUIET) printed:
    `cancel_after_decision: quiet ['1 agent_started builder', '2 agent_started tester', '3 agent_idle builder', '4 agent_idle tester', '5 swarm_ended  [quiet]'] replies: [('builder', 'Builder done.')]`
    The test that pins this case, `test_agent_swarm_lifecycle.py:434`, asserts only a subset of replies, citing "INV-11 r4" (`:459`, `:461`). `test-plan.md:86` does the same. INV-11 r4 does not cover this trigger.
  - (b) **EC-39 leaves out MAX_TURNS.** EC-39 says the swarm then ends "QUIET, or FAILED when every agent has failed" and its User-sees column says "stop reason QUIET or FAILED". INV-10, which the code follows correctly, gives MAX_TURNS when an idle agent still holds mail the spent budget cannot wake it for. `probe_rr.py stray_cancel_with_budget_spent` (`max_turns=2`, builder messages idle tester, then builder's search tool raises `CancelledError`) printed:
    `budget-spent stray cancel: 0.02 max_turns [... '4 message_sent builder', '5 tool_called builder', '6 agent_failed builder (CancelledError: the run was cancelled, but not by the swarm)', '7 swarm_ended  [max_turns]']`
  - (c) **"Failed, not woken" holds only for a callback that raises at once.** EC-39 says that in the idle variant "the agent is failed, not woken: the peer's message is refused as a stopped recipient and no AGENT_WOKE is recorded". That holds only when `on_event` raises before it awaits anything. With an async callback that yields first, the peer's send wakes the agent, and only then does the agent fail. `probe_idle_async.py` printed this in 3 of 3 runs:
    `idle-async: 0.01 quiet [... '3 agent_idle tester', '4 message_sent builder', '5 agent_woke tester', '6 agent_failed tester', '7 tool_called builder', '8 agent_idle builder', '9 swarm_ended '] ... stray tasks: 0`
    The code is sound here: no hang, INV-10 holds, INV-14 holds, and the message is left with a failed agent. Only the spec sentence is too broad.
  Failure: In each case, the spec text plus a developer `on_event` (or tool) that raises `CancelledError` lead a reader to expect one outcome, and the swarm returns another. In (a) the reader expects every released agent's reply and finds one missing. In (b) the reader expects QUIET or FAILED and gets MAX_TURNS. In (c) the reader expects no AGENT_WOKE and finds one. No outcome is wrong under INV-10, INV-14, INV-16 and INV-17. The weighted word "every" in INV-11 cannot hold here, because INV-17 r4 requires the re-raise. This is the same class and remedy as R-14, which S4 rated Minor.
  Smallest fix: Edit the spec text only.
  - (a) Extend INV-11's r4 exception, and the EC-39 row, to say that a `CancelledError` the swarm did not request, arriving after the end was decided, also cuts that agent's run, so it may be missing from `replies`. Its last text survives in its AGENT_IDLE.
  - (b) EC-39: "by INV-10's rule (QUIET, MAX_TURNS or FAILED), never TIMEOUT".
  - (c) EC-39 idle variant: "when the callback raises before it awaits; an async callback that awaits first may let a peer's message wake the agent, which then fails with that message undelivered".
  No code or test change.
  Spec IDs: INV-11, INV-17, EC-39 (INV-10 and INV-14 hold)

R-17 (R-C2) [Minor] [conformance: docs vs fixed behavior] `vidbyte/agents/agent_swarm/swarm.py:38`; `vidbyte/agents/agent_swarm/README.md:58`; `vidbyte/agents/agent_swarm/events.py:9` — three sentences still describe the behavior from before the R-6, R-2 and R-11 fixes
  Evidence:
  - (1) **R-6's claim survives in the public docstring.** `swarm.py:38`, the docstring of `AgentSwarm.arun`, says: `"""Run the swarm on the goal until no agent has work left, the turn budget is spent, every agent failed, or the time limit is reached."""` That is the false claim R-6 removed from the four docs it listed: a spent budget does not end the swarm (INV-9, EC-9). The R-6 rewrite of the package README says so itself: "A spent turn budget does not end it by itself". This docstring is what `help(AgentSwarm.arun)` shows a developer.
  - (2) **The README limits table misses R-2.** `README.md:58` says `` | `search_tool` | `None` | one extra tool every agent holds; may not take a swarm tool's name | ``. After R-2, the name `isDone` is refused too. `probe_verify.py p3` printed `ConfigurationError: ... got 'isDone'. Reserved: bash, grep, read_lines, write_text, patch_file, message, isDone.` The `settings.py` header asks for "one row in the package README's limits table" per setting rule, and its own comment says "neither a swarm tool's name nor the loop's own isDone".
  - (3) **The events header contradicts the runtime.** `events.py:9` says the record is built "when the run starts, never when the runtime itself is built". But `runtime.py:53` still builds an `AgentSwarmEvents` in `__init__`, and the R-11 fix replaces it at `runtime.py:79`.
  Failure: A developer reading the `arun` docstring believes the swarm stops when the budget runs out. One reading the limits table may name a search tool `isDone`, then hit a `ConfigurationError` the table never mentions. A maintainer reading `events.py` may search for a constructor call that does not exist. No behavior changes.
  Smallest fix:
  - (1) `swarm.py:38`: "...until no agent is working, or the time limit is reached."
  - (2) `README.md:58`: "may not take a swarm tool's name or `isDone`".
  - (3) Either delete the placeholder at `runtime.py:53` (it is only read after `arun` sets it), or reword `events.py:9` to "the record that arun builds when the run starts; the one built with the runtime is replaced".
  Spec IDs: INV-9, EC-9, EC-33, §9.3 (`search_tool` row), D-16

VERIFIED CLAIMS:
- **Scope (re-review round 1 of 2).** Reviewed `git diff c0b167d3..87df4fc9` without the main merge `dc4710f9`, which touches no swarm file (`git diff dc4710f9^1 dc4710f9 --stat` over the swarm paths is empty), and checked the full branch diff `origin/main...87df4fc9` against spec r4. The worktree HEAD `4aa94cf1` adds only `docs/spec/agent-swarm/pipeline.md`; `git diff --quiet 87df4fc9 -- vidbyte tests` printed `vidbyte+tests match 87df4fc9`. Every probe ran read-only against the worktree; the one mutant ran on a scratch `git archive` copy.
- **R-1: held.** `grep -rn -i "read a file again\|what is left\|keep working\|stands on its own\|what you need\|what you did\|name the files" vidbyte/prompts/prompts/agent_swarm/` exited 1. The descriptions have 5 sentences (tool), 4 (`to`) and 4 (`text`). The `system_prompt` keeps `{name}`, `{agents}`, "agent swarm", "folder", "message" and "isDone". The rewritten text matches how the inbox is rendered (`inbox_message.md:1` is `From {sender}:`).
- **R-2: held.** `probe_verify.py p3` raised `ConfigurationError: AgentSwarmSettings.search_tool must not take a swarm tool's name; got 'isDone'. Reserved: bash, grep, read_lines, write_text, patch_file, message, isDone.`. `with_internal_agent_tools` adds only `isDone` (`vidbyte/tools/_internal.py:51-53`), so no other internal name can be shadowed.
- **R-3 and R-9: held.**
  - P1 printed `elapsed 0.01 QUIET ... '3 agent_failed builder (CancelledError: the run was cancelled, but not by the swarm)'` with replies `[('tester', 'Tester done.')]`.
  - P2 printed `0.02 QUIET`.
  - The idle variant printed `0.02 quiet ... '3 agent_idle tester', '4 agent_failed tester'` with no `agent_woke`.
  - Requested cancels record nothing:
    - the caller's cancel: `caller_cancel events: ['1 agent_started builder', '2 agent_started tester', '3 agent_idle tester'] stop_reason: None failed: set()`;
    - an EC-38 sibling: `ec38: arun raised ExceptionGroup ['RuntimeError']` / `ec38 events: ['1 agent_started builder', '2 agent_started tester'] failed: set()`;
    - the time limit inside a blocking tool, 5 of 5 runs: `time_limit_in_tool: 0.5 timeout [... '4 swarm_ended  [timeout]'] replies: ()`.
  - `event_error_types` stays `()` (`error_types_on_cancel`).
  - INV-15 still holds under EC-39: `probe_delivery.py` printed `idle quiet delivered [1..7] recorded [1..7] exactly once in order: True error_types: ()` and the same for `working` with events 1..6.
  - The R-9 header sentence ("only a member that failed before the limit has one, and replies is empty") matches `runtime.py:101-105`.
- **The 87df4fc9 test kills S5-M2.** On a scratch copy, dropping `and self._stop_reason is None` turned the baseline `1 failed, 170 passed` into `2 failed, 169 passed`. The baseline failure is the contract-path test, because the copy has no `contracts/`. The extra failure is `test_an_unrequested_cancel_after_the_end_was_decided_does_not_fail_the_released_agent`, with `'5 agent_failed tester'` in the assertion diff.
- **R-4: held.** The script printed `same class True module vidbyte.middleware.builtins.agent_swarm_turn fail_closed True`, `on builtins False`, and `in member __all__ True`. `git diff --name-status 845a4d9b 87df4fc9` (excluding docs and tests) gave `24 A` and `13 M`, all of them §12.3 rows. The class body moved unchanged (diff hunk). The middleware layer imports `AgentSwarmRuntime` only under `TYPE_CHECKING`.
- **R-6: partly held.** The four listed sentences are fixed. One more instance of the same claim remains (R-17 (1)).
- **R-7: held.** The comment lines are 68, 70, 57, 69 and 27 columns wide (`awk length`).
- **R-8: held.** `test_a_tool_name_holding_a_newline_is_a_tool_error_not_a_failure` passes, and the differential run accepts `'bash\nrm'`.
- **R-10: held.** `measure_tokens.py` printed `swarm prompt ... tokens 326`, `loop prompt ... 115`, `tool schemas ... 748`, `fixed total tokens 1189 with history 91189`. That matches the header's 330, 750, 115, 1,190, 91,190 and 36,800.
- **R-11: held.** `probe_verify.py p4` printed `P4 first event elapsed_ms: 16`, down from 406.
  - A concurrent second `arun` on the same runtime printed `second arun refused: {'field': 'arun'}`, `events object unchanged by refused call: True`, then `first run: quiet ... seq ok: True`.
  - A third call printed `third arun after finish refused`.
- **R-13: held.** The R-13 differential printed `cases 8987, identical outcome 8849, different 138`. All 138 are `TOOL_CALLED` `tool_name` cases. 124 (`None` 96, `''` 14, `'  '` 14) are refused on the same field and differ only in wording (the old `one_line` text, "must be one line of non-empty text"). The other 14 are `'bash\nrm'`: 2 now pass (`('ok',)`), and 12 now fail on `AgentSwarmEvent.tool_status` instead, as R-8 intends.
- **AC-1: held.** The §4 snippet, taken verbatim from `spec.md` and run with scripted models, printed 11 event lines, then `quiet`, `True`, `swarm_ended`, `builder Wrote c2f.py.`, `tester Tests pass.`.
- **§14 Never items: held.** The baseline diff has 0 lines. No `noqa`, `type: ignore`, `pragma` or `nosemgrep` was added. `asyncio.sleep` appears 0 times in the swarm package. The test-tree changes since `c0b167d3` are S2 additions plus rewritten module docstrings.
- **Not a finding (out of lens, pre-existing CPython 3.11.0 behavior).** After an EC-38 `ExceptionGroup`, the calling task keeps `cancelling() == 1`: Python 3.11.0's `TaskGroup.__aexit__` does not uncancel the parent when a child errors after the body ended. A later swarm run in that same task therefore raises `CancelledError` at its time limit instead of returning TIMEOUT (`ec38_runtime_bug time_limit_in_tool` ended in `asyncio.exceptions.CancelledError`; every other preceding probe left TIMEOUT intact). The swarm did not cause this and R-3 does not touch it.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` (x6) → `171 passed in 5.55s`–`6.31s` every time
- `PYTHONPATH=$(pwd) python lint/run.py` → `S063 IMPROVED 4 -> 3 ...` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`, exit 0, 0 REGRESSED
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 698f913b... (vidbyte-sdk 0.3.0, 649 exports).`
- `PYTHONPATH=$(pwd) python <scratchpad>/s4-probes/probe_verify.py p1|p2|p3|p4`, `probe_idle_cancel.py` → the outputs quoted above
- `PYTHONPATH=$(pwd) python <scratchpad>/s5-rereview/probe_rr.py caller_cancel ec38_runtime_bug error_types_on_cancel concurrent_second_arun_on_runtime stray_cancel_with_budget_spent time_limit_in_tool cancel_after_decision` (each also run alone or after one other probe) → the outputs quoted above
- `PYTHONPATH=$(pwd) python <scratchpad>/s5-rereview/probe_idle_async.py` (x3), `probe_delivery.py idle|working`, `run_section4.py docs/spec/agent-swarm/spec.md`, `diff_records.py old_records_c0b167d3.py` → the outputs quoted above
- `PYTHONPATH=$(pwd) python <scratchpad>/s5/probes/measure_tokens.py` → `fixed total tokens 1189 with history 91189`
- `git archive 87df4fc9 vidbyte tests/__init__.py tests/features/agent_swarm tests/features/infinite_memory_agent pyproject.toml | tar -x -C <scratchpad>/s5-rereview/mutcopy`, then the S5-M2 edit and the pack → `2 failed, 169 passed` (baseline on the copy `1 failed, 170 passed`, the contract-path test)
- `git diff --name-status 845a4d9b 87df4fc9 -- . ':(exclude)docs' ':(exclude)tests'` → `24 A`, `13 M`; `git diff origin/main...87df4fc9 -- lint/baseline.json | wc -l` → `0`; `git diff dc4710f9^1 dc4710f9 --stat -- <swarm paths>` → empty

`<scratchpad>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad`
