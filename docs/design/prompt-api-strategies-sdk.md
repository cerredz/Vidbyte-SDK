# Design Doc: Prompt/API Strategy SDK

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-19
**Last Updated:** 2026-05-19

---

## 1. Overview

Build the next Vidbyte SDK layer for model-provider execution, filesystem tools, and prompt/API-implementable reasoning strategies. The SDK will gain typed provider configs, semantic model runners for text/image/video calls, a minimal safe filesystem toolset, and a `strategies` root namespace whose first batch implements prompt-level strategies such as Chain-of-Thought, Step-Back, Chain-of-Draft, Skeleton-of-Thought, self-consistency, budget forcing, answer convergence, Plan-and-Execute, and paradigm routing through `TextModelRunner.run()`.

---

## 2. Goals & Non-Goals

### Goals

- Add typed SDK config classes under `vidbyte/lib/config`.
- Add semantic runners under `vidbyte/lib/runners`: `TextModelRunner`, `ImageModelRunner`, and `VideoModelRunner`.
- Fill `vidbyte/providers` with first-party HTTP adapters for OpenAI, Anthropic, Gemini, and xAI, using official API docs as the source of truth.
- Keep provider credentials explicit and environment-resolvable without hardcoding secrets.
- Add a minimal, root-scoped filesystem tool subset under `vidbyte/tools/filesystem`.
- Add a new `vidbyte/strategies` root category and wire `StrategyClient` into `VidbyteSDK`.
- Implement the first prompt/API strategy batch sequentially:
  - Chain of Thought / test-time compute prompt wrapper
  - Step-Back Prompting
  - Chain of Draft
  - Skeleton of Thought
  - Self-Consistency / Best-of-N
  - Budget Forcing
  - Answer Convergence early stopping
  - Plan-and-Execute
  - Paradigm Routing
- Add tests using stdlib `unittest` and injected fake transports/runners.
- Update `skills/vidbyte-sdk/SKILL.md`, `README.md`, and the Obsidian note `Vidbyte/product/prompt_engineering_strategies.md` with implementation explanations.

### Non-Goals

- No training-time strategies in this PR: STaR, RLVR, GRPO, PRM training, DSPy compilation over datasets, or fine-tuning loops.
- No latent/hidden-state communication: Interlat, C2C, COCONUT, Quiet-STaR, recurrent latent depth, or role-vector injection require model internals not available through normal APIs.
- No unsafe arbitrary code execution. CodeAct/ReCode will be documented as later work requiring sandbox design.
- No full RAG storage service, vector database, or persistent memory backend.
- No new runtime third-party dependencies. HTTP uses the Python standard library with an injectable transport.
- No real API calls in automated tests.

---

## 3. Background & Context

- The standalone SDK repo is `cerredz/Vidbyte-SDK`.
- PR #1 established the approved package layout: `vidbyte/` is the top-level Python package, namespace clients live under `vidbyte/harnesses`, `vidbyte/tools`, and `vidbyte/providers`, and internal helpers live under `vidbyte/lib`.
- The current SDK is intentionally minimal: `VidbyteSDK` exposes `harnesses`, `tools`, and `providers`; the rest is scaffold.
- The user wants prompt-engineering paradigms implemented through the SDK where possible, but sequentially in stages rather than as a single broad drop.
- Official provider docs reviewed for this design:
  - OpenAI Responses, image generation, and Sora video APIs.
  - Anthropic Messages API and tool-use behavior.
  - Gemini `generateContent` and function-calling APIs.
  - xAI Chat Completions, structured outputs, and image generation APIs.
- Research sources reviewed for this design include ReAct, Reflexion, Tree of Thoughts, Graph of Thoughts, self-consistency, Skeleton-of-Thought, Least-to-Most, Step-Back, Chain-of-Draft, Plan-and-Solve, CodeAct, TextGrad, DSPy, and Self-RAG.

Implementability classification:

