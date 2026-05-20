# Design Doc: Agent Abstractions (Tools, Prompt Registry, Prompt Translations)

**Status:** Draft
**Author:** Antigravity
**Created:** 2026-05-20
**Last Updated:** 2026-05-20

---

## 1. Overview

This design outlines three core, interconnected developer-facing subsystems within the `vidbyte-sdk` to enable robust, customizable agent behaviors:
1. **Tools Abstraction**: A unified contract separating tool specifications, invocation validation, execution, and rendering. It features a clean `BaseTool` interface, a thread-safe `ToolRegistry`, a unified `ToolExecutor` that parses model action outputs, and a suite of built-in safe/mock tools (Calculator, Web Search, Code Execution, and Document Retrieval).
2. **Prompt Registry**: A centralized, versioned, and overridable prompt store. System and iteration prompts are formal versioned artifacts rather than hardcoded strings, allowing Vidbyte to ship prompt updates and developers to swap prompts seamlessly without subclassing.
3. **Prompt Translations**: Concrete `BasePrompt` subclasses that expose system and iteration prompts for strategies (ReAct, Tree of Thoughts, Reflexion, Self-Consistency, Step-Back) and harnesses (Conditional loop agent, stopping evaluator).

Additionally, this design provides the skeleton strategy and harness classes that tie these registries together under a clean client namespace interface.

---

## 2. Goals & Non-Goals

### Goals

- Implement a robust **Tools Abstraction** (`BaseTool`, `ToolRegistry`, `ToolExecutor`, `ToolSpec`, `ToolCall`, `ToolResult`) in `vidbyte/tools/`.
- Provide high-quality built-in tool implementations (`CalculatorTool`, `WebSearchTool`, `CodeExecutionTool`, `DocumentRetrievalTool`) inside `vidbyte/tools/builtins/`.
- Implement a thread-safe, singleton **Prompt Registry** (`BasePrompt`, `PromptRegistry`, `PromptKey`, `PromptVersion`, `RenderedPrompt`) in `vidbyte/prompts/`.
- Create comprehensive **Prompt Translations** under `vidbyte/prompts/translations/` for all major strategies and harnesses.
- Wire defaults using `vidbyte/prompts/builtins/vidbyte_defaults.py` to register all translations automatically upon initialization.
- Provide clean developer skeletons for **Strategies** and **Harnesses** that utilize the registries in `vidbyte/strategies/` and `vidbyte/harnesses/`.
- Properly expose all public API components through namespace package `__init__.py` files and standard `VidbyteSDK` fields.
- Strictly adhere to the **Context Protocol Header** for all created and modified source files.
- Establish a complete suite of unit tests verifying all registries, executors, parsing logic, and overrides using Python's standard `unittest`.

### Non-Goals

- Implementing real third-party credentials/access drivers (e.g., live Google API or live container environments for code execution) in the core SDK package. Built-in tools should be robust, safe simulation tools.
- Real runtime large language model network requests. Strategy/harness execution should interact with mock or modular runners rather than hardcoding HTTP integrations inside the agent loops.

---

## 3. Background & Context

Currently, the `vidbyte-sdk` is an empty namespace scaffold. The SDK client exposes empty namespace holders `tools` and `harnesses`, while the core agentic concepts (like ReAct, Tree of Thoughts, or Reflexion) are not yet formal architectural layers. 

System prompts are scattered across strategy types or hardcoded as inline strings. This prevents:
- Centralized tracking/versioning of model-facing instructions.
- Custom developer overrides (e.g., changing the ReAct system prompt to fit a specific domain without subclassing).
- Invisible prompt upgrades via public package updates.

Tools are also lacking a unified abstraction. Agent loops need a clean way to find, describe, and execute tools, while separating:
- **Spec**: What the model reads to learn the tool.
- **Executor**: How the SDK invokes it.
- **Formatter**: How results and observations return to the loop.

Solving these needs establishes the Vidbyte SDK as a premium, developer-first orchestration framework.

---

## 4. Requirements

### Functional Requirements

1. **BaseTool Contract**:
   - `BaseTool.spec()` must return a typed `ToolSpec`.
   - `BaseTool.execute(call)` must be an asynchronous method returning `ToolResult`.
   - `BaseTool.validate_call(call)` must return `None` if valid, or a descriptive validation error string if arguments are missing or malformed.
