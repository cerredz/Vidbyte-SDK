"""FILE: tests/features/harness_threads/test_harness_threads_helper_arguments.py

PURPOSE: Argument refusal through the 47 new functions: every invalid value listed in spec §9.1 and §9.2 (wrong type, True for an int, out of range, blank, NUL, pattern miss, `branch` with `local` or `pr`, a relative or missing or whitespace-holding `design_doc`, a slash-option token in wrapper text, a reserved `/goal` word, `config` of another harness, the win32 command-line budget) raises configuration.invalid_argument naming the public parameter, before any child starts or anything is written (AC-12, INV-3, INV-9, EC-2 to EC-6, EC-42, EC-44 to EC-46, EC-53, EC-54, EC-57, EC-69, EC-70, EC-80, D-25, D-30); and the values that must pass still run (R-19, EC-70, EC-71, §9.1 boundaries), with a search query never on argv (INV-9).
ROLE IN CODEBASE: Start here when a bad argument reaches a vendor child, a refusal names the wrong parameter, or valid wrapper text is refused.
ARCHITECTURE NOTE: Each refusal builds the stand-in config first, snapshots the whole sandbox including the stand-in's log folder, calls the function, and compares (the #1036 `refuse` pattern of test_harness_threads_arguments.py): a child that started would have claimed a launch number there, and a Grok home or temp folder would show as a new path.
FUNCTION INVENTORY: refuse runs one call that must be refused and checks the INV-3 and INV-5 shape; place resolves the placeholders of a case row; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new argument rule is one row in its table.
WHAT NOT TO DO IN THIS FILE: Do not compare refusal wording beyond the parameter name and the INV-5 elements.
KNOWN EDGE CASES: The relative design-doc case chdirs into the workspace so the relative path exists; it must still be refused. `branch` together with `pr` may name either parameter. The command-line-units cases run only on win32, where CreateProcess counts quoted units.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-3, INV-9, §6.2 AC-12, §6.3 EC-2 to EC-6, EC-42, EC-44 to EC-46, EC-53, EC-54, EC-57, EC-69 to EC-71, EC-80, §9.1, §9.2, D-25, D-30
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_helper_arguments.py
"""

from __future__ import annotations

import inspect
import sys
from datetime import timedelta

import pytest

