# Design Doc: Jev Decide Tool (bolt-on) + TypeSafe Provider + Usage Tracking

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-21
**Last Updated:** 2026-09-21

---

## 1. Overview

This change adds Jev, TypeSafe's calibrated "System One" decision model, to the SDK in its simplest form: a **bolt-on tool**. The main agent calls `jev_decide(question, options)` when it wants a quick judgment. Jev answers in roughly 70–500 ms with a calibrated probability for every option, and the tool returns the chosen option, the full distribution, and a confidence flag. To make that possible, the change also connects TypeSafe as a real SDK **model provider** (enum member, registry entries, config, provider adapter, runner) and wires Jev's token usage into the agent's existing **`UsageTracker`**, so every Jev call appears in `agent.get_usage()` and `agent.get_cost_usd()` with a priced cost.

---

## 2. Goals & Non-Goals

### Goals
- Add a model-callable `jev_decide` tool in a new `vidbyte/tools/classifier/` package.
- Connect TypeSafe as a first-class provider: `ModelProvider.TYPESAFE`, `TYPESAFE_API_KEY`, the `https://api.typesafe.ai/v1` endpoint, the `jev-latest` default model, and the runner catalog, with S014 parity kept.
- Add a typed decision request/response layer (`DecisionModelConfig`, `JevQuestion`, `JevDecisionRequest`, `DecisionModelResponse`), a `TypeSafeProvider` adapter, a `ModelProviders.decision()` factory, and a `DecisionModelRunner`.
- Price Jev calls: a `JevUsage` usage class bound to `ModelProvider.TYPESAFE`, and a `jev-latest` rate of $0.042 per million input tokens with free output tokens.
- Record the tool's Jev usage into the running agent's `UsageTracker` through a small, generic "model-backed tool" seam that mirrors how `PricedOperationTool` search and fetch usage is recorded today.
- Follow the Jev skill's rules: act on probabilities (not just the argmax), keep any threshold configurable and off by default, fail open, record every decision, and keep secrets out of the state sent to TypeSafe.

### Non-Goals
- Runtime controllers (context controller, stall breaker, completion gate, and so on), `JevControllerMiddleware`, the shadow baseline, and merging questions per hook. These are the later "Jev in the runtime" work in the Jev skill.
- Using `jev-latest` as an agent's main model. Jev cannot generate text, so `Runner.build()` refuses it with a clear error.
- Claude Code or Codex plugin hooks, the MCP `find_vidbyte_agent` router, and batch `jev_filter` / `jev_rank` tools.
- Recording Jev usage for tools that run inside the Codex harness agent (it owns its own per-turn tracker). This is a follow-up.
- Tuned thresholds. No replay evidence exists yet, so the tool ships with no threshold. See the Jev skill's stop conditions.

---

## 3. Background & Context

- **Why now:** the Jev skill (`vidbyte/skills/jev/`, private repo) lists "Jev as a tool" as the fastest way to start, because it needs no loop changes. Its known cost is that the host model still decides when to ask, so it still spends its own reasoning on the delegation choice. This PR accepts that trade-off on purpose and lays the provider and pricing groundwork that the runtime controllers will reuse.
- **Current state:** the SDK has no TypeSafe client. Model providers live in `vidbyte/providers/`, with their enum in `vidbyte/lib/enums/model_provider.py` and their maps in `vidbyte/lib/registries/models.py` and `vidbyte/lib/constants/runners.py`. `vidbyte/lib/providers/` holds *database* providers and is not the right home. (The request guessed `vidbyte/lib/provider`; the audit places model providers in `vidbyte/providers/`.)
- **Usage tracking today:** `UsageTracker.record_call(response)` duck-types `response.provider`, `.model` and `.usage`, resolves `ModelProvider.usage_class()`, and prices the call from `ModelPricingRegistry`. The runtime records only the agent's own model responses, plus `PricedOperationTool` operations through `AgentRuntime._record_operation_usage`. A tool that calls a model has no path into the ledger yet.
- **Constraints:**
  - `vidbyte/providers` and `vidbyte/lib` are lower layers under lint A006 and must not import `vidbyte.tools`, `vidbyte.agents`, or other higher layers.
  - Cost arithmetic may only live in `vidbyte/agents/pricing/` (lint C005).
  - S014 requires the enum, the three registry maps, and both runner catalogs to stay in parity.
  - New modules need the A001 header fields. Policy functions need `# @intent` markers (A002).
  - Jev API facts (endpoint, request and response shapes, price, the 255-option limit) come from the Jev skill's `what-is-jev.md`, checked against TypeSafe's launch post in September 2026. They are vendor claims.

---

## 4. Requirements

