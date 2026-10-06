"""Context Protocol Header

Description:
    Skills subcommand group for the unified Vidbyte SDK CLI.
Purpose:
    Lets terminal users list, inspect, and install packaged Vidbyte skills
    without writing Python code.
Architecture:
    - register attaches vidbyte-sdk skills list/show/install to the root parser.
    - SkillsCommandGroup lazily imports and calls vidbyte.skills.Skills.
    - SkillKeyResolver accepts full enum values and unambiguous short forms.
Relations:
    Thin adapter over vidbyte.skills; all skill business logic stays in the catalog.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from vidbyte.cli import CliUsageError
from vidbyte.lib.enums.skills import Skill, skill_from_value
from vidbyte.lib.errors import ConfigurationError


class UnknownSkillKeyError(Exception):
    """Expected usage error for unknown or ambiguous skill keys."""

    def __init__(self, message: str, valid_keys: tuple[Skill, ...]) -> None:
        # Stores the user-facing key error and catalog keys for stderr output.
        super().__init__(message)
        self.valid_keys = valid_keys


class SkillKeyResolver:
    """Resolves CLI skill key text to typed Skill enum members."""

    def resolve(self, key_text: str, valid_keys: tuple[Skill, ...]) -> Skill:
        # Accepts full enum values plus unambiguous leaf snake_case or kebab-case names.
        normalized = key_text.strip()
        direct = self._resolve_direct_value(normalized)
        if direct is not None:
            return direct
        matches = self._match_short_forms(normalized, valid_keys)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise UnknownSkillKeyError(f"ambiguous skill key: {key_text}", valid_keys)
        raise UnknownSkillKeyError(f"unknown skill key: {key_text}", valid_keys)

    def _resolve_direct_value(self, key_text: str) -> Skill | None:
        # Resolves exact enum values across registered paradigm enums via skill_from_value.
        try:
            return skill_from_value(key_text)
        except ValueError:
            return None

    def _match_short_forms(self, key_text: str, valid_keys: tuple[Skill, ...]) -> tuple[Skill, ...]:
        # Matches leaf skill names in snake_case or kebab-case when the match is unique.
        matches: list[Skill] = []
        for key in valid_keys:
            leaf_name = key.value.rsplit(".", 1)[-1]
            accepted_names = {leaf_name, leaf_name.replace("_", "-")}
            if key_text in accepted_names:
                matches.append(key)
        return tuple(matches)


class SkillsCommandGroup:
    """Registers and handles the vidbyte-sdk skills subcommand group."""

    def register(self, subparsers: argparse._SubParsersAction[Any]) -> None:
        # Attaches the skills command group and its list, show, and install actions.
        skills_parser = subparsers.add_parser("skills", help="List, show, and install packaged Vidbyte skills.")
        action_parsers = skills_parser.add_subparsers(dest="skills_command", required=True)
        self._register_list(action_parsers)
        self._register_show(action_parsers)
        self._register_install(action_parsers)

    def _register_list(self, subparsers: argparse._SubParsersAction[Any]) -> None:
        # Registers vidbyte-sdk skills list.
        parser = subparsers.add_parser("list", help="List packaged Vidbyte skills.")
        parser.set_defaults(handler=self.list_skills)

    def _register_show(self, subparsers: argparse._SubParsersAction[Any]) -> None:
        # Registers vidbyte-sdk skills show <key>.
        parser = subparsers.add_parser("show", help="Print a packaged skill's SKILL.md.")
        parser.add_argument("key", help="Full key or unambiguous short name, for example decompose-fanout.")
        parser.set_defaults(handler=self.show_skill)

    def _register_install(self, subparsers: argparse._SubParsersAction[Any]) -> None:
        # Registers vidbyte-sdk skills install <key> --dest <dir> [--force].
        parser = subparsers.add_parser("install", help="Materialize a packaged skill under a destination directory.")
        parser.add_argument("key", help="Full key or unambiguous short name, for example decompose-fanout.")
        parser.add_argument("--dest", required=True, help="Destination directory, for example .claude/skills.")
        parser.add_argument("--force", action="store_true", help="Overwrite an existing non-empty skill folder.")
        parser.set_defaults(handler=self.install_skill)

    def list_skills(self, args: argparse.Namespace) -> int:
        # Prints one stable line per skill using catalog descriptions.
        skills = self._catalog()
        for key in skills.keys():
            print(f"{key.value} - {skills.descriptions()[key]}")
        return 0

    def show_skill(self, args: argparse.Namespace) -> int:
        # Prints the selected skill's SKILL.md text to stdout.
        skills = self._catalog()
        key = self._resolve_key(args.key, skills.keys())
        text = skills.text(key)
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    def install_skill(self, args: argparse.Namespace) -> int:
        # Validates overwrite safety, materializes the skill, and prints the written path.
        skills = self._catalog()
        key = self._resolve_key(args.key, skills.keys())
        record = skills.get(key)
        self._refuse_existing_target(Path(args.dest), record.folder, args.force)
        installed_path = skills.materialize(key, args.dest)
        print(installed_path)
        return 0

    def _catalog(self) -> Any:
        # Imports and instantiates Skills lazily so help output does not validate assets.
        from vidbyte.skills import Skills

        return Skills()

    def _resolve_key(self, key_text: str, valid_keys: tuple[Skill, ...]) -> Skill:
        # Converts user-facing key text into a Skill enum or prints valid choices on failure.
        try:
            return SkillKeyResolver().resolve(key_text, valid_keys)
        except UnknownSkillKeyError as exc:
            self._print_key_error(exc)
            raise CliUsageError from exc

    def _print_key_error(self, exc: UnknownSkillKeyError) -> None:
        # Writes one usage-error line containing the valid enum values to stderr.
        valid = ", ".join(key.value for key in exc.valid_keys)
        print(f"error: {exc}; valid keys: {valid}", file=sys.stderr)

    def _refuse_existing_target(self, dest_dir: Path, folder: str, force: bool) -> None:
        # Refuses to overwrite an existing non-empty skill folder unless --force is provided.
        target = dest_dir.expanduser().joinpath(folder)
        if force or not target.exists():
            return
        if target.is_dir() and not any(target.iterdir()):
            return
        raise ConfigurationError(f"skill target already exists and is not empty: {target}")


def register(subparsers: argparse._SubParsersAction[Any]) -> None:
    # Registers the skills command group with the root vidbyte-sdk parser.
    SkillsCommandGroup().register(subparsers)


__all__ = [
    "SkillsCommandGroup",
    "register",
]
