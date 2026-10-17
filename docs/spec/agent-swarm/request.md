---
slug: agent-swarm
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-16 16:02
flags: none
---

# Request: AgentSwarm — a minimal runtime where user-defined agents run their tools and message each other

## A. Every user prompt in this conversation, verbatim and in order

_Earlier prompts in the same session were about an unrelated research survey (a 195-post checklist of how practitioners build with coding agents, and an 85-entry "Agent Builder Field Guide" distilled from it). They are omitted because they are not about this feature; the research entries this feature leans on are quoted in §C "Implementation hints" by their reference IDs (R02, R03, R05, R17, L03, L09, F13). The prompts below are every prompt about this feature, verbatim._

**Prompt 1** (the feature idea; asked for an architecture critique):

```text
great, I just came up with an idea based on all this researcch, something to add in either the vidbyte-sdk/ or vidbyte-cli/ repo, and it branches off the idea of the InfiniteMemoryAgent agent that we have in the vidbyte-sdk/. I want to create a variation of this agent  where this agent but the main goal is to create an "agent swarm". One of the log-term horizon research found was that the team of agents kind of just figured out how to communicate effectively and developed their own strategies with peolpe. Also, i think that setting this up is really valuable data because if you can setup agent swarms in a way that are reliable then I think this is valuable data, but that is besides the point. So, I want to build an "AgentSwarm" runtime. Some architectural decisions that I want to make are 1) all agents should again have minimal tools: bash, grep, write, patch, web search (fogetting 2-3 main ones that claude code has), and then also a MESSAGE agent tool 2) i want the agents to have a shared workspace (help me decide if I should make github the actual shared workspace, or just the file system), I think that for each "agent swarm" giving them their own github is very powerful. 3) dont want to influence the same biases as the InfiniteMemoryAgent, want to tell all the agents that they are working in an agent swarm, they have the ability to edit files and communicate with other agents. 4) think that i  want to create a "backlog" of issues/items  when the agents run into something that they think is important to complete.


what do you think about this, what are we missing, what can we add to this architecture, is there any research above that is applicable to this arch?
```

**Prompt 2** (after the critique):

```text
great, lets start simple, what does the psuedocode of this "agent swarm" look like?
```

**Prompt 3** (the `/spec-pipeline` invocation; this is the build request):

```text
Lets forget the backlog for now. Right now i just want you to setup the ability for users to run an "agent swarm" where the architecture is very minimal inside of the vidbyte-sdk/. I want you to decompose the AgentSwarm into different classes that have different roles (AgentSwarmTools, AgentSwarmSettings, AgentSwarmRuntime, AgentSwarmEvents (events that happen during the agent swarm), AgentSwarmWorkplace), and what I simply want you to do is to setup an envrionment that has multiple agents running that the user defines that can run their tools and message each other,  lets start off simple. If you have any clarifying questions before the run feel  free to ask me (try to keep questions to 5)
```

