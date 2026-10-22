---
slug: agent-swarm-v2
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-19 17:10
flags: none (the run updates the existing PR #1174 on branch feat/agent-swarm in place; see §C "Constraints")
---

# Request: AgentSwarm revision — same prompt for every agent, loose messaging, best-in-class compaction, generous limits, full event visibility (PR #1174 updated in place)

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (start of the conversation; the user asked for an explanation of the PR, which the assistant gave from the code on the branch):

````
explain to me the architecture of pr #1174 for the vidbyte-sdk/ repo? what are the main "components' of the agent swarm (runtime shape, tools, middleware, etc)
````

**Prompt 2** (after the architecture explanation):

````
can you kind of write the psuedocode for the runtime for me?
````

**Prompt 3** (after a Python-shaped pseudocode was given):

````
want simplified psuedocode, not actualy code
````

**Prompt 4** (the `/spec-pipeline` invocation; the argument string, verbatim, including the garbled pasted portions):

````
okay, great, few things that i want to change for the pr (want you to update the pr and not create a new one). 1)  resolve the comments on the pr./ 2) prompt needs a little bit of work on the pr. I want you to explain things in 6-8 sentences at least, and for the main prompts have a few sections of this legth (goal, instructions, objective, etc) 3) want to explain/change the architecture of this agent swarm a little bit,  and you can also propagate this information into the prompts. I want this architecture of this agent swarm to be simple and not too opinionated, and kind of like 'getting out of the way of the agents'. these are the changes that i want to make to the pr: when we start the runtime, i want there to be N agents that swarm with the same message/system prompt in a few paragraphs: "you are running in an agent swarm, you are running in this workspace, you have access to talk to other agents, you have these tools. ". this is the important STARTING point of the algorithm, the reason I want to set it up like this is because I want the agents to kind of figure out what they have to do during the run and talk to each other. I think that each agent getting a "mailbox" can stay in terms of messeging each other. then, I think that. i think that each agent should also get its own compaction tool, and I want to kind of remove the 'task board' that we have in the swarm and just kind of let the agents work this out. i think that also for the "main prompts" we should specify to the agent, through promptting, in 6-8 sentences each of the following ideas that we have implemented in the JevAgent inside of the sdk for "done checks", just try to bias the agents for being extremely throughout and making sure that the work is done. 4) i want to keep teh event log but I want to try to expand it so that a user can very easily "see into" the agent swarm, etc: Decisions the runtime already makes but never records. These need no new seam. Each is a branch in runtime.py that today leaves no trace.

- message_refused. The send path has three refusal branches: blank text, an unknown or self recipient, and a recipient that has failed. Each raises a tool error the model reads, so the stream only shows a tool_called for message with error status and no reason. The event carries the sender as agent, the attempted name as peer, and the reason as text. It separates "tried to reach a dead peer", which is a coordination failure, from an ordinary tool mistake.
- wake_refused. Both the send path and the turn end check the turn budget before waking an agent. When the budget is spent the message is queued and nobody wakes, and the only trace is a max_turns stop reason at the very end. Recording it at the moment it happens, with the un-woken agent, the sender as peer, and the message id, makes edge case EC-8 visible when it occurs rather than inferred afterwards.
- message_undelivered. When an agent fails its inbox is abandoned, and when the swarm ends max_turns the running agents still hold mail. Today a reader must diff message_sent against message_delivered to find those messages. Recording one event per orphaned message inside the fail path and the end check, with recipient, sender as peer, and message id, gives every sent message exactly one outcome. The rm_ended record, so the result invariant thatswarm_ended is last still holds.
- swarm_stopping. The stop reason is decided inside the end check, but swarm_ended is recorded only after every releagent's run has returned. Edge case EC-18 sa that gap and drop agents from the replies, andthe reader cannot see when the decision was made. An event recorded in the same block that sets the stop reason, with an empty agent and the reason, makes the gap measurable through elapsed time.
- agent_released. When a released agent's run returns, the runtime keeps its reply and does nothing else. There is no per-agent terminal event on the normal path, so an agent missing from the replies after a late cancel leaves no explanation. Recording it in that branch gives every agent one of three endings.                                  agent_cancelled. On a timeout every running out an agent_failed, so a timed-out run has noper-agent ending at all. The cancel branch already distinguishes the swarm's own cancel from a stray one by checking the task's cancel count and the decided stop reason. Recording the event in that branch before re-raising, with whetheagent was working or idle as text, completesagent_exited. The failure path currently folagent_failed: a model or SDK error, and a runthat returned early with its own stop reason such as max_iterations, max_tokens, tool_loop_limit or middleware_abort. The early-exit branch already extracts that stop reason into text. Splitting it into its own kind lets a reader tell a provider outage from an agent that hit its own loop budget without parsing a sentence.                             event below is one more override plus one record method on the runtime, which respects the non-goal of not touching the shared loop.

