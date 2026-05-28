"""Context Protocol Header

Description:
    Verification script for Advanced Agent Runtimes and Registries.
Purpose:
    Ensures that the relocated registries, swappable runtime config classes,
    PrebuiltActor hierarchy, and selective spawning mechanisms work together correctly.
Architecture & Key Functions:
    - Main execution checking multiple unit, integration, edge cases, failure modes,
      and hidden assumptions in the registry and runtime logic.
Relations:
    Located in scripts/test-feat-advanced-runtimes-and-registries.py. Used for Phase 5 verification.
Similar Files:
    - scripts/test-actor-model-runtime-redesign.py: Verifies original actor runtime loops.
"""

from __future__ import annotations

import sys
import asyncio
from typing import Sequence

from vidbyte.lib.registries import (
    AgentRegistry,
    ProviderModelRegistry,
    Prompts,
    ToolRegistry,
    ActorRegistry,
    actor_registry,
)
from vidbyte.agents.runtimes.configs import LinearRuntime, MctsSearchRuntime, ActorRuntime
from vidbyte.agents.runtimes.actor.actor import (
    PrebuiltActor,
    PlannerActor,
    CoderActor,
    ReviewerActor,
    GeneratorActor,
    CriticActor,
    ReasonerActor,
    SummarizationActor,
    DecomposerActor,
    ExplorerActor,
    TradeoffActor,
    HypothesisGeneratorActor,
    RefinerActor,
    FormatterActor,
    SafetyActor,
    FinalAnswerActor,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.errors import ConfigurationError


class VerificationHarness:
    """Harness that coordinates and runs all test cases for verification."""

    def __init__(self) -> None:
        # Initialises verification statistics.
        self.passed = 0
        self.failed = 0

    def run_test(self, name: str, test_fn: callable) -> None:
        # Executes a single test case safely and prints a structured label.
        try:
            test_fn()
            print(f"[ PASS ] {name}")
            self.passed += 1
        except Exception as e:
            print(f"[ FAIL ] {name}")
            print(f"         Error: {e}")
            self.failed += 1


def test_registries_relocation() -> None:
    # [Edge Case] Verify all relocated registry classes load correctly from the new package.
    assert AgentRegistry is not None
    assert ProviderModelRegistry is not None
    assert Prompts is not None
    assert ToolRegistry is not None
    assert ActorRegistry is not None
    assert actor_registry is not None
    print("         All registries loaded successfully from subpackage.")


def test_runtime_config_objects() -> None:
    # [Edge Case] Validate agent instantiation with Linear, Search, and Actor runtimes.
    agent_lin = BaseAgent(
        name="test_linear",
        system_prompt="Help.",
        runtime=LinearRuntime(),
    )
    assert agent_lin.runtime_type.value == "linear"

    agent_mcts = BaseAgent(
        name="test_mcts",
        system_prompt="Help.",
        runtime=MctsSearchRuntime(),
    )
    assert agent_mcts.runtime_type.value == "mcts_search"

    agent_act = BaseAgent(
        name="test_actor",
        system_prompt="Help.",
        runtime=ActorRuntime(dynamic_actors=True),
    )
    assert agent_act.runtime_type.value == "actor_model_p2p"


def test_selective_actor_spawning() -> None:
    # [Edge Case] Spawning empty, list, or None actors registers appropriate runtime actor settings.
    agent_empty = BaseAgent(
        name="test_empty",
        system_prompt="Help.",
        runtime=ActorRuntime(include_actors=[]),
    )
    runtime_empty = agent_empty._runtime()
    assert runtime_empty.include_actors == []

    agent_select = BaseAgent(
        name="test_select",
        system_prompt="Help.",
        runtime=ActorRuntime(include_actors=[PlannerActor, CoderActor]),
    )
    runtime_select = agent_select._runtime()
    assert runtime_select.include_actors == [PlannerActor, CoderActor]

    agent_none = BaseAgent(
        name="test_none",
        system_prompt="Help.",
        runtime=ActorRuntime(include_actors=None),
    )
    runtime_none = agent_none._runtime()
    assert runtime_none.include_actors is None


def test_actor_registry_methods() -> None:
    # [Edge Case] Check ActorRegistry list, get, all, and registration work perfectly.
    assert "planner" in actor_registry.list()
    assert "summarization" in actor_registry.list()
    assert actor_registry.get("coder") is CoderActor
    assert actor_registry.get("summarization") is SummarizationActor

    all_actors = actor_registry.all()
    assert len(all_actors) == 15
    assert all_actors["planner"] is PlannerActor


def test_fail_fast_runtime_validation() -> None:
    # [Hidden Failure] Verify ConfigurationError when trying to configure incompatible options.
    try:
        BaseAgent(
            name="test_fail",
            system_prompt="Help.",
            runtime=ActorRuntime(),
            middleware=[object()],  # Non-linear runtimes don't support middleware
        )
        raise AssertionError("Expected ConfigurationError did not raise for active middleware in non-linear runtime.")
    except ConfigurationError:
        pass


def main() -> None:
    # Executes the full test suite and outputs the final result.
    harness = VerificationHarness()
    harness.run_test("test_registries_relocation", test_registries_relocation)
    harness.run_test("test_runtime_config_objects", test_runtime_config_objects)
    harness.run_test("test_selective_actor_spawning", test_selective_actor_spawning)
    harness.run_test("test_actor_registry_methods", test_actor_registry_methods)
    harness.run_test("test_fail_fast_runtime_validation", test_fail_fast_runtime_validation)

    print("\n--- Summary ---")
    print(f"{harness.passed} / {harness.passed + harness.failed} tests passed")
    if harness.failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