2. **Tool Specification Rendering**:
   - `ToolSpec.to_prompt_str()` must render parameter details as a clean, standardized format suitable for prompt injection.
3. **Tool Execution Parsing**:
   - `ToolExecutor` must parse action blocks matching standard `Action: <tool_name>` and `Action Input: <json_args>` formats.
   - It must validate tool availability and parameter requirements, and execute securely.
4. **Built-in Mocks**:
   - `CalculatorTool` must perform safe evaluation (avoiding arbitrary python built-ins).
   - `WebSearchTool`, `CodeExecutionTool`, and `DocumentRetrievalTool` must return clear, rich simulated results.
5. **Prompt Registry Singleton**:
   - `PromptRegistry` must be a thread-safe singleton.
   - Must support `register`, `override`, `get`, `get_raw`, and `list_all`.
   - Overrides must transparently take precedence over default registered prompts.
6. **BasePrompt and Variable Substitution**:
   - `BasePrompt` must specify `key()`, `version()`, `template()`, and `variables()`.
   - `render(**kwargs)` must validate variables; missing inputs must raise a clean `PromptRenderError`.
7. **Prompt Translations**:
   - Concrete `BasePrompt` subclasses must exist for ReAct, Tree of Thoughts, Reflexion, Self-Consistency, Step-Back, and Conditional Loop.
8. **Strategies & Harnesses Skeletons**:
   - The strategies and harnesses themselves must reside in `vidbyte/strategies/` and `vidbyte/harnesses/` and fetch prompts from the `PromptRegistry` and tools from `ToolRegistry`.
9. **Context Protocol Header**:
   - Every created or modified Python file must begin with a comprehensive Context Protocol Header detailing its Description, Purpose, Architecture/Key Functions, Codebase Relation, and Similar Files.

### Non-Functional Requirements

- **Zero External Runtime Dependencies**: Standard library Python 3.11+ only.
- **Thread Safety**: Registries must be safe under concurrent reads/writes (using standard threading Locks where appropriate).
- **Asynchronous Execution**: Tool execution and strategy wrappers must support async/await constructs natively.
- **Test Coverage**: Standard library `unittest` verification.

---

## 5. High-Level Design

The agent abstractions layer divides the SDK into three major conceptual packages: `tools`, `prompts`, and `strategies`/`harnesses`. 

```text
                               +------------------------------------+
                               |            VidbyteSDK              |
                               +-----------------+------------------+
                                                 |
         +---------------------------------------+---------------------------------------+
         |                                       |                                       |
         v                                       v                                       v
+------------------+                    +------------------+                   +------------------+
|    tools/        |                    |    prompts/      |                   |   strategies/    |
|                  |                    |                  |                   |        &         |
|  - BaseTool      |                    |  - BasePrompt    |                   |   harnesses/     |
|  - ToolRegistry  |                    |  - PromptRegistry|                   |                  |
|  - ToolExecutor  |                    |    (Singleton)   |                   | - Pulls tools    |
|  - Builtins      |                    |  - Translations  |                   |   from registry  |
|                  |                    |                  |                   | - Pulls prompts  |
|                  |                    |                  |                   |   from registry  |
+------------------+                    +------------------+                   +------------------+
```

### Components and Data Flows

1. **Strategy Initialization**:
   A strategy (e.g., `ReActStrategy`) is instantiated. It requests the shared `ToolRegistry` and grabs the default system prompts from the `PromptRegistry`.
2. **Prompt Retrieval**:
   The strategy calls `PromptRegistry.get(PromptKey("strategies.react", "system"), tools=tool_registry.specs_as_prompt_str())`.
3. **Execution Loop (ReAct)**:
   The model returns output containing a tool invocation block. The strategy feeds this output into `ToolExecutor.execute(model_output)`.
4. **Tool Parsing and Run**:
   - `ToolExecutor` extracts the `ToolCall(name, args)`.
   - Resolves the tool via `ToolRegistry`.
   - Validates arguments via `BaseTool.validate_call()`.
   - Asynchronously runs `BaseTool.execute()`.
   - Wraps the result into `ToolResult` and formats it as an observation string via `to_observation_str()`.
5. **Critique and Stopping Evaluation**:
   Conditional harnesses run stopping evaluation by retrieving the stopping evaluator prompt from the registry, prompting a judge model, and parsing the Halt JSON outcome.

---

## 6. Detailed Design

### 6.1 Tools Abstraction Core

