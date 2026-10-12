# Bill xAI reasoning tokens as output

## Problem

xAI's chat-completions usage reports reasoning tokens outside `completion_tokens`. A live
`grok-4.3` call through `BaseAgent` (2026-10-11) returned:

- `prompt_tokens` 473, with 128 cached.
- `completion_tokens` 11.
- `completion_tokens_details.reasoning_tokens` 163.
- `total_tokens` 647, which is 473 + 11 + 163.
- `cost_in_usd_ticks` 8918500, which is $0.00089185.

`ChatCompletionUsage` read `output_tokens` from `completion_tokens` alone, so `get_cost_usd()`
reported $0.00048435, about 54% of what xAI charged. Budget middleware and usage rollups
under-counted every Grok reasoning call by the same margin. The two token counts also failed to
add up to `total_tokens`.

OpenAI-style chat completions already count reasoning inside `completion_tokens`, with a total of
prompt + completion. Adding reasoning unconditionally would double-bill those providers, as the
providers README warns.

## Change

`ChatCompletionUsage.from_usage_payload` sets `output_tokens` to completion + reasoning only when
the reported total equals prompt + completion + reasoning. In every other case it keeps
`completion_tokens` as reported:

- an OpenAI-style total;
- a missing prompt, completion, or total count;
- zero reasoning tokens.

The rule keys on the response shape, not a provider name, so it stays one class per shape.
OpenRouter inherits the rule, but its reported `cost` still wins over table math.

## Alternatives not taken

- **Pricing from xAI's `cost_in_usd_ticks`.** It is authoritative, but it is xAI-only and
  undocumented in the SDK. Token counts also feed budgets and speed statistics, not just cost, so
  the token count itself has to be right.
- **A separate `XAIUsage` class.** xAI's response shape is otherwise identical, and the total
  already distinguishes the convention.

## Tests

`tests/test_agent_pricing.py` adds three tests:

- The live payload prices to xAI's billed cost to 12 decimal places. On the old code it fails
  with 11 != 174.
- An OpenAI-style total is not double-counted.
- A missing total leaves the reported output unchanged.
