<!--
Context Protocol Header

Description:
    Skill for tracing provider integrations in the Vidbyte SDK.
Purpose:
    Documents the three integrated providers, the critical distinction between
    semantic translators and external adapters, the provider= argument, and how
    to add a new provider.
Architecture:
    - Covers vidbyte/trace/providers/ (translators: base, generic, langsmith).
    - Covers vidbyte/providers/tracing/ (adapters: langsmith, langfuse, phoenix).
    - Covers _TraceFactory.resolve_translator in vidbyte/trace/base.py.
Relations:
    Sub-skill of skills/tracing/SKILL.md. Pairs with enabling-tracing.md
    (Trace facade helpers) and trace-controller-and-session.md (how the
    translator is invoked).
-->

# Trace Providers

The SDK integrates with three tracing backends — **LangSmith**, **Langfuse**, and
**Arize Phoenix** — and provides a generic pass-through for any other
`TracerBase`. The most important concept is the split between **translators**
and **adapters**.

## Two Layers of Provider Code

| Layer | Folder | Calls external SDKs? | Responsibility |
|-------|--------|-----------------------|----------------|
| **Translators** | `vidbyte/trace/providers/` | No | Convert a semantic `SpanSpec` into a provider-facing name + attributes (e.g. add LangSmith `run_type`). |
| **Adapters** | `vidbyte/providers/tracing/` | Yes | Implement `TracerBase` against a real backend client (`langsmith.Client`, `langfuse.Langfuse`, OpenTelemetry). |

The `TraceController` calls the translator to build the payload, then calls the
adapter (the `inner` tracer) to actually open/close the span. A translator never
makes a network call; an adapter never knows about semantic profiles.

## Integrated Providers

| Provider | Install | Env vars (constructor kwargs override) | Default |
|----------|---------|----------------------------------------|---------|
| LangSmith | `pip install langsmith` | `LANGSMITH_API_KEY` (required), `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT` | project `default` |
| Langfuse | `pip install langfuse` | `LANGFUSE_PUBLIC_KEY` (required), `LANGFUSE_SECRET_KEY` (required), `LANGFUSE_HOST` | host `https://cloud.langfuse.com` |
| Phoenix | `pip install arize-phoenix opentelemetry-sdk opentelemetry-exporter-otlp-proto-http` | `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` |

Missing optional packages raise `TracerConfigurationError` with an install hint.

## The `Trace.*` Provider Helpers

```python
from vidbyte import Trace

trace = Trace.langsmith(api_key="...", project="vidbyte-agents")
trace = Trace.langfuse(public_key="...", secret_key="...", host="...")
trace = Trace.phoenix(endpoint="http://localhost:6006/v1/traces")
```

These return **raw adapters** (low-level `TracerBase`). To get the recommended
semantic shape, use the wrappers that combine an adapter with a profile and a
translator:

```python
trace = Trace.langsmith_default(api_key="...", project="vidbyte-agents")  # default profile
trace = Trace.langsmith_verbose(api_key="...", project="vidbyte-agents")  # verbose profile
trace = Trace.langsmith_session(api_key="...", project="vidbyte-agents", name="workflow")
```

`Trace.langsmith_default` is the recommended single-agent LangSmith preset. It is
exactly `Trace.profile(Trace.langsmith(...), profile=TraceProfile.default(), provider="langsmith")`.

## LangSmith `run_type` Mapping

The `LangSmithProviderTranslator` (`vidbyte/trace/providers/langsmith.py`) adds a
`run_type` attribute to every span payload, set to the `SpanKind` value:

| `SpanKind` | `run_type` |
|------------|------------|
| `CHAIN` | `chain` |
| `LLM` | `llm` |
| `TOOL` | `tool` |
| `RETRIEVER` | `retriever` |
| `EMBEDDING` | `embedding` |
| `PROMPT` | `prompt` |
| `PARSER` | `parser` |

```python
class LangSmithProviderTranslator:
    provider = "langsmith"

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        attributes = dict(spec.attributes)
        attributes.setdefault("run_type", self._run_type(spec.kind))
        return ProviderSpanPayload(name=spec.name, attributes=attributes)

    @staticmethod
    def _run_type(kind: SpanKind) -> str:
        return kind.value
```

