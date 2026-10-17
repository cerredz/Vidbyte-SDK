---
slug: browser-agent
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-16 (session d4409101; captured by the main agent for the orchestrator subagent)
flags: none
---

# Request: BrowserAgent — a JevAgent-shaped agent and runtime for long-running browser tasks

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (start of conversation):
````
what do you think is a good architecture for "a long-run
  agent that uses the browser" where we can very easily influence the behavior  of what it actually does on the web through a prompt (ex: prompt it to research to 8 hours and at any opoints not duplicate queries orpages visited, going off o teh web and finding 1,000 vc applications to apply to, going ton the web and finding 100 resaerch papers for something, etc. These are teh, generall speaking, tasks that I am thinking about). can you help me thinnk of an architecture that is well suited for this problem space. is it claude code with a simply browser + memory tool/s, is it our new InfiniteMemoryAgent inside of the vidbyte-sdk/, is it claude codex/codex with hookks, is it a new custom-made runtime shaped to the task we are trying to implement (ex: subagents for all browser actions, custom database tool for memory, etc). Can you weight in on this question for me, consider mutliple approaches that exist and converge on what you think is best?
````

**Prompt 2**:
````
I dont thinkk that you explained to me an actual answer,  can you explain to me one simply. Also, think about generalized browser interactions. ANd I dont want you to overcomplex things, here is what I am mainly trying to get at: compared to a standard linear agent loop there are a few attributes of long-running browser-based agent sessions where they differ slightly:

1) they tend to be alot more context/token heavy for several reasons. Screenshots/images are alot of tokens,  each page we might need to use 25+ actions with tools compared to something like just 1 bash call for a coding agent

2) they tend to be alot of repeatable actions. 

3) there needs to be a way to dynamically update the "main memory" of what we are trying to accomplish given the fact of the token-heavy use of the browser agent while also still preserving the main goal

i am not looking for anything super complex, just small architectural tweaks to the main linear agent loop that helps fit these types of tasks, generally speaking, for long-term browser-based tasks.

am thinking along the lines of a "minimal main orchestrator agent that uses subagents with browser tools for specific actions (clicking, searching, typing, etc) with a memory patch tool and a "/goal" setup that rechecks the original goal/done critiera with original prompt". This is just a thought though, any ways to improve/consider things that I am missing?
````

**Prompt 3** (the invoking prompt, sent as `/goal` arguments):
````
/spec-pipeline Okay, here is what i want to do. I want you to  launch a spec pipeline subagent that builds a "BrowserAgent" that discusses the main talking points of the architecture that we specified in the vidbyte-sdk/vidbyte/agents/browser. I want you to focus on the architecture of the runtime, and for the agent try to model it like out JevAgent in the repo (decompose the class logic, have a main BrowserAgent class that uses BrowserAgentRuntime, BrowserAgentSettings, BrowserAgentTools, BrowserAgentEvents, BrowserAgentUsage, BrowserAgentresponse etc subclasses). try not to overengineer each class, alot  of these  can be implemented in only a few hundred lines of code. then, the user for the browser agent, in its settings, should be able to "define' the actual  browser mcp servers that they want to use (playwright, browserbase, firecrawl, etc. there are alot and I want users to be able to import these, by nature they should also we required to upload their api keys into the agent settings), the browser tools themselves could even have more than 1 param (ex: browser_event_tools=playwright, browser_search_tools=firewcrawl). use judgement to decide best way to implement something like this.
````

## B. Handoff block and decision ledger (verbatim, if present)

No `## HANDOFF` block was produced. The architecture the user accepted is the assistant's second answer (to Prompt 2). Its decision ledger, verbatim:

````
**Re-entry · long-run browser agent loop**
Decided: linear loop plus five tweaks · delegation unit is a page-level episode with action and screenshot caps · browser session is the durable state, worker contexts are disposable · keep only the latest one or two observations, batch actions per turn · recipes replay successful action sequences without a model · goal card with immutable prompt and done criteria, patch tool for plan, progress, blockers · recheck in a fresh context on a cheap model every K episodes and on done claims · orchestrator compaction and resume are the same rebuild
Open: K for the recheck and the action cap per episode, measure on 20 pages first
````

