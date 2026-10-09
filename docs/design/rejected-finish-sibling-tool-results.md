# Answer Tool Calls Skipped by a Turned-Down Finish

## Summary

When one assistant turn holds several tool calls and `isDone` is not the last one (normal for parallel tool calling), a turned-down finish attempt (output-contract rejection or a specialized-runtime continuation such as Jev's) breaks out of the turn's tool-call loop. The calls after `isDone` never get a tool-result message, so the next request carries an assistant turn with unanswered `tool_call` ids, and OpenAI-compatible chat APIs and Anthropic reject it with HTTP 400. The fix answers every remaining call of that turn with a short error tool result, without running it. The continuation path had the same gap for the `isDone` call itself (even when it is the only call), so it is answered too.

## Flow chart

```mermaid
flowchart TD
    A[Assistant turn: isDone, search] --> B[Process isDone]
    B --> C{Finish accepted?}
    C -- yes --> D[Finish run]
    C -- contract rejected --> E[Append rejection feedback for isDone]
    E --> F[Append 'not executed' result for search]
    C -- finish attempt evaluated --> G[Append 'not accepted' result for isDone, then 'not executed' for search]
    G --> H{Continuation continues?}
    H -- no --> D
    H -- yes --> I[Continuation appends its messages]
    F --> J[Next model request: every tool_call id answered]
    I --> J
```

## Usage example

```python
from vidbyte import Agent
from vidbyte.agents import AgentLoopSettings, MinToolCalls

agent = Agent(
    name="worker",
    system_prompt="Work.",
    tools=[search],
    agent_loop_settings=AgentLoopSettings(output_contracts=[MinToolCalls(2)]),
)
# If the model returns [isDone(...), search(q="a")] in one turn and the contract
# rejects the finish, `search` is not run; the model instead sees a tool result
# "tool call not executed: ... call it again if it is still needed" and the run continues.
agent.run("task")
```

## How it works

- `AgentRuntime` loop in `vidbyte/agents/runtime.py` iterates the turn's calls with `enumerate`.
- A small helper `_answer_skipped_tool_calls` appends a `ToolResult.error(...)` (metadata `error: not_executed`) through the existing `_append_tool_result_message` for each call after `isDone`.
- Contract rejection: called right after the rejection feedback, before `break`.
- Continuation: the `isDone` call gets a `finish_not_accepted` error result, then the skipped calls are answered, all before `_continue_finish_attempt`, so the results sit directly after the turn's other tool results and before any continuation message. If the run then finishes, the extra messages are unused.
- Unchanged: `isDone` last in the turn, accepted finishes, and the skipped tools are never executed.

## Files

- `vidbyte/agents/runtime.py` - helper plus two call sites.
- `tests/test_agent_tool_loop.py` - regression tests for the contract-rejection path and the continuation path (patched `_continue_finish_attempt`).

## Risks

- Low. Only adds tool-result messages for ids that previously had none. The continuation test patches `_continue_finish_attempt` the way `JevDoneContinuation` behaves rather than running a full `JevAgent`.

## Verification

- New test fails on `main` (only one tool message after the assistant turn) and passes with the fix.
- `python scripts/run_ci.py --stage source` locally, then PR CI.
