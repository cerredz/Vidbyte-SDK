"""FILE: tests/features/coding_agent/test_coding_agent_contract.py

PURPOSE: Pin CodingAgent's construction contract: its public names, a constructor that adds only root_dir, four keys, tools, and a policy default to BaseAgent's, one absolute root shared by all six root-bound tools, and fail-fast validation of everything else.
ROLE IN CODEBASE: Calls vidbyte.CodingAgent, vidbyte.agents.base.BaseAgent, and the tools in agent.tools directly; offline, with real temporary folders and, for bash, a real subprocess.
ARCHITECTURE NOTE: "Same settings as BaseAgent" is proven differentially: a CodingAgent and a BaseAgent built from the same keywords, tools, and allow-all policy must export identical RunState snapshots.
FUNCTION INVENTORY: test_public_names_* (AC-20); test_coding_agent_adds_only_* (INV-1, §8.5); test_*_same_state_as_* (INV-2, INV-8); test_restored_state_* (AC-21); test_caller_tools_* (AC-9); test_caller_tool_named_* (AC-8); test_base_agent_identity_errors_* (AC-10); test_root_dir_that_is_not_* (AC-11, EC-6, D-8); test_root_bound_tools_* (INV-4, EC-7).
COMMON MODIFICATION PATTERNS: When BaseAgent gains a keyword that RunState exports, add it to PARITY_KEYWORDS; when the spec adds a CodingAgent parameter, extend EXPECTED_SIGNATURE in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not monkeypatch BaseAgent.__init__ (tests/agent_test_support.py forbids it). 2. Do not assert private attributes of CodingAgent; use agent.root_dir, agent.tools, export_state(), and tool results.
KNOWN EDGE CASES: A relative root_dir must be resolved once at construction; FileSystemToolConfig re-resolves a relative root at every call, so a later chdir would silently move writes. BaseAgent drops caller items that are not tools, so only real tools are used here.
RELATED DOCS: tests/features/coding_agent/FEATURE.md; docs/spec/coding-agent/spec.md (§6.1, §6.2, §8.5, §9.2)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_contract.py
"""

from __future__ import annotations

import copy
import inspect
from pathlib import Path

import pytest

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError, ToolRegistrationError
from vidbyte.tools import BaseTool, Tools
from vidbyte.tools.security import PermissionPolicy
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec, ToolStatus

NO_KEY_TOOL_NAMES = ("bash", "read_lines", "write_text", "replace_text", "glob", "grep", "direct_http_fetch")

# spec §8.5: every explicit keyword-only parameter of CodingAgent.__init__ and its default; everything else is **kwargs.
EXPECTED_SIGNATURE = {
    "root_dir": inspect.Parameter.empty,
    "firecrawl_api_key": None,
    "browserbase_api_key": None,
    "parallel_api_key": None,
    "tavily_api_key": None,
    "tools": (),
    "permission_policy": None,
}

# BaseAgent keywords that RunState exports, so a pass-through mistake shows up as a state difference.
PARITY_KEYWORDS = {
    "name": "coder",
    "system_prompt": "Make the smallest correct change and explain it.",
    "provider": "openai",
    "model_name": "gpt-4.1-mini",
    "temperature": 0.2,
    "timeout_seconds": 45.0,
    "max_tool_rounds": 12,
    "max_tokens": 4096,
    "description": "Edits the repository.",
    "capabilities": ("python", "shell"),
    "metadata": {"team": "sdk"},
    "run_id": "run-coding-parity",
    "output_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
}

OFFLINE_MODEL = {"provider": "openai", "model_name": "gpt-4.1-mini"}


class CallerTool(BaseTool):
    """A caller-supplied tool whose model-facing name is chosen by the test."""

    def __init__(self, name: str) -> None:
        self._tool_name = name

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self._tool_name, description="Caller tool used to probe catalog merging.")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success(self._tool_name, "ok")


async def _execute(tool: BaseTool, **arguments: object) -> ToolResult:
    # Runs one tool exactly as the runtime would after its permission and validation checks.
    return await tool.execute(ToolCall(tool.name, arguments))


