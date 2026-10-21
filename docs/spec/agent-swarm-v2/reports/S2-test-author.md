# S2 test author: AgentSwarm v2

Spec: `docs/spec/agent-swarm-v2/spec.md` r3 · Branch `feat/agent-swarm` · Base `06861b41` · Commits `42d28420` (tests + test plan), `b24e4959` (spec §6.2 Proof column) · Framework pytest 8.3.5 + pytest-asyncio 1.3.0.

## What this stage produced

- `tests/features/agent_swarm/FEATURE.md`: rewritten for v2 (contract, 24 event kinds, invariants, failure modes with their tests, test-suite map).
- `tests/features/agent_swarm/agent_swarm_fixtures.py`: extended. Members have the three v2 fields only; all 24 kinds and their `_KIND_FIELDS`; new steps (`compact`, `search`, `calls`, `observe`); `ScriptedSwarm` stamps each response with the member's own provider so Anthropic usage is parsed by Anthropic's parser; `usage={}` scripts a response with no usage block; `FakeTavily` (record, block, or raise at `TavilyClient.search`); `RetryModelErrorOnce` + `install_model_retry`; the `_Replay` oracle in `assert_event_invariants` now replays every v2 kind (see test-plan "Oracle").
- New modules: `test_agent_swarm_settings.py` (11 cases), `test_agent_swarm_stop.py` (8), `test_agent_swarm_observer.py` (7), `test_agent_swarm_compaction.py` (12). Each is under 400 lines after its header (190, 269, 199, 294) and contains no `sleep`.
- Rewritten in place: acceptance, contract, lifecycle, messaging, property, workplace.
- Pack total: 268 collected cases (r5: 171). Nothing deleted, skipped, or loosened.
- `docs/spec/agent-swarm-v2/test-plan.md`: coverage map (every AC, the EC rows, and the INV groups), the tests deliberately not written, the red run, and nine implementer notes.
- Spec §6.2: only the **Proof** cells of AC-1..AC-25 filled (25 lines changed, nothing else in the spec).

## Assertions the spec reverses (rewritten, with the spec ID that reverses them)

