# Agents

The Vidbyte SDK uses agents as the executable actor abstraction for AI workflows.
An agent combines a system prompt, provider/model configuration, optional
tools, structured context, tracing, runtime configuration, and handoff behavior.

## Role In The SDK

`vidbyte.agents` is the layer most application code touches first. It exposes
`Agent` / `BaseAgent`, `AgentInput`, agent messages, local registries, handoff
agents, and swappable runtime implementations. Agents normalize input, build a
context window, infer the runner from provider/model configuration, execute tools when the
runtime requests them, and return an `AgentMessage`.

For open-ended team work, `vidbyte.agents.multi` exposes `MultiAgent`, a
`BaseAgent`-compatible facade whose manager plans against a shared immutable
ledger snapshot, delegates one worker per round, and can replan after failure.

## Design Philosophy

Agents are explicit composition objects rather than hidden global state. The SDK
keeps the prompt, tools, context manager, middleware, trace settings, and runner
inference visible at construction time so developers can reason about what the model sees
and what local capabilities it can call.

The default linear runtime is the compatibility path for middleware and continual
trace artifacts. Non-linear runtimes such as search and actor-model execution are
separate runtime choices with narrower compatibility rules.

## Usage

```python
from vidbyte import Agent, tool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

agent = Agent(
    name="analyst",
    system_prompt="Answer directly and cite uncertainty.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
)

reply = await agent.arun("Summarize user 42.")
print(reply.content)
```

Use `AgentInput` when a single run needs additional metadata or context items:

```python
from vidbyte import AgentInput
from vidbyte.context.primitives import TextContextItem

reply = await agent.arun(
    AgentInput(
        "Review this change.",
        context_items=(TextContextItem(title="Reviewer note", content="Focus on API compatibility."),),
    )
)
```

## Model Fallback

An agent can declare an ordered chain of backup models. Array index sets precedence:
index 0 is tried first, and the runtime advances one step each time a model call
fails with a provider-level error.

```python
from vidbyte import Agent

agent = Agent(
    name="analyst",
    system_prompt="Answer directly.",
    provider="openai",
    model_name="gpt-5.2",
    fallback=[
        "gpt-5-mini",                 # bare name inherits provider, api_key, temperature
        "anthropic/claude-sonnet-5",  # provider-prefixed, overrides the provider
    ],
)
```

Entries may also be `FallbackModel` objects when a backup needs its own credentials,
and the whole chain can be passed as a settings object alongside `AgentLoopSettings`:

```python
from vidbyte.agents import FallbackModel
from vidbyte.agents.settings import AgentFallbackSettings

agent = Agent(
    name="analyst",
    system_prompt="Answer directly.",
    provider="openai",
    model_name="gpt-5.2",
    fallback=AgentFallbackSettings(
        models=[FallbackModel(provider="anthropic", model="claude-sonnet-5", api_key=ANTHROPIC_KEY)],
        enabled=True,
    ),
)
```

Rules worth knowing:

- **Only provider-level failures trigger a switch** — `ProviderRequestError`,
  `ProviderResponseError`, `ProviderConfigurationError`, `ProviderSelectionError`,
  `UnsupportedProviderError`, and `TimeoutError`. Tool errors, permission denials,
  and cancellation propagate untouched. Override with `AgentFallbackSettings(fallback_on=...)`.
- **Retries happen first.** Retry middleware exhausts its budget on the current model
  before the chain advances, and the chain does not reset that budget.
- **Same-wire-format switches keep the transcript.** OpenAI, DeepSeek, xAI, and
  OpenRouter share one payload shape, so an in-flight run carries its tool history over
  intact. Switching across wire formats (OpenAI ↔ Anthropic ↔ Gemini) resets the
  transcript and restarts from the original prompt, because the accumulated messages are
  in the previous provider's shape. Tools already executed may run again in that case;
  the run reports `context_reset: True`.
- **Every switch is visible.** A run that fell back reports
  `AgentResult.metadata["fallback"]` with the ordered attempt log and final model, and
  emits an `agent.fallback` span. A clean run reports no `fallback` key at all.
- **The chain is per-run.** Falling back on one call never pins later calls to the backup.
- When every model fails, the agent raises `AllModelsFailedError` carrying every attempt
  and every error, chained from the first failure.
- Fallback requires the linear runtime and an agent with its own `provider`/`model_name`;
  both are rejected at construction otherwise. `fork()` inherits the chain, and
  `AgentForkSettings(fallback=...)` overrides it.

### Fallback Policies

Beyond reacting to a raised error, a chain can advance proactively on a per-hop
deadline, a per-hop cost ceiling, a per-hop error-ratio ceiling, or a chain-wide
stuck-tool-call detector:

```python
from vidbyte.agents import CostBudgetPolicy, ErrorRatePolicy, LatencyPolicy, ToolCallLoopPolicy
from vidbyte.agents.settings import AgentFallbackSettings

agent = Agent(
    name="analyst",
    system_prompt="Answer directly.",
    provider="openai",
    model_name="gpt-5.2",
    fallback=AgentFallbackSettings(
        models=["gpt-5-mini", "anthropic/claude-haiku-4-5"],
        policies=[
            LatencyPolicy(timeout_seconds_by_hop=[8.0, 5.0]),
            CostBudgetPolicy(cost_ceiling_usd_by_hop=[0.10, 0.30]),
            ToolCallLoopPolicy(window_size=8, repeat_threshold=3),
            ErrorRatePolicy(max_error_ratio_by_hop=[0.2, 0.3]),
        ],
    ),
)
```