WS, DOC, DOC_SPACE, DOC_FLAG, DOC_REL, MISSING, A_FILE = "<ws>", "<doc>", "<doc-space>", "<doc-flag>", "<doc-rel>", "<missing>", "<file>"
DENSE = '"' * 20000
LIMITS = [("zero", 0), ("negative", -1), ("over", 201), ("float", 2.5), ("text", "5"), ("bool", True)]
SINCES = [("int", 24), ("zero", timedelta(0)), ("negative", timedelta(hours=-1)), ("max", timedelta.max), ("over-cap", timedelta(days=3650, seconds=1)), ("float", 2.5)]
THREAD_IDS = [("dots", "../../etc"), ("flag", "-rf"), ("space", "a b"), ("empty", ""), ("sql", "x' OR '1'='1"), ("too-long", "t" * 161), ("none", None), ("int", 7)]
QUERIES = [("empty", ""), ("blank", "   "), ("nul", "fix\x00bug"), ("too-long", "q" * 1001), ("int", 3)]
ONE_ID = {
    "grok": ["get_grok_thread", "read_grok_thread", "get_grok_thread_lineage", "delete_grok_thread"],
    "opencode": ["get_opencode_thread", "read_opencode_thread", "get_opencode_thread_lineage", "delete_opencode_thread"],
    "muse": ["get_muse_thread", "read_muse_thread", "get_muse_thread_lineage"],
}
LISTS = ["list_grok_threads", "list_recent_grok_threads", "list_opencode_threads", "list_recent_opencode_threads", "list_muse_threads", "list_recent_muse_threads"]
SKILL_CASES = [
    # (id, function, positional, keywords, field)
    ("goal-empty", "run_grok_goal", ("",), {}, "objective"),
    ("goal-blank", "run_grok_goal", ("  \n ",), {}, "objective"),
    ("goal-nul", "run_grok_goal", ("ship\x00it",), {}, "objective"),
    ("goal-too-long", "run_grok_goal", ("g" * 22977,), {}, "objective"),
    ("goal-budget-token", "run_grok_goal", ("ship it --budget 9",), {}, "objective"),
    ("goal-budget-joined", "run_grok_goal", ("ship it --budget=9",), {}, "objective"),
    ("goal-reserved-status", "run_grok_goal", ("status",), {}, "objective"),
    ("goal-reserved-clear", "run_grok_goal", (" Clear ",), {}, "objective"),
    ("goal-reserved-pause", "run_grok_goal", ("pause",), {}, "objective"),
    ("goal-reserved-resume", "run_grok_goal", ("RESUME",), {}, "objective"),
    ("goal-budget-zero", "run_grok_goal", ("ship",), {"budget_tokens": 0}, "budget_tokens"),
    ("goal-budget-over", "run_grok_goal", ("ship",), {"budget_tokens": 100000001}, "budget_tokens"),
    ("goal-budget-bool", "run_grok_goal", ("ship",), {"budget_tokens": True}, "budget_tokens"),
    ("goal-budget-text", "run_grok_goal", ("ship",), {"budget_tokens": "5"}, "budget_tokens"),
    ("goal-not-text", "run_grok_goal", (5,), {}, "objective"),
    ("implement-effort-token", "run_grok_implement", ("fix --effort 5",), {}, "task"),
    ("implement-effort-joined", "run_grok_implement", ("fix --effort=5",), {}, "task"),
    ("implement-effort-zero", "run_grok_implement", ("fix",), {"effort": 0}, "effort"),
    ("implement-effort-six", "run_grok_implement", ("fix",), {"effort": 6}, "effort"),
    ("implement-effort-bool", "run_grok_implement", ("fix",), {"effort": True}, "effort"),
    ("design-empty", "run_grok_design", ("",), {}, "description"),
    ("plan-doc-relative", "run_grok_execute_plan", (DOC_REL,), {}, "design_doc"),
    ("plan-doc-missing", "run_grok_execute_plan", (MISSING,), {}, "design_doc"),
    ("plan-doc-space", "run_grok_execute_plan", (DOC_SPACE,), {}, "design_doc"),
    ("plan-doc-flag", "run_grok_execute_plan", (DOC_FLAG,), {}, "design_doc"),
    ("plan-doc-folder", "run_grok_execute_plan", (WS,), {}, "design_doc"),
    ("plan-effort-three", "run_grok_execute_plan", (DOC,), {"effort": 3}, "effort"),
    ("plan-concurrency-nine", "run_grok_execute_plan", (DOC,), {"concurrency": 9}, "concurrency"),
    ("plan-concurrency-zero", "run_grok_execute_plan", (DOC,), {"concurrency": 0}, "concurrency"),
    ("plan-dry-run-int", "run_grok_execute_plan", (DOC,), {"dry_run": 1}, "dry_run"),
    ("plan-auto-pr-text", "run_grok_execute_plan", (DOC,), {"auto_pr": "yes"}, "auto_pr"),
    ("review-local-and-branch", "run_grok_review", (), {"local": True, "branch": "x"}, "branch"),
    ("review-branch-dash", "run_grok_review", (), {"branch": "-x"}, "branch"),
    ("review-branch-space", "run_grok_review", (), {"branch": "a b"}, "branch"),
    ("review-branch-empty", "run_grok_review", (), {"branch": ""}, "branch"),
    ("review-pr-zero", "run_grok_review", (), {"pr": 0}, "pr"),
    ("review-pr-bool", "run_grok_review", (), {"pr": True}, "pr"),
    ("review-pr-word", "run_grok_review", (), {"pr": "twelve"}, "pr"),
    ("review-pr-http", "run_grok_review", (), {"pr": "http://example.test/pull/1"}, "pr"),
    ("review-pr-float", "run_grok_review", (), {"pr": 1.5}, "pr"),
    ("review-local-int", "run_grok_review", (), {"local": 1}, "local"),
    ("resume-empty", "run_grok_resume_claude", ("",), {}, "session"),
    ("resume-codex-nul", "run_grok_resume_codex", ("a\x00b",), {}, "session"),
    ("imagine-empty", "run_grok_imagine", ("",), {}, "description"),
    ("imagine-video-blank", "run_grok_imagine_video", ("  ",), {}, "description"),
    ("grok-plan-empty", "run_grok_plan", ("",), {}, "task"),
    ("explore-empty", "run_grok_explore", ("",), {}, "question"),
    ("grok-command-unknown", "run_grok_command", ("no-such",), {}, "command"),
    ("grok-command-nul", "run_grok_command", ("<GOAL>", "x\x00y"), {}, "arguments"),
    ("grok-key-empty", "run_grok_goal", ("ship",), {"api_key": ""}, "api_key"),
    ("grok-model-flag", "run_grok_goal", ("ship",), {"model": "-m"}, "model"),
    ("grok-skills-text", "run_grok_goal", ("ship",), {"skills": "not-a-list"}, "skills"),
    ("grok-config-other", "run_grok_goal", ("ship",), {"config": "<opencode-config>"}, "config"),
    ("grok-workspace-missing", "run_grok_goal", ("ship",), {"workspace": MISSING}, "workspace"),
    ("opencode-command-dash", "run_opencode_command", ("-x",), {}, "command"),
    ("opencode-command-space", "run_opencode_command", ("a b",), {}, "command"),
    ("opencode-command-empty", "run_opencode_command", ("",), {}, "command"),
    ("opencode-command-nul-args", "run_opencode_command", ("review", "a\x00b"), {}, "arguments"),
    ("opencode-review-target-int", "run_opencode_review", (7,), {}, "target"),
    ("opencode-plan-empty", "run_opencode_plan", ("",), {}, "task"),
    ("opencode-plan-build-agent", "run_opencode_plan", ("plan it",), {"config": "<opencode-build>"}, "config"),
    ("opencode-model-none", "run_opencode_init", (), {"model": "deepseek"}, "model"),
    ("opencode-key-space", "run_opencode_init", (), {"api_key": "vbk key"}, "api_key"),
    ("opencode-config-other", "run_opencode_init", (), {"config": "<muse-config>"}, "config"),
    ("muse-skill-space", "run_muse_skill", ("bundled plan", "x"), {}, "skill"),
    ("muse-skill-empty", "run_muse_skill", ("", "x"), {}, "skill"),
    ("muse-skill-dash", "run_muse_skill", ("-x", "x"), {}, "skill"),
    ("muse-skill-prompt-empty", "run_muse_skill", ("bundled:plan", ""), {}, "prompt"),
    ("muse-goal-empty", "run_muse_goal", ("",), {}, "objective"),
    ("muse-plan-too-long", "run_muse_plan", ("m" * 22977,), {}, "task"),
    ("muse-import-empty", "run_muse_import", ("",), {}, "session_ref"),
    ("muse-scaffold-nul", "run_muse_scaffold", ("a\x00b",), {}, "description"),
    ("muse-browser-empty", "run_muse_browser_app", ("",), {}, "description"),
    ("muse-config-other", "run_muse_plan", ("plan",), {"config": "<grok-config>"}, "config"),
    ("muse-key-none", "run_muse_plan", ("plan",), {"api_key": None}, "api_key"),
]


