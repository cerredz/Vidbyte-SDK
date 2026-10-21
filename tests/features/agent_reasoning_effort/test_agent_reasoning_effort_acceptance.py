"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_acceptance.py

PURPOSE: Run the spec's section 4 developer snippet exactly as written, with the three
provider keys in the environment (built at run time) and the HTTP seam scripted, and
prove what the spec says it does: the planner's Responses bodies carry
"reasoning": {"effort": "high"}, the gemini agent is refused before any request with
exactly the one printed line, and the JevAgent it builds sends
"output_config": {"effort": "low"} on its Messages calls.
ROLE IN CODEBASE: Acceptance test for spec AC-1, end to end from the root vidbyte
import through Agent, the construction guard, Runner, TextModelConfig, the OpenAI and
Anthropic adapters and JevAgent.
ARCHITECTURE NOTE: The snippet runs as a script file through runpy in this process, so
the scripted HttpTransport.request answers it; nothing else is faked. The snippet's own
globals hand back the jev agent, which the test then runs once.
FUNCTION INVENTORY: _offline_keys sets the three run-time keys and removes every other;
test_the_developer_snippet_sends_high_prints_one_refusal_and_builds_jev.
COMMON MODIFICATION PATTERNS: When the spec's section 4 snippet changes, paste the new
text into SECTION_4_SNIPPET unchanged and update EXPECTED_LINE from the spec's printed
output.
WHAT NOT TO DO IN THIS FILE: 1. Do not edit SECTION_4_SNIPPET to make it testable; it
must stay the spec's text. 2. Do not write a key-shaped literal. 3. Do not reach the
network.
KNOWN EDGE CASES: The snippet's JevAgent has no runtime settings, so it makes no
decision call and needs no Vidbyte key; every Messages request it sends is a
main-model call.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md section 4 and AC-1;
tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_acceptance.py
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    Wire,
    clear_provider_environment,
    provider_key,
    run_agent,
)

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import ReasoningEffort
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

# Spec section 4, character for character.
SECTION_4_SNIPPET = """import os

from vidbyte import Agent, ConfigurationError, JevAgent, JevAgentSettings, ReasoningEffort, TextModelMode

planner = Agent(
    name="planner",
    system_prompt="Plan database migrations.",
    provider="openai",
    model_name="gpt-5.6-sol",
    api_keys=[os.environ["OPENAI_API_KEY"]],
    model_mode=TextModelMode.DIRECT,
    reasoning_effort=ReasoningEffort.HIGH,
)
reply = planner.run("Plan a zero-downtime rename of users.email.")  # body carries "reasoning": {"effort": "high"}

try:
    Agent(name="fast", system_prompt="Answer briefly.", provider="gemini", model_name="gemini-3.5-flash",
          api_keys=[os.environ["GEMINI_API_KEY"]], model_mode=TextModelMode.DIRECT, reasoning_effort=ReasoningEffort.XHIGH)
except ConfigurationError as error:
    print(error)

jev = JevAgent(JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="anthropic", model_name="claude-opus-5-5",
                                api_keys=[os.environ["ANTHROPIC_API_KEY"]], model_mode=TextModelMode.DIRECT, reasoning_effort=ReasoningEffort.LOW))
"""
# Spec section 4 "Printed output (exactly one line)".
EXPECTED_LINE = "Agent fast sets reasoning_effort, but gemini:gemini-3.5-flash has no documented form for reasoning effort 'xhigh' (it supports minimal, low, medium, high)."
RESPONSES_URL = "https://api.openai.com/v1/responses"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _offline_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the three keys the snippet reads are present, each built at run time.
    clear_provider_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", provider_key("openai"))
    monkeypatch.setenv("GEMINI_API_KEY", provider_key("gemini"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", provider_key("anthropic"))


def test_the_developer_snippet_sends_high_prints_one_refusal_and_builds_jev(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    # AC-1: the snippet runs as written; its one printed line is the
    # section 4 text, and the refused agent sends nothing.
    _offline_keys(monkeypatch)
    wire = Wire().install(monkeypatch)
    snippet = tmp_path / "spec_section_4.py"
    snippet.write_text(SECTION_4_SNIPPET, encoding="utf-8")

    namespace = runpy.run_path(str(snippet), run_name="__main__")

    assert capsys.readouterr().out.splitlines() == [EXPECTED_LINE]
    assert namespace["ReasoningEffort"] is ReasoningEffort
    planner_bodies = [
        r["json_body"] for r in wire.requests if r["url"] == RESPONSES_URL
    ]
    assert planner_bodies, wire.urls
    assert [body.get("reasoning") for body in planner_bodies] == [
        {"effort": "high"}
    ] * len(planner_bodies)
    assert all(url == RESPONSES_URL for url in wire.urls), wire.urls

    # The jev agent constructs; each Messages call it sends carries the low effort.
    start = len(wire.requests)
    run_agent(namespace["jev"], "Rename users.email to users.email_address.")
    jev_bodies = [
        r["json_body"] for r in wire.requests[start:] if r["url"] == MESSAGES_URL
    ]
    assert jev_bodies, wire.urls[start:]
    assert [body.get("output_config", {}).get("effort") for body in jev_bodies] == [
        "low"
    ] * len(jev_bodies)
