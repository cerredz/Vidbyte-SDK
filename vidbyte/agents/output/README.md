# Agent Outputs

This package decides what happens to an agent's finished reply after the run:
it owns the `OutputConnector` contract, the rule for which replies are
delivered, the default title and body shaping, and `OutputDispatcher`, which
sends one reply to every connector in `BaseAgent(outputs=[...])` or
`JevAgentSettings(outputs=...)`. The provider classes (Slack, email, GitHub,
and the rest) live lower down in [`vidbyte/lib/outputs/`](../../lib/outputs/README.md),
so they never import the agent layer; that README has the provider reference,
credentials, and limits.

## Non-Goals

- **No model-driven, MCP, or OAuth delivery.** Delivery runs in code after
  the run, never as a tool the model calls, and every destination takes one
  pasted credential.
- **No delivery from agents the SDK builds.** Forks, `as_tool()` children,
  MultiAgent workers, and Jev's internal agents never deliver.
  `CodexHarnessAgent`, `MultiAgent`, `AggregateAgent`, `Session.resume`,
  `Session.fork_from`, and YAML agent config take no `outputs`, and a
  user-built sub-agent's own `outputs` are neither stripped nor rejected.
- **No retries beyond HTTP 429.** There is no outbox, queue, or resend
  helper, and receipts are not saved in session checkpoints, because a
  duplicate post is worse than a reported failure.
- **No per-reply opt-out.** A `render` that returns anything but
  `OutputContent` fails that connector; it does not skip it.

## Modules

- `connector.py`: `OutputConnector`, the runtime-checkable protocol (a
  `destination`, an optional `render`, and an async `send`), and
  `OutputShaping`, the skip rule and the default title and body.
- `dispatcher.py`: `OutputDispatcher`, which validates an `outputs` argument
  and delivers one reply to every connector.
- `__init__.py`: the public names, re-exported from the `vidbyte` root except
  `OutputDispatcher`.

## When Delivery Runs

`BaseAgent._generate_reply` delivers once per run, after the reply passes the
output-schema check and has been recorded in history and the session, and
before any queued follow-up prompts run. An agent with no outputs skips the
step entirely and its reply has no `"deliveries"` key.

- **Skipped replies.** A blank reply, or a run stopped by a budget, guard, or
  middleware instead of an accepted answer, sends nothing; every receipt is
  SKIPPED. A reply with no stop reason, such as Jev's clarification stop, is
  delivered.
- **Shaping.** A connector's `render` builds its content when given.
  Otherwise the title and body come from the structured output's `title` and
  `body` fields, or from the reply text (its first line is the title), and the
  agent's name is the fallback title.
- **Concurrency and deadline.** Every connector sends at once, and each one
  has `OUTPUT_DELIVERY_DEADLINE_SECONDS` to finish; one that does not is
  FAILED `network` without holding back the others.
- **Receipts.** `reply.metadata["deliveries"]` holds one `DeliveryReceipt` per
  connector, in configured order.

## Forks And Sub-Agents

Agents the SDK builds never deliver: `fork()` passes `outputs=()`, so
`as_tool()` children, MultiAgent workers, and workflow
`AgentStage(fresh_fork=True)` runs post nothing, and Jev's bulk-work, clone,
swarm, and continuation agents are built without outputs.

A user-built agent that carries its own outputs delivers whenever it runs,
un-forked:

- as a Jev specialist, its delivery failure surfaces from the JevAgent as
  `AgentExecutionError` (with the `OutputDeliveryError` as its cause), and a
  successful delegation copies its `deliveries` into the JevAgent's reply;
- as an AggregateAgent proposer, a failed delivery makes it a failed proposer;
- as a pipeline stage, a workflow `AgentStage` without `fresh_fork`, or an
  MCP-served agent, it posts once per stage run or tool call.

## Failure Behavior

If any connector fails, `OutputDispatcher.deliver` waits for every other
connector, records all receipts, and then raises `OutputDeliveryError`. The
reply is already in `agent.history`, `agent.last_reply`, and the session; the
error carries it as `.reply`, all receipts as `.receipts`, and the failures as
`.failed`. Queued follow-up prompts from that run are dropped. Only HTTP 429
is retried. Running the agent again sends to every output again, so resend
only the failed ones:

```python
try:
    reply = await agent.arun("Scan checkout")
except OutputDeliveryError as err:
    failed = tuple(
        connector
        for connector, receipt in zip(agent.outputs, err.receipts, strict=True)
        if receipt.status is DeliveryStatus.FAILED
    )
    receipts = await OutputDispatcher.deliver(failed, err.reply, {})
```

A FAILED `network` receipt, and an email that passed the deadline, may
already have been delivered, so check that destination before resending it.
