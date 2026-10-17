"""FILE: tests/test_read_lines_window.py

PURPOSE: Proves the read window of spec infinite-memory-context-economy item 1: FileSystemToolConfig.max_read_lines caps the lines one read_lines call returns and ends a cut result with a footer naming the next start line, while a config without it reads to EOF exactly as on main. It also runs the spec's section 4 snippet as written.
ROLE IN CODEBASE: Root-level test of the shared filesystem piece (spec section 13: item 1 prior art is tests/test_filesystem_tools.py). Exercises vidbyte/lib/dataclasses/filesystem.py (LineLimit, FileSystemToolConfig) and vidbyte/tools/filesystem/read_lines.py on a real tmp folder.
ARCHITECTURE NOTE: Nothing is mocked. Every expected output is built from the file's own lines with the footer format of spec INV-1.2, and every "as on main" expectation is the literal main behavior (the description sentence, the metadata keys, the error texts), so the window cannot pass by changing both sides. Feature symbols are imported inside each test, so before the feature exists each test fails on its own.
FUNCTION INVENTORY: ReadWindowTests covers AC-1.1..AC-1.4, INV-1.1..INV-1.7 and the LineLimit refusals (AC-1.5, INV-1.5, INV-R.2); SectionFourSnippetTests runs AC-1 in a child process from an empty folder. _write_lines, _tool and _read are small builders.
COMMON MODIFICATION PATTERNS: Add a read case as one call on the 1,000-line file and compare with the slice of LINES it should return.
WHAT NOT TO DO IN THIS FILE: 1. Do not fake the filesystem or the backend. 2. Do not pin the window size with a literal anywhere but the explicit max_read_lines argument the test passes. 3. Do not edit the main-behavior literals to match a new implementation; INV-1.1 says they never change.
KNOWN EDGE CASES: The section 4 snippet writes notes/ relative to its working directory, so it runs in a child process whose cwd is a temporary folder. The footer uses plain integers, so "1000" never becomes "1,000".
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md sections 4, 6.1 (INV-1.x), 6.2 (AC-1, AC-1.x), 8.5.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_read_lines_window.py -q
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.types import ToolCall, ToolStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
# main's read_lines description and metadata keys (INV-1.1: unchanged without a window).
MAIN_DESCRIPTION = "Read a range of lines from a text file at the given path inside the configured root."
MAIN_METADATA_KEYS = {"path", "start", "end"}
WINDOW_METADATA_KEYS = MAIN_METADATA_KEYS | {"truncated", "total_lines", "next_start"}
# The spec's INV-1.7 sentence, with {limit:,} filled in by each test.
WINDOW_SENTENCE = " At most {limit:,} lines come back from one call; when more lines remain in the requested range, the result ends with a line naming the next start line."
LINES = [f"line {number}" for number in range(1, 1001)]
WINDOW = 200

# The section 4 snippet, verbatim.
SECTION_4_SNIPPET = '''
import asyncio
from pathlib import Path

from vidbyte import InfiniteRecallMode, InfiniteWorkspaceSettings
from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.tools.filesystem.read_lines import ReadLinesTool
from vidbyte.tools.types import ToolCall

notes = Path("notes")
notes.mkdir(exist_ok=True)
(notes / "long.md").write_text("\\n".join(f"line {n}" for n in range(1, 1001)), encoding="utf-8")

reader = ReadLinesTool(FileSystemToolConfig(root=notes, max_read_lines=200))
result = asyncio.run(reader.execute(ToolCall(tool_name="read_lines", arguments={"path": "long.md"})))
print(result.output.splitlines()[-1])
print(result.metadata["truncated"], result.metadata["total_lines"], result.metadata["next_start"])

workspace = InfiniteWorkspaceSettings(root="memory", recall_mode="delegated")
print(workspace.max_read_lines, workspace.recall_mode is InfiniteRecallMode.DELEGATED)
'''
SECTION_4_OUTPUT = "[lines 1-200 of 1000 shown; read on with start=201]\nTrue 1000 201\n200 True\n"


def _write_lines(root: Path, name: str, lines: list[str]) -> Path:
    # Writes the lines joined by "\n" with no trailing newline, as the section 4 snippet does.
    path = root / name
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path


def _tool(root: Path, **config: Any) -> Any:
    from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
    from vidbyte.tools.filesystem.read_lines import ReadLinesTool

    return ReadLinesTool(FileSystemToolConfig(root=root, **config))


def _read(tool: Any, **arguments: Any) -> Any:
    return asyncio.run(tool.execute(ToolCall("read_lines", arguments)))


def _footer(start: int, shown: int, total: int) -> str:
    # INV-1.2's footer, plain integers.
    return f"[lines {start}-{start + shown - 1} of {total} shown; read on with start={start + shown}]"


class ReadWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write_lines(self.root, "long.md", LINES)
        _write_lines(self.root, "short.md", LINES[:50])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_a_long_file_returns_the_window_then_a_footer_naming_the_next_start(self) -> None:
        # AC-1.1, INV-1.2, INV-1.4: only the path is given, so the requested range is the whole file and the first 200 lines come back.
        result = _read(_tool(self.root, max_read_lines=WINDOW), path="long.md")

        self.assertIs(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.output, "\n".join(LINES[:WINDOW]) + "\n" + _footer(1, WINDOW, 1000))
        self.assertEqual(result.output.splitlines()[-1], "[lines 1-200 of 1000 shown; read on with start=201]")
        self.assertEqual(set(result.metadata), WINDOW_METADATA_KEYS)
        self.assertEqual((result.metadata["truncated"], result.metadata["total_lines"], result.metadata["next_start"]), (True, 1000, 201))
        self.assertEqual((result.metadata["start"], result.metadata["end"]), (1, None))
        self.assertEqual(result.metadata["path"], _read(_tool(self.root), path="long.md").metadata["path"])

    def test_a_window_inside_the_file_and_a_too_long_end_are_cut_at_the_window(self) -> None:
        # INV-1.2: the range is start..min(end, total); a range longer than the window is cut and names start+N.
        tool = _tool(self.root, max_read_lines=WINDOW)
        middle = _read(tool, path="long.md", start=401)
        self.assertEqual(middle.output, "\n".join(LINES[400:600]) + "\n" + _footer(401, WINDOW, 1000))
        self.assertEqual((middle.metadata["truncated"], middle.metadata["next_start"], middle.metadata["end"]), (True, 601, None))
        bounded = _read(tool, path="long.md", start=1, end=500)
        self.assertEqual(bounded.output, "\n".join(LINES[:WINDOW]) + "\n" + _footer(1, WINDOW, 1000))
        self.assertEqual((bounded.metadata["end"], bounded.metadata["next_start"]), (500, 201))
        small = _read(_tool(self.root, max_read_lines=7), path="long.md", start=10)
        self.assertEqual(small.output, "\n".join(LINES[9:16]) + "\n" + _footer(10, 7, 1000))

    def test_a_range_within_the_window_is_identical_to_main_with_no_footer(self) -> None:
        # AC-1.2, INV-1.3: 50 lines, and exactly 200 lines, read as on main; truncated is False and next_start None.
        windowed = _tool(self.root, max_read_lines=WINDOW)
        plain = _tool(self.root)
        short = _read(windowed, path="short.md")
        self.assertEqual(short.output, "\n".join(LINES[:50]))
        self.assertEqual(short.output, _read(plain, path="short.md").output)
        self.assertEqual((short.metadata["truncated"], short.metadata["total_lines"], short.metadata["next_start"]), (False, 50, None))
        for arguments, expected in (({"start": 1, "end": WINDOW}, LINES[:WINDOW]), ({"start": 801}, LINES[800:])):
            with self.subTest(arguments=arguments):
                result = _read(windowed, path="long.md", **arguments)
                self.assertEqual(result.output, "\n".join(expected))
                self.assertEqual(result.output, _read(plain, path="long.md", **arguments).output)
                self.assertEqual((result.metadata["truncated"], result.metadata["next_start"]), (False, None))

    def test_a_range_running_past_the_end_returns_the_rest_without_a_footer(self) -> None:
        # AC-1.3: start=950, end=2000 is lines 950..1000, 51 lines, inside the window.
        result = _read(_tool(self.root, max_read_lines=WINDOW), path="long.md", start=950, end=2000)
        self.assertEqual(result.output, "\n".join(LINES[949:]))
        self.assertEqual((result.metadata["truncated"], result.metadata["total_lines"], result.metadata["next_start"], result.metadata["end"]), (False, 1000, None, 2000))

    def test_without_a_window_output_metadata_and_spec_equal_main(self) -> None:
        # AC-1.4, INV-1.1: None (given or omitted) reads to EOF, adds no metadata key, and keeps main's spec.
        for label, tool in (("omitted", _tool(self.root)), ("None", _tool(self.root, max_read_lines=None))):
            with self.subTest(max_read_lines=label):
                result = _read(tool, path="long.md")
                self.assertEqual(result.output, "\n".join(LINES))
                self.assertEqual(set(result.metadata), MAIN_METADATA_KEYS)
                self.assertEqual((result.metadata["start"], result.metadata["end"]), (1, None))
                spec = tool.spec()
                self.assertEqual(spec.description, MAIN_DESCRIPTION)
                self.assertEqual([parameter.name for parameter in spec.parameters], ["path", "start", "end"])

    def test_the_window_adds_exactly_one_sentence_naming_the_limit_to_the_spec(self) -> None:
        # INV-1.7: main's sentence, then the limit sentence with a thousands separator; parameters unchanged.
        for limit in (WINDOW, 1500):
            with self.subTest(limit=limit):
                spec = _tool(self.root, max_read_lines=limit).spec()
                self.assertEqual(spec.description, MAIN_DESCRIPTION + WINDOW_SENTENCE.format(limit=limit))
                self.assertEqual([parameter.name for parameter in spec.parameters], ["path", "start", "end"])
                self.assertEqual(spec.parameters, _tool(self.root).spec().parameters)

    def test_errors_and_a_start_past_the_end_are_unchanged_with_a_window(self) -> None:
        # INV-1.6, EC-1.4: start past EOF is an empty success with no footer; bad bounds and a missing file keep main's errors.
        windowed = _tool(self.root, max_read_lines=WINDOW)
        past = _read(windowed, path="long.md", start=1001)
        self.assertIs(past.status, ToolStatus.SUCCESS)
        self.assertEqual(past.output, "")
        self.assertEqual((past.metadata["truncated"], past.metadata["next_start"]), (False, None))
        for arguments, text in (({"start": 0}, "ReadLinesTool start must be at least 1."), ({"start": 3, "end": 1}, "ReadLinesTool end must be greater than or equal to start.")):
            with self.subTest(arguments=arguments):
                result = _read(windowed, path="long.md", **arguments)
                self.assertIs(result.status, ToolStatus.ERROR)
                self.assertIn(text, result.output)
        missing = _read(windowed, path="absent.md")
        self.assertIs(missing.status, ToolStatus.ERROR)
        self.assertEqual(missing.output, _read(_tool(self.root), path="absent.md").output)

    def test_a_bad_window_is_refused_naming_the_field(self) -> None:
        # AC-1.5, INV-1.5, EC-1.3: a bool, a non-int, or a value below 1 is refused with the shared LineLimit text.
        from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig

        for bad in (0, -1, True, 2.5, "200"):
            with self.subTest(max_read_lines=bad):
                with self.assertRaises(ConfigurationError) as caught:
                    FileSystemToolConfig(root=self.root, max_read_lines=bad)
                self.assertIn("max_read_lines must be None or an int of at least 1.", str(caught.exception))
        for good in (1, WINDOW):
            self.assertEqual(FileSystemToolConfig(root=self.root, max_read_lines=good).max_read_lines, good)

    def test_line_limit_validates_both_caps_with_the_same_refusal_text(self) -> None:
        # FR-1.2, INV-R.2: the renamed record keeps the overwrite text and serves the read window too.
        from vidbyte.lib.dataclasses.filesystem import LineLimit

        for parameter in ("max_overwrite_lines", "max_read_lines"):
            for bad in (0, True, 2.5):
                with self.subTest(parameter=parameter, bad=bad):
                    with self.assertRaises(ConfigurationError) as caught:
                        LineLimit(bad, parameter)
                    self.assertIn(f"{parameter} must be None or an int of at least 1.", str(caught.exception))
            self.assertIsNone(LineLimit(None, parameter).lines)
            self.assertEqual(LineLimit(3, parameter).lines, 3)


class SectionFourSnippetTests(unittest.TestCase):
    def test_section_4_snippet_prints_exactly_the_three_documented_lines(self) -> None:
        # AC-1: the snippet runs as written from an empty folder of a clean checkout and prints the three lines of section 4.
        with TemporaryDirectory() as tmp:
            env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (str(REPO_ROOT), os.environ.get("PYTHONPATH"))))}
            completed = subprocess.run([sys.executable, "-c", SECTION_4_SNIPPET], cwd=tmp, env=env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertEqual(completed.stdout, SECTION_4_OUTPUT)


if __name__ == "__main__":
    unittest.main()