def test_public_names_resolve_to_one_coding_agent_class_and_one_bash_tool_class() -> None:
    # AC-20 / FR-1 / FR-12: the root, the agents package, and the defining modules agree.
    import vidbyte
    import vidbyte.agents
    import vidbyte.tools.builtins
    from vidbyte import CodingAgent as root_export
    from vidbyte.agents import CodingAgent as agents_export
    from vidbyte.agents.coding import CodingAgent as defined
    from vidbyte.tools.builtins import BashTool as builtins_export
    from vidbyte.tools.builtins.bash import BashTool as bash_defined

    assert root_export is agents_export is defined
    assert builtins_export is bash_defined
    assert "CodingAgent" in vidbyte.__all__
    assert "CodingAgent" in vidbyte.agents.__all__
    assert "BashTool" in vidbyte.tools.builtins.__all__
    assert issubclass(defined, BaseAgent)
    assert issubclass(bash_defined, BaseTool)


def test_coding_agent_adds_only_a_constructor_with_root_keys_tools_and_policy(coding_agent_cls) -> None:
    # INV-1 / D-1 / D-8 / §8.5: one keyword-only constructor over **kwargs; no BaseAgent behavior is overridden.
    parameters = inspect.signature(coding_agent_cls.__init__).parameters
    explicit = {name: parameter for name, parameter in parameters.items() if name != "self" and parameter.kind is not inspect.Parameter.VAR_KEYWORD}
    assert {name: parameter.default for name, parameter in explicit.items()} == EXPECTED_SIGNATURE
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in explicit.values())
    assert [parameter.kind for parameter in parameters.values()].count(inspect.Parameter.VAR_KEYWORD) == 1

    # A same-named method or property, public or private, would silently replace BaseAgent behavior (INV-22 needs generate_reply untouched).
    overridden = sorted(
        name
        for name in vars(coding_agent_cls)
        if name != "__init__" and (callable(getattr(BaseAgent, name, None)) or isinstance(inspect.getattr_static(BaseAgent, name, None), property))
    )
    assert overridden == []
    assert coding_agent_cls.generate_reply is BaseAgent.generate_reply


def test_coding_agent_exports_the_same_state_as_an_equivalent_base_agent(coding_agent_cls, tmp_path) -> None:
    # INV-2 / INV-7 / INV-8 / §9.1: pass-through keywords keep their meaning, the prompt is untouched, and no key or root enters RunState.
    coding = coding_agent_cls(root_dir=tmp_path, tavily_api_key="tvly-test-key", **copy.deepcopy(PARITY_KEYWORDS))
    plain = BaseAgent(tools=coding.tools.all(), permission_policy=PermissionPolicy.allow_all(), **copy.deepcopy(PARITY_KEYWORDS))

    assert coding.export_state() == plain.export_state()


def test_restored_state_keeps_the_seven_tools_and_the_allow_all_policy(coding_agent_cls, tmp_path) -> None:
    # AC-21: the documented restore path, BaseAgent.restore(state, tools=agent.tools.all()), loses nothing.
    agent = coding_agent_cls(name="coder", system_prompt="Code.", root_dir=tmp_path, tavily_api_key="tvly-test-key", **OFFLINE_MODEL)

    restored = BaseAgent.restore(agent.export_state(), tools=agent.tools.all())

    assert restored.tools.names() == agent.tools.names()
    assert restored.permission_policy.allowed == frozenset(ToolPermission)
    assert "__resume_tool_mismatch__" not in restored.metadata


@pytest.mark.parametrize("as_caller_input", [list, Tools], ids=["sequence", "tools-catalog"])
def test_caller_tools_follow_the_seven_coding_tools_in_caller_order(coding_agent_cls, tmp_path, as_caller_input) -> None:
    # AC-9 / INV-3 / FR-7: the seven come first, then the caller's own tool objects, in the caller's order.
    caller_tools = [CallerTool("lint_report"), CallerTool("open_ticket")]

    agent = coding_agent_cls(name="coder", system_prompt="Code.", root_dir=tmp_path, tools=as_caller_input(caller_tools), **OFFLINE_MODEL)

    assert agent.tools.names() == NO_KEY_TOOL_NAMES + ("lint_report", "open_ticket")
    assert agent.tools.all()[7:] == tuple(caller_tools)


