# Design Doc: Jev Agent Scaffold

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-21
**Last Updated:** 2026-09-21

---

## 1. Overview

This change introduces the first public scaffold for an opinionated Jev-backed agent. It adds the TypeSafe Jev provider and typed decision-model substrate, then adds a deliberately small `JevAgent` configured by one `JevAgentSettings` object and executed by a dedicated `JevRuntime`. The initial runtime behaves like the SDK's established linear model/tool loop and does not yet classify, route, coordinate multiple agents, allocate compute dynamically, or ask clarification questions. Its purpose is to establish the correct package boundaries and a narrow construction API before those named Jev capabilities are added.

---

## 2. Goals & Non-Goals

### Goals

- Add TypeSafe as a supported decision-model provider with typed configuration, request, answer, response, pricing, and runner contracts.
- Add an opinionated `vidbyte.agents.jev` package containing `JevAgent`, `JevRuntime`, and `JevAgentSettings`.
- Make `JevAgent` use the existing linear model/tool execution semantics through `JevRuntime`.
- Keep `JevAgent` construction settings-based and intentionally omit generic runtime, middleware, decision-list, and hook customization.
- Expose the agent through `vidbyte.agents`, the root `vidbyte` package, and `sdk.agents.jev(...)`.
- Add a contributor skill explaining the Jev agent's opinionated design constraints for future agents.
- Verify provider normalization, settings validation, runtime selection, ordinary linear execution, public exports, and credential-safe representations without live network calls.

### Non-Goals

- No clarity gate, preflight question collection, dynamic compute routing, tool narrowing, context filtering, completion gate, or multi-agent coordination.
- No generic `decisions=` parameter, public decision-point DSL, arbitrary Jev hooks, or user-defined Jev policies.
- No `jev_decide` model-callable tool; that remains a separate feature.
- No new runtime enum value. `JevRuntime` is a specialized linear runtime, not another selectable general runtime family.
- No hosted Vidbyte inference gateway or billing API.
- No declarative YAML construction for `JevAgent` in this first scaffold.
- No migration of existing `BaseAgent` callers.

---

## 3. Background & Context

The SDK currently has a mature direct `AgentRuntime` that owns the linear model/tool loop, and `BaseAgent._runtime()` constructs it through the runtime registry. Jev is a decision model rather than a text-generation model, so it cannot drive that loop. The correct architecture therefore keeps the ordinary text model as the generative engine and makes Jev an additional decision substrate used by future runtime capabilities.

An existing isolated branch contains a reviewed TypeSafe provider foundation in commit `9f659add`. This change reuses that provider/lib implementation but excludes its two tool-specific records (`JevDecideSettings` and `ToolModelCall`) because the `jev_decide` tool is outside this feature. The utility error for trying to use Jev as an agent-loop model will refer callers to `DecisionModelRunner`, which is present in this scope.

The repository's runtime boundary requires model usage accounting to remain agent-owned and run-local state to remain runtime-local. This scaffold does not yet execute Jev calls, so it adds no second usage tracker and no decision state. `JevRuntime` merely retains the validated Jev settings needed by later capabilities while delegating execution to `AgentRuntime` unchanged.

The canonical `main` checkout contains unrelated untracked design documents. The implementation uses an isolated worktree based on `origin/main` and leaves those files untouched.

---

## 4. Requirements

### Functional Requirements

