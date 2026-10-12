"""FILE: tests/features/coding_agent/test_coding_agent_environment.py

PURPOSE: Pin CodingAgent's environment section: the OS family and version, date, working directory, project files with their languages and package managers, declared dependencies, installed dependency folders, git branch, shell, and what bash reports reach the model as an EnvironmentContextItem after AGENTS.md and before the user message, and a missing bash, a failed probe, or a malformed manifest never raises.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real run loop with the offline scripted model from conftest.py; calls EnvironmentLoader (vidbyte/agents/coding_context/environment.py) directly where sys.platform must be simulated, and builds EnvironmentContextItem (vidbyte/context/primitives/documents.py) and CodingContextSectionItem (vidbyte/lib/dataclasses/coding.py) on their own for their checks.
ARCHITECTURE NOTE: Most tests replace bash with this Python interpreter and the probe script with a short Python program that prints the probe's raw tab-separated records, so the real subprocess, temporary-file, parsing, and timeout path runs on every OS without depending on which tools the host has. The probe cache in vidbyte/agents/coding_context/environment_probe.py is reset for those tests. One test runs the host's real bash.
FUNCTION INVENTORY: test_environment_is_shown_* (position and facts in the request); test_windows_* (Git Bash line); test_missing_bash_* (no bash); test_failed_probe_* (timeout, non-zero exit); test_probe_keeps_only_finished_records (cut output); test_load_environment_false_* and test_load_environment_must_be_* (the switch); test_planted_secret_* (secrecy); test_project_files_* (markers, languages, package managers); test_declared_dependencies_* and test_malformed_manifests_* (manifests); test_installed_dependency_folders_* ; test_git_head_* (branches); test_probe_runs_once_* (cache); test_caller_environment_item_* and test_environment_item_rejects_* (the primitive alone); test_section_item_* (CodingContextSectionItem); test_real_bash_* (integration).
COMMON MODIFICATION PATTERNS: A new fact adds one field assertion and one rendered-line assertion to the first test; a new failure path adds a case to test_failed_probe_*; a new manifest adds a file to test_declared_dependencies_*.
WHAT NOT TO DO IN THIS FILE: 1. Do not depend on which tools the host has outside the real-bash test. 2. Do not patch sys.platform while a CodingAgent is built; patch it only around EnvironmentLoader.load.
KNOWN EDGE CASES: The date assertion could fail if the test runs across midnight. The timeout case leaves the fake probe sleeping for a few seconds after the call returns, because killing it is not waited on.
RELATED DOCS: docs/design/coding-agent-environment-context.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_environment.py
"""

from __future__ import annotations

import json
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
from vidbyte.agents.coding_context import environment_probe as probe_module
from vidbyte.agents.coding_context import project_dependencies as dependencies_module
from vidbyte.agents.coding_context.environment import EnvironmentLoader
from vidbyte.agents.coding_context.window import CodingContextWindow
from vidbyte.context.primitives import EnvironmentContextItem
from vidbyte.lib.dataclasses.coding import CodingAgentSettings, CodingContextSectionItem
from vidbyte.lib.dataclasses.context import EnvironmentTool
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.enums.context import GitHeadState, OperatingSystemFamily, ShellKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.builtins.bash import BashTool
from vidbyte.tools.security import PermissionPolicy

SYSTEM_PROMPT = "You are a careful engineer. SYSTEM-PROMPT-MARKER."
USER_MESSAGE = "Fix the failing test. USER-MESSAGE-MARKER"
OFFLINE_MODEL = {"provider": "openai", "model_name": "gpt-4.1-mini"}
AGENTS_HEADER = "### [coding:agents_md] Repository instructions (AGENTS.md)"
ENVIRONMENT_HEADER = "### [coding:environment] Environment"
FAKE_PROBE_OUTPUT = "bash\t9.9.9-fake\tFakeOS 1.0 x86_64\npackage-manager\tfakebrew\ntool\tgit\tgit version 9.9.9-fake\t/fake/bin/git\ntool\tuv\tuv 0.0.1-fake\t/fake/bin/uv\n"
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
    monkeypatch.setattr(probe_module, "_PROBE_RESULTS", {})
    monkeypatch.setattr(BashTool, "find_bash", staticmethod(lambda: sys.executable))

    def install(program: str, timeout_seconds: float = 15.0) -> None:
        monkeypatch.setattr(probe_module, "CODING_ENVIRONMENT_PROBE_SCRIPT", program)
        monkeypatch.setattr(probe_module, "CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS", timeout_seconds)

    install(f"import sys; sys.stdout.write({FAKE_PROBE_OUTPUT!r})")
    return install


