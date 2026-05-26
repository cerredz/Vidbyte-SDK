"""Context Protocol Header

Description:
    Defines the abstract base class for browser automation backends.
Purpose:
    Provides a typed contract that browser provider backends must implement
    for navigation, interaction, extraction, and tab management.
Architecture:
    - BaseBrowserBackend: ABC with 14 async abstract methods.
    - Covers full browser lifecycle: navigate, interact, extract, tabs.
Relations:
    Related to vidbyte.lib.providers.browser and vidbyte.tools.builtins.browser.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseBrowserBackend(ABC):
    @abstractmethod
    async def navigate(self, url: str) -> str:
        ...

    @abstractmethod
    async def screenshot(self) -> str:
        ...

    @abstractmethod
    async def get_content(self, format: str) -> str:
        ...

    @abstractmethod
    async def click(self, selector: str) -> str:
        ...

    @abstractmethod
    async def type_text(self, selector: str, text: str) -> str:
        ...

    @abstractmethod
    async def press_key(self, key: str) -> str:
        ...

    @abstractmethod
    async def scroll(self, direction: str, amount: int) -> str:
        ...

    @abstractmethod
    async def extract(self, instruction: str, schema: dict | None) -> str:
        ...

    @abstractmethod
    async def act(self, instruction: str) -> str:
        ...

    @abstractmethod
    async def new_tab(self, url: str | None) -> str:
        ...

    @abstractmethod
    async def switch_tab(self, tab_index: int) -> str:
        ...

    @abstractmethod
    async def close_tab(self, tab_index: int) -> str:
        ...

    @abstractmethod
    async def list_tabs(self) -> list[dict]:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


__all__ = ["BaseBrowserBackend"]
