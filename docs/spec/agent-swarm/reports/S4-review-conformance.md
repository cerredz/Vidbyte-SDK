LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — The lifecycle, events, budget and boundaries match spec r3 and the user's answers on every path traced. Two things are wrong. Five clauses in the prompt leaves give the workflow advice the user ruled out. A search tool named `isDone` is silently dropped.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The decomposition is the one the user asked for, and §8.5 states it:
  - `AgentSwarm` (swarm.py:26-56) is a thin entry point. It holds a flag, checks the goal, prepares the folder, and builds one fresh `AgentSwarmRuntime` per `arun`.
  - `AgentSwarmRuntime` (runtime.py:41) is the per-run coordinator. It owns the inboxes, working/failed/waiting sets, turns, stop reason and replies.
  - `AgentSwarmEvents`, `AgentSwarmWorkplace` and `AgentSwarmTools` each have one role.
  - `AgentSwarmMemberRuntime` overrides one hook only, `_after_tool_iteration` (member.py:62-70).
- The lifecycle holds on every path traced. These were checked against the code, not only the tests:
  - The decision, the state change and the event record share one synchronous block in `post_message` (runtime.py:150-168), `end_turn` (runtime.py:189-204) and `_end_check` (runtime.py:260-271).
  - The idle mark, the wait future and the end check run before the first `await` (runtime.py:201-205), so the EC-1 race cannot lose a wake.
  - A wake is decided at send time and counted against the budget (runtime.py:164-168).
  - QUIET, MAX_TURNS and FAILED are decided exactly as INV-10 states (runtime.py:262-268).
  - TIMEOUT is used only when no reason was decided first (runtime.py:101).
  - No `asyncio.sleep` and no polling.
- The boundaries are exact:
  - The new and modified files match the budget: 23 new and 13 modified, the §8.4 numbers.
  - `lint/baseline.json` is unchanged, and `tests/` has not changed since `87c8ed14`.
  - `runtime.py`, `runtimes/actor/`, `infinite/`, `jev/` and `validation.py` are untouched.
  - The `base.py` change is only the `_LINEAR_LOOP_RUNTIMES` entry plus two comment lines.
  - No NG-1..NG-10 feature was built: no backlog, lock, broadcast, `web_fetch`, journal, events file or CLI.