@pytest.fixture
def no_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    # The host has no usable bash, as BashTool's own lookup would report.
    monkeypatch.setattr(BashTool, "find_bash", staticmethod(lambda: None))


def _agent(coding_agent_cls: type, root_dir: str | Path, **options: object) -> Any:
    return coding_agent_cls(name="coder", system_prompt=SYSTEM_PROMPT, root_dir=root_dir, **OFFLINE_MODEL, **options)


def _item(agent: Any) -> EnvironmentContextItem:
    # The environment primitive the agent placed, read through ContextManager's public API.
    item = agent.context_manager.get_by_id(CodingContextSection.ENVIRONMENT.value)
    assert isinstance(item, EnvironmentContextItem)
    return item


def _load_as(platform_name: str, root: Path, monkeypatch: pytest.MonkeyPatch) -> EnvironmentContextItem:
    # Runs the loader alone with sys.platform faked, so nothing else the agent builds sees the fake.
    settings = CodingAgentSettings(root_dir=root, permission_policy=PermissionPolicy.allow_all(), max_rewrite_lines=300)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "platform", platform_name)
        section = EnvironmentLoader.load(settings)
    assert isinstance(section, CodingContextSectionItem)
    assert isinstance(section.item, EnvironmentContextItem)
    return section.item


def _write_files(root: Path, files: dict[str, str | bytes]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))


def test_environment_is_shown_after_agents_md_and_before_the_user_message(coding_agent_cls, script_model, tmp_path, fake_bash) -> None:
    # Silent failure: the gathered facts reach the model once, after AGENTS.md, as the environment primitive, and the user message is unchanged.
    _write_files(tmp_path, {"AGENTS.md": "Use uv, not pip.\n", "pyproject.toml": '[project]\nname = "demo"\ndependencies = ["httpx>=0.27"]\n', "uv.lock": ""})
    agent = _agent(coding_agent_cls, tmp_path, progress_notes=False)
    recorder = PromptRecorder(script_model([], final_answer="done"))
    bind_test_runner(agent, recorder)

    agent.run(USER_MESSAGE)
    system = recorder._runner.requests[0]["system"]
    today = datetime.now(timezone.utc).astimezone()
    item = _item(agent)

    assert system.index(SYSTEM_PROMPT) < system.index(AGENTS_HEADER) < system.index(ENVIRONMENT_HEADER)
    assert system.count(ENVIRONMENT_HEADER) == 1
    assert item.os_name == platform.platform() and item.cwd == str(tmp_path.resolve())
    assert item.languages == ("Python",) and item.package_managers == ("uv",) and item.dependencies == ("httpx",)
    assert item.tools == (EnvironmentTool("git", "git version 9.9.9-fake", "/fake/bin/git"), EnvironmentTool("uv", "uv 0.0.1-fake", "/fake/bin/uv"))
    # On Linux the distribution precedes the platform inside the parentheses, so match the platform on its own.
    assert platform.platform() in system
    assert f"- Date when gathered: {today:%Y-%m-%d}" in system
    assert f"- Working directory: {tmp_path.resolve()}" in system
    assert "- Languages: Python\n- Package managers: uv\n- Declared dependencies: httpx\n" in system
    assert "- Bash version: 9.9.9-fake\n- System (uname -srm): FakeOS 1.0 x86_64\n- System package managers on the shell's PATH: fakebrew\n" in system
    assert "  - git: git version 9.9.9-fake (/fake/bin/git)" in system
    assert "  - uv: uv 0.0.1-fake (/fake/bin/uv)" in system
    assert "Tool probe failed" not in system
    assert recorder.prompts == [USER_MESSAGE]


