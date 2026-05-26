"""CLI entry point for vidbyte-prompts: serve and export subcommands."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys


PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _extract_arguments(text: str) -> list[str]:
    """Extract unique {placeholder} names from prompt text."""
    seen: set[str] = set()
    args: list[str] = []
    for match in PLACEHOLDER_RE.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            args.append(name)
    return args


def _cmd_serve() -> None:
    """Dispatch to the MCP server entry point."""
    from vidbyte.prompts.mcp_server import main as serve_main

    serve_main()


def _cmd_export(output_dir: str) -> None:
    """Export all prompts as standalone JSON files to *output_dir*."""
    from vidbyte.prompts.catalog import Prompts
    from vidbyte.lib.enums.prompts import Prompt

    catalog = Prompts()
    all_prompts = catalog.all()
    exported = 0

    os.makedirs(output_dir, exist_ok=True)

    for key in sorted(all_prompts.keys(), key=lambda k: k.value):
        record = catalog._records[key]
        text = all_prompts[key]
        family_key = key.value.split(".")[0]
        arguments = _extract_arguments(text)

        payload = {
            "name": f"{record.name} - {record.name}",
            "description": record.description,
            "key": key.value,
            "family": family_key,
            "text": text,
            "arguments": arguments,
            "version": "0.1.0",
        }

        file_name = key.value.replace(".", "-") + ".json"
        file_path = os.path.join(output_dir, file_name)

        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

        exported += 1

    print(f"Exported {exported} prompts to {os.path.abspath(output_dir)}")


def main() -> None:
    """Entry point registered as ``vidbyte-prompts`` console_script."""
    parser = argparse.ArgumentParser(
        prog="vidbyte-prompts",
        description="Vidbyte prompt distribution — MCP server and export tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve", help="Start MCP prompt server over stdio")

    export_parser = subparsers.add_parser("export", help="Export prompts as standalone files")
    export_parser.add_argument(
        "--output-dir", "-o",
        default=".",
        help="Directory to write prompt files (default: current directory)",
    )

    args = parser.parse_args()

    if args.command == "serve":
        _cmd_serve()
    elif args.command == "export":
        _cmd_export(args.output_dir)


if __name__ == "__main__":
    main()
