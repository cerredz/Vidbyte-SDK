# Design Doc: Agent Modality Routing

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

This feature moves text/image/video model-runner selection behind the public agent-facing SDK surface. Developers should create and run `BaseAgent` instances, or build harnesses that compose agents, instead of constructing `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner` in user-facing examples. `BaseAgent` will accept an explicit modality, support typed prompt inputs for reliable auto-detection, route execution to the correct runner internally, and keep the concrete runner classes available for SDK internals and advanced compatibility without presenting them as the primary API.

---

## 2. Goals & Non-Goals

### Goals

- Make `BaseAgent` the recommended public entry point for text, image, and video generation.
- Add an explicit model modality type for `"auto"`, `"text"`, `"image"`, and `"video"`.
- Allow `BaseAgent` to route direct runner execution and strategy execution to the correct modality runner.
- Support reliable auto-detection from typed agent inputs while defaulting ambiguous plain strings to text.
- Preserve existing explicit runner injection for tests, custom runners, and advanced users.
- Update README, SDK skill guidance, and relevant design docs so examples do not teach users to instantiate modality-specific runner classes directly.
- Keep current SDK verification style: Python 3.11, standard library `unittest`, fake runners/transports, no live provider calls.

### Non-Goals

- No removal of the concrete runner implementations from source.
- No deletion of compatibility imports that existing internal tests or advanced code may use.
- No natural-language intent classifier that guesses image/video modality from a plain text prompt.
- No new model provider, endpoint, billing, credential, or network transport behavior.
- No new persisted data, database schema, queue, or remote harness runtime.
- No full harness framework redesign; harness guidance will be documentation-level unless a minimal namespace factory is needed.

---

## 3. Background & Context

The local checkout is currently on `main` at `89e2404`, behind `origin/main` at `75bae16`. The current working tree also has untracked design docs that overlap files already present on `origin/main`; the required design-doc workflow may hit a `git pull` blocker after approval unless those untracked files are handled first.

`origin/main` already contains the larger SDK surface relevant to this change:

- `vidbyte/agents/base.py` defines `BaseAgent`, `ConfiguredAgentRunner`, direct runner execution, strategy execution, tool handling, MCP attach state, and `generate_reply()`.
- `vidbyte/lib/runners/text.py`, `image.py`, and `video.py` define the concrete modality-specific runner classes.
- `vidbyte/lib/config` and `vidbyte/lib/enums` define model configs and provider enums used by runner construction.
- `vidbyte/strategies` contains async-first strategies that receive a `runner` through `BaseAgent.generate_reply()`.
- `README.md` currently explains agents as actor objects but still leaves the model runner relationship abstract.
- `docs/design/prompt-api-strategies-sdk.md` and `docs/design/sdk-consolidated.md` currently describe runner classes as a visible SDK concept, including examples/import guidance.