### Functional Requirements
1. `ModelProvider.TYPESAFE == "typesafe"` exists. `ProviderModelRegistry` maps it to the default model `jev-latest`, the key variable `TYPESAFE_API_KEY`, and the endpoint `https://api.typesafe.ai/v1`.
2. The runner catalogs map `typesafe/jev-latest` and `jev-latest` to a new `RUNNER_TYPE_DECISION`. `Runner.build()` for that runner type raises `ConfigurationError`, explaining that decision models cannot drive an agent loop.
3. `DecisionModelConfig.validate()` rejects a provider other than TypeSafe, a blank model, a non-positive timeout, and a negative retry count, and it resolves the API key.
4. `JevQuestion` validates each question type:
   - `noul` takes exactly the options `true` and `false`.
   - `choice` takes 2–255 unique, non-blank option names.
   - `score` takes 2–255 unique, non-blank levels, in order.
   - Instructions must not be blank.
5. `JevDecisionRequest` requires a non-blank state within `JEV_MAX_STATE_CHARS`, and 1 to `JEV_MAX_QUESTIONS` questions with unique names.
6. `TypeSafeProvider.run_decision()` POSTs `{model, state, questions}` to `{endpoint}/systemone` with bearer auth, a bounded response size, and the configured timeout. It returns a `DecisionModelResponse` with one normalized `JevAnswer` per requested question and the raw `usage` mapping.
7. Answer normalization:
   - `noul` becomes probabilities `{true: p, false: 1 - p}`, with choice `true` when p ≥ 0.5 and confidence `max(p, 1 - p)`.
   - `choice` and `score` keep only probabilities for known options, and the chosen label must be a known option.
   - A missing answer, an unknown label, a probability outside [0, 1], or a non-numeric probability raises `ProviderResponseError`.
8. `ModelProviders.decision(config)` returns a `TypeSafeProvider` for TypeSafe and raises `ProviderSelectionError` for any other provider.
9. `DecisionModelRunner(config).arun(request)` validates the config and returns the provider response.
10. `JevUsage.from_usage_payload()` parses `input_tokens` and `output_tokens`, sets `total_tokens` to their sum when both are known, and prices input at the table rate and output at $0. `ModelProvider.TYPESAFE.usage_class() is JevUsage`.
11. `ModelPricingRegistry.default().resolve(TYPESAFE, "jev-latest")` returns $0.042 input and $0.0 output per million tokens.
12. The `jev_decide` tool:
    - Takes `question` (required), `options` (required array of strings or `{name, description}` objects), `state` (optional), and `answer_type` (optional, `choice` or `score`, default `choice`).
    - Invalid arguments return a `ToolResult.error` with `metadata.error = "invalid_arguments"` and make no network call.
    - On success, it returns the chosen option, every option's probability sorted from high to low, and the confidence.
    - When the application configured `min_confidence` and the confidence falls below it, the output says so and tells the agent to make the call itself.
13. Fail open: a missing key, `401`, `422`, `429`, `529`, a timeout, a network error, or a malformed response returns `ToolResult.error` with a stable `metadata.error` code and a model-facing message telling the agent to decide without Jev. It never raises. After a `401` or a missing key, the tool instance stops calling TypeSafe and answers "unavailable" immediately.
14. Every successful Jev response the tool received, including one whose answer then failed normalization, is attached to the result as model usage. `AgentRuntime` records each one through `usage_tracker.record_call`, so it appears in `get_usage().calls` with `provider == "typesafe"` and a priced `cost_usd`.
15. Every decision produces a `JevDecisionRecord`: the question, option names, the probabilities, the chosen option, the confidence, the threshold, whether it passed, the model, a SHA-256 of the state, and the latency. The record goes into the result's metadata and to an optional `on_decision` callback. An exception inside the callback never fails the tool call.
16. The state text sent to TypeSafe has credential assignments (such as `api_key=...` or `Authorization: ...`) and the configured TypeSafe key replaced by `<redacted>`.

### Non-Functional Requirements
- **Latency:** one HTTP request per tool call. The default timeout is 10 s and the default retry count is 0 (fail open rather than wait).
- **Security:** the API key never appears in results, metadata, records or logs. Response bodies are capped (`JEV_MAX_RESPONSE_BYTES`). State is scrubbed before sending. The tool's permission is `SAFE`, the same as the search tools. It sends caller-provided text to a third-party API, which is documented in the tool README.
- **Observability:** the runtime already traces tool spans. Decision records ride on `ToolResult.metadata["jev_decision"]`.
- **Reliability:** a tool failure never aborts a run. A usage-recording exception marks the tracker `recording_corrupted` rather than propagating it, the same as operation usage.

---

## 5. High-Level Design

