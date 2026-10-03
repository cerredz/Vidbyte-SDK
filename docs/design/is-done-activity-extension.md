# Design Doc: Configurable IsDone Activity Annotations

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-03
**Last Updated:** 2026-09-03

---

## 1. Overview

Add a public is_done_activity configuration point to BaseAgent and AgentRuntime. The runtime will decorate its existing internal IsDoneTool with the SDK's established ToolActivity wrapper, allowing applications to receive typed model-authored completion metadata without replacing or reimplementing loop-control behavior. The existing ToolActivity schema generation, validation, call normalization, middleware visibility, and ToolCallContext capture remain the single implementation path.

---

## 2. Goals & Non-Goals

### Goals

- Allow a developer to bind one typed ToolActivity schema to the internal isDone tool.
- Make the activity declaration visible to the model as a nested activity property in the provider tool schema.
- Preserve existing isDone stopping, output-schema validation, permission, internal-tool accounting, and result behavior.
- Preserve the captured annotation on ToolCallContext.activity and final runtime metadata.
- Support agents built directly by BaseAgent and agents created through the SDK YAML loader plus application-side wiring.
- Document the public configuration and add regression coverage for schema, capture, execution separation, and loop termination.

### Non-Goals

- Do not make IsDoneTool a developer-replaceable public tool.
- Do not change the isDone tool name, final-answer argument, or stop-reason contract.
- Do not add a new activity wrapper implementation; reuse BaseTool.with_activity().
- Do not change non-linear runtimes that do not use the direct AgentRuntime loop.
- Do not persist activity payloads or introduce application-specific recommendation fields in the SDK.

---

## 3. Background & Context

- The direct runtime injects IsDoneTool through with_internal_agent_tools() and replaces any same-named user tool. This ownership is required because the runtime identifies the stop signal by the stable isDone name and finalizes the loop immediately.
- BaseTool.with_activity() already adds a typed nested annotation to an existing tool, validates it before execution, removes it from business arguments, and preserves it on ToolCallContext.activity.
- BaseAgent constructs AgentRuntime lazily, so an activity setting stored on the agent can be wired without changing session execution or tool catalogs.
- The feature must remain generic. Applications such as the research harness own the activity Pydantic model and its interpretation; the SDK only exposes the typed annotation mechanism.

---

## 4. Requirements

### Functional Requirements

1. BaseAgent accepts an optional is_done_activity: ToolActivity | None setting.
2. AgentRuntime accepts the same optional setting.
3. When internal tools are enabled and the setting is present, the runtime registers IsDoneTool().with_activity(is_done_activity) under the existing isDone name.
4. When the setting is absent, the generated isDone schema and behavior remain byte-compatible with current behavior.
5. When a model supplies a valid activity, the SDK removes activity before calling IsDoneTool.execute() and preserves the normalized payload on the resulting ToolCallContext.
6. A missing or invalid required activity produces the existing activity validation error and does not stop the loop as a successful isDone call.
7. The final result still uses isDone output as the final answer and still applies the configured output schema.
8. A fluent with_is_done_activity() helper is available for application factories that build agents from declarative settings and attach runtime-specific objects afterwards.
9. The setting is documented as a generic completion annotation and not as a research-specific feature.

### Non-Functional Requirements

- Preserve the existing wrapper identity and unwrapping behavior used by pricing and tool accounting.
- Preserve provider-schema parity across OpenAI, Anthropic, and Gemini formatters through the existing formatter path.
- Keep the activity payload bounded by the caller-provided Pydantic schema; the SDK must not impose application-specific fields.
- Keep the internal tool private and prevent an activity setting from changing authorization or loop accounting.
- Maintain source-stage, package-stage, and full SDK CI compatibility.

---

## 5. High-Level Design

The runtime remains the owner of IsDoneTool. with_internal_agent_tools() will construct the internal tool, optionally apply BaseTool.with_activity(), and register the resulting wrapper with replace=True. This preserves the existing protection against a user-supplied tool named isDone while allowing the runtime to expose a typed annotation declaration.

BaseAgent stores the optional ToolActivity and passes it to the runtime it constructs. The existing activity formatter adds the nested schema to provider declarations, validates and separates the model's activity argument, and copies it into ToolCallContext. No new result or tracing shape is needed.

~~~text
[Developer ToolActivity]
          |
          v
[BaseAgent.is_done_activity]
          |
          v
[AgentRuntime]
          |
          v
[IsDoneTool().with_activity(...)]
          |
          +--> provider schema: isDone(final_answer, activity)
          +--> runtime call context: ToolCallContext.activity
          +--> existing loop stop and final-answer path
~~~

---

## 6. Detailed Design

### 6.1 Internal IsDone Injection

**File(s):** vidbyte/tools/_internal.py
**Type:** Modified

#### What it does

Extend the existing internal-tool injection helper with an optional ToolActivity. The helper will decorate the internal tool before catalog registration.

#### Interface / API

