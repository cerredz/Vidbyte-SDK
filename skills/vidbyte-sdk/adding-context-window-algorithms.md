# Adding Context Window Algorithms

Use this guide when adding or changing a Vidbyte SDK context-window algorithm.
A context-window algorithm is an out-of-the-box agent behavior that changes what
the model sees during execution. It is not just a configuration flag. When a
developer writes `algorithm=ContextWindow.preset.<name>`, the SDK should attach
the complete algorithm implementation to the agent runtime and run it without
requiring the developer to manually call helper functions.

This file is intentionally detailed. Context-window algorithms sit across the
public SDK surface, prompt catalog, agent runtime, middleware, tool execution,
and tests. Small mistakes usually still compile, but they fail silently at
runtime by dropping context, bypassing middleware, hiding tool results from the
wrong place, or exposing a preset that does not actually run.

Related skill files:

- Vidbyte SDK structure: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/vidbyte-sdk/SKILL.md
- Adding prompt assets: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/vidbyte-sdk/adding-prompts.md
- Pipeline topology guidance: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/vidbyte-sdk/pipelines.md

Related design docs:

- Minimal agent runtime: `docs/design/minimal-agent-runtime.md`
- Context management foundation: `docs/design/context-management-foundation.md`
- Strategies to context-window algorithms, when present: `docs/design/strategies-to-context-window-algorithms.md`

## 1. Mental Model

Context-window algorithms are agent-attached runtime policies. They receive the
same task, runner, context, tools, middleware, and tracing path as a normal
direct agent run, but they may modify the context between attempts or stages.
Simple compaction of tool results or provider message history now belongs in
`vidbyte.middleware.builtins` instead of new context-window algorithms. Use a
context-window algorithm only when the behavior owns a full runtime flow, such
as Reflexion retries or multi-provider grading.

The developer-facing shape should stay simple:

```python
from vidbyte import Agent, ContextWindow

agent = Agent(
    name="worker",
    system_prompt="Work carefully.",
    runner=runner,
    tools=[lookup],
    algorithm=ContextWindow.preset.reflexion,
)
```

That line must be enough. The developer should not need to import a runtime
adapter, call a retry loop manually, render prompt files, or wire middleware
callbacks themselves.

There are two implementation halves:

1. Public context configuration under `vidbyte/context/`.
2. Runtime execution under `vidbyte/agents/`.

The public context half defines what a user can select or customize. The runtime
half defines what actually happens when the agent runs. Both halves are required
for a real algorithm.

## 2. Goals And Non-Goals

### Goals

- Provide one obvious preset through `ContextWindow.preset.<name>`.
- Support string resolution through `ContextWindow.resolve_algorithm("<name>")`.
- Expose a typed public configuration object when users need customization.
- Keep prompt assets readable, inspectable, and overrideable without hardcoding
  large prompt bodies in Python runtime code.
- Attach the real runtime behavior automatically through `AgentRuntime`.
- Preserve tools, permissions, middleware, tracing, provider formatting, and
  `StrategyResult` metadata.
- Add tests before implementation for the public API, runtime behavior, prompt
  loading, edge cases, and hidden failure modes.
- Document the trace shape so developers and future maintainers can understand
  what happened during a run.

### Non-Goals

- Do not turn pipelines into context-window algorithms. Pipelines pass strings
  between agents and must not manage context, budgets, or artifacts.
- Do not add a custom compiler or low-level builder API unless a design review
  explicitly asks for it.
- Do not add provider network calls or service-specific logic.
- Do not hide internal failures by returning a default preset when an unknown
  algorithm name is requested.
- Do not make `AgentRuntime` contain every algorithm loop directly.

## 3. Required Architecture

