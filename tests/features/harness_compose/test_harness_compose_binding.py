"""FILE: tests/features/harness_compose/test_harness_compose_binding.py

PURPOSE: Binding and calling steps (INV-2, INV-3, INV-28, INV-31, EC-43, EC-44, EC-78, FR-1): each binder accepts exactly its six functions; a bound step stores resolved, checked values and hides its key; bad arguments fail at binding naming the argument; a direct call makes exactly one call to the bound function in its verb's argument order and lets its error through unchanged; an unanchored fork and a step without an invoker refuse direct calls before any process starts; a composite never calls a step's stored invoker; and a step called by a composite starts exactly the child process a direct call starts, with one Grok private home.
ROLE IN CODEBASE: Start here when bind_thread, bind_continue or ThreadStep behave differently from a direct call to the nine functions.
ARCHITECTURE NOTE: The composite used to call a step is run_staged_threads with a single stage whose template is the direct call's prompt, because it adds nothing to the prompt and needs no git. The comparison of direct and composite children reads the CliRunner spy, so it sees argv, working folder, stdin and environment exactly as CliRunner received them.
FUNCTION INVENTORY: unrelated_async is a callable that is not one of the nine; overlay_without_temp normalizes Muse's per-call temporary config folder; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new binder rule is an INV-2 change first, then one case here.
WHAT NOT TO DO IN THIS FILE: Do not call a step's invoker yourself; reach it only through `await step(prompt)` and composites.
KNOWN EDGE CASES: Muse gives every call a fresh XDG_CONFIG_HOME under the temporary folder, so that one folder name is normalized before comparing environments. A relative-looking workspace such as `ws/sub/..` must name an existing `sub` on POSIX, so the test creates it.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-2, INV-3, INV-28, INV-31, §6.3 EC-43, EC-44, EC-78, §8.1 D-2, §9.1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_binding.py
"""

from __future__ import annotations

import dataclasses
import functools
import re

import pytest

THREAD_ID = "0192f0c4-beef-7bee-8f00-000000000001"
BAD_KEY = "bad key with spaces 0123456789"


async def unrelated_async(prompt: str, *, api_key: str, workspace: str) -> None:
    return None


def overlay_without_temp(overlay, temp_folder) -> dict[str, str]:
    # Muse's private config folder is a fresh temporary folder per
    # call; everything else must be identical.
    pattern = re.escape(str(temp_folder)) + r"[\\/][^\\/]+"
    return {name: re.sub(pattern, "<temp>", value) for name, value in overlay.items()}


@pytest.mark.parametrize("harness", ["grok", "opencode", "muse"])
def test_each_binder_accepts_exactly_its_six_functions(compose_api, sandbox, runs, pack, harness) -> None:
    # INV-2 / EC-43: bind_thread takes run_* (RUN) and fork_*
    # (unanchored FORK); bind_continue takes continue_* (CONTINUE) and
    # fork_* (anchored FORK); anything else is refused naming function.
    api, compose = compose_api, compose_api.compose
    model = pack.OPENCODE_MODEL if harness == "opencode" else None
    common = {"api_key": pack.API_KEY, "workspace": sandbox.workspace, "model": model}
    for verb in pack.VERBS:
        function = api.functions[(harness, verb)]
        if verb == "continue":
            with pytest.raises(api.ConfigurationError) as caught:
                compose.bind_thread(function, **common)
            assert caught.value.details.get("field") == "function"
        else:
            step = compose.bind_thread(function, **common)
            assert (step.harness, step.verb, step.thread_id) == (api.NativeHarness(harness), api.NativeThreadVerb(verb), None)
            assert step.function is function
        if verb == "run":
            with pytest.raises(api.ConfigurationError) as caught:
                compose.bind_continue(function, THREAD_ID, **common)
            assert caught.value.details.get("field") == "function"
        else:
            step = compose.bind_continue(function, THREAD_ID, **common)
            assert (step.harness, step.verb, step.thread_id) == (api.NativeHarness(harness), api.NativeThreadVerb(verb), THREAD_ID)
    for stranger in (unrelated_async, lambda prompt: prompt, functools.partial(api.functions[(harness, "run")], api_key=pack.API_KEY)):
        with pytest.raises(api.ConfigurationError) as caught:
            compose.bind_thread(stranger, **common)
        assert caught.value.details.get("field") == "function"
        with pytest.raises(api.ConfigurationError) as caught:
            compose.bind_continue(stranger, THREAD_ID, **common)
        assert caught.value.details.get("field") == "function"
        assert pack.API_KEY not in str(caught.value)
    assert runs.invocations == [] and sandbox.launches() == []


