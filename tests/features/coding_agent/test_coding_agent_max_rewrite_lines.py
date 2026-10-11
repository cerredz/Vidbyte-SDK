"""FILE: tests/features/coding_agent/test_coding_agent_max_rewrite_lines.py

PURPOSE: Prove that CodingAgent's max_rewrite_lines reaches write_text: by default (300) the model gets a refusal for replacing a 301-line file and the run goes on, None turns the limit off, and a bad value fails at construction naming the keyword.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real tool loop with the offline scripted model from conftest.py; the file tools are real.
ARCHITECTURE NOTE: The tool-level rules (line counting, the at-limit edge, replace_text, the spec sentence) are tested in tests/test_filesystem_tools.py (WriteTextOverwriteLimitTests); this module checks only the agent wiring.
FUNCTION INVENTORY: _write_text_description reads the write_text description the model was sent; test_default_limit_* (default 300 refused, run continues, model told the limit); test_none_* (limit off); test_invalid_* (ConfigurationError naming max_rewrite_lines).
COMMON MODIFICATION PATTERNS: Script one more tool call per scenario and assert on tool_call_states, the model-visible tool messages, and the bytes on disk.
WHAT NOT TO DO IN THIS FILE: Do not mock WriteTextTool or the runtime; the wiring through CodingAgentTools is what is under test.
KNOWN EDGE CASES: tool_call_states includes the final isDone call.
RELATED DOCS: docs/design/coding-agent-max-rewrite-lines.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_max_rewrite_lines.py
"""

from __future__ import annotations

import pytest

from tests.agent_test_support import build_test_agent
from vidbyte.lib.errors import ConfigurationError

BIG_FILE = b"line\n" * 301
REWRITE = ("write_text", {"path": "big.py", "content": "short\n"})


def _write_text_description(runner: object) -> str:
    # The write_text description the model was sent with its first request.
    return next(tool["function"]["description"] for tool in runner.requests[0]["tools"] if tool["function"]["name"] == "write_text")


@pytest.mark.asyncio
async def test_default_limit_refuses_a_301_line_rewrite_and_the_run_continues(coding_agent_cls, script_model, tmp_path) -> None:
    target = tmp_path / "big.py"
    target.write_bytes(BIG_FILE)
    runner = script_model([REWRITE], final_answer="used replace_text instead")
    agent = build_test_agent(name="coder", system_prompt="Edit files.", root_dir=tmp_path, runner=runner, agent_type=coding_agent_cls)

    reply = await agent.arun("Rewrite big.py.")

    # The model saw the refusal as a failed tool call, then finished normally.
    assert reply.content == "used replace_text instead"
    assert reply.metadata["tool_call_states"] == ("failed", "succeeded")
    [(tool_name, seen)] = runner.tool_messages()
    assert tool_name == "write_text"
    assert "301 lines" in seen and "300-line limit" in seen and "replace_text" in seen
    assert target.read_bytes() == BIG_FILE
    assert "300 lines" in _write_text_description(runner)


@pytest.mark.asyncio
async def test_none_turns_the_limit_off(coding_agent_cls, script_model, tmp_path) -> None:
    target = tmp_path / "big.py"
    target.write_bytes(BIG_FILE)
    runner = script_model([REWRITE], final_answer="rewrote it")
    agent = build_test_agent(name="coder", system_prompt="Edit files.", root_dir=tmp_path, max_rewrite_lines=None, runner=runner, agent_type=coding_agent_cls)

    reply = await agent.arun("Rewrite big.py.")

    assert reply.metadata["tool_call_states"] == ("succeeded", "succeeded")
    assert target.read_text(encoding="utf-8") == "short\n"
    assert "replace_text" not in _write_text_description(runner)


@pytest.mark.parametrize("bad", [0, -1, True, 2.5, "300"])
def test_invalid_max_rewrite_lines_fails_at_construction_naming_the_keyword(coding_agent_cls, tmp_path, bad) -> None:
    with pytest.raises(ConfigurationError, match="max_rewrite_lines"):
        coding_agent_cls(name="coder", system_prompt="Edit files.", root_dir=tmp_path, max_rewrite_lines=bad, provider="openai", model_name="gpt-4.1-mini")
