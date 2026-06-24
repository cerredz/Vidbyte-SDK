<!--
Context Protocol Header

Description:
    SDK sub-skill for the agent behavior facade: how to use it and how to extend it.
Purpose:
    Documents the agent.behavior API, the RunProbe snapshot, the category decomposition,
    the PredicateGrader bridge, and the invariants any change must preserve.
Architecture:
    - Usage: agent.behavior.tool, agent.behavior.tool_args, agent.behavior.stop, agent.behavior.handoff, agent.behavior.output.
    - Internals: RunProbe + Behavior facade + category classes + BaseAgent property.
Relation to the codebase as a whole:
    Sub-skill referenced by skills/vidbyte-sdk/SKILL.md. Pairs with evals.md and
    continual-tracing.md.
-->

# Agent Behavior

## What it is

A post-run predicate facade that lets developers inspect *what an agent did* — not just
what it said. After `await agent.arun(prompt)`, access `agent.behavior` to query tool
presence, tool outcomes, tool arguments, stop conditions, handoff occurrence, and
output shape through ergonomic boolean methods grouped by category.

```python
from vidbyte import Agent

agent = Agent(name="worker", system_prompt="...", runner=runner, tools=[search_tool, read_tool])
reply = await agent.arun("find and read the file")

# Tool presence
assert agent.behavior.tool.called_tool("search")
assert agent.behavior.tool.called_all_tools(["search", "read"])
assert agent.behavior.tool.called_only_tools(["search", "read"])

# Tool outcome
assert agent.behavior.tool.tool_succeeded("search")
assert agent.behavior.tool.all_tool_calls_succeeded()

# Tool arguments
assert agent.behavior.tool_args.tool_called_with("search", query="python")

# Stop conditions
assert agent.behavior.stop.stopped_normally()
assert agent.behavior.stop.did_not_hit_max_iterations()

# Handoff
assert agent.behavior.handoff.handoff_occurred()

# Output shape
assert agent.behavior.output.is_not_empty()
assert agent.behavior.output.contains_code_block("python")
assert agent.behavior.output.structured_field_exists("answer")
```

## Architecture (do not bypass)

- `vidbyte/evals/behavior/probe.py` — `RunProbe`: frozen, slotted dataclass capturing a
  completed run's observable state. Built from `agent.last_reply.metadata` plus
  `agent.last_handoff`, `agent.handoffs`, `agent.last_trace`, and structured output from
  `reply.metadata["structured"]`.
- `vidbyte/evals/behavior/behavior.py` — `Behavior`: facade that lazily builds a `RunProbe`
  and composes four category behavior objects. Exposed via `agent.behavior`.
- `vidbyte/evals/behavior/tool.py` — `ToolBehavior`: predicates over tool presence (A) and
  outcome/state (B).
- `vidbyte/evals/behavior/tool_arguments.py` — `ToolArgumentBehavior`: predicates over tool
  call arguments (C).
- `vidbyte/evals/behavior/stop.py` — `StopBehavior`: predicates over stop reason, iterations,
  tokens (D).
- `vidbyte/evals/behavior/output.py` - `OutputBehavior`: predicates over response text and
  structured output (F).
- `vidbyte/evals/behavior/handoff.py` — `HandoffBehavior`: predicates over handoff occurrence (E).
- `vidbyte/agents/base.py` — `behavior` property (lazy, cached), invalidated at the start of
  `generate_reply`.
- `vidbyte/evals/graders/predicate.py` — `PredicateGrader`: bridges behavior predicates into
  `EvalRunner` suites via `agrade_with_probe`.
- `vidbyte/evals/runner.py` — builds `RunProbe` per case for agent targets; dispatches to
  `agrade_with_probe` when the grader implements it.

## Function Catalog

### `agent.behavior.tool` (ToolBehavior)

| Method | Description |
|--------|-------------|
| `called_tool(name)` | True if the named tool was called at least once. |
| `not_called_tool(name)` | True if the named tool was never called. |
| `called_all_tools(names)` | True if every tool in `names` was called. |
| `called_any_tool(names)` | True if at least one tool in `names` was called. |
| `called_no_tools()` | True if no tool calls were made. |
| `called_only_tools(names)` | True if every call was to a tool in `names` (no extras). |
| `called_tools_in_order(names)` | True if `names` is a subsequence of the call order. |
| `tool_call_count(name)` | Number of times the named tool was called. |
| `called_tool_names()` | Ordered unique tool names (first-occurrence order). |
| `tool_succeeded(name)` | True if any call to `name` has state SUCCEEDED. |
| `tool_failed(name)` | True if any call to `name` has state FAILED. |
| `tool_denied(name)` | True if any call to `name` has state DENIED. |
| `all_tool_calls_succeeded()` | True if every call has state SUCCEEDED. |
| `tool_returned_containing(name, substring)` | True if any call's result contains substring. |
| `tool_returned_matching(name, pattern)` | True if any call's result matches the regex. |

### `agent.behavior.tool_args` (ToolArgumentBehavior)

| Method | Description |
|--------|-------------|
| `tool_called_with(name, **args)` | True if any call to `name` has `args` as a subset. |
| `tool_called_with_exact(name, args)` | True if any call to `name` has exact arg dict match. |
| `tool_never_called_with(name, **args)` | Negation of `tool_called_with`. |
| `tool_called_with_matching(name, arg_name, predicate)` | True if `arg_name` present and predicate(value). |

### `agent.behavior.stop` (StopBehavior)

