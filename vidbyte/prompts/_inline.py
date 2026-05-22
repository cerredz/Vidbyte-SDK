from __future__ import annotations

import re
from typing import Dict

from vidbyte.prompts.base import BasePrompt
from vidbyte.prompts.types import PromptKey


class InlinePrompt(BasePrompt):
    """Lightweight prompt created from a key + raw template string."""

    def __init__(self, prompt_key: PromptKey, template_str: str) -> None:
        self._key = prompt_key
        self._template = template_str
        self._vars: dict[str, str] = {
            v: v for v in re.findall(r"\{(\w+)\}", template_str)
        }

    def key(self) -> PromptKey:
        return self._key

    def version(self) -> str:
        return "inline"

    def template(self) -> str:
        return self._template

    def variables(self) -> Dict[str, str]:
        return self._vars