def test_bound_step_stores_resolved_checked_values_and_hides_its_key(compose_api, sandbox, pack) -> None:
    # INV-2 / INV-4: workspace and skills resolved, the harness's
    # default config when none is given, the invoker set, the key out
    # of the repr.
    api = compose_api
    (sandbox.workspace / "sub").mkdir()
    skill = sandbox.make_skill("python-style")
    step = api.compose.bind_thread(api.functions[("grok", "run")], api_key=pack.API_KEY, workspace=str(sandbox.workspace / "sub" / ".."), skills=[str(skill)])
    assert step.workspace == sandbox.workspace.resolve()
    assert tuple(step.skills) == (skill.resolve(),)
    assert step.config == api.configs["grok"]()
    assert step.api_key == pack.API_KEY and step.model is None and step.thread_id is None
    assert step.invoker is not None and callable(step.invoker)
    assert pack.API_KEY not in repr(step)
    opencode = api.compose.bind_thread(api.functions[("opencode", "run")], api_key=pack.API_KEY, workspace=sandbox.workspace, model=pack.OPENCODE_MODEL)
    assert opencode.config == api.configs["opencode"]() and opencode.model == pack.OPENCODE_MODEL


@pytest.mark.parametrize(("case", "field"), [
    ("blank key", "api_key"), ("key with spaces", "api_key"), ("relative workspace", "workspace"), ("missing workspace", "workspace"),
    ("opencode without model", "model"), ("grok model with spaces", "model"), ("bad thread id", "thread_id"), ("blank thread id", "thread_id"),
    ("missing skill folder", "skills[0]"), ("skills as one string", "skills"), ("config of another harness", "config"), ("config that is not a record", "config"),
])
def test_bad_argument_fails_at_binding_naming_it(compose_api, sandbox, runs, pack, case, field) -> None:
    # INV-2: every argument is checked when the step is built, by the
    # record the nine functions use, so nothing fails later mid-run.
    api, compose = compose_api, compose_api.compose
    run_grok, run_opencode, continue_grok = api.functions[("grok", "run")], api.functions[("opencode", "run")], api.functions[("grok", "continue")]
    workspace = sandbox.workspace
    calls = {
        "blank key": lambda: compose.bind_thread(run_grok, api_key="", workspace=workspace),
        "key with spaces": lambda: compose.bind_thread(run_grok, api_key=BAD_KEY, workspace=workspace),
        "relative workspace": lambda: compose.bind_thread(run_grok, api_key=pack.API_KEY, workspace="relative/folder"),
        "missing workspace": lambda: compose.bind_thread(run_grok, api_key=pack.API_KEY, workspace=sandbox.root / "no-such-folder"),
        "opencode without model": lambda: compose.bind_thread(run_opencode, api_key=pack.API_KEY, workspace=workspace),
        "grok model with spaces": lambda: compose.bind_thread(run_grok, api_key=pack.API_KEY, workspace=workspace, model="grok 4 fast"),
        "bad thread id": lambda: compose.bind_continue(continue_grok, "bad id!", api_key=pack.API_KEY, workspace=workspace),
        "blank thread id": lambda: compose.bind_continue(continue_grok, "", api_key=pack.API_KEY, workspace=workspace),
        "missing skill folder": lambda: compose.bind_thread(run_grok, api_key=pack.API_KEY, workspace=workspace, skills=[sandbox.root / "no-skill"]),
        "skills as one string": lambda: compose.bind_thread(run_grok, api_key=pack.API_KEY, workspace=workspace, skills=str(sandbox.skill_root)),
        "config of another harness": lambda: compose.bind_thread(run_grok, api_key=pack.API_KEY, workspace=workspace, config=api.configs["opencode"]()),
        "config that is not a record": lambda: compose.bind_thread(run_grok, api_key=pack.API_KEY, workspace=workspace, config={"permission_mode": "plan"}),
    }
    with pytest.raises(api.ConfigurationError) as caught:
        calls[case]()
    assert caught.value.details.get("field") == field, f"{case}: {caught.value} {caught.value.details}"
    assert BAD_KEY not in str(caught.value) and pack.API_KEY not in str(caught.value)
    assert runs.invocations == [] and sandbox.launches() == []


