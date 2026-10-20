"""FILE: tests/features/harness_threads/test_harness_threads_muse_helpers.py

PURPOSE: The six Muse thread helpers and init_muse_workspace against a muse stand-in that answers batch `muse serve` frames from MSP Session records: list through `session/list` with the workspace root, limit and window (AC-2, INV-7), the wrappers (AC-3), get and lineage through `session/read {excludeItems: true}`, one serve per step, with `forkedFrom` as an object (AC-4, AC-6, EC-35, EC-65), read through `muse export` run in an empty SDK temp folder (AC-5, D-17, EC-38 to EC-40), the `-32601` and other JSON-RPC errors (EC-36), unusable Session shapes (AC-19), the private config of every helper child (INV-23), and `muse init` (AC-18, EC-58, EC-59).
ROLE IN CODEBASE: Start here when a Muse helper lists the wrong sessions, reads the wrong file, or leaks a login into a helper child.
ARCHITECTURE NOTE: The stand-in keeps one MSP Session per thread in its state folder (conftest.py `Stores.muse_session`); `session/list` filters by `workspaceRoot` and `updatedAfter` and returns ties in ascending `sessionId` order, the reverse of INV-7, so a helper that keeps Muse's order fails here. Every frame the SDK sends is logged, so the tests read the exact `session/list` and `session/read` params. On win32 the helpers run native (config.muse_command set); WSL mode is covered in test_harness_threads_helper_bounds.py.
FUNCTION INVENTORY: stamp_z writes Muse's RFC 3339 `Z` form; expect builds the expected field tuple; requests lists the logged JSON-RPC requests of one method; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new Muse fact is a stand-in change (fake_harness_helpers.py) first, then a case here.
WHAT NOT TO DO IN THIS FILE: Do not model `forkedFrom` as a string: MSP sends an object, and the spec reads `forkedFrom.sessionId` (spec §13).
KNOWN EDGE CASES: Times inside a window sit whole hours from its edge, because the helper reads the clock itself. The oversize export is made with truncate, so it costs no write time.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-7, INV-10, INV-23, §6.2 AC-2 to AC-6, AC-18, AC-19, §6.3 EC-35 to EC-40, EC-58, EC-59, EC-65, §9.1, §9.2, D-17
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_muse_helpers.py
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone

import pytest

UNKNOWN = "0192f0c4-dead-7000-8000-000000000404"
EXPORT_BYTES = "{\r\n  \"session\": \"café ☕\",\r\n  \"items\": []\r\n}\r\n".encode("utf-8")
INIT_PLAN = ".muse/config.toml\n.muse/skills/\n"


def stamp_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def expect(thread_id: str, created: datetime, updated: datetime, *, parent: str | None = None, model: str | None = "muse-coder-1") -> tuple:
    return ("muse", thread_id, None, created, updated, parent, model)


def requests(sandbox, method: str) -> list[dict]:
    return [record["frame"] for record in sandbox.records("frame", "muse-serve") if record["frame"].get("method") == method]


def whole_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@pytest.mark.asyncio
async def test_list_sends_session_list_for_the_workspace_and_reorders_ties(api, sandbox, helper, stores, shapes) -> None:
    # AC-2 / INV-7 / §9.1 / §9.2: one serve batch with session/list
    # {workspaceRoot, limit, updatedAfter}; ties come back from Muse in
    # ascending id order and must leave the SDK id-descending.
    now = whole_now()
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for thread_id, hours in {"muse-fresh": 1, "muse-tie-a": 3, "muse-tie-b": 3, "muse-mid": 5, "muse-old": 48}.items():
        stores.muse_session(thread_id, created=created, updated=stamp_z(now - timedelta(hours=hours)))
    stores.muse_session("muse-forked", created=created, updated=now - timedelta(hours=7), forked_from="muse-mid")
    stores.muse_session("muse-elsewhere", workspace_root=str(sandbox.root / "elsewhere"), updated=now - timedelta(hours=2))
    listed = await helper("list_muse_threads", sandbox.workspace, since=timedelta(hours=24), limit=3)
    assert [shapes.summary_fields(summary) for summary in listed] == [
        expect("muse-fresh", created, now - timedelta(hours=1)), expect("muse-tie-b", created, now - timedelta(hours=3)), expect("muse-tie-a", created, now - timedelta(hours=3)),
    ]
    frame = requests(sandbox, "session/list")[0]
    params = frame["params"]
    assert set(params) == {"workspaceRoot", "limit", "updatedAfter"} and params["workspaceRoot"] == str(sandbox.workspace)
    assert isinstance(params["limit"], int) and 3 <= params["limit"] <= api.constants.NATIVE_LIST_MAX_LIMIT
    after = datetime.fromisoformat(params["updatedAfter"].replace("Z", "+00:00"))
    assert after.tzinfo is not None and abs(after - (now - timedelta(hours=24))) < timedelta(minutes=10)
    everything = await helper("list_muse_threads", sandbox.workspace, limit=200)
    assert [summary.thread_id for summary in everything] == ["muse-fresh", "muse-tie-b", "muse-tie-a", "muse-mid", "muse-forked", "muse-old"]
    assert everything[4].parent_thread_id == "muse-mid"
    assert "updatedAfter" not in requests(sandbox, "session/list")[1]["params"], "no window, no updatedAfter"
    assert len(sandbox.starts("muse-serve")) == 2 and sandbox.starts("muse-exec") == [] and sandbox.starts("muse-export") == []


@pytest.mark.asyncio
async def test_recent_and_since_wrappers_equal_the_base_list(api, sandbox, helper, stores) -> None:
    # AC-3 / INV-7: same store, same answers; default limits 10 and 20.
    now = whole_now()
    for hour in range(1, 26):
        stores.muse_session(f"muse-{hour:02d}", updated=now - timedelta(hours=hour))
    ws = sandbox.workspace
    assert len(await helper("list_muse_threads", ws)) == api.constants.NATIVE_LIST_DEFAULT_LIMIT
    recent = await helper("list_recent_muse_threads", ws)
    assert len(recent) == api.constants.NATIVE_RECENT_DEFAULT_LIMIT and recent == await helper("list_muse_threads", ws, limit=10)
    window = timedelta(hours=6, minutes=30)
    assert await helper("list_muse_threads_since", ws, window) == await helper("list_muse_threads", ws, since=window)
    assert [summary.thread_id for summary in await helper("list_muse_threads_since", ws, window, limit=2)] == ["muse-01", "muse-02"]


@pytest.mark.asyncio
async def test_no_sessions_is_an_empty_tuple(sandbox, helper) -> None:
    # AC-2: an empty store lists ().
    assert await helper("list_muse_threads", sandbox.workspace) == ()


@pytest.mark.asyncio
async def test_get_reads_one_session_without_items_and_unknown_is_thread_not_found(api, sandbox, helper, stores, shapes, check_error) -> None:
    # AC-4 / EC-35 / §9.2: session/read {sessionId, excludeItems: true};
    # -32020 is thread_not_found and no export starts.
    created, updated = datetime(2026, 9, 1, 8, tzinfo=timezone.utc), datetime(2026, 9, 2, 9, 30, tzinfo=timezone.utc)
    stores.muse_session("muse-known", created=stamp_z(created), updated=stamp_z(updated), forked_from="muse-source", model="muse-coder-2")
    found = await helper("get_muse_thread", "muse-known", sandbox.workspace)
    assert shapes.summary_fields(found) == expect("muse-known", created, updated, parent="muse-source", model="muse-coder-2")
    assert [frame["params"] for frame in requests(sandbox, "session/read")] == [{"sessionId": "muse-known", "excludeItems": True}]
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_muse_thread", UNKNOWN, sandbox.workspace)
    check_error(caught.value, harness="muse", operation="get_muse_thread", code="muse.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN)
    assert sandbox.starts("muse-export") == [] and sandbox.starts("muse-exec") == []


@pytest.mark.asyncio
async def test_lineage_follows_forked_from_objects_one_serve_per_step(api, sandbox, helper, stores, check_error) -> None:
    # AC-6 / INV-10 / EC-65: root <- fork <- fork-of-fork; a parent that
    # session/read cannot find ends the chain; a cycle is
    # protocol_mismatch.
    stores.muse_session("muse-root")
    stores.muse_session("muse-fork", forked_from="muse-root")
    stores.muse_session("muse-fork2", forked_from="muse-fork")
    chain = await helper("get_muse_thread_lineage", "muse-fork2", sandbox.workspace)
    assert [(summary.thread_id, summary.parent_thread_id) for summary in chain] == [("muse-root", None), ("muse-fork", "muse-root"), ("muse-fork2", "muse-fork")]
    assert len(sandbox.starts("muse-serve")) == 3
    stores.muse_session("muse-orphan", forked_from="muse-gone")
    assert [(summary.thread_id, summary.parent_thread_id) for summary in await helper("get_muse_thread_lineage", "muse-orphan", sandbox.workspace)] == [("muse-orphan", "muse-gone")]
    stores.muse_session("muse-loop-a", forked_from="muse-loop-b")
    stores.muse_session("muse-loop-b", forked_from="muse-loop-a")
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_muse_thread_lineage", "muse-loop-a", sandbox.workspace)
    check_error(caught.value, harness="muse", operation="get_muse_thread_lineage", code="muse.protocol_mismatch", workspace=sandbox.workspace, thread_id="muse-loop-a", observations=[("repeated id", ("muse-loop-a", "muse-loop-b"))])


@pytest.mark.asyncio
async def test_read_exports_into_an_empty_temp_folder_and_returns_the_file_whole(api, sandbox, helper, stores, monkeypatch) -> None:
    # AC-5 / D-17 / EC-40 / INV-21 / INV-23: a session/read check, then
    # `muse export --session <id> --out <tmp>/export/thread.json` with
    # cwd that empty folder; a file named like the id in the caller's
    # folder and the workspace is never read; the bytes come back whole
    # as UTF-8 text; the folder is gone afterwards.
    stores.muse_session("muse-doc", export=EXPORT_BYTES)
    (sandbox.workspace / "muse-doc").write_text("DECOY", encoding="utf-8")
    monkeypatch.chdir(sandbox.workspace)
    result = await helper("read_muse_thread", "muse-doc", sandbox.workspace)
    assert (result.harness.value, result.thread_id, result.text, result.text_truncated) == ("muse", "muse-doc", EXPORT_BYTES.decode("utf-8"), False)
    assert isinstance(result, api.NativeThreadResult)
    assert [frame["params"]["sessionId"] for frame in requests(sandbox, "session/read")] == ["muse-doc"]
    start = sandbox.only_start("muse-export")
    out = pathlib.Path(start["options"]["--out"])
    assert start["options"]["--session"] == "muse-doc" and out.parts[-2:] == tuple(api.constants.MUSE_EXPORT_PARTS)
    assert pathlib.Path(start["cwd"]).resolve() == out.parent.resolve() and start["cwd_entries"] == [], "EC-40: export runs in an empty folder"
    assert out.resolve().is_relative_to(sandbox.tmp) and all(value is None for value in start["credentials"].values())
    assert sandbox.records("exported", "muse-export")[0]["decoy"] is False
    assert list(sandbox.tmp.iterdir()) == [], "INV-12: the SDK temp folder is removed"


@pytest.mark.asyncio
async def test_read_of_an_unknown_id_starts_no_export(api, sandbox, helper, check_error) -> None:
    # EC-35: the session/read check fails first.
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("read_muse_thread", UNKNOWN, sandbox.workspace)
    check_error(caught.value, harness="muse", operation="read_muse_thread", code="muse.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN)
    assert sandbox.starts("muse-export") == [] and list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("fake", "code", "observation"), [
    ({"export_mode": "fail", "vendor_text": "Error: export failed: the session file is locked"}, "muse.run_failed", ("vendor text", ("Error: export failed: the session file is locked",))),
    ({"export_mode": "no_file"}, "muse.protocol_mismatch", ("missing file", ("thread.json",))),
    ({"export_mode": "oversize"}, "muse.output_too_large", ("byte cap", ())),
], ids=["export-fails", "no-file", "oversize"])
async def test_export_failures_raise_and_remove_the_temp_folder(api, sandbox, helper, stores, check_error, fake, code, observation) -> None:
    # EC-38 / EC-39 / INV-21: a failed export, a missing file, or a file
    # over NATIVE_PROCESS_MAX_OUTPUT_BYTES (sized with fstat, never
    # returned cut).
    cap = api.constants.NATIVE_PROCESS_MAX_OUTPUT_BYTES
    if fake.get("export_mode") == "oversize":
        fake = {**fake, "oversize_bytes": cap + 1}
        observation = ("byte cap", (str(cap), f"{cap:,}"))
    stores.muse_session("muse-doc")
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("read_muse_thread", "muse-doc", sandbox.workspace, fake=fake)
    check_error(caught.value, harness="muse", operation="read_muse_thread", code=code, workspace=sandbox.workspace, thread_id="muse-doc", observations=[observation])
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("fake", "code", "observation"), [
    ({"serve_mode": "no_list"}, "muse.protocol_mismatch", ("method", ("session/list",))),
    ({"serve_mode": "other_error"}, "muse.run_failed", ("vendor text", ("the session store is locked by another process",))),
], ids=["method-not-found", "other-error"])
async def test_json_rpc_errors_of_session_list(api, sandbox, helper, check_error, fake, code, observation) -> None:
    # EC-36 / §9.2: -32601 is a version mismatch naming session/list;
    # any other JSON-RPC error is run_failed.
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("list_muse_threads", sandbox.workspace, fake=fake)
    check_error(caught.value, harness="muse", operation="list_muse_threads", code=code, workspace=sandbox.workspace, observations=[observation])


def session(**fields) -> dict:
    base = {"sessionId": "muse-shape", "createdAt": "2026-03-01T12:00:00Z", "updatedAt": "2026-03-01T12:00:00Z", "forkedFrom": None, "modelId": "muse-coder-1", "workspaceRoot": "", "status": "notLoaded"}
    base.update(fields)
    return {key: value for key, value in base.items() if value != "<absent>"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("result", "members"), [
    ({"sessions": [session(updatedAt="<absent>")]}, ("updatedAt", "updated_at")),
    ({"sessions": [session(createdAt="2026-03-01T12:00:00")]}, ("createdAt", "created_at")),
    ({"sessions": [session(updatedAt="yesterday")]}, ("updatedAt", "updated_at")),
    ({"sessions": [session(forkedFrom="muse-parent")]}, ("forkedFrom", "parent_thread_id")),
    ({"sessions": [session(modelId=7)]}, ("modelId", "model")),
    ({"sessions": [session(sessionId="../escape")]}, ("sessionId", "thread_id")),
    ({"items": []}, ("sessions",)),
], ids=["no-updated", "naive-created", "garbled-updated", "forked-from-string", "model-int", "bad-id", "no-sessions"])
async def test_unusable_session_shapes_are_protocol_mismatch_never_a_partial_list(api, sandbox, helper, check_error, result, members) -> None:
    # AC-19 / INV-6: one bad Session fails the whole list, naming the
    # member (the MSP name or the record field it maps to).
    good = session(sessionId="muse-good")
    if "sessions" in result:
        result = {"sessions": [good, *result["sessions"]], "nextCursor": None}
    for row in result.get("sessions", []):
        row["workspaceRoot"] = str(sandbox.workspace)
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("list_muse_threads", sandbox.workspace, fake={"list_result": result})
    check_error(caught.value, harness="muse", operation="list_muse_threads", code="muse.protocol_mismatch", workspace=sandbox.workspace, observations=[("member", members)])


@pytest.mark.asyncio
async def test_get_with_a_garbled_session_is_protocol_mismatch(api, sandbox, helper, stores, check_error) -> None:
    # AC-19: the same rule for session/read.
    stores.muse_session("muse-known")
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_muse_thread", "muse-known", sandbox.workspace, fake={"session_fields": {"createdAt": 1767225600000}})
    check_error(caught.value, harness="muse", operation="get_muse_thread", code="muse.protocol_mismatch", workspace=sandbox.workspace, thread_id="muse-known", observations=[("member", ("createdAt", "created_at"))])


@pytest.mark.asyncio
async def test_every_helper_child_gets_a_fresh_private_config_and_no_login(api, sandbox, helper, stores, monkeypatch) -> None:
    # INV-23 / INV-2 / EC-60: XDG_CONFIG_HOME is a new SDK temp folder,
    # MUSE_AUTH_PATH a file in it that does not exist, META_API_KEY is
    # gone even when the caller has one, and the folder is removed.
    saved_auth = sandbox.home / "saved-auth.json"
    saved_auth.write_text("{\"token\": \"stored-login\"}", encoding="utf-8")
    monkeypatch.setenv("META_API_KEY", "meta-env-caller-key")
    monkeypatch.setenv("MUSE_AUTH_PATH", str(saved_auth))
    stores.muse_session("muse-doc", export=EXPORT_BYTES)
    await helper("list_muse_threads", sandbox.workspace)
    await helper("get_muse_thread", "muse-doc", sandbox.workspace)
    await helper("read_muse_thread", "muse-doc", sandbox.workspace)
    await helper("init_muse_workspace", sandbox.workspace, dry_run=True)
    starts = sandbox.starts("muse-serve") + sandbox.starts("muse-export") + sandbox.starts("muse-init")
    assert len(starts) == 5
    homes = set()
    for start in starts:
        config_home = pathlib.Path(start["plain"]["XDG_CONFIG_HOME"])
        assert start["xdg_config_exists"] is True and config_home.resolve().is_relative_to(sandbox.tmp)
        assert pathlib.Path(start["plain"]["MUSE_AUTH_PATH"]) == config_home / "muse" / "auth.json" and start["muse_auth_file_exists"] is False
        assert all(value is None for value in start["credentials"].values()) and "META_API_KEY" not in (start["plain"]["WSLENV"] or "")
        assert start["plain"]["MUSE_NO_AUTO_UPDATE"] == "1"
        homes.add(config_home)
    assert len(homes) >= 4, "no two calls share a private config folder"
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
async def test_init_runs_muse_init_in_the_workspace_and_returns_its_stdout(api, sandbox, helper) -> None:
    # AC-18 / EC-59: `muse init` in ws with no key returns
    # NativeCommandOutput(MUSE, stdout); --dry-run writes nothing.
    before = sandbox.snapshot()
    planned = await helper("init_muse_workspace", sandbox.workspace, dry_run=True)
    assert planned == api.native.NativeCommandOutput(harness=api.enums.NativeHarness.MUSE, text="Would create:\n" + INIT_PLAN)
    assert sandbox.snapshot() == before, "EC-59: a dry run writes nothing"
    created = await helper("init_muse_workspace", sandbox.workspace)
    assert created == api.native.NativeCommandOutput(harness=api.enums.NativeHarness.MUSE, text="Created:\n" + INIT_PLAN)
    assert (sandbox.workspace / ".muse" / "config.toml").is_file()
    dry, real = sandbox.starts("muse-init")
    assert dry["argv"] == ["init", "--dry-run"] and real["argv"] == ["init"]
    for start in (dry, real):
        assert pathlib.Path(start["cwd"]).resolve() == sandbox.workspace and all(value is None for value in start["credentials"].values())
    assert sandbox.starts("muse-exec") == [] and sandbox.starts("muse-serve") == []


@pytest.mark.asyncio
async def test_init_where_muse_is_already_set_up_is_run_failed_with_muses_text(api, sandbox, helper, check_error) -> None:
    # EC-58: Muse refuses (no --force is exposed); its text is kept.
    (sandbox.workspace / ".muse").mkdir()
    (sandbox.workspace / ".muse" / "config.toml").write_text("[workspace]\n", encoding="utf-8")
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("init_muse_workspace", sandbox.workspace)
    check_error(caught.value, harness="muse", operation="init_muse_workspace", code="muse.run_failed", workspace=sandbox.workspace, thread_id=None, vendor="Muse is already initialized here", exit_code=1)
    assert (sandbox.workspace / ".muse" / "config.toml").read_text(encoding="utf-8") == "[workspace]\n"
