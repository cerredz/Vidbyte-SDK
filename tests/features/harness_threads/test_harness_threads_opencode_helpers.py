"""FILE: tests/features/harness_threads/test_harness_threads_opencode_helpers.py

PURPOSE: The eight opencode thread helpers against an opencode stand-in that keeps sessions in a SQLite file with opencode's `session` columns: list with `--max-count`, the directory filter, order and window (AC-2, AC-32, INV-7, D-19, EC-28, EC-75), the wrappers (AC-3), get and lineage through one `opencode db` query per id, reaching subagent children that `session list` never shows (AC-4, AC-6, AC-31, D-26, EC-77), read through `export` (AC-5), search (AC-7), delete (AC-8, EC-32), empty and malformed output (AC-19, EC-29, EC-30), and the overlaid PWD (EC-31, D-22).
ROLE IN CODEBASE: Start here when an opencode helper lists the wrong project, misses threads, or starts the wrong child.
ARCHITECTURE NOTE: The stand-in plays opencode 1.18.31 as the spec records it (spec §13): `session list` returns roots only, rows exactly {id, title, updated, created, projectId, directory} with no parent, cut at `--max-count` (default 100), in the project of PWD; `db --format=json <sql>` runs the query for real against the SQLite file; an unknown id makes `export` and `session delete` print `Session not found: <id>`. Rows are seeded by conftest.py `Stores.opencode_session`.
FUNCTION INVENTORY: ms converts a datetime to epoch milliseconds; expect builds the expected field tuple; options_of reads the stand-in's parsed options; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new opencode fact is a stand-in change (fake_harness_helpers.py) first, then a case here.
WHAT NOT TO DO IN THIS FILE: Do not give the stand-in's list rows a parent: opencode lists roots only, so a lineage that relies on list rows must fail here.
KNOWN EDGE CASES: Times are whole seconds so epoch milliseconds convert back exactly. The scan-cap case seeds exactly NATIVE_OPENCODE_SCAN_MAX roots in one transaction.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.2 AC-2 to AC-8, AC-19, AC-31, AC-32, §6.3 EC-28 to EC-32, EC-75 to EC-77, §9.1, §9.2, D-19, D-22, D-24, D-26
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_opencode_helpers.py
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

UNKNOWN = "ses_unknown0000000000000000"


def ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def expect(thread_id: str, created: datetime, updated: datetime, title: str, parent: str | None = None) -> tuple:
    return ("opencode", thread_id, title, created, updated, parent, None)


def whole_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@pytest.mark.asyncio
async def test_list_keeps_the_workspace_rows_newest_first_with_ties_by_id_descending(sandbox, helper, stores, shapes) -> None:
    # AC-2 / INV-7 / D-19 / EC-28 / EC-16 / D-24: rows whose directory
    # equals the workspace, in the window, ordered and cut; model None.
    now = whole_now()
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = {"fresh": 1, "tie-a": 3, "tie-b": 3, "mid": 5, "old": 48}
    for thread_id, hours in rows.items():
        stores.opencode_session(thread_id, title=f"Title {thread_id}", created_ms=ms(created), updated_ms=ms(now - timedelta(hours=hours)))
    stores.opencode_session("elsewhere", directory=sandbox.root / "elsewhere", updated_ms=ms(now - timedelta(hours=2)))
    stores.opencode_session("in-subfolder", directory=sandbox.workspace / "sub", updated_ms=ms(now - timedelta(hours=2)))
    stores.opencode_session("subagent-child", parent="fresh", updated_ms=ms(now - timedelta(minutes=90)))
    listed = await helper("list_opencode_threads", sandbox.workspace, since=timedelta(hours=24), limit=3)
    assert [shapes.summary_fields(summary) for summary in listed] == [
        expect("fresh", created, now - timedelta(hours=1), "Title fresh"), expect("tie-b", created, now - timedelta(hours=3), "Title tie-b"),
        expect("tie-a", created, now - timedelta(hours=3), "Title tie-a"),
    ]
    everything = await helper("list_opencode_threads", sandbox.workspace, limit=200)
    assert [summary.thread_id for summary in everything] == ["fresh", "tie-b", "tie-a", "mid", "old"]
    start = sandbox.starts("opencode-list")[0]
    assert start["argv"][:2] == ["session", "list"] and start["options"] == {"--format": "json", "--max-count": "10000"} and start["stray"] == []
    assert pathlib.Path(start["cwd"]).resolve() == sandbox.workspace and start["plain"]["PWD"] == str(sandbox.workspace)
    assert start["plain"]["OPENCODE_DISABLE_AUTOUPDATE"] == "1" and all(value is None for value in start["credentials"].values())


@pytest.mark.asyncio
async def test_recent_and_since_wrappers_equal_the_base_list(api, sandbox, helper, stores) -> None:
    # AC-3 / INV-7: same store, same answers; default limits 10 and 20.
    now = whole_now()
    for hour in range(1, 26):
        stores.opencode_session(f"ses_{hour:02d}", updated_ms=ms(now - timedelta(hours=hour)))
    ws = sandbox.workspace
    assert len(await helper("list_opencode_threads", ws)) == api.constants.NATIVE_LIST_DEFAULT_LIMIT
    recent = await helper("list_recent_opencode_threads", ws)
    assert len(recent) == api.constants.NATIVE_RECENT_DEFAULT_LIMIT and recent == await helper("list_opencode_threads", ws, limit=10)
    window = timedelta(hours=6, minutes=30)
    assert await helper("list_opencode_threads_since", ws, window) == await helper("list_opencode_threads", ws, since=window)
    assert await helper("list_opencode_threads_since", ws, window, limit=2) == await helper("list_opencode_threads", ws, since=window, limit=2)


@pytest.mark.asyncio
async def test_get_runs_one_db_query_for_the_id_and_maps_its_row(api, sandbox, helper, stores, shapes, check_error) -> None:
    # AC-4 / AC-31 / D-26 / §9.1: exactly one `opencode db
    # --format=json <OPENCODE_SESSION_QUERY>` child; no list, no export;
    # [] is thread_not_found.
    created, updated = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc), datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
    stores.opencode_session("ses_known", title="Known session", created_ms=ms(created), updated_ms=ms(updated))
    found = await helper("get_opencode_thread", "ses_known", sandbox.workspace)
    assert shapes.summary_fields(found) == expect("ses_known", created, updated, "Known session")
    queries = sandbox.records("query", "opencode-db")
    query = "SELECT id, title, time_created, time_updated, parent_id, directory FROM session WHERE id = 'ses_known'"
    assert [record["query"] for record in queries] == [query] == [api.constants.OPENCODE_SESSION_QUERY.format(thread_id="ses_known")]
    start = sandbox.only_start("opencode-db")
    assert start["argv"][0] == "db" and start["options"] == {"--format": "json"} and start["stray"] == [query]
    assert sandbox.starts("opencode-list") == [] and sandbox.starts("opencode-export") == []
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_opencode_thread", UNKNOWN, sandbox.workspace)
    check_error(caught.value, harness="opencode", operation="get_opencode_thread", code="opencode.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN)


@pytest.mark.asyncio
async def test_lineage_follows_parent_id_through_subagent_children_lists_never_show(api, sandbox, helper, stores, check_error) -> None:
    # AC-6 / AC-31 / EC-77 / D-26: root <- child <- grandchild, the
    # children absent from `session list`; one db child per step,
    # database-wide (the grandchild ran in another folder); a missing
    # parent ends the chain; a cycle is protocol_mismatch.
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    stores.opencode_session("ses_root", title="Root", created_ms=ms(when), updated_ms=ms(when))
    stores.opencode_session("ses_child", title="Child", parent="ses_root", created_ms=ms(when), updated_ms=ms(when + timedelta(hours=1)))
    stores.opencode_session("ses_grandchild", title="Grandchild", parent="ses_child", directory=sandbox.root / "subagent-dir", created_ms=ms(when), updated_ms=ms(when + timedelta(hours=2)))
    assert [summary.thread_id for summary in await helper("list_opencode_threads", sandbox.workspace)] == ["ses_root"], "roots only"
    chain = await helper("get_opencode_thread_lineage", "ses_grandchild", sandbox.workspace)
    assert [(summary.thread_id, summary.parent_thread_id) for summary in chain] == [("ses_root", None), ("ses_child", "ses_root"), ("ses_grandchild", "ses_child")]
    assert len(sandbox.starts("opencode-db")) == 3 and len(sandbox.starts("opencode-list")) == 1 and sandbox.starts("opencode-export") == []
    assert (await helper("get_opencode_thread", "ses_child", sandbox.workspace)).parent_thread_id == "ses_root"
    stores.opencode_session("ses_orphan", parent="ses_gone")
    assert [(summary.thread_id, summary.parent_thread_id) for summary in await helper("get_opencode_thread_lineage", "ses_orphan", sandbox.workspace)] == [("ses_orphan", "ses_gone")]
    stores.opencode_session("ses_loop_a", parent="ses_loop_b")
    stores.opencode_session("ses_loop_b", parent="ses_loop_a")
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_opencode_thread_lineage", "ses_loop_a", sandbox.workspace)
    check_error(caught.value, harness="opencode", operation="get_opencode_thread_lineage", code="opencode.protocol_mismatch", workspace=sandbox.workspace, thread_id="ses_loop_a", observations=[("repeated id", ("ses_loop_a", "ses_loop_b"))])


@pytest.mark.asyncio
async def test_read_returns_the_export_document_whole(api, sandbox, helper, stores, check_error) -> None:
    # AC-5 / INV-21 / EC-32: `opencode export <id>` stdout, whole; an
    # unknown id (stderr `Session not found: <id>`) is thread_not_found.
    document = json.dumps({"info": {"id": "ses_doc", "title": "Doc"}, "messages": [{"parts": [{"type": "text", "text": "héllo\r\nwörld"}]}]}, ensure_ascii=False).encode("utf-8")
    stores.opencode_session("ses_doc", title="Doc", export=document)
    result = await helper("read_opencode_thread", "ses_doc", sandbox.workspace)
    assert isinstance(result, api.NativeThreadResult)
    assert (result.harness, result.thread_id, result.text, result.text_truncated) == (api.enums.NativeHarness.OPENCODE, "ses_doc", document.decode("utf-8"), False)
    start = sandbox.only_start("opencode-export")
    assert start["argv"] == ["export", "ses_doc"] and pathlib.Path(start["cwd"]).resolve() == sandbox.workspace and start["plain"]["PWD"] == str(sandbox.workspace)
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("read_opencode_thread", UNKNOWN, sandbox.workspace)
    check_error(caught.value, harness="opencode", operation="read_opencode_thread", code="opencode.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN)


@pytest.mark.asyncio
async def test_search_matches_titles_literally_and_case_insensitively(sandbox, helper, stores) -> None:
    # AC-7 / D-3 / EC-7: the title is the only searchable text a list
    # row carries.
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    stores.opencode_session("ses_upper", title="REVIEW [auth] (v2)", updated_ms=ms(when + timedelta(hours=3)))
    stores.opencode_session("ses_lower", title="review [AUTH] (v2) again", updated_ms=ms(when + timedelta(hours=2)))
    stores.opencode_session("ses_regex", title="review a (v2)", updated_ms=ms(when + timedelta(hours=4)))
    found = await helper("search_opencode_threads", sandbox.workspace, "Review [Auth] (V2)")
    assert [summary.thread_id for summary in found] == ["ses_upper", "ses_lower"]


@pytest.mark.asyncio
async def test_delete_runs_session_delete_and_the_thread_no_longer_lists(api, sandbox, helper, stores, check_error) -> None:
    # AC-8 / INV-11 / EC-32: exit 0 without the marker -> None; an
    # unknown id is thread_not_found.
    stores.opencode_session("ses_doomed")
    stores.opencode_session("ses_kept")
    assert await helper("delete_opencode_thread", "ses_doomed", sandbox.workspace) is None
    assert sandbox.only_start("opencode-delete")["argv"] == ["session", "delete", "ses_doomed"]
    assert [summary.thread_id for summary in await helper("list_opencode_threads", sandbox.workspace)] == ["ses_kept"]
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("delete_opencode_thread", "ses_doomed", sandbox.workspace)
    check_error(caught.value, harness="opencode", operation="delete_opencode_thread", code="opencode.thread_not_found", workspace=sandbox.workspace, thread_id="ses_doomed")


@pytest.mark.asyncio
async def test_list_asks_for_the_scan_cap_and_refuses_a_list_cut_at_it(api, sandbox, helper, stores, check_error) -> None:
    # AC-32 / EC-75 / D-19: without --max-count opencode stops at 100
    # rows; with it 300 roots give limit=150 threads; exactly
    # NATIVE_OPENCODE_SCAN_MAX roots may be a cut list and raise.
    cap = api.constants.NATIVE_OPENCODE_SCAN_MAX
    base = ms(datetime(2026, 1, 1, tzinfo=timezone.utc))
    ws = str(sandbox.workspace)
    stores.opencode_many((f"ses_{index:05d}", "global", None, ws, f"Session {index}", base, base + index * 1000) for index in range(300))
    listed = await helper("list_opencode_threads", sandbox.workspace, limit=150)
    assert len(listed) == 150 and listed[0].thread_id == "ses_00299" and listed[-1].thread_id == "ses_00150"
    assert sandbox.starts("opencode-list")[0]["options"]["--max-count"] == str(cap)
    stores.opencode_many((f"ses_x{index:05d}", "global", None, ws, "More", base, base + index) for index in range(cap - 300))
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("list_opencode_threads", sandbox.workspace, limit=10)
    check_error(caught.value, harness="opencode", operation="list_opencode_threads", code="opencode.protocol_mismatch", workspace=sandbox.workspace, observations=[("scan cap", (str(cap), f"{cap:,}", "NATIVE_OPENCODE_SCAN_MAX"))])


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", ["blank", "brackets"])
async def test_an_empty_session_list_is_no_threads(sandbox, helper, empty) -> None:
    # EC-29 / A-12: nothing, or [], is ().
    assert await helper("list_opencode_threads", sandbox.workspace, fake={"empty_list": empty}) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "text", "member"), [
    ("updated-as-text", [{"id": "ses_a", "title": "A", "updated": "2026-10-15", "created": 1760000000000, "projectId": "global", "directory": "{ws}"}], "updated"),
    ("missing-id", [{"title": "A", "updated": 1760000000000, "created": 1760000000000, "projectId": "global", "directory": "{ws}"}], "id"),
    ("created-as-bool", [{"id": "ses_a", "title": "A", "updated": 1760000000000, "created": True, "projectId": "global", "directory": "{ws}"}], "created"),
    ("not-a-list", {"id": "ses_a"}, None),
    ("not-json", "opencode: loading plugins\nno sessions table yet\n", None),
])
async def test_malformed_list_output_is_protocol_mismatch_naming_the_member(api, sandbox, helper, check_error, case, text, member) -> None:
    # AC-19 / EC-30 / INV-6: never a partial list; the member is named.
    raw = text if isinstance(text, str) else json.dumps(text).replace("{ws}", str(sandbox.workspace).replace("\\", "\\\\"))
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("list_opencode_threads", sandbox.workspace, fake={"list_text": raw})
    check_error(caught.value, harness="opencode", operation="list_opencode_threads", code="opencode.protocol_mismatch", workspace=sandbox.workspace, observations=[("member", (member,))] if member else ())


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "rows"), [
    ("two-rows", [{"id": "ses_a", "title": "A", "time_created": 1, "time_updated": 2, "parent_id": None, "directory": "/w"}] * 2),
    ("time-as-text", [{"id": "ses_a", "title": "A", "time_created": "yesterday", "time_updated": 2, "parent_id": None, "directory": "/w"}]),
    ("parent-is-self", [{"id": "ses_a", "title": "A", "time_created": 1, "time_updated": 2, "parent_id": "ses_a", "directory": "/w"}]),
])
async def test_unusable_db_rows_are_protocol_mismatch(api, sandbox, helper, check_error, case, rows) -> None:
    # D-26 / INV-6: more than one row for an exact id, or a bad member,
    # is protocol_mismatch.
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_opencode_thread", "ses_a", sandbox.workspace, fake={"db_text": json.dumps(rows)})
    check_error(caught.value, harness="opencode", operation="get_opencode_thread", code="opencode.protocol_mismatch", workspace=sandbox.workspace, thread_id="ses_a")


@pytest.mark.asyncio
async def test_an_inherited_pwd_never_chooses_the_project(sandbox, helper, stores, monkeypatch) -> None:
    # EC-31 / D-22: cwd and PWD are the workspace, so the caller's own
    # PWD (another project) cannot pick the listed sessions.
    elsewhere = sandbox.root / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("PWD", str(elsewhere))
    stores.opencode_session("ses_mine", project="proj-ws")
    stores.opencode_session("ses_theirs", project="proj-else", directory=elsewhere)
    projects = {str(sandbox.workspace): "proj-ws", str(elsewhere): "proj-else"}
    listed = await helper("list_opencode_threads", sandbox.workspace, fake={"projects": projects})
    assert [summary.thread_id for summary in listed] == ["ses_mine"]
    start = sandbox.only_start("opencode-list")
    assert start["plain"]["PWD"] == str(sandbox.workspace) and pathlib.Path(start["cwd"]).resolve() == sandbox.workspace
