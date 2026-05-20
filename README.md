# Vidbyte SDK

`vidbyte-sdk` is the root-level home for Vidbyte's Python SDK surface.

This package is intentionally minimal right now. It establishes the SDK package identity and namespace layout without including private Vidbyte service logic.

## Status

This package is not published. It is marked `UNLICENSED` until Vidbyte's release, licensing, and open-source strategy are finalized.

## Usage

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
sdk.harnesses
sdk.tools
sdk.providers
sdk.strategies
```

## Model Runners

Semantic runners live under `vidbyte.lib.runners` and normalize provider-specific APIs.

```python
from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import TextModelRunner

runner = TextModelRunner(
    provider=ModelProvider.OPENAI,
    model="gpt-4.1-mini",
)

response = runner.run("Summarize retrieval practice in one paragraph.")
print(response.text)
```

Supported first-pass providers:

- Text: OpenAI, Anthropic, Gemini, xAI
- Image: OpenAI, xAI
- Video jobs: OpenAI

## Strategies

Prompt/API strategies live under `vidbyte.strategies` and own their runner configuration at construction time.

```python
strategy = sdk.strategies.step_back(
    runner=runner,
)
result = strategy.run("Explain why spaced repetition works.")

print(result.output)
```

Prompt templates are JSON assets under `vidbyte/prompts/prompts` and are loaded through `vidbyte.lib.prompts.PromptRegistry`.

Implemented first-batch strategies:

- Chain of Thought
- Step-Back Prompting
- Chain of Draft
- Skeleton of Thought
- Self-Consistency
- Budget Forcing
- Answer Convergence
- Plan-and-Execute
- Paradigm Routing

## Filesystem Tools

Filesystem tools are root-scoped and reject paths outside the configured root.

```python
from vidbyte.tools.filesystem import FileSystemToolConfig, ReadTextTool, StatTool

tool = ReadTextTool(FileSystemToolConfig(root="./workspace"))
content = tool.run("notes.md").value
metadata = StatTool(FileSystemToolConfig(root="./workspace")).run("notes.md").value
```

## Package Structure

```text
vidbyte/
|-- client.py
|-- harnesses/
|   `-- client.py
|-- providers/
|   |-- client.py
|   |-- openai.py
|   |-- anthropic.py
|   |-- gemini.py
|   `-- xai.py
|-- strategies/
|   |-- reasoning/
|   |-- sampling/
|   |-- agent_loops/
|   `-- routing/
|-- prompts/
|   |-- prompts/
|   `-- strategies/
|-- tools/
|   |-- client.py
|   `-- filesystem/
|-- shared/
`-- lib/
    |-- config/
    |-- dataclasses/
    |-- errors/
    |-- prompts/
    |-- tools/
    `-- runners/
```

## Public Boundary

The SDK should contain reusable public namespace scaffolding and developer-facing abstractions.

Private Vidbyte service implementations, proprietary learning evaluations, product-private prompts, scoring logic, adaptive sequencing, and database access should stay outside this package.

## Local Verification

```bash
python -m compileall vidbyte
python -m unittest discover -s tests
python -c "from vidbyte import VidbyteSDK; sdk = VidbyteSDK(); print(type(sdk.strategies).__name__)"
```
