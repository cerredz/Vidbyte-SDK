# Design Doc: Structured Output Guarantee

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-28
**Last Updated:** 2026-07-28

---

## 1. Overview

When a developer declares `output_schema=SomeModel` on an agent, the SDK currently builds a
provider request format, validates the final output, and then — if validation fails — writes the
error to a trace span and silently discards it. The caller receives a reply whose `structured`
value is absent, indistinguishable from an agent that never had a schema at all. Every consumer
therefore re-implements parsing, re-validation, and error raising: the Vidbyte research harness
does it in `ResearchContextBuilder.parse_structured`, and the SDK's own
`ProsecutorDefenderJudgeRuntimeAlgorithm` does it again in `_structured`.

This change makes `output_schema` a guarantee. The declared schema compiles into an
`OutputContract`, so schema violations flow through the reject-and-retry engine the linear runtime
already runs for tool-call floors; the validated instance lands on a real `AgentMessage.structured`
field; and an unsatisfiable schema raises a typed `OutputSchemaViolationError` instead of returning
a quiet `None`. Alongside that, provider translation moves out of a substring-matching helper and
onto the provider classes, driven by a declared per-provider capability tier, so the same developer
code gets the strongest enforcement each provider actually supports.

---

## 2. Goals & Non-Goals

### Goals

- A developer writes `output_schema=Model` and reads `reply.structured`. Nothing else.
- Schema violations are repaired in-loop by the existing output-contract engine before the agent is
  allowed to stop.
- An unsatisfiable schema raises a typed error carrying the raw output and the validation failure —
  never a silent `None`.
- `AgentMessage.structured` is a real field, typed as the declared schema.
- Provider translation is declared per `(provider, model)`, not inferred from substrings, and each
  provider class owns its own wire format.
- Anthropic's native structured outputs and DeepSeek's JSON mode are actually used; today neither is.
- Pydantic `Field(description=...)` reaches the model, and constraints the provider tier cannot
  enforce are folded into the description rather than silently dropped.

### Non-Goals

- **No `$model:`/dotted-path schema references in YAML.** `vidbyte/config`'s threat model forbids
  document text reaching an import (`vidbyte/config/loader.py` header; field guide
  *Declarative Config Resolution*). A caller's Pydantic model lives outside the SDK and can never be
  named by a document. Callers use `AgentSettings.to_agent_kwargs()` and pass `output_schema`
  directly — the already-sanctioned path for non-serializable injection.
- **No change to `YamlLoader.build_agent`'s signature.** The same field-guide rule forbids adding
  caller-supplied non-serializable parameters there.
- **No `jsonschema` dependency.** Runtime deps stay `pydantic` + `httpx`. Inline-dict schemas keep
  their current guarantee (valid JSON, fields unchecked) and are documented as the weaker tier.
- No new tests. Existing CI (`python scripts/run_ci.py`) must stay green.
- No changes to the Vidbyte backend repo. Deleting `parse_structured` there is a follow-up.
- No repair loop for non-linear runtimes (MCTS, actor). They do not receive `output_contract`
  today; they get the boundary raise only.

---

## 3. Background & Context

**Why now.** PR #284 in the Vidbyte repo shipped a 15-line `parse_structured` helper whose only
live branch is `isinstance(candidate, schema)` — the SDK had already produced the validated
instance. The remaining branches are dead: nothing in the SDK writes a `structured_output` metadata
key, and the `json.loads(reply.content)` fallback re-runs the exact call
`OutputSchemaFormatter.validate` already made on the same string. What the helper genuinely needs
is the missing-value guard, because the SDK will not raise.

**Current state.**

| Location | Behavior |
|---|---|
| `runtime.py:1355` | Builds `response_format` via provider-name substring match |
| `runtime.py:1417` | Validates final output; on failure records a span and **drops the error** |
| `runtime.py:1117` | Tool-output schema violation → `ToolResult.error` fed back to the model |
| `base.py:637` | Copies `result.structured` into `metadata["structured"]` when not `None` |
| `providers/output_schema.py:44` | Returns `None` for Anthropic — native structured outputs unused |
| `providers/compatible.py:110` | `DeepSeekProvider` **deletes** `response_format`, appends schema to the system prompt |

