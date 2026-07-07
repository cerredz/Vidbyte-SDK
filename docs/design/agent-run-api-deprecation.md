# Design Doc: Agent Run API Deprecation

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

This change makes the public Vidbyte agent execution examples and agent object API prefer `run()` over `arun()`. The public `BaseAgent` / `Agent` `arun()` methods will no longer execute agent runs; they will raise a clear deprecation error telling callers to use `run()` instead. Internal async SDK flows will call `generate_reply()` directly so they do not depend on the deprecated public alias.

---

## 2. Goals & Non-Goals

### Goals

- Make public `Agent` / `BaseAgent` usage run through `run()` instead of `arun()`.
- Change the public agent object's `arun()` method to raise a clear deprecation error message.
- Change the public agent object's sequential async alias, `arun_sequentially()`, to raise a clear deprecation error message for consistency.
- Update internal SDK code that currently calls public agent `arun()` to use `generate_reply()` instead.
- Update the main `README.md` and root `llms.txt` to document `run()` as the public execution method and to note that agent `arun()` is deprecated.

### Non-Goals

- No change to internal runtime methods named `arun()` under `vidbyte/agents/runtime.py`, runtime algorithms, provider runners, eval runners, pipelines, tools, or MCP server loops unless they are public agent-object aliases.
- No new session package or first-class session object will be created.
- No broad documentation sweep outside the main `README.md` and root `llms.txt`.
- No migration of async application examples to a new async public method beyond existing `generate_reply()` for internal SDK use.

---

## 3. Background & Context

The active repository is a Python SDK package (`pyproject.toml`) with public exports from `vidbyte/__init__.py`. `Agent` is an alias for `BaseAgent` in `vidbyte/agents/__init__.py`. `BaseAgent` currently has three relevant execution surfaces: `generate_reply()` as the async implementation method, `arun()` as an async ergonomic alias, and `run()` as a synchronous wrapper around `generate_reply()`.

The current `run()` implementation refuses to run inside an already running event loop and tells callers to use `await arun()`. If `arun()` becomes deprecated, this message must change so it no longer points callers to the deprecated method. Internal async SDK flows currently use public `arun()` in handoff generation, continual trace updates, and the context-minimal-fanout paradigm harness. These call sites need to move to `generate_reply()` so the public alias can fail without breaking SDK internals.

I did not find an active first-class `Session` class or `vidbyte/sessions` package in the current package tree. The only active "session" object found is `McpServerHandle`, described as a live MCP server connection session, and it has `close()`, `name`, and `tool_names`, not `run()` or `arun()`. There are untracked nested worktree directories under this checkout that contain a `vidbyte/sessions` package, but those are not part of the active package tree and should not be edited as part of this change.

---

## 4. Requirements

### Functional Requirements

1. Calling `BaseAgent.arun(...)` or `Agent.arun(...)` must raise `AgentExecutionError` with a message that says the function is deprecated and instructs the caller to use `run()` instead.
2. Calling `BaseAgent.arun_sequentially(...)` must raise `AgentExecutionError` with a message that says the function is deprecated and instructs the caller to use `run_sequentially()` instead.
3. Calling `BaseAgent.run(...)` from normal synchronous code must continue to execute the agent and return `AgentMessage`.
4. Calling `BaseAgent.run(...)` from inside an active event loop must raise `AgentExecutionError` without recommending `arun()`.
5. Calling `BaseAgent.run_sequentially(...)` from normal synchronous code must continue to execute prompts sequentially and return `list[AgentMessage]`.
6. Calling `BaseAgent.run_sequentially(...)` from inside an active event loop must raise `AgentExecutionError` without recommending `arun_sequentially()`.
7. Internal async SDK flows in `HandoffAgent`, `ContinualTraceAgent`, and `MultiplePromptFanoutHarness` must not call deprecated public agent `arun()` methods.
8. The main `README.md` must show agent examples using `run()` and mention that `arun()` is deprecated for public agent objects.
9. The root `llms.txt` must show agent examples using `run()` and mention that `arun()` is deprecated for public agent objects.

### Non-Functional Requirements

