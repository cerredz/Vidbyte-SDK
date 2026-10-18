"""FILE: tests/features/harness_compose/test_harness_compose_chain.py

PURPOSE: chain_threads and the pair aliases (AC-2, AC-7, AC-19, INV-6, INV-12, INV-15, INV-16, INV-17, INV-18, INV-29, EC-34, EC-36, EC-37, EC-80): step 1 gets exactly the caller's prompt and step k the template rendered with the previous answer and diff, braces in model output arriving literally; the writer's diff is the oracle's diff; a failed step ends the chain with the very error the function raised and later steps never start; a chain without {diff} runs no git at all; and a 100,000-character answer holding a NUL is shortened to fit a Grok step, ending with the truncation note, while the record keeps the raw text; an answer of double quotes is cut by the win32 command-line unit ceiling as well as the character cap; surrogate halves in an answer reach a Grok, Muse or opencode next step repaired, a lone half as U+FFFD and a pair that only NULs kept apart as the one character it encodes, while the record keeps the raw text, no stand-in is left running, and a truncation note counts the answer's length after the repair.
ROLE IN CODEBASE: Start here when a chain sends the wrong prompt, mis-attributes a diff, keeps going after a failure or sends a prompt the next step refuses.
ARCHITECTURE NOTE: Expected diffs come from the conftest tree oracle (the test's own git and a temporary index), and expected prompts from rendering the prompt files directly, so neither comes from the code under test. Prompts are read from the stand-in logs: Grok's --single, opencode's stdin, Muse's operand.
FUNCTION INVENTORY: traceback_files lists the source files of an exception's traceback; surrogate_points lists the surrogate code points of a text; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new chain behaviour gets its own test with its own labelled stand-ins; keep labels unique within a test.
WHAT NOT TO DO IN THIS FILE: Do not compare against text compose produced; render the prompt files or ask the oracle.
KNOWN EDGE CASES: The omitted count of the truncation note is measured on the answer after its NUL is removed, because INV-18 removes NULs before it shortens. NATIVE_ARGV_PROMPT_MAX_CHARS is imported by name into the request record, so the 24,000 cap holds whatever the constants module says (spec §13). A surrogate half reaches compose only through a JSON escape such as \ud83d in a stand-in's output: json.loads joins two escapes side by side into one character, and opencode's text parts are joined with a line break, so a pair split across two parts arrives as two lone halves. Two halves side by side therefore exist only inside compose, once it removed the NULs between them, which is the case these tests send.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-6, INV-12, INV-15 to INV-18, §6.2 AC-2, AC-7, AC-19, §6.3 EC-34, EC-36, EC-37, EC-80; docs/spec/native-thread-compose/review.md R-12
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_chain.py
"""

from __future__ import annotations

import asyncio
import re
import sys

import pytest

NOTES = "NOTES-CONTENT-7f3a\nsecond line\n"
GROK_TEXT = "Use {curly} braces, {{doubled}} ones and a lone } here."
VENDOR = "the model refused because the request was ambiguous"
HIGH, LOW, NUL = chr(0xD83D), chr(0xDE00), chr(0)
REPLACEMENT, JOINED = chr(0xFFFD), chr(0x1F600)
# Each case: the opencode answer's text parts, and the answer
# as the next step must receive it.
SURROGATE_CASES = {
    "lone high half": (["answer " + HIGH + " end"], "answer " + REPLACEMENT + " end"),
    "lone low half": (["answer " + LOW + " end"], "answer " + REPLACEMENT + " end"),
    "pair split across two parts": (["answer " + HIGH, LOW + " end"], "answer " + REPLACEMENT + "\n" + REPLACEMENT + " end"),
    "pair with a NUL between": (["answer " + HIGH + NUL + LOW + " end"], "answer " + JOINED + " end"),
    "pair with two NULs between": (["answer " + HIGH + NUL + NUL + LOW + " end"], "answer " + JOINED + " end"),
}
# 30,004 code points; 30,002 once the NUL is gone and the pair
# is joined into one character.
LONG_SURROGATE_ANSWER = "x" * 30_000 + HIGH + NUL + LOW + "y"
REPAIRED_LONG_CHARS = 30_002


