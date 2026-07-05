# Forking and Resuming Agent Threads

Use this skill when you need to branch, time-travel, or incorporate another agent's thread into the current one using Vidbyte durable sessions.

Forking and resuming are queries over a session's checkpoint DAG. Every `Checkpoint` carries `(id, session_id, parent_id, seq, run_state, trace_*)`, so branching, time-travel, and cross-thread incorporation are all first-class. See [sessions.md](./sessions.md) for the attach/store/verb baseline.

## Fork — branch without touching the parent

```python
from vidbyte import Session, FileSessionStore

store = FileSessionStore("./.vidbyte/sessions")

# branch from the current head (default) or any checkpoint
branch = session.fork(at=None, tools=[grep], runner=my_runner)
print(branch.id, branch.agent)                   # new se_… id; parent lineage recorded

await branch.arun("take the branch in a different direction")
# session's own head/history is unchanged
```

Or fork from any checkpoint in the store directly (no live parent session needed):

```python
branch = Session.fork_from(store, "ck_abc123", tools=[grep], runner=my_runner, tags=["exploration"])
```

The fork records `parent_session_id` on its metadata — first-class lineage for subagent flows. Mutating the fork never alters the parent's stored state.

## Rewind — time-travel the head

```python
earlier = store.history(session.id)[0].id
session.rewind(to=earlier)                       # head moves back; next run branches from here
await session.arun("redo from the earlier point")
```

`rewind` validates that the target belongs to this session — rewinding to a foreign checkpoint raises `SessionError`.

## Edit — transform history, save as a new checkpoint

```python
# drop the last turn, or redact, or inject a what-if message
session.edit(lambda history: history[:-1], label="dropped-last-turn")

def redact(messages):
    return [{**m, "content": m["content"].replace(secret, "***")} if "content" in m else m
            for m in messages]

session.edit(redact, label="redacted")
```

The original checkpoint is retained; `edit` writes a new one with the transformed history.

## Cross-thread resume — three modes

When one agent should pick up another agent's work, choose the mode by how much of the other thread you want to incorporate. All three are prebuilt tools under `vidbyte.tools.builtins.sessions` and are also available as `Session` methods.

### Replace — override the current context window entirely

`ResumeReplaceTool` / `Session.adopt(checkpoint_id)`: load another session's checkpoint, replace the bound agent's history with it, and write a new checkpoint. Use when the agent should continue AS the other thread.

```python
new_head = session.adopt("ck_other")             # current context is now the other thread's
```

For own-thread, `ResumeReplaceTool` with no `session_id` is equivalent to `rewind` (time-travel to an earlier checkpoint).

### Append — keep current context, add the other thread's context window

`ResumeAppendTool` / `Session.append_context(checkpoint_id)`: append the other session's history as a single framed `<resumed_thread>` block after the current history. Use when the agent needs both its own context AND the other thread's full trajectory.

```python
new_head = session.append_context("ck_other")    # current history + framed other thread
```

### Output — append only the other thread's final answer

`ResumeOutputTool` / `Session.append_output(session_id)`: append only the other agent's last assistant message, framed as `<resumed_output>`. The target session MUST be `COMPLETED` — an unfinished thread raises `SessionError` so partial work is never silently incorporated.

```python
other_session.complete()                         # mark the producer finished
new_head = session.append_output(other_session.id)
```

## Cross-agent access — SessionScope

By default a session tool can only read sessions it created or is bound to. To let one agent resume another agent's thread, grant access explicitly:

```python
from vidbyte import SessionScope

# a fixed allowlist of session ids the tool may read
scope = SessionScope.sessions(["se_alice", "se_bob"])
# or grow the allowlist at runtime
tool._scope.allow(other_session.id)
# or an unrestricted scope (use with caution)
SessionScope.all_runs()
```

Out-of-scope operations return a denied `ToolResult`, not an exception. This is the foundation for subagent "checkpoint before launching, return after" flows.

## Patterns

- **Subagent checkpoint/return**: before launching a child agent, the parent checkpoints its own session; the child runs to completion and marks its session `COMPLETED`; the parent uses `ResumeOutputTool` to fold the child's final output back into its context.
- **What-if exploration**: `fork` from a shared checkpoint, run divergent prompts on each branch, compare results — the parent branch is never mutated.
- **Redaction before sharing**: `edit` to scrub secrets, then `fork` the redacted checkpoint into a shareable session.
- **Cold-process resume**: persist with `FileSessionStore` (or a DB store), then in a new Python process `Session.resume(store, session_id, tools=, runner=)` and continue with full history.
