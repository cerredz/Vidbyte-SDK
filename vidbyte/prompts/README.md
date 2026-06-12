# Prompts

The Vidbyte SDK ships repository-backed prompt assets for common agent,
handoff, eval, template, goal, and trajectory workflows. Prompt text is loaded
through a small catalog rather than scattered string constants.

## Role In The SDK

`vidbyte.prompts` exposes the `Prompts` catalog, `PromptRecord`, the `Prompt`
enum, and direct prompt imports generated from catalog keys. Agents and MCP
servers can use these assets as stable prompt building blocks.

## Design Philosophy

Prompt assets should be discoverable and validated at import time. The catalog
requires prompt JSON records to map to enum values, validates referenced Markdown
assets, and exposes metadata methods so developers can inspect available prompt
families instead of memorizing filenames.

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website agents need repeatable prompt
families for feedback, handoff, evaluation, templates, goals, actor roles, and
trace summarization; the prompt catalog keeps those assets discoverable.

## Usage

```python
from vidbyte.prompts import Prompts
from vidbyte.lib.enums.prompts import Prompt

prompts = Prompts()
system_prompt = prompts.get(Prompt.REFLEXION_AGENT_SYSTEM_PROMPT)
descriptions = prompts.descriptions()
```

Direct imports are generated from prompt enum values:

```python
from vidbyte.prompts import handoff_system_prompt, templates_persona

handoff_prompt = handoff_system_prompt
persona_template = templates_persona
```

List prompt metadata and load a family:

```python
from vidbyte.prompts import Prompts

prompts = Prompts()
for key, description in prompts.descriptions().items():
    print(key.value, description)

reflexion_prompts = prompts.family("reflexion")
```

## Feature Coverage

- `Prompt` enum values as the stable key space for prompt assets.
- `PromptRecord` metadata for key, text, description, family, name, and direct import name.
- `Prompts.get()` for enum-keyed lookup.
- `Prompts.keys()`, `descriptions()`, `all()`, `family()`, and `import_names()` for discovery.
- Dynamic direct imports from `vidbyte.prompts`.
- JSON prompt asset validation and Markdown prompt asset loading.
- Prompt enum synchronization checks so catalog files and enum values stay aligned.

## Key Modules

- `catalog.py`: prompt record loading, validation, family lookup, and direct import names.
- `prompts/`: JSON and Markdown prompt assets packaged with the SDK.
- `__init__.py`: dynamic direct prompt exports.

## Related Layers

Prompts are consumed by [`agents`](../agents/README.md),
[`mcp_server`](../mcp_server/README.md), [`evals`](../evals/README.md), and
[`trace`](../trace/README.md).
