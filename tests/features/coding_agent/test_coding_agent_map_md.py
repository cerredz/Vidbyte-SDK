"""FILE: tests/features/coding_agent/test_coding_agent_map_md.py

PURPOSE: Pin CodingAgent's MAP.md loading: the root folder's MAP.md reaches the model as the REPO_MAP section, after AGENTS.md and before the user message, capped at 32 KiB without splitting a character, and only when load_map is a real True.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real run loop with the offline scripted model from conftest.py; exercises MapMdLoader (vidbyte/agents/coding_context/map_md.py) and the shared RootFileLoader (root_file.py) it inherits from.
ARCHITECTURE NOTE: Assertions read the system string and the user prompt the scripted model actually received. The shared reading steps are also pinned, in more depth, by test_coding_agent_agents_md.py, which is the regression guard for the RootFileLoader refactor.
FUNCTION INVENTORY: test_map_md_is_shown_* and test_map_md_renders_after_agents_md (FR-8); test_missing_or_blank_* (FR-6); test_lowercase_* (FR-4); test_large_map_md_* (FR-5); test_map_md_directory_* (FR-7); test_load_map_false_* (FR-3); test_load_map_must_be_* (FR-2).
COMMON MODIFICATION PATTERNS: A case that applies to every root file belongs in test_coding_agent_agents_md.py; add one here only when MAP.md behaves differently.
WHAT NOT TO DO IN THIS FILE: 1. Do not monkeypatch the loader or the window; build real files under tmp_path. 2. Do not open sockets or use real keys.
KNOWN EDGE CASES: The truncation case builds a file whose 32,768th byte falls inside a three-byte character.
RELATED DOCS: docs/design/coding-agent-map-md.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_map_md.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.constants.coding import CODING_MAP_MD_MAX_BYTES
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError

SYSTEM_PROMPT = "You are a careful engineer. SYSTEM-PROMPT-MARKER."
USER_MESSAGE = "Fix the fetch tool. USER-MESSAGE-MARKER"
MAP = "# Map\n\n- vidbyte/tools/builtins/operations/fetch.py holds the fetch tool.\n"
MAP_LINE = "fetch.py holds the fetch tool."
RULES = "# Rules\n\nUse uv, not pip.\n"
MAP_HEADER = "### [coding:repo_map] Repository map (MAP.md)"
AGENTS_HEADER = "### [coding:agents_md] Repository instructions (AGENTS.md)"
ZONE_HEADER = "## Context Window Primitives"
OFFLINE_MODEL = {"provider": "openai", "model_name": "gpt-4.1-mini"}
FORTY_KIB = 40 * 1024


class PromptRecorder:
    """Wraps a scripted runner and also records the user prompt it is given."""

    def __init__(self, runner: Any) -> None:
        self._runner = runner
        self.prompts: list[str] = []

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self._runner.requests

    def run(self, prompt: str, **kwargs: Any) -> Any:
        self.prompts.append(prompt)
        return self._runner.run(prompt, **kwargs)


def _agent(coding_agent_cls: type, root_dir: Path, **options: object) -> Any:
    # Builds a CodingAgent with fixed name, prompt, and offline model identity.
    return coding_agent_cls(name="coder", system_prompt=SYSTEM_PROMPT, root_dir=root_dir, **OFFLINE_MODEL, **options)


def _first_request(agent: BaseAgent, script_model: type) -> tuple[str, str]:
    # Runs one turn that ends at once and returns the system string and the user prompt the model received.
    recorder = PromptRecorder(script_model([], final_answer="done"))
    bind_test_runner(agent, recorder)
    agent.run(USER_MESSAGE)
    return recorder.requests[0]["system"], recorder.prompts[0]


def _write(path: Path, text: str) -> None:
    # Writes UTF-8 bytes exactly, so Windows text mode never adds carriage returns.
    path.write_bytes(text.encode("utf-8"))


def test_map_md_is_shown_after_the_system_prompt_and_before_the_user_message(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-8: the map reaches the model once, between the system prompt and the user message, with its source path.
    _write(tmp_path / "MAP.md", MAP)

    system, prompt = _first_request(_agent(coding_agent_cls, tmp_path), script_model)

    assert system.index(SYSTEM_PROMPT) < system.index(MAP_HEADER) < system.index(MAP.strip())
    assert f"Source: {tmp_path.resolve() / 'MAP.md'}" in system
    assert system.count(MAP_LINE) == 1
    assert prompt == USER_MESSAGE


def test_map_md_renders_after_agents_md(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-8 hidden failure: with both files present, the rules come first and the map second, each once.
    _write(tmp_path / "AGENTS.md", RULES)
    _write(tmp_path / "MAP.md", MAP)

    system, _prompt = _first_request(_agent(coding_agent_cls, tmp_path), script_model)

    assert system.index(SYSTEM_PROMPT) < system.index(AGENTS_HEADER) < system.index("Use uv, not pip.") < system.index(MAP_HEADER) < system.index(MAP_LINE)
    assert system.count(MAP_LINE) == 1
    assert system.count("Use uv, not pip.") == 1


@pytest.mark.parametrize("raw", [None, b"", b"   \n\t\r\n"], ids=["missing", "empty", "whitespace"])
def test_missing_or_blank_map_md_adds_no_section(coding_agent_cls, script_model, tmp_path, raw) -> None:
    # FR-6 edge: no file, or a file with nothing to say, adds no section and no primitives zone.
    if raw is not None:
        (tmp_path / "MAP.md").write_bytes(raw)

    agent = _agent(coding_agent_cls, tmp_path)
    system, _prompt = _first_request(agent, script_model)

    assert agent.context_manager is None
    assert ZONE_HEADER not in system


def test_lowercase_map_md_is_loaded_when_the_exact_name_is_absent(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-4: the user writes the file name as map.md; it is found under its real name on every platform.
    _write(tmp_path / "map.md", "Lowercase map.\n")

    system, _prompt = _first_request(_agent(coding_agent_cls, tmp_path), script_model)

    assert "### [coding:repo_map] Repository map (map.md)" in system
    assert "Lowercase map." in system


def test_large_map_md_is_cut_at_the_cap_without_splitting_a_character(coding_agent_cls, tmp_path) -> None:
    # FR-5 silent failure: a 40 KiB map whose cap falls inside a character shows only whole characters and a MAP.md read_lines hint.
    cap = CODING_MAP_MD_MAX_BYTES
    head = (("m" * 63 + "\n") * (cap // 64))[: cap - 1]
    straddler = "€"
    tail = "n" * (FORTY_KIB - len(head) - len(straddler.encode("utf-8")))
    (tmp_path / "MAP.md").write_bytes((head + straddler + tail).encode("utf-8"))

    item = _agent(coding_agent_cls, tmp_path).context_manager.get_by_id(CodingContextSection.REPO_MAP.value)

    note = f'[MAP.md was truncated at {cap - 1} of {FORTY_KIB} bytes. Read the rest with the read_lines tool (path "MAP.md"), starting at line 512.]'
    assert item.content == f"{head}\n\n{note}"


def test_map_md_directory_fails_construction_naming_the_path(coding_agent_cls, tmp_path) -> None:
    # FR-7: a present-but-broken MAP.md fails loudly instead of being skipped.
    broken = tmp_path / "MAP.md"
    broken.mkdir()

    with pytest.raises(ConfigurationError) as raised:
        _agent(coding_agent_cls, tmp_path)

    assert str(broken.resolve()) in str(raised.value)
    assert raised.value.details["path"] == str(broken.resolve())


def test_load_map_false_never_touches_the_file(coding_agent_cls, tmp_path) -> None:
    # FR-3: a MAP.md that would fail construction is never looked at when loading is off.
    (tmp_path / "MAP.md").mkdir()

    agent = _agent(coding_agent_cls, tmp_path, load_map=False)

    assert agent.context_manager is None


@pytest.mark.parametrize("bad", ["yes", 1, None], ids=["yes", "one", "none"])
def test_load_map_must_be_a_real_bool(coding_agent_cls, tmp_path, bad) -> None:
    # FR-2 hidden assumption: a truthy stand-in never switches loading on or off.
    with pytest.raises(ConfigurationError, match="load_map") as raised:
        _agent(coding_agent_cls, tmp_path, load_map=bad)

    assert raised.value.details["parameter"] == "load_map"
