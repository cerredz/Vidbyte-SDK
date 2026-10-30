"""FILE: tests/features/claude_code_agent/test_claude_code_records.py

PURPOSE: Validation tests of the Claude Code harness agent's records and settings: ClaudeCodeHarnessAgentSettings (name, instructions, model, output_schema, effort, allowed_tools, workspace, claude_bin, timeout_seconds, session_id), ClaudeCodeImage, ClaudeCodeRunInput, ClaudeCodeUsage and ClaudeCodeRunResult, each refusing a bad value with ConfigurationError at construction and converting the values the contract writes as text.
ROLE IN CODEBASE: Proves AGENTS.md principle 4 for this feature: invalid data fails where it enters, before any process starts.
ARCHITECTURE NOTE: Pure construction tests; nothing here starts a process, so no sandbox is used except for real folders.
FUNCTION INVENTORY: One test per rule.
COMMON MODIFICATION PATTERNS: A new settings field gets one accepting and one refusing case here.
KNOWN EDGE CASES: A relative workspace is resolved against the current folder at construction, so a later chdir cannot move it.
RELATED DOCS: tests/features/claude_code_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/claude_code_agent/test_claude_code_records.py
"""

from __future__ import annotations

import base64
import json
import math
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.features.claude_code_agent.claude_code_support import SCHEMA, settings
from vidbyte.agents.claude_code import (
    ClaudeCodeEffort,
    ClaudeCodeHarnessAgent,
    ClaudeCodeImage,
    ClaudeCodeRunInput,
    ClaudeCodeRunResult,
    ClaudeCodeUsage,
)
from vidbyte.lib.errors import ConfigurationError

PNG = base64.b64encode(b"png-bytes").decode("ascii")
USAGE = ClaudeCodeUsage(input_tokens=1, output_tokens=2, cache_read_input_tokens=3, cache_creation_input_tokens=4)


def test_contract_defaults() -> None:
    value = settings()
    assert (value.model, value.output_schema, value.effort, value.allowed_tools, value.workspace, value.claude_bin, value.session_id) == (None, None, None, (), None, None, None)
    assert settings(timeout_seconds=600.0).timeout_seconds == 600.0
    assert "careful test advisor" not in repr(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "two\nlines"),
        ("instructions", "   "),
        ("instructions", None),
        ("model", ""),
        ("model", "has space"),
        ("effort", "extreme"),
        ("effort", 3),
        ("allowed_tools", "Read"),
        ("allowed_tools", ("Bash(git *)",)),
        ("allowed_tools", ("",)),
        ("timeout_seconds", 0),
        ("timeout_seconds", math.inf),
        ("timeout_seconds", 14401.0),
        ("timeout_seconds", True),
        ("session_id", "not-a-uuid"),
        ("output_schema", ["type", "object"]),
        ("output_schema", {"type": "array"}),
        ("output_schema", {"type": "object", "minimum": math.nan}),
        ("output_schema", {"type": "object", "default": object()}),
    ],
)
def test_bad_settings_are_refused(field: str, value: Any) -> None:
    with pytest.raises(ConfigurationError):
        settings(**{field: value})


def test_effort_text_becomes_the_enum_member() -> None:
    assert settings(effort="xhigh").effort is ClaudeCodeEffort.XHIGH
    assert settings(effort=ClaudeCodeEffort.LOW).effort is ClaudeCodeEffort.LOW
    assert [member.value for member in ClaudeCodeEffort] == ["low", "medium", "high", "xhigh", "max"]


def test_allowed_tools_accept_a_list_and_drop_repeats() -> None:
    assert settings(allowed_tools=["Read", "Grep", "Read"]).allowed_tools == ("Read", "Grep")


