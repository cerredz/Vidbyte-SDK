from __future__ import annotations

import asyncio
import base64
import json
import os
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vidbyte.lib.tools.filesystem import FileSystemPermissions
from vidbyte.lib.tools.filesystem.backends.local import LocalFileSystemBackend
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.catalog import Tools
from vidbyte.tools.filesystem import (
    AppendTool,
    ChecksumTool,
    CopyTool,
    DeleteTool,
    DiffTool,
    ExistsTool,
    FileSystemToolConfig,
    FindTool,
    ListDirTool,
    MakeDirTool,
    MoveTool,
    ReadBinaryTool,
    ReadLinesTool,
    ReadTextTool,
    ReplaceTextTool,
    StatTool,
    TouchTool,
    TreeTool,
    UnzipTool,
    WriteTextTool,
    ZipTool,
)
from vidbyte.tools.filesystem._base_tool import EDIT_DIFF_MAX_LINES
from vidbyte.tools.types import ToolCall, ToolStatus


def run(coro):
    return asyncio.run(coro)


class FileSystemToolRegistrationTests(unittest.TestCase):
    def test_all_tools_are_base_tool_instances(self) -> None:
        from vidbyte.tools.base import BaseTool
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            tools = [
                WriteTextTool(config), ReadTextTool(config), AppendTool(config),
                ChecksumTool(config), CopyTool(config), DeleteTool(config),
                DiffTool(config), ExistsTool(config), FindTool(config),
                ListDirTool(config), MakeDirTool(config), MoveTool(config),
                ReadBinaryTool(config), ReadLinesTool(config), ReplaceTextTool(config),
                StatTool(config), TouchTool(config), TreeTool(config),
                UnzipTool(config), ZipTool(config),
            ]
            for tool in tools:
                self.assertIsInstance(tool, BaseTool, f"{type(tool).__name__} is not a BaseTool")

    def test_filesystem_tools_register_in_catalog_without_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            catalog = Tools([WriteTextTool(config), ReadTextTool(config), ExistsTool(config)])
            self.assertIn("write_text", catalog.names())
            self.assertIn("read_text", catalog.names())
            self.assertIn("exists", catalog.names())

    def test_all_tool_spec_names_are_unique(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            all_tools = [
                WriteTextTool(config), ReadTextTool(config), AppendTool(config),
                ChecksumTool(config), CopyTool(config), DeleteTool(config),
                DiffTool(config), ExistsTool(config), FindTool(config),
                ListDirTool(config), MakeDirTool(config), MoveTool(config),
                ReadBinaryTool(config), ReadLinesTool(config), ReplaceTextTool(config),
                StatTool(config), TouchTool(config), TreeTool(config),
                ZipTool(config), UnzipTool(config),
            ]
            names = [t.spec().name for t in all_tools]
            self.assertEqual(len(names), len(set(names)), f"Duplicate tool names: {names}")

    def test_catalog_does_not_wrap_tools_in_spec_only_adapter(self) -> None:
        from vidbyte.tools.catalog import _SpecOnlyTool
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            catalog = Tools([WriteTextTool(config)])
            self.assertNotIsInstance(catalog[0], _SpecOnlyTool)


class FileSystemToolHappyPathTests(unittest.TestCase):
    def test_write_and_read_text(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(MakeDirTool(config).execute(ToolCall("make_dir", {"path": "nested"})))
            result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "nested/file.txt", "content": "hello"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            read = run(ReadTextTool(config).execute(ToolCall("read_text", {"path": "nested/file.txt"})))
            self.assertEqual(read.status, ToolStatus.SUCCESS)
            self.assertEqual(read.output, "hello")

    def test_list_dir_returns_newline_joined_entries(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(MakeDirTool(config).execute(ToolCall("make_dir", {"path": "nested"})))
            result = run(ListDirTool(config).execute(ToolCall("list_dir", {"path": "."})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.output, "nested/")

    def test_exists_returns_true_string_for_existing_path(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "x"})))
            result = run(ExistsTool(config).execute(ToolCall("exists", {"path": "f.txt"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.output, "true")

    def test_exists_returns_false_string_for_missing_path(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            result = run(ExistsTool(config).execute(ToolCall("exists", {"path": "missing.txt"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.output, "false")

    def test_read_binary_returns_base64_encoded_output(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "binary.bin", "content": "data"})))
            result = run(ReadBinaryTool(config).execute(ToolCall("read_binary", {"path": "binary.bin"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(base64.b64decode(result.output), b"data")

    def test_stat_returns_json_with_exists_true_for_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "x"})))
            result = run(StatTool(config).execute(ToolCall("stat", {"path": "f.txt"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            parsed = json.loads(result.output)
            self.assertTrue(parsed["exists"])
            self.assertTrue(parsed["is_file"])

    def test_stat_returns_json_with_exists_false_for_missing_path(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            result = run(StatTool(config).execute(ToolCall("stat", {"path": "missing.txt"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            parsed = json.loads(result.output)
            self.assertFalse(parsed["exists"])

    def test_find_returns_newline_joined_matches(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(MakeDirTool(config).execute(ToolCall("make_dir", {"path": "sub"})))
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "sub/a.txt", "content": "x"})))
            result = run(FindTool(config).execute(ToolCall("find", {"pattern": "*.txt", "root": "sub"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.output, "a.txt")

    def test_find_returns_empty_string_when_no_matches(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            result = run(FindTool(config).execute(ToolCall("find", {"pattern": "*.xyz"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.output, "")

    def test_checksum_returns_64_char_hex_digest(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "hello"})))
            result = run(ChecksumTool(config).execute(ToolCall("checksum", {"path": "f.txt"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(len(result.output), 64)

    def test_diff_returns_nonempty_string_when_content_differs(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "one\ntwo\n"})))
            result = run(DiffTool(config).execute(ToolCall("diff", {"path": "f.txt", "content": "one\ntwo\nthree\n"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertIn("+three", result.output)

    def test_replace_text_modifies_file_when_search_appears_once(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "hello world"})))
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.txt", "search": "world", "replacement": "there"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            read = run(ReadTextTool(config).execute(ToolCall("read_text", {"path": "f.txt"})))
            self.assertEqual(read.output, "hello there")

    def test_replace_text_preserves_lf_line_endings(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            target = Path(tmp) / "f.py"
            target.write_bytes(b"def f():\n    x = 1\n    return 2\n\nprint(f())\n")
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.py", "search": "return 2", "replacement": "return 3"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(target.read_bytes(), b"def f():\n    x = 1\n    return 3\n\nprint(f())\n")

    def test_replace_text_preserves_crlf_line_endings(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            target = Path(tmp) / "f.py"
            target.write_bytes(b"def f():\r\n    x = 1\r\n    return 2\r\n\r\nprint(f())\r\n")
            call = ToolCall("replace_text", {"path": "f.py", "search": "    x = 1\n    return 2\n", "replacement": "    x = 1\n    return 3\n"})
            result = run(ReplaceTextTool(config).execute(call))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(target.read_bytes(), b"def f():\r\n    x = 1\r\n    return 3\r\n\r\nprint(f())\r\n")

    def test_write_text_over_existing_file_keeps_its_line_endings(self) -> None:
        # Replacing a file must not flip every line to the platform default,
        # whichever style the file already uses and whatever OS runs the test.
        for old, new in ((b"a = 1\nb = 2\nc = 3\n", b"a = 1\nb = 22\nc = 3\n"), (b"a = 1\r\nb = 2\r\nc = 3\r\n", b"a = 1\r\nb = 22\r\nc = 3\r\n")):
            with self.subTest(old=old), TemporaryDirectory() as tmp:
                config = FileSystemToolConfig(root=tmp, allow_write=True)
                target = Path(tmp) / "f.py"
                target.write_bytes(old)
                result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.py", "content": "a = 1\nb = 22\nc = 3\n"})))
                self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
                self.assertEqual(target.read_bytes(), new)

    def test_write_text_with_crlf_spelled_content_keeps_file_line_endings(self) -> None:
        # @intent model-crlf-text-keeps-file-endings
        # Content the model spells with CRLF lands in the file's own endings once:
        # a CRLF file never gets CR CR LF, and an LF file stays LF.
        for old, new in ((b"a = 1\r\nb = 2\r\n", b"a = 1\r\nb = 22\r\n"), (b"a = 1\nb = 2\n", b"a = 1\nb = 22\n")):
            with self.subTest(old=old), TemporaryDirectory() as tmp:
                config = FileSystemToolConfig(root=tmp, allow_write=True)
                target = Path(tmp) / "f.txt"
                target.write_bytes(old)
                result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "a = 1\r\nb = 22\r\n"})))
                self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
                self.assertEqual(target.read_bytes(), new)
                self.assertNotIn("-a = 1", result.output)

    def test_replace_text_with_crlf_spelled_search_and_replacement_on_crlf_file(self) -> None:
        # @intent model-crlf-text-keeps-file-endings
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            target = Path(tmp) / "f.ini"
            target.write_bytes(b"[a]\r\nx=1\r\ny=2\r\n")
            call = ToolCall("replace_text", {"path": "f.ini", "search": "[a]\r\nx=1", "replacement": "[a]\r\nx=10\r\nz=3"})
            result = run(ReplaceTextTool(config).execute(call))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(target.read_bytes(), b"[a]\r\nx=10\r\nz=3\r\ny=2\r\n")

    def test_write_text_over_non_utf8_crlf_file_still_writes_and_keeps_crlf(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            target = Path(tmp) / "f.txt"
            target.write_bytes(b"caf\xe9\r\nbar\r\n")
            result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "café\nbar\n"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(result.output.split("\n")[1], "no diff: the old file is not valid utf-8 text")
            self.assertEqual(target.read_bytes(), "café\r\nbar\r\n".encode("utf-8"))

    def test_tree_returns_newline_joined_tree_entries(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(MakeDirTool(config).execute(ToolCall("make_dir", {"path": "sub"})))
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "sub/f.txt", "content": "x"})))
            result = run(TreeTool(config).execute(ToolCall("tree", {"path": "."})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertIn("sub/f.txt", result.output)

    def test_zip_and_unzip_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(MakeDirTool(config).execute(ToolCall("make_dir", {"path": "src"})))
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "src/file.txt", "content": "zip me"})))
            zip_result = run(ZipTool(config).execute(ToolCall("zip", {"source": "src", "destination": "out.zip"})))
            self.assertEqual(zip_result.status, ToolStatus.SUCCESS)
            self.assertTrue(zip_result.output.endswith("out.zip"))
            unzip_result = run(UnzipTool(config).execute(ToolCall("unzip", {"source": "out.zip", "destination": "extracted"})))
            self.assertEqual(unzip_result.status, ToolStatus.SUCCESS)
            self.assertIn("src/file.txt", unzip_result.output)

    def test_read_lines_returns_selected_lines_newline_joined(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "a\nb\nc"})))
            result = run(ReadLinesTool(config).execute(ToolCall("read_lines", {"path": "f.txt", "start": 2})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.output, "b\nc")

    def test_read_lines_numbers_a_form_feed_line_as_one_line(self) -> None:
        # A ^L page break line is one line on disk, as in grep -n and the
        # edit diffs, and the text read back is exact enough to edit with.
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.c").write_text("int a;\n\f\nint b;\nint c;\n", encoding="utf-8")
            line4 = run(ReadLinesTool(config).execute(ToolCall("read_lines", {"path": "f.c", "start": 4, "end": 4})))
            self.assertEqual(line4.output, "int c;")
            head = run(ReadLinesTool(config).execute(ToolCall("read_lines", {"path": "f.c", "start": 1, "end": 3})))
            self.assertEqual(head.output, "int a;\n\f\nint b;")
            edit = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.c", "search": head.output, "replacement": "int z;"})))
            self.assertEqual(edit.status, ToolStatus.SUCCESS, edit.output)

    def test_read_lines_drops_crlf_endings(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.txt").write_bytes(b"a\r\nb\r\nc")
            result = run(ReadLinesTool(config).execute(ToolCall("read_lines", {"path": "f.txt"})))
            self.assertEqual(result.output, "a\nb\nc")

    def test_read_lines_returns_empty_output_when_start_beyond_eof(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "one"})))
            result = run(ReadLinesTool(config).execute(ToolCall("read_lines", {"path": "f.txt", "start": 99})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.output, "")

    def test_tree_respects_max_entries_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            for i in range(10):
                run(WriteTextTool(config).execute(ToolCall("write_text", {"path": f"f{i}.txt", "content": "x"})))
            result = run(TreeTool(config).execute(ToolCall("tree", {"path": ".", "max_entries": 3})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(len(result.output.splitlines()), 3)
            self.assertTrue(result.metadata["truncated"])

    def test_tree_not_truncated_when_entries_exactly_fill_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            for i in range(3):
                run(WriteTextTool(config).execute(ToolCall("write_text", {"path": f"f{i}.txt", "content": "x"})))
            result = run(TreeTool(config).execute(ToolCall("tree", {"path": ".", "max_entries": 3})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(len(result.output.splitlines()), 3)
            self.assertFalse(result.metadata["truncated"])

    def test_list_dir_returns_empty_string_for_empty_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(MakeDirTool(config).execute(ToolCall("make_dir", {"path": "empty"})))
            result = run(ListDirTool(config).execute(ToolCall("list_dir", {"path": "empty"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.output, "")

    def test_append_then_read(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "one"})))
            run(AppendTool(config).execute(ToolCall("append_text", {"path": "f.txt", "content": "\ntwo"})))
            result = run(ReadTextTool(config).execute(ToolCall("read_text", {"path": "f.txt"})))
            self.assertIn("two", result.output)

    def test_append_text_keeps_existing_file_line_endings(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            for name, initial, expected in (("lf.txt", b"a\nb\n", b"a\nb\nc\n"), ("crlf.txt", b"a\r\nb\r\n", b"a\r\nb\r\nc\r\n")):
                target = Path(tmp) / name
                target.write_bytes(initial)
                result = run(AppendTool(config).execute(ToolCall("append_text", {"path": name, "content": "c\n"})))
                self.assertEqual(result.status, ToolStatus.SUCCESS)
                self.assertEqual(target.read_bytes(), expected, name)

    def test_append_text_with_crlf_spelled_content_keeps_file_line_endings(self) -> None:
        # @intent model-crlf-text-keeps-file-endings
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            for name, initial, expected in (("lf.txt", b"a\n", b"a\nb\nc\n"), ("crlf.txt", b"a\r\n", b"a\r\nb\r\nc\r\n")):
                target = Path(tmp) / name
                target.write_bytes(initial)
                result = run(AppendTool(config).execute(ToolCall("append_text", {"path": name, "content": "b\r\nc\r\n"})))
                self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
                self.assertEqual(target.read_bytes(), expected, name)

    def test_append_text_tolerates_undecodable_bytes_in_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            target = Path(tmp) / "app.log"
            target.write_bytes(b"start\ncrash \xff dump\n")
            result = run(AppendTool(config).execute(ToolCall("append_text", {"path": "app.log", "content": "status: ok\n"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(target.read_bytes(), b"start\ncrash \xff dump\nstatus: ok\n")

    def test_copy_then_move(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "a.txt", "content": "x"})))
            run(CopyTool(config).execute(ToolCall("copy", {"source": "a.txt", "destination": "b.txt"})))
            run(MoveTool(config).execute(ToolCall("move", {"source": "b.txt", "destination": "sub/c.txt"})))
            result = run(ExistsTool(config).execute(ToolCall("exists", {"path": "sub/c.txt"})))
            self.assertEqual(result.output, "true")
            gone = run(ExistsTool(config).execute(ToolCall("exists", {"path": "b.txt"})))
            self.assertEqual(gone.output, "false")

    def test_move_performs_case_only_rename_when_resolve_canonicalizes_case(self) -> None:
        # Simulate Windows, where resolve() of an existing entry returns its on-disk spelling.
        original = FileSystemPermissions.resolve_scoped_path

        def canonical_case(config: FileSystemToolConfig, path: str | Path) -> Path:
            resolved = original(config, path)
            if resolved.parent.is_dir():
                for entry in resolved.parent.iterdir():
                    if entry.name.casefold() == resolved.name.casefold():
                        return entry
            return resolved

        with TemporaryDirectory() as tmp, patch.object(FileSystemPermissions, "resolve_scoped_path", side_effect=canonical_case):
            root = Path(tmp)
            (root / "Readme.md").write_text("r")
            (root / "Src").mkdir()
            (root / "a.txt").write_text("a")
            tool = MoveTool(FileSystemToolConfig(root=tmp, allow_write=True))
            file_result = run(tool.execute(ToolCall("move", {"source": "Readme.md", "destination": "README.md"})))
            dir_result = run(tool.execute(ToolCall("move", {"source": "Src", "destination": "src"})))
            other_result = run(tool.execute(ToolCall("move", {"source": "a.txt", "destination": "b.txt"})))
            same_result = run(tool.execute(ToolCall("move", {"source": "b.txt", "destination": "b.txt"})))
            for result in (file_result, dir_result, other_result, same_result):
                self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(Path(file_result.output).name, "README.md")
            self.assertEqual(Path(dir_result.output).name, "src")
            self.assertEqual(Path(same_result.output).name, "b.txt")
            self.assertEqual(sorted(os.listdir(tmp)), ["README.md", "b.txt", "src"])

    def test_delete_then_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "del.txt", "content": "bye"})))
            run(DeleteTool(config).execute(ToolCall("delete", {"path": "del.txt"})))
            result = run(ExistsTool(config).execute(ToolCall("exists", {"path": "del.txt"})))
            self.assertEqual(result.output, "false")

    def test_touch_creates_file_and_parents(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            result = run(TouchTool(config).execute(ToolCall("touch", {"path": "deep/new.txt", "create_parents": True})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            exists = run(ExistsTool(config).execute(ToolCall("exists", {"path": "deep/new.txt"})))
            self.assertEqual(exists.output, "true")


def test_copy_refuses_to_copy_a_directory_into_itself(tmp_path: Path) -> None:
    (tmp_path / "handbook" / "sub").mkdir(parents=True)
    (tmp_path / "handbook" / "a.md").write_text("a")
    (tmp_path / "handbook" / "sub" / "b.md").write_text("b")
    tool = CopyTool(FileSystemToolConfig(root=str(tmp_path), allow_write=True))
    into_subfolder = run(tool.execute(ToolCall("copy", {"source": "handbook", "destination": "handbook/archive/today"})))
    assert into_subfolder.status == ToolStatus.ERROR
    assert "Cannot copy a directory into itself" in into_subfolder.output
    assert not (tmp_path / "handbook" / "archive").exists()
    root_into_subfolder = run(tool.execute(ToolCall("copy", {"source": ".", "destination": "backups/x"})))
    assert root_into_subfolder.status == ToolStatus.ERROR
    assert "Cannot copy a directory into itself" in root_into_subfolder.output
    assert not (tmp_path / "backups").exists()
    sibling = run(tool.execute(ToolCall("copy", {"source": "handbook", "destination": "handbook_copy"})))
    assert sibling.status == ToolStatus.SUCCESS, sibling.output
    assert (tmp_path / "handbook_copy" / "a.md").read_text() == "a"
    assert (tmp_path / "handbook_copy" / "sub" / "b.md").read_text() == "b"


class FileSystemToolErrorPathTests(unittest.TestCase):
    def test_path_traversal_returns_error_not_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            result = run(ReadTextTool(config).execute(ToolCall("read_text", {"path": "../outside.txt"})))
            self.assertEqual(result.status, ToolStatus.ERROR)

    def test_find_pattern_escaping_root_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            Path(tmp, "OUTSIDE_SECRET.txt").write_text("secret", encoding="utf-8")
            Path(tmp, "root", "notes").mkdir(parents=True)
            config = FileSystemToolConfig(root=str(Path(tmp, "root")))
            absolute = str(Path(tmp, "*.txt"))
            for pattern in ("../*", "*/../../*", "notes\\..\\..\\*", absolute):
                result = run(FindTool(config).execute(ToolCall("find", {"pattern": pattern, "root": "."})))
                self.assertEqual(result.status, ToolStatus.ERROR, pattern)
                self.assertNotIn("OUTSIDE_SECRET", result.output)
                self.assertIn("escaped the configured root", result.output)

    def test_zip_destination_inside_source_is_not_archived(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(MakeDirTool(config).execute(ToolCall("make_dir", {"path": "notes"})))
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "notes/a.md", "content": "a"})))
            result = run(ZipTool(config).execute(ToolCall("zip", {"source": ".", "destination": "backup.zip"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            with zipfile.ZipFile(Path(tmp, "backup.zip")) as archive:
                names = archive.namelist()
            self.assertFalse(any(name.endswith("backup.zip") for name in names), names)
            self.assertTrue(any(name.endswith("notes/a.md") for name in names), names)

    def test_write_without_allow_write_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=False)
            result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "blocked"})))
            self.assertEqual(result.status, ToolStatus.ERROR)
            self.assertIn("allow_write", result.output)

    def test_read_nonexistent_file_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            result = run(ReadTextTool(config).execute(ToolCall("read_text", {"path": "missing.txt"})))
            self.assertEqual(result.status, ToolStatus.ERROR)

    def test_delete_nonexistent_path_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            result = run(DeleteTool(config).execute(ToolCall("delete", {"path": "nope.txt"})))
            self.assertEqual(result.status, ToolStatus.ERROR)

    def test_delete_refuses_string_recursive_flag_and_keeps_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "reports").mkdir()
            Path(tmp, "reports", "q1.txt").write_text("keep", encoding="utf-8")
            result = run(DeleteTool(config).execute(ToolCall("delete", {"path": "reports", "recursive": "false"})))
            self.assertEqual(result.status, ToolStatus.ERROR)
            self.assertIn("'recursive' must be a boolean (true/false)", result.output)
            self.assertTrue(Path(tmp, "reports", "q1.txt").exists())

    def test_delete_refuses_the_configured_root_and_keeps_its_files(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "notes.txt").write_text("keep", encoding="utf-8")
            Path(tmp, "reports").mkdir()
            Path(tmp, "reports", "q1.txt").write_text("gone", encoding="utf-8")
            for path in (".", ""):
                result = run(DeleteTool(config).execute(ToolCall("delete", {"path": path, "recursive": True})))
                self.assertEqual(result.status, ToolStatus.ERROR, path)
                self.assertIn("root itself cannot be deleted", result.output)
            self.assertTrue(Path(tmp, "notes.txt").exists())
            result = run(DeleteTool(config).execute(ToolCall("delete", {"path": "reports", "recursive": True})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertFalse(Path(tmp, "reports").exists())
            self.assertTrue(Path(tmp, "notes.txt").exists())

    def test_make_dir_null_flags_use_documented_defaults(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            result = run(MakeDirTool(config).execute(ToolCall("make_dir", {"path": "a/b/c", "parents": None, "exist_ok": None})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertTrue(Path(tmp, "a", "b", "c").is_dir())

    def test_create_parents_string_flag_is_refused_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            for tool, name in ((WriteTextTool(config), "write_text"), (AppendTool(config), "append_text"), (TouchTool(config), "touch")):
                result = run(tool.execute(ToolCall(name, {"path": "new/f.txt", "content": "x", "create_parents": "false"})))
                self.assertEqual(result.status, ToolStatus.ERROR, name)
                self.assertIn("'create_parents' must be a boolean (true/false)", result.output)
            self.assertFalse(Path(tmp, "new").exists())

    def test_diff_without_content_or_other_path_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "x"})))
            result = run(DiffTool(config).execute(ToolCall("diff", {"path": "f.txt"})))
            self.assertEqual(result.status, ToolStatus.ERROR)

    def test_replace_text_search_not_found_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "hello"})))
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.txt", "search": "nope", "replacement": "x"})))
            self.assertEqual(result.status, ToolStatus.ERROR)
            self.assertNotIn("@@", result.output)

    def test_replace_text_multiple_matches_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "aa aa"})))
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.txt", "search": "aa", "replacement": "bb"})))
            self.assertEqual(result.status, ToolStatus.ERROR)

    def test_replace_text_overlapping_matches_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            target = Path(tmp) / "f.go"
            original = b"func a() {\nif x {\nfor {\n}\n}\n}\n"
            target.write_bytes(original)
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.go", "search": "}\n}\n", "replacement": "}\n"})))
            self.assertEqual(result.status, ToolStatus.ERROR)
            self.assertIn("exactly once", result.output)
            self.assertEqual(target.read_bytes(), original)

    def test_replace_text_error_says_whether_search_was_missing_or_repeated(self) -> None:
        # The model reads only this message, so it must tell "not found"
        # (re-read the file) apart from "several matches" (add context).
        for search, expected in (("zz", "but it was not found."), ("aa", "but it appears 3 times; include more surrounding text to make it unique.")):
            with self.subTest(search=search), TemporaryDirectory() as tmp:
                config = FileSystemToolConfig(root=tmp, allow_write=True)
                target = Path(tmp) / "f.txt"
                target.write_bytes(b"aa\naa\naa\n")
                result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.txt", "search": search, "replacement": "bb"})))
                self.assertEqual(result.status, ToolStatus.ERROR)
                self.assertIn(f"ReplaceTextTool requires the search text to appear exactly once, {expected}", result.output)
                self.assertEqual(target.read_bytes(), b"aa\naa\naa\n")

    def test_edit_the_encoding_cannot_hold_returns_error_and_leaves_file_untouched(self) -> None:
        # @intent failed-edit-leaves-file-untouched
        # "€" does not exist in latin-1, and a lone surrogate from the model's JSON arguments
        # cannot be UTF-8, so each edit must fail before the file is emptied by opening it.
        original = b"<?php\n$name = 'caf\xe9';\n"
        cases = (
            ("latin-1", ReplaceTextTool, {"search": "caf\xe9", "replacement": "€5"}),
            ("latin-1", WriteTextTool, {"content": "<?php\n$price = '€5';\n"}),
            ("utf-8", ReplaceTextTool, {"search": "$name", "replacement": "$name\ud83d"}),
            ("utf-8", WriteTextTool, {"content": "print('hi \ud83d')\n"}),
        )
        for encoding, tool_class, arguments in cases:
            with self.subTest(encoding=encoding, tool=tool_class.__name__), TemporaryDirectory() as tmp:
                content = original if encoding == "latin-1" else original.replace(b"\xe9", b"e")
                target = Path(tmp) / "app.php"
                target.write_bytes(content)
                tool = tool_class(FileSystemToolConfig(root=tmp, allow_write=True, encoding=encoding))
                result = run(tool.execute(ToolCall(tool.name, {"path": "app.php", **arguments})))
                self.assertEqual(result.status, ToolStatus.ERROR)
                self.assertIn("can't encode", result.output)
                self.assertEqual(target.read_bytes(), content)

    def test_read_lines_start_less_than_one_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "x"})))
            result = run(ReadLinesTool(config).execute(ToolCall("read_lines", {"path": "f.txt", "start": 0})))
            self.assertEqual(result.status, ToolStatus.ERROR)

    def test_read_lines_end_less_than_start_returns_error(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "x\ny"})))
            result = run(ReadLinesTool(config).execute(ToolCall("read_lines", {"path": "f.txt", "start": 3, "end": 1})))
            self.assertEqual(result.status, ToolStatus.ERROR)


