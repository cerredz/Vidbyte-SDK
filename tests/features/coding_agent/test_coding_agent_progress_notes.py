"""FILE: tests/features/coding_agent/test_coding_agent_progress_notes.py

PURPOSE: Pin CodingAgent's progress notes: the agent's own <root>/.vidbyte/coding-agent/progress.md is created from a template when missing, never overwritten, hidden from git by a .vidbyte/coding-agent/.gitignore holding "*" without hiding other tools' files under .vidbyte, and shown as the last context section, so a second run sees what the first one wrote.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real run loop with the offline scripted model from conftest.py; covers vidbyte/agents/coding_context/progress_notes.py (ProgressNotesLoader) and the progress_notes switch on CodingAgentSettings.
ARCHITECTURE NOTE: Assertions read the system string and prompt the scripted model received, the files on disk, and git's own status, so a section that is never rendered or a notes file git can see fails here.
FUNCTION INVENTORY: test_fresh_root_* (FR-2, FR-4, FR-6); test_existing_notes_* and test_existing_gitignore_* (FR-3); test_git_status_* and test_sibling_tool_files_* (hidden failure); test_notes_written_in_one_run_* (the cross-run promise); test_root_that_cannot_be_written_* (FR-7); test_progress_notes_false_* (FR-8); test_progress_notes_must_be_* (FR-1); test_notes_over_the_cap_* (FR-5).
COMMON MODIFICATION PATTERNS: Change the template or texts in vidbyte/lib/constants/coding.py; these tests import them rather than repeating them.
WHAT NOT TO DO IN THIS FILE: 1. Do not monkeypatch the loader; build real files under tmp_path. The read-only case patches only Path.mkdir, so it runs on every platform. 2. Do not open sockets or use real keys.
KNOWN EDGE CASES: The git cases skip when git is not installed.
RELATED DOCS: docs/design/coding-agent-progress-notes.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_progress_notes.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.agent_test_support import bind_test_runner
from vidbyte.lib.constants.coding import (
    CODING_PROGRESS_NOTES_INSTRUCTION,
    CODING_PROGRESS_NOTES_MAX_BYTES,
    CODING_PROGRESS_NOTES_TEMPLATE,
    CODING_PROGRESS_NOTES_TRUNCATION_NOTE,
)
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError

SYSTEM_PROMPT = "You are a careful engineer. SYSTEM-PROMPT-MARKER."
USER_MESSAGE = "Migrate the next module. USER-MESSAGE-MARKER"
OFFLINE_MODEL = {"provider": "openai", "model_name": "gpt-4.1-mini"}
NOTES_HEADER = "### [coding:progress_notes] Progress notes (.vidbyte/coding-agent/progress.md)"
AGENTS_HEADER = "### [coding:agents_md] Repository instructions (AGENTS.md)"
OLD_NOTES = "# Progress notes\n\n## Done\nMigrated 3 of 5 modules.\n\n## Next\nauth.py\n"


def _agent(coding_agent_cls: type, root_dir: Path, **options: object) -> Any:
    # Builds a CodingAgent with fixed name, prompt, and offline model identity.
    return coding_agent_cls(name="coder", system_prompt=SYSTEM_PROMPT, root_dir=root_dir, **OFFLINE_MODEL, **options)


def _notes_shown(agent: Any) -> str:
    # The progress-notes section text the agent placed, read through ContextManager's public API.
    item = agent.context_manager.get_by_id(CodingContextSection.PROGRESS_NOTES.value)
    assert item is not None
    return item.content


def _notes_dir(root: Path) -> Path:
    return root / ".vidbyte" / "coding-agent"


def test_fresh_root_gets_both_files_and_the_template_renders_last_before_the_user_message(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-2 / FR-4 / FR-6: both files are created, and the template reaches the model after AGENTS.md, in the system string, not the prompt.
    (tmp_path / "AGENTS.md").write_bytes(b"Use uv, not pip.\n")
    runner = script_model([], final_answer="done")
    prompts: list[str] = []
    original_run = runner.run

    def recording_run(prompt: str, **kwargs: Any) -> Any:
        prompts.append(prompt)
        return original_run(prompt, **kwargs)

    runner.run = recording_run
    agent = bind_test_runner(_agent(coding_agent_cls, tmp_path), runner)
    agent.run(USER_MESSAGE)
    system = runner.requests[0]["system"]

    assert (_notes_dir(tmp_path) / "progress.md").read_bytes() == CODING_PROGRESS_NOTES_TEMPLATE.encode("utf-8")
    assert (_notes_dir(tmp_path) / ".gitignore").read_bytes() == b"*\n"
    assert _notes_shown(agent) == f"{CODING_PROGRESS_NOTES_INSTRUCTION}\n\n{CODING_PROGRESS_NOTES_TEMPLATE}"
    assert system.index(SYSTEM_PROMPT) < system.index(AGENTS_HEADER) < system.index(NOTES_HEADER) < system.index("## Decisions")
    assert prompts == [USER_MESSAGE]


def test_existing_notes_are_shown_unchanged_and_never_overwritten(coding_agent_cls, tmp_path) -> None:
    # FR-3 silent failure: the last run's notes must survive construction byte for byte.
    notes = _notes_dir(tmp_path) / "progress.md"
    notes.parent.mkdir(parents=True)
    notes.write_bytes(OLD_NOTES.encode("utf-8"))

    shown = _notes_shown(_agent(coding_agent_cls, tmp_path))

    assert shown == f"{CODING_PROGRESS_NOTES_INSTRUCTION}\n\n{OLD_NOTES}"
    assert notes.read_bytes() == OLD_NOTES.encode("utf-8")


def test_existing_gitignore_in_the_notes_folder_is_not_overwritten(coding_agent_cls, tmp_path) -> None:
    # FR-3 silent failure: a .vidbyte/coding-agent/.gitignore the user changed is left as it is.
    ignore = _notes_dir(tmp_path) / ".gitignore"
    ignore.parent.mkdir(parents=True)
    ignore.write_bytes(b"progress.md\n")

    _agent(coding_agent_cls, tmp_path)

    assert ignore.read_bytes() == b"progress.md\n"
    assert (_notes_dir(tmp_path) / "progress.md").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_status_shows_nothing_from_the_notes_folder(coding_agent_cls, tmp_path) -> None:
    # Hidden failure: the notes are never seen by git, and the user's own root .gitignore is never created or touched.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    _agent(coding_agent_cls, tmp_path)
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=tmp_path, check=True, capture_output=True, text=True)

    assert (_notes_dir(tmp_path) / "progress.md").exists()
    assert status.stdout == ""
    assert not (tmp_path / ".gitignore").exists()
    assert not (tmp_path / ".vidbyte" / ".gitignore").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_sibling_tool_files_under_vidbyte_stay_visible_to_git(coding_agent_cls, tmp_path) -> None:
    # Hidden failure: vidbyte-cli's task board writes .vidbyte/task-board/; only the notes folder may be ignored, never its siblings.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    board = tmp_path / ".vidbyte" / "task-board"
    board.mkdir(parents=True)
    (board / "x.json").write_bytes(b"{}\n")

    _agent(coding_agent_cls, tmp_path)
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=tmp_path, check=True, capture_output=True, text=True)

    assert status.stdout.splitlines() == ["?? .vidbyte/task-board/x.json"]


def test_notes_written_in_one_run_are_shown_to_the_next_agent(coding_agent_cls, script_model, tmp_path) -> None:
    # The cross-run promise: the model updates the notes with replace_text, and a new agent on the same root shows the update.
    edit = ("replace_text", {"path": ".vidbyte/coding-agent/progress.md", "search": "## Next\n", "replacement": "## Next\nauth.py is next.\n"})
    first = bind_test_runner(_agent(coding_agent_cls, tmp_path), script_model([edit], final_answer="noted"))

    reply = first.run(USER_MESSAGE)
    second_shown = _notes_shown(_agent(coding_agent_cls, tmp_path))

    assert reply.metadata["tool_call_states"] == ("succeeded", "succeeded")
    assert "auth.py is next." in second_shown
    assert "auth.py is next." not in _notes_shown(first)


def test_root_that_cannot_be_written_gives_no_section_and_does_not_raise(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # FR-7 hidden failure: a read-only checkout still builds an agent; notes are on by default.
    def refuse(self: Path, *args: Any, **kwargs: Any) -> None:
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "mkdir", refuse)
    agent = _agent(coding_agent_cls, tmp_path, load_environment=False)

    assert agent.context_manager is None
    assert not _notes_dir(tmp_path).exists()


def test_progress_notes_false_creates_nothing_and_adds_no_section(coding_agent_cls, tmp_path) -> None:
    # FR-8 edge: the switch off means no files and no section.
    agent = _agent(coding_agent_cls, tmp_path, progress_notes=False, load_environment=False)

    assert agent.context_manager is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", ["yes", 1, None], ids=["yes", "one", "none"])
def test_progress_notes_must_be_a_real_bool(coding_agent_cls, tmp_path, bad) -> None:
    # FR-1 hidden assumption: a truthy stand-in never switches notes on or off.
    with pytest.raises(ConfigurationError, match="progress_notes") as raised:
        _agent(coding_agent_cls, tmp_path, progress_notes=bad)

    assert raised.value.details["parameter"] == "progress_notes"
    assert not _notes_dir(tmp_path).exists()


def test_notes_over_the_cap_are_cut_without_garbage_and_the_file_is_unchanged(coding_agent_cls, tmp_path) -> None:
    # FR-5 edge: a 3-byte character straddles the cap; it is dropped, the cut note follows, and the file keeps every byte.
    cap = CODING_PROGRESS_NOTES_MAX_BYTES
    raw = ("a" * (cap - 1) + "€" + "b" * 8 * 1024).encode("utf-8")
    notes = _notes_dir(tmp_path) / "progress.md"
    notes.parent.mkdir(parents=True)
    notes.write_bytes(raw)

    shown = _notes_shown(_agent(coding_agent_cls, tmp_path))

    assert shown == f"{CODING_PROGRESS_NOTES_INSTRUCTION}\n\n{'a' * (cap - 1)}\n\n{CODING_PROGRESS_NOTES_TRUNCATION_NOTE}"
    assert notes.read_bytes() == raw
