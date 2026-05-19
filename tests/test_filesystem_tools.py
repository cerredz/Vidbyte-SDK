from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.filesystem import FileSystemToolConfig, ListDirTool, MakeDirTool, ReadTextTool, WriteTextTool


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


if __name__ == "__main__":
    unittest.main()
