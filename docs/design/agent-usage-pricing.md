# Design Doc: Agent Usage & Pricing

**Status:** Draft
**Author:** OpenCode
**Created:** 2026-07-22
**Last Updated:** 2026-07-22

---

## 1. Overview

This feature adds Vercel-AI-Gateway-style token-usage and cost accounting to `BaseAgent`. Every text-model call made during an agent run is parsed into a provider-native usage object, priced against a built-in per-model rate table, and accumulated into a per-run rollup. Usage tracking is owned entirely by the agent — the tracker is built internally from the agent's own model identity, so there are no pricing/usage constructor params. Developers read usage/pricing through agent functions both mid-run (live `agent.get_usage()`) and after run (`agent.get_usage()`, `agent.get_cost_usd()`, and `AgentMessage.metadata["usage_rollup"]`). Per-call usage is observable mid-run through `MiddlewareContext.model_usage` on the existing `after_model_response` hook, so a user-supplied middleware is the sanctioned way to react to each LLM call as it happens.

The design follows the user's explicit direction: per-provider usage classes with provider-native fields and per-class cost formulas, bound to provider string via a registry; the feature lives in `vidbyte/agents/pricing/`; the source-of-truth rate table lives in the lib folder (`vidbyte/lib/registries/pricing.py`).

---

## 2. Goals & Non-Goals

### Goals

- One `ProviderUsage` class per provider response shape, each owning its native fields and its own `cost_usd()` formula, bound to a provider via a string/enum registry.
- A source-of-truth rate table (`PROVIDER_PRICING`) in `vidbyte/lib/registries/pricing.py` covering at least every default text model in `ProviderModelRegistry.DEFAULT_PROVIDER_MODELS`, stamped with `PRICING_AS_OF`.
- Per-call cost computed inside the agent runtime loop and summed into a `UsageRollup`; cost is `None` when pricing is unknown — never fabricated.
- Agent-class API: usage tracking is constructed internally from the agent's model identity (no `pricing`/`on_usage` constructor params); `agent.get_usage()` and `agent.get_cost_usd()` methods usable mid-run and after run.
- Final-return surface: `AgentMessage.metadata["usage_rollup"]` carries the `UsageRollup` (additive key; existing `metadata["usage"]` raw provider dict and `metadata["tokens_used"]` are unchanged).
- Middleware surface: `MiddlewareContext.model_usage` populated on `AFTER_MODEL_RESPONSE` contexts with the provider-native usage object.
- Fix the existing Gemini usage gap centrally: Gemini runs currently report `tokens_used=None` because `token_usage_from_response` never reads `TextModelResponse.usage` nor `usageMetadata` camelCase keys.
- OpenRouter: request provider-reported cost (`"usage": {"include": true}`) and prefer it over table math when present.

### Non-Goals

- Streaming usage capture (`StreamingTextModelRunner` discards usage and is not wired into `BaseAgent`).
- Non-text modality pricing (image/video per-unit, ElevenLabs per-character); those runs return an empty rollup.
- Platform-side credits/billing concepts; the SDK reports `cost_usd` only.
- MCTS/actor runtimes (they already reject middleware; the tracker wiring in this doc targets `AgentRuntime` / linear only).
- Restructuring `metadata["usage"]` (raw provider dict stays; the structured data lands on the additive `usage_rollup` key).
- A built-in `UsageTrackingMiddleware` class (per-call usage is exposed on `MiddlewareContext.model_usage`, so any user-supplied middleware can consume it).
- No new feature tests, per the workflow for this change; existing CI gates still apply.

---

## 3. Background & Context

`BaseAgent` (`vidbyte/agents/base.py`) runs its text loop in `AgentRuntime._arun_once` (`vidbyte/agents/runtime.py:158`). Today the only usage accounting is a cumulative `tokens_used: int | None` summed per iteration (`runtime.py:338`) from `token_usage_from_response` (`vidbyte/lib/token_usage.py`), which discards the input/output split and never reads `TextModelResponse.usage` — so Gemini (whose adapter stores `usageMetadata` in the `usage` attribute) reports `tokens_used=None`.