| Category | Strategy Families | SDK Treatment |
|----------|-------------------|---------------|
| Prompt/API implementable now | CoT, Step-Back, Chain-of-Draft, Skeleton-of-Thought, Least-to-Most, contrastive prompting, self-consistency, budget forcing, answer convergence, Plan-and-Execute, ReAct-style loops, Reflexion-style critique, paradigm routing, expert persona routing | Implement as `BaseStrategy` subclasses that call `TextModelRunner.run()` |
| Prompt/API implementable later with tools/memory | ReAct with arbitrary tools, Agentic RAG, Self-RAG approximation, episodic/structured memory, sleep-time compute, self-notes, ACE playbooks, multi-agent debate, mixture-of-agents | Add after filesystem tools, retrievers, memory stores, and tool-loop safety contracts mature |
| Requires sandbox design | CodeAct, ReCode, Program-of-Thoughts with execution, dynamic tool creation | Do not execute code until a sandbox boundary is designed |
| Requires model internals or training | Latent communication, COCONUT, Quiet-STaR, role vectors, RLVR/STaR, PRMs, recurrent latent depth, activation steering | Document only; not implementable through public prompt/API calls |

---

## 4. Requirements

### Functional Requirements

1. `VidbyteSDK()` must expose `sdk.strategies` in addition to existing namespace clients.
2. `TextModelRunner` must accept a typed provider config and run prompts through OpenAI, Anthropic, Gemini, or xAI.
3. `TextModelRunner.run()` must return a normalized `TextModelResponse` containing provider, model, text, raw response, and optional usage metadata.
4. `ImageModelRunner` must support provider configs for providers with official image APIs in this implementation batch: OpenAI and xAI.
5. `VideoModelRunner` must support OpenAI Sora asynchronous job creation and expose job status fields without hiding async/polling behavior.
6. Provider configs must validate required parameters, including provider name, model, API key resolution, max token/output bounds, temperature bounds, and endpoint URL defaults.
7. Provider adapters must use injectable HTTP transport so tests can mock responses without network calls.
8. Filesystem tools must operate only inside an explicit root directory and must reject path traversal outside that root.
9. Strategy classes must call `TextModelRunner.run()` rather than direct provider APIs.
10. Each strategy must expose a stable `run(input, *, runner, **options)` API and return `StrategyResult`.
11. Skeleton-of-Thought must generate a skeleton first, then complete skeleton points through separate runner calls, allowing parallel execution with a configurable concurrency limit.
12. Self-Consistency must sample N candidate outputs and select a winner by normalized answer voting.
13. Budget Forcing must implement prompt-level continuation forcing through additional calls when the model appears to stop before the requested budget.
14. Answer Convergence must stop sampling when recent normalized answers converge.
15. Paradigm Routing must select a strategy from a registered set before solving, using either heuristic rules or a model-scored routing prompt.
16. README and SDK skill docs must explain the runner/provider/strategy architecture.
17. The Obsidian note `Vidbyte/product/prompt_engineering_strategies.md` must be updated after implementation with concise explanations of each implemented strategy.

### Non-Functional Requirements

- Security: no API keys or secrets may be committed or logged.
- Security: filesystem tools must default to read-only unless write methods are explicitly called with a scoped root.
- Reliability: provider errors must normalize into SDK exceptions with provider, status, and message.
- Maintainability: every package `__init__.py` must use explicit `__all__`.
- Compatibility: Python `>=3.11`, zero runtime dependencies, stdlib-only tests.
- Observability: normalized responses include raw provider metadata, but logs and `print()` helpers must avoid secrets.
- Performance: strategies that issue multiple calls must expose call count/concurrency/budget controls.
- Cost control: defaults must be conservative; high-fanout strategies require explicit `samples`, `branches`, or `max_calls`.

---

## 5. High-Level Design

The SDK will get three new layers. First, `vidbyte/lib/config` defines typed dataclass configs for provider/model execution. Second, `vidbyte/providers` contains provider-specific HTTP adapters. Third, `vidbyte/lib/runners` exposes semantic runners that hide provider-specific request shapes behind stable `run()` methods. Strategies depend on runners, not providers.

Filesystem tools live under `vidbyte/tools/filesystem` because tool usage is public SDK surface. They provide safe local primitives that future ReAct/CodeAct/RAG strategies can call through a small common tool protocol.