The architecture talking points from that answer, verbatim (this is "the architecture that we specified" in Prompt 3):

````
Your sketch is right in shape. The one correction is granularity. The worker is not "a subagent per click". It is a subagent per **episode**: one page or one form with a clear done check. The worker runs its 25 actions with screenshots, returns a small text result card, and its context is thrown away. The orchestrator never sees a screenshot. The browser itself holds the real state, so throwing worker context away is safe. The orchestrator keeps one structured goal card, patches only the mutable parts, and a separate fresh-context call rechecks the original goal. That is the whole architecture.

orchestrator (thin context: goal card + progress + last result card)
   │  run_episode("on this page, open the apply form; return field names")
   ▼
worker (thick, disposable context; browser tools; keeps only the latest observation)
   │  acts on the SHARED browser session, 5-30 actions
   ▼
result card (≤300 tokens of text: outcome, facts, ids, evidence paths)
   │
   ▼
orchestrator patches goal card  →  every K episodes: fresh-context /goal recheck

1. Episodes, not actions, are the unit of delegation. A click-level subagent would respawn 25 times per page and lose the thread between clicks. A page-level episode has a goal, a done check, and an action cap. Only its result card reaches the orchestrator, so 25 actions cost the orchestrator about 300 tokens.

2. The browser session is the durable state, not the context. Workers attach to one shared Playwright context or Browserbase session. A new worker continues from the tab, cookies, and scroll position the last one left. This is what makes disposable worker contexts safe, and it is why the orchestrator can rebuild its own context at any time without losing the run.

3. Observation diet inside the worker. This is the biggest token saver, bigger than subagents. A screenshot costs roughly 1,000 to 1,500 tokens. Every turn re-sends every earlier one, so a 25-action page grows with the square of the action count. Keep only the latest one or two observations and drop the rest. Default to a trimmed text snapshot of interactive elements, screenshot when the text is ambiguous or to verify. Let the worker batch several actions per turn, fill five fields then observe once, so a page takes about 8 turns instead of 25.

4. Recipes for repeatable actions. When an episode succeeds, the worker returns the action sequence as a recipe keyed by site and task type. Next time the runtime replays the recipe without a model call and only invokes the worker when a step fails. This is the job-applier rule, deterministic browser first, agent as fallback, applied automatically.

5. Goal card with a patch tool and a fresh-context recheck. The card has two immutable sections, the original prompt and the done criteria, and three mutable ones, plan, progress, and blockers. The patch tool can only touch the mutable three. The card is re-rendered at the top of the orchestrator's context after every episode, which fixes goal drift caused by the goal sliding out of the recency window. The recheck runs in a fresh context on a cheap model every K episodes and on every "done" claim. It reads only the original prompt, the done criteria, and progress, and returns continue, done, or stalled with the gap. Fresh context is the part that matters. A recheck inside the drifting context agrees with the drift.

goal:       <original prompt, verbatim, immutable>
done_when:  <criteria, immutable except by the user>
plan:       <mutable>
progress:   <append-only facts: ids, urls, counts>
blockers:   <mutable>

Keep / change / add:
- Keep: minimal orchestrator, browser subagents, memory patch tool, the goal recheck.
- Change: delegate per page or form, not per click. Make the patch tool unable to touch the original prompt and done criteria. Run the recheck in a fresh context, not in the orchestrator's.
- Add: an action cap and a screenshot cap per episode, so a stuck worker returns a "stuck" card with evidence instead of burning the run. A gate on irreversible actions: a worker returns "ready to submit" and never submits, sends, or pays on its own. Resume for free: when the orchestrator's context fills or the process dies, start a new conversation from the goal card plus progress. That is exactly how the InfiniteMemoryAgent resume works.

What already exists in the SDK: InfiniteMemoryAgent has the episode pattern (pairs that return one short result card, a map re-rendered after every root iteration, resume as a fresh conversation built from the journal). Jev has the done-check questions in vidbyte/lib/jev/done/. The job-applier BrowserPort (vidbyte-harnesses) is index-addressed with no element handles. The context layer has compaction engines and context-window algorithms.

The smallest build is a BrowserEpisodeRunner that takes a page-level task and a shared session, prunes observations, caps actions, and returns a typed result card, plus a goal card with a patch tool and a recheck middleware. Everything else is prompt text.
````

