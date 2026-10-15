"""FILE: tests/features/harness_threads/test_harness_threads_arguments.py

PURPOSE: Argument refusal through the nine public functions: every invalid key, workspace, prompt, thread id, model, skill list or config raises configuration.invalid_argument naming the argument, never quotes the key, and happens before any process starts or any file or folder is created (AC-5, INV-4, INV-7, EC-1 to EC-6, EC-33, EC-38, D-25); the boundary values the spec allows still run (§9.1), including Grok and Muse prose prompts of 24,000 and 23,999 characters (review R-29).
ROLE IN CODEBASE: Start here when a bad argument reaches a vendor process, a refusal names the wrong argument, or a valid boundary value is refused.
ARCHITECTURE NOTE: Each refusal case builds the stand-in command first, snapshots the whole sandbox including the stand-in's log folder, calls the function, and compares; a stand-in that started would have claimed a launch number in that folder, and a Grok home or Muse temp folder would show as a new path.
FUNCTION INVENTORY: refuse runs one call that must be refused and checks the INV-4 and INV-5 shape; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new argument rule is one more row in the case table for its argument.
WHAT NOT TO DO IN THIS FILE: Do not compare refusal wording beyond the argument name, the cap and the INV-5 elements.
KNOWN EDGE CASES: The relative-path cases chdir into the sandbox so the relative path exists; it must still be refused (R-14). Non-text values are passed on purpose. The quote-dense and astral prompt cases run only on win32, where the quoted command line is what the 32,767-unit CreateProcess limit counts (review R-8); their refusal names NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS, read from the constants module, and the Windows command line (review R-29).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-4, INV-7, §6.2 AC-5, §6.3 EC-1 to EC-6, EC-33, EC-38, §9.1; docs/spec/harness-thread-functions/review.md R-8, R-29
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_arguments.py
"""

from __future__ import annotations

import sys

import pytest

HARNESSES = ("grok", "opencode", "muse")
PROMPT_CAPS = {"grok": 24000, "opencode": 200000, "muse": 24000}
DENSE_PROMPTS = [("quotes", '"' * 20000), ("astral", chr(0x1F600) * 20000)]
PROSE_PROMPTS = [("prose-24000", ("word " * 4800)[:23999] + "."), ("one-space-23999", "p" * 11999 + " " + "p" * 11999)]
WINDOWS_UNITS_NAME = "NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS"
VALID_THREAD = "valid-thread-0001"
KEY_CASES = [
    ("empty", ""), ("blank", "   "), ("inner-space", "vbk key with space"), ("nul", "vbk-key\x00tail"), ("bell", "vbk-key\x07tail"),
    ("tab", "vbk-key\ttail"), ("trailing-newline", "vbk-key-tail\n"), ("non-ascii", "vbk-kéy-tail"), ("delete-char", "vbk-key\x7ftail"),
    ("env-token", "{env:DEEPSEEK_API_KEY}"), ("file-token", "{file:/etc/passwd}"), ("open-brace", "vbk-{key"), ("too-long", "k" * 4097),
    ("not-text", 12345), ("none", None),
]
WORKSPACE_CASES = ["relative", "missing", "file", "not-text"]
THREAD_CASES = [("flag", "--yolo"), ("dash", "-x"), ("path", "../x"), ("leading-space", " id"), ("inner-space", "id two"), ("newline", "id\n"), ("empty", ""), ("too-long", "t" * 161), ("none", None)]
MODEL_CASES = {
    "grok": [("flag", "-m"), ("space", "grok fast"), ("slash-first", "/grok"), ("too-long", "g" * 161), ("not-text", 7)],
    "opencode": [("no-provider", "deepseek"), ("upper-provider", "DeepSeek/v4"), ("empty-provider", "/deepseek-v4"), ("empty-model", "deepseek/"), ("dash-model", "deepseek/-pro"), ("space", "deep seek/v4"), ("too-long", "p/" + "m" * 159), ("none", None)],
    "muse": [("flag", "--model"), ("space", "muse large"), ("too-long", "m" * 161), ("not-text", 7)],
}
SKILL_CASES = ["missing", "relative", "file", "no-skill-md", "skill-md-folder", "bad-name", "too-long-name", "duplicate", "too-many", "not-text", "string-not-list"]
WRONG_CONFIGS = {"grok": "OpencodeThreadConfig", "opencode": "MuseThreadConfig", "muse": "GrokThreadConfig"}


