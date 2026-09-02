"""Context Protocol Header

Description:
    Defines ParadigmMinimalToolset — the minimal universal toolset for thin
    harnesses that operate on a local filesystem.
Purpose:
    Centralizes the read/search/execute (and optional write) tools a paradigm
    agent needs so harnesses import one toolset instead of hand-building tuples.
Architecture:
    - ParadigmMinimalToolset: Builds a Tools catalog rooted at a directory.
Relations:
    Consumed by vidbyte.paradigms harnesses; composes builtin filesystem, search,
    execution, and editing tools into a vidbyte.tools.Tools catalog.
"""

from __future__ import annotations

from pathlib import Path

from vidbyte.lib.dataclasses.filesystem import FileSystemToolConfig
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.code_search import GlobTool, GrepTool
from vidbyte.tools.builtins.editing import PatchTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.filesystem import ListDirTool, ReadLinesTool, ReadTextTool, StatTool, TreeTool


class ParadigmMinimalToolset:
    """Minimal universal filesystem toolset for paradigm harness agents."""

    def __init__(self, root: str | Path = ".", *, include_execution: bool = True, include_write: bool = False) -> None:
        # Stores the filesystem root and which optional tool groups to include.
        self._root = Path(root)
        self._include_execution = include_execution
        self._include_write = include_write

    def tools(self) -> Tools:
        # Builds the read/search (and optional execute/write) tools as a catalog.
        return Tools(self._build_tools())

    def all(self) -> tuple[BaseTool, ...]:
        # Convenience accessor so the toolset drops into settings tool fields.
        return self.tools().all()

    def _build_tools(self) -> tuple[BaseTool, ...]:
        # Assembles the ordered tool instances for the configured root.
        fs_config = FileSystemToolConfig(root=self._root, allow_write=self._include_write)
        tools: list[BaseTool] = [
            GlobTool(root_dir=self._root),
            GrepTool(root_dir=self._root),
            ReadTextTool(fs_config),
            ReadLinesTool(fs_config),
            ListDirTool(fs_config),
            TreeTool(fs_config),
            StatTool(fs_config),
        ]
        if self._include_execution:
            tools.append(CodeExecutionTool())
        if self._include_write:
            tools.append(PatchTool(root_dir=self._root))
        return tuple(tools)


__all__ = [
    "ParadigmMinimalToolset",
]
