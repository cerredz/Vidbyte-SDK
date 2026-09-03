# Design Doc: In-Memory OTel GenAI and OpenInference Trace Shapes

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-02
**Last Updated:** 2026-09-02

---

## 1. Overview

This revision makes the OTel GenAI and OpenInference providers in-process trace-shape builders. The agent and runtime already call the TracerBase lifecycle methods for agent.run, llm.call, and tool.call; each new provider will consume those calls directly, map their names and attributes into the selected provider's documented shape, and append plain dictionaries to an optional caller-owned list. The revision removes the new endpoint/export transport and the new shape dataclasses/enums from PR #395. Developers receive inspectable shaped records and may serialize, export, or transform them themselves later.

---

## 2. Goals & Non-Goals

### Goals

- Make Trace.otel_genai(events=None) return a direct in-memory OTel GenAI shape tracer.
- Make Trace.openinference(events=None) return a direct in-memory OpenInference shape tracer.
- Consume the runtime's existing start_trace, start_span, end_span, and end_trace calls without TraceController, SpanSpec, ProviderSpanPayload, or a second translation stage.
- Preserve the exact provider-facing names and documented attributes for agent, LLM, and tool operations where the runtime supplies the source value.
- Preserve parent/child relationships and lifecycle state in inspectable plain dictionaries.
- Keep the existing Langfuse, LangSmith, Phoenix, generic tracer, and legacy semantic translator paths unchanged.
- Document the provider manuals with direct links to the official OTel GenAI and OpenInference specifications.

### Non-Goals

- No HTTP endpoint, OTLP exporter, headers, service-name setting, collector configuration, or provider-specific export implementation.
- No new dataclasses, enums, payload objects, or provider-neutral shape model for this feature.
- No automatic serialization, network delivery, batching, retrying, or destination selection.
- No attempt to invent token counts, finish reasons, output messages, or other values absent from the runtime lifecycle call.
- No new usage model or exporter is added. The existing runtime passes provider-reported usage and finish metadata directly to the active tracer after an LLM response; the direct providers map those raw values when the response supplies them.
- No removal of the pre-existing SpanSpec/ProviderSpanPayload contracts because existing LangSmith and generic semantic tracing still use them.
- No new session/profile facade variants for the two direct shape tracers.

---

## 3. Background & Context

PR #395 originally added two semantic translators, a destination-agnostic OTelTracer, endpoint parameters, transport tests, and typed shape/configuration contracts. That design mixed two responsibilities: choosing a provider's attribute shape and exporting spans to a destination. The requested behavior is narrower: automatically build provider-shaped records during an agent run and leave handling of those records to the developer.

The relevant runtime boundary is already present. BaseAgent.generate_reply() opens agent.run; AgentRuntime._invoke_with_middleware() opens and closes llm.call; and AgentRuntime.execute_tool_call() opens and closes tool.call. Their attributes contain the agent name, run ID, provider, model, messages, prompts, tool names, call IDs, arguments, metadata, and lifecycle output/error values. After a model response, the runtime also forwards the response's existing usage and finish metadata through the optional TracerBase update hook. The new providers therefore map those direct calls without introducing an intermediate trace model.

The field names are based on the official specifications:

- [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai), including the [agent span instructions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md), [GenAI span instructions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md), and [tool span report](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/reference/reports/execute-tool-span.md).
- [OpenInference specification](https://github.com/Arize-ai/openinference/blob/main/spec/README.md), including [semantic conventions](https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md), [LLM spans](https://github.com/Arize-ai/openinference/blob/main/spec/llm_spans.md), and [tool calling](https://github.com/Arize-ai/openinference/blob/main/spec/tool_calling.md).

---

## 4. Requirements

### Functional Requirements

1. Trace.otel_genai(events=None) must return an OTelGenAITrace instance with an .events list; when a list is supplied, the tracer must append to that exact list.
2. Trace.openinference(events=None) must return an OpenInferenceTrace instance with the same caller-owned-list behavior.
3. Both providers must implement the four TracerBase lifecycle methods and receive the runtime's raw operation name and keyword attributes directly.
4. Each started record must be a plain dictionary containing id, type, name, attributes, parent_id, output, error, and status.
5. OTel GenAI agent.run must become invoke_agent {agent_name} with gen_ai.operation.name, gen_ai.agent.name, and optional gen_ai.provider.name/gen_ai.conversation.id from provider/run_id.
6. OTel GenAI llm.call must become chat {model} with gen_ai.operation.name, gen_ai.provider.name, and gen_ai.request.model; optional messages, system instructions, token counts, and finish reasons are included only when supplied.
7. OTel GenAI tool.call must become execute_tool {tool_name} with gen_ai.operation.name, gen_ai.tool.name, and optional call ID/arguments.
8. OpenInference agent.run must be marked openinference.span.kind=AGENT; LLM calls must be marked LLM; tool calls must be marked TOOL; and other recognized runtime names must receive their corresponding documented kind or CHAIN fallback.
9. OpenInference LLM calls must map model to llm.model_name, flatten input messages into indexed llm.input_messages.* attributes, and include token counts only when supplied.
10. OpenInference tool calls must map tool_name, call_id, and JSON-encoded arguments to the documented tool.* and tool_call.* attributes.
11. Unmapped attributes must remain available under a vidbyte. prefix rather than being silently dropped or guessed into an unrelated provider field.
12. Ending a record must update that same dictionary with output or error text and status=ok or status=error; absent values must remain None and status=open until completion.
13. The new provider constructors and facade methods must not accept or resolve an endpoint, headers, service name, profile, session, or exporter.
14. The PR must remove the new destination transport and its tests/docs while preserving pre-existing provider adapters.

### Non-Functional Requirements

- No I/O: Shape construction is synchronous, in-process, and has no network or exporter dependency.
- Low overhead: Each lifecycle start creates one output dictionary and one existing SpanContext handle; no provider-neutral payload object is created.
- Failure tolerance: A malformed or foreign context passed to an end method is a no-op. Normal mapping of arbitrary runtime values must not raise; JSON encoding is used only where OpenInference requires a JSON string for tool arguments.
- Data safety: The providers must not mutate the runtime's input mappings or caller-owned nested values while mapping them.
- Compatibility: Existing tracer adapters and the legacy semantic Trace.profile/translator APIs retain their behavior.

---

## 5. High-Level Design

The direct providers sit at the same boundary as DebugTracer: they implement TracerBase, but their records are already provider-shaped. The runtime calls them directly. A small private lifecycle helper may own record creation and completion mechanics, but it does not define a second schema or payload type; the dictionaries appended to .events are the final developer-visible result.

~~~text
[BaseAgent / AgentRuntime]
        | start_trace/start_span/end_span/end_trace
        v
[OTelGenAITrace] --------> caller-owned list[dict]
[OpenInferenceTrace] ----> caller-owned list[dict]
        |
        +--> developer serializes, exports, or transforms records later

[TraceController + SpanSpec + ProviderSpanPayload]
        | unchanged legacy path for generic/LangSmith semantic tracing
~~~

The provider shape and destination are intentionally separate in this revision: the provider creates records only, and there is no destination axis in the new API. Existing Trace.phoenix(endpoint=...), Trace.langsmith(endpoint=...), and Trace.langfuse(host=...) remain existing export adapters and are not repurposed by these shape providers.

---

## 6. Detailed Design

### 6.1 Shared in-memory lifecycle helper

**File(s):** vidbyte/trace/providers/base.py
**Type:** Modified

#### What it does

Keeps the existing ProviderTraceTranslator protocol and ProviderSpanPayload dataclass for the legacy semantic path, and adds a private TracerBase lifecycle helper for the two new direct providers. The helper owns only dictionary creation, ID assignment, parent ID extraction, and end-state mutation. It does not translate through SpanSpec or create an intermediate provider payload.

#### Interface / API

~~~python
class _InMemoryShapeTrace(TracerBase):
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None: ...
    def start_trace(self, name: str, **attributes: Any) -> SpanContext: ...
    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...
    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext: ...
    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...
    def _shape(self, name: str, attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]: ...
~~~

#### Logic / Algorithm

1. Use the supplied events list by identity, or allocate an empty list.
2. Ask the provider subclass to return the final provider span name and attributes from the raw operation call.
3. Append one final-shape dictionary with a monotonically increasing local ID and the parent record ID, if the parent is one of this tracer's contexts.
4. Return the existing SpanContext class with a reference to that output record as its lifecycle handle; no new context dataclass is introduced.
5. On end, update the referenced record with output or str(error) and set status to ok or error.

#### Edge Cases & Error Handling

- A None parent or a context from another tracer produces parent_id=None.
- A foreign/empty context passed to an end method is ignored.
- A failed JSON conversion for OpenInference tool arguments falls back to str(value) so tracing cannot break agent execution.

### 6.2 OTelGenAITrace

**File(s):** vidbyte/trace/providers/otel_genai.py
**Type:** Modified (replaces the PR's translator)

#### What it does

Maps the raw agent.run, llm.call, and tool.call calls from the runtime directly to the OTel GenAI semantic shape. The class is a TracerBase implementation, not a ProviderTraceTranslator.

#### Interface / API

~~~python
class OTelGenAITrace(_InMemoryShapeTrace):
    def _shape(self, name: str, attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]: ...
~~~

#### Logic / Algorithm

1. For agent.run, use agent_name (or agent) in invoke_agent {agent_name}; map provider to gen_ai.provider.name and run_id to gen_ai.conversation.id when present.
2. For llm.call, use model (or unknown) in chat {model}; map provider and model to the required gen_ai.* fields. Map input_messages/messages, system/system_prompt, usage values, and finish reason only when present.
3. For tool.call, use tool_name (or unknown_tool) in execute_tool {tool_name}; map call ID and arguments/tool_input when present.
4. For any other operation, preserve its name, set gen_ai.operation.name to that operation name, and namespace the remaining raw attributes under vidbyte..
5. For all branches, copy the input mapping before adding provider fields and leave unknown values available under vidbyte..

#### Edge Cases & Error Handling

- Missing names use stable placeholders and never raise.
- Optional fields are absent rather than emitted as None.
- The provider does not invent input_tokens, output_tokens, or finish_reasons; those fields appear only when the direct caller supplies them.

### 6.3 OpenInferenceTrace

**File(s):** vidbyte/trace/providers/openinference.py
**Type:** Modified (replaces the PR's translator)

#### What it does

Maps the raw runtime operations directly to the OpenInference shape using plain attributes. It emits AGENT for agent.run, which is a valid OpenInference span kind for the agent root, and keeps deterministic fallbacks for other runtime names.

#### Interface / API

~~~python
class OpenInferenceTrace(_InMemoryShapeTrace):
    def _shape(self, name: str, attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]: ...
~~~

#### Logic / Algorithm

1. Classify agent.run as AGENT, llm.call as LLM, tool.call as TOOL, retriever.* as RETRIEVER, and embedding.* as EMBEDDING; classify parser/context/unknown operations as CHAIN.
2. For LLM calls, map model to llm.model_name, flatten each mapping message into indexed role/content fields, and map optional token counts.
3. For tool calls, map the tool name and call ID; encode arguments as JSON because OpenInference documents tool_call.function.arguments as a JSON string.
4. Preserve all unconsumed source attributes under vidbyte. and keep the source operation name as the span name.

#### Edge Cases & Error Handling

- Non-mapping message entries are ignored for indexed role/content fields but remain available through the raw vidbyte. attributes.
- Missing model/tool/call values omit optional fields rather than emitting fabricated values.
- Non-JSON arguments use a string fallback and never escape the tracer.

### 6.4 Trace facade

**File(s):** vidbyte/trace/base.py, vidbyte/trace/providers/__init__.py
**Type:** Modified

#### What it does

Exposes the two direct classes through the public facade and exports their names from the trace-provider package. The existing translator resolver remains limited to the legacy generic and LangSmith translators.

#### Interface / API

~~~python
@staticmethod
def otel_genai(events: list[dict[str, Any]] | None = None) -> OTelGenAITrace: ...

@staticmethod
def openinference(events: list[dict[str, Any]] | None = None) -> OpenInferenceTrace: ...
~~~

#### Logic / Algorithm

1. Import the direct provider classes from vidbyte.trace.providers.
2. Construct and return them without TraceController, TraceProfile, endpoint lookup, or exporter setup.
3. Remove the PR-only otel, *_session, phoenix_default, and provider-resolver branches.
4. Leave Trace.profile and Trace.session available for the pre-existing semantic translator architecture.

#### Edge Cases & Error Handling

- A supplied list is retained by identity so the developer can observe it while the agent runs.
- No endpoint/configuration error can occur because these constructors do not perform external setup.
- Existing calls to Trace.profile(..., provider="langsmith") continue to resolve exactly as before.

### 6.5 Removal of destination transport and PR-only shape contracts

**File(s):** vidbyte/providers/tracing/otel.py, vidbyte/providers/tracing/README.md, vidbyte/providers/tracing/__init__.py, vidbyte/providers/tracing/phoenix.py, vidbyte/lib/dataclasses/tracing.py, vidbyte/lib/dataclasses/__init__.py, vidbyte/lib/enums/tracing.py, vidbyte/lib/enums/__init__.py
**Type:** Deleted/Modified

#### What it does

Removes only the destination transport, transport README, shape/configuration dataclasses, and shape-only enums introduced by PR #395. Existing Phoenix behavior is restored because the direct providers do not feed it and it no longer needs an openinference.span.kind override. Existing provider adapters and unrelated library contracts remain.

#### Logic / Algorithm

1. Delete OTelTracer and all endpoint/header/service-name transport code introduced by this PR.
2. Remove its package export and transport test.
3. Restore PhoenixTracer to its pre-PR behavior and retain Trace.phoenix(endpoint=...) as the existing Phoenix export adapter.
4. Remove imports and public exports for the PR-only typed shape/configuration contracts and enums.

#### Edge Cases & Error Handling

- Existing Phoenix callers retain the same endpoint argument and environment fallback.
- No other provider adapter is deleted or rerouted.
- The direct shape providers remain usable without optional OpenTelemetry, Phoenix, LangSmith, or Langfuse packages.

### 6.6 Runtime boundary and documentation

**File(s):** vidbyte/lib/tracing/base.py, vidbyte/agents/runtime.py, skills/sdk/update-skill-files.md, vidbyte/trace/providers/README.md, tests/test_otel_genai_trace_shape.py, tests/test_openinference_trace_shape.py
**Type:** Modified

#### What it does

Documents and tests the direct runtime boundary. No new intermediate runtime model is added. The runtime's existing lifecycle calls are the source of truth; a compatibility-preserving update hook forwards response metadata directly, and the providers map what is present while leaving absent spec fields absent.

#### Interface / API

~~~python
trace = Trace.otel_genai(events)
agent = Agent(...)
await agent.arun("hello")
# events now contains provider-shaped dictionaries
~~~

#### Logic / Algorithm

1. Keep the existing agent.run, llm.call, and tool.call start/end calls.
2. Add a default no-op TracerBase.update_span() hook so existing custom tracers remain compatible.
3. Forward response usage and finish metadata directly from AgentRuntime to that hook after each successful model response.
4. Ensure the direct classes can be installed through the agent's existing tracer path.
5. Update the SDK skill map and provider README so the direct shape providers, not an exporter destination, are discoverable.

#### Edge Cases & Error Handling

- A runtime operation not covered by a provider-specific convention is still captured with a namespaced passthrough.
- Missing runtime response usage or finish metadata remains an honest omission rather than a guessed value.

---

## 7. Data Model Changes

### 7.1 PR-only shape contracts

**Change type:** Deleted

The PR-only typed shape/configuration dataclasses and tracing enums are deleted. No replacement dataclass or schema is introduced. The final developer-visible shape is a plain dict[str, Any] appended to the caller's list:

~~~python
{
    "id": 1,
    "type": "trace" or "span",
    "name": "chat claude-3-5-sonnet",
    "attributes": {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": "claude-3-5-sonnet",
        # optional fields appear only when supplied by the runtime/caller
    },
    "parent_id": None,
    "output": None,
    "error": None,
    "status": "open",
}
~~~

The existing legacy SpanSpec, SemanticSpanContext, and ProviderSpanPayload contracts are unchanged because other tracing APIs still depend on them.

**Migration strategy:** No migration is needed for this unmerged PR. Callers following the old PR #395 endpoint/translator API must use Trace.otel_genai(events) or Trace.openinference(events) and handle the resulting dictionaries themselves.

---

## 8. API Changes

### 8.1 Trace.otel_genai(events=None)

**Change type:** Modified

**Request:** A Python list of dictionaries is optional; no endpoint or transport options are accepted.

~~~python
events: list[dict[str, Any]] | None = None
~~~

**Response:** An OTelGenAITrace implementing TracerBase and exposing .events.

**Error cases:** No network/configuration errors. Invalid lifecycle contexts are ignored by end methods.

### 8.2 Trace.openinference(events=None)

**Change type:** Modified

**Request:** Same as Trace.otel_genai.

**Response:** An OpenInferenceTrace implementing TracerBase and exposing .events.

**Error cases:** Same as Trace.otel_genai.

### 8.3 Removed PR-only transport APIs

**Change type:** Deleted before merge

The PR-only Trace.otel, Trace.otel_genai(... endpoint ...), Trace.openinference(... endpoint ...), session variants, Trace.phoenix_default, and OTelTracer transport constructor are removed. There is no new HTTP endpoint in this design.

---

## 9. File Change Manifest

Complete list of every file changed by this revision:

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | docs/design/otel-genai-and-openinference-trace-shapes.md | Replace the endpoint/export design with the direct in-memory design. |
| MODIFY | vidbyte/lib/tracing/base.py | Add the optional post-response span-attribute hook with a no-op default. |
| MODIFY | vidbyte/agents/runtime.py | Forward response usage and finish metadata directly to the active tracer. |
| MODIFY | vidbyte/trace/providers/base.py | Add shared in-memory lifecycle mechanics while preserving legacy translator contracts. |
| MODIFY | vidbyte/trace/providers/otel_genai.py | Replace the SpanSpec translator with OTelGenAITrace. |
| MODIFY | vidbyte/trace/providers/openinference.py | Replace the SpanSpec translator with OpenInferenceTrace. |
| MODIFY | vidbyte/trace/providers/__init__.py | Export the direct provider classes. |
| MODIFY | vidbyte/trace/base.py | Add list-based direct facade methods and remove PR-only endpoint/session/resolver wiring. |
| MODIFY | vidbyte/providers/tracing/__init__.py | Remove the PR-only OTel transport export. |
| MODIFY | vidbyte/providers/tracing/phoenix.py | Restore pre-PR Phoenix behavior. |
| MODIFY | vidbyte/lib/dataclasses/__init__.py | Remove PR-only shape dataclass exports. |
| MODIFY | vidbyte/lib/enums/__init__.py | Remove PR-only shape enum exports. |
| MODIFY | skills/sdk/update-skill-files.md | Document the direct provider location and no-export scope. |
| MODIFY | vidbyte/trace/providers/README.md | Document direct usage and link official provider manuals. |
| DELETE | vidbyte/providers/tracing/otel.py | Remove destination-agnostic OTLP transport. |
| DELETE | vidbyte/providers/tracing/README.md | Remove transport-specific documentation. |
| DELETE | vidbyte/lib/dataclasses/tracing.py | Remove PR-only typed shape/configuration models. |
| DELETE | vidbyte/lib/enums/tracing.py | Remove PR-only shape/transport enums. |
| DELETE | tests/test_otel_tracer_transport.py | Remove transport tests for deleted functionality. |
| MODIFY | tests/test_otel_genai_trace_shape.py | Test direct OTel GenAI records and runtime wiring. |
| MODIFY | tests/test_openinference_trace_shape.py | Test direct OpenInference records and runtime wiring. |
| MODIFY | scripts/test-trace-shape-prebuilts.py | Run only the direct shape suites. |

---

## 10. Testing Plan

### Unit Tests

- OTelGenAITrace starts an agent, LLM, and tool record with exact names and required attributes. **[Silent Failure]**
- OpenInferenceTrace emits AGENT, LLM, TOOL, RETRIEVER, EMBEDDING, and CHAIN kinds for the supported name patterns. **[Silent Failure]**
- Optional usage, finish-reason, system, message, call-ID, and argument fields appear only when supplied. **[Hidden Assumption]**
- Missing model, agent, and tool names use stable fallbacks without raising. **[Edge Case]**
- Tool arguments are JSON strings for OpenInference and remain available in the OTel shape. **[Silent Failure]**
- Unknown attributes are namespaced and input mappings are not mutated. **[Hidden Failure]**
- End methods update output/error/status on the same dictionary and ignore foreign contexts. **[Edge Case]**
- A caller-supplied list is retained by identity and an omitted list is created. **[Hidden Assumption]**
- Trace.otel_genai and Trace.openinference return direct TracerBase implementations and reject no endpoint because none is accepted. **[Hidden Failure]**
- Deleted transport/dataclass/enum modules are not imported by the new providers. **[Silent Failure]**

### Integration Tests

- Run an existing Agent with each direct tracer and verify that agent.run, llm.call, and tool.call records are populated without TraceController. **[Hidden Failure]**
- Verify the agent's regular execution result is unchanged when the direct tracer is attached. **[Hidden Assumption]**
- Run the focused verification script offline; no network, collector, or optional exporter is required. **[Edge Case]**

### Manual / QA Test Cases

1. Given events=[], when an agent runs with Trace.otel_genai(events), then the same list contains an invoke_agent, chat, and—if a tool is used—execute_tool record. **[Silent Failure]**
2. Given events=[], when an agent runs with Trace.openinference(events), then each record has openinference.span.kind and parent IDs connect children to the agent record. **[Silent Failure]**
3. Given no runtime usage metadata, when an LLM call is captured, then no fabricated token count or finish reason is emitted. **[Hidden Assumption]**
4. Given an unreachable collector URL, when a direct shape tracer is constructed, then construction still succeeds because no network transport exists. **[Edge Case]**

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|-------------------|---------|------|
| None added | N/A | In-memory dictionary capture only. | None beyond ordinary Python runtime behavior. |
| OTel GenAI specification | Official GitHub manuals linked in Section 3 | Defines field names and span naming used by the OTel shape. | Specification revisions may require future mapping updates. |
| OpenInference specification | Official GitHub manuals linked in Section 3 | Defines span kinds and LLM/tool attribute names. | Specification revisions may require future mapping updates. |

No external service is contacted by this feature.

---

## 12. Rollout & Deployment

- No feature flag or deployment ordering is required.
- This changes the unmerged PR #395 API before release; the endpoint/export API is removed rather than deprecated.
- Existing provider adapters are not migrated and continue to operate through their existing APIs.
- Rollback is a normal git revert of the implementation commits on the existing PR branch.

---

## 13. Open Questions

- [ ] Should a future revision add a session/root grouping helper around the caller-owned event list, after the direct single-run shape is established?
- [x] Should the runtime pass provider-reported token counts and finish reasons to the direct shape provider automatically? Yes; it uses the compatibility-preserving update hook and leaves missing values absent.
- [ ] Should a future revision define output-message mappings after confirming the exact current provider specification versions?

---

## 14. Alternatives Considered

### Alternative 1: Keep the SpanSpec -> ProviderSpanPayload pipeline

- **What:** Keep using TraceController and add two new translator classes.
- **Why rejected:** It adds an intermediate semantic model and payload layer between the runtime's existing lifecycle calls and the requested provider-shaped dictionaries.

### Alternative 2: Keep OTelTracer and endpoint-based exporting

- **What:** Build provider-shaped attributes and immediately send them through OTLP/HTTP.
- **Why rejected:** Exporting is outside this feature. It creates destination configuration, network failure, and ownership concerns before developers can inspect or handle the generated shapes.

### Alternative 3: Add typed dataclasses/enums for every shape field

- **What:** Represent provider configurations and payloads with new frozen dataclasses and enum constants.
- **Why rejected:** The requested API is direct runtime-to-shape capture; extra typed models would recreate the intermediate data layer the revision is removing.

### Alternative 4: Route the new shapes through Phoenix

- **What:** Use Phoenix's existing OTel adapter as the destination and modify it to accept the new fields.
- **Why rejected:** Phoenix is an existing exporter, not the requested in-memory shape output, and routing through it would prevent developers from owning the generated records.
