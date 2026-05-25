from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any, ClassVar

from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class PromptRecord:
    """One flattened prompt asset record."""

    key: Prompt
    text: str
    description: str
    family: str
    name: str
    import_name: str


class Prompts:
    """Enum-keyed accessor for plain text Vidbyte prompts."""

    _records: ClassVar[dict[Prompt, PromptRecord] | None] = None
    _families: ClassVar[dict[str, dict[str, str]] | None] = None

    def __init__(self) -> None:
        self._ensure_loaded()

    def get(self, key: Prompt) -> str:
        """Return prompt text for a single prompt enum member."""
        if not isinstance(key, Prompt):
            raise TypeError("Prompts.get() expects a Prompt enum member.")
        return self._records_by_key()[key].text

    def keys(self) -> tuple[Prompt, ...]:
        """Return all available prompt enum keys."""
        return tuple(sorted(self._records_by_key(), key=lambda prompt: prompt.value))

    def descriptions(self) -> Mapping[Prompt, str]:
        """Return prompt descriptions keyed by prompt enum."""
        return {key: self._records_by_key()[key].description for key in self.keys()}

    def all(self) -> Mapping[Prompt, str]:
        """Return all prompt text keyed by prompt enum."""
        return {key: self._records_by_key()[key].text for key in self.keys()}

    def family(self, family_key: str) -> Mapping[str, str]:
        """Return one prompt family keyed by leaf prompt name."""
        try:
            return dict(self._families_by_key()[family_key])
        except KeyError as exc:
            raise ConfigurationError(f"Prompt family does not exist: {family_key!r}") from exc

    def import_names(self) -> Mapping[Prompt, str]:
        """Return direct import names keyed by prompt enum."""
        return {key: self._records_by_key()[key].import_name for key in self.keys()}

    @classmethod
    def _records_by_key(cls) -> dict[Prompt, PromptRecord]:
        cls._ensure_loaded()
        assert cls._records is not None
        return cls._records

    @classmethod
    def _families_by_key(cls) -> dict[str, dict[str, str]]:
        cls._ensure_loaded()
        assert cls._families is not None
        return cls._families

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._records is not None and cls._families is not None:
            return
        records, families = cls._load()
        cls._validate_enum_sync(records)
        cls._records = records
        cls._families = families

    @classmethod
    def _load(cls) -> tuple[dict[Prompt, PromptRecord], dict[str, dict[str, str]]]:
        records: dict[Prompt, PromptRecord] = {}
        families: dict[str, dict[str, str]] = {}
        prompt_dir = resources.files("vidbyte.prompts.prompts")

        for asset in cls._json_assets(prompt_dir):
            filename = cls._asset_label(asset)
            try:
                with asset.open("r", encoding="utf-8") as file:
                    raw = json.load(file)
            except json.JSONDecodeError as exc:
                raise ConfigurationError(f"Prompt file {filename} is not valid JSON.") from exc

            record = cls._validate_record(raw, filename)
            family_key = cls._required_text(record, "key", filename)
            family_description = cls._required_text(record, "description", filename)
            prompts = record["prompts"]
            families[family_key] = {}

            for prompt_name, prompt_value in prompts.items():
                text = cls._resolve_prompt_text(prompt_value, asset, filename)
                prompt_id = f"{family_key}.{prompt_name}"
                try:
                    prompt_key = Prompt(prompt_id)
                except ValueError as exc:
                    raise ConfigurationError(f"Prompt enum is missing a member for {prompt_id!r}.") from exc
                if prompt_key in records:
                    raise ConfigurationError(f"Duplicate prompt enum value: {prompt_id!r}.")
                import_name = prompt_id.replace(".", "_")
                description = f"{family_description} ({prompt_name})"
                records[prompt_key] = PromptRecord(
                    key=prompt_key,
                    text=text,
                    description=description,
                    family=family_key,
                    name=str(prompt_name),
                    import_name=import_name,
                )
                families[family_key][str(prompt_name)] = text

        return records, families

    @classmethod
    def _json_assets(cls, prompt_dir: Any) -> tuple[Any, ...]:
        assets: list[Any] = []
        for asset in prompt_dir.iterdir():
            if asset.is_file() and asset.name.endswith(".json"):
                assets.append(asset)
            elif asset.is_dir():
                assets.extend(
                    child for child in asset.iterdir() if child.is_file() and child.name.endswith(".json")
                )
        return tuple(sorted(assets, key=cls._asset_label))

    @staticmethod
    def _asset_label(asset: Any) -> str:
        parent_name = getattr(getattr(asset, "parent", None), "name", "")
        if parent_name and parent_name != "prompts":
            return f"{parent_name}/{asset.name}"
        return asset.name

    @classmethod
    def _validate_record(cls, raw: object, filename: str) -> Mapping[str, Any]:
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Prompt file {filename} must contain a JSON object.")
        cls._required_text(raw, "name", filename)
        cls._required_text(raw, "description", filename)
        cls._required_text(raw, "key", filename)
        prompts = raw.get("prompts")
        if not isinstance(prompts, dict) or not prompts:
            raise ConfigurationError(f"Prompt file {filename} must contain a non-empty prompts object.")
        return raw

    @staticmethod
    def _required_text(record: Mapping[str, Any], field_name: str, filename: str) -> str:
        value = record.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"Prompt file {filename} must contain a non-empty {field_name}.")
        return value

    @classmethod
    def _resolve_prompt_text(cls, value: object, asset: Any, filename: str) -> str:
        if isinstance(value, str):
            return cls._validate_prompt_text(value, filename)
        if not isinstance(value, dict):
            raise ConfigurationError(f"Prompt file {filename} contains an invalid prompt value.")

        markdown_path = cls._required_text(value, "path", filename)
        cls._required_text(value, "source_url", filename)
        if not markdown_path.endswith(".md"):
            raise ConfigurationError(f"Prompt file {filename} references a non-Markdown prompt asset.")
        markdown_asset = asset.parent.joinpath(markdown_path)
        if not markdown_asset.is_file():
            raise ConfigurationError(f"Prompt file {filename} references missing Markdown asset: {markdown_path}.")
        with markdown_asset.open("r", encoding="utf-8") as file:
            return cls._validate_prompt_text(file.read(), markdown_path)

    @staticmethod
    def _validate_prompt_text(value: object, filename: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"Prompt file {filename} contains an empty prompt value.")
        return value

    @staticmethod
    def _validate_enum_sync(records: Mapping[Prompt, PromptRecord]) -> None:
        missing_assets = sorted(prompt.value for prompt in Prompt if prompt not in records)
        if missing_assets:
            raise ConfigurationError(f"Prompt enum values have no asset text: {missing_assets}")


__all__ = [
    "PromptRecord",
    "Prompts",
]
