"""FILE: tests/features/sdk_consumer_probes/test_consumer_programs.py

PURPOSE: Keep real, runnable SDK consumer programs in the full source CI gate.
ROLE IN CODEBASE: Calls scripts/sdk_edge_probes/run.py's public scenarios, which compose real SDK objects but replace outbound model transport.
ARCHITECTURE NOTE: These tests do not mock SDK runtime behavior; each exercise is also runnable as a standalone script by a developer.
FUNCTION INVENTORY: test_agent_flow exercises reused agent usage and trace; test_budget_flow checks middleware; test_tool_limit_flow checks tool policy; test_structured_flow checks schema; test_handoff_flow checks typed and prose handoffs; test_jev_flow checks Jev preflight and total usage.
COMMON MODIFICATION PATTERNS: Add one scenario and its matching test when another public SDK combination should be probed.
WHAT NOT TO DO IN THIS FILE: 1. Do not duplicate scenario internals. 2. Do not issue live provider requests or require credentials.
KNOWN EDGE CASES: Handoff retries invalid structured output; JEV rejects unpriced fake model usage.
RELATED DOCS: tests/features/sdk_consumer_probes/FEATURE.md; scripts/sdk_edge_probes/README.md.
TESTS: This file, the full source gate, and python -m scripts.sdk_edge_probes.run.
"""

from __future__ import annotations

import pytest

from scripts.sdk_edge_probes.run import (
    run_agent_flow,
    run_budget_flow,
    run_handoff_flow,
    run_jev_flow,
    run_structured_flow,
    run_tool_limit_flow,
)


@pytest.mark.asyncio
async def test_agent_flow() -> None:
    await run_agent_flow()


@pytest.mark.asyncio
async def test_budget_flow() -> None:
    await run_budget_flow()


@pytest.mark.asyncio
async def test_tool_limit_flow() -> None:
    await run_tool_limit_flow()


@pytest.mark.asyncio
async def test_structured_flow() -> None:
    await run_structured_flow()


@pytest.mark.asyncio
async def test_handoff_flow() -> None:
    await run_handoff_flow()


@pytest.mark.asyncio
async def test_jev_flow() -> None:
    await run_jev_flow()