class FileSystemToolNullOptionalArgumentTests(unittest.TestCase):
    """An explicit JSON null for an optional argument behaves exactly like leaving it out."""

    def _assert_null_matches_omitted(self, tool, name: str, base: dict, nulls: dict) -> None:
        omitted = run(tool.execute(ToolCall(name, dict(base))))
        nulled = run(tool.execute(ToolCall(name, {**base, **nulls})))
        self.assertEqual(omitted.status, ToolStatus.SUCCESS, omitted.output)
        self.assertEqual(nulled.status, ToolStatus.SUCCESS, nulled.output)
        self.assertEqual(nulled.output, omitted.output)
        self.assertEqual(nulled.metadata, omitted.metadata)

    def test_null_optional_arguments_use_documented_defaults(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            Path(tmp, "app.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            Path(tmp, "sub").mkdir()
            Path(tmp, "sub", "util.py").write_text("x", encoding="utf-8")
            cases = (
                (ReadLinesTool(config), "read_lines", {"path": "app.py"}, {"start": None}),
                (ReadLinesTool(config), "read_lines", {"path": "app.py"}, {"start": None, "end": None}),
                (FindTool(config), "find", {"pattern": "*.py"}, {"root": None}),
                (ListDirTool(config), "list_dir", {}, {"path": None}),
                (TreeTool(config), "tree", {}, {"path": None, "max_depth": None, "max_entries": None}),
            )
            for tool, name, base, nulls in cases:
                with self.subTest(tool=name, nulls=sorted(nulls)):
                    self._assert_null_matches_omitted(tool, name, base, nulls)

    def test_read_lines_null_start_reads_from_first_line(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            Path(tmp, "app.py").write_text("one\ntwo\n", encoding="utf-8")
            result = run(ReadLinesTool(config).execute(ToolCall("read_lines", {"path": "app.py", "start": None, "end": 1})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(result.output, "one")

    def test_tree_non_integer_max_depth_returns_error_result(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)
            for arguments in ({"max_depth": "abc"}, {"max_entries": "abc"}):
                with self.subTest(arguments=arguments):
                    result = run(TreeTool(config).execute(ToolCall("tree", arguments)))
                    self.assertEqual(result.status, ToolStatus.ERROR)


class FailingWriteBackend(LocalFileSystemBackend):
    """A local backend whose writes fail the way a read-only file does."""

    def write_text(self, path: Path, content: str, *, encoding: str, create_parents: bool, newline: str | None = None) -> None:
        raise PermissionError("[Errno 13] Permission denied")


def changed_lines(output: str) -> list[str]:
    # The diff's removed and added lines, after the path line and
    # the ---/+++ file headers.
    return [line for line in output.split("\n")[3:] if line.startswith(("-", "+"))]


class EditToolDiffTests(unittest.TestCase):
    def test_replace_text_on_crlf_file_diffs_only_the_edited_line(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            target = Path(tmp) / "f.py"
            target.write_bytes(b"def f():\r\n    x = 1\r\n    return 2\r\n\r\nprint(f())\r\n")
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.py", "search": "return 2", "replacement": "return 3"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(result.output.split("\n")[0], result.metadata["path"])
            self.assertEqual(changed_lines(result.output), ["-    return 2", "+    return 3"])
            self.assertEqual(target.read_bytes(), b"def f():\r\n    x = 1\r\n    return 3\r\n\r\nprint(f())\r\n")

    def test_replace_text_diff_shows_which_of_two_similar_blocks_was_hit(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.py").write_text("def first():\n    value = 1\n    return value\n\ndef second():\n    value = 1\n    return value\n", encoding="utf-8")
            call = ToolCall("replace_text", {"path": "f.py", "search": "def second():\n    value = 1", "replacement": "def second():\n    value = 2"})
            result = run(ReplaceTextTool(config).execute(call))
            lines = result.output.split("\n")
            self.assertEqual(lines[3], "@@ -3,5 +3,5 @@")
            self.assertIn(" def second():", lines)
            self.assertEqual(changed_lines(result.output), ["-    value = 1", "+    value = 2"])

    def test_write_text_new_file_reports_line_count_instead_of_a_diff(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "new.txt", "content": "a\nb\nc\n"})))
            self.assertEqual(result.output, f"{result.metadata['path']}\ncreated, 3 lines")

    def test_identical_rewrite_and_same_text_replacement_report_no_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.txt").write_text("keep\n", encoding="utf-8")
            written = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "keep\n"})))
            replaced = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.txt", "search": "keep", "replacement": "keep"})))
            for result in (written, replaced):
                self.assertEqual(result.output, f"{result.metadata['path']}\nno changes")

    def test_failed_write_returns_its_error_without_a_diff(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True, backend=FailingWriteBackend())
            target = Path(tmp) / "f.txt"
            target.write_text("old\n", encoding="utf-8")
            calls = (
                (WriteTextTool(config), ToolCall("write_text", {"path": "f.txt", "content": "new\n"})),
                (ReplaceTextTool(config), ToolCall("replace_text", {"path": "f.txt", "search": "old", "replacement": "new"})),
            )
            for tool, call in calls:
                with self.subTest(tool=tool.name):
                    result = run(tool.execute(call))
                    self.assertEqual(result.status, ToolStatus.ERROR)
                    self.assertEqual(result.output, "[Errno 13] Permission denied")
            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")

    def test_diff_is_cut_after_the_cap_with_a_count_of_the_rest(self) -> None:
        # The diff is 4 lines (---, +++, @@, -old) plus one + line per
        # new line, so the first case fills the cap exactly.
        exact, over = EDIT_DIFF_MAX_LINES - 4, 200
        for new_lines, expected_last in ((exact, f"+line {exact - 1}"), (over, f"[diff truncated: {4 + over - EDIT_DIFF_MAX_LINES} more lines]")):
            with self.subTest(new_lines=new_lines), TemporaryDirectory() as tmp:
                config = FileSystemToolConfig(root=tmp, allow_write=True)
                Path(tmp, "f.txt").write_text("old\n", encoding="utf-8")
                content = "".join(f"line {index}\n" for index in range(new_lines))
                result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": content})))
                lines = result.output.split("\n")
                self.assertEqual(lines[-1], expected_last)
                self.assertEqual(len(lines), 1 + min(4 + new_lines, EDIT_DIFF_MAX_LINES + 1))
                self.assertEqual(Path(tmp, "f.txt").read_text(encoding="utf-8"), content)

    def test_utf8_edit_diffs_the_exact_characters(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.txt").write_text("menu: café\n", encoding="utf-8")
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.txt", "search": "café", "replacement": "naïve 🙂"})))
            self.assertEqual(changed_lines(result.output), ["-menu: café", "+menu: naïve 🙂"])

    def test_missing_final_newline_does_not_join_diff_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.txt").write_text("alpha beta", encoding="utf-8")
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.txt", "search": "beta", "replacement": "gamma"})))
            marker = "\\ No newline at end of file"
            self.assertEqual(result.output.split("\n")[3:], ["@@ -1 +1 @@", "-alpha beta", marker, "+alpha gamma", marker])

    def test_form_feed_line_stays_one_diff_line(self) -> None:
        # A ^L page break line is one line on disk, so the diff must not
        # split it or mark it as a last line without a newline.
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.c").write_text("int a;\n\f\nint b;\nint c;\n", encoding="utf-8")
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.c", "search": "int c;", "replacement": "int c2;"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(result.output.split("\n")[3:], ["@@ -1,4 +1,4 @@", " int a;", " \f", " int b;", "-int c;", "+int c2;"])

    def test_line_separator_inside_a_line_stays_one_diff_line(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.js").write_text('const s = "x y";\nlet n = 1;\n', encoding="utf-8")
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.js", "search": "n = 1", "replacement": "n = 2"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertNotIn("No newline at end of file", result.output)
            self.assertEqual(result.output.split("\n")[3:], ["@@ -1,2 +1,2 @@", ' const s = "x y";', "-let n = 1;", "+let n = 2;"])

    def test_missing_final_newline_is_marked_only_at_the_real_end(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            Path(tmp, "f.txt").write_text("page\fbreak\nlast", encoding="utf-8")
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.txt", "search": "last", "replacement": "end"})))
            marker = "\\ No newline at end of file"
            self.assertEqual(result.output.split("\n")[3:], ["@@ -1,2 +1,2 @@", " page\fbreak", "-last", marker, "+end", marker])

    def test_write_text_new_file_counts_lines_by_newline_only(self) -> None:
        # A form feed is not a line break; a last line without a newline
        # still counts, and empty content has no lines.
        for content, expected in (("page1\fstill line1\nline2\n", 2), ("a b\nc", 2), ("", 0)):
            with self.subTest(content=content), TemporaryDirectory() as tmp:
                config = FileSystemToolConfig(root=tmp, allow_write=True)
                result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "new.txt", "content": content})))
                self.assertEqual(result.output, f"{result.metadata['path']}\ncreated, {expected} lines")

    def test_write_text_over_non_utf8_file_still_writes(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)
            target = Path(tmp) / "f.txt"
            target.write_bytes(b"caf\xe9\n")
            result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.txt", "content": "café\n"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(result.output.split("\n")[1], "no diff: the old file is not valid utf-8 text")
            self.assertEqual(target.read_text(encoding="utf-8"), "café\n")


