# S4 findings verifier — report

Stage: S4, findings verifier · Diff: `git diff origin/main...c0b167d3` (local HEAD `038118e2` differs only in `docs/spec/agent-swarm/pipeline.md`) · Output: `docs/spec/agent-swarm/review.md` · No commits, no edits to the worktree apart from these two files.

Verdict: **MERGEABLE AFTER FIXES**. 1 confirmed Blocker, 4 confirmed Majors, 10 Minors. 1 finding refuted (the orchestrator's suspicion) and 3 proposed fixes refuted. 0 downgraded.

## How the evidence was produced

- **Scratch copy.** I copied `vidbyte`, `contracts`, `lint`, `pyproject.toml`, `tests/__init__.py` and `tests/features/agent_swarm` into `…/scratchpad/s4-verify/`, then confirmed the copy was identical to the worktree with `diff -r vidbyte <worktree>/vidbyte -x __pycache__ -q`.
  - Every probe and fix ran there, with `PYTHONPATH=<copy>`.
  - The probes print `vidbyte from …\s4-verify\vidbyte\__init__.py`, so the global editable install was never used.
  - Lint needs `git ls-files`, so the copy was made a throwaway git repo (`git init` inside the scratch folder only).
  - C015 and C016 show REGRESSED in the copy only because the copy is partial; this happens in every run, including the baseline. Every comparison below is against the copy's own baseline table.
- **Probe scripts.** They are kept, and run against the worktree as well, from its root with `PYTHONPATH=$(pwd)`. All live in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/s4-probes/`:
  - `probe_verify.py [p1 p2 p3 p4]`
  - `probe_idle_cancel.py`
  - `probe_m2.py`
  - `probe_m2_reviewer_recipe.py`
  - `probe_m7.py`
  - `probe_d10.py`
  - `probe_toolname.py`
  - `mutate.py`: run it **only** in a scratch copy, because it rewrites source files in the current directory.
  - `lint_base.txt`, `lint_fixed.txt`, `lint_folded.txt`: the lint tables compared below.
- **Cleanup.** The scratch copy was deleted at the end; the probes remain.

## Merge map

| Original IDs | Merged ID | Severity | Note |
|---|---|---|---|
| R-C1 | R-1 | Blocker | all five clauses confirmed as advice |
| R-C2, R-V3 (item 1), R-E5 | R-2 | Major | same root cause: `settings.py:103` reserves six names, and `_internal.py:53` replaces `isDone`; the highest severity (Major) is kept |
| R-E1 | R-3 | Major | reproduced; the fix is refined with a `_stop_reason is None` guard |
| R-V1 | R-4 | Major | confirmed on precedent plus the owner's comment; the field-guide citation is narrower than claimed |
| R-E2, R-E3 (test part) | R-5 | Major | four surviving mutants (M2, M7, M21, M22); the reviewer's M2 recipe is refuted and replaced |
| R-C3, R-V4 | R-6 | Minor | README wording, same sentences |
| R-V5 | R-7 | Minor | |
| R-E4 | R-8 | Minor | reproduced |
| R-V3 (item 3) | R-9 | Minor | do it in the same edit as R-3 |
| R-V6 | R-10 | Minor | do it in the same edit as R-2's header |
| R-C4, R-V3 (item 2) | R-11 | Minor | same root cause (where the clock starts); minimal fix verified |
| R-C5, R-V7 | R-12 | Minor | same deviation, reported by two lenses |
| R-V2 | R-13 | Minor | the no-ask fold was verified lint-clean |
| R-E3 (spec part) | R-14 | Minor | INV-11 and EC-18 conflict |
| R-V8 | R-15 | Minor | scope-adding; Q-11 already settled it |
| Orchestrator suspicion (commit IDs) | — | refuted | |

## Verifications

### R-1 (R-C1): workflow advice in the prompt leaves — CONFIRMED, Blocker

**Source.**
- The user's words (request.md §A Prompt 1): "dont want to influence the same biases as the InfiniteMemoryAgent, want to tell all the agents that they are working in an agent swarm, they have the ability to edit files and communicate with other agents".
- Prompt 1's premise: the agents "developed their own strategies".
- The spec: NG-10 ("Routing roles, planning, or any workflow advice in the swarm prompt"); INV-22 ("No prompt leaf of the swarm states … a workflow"); FR-9 ("tells it only …"); §14 Never ("put numbers, roles or workflow advice in the swarm prompt"); §12.3 row 8 ("No roles, no strategy, no digits"); row 12 (the sent text "says the message is queued for that agent and that its reply, if any, arrives later as a user message").

**Leaf-by-leaf reading.** I printed every leaf with `cat vidbyte/prompts/prompts/agent_swarm/*.md`.

| Leaf | Clause | Verdict | Why |
|---|---|---|---|
| system_prompt.md:3 | "Every agent received the same goal … all of you work on it at the same time." | fact | |
| system_prompt.md:7 | "the other agents may change its files while you work" | fact | the shared folder (§C, NG-9) |
| system_prompt.md:7 | "so read a file again before you rely on what it held earlier" | **advice** | prescribes a working habit |
| system_prompt.md:7 | "returns at once, without waiting for that agent to read or answer it" | fact | INV-4 |
| system_prompt.md:11 (How the swarm works) | all four sentences | fact | INV-6, FR-6, AC-14 |
| system_prompt.md:15 (Limits) | both sentences | fact | INV-9, INV-12; no digits |
| system_prompt.md:19 | "the reply that ends your last turn is your final answer" | fact | FR-15 |
| system_prompt.md:19 | "so say in it what you did and what is left" | **advice** | the SDK handoff shape: `infinite_memory/generator_system_prompt.md:49` "**Open items**: what is left", `:51` "Report only what you did and checked", `jev_bulk_work/worker_system_prompt.md:15` "say plainly what you did" (grep verified) |
| message_tool_description.md s1–s3, s5 | "Sends one text … refused, and nothing is sent." | fact | |
| message_tool_description.md s4 | "Any answer comes back to you later in the same way" | fact | |
| message_tool_description.md s4 | "so keep working instead of waiting for it" | **advice** | steers against the accepted pattern, request.md §C: "An agent that wants an answer ends its turn (goes idle) and is woken when the reply arrives" |
| message_sent.md | "Any reply arrives later as a user message" | fact | row 12 |
| message_sent.md | "so keep working." | **advice** | goes beyond row 12; same SDK nudge as `vidbyte/agents/contracts/floors.py:133` "Keep working." |
| message_text_description.md s1, s4 | "delivered whole …", "must not be empty or blank" | fact | |
| message_text_description.md s2 | "Write it so it stands on its own" | **advice** | its "because …" half is a fact and is kept |
| message_text_description.md s3 | "Say what you did, what you need, or what changed, and name the files …" | **advice** | prescribes message content, which is the user's "own strategies" |
| message_to_description.md | "Make a separate call for each agent that needs the message." | not advice | the one-recipient rule (D-13) stated as call mechanics |
| message_blank_text.md | "Write the message in text and call the tool again." | not advice | a remedy that makes the call succeed (error-message practice) |
| message_unknown_recipient.md | "Send it to one of these agents instead: {agents}." | not advice | same: a remedy, not a strategy |
| message_stopped_recipient.md, inbox.md, inbox_message.md | — | fact | |

**Why the tests miss it.** `ROLE_WORDS` (test_agent_swarm_contract.py:83) lists six InfiniteMemory words, and none of the five clauses uses one. The test passes, and the prose fails.

**Fix verified on the scratch copy.** I applied the five exact replacements written in review.md R-1.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` → `161 passed in 3.74s`.
- `grep -rn -i "keep working\|read a file again\|what is left\|stands on its own\|what you did" vidbyte/prompts/prompts/agent_swarm` → no output (`grep exit 1`).
- The leaves were then restored, and the copy was confirmed identical to the worktree.

**Severity.** Blocker stands. The clauses break a weighted user word and a §14 Never, and the spec calibration puts both in the Blocker tier.

### R-2 (R-C2 + R-V3 item 1 + R-E5): a search tool named `isDone` is silently dropped — CONFIRMED, Major

**Code.**
- `vidbyte/tools/_internal.py:51-53`: `def with_internal_agent_tools(tools): return tools.add(IsDoneTool(), replace=True)`.
- `settings.py:103` refuses only `AGENT_SWARM_RESERVED_TOOL_NAMES`, the six swarm names.
- The constants header (`agent_swarm.py:9`) says "the loop's own isDone is refused by the tool catalog itself". That is false: the catalog replaces the tool.

**Probe** `probe_verify.py p3`:
```
P3 settings accepted a search tool named isDone
P3 tools offered: ('bash', 'grep', 'read_lines', 'write_text', 'patch_file', 'message', 'isDone')
P3 isDone description seen: Call this when you are done with the problem; this is how you stop the loop.
P3 search tool ran: [] stop: quiet
```

**Spec.**
- INV-21: "Every agent holds exactly the tools … and the loop's own `isDone`, plus the developer's search tool when one is given". This fails on this input.
- EC-33, read with §9.3, reserves six names, so by its letter EC-33 does not promise a refusal of `isDone`.
- INV-21 together with INV-18 (refuse at construction) can only hold by refusing the name. The severity therefore rests on INV-21 and on the false code claim.

**Severity.** Major. A configured tool is lost silently on a reachable input, and a comment claims a guard that does not exist; a human reviewer would flag both. The reviewers split Major, Minor, Minor, and the merge rule keeps the highest.

**Fix verified** (settings.py: `reserved = (*AGENT_SWARM_RESERVED_TOOL_NAMES, IS_DONE_TOOL_NAME)`):
```
vidbyte.lib.errors.base.ConfigurationError: AgentSwarmSettings.search_tool must not take a swarm tool's name; got 'isDone'. Reserved: bash, grep, read_lines, write_text, patch_file, message, isDone.
```
- The pack gave 161 passed.
- The lint table was identical (see "Combined fix check" below).
- `IS_DONE_TOOL_NAME` is already imported from `vidbyte.tools._internal` by `vidbyte/agents/runtime.py:150`, `vidbyte/agents/jev/compute/facts.py:15` and `vidbyte/agents/jev/done/event_log.py:27`.
- The tuple must not change: test_agent_swarm_contract.py:410 asserts `constants.AGENT_SWARM_RESERVED_TOOL_NAMES == ("bash", "grep", "read_lines", "write_text", "patch_file", "message")`.

### R-3 (R-E1): an unrequested CancelledError waits out the time limit — CONFIRMED, Major

**Code.**
- `_run_member` (runtime.py:122-139) catches only `VidbyteSdkError`.
- `BaseAgent.generate_reply` re-raises `BaseException` after closing its trace (base.py:980-984).
- The member's name stays in `_working`, and the 3.11 TaskGroup returns early for a cancelled child.

**Probes** (`probe_verify.py p1 p2`, HEAD code):
```
P1 elapsed 3.02 AgentSwarmStopReason.TIMEOUT ['1 agent_started builder', '2 agent_started tester', '3 agent_idle tester', '4 swarm_ended '] []
P2 elapsed 3.01 AgentSwarmStopReason.TIMEOUT ['1 agent_started builder', '2 agent_started tester', '3 tool_called builder', '4 agent_idle tester', '5 swarm_ended ']
```

**The idle variant (my own probe, `probe_idle_cancel.py`).** `on_event` raises `CancelledError` on tester's `AGENT_IDLE`, and builder then messages tester:
```
--- without fix (HEAD code)
IDLE-VARIANT elapsed 3.01 timeout ['1 agent_started builder', '2 agent_started tester', '3 agent_idle tester', '4 message_sent builder', '5 agent_woke tester', '6 tool_called builder', '7 agent_idle builder', '8 swarm_ended ']
```
The dead task is woken and counted as working, so the swarm cannot end until the limit. This is a second path the reviewer did not show.

**Adjudication against the spec.**
- INV-16 says "Cancellation and other BaseExceptions are never swallowed". The swarm's own code does not swallow the error, but the TaskGroup drops it, and the run then breaks:
  - INV-10: the swarm ends exactly when no agent is working;
  - INV-14: a failed agent's last event is `AGENT_FAILED`;
  - G-3: every swarm ends by itself.
- EC-38 and A-12 list the uncontained exceptions as `KeyboardInterrupt`/`SystemExit` and `Exception`s from the runtime's own code. A stray `CancelledError` from a member's run is in neither list.
- Propagating it from `arun` would mean cancelling every other member, which contradicts INV-17 ("One agent's contained failure never stops another agent").
- Conclusion: "contained as `AGENT_FAILED`, then re-raised" is the reading that meets INV-10, INV-14, INV-16, INV-17 and G-3 together. The spec should record it, because neither EC-38 nor INV-17 names this case.

**Fix verified on the scratch copy.** It is the reviewer's fix plus my guard `and self._stop_reason is None`. The guard leaves alone an agent whose end was already decided: such an agent was released, and failing it after `SWARM_ENDED` was decided would record a failure after the decision.
```
P1 elapsed 0.0 AgentSwarmStopReason.QUIET ['1 agent_started builder', '2 agent_started tester', "3 agent_failed builder (CancelledError: the agent's run was cancelled by something other than the swarm.)", '4 agent_idle tester', '5 swarm_ended '] [('tester', 'Tester done.')]
P2 elapsed 0.0 AgentSwarmStopReason.QUIET [... "4 agent_failed builder (CancelledError: ...)", '5 agent_idle tester', '6 swarm_ended ']
IDLE-VARIANT elapsed 0.02 quiet ['1 agent_started builder', '2 agent_started tester', '3 agent_idle tester', '4 agent_failed tester', '5 tool_called builder', '6 agent_idle builder', '7 swarm_ended ']
161 passed in 3.16s
```
- `cancelling() == 0` tells a stray cancellation apart from a requested one. `asyncio.timeout`, `TaskGroup` sibling cancellation and EC-19's caller cancel all go through `Task.cancel()`, which raises the count. The AC-6 and EC-19 tests in the pack still pass.
- A failed idle agent keeps its future in `_waiting`, which is harmless: `post_message` checks `_failed` before it wakes anyone, and `_end_check` only resolves the future.

### R-4 (R-V1): `AgentSwarmTurnMiddleware` sits outside the middleware layer — CONFIRMED, Major (needs §8.4 amendment)

**Grep.** `grep -rn "(AgentMiddleware)\|(AgentMiddleware, \|Middleware):" vidbyte --include=*.py | grep "class " | grep -v "^vidbyte/middleware"` prints only `vidbyte/agents/agent_swarm/member.py:73:class AgentSwarmTurnMiddleware(AgentMiddleware):`.

**Precedent.** Every other middleware, including agent-specific ones, lives in `vidbyte/middleware/`:
- `builtins/delegation_limits.py` belongs to InfiniteMemoryAgent, the sibling. Its header says "Attached by InfiniteMemoryAgent".
- `builtins/verify_command.py` belongs to CodingAgent and is "Not re-exported from vidbyte.middleware.builtins".
- `vidbyte/middleware/continual_trace.py` is a bridge to an agent. It imports `vidbyte.agents.base` under `TYPE_CHECKING` and `vidbyte.agents.continual_trace` at run time.
- REPO_MAP.md:259-261 says the middleware layer "is deliberately where policy lives".

**Field-guide check.** `blocking-lint-invariants.md:3-8` is narrower than the reviewer says.
- Its "When" is an `AgentMiddleware` that bridges a `vidbyte/sessions/*` object, and its body is about the A006 layer order between sessions and middleware.
- What carries over is the owner's comment it quotes: PR #399, "should be defined in the middleware layer".
- So the finding stands on the owner's stated preference plus a precedent with no exceptions, not on that entry's own scope. It would surface in human review, so Major is correct. It is not a Blocker, because no field-guide lesson literally covers this case.

**Test import.** `git grep -n "AgentSwarmTurnMiddleware" -- tests/` finds `test_agent_swarm_contract.py:108`: `from vidbyte.agents.agent_swarm.member import AgentSwarmMemberAgent, AgentSwarmMessageTool, AgentSwarmTurnMiddleware`.

**Move verified on the scratch copy.** The new file `vidbyte/middleware/builtins/agent_swarm_turn.py` holds the class unchanged, with an A001 header and `AgentSwarmRuntime` under `TYPE_CHECKING`. `member.py` imports it from there.
- Pack: `161 passed`. The test import still works because `member.py` binds the name. `python -c "from vidbyte.agents.agent_swarm.member import AgentSwarmTurnMiddleware as A; print(A.__module__)"` → `vidbyte.middleware.builtins.agent_swarm_turn`.
- The full lint table matched the baseline; see "Combined fix check".
- **No test change is needed.**
- **The budget amendment is needed:** 24 new files against §8.4's 23, and a file outside §12.3. Both are §14 ask-first.
- `vidbyte/middleware/builtins/` has no README, so S020 adds no File Index duty there.

### R-5 (R-E2 + R-E3 test part): four specified behaviours have no test that can fail — CONFIRMED, Major (S2 test author)

**Mutation run** (`python <probes>/mutate.py` in the scratch copy; full pack per mutant; file restored after each):
```
M2_failed_inbox_counts_for_max_turns: 161 passed in 3.15s (exit 0)
M7_timeout_overrides_decided_reason: 161 passed in 3.24s (exit 0)
M21_no_history_trim: 161 passed in 3.25s (exit 0)
M22_no_result_cap: 161 passed in 3.28s (exit 0)
CTRL_end_check_never_failed: 1 failed, 160 passed in 3.44s (exit 1)
```

**Each mutant is reachable and wrong, and each maps to a spec ID:**
- **M2 → INV-10** ("MAX_TURNS when some idle, *running* agent still holds undelivered messages") and **EC-12** ("Its queued messages stay undelivered; the others continue"). `probe_m2.py` (builder sends while reviewer's first model call is in flight; that call raises):
  ```
  --- HEAD
  M2-PROBE quiet ['1 agent_started builder', '2 agent_started reviewer', '3 message_sent builder', '4 tool_called builder', '5 agent_idle builder', '6 agent_failed reviewer', '7 swarm_ended ']
  --- M2
  M2-PROBE max_turns [same events]
  ```
  The engineering reviewer's recipe holds reviewer in `BlockingSearchTool`, then makes its next call fail. It does not kill M2, because the message is delivered at `_after_tool_iteration` before the failing call. `probe_m2_reviewer_recipe.py`, run with M2 applied:
  ```
  REVIEWER-RECIPE quiet ['agent_started builder', 'agent_started reviewer', 'message_sent builder', 'tool_called builder', 'agent_idle builder', 'tool_called reviewer', 'message_delivered reviewer', 'agent_failed reviewer', 'swarm_ended ']
  ```
- **M7 → INV-10** ("TIMEOUT overrides all three when the time limit is reached before the swarm had decided to end") and **EC-18**. `probe_m7.py`: an async `on_event` whose hook awaits a never-set event on tester's `AGENT_IDLE`; `timeout_seconds=0.5`. Three runs on HEAD, then one with M7:
  ```
  EC18-PROBE elapsed 0.5 quiet [...] [('builder', 'Builder done.')]
  EC18-PROBE elapsed 0.52 quiet [...] [('builder', 'Builder done.')]
  EC18-PROBE elapsed 0.52 quiet [...] [('builder', 'Builder done.')]
  --- M7
  EC18-PROBE elapsed 0.52 timeout [...] [('builder', 'Builder done.')]
  ```
  The result is deterministic and costs one 0.5-second wait, the same seam as the EC-23 test. The waiver at test-plan.md:89 ("needs wall-clock timing, which would be flaky") is therefore false.
- **M21 → EC-26 and D-10; M22 → D-10** (and the §9.3 cap "the model sees"). These two map to a decision and an edge case, not to an AC. They are included because the EC-26 waiver (test-plan.md:91, "covered by its own tests") covers the middleware but not the swarm's wiring of it. `probe_d10.py` (a search tool returning 250,000 characters, six calls):
  ```
  --- current   D10 last call: messages 6 max content chars 100070 total chars 300210
  --- M22       D10 last call: messages 2 max content chars 250000 total chars 250000
  --- M21       D10 last call: messages 12 max content chars 100070 total chars 600420
  ```

**Ownership.** These are test defects, so the owner is the S2 test author. The repair agent may not edit `tests/`.

### R-6 to R-15 (Minors): what I checked myself

- **R-6.** The quoted sentences are present: `agents/README.md:205` ("after its current tool call", "`max_turns` when the turn budget is spent"), `agent_swarm/README.md:3` and `:42`, and `REPO_MAP.md:77`. A-1 and INV-10 contradict them.
- **R-7.** `awk 'NR>=78 && NR<=84 {print length($0)}' vidbyte/agents/base.py` → `99`, `99`, `95`. The third line is new in the diff (`git diff origin/main...c0b167d3 -- vidbyte/agents/base.py`). comment-format.md:3-8 covers "Writing or editing any `#` comment".
- **R-8.** `probe_toolname.py`:
  ```
  'bash_tool' quiet ['agent_started builder', 'agent_started tester', 'tool_called builder', 'agent_idle builder', 'agent_idle tester', 'swarm_ended ']
  'bash\nrm' quiet ['agent_started builder', 'agent_started tester', "agent_failed builder (The agent's run ended before the swarm released it, with stop reason middleware_abort.)", 'agent_idle tester', 'swarm_ended ']
  ```
  No test pins `one_line` for `tool_name`: in `grep -n "tool_name" test_agent_swarm_contract.py`, the cases are blank, missing and on the wrong kind only.
- **R-9.** runtime.py:9 contradicts `_fail` at :245-250 for a member that failed before the limit.
- **R-10.** The header sentence follows spec §9.3's wording. Field guide strict-config-dataclasses.md:68-73 asks for the sum. The figures are the reviewer's measurement; the repair agent re-measures them.
- **R-11.** `probe_verify.py p4` → `P4 first event elapsed_ms: 406 stop: quiet`. With `self._events = AgentSwarmEvents(self._settings.on_event)` added after `self._ran = True` → `P4 first event elapsed_ms: 0` and `161 passed in 3.31s`. No test reads `_events`, `_inboxes` or the other private state before a run (grep of the pack: no hits).
- **R-12.** runtime.py:141 is `async def post_message(self, sender: str, recipient: object, text: object) -> str:`; spec.md:461 types both as `str`. Neither the S3 report's deviations 1-7 nor spec §17 list it.
- **R-13.** I folded the three helper bodies into `__post_init__` on the scratch copy:
  - pack: `161 passed in 3.87s`;
  - `lint/run.py --rule S008`: `S008 RATCHETED: 19 known finding(s)` / `SDK-LINT: PASS`;
  - full table against the baseline: only C015 changed, by 944 → 945, a scratch artifact (pytest `__pycache__` files got git-added; C015 is package-data coverage).

  The reviewer's fear that C901 would block the fold does not hold. It stays Minor, for the reasons in review.md R-13. The `lint/rules/s008_bounded_function_complexity.py` repair text ("move implementation detail into typed private leaf methods") points the other way from the field guide, which is a further reason not to force it in this PR.
- **R-14.** Shown by the `probe_m7.py` output above: tester's reply is missing from `replies` on a QUIET result, and its text survives in `AGENT_IDLE`.
- **R-15.** Q-11 decided "No — a private helper". It is scope-adding, so it is a follow-up.

### Combined fix check (blind-spot test: do the fixes break each other or the gates?)

I applied R-1, R-2, R-3 and R-4 together on the scratch copy, ran `git add -A` inside the copy, and then ran:
```
PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q -p no:cacheprovider   → 161 passed in 3.95s
PYTHONPATH=$(pwd) python lint/run.py | grep -E "^[A-Z][0-9]{3} " > lint_fixed.txt
diff lint_base.txt lint_fixed.txt   → (no output) diff exit 0
```
Every rule count matched the baseline, including A001, A002, A006 (34/34), S006, S008, S015, S019 (5/5), S020, S024 (25/25), S051 and S063. P1 and P2 then end QUIET at once, and P3 is refused at construction.

### Blind spots checked (no new finding beyond what review.md lists)

- **Tests vs fixes.** The fixes touch three places the tests read, and none of them breaks a test:
  - the prompt leaves, which the tests match through catalog-template regexes, sentence counts and field sets, not literal wording;
  - `member.py` import paths (test :108);
  - the reserved-names tuple (test :410).
- **Fix interactions.**
  - R-3, R-9 and R-11 all edit `runtime.py`; R-3 and R-9 share one header paragraph.
  - R-4 edits the ROLE IN CODEBASE line of `runtime.py` and the `member.py` header.
  - R-2 and R-10 edit the same constants header.
  - R-1 is independent.
  - R-5's tests must pass on the code both before and after repair. None of them depends on R-1 to R-4.
- **`AgentSwarmResult` and replies on TIMEOUT.** The record does not enforce §9.1's "replies empty on TIMEOUT". Under M7 it accepted a TIMEOUT with one reply. On HEAD this cannot happen, because a reply exists only after a decided release, and a decided reason is never TIMEOUT. Not filed.
- **AC-6's loose bound.** The bound is `elapsed < timeout + 10 s`, while NFR-9's offline target is under 1 second. The engineering reviewer weighed this and did not file it; the test plan states it is loose on purpose, and the test still fails if the limit does not cancel at all. Not filed.
- **A `CancelledError` in the final flush.** If `on_event` raises `CancelledError` on `SWARM_ENDED`, it propagates from `arun`. That matches INV-16. Not filed.

## Adjudications between reviewers

- **The `isDone` severity: conformance said Major; conventions and engineering said Minor.** I kept Major. The merge rule keeps the highest severity, and nothing in the evidence argues for less: the loss is silent, the comment claims a guard that does not exist, and the fix is three lines. On the fix itself, conventions and engineering offered "reserve it in the tuple", which the test and §9.3 rule out. Conformance's `settings.py` route is the one that works.
- **The R-E3 tier.** Engineering said Minor; I moved the test part into Major R-5 and kept the spec part Minor (R-14).
  - Conformance considered the same EC-18 window and did not file it ("consistent with EC-18 … not filed"). That is right for the code's behaviour, which the spec does not decide.
  - It is wrong for test coverage, because M7 survives.
- **R-C4 against D-16.** Conformance saw a deviation-record error; conventions saw a header error. Both describe the same root cause, so I merged them into R-11. It stays Minor: only the public runtime path is affected, and sequence order is untouched.
- **R-V2's severity.** The briefing asked me to decide. I kept Minor; reasons in review.md R-13.

## Commands run (final lines)

- `diff -r vidbyte <worktree>/vidbyte -x __pycache__ -q && echo "copy identical to worktree vidbyte"` → `copy identical to worktree vidbyte`. This was checked before each fix trial and after each restore.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q -p no:cacheprovider` (unchanged copy) → `161 passed in 4.12s`.
- `PYTHONPATH=$(pwd) python lint/run.py` (copy baseline) → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: FAIL`. The FAIL is C015 (944) and C016 (1) only, both partial-copy artifacts; every other rule is RATCHETED, IMPROVED or CLEAN.
- `git log -1 --format=%b 0d64078a | 28444b65 | f97170ec` → `W-1, W-3 to W-11.` / `W-3; FR-3, FR-14; AC-13, AC-17.` / `W-7, W-8, W-9, W-10, W-11; FR-2 to FR-7, FR-11, FR-13 to FR-18; AC-1 to`.
- The probe, mutation and lint outputs are quoted in full above.

## Housekeeping

- The scratch copy `…/scratchpad/s4-verify/` was deleted after the last run. The probe scripts and lint tables stay in `…/scratchpad/s4-probes/`.
- The worktree is unchanged apart from `docs/spec/agent-swarm/review.md` and this report. Both are untracked and not committed.
