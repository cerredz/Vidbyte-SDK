# Design Doc: OTel GenAI and OpenInference Trace Shape Prebuilts

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-30
**Last Updated:** 2026-08-30

---

## 1. Overview

Vidbyte's agent runtime already emits a rich, provider-neutral semantic trace (`vidbyte/trace/`: `TraceController` + `TraceProfile` + `SpanSpec` + `ProviderTraceTranslator`), but today only one output shape exists — a LangSmith `run_type` translator. Outside buyers of agent trace data (AWS Bedrock AgentCore's Evaluate API, Datadog LLM Observability) do not read LangSmith's shape; they read two specific, publicly documented industry standards: OpenTelemetry's GenAI semantic conventions (`gen_ai.*` attributes) and Arize's OpenInference semantic conventions (`llm.*`/`tool.*` attributes plus `openinference.span.kind`). This feature adds both as new, swappable `ProviderTraceTranslator` implementations, plus one new destination-agnostic OpenTelemetry transport (`OTelTracer`) so either shape can be shipped over the standard OTLP wire protocol to any compatible destination — Phoenix, a Datadog Agent, an AWS Distro for OpenTelemetry (ADOT) collector, or a self-hosted OTel Collector — without hardcoding to one of them. The result: an SDK user turns on either shape in a few lines of configuration, reusing the semantic spans the runtime already produces.

---

## 2. Goals & Non-Goals

### Goals