```
Agent model ──calls──> jev_decide tool (vidbyte/tools/classifier)
                          │ builds JevQuestion / JevDecisionRequest (lib/dataclasses/jev.py)
                          │ scrubs state, lazily builds DecisionModelRunner
                          ▼
              DecisionModelRunner (lib/runners/decision.py)
                          ▼
              ModelProviders.decision(config) -> TypeSafeProvider (providers/typesafe.py)
                          │ POST https://api.typesafe.ai/v1/systemone
                          ▼
              DecisionModelResponse(provider=TYPESAFE, model, answers, usage)
                          │
tool result  <────────────┘  metadata: model_usage=(ToolModelCall,...), jev_decision=record
    │
AgentRuntime._record_tool_model_usage ──> UsageTracker.record_call(ToolModelCall)
                                              └─> ModelProvider.TYPESAFE.usage_class() = JevUsage
                                              └─> PROVIDER_PRICING[TYPESAFE]["jev-latest"]
```

The provider layer follows the existing non-text provider pattern, the same one used for ElevenLabs, PlayAI and embeddings:
- a config dataclass in `lib/dataclasses/model_configs.py`
- an adapter class in `vidbyte/providers/`
- a `ModelProviders.<capability>()` factory
- a runner in `vidbyte/lib/runners/`
- the enum, registry and runner-catalog entries that S014 keeps in parity

Decision requests and answers are new typed records in `vidbyte/lib/dataclasses/jev.py`. The provider builds the wire dict, because lint S060 bars `dict[str, Any]` encoders in `lib/dataclasses`. `DecisionModelResponse` sits next to the other runner responses in `lib/runners/types.py`.

The usage seam is the one runtime change. Today only `PricedOperationTool` results feed the tracker. This PR adds `ModelBackedTool`, a `BaseTool` subclass in `vidbyte/tools/model_backed.py` that embeds `ToolModelCall` records (provider, model, raw usage) in its result metadata. It adds a sibling `AgentRuntime._record_tool_model_usage` that unwraps the tool, checks `isinstance(tool, ModelBackedTool)`, and calls `usage_tracker.record_call()` once per embedded call. It is generic, so any future tool that calls a model (another Jev tool, a judge tool) meters itself the same way. It also keeps the field-guide rule that usage accounting stays agent-owned and is recorded once per raw response. This change touches accounting only, not the agent loop, which matches the "no runtime code changes" spirit of the bolt-on approach.

Key decisions:
1. **The provider is named TypeSafe (the vendor) and the model is `jev-latest`.** This mirrors how every other provider is named after its vendor.
2. **No default threshold.** The tool always reports the full distribution. `min_confidence` is an application setting that defaults to `None`, so the SDK never hard-codes an untested threshold.
3. **The model cannot set the threshold.** Thresholds are policy and belong to the application, not the model.
4. **`answer_type` offers only `choice` and `score`.** A yes/no judgment is a two-option `choice`. `noul` stays available to callers of the provider and runner.

---

## 6. Detailed Design

### 6.1 ModelProvider enum
**File(s):** `vidbyte/lib/enums/model_provider.py` · **Type:** Modified
Add `TYPESAFE = "typesafe"`. Add `ModelProvider.TYPESAFE: JevUsage` to `_usage_class_map()`, keeping the pricing import deferred.

### 6.2 Jev enums
**File(s):** `vidbyte/lib/enums/jev.py` (new), `vidbyte/lib/enums/__init__.py` (export)
```python
class JevQuestionType(str, Enum):
    NOUL = "noul"; CHOICE = "choice"; SCORE = "score"
    @classmethod
    def values(cls) -> tuple[str, ...]: ...
```

### 6.3 Jev constants
**File(s):** `vidbyte/lib/constants/jev.py` (new), `vidbyte/lib/constants/__init__.py` (export)
- `JEV_DEFAULT_MODEL = "jev-latest"` and `JEV_SYSTEMONE_PATH = "/systemone"`.
- `JEV_MIN_OPTIONS = 2`, `JEV_MAX_OPTIONS = 255` and `JEV_MAX_OPTION_NAME_CHARS = 200`.
- `JEV_MAX_QUESTIONS = 16` (a local sanity cap) and `JEV_MAX_STATE_CHARS = 200_000`.
- `JEV_DEFAULT_TIMEOUT_SECONDS = 10.0` and `JEV_MAX_RESPONSE_BYTES = 1_000_000`.
- `JEV_RETRY_STATUS_CODES = (429, 529)`.
- `JEV_NOUL_OPTIONS = ("true", "false")`.
- `JEV_DECIDE_ANSWER_TYPES = (JevQuestionType.CHOICE.value, JevQuestionType.SCORE.value)`.