- model_called. The after_model_response hook hands the middleware the provider usage record, which exposes input, output and cached tokens plus a cost formula, and the running model call count. One event per model response, with the agent and the token counts as new integer fields, answers open question Q-5 about per-agent usage through the stream instead of a result field. It also shows how many rounds each turn took. It is the highest-volume candidate, which touches Q-8.
- model_error. The on_model_error hook receives the exception for every failed attempt, including ones a retry or a fallback later absorbs. Today only the final failure surfaces, as agent_failed. Recording the error type and text per attempt shows rate limiting and flakiness before an agent dies. The middleware must return continue so the loop's own retry decision stays untouched.                                                                                   history_trimmed. The trim middleware is firs the pipeline applies each transform to thecontext before the next middleware runs, so in before_model_call the turn middleware sees the post-trim history. A conversation only grows between calls, so a message count lower than the one seen at the previous call proves a trim. Edge case EC-26 warns that delivered messages can drop out of the model's view. This event says exactly when that happened, which is the key fact when an agenit.
- tool_result_truncated. The after_tool_call hook sees the raw result before the loop applies the swarm's own character cap, so comparing the output length with the constant is exact. The event carries the tool name and the omitted count. A wrong decision by that agent later may trace to a cut result. It could also be a flag on tool_called, which is open question Q-6 territory.

Workplace facts from the tools' own result metadata. Also derived in after_tool_call, from fields the tools already return.

- file_changed. The write_text success result carries the path, and patch_file carries the file path and a changed flag. The runtime can keep a last-writer map per path, updated in the same synchronous block, and record the path as text and the previous writer as peer when it was a di4 claims collisions are visible in tool_calledevents, but tool_called carries no path, so today they are not. Writes made through bash stay invisible, since bash is unsandboxed and reports no path.                                                                                        command_failed. The bash tool returns a succat finished, with the exit code only in metadata and on the last output line. A red test run is therefore a success-status tool_called today. Recording an event when the exit code is non-zero, or when the error metadata says timeout, is the one event that tells a reader the tests failed from the stream alone.

Run-level.                                                                                                                
- workplace_prepared. The workplace object can check whether the folder existed before its one mkdir call. Edge case EC-31 says a second run sees the previous run's files, and a reader of the events alone cannot tell whether the swarm started clean. Recording the path and a created-or-et needs prepare to return that fact to theruntime.

Not derivable without breaking a runtime rule

- message_read. Delivery appends a user message to the conversation. Nothing signals that the model used it, so only delivered is observable.
- Per-tool-call delivery. The loop has no seam between two tool calls of one response, per assumption A-1. Adding one changes the shared loop, which non-goal NG-8 forbids.
- swarm_stalled or heartbeat. Needs a timer, and the runtime forbids polling and sleeping. Stall detection belongs in the consumer of the stream, which can watch elapsed time between events.
- File changes through bash. No path metadata exists, and sandboxing is a stated limitation.