Each provider adapter already stores the provider's usage sub-dict on `TextModelResponse.usage` (`vidbyte/lib/runners/types.py:15`): OpenAI Responses (`input_tokens`/`output_tokens`/`total_tokens` + `*_tokens_details`), Anthropic Messages (`input_tokens`/`output_tokens` + `cache_creation_input_tokens`/`cache_read_input_tokens`), Gemini (`promptTokenCount`/`candidatesTokenCount`/`thoughtsTokenCount`/`cachedContentTokenCount`/`totalTokenCount`), and OpenAI-compatible chat completions for xAI/DeepSeek/GLM/MiniMax/OpenRouter (`prompt_tokens`/`completion_tokens`/`total_tokens`). Because the sub-dict is already extracted per provider, parsing can happen centrally at the runtime boundary with zero provider-adapter changes (except the OpenRouter request-payload addition).

Cache-token billing semantics differ per provider and force per-class cost formulas: OpenAI and Gemini report cached tokens as a discounted *subset* of input tokens, while Anthropic reports cache write/read as *additive* buckets billed at ~1.25x/~0.1x the input rate. A single normalized shape would lose these distinctions.

Middleware (`vidbyte/middleware/base.py`) already fires `after_model_response` with `ctx.model_response` set to the raw `TextModelResponse`; `MiddlewareContext` (`vidbyte/lib/dataclasses/middleware.py:151`) types such payload fields as `object | None` (see `model_response`) to avoid lib→agents imports, and this doc follows that precedent for `model_usage`.

In-flight related work: the PR-282 worktree contains an unreleased `vidbyte/sessions/` package with `AgentUsage`/`UsageRollup` names and a caller-supplied `prices: Mapping[str, float]` convention. This doc reuses the `UsageRollup` name and supports caller-supplied prices via registry overrides so the two efforts converge rather than conflict.

Audit notes:

- The main checkout is on branch `feat/context-minimal-fanout-trace` with unrelated in-flight changes; implementation must branch from `origin/main` in a fresh worktree.
- Baseline test run on the current checkout: **1208 collected — 5 failed, 1202 passed, 1 skipped**. The 5 failures are pre-existing and unrelated: `test_single_provider_configured` (grader StopIteration), `test_llm_span_inputs_include_prompt_model_and_safe_metadata` and `test_llm_span_messages_include_full_input_when_history_exists` (`KeyError: 'prompt'` span attrs), `test_langsmith_update_uses_datetime_end_time`. Baseline must be re-measured on `origin/main` inside the worktree; the gate for this feature is *no new failures beyond the recorded main baseline*.
- `scripts/run_ci.py` does not exist on this checkout; the only tracked workflow is tag-triggered `publish.yml`. Canonical local gate: `python -m pytest tests/ -q` plus an editable-install packaging check.
- An untracked in-flight `.github/workflows/quality.yml` + `.semgrep/rules.yml` adds a Semgrep gate with one rule (`redundant-mapping-get-then-subscript`): never `$MAP.get($KEY)`-None-check then `$MAP[$KEY]`; store the lookup in a local. New code in this feature must comply.

---

## 4. Requirements

### Functional Requirements

