"""FILE: tests/features/claude_code_agent/test_claude_code_agent.py

PURPOSE: Behaviour tests of a successful ClaudeCodeHarnessAgent run against the offline `claude` stand-in: structured output and the minted session, resume on the second arun from the same folder, per-run cost and its fallback, model selection, the exact command line (print mode, stream-json both ways, the isolation flags, --tools= with no tools, named tools pre-approved, model, effort, schema, session flag), the stdin message with images, the private instructions file, the environment the child sees, the workspace lifecycle, runs that never overlap, and the synchronous twin.
ROLE IN CODEBASE: The executable form of the success half of tests/features/claude_code_agent/FEATURE.md; the failure half is test_claude_code_failures.py.
ARCHITECTURE NOTE: Every run starts the real stand-in through PATH, so argv, stdin, cwd and environment are what a real `claude` would receive. Assertions read the stand-in's log (ClaudeSandbox.records) and the returned records.
FUNCTION INVENTORY: One test per behaviour; option() reads one parsed option from a log record.
COMMON MODIFICATION PATTERNS: A new flag gets one assertion in test_command_line_is_isolated_print_mode_with_stream_json or its own test.
KNOWN EDGE CASES: On Windows the stand-in is an .exe built from pip's launcher; the sandbox fixture skips when pip lacks it.
RELATED DOCS: tests/features/claude_code_agent/FEATURE.md; docs/design/claude-code-harness-agent.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/claude_code_agent/test_claude_code_agent.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.features.claude_code_agent.claude_code_support import (
    INSTRUCTIONS,
    SCHEMA,
    ClaudeSandbox,
    settings,
)
from vidbyte.agents.claude_code import (
    ClaudeCodeHarnessAgent,
    ClaudeCodeImage,
    ClaudeCodeRunInput,
    ClaudeCodeUsage,
)
from vidbyte.lib.errors import ConfigurationError

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")


def option(record: dict[str, Any], name: str) -> Any:
    return record["options"].get(name)


@pytest.mark.asyncio
async def test_first_run_returns_structured_output_and_starts_a_session(sandbox: ClaudeSandbox) -> None:
    agent = ClaudeCodeHarnessAgent(settings(output_schema=SCHEMA, model="haiku"))
    assert agent.session_id is None

    result = await agent.arun(ClaudeCodeRunInput(prompt="Suggest one idea."))

    assert result.output == {"answer": "turn 1", "first_prompt": "Suggest one idea."}
    assert json.loads(result.text) == result.output
    assert result.session_id == agent.session_id
    assert uuid.UUID(result.session_id).version == 4
    assert result.usage == ClaudeCodeUsage(input_tokens=2, output_tokens=53, cache_read_input_tokens=0, cache_creation_input_tokens=1126)
    assert result.cost_usd == pytest.approx(0.00025)
    assert result.session_cost_usd == pytest.approx(0.00025)
    assert result.model == "haiku"
    assert (result.num_turns, result.duration_ms) == (2, 975)
    (record,) = sandbox.records()
    assert option(record, "--session-id") == result.session_id
    assert option(record, "--resume") is None


@pytest.mark.asyncio
async def test_second_run_resumes_the_same_session_from_the_same_folder(sandbox: ClaudeSandbox) -> None:
    agent = ClaudeCodeHarnessAgent(settings(output_schema=SCHEMA))

    first = await agent.arun(ClaudeCodeRunInput(prompt="Remember PLUM."))
    second = await agent.arun(ClaudeCodeRunInput(prompt="Which word?"))

    # The stand-in only finds a session from the folder it was made in, so
    # the second answer remembering the first prompt proves both the resume
    # flag and the reused folder.
    assert second.session_id == first.session_id == agent.session_id
    assert second.output == {"answer": "turn 2", "first_prompt": "Remember PLUM."}
    started, resumed = sandbox.records()
    assert option(resumed, "--resume") == first.session_id
    assert option(resumed, "--session-id") is None
    assert resumed["cwd"] == started["cwd"]
    # The run's cost is this run alone; the session total keeps growing.
    assert second.cost_usd == pytest.approx(0.00025)
    assert second.session_cost_usd == pytest.approx(0.0005)


@pytest.mark.asyncio
async def test_cost_falls_back_to_the_growth_of_the_session_total(sandbox: ClaudeSandbox) -> None:
    # An older Claude Code without model_usage_since_last_result: the run's
    # cost is the session total minus the total the agent saw last.
    sandbox.scenario({"omit_run_usage": True, "cost": 0.001}, {"omit_run_usage": True, "cost": 0.004})
    agent = ClaudeCodeHarnessAgent(settings())

    first = await agent.arun("one")
    second = await agent.arun("two")

    assert first.cost_usd == pytest.approx(0.001)
    assert second.cost_usd == pytest.approx(0.004)
    assert second.session_cost_usd == pytest.approx(0.005)


@pytest.mark.asyncio
async def test_saved_session_resumes_from_its_folder_and_has_no_cost_baseline(sandbox: ClaudeSandbox) -> None:
    first_agent = ClaudeCodeHarnessAgent(settings(workspace=sandbox.workspace))
    saved = (await first_agent.arun("first turn")).session_id
    sandbox.scenario({"omit_run_usage": True})

    agent = ClaudeCodeHarnessAgent(settings(workspace=sandbox.workspace, session_id=saved))
    result = await agent.arun("continue")

    assert option(sandbox.records()[-1], "--resume") == saved
    assert result.text == "turn 2: continue"
    assert result.cost_usd is None
    assert result.session_cost_usd == pytest.approx(0.0005)


@pytest.mark.asyncio
async def test_command_line_is_isolated_print_mode_with_stream_json(sandbox: ClaudeSandbox) -> None:
    await ClaudeCodeHarnessAgent(settings(output_schema=SCHEMA)).arun("A private prompt that must stay off argv.")

    (record,) = sandbox.records()
    switches = {name for name, value in record["options"].items() if value is True}
    assert {"--print", "--verbose", "--safe-mode", "--strict-mcp-config", "--disable-slash-commands"} <= switches
    assert option(record, "--input-format") == option(record, "--output-format") == "stream-json"
    assert option(record, "--setting-sources") == ""
    assert option(record, "--json-schema") == json.dumps(SCHEMA, separators=(",", ":"))
    assert "--bare" not in record["argv"]
    # Every element is a known switch or a joined option: nothing positional,
    # and neither the prompt nor the instructions on the command line.
    assert record["unknown"] == []
    assert not any("private prompt" in element or "careful test advisor" in element for element in record["argv"])


@pytest.mark.asyncio
async def test_no_tools_turns_every_built_in_tool_off(sandbox: ClaudeSandbox) -> None:
    await ClaudeCodeHarnessAgent(settings()).arun("advise me")

    (record,) = sandbox.records()
    assert option(record, "--tools") == ""
    assert option(record, "--allowed-tools") is None


@pytest.mark.asyncio
async def test_named_tools_are_available_and_preapproved(sandbox: ClaudeSandbox) -> None:
    result = await ClaudeCodeHarnessAgent(settings(allowed_tools=("Read", "Grep", "Read"))).arun("look around")

    (record,) = sandbox.records()
    assert option(record, "--tools") == option(record, "--allowed-tools") == "Read,Grep"
    assert result.text == "turn 1: look around"


@pytest.mark.asyncio
async def test_model_and_effort_are_sent_only_when_chosen(sandbox: ClaudeSandbox) -> None:
    default = await ClaudeCodeHarnessAgent(settings()).arun("default")
    chosen = await ClaudeCodeHarnessAgent(settings(model="claude-opus-5-5", effort="max")).arun("chosen")

    plain, explicit = sandbox.records()
    assert option(plain, "--model") is None and option(plain, "--effort") is None
    assert default.model == "claude-fake-default"
    assert option(explicit, "--model") == "claude-opus-5-5"
    assert option(explicit, "--effort") == "max"
    assert chosen.model == "claude-opus-5-5"


@pytest.mark.asyncio
async def test_model_is_the_one_that_wrote_most_of_this_run(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"run_usage": {"claude-haiku-5-5": {"outputTokens": 12, "costUSD": 0.0001}, "claude-opus-5-5": {"outputTokens": 900, "costUSD": 0.02}}})

    result = await ClaudeCodeHarnessAgent(settings()).arun("which model?")

    assert result.model == "claude-opus-5-5"
    assert result.cost_usd == pytest.approx(0.0201)


@pytest.mark.asyncio
async def test_prompt_and_images_travel_as_one_stdin_message(sandbox: ClaudeSandbox) -> None:
    images = (ClaudeCodeImage(media_type="IMAGE/PNG", data_base64=PNG), ClaudeCodeImage(media_type="image/webp", data_base64=PNG))

    await ClaudeCodeHarnessAgent(settings()).arun(ClaudeCodeRunInput(prompt="Describe these.", images=images))

    (record,) = sandbox.records()
    assert record["stdin"].endswith("\n") and record["stdin"].count("\n") == 1
    message = record["message"]
    assert message["type"] == "user" and message["message"]["role"] == "user"
    first, second, text = message["message"]["content"]
    assert first == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}}
    assert second["source"]["media_type"] == "image/webp"
    assert text == {"type": "text", "text": "Describe these."}


@pytest.mark.asyncio
async def test_instructions_reach_claude_through_a_private_file_removed_after_the_run(sandbox: ClaudeSandbox) -> None:
    agent = ClaudeCodeHarnessAgent(settings(workspace=sandbox.workspace))

    await agent.arun("hello")

    (record,) = sandbox.records()
    assert record["instructions"] == INSTRUCTIONS
    folder = Path(record["instructions_folder"])
    assert folder.parent == sandbox.tmp
    assert not folder.exists()
    # The caller's folder is left exactly as it was.
    assert record["cwd_files"] == []
    assert list(sandbox.workspace.iterdir()) == []


@pytest.mark.asyncio
async def test_child_environment_drops_the_parent_session_and_keeps_the_config_dir(sandbox: ClaudeSandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-user-own-key-for-byok")

    await ClaudeCodeHarnessAgent(settings()).arun("hello")

    # The user's own key and config folder are the bring-your-own-key path,
    # so they pass through; every variable of a parent Claude Code session
    # (set by the sandbox) is left out.
    (record,) = sandbox.records()
    assert record["variables"] == ["ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR"]


@pytest.mark.asyncio
async def test_default_workspace_is_one_temp_folder_reused_then_removed_by_close(sandbox: ClaudeSandbox) -> None:
    agent = ClaudeCodeHarnessAgent(settings())
    assert agent.workspace is None

    await agent.arun("one")
    await agent.arun("two")

    first, second = sandbox.records()
    assert first["cwd"] == second["cwd"] == str(agent.workspace)
    assert agent.workspace is not None and agent.workspace.parent == sandbox.tmp
    assert agent.workspace.name.startswith("vidbyte-claude-code-")
    assert sandbox.leftovers() == [agent.workspace.name]

    folder = agent.workspace
    agent.close()
    assert not folder.exists()
    assert agent.session_id is None and agent.workspace is None


@pytest.mark.asyncio
async def test_close_keeps_a_caller_folder_and_its_session(sandbox: ClaudeSandbox) -> None:
    agent = ClaudeCodeHarnessAgent(settings(workspace=sandbox.workspace))
    result = await agent.arun("one")

    agent.close()

    assert sandbox.workspace.is_dir()
    assert agent.session_id == result.session_id


@pytest.mark.asyncio
async def test_runs_on_one_agent_never_overlap(sandbox: ClaudeSandbox) -> None:
    sandbox.scenario({"delay": 1.0})
    agent = ClaudeCodeHarnessAgent(settings())

    first, second = await asyncio.gather(agent.arun("one"), agent.arun("two"))

    # The second run started only after the first finished, and continued it.
    started, resumed = sandbox.records()
    assert resumed["started"] - started["started"] >= 1.0
    assert option(resumed, "--resume") == first.session_id == second.session_id


@pytest.mark.asyncio
async def test_a_plain_string_is_a_prompt(sandbox: ClaudeSandbox) -> None:
    result = await ClaudeCodeHarnessAgent(settings()).arun("just text")

    assert result.text == "turn 1: just text"
    assert result.output is None


def test_run_is_the_synchronous_twin(sandbox: ClaudeSandbox) -> None:
    result = ClaudeCodeHarnessAgent(settings()).run("from sync code")

    assert result.text == "turn 1: from sync code"


@pytest.mark.asyncio
async def test_run_refuses_a_running_event_loop(sandbox: ClaudeSandbox) -> None:
    with pytest.raises(ConfigurationError, match="await agent.arun"):
        ClaudeCodeHarnessAgent(settings()).run("inside a loop")
    assert sandbox.records() == []