The user request is to avoid exposing `TextModelRunner`, `ImageModelRunner`, and similar concrete runners in docs. The desired public surface is agent or harness oriented, with either an explicit modality type on the base agent class or automatic input-type detection inside the agent.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent.__init__()` must accept a modality option that defaults to `"auto"`.
2. `BaseAgent.generate_reply()` must accept a per-call modality override.
3. A typed agent input must carry both prompt text and modality so routing can be inferred without parsing natural language.
4. Plain `str` input must resolve to text when neither the call nor the agent has an explicit non-auto modality.
5. Direct agent execution without a strategy must route to the selected modality runner.
6. Agent execution with a strategy must pass the selected modality runner to `strategy.arun(..., runner=selected_runner, ...)`.
7. Existing explicit `runner=` injection must remain supported and must not require a modality-specific SDK runner.
8. Agents must support a runner mapping for callers/tests that want to provide different custom runners per modality.
9. Agents configured with provider/model primitives must instantiate the selected internal runner lazily when enough configuration exists.
10. Agent replies must preserve selected modality in metadata.
11. Agent cards must expose supported modalities as capability metadata without exposing concrete runner class names.
12. Runner output normalization must handle text responses, image responses, video job responses, simple strings, and custom objects.
13. `vidbyte.__all__` must not add `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner`.
14. README examples must use `BaseAgent` or SDK namespace clients, not direct runner construction.
15. SDK skill guidance must say runner classes are internal/advanced implementation details and public examples should start from agents or harnesses.
16. Existing tests on `origin/main` must continue to pass or be updated only when they assert the old public-doc expectation.

### Non-Functional Requirements

- Performance: modality resolution is constant-time and must not make network calls.
- Security: API keys remain in existing config paths; docs and tests must not introduce real secrets.
- Reliability: ambiguous string prompts must not be guessed as image/video from keywords.
- Observability: selected modality must be present in `AgentMessage.metadata`.
- Compatibility: preserve Python `>=3.11`, existing sync/async runner call handling, and existing `unittest` style.
- Maintainability: keep public package exports explicit with `__all__`.
- Testability: all new routing tests must use fake runners or fake transports, never live providers.

---

## 5. High-Level Design

The implementation adds a small modality-routing layer between `BaseAgent` and the existing concrete runners. Public callers configure an agent with `modality="text"`, `modality="image"`, `modality="video"`, or leave it as `"auto"`. For automatic routing, callers can pass a typed `AgentInput` object that includes modality; plain strings remain text by default because prompt content is not a reliable signal.

`BaseAgent` will hold either a single runner, a mapping of runners by modality, or primitive provider/model configuration. At execution time, it resolves modality from the per-call override, typed input, agent default, then final text fallback. It selects or creates a runner for that modality and passes it into direct execution or the configured strategy. Concrete runner classes stay under `vidbyte.lib.runners`; they are invoked by the router but not promoted in README examples.

```text
User code
  |
  v
BaseAgent(modality="image") or BaseAgent().generate_reply(AgentInput(..., modality="image"))
  |
  v
BaseAgent resolves modality
  |
  v
Internal runner router
  |-- text  -> TextModelRunner
  |-- image -> ImageModelRunner
  `-- video -> VideoModelRunner
  |
  v
Strategy or direct runner call
  |
  v
AgentMessage(content=..., metadata={"modality": ...})
```

The harness story remains intentionally conservative because `origin/main` has only a `HarnessClient` stub and its docs state custom harnesses stay outside the base SDK until public contracts are defined. This change will document that harnesses should compose `BaseAgent` rather than concrete runners. If a small factory is useful, it will be limited to namespace construction and will not introduce a new harness execution contract.

---

## 6. Detailed Design

### 6.1 Model Modality Enum

**File(s):** `vidbyte/lib/enums/model_modality.py`, `vidbyte/lib/enums/__init__.py`
**Type:** New file, Modified

#### What it does

Defines the stable modality vocabulary shared by agents, typed inputs, and runner routing.

#### Interface / API

```python
from enum import Enum


class ModelModality(str, Enum):
    AUTO = "auto"
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
```

#### Logic / Algorithm

1. Add a string enum matching existing enum style under `vidbyte/lib/enums`.
2. Re-export `ModelModality` from `vidbyte.lib.enums`.
3. Agent-facing modules import this enum instead of duplicating string literals.

#### Edge Cases & Error Handling

- Invalid modality strings raise `AgentExecutionError` through the agent/router coercion layer.
- `"auto"` is accepted only as an input preference; resolved execution modality is always concrete.

---

### 6.2 Agent Input Dataclass And Agent Config Fields

**File(s):** `vidbyte/lib/dataclasses/agents.py`, `vidbyte/agents/types.py`
**Type:** Modified

#### What it does

Adds typed agent input and modality fields to existing agent dataclasses so callers can opt into reliable auto-detection without direct runner imports.

#### Interface / API

