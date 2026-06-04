<!--
Context Protocol Header

Description:
    Implementation guide for Vidbyte SDK continual trace artifacts.
Purpose:
    Keeps future changes aligned with the TraceOption.continual API, trace agent
    wrapper, runtime controller, prompt assets, and prebuilt schema package.
Architecture:
    - Public contracts live in vidbyte/lib/dataclasses/trace.py and vidbyte/trace/.
    - Runtime updates are delegated through ContinualTraceAgent and UpdateTraceTool.
Relations:
    Referenced by skills/vidbyte-sdk/SKILL.md and usage continual trace docs.
-->

# Continual Tracing

Use this guide when modifying continual trace artifacts in the Vidbyte SDK.

## Public API

- `BaseAgent(trace=TraceOption.continual(...))` is the public agent entry point.
- `TraceOption.continual(schema, every_n_iterations=5, max_trace_iterations=3)` is the only supported v1 trace configuration constructor.
- `schema` may be a `TraceSchema`, a pydantic `BaseModel` subclass, or a `Mapping[str, str]` of field names to descriptions. Pydantic models are the preferred way to declare schemas because each field carries both a description and a type.
- Each trace field is a typed `TraceField` (`description` + `TraceFieldType`). `TraceSchema.from_model(...)` derives the type from the pydantic annotation; mapping and string inputs default to `string`.
- Prebuilt schemas live under `vidbyte/trace/prebuilt/` and are imported with `from vidbyte.trace.prebuilt import ActionTrace`.
- Do not confuse `trace=` with `tracer=`. `trace=` returns user-visible artifacts. `tracer=` records observability spans.

## Implementation Boundaries

- Shared dataclasses belong in `vidbyte/lib/dataclasses/trace.py`.
- Public re-export modules belong in `vidbyte/trace/`.
- Prebuilt schemas belong in `vidbyte/trace/prebuilt/`.
- The trace update tool belongs in `vidbyte/trace/tools.py`.
- `ContinualTraceController` belongs in `vidbyte/trace/continual/` (not in `runtime.py`); `AgentRuntime` re-exports it for backward compatibility.
- `ContinualTraceAgent` belongs in `vidbyte/agents/continual_trace.py` and must remain a thin wrapper over `BaseAgent`.
- Prompt assets belong in `vidbyte/prompts/prompts/continual_trace/` and must be registered in `vidbyte/lib/enums/prompts.py`.
- Runtime scheduling belongs in the direct linear `AgentRuntime`; do not duplicate the agent loop in the trace feature.

## Runtime Rules

- Continual trace is v1 linear-runtime-only.
- Agents with non-linear runtimes and `trace=` must fail fast in `BaseAgent`.
- Agents with non-default context-window algorithms and `trace=` must fail fast in `BaseAgent`.
- Trace updates run after every configured interval and once before a normal `isDone` result.
- The periodic interval update must happen at exactly one point in the agent loop (top of the loop, before the model call). Only the forced final update before `isDone` is a separate trace point.
- Budget and middleware stop paths attach the current artifact without spending an extra trace-agent model call.
- Trace-agent failures are fail-open and must not abort the main agent run.
- Trace-agent tool calls must not appear in the main agent `tool_calls` metadata.
- The trace artifact must never be written back into the main agent's context window or provider `messages`; it lives only on the controller and is surfaced through final `AgentResult.metadata`.

## Testing Requirements

- Use fake runners only; no live provider calls.
- Cover schema validation, prebuilt imports, `UpdateTraceTool` merge behavior, `ContinualTraceAgent` fail-open behavior, and `AgentRuntime` metadata attachment.
- Keep `scripts/test-continual-trace.py` aligned with the design doc test plan.
- Run with `PYTHONDONTWRITEBYTECODE=1` when possible because this repo tracks some bytecode artifacts.

## Things to Remember

- Every prebuilt trace schema field description must be 4-5 sentences long. Short one-line descriptions are not acceptable; the description has to give the trace agent enough guidance to fill the field well and decide what belongs in a handoff.
- Declare trace schemas with pydantic models and `Field(description=...)`, not bare `Mapping[str, str]` dicts. Each field must carry a type, derived from the pydantic annotation via `TraceSchema.from_model(...)`.
