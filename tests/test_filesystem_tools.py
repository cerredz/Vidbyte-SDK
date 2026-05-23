from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from vidbyte.lib.errors import ToolExecutionError
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


class FileSystemToolTests(unittest.TestCase):
    def test_read_list_write_and_mkdir_inside_root(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)

            MakeDirTool(config).run("nested")
            WriteTextTool(config).run("nested/file.txt", "hello")
            text = ReadTextTool(config).run("nested/file.txt")
            entries = ListDirTool(config).run(".")

            self.assertEqual(text.value, "hello")
            self.assertEqual(entries.value, ("nested/",))

    def test_path_traversal_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp)

            with self.assertRaises(ToolExecutionError):
                ReadTextTool(config).run("../outside.txt")

    def test_write_requires_allow_write(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=False)

            with self.assertRaises(ToolExecutionError):
                WriteTextTool(config).run("file.txt", "blocked")

    def test_expanded_filesystem_tools_use_scoped_backend(self) -> None:
        with TemporaryDirectory() as tmp:
            config = FileSystemToolConfig(root=tmp, allow_write=True)

            WriteTextTool(config).run("a.txt", "one")
            AppendTool(config).run("a.txt", "\ntwo")
            CopyTool(config).run("a.txt", "b.txt")
            MoveTool(config).run("b.txt", "nested/c.txt")
            WriteTextTool(config).run("binary.bin", "data")
            archive = ZipTool(config).run("nested", "nested.zip")
            extracted = UnzipTool(config).run("nested.zip", "unzipped")

            self.assertIn("two", ReadTextTool(config).run("a.txt").value)
            self.assertEqual(ReadBinaryTool(config).run("binary.bin").value, b"data")
            self.assertTrue(ExistsTool(config).run("a.txt").value)
            self.assertEqual(ReadLinesTool(config).run("a.txt", start=2).value, ("two",))
            self.assertTrue(StatTool(config).run("nested/c.txt").value.is_file)
            self.assertEqual(FindTool(config).run("*.txt", root="nested").value, ("c.txt",))
            self.assertIn("+three", DiffTool(config).run("a.txt", content="one\ntwo\nthree").value)
            ReplaceTextTool(config).run("a.txt", search="two", replacement="three")
            self.assertIn("three", ReadTextTool(config).run("a.txt").value)
            TouchTool(config).run("touched/new.txt", create_parents=True)
            self.assertTrue(ExistsTool(config).run("touched/new.txt").value)
            self.assertIn("nested/c.txt", TreeTool(config).run(".").value)
            self.assertEqual(len(ChecksumTool(config).run("a.txt").value), 64)
            self.assertTrue(str(archive.value).endswith("nested.zip"))
            self.assertIn("nested/c.txt", extracted.value)

            DeleteTool(config).run("nested/c.txt")
            self.assertFalse(StatTool(config).run("nested/c.txt").value.exists)


if __name__ == "__main__":
    unittest.main()