The first answer (to Prompt 1) recommended a code-owned "harvest runtime" with ledgers and tool-level dedup for the bulk tasks. The user did not pick that up; Prompt 2 narrowed the ask to small tweaks of the linear loop, and Prompt 3 asks for the agent built from the Prompt 2 architecture. The harvest design is **out of scope** for this PR.

## C. Structured conversation notes

### Key decisions
- **Build `BrowserAgent` as a new SDK agent package at `vidbyte/agents/browser/`**, decomposed like `JevAgent` (`vidbyte/agents/jev/`): a narrow `BrowserAgent(BaseAgent)` facade that maps `BrowserAgentSettings` into `BaseAgent`, fixes its runtime to a new `AgentRuntimeType.BROWSER` resolved by `RuntimeRegistry` to `BrowserAgentRuntime(AgentRuntime)`, and builds its collaborators once at construction and passes them to the runtime. The user named the collaborators: `BrowserAgentRuntime`, `BrowserAgentSettings`, `BrowserAgentTools`, `BrowserAgentEvents`, `BrowserAgentUsage`, `BrowserAgentResponse` ("etc subclasses"). Each should be a few hundred lines at most ("try not to overengineer each class").
- **The runtime is the linear loop plus the five tweaks** from §B: (1) page-level episodes run by a disposable worker agent that returns a typed result card; (2) one shared browser session (the MCP server processes) that every episode acts on; (3) an observation diet inside the worker: keep only the latest N observations, cap actions and screenshots per episode; (4) repeatable actions recorded as recipes (see Q-1 for how much of this lands now); (5) a goal card with immutable goal and done criteria, a patch tool for plan, progress, blockers, re-rendered at the top of the orchestrator's context every iteration, plus a fresh-context recheck every K episodes and at every finish attempt.
- **The orchestrator never holds a screenshot.** Only result cards (bounded text) reach it. Evidence such as screenshots goes to files on disk and the card carries paths.
- **Users define browser MCP servers in the settings, by role, with their keys.** Reasoning (the user asked for judgment): the SDK already has `McpPresetDefinition` entries (`vidbyte/lib/config/mcp_presets.py`: `PlaywrightMCP`, `PuppeteerMCP`, `BrowserbaseMCP`, `FirecrawlMCP`, `JinaReaderMCP`, `BraveSearchMCP`, `TavilyMCP`, `ExaMCP`, `ApifyMCP`...) each with `required_env`, `McpPresetRegistry.build_config(...)` in `vidbyte/tools/mcp/presets.py`, `McpServerConfig(command, name, permission, env, timeout)` in `vidbyte/tools/mcp/types.py`, and `McpAttachableMixin.attach_mcp_servers(configs)` on `BaseAgent` (concurrent, all-or-nothing). So the settings should reference presets by name or definition and carry the env values; a custom server is a `command` with no preset. The proposed shape, which the spec author may rename within the house style:
  - `BrowserMcpServer(preset: str | McpPresetDefinition | None, env: Mapping[str, str] = {}, command: tuple[str, ...] | None = None, timeout: float = 30.0)`, frozen, validated in `__post_init__`: exactly one of preset or command; every `required_env` of the preset present in `env` or in `os.environ` else `ConfigurationError` naming the missing variable and the preset; `env` excluded from `repr` (pattern: `api_keys` is `repr=False` on `JevAgentSettings` and `InfiniteMemoryAgentSettings`).
  - `BrowserToolSettings(actions: tuple[BrowserMcpServer, ...], search: tuple[BrowserMcpServer, ...] = (), fetch: tuple[BrowserMcpServer, ...] = ())` with a `BrowserToolRole` enum (`ACTION`, `SEARCH`, `FETCH`). This is the user's "more than 1 param" idea (`browser_event_tools=playwright, browser_search_tools=firecrawl`), with role names chosen for what the tools do: ACTION servers drive pages (navigate, click, type, screenshot) and are given only to episode workers; SEARCH and FETCH servers (web search, page-to-markdown) are given to the orchestrator. At least one ACTION server is required.
  - The bridged tools from each server are partitioned by the server's role when the runtime attaches them, so the orchestrator's catalog and the worker's catalog are built from roles, not from tool names.
