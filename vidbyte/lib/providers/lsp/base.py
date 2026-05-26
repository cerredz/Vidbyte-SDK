"""Context Protocol Header

Description:
    Defines the abstract base class and data transfer objects for LSP backends.
Purpose:
    Provides a typed contract that LSP provider backends must implement,
    along with shared Location and HoverInfo dataclasses.
Architecture:
    - Location: Dataclass with uri, line, character.
    - HoverInfo: Dataclass with contents and optional range.
    - BaseLspBackend: ABC requiring async LSP operations.
Relations:
    Related to vidbyte.lib.providers.lsp and vidbyte.tools.builtins.lsp.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class Location:
    uri: str
    line: int
    character: int


@dataclass(slots=True)
class HoverInfo:
    contents: str
    range: tuple | None = None


class BaseLspBackend(ABC):
    @abstractmethod
    async def initialize(self, root_uri: str, language: str) -> None:
        ...

    @abstractmethod
    async def definition(self, file_path: str, line: int, character: int) -> list[Location]:
        ...

    @abstractmethod
    async def references(self, file_path: str, line: int, character: int) -> list[Location]:
        ...

    @abstractmethod
    async def hover(self, file_path: str, line: int, character: int) -> HoverInfo | None:
        ...

    @abstractmethod
    async def diagnostics(self, file_path: str) -> list[str]:
        ...

    @abstractmethod
    async def symbols(self, file_path: str | None) -> list[dict]:
        ...

    async def shutdown(self) -> None:
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        ...


__all__ = [
    "BaseLspBackend",
    "HoverInfo",
    "Location",
]
