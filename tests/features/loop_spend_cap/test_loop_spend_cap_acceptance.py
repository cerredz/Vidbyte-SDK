"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_acceptance.py

PURPOSE: Run the spec's section 4 developer snippet exactly as written, against a
scripted Vidbyte gateway, and prove it prints the one line that matches the run: the
cap line when the spend reaches $0.50, the could-not-be-measured line when the call
reported no usage, and the finished line otherwise. Also prove the cap never reaches
the model's request.
ROLE IN CODEBASE: Acceptance tests for spec AC-1 and AC-21 (INV-16), end to end from
the root vidbyte import through the default AUTO text-model mode, the gateway
transport, the runtime loop and the usage ledger.
ARCHITECTURE NOTE: The only fake is HttpTransport.request, the seam
tests/features/sdk_model_usage/test_nested_usage_bill.py patches; the gateway decorator,
the OpenAI Responses parser, the agent, the runtime and the pricebook are production
code. The Vidbyte key is built at runtime from parts and every other provider key
variable is removed, so the snippet takes the gateway route. Expected dollar figures
are computed from the live pricebook at test time.
FUNCTION INVENTORY: GatewayWire answers every gateway call with one scripted Responses
body and records the request; test_the_developer_snippet_prints_the_line_that_matches_the_run;
test_the_cap_never_reaches_the_model.
COMMON MODIFICATION PATTERNS: When the spec's section 4 snippet changes, paste the new
text into SECTION_4_SNIPPET unchanged and update the three expected lines.
WHAT NOT TO DO IN THIS FILE: 1. Do not edit SECTION_4_SNIPPET to make it testable; it
must stay the spec's text. 2. Do not write a key-shaped literal. 3. Do not reach the
network.
KNOWN EDGE CASES: A response without a usage object is an unaccounted call, so a capped
run stops blind with cost_usd None and the snippet prints $0.0000 as its lower bound.
RELATED DOCS: docs/spec/loop-spend-cap/spec.md section 4, AC-1, AC-21, INV-16, section 13.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_acceptance.py
"""

from __future__ import annotations

import json
import os
import runpy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    PRICED_MODEL,
    capped_settings,
    reference_cost,
    text_response,
    usage,
    usage_costing_at_least,
)
from vidbyte import Agent, AgentLoopSettings
from vidbyte.lib.http import HttpResponse, HttpTransport

# Spec section 4, character for character.
SECTION_4_SNIPPET = """from vidbyte import Agent, AgentLoopSettings, AgentStopReason

cap = 0.50
agent = Agent(
    name="researcher",
    system_prompt="Answer directly.",
    provider="openai",
    model_name="gpt-5.4-mini",
    agent_loop_settings=AgentLoopSettings(max_spend_usd=cap),
)
reply = agent.run("Summarize the open issues in this repository.")

usage = agent.get_usage()            # vidbyte.UsageRollup for the whole call
spent = usage.cost_usd or 0.0        # USD the SDK measured for this run
if reply.metadata["stop_reason"] == AgentStopReason.MAX_SPEND.value:
    if reply.metadata["usage_rollup"].cost_measured:  # the ledger the cap read
        print(f"stopped at ${spent:.4f}: reached the ${cap:.2f} cap")
    else:
        print(f"stopped: spend could not be fully measured (at least ${spent:.4f})")
else:
    print(f"finished; spent ${spent:.4f}" + ("" if usage.cost_measured else " or more"))
"""


class GatewayWire:
    """Stands in for HttpTransport.request: answers each gateway call with one Responses body and keeps the request."""

    def __init__(self, usage_payload: Mapping[str, int] | None) -> None:
        self.usage_payload = usage_payload
        self.bodies: list[dict[str, Any]] = []

    @property
    def calls(self) -> int:
        return len(self.bodies)

    async def __call__(
        self, *, json_body: dict[str, Any] | None = None, **_: Any
    ) -> HttpResponse:
        # A callable instance is not a descriptor, so no transport argument arrives.
        self.bodies.append(dict(json_body or {}))
        body: dict[str, Any] = {
            "id": f"resp-{self.calls}",
            "object": "response",
            "model": PRICED_MODEL,
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Three issues are open."}
                    ],
                }
            ],
        }
        if self.usage_payload is not None:
            body["usage"] = dict(self.usage_payload)
        return HttpResponse(
            status_code=200,
            body=json.dumps(body),
            headers={"content-type": "application/json"},
        )


def _offline_gateway(monkeypatch: pytest.MonkeyPatch, wire: GatewayWire) -> None:
    # Only the Vidbyte key is present, built at runtime, so AUTO mode takes the gateway route the wire answers.
    for name in list(os.environ):
        if name.endswith("_API_KEY"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VIDBYTE_API_KEY", "vb_live_" + "a" * 32)
    monkeypatch.setattr(HttpTransport, "request", wire)


@pytest.mark.parametrize("case", ["cap", "blind", "finished"])
def test_the_developer_snippet_prints_the_line_that_matches_the_run(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    # AC-1: the snippet runs as written and its one printed line tells the developer what happened.
    usage_payload = {
        "cap": usage_costing_at_least(0.5, output_tokens=10),
        "blind": None,
        "finished": usage(1_000, 10),
    }[case]
    spent = (
        0.0
        if usage_payload is None
        else reference_cost(text_response("", usage=usage_payload))
    )
    expected = {
        "cap": f"stopped at ${spent:.4f}: reached the $0.50 cap",
        "blind": f"stopped: spend could not be fully measured (at least ${spent:.4f})",
        "finished": f"finished; spent ${spent:.4f}",
    }[case]
    wire = GatewayWire(usage_payload)
    _offline_gateway(monkeypatch, wire)

    # Run the snippet as a script file, the way a developer would, in this process so the scripted wire answers it.
    snippet = tmp_path / "spec_section_4.py"
    snippet.write_text(SECTION_4_SNIPPET, encoding="utf-8")
    runpy.run_path(str(snippet), run_name="__main__")

    assert capsys.readouterr().out.splitlines() == [expected]
    assert wire.calls == 1
    if case == "cap":
        assert spent >= 0.5


def test_the_cap_never_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-21 and INV-16: the request a capped agent sends is the uncapped one; neither the field nor its value appears.
    wire = GatewayWire(usage(1_000, 10))
    _offline_gateway(monkeypatch, wire)

    for loop in (
        AgentLoopSettings(max_iterations=3),
        capped_settings(0.4321, max_iterations=3),
    ):
        Agent(
            name="researcher",
            system_prompt="Answer directly.",
            provider="openai",
            model_name=PRICED_MODEL,
            agent_loop_settings=loop,
        ).run("Summarize the open issues in this repository.")

    uncapped, capped = wire.bodies
    sent = json.dumps(capped)
    assert "max_spend" not in sent
    assert "0.4321" not in sent
    assert capped["body"]["instructions"] == uncapped["body"]["instructions"]
