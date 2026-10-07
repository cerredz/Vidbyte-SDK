"""FILE: tests/features/sdk_loop_settings/test_contract.py

PURPOSE: Probe the public AgentLoopSettings boundary for invalid budgets and timeouts before an agent starts; do not emulate a model provider here.
ROLE IN CODEBASE: Calls vidbyte.agents.settings.AgentLoopSettings and reads the resulting AgentRuntimeConfig; complements tests/test_agent_settings_validation.py.
ARCHITECTURE NOTE: Tests bind no runner and make no network calls, so a failure identifies configuration rather than model behavior.
FUNCTION INVENTORY: test_integer_limits_reject_non_integer_values tests all count fields; test_timeout_rejects_non_finite_or_invalid_values tests timeouts; test_valid_limits_reach_runtime_config tests conversion. Run this file with pytest.
COMMON MODIFICATION PATTERNS: Add an invalid value when a new public count or timeout field is introduced; assert the named ConfigurationError and the valid runtime value.
WHAT NOT TO DO IN THIS FILE: 1. Do not implement validation here; vidbyte/agents/settings/loop.py owns it. 2. Do not call live providers; tests/agent_test_support.py owns offline agent fixtures.
KNOWN EDGE CASES: bool inherits int, NaN is not ordered, and a string throws TypeError before comparison.
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import math

import pytest

from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.errors import ConfigurationError

INTEGER_FIELDS = (
    "max_iterations", "max_tokens", "max_tool_calls", "max_queued_prompts",
    "max_parallel_tool_calls", "max_retries", "context_window_budget",
    "compaction_trigger_tokens", "compaction_target_tokens", "max_contract_rejections",
)


@pytest.mark.parametrize("field", INTEGER_FIELDS)
@pytest.mark.parametrize("value", [True, 1.5, "4", 0, -1])
def test_integer_limits_reject_non_integer_values(field: str, value: object) -> None:
    with pytest.raises(ConfigurationError, match=field):
        AgentLoopSettings(**{field: value})


@pytest.mark.parametrize("value", [True, "1", float("nan"), math.inf, -math.inf, 0, -1])
def test_timeout_rejects_non_finite_or_invalid_values(value: object) -> None:
    with pytest.raises(ConfigurationError, match="timeout_seconds"):
        AgentLoopSettings(timeout_seconds=value)


def test_valid_limits_reach_runtime_config() -> None:
    settings = AgentLoopSettings(max_iterations=1, max_tool_calls=2, timeout_seconds=0.25)
    runtime = settings.to_runtime_config()
    assert (runtime.max_iterations, runtime.max_tool_calls, runtime.timeout_seconds) == (1, 2, 0.25)