- **Every per-hop policy takes exactly one value per transition, never one per model.**
  With two declared fallback models the chain has three models total but only two
  possible transitions — primary→first fallback, first→second fallback — so each
  array above has exactly two entries. The last model in the chain never gets one:
  there's nowhere left to fall back to. Passing the wrong length, a gap, or a
  non-positive value raises `ConfigurationError` at `AgentFallbackSettings`
  construction, before any agent exists.
- **`LatencyPolicy`** wraps the call to hop *i* in a deadline; exceeding it raises
  `TimeoutError`, which flows through the same provider-error path `fallback_on`
  already handles — no separate metadata shape.
- **`CostBudgetPolicy`** checks cumulative run cost against hop *i*'s ceiling once
  per loop iteration, before the next model call is made. Unlike `LatencyPolicy`,
  nothing has to fail for this to trigger — it downgrades proactively.
- **`ToolCallLoopPolicy`** looks at the last `window_size` tool calls the run has
  made and advances the chain once the same tool-name-plus-arguments fingerprint
  recurs across `repeat_threshold` *distinct iterations* — same-iteration parallel
  calls with identical arguments don't count on their own, only recurrence across
  separate iterations does. It is **chain-wide, not per-hop** (like `fallback_on`,
  not like `LatencyPolicy`/`CostBudgetPolicy`): a stuck tool-calling pattern isn't a
  property of which model happens to be active, so it takes one `window_size` and
  one `repeat_threshold`, not an array. `ignored_argument_keys` can exclude fields
  that legitimately vary between otherwise-identical calls.
- All three report through the same `AgentResult.metadata["fallback"]` shape and
  `agent.fallback` span as an error-triggered switch; `error_type` carries a
  reason string (e.g. `"cost_budget_exceeded"`, `"tool_call_loop_detected"`)
  instead of an exception name.
- **`ErrorRatePolicy`** checks the cumulative failure ratio of hop *i* (failed
  calls ÷ attempts, counted at the model-call site, retries included) once per
  loop iteration at the same checkpoint. A provider that recovers on retry still
  counts its failures — one call in five failing with one retry each shows
  `2/4 = 0.5`, not `0.2` — so read the ceiling as "how much retry tax am I
  willing to pay" rather than the provider's raw error rate. The ratio is not
  trusted until `min_attempts` (default 3) attempts have accumulated.
- Both report through the same `AgentResult.metadata["fallback"]` shape and
  `agent.fallback` span as an error-triggered switch; `error_type` carries a
  reason string (e.g. `"cost_budget_exceeded"`, `"error_rate_exceeded"`) instead
  of an exception name.
- All four policy triggers report through the same `AgentResult.metadata["fallback"]`
  shape and `agent.fallback` span; `error_type` carries a reason string instead of
  an exception name.
- `fallback_on` itself stays chain-wide, not per-hop — every hop shares the same
  set of exception types that justify a switch.
- All three policies are scoped to the tool-using (linear) runtime loop; non-text
  runners (image, audio, video, embedding) don't check them.

## Durable Sessions

Agents can opt into durable sessions without moving persistence into the agent constructor:

```python
from vidbyte import FileSessionStore

store = FileSessionStore("./.vidbyte/sessions")
session = agent.persist(store=store)
reply = await agent.arun("Continue the investigation.")
print(agent.session is session)
```

`agent.persist(...)` delegates to `vidbyte.sessions.Session(agent, ...)`. Once bound, direct `agent.arun(...)` and `agent.run(...)` calls record checkpoints with the same policy as `session.arun(...)` and `session.run(...)`; `agent.session` returns the current session or `None`.

`MultiAgent` is intentionally excluded from durable sessions because its
orchestrator, transfer callbacks, worker factories, and live ledger cannot be
encoded by `RunState` without changing behavior on restore.

## Ledger-Driven Teams

```python
from vidbyte import AgentBinding, AgentTransfer, MultiAgent

team = MultiAgent(
    name="team",
    system_prompt="Own the goal, surface blockers, and finish with evidence.",
    orchestrator=manager_agent,
    agents=[
        AgentBinding(
            researcher_agent,
            transfer=AgentTransfer(report_validator=verify_research_report),
        )
    ],
)

reply = await team.arun("Investigate the incident and recommend a response.")
ledger = team.last_ledger
```

The default transfer sends deterministic JSON and treats non-blank worker text
as completed but unverified evidence. Use a report validator to mark evidence
verified. Use pipelines for fixed text flow and workflows for code-owned state
machines; use `MultiAgent` when the manager must own progress and recovery.

## Key Modules

- `base.py`: `BaseAgent`, inferred runner construction, tool binding, context assembly, trace setup, and runtime dispatch.
- `client.py`: namespace client used by `VidbyteSDK().agents`.
- `fallback/`: the fallback subsystem — `chain.py` (`AgentFallback`, the ordered model
  chain and the transforms that route a run to the next model), `settings.py`
  (`AgentFallbackSettings`, the validated developer-facing chain configuration), and
  `policies.py` (`LatencyPolicy`, `CostBudgetPolicy`, the per-hop trigger conditions,
  and `ToolCallLoopPolicy`, the chain-wide stuck-tool-call trigger).
  `policies.py` (`LatencyPolicy`, `CostBudgetPolicy`, and `ErrorRatePolicy`, the
  per-hop trigger conditions, plus `ToolCallLoopPolicy`, the chain-wide trigger).
- `runtimes/`: linear, search, and actor-model runtime components.
- `handoff.py`: structured handoff generation from a completed agent run.
- `multi/`: ledger-driven manager/worker orchestration and transfer controls.
- `types.py`: agent messages, input envelopes, cards, and specs.

## Related Layers

Agents compose with [`context`](../context/README.md), [`tools`](../tools/README.md),
[`middleware`](../middleware/README.md), [`providers`](../providers/README.md),
[`pipelines`](../pipelines/README.md), and [`trace`](../trace/README.md).
