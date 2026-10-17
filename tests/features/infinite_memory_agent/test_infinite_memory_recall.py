"""FILE: tests/features/infinite_memory_agent/test_infinite_memory_recall.py

PURPOSE: Proves item 10 of spec infinite-memory-context-economy: InfiniteRecallMode and its exports, the registry's recall grants and withheld grep, the tool sets each agent is offered in DIRECT and DELEGATED, the recall tool's internal spec, the request and citation records, the retriever (name, system, tools, middleware, iteration cap), a card whose found section holds only text code copied from disk, every rejected citation, the per-agent quota, the card cap, the terms pre-search, and a recall that never counts toward max_agents or the journal while its usage reaches the run.
ROLE IN CODEBASE: Recall layer of tests/features/infinite_memory_agent/. Runs whole trees through ScriptedTree, scripting the retriever by its spec name, "analyst/root/recall", over a real workspace in tmp_path.
ARCHITECTURE NOTE: Only the model is scripted. The card is read back through the recall_card leaf itself: _card_sections turns the leaf into a pattern with one named group per field, so each section is compared on its own, and the found section is compared with the bytes on disk. A retriever reply that must name the run journal is built when the retriever is called, through a callable step.
FUNCTION INVENTORY: _recall builds a recall call; _card_sections / _card_prefix read a card; _seed writes the shared workspace. Tests: FR-10.1 (mode, exports, settings); AC-10.6, FR-10.2 (registry); AC-10.1, INV-10.1 and AC-10.2, INV-10.2 (offered tools); INV-10.9, EC-10.4 (spec); section 9.1 records and D-16 parse; AC-10.3, INV-10.3, INV-10.4, FR-10.5, NFR-10.3; AC-10.4, INV-10.5, EC-10.2, EC-10.7; AC-10.5, INV-10.6, EC-10.3; NFR-10.2, INV-10.7 loop cap, EC-10.1; AC-10.7, NFR-10.1, EC-10.6; AC-10.8, INV-10.10; INV-10.8, FR-10.6; EC-10.5, FR-10.9.
COMMON MODIFICATION PATTERNS: Add a citation case as one reply line plus its expected rejected or found section; add a tool-set case through the _offered sets.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level. 2. Do not pin a rejection reason's wording; the spec fixes only the citation, the line form, and the found text. 3. Do not patch the recall quota or cap constants; drive them with real calls.
KNOWN EDGE CASES: "reply line {n}" is accepted with n counted from 1 or from 0, which the spec does not fix. The retriever's error is accepted under the class the tool caught (AgentExecutionError, BaseAgent's wrapper) or the class the model raised.
RELATED DOCS: tests/features/infinite_memory_agent/FEATURE.md; docs/spec/infinite-memory-context-economy/spec.md sections 6.1 (INV-10.x), 6.2 (AC-10.x), 7 (EC-10.x), 8.5, 9.1, 9.2 (recall), 12.3 rows 17, 26-33, 36-43, 57 (recall.py, D-18).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_recall.py -q
"""

from __future__ import annotations

import asyncio
import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.features.infinite_memory_agent.infinite_memory_fixtures import (
    MAP_HEADER,
    ROOT,
    RUN_A,
    SYSTEM_PROMPT,
    TASK,
    ScriptedTree,
    build_agent,
    build_settings,
    entry_record,
    events,
    fail,
    generator,
    int_token,
    is_error,
    journal_paths,
    journal_records,
    launch,
    project_dir,
    prompt_text,
    reply,
    simple_pair,
    task,
    template_regex,
    tool_call,
    tool_result,
    tool_results,
    verifier,
    workspace_root,
    write_jsonl,
)
from tests.features.infinite_memory_agent.test_infinite_memory_economy import _view
from vidbyte import tool
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tools.formatter import ToolsFormatter
from vidbyte.tools.types import ToolCall, ToolPermission

REPO_ROOT = Path(__file__).resolve().parents[3]
RETRIEVER = f"{ROOT}/root/recall"
DELEGATED = {"recall_mode": "delegated"}
QUESTION = "What does Acme charge for its Pro plan?"
PURPOSE = "Put the Pro price in the comparison table."
ENTRY_TEXT = "Acme lists Pro at 49 USD per month"
OLD_ENTRY_TEXT = "Acme lists Pro at 39 USD per month"
P_LINES = [f"Plan row {number}: tier {number} costs {number * 10} USD" for number in range(1, 11)]
LONG_LINES = [f"line {number}" for number in range(1, 1001)]
CARD_FIELDS = ["question", "not_found", "rejected", "searches", "found"]