Strategies live under a new root namespace, `vidbyte/strategies`, and are grouped by category. This first implementation batch focuses on prompt/API strategies that do not require hidden model state, training, vector DBs, or arbitrary code execution. Later stages can add memory, agentic RAG, ReAct tool loops, CodeAct sandboxing, and graph/tree search once the base runner and tool contracts are stable.

```text
VidbyteSDK
|-- providers -> provider adapter discovery/helpers
|-- tools -> filesystem tools
`-- strategies -> StrategyClient
              `-- BaseStrategy subclasses
                         |
                         v
                  TextModelRunner.run()
                         |
                         v
              OpenAI / Anthropic / Gemini / xAI adapters
```

Sequential implementation stages inside this design:

1. Provider config, errors, HTTP transport, provider adapters, model runners.
2. Filesystem tool protocol and minimal safe filesystem tools.
3. Strategy framework and first reasoning/sampling/routing strategies.
4. Tests, README/skill documentation, and Obsidian implementation note.

---

## 6. Detailed Design

### 6.1 Config Layer

**File(s):** `vidbyte/lib/config/__init__.py`, `vidbyte/lib/config/base.py`, `vidbyte/lib/config/models.py`
**Type:** New file

#### What it does

Defines provider enums and validated dataclass configs for text, image, and video model runners.

#### Interface / API

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    XAI = "xai"

@dataclass(frozen=True, slots=True)
class TextModelConfig:
    provider: ModelProvider
    model: str
    api_key: str | None = None
    system: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    endpoint: str | None = None

    def validate(self) -> None: ...
    def resolved_api_key(self) -> str: ...
```

Similar configs will exist for `ImageModelConfig` and `VideoModelConfig`.

#### Logic / Algorithm

1. Validate enum provider and non-empty model name.
2. Resolve API key from explicit config first, then provider-specific environment variable.
3. Validate numeric bounds.
4. Choose default endpoint per provider if one is not supplied.

#### Edge Cases & Error Handling

- Missing API key raises `ConfigurationError`.
- Unsupported provider/runner pair raises `UnsupportedProviderError`.
- Invalid bounds raise `ConfigurationError`.

---

### 6.2 Errors

**File(s):** `vidbyte/lib/errors/__init__.py`, `vidbyte/lib/errors/base.py`
**Type:** Modified, New file

#### What it does

Creates typed SDK exceptions for config, provider, tool, and strategy failures.

#### Interface / API

```python
class VidbyteSdkError(Exception): ...
class ConfigurationError(VidbyteSdkError): ...
class ProviderRequestError(VidbyteSdkError): ...
class ToolExecutionError(VidbyteSdkError): ...
class StrategyExecutionError(VidbyteSdkError): ...
```

#### Logic / Algorithm

1. Store message and optional details on each exception.
2. Provider errors include provider, status code, and safe response excerpt.

#### Edge Cases & Error Handling

- Error details must not include API keys or request headers.

---

### 6.3 HTTP Transport

**File(s):** `vidbyte/lib/http.py`
**Type:** New file

#### What it does

Provides a small stdlib HTTP wrapper and a protocol-like interface for test injection.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str
    headers: Mapping[str, str]

class HttpTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
        timeout_seconds: float = 60.0,
    ) -> HttpResponse: ...
```

#### Logic / Algorithm

1. JSON-encode request body when present.
2. Use `urllib.request` for HTTPS calls.
3. Return status, body text, and response headers.
4. Convert network errors into `ProviderRequestError`.

#### Edge Cases & Error Handling

- Non-2xx statuses are returned to provider adapters, which produce provider-specific normalized errors.
- Timeouts surface as `ProviderRequestError`.

---

### 6.4 Provider Adapters

**File(s):** `vidbyte/providers/base.py`, `vidbyte/providers/openai.py`, `vidbyte/providers/anthropic.py`, `vidbyte/providers/gemini.py`, `vidbyte/providers/xai.py`, `vidbyte/providers/__init__.py`
**Type:** New file, Modified

#### What it does

Implements provider-specific request/response shapes while preserving a normalized runner-facing interface.