- **Episode worker**: a fresh `BaseAgent` per episode, built by `BrowserAgentTools`/the runtime from the settings (same provider/model as the orchestrator unless `BrowserEpisodeSettings` overrides the model), tools = ACTION bridged tools plus a `finish_episode` tool that takes the typed result card; `AgentLoopSettings(max_iterations=...)` from the action cap; observation pruning keeps only the latest `keep_observations` observation tool results in the worker's history; the result card is a frozen dataclass (`BrowserEpisodeResult`: outcome enum `DONE | STUCK | BLOCKED | READY_TO_SUBMIT`, facts, artifacts such as urls/ids, evidence paths, action count, tokens). Orchestrator tool: `run_episode(task, done_when)`; the user's words: "subagents with browser tools for specific actions".
- **Irreversible actions are gated**: a worker returns `READY_TO_SUBMIT` and never submits, sends, or pays on its own; the orchestrator decides. The default is to stop and report when the task requires a submit; there is no auto-submit flag in this PR.
- **Goal card**: `BrowserGoalCard(goal, done_when, plan, progress, blockers)`; `goal` is the user's prompt verbatim; `done_when` comes from `BrowserGoalSettings.done_when` when the user supplies it, otherwise from one structured call at run start; a `patch_goal(section, text)` orchestrator tool with a `GoalSection` enum (`PLAN | PROGRESS | BLOCKERS`) that refuses the immutable sections; the card is rendered at the top of the orchestrator's context on every iteration (pattern: InfiniteMemoryAgent re-renders its workspace map after every root tool iteration, `vidbyte/agents/infinite/runtime.py`).
- **Recheck**: a tool-free, fresh-context call on the recheck model (settable; default the orchestrator's model) that receives only `goal`, `done_when`, and `progress` and returns a structured `GoalVerdict` (`CONTINUE | DONE | STALLED`) with a gap sentence; runs every `recheck_every` episodes and at every finish attempt through the runtime's finish-attempt hook (the hook `JevRuntime` uses for `JevContinuation`); `DONE` lets the run finish; `CONTINUE` sends the gap back into the orchestrator's loop; `STALLED` (no progress change since the last recheck, `max_stalls` times) ends the run with a stop reason. Prior art the user researched: Claude Code's `/goal` is a Stop-hook evaluator on a cheap model with three verdicts and a stall stop; Codex keeps the goal in a store with a self-reported update and a continuation audit.
- **Orchestrator context rebuild**: when the orchestrator's history passes a token cap, the runtime starts a fresh conversation whose first message is the goal card plus progress (pattern: `InfiniteMemoryAgent.resume` builds a fresh conversation from the journal). In-run only; see Q-2.
- **Events**: `BrowserAgentEvents` is the one writer of `BrowserEvent` records (frozen dataclass, JSON-representable fields, no model calls) delivered to `BrowserAgentSettings.on_event`; a sink exception never reaches the run. Event kinds (enum): `run_started`, `goal_set`, `episode_started`, `episode_finished`, `goal_patched`, `goal_rechecked`, `context_rebuilt`, `recipe_recorded`, `run_finished`, `run_stopped`. Pattern: `JevResponse` (`vidbyte/agents/jev/response.py`) is the one-writer pattern; the InfiniteMemory events contract (`InfiniteEvents`, in SDK PR #1084's stacked events branch, not on main) is the sibling shape.
- **Usage**: `BrowserUsageAccount` modeled on `JevUsageAccount` (`vidbyte/agents/jev/usage.py`): the agent's own tracker is the one ledger for the run, episode workers and recheck calls included; fail closed when usage cannot be recorded or priced; report on the response.
- **Response**: `BrowserResponse` writer (pattern `JevResponse`) → `BrowserAgentResponse` record on `BrowserAgent.response`: final goal card, episodes (result cards), rechecks, context rebuild count, usage, stop reason.
- **Placement** per AGENTS.md: dataclasses in `vidbyte/lib/dataclasses/browser.py`, enums in `vidbyte/lib/enums/browser.py` (exported from `vidbyte/lib/enums/__init__.py`), constants in `vidbyte/lib/constants/browser.py`, settings objects in `vidbyte/agents/browser/settings.py` (the settings exception), prompts as a prompt family under `vidbyte/prompts/prompts/` with keys in `vidbyte/lib/enums/prompts.py` (verify the pattern the scout finds for Jev and Infinite prompts), `AgentRuntimeType.BROWSER` in `vidbyte/lib/enums/agent_runtime.py`, registry row in `vidbyte/lib/registries/runtimes.py`, exports in `vidbyte/agents/__init__.py` and `vidbyte/__init__.py`, a folder `README.md` with a File Index and `## Notes for agents`, REPO_MAP entry, feature test pack under `tests/features/browser_agent/` modeled on `tests/features/infinite_memory_agent/`.

### Rejected alternatives
- A subagent per browser action (click, type): 25 spawns per page and no continuity between clicks; rejected in favor of page-level episodes.
- Running the goal recheck inside the orchestrator's own context: it agrees with the drift; rejected in favor of a fresh-context call.
- Summarizing the orchestrator transcript when it fills: lossy; rejected in favor of rebuilding from the goal card plus progress.
- Building the bulk "harvest" runtime (ledgers, tool-level dedup, frontier) from the first answer: the user narrowed scope in Prompt 2; out of scope.
- A single `mcp_servers` list with no roles: cannot decide which loop sees which tools; rejected in favor of role slots.
- Browser adapters (Playwright code, Browserbase SDK) inside the SDK: the SDK stays primitives-only and talks to browsers only through MCP servers; the website-tester package in vidbyte-harnesses states that the host owns browser tooling.

### Constraints and assumptions
- Repo rules: `vidbyte-sdk/AGENTS.md` (one-level call chains, narrated main functions, layered small classes, validated frozen dataclasses, canonical helpers in `vidbyte/lib/`, placement rules); `docs/` is opaque except the pipeline's own `docs/spec/browser-agent/`; the full local gate is `python scripts/run_ci.py`.
- The SDK is multi-provider; model and provider strings follow `ProviderModelRegistry`. Examples in READMEs use whatever provider the sibling READMEs use.
- MCP servers are subprocesses on stdio (`vidbyte/tools/mcp/transport.py`); the shared browser session lives inside the ACTION server process for the whole run, so the runtime attaches servers once per run and closes them when the run ends (`BaseAgent` already releases MCP handles around `run`).
- Assumption to verify by the scout: how image content (screenshots) returned by an MCP tool flows through `McpToolBridge` into the context today (text only, base64, or an image block). The observation-diet rule must prune whatever shape arrives.
- Assumption: the orchestrator model and the episode model are configured separately; both default to the same provider/model.
- The user is on a usage-limited account; no gate may call a paid model. Tests use the SDK's fakes (stub runners, recording tracers), as the infinite-memory feature pack does.

### Clarifications and answers
- Prompt 2 clarified the three attributes the design must address: token-heavy screenshots and 25+ actions per page; many repeatable actions; a dynamically updated main memory that preserves the original goal.
- Prompt 3 clarified the deliverable: a JevAgent-shaped decomposition, each class small; settings that define browser MCP servers by role with their keys; "use judgement to decide best way to implement".

### Terminology
- **Episode**: one page-level or form-level task run by a disposable worker agent against the shared browser session, with an action cap, ending in a result card.
- **Result card**: the bounded, typed text record an episode returns to the orchestrator.
- **Goal card**: the orchestrator's structured memory: goal, done_when (immutable), plan, progress, blockers (mutable).
- **Recheck**: the fresh-context verdict on the goal card (continue, done, stalled).
- **Observation**: a tool result that describes the page (screenshot, DOM or accessibility snapshot).
- **Role**: which loop an MCP server's tools serve: ACTION (workers), SEARCH or FETCH (orchestrator).
- **Recipe**: the recorded action sequence of a successful episode, keyed by site and task kind.

### Implementation hints
- Model the facade on `vidbyte/agents/jev/agent.py` (closed construction surface, `ConfigurationError` on wrong settings types, collaborators built once), the runtime on `vidbyte/agents/jev/runtime.py` (an `AgentRuntime` subclass that wraps the inherited loop, uses the finish-attempt hook, scopes usage), the response writer on `vidbyte/agents/jev/response.py`, the usage account on `vidbyte/agents/jev/usage.py`, the settings on `vidbyte/agents/jev/settings.py` and `vidbyte/agents/infinite/settings.py` (`api_keys` with `repr=False`, `tools`, `loop`, `vidbyte_api_key`, `model_mode`).
- The episode worker and the per-iteration card re-render follow `vidbyte/agents/infinite/launch.py` and `vidbyte/agents/infinite/runtime.py`.
- MCP attachment: `vidbyte/agents/mixins.py` (`attach_mcp_servers`), `vidbyte/tools/mcp/presets.py` (`McpPresetRegistry.get`, `build_config`), `vidbyte/tools/mcp/types.py` (`McpServerConfig`), `vidbyte/lib/config/mcp_presets.py` (preset definitions and `required_env`).
- Runtime registration: `vidbyte/lib/enums/agent_runtime.py` and `vidbyte/lib/registries/runtimes.py` (lazy imports, one dict).
- Budget middleware exists (`vidbyte/middleware/builtins/cost_budget.py`, `token_budget.py`) if a per-episode cost cap is wanted; prefer `AgentLoopSettings` limits for the action cap.
- Keep every class a few hundred lines; prefer fewer files; no abstraction with one implementation.

### Open questions (carry as Q-n with these defaults unless the user replies)
- **Q-1 Recipes**: how much of tweak 4 lands in this PR? *Default:* record only. Every successful episode's action sequence is recorded on its result card and in a `recipe_recorded` event; deterministic replay without a model is a follow-up PR. Reason: replay needs a store format and keying rules the conversation did not settle, and the user asked not to overengineer.
- **Q-2 Cross-process resume**: journal the run so `resume()` works after a crash, as InfiniteMemoryAgent does? *Default:* no. In-run context rebuild from the goal card only; a journal and `resume()` are a follow-up.
- **Q-3 done_when source**: when `BrowserGoalSettings.done_when` is not given, derive it with one structured model call at run start, or require it? *Default:* derive it with one call, record it on the goal card, and emit `goal_set`.
- **Q-4 Default caps**: action cap per episode, screenshot cap, observations kept, recheck cadence. *Default:* 30 actions, 5 screenshots, 2 observations kept, recheck every 5 episodes, 3 stalls; all constants in `vidbyte/lib/constants/browser.py`, all overridable in settings. The user said to measure on 20 pages first, so these are starting values.
- **Q-5 Role of SEARCH/FETCH tools for workers**: do episode workers also get FETCH tools? *Default:* no; workers get ACTION tools only.

## D. Weighted words
- "I dont want you to overcomplex things" (Prompt 2): the design must stay small.
- "just small architectural tweaks to the main linear agent loop" (Prompt 2): the runtime wraps the inherited linear loop; it does not replace it.
- "minimal main orchestrator agent" (Prompt 2): the orchestrator's catalog and context stay thin.
- "subagents with browser tools for specific actions (clicking, searching, typing, etc)" (Prompt 2): workers hold the action tools.
- "a memory patch tool" (Prompt 2): one patch tool over the goal card's mutable sections.
- "rechecks the original goal/done critiera with original prompt" (Prompt 2): the recheck reads the original prompt, not a summary.
- "try not to overengineer each class, alot of these can be implemented in only a few hundred lines of code" (Prompt 3): class size is a requirement.
- "the user for the browser agent, in its settings, should be able to "define' the actual browser mcp servers that they want to use" (Prompt 3): settings-level MCP definition is required.
- "they should also we required to upload their api keys into the agent settings" (Prompt 3): keys are supplied in settings and validated there.
- "the browser tools themselves could even have more than 1 param (ex: browser_event_tools=playwright, browser_search_tools=firewcrawl)" (Prompt 3): more than one role slot.
- "use judgement to decide best way to implement something like this" (Prompt 3): the role-slot design in §C is that judgment; the spec author may refine names.
- From the accepted architecture (§B): "The orchestrator never sees a screenshot"; "The patch tool can only touch the mutable three"; "Fresh context is the part that matters"; "a worker returns 'ready to submit' and never submits, sends, or pays on its own"; "keep only the latest one or two observations".