The asymmetry between `runtime.py:1117` and `runtime.py:1417` is the defect: a tool schema
violation becomes actionable model feedback, while an agent schema violation becomes a dropped span
attribute. The structural cause is ordering — `_final_result()` runs at line 466, *after* the
output-contract block at line 453, so validation happens at the one point in the loop where nothing
can act on the result.

**Provider reality** (verified against vendor docs, July 2026):

| Provider | Real capability | SDK today |
|---|---|---|
| OpenAI | Native grammar-constrained `json_schema` + `strict` | correct |
| Anthropic 4.5+ | Native `output_config.format` (GA) | **returns `None`** |
| Gemini | Native `responseSchema` + `responseMimeType` | correct |
| Mistral | Native `json_schema` + `strict` | correct by accident via fall-through |
| DeepSeek | `json_object` JSON mode; strict tools on beta URL | **prompt-only** |
| xAI / GLM / Kimi / MiniMax | OpenAI-compatible, unverified | assumed |
| Meta | Endpoint-dependent; Llama has no API of its own | unmodelled |

Mistral works because `_compatible_format` happens to emit the shape it wants; the identical
fall-through sends DeepSeek a payload it rejects with 400, which is *why* the prompt-injection
override exists. Inference by substring produces silent correctness in one case and a silent
workaround in the next.

**Constraints.**

- Field guide, *Declarative Config Resolution*: refs resolve through a registry under
  `vidbyte/lib/registries/`, never through an import; new registries follow `runtimes.py`'s shape.
- Field guide, *Local CI Verification*: run the source stage with `PYTHONPATH=$(pwd)` from a
  worktree, the package stage without it; `git add` new files before trusting semgrep.
- The local checkout is behind `origin/main`; branch from `origin/main`.
- Code style: Context Protocol Header docstrings, one-line signatures, a mandatory 1–2 line comment
  under every signature, sparse comments elsewhere, class-first design.

---

## 4. Requirements

### Functional Requirements

1. When `output_schema` is set and the final output fails validation, the linear runtime MUST inject
   the validation error as corrective feedback and let the agent retry, bounded by the existing
   `AgentLoopSettings.max_contract_rejections` budget.
2. When the repair budget is exhausted and the schema is still unsatisfied, `BaseAgent.generate_reply`
   MUST raise `OutputSchemaViolationError` carrying the raw output, the validation error, and the
   run's stop reason.
3. `AgentMessage` MUST expose `structured` as a real field. When `output_schema` was declared and
   `generate_reply` returns normally, `structured` MUST be a validated instance, never `None`.
4. `metadata["structured"]` MUST continue to be populated for backward compatibility with existing
   consumers (`agents/handoff.py:150`, `algorithms/prosecutor_defender_judge.py:508`).
5. Provider request translation MUST be owned by the provider class. `OutputSchemaFormatter` MUST NOT
   branch on provider identity.
6. A `(provider, model)` pair MUST resolve to a declared `StructuredOutputSupport` tier. An
   unregistered provider MUST resolve to `PROMPT_ONLY` — degraded but working — never to a payload
   the provider rejects.
7. `AnthropicProvider` MUST emit `output_config.format` for native-schema models.
8. `DeepSeekProvider` MUST emit `{"type": "json_object"}` and keep the schema-in-prompt annotation,
   rather than deleting `response_format` outright.
9. Output parsing MUST tolerate markdown-fenced JSON for every provider, not only DeepSeek.
10. Pydantic constraints the resolved tier cannot enforce (`minItems`, `minLength`, `maximum`, …)
    MUST be appended to the affected property's `description` before the schema goes on the wire,
    and MUST remain enforced by Pydantic on the way back.
11. Non-linear runtimes MUST still get requirement 2 (the boundary raise), even without repair.

### Non-Functional Requirements

- **Performance:** at most one extra `model_validate` per run beyond today. The contract's
  evaluation result is reused by `_final_result` rather than re-parsed.
- **Security:** no document text reaches an import. The capability registry is a fixed table in the
  SDK, keyed by the `ModelProvider` enum.
- **Observability:** the existing `parser.structured_output` span is retained; schema contract
  evaluations appear in `metadata["contract_evaluations"]` like every other contract.
- **Reliability:** unknown providers degrade to `PROMPT_ONLY` rather than erroring. Unknown
  `(provider, model)` pairs resolve by provider default.