```python
from dataclasses import dataclass, field
from typing import Any, Mapping

from vidbyte.lib.enums import ModelModality


@dataclass(frozen=True, slots=True)
class AgentInput:
    prompt: str
    modality: ModelModality | str = ModelModality.AUTO
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    api_key: str | None = None
    provider: str | None = None
    model_name: str | None = None
    modality: ModelModality | str = ModelModality.AUTO
    temperature: float | None = None
    run_id: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentCard:
    ...
    modalities: tuple[ModelModality, ...] = ()
```

#### Logic / Algorithm

1. Add `AgentInput` with a `prompt`, `modality`, and metadata.
2. Add `provider` and `modality` to `AgentRunnerConfig`.
3. Add `modalities` to `AgentCard` with a default empty tuple to keep existing construction compatible.
4. Re-export `AgentInput` and `ModelModality` from `vidbyte/agents/types.py`.

#### Edge Cases & Error Handling

- `AgentInput.prompt` is not validated in the dataclass; `BaseAgent` rejects empty prompts where it currently rejects invalid execution.
- Existing code constructing `AgentCard` remains valid because new fields have defaults.

---

### 6.3 Internal Runner Router

**File(s):** `vidbyte/lib/runners/router.py`, `vidbyte/lib/runners/__init__.py`
**Type:** New file, Modified

#### What it does

Centralizes modality coercion, auto-resolution, and lazy creation of concrete runners. This keeps `BaseAgent` from importing all runner classes at module import time and keeps concrete runner classes out of public examples.

#### Interface / API

```python
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.enums import ModelModality, ModelProvider


def coerce_modality(value: ModelModality | str | None) -> ModelModality: ...

def resolve_modality(
    *,
    requested: ModelModality | str | None,
    input_modality: ModelModality | str | None,
    default: ModelModality | str | None,
) -> ModelModality: ...

def create_runner_for_modality(
    modality: ModelModality,
    *,
    provider: ModelProvider | str,
    model: str,
    transport: object | None = None,
    **options: Any,
) -> object: ...
```

#### Logic / Algorithm

1. `coerce_modality()` accepts enum values and known strings.
2. `resolve_modality()` chooses the first non-auto value from call override, typed input, and agent default.
3. If all values are missing or auto, return `ModelModality.TEXT`.
4. `create_runner_for_modality()` lazily imports `TextModelRunner`, `ImageModelRunner`, or `VideoModelRunner` based on resolved modality.
5. The router passes provider/model/config options into the existing runner constructors.
6. `vidbyte/lib/runners/__init__.py` may export router helpers but must not add runner classes to top-level `vidbyte.__all__`.

#### Edge Cases & Error Handling

- Unknown modalities raise `AgentExecutionError` or `ConfigurationError` with safe details.
- Missing provider/model for lazy construction raises `AgentExecutionError` explaining that an executable runner or provider/model config is required.
- Direct `vidbyte.lib.runners.TextModelRunner` compatibility can remain, but user docs should not use it.

---

### 6.4 BaseAgent Modality Routing

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Extends `BaseAgent` so it resolves modality per call, selects an executable runner for that modality, and normalizes runner output into `AgentMessage` content plus metadata.

#### Interface / API

```python
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.agents.types import AgentInput
from vidbyte.lib.enums import ModelModality, ModelProvider


class BaseAgent:
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        strategy: BaseStrategy | None = None,
        runner: object | None = None,
        runners: Mapping[ModelModality | str, object] | None = None,
        modality: ModelModality | str = ModelModality.AUTO,
        provider: ModelProvider | str | None = None,
        ...
    ) -> None: ...

    async def generate_reply(
        self,
        message: str | AgentInput,
        *,
        modality: ModelModality | str | None = None,
        ...
    ) -> AgentMessage: ...

    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage: ...
    def run(self, message: str | AgentInput, **options: Any) -> AgentMessage: ...
```

