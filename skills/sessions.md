# Durable Sessions

Use this skill when making a Vidbyte agent persistent — saving its conversation to disk or a database and continuing, resuming, or forking it later, across processes.

Durable sessions add a harness-level primitive that wraps any agent in a `Session` and persists its run state as an append-only checkpoint DAG. The agent stays pure; persistence lives in the `Session` wrapper, so it works for every runtime (linear, MCTS, actor). All session logic lives under `vidbyte/sessions/`; database-backed stores live under `vidbyte/lib/providers/`.

## Attach in one line

```python
from vidbyte import Agent, Session

agent = Agent(name="researcher", system_prompt="Investigate carefully.", provider="openai", model_name="gpt-4.1")
session = Session(agent)                 # defaults to InMemorySessionStore
reply = await session.arun("Investigate the failing test")
print(session.id, session.head)         # se_…  ck_…
```

Agents also expose the same entry point natively:

```python
session = agent.persist(store=store)
reply = await agent.arun("Investigate the failing test")
print(agent.session is session)          # True
```

`agent.persist(...)` delegates to `Session(agent, ...)`; it does not move persistence into the agent constructor. Once bound, `agent.arun(...)`, `agent.run(...)`, `session.arun(...)`, and `session.run(...)` all record one checkpoint per turn under the same policy. `sdk.harnesses.sessions.attach(agent, store=...)` is the namespace-client equivalent.

## Stores

| Store | Import | Notes |
|-------|--------|-------|
| `InMemorySessionStore` | `vidbyte.sessions` | default; ephemeral |
| `FileSessionStore(root=...)` | `vidbyte.sessions` | atomic JSON, one dir per session |
| `SqliteSessionStore(path=...)` | `vidbyte.lib.providers` | stdlib sqlite3 — no driver to install |
| `PostgresSessionStore(dsn=...)` | `vidbyte.lib.providers` | needs `psycopg` |
| `MongoDbSessionStore(uri=...)` | `vidbyte.lib.providers` | needs `pymongo` |
| `SupabaseSessionStore(url=, key=)` | `vidbyte.lib.providers` | needs `supabase` |

All implement one `SessionStore` protocol and are interchangeable. Database stores import their driver lazily and raise `ConfigurationError` when the driver is missing — importing `vidbyte` never pulls a DB driver (except SQLite, which is stdlib).

## The verbs

```python
from vidbyte import Session, FileSessionStore

store = FileSessionStore("./.vidbyte/sessions")
session = Session(agent, store=store)
await session.arun("step one")

# resume / continue / fork re-supply non-serializable parts (rehydration contract)
session = Session.resume(store, session_id, tools=[grep], runner=my_runner)
session = Session.continue_(store, session_id, runner=my_runner)      # resume head
branch  = Session.fork_from(store, checkpoint_id, runner=my_runner)   # new id + lineage

session.rewind(to=checkpoint_id)                 # time-travel the head
session.edit(lambda history: history[:-1])       # state editing -> new checkpoint
cid = session.checkpoint(label="milestone")      # manual checkpoint
session.complete()                               # mark COMPLETED
```

`CheckpointPolicy.PER_TURN` (default) writes a checkpoint after each run, including direct `agent.arun(...)` calls after the agent is bound to a session. `MANUAL` writes only on `checkpoint()`. Persistence is fail-open: a store write failure is recorded in `reply.metadata["__session_error__"]` and never ends the run.

## Trace capture

A session reads the agent's trace settings and persists the continual-trace artifact onto each checkpoint. Control with `trace=`:

- `TraceCapture.AUTO` (default) — capture when the agent has tracing enabled.
- `TraceCapture.OFF` — never capture.
- `TraceCapture.ARTIFACT` — always capture the artifact.
- `TraceCapture.FULL` — artifact plus raw span events.

Trace is a derived observation stored on the checkpoint; it never feeds `resume`, which always restores raw history as source of truth.

## Prebuilt agent-facing tools

Hand an agent ready-made tools to checkpoint, fork, rewind, and resume its own or another agent's thread. `Session` auto-binds any of these found on the wrapped agent; access is gated by `SessionScope` (own runs by default).

```python
from vidbyte import Agent, Session, FileSessionStore, SessionScope
from vidbyte.tools.builtins import (
    CheckpointTool, ForkTool, RewindTool,
    ResumeReplaceTool, ResumeAppendTool, ResumeOutputTool, SessionTool,
)

store = FileSessionStore("./.vidbyte/sessions")
agent = Agent(name="researcher", system_prompt="...", provider="openai", model_name="gpt-4.1",
              tools=[CheckpointTool(store), ForkTool(store), RewindTool(store),
                     ResumeReplaceTool(store), ResumeAppendTool(store), ResumeOutputTool(store),
                     SessionTool(store)])
session = Session(agent, store=store)   # auto-binds the tools
```

- `CheckpointTool` — snapshot the current thread (or copy an in-scope session's head as a labeled checkpoint).
- `ForkTool` — branch a new session from the current head or any in-scope checkpoint.
- `RewindTool` — time-travel the current session's head to an earlier checkpoint.
- `ResumeReplaceTool` — replace the current context window with another agent's thread state (own-thread: rewind).
- `ResumeAppendTool` — append another agent's full context window into the current one (history preserved).
- `ResumeOutputTool` — append only another agent's final output; errors if that thread is not `COMPLETED`.
- `SessionTool` — central combined tool: `create_checkpoint` / `fork_current` / `list_my_runs` / `read_run`.

## Rules of thumb

- The agent's state seam is `BaseAgent.export_state()` / `BaseAgent.restore(state, *, tools, runner, middleware)` - pure, no I/O. `agent.persist()` and `agent.session` are entry points into the external `Session` wrapper.
- Persist raw history; re-supply tools/runner/middleware at resume.
- Never persist secrets; the serializer scrubs credential-like keys and `api_key`.
- Remote/DB stores are adapters behind `SessionStore`; add new ones under `vidbyte/lib/providers/`.
- For fork/resume/time-travel patterns, see [forking.md](./forking.md).
