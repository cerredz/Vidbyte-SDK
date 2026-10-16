from __future__ import annotations

import os
import shutil
import uuid
import zipfile
from pathlib import Path

from vidbyte.lib.dataclasses import FileStat
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.lib.tools.filesystem.backends.base import BaseFileSystemBackend
from vidbyte.lib.tools.filesystem.newlines import LineEndings


class LocalFileSystemBackend(BaseFileSystemBackend):
    """Local pathlib implementation of the filesystem backend interface."""

    def read_text(self, path: Path, *, encoding: str) -> str:
        return path.read_text(encoding=encoding)

    def read_binary(self, path: Path) -> bytes:
        return path.read_bytes()

    def write_text(self, path: Path, content: str, *, encoding: str, create_parents: bool, newline: str | None = None) -> None:
        # @intent failed-edit-leaves-file-untouched
        # Opening for writing empties the file at once, so text the encoding
        # cannot hold must fail here, before the file is opened.
        content.encode(encoding)
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding=encoding, newline=newline) as handle:
            handle.write(content)

    def append_text(self, path: Path, content: str, *, encoding: str, create_parents: bool, newline: str | None = None) -> None:
        # @intent failed-edit-leaves-file-untouched
        # Opening for appending creates a missing file at once, so text the
        # encoding cannot hold must fail here, before any folder or file is made.
        content.encode(encoding)
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding=encoding, newline=newline) as handle:
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
        # @intent copy-never-copies-into-itself
        # A destination inside the source directory would be copied into itself until the path is too
        # deep, so it is refused before anything is written, the way `cp -r` and `shutil.move` refuse it.
        if source.is_dir() and destination.resolve().is_relative_to(source.resolve()):
            raise ToolExecutionError("Cannot copy a directory into itself.", details={"source": str(source), "destination": str(destination)})
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
        matches = set(root.rglob(pattern))
        # See @intent trailing-globstar-matches-files: before Python 3.13 a last "**" segment matched directories only,
        # so add everything below the matched directories, as Python 3.13 does.
        if pattern.endswith("**") and Path(pattern).name == "**":
            matches.update(root.rglob(pattern + "/*"))
        return tuple(str(path.relative_to(root)) for path in sorted(matches, key=lambda item: str(item).lower()))

    def diff_text(self, left: Path, right_content: str, *, encoding: str, label: str) -> str:
        current = left.read_text(encoding=encoding) if left.exists() else ""
        return LineEndings.unified_diff(current, right_content, fromfile=str(left), tofile=label)

    def zip_path(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # @intent failed-zip-keeps-existing-archive
        # Opening an archive for writing empties it at once, so a source file that cannot be read
        # would destroy the archive already there. Build the new one in a file beside it and swap it
        # in only after every member is written. Mode "x" creates that file like any new file, so the
        # archive keeps the usual permissions (mkstemp would make it owner-only).
        partial = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                self._write_members(archive, source, skipped={partial.resolve(), destination.resolve()})
            os.replace(partial, destination)
        except Exception:
            partial.unlink(missing_ok=True)
            raise

    @staticmethod
    def _write_members(archive: zipfile.ZipFile, source: Path, *, skipped: set[Path]) -> None:
        # A file is one member; a folder adds every entry under it, named from the folder's parent.
        if source.is_file():
            archive.write(source, arcname=source.name)
            return
        # @intent zip-never-archives-itself
        # The archive being built, and the one it replaces, can sit inside the source,
        # so neither is added to the new archive as a member.
        for path in source.rglob("*"):
            if path.resolve() in skipped:
                continue
            archive.write(path, arcname=path.relative_to(source.parent))

    def unzip_path(self, source: Path, destination: Path) -> tuple[str, ...]:
        destination.mkdir(parents=True, exist_ok=True)
        extracted: list[str] = []
        with zipfile.ZipFile(source) as archive:
            # @intent refused-archive-extracts-nothing
            # An archive with a member outside the extraction root is refused as a whole, so check
            # every member before writing any; otherwise earlier members would already be extracted.
            for member in archive.infolist():
                target = (destination / member.filename).resolve()
                if target != destination and destination not in target.parents:
                    raise ToolExecutionError("Zip archive contains a path outside the extraction root.", details={"member": member.filename})
            for member in archive.infolist():
                archive.extract(member, destination)
                extracted.append(member.filename)
        return tuple(extracted)


__all__ = [
    "LocalFileSystemBackend",
]
