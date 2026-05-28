# Context Protocol Header

## Description
This design document defines the architecture, requirements, and testing plan for the Multi-Provider Agentic Grader context-window algorithm.

## Purpose
It provides a formal specification of the ensemble algorithm that runs queries concurrently across multiple model providers, executes an agentic loop for each, and grades their candidate outputs using a meta-grader agent to select the absolute best response.

## Architecture
- Public algorithm configuration: `vidbyte.context.algorithms.multi_provider_agentic_grader`
- Agent preset registration: `vidbyte.context.presets`
- Runtime dispatching integration: `vidbyte.agents.context_algorithms`
- Orchestration and concurrent loops: `vidbyte.agents.algorithms.multi_provider_agentic_grader`
- Static prompt catalog assets: `vidbyte.prompts.prompts.multi_provider_agentic_grader.json`

## Relations
- Closely related to the `Reflexion` algorithm implementation (`vidbyte/context/algorithms/reflexion.py`, `vidbyte/agents/algorithms/reflexion.py`).

---

# Design Doc: Multi-Provider Agentic Grader Algorithm

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

The Multi-Provider Agentic Grader algorithm is an ensemble context-window algorithm designed to maximize correctness and response quality. It executes user requests concurrently through all available (or explicitly configured) model providers in the Vidbyte SDK, running each request through an independent agentic-loop. Finally, it aggregates all generated candidate outputs and routes them to a specialized meta-grader agent, which evaluates the outputs against the original request and selects the best candidate, returning it verbatim to the caller.

---

## 2. Goals & Non-Goals

### Goals
- Add the `multi_provider_agentic_grader` preset to `ContextWindow.preset` namespace.
- Support configurable lists or mappings of providers and their models, while defaulting to the best known models for all 7 supported providers.
- Run the agentic loop (`_arun_once`) concurrently for each participating provider using asynchronous execution.
- Only run providers for which API keys are available in the runtime environment (or explicitly supplied), avoiding crashes when some keys are missing.
- Grade candidate outputs using a dedicated grader model (defaulting to the best OpenAI model `gpt-4o` or original runner provider/model) and return the chosen output verbatim.
- Add structured execution metadata including candidate details, grading decisions, and token consumption to the final `StrategyResult` object.
- Externalize all static prompt texts to a prompt catalog JSON file (`vidbyte/prompts/prompts/multi_provider_agentic_grader.json`) and synchronize them with the `Prompt` enum.
- Achieve 100% test coverage with robust unit tests validating single-provider execution, multi-provider routing, grading decisions, edge cases, and failure modes.

### Non-Goals
- Changing the generic runtime orchestration in `AgentRuntime` or bypassing middleware pipelines.
- Persisting candidate outputs or grader evaluations across multiple agent sessions.
- Adding arbitrary external model providers not currently supported by `ModelProvider`.

---

## 3. Background & Context

In complex reasoning tasks, different model families exhibit different reasoning capabilities, biases, and prompt sensitivities. Unifying multiple provider networks via an ensemble grader strategy significantly elevates response reliability.
By leveraging the context-window algorithm lifecycle architecture established during the Reflexion refactor, we can implement this robust agentic ensemble pattern entirely outside the core `AgentRuntime` loop, preserving all existing middleware, security policies, and token tracing.

---

## 4. Requirements

### Functional Requirements

1. `ContextWindow.preset.multi_provider_agentic_grader` must return the default preset algorithm configuration.
2. `ContextWindow.resolve_algorithm("multi_provider_agentic_grader")` must resolve the preset.
3. Users must be able to instantiate `MultiProviderAgenticGraderAlgorithm` with custom provider/model dictionary mappings.
4. The algorithm must automatically default to the following provider model mapping:
   - `openai`: `gpt-4o`
   - `anthropic`: `claude-3-5-sonnet-latest`
   - `gemini`: `gemini-1.5-pro`
   - `xai`: `grok-beta`
   - `deepseek`: `deepseek-chat`
   - `glm`: `glm-4`
   - `minimax`: `abab6.5-chat`
5. When running in default mode, the algorithm must dynamically skip any provider for which the corresponding API key environment variable is not defined, running only on available providers.
6. If the user explicitly passes custom providers and any of them is missing an API key, a `ConfigurationError` must be raised.
7. If no provider has a valid API key, the execution must raise a `ConfigurationError`.
8. The agentic loops for each provider must run concurrently using `asyncio.gather`.
9. The meta-grader model must receive the original user request and all candidate outputs, selecting the best output verbatim using prompt catalog templates.
10. Final execution metadata must contain:
    - `grader_decision`: details of which provider's output was selected.
    - `candidates`: a dictionary of provider name to candidate output.
    - `total_runs`: count of successful provider loops executed.
11. Static grader prompts must be loaded through the `Prompts` catalog and enum.

### Non-Functional Requirements
- **Performance**: Agentic loops must run concurrently, meaning total latency is bounded by the slowest individual provider execution plus the single grader call.
- **Observability**: Complete tracking of token usage across all parallel calls and grading calls must be consolidated and returned in metadata.
- **Compatibility**: The algorithm must behave as a first-class context-window algorithm, maintaining total source compatibility with existing agents and tools.

---

## 5. High-Level Design

The algorithm utilizes the Reflexion-style plugin-based runtime architecture:

1. **`MultiProviderAgenticGraderAlgorithm`** (`vidbyte/context/algorithms/multi_provider_agentic_grader.py`): Immutable public configuration class, specifying models, keys, templates, and limits.
2. **`MultiProviderAgenticGraderRuntimeAlgorithm`** (`vidbyte/agents/algorithms/multi_provider_agentic_grader.py`): Concrete runtime adapter executing the parallel runner instantiation, `_arun_once` invocations, and grader-stage model calls.
3. **`AgentRuntimeContextAlgorithms`** (`vidbyte/agents/context_algorithms.py`): Dispatches requests to the grader algorithm if configured.

