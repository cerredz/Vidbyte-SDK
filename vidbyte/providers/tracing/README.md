# vidbyte/providers/tracing — Transport Adapters

Destination-agnostic OTel transports paired with typed trace shape translators. Shape (translator) and destination (tracer endpoint) are decoupled so any shape works with any OTel-compatible collector.

## Transports

- `OTelTracer` (`vidbyte/providers/tracing/otel.py`) — Ships spans over OTLP/HTTP to any OTel-compatible collector (Phoenix, Datadog Agent, AWS ADOT -> Bedrock AgentCore, self-hosted OTel Collector). Requires `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http` at runtime; fails loud at construction (`TracerConfigurationError`) and fails open per-call. Configuration is validated through `vidbyte.lib.dataclasses.tracing.OTelTracerConfig` and constants live in `vidbyte.lib.enums.tracing` (`OTelEndpointEnvVar`, `OTelDefault`).
- `PhoenixTracer` (`vidbyte/providers/tracing/phoenix.py`) — Phoenix-specific wrapper that defaults to `PHOENIX_COLLECTOR_ENDPOINT` / `http://localhost:6006/v1/traces`. Respects an explicit `openinference.span.kind` when set by an upstream translator; otherwise falls back to its legacy name-prefix guessing. Enum constants for span kinds and attributes live in `vidbyte.lib.enums.tracing` (`OpenInferenceSpanKind`, `OpenInferenceAttribute`).

## Trace Shapes

Shapes are `ProviderTraceTranslator` implementations under `vidbyte/trace/providers/`. Their wire strings and validation live in `vidbyte.lib.enums.tracing` and `vidbyte.lib.dataclasses.tracing`.

- `OTelGenAIProviderTranslator` (`vidbyte/trace/providers/otel_genai.py`) — `gen_ai.*` shape (`provider="otel-genai"`). Validated shape contract `OTelGenAIShapeDefinition` declared as `trace_shape` at the provider line. See design doc `docs/design/otel-genai-and-openinference-trace-shapes.md` for the spec tables.
- `OpenInferenceProviderTranslator` (`vidbyte/trace/providers/openinference.py`) — `openinference.span.kind` / `llm.*` / `tool.*` shape (`provider="openinference"`). Validated shape contract `OpenInferenceShapeDefinition` declared as `trace_shape` alongside `provider`.

## Documentation Links (specs verified live during PR #390)

- OTel GenAI semantic conventions — https://github.com/open-telemetry/semantic-conventions-genai
  - Agent spans (`invoke_agent`) — https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md
  - LLM/chat spans — https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md
  - Tool spans (`execute_tool`) — https://github.com/open-telemetry/semantic-conventions-genai/blob/main/reference/reports/execute-tool-span.md
  - AWS Bedrock AgentCore OTel compatibility — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html
- OpenInference semantic conventions — https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
- Datadog OTel intake (GenAI + OpenInference) — https://docs.datadoghq.com/llm_observability/instrumentation/otel_instrumentation/
- OTel OTLP/HTTP exporter — https://opentelemetry.io/docs/specs/otlp/

## Usage

```python
from vidbyte import Agent, Trace

# OTel GenAI shape to any OTel collector (ADOT, Datadog Agent, OTel Collector)
agent = Agent(..., trace=Trace.otel_genai(endpoint="https://adot-collector.example.com/v1/traces"))

# OpenInference shape (works with Phoenix or any OTel collector)
agent = Agent(..., trace=Trace.openinference(endpoint="http://localhost:6006/v1/traces"))
```

Endpoint resolution for `OTelTracer`: explicit `endpoint=` arg → `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` → `OTEL_EXPORTER_OTLP_ENDPOINT` → `TracerConfigurationError` unless an `exporter=` override is injected (used in tests).

## File Index

- `README.md` — this file, links to all trace shape documentation used.
- `otel.py` — destination-agnostic OTel transport.
- `phoenix.py` — Phoenix-specific transport with openinference span-kind guard.
- `__init__.py` — exports `OTelTracer`, `PhoenixTracer`, etc.

Related:
- `docs/design/otel-genai-and-openinference-trace-shapes.md` — full design doc with functional requirements and spec citations.
- `vidbyte/lib/enums/tracing.py` — all hardcoded strings (provider names, env vars, span kinds, wire attribute keys).
- `vidbyte/lib/dataclasses/tracing.py` — validated `OTelTracerConfig` and shape dataclasses (`OTelGenAIShapeDefinition`, `OpenInferenceShapeDefinition`, `OTelGenAIAgentShape`, etc.).
