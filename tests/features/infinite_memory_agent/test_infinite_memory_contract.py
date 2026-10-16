"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_contract.py

PURPOSE: Pins the InfiniteMemory agent's static contract: public import paths and exports, enum values, the 40-leaf prompt family, the runtime registry entry and its refusal outside InfiniteMemoryAgent, the session opt-out, settings validation and defaults, the exact tools and schemas the root's model is offered, the TokenEstimate helper, prompt text free of coding-only rules, and the complexity budget. Since the re-review it also proves that a read-only seed is copied again, unchanged, each time an agent attaches.
ROLE IN CODEBASE: Contract layer of tests/features/infinite_memory_agent/ (spec AC-2, AC-3, AC-4, AC-25, AC-27, AC-30, AC-39; INV-1..INV-3, INV-6, INV-21, INV-33, INV-36; EC-2, EC-3, EC-33, EC-34; FR-15; NFR-1; re-review finding R-26). Exercises vidbyte/agents/infinite/, vidbyte/lib/enums/infinite.py, vidbyte/lib/constants/infinite.py, vidbyte/lib/util/text.py, vidbyte/lib/registries/runtimes.py and the infinite_memory prompt family.
ARCHITECTURE NOTE: Every feature symbol is imported inside the test that needs it, so before the feature exists each test fails on its own ImportError and the rest of the suite still collects. Tool offers are read from what the scripted runner receives on the root's first call, not from the agent's internals.
FUNCTION INVENTORY: test_public_names_import_from_every_documented_path (AC-27, INV-1); test_prompt_family_has_exactly_the_forty_documented_leaves (AC-27, INV-36); test_enum_values_are_the_documented_lowercase_strings (section 8.5); test_runtime_type_resolves_and_refuses_outside_its_agent (AC-3, INV-3, EC-33); test_session_refuses_the_agent (AC-25, EC-34); test_loop_and_limit_defaults_match_the_spec (AC-39, section 9.3); test_construction_rejects_each_invalid_setting (AC-2, EC-2); test_attaching_a_workspace_already_over_a_cap_is_refused (INV-21, EC-3); test_a_read_only_seed_is_copied_again_each_time_an_agent_attaches (re-review R-26, INV-21, section 9.2, AC-30);test_root_is_offered_exactly_the_preset_tools_plus_its_extra (AC-4, INV-6); test_launch_and_remember_schemas_follow_the_documented_shape (section 9.2, INV-9); test_token_estimate_counts_characters_and_cuts_to_a_prefix (FR-15, D-17); test_prompt_family_text_carries_no_coding_only_rules (INV-33, NFR-5); test_new_modules_stay_inside_the_complexity_budget (NFR-1); test_construction_rejects_a_non_settings_object (AC-2, INV-2); test_entries_written_by_hand_in_the_documented_shape_are_accepted (section 9.1).
COMMON MODIFICATION PATTERNS: When the spec adds a prompt leaf, add it to EXPECTED_LEAVES. When a setting gains a bound, add one row to INVALID_SETTINGS with the field name and the bad value the error must name.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level (see infinite_memory_fixtures.py). 2. Do not compare tool descriptions to hand-written text; descriptions come from the prompt catalog. 3. Do not loosen the exact tool-name sets to subset checks; INV-6 is an exact list.
KNOWN EDGE CASES: A ConfigurationError may carry the field in `details` instead of the message, so error_text joins both. The settings-level cases must leave no workspace folder behind, so they never build the agent past its settings.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-agent/spec.md sections 6.1, 6.2, 8.4, 8.5, 9.2, 9.3 and 12.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_contract.py -q
"""

from __future__ import annotations

import ast
import importlib
import json
import math
import os
import random
import re
import stat
import string
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    ROOT,
    ScriptedTree,
    build_agent,
    build_settings,
    entry_record,
    int_token,
    project_dir,
    reply,
    template_regex,
    workspace_root,
    write_jsonl,
)
from vidbyte import BaseAgent, tool
from vidbyte.lib.errors import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]

# The 40 leaves of spec section 9.2, in its order.
EXPECTED_LEAVES = (
    "root_system_prompt",
    "generator_system_prompt",
    "verifier_system_prompt",
    "task_prompt",
    "verifier_task_prompt",
    "resume_prompt",
    "result_card",
    "replayed_label",
    "launch_rejected_prompt",
    "memory_rejected_prompt",
    "remember_saved_prompt",
    "remember_staged_prompt",
    "note_saved_prompt",
    "entry_dropped_prompt",
    "quota_line",
    "map_header",
    "launch_tool_description",
    "launch_tasks_description",
    "launch_name_description",
    "launch_goal_description",
    "launch_done_criteria_description",
    "launch_generator_prompt_description",
    "launch_verifier_prompt_description",
    "launch_context_description",
    "launch_tools_description",
    "remember_tool_description",
    "remember_kind_description",
    "remember_text_description",
    "remember_tags_description",
    "remember_refs_description",
    "remember_supersedes_description",
    "write_note_tool_description",
    "note_path_description",
    "write_note_text_description",
    "write_note_file_description",
    "edit_file_tool_description",
    "edit_file_old_text_description",
    "edit_file_new_text_description",
    "drop_entry_tool_description",
    "drop_entry_id_description",
)

# The twelve new modules of spec section 8.4 (the folder's 8 plus toolset, enums, constants, records).
BUDGET_MODULES = (
    "vidbyte/agents/infinite/__init__.py",
    "vidbyte/agents/infinite/agent.py",
    "vidbyte/agents/infinite/settings.py",
    "vidbyte/agents/infinite/runtime.py",
    "vidbyte/agents/infinite/workspace.py",
    "vidbyte/agents/infinite/journal.py",
    "vidbyte/agents/infinite/memory.py",
    "vidbyte/agents/infinite/launch.py",
    "vidbyte/tools/toolsets/infinite.py",
    "vidbyte/lib/enums/infinite.py",
    "vidbyte/lib/constants/infinite.py",
    "vidbyte/lib/dataclasses/infinite.py",
)

# Words that would only appear in a coding-only or single-writer rule (INV-33).
CODING_ONLY_WORDS = (
    r"\bworktrees?\b",
    r"\bpull[- ]requests?\b",
    r"\bsingle[- ]writer\b",
    r"\bone writer\b",
    r"\bgit\b",
    r"\brepo(?:s|sitory|sitories)?\b",
)

PRESET_TOOLS = {"bash", "grep", "read_lines", "launch_subagent", "remember", "write_note", "isDone"}


@tool(name="web_fetch")
def web_fetch(url: str) -> str:
    """Fetch a public web page and return its text."""
    return f"PAGE:{url}"


@tool(name="grep")
def shadow_grep(pattern: str) -> str:
    """A developer tool that collides with the preset grep."""
    return pattern


def error_text(error: BaseException) -> str:
    """The message plus any structured details, where an error may name its field."""
    return f"{error} {json.dumps(getattr(error, 'details', None), default=str)}"


# ---------------------------------------------------------------- exports and catalog


def test_public_names_import_from_every_documented_path() -> None:
    """AC-27, INV-1: every documented import path works and yields the same objects, and the root names are in the public contract."""
    import vidbyte
    from vidbyte import InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteMemoryPreset, InfiniteWorkspaceSettings
    from vidbyte.agents import InfiniteMemoryAgent as agents_agent
    from vidbyte.agents import InfiniteMemoryAgentSettings as agents_settings
    from vidbyte.agents import InfiniteMemoryRuntime
    from vidbyte.agents import InfiniteWorkspaceSettings as agents_workspace
    from vidbyte.agents.infinite import InfiniteMemoryAgent as package_agent
    from vidbyte.agents.infinite import InfiniteMemoryRuntime as package_runtime
    from vidbyte.lib.enums import InfiniteAgentRole, InfiniteEntryKind, InfiniteJournalEvent, InfiniteResultStatus, InfiniteVerdict
    from vidbyte.lib.enums import InfiniteMemoryPreset as enums_preset
    from vidbyte.lib.util import TokenEstimate
    from vidbyte.tools.toolsets import InfiniteMemoryAgentTools

    assert InfiniteMemoryAgent is agents_agent is package_agent
    assert InfiniteMemoryAgentSettings is agents_settings
    assert InfiniteWorkspaceSettings is agents_workspace
    assert InfiniteMemoryRuntime is package_runtime
    assert InfiniteMemoryPreset is enums_preset
    assert issubclass(InfiniteMemoryAgent, BaseAgent)
    assert callable(TokenEstimate.count) and callable(InfiniteMemoryAgentTools.get_tools)
    enums_package = importlib.import_module("vidbyte.lib.enums")
    enum_names = {cls.__name__ for cls in (InfiniteAgentRole, InfiniteEntryKind, InfiniteJournalEvent, InfiniteResultStatus, InfiniteVerdict, InfiniteMemoryPreset)}
    assert enum_names <= set(enums_package.__all__), "every public enum is in vidbyte.lib.enums.__all__"
    root_names = {"InfiniteMemoryAgent", "InfiniteMemoryAgentSettings", "InfiniteWorkspaceSettings", "InfiniteMemoryPreset"}
    assert root_names <= set(vidbyte.__all__)
    contract = json.loads((REPO_ROOT / "contracts" / "sdk-public-api.json").read_text(encoding="utf-8"))
    assert root_names <= set(contract["exports"]), "the regenerated public-API contract must list the new root exports"


def test_prompt_family_has_exactly_the_forty_documented_leaves() -> None:
    """AC-27, INV-36: Prompt.INFINITE_MEMORY_* is exactly the 40 leaves of section 9.2, each backed by non-blank catalog text."""
    from vidbyte.lib.enums.prompts import Prompt
    from vidbyte.prompts import Prompts

    members = {member.name: member.value for member in Prompt if member.name.startswith("INFINITE_MEMORY_")}
    assert members == {f"INFINITE_MEMORY_{leaf.upper()}": f"infinite_memory.{leaf}" for leaf in EXPECTED_LEAVES}
    catalog = Prompts()
    keys = set(catalog.keys())
    for leaf in EXPECTED_LEAVES:
        member = Prompt[f"INFINITE_MEMORY_{leaf.upper()}"]
        assert member in keys, f"{member} has no catalog asset"
        assert catalog.get(member).strip(), f"{member} is blank"
    assert set(catalog.family("infinite_memory")) == set(EXPECTED_LEAVES)


def test_enum_values_are_the_documented_lowercase_strings() -> None:
    """Section 8.5: each new enum is a str enum whose values are exactly the documented lowercase names."""
    from vidbyte.lib.enums import AgentRuntimeType, InfiniteAgentRole, InfiniteEntryKind, InfiniteJournalEvent, InfiniteMemoryPreset, InfiniteResultStatus, InfiniteVerdict

    expected: dict[type, set[str]] = {
        InfiniteMemoryPreset: {"sparse", "full"},
        InfiniteEntryKind: {"decision", "fact", "lesson", "open_question", "pointer"},
        InfiniteResultStatus: {"done", "partial", "failed"},
        InfiniteVerdict: {"passed", "fixed", "failed", "unchecked"},
        InfiniteJournalEvent: {"run_started", "pair_started", "pair_finished", "run_finished"},
        InfiniteAgentRole: {"root", "generator", "verifier"},
    }
    for enum_type, values in expected.items():
        assert {member.value for member in enum_type} == values, enum_type.__name__
        assert all(isinstance(member, str) and member.value == member.name.lower() for member in enum_type), enum_type.__name__
    assert AgentRuntimeType("infinite_memory") is AgentRuntimeType.INFINITE_MEMORY


# ---------------------------------------------------------------- runtime, sessions, defaults


def test_runtime_type_resolves_and_refuses_outside_its_agent(tmp_path: Path) -> None:
    """AC-3, INV-3, EC-33: the registry maps the type to InfiniteMemoryRuntime, and a plain BaseAgent or a fork cannot build it."""
    from vidbyte.agents import InfiniteMemoryRuntime
    from vidbyte.lib.enums import AgentRuntimeType
    from vidbyte.lib.registries.runtimes import RuntimeRegistry

    assert RuntimeRegistry.resolve(AgentRuntimeType.INFINITE_MEMORY) is InfiniteMemoryRuntime
    plain = BaseAgent(name="base", system_prompt="Work.", provider="openai", model_name="gpt-4.1", runtime="infinite_memory")
    with pytest.raises(ConfigurationError) as refused:
        plain._runtime()
    assert str(refused.value).startswith("The 'infinite_memory' runtime is only available through InfiniteMemoryAgent")
    agent = build_agent(tmp_path)
    with pytest.raises(ConfigurationError, match="InfiniteMemoryAgent"):
        agent.fork()._runtime()


def test_session_refuses_the_agent(tmp_path: Path) -> None:
    """AC-25, EC-34: Session refuses an InfiniteMemoryAgent with the SessionError it raises for opted-out agent types."""
    from vidbyte import Session, SessionError

    agent = build_agent(tmp_path)
    with pytest.raises(SessionError, match="does not support durable session persistence"):
        Session(agent)


def test_loop_and_limit_defaults_match_the_spec(tmp_path: Path) -> None:
    """AC-39, section 9.3: without `loop` every agent stops at 100 iterations and cuts tool results at 100,000 characters; caps default to D-7."""
    from vidbyte.lib.constants.infinite import INFINITE_DEFAULT_MAX_ITERATIONS, INFINITE_TOOL_RESULT_MAX_CHARS

    settings = build_settings(tmp_path)
    assert settings.loop.max_iterations == INFINITE_DEFAULT_MAX_ITERATIONS == 100
    assert settings.loop.tool_settings is not None
    assert settings.loop.tool_settings.result_max_chars == INFINITE_TOOL_RESULT_MAX_CHARS == 100_000
    assert (settings.max_depth, settings.max_parallel, settings.max_agents) == (10, 10, 200)
    workspace = settings.workspace
    assert (workspace.max_files, workspace.max_tokens, workspace.max_file_tokens) == (200, 250_000, 20_000)
    assert (workspace.max_entry_tokens, workspace.max_entries_per_agent) == (60, 5)
    assert workspace.root == workspace_root(tmp_path).resolve()


# ---------------------------------------------------------------- construction validation


def _seed(tmp_path: Path, folder: str, name: str = "brief.md") -> Path:
    path = tmp_path / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Competitors: Acme, Globex, Initech, Umbrella, Hooli.\n", encoding="utf-8")
    return path


INVALID_SETTINGS = (
    pytest.param("tools", lambda tmp: {"tools": (shadow_grep,)}, ("tools", "grep"), id="reserved-tool-name"),
    pytest.param("root_dir", lambda tmp: {"root_dir": tmp / "no-such-project"}, ("root_dir", "no-such-project"), id="missing-root-dir"),
    pytest.param("seed_files", lambda tmp: {"workspace": {"seed_files": (tmp / "inputs" / "missing-brief.md",)}}, ("seed_files", "missing-brief.md"), id="missing-seed"),
    pytest.param(
        "seed_files",
        lambda tmp: {"workspace": {"seed_files": (_seed(tmp, "north"), _seed(tmp, "south"))}},
        ("seed_files", "brief.md", "north", "south"),
        id="duplicate-seed-basename",
    ),
    pytest.param("max_depth", lambda tmp: {"max_depth": 0}, ("max_depth", 0), id="max-depth-0"),
    pytest.param("max_parallel", lambda tmp: {"max_parallel": 0}, ("max_parallel", 0), id="max-parallel-0"),
    pytest.param("max_agents", lambda tmp: {"max_agents": 1}, ("max_agents", 1), id="max-agents-1"),
    pytest.param("model_mode", lambda tmp: {"model_mode": "direct"}, ("model_mode", "direct"), id="model-mode-not-enum"),
    pytest.param(
        "max_file_tokens",
        lambda tmp: {"workspace": {"max_tokens": 1_000, "max_file_tokens": 1_001}},
        ("max_file_tokens", 1_001),
        id="file-cap-above-total",
    ),
)


@pytest.mark.parametrize(("field_name", "overrides", "named"), INVALID_SETTINGS)
def test_construction_rejects_each_invalid_setting(tmp_path: Path, field_name: str, overrides: Any, named: tuple[Any, ...]) -> None:
    """AC-2, EC-2: each invalid setting raises ConfigurationError naming the field and value, and no workspace folder is created."""
    fields = overrides(tmp_path)
    workspace = fields.pop("workspace", None)
    with pytest.raises(ConfigurationError) as refused:
        build_agent(tmp_path, workspace=workspace, **fields)
    text = error_text(refused.value)
    for token in named:
        pattern = int_token(token) if isinstance(token, int) else re.compile(re.escape(str(token)))
        assert pattern.search(text), f"the {field_name} error does not name {token!r}: {text}"
    assert not workspace_root(tmp_path).exists(), "a settings-level refusal must not create the workspace"


def test_construction_rejects_a_non_settings_object(tmp_path: Path) -> None:
    """AC-2, INV-2: anything but InfiniteMemoryAgentSettings is refused before BaseAgent runs."""
    from vidbyte.agents.infinite import InfiniteMemoryAgent

    with pytest.raises(ConfigurationError) as refused:
        InfiniteMemoryAgent({"name": ROOT, "root_dir": str(project_dir(tmp_path))})  # type: ignore[arg-type]
    text = error_text(refused.value)
    assert re.search("settings", text, re.IGNORECASE), text
    assert "dict" in text or "'name': 'analyst'" in text, f"the refusal does not name the value it got: {text}"
    assert not workspace_root(tmp_path).exists()


@pytest.mark.parametrize(
    ("cap", "workspace", "prepare"),
    (
        pytest.param("max_files", {"max_files": 4}, "notes", id="over-max-files"),
        pytest.param("max_file_tokens", {"max_file_tokens": 10, "max_tokens": 1_000}, "big-seed", id="seed-over-file-cap"),
    ),
)
def test_attaching_a_workspace_already_over_a_cap_is_refused(tmp_path: Path, cap: str, workspace: dict[str, Any], prepare: str) -> None:
    """INV-21, EC-3: construction refuses a workspace that is already above a cap after setup."""
    root = workspace_root(tmp_path)
    fields = dict(workspace)
    if prepare == "notes":
        for index in range(3):
            path = root / "notes" / f"old-{index}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Old pricing notes.\n", encoding="utf-8")
    else:
        big = tmp_path / "inputs" / "brief.md"
        big.parent.mkdir(parents=True, exist_ok=True)
        big.write_text("x" * 400, encoding="utf-8")
        fields["seed_files"] = (big,)
    with pytest.raises(ConfigurationError) as refused:
        build_agent(tmp_path, workspace=fields)
    assert cap in error_text(refused.value)


def test_a_read_only_seed_is_copied_again_each_time_an_agent_attaches(tmp_path: Path) -> None:
    """R-26, INV-21, section 9.2, AC-30: with a read-only seed file, a second and a third agent build over the same workspace, and seed/<name> matches the source each time, including after the source changes."""
    seed = tmp_path / "inputs" / "brief.md"
    seed.parent.mkdir(parents=True)
    seed.write_text("Competitors: Acme, Globex.\n", encoding="utf-8", newline="\n")
    copy = workspace_root(tmp_path) / "seed" / "brief.md"
    os.chmod(seed, stat.S_IREAD)
    try:
        build_agent(tmp_path, workspace={"seed_files": (seed,)})
        assert copy.read_bytes() == seed.read_bytes()
        # Construction may raise only ConfigurationError (section 9.2), and attaching again copies the seed again (INV-21).
        build_agent(tmp_path, workspace={"seed_files": (seed,)})
        assert copy.read_bytes() == seed.read_bytes()
        os.chmod(seed, stat.S_IREAD | stat.S_IWRITE)
        seed.write_text("Competitors: Acme, Globex, Initech.\n", encoding="utf-8", newline="\n")
        os.chmod(seed, stat.S_IREAD)
        build_agent(tmp_path, workspace={"seed_files": (seed,)})
        assert copy.read_bytes() == seed.read_bytes(), "the edited seed was not copied over the old one"
    finally:
        # Windows cannot delete a read-only file, so make every file writable again for tmp_path's cleanup.
        for path in tmp_path.rglob("*"):
            if path.is_file():
                os.chmod(path, path.stat().st_mode | stat.S_IWRITE)


# ---------------------------------------------------------------- what the root's model is offered


@pytest.mark.parametrize(("preset", "extra"), (("SPARSE", set()), ("FULL", {"edit_file"})))
def test_root_is_offered_exactly_the_preset_tools_plus_its_extra(tmp_path: Path, preset: str, extra: set[str]) -> None:
    """AC-4, INV-6, NFR-8: the root's first call offers exactly the preset tools, the developer's extra, and isDone; FULL adds edit_file."""
    from vidbyte.lib.enums import InfiniteMemoryPreset

    agent = build_agent(tmp_path, workspace={"preset": InfiniteMemoryPreset[preset]}, tools=(web_fetch,))
    tree = ScriptedTree({ROOT: [reply("Nothing to do.")]})
    with tree.install():
        agent.run("Say hello.")
    offered = tree.first_call(ROOT).tools
    assert len(offered) == len(set(offered)), f"a tool is offered twice: {offered}"
    assert set(offered) == PRESET_TOOLS | {"web_fetch"} | extra
    tree.assert_complete()


def test_launch_and_remember_schemas_follow_the_documented_shape(tmp_path: Path) -> None:
    """Section 9.2, INV-9, INV-11: launch_subagent takes 1..max_parallel closed task cards with both prompts; remember's kind is the enum."""
    from vidbyte.lib.enums import InfiniteEntryKind
    from vidbyte.lib.enums.prompts import Prompt
    from vidbyte.prompts import Prompts

    agent = build_agent(tmp_path, max_parallel=3)
    tree = ScriptedTree({ROOT: [reply("Nothing to do.")]})
    with tree.install():
        agent.run("Say hello.")
    schemas = tree.first_call(ROOT).tool_schemas
    tasks = schemas["launch_subagent"]["properties"]["tasks"]
    assert tasks["type"] == "array" and tasks["minItems"] == 1 and tasks["maxItems"] == 3
    card = tasks["items"]
    fields = ("name", "goal", "done_criteria", "generator_prompt", "verifier_prompt", "context", "tools")
    assert card["additionalProperties"] is False
    assert set(card["properties"]) == set(fields)
    assert {"name", "goal", "done_criteria", "generator_prompt", "verifier_prompt"} <= set(card["required"])
    assert card["properties"]["done_criteria"].get("minItems") == 1
    catalog = Prompts()
    for name in fields:
        described = card["properties"][name].get("description", "").strip()
        leaf = catalog.get(Prompt[f"INFINITE_MEMORY_LAUNCH_{name.upper()}_DESCRIPTION"])
        assert template_regex(leaf).fullmatch(described), f"{name}'s description is not its catalog leaf: {described!r}"
    remember = schemas["remember"]["properties"]
    assert set(remember["kind"]["enum"]) == {kind.value for kind in InfiniteEntryKind}
    assert remember["supersedes"]["type"] == "integer"
    assert {"kind", "text"} <= set(schemas["remember"]["required"])
    assert {"path", "text"} <= set(schemas["write_note"]["required"])