★ Insight ─────────────────────────────────────
The current event set is "exactly the state mae transition in the spec's lifecycle diagram.The additions above fall into two different classes with different guarantees. The runtime-decision events inherit the no-interleaving proof for free because they li exist. The hook-derived events are per-agentobservations with no cross-agent ordering claim beyond the sequence number, and they are where the volume lives: model_called and tool_result events scale with the agents' call rate, so a cap or a per-kind opt-in on the settings would land alongside them.
─────────────────────────────────────────────────. Also maybe things like agents created.
````

**Prompt 5** (the user's answers to the orchestrator's ten alignment questions; the questions are reproduced in §C "Clarifications and answers"):

````
1) yes, I want each agent to have the same system prompt, and in that system prompt include a section that lets them know about their environment (they are in an agent swarm, they can message other agents, they are working in a shared workspace, etc). 2) remove this. I want the messagin protocol to be very loose and non-restrictive, the agents should be able to message any agent anything.. 3) include the most important ones 4) okay thats fine ignore this. 5) think about some good prebuilt compaction tools that other providers/companies have created and see if you can attach this compaction  tool  to the agents. Compaction is very important and want to see if you can integrate from someone how has built it really good 6) forget this, keep the messaging tool specific to this runtime. 7) lib folder. 8) we can keep limits, but they should be extremely generous. if you are running an agent swarm you probable have the tokens to support the cost. thinking max agents 5,00, max tokens 10 billion, things of this scale. 9) this can be setting that user selects. 10) adopt full list that can be done deterministically through software and not through changing the runtime shape
````

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### What exists today (the baseline this run revises)

PR #1174 on `cerredz/Vidbyte-SDK` (draft, open, branch `feat/agent-swarm`, head `39ce8b20`, 63 commits over `origin/main` at merge-base `845a4d9b`) adds `AgentSwarm`. Its previous pipeline run lives at `docs/spec/agent-swarm/` (spec r5, request, test plan, review record, verify log, pr-body, pipeline state). The user read an explanation of that architecture in this conversation and then asked for the revisions below. The explanation that was given, condensed, so every agent shares the same picture:

- Each member is an ordinary `BaseAgent` running the shared linear loop in `vidbyte/agents/runtime.py` once for the whole swarm. The shared loop is untouched by the PR; the swarm attaches through three existing extension points plus one tool: `AgentSwarmMemberRuntime._after_tool_iteration` (mail between tool iterations), `AgentSwarmTurnMiddleware.review_finish` and `after_tool_call` (turn end, `tool_called` events), and `AgentSwarmMessageTool` (`message`).
- One `AgentSwarmRuntime` per `arun` owns all swarm state (inboxes, working, waiting futures, failed, turns, stop reason, replies) and mutates it only in blocks with no `await`, which is the whole concurrency argument. One `asyncio.TaskGroup` under `asyncio.timeout` holds one task per member.
- `AgentSwarmEvents` is an outbox: synchronous `record` numbers events; async `flush` delivers in order under a one-slot semaphore; a callback `Exception` is kept by type name and never stops the swarm.
- Tools per agent: `bash`, `grep`, `read_lines`, `write_text`, `patch_file` over the shared folder (`AgentSwarmTools`), plus `message`, optional `search_tool`, and the loop's `isDone`.
- Prompts: ten leaves under `vidbyte/prompts/prompts/agent_swarm/`; system prompt = member's own prompt + swarm prompt (name + peers, facts only) + the loop's agentic prompt.
- Constants: 2 to 100 agents, 500 turns default, 3,600 s default and one-week ceiling, 90,000-token history trim, 100,000-char tool-result cap.
- Eight event kinds (`agent_started`, `tool_called`, `message_sent`, `message_delivered`, `agent_idle`, `agent_woke`, `agent_failed`, `swarm_ended`); four stop reasons (`quiet`, `max_turns`, `timeout`, `failed`).

