<!--
Context Protocol Header

Description:
    Usage guide for the agent behavior facade — how to call agent.behavior after a run.
Purpose:
    Step-by-step examples for each behavior category and PredicateGrader usage in eval suites.
Architecture:
    - User-facing guide with code examples per category.
    - Follows the usage skill file pattern (skills/usage/create_agent.md).
Relations:
    Referenced by skills/sdk/SKILL.md. Pairs with skills/vidbyte-sdk/agent-behavior.md.
-->

# Agent Behavior Usage

After running an agent, use `agent.behavior` to inspect what the agent did during its last
run. The facade exposes six sub-properties grouped by category.

## Quick Start

```python
from vidbyte import Agent

agent = Agent(name="worker", system_prompt="You search and read.", runner=runner, tools=[search_tool, read_tool])
await agent.arun("find and read the file")

# Check tool usage
assert agent.behavior.tool.called_tool("search")
assert agent.behavior.tool.tool_succeeded("search")

# Check stop conditions
assert agent.behavior.stop.stopped_normally()

# Check output shape
assert agent.behavior.output.is_not_empty()
assert agent.behavior.output.contains_code_block("python")

# Check loop efficiency
assert agent.behavior.efficiency.no_duplicate_tool_calls()
assert agent.behavior.efficiency.completed_within_iterations(4)
```

## Tool Presence (`agent.behavior.tool`)

```python
# Was a specific tool called?
agent.behavior.tool.called_tool("search")          # True/False
agent.behavior.tool.not_called_tool("exec")         # True/False

# Set membership
agent.behavior.tool.called_all_tools(["search", "read"])  # both called
agent.behavior.tool.called_any_tool(["search", "write"])  # at least one
agent.behavior.tool.called_no_tools()                     # no tools at all
agent.behavior.tool.called_only_tools(["search", "read"]) # no extras outside set

# Ordering (subsequence match)
agent.behavior.tool.called_tools_in_order(["search", "read"])  # search before read

# Counting
agent.behavior.tool.tool_call_count("search")  # int
agent.behavior.tool.called_tool_names()        # ("search", "read")
```

## Tool Outcome (`agent.behavior.tool`)

```python
# State checks
agent.behavior.tool.tool_succeeded("search")   # at least one SUCCEEDED
agent.behavior.tool.tool_failed("search")      # at least one FAILED
agent.behavior.tool.tool_denied("search")      # at least one DENIED
agent.behavior.tool.all_tool_calls_succeeded()  # every call succeeded

# Result content
agent.behavior.tool.tool_returned_containing("search", "python")
agent.behavior.tool.tool_returned_matching("search", r"\d{3}-\d{2}")
```

## Tool Arguments (`agent.behavior.tool_args`)

```python
# Subset match — were specific args passed?
agent.behavior.tool_args.tool_called_with("search", query="python")
agent.behavior.tool_args.tool_called_with("search", query="python", limit=10)

# Exact match — were these the exact args?
agent.behavior.tool_args.tool_called_with_exact("search", {"query": "python", "limit": 10})

# Negation
agent.behavior.tool_args.tool_never_called_with("search", query="java")

# Predicate on arg value
agent.behavior.tool_args.tool_called_with_matching("search", "query", lambda q: "python" in q)
```

## Stop Conditions (`agent.behavior.stop`)

```python
# Stop reason
agent.behavior.stop.stop_reason()                    # "final_response"
agent.behavior.stop.stopped_on("max_iterations")     # True/False
agent.behavior.stop.stopped_normally()               # True if "final_response"

# Budget checks
agent.behavior.stop.did_not_hit_max_iterations()
agent.behavior.stop.did_not_hit_max_tool_calls()
agent.behavior.stop.did_not_hit_max_tokens()
agent.behavior.stop.did_not_exceed_tokens(10000)

# Raw values
agent.behavior.stop.iteration_count()    # int
agent.behavior.stop.total_tool_calls()   # int
agent.behavior.stop.tokens_used()        # int or None
```

## Handoff (`agent.behavior.handoff`)

```python
agent.behavior.handoff.handoff_occurred()           # True if handoff produced
agent.behavior.handoff.handoff_is_filled()           # True if handoff is filled
agent.behavior.handoff.handoff_count()               # int
agent.behavior.handoff.handoff_has_section("summary") # True/False
agent.behavior.handoff.handoff_section_contains("summary", "searched")
```

## Output (`agent.behavior.output`)