# ---------------------------------------------------------------- TokenEstimate (FR-15, D-17)


def test_token_estimate_counts_characters_and_cuts_to_a_prefix() -> None:
    """FR-15, D-17: count is 0 for "" and max(1, ceil(chars / 4)) otherwise; cut keeps a prefix within the budget."""
    from vidbyte.lib.util import TokenEstimate

    assert [TokenEstimate.count(text) for text in ("", "a", "abcd", "abcde", "€€€€€")] == [0, 1, 1, 2, 2]
    assert TokenEstimate.cut("abcdefgh", 1) == "abcd"
    assert TokenEstimate.cut("abc", 1) == "abc"
    sample = random.Random(20261015)
    alphabet = string.ascii_letters + " \n€é"
    for _ in range(300):
        text = "".join(sample.choice(alphabet) for _ in range(sample.randint(0, 60)))
        budget = sample.randint(1, 12)
        cut = TokenEstimate.cut(text, budget)
        assert TokenEstimate.count(text) == (0 if not text else max(1, math.ceil(len(text) / 4)))
        assert text.startswith(cut)
        assert TokenEstimate.count(cut) <= budget
        assert TokenEstimate.cut(cut, budget) == cut
        assert cut == text if TokenEstimate.count(text) <= budget else len(cut) == budget * 4


