# Browser agent

`BrowserAgent` is an agent for long-running browser tasks: finding, comparing, and recording things across many sites over hours. It splits the work in two. An orchestrator plans, keeps a goal card, and reads through search and fetch tools; it never touches a page. Each piece of page work runs as an episode in a fresh worker that holds only the browser action tools, works under fixed caps, and returns one short result card. The browsers themselves are the developer's own MCP servers (Playwright, Browserbase, Firecrawl, and so on), each given a role and its own keys in the settings.

```python
from vidbyte import BrowserAgent, BrowserAgentSettings, BrowserServerSettings
from vidbyte.tools.mcp import FirecrawlMCP, PlaywrightMCP

agent = BrowserAgent(
    BrowserAgentSettings(
        name="vc-scout",
        system_prompt="You find seed-stage accelerator programs and record where to apply.",
        provider="openai",
        model_name="gpt-5.4-mini",
        action_servers=(BrowserServerSettings(PlaywrightMCP),),
        search_servers=(BrowserServerSettings(FirecrawlMCP, env={"FIRECRAWL_API_KEY": "fc-your-key"}),),
        done_when=("Twenty programs are listed, each with its application URL and deadline.",),
        on_event=lambda event: print(event.kind.value, event.detail),
    )
)
reply = agent.run("Find twenty seed-stage accelerator programs that accept applications this quarter.")
print(reply.content)
print(agent.response.stop_reason, len(agent.response.episodes))
print("\n".join(agent.response.goal.progress))
```

A preset runs its registered command (`PlaywrightMCP` runs `python -m mcp_server_playwright`). When that command is not installed, pass the server's own command instead, for example `BrowserServerSettings(command=("npx", "@playwright/mcp@latest"))`.

## What it is for

- Browser tasks too long for one conversation: the orchestrator's context stays bounded however many pages the workers visit, because it sees only result cards and its goal card.
- Developers who already run browser MCP servers. Each server is a `BrowserServerSettings` with a registered preset (by definition or name) or a `command`, its own `env`, and its own `timeout`. A preset that requires a key refuses settings whose `env` lacks it.
- Tasks with a clear end. `done_when` lists the done criteria; when it is empty, one structured call writes them from the task before the run starts.
- Runs a developer can watch: `on_event` receives one `BrowserEvent` per step, and `agent.response` holds the goal card, every episode card, every recheck, the rebuild count, the stop reason, and the run's usage.

## What it is not for

- No browser code in the SDK: every page action goes through an MCP server.
- No bulk harvest runtime with ledgers, deduplication, or a URL frontier; the goal card holds about 480 to 800 progress lines.
- No replay of recorded recipes; a recipe is recorded on a `done` card only.
- No run journal, `resume()`, durable `Session` persistence, or working `fork()`.
- No auto-submit: a worker reports `ready_to_submit`, and nothing in code acts on it. The rule itself is in the prompts only; see Notes for agents.
- No image passthrough: the MCP bridge turns every image into a text placeholder.
- No pricing of vendor-billed MCP usage; `agent.response.usage` counts model calls only.
- No CLI command; build the agent from Python.

## How a run works

- **Roles.** `action_servers` (at least one) act on pages; `search_servers` and `fetch_servers` read. Each server starts under the name `browser-<role>-<n>` with only its own env. At run start the runtime splits the live tools by that name: the workers get the action tools, and the orchestrator keeps the search and fetch tools and the developer's `tools`.
- **Episodes.** The orchestrator calls `run_episode(task, done_when)`. A fresh worker, a plain `BaseAgent` with `output_schema=BrowserEpisodePayload`, does the page work and answers with an outcome (`done`, `stuck`, `blocked`, or `ready_to_submit`), a summary, facts, URLs, and evidence. When it hits its action cap or cannot answer in the schema, the card is built from its last reply as `stuck`, with the exact action count and the newest observation it saw. The orchestrator receives the card as text cut at 800 tokens.
- **Goal card.** The goal, the done criteria, the plan, the progress, the blockers, the latest verdict and gap, and the last episode, pinned at the top of the orchestrator's context on every call. The orchestrator changes the plan, progress, or blockers through `patch_goal`; progress only grows, and the goal and criteria never change during a run.
- **Recheck.** Every finish attempt, by final text or by `isDone`, is checked by a fresh agent that sees only the goal, the criteria, and the progress. A `done` verdict, or an unavailable recheck, accepts the finish; otherwise the card shows the verdict and gap, one message carries them, and the same loop continues. A recheck also runs after every `recheck_every` episodes.
- **Stalls.** A `stalled` verdict, or `continue` with progress unchanged since the previous recheck, counts one stall; anything else resets the count. At `max_stalls` the run stops with `goal_stalled` before its next model call, and its output is the card.
- **Rebuild.** After every tool iteration and every refused finish, once the stored conversation passes 60,000 tokens it is rebuilt to its newest whole call/result group through `ContextCompactionEngine`. The card carries everything older, so nothing is summarized.