#### Interface / API

```python
class TextProviderAdapter:
    def run_text(self, *, config: TextModelConfig, prompt: str, transport: HttpTransport) -> TextModelResponse: ...

class OpenAIProvider(TextProviderAdapter): ...
class AnthropicProvider(TextProviderAdapter): ...
class GeminiProvider(TextProviderAdapter): ...
class XAIProvider(TextProviderAdapter): ...
```

#### Logic / Algorithm

Provider mapping:

- OpenAI text: `POST /v1/responses`, normalize `output_text` or message content.
- OpenAI image: `POST /v1/images/generations`, normalize returned image URLs/base64.
- OpenAI video: `POST /v1/videos`, plus status retrieval helper for async jobs.
- Anthropic text: `POST /v1/messages` with top-level `system`, `messages`, and `max_tokens`.
- Gemini text: `models.generateContent` REST endpoint shape with contents and generation config.
- xAI text: OpenAI-compatible `POST /v1/chat/completions`.
- xAI image: `POST /v1/images/generations`.

#### Edge Cases & Error Handling

- If a provider response lacks expected text/image/job fields, raise `ProviderRequestError`.
- If a capability is unsupported, raise `UnsupportedProviderError`.
- Streaming is not implemented in this batch.

---

### 6.5 Semantic Model Runners

**File(s):** `vidbyte/lib/runners/__init__.py`, `vidbyte/lib/runners/types.py`, `vidbyte/lib/runners/base.py`, `vidbyte/lib/runners/text.py`, `vidbyte/lib/runners/image.py`, `vidbyte/lib/runners/video.py`
**Type:** New file

#### What it does

Defines user-facing semantic classes for model execution. Strategies use these runners instead of provider APIs.

#### Interface / API

```python
class TextModelRunner:
    def __init__(self, config: TextModelConfig, *, transport: HttpTransport | None = None) -> None: ...
    def run(self, prompt: str, *, system: str | None = None, metadata: Mapping[str, object] | None = None) -> TextModelResponse: ...
    def model_name(self) -> str: ...
    def print(self, response: TextModelResponse) -> None: ...

class ImageModelRunner: ...
class VideoModelRunner: ...
```

#### Logic / Algorithm

1. Validate config on construction.
2. Select provider adapter from config provider.
3. Delegate request and response normalization to adapter.
4. Return normalized response objects.

#### Edge Cases & Error Handling

- Runner methods must not print raw secrets.
- `VideoModelRunner.run()` returns a job object rather than blocking until completion unless `wait=True` is explicitly added later.

---

### 6.6 Filesystem Tools

**File(s):** `vidbyte/tools/base.py`, `vidbyte/tools/filesystem/__init__.py`, `vidbyte/tools/filesystem/base.py`, `vidbyte/tools/filesystem/list_dir.py`, `vidbyte/tools/filesystem/read_text.py`, `vidbyte/tools/filesystem/write_text.py`, `vidbyte/tools/filesystem/make_dir.py`, `vidbyte/tools/__init__.py`
**Type:** New file, Modified

#### What it does

Adds a minimal root-scoped filesystem toolset that future agent-loop strategies can use.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class FileSystemToolConfig:
    root: Path
    allow_write: bool = False

class ReadTextTool:
    def run(self, path: str) -> str: ...

class WriteTextTool:
    def run(self, path: str, content: str) -> Path: ...
```

#### Logic / Algorithm

1. Resolve requested paths against configured root.
2. Reject traversal outside root.
3. Read/list/write/mkdir through pathlib.
4. Require `allow_write=True` for writes and mkdir.

#### Edge Cases & Error Handling

- Binary files are not supported in this batch.
- Delete/move operations are excluded from the first batch.
- Writes create parent directories only when explicitly requested by the tool config or method option.

---

### 6.7 Strategy Framework

**File(s):** `vidbyte/strategies/__init__.py`, `vidbyte/strategies/base.py`, `vidbyte/strategies/client.py`, `vidbyte/strategies/mixins.py`, `vidbyte/strategies/types.py`, `vidbyte/client.py`, `vidbyte/__init__.py`
**Type:** New file, Modified

#### What it does

Creates the root strategy category and a common API for all prompt/API strategies.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class StrategyResult:
    output: str
    strategy_name: str
    calls: tuple[TextModelResponse, ...]
    metadata: Mapping[str, object]

class BaseStrategy(ABC):
    name: ClassVar[str]
    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult: ...

class StrategyClient:
    def chain_of_thought(self) -> ChainOfThoughtStrategy: ...
    def step_back(self) -> StepBackStrategy: ...
```