- Implement `OTelGenAIProviderTranslator` (`provider="otel-genai"`) and `OpenInferenceProviderTranslator` (`provider="openinference"`) under `vidbyte/trace/providers/`, each mapping the SDK's existing `SpanSpec` objects into that company's exact published span-naming and attribute conventions.
- Implement a new destination-agnostic `OTelTracer` under `vidbyte/providers/tracing/otel.py` that ships real OpenTelemetry spans over OTLP/HTTP to any configured endpoint, so "which shape" (the translator) and "which destination" (the tracer's endpoint) are fully decoupled — one exporter, many possible buyers.
- Register `"otel-genai"` and `"openinference"` as recognized `provider=` strings in `Trace.profile(...)`, and add `Trace.otel(...)`, `Trace.otel_genai(...)`, `Trace.otel_genai_session(...)`, `Trace.openinference(...)`, `Trace.openinference_session(...)`, and `Trace.phoenix_default(...)` facade helpers, mirroring the existing `Trace.langsmith()` / `Trace.langsmith_default()` / `Trace.langsmith_session()` pattern exactly.
- Fix `PhoenixTracer.start_span()` to respect an already-set `openinference.span.kind` attribute instead of always overwriting it with its own guess, so it interoperates correctly as an `inner` tracer under the new `OpenInferenceProviderTranslator` (this also lets `Trace.phoenix_default(...)` reuse Phoenix's existing collector defaults with the new, spec-driven translator instead of Phoenix's ad hoc name-prefix guessing).
- Build golden-fixture tests that assert both translators' output against the exact required/recommended field names published in each company's own spec (verified this session against the live spec documents, sources cited in Section 3), plus real (non-networked) OpenTelemetry SDK round-trip tests using an injected in-memory span exporter.
- Preserve every existing tracer, translator, and facade method's current behavior, construction signature, and failure semantics — this change is purely additive.

### Non-Goals

- No Datadog-specific or Langfuse-specific translator. Datadog's own documentation states it ingests OTel 1.37+ GenAI semantic conventions and OpenInference directly, so the two translators built here already reach Datadog with no dedicated code.
- No change to `gen_ai.usage.*` / token-count population inside `AgentRuntime`. Confirmed by reading `vidbyte/agents/runtime.py::_llm_trace_inputs` — no token-count attributes are attached to `llm.call` spans anywhere in the SDK today. Both translators map usage/finish-reason fields opportunistically when present in `spec.attributes`, but do not require, invent, or backfill them. Wiring PR #304's usage tracking into span attributes is a separate, follow-up concern (see Section 13).
- No dedicated `gen_ai.*`/OpenInference mapping for `RETRIEVER`, `EMBEDDING`, `PARSER`, or `PROMPT` span kinds, or for Vidbyte-specific concepts (`aggregate.*`, `runtime.*`, `algorithm.*`, `middleware.*`, `multi_agent.*`, `session.*`). This session's spec research verified field-level detail only for GenAI **agent**, **chat/LLM**, and **tool-execution** spans (the three concretely cited by the AWS AgentCore / Datadog motivation). Every other span kind and Vidbyte-specific concept falls back to a generic, honest passthrough that preserves the semantic span name and namespaces all attributes under a `vidbyte.*` prefix, rather than inventing unverified field names.
- No live integration test against a real AWS Bedrock AgentCore or Datadog account. Verification is against each company's published spec document (golden fixtures), not a live sandbox — no such sandbox is available to this change.
- No change to `LangSmithTracer`, `LangfuseTracer`, or the `LangSmithProviderTranslator`.
- No new hard dependency in `pyproject.toml`. `opentelemetry-sdk` / `opentelemetry-exporter-otlp-proto-http` remain optional, soft-imported at call time — exactly how `PhoenixTracer` already treats them, and how `LangSmithTracer`/`LangfuseTracer` already treat their own packages.
- No validation or blocking of "mismatched" shape × destination pairings (e.g. `provider="otel-genai"` with `inner=Trace.langsmith(...)`). The existing design already allows any `provider=` × `inner=` pairing without validation; this change does not add new restrictions, only new valid combinations.

---

## 3. Background & Context

**Why now.** Outside feedback on Vidbyte's research harness identified a concrete, buildable gap: the harness tracks its own steps internally, but has no way to export a run in the shape an outside buyer's tooling actually reads. AWS Bedrock AgentCore's Evaluate API is built to import OpenTelemetry traces using the GenAI semantic conventions; without that shape, "sell trace data to AWS" has no concrete implementation path.

**Current state.** `vidbyte/trace/` already implements almost the entire abstraction this feature needs — it was found fully built during this design's repo audit (its own design doc, `docs/design/semantic-trace-profiles.md`, is stale and still marked "Draft" even though the code is real and tested):

- `vidbyte/trace/schema.py` — `SpanKind` (`chain`/`llm`/`tool`/`retriever`/`embedding`/`prompt`/`parser`), `SpanSpec` (name, kind, component, detail, parent_policy, attributes), `SemanticSpanContext`.
- `vidbyte/trace/profiles.py` — `TraceProfile` (minimal/default/verbose/diagnostic presets, per-component overrides) and `safe_trace_value()`, which redacts credential-like keys and truncates long strings.
- `vidbyte/trace/controller.py` — `TraceController(TracerBase)`: converts legacy span names (`agent.run`, `llm.call`, `tool.call`, ...) into `SpanSpec`, filters via the active `TraceProfile`, **sanitizes attributes before any translator ever sees them**, resolves parentage via a `ContextVar`-based async-safe stack, and delegates to a `ProviderTraceTranslator` then an inner `TracerBase`.
- `vidbyte/trace/providers/base.py` — the `ProviderTraceTranslator` protocol (`provider: str`, `translate_start(spec) -> ProviderSpanPayload`) and `ProviderSpanPayload(name, attributes)`. Two implementations exist today: `GenericProviderTranslator` (passthrough) and `LangSmithProviderTranslator` (adds `run_type`).
- `vidbyte/trace/base.py` — the public `Trace` facade: `Trace.off/debug/custom/profile/session/continual/langfuse/langsmith/langsmith_default/langsmith_verbose/langsmith_session/phoenix`.
- `vidbyte/providers/tracing/{langsmith,langfuse,phoenix}.py` — concrete `TracerBase` adapters, each wrapping a real external client/SDK behind a two-tier failure contract: **fail loud at construction** (`TracerConfigurationError` if the package is missing or credentials are absent) and **fail open at every per-call method** (`start_trace`/`end_trace`/`start_span`/`end_span` each wrap their body in `try/except Exception` and never let a tracing failure break agent execution).

Critically, `PhoenixTracer` (`vidbyte/providers/tracing/phoenix.py`) already builds real OpenTelemetry spans and ships them over OTLP/HTTP using the real `opentelemetry-sdk` (`TracerProvider`, `OTLPSpanExporter`, `SimpleSpanProcessor`) — this is genuine, working OTel/OTLP plumbing already in the repo. But the "shape" logic lives in the wrong layer: `PhoenixTracer.start_span()` hardcodes a guess at `openinference.span.kind` from the span name / `run_type` attribute, rather than that decision living in a `ProviderTraceTranslator` the way `LangSmithProviderTranslator` already does it for LangSmith's `run_type`. And the endpoint defaults to Phoenix's proprietary `PHOENIX_COLLECTOR_ENDPOINT` env var / `localhost:6006`, tying the transport to one destination.

**The two external specs**, re-verified via live web search and spec-document fetch during this design's research (not carried over from memory):

- **OpenTelemetry GenAI semantic conventions** (`gen_ai.*`) — https://github.com/open-telemetry/semantic-conventions-genai. Field tables fetched directly from:
  - Agent spans: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md — span name `"invoke_agent {gen_ai.agent.name}"`; required: `gen_ai.operation.name`, `gen_ai.provider.name`; conditionally required: `gen_ai.agent.name`, `gen_ai.agent.id`, `gen_ai.conversation.id`.
  - Chat/LLM spans: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md — span name `"{gen_ai.operation.name} {gen_ai.request.model}"` (e.g. `"chat gpt-4"`); required at span creation: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`; recommended: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`.
  - Tool spans: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/reference/reports/execute-tool-span.md — required: `gen_ai.operation.name` (`"execute_tool"`), `gen_ai.tool.name`; recommended: `gen_ai.tool.call.id`, `gen_ai.tool.description`; opt-in: `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`.
  - AWS Bedrock AgentCore confirms it just speaks this standard: "AgentCore emits telemetry data in standardized OpenTelemetry (OTEL)-compatible format" — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html.
- **OpenInference semantic conventions** — https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md. Confirmed fields: `openinference.span.kind` (`"LLM"`/`"TOOL"`/`"CHAIN"`/`"RETRIEVER"`/...), `llm.model_name`, `llm.input_messages.<index>.message.role`/`.content`, `llm.output_messages.<index>.message.role`/`.content`, `llm.token_count.prompt`/`.completion`/`.total`, `tool.name`, `tool.description`, `tool_call.id`, `tool_call.function.name`/`.arguments`.
- **Datadog LLM Observability** confirms it ingests both shapes directly, no translation needed on Datadog's side: "Datadog Agent Observability supports ingesting OpenTelemetry traces that follow either the OpenTelemetry 1.37+ semantic conventions for generative AI or the supported OpenInference semantic conventions" — https://docs.datadoghq.com/llm_observability/instrumentation/otel_instrumentation/.

**Real attribute keys already produced by the runtime today** (confirmed by reading `vidbyte/agents/runtime.py`, since translators must map from what actually exists, not an idealized shape):
- `llm.call` spans (`AgentRuntime._llm_trace_inputs`, line ~1126): `agent_name`, `run_id`, `provider`, `model`, `iteration`, `model_call`, `prompt`, `user_prompt`, `system`, `messages`, `input_messages`, `metadata`, `system_prompt` (conditional).
- `tool.call` spans (`AgentRuntime.execute_tool_call`, line ~930): `tool_name`, `tool_input`, `arguments`, `call_id`, `provider`, `metadata`.
- `agent.run` spans (`AgentTrace.run` in `vidbyte/trace/components/agents.py`): attributes forwarded by the caller (`BaseAgent`), commonly including `agent_name`.

**Environment check performed for this design:** `opentelemetry-sdk` 1.37.0, `opentelemetry-exporter-otlp-proto-http` 1.37.0, and `langsmith` 0.6.7 are installed in this dev environment (confirmed via `pip show`), so this PR's tests can exercise the real OTel SDK (using its `InMemorySpanExporter` test utility) rather than mocking it. `langfuse` is not installed and is out of scope for this change regardless.

---

## 4. Requirements

### Functional Requirements

1. `OTelGenAIProviderTranslator.translate_start(spec)` must set `gen_ai.operation.name="invoke_agent"`, `gen_ai.agent.name`, and (when present in `spec.attributes`) `gen_ai.provider.name`/`gen_ai.conversation.id`, with span name `f"invoke_agent {agent_name}"`, for any `SpanSpec` named `"agent.run"`.
2. `OTelGenAIProviderTranslator.translate_start(spec)` must set `gen_ai.operation.name="chat"`, `gen_ai.provider.name`, `gen_ai.request.model`, with span name `f"chat {model}"`, for any `SpanSpec` with `kind == SpanKind.LLM`.
3. The LLM-span translation must opportunistically map `input_messages` → `gen_ai.input.messages`, `system`/`system_prompt` → `gen_ai.system_instructions`, and any of `input_tokens`/`output_tokens`/`finish_reason` present in attributes → `gen_ai.usage.input_tokens`/`gen_ai.usage.output_tokens`/`gen_ai.response.finish_reasons`, without requiring any of them.
4. `OTelGenAIProviderTranslator.translate_start(spec)` must set `gen_ai.operation.name="execute_tool"`, `gen_ai.tool.name`, and (when present) `gen_ai.tool.call.id`/`gen_ai.tool.call.arguments`, with span name `f"execute_tool {tool_name}"`, for any `SpanSpec` with `kind == SpanKind.TOOL`.
5. For any `SpanSpec` not covered by requirements 1–4 (retriever/embedding/parser/prompt kinds, or Vidbyte-specific components such as `aggregate.*`/`runtime.*`/`algorithm.*`/`middleware.*`/`multi_agent.*`/`session.*`), the translator must preserve the original semantic span name, set `gen_ai.operation.name` to that name, and namespace every other attribute under a `vidbyte.` prefix rather than guessing an unverified `gen_ai.*` field.
6. Missing expected keys (no `model`, no `tool_name`, no `agent_name`) must never raise; the translator must fall back to a stable placeholder (`"unknown"` / `"unknown_tool"` / `"agent"`) for the span name and simply omit the corresponding attribute.
7. `OpenInferenceProviderTranslator.translate_start(spec)` must always set `openinference.span.kind` (`"LLM"`, `"TOOL"`, `"CHAIN"`, `"RETRIEVER"`, `"EMBEDDING"`, or `"CHAIN"` for prompt/parser kinds) on every span it translates, with no exceptions.
8. For `SpanKind.LLM`, the translator must map `model` → `llm.model_name`, expand every entry of `input_messages` into `llm.input_messages.<index>.message.role` / `.message.content`, and opportunistically map `input_tokens`/`output_tokens` → `llm.token_count.prompt`/`.completion` when present.
9. For `SpanKind.TOOL`, the translator must map `tool_name` → `tool.name` and `tool_call.function.name`, `call_id` → `tool_call.id`, and `arguments`/`tool_input` → `tool_call.function.arguments` as a JSON string (not a Python `repr`).
10. Both translators must namespace every attribute they do not explicitly map under a `vidbyte.` prefix, so no Vidbyte-internal field name silently collides with a future addition to either external spec.
11. `OTelTracer.__init__` must raise `TracerConfigurationError` when `opentelemetry-sdk`/`opentelemetry-exporter-otlp-proto-http` are not importable, matching `PhoenixTracer`'s existing message-and-install-hint pattern.
12. `OTelTracer.__init__` must raise `TracerConfigurationError` when no endpoint can be resolved from the `endpoint` argument, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, or `OTEL_EXPORTER_OTLP_ENDPOINT` — unless an `exporter=` override is supplied directly (used by tests and by advanced callers with a custom exporter).
13. `OTelTracer` must accept `headers: Mapping[str, str] | None` (for bearer tokens / SigV4-signed collector auth) and forward them to `OTLPSpanExporter`.
14. `OTelTracer` must accept `service_name: str | None` and set it as the OTel `Resource`'s `service.name`, defaulting to `"vidbyte-agent"` when not supplied, since most OTel backends group traces by resource service name.
15. `OTelTracer.start_span`/`start_trace` must never guess a semantic shape (no name-prefix or `run_type` inspection) — every attribute in the payload it receives must be forwarded to the OTel span exactly as given by whichever translator produced it.
16. `OTelTracer` must coerce every attribute value before calling `span.set_attribute`: primitives (`str`/`bool`/`int`/`float`) pass through unchanged; `None` is skipped entirely; everything else (`dict`, `list`, `tuple`, dataclasses, ...) is JSON-encoded via `json.dumps(value, default=str)` so structured values (tool arguments, message lists) survive as valid JSON rather than an unreadable Python `repr` string or a dropped/rejected attribute.
17. `OTelTracer.start_span` must correctly nest under an explicit `parent` `OTelSpanContext` using `set_span_in_context`, mirroring `PhoenixTracer`'s existing parent-linkage behavior exactly.
18. Every `OTelTracer` method (`start_trace`/`end_trace`/`start_span`/`end_span`) must wrap its body in `try/except Exception` and degrade to a safe empty context / no-op on failure, matching the fail-open contract already established by `PhoenixTracer`/`LangfuseTracer`/`LangSmithTracer`.
19. `PhoenixTracer.start_span` must skip its own `openinference.span.kind` guessing block entirely when that key is already present in the incoming `attributes`, so an upstream translator's explicit value is never overwritten. When the key is absent, existing guessing behavior must be unchanged byte-for-byte.
20. `Trace.otel(endpoint=None, headers=None, service_name=None)` must return a raw `OTelTracer`, mirroring `Trace.phoenix(endpoint=None)`'s shape.
21. `Trace.otel_genai(endpoint=None, headers=None, service_name=None, profile=None)` must return `Trace.profile(Trace.otel(...), profile=profile or TraceProfile.default(), provider="otel-genai")`.
22. `Trace.openinference(endpoint=None, headers=None, service_name=None, profile=None)` must return the same shape as requirement 21 but with `provider="openinference"`.
23. `Trace.phoenix_default(endpoint=None, profile=None)` must return `Trace.profile(Trace.phoenix(endpoint=endpoint), profile=profile or TraceProfile.default(), provider="openinference")`, proving the OpenInference shape works identically through two different inner tracers (the new `OTelTracer` and the existing `PhoenixTracer`).
24. `Trace.otel_genai_session(...)` and `Trace.openinference_session(...)` must exist with the same parameter shape as `Trace.langsmith_session(...)`, returning a `SessionTraceController` wired to the matching translator.
25. `_TraceFactory.resolve_translator("otel-genai")` and `_TraceFactory.resolve_translator("openinference")` must return `OTelGenAIProviderTranslator()`/`OpenInferenceProviderTranslator()`; every other existing string (`None`, `"generic"`, `"langsmith"`) and unknown-string-raises-`ConfigurationError` behavior must be unchanged.
26. A user must be able to enable either shape in a small number of lines, e.g.:
    ```python
    from vidbyte import Agent, Trace
    agent = Agent(..., trace=Trace.otel_genai(endpoint="https://<adot-collector>/v1/traces"))
    # or
    agent = Agent(..., trace=Trace.openinference(endpoint="http://localhost:6006/v1/traces"))
    ```

### Non-Functional Requirements

- **Reliability:** tracing failures must never propagate into agent execution. Both translators are pure functions over already-validated data (no I/O, cannot themselves throw for reasonable inputs); `OTelTracer` fails loud only at construction and fails open on every per-call method, matching the existing two-tier contract used by every other provider adapter in this repo.
- **Security:** translators run on `SpanSpec.attributes` that `TraceController._sanitize_spec` has already redacted (credential-like keys stripped, long strings truncated) and this change must not introduce a second path that re-exposes raw values — translators only ever read from the already-sanitized `spec.attributes`, never from any other source.
- **Performance:** `translate_start` must remain a pure, allocation-light dict transform with no I/O; `OTelTracer`'s attribute coercion (`json.dumps` for non-primitives) is bounded by the same `TraceProfile.max_chars` truncation already applied upstream.
- **Compatibility:** zero changes to any existing public method signature; the only modified existing file (`vidbyte/providers/tracing/phoenix.py`) changes internal behavior only when a caller explicitly pre-sets `openinference.span.kind`, which no current caller does.
- **Observability:** no new logging is required beyond the existing fail-open exception swallowing; `OTelTracer` follows the same silent-degrade convention as `PhoenixTracer` rather than introducing new logging infrastructure.

---

## 5. High-Level Design

Today, a semantic span flows: agent/runtime code calls `self._tracer.start_span("llm.call", **attrs)` → `TraceController` converts the name into a `SpanSpec`, applies `TraceProfile` filtering and redaction, then calls `translator.translate_start(spec)` → the translator returns a `ProviderSpanPayload(name, attributes)` → `TraceController` calls `inner.start_span(payload.name, parent=..., **payload.attributes)` on whatever `TracerBase` it wraps.

This feature adds two new links at the translator step and one new option at the `inner` step, without touching anything upstream of the translator call:

```
Agent / AgentRuntime
  self._tracer.start_span("llm.call", model=..., tool_name=..., ...)
        |
        v
TraceController  (profile filter -> redact/truncate -> SpanSpec)
        |
        v
ProviderTraceTranslator   <-- NEW: OTelGenAIProviderTranslator / OpenInferenceProviderTranslator
        |                       (existing: GenericProviderTranslator, LangSmithProviderTranslator)
        v
ProviderSpanPayload(name, attributes)
        |
        v
inner: TracerBase   <-- NEW: OTelTracer (endpoint=any OTLP-compatible collector)
        |                 (existing: LangSmithTracer, LangfuseTracer, PhoenixTracer)
        v
   OTLP/HTTP  -->  Phoenix  |  Datadog Agent  |  AWS ADOT collector (-> AgentCore/CloudWatch)  |  self-hosted OTel Collector
```

The key design decision is keeping "shape" (the translator) and "destination" (the tracer's configured endpoint) as two independent axes. `OTelTracer` never inspects a span's name or kind to decide what to tag it with — every attribute it receives is forwarded exactly as the translator produced it. This is what makes the OTel GenAI shape work identically whether it is pointed at an AWS collector or a Datadog agent, and what lets the OpenInference shape work identically through either the new `OTelTracer` or the pre-existing `PhoenixTracer` (once the latter's hardcoded guess is taught to yield to an explicit value — Section 6.2).

---

## 6. Detailed Design

### 6.1 `OTelTracer` (new)

**File(s):** `vidbyte/providers/tracing/otel.py`
**Type:** New file

#### What it does

Destination-agnostic OpenTelemetry tracer adapter. Builds real OTel spans and ships them over OTLP/HTTP to any configured endpoint, with no destination-specific attribute guessing.

#### Interface / API

```python
@dataclass
class OTelSpanContext(SpanContext):
    span: Any = field(default=None)
    token: Any = field(default=None)

class OTelTracer(TracerBase):
    def __init__(self, *, endpoint: str | None = None, headers: Mapping[str, str] | None = None, service_name: str | None = None, exporter: Any = None) -> None: ...
    def start_trace(self, name: str, **attributes: Any) -> OTelSpanContext: ...
    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...
    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> OTelSpanContext: ...
    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...
```

#### Logic / Algorithm

1. `__init__` imports `opentelemetry.trace`, `opentelemetry.sdk.resources.Resource`, `opentelemetry.sdk.trace.TracerProvider`, `opentelemetry.sdk.trace.export.SimpleSpanProcessor`; raises `TracerConfigurationError` with an install hint on `ImportError`.
2. If `exporter` is not supplied, `_build_default_exporter` resolves the endpoint (`endpoint` kwarg, then `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT`), raising `TracerConfigurationError` if none resolve, then constructs a real `OTLPSpanExporter(endpoint=..., headers=...)`.
3. Builds a `Resource` with `service.name` (default `"vidbyte-agent"`), a `TracerProvider`, and a `SimpleSpanProcessor` wired to the resolved exporter — mirrors `PhoenixTracer`'s construction exactly, generalized.
4. `start_trace`/`start_span` open a real OTel span (nesting under `parent.span` via `set_span_in_context` when given an `OTelSpanContext` parent), apply `_set_attributes` (Section 6.1 requirement 16 coercion), and return an `OTelSpanContext`. Any exception is caught and an empty `OTelSpanContext()` is returned instead.
5. `end_trace`/`end_span` set `output.value`/`error.message` (and `record_exception`) when given, then call `span.end()`, all inside `try/except Exception: pass`.
6. `_set_attributes(span, attributes)` is a private static helper: skip `None` values; pass `str`/`bool`/`int`/`float` through unchanged; JSON-encode everything else via `json.dumps(value, default=str)`, falling back to `str(value)` only if `json.dumps` itself raises `TypeError`.

#### Edge Cases & Error Handling

- No `opentelemetry-sdk` installed → `TracerConfigurationError` at construction (never at call time).
- No endpoint resolvable and no `exporter=` override → `TracerConfigurationError` at construction.
- `exporter=InMemorySpanExporter()` (test-only path) bypasses endpoint resolution entirely.
- A `dict`/`list` attribute value → valid JSON string, not a Python `repr`.
- A non-JSON-serializable object (e.g. containing a custom class instance) → falls back to `str(value)` rather than raising `TypeError` out of `_set_attributes`.
- `start_span` called with a non-`OTelSpanContext` parent (e.g. a raw `SpanContext` from a different tracer) → treated as no parent, span opens at the current default context, matching `PhoenixTracer`'s existing behavior for the same case.

### 6.2 `PhoenixTracer` compatibility fix

**File(s):** `vidbyte/providers/tracing/phoenix.py`
**Type:** Modified

#### What it does

Lets an upstream `ProviderTraceTranslator` (specifically the new `OpenInferenceProviderTranslator`) set `openinference.span.kind` explicitly without Phoenix's own guess silently overwriting it afterward.

#### Logic / Algorithm

1. In `start_span`, wrap the existing name-prefix/`run_type` guessing block in `if "openinference.span.kind" not in attributes:`. When the key is already present, the earlier attribute-setting loop (`for key, value in attributes.items(): span.set_attribute(key, str(value))`) has already set it correctly, so the guessing block is simply skipped.
2. No other line in `phoenix.py` changes.

#### Edge Cases & Error Handling

- No caller today sets `openinference.span.kind` explicitly, so existing behavior (guessing from `run_type`/name prefix) is unchanged byte-for-byte for every current test and caller.
- When `Trace.phoenix_default(...)` (new, Section 6.4) routes through `OpenInferenceProviderTranslator`, the explicit value now survives.

### 6.3 `vidbyte/providers/tracing/__init__.py`

**File(s):** `vidbyte/providers/tracing/__init__.py`
**Type:** Modified

#### What it does

Exports the new `OTelTracer` alongside the existing three adapters.

```python
from vidbyte.providers.tracing.langfuse import LangfuseTracer
from vidbyte.providers.tracing.langsmith import LangSmithTracer
from vidbyte.providers.tracing.otel import OTelTracer
from vidbyte.providers.tracing.phoenix import PhoenixTracer

__all__ = ["LangfuseTracer", "LangSmithTracer", "OTelTracer", "PhoenixTracer"]
```

### 6.4 `OTelGenAIProviderTranslator` (new)

**File(s):** `vidbyte/trace/providers/otel_genai.py`
**Type:** New file

#### What it does

Maps semantic `SpanSpec` objects into the OpenTelemetry GenAI semantic conventions shape.

#### Interface / API

```python
class OTelGenAIProviderTranslator:
    provider = "otel-genai"
    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload: ...
    # private: _translate_agent, _translate_llm, _translate_tool, _translate_generic, _namespaced_extras
```

#### Logic / Algorithm

1. Dispatch on `spec.name == "agent.run"` → `_translate_agent`; `spec.kind is SpanKind.LLM` → `_translate_llm`; `spec.kind is SpanKind.TOOL` → `_translate_tool`; else → `_translate_generic`.
2. `_translate_agent`: span name `f"invoke_agent {agent_name}"` (`agent_name` from `attributes.get("agent_name", "agent")`); attributes `gen_ai.operation.name="invoke_agent"`, `gen_ai.agent.name`, plus `gen_ai.provider.name`/`gen_ai.conversation.id` when `provider`/`run_id` are present.
3. `_translate_llm`: span name `f"chat {model}"` (`model` from `attributes.get("model", "unknown")`); attributes per Functional Requirements 2–3.
4. `_translate_tool`: span name `f"execute_tool {tool_name}"` (`tool_name` from `attributes.get("tool_name", "unknown_tool")`); attributes per Functional Requirement 4, with `arguments` falling back to `tool_input` if `arguments` absent.
5. `_translate_generic`: span name unchanged (`spec.name`); `gen_ai.operation.name=spec.name`; every attribute namespaced under `vidbyte.`.
6. `_namespaced_extras(attrs, consumed)`: returns `{f"vidbyte.{k}": v for k, v in attrs.items() if k not in consumed}` — applied in every branch so nothing silently drops.

#### Edge Cases & Error Handling

- Missing `model`/`tool_name`/`agent_name` → falls back to `"unknown"`/`"unknown_tool"`/`"agent"`; never raises.
- `input_messages` containing non-`Mapping` entries → skipped for message-role/content expansion (defensive, matches how `_llm_trace_inputs` already only ever produces mapping entries).
- Attribute already redacted upstream (e.g. `[REDACTED]` placeholder string) → passed through unchanged; translator does no additional redaction and does not need to.

### 6.5 `OpenInferenceProviderTranslator` (new)

**File(s):** `vidbyte/trace/providers/openinference.py`
**Type:** New file

#### What it does

Maps semantic `SpanSpec` objects into the OpenInference semantic conventions shape.

#### Interface / API

```python
class OpenInferenceProviderTranslator:
    provider = "openinference"
    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload: ...
    # private: _translate_llm, _translate_tool, _translate_generic, _namespaced_extras
_KIND_TO_OPENINFERENCE = {SpanKind.CHAIN: "CHAIN", SpanKind.LLM: "LLM", SpanKind.TOOL: "TOOL", SpanKind.RETRIEVER: "RETRIEVER", SpanKind.EMBEDDING: "EMBEDDING", SpanKind.PROMPT: "CHAIN", SpanKind.PARSER: "CHAIN"}
```

#### Logic / Algorithm

1. Dispatch on `spec.kind`: `LLM` → `_translate_llm`; `TOOL` → `_translate_tool`; else → `_translate_generic`.
2. Every branch first sets `openinference.span.kind = _KIND_TO_OPENINFERENCE[spec.kind]` (Functional Requirement 7).
3. `_translate_llm`: `llm.model_name` from `model`; iterate `input_messages` (or `messages`) building `llm.input_messages.<i>.message.role`/`.content`; opportunistic `llm.token_count.prompt`/`.completion` from `input_tokens`/`output_tokens`.
4. `_translate_tool`: `tool.name`/`tool_call.function.name` from `tool_name`; `tool_call.id` from `call_id`; `tool_call.function.arguments` = `json.dumps(arguments or tool_input, default=str)`.
5. `_translate_generic`: only sets `openinference.span.kind` plus namespaced extras — no other spec-defined fields apply outside LLM/TOOL per this session's verified research (Non-Goals).
6. Span name is left as the original semantic name in every branch — OpenInference's spec constrains attribute keys and `span.kind`, not span-name text, unlike OTel GenAI.

#### Edge Cases & Error Handling

- `arguments` is a dict containing non-JSON-serializable values → `json.dumps(..., default=str)` covers it.
- No `input_messages` present → loop simply produces zero `llm.input_messages.*` keys, no error.
- Unknown `spec.kind` value → cannot occur; `SpanKind` is a closed `Enum` already validated at `SpanSpec` construction.

### 6.6 `vidbyte/trace/providers/__init__.py`

**File(s):** `vidbyte/trace/providers/__init__.py`
**Type:** Modified

#### What it does

Exports the two new translators alongside the existing ones.

```python
from vidbyte.trace.providers.base import ProviderSpanPayload, ProviderTraceTranslator
from vidbyte.trace.providers.generic import GenericProviderTranslator
from vidbyte.trace.providers.langsmith import LangSmithProviderTranslator
from vidbyte.trace.providers.openinference import OpenInferenceProviderTranslator
from vidbyte.trace.providers.otel_genai import OTelGenAIProviderTranslator

__all__ = [
    "GenericProviderTranslator",
    "LangSmithProviderTranslator",
    "OpenInferenceProviderTranslator",
    "OTelGenAIProviderTranslator",
    "ProviderSpanPayload",
    "ProviderTraceTranslator",
]
```

*(Note: current file has no `__init__.py` content shown in the audit beyond re-exports inferred from `controller.py`'s `from vidbyte.trace.providers import GenericProviderTranslator, ProviderTraceTranslator` and `base.py`'s `from vidbyte.trace.providers import GenericProviderTranslator, LangSmithProviderTranslator, ProviderTraceTranslator` — implementation must read the actual current file first and extend it, not assume this reconstruction is complete.)*

### 6.7 Trace facade additions

**File(s):** `vidbyte/trace/base.py`
**Type:** Modified

#### What it does

Adds the six new/updated public entry points from Functional Requirements 20–25.

#### Interface / API

```python
class Trace:
    @staticmethod
    def otel(endpoint: str | None = None, headers: Mapping[str, str] | None = None, service_name: str | None = None) -> TracerBase: ...
    @staticmethod
    def otel_genai(endpoint: str | None = None, headers: Mapping[str, str] | None = None, service_name: str | None = None, profile: TraceProfile | None = None) -> TraceController: ...
    @staticmethod
    def otel_genai_session(endpoint: str | None = None, headers: Mapping[str, str] | None = None, service_name: str | None = None, name: str | None = None, profile: TraceProfile | None = None) -> SessionTraceController: ...
    @staticmethod
    def openinference(endpoint: str | None = None, headers: Mapping[str, str] | None = None, service_name: str | None = None, profile: TraceProfile | None = None) -> TraceController: ...
    @staticmethod
    def openinference_session(endpoint: str | None = None, headers: Mapping[str, str] | None = None, service_name: str | None = None, name: str | None = None, profile: TraceProfile | None = None) -> SessionTraceController: ...
    @staticmethod
    def phoenix_default(endpoint: str | None = None, profile: TraceProfile | None = None) -> TraceController: ...
```

#### Logic / Algorithm

1. `Trace.otel(...)` imports `OTelTracer` from `vidbyte.providers.tracing` (matching the existing lazy-import-inside-staticmethod pattern used by `Trace.langfuse`/`Trace.langsmith`/`Trace.phoenix`) and constructs it with forwarded kwargs.
2. `Trace.otel_genai(...)` returns `Trace.profile(Trace.otel(endpoint=endpoint, headers=headers, service_name=service_name), profile=profile or TraceProfile.default(), provider="otel-genai")`.
3. `Trace.otel_genai_session(...)` returns `Trace.session(Trace.otel(...), name=name, profile=profile or TraceProfile.default(), provider="otel-genai")`.
4. `Trace.openinference(...)`/`Trace.openinference_session(...)` mirror steps 2–3 with `provider="openinference"`.
5. `Trace.phoenix_default(...)` returns `Trace.profile(Trace.phoenix(endpoint=endpoint), profile=profile or TraceProfile.default(), provider="openinference")`.
6. `_TraceFactory.resolve_translator` gains two new `if` branches (Functional Requirement 25), inserted before the existing `hasattr(provider, "translate_start")` fallback so string names are still resolved first.

#### Edge Cases & Error Handling

- `Trace.otel_genai()` called with no endpoint and no env var set → `TracerConfigurationError` propagates from `OTelTracer.__init__` through `Trace.otel` unchanged (facade does not swallow construction errors, matching every existing `Trace.*` provider helper).
- `resolve_translator("otel-genai")` / `resolve_translator("openinference")` are case-sensitive exact matches, consistent with the existing `"langsmith"` check.

### 6.8 Tests

**File(s):** `tests/test_otel_tracer_transport.py`, `tests/test_otel_genai_trace_shape.py`, `tests/test_openinference_trace_shape.py`
**Type:** New files

Covered in full in Section 10.

### 6.9 Verification script

**File(s):** `scripts/test-trace-shape-prebuilts.py`
**Type:** New file

Runs every case from Section 10 directly against the implementation and prints PASS/FAIL per case plus a final summary, per the design-doc workflow's Phase 5 requirement.

---

## 7. Data Model Changes

N/A — no persisted schema changes. `ProviderSpanPayload`, `SpanSpec`, and every dataclass touched already exist; this feature adds new implementations of existing protocols, not new data shapes.

---

## 8. API Changes

### 8.1 Python API: `Trace.otel_genai`

**Change type:** New

**Request:**
```python
from vidbyte import Agent, Trace
trace = Trace.otel_genai(endpoint="https://my-adot-collector.example.com/v1/traces")
agent = Agent(name="research-agent", system_prompt="...", runner=my_runner, trace=trace)
```

**Response:** agent runs normally; spans are shipped over OTLP/HTTP using `gen_ai.*` attribute names.

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A (raises `TracerConfigurationError`) | `opentelemetry-sdk` not installed |
| N/A (raises `TracerConfigurationError`) | No endpoint resolvable from argument or env vars |

### 8.2 Python API: `Trace.openinference`

**Change type:** New

**Request:**
```python
trace = Trace.openinference(endpoint="http://localhost:6006/v1/traces")
agent = Agent(..., trace=trace)
```

**Response:** agent runs normally; spans carry `openinference.span.kind` plus `llm.*`/`tool.*` attributes.

**Error cases:** identical table to 8.1.

### 8.3 Python API: `Trace.phoenix_default`

**Change type:** New

**Request:**
```python
trace = Trace.phoenix_default()  # uses PHOENIX_COLLECTOR_ENDPOINT / localhost:6006 default
```

**Error cases:** identical table to 8.1, raised from the existing `PhoenixTracer.__init__`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/otel-genai-and-openinference-trace-shapes.md` | This design doc |
| CREATE | `vidbyte/providers/tracing/otel.py` | New destination-agnostic `OTelTracer` transport |
| CREATE | `vidbyte/trace/providers/otel_genai.py` | `OTelGenAIProviderTranslator` |
| CREATE | `vidbyte/trace/providers/openinference.py` | `OpenInferenceProviderTranslator` |
| CREATE | `tests/test_otel_tracer_transport.py` | Transport-layer tests: construction, attribute coercion, parent linkage, real in-memory OTel round trip |
| CREATE | `tests/test_otel_genai_trace_shape.py` | Golden-fixture + facade tests for the OTel GenAI shape |
| CREATE | `tests/test_openinference_trace_shape.py` | Golden-fixture + facade tests for the OpenInference shape |
| CREATE | `scripts/test-trace-shape-prebuilts.py` | Phase 5 verification script |
| MODIFY | `vidbyte/providers/tracing/phoenix.py` | Respect explicit `openinference.span.kind` (Section 6.2) |
| MODIFY | `vidbyte/providers/tracing/__init__.py` | Export `OTelTracer` |
| MODIFY | `vidbyte/trace/providers/__init__.py` | Export `OTelGenAIProviderTranslator`, `OpenInferenceProviderTranslator` |
| MODIFY | `vidbyte/trace/base.py` | Add `Trace.otel/otel_genai/otel_genai_session/openinference/openinference_session/phoenix_default`; extend `_TraceFactory.resolve_translator` |

Summary: 8 files to create, 4 files to modify, 0 files to delete.

---

## 10. Testing Plan

### Unit Tests — `tests/test_otel_tracer_transport.py`

- `it('raises TracerConfigurationError when opentelemetry is not importable')` — [Hidden Assumption] (patch the import to fail)
- `it('raises TracerConfigurationError when no endpoint or env var is set and no exporter override is given')` — [Edge Case]
- `it('accepts an injected exporter and skips endpoint resolution entirely')` — [Hidden Assumption]
- `it('reads OTEL_EXPORTER_OTLP_TRACES_ENDPOINT before OTEL_EXPORTER_OTLP_ENDPOINT')` — [Edge Case]
- `it('sets service.name resource attribute from service_name, defaulting to vidbyte-agent')` — [Silent Failure] (assert the actual `Resource` attribute, not just "it didn't crash")
- `it('coerces a dict attribute value into valid JSON, not a Python repr')` — [Silent Failure] (`json.loads()` the resulting attribute value and compare structurally)
- `it('skips None-valued attributes instead of stringifying them')` — [Edge Case]
- `it('passes str/bool/int/float attributes through unchanged, not JSON-wrapped')` — [Hidden Assumption]
- `it('falls back to str() when a value is not JSON-serializable')` — [Hidden Failure] (pass an object with no `__dict__`/default JSON support)
- `it('nests a child span under an explicit OTelSpanContext parent')` — [Silent Failure] (using the real in-memory exporter, assert the exported child span's `parent.span_id` equals the root's `span_id`)
- `it('start_span degrades to an empty OTelSpanContext instead of raising when the underlying tracer throws')` — [Hidden Failure] (patch `self._tracer.start_span` to raise)
- `it('end_span on a context with span=None is a safe no-op')` — [Edge Case]
- `it('a full start_trace/start_span/end_span/end_trace cycle exports exactly two real OTel spans with the given names')` — [Silent Failure] (real `InMemorySpanExporter`, no mocking of the SDK itself)

### Unit Tests — `tests/test_otel_genai_trace_shape.py`

- `it('translates agent.run into invoke_agent span name and gen_ai.operation.name/gen_ai.agent.name')` — [Silent Failure]
- `it('translates an LLM SpanSpec into chat {model} span name with gen_ai.operation.name/provider.name/request.model')` — [Silent Failure]
- `it('maps input_tokens/output_tokens/finish_reason into gen_ai.usage.*/gen_ai.response.finish_reasons only when present')` — [Hidden Assumption] (assert absence when not present, not a zero/empty default)
- `it('translates a TOOL SpanSpec into execute_tool {tool_name} with gen_ai.tool.name/call.id/call.arguments')` — [Silent Failure]
- `it('falls back to unknown/unknown_tool/agent placeholders when model/tool_name/agent_name are missing, without raising')` — [Hidden Assumption]
- `it('namespaces every unmapped attribute under vidbyte. for a generic (e.g. algorithm.reflexion.trial) SpanSpec, and never emits an invented gen_ai.* field for it')` — [Hidden Failure] (this is the test that would catch quietly inventing an unverified field name)
- `it('output for every required/recommended field name in the golden fixture matches exactly — no typos, no case drift')` — [Silent Failure] (compare against the hardcoded, spec-sourced constant set: `{"gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model"}` for LLM spans, `{"gen_ai.operation.name", "gen_ai.tool.name"}` for tool spans, `{"gen_ai.operation.name", "gen_ai.agent.name"}` for agent spans)
- `it('a secret-shaped attribute key (e.g. api_key) is already absent by the time the translator runs, because TraceController redacted it first')` — [Hidden Assumption] (full-path test: build a `TraceController` with the real `TraceProfile`, run a span with a secret-looking key through it, inspect what the translator actually received)
- `it('resolve_translator("otel-genai") returns an OTelGenAIProviderTranslator instance')` — [Edge Case]
- `it('Trace.otel_genai wraps Trace.otel in a TraceController with the otel-genai translator and TraceProfile.default() when no profile is given')` — [Silent Failure]
- `it('Trace.otel_genai_session returns a SessionTraceController wired to the otel-genai translator')` — [Edge Case]
- `it('Trace.otel_genai propagates TracerConfigurationError from Trace.otel unchanged when no endpoint is configured')` — [Hidden Failure]

### Unit Tests — `tests/test_openinference_trace_shape.py`

- `it('sets openinference.span.kind on every span kind, including kinds with no dedicated mapping')` — [Hidden Assumption] (loop over every `SpanKind` member, assert the key is always present)
- `it('translates an LLM SpanSpec into llm.model_name and expanded llm.input_messages.<i>.message.role/.content')` — [Silent Failure]
- `it('translates a TOOL SpanSpec into tool.name/tool_call.id/tool_call.function.name/.arguments as valid JSON')` — [Silent Failure] (`json.loads()` the arguments value)
- `it('falls back to tool_input when arguments is absent')` — [Hidden Assumption]
- `it('does not mutate the input SpanSpec.attributes mapping')` — [Hidden Failure] (matches the existing `LangSmithProviderTranslator` non-mutation test convention already in `test_semantic_tracing.py`)
- `it('output for the golden fixture required fields matches exactly for both LLM and TOOL spans')` — [Silent Failure] (hardcoded constant sets: `{"openinference.span.kind", "llm.model_name"}`, `{"openinference.span.kind", "tool.name", "tool_call.function.name"}`)
- `it('resolve_translator("openinference") returns an OpenInferenceProviderTranslator instance')` — [Edge Case]
- `it('Trace.openinference wraps Trace.otel in a TraceController with the openinference translator')` — [Silent Failure]
- `it('Trace.phoenix_default wraps the existing PhoenixTracer with the openinference translator, proving the shape works through a second, different inner tracer')` — [Silent Failure] (uses the PhoenixTracer fix from 6.2; asserts the guessed `openinference.span.kind` is the translator's explicit value, not Phoenix's own guess, by picking a span kind — e.g. `RETRIEVER` — where the two would disagree)
- `it('Trace.openinference_session returns a SessionTraceController wired to the openinference translator')` — [Edge Case]

### Integration Tests

- End-to-end: build a `DebugTracer`-free real pipeline — `Trace.profile(inner=OTelTracer(exporter=InMemorySpanExporter()), profile=TraceProfile.verbose(), provider="otel-genai")` — run through a fake `agent.run` → `llm.call` → `tool.call` sequence via direct `TraceController` calls (no real `Agent`/`AgentRuntime` needed, matching how `test_semantic_tracing.py`'s `TraceControllerTests` already exercises the controller directly), and assert the real exported OTel spans have the exact expected `gen_ai.*` attributes and parent/child nesting. Repeat with `provider="openinference"` and `InMemorySpanExporter`.
- Same pipeline with `TraceProfile.minimal()` — assert that spans this profile suppresses (e.g. an `algorithm.reflexion.trial` span) never reach the translator or the exporter at all — verifies profile filtering composes correctly with the two new translators, not just with the existing generic/LangSmith ones.
- Silent-failure path to check explicitly: a translator that quietly returns a payload with the wrong span kind mapped to the wrong `gen_ai.*`/`openinference.*` field would produce a trace that looks superficially fine (valid JSON, spans exist) but would fail a real AWS/Datadog ingestion silently — this is exactly what the golden-fixture exact-match tests above are designed to catch, so no test in this suite should assert "some `gen_ai.*` key exists" without also asserting it is the *specific, correct* key from the spec.
- Hidden assumption the integration surfaces that unit tests cannot: `TraceController`'s `ContextVar`-based parent stack must still correctly nest spans when the `inner` tracer is the new `OTelTracer` rather than `DebugTracer`/`LangSmithTracer` — covered by asserting real exported parent/child `span_id`/`parent.span_id` linkage end-to-end, not just that `translate_start` was called with the right `parent_policy`.

### Manual / QA Test Cases

1. [Edge Case] Given `Trace.otel_genai(endpoint="http://localhost:4318/v1/traces")` pointed at a local `otel-collector` running in debug-exporter mode, when a simple agent runs one tool call, then the collector's console output shows a span named `invoke_agent <name>` containing `chat <model>` and `execute_tool <tool>` children with `gen_ai.*` attributes.
2. [Silent Failure] Given the same setup with `provider="openinference"` instead, when the same agent runs, then every exported span carries `openinference.span.kind` and no span is missing it.
3. [Hidden Failure] Given `Trace.otel_genai()` called with no endpoint and no `OTEL_EXPORTER_OTLP_*` env var set, when constructing the tracer, then a `TracerConfigurationError` is raised immediately, before any agent runs (not a silent no-op tracer).
4. [Hidden Assumption] Given an existing caller using `Trace.phoenix(endpoint=...)` raw (no profile/translator), when it runs today, then its `openinference.span.kind` guessing behavior is byte-for-byte unchanged from before this PR.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `opentelemetry-sdk` (optional, already used by `PhoenixTracer`) | 1.37.0+ (installed in dev env) | `OTelTracer`'s `TracerProvider`/`Resource` | Soft dependency; missing package raises `TracerConfigurationError` at construction only |
| `opentelemetry-exporter-otlp-proto-http` (optional, already used by `PhoenixTracer`) | 1.37.0+ (installed in dev env) | `OTelTracer`'s `OTLPSpanExporter` | Same as above |
| OTel GenAI semantic conventions spec | pre-1.0, actively evolving | Field names for `OTelGenAIProviderTranslator` | Spec drift — mitigated by keeping the internal `SpanSpec`/`SpanKind` model spec-agnostic; only the translator file needs updates if the spec changes |
| OpenInference semantic conventions spec | Arize-maintained, stable core | Field names for `OpenInferenceProviderTranslator` | Same isolation strategy |

No new mandatory dependency is added to `pyproject.toml`.

---

## 12. Rollout & Deployment

- No feature flag; purely additive, matching every prior tracing PR in this repo.
- Not a breaking change — every new public method is new; the one modified existing method (`PhoenixTracer.start_span`) only changes behavior when a caller explicitly pre-sets `openinference.span.kind`, which nothing does today.
- Deployment is a normal SDK package release; no migration needed.
- Rollback: remove the 4 new files under `vidbyte/`, revert the one-line guard in `phoenix.py`, revert the two `__init__.py` export additions, and revert the `Trace.*`/`_TraceFactory.resolve_translator` additions in `base.py`. Existing `Trace.langsmith*`/`Trace.langfuse`/`Trace.phoenix` behavior is the fallback and is untouched throughout.

---

## 13. Open Questions

- [ ] Should `RETRIEVER`/`EMBEDDING`/`PARSER` span kinds get dedicated `gen_ai.*`/OpenInference field mappings in a follow-up, once those parts of each spec are separately verified against the live documents (out of scope here per Non-Goals)?
- [ ] Should `gen_ai.usage.*`/`llm.token_count.*` be backfilled by wiring PR #304's usage/cost tracking (`get_usage`/`get_cost_usd`/`on_usage`) into `llm.call` span attributes in `AgentRuntime`, so both translators' opportunistic usage mapping actually has data to map? Tracked separately; not required for this PR's stopping condition.
- [ ] Should there be an explicit `export_policy` distinct from `TraceProfile` (discussed in a prior conversation this session, not part of this PR) so that "how much do we capture" and "how much of that is safe to ship to an external OTLP endpoint" become independently controllable? This PR does not add that distinction — `TraceProfile.redact`/`max_chars` remain the only safety controls, applied identically regardless of destination.

---

## 14. Alternatives Considered

### Alternative 1: Bake shape logic into `OTelTracer` itself (like `PhoenixTracer` does today)

- What: Give the new `OTelTracer` its own hardcoded `if shape == "otel-genai": ... elif shape == "openinference": ...` branching, instead of two separate `ProviderTraceTranslator` implementations.
- Why rejected: This is exactly the design flaw already present in `PhoenixTracer` that this PR fixes (Section 6.2) rather than repeats. Keeping shape logic in translators means a third shape (or a future spec-version bump) never touches the transport layer, and the same translator already works through any existing or future `TracerBase`.

### Alternative 2: One combined translator with a `shape=` constructor argument instead of two classes

- What: `SemanticShapeTranslator(shape="otel-genai" | "openinference")`.
- Why rejected: The existing pattern (`GenericProviderTranslator`, `LangSmithProviderTranslator` as separate classes, `provider` as a class attribute) is already established and tested; two small classes are more discoverable, more testable in isolation, and consistent with the "Class-Bound Helpers" repo convention (one class, one concern) than one class with an internal mode switch.

### Alternative 3: Extend `PhoenixTracer` itself to accept an `endpoint=` pointing anywhere, instead of adding a new `OTelTracer`

- What: Just generalize `PhoenixTracer`'s endpoint resolution and rename nothing.
- Why rejected: `PhoenixTracer`'s name, its `PHOENIX_COLLECTOR_ENDPOINT` env var default, and its `arize-phoenix` install hint are all Phoenix-specific and used by existing callers who reasonably expect a tracer named "Phoenix" to default to Phoenix's own collector. A separate, honestly-named `OTelTracer` avoids confusing an existing Phoenix user while giving everyone else (AWS/Datadog/self-hosted collector users) a transport that isn't named after a specific vendor's product.

### Alternative 4: Invent plausible `gen_ai.*`/OpenInference field names for retrieval/embedding/parser/Vidbyte-specific spans now, instead of a generic fallback

- What: Guess reasonable-looking field names for span kinds this session's research didn't verify against the live spec.
- Why rejected: The design-doc workflow explicitly forbids inventing unverified APIs/fields without calling it out, and a wrong invented field name is worse than an honest, clearly-namespaced `vidbyte.*` passthrough — it would silently produce a trace that looks compliant but isn't, which is precisely the kind of silent failure this feature exists to prevent for the two spans that matter most (LLM calls and tool calls).
