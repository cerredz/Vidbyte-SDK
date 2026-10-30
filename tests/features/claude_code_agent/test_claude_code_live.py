"""FILE: tests/features/claude_code_agent/test_claude_code_live.py

PURPOSE: One opt-in live test of ClaudeCodeHarnessAgent against the real Claude Code on this machine: two turns on one agent with a JSON schema, proving that the first run starts a session, the second resumes it and remembers the first turn, structured output arrives through --json-schema with every built-in tool off and the isolation flags on, the instructions file is read, and usage, per-run cost, session cost and model come back as observed.
ROLE IN CODEBASE: The end-to-end check that the offline stand-in (fake_claude.py) still matches the real program. It is skipped unless VIDBYTE_LIVE_CLAUDE_CODE=1, so the gate and remote CI never spend model calls.
ARCHITECTURE NOTE: ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN are removed from this process's environment for the test, so Claude Code uses the machine's own Claude login, as a Claude subscriber's would. The model defaults to the haiku alias (about $0.001 for both turns); VIDBYTE_LIVE_CLAUDE_CODE_MODEL overrides it.
COMMON MODIFICATION PATTERNS: Keep it to two cheap turns; a new behaviour belongs in the offline tests, with the live shape recorded in the design doc.
KNOWN EDGE CASES: It needs a signed-in Claude Code on PATH (`claude auth login`); without one it fails with NOT_AUTHENTICATED, which is itself the live check of that path. The agent's temporary folder is removed by close() at the end.
RELATED DOCS: docs/design/claude-code-harness-agent.md section 4
TESTS: VIDBYTE_LIVE_CLAUDE_CODE=1 PYTHONPATH=$(pwd) python -m pytest -q tests/features/claude_code_agent/test_claude_code_live.py
"""

from __future__ import annotations

import os

import pytest

from vidbyte.agents.claude_code import (
    ClaudeCodeHarnessAgent,
    ClaudeCodeHarnessAgentSettings,
)

LIVE = os.environ.get("VIDBYTE_LIVE_CLAUDE_CODE") == "1"
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}

pytestmark = pytest.mark.skipif(not LIVE, reason="set VIDBYTE_LIVE_CLAUDE_CODE=1 to run two real Claude Code turns on this machine's login")


@pytest.mark.asyncio
async def test_two_real_turns_share_one_isolated_session(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use this machine's Claude login, never a key from the environment.
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    agent = ClaudeCodeHarnessAgent(
        ClaudeCodeHarnessAgentSettings(
            name="live-check",
            instructions="You are a terse test assistant. Always answer through the structured output.",
            model=os.environ.get("VIDBYTE_LIVE_CLAUDE_CODE_MODEL", "haiku"),
            output_schema=SCHEMA,
            timeout_seconds=180.0,
        )
    )
    try:
        first = await agent.arun("Remember the codeword PLUM for later. For now set answer to the single word ok.")
        second = await agent.arun("What codeword did I ask you to remember? Put just the codeword in answer.")
        assert agent.workspace is not None and list(agent.workspace.iterdir()) == []
    finally:
        agent.close()

    assert first.output is not None and second.output is not None
    assert "plum" in second.output["answer"].lower()
    assert second.session_id == first.session_id
    assert first.usage.output_tokens > 0 and second.usage.output_tokens > 0
    assert first.model.startswith("claude-") and second.model.startswith("claude-")
    assert first.cost_usd is not None and first.cost_usd > 0
    assert second.cost_usd is not None and second.session_cost_usd is not None
    assert second.session_cost_usd > second.cost_usd