@pytest.mark.asyncio
async def test_direct_calls_run_the_bound_function_once_in_its_verbs_order(compose_api, sandbox, steps, pack) -> None:
    # INV-2: run, continue (thread id first, same thread) and anchored
    # fork (a new thread branched from it), each exactly one call with
    # the bound key, workspace and config.
    api = compose_api
    first = await steps.bind("grok", label="direct-run", plan=True)("Say hello.")
    assert isinstance(first, api.NativeThreadResult)
    launch = sandbox.only_launch("direct-run")
    assert pack.launch_prompt(launch) == "Say hello."
    assert launch["start"]["options"]["--permission-mode"] == "plan"
    assert launch["start"]["options"]["--cwd"] == str(sandbox.workspace)
    assert launch["start"]["credentials"]["XAI_API_KEY"] == pack.key_digest(pack.API_KEY)
    assert first.thread_id == pack.launch_session(launch)
    again = await steps.bind("grok", "continue", first.thread_id, label="direct-continue")("Again.")
    resumed = sandbox.only_launch("direct-continue")
    assert resumed["start"]["options"]["--resume"] == first.thread_id and resumed["start"]["switches"] == []
    assert again.thread_id == first.thread_id
    branch = await steps.bind("grok", "fork", first.thread_id, label="direct-fork")("Branch.")
    forked = sandbox.only_launch("direct-fork")
    assert forked["start"]["options"]["--resume"] == first.thread_id and forked["start"]["switches"] == ["--fork-session"]
    assert branch.thread_id not in (None, first.thread_id)


@pytest.mark.asyncio
async def test_unanchored_fork_refuses_a_direct_call_and_errors_pass_through_unchanged(compose_api, sandbox, steps, runs, pack) -> None:
    # INV-2 / EC-44: an unanchored fork names thread_id before any
    # process starts; a NativeThreadError from the function is the very
    # error the harness raised.
    api = compose_api
    fork = steps.bind("grok", "fork", label="unanchored")
    with pytest.raises(api.ConfigurationError) as caught:
        await fork("Branch.")
    assert caught.value.details.get("field") == "thread_id"
    assert runs.invocations == [] and sandbox.launches() == []
    rejected = steps.bind("grok", label="rejected", fake={"mode": "key_rejected"})
    with pytest.raises(api.NativeThreadError) as failure:
        await rejected("Say hello.")
    assert failure.value.failure_code.value == "grok.key_rejected"
    frames = []
    trace = failure.value.__traceback__
    while trace is not None:
        frames.append(trace.tb_frame.f_code.co_filename.replace("\\", "/"))
        trace = trace.tb_next
    assert any("/vidbyte/harnesses/native/grok/" in name for name in frames), "the error is the one the Grok function raised, not a copy"


