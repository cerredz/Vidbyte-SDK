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

## Expanded Trace-Provider Reading Maps

The translator contract is small, but the systems receiving these spans are
not. These maps keep the operational pages that explain the fields, SDKs,
instrumentation, retention, evaluation, and integrations adjacent to the
translator boundary. **Retrieved:** 2026-08-29.

### LangSmith

- [Tracing quickstart](https://docs.langchain.com/langsmith/observability-quickstart)
- [Observability concepts](https://docs.langchain.com/langsmith/observability-concepts)
- [Run data format](https://docs.langchain.com/langsmith/run-data-format)
- [Trace with LangGraph](https://docs.langchain.com/langsmith/trace-with-langgraph)
- [Trace with OpenTelemetry](https://docs.langchain.com/langsmith/trace-with-opentelemetry)
- [Trace with Codex](https://docs.langchain.com/langsmith/trace-with-codex)
- [Trace with Cursor](https://docs.langchain.com/langsmith/trace-with-cursor)
- [Trace Bedrock](https://docs.langchain.com/langsmith/trace-bedrock)
- [LangSmith reference](https://docs.langchain.com/langsmith/reference)
- [Custom endpoint](https://docs.langchain.com/langsmith/custom-endpoint)
- [Custom middleware](https://docs.langchain.com/langsmith/custom-middleware)
- [Cloud environment variables](https://docs.langchain.com/langsmith/env-var-cloud)
- [Agent-server distributed tracing](https://docs.langchain.com/langsmith/agent-server-distributed-tracing)
- [Audit evaluator scores](https://docs.langchain.com/langsmith/audit-evaluator-scores)
- [Cron jobs](https://docs.langchain.com/langsmith/cron-jobs)
- [Remote MCP servers](https://docs.langchain.com/langsmith/fleet/remote-mcp-servers)
- [Terraform management](https://docs.langchain.com/langsmith/manage-with-terraform)
- [Prompt engineering concepts](https://docs.langchain.com/langsmith/prompt-engineering-concepts)
- [Delete traces](https://docs.langchain.com/langsmith/script-delete-traces)
- [Self-hosted agent-server metrics](https://docs.langchain.com/langsmith/self-hosted-agent-server-metrics)
- [Shared run API](https://docs.langchain.com/langsmith/smith-api/public/get-shared-run-by-id)
- [Feedback configuration API](https://docs.langchain.com/langsmith/smith-api/feedback-configs/delete-feedback-config-endpoint)
- [Server information API](https://docs.langchain.com/langsmith/smith-api/info/get-server-info)
- [Query threads API](https://docs.langchain.com/langsmith/smith-api/threads/query-threads)
- [Workspace secrets API](https://docs.langchain.com/langsmith/smith-api/workspaces/list-current-workspace-secrets)

### Langfuse

- [Observability quickstart](https://langfuse.com/docs/observability/get-started)
- [Observability data model](https://langfuse.com/docs/observability/data-model)
- [SDK overview](https://langfuse.com/docs/observability/sdk/overview)
- [Python SDK](https://langfuse.com/docs/observability/sdk/python)
- [JavaScript and TypeScript SDK](https://langfuse.com/docs/observability/sdk/js)
- [Tracing](https://langfuse.com/docs/observability/features/tracing)
- [Observations](https://langfuse.com/docs/observability/features/observations)
- [Generations](https://langfuse.com/docs/observability/features/generations)
- [Sessions](https://langfuse.com/docs/observability/features/sessions)
- [Scores](https://langfuse.com/docs/observability/features/scores)
- [User feedback](https://langfuse.com/docs/observability/features/user-feedback)
- [Prompt management](https://langfuse.com/docs/prompt-management/get-started)
- [Prompt versioning](https://langfuse.com/docs/prompt-management/features/overview)
- [Datasets](https://langfuse.com/docs/datasets/overview)
- [Evaluations](https://langfuse.com/docs/evaluation/overview)
- [Annotation queues](https://langfuse.com/docs/evaluation/evaluation-methods/annotation)
- [LangChain integration](https://langfuse.com/docs/integrations/langchain)
- [LangGraph integration](https://langfuse.com/docs/integrations/langgraph)
- [OpenAI integration](https://langfuse.com/docs/integrations/openai)
- [Anthropic integration](https://langfuse.com/docs/integrations/anthropic)
- [Vercel AI SDK integration](https://langfuse.com/docs/integrations/vercel-ai-sdk)
- [LlamaIndex integration](https://langfuse.com/docs/integrations/llama-index)
- [OpenTelemetry](https://langfuse.com/docs/opentelemetry/get-started)
- [Self-hosting](https://langfuse.com/docs/deployment/self-host)
- [Cloud deployment](https://langfuse.com/docs/deployment/cloud)

### Phoenix

- [Phoenix overview](https://arize.com/docs/phoenix)
- [Tracing overview](https://arize.com/docs/phoenix/tracing)
- [Tracing integrations](https://arize.com/docs/phoenix/tracing/integrations-tracing)
- [Your first traces](https://arize.com/docs/phoenix/tracing/tutorial/your-first-traces)
- [Phoenix OTEL setup](https://arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-using-phoenix-otel)
- [Phoenix client setup](https://arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-using-phoenix-client)
- [OpenTelemetry setup](https://arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-using-opentelemetry)
- [Collect traces](https://arize.com/docs/phoenix/tracing/how-to-tracing/collect-traces)
- [Trace attributes](https://arize.com/docs/phoenix/tracing/how-to-tracing/trace-attributes)
- [Trace annotations](https://arize.com/docs/phoenix/tracing/how-to-tracing/trace-annotations)
- [Tracing monitoring](https://arize.com/docs/phoenix/tracing/how-to-tracing/monitoring)
- [Integrations overview](https://arize.com/docs/phoenix/integrations)
- [Tracing integrations index](https://arize.com/docs/phoenix/tracing/integrations-tracing)
- [Python API](https://arize.com/docs/phoenix/resources/python-api)
- [Phoenix OTEL Python API](https://arize.com/docs/phoenix/sdk-api-reference/python/arize-phoenix-otel)
- [Phoenix client API](https://arize.com/docs/phoenix/sdk-api-reference/python/arize-phoenix-client)
- [Phoenix evaluation](https://arize.com/docs/phoenix/evaluation)
- [Datasets and experiments](https://arize.com/docs/phoenix/datasets-and-experiments)
- [Prompt engineering](https://arize.com/docs/phoenix/prompt-engineering)
- [LangChain integration](https://arize.com/docs/phoenix/integrations/frameworks/langchain)
- [LangGraph integration](https://arize.com/docs/phoenix/integrations/frameworks/langgraph)
- [OpenAI integration](https://arize.com/docs/phoenix/integrations/llm-providers/openai)
- [Anthropic integration](https://arize.com/docs/phoenix/integrations/llm-providers/anthropic)
- [Deployment](https://arize.com/docs/phoenix/deployment)
- [Self-hosting](https://arize.com/docs/phoenix/deployment/self-hosting)

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
