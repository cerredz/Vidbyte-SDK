from __future__ import annotations

import asyncio
import base64
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

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
