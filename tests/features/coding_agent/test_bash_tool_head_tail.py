"""FILE: tests/features/coding_agent/test_bash_tool_head_tail.py

PURPOSE: Prove item 6 of spec infinite-memory-context-economy: a bash output over the cap keeps its first H and its last T bytes with the omitted count between them, an output within the cap is byte-identical to main (a character straddling the head/tail edge included), a timeout shows the head, the counted marker only when bytes were left out, the tail, and the stopped line, and the bash spec says so.
ROLE IN CODEBASE: Calls vidbyte.tools.builtins.bash.BashTool directly with real bash subprocesses (Linux bash in CI, Git for Windows bash on Windows hosts), like test_bash_tool_contract.py.
ARCHITECTURE NOTE: Each command prints a file of known bytes written by the test (cat), so every expected output is computed from those bytes and the spec formula, never captured from the tool. H and T follow INV-6.2: T = min(BASH_TAIL_OUTPUT_BYTES, BASH_MAX_OUTPUT_BYTES // 2), H = BASH_MAX_OUTPUT_BYTES - T. BASH_MAX_OUTPUT_BYTES, BASH_TAIL_OUTPUT_BYTES, BASH_TIMEOUT_SECONDS and BASH_KILL_GRACE_SECONDS are patched as module globals, which INV-6.5 and spec section 13 allow.
FUNCTION INVENTORY: _head_tail (the INV-6.2 split); _expected_long (the INV-6.2 success text); _known_bytes (numbered lines of an exact length); test_sixty_thousand_bytes_* (AC-6.1, INV-6.2); test_small_caps_* (AC-6.5, EC-6.2, INV-6.5); test_one_byte_over_* (INV-6.2 boundary); test_output_within_the_cap_* (AC-6.3, INV-6.1); test_timeout_after_exactly_the_cap_* (AC-6.4, INV-6.4, EC-6.3); test_timeout_after_more_than_the_cap_* (INV-6.4, EC-6.3); test_bash_constants_* (INV-6.5); test_bash_spec_* (INV-6.6).
COMMON MODIFICATION PATTERNS: A new size case writes a file of known bytes, cats it, and compares the whole output with _expected_long or the main shape.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare against a second BashTool's output; the spec formula over known bytes is the oracle. 2. Do not use yes or /dev/zero for exact-content cases; they cannot show which bytes were kept. 3. Do not add a timing assertion; the bounds belong to test_bash_tool_process_bounds.py.
KNOWN EDGE CASES: On Windows only Git's launcher is killed at a timeout (EC-14), so the sleeping command outlives the test by a few seconds; every printed byte was read before the limit, so the result is the same on every OS.
RELATED DOCS: tests/features/coding_agent/FEATURE.md; docs/spec/infinite-memory-context-economy/spec.md (section 6.1 INV-6.1 to INV-6.6; section 6.2 AC-6.1 to AC-6.5; section 7 EC-6.1 to EC-6.3; section 8.5 bash)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_bash_tool_head_tail.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vidbyte.tools.types import ToolCall, ToolStatus

TIME_LIMIT_SECONDS = 2.0  # patched over BASH_TIMEOUT_SECONDS
KILL_GRACE_SECONDS = 1.0  # patched over BASH_KILL_GRACE_SECONDS
OUTLIVES_SECONDS = 8  # past the patched limit, and short enough that a Windows orphan dies soon (EC-14)
SMALL_CAP_BYTES = 1000  # the cap test_bash_tool_process_bounds.py patches (EC-6.2)


def _bash_call(command: str) -> ToolCall:
    return ToolCall("bash", {"command": command})


def _head_tail(bash_module) -> tuple[int, int]:
    # INV-6.2: T = min(BASH_TAIL_OUTPUT_BYTES, BASH_MAX_OUTPUT_BYTES // 2), H = BASH_MAX_OUTPUT_BYTES - T, read at call time.
    tail = min(bash_module.BASH_TAIL_OUTPUT_BYTES, bash_module.BASH_MAX_OUTPUT_BYTES // 2)
    return bash_module.BASH_MAX_OUTPUT_BYTES - tail, tail


def _expected_long(data: bytes, head: int, tail: int) -> str:
    # INV-6.2 before the exit-code line: the first H bytes, the counted marker, the last T bytes.
    omitted = len(data) - head - tail
    return data[:head].decode("utf-8") + f"\n[output truncated: {omitted:,} bytes not shown]\n" + data[-tail:].decode("utf-8")


def _known_bytes(size: int) -> bytes:
    # Numbered 12-byte lines cut to exactly size bytes, so every kept byte says where it came from.
    lines = b"".join(f"line {n:06d}\n".encode("ascii") for n in range(size // 12 + 1))
    return lines[:size]


def _write(tmp_path: Path, name: str, data: bytes) -> str:
    (tmp_path / name).write_bytes(data)
    return name


def _stopped_line(bash_module) -> str:
    # main's stopped line, unchanged by INV-6.4.
    return f"\n[command stopped: it did not finish within the {bash_module.BASH_TIMEOUT_SECONDS:g}-second time limit]"


@pytest.mark.asyncio
async def test_sixty_thousand_bytes_keep_the_first_and_last_25000_with_10000_counted_between(bash_module, tmp_path) -> None:
    # AC-6.1 / INV-6.2: 60,000 known bytes, exit 1; the head, the marker, the tail, then the exit code.
    data = _known_bytes(60_000)
    head, tail = _head_tail(bash_module)
    assert (head, tail) == (25_000, 25_000)

    result = await bash_module.BashTool(tmp_path).execute(_bash_call(f"cat {_write(tmp_path, 'data.bin', data)}; exit 1"))

    assert result.status is ToolStatus.SUCCESS
    assert result.output == data[:25_000].decode("ascii") + "\n[output truncated: 10,000 bytes not shown]\n" + data[-25_000:].decode("ascii") + "\nexit code: 1"
    assert result.metadata == {"exit_code": 1, "truncated": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("max_bytes", "tail_bytes", "expected_split"),
    [
        (SMALL_CAP_BYTES, None, (500, 500)),  # AC-6.5 / EC-6.2: a cap below BASH_TAIL_OUTPUT_BYTES still keeps a head and a tail
        (1001, None, (501, 500)),  # an odd cap: H >= T
        (SMALL_CAP_BYTES, 100, (900, 100)),  # section 13: both constants patched, read at call time (INV-6.5)
    ],
)
async def test_small_caps_split_into_a_head_and_a_tail_by_the_spec_formula(bash_module, tmp_path, monkeypatch, max_bytes, tail_bytes, expected_split) -> None:
    # AC-6.5 / EC-6.2 / INV-6.2 / INV-6.5: 5,000 known bytes under a patched cap, exit 0.
    monkeypatch.setattr(bash_module, "BASH_MAX_OUTPUT_BYTES", max_bytes)
    if tail_bytes is not None:
        monkeypatch.setattr(bash_module, "BASH_TAIL_OUTPUT_BYTES", tail_bytes)
    data = _known_bytes(5_000)
    head, tail = _head_tail(bash_module)
    assert (head, tail) == expected_split

    result = await bash_module.BashTool(tmp_path).execute(_bash_call(f"cat {_write(tmp_path, 'data.bin', data)}; exit 0"))

    assert result.output == _expected_long(data, head, tail) + "\nexit code: 0"
    assert result.metadata == {"exit_code": 0, "truncated": True}
    if (max_bytes, tail_bytes) == (SMALL_CAP_BYTES, None):
        # AC-6.5 verbatim: the first 500 bytes, 4,000 counted, the last 500.
        assert result.output == data[:500].decode("ascii") + "\n[output truncated: 4,000 bytes not shown]\n" + data[-500:].decode("ascii") + "\nexit code: 0"


@pytest.mark.asyncio
async def test_one_byte_over_the_cap_keeps_a_head_and_a_tail_with_one_byte_counted(bash_module, tmp_path) -> None:
    # INV-6.2 boundary: H + T + 1 bytes is the smallest output that is cut; exactly one byte is left out.
    head, tail = _head_tail(bash_module)
    data = _known_bytes(head + tail + 1)

    result = await bash_module.BashTool(tmp_path).execute(_bash_call(f"cat {_write(tmp_path, 'data.bin', data)}"))

    assert result.output == data[:head].decode("ascii") + "\n[output truncated: 1 bytes not shown]\n" + data[-tail:].decode("ascii") + "\nexit code: 0"
    assert result.metadata == {"exit_code": 0, "truncated": True}


@pytest.mark.asyncio
async def test_output_within_the_cap_equals_main_even_with_a_character_across_the_head_tail_edge(bash_module, tmp_path) -> None:
    # AC-6.3 / INV-6.1: 1,000 bytes, and exactly the cap with a two-byte character at bytes H-1..H, both come back as main renders them.
    head, tail = _head_tail(bash_module)
    small = ("Plans overview\n" * 67).encode("ascii")[:1_000]
    assert len(small) == 1_000
    straddling = b"a" * (head - 1) + "é".encode("utf-8") + b"b" * (tail - 1)
    assert len(straddling) == bash_module.BASH_MAX_OUTPUT_BYTES
    tool = bash_module.BashTool(tmp_path)

    for name, data in (("small.txt", small), ("cap.txt", straddling)):
        result = await tool.execute(_bash_call(f"cat {_write(tmp_path, name, data)}"))
        # main's success shape: the decoded output, no note, then the exit code.
        assert result.output == data.decode("utf-8") + "\nexit code: 0", name
        assert result.metadata == {"exit_code": 0, "truncated": False}, name
    assert "�" not in result.output


@pytest.mark.asyncio
async def test_timeout_after_exactly_the_cap_shows_every_byte_then_the_stopped_line_and_no_marker(bash_module, tmp_path, monkeypatch) -> None:
    # AC-6.4 / INV-6.4 / EC-6.3: exactly BASH_MAX_OUTPUT_BYTES printed, then the command sleeps past the patched limit.
    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", TIME_LIMIT_SECONDS)
    monkeypatch.setattr(bash_module, "BASH_KILL_GRACE_SECONDS", KILL_GRACE_SECONDS)
    head, tail = _head_tail(bash_module)
    # The two-byte character straddles the head/tail edge, so the joined decode of INV-6.4 is checked as well.
    data = b"a" * (head - 1) + "é".encode("utf-8") + b"b" * (tail - 1)
    assert len(data) == bash_module.BASH_MAX_OUTPUT_BYTES

    result = await bash_module.BashTool(tmp_path).execute(_bash_call(f"cat {_write(tmp_path, 'cap.bin', data)}; sleep {OUTLIVES_SECONDS}"))

    assert result.status is ToolStatus.ERROR
    assert result.output == data.decode("utf-8") + _stopped_line(bash_module)
    assert result.metadata == {"error": "timeout", "truncated": False}


@pytest.mark.asyncio
async def test_timeout_after_more_than_the_cap_shows_the_head_the_count_so_far_the_tail_and_the_stopped_line(bash_module, tmp_path, monkeypatch) -> None:
    # INV-6.4 / EC-6.3: 5,000 known bytes under a 1,000-byte cap, then a sleep past the limit; the count left out survives the timeout.
    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", TIME_LIMIT_SECONDS)
    monkeypatch.setattr(bash_module, "BASH_KILL_GRACE_SECONDS", KILL_GRACE_SECONDS)
    monkeypatch.setattr(bash_module, "BASH_MAX_OUTPUT_BYTES", SMALL_CAP_BYTES)
    data = _known_bytes(5_000)
    head, tail = _head_tail(bash_module)

    result = await bash_module.BashTool(tmp_path).execute(_bash_call(f"cat {_write(tmp_path, 'data.bin', data)}; sleep {OUTLIVES_SECONDS}"))

    assert result.status is ToolStatus.ERROR
    assert result.output == _expected_long(data, head, tail) + _stopped_line(bash_module)
    assert "[output truncated: 4,000 bytes not shown]" in result.output
    assert result.metadata == {"error": "timeout", "truncated": True}


def test_bash_constants_keep_their_values_and_the_tail_constant_is_25000(bash_module) -> None:
    # INV-6.5 / FR-6.1: the four main constants are unchanged and BASH_TAIL_OUTPUT_BYTES is new.
    bounds = (bash_module.BASH_TIMEOUT_SECONDS, bash_module.BASH_MAX_OUTPUT_BYTES, bash_module.BASH_READ_CHUNK_BYTES, bash_module.BASH_KILL_GRACE_SECONDS)
    assert bounds == (600.0, 50_000, 65_536, 5.0)
    assert bash_module.BASH_TAIL_OUTPUT_BYTES == 25_000


def test_bash_spec_rewords_one_sentence_to_say_the_first_and_last_bytes_are_kept_and_the_rest_counted(bash_module, tmp_path) -> None:
    # INV-6.6 / section 10: only the sentence about what is kept changes; it names the first and the last bytes and the count of the rest.
    cap = f"{bash_module.BASH_MAX_OUTPUT_BYTES:,}"
    main_reworded = f"only the first {cap} bytes are kept"
    unchanged = (
        "Runs one command in a fresh bash process that starts in the agent's root folder with standard input closed, and returns what the command printed.",
        "Changes of directory and shell variables do not carry over from one call to the next, and the command is not confined to the root folder.",
        f"When the command finishes, its exit code is the last line of the result; a command still running after {bash_module.BASH_TIMEOUT_SECONDS:g} seconds is stopped instead, except that on Windows only Git's bash launcher is stopped and the command itself may keep running.",
        "A background process must redirect both its standard output and its standard error to a file, otherwise the call waits for the time limit and the process is killed.",
    )
    description = bash_module.BashTool(tmp_path).spec().description

    assert main_reworded not in description
    remainder = description
    for sentence in unchanged:
        assert sentence in description, sentence
        remainder = remainder.replace(sentence, "")
    reworded = remainder.strip().lower()
    assert "first" in reworded and "last" in reworded, reworded
    assert "count" in reworded or "number" in reworded, reworded
