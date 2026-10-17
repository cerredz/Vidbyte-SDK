"""FILE: tests/features/harness_compose/test_harness_compose_prompts.py

PURPOSE: The 22 Markdown prompt files (AC-21 static part, INV-20, NFR-11, §9.2 port rules, D-10, D-12): the folder holds exactly those files and nothing the wheel would refuse; each file's placeholders are bare names equal to its §9.2 field set and to COMPOSE_PROMPT_FIELDS; each loads as a package resource in UTF-8; no CLI placeholder survives unconverted; the ten ported files drop their own output contracts, examples and sandbox wording; every fixed combination compose sends leaves half the 24,000-character argv room; pyproject ships the files.
ROLE IN CODEBASE: Start here when a prompt file gains or loses a placeholder, grows past its room, or still carries CLI wording.
ARCHITECTURE NOTE: The files are read straight from the source folder with string.Formatter, independent of compose's loader; only the package-resource test goes through importlib.resources. The installed-wheel half of AC-21 is left to the package stage (lint C015 proves statically that the files ship); see the test plan.
FUNCTION INVENTORY: filled renders one file with numbers at their largest and spliced values empty; combinations builds every fixed combination NFR-11 names; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new prompt file is a §9.2 change first: add its stem and field set to PROMPT_FIELDS, and its combination to combinations when compose sends it.
WHAT NOT TO DO IN THIS FILE: Do not compare prompt prose beyond the spec's forbidden texts; the wording belongs to the implementer.
KNOWN EDGE CASES: The forbidden texts are matched case-insensitively, which is stricter than the AC's literal texts. A doubled brace renders as one brace, so a leftover `{{roles}}` shows up only after rendering, which is how the placeholder test finds it.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-20, §6.2 AC-21, §7 NFR-11, §8.1 D-9 to D-13, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_prompts.py
"""

from __future__ import annotations

import importlib.resources
import sys
import tomllib

import pytest

PROMPT_FIELDS = {
    "planner_system": {"roles"},
    "planner_turn": {"task", "roles"},
    "plan_schema": {"roles"},
    "role_system": {"role_name", "identity", "personality", "expertise", "knowledge", "skills", "goal", "minimum", "maximum"},
    "role_turn": {"task", "task_analysis", "roster_strategy", "coverage_summary", "minimum", "maximum"},
    "fork_turn": {"instructions", "turn"},
    "selector_system": set(),
    "selector_round_turn": {"task", "round", "surviving", "target", "candidates"},
    "selector_final_turn": {"task", "round", "surviving", "candidates"},
    "round_schema": {"target"},
    "selection_schema": set(),
    "proposal_block": {"number", "role_name", "text"},
    "implementer_system": set(),
    "implementer_turn": {"task", "role_name", "proposal", "approach", "rationale", "guidance"},
    "chain_turn": {"prompt", "previous", "diff"},
    "verify_turn": {"prompt", "files", "diff"},
    "verdict_schema": set(),
    "handoff_summary": set(),
    "handoff_seed": {"summary"},
    "json_answer": {"prompt", "schema"},
    "json_repair": {"problem", "schema"},
    "truncation_note": {"omitted"},
}
PORTED = ("planner_system", "planner_turn", "role_system", "role_turn", "fork_turn", "selector_system", "selector_round_turn", "selector_final_turn", "implementer_system", "implementer_turn")
FORBIDDEN_IN_PORTED = ("Return one JSON object", "candidate_id", "eliminated", "round_summary", "sandbox", "workspace-write", "cannot write", "will fail", "<examples>")
ROOM_CHARS = 12_000
ARGV_PROMPT_MAX_CHARS = 24_000
ALL_FIELD_NAMES = sorted(set().union(*PROMPT_FIELDS.values()))
NUMBERS = {"roles": 10, "minimum": 2, "maximum": 5, "round": 10, "surviving": 10, "target": 2, "number": 10, "omitted": sys.maxsize}


def filled(pack, stem: str, **values: object) -> str:
    # One file with every counted number at its largest and every other
    # field empty, unless given.
    data: dict[str, object] = {name: NUMBERS.get(name, "") for name in PROMPT_FIELDS[stem]}
    data.update(values)
    return pack.render(stem, **data)