@pytest.fixture
def refuse(api, sandbox, check_error, shapes, pack):
    async def run(name: str, *positional, field, observations=(), **keywords):
        # INV-3 / INV-4: refused before any child or file; the message
        # names the public parameter.
        function = getattr(api.native, name)
        harness = shapes.harness_of(name)
        parameters = inspect.signature(function).parameters
        if "config" in parameters and "config" not in keywords:
            keywords["config"] = api.configs[harness](**{pack.COMMAND_FIELDS[harness]: sandbox.command(harness), "timeout_seconds": pack.CALL_TIMEOUT_SECONDS})
        if "api_key" in parameters:
            keywords.setdefault("api_key", pack.API_KEY)
            keywords.setdefault("workspace", sandbox.workspace)
            if harness == "opencode":
                keywords.setdefault("model", pack.OPENCODE_MODEL)
        before = sandbox.snapshot(include_fake=True)
        with pytest.raises(api.NativeThreadError) as caught:
            await function(*positional, **keywords)
        check_error(caught.value, harness=harness, operation=name, code="configuration.invalid_argument", observations=[("argument name", (field,) if isinstance(field, str) else field), *observations])
        assert sandbox.snapshot(include_fake=True) == before, "INV-4: a refused call starts no child and writes nothing"
        assert pack.API_KEY not in str(caught.value)
        return caught.value

    return run