1. `DecisionModelConfig` must default to TypeSafe's Jev model, validate its provider/model/timeout/retry shape at construction, and resolve credentials only when a `DecisionModelRunner` is built.
2. `JevDecisionRequest` must accept a non-empty state and one or more uniquely named, typed Jev questions.
3. The TypeSafe provider must serialize decision requests and normalize choice, score, and noul responses into typed `JevAnswer` records.
4. `DecisionModelRunner` must be the only lib runner entry point for decision models; a Jev model passed to the ordinary `Runner` must fail with a clear configuration error.
5. TypeSafe Jev usage must be represented and priceable through the existing pricing registry.
6. `JevAgentSettings` must require a non-blank name, system prompt, generative provider, and generative model name; it must own a `DecisionModelConfig`, tool tuple, permission policy, and `AgentLoopSettings`.
7. `JevAgentSettings` must reject TypeSafe as the generative provider because decision models cannot produce agent replies.
8. API keys must not appear in `JevAgentSettings` representations.
9. `JevAgent` must accept exactly one `JevAgentSettings` object and construct the established `BaseAgent` state with the linear runtime fixed internally.
10. `JevAgent` must not expose generic `runtime`, `middleware`, `algorithm`, `fallback`, or `decisions` constructor parameters.
11. `JevAgent._runtime()` must return a `JevRuntime`, and that runtime must retain the same `JevAgentSettings` instance.
12. `JevRuntime` must execute the same model/tool loop and preserve the same usage, speed, output-contract, session-middleware, and tracing wiring as the standard linear runtime.
13. Existing `BaseAgent` and other runtime types must continue resolving through the current registry with no behavior change.
14. `sdk.agents.jev(settings)` and direct package imports must construct the new agent.
15. The contributor skill must tell future agents to add named, opinionated Jev capabilities inside `vidbyte/agents/jev`, keep Jev from becoming the generative loop model, and avoid introducing a generic decisions collection.

### Non-Functional Requirements

- Provider HTTP execution remains asynchronous and uses the shared `HttpTransport`.
- No Jev API call occurs merely from importing modules, constructing settings, constructing an agent, or creating its runtime.
- Missing TypeSafe credentials fail when decision execution is requested, not during ordinary Jev agent construction.
- Decision request/response records are immutable and validate bounds before provider serialization.
- Provider credentials and raw secrets are never written to logs, result records, or object representations introduced here.
- The runtime extension must add no per-run global state and must remain safe for concurrent agents.
- All new Python modules must satisfy the repository's agent-readable headers, one-line signatures, method comments, directed dependency graph, and source/package gates.

---

## 5. High-Level Design

The provider layer adds a TypeSafe adapter beneath a semantic `DecisionModelRunner`. Shared lib records describe Jev questions, requests, answers, responses, model configuration, enums, constants, and provider pricing. These are independent of `JevAgent`; future tools and runtime capabilities can use the same runner without importing the agent layer.

The agent layer adds a small vertical package. `JevAgentSettings` is the sole public construction input. `JevAgent` maps those settings to `BaseAgent` while fixing execution to the linear runtime. `BaseAgent` gains two protected construction hooks: one chooses the runtime class and one contributes feature-specific runtime keyword arguments. Defaults preserve every current caller. `JevAgent` overrides the hooks to choose `JevRuntime` and pass its settings. `JevRuntime` subclasses `AgentRuntime`, stores the settings, and otherwise inherits the linear execution loop unchanged.

```text
JevAgentSettings
  |-- generative provider/model/tools/loop policy
  `-- DecisionModelConfig (TypeSafe Jev; unused until a capability is enabled)
              |
              v
          JevAgent
              |
              v
         JevRuntime ----------------> existing AgentRuntime model/tool loop
              |
              `-- future named Jev capabilities
                         |
                         v
                DecisionModelRunner -> TypeSafeProvider -> Jev API
```

The contributor skill records the product constraint: future public APIs expose scaffolded feature settings such as preflight, compute, or coordination. Internal Jev questions and policies can be added behind those features, but the public agent does not become a generic decision-rule engine.

---

## 6. Detailed Design

### 6.1 TypeSafe Provider and Decision Contracts

**File(s):** `vidbyte/providers/typesafe.py`, `vidbyte/providers/__init__.py`, `vidbyte/lib/config/models.py`, `vidbyte/lib/config/__init__.py`, `vidbyte/lib/constants/jev.py`, `vidbyte/lib/constants/runners.py`, `vidbyte/lib/constants/__init__.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/dataclasses/model_configs.py`, `vidbyte/lib/enums/jev.py`, `vidbyte/lib/enums/model_provider.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/registries/models.py`, `vidbyte/lib/runners/decision.py`, `vidbyte/lib/runners/types.py`, `vidbyte/lib/runners/utility.py`, `vidbyte/lib/runners/__init__.py`
**Type:** New files and modified files

