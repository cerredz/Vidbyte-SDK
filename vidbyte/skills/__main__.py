from __future__ import annotations

import argparse
from collections.abc import Sequence

from vidbyte.lib.enums.skills import Skill
from vidbyte.skills.catalog import Skills


class SkillsCli:
    """Small argparse wrapper for inspecting and materializing packaged skills."""

    def main(self, argv: Sequence[str] | None = None) -> int:
        # Parses CLI arguments and dispatches to the selected subcommand.
        parser = self._build_parser()
        args = parser.parse_args(argv)
        if args.command == "list":
            return self._list_skills()
        if args.command == "install":
            return self._install_skill(args.key, args.dest)
        parser.print_help()
        return 1

    def _build_parser(self) -> argparse.ArgumentParser:
        # Builds the command parser for list and install operations.
        parser = argparse.ArgumentParser(prog="python -m vidbyte.skills")
        subparsers = parser.add_subparsers(dest="command")
        subparsers.add_parser("list", help="List packaged Vidbyte skills.")
        install_parser = subparsers.add_parser("install", help="Materialize a packaged Vidbyte skill.")
        install_parser.add_argument("key", help="Skill key, for example context_minimal_fanout.decompose_fanout.")
        install_parser.add_argument("--dest", required=True, help="Destination directory for the skill files.")
        return parser

    def _list_skills(self) -> int:
        # Prints one line per packaged skill with its enum value and description.
        skills = Skills()
        for key, description in skills.descriptions().items():
            print(f"{key.value}\t{description}")
        return 0

    def _install_skill(self, key_text: str, dest: str) -> int:
        # Materializes one skill by string key and prints the installed skill path.
        skill_path = Skills().materialize(Skill(key_text), dest)
        print(skill_path)
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    # Runs the module CLI and returns a process exit code.
    return SkillsCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
