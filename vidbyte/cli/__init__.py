"""Context Protocol Header

Description:
    Unified Vidbyte SDK console command entry point.
Purpose:
    Provides a small argparse command surface that can grow by registering
    explicit subcommand groups.
Architecture:
    - VidbyteCli builds the root parser, version flag, and subparser registry.
    - ReturningArgumentParser converts argparse exits into integer return codes.
    - main(argv) returns an exit code for in-process tests and console scripts.
Relations:
    First subcommand group is vidbyte.cli.skills, wrapping vidbyte.skills.Skills.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib import metadata
from typing import Any

from vidbyte.lib.errors import ConfigurationError


class CliParserExit(Exception):
    """Internal signal used to convert argparse exits into return values."""

    def __init__(self, status: int) -> None:
        # Stores the argparse status code that main() should return.
        super().__init__(status)
        self.status = status


class CliUsageError(Exception):
    """Expected usage error that should return argparse's status code 2."""


class ReturningArgumentParser(argparse.ArgumentParser):
    """ArgumentParser variant that returns exit codes instead of exiting."""

    def exit(self, status: int = 0, message: str | None = None) -> None:
        # Raises an internal signal after printing argparse's message, if any.
        if message:
            self._print_message(message, sys.stderr)
        raise CliParserExit(status)


class VersionResolver:
    """Resolves the installed vidbyte-sdk package version for --version."""

    def resolve(self) -> str:
        # Reads package metadata, falling back to the local project version in source checkouts.
        try:
            return metadata.version("vidbyte-sdk")
        except metadata.PackageNotFoundError:
            return "0.1.0"


class VidbyteCli:
    """Root command builder and dispatcher for the unified vidbyte CLI."""

    def main(self, argv: Sequence[str] | None = None) -> int:
        # Parses argv, dispatches the selected handler, and returns a deterministic exit code.
        parser = self._build_parser()
        try:
            args = parser.parse_args(argv)
            return int(args.handler(args))
        except CliParserExit as exc:
            return exc.status
        except CliUsageError:
            return 2
        except ConfigurationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    def _build_parser(self) -> ReturningArgumentParser:
        # Builds the root parser and attaches every explicit subcommand group.
        parser = ReturningArgumentParser(prog="vidbyte-sdk")
        parser.add_argument("--version", action="version", version=f"%(prog)s {VersionResolver().resolve()}")
        subparsers = parser.add_subparsers(dest="command", required=True)
        self._register_subcommand_groups(subparsers)
        return parser

    def _register_subcommand_groups(self, subparsers: argparse._SubParsersAction[Any]) -> None:
        # Registers first-party command groups using an explicit growable list.
        from vidbyte.cli import skills

        skills.register(subparsers)


def main(argv: Sequence[str] | None = None) -> int:
    # Runs the unified Vidbyte CLI and returns a process-compatible exit code.
    return VidbyteCli().main(argv)


__all__ = [
    "CliUsageError",
    "VidbyteCli",
    "main",
]