```python
# Emptiness and size
agent.behavior.output.is_empty()
agent.behavior.output.is_not_empty()
agent.behavior.output.length(at_least=10, at_most=500)
agent.behavior.output.line_count(at_most=10)
agent.behavior.output.word_count(at_least=3)

# Format and references
agent.behavior.output.is_valid_json()
agent.behavior.output.contains_code_block("python")
agent.behavior.output.code_block_count("python", at_least=1)
agent.behavior.output.contains_url()
agent.behavior.output.contains_citation("markdown")

# Response stance
agent.behavior.output.refused()
agent.behavior.output.contains_hedging()
agent.behavior.output.starts_with("Result:", case_sensitive=False)
agent.behavior.output.ends_with(".", strip=True)
```

## Structured Output (`agent.behavior.output`)

When an agent run produces parsed structured output, `RunProbe.structured` reads
`reply.metadata["structured"]`.

```python
agent.behavior.output.structured_valid()
agent.behavior.output.structured_field_exists("items.0.title")
agent.behavior.output.structured_field_equals("status", "complete")
agent.behavior.output.structured_field_type("items", list)
agent.behavior.output.structured_contains_keys(["status", "items"])
```

## Efficiency / Loop Behavior (`agent.behavior.efficiency`)

Efficiency predicates inspect existing run metadata only. Duplicate checks are exact:
they compare tool names, argument mappings, and result strings; they do not detect
semantic similarity between queries.

```python
# Tool repetition and loop budgets
agent.behavior.efficiency.max_tool_repetitions("search", 2)
agent.behavior.efficiency.max_any_tool_repetitions(3)
agent.behavior.efficiency.completed_within_iterations(4)
agent.behavior.efficiency.completed_within_tool_calls(5)
agent.behavior.efficiency.tool_calls_between(1, 5)
agent.behavior.efficiency.did_not_stop_on_budget()

# Duplicate calls and arguments
agent.behavior.efficiency.no_duplicate_tool_args("search")
agent.behavior.efficiency.no_duplicate_tool_calls()
agent.behavior.efficiency.duplicate_tool_arg_count("search")
agent.behavior.efficiency.duplicate_tool_call_count()
agent.behavior.efficiency.unique_tool_call_count()
agent.behavior.efficiency.unique_tool_ratio_at_least(0.5)

# Consecutive repetition
agent.behavior.efficiency.no_consecutive_identical_calls()
agent.behavior.efficiency.no_consecutive_same_tool()
agent.behavior.efficiency.consecutive_identical_call_count()
agent.behavior.efficiency.consecutive_same_tool_count()
agent.behavior.efficiency.max_consecutive_tool_calls("search", 1)
agent.behavior.efficiency.max_any_consecutive_tool_repetitions(2)

# Results and failure thrash
agent.behavior.efficiency.repeated_tool_names()
agent.behavior.efficiency.no_repeated_tool_results()
agent.behavior.efficiency.repeated_tool_result_count("search")
agent.behavior.efficiency.max_result_repetitions(1, name="search")
agent.behavior.efficiency.failed_tool_calls_at_most(1)
agent.behavior.efficiency.denied_tool_calls_at_most(0)
agent.behavior.efficiency.unsuccessful_tool_calls_at_most(1)
agent.behavior.efficiency.no_failed_tool_retries()

# Token density
agent.behavior.efficiency.tokens_per_tool_call()
agent.behavior.efficiency.tokens_per_tool_call_at_most(500)
agent.behavior.efficiency.tokens_per_iteration()
agent.behavior.efficiency.tokens_per_iteration_at_most(1500)
```

## Using PredicateGrader in Eval Suites

```python
from vidbyte import EvalCase, EvalRunner, EvalSuite, PredicateGrader

suite = EvalSuite("behavior", [
    EvalCase(
        prompt="search for python tutorials",
        grader=PredicateGrader(lambda p: any(c.tool_name == "search" for c in p.tool_calls)),
    ),
    EvalCase(
        prompt="read the file",
        grader=PredicateGrader(lambda p: p.tool_call_count > 0 and any(c.tool_name == "read" for c in p.tool_calls)),
    ),
])

runner = EvalRunner(agent, default_grader=PredicateGrader(lambda p: False))
result = await runner.arun(suite)
print(result.pass_rate)
```

The `PredicateGrader` receives a `RunProbe` with all the same fields the behavior facade
reads. Use `p.tool_calls`, `p.stop_reason`, `p.iteration_count`, `p.handoff`, etc. directly
in the predicate lambda.

```python
EvalCase(
    prompt="Return JSON with an answer field",
    grader=PredicateGrader(lambda p: p.structured is not None and "answer" in p.structured),
)
```
