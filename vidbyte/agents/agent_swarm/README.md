# AgentSwarm

`AgentSwarm` runs a group of agents on one goal. The developer names the agents and their models; every agent gets the same sectioned system prompt, works in the same folder with the same file and shell tools, and can send a text message to any agent of the swarm, itself included, with the `message` tool. Each agent can also compact its own history with the `compact` tool, and compacts automatically once its real prompt size grows past a trigger. Each agent works in turns: a turn ends when it replies without calling a tool, or calls `isDone`, and the agent then waits until a message wakes it. The swarm stops once no agent is working, the token budget is spent, or the time limit is reached. One `arun(goal)` call returns an `AgentSwarmResult` with the stop reason, every event in order, and the last reply of every agent the swarm released.

## Usage

```python
import asyncio

from vidbyte import AgentSwarm, AgentSwarmMember, AgentSwarmSettings

settings = AgentSwarmSettings(
    agents=(
        AgentSwarmMember(name="ada", provider="openai", model_name="gpt-4.1"),
        AgentSwarmMember(name="ben", provider="openai", model_name="gpt-4.1"),
        AgentSwarmMember(name="cleo", provider="openai", model_name="gpt-4.1"),
    ),
    workplace="swarm-workplace",          # created if missing, never cleaned
    api_keys=["sk-proj-..."],             # matched to each member's provider
    web_search="tavily",                  # AgentSwarmWebSearch value; None means no web search
    web_search_api_key="tvly-...",
    on_event=lambda event: print(event.sequence, event.kind.value, event.agent, event.peer, event.text),
)

result = asyncio.run(AgentSwarm(settings).arun("Build a Celsius-to-Fahrenheit command-line tool with tests."))
print(result.stop_reason.value, len(result.events), len(result.replies))
```

The model keys come from the usual provider environment variables when `api_keys` is not given. The web-search key is never read from the environment.

## Lifecycle

A run records `workplace_prepared` (with `folder_state` `created` or `existed`), then `agent_created` and `agent_started` for every member in member order. Every agent gets the goal as its first message and starts working at once; each agent is one long agent run for the whole swarm, so it keeps its conversation from turn to turn.