#### Logic / Algorithm

1. Strategies build prompts and call `runner.run()`.
2. Results preserve call history and metadata for inspection.
3. `StrategyMixin` lets future harness classes compose a strategy without inheriting from it.

#### Edge Cases & Error Handling

- Unknown strategy names raise `StrategyExecutionError`.
- Strategies enforce max call counts before making model calls.

---

### 6.8 Initial Strategy Batch

**File(s):** `vidbyte/strategies/reasoning/*.py`, `vidbyte/strategies/sampling/*.py`, `vidbyte/strategies/agent_loops/*.py`, `vidbyte/strategies/routing/*.py`
**Type:** New file

#### What it does

Implements the first set of prompt/API strategies.

#### Interface / API

```python
ChainOfThoughtStrategy().run(prompt, runner=runner)
StepBackStrategy().run(prompt, runner=runner)
ChainOfDraftStrategy(max_words_per_step=5).run(prompt, runner=runner)
SkeletonOfThoughtStrategy(max_workers=4).run(prompt, runner=runner)
SelfConsistencyStrategy(samples=5).run(prompt, runner=runner)
BudgetForcingStrategy(max_rounds=3).run(prompt, runner=runner)
AnswerConvergenceStrategy(max_samples=7, window=3).run(prompt, runner=runner)
PlanAndExecuteStrategy().run(prompt, runner=runner)
ParadigmRouterStrategy(strategies=[...]).run(prompt, runner=runner)
```

#### Logic / Algorithm

- Chain of Thought: asks for a private solution process and a final answer section. The strategy returns only the final response text the model provides; it does not expose hidden provider reasoning tokens.
- Step-Back: first asks for principles/abstractions, then solves the original prompt with those principles.
- Chain of Draft: constrains intermediate reasoning to terse draft steps before final answer.
- Skeleton-of-Thought: asks for a skeleton/outline, parses numbered points, completes each point through separate runner calls, then assembles.
- Self-Consistency: samples multiple answers, extracts normalized final answers, votes, and returns winner plus vote metadata.
- Budget Forcing: asks the model to continue checking/revising until a round budget or stop condition is met.
- Answer Convergence: runs repeated samples until recent normalized answers converge.
- Plan-and-Execute: generates a plan, then executes each step sequentially using runner calls.
- Paradigm Routing: scores prompt characteristics and selects one of the registered strategies before running it.

#### Edge Cases & Error Handling

- Skeleton parsing falls back to line splitting if numbering is inconsistent.
- Voting falls back to longest/common normalized answer when exact majority is absent.
- Router defaults to direct/CoT when confidence is low.
- All strategies cap total runner calls.

---