- Performance targets: N/A - this is a small API and documentation change with no intended runtime performance impact.
- Scalability considerations: N/A - no data structures or concurrency model changes.
- Security requirements: Do not alter tool permission, MCP, tracing, or provider behavior.
- Observability: Existing trace naming such as `agent.run` remains unchanged.
- Reliability / error tolerance: Deprecation errors must be deterministic and should not be swallowed by internal SDK flows.

---

## 5. High-Level Design

The public agent object will keep `run()` as the supported caller-facing execution method. `arun()` will remain present to avoid `AttributeError`, but its body will immediately raise `AgentExecutionError` with a deprecation message. This matches the user's request to "put an error message saying that this function is deprecated" while keeping the object shape discoverable.

Internal async code will continue using the existing async implementation method, `generate_reply()`. This avoids forcing async SDK internals to call sync `run()` inside an active event loop, which would fail by design. The result is a split between public compatibility aliases (`run()` supported, `arun()` deprecated) and internal async implementation (`generate_reply()` supported).

```text
Public caller
  -> agent.run(...)
      -> asyncio.run(agent.generate_reply(...))

Public caller
  -> await agent.arun(...)
      -> AgentExecutionError("BaseAgent.arun() is deprecated; use run() instead.")

Internal async SDK flow
  -> await agent.generate_reply(...)
```

The root README and LLM documentation bundle will be updated so public agent examples no longer recommend `await agent.arun(...)`.

---

## 6. Detailed Design

### 6.1 Public Agent Execution Alias

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

`BaseAgent` owns the public agent execution aliases. This change makes `arun()` and `arun_sequentially()` deprecated error surfaces, keeps `run()` and `run_sequentially()` working from synchronous code, and updates active-event-loop error messages.

#### Interface / API

```python
async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage:
    # Raises AgentExecutionError explaining that arun is deprecated and run should be used.

def run(self, message: str | AgentInput, **options: Any) -> AgentMessage:
    # Runs generate_reply from synchronous code.

async def arun_sequentially(self, prompts: Sequence[str | AgentInput], **options: Any) -> list[AgentMessage]:
    # Raises AgentExecutionError explaining that arun_sequentially is deprecated.

def run_sequentially(self, prompts: Sequence[str | AgentInput], **options: Any) -> list[AgentMessage]:
    # Runs a private sequential coroutine from synchronous code.
```

#### Logic / Algorithm

1. Replace `arun()` implementation with `raise AgentExecutionError("BaseAgent.arun() is deprecated; use run() instead.")`.
2. Update `run()` active-loop error to avoid telling callers to use `arun()`.
3. Replace `arun_sequentially()` implementation with `raise AgentExecutionError("BaseAgent.arun_sequentially() is deprecated; use run_sequentially() instead.")`.
4. Add or reuse a private async helper such as `_run_sequentially_async(...)` that contains the previous sequential loop over `generate_reply()`.
5. Change `run_sequentially()` to call that private helper with `asyncio.run(...)` from synchronous code.
6. Keep `generate_reply()` unchanged as the async implementation method.

#### Edge Cases & Error Handling

- Existing callers that still use `await agent.arun(...)` receive a direct SDK error rather than silently continuing.
- `run()` inside an active event loop still fails because nested `asyncio.run()` is invalid; the message should recommend calling `generate_reply()` only if the caller is already in SDK-internal async code, or phrase the error without recommending deprecated `arun()`.
- `run_sequentially()` must not call deprecated `arun_sequentially()`.

### 6.2 Handoff Agent Internal Call

**File(s):** `vidbyte/agents/handoff.py`
**Type:** Modified

#### What it does

`HandoffAgent.generate_handoff()` currently calls `await self.arun(source)`. It must call `await self.generate_reply(source)` so handoff generation still works after public `arun()` is deprecated.

#### Interface / API

```python
async def generate_handoff(self, source: str) -> Handoff:
    # Runs the handoff model through generate_reply and converts the output into a Handoff.
```

#### Logic / Algorithm

1. Replace `reply = await self.arun(source)` with `reply = await self.generate_reply(source)`.
2. Leave structured payload parsing and handoff filling unchanged.

#### Edge Cases & Error Handling