- **Messages.** A message to a working agent is delivered once the tool calls of its current model response have run, or when its turn ends; a message to an idle agent wakes it, and the waiting messages become its next user message, each labeled with its sender. Sending never waits for the recipient. A send to an unknown name, or with blank text, is a tool error recorded as `message_refused`. A send to an agent that has left the swarm, or any send once the swarm is stopping, succeeds with a reply saying the recipient stopped, and is recorded `message_sent` then `message_undelivered`. Every sent message ends with exactly one `message_delivered` or `message_undelivered`.
- **Turns.** Every first turn and every wake counts against `max_turns`. When no turn is left, a message to an idle agent is queued with one `wake_refused`, and so is mail waiting at a turn end.
- **Compaction.** After each tool iteration, before any mail is appended, an agent's history is compacted when it called `compact` (with an optional focus) or when its last reported prompt size reached `AGENT_SWARM_COMPACTION_TRIGGER_TOKENS`. After its first compaction, an automatic one also waits until the history's estimate (whole messages, four characters per token) has grown by `AGENT_SWARM_COMPACTION_TARGET_TOKENS` since the last, so a prompt, tool list, and goal that alone reach the trigger cost one summary per target of new history, not one per tool iteration; a `compact` call never waits. The agent's own model writes a handoff summary of the older messages in ten sections (identity, peers, goal, messages received and sent, promises to peers, files changed, work in progress, decisions, next steps); the newest messages that fit `AGENT_SWARM_COMPACTION_TARGET_TOKENS` are kept as they are. The summary call counts against the token budget, and a failed summary call is a `model_error` that keeps the history. The provider-boundary trim still runs before every model call as the backstop.
- **Ending.** The stop is decided once and recorded as `swarm_stopping`; in the same step every queued message is marked undelivered and every idle agent is released. After it no agent calls the model again, except a call already in flight. Each agent then ends with exactly one of `agent_released` (its run returned after the decision; its reply is kept), `agent_cancelled` (the time limit, with `agent_state` `working` or `idle`), `agent_failed` (a model or SDK error, or a stray `CancelledError`), or `agent_exited` (its run returned on its own before the decision, named by the loop's stop reason). A failed or exited agent's waiting mail is marked undelivered with it; the others go on.

| Stop reason | When |
|---|---|
| `quiet` | No agent is working and no message is waiting for a running agent. |
| `max_turns` | No agent is working, and a message is still waiting because no turn was left to wake its recipient. |
| `max_tokens` | One model call, a summary call included, brought the swarm's token total to `max_tokens`. |
| `failed` | Every agent failed or exited. |
| `timeout` | `timeout_seconds` passed first; every agent still running is cancelled and `replies` is empty. |

## Limits and defaults

| Setting | Default | Rule |
|---|---|---|
| `agents` | required | 2 to 500 `AgentSwarmMember(name, provider, model_name)` with distinct names matching `AGENT_SWARM_NAME_PATTERN` |
| `workplace` | required | a folder path; created with its parents when a run starts; never a file |
| `api_keys` | the environment | matched once against every member's provider; never shown |
| `web_search` | `None` | `brave`, `browserbase`, `exa`, `parallel`, or `tavily`; every agent then holds that provider's search tool |
| `web_search_api_key` | `None` | required with `web_search`, refused without it; never shown |
| `on_event` | `None` | sync or async; called once per event, in order, never twice at once |
| `max_turns` | 100,000 | every first turn and every wake counts; at least the number of agents |
| `max_tokens` | 10,000,000,000 | the swarm-wide token budget (`total_tokens`, else input plus output); at least 1 |
| `timeout_seconds` | 86,400.0 | finite, above zero, at most thirty days |

Each agent's history is compacted from 72,000 measured tokens down to its newest 27,000, trimmed past 90,000 tokens before every model call, and each tool result the model sees is cut at 100,000 characters. Every limit is a constant in `vidbyte/lib/constants/agent_swarm.py` and is enforced in code; the prompts say only that limits exist.

## Events

| Kind | `agent` | Other fields |
|---|---|---|
| `workplace_prepared` | `""` | `path` (absolute), `folder_state` |
| `agent_created` | the agent | — |
| `agent_started` | the agent | — |
| `model_called` | the caller | `input_tokens` (billed), `output_tokens`, `cached_tokens`, `model_calls` |
| `model_error` | the caller | `text`: `<Type>: <message>` of one failed attempt |
| `history_trimmed` | the agent | `messages_dropped` by the trim for one call |
| `tool_called` | the caller | `tool_name`, `tool_status`; `isDone` is not recorded |
| `tool_result_truncated` | the caller | `tool_name`, `omitted_chars` |
| `file_changed` | the writer | `path` (absolute), `peer` (the previous writer when another agent, else `""`) |
| `command_failed` | the caller | `text`: `exit code <n>` or `timeout` for one `bash` call |
| `compaction` | the agent | `compaction_trigger` (`tool` or `auto`), `text` (the focus, may be `""`), `input_tokens` (measured context), `messages_dropped` |
| `message_sent` | the sender | `peer` (recipient), `message_id` (its own `sequence`), `text` |
| `message_refused` | the sender | `peer` (the attempted name as text, `""` when none), `text` (the reason) |
| `message_delivered` | the recipient | `peer` (sender), `message_id` |
| `message_undelivered` | the recipient | `peer` (sender), `message_id` |
| `wake_refused` | the recipient | `peer` (sender), `message_id` |
| `agent_idle` | the agent | `text`: the reply that ended its turn |
| `agent_woke` | the agent | — |
| `swarm_stopping` | `""` | `stop_reason` |
| `agent_released` | the agent | — |
| `agent_cancelled` | the agent | `agent_state` (`working` or `idle`) |
| `agent_failed` | the agent | `text`: the cause's type name and message |
| `agent_exited` | the agent | `text`: the loop's own stop reason |
| `swarm_ended` | `""` | `stop_reason` |

Every event has a `sequence` (1, 2, … in the order the changes happened) and `elapsed_ms` since the run started; a field its kind does not list keeps its default. An exception raised by `on_event` never stops the swarm; its type name is kept in `AgentSwarmResult.event_error_types`.

## File Index

- `__init__.py`: the package facade, exporting `AgentSwarm`, `AgentSwarmSettings` (a lib record, re-exported here), `AgentSwarmRuntime`, `AgentSwarmEvents`, `AgentSwarmWorkplace`, and `AgentSwarmMemberRuntime`.
- `swarm.py`: `AgentSwarm`, the entry point; prepares the folder and runs one fresh `AgentSwarmRuntime` per `arun`, refusing a concurrent run.
- `runtime.py`: `AgentSwarmRuntime`, one swarm run: the shared prompt, the inboxes, turns, wakes, token budget, compaction requests, the observations, the stop, and the replies.
- `member.py`: the member's loop (`AgentSwarmMemberRuntime`, which compacts and then delivers mail after each tool iteration), its agent, and the `message` tool; each agent gets the trim, turn, and observer middleware, which live in the middleware layer as `vidbyte.middleware.builtins.agent_swarm_turn` and `vidbyte.middleware.builtins.agent_swarm_observer`.
- `compaction.py`: `AgentSwarmHandoffSummarizer`, which writes the handoff summary through the member's own model, and the `compact` tool.
- `events.py`: `AgentSwarmEvents`, the numbered event record and its in-order, once-only delivery to `on_event`.
- `workplace.py`: `AgentSwarmWorkplace`, which creates the shared folder, reports whether it created it, and never cleans it.
- `README.md`: this file.

## Notes for agents

- `AgentSwarmRuntime` is one swarm run; `AgentSwarmMemberRuntime` is one member's loop, which `AgentRuntimeType.AGENT_SWARM_MEMBER` resolves to and which refuses to run outside a swarm.
- Every state change (a send, a wake, a turn end, a failure, a token count, the stop) happens in one block with no `await` inside, together with its events, in the same block as the branch that decides it; only the event delivery is awaited afterwards. Keep it that way: an `await` between a check and its change can lose or double a message. The one exception is the cancel branch of `_run_member`, which records without flushing because its task is being torn down; the run's last flush delivers it.
- The stop reason is set only in `_stop`, and a new end condition goes through it, so `swarm_stopping` and the undelivered marks stay in one step.
- `_after_tool_iteration` compacts before it appends mail, so a delivered message never sits before the summary.
- `bash` is not confined to the workplace and inherits the process environment, so do not run a swarm where its agents should not reach.
- Agents edit the same files at the same time, and nothing serializes their edits; concurrent edits to one file can collide. `file_changed` sees only `write_text` and `patch_file`, never a write made through `bash`.
- A member makes no retry of a failed model call: the first provider error fails it, and its inbox is marked undelivered.
- On Windows, a cancelled `bash` command (on the time limit) may keep running after the swarm returns.
- Two swarms on one workplace at the same time are not guarded against each other.
- Limits live in code, not in prompts. A new limit is a constant, a settings field, and a check whose refusal names it.
- A bug in the swarm's turn-end or delivery code (`end_turn`, `collect_messages`) surfaces as `agent_failed` naming its cause. A bug in its event recording (`record_tool_call`, and the observer's `record_tool_outcome`, `record_model_call`, `record_model_error`, `record_history_trim`) surfaces as `agent_exited` with text `middleware_abort` (or `agent_failed`, when the call is the compaction summary's), because the fail-closed middleware returned the run before the swarm decided to stop; the summary call is recorded by the member runtime, outside that middleware, so its bug leaves the loop as an error instead. A bug in a tool, including `message`, is a tool error in `tool_called` that the agent reads and continues past. Check `agent_failed`, `agent_exited`, and error-status `tool_called` events before trusting a `quiet` or `failed` result.