A complete algorithm has these layers:

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Public config | `vidbyte/context/algorithms/<name>.py` | User-facing dataclass, validation, pure formatting helpers |
| Preset registration | `vidbyte/context/presets.py` | One coarse SDK preset and string-resolution support |
| Runtime dispatcher | `vidbyte/agents/context_algorithms.py` | Detect the selected algorithm and return the runtime adapter |
| Runtime implementation | `vidbyte/agents/algorithms/<name>.py` | The actual model/tool/middleware orchestration |
| Prompt assets | `vidbyte/prompts/prompts/<family>/` | Markdown-backed prompt bodies and JSON descriptor |
| Prompt exports | `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/` | Enum access, direct imports, prompt bundles |
| Tests | `tests/` | Public API, prompt catalog, runtime behavior, metadata, edge cases |
| Docs/skills | `skills/vidbyte-sdk/` and README/design docs when needed | Maintainer and user guidance |

Keep the boundaries strict. Public configuration may render text and summarize
state, but it should not call model runners. Runtime adapters may call
`AgentRuntime` helpers, but they should not define public preset dataclasses.
Prompt assets should live in the prompt catalog, not inside algorithm classes as
large inline strings.

## 4. Naming And File Layout

Use one stable algorithm key everywhere. For an algorithm named `example`, use:

```text
vidbyte/context/algorithms/example.py
vidbyte/agents/algorithms/example.py
vidbyte/prompts/prompts/example/
ContextWindow.preset.example
ContextWindow.resolve_algorithm("example")
ContextWindowAlgorithm.example
ExampleAlgorithm
ExampleRuntimeAlgorithm
```

Names should be snake_case for files, prompt keys, metadata keys, and preset
names. Class names should be PascalCase. Runtime adapter names should end with
`RuntimeAlgorithm` so it is clear they are not the public config object.

Avoid near-duplicate preset names. Prefer:

```python
ContextWindow.preset.reflexion
```

over:

```python
ContextWindow.preset.reflexion_last_attempt
ContextWindow.preset.reflexion_with_memory
ContextWindow.preset.reflexion_retry_three_times
```

Low-level behavior belongs on the public configuration dataclass:

```python
ReflexionAlgorithm(max_trials=3, max_reflection_chars=1200)
```

The preset should be the obvious default, not a catalog of every possible
parameter combination.

## 5. Tests-First Workflow

Write the first tests before implementing runtime behavior. Context-window
algorithms have too many cross-module wiring points to trust a code-only pass.
The tests should prove that the algorithm is selectable, actually runs, and
preserves the agent runtime contract.

### 5.1 Public API Tests

Add tests that assert:

- `ContextWindow.preset.<name>.name == "<name>"`.
- `ContextWindow.preset.<name>.<name>` contains the public config object.
- `ContextWindow.resolve_algorithm("<name>").name == "<name>"`.
- The config object can be imported from expected public surfaces when it is
  user-facing.
- Unrelated presets keep their existing behavior.

Example:

```python
def test_context_window_preset_exposes_example_algorithm(self) -> None:
    algorithm = ContextWindow.preset.example

    self.assertEqual(algorithm.name, "example")
    self.assertIsInstance(algorithm.example, ExampleAlgorithm)
    self.assertEqual(ContextWindow.resolve_algorithm("example").name, "example")
```

### 5.2 Prompt Catalog Tests

When prompts are added, test:

- `Prompts().family("<family>")` contains every expected prompt key.
- `Prompts().get(Prompt.EXAMPLE_PROMPT)` returns Markdown text, not the JSON
  descriptor or path.
- Direct imports from `vidbyte.prompts` match enum lookup.
- Any prompt bundle class returns the same family data as `Prompts().family`.
- Prompt templates can be formatted with all required variables.

Prompt tests catch a common silent failure: the enum value points to the wrong
family key, direct import names exist but return stale text, or a Markdown-backed
prompt path is missing from package data.

### 5.3 Dispatcher Tests

Add tests for `AgentRuntimeContextAlgorithms`:

- `detect_algorithm()` returns the active name.
- `is_algorithm(name)` is true only for the active algorithm.
- `return_algorithm()` returns the expected runtime adapter class.
- `arun(...)` returns `None` when no runtime algorithm is configured.

This prevents a preset that exists publicly but never attaches to the agent
runtime.

### 5.4 Runtime Behavior Tests