@pytest.mark.parametrize(("platform_name", "family", "label"), [("win32", OperatingSystemFamily.WINDOWS, "Windows"), ("linux", OperatingSystemFamily.LINUX, "Linux"), ("darwin", OperatingSystemFamily.MACOS, "macOS")])
def test_windows_says_commands_run_in_git_bash_with_posix_syntax(tmp_path, fake_bash, monkeypatch, platform_name, family, label) -> None:
    # Hidden assumption: on Windows the model is told its bash is Git Bash, not PowerShell; elsewhere it is told plain bash, and the OS family matches.
    item = _load_as(platform_name, tmp_path, monkeypatch)
    content = item.to_context_text()

    windows_line = f"- Shell: Git Bash (MSYS) from {sys.executable}. Write POSIX shell commands, not PowerShell or cmd. Windows paths appear as /c/Users/... inside bash."
    assert item.os_family is family
    assert f"- Operating system: {label} (" in content
    assert (windows_line in content) is (platform_name == "win32")
    assert (item.shell_kind is ShellKind.GIT_BASH) is (platform_name == "win32")
    if platform_name != "win32":
        assert f"- Shell: bash from {sys.executable}." in content


@pytest.mark.parametrize(("platform_name", "fix"), [("win32", "Install Git for Windows and put git on PATH"), ("linux", "Install bash and put it on PATH.")])
def test_missing_bash_still_shows_the_python_facts_and_how_to_fix_it(tmp_path, no_bash, monkeypatch, platform_name, fix) -> None:
    # Hidden failure: no bash never raises; the section says shell commands will fail, how to fix it, and keeps every other fact.
    item = _load_as(platform_name, tmp_path, monkeypatch)
    content = item.to_context_text()

    assert f"- Shell: none, so shell commands will fail: bash was not found. {fix}" in content
    assert f"- Working directory: {tmp_path.resolve()}" in content
    assert "- Date when gathered: " in content
    assert item.shell is None and item.shell_kind is None and item.bash_version is None and item.tools == ()
    assert "Tool probe failed" not in content


@pytest.mark.parametrize(
    ("program", "timeout_seconds", "version", "failure"),
    [
        ("import sys, time; sys.stdout.write('bash\\tearly-fact\\tFakeOS\\n'); sys.stdout.flush(); time.sleep(5)", 1.0, "early-fact", "bash did not finish within 1 seconds"),
        ("import sys; sys.stdout.write('bash\\tpartial-fact\\tFakeOS\\n'); raise SystemExit(3)", 15.0, "partial-fact", "bash exited with code 3"),
    ],
    ids=["timeout", "non-zero-exit"],
)
def test_failed_probe_keeps_what_it_printed_and_says_it_failed(coding_agent_cls, tmp_path, fake_bash, program, timeout_seconds, version, failure) -> None:
    # Hidden failure: a hanging or failing probe still gives a section with what it printed first, and never raises.
    fake_bash(program, timeout_seconds)

    item = _item(_agent(coding_agent_cls, tmp_path))
    content = item.to_context_text()

    assert item.bash_version == version and item.probe_error == failure
    assert f"\n- Bash version: {version}\n" in content
    assert content.endswith(f"- Tool probe failed: {failure}. The facts gathered from the shell may be incomplete.")
    assert f"- Working directory: {tmp_path.resolve()}" in content


def test_probe_keeps_only_finished_records(coding_agent_cls, tmp_path, fake_bash) -> None:
    # Edge case: output cut mid-line by a timeout or the cap never becomes half a record; a tab inside a version line stays in the version.
    fake_bash("import sys; sys.stdout.write('tool\\tgit\\tgit\\tversion 1\\t/p/git\\nnoise line\\ntool\\tcut\\tcut 1')")

    item = _item(_agent(coding_agent_cls, tmp_path))

    assert item.tools == (EnvironmentTool("git", "git\tversion 1", "/p/git"),)


