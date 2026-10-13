"""FILE: tests/features/grok_host/test_grok_host_reads.py

PURPOSE: The successful outputs of GrokHost's reads and CLI runs: readiness (FR-1), the model catalog with reasoning efforts (D-12), session pages and cursors, casefolded search with its page cap, one-shot and fork results and their argv (T-2, INV-9), result text capping (INV-16), and dropped garbage frames (EC-6).
ROLE IN CODEBASE: Start here when a Grok read returns the wrong record or a CLI run builds the wrong argv. The error rows for the same functions live in test_grok_host_errors.py.
ARCHITECTURE NOTE: Every value asserted comes from the scenario fake_grok_peer.py was given, so a host that invents or drops a field fails. Argv checks read the argv the fake itself received, which is what Grok would parse.
FUNCTION INVENTORY: elements_holding finds argv elements that contain a value; pair_or_joined checks a fixed host flag in either argv form; assert_name_value_only pins T-2 for one user value; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Add a scenario key in fake_grok_peer.py before asserting a new field here.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert the order of one-shot flags; only their form is specified. 2. Do not assert flag names the spec does not give (the allow, deny and max-turns flags); assert the T-2 form of their values instead.
KNOWN EDGE CASES: The casefold case uses "Straße", which matches "STRASSE" only under str.casefold, not str.lower. The endless listing needs exactly GROK_LIST_MAX_PAGES requests to set truncated.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.3, §8.5, §9.1, §10 T-2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_reads.py
"""

from __future__ import annotations

from pathlib import Path
import pytest

KNOWN_SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
OTHER_SESSION = "0c9b8a7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d"
NEW_SESSION = "11111111-2222-4333-8444-555555555555"
THIRD_SESSION = "22222222-3333-4444-8555-666666666666"
PROMPT = "Summarise the README."
FORBIDDEN_ARGS = ("--always-approve", "--dangerously-skip-permissions", "--yolo", "bypassPermissions", "auto", "allowAll")


def elements_holding(argv: list[str], value: str) -> list[str]:
    return [arg for arg in argv if value in arg]


def pair_or_joined(argv: list[str], flag: str, value: str) -> bool:
    # Host-fixed flags appear in the spec as "--flag value"; T-2 prefers "--flag=value". Either carries the value.
    if f"{flag}={value}" in argv:
        return True
    return any(argv[index] == flag and argv[index + 1] == value for index in range(len(argv) - 1))


def assert_name_value_only(argv: list[str], value: str) -> None:
    # T-2: a caller-supplied value reaches argv only inside one "--name=value" element, never as its own element.
    holders = elements_holding(argv, value)
    assert len(holders) == 1, f"{value!r} should appear in exactly one argv element: {argv}"
    name, separator, carried = holders[0].partition("=")
    assert name.startswith("--") and separator == "=" and carried == value, holders[0]


def assert_no_approve_everything(argv: list[str]) -> None:
    for arg in argv:
        assert not any(arg == flag or arg.endswith("=" + flag) for flag in FORBIDDEN_ARGS), argv


def same_folder(left: str, right: Path) -> bool:
    return Path(left).resolve() == right.resolve()


