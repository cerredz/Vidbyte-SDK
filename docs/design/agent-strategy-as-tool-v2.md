# Design Doc: Agent and Strategy as Tool (v2)

**Status:** Approved
**Author:** Claude
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

Adds `as_tool()` methods to `BaseAgent` and `BaseStrategy` that return zero-parameter `BaseTool` subclasses (`AgentTool` and `StrategyTool`). When the LLM invokes the tool, the parent agent's live conversation context is automatically serialized and forwarded to the wrapped agent or strategy, enabling agent-to-agent delegation without manual prompt construction.

---

## 2. Goals & Non-Goals

### Goals
- `BaseAgent.as_tool()` returns an `AgentTool` with a rich description derived from the agent's config
- `BaseStrategy.as_tool(agent)` returns a `StrategyTool` wrapping the agent's strategy
- Both tools expose **zero LLM-facing parameters** — the parent's context is injected automatically
- The tool description (in the parent's context window) documents what the child agent does and when to use it
- When called, the parent's history + active prompt are serialized and passed to the child agent via `fork().generate_reply()`
- History isolation: each invocation forks the child agent so parent history is not polluted
- Works naturally when passed into the `tools=` array at agent construction or via `add_tool()`

### Non-Goals
- No harness `as_tool()` (out of scope for this PR)
- No streaming or multi-turn sub-agent sessions
- No cross-process or network agent delegation

---

## 3. Background & Context

PR #30 introduced `as_tool()` with `{message, recipient, modality}` as explicit LLM-facing parameters. The user revised the design: the LLM should not have to craft a message — the current conversation context is the message. This v2 supersedes PR #30.

---

## 4. Requirements

### Functional Requirements
1. `AgentTool.spec()` returns a `ToolSpec` with zero parameters
2. `AgentTool` description encodes the agent name, description, capabilities, and usage hint
3. `AgentTool.execute()` reads the parent context via a bound getter, serializes it, and calls `agent.fork().generate_reply(serialized)`
4. `StrategyTool` raises `AgentExecutionError` at construction when `agent.strategy is None`
5. `StrategyTool.execute()` returns `ToolResult.error` if agent has no real runner (`ConfiguredAgentRunner` or `None`)
6. `StrategyTool.execute()` calls `strategy.arun(serialized, runner=runner, tools=agent._agent_tool_items)`
7. `BaseAgent.add_tool()` and construction-time tools both bind the context getter for `AgentTool`/`StrategyTool`
8. `BaseAgent._active_prompt` tracks the in-flight prompt during `generate_reply()`
9. `BaseStrategy.description` class variable defaults to `""`

### Non-Functional Requirements
- No circular imports: `agent_tool.py`/`strategy_tool.py` use `TYPE_CHECKING` guards for `BaseAgent`
- Context getter uses a lazy lambda — no snapshot at bind time
- Errors in child agent execution are caught and returned as `ToolResult.error`

---

## 5. High-Level Design

A parent agent is given a child agent via `child.as_tool()` or `StrategyTool(child_agent)`. The tool's description serves as context injection — the LLM sees a description like "Agent: summarizer — summarizes documents. Use this to delegate summarization tasks." When the LLM calls the tool (with empty arguments `{}`), `AgentTool.execute()` fires a context getter lambda that reads the parent's live `_active_prompt` and `history`, serializes them into an XML-tagged string, forks the child agent, and calls `generate_reply()` with the serialized context.

```
Parent agent run loop
  │
  ├─ tool call: child_agent_name({})
  │
  └─ AgentTool.execute()
       ├─ context_getter() → (active_prompt, history)
       ├─ serialize_context(...)
       └─ child.fork().generate_reply(serialized)
            └─ returns reply → ToolResult.success(reply.content)
```

---

## 6. Detailed Design

### 6.1 `vidbyte/tools/agent_tool.py` (New)

**Type:** New file

#### What it does
Wraps a `BaseAgent` as a zero-parameter `BaseTool`. Serializes parent context on execute.

#### Interface
```python
class AgentTool(BaseTool):
    def __init__(self, agent, *, name=None, description=None): ...
    def bind_context_getter(self, getter: Callable[[], tuple[str, list]]): ...
    def spec(self) -> ToolSpec: ...  # zero parameters
    async def execute(self, call: ToolCall) -> ToolResult: ...

def serialize_context(active_prompt: str, history: list[AgentMessage]) -> str: ...
```

### 6.2 `vidbyte/tools/strategy_tool.py` (New)

**Type:** New file

#### What it does
Wraps an agent's strategy as a zero-parameter tool. Raises at init if strategy is absent.

#### Interface
```python
class StrategyTool(BaseTool):
    def __init__(self, agent, *, name=None, description=None): ...  # raises if no strategy
    def bind_context_getter(self, getter: Callable[[], tuple[str, list]]): ...
    def spec(self) -> ToolSpec: ...  # zero parameters
    async def execute(self, call: ToolCall) -> ToolResult: ...
```

### 6.3 `vidbyte/strategies/base.py` (Modified)

Add `description: ClassVar[str] = ""` and `as_tool(agent, *, name, description)` method.

### 6.4 `vidbyte/agents/base.py` (Modified)

- Add `_active_prompt: str = ""` instance variable
- Add `_bind_agent_tool_context(tool)` — binds lambda to `AgentTool`/`StrategyTool`
- Update `add_tool()` to call `_bind_agent_tool_context(tool)` after adding
- In `__init__`, iterate tools and call `_bind_agent_tool_context` for each
- Set `self._active_prompt = prompt` after `_normalize_input` in `generate_reply()`; clear on exit
- Add `as_tool(*, name, description) -> AgentTool` method

### 6.5 `vidbyte/tools/__init__.py` (Modified)

Export `AgentTool` and `StrategyTool`.

---

## 7. Data Model Changes

N/A — no schema changes.

---

## 8. API Changes

N/A — no HTTP endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-strategy-as-tool-v2.md` | Design doc |
| CREATE | `vidbyte/tools/agent_tool.py` | AgentTool implementation |
| CREATE | `vidbyte/tools/strategy_tool.py` | StrategyTool implementation |
| MODIFY | `vidbyte/strategies/base.py` | Add description ClassVar + as_tool() |
| MODIFY | `vidbyte/agents/base.py` | Add _active_prompt, _bind_agent_tool_context, as_tool() |
| MODIFY | `vidbyte/tools/__init__.py` | Export AgentTool and StrategyTool |
| CREATE | `tests/test_agent_tool.py` | Unit tests for AgentTool |
| CREATE | `tests/test_strategy_tool.py` | Unit tests for StrategyTool |

---

## 10. Testing Plan

### Unit Tests
- `AgentTool`: spec has zero params, name/description defaults and overrides, permission, execute success, execute error, history isolation, metadata, as_tool() method, context getter binding
- `StrategyTool`: init raises without strategy, spec has zero params, name/description defaults and overrides, permission, metadata, execute returns strategy output, execute error on strategy failure, execute error on no real runner, as_tool() method, description ClassVar

---

## 11. Dependencies & External Services

N/A — all in-process.

---

## 12. Rollout & Deployment

No feature flags. No breaking changes. New optional methods on existing public classes.

---

## 13. Open Questions

None.

---

## 14. Alternatives Considered

### Alternative: Explicit message parameter (PR #30 design)
- What: LLM specifies message, recipient, modality explicitly
- Why rejected: Forces the LLM to re-state what is already in the context window; context injection is more natural for agent-to-agent delegation
