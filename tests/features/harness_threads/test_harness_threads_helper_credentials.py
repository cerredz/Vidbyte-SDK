"""FILE: tests/features/harness_threads/test_harness_threads_helper_credentials.py

PURPOSE: Where keys can and cannot go in the new functions: every helper child runs without the caller's XAI_API_KEY, GROK_CODE_XAI_API_KEY, META_API_KEY and OPENCODE_CONFIG_CONTENT, with self-update off (AC-10, INV-2, INV-17, EC-60); the read helpers write nothing in the workspace, `~/.vidbyte` or `~/.grok` and leave no temp folder (AC-11, INV-4, INV-12, EC-18); and a skill run whose vendor echoes its key everywhere leaves that key in no argv element, no file the SDK wrote, and no error text or attribute, on failure and on success (AC-24, INV-24).
ROLE IN CODEBASE: Start here when a key leaks into a helper child, an argv, a file or an error, or when a read helper leaves something behind.
ARCHITECTURE NOTE: The stand-in logs only a digest and length of each credential variable, never its value, so these tests can assert absence and identity without the logs holding a key. The `echo_secrets` mode prints the sentinel key, the argv and the credential variables as one vendor error text, with copies of the key straddling the vendor-text cap.
FUNCTION INVENTORY: seed_all fills a store per harness; texts_of collects every text attribute of an error; files_with lists sandbox files outside the stand-in's folder that hold a byte string; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new helper child is one more call in the AC-10 test.
WHAT NOT TO DO IN THIS FILE: Do not put the sentinel key in a fixture file: the scan for it must find only what the SDK or the vendor wrote.
KNOWN EDGE CASES: The stand-in's own folder holds the scenario that tells it the sentinel (it plays a vendor that knows the key), so the file scan leaves that folder out.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-2, INV-4, INV-12, INV-17, INV-24, §6.2 AC-10, AC-11, AC-24, §6.3 EC-1, EC-18, EC-60, §10
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_helper_credentials.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

SENTINEL = "vbk-sentinel-AC24-7f3e9c1d2b4a6e80"
CALLER_KEYS = {"XAI_API_KEY": "xai-caller-own-key", "GROK_CODE_XAI_API_KEY": "xai-caller-alias-key", "META_API_KEY": "meta-caller-own-key", "OPENCODE_CONFIG_CONTENT": "{\"provider\": {\"deepseek\": {\"options\": {\"apiKey\": \"sk-caller-own-key\"}}}}"}
GROK_ID = "f0000000-0000-4000-8000-0000000000a1"
SKILL_RUNS = {
    "grok": ("run_grok_goal", ("Ship the release",)),
    "opencode": ("run_opencode_review", ("src/",)),
    "muse": ("run_muse_plan", ("Plan the rewrite",)),
}


def seed_all(sandbox, stores) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stores.grok_thread(GROK_ID, updated=now - timedelta(hours=1), transcript=b"# Grok session\n")
    stores.grok_thread("f0000000-0000-4000-8000-0000000000b2", home=stores.user_grok, updated=now - timedelta(hours=2))
    stores.opencode_session("ses_alpha", updated_ms=int((now - timedelta(hours=1)).timestamp() * 1000), export=b"{\"info\": {}}")
    stores.muse_session("muse-alpha", updated=now - timedelta(hours=1), export=b"{\"session\": {}}")


def texts_of(error) -> list[str]:
    texts = [str(error), repr(error)]
    for name in dir(error):
        if name.startswith("__"):
            continue
        try:
            value = getattr(error, name)
        except Exception:
            continue
        if not callable(value):
            texts.append(repr(value))
    return texts


def files_with(sandbox, needle: bytes) -> list[str]:
    found = []
    for path in sandbox.root.rglob("*"):
        relative = path.relative_to(sandbox.root).as_posix()
        if relative.split("/", 1)[0] == "fake" or not path.is_file():
            continue
        if needle in path.read_bytes():
            found.append(relative)
    return found


@pytest.mark.asyncio
async def test_helper_children_carry_no_key_even_when_the_caller_has_one(api, sandbox, helper, stores, monkeypatch) -> None:
    # AC-10 / INV-2 / INV-17 / EC-60: every helper child, of every kind.
    for name, value in CALLER_KEYS.items():
        monkeypatch.setenv(name, value)
    seed_all(sandbox, stores)
    ws = sandbox.workspace
    await helper("read_grok_thread", GROK_ID, ws)
    await helper("list_opencode_threads", ws)
    await helper("get_opencode_thread", "ses_alpha", ws)
    await helper("read_opencode_thread", "ses_alpha", ws)
    await helper("list_muse_threads", ws)
    await helper("read_muse_thread", "muse-alpha", ws)
    await helper("init_muse_workspace", ws, dry_run=True)
    await helper("delete_opencode_thread", "ses_alpha", ws)
    await helper("delete_grok_thread", GROK_ID, ws)
    roles = {start["role"] for start in sandbox.starts()}
    assert roles == {"grok-export", "grok-delete", "opencode-list", "opencode-db", "opencode-export", "opencode-delete", "muse-serve", "muse-export", "muse-init"}
    switches = {"grok": "GROK_DISABLE_AUTOUPDATER", "opencode": "OPENCODE_DISABLE_AUTOUPDATE", "muse": "MUSE_NO_AUTO_UPDATE"}
    for start in sandbox.starts():
        leaked = {name for name in CALLER_KEYS if start["credentials"].get(name) is not None}
        assert not leaked, f"INV-2: {start['role']} got {sorted(leaked)}"
        assert start["plain"][switches[start["role"].split("-")[0]]] == "1", f"INV-17: {start['role']} has self-update on"


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode", "muse"])
async def test_read_helpers_write_nothing_and_leave_no_temp_folder(api, sandbox, helper, stores, harness) -> None:
    # AC-11 / INV-4 / INV-12: the snapshot (workspace, home with
    # ~/.vidbyte and ~/.grok, temp) is unchanged after every read helper.
    seed_all(sandbox, stores)
    ws = sandbox.workspace
    thread = {"grok": GROK_ID, "opencode": "ses_alpha", "muse": "muse-alpha"}[harness]
    calls = [
        (f"list_{harness}_threads", (ws,), {}), (f"list_recent_{harness}_threads", (ws,), {}), (f"list_{harness}_threads_since", (ws, timedelta(days=2)), {}),
        (f"get_{harness}_thread", (thread, ws), {}), (f"read_{harness}_thread", (thread, ws), {}), (f"get_{harness}_thread_lineage", (thread, ws), {}),
    ]
    if harness != "muse":
        calls.append((f"search_{harness}_threads", (ws, "title"), {}))
    if harness == "grok":
        calls.append(("list_grok_threads", (ws,), {"scope": api.native.GrokThreadScope.USER}))
    before = sandbox.snapshot()
    for name, positional, keywords in calls:
        await helper(name, *positional, **keywords)
        assert sandbox.snapshot() == before, f"INV-4: {name} changed the sandbox"
    assert list(sandbox.tmp.iterdir()) == []


@pytest.mark.asyncio
async def test_user_scope_without_a_grok_store_lists_nothing_and_creates_nothing(api, sandbox, helper) -> None:
    # EC-18 / INV-4: no ~/.grok/sessions is (), and ~/.grok is not made.
    before = sandbox.snapshot(include_fake=True)
    assert await helper("list_grok_threads", sandbox.workspace, scope=api.native.GrokThreadScope.USER) == ()
    assert await helper("search_grok_threads", sandbox.workspace, "anything", scope=api.native.GrokThreadScope.USER) == ()
    assert sandbox.snapshot(include_fake=True) == before and not (sandbox.home / ".grok").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode", "muse"])
async def test_an_echoed_key_reaches_no_error_text_argv_or_file_when_the_run_fails(api, sandbox, skill, harness) -> None:
    # AC-24 / INV-24: the vendor prints the key (and argv and env) as its
    # error; the SDK scrubs it everywhere it reports.
    name, positional = SKILL_RUNS[harness]
    with pytest.raises(api.NativeThreadError) as caught:
        await skill(name, *positional, api_key=SENTINEL, fake={"mode": "echo_secrets", "echo_key": SENTINEL})
    for text in texts_of(caught.value):
        assert SENTINEL not in text, f"INV-24: the key is in an error text or attribute: {text[:200]!r}"
    assert sandbox.starts(), "the stand-in must have run"
    assert all(SENTINEL not in element for start in sandbox.starts() for element in start["argv"])
    assert files_with(sandbox, SENTINEL.encode("utf-8")) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode", "muse"])
async def test_a_successful_skill_run_puts_the_key_in_no_argv_and_no_file(api, sandbox, skill, pack, harness) -> None:
    # AC-24 / INV-24: the key travels only in the child's environment
    # (Grok, Muse) or its inline config (opencode).
    name, positional = SKILL_RUNS[harness]
    result = await skill(name, *positional, api_key=SENTINEL)
    assert result.thread_id
    assert all(SENTINEL not in element for start in sandbox.starts() for element in start["argv"])
    assert files_with(sandbox, SENTINEL.encode("utf-8")) == []
    run = sandbox.starts({"grok": "grok", "opencode": "opencode", "muse": "muse-exec"}[harness])[0]
    variable = {"grok": "XAI_API_KEY", "opencode": "OPENCODE_CONFIG_CONTENT", "muse": "META_API_KEY"}[harness]
    assert run["credentials"][variable] is not None
    if harness != "opencode":
        assert run["credentials"][variable] == pack.key_digest(SENTINEL)
    for start in sandbox.starts():
        if start is not run and start["role"] != run["role"]:
            assert all(value is None for value in start["credentials"].values()), f"INV-23: {start['role']} carries a key"
    assert list(sandbox.tmp.iterdir()) == []
