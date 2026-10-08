"""FILE: tests/features/sdk_loop_settings/test_contract.py

PURPOSE: Probe the public AgentLoopSettings boundary for invalid budgets and timeouts before an agent starts; do not emulate a model provider here.
ROLE IN CODEBASE: Calls vidbyte.agents.settings.AgentLoopSettings and reads the resulting AgentRuntimeConfig; complements tests/test_agent_settings_validation.py.
ARCHITECTURE NOTE: Tests bind no runner and make no network calls, so a failure identifies configuration rather than model behavior.
FUNCTION INVENTORY: test_integer_limits_reject_non_integer_values tests all count fields; test_timeout_rejects_non_finite_or_invalid_values tests loop timeouts; test_tool_timeout_rejects_non_finite_values tests tool-call timeouts; test_invalid_retry_counts and test_invalid_backoff_parameters test tool-error policy; test_valid_limits_reach_runtime_config tests conversion. Run this file with pytest.
COMMON MODIFICATION PATTERNS: Add an invalid value when a new public count or timeout field is introduced; assert the named ConfigurationError and the valid runtime value.
WHAT NOT TO DO IN THIS FILE: 1. Do not implement validation here; vidbyte/agents/settings/loop.py owns it. 2. Do not call live providers; tests/agent_test_support.py owns offline agent fixtures.
KNOWN EDGE CASES: bool inherits int, NaN is not ordered, and a string throws TypeError before comparison.
RELATED DOCS: tests/features/sdk_loop_settings/FEATURE.md defines the public validation contract for these probes.
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import math

import pytest

from vidbyte.agents.settings import AgentLoopSettings, ToolErrorPolicy, ToolSettings
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


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 10**400])
def test_tool_timeout_rejects_non_finite_values(value: float | int) -> None:
    with pytest.raises(ConfigurationError, match="tool_timeout_seconds"):
        ToolSettings(tool_timeout_seconds=value)


@pytest.mark.parametrize("field", ["max_retries_per_tool_call", "max_total_tool_errors"])
@pytest.mark.parametrize("value", [True, 1.5, "2", -1, math.inf])
def test_invalid_retry_counts(field: str, value: object) -> None:
    with pytest.raises(ConfigurationError, match=field):
        ToolErrorPolicy(**{field: value})


@pytest.mark.parametrize("field", ["retry_backoff_base_seconds", "retry_backoff_multiplier", "retry_backoff_cap_seconds"])
@pytest.mark.parametrize("value", [True, "2", math.inf, math.nan])
def test_invalid_backoff_parameters(field: str, value: object) -> None:
    kwargs: dict[str, object] = {field: value}
    if field == "retry_backoff_base_seconds":
        kwargs["retry_backoff_cap_seconds"] = value
    with pytest.raises(ConfigurationError, match=field):
        ToolErrorPolicy(**kwargs)


def test_valid_limits_reach_runtime_config() -> None:
    settings = AgentLoopSettings(max_iterations=1, max_tool_calls=2, timeout_seconds=0.25)
    runtime = settings.to_runtime_config()
    assert (runtime.max_iterations, runtime.max_tool_calls, runtime.timeout_seconds) == (1, 2, 0.25)


def test_zero_retries_and_finite_backoff_are_valid() -> None:
    settings = ToolErrorPolicy(max_retries_per_tool_call=0, retry_backoff_base_seconds=0.0, retry_backoff_multiplier=1.0, retry_backoff_cap_seconds=0.0)
    assert settings.max_retries_per_tool_call == 0