@pytest.mark.asyncio
async def test_check_grok_ready_reports_version_protocol_auth_and_model(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # FR-1: the three-step check returns a GrokReadiness built from what Grok reported.
    async with make_grok_host() as host:
        readiness = await host.check_grok_ready()
    assert type(readiness).__name__ == "GrokReadiness"
    assert readiness.version == "1.0.52"
    assert readiness.protocol_version == 1
    assert readiness.agent_version == "1.0.52"
    assert readiness.auth_method_ids == ("grok-login",)
    assert readiness.current_model_id == "grok-code-fast-1"
    roles = sorted(record["role"] for record in grok_fake.records("start"))
    assert roles == ["models", "peer", "version"], "one --version run, one short-lived peer, one models run"
    assert grok_fake.received_methods() == ["initialize"], "readiness never opens a session"


@pytest.mark.asyncio
async def test_list_grok_models_returns_the_live_catalog_with_efforts(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # D-12: models and reasoning efforts come from initialize's _meta.modelState and each entry's _meta.reasoningEfforts.
    models = [
        {"modelId": "grok-code-fast-1", "name": "Grok Code Fast", "description": "Fast coding model.", "_meta": {"reasoningEfforts": ["low", "medium", "high"]}},
        {"modelId": "grok-4-heavy", "name": "Grok 4 Heavy", "description": "Deep reasoning model.", "_meta": {"reasoningEfforts": ["high"]}},
        {"modelId": "grok-plain"},
    ]
    async with make_grok_host({"acp": {"initialize": {"models": models, "current_model": "grok-4-heavy"}}}) as host:
        catalog = await host.list_grok_models()
    assert catalog.current_model_id == "grok-4-heavy"
    assert [model.model_id for model in catalog.models] == ["grok-code-fast-1", "grok-4-heavy", "grok-plain"]
    assert catalog.models[0].name == "Grok Code Fast" and catalog.models[0].description == "Fast coding model."
    assert catalog.models[0].reasoning_efforts == ("low", "medium", "high")
    assert catalog.models[1].reasoning_efforts == ("high",)
    assert catalog.models[2].name is None and catalog.models[2].description is None
    assert catalog.models[2].reasoning_efforts == ()
    assert isinstance(catalog.models, tuple)
    assert grok_fake.received_methods() == ["initialize"]


@pytest.mark.asyncio
async def test_list_grok_sessions_pages_with_the_workspace_cwd(grok_fake, make_grok_host, fast_stop) -> None:
    # session/list is sent with cwd set to the workspace; nextCursor becomes next_cursor and is passed back verbatim.
    pages = [
        [{"sessionId": KNOWN_SESSION, "title": "Refactor the Parser", "updatedAt": "2026-10-12T08:00:00Z"}, {"sessionId": OTHER_SESSION}],
        [{"sessionId": THIRD_SESSION, "title": "Third"}],
    ]
    async with make_grok_host({"acp": {"session_list": {"pages": pages}}}) as host:
        first = await host.list_grok_sessions()
        second = await host.list_grok_sessions(cursor=first.next_cursor)
    assert [session.session_id for session in first.sessions] == [KNOWN_SESSION, OTHER_SESSION]
    assert first.sessions[0].title == "Refactor the Parser"
    assert first.sessions[0].updated_at == "2026-10-12T08:00:00Z"
    assert first.sessions[1].title is None and first.sessions[1].updated_at is None
    assert first.next_cursor == "page-1"
    assert [session.session_id for session in second.sessions] == [THIRD_SESSION]
    assert second.next_cursor is None
    requests = grok_fake.received("session/list")
    assert [frame["params"].get("cursor") for frame in requests] == [None, "page-1"]
    assert all(same_folder(frame["params"]["cwd"], grok_fake.workspace) for frame in requests)
    assert all(same_folder(session.cwd, grok_fake.workspace) for session in first.sessions)


@pytest.mark.asyncio
async def test_search_matches_titles_casefolded_across_pages(grok_fake, make_grok_host, fast_stop) -> None:
    # search_grok_sessions keeps titles containing the query when both are casefolded, across pages.
    pages = [
        [{"sessionId": KNOWN_SESSION, "title": "Straße repairs"}, {"sessionId": OTHER_SESSION, "title": "Write release notes"}],
        [{"sessionId": THIRD_SESSION, "title": "strasse signage"}, {"sessionId": NEW_SESSION}],
    ]
    async with make_grok_host({"acp": {"session_list": {"pages": pages}}}) as host:
        found = await host.search_grok_sessions("STRASSE")
    assert found.query == "STRASSE"
    assert [session.session_id for session in found.sessions] == [KNOWN_SESSION, THIRD_SESSION]
    assert found.truncated is False
    assert len(grok_fake.received("session/list")) == 2


@pytest.mark.asyncio
async def test_search_with_no_match_returns_an_empty_result(make_grok_host, fast_stop) -> None:
    async with make_grok_host() as host:
        found = await host.search_grok_sessions("no such title")
    assert found.sessions == ()
    assert found.truncated is False


@pytest.mark.asyncio
async def test_search_stops_at_the_page_cap_and_sets_truncated(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # Reaching GROK_LIST_MAX_PAGES is not an error: truncated=True and no request past the cap.
    async with make_grok_host({"acp": {"session_list": {"endless": True}}}) as host:
        found = await host.search_grok_sessions("no such title")
    assert found.truncated is True
    assert found.sessions == ()
    assert len(grok_fake.received("session/list")) == grok_api.constants.GROK_LIST_MAX_PAGES == 20


@pytest.mark.asyncio
async def test_search_returns_at_most_limit_sessions_in_listing_order(grok_fake, make_grok_host, fast_stop) -> None:
    pages = [[{"sessionId": KNOWN_SESSION, "title": "parser one"}, {"sessionId": OTHER_SESSION, "title": "parser two"}], [{"sessionId": THIRD_SESSION, "title": "parser three"}]]
    async with make_grok_host({"acp": {"session_list": {"pages": pages}}}) as host:
        found = await host.search_grok_sessions("PARSER", limit=2)
    assert [session.session_id for session in found.sessions] == [KNOWN_SESSION, OTHER_SESSION]


@pytest.mark.asyncio
async def test_run_grok_once_returns_the_cli_result(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # FR-1: a one-shot CLI run; the result mirrors the --output-format json object.
    async with make_grok_host({"oneshot": {"session_id": NEW_SESSION}}) as host:
        result = await host.run_grok_once(grok_api.GrokOneShotRequest(prompt=PROMPT))
    assert (result.text, result.text_truncated, result.stop_reason, result.session_id, result.request_id) == ("one-shot answer", False, "end_turn", NEW_SESSION, "req-0001")
    assert not hasattr(result, "usage"), "the CLI JSON has no usage, so the record has no usage field"
    assert len(grok_fake.launches("oneshot")) == 1
    assert grok_fake.launches("peer") == [], "no model or effort was requested, so no live check runs"


@pytest.mark.asyncio
async def test_one_shot_argv_carries_every_value_in_name_value_form(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # T-2 and INV-9: values only as --name=value; fixed flags per §6.3.3; no approve-everything flag.
    request = grok_api.GrokOneShotRequest(
        prompt="--always-approve",
        model="grok-4-heavy",
        reasoning_effort="high",
        permission_mode=grok_api.GrokPermissionMode.ACCEPT_EDITS,
        allow_rules=("Read(docs/**)",),
        deny_rules=("Bash(rm -rf *)",),
        max_turns=7,
    )
    async with make_grok_host() as host:
        await host.run_grok_once(request)
    [argv] = grok_fake.launches("oneshot")
    assert "--single=--always-approve" in argv
    assert "--always-approve" not in argv, "a prompt that looks like a flag stays inside --single="
    assert "--model=grok-4-heavy" in argv and "--reasoning-effort=high" in argv
    assert_name_value_only(argv, "Read(docs/**)")
    assert_name_value_only(argv, "Bash(rm -rf *)")
    assert pair_or_joined(argv, "--output-format", "json")
    assert pair_or_joined(argv, "--permission-mode", "acceptEdits")
    assert any(pair_or_joined(argv, "--cwd", candidate) for candidate in (str(grok_fake.workspace), str(grok_fake.workspace.resolve())))
    assert any(arg.endswith("=7") and arg.startswith("--") for arg in argv), "max_turns is passed in --name=value form"
    assert_no_approve_everything(argv)


@pytest.mark.asyncio
async def test_one_shot_default_permission_mode_is_default(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # A-5 / T-2: one-shot runs rely on --permission-mode default unless the request says otherwise.
    async with make_grok_host() as host:
        await host.run_grok_once(grok_api.GrokOneShotRequest(prompt=PROMPT))
    [argv] = grok_fake.launches("oneshot")
    assert pair_or_joined(argv, "--permission-mode", "default")
    assert f"--single={PROMPT}" in argv


@pytest.mark.asyncio
async def test_one_shot_with_a_model_checks_it_live_before_spending(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # EC-37: a short-lived peer launched with --model=<model> confirms the model before the CLI run.
    async with make_grok_host() as host:
        await host.run_grok_once(grok_api.GrokOneShotRequest(prompt=PROMPT, model="grok-4-heavy", reasoning_effort="high"))
    [peer_argv] = grok_fake.launches("peer")
    assert "--model=grok-4-heavy" in peer_argv
    assert grok_fake.received_methods() == ["initialize"], "the live check opens no session"
    assert len(grok_fake.launches("oneshot")) == 1


@pytest.mark.asyncio
async def test_one_shot_text_over_the_cap_is_cut_and_flagged(grok_api, make_grok_host, fast_stop) -> None:
    # §6.3.3 run_grok_once / INV-16: not an error; text cut to NATIVE_RESULT_TEXT_MAX_CHARS with text_truncated.
    cap = grok_api.constants.NATIVE_RESULT_TEXT_MAX_CHARS
    async with make_grok_host({"oneshot": {"text_repeat": cap + 5}}) as host:
        result = await host.run_grok_once(grok_api.GrokOneShotRequest(prompt=PROMPT))
    assert len(result.text) == cap
    assert result.text_truncated is True


@pytest.mark.asyncio
async def test_fork_checks_the_listing_then_runs_the_fork_cli(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    # §6.3.3 fork: session/list on a short-lived peer, then grok --resume=<id> --fork-session --session-id=<new> --single=<prompt>.
    pages = [[{"sessionId": OTHER_SESSION, "title": "Write release notes"}], [{"sessionId": KNOWN_SESSION, "title": "Refactor the Parser"}]]
    async with make_grok_host({"acp": {"session_list": {"pages": pages}}}) as host:
        result = await host.fork_grok_session(KNOWN_SESSION, grok_api.GrokOneShotRequest(prompt=PROMPT), new_session_id=NEW_SESSION)
    assert result.session_id == NEW_SESSION
    assert len(grok_fake.received("session/list")) == 2, "the source session was found on the second page"
    [argv] = grok_fake.launches("oneshot")
    assert f"--resume={KNOWN_SESSION}" in argv
    assert "--fork-session" in argv
    assert f"--session-id={NEW_SESSION}" in argv
    assert f"--single={PROMPT}" in argv
    assert pair_or_joined(argv, "--output-format", "json")
    assert KNOWN_SESSION not in [arg for arg in argv if not arg.startswith("--")], "session ids never travel as bare argv elements"
    assert_no_approve_everything(argv)


@pytest.mark.asyncio
async def test_fork_without_a_new_id_lets_grok_choose_one(grok_api, grok_fake, make_grok_host, fast_stop) -> None:
    async with make_grok_host() as host:
        result = await host.fork_grok_session(KNOWN_SESSION, grok_api.GrokOneShotRequest(prompt=PROMPT))
    [argv] = grok_fake.launches("oneshot")
    assert not any(arg.startswith("--session-id") for arg in argv)
    assert result.session_id not in ("", KNOWN_SESSION)


@pytest.mark.asyncio
async def test_garbage_frames_before_an_answer_are_dropped(grok_api, make_grok_host, fast_stop) -> None:
    # EC-6: frames that are not UTF-8 JSON objects with an id or a method are dropped, and the real answer still lands.
    garbage = ["this is not json", "[1, 2, 3]", '{"jsonrpc": "2.0", "params": {}}', '"just a string"']
    async with make_grok_host({"acp": {"initialize": {"garbage_before": garbage}}}) as host:
        catalog = await host.list_grok_models()
    assert catalog.current_model_id == "grok-code-fast-1"


@pytest.mark.asyncio
async def test_garbage_instead_of_an_answer_fails_at_the_deadline(grok_api, make_grok_host, fast_stop, check_native_error) -> None:
    # EC-6: when only garbage arrives, the control request fails at its deadline with grok.server_unreachable.
    scenario = {"acp": {"initialize": {"mode": "silent", "garbage_before": ["not json at all"]}}}
    async with make_grok_host(scenario, control_timeout_seconds=0.5) as host:
        with pytest.raises(grok_api.NativeHostError) as caught:
            await host.list_grok_models()
    check_native_error(caught.value, code="grok.server_unreachable", token="control_timeout_seconds", operation="list_grok_models")


@pytest.mark.asyncio
async def test_child_environment_is_the_callers_plus_overlays(grok_fake, make_grok_host, fast_stop, monkeypatch: pytest.MonkeyPatch) -> None:
    # D-18 / §13: child environments are os.environ plus overlays, so a caller variable reaches every grok process.
    monkeypatch.setenv("VIDBYTE_TEST_MARKER", "present")
    async with make_grok_host({"env_keys": ["VIDBYTE_TEST_MARKER"]}) as host:
        await host.check_grok_ready()
    environments = [record["env"] for record in grok_fake.records("start")]
    assert environments and all(env == {"VIDBYTE_TEST_MARKER": "present"} for env in environments)