def test_schema_is_a_frozen_copy_sent_as_compact_json() -> None:
    schema: dict[str, Any] = json.loads(json.dumps(SCHEMA))
    value = settings(output_schema=schema)
    schema["properties"]["answer"]["type"] = "integer"

    assert value.output_schema is not None and value.output_schema["properties"]["answer"]["type"] == "string"
    assert value.output_schema_json == json.dumps(SCHEMA, separators=(",", ":"))
    with pytest.raises(TypeError):
        value.output_schema["type"] = "array"  # type: ignore[index]


def test_workspace_must_exist_and_is_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path)

    assert settings(workspace="work").workspace == (tmp_path / "work").resolve()
    with pytest.raises(ConfigurationError):
        settings(workspace=tmp_path / "missing")
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        settings(workspace=tmp_path / "file.txt")


def test_saved_session_needs_its_workspace(tmp_path: Path) -> None:
    saved = str(uuid.uuid4())
    with pytest.raises(ConfigurationError, match="workspace"):
        settings(session_id=saved)
    assert settings(session_id=saved, workspace=tmp_path).session_id == saved


def test_claude_bin_text_becomes_a_path() -> None:
    assert settings(claude_bin="tools/claude.exe").claude_bin == Path("tools/claude.exe")


def test_image_needs_a_media_type_and_real_base64() -> None:
    assert ClaudeCodeImage(media_type="image/png", data_base64=PNG).media_type == "image/png"
    with pytest.raises(ConfigurationError):
        ClaudeCodeImage(media_type="png", data_base64=PNG)
    with pytest.raises(ConfigurationError):
        ClaudeCodeImage(media_type="image/png", data_base64="not base64!")
    with pytest.raises(ConfigurationError):
        ClaudeCodeImage(media_type="image/png", data_base64="")
    assert PNG not in repr(ClaudeCodeImage(media_type="image/png", data_base64=PNG))


def test_run_input_needs_a_prompt_and_stores_images_as_a_tuple() -> None:
    image = ClaudeCodeImage(media_type="image/png", data_base64=PNG)
    assert ClaudeCodeRunInput(prompt="hi", images=[image]).images == (image,)  # type: ignore[arg-type]
    assert ClaudeCodeRunInput(prompt="hi").images == ()
    with pytest.raises(ConfigurationError):
        ClaudeCodeRunInput(prompt=" ")
    with pytest.raises(ConfigurationError):
        ClaudeCodeRunInput(prompt="hi", images=("image/png",))  # type: ignore[arg-type]


def test_usage_counts_are_whole_and_not_negative() -> None:
    assert USAGE.total_tokens == 10
    with pytest.raises(ConfigurationError):
        ClaudeCodeUsage(input_tokens=-1, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    with pytest.raises(ConfigurationError):
        ClaudeCodeUsage(input_tokens=1.5, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0)  # type: ignore[arg-type]


def test_run_result_is_validated() -> None:
    session = str(uuid.uuid4())
    result = ClaudeCodeRunResult(output={"a": 1}, text="{}", session_id=session, usage=USAGE, cost_usd=0.01, model="claude-haiku-5-5")
    assert (result.num_turns, result.duration_ms, result.session_cost_usd) == (0, 0, None)
    assert ClaudeCodeRunResult(output=None, text="", session_id=session, usage=USAGE, cost_usd=None, model="m").cost_usd is None
    with pytest.raises(ConfigurationError):
        ClaudeCodeRunResult(output=None, text="", session_id="nope", usage=USAGE, cost_usd=0.0, model="m")
    with pytest.raises(ConfigurationError):
        ClaudeCodeRunResult(output=None, text="", session_id=session, usage=USAGE, cost_usd=-1.0, model="m")
    with pytest.raises(ConfigurationError):
        ClaudeCodeRunResult(output=None, text="", session_id=session, usage=USAGE, cost_usd=0.0, model="")


def test_agent_needs_a_settings_object() -> None:
    with pytest.raises(ConfigurationError):
        ClaudeCodeHarnessAgent({"name": "x", "instructions": "y"})  # type: ignore[arg-type]