- AC-1 is bound correctly. `test_agent_swarm_acceptance.py:64-91` pastes the §4 snippet byte for byte: the same three public imports, the settings fields `agents`/`workplace`/`on_event`, and the result fields `stop_reason`, `events`, `replies`, `reply.sender` and `reply.content`. Only `BaseAgent._runner_for_model` is replaced, and the test compares every printed line with the lines rebuilt from `result.events`. The env-key path the real snippet relies on (A-6) exists in `ProviderModelRegistry.resolve_api_key` (vidbyte/lib/registries/models.py:159-168).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [the user's words] vidbyte/prompts/prompts/agent_swarm/system_prompt.md:7 — The swarm prompt and the message-tool leaves give workflow advice, violating NG-10 ("any workflow advice"), FR-9 ("tells it only …"), INV-22 and the user's "dont want to influence the same biases as the InfiniteMemoryAgent"
  Evidence: five clauses go beyond the facts that §12.3 rows 8, 11 and 12 list.
  - system_prompt.md:7: "…the other agents may change its files while you work, so read a file again before you rely on what it held earlier."
  - system_prompt.md:19: "…the reply that ends your last turn is your final answer, so say in it what you did and what is left."
  - message_tool_description.md:1, sentence 4: "Any answer comes back to you later in the same way, so keep working instead of waiting for it."
  - message_sent.md:1: "Message queued for {recipient}. Any reply arrives later as a user message, so keep working."
  - message_text_description.md:1: "Write it so it stands on its own, … Say what you did, what you need, or what changed, and name the files in the shared folder it concerns."

  The "what you did and what is left" report shape is the SDK's existing handoff framing:
  - `vidbyte/prompts/prompts/infinite_memory/generator_system_prompt.md:49` "**Open items**: what is left…";
  - `:51` "Report only what you did and checked";
  - `jev_bulk_work/worker_system_prompt.md:15` "say plainly what you did".

  These are the InfiniteMemoryAgent-family biases the user excluded. "keep working instead of waiting for it" also steers agents against the coordination pattern the user accepted (request.md §C:58: "An agent that wants an answer ends its turn (goes idle) and is woken when the reply arrives").

  The spec says the opposite of what the leaves do:
  - Row 8 (spec.md:804) ends "No roles, no strategy, no digits."
  - Row 12 (spec.md:808) says the sent text only "says the message is queued for that agent and that its reply, if any, arrives later as a user message".
  - `vidbyte/prompts/README.md:106` claims the prompt "states no number, role, or workflow". That claim is false.

  The S2 test missed this because `ROLE_WORDS` bans only six InfiniteMemory words (tests/features/agent_swarm/test_agent_swarm_contract.py:83).
  Failure: every member's system prompt and tool schema tell the model how to work: re-read files, keep working instead of idling, and report "what you did and what is left". The user asked the prompt to say only that the agents are in a swarm, can edit files, and can message each other. The behaviour data the user wants from the swarm ("valuable data") then reflects the SDK's nudges, not the agents' own coordination.
  Smallest fix: delete the advice and keep only the facts. Each description leaf must stay at 4–5 sentences, because the contract test checks that (test_agent_swarm_contract.py:216-218). Keep every `{field}`.
  - system_prompt.md:7: end the sentence at "…may change its files while you work."
  - system_prompt.md:19: end it at "…is your final answer."
  - message_sent.md: "Message queued for {recipient}. Any reply arrives later as a user message."
  - message_tool_description.md sentence 4: "Any answer comes back to you later in the same way."
  - message_text_description.md: replace sentences 2–3 with facts, for example "The recipient sees only this text and your name." and "It arrives as part of one user message labeled with your name."
  - prompts README:106: either keep it (once it is true) or correct it.
  Spec IDs: NG-10, FR-9, INV-22, AC-14 (its test passes; the prose fails), §12.3 rows 8, 11, 12; request.md §D Prompt 1.

R-C2 [Major] [every ID] vidbyte/agents/agent_swarm/settings.py:103 — A developer search tool named `isDone` is accepted and then silently replaced by the loop's own `isDone`, so the agents never hold it, violating INV-21/FR-3 ("plus the developer's search tool when one is given")
  Evidence:
  - settings.py:103 refuses only `AGENT_SWARM_RESERVED_TOOL_NAMES`, the six swarm names.
  - The loop then runs `tools.add(IsDoneTool(), replace=True)` (vidbyte/tools/_internal.py:51-53), which overwrites a same-named tool.
  - The constants header justifies leaving `isDone` out with a false claim (vidbyte/lib/constants/agent_swarm.py:9): "the loop's own isDone is refused by the tool catalog itself".

  Probe `…/scratchpad/s4conf/probe_isdone.py`, with `search_tool=SearchTool("isDone")`, shows this:
  ```
  settings accepted a search tool named isDone
  tools seen: ('bash', 'grep', 'read_lines', 'write_text', 'patch_file', 'message', 'isDone')
  isDone description seen by model: Call this when you are done with the problem; this is how you stop the loop.
  folder created: True
  ```
  Seven tools, not eight. The developer's tool is gone, no error is raised, and the folder was created anyway.
  Failure: settings with `search_tool` named `isDone` give a swarm whose agents silently lack the configured tool. EC-33 and INV-18 say a search tool that takes a name every agent already holds is refused at construction, naming the reserved names, before any folder exists. Here it is accepted and lost. The chance is low, but the drop is silent, and it contradicts a claim written in the code.
  Smallest fix:
  - In `AgentSwarmSettings.__post_init__`, refuse `self.search_tool.name` when it is in `AGENT_SWARM_RESERVED_TOOL_NAMES` or equal to `IS_DONE_TOOL_NAME` (vidbyte/tools/_internal.py:11). Name both in the message and in `details["field"] = "AgentSwarmSettings.search_tool"`.
  - Correct the constants header.
  - Do not change the tuple's value; §9.3 and test_agent_swarm_contract.py:410 pin it.
  Spec IDs: INV-21, FR-3, EC-33, INV-18, AC-13.

R-C3 [Minor] [the user's words] vidbyte/agents/README.md:205 — Three user-facing docs say a spent turn budget ends the swarm, or ends it MAX_TURNS. INV-10/EC-9 make the budget graceful: QUIET when no mail is waiting.
  Evidence:
  - agents/README.md:205: "`max_turns` when the turn budget is spent".
  - agent_swarm/README.md:3: "The swarm ends … when the turn budget is spent".
  - REPO_MAP.md:77: "when its turn budget or time limit runs out".
  - The package README table is correct (agent_swarm/README.md:47). So is AC-4's `budget-equals-agents` case, which spends the budget exactly and asserts QUIET (test_agent_swarm_acceptance.py:104-121, passing).
  - agent_swarm/README.md:42 and agents/README.md:205 also say a message arrives "after its current tool call". INV-6/A-1 put delivery after the tool *iteration*, that is, after all calls of one model response.
  Failure: a developer reads that a spent budget means `max_turns`, then gets QUIET with a spent budget (EC-9) and misreads the run. The same developer expects delivery between two calls of one response, which never happens.
  Smallest fix: change the three sentences to say that the turn budget stops wakes, and that the swarm then ends MAX_TURNS only if a message is still waiting; otherwise it ends QUIET. Change "tool call" to "tool iteration (all calls of one model response)".
  Spec IDs: INV-10, INV-9, EC-9, INV-6, A-1, D-8.

R-C4 [Minor] [deviations] vidbyte/agents/agent_swarm/runtime.py:53 — The event record, inboxes and clock are built in `AgentSwarmRuntime.__init__`, not in `arun` as §8.5 shows. So `elapsed_ms` counts from construction, not from "since the run started" (D-16), and the recorded deviation 6 misstates this.
  Evidence:
  - runtime.py:53-61 builds `AgentSwarmEvents`, which starts its clock at events.py:36 (`self._started_at = time.monotonic()`). The §8.5 pseudocode builds `events = AgentSwarmEvents(on_event); inboxes, statuses` inside `arun`.
  - spec.md:978 (deviation 6) says the clock starts "one statement before `arun` begins". events.py:9 says it is built by "AgentSwarm … when the run starts".
  - Both claims are true only through `AgentSwarm`. `AgentSwarmRuntime` is public (§9.2), and AC-18 has a runtime refuse a goal and run later.
  - Probe `…/scratchpad/s4conf/probe_clock.py` builds the runtime, waits 0.4 s, then calls `arun`. Output: `first event elapsed_ms: 406 (run started at 0 by D-16)`.
  Failure: on the public runtime path, every event's `elapsed_ms` includes the time before `arun` was called, and the first event is not near 0.
  Smallest fix: move lines 53-61 (`_events`, `_inboxes`, `_working`, `_failed`, `_waiting`, `_turns`, `_stop_reason`, `_replies`) into `arun` after the run-once check, as §8.5 shows. Then the deviation and the events.py:9 sentence can be dropped.
  Spec IDs: D-16, §8.5 pseudocode, §17 deviation 6.

R-C5 [Minor] [deviations] vidbyte/agents/agent_swarm/runtime.py:141 — The public `AgentSwarmRuntime.post_message` signature was widened from §8.5's `(sender: str, recipient: str, text: str)` to `recipient: object, text: object`. Neither the S3 report nor spec §17 records this.
  Evidence: runtime.py:141 `async def post_message(self, sender: str, recipient: object, text: object) -> str:` against spec.md:461. §14 lists "any change to a public signature not in §8.5 / §9.2" under "Ask first". The widening is reasonable, because the tool hands it unchecked model arguments (member.py:128) and the body type-checks both (runtime.py:151-153). But it is a deviation no one recorded.
  Failure: none at run time. The deviation record is incomplete, so a reader of the spec sees `str` while the code accepts any object.
  Smallest fix: add one bullet to §17 "Implementation deviations" (orchestrator's call). Alternatively, narrow the annotation back to `str` and keep the `isinstance` checks.
  Spec IDs: §8.5, §9.2, §14.

VERIFIED CLAIMS: each claim checked, and whether it held

**Implementer gates and boundaries**
- Pack 161/161: held. 161 passed in 3.26s on HEAD 038118e2; the product code is identical to c0b167d3.
- `SDK-LINT: PASS`: held. Contract `--check` is current at 698f913b: held.
- Neighbours 270 passed: held.
- Budget is 23 new and 13 modified product files, all in §12.3: held. The `git diff --name-status` list matches rows 1–37 exactly (row 4 is withdrawn).
- `git diff origin/main...c0b167d3 -- lint/baseline.json` is empty: held (0 lines).
- `git diff 87c8ed14..c0b167d3 -- tests/` is empty: held.
- The protected paths (`runtime.py`, `runtimes/actor/`, `infinite/`, `jev/`, `validation.py`) are untouched: held (empty diff).
- `base.py` changes only the `_LINEAR_LOOP_RUNTIMES` entry and comments: held (header line 14 and comment line 82 change, plus the set at line 83).
- The prompt enum header reads 149/36: held (149 dotted keys, 36 families).
- `RuntimeRegistry.resolve(AGENT_SWARM_MEMBER) is AgentSwarmMemberRuntime`: held.
- The root `AgentSwarm*` exports are exactly the five names: held.

**Reported deviations**
- Deviation 1 (Semaphore): necessary, because `lint/ruff.toml:8` bans `asyncio.Lock`. It is minimal and recorded: held.
- Deviation 2 (`ModelProvider(...)`): necessary. C012's provider proofs (`lint/rules/c012_provider_model_registry_validation.py`, `_PROVIDER_PROOF_METHODS`) do not include `to_enum`. The refusal still names the field. Recorded: held.
- Deviation 3 (`callable()`): not a deviation. Row 23 already says "`on_event` None or callable", and §11 cites `multi/validation.py:91` as the precedent. Harmless.
- Deviation 4 (start events flushed inside the time limit): it strengthens NFR-9. Without it, a stuck `AGENT_STARTED` callback would outlive `timeout_seconds`. Minimal and recorded: held.
- Deviation 5 (sorted placement): imports are forced by I001. `__all__` entries still sit beside infinite. Recorded: held.
- Deviation 6 (clock): recorded, but its justification fails on the public runtime path (R-C4).

**Unreported deviations found**
- The prompt text goes beyond rows 8, 11 and 12 (R-C1).
- The `post_message` signature was widened (R-C5).
- Run state is built in `__init__` (R-C4).
- The constants-header claim about `isDone` is false (R-C2).

**The user's weighted words (request.md §D)**
- Tools: held, apart from R-C2. Each member holds exactly bash, grep, read_lines, write_text, patch_file, message and isDone (runtime.py:228; member.py:154). read_lines was the default the user did not object to (§C). Web search is added only when `search_tool` is set (runtime.py:227).
- Swarm prompt, "only swarm / edit files / communicate": failed (R-C1). There are no digits (grep: none) and no InfiniteMemory role words.
- Five role classes, `AgentSwarmRuntime` as the per-run coordinator, `AgentSwarm` thin: held.
- "very minimal / start simple / forget the backlog": held. The diff contains no NG item. The only `backlog` hit is events.py's header wording about the event outbox.
- "idle; a new message wakes it; ends when every agent is idle with an empty inbox, or a max-turns / time limit": held. The budget is graceful per the settled D-8.
- "swarm.arun("goal") sends the same goal to every agent": held (runtime.py:97, 123; the INV-1 acceptance test checks byte equality on every call).
- "the result carries the full ordered tuple of events": held (runtime.py:106-112). `AgentSwarmResult.__post_init__` itself enforces 1..N and one final `SWARM_ENDED` (vidbyte/lib/dataclasses/agent_swarm.py:285-290).

**ID walk**
- FR-1..FR-18: held, except FR-3 (R-C2, on the `isDone` path only) and FR-9 (R-C1).
- NFR-1..NFR-9: held. NFR-2: no sleep in the package. NFR-3: every module is at most 289 lines. NFR-4: no digits in any leaf. NFR-9: AC-6 passes, and deviation 4 closes the gap left by the stuck-callback-at-start case.
- INV-1..INV-28: held, except INV-21 (R-C2) and INV-22 (R-C1).
- INV-11 on the EC-18 window: if the time limit hits while released agents are unwinding, those runs are cancelled. The decided reason stands, but `replies` may be partial. This is consistent with EC-18 and §9.1 ("at most one per agent"), so it is not filed.
- AC-1..AC-21: each named test exists and passes. AC-14's test cannot detect R-C1.
- EC-1..EC-38: held, or a stated limitation. EC-33 does not cover `isDone` (R-C2).

**§5 flow traced against the real call path**
1. `AgentSwarm.arun` (swarm.py:43-54) refuses a concurrent run, checks the goal, runs `AgentSwarmWorkplace.prepare`, then calls `AgentSwarmRuntime(settings, root).arun`. This matches.
2. `AgentSwarmRuntime.arun` (runtime.py:70-112) checks the goal, runs once, builds the members, and records `AGENT_STARTED` in member order. **Divergence:** the flush runs inside `asyncio.timeout + TaskGroup` (deviation 4, recorded). **Divergence:** the event record and state are built in `__init__` (R-C4).
3. Each member runs `agent.arun(goal)` inside `_run_member` (runtime.py:114-139). This matches.
4. `message` goes to `AgentSwarmMessageTool.execute`, then `post_message`, which queues the message, records `MESSAGE_SENT`, wakes an idle recipient if turns remain, then flushes. This matches.
5. `_after_tool_iteration` calls `collect_messages`, which drains the inbox and appends one user message (member.py:68-70; it runs after `after_iteration`, vidbyte/agents/runtime.py:690-700). This matches.
6. `review_finish` calls `end_turn`, which records IDLE, then either continues at once with mail or waits idle after the end check. `end_turn` then returns `continue_with(text)` or `accept()` (member.py:85-96). This matches.
7. `_end_check` releases the waiters, and `SWARM_ENDED` is recorded after the TaskGroup drains (runtime.py:106). This follows the §8.5 pseudocode and the sequence diagram. The flowchart's node E lists "record SWARM_ENDED, release idle agents" in the opposite order; this is a wording difference, not a defect.

**Other checks**
- Mixed-provider members build from one matched key record: held (probe_keys.py).
- An invalid search-tool name (with a space, or 200 characters) passes settings and reaches the model. This is the provider's problem, not swarm conformance, so it is not filed.

COMMANDS RUN: each with its final lines
- `git log --oneline -5` shows 038118e2, c0b167d3, … `git diff --stat origin/main...c0b167d3`: `56 files changed, 7653 insertions(+), 8 deletions(-)`.
- `git diff origin/main...c0b167d3 -- lint/baseline.json | wc -l`: `0`.
- `git diff --stat 87c8ed14..c0b167d3 -- tests/`: (empty).
- `git diff --stat origin/main...c0b167d3 -- vidbyte/agents/runtime.py vidbyte/agents/runtimes/actor/ vidbyte/agents/infinite/ vidbyte/agents/jev/ vidbyte/lib/dataclasses/validation.py`: (empty).
- `git diff origin/main...c0b167d3 -- vidbyte/agents/base.py`: 2 hunks; header line 14, comment line 82, set line 83.
- `git diff --name-status origin/main...c0b167d3 | grep -v "docs/\|tests/"`: `NEW: 23`, `MOD: 13`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/agent_swarm -q -p no:cacheprovider`: `161 passed in 3.26s`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent tests/test_agent_tool_loop.py tests/test_jev_compute.py tests/multi_agent tests/test_prompts_interface.py tests/test_agent_runtime.py tests/test_fork_tool.py tests/test_restore_actor_include_actors.py -q`: `270 passed in 6.08s`.
- `PYTHONPATH=$(pwd) python lint/run.py`: `S063 IMPROVED 4 -> 3 … SDK-LINT: PASS`.
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check`: `contracts/sdk-public-api.json is current at 698f913b… (vidbyte-sdk 0.3.0, 649 exports).`
- `grep -n "[0-9]" vidbyte/prompts/prompts/agent_swarm/*.md`: no output (exit 1). The role-word grep (`role|plan|strategy|verif|generat|delegat|scarce|context|memory`) found nothing either.
- `grep -rn "asyncio.sleep\|\.sleep(" vidbyte/agents/agent_swarm vidbyte/tools/toolsets/agent_swarm.py`: no output.
- `grep -rn -A2 "asyncio.Lock" lint/ …`: `lint/ruff.toml:8:"asyncio.Lock" = { msg = "Use the SDK-owned concurrency boundary." }`.
- `grep -rn -i "what is left\|read a file again\|what you did\|keep working\|before you rely" vidbyte/prompts/prompts/`: the five swarm hits in R-C1, plus infinite_memory/generator_system_prompt.md:49, :51 and jev_bulk_work/worker_system_prompt.md:15.
- `python -c` (prompt counts, registry, root exports): `dotted prompt keys: 149 families: 36`, `registry ok: True`, `['AgentSwarm', 'AgentSwarmEventKind', 'AgentSwarmMember', 'AgentSwarmSettings', 'AgentSwarmStopReason']`.

Probes are offline: scripted runners only, with no network or keys. Each runs with `PYTHONPATH=$(pwd) python <path>`, and the scripts are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/b5ead954-ba63-4734-96d3-7e412171de95/scratchpad/s4conf/`.
- `probe_keys.py`: `built a openai (openai, anthropic)` / `built b anthropic (openai, anthropic)` / `built(no keys) …` (held).
- `probe_clock.py`: `stop: quiet` / `first event elapsed_ms: 406 (run started at 0 by D-16)` (R-C4).
- `probe_isdone.py`: `settings accepted a search tool named isDone` / `tools seen: ('bash', 'grep', 'read_lines', 'write_text', 'patch_file', 'message', 'isDone')` / `isDone description seen by model: Call this when you are done with the problem; this is how you stop the loop.` (R-C2).
- `probe_badtool.py`: `'web search' -> ran quiet tools: (…, 'web search', 'isDone')` (not filed).