def traceback_files(error: BaseException) -> list[str]:
    files: list[str] = []
    trace = error.__traceback__
    while trace is not None:
        files.append(trace.tb_frame.f_code.co_filename.replace("\\", "/"))
        trace = trace.tb_next
    return files


def surrogate_points(text: str) -> list[str]:
    return [hex(ord(char)) for char in text if 0xD800 <= ord(char) <= 0xDFFF]


@pytest.mark.asyncio
async def test_opencode_then_grok_sends_the_answer_and_the_writers_diff(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-2 / INV-17 / INV-8: opencode gets exactly the prompt; Grok gets
    # chain_turn rendered with the prompt, opencode's answer and the
    # oracle's diff of notes.txt; only the step before the last has a
    # diff.
    api = compose_api
    sandbox.make_repo()
    before = sandbox.tree_of()
    opencode = steps.bind("opencode", label="writer", fake={"final_parts": ["done"], "write_files": {"notes.txt": NOTES}})
    grok = steps.bind("grok", label="reader")
    result = await api.compose.run_opencode_then_grok(pack.PROMPT, opencode=opencode, grok=grok)
    writer, reader = sandbox.only_launch("writer"), sandbox.only_launch("reader")
    files, diff_text = sandbox.tree_diff(before, sandbox.tree_of())
    assert files == ("notes.txt",) and "+NOTES-CONTENT-7f3a" in diff_text
    assert pack.launch_prompt(writer) == pack.PROMPT
    grok_prompt = pack.launch_prompt(reader)
    assert grok_prompt.strip() == pack.render("chain_turn", prompt=pack.PROMPT, previous="done", diff=diff_text)
    assert pack.PROMPT in grok_prompt and "notes.txt" in grok_prompt and "+NOTES-CONTENT-7f3a" in grok_prompt
    assert len(result.outcomes) == 2 and result.failed_step is None
    assert [outcome.thread_id for outcome in result.outcomes] == [pack.launch_session(writer), pack.launch_session(reader)]
    assert result.outcomes[0].text == "done"
    first_diff = result.outcomes[0].diff
    assert (first_diff.files, first_diff.text, first_diff.truncated) == (("notes.txt",), diff_text, False)
    assert result.outcomes[1].diff is None
    (first, _), (second, _) = runs.vendor_calls()
    assert not runs.overlap(first, second), "INV-12: chain steps run one after another"
    assert sandbox.leftovers() == []


@pytest.mark.asyncio
async def test_failed_middle_step_ends_the_chain_with_the_functions_own_error(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-7 / INV-15 / INV-16 / INV-29 / INV-6 / INV-17: Grok
    # answers with braces, opencode gets the template rendered
    # literally and fails run_failed; the record holds that
    # very error, Muse never starts, and a template without
    # {diff} runs no git (the folder is not a repository).
    api = compose_api
    grok = steps.bind("grok", label="first", fake={"text": GROK_TEXT})
    opencode = steps.bind("opencode", label="second", fake={"mode": "fail", "vendor_text": VENDOR, "exit_code": 93})
    muse = steps.bind("muse", label="third")
    result = await api.compose.chain_threads([grok, opencode, muse], "Continue from: {previous}", prompt=pack.PROMPT)
    assert pack.launch_prompt(sandbox.only_launch("first")) == pack.PROMPT
    second = sandbox.only_launch("second")
    assert pack.launch_prompt(second) == "Continue from: " + GROK_TEXT
    assert len(result.outcomes) == 2 and result.failed_step == 1
    assert result.outcomes[0].ok and result.outcomes[0].text == GROK_TEXT
    error = result.outcomes[1].error
    assert isinstance(error, api.NativeThreadError) and result.outcomes[1].result is None
    assert error.failure_code.value == "opencode.run_failed" and error.exit_code == 93
    assert VENDOR in (error.vendor_message or "")
    assert any("/vidbyte/harnesses/native/opencode/" in name for name in traceback_files(error)), "the recorded error is the object run_opencode_thread raised"
    assert result.outcomes[1].thread_id == pack.launch_session(second)
    assert all(outcome.diff is None for outcome in result.outcomes)
    assert sandbox.launches(label="third") == [] and runs.calls_of("third") == []
    assert runs.git_calls() == []


@pytest.mark.asyncio
async def test_long_answer_with_a_nul_is_shortened_to_fit_the_grok_step(compose_api, sandbox, steps, runs, pack) -> None:
    # AC-19 / INV-18 / EC-34 / EC-37: the 100,000-character answer loses
    # its NUL and is cut to the largest prefix that fits beside the
    # fixed text, followed by the truncation note with the omitted
    # count; the caller's prompt stays whole; the Grok step succeeds;
    # the record keeps the raw answer.
    api = compose_api
    sandbox.make_repo()
    answer = "x" * 50_000 + "\x00" + "x" * 49_999
    assert len(answer) == api.threads_constants.NATIVE_RESULT_TEXT_MAX_CHARS
    opencode = steps.bind("opencode", label="long", fake={"final_parts": [answer]})
    grok = steps.bind("grok", label="short")
    result = await api.compose.run_opencode_then_grok(pack.PROMPT, opencode=opencode, grok=grok)
    assert result.failed_step is None and result.outcomes[1].ok
    assert result.outcomes[0].text == answer, "records keep the raw answer, NUL included"
    prompt = pack.launch_prompt(sandbox.only_launch("short"))
    cap = api.threads_constants.NATIVE_ARGV_PROMPT_MAX_CHARS
    assert cap - 100 <= len(prompt) <= cap, f"the shortened prompt uses the room it has: {len(prompt)}"
    if sys.platform == "win32":
        assert pack.command_line_units(prompt) <= api.threads_constants.NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS
    assert "\x00" not in prompt
    assert pack.PROMPT in prompt
    run = max(re.finditer(r"x+", prompt), key=lambda match: len(match.group()))
    kept = len(run.group())
    assert kept >= 12_000, f"only {kept} characters of the answer were kept"
    note = pack.render("truncation_note", omitted=(len(answer) - 1) - kept)
    assert prompt[run.end() :].lstrip().startswith(note), "the shortened answer ends with the truncation note giving the omitted count"


@pytest.mark.asyncio
async def test_quote_dense_answer_is_shortened_by_command_line_units_as_well(compose_api, sandbox, steps, runs, pack) -> None:
    # EC-36 / INV-18 / D-19: an answer of 100,000 double quotes
    # takes two command-line units per character, so on win32 the
    # unit ceiling, not the character cap, sets the cut; the Grok
    # step still succeeds, the kept prefix ends with its truncation
    # note, and the prompt uses the room its binding cap leaves.
    api = compose_api
    answer = '"' * api.threads_constants.NATIVE_RESULT_TEXT_MAX_CHARS
    opencode = steps.bind("opencode", label="quotes", fake={"final_parts": [answer]})
    grok = steps.bind("grok", label="after-quotes")
    result = await api.compose.chain_threads([opencode, grok], "Answer was: {previous}", prompt=pack.PROMPT)
    assert result.failed_step is None and result.outcomes[1].ok, "the Grok step ran on a prompt it accepts"
    assert result.outcomes[0].text == answer
    prompt = pack.launch_prompt(sandbox.only_launch("after-quotes"))
    chars_cap = api.threads_constants.NATIVE_ARGV_PROMPT_MAX_CHARS
    units_cap = api.threads_constants.NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS
    assert len(prompt) <= chars_cap
    if sys.platform == "win32":
        units = pack.command_line_units(prompt)
        assert units_cap - 200 <= units <= units_cap, f"the prompt fits the unit ceiling and uses it: {units} units"
    else:
        assert chars_cap - 200 <= len(prompt), f"the prompt uses the character room: {len(prompt)}"
    run = max(re.finditer('"+', prompt), key=lambda match: len(match.group()))
    kept = len(run.group())
    assert kept >= 5_000, f"only {kept} quotes were kept"
    note = pack.render("truncation_note", omitted=len(answer) - kept)
    assert prompt[run.end() :].lstrip().startswith(note), "the shortened answer ends with the truncation note giving the omitted count"
    assert runs.git_calls() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(SURROGATE_CASES))
@pytest.mark.parametrize("harness", ["grok", "muse", "opencode"])
async def test_surrogate_halves_in_an_answer_reach_the_next_step_repaired(compose_api, sandbox, steps, pack, alive, case, harness) -> None:
    # EC-80 / INV-18 / INV-15: nothing is refused. The next step
    # gets U+FFFD for each lone half and the joined character for a
    # pair that only NULs kept apart, the chain returns its record
    # with the raw answer, and no stand-in is left running. Red until
    # review R-12 lands: a Grok or Muse step raised
    # UnicodeEncodeError with no record, and an opencode step failed
    # with its child left running.
    api = compose_api
    parts, expected = SURROGATE_CASES[case]
    first = steps.bind("opencode", label="halves", fake={"final_parts": parts})
    second = steps.bind(harness, label="next")
    result = await asyncio.wait_for(api.compose.chain_threads([first, second], "Answer was: {previous}", prompt=pack.PROMPT), pack.WAIT_SECONDS)
    living = [launch["pid"] for launch in sandbox.launches() if alive(launch["pid"])]
    assert result.failed_step is None and result.outcomes[1].ok, f"the {harness} step failed: {result.outcomes[1].error!r}"
    assert result.outcomes[0].text == "\n".join(parts), "the record keeps the raw answer"
    prompt = pack.launch_prompt(sandbox.only_launch("next"))
    assert prompt == "Answer was: " + expected, f"the {harness} step got {ascii(prompt)}"
    assert surrogate_points(prompt) == [] and NUL not in prompt
    assert living == [], f"stand-in processes still running after the chain returned: {living}"


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "muse"])
async def test_the_truncation_note_counts_an_answer_after_its_surrogate_repair(compose_api, sandbox, steps, pack, harness) -> None:
    # EC-80 / INV-18: a 30,004-character answer whose surrogate pair
    # only a NUL keeps apart is cut to fit a Grok or Muse step. The
    # note's omitted count is the length after the NUL is removed
    # and the pair joined, 30,002, minus the kept prefix. Red until
    # review R-12 lands: the step raised UnicodeEncodeError.
    api = compose_api
    first = steps.bind("opencode", label="long-halves", fake={"final_parts": [LONG_SURROGATE_ANSWER]})
    second = steps.bind(harness, label="after-long")
    result = await asyncio.wait_for(api.compose.chain_threads([first, second], "Answer: {previous}", prompt=pack.PROMPT), pack.WAIT_SECONDS)
    assert result.failed_step is None and result.outcomes[1].ok, f"the {harness} step failed: {result.outcomes[1].error!r}"
    assert result.outcomes[0].text == LONG_SURROGATE_ANSWER, "the record keeps the raw answer"
    prompt = pack.launch_prompt(sandbox.only_launch("after-long"))
    cap = api.threads_constants.NATIVE_ARGV_PROMPT_MAX_CHARS
    assert cap - 100 <= len(prompt) <= cap, f"the shortened prompt uses the room it has: {len(prompt)}"
    assert surrogate_points(prompt) == [] and NUL not in prompt
    run = max(re.finditer("x+", prompt), key=lambda match: len(match.group()))
    kept = len(run.group())
    note = pack.render("truncation_note", omitted=REPAIRED_LONG_CHARS - kept)
    assert prompt[run.end() :].lstrip().startswith(note), f"the note must count {REPAIRED_LONG_CHARS - kept} omitted characters: {ascii(prompt[run.end() :])}"
