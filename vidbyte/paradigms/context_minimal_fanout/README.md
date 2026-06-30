# Context Minimal Fanout

`context_minimal_fanout` is a paradigm for reducing implementation-agent context
load by splitting one large request into multiple non-overlapping prompts and
running each prompt in a fresh agent context.

## Role In The SDK

This package contains Vidbyte-owned runnable paradigm harnesses. The first
implementation is `multiple_prompts`, which composes existing SDK agents, tools,
middleware, and prompt assets into one split-and-fanout execution loop.

## Usage

```python
from vidbyte import VidbyteSDK

sdk = VidbyteSDK()
harness = sdk.paradigms.context_minimal_fanout.multiple_prompts(
    implementation_tools=[patch_tool],
    implementation_model_name="gpt-5-codex",
    splitter_model_name="gpt-5",
)

result = await harness.arun("Implement the requested repository change.")
print(result.plan_markdown)
```

## Non-Overlap Rules

Each split prompt must own distinct paths. Shared context belongs in
`read_only_paths`, not `owned_paths`. The harness rejects duplicate prompt ids
and duplicate owned paths before implementation agents run.

## Default Tools

The splitter receives default read/search/code tools when
`include_default_splitter_tools=True`: glob, grep, read text, read lines, and
code execution. Implementation agents only receive tools passed through
`implementation_tools`, so write permissions remain explicit.

## Limits

`max_prompt_count` bounds split size. `max_concurrency` bounds simultaneous
implementation agents. Per-agent token and cost middleware can be configured,
but this first version does not implement cross-agent total budget cancellation.

## Related Layers

This paradigm composes [`agents`](../../agents/README.md),
[`tools`](../../tools/README.md), [`middleware`](../../middleware/README.md),
and the generic [`paradigms`](../README.md) harness contract.