### 6.9 Documentation And Obsidian Note

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`, external Obsidian note `Vidbyte/product/prompt_engineering_strategies.md`
**Type:** Modified, Modified, External note update

#### What it does

Documents how to use runners, tools, and strategies, and records strategy implementation notes in Obsidian.

#### Interface / API

N/A - documentation and Obsidian note updates only.

#### Logic / Algorithm

1. README gets short install-free usage examples.
2. SDK skill gets structure rules for providers, runners, tools, and strategies.
3. Obsidian note gets a section per implemented strategy with:
   - source paper/doc
   - SDK class
   - key parameters
   - call pattern
   - limitations

#### Edge Cases & Error Handling

- Obsidian update uses Local REST API first and filesystem fallback.
- No API keys or raw secrets are written to Obsidian.

---

## 7. Data Model Changes

### 7.1 SDK Dataclasses

**Change type:** New

```python
TextModelConfig
ImageModelConfig
VideoModelConfig
TextModelResponse
ImageModelResponse
VideoModelJob
StrategyResult
FileSystemToolConfig
```

**Migration strategy:** N/A - no persisted data or database schema.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints. It adds Python package APIs only.

External API usage through provider adapters:

| Provider | API Surface | Purpose |
|----------|-------------|---------|
| OpenAI | Responses API, Images API, Videos API | Text, image, video runner support |
| Anthropic | Messages API | Text runner support |
| Gemini | `generateContent` API | Text runner support |
| xAI | Chat Completions, structured outputs, image generations | Text and image runner support |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/prompt-api-strategies-sdk.md` | Design doc for this feature |
| MODIFY | `README.md` | Document runners, filesystem tools, and strategies |
| MODIFY | `pyproject.toml` | Add optional test metadata if needed; keep zero runtime dependencies |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update SDK structure guidance |
| MODIFY | `vidbyte/__init__.py` | Export strategy and runner public types |
| MODIFY | `vidbyte/client.py` | Add `sdk.strategies` |
| MODIFY | `vidbyte/providers/__init__.py` | Export provider adapters |
| MODIFY | `vidbyte/tools/__init__.py` | Export filesystem tools |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export typed errors |
| CREATE | `vidbyte/lib/errors/base.py` | SDK exception hierarchy |
| CREATE | `vidbyte/lib/http.py` | Injectable HTTP transport |
| CREATE | `vidbyte/lib/config/__init__.py` | Config package exports |
| CREATE | `vidbyte/lib/config/base.py` | Provider enum and shared validation helpers |
| CREATE | `vidbyte/lib/config/models.py` | Text/image/video model config dataclasses |
| CREATE | `vidbyte/lib/runners/__init__.py` | Runner package exports |
| CREATE | `vidbyte/lib/runners/types.py` | Normalized response dataclasses |
| CREATE | `vidbyte/lib/runners/base.py` | Shared runner helpers |
| CREATE | `vidbyte/lib/runners/text.py` | `TextModelRunner` |
| CREATE | `vidbyte/lib/runners/image.py` | `ImageModelRunner` |
| CREATE | `vidbyte/lib/runners/video.py` | `VideoModelRunner` |
| CREATE | `vidbyte/providers/base.py` | Provider adapter interfaces |
| CREATE | `vidbyte/providers/openai.py` | OpenAI adapter |
| CREATE | `vidbyte/providers/anthropic.py` | Anthropic adapter |
| CREATE | `vidbyte/providers/gemini.py` | Gemini adapter |
| CREATE | `vidbyte/providers/xai.py` | xAI adapter |
| CREATE | `vidbyte/tools/base.py` | Shared tool protocol/types |
| CREATE | `vidbyte/tools/filesystem/__init__.py` | Filesystem tool exports |
| CREATE | `vidbyte/tools/filesystem/base.py` | Root-scoped filesystem config/path guard |
| CREATE | `vidbyte/tools/filesystem/list_dir.py` | Directory listing tool |
| CREATE | `vidbyte/tools/filesystem/read_text.py` | Text file read tool |
| CREATE | `vidbyte/tools/filesystem/write_text.py` | Text file write tool |
| CREATE | `vidbyte/tools/filesystem/make_dir.py` | Directory creation tool |
| CREATE | `vidbyte/strategies/__init__.py` | Strategy package exports |
| CREATE | `vidbyte/strategies/base.py` | `BaseStrategy` |
| CREATE | `vidbyte/strategies/client.py` | `StrategyClient` |
| CREATE | `vidbyte/strategies/mixins.py` | Harness composition mixin |
| CREATE | `vidbyte/strategies/types.py` | Strategy result/context types |
| CREATE | `vidbyte/strategies/reasoning/__init__.py` | Reasoning strategy exports |
| CREATE | `vidbyte/strategies/reasoning/chain_of_thought.py` | CoT strategy |
| CREATE | `vidbyte/strategies/reasoning/step_back.py` | Step-Back strategy |
| CREATE | `vidbyte/strategies/reasoning/chain_of_draft.py` | Chain-of-Draft strategy |
| CREATE | `vidbyte/strategies/reasoning/skeleton_of_thought.py` | Skeleton-of-Thought strategy |
| CREATE | `vidbyte/strategies/sampling/__init__.py` | Sampling strategy exports |
| CREATE | `vidbyte/strategies/sampling/self_consistency.py` | Self-consistency strategy |
| CREATE | `vidbyte/strategies/sampling/budget_forcing.py` | Budget forcing strategy |
| CREATE | `vidbyte/strategies/sampling/answer_convergence.py` | Answer convergence strategy |
| CREATE | `vidbyte/strategies/agent_loops/__init__.py` | Agent-loop strategy exports |
| CREATE | `vidbyte/strategies/agent_loops/plan_and_execute.py` | Plan-and-Execute strategy |
| CREATE | `vidbyte/strategies/routing/__init__.py` | Routing strategy exports |
| CREATE | `vidbyte/strategies/routing/paradigm_router.py` | Paradigm routing strategy |
| CREATE | `tests/test_config_validation.py` | Config validation tests |
| CREATE | `tests/test_text_model_runner.py` | Text runner and provider normalization tests |
| CREATE | `tests/test_image_video_runners.py` | Image/video runner tests |
| CREATE | `tests/test_filesystem_tools.py` | Filesystem path-safety tests |
| CREATE | `tests/test_reasoning_strategies.py` | Reasoning strategy prompt/call tests |
| CREATE | `tests/test_sampling_strategies.py` | Sampling strategy voting/convergence tests |
| CREATE | `tests/test_strategy_router.py` | Router selection tests |