def test_load_environment_false_shows_nothing_and_starts_no_process(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # Silent failure: the switch removes the section and the probe; Popen underlies subprocess.run too.
    started: list[object] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: started.append(args))

    agent = _agent(coding_agent_cls, tmp_path, load_environment=False, progress_notes=False)

    assert started == []
    assert agent.context_manager is None


@pytest.mark.parametrize("bad", [1, "yes"], ids=["one", "yes"])
def test_load_environment_must_be_a_real_bool(coding_agent_cls, tmp_path, bad) -> None:
    # Hidden assumption: a truthy stand-in never switches the section on.
    with pytest.raises(ConfigurationError, match="load_environment") as raised:
        _agent(coding_agent_cls, tmp_path, load_environment=bad)

    assert raised.value.details["parameter"] == "load_environment"


def test_planted_secret_never_reaches_the_section(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # Hidden failure: no environment-variable value is shown, with the host's real bash probe run fresh.
    monkeypatch.setenv("SECRET_TOKEN", PLANTED_SECRET)
    monkeypatch.setattr(probe_module, "_PROBE_RESULTS", {})

    content = _item(_agent(coding_agent_cls, tmp_path)).to_context_text()

    assert PLANTED_SECRET not in content
    assert "SECRET_TOKEN" not in content


def test_project_files_name_the_languages_and_package_managers(tmp_path, no_bash, monkeypatch) -> None:
    # Edge case: only marker files directly in the root count, in table order; a folder or a nested file does not, and an empty root lists nothing.
    _write_files(tmp_path, {"Makefile": "", "uv.lock": "", "package-lock.json": "", "pyproject.toml": "", "package.json": "{}", "tsconfig.json": "{}", "nested/Cargo.toml": ""})
    (tmp_path / "go.mod").mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()

    item = _load_as(sys.platform, tmp_path, monkeypatch)
    bare = _load_as(sys.platform, empty, monkeypatch)

    assert item.project_files == ("pyproject.toml", "package.json", "tsconfig.json", "uv.lock", "package-lock.json", "Makefile")
    assert item.languages == ("Python", "JavaScript", "TypeScript")
    assert item.package_managers == ("uv", "npm")
    assert "- Project files in the working directory: pyproject.toml, package.json, tsconfig.json, uv.lock, package-lock.json, Makefile\n" in item.to_context_text()
    assert bare.project_files == bare.languages == bare.package_managers == ()
    assert "Project files" not in bare.to_context_text() and "Languages" not in bare.to_context_text()


def test_declared_dependencies_come_from_every_manifest_once(tmp_path, no_bash, monkeypatch) -> None:
    # Edge case: PEP 621, dependency groups, Poetry, requirements.txt, package.json, and Cargo.toml all count; versions and extras drop; a repeated name shows once.
    pyproject = '[project]\ndependencies = ["httpx>=0.27", "pydantic[email]>=2"]\n[project.optional-dependencies]\ndev = ["pytest"]\n[dependency-groups]\nlint = ["ruff", {include-group = "dev"}]\n[tool.poetry.dependencies]\npython = "^3.11"\nrequests = "*"\n'
    requirements = "# pinned\nhttpx==0.27.0\n-r base.txt\ngit+https://example.com/pkg.git\nrich ; python_version >= '3.8'\n"
    package_json = json.dumps({"dependencies": {"react": "^19"}, "devDependencies": {"vitest": "^2"}})
    _write_files(tmp_path, {"pyproject.toml": pyproject, "requirements.txt": requirements, "package.json": package_json, "Cargo.toml": '[dependencies]\nserde = "1"\n[dev-dependencies]\ninsta = "1"\n'})

    item = _load_as(sys.platform, tmp_path, monkeypatch)

    assert item.dependencies == ("httpx", "pydantic", "pytest", "ruff", "requests", "rich", "react", "vitest", "serde", "insta")
    assert "- Declared dependencies: httpx, pydantic, pytest, ruff, requests, rich, react, vitest, serde, insta\n" in item.to_context_text()


def test_declared_dependencies_read_parenthesized_versions_and_inline_comments(tmp_path, no_bash, monkeypatch) -> None:
    # Regression: Poetry 2 writes "name (>=1)" into PEP 621 lists, and pip allows "name  # comment"; both forms used to drop the name.
    pyproject = '[project]\ndependencies = ["requests (>=2.32.3,<3.0.0)", "pydantic(>=2.7)", "httpx[http2] (>=0.27)", "rich"]\n[dependency-groups]\ndev = ["ruff (>=0.6)", "mypy ; python_version >= \'3.11\'"]\n'
    requirements = "# tools\npytest  # test runner\nhypothesis==6.100  # property tests\ncoverage\t# tab before the comment\n    # indented comment\nblack\n"
    _write_files(tmp_path, {"pyproject.toml": pyproject, "requirements.txt": requirements})

    item = _load_as(sys.platform, tmp_path, monkeypatch)

    assert item.dependencies == ("requests", "pydantic", "httpx", "rich", "ruff", "mypy", "pytest", "hypothesis", "coverage", "black")
    assert "- Declared dependencies: requests, pydantic, httpx, rich, ruff, mypy, pytest, hypothesis, coverage, black\n" in item.to_context_text()


def test_declared_dependencies_read_manifests_with_a_byte_order_mark(tmp_path, no_bash, monkeypatch) -> None:
    # Regression: Windows PowerShell writes UTF-8 with a BOM, which npm and pip accept; the BOM used to break TOML and JSON parsing and hide the first requirements.txt name.
    bom = b"\xef\xbb\xbf"
    pyproject = bom + b'[project]\ndependencies = ["httpx>=0.27"]\n'
    requirements = bom + b"flask\nrich\n"
    package_json = bom + json.dumps({"dependencies": {"react": "^19"}, "devDependencies": {"vitest": "^2"}}).encode("utf-8")
    _write_files(tmp_path, {"pyproject.toml": pyproject, "requirements.txt": requirements, "package.json": package_json})

    assert _load_as(sys.platform, tmp_path, monkeypatch).dependencies == ("httpx", "flask", "rich", "react", "vitest")


@pytest.mark.parametrize(
    "line",
    ["https://example.com/pkg-1.0-py3-none-any.whl", "git+https://example.com/pkg.git", "git+https://example.com/pkg.git  # pinned fork", "./local/path", "../sibling/pkg", "pkg-1.0.tar.gz#sha256=abc", "--index-url https://example.com/simple"],
    ids=["url", "vcs", "vcs-with-comment", "relative-path", "parent-path", "archive-with-fragment", "option"],
)
def test_requirement_lines_that_are_not_names_give_no_names(tmp_path, no_bash, monkeypatch, line) -> None:
    # Edge case: widening what may follow a name must not turn a URL, a VCS link, a path, or an option into a name such as "git" or "https".
    _write_files(tmp_path, {"requirements.txt": f"{line}\n"})

    assert _load_as(sys.platform, tmp_path, monkeypatch).dependencies == ()


def test_declared_dependencies_are_capped(tmp_path, no_bash, monkeypatch) -> None:
    # Edge case: a huge manifest cannot fill the context; only the first names up to the cap are kept.
    monkeypatch.setattr(dependencies_module, "CODING_ENVIRONMENT_MAX_DEPENDENCIES", 3)
    _write_files(tmp_path, {"requirements.txt": "".join(f"pkg{index}\n" for index in range(10))})

    assert _load_as(sys.platform, tmp_path, monkeypatch).dependencies == ("pkg0", "pkg1", "pkg2")


def test_declared_dependencies_skip_an_oversized_manifest(tmp_path, no_bash, monkeypatch) -> None:
    # Edge case: a manifest over the size cap is skipped whole rather than parsed from a cut prefix; one exactly at the cap is read.
    requirements = b"httpx\npytest\n"
    monkeypatch.setattr(dependencies_module, "CODING_ENVIRONMENT_MANIFEST_MAX_BYTES", len(requirements))
    _write_files(tmp_path, {"requirements.txt": requirements, "package.json": json.dumps({"dependencies": {"react": "^19.0.0"}})})

    assert _load_as(sys.platform, tmp_path, monkeypatch).dependencies == ("httpx", "pytest")


@pytest.mark.parametrize(
    "files",
    [
        {"pyproject.toml": "[project\nbroken", "package.json": "{not json", "Cargo.toml": "= nope"},
        {"pyproject.toml": '[project]\ndependencies = "httpx"\n[dependency-groups]\ndev = "pytest"\n[tool.poetry]\ndependencies = ["requests"]\n', "package.json": "[1, 2]", "Cargo.toml": 'dependencies = "serde"\n'},
        {"pyproject.toml": '[project]\ndependencies = ["httpx"]\noptional-dependencies = 3\n'},
        {"pyproject.toml": b'\xff\xfe[project]\ndependencies = ["httpx"]\n'},
    ],
    ids=["unparsable", "wrong-list-shapes", "wrong-table-shape", "undecodable"],
)
def test_malformed_manifests_give_no_names_and_never_raise(tmp_path, no_bash, monkeypatch, files) -> None:
    # Hidden failure: a broken manifest must not break construction; it only adds no dependency names.
    _write_files(tmp_path, files)

    item = _load_as(sys.platform, tmp_path, monkeypatch)

    assert item.dependencies == ()
    assert "Declared dependencies" not in item.to_context_text()


def test_installed_dependency_folders_are_listed(tmp_path, no_bash, monkeypatch) -> None:
    # Edge case: a dependency folder tells the model the install step already ran; a file with a folder's name does not count.
    (tmp_path / ".venv").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "vendor").write_bytes(b"")

    item = _load_as(sys.platform, tmp_path, monkeypatch)

    assert item.dependency_folders == (".venv", "node_modules")
    assert "- Installed dependency folders: .venv, node_modules\n" in item.to_context_text()