1. A `ProviderUsage` ABC must exist in `vidbyte/agents/pricing/base.py` exposing `input_tokens`, `output_tokens`, `total_tokens` properties, a `from_usage_payload` classmethod, and a `cost_usd(pricing)` method, plus a `raw` passthrough of the provider's usage sub-dict.
2. Concrete classes must be bound to providers through a registry: `OpenAIUsage`→OPENAI, `AnthropicUsage`→ANTHROPIC, `GeminiUsage`→GEMINI, `ChatCompletionUsage`→XAI/DEEPSEEK/GLM/MINIMAX, `OpenRouterUsage`→OPENROUTER. Providers without text usage (ELEVENLABS, PLAYAI) resolve to `None`.
3. `parse_usage(provider, payload)` must coerce provider strings to `ModelProvider` (inline, not via a standalone helper), dispatch through the registry, and return `None` (never raise) for missing/unknown/malformed payloads.
4. The shared cost math (`effective_rates`, `subset_billing_cost`) and token coercion (`coerce_int`) live as methods on the `ProviderUsage` base class, so each provider subclass computes cost through `self` rather than free functions. Each class's `cost_usd` must implement its provider's billing semantics: OpenAI/compatible subtract the cached subset before applying input rate; Anthropic adds cache creation/read buckets at their own rates; Gemini bills `thoughtsTokenCount` as output and treats `cachedContentTokenCount` as an input subset. Cache rates fall back to the base input rate when the table omits them. `cost_usd(None)` must return `None`.
5. `ModelPricing` and `ModelPricingRegistry` must live in `vidbyte/lib/registries/pricing.py`; `resolve()` must try exact match, then longest-prefix match (dated model variants), then `None`. `register()` must allow user overrides/additions. `PROVIDER_PRICING` must include every default text model from `ProviderModelRegistry` and carry `PRICING_AS_OF`.
6. `ModelPricing` must support optional context-tier fields (`threshold_tokens`, `input_over_threshold_per_million`, `output_over_threshold_per_million`); when input tokens exceed the threshold and tier rates exist, cost functions must use the tier rates for the whole call.
7. `UsageTracker` (in `vidbyte/agents/pricing/tracker.py`) must defensively parse any response object (`getattr` for provider/model/usage), record `UsageRecord`s, and build a `UsageRollup`. Unparseable responses are skipped (record nothing), so duck-typed fake runners in existing tests are unaffected.
8. `AgentRuntime` must accept an optional `usage_tracker` param (defaulting to a fresh `UsageTracker`), record one usage entry after every successful model call (at the existing token-accumulation point, `runtime.py:338`), and expose the tracker as `runtime.usage_tracker`.
9. `AgentRuntime._runtime_metadata` must add `"usage_rollup": UsageRollup` so `AgentMessage.metadata["usage_rollup"]` is populated on every terminal path (final response, budget stop, middleware abort), because all such paths flow through `_runtime_metadata` or `_finish_result`.
10. `MiddlewareContext` must gain `model_usage: object | None = None`; the `AFTER_MODEL_RESPONSE` context must carry the call's `ProviderUsage` (or `None` when unparseable). All other hooks leave it `None`.
11. `BaseAgent` must own a `UsageTracker` built internally (no `pricing`/`on_usage` constructor params; the default rate table prices every model the agent can run), reset it at the start of each `generate_reply`, and pass it into `_runtime()`. Per-call usage is surfaced to user middleware through `MiddlewareContext.model_usage`.
12. `BaseAgent.get_usage()` must return the current `UsageRollup` (live mid-run and final after run), delegating to the internal aggregate agent when one is configured. `BaseAgent.get_cost_usd()` must return the rollup's `cost_usd`.
13. `token_usage_from_response` must additionally check `response.usage` (Mapping) — including Gemini camelCase keys (`totalTokenCount`, or `promptTokenCount`+`candidatesTokenCount`+`thoughtsTokenCount`) — after the metadata check and before the raw-payload check, fixing Gemini `tokens_used=None` without changing existing precedence for current callers.
14. `OpenRouterProvider` must include `"usage": {"include": true}` in its chat-completions payload (new provider-API usage, explicitly called out), and `OpenRouterUsage.cost_usd` must prefer the provider-reported `raw["cost"]` when present, falling back to table math.
15. Per-call usage observation is done through a user-supplied middleware reading `MiddlewareContext.model_usage`; a middleware raising is already isolated by the existing middleware error handling, so a bad observer cannot break a run.
16. New exports: `ModelPricing`, `ModelPricingRegistry`, `PROVIDER_PRICING`, `ProviderUsage`, `UsageRecord`, `UsageRollup`, `UsageTracker`, `parse_usage` surfaced from `vidbyte.agents.pricing` and the relevant names from the root `vidbyte` package, following existing export patterns.