def place(value, sandbox, api, pack):
    # The placeholders of a case row, made real in this test's sandbox.
    if isinstance(value, tuple):
        return tuple(place(item, sandbox, api, pack) for item in value)
    if isinstance(value, dict):
        return {key: place(item, sandbox, api, pack) for key, item in value.items()}
    if value == WS:
        return sandbox.workspace
    if value == DOC:
        path = sandbox.workspace / "plan.md"
        path.write_text("# Plan\n", encoding="utf-8")
        return str(path)
    if value == DOC_SPACE:
        path = sandbox.workspace / "my plan.md"
        path.write_text("# Plan\n", encoding="utf-8")
        return str(path)
    if value == DOC_FLAG:
        path = sandbox.workspace / "x --auto-pr.md"
        path.write_text("# Plan\n", encoding="utf-8")
        return str(path)
    if value == DOC_REL:
        (sandbox.workspace / "rel-plan.md").write_text("# Plan\n", encoding="utf-8")
        return "rel-plan.md"
    if value == MISSING:
        return sandbox.root / "missing" / "plan.md"
    if value == A_FILE:
        path = sandbox.root / "a-file.txt"
        path.write_text("not a folder\n", encoding="utf-8")
        return path
    if value == "<GOAL>":
        return api.native.GrokCommand.GOAL
    configs = {
        "<opencode-config>": lambda: api.OpencodeThreadConfig(opencode_command=sandbox.command("opencode")),
        "<muse-config>": lambda: api.MuseThreadConfig(muse_command=sandbox.command("muse")),
        "<grok-config>": lambda: api.GrokThreadConfig(grok_command=sandbox.command("grok")),
        "<opencode-build>": lambda: api.OpencodeThreadConfig(opencode_command=sandbox.command("opencode"), agent="build"),
    }
    return configs[value]() if isinstance(value, str) and value in configs else value


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "name", "positional", "keywords", "field"), SKILL_CASES, ids=[row[0] for row in SKILL_CASES])
async def test_every_skill_function_refuses_its_invalid_arguments(api, sandbox, refuse, pack, monkeypatch, case, name, positional, keywords, field) -> None:
    # AC-12 / D-25 / D-30 / EC-42 / EC-44 to EC-46 / EC-53 / EC-54 /
    # EC-57 / EC-69 / EC-70.
    monkeypatch.chdir(sandbox.workspace)
    positional, keywords = place(positional, sandbox, api, pack), place(keywords, sandbox, api, pack)
    names = ("branch", "pr") if case == "review-local-and-branch" else field
    await refuse(name, *positional, field=names, **keywords)


@pytest.mark.asyncio
async def test_branch_and_pr_together_are_refused(refuse) -> None:
    # EC-44: at most one of local, branch and pr.
    await refuse("run_grok_review", branch="feature/x", pr=12, field=("branch", "pr"))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", LISTS)
@pytest.mark.parametrize(("case", "limit"), LIMITS, ids=[case for case, _ in LIMITS])
async def test_list_helpers_refuse_a_bad_limit(sandbox, refuse, name, case, limit) -> None:
    # EC-2 / D-1: 1..200 and not a bool.
    await refuse(name, sandbox.workspace, limit=limit, field="limit")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["list_grok_threads", "list_opencode_threads", "list_muse_threads"])
@pytest.mark.parametrize(("case", "since"), SINCES, ids=[case for case, _ in SINCES])
async def test_list_helpers_refuse_a_bad_since(sandbox, refuse, name, case, since) -> None:
    # EC-3 / EC-4: a positive timedelta up to NATIVE_SINCE_MAX.
    await refuse(name, sandbox.workspace, since=since, field="since")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["list_grok_threads_since", "list_opencode_threads_since", "list_muse_threads_since"])
async def test_since_wrappers_require_since(sandbox, refuse, name) -> None:
    # D-1: since is required for the _since wrappers.
    await refuse(name, sandbox.workspace, None, field="since")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [name for names in ONE_ID.values() for name in names])
@pytest.mark.parametrize(("case", "thread_id"), THREAD_IDS, ids=[case for case, _ in THREAD_IDS])
async def test_one_id_helpers_refuse_a_bad_thread_id(sandbox, refuse, name, case, thread_id) -> None:
    # EC-5 / INV-9 / T-9: never a path, a flag or SQL.
    await refuse(name, thread_id, sandbox.workspace, field="thread_id")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["search_grok_threads", "search_opencode_threads"])
@pytest.mark.parametrize(("case", "query"), QUERIES, ids=[case for case, _ in QUERIES])
async def test_search_helpers_refuse_a_bad_query(sandbox, refuse, name, case, query) -> None:
    # EC-6.
    await refuse(name, sandbox.workspace, query, field="query")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["list_grok_threads", "search_grok_threads", "list_opencode_threads", "list_muse_threads", "init_muse_workspace"])