@pytest.fixture
def refuse(api, sandbox, call, check_error):
    async def run(harness: str, field: str, *, verb: str = "run", observations=(), unquoted: str | None = None, **arguments):
        # INV-4: refused before any process or file; the message names
        # the argument; the key value is never quoted.
        command = sandbox.command(harness)
        before = sandbox.snapshot(include_fake=True)
        if verb != "run":
            arguments.setdefault("thread_id", VALID_THREAD)
        with pytest.raises(api.NativeThreadError) as caught:
            await call(harness, verb, command=command, **arguments)
        error = caught.value
        check_error(error, harness=harness, verb=verb, code="configuration.invalid_argument", observations=[("argument name", (field,)), *observations])
        assert sandbox.snapshot(include_fake=True) == before, "INV-4: a refused call starts no process and creates no file or folder"
        for text in (str(error), repr(error), error.vendor_message or ""):
            if unquoted:
                assert unquoted not in text, "INV-4: the value of api_key is never quoted"
        return error

    return run


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize(("case", "key"), KEY_CASES, ids=[case for case, _ in KEY_CASES])
async def test_invalid_api_key_is_refused_without_quoting_it(refuse, harness, case, key) -> None:
    # EC-1 / EC-38 / D-25: printable ASCII without space, { or }, at
    # most NATIVE_API_KEY_MAX_CHARS; a non-str is refused too.
    quoted = key.strip() if isinstance(key, str) and len(key.strip()) >= 4 else None
    await refuse(harness, "api_key", api_key=key, unquoted=quoted)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize("case", WORKSPACE_CASES)
async def test_invalid_workspace_is_refused(refuse, sandbox, monkeypatch, harness, case) -> None:
    # EC-2 / R-14: relative (even when it exists relative to the current
    # folder), missing, a file, or not a path.
    monkeypatch.chdir(sandbox.root)
    a_file = sandbox.root / "a-file.txt"
    a_file.write_text("not a folder\n", encoding="utf-8")
    workspace = {"relative": "ws", "missing": sandbox.root / "missing-ws", "file": a_file, "not-text": 42}[case]
    await refuse(harness, "workspace", workspace=workspace)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize(("case", "prompt"), [("empty", ""), ("blank", "  \n\t "), ("nul", "list\x00files"), ("not-text", 3)], ids=["empty", "blank", "nul", "not-text"])
async def test_invalid_prompt_is_refused(refuse, harness, case, prompt) -> None:
    # EC-3: empty, blank, NUL-holding or non-text prompts never reach
    # the vendor.
    await refuse(harness, "prompt", prompt=prompt)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_prompt_over_the_harness_cap_is_refused_naming_the_cap(refuse, harness) -> None:
    # EC-3 / D-20: 24,000 characters on argv for Grok and Muse, 200,000
    # on stdin for opencode.
    cap = PROMPT_CAPS[harness]
    await refuse(harness, "prompt", prompt="p" * (cap + 1), observations=[("prompt cap", (str(cap), f"{cap:,}"))])


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="the 32,767-unit command-line limit exists only on win32 (EC-3, review R-8)")
@pytest.mark.parametrize("harness", ["grok", "muse"])
@pytest.mark.parametrize(("case", "prompt"), DENSE_PROMPTS, ids=[case for case, _ in DENSE_PROMPTS])
async def test_prompt_whose_quoted_form_passes_the_argv_cap_is_refused(api, refuse, harness, case, prompt) -> None:
    # EC-3 / R-8: 20,000 characters, within the 24,000 cap, but quoting
    # each " or counting UTF-16 units doubles it on the command line;
    # it is refused, never launched as not_installed.
    # R-29: the refusal names the Windows command-line ceiling, read
    # from the constants module, not the 24,000-character cap.
    ceiling = getattr(api.constants, WINDOWS_UNITS_NAME, None)
    assert isinstance(ceiling, int), f"R-29: vidbyte.lib.constants.native_threads defines no {WINDOWS_UNITS_NAME}"
    observations = [("unit ceiling", (str(ceiling), f"{ceiling:,}")), ("Windows command line", ("command line", "command-line"))]
    await refuse(harness, "prompt", prompt=prompt, observations=observations)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "muse"])
@pytest.mark.parametrize(("case", "prompt"), PROSE_PROMPTS, ids=[case for case, _ in PROSE_PROMPTS])
async def test_prose_prompt_within_the_argv_cap_still_runs(sandbox, call, harness, case, prompt) -> None:
    # §9.1 / EC-3 / R-29: a prose prompt of 24,000 or 23,999 characters
    # is allowed; quoting it adds two units, which must not refuse it.
    result = await call(harness, prompt=prompt)
    assert result.thread_id
    start = sandbox.starts()[-1]
    sent = start["options"]["--single"] if harness == "grok" else start["operands"][0]
    assert sent == prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_prompt_at_the_harness_cap_still_runs(sandbox, call, harness) -> None:
    # §9.1 boundary: exactly the cap is allowed, so opencode is not
    # held to the argv cap.
    cap = PROMPT_CAPS[harness]
    result = await call(harness, prompt="p" * cap)
    assert result.thread_id
    start = sandbox.starts()[-1]
    sent = start["stdin_text"] if harness == "opencode" else (start["options"]["--single"] if harness == "grok" else start["operands"][0])
    assert sent == "p" * cap


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize("verb", ["continue", "fork"])
@pytest.mark.parametrize(("case", "thread_id"), THREAD_CASES, ids=[case for case, _ in THREAD_CASES])
async def test_invalid_thread_id_is_refused(refuse, harness, verb, case, thread_id) -> None:
    # EC-5 / INV-7: no leading dash, no whitespace or path characters,
    # at most 160 characters.
    await refuse(harness, "thread_id", verb=verb, thread_id=thread_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "case", "model"), [(harness, case, model) for harness, cases in MODEL_CASES.items() for case, model in cases], ids=[f"{harness}-{case}" for harness, cases in MODEL_CASES.items() for case, _ in cases])
