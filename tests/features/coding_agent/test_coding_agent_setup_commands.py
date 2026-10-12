"""FILE: tests/features/coding_agent/test_coding_agent_setup_commands.py

PURPOSE: Pin CodingAgent's setup commands: they run once, in order, in root_dir while the agent is built, the first failure stops the run, and a short pass/fail note reaches the model after the earlier sections and before the user message, with only a capped tail of the failed command's output.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real run loop with the offline scripted model from conftest.py; the commands run in real bash (BashTool.find_bash), and the no-bash case patches that lookup.
ARCHITECTURE NOTE: Assertions read the system string the scripted model actually received, so a section that is built but never rendered fails here. Marker files prove whether a command really ran. PromptRecorder keeps the user prompt, which the conftest runner receives positionally and does not record.
FUNCTION INVENTORY: test_two_passing_* (order and placement); test_first_failure_* (stop at the first failure); test_a_command_that_times_out_* (time limit); test_commands_run_in_root_dir_* (cwd); test_without_bash_* (no bash); test_empty_setup_commands_* (default off); test_invalid_setup_commands_* (validation); test_a_huge_failing_output_* (capped tail).
COMMON MODIFICATION PATTERNS: A new outcome line adds one test here that asserts on the request the model receives.
WHAT NOT TO DO IN THIS FILE: 1. Do not monkeypatch the loader itself; run real commands under tmp_path. 2. Do not open sockets or use real keys. 3. Do not assert private CodingAgent attributes.
KNOWN EDGE CASES: Real-bash tests are skipped when BashTool.find_bash() finds none (Windows without Git for Windows). On Windows a timeout kills only Git's launcher, so the timed-out command uses a short sleep that ends on its own.
RELATED DOCS: docs/design/coding-agent-setup-commands.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_setup_commands.py
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.base import BaseAgent
from vidbyte.lib.constants.coding import CODING_SETUP_OUTPUT_TAIL_BYTES, CODING_SETUP_OUTPUT_TAIL_LINES
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.builtins.bash import BashTool

SYSTEM_PROMPT = "You are a careful engineer. SYSTEM-PROMPT-MARKER."
USER_MESSAGE = "Fix the failing test. USER-MESSAGE-MARKER"
AGENTS_HEADER = "### [coding:agents_md]"
SETUP_HEADER = "### [coding:setup_results] Setup command results"
NOTES_HEADER = "### [coding:progress_notes]"
ZONE_HEADER = "## Context Window Primitives"
OFFLINE_MODEL = {"provider": "openai", "model_name": "gpt-4.1-mini"}

needs_bash = pytest.mark.skipif(BashTool.find_bash() is None, reason="no bash on this host (Windows needs Git for Windows)")


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


def _agent(coding_agent_cls: type, root_dir: str | Path, **options: object) -> Any:
    # Builds a CodingAgent with fixed name, prompt, and offline model identity.
    return coding_agent_cls(name="coder", system_prompt=SYSTEM_PROMPT, root_dir=root_dir, **OFFLINE_MODEL, **options)


def _first_request(agent: BaseAgent, script_model: type) -> tuple[str, str]:
    # Runs one turn that ends at once and returns the system string and the user prompt the model received.
    recorder = PromptRecorder(script_model([], final_answer="done"))
    bind_test_runner(agent, recorder)
    agent.run(USER_MESSAGE)
    return recorder.requests[0]["system"], recorder.prompts[0]


def _shown(agent: BaseAgent) -> str:
    # The setup section text the agent placed, read through ContextManager's public API.
    item = agent.context_manager.get_by_id(CodingContextSection.SETUP_RESULTS.value)
    assert item is not None
    return item.content


def _forbid_processes(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    # Records any attempt to start a process, so a test can prove that none was started.
    started: list[object] = []

    def refuse(*args: object, **kwargs: object) -> None:
        started.append(args)
        raise AssertionError("no setup command should start")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    return started


@needs_bash
def test_two_passing_commands_show_two_passed_lines_between_the_earlier_sections_and_the_user_message(coding_agent_cls, script_model, tmp_path) -> None:
    # Both commands run, in order, and the model sees one passed line each, after AGENTS.md, before the progress notes, and before the user message.
    (tmp_path / "AGENTS.md").write_bytes(b"# Rules\nUse uv.\n")

    agent = _agent(coding_agent_cls, tmp_path, setup_commands=("echo one > one.txt", "cat one.txt > two.txt"))
    system, prompt = _first_request(agent, script_model)

    assert (tmp_path / "two.txt").read_text(encoding="utf-8").strip() == "one"
    assert system.index(SYSTEM_PROMPT) < system.index(AGENTS_HEADER) < system.index(SETUP_HEADER) < system.index(NOTES_HEADER)
    assert f"These commands ran in {tmp_path.resolve()} before this conversation started:" in system
    assert "1. `echo one > one.txt`: passed (exit 0, " in system
    assert "2. `cat one.txt > two.txt`: passed (exit 0, " in system
    assert "FAILED" not in system
    assert prompt == USER_MESSAGE


@needs_bash
def test_first_failure_shows_its_exit_code_and_tail_and_never_runs_the_next_command(coding_agent_cls, tmp_path) -> None:
    # Silent failure: a command after a failure must not run, and the failure must be visible with its output.
    agent = _agent(coding_agent_cls, tmp_path, setup_commands=["echo ModuleNotFoundError: no module named foo; exit 3", "touch marker.txt"])
    shown = _shown(agent)

    assert "1. `echo ModuleNotFoundError: no module named foo; exit 3`: FAILED (exit 3, " in shown
    assert "Last lines of its output:\n   ModuleNotFoundError: no module named foo" in shown
    assert "2. `touch marker.txt`: not run, because an earlier command failed" in shown
    assert not (tmp_path / "marker.txt").exists()


@needs_bash
def test_a_command_that_times_out_is_marked_timed_out_and_nothing_raises(coding_agent_cls, bash_module, tmp_path, monkeypatch) -> None:
    # Hidden failure: a command that never ends must not hang construction; it is stopped at the bash tool's limit.
    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", 0.5)

    started = time.monotonic()
    agent = _agent(coding_agent_cls, tmp_path, setup_commands=["echo starting; sleep 5", "touch marker.txt"])
    elapsed = time.monotonic() - started
    shown = _shown(agent)

    assert elapsed < 4.5
    assert "1. `echo starting; sleep 5`: FAILED (timed out after 0.5 s). Last lines of its output:\n   starting" in shown
    assert "2. `touch marker.txt`: not run, because an earlier command failed" in shown
    assert not (tmp_path / "marker.txt").exists()


@needs_bash
def test_commands_run_in_root_dir_even_when_the_process_cwd_is_elsewhere(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # Hidden assumption: the process working directory is not the root folder.
    root = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    root.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    agent = _agent(coding_agent_cls, "../repo", setup_commands=["touch here.txt"])

    assert "passed" in _shown(agent)
    assert (root / "here.txt").exists()
    assert not (elsewhere / "here.txt").exists()


def test_without_bash_the_section_says_so_and_nothing_runs(coding_agent_cls, script_model, tmp_path, monkeypatch) -> None:
    # Hidden assumption: bash is installed. Without it, nothing starts and the model is told how to fix it.
    monkeypatch.setattr(BashTool, "find_bash", staticmethod(lambda: None))
    started = _forbid_processes(monkeypatch)

    agent = _agent(coding_agent_cls, tmp_path, setup_commands=["uv sync", "npm ci"])
    system, _prompt = _first_request(agent, script_model)

    assert started == []
    assert "but none of them ran. bash was not found. Install " in system
    assert "1. `uv sync`: not run\n2. `npm ci`: not run" in system


def test_empty_setup_commands_add_no_section_and_start_no_process(coding_agent_cls, script_model, tmp_path, monkeypatch) -> None:
    # Edge case: the default runs nothing, so the request is what it was before this feature.
    started = _forbid_processes(monkeypatch)

    agent = _agent(coding_agent_cls, tmp_path, progress_notes=False)
    system, _prompt = _first_request(agent, script_model)

    assert started == []
    assert agent.context_manager is None
    assert ZONE_HEADER not in system


@pytest.mark.parametrize("setup_commands", ["uv sync", None, ["uv sync", 3], ["uv sync", "   "]], ids=["bare-string", "none", "non-str-item", "blank-item"])
def test_invalid_setup_commands_fail_naming_the_field(coding_agent_cls, tmp_path, monkeypatch, setup_commands) -> None:
    # Hidden assumption: a bare string would otherwise run one character at a time; bad input fails before anything runs.
    started = _forbid_processes(monkeypatch)

    with pytest.raises(ConfigurationError, match="setup_commands"):
        _agent(coding_agent_cls, tmp_path, setup_commands=setup_commands)

    assert started == []


@needs_bash
def test_a_huge_failing_output_shows_only_a_capped_tail(coding_agent_cls, tmp_path) -> None:
    # Silent failure: a huge output must not fill the model's context; only its last lines are shown.
    many_lines = _shown(_agent(coding_agent_cls, tmp_path, setup_commands=["for i in $(seq 1 5000); do echo row-$i; done; exit 1"]))
    one_line = _shown(_agent(coding_agent_cls, tmp_path, setup_commands=["head -c 100000 /dev/zero | tr '\\0' x; exit 1"]))

    shown_rows = [line for line in many_lines.splitlines() if line.startswith("   row-")]
    assert len(shown_rows) == CODING_SETUP_OUTPUT_TAIL_LINES
    assert shown_rows[-1] == "   row-5000"
    assert "   row-4970" not in shown_rows
    x_runs = [len(line.strip()) for line in one_line.splitlines() if line.strip() and set(line.strip()) == {"x"}]
    assert x_runs and max(x_runs) <= CODING_SETUP_OUTPUT_TAIL_BYTES
