"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_usage.py

PURPOSE: Prove that billed reasoning tokens reach UsageRollup when an effort is set,
for each provider's documented usage shape: the rollup's output tokens follow the
vendor's billing rule from the spec's section 9.2 "Billing" table, and the output
tokens and cost_usd equal those of the same reply recorded with no effort.
ROLE IN CODEBASE: Covers spec AC-17, INV-10 and NFR-5 (reasoning spend reaches R3's
max_spend_usd through UsageRollup) for the unchanged vidbyte/agents/pricing parsers,
as reached through a DIRECT agent with an effort.
ARCHITECTURE NOTE: The Wire answers each vendor in its own response shape with a
usage block that reports reasoning tokens the way that vendor documents it. The
expected output count is the section 9.2 billing rule applied to those numbers;
prices are never copied: cost is compared between the two runs, and the pricebook is
read at run time only to know that the model is priced.
FUNCTION INVENTORY: _rollup runs one reply and returns the agent's UsageRollup;
the test_* function checks every provider shape.
COMMON MODIFICATION PATTERNS: A new provider adds one USAGE_SHAPES row with its
documented usage block and billed output count.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy a price or a cost into this file. 2. Do
not patch the usage parsers. 3. Do not write a key-shaped literal.
KNOWN EDGE CASES: xAI's total can exceed prompt plus completion by the reasoning count
(XA-25), in which case the reasoning tokens are billed on top of completion. GLM
reports no reasoning field (A-3), so its completion count is the billed output.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 6.1 INV-10, 6.2 AC-17
and 9.2 "Billing"; tests/test_agent_pricing.py; tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_usage.py
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    Wire,
    clear_provider_environment,
    direct_agent,
    run_agent,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricingRegistry

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.lib.enums import ReasoningEffort
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

# (provider, model, effort, reply dialect, usage block as the vendor reports it, billed output tokens per section 9.2 "Billing")
USAGE_SHAPES = (
    (
        "openai",
        "gpt-5.5",
        "high",
        "openai",
        {
            "input_tokens": 40,
            "output_tokens": 120,
            "output_tokens_details": {"reasoning_tokens": 100},
        },
        120,
    ),
    (
        "anthropic",
        "claude-sonnet-5",
        "high",
        "anthropic",
        {"input_tokens": 40, "output_tokens": 120},
        120,
    ),
    (
        "gemini",
        "gemini-3.5-flash",
        "high",
        "gemini",
        {
            "promptTokenCount": 40,
            "candidatesTokenCount": 6,
            "thoughtsTokenCount": 100,
            "totalTokenCount": 146,
        },
        106,
    ),
    (
        "deepseek",
        "deepseek-v4-pro",
        "high",
        "chat",
        {
            "prompt_tokens": 40,
            "completion_tokens": 120,
            "total_tokens": 160,
            "completion_tokens_details": {"reasoning_tokens": 100},
        },
        120,
    ),
    (
        "xai",
        "grok-4.7",
        "high",
        "chat",
        {
            "prompt_tokens": 32,
            "completion_tokens": 9,
            "total_tokens": 135,
            "completion_tokens_details": {"reasoning_tokens": 94},
        },
        103,
    ),
    (
        "meta",
        "muse-spark-1.1",
        "high",
        "chat",
        {
            "prompt_tokens": 40,
            "completion_tokens": 120,
            "total_tokens": 160,
            "completion_tokens_details": {"reasoning_tokens": 100},
        },
        120,
    ),
    (
        "glm",
        "glm-5.2",
        "high",
        "chat",
        {"prompt_tokens": 239, "completion_tokens": 8, "total_tokens": 247},
        8,
    ),
)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_provider_environment(monkeypatch)
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _rollup(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    model: str,
    dialect: str,
    usage: dict[str, Any],
    **options: Any,
) -> Any:
    wire = Wire(usage={dialect: usage}).install(monkeypatch)
    agent = direct_agent(provider, model, **options)
    run_agent(agent)
    assert len(wire.vendor_requests()) == 1, wire.urls
    return agent.get_usage()


@pytest.mark.parametrize(
    ("provider", "model", "value", "dialect", "usage", "billed_output"),
    USAGE_SHAPES,
    ids=[shape[0] for shape in USAGE_SHAPES],
)
def test_billed_reasoning_tokens_reach_the_usage_rollup(
    provider: str,
    model: str,
    value: str,
    dialect: str,
    usage: dict[str, Any],
    billed_output: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-17, INV-10, NFR-5: the effort changes what the vendor bills,
    # never how the SDK reads it, so reasoning spend reaches R3's cap.
    effort = _rollup(
        monkeypatch,
        provider,
        model,
        dialect,
        usage,
        reasoning_effort=ReasoningEffort(value),
    )
    unset = _rollup(monkeypatch, provider, model, dialect, usage)

    assert effort.output_tokens == billed_output
    assert (effort.output_tokens, effort.cost_usd) == (
        unset.output_tokens,
        unset.cost_usd,
    )
    if (
        ModelPricingRegistry.default().resolve(ModelProvider(provider), model)
        is not None
    ):
        assert effort.cost_usd is not None and effort.cost_usd > 0