#### What it does

Adds the reusable decision-model transport and typed Jev vocabulary. The lib layer owns validated data only; provider wire dictionaries remain in `typesafe.py` in accordance with lint rule S060.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class DecisionModelConfig:
    provider: ModelProvider | str = ModelProvider.TYPESAFE
    model: str = JEV_DEFAULT_MODEL
    api_key: str | None = None
    endpoint: str | None = None
    timeout_seconds: float = JEV_DEFAULT_TIMEOUT_SECONDS
    retry_count: int = JEV_DEFAULT_RETRY_COUNT

class DecisionModelRunner:
    def __init__(self, config: DecisionModelConfig | None = None, *, transport: HttpTransport | None = None) -> None: ...
    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse: ...
    def model_name(self) -> str: ...
```

#### Logic / Algorithm

1. Validate model/provider/retry/timeout shape at `DecisionModelConfig` construction.
2. Resolve the TypeSafe key and endpoint when `DecisionModelRunner` is constructed.
3. Serialize the immutable request in the provider adapter.
4. Post through the shared async transport.
5. Validate response shape and normalize each named answer.
6. Return a typed `DecisionModelResponse` with raw usage for accounting.

#### Edge Cases & Error Handling

- Blank state, duplicate question names, wrong option counts, non-probability values, or unsupported providers raise `ConfigurationError` before the request.
- Missing keys raise at runner construction so future opinionated capabilities can choose their explicit fail-open behavior.
- Malformed provider payloads raise `ProviderRequestError`; no partial answer is returned.
- Noul uses its probability directly and does not invent a confidence field.

### 6.2 TypeSafe Usage and Pricing

**File(s):** `vidbyte/agents/pricing/typesafe.py`, `vidbyte/agents/pricing/__init__.py`, `vidbyte/lib/registries/pricing.py`
**Type:** New file and modified files

#### What it does

Normalizes Jev input/output token usage and makes the provider's published rate available to the existing usage tracker.

#### Interface / API

```python
class JevUsage(ProviderUsage):
    @classmethod
    def from_raw(cls, usage: Mapping[str, Any]) -> JevUsage: ...
```

#### Logic / Algorithm

1. Read TypeSafe's input and output token counters.
2. Normalize missing counters to zero while preserving whether a response was priceable.
3. Resolve the model rate from `PROVIDER_PRICING`.

#### Edge Cases & Error Handling

- Boolean, negative, or malformed usage counts do not silently become valid billed usage.
- Unknown model versions remain unpriced rather than inheriting an incorrect rate.

### 6.3 Opinionated Jev Settings

**File(s):** `vidbyte/agents/jev/settings.py`
**Type:** New file

#### What it does

Defines the complete initial user configuration for `JevAgent`. It intentionally presents a narrow surface and does not forward arbitrary `BaseAgent` keywords.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class JevAgentSettings:
    name: str
    system_prompt: str
    provider: ModelProvider | str
    model_name: str
    api_key: str | None = field(default=None, repr=False)
    temperature: float | None = None
    timeout_seconds: float | None = None
    tools: tuple[object, ...] = ()
    permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)
    loop: AgentLoopSettings = field(default_factory=AgentLoopSettings)
    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig, repr=False)
```

#### Logic / Algorithm

1. Normalize the provider to `ModelProvider` once.
2. Freeze tool inputs to a tuple.
3. Validate non-blank identity and model fields.
4. Validate nested settings types.
5. Reject `ModelProvider.TYPESAFE` as the generative provider.

#### Edge Cases & Error Handling

- Empty names/prompts/models, strings passed as tool sequences, invalid temperatures/timeouts, and wrong nested objects raise `ConfigurationError` at settings construction.
- API keys are excluded from representations.
- An absent TypeSafe key does not prevent constructing settings because no Jev capability executes yet.

### 6.4 Jev Runtime