# ---------------------------------------------------------------- prompt text and budget


def test_prompt_family_text_carries_no_coding_only_rules() -> None:
    """INV-33, NFR-5: no infinite_memory prompt mentions worktrees, pull requests, git, repositories, or single-writer rules."""
    from vidbyte.prompts import Prompts

    family = Prompts().family("infinite_memory")
    assert family, "the infinite_memory family is missing"
    for leaf, text in family.items():
        for word in CODING_ONLY_WORDS:
            assert not re.search(word, text, re.IGNORECASE), f"{leaf} mentions {word!r}"


def _lines_after_header(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    first = tree.body[0] if tree.body else None
    header_end = first.end_lineno if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else 0
    return len(source.splitlines()) - int(header_end or 0)


def test_new_modules_stay_inside_the_complexity_budget() -> None:
    """NFR-1, section 8.4: the agent package has at most its 8 modules, and each of the 12 new modules is at most 400 lines after its header."""
    package = REPO_ROOT / "vidbyte" / "agents" / "infinite"
    assert package.is_dir(), "vidbyte/agents/infinite does not exist"
    assert len(list(package.glob("*.py"))) <= 8
    for relative in BUDGET_MODULES:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is missing"
        assert _lines_after_header(path) <= 400, f"{relative} is over 400 lines after its header"


def test_entries_written_by_hand_in_the_documented_shape_are_accepted(tmp_path: Path) -> None:
    """Section 9.1: a workspace whose bookkeeping files were written in the documented shape attaches, and its live entries resolve."""
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace

    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(214, "Use SQLite; Postgres dropped (no server available)", kind="decision", tags=("db",), refs=("notes/db.md",), supersedes=88, by="root/db/gen", verified_by="root/db/ver")])
    write_jsonl(root / "superseded.jsonl", [entry_record(88, "Use Postgres", kind="decision", by="root/db/gen", verified_by="root/db/ver")])
    agent = build_agent(tmp_path)
    assert isinstance(agent.workspace, InfiniteWorkspace)
    (entry,) = agent.workspace.entries((214,))
    assert (entry.id, entry.draft.text, entry.draft.supersedes, entry.by, entry.verified_by) == (214, "Use SQLite; Postgres dropped (no server available)", 88, "root/db/gen", "root/db/ver")
    assert entry.draft.tags == ("db",) and entry.draft.refs == ("notes/db.md",)
