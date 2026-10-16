"""FILE: tests/test_lib_config_loader_blank_values.py

PURPOSE:
    Regression tests for the descriptor loader exported from vidbyte.lib.config: a text
    field left blank in YAML (`key:`, `key: ~`, `key: null`) is read exactly as if the key
    were omitted, never as the four-character text "None". A blank system_prompt is then
    refused by the descriptor's own non-empty check, and a blank optional text field loads
    as "".

ROLE IN CODEBASE:
    Exercises YamlLoader._text and the text-field reads in YamlLoader._construct_base_agent
    in vidbyte/lib/config/loader.py through the public load_agent entry point.

ARCHITECTURE NOTE:
    Each test writes a small agent YAML into pytest's tmp_path and loads it, so the real
    parse, dispatch, and AgentDescriptor validation path runs. No model calls.

COMMON MODIFICATION PATTERNS:
    Add a case here when the loader reads a new text field from YAML, so a blank value
    keeps behaving like an omitted key.

KNOWN EDGE CASES:
    YAML parses a blank value, `~`, and `null` all as None, and dict.get returns its
    default only for an absent key, so str() of a present-but-blank key used to yield
    "None".

RELATED DOCS:
    tests/test_lib_config_loader_output_contracts.py covers the same loader's loop fields.

TESTS:
    python -m pytest tests/test_lib_config_loader_blank_values.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vidbyte.lib.config import YamlLoader
from vidbyte.lib.errors import ConfigurationError

BASE = "name: support-agent\nsystem_prompt: Help customers.\n"


def _load(tmp_path: Path, text: str):
    # Writes one agent YAML into the temporary folder and loads it through the descriptor loader.
    path = tmp_path / "agent.yaml"
    path.write_text(text, encoding="utf-8")
    return YamlLoader().load_agent(path)


@pytest.mark.parametrize("blank", ["", " ~", " null"])
def test_blank_system_prompt_is_refused_not_loaded_as_none(tmp_path: Path, blank: str) -> None:
    with pytest.raises(ConfigurationError, match="Agent system_prompt must be a non-empty string."):
        _load(tmp_path, f"name: support-agent\nsystem_prompt:{blank}\n")


def test_blank_description_loads_as_empty(tmp_path: Path) -> None:
    descriptor = _load(tmp_path, BASE + "description:\n")
    assert descriptor.description == ""
    assert descriptor.system_prompt == "Help customers."


def test_blank_agent_metadata_use_cases_loads_as_empty(tmp_path: Path) -> None:
    descriptor = _load(
        tmp_path,
        BASE + "agent_metadata:\n  name: support\n  description: Answers support questions.\n  use_cases:\n",
    )
    assert descriptor.agent_metadata.use_cases == ""
    assert descriptor.agent_metadata.name == "support"
    assert descriptor.agent_metadata.description == "Answers support questions."