# Main's registry table: the memory tools for each preset, then the verifier's drop_entry.
MAIN_PRESET_TOOLS = {"SPARSE": ("remember", "write_note"), "FULL": ("remember", "write_note", "edit_file")}
MAIN_ROLE_TOOLS = {"ROOT": (), "GENERATOR": (), "VERIFIER": ("drop_entry",)}

# The tools each agent is offered by default once search_memory joins every agent (FR-8.1).
MEMORY_TOOLS = {"bash", "grep", "read_lines", "search_memory", "remember", "write_note"}
ROOT_TOOLS = MEMORY_TOOLS | {"launch_subagent", "isDone"}
GENERATOR_TOOLS = MEMORY_TOOLS | {"launch_subagent", "isDone"}
VERIFIER_TOOLS = MEMORY_TOOLS | {"drop_entry", "isDone"}


def _recall(**arguments: Any) -> Any:
    return tool_call("recall", {"question": QUESTION, "purpose": PURPOSE, **arguments})


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _seed(tmp_path: Path) -> Path:
    # Live entry #7, superseded entry #3, a ten-line note, and a 1,000-line note.
    root = workspace_root(tmp_path)
    write_jsonl(root / "entries.jsonl", [entry_record(7, ENTRY_TEXT)])
    write_jsonl(root / "superseded.jsonl", [entry_record(3, OLD_ENTRY_TEXT)])
    _write(root, "notes/p.md", "\n".join(P_LINES) + "\n")
    _write(root, "notes/long.md", "\n".join(LONG_LINES) + "\n")
    return root


def _leaf_pattern(leaf: str) -> str:
    # The leaf as a regex: literal text exact, each {field} one lazy named group.
    parts: list[str] = []
    position = 0
    for match in re.finditer(r"\{(\w+)\}", leaf):
        parts.append(re.escape(leaf[position : match.start()]))
        parts.append(f"(?P<{match.group(1)}>[\\s\\S]*?)")
        position = match.end()
    parts.append(re.escape(leaf[position:]))
    return "".join(parts)


def _card_sections(card: str) -> dict[str, str]:
    """Each field of an uncut recall card, by name."""
    found = re.fullmatch(_leaf_pattern(prompt_text("recall_card").strip()), card.strip())
    assert found, f"the result is not one recall_card rendering: {card!r}"
    return found.groupdict()


def _card_prefix(card: str) -> tuple[dict[str, str], str]:
    """The fields before {found} of a card cut by the cap, and the rest of the card after them."""
    leaf = prompt_text("recall_card").strip()
    head = leaf[: leaf.index("{found}")]
    found = re.match(_leaf_pattern(head), card.lstrip())
    assert found, f"the card does not start with the recall_card fields before {{found}}: {card!r}"
    return found.groupdict(), card.lstrip()[found.end() :]


def _lines(section: str) -> list[str]:
    return [line for line in section.splitlines() if line.strip()]


# ---------------------------------------------------------------- the mode, the registry, the tool sets


def test_recall_mode_is_a_public_str_enum_and_a_workspace_setting_that_accepts_text(tmp_path: Path) -> None:
    """FR-10.1, row 17, rows 29-32: InfiniteRecallMode(DIRECT, DELEGATED) is exported everywhere; the setting defaults to DIRECT, converts text, and names itself when refused."""
    import vidbyte
    from vidbyte import InfiniteRecallMode
    from vidbyte.agents.infinite import InfiniteWorkspaceSettings
    from vidbyte.lib.enums import InfiniteRecallMode as enums_mode
    from vidbyte.lib.enums.infinite import InfiniteRecallMode as domain_mode

    assert InfiniteRecallMode is enums_mode is domain_mode
    assert issubclass(InfiniteRecallMode, str)
    assert {member.name: member.value for member in InfiniteRecallMode} == {"DIRECT": "direct", "DELEGATED": "delegated"}
    assert "InfiniteRecallMode" in vidbyte.__all__ and "InfiniteRecallMode" in importlib.import_module("vidbyte.lib.enums").__all__
    contract = json.loads((REPO_ROOT / "contracts" / "sdk-public-api.json").read_text(encoding="utf-8"))
    assert "InfiniteRecallMode" in contract["exports"]
    root = workspace_root(tmp_path)
    assert InfiniteWorkspaceSettings(root=root).recall_mode is InfiniteRecallMode.DIRECT
    assert InfiniteWorkspaceSettings(root=root, recall_mode="delegated").recall_mode is InfiniteRecallMode.DELEGATED
    assert InfiniteWorkspaceSettings(root=root, recall_mode=InfiniteRecallMode.DELEGATED).recall_mode is InfiniteRecallMode.DELEGATED
    with pytest.raises(ConfigurationError) as caught:
        InfiniteWorkspaceSettings(root=root, recall_mode="sometimes")
    assert "recall_mode" in str(caught.value) + str(getattr(caught.value, "details", ""))


