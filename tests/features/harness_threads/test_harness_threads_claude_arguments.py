"""FILE: tests/features/harness_threads/test_harness_threads_claude_arguments.py

PURPOSE: Argument refusal through the three Claude Code thread functions (spec claude-thread-functions INV-5, INV-8): a thread id that is a session title, an upper-case UUID, dash-led or not a UUID, a prompt over 200,000 characters, blank or holding NUL, a malformed api_key, a relative or missing workspace, a skill folder without SKILL.md, a dash-led model, and a config that is another harness's record or a mapping each raise configuration.invalid_argument naming the argument, never quote the key, and happen before any process starts or any file or folder (the private config folder included) is created (AC-8, EC-6, EC-27); the boundary values the spec allows still run: a 200,000-character prompt on stdin and a quote-dense prompt that only the argv harnesses refuse on win32 (INV-5 rule 2, EC-27, D-5).
ROLE IN CODEBASE: Start here when a bad argument reaches claude, a refusal names the wrong argument, or a valid boundary value is refused.
ARCHITECTURE NOTE: Each refusal builds the stand-in command first, snapshots the whole sandbox including the stand-in's log folder, calls the function, and compares; a stand-in that started would have claimed a launch number in that folder, and a private config folder would show as a new path under the home.
FUNCTION INVENTORY: refuse runs one call that must be refused and checks the INV-5 shape; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new argument rule is one more row in the case table for its argument.
WHAT NOT TO DO IN THIS FILE: Do not compare refusal wording beyond the argument name, the cap and the INV-6 elements.
KNOWN EDGE CASES: The relative-path cases chdir into the sandbox so the relative path exists; it must still be refused. THREAD_CASES holds an upper-case spelling of a valid UUID and a session title on purpose: `claude --resume` would accept both (vendor-facts p13), so only the SDK's lowercase-UUID rule keeps a title from resuming another session.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-5, INV-8, §6.2 AC-8, §6.3 EC-6, EC-25 to EC-27, §8.1 D-5, D-8, §9.1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_arguments.py
"""

from __future__ import annotations

import pytest

PROMPT_CAP = 200000
VALID_THREAD = "c3f73f50-b50c-4f3a-8369-f97267313173"
THREAD_CASES = [
    ("title", "fix-login"), ("upper-uuid", VALID_THREAD.upper()), ("mixed-case-uuid", "C3f73f50-b50c-4f3a-8369-f97267313173"), ("dash", "-x"), ("flag", "--yolo"),
    ("not-uuid", "not-a-uuid"), ("short-uuid", VALID_THREAD[:-1]), ("braced-uuid", "{" + VALID_THREAD + "}"), ("uuid-newline", VALID_THREAD + "\n"),
    ("uuid-no-dashes", VALID_THREAD.replace("-", "")), ("path", "../" + VALID_THREAD), ("empty", ""), ("none", None),
]
PROMPT_CASES = [("empty", ""), ("blank", "  \n\t "), ("nul", "list\x00files"), ("not-text", 3), ("over-cap", "p" * (PROMPT_CAP + 1))]
KEY_CASES = [("empty", ""), ("inner-space", "sk-ant key with space"), ("nul", "sk-ant-key\x00tail"), ("non-ascii", "sk-ant-kéy-tail"), ("too-long", "k" * 4097), ("none", None)]
WORKSPACE_CASES = ["relative", "missing", "file", "not-text"]
MODEL_CASES = [("flag", "-m"), ("double-flag", "--model"), ("space", "claude sonnet"), ("too-long", "s" * 161), ("not-text", 7)]
SKILL_CASES = ["missing", "relative", "no-skill-md", "duplicate", "not-text", "string-not-list"]
WRONG_CONFIGS = ["GrokThreadConfig", "OpencodeThreadConfig", "MuseThreadConfig"]


@pytest.fixture
def refuse(api, sandbox, call, check_error):
    async def run(field: str, *, verb: str = "run", observations=(), unquoted: str | None = None, **arguments):
        # INV-5: refused before any program is looked up, any folder is
        # created and any process starts; the message names the
        # argument and never quotes the key.
        command = sandbox.command("claude")
        before = sandbox.snapshot(include_fake=True)
        if verb != "run":
            arguments.setdefault("thread_id", VALID_THREAD)
        with pytest.raises(api.NativeThreadError) as caught:
            await call("claude", verb, command=command, **arguments)
        error = caught.value
        check_error(error, harness="claude", verb=verb, code="configuration.invalid_argument", observations=[("argument name", (field,)), *observations])
        assert sandbox.snapshot(include_fake=True) == before, "INV-5: a refused call starts no process and creates no file or folder"
        assert not (sandbox.home / ".vidbyte").exists(), "AC-8: no private config folder was created"
        for text in (str(error), repr(error), error.vendor_message or ""):
            if unquoted:
                assert unquoted not in text, "INV-5: the value of api_key is never quoted"
        return error

    return run


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["continue", "fork"])
@pytest.mark.parametrize(("case", "thread_id"), THREAD_CASES, ids=[case for case, _ in THREAD_CASES])
async def test_thread_id_that_is_not_a_lowercase_uuid_is_refused(refuse, verb, case, thread_id) -> None:
    # AC-8 / INV-5 rule 1 / INV-8 / EC-6 / D-8: CLAUDE_THREAD_ID_PATTERN.
    await refuse("thread_id", verb=verb, thread_id=thread_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "prompt"), PROMPT_CASES, ids=[case for case, _ in PROMPT_CASES])