### Non-Functional Requirements

- Backward compatibility: no changes to existing public signatures except additive keyword params with `None` defaults; `metadata["usage"]` and `metadata["tokens_used"]` semantics unchanged; all existing tests must pass exactly as on the recorded baseline.
- Concurrency: per-run state lives on the run's tracker, never on shared class state; `get_usage()` has documented last-run semantics identical to `last_reply`.
- Cost integrity: unknown model/provider ⇒ `cost_usd=None` and `cost_complete=False`; no estimated or assumed rates.
- Performance: O(1) work per model call; no message-history inspection; rollup built from the retained per-call tuple.
- Style: class-first design; every function/method signature on one line; a 1–2 line comment under every signature; sparse comments elsewhere; comply with the incoming Semgrep rule (no get-then-subscript on mappings).

---

## 5. High-Level Design

Three layers, respecting the repo's existing `lib` = data/registries vs `agents` = behavior split:

1. **Rate data (lib):** `vidbyte/lib/registries/pricing.py` holds `ModelPricing`, the `PROVIDER_PRICING` source-of-truth table with `PRICING_AS_OF`, and `ModelPricingRegistry` (exact → longest-prefix resolution, `register()` overrides). It imports only `vidbyte.lib.enums`/`vidbyte.lib.errors`, same as the neighboring `models.py`.
2. **Provider usage classes (agents/pricing):** `vidbyte/agents/pricing/base.py` defines the `ProviderUsage` ABC, the `usage_for(provider)` decorator registry, and `parse_usage()`. One module per provider shape implements the native fields and cost formula. `records.py` holds `UsageRecord`/`UsageRollup`; `tracker.py` holds `UsageTracker`.
3. **Runtime + agent wiring:** `AgentRuntime` records one `UsageRecord` per successful model call into its `UsageTracker` and stamps `usage_rollup` into result metadata; `MiddlewareContext.model_usage` carries the per-call object; `BaseAgent` owns the tracker, resets it per run, and exposes `get_usage()`/`get_cost_usd()`.

Data flow per model call:

```
provider HTTP response
  → TextModelResponse(provider, model, usage=<provider usage sub-dict>)   [unchanged]
  → runtime: usage_tracker.record_call(raw_result)
      → parse_usage(response.provider, response.usage)  → ProviderUsage | None
      → pricing.resolve(provider, model)                → ModelPricing | None
      → usage.cost_usd(pricing)                         → float | None
      → append UsageRecord(call_index, provider, model, usage, cost_usd)
  → ctx.model_usage = record.usage  (AFTER_MODEL_RESPONSE hook)           [mid-run middleware surface]
  → metadata["usage_rollup"] = tracker.rollup()  at run end               [final-return surface]
  → agent.get_usage() / agent.get_cost_usd()                              [agent function surface]
```

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/registries/pricing.py` (new)

```python
@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None = None
    cache_write_per_million: float | None = None
    threshold_tokens: int | None = None
    input_over_threshold_per_million: float | None = None
    output_over_threshold_per_million: float | None = None

PRICING_AS_OF: str = "2026-07-22"

PROVIDER_PRICING: dict[ModelProvider, dict[str, ModelPricing]] = { ... }

class ModelPricingRegistry:
    def __init__(self, table: Mapping[ModelProvider, Mapping[str, ModelPricing]] | None = None) -> None: ...
    @classmethod
    def default(cls) -> "ModelPricingRegistry": ...
    def resolve(self, provider: ModelProvider | str, model: str) -> ModelPricing | None: ...
    def register(self, provider: ModelProvider | str, model: str, pricing: ModelPricing) -> None: ...
