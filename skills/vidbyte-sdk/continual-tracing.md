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
- `schema` may be a `TraceSchema` or a `Mapping[str, str]` of field names to descriptions.
- Prebuilt schemas live under `vidbyte/trace/prebuilt/` and are imported with `from vidbyte.trace.prebuilt import ActionTrace`.
- Do not confuse `trace=` with `tracer=`. `trace=` returns user-visible artifacts. `tracer=` records observability spans.

## Implementation Boundaries

- Shared dataclasses belong in `vidbyte/lib/dataclasses/trace.py`.
- Public re-export modules belong in `vidbyte/trace/`.
- Prebuilt schemas belong in `vidbyte/trace/prebuilt/`.
- The trace update tool belongs in `vidbyte/trace/tools.py`.
- `ContinualTraceAgent` belongs in `vidbyte/agents/continual_trace.py` and must remain a thin wrapper over `BaseAgent`.
- Prompt assets belong in `vidbyte/prompts/prompts/continual_trace/` and must be registered in `vidbyte/lib/enums/prompts.py`.
- Runtime scheduling belongs in the direct linear `AgentRuntime`; do not duplicate the agent loop in the trace feature.

## Runtime Rules

- Continual trace is v1 linear-runtime-only.
- Agents with non-linear runtimes and `trace=` must fail fast in `BaseAgent`.
- Agents with non-default context-window algorithms and `trace=` must fail fast in `BaseAgent`.
- Trace updates run after every configured interval and once before a normal `isDone` result.
- Budget and middleware stop paths attach the current artifact without spending an extra trace-agent model call.
- Trace-agent failures are fail-open and must not abort the main agent run.
- Trace-agent tool calls must not appear in the main agent `tool_calls` metadata.

## Testing Requirements

- Use fake runners only; no live provider calls.
- Cover schema validation, prebuilt imports, `UpdateTraceTool` merge behavior, `ContinualTraceAgent` fail-open behavior, and `AgentRuntime` metadata attachment.
- Keep `scripts/test-continual-trace.py` aligned with the design doc test plan.
- Run with `PYTHONDONTWRITEBYTECODE=1` when possible because this repo tracks some bytecode artifacts.
