# Adding Context Window Algorithms

Use this guide when adding an SDK context-window algorithm that changes what an
agent sees while it runs. Context-window algorithms are selected by users through
`algorithm=ContextWindow.preset.<name>` and are attached to direct agent runtime
execution through the agent-side algorithm dispatcher.

Related skill files:

- Vidbyte SDK structure: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/vidbyte-sdk/SKILL.md
- Adding prompt assets: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/vidbyte-sdk/adding-prompts.md
- Pipeline topology guidance: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/vidbyte-sdk/pipelines.md

## Architecture

A complete context-window algorithm has four layers:

1. Public configuration under `vidbyte/context/algorithms/`.
2. Preset registration under `vidbyte/context/presets.py`.
3. Runtime dispatch under `vidbyte/agents/context_algorithms.py`.
4. Agent execution logic under `vidbyte/agents/algorithms/<algorithm_name>.py`.

Keep these responsibilities separate. The generic `AgentRuntime` should own the
normal model/tool loop, middleware hooks, permissions, tracing, and result
metadata. It should not contain algorithm-specific loops. Algorithm-specific code
belongs in `vidbyte/agents/algorithms/`.

## Step 1 - Define Public Configuration

Add the public configuration object under `vidbyte/context/algorithms/`.

Use this layer for stable user-facing configuration:

- algorithm limits and budgets
- prompt override strings
- context rendering policies
- immutable dataclasses
- pure formatting helpers

Example shape:

```python
@dataclass(frozen=True, slots=True)
class ExampleAlgorithm:
    max_trials: int = 3
    system_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

Export the new configuration from:

- `vidbyte/context/algorithms/__init__.py`
- `vidbyte/context/__init__.py`
- `vidbyte/__init__.py` when it is user-facing

## Step 2 - Add Prompt Assets

If the algorithm needs static prompts, add them through the prompt catalog.
Follow `skills/vidbyte-sdk/adding-prompts.md`.

Required pattern for new prompt families:

- create `vidbyte/prompts/prompts/<family_key>/`
- add one JSON descriptor in that folder
- add one Markdown file per prompt body
- add matching enum values to `vidbyte/lib/enums/prompts.py`
- expose a prompt bundle from `vidbyte/prompts/strategies/strategy_prompts.py`
- export the bundle from `vidbyte/prompts/strategies/__init__.py`
- export the bundle from `vidbyte/prompts/__init__.py` when useful

Algorithm implementations should retrieve default prompt text with:

```python
Prompts().get(Prompt.EXAMPLE_PROMPT)
```

Do not hardcode long prompt bodies in Python runtime files. Runtime prompt
overrides should be plain string fields on the algorithm configuration object,
not file paths or mutable global prompt registry changes.

## Step 3 - Register The Preset

Add one coarse SDK preset under `vidbyte/context/presets.py`.

```python
@property
def example(self) -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(
        name="example",
        example=ExampleAlgorithm(),
    )
```

Do not add many low-level preset variants unless the user-facing API really
needs them. Prefer one obvious preset plus a public configuration object for
customization.

If the algorithm needs storage on `ContextWindowAlgorithm`, add a nullable field
there with a backward-compatible default:

```python
example: ExampleAlgorithm | None = None
```

Existing tool-result admission behavior must keep working when the new field is
`None`.

## Step 4 - Add Agent Runtime Implementation

Create the concrete runtime implementation under:

```text
vidbyte/agents/algorithms/<algorithm_name>.py
```

This file owns the real model/tool orchestration for the algorithm. Keep its
public method small:

```python
class ExampleRuntimeAlgorithm:
    name = "example"

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, ...) -> StrategyResult:
        ...
```

Break large flows into helper methods such as:

- `_run_trial`
- `_build_trial_context`
- `_run_reflection_stage`
- `_build_stage_metadata`
- `_summarize_attempt`
- `_with_algorithm_metadata`

The runtime implementation may call generic `AgentRuntime` helpers such as
`_arun_once()` or `_invoke_with_middleware()` when it needs the normal direct
runtime behavior. This preserves tools, permissions, middleware, tracing, and
provider formatting instead of duplicating the agent loop.

Do not place algorithm-specific loops directly in `vidbyte/agents/runtime.py`.

## Step 5 - Wire The Dispatcher

Update `vidbyte/agents/context_algorithms.py`.

The dispatcher is the only agent-runtime place that should know how configured
context-window algorithms map to runtime implementations. Keep the interface
small and readable:

- `detect_algorithm()` returns the configured algorithm name or `None`.
- `is_algorithm(name)` checks the active algorithm.
- `return_algorithm()` returns the concrete runtime implementation or `None`.
- `arun(...)` delegates execution to the concrete implementation when present.

Add the new algorithm branch to `detect_algorithm()` and `return_algorithm()`.

`AgentRuntime.arun()` should call the dispatcher first, then fall back to
`_arun_once()` when no context-window algorithm is configured.

## Step 6 - Preserve Runtime Contracts

Every context-window algorithm must preserve these contracts unless a review
comment explicitly changes them:

- Tools still come from the agent's `Tools` catalog.
- Internal `isDone` behavior remains available for direct text agents.
- Permission policy checks still happen through `AgentRuntime.execute_tool_call`.
- Middleware hooks still run through `MiddlewarePipeline`.
- Provider tool-call parsing still uses `ToolsFormatter`.
- Tracing still uses the runtime tracer.
- Final output is still a `StrategyResult`.
- Public agent replies still flow through `BaseAgent.generate_reply`.

If the algorithm adds extra model calls, attach clear metadata so middleware,
audit logs, and result consumers can distinguish main attempts from algorithm
stages.

## Step 7 - Add Tests

Add focused tests for:

- preset registration through `ContextWindow.preset.<name>`
- string resolution through `ContextWindow.resolve_algorithm("<name>")`
- public exports for user-facing configuration objects
- dispatcher detection through `AgentRuntimeContextAlgorithms`
- concrete runtime behavior using fake runners/tools
- prompt catalog loading and direct prompt imports when prompts are added
- metadata shape for algorithm traces

Prefer fake runners with deterministic responses. Do not require network calls
or real providers in unit tests.

## Step 8 - Update Documentation And Skills

When adding a new context-window algorithm, update relevant SDK docs or skills:

- add usage notes to this file when the workflow changes
- link to prompt assets and public imports when adding prompts
- mention any middleware, tools, or tracing caveats
- keep examples centered on `Agent` or `BaseAgent`

User-facing examples should look like:

```python
agent = Agent(
    name="worker",
    system_prompt="Work carefully.",
    runner=runner,
    tools=[lookup],
    algorithm=ContextWindow.preset.example,
)
```

## Step 9 - Verification

Run these checks from the SDK root:

```powershell
python -m compileall vidbyte
python -m unittest discover -s tests
```

When available, also run:

```powershell
ruff check .
mypy .
```

If `ruff` or `mypy` are not installed in the local environment, report that in
the PR body instead of claiming they passed.