- **Backward compatibility:** `agent.output_schema = X` post-construction keeps working; the runtime
  is rebuilt per run and reads the attribute then.

---

## 5. High-Level Design

Three layers, each independently useful.

**Layer 1 — the guarantee.** A new `SchemaConformance(OutputContract)` reads `counters["final_output"]`
— a key already populated at both termination boundaries because `MinFinalOutputChars` needed it —
and reports satisfied only when the output validates. `BaseAgent._build_runtime` appends it to the
loop's contract set whenever `output_schema` is set, so the developer never names it. The runtime's
existing reject-and-continue block at `runtime.py:453` then does the repair work unchanged. At the
`BaseAgent` boundary, a schema that was declared but produced no instance raises
`OutputSchemaViolationError`.

**Layer 2 — provider capability.** A new `StructuredOutputRegistry` under `vidbyte/lib/registries/`
maps `(provider, model)` to a `StructuredOutputSupport` tier, following the same shape as
`pricing.py` (fixed table, prefix-matched model keys, provider-level default). `OutputSchemaFormatter`
loses `build_response_format` entirely and keeps only provider-agnostic work: resolve, annotate,
validate. Each provider class translates the resolved schema into its own wire format in
`_attach_response_format`, which is already an override point.

**Layer 3 — schema fidelity.** `resolve_schema` already emits `Field(description=...)` because
`model_json_schema()` includes it. A new annotation step folds constraints the resolved tier cannot
enforce into the property description, so the model is told about them even when the grammar cannot
enforce them — and Pydantic still rejects violations on the way back, which now means a repair turn
rather than an exception.

```
BaseAgent(output_schema=Model)
   |
   ├─ _build_runtime() ──> AgentRuntime(output_schema=Model,
   |                                    output_contract=[...floors, SchemaConformance(Model)])
   |                          |
   |                          ├─ request:  StructuredOutputRegistry.resolve(provider, model) -> tier
   |                          |            OutputSchemaFormatter.resolve_schema()/annotate()
   |                          |            provider._attach_response_format()   <- provider owns wire form
   |                          |
   |                          └─ stop boundary (runtime.py:453):
   |                                 SchemaConformance.satisfied()?
   |                                   no  -> feedback() appended, rejections += 1, continue
   |                                   out of budget -> AgentStopReason.CONTRACT_UNSATISFIED
   |                                   yes -> _final_result() -> AgentResult.structured
   |
   └─ generate_reply(): reply.structured = result.structured
                        raise OutputSchemaViolationError if schema declared and structured is None
```

**Key decisions.**

*Reuse the contract engine rather than build a repair loop.* Detect → feedback → bounded retry →
typed give-up already exists, is tested, and is what PR #284 uses for `MinToolCallsById`. Schema
conformance is the same shape.

*Raise at the `BaseAgent` boundary, not inside the runtime.* Contract exhaustion returning a result
is correct for effort floors — a partially-completed run is still useful. It is wrong for schema
conformance. Rather than make runtime semantics conditional, the runtime stays uniform and
`generate_reply` raises. This also covers non-linear runtimes for free.

*Declare capability, do not infer it.* Anthropic's tier is model-dependent (4.5+), DeepSeek's is
endpoint-dependent (strict tools only on the beta URL), and "Meta" is a model family served by many
endpoints with different capabilities. That is a `(provider, model)`-keyed fact whose value changes
by vintage — exactly the shape already solved by `ModelPricingRegistry`.

---

## 6. Detailed Design

### 6.1 SchemaConformance

**File:** `vidbyte/agents/contracts/schema.py`
**Type:** New file

#### What it does

An output contract that is satisfied only when the agent's final output validates against the
declared schema. Unlike the effort floors, it is boolean rather than a numeric floor, so it reports
`minimum=1` and an `observed` of 0 or 1 to keep `report()` uniform.

#### Interface

```python
class SchemaConformance(OutputContract):
    key = "final_output"
    ceiling_key = None
    unit = "schema-valid output"
    category = "semantic"

    def __init__(self, schema: type | Mapping[str, Any]) -> None: ...
    def satisfied(self, counters: Mapping[str, Any]) -> bool: ...
    def error(self, counters: Mapping[str, Any]) -> str: ...
    def observed(self, counters: Mapping[str, Any]) -> int: ...
    def validated(self, counters: Mapping[str, Any]) -> Any: ...
```