| r5 assertion | v2 assertion | Spec ID |
|---|---|---|
| messaging: a message to itself is refused (`to-itself` refusal row) | accepted, `message_sent` agent = peer, delivered at the next tool iteration (`test_a_message_to_oneself_is_accepted_and_delivered_at_the_next_tool_iteration`; EC-3 test added) | AC-3, EC-2, D-4, INV-6 |
| messaging: refusals leave no event | each refusal records one `message_refused` (peer = name as text, text = the leaf); new rows `to-a-number`, `to-null`, `text-not-a-string`; the unknown-recipient leaf names every member (`agents`) | AC-4, EC-1, INV-5, INV-11 |
| lifecycle / property: a send to a failed agent is refused | a success with `message_stopped_recipient`, recorded `message_sent` then `message_undelivered` | AC-5, INV-6 |
| lifecycle: a turn-middleware recording bug gives `agent_failed` (`..._fails_only_that_agent_...`) | `agent_exited` with text `middleware_abort` (renamed `..._exits_only_that_agent_...`) | AC-24, INV-14 |
| lifecycle: a spent budget ends MAX_TURNS with nothing else recorded | `wake_refused` at the send and one `message_undelivered` at the stop | AC-6, EC-5, INV-9, INV-10, INV-12 |
| lifecycle: mail left for a failed agent only "does not turn QUIET into MAX_TURNS" | that mail is `message_undelivered` right after `agent_failed` (renamed `..._is_marked_undelivered_with_its_failure`) | INV-14, INV-7 |
| lifecycle: timeout, slow-callback, decided-end, every-agent-failing exact event lists (5 events for a failing pair) | v2 lists: `workplace_prepared`, `agent_created` ×N, `agent_started` ×N, `model_called`, `swarm_stopping`, `agent_cancelled` with `agent_state`, terminal per agent (11 events for a failing pair) | INV-12, INV-14, INV-17, INV-22, INV-28, EC-14 |
| lifecycle: the first event is `agent_started` | the first event is `workplace_prepared` | INV-28 |
| lifecycle: `..._does_not_fail_the_released_agent` presumed the agent released | asserts exactly one terminal event per agent (renamed `..._does_not_fail_the_agent`) | INV-14 |
| lifecycle / workplace / messaging: `AgentSwarmRuntime(settings, root)` | `AgentSwarmRuntime(settings, root, workplace_created=False)` | §8.5, §9.2 |
| workplace: `prepare()` returns the folder `Path` | returns `True` when it created the folder, then `False` | §8.5, §9.2 |
| every module: `max_turns=500` literal in oracle calls | `swarm.settings.max_turns` / `AGENT_SWARM_DEFAULT_MAX_TURNS` (default is now 100,000) | §9.3 |
| lifecycle: tool exception and stray-cancel tests used the developer `search_tool` | the Tavily web-search tool through `FakeTavily(error=...)` | D-3, D-17, D-18 |
| acceptance: the §4 snippet prints `quiet`, `True`, `swarm_ended`, one line per reply | prints the event lines, then `quiet <events> <replies>`, and every member's first system string is the shared template | AC-1, §4, INV-1 |
| acceptance: a no-message run has 5 events | 13 events: prepared, created ×2, started ×2, then per agent model_called, idle, released, plus stopping and ended | INV-12, INV-14, INV-17, INV-22, INV-28 |
| contract: 10 prompt leaves; descriptions of 4–5 sentences; a `system_prompt` leaf with "agent swarm"/"isDone" | 23 leaves of §12.3; `system_*` ≥ 6 sentences; tool and parameter descriptions 6–8; thoroughness has eight headings | AC-22, INV-2, FR-3, D-2 |
| contract: `to` enum = the other agents | no `enum`; the description names every member | INV-11, FR-5 |
| contract: own prompt + swarm prompt + loop prompt per member | one shared sectioned template + loop prompt for every member | INV-1, FR-1, D-2 |
| contract: refusal rows `blank-system-prompt`, 101 agents, timeout over one week, three `search_tool` rows; the `isDone`-named search tool test | 501 agents, timeout over thirty days, `max_tokens` rows, web-search rows; the field and `AGENT_SWARM_RESERVED_TOOL_NAMES` are gone (`test_the_search_tool_setting_and_the_reserved_names_are_gone`); members have no prompt (`test_a_member_has_no_prompt_of_its_own`) | AC-19, AC-20, AC-21, D-17, D-18, FR-1 |
| contract: defaults 500 turns / 3,600 s, `MAX_AGENTS` 100, `MAX_TIMEOUT` 604,800 | 100,000 turns, 10,000,000,000 tokens, 86,400 s; `MAX_AGENTS` 500; `MAX_TIMEOUT` 2,592,000; trigger 72,000 / target 27,000 | §9.3, AC-20 |
| contract: hidden repr fields `{"api_keys"}` | `{"api_keys", "web_search_api_key"}` | §10, D-18 |
| contract: a valid result is 5 events without `swarm_stopping` | one `swarm_stopping` with the result's reason before the last `swarm_ended` | INV-16 |
| contract: seven package modules incl. `settings.py` | `settings.py` deleted, `compaction.py` added; the observer module is in the sleep-free set | §8.4, §12.2, INV-37 |
| contract: EC-26 truncation read through the developer search tool | read through `read_lines` | INV-25, INV-36, D-17 |

## Tests deliberately not written

EC-13 (no `tool_loop_limit`/`max_iterations` stop reachable offline; §13), EC-26 (impossible by construction), EC-27 (engine-owned rounding, covered by `tests/test_context_compaction_middleware.py`), EC-29 and EC-30 (load, not behavior), EC-31 run side (only the setting is testable). Reasons and the covering tests are in the test plan.

## Seams (all from spec §13; nothing else is mocked)

`BaseAgent._runner_for_model` (ScriptedSwarm, the loop and the compaction side call), `TavilyClient.search` (FakeTavily), `BaseAgent._runtime_middleware` (one appended retry middleware, AC-10), `AgentSwarmRuntime.record_tool_call` (AC-24 fault), `vidbyte.tools.builtins.bash.BASH_TIMEOUT_SECONDS` / `BASH_MAX_OUTPUT_BYTES` (AC-14). Keys in tests are fakes (`sk-proj-...`, `sk-ant-...`, `tvly-...`); no test reads the environment or the network.

## Defects found and fixed in my own tests during this stage

