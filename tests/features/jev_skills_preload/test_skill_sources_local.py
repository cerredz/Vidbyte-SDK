"""FILE: tests/features/jev_skills_preload/test_skill_sources_local.py

PURPOSE: Pin LocalSkill loading from disk: the exact SKILL.md body under a folder-name label, not_found for every shape of missing file (remembered, with the absolute path), fetch_failed for read errors (retried on the next load), the SKILL.md size cap, the folder pinned at construction, symlinks followed, and the read kept off the event loop.
ROLE IN CODEBASE: Covers spec AC-4, INV-5, INV-11, INV-12, INV-18, FR-7, D-6, D-15, D-21, D-23 and EC-15 to EC-22, EC-24 for vidbyte/agents/skills/local.py through vidbyte/agents/skills/loader.py, with one JevAgent run for the AC-4 result fields.
ARCHITECTURE NOTE: Files are real, under tmp_path; SkillLoader, SkillMarkdown, and the entry records run unpatched. Only LocalSkillResolver.read_capped is replaced, and only to raise an OSError that Windows cannot produce on demand.
FUNCTION INVENTORY: test_local_skill_loads_the_exact_body_under_its_folder_name; test_missing_skill_file_is_not_found_naming_the_absolute_path; test_not_found_is_remembered_until_a_new_loader; test_remembered_not_found_says_to_create_a_new_agent_after_fixing; test_read_error_is_fetch_failed_and_read_again_next_load; test_skill_file_over_the_cap_is_too_large_and_at_the_cap_loads; test_relative_path_reads_the_folder_pinned_at_construction; test_symlinked_folder_and_file_are_followed; test_disk_read_runs_off_the_event_loop_thread.
COMMON MODIFICATION PATTERNS: A new missing-file shape adds a row to the not_found table; a new read error adds a case beside PermissionError.
WHAT NOT TO DO IN THIS FILE: 1. Do not write SKILL.md with text mode; CRLF must reach the parser unchanged. 2. Do not assert the exact detail sentence; assert the path, file name, error class, and numbers the spec names.
KNOWN EDGE CASES: NTFS is case-insensitive, so the lowercase skill.md case only runs where the filesystem is case-sensitive. Creating symlinks on Windows may need privileges; that test skips when it cannot create one.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 6.3 LocalSkill, 9.2 local mapping, 13)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_local.py
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.agents.skills.loader import SkillLoader
    from vidbyte.agents.skills.local import LocalSkillResolver
    from vidbyte.lib.constants.skills import SKILL_MARKDOWN_MAX_BYTES

    from vidbyte import JevSkillStatus, LocalSkill, SkillUnavailableReason
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

BOM = b"\xef\xbb\xbf"
AC4_BODY = "# Migrations\r\n\r\n  Keep each step reversible.\r\nRun the dry run first.\r\n"
AC4_FILE = BOM + b"---\r\nname: db-migrations\r\ndescription: >\r\n  Plans SQL migrations\r\n  and reviews them.\r\n---\r\n" + AC4_BODY.encode()
FOLDED = ("Plans SQL migrations and reviews them.", "Plans SQL migrations and reviews them.\n")


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _names_path(detail: str, path: Path) -> bool:
    # The absolute path may be written with either separator style.
    return str(path) in detail or path.as_posix() in detail


def _names_number(detail: str, number: int) -> bool:
    return str(number) in detail.replace(",", "").replace("_", "")


def _sized_skill(size: int) -> bytes:
    # A valid SKILL.md of exactly `size` bytes.
    head = b"---\nname: big\ndescription: A large skill.\n---\n"
    return head + b"x" * (size - len(head))


@pytest.mark.asyncio
async def test_local_skill_loads_the_exact_body_under_its_folder_name(tmp_path: Path, write_skill: Callable[..., Path], make_agent: Callable[..., Any], jev: Callable[..., Any], fake_http: Any) -> None:
    # AC-4, INV-11, D-21: the label carries only the folder name, never the machine path (INV-18).
    write_skill(tmp_path / "skills" / "db-migrations", AC4_FILE)
    entry = LocalSkill(name="sql-migrations", path="skills/db-migrations")
    (resolution,) = await SkillLoader((entry,)).load()
    document = resolution.document
    assert document is not None, resolution
    assert document.text == AC4_BODY
    assert document.description in FOLDED
    assert (document.name, document.source) == ("sql-migrations", "local:db-migrations")
    # The same fields reach the run's result, and the exact body reaches the main model once Jev selects it.
    jev({"sql-migrations": 0.9})
    agent, runner = make_agent([entry])
    await agent.arun("Plan the migration.")
    (result,) = agent.response.skills.results
    assert (result.name, result.status, result.source, result.reason, result.detail) == ("sql-migrations", JevSkillStatus.SELECTED, "local:db-migrations", None, None)
    assert result.description in FOLDED
    assert AC4_BODY in runner.systems[0]
    assert str(tmp_path) not in repr(agent.response)
    assert fake_http.sent == []


def _missing_folder(root: Path) -> Path:
    return root / "skills" / "absent"


def _folder_without_file(root: Path) -> Path:
    folder = root / "skills" / "empty"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("not a skill", encoding="utf-8")
    return folder


def _skill_file_is_a_directory(root: Path) -> Path:
    folder = root / "skills" / "dir-instead"
    (folder / "SKILL.md").mkdir(parents=True)
    return folder


def _path_is_a_regular_file(root: Path) -> Path:
    # EC-18: the path names a file, so there is no SKILL.md under it.
    path = root / "notes.txt"
    path.write_text("---\nname: x\ndescription: y\n---\nbody\n", encoding="utf-8")
    return path


def _only_lowercase_file(root: Path) -> Path:
    folder = root / "skills" / "lowercase"
    folder.mkdir(parents=True)
    (folder / "skill.md").write_bytes(b"---\nname: x\ndescription: y\n---\nbody\n")
    if (folder / "SKILL.md").exists():
        pytest.skip("this filesystem is case-insensitive, so skill.md is SKILL.md here")
    return folder


def _dangling_symlink(root: Path) -> Path:
    folder = root / "skills" / "dangling"
    folder.mkdir(parents=True)
    try:
        os.symlink(root / "nowhere" / "SKILL.md", folder / "SKILL.md")
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks")
    return folder


@pytest.mark.parametrize(
    "build",
    [_missing_folder, _folder_without_file, _skill_file_is_a_directory, _path_is_a_regular_file, _only_lowercase_file, _dangling_symlink],
    ids=["folder missing", "file missing", "SKILL.md is a directory", "path is a file", "only skill.md", "dangling symlink"],
)
@pytest.mark.asyncio
async def test_missing_skill_file_is_not_found_naming_the_absolute_path(tmp_path: Path, build: Callable[[Path], Path]) -> None:
    # EC-16 to EC-18, D-6: the detail tells the developer exactly where the loader looked.
    path = build(tmp_path)
    (resolution,) = await SkillLoader((LocalSkill(name="pdf", path=path),)).load()
    assert resolution.document is None
    assert resolution.reason is SkillUnavailableReason.NOT_FOUND
    assert _names_path(resolution.detail, path.absolute()), resolution.detail
    assert "SKILL.md" in resolution.detail


@pytest.mark.asyncio
async def test_not_found_is_remembered_until_a_new_loader(tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # INV-5, EC-24: a permanent miss is never read again by this loader; only a new agent (a new loader) picks up the fix.
    entry = LocalSkill(name="pdf", path=tmp_path / "skills" / "pdf")
    loader = SkillLoader((entry,))
    assert (await loader.load())[0].reason is SkillUnavailableReason.NOT_FOUND
    write_skill(tmp_path / "skills" / "pdf", body="Installed later.\n")
    assert (await loader.load())[0].reason is SkillUnavailableReason.NOT_FOUND
    assert loader.documents() == (None,)
    (fresh,) = await SkillLoader((entry,)).load()
    assert fresh.document is not None and fresh.document.text == "Installed later.\n"


@pytest.mark.asyncio
async def test_remembered_not_found_says_to_create_a_new_agent_after_fixing(tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # EC-24, EC-16, Q-1: the miss is remembered, so a developer who fixes the path and reruns sees the same
    # not_found; the detail must say a new agent is needed, and must still name the absolute path.
    folder = tmp_path / "skills" / "pdf"
    loader = SkillLoader((LocalSkill(name="pdf", path=folder),))
    (first,) = await loader.load()
    write_skill(folder, body="Installed later.\n")
    (second,) = await loader.load()
    for resolution in (first, second):
        assert resolution.reason is SkillUnavailableReason.NOT_FOUND
        assert _names_path(resolution.detail, folder.absolute()), resolution.detail
        # Judge only the SDK's own words: the temporary path can hold any word, including the test's name.
        wording = resolution.detail.replace(str(folder.absolute()), "").replace(folder.absolute().as_posix(), "").lower()
        assert "agent" in wording, resolution.detail
        assert any(word in wording for word in ("new", "create", "fresh")), resolution.detail


@pytest.mark.asyncio
async def test_read_error_is_fetch_failed_and_read_again_next_load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # EC-19, D-6: a permission fix must take effect without a restart, so read errors are never remembered.
    folder = write_skill(tmp_path / "skills" / "pdf", body="Readable now.\n")
    real_read = LocalSkillResolver.read_capped
    failures = [PermissionError(13, "Permission denied")]

    def flaky_read(path: Path) -> Any:
        if failures:
            raise failures.pop()
        return real_read(path)

    monkeypatch.setattr(LocalSkillResolver, "read_capped", staticmethod(flaky_read))
    loader = SkillLoader((LocalSkill(name="pdf", path=folder),))
    (first,) = await loader.load()
    assert first.reason is SkillUnavailableReason.FETCH_FAILED
    assert _names_path(first.detail, folder.absolute()), first.detail
    assert "PermissionError" in first.detail
    (second,) = await loader.load()
    assert second.document is not None and second.document.text == "Readable now.\n"


@pytest.mark.asyncio
async def test_skill_file_over_the_cap_is_too_large_and_at_the_cap_loads(tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # EC-20, INV-12: the cap is inclusive; one byte more is remembered as too_large, naming the size and the cap.
    at_cap = write_skill(tmp_path / "skills" / "at-cap", _sized_skill(SKILL_MARKDOWN_MAX_BYTES))
    over_cap = write_skill(tmp_path / "skills" / "over-cap", _sized_skill(SKILL_MARKDOWN_MAX_BYTES + 1))
    loader = SkillLoader((LocalSkill(name="at-cap", path=at_cap), LocalSkill(name="over-cap", path=over_cap)))
    loaded, refused = await loader.load()
    assert loaded.document is not None and len(loaded.document.text.encode()) == SKILL_MARKDOWN_MAX_BYTES - len(b"---\nname: big\ndescription: A large skill.\n---\n")
    assert refused.reason is SkillUnavailableReason.TOO_LARGE
    assert _names_number(refused.detail, SKILL_MARKDOWN_MAX_BYTES + 1), refused.detail
    assert _names_number(refused.detail, SKILL_MARKDOWN_MAX_BYTES) or "SKILL_MARKDOWN_MAX_BYTES" in refused.detail, refused.detail
    # Remembered: shrinking the file does not change this loader's answer.
    write_skill(over_cap, body="Small now.\n")
    assert (await loader.load())[1].reason is SkillUnavailableReason.TOO_LARGE


@pytest.mark.asyncio
async def test_relative_path_reads_the_folder_pinned_at_construction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # EC-15, D-15: a later chdir (a test runner, a daemon) must not move the skill.
    project, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    write_skill(project / "skills" / "pdf", body="Project copy.\n")
    write_skill(elsewhere / "skills" / "pdf", body="Decoy copy.\n")
    monkeypatch.chdir(project)
    loader = SkillLoader((LocalSkill(name="pdf", path="skills/pdf"),))
    monkeypatch.chdir(elsewhere)
    (resolution,) = await loader.load()
    assert resolution.document is not None and resolution.document.text == "Project copy.\n"


@pytest.mark.asyncio
async def test_symlinked_folder_and_file_are_followed(tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # EC-22: npx link mode and shared skill folders install symlinks.
    real = write_skill(tmp_path / "shared" / "pdf", body="Shared copy.\n")
    linked_folder = tmp_path / "skills" / "linked-folder"
    linked_file_folder = tmp_path / "skills" / "linked-file"
    linked_folder.parent.mkdir(parents=True)
    linked_file_folder.mkdir(parents=True)
    try:
        os.symlink(real, linked_folder, target_is_directory=True)
        os.symlink(real / "SKILL.md", linked_file_folder / "SKILL.md")
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks")
    resolutions = await SkillLoader((LocalSkill(name="via-folder", path=linked_folder), LocalSkill(name="via-file", path=linked_file_folder))).load()
    assert [resolution.document.text if resolution.document else resolution for resolution in resolutions] == ["Shared copy.\n", "Shared copy.\n"]
    assert [resolution.document.source for resolution in resolutions] == ["local:linked-folder", "local:linked-file"]


@pytest.mark.asyncio
async def test_disk_read_runs_off_the_event_loop_thread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_skill: Callable[..., Path]) -> None:
    # D-23: a slow disk or network mount must not block the event loop that runs the other sources.
    folder = write_skill(tmp_path / "skills" / "pdf")
    real_read = LocalSkillResolver.read_capped
    threads: list[int] = []

    def recording_read(path: Path) -> Any:
        threads.append(threading.get_ident())
        return real_read(path)

    monkeypatch.setattr(LocalSkillResolver, "read_capped", staticmethod(recording_read))
    (resolution,) = await SkillLoader((LocalSkill(name="pdf", path=folder),)).load()
    assert resolution.document is not None
    assert threads and threading.get_ident() not in threads
