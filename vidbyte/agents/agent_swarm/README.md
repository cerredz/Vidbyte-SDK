# AgentSwarm

`AgentSwarm` runs a group of agents the developer defines on one goal. Every agent works in the same folder with the same file and shell tools, and any agent can send a text message to any other agent with the `message` tool. Each agent works in turns: a turn ends when it replies without calling a tool, or calls `isDone`, and the agent then waits until a message wakes it. The swarm ends once no agent is working, or when the time limit is reached. A spent turn budget does not end it by itself: it stops further wakes, so the swarm ends `max_turns` only when a message is left waiting, and `quiet` otherwise. One `arun(goal)` call returns an `AgentSwarmResult` with the stop reason, every event in order, and each agent's last reply.

## Usage

```python
import asyncio

from vidbyte import AgentSwarm, AgentSwarmMember, AgentSwarmSettings
from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmEvent


def show(event: AgentSwarmEvent) -> None:
    # Called once per event, in order, while the swarm runs.
    print(event.sequence, event.kind.value, event.agent, event.peer)


swarm = AgentSwarm(
    AgentSwarmSettings(
        agents=(
            AgentSwarmMember(name="builder", system_prompt="You write the code.", provider="openai", model_name="gpt-4.1"),
            AgentSwarmMember(name="tester", system_prompt="You write and run the tests.", provider="openai", model_name="gpt-4.1"),
        ),
        workplace="swarm-workplace",  # one folder both agents share; created if missing, never deleted
        on_event=show,
    )
)

result = asyncio.run(swarm.arun("Build a Celsius-to-Fahrenheit command-line tool with tests."))
print(result.stop_reason.value)                          # quiet
print(result.events[-1].sequence == len(result.events))  # True
print(result.events[-1].kind.value)                      # swarm_ended
for reply in result.replies:
    print(reply.sender, reply.content)  # each agent's reply from its last turn
```

The API keys come from the usual provider environment variables when `api_keys` is not given.

## Lifecycle

Every agent gets the goal as its first message and starts working at once. Each agent is one long agent run for the whole swarm, so it keeps its conversation from turn to turn. A message sent to a working agent is delivered once the tool calls of its current model response have run, or when its turn ends; a message sent to an idle agent wakes it, and the messages become its next user message, each labeled with its sender. Sending never waits for the recipient. An agent whose model call fails, or whose run stops on its own, leaves the swarm with an `agent_failed` event naming the cause, and later messages to it are refused; the others go on.

| Stop reason | When |
|---|---|
| `quiet` | No agent is working and no message is waiting for a running agent. |
| `max_turns` | No agent is working, and a message is still waiting because the turn budget was spent before it could wake its recipient. |
| `failed` | Every agent failed. |
| `timeout` | `timeout_seconds` passed first; every agent is cancelled and `replies` is empty. |

## Limits and defaults

| Setting | Default | Rule |
|---|---|---|
| `agents` | required | 2 to 100 members with distinct names matching `AGENT_SWARM_NAME_PATTERN` |
| `workplace` | required | a folder path; created with its parents when a run starts; never a file |
| `api_keys` | the environment | matched once against every member's provider; never shown |
| `search_tool` | `None` | one extra tool every agent holds; may not take a swarm tool's name or `isDone` |
| `on_event` | `None` | sync or async; called once per event, in order, never twice at once |
| `max_turns` | 500 | every first turn and every wake counts; at least the number of agents |
| `timeout_seconds` | 3600.0 | finite, above zero, at most one week |

Each agent's history is trimmed past 90,000 tokens, and each tool result the model sees is cut at 100,000 characters. Every limit is a constant in `vidbyte/lib/constants/agent_swarm.py` and is enforced in code; the prompts say only that limits exist.

## Events

| Kind | `agent` | Other fields |
|---|---|---|
| `agent_started` | the agent | — |
| `tool_called` | the caller | `tool_name`, `tool_status`; `isDone` is not recorded |
| `message_sent` | the sender | `peer` (recipient), `message_id` (its own `sequence`), `text` |
| `message_delivered` | the recipient | `peer` (sender), `message_id` of the sent message |
| `agent_idle` | the agent | `text`: the reply that ended its turn |
| `agent_woke` | the agent | — |
| `agent_failed` | the agent | `text`: the cause's type name and message |
| `swarm_ended` | `""` | `stop_reason` |

Every event has a `sequence` (1, 2, … in the order the changes happened) and `elapsed_ms` since the run started. An exception raised by `on_event` never stops the swarm; its type name is kept in `AgentSwarmResult.event_error_types`.

## File Index

- `__init__.py`: the package facade, exporting `AgentSwarm`, `AgentSwarmSettings`, `AgentSwarmRuntime`, `AgentSwarmEvents`, `AgentSwarmWorkplace`, and `AgentSwarmMemberRuntime`.
- `swarm.py`: `AgentSwarm`, the entry point; prepares the folder and runs one fresh `AgentSwarmRuntime` per `arun`, refusing a concurrent run.
- `settings.py`: `AgentSwarmSettings`, validated when it is created, with the keys matched once.
- `runtime.py`: `AgentSwarmRuntime`, one swarm run: the inboxes, turns, wakes, failures, the end check, and the replies.
- `member.py`: the member's loop (`AgentSwarmMemberRuntime`), its agent, and the `message` tool; each agent gets the turn middleware that turns a finish into the end of a turn, which lives in the middleware layer as `vidbyte.middleware.builtins.agent_swarm_turn`.
- `events.py`: `AgentSwarmEvents`, the numbered event record and its in-order, once-only delivery to `on_event`.
- `workplace.py`: `AgentSwarmWorkplace`, which creates the shared folder and never cleans it.
- `README.md`: this file.

## Notes for agents

- `AgentSwarmRuntime` is one swarm run; `AgentSwarmMemberRuntime` is one member's loop, which `AgentRuntimeType.AGENT_SWARM_MEMBER` resolves to and which refuses to run outside a swarm.
- Every state change (a send, a wake, a turn end, a failure, the end decision) happens in one block with no `await` inside, together with its event; only the event delivery is awaited afterwards. Keep it that way: an `await` between a check and its change can lose or double a message.
- `bash` is not confined to the workplace and inherits the process environment, so do not run a swarm where its agents should not reach.
- Agents edit the same files at the same time, and nothing serializes their edits; concurrent edits to one file can collide.
- On Windows, a cancelled `bash` command (on the time limit) may keep running after the swarm returns.
- Two swarms on one workplace at the same time are not guarded against each other.
- Limits live in code, not in prompts. A new limit is a constant, a settings field, and a check whose refusal names it.
- A bug in the swarm's turn-end or delivery code (`end_turn`, `collect_messages`) surfaces as `agent_failed` naming its cause; a bug in its event recording (`record_tool_call`) as `agent_failed` naming the middleware abort; and a bug in a tool, including `message`, as a tool error in `tool_called` that the agent reads and continues past. Check `agent_failed` and error-status `tool_called` events before trusting a `quiet` or `failed` result.