**Files:**
- `vidbyte/tools/types.py` (New)
- `vidbyte/tools/base.py` (New)
- `vidbyte/tools/registry.py` (New)
- `vidbyte/tools/executor.py` (New)
- `vidbyte/tools/__init__.py` (Modified)
- `vidbyte/tools/client.py` (Modified)

#### Interface / API (types.py, base.py, registry.py, executor.py)

```python
# Types, Base, Registry, and Executor class signatures in vidbyte/tools
```

*Detailed implementation of these interfaces is given in the python classes in Section 6.1.*

#### Logic / Algorithm

1. `ToolRegistry` holds a dictionary of `BaseTool` instances. It supports registering tools, looking them up, and outputting formatted prompt strings for LLM injection.
2. `ToolExecutor` uses regex to look for `Action: <tool_name>` and `Action Input: <json_blob>`. It parses JSON arguments, resolves the tool, performs standard validation (comparing against required parameters in the spec), and executes async.

### 6.2 Built-in Tools

**Files:**
- `vidbyte/tools/builtins/__init__.py` (New)
- `vidbyte/tools/builtins/calculator.py` (New)
- `vidbyte/tools/builtins/web_search.py` (New)
- `vidbyte/tools/builtins/code_execution.py` (New)
- `vidbyte/tools/builtins/document_retrieval.py` (New)

#### What they do
- `CalculatorTool`: Parses a mathematical string and evaluates it inside a highly restricted sandboxed environment (using `eval` with empty builtins and local safe operators).
- `WebSearchTool`: Mocks a search interface returning detailed paragraphs for queries.
- `CodeExecutionTool`: Safely simulates running python code inside a mock runtime.
- `DocumentRetrievalTool`: Mocks document lookup across a fictional vector index.

### 6.3 Prompt Registry Core

**Files:**
- `vidbyte/prompts/types.py` (New)
- `vidbyte/prompts/base.py` (New)
- `vidbyte/prompts/registry.py` (New)
- `vidbyte/prompts/__init__.py` (New)

#### Interface / API (types.py, base.py, registry.py)

```python
# Dataclasses and Class interfaces for Prompt Management
```

#### Logic / Algorithm
- `PromptRegistry` is implemented as a singleton with a thread lock around writing methods (`register` and `override`).
- It has two internally isolated structures: `_prompts` (the SDK defaults) and `_overrides` (developer customized overrides).
- `get()` checks `_overrides` first; if missing, it retrieves from `_prompts`. It then renders variables securely via `.format()`. If variables required in the template are missing, it throws `PromptRenderError`.

### 6.4 Prompt Translations

**Files:**
- `vidbyte/prompts/translations/__init__.py` (New)
- `vidbyte/prompts/translations/strategies/__init__.py` (New)
- `vidbyte/prompts/translations/strategies/react.py` (New)
- `vidbyte/prompts/translations/strategies/tree_of_thoughts.py` (New)
- `vidbyte/prompts/translations/strategies/reflexion.py` (New)
- `vidbyte/prompts/translations/strategies/self_consistency.py` (New)
- `vidbyte/prompts/translations/strategies/step_back.py` (New)
- `vidbyte/prompts/translations/harnesses/__init__.py` (New)
- `vidbyte/prompts/translations/harnesses/conditional/__init__.py` (New)
- `vidbyte/prompts/translations/harnesses/conditional/loop_agent.py` (New)
- `vidbyte/prompts/translations/harnesses/conditional/stopping_evaluator.py` (New)

#### What they contain
Exposes structural translations of prompts as classes, such as:
- `ReActSystemPrompt` & `ReActIterationPrompt`
- `TreeOfThoughtsBranchPrompt` & `TreeOfThoughtsScoringPrompt`
- `ReflexionActorPrompt`, `ReflexionEvaluatorPrompt`, `ReflexionReflectorPrompt`
- `SelfConsistencyPrompt`
- `StepBackAbstractionPrompt` & `StepBackReasoningPrompt`
- `ConditionalLoopAgentPrompt`
- `ConditionalStoppingEvaluatorPrompt`

### 6.5 Prompt Builtins default registration

**Files:**
- `vidbyte/prompts/builtins/__init__.py` (New)
- `vidbyte/prompts/builtins/vidbyte_defaults.py` (New)

#### Logic / Algorithm
A dedicated registration helper `register_defaults(registry)` is defined to automatically instantiate and register all the translation prompts so the PromptRegistry is ready to go.

