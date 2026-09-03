# Trace shape providers

These providers build provider-shaped trace dictionaries in memory. They are
not exporters and do not send anything over the network.

The agent runtime already emits these lifecycle calls:

- agent.run from BaseAgent.generate_reply()
- llm.call from AgentRuntime._invoke_with_middleware()
- tool.call from AgentRuntime.execute_tool_call()

The shape provider receives those calls directly. There is no
TraceController, SpanSpec, ProviderSpanPayload, endpoint, exporter, or
new provider-specific dataclass in this path.

The initial agent.run and llm.call records use the attributes already supplied
by the agent and runtime. After a successful model response, the runtime passes
the response's existing usage and finish metadata directly to the active
provider shape. This is why the token and finish-reason fields in the examples
appear automatically when the selected model adapter reports them.

## Usage

Pass an optional list to keep ownership of the generated records:

~~~python
from vidbyte.trace import Trace

events: list[dict] = []
trace = Trace.otel_genai(events)
agent = Agent(..., trace=trace)
await agent.arun("Research this question")

# The same list now contains the completed provider-shaped records.
print(events)
~~~

Use Trace.openinference(events) for the OpenInference shape. If no list is
provided, the tracer exposes its own list as trace.events.

Each record is a plain dictionary:

~~~python
{
    "id": 1,
    "type": "trace",  # or "span"
    "name": "chat claude-3-5-sonnet",
    "attributes": {...},
    "parent_id": 1,  # None for a root record
    "output": "final answer",
    "error": None,
    "status": "ok",  # "open" while running, "error" on failure
}
~~~

The caller can serialize, export, filter, or transform these dictionaries.
This package intentionally does none of those things.

## OTel GenAI shape

Implementation: OTelGenAITrace in otel_genai.py.

### Agent record

agent.run becomes:

~~~json
{
  "name": "invoke_agent researcher",
  "attributes": {
    "gen_ai.operation.name": "invoke_agent",
    "gen_ai.agent.name": "researcher",
    "gen_ai.provider.name": "anthropic",
    "gen_ai.conversation.id": "run-123"
  }
}
~~~

gen_ai.provider.name and gen_ai.conversation.id are included when the
runtime supplies provider and run_id.

### LLM record

llm.call becomes the shape in the question:

~~~json
{
  "name": "chat claude-3-5-sonnet",
  "attributes": {
    "gen_ai.operation.name": "chat",
    "gen_ai.provider.name": "anthropic",
    "gen_ai.request.model": "claude-3-5-sonnet",
    "gen_ai.input.messages": "...",
    "gen_ai.system_instructions": "...",
    "gen_ai.usage.input_tokens": 145,
    "gen_ai.usage.output_tokens": 62,
    "gen_ai.response.finish_reasons": ["stop"]
  }
}
~~~

The message, system, token, and finish-reason attributes are optional. They
are emitted only when the direct runtime call supplies the corresponding
source values. Runtime-only values that do not have a verified OTel GenAI
mapping remain under vidbyte.*.

### Tool record

tool.call becomes:

~~~json
{
  "name": "execute_tool web_search",
  "attributes": {
    "gen_ai.operation.name": "execute_tool",
    "gen_ai.tool.name": "web_search",
    "gen_ai.tool.call.id": "call-1",
    "gen_ai.tool.call.arguments": {
      "query": "vidbyte"
    }
  }
}
~~~

### Direct OTel GenAI manuals

- [OTel GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
- [GenAI agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
- [GenAI inference/chat spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md)
- [Execute tool span](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/reference/reports/execute-tool-span.md)

## OpenInference shape

Implementation: OpenInferenceTrace in openinference.py.

### Agent record

agent.run becomes:

~~~json
{
  "name": "agent.run",
  "attributes": {
    "openinference.span.kind": "AGENT",
    "agent.name": "researcher"
  }
}
~~~

### LLM record

llm.call becomes:

~~~json
{
  "name": "llm.call",
  "attributes": {
    "openinference.span.kind": "LLM",
    "llm.system": "anthropic",
    "llm.provider": "anthropic",
    "llm.model_name": "claude-3-5-sonnet",
    "llm.input_messages.0.message.role": "user",
    "llm.input_messages.0.message.content": "hello",
    "llm.token_count.prompt": 145,
    "llm.token_count.completion": 62,
    "llm.finish_reason": "stop"
  }
}
~~~

### Tool record

tool.call becomes:

~~~json
{
  "name": "tool.call",
  "attributes": {
    "openinference.span.kind": "TOOL",
    "tool.name": "web_search",
    "tool_call.function.name": "web_search",
    "tool_call.id": "call-1",
    "tool_call.function.arguments": "{\"query\": \"vidbyte\"}"
  }
}
~~~

### Direct OpenInference manuals

- [OpenInference specification](https://github.com/Arize-ai/openinference/blob/main/spec/README.md)
- [OpenInference traces](https://github.com/Arize-ai/openinference/blob/main/spec/traces.md)
- [Semantic conventions](https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md)
- [LLM spans](https://github.com/Arize-ai/openinference/blob/main/spec/llm_spans.md)
- [Tool and function calling](https://github.com/Arize-ai/openinference/blob/main/spec/tool_calling.md)

## Existing export adapters

vidbyte/providers/tracing/ contains the pre-existing Langfuse, LangSmith,
and Phoenix exporters. The OTel GenAI and OpenInference classes in this folder
do not route through those adapters. Developers may choose their own handling
for the generated dictionaries.