```

- `resolve` order: exact `table[provider][model]` → longest key that is a prefix of `model` (handles `gpt-5.5-2026-05-01`→`gpt-5.5`) → `None`.
- `default()` returns a registry over `PROVIDER_PRICING`; each call returns an independent registry so `register()` overrides never mutate shared class state.
- Table population rule: every TEXT model in `ProviderModelRegistry.DEFAULT_PROVIDER_MODELS` (gpt-5.5, claude-sonnet-4-6, gemini-2.5-pro, grok-3, deepseek-v3, glm-4-plus, minimax-text-01) plus widely used siblings, with rates verified against official provider pricing pages at implementation time. Rates are never invented; anything unverifiable is omitted (resolving to `cost=None`).

### 6.2 `vidbyte/agents/pricing/base.py` (new)

```python
class ProviderUsage(ABC):
    raw: Mapping[str, Any]

    @classmethod
    @abstractmethod
    def from_usage_payload(cls, payload: Mapping[str, Any]) -> "ProviderUsage | None": ...
    @property
    @abstractmethod
    def input_tokens(self) -> int | None: ...
    @property
    @abstractmethod
    def output_tokens(self) -> int | None: ...
    @property
    @abstractmethod
    def total_tokens(self) -> int | None: ...
    @abstractmethod
    def cost_usd(self, pricing: ModelPricing | None) -> float | None: ...