Use fake runners and fake tools. Do not call real providers. Test the smallest
complete execution trace:

1. A first model attempt fails or stops for the algorithm-specific reason.
2. The algorithm-specific stage runs, if the algorithm has one.
3. A later attempt receives the transformed context.
4. The final `StrategyResult` includes metadata describing the algorithm trace.

For retry-style algorithms, include at least one test where the first trial
fails and a later trial succeeds. For compaction-style algorithms, include a
test where raw context is stored in metadata but transformed before becoming
model-visible.

### 5.5 Edge Case Tests

Add focused tests for likely mistakes:

- Invalid numeric config values raise at construction time.
- `max_trials=1` or equivalent single-pass settings do not call reflection or
  retry stages.
- Empty reflections, empty summaries, and empty model output do not crash.
- Unknown stop reasons use a conservative fallback.
- Prompt override strings replace catalog defaults.
- Metadata from normal runtime execution is preserved after algorithm metadata
  is attached.
- Tool calls still use permission checks and appear in result metadata.

### 5.6 Regression Tests For Hidden Assumptions

Before implementation, write down assumptions in test names or comments. Common
hidden assumptions include:

- The model-visible system prompt is allowed to change between trials.
- The provider `messages` option can be copied safely per attempt.
- Middleware hooks should run for each model call, including algorithm stages.
- Raw tool output should remain auditable even if model-visible output is
  compacted or hidden.
- Token usage may be unavailable from the provider.
- The algorithm may receive a `StrategyResult` from middleware instead of a raw
  runner response.

The test suite should make those assumptions executable.

## 6. Public Configuration Layer

Create the public config dataclass in `vidbyte/context/algorithms/<name>.py`.

Use this layer for:

- immutable algorithm settings
- validation of limits and budgets
- prompt override strings
- pure context transformation helpers
- pure formatting and truncation helpers
- metadata defaults

Do not use this layer for:

- model runner calls
- tool execution
- middleware dispatch
- tracing spans
- provider message mutation
- filesystem or network access

Preferred shape:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ExampleAlgorithm:
    max_attempts: int = 3
    max_memory_chars: int = 1200
    stage_prompt: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero.")
        if self.max_memory_chars <= 0:
            raise ValueError("max_memory_chars must be greater than zero.")
```

### 6.1 Comprehensive Validation In `__post_init__`

Every public config class that accepts provider names, model strings, prompt overrides, character limits, or mappings must validate all fields in `__post_init__` so errors surface at construction time rather than at runtime. Define each check as a small module-level helper function and call them from `__post_init__` — one line per check.

Required validation categories:

- **Provider names**: validate each provider string against `ModelProvider` via `ProviderModelRegistry.validate_provider(provider)`. This raises `ConfigurationError` for unrecognized provider values.
- **Model strings**: validate non-empty via `ProviderModelRegistry.validate_model(model)`.
- **Provider-models mapping**: validate all entries via `ProviderModelRegistry.validate_provider_models_map(provider_models)`.
- **Character limits**: check both a lower bound (`> 0`) and an upper safeguard (`<= MAX_LIMIT`) to prevent token exhaustion.
- **Prompt overrides**: if a prompt override string is provided, reject empty or whitespace-only values.
- **Prompt template placeholders**: if a custom prompt template is accepted, validate that all required `{placeholder}` keys are present using `string.Formatter().parse(...)`.
- **Metadata keys**: reject non-string keys in any `metadata: Mapping[str, Any]` field.

Errors must be `ConfigurationError` from `vidbyte.lib.errors`, not bare `ValueError` or `TypeError`. Example shape:

```python
def __post_init__(self) -> None:
    # Validates all configuration fields at construction time to surface errors early.
    _validate_grader_chars(self.max_grader_chars)
    ProviderModelRegistry.validate_provider(self.grader_provider)
    ProviderModelRegistry.validate_model(self.grader_model)
    if self.provider_models is not None:
        ProviderModelRegistry.validate_provider_models_map(self.provider_models)
    _validate_prompt_override(self.agent_system_prompt, "agent_system_prompt")
    _validate_grader_prompt_placeholders(self.grader_prompt)
    _validate_metadata_keys(self.metadata)