### 6.4 Registry and runner catalog
**File(s):** `vidbyte/lib/registries/models.py`, `vidbyte/lib/constants/runners.py`, `vidbyte/lib/constants/__init__.py`, `vidbyte/lib/runners/utility.py` · **Type:** Modified
- Registry: add `TYPESAFE` to `DEFAULT_PROVIDER_MODELS`, `API_KEY_ENV_VARS` and `DEFAULT_ENDPOINTS`.
- Runner catalog: add `RUNNER_TYPE_DECISION = "decision"`, and the entries `"typesafe/jev-latest"`, `"jev-latest"`, `"typesafe"` (provider default) and the prefix `"jev-"`.
- `Runner.build()` and `_config_type_for()`: for the decision type, raise `ConfigurationError("Model 'jev-latest' is a decision model and cannot drive an agent loop; call it through JevDecideTool or DecisionModelRunner.")`.
- `ProviderModelRegistry._resolve_from_environment()` already skips models that are not text (`detect_modality("jev-latest")` is AUTO), so a set `TYPESAFE_API_KEY` never makes Jev an "active text provider".

### 6.5 DecisionModelConfig
**File(s):** `vidbyte/lib/dataclasses/model_configs.py`, `vidbyte/lib/config/__init__.py`, `vidbyte/lib/config/models.py`
```python
DECISION_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({ModelProvider.TYPESAFE})

@dataclass(frozen=True, slots=True)
class DecisionModelConfig:
    provider: ModelProvider | str = ModelProvider.TYPESAFE
    model: str = "jev-latest"
    api_key: str | None = None
    endpoint: str | None = None
    timeout_seconds: float = 10.0
    retry_count: int = 0
    def normalized_provider(self) -> ModelProvider: ...
    def validate(self) -> None: ...
    def resolved_api_key(self) -> str: ...
    def resolved_endpoint(self) -> str: ...
```
`validate()` checks: the provider is in `DECISION_SUPPORTED_PROVIDERS`, the model is not blank, `timeout_seconds > 0`, `retry_count` is an int ≥ 0 (not a bool), and the API key resolves.

### 6.6 Jev records
**File(s):** `vidbyte/lib/dataclasses/jev.py` (new)
```python
@dataclass(frozen=True, slots=True)
class JevOption:            # name + optional criterion text
    name: str
    description: str | None = None

@dataclass(frozen=True, slots=True)
class JevQuestion:
    name: str
    question_type: JevQuestionType
    instructions: str
    options: tuple[JevOption, ...]
    def option_names(self) -> tuple[str, ...]: ...

@dataclass(frozen=True, slots=True)
class JevDecisionRequest:
    state: str
    questions: tuple[JevQuestion, ...]

@dataclass(frozen=True, slots=True)
class JevAnswer:
    question_name: str
    question_type: JevQuestionType
    choice: str
    probabilities: Mapping[str, float]   # MappingProxyType
    confidence: float
    def ranked(self) -> tuple[tuple[str, float], ...]: ...

@dataclass(frozen=True, slots=True)
class JevDecisionRecord:
    question: str
    answer_type: JevQuestionType
    options: tuple[str, ...]
    choice: str
    probabilities: Mapping[str, float]
    confidence: float
    min_confidence: float | None
    passed_threshold: bool
    model: str
    state_sha256: str
    latency_ms: float

@dataclass(frozen=True, slots=True)
class JevDecideSettings:
    model: str = "jev-latest"
    api_key: str | None = None
    endpoint: str | None = None
    timeout_seconds: float = 10.0
    retry_count: int = 0
    min_confidence: float | None = None
```
Every `__post_init__` validates its record, following section 4 FR 4–5. `JevAnswer` also checks that its probabilities are within [0, 1]. `JevDecideSettings` checks that `min_confidence`, when set, lies in [0, 1], and that the timeout and retry count are valid. `JevDecideSettings.decision_config()` returns a `DecisionModelConfig`.

### 6.7 DecisionModelResponse
**File(s):** `vidbyte/lib/runners/types.py`, `vidbyte/lib/runners/__init__.py`
```python
@dataclass(frozen=True, slots=True)
class DecisionModelResponse:
    provider: ModelProvider
    model: str
    answers: Mapping[str, JevAnswer]
    raw: Mapping[str, Any]
    usage: Mapping[str, Any] | None = None
    def answer(self, name: str) -> JevAnswer: ...
```