### 6.6 Strategies and Harnesses Integrations

To ensure these abstractions are useful out-of-the-box, we create skeleton/placeholder files that outline exactly how strategies and harnesses fetch prompts and tools:
**Files:**
- `vidbyte/strategies/__init__.py` (New)
- `vidbyte/strategies/base.py` (New)
- `vidbyte/strategies/react.py` (New)
- `vidbyte/strategies/tree_of_thoughts.py` (New)
- `vidbyte/strategies/reflexion.py` (New)
- `vidbyte/strategies/self_consistency.py` (New)
- `vidbyte/strategies/step_back.py` (New)
- `vidbyte/harnesses/base.py` (New)
- `vidbyte/harnesses/conditional/__init__.py` (New)
- `vidbyte/harnesses/conditional/loop_agent.py` (New)
- `vidbyte/harnesses/conditional/stopping_evaluator.py` (New)
- `vidbyte/harnesses/__init__.py` (Modified)
- `vidbyte/harnesses/client.py` (Modified)

---

## 7. Data Model Changes

This system uses only memory-resident Python dataclasses for configuration and contracts. No database schemas, migrations, or SQL models are changed.

---

## 8. API Changes

### New / Modifying SDK Surface

All new classes are exported under `vidbyte` public package namespaces:

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()

# Tools registry and executor
sdk.tools.registry.register(MyCustomTool())
result = await sdk.tools.executor.execute("Action: calculator\nAction Input: {\"expression\": \"3 + 5\"}")