| Method | Description |
|--------|-------------|
| `stop_reason()` | Raw stop reason string. |
| `stopped_on(reason)` | True if stop reason matches. |
| `stopped_normally()` | True if stop reason is `"final_response"`. |
| `did_not_hit_max_iterations()` | True if not stopped by max_iterations. |
| `did_not_hit_max_tool_calls()` | True if not stopped by max_tool_calls. |
| `did_not_hit_max_tokens()` | True if not stopped by max_tokens. |
| `iteration_count()` | Total iteration count. |
| `total_tool_calls()` | Total tool call count. |
| `tokens_used()` | Tokens used, or None if not reported. |
| `did_not_exceed_tokens(limit)` | True if tokens_used is None or <= limit. |

### `agent.behavior.handoff` (HandoffBehavior)

| Method | Description |
|--------|-------------|
| `handoff_occurred()` | True if a handoff was produced. |
| `handoff_is_filled()` | True if the last handoff is marked filled. |
| `handoff_count()` | Number of handoffs recorded. |
| `handoff_has_section(title)` | True if the last handoff has the named section. |
| `handoff_section_contains(title, substring)` | True if the named section contains substring. |

### `agent.behavior.output` (OutputBehavior)

| Method | Description |
|--------|-------------|
| `is_empty(strip=True)` | True if output is empty, optionally after stripping whitespace. |
| `is_not_empty(strip=True)` | Negation of `is_empty`. |
| `length(at_least=None, at_most=None, strip=False)` | True if character length is within inclusive bounds. |
| `line_count(at_least=None, at_most=None)` | True if logical line count is within inclusive bounds. |
| `word_count(at_least=None, at_most=None)` | True if word-token count is within inclusive bounds. |
| `is_valid_json()` | True if raw output parses as JSON. |
| `contains_code_block(language=None)` | True if output contains a Markdown fenced code block. |
| `code_block_count(language=None, at_least=None, at_most=None)` | Count fenced code blocks, or check bounds when supplied. |
| `contains_url()` | True if output contains an HTTP(S) or `www.` URL. |
| `url_count(at_least=None, at_most=None)` | Count URLs, or check bounds when supplied. |
| `contains_citation(style="any")` | True if output contains a citation-like marker. |
| `citation_count(style="any", at_least=None, at_most=None)` | Count citations, or check bounds when supplied. |
| `refused()` | True if output contains common refusal language. |
| `contains_hedging()` | True if output contains common hedging language. |
| `starts_with(prefix, case_sensitive=True, strip=False)` | True if output starts with prefix. |
| `ends_with(suffix, case_sensitive=True, strip=False)` | True if output ends with suffix. |
| `structured_valid()` | True if `RunProbe.structured` is not None. |
| `structured_field_exists(path)` | True if a dot-path field exists in structured output. |
| `structured_field_equals(path, value)` | True if a structured field equals value. |
| `structured_field_matches(path, predicate)` | True if predicate(value) is true for a structured field. |
| `structured_field_type(path, expected_type)` | True if a structured field has the expected type. |
| `structured_contains_keys(keys)` | True if top-level structured output contains every key. |

## Using PredicateGrader in Eval Suites

```python
from vidbyte import EvalCase, EvalRunner, EvalSuite, PredicateGrader

suite = EvalSuite("behavior", [
    EvalCase(
        prompt="search for X",
        grader=PredicateGrader(lambda p: any(c.tool_name == "search" for c in p.tool_calls)),
    ),
])
runner = EvalRunner(agent, default_grader=PredicateGrader(lambda p: False))
result = await runner.arun(suite)
```

`PredicateGrader` implements `agrade_with_probe`, which `EvalRunner` detects and calls with
a `RunProbe` built from the forked agent. Standard graders (`ContainsGrader`, etc.) are
unaffected — the runner falls back to `agrade` when `agrade_with_probe` is not present.

## Invariants any change must preserve

1. **Read-only.** Behavior predicates never mutate agent state, run state, or reply metadata.
2. **Lazy probe.** The `RunProbe` is built on first access of `agent.behavior.probe`, not at
   construction. The `Behavior` instance is cached on `agent._behavior_view` and invalidated
   at the start of `generate_reply`.
3. **Source of truth is `reply.metadata["tool_calls"]`.** This is per-run and always correct
   for text modality. Do not fall back to `agent._tool_call_contexts` (accumulates across runs).
4. **Non-text modality returns empty tool calls.** Non-text modalities don't run tool loops;
   an empty `tool_calls` tuple is correct, not a bug.
5. **`PredicateGrader` is opt-in.** The runner uses `hasattr(grader, "agrade_with_probe")`
   duck-typing; `BaseGrader.agrade` signature is unchanged.
6. **Output behavior is not arbitrary text grading.** Keep substring and caller-provided regex
   assertions in `ContainsGrader` and `RegexMatchGrader`; `OutputBehavior` owns structural and
   linguistic response properties.

## Adding a new behavior category

1. Create `vidbyte/evals/behavior/<category>.py` with a class that accepts a `Behavior`
   reference and reads `self._behavior.probe`.
2. Export the class from `vidbyte/evals/behavior/__init__.py`.
3. Add a property to `Behavior` in `vidbyte/evals/behavior/behavior.py` that returns the
   new category object.
4. Add tests to `tests/test_agent_behavior.py` and the relevant script in `scripts/`.
5. Update this skill file's function catalog.

## Verify

`python scripts/test-agent-behavior.py` and `python -m unittest tests.test_agent_behavior`.
