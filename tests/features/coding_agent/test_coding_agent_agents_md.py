"""FILE: tests/features/coding_agent/test_coding_agent_agents_md.py

PURPOSE: Pin CodingAgent's AGENTS.md loading and the shared coding context window: the root folder's AGENTS.md reaches the model after the system prompt and before the user message, read once, capped at 32 KiB without splitting a character, and placed ahead of the caller's own context manager without changing it.
ROLE IN CODEBASE: Drives vidbyte.CodingAgent through BaseAgent's real run loop with the offline scripted model from conftest.py, and calls CodingContextWindow (vidbyte/agents/coding_context/window.py) and CodingContextSectionText (vidbyte/lib/dataclasses/coding.py) directly.
ARCHITECTURE NOTE: Assertions read the system string and the prompt the scripted model actually received, so a section that is built but never rendered fails here. PromptRecorder wraps the conftest runner only to keep the user prompt, which the runner receives positionally and does not record.
FUNCTION INVENTORY: test_agents_md_is_shown_* (FR-10); test_without_agents_md_* (byte-identical request); test_load_agents_false_* (FR-3); test_lowercase_* / test_exact_name_* / test_parent_folder_* (FR-4, FR-5); test_large_file_* / test_file_of_exactly_* (FR-8); test_blank_file_* / test_file_bytes_* (FR-8, FR-9); test_agents_md_directory_* / test_unreadable_* (FR-7); test_load_agents_must_be_* (FR-2); test_caller_context_manager_* (FR-11, FR-12); test_fork_* (FR-13); test_cwd_change_* / test_edits_after_* (read once); test_window_* and test_section_record_* (the shared helper's contract, FR-11, FR-14).
COMMON MODIFICATION PATTERNS: A sibling section adds its own test module; extend the window tests here only when the window's contract changes.
WHAT NOT TO DO IN THIS FILE: 1. Do not monkeypatch the loader or the window; build real files under tmp_path. 2. Do not open sockets or use real keys. 3. Do not assert private CodingAgent attributes; use the request, agent.context_manager, and agent.tools.
KNOWN EDGE CASES: The exact-name-wins case needs a case-sensitive filesystem and is skipped elsewhere (Windows, default macOS). The truncation cases build files whose 32,768th byte falls inside a multibyte character.
RELATED DOCS: docs/design/coding-agent-agents-md.md; tests/features/coding_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_agents_md.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from tests.agent_test_support import bind_test_runner
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.coding_context.window import CodingContextWindow
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.constants.coding import CODING_AGENTS_MD_MAX_BYTES
from vidbyte.lib.dataclasses.coding import CodingContextSectionText
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCall

SYSTEM_PROMPT = "You are a careful engineer. SYSTEM-PROMPT-MARKER."
USER_MESSAGE = "Fix the failing test. USER-MESSAGE-MARKER"
RULES = "# Rules\n\nUse uv, not pip.\nRun python lint/run.py before committing.\n"
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


def _agent(coding_agent_cls: type, root_dir: str | Path, **options: object) -> Any:
    # Builds a CodingAgent with fixed name, prompt, and offline model identity.
    return coding_agent_cls(name="coder", system_prompt=SYSTEM_PROMPT, root_dir=root_dir, **OFFLINE_MODEL, **options)


def _first_request(agent: BaseAgent, script_model: type) -> tuple[dict[str, Any], str]:
    # Runs one turn that ends at once and returns what the model received: the request and the user prompt.
    recorder = PromptRecorder(script_model([], final_answer="done"))
    bind_test_runner(agent, recorder)
    agent.run(USER_MESSAGE)
    return recorder.requests[0], recorder.prompts[0]


def _system(agent: BaseAgent, script_model: type) -> str:
    return _first_request(agent, script_model)[0]["system"]


def _shown(agent: BaseAgent) -> str:
    # The AGENTS.md section text the agent placed, read through ContextManager's public API.
    item = agent.context_manager.get_by_id(CodingContextSection.AGENTS_MD.value)
    assert item is not None
    return item.content


def _write(path: Path, text: str) -> None:
    # Writes UTF-8 bytes exactly, so Windows text mode never adds carriage returns.
    path.write_bytes(text.encode("utf-8"))


def _case_sensitive(folder: Path) -> bool:
    # True when two names that differ only in case are two different files here.
    probe = folder / "CaseProbe"
    probe.write_text("probe", encoding="utf-8")
    sensitive = not (folder / "caseprobe").exists()
    probe.unlink()
    return sensitive


def _section(kind: CodingContextSection) -> CodingContextSectionText:
    return CodingContextSectionText(section=kind, title=f"Title {kind.name}", content=f"Body {kind.name}")


def test_agents_md_is_shown_after_the_system_prompt_and_before_the_user_message(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-10: the rules reach the model once, between the system prompt and the user message, with their source path.
    _write(tmp_path / "AGENTS.md", RULES)

    request, prompt = _first_request(_agent(coding_agent_cls, tmp_path), script_model)
    system = request["system"]

    assert system.index(SYSTEM_PROMPT) < system.index(AGENTS_HEADER) < system.index(RULES.strip())
    assert f"Source: {tmp_path.resolve() / 'AGENTS.md'}" in system
    assert system.count("Use uv, not pip.") == 1
    assert prompt == USER_MESSAGE
    assert "Use uv, not pip." not in prompt


def test_without_agents_md_the_request_equals_a_plain_base_agents(coding_agent_cls, script_model, tmp_path) -> None:
    # Silent failure: an agent with nothing to load must send exactly what it sent before this feature.
    coding = _agent(coding_agent_cls, tmp_path, load_environment=False)
    plain = BaseAgent(name="coder", system_prompt=SYSTEM_PROMPT, tools=coding.tools.all(), permission_policy=PermissionPolicy.allow_all(), **OFFLINE_MODEL)

    coding_request, coding_prompt = _first_request(coding, script_model)
    plain_request, plain_prompt = _first_request(plain, script_model)

    assert coding.context_manager is None
    assert coding_request == plain_request
    assert coding_prompt == plain_prompt
    assert ZONE_HEADER not in coding_request["system"]


def test_load_agents_false_shows_no_agents_md(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-3: the switch turns the section off even when the file is there.
    _write(tmp_path / "AGENTS.md", RULES)

    agent = _agent(coding_agent_cls, tmp_path, load_agents=False, load_environment=False)
    system = _system(agent, script_model)

    assert agent.context_manager is None
    assert "Use uv, not pip." not in system
    assert ZONE_HEADER not in system


def test_load_agents_false_never_touches_the_file(coding_agent_cls, tmp_path) -> None:
    # FR-3: an AGENTS.md that would fail construction is never looked at when loading is off.
    (tmp_path / "AGENTS.md").mkdir()

    agent = _agent(coding_agent_cls, tmp_path, load_agents=False, load_environment=False)

    assert agent.context_manager is None


def test_lowercase_agents_md_is_loaded_when_the_exact_name_is_absent(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-5: the user writes the file name in lower case; it is found under its real name on every platform.
    _write(tmp_path / "agents.md", "Lowercase rules apply.\n")

    system = _system(_agent(coding_agent_cls, tmp_path), script_model)

    assert "### [coding:agents_md] Repository instructions (agents.md)" in system
    assert "Lowercase rules apply." in system


def test_exact_name_wins_over_case_variants_then_the_first_sorted_variant(coding_agent_cls, tmp_path) -> None:
    # FR-5: with several variants the choice is deterministic: AGENTS.md, else the first name in sorted order.
    if not _case_sensitive(tmp_path):
        pytest.skip("Needs a case-sensitive filesystem to hold AGENTS.md and agents.md side by side.")
    _write(tmp_path / "AGENTS.md", "Upper rules.\n")
    _write(tmp_path / "agents.md", "Lower rules.\n")
    _write(tmp_path / "Agents.md", "Mixed rules.\n")

    assert _shown(_agent(coding_agent_cls, tmp_path)) == "Upper rules.\n"

    (tmp_path / "AGENTS.md").unlink()
    assert _shown(_agent(coding_agent_cls, tmp_path)) == "Mixed rules.\n"


def test_parent_folder_agents_md_is_not_searched(coding_agent_cls, tmp_path) -> None:
    # FR-4: only the root folder's own file counts; a parent's AGENTS.md is never read.
    _write(tmp_path / "AGENTS.md", "Parent rules.\n")
    project = tmp_path / "project"
    project.mkdir()

    agent = _agent(coding_agent_cls, project, load_environment=False)

    assert agent.context_manager is None


@pytest.mark.parametrize("straddler", ["é", "€", "\U0001f600"], ids=["2-byte", "3-byte", "4-byte"])
def test_large_file_is_cut_at_the_cap_without_splitting_a_character(coding_agent_cls, script_model, tmp_path, straddler) -> None:
    # FR-8 edge: a 40 KiB file whose cap falls inside a character shows only whole characters and an exact read_lines hint.
    cap = CODING_AGENTS_MD_MAX_BYTES
    head = (("a" * 63 + "\n") * (cap // 64))[: cap - 1]
    tail_size = FORTY_KIB - len(head) - len(straddler.encode("utf-8"))
    (tmp_path / "AGENTS.md").write_bytes((head + straddler + "b" * tail_size).encode("utf-8"))
    agent = _agent(coding_agent_cls, tmp_path)

    shown = _shown(agent)
    note = f'[AGENTS.md was truncated at {cap - 1} of {FORTY_KIB} bytes. Read the rest with the read_lines tool (path "AGENTS.md"), starting at line 512.]'
    assert shown == f"{head}\n\n{note}"
    assert "�" not in shown
    assert shown in _system(agent, script_model)

    # The hint is actionable: read_lines from that line returns the cut line in full, including the dropped character.
    [read_lines] = [tool for tool in agent.tools.all() if tool.name == "read_lines"]
    result = asyncio.run(read_lines.execute(ToolCall("read_lines", {"path": "AGENTS.md", "start": 512})))
    assert result.output.startswith("a" * 63 + straddler + "b")


def test_file_of_exactly_the_cap_is_shown_whole_with_no_truncation_line(coding_agent_cls, tmp_path) -> None:
    # FR-8 edge: the cap is inclusive; a file of exactly 32,768 bytes is not truncated.
    text = ("r" * 63 + "\n") * (CODING_AGENTS_MD_MAX_BYTES // 64)
    _write(tmp_path / "AGENTS.md", text)

    assert _shown(_agent(coding_agent_cls, tmp_path)) == text


@pytest.mark.parametrize("raw", [b"", b"   \n\t\r\n", b"\xef\xbb\xbf \n"], ids=["empty", "whitespace", "bom-and-whitespace"])
def test_blank_file_adds_no_section(coding_agent_cls, script_model, tmp_path, raw) -> None:
    # FR-9 edge: a file with nothing to say adds no section and no primitives zone.
    (tmp_path / "AGENTS.md").write_bytes(raw)

    agent = _agent(coding_agent_cls, tmp_path, load_environment=False)

    assert agent.context_manager is None
    assert ZONE_HEADER not in _system(agent, script_model)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(b"rule one \xff\xfe rule two\n", "rule one �� rule two\n"), (b"\xef\xbb\xbfUse uv.\n", "Use uv.\n")],
    ids=["invalid-utf8", "byte-order-mark"],
)
def test_file_bytes_are_decoded_leniently(coding_agent_cls, tmp_path, raw, expected) -> None:
    # FR-8 hidden failure: invalid UTF-8 is replaced, not raised, and a byte-order mark is not shown to the model.
    (tmp_path / "AGENTS.md").write_bytes(raw)

    assert _shown(_agent(coding_agent_cls, tmp_path)) == expected


def test_agents_md_directory_fails_construction_naming_the_path(coding_agent_cls, tmp_path) -> None:
    # FR-7: a present-but-broken AGENTS.md fails loudly instead of being skipped.
    broken = tmp_path / "AGENTS.md"
    broken.mkdir()

    with pytest.raises(ConfigurationError) as raised:
        _agent(coding_agent_cls, tmp_path)

    assert str(broken.resolve()) in str(raised.value)
    assert raised.value.details["path"] == str(broken.resolve())


def test_unreadable_agents_md_fails_construction_naming_the_path(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # FR-7: a permission error on a present file fails loudly; Path.open is patched so the case runs on every platform.
    agents_md = tmp_path / "AGENTS.md"
    _write(agents_md, RULES)
    real_open = Path.open

    def refuse_agents_md(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == "AGENTS.md":
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", refuse_agents_md)
    with pytest.raises(ConfigurationError) as raised:
        _agent(coding_agent_cls, tmp_path)

    assert str(agents_md.resolve()) in str(raised.value)
    assert raised.value.details == {"path": str(agents_md.resolve()), "error": "PermissionError"}
    assert isinstance(raised.value.__cause__, PermissionError)


@pytest.mark.parametrize("bad", ["yes", 1, 0, None, "false"], ids=["yes", "one", "zero", "none", "false-string"])
def test_load_agents_must_be_a_real_bool(coding_agent_cls, tmp_path, bad) -> None:
    # FR-2 hidden assumption: a truthy stand-in never switches loading on or off.
    with pytest.raises(ConfigurationError, match="load_agents") as raised:
        _agent(coding_agent_cls, tmp_path, load_agents=bad)

    assert raised.value.details["parameter"] == "load_agents"


def _snapshot(manager: ContextManager) -> tuple[object, ...]:
    # Everything a caller could observe about its manager: managed entries, their placements, plain items, metadata.
    entries = manager.registry_items()
    return (entries, tuple(manager.placement_for(primitive_id) for primitive_id, _ in entries), manager.items(), dict(manager.metadata))


def test_caller_context_manager_renders_after_agents_md_and_is_never_changed(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-11 hidden failure: the caller's context still reaches the model, after the section, and the caller's object is untouched.
    _write(tmp_path / "AGENTS.md", RULES)
    caller = ContextManager(metadata={"team": "sdk"})
    caller.add(TextContextItem(title="Caller plain note", content="CALLER-PLAIN-BODY"))
    caller.place_after_system_prompt(TextContextItem(title="Caller top note", content="CALLER-TOP-BODY", primitive_id="caller:top"))
    caller.place_after_tools(TextContextItem(title="Caller end note", content="CALLER-END-BODY", primitive_id="caller:end"))
    before = _snapshot(caller)

    agent = _agent(coding_agent_cls, tmp_path, context_manager=caller)
    system = _system(agent, script_model)

    assert system.index(SYSTEM_PROMPT) < system.index("Use uv, not pip.") < system.index("CALLER-TOP-BODY") < system.index("CALLER-END-BODY")
    assert "CALLER-PLAIN-BODY" in system
    assert agent.context_manager is not caller
    assert agent.context_manager.placement_for("caller:end") is ContextWindowPlacement.END_OF_CONTEXT
    assert _snapshot(caller) == before


def test_fork_keeps_the_agents_md_section(coding_agent_cls, script_model, tmp_path) -> None:
    # FR-13: a forked child shows the same AGENTS.md text from its own copy of the manager.
    _write(tmp_path / "AGENTS.md", RULES)
    agent = _agent(coding_agent_cls, tmp_path)

    child = agent.fork()
    system = _system(child, script_model)

    assert AGENTS_HEADER in system
    assert "Use uv, not pip." in system
    assert child.context_manager is not agent.context_manager


def test_cwd_change_after_construction_keeps_the_root_folders_file(coding_agent_cls, script_model, tmp_path, monkeypatch) -> None:
    # Hidden assumption: a relative root_dir is resolved once, so a later chdir never swaps in another folder's AGENTS.md.
    project = tmp_path / "project"
    elsewhere = tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    _write(project / "AGENTS.md", "Project rules.\n")
    _write(elsewhere / "AGENTS.md", "Elsewhere rules.\n")
    monkeypatch.chdir(tmp_path)

    agent = _agent(coding_agent_cls, "project")
    monkeypatch.chdir(elsewhere)
    system = _system(agent, script_model)

    assert "Project rules." in system
    assert "Elsewhere rules." not in system


def test_edits_after_construction_are_not_seen_until_a_new_agent_is_built(coding_agent_cls, script_model, tmp_path) -> None:
    # Read once: the text is fixed at construction, as documented, and a new agent picks up the edit.
    agents_md = tmp_path / "AGENTS.md"
    _write(agents_md, "First rules.\n")
    agent = _agent(coding_agent_cls, tmp_path)

    _write(agents_md, "Edited rules.\n")
    system = _system(agent, script_model)

    assert "First rules." in system
    assert "Edited rules." not in system
    assert _shown(_agent(coding_agent_cls, tmp_path)) == "Edited rules.\n"


def test_window_renders_sections_in_enum_order_whatever_the_input_order() -> None:
    # FR-11 silent failure: sections listed out of order, with gaps, still render in CodingContextSection order.
    records = [_section(kind) for kind in CodingContextSection]

    window = CodingContextWindow.build((None, *reversed(records), None), None)

    assert window is not None
    assert [primitive_id for primitive_id, _ in window.registry_items()] == [kind.value for kind in CodingContextSection]
    assert all(window.placement_for(kind.value) is ContextWindowPlacement.TOP_OF_CONTEXT for kind in CodingContextSection)
    zone = window.render_primitives_zone()
    positions = [zone.index(f"### [{kind.value}] Title {kind.name}") for kind in CodingContextSection]
    assert positions == sorted(positions)


def test_window_with_no_sections_returns_the_callers_manager_unchanged() -> None:
    # Silent failure: nothing to add means BaseAgent gets exactly what the caller passed, the same object or None.
    caller = ContextManager()

    assert CodingContextWindow.build((), None) is None
    assert CodingContextWindow.build((None,), None) is None
    assert CodingContextWindow.build((None,), caller) is caller


@pytest.mark.parametrize(
    ("sections", "manager", "message"),
    [
        (("not a section",), None, "CodingContextSectionText"),
        ((_section(CodingContextSection.AGENTS_MD), _section(CodingContextSection.AGENTS_MD)), None, "must not repeat a section"),
        ((_section(CodingContextSection.AGENTS_MD),), object(), "context_manager must be a ContextManager"),
    ],
    ids=["not-a-record", "repeated-section", "not-a-manager"],
)
def test_window_rejects_wiring_mistakes(sections, manager, message) -> None:
    # FR-11 hidden assumption: a sibling loader wired wrongly fails at construction, not as odd rendering later.
    with pytest.raises(ConfigurationError, match=message):
        CodingContextWindow.build(sections, manager)


def test_window_section_wins_over_a_caller_primitive_with_its_id() -> None:
    # FR-12 hidden failure: a manager taken from another CodingAgent cannot replace this agent's own section.
    caller = ContextManager()
    caller.place_after_tools(TextContextItem(title="Stale", content="STALE-AGENTS-MD", primitive_id=CodingContextSection.AGENTS_MD.value))

    window = CodingContextWindow.build((_section(CodingContextSection.AGENTS_MD),), caller)

    assert window is not None
    assert window.get_by_id(CodingContextSection.AGENTS_MD.value).content == "Body AGENTS_MD"
    assert window.placement_for(CodingContextSection.AGENTS_MD.value) is ContextWindowPlacement.TOP_OF_CONTEXT
    assert caller.get_by_id(CodingContextSection.AGENTS_MD.value).content == "STALE-AGENTS-MD"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"section": "coding:agents_md"}, "section"),
        ({"title": "   "}, "title"),
        ({"title": 3}, "title"),
        ({"content": ""}, "content"),
        ({"source": " "}, "source"),
    ],
    ids=["section-string", "blank-title", "non-string-title", "empty-content", "blank-source"],
)
def test_section_record_rejects_bad_fields_naming_the_field(overrides, field) -> None:
    # Hidden assumption: a loader cannot hand the window a section that would render blank or under the wrong id.
    fields: dict[str, object] = {"section": CodingContextSection.AGENTS_MD, "title": "Title", "content": "Body", "source": None, **overrides}

    with pytest.raises(ConfigurationError, match=field):
        CodingContextSectionText(**fields)