async def test_invalid_model_is_refused(refuse, harness, case, model) -> None:
    # EC-5 / FR-8: opencode needs "<provider>/<model>"; Grok and Muse
    # take a bare id; no leading dash or whitespace; at most 160.
    await refuse(harness, "model", model=model)


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize("case", SKILL_CASES)
async def test_invalid_skill_list_is_refused_naming_the_item(refuse, sandbox, monkeypatch, harness, case) -> None:
    # EC-6: each skill an absolute existing folder holding a SKILL.md
    # file, named lowercase-hyphenated (<= 64), unique, at most 32.
    monkeypatch.chdir(sandbox.root)
    good = sandbox.make_skill("good-skill")
    if case == "missing":
        skills, field = [sandbox.skill_root / "absent-skill"], "skills[0]"
    elif case == "relative":
        sandbox.make_skill("other-skill")
        skills, field = [good, "skill-src/other-skill"], "skills[1]"
    elif case == "file":
        skills, field = [good / "SKILL.md"], "skills[0]"
    elif case == "no-skill-md":
        (sandbox.skill_root / "empty-skill").mkdir()
        skills, field = [sandbox.skill_root / "empty-skill"], "skills[0]"
    elif case == "skill-md-folder":
        (sandbox.skill_root / "odd-skill" / "SKILL.md").mkdir(parents=True)
        skills, field = [good, sandbox.skill_root / "odd-skill"], "skills[1]"
    elif case == "bad-name":
        skills, field = [sandbox.make_skill("Python_Style")], "skills[0]"
    elif case == "too-long-name":
        skills, field = [sandbox.make_skill("n" * 65)], "skills[0]"
    elif case == "duplicate":
        first = sandbox.make_skill("dup-skill", parent=sandbox.skill_root / "a")
        second = sandbox.make_skill("dup-skill", parent=sandbox.skill_root / "b")
        skills, field = [first, second], "skills[1]"
    elif case == "too-many":
        skills, field = [sandbox.make_skill(f"skill-{index}") for index in range(33)], "skills"
    elif case == "not-text":
        skills, field = [123], "skills[0]"
    else:
        skills, field = str(good), "skills"
    await refuse(harness, field, skills=skills)


@pytest.mark.asyncio
async def test_skill_list_at_the_count_and_name_caps_still_runs(sandbox, call) -> None:
    # §9.1 boundary: 32 skills and a 64-character name are allowed.
    skills = [sandbox.make_skill("n" * 64)] + [sandbox.make_skill(f"skill-{index}") for index in range(31)]
    await call("opencode", skills=skills)
    paths = sandbox.only_start("opencode")["opencode_config"]["skills"]["paths"]
    assert len(paths) == 32


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_config_of_the_wrong_type_is_refused(api, refuse, sandbox, harness) -> None:
    # EC-33: another harness's config record, or a plain mapping, names
    # config.
    await refuse(harness, "config", raw_config=getattr(api, WRONG_CONFIGS[harness])())
    await refuse(harness, "config", raw_config={"timeout_seconds": 5})


@pytest.mark.asyncio
async def test_argument_check_comes_before_launcher_resolution(api, sandbox, call) -> None:
    # INV-4: an invalid argument is reported even when the launcher is
    # also missing.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("grok", api_key="", command=(str(sandbox.root / "no-such-folder" / "grok"),))
    assert caught.value.failure_code.value == "configuration.invalid_argument"


@pytest.mark.asyncio
async def test_widest_allowed_key_still_runs(sandbox, call, pack) -> None:
    # D-25 boundary: every printable ASCII character except space, { and
    # }, up to NATIVE_API_KEY_MAX_CHARS.
    alphabet = "".join(chr(code) for code in range(0x21, 0x7F) if chr(code) not in "{}")
    key = (alphabet * 50)[:4096]
    await call("grok", api_key=key)
    assert sandbox.only_start("grok")["credentials"]["XAI_API_KEY"] == pack.key_digest(key)
