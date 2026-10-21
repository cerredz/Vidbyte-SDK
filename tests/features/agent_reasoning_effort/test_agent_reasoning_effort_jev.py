"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_jev.py

PURPOSE: Prove that JevAgentSettings.reasoning_effort reaches every generative call
that runs on JevAgent's own model, and nothing else: the main agent, the
fresh-continuation agent, JevRunState and JevRunStateRelation, JevHandoff,
JevReviewer, JevClarificationAgent, bulk workers, clones and swarm helpers each send
the fragment, while the run-brief writer, a specialist on the delegated path and the
Jev decision calls send exactly what they send without it.
ROLE IN CODEBASE: Covers spec AC-9, INV-15, EC-20, D-9 and FR-9 for
vidbyte/agents/jev/{agent,settings,bulk_work}.py, vidbyte/agents/jev/compute/{clone,swarm}.py,
vidbyte/agents/jev/done/{run_state,handoff,reviewer}.py,
vidbyte/agents/jev/gate/clarification.py and vidbyte/agents/jev/brief/writer.py.
ARCHITECTURE NOTE: Every child is built by production code (JevAgent's own wiring or
the child's constructor) and run once against the Wire, which fails each Messages
call with HTTP 500 so a child sends exactly one request and stops. Each child is
compared with the same child built from settings without the effort, in the same
test, so the expectation never depends on which children use structured output.
The delegated path fakes TypeSafeProvider.run_decision, the seam R3's pack uses;
decision calls are otherwise observed on the wire, where they fail open.
FUNCTION INVENTORY: _settings builds DIRECT JevAgentSettings on Anthropic; _runtime
builds the runtime that creates every machinery child; CHILDREN maps a label to its
builder; _delegate_to_database answers every decision by choosing the specialist;
the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new Jev child that runs on the main model adds one
CHILDREN entry; one that must not inherit the effort adds one exclusion test.
WHAT NOT TO DO IN THIS FILE: 1. Do not bind a ScriptedRunner to a child; it bypasses
the adapter and hides the fragment. 2. Do not hard-code which children send
output_config.format; compare with the unset build. 3. Do not write a key-shaped literal.
KNOWN EDGE CASES: A JevAgent with no runtime settings makes no decision call, so its
first Messages request is the main model's. Decision calls answer HTTP 500 and Jev's
gates fail open.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 6.1 INV-15, 6.2 AC-9,
8.1 D-9 and 9.2 "Every agent"; tests/features/loop_spend_cap/test_loop_spend_cap_jev.py
(the delegated-path seam); tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_jev.py
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    VIDBYTE_KEY,
    Wire,
    clear_provider_environment,
    direct_agent,
    first_request,
    provider_key,
    run_agent,
)
from tests.test_jev_usage_ledger import _answer
from vidbyte import (
    JevAgent,
    JevAgentSettings,
    JevPreflightPreset,
    JevRuntimeSettings,
    JevSpecialist,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.jev.brief.writer import JevRunBriefWriter
from vidbyte.agents.jev.bulk_work import JevBulkWorker
from vidbyte.agents.jev.compute.clone import JevCloneAgent
from vidbyte.agents.jev.compute.swarm import JevSwarmAgent
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevContinualSettings, JevRunBriefSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_DEFAULT_MODEL
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevSwarmAssignment
from vidbyte.lib.enums import (
    DecisionModelMode,
    JevContinuationGate,
    JevDoneCheck,
    ModelProvider,
    TextModelMode,
)
from vidbyte.lib.runners.types import DecisionModelResponse

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import ReasoningEffort
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

RUN_DECISION = "vidbyte.providers.typesafe.TypeSafeProvider.run_decision"
ANTHROPIC = "https://api.anthropic.com"
MODEL = "claude-sonnet-5"
TASK = "Rename users.email to users.email_address."
SPECIALIST = "database"
SPECIALIST_PROMPT = "Plan database migrations."


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_provider_environment(monkeypatch)
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _settings(**options: Any) -> JevAgentSettings:
    return JevAgentSettings(
        name="jev",
        system_prompt="Work carefully.",
        provider="anthropic",
        model_name=MODEL,
        api_keys=[provider_key("anthropic")],
        model_mode=TextModelMode.DIRECT,
        **options,
    )


def _runtime(*preflight: JevPreflightPreset) -> JevRuntimeSettings:
    # The decision record JevRuntimeSettings requires, plus the self-review
    # check and the fresh gate, which create the done-machinery children.
    return JevRuntimeSettings(
        preflight=preflight,
        decision=DecisionModelConfig(
            mode=DecisionModelMode.VIDBYTE_MANAGED, api_key=VIDBYTE_KEY
        ),
        continual=JevContinualSettings(
            checks=(JevDoneCheck.SELF_REVIEW,), gate=JevContinuationGate.FRESH
        ),
    )


def _machinery(settings: JevAgentSettings) -> JevAgent:
    return JevAgent(
        settings,
        _runtime(JevPreflightPreset.CLARITY, JevPreflightPreset.RUN_STATE_RELATION),
    )


_ASSIGNMENT = JevSwarmAssignment(
    id="A1",
    name="Rename",
    objective=TASK,
    inputs="The users table schema.",
    deliverable="One migration.",
    boundaries="Only the users table.",
    verification="Run the migration tests.",
)
# Spec INV-15: every agent that runs on JevAgent's own model, as production builds it.
CHILDREN: dict[str, Callable[[JevAgentSettings], Any]] = {
    "main": lambda settings: JevAgent(settings),
    "fresh_continuation": lambda settings: _machinery(
        settings
    ).continuation.fresh_agent_factory(),
    "run_state_relation": lambda settings: _machinery(settings).run_state,
    "run_state": lambda settings: JevRunState(settings, _runtime(), JevResponse()),
    "handoff": lambda settings: _machinery(settings).run_state.handoff_writer,
    "reviewer": lambda settings: _machinery(settings).run_state.reviewer,
    "clarification": lambda settings: _machinery(settings).preflight.clarification,
    "bulk_worker": lambda settings: JevBulkWorker(settings, (), 1, TASK).agent,
    "clone": lambda settings: JevCloneAgent(settings, 1),
    "swarm": lambda settings: JevSwarmAgent(settings, _ASSIGNMENT),
}


def _one_request(monkeypatch: pytest.MonkeyPatch, agent: BaseAgent) -> dict[str, Any]:
    # Each Messages call fails, so a child sends exactly one request and stops.
    wire = Wire(fail={ANTHROPIC: 500}).install(monkeypatch)
    return first_request(wire, agent, TASK)["json_body"]


async def _delegate_to_database(
    self: object,
    *,
    request: JevDecisionRequest,
    transport: object,
    config: object = None,
) -> DecisionModelResponse:
    # Answers every question clearly and routes the run to the database specialist (the delegated path).
    answers = {
        question.name: _answer(question, 0.95, SPECIALIST)
        for question in request.questions
    }
    return DecisionModelResponse(
        provider=ModelProvider.TYPESAFE,
        model=JEV_DEFAULT_MODEL,
        answers=answers,
        raw={},
        usage={"input_tokens": 300, "output_tokens": 20},
    )


@pytest.mark.parametrize("label", list(CHILDREN))
def test_each_agent_on_jevs_model_sends_the_effort(
    label: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-9, INV-15, D-9: the main agent and its children copy the effort
    # as they copy temperature; a child built without it runs at the
    # vendor default. output_config.format, where a child has one, stays.
    unset = _one_request(monkeypatch, CHILDREN[label](_settings()))
    effort = _one_request(
        monkeypatch, CHILDREN[label](_settings(reasoning_effort=ReasoningEffort.LOW))
    )

    assert effort["output_config"] == {
        **unset.get("output_config", {}),
        "effort": "low",
    }
    assert set(effort) == set(unset) | {"output_config"}


def test_the_run_brief_writer_keeps_its_own_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-9, INV-15: the brief writer uses JevRunBriefSettings, so its
    # request is the one it sends without the effort.
    unset = _one_request(
        monkeypatch, JevRunBriefWriter(_settings(), JevRunBriefSettings())
    )
    effort = _one_request(
        monkeypatch,
        JevRunBriefWriter(
            _settings(reasoning_effort=ReasoningEffort.LOW), JevRunBriefSettings()
        ),
    )

    assert effort == unset


def test_jev_decision_calls_never_carry_the_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC-9, INV-15, NG-4: decisions go to the TypeSafe gateway, whose
    # allow-list has no effort; their bodies are unchanged by it.
    def decision_bodies(settings: JevAgentSettings) -> list[dict[str, Any]]:
        wire = Wire().install(monkeypatch)
        run_agent(JevAgent(settings, _runtime(JevPreflightPreset.CLARITY)), TASK)
        return [request["json_body"] for request in wire.decision_requests()]

    unset = decision_bodies(_settings())
    effort = decision_bodies(_settings(reasoning_effort=ReasoningEffort.LOW))

    assert unset, "the CLARITY gate made no decision call"
    assert effort == unset


@pytest.mark.parametrize("own", [None, "high"], ids=["no_effort", "own_effort"])
def test_a_specialist_runs_at_its_own_setting(
    own: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-9, EC-20, NG-5: a delegated run never enters JevAgent's loop, so
    # the specialist sends its own effort (or none), never Jev's low.
    options = {} if own is None else {"reasoning_effort": own}
    specialist = JevSpecialist(
        SPECIALIST,
        "Changes to the database schema and its migrations.",
        direct_agent("anthropic", MODEL, name=SPECIALIST, **options),
    )
    jev = JevAgent(
        _settings(reasoning_effort=ReasoningEffort.LOW, agents=(specialist,)),
        _runtime(),
    )
    wire = Wire().install(monkeypatch)

    with patch(RUN_DECISION, new=_delegate_to_database):
        run_agent(jev, "Add a migration for the users table.")

    sent = [
        request["json_body"]
        for request in wire.vendor_requests()
        if SPECIALIST_PROMPT in json.dumps(request["json_body"].get("system"))
    ]
    assert sent, wire.urls
    assert [body.get("output_config", {}).get("effort") for body in sent] == [
        own
    ] * len(sent)
    assert all("thinking" not in body for body in sent)