**File(s):** `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/base.py`
**Type:** New file and modified file

#### What it does

Creates a dedicated linear runtime seam for future opinionated Jev capabilities while preserving all current direct-runtime behavior.

#### Interface / API

```python
class JevRuntime(AgentRuntime):
    def __init__(self, *, jev_settings: JevAgentSettings, **kwargs: Any) -> None: ...

class BaseAgent:
    def _runtime_class(self) -> type: ...
    def _runtime_extension_kwargs(self) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. `BaseAgent._runtime()` asks `_runtime_class()` for the implementation and merges `_runtime_extension_kwargs()` into constructor arguments.
2. Default hooks resolve exactly the same class and no extension options.
3. `JevAgent` selects `JevRuntime` and passes `jev_settings`.
4. `JevRuntime` stores the immutable settings, then calls `AgentRuntime.__init__` unchanged.

#### Edge Cases & Error Handling

- Runtime extension keyword collisions are prevented by keeping the default empty and the Jev key unique.
- Existing non-linear runtimes never receive Jev settings.
- Jev runtime construction makes no provider call.

### 6.5 Jev Agent and Public Construction

**File(s):** `vidbyte/agents/jev/agent.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/jev/README.md`, `vidbyte/agents/client.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`
**Type:** New files and modified files

#### What it does

Exposes a settings-only `JevAgent` and adds direct and namespace-client imports.

#### Interface / API

```python
class JevAgent(BaseAgent):
    def __init__(self, settings: JevAgentSettings) -> None: ...

class AgentClient:
    def jev(self, settings: JevAgentSettings) -> JevAgent: ...
```

#### Logic / Algorithm

1. Require a `JevAgentSettings` instance.
2. Retain it as `agent.settings`.
3. Call `BaseAgent` with only the approved fields and a fixed linear runtime.
4. Override protected runtime hooks to return `JevRuntime` and supply settings.

#### Edge Cases & Error Handling

- Passing a mapping or arbitrary object instead of settings raises `ConfigurationError` before agent state is initialized.
- Users cannot select a non-linear runtime through this API.

### 6.6 Contributor Skill

**File(s):** `skills/jev-agent/SKILL.md`
**Type:** New file

#### What it does

Documents the non-obvious architecture and product constraints future coding agents must preserve.

#### Interface / API

```yaml
name: jev-agent
description: Extend or review the opinionated JevAgent runtime in vidbyte-sdk...
```

#### Logic / Algorithm

The skill routes future JevAgent changes to the correct files, distinguishes generative and decision models, and requires named capability settings rather than a generic decisions collection.

#### Edge Cases & Error Handling

- The skill does not contain private business strategy or provider credentials.
- It describes current scaffold behavior separately from future capability examples.

---

## 7. Data Model Changes

### 7.1 Jev Decision Records

**Change type:** New

```python
JevOption
JevQuestion
JevDecisionRequest
JevAnswer
JevDecisionRecord
DecisionModelResponse
JevAgentSettings
```

**Migration strategy:**

- Forward migration: additive Python types only; existing serialized data is unchanged.
- Rollback plan: remove the new exports and modules. No stored records require migration.

---

## 8. API Changes

N/A - This SDK change adds Python construction APIs and an outbound provider adapter; it does not add an HTTP server endpoint. The outbound TypeSafe request remains provider-internal and is covered in Section 6.1.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-agent-scaffold.md` | Source-of-truth design |
| CREATE | `vidbyte/agents/pricing/typesafe.py` | Normalize Jev usage |
| CREATE | `vidbyte/lib/constants/jev.py` | Jev limits, endpoint, and defaults |
| CREATE | `vidbyte/lib/dataclasses/jev.py` | Typed Jev request/answer records |
| CREATE | `vidbyte/lib/enums/jev.py` | Jev question-type enum |
| CREATE | `vidbyte/lib/runners/decision.py` | Semantic decision-model runner |
| CREATE | `vidbyte/providers/typesafe.py` | TypeSafe HTTP adapter |
| CREATE | `vidbyte/agents/jev/__init__.py` | Jev agent package exports |
| CREATE | `vidbyte/agents/jev/README.md` | Package intent and file map |
| CREATE | `vidbyte/agents/jev/agent.py` | Opinionated agent facade |
| CREATE | `vidbyte/agents/jev/runtime.py` | Specialized linear runtime seam |
| CREATE | `vidbyte/agents/jev/settings.py` | Settings-only public configuration |
| CREATE | `skills/jev-agent/SKILL.md` | Future-agent implementation guidance |
| CREATE | `tests/test_jev_agent.py` | Provider and agent tests |
| CREATE | `scripts/test-jev-agent-scaffold.py` | Required executable verification script |
| MODIFY | `vidbyte/agents/pricing/__init__.py` | Export Jev usage parser |
| MODIFY | `vidbyte/lib/config/__init__.py` | Export decision model config |
| MODIFY | `vidbyte/lib/config/models.py` | Export decision model config |
| MODIFY | `vidbyte/lib/constants/__init__.py` | Export Jev constants |
| MODIFY | `vidbyte/lib/constants/runners.py` | Catalog decision runner type and Jev model |
| MODIFY | `vidbyte/lib/dataclasses/model_configs.py` | Define validated decision model config |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export Jev enum |
| MODIFY | `vidbyte/lib/enums/model_provider.py` | Add TypeSafe provider identity |
| MODIFY | `vidbyte/lib/registries/models.py` | Register TypeSafe key, endpoint, and model |
| MODIFY | `vidbyte/lib/registries/pricing.py` | Register Jev pricing |
| MODIFY | `vidbyte/lib/runners/__init__.py` | Export decision runner and response |
| MODIFY | `vidbyte/lib/runners/types.py` | Define typed decision response |
| MODIFY | `vidbyte/lib/runners/utility.py` | Refuse decision models as generative runners |
| MODIFY | `vidbyte/providers/__init__.py` | Register and export TypeSafe provider |
| MODIFY | `vidbyte/agents/base.py` | Add protected runtime construction hooks |
| MODIFY | `vidbyte/agents/client.py` | Add `sdk.agents.jev` constructor |
| MODIFY | `vidbyte/agents/__init__.py` | Export Jev classes |
| MODIFY | `vidbyte/__init__.py` | Export Jev classes at package root |

