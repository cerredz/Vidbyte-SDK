from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar, Mapping

from vidbyte.lib.errors import ConfigurationError


class PromptRegistry:
    """Load inspectable prompt definitions from JSON prompt assets."""

    _default: ClassVar[PromptRegistry | None] = None

    def __init__(self, prompt_dir: Path | str | None = None) -> None:
        package_root = Path(__file__).resolve().parents[2]
        self._prompt_dir = Path(prompt_dir) if prompt_dir is not None else package_root / "prompts" / "prompts"
        self._prompts = self._load_prompts()

    @classmethod
    def default(cls) -> PromptRegistry:
        if cls._default is None:
            cls._default = cls()
        return cls._default

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._prompts))

    def all(self) -> Mapping[str, Mapping[str, str]]:
        return {key: dict(value) for key, value in self._prompts.items()}

    def get(self, key: str) -> dict[str, str]:
        try:
            return dict(self._prompts[key])
        except KeyError as exc:
            raise ConfigurationError(f"Prompt registry does not contain {key!r}.") from exc

    def _load_prompts(self) -> dict[str, dict[str, str]]:
        if not self._prompt_dir.exists():
            raise ConfigurationError(f"Prompt directory does not exist: {self._prompt_dir}")
        loaded: dict[str, dict[str, str]] = {}
        for path in sorted(self._prompt_dir.glob("*.json")):
            record = self._read_record(path)
            key = self._required_text(record, "key", path)
            prompts = record.get("prompts")
            if not isinstance(prompts, dict) or not prompts:
                raise ConfigurationError(f"Prompt file {path.name} must contain a non-empty prompts object.")
            loaded[key] = {str(prompt_key): self._validate_prompt_text(prompt_value, path) for prompt_key, prompt_value in prompts.items()}
        return loaded

    def _read_record(self, path: Path) -> dict[str, Any]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Prompt file {path.name} is not valid JSON.") from exc
        if not isinstance(record, dict):
            raise ConfigurationError(f"Prompt file {path.name} must contain a JSON object.")
        self._required_text(record, "name", path)
        self._required_text(record, "description", path)
        return record

    def _required_text(self, record: Mapping[str, Any], field_name: str, path: Path) -> str:
        value = record.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"Prompt file {path.name} must contain a non-empty {field_name}.")
        return value

    def _validate_prompt_text(self, value: object, path: Path) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"Prompt file {path.name} contains an empty prompt value.")
        return value


PrompRegistry = PromptRegistry


__all__ = [
    "PrompRegistry",
    "PromptRegistry",
]
