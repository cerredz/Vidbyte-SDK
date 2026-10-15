"""FILE: tests/features/harness_threads/test_harness_threads_skills.py

PURPOSE: The caller's skills reach each harness only through SDK-owned locations that hold only those skills (AC-16, INV-12, FR-7, D-7): Grok copies into `skills/` of its private home and leaves that folder alone when it already matches (EC-27, R-8, R-19), opencode lists the folders in `skills.paths` without copying, Muse copies into a fresh config folder removed after the call, and links inside a skill are copied as links (T-5).
ROLE IN CODEBASE: Start here when a harness misses a skill, sees a stale one, or the SDK touches the caller's skill folders.
ARCHITECTURE NOTE: The stand-in lists, at start, the skill folders it can see (file names and SHA-256 per file). The "not rebuilt" proof is a hard link made from outside the private home to the copied SKILL.md: if the SDK removes and re-copies the folder, the link and the new file are no longer the same file, and an inode number cannot be reused while the link keeps the old one alive (AC-16's st_ino proof, made immune to inode reuse).
FUNCTION INVENTORY: digest_tree lists a source skill folder the way the stand-in does; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new skill location is a spec change first (D-7), then one test here.
WHAT NOT TO DO IN THIS FILE: Do not write into the private home from the test except the one hard link's target count.
KNOWN EDGE CASES: Symlinks need privileges on win32, so the link test skips when os.symlink fails.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-12, §6.2 AC-16, §6.3 EC-27, D-7, §10 T-5
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_skills.py
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest


def digest_tree(folder: Path) -> dict[str, str]:
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(folder.rglob("*"), key=lambda item: item.as_posix()) if path.is_file()}


@pytest.mark.asyncio
async def test_grok_skills_folder_holds_exactly_the_passed_skills_and_is_rebuilt_only_on_change(sandbox, call) -> None:
    # AC-16 / INV-12 / EC-27: [A, B] then [A] leaves only A; a third [A] keeps the same files; a changed source rebuilds; () empties it.
    alpha = sandbox.make_skill("alpha-skill", extra_files={"references/notes.md": "Alpha notes.\n"})
    beta = sandbox.make_skill("beta-skill")
    sources_before = sandbox.snapshot()
    await call("grok", skills=[alpha, beta])
    assert sandbox.starts("grok")[-1]["skills"] == {"alpha-skill": digest_tree(alpha), "beta-skill": digest_tree(beta)}
    await call("grok", skills=[alpha])
    assert sandbox.starts("grok")[-1]["skills"] == {"alpha-skill": digest_tree(alpha)}
    skills_folder = sandbox.grok_home() / "skills"
    assert sorted(path.name for path in skills_folder.iterdir()) == ["alpha-skill"]
    copied = skills_folder / "alpha-skill" / "SKILL.md"
    probe = sandbox.fake_root / "copied-skill-link"
    os.link(copied, probe)
    inode = copied.stat().st_ino
    await call("grok", skills=[alpha])
    assert os.path.samefile(probe, copied) and copied.stat().st_ino == inode, "a matching skills/ folder must not be rebuilt"
    unchanged = {path: entry for path, entry in sandbox.snapshot().items() if path.startswith("skill-src")}
    assert unchanged == {path: entry for path, entry in sources_before.items() if path.startswith("skill-src")}, "INV-12: the caller's skill folders are never written"
    (alpha / "SKILL.md").write_text("---\nname: alpha-skill\ndescription: Changed.\n---\nChanged.\n", encoding="utf-8")
    await call("grok", skills=[alpha])
    assert sandbox.starts("grok")[-1]["skills"] == {"alpha-skill": digest_tree(alpha)}
    assert not os.path.samefile(probe, copied), "a changed file must be copied again"
    await call("grok")
    assert sandbox.starts("grok")[-1]["skills"] in (None, {}), "an empty skill list leaves no skills behind"


@pytest.mark.asyncio
async def test_opencode_lists_exactly_the_passed_folders_without_copying(sandbox, call, pack) -> None:
    # AC-16 / INV-12: skills.paths lists the passed folders (resolved, in order); nothing is copied anywhere.
    alpha = sandbox.make_skill("alpha-skill")
    beta = sandbox.make_skill("beta-skill")
    before = sandbox.snapshot()
    await call("opencode", skills=[beta, alpha])
    start = sandbox.only_start("opencode")
    config = start["opencode_config"]
    assert [Path(path) for path in config["skills"]["paths"]] == [beta.resolve(), alpha.resolve()]
    assert start["skill_paths_loadable"] == [True, True]
    assert config["provider"] == {"deepseek": {"options": {"apiKey": pack.key_digest(pack.API_KEY)}}}
    assert sandbox.snapshot() == before


@pytest.mark.asyncio
async def test_muse_skills_live_in_a_fresh_config_folder_that_is_removed(sandbox, call) -> None:
    # AC-16 / INV-12: XDG_CONFIG_HOME/muse/skills/ held exactly the passed folders, and the folder is gone after the call.
    alpha = sandbox.make_skill("alpha-skill", extra_files={"scripts/run.sh": "echo alpha\n"})
    beta = sandbox.make_skill("beta-skill")
    await call("muse", skills=[alpha, beta])
    start = sandbox.only_start("muse-exec")
    assert start["skills"] == {"alpha-skill": digest_tree(alpha), "beta-skill": digest_tree(beta)}
    assert not Path(start["plain"]["XDG_CONFIG_HOME"]).exists()
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
async def test_links_inside_a_skill_are_copied_as_links(sandbox, call) -> None:
    # T-5: copytree(symlinks=True); the SDK never follows a link out of the skill folder.
    outside = sandbox.root / "outside-secret.txt"
    outside.write_text("outside the skill\n", encoding="utf-8")
    skill = sandbox.make_skill("linked-skill")
    try:
        os.symlink(outside, skill / "linked.txt")
    except (OSError, NotImplementedError):
        pytest.skip("creating a symlink needs a privilege this machine does not grant")
    await call("grok", skills=[skill])
    copied = sandbox.grok_home() / "skills" / "linked-skill" / "linked.txt"
    assert copied.is_symlink()