#### Logic

1. `__init__` stores the schema and an `OutputSchemaFormatter`, and calls `super().__init__(1)`.
2. `satisfied` evaluates the output and returns whether the error is `None`.
3. Evaluation is memoized on the exact output string, so `satisfied`, `error`, and `validated`
   called within one boundary check parse once.
4. `error` returns the validation message prefixed with a corrective instruction.
5. `validated` returns the instance so `_final_result` can reuse it.

#### Edge cases

- Missing or empty `final_output` → unsatisfied, with a message saying the response was empty.
- `ceiling_key` is `None`, so `AgentLoopSettings._validate_contract_ceiling` returns early
  (verified at `settings/loop.py:148`).
- Memo is keyed on output text, so a repaired output on a later iteration re-evaluates correctly.

---

### 6.2 AgentLoopSettingsOutputContract.with_contract

**File:** `vidbyte/agents/contract.py`
**Type:** Modified

#### What it does

Returns a new contract owner with one additional contract appended, preserving the configured
rejection budget. Needed because `output_schema` lives on the agent while the contract set lives on
loop settings.

```python
def with_contract(self, contract: OutputContract) -> "AgentLoopSettingsOutputContract": ...
```

The class is documented as immutable and stateless across runs, so this returns a new instance
rather than mutating. `_max_rejections` is carried forward.

---

### 6.3 BaseAgent runtime wiring and boundary raise

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Auto-registers the schema contract for linear runtimes, populates `AgentMessage.structured`, and
raises when a declared schema produced nothing.

#### Logic

1. In `_build_runtime`, inside the existing `if self.runtime_type is AgentRuntimeType.LINEAR` block,
   when `self.output_schema is not None`, replace `kwargs["output_contract"]` with
   `.with_contract(SchemaConformance(self.output_schema))`.
2. In `generate_reply`, after building `metadata`, pass `structured=result.structured` into
   `AgentMessage`. `metadata["structured"]` is still written (requirement 4).
3. Immediately before returning, if `self.output_schema is not None and result.structured is None`,
   raise `OutputSchemaViolationError`.

#### Edge cases

- Reading `output_schema` at `_build_runtime` time preserves post-hoc assignment.
- Non-linear runtimes skip step 1 (no `output_contract` kwarg) but still get step 3.
- The raise happens after `self.history.append(reply)` and `_notify_session(reply)` so the failed
  turn is still recorded and checkpointed — the session must not silently lose the attempt.
- `generate_reply` wraps its execution block in `AgentExecutionError`; the raise is placed *outside*
  that block so the typed error is not re-wrapped.

---

### 6.4 AgentMessage.structured

**File:** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentMessage:
    sender: str
    recipient: str
    content: str
    message_type: str = "response"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    structured: Any = None
```

Appended last so every positional construction in the codebase keeps working.

**Serialization:** `SessionSerializer.message_to_dict` projects a JSON-safe dict. A Pydantic instance
is not JSON-safe, so `message_to_dict` gains a `structured` projection via `model_dump(mode="json")`
when the value is a `BaseModel`, and `message_from_dict` restores it as the plain dict. This closes
a latent defect: `metadata["structured"]` already carries a live `BaseModel` through that path today.

---

### 6.5 OutputSchemaViolationError

**File:** `vidbyte/lib/errors/base.py`, exported from `vidbyte/lib/errors/__init__.py`
**Type:** Modified

```python
class OutputSchemaViolationError(AgentExecutionError):
    def __init__(self, message: str, *, raw_output: str, validation_error: str | None = None, stop_reason: str | None = None) -> None: ...
```

Subclasses `AgentExecutionError` so existing broad handlers still catch it. Attributes are also
mirrored into `details` following `AllModelsFailedError`'s shape.

---

### 6.6 StructuredOutputSupport and StructuredOutputRegistry

**Files:** `vidbyte/lib/enums/__init__.py` (modified), `vidbyte/lib/registries/structured_output.py` (new)

```python
class StructuredOutputSupport(str, Enum):
    NATIVE_SCHEMA = "native_schema"
    STRICT_TOOLS = "strict_tools"
    JSON_MODE = "json_mode"
    PROMPT_ONLY = "prompt_only"