#### Logic / Algorithm

1. Preserve all existing constructor arguments and behavior.
2. Store `self.modality` as the agent default.
3. Store `self.runners` as an instance-local modality-to-runner mapping.
4. Add `provider` to `AgentRunnerConfig`; if a concrete single `runner` is provided, preserve current behavior.
5. During `generate_reply()`:
   1. Extract prompt and input metadata from `AgentInput`, otherwise use the string as prompt.
   2. Resolve modality from call override, input modality, agent default, then text fallback.
   3. Select a runner:
      - If a runner exists in `self.runners[modality]`, use it.
      - Else if `self.runner` is executable and no modality-specific mapping exists, use it.
      - Else if provider/model config exists, create and cache an internal runner for the resolved modality.
      - Else keep existing failure behavior for strategy-less agents.
   4. Build agent context using the extracted prompt.
   5. If a strategy exists, call it with `runner=selected_runner`.
   6. If no strategy exists, call the selected runner directly.
   7. Normalize output and include `modality` in reply metadata.
6. `arun()` and `run()` are convenience aliases around `generate_reply()` for docs ergonomics.
7. `fork()` preserves modality, provider, and runner mapping unless explicitly overridden.
8. `card()` includes supported modalities from explicit mapping and agent default.

#### Edge Cases & Error Handling

- Empty agent names and missing system prompts continue to raise `AgentExecutionError`.
- Plain string prompts do not trigger image/video inference from prompt text.
- If strategy code requires a text runner but the caller forces image modality, the strategy error is wrapped by existing `AgentExecutionError` behavior.
- If both `runner` and `runners` are supplied, modality-specific mapping wins for matching modalities; single `runner` remains fallback.
- Async and sync custom runners preserve existing inspect-awaitable behavior.
- Image responses with URLs return newline-joined URLs as message content and store response metadata.
- Image responses with base64 but no URL return a concise placeholder content and store the response object/metadata rather than dumping large base64 into content.
- Video job responses return a concise job/status string and include job metadata.

---

### 6.5 Agent Namespace Client

**File(s):** `vidbyte/agents/client.py`, `vidbyte/agents/__init__.py`, `vidbyte/client.py`, `vidbyte/__init__.py`
**Type:** New file, Modified

#### What it does

Adds a small namespace factory so examples can use `sdk.agents.base(...)` instead of direct runner imports.

#### Interface / API

```python
from typing import Any

from vidbyte.agents.base import BaseAgent


class AgentClient:
    def base(self, **kwargs: Any) -> BaseAgent:
        return BaseAgent(**kwargs)
```

#### Logic / Algorithm

1. Add `AgentClient` under `vidbyte/agents/client.py`.
2. Mount `self.agents = AgentClient()` in `VidbyteSDK.__init__()`.
3. Re-export `AgentClient`, `AgentInput`, and `ModelModality` from `vidbyte.agents`.
4. Re-export `AgentClient`, `AgentInput`, and `ModelModality` from `vidbyte.__init__`.
5. Do not re-export concrete runner classes from `vidbyte.__init__`.

#### Edge Cases & Error Handling

- `AgentClient.base()` intentionally delegates validation to `BaseAgent`.
- Existing `VidbyteSDK().harnesses`, `.tools`, `.providers`, and `.strategies` remain unchanged.

---

### 6.6 Documentation And Prior Design Notes

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`, `docs/design/prompt-api-strategies-sdk.md`, `docs/design/multi-agent-orchestration-strategies.md`, `docs/design/sdk-consolidated.md`
**Type:** Modified

#### What it does

Updates public guidance to teach agents/harness composition first and treat concrete runners as internal implementation details. Existing design notes are updated where they currently present runner classes as a public recommended API.

#### Interface / API

```python
from vidbyte import ModelModality, VidbyteSDK

sdk = VidbyteSDK()

