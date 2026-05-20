from __future__ import annotations

import difflib
import shutil
import zipfile
from pathlib import Path

from vidbyte.lib.dataclasses import FileStat
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem.backends.base import BaseFileSystemBackend


class LocalFileSystemBackend(BaseFileSystemBackend):
    """Local pathlib implementation of the filesystem backend interface."""

    def read_text(self, path: Path, *, encoding: str) -> str:
        return path.read_text(encoding=encoding)

    def read_binary(self, path: Path) -> bytes:
        return path.read_bytes()

    def write_text(self, path: Path, content: str, *, encoding: str, create_parents: bool) -> None:
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)

    def append_text(self, path: Path, content: str, *, encoding: str, create_parents: bool) -> None:
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding=encoding) as handle:
            handle.write(content)

    def list_dir(self, path: Path) -> tuple[str, ...]:
        return tuple(f"{entry.name}/" if entry.is_dir() else entry.name for entry in sorted(path.iterdir(), key=lambda item: item.name.lower()))

    def make_dir(self, path: Path, *, parents: bool, exist_ok: bool) -> None:
        path.mkdir(parents=parents, exist_ok=exist_ok)

    def delete(self, path: Path, *, recursive: bool) -> None:
        if path.is_dir():
            if recursive:
                shutil.rmtree(path)
                return
            path.rmdir()
            return
        path.unlink()

    def move(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

    def copy(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
            return
        shutil.copy2(source, destination)

    def stat(self, path: Path) -> FileStat:
        if not path.exists():
            return FileStat(path=str(path), exists=False, is_file=False, is_dir=False, size=None, modified_time=None)
        metadata = path.stat()
        return FileStat(path=str(path), exists=True, is_file=path.is_file(), is_dir=path.is_dir(), size=metadata.st_size, modified_time=metadata.st_mtime)

    def find(self, root: Path, pattern: str) -> tuple[str, ...]:
        return tuple(str(path.relative_to(root)) for path in sorted(root.rglob(pattern), key=lambda item: str(item).lower()))

    def diff_text(self, left: Path, right_content: str, *, encoding: str, label: str) -> str:
        current = left.read_text(encoding=encoding).splitlines(keepends=True) if left.exists() else []
        proposed = right_content.splitlines(keepends=True)
        return "".join(difflib.unified_diff(current, proposed, fromfile=str(left), tofile=label))

    def zip_path(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if source.is_file():
                archive.write(source, arcname=source.name)
                return
            for path in source.rglob("*"):
                archive.write(path, arcname=path.relative_to(source.parent))

    def unzip_path(self, source: Path, destination: Path) -> tuple[str, ...]:
        destination.mkdir(parents=True, exist_ok=True)
        extracted: list[str] = []
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                target = (destination / member.filename).resolve()
                if target != destination and destination not in target.parents:
                    raise ToolExecutionError("Zip archive contains a path outside the extraction root.", details={"member": member.filename})
                archive.extract(member, destination)
                extracted.append(member.filename)
        return tuple(extracted)


__all__ = [
    "LocalFileSystemBackend",
]
