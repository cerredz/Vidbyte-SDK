"""FILE: tests/test_delegation_limits_middleware.py

PURPOSE: Proves DelegationLimits refuses caps that would switch delegation off or run it unbounded, and that DelegationLimitsMiddleware denies only the delegating tool's call, at the depth cap first and then over the batch cap, with a reason and metadata that name the cap.
ROLE IN CODEBASE: Unit tests for vidbyte/middleware/builtins/delegation_limits.py and the DelegationLimits record in vidbyte/lib/dataclasses/middleware.py. The InfiniteMemoryAgent feature tests prove the same middleware through a real run (tests/features/infinite_memory_agent/test_infinite_memory_delegation.py).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_delegation_limits_middleware.py -q
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from vidbyte.lib.dataclasses.middleware import (
    DelegationLimits,
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareHook,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.middleware import DelegationLimitsMiddleware
from vidbyte.tools import ToolCall

TOOL = "launch_subagent"
LIMITS = DelegationLimits(tool_name=TOOL, batch_argument="tasks", max_depth=3, max_parallel=2)


def _decide(middleware: DelegationLimitsMiddleware, call: ToolCall | None) -> MiddlewareDecision:
    # Runs before_tool_call once for call, outside any agent.
    return asyncio.run(middleware.before_tool_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="worker", tool_call=call)))


def _tasks(count: int) -> dict[str, Any]:
    # A launch argument carrying count placeholder tasks.
    return {"tasks": [{"name": f"task-{index}"} for index in range(count)]}


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        pytest.param({"tool_name": "  "}, "DelegationLimits.tool_name", id="blank-tool-name"),
        pytest.param({"batch_argument": "tasks\nmore"}, "DelegationLimits.batch_argument", id="two-line-argument"),
        pytest.param({"max_depth": 0}, "DelegationLimits.max_depth", id="depth-zero"),
        pytest.param({"max_parallel": True}, "DelegationLimits.max_parallel", id="parallel-bool"),
        pytest.param({"max_parallel": 1.5}, "DelegationLimits.max_parallel", id="parallel-fraction"),
    ],
)
def test_limits_refuse_caps_that_switch_delegation_off(overrides: dict[str, Any], field: str) -> None:
    """Each cap allows at least one level and one task, and the names are one-line text, so no value disables the check."""
    given = {"tool_name": TOOL, "batch_argument": "tasks", "max_depth": 3, "max_parallel": 2, **overrides}
    with pytest.raises(ConfigurationError) as raised:
        DelegationLimits(**given)
    assert raised.value.details["field"] == field


def test_middleware_refuses_a_negative_depth_and_a_plain_mapping_of_limits() -> None:
    """The depth is a level of at least 0, and the caps must arrive as a validated record."""
    with pytest.raises(ConfigurationError, match="DelegationLimitsMiddleware.depth"):
        DelegationLimitsMiddleware(LIMITS, depth=-1)
    with pytest.raises(ConfigurationError, match="DelegationLimitsMiddleware.limits"):
        DelegationLimitsMiddleware({"max_depth": 3}, depth=0)  # type: ignore[arg-type]


def test_other_tools_and_hooks_without_a_call_pass_untouched() -> None:
    """Only the named tool is checked, even at the depth cap and with an oversized argument of the same name."""
    capped = DelegationLimitsMiddleware(LIMITS, depth=LIMITS.max_depth)
    assert _decide(capped, ToolCall("grep", _tasks(9))).action is MiddlewareAction.CONTINUE
    assert _decide(capped, None).action is MiddlewareAction.CONTINUE


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_a_call_within_both_caps_continues(depth: int) -> None:
    """Below the depth cap, a call with up to max_parallel tasks runs as usual."""
    middleware = DelegationLimitsMiddleware(LIMITS, depth=depth)
    for count in range(1, LIMITS.max_parallel + 1):
        assert _decide(middleware, ToolCall(TOOL, _tasks(count))).action is MiddlewareAction.CONTINUE


@pytest.mark.parametrize("depth", [3, 4])
def test_the_depth_cap_denies_any_call_and_names_max_depth(depth: int) -> None:
    """At or past max_depth even a one-task call is denied, and the reason tells the model to do the work itself."""
    decision = _decide(DelegationLimitsMiddleware(LIMITS, depth=depth), ToolCall(TOOL, _tasks(1)))
    assert decision.action is MiddlewareAction.DENY_TOOL
    assert decision.reason is not None and "max_depth (3)" in decision.reason and f"depth {depth}" in decision.reason and "yourself" in decision.reason
    assert dict(decision.metadata) == {"limit": "max_depth", "depth": depth, "max_depth": 3}


def test_an_oversized_batch_is_denied_whole_and_names_max_parallel() -> None:
    """A call with more tasks than max_parallel is denied before anything starts, with how to split it."""
    decision = _decide(DelegationLimitsMiddleware(LIMITS, depth=0), ToolCall(TOOL, _tasks(3)))
    assert decision.action is MiddlewareAction.DENY_TOOL
    assert decision.reason is not None and "3 tasks" in decision.reason and "max_parallel (2)" in decision.reason and "nothing was started" in decision.reason
    assert dict(decision.metadata) == {"limit": "max_parallel", "tasks": 3, "max_parallel": 2}


def test_the_depth_cap_is_reported_before_the_batch_cap() -> None:
    """When both caps are broken the depth refusal wins, because splitting the batch would not help."""
    decision = _decide(DelegationLimitsMiddleware(LIMITS, depth=LIMITS.max_depth), ToolCall(TOOL, _tasks(5)))
    assert decision.metadata["limit"] == "max_depth"


@pytest.mark.parametrize("tasks", [None, "three tasks", {"name": "one"}])
def test_a_task_argument_that_is_not_a_list_is_left_to_the_tool(tasks: object) -> None:
    """The middleware counts only lists; the tool reports a malformed argument in its own words."""
    arguments = {} if tasks is None else {"tasks": tasks}
    assert _decide(DelegationLimitsMiddleware(LIMITS, depth=0), ToolCall(TOOL, arguments)).action is MiddlewareAction.CONTINUE
