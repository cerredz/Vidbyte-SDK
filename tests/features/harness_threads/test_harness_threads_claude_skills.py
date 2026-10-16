"""FILE: tests/features/harness_threads/test_harness_threads_claude_skills.py

PURPOSE: The private per-workspace Claude Code config folder and the skills in it (spec claude-thread-functions INV-13, INV-14, D-3, D-15): a run and a continue in one workspace get the same CLAUDE_CONFIG_DIR, `<home>/.vidbyte/claude-configs/<16 hex of sha256(normcase(resolved workspace))>`, whose `skills/` holds copies of exactly the passed skills, and the workspace gains nothing (AC-9); `skills/` is rebuilt only when the passed set changes and is emptied by a call with no skills (INV-14); the SDK writes nothing outside that folder and nothing inside it but `skills/` (INV-13); and the shared hostkit helper NativePrivateFolders.prepare honours every parameter it is given and maps a folder it cannot prepare to <harness>.launch_failed, for Claude and for Grok, whose private home it now prepares with Grok's own constants (§8.5, D-15, INV-20, EC-3).
ROLE IN CODEBASE: Start here when Claude misses a skill, sees a stale one, a continue cannot find its run's thread because the folder moved, or the SDK writes into the workspace or the user's own ~/.claude.
ARCHITECTURE NOTE: The stand-in lists, at start, the skill folders it can see in $CLAUDE_CONFIG_DIR/skills (file names and SHA-256 per file). The "not rebuilt" proof is a hard link made from outside the config folder to the copied SKILL.md, as the Grok skills test does: a removed and re-copied folder breaks the link's identity. The hostkit tests build NativeThreadRequest and NativeErrorFactory for real and call NativePrivateFolders.prepare directly with made-up parts, key length, folder name and templates, so a helper that ignores a parameter and uses Grok's or Claude's constants fails. The Grok guard wraps the real helper (it still runs) to see which constants a Grok call hands it.
FUNCTION INVENTORY: digest_tree lists a source skill folder the way the stand-in does; native_request builds a Claude request for the hostkit tests; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new file the SDK may write in the config folder is a spec change first (INV-13), then one name in SDK_FOLDER_ENTRIES.
WHAT NOT TO DO IN THIS FILE: Do not write into the config folder from a test except the one hard link's target count.
KNOWN EDGE CASES: The stand-in itself writes `projects/` into the config folder, as Claude Code writes its transcripts there; that is vendor state, not an SDK write.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-13, INV-14, INV-20, §6.2 AC-9, §6.3 EC-3, EC-21, EC-28, §8.1 D-3, D-15, §8.5, §12.3 rows 32 and 34
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_skills.py
"""

from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path

import pytest

SDK_FOLDER_ENTRIES = {"skills"}
VENDOR_FOLDER_ENTRIES = {"projects"}


def digest_tree(folder: Path) -> dict[str, str]:
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(folder.rglob("*"), key=lambda item: item.as_posix()) if path.is_file()}


def native_request(lib_api, sandbox, pack, skills=()):
    enums = lib_api.enums
    return lib_api.NativeThreadRequest(harness=enums.NativeHarness.CLAUDE, verb=enums.NativeThreadVerb.RUN, prompt="Explain.", api_key=pack.API_KEY, workspace=sandbox.workspace, skills=list(skills))


@pytest.mark.asyncio
async def test_run_and_continue_share_one_config_folder_holding_exactly_the_passed_skills(sandbox, call) -> None:
    # AC-9 / INV-13 / INV-14 / D-3: both children get the same
    # CLAUDE_CONFIG_DIR, the hashed folder under the user home; skills/
    # holds copies of exactly S1 and S2; the workspace gains nothing.
    first_skill = sandbox.make_skill("first-skill", extra_files={"references/notes.md": "First notes.\n"})
    second_skill = sandbox.make_skill("second-skill")
    workspace_before = {path: entry for path, entry in sandbox.snapshot().items() if path == "ws" or path.startswith("ws/")}
    first = await call("claude", skills=[first_skill, second_skill])
    await call("claude", "continue", "Again.", thread_id=first.thread_id, skills=[first_skill, second_skill])
    run_start, continue_start = sandbox.starts("claude")
    expected = os.path.normcase(str(sandbox.claude_config()))
    assert os.path.normcase(run_start["plain"]["CLAUDE_CONFIG_DIR"]) == os.path.normcase(continue_start["plain"]["CLAUDE_CONFIG_DIR"]) == expected
    listing = {"first-skill": digest_tree(first_skill), "second-skill": digest_tree(second_skill)}
    assert run_start["skills"] == listing and continue_start["skills"] == listing
    assert {path: entry for path, entry in sandbox.snapshot().items() if path == "ws" or path.startswith("ws/")} == workspace_before