**Prompt 4** (the user's answers to four clarifying questions, as recorded by the tool):

```text
"What should the AgentSwarmWorkplace be in this first version?"="One shared folder (Recommended)", "How long does an agent live, and when does the swarm end?"="Stay alive until quiet (Recommended)", "How does the user give the swarm its work?"="Shared goal + per-agent prompts (Recommended)", "How should AgentSwarmEvents reach the user?"="Callback + list on result (Recommended)"
```

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### Key decisions

- **Build it in `vidbyte-sdk`, on `origin/main`.** Prompt 3 says "inside of the vidbyte-sdk/". *Orchestrator correction at S0 (scout evidence, code-map.md §4 item 1):* InfiniteMemoryAgent, the agent this "branches off", is **merged on main** as `2c84049c` (#1084, 2026-10-16 15:45). An earlier note here said it was unmerged; that was stale. Main's `vidbyte/agents/infinite/` is therefore a legitimate code precedent for the package shape: runtime subclass, toolset, settings, lib records, enums, constants, prompt family and feature pack. The user's rule still applies to its **prompt and roles**: "dont want to influence the same biases as the InfiniteMemoryAgent". The follow-up branches (`feat/infinite-memory-events` #1159, `feat/infinite-memory-prompts`) are still unmerged and off-limits.
- **Five classes with exactly these names and roles** (Prompt 3): `AgentSwarmTools`, `AgentSwarmSettings`, `AgentSwarmRuntime`, `AgentSwarmEvents` ("events that happen during the agent swarm"), `AgentSwarmWorkplace`. The user asked for a decomposition by role. Whether a thin public entry class (for example `AgentSwarm`) sits on top is for the spec author to decide (see Open questions).
- **Workplace = one shared folder.** Every agent's file and shell tools are rooted in the same directory. The clarifying option's wording, which the user picked: "Every agent's tools are rooted in the same directory. Simplest; agents must coordinate edits through messages (research shows concurrent edits can collide, which is itself useful data). Git per agent can come later."
- **Lifecycle = stay alive until quiet.** The option's wording: "An agent that ends its turn goes idle; a new message wakes it. The swarm ends when every agent is idle with an empty inbox, or a max-turns / time limit is hit."
- **Task input = shared goal + per-agent prompts.** The option's wording: "swarm.arun("goal") sends the same goal to every agent; each agent's own system prompt (defined by the user) shapes its part."
- **Events = callback + list on result.** The option's wording: "An optional on_event callback (the pattern MultiAgent already uses) fires per event, and the result carries the full ordered tuple of events."
- **The agents are user-defined** (Prompt 3: "multiple agents running that the user defines"). The user chooses how many agents there are, their names, their models and their system prompts.
- **Minimal tools per agent** (Prompt 1: "all agents should again have minimal tools: bash, grep, write, patch, web search ... and then also a MESSAGE agent tool"). Before the questions were asked, the user was told the defaults would be: bash, grep, read, write and patch, all rooted in the workplace, plus `message`. Read was included because the user noted they were "fogetting 2-3 main ones that claude code has". Web search is included only when the user passes a search tool, because every search provider needs an API key. The user did not object.
- **The prompt tells agents they are in a swarm, and nothing more opinionated** (Prompt 1: "dont want to influence the same biases as the InfiniteMemoryAgent, want to tell all the agents that they are working in an agent swarm, they have the ability to edit files and communicate with other agents"). No root/generator/verifier roles and no "context is your scarcest resource" framing. The swarm framing goes alongside the user's own per-agent system prompt.
- **Messages never block the sender.** An agent that wants an answer ends its turn (goes idle) and is woken when the reply arrives. A blocking wait could deadlock two agents waiting on each other. This was in the critique and pseudocode the user accepted with "great".
- **Messages reach a busy agent between its tool calls, appended as a new user turn** (never as a system-prompt rewrite; see R02 below). They reach an idle agent by waking it. This also comes from the accepted pseudocode.

### Rejected alternatives

- **The backlog** (Prompt 1, item 4). Prompt 3 says "Lets forget the backlog for now." There is no backlog tool, store or event.
- **GitHub as the shared workspace, or a git clone per agent with a shared trunk.** The user chose "One shared folder". There is no git machinery, no GitHub, no tokens and no pushes.
- **"Shared folder + private subfolder".** Not chosen.
- **"Each agent runs once"** (an agent that has finished cannot be woken, and late messages to it are dropped). Not chosen. Agents stay alive until the swarm is quiet.
- **"Per-agent starting tasks" and "Goal to one entry agent".** Not chosen. Every agent gets the same goal.
- **"List on result only" and "Callback + JSONL file + list".** Not chosen. There is no events file on disk.
- **Things the earlier critique and pseudocode proposed that the build request did not ask for:**
  - an external oracle or "done" check run by the runtime;
  - file-area claims or locks;
  - a broadcast allowance and outbound message rate limits;
  - a `"human"` message recipient and a human inbox file;
  - a `web_fetch` tool;
  - a dollar budget (`max_usd`);
  - a known-good ("last green") ref;
  - run journals and resume.

  Under the pipeline's scope rule these are **not built**. Any of them may appear only as an optional `Q-n` with default **no**, or as a stated limitation.
- **A CLI command for running a swarm.** The SDK owner removed CLI commands from the SDK on 2026-10-10 (`vidbyte-sdk coding run` was deleted right after merging #747). Never add or offer SDK CLI commands.

### Constraints and assumptions

- Placement and style follow `AGENTS.md` and `REPO_MAP.md`:
  - dataclasses go in `vidbyte/lib/dataclasses/<domain>.py`;
  - enums go in `vidbyte/lib/enums/<domain>.py` and are exported;
  - settings go where `REPO_MAP.md` says agent settings live;
  - `vidbyte/lib/` never imports a higher layer;
  - call chains are one level deep;
  - main functions are narrated in plain English;
  - core inputs and outputs are validated frozen dataclasses;
  - files stay well under 1,000 lines.

  The scout confirms these against the live `AGENTS.md`.
- **Deterministic limits are enforced in code, not stated in prompts.** This is the rule in #1084's README, and the critique repeated it. The max-turns limit and the time limit are runtime checks, not prompt text.
- **"Start simple" is a hard constraint.** Only the five roles and the four answers above. The smallest public surface that lets a user define N agents, give them a goal and a folder, run them, and get events back.
- **Tests must not call real model APIs.** They use the SDK's existing fake or scripted model-client test patterns; the scout locates them. Any live-model check is a manual QA item, not a test.
- **`docs/` is opaque in this repo**, except for `docs/spec/agent-swarm/` files that a briefing names.

### Clarifications and answers

- Q: "What should the AgentSwarmWorkplace be in this first version?" — A: "One shared folder (Recommended)"
- Q: "How long does an agent live, and when does the swarm end?" — A: "Stay alive until quiet (Recommended)"
- Q: "How does the user give the swarm its work?" — A: "Shared goal + per-agent prompts (Recommended)"
- Q: "How should AgentSwarmEvents reach the user?" — A: "Callback + list on result (Recommended)"
- Prompt 1 asked "help me decide if I should make github the actual shared workspace, or just the file system". The critique recommended starting with local files and keeping GitHub off the hot path. The user then chose "One shared folder".

### Terminology

- **swarm** — one run in which N user-defined agents work concurrently in one workplace toward one shared goal and can message each other.
- **agent (swarm member)** — a user-defined participant: a unique name, a model, the user's system prompt, and the swarm's tools. Each one runs an ordinary SDK tool loop.
- **workplace** — the single shared directory that every agent's bash, grep, read, write and patch tools are rooted in (`AgentSwarmWorkplace`).
- **message** — text one agent sends to another named agent (whether "all agents" is a valid recipient is an open question) through the `message` tool. It is delivered to the recipient's inbox and never blocks the sender.
- **inbox** — the per-agent queue of messages that have not been delivered yet.
- **idle** — an agent whose tool loop has ended its turn (it replied without a tool call) and that is waiting for a message.
- **wake** — an idle agent receiving a message and starting a new turn with that message as input.
- **quiet** — every agent is idle and every inbox is empty. The swarm ends.
- **event** — one record of something that happened during the swarm, such as agent started, tool called, message sent, message delivered, agent idle, agent woke, agent failed, or swarm ended (`AgentSwarmEvents`). Events go to the optional `on_event` callback and to the ordered tuple on the result.
- **goal** — the one task string passed to `swarm.arun("goal")` and sent to every agent.

### Implementation hints

These were noted while reading the SDK earlier. The scout re-verifies each one; none is a decision.

- **The seam for mid-loop delivery.** `AgentRuntime._after_tool_iteration(state, messages)` in `vidbyte/agents/runtime.py` (around line 925) is called after `middleware.after_iteration`. Its docstring says it "may append to messages, and may replace self.tools". JevRuntime and InfiniteMemoryRuntime (#1084) already use it. The pseudocode drained the agent's inbox there and appended `{"role": "user", "content": render_inbox(batch)}`.
- **An actor runtime already exists on main** (`vidbyte/agents/runtimes/actor/`):
  - `BaseActorRuntime` with `spawn`, `send`, `mark_busy`/`mark_idle`, `_check_quiescence` and `fail`;
  - `ActorInbox` (an `asyncio.Queue`);
  - `ActorMessage(message_id, sender, recipient, content, parent_task_id, state)`;
  - point-to-point and broadcast runtimes;
  - #963: quiescence waits for busy actors, and a failed actor fails the run;
  - #973: `max_loop`.

  Its actors are reactive: one model call per message, and the reply goes back to the sender automatically. So it cannot drive proactive agents with tools as it stands. Its inbox, quiescence and failure ideas, or its classes, may be reusable. That is for the spec author to judge from the code.
- **The on_event precedent.** `vidbyte/agents/multi/agent.py` takes `on_event: MultiAgentEventCallback | None`. BaseAgent has no streaming API.
- **Existing tools to reuse instead of writing new ones:**
  - `vidbyte/tools/builtins/bash.py`;
  - `GrepTool` (and `GlobTool`) in the code-search tools;
  - `ReadLinesTool`, `ReadTextTool`, `WriteTextTool` and `ListDirTool` in `vidbyte/tools/filesystem/`;
  - `PatchTool` in `vidbyte/tools/editing/patch.py`, which replaces one exact block;
  - `ParadigmMinimalToolset` in `vidbyte/tools/toolsets/paradigm_minimal.py`, built with `FileSystemToolConfig(root, allow_write)`, which may already be most of `AgentSwarmTools`;
  - the operations search tools (Brave, Exa, Tavily), for the optional search tool.
- **Research behind the hints** (Agent Builder Field Guide, compiled 2026-10-16 from verified practitioner posts):
  - **R02** (Manus): keep a stable prompt prefix and append-only history, and never edit earlier turns, because that breaks the KV cache. This is why messages are appended as new user turns and not written into the system prompt.
  - **R03** (Zechner's Pi agent): four core tools are enough, and tool schemas cost context. This is why the toolset stays minimal.
  - **R05** (Ronacher): newer models invent keys inside nested edit schemas, so prefer flat old/new edit shapes. `PatchTool`'s flat shape fits.
  - **R17** (DoorDash): agents sharing one folder without isolation hit races and corrupted diffs. With one shared folder this is a known limitation the user accepted ("concurrent edits can collide, which is itself useful data"), not something to engineer around.
  - **L03** (Cursor): flat swarms that coordinate by locking files slowed down, and clear ownership worked. This is context for the prompt wording. The prompt does not prescribe roles.
  - **L09** (Thoughtworks): agents coordinated through an accidental blackboard. Give coordination its own channel, separate from the files. That is the `message` tool.
  - **F13**: bugs live in the seams between agents. This is context only.
- **Things not to touch:**
  - InfiniteMemoryAgent's behaviour on main (reading and copying its patterns is fine), and its unmerged follow-up branches;
  - `vidbyte/agents/runtimes/actor/` behaviour for its existing users (reuse is fine, but changing its semantics is not);
  - anything under `docs/` other than `docs/spec/agent-swarm/`.

### Open questions

For the spec author to resolve as A- or Q-items:

- **Placement.** Where the swarm package lives (for example `vidbyte/agents/swarm/`), per `REPO_MAP.md`. Where its dataclasses and enums go. Whether it registers anywhere, such as a runtimes registry, the public `vidbyte/__init__.py` exports, or `contracts/sdk-public-api.json`.
- **How a user defines one agent.** A small validated dataclass (name, model, system prompt, optional extra tools), or an existing SDK agent object.
- **The public entry point.** Whether there is a thin `AgentSwarm` facade with `arun(goal)` over `AgentSwarmRuntime`, or the user calls `AgentSwarmRuntime` directly. What the result type contains, for example per-agent final text, the events tuple, the stop reason and usage.
- **Message addressing.** Single recipient only, a list, or also "all". What happens on an unknown recipient (refused with the valid names listed). Whether an agent may message itself. Whether there is a message-length cap enforced in code.
- **Limits.** Whether "max-turns" counts per agent or for the whole swarm. The default values. The time-limit unit and default. What the swarm returns when a limit stops it (a stop reason on the result, not an exception).
- **Failure semantics.** One agent's model or tool error: does it fail the swarm (the actor runtime's #963 behaviour) or only that agent?
- **Workplace lifecycle.** Whether the workplace is a user-given existing path or a new temp directory. Whether it is created if missing. Whether it is cleaned up afterwards (default: never delete user files).
- **The search tool.** Exactly how a user opts in (a settings field that takes a search tool instance, or extra tools per agent).
- **Event kinds.** The exact list and payload of each event. Whether tool calls are events (they are useful data, and the user said this data is valuable, but "start simple").

## D. Weighted words

- "all agents should again have minimal tools: bash, grep, write, patch, web search (fogetting 2-3 main ones that claude code has), and then also a MESSAGE agent tool" — Prompt 1
- "i want the agents to have a shared workspace" — Prompt 1
- "dont want to influence the same biases as the InfiniteMemoryAgent, want to tell all the agents that they are working in an agent swarm, they have the ability to edit files and communicate with other agents" — Prompt 1
- "if you can setup agent swarms in a way that are reliable then I think this is valuable data" — Prompt 1
- "great, lets start simple" — Prompt 2
- "Lets forget the backlog for now." — Prompt 3
- "setup the ability for users to run an "agent swarm" where the architecture is very minimal inside of the vidbyte-sdk/" — Prompt 3
- "decompose the AgentSwarm into different classes that have different roles (AgentSwarmTools, AgentSwarmSettings, AgentSwarmRuntime, AgentSwarmEvents (events that happen during the agent swarm), AgentSwarmWorkplace)" — Prompt 3
- "what I simply want you to do is to setup an envrionment that has multiple agents running that the user defines that can run their tools and message each other" — Prompt 3
- "lets start off simple" — Prompt 3
- "The swarm ends when every agent is idle with an empty inbox, or a max-turns / time limit is hit." — Prompt 4 (the chosen option's text)
- "swarm.arun("goal") sends the same goal to every agent" — Prompt 4 (the chosen option's text)
- "the result carries the full ordered tuple of events" — Prompt 4 (the chosen option's text)