class WriteTextOverwriteLimitTests(unittest.TestCase):
    """max_overwrite_lines: write_text may not replace an existing file with more lines than the limit."""

    def _write(self, tmp: str, limit: int | None, path: str = "f.py", content: str = "new\n"):
        config = FileSystemToolConfig(root=tmp, allow_write=True, max_overwrite_lines=limit)
        return run(WriteTextTool(config).execute(ToolCall("write_text", {"path": path, "content": content})))

    def test_file_at_the_limit_is_replaced_and_one_line_over_is_refused_untouched(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp, "f.py")
            target.write_bytes(b"line\n" * 300)
            self.assertEqual(self._write(tmp, 300).status, ToolStatus.SUCCESS)
            self.assertEqual(target.read_text(encoding="utf-8"), "new\n")

            original = b"line\n" * 301
            target.write_bytes(original)
            result = self._write(tmp, 300)
            self.assertEqual(result.status, ToolStatus.ERROR)
            self.assertEqual(target.read_bytes(), original)
            for expected in ("f.py", "301 lines", "300-line limit", "replace_text"):
                self.assertIn(expected, result.output)
            self.assertNotIn("delete", result.output.lower())

    def test_new_file_of_any_size_is_written(self) -> None:
        with TemporaryDirectory() as tmp:
            result = self._write(tmp, 1, path="big.py", content="x\n" * 10_000)
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(Path(tmp, "big.py").read_bytes().count(b"\n"), 10_000)

    def test_replace_text_still_edits_a_file_over_the_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp, "f.py")
            target.write_bytes(b"keep\n" * 500 + b"old\n")
            config = FileSystemToolConfig(root=tmp, allow_write=True, max_overwrite_lines=10)
            result = run(ReplaceTextTool(config).execute(ToolCall("replace_text", {"path": "f.py", "search": "old", "replacement": "new"})))
            self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
            self.assertEqual(target.read_bytes(), b"keep\n" * 500 + b"new\n")

    def test_no_limit_by_default_or_with_none(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp, "f.py")
            for config in (FileSystemToolConfig(root=tmp, allow_write=True), FileSystemToolConfig(root=tmp, allow_write=True, max_overwrite_lines=None)):
                with self.subTest(max_overwrite_lines=config.max_overwrite_lines):
                    self.assertIsNone(config.max_overwrite_lines)
                    target.write_bytes(b"line\n" * 5_000)
                    result = run(WriteTextTool(config).execute(ToolCall("write_text", {"path": "f.py", "content": "new\n"})))
                    self.assertEqual(result.status, ToolStatus.SUCCESS, result.output)
                    self.assertEqual(target.read_text(encoding="utf-8"), "new\n")

    def test_line_count_handles_no_trailing_newline_crlf_and_invalid_utf8(self) -> None:
        cases = {
            "no trailing newline": (b"a\nb\nc", 3),
            "crlf": (b"a\r\nb\r\nc\r\n", 3),
            "invalid utf-8": (b"\xff\xfe\n\x80abc\n\xc3\n", 3),
        }
        for label, (data, lines) in cases.items():
            with self.subTest(label), TemporaryDirectory() as tmp:
                target = Path(tmp, "f.py")
                target.write_bytes(data)
                refused = self._write(tmp, lines - 1)
                self.assertEqual(refused.status, ToolStatus.ERROR)
                self.assertIn(f"{lines} lines", refused.output)
                self.assertEqual(target.read_bytes(), data)
                self.assertEqual(self._write(tmp, lines).status, ToolStatus.SUCCESS)

    def test_invalid_limits_raise_configuration_error_naming_the_field(self) -> None:
        with TemporaryDirectory() as tmp:
            for bad in (0, -1, True, 2.5, "300"):
                with self.subTest(bad=bad), self.assertRaises(ConfigurationError) as caught:
                    FileSystemToolConfig(root=tmp, max_overwrite_lines=bad)
                self.assertIn("max_overwrite_lines", str(caught.exception))

    def test_spec_mentions_the_limit_only_when_one_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            plain = WriteTextTool(FileSystemToolConfig(root=tmp)).spec().description
            limited = WriteTextTool(FileSystemToolConfig(root=tmp, max_overwrite_lines=1500)).spec().description
            self.assertEqual(plain, "Write text content to a file at the given path inside the configured root. The result shows a diff of the change, or the line count of a new file.")
            self.assertTrue(limited.startswith(plain))
            self.assertIn("1,500 lines", limited)
            self.assertIn("replace_text", limited)
            self.assertNotIn("replace_text", plain)


class FileSystemToolImportTests(unittest.TestCase):
    def test_filestat_importable_from_lib_dataclasses(self) -> None:
        from vidbyte.lib.dataclasses import FileStat
        self.assertTrue(hasattr(FileStat, "path"))
        self.assertTrue(hasattr(FileStat, "exists"))

    def test_filestat_importable_directly_from_filesystem_module(self) -> None:
        from vidbyte.lib.dataclasses.filesystem import FileStat
        self.assertTrue(hasattr(FileStat, "path"))

    def test_tool_types_module_no_longer_exists(self) -> None:
        import importlib
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("vidbyte.lib.dataclasses.tool_types")


if __name__ == "__main__":
    unittest.main()