def test_the_registry_names_main_tools_in_direct_and_adds_recall_and_withholds_grep_in_delegated() -> None:
    """AC-10.6, INV-10.1, FR-10.2, row 28: DIRECT (default or named) equals main for every pair; DELEGATED adds recall for the root and generators; only they lose grep."""
    from vidbyte.lib.enums import InfiniteAgentRole, InfiniteMemoryPreset, InfiniteRecallMode
    from vidbyte.lib.registries import InfiniteMemoryToolRegistry

    for preset in InfiniteMemoryPreset:
        for role in InfiniteAgentRole:
            main = (*MAIN_PRESET_TOOLS[preset.name], *MAIN_ROLE_TOOLS[role.name])
            assert InfiniteMemoryToolRegistry.tool_names(preset, role) == main, (preset, role)
            assert InfiniteMemoryToolRegistry.tool_names(preset, role, InfiniteRecallMode.DIRECT) == main, (preset, role)
            delegated = InfiniteMemoryToolRegistry.tool_names(preset, role, recall_mode=InfiniteRecallMode.DELEGATED)
            assert delegated == (main if role is InfiniteAgentRole.VERIFIER else (*main, "recall")), (preset, role, delegated)
    for role in InfiniteAgentRole:
        assert InfiniteMemoryToolRegistry.withheld_tool_names(InfiniteRecallMode.DIRECT, role) == ()
        expected = () if role is InfiniteAgentRole.VERIFIER else ("grep",)
        assert InfiniteMemoryToolRegistry.withheld_tool_names(InfiniteRecallMode.DELEGATED, role) == expected, role


@pytest.mark.parametrize(
    ("workspace", "root_tools", "generator_tools", "verifier_tools"),
    (
        pytest.param({}, ROOT_TOOLS, GENERATOR_TOOLS, VERIFIER_TOOLS, id="direct"),
        pytest.param(DELEGATED, ROOT_TOOLS - {"grep"} | {"recall"}, GENERATOR_TOOLS - {"grep"} | {"recall"}, VERIFIER_TOOLS, id="delegated"),
    ),
)
def test_each_agent_is_offered_its_modes_tools(tmp_path: Path, workspace: dict[str, str], root_tools: set[str], generator_tools: set[str], verifier_tools: set[str]) -> None:
    """AC-10.1, AC-10.2, INV-10.1, INV-10.2, FR-10.4: DIRECT offers grep, read_lines and search_memory to all and recall to none; DELEGATED swaps grep for recall in the root and the generator only."""
    agent = build_agent(tmp_path, workspace=workspace)
    tree = ScriptedTree({ROOT: [launch(task("alpha")), reply("done")], **simple_pair("alpha", "ALPHA")})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    for name, expected in ((ROOT, root_tools), (generator("alpha"), generator_tools), (verifier("alpha"), verifier_tools)):
        offered = tree.first_call(name).tools
        assert len(offered) == len(set(offered)), f"{name} is offered a tool twice: {offered}"
        assert set(offered) == expected, name


def test_the_recall_spec_is_internal_read_only_and_built_from_the_five_leaves(tmp_path: Path) -> None:
    """INV-10.9, EC-10.4, section 9.2, rows 27, 36-40: recall is READ and internal, takes question and purpose (required) and known and terms (optional), and every description is its leaf with no number."""
    from vidbyte.agents.infinite.memory import InfiniteAgentMemory
    # D-18 (spec r4): the class's own module is recall.py; memory.py only imports it for its builder table.
    from vidbyte.agents.infinite.recall import InfiniteRecallTool
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.constants.infinite import INFINITE_RECALL_TOOL_NAME
    from vidbyte.lib.enums import InfiniteAgentRole

    settings = build_settings(tmp_path, workspace=DELEGATED)
    memory = InfiniteAgentMemory(InfiniteWorkspace(settings.workspace), key="root", role=InfiniteAgentRole.ROOT, run_id=RUN_A, settings=settings)
    assert memory.recalled == 0
    spec = InfiniteRecallTool(memory).spec()
    assert spec.name == INFINITE_RECALL_TOOL_NAME == "recall"
    assert spec.permission is ToolPermission.READ
    assert dict(spec.metadata or {}).get("internal") is True
    # The schema the model receives, whether the spec declares typed parameters or an input schema.
    schema = ToolsFormatter.input_schema(spec)
    properties = dict(schema.get("properties") or {})
    assert {name: str(value.get("type")) for name, value in properties.items()} == {"question": "string", "purpose": "string", "known": "string", "terms": "array"}
    assert set(schema.get("required") or ()) == {"question", "purpose"}
    assert spec.description.strip() == prompt_text("recall_tool_description").strip()
    for name in ("question", "purpose", "known", "terms"):
        assert str(properties[name].get("description", "")).strip() == prompt_text(f"recall_{name}_description").strip(), name
    for text in (spec.description, *(str(value.get("description", "")) for value in properties.values())):
        assert 4 <= len(re.findall(r"[.!?](?:\s|$)", text.strip())) <= 5, text
        assert not re.search(r"\d", text), f"a recall description states a number: {text}"