```text
[BaseAgent.arun(message)]
          |
          v
[AgentRuntime.arun] -> [AgentRuntimeContextAlgorithms]
          |
          +---> [MultiProviderAgenticGraderRuntimeAlgorithm]
                    |
                    +--- (Concurrently for each active provider)
                    |     [ModalityDetector.create_runner]
                    |     [runtime._arun_once] -> Candidate Output
                    |
                    v
         [Meta-Grader Model Call via _invoke_with_middleware]
                    |
                    v
          Selects Best Candidate Verbatim
                    |
                    v
         Returns StrategyResult + Consolidated Metadata
```

---

## 6. Detailed Design

### 6.1 Grader Public Algorithm

**File:** `vidbyte/context/algorithms/multi_provider_agentic_grader.py`
**Type:** New file

#### What it does
Provides the user-facing configuration options for the ensemble grader, defines default models, and renders prompts.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class MultiProviderAgenticGraderAlgorithm:
    provider_models: Mapping[str, str] | None = None
    grader_provider: str = "openai"
    grader_model: str = "gpt-4o"
    agent_system_prompt: str | None = None
    grader_system_prompt: str | None = None
    grader_prompt: str | None = None
    max_grader_chars: int = 15000
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

### 6.2 Grader Runtime Adapter

**File:** `vidbyte/agents/algorithms/multi_provider_agentic_grader.py`
**Type:** New file

#### What it does
Orchestrates the parallel execution across model providers and evaluates their answers via the grader agent.

#### Logic / Algorithm
1. Detect available providers by inspecting `provider_models` or environment variables:
   `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `DEEPSEEK_API_KEY`, `GLM_API_KEY`, `MINIMAX_API_KEY`.
2. Construct independent runners using `ModalityDetector.create_runner(...)`.
3. Wrap each execution in an async task that runs `runtime._arun_once(...)`.
4. Capture successful candidate text and usage metrics, catching individual runner errors safely.
5. If no candidates succeeded, raise `AgentExecutionError`.
6. Formulate the grading user prompt using candidate outputs and task request.
7. Execute the grading model stage using `runtime._invoke_with_middleware(...)` on the grader runner.
8. Parse the chosen response, returning the winner verbatim.

---

## 7. Data Model Changes

### 7.1 `ContextWindowAlgorithm`

**Change Type:** Modified in `vidbyte/context/algorithms/tool_results.py`

```python
multi_provider_agentic_grader: MultiProviderAgenticGraderAlgorithm | None = None
```

Preserves Reflexion and other fields. Rejects multiple active runtime algorithms.

---

## 8. API Changes

### 8.1 Python SDK Context Window Presets

Adds `multi_provider_agentic_grader` preset property:

```python
# ContextWindowPresets
@property
def multi_provider_agentic_grader(self) -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(
        name="multi_provider_agentic_grader",
        multi_provider_agentic_grader=MultiProviderAgenticGraderAlgorithm(),
    )
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/context/algorithms/multi_provider_agentic_grader.py` | Configuration dataclass for the algorithm |
| CREATE | `vidbyte/agents/algorithms/multi_provider_agentic_grader.py` | Runtime execution adapter |
| CREATE | `vidbyte/prompts/prompts/multi_provider_agentic_grader.json` | Grader prompts and descriptions |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add multi_provider_agentic_grader config field |
| MODIFY | `vidbyte/context/presets.py` | Register multi_provider_agentic_grader preset |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export public algorithm class |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export runtime algorithm adapter |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Wire dispatching logic for the grader |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Define grader prompt enum members |
| MODIFY | `vidbyte/context/__init__.py` | Re-export new public algorithm class |
| MODIFY | `vidbyte/__init__.py` | Add public exports |
| CREATE | `tests/test_multi_provider_agentic_grader.py` | Complete unit/integration test suite |

---

## 10. Testing Plan

All tests will be written in `tests/test_multi_provider_agentic_grader.py` using `unittest.IsolatedAsyncioTestCase` and the project's standard fake runners.

### Test Cases

- **[Edge Case]** Single provider configured: Ensure the algorithm runs successfully when only one provider is configured/available and returns the output properly.
- **[Edge Case]** Empty or blank response from all providers: Ensure the system throws an appropriate `AgentExecutionError` when no valid candidate responses are obtained.
- **[Hidden Failure]** Missing API key for explicitly requested provider: Ensure that a `ConfigurationError` is raised immediately if a provider is explicitly requested but has no configured API key.
- **[Hidden Failure]** Concurrency timeout or provider crash: If one provider crashes during the concurrent loops, verify that the other providers' candidates are still collected, graded, and evaluated successfully without crashing the entire run.
- **[Silent Failure]** Grader returns filler or explanation: If the grader model includes conversational filler in its grading output, verify that our parsing logic (or strict prompt design) successfully extracts the exact selected candidate output.
- **[Hidden Assumption]** Default execution with zero API keys: Verify that running the default configuration raises `ConfigurationError` when no API keys are present in the environment.

---

## 11. Dependencies & External Services

N/A - Uses existing standard libraries and SDK components.

---

## 12. Rollout & Deployment

- Non-breaking additive change.
- Rollback: Revert the PR commits.

---

## 13. Open Questions

None. The design leverages fully tested infrastructure models.

---

## 14. Alternatives Considered

### Alternative 1: Run loops sequentially
- Sequential runs are slow and highly inefficient for 7 providers. Concurrent execution is the optimal approach.

### Alternative 2: Build a custom grader class
- Reusing `_invoke_with_middleware` keeps prompt execution standardized, traces complete token usage, and automatically benefits from existing retries/logging.