@pytest.mark.parametrize(
    ("layout", "state", "ref", "line"),
    [
        ({"repo/.git/HEAD": "ref: refs/heads/feature/env\n"}, GitHeadState.BRANCH, "feature/env", "- Git: inside a git repository, on branch feature/env."),
        ({"repo/.git": "gitdir: ../main/.git/worktrees/wt\n", "main/.git/worktrees/wt/HEAD": "ref: refs/heads/wt-branch\n"}, GitHeadState.BRANCH, "wt-branch", "- Git: inside a git repository, on branch wt-branch."),
        ({"repo/.git/HEAD": "3f2c1e0d9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e\n"}, GitHeadState.DETACHED, "3f2c1e0d9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e", "- Git: inside a git repository, detached at commit 3f2c1e0d9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e."),
        ({"repo/.git": "gitdir: \0broken\n"}, GitHeadState.UNREADABLE, None, "- Git: inside a git repository; its branch could not be read."),
        ({"repo/.git/HEAD": "\n"}, GitHeadState.UNREADABLE, None, "- Git: inside a git repository; its branch could not be read."),
    ],
    ids=["branch-from-a-subfolder", "worktree-gitdir-file", "detached", "broken-gitdir", "empty-head"],
)
def test_git_head_is_read_from_git_files(tmp_path, no_bash, monkeypatch, layout, state, ref, line) -> None:
    # Hidden assumption: the root may be a subfolder, a worktree whose .git is a file, a detached checkout, or a broken .git that must not raise.
    _write_files(tmp_path, layout)
    root = tmp_path / "repo" / "src"
    root.mkdir()

    item = _load_as(sys.platform, root, monkeypatch)

    assert (item.git_state, item.git_ref) == (state, ref)
    assert line in item.to_context_text()