No files will be deleted.

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] Construct `DecisionModelConfig` without a TypeSafe key and verify shape validation succeeds without resolving credentials.
- [Hidden Assumption] Construct `DecisionModelRunner` without a key and verify it fails before any HTTP call.
- [Edge Case] Reject an empty Jev state and duplicate question names.
- [Silent Failure] Normalize a valid TypeSafe choice response and verify every option probability is preserved under the correct question name.
- [Hidden Failure] Return a malformed provider answer and verify the adapter raises instead of producing an empty or partial answer.
- [Silent Failure] Verify Jev usage and pricing use input tokens and zero-cost output tokens without swapping fields.
- [Edge Case] Reject blank Jev agent names, prompts, and model names.
- [Hidden Assumption] Reject TypeSafe as the generative provider while accepting it in `settings.decision`.
- [Hidden Failure] Reject strings masquerading as a tool sequence and incorrect nested settings objects.
- [Silent Failure] Verify settings normalize the generative provider and never expose either API key in `repr(settings)`.
- [Silent Failure] Verify `JevAgent._runtime()` returns `JevRuntime`, carries the identical settings object, and retains agent-owned usage/speed trackers.
- [Hidden Assumption] Verify a normal `BaseAgent` still resolves the standard `AgentRuntime` rather than `JevRuntime`.
- [Edge Case] Run a no-tool response through a fake generative runner and verify `JevAgent` returns the ordinary final response.
- [Hidden Failure] Run one fake tool call followed by completion and verify `JevRuntime` preserves the standard tool loop.
- [Silent Failure] Verify direct imports and `sdk.agents.jev(settings)` return the expected public class.
- [Hidden Assumption] Inspect `JevAgent.__init__` and verify no `runtime`, `middleware`, `algorithm`, `fallback`, or `decisions` parameter exists.