### 6.8 TypeSafeProvider
**File(s):** `vidbyte/providers/typesafe.py` (new), `vidbyte/providers/__init__.py`
```python
class TypeSafeProvider:
    provider = ModelProvider.TYPESAFE
    def __init__(self, *, decision_config: DecisionModelConfig | None = None, response_parser: HttpResponseParser | None = None, **_: Any) -> None
    async def run_decision(self, *, request: JevDecisionRequest, transport: HttpTransport, config: DecisionModelConfig | None = None) -> DecisionModelResponse
```
Logic:
1. Resolve the config, and raise `ProviderConfigurationError` when it is missing.
2. `_create_payload(config, request)` builds `{"model", "state", "questions": {name: {"type", "instructions", "criteria"}}}`. `noul` and `choice` send a criteria dict (option name mapped to description or `None`). `score` sends an ordered list of level names.
3. Send `transport.request(POST, url, bearer headers, json, timeout, retry_count, retry_status_codes=JEV_RETRY_STATUS_CODES, max_response_bytes, idempotency_key=...)`. The idempotency key is a per-request UUID, set only when `retry_count > 0`. A decision is read-only, so a repeat cannot duplicate a side effect.
4. `HttpResponseParser.parse_json_response()` turns a non-2xx status into `ProviderRequestError(status_code=…)`.
5. `_normalize_answers(request, parsed)` builds one `JevAnswer` per question. It raises `ProviderResponseError` on any contract drift (FR 7). For `score`, the chosen value may be a level label or an integer index into the level list. Probability keys may be labels or indices written as digit strings. Both forms are normalized to labels, because the public docs do not pin this shape.
6. Return `DecisionModelResponse(provider, model=parsed.get("model") or config.model, answers, raw=parsed, usage=parsed.get("usage") if it is a Mapping)`.

`ModelProviders.decision(config)` builds this provider through `_build_provider(..., capability="decision", decision_config=config)`.

### 6.9 DecisionModelRunner
**File(s):** `vidbyte/lib/runners/decision.py` (new)
```python
class DecisionModelRunner:
    def __init__(self, config: DecisionModelConfig | None = None, *, transport: HttpTransport | None = None) -> None
    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse
    def model_name(self) -> str
```
The constructor validates the config and builds the provider through `ModelProviders.decision`.

### 6.10 JevUsage and pricing
**File(s):** `vidbyte/agents/pricing/typesafe.py` (new), `vidbyte/agents/pricing/__init__.py`, `vidbyte/lib/registries/pricing.py`
```python
@dataclass(frozen=True, slots=True)
class JevUsage(ProviderUsage):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
    @classmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "JevUsage | None"
    def cost_usd(self, pricing: ModelPricing | None) -> float | None   # subset_billing_cost
```
Pricing entry: `ModelProvider.TYPESAFE: {"jev-latest": ModelPricing(input_per_million=0.042, output_per_million=0.0)}`, with a comment that cites the TypeSafe launch post and notes that output tokens are free.

### 6.11 ToolModelCall and ModelBackedTool
**File(s):** `vidbyte/lib/dataclasses/tool_model_usage.py` (new), `vidbyte/tools/model_backed.py` (new), `vidbyte/tools/__init__.py`
```python
@dataclass(frozen=True, slots=True)
class ToolModelCall:          # the duck type UsageTracker.record_call reads
    provider: ModelProvider
    model: str
    usage: Mapping[str, Any]

class ModelBackedTool(BaseTool):
    _MODEL_USAGE_KEY: ClassVar[str] = "model_usage"
    @classmethod
    def model_calls(cls, result: ToolResult) -> tuple[ToolModelCall, ...]
    @classmethod
    def _model_usage_metadata(cls, calls: Iterable[ToolModelCall]) -> dict[str, Any]
```
`model_calls()` returns only well-typed `ToolModelCall` entries. Anything else is ignored.

### 6.12 Runtime usage hook
**File(s):** `vidbyte/agents/runtime.py` · **Type:** Modified
Right after `self._record_operation_usage(tool, call, result)`, call `self._record_tool_model_usage(tool, result)`:
```python
def _record_tool_model_usage(self, tool: object, result: ToolResult) -> None:
    # @intent meter-tool-model-calls-once
    tool = ActivityToolFormatter.unwrap(tool) if isinstance(tool, BaseTool) else tool
    if not isinstance(tool, ModelBackedTool): return
    try:
        for model_call in tool.model_calls(result): self.usage_tracker.record_call(model_call)
    except Exception:
        self.usage_tracker.mark_recording_corrupted()
```
This runs for success and error results alike. A Jev response that arrived and was billed counts even if its answer failed normalization.

### 6.13 JevDecideTool
**File(s):** `vidbyte/tools/classifier/__init__.py`, `vidbyte/tools/classifier/jev_decide.py`, `vidbyte/tools/classifier/README.md` (all new)
```python
class JevDecideTool(ModelBackedTool):
    def __init__(self, *, settings: JevDecideSettings | None = None, runner: DecisionModelRunner | None = None, on_decision: Callable[[JevDecisionRecord], None] | None = None) -> None
    def spec(self) -> ToolSpec
    async def execute(self, call: ToolCall) -> ToolResult
```
Collaborators, which are private classes in the same module:
- `_JevDecideArguments` parses `question`, `options`, `state` and `answer_type` from `call.arguments` into a `JevQuestion` plus the state text. Options may arrive as a JSON-encoded string, as strings, or as `{name, description}` objects. When `state` is blank, the question text is used as the state.
- `_JevStateScrubber` replaces credential assignments and the configured key with `<redacted>`.
- `_JevDecisionRenderer` builds the model-facing text: the verdict line, the ranked probabilities, and the threshold note.