@pytest.mark.asyncio
async def test_step_without_invoker_refuses_direct_calls_yet_runs_in_a_composite(compose_api, sandbox, steps, runs, pack) -> None:
    # EC-78 / INV-2 / INV-3: a ThreadStep built without a binder names
    # ThreadStep.invoker on a direct call, before any process; a
    # composite runs it through compose's own invoke.
    api = compose_api
    raw = api.records.ThreadStep(function=api.functions[("grok", "run")], harness=api.NativeHarness.GROK, verb=api.NativeThreadVerb.RUN, api_key=pack.API_KEY, workspace=sandbox.workspace, config=steps.config("grok", label="raw"))
    assert raw.invoker is None
    with pytest.raises(api.ConfigurationError) as caught:
        await raw("Direct.")
    assert caught.value.details.get("field") == "ThreadStep.invoker"
    assert runs.invocations == [] and sandbox.launches() == []
    staged = await api.compose.run_staged_threads([api.records.StageSpec(step=raw, template="Do it.")])
    assert staged.failed_stage is None and staged.stages[0].ok
    assert pack.launch_prompt(sandbox.only_launch("raw")) == "Do it."


@pytest.mark.asyncio
async def test_composite_never_calls_a_replaced_invoker(compose_api, sandbox, steps, pack) -> None:
    # EC-78 / INV-3: dataclasses.replace with another invoker gives an
    # equal step whose repr hides the invoker; a direct call runs the
    # replacement (the caller's own code), a composite never does.
    api = compose_api
    bound = steps.bind("grok", label="bound")
    seen: list[str] = []

    async def replacement(step, prompt: str):
        seen.append(prompt)
        return api.NativeThreadResult(harness=api.NativeHarness.GROK, thread_id="replacement-thread", text="from the replacement", text_truncated=False)

    replaced = dataclasses.replace(bound, invoker=replacement)
    assert replaced == bound
    assert "replacement" not in repr(replaced)
    direct = await replaced("Direct.")
    assert direct.thread_id == "replacement-thread" and seen == ["Direct."]
    assert sandbox.launches(label="bound") == []
    staged = await api.compose.run_staged_threads([api.records.StageSpec(step=replaced, template="Composite.")])
    assert seen == ["Direct."], "a composite must call the step's checked function, never its stored invoker"
    assert staged.stages[0].ok and staged.stages[0].text != "from the replacement"
    assert pack.launch_prompt(sandbox.only_launch("bound")) == "Composite."


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode", "muse"])
async def test_composite_step_starts_exactly_the_process_a_direct_call_starts(compose_api, sandbox, steps, runs, pack, harness) -> None:
    # INV-28 / INV-31: same argv, working folder, stdin and environment
    # as a direct call with the same arguments; no git; for Grok one
    # private home, the direct call's own.
    api = compose_api
    skill = sandbox.make_skill("python-style")
    bound = steps.bind(harness, label=f"{harness}-same", skills=[skill])
    await bound("Inspect the code.")
    staged = await api.compose.run_staged_threads([api.records.StageSpec(step=bound, template="Inspect the code.")])
    assert staged.failed_stage is None
    assert runs.git_calls() == []
    (direct_index, direct), (composite_index, composite) = runs.vendor_calls()
    assert composite.argv == direct.argv
    assert composite.cwd == direct.cwd
    assert composite.stdin_text == direct.stdin_text
    assert tuple(composite.env_remove) == tuple(direct.env_remove)
    assert overlay_without_temp(composite.env_overlay, sandbox.tmp) == overlay_without_temp(direct.env_overlay, sandbox.tmp)
    homes = sandbox.home / ".vidbyte" / "grok-homes"
    if harness == "grok":
        assert sorted(path.name for path in homes.iterdir()) == [pack.private_home(sandbox.home, sandbox.workspace).name]
    else:
        assert not homes.exists() or list(homes.iterdir()) == []