@pytest.mark.asyncio
async def test_skills_folder_is_rebuilt_only_when_the_passed_set_changes(sandbox, call) -> None:
    # INV-14: [A, B] then [A] leaves only A; a third [A] keeps the same
    # files; a changed source is copied again; no skills empties it; the
    # caller's skill folders are never written.
    alpha = sandbox.make_skill("alpha-skill", extra_files={"references/notes.md": "Alpha notes.\n"})
    beta = sandbox.make_skill("beta-skill")
    sources_before = {path: entry for path, entry in sandbox.snapshot().items() if path.startswith("skill-src")}
    await call("claude", skills=[alpha, beta])
    assert sandbox.starts("claude")[-1]["skills"] == {"alpha-skill": digest_tree(alpha), "beta-skill": digest_tree(beta)}
    await call("claude", skills=[alpha])
    assert sandbox.starts("claude")[-1]["skills"] == {"alpha-skill": digest_tree(alpha)}
    skills_folder = sandbox.claude_config() / "skills"
    assert sorted(path.name for path in skills_folder.iterdir()) == ["alpha-skill"]
    copied = skills_folder / "alpha-skill" / "SKILL.md"
    probe = sandbox.fake_root / "copied-skill-link"
    os.link(copied, probe)
    await call("claude", skills=[alpha])
    assert os.path.samefile(probe, copied), "INV-14: a matching skills/ folder must not be rebuilt"
    assert {path: entry for path, entry in sandbox.snapshot().items() if path.startswith("skill-src")} == sources_before
    (alpha / "SKILL.md").write_text("---\nname: alpha-skill\ndescription: Changed.\n---\nChanged.\n", encoding="utf-8")
    await call("claude", skills=[alpha])
    assert sandbox.starts("claude")[-1]["skills"] == {"alpha-skill": digest_tree(alpha)}
    assert not os.path.samefile(probe, copied), "a changed file must be copied again"
    await call("claude")
    assert sandbox.starts("claude")[-1]["skills"] in (None, {}), "INV-14: a call with no skills leaves skills/ empty or absent"


@pytest.mark.asyncio
async def test_successful_call_writes_only_skills_in_the_private_config_folder(sandbox, call) -> None:
    # INV-13 / EC-28 / NFR: nothing in the workspace, the skill folders,
    # the user's ~/.claude or ~/.claude.json; under the home only the
    # config folder and its parents; inside it the SDK writes only
    # skills/ (projects/ is the stand-in's own transcripts).
    skill = sandbox.make_skill("review-notes", extra_files={"references/checklist.md": "Check the edges.\n"})
    before = sandbox.snapshot()
    before_environ = dict(os.environ)
    await call("claude", skills=[skill])
    after = sandbox.snapshot()
    added = sorted(set(after) - set(before))
    changed = sorted(path for path in before if after.get(path) != before[path])
    assert changed == [], f"files changed: {changed}"
    folder = sandbox.claude_config().relative_to(sandbox.root).as_posix()
    allowed_parents = {"home/.vidbyte", "home/.vidbyte/claude-configs", folder}
    outside = [path for path in added if path not in allowed_parents and not path.startswith(folder + "/")]
    assert outside == [], f"written outside the private config folder: {outside}"
    inside = {path[len(folder) + 1 :].split("/", 1)[0] for path in added if path.startswith(folder + "/")}
    assert inside <= SDK_FOLDER_ENTRIES | VENDOR_FOLDER_ENTRIES and "skills" in inside, f"the SDK writes only skills/ in the config folder: {inside}"
    assert dict(os.environ) == before_environ