`execute()` flow:
1. Parse the arguments. On failure, return an `invalid_arguments` error.
2. If the tool has been disabled, return a `jev_unavailable` error.
3. Build the runner lazily from the settings. If that raises `ConfigurationError` (for example, no key), disable the tool and return `jev_unavailable`.
4. Time the `runner.arun(request)` call and handle failures:

   | Failure | `metadata.error` | Extra effect |
   |---|---|---|
   | `ProviderRequestError` with status 401 | `jev_unauthorized` | Disable the tool |
   | `ProviderRequestError` with 429 or 529 | `jev_rate_limited` | None |
   | `ProviderRequestError` with 422 | `jev_invalid_request` | None |
   | Other `ProviderRequestError` | `jev_request_failed` | None |
   | `ProviderResponseError` | `jev_bad_response` | None |

   Every failure message tells the agent to make the judgment itself.
5. Build a `JevDecisionRecord`, including the threshold check, and notify `on_decision` inside a `try`.
6. Return success with the rendered text. The metadata carries `model_usage` (one `ToolModelCall`) and `jev_decision` (the record).

A `ProviderResponseError` raised during normalization loses the parsed usage, so the provider attaches its raw usage to the error. See 6.8: `ProviderResponseError(details={"usage": ...})`. The tool reads `exc.details.get("usage")` so the call stays billable.

Spec: the name is `jev_decide` and the permission is `SAFE`. It has four parameters, each described in 4–5 general sentences with no concrete examples (field guide: model-facing tool contracts, lint S025).

---

## 7. Data Model Changes

N/A: there are no persisted schemas or database collections. The new in-memory records (`DecisionModelConfig`, `JevQuestion`, `JevDecisionRequest`, `JevAnswer`, `JevDecisionRecord`, `JevDecideSettings`, `DecisionModelResponse` and `ToolModelCall`) are frozen dataclasses, described in section 6. `UsageRollup` is unchanged. Jev calls appear as ordinary `UsageRecord`s, and they count toward `model_call_count`.

---

## 8. API Changes

N/A for HTTP endpoints. The SDK does not expose one. The outbound call is `POST https://api.typesafe.ai/v1/systemone` (section 6.8).