class StructuredOutputRegistry:
    @classmethod
    def resolve(cls, provider: ModelProvider | str, model: str | None = None) -> StructuredOutputSupport: ...
```

#### Logic

1. `PROVIDER_SUPPORT` maps each `ModelProvider` to its default tier.
2. `MODEL_SUPPORT` overrides by model prefix where the tier is model-dependent (Anthropic native only
   on `claude-*-4-5` and later; earlier Claude models fall back to `STRICT_TOOLS`).
3. `resolve` coerces a string provider to the enum, returns `PROMPT_ONLY` for anything unrecognized,
   checks model prefixes longest-first, then falls back to the provider default.

Follows `pricing.py`: fixed `ClassVar` tables, an `AS_OF` date constant, a comment recording that
tiers were verified against vendor docs, and unverifiable providers omitted so they resolve to the
safe floor rather than a guess.

#### Edge cases

- Unknown provider string → `PROMPT_ONLY`, no raise. Requirement 6.
- `model=None` → provider default.

---

### 6.7 OutputSchemaFormatter

**File:** `vidbyte/providers/output_schema.py`
**Type:** Modified

#### What changes

- **Delete** `build_response_format`, `_openai_format`, `_compatible_format`, `_gemini_format`.
  Provider branching leaves this class entirely.
- **Keep** `resolve_schema` and `validate`.
- **Add** `annotate(schema, tier)` — folds unenforceable constraints into descriptions.
- **Add** fence-tolerant pre-parse inside `validate`.

```python
class OutputSchemaFormatter:
    def resolve_schema(self, schema: type | Mapping[str, Any]) -> dict[str, Any]: ...
    def annotate(self, schema: Mapping[str, Any], tier: StructuredOutputSupport) -> dict[str, Any]: ...
    def validate(self, output: str, schema: type | Mapping[str, Any]) -> tuple[Any, str | None]: ...