### The four open review comments on PR #1174 (verbatim, to be resolved by this run)

| Comment id | File:line (on `39ce8b20`) | The user's comment, verbatim | Decision reached in this conversation |
|---|---|---|---|
| 4318715506 | `vidbyte/agents/agent_swarm/settings.py:59` | `wrong file location for this dataclass, given agents.md in the repo` | Move `AgentSwarmSettings` to `vidbyte/lib/dataclasses/` ("7) lib folder."). |
| 4318721573 | `vidbyte/agents/agent_swarm/member.py:78` | `wrong location for this tool, should be at vidbyte/tools folder, and want you to turn it into a general tool for messaging agents between each other` | Superseded by the user in Prompt 5: "6) forget this, keep the messaging tool specific to this runtime." The tool stays swarm-specific; the thread is answered with this decision and resolved. |
| 4318728824 | `vidbyte/lib/constants/agent_swarm.py:19` | `dont want caps like this, user pays for the usage so let them define however many agents that they want` | Limits stay but become extremely generous (Prompt 5 answer 8): examples given are 500 agents and 10 billion tokens, "things of this scale". |
| 4318730679 | `vidbyte/lib/constants/agent_swarm.py:46` | `agent should also have a web-search tool` | Web search becomes a setting the user selects (Prompt 5 answer 9). |

Resolution means: a reply on each thread naming the decision and the fixing commit, and the thread marked resolved (GitHub review-thread resolution), done in the last stage, never by force-pushing history away.

### Key decisions

- **Update PR #1174 in place; no new PR.** All work lands on `feat/agent-swarm`. The last stage edits the existing PR's title and body (`gh pr edit`), it never opens a second PR. The user: "want you to update the pr and not create a new one".
- **Every agent gets the same system prompt.** Per-member role prompts go away. The one shared prompt is the "important STARTING point of the algorithm": it tells each agent it is in an agent swarm, which workspace it works in, that it can talk to the other agents, and which tools it has, "in a few paragraphs". The reason: "I want the agents to kind of figure out what they have to do during the run and talk to each other." Members still differ by name, and the orchestrator's default is that provider and model stay per member (the user confirmed only "same system prompt"; see Open questions).
- **The architecture stays simple and unopinionated, "getting out of the way of the agents".** No imposed coordination structure. The per-agent mailbox stays: "each agent getting a 'mailbox' can stay in terms of messeging each other."
- **Messaging is very loose and non-restrictive.** "the agents should be able to message any agent anything." The current design's recipient enum and three refusals (blank text, unknown/self recipient, failed recipient) are the opinionated parts to loosen; the spec author decides the minimum that still delivers (see Open questions).
- **Prompts explain things in 6–8 sentences at least**, and the main prompts have several sections of that length (the user named "goal, instructions, objective, etc"). The user's answer 1 adds an environment section ("they are in an agent swarm, they can message other agents, they are working in a shared workspace, etc").
- **Thoroughness bias via the JevAgent done-check ideas.** The main prompt specifies, "in 6-8 sentences each", the most important done-check ideas implemented in JevAgent (`vidbyte/lib/jev/done/`, 24 checks on `JevDoneCheck`), to "bias the agents for being extremely throughout and making sure that the work is done". The user chose "include the most important ones", not all 24. This supersedes the previous run's finding R-1 (which had removed all workflow guidance from the prompts): the user answered "remove this" to the question whether R-1 still stands.
- **Each agent gets its own compaction tool, integrated from the best prebuilt compaction available.** The user: "think about some good prebuilt compaction tools that other providers/companies have created and see if you can attach this compaction tool to the agents. Compaction is very important and want to see if you can integrate from someone how has built it really good". A research pass precedes the spec (see Constraints).
- **The message tool stays specific to this runtime** and is not generalized or moved ("forget this, keep the messaging tool specific to this runtime").
- **`AgentSwarmSettings` moves to the lib folder**, i.e. `vidbyte/lib/dataclasses/`.
- **Limits stay but are extremely generous.** "we can keep limits, but they should be extremely generous. if you are running an agent swarm you probable have the tokens to support the cost. thinking max agents 5,00, max tokens 10 billion, things of this scale." Read as: a maximum of 500 agents, a swarm-wide token budget on the order of 10 billion tokens, and the turn and time limits scaled to the same order. A token budget is a new limit the current PR does not have.
- **Web search is a user-selected setting.** When selected, every agent gets that web-search tool; when not selected, no web-search tool. (Orchestrator default from the alignment questions, not objected to: a missing key for the selected provider is refused when the settings are built, naming the field.)
- **The event log stays and is expanded** with every event in the user's list that "can be done deterministically through software and not through changing the runtime shape": the runtime-decision events (`message_refused`, `wake_refused`, `message_undelivered`, `swarm_stopping`, `agent_released`, `agent_cancelled`, `agent_exited` split from `agent_failed`), the hook-derived events (`model_called` with token counts, `model_error`, `history_trimmed`, `tool_result_truncated`), the workplace facts (`file_changed`, `command_failed`), the run-level `workplace_prepared`, and "things like agents created" (`agent_created`). The four "not derivable" items (`message_read`, per-tool-call delivery, `swarm_stalled`/heartbeat, file changes through bash) are out. The purpose: "a user can very easily 'see into' the agent swarm".
- **The "task board" item is dropped.** No task board exists in the PR; the user said "okay thats fine ignore this."