```

Where each helper is a small module-level function raising `ConfigurationError`:

```python
def _validate_grader_chars(max_grader_chars: int) -> None:
    # Raises ConfigurationError if max_grader_chars is outside the valid positive range.
    if max_grader_chars <= 0:
        raise ConfigurationError("max_grader_chars must be greater than zero.")
    if max_grader_chars > _MAX_GRADER_CHARS_LIMIT:
        raise ConfigurationError(f"max_grader_chars exceeds limit of {_MAX_GRADER_CHARS_LIMIT}.")
```

### 6.2 Class-Level Instructions

Each public config class should follow these rules:

- Use `@dataclass(frozen=True, slots=True)`.
- Keep constructor defaults conservative and useful out of the box.
- Validate every numeric limit in `__post_init__`.
- Store `metadata` as a mapping with `field(default_factory=dict)`.
- Keep methods deterministic and side-effect free.
- Return new context objects with `dataclasses.replace(...)` when modifying a
  dataclass context.
- Bound model-provided memory, summaries, or attempts by character limits.
- Prefer explicit method names such as `context_for_trial`,
  `render_reflection_prompt`, `capture_reflection`, or `should_reflect`.
- Keep public and private method signatures on one line when practical, matching
  the SDK style used in strategy and dataclass files.

### 6.2 Public Config Silent Failures

Watch for these issues:

- A default prompt override of `""` is treated as false and silently falls back
  to the catalog prompt. If empty override should be invalid, validate it.
- A truncation helper appends a suffix but does not account for suffix length.
  That may exceed documented bounds.
- A `Mapping` is stored directly and later mutated by the caller. Prefer copying
  into a `dict` when merging into runtime metadata.
- A helper returns the original context even when metadata should be updated.
- A config object validates `max_trials` but runtime code loops over a different
  field.

## 7. Preset Registration

Add the algorithm field to `ContextWindowAlgorithm` only when the algorithm has
runtime behavior beyond existing tool-result admission:

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    name: str
    tool_result_admission: ToolResultAdmission = ToolResultAdmission.RAW
    max_tool_result_chars: int = 600
    example: ExampleAlgorithm | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

Then register one preset in `vidbyte/context/presets.py`:

```python
@property
def example(self) -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(
        name="example",
        example=ExampleAlgorithm(),
    )
```

Also update string resolution:

```python
if algorithm == "example":
    return ContextWindow.preset.example
```

Do not return `ContextWindow.preset.default` for unknown strings. Unknown
algorithm names should raise `ValueError` so mistakes fail loudly.

## 8. Prompt Assets

If the algorithm uses static prompts, follow
`skills/vidbyte-sdk/adding-prompts.md`.

The required folder pattern is:

```text
vidbyte/prompts/prompts/<family_key>/
|-- <family_key>.json
|-- main_stage_prompt.md
`-- optional_stage_prompt.md
```

Update:

- `vidbyte/lib/enums/prompts.py`
- `vidbyte/prompts/strategies/strategy_prompts.py`
- `vidbyte/prompts/strategies/__init__.py`
- `vidbyte/prompts/__init__.py` when direct imports are user-facing
- prompt tests

Prompt construction should make context sections explicit. Prefer named sections
like:

- original task
- previous attempt
- tool observations
- reflection memory
- requested output

Do not use anonymous inline strings such as:

```python
f"{task}\n{result}\nTry again."
```

That shape is hard to audit, hard to override, and easy to break when new
context fields are added.

## 9. Runtime Dispatcher

`vidbyte/agents/context_algorithms.py` is the only agent-runtime file that should
map configured public algorithms to concrete runtime adapters.

Required interface:

```python
class AgentRuntimeContextAlgorithms:
    def __init__(self, runtime: AgentRuntime) -> None: ...
    def detect_algorithm(self) -> str | None: ...
    def is_algorithm(self, name: str) -> bool: ...
    def return_algorithm(self) -> ExampleRuntimeAlgorithm | None: ...
    async def arun(...) -> StrategyResult | None: ...
```