@pytest.mark.parametrize("case", ["relative", "missing", "file", "not-text"])
async def test_helpers_refuse_a_bad_workspace(sandbox, refuse, monkeypatch, name, case) -> None:
    # INV-3: the workspace rule of NativeThreadRequest.
    monkeypatch.chdir(sandbox.root)
    a_file = sandbox.root / "a-file.txt"
    a_file.write_text("not a folder\n", encoding="utf-8")
    workspace = {"relative": "ws", "missing": sandbox.root / "missing-ws", "file": a_file, "not-text": 42}[case]
    extra = ("fix",) if name.startswith("search") else ()
    await refuse(name, workspace, *extra, field="workspace")


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["everything", 1, None])
async def test_grok_helpers_refuse_a_bad_scope(sandbox, refuse, scope) -> None:
    # D-1 step 7: scope is a GrokThreadScope.
    await refuse("list_grok_threads", sandbox.workspace, scope=scope, field="scope")


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run", [1, "yes", None])
async def test_init_refuses_a_non_bool_dry_run(sandbox, refuse, dry_run) -> None:
    # D-1 step 8: require_bool.
    await refuse("init_muse_workspace", sandbox.workspace, dry_run=dry_run, field="dry_run")


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "positional", "other"), [
    ("read_grok_thread", ("thread-1",), "<muse-config>"), ("delete_opencode_thread", ("ses_1",), "<grok-config>"),
    ("list_opencode_threads", (), "<muse-config>"), ("get_muse_thread", ("muse-1",), "<opencode-config>"), ("init_muse_workspace", (), "<grok-config>"),
])
async def test_helpers_refuse_a_config_of_another_harness(api, sandbox, refuse, pack, name, positional, other) -> None:
    # AC-12: config of another harness, naming config.
    await refuse(name, *positional, sandbox.workspace, config=place(other, sandbox, api, pack), field="config")


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="the 32,767-unit command-line limit exists only on win32 (EC-80, D-25)")
@pytest.mark.parametrize(("name", "field"), [("run_grok_goal", "objective"), ("run_grok_implement", "task"), ("run_muse_plan", "task"), ("run_muse_skill", "prompt")])
async def test_quote_dense_text_over_the_command_line_budget_is_refused_under_its_own_name(refuse, name, field) -> None:
    # EC-80 / D-25 / R-24: 20,000 characters, within the text cap, but
    # its quoted form passes the Windows budget.
    positional = ("bundled:plan", DENSE) if name == "run_muse_skill" else (DENSE,)
    await refuse(name, *positional, field=field)


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "text", "line"), [
    ("run_grok_goal", "clear the stale cache entries", "/goal clear the stale cache entries"),
    ("run_grok_goal", "Document the --effort and --dry-run flags", "/goal Document the --effort and --dry-run flags"),
    ("run_grok_implement", "Support --budget=9 in the CLI", "/implement Support --budget=9 in the CLI"),
    ("run_grok_implement", "Add a --dry-run flag", "/implement Add a --dry-run flag"),
    ("run_grok_design", "Design --local and --branch modes", "/design Design --local and --branch modes"),
    ("run_grok_goal", "g" * 22976, "/goal " + "g" * 22976),
], ids=["goal-leading-reserved-word", "goal-other-flags", "implement-budget", "implement-dry-run", "design-review-flags", "goal-at-text-cap"])
async def test_text_that_names_another_commands_flag_still_runs(sandbox, skill, name, text, line) -> None:
    # R-19 / EC-70 / EC-71 / D-25: only the command's own flags are
    # refused, only the whole value is compared with the reserved words,
    # and exactly the text cap passes.
    result = await skill(name, text)
    assert sandbox.only_start("grok")["options"]["--single"] == line and result.thread_id


@pytest.mark.asyncio
async def test_boundary_values_of_the_helpers_still_run(api, sandbox, helper) -> None:
    # §9.1: limit 1 and 200, since at NATIVE_SINCE_MAX, a 160-character
    # id (unknown, so not found rather than refused).
    assert await helper("list_grok_threads", sandbox.workspace, limit=1) == ()
    assert await helper("list_grok_threads", sandbox.workspace, limit=200, since=api.constants.NATIVE_SINCE_MAX) == ()
    with pytest.raises(api.NativeThreadError) as caught:
        await helper("get_muse_thread", "t" * 160, sandbox.workspace)
    assert caught.value.failure_code.value == "muse.thread_not_found"


@pytest.mark.asyncio
async def test_a_search_query_never_reaches_argv(sandbox, helper, stores) -> None:
    # INV-9: opencode search filters the list it read; the query that
    # looks like a flag stays in the SDK.
    stores.opencode_session("ses_flaggy", title="Handle --yolo safely")
    found = await helper("search_opencode_threads", sandbox.workspace, "--YOLO")
    assert [summary.thread_id for summary in found] == ["ses_flaggy"]
    assert all("--YOLO" not in element and "--yolo" not in element for start in sandbox.starts() for element in start["argv"])
