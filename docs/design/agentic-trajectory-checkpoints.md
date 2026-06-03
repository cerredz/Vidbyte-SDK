# Design Doc: Agentic Trajectory Checkpoints

**Status:** Draft
**Author:** Antigravity
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

---

## 1. Overview

This feature introduces a model-based / agentic mode for generating trajectory checkpoints in `vidbyte-sdk`. Instead of computing summaries, trajectory descriptions, heuristic scores, and guidance feedback deterministically via hardcoded Python rules, the algorithm will dynamically call an LLM (using the main agent's runner and provider) to synthesize this information from the agent's current context window (conversation history and tool call outcomes). This provides the agent with high-quality, semantically rich checkpoints that capture nuanced progress, identify roadblocks, and offer context-aware guidance during the main execution loop.

---

## 2. Goals & Non-Goals

### Goals

- Support a new configurable mode (`deterministic` vs. `agentic`) on `TrajectoryCheckpointAlgorithm`.
- Define a new system prompt asset for the summarizer model inside `vidbyte/prompts/prompts/trajectory_checkpoints.json` and register it in the `Prompt` enum.
- Update `InnerContextWindowAlgorithm.after_tool_calls` and the inner-loop execution dispatch hook in `AgentRuntime` to be asynchronous (`async def`) so they can perform model calls.
- Pass the main agent's current conversation history (messages) and system prompt to the summarizer model.
- Parse the structured JSON response from the summarizer to instantiate a `TrajectoryCheckpointContextItem`.
- Provide a fallback to the deterministic heuristic generation if the summarizer model call fails (due to API errors, JSON parsing errors, etc.).
- Add unit and integration tests verifying the agentic trajectory generation flow using fake runners/providers.

### Non-Goals

- Replacing the deterministic mode. The deterministic mode remains the default to avoid unexpected token costs and loop latency for users who do not opt-in.
- Adding interactive user authorization/middleware gates to the summarizing model calls.
- Designing a separate billing/cost budget specifically for summary calls (they will count towards the run's overall token usage/budget).

---

## 3. Background & Context

- Currently, trajectory checkpoints are generated entirely deterministically in Python using the `AgentIterationSnapshot`.
- While this is fast and incurs no token cost, the generated checkpoint lacks semantic depth. The score is a simple ratio of successful tool calls, and the feedback is a set of hardcoded fallback strings.
- By introducing an LLM call to synthesize the checkpoint, the agent can receive a much more informative self-reflective context.
- However, since model calls in Vidbyte SDK are asynchronous (requiring `await`), the currently synchronous `InnerContextWindowAlgorithm` lifecycle hook `after_tool_calls` must be updated to be asynchronous.

---

## 4. Requirements

### Functional Requirements

1. **Configurable Mode**: `TrajectoryCheckpointAlgorithm` must accept a `mode` parameter (value: `"deterministic"` or `"agentic"`, default: `"deterministic"`).
2. **Asynchronous Lifecycle Hook**: `InnerContextWindowAlgorithm.after_tool_calls` must be an `async def` method.
3. **Async Runtime Hook**: `AgentRuntime._run_inner_context_window_hook` must be asynchronous and awaited inside `AgentRuntime._arun_once(...)`.
4. **Prompt Asset**: A new prompt asset must be defined in `vidbyte/prompts/prompts/trajectory_checkpoints.json` and registered under `Prompt.TRAJECTORY_CHECKPOINTS_AGENTIC_SUMMARIZER`.
5. **Run Context Extension**: `ContextWindowRunContext` must carry the active `runner`, `provider`, `invoke_runner`, `runner_output_text`, `runner_output_metadata`, and `messages` (history) from `AgentRuntime` to allow the algorithm to call the model.
6. **Structured LLM Prompting**: The agentic summarizer prompt must instruct the model to return a JSON object with:
   - `reasoning_summary` (string)
   - `trajectory` (string)
   - `output` (string)
   - `score` (float between 0.0 and 1.0)
   - `feedback` (string)
7. **Robust Parsing & Fallback**: If the summarizer model call fails or returns invalid JSON, the algorithm must log/trace the error and fall back to generating a deterministic heuristic-based checkpoint so the run does not crash.

### Non-Functional Requirements

- **Performance**: Agentic mode will add blocking network latency (one LLM call per checkpoint interval).
- **Security**: The summary model call must not expose sensitive internal prompts/keys beyond the configured runner and provider.
- **Reliability**: Normal execution loops must remain fully backward-compatible when using deterministic mode.

---

## 5. High-Level Design

We will modify the `InnerContextWindowAlgorithm` class so that its primary lifecycle hook `after_tool_calls` becomes asynchronous. In `AgentRuntime._arun_once`, when the checkpoint cadence is reached, we will invoke the hook with `await`.

Inside the hook, if `mode == "agentic"`, we will build a prompt containing the main agent's system prompt and the messages history. We will then invoke `invoke_runner` using the main agent's runner and provider to request a structured JSON synthesis. Once returned, the JSON is parsed and mapped into `TrajectoryCheckpointContextItem`, which is then placed in the context manager.

```text
AgentRuntime._arun_once(...)
    -> iteration completes, calls: await _run_inner_context_window_hook(...)
        -> TrajectoryCheckpointAlgorithm.after_tool_calls(ctx)
            -> If mode == "agentic":
                -> Load Prompt.TRAJECTORY_CHECKPOINTS_AGENTIC_SUMMARIZER
                -> Format prompt with main agent's system prompt and messages
                -> await invoke_runner(...) to get structured synthesis
                -> Parse JSON and construct TrajectoryCheckpointContextItem
            -> If mode == "deterministic" or failure occurs:
                -> Fall back to heuristic calculation
            -> Place item in context manager
```

---

## 6. Detailed Design

### 6.1 `Prompt` enum
**File(s):** `vidbyte/lib/enums/prompts.py`  
**Type:** Modified  

#### Interface / API
Add new enum member:
```python
class Prompt(str, Enum):
    ...
    TRAJECTORY_CHECKPOINTS_AGENTIC_SUMMARIZER = "trajectory_checkpoints.agentic_summarizer"
```

---

### 6.2 Prompt Asset File
**File(s):** `vidbyte/prompts/prompts/trajectory_checkpoints.json`  
**Type:** New file  

#### Content
```json
{
  "name": "Trajectory Checkpoints",
  "description": "Prompts used to generate agentic trajectory checkpoints.",
  "key": "trajectory_checkpoints",
  "prompts": {
    "agentic_summarizer": "You are a trajectory checkpoints generator. Analyze the following agent context window containing the system prompt and conversation history (including tool calls and outcomes). Synthesize a concise trajectory checkpoint summarizing: reasoning summary of the progress, a compact trajectory outline, latest output/state of the task, a score (0.0 to 1.0) assessing overall success/confidence, and concrete feedback/guidance for next steps. Output only a valid JSON object matching this structure:\n{{\n  \"reasoning_summary\": \"string\",\n  \"trajectory\": \"string\",\n  \"output\": \"string\",\n  \"score\": float,\n  \"feedback\": \"string\"\n}}\n\nMain Agent System Prompt:\n{main_system_prompt}\n\nMain Agent Conversation History:\n{conversation_history}"
  }
}
```

---

### 6.3 `ContextWindowRunContext`
**File(s):** `vidbyte/context/runtime.py`  
**Type:** Modified  

#### Interface / API
Add runtime dependencies to the dataclass:
```python
@dataclass(slots=True)
class ContextWindowRunContext:
    context_manager: ContextManager
    recorder: RecorderBase
    state: dict[str, Any]
    iteration: AgentIterationSnapshot | None = None
    # New fields:
    runner: object | None = None
    provider: str | None = None
    invoke_runner: Callable[..., Any] | None = None
    runner_output_text: Callable[[object], str] | None = None
    runner_output_metadata: Callable[[object], Mapping[str, Any]] | None = None
    options: Mapping[str, Any] | None = None
    messages: Sequence[dict[str, Any]] | None = None
    system_prompt: str | None = None
```

Update `InnerContextWindowAlgorithm`:
```python
class InnerContextWindowAlgorithm:
    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        # Now async def
        del ctx
```

---

### 6.4 `AgentRuntime`
**File(s):** `vidbyte/agents/runtime.py`  
**Type:** Modified  

#### Logic / Algorithm
1. Update `_run_inner_context_window_hook` to be `async def`:
```python
    async def _run_inner_context_window_hook(
        self,
        metadata: Mapping[str, Any],
        *,
        message: str,
        provider: str,
        iteration_count: int = 0,
        assistant_output: str | None = None,
        call_contexts: Sequence[ToolCallContext] = (),
        tokens_used: int | None = None,
        runner: object | None = None,
        invoke_runner: Callable[..., Any] | None = None,
        runner_output_text: Callable[[object], str] | None = None,
        runner_output_metadata: Callable[[object], Mapping[str, Any]] | None = None,
        options: Mapping[str, Any] | None = None,
        messages: Sequence[dict[str, Any]] | None = None,
    ) -> None:
```
2. Build and pass all required run-context fields inside `_run_inner_context_window_hook`.
3. In `_arun_once`, prefix both invocations of `_run_inner_context_window_hook` with `await`.
4. Ensure the second invocation passes `runner`, `invoke_runner`, `runner_output_text`, `runner_output_metadata`, `options`, `messages`, and `self.system_prompt`.

---

### 6.5 `TrajectoryCheckpointAlgorithm`
**File(s):** `vidbyte/context/algorithms/trajectory_checkpoints.py`  
**Type:** Modified  

#### Logic / Algorithm
1. Add `mode: Literal["deterministic", "agentic"] = "deterministic"` to fields.
2. Update `after_tool_calls` to be `async def`.
3. If `mode == "agentic"` and `snapshot is not None`:
   - Attempt to load `Prompt.TRAJECTORY_CHECKPOINTS_AGENTIC_SUMMARIZER` using `Prompts().get(...)`.
   - Stringify `ctx.messages` into a readable conversation history representation.
   - Format the summarizer prompt.
   - Call `await ctx.invoke_runner(ctx.runner, formatted_prompt, **dict(ctx.options or {}))` to get the model response.
   - Extract response text and parse as JSON.
   - If successful, construct `TrajectoryCheckpointContextItem` using the JSON fields.
   - If any step fails (network error, JSON error), log/record the failure and fall back to `self.build_item` (deterministic).

---

## 7. Data Model Changes

### 7.1 `TrajectoryCheckpointAlgorithm` Fields
**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointAlgorithm(InnerContextWindowAlgorithm):
    ...
    mode: str = "deterministic" # "deterministic" or "agentic"
```

---

## 8. API Changes

N/A - no external HTTP endpoints added. Only Python SDK interface parameter additions.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/prompts/trajectory_checkpoints.json` | New prompt asset for agentic summarizer |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add Prompt enum member for summarizer |
| MODIFY | `vidbyte/context/runtime.py` | Update InnerContextWindowAlgorithm to async and extend run context |
| MODIFY | `vidbyte/agents/runtime.py` | Await async context window hook and pass runner/provider fields |
| MODIFY | `vidbyte/context/algorithms/trajectory_checkpoints.py` | Add agentic mode logic, parser, and fallbacks |

---

## 10. Testing Plan

### Unit Tests

- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_config_accepts_valid_modes` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_config_rejects_invalid_mode` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_agentic_prompt_asset_loads_successfully` [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_agentic_parsing_valid_json` [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_agentic_parsing_invalid_json_falls_back_to_deterministic` [Silent Failure]

### Integration Tests

- `tests/test_agent_runtime.py` -> `test_runtime_invokes_model_call_for_agentic_checkpoints` [Integration]
- `tests/test_agent_runtime.py` -> `test_runtime_gracefully_handles_agentic_model_call_failure_with_fallback` [Hidden Failure]

### Manual / QA Test Cases

1. Given an Agent with `algorithm=TrajectoryCheckpointAlgorithm(mode="agentic", interval=2)`, when running a task that requires 3 iterations, then verify the model is called to produce a synthesized trajectory checkpoint.

---

## 11. Dependencies & External Services

No new external dependencies.

---

## 12. Rollout & Deployment

- Opt-in behavior only (default remains `deterministic`).
- No breaking changes.

---

## 13. Open Questions

- [ ] Should the user be able to specify a separate `summary_provider` / model config to reduce token costs (e.g. running the main agent on Claude 3.5 Sonnet, but checkpoints on Gemini 1.5 Flash)?

---

## 14. Alternatives Considered

### Alternative 1: Run summary call as an internal agent tool
- **What:** Expose a `generate_checkpoint` tool.
- **Why rejected:** Checkpoint creation is deterministic in cadence and must run automatically in the background without requiring the main agent to select or execute a tool.
