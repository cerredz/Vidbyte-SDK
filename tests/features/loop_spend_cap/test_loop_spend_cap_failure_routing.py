"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_failure_routing.py

PURPOSE: Prove a reply the spend cap stopped is routed by sessions as one exhausted
resource failure, never as a generic runtime error, and that the eval layer counts it
as a budget stop.
ROLE IN CODEBASE: Behavior tests for spec INV-10, AC-17 and AC-18 against
FailureMetadataNormalizer.from_reply and EfficiencyBehavior.did_not_stop_on_budget, fed
by a real capped run rather than a hand-built reply.
ARCHITECTURE NOTE: The reply comes from a real BaseAgent run over the scripted runner,
so the metadata the router reads is exactly what the runtime writes on a cap stop. The
normalizer itself is production code and is not mocked.
FUNCTION INVENTORY: test_a_cap_stop_routes_as_one_exhausted_resource_failure;
test_a_cap_stop_counts_as_a_budget_stop.
COMMON MODIFICATION PATTERNS: A new consumer that classifies stop reasons adds one case
fed by the same capped reply.
WHAT NOT TO DO IN THIS FILE: 1. Do not add or reorder FailureCode members; the spec maps
the cap onto the existing resource.exhausted code. 2. Do not mock
FailureMetadataNormalizer. 3. Do not hand-build the metadata the runtime writes.
KNOWN EDGE CASES: The details are exactly three keys; a richer record would change what
bound recovery handlers receive.
RELATED DOCS: docs/spec/loop-spend-cap/spec.md INV-10, INV-21, AC-17, AC-18, EC-34.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_failure_routing.py
"""

from __future__ import annotations

from typing import Any

from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    MAX_SPEND,
    LookupTool,
    ScriptedRunner,
    call_response,
    capped_settings,
    priced_agent,
    reference_cost,
    text_response,
    usage,
)
from vidbyte.lib.enums.failure import (
    FailureCode,
    FailureDisposition,
    FailurePhase,
    FailureStatus,
)
from vidbyte.sessions.failure.router import FailureMetadataNormalizer


def _capped_run() -> tuple[Any, Any]:
    response = call_response(("lookup", {"q": "Paris"}), usage=usage(1_000, 100))
    agent = priced_agent(
        ScriptedRunner(response),
        tools=[LookupTool()],
        loop=capped_settings(reference_cost(response)),
    )
    return agent, agent.run("Find the capital.")


def test_a_cap_stop_routes_as_one_exhausted_resource_failure() -> None:
    # AC-17 and INV-10: without the mapping the stop would fall through to the generic runtime error code.
    _, reply = _capped_run()
    assert reply.metadata["stop_reason"] == MAX_SPEND

    (failure,) = FailureMetadataNormalizer.from_reply(reply)

    assert failure.code is FailureCode.RESOURCE_EXHAUSTED
    assert (failure.status, failure.disposition, failure.phase, failure.source) == (
        FailureStatus.EXHAUSTED,
        FailureDisposition.ROUTE,
        FailurePhase.LOOP,
        "agent_runtime",
    )
    assert dict(failure.details) == {
        "stop_reason": MAX_SPEND,
        "iteration_count": reply.metadata["iteration_count"],
        "tokens_used": reply.metadata["tokens_used"],
    }


def test_a_cap_stop_counts_as_a_budget_stop() -> None:
    # AC-18: the eval predicate must not report a capped run as one that finished within budget.
    finished = priced_agent(ScriptedRunner(text_response("Paris.", usage=usage(10, 1))))
    finished.run("Find the capital.")
    assert finished.behavior.efficiency.did_not_stop_on_budget() is True

    agent, _ = _capped_run()

    assert agent.behavior.efficiency.did_not_stop_on_budget() is False