~~~python
def with_internal_agent_tools(tools: Tools, *, is_done_activity: ToolActivity | None = None) -> Tools:
    """Return a runtime-only catalog with internal loop-control tools included."""
~~~

#### Logic / Algorithm

1. Construct IsDoneTool() exactly as today.
2. If is_done_activity is not None, call done_tool.with_activity(is_done_activity).
3. Add the resulting tool with replace=True.
4. Preserve IS_DONE_TOOL_NAME, internal metadata, and the wrapped tool identity.

#### Edge Cases & Error Handling

- None preserves the current unannotated tool.
- A malformed ToolActivity fails during its existing construction validation.
- A user-provided isDone tool is still replaced by the runtime-owned tool.

### 6.2 AgentRuntime Wiring

**File(s):** vidbyte/agents/runtime.py
**Type:** Modified

#### What it does

Accept and store the optional activity and pass it to the internal-tool injection path.

#### Interface / API

~~~python
def __init__(self, *, agent_name: str, system_prompt: str, tools: Tools, permission_policy: PermissionPolicy, is_done_activity: ToolActivity | None = None, ... ) -> None:
~~~

#### Logic / Algorithm

1. Store is_done_activity on the runtime.
2. When include_internal_tools is true, call with_internal_agent_tools(tools, is_done_activity=is_done_activity).
3. When internal tools are disabled, leave the supplied catalog unchanged.
4. Do not change _process_tool_call(), whose name-based isDone finalization remains the stop contract.

#### Edge Cases & Error Handling

- Existing direct runtime callers omit the new keyword and retain current behavior.
- An activity supplied with include_internal_tools=False is ignored because no internal isDone tool is present.
- The activity wrapper must not interfere with ActivityToolFormatter.unwrap() or priced-operation accounting.

### 6.3 BaseAgent Public Configuration

**File(s):** vidbyte/agents/base.py
**Type:** Modified

#### What it does

Expose the configuration to normal SDK developers and application factories.

#### Interface / API

~~~python
def __init__(self, *, name: str, system_prompt: str, is_done_activity: ToolActivity | None = None, ... ) -> None:
~~~

~~~python
def with_is_done_activity(self, activity: ToolActivity) -> "BaseAgent":
    """Attach completion activity to future runtime instances and return this agent."""
~~~

#### Logic / Algorithm

1. Store the constructor value on the agent.
2. Pass it explicitly from _runtime() to the resolved runtime class.
3. The fluent helper replaces the stored value and returns self, matching existing application-side builder usage.
4. Do not serialize the Pydantic class into session state; restored agents must reattach application-owned activity in the same way they reattach tools and middleware.

#### Edge Cases & Error Handling

- None is a valid opt-out.
- Calling the fluent helper before the first run affects the next runtime construction.
- Changing the setting after a runtime has already been constructed affects future runtime constructions, consistent with the existing lazy runtime model.
- Non-linear runtimes receive no new behavior unless their runtime implementation adopts the setting; the direct linear runtime is the supported contract for this feature.

### 6.4 Documentation

**File(s):** vidbyte/tools/README.md, llms.txt
**Type:** Modified

#### What it does

Describe is_done_activity as a generic completion annotation that is separate from the agent's final answer and remains visible through tool-call context metadata.

#### Logic / Algorithm

1. Explain the public BaseAgent setting.
2. Show a small Pydantic schema example.
3. Explain that the activity is nested under isDone and removed before internal execution.
4. State that applications own the schema and its interpretation.

#### Edge Cases & Error Handling

- Documentation must not imply that developers replace or execute IsDoneTool directly.
- Documentation must not promise support for runtimes that do not expose the direct internal-tool loop.

### 6.5 SDK Tests

**File(s):** tests/test_agent_base.py, tests/test_agent_runtime.py, tests/test_provider_tool_schema_translation.py
**Type:** Modified

#### What it does

Cover public wiring, runtime behavior, provider schema rendering, validation, and preservation of existing stop semantics.

#### Logic / Algorithm

1. Build an agent with a typed activity and assert the runtime's isDone spec declares it.
2. Use a fake model response containing valid activity and assert the loop stops with AgentStopReason.IS_DONE.
3. Assert the final ToolCallContext contains the normalized activity payload.
4. Assert the wrapped IsDoneTool receives no reserved activity business argument.
5. Assert missing and malformed required activity are rejected.
6. Assert the unconfigured schema remains unchanged.
7. Assert provider schema translation includes the nested object for supported providers.

#### Edge Cases & Error Handling

- Test activity omitted when optional and required when configured.
- Test an activity payload with extra fields.
- Test an activity payload at its declared size boundary and just beyond it.
- Test a developer-supplied same-name isDone tool remains unable to replace loop control.

---

## 7. Data Model Changes

### 7.1 Runtime Tool Call Context

**Change type:** Modified behavior, no new persisted schema

ToolCallContext.activity already exists and will carry the normalized activity payload. No dataclass field or storage migration is required.

