# Retry Exhaustion Advances the Fallback Chain

## Summary

The README promises that retry middleware spends its budget on the current model and the fallback chain then advances. In practice, once `ModelRetryMiddleware` used up its budget it returned `abort("model_retry_exhausted")`. `_invoke_with_middleware` turned that into a middleware-abort `AgentResult`, so `_arun_once`'s fallback switch never ran. This fix re-raises the model error in that case, but only when the error is fallback-eligible and the chain has a next model. The existing switch then takes over.

## Flow chart

```mermaid
flowchart TD
    A[model call raises] --> B{on_model_error decision}
    B -- RETRY --> A
    B -- ABORT_RUN --> C{fallback set, chain index known,<br/>advance(exc, index) not None?}
    C -- yes --> D[re-raise] --> E[_arun_once _fallback_transition switches model]
    C -- no --> F[return middleware abort result, unchanged]
    B -- other --> G[re-raise, unchanged]
```

## Usage example

```python
agent = Agent(
    provider="deepseek",
    model_name="deepseek-v4-pro",
    middleware=[ModelRetryMiddleware(max_attempts=3)],
    fallback=["deepseek-v4-flash"],
)
result = agent.run("task")  # pro x3 (503), then flash answers
assert result.metadata["fallback"]["used"] is True
```

## How it works

In the `ABORT_RUN` branch of the model-error handler, the runtime reads the chain index that `_arun_once` stores in `run_state["_speed_fallback_index"]` just before the call. It asks `AgentFallback.advance(exc, index)`, which is a pure function. If a next index exists, the original exception is re-raised. In every other case the abort result is returned as before: no fallback configured, the chain is exhausted, the error is not a model error, or an external caller (reflexion, the multi-provider grader) that never sets the index. The retry budget is not reset on a switch, as the README documents.

## Files

- `vidbyte/agents/runtime.py`: about 4 lines in `_invoke_with_middleware`.
- `tests/test_agent_middleware.py`: one regression test with an offline fake chain.

## Risks

- A model switched in after exhaustion gets no further retries, because the budget is run-wide. If it also fails, the run aborts with `model_retry_exhausted`. This is the documented behavior.

## Verification

- The new test fails on `main` and passes with the fix.
- `python scripts/run_ci.py --stage source`, then PR CI.