@pytest.mark.parametrize("taken_name", ["bash", "glob", "direct_http_fetch"])
def test_caller_tool_named_like_a_coding_tool_is_rejected_at_construction(coding_agent_cls, tmp_path, taken_name) -> None:
    # AC-8 / EC-4 / D-7: a collision fails loudly instead of silently replacing one of the seven.
    with pytest.raises(ToolRegistrationError, match=f"Tool already exists: {taken_name}"):
        coding_agent_cls(name="coder", system_prompt="Code.", root_dir=tmp_path, tools=[CallerTool(taken_name)], **OFFLINE_MODEL)


@pytest.mark.parametrize(
    ("identity", "expected_error", "expected_text"),
    [
        ({"name": "coder", "system_prompt": ""}, AgentExecutionError, "Agent system_prompt is required."),
        ({"name": "", "system_prompt": "Code."}, AgentExecutionError, "Agent name cannot be empty."),
        ({"name": "coder"}, TypeError, "system_prompt"),
        ({"system_prompt": "Code."}, TypeError, "name"),
    ],
    ids=["empty-prompt", "empty-name", "missing-prompt", "missing-name"],
)
def test_base_agent_identity_errors_pass_through_unchanged(coding_agent_cls, tmp_path, identity, expected_error, expected_text) -> None:
    # AC-10 / NG-2 / FR-2: CodingAgent supplies neither a default prompt nor a default name.
    with pytest.raises(expected_error) as caught:
        coding_agent_cls(root_dir=tmp_path, **identity, **OFFLINE_MODEL)

    assert expected_text in str(caught.value)


@pytest.mark.parametrize("bad_root", ["missing-folder", "a-file", "integer", "none", "omitted"])
def test_root_dir_that_is_not_an_existing_directory_is_rejected_at_construction(coding_agent_cls, tmp_path, bad_root) -> None:
    # AC-11 / EC-6 / D-8: one clear error at construction instead of a different failure on every later tool call.
    (tmp_path / "a-file").write_text("not a folder", encoding="utf-8")
    candidates = {"missing-folder": tmp_path / "missing-folder", "a-file": tmp_path / "a-file", "integer": 42, "none": None}
    root_keyword = {} if bad_root == "omitted" else {"root_dir": candidates[bad_root]}
    expected_error = TypeError if bad_root == "omitted" else ConfigurationError

    with pytest.raises(expected_error) as caught:
        coding_agent_cls(name="coder", system_prompt="Code.", **root_keyword, **OFFLINE_MODEL)

    if isinstance(caught.value, ConfigurationError):
        # Detail values are compared as text, not repr, so a Windows path's backslashes are not doubled.
        reported = " ".join([str(caught.value), *(str(value) for value in caught.value.details.values())])
        assert str(candidates[bad_root]) in reported


@pytest.mark.asyncio
async def test_root_bound_tools_and_bash_keep_the_construction_root_after_chdir(coding_agent_cls, tmp_path, monkeypatch) -> None:
    # INV-4 / EC-7 / FR-4: a relative root_dir is resolved once; after chdir into a folder holding a same-named decoy, every tool still works in the original root.
    project = tmp_path / "start" / "proj"
    decoy = tmp_path / "elsewhere" / "proj"
    project.mkdir(parents=True)
    decoy.mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "start")
    agent = coding_agent_cls(name="coder", system_prompt="Code.", root_dir="proj", **OFFLINE_MODEL)
    monkeypatch.chdir(tmp_path / "elsewhere")
    tools = dict(zip(agent.tools.names(), agent.tools.all()))

    results = [
        await _execute(tools["write_text"], path="notes.txt", content="alpha beta"),
        await _execute(tools["replace_text"], path="notes.txt", search="beta", replacement="gamma"),
        await _execute(tools["read_lines"], path="notes.txt"),
        await _execute(tools["glob"], pattern="*.txt"),
        await _execute(tools["grep"], pattern="gamma"),
        await _execute(tools["bash"], command="cat notes.txt"),
    ]

    assert agent.root_dir == project.resolve()
    assert [result.status for result in results] == [ToolStatus.SUCCESS] * 6
    assert (project / "notes.txt").read_text(encoding="utf-8") == "alpha gamma"
    assert list(decoy.iterdir()) == []
    _, _, read, globbed, grepped, shelled = results
    assert "alpha gamma" in read.output
    assert "notes.txt" in globbed.output
    assert "notes.txt" in grepped.output
    assert shelled.output.splitlines()[0] == "alpha gamma"
    assert isinstance(agent.root_dir, Path)
