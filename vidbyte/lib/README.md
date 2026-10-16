# Lib

`vidbyte.lib` is the shared contract layer behind the Vidbyte SDK. It holds the
dataclasses, enums, registries, errors, config objects, runner helpers, tool
formatters, and tracing base classes that public packages build on.

## Role In The SDK

Application code normally starts with root imports from `vidbyte`, but `lib`
contains the common types that make those imports consistent. It centralizes
model provider enums, context and agent dataclasses, registry implementations,
provider config, transport helpers, and base tracing contracts.

## Design Philosophy

Shared contracts should have one home. Keeping these types in `lib` prevents
agents, tools, middleware, providers, and evals from redefining the same payload
shapes or error types. Public README examples should still prefer root imports
when a type is re-exported there.

## Usage

```python
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries import ModelPricingRegistry, ProviderModelRegistry

default_model = ProviderModelRegistry.default_model(ModelProvider.OPENAI)
api_key_env = ProviderModelRegistry.get_api_key_env_var("openai")
openai_models = ProviderModelRegistry.get_supported_models("openai")
gpt56_luna_price = ModelPricingRegistry.default().resolve(ModelProvider.OPENAI, "gpt-5.6-luna")

print(default_model, api_key_env, openai_models, gpt56_luna_price)
```

## Key Modules

- `dataclasses/`: shared payloads for agents, context, tools, middleware, runners, traces, and strategies.
- `enums/`: model providers, permissions, prompts, platforms, and runtime choices.
- `constants/`: shared SDK constants, including model/provider-to-runner mappings.
- `registries/`: agent, provider/model, pricing, runtime, prompt, tool, actor, and declarable-component registries, plus `InfiniteMemoryToolRegistry`, the table of memory tools by preset and role.
- `dataclasses/validation.py`: `RecordFieldValidator` and `RecordFieldConverter`, the canonical field checks and conversions for every validated record: text with an optional cap, pattern, and one-line rule, tuples of text items, bounded integers, enums, folders resolved once, and lists of existing files. Extend these with an option before writing a private `_text_field`-style helper.
- `errors/`: SDK-specific exception types.
- `outputs/`: provider classes that send a finished agent reply's title and body to chat channels, email, issue trackers and code hosts (including comments and update-in-place), docs workspaces, CI job summaries, social-post drafts, CRM tasks, and signed webhooks.
- `process/`: the canonical local-process helpers: `CliRunner` runs one command with a deadline and capped output, its child inheriting the caller's environment plus an overlay; `CliArgv` builds every argv from flag records in one joined or separate style; and `ProcessStopper` stops a whole process tree. Failures come back as fields of the returned record, never as exceptions, except cancellation.
- `runners/`: runner handles, concrete model runners, and runner inference helpers.
- `tools/`: provider-specific tool schema formatting; `ToolArguments.records`, which reads a model's list-of-objects argument into validated records; and under `tools/filesystem/`, `FolderUsage`, which counts a folder's files and tokens from disk and projects a write's effect on them.
- `tracing/`: tracer base classes and null tracer.
- `util/`: small canonical helpers, including `TokenEstimate` (count, cut, and cap text by the four-characters-per-token estimate) and `AppendOnlyJsonl` (an fsynced append-only JSON-lines log that leaves out and repairs a torn last line).
- `system_prompt_presets.py`: `SystemPromptPresetScope`, the run-scoped ContextVar that hands an agent's system-prompt presets to every agent its run starts.

## Related Layers

`lib` supports every public layer, especially [`agents`](../agents/README.md),
[`tools`](../tools/README.md), [`providers`](../providers/README.md), and
[`middleware`](../middleware/README.md).