**Migration strategy:** N/A - this is an in-memory SDK behavior and existing unannotated calls remain valid.

---

## 8. API Changes

### 8.1 BaseAgent constructor

**Change type:** Modified, backward-compatible

**Request:**

~~~json
{
  "is_done_activity": "ToolActivity | null - optional typed completion annotation"
}
~~~

**Response:** N/A - the setting changes the generated internal tool schema and captured runtime metadata.

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid activity schema raises the existing SDK configuration error during ToolActivity construction. |
| N/A | Missing or malformed required model activity returns the existing tool-validation error to the agent loop. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | docs/design/is-done-activity-extension.md | Source of truth for the SDK change. |
| MODIFY | vidbyte/tools/_internal.py | Decorate the runtime-owned IsDoneTool with optional activity. |
| MODIFY | vidbyte/agents/runtime.py | Accept and inject the activity setting. |
| MODIFY | vidbyte/agents/base.py | Expose constructor and fluent configuration. |
| MODIFY | vidbyte/tools/README.md | Document developer-facing usage. |
| MODIFY | llms.txt | Keep the agent-readable SDK reference aligned. |
| MODIFY | tests/test_agent_base.py | Verify BaseAgent wiring and public configuration. |
| MODIFY | tests/test_agent_runtime.py | Verify loop, validation, capture, and execution behavior. |
| MODIFY | tests/test_provider_tool_schema_translation.py | Verify provider schema rendering. |
| CREATE | scripts/test-is-done-activity-extension.py | Execute the feature test matrix independently. |

---

## 10. Testing Plan

### Unit Tests

- BaseAgent with no activity produces the current isDone schema. [Silent Failure]
- BaseAgent with activity passes the exact declaration into the runtime. [Hidden Assumption]
- A valid activity appears in the provider schema as a nested required object. [Silent Failure]
- A valid model call stops the loop and preserves the final answer. [Hidden Failure]
- The captured activity is present on ToolCallContext.activity. [Silent Failure]
- The wrapped IsDoneTool receives no reserved activity argument. [Hidden Failure]
- Missing required activity is rejected and does not finalize the run. [Edge Case]
- Extra activity fields are rejected by the caller schema. [Edge Case]
- Minimum and maximum activity payload bounds are respected. [Edge Case]
- A same-name user tool cannot replace runtime loop control. [Hidden Assumption]
- Activity wrapping does not break tool unwrapping or pricing identity. [Hidden Failure]
- A fluent activity attachment returns the same agent and affects a subsequent runtime. [Silent Failure]

### Integration Tests

- Run a linear BaseAgent with a fake runner returning isDone plus activity and verify the complete result metadata.
- Render the decorated isDone schema through each supported provider formatter and verify the nested schema shape.
- Run the SDK source and package CI stages, including semgrep and the feature script.

### Manual / QA Test Cases

1. Create an agent with a two-field Pydantic completion schema, inspect the model request, and confirm isDone.activity is visible.
2. Return a valid activity from a fake or development model and confirm the agent stops normally while application middleware can read the payload.
3. Omit the required activity and confirm the model receives a validation failure instead of a successful stop.
4. Supply a custom tool named isDone and confirm the runtime still exposes the SDK's loop-control tool.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Pydantic | Existing SDK dependency | Validates caller-owned activity schemas. | Existing validation behavior must remain unchanged. |
| Provider schema formatters | Existing OpenAI, Anthropic, and Gemini adapters | Render nested activity input to the model. | Provider-specific schema differences require regression tests. |
| Existing runtime middleware | Existing SDK API | Exposes normalized activity through tool-call context. | A wrapper regression could hide activity from middleware. |

---

## 12. Rollout & Deployment

- No feature flag is needed; the new setting is opt-in and unconfigured agents are unchanged.
- Merge and release the SDK PR before consumers depend on the new BaseAgent API.
- Existing applications can adopt the setting independently.
- Rollback is a normal package rollback; callers that use the new keyword must stop using it or remain on the compatible SDK version.

---

## 13. Open Questions

- [ ] Should restored agents eventually serialize a symbolic activity factory, or should applications continue to reattach live Pydantic schemas after restore?
- [ ] Should non-linear runtimes expose the same internal completion annotation in a later feature, or remain explicitly unsupported?

---

## 14. Alternatives Considered

### Alternative 1: Public replacement IsDoneTool

- What: Expose the internal class and let developers register a customized replacement.
- Why rejected: It weakens runtime ownership of loop termination and can change stop, output, permission, and accounting semantics.

### Alternative 2: Add completion fields to AgentResult

- What: Add a generic completion metadata mapping beside the final answer.
- Why rejected: It would require a second model-facing contract and bypass the existing typed activity schema and tool-call capture path.

### Alternative 3: Add a runtime completion callback

- What: Invoke application code after any run ends.
- Why rejected: A callback can observe completion but cannot give the model a validated field to author and does not reuse the established tool activity contract.

