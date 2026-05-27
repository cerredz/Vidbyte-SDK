"""Context Protocol Header

Description:
    Verification script for Non-Linear Agent Runtimes.
Purpose:
    Executes and validates all non-linear agent runtime test cases described in
    the design doc, ensuring strict fail-fast validation and dynamic dispatch.
Architecture:
    - Independent python execution script asserting class instantiations, type coercion,
      and fast-failing configuration raises.
Relations:
    Located in scripts/. Used to certify PR readiness in Phase 5.
"""

from __future__ import annotations

import sys
import unittest

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.agents.runtimes.linear import AgentRuntime as LinearAgentRuntime
from vidbyte.agents.runtimes.search import SearchTreeRuntimeComponent
from vidbyte.agents.runtimes.actor import ActorRuntimeComponent
from vidbyte.context.presets import ContextWindowPresets


def run_test_case(name: str, test_func: callable) -> bool:
    # Run a test function and print a descriptive PASS/FAIL label.
    try:
        test_func()
        print(f"[PASS] {name}")
        return True
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        return False


def test_mcts_instantiates_with_defaults() -> None:
    # [Edge Case] Non-linear runtime (MCTS) with empty middleware and default algorithm passes successfully.
    agent = BaseAgent(
        name="searcher",
        system_prompt="Heuristic finder.",
        runtime=AgentRuntimeType.MCTS_SEARCH,
    )
    assert agent.runtime_type == AgentRuntimeType.MCTS_SEARCH
    assert isinstance(agent._runtime(), SearchTreeRuntimeComponent)


def test_actor_instantiates_with_defaults() -> None:
    # [Edge Case] Non-linear runtime (Actor) with empty middleware and default algorithm passes successfully.
    agent = BaseAgent(
        name="actor",
        system_prompt="Message passing.",
        runtime=AgentRuntimeType.ACTOR_MODEL,
    )
    assert agent.runtime_type == AgentRuntimeType.ACTOR_MODEL
    assert isinstance(agent._runtime(), ActorRuntimeComponent)


def test_middleware_raises_fail_fast() -> None:
    # [Hidden Failure] Non-linear runtime with active middleware list raises ConfigurationError immediately.
    class DummyMiddleware:
        pass

    try:
        BaseAgent(
            name="bad_searcher",
            system_prompt="Fail fast.",
            runtime="mcts_search",
            middleware=[DummyMiddleware()],
        )
        raise AssertionError("Should have raised ConfigurationError for middleware.")
    except ConfigurationError as e:
        assert "does not support middleware" in str(e)


def test_context_algorithm_raises_fail_fast() -> None:
    # [Silent Failure] Non-linear runtime with non-default context-window algorithm preset raises ConfigurationError immediately.
    try:
        BaseAgent(
            name="bad_actor",
            system_prompt="Fail fast.",
            runtime=AgentRuntimeType.ACTOR_MODEL,
            algorithm=ContextWindowPresets().compact_tool_outputs,
        )
        raise AssertionError("Should have raised ConfigurationError for algorithm.")
    except ConfigurationError as e:
        assert "does not support in-context learning algorithms" in str(e)


def test_string_coercion_validation() -> None:
    # [Hidden Assumption] Ensure a string value "actor_model" is correctly coerced into AgentRuntimeType.ACTOR_MODEL and validates.
    agent = BaseAgent(
        name="actor_str",
        system_prompt="Coercion check.",
        runtime="actor_model",
    )
    assert agent.runtime_type == AgentRuntimeType.ACTOR_MODEL


def test_runtime_dynamic_dispatch() -> None:
    # [Edge Case] Ensure the correct runtime component classes are instantiated dynamically.
    linear_agent = BaseAgent(name="l", system_prompt="L", runtime=AgentRuntimeType.LINEAR)
    assert isinstance(linear_agent._runtime(), LinearAgentRuntime)

    search_agent = BaseAgent(name="s", system_prompt="S", runtime=AgentRuntimeType.MCTS_SEARCH)
    assert isinstance(search_agent._runtime(), SearchTreeRuntimeComponent)

    actor_agent = BaseAgent(name="a", system_prompt="A", runtime=AgentRuntimeType.ACTOR_MODEL)
    assert isinstance(actor_agent._runtime(), ActorRuntimeComponent)


def main() -> None:
    # Main execution point running all design-doc test scenarios.
    test_cases = {
        "MCTS Instantiation with Defaults [Edge Case]": test_mcts_instantiates_with_defaults,
        "Actor Instantiation with Defaults [Edge Case]": test_actor_instantiates_with_defaults,
        "Middleware Incompatibility Gating [Hidden Failure]": test_middleware_raises_fail_fast,
        "Context Window Algorithm Gating [Silent Failure]": test_context_algorithm_raises_fail_fast,
        "String Coercion Validation [Hidden Assumption]": test_string_coercion_validation,
        "Runtime Dynamic Dispatch [Edge Case]": test_runtime_dynamic_dispatch,
    }

    passed_count = 0
    total_count = len(test_cases)

    print("Running Non-Linear Agent Runtimes design-doc test cases...\n")
    for name, test_func in test_cases.items():
        if run_test_case(name, test_func):
            passed_count += 1

    print(f"\nSummary: {passed_count}/{total_count} tests passed.")

    if passed_count != total_count:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
