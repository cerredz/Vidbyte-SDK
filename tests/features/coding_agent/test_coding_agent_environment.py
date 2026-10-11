"""FILE: tests/features/coding_agent/test_coding_agent_environment.py

PURPOSE: Pin CodingAgent's environment section: the OS, date, root folder, project files, git branch, shell, and the tools bash reports reach the model after AGENTS.md and before the user message, and a missing bash or a failed probe never raises.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real run loop with the offline scripted model from conftest.py, and calls EnvironmentLoader (vidbyte/agents/coding_context/environment.py) directly where sys.platform must be simulated.
ARCHITECTURE NOTE: Most tests replace bash with this Python interpreter and the probe script with a short Python program, so the real subprocess, temporary-file, and timeout path runs on every OS without depending on which tools the host has. The probe cache is reset for those tests. One test runs the host's real bash.
FUNCTION INVENTORY: test_environment_is_shown_* (FR-3, FR-4, FR-8); test_windows_* (FR-7); test_missing_bash_* (FR-9); test_failed_probe_* (FR-10); test_load_environment_false_* (FR-2); test_load_environment_must_be_* (FR-1); test_planted_secret_* (security); test_project_marker_* (FR-5); test_git_line_* (FR-6); test_probe_runs_once_* (FR-11); test_real_bash_* (integration).
COMMON MODIFICATION PATTERNS: A new fact adds one assertion to the first test; a new failure path adds a case to test_failed_probe_*.
WHAT NOT TO DO IN THIS FILE: 1. Do not depend on which tools the host has outside the real-bash test. 2. Do not patch sys.platform while a CodingAgent is built; patch it only around EnvironmentLoader.load.
KNOWN EDGE CASES: The date assertion could fail if the test runs across midnight. The timeout case leaves the fake probe sleeping for a few seconds after the call returns, because killing it is not waited on.
RELATED DOCS: docs/design/coding-agent-environment-context.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_environment.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.coding_context import environment as environment_module
from vidbyte.agents.coding_context.environment import EnvironmentLoader
from vidbyte.lib.dataclasses.coding import CodingAgentSettings
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.builtins.bash import BashTool
from vidbyte.tools.security import PermissionPolicy

SYSTEM_PROMPT = "You are a careful engineer. SYSTEM-PROMPT-MARKER."
USER_MESSAGE = "Fix the failing test. USER-MESSAGE-MARKER"
OFFLINE_MODEL = {"provider": "openai", "model_name": "gpt-4.1-mini"}
AGENTS_HEADER = "### [coding:agents_md] Repository instructions (AGENTS.md)"
ENVIRONMENT_HEADER = "### [coding:environment] Environment"
FAKE_PROBE_OUTPUT = "- Bash: 9.9.9-fake (FakeOS 1.0 x86_64)\n- Tools on the bash PATH:\n  - git: git version 9.9.9-fake (/fake/bin/git)\n  - uv: uv 0.0.1-fake (/fake/bin/uv)"
PLANTED_SECRET = "sk-planted-environment-secret-7f3a9c"


class PromptRecorder:
    """Wraps a scripted runner and also records the user prompt it is given."""

    def __init__(self, runner: Any) -> None:
        self._runner = runner
        self.prompts: list[str] = []

    def run(self, prompt: str, **kwargs: Any) -> Any:
        self.prompts.append(prompt)
        return self._runner.run(prompt, **kwargs)


@pytest.fixture
def fake_bash(monkeypatch: pytest.MonkeyPatch) -> Any:
    # Runs the probe with this Python interpreter in place of bash, from an empty cache; install() swaps the program it runs.
    monkeypatch.setattr(environment_module, "_PROBE_RESULTS", {})
    monkeypatch.setattr(BashTool, "_find_bash", staticmethod(lambda: sys.executable))

    def install(program: str, timeout_seconds: float = 15.0) -> None:
        monkeypatch.setattr(environment_module, "CODING_ENVIRONMENT_PROBE_SCRIPT", program)
        monkeypatch.setattr(environment_module, "CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS", timeout_seconds)

    install(f"print({FAKE_PROBE_OUTPUT!r})")
    return install


@pytest.fixture
def no_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    # The host has no usable bash, as BashTool's own lookup would report.
    monkeypatch.setattr(BashTool, "_find_bash", staticmethod(lambda: None))


def _agent(coding_agent_cls: type, root_dir: str | Path, **options: object) -> Any:
    return coding_agent_cls(name="coder", system_prompt=SYSTEM_PROMPT, root_dir=root_dir, **OFFLINE_MODEL, **options)


def _shown(agent: Any) -> str:
    # The environment section text the agent placed, read through ContextManager's public API.
    item = agent.context_manager.get_by_id(CodingContextSection.ENVIRONMENT.value)
    assert item is not None
    return item.content


def _load_as(platform_name: str, root: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    # Runs the loader alone with sys.platform faked, so nothing else the agent builds sees the fake.
    settings = CodingAgentSettings(root_dir=root, permission_policy=PermissionPolicy.allow_all())
    with monkeypatch.context() as patch:
        patch.setattr(sys, "platform", platform_name)
        section = EnvironmentLoader.load(settings)
    assert section is not None
    return section.content


def test_environment_is_shown_after_agents_md_and_before_the_user_message(coding_agent_cls, script_model, tmp_path, fake_bash) -> None:
    # FR-3, FR-4, FR-8: the facts reach the model once, after AGENTS.md, and the user message is unchanged.
    (tmp_path / "AGENTS.md").write_bytes(b"Use uv, not pip.\n")
    agent = _agent(coding_agent_cls, tmp_path)
    recorder = PromptRecorder(script_model([], final_answer="done"))
    bind_test_runner(agent, recorder)

    agent.run(USER_MESSAGE)
    system = recorder._runner.requests[0]["system"]
    today = datetime.now(timezone.utc).astimezone()

    assert system.index(SYSTEM_PROMPT) < system.index(AGENTS_HEADER) < system.index(ENVIRONMENT_HEADER)
    assert system.count(ENVIRONMENT_HEADER) == 1
    assert f"- Operating system: {platform.platform()}" in system
    assert f"- Today's date: {today:%Y-%m-%d}" in system
    assert f"- Root folder: {tmp_path.resolve()}" in system
    assert "  - git: git version 9.9.9-fake (/fake/bin/git)" in system
    assert "  - uv: uv 0.0.1-fake (/fake/bin/uv)" in system
    assert "Tool probe failed" not in system
    assert recorder.prompts == [USER_MESSAGE]


@pytest.mark.parametrize("platform_name", ["win32", "linux"])
def test_windows_says_commands_run_in_git_bash_with_posix_syntax(tmp_path, fake_bash, monkeypatch, platform_name) -> None:
    # FR-7 hidden assumption: on Windows the model is told its bash is Git Bash, not PowerShell; elsewhere it is not.
    content = _load_as(platform_name, tmp_path, monkeypatch)

    windows_line = f"- Shell: the bash tool runs Git Bash (MSYS) from {sys.executable}. Write POSIX shell commands, not PowerShell or cmd. Windows paths appear as /c/Users/... inside bash."
    assert (windows_line in content) is (platform_name == "win32")
    if platform_name == "linux":
        assert f"- Shell: the bash tool runs {sys.executable}." in content


@pytest.mark.parametrize(("platform_name", "fix"), [("win32", "install Git for Windows"), ("linux", "install bash")])
def test_missing_bash_still_shows_the_python_facts_and_how_to_fix_it(tmp_path, no_bash, monkeypatch, platform_name, fix) -> None:
    # FR-9 hidden failure: no bash never raises; the section says the bash tool will fail and keeps every other fact.
    content = _load_as(platform_name, tmp_path, monkeypatch)

    assert f"- Shell: bash was not found, so the bash tool will fail; {fix}." in content
    assert f"- Root folder: {tmp_path.resolve()}" in content
    assert "- Today's date: " in content
    assert "- Bash:" not in content
    assert "Tool probe failed" not in content


@pytest.mark.parametrize(
    ("program", "timeout_seconds", "failure"),
    [
        ("import time; print('- Bash: early-fact', flush=True); time.sleep(5)", 1.0, "bash did not finish within 1 seconds"),
        ("print('- Bash: partial-fact'); raise SystemExit(3)", 15.0, "bash exited with code 3"),
    ],
    ids=["timeout", "non-zero-exit"],
)
def test_failed_probe_keeps_what_it_printed_and_says_it_failed(coding_agent_cls, tmp_path, fake_bash, program, timeout_seconds, failure) -> None:
    # FR-10 hidden failure: a hanging or failing probe still gives a section with its partial output, and never raises.
    fake_bash(program, timeout_seconds)

    content = _shown(_agent(coding_agent_cls, tmp_path))

    assert "- Bash: " in content and "-fact" in content
    assert content.endswith(f"- Tool probe failed: {failure}. The tool list above may be incomplete.")
    assert f"- Root folder: {tmp_path.resolve()}" in content


def test_load_environment_false_shows_nothing_and_starts_no_process(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # FR-2 silent failure: the switch removes the section and the probe; Popen underlies subprocess.run too.
    started: list[object] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: started.append(args))

    agent = _agent(coding_agent_cls, tmp_path, load_environment=False)

    assert started == []
    assert agent.context_manager is None


@pytest.mark.parametrize("bad", [1, "yes"], ids=["one", "yes"])
def test_load_environment_must_be_a_real_bool(coding_agent_cls, tmp_path, bad) -> None:
    # FR-1 hidden assumption: a truthy stand-in never switches the section on.
    with pytest.raises(ConfigurationError, match="load_environment") as raised:
        _agent(coding_agent_cls, tmp_path, load_environment=bad)

    assert raised.value.details["parameter"] == "load_environment"


def test_planted_secret_never_reaches_the_section(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # Hidden failure: no environment-variable value is shown, with the host's real bash probe run fresh.
    monkeypatch.setenv("SECRET_TOKEN", PLANTED_SECRET)
    monkeypatch.setattr(environment_module, "_PROBE_RESULTS", {})

    content = _shown(_agent(coding_agent_cls, tmp_path))

    assert PLANTED_SECRET not in content
    assert "SECRET_TOKEN" not in content


def test_project_marker_files_in_the_root_are_listed(tmp_path, no_bash, monkeypatch) -> None:
    # FR-5 edge: only marker files directly in the root count, in a fixed order; a folder or a nested file does not.
    for name in ("Makefile", "uv.lock", "package-lock.json"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "go.mod").mkdir()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "Cargo.toml").write_bytes(b"")
    empty = tmp_path / "empty"
    empty.mkdir()

    assert "- Project files in the root folder: uv.lock, package-lock.json, Makefile\n" in _load_as(sys.platform, tmp_path, monkeypatch)
    assert "- Project files in the root folder: none of the usual lockfiles or build files\n" in _load_as(sys.platform, empty, monkeypatch)


@pytest.mark.parametrize(
    ("layout", "expected"),
    [
        ({"repo/.git/HEAD": "ref: refs/heads/feature/env\n"}, "- Git: inside a git repository, on branch feature/env."),
        ({"repo/.git": "gitdir: ../main/.git/worktrees/wt\n", "main/.git/worktrees/wt/HEAD": "ref: refs/heads/wt-branch\n"}, "- Git: inside a git repository, on branch wt-branch."),
        ({"repo/.git/HEAD": "3f2c1e0d9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e\n"}, "- Git: inside a git repository, detached at commit 3f2c1e0d9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e."),
    ],
    ids=["branch-from-a-subfolder", "worktree-gitdir-file", "detached"],
)
def test_git_line_reads_the_branch_from_git_files(tmp_path, no_bash, monkeypatch, layout, expected) -> None:
    # FR-6 hidden assumption: the root may be a subfolder, a worktree whose .git is a file, or a detached checkout.
    for relative, text in layout.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    root = tmp_path / "repo" / "src"
    root.mkdir()

    assert expected in _load_as(sys.platform, root, monkeypatch)


def test_probe_runs_once_per_bash_and_path(coding_agent_cls, tmp_path, fake_bash, monkeypatch) -> None:
    # FR-11 hidden failure: agents over other roots reuse the probe, and a changed PATH probes again.
    real_run = subprocess.run
    runs: list[object] = []

    def counting_run(*args: Any, **kwargs: Any) -> Any:
        runs.append(kwargs["cwd"])
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", counting_run)
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()

    _agent(coding_agent_cls, first)
    shown = _shown(_agent(coding_agent_cls, second))
    assert len(runs) == 1
    assert "  - git: git version 9.9.9-fake (/fake/bin/git)" in shown
    assert f"- Root folder: {second.resolve()}" in shown

    monkeypatch.setenv("PATH", os.environ.get("PATH", "") + os.pathsep + str(tmp_path))
    _agent(coding_agent_cls, second)
    assert len(runs) == 2


@pytest.mark.skipif(BashTool._find_bash() is None or shutil.which("git") is None, reason="needs a real bash and git on this host")
def test_real_bash_reports_its_version_and_git(coding_agent_cls, tmp_path) -> None:
    # Integration: the host's own bash runs the real probe script and finds git on its PATH.
    content = _shown(_agent(coding_agent_cls, tmp_path))

    assert "- Bash: " in content
    assert "  - git: git version " in content
    assert "Tool probe failed" not in content
