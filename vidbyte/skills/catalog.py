from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, ClassVar

from vidbyte.lib.enums.skills import Skill
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class SkillRecord:
    """One distributable skill asset record."""

    key: Skill
    paradigm: str
    name: str
    description: str
    folder: str
    entry: str
    text: str
    files: Mapping[str, str]


class Skills:
    """Enum-keyed accessor for packaged Vidbyte skill file trees."""

    _records: ClassVar[dict[Skill, SkillRecord] | None] = None
    _paradigms: ClassVar[dict[str, dict[Skill, SkillRecord]] | None] = None
    _manifest_packages: ClassVar[tuple[str, ...]] = ("vidbyte.paradigms.context_minimal_fanout",)

    def __init__(self) -> None:
        # Loads and validates packaged skill manifests the first time the catalog is used.
        self._ensure_loaded()

    def get(self, key: Skill) -> SkillRecord:
        # Returns the full record for one skill enum member.
        if not isinstance(key, Skill):
            raise TypeError("Skills.get() expects a Skill enum member.")
        return self._records_by_key()[key]

    def text(self, key: Skill) -> str:
        # Returns the SKILL.md text for one skill enum member.
        return self.get(key).text

    def keys(self) -> tuple[Skill, ...]:
        # Returns all available skill enum keys in stable value order.
        return tuple(sorted(self._records_by_key(), key=lambda skill: skill.value))

    def descriptions(self) -> Mapping[Skill, str]:
        # Returns skill descriptions keyed by skill enum.
        return {key: self._records_by_key()[key].description for key in self.keys()}

    def paradigm(self, family_key: str) -> Mapping[Skill, SkillRecord]:
        # Returns all skills registered for one paradigm family key.
        try:
            return dict(self._paradigms_by_key()[family_key])
        except KeyError as exc:
            raise ConfigurationError(f"Skill paradigm does not exist: {family_key!r}") from exc

    def files(self, key: Skill) -> Mapping[str, str]:
        # Returns all materializable files for one skill as relative path to text.
        return dict(self.get(key).files)

    def materialize(self, key: Skill, dest_dir: str | Path) -> Path:
        # Writes a skill folder and declared shared files under dest_dir and returns the skill path.
        record = self.get(key)
        root = Path(dest_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        for relative_path, content in record.files.items():
            target = self._safe_materialize_target(root, relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return root.joinpath(record.folder)

    @classmethod
    def _records_by_key(cls) -> dict[Skill, SkillRecord]:
        # Returns the cached record map after ensuring it has been loaded.
        cls._ensure_loaded()
        assert cls._records is not None
        return cls._records

    @classmethod
    def _paradigms_by_key(cls) -> dict[str, dict[Skill, SkillRecord]]:
        # Returns the cached paradigm map after ensuring it has been loaded.
        cls._ensure_loaded()
        assert cls._paradigms is not None
        return cls._paradigms

    @classmethod
    def _ensure_loaded(cls) -> None:
        # Loads manifests once and validates enum, manifest, and filesystem sync.
        if cls._records is not None and cls._paradigms is not None:
            return
        records, paradigms = cls._load()
        cls._validate_enum_sync(records)
        cls._records = records
        cls._paradigms = paradigms

    @classmethod
    def _load(cls) -> tuple[dict[Skill, SkillRecord], dict[str, dict[Skill, SkillRecord]]]:
        # Reads every configured skill manifest package and flattens records by enum key.
        records: dict[Skill, SkillRecord] = {}
        paradigms: dict[str, dict[Skill, SkillRecord]] = {}
        for package_name in cls._manifest_packages:
            cls._load_package(package_name, records, paradigms)
        return records, paradigms

    @classmethod
    def _load_package(cls, package_name: str, records: dict[Skill, SkillRecord], paradigms: dict[str, dict[Skill, SkillRecord]]) -> None:
        # Loads one package-local skills.json manifest and appends its records.
        skills_dir = resources.files(package_name).joinpath("skills")
        manifest_asset = skills_dir.joinpath("skills.json")
        if not manifest_asset.is_file():
            raise ConfigurationError(f"Skill manifest is missing: {package_name}/skills/skills.json.")
        try:
            with manifest_asset.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Skill manifest {package_name}/skills/skills.json is not valid JSON.") from exc

        manifest = cls._validate_manifest(raw, f"{package_name}/skills/skills.json")
        paradigm_key = cls._required_text(manifest, "key", "skills.json")
        manifest_records = cls._validate_manifest_entries(manifest["skills"], skills_dir, paradigm_key)
        cls._validate_folder_sync(manifest_records, skills_dir, paradigm_key)

        paradigms.setdefault(paradigm_key, {})
        for record in manifest_records:
            if record.key in records:
                raise ConfigurationError(f"Duplicate skill enum value: {record.key.value!r}.")
            records[record.key] = record
            paradigms[paradigm_key][record.key] = record

    @classmethod
    def _validate_manifest(cls, raw: object, filename: str) -> Mapping[str, Any]:
        # Validates top-level manifest fields before entry-specific loading.
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Skill manifest {filename} must contain a JSON object.")
        cls._required_text(raw, "name", filename)
        cls._required_text(raw, "description", filename)
        cls._required_text(raw, "key", filename)
        skills = raw.get("skills")
        if not isinstance(skills, list) or not skills:
            raise ConfigurationError(f"Skill manifest {filename} must contain a non-empty skills list.")
        return raw

    @classmethod
    def _validate_manifest_entries(cls, raw_entries: object, skills_dir: Any, paradigm_key: str) -> tuple[SkillRecord, ...]:
        # Converts manifest entries into validated SkillRecord values.
        records: list[SkillRecord] = []
        assert isinstance(raw_entries, list)
        for raw_entry in raw_entries:
            records.append(cls._load_record(raw_entry, skills_dir, paradigm_key))
        return tuple(records)

    @classmethod
    def _load_record(cls, raw_entry: object, skills_dir: Any, paradigm_key: str) -> SkillRecord:
        # Loads and validates one manifest skill entry plus its Markdown files.
        if not isinstance(raw_entry, dict):
            raise ConfigurationError("Skill manifest entries must be JSON objects.")
        key_text = cls._required_text(raw_entry, "key", "skills.json")
        folder = cls._required_text(raw_entry, "folder", key_text)
        entry = cls._required_text(raw_entry, "entry", key_text)
        name = cls._required_text(raw_entry, "name", key_text)
        description = cls._required_text(raw_entry, "description", key_text)
        if not key_text.startswith(f"{paradigm_key}."):
            raise ConfigurationError(f"Skill key {key_text!r} must be namespaced by {paradigm_key!r}.")
        try:
            key = Skill(key_text)
        except ValueError as exc:
            raise ConfigurationError(f"Skill enum is missing a member for {key_text!r}.") from exc
        file_paths = cls._validate_file_list(raw_entry.get("files"), key_text)
        file_map = cls._load_file_map(file_paths, skills_dir, key_text)
        entry_path = f"{folder}/{entry}"
        text = cls._required_file_text(file_map, entry_path, key_text)
        cls._validate_frontmatter(text, folder, entry_path)
        return SkillRecord(key=key, paradigm=paradigm_key, name=name, description=description, folder=folder, entry=entry, text=text, files=file_map)

    @classmethod
    def _validate_file_list(cls, raw_files: object, key_text: str) -> tuple[str, ...]:
        # Validates manifest file paths before resolving package resources.
        if not isinstance(raw_files, list) or not raw_files:
            raise ConfigurationError(f"Skill {key_text!r} must declare a non-empty files list.")
        files: list[str] = []
        for raw_file in raw_files:
            if not isinstance(raw_file, str) or not raw_file.strip():
                raise ConfigurationError(f"Skill {key_text!r} declares an invalid file path.")
            normalized = raw_file.replace("\\", "/")
            if normalized.startswith("/") or ".." in Path(normalized).parts:
                raise ConfigurationError(f"Skill {key_text!r} declares an unsafe file path: {raw_file!r}.")
            files.append(normalized)
        return tuple(files)

    @classmethod
    def _load_file_map(cls, file_paths: tuple[str, ...], skills_dir: Any, key_text: str) -> Mapping[str, str]:
        # Reads every declared skill file and returns package-relative text content.
        file_map: dict[str, str] = {}
        for file_path in file_paths:
            if not file_path.endswith(".md"):
                raise ConfigurationError(f"Skill {key_text!r} references a non-Markdown skill asset: {file_path}.")
            asset = skills_dir.joinpath(*file_path.split("/"))
            if not asset.is_file():
                raise ConfigurationError(f"Skill {key_text!r} references missing asset: {file_path}.")
            with asset.open("r", encoding="utf-8") as file:
                content = file.read()
            if not content.strip():
                raise ConfigurationError(f"Skill {key_text!r} references empty asset: {file_path}.")
            file_map[file_path] = content
        return file_map

    @staticmethod
    def _required_file_text(file_map: Mapping[str, str], path: str, key_text: str) -> str:
        # Returns a required file from a loaded file map or raises a precise config error.
        try:
            return file_map[path]
        except KeyError as exc:
            raise ConfigurationError(f"Skill {key_text!r} must include its entry file {path!r}.") from exc

    @classmethod
    def _validate_frontmatter(cls, text: str, folder: str, filename: str) -> None:
        # Validates YAML-like frontmatter without adding a YAML dependency.
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ConfigurationError(f"Skill file {filename} must start with YAML frontmatter.")
        try:
            closing_index = lines[1:].index("---") + 1
        except ValueError as exc:
            raise ConfigurationError(f"Skill file {filename} must close YAML frontmatter.") from exc
        fields = cls._parse_frontmatter_fields(lines[1:closing_index], filename)
        if fields.get("name") != folder:
            raise ConfigurationError(f"Skill file {filename} frontmatter name must match folder {folder!r}.")
        if not fields.get("description"):
            raise ConfigurationError(f"Skill file {filename} frontmatter must include a non-empty description.")

    @staticmethod
    def _parse_frontmatter_fields(lines: list[str], filename: str) -> dict[str, str]:
        # Parses simple key-value frontmatter used by harness skill discovery.
        fields: dict[str, str] = {}
        for line in lines:
            if ":" not in line:
                raise ConfigurationError(f"Skill file {filename} contains invalid frontmatter line: {line!r}.")
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"').strip("'")
        return fields

    @staticmethod
    def _validate_folder_sync(records: tuple[SkillRecord, ...], skills_dir: Any, paradigm_key: str) -> None:
        # Ensures every manifest skill folder exists and every skill folder has a manifest entry.
        manifest_folders = {record.folder for record in records}
        disk_folders = {
            asset.name
            for asset in skills_dir.iterdir()
            if asset.is_dir() and asset.name != "references" and asset.joinpath("SKILL.md").is_file()
        }
        missing_folders = sorted(manifest_folders - disk_folders)
        extra_folders = sorted(disk_folders - manifest_folders)
        if missing_folders:
            raise ConfigurationError(f"Skill manifest for {paradigm_key!r} references missing folders: {missing_folders}.")
        if extra_folders:
            raise ConfigurationError(f"Skill manifest for {paradigm_key!r} is missing folders: {extra_folders}.")

    @staticmethod
    def _required_text(record: Mapping[str, Any], field_name: str, filename: str) -> str:
        # Reads a required non-empty text field from a manifest object.
        value = record.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"Skill manifest {filename} must contain a non-empty {field_name}.")
        return value

    @staticmethod
    def _validate_enum_sync(records: Mapping[Skill, SkillRecord]) -> None:
        # Ensures every Skill enum member has a manifest-backed record and nothing is missing.
        missing_assets = sorted(skill.value for skill in Skill if skill not in records)
        if missing_assets:
            raise ConfigurationError(f"Skill enum values have no asset text: {missing_assets}")

    @staticmethod
    def _safe_materialize_target(root: Path, relative_path: str) -> Path:
        # Resolves a materialize target and refuses any path outside the destination root.
        target = root.joinpath(relative_path)
        resolved_target = target.resolve()
        if not resolved_target.is_relative_to(root):
            raise ConfigurationError(f"Skill materialize target escapes destination: {relative_path!r}.")
        return resolved_target


__all__ = [
    "SkillRecord",
    "Skills",
]