Summary: 50 files created, 9 files modified, 0 files deleted.

External non-repo artifact:

| Action | Artifact | Reason |
|--------|----------|--------|
| UPDATE | `Vidbyte/product/prompt_engineering_strategies.md` in Obsidian | Explain each implemented strategy and its SDK class |

---

## 10. Testing Plan

### Unit Tests

- `test_config_validation.py` -> validates missing keys, bad bounds, endpoint defaults, and provider enum handling.
- `test_text_model_runner.py` -> verifies OpenAI, Anthropic, Gemini, and xAI request payloads and normalized text responses using fake transport.
- `test_image_video_runners.py` -> verifies OpenAI/xAI image response normalization and OpenAI video job normalization.
- `test_filesystem_tools.py` -> verifies read/list/write/mkdir inside root and rejects `..` traversal.
- `test_reasoning_strategies.py` -> verifies each reasoning strategy calls `TextModelRunner.run()` with expected staged prompts.
- `test_sampling_strategies.py` -> verifies self-consistency voting, budget call limits, and answer-convergence stopping.
- `test_strategy_router.py` -> verifies heuristic and model-scored router paths.

### Integration Tests

- N/A - no live provider integration tests in CI because they require credentials and spend money.
- Manual live-provider smoke commands will be documented but not required for automated verification.

### Manual / QA Test Cases

1. Create an OpenAI text config with `OPENAI_API_KEY`, run `TextModelRunner.run("Say OK")`, confirm normalized response.
2. Create an Anthropic text config with `ANTHROPIC_API_KEY`, run a short prompt, confirm normalized response.
3. Create a Gemini text config with `GEMINI_API_KEY`, run a short prompt, confirm normalized response.
4. Create an xAI text config with `XAI_API_KEY`, run a short prompt, confirm normalized response.
5. Use `ReadTextTool` with a temp root and confirm traversal outside the root fails.
6. Run `SkeletonOfThoughtStrategy` with a fake runner and confirm multiple completion calls are made.
7. Run `ParadigmRouterStrategy` with deterministic fake scores and confirm selected strategy executes.

Verification commands:

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.strategies).__name__)"
```

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | HTTP, dataclasses, tests, concurrency | Lower ergonomics than provider SDKs, but avoids runtime dependencies |
| OpenAI API | `/v1/responses`, `/v1/images/generations`, `/v1/videos` | Text, image, video runner support | API capability and model names change; keep endpoints/config explicit |
| Anthropic API | `/v1/messages` | Text runner support | Stateless history and top-level `system` differ from OpenAI |
| Gemini API | `generateContent` | Text runner support | Request shape differs from chat-completions style APIs |
| xAI API | `/v1/chat/completions`, `/v1/images/generations` | Text and image runner support | Docs and model availability change quickly |
| Obsidian Local REST API | `https://127.0.0.1:27124` | Update product note after implementation | Fallback to filesystem when Obsidian is closed |

