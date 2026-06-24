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
run. The facade exposes four sub-properties grouped by category.

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
        grader=PredicateGrader(lambda p: p.tool_call_count > 0 and p.tool_succeeded("read")),
    ),
])

runner = EvalRunner(agent, default_grader=PredicateGrader(lambda p: False))
result = await runner.arun(suite)
print(result.pass_rate)
```

The `PredicateGrader` receives a `RunProbe` with all the same fields the behavior facade
reads. Use `p.tool_calls`, `p.stop_reason`, `p.iteration_count`, `p.handoff`, etc. directly
in the predicate lambda.
