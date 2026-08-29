# Trace Providers

Provider translators convert Vidbyte's transport-neutral semantic spans into the shape a specific
observability backend expects. `controller.py` produces a `SpanSpec`; a translator here turns it
into a `ProviderSpanPayload` (a name plus an attribute dict) immediately before emission.

## Role In The SDK

Two translators cover every supported backend:

- `LangSmithProviderTranslator` — adds LangSmith's `run_type` attribute.
- `GenericProviderTranslator` — pass-through for debug, custom, null, Langfuse, and Phoenix tracers.

Both satisfy the `ProviderTraceTranslator` protocol in `base.py`, which requires a `provider` string
and `translate_start` / `translate_end` methods over `SpanSpec`.

## Design Philosophy

Semantic naming belongs to the SDK, not to a vendor. A span is described once, in Vidbyte's own
vocabulary, and translated at the boundary. That keeps the tracing call sites free of backend
conditionals and makes adding a backend a matter of adding one translator rather than editing every
instrumentation point.

---

# External Contract

> **sources:** the first-party links in the trace-provider reference table below
> **retrieved:** 2026-08-29
> **verified_by:** `vidbyte/trace/providers/langsmith.py`, `vidbyte/trace/schema.py`
> **scope:** The `run_type` vocabulary and the pass-through contract. Excludes LangSmith's ingestion
> API, auth, and project routing — those are handled in `vidbyte/trace/`.
>
> Written in our own words: `vidbyte-sdk` is MIT-licensed and published to PyPI, and vendor
> documentation is not MIT-licensed.

## Official Trace-Provider Documentation

| Backend | First-party reference | Contract use |
| --- | --- | --- |
| LangSmith | [Run data format](https://docs.langchain.com/langsmith/run-data-format) | `run_type` vocabulary and trace fields |
| LangSmith | [Trace with LangGraph](https://docs.langchain.com/langsmith/trace-with-langgraph) | Framework trace setup |
| Langfuse | [Tracing quickstart](https://langfuse.com/docs/observability/get-started) | Trace ingestion and setup |
| Langfuse | [Data model](https://langfuse.com/docs/observability/data-model) | Traces, observations, and sessions |
| Phoenix | [Tracing integrations](https://arize.com/docs/phoenix/integrations) | OpenTelemetry/OpenInference integrations |
| Phoenix | [Setup Phoenix OTEL](https://www.arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-using-phoenix-otel) | Export and collector setup |

## The `run_type` Coupling — Read This Before Renaming A `SpanKind`

LangSmith classifies every run by a `run_type` string drawn from a fixed vocabulary (`llm`, `chain`,
`tool`, `retriever`, and related values). The UI groups, filters, and costs runs by this field, and
an unrecognized value degrades the trace rather than erroring.

`LangSmithProviderTranslator` maps our semantic span kinds onto that vocabulary by taking the enum
value directly:

```python
@staticmethod
def _run_type(kind: SpanKind) -> str:
    # Returns the LangSmith run_type for every supported semantic kind.
    return kind.value
```

**This makes `SpanKind`'s enum *values* a vendor contract, not an internal naming choice.** The
coupling is invisible at the definition site: `vidbyte/trace/schema.py` looks like an ordinary
internal enum, and nothing there says a value is transmitted verbatim to a third party.

Consequences:

1. **Renaming a `SpanKind` value silently corrupts LangSmith traces.** The code keeps working, spans
   keep being emitted, and the runs land with an invalid `run_type`. There is no error and no
   warning — only a degraded trace view that nobody notices until they need it.
2. **Adding a `SpanKind` requires checking it against LangSmith's vocabulary.** A new kind whose
   value is not a recognized `run_type` produces the same silent degradation for that span type.
3. **The translator uses `setdefault`**, so an explicit `run_type` already present in
   `spec.attributes` wins. That is the escape hatch when a semantic kind must map to a different
   vendor value — prefer it over renaming the enum.

If the enum and the vocabulary need to diverge, replace `kind.value` with an explicit mapping in
this module. That localizes the vendor coupling here, where this README documents it, instead of
leaving it latent in `schema.py`.

## The Generic Translator Covers Three Backends Implicitly

`GenericProviderTranslator`'s docstring names its scope:

> Pass-through translator for debug, custom, null, Langfuse, and Phoenix tracers.

It preserves semantic names and attributes unchanged:

```python
return ProviderSpanPayload(name=spec.name, attributes=dict(spec.attributes))
```

Pass-through is correct for Langfuse and Phoenix because both accept arbitrary span names and
attributes rather than requiring a closed vocabulary. That is a property of those backends, not a
default — a future backend with its own required fields needs a real translator, not this one.

Note the defensive copy: `dict(spec.attributes)` prevents a translator from mutating the caller's
attribute dict, which matters because one `SpanSpec` may be translated for more than one backend.

## Contract Invariants

1. **`SpanKind` values are a vendor contract.** Do not rename one without checking LangSmith's
   `run_type` vocabulary and updating this README.
2. **Translators are pure.** `translate_start` and `translate_end` must not mutate the incoming
   `SpanSpec` or perform I/O. Copy attributes before modifying.
3. **`setdefault`, not assignment.** A caller-supplied attribute always wins over a translator
   default.
4. **`provider` is a stable string.** It is the registry key in `registry.py`.

## Adding A Backend

1. Check whether the backend requires a closed vocabulary for span names or types. If not,
   `GenericProviderTranslator` already covers it — add it to that docstring's list rather than
   writing a new class.
2. If it does, implement `ProviderTraceTranslator` here, and document the vocabulary and the mapping
   in this file with a retrieval date.
3. Register the translator under its `provider` string.
4. Never introduce a second place where a `SpanKind` value is transmitted verbatim to a vendor.