Research references:

- ReAct: https://arxiv.org/abs/2210.03629
- Reflexion: https://arxiv.org/abs/2303.11366
- Tree of Thoughts: https://arxiv.org/abs/2305.10601
- Graph of Thoughts: https://arxiv.org/abs/2308.09687
- Self-Consistency: https://arxiv.org/abs/2203.11171
- Least-to-Most: https://arxiv.org/abs/2205.10625
- Step-Back Prompting: https://arxiv.org/abs/2310.06117
- Chain-of-Draft: https://arxiv.org/abs/2502.18600
- Plan-and-Solve: https://arxiv.org/abs/2305.04091
- CodeAct: https://arxiv.org/abs/2402.01030
- TextGrad: https://arxiv.org/abs/2406.07496
- DSPy: https://arxiv.org/abs/2310.03714
- Self-RAG: https://arxiv.org/abs/2310.11511

---

## 12. Rollout & Deployment

- This is a package-only SDK change; no deployed service is updated.
- This is a breaking SDK change relative to the initial `vidbyte_sdk` scaffold, but PR #1 already moved the package toward `vidbyte/`; this feature continues that approved direction.
- Rollout is a draft PR against `main` in `cerredz/Vidbyte-SDK`.
- Rollback is reverting the merge commit.
- Provider APIs are only called by users who instantiate runners with credentials.
- Live provider smoke tests should be opt-in and documented because they can spend money.

---

## 13. Open Questions

- [ ] Should the first strategy batch include ReAct/Reflexion now, or should those wait until tool-loop and memory contracts are stronger?
- [ ] Should `VideoModelRunner` include only OpenAI Sora initially, or should xAI/Gemini video adapters wait for confirmed official API docs in the implementation pass?
- [ ] Should runner config classes expose provider-specific subclasses such as `OpenAITextModelConfig`, or keep one generic `TextModelConfig` with provider enum plus validation helpers?
- [ ] Should filesystem write tools be included in the first batch, or should the minimal subset be read/list only?
- [ ] Should `TextModelRunner.print()` be named exactly `print()` per request, or should we prefer `print_response()` to avoid shadowing Python's builtin in examples?
- [ ] Should each strategy maintain its own source/research note file, or is the Obsidian product note enough?

---

## 14. Alternatives Considered

### Alternative 1: Implement all 40+ paradigms in one PR

- What: Add every listed prompt, memory, routing, agent, latent, and training paradigm at once.
- Why rejected: It would mix prompt wrappers, unsafe execution, memory infrastructure, training workflows, and non-public model internals into one unreviewable change. The user explicitly asked for sequential stages.

### Alternative 2: Use official provider SDK packages

- What: Depend on `openai`, `anthropic`, `google-genai`, and `xai-sdk`.
- Why rejected: The SDK currently has zero runtime dependencies. Stdlib HTTP plus injectable transport keeps the first implementation small and testable. Provider SDKs can be added later if ergonomics outweigh dependency cost.

### Alternative 3: Put strategies under `vidbyte/lib`

- What: Treat strategies as internal helpers.
- Why rejected: The user requested `strategies` as a root category alongside `harnesses`; strategies are public SDK behavior, not only internal implementation.

### Alternative 4: Implement CodeAct immediately

- What: Let the SDK execute generated Python code as part of a CodeAct strategy.
- Why rejected: Executable-code agents require a sandbox, resource limits, dependency policy, and security review. This design only prepares tool and strategy interfaces that can support CodeAct later.

### Alternative 5: Build memory and RAG first

- What: Prioritize episodic memory, structured memory, Self-RAG, and Agentic RAG.
- Why rejected: Those need persistence/retrieval abstractions that do not exist yet. Provider runners and strategy result types should land first.

---

END OF DESIGN DOC
