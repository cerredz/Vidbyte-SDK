# Design Doc: MultiAgent manager schema that strict providers accept

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-27
**Last Updated:** 2026-10-27

---

## 1. Overview

`MultiAgent` cannot run on any Anthropic model. Its manager's plan and progress phases send a structured-output schema with an untyped `payload` field and an open `metadata` map. Anthropic rejects untyped nodes and open objects with HTTP 400. The fix declares `payload` as text on the wire and removes the open `metadata` map from the two private, provider-facing Pydantic models, so the manager schema is valid in every strict structured-output dialect.

## 2. Goals & Non-Goals

### Goals
- Every schema node the manager sends has a `type`, and every object sets `additionalProperties: false`.
- Fix it once, where the schema is declared, so Anthropic, OpenAI, and the OpenAI-compatible native-schema tier all get a valid schema.
- Providers that only describe the schema in the prompt keep working. An object payload they return is still accepted, unchanged.

### Non-Goals
- Changing `OutputSchemaFormatter.strict()` or the Anthropic adapter. A converter cannot express "any JSON value" in Anthropic's grammar (see §14).
- Changing the public `TaskSpec` or `OrchestratorDecision` records, or the worker transfer format.
- Validating a developer's own `output_schema` before it is sent. That is a possible follow-up.

## 3. Background & Context

Live billing-readiness run, 2026-10-27, DIRECT mode on `claude-haiku-5-5` and `claude-sonnet-5-5`: the manager plan phase got HTTP 400 three times, then raised `MultiAgentExecutionError: Multi-agent manager phase failed after bounded parse retries.` Anthropic's message was `output_config.format.schema: Invalid schema: Schema type is missing for schema: {'default': None, 'title': 'Payload'}`. The 400s were not billed.

`vidbyte/agents/multi/orchestrator.py` declares `_TaskSpecOutput.payload: Any`, `_TaskSpecOutput.metadata: dict[str, Any]`, and `_DecisionOutput.payload: Any`. Pydantic emits `{"default": null, "title": "Payload"}` (no type) and `{"type": "object", "additionalProperties": true}`. `OutputSchemaFormatter.strict()` keeps both as they are, and the Anthropic, OpenAI Responses, and compatible native-schema adapters all send its output.

Anthropic's structured-outputs reference ("JSON Schema limitations") supports only the basic types, and requires `additionalProperties` to be `false` on objects. "`additionalProperties` set to anything other than `false`" is listed as not supported. Recursive schemas are also unsupported. The Anthropic Python SDK's own `transform_schema` raises `Schema must have a 'type', 'anyOf', 'oneOf', or 'allOf' field.` for an untyped node, and it forces `additionalProperties: false` on every object. OpenAI strict mode has the same two rules, and openai-python's helper leaves both nodes as they are, so the same schema fails there too. Fixing only the Anthropic `metadata` error would surface the next 400, so both nodes must change.

## 4. Requirements

### Functional Requirements
1. The plan, progress, and replan schemas the manager sends contain no untyped node and no object with an `additionalProperties` value other than `false`.
2. The wire schema declares `payload` as optional text (`anyOf [string, null]`). The value reaches `TaskSpec.payload` and `OrchestratorDecision.payload` unchanged.
3. Validation of `payload` is unchanged (`Any`). A non-text JSON payload from a prompt-only or JSON-mode provider is accepted exactly as on main, and does not cost a parse retry.
4. The manager is no longer offered task `metadata`. Planned tasks get the `TaskSpec` default (empty metadata). Developer-built `TaskSpec` objects are unaffected.

### Non-Functional Requirements
- No new dependencies, and no change to any provider adapter or public API.
- The schema stays within Anthropic's complexity limits: at most 16 union parameters, and zero optional parameters after `strict()`.

## 5. High-Level Design

```
_PlanOutput / _DecisionOutput (Pydantic)  ->  runtime._wire_schema (annotate)
   -> provider: Anthropic output_config.format | OpenAI text.format | compatible response_format (strict())
```

Only the source models change. `payload` keeps `Any` validation but publishes `WithJsonSchema({"anyOf": [string, null]})`. Strict grammars then force text, and lenient providers behave as before. `metadata` is removed from `_TaskSpecOutput`, and `_to_task` stops passing it. Pydantic's `WithJsonSchema` is new to this repository. It has been part of Pydantic since 2.0, which is the floor the SDK pins (`pydantic>=2,<3`).

## 6. Detailed Design

### 6.1 Provider-facing manager schemas
**File(s):** `vidbyte/agents/multi/orchestrator.py`
**Type:** Modified

#### What it does
Declares the private Pydantic models the manager's structured phases send as the output schema.

#### Interface / API
```python
class _TaskSpecOutput(BaseModel):
    payload: Annotated[Any, WithJsonSchema({"anyOf": [{"type": "string"}, {"type": "null"}], "description": "..."})] = None
    # metadata removed

class _DecisionOutput(BaseModel):
    payload: Annotated[Any, WithJsonSchema({"anyOf": [{"type": "string"}, {"type": "null"}], "description": "..."})] = None
```

