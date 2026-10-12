"""FILE: tests/features/coding_agent/test_coding_agent_readonly_paths.py

PURPOSE: Prove that CodingAgent(readonly_paths=...) lets the model read protected files but never edit them with write_text or replace_text, however it spells the path, while every other call behaves as before.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real tool loop (AgentRuntime, the middleware pipeline, the real file tools) with the offline scripted model from conftest.py.
ARCHITECTURE NOTE: Only the model runner is replaced. Assertions read tool_call_states, the model-visible tool messages, agent.middleware, and the files under root_dir.
FUNCTION INVENTORY: test_edits_of_a_protected_file_* (both edit tools, both pattern forms); test_every_spelling_* (path variants); test_case_is_ignored_on_windows_* (normcase on both sides); test_unprotected_* (other writes and protected reads); test_a_path_outside_root_* (the tool's own error); test_no_readonly_paths_* (no middleware); test_bad_readonly_paths_* (construction errors); test_caller_middleware_* (order).
COMMON MODIFICATION PATTERNS: A new file-editing tool on CodingAgent gets one denied call in test_edits_of_a_protected_file_*.
WHAT NOT TO DO IN THIS FILE: 1. Do not call the middleware directly; the denial must be proven through the loop. 2. Do not test bash; it is deliberately unconfined.
KNOWN EDGE CASES: Backslash and case variants name the same file only on Windows, so those cases run only there.
RELATED DOCS: tests/features/coding_agent/FEATURE.md; docs/design/coding-agent-readonly-paths.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_readonly_paths.py
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from tests.agent_test_support import build_test_agent
from vidbyte.lib.errors import ConfigurationError
from vidbyte.middleware import AgentMiddleware, MiddlewareDecision
from vidbyte.middleware.builtins.readonly_paths import ReadonlyPathsMiddleware

PROTECTED = "tests/unit/test_api.py"
WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="backslashes and case name the same file only on Windows")
IDENTITY = {"name": "coder", "system_prompt": "Fix the code.", "provider": "openai", "model_name": "gpt-4.1-mini"}


class RecordingMiddleware(AgentMiddleware):
    """Caller middleware that records every tool call it sees and lets it through."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def before_tool_call(self, ctx: Any) -> MiddlewareDecision:
        self.seen.append(ctx.tool_call.tool_name)
        return MiddlewareDecision.continue_()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # A root with one protected test file and an empty source folder.
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / PROTECTED).write_text("def test_api():\n    assert add(1, 2) == 3\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    return tmp_path


def _files(root: Path) -> dict[str, bytes]:
    # Every file under root with its exact bytes, so a denied call can
    # be shown to change nothing.
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _run(agent_cls: type, script_model: Any, root: Path, calls: Sequence[tuple[str, Mapping[str, object]]], **options: Any) -> tuple[Any, tuple[str, ...], list[tuple[str, str]]]:
    # Runs one scripted task and returns the agent, the call states, and
    # the tool messages the model saw.
    runner = script_model(calls, final_answer="done")
    agent = build_test_agent(name="coder", system_prompt="Fix the code.", root_dir=root, runner=runner, agent_type=agent_cls, **options)
    reply = agent.run("Make the tests pass.")
    return agent, reply.metadata["tool_call_states"], runner.tool_messages()


@pytest.mark.parametrize("pattern", ["tests/**", "tests/*"])
def test_edits_of_a_protected_file_are_denied_and_name_the_file_and_pattern(coding_agent_cls, script_model, project, pattern) -> None:
    # In fnmatch * also matches /, so both forms protect a nested file;
    # a list input works too.
    before = _files(project)
    calls = [
        ("write_text", {"path": PROTECTED, "content": "def test_api():\n    pass\n"}),
        ("replace_text", {"path": PROTECTED, "search": "== 3", "replacement": "== 4"}),
    ]

    _, states, messages = _run(coding_agent_cls, script_model, project, calls, readonly_paths=[pattern])

    assert states == ("denied", "denied", "succeeded")
    assert _files(project) == before
    assert [name for name, _ in messages] == ["write_text", "replace_text"]
    for _, seen in messages:
        assert f"`{PROTECTED}` is read-only for this run (readonly_paths: `{pattern}`)" in seen


@pytest.mark.parametrize(
    "spelling",
    [
        "./tests/unit/test_api.py",
        "src/../tests/unit/test_api.py",
        "<absolute>",
        "tests/unit/test_new.py",
        pytest.param("tests\\unit\\test_api.py", marks=WINDOWS_ONLY),
        pytest.param("TESTS/Unit/test_api.py", marks=WINDOWS_ONLY),
    ],
)
def test_every_spelling_of_a_protected_path_is_denied(coding_agent_cls, script_model, project, spelling) -> None:
    # The check resolves the path exactly as the tool does, so no
    # spelling, and no new file, slips past it.
    path = str(project / PROTECTED) if spelling == "<absolute>" else spelling
    before = _files(project)

    _, states, messages = _run(coding_agent_cls, script_model, project, [("write_text", {"path": path, "content": "pass\n"})], readonly_paths=("tests/**",))

    assert states == ("denied", "succeeded")
    assert _files(project) == before
    assert "is read-only for this run" in messages[0][1]


@WINDOWS_ONLY
def test_case_is_ignored_on_windows_even_for_a_folder_that_does_not_exist_yet(coding_agent_cls, script_model, project) -> None:
    # Resolving keeps the model's case for a missing folder, so only
    # normcase on both sides can match it.
    call = ("write_text", {"path": "GENERATED/out.py", "content": "pass\n", "create_parents": True})

    _, states, _ = _run(coding_agent_cls, script_model, project, [call], readonly_paths=["Generated/**"])

    assert states == ("denied", "succeeded")
    assert not (project / "generated").exists()


def test_unprotected_writes_and_reads_of_protected_files_still_work(coding_agent_cls, script_model, project) -> None:
    calls = [
        ("write_text", {"path": "src/app.py", "content": "def add(a, b):\n    return a + b\n"}),
        ("read_lines", {"path": PROTECTED}),
    ]

    _, states, messages = _run(coding_agent_cls, script_model, project, calls, readonly_paths=["tests/**"])

    assert states == ("succeeded", "succeeded", "succeeded")
    assert (project / "src" / "app.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
    assert "assert add(1, 2) == 3" in messages[1][1]


def test_a_path_outside_root_gets_the_tool_error_unchanged(coding_agent_cls, script_model, project) -> None:
    # Even a match-everything pattern must not replace the tool's own
    # error with a denial.
    call = [("write_text", {"path": "../outside.py", "content": "pass\n"})]

    _, protected_states, protected_messages = _run(coding_agent_cls, script_model, project, call, readonly_paths=["*"])
    _, plain_states, plain_messages = _run(coding_agent_cls, script_model, project, call)

    assert protected_states == plain_states
    assert protected_messages == plain_messages
    assert "escaped the configured root" in protected_messages[0][1]


def test_no_readonly_paths_adds_no_middleware(coding_agent_cls, project) -> None:
    caller = RecordingMiddleware()

    assert coding_agent_cls(root_dir=project, **IDENTITY).middleware == ()
    assert coding_agent_cls(root_dir=project, readonly_paths=(), **IDENTITY).middleware == ()
    assert coding_agent_cls(root_dir=project, readonly_paths=[], middleware=[caller], **IDENTITY).middleware == (caller,)


@pytest.mark.parametrize("bad", ["tests/**", ["tests/**", 5], ["tests/**", "  "]], ids=["bare-string", "non-string-item", "blank-item"])
def test_bad_readonly_paths_fail_at_construction_naming_the_field(coding_agent_cls, project, bad) -> None:
    # A bare string must not be split into one-character patterns that
    # protect nothing.
    with pytest.raises(ConfigurationError, match="readonly_paths"):
        coding_agent_cls(root_dir=project, readonly_paths=bad, **IDENTITY)


def test_caller_middleware_runs_before_the_readonly_check(coding_agent_cls, script_model, project) -> None:
    # A deny stops the pipeline, so the caller's middleware sees the
    # edit only if it runs first.
    caller = RecordingMiddleware()

    agent, states, _ = _run(coding_agent_cls, script_model, project, [("write_text", {"path": PROTECTED, "content": "pass\n"})], readonly_paths=["tests/**"], middleware=[caller])

    assert agent.middleware[0] is caller
    assert isinstance(agent.middleware[1], ReadonlyPathsMiddleware)
    assert len(agent.middleware) == 2
    assert caller.seen[0] == "write_text"
    assert states == ("denied", "succeeded")