1. Ten imports took `AgentSwarmAgentState`, `AgentSwarmFolderState`, `AgentSwarmCompactionTrigger` from root `vidbyte`; §9.2 and §12.3 row 2 export them from `vidbyte.lib.enums` only. They would have stayed red after a correct implementation. Moved to `vidbyte.lib.enums`.
2. `usage={}` was swallowed by `usage or DEFAULT_USAGE` in the step builders, so EC-8 would have scripted usage after all. Fixed to `DEFAULT_USAGE if usage is None else usage`.
3. EC-12 was unbound: added the kept-reply assertion (`metadata["stop_reason"] == "middleware_abort"` for builder and reviewer) to the AC-9 test.
4. EC-17 was unbound: the zero-exit bash command now writes `fine.txt`, and the test asserts the file exists while no `file_changed` is recorded.
5. Two r5 import blocks (lifecycle, messaging) were unsorted (`observe`/`of_kind`); fixed with `ruff --isolated --select I001`.

## Commands and their final lines

Red run (expected red; this is the stage's required failing state):

```
$ PYTHONPATH="C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-agent-swarm-v2" python -m pytest tests/features/agent_swarm -q -p no:cacheprovider
FAILED tests/features/agent_swarm/test_agent_swarm_workplace.py::test_a_blank_or_non_text_goal_is_refused_before_any_side_effect[none-AgentSwarmRuntime]
FAILED tests/features/agent_swarm/test_agent_swarm_workplace.py::test_a_blank_or_non_text_goal_is_refused_before_any_side_effect[a-number-AgentSwarm]
FAILED tests/features/agent_swarm/test_agent_swarm_workplace.py::test_a_blank_or_non_text_goal_is_refused_before_any_side_effect[a-number-AgentSwarmRuntime]
265 failed, 3 passed in 9.66s
```

Cause of each failure, from a `--junitxml` copy of the same run (sums to 265): 165 `AgentSwarmMember` still requires `system_prompt`; 69 v2 enums missing from `vidbyte.lib.enums`; 13 `swarm_stopping` not a valid kind; 5 `AgentSwarmWebSearch` not in `vidbyte`; 4 `AGENT_SWARM_COMPACTION_TRIGGER_TOKENS` missing; 9 single causes (missing leaves, settings not in lib, contract set mismatches). The 3 passing cases are r5 behavior the spec keeps (runtime-type refusal outside a swarm; two outbox tests).

Diagnostic probe (temporary uncommitted `tests/features/agent_swarm/conftest.py` giving `member()` a `system_prompt`, deleted at once; `ls conftest.py` now reports "No such file or directory"):

```
FAILED tests/features/agent_swarm/test_agent_swarm_workplace.py::test_a_blank_or_non_text_goal_is_refused_before_any_side_effect[a-number-AgentSwarmRuntime]
253 failed, 15 passed in 24.25s
```

Every probe failure names missing v2 behavior. The only test-side finding was `BaseTool.validate_call` (implementer note 1).

Collection:

```
$ PYTHONPATH=... python -m pytest tests/features/agent_swarm -q --collect-only -p no:cacheprovider
268 tests collected in 0.76s
```

Ruff (the repo has no ruff config and the gate does not run ruff; the ambient user config adds rules the base files also fail, hence `--isolated`):

```
$ ruff check --isolated --select I001,F --line-length 400 --output-format concise tests/features/agent_swarm
tests\features\agent_swarm\test_agent_swarm_contract.py:154:5: I001 [*] Import block is un-sorted or un-formatted
Found 1 error.
[*] 1 fixable with the `--fix` option.

$ ruff check --isolated --select I001,F --line-length 400 --config "lint.isort.known-first-party=['vidbyte']" tests/features/agent_swarm
All checks passed!
```

The one I001 comes only from two modules that do not exist yet (`vidbyte.agents.agent_swarm.compaction`, `vidbyte.middleware.builtins.agent_swarm_observer`), which ruff therefore sorts as third-party; with `vidbyte` marked first-party the pack is clean.

Size and sleep check of the new modules:

```
test_agent_swarm_settings.py 190 lines after header, sleep hits: 0
test_agent_swarm_stop.py 269 lines after header, sleep hits: 0
test_agent_swarm_observer.py 199 lines after header, sleep hits: 0
test_agent_swarm_compaction.py 294 lines after header, sleep hits: 0
```

Full lint, read-only, after commit `42d28420` (not passing; reported for S3):

```
$ python lint/run.py
S020   readme-file-index-parity                    5      1 REGRESSED
...
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: FAIL
```

S020 is the only regressed rule; its four new findings are `tests/features/agent_swarm/README.md:9` missing `test_agent_swarm_compaction.py`, `test_agent_swarm_observer.py`, `test_agent_swarm_settings.py`, `test_agent_swarm_stop.py`. This stage may not edit any README.

## Open items

1. `tests/features/agent_swarm/README.md` File Index needs the four new modules and v2 wording for the existing entries (S020). Owner: S3.
2. Spec gap: EC-1's null case and INV-5's non-string text cannot reach `post_message` while `BaseTool.validate_call` (`vidbyte/tools/base.py:86-96`) treats a `None` required argument as missing. The spec does not name the override; the tests hold the spec's behavior and the test plan's note 1 gives the fix (`AgentSwarmMessageTool.validate_call` returns `None`).
3. The contract test's one I001 clears once the two new modules exist; re-run `ruff --isolated` after P3.
4. This report is not in either commit (the briefing's two `git add` lists do not name `reports/`); the orchestrator commits it.
5. The three `tests/features/harness_threads/test_harness_threads_surface.py` failures are inherited and untouched.

OPEN ITEM 1 resolved in this commit.

`PYTHONPATH=<worktree> python lint/run.py --rule S020` after the README update:

```
S020   readme-file-index-parity                    1      1 RATCHETED

S020 RATCHETED: 1 known finding(s). Inspect with: python lint/run.py --rule S020 --all

SDK-LINT: PASS
```

The one remaining finding is the baseline one, outside this folder: `vidbyte/agents/multi/README.md:26 File Index entry multi_agent.py is out of parity`. It was left as it is.

## S3 follow-up (commit 1ddc6b9d)

S3 found three defects in this pack after its implementation landed, and the orchestrator confirmed them (`11 failed, 257 passed` at `18565c17`). All three were test-side. Each fix keeps every assertion it touches at its original strength.

- **D1: the oracle could never accept a `compaction` event (8 cases).** Root cause: `_Replay.step` in `agent_swarm_fixtures.py` stored every kind except derived kinds and `message_undelivered` as the agent's last base event, before dispatch. A `compaction` therefore became its own base, and `observation` then required that base to be a `model_called`, which could never hold. Change: `if kind not in _DERIVED | {COMPACTION} and kind != UNDELIVERED:`, plus a one-line comment. The compaction check itself (base is the side call's `model_called`, trigger set) is unchanged.
- **D2: two system-string comparisons missed the shared loop's label (3 cases).** Root cause: every agent's system string is rendered by `BaseContext.build_context_fixed` (`vidbyte/lib/dataclasses/context.py:211-218`; the coordinator's note called it `ContextWindow`, but the method lives on `BaseContext`). It writes `"System prompt:\n"` before the prompt. That file is outside this change (NG-1). Change: `test_agent_swarm_contract.py::test_every_member_gets_the_same_sectioned_system_prompt_then_the_agentic_loop_prompt` and `test_agent_swarm_acceptance.py::test_the_section_4_snippet_runs_as_written` now compare `system[:loop_at].strip() == "System prompt:\n" + expected`. Each has a comment naming the label's source. The comparison is still exact equality.
- **D3: the EC-6 test relied on scheduling that the scripted runner does not provide (1 case).** Root cause: the scripted runner never suspends. Builder therefore ran its whole script, and its summary side call crossed `max_tokens=1_000` before tester's first model call. Tester was then refused, as EC-12 requires, and its scripted reply was never consumed, so `assert_complete` failed. Change: in `test_a_side_call_that_reaches_the_budget_completes_its_compaction_and_stops_the_swarm`, the side step is now `after(log.signal(IDLE, "tester"), reply(SUMMARY, ...))`, and the same `EventLog` is passed to `_run`. Tester's call adds 5 tokens, so the side call is still the one that crosses the budget. All assertions are unchanged.

Proof:

```
$ PYTHONPATH=<worktree> python -m pytest tests/features/agent_swarm -q -p no:cacheprovider
....................................................                     [100%]
268 passed in 7.07s

$ PYTHONPATH=<worktree> python -m ruff check tests/features/agent_swarm --config lint/ruff.toml
All checks passed!
```

The compaction module passed 8 repeated runs in a row (`12 passed` each), and the I001 noted earlier in the contract test is gone now that the modules exist.