# ---------------------------------------------------------------- the records


def test_a_recall_request_refuses_blank_text_and_too_many_or_blank_terms() -> None:
    """Section 9.1, INV-10.6, T-1: question and purpose non-blank, known text, terms a tuple of at most INFINITE_RECALL_MAX_TERMS non-blank words; each refusal names its field."""
    from vidbyte.lib.constants.infinite import INFINITE_RECALL_MAX_TERMS
    from vidbyte.lib.dataclasses.infinite import InfiniteRecallRequest

    request = InfiniteRecallRequest(question=QUESTION, purpose=PURPOSE)
    assert (request.known, request.terms) == ("", ())
    full = InfiniteRecallRequest(question=QUESTION, purpose=PURPOSE, known="Pro exists.", terms=tuple(f"word{n}" for n in range(INFINITE_RECALL_MAX_TERMS)))
    assert len(full.terms) == INFINITE_RECALL_MAX_TERMS
    cases = (
        ("question", {"question": "  "}),
        ("question", {"question": 7}),
        ("purpose", {"purpose": ""}),
        ("known", {"known": None}),
        ("terms", {"terms": tuple(f"word{n}" for n in range(INFINITE_RECALL_MAX_TERMS + 1))}),
        ("terms", {"terms": ("zeta", " ")}),
        ("terms", {"terms": ["zeta"]}),
        ("terms", {"terms": "zeta"}),
    )
    for field_name, override in cases:
        with pytest.raises(ConfigurationError) as caught:
            InfiniteRecallRequest(**{"question": QUESTION, "purpose": PURPOSE, **override})
        assert field_name in str(caught.value) + str(getattr(caught.value, "details", "")), override


def test_a_citation_parses_the_three_reply_forms_and_refuses_bad_numbers() -> None:
    """Section 9.1, section 9.2 reply grammar, D-16, EC-10.7: FOUND #id, FOUND path:start-end and NOT FOUND parse with decorations; other lines are None; refused numbers raise."""
    from vidbyte.lib.dataclasses.infinite import InfiniteRecallCitation

    entry = InfiniteRecallCitation(why="price", entry_id=7)
    lines = InfiniteRecallCitation(why="table", path="notes/p.md", start=3, end=5)
    missing = InfiniteRecallCitation(why="pricing for Initech")
    parsed = {
        "FOUND #7 (price)": entry,
        "- FOUND #7 (price)": entry,
        "**FOUND** #7 (price)": entry,
        "  `FOUND` #7 (price)  ": entry,
        "FOUND notes/p.md:3-5 (table)": lines,
        "- _FOUND_ notes/p.md:3-5 (table)": lines,
        "NOT FOUND (pricing for Initech)": missing,
        "**NOT FOUND** (pricing for Initech)": missing,
    }
    for line, expected in parsed.items():
        assert InfiniteRecallCitation.parse(line) == expected, line
    for line in ("found #7 (price)", "Not Found (x)", "The price is in notes/p.md:3-5.", "", "FOUNDATION #7 (x)", "We FOUND #7 (price) earlier"):
        assert InfiniteRecallCitation.parse(line) is None, line
    for line in ("FOUND notes/p.md:5-3 (x)", "FOUND notes/p.md:0-4 (x)", "FOUND #0 (x)"):
        with pytest.raises(ConfigurationError):
            InfiniteRecallCitation.parse(line)
    for fields in ({"why": "x", "entry_id": 7, "path": "notes/p.md", "start": 1, "end": 1}, {"why": "x", "path": "notes/p.md", "start": 1}, {"why": "x", "entry_id": True}, {"why": 3}, {"why": "x", "path": "notes/p.md", "start": 2, "end": 1}):
        with pytest.raises(ConfigurationError):
            InfiniteRecallCitation(**fields)