image_agent = sdk.agents.base(
    name="image-generator",
    system_prompt="Create useful image assets.",
    provider="openai",
    model_name="gpt-image-1",
    modality=ModelModality.IMAGE,
)

reply = image_agent.run("A clean product mockup on a white desk")
```

#### Logic / Algorithm

1. README adds a compact "Agents and Modalities" section.
2. README examples avoid direct `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner` construction.
3. SDK skill rules state that user-facing docs should prefer `BaseAgent` or harnesses and keep runners under `vidbyte.lib.runners` as internal/advanced details.
4. Existing design docs are adjusted to say strategies may use a runner supplied by `BaseAgent`; user examples should not start from concrete runners.

#### Edge Cases & Error Handling

- Documentation examples must not include real API keys.
- Previous architecture notes may still mention concrete runner class names when describing internals, but they must not present those classes as the preferred user entry point.

---

### 6.7 Tests

**File(s):** `tests/test_agent_modality_routing.py`, existing agent/runner tests as needed
**Type:** New file, Modified

#### What it does

Adds coverage for explicit modality routing, typed input routing, text fallback, strategy runner injection, metadata, and public export boundaries.

#### Interface / API

```python
class AgentModalityRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_agent_modality_routes_to_image_runner(self) -> None: ...
    async def test_typed_input_modality_routes_without_prompt_guessing(self) -> None: ...
    async def test_plain_string_defaults_to_text_runner(self) -> None: ...
    async def test_strategy_receives_selected_runner(self) -> None: ...
    def test_runner_classes_are_not_top_level_exports(self) -> None: ...
```

#### Logic / Algorithm

1. Use fake runners that record prompt/system/options and return simple fake response objects.
2. Use a fake strategy that records the runner object passed by `BaseAgent`.
3. Assert reply metadata includes concrete modality.
4. Assert `vidbyte.__all__` does not contain concrete runner class names.
5. Keep existing runner tests that import from `vidbyte.lib.runners` unless the approved implementation intentionally updates those imports.

#### Edge Cases & Error Handling

- No test may perform a live provider network call.
- Tests should not rely on unbounded object string representations for image/video response assertions.

---

## 7. Data Model Changes

### 7.1 `ModelModality`

**Change type:** New

```python
class ModelModality(str, Enum):
    AUTO = "auto"
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
```

**Migration strategy:** N/A - no persisted data or database schema.

- Forward migration: import and use the enum for agent modality settings.
- Rollback plan: remove enum exports and return to string-only options.

### 7.2 `AgentInput`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class AgentInput:
    prompt: str
    modality: ModelModality | str = ModelModality.AUTO
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: callers may pass `AgentInput` to `BaseAgent.generate_reply()`, `.arun()`, or `.run()`.
- Rollback plan: callers return to plain string prompts plus explicit `modality=`.

### 7.3 `AgentRunnerConfig`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentRunnerConfig:
    api_key: str | None = None
    provider: str | None = None
    model_name: str | None = None
    modality: ModelModality | str = ModelModality.AUTO
    temperature: float | None = None
    run_id: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: existing fields keep defaults; new fields are optional.
- Rollback plan: remove new fields if agent-level construction is reverted.

### 7.4 `AgentCard`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentCard:
    ...
    modalities: tuple[ModelModality, ...] = ()
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: existing card construction remains compatible because the new field has a default.
- Rollback plan: remove the field and keep modality in metadata only.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints. It adds Python package APIs only.

### 8.1 Python SDK API: `BaseAgent`

**Change type:** Modified

**Request:**

```python
agent = BaseAgent(
    name="asset-agent",
    system_prompt="Generate product assets.",
    provider="openai",
    model_name="gpt-image-1",
    modality="image",
)