### Rejected alternatives

- A general, cross-runtime agent-messaging tool under `vidbyte/tools/` (the original review comment 4318721573) — rejected by the user in Prompt 5: keep it swarm-specific.
- `vidbyte/agents/settings/agent_swarm.py` as the settings home — rejected: "lib folder".
- Removing limits entirely — rejected: "we can keep limits, but they should be extremely generous."
- Per-member role prompts (builder/tester) — rejected: same prompt for every agent; agents work out roles by talking.
- All 24 done checks as prompt sections — rejected: "include the most important ones".
- Prompts that state facts only with no workflow guidance (the previous run's R-1) — reversed: thoroughness guidance is wanted.

### Constraints and assumptions

- The shared agent loop (`vidbyte/agents/runtime.py`) stays untouched; every new event comes from an existing seam (a runtime branch, a middleware hook, a tool's result metadata). The user's words: "deterministically through software and not through changing the runtime shape".
- The previous run's artifacts under `docs/spec/agent-swarm/` are the baseline; this run's artifacts live under `docs/spec/agent-swarm-v2/`. Subagents may read `docs/spec/agent-swarm/spec.md` (r5) when the orchestrator names it; `docs/` is otherwise opaque per AGENTS.md.
- The existing 171-test feature pack under `tests/features/agent_swarm/` is the previous contract. This run's test author owns it: tests that encode decisions this run reverses (per-member prompts, the 100-agent cap, the recipient enum, the refusal set, the eight-kind event set) must be rewritten by the test author at S2, not by the implementer.
- Offline scripted tests only, as in the previous run (`ScriptedSwarm` in `tests/features/agent_swarm/agent_swarm_fixtures.py` replaces only `BaseAgent._runner_for_model`). No live provider calls in the pipeline.
- A research pass on prebuilt compaction (Anthropic, OpenAI, Google, LangChain/LangGraph, Letta and others, plus the SDK's own `MessageHistoryCompactionMiddleware`, `ContextCompactionTool`, `CompactCodexThreadTool`) runs in S0 and is recorded at `docs/spec/agent-swarm-v2/context/compaction-research.md`; the spec author designs the compaction tool from it.
- Lint facts inherited from the previous PR body: TID251/S039 bans `asyncio.Lock` (a one-slot `asyncio.Semaphore` is the mutex); C012 accepts only `ModelProvider(...)` as proof of a valid provider; mypy rejects `Callable` as an `isinstance` target; the prompts header count in `vidbyte/lib/enums/prompts.py` must match; `contracts/sdk-public-api.json` is regenerated with `python scripts/generate-sdk-public-api.py`.
- CI on this repo runs only by manual dispatch (`gh workflow run`), so `gh pr checks` stays empty; results are read with `gh run list --branch feat/agent-swarm`. The Static policy workflow (semgrep) is dispatched separately.
- The 6–8 sentence rule applies to the system prompt sections and the tool and parameter descriptions; one-line refusals and the inbox labels stay short (orchestrator assumption stated to the user, not objected to).
- The user's event list contains garbled text from a paste (for example "The rm_ended record, so the result invariant thatswarm_ended is last still holds."); the intended meaning of each item is recoverable from its first sentences and is restated in "Key decisions".

### Clarifications and answers

- Q1: Identical agents or roles? Should the per-member `system_prompt` go away entirely, or stay as an optional extra? — A: "yes, I want each agent to have the same system prompt, and in that system prompt include a section that lets them know about their environment (they are in an agent swarm, they can message other agents, they are working in a shared workspace, etc)."
- Q2: The thoroughness guidance reverses the previous run's R-1 ruling (prompts state facts only). Confirm it supersedes R-1, and whether it lives in the system prompt or as a turn-end reminder. — A: "remove this. I want the messagin protocol to be very loose and non-restrictive, the agents should be able to message any agent anything.." (Read as: R-1's restriction is removed, and, separately, the messaging protocol must be loose.) Default applied for the unanswered half: the guidance lives in the shared system prompt as its own sections.
- Q3: Which of the 24 done-check ideas? (The orchestrator proposed a curated eight: multi_part, claims, completion_evidence, problems_resolved, faithful_scope, negative_coverage, self_review, can_simplify.) — A: "include the most important ones"
- Q4: What is the "task board"? None was found in the PR. — A: "okay thats fine ignore this."
- Q5: Compaction tool: use the SDK's `ContextCompactionTool` as-is, and keep the automatic 90,000-token trim as a backstop? — A: "think about some good prebuilt compaction tools that other providers/companies have created and see if you can attach this compaction  tool  to the agents. Compaction is very important and want to see if you can integrate from someone how has built it really good"
- Q6: A general messaging tool under `vidbyte/tools/` over a mailbox Protocol? — A: "forget this, keep the messaging tool specific to this runtime."
- Q7: Settings location: `vidbyte/agents/settings/agent_swarm.py` or `vidbyte/lib/dataclasses/agent_swarm.py`? — A: "lib folder."
- Q8: Caps: drop the 100-agent maximum; drop the one-week ceiling; allow `None` for no limit? — A: "we can keep limits, but they should be extremely generous. if you are running an agent swarm you probable have the tokens to support the cost. thinking max agents 5,00, max tokens 10 billion, things of this scale."
- Q9: Built-in web search: which of the eight priced providers is the default, and what happens when its key is missing? — A: "this can be setting that user selects." Default applied for the unanswered half: no provider selected means no web-search tool; a selected provider with no key is refused at settings time, naming the field.
- Q10: Adopt the full event list; always-on with no cap or per-kind opt-in; PR mechanics (existing branch, new spec folder, resolve the four threads, edit #1174's body). — A: "adopt full list that can be done deterministically through software and not through changing the runtime shape". Defaults applied for the unanswered parts: always-on, no cap; new integer token fields and a path field on the event record; PR mechanics as described; offline scripted tests only.

### Terminology

- **Swarm** — one `AgentSwarm.arun(goal)` run: N agents, one shared folder, mailboxes, one event log.
- **Member / agent** — one `BaseAgent` in the swarm, named; runs one long conversation for the whole swarm.
- **Turn** — one span from a model call until the model stops calling tools (a plain reply or `isDone`); turns are what the turn budget counts.
- **Mailbox / inbox** — the per-agent queue of `message_sent` events not yet delivered.
- **Idle / parked** — an agent whose turn ended with no mail, waiting on its wake future.
- **Compaction** — replacing part of an agent's conversation with a shorter representation (summary, cleared tool results, provider-side compaction) so a long run fits the model's context.
- **Done checks** — the JevAgent ideas in `vidbyte/lib/jev/done/` that judge whether work is really finished (multi-part deliverables, claims backed by evidence, problems resolved, faithful scope, negative coverage, self-review, simplification, and others).
- **Deterministic event** — an event recorded from a branch or hook that already exists, with no timer, no polling, and no change to the shared loop.

### Implementation hints

- Product files on the branch (all at `39ce8b20`): `vidbyte/agents/agent_swarm/{swarm,settings,runtime,events,workplace,member,__init__}.py` and `README.md`; `vidbyte/middleware/builtins/agent_swarm_turn.py`; `vidbyte/tools/toolsets/agent_swarm.py`; `vidbyte/lib/{dataclasses,enums,constants}/agent_swarm.py`; `vidbyte/prompts/prompts/agent_swarm/` (`agent_swarm.json` + 10 leaves); edits in `vidbyte/lib/enums/{agent_runtime,prompts,__init__}.py`, `vidbyte/lib/registries/runtimes.py`, `vidbyte/agents/base.py`, `vidbyte/tools/toolsets/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `contracts/sdk-public-api.json`, `vidbyte/agents/README.md`, `vidbyte/tools/README.md`, `vidbyte/prompts/README.md`, `REPO_MAP.md`.
- Tests on the branch: `tests/features/agent_swarm/` (fixtures, acceptance 8, contract 73, lifecycle 26, messaging 14, property 36, workplace 14; `FEATURE.md`, `README.md`).
- The runtime's state changes happen only in `post_message`, `end_turn`, `_drain`, `_fail`, `_end_check` (plus the stray-cancel branch of `_run_member`); each new runtime-decision event is recorded in the same synchronous block as the branch it describes.
- Middleware hooks available on `AgentMiddleware` (`vidbyte/middleware/base.py`): `before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `on_model_error`, `before_tool_call`, `after_tool_call`, `after_iteration`, `after_run`, `review_finish`. The hook-derived events use `after_model_response` (usage record), `on_model_error`, `before_model_call` (post-trim history for `history_trimmed`), and `after_tool_call` (raw result length, write/patch/bash result metadata).
- Done-check source material: `vidbyte/lib/jev/done/*.py` (one file per check, 24 checks) and the prose in `vidbyte/agents/jev/README.md` (lines 30–51 describe each check); enum `JevDoneCheck` in `vidbyte/lib/enums/jev.py`.
- Compaction pieces already in the SDK: `MessageHistoryCompactionMiddleware` (`vidbyte/middleware`, used today as `trim_with_provider_boundaries(max_tokens=90_000)`), `ContextCompactionTool` at `vidbyte/tools/builtins/context/compaction.py`, `CompactCodexThreadTool` in `vidbyte/tools/builtins/codex/thread_helpers.py`.
- Web-search tools already in the SDK: `BraveSearchTool`, `BrowserbaseSearchTool`, `ExaSearchTool`, `TavilySearchTool`, `LinkupSearchTool`, `ParallelSearchTool`, `OpenAlexSearchTool`, `SemanticScholarSearchTool` in `vidbyte/tools/builtins/operations/search.py` (each a `PricedOperationTool` with its own key).
- Validation helpers: `RecordFieldValidator` / `RecordFieldConverter` in `vidbyte/lib/dataclasses/validation.py`; key matching: `ProviderKeyMatcher` in `vidbyte/lib/registries/provider_keys.py`.
- `vidbyte/lib/` must not import `vidbyte.tools`; today `settings.py` imports `BaseTool` (for `search_tool`) and `IS_DONE_TOOL_NAME` from `vidbyte.tools._internal`. Moving the settings to `vidbyte/lib/dataclasses/` means those fields change shape (the web-search provider becomes an enum value, the reserved-name check moves or goes).
- Do not touch: `vidbyte/agents/runtime.py` (the shared loop), the actor runtime, InfiniteMemoryAgent, JevAgent, the shared validators.
- Previous-run niche facts worth keeping: the prompts README entry and the REPO_MAP entry sit in alphabetical order; `asyncio.Semaphore()` not `asyncio.Lock`; `ModelProvider(value)` for provider validation; the `agent_started` events are delivered inside the time limit; `post_message` accepts `object` for recipient and text and refuses in its body.

### Open questions

- The member record after the change: does `AgentSwarmMember` keep `name`, `provider`, `model_name` with no `system_prompt`, or do settings take a count plus one provider/model for all? Default: keep name/provider/model per member, drop `system_prompt`.
- The minimal refusal set for "loose" messaging: is a message to a name that is not in the swarm still refused (nobody to deliver to)? Is a self-message allowed? Is a broadcast ("all") supported? Default: refuse only an address that names nobody; allow everything else; spec author decides broadcast as a Q-n with a stated default.
- Which done checks are "the most important" for open-ended swarm work; the orchestrator's starting list is eight (multi_part, claims, completion_evidence, problems_resolved, faithful_scope, negative_coverage, self_review, can_simplify); the spec author may swap with a reason.
- Which compaction integration, chosen from the research file; whether the automatic trim stays as a backstop beside the tool.
- The exact generous limits (agent maximum, token budget, turn and time defaults and ceilings) at the stated scale, and where the swarm-wide token budget is enforced (the usage seen in `after_model_response`) and its stop reason name.
- Event volume: always-on with no cap is the default; a per-kind filter in settings is an optional Q-n with default "not built".
- Whether `AgentSwarmEvent` gains typed integer fields (`input_tokens`, `output_tokens`, `cached_tokens`, `model_calls`) and a `path` field, versus packing them into `text`.
- Whether the previous spec's `search_tool: BaseTool | None` field is removed outright in favor of the web-search provider setting (needed for the lib move).

## D. Weighted words

- "want you to update the pr and not create a new one" — Prompt 4
- "I want you to explain things in 6-8 sentences at least" — Prompt 4
- "I want this architecture of this agent swarm to be simple and not too opinionated, and kind of like 'getting out of the way of the agents'." — Prompt 4
- "this is the important STARTING point of the algorithm" — Prompt 4
- "just try to bias the agents for being extremely throughout and making sure that the work is done" — Prompt 4
- "I want to try to expand it so that a user can very easily 'see into' the agent swarm" — Prompt 4
- "Decisions the runtime already makes but never records." — Prompt 4
- "gives every sent message exactly one outcome" — Prompt 4
- "so the result invariant thatswarm_ended is last still holds" — Prompt 4
- "Recording it in that branch gives every agent one of three endings." — Prompt 4
- "The middleware must return continue so the loop's own retry decision stays untouched." — Prompt 4
- "which respects the non-goal of not touching the shared loop" — Prompt 4
- "This event says exactly when that happened" — Prompt 4
- "comparing the output length with the constant is exact" — Prompt 4
- "Needs a timer, and the runtime forbids polling and sleeping." — Prompt 4
- "yes, I want each agent to have the same system prompt" — Prompt 5
- "I want the messagin protocol to be very loose and non-restrictive, the agents should be able to message any agent anything.." — Prompt 5
- "Compaction is very important" — Prompt 5
- "keep the messaging tool specific to this runtime" — Prompt 5
- "we can keep limits, but they should be extremely generous" — Prompt 5
- "adopt full list that can be done deterministically through software and not through changing the runtime shape" — Prompt 5