```

#### annotate logic

1. Return the schema unchanged for `NATIVE_SCHEMA` where the constraint is supported.
2. Walk `properties` recursively. For each property carrying a constraint key in
   `_UNENFORCEABLE` (`minItems`, `maxItems`, `minLength`, `maxLength`, `minimum`, `maximum`,
   `multipleOf`, `pattern`), append a readable clause to its `description` and drop the key from the
   wire schema.
3. Constraints remain enforced by Pydantic on the return path, so a violation becomes a repair turn.

#### validate logic

1. Strip a leading/trailing markdown fence if present (hoisted from `DeepSeekProvider`).
2. `json.loads`; on failure return `(None, "output is not valid JSON: ...")`.
3. If the schema is a `BaseModel` subclass, `model_validate` and return the instance.
4. Otherwise return the parsed value unchanged — the documented weaker tier for inline dicts.

**Breaking change:** `build_response_format` is a public method on an exported class
(`vidbyte/__init__.py:445`). See §11.

---

### 6.8 Provider translation

**Files:** `vidbyte/providers/compatible.py`, `vidbyte/providers/anthropic.py`, `vidbyte/providers/openai.py`
**Type:** Modified

`TextModelConfig.response_format` now carries the **resolved JSON Schema dict** (annotated), not a
pre-built provider envelope. Each provider wraps it:

| Class | Wire form |
|---|---|
| `OpenAIProvider` | `payload["text"] = {"format": {"type": "json_schema", "name": "agent_output", "schema": ..., "strict": True}}` |
| `AnthropicProvider` | `payload["output_config"] = {"format": {"type": "json_schema", "schema": ...}}` — **new**, currently absent |
| `GeminiProvider` | unchanged; already consumes the raw schema |
| `OpenAICompatibleProvider` | `{"type": "json_schema", "json_schema": {"name": ..., "schema": ..., "strict": True}}` — correct for Mistral, xAI, GLM, Kimi, MiniMax |
| `DeepSeekProvider` | `{"type": "json_object"}` **plus** the existing schema-in-prompt annotation |

`DeepSeekProvider._extract_chat_text` keeps its tool-call and fence handling; the fence regex is
retained there for its own response shape while `validate` gains the general case.

#### Edge cases

- Anthropic below 4.5 resolves to `STRICT_TOOLS`; since the agent-level path has no tool to force,
  it attaches nothing and relies on `SchemaConformance` repair. Documented, not silently wrong.
- `PROMPT_ONLY` attaches nothing to the payload and relies on prompt annotation plus repair.

---

### 6.9 AgentRuntime request construction

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### Logic

1. At `_build_call_options`, replace the `build_response_format` call with: resolve the tier from
   `StructuredOutputRegistry`, `resolve_schema`, `annotate(schema, tier)`, and set
   `call_options["response_format"]` to the annotated schema dict when the tier is not `PROMPT_ONLY`.
2. In `_final_result`, when the runtime's contract set contains a `SchemaConformance`, reuse its
   memoized instance instead of re-validating. Otherwise behave exactly as today.

---

## 7. Data Model Changes

N/A — no database, ORM, or persisted schema in this SDK. The one persistence-adjacent change is the
`AgentMessage.structured` session-checkpoint projection, covered in §6.4.

---

## 8. API Changes

No HTTP endpoints in this repo. Public Python surface changes:

| Symbol | Change | Notes |
|---|---|---|
| `AgentMessage.structured` | New field | Appended last; positional construction unaffected |
| `OutputSchemaViolationError` | New export | Subclasses `AgentExecutionError` |
| `StructuredOutputSupport` | New export | Enum |
| `StructuredOutputRegistry` | New export | Registry |
| `SchemaConformance` | New export | Auto-registered; developers do not name it |
| `OutputSchemaFormatter.build_response_format` | **Removed** | Provider-owned now |
| `OutputSchemaFormatter.annotate` | New method | |

**Error surface:**

| Raised | Condition |
|---|---|
| `OutputSchemaViolationError` | `output_schema` declared, repair budget spent, output still invalid |
| `ConfigurationError` | `output_schema` is neither a `BaseModel` subclass nor a mapping (unchanged) |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/structured-output-guarantee.md` | This design doc |
| CREATE | `vidbyte/agents/contracts/schema.py` | `SchemaConformance` contract |
| CREATE | `vidbyte/lib/registries/structured_output.py` | `(provider, model)` → capability tier |
| MODIFY | `vidbyte/agents/contracts/__init__.py` | Export `SchemaConformance` |
| MODIFY | `vidbyte/agents/contract.py` | `with_contract()` composition |
| MODIFY | `vidbyte/agents/base.py` | Auto-register contract; populate `structured`; boundary raise |
| MODIFY | `vidbyte/agents/runtime.py` | Tier-driven request build; reuse contract's validated instance |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | `AgentMessage.structured` field |
| MODIFY | `vidbyte/sessions/serialization.py` | JSON-safe projection of `structured` |
| MODIFY | `vidbyte/lib/errors/base.py` | `OutputSchemaViolationError` |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export the new error |
| MODIFY | `vidbyte/lib/enums/__init__.py` | `StructuredOutputSupport` |
| MODIFY | `vidbyte/lib/registries/__init__.py` | Export the new registry |
| MODIFY | `vidbyte/providers/output_schema.py` | Drop provider branching; add `annotate`; tolerant parse |
| MODIFY | `vidbyte/providers/anthropic.py` | Emit `output_config.format` |
| MODIFY | `vidbyte/providers/compatible.py` | Base wraps schema; DeepSeek uses `json_object` |
| MODIFY | `vidbyte/providers/openai.py` | Wrap resolved schema in the Responses `text.format` envelope |
| MODIFY | `vidbyte/__init__.py` | Export new symbols; drop removed one |
| MODIFY | `llms.txt` | Document the guarantee and the capability tiers |

**Totals:** 3 created (1 doc, 2 code), 16 modified, 0 deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `pydantic` | `>=2,<3` (existing) | Schema resolution and validation | None — already required |
| `httpx` | `>=0.27` (existing) | Provider transport | None — unchanged |
| Anthropic Messages API | `output_config.format` | Native structured outputs | Field name verified against vendor docs 2026-07-28; no live call in CI |
| DeepSeek chat API | `response_format: json_object` | JSON mode | Documented as supported; current code wrongly claims it is not |

**No new dependencies.**

---

## 11. Rollout & Deployment

**Feature flags:** none. The behavior only engages when `output_schema` is set.

**Breaking changes — two, both intentional:**

1. **`OutputSchemaFormatter.build_response_format` is removed.** It is exported at
   `vidbyte/__init__.py:445`. Its only in-repo caller is `runtime.py:1355`. Any external caller was
   getting a payload the SDK then discarded for DeepSeek, so its behavior was already unreliable.
   Migration: the provider now owns translation; nothing external should build these envelopes.