## Limits and defaults

All of them live in `vidbyte/lib/constants/browser.py`, and every cap is enforced in code; the prompts carry no numbers.

- Orchestrator: 1,000 iterations and tool results cut at 20,000 characters, unless you pass another `loop`; history rebuilt past 60,000 tokens.
- Each episode: `max_actions` 30 browser calls (the worker's `max_tool_calls`), `max_screenshots` 5 per screenshot tool (`ToolSettings.max_calls_per_tool`), the newest `keep_observations` 2 results of each tool kept whole and older ones cut to 400 characters, and the worker's history trimmed to 32,000 tokens.
- Rechecks: `recheck_every` 5 episodes and `max_stalls` 3.
- Servers: `timeout` 30 seconds per request, at most 600.
- Cards: the result card 800 tokens; a summary 2,000 characters; facts, URLs, and evidence items 500 characters, 50 of each; 20 done criteria; plan and blockers 8,000 characters each; progress 96,000 characters; an event detail one line of at most 500 characters.

## Shared helpers

This package builds on canonical helpers rather than private copies: `RecordFieldValidator` and `RecordFieldConverter` check every settings and record field; `McpPresetRegistry.build_config` checks a preset's keys; `ProviderModelRegistry` and `ProviderKeyMatcher` check the model and keys; the MCP mixin's `with_preset_mcp_server` and `with_mcp_server` queue and start the servers; `MessageHistoryCompactionMiddleware` bounds the worker's history; `ContextCompactionEngine` rebuilds the orchestrator's; `TokenEstimate.cap` cuts the result card; and `JevUsageAccount.failures` decides when the usage ledger fails closed.

## File Index

- `__init__.py`: the package facade, exporting the agent, its two settings objects, and the runtime.
- `agent.py`: `BrowserAgent`, which maps the settings into `BaseAgent` and queues each server under its role name.
- `settings.py`: `BrowserAgentSettings` and `BrowserServerSettings`, validated when they are created.
- `runtime.py`: `BrowserAgentRuntime`, which splits the tools by role, pins the card, runs the loop, rechecks finishes, rebuilds the history, and stops a stalled run.
- `tools.py`: `BrowserAgentTools`, the map from server name to role and the live tools of one role.
- `episode.py`: `BrowserEpisodeTool`, the `run_episode` tool and its fresh worker.
- `goal.py`: `BrowserGoal`, the card and `patch_goal`, and `BrowserGoalCheck`, the done-criteria and recheck calls.
- `events.py`: `BrowserAgentEvents`, which numbers events and delivers them to the sink.
- `usage.py`: `BrowserAgentUsage`, the run's one usage ledger, which fails closed.
- `response.py`: `BrowserResponse`, the one writer of `agent.response`.
- `README.md`: this file.

## Notes for agents

- The no-submit rule lives only in the worker and orchestrator prompts. Browser MCP tools are generic, so code cannot tell a submit from any other click, and an injected page instruction can still lead a worker to submit, send, or pay. `settings.permission_policy` (allow-all by default) applies to every worker and orchestrator tool call; it is the code gate the developer controls.
- Overlapping `arun` calls on one agent are unsupported: the response writer belongs to the agent, so the runs overwrite each other's record.
- Each synchronous `run()` closes the servers and starts them again, so cookies and tabs do not survive between sync runs; use `arun` or `async with agent:` to keep one browser.
- An explicit `system=` run option replaces the system prompt and the goal card for that run; the runtime leaves the caller's option alone.
- Do not log or print `mcp_servers()`: each handle's config repr shows its server's env, keys included.
- A recipe keeps each call's arguments verbatim, so a typed password sits on `agent.response.episodes[i].recipe` in process memory; events carry only the step count, and the SDK writes no file.
- The goal card holds about 480 to 800 progress lines at 120 to 200 characters each; past that `patch_goal` refuses progress, every later recheck counts as a stall, and the run ends `goal_stalled`.
- A rebuild keeps only the newest call/result group, after a tool iteration or a refused finish; a newest group that alone passes the cap is kept whole, so nothing is removed and nothing is recorded.
- The orchestrator rules say to finish through `isDone`: after a refused final-text finish, the loop appends the model's own answer after the gap message.
- Keep caps in code. A new cap is a constant, a settings field, and a check in code whose refusal names it; the prompts say only that limits exist.
- Screenshots reach the model as text placeholders, so the worker rules say to take one only to save evidence; the screenshot cap covers every action tool whose name contains `screenshot` in any case.
- Before adding a private helper here, look in `vidbyte/lib/` for a canonical one and add an option to it.