def test_private_folders_helper_honours_every_parameter(lib_api, sandbox, pack) -> None:
    # §8.5 / D-15 / §12.3 row 32: the folder is <home>/<parts>/<first
    # key_hex_chars of sha256(normcase(resolved workspace))>, its
    # <skills_dir> holds the request's skills, and the folder is
    # returned.
    hostkit = importlib.import_module("vidbyte.harnesses.native.hostkit")
    skill = sandbox.make_skill("helper-skill")
    request = native_request(lib_api, sandbox, pack, [skill])
    errors = hostkit.NativeErrorFactory(lib_api.enums.NativeHarness.CLAUDE, lib_api.enums.NativeThreadOperation.RUN_CLAUDE_THREAD)
    folder = hostkit.NativePrivateFolders.prepare(request, errors, parts=("x-parts", "y-part"), key_hex_chars=8, skills_dir="loaded", unknown_detail="Home unknown ({error_type}).", failure_detail="Folder {home} failed ({error_type}: {reason}).")
    key = hashlib.sha256(os.path.normcase(str(sandbox.workspace.resolve())).encode("utf-8")).hexdigest()[:8]
    assert Path(folder) == sandbox.home / "x-parts" / "y-part" / key
    assert sorted(path.name for path in (Path(folder) / "loaded").iterdir()) == ["helper-skill"]
    assert digest_tree(Path(folder) / "loaded" / "helper-skill") == digest_tree(skill)
    assert not (sandbox.home / ".vidbyte").exists(), "the helper used no constant of its own"


def test_private_folders_helper_maps_an_unpreparable_folder_to_launch_failed(lib_api, sandbox, pack) -> None:
    # §8.5 / EC-3 / §12.3 row 32: an OSError becomes the harness's
    # launch_failed with failure_detail filled with {home}, {error_type}
    # and {reason}; nothing of the key appears.
    hostkit = importlib.import_module("vidbyte.harnesses.native.hostkit")
    (sandbox.home / "x-parts").write_text("a file, not a folder\n", encoding="utf-8")
    request = native_request(lib_api, sandbox, pack)
    errors = hostkit.NativeErrorFactory(lib_api.enums.NativeHarness.CLAUDE, lib_api.enums.NativeThreadOperation.RUN_CLAUDE_THREAD)
    with pytest.raises(lib_api.NativeThreadError) as caught:
        hostkit.NativePrivateFolders.prepare(request, errors, parts=("x-parts", "y-part"), key_hex_chars=8, skills_dir="loaded", unknown_detail="Home unknown ({error_type}).", failure_detail="Folder {home} failed ({error_type}: {reason}).")
    error = caught.value
    assert error.failure_code.value == "claude.launch_failed"
    assert "Folder " in str(error) and " failed (" in str(error) and pack.API_KEY not in str(error)


@pytest.mark.asyncio
async def test_grok_and_claude_prepare_their_folders_through_the_one_helper(api, sandbox, call, monkeypatch) -> None:
    # D-15 / INV-20 / §12.3 rows 19 and 34: both harnesses call
    # NativePrivateFolders.prepare, each with its own constants, so the
    # folder logic exists once; Grok's folder and skills are unchanged.
    hostkit = importlib.import_module("vidbyte.harnesses.native.hostkit")
    real_prepare = hostkit.NativePrivateFolders.prepare
    seen: list[dict] = []

    def recording_prepare(request, errors, **options):
        seen.append({"harness": request.harness.value, **options})
        return real_prepare(request, errors, **options)

    monkeypatch.setattr(hostkit.NativePrivateFolders, "prepare", staticmethod(recording_prepare))
    skill = sandbox.make_skill("shared-skill")
    await call("grok", skills=[skill])
    await call("claude", skills=[skill])
    constants = api.constants
    assert seen == [
        {"harness": "grok", "parts": constants.GROK_PRIVATE_HOMES_PARTS, "key_hex_chars": constants.GROK_HOME_KEY_HEX_CHARS, "skills_dir": constants.GROK_SKILLS_DIR, "unknown_detail": constants.GROK_HOME_UNKNOWN_DETAIL, "failure_detail": constants.GROK_HOME_FAILURE_DETAIL},
        {"harness": "claude", "parts": constants.CLAUDE_PRIVATE_CONFIGS_PARTS, "key_hex_chars": constants.CLAUDE_CONFIG_KEY_HEX_CHARS, "skills_dir": constants.CLAUDE_SKILLS_DIR, "unknown_detail": constants.CLAUDE_CONFIG_UNKNOWN_DETAIL, "failure_detail": constants.CLAUDE_CONFIG_FAILURE_DETAIL},
    ]
    assert sandbox.only_start("grok")["skills"] == {"shared-skill": digest_tree(skill)}
    assert os.path.normcase(sandbox.only_start("grok")["plain"]["GROK_HOME"]) == os.path.normcase(str(sandbox.grok_home()))