### 9.1 Dispatcher Rules

- `detect_algorithm()` should inspect `self.runtime.algorithm` and return the
  active algorithm name or `None`.
- `is_algorithm(name)` should be a thin readability helper.
- `return_algorithm()` should instantiate the matching runtime adapter.
- `arun(...)` should delegate to the adapter and return `None` when no runtime
  algorithm is configured.
- The dispatcher should not contain algorithm loops, prompt rendering, retry
  policy, or stage-specific metadata construction.
- The dispatcher should be tested directly.

### 9.2 Dispatcher Silent Failures

The most common dispatcher bugs are:

- The preset exists, but `detect_algorithm()` does not know about it.
- `detect_algorithm()` returns the algorithm name, but `return_algorithm()` still
  returns `None`.
- `return_algorithm()` imports from the public config layer instead of the
  runtime adapter layer.
- The dispatcher returns an adapter for any truthy metadata value instead of the
  typed algorithm field.
- `AgentRuntime.arun()` ignores the dispatcher result and always falls through
  to `_arun_once()`.

Write tests that would fail for each of those mistakes.

## 10. Runtime Implementation

Create the concrete runtime adapter under:

```text
vidbyte/agents/algorithms/<algorithm_name>.py
```

This module owns the real algorithm execution. It may call generic
`AgentRuntime` helpers, but it must keep algorithm-specific loops out of
`vidbyte/agents/runtime.py`.

Preferred shape:

```python
class ExampleRuntimeAlgorithm:
    name = "example"

    def __init__(self, runtime: AgentRuntime, algorithm: ExampleAlgorithm) -> None:
        self.runtime = runtime
        self.algorithm = algorithm

    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> StrategyResult:
        ...
```

Long signatures are accepted when they match the runtime call boundary. Avoid
inventing a second argument object unless the surrounding runtime already has
one. The adapter should mirror `AgentRuntime.arun(...)` closely so delegation is
obvious.

### 10.1 Runtime Helper Methods

Split algorithm execution into helpers that describe the trace:

- `_run_trial`
- `_build_trial_context`
- `_run_stage`
- `_reflect_after_failure`
- `_summarize_attempt`
- `_stage_metadata`
- `_trial_metadata`
- `_with_algorithm_metadata`
- `_capture_memory`

Each helper should own one decision. For example, do not combine "run model
call", "summarize failed attempt", "decide retry", and "attach metadata" in a
single private method.

### 10.2 Preserving The Agentic Loop

Runtime adapters should call `self.runtime._arun_once(...)` for ordinary direct
agent trials. This preserves:

- provider tool schema formatting
- internal `isDone` behavior
- local tool execution
- permission checks
- tool-call metadata
- budget stops
- provider messages
- middleware before/after hooks
- tracing

If an algorithm needs an extra model call that is not a full agent trial, call
`self.runtime._invoke_with_middleware(...)` rather than invoking the runner
directly. That keeps middleware and tracing consistent for algorithm stages.

Do not duplicate the tool loop in the adapter unless the algorithm is explicitly
designed to replace the normal direct runtime. Reimplementing the loop usually
breaks permissions, `isDone`, provider-specific parsing, or runtime metadata.

### 10.3 Updating The Inner Agent Loop

Some context-window algorithms need to add or update model-visible context
inside one direct `_arun_once(...)` run instead of wrapping whole trials. Use the
inner-loop context-window lifecycle for that shape.

The interface is intentionally small. An inner-loop algorithm exposes a single
hook, `after_tool_calls`, which the runtime invokes after the tool calls of each
completed non-final iteration finish. The runtime also invokes it once at run
start with `ctx.iteration is None` so the algorithm can initialize per-run state:

```python
from vidbyte.context.runtime import ContextWindowRunContext, InnerContextWindowAlgorithm

class ExampleInnerAlgorithm(InnerContextWindowAlgorithm):
    def after_tool_calls(self, ctx: ContextWindowRunContext) -> None:
        if ctx.iteration is None:
            return  # run-start initialization
        ctx.place_after_tools(
            ExampleContextItem(primitive_id="example:current", content="bounded context")
        )
```

There is exactly one runtime dispatch point. Do not reintroduce per-stage hooks
such as `before_model_call`, `after_model_response`, or `on_run_end`; everything
an inner-loop algorithm needs is observable from the iteration snapshot at the
single `after_tool_calls` point.

`ContextWindowRunContext` is a slim write surface over the active
`ContextManager`. It carries only:

- `iteration`: the observable `AgentIterationSnapshot` (read), or `None` at run start.
- `context_manager`: the active `ContextManager` (write surface).
- `recorder`: the run recorder for template slots.
- `state`: a per-run dict for cadence tracking and published metadata.

All primitive placement logic lives on `ContextManager`. Use its semantically
named methods rather than a raw placement enum:

- `place_after_system_prompt(item)` renders the primitive at the top of the
  context zone, just after the system prompt.
- `place_after_tools(item)` renders the primitive at the end of the context
  zone, after tool-bound primitives.

Both methods mint a stable `primitive_id` when the item does not already have
one and return it. The run context exposes the same two methods plus `remove`,
`record`, and `set_metadata`.

Do not mutate provider `messages` directly from a context-window algorithm.
Do not add an arbitrary callback such as `iteration_observer` that returns text
for runtime to append. Do not make deterministic runtime algorithms depend on a
model-called `write_context` tool. Tools are model-selected; inner-loop context
algorithms are SDK-selected runtime behavior.

CI enforces this for inner-loop modules as **CWP002** in
`scripts/check_context_write_paths.py` (wired into `python scripts/run_ci.py`).
Private `ContextManager._registry` / `._placements` access is also banned outside
`manager.py` (**CWP001**). See the "Context write path integrity" section in
`skills/vidbyte-sdk/context-primitives.md` and
`docs/design/context-write-path-integrity.md`.

`AgentRuntime` renders the manager on the next model call through the existing
context-window primitive path. This keeps a single standard for context-window
updates and preserves middleware, permissions, tracing, tool execution, and
provider formatting.

When adding an inner-loop algorithm:

1. Define a public frozen config dataclass that subclasses `InnerContextWindowAlgorithm`.
2. Define a typed `ContextItem` for any algorithm-owned context block.
3. Implement `after_tool_calls`, initializing on the `ctx.iteration is None` call
   and using config-owned cadence logic (e.g. `iteration_count % interval == 0`).
4. Write context with `ctx.place_after_tools(...)` or `ctx.place_after_system_prompt(...)`.
5. Record template slots with `ctx.record(...)`.
6. Publish final metadata with `ctx.set_metadata(...)`; the runtime copies public
   `state` keys onto the final result metadata.
7. Add tests proving the next model call sees the context through `ContextManager`, not direct message injection.
8. Run `python scripts/check_context_write_paths.py` (or full `python scripts/run_ci.py`)
   so CWP002/CWP001 pass before opening a PR.

### 10.4 Metadata Contract

Every runtime algorithm should attach one algorithm-specific metadata object to
the final `StrategyResult.metadata`.

For example:

```python
metadata["example"] = {
    "trial_count": 2,
    "stage_count": 1,
    "attempts": (
        {"trial_index": 0, "stop_reason": "max_iterations"},
        {"trial_index": 1, "stop_reason": "is_done"},
    ),
}
```

Metadata should answer:

- How many main attempts ran?
- Which algorithm-specific stages ran?
- Why did each attempt stop?
- What bounded memory, summaries, or decisions were carried forward?
- Did the final result come from a normal trial or an algorithm stage?

Keep raw provider responses out of algorithm metadata unless already part of
normal runtime metadata. Store bounded strings and structured counters instead.

### 10.5 Runtime Silent Failures

Watch for these issues:

- Reusing the same mutable `options` dict across attempts, causing provider
  messages from one attempt to leak into another.
