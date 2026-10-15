"""FILE: tests/features/jev_skills_preload/test_skill_sources_skills_sh.py

PURPOSE: Pin SkillsShSkill loading of the copy `npx skills add` installed: the hash-bearing label from skills-lock.json, not_installed with the exact install command and the absolute path (remembered), the inclusive SKILL.md cap, fetch_failed for a read error (read again next load), invalid_skill for a lock that names another source, a lock that is broken or unreadable in any way treated as absent, no lock lookup outside <root>/.agents/skills, and hostile files that must not crash a run.
ROLE IN CODEBASE: Covers spec AC-5, AC-6, AC-23, FR-8, INV-12, D-6, D-16, D-17, D-21, D-29, the section 9.2 local and skills.sh mapping, and EC-39 to EC-46, EC-111 for vidbyte/agents/skills/skills_sh.py through vidbyte/agents/skills/loader.py, plus one JevAgent run for AC-23.
ARCHITECTURE NOTE: Installs and lock files are real files under tmp_path, which the autouse fixture makes the working folder, so the default directory ".agents/skills" lands there. Besides the conftest's network fake, which proves no request is made, only LocalSkillResolver.read_capped is replaced, and only to raise an OSError that Windows cannot produce on demand.
FUNCTION INVENTORY: test_installed_skill_loads_with_the_lock_hash_in_its_label; test_missing_install_is_not_installed_with_the_install_command_and_path; test_installed_skill_md_cap_is_inclusive_and_over_it_is_too_large; test_read_error_on_the_installed_file_is_fetch_failed_and_read_again; test_lock_that_raises_on_read_is_treated_as_absent; test_lock_naming_another_source_is_invalid_naming_both; test_broken_or_silent_lock_is_treated_as_absent; test_lock_is_not_consulted_outside_the_default_layout; test_hostile_files_end_as_data_and_the_run_returns.
COMMON MODIFICATION PATTERNS: A new lock problem adds a row to the broken-lock table; each row keeps a lock that would fail the source check if it were read, so "treated as absent" is observable.
WHAT NOT TO DO IN THIS FILE: 1. Do not run npx or any subprocess. 2. Do not assert the label hash beyond its first 12 characters.
KNOWN EDGE CASES: json.loads raises RecursionError, not JSONDecodeError, for about 2,000 nested brackets; that lock must still count as absent. An interrupted install leaves the folder without SKILL.md and is still not_installed.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 6.3 SkillsShSkill, 8.1 D-17, 9.2 local and skills.sh mapping)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_skills_sh.py
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.agents.skills.loader import SkillLoader
    from vidbyte.agents.skills.local import LocalSkillResolver
    from vidbyte.lib.constants.skills import SKILL_MARKDOWN_MAX_BYTES

    from vidbyte import JevSkillStatus, SkillsShSkill, SkillUnavailableReason
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

SOURCE = "vercel-labs/agent-skills"
NAME = "react-best-practices"
HASH = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
FORK = "someone-else/agent-skills"


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _names_path(detail: str, path: Path) -> bool:
    return str(path) in detail or path.as_posix() in detail


def _lock(skills: object, version: object = 1) -> str:
    return json.dumps({"version": version, "skills": skills})


def _install(root: Path, write_skill: Callable[..., Path], name: str = NAME, **markdown: Any) -> Path:
    return write_skill(root / ".agents" / "skills" / name, **({"body": "Prefer server components.\n"} | markdown))


@pytest.mark.asyncio
async def test_installed_skill_loads_with_the_lock_hash_in_its_label(tmp_path: Path, write_skill: Callable[..., Path], fake_http: Any) -> None:
    # AC-5, D-21: the label shows which installed revision Jev saw.
    _install(tmp_path, write_skill)
    (tmp_path / "skills-lock.json").write_text(_lock({NAME: {"source": SOURCE, "computedHash": HASH, "sourceType": "github"}}), encoding="utf-8")
    (resolution,) = await SkillLoader((SkillsShSkill(name=NAME, source=SOURCE),)).load()
    assert resolution.document is not None, resolution
    assert resolution.document.text == "Prefer server components.\n"
    assert resolution.document.source == f"skills_sh:{SOURCE}/{NAME}@{HASH[:12]}"
    assert fake_http.sent == []


@pytest.mark.parametrize("interrupted", [False, True], ids=["never installed", "interrupted install"])
@pytest.mark.asyncio
async def test_missing_install_is_not_installed_with_the_install_command_and_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_skill: Callable[..., Path], interrupted: bool) -> None:
    # AC-6, EC-39, EC-40: the detail is the fix, and the path shows where a service with another working folder looked.
    service_folder = tmp_path / "service"
    service_folder.mkdir()
    monkeypatch.chdir(service_folder)
    expected_folder = service_folder / ".agents" / "skills" / NAME
    if interrupted:
        expected_folder.mkdir(parents=True)
    loader = SkillLoader((SkillsShSkill(name=NAME, source=SOURCE),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason.NOT_INSTALLED
    assert f"npx skills add {SOURCE} --skill {NAME}" in resolution.detail
    assert _names_path(resolution.detail, expected_folder), resolution.detail
    # Remembered (INV-5): installing later does not change this loader's answer.
    _install(service_folder, write_skill)
    assert (await loader.load())[0].reason is SkillUnavailableReason.NOT_INSTALLED


@pytest.mark.asyncio
async def test_installed_skill_md_cap_is_inclusive_and_over_it_is_too_large(tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # Section 9.2 local and skills.sh mapping, INV-12: an installed SKILL.md of exactly the cap loads; one byte more
    # is too_large and remembered, never a load of the first SKILL_MARKDOWN_MAX_BYTES bytes.
    head = b"---\nname: big\ndescription: A large skill.\n---\n"
    write_skill(tmp_path / ".agents" / "skills" / "at-cap", head + b"x" * (SKILL_MARKDOWN_MAX_BYTES - len(head)))
    over_cap = write_skill(tmp_path / ".agents" / "skills" / "over-cap", head + b"x" * (SKILL_MARKDOWN_MAX_BYTES + 1 - len(head)))
    loader = SkillLoader((SkillsShSkill(name="at-cap", source=SOURCE), SkillsShSkill(name="over-cap", source=SOURCE)))
    loaded, refused = await loader.load()
    assert loaded.document is not None and len(loaded.document.text.encode()) == SKILL_MARKDOWN_MAX_BYTES - len(head)
    assert refused.document is None and refused.reason is SkillUnavailableReason.TOO_LARGE
    # Remembered: shrinking the file does not change this loader's answer.
    write_skill(over_cap, body="Small now.\n")
    assert (await loader.load())[1].reason is SkillUnavailableReason.TOO_LARGE


@pytest.mark.asyncio
async def test_read_error_on_the_installed_file_is_fetch_failed_and_read_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # Section 9.2 local and skills.sh mapping (OSError -> FETCH_FAILED), INV-5, D-6: a permission problem is not a
    # missing install, so it is never remembered as not_installed and a fix works without a new agent.
    _install(tmp_path, write_skill)
    real_read = LocalSkillResolver.read_capped
    failures = [PermissionError(13, "Permission denied")]

    def flaky_read(path: Path) -> Any:
        if path.name == "SKILL.md" and failures:
            raise failures.pop()
        return real_read(path)

    monkeypatch.setattr(LocalSkillResolver, "read_capped", staticmethod(flaky_read))
    loader = SkillLoader((SkillsShSkill(name=NAME, source=SOURCE),))
    (first,) = await loader.load()
    assert first.reason is SkillUnavailableReason.FETCH_FAILED, first
    assert failures == []
    (second,) = await loader.load()
    assert second.document is not None and second.document.text == "Prefer server components.\n"


@pytest.mark.asyncio
async def test_lock_that_raises_on_read_is_treated_as_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # EC-43 ("unreadable"), D-17, INV-9: a lock read that raises (a permission problem) counts as no lock; it must
    # neither crash the run nor refuse the skill. The lock names the fork, so a lock that was read would refuse it.
    _install(tmp_path, write_skill)
    (tmp_path / "skills-lock.json").write_text(_lock({NAME: {"source": FORK, "computedHash": HASH}}), encoding="utf-8")
    real_read = LocalSkillResolver.read_capped
    lock_reads: list[Path] = []

    def unreadable_lock(path: Path) -> Any:
        if path.name == "skills-lock.json":
            lock_reads.append(path)
            raise PermissionError(13, "Permission denied")
        return real_read(path)

    monkeypatch.setattr(LocalSkillResolver, "read_capped", staticmethod(unreadable_lock))
    (resolution,) = await SkillLoader((SkillsShSkill(name=NAME, source=SOURCE),)).load()
    assert resolution.document is not None, resolution
    assert resolution.document.source == f"skills_sh:{SOURCE}/{NAME}"
    # Non-vacuity: the lock read was attempted, and it raised.
    assert len(lock_reads) == 1


@pytest.mark.asyncio
async def test_lock_naming_another_source_is_invalid_naming_both(tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # EC-41: without the check a fork's same-named skill would load under the trusted name.
    _install(tmp_path, write_skill)
    lock = tmp_path / "skills-lock.json"
    lock.write_text(_lock({NAME: {"source": FORK, "computedHash": HASH}}), encoding="utf-8")
    loader = SkillLoader((SkillsShSkill(name=NAME, source=SOURCE),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason.INVALID_SKILL
    assert SOURCE in resolution.detail and FORK in resolution.detail
    # Remembered: fixing the lock needs a new agent.
    lock.write_text(_lock({NAME: {"source": SOURCE, "computedHash": HASH}}), encoding="utf-8")
    assert (await loader.load())[0].reason is SkillUnavailableReason.INVALID_SKILL


def _write_text(text: str) -> Callable[[Path], None]:
    return lambda path: path.write_text(text, encoding="utf-8")


def _make_directory(path: Path) -> None:
    path.mkdir()


def _oversized_mismatch(path: Path) -> None:
    # Valid JSON naming the fork, padded past the SKILL.md cap, so reading it would fail the source check.
    text = _lock({NAME: {"source": FORK, "computedHash": HASH}})
    path.write_text(text + " " * (SKILL_MARKDOWN_MAX_BYTES + 1 - len(text)), encoding="utf-8")


# (case, how the lock is written or None for no lock)
BROKEN_LOCKS: list[tuple[str, Callable[[Path], None] | None]] = [
    ("no lock", None),
    ("merge conflict markers", _write_text("<<<<<<< HEAD\n" + _lock({NAME: {"source": FORK}}) + "\n=======\n{}\n>>>>>>> main\n")),
    ("version 0 naming the fork", _write_text(_lock({NAME: {"source": FORK, "computedHash": HASH}}, version=0))),
    ("skills missing", _write_text(json.dumps({"version": 1}))),
    ("skills is a list", _write_text(json.dumps({"version": 1, "skills": [{"name": NAME, "source": FORK}]}))),
    ("top level is a list", _write_text(json.dumps([{"source": FORK}]))),
    ("no entry for this skill", _write_text(_lock({"another-skill": {"source": FORK, "computedHash": HASH}}))),
    ("nested 2000 levels", _write_text('{"version": 1, "skills": ' + "[" * 2000 + "]" * 2000 + "}")),
    ("larger than the cap naming the fork", _oversized_mismatch),
    ("unreadable: a directory", _make_directory),
    ("computedHash is not text", _write_text(_lock({NAME: {"source": SOURCE, "computedHash": 42}}))),
    ("computedHash missing", _write_text(_lock({NAME: {"source": SOURCE}}))),
]


@pytest.mark.parametrize(("case", "write_lock"), BROKEN_LOCKS, ids=[row[0] for row in BROKEN_LOCKS])
@pytest.mark.asyncio
async def test_broken_or_silent_lock_is_treated_as_absent(tmp_path: Path, write_skill: Callable[..., Path], case: str, write_lock: Callable[[Path], None] | None) -> None:
    # EC-42 to EC-44, EC-46, EC-111, D-17, D-29: as npx skills does, a lock that cannot vouch for the skill is ignored.
    _install(tmp_path, write_skill)
    if write_lock is not None:
        write_lock(tmp_path / "skills-lock.json")
    (resolution,) = await SkillLoader((SkillsShSkill(name=NAME, source=SOURCE),)).load()
    assert resolution.document is not None, resolution
    assert resolution.document.source == f"skills_sh:{SOURCE}/{NAME}"


@pytest.mark.asyncio
async def test_lock_is_not_consulted_outside_the_default_layout(tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # EC-45: a vendored skills folder has no lock of its own, so a lock beside it is not about it.
    write_skill(tmp_path / "vendor" / "skills" / NAME, body="Vendored copy.\n")
    mismatch = _lock({NAME: {"source": FORK, "computedHash": HASH}})
    for folder in (tmp_path, tmp_path / "vendor", tmp_path / "vendor" / "skills"):
        (folder / "skills-lock.json").write_text(mismatch, encoding="utf-8")
    (resolution,) = await SkillLoader((SkillsShSkill(name=NAME, source=SOURCE, directory="vendor/skills"),)).load()
    assert resolution.document is not None, resolution
    assert resolution.document.text == "Vendored copy.\n"
    assert resolution.document.source == f"skills_sh:{SOURCE}/{NAME}"


@pytest.mark.asyncio
async def test_hostile_files_end_as_data_and_the_run_returns(tmp_path: Path, write_skill: Callable[..., Path], make_agent: Callable[..., Any], jev: Callable[..., Any]) -> None:
    # AC-23, EC-109 to EC-111, D-29: one hostile SKILL.md or lock must not crash every run.
    write_skill(tmp_path / ".agents" / "skills" / "bad-date", b"---\nname: bad-date\ndescription: 2024-13-45\n---\nBody\n")
    write_skill(tmp_path / ".agents" / "skills" / "deep-yaml", b"---\nname: deep-yaml\ndescription: " + b"[" * 500 + b"]" * 500 + b"\n---\nBody\n")
    _install(tmp_path, write_skill, name="good")
    (tmp_path / "skills-lock.json").write_text('{"version": 1, "skills": ' + "[" * 2000 + "]" * 2000 + "}", encoding="utf-8")
    entries = [SkillsShSkill(name=name, source=SOURCE) for name in ("bad-date", "deep-yaml", "good")]
    jev({"good": 0.9})
    agent, runner = make_agent(entries)
    reply = await agent.arun("Review the React components.")
    assert reply.content == "completed"
    bad_date, deep_yaml, good = agent.response.skills.results
    assert (bad_date.status, bad_date.reason) == (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.INVALID_SKILL)
    assert (deep_yaml.status, deep_yaml.reason) == (JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.INVALID_SKILL)
    assert bad_date.detail.strip() and deep_yaml.detail.strip()
    assert (good.status, good.source) == (JevSkillStatus.SELECTED, f"skills_sh:{SOURCE}/good")