- Handoff failures continue to propagate through the existing `generate_handoff()` path.
- Automatic handoff generation from `BaseAgent._run_auto_handoff()` remains fail-open as currently implemented there.

### 6.3 Continual Trace Agent Internal Call

**File(s):** `vidbyte/agents/continual_trace.py`
**Type:** Modified

#### What it does

`ContinualTraceAgent.update()` currently calls `await self.arun(...)`. It must call `await self.generate_reply(...)` so fail-open trace updates still work after public `arun()` is deprecated.

#### Interface / API

```python
async def update(self, *, context_window: str, runtime_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    # Runs one trace update through generate_reply and returns the current trace artifact.
```

#### Logic / Algorithm

1. Build the trace update prompt as before.
2. Replace `await self.arun(...)` with `await self.generate_reply(...)`.
3. Preserve existing exception capture into `self.last_error`.

#### Edge Cases & Error Handling

- Trace update failures remain fail-open and return the current trace artifact.
- The deprecation error for public `arun()` must not be captured as a trace update failure because this internal path no longer calls it.

### 6.4 Context Minimal Fanout Internal Agent Calls

**File(s):** `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/harness.py`
**Type:** Modified

#### What it does

The fanout harness is async internally and currently awaits public agent `arun()` for splitter and implementation agents. Those call sites must use `generate_reply()` instead.

#### Interface / API

```python
async def _run_splitter(self, prompt: str, settings: MultiplePromptFanoutSettings) -> PromptSplitPlan:
    # Runs the splitter agent through generate_reply and parses the JSON plan.

async def _run_one_implementation_prompt(self, split_prompt: SplitPrompt, plan: PromptSplitPlan, settings: MultiplePromptFanoutSettings) -> ImplementationOutput:
    # Runs one implementation agent through generate_reply and normalizes the output.
```

#### Logic / Algorithm

1. Replace `reply = await splitter.arun(message)` with `reply = await splitter.generate_reply(message)`.
2. Replace `reply = await agent.arun(message)` with `reply = await agent.generate_reply(message)`.
3. Keep concurrency, plan validation, and exception behavior unchanged.

#### Edge Cases & Error Handling

- The harness still has its own `arun()` method inherited from `ParadigmHarness`; this design intentionally does not deprecate paradigm harness `arun()` because the user asked for agent/session objects and because root docs show harness `arun()` separately.
- If public harness deprecation is desired too, that should be a separate explicit scope expansion.

### 6.5 Main README Updates

**File(s):** `README.md`
**Type:** Modified

#### What it does

The root README will document `run()` as the public agent execution method and note that agent `arun()` is deprecated.

#### Interface / API

```python
reply = agent.run("Draft a concise release note")
```

#### Logic / Algorithm

1. Update "Agents and Modalities" text from "run() and arun()" to "run()".
2. Add a short deprecation note for public agent objects.
3. Convert root README public agent examples from `await agent.arun(...)` to `agent.run(...)`.
4. Leave non-agent async examples such as MCP server `await server.run()` and paradigm/eval runner examples unchanged unless they explicitly describe public agent objects.

#### Edge Cases & Error Handling

- Do not rewrite unrelated `run` words or internal MCP server examples.
- Keep examples syntactically coherent after removing `await`.

### 6.6 LLM Documentation Bundle Updates

**File(s):** `llms.txt`
**Type:** Modified

#### What it does

The root LLM documentation bundle will mirror the README guidance so downstream LLMs learn `run()` as the public agent-object execution method.

#### Interface / API

```python
reply = agent.run("Draft a concise release note")
```

#### Logic / Algorithm

1. Update the core mental model and "How To Install And Use" sections to say public agents use `run()`.
2. Add a short warning that public agent `arun()` is deprecated and raises an error.
3. Convert public agent examples from `await agent.arun(...)` to `agent.run(...)`.
4. Leave non-agent async examples such as `await server.run()` unchanged.

#### Edge Cases & Error Handling

- Avoid changing MCP protocol language around `studio.agents.run`, which is unrelated and should remain.
- Avoid changing lower-level internal APIs that are not public agent-object examples.

---

## 7. Data Model Changes

### 7.1 Data Models

**Change type:** N/A - no persisted schemas, dataclasses, or storage models change.

```text
N/A
```