# ---------------------------------------------------------------- the retriever and its card


def test_a_recall_card_holds_only_text_copied_from_disk_under_its_code_built_labels(tmp_path: Path) -> None:
    """AC-10.3, INV-10.3, INV-10.4, FR-10.5, NFR-10.3: entry #7 and lines 3-5 come from disk; no why or prose of the retriever's appears; the retriever is analyst/root/recall with its own system, map, tools and middleware."""
    from vidbyte.lib.constants.infinite import INFINITE_RECALL_CARD_MAX_TOKENS, INFINITE_RECALL_MAX_ITERATIONS
    from vidbyte.lib.util import TokenEstimate

    _seed(tmp_path)
    agent = build_agent(tmp_path, workspace=DELEGATED)
    answer = "Here is what I found, RETRIEVER-PROSE.\nFOUND #7 (price-WHY-TEXT)\n- **FOUND** notes/p.md:3-5 (table-WHY-TEXT)"
    tree = ScriptedTree(
        {
            ROOT: [_recall(), reply("done")],
            RETRIEVER: [tool_call("search_memory", {"query": "acme pro"}), tool_call("read_lines", {"path": "notes/long.md"}), reply(answer)],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = tool_result(tree.calls_by(ROOT)[1], "recall")
    assert not is_error(card), card
    sections = _card_sections(card)
    assert (sections["question"], sections["not_found"], sections["rejected"]) == (QUESTION, "-", "-")
    searches = _lines(sections["searches"])
    assert len(searches) == 1 and "search_memory" in searches[0] and "acme pro" in searches[0], searches
    entry_block = f"#7 fact: {ENTRY_TEXT}"
    range_block = "notes/p.md:3-5\n" + "\n".join(P_LINES[2:5])
    found = sections["found"]
    assert entry_block in found and range_block in found, found
    assert not found.replace(entry_block, "").replace(range_block, "").strip(), f"the found section holds text not copied from disk: {found!r}"
    for written in ("WHY-TEXT", "RETRIEVER-PROSE", "Here is what I found"):
        assert written not in card
    # The retriever: its own system after the developer's prompt, the map, the loop cap, and exactly the read-only search tools.
    first = tree.first_call(RETRIEVER)
    assert f"{SYSTEM_PROMPT}\n\n{prompt_text('retriever_system_prompt').strip()}" in first.system
    assert MAP_HEADER in first.system and "notes/p.md" in first.system
    assert f"max_iterations: 0/{INFINITE_RECALL_MAX_ITERATIONS}" in first.system
    assert template_regex(prompt_text("retriever_task_prompt"), question=QUESTION, purpose=PURPOSE, hits="-").fullmatch(first.prompt.strip()), first.prompt
    offered = set(first.tools)
    assert {"grep", "read_lines", "search_memory"} <= offered and offered - {"grep", "read_lines", "search_memory"} <= {"isDone"}, offered
    windowed = tool_result(tree.calls_by(RETRIEVER)[2], "read_lines")
    assert windowed == "\n".join(LONG_LINES[:200]) + "\n[lines 1-200 of 1000 shown; read on with start=201]"
    middleware = tree.agents[RETRIEVER].middleware
    assert len(middleware) == 2
    greps = [message for number in range(5) for message in ({"role": "assistant", "content": None, "tool_calls": [{"id": f"g{number}", "type": "function", "function": {"name": "grep", "arguments": "{}"}}]}, {"role": "tool", "tool_call_id": f"g{number}", "name": "grep", "content": f"GREP-{number}"})]
    placeholder = prompt_text("masked_output")
    assert [message["content"] for message in _view(middleware[0], greps) if message["role"] == "tool"] == [placeholder, placeholder, "GREP-2", "GREP-3", "GREP-4"]
    long_history = [{"role": "user", "content": f"{number:04d}" + "x" * 1996} for number in range(182)]
    assert _view(middleware[1], long_history) == long_history[50:]
    assert TokenEstimate.count(card) <= INFINITE_RECALL_CARD_MAX_TOKENS


def _rejection_reply(root: Path) -> str:
    # Built when the retriever is called, so the run journal under .runs/ already exists.
    (journal,) = journal_paths(root)
    return "\n".join(
        (
            "FOUND #3 (superseded)",
            "FOUND superseded.jsonl:1-1 (old line)",
            "FOUND entries.jsonl:1-1 (raw json)",
            f"FOUND .runs/{journal.name}:1-1 (journal)",
            "FOUND notes/../entries.jsonl:1-1 (dotted)",
            "FOUND ../secret.md:1-1 (outside)",
            "FOUND notes/long.md:1-201 (too long)",
            "FOUND notes/p.md:9-12 (past the end)",
            "FOUND notes/missing.md:1-1 (no file)",
            "FOUND notes/p.md:5-3 (backwards)",
            "FOUND #0 (zero)",
            "FOUND notes/p.md:2-2 (valid-WHY)",
        )
    )


def test_every_invalid_citation_is_listed_as_rejected_and_only_the_valid_one_is_transcribed(tmp_path: Path) -> None:
    """AC-10.4, INV-10.5, EC-10.2, EC-10.7: superseded and bookkeeping targets, paths outside or missing, ranges too long or past the end, and refused numbers are each rejected; the recall still succeeds."""
    root = _seed(tmp_path)
    _write(root.parent, "secret.md", "SECRET-TEXT outside the workspace\n")
    agent = build_agent(tmp_path, workspace=DELEGATED)
    tree = ScriptedTree({ROOT: [_recall(), reply("done")], RETRIEVER: [lambda call: reply(_rejection_reply(root))]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = tool_result(tree.calls_by(ROOT)[1], "recall")
    assert not is_error(card), card
    sections = _card_sections(card)
    assert sections["found"].strip() == "notes/p.md:2-2\n" + P_LINES[1]
    rejected = _lines(sections["rejected"])
    (journal,) = journal_paths(root)
    citations = ["#3", "superseded.jsonl:1-1", "entries.jsonl:1-1", f".runs/{journal.name}:1-1", "notes/../entries.jsonl:1-1", "../secret.md:1-1", "notes/long.md:1-201", "notes/p.md:9-12", "notes/missing.md:1-1"]
    for citation in citations:
        assert sum(line.startswith(f"- {citation}: ") for line in rejected) == 1, (citation, rejected)
    numbered = [int(match.group(1)) for line in rejected if (match := re.match(r"- reply line (\d+): \S", line))]
    assert numbered in ([10, 11], [9, 10]), f"the two refused-number lines are reply lines 10 and 11 (or 9 and 10 from zero): {rejected}"
    assert len(rejected) == len(citations) + 2, rejected
    for leaked in ("SECRET-TEXT", "Acme lists Pro at 39 USD", '"kind"', "run_started", "valid-WHY"):
        assert leaked not in card, leaked


def test_a_recall_refused_for_validation_costs_nothing_and_the_quota_counts_failed_attempts(tmp_path: Path) -> None:
    """AC-10.5, INV-10.6, EC-10.3, EC-10.1: two invalid calls start no agent; a retriever error names its class and counts; nine more run; the next is refused naming the quota."""
    from vidbyte.lib.constants.infinite import INFINITE_RECALL_MAX_TERMS, INFINITE_RECALLS_PER_AGENT

    _seed(tmp_path)
    agent = build_agent(tmp_path, workspace=DELEGATED)
    good = INFINITE_RECALLS_PER_AGENT - 1
    tree = ScriptedTree(
        {
            ROOT: [
                _recall(question="   "),
                _recall(terms=[f"word{n}" for n in range(INFINITE_RECALL_MAX_TERMS + 1)]),
                _recall(),
                *(_recall() for _ in range(good)),
                _recall(),
                reply("done"),
            ],
            RETRIEVER: [fail(OSError("RETRIEVER-DISK-GONE")), reply("I looked around but it is not written down anywhere."), *(reply("NOT FOUND (the Pro price)") for _ in range(good - 1))],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    results = [content for name, content in tool_results(tree.calls_by(ROOT)[-1]) if name == "recall"]
    assert len(results) == 3 + good + 1
    rejected = template_regex(prompt_text("memory_rejected_prompt"))
    for invalid in results[:2]:
        assert is_error(invalid) and rejected.search(invalid), invalid
    assert is_error(results[2]) and re.search(r"\b(AgentExecutionError|OSError)\b", results[2]), results[2]
    assert "recall" in results[2].lower(), results[2]
    prose = _card_sections(results[3])
    assert (prose["not_found"], prose["found"]) == ("-", "-"), "a prose-only reply gives an empty card"
    for card in results[4 : 3 + good]:
        assert not is_error(card) and _card_sections(card)["not_found"] == "- the Pro price", card
    refused = results[-1]
    problem = "\n".join(refused.splitlines()[:-1])
    assert is_error(refused) and rejected.search(refused) and int_token(INFINITE_RECALLS_PER_AGENT).search(problem) and "recall" in problem.lower(), refused
    assert len(tree.calls_by(RETRIEVER)) == INFINITE_RECALLS_PER_AGENT, "a refused call started a retriever"


def test_the_retriever_stops_after_its_iteration_cap_and_its_searches_are_listed(tmp_path: Path) -> None:
    """NFR-10.2, INV-10.7, EC-10.3, EC-10.1: a retriever that only searches is stopped after INFINITE_RECALL_MAX_ITERATIONS calls; the card lists each grep and finds nothing."""
    from vidbyte.lib.constants.infinite import INFINITE_RECALL_MAX_ITERATIONS

    _seed(tmp_path)
    agent = build_agent(tmp_path, workspace=DELEGATED)
    patterns = [f"Initech{number}" for number in range(INFINITE_RECALL_MAX_ITERATIONS)]
    tree = ScriptedTree({ROOT: [_recall(), reply("done")], RETRIEVER: [tool_call("grep", {"pattern": pattern}) for pattern in patterns]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert len(tree.calls_by(RETRIEVER)) == INFINITE_RECALL_MAX_ITERATIONS
    card = tool_result(tree.calls_by(ROOT)[1], "recall")
    assert not is_error(card), card
    sections = _card_sections(card)
    assert sections["found"].strip() == "-"
    searches = _lines(sections["searches"])
    assert len(searches) == len(patterns)
    for line, pattern in zip(searches, patterns, strict=True):
        assert "grep" in line and pattern in line, (line, pattern)


def test_a_card_over_its_cap_cuts_the_found_text_to_a_prefix_of_the_disk_and_keeps_the_other_sections(tmp_path: Path) -> None:
    """AC-10.7, NFR-10.1, INV-10.7, NFR-10.3: a valid 200-line range larger than the cap plus one NOT FOUND line; the card fits the cap, ends with the marker, and shows the question, the not-found line and the search."""
    from vidbyte.lib.constants.infinite import INFINITE_RECALL_CARD_MAX_TOKENS, INFINITE_TRUNCATION_MARKER
    from vidbyte.lib.util import TokenEstimate

    root = _seed(tmp_path)
    big_lines = [f"big row {number:03d}: " + "lorem ipsum " * 6 for number in range(1, 201)]
    _write(root, "notes/big.md", "\n".join(big_lines) + "\n")
    block = "notes/big.md:1-200\n" + "\n".join(big_lines)
    assert TokenEstimate.count(block) > INFINITE_RECALL_CARD_MAX_TOKENS, "precondition: the range alone exceeds the cap"
    agent = build_agent(tmp_path, workspace=DELEGATED)
    tree = ScriptedTree({ROOT: [_recall(), reply("done")], RETRIEVER: [tool_call("grep", {"pattern": "Initech"}), reply("NOT FOUND (pricing for Initech)\nFOUND notes/big.md:1-200 (all rows)")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    card = tool_result(tree.calls_by(ROOT)[1], "recall")
    assert not is_error(card), card
    assert TokenEstimate.count(card) <= INFINITE_RECALL_CARD_MAX_TOKENS
    assert card.endswith(INFINITE_TRUNCATION_MARKER)
    sections, rest = _card_prefix(card)
    assert (sections["question"], sections["not_found"], sections["rejected"]) == (QUESTION, "- pricing for Initech", "-")
    (search,) = _lines(sections["searches"])
    assert "grep" in search and "Initech" in search
    cut = rest[: -len(INFINITE_TRUNCATION_MARKER)]
    assert len(cut) > len("notes/big.md:1-200\n") and block.startswith(cut), f"the found text is not a prefix of the disk text: {cut[-80:]!r}"


def test_terms_are_searched_one_by_one_in_order_before_the_retriever_starts(tmp_path: Path) -> None:
    """AC-10.8, INV-10.10: terms ("zeta", "acme price") each match a different note line; the retriever's first message holds both search_memory results, in order, and the card lists both searches."""
    from vidbyte.agents.infinite.workspace import InfiniteWorkspace
    from vidbyte.lib.constants.infinite import INFINITE_DEFAULT_MAX_READ_LINES
    from vidbyte.tools.toolsets import InfiniteMemoryAgentTools

    root = _seed(tmp_path)
    _write(root, "notes/zeta.md", "Zeta sells an Enterprise tier\n")
    _write(root, "notes/acme.md", "Acme price sheet for this quarter\n")
    agent = build_agent(tmp_path, workspace=DELEGATED)
    tree = ScriptedTree({ROOT: [_recall(terms=["zeta", "acme price"]), reply("done")], RETRIEVER: [reply("NOT FOUND (nothing else)")]})
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    # The oracle: the same searches through a fresh search_memory over the same disk.
    workspace = InfiniteWorkspace(build_settings(tmp_path).workspace)
    search = InfiniteMemoryAgentTools.get_tools(project_dir(tmp_path), workspace.root, workspace.settings.max_tokens, INFINITE_DEFAULT_MAX_READ_LINES, workspace.full_text)[3]
    outputs = [asyncio.run(search.execute(ToolCall("search_memory", {"query": term}))).output for term in ("zeta", "acme price")]
    assert outputs[0].startswith("notes/zeta.md:1: ") and outputs[1].startswith("notes/acme.md:1: "), outputs
    prompt = tree.first_call(RETRIEVER).prompt
    hits = [output.splitlines()[0] for output in outputs]
    assert hits[0] in prompt and hits[1] in prompt, prompt
    assert prompt.index("zeta") < prompt.index(hits[0]) < prompt.index("acme price") < prompt.index(hits[1]), "each result must follow its own term, in the order given"
    searches = _lines(_card_sections(tool_result(tree.calls_by(ROOT)[1], "recall"))["searches"])
    assert len(searches) == 2 and "zeta" in searches[0] and "acme price" in searches[1], searches


def test_a_recall_adds_its_usage_to_the_run_but_never_counts_toward_max_agents_or_the_journal(tmp_path: Path) -> None:
    """INV-10.8, FR-10.6: with max_agents at its minimum, a recall then one pair both run; the journal has only the pair's records; usage holds the retriever's call."""
    from vidbyte.lib.constants.infinite import INFINITE_MIN_AGENTS

    _seed(tmp_path)
    agent = build_agent(tmp_path, workspace=DELEGATED, max_agents=INFINITE_MIN_AGENTS)
    root_usage = {"input_tokens": 1_000, "output_tokens": 100}
    tree = ScriptedTree(
        {
            ROOT: [
                tool_call("recall", {"question": QUESTION, "purpose": PURPOSE}, usage=root_usage),
                tool_call("launch_subagent", {"tasks": [task("alpha")]}, usage=root_usage),
                reply("done", usage=root_usage),
            ],
            RETRIEVER: [reply("NOT FOUND (the Pro price)", usage={"input_tokens": 300, "output_tokens": 30})],
            generator("alpha"): [reply("ALPHA", usage={"input_tokens": 200, "output_tokens": 20})],
            verifier("alpha"): [reply("Checked.\nVERDICT: passed", usage={"input_tokens": 30, "output_tokens": 3})],
        }
    )
    with tree.install():
        agent.run(TASK)
    tree.assert_complete()
    assert not is_error(tool_result(tree.calls_by(ROOT)[2], "launch_subagent")), "the recall counted toward max_agents"
    assert events(journal_records(workspace_root(tmp_path))) == ["run_started", "pair_started", "pair_finished", "run_finished"]
    usage = agent.get_usage()
    assert usage.model_call_count == 6
    # Three root calls, then the retriever, the generator and the verifier: without the retriever's call it would be (3_230, 323).
    assert (usage.input_tokens, usage.output_tokens) == (3 * 1_000 + 300 + 200 + 30, 3 * 100 + 30 + 20 + 3)


def test_a_developer_tool_named_recall_is_refused(tmp_path: Path) -> None:
    """EC-10.5, FR-10.9: recall joins the run-bound names, so settings refuse a developer tool that takes it."""
    from vidbyte.lib.constants.infinite import INFINITE_RUN_BOUND_TOOL_NAMES

    @tool(name="recall")
    def recall(question: str) -> str:
        """Look something up."""
        return question

    assert "recall" in INFINITE_RUN_BOUND_TOOL_NAMES
    with pytest.raises(ConfigurationError) as caught:
        build_settings(tmp_path, tools=(recall,))
    assert "recall" in str(caught.value) + str(getattr(caught.value, "details", ""))


def test_the_recall_card_leaf_renders_its_fields_in_the_spec_order() -> None:
    """INV-10.7, row 43, the leaf contract table: recall_card holds {question}, {not_found}, {rejected}, {searches}, then {found} last."""
    assert re.findall(r"\{(\w+)\}", prompt_text("recall_card")) == CARD_FIELDS
    assert sorted(re.findall(r"\{(\w+)\}", prompt_text("retriever_task_prompt"))) == ["hits", "known", "purpose", "question"]
