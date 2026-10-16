"""FILE: tests/features/harness_threads/test_harness_threads_grok_helpers.py

PURPOSE: The eight Grok thread helpers over a real-layout store: list order, window, tie-break, duplicates and limit (AC-2, INV-7, EC-15 to EC-17), the wrappers (AC-3), get with the §9.1 mapping (AC-4), read through `grok export` (AC-5, EC-21), lineage (AC-6, INV-10, EC-25 to EC-27), search (AC-7, EC-7), delete with its post-check (AC-8, INV-11, EC-23), the SDK and USER scopes (AC-9, INV-13, EC-17 to EC-20, D-21), strict reads (AC-19, INV-6, EC-8 to EC-10, EC-14), the non-session files and the layout bound (AC-27, EC-11, EC-66, EC-67), one-id reads that ignore a corrupt sibling (AC-28, EC-68, D-27), and store errors (EC-13).
ROLE IN CODEBASE: Start here when a Grok list, get, lineage, search, read or delete returns the wrong threads or fails on a real store.
ARCHITECTURE NOTE: Stores are real files written by conftest.py `Stores.grok_thread` in Grok's layout (`<home>/sessions/<url-encoded cwd>/<id>/summary.json`) under the sandbox home, which `Path.home()` resolves to. List, get, lineage and search read files only; read and delete run the stand-in grok (`export`, `sessions delete`) through `GrokThreadConfig.grok_command`. Summaries are compared as field tuples (`shapes.summary_fields`), so no record import is needed to state the expectation.
FUNCTION INVENTORY: hours_ago builds a time relative to the start of the test; expect builds the expected field tuple; mentions checks that a message names a path; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new Grok store fact is a stand-in change (fake_harness_helpers.py) and a builder change (conftest.py) first, then a case here.
WHAT NOT TO DO IN THIS FILE: Do not mock the filesystem or Path.home beyond the EC-13 case; write real store files.
KNOWN EDGE CASES: Times inside a `since` window sit whole hours away from its edge, because the helper reads the clock itself (spec §13). The PermissionError case locks the file on win32 (msvcrt) and removes its read bit on POSIX (skipped as root, which ignores file modes).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-4, INV-6, INV-7, INV-10, INV-11, INV-13, §6.2 AC-2 to AC-9, AC-19, AC-27, AC-28, §6.3 EC-1, EC-7 to EC-27, EC-66 to EC-68, §9.1, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_grok_helpers.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

WS_HOURS = timedelta(hours=24)
PLUS_TWO = timezone(timedelta(hours=2))
UNKNOWN = "f0000000-0000-4000-8000-000000000404"
OLD_SECONDS = 3600


def hours_ago(now: datetime, hours: float) -> datetime:
    return now - timedelta(hours=hours)


def expect(thread_id: str, created: datetime, updated: datetime, *, title: str | None = "Thread title", parent: str | None = None, model: str | None = "grok-build-fast-1") -> tuple:
    return ("grok", thread_id, title, created, updated, parent, model)


def mentions(message: str, path) -> bool:
    spellings = {str(path), pathlib.Path(path).as_posix()}
    if sys.platform == "win32":
        return any(text.casefold() in message.casefold() for text in spellings)
    return any(text in message for text in spellings)


@pytest.mark.asyncio
async def test_sdk_list_is_newest_first_ties_by_id_descending_window_and_limit(sandbox, helper, stores, shapes) -> None:
    # AC-2 / INV-7 / EC-15 / EC-16 / EC-17: window, order, tie-break,
    # one entry per id (the newer copy, here across two groups of the
    # private home) and the limit, applied in that order.
    now = datetime.now(timezone.utc)
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stores.grok_thread("old-one", created=created, updated=hours_ago(now, 48))
    stores.grok_thread("fresh", created=created, updated=hours_ago(now, 1))
    stores.grok_thread("tie-a", created=created, updated=hours_ago(now, 3))
    stores.grok_thread("tie-b", created=created, updated=hours_ago(now, 3))
    stores.grok_thread("dup", created=created, updated=hours_ago(now, 10), title="older copy")
    stores.grok_thread("dup", group="second-group", created=created, updated=hours_ago(now, 2), title="newer copy")
    offset = hours_ago(now, 5).astimezone(PLUS_TWO)
    stores.grok_thread("offset", created=created.astimezone(PLUS_TWO).isoformat(), updated=offset.isoformat())
    stores.grok_thread("last", created=created, updated=hours_ago(now, 20))
    listed = await helper("list_grok_threads", sandbox.workspace, since=WS_HOURS, limit=5)
    assert isinstance(listed, tuple)
    assert [shapes.summary_fields(summary) for summary in listed] == [
        expect("fresh", created, hours_ago(now, 1)), expect("dup", created, hours_ago(now, 2), title="newer copy"),
        expect("tie-b", created, hours_ago(now, 3)), expect("tie-a", created, hours_ago(now, 3)), expect("offset", created, offset),
    ]
    assert all(summary.updated_at.utcoffset() == timedelta(0) for summary in listed), "D-13: UTC-aware"
    everything = await helper("list_grok_threads", sandbox.workspace, limit=200)
    assert [summary.thread_id for summary in everything] == ["fresh", "dup", "tie-b", "tie-a", "offset", "last", "old-one"]


@pytest.mark.asyncio
async def test_workspace_without_a_grok_home_lists_nothing_and_creates_nothing(api, sandbox, helper, check_error) -> None:
    # EC-1 / EC-18 / INV-4 / D-11: no private home and no ~/.grok/sessions
    # mean "no threads"; nothing is created on the way.
    before = sandbox.snapshot(include_fake=True)
    assert await helper("list_grok_threads", sandbox.workspace) == ()
    assert await helper("list_recent_grok_threads", sandbox.workspace, scope=api.enums.GrokThreadScope.USER) == ()
    assert await helper("search_grok_threads", sandbox.workspace, "anything") == ()
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_grok_thread", UNKNOWN, sandbox.workspace)
    check_error(caught.value, harness="grok", operation="get_grok_thread", code="grok.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN)
    assert sandbox.snapshot(include_fake=True) == before, "INV-4: a read path never creates a Grok home"
    assert not sandbox.grok_home().exists()


@pytest.mark.asyncio
async def test_recent_and_since_wrappers_equal_the_base_list_with_named_default_limits(api, sandbox, helper, stores) -> None:
    # AC-3 / INV-7: list_recent_ = list_(limit=n); list_..._since(d) =
    # list_(since=d); default limits 20 and 10.
    now = datetime.now(timezone.utc)
    for hour in range(1, 26):
        stores.grok_thread(f"thread-{hour:02d}", updated=hours_ago(now, hour))
    ws = sandbox.workspace
    listed = await helper("list_grok_threads", ws)
    assert len(listed) == api.constants.NATIVE_LIST_DEFAULT_LIMIT == 20
    recent = await helper("list_recent_grok_threads", ws)
    assert len(recent) == api.constants.NATIVE_RECENT_DEFAULT_LIMIT == 10
    assert recent == await helper("list_grok_threads", ws, limit=10) == listed[:10]
    assert await helper("list_recent_grok_threads", ws, limit=3) == await helper("list_grok_threads", ws, limit=3)
    window = timedelta(hours=12, minutes=30)
    since = await helper("list_grok_threads_since", ws, window)
    assert since == await helper("list_grok_threads", ws, since=window) and len(since) == 12
    assert await helper("list_grok_threads_since", ws, timedelta(hours=30), limit=3) == await helper("list_grok_threads", ws, since=timedelta(hours=30), limit=3)


@pytest.mark.asyncio
async def test_get_maps_summary_json_and_an_unknown_id_is_thread_not_found(api, sandbox, helper, stores, shapes, check_error) -> None:
    # AC-4 / §9.1: folder name -> thread_id, generated_title -> title
    # (null, absent or blank -> None), times -> UTC, parent_session_id,
    # current_model_id; an unknown id names itself.
    created = datetime(2026, 10, 1, 9, 0, tzinfo=PLUS_TWO)
    updated = datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc)
    stores.grok_thread("child", created=created, updated=updated, title="Fix the login flow", parent="root-gone", model="grok-code-fast-1")
    stores.grok_thread("null-title", created=created, updated=updated, title=None)
    stores.grok_thread("no-title", created=created, updated=updated, drop=["generated_title"])
    stores.grok_thread("blank-title", created=created, updated=updated, title="   ")
    found = await helper("get_grok_thread", "child", sandbox.workspace)
    assert shapes.summary_fields(found) == expect("child", created, updated, title="Fix the login flow", parent="root-gone", model="grok-code-fast-1")
    for thread_id in ("null-title", "no-title", "blank-title"):
        assert (await helper("get_grok_thread", thread_id, sandbox.workspace)).title is None, thread_id
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_grok_thread", UNKNOWN, sandbox.workspace)
    check_error(caught.value, harness="grok", operation="get_grok_thread", code="grok.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN)


@pytest.mark.asyncio
async def test_read_returns_the_export_document_whole_through_a_keyless_child(api, sandbox, helper, stores, check_error) -> None:
    # AC-5 / INV-21 / D-16 / INV-2 / INV-17: `grok export <id>` with
    # GROK_HOME = the scope home, cwd = workspace and no key; stdout
    # byte for byte; an unknown id starts no export.
    document = "# Grok session read-me\r\n\n## User\n\nÉtude — naïve café ☕\n".encode("utf-8")
    stores.grok_thread("read-me", transcript=document)
    result = await helper("read_grok_thread", "read-me", sandbox.workspace)
    assert isinstance(result, api.NativeThreadResult)
    assert (result.harness, result.thread_id, result.text, result.text_truncated) == (api.enums.NativeHarness.GROK, "read-me", document.decode("utf-8"), False)
    start = sandbox.only_start("grok-export")
    assert start["argv"] == ["export", "read-me"]
    assert os.path.normcase(start["plain"]["GROK_HOME"]) == os.path.normcase(str(sandbox.grok_home()))
    assert start["plain"]["GROK_DISABLE_AUTOUPDATER"] == "1"
    assert all(value is None for value in start["credentials"].values()), "INV-2: no key in a helper child"
    assert pathlib.Path(start["cwd"]).resolve() == sandbox.workspace
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("read_grok_thread", UNKNOWN, sandbox.workspace)
    check_error(caught.value, harness="grok", operation="read_grok_thread", code="grok.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN)
    assert len(sandbox.starts("grok-export")) == 1, "D-16: the store lookup fails first; no export starts"


@pytest.mark.asyncio
async def test_read_of_a_thread_removed_before_export_is_thread_not_found(api, sandbox, helper, stores, check_error) -> None:
    # EC-21: the store had it, then `grok export` prints
    # "Session '<id>' not found." (GROK_SESSION_NOT_FOUND_TEXT).
    stores.grok_thread("vanishing")
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("read_grok_thread", "vanishing", sandbox.workspace, fake={"export_mode": "not_found"})
    check_error(caught.value, harness="grok", operation="read_grok_thread", code="grok.thread_not_found", workspace=sandbox.workspace, thread_id="vanishing")


@pytest.mark.asyncio
async def test_lineage_is_root_first_linked_and_ends_at_a_missing_parent(sandbox, helper, stores, shapes) -> None:
    # AC-6 / INV-10 / EC-25 / D-23: root <- fork <- fork-of-fork; a
    # thread whose parent is gone is its own chain head.
    when = datetime(2026, 5, 1, tzinfo=timezone.utc)
    stores.grok_thread("root", created=when, updated=when)
    stores.grok_thread("fork", created=when, updated=when + timedelta(hours=1), parent="root")
    stores.grok_thread("fork-of-fork", created=when, updated=when + timedelta(hours=2), parent="fork")
    stores.grok_thread("orphan", created=when, updated=when, parent="deleted-parent")
    chain = await helper("get_grok_thread_lineage", "fork-of-fork", sandbox.workspace)
    assert [summary.thread_id for summary in chain] == ["root", "fork", "fork-of-fork"]
    assert all(chain[index + 1].parent_thread_id == chain[index].thread_id for index in range(len(chain) - 1))
    assert chain[0].parent_thread_id is None
    assert shapes.summary_fields(chain[-1]) == expect("fork-of-fork", when, when + timedelta(hours=2), parent="fork")
    orphan = await helper("get_grok_thread_lineage", "orphan", sandbox.workspace)
    assert [(summary.thread_id, summary.parent_thread_id) for summary in orphan] == [("orphan", "deleted-parent")]
    assert [summary.thread_id for summary in await helper("get_grok_thread_lineage", "root", sandbox.workspace)] == ["root"]


@pytest.mark.asyncio
async def test_lineage_cycle_and_a_chain_past_the_depth_cap_are_protocol_mismatch(api, sandbox, helper, stores, check_error) -> None:
    # EC-26 / EC-27 / INV-10 / INV-16: a repeated id is named; a chain
    # of exactly NATIVE_LINEAGE_MAX_DEPTH passes and one more fails.
    stores.grok_thread("cycle-a", parent="cycle-b")
    stores.grok_thread("cycle-b", parent="cycle-a")
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_grok_thread_lineage", "cycle-a", sandbox.workspace)
    check_error(caught.value, harness="grok", operation="get_grok_thread_lineage", code="grok.protocol_mismatch", workspace=sandbox.workspace, thread_id="cycle-a", observations=[("repeated id", ("cycle-a", "cycle-b"))])
    depth = api.constants.NATIVE_LINEAGE_MAX_DEPTH
    for index in range(depth + 1):
        stores.grok_thread(f"deep-{index:03d}", parent=None if index == 0 else f"deep-{index - 1:03d}")
    full = await helper("get_grok_thread_lineage", f"deep-{depth - 1:03d}", sandbox.workspace)
    assert len(full) == depth and full[0].thread_id == "deep-000"
    with pytest.raises(api.NativeThreadError) as too_deep:
        await helper("get_grok_thread_lineage", f"deep-{depth:03d}", sandbox.workspace)
    check_error(too_deep.value, harness="grok", operation="get_grok_thread_lineage", code="grok.protocol_mismatch", workspace=sandbox.workspace, thread_id=f"deep-{depth:03d}", observations=[("depth cap", (str(depth), "NATIVE_LINEAGE_MAX_DEPTH"))])


@pytest.mark.asyncio
async def test_search_is_a_literal_case_insensitive_match_over_title_and_both_summaries(sandbox, helper, stores) -> None:
    # AC-7 / D-3 / EC-7: generated_title, session_summary and
    # last_turn_summary; `fix.*bug` matches only itself; INV-7 order
    # and limit.
    when = datetime(2026, 6, 1, tzinfo=timezone.utc)
    stores.grok_thread("in-title", updated=when + timedelta(hours=4), title="Please FIX.*BUG now")
    stores.grok_thread("in-summary", updated=when + timedelta(hours=3), title="Other", session_summary="we tried fix.*Bug twice")
    stores.grok_thread("in-last-turn", updated=when + timedelta(hours=2), title=None, last_turn_summary="Fix.*bug done")
    stores.grok_thread("regex-only", updated=when + timedelta(hours=5), title="fixABCbug and fix-bug")
    stores.grok_thread("nowhere", updated=when + timedelta(hours=6), title="Unrelated", session_summary="nothing", last_turn_summary="nothing")
    found = await helper("search_grok_threads", sandbox.workspace, "fix.*bug")
    assert [summary.thread_id for summary in found] == ["in-title", "in-summary", "in-last-turn"]
    assert [summary.thread_id for summary in await helper("search_grok_threads", sandbox.workspace, "FIX.*BUG", limit=2)] == ["in-title", "in-summary"]


@pytest.mark.asyncio
async def test_delete_removes_the_session_folder_and_checks_that_it_is_gone(api, sandbox, helper, stores, check_error, pack) -> None:
    # AC-8 / INV-11 / D-16 / EC-23: `grok sessions delete <id>` under
    # the scope home, then the folder must be gone; an exit 0 that
    # leaves it is run_failed naming the folder; an unknown id starts
    # no child.
    doomed = stores.grok_thread("doomed")
    stores.grok_thread("kept")
    assert await helper("delete_grok_thread", "doomed", sandbox.workspace) is None
    assert not doomed.exists()
    start = sandbox.only_start("grok-delete")
    assert start["argv"] == ["sessions", "delete", "doomed"]
    assert os.path.normcase(start["plain"]["GROK_HOME"]) == os.path.normcase(str(sandbox.grok_home()))
    assert all(value is None for value in start["credentials"].values())
    assert [summary.thread_id for summary in await helper("list_grok_threads", sandbox.workspace)] == ["kept"]
    sticky = stores.grok_thread("sticky")
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("delete_grok_thread", "sticky", sandbox.workspace, fake={"delete_mode": "leave"})
    check_error(caught.value, harness="grok", operation="delete_grok_thread", code="grok.run_failed", workspace=sandbox.workspace, thread_id="sticky", observations=[("folder still there", pack.path_spellings(sticky))])
    with pytest.raises(api.NativeThreadError) as unknown:
        await helper("delete_grok_thread", UNKNOWN, sandbox.workspace)
    check_error(unknown.value, harness="grok", operation="delete_grok_thread", code="grok.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN)
    assert len(sandbox.starts("grok-delete")) == 2, "INV-11: no delete child for an id the store lookup did not find"


@pytest.mark.asyncio
async def test_sdk_scope_reads_the_private_home_and_user_scope_the_users_own_store(api, sandbox, helper, stores, monkeypatch) -> None:
    # AC-9 / INV-13 / D-21 / EC-17 / EC-19 / EC-20: USER keeps groups
    # whose decoded name or .cwd normcase-equals the workspace, ignores
    # an inherited GROK_HOME, keeps a duplicated id once (the newer);
    # SDK sees only the private home.
    user, ws = stores.user_grok, sandbox.workspace
    when = datetime(2026, 7, 1, tzinfo=timezone.utc)
    stores.grok_thread("private", updated=when)
    stores.grok_thread("user-encoded", home=user, updated=when + timedelta(hours=1))
    stores.grok_thread("user-dotcwd", home=user, group="renamed-group", updated=when + timedelta(hours=2))
    (user / "sessions" / "renamed-group" / ".cwd").write_text(str(ws) + "\n", encoding="utf-8")
    stores.grok_thread("dup", home=user, updated=when + timedelta(hours=3), title="older")
    stores.grok_thread("dup", home=user, group="renamed-group", updated=when + timedelta(hours=4), title="newer")
    stores.grok_thread("other-workspace", home=user, group=stores.grok_group(sandbox.root / "elsewhere"), updated=when + timedelta(hours=5))
    stores.grok_thread("case-variant", home=user, group=stores.grok_group(str(ws).swapcase()), updated=when + timedelta(hours=6))
    decoy_home = sandbox.root / "decoy-grok-home"
    stores.grok_thread("from-grok-home-variable", home=decoy_home, updated=when + timedelta(hours=7))
    monkeypatch.setenv("GROK_HOME", str(decoy_home))
    sdk = await helper("list_grok_threads", ws, limit=200)
    assert [summary.thread_id for summary in sdk] == ["private"]
    users = await helper("list_grok_threads", ws, limit=200, scope=api.enums.GrokThreadScope.USER)
    expected = (["case-variant"] if sys.platform == "win32" else []) + ["dup", "user-dotcwd", "user-encoded"]
    assert [summary.thread_id for summary in users] == expected, "EC-19: letter case folds only on win32"
    assert [summary.title for summary in users if summary.thread_id == "dup"] == ["newer"]
    assert (await helper("get_grok_thread", "user-encoded", ws, scope=api.enums.GrokThreadScope.USER)).thread_id == "user-encoded"
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_grok_thread", "user-encoded", ws)
    message = str(caught.value)
    assert caught.value.failure_code.value == "grok.thread_not_found"
    assert "sdk" in message.casefold() and mentions(message, sandbox.grok_home()), "EC-20: the detail names the scope and the home searched"


@pytest.mark.asyncio
async def test_non_session_files_in_a_real_store_change_no_result(api, sandbox, helper, stores) -> None:
    # AC-27 / EC-66 / D-27: session_search.sqlite, permission*.toml and
    # .cwd beside the session folders are ignored by every helper.
    when = datetime(2026, 8, 1, tzinfo=timezone.utc)
    home = sandbox.grok_home()
    stores.grok_thread("root", updated=when, transcript=b"# root\n")
    stores.grok_thread("leaf", updated=when + timedelta(hours=1), parent="root", title="find me", transcript=b"# leaf\n")
    stores.grok_thread("spare", updated=when + timedelta(hours=2))
    ws = sandbox.workspace

    async def results() -> tuple:
        return (
            await helper("list_grok_threads", ws), await helper("search_grok_threads", ws, "FIND"), await helper("get_grok_thread", "leaf", ws),
            await helper("get_grok_thread_lineage", "leaf", ws), (await helper("read_grok_thread", "leaf", ws)).text,
        )

    clean = await results()
    stores.grok_noise(home, stores.grok_group(), str(ws))
    stores.grok_noise(home, "another-group", str(ws))
    assert await results() == clean
    assert await helper("delete_grok_thread", "spare", ws) is None
    stores.grok_thread("user-thread", home=stores.user_grok, updated=when)
    stores.grok_noise(stores.user_grok, stores.grok_group(), str(ws))
    users = await helper("list_grok_threads", ws, scope=api.enums.GrokThreadScope.USER)
    assert [summary.thread_id for summary in users] == ["user-thread"]


@pytest.mark.asyncio
async def test_store_whose_folders_all_lack_summary_json_is_a_layout_mismatch_after_the_grace_period(api, sandbox, helper, stores, check_error, pack) -> None:
    # AC-27 / EC-67 / D-31 / EC-11: every session folder without
    # summary.json and the newest older than GROK_SUMMARY_GRACE_SECONDS
    # is a renamed layout; a fresh one is a run still starting.
    group = sandbox.grok_home() / "sessions" / stores.grok_group()
    folders = [group / f"no-summary-{index}" for index in range(2)]
    old = time.time() - OLD_SECONDS
    for folder in folders:
        folder.mkdir(parents=True)
        (folder / "chat_history.jsonl").write_text("{}\n", encoding="utf-8")
        os.utime(folder, (old, old))
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("list_grok_threads", sandbox.workspace)
    check_error(caught.value, harness="grok", operation="list_grok_threads", code="grok.protocol_mismatch", workspace=sandbox.workspace)
    message = str(caught.value)
    assert "summary.json" in message and mentions(message, sandbox.grok_home()), f"EC-67: the expected layout and the home are named: {message!r}"
    os.utime(folders[1], None)
    assert await helper("list_grok_threads", sandbox.workspace) == (), "EC-11: a folder younger than the grace period is a run still starting"
    os.utime(folders[1], (old, old))
    stores.grok_thread("complete")
    assert [summary.thread_id for summary in await helper("list_grok_threads", sandbox.workspace)] == ["complete"], "EC-11: folders without summary.json are skipped beside real threads"


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "member"), [
    ("missing-created", "created_at"), ("int-updated", "updated_at"), ("naive-time", "created_at"), ("garbled-time", "updated_at"),
    ("json-array", None), ("invalid-json", None), ("invalid-utf8", None), ("oversize", None), ("long-title", "generated_title"),
    ("bad-model", "current_model_id"), ("title-not-text", "generated_title"), ("bad-folder-id", None),
])
async def test_unreadable_summary_json_is_protocol_mismatch_naming_the_file_and_member(api, sandbox, helper, stores, check_error, case, member) -> None:
    # AC-19 / INV-6 / EC-8 / EC-9 / EC-10 / EC-14: never a skipped
    # thread or a partial list; the file (and the member) is named.
    stores.grok_thread("good-one")
    thread_id = "bad.id" if case == "bad-folder-id" else "broken"
    cap = api.constants.GROK_SUMMARY_MAX_BYTES
    layouts = {
        "missing-created": {"drop": ["created_at"]}, "int-updated": {"updated": 1760529600}, "naive-time": {"created": "2026-10-15T12:00:00"},
        "garbled-time": {"updated": "15/10/2026 noon"}, "json-array": {"raw": b"[1, 2]"}, "invalid-json": {"raw": b"{\"created_at\": "},
        "invalid-utf8": {"raw": b"{\"generated_title\": \"\xff\xfe\"}"}, "oversize": {"raw": b"{}" + b" " * (cap - 1)},
        "long-title": {"title": "t" * (api.constants.NATIVE_TITLE_MAX_CHARS + 1)}, "bad-model": {"model": "grok fast"}, "title-not-text": {"extra": {"generated_title": 42}},
        "bad-folder-id": {},
    }
    fields = dict(layouts[case])
    if "updated" in fields and not isinstance(fields["updated"], str):
        fields["extra"] = {"updated_at": fields.pop("updated")}
    folder = stores.grok_thread(thread_id, **fields)
    path = folder / "summary.json"
    for name in ("list_grok_threads", "search_grok_threads"):
        arguments = (sandbox.workspace, "good") if name.startswith("search") else (sandbox.workspace,)
        with pytest.raises(api.NativeThreadError) as caught:
            await helper(name, *arguments)
        message = str(caught.value)
        check_error(caught.value, harness="grok", operation=name, code="grok.protocol_mismatch", workspace=sandbox.workspace)
        assert mentions(message, path), f"INV-6: {case}: the message names {path}: {message!r}"
        if member is not None:
            assert member in message, f"INV-6: {case}: the message names {member}"
        if case == "oversize":
            assert str(cap + 1) in message or f"{cap + 1:,}" in message, "EC-10: the size is named"


@pytest.mark.asyncio
async def test_one_id_operations_read_only_their_own_file_while_scans_stay_strict(api, sandbox, helper, stores, check_error) -> None:
    # AC-28 / EC-68 / D-27: a sibling B that is invalid JSON, then
    # oversize, cannot fail get, read, lineage or delete of A; list and
    # search still raise naming B's file.
    cap = api.constants.GROK_SUMMARY_MAX_BYTES
    for broken in (b"{\"created_at\": ", b"{}" + b" " * cap):
        stores.grok_thread("root-a")
        stores.grok_thread("thread-a", parent="root-a", transcript=b"# thread-a\n")
        sibling = stores.grok_thread("sibling-b", raw=broken)
        ws = sandbox.workspace
        assert (await helper("get_grok_thread", "thread-a", ws)).thread_id == "thread-a"
        assert (await helper("read_grok_thread", "thread-a", ws)).text == "# thread-a\n"
        assert [summary.thread_id for summary in await helper("get_grok_thread_lineage", "thread-a", ws)] == ["root-a", "thread-a"]
        for name, arguments in (("list_grok_threads", (ws,)), ("search_grok_threads", (ws, "thread"))):
            with pytest.raises(api.NativeThreadError) as caught:
                await helper(name, *arguments)
            assert caught.value.failure_code.value == "grok.protocol_mismatch" and mentions(str(caught.value), sibling / "summary.json"), str(caught.value)
        assert await helper("delete_grok_thread", "thread-a", ws) is None


@pytest.mark.asyncio
async def test_unknown_home_is_store_unreadable_naming_the_error_class(api, sandbox, helper, monkeypatch, check_error) -> None:
    # EC-13 / D-12: Path.home() raising RuntimeError is
    # grok.store_unreadable, not runtime.error.
    def no_home(cls=None):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(pathlib.Path, "home", classmethod(no_home))
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("list_grok_threads", sandbox.workspace)
    check_error(caught.value, harness="grok", operation="list_grok_threads", code="grok.store_unreadable", workspace=sandbox.workspace, observations=[("error class", ("RuntimeError",))])


@pytest.mark.asyncio
async def test_unreadable_summary_json_file_is_store_unreadable_naming_the_path(api, sandbox, helper, stores, check_error) -> None:
    # EC-13 / D-12: a PermissionError on a summary.json is
    # grok.store_unreadable naming the path and the error class.
    folder = stores.grok_thread("locked")
    path = folder / "summary.json"
    size = path.stat().st_size
    if sys.platform == "win32":
        import msvcrt

        handle = path.open("r+b")
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, size)
    else:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("root reads files regardless of their mode")
        path.chmod(0)
    try:
        with pytest.raises(api.NativeThreadError) as caught:
            await helper("list_grok_threads", sandbox.workspace)
    finally:
        if sys.platform == "win32":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, size)
            handle.close()
        else:
            path.chmod(0o644)
    check_error(caught.value, harness="grok", operation="list_grok_threads", code="grok.store_unreadable", workspace=sandbox.workspace, observations=[("error class", ("PermissionError",))])
    assert mentions(str(caught.value), path)