def test_probe_runs_once_per_bash_and_path(coding_agent_cls, tmp_path, fake_bash, monkeypatch) -> None:
    # Hidden failure: agents over other roots reuse the probe, and a changed PATH probes again.
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
    item = _item(_agent(coding_agent_cls, second))
    assert len(runs) == 1
    assert item.tools[0] == EnvironmentTool("git", "git version 9.9.9-fake", "/fake/bin/git")
    assert item.cwd == str(second.resolve())

    monkeypatch.setenv("PATH", os.environ.get("PATH", "") + os.pathsep + str(tmp_path))
    _agent(coding_agent_cls, second)
    assert len(runs) == 2


def test_caller_environment_item_renders_only_what_it_was_given() -> None:
    # Silent failure: an item built by a caller or the create tool keeps rendering its three fields, and an empty one says N/A.
    item = EnvironmentContextItem(os_name="Linux", cwd="/work", shell="zsh")
    body = item.to_context_text().split("Environment:\n", 1)[1]

    assert body == "- Operating system: Linux\n- Working directory: /work\n- Shell: zsh"
    assert EnvironmentContextItem().to_context_text().endswith("Environment:\nN/A")


@pytest.mark.parametrize(
    ("fields", "wrong"),
    [
        ({"cpu_count": True}, "cpu_count"),
        ({"cpu_count": 0}, "cpu_count"),
        ({"local_time": datetime(2026, 10, 11)}, "local_time"),
        ({"git_state": GitHeadState.BRANCH}, "git_ref"),
        ({"git_state": "branch", "git_ref": "main"}, "git_state"),
        ({"shell_kind": ShellKind.GIT_BASH}, "shell"),
        ({"tools": (("git", "v", "/p"),)}, "tools"),
        ({"languages": ["Python"]}, "languages"),
        ({"dependencies": ("",)}, "dependencies"),
        ({"probe_error": "  "}, "probe_error"),
    ],
    ids=["bool-count", "zero-count", "naive-time", "branch-without-ref", "string-state", "kind-without-shell", "tuple-tool", "list-languages", "blank-dependency", "blank-error"],
)
def test_environment_item_rejects_malformed_facts(fields, wrong) -> None:
    # Hidden failure: a loader bug fails where the item is built, naming the field, instead of rendering nonsense to the model.
    with pytest.raises(ConfigurationError, match=f"EnvironmentContextItem {wrong} ") as raised:
        EnvironmentContextItem(**fields)

    assert raised.value.details["fields"] == [wrong]