#### Logic / Algorithm
1. Pydantic emits the `WithJsonSchema` value for `payload` in place of the empty `Any` schema. `annotate()` and `strict()` pass it through unchanged.
2. `_to_task` builds `TaskSpec` without `metadata`.
3. The module stays at 300 lines, the cap in `tests/multi_agent/test_structure.py`, and adds no module-level function.

#### Edge Cases & Error Handling
- A lenient reply that still sends `metadata` now fails `extra="forbid"`, and costs one bounded parse retry. Such providers read the schema in the prompt, and it no longer lists `metadata`.
- A payload that is valid JSON text stays text. It is never decoded, so `"42"` does not become `42`.

## 7. Data Model Changes
### 7.1 `_TaskSpecOutput`, `_DecisionOutput` (private)
**Change type:** Modified. The wire schema of `payload` is now `string | null`, and `_TaskSpecOutput.metadata` is removed. No persisted data and no migration.

## 8. API Changes
N/A. These are private models. `TaskSpec`, `OrchestratorDecision`, and `MultiAgent` keep their signatures.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/agents/multi/orchestrator.py` | Type `payload` on the wire, drop open `metadata` |
| MODIFY | `vidbyte/agents/multi/README.md` | Dated log entry for the schema decision |
| CREATE | `tests/multi_agent/test_manager_schema_wire.py` | Wire-level regression tests |
| CREATE | `scripts/test-multiagent-manager-schema-types.py` | Design-doc verification script |
| CREATE | `docs/design/multiagent-manager-schema-types.md` | This document |

## 10. Testing Plan

### Unit Tests
- `test_anthropic_manager_schema_meets_anthropic_rules`: runs the live build case (DIRECT, `claude-haiku-5-5`) through a fake transport, captures the plan and progress request bodies, and checks every node of `output_config.format.schema` against Anthropic's documented rules: typed, closed objects, supported keywords and formats, no recursion, and the union and optional limits. Fails on main. [Hidden Failure]
- `test_openai_manager_schema_meets_strict_rules`: the same check against `text.format.schema` for OpenAI strict mode (typed, closed, every property required). Fails on main. [Hidden Assumption]
- `test_rule_checker_rejects_the_old_shapes`: the checker flags `{"default": null}` and `{"type": "object", "additionalProperties": true}`, so the test cannot pass vacuously. [Silent Failure]
- `test_rule_checker_rejects_the_old_shapes` also covers a recursive schema. [Edge Case]
- `test_payload_text_reaches_the_worker`: a delegated text payload arrives in the worker's request unchanged. [Silent Failure]
- `test_lenient_provider_payload_still_validates`: an object, a list, a number, a bool, `None`, and text all validate and are kept as given. [Edge Case]

### Integration Tests
The two wire tests run the whole MultiAgent through plan, delegate, worker, progress, and finalize, with every adapter in production code and only `HttpTransport.request` scripted. A scratch run also confirmed that Gemini completes the same team, and that its `payload` now has the same `anyOf [string, null]` shape as `owner`.

### Manual / QA Test Cases
1. Given a funded Anthropic key, when the build case runs live, then the plan phase returns 200 and the run finishes. [Hidden Failure] This is left to the founder, because this run makes no real calls.

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Anthropic Messages API | `output_config.format` | Structured output | Rules change. The test encodes the documented rules. |

## 12. Rollout & Deployment
No flag. The change is not breaking for public APIs. Customers get it in the next SDK release. Roll back by reverting the commit.

## 13. Open Questions
- [ ] Should `OutputSchemaFormatter` refuse a developer's untyped or open-map `output_schema` locally, with a clear error, instead of letting the provider return a 400? (Follow-up.)

## 14. Alternatives Considered

### Alternative 1: Normalize untyped nodes in the Anthropic conversion
- What: Rewrite `{}` to a typed union, and close open maps, in `_attach_response_format`.
- Why rejected: Anthropic's grammar has no recursion and no open objects, so "any JSON value" has no faithful form. Any rewrite silently narrows the contract. The vendor SDK refuses untyped nodes rather than guessing. It would also leave OpenAI strict mode broken.

### Alternative 2: Type `payload` as `str | None` with a coercing validator
- What: Validate text only, turning objects from lenient providers into JSON text.
- Why rejected: it changes what lenient providers deliver to workers, and the helper does not fit the module's 300-line and no-module-function rules. `WithJsonSchema` changes only the wire schema.

### Alternative 3: Keep `metadata` as a list of key/value pairs
- What: `metadata: list[_Pair]`, converted to a dict.
- Why rejected: nothing in the SDK reads manager-written task metadata, and no prompt mentions it. The extra parameters count toward Anthropic's complexity limits for no use.