reply = await agent.arun("A clean product mockup")
```

**Response:**

```python
AgentMessage(
    sender="asset-agent",
    recipient="orchestrator",
    content="...",
    metadata={"strategy": "direct_runner", "modality": "image", ...},
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid modality raises `AgentExecutionError`. |
| N/A | Missing executable runner/provider/model for direct execution raises `AgentExecutionError`. |
| N/A | Provider/config validation errors propagate through existing SDK exceptions. |

### 8.2 Python SDK API: `AgentClient`

**Change type:** New

**Request:**

```python
sdk = VidbyteSDK()
agent = sdk.agents.base(name="writer", system_prompt="Write clearly.", modality="text")
```

**Response:**

```python
BaseAgent(...)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Construction validation remains in `BaseAgent`. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-modality-routing.md` | Design doc for this feature |
| CREATE | `vidbyte/lib/enums/model_modality.py` | Stable text/image/video/auto modality enum |
| CREATE | `vidbyte/lib/runners/router.py` | Internal modality resolution and runner factory |
| CREATE | `vidbyte/agents/client.py` | Public SDK namespace factory for agents |
| CREATE | `tests/test_agent_modality_routing.py` | Focused routing and public export tests |
| MODIFY | `README.md` | Document agent-first modality usage and remove direct runner examples |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Add SDK structure guidance for agent-first runner routing |
| MODIFY | `docs/design/prompt-api-strategies-sdk.md` | Mark concrete runners as internal implementation details in design guidance |
| MODIFY | `docs/design/multi-agent-orchestration-strategies.md` | Update agent design language for modality-aware runner routing |
| MODIFY | `docs/design/sdk-consolidated.md` | Update consolidated public import guidance away from direct runner classes |
| MODIFY | `vidbyte/__init__.py` | Export agent-facing modality/request/client types, not concrete runners |
| MODIFY | `vidbyte/agents/__init__.py` | Export `AgentClient`, `AgentInput`, and `ModelModality` |
| MODIFY | `vidbyte/agents/base.py` | Add modality routing, typed input support, runner selection, and run/arun aliases |
| MODIFY | `vidbyte/agents/types.py` | Re-export new agent input and modality contracts |
| MODIFY | `vidbyte/client.py` | Mount `sdk.agents` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentInput`, modality config fields, and card modalities |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Re-export `ModelModality` |
| MODIFY | `vidbyte/lib/runners/__init__.py` | Expose router helpers cautiously while keeping docs agent-first |
| MODIFY | `tests/test_agent_base.py` | Update existing expectations for modality metadata and preserved fork config if needed |
| MODIFY | `tests/test_text_model_runner.py` | Adjust imports only if runner package export behavior changes |
| MODIFY | `tests/test_image_video_runners.py` | Adjust imports only if runner package export behavior changes |

Summary: 5 files created, 16 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_agent_modality_routing.py` -> `test_explicit_agent_modality_routes_to_image_runner`: agent default `modality="image"` selects image fake runner.
- `tests/test_agent_modality_routing.py` -> `test_call_modality_override_wins`: per-call modality overrides agent default.
- `tests/test_agent_modality_routing.py` -> `test_typed_input_modality_routes_without_prompt_guessing`: `AgentInput(prompt=..., modality="video")` selects video fake runner.
- `tests/test_agent_modality_routing.py` -> `test_plain_string_defaults_to_text_runner`: plain strings with auto config select text fake runner.
- `tests/test_agent_modality_routing.py` -> `test_strategy_receives_selected_runner`: strategy path receives the modality-selected runner.
- `tests/test_agent_modality_routing.py` -> `test_reply_metadata_includes_modality`: replies include `"modality"` metadata.
- `tests/test_agent_modality_routing.py` -> `test_runner_classes_are_not_top_level_exports`: top-level `vidbyte.__all__` excludes concrete runner classes.
- `tests/test_agent_base.py` -> existing direct runner, fork, card, and strategy tests continue to pass with modality metadata/defaults.

### Integration Tests

- No live provider integration tests in CI.
- Existing fake transport runner tests continue to verify provider payload normalization.
- Agent routing tests with fake runners cover the in-process flow from public agent API to selected runner/strategy.

### Manual / QA Test Cases

1. Run `python -m compileall vidbyte`.
2. Run `python -m unittest discover -s tests`.
3. Run import smoke:

```bash
python -c "from vidbyte import VidbyteSDK, BaseAgent, ModelModality; sdk = VidbyteSDK(); print(type(sdk.agents).__name__, ModelModality.TEXT.value)"
```

4. Search docs for direct public runner examples:

```bash
rg "TextModelRunner\\(|ImageModelRunner\\(|VideoModelRunner\\(" README.md skills docs
```

Remaining matches should be internal architecture references, not recommended user examples.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | `>=3.11` | SDK runtime | Existing project requirement |
| setuptools | `>=68` | Package build backend | Existing project requirement |
| pydantic | `>=2,<3` | Existing tool validation dependency | No new use planned |
| OpenAI/Anthropic/Gemini/xAI provider endpoints | Existing SDK provider adapters | Used only when real configured runners are executed | No live calls in tests; docs must not include real secrets |

---

## 12. Rollout & Deployment

- No feature flags.
- This is intended to be backward-compatible for code that uses existing agents, strategies, custom runners, and runner tests.
- The preferred public examples change from concrete runner construction to agent construction.
- Existing advanced imports from `vidbyte.lib.runners` can remain for compatibility, but docs should stop promoting them.
- Deployment is a library merge only; no service rollout.
- Rollback procedure:
  1. Revert the modality enum/router/client changes.
  2. Restore previous README and skill guidance.
  3. Remove `tests/test_agent_modality_routing.py`.
  4. Keep concrete runner classes untouched.

---

## 13. Open Questions

- [ ] During Phase 3, should the untracked docs in the current working tree be removed/stashed by the user before `git pull origin main`, since the design-doc workflow requires pulling `main` and those files overlap `origin/main`?
- [ ] Should `sdk.harnesses` gain a small `agent(...)` factory, or should harness support remain documentation-only until a real harness execution contract exists?
- [ ] Should `vidbyte.lib.runners.__all__` remove concrete runner class names, or is README/skill documentation cleanup enough for the current compatibility target?
- [ ] Should image response content prefer URLs only and place base64 data exclusively in metadata to avoid huge `AgentMessage.content` payloads?
- [ ] Should model aliases per modality be supported in this PR, or should multi-modality agents use explicit `runners={...}` until a richer config object is designed?

---

## 14. Alternatives Considered

### Alternative 1: Remove Or Rename Runner Classes

- What: Delete or rename `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner` so they cannot be imported directly.
- Why rejected: Existing tests and internal strategy code rely on the classes. Removing them would create unnecessary churn and a larger breaking change than the user requested.

### Alternative 2: Guess Modality From Prompt Text

- What: Treat prompts such as "draw..." or "make a video..." as image/video requests.
- Why rejected: Plain strings are ambiguous and keyword guessing creates surprising behavior. Explicit modality and typed inputs are reliable; plain strings should default to text.

### Alternative 3: Put Routing In Every Strategy

- What: Require each strategy to inspect input and choose text/image/video runners itself.
- Why rejected: This duplicates routing logic across strategies and keeps runners visible in user-facing strategy examples. `BaseAgent` is the right composition boundary.

### Alternative 4: Make Harnesses The Only Public API

- What: Hide agents and expose only harness constructors.
- Why rejected: `origin/main` already has a concrete `BaseAgent` implementation, while harnesses are currently a namespace stub. Agents are the lowest-risk public surface for this change; harnesses can compose agents later.

### Alternative 5: Keep Docs As-Is And Only Add `modality=`

- What: Add a modality parameter but leave direct runner examples and public guidance unchanged.
- Why rejected: The explicit user request is about documentation and public mental model. The implementation must adjust docs so developers learn agent/harness-first usage.