New public Python surface:
- **Provider layer:** `ModelProvider.TYPESAFE`, `DecisionModelConfig`, `ModelProviders.decision`, `TypeSafeProvider`, `DecisionModelRunner` and `DecisionModelResponse`.
- **Records:** `JevQuestionType`, `JevOption`, `JevQuestion`, `JevDecisionRequest`, `JevAnswer`, `JevDecisionRecord` and `JevDecideSettings`.
- **Pricing and tools:** `JevUsage`, `ToolModelCall`, `ModelBackedTool` and `JevDecideTool`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-decide-tool.md` | This design |
| MODIFY | `vidbyte/lib/enums/model_provider.py` | `TYPESAFE` member + `JevUsage` binding |
| CREATE | `vidbyte/lib/enums/jev.py` | `JevQuestionType` |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export `JevQuestionType` |
| CREATE | `vidbyte/lib/constants/jev.py` | Jev limits and defaults |
| MODIFY | `vidbyte/lib/constants/runners.py` | `RUNNER_TYPE_DECISION` + catalog entries |
| MODIFY | `vidbyte/lib/constants/__init__.py` | Export new constants |
| MODIFY | `vidbyte/lib/registries/models.py` | TypeSafe default model/key/endpoint |
| MODIFY | `vidbyte/lib/registries/pricing.py` | `jev-latest` rate |
| MODIFY | `vidbyte/lib/dataclasses/model_configs.py` | `DecisionModelConfig` |
| MODIFY | `vidbyte/lib/config/__init__.py`, `vidbyte/lib/config/models.py` | Export `DecisionModelConfig` |
| CREATE | `vidbyte/lib/dataclasses/jev.py` | Jev request/answer/record/settings records |
| CREATE | `vidbyte/lib/dataclasses/tool_model_usage.py` | `ToolModelCall` |
| MODIFY | `vidbyte/lib/runners/types.py` | `DecisionModelResponse` |
| CREATE | `vidbyte/lib/runners/decision.py` | `DecisionModelRunner` |
| MODIFY | `vidbyte/lib/runners/__init__.py` | Export runner + response |
| MODIFY | `vidbyte/lib/runners/utility.py` | Refuse decision runner type clearly |
| CREATE | `vidbyte/providers/typesafe.py` | `TypeSafeProvider` |
| MODIFY | `vidbyte/providers/__init__.py` | `ModelProviders.decision` + export |
| CREATE | `vidbyte/agents/pricing/typesafe.py` | `JevUsage` |
| MODIFY | `vidbyte/agents/pricing/__init__.py` | Export `JevUsage` |
| CREATE | `vidbyte/tools/model_backed.py` | `ModelBackedTool` seam |
| MODIFY | `vidbyte/agents/runtime.py` | `_record_tool_model_usage` |
| CREATE | `vidbyte/tools/classifier/__init__.py` | Package exports |
| CREATE | `vidbyte/tools/classifier/jev_decide.py` | `JevDecideTool` |
| CREATE | `vidbyte/tools/classifier/README.md` | Folder map + data-egress note |
| MODIFY | `vidbyte/tools/__init__.py` | Export `JevDecideTool`, `ModelBackedTool` |
| CREATE | `tests/test_jev_decide_tool.py` | Unit + integration tests |
| CREATE | `scripts/test_jev_decide_tool.py` | Phase-5 verification script |

---

## 10. Testing Plan

All network calls use a fake `HttpTransport` that records requests and returns scripted `HttpResponse`s. No test reaches TypeSafe.

### Unit Tests
- `DecisionModelConfig` → `it rejects a non-TypeSafe provider` — [Hidden Assumption]
- `DecisionModelConfig` → `it rejects negative and bool retry_count` — [Edge Case]
- `DecisionModelConfig` → `it raises when neither api_key nor TYPESAFE_API_KEY is set` — [Hidden Assumption]
- `JevQuestion` → `it rejects a choice with 1 option and accepts exactly 255, rejecting 256` — [Edge Case]
- `JevQuestion` → `it rejects duplicate and blank option names` — [Edge Case]
- `JevQuestion` → `it requires noul options to be exactly true/false` — [Hidden Assumption]
- `JevDecisionRequest` → `it rejects blank state, zero questions, duplicate question names` — [Edge Case]
- `TypeSafeProvider` → `it posts to {endpoint}/systemone with bearer auth and choice criteria dict` — [Silent Failure]
- `TypeSafeProvider` → `it sends score criteria as an ordered list preserving level order` — [Silent Failure]
- `TypeSafeProvider` → `it normalizes noul p into true/false probabilities and confidence` — [Silent Failure]
- `TypeSafeProvider` → `it normalizes score index answers and digit-string probability keys to labels` — [Hidden Assumption]
- `TypeSafeProvider` → `it raises ProviderResponseError when an answer is missing` — [Hidden Failure]
- `TypeSafeProvider` → `it raises when the chosen label is not an option` — [Silent Failure]
- `TypeSafeProvider` → `it raises on probability outside [0,1] or non-numeric` — [Silent Failure]
- `TypeSafeProvider` → `it attaches usage to ProviderResponseError details` — [Hidden Failure]
- `TypeSafeProvider` → `it raises ProviderRequestError with status 401 on auth failure` — [Hidden Failure]
- `ModelProviders.decision` → `it rejects a non-decision provider` — [Hidden Assumption]
- `Runner.build` → `it refuses jev-latest with a decision-model ConfigurationError` — [Hidden Assumption]
- `ProviderModelRegistry` → `a set TYPESAFE_API_KEY does not add typesafe to active text providers` — [Hidden Failure]
- `JevUsage` → `it parses input/output and derives total` — [Edge Case]
- `JevUsage` → `it returns None for a payload with no token fields` — [Edge Case]
- `JevUsage` → `cost is 0.042 per million input and zero for output tokens` — [Silent Failure]
- `ModelPricingRegistry` → `resolves typesafe/jev-latest; ModelProvider.TYPESAFE.usage_class() is JevUsage` — [Hidden Assumption]
- `ModelBackedTool` → `model_calls ignores malformed metadata entries` — [Hidden Assumption]
- `JevDecideTool` → `invalid options (1 option, >255, non-list) return invalid_arguments without a network call` — [Edge Case]
- `JevDecideTool` → `options given as a JSON string or {name, description} objects both parse` — [Edge Case]
- `JevDecideTool` → `blank state falls back to the question text` — [Edge Case]
- `JevDecideTool` → `renders every option's probability ranked high to low, not only the argmax` — [Silent Failure]
- `JevDecideTool` → `below min_confidence the output flags it and passed_threshold is False` — [Silent Failure]
- `JevDecideTool` → `min_confidence None never flags` — [Edge Case]
- `JevDecideTool` → `missing API key returns jev_unavailable and disables later calls with no network` — [Hidden Assumption]
- `JevDecideTool` → `401 disables the tool; 429/529 does not` — [Hidden Failure]
- `JevDecideTool` → `timeout/network error returns jev_request_failed, never raises` — [Hidden Failure]
- `JevDecideTool` → `bad response still reports model_usage so the call is billed` — [Silent Failure]
- `JevDecideTool` → `state credential assignments and the configured key are redacted before sending` — [Hidden Assumption]
- `JevDecideTool` → `on_decision callback raising does not fail the call` — [Hidden Failure]
- `JevDecideTool` → `the API key never appears in output or metadata` — [Silent Failure]
- `JevDecideTool` → `spec has four parameters, each with a 4–5 sentence description` — [Edge Case]