**Migration strategy:** N/A - no persisted data migration.

- Forward migration: N/A.
- Rollback plan: Revert the code and documentation changes.

---

## 8. API Changes

### 8.1 Public Agent Object Execution Methods

**Change type:** Deprecated

**Request:**

```json
{
  "method": "BaseAgent.arun",
  "message": "str | AgentInput",
  "options": "keyword arguments"
}
```

**Response:**

```json
{
  "raises": "AgentExecutionError",
  "message": "BaseAgent.arun() is deprecated; use run() instead."
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python method raises `AgentExecutionError` for all public `arun()` calls |

### 8.2 Public Agent Sequential Async Alias

**Change type:** Deprecated

**Request:**

```json
{
  "method": "BaseAgent.arun_sequentially",
  "prompts": "Sequence[str | AgentInput]",
  "options": "keyword arguments"
}
```

**Response:**

```json
{
  "raises": "AgentExecutionError",
  "message": "BaseAgent.arun_sequentially() is deprecated; use run_sequentially() instead."
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python method raises `AgentExecutionError` for all public `arun_sequentially()` calls |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-run-api-deprecation.md` | Design doc for the requested API/docs change |
| MODIFY | `vidbyte/agents/base.py` | Deprecate public agent `arun()` aliases, keep `run()`/`run_sequentially()` working, and update error messages |
| MODIFY | `vidbyte/agents/handoff.py` | Replace internal public `arun()` call with `generate_reply()` |
| MODIFY | `vidbyte/agents/continual_trace.py` | Replace internal public `arun()` call with `generate_reply()` |
| MODIFY | `vidbyte/paradigms/context_minimal_fanout/multiple_prompts/harness.py` | Replace internal public agent `arun()` calls with `generate_reply()` |
| MODIFY | `README.md` | Document `run()` as public agent execution and note `arun()` deprecation |
| MODIFY | `llms.txt` | Mirror README guidance for LLM-facing documentation |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| N/A | N/A | No new dependencies or external services | N/A |

---

## 11. Rollout & Deployment

- Feature flags: None.
- Breaking change: Yes for callers using public `await agent.arun(...)`; they will receive a deprecation error and must move to `agent.run(...)` from synchronous code.
- Migration path: Public examples will use `agent.run(...)`. Async internal SDK code uses `generate_reply(...)`; external async applications that cannot call sync `run()` inside an event loop will need guidance if a public async replacement should remain supported.
- Deployment order: Single SDK code/docs change.
- Rollback procedure: Restore `arun()` and `arun_sequentially()` implementations, restore active-loop error messages, and revert docs examples.

---

## 12. Open Questions

- [ ] The active package tree does not contain a first-class `Session` object with `run()` / `arun()`. Did "session object" refer to an unmerged `vidbyte/sessions` package in another branch, an MCP connection session, or only agent conversation state?
- [ ] Should public async agent callers have a supported replacement such as `generate_reply()` documented, or should the public API intentionally be sync-only for agents after this change?
- [ ] Should this deprecation also apply to paradigm harnesses, eval runners, provider runners, tools, or internal runtime classes that have methods named `arun()`? This design assumes no because the request named session and agent objects and asked only for main README plus `llms.txt`.

---

## 13. Alternatives Considered

### Alternative 1: Keep `arun()` Working And Only Update Docs

- What: Leave public `arun()` as a working alias and only change README/LLM examples to `run()`.
- Why rejected: The user explicitly asked for the `arun` methods to emit an error saying the function is deprecated.

### Alternative 2: Make `run()` Async And Awaitable

- What: Rename the async public behavior from `arun()` to `run()` and require `await agent.run(...)`.
- Why rejected: Current `run()` is synchronous across agents and many runner-like objects. Changing it to async would be a larger breaking change and would contradict existing examples that use `reply = image_agent.run(...)`.

### Alternative 3: Deprecate Every Method Named `arun()` In The Repository

- What: Change all runtime, runner, tool, paradigm, eval, and provider `arun()` methods to errors.
- Why rejected: Many `arun()` methods are internal contracts or non-agent public APIs. Changing them would greatly expand the blast radius beyond "session and agent objects" and break async runtime internals.