### Integration Tests

- The verification script will load and run every case in `tests/test_jev_agent.py` against fake transports and fake generative runners.
- `python lint/run.py` will check architecture, imports, settings validation placement, and agent-readable source policy.
- `python scripts/run_ci.py --stage source` and `python scripts/run_ci.py` will verify the complete source and installed-package behavior.
- Live TypeSafe calls are excluded because CI must be deterministic and credential-free.

### Manual / QA Test Cases

1. Import `JevAgent`, `JevAgentSettings`, and `JevRuntime` from both `vidbyte` and `vidbyte.agents.jev`.
2. Build settings with a normal text provider and no `TYPESAFE_API_KEY`; confirm construction succeeds and its representation contains no credentials.
3. Build a `JevAgent`, call its runtime factory, and confirm the result is a `JevRuntime` configured with the same settings.
4. Confirm the contributor skill clearly states that the current runtime has no active Jev decisions yet.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| TypeSafe Jev | `POST https://api.typesafe.ai/v1/systemone` | Calibrated decision inference | Early service; schema, limits, pricing, or availability may change |
| Shared `HttpTransport` | Existing SDK implementation | Async authenticated request execution | Incorrect retry behavior could duplicate billable calls; the provider config uses the established transport policy |
| No new package dependency | N/A | Provider uses existing HTTP and dataclass infrastructure | N/A |

---

## 12. Rollout & Deployment

- This is an additive alpha SDK API with no feature flag.
- Existing agents are unaffected because protected runtime hook defaults reproduce current registry behavior.
- `JevAgent` can ship before active Jev capabilities because construction and ordinary generative execution do not require a TypeSafe key.
- Rollback consists of reverting the additive exports, provider/lib modules, runtime hooks, and Jev package. No migrations or remote cleanup are required.
- Later capability PRs must build on this scaffold and add their own design, policy, measurement, and fail-open tests.

---

## 13. Open Questions

- [ ] Which named capability should be first after the scaffold: preflight clarity or dynamic compute allocation? This does not affect the current implementation.
- [ ] Should a future `JevAgentSettings` revision group named capability settings under nested `preflight`, `compute`, and `coordination` objects, or expose a smaller fixed preset enum? This scaffold deliberately adds neither.
- [ ] Should decision-call usage ultimately roll into the same `UsageTracker` as generative calls or a separately visible decision rollup? No Jev call occurs in this version.

---

## 14. Alternatives Considered

### Alternative 1: Public `decisions=` Collection

- What: Let developers assemble arbitrary question/state/hook/action objects.
- Why rejected: It conflicts with the requested opinionated product direction, exposes runtime ordering prematurely, and turns the first scaffold into a generic rules framework.

### Alternative 2: Add `JEV` to `AgentRuntimeType`

- What: Register Jev as a fourth general runtime family.
- Why rejected: Jev cannot generate text and the execution loop remains linear. A new enum would incorrectly imply that all `BaseAgent` callers can select it and would duplicate every linear-runtime compatibility check.

### Alternative 3: Implement `JevAgent` as a Wrapper Around `BaseAgent`

- What: Store a private `BaseAgent` and delegate `run`/`arun` calls.
- Why rejected: The wrapper would have to proxy history, sessions, tools, usage, speed, MCP, handoffs, and future interfaces. Subclassing preserves the established agent contract.

### Alternative 4: Duplicate `BaseAgent._runtime()` Inside `JevAgent`

- What: Construct `JevRuntime` in an overridden copy of the existing factory.
- Why rejected: The copy would drift whenever usage, speed, fallback, tracing, output contracts, or session middleware changed. Two protected hooks preserve one constructor path.

### Alternative 5: Ship the Existing `jev_decide` Tool in This Change

- What: Bring the model-callable Jev tool and its usage bridge into the same PR.
- Why rejected: The user requested provider/lib setup and the initial Jev agent. A model-callable bolt-on tool is a separate surface and would bring unrelated runtime metering changes into this scaffold.