def usage_for(provider: ModelProvider) -> Callable[[type[ProviderUsage]], type[ProviderUsage]]: ...
def parse_usage(provider: ModelProvider | str | None, payload: Mapping[str, Any] | None) -> ProviderUsage | None: ...
```

- `parse_usage` coerces `str`→`ModelProvider` (`ValueError`→`None`), looks up the registry, and delegates to `from_usage_payload`; all parsing is defensive (`isinstance` checks, `None` on mismatch), never raises.

### 6.3 Provider classes (new modules under `vidbyte/agents/pricing/`)

- `openai.py` — `OpenAIUsage` (bound: OPENAI). Fields: `input_tokens`, `output_tokens`, `total_tokens`, `cached_input_tokens` (`input_tokens_details.cached_tokens`), `reasoning_tokens` (`output_tokens_details.reasoning_tokens`). Cost: `((input − cached) × in_rate + cached × (cache_read_rate or in_rate) + output × out_rate) / 1e6`, with context-tier rate swap when applicable.
- `compatible.py` — `ChatCompletionUsage` (bound: XAI, DEEPSEEK, GLM, MINIMAX). Same math as OpenAI but reads `prompt_tokens`/`completion_tokens` and `prompt_tokens_details.cached_tokens`/`completion_tokens_details.reasoning_tokens`.
- `anthropic.py` — `AnthropicUsage` (bound: ANTHROPIC). Fields: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`. `total_tokens` = sum of all four (cache buckets are additive). Cost: `input × in_rate + cache_write × (cache_write_rate or in_rate) + cache_read × (cache_read_rate or in_rate) + output × out_rate`.
- `gemini.py` — `GeminiUsage` (bound: GEMINI). Fields: `promptTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount`, `cachedContentTokenCount`, `totalTokenCount`. `input_tokens` = prompt; `output_tokens` = candidates + thoughts; cost treats cached as an input subset and supports the context-tier fields (Gemini's documented >200k tier).
- `openrouter.py` — `OpenRouterUsage(ChatCompletionUsage)` (bound: OPENROUTER). `cost_usd` returns `float(raw["cost"])` when the provider reported it (response to the new `usage.include` request field); otherwise table math.

### 6.4 `vidbyte/agents/pricing/records.py` (new)

```python
@dataclass(frozen=True, slots=True)
class UsageRecord:
    call_index: int
    provider: str
    model: str
    usage: ProviderUsage
    cost_usd: float | None

@dataclass(frozen=True, slots=True)
class UsageRollup:
    calls: tuple[UsageRecord, ...]
    model_call_count: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    cost_complete: bool
```

- Token sums are `None` when no call reported that component; `cost_usd` sums known costs (`None` when none known); `cost_complete` is `True` only when every recorded call has a non-`None` cost. The per-call ledger is retained because the tool loop re-bills input every iteration, so "sum of per-call costs" (correct) differs from "cost of final-state tokens" (wrong).

### 6.5 `vidbyte/agents/pricing/tracker.py` (new)

```python
class UsageTracker:
    def __init__(self, *, pricing: ModelPricingRegistry | None = None) -> None: ...
    def record_call(self, response: object) -> UsageRecord | None: ...
    def rollup(self) -> UsageRollup: ...
    def reset(self) -> None: ...
    @property
    def records(self) -> tuple[UsageRecord, ...]: ...
```

- `record_call` reads `provider`/`model`/`usage` via `getattr`, tolerating fake/duck-typed responses (records nothing when provider or payload is unusable). `call_index` is the 1-based length of the ledger at insert time.
- `pricing=None` resolves to `ModelPricingRegistry.default()`.

### 6.6 Runtime wiring (`vidbyte/agents/runtime.py`, modify)

- `__init__` gains `usage_tracker: UsageTracker | None = None`; stored as `self.usage_tracker = usage_tracker or UsageTracker()`.
- In `_arun_once`, immediately after the existing `tokens_used` accumulation (line 338): `usage_record = self.usage_tracker.record_call(raw_result)`.
- The `AFTER_MODEL_RESPONSE` `_middleware_context(...)` call passes `model_usage=usage_record.usage if usage_record else None`; `_middleware_context` gains the matching `model_usage` kwarg forwarded into `MiddlewareContext`.
- `_runtime_metadata` adds `"usage_rollup": self.usage_tracker.rollup()` so all terminal paths (final response, `_stopped_result`, `_middleware_abort_result`) carry it automatically.

### 6.7 Agent wiring (`vidbyte/agents/base.py`, modify)

- Constructor: no pricing/usage params; builds `self._usage_tracker = UsageTracker()` (default rate table, resolved per model call at record time).
- `generate_reply`: after the aggregate-agent delegation, calls `self._usage_tracker.reset()` before `_run_direct`.
- `_runtime()`: passes `usage_tracker=self._usage_tracker`.
- New public methods:

```python
def get_usage(self) -> UsageRollup:
    # Returns the live or final usage rollup, delegating to the aggregate agent when configured.
    if self._aggregate_agent is not None:
        return self._aggregate_agent.get_usage()
    return self._usage_tracker.rollup()

def get_cost_usd(self) -> float | None:
    # Returns total known cost in USD for the current or most recent run.
    return self.get_usage().cost_usd
```

### 6.8 `vidbyte/lib/token_usage.py` (modify)

Insert a `response.usage` Mapping check between the existing metadata check and raw-payload check, handled by extending `_usage_total`-style extraction with Gemini keys (`totalTokenCount`; else `promptTokenCount` + `candidatesTokenCount` + `thoughtsTokenCount`). Existing precedence is preserved; this only adds a previously missed source.

### 6.9 `vidbyte/lib/dataclasses/middleware.py` (modify)

Add `model_usage: object | None = None` to `MiddlewareContext`, typed loosely for the same lib→agents layering reason as `model_response`.

### 6.10 `vidbyte/providers/openrouter.py` (modify)

Attach `"usage": {"include": true}` in the OpenRouter payload (override `_create_payload` or extend `_attach_extra_body`-style hook). This is a new provider-API interaction, called out per workflow rules; it is additive request metadata that OpenRouter documents for returning cost.

### 6.11 Exports (modify `vidbyte/agents/pricing/__init__.py` [new], `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`)

`vidbyte.agents.pricing` exports `ProviderUsage`, `parse_usage`, `usage_for`, `UsageRecord`, `UsageRollup`, `UsageTracker`. Root `vidbyte` additionally exports `ModelPricing`, `ModelPricingRegistry`, `UsageRecord`, `UsageRollup`, `UsageTracker` following the existing grouped-import pattern.

---

## 7. Data Model Changes

- **New:** `ModelPricing` (frozen, lib), `PROVIDER_PRICING` table + `PRICING_AS_OF` (lib), `ProviderUsage` ABC + 5 concrete classes (agents/pricing), `UsageRecord`, `UsageRollup` (frozen dataclasses, agents/pricing), `UsageTracker` (mutable, per-run).
- **Modified:** `MiddlewareContext` gains `model_usage: object | None = None` (additive, default preserves existing constructions); `AgentMessage.metadata` gains the `"usage_rollup"` key at runtime (dataclass itself unchanged).
- **Unchanged:** `TextModelResponse` (the `usage` Mapping stays the provider sub-dict; parsing happens at the runtime boundary, so no lib→agents import is introduced and no adapter except OpenRouter is touched).

---

## 8. API Changes

- `BaseAgent.__init__`: no new params — usage tracking is built internally from the agent's model identity.
- `BaseAgent.get_usage() -> UsageRollup`, `BaseAgent.get_cost_usd() -> float | None` (new public methods).
- `AgentRuntime.__init__`: additive `usage_tracker=` kwarg; new public attribute `runtime.usage_tracker`.
- `MiddlewareContext.model_usage` (new field).
- `vidbyte.agents.pricing` public surface: `ProviderUsage`, `usage_for`, `parse_usage`, `UsageRecord`, `UsageRollup`, `UsageTracker`.
- `vidbyte.lib.registries.pricing` public surface: `ModelPricing`, `ModelPricingRegistry`, `PROVIDER_PRICING`, `PRICING_AS_OF`.
- OpenRouter outbound payloads now include `"usage": {"include": true}`.
- No breaking changes; no deprecations.

---

## 9. File Change Manifest

**Create (11):**

| File | Contents |
|---|---|
| `docs/design/agent-usage-pricing.md` | this doc |
| `vidbyte/lib/registries/pricing.py` | `ModelPricing`, `PROVIDER_PRICING`, `PRICING_AS_OF`, `ModelPricingRegistry` |
| `vidbyte/agents/pricing/__init__.py` | package exports |
| `vidbyte/agents/pricing/base.py` | `ProviderUsage` ABC, `usage_for` registry, `parse_usage` |
| `vidbyte/agents/pricing/openai.py` | `OpenAIUsage` |
| `vidbyte/agents/pricing/anthropic.py` | `AnthropicUsage` |
| `vidbyte/agents/pricing/gemini.py` | `GeminiUsage` |
| `vidbyte/agents/pricing/compatible.py` | `ChatCompletionUsage` (xAI/DeepSeek/GLM/MiniMax) |
| `vidbyte/agents/pricing/openrouter.py` | `OpenRouterUsage` |
| `vidbyte/agents/pricing/records.py` | `UsageRecord`, `UsageRollup` |
| `vidbyte/agents/pricing/tracker.py` | `UsageTracker` |

**Modify (7):**

| File | Change |
|---|---|
| `vidbyte/lib/token_usage.py` | read `response.usage` + Gemini camelCase keys (central Gemini fix) |
| `vidbyte/lib/dataclasses/middleware.py` | `MiddlewareContext.model_usage` field |
| `vidbyte/agents/runtime.py` | tracker param, per-call record, ctx `model_usage`, `usage_rollup` metadata |
| `vidbyte/agents/base.py` | internal tracker ownership + reset (no new params), `get_usage()`/`get_cost_usd()` |
| `vidbyte/providers/openrouter.py` | `usage: {include: true}` request field |
| `vidbyte/agents/__init__.py` | re-export pricing symbols |
| `vidbyte/__init__.py` | root exports for pricing/usage names |

**Delete (0).**

---

## 10. Dependencies

No new third-party dependencies (`pydantic`, `httpx` remain the only runtime deps). Internal: `vidbyte.agents.pricing` depends on `vidbyte.lib.enums`, `vidbyte.lib.registries.pricing`; lib never imports from agents. Overlap coordination: naming (`UsageRollup`, per-model price overrides) is aligned with the in-flight PR-282 sessions work to minimize merge friction.

---

## 11. Rollout

1. Create worktree from `origin/main`: `git worktree add ../worktrees/feat/agent-usage-pricing -b feat/agent-usage-pricing origin/main` (the main checkout is dirty with unrelated work and is not on `main`; do not branch from it).
2. Commit this design doc first inside the worktree.
3. Re-measure the pytest baseline on `origin/main` in the worktree and record it before implementing.
4. Implement in atomic commits: (a) lib pricing table + registry, (b) pricing package (ABC, provider classes, records, tracker), (c) runtime + middleware-context wiring, (d) agent API + exports, (e) OpenRouter payload + token_usage Gemini fix.
5. Local gate: `python -m pytest tests/ -q` must show zero new failures vs the recorded main baseline (the 5 known failures listed in §3, or the re-measured main equivalent, may persist as out-of-scope baseline defects); packaging check `python -m pip install -e .` + import smoke of the new modules; verify new code complies with the incoming `.semgrep` rule.
6. Open draft PR (`gh pr create --draft`, base `main`), watch `gh pr checks`; only `publish.yml` exists on main (tag-triggered), so no PR checks are expected — green local gate is the bar.
7. Handoff report per workflow.

---

## 12. Open Questions

1. **"Credits":** the original ask mentioned "usage credits of each provider." This doc interprets that as per-provider rates/usage and ships `cost_usd` only. If Vidbyte needs a platform credits conversion, that is a follow-up (likely platform-side), not SDK scope.
2. **Price verification:** exact rates for the 2026-generation default models must be pulled from official pricing pages during implementation; anything unverifiable is omitted rather than guessed. Acceptable?
3. **`CostBudgetMiddleware` relationship:** it prices with a caller-supplied single blended rate off cumulative `tokens_used`. This doc leaves it untouched; a future PR could rewire it to `UsageRollup.cost_usd` for per-model-accurate budgets. Confirm no rewiring expected now.
4. **Aggregate-agent usage granularity:** multi-model runs expose one merged rollup via delegation; per-proposer legs remain visible in `UsageRollup.calls[].provider/model`. Sufficient for v1?

---

## 13. Alternatives Considered

1. **Type `TextModelResponse.usage` as `ProviderUsage` and parse inside each provider adapter.** Rejected: `vidbyte/lib/runners/types.py` importing `vidbyte.agents.pricing` creates a lib→agents dependency (and a real import cycle through `vidbyte/agents/__init__.py` → `base.py` → `runtime.py` → `lib.dataclasses.middleware`). Parsing at the runtime boundary achieves the same centralization with zero adapter churn. The OpenRouter payload change is the single justified adapter touch.
2. **One normalized usage dataclass for all providers.** Rejected: cache-token billing semantics differ (subset vs additive buckets; separate reasoning buckets), so a single shape either loses money-relevant detail or grows per-provider optional fields until it is a per-provider class anyway. The ABC exposes only the uniform surface (`input/output/total/cost_usd`) the rollup needs.
3. **Caller-supplied prices only (PR-282 sessions convention).** Rejected as the sole mechanism — the user asked for a built-in source-of-truth table — but supported via `ModelPricingRegistry.register()` overrides so both conventions coexist.
4. **Ship a `UsageTrackingMiddleware` builtin instead of agent functions.** Rejected: the user wants functions on the agent class for mid-run and after-run access; `agent.get_usage()`/`get_cost_usd()` cover the agent surface, while `MiddlewareContext.model_usage` lets any user-supplied middleware react per call — no bespoke callback param on the agent.
5. **Put `UsageRecord`/`UsageRollup` in `vidbyte/lib/dataclasses/`.** Rejected: they reference `ProviderUsage` (agents layer); keeping them in `vidbyte/agents/pricing/records.py` preserves the lib/agents dependency direction.