- Running reflection or scoring stages by calling `invoke_runner` directly,
  bypassing middleware and tracing.
- Attaching algorithm metadata by replacing the entire result metadata dict and
  dropping normal runtime fields.
- Using `result.output` as the only failure summary even when tool-call metadata
  contains the important failure.
- Treating every non-`isDone` result as a failure without considering configured
  stop reasons.
- Running an extra reflection stage after the final allowed trial.
- Forgetting to bound model-generated reflection memory before injecting it into
  the next context.
- Returning the original `StrategyResult` after mutating a local metadata copy.

## 11. AgentRuntime Integration

`AgentRuntime.arun(...)` should stay thin:

```python
algorithm_result = await AgentRuntimeContextAlgorithms(self).arun(...)
if algorithm_result is not None:
    return algorithm_result
return await self._arun_once(...)
```

Do not add algorithm-specific conditionals such as:

```python
if self.algorithm.reflexion:
    return await self._arun_with_reflexion(...)
```

That puts runtime algorithm logic back into the generic runtime and makes every
new algorithm expand `AgentRuntime`.

`AgentRuntime` may expose generic helpers such as `_arun_once(...)` and
`_invoke_with_middleware(...)` for adapters to reuse. Those helpers should remain
algorithm-neutral.

## 12. Runtime Contracts To Preserve

Every context-window algorithm must preserve these contracts unless a reviewed
design explicitly changes them:

- Tools still come from the agent's `Tools` catalog.
- Internal `isDone` remains available for direct text agents.
- Permission policy checks still happen through `AgentRuntime.execute_tool_call`.
- Middleware hooks still run through `MiddlewarePipeline`.
- Provider tool-call parsing still uses `ToolsFormatter`.
- Tracing still uses the runtime tracer.
- Final output is still a `StrategyResult`.
- Public agent replies still flow through `BaseAgent.generate_reply`.
- Agent history is updated by `BaseAgent`, not directly by the algorithm.
- Raw audit metadata remains available even when model-visible context is
  transformed.

If a new algorithm intentionally changes any of these contracts, write a design
doc first and add tests that prove the new behavior.

## 13. Context Interaction

Context-window algorithms may transform these pieces:

- `BaseAgentContext.system_prompt`
- model-visible provider messages for future calls
- bounded summaries or memories injected into context metadata
- model-visible tool-result text

They should not mutate:

- the agent's default context items
- the caller's `ContextManager`
- prior `AgentMessage` history objects
- global prompt registry state
- tool definitions or permission policy

Use `dataclasses.replace(...)` for context dataclasses and create fresh dicts or
tuples when attaching metadata.

## 14. Prompt Override Rules

Default prompt text should come from the prompt catalog. User overrides should
be plain string fields on the public config dataclass:

```python
ExampleAlgorithm(
    stage_system_prompt="Custom system prompt.",
    stage_prompt="Task: {task}\nAttempt: {attempt}",
)
```

Do not let runtime config point at arbitrary files. File-path prompt overrides
make packaging, security, and reproducibility worse. If a developer wants custom
text, they can pass the text directly.

Validate or test every placeholder used by a default prompt. A prompt can pass
catalog loading tests and still fail at runtime because `.format(...)` expects a
missing key.

## 15. Edge Case Checklist

Before opening a PR, confirm the algorithm handles:

- no configured algorithm
- unknown algorithm string
- single-trial or single-pass config
- zero or negative numeric config values
- empty task string
- empty runner output
- model calls that return no tool calls
- model calls that return malformed tool calls
- tool execution success
- tool execution error
- permission denial
- max-iteration stop
- max-token stop when provider usage is available
- missing provider usage
- middleware short-circuit returning `StrategyResult`
- prompt override fields
- long reflection or memory text
- long failed-attempt summaries
- empty accumulated memory
- final metadata preserving normal runtime fields

Not every algorithm needs a separate test for every bullet, but the PR should
explicitly cover the cases that can affect its behavior.