### Integration Tests
- A fake text runner calls `jev_decide`, then finishes. The test asserts that `agent.get_usage().calls` holds one `typesafe` record with `cost_usd == input_tokens * 0.042e-6`, that `cost_complete` is true when the main model's call is priced, and that the tool output reached the next model call. This is the silent-failure path: without the runtime hook, the run succeeds with Jev silently unbilled.
- The same run with a failing Jev transport: the run completes, the tool result is an error, and no `typesafe` record is written.
- An activity-wrapped `JevDecideTool` (`with_activity`) is still metered, because the tool is unwrapped before the `isinstance` check.
- A usage-tracker exception during Jev recording marks the rollup `CORRUPTED` without failing the run.

### Manual / QA Test Cases
1. Given a real `TYPESAFE_API_KEY`, when an agent calls `jev_decide` with a yes/no question given as two options, then the output shows both probabilities and the rollup shows a `typesafe` cost below $0.0001 — [Edge Case]
2. Given no key, when the agent calls `jev_decide` twice, then both calls return "Jev is unavailable" and only the first attempts to build a runner — [Hidden Assumption]
3. Given 256 options, when called, then the tool rejects the call before any network request — [Edge Case]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| TypeSafe Jev API | `POST https://api.typesafe.ai/v1/systemone`, model `jev-latest` | Calibrated decisions | Early access and waitlist. The shape and pricing are vendor claims and could change. The `score` answer shape is not pinned. |
| `httpx` (existing) | via `HttpTransport` | Async HTTP | None (already used) |

---

## 12. Rollout & Deployment

- There is no feature flag. The tool is opt-in: a caller must add `JevDecideTool()` to an agent's tools.
- The change is not breaking. Adding a `ModelProvider` member changes the `fork` tool's provider enum list, and a fork to `typesafe` fails with the new clear decision-model error.
- Rollback: revert the PR. No persisted state is involved.

---

## 13. Open Questions

- [ ] Confirm the `score` answer's exact shape (whether it is a label or an index, and what the `probabilities` keys are) against a live key. The normalizer accepts both forms for now.
- [ ] Should `jev_decide` count toward `TokenBudgetMiddleware` token budgets? Today it adds to the cost rollup only, not to `state.tokens_used`.
- [ ] Should the Codex harness agent's tool bridge also record `ModelBackedTool` usage? (Follow-up.)
- [ ] Choose a default `min_confidence` once replay evidence exists (Jev skill, build 0).

---

## 14. Alternatives Considered

### Alternative 1: Price Jev as a `PricedOperationTool` operation
- **What:** add a `("decision", "typesafe")` operation with `reported_cost_usd` computed in the tool.
- **Why rejected:** Jev bills per token. The operation axis would drop the token counts, and computing cost in the tool would break C005. The token axis (`record_call` with `JevUsage`) is the correct ledger.

### Alternative 2: Bind the agent's tracker into the tool
- **What:** give the tool a reference to `agent._usage_tracker` at bind time.
- **Why rejected:** it reaches into private agent state, breaks for tools shared across agents, and duplicates the runtime's single recording point. The metadata seam mirrors the existing operation-usage path.

### Alternative 3: Put the provider in `vidbyte/lib/providers/`
- **What:** the location the request guessed.
- **Why rejected:** that package holds database persistence providers. Model providers live in `vidbyte/providers/`, which is the layer the enum, registries and runners already route through.

### Alternative 4: Make Jev a text runner
- **What:** register `jev-latest` as `RUNNER_TYPE_TEXT`.
- **Why rejected:** Jev cannot generate text. A text runner would let an agent select it and then fail deep inside the loop. A dedicated decision runner type keeps validation honest and fails early.

### Alternative 5: Ship a default confidence threshold
- **Why rejected:** the Jev skill's stop condition forbids hard-coding a threshold without replay evidence. The tool reports the full distribution instead, and the application can opt in to a threshold.