async def test_invalid_prompt_is_refused(refuse, case, prompt) -> None:
    # AC-8 / INV-5 rule 2: blank, NUL-holding, non-text or over
    # NATIVE_PROMPT_MAX_CHARS (200,000).
    observations = [("prompt cap", (str(PROMPT_CAP), f"{PROMPT_CAP:,}"))] if case == "over-cap" else []
    await refuse("prompt", prompt=prompt, observations=observations)


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "key"), KEY_CASES, ids=[case for case, _ in KEY_CASES])
async def test_malformed_api_key_is_refused_without_quoting_it(refuse, case, key) -> None:
    # AC-8 / INV-5: the shared key rules; the value is never quoted.
    quoted = key.strip() if isinstance(key, str) and len(key.strip()) >= 4 else None
    await refuse("api_key", api_key=key, unquoted=quoted)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", WORKSPACE_CASES)
async def test_invalid_workspace_is_refused(refuse, sandbox, monkeypatch, case) -> None:
    # AC-8: relative (even when it exists relative to the current
    # folder), missing, a file, or not a path.
    monkeypatch.chdir(sandbox.root)
    a_file = sandbox.root / "a-file.txt"
    a_file.write_text("not a folder\n", encoding="utf-8")
    workspace = {"relative": "ws", "missing": sandbox.root / "missing-ws", "file": a_file, "not-text": 42}[case]
    await refuse("workspace", workspace=workspace)


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "model"), MODEL_CASES, ids=[case for case, _ in MODEL_CASES])
async def test_invalid_model_is_refused(refuse, case, model) -> None:
    # AC-8 / INV-8: NATIVE_MODEL_PATTERN; no leading dash or whitespace.
    await refuse("model", model=model)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", SKILL_CASES)
async def test_invalid_skill_list_is_refused_naming_the_item(refuse, sandbox, monkeypatch, case) -> None:
    # AC-8: each skill an absolute existing folder holding SKILL.md,
    # unique; a bare string is not a list.
    monkeypatch.chdir(sandbox.root)
    good = sandbox.make_skill("good-skill")
    if case == "missing":
        skills, field = [sandbox.skill_root / "absent-skill"], "skills[0]"
    elif case == "relative":
        sandbox.make_skill("other-skill")
        skills, field = [good, "skill-src/other-skill"], "skills[1]"
    elif case == "no-skill-md":
        (sandbox.skill_root / "empty-skill").mkdir()
        skills, field = [good, sandbox.skill_root / "empty-skill"], "skills[1]"
    elif case == "duplicate":
        first = sandbox.make_skill("dup-skill", parent=sandbox.skill_root / "a")
        second = sandbox.make_skill("dup-skill", parent=sandbox.skill_root / "b")
        skills, field = [first, second], "skills[1]"
    elif case == "not-text":
        skills, field = [123], "skills[0]"
    else:
        skills, field = str(good), "skills"
    await refuse(field, skills=skills)


@pytest.mark.asyncio
@pytest.mark.parametrize("record", [*WRONG_CONFIGS, "mapping"])
async def test_config_that_is_not_a_claude_thread_config_is_refused(api, refuse, record) -> None:
    # AC-8 / INV-5 rule 3 / EC-33: another harness's record or a plain
    # mapping names config.
    raw = {"timeout_seconds": 5} if record == "mapping" else getattr(api, record)()
    await refuse("config", raw_config=raw)


@pytest.mark.asyncio
async def test_argument_check_comes_before_launcher_resolution(api, sandbox, call) -> None:
    # INV-5: an invalid argument is reported even when no claude can be
    # found, and nothing is written.
    before = sandbox.snapshot()
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", "continue", thread_id="fix-login", config={"claude_command": None})
    assert caught.value.failure_code.value == "configuration.invalid_argument"
    assert sandbox.snapshot() == before


@pytest.mark.asyncio
async def test_prompt_at_the_stdin_cap_still_runs_and_arrives_whole(sandbox, call) -> None:
    # INV-5 rule 2 / D-5 / EC-27: exactly 200,000 characters is allowed,
    # far past the 24,000 argv cap, and reaches Claude Code on stdin.
    prompt = "p" * PROMPT_CAP
    result = await call("claude", prompt=prompt)
    assert result.thread_id
    start = sandbox.only_start("claude")
    assert start["stdin_text"] == prompt and prompt not in start["argv"]


@pytest.mark.asyncio
async def test_quote_dense_prompt_is_not_held_to_the_windows_command_line_check(sandbox, call) -> None:
    # INV-5 rule 2 / EC-27: 20,000 double quotes would pass the Windows
    # command-line limit once quoted, which refuses it for Grok and Muse
    # on win32; Claude reads the prompt from stdin, so it runs.
    prompt = '"' * 20000 + " and 30,000 more characters " + "q" * 30000
    result = await call("claude", prompt=prompt)
    assert result.thread_id
    assert sandbox.only_start("claude")["stdin_text"] == prompt


@pytest.mark.asyncio
async def test_lowercase_uuid_thread_id_and_bare_model_are_accepted(sandbox, call) -> None:
    # D-8 boundary: a lowercase UUID passes the argument check (it then
    # reaches Claude Code), and a bare model id such as "sonnet" or
    # "claude-opus-5-5" passes NATIVE_MODEL_PATTERN.
    first = await call("claude", model="sonnet")
    second = await call("claude", "continue", "Again.", thread_id=first.thread_id, model="claude-opus-5-5")
    assert second.thread_id == first.thread_id
    assert [start["options"]["--model"] for start in sandbox.starts("claude")] == ["sonnet", "claude-opus-5-5"]