## 16. Hidden Assumptions To Write Down

Context-window algorithms often depend on assumptions that are not obvious from
the code. Make them explicit in docs, test names, or metadata:

- What counts as a failed attempt?
- Does the algorithm retry after every non-final stop reason or only specific
  stop reasons?
- Are reflection/scoring stages allowed to use tools, or are they model-only?
- Does middleware run for algorithm stages?
- Are algorithm stages counted as normal model calls in final metadata?
- Is algorithm memory visible to the user, the model, both, or only metadata?
- Does the algorithm transform only model-visible context or also stored audit
  data?
- Can the algorithm run with strategies, or only direct no-strategy agents?
- What happens when the provider cannot report token usage?

If an assumption matters for correctness, add a test. If it matters for users,
add documentation.

## 17. Review Checklist

Use this checklist before handing off a PR:

- [ ] The public preset exists and is the intended default.
- [ ] String resolution accepts the new preset name.
- [ ] Unknown preset names still fail loudly.
- [ ] The public config dataclass validates limits.
- [ ] Prompt assets are Markdown-backed when prompt bodies are large.
- [ ] Prompt enum values and direct imports resolve.
- [ ] The dispatcher detects the algorithm.
- [ ] The dispatcher returns the correct runtime adapter.
- [ ] `AgentRuntime.arun(...)` stays generic and thin.
- [ ] Runtime adapter helpers are split by responsibility.
- [ ] The adapter uses `_arun_once(...)` for normal trials.
- [ ] Extra model stages use `_invoke_with_middleware(...)`.
- [ ] Final metadata includes an algorithm trace.
- [ ] Raw audit metadata is not lost.
- [ ] Tools, permissions, middleware, tracing, and provider formatting still run.
- [ ] Tests use fake runners and do not call live providers.
- [ ] README or usage docs show the simple `algorithm=ContextWindow.preset.<name>` path when user-facing.
- [ ] The skill docs are updated when the workflow changes.

## 18. Verification

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

If `ruff` or `mypy` are not installed locally, say so in the PR body. Do not
claim they passed.

For documentation-only changes to this file, still run at least:

```powershell
python -m compileall vidbyte
```

Then run focused tests when the existing implementation is directly referenced
by the doc, for example:

```powershell
python -m unittest tests.test_reflexion_algorithm tests.test_reflexion_prompt tests.test_context_management
```

## 19. Example Trace Shape

A retry/reflection algorithm such as Reflexion should produce a trace that can
be understood from metadata:

```python
{
    "stop_reason": "is_done",
    "iteration_count": 1,
    "tool_call_count": 1,
    "context_window_algorithm": "reflexion",
    "reflexion": {
        "trial_count": 2,
        "reflection_count": 1,
        "reflections": (
            "The first attempt stopped after using lookup without synthesizing the answer.",
        ),
        "attempts": (
            {"trial_index": 0, "stop_reason": "max_iterations", "tool_call_count": 1},
            {"trial_index": 1, "stop_reason": "is_done", "tool_call_count": 1},
        ),
    },
}
```

The exact keys may differ by algorithm, but the trace must be structured enough
for tests, middleware logs, and developers to understand what happened.

## 20. Common Implementation Sequence

Use this order for a new algorithm:

1. Write public API and prompt catalog tests.
2. Write runtime dispatcher and behavior tests with fake runners.
3. Add the public config dataclass under `vidbyte/context/algorithms/`.
4. Export the config object from context and root packages when user-facing.
5. Add prompt assets and prompt exports, if needed.
6. Add the preset and string resolution.
7. Add the runtime adapter under `vidbyte/agents/algorithms/`.
8. Wire the adapter through `AgentRuntimeContextAlgorithms`.
9. Keep `AgentRuntime.arun(...)` limited to dispatcher delegation and fallback.
10. Attach final trace metadata.
11. Update README, design docs, and skills.
12. Run compile, focused tests, and full tests.

Do not start by putting the algorithm loop inside `AgentRuntime`. That usually
creates a working prototype that is harder to review and must be extracted later.