2. **A declared schema that cannot be satisfied now raises instead of returning a reply with no
   structured value.** This is the point of the change. Callers who relied on inspecting
   `metadata.get("structured")` for `None` — the Vidbyte research harness and the SDK's own
   `prosecutor_defender_judge` — keep working, because `metadata["structured"]` is still written on
   success and the raise only replaces a path that previously returned unusable data.

**Deployment order:** SDK ships first. The Vidbyte backend's `parse_structured` continues to work
unchanged against the new SDK (its `isinstance` branch still hits) and can be deleted in a follow-up
PR, so the repos are not coupled.

**Rollback:** revert the PR. No persisted state or migration.

---

## 12. Open Questions

- [ ] **Inline-dict YAML schemas remain unvalidated at field level.** Real JSON Schema validation
      needs a `jsonschema` dependency, which conflicts with the two-dependency runtime. Current plan:
      document the tier honestly and point developers at `to_agent_kwargs()` + Pydantic for the
      strong guarantee. Confirm this is acceptable rather than adding the dependency.
- [ ] **Anthropic tier boundary.** Native structured outputs are documented as Claude 4.5 and later.
      The registry encodes that as a model-prefix rule; confirm the intended fallback for older
      Claude models is `STRICT_TOOLS` (attaches nothing at the agent level, relies on repair) rather
      than `PROMPT_ONLY` (which would add a schema paragraph to the system prompt).
- [ ] **`ModelProvider.META` capability.** Llama has no structured-output API of its own and the
      registry's endpoint is `https://api.meta.ai/v1`. Planned tier is `PROMPT_ONLY`. Confirm, since
      this may become wrong if that endpoint is OpenAI-compatible.
- [ ] **Truncation.** `max_tokens` truncation produces invalid JSON that repair cannot fix, and each
      retry costs another call. Current plan surfaces `stop_reason` in the error rather than
      short-circuiting the repair loop. A short-circuit would be cheaper but needs a reliable
      truncation signal across every provider's response shape — deferred as out of scope.

---

## 13. Alternatives Considered

### Alternative 1: `$model: pkg.mod:Class` references in YAML

- **What:** Let a document name a Pydantic class by dotted path, resolved and digested like `$file`.
- **Why rejected:** `vidbyte/config`'s threat model explicitly forbids document text reaching an
  import, and the field guide records this as settled (PR #317/#318). A caller's model lives outside
  the SDK, so it could never be registry-resolvable either. `to_agent_kwargs()` already covers the
  case without weakening the boundary.

### Alternative 2: A new `with_structured_output()` method, LangChain-style

- **What:** A separate builder returning a schema-bound agent.
- **Why rejected:** Adds a second way to say something `output_schema=` already says, and forces the
  developer to choose. The stated goal is that they think about none of this.

### Alternative 3: A bespoke repair loop inside `_final_result`

- **What:** Retry logic local to structured output.
- **Why rejected:** Duplicates the reject-and-continue engine at `runtime.py:453`, including its
  budget, exhaustion handling, typed stop reason, and metadata reporting. The existing engine already
  passes `final_output` into the counters.

### Alternative 4: Raise from the runtime on contract exhaustion

- **What:** Make `CONTRACT_UNSATISFIED` raise when a schema contract is the unmet one.
- **Why rejected:** Makes runtime termination semantics conditional on contract type. Raising at the
  `BaseAgent` boundary keeps the runtime uniform and covers non-linear runtimes, which never receive
  the contract set.

### Alternative 5: Keep substring provider matching, just add Anthropic and DeepSeek

- **What:** Two more branches in `build_response_format`.
- **Why rejected:** Leaves two places deciding the same thing — the formatter builds an envelope the
  DeepSeek provider then discards — and leaves the silent fall-through that makes Mistral correct by
  accident and unknown providers broken.

---

## 14. Verification

Canonical CI, run from the implementation worktree per the field guide:

```bash
PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source   # diagnostic
python scripts/run_ci.py --stage package                    # diagnostic, no PYTHONPATH
python -m pip install -e ".[dev]"
python scripts/run_ci.py                                    # required gate
```

`git add -A` before any semgrep run so new files are actually scanned.
