"""FILE: tests/features/public_skill_loader/test_public_skill_loader_boundary.py

PURPOSE: Pin the public door's boundary: SkillLoader(entries) takes a tuple, a list, a generator, or a dict keyed by entries once and in iteration order, and rejects text, a single value, a non-entry element, or a repeated name with a ConfigurationError whose details have one fixed shape, before any file, key variable, or request is touched; names compare exactly, and an empty collection is valid.
ROLE IN CODEBASE: Covers spec AC-3, AC-4, AC-5, AC-14, AC-17, INV-2, INV-3, INV-4, INV-5, D-3, D-4, D-14 and EC-1 to EC-8, EC-28 for SkillLoader.__init__ in vidbyte/agents/skills/loader.py and SkillEntries.__post_init__ in vidbyte/lib/dataclasses/skills.py, through the root export.
ARCHITECTURE NOTE: Everything runs through the real constructor and the real record; nothing is patched except the conftest's transport fake, which turns any request into a failure. Each rejection runs inside the conftest's I/O recorder with entries that point at real paths under tmp_path, so a validator that stats a folder or reads a key shows up.
FUNCTION INVENTORY: test_text_or_a_single_value_is_rejected_whole_before_any_io; test_first_non_entry_element_is_rejected_at_its_zero_based_position; test_repeated_names_are_rejected_sorted_and_each_listed_once; test_names_differing_only_by_case_space_or_unicode_form_are_distinct; test_any_non_text_collection_is_taken_once_in_its_iteration_order; test_empty_tuple_and_empty_list_load_nothing.
COMMON MODIFICATION PATTERNS: A new rejected shape adds a row to NOT_COLLECTIONS, BAD_ELEMENTS, or REPEATED_NAMES with the exact details the spec gives it.
WHAT NOT TO DO IN THIS FILE: 1. Do not loosen the details checks to key membership; an extra key is where a rejected value would leak. 2. Do not read the loader's entries, memory, or resolvers attributes; they are not public (spec NG-15), so results are observed through load() and documents(). 3. Do not assert message wording beyond the class name and the InlineSkill hint the spec requires.
KNOWN EDGE CASES: The Jev door counts positions from 1 (enumerate start=1 in JevAlignmentSettings); the public door counts from 0. A generator is spent by the first pass over it, so a loader that builds its memory from the raw argument after converting it sees nothing. A dict iterates its keys.
RELATED DOCS: docs/spec/public-skill-loader/spec.md (sections 6.1 INV-2 to INV-5, 6.3 EC-1 to EC-8 and EC-28, 8.5, 12.3 rows 1 and 2)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader/test_public_skill_loader_boundary.py
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import (
        AnthropicSkill,
        ConfigurationError,
        GitHubSkill,
        InlineSkill,
        LocalSkill,
        OpenAISkill,
        SkillDocument,
        SkillLoader,
        SkillResolution,
        SkillsShSkill,
        SkillUnavailableReason,
    )
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

KEY_VARIABLES = {"GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"}


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def inline(name: str) -> Any:
    return InlineSkill(name=name, description=f"The {name} skill.", text=f"Text of {name}.\n")


def local(name: str, root: Path) -> Any:
    # A real-looking folder under tmp_path, so a validator that stats it is recorded.
    return LocalSkill(name=name, path=root / "skills" / name)


def reject(argument: object, record_io: Callable[[], Any], tmp_path: Path, fake_http: Any) -> Any:
    # Builds the loader inside the I/O recorder and returns the error, after checking nothing was touched.
    with record_io() as window, pytest.raises(ConfigurationError) as raised:
        SkillLoader(argument)
    assert window.touched(tmp_path) == []
    assert KEY_VARIABLES.isdisjoint(window.env_keys)
    assert fake_http.sent == []
    assert "SkillLoader" in raised.value.message
    return raised.value


# (case, argument builder, type name the details must carry)
NOT_COLLECTIONS: list[tuple[str, Callable[[Path], object], str]] = [
    ("str path meant as one source (EC-2)", lambda root: "skills/pdf", "str"),
    ("bytes", lambda root: b"skills/pdf", "bytes"),
    ("None", lambda root: None, "NoneType"),
    ("int", lambda root: 3, "int"),
    ("one entry instead of a collection", lambda root: local("pdf", root), "LocalSkill"),
]


@pytest.mark.parametrize(("case", "build", "type_name"), NOT_COLLECTIONS, ids=[row[0] for row in NOT_COLLECTIONS])
def test_text_or_a_single_value_is_rejected_whole_before_any_io(tmp_path: Path, fake_http: Any, record_io: Callable[[], Any], case: str, build: Callable[[Path], object], type_name: str) -> None:
    # AC-3, INV-2, INV-3, EC-2: text is never split into characters, and one value is never wrapped silently.
    error = reject(build(tmp_path), record_io, tmp_path, fake_http)
    assert error.details == {"entries_type": type_name}


# (case, collection builder, 0-based position of the first non-entry element, its type name)
BAD_ELEMENTS: list[tuple[str, Callable[[Path], object], int, str]] = [
    ("str meant as inline text (EC-7)", lambda root: (inline("house-review"), "Read the tests first.", local("pdf", root)), 1, "str"),
    ("None last in a list (EC-3)", lambda root: [inline("house-review"), local("pdf", root), None], 2, "NoneType"),
    ("dict first (EC-3)", lambda root: ({"name": "pdf", "type": "github"}, local("pdf", root)), 0, "dict"),
    ("a SkillResolution", lambda root: (local("pdf", root), SkillResolution(reason=SkillUnavailableReason.NOT_FOUND, detail="Missing."), inline("notes"), inline("sheets")), 1, "SkillResolution"),
    ("first of two bad elements", lambda root: (inline("house-review"), None, "text", local("pdf", root)), 1, "NoneType"),
    ("bad element after a repeated name (checked first)", lambda root: (local("pdf", root), local("pdf", root), None), 2, "NoneType"),
    ("dict keyed by a non-entry (EC-28)", lambda root: {local("pdf", root): "first", "oops": "second"}, 1, "str"),
]


@pytest.mark.parametrize(("case", "build", "position", "type_name"), BAD_ELEMENTS, ids=[row[0] for row in BAD_ELEMENTS])
def test_first_non_entry_element_is_rejected_at_its_zero_based_position(tmp_path: Path, fake_http: Any, record_io: Callable[[], Any], case: str, build: Callable[[Path], object], position: int, type_name: str) -> None:
    # AC-4, INV-2, INV-3, EC-3, EC-7: today these raise KeyError or TypeError from load(), after real groups resolved.
    error = reject(build(tmp_path), record_io, tmp_path, fake_http)
    assert error.details == {"position": position, "entry_type": type_name}
    # EC-7: the fix for a plain string is to wrap it in InlineSkill.
    assert "InlineSkill" in error.message


# (case, collection builder, sorted repeated names)
REPEATED_NAMES: list[tuple[str, Callable[[Path], object], list[str]]] = [
    ("same LocalSkill twice (EC-4)", lambda root: (local("pdf", root), local("pdf", root)), ["pdf"]),
    ("same SkillsShSkill twice in a list (EC-4)", lambda root: [SkillsShSkill(name="react", source="acme/skills"), inline("notes"), SkillsShSkill(name="react", source="acme/skills")], ["react"]),
    ("GitHub entry and a document of one name", lambda root: (GitHubSkill(name="notes", repo="acme/skills"), SkillDocument(name="notes", description="Caller notes.", text="Body.")), ["notes"]),
    ("local and GitHub entries of one name (EC-5)", lambda root: (local("pdf", root), GitHubSkill(name="pdf", repo="anthropics/skills")), ["pdf"]),
    (
        "three names repeated, one three times",
        lambda root: (inline("zeta"), AnthropicSkill(name="mid", skill_id="skill_1"), inline("alpha"), OpenAISkill(name="zeta", skill_id="skill_2"), inline("mid"), local("alpha", root), inline("mid"), inline("solo")),
        ["alpha", "mid", "zeta"],
    ),
]


@pytest.mark.parametrize(("case", "build", "names"), REPEATED_NAMES, ids=[row[0] for row in REPEATED_NAMES])
def test_repeated_names_are_rejected_sorted_and_each_listed_once(tmp_path: Path, fake_http: Any, record_io: Callable[[], Any], case: str, build: Callable[[Path], object], names: list[str]) -> None:
    # AC-5, INV-2, D-4, EC-4, EC-5: today two equal single-source entries share one resolver group and abort every entry.
    error = reject(build(tmp_path), record_io, tmp_path, fake_http)
    assert error.details == {"names": names}


@pytest.mark.asyncio
async def test_names_differing_only_by_case_space_or_unicode_form_are_distinct() -> None:
    # INV-2: names compare exactly, so a check that lowercases, strips, or normalizes Unicode wrongly rejects these.
    names = ["pdf", "PDF", "pdf ", "café", "café"]
    resolutions = await SkillLoader(tuple(inline(name) for name in names)).load()
    assert [resolution.document.name for resolution in resolutions] == names


def as_generator(items: list[Any]) -> Iterator[Any]:
    return (item for item in items)


# (case, wrapper that turns the item list into the argument)
CONTAINERS: list[tuple[str, Callable[[list[Any]], Any]]] = [
    ("list (EC-6)", list),
    ("generator (EC-1)", as_generator),
    ("dict keyed by entries (EC-28)", dict.fromkeys),
]


@pytest.mark.parametrize(("case", "wrap"), CONTAINERS, ids=[row[0] for row in CONTAINERS])
@pytest.mark.asyncio
async def test_any_non_text_collection_is_taken_once_in_its_iteration_order(tmp_path: Path, write_skill: Callable[..., Path], skill_md: Callable[..., bytes], case: str, wrap: Callable[[list[Any]], Any]) -> None:
    # AC-17, D-14, EC-1, EC-6, EC-28: names out of sorted order, and a caller document the loader must remember at once.
    folder = write_skill(tmp_path / "skills" / "local-one", skill_md("local-one", "Local text.\n"))
    document = SkillDocument(name="caller-notes", description="Resolved by the caller.", text="Caller text.\n")
    items = [inline("zeta"), document, LocalSkill(name="local-one", path=folder), inline("alpha")]
    argument = wrap(items)

    loader = SkillLoader(argument)

    # A caller's document is remembered at construction, from the loader's own copy of the argument.
    assert loader.documents() == (None, document, None, None)
    if isinstance(argument, list):
        # The loader keeps its own tuple; the caller's list may change afterwards.
        argument.clear()
    elif isinstance(argument, Iterator):
        # A generator is consumed once, at construction.
        assert next(argument, None) is None
    resolutions = await loader.load()
    assert [resolution.document.name for resolution in resolutions] == ["zeta", "caller-notes", "local-one", "alpha"]
    assert [resolution.document.text for resolution in resolutions] == ["Text of zeta.\n", "Caller text.\n", "Local text.\n", "Text of alpha.\n"]
    assert resolutions[1].document is document


@pytest.mark.parametrize("empty", [(), []], ids=["empty tuple", "empty list"])
@pytest.mark.asyncio
async def test_empty_tuple_and_empty_list_load_nothing(tmp_path: Path, fake_http: Any, record_io: Callable[[], Any], empty: tuple[()] | list[Any]) -> None:
    # AC-14, EC-8: an empty collection is valid, not an "at least one entry" error, and loads to an empty tuple.
    with record_io() as window:
        loader = SkillLoader(empty)
        resolutions = await loader.load()
    assert resolutions == () and isinstance(resolutions, tuple)
    assert loader.documents() == ()
    assert window.touched(tmp_path) == [] and fake_http.sent == []