def combinations(pack) -> dict[str, str]:
    # Every fixed combination compose sends (NFR-11): a system file in
    # front of its turn, json_answer around a schema when the answer is
    # JSON, fork_turn around both for an unanchored Grok fork.
    separator = pack.PROMPT_SEPARATOR

    def wrapped(prompt: str, schema: str) -> str:
        return filled(pack, "json_answer", prompt=prompt, schema=filled(pack, schema))

    def forked(system: str, turn: str) -> str:
        return filled(pack, "fork_turn", instructions=filled(pack, system), turn=filled(pack, turn))

    return {
        "planner": wrapped(filled(pack, "planner_system") + separator + filled(pack, "planner_turn"), "plan_schema"),
        "proposer": filled(pack, "role_system") + separator + filled(pack, "role_turn"),
        "fork proposer": forked("role_system", "role_turn"),
        "selector round": wrapped(filled(pack, "selector_system") + separator + filled(pack, "selector_round_turn"), "round_schema"),
        "selector final": wrapped(filled(pack, "selector_system") + separator + filled(pack, "selector_final_turn"), "selection_schema"),
        "fork selector round": wrapped(forked("selector_system", "selector_round_turn"), "round_schema"),
        "fork selector final": wrapped(forked("selector_system", "selector_final_turn"), "selection_schema"),
        "implementer": filled(pack, "implementer_system") + separator + filled(pack, "implementer_turn"),
        "fork implementer": forked("implementer_system", "implementer_turn"),
        "verifier": wrapped(filled(pack, "verify_turn"), "verdict_schema"),
        "chain": filled(pack, "chain_turn"),
        "handoff summary": filled(pack, "handoff_summary"),
        "handoff seed": filled(pack, "handoff_seed"),
        "repair verdict": filled(pack, "json_repair", schema=filled(pack, "verdict_schema")),
        "repair plan": filled(pack, "json_repair", schema=filled(pack, "plan_schema")),
        "repair round": filled(pack, "json_repair", schema=filled(pack, "round_schema")),
        "repair selection": filled(pack, "json_repair", schema=filled(pack, "selection_schema")),
    }


def test_prompt_folder_holds_exactly_the_22_markdown_files(compose_api, pack) -> None:
    # INV-20 / §12.2: 22 files and nothing else (no __init__.py, no
    # README the wheel would refuse under lint C015).
    assert len(PROMPT_FIELDS) == 22
    assert pack.PROMPTS.is_dir()
    assert sorted(path.name for path in pack.PROMPTS.iterdir()) == sorted(f"{stem}.md" for stem in PROMPT_FIELDS)
    assert sorted(member.value for member in compose_api.enums.ComposePrompt) == sorted(PROMPT_FIELDS)


@pytest.mark.parametrize("stem", sorted(PROMPT_FIELDS))
def test_each_prompt_holds_exactly_its_bare_placeholders(compose_api, pack, stem) -> None:
    # INV-20 / AC-21 / D-10: placeholders are bare {name}s equal to the
    # §9.2 set and to COMPOSE_PROMPT_FIELDS; rendering leaves no
    # unconverted CLI placeholder behind.
    fields = pack.prompt_fields(stem)
    for name, spec, conversion in fields:
        assert name.isidentifier(), f"{stem}: {{{name}}} is not a bare name"
        assert spec == "" and conversion is None, f"{stem}: {{{name}}} carries a format spec or conversion"
    assert {name for name, _spec, _conversion in fields} == PROMPT_FIELDS[stem]
    declared = compose_api.constants.COMPOSE_PROMPT_FIELDS[compose_api.enums.ComposePrompt(stem)]
    assert {field.value for field in declared} == PROMPT_FIELDS[stem]
    rendered = pack.render(stem, **{name: "" for name in PROMPT_FIELDS[stem]})
    assert rendered.strip(), f"{stem} is blank"
    leftovers = [name for name in ALL_FIELD_NAMES if "{" + name + "}" in rendered]
    assert leftovers == [], f"{stem} still holds unconverted placeholders {leftovers}"


def test_compose_prompt_fields_covers_every_prompt(compose_api) -> None:
    # §8.5: one COMPOSE_PROMPT_FIELDS entry per ComposePrompt member.
    assert set(compose_api.constants.COMPOSE_PROMPT_FIELDS) == set(compose_api.enums.ComposePrompt)


@pytest.mark.parametrize("stem", sorted(PROMPT_FIELDS))
def test_each_prompt_loads_as_a_package_resource(compose_api, pack, stem) -> None:
    # AC-21 / D-9: loaded with importlib.resources in UTF-8, the same
    # text as the source file.
    resource = importlib.resources.files("vidbyte.harnesses.native.compose").joinpath("prompts", f"{stem}.md")
    assert resource.read_text(encoding="utf-8") == pack.prompt_text(stem)


@pytest.mark.parametrize("stem", PORTED)
def test_ported_prompt_drops_its_own_output_contract_and_sandbox_wording(compose_api, pack, stem) -> None:
    # AC-21 / §9.2 port rules / D-12, D-13: no ported file keeps the
    # CLI's JSON contract, its ids, its examples or sandbox claims.
    text = pack.prompt_text(stem).lower()
    found = [phrase for phrase in FORBIDDEN_IN_PORTED if phrase.lower() in text]
    assert found == [], f"{stem} still contains {found}"


def test_every_fixed_combination_leaves_half_the_argv_room(compose_api, pack) -> None:
    # NFR-11 / AC-21: with the caller's prompt and every spliced value
    # empty, each combination is at most 12,000 characters.
    sizes = {name: len(text) for name, text in combinations(pack).items()}
    too_long = {name: size for name, size in sizes.items() if size > ROOM_CHARS}
    assert too_long == {}, f"over {ROOM_CHARS} characters: {too_long}"
    assert ROOM_CHARS * 2 == ARGV_PROMPT_MAX_CHARS == compose_api.threads_constants.NATIVE_ARGV_PROMPT_MAX_CHARS


def test_pyproject_ships_the_prompt_files(compose_api, pack) -> None:
    # §12.3 row 18 / AC-21: the package-data entry, exactly as specified.
    data = tomllib.loads((pack.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["tool"]["setuptools"]["package-data"]["vidbyte.harnesses.native.compose"] == ["prompts/*.md"]