# Prompts registry
from vidbyte.prompts import PromptRegistry, PromptKey
prompt_reg = PromptRegistry()
rendered = prompt_reg.get(PromptKey("strategies.react", "system"), tools="[my-tool-specs]")
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/__init__.py` | Add public exports for new abstractions |
| MODIFY | `vidbyte/client.py` | Mount Tool/Prompt Registry and Strategy/Harness Clients |
| MODIFY | `vidbyte/tools/__init__.py` | Export core tool abstraction classes |
| MODIFY | `vidbyte/tools/client.py` | Add registry and executor properties to ToolsClient |
| CREATE | `vidbyte/tools/types.py` | Tool dataclasses and enums |
| CREATE | `vidbyte/tools/base.py` | Abstract `BaseTool` class |
| CREATE | `vidbyte/tools/registry.py` | Central `ToolRegistry` store |
| CREATE | `vidbyte/tools/executor.py` | Output parsing and tool execution |
| CREATE | `vidbyte/tools/builtins/__init__.py` | Export builtin tools |
| CREATE | `vidbyte/tools/builtins/calculator.py` | Sandboxed mathematical calculation |
| CREATE | `vidbyte/tools/builtins/web_search.py` | Mock search capability |
| CREATE | `vidbyte/tools/builtins/code_execution.py` | Mock code execution sandbox |
| CREATE | `vidbyte/tools/builtins/document_retrieval.py`| Mock vector store lookup |
| CREATE | `vidbyte/prompts/__init__.py` | Export core prompt registry components |
| CREATE | `vidbyte/prompts/types.py` | Prompt registries types and dataclasses |
| CREATE | `vidbyte/prompts/base.py` | Abstract `BasePrompt` class and errors |
| CREATE | `vidbyte/prompts/registry.py` | Central `PromptRegistry` singleton |
| CREATE | `vidbyte/prompts/builtins/__init__.py` | Package default hook exports |
| CREATE | `vidbyte/prompts/builtins/vidbyte_defaults.py`| Pre-loads standard prompt translations |
| CREATE | `vidbyte/prompts/translations/__init__.py` | Root for prompt translations |
| CREATE | `vidbyte/prompts/translations/strategies/__init__.py` | Export strategy prompt translations |
| CREATE | `vidbyte/prompts/translations/strategies/react.py` | ReAct system & iteration prompts |
| CREATE | `vidbyte/prompts/translations/strategies/tree_of_thoughts.py` | Tree of Thoughts branching & scoring |
| CREATE | `vidbyte/prompts/translations/strategies/reflexion.py` | Reflexion actor, critic & evaluator |
| CREATE | `vidbyte/prompts/translations/strategies/self_consistency.py` | Self-Consistency prompts |
| CREATE | `vidbyte/prompts/translations/strategies/step_back.py` | Step-Back abstraction & reasoning |
| CREATE | `vidbyte/prompts/translations/harnesses/__init__.py` | Export harness prompt translations |
| CREATE | `vidbyte/prompts/translations/harnesses/conditional/__init__.py` | Conditional translations exports |
| CREATE | `vidbyte/prompts/translations/harnesses/conditional/loop_agent.py` | Conditional loop agent prompts |
| CREATE | `vidbyte/prompts/translations/harnesses/conditional/stopping_evaluator.py` | Stopping condition evaluator prompts |
| CREATE | `vidbyte/strategies/__init__.py` | Export strategy base and concrete loops |
| CREATE | `vidbyte/strategies/base.py` | Abstract `BaseStrategy` strategy contract |
| CREATE | `vidbyte/strategies/react.py` | ReAct orchestration strategy skeleton |
| CREATE | `vidbyte/strategies/tree_of_thoughts.py` | Tree of Thoughts search strategy skeleton |
| CREATE | `vidbyte/strategies/reflexion.py` | Reflexion loop strategy skeleton |
| CREATE | `vidbyte/strategies/self_consistency.py`| Self-Consistency strategy skeleton |
| CREATE | `vidbyte/strategies/step_back.py` | Step-Back reasoning strategy skeleton |
| MODIFY | `vidbyte/harnesses/__init__.py` | Export all harnesses |
| MODIFY | `vidbyte/harnesses/client.py` | Wire harnesses registry access |
| CREATE | `vidbyte/harnesses/base.py` | Abstract `BaseHarness` contract |
| CREATE | `vidbyte/harnesses/conditional/__init__.py` | Export conditional harnesses |
| CREATE | `vidbyte/harnesses/conditional/loop_agent.py` | Conditional Loop Agent harness skeleton |
| CREATE | `vidbyte/harnesses/conditional/stopping_evaluator.py` | Stopping Condition Evaluator skeleton |

---

## 10. Testing Plan

### Unit Tests

We will create a comprehensive testing suite under `vidbyte/tests/` (or standard `tests/` directory) to verify:
1. **Tool Specs & Registry**:
   - Verify tool registration, retrieval, and specification prompt rendering.
2. **Tool Executor Parsing**:
   - Verify extraction of `ToolCall` from various text formats (including multi-line JSON inputs).
   - Verify error response when tools do not exist or when validation fails.
3. **Builtin Tools**:
   - Validate `CalculatorTool` handles safe math and raises errors on unsafe operations.
   - Validate mocks return deterministic mock data.
4. **Prompt Registry Rendering**:
   - Verify variables rendering inside templates.
   - Assert `PromptRenderError` is thrown when variables are missing.
5. **Prompt Overrides**:
   - Verify overriding a default prompt correctly updates the rendered string transparently across all references.
6. **Skeletons Loading**:
   - Verify strategies and harnesses load their default prompts successfully.

### Automated Tests
- Command to run: `python -m unittest discover -s tests` from repository root.

### Manual Verification
- Execute `python -m compileall vidbyte` to verify clean compilation.
- Run inline integration check script:
```python
from vidbyte import VidbyteSDK
from vidbyte.prompts import PromptRegistry, PromptKey

sdk = VidbyteSDK()
print(f"Tool registry specs count: {len(sdk.tools.registry.all())}")

# Try overriding and fetching
reg = PromptRegistry()
key = PromptKey("strategies.react", "system")
print(f"Default ReAct Prompt Length: {len(reg.get(key, tools='None').text)}")
```

---

## 11. Dependencies & External Services

This PR adds no external packages or runtimes. Standard library modules only.

---

## 12. Rollout & Deployment

This is a non-breaking, fully backward-compatible feature drop. Skeletons and placeholder hooks populate empty package namespaces, allowing seamless adoption without breaking existing workflows.

---

## 13. Open Questions

- [ ] Do we need to allow custom regex patterns inside `ToolExecutor` to parse tool calls that deviate from `Action:` and `Action Input:` (e.g. Markdown code block JSON format)?
  - *Recommendation*: Stick to the standard `Action` block regex for now, but design the parser to be easily overrideable or subclassable.

---

## 14. Alternatives Considered

### Alternative 1: JSON-based prompt templates (e.g. external files)
- **What**: Store templates as JSON or YAML files inside the Python package, loading them dynamically at runtime.
- **Why rejected**: Native Python classes provide better static typing, docstrings, variable contract visibility, and standard overriding mechanics without disk I/O at runtime. Class inheritance fits well with Python SDK conventions.