def test_section_item_is_placed_as_its_own_primitive_under_the_section_id() -> None:
    # Silent failure: the window places the environment primitive itself, not a text copy, and gives it the section's id.
    section = CodingContextSectionItem(section=CodingContextSection.ENVIRONMENT, item=EnvironmentContextItem(os_name="Linux"))

    window = CodingContextWindow.build((section,), None)

    assert window is not None
    placed = window.get_by_id(CodingContextSection.ENVIRONMENT.value)
    assert isinstance(placed, EnvironmentContextItem) and placed.primitive_id == CodingContextSection.ENVIRONMENT.value
    assert section.item.primitive_id is None


@pytest.mark.parametrize(("section", "item", "field"), [(CodingContextSection.ENVIRONMENT, object(), "item"), (CodingContextSection.ENVIRONMENT, EnvironmentContextItem, "item"), ("coding:environment", EnvironmentContextItem(), "section")], ids=["not-a-primitive", "a-class", "string-section"])
def test_section_item_rejects_what_the_window_cannot_place(section, item, field) -> None:
    # Hidden assumption: a loader wired with the wrong record fails at construction, naming the field.
    with pytest.raises(ConfigurationError, match=f"CodingContextSectionItem {field} must be") as raised:
        CodingContextSectionItem(section=section, item=item)

    assert raised.value.details["field"] == field


@pytest.mark.skipif(BashTool.find_bash() is None or shutil.which("git") is None, reason="needs a real bash and git on this host")
def test_real_bash_reports_its_version_and_git(coding_agent_cls, tmp_path) -> None:
    # Integration: the host's own bash runs the real probe script and finds git on its PATH.
    item = _item(_agent(coding_agent_cls, tmp_path))
    content = item.to_context_text()

    assert item.bash_version and "- Bash version: " in content
    assert "git" in [tool.name for tool in item.tools]
    assert "  - git: git version " in content
    assert "Tool probe failed" not in content