The `GenericProviderTranslator` (used for debug, custom, null, Langfuse, and
Phoenix tracers) is a pass-through: it preserves the semantic name and
attributes without adding anything.

## The `provider=` Argument

`Trace.profile(inner, profile=None, provider=None)` and `Trace.session(...)` take
a `provider` argument that selects the translator. Resolution lives in
`_TraceFactory.resolve_translator`:

| `provider` value | Resolves to |
|------------------|-------------|
| `None` or `"generic"` | `GenericProviderTranslator` |
| `"langsmith"` | `LangSmithProviderTranslator` |
| an object with a `translate_start` method | used as-is (custom translator) |
| anything else | raises `ConfigurationError` |

```python
from vidbyte import Trace, TraceProfile

# LangSmith translator (adds run_type) over a debug tracer.
trace = Trace.profile(inner=Trace.debug([]), profile=TraceProfile.default(), provider="langsmith")

# Custom translator instance.
trace = Trace.profile(inner=Trace.debug([]), profile=TraceProfile.default(), provider=my_translator)
```

## Provider Adapter Behavior

### `LangSmithTracer` (`vidbyte/providers/tracing/langsmith.py`)

- Resolves `api_key` from kwarg or `LANGSMITH_API_KEY` (raises if absent).
- `LangSmithSpanContext` carries `run_id`, `parent_run_id`, `trace_id` so child
  runs attach to the right parent and trace.
- `strict=True` makes LangSmith delivery errors raise
  `TracerConfigurationError`; by default they are recorded in `last_error` and
  swallowed (fail open).
- `_resolve_run_type(name, explicit)` classifies by name prefix (`llm.` → `llm`,
  `tool.` → `tool`, else `chain`) **unless** an explicit `run_type` is popped
  from attributes — which is exactly what the LangSmith translator sets.
- `_redact` scrubs `lsv2_…` and `xai-…` key shapes from diagnostic strings.
- `_flush` flushes the client after each end call when a `flush` method exists.

### `LangfuseTracer` (`vidbyte/providers/tracing/langfuse.py`)

- Resolves `public_key`/`secret_key` from kwargs or env (both required).
- `LangfuseSpanContext` carries the langfuse trace/span `handle`.
- Child spans under a parent use `parent.generation(name=...)` for `llm.` spans
  and `parent.span(name=...)` otherwise.
- Fail open: every backend call is wrapped in `try/except` so trace errors never
  abort the run.

### `PhoenixTracer` (`vidbyte/providers/tracing/phoenix.py`)

- Builds an OpenTelemetry `TracerProvider` with an `OTLPSpanExporter` pointed at
  the Phoenix collector endpoint.
- `PhoenixSpanContext` carries the OTel `span` and a `token` from `use_span`.
- Sets `openinference.span.kind`: `LLM` for `llm.` names or `run_type == "llm"`,
  `TOOL` for `tool.` names or `run_type == "tool"`, otherwise the uppercased
  `run_type`.
- Records exceptions and sets `output.value` / `error.message` attributes.

## Adding a New Provider

1. **External adapter** — add `vidbyte/providers/tracing/<name>.py` implementing
   `TracerBase` against the backend's client. Resolve credentials from kwargs
   first, then env vars. Re-export it from `vidbyte/providers/tracing/__init__.py`.
2. **Facade helper** — add a `Trace.<name>(...)` `@staticmethod` in
   `vidbyte/trace/base.py` that builds your adapter (import it lazily inside the
   method, like `Trace.langsmith` does).
3. **Optional translator** — if the provider needs semantic-field translation
   (like LangSmith's `run_type`), add `vidbyte/trace/providers/<name>.py`
   implementing the `ProviderTraceTranslator` protocol and re-export it from
   `vidbyte/trace/providers/__init__.py`.
4. **Register the translator name** — add a branch for the provider name in
   `_TraceFactory.resolve_translator` (`vidbyte/trace/base.py`).
5. **Docs** — update `vidbyte/trace/README.md` and `llms.txt`, and add the
   provider to this skill and to `trace-types.md`.

See `updating-the-tracer.md` for the full file-by-file checklist.
