"""CLI entry point for vidbyte-prompts: list, get, serve, and export subcommands."""

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


def _cmd_list() -> None:
    """List all available prompts with descriptions."""
    from vidbyte.prompts.catalog import Prompts

    catalog = Prompts()
    for key in sorted(catalog.keys(), key=lambda k: k.value):
        record = catalog._records[key]
        args = _extract_arguments(record.text)
        arg_str = f"  args: {', '.join(args)}" if args else ""
        print(f"  {key.value:<52s}  {record.description}{arg_str}")


def _cmd_get(key: str, raw_args: list[str] | None) -> None:
    """Print a single prompt to stdout, optionally substituting arguments."""
    from vidbyte.prompts.mcp_server import resolve_prompt

    arguments: dict[str, str] = {}
    if raw_args:
        for pair in raw_args:
            if "=" not in pair:
                print(f"Invalid argument format: {pair} (expected key=value)", file=sys.stderr)
                sys.exit(1)
            k, v = pair.split("=", 1)
            arguments[k] = v

    try:
        text = resolve_prompt(key, arguments if arguments else None)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyError as exc:
        print(f"Missing required argument: {exc}", file=sys.stderr)
        sys.exit(1)

    print(text)


def _cmd_serve() -> None:
    """Dispatch to the MCP server entry point."""
    from vidbyte.prompts.mcp_server import main as serve_main

    serve_main()


def _cmd_export(output_dir: str) -> None:
    """Export all prompts as standalone JSON files to *output_dir*."""
    from vidbyte.prompts.catalog import Prompts

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
            "name": record.name,
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

    list_parser = subparsers.add_parser("list", help="List all available prompts")
    list_parser.set_defaults(func=lambda a: _cmd_list())

    get_parser = subparsers.add_parser("get", help="Print a prompt to stdout")
    get_parser.add_argument("key", help="Prompt key (e.g. chain_of_thought.reason_prompt)")
    get_parser.add_argument(
        "--arg", "-a",
        action="append",
        dest="raw_args",
        metavar="KEY=VALUE",
        help="Substitute {placeholder} values (repeatable)",
    )

    subparsers.add_parser("serve", help="Start MCP prompt server over stdio")

    export_parser = subparsers.add_parser("export", help="Export prompts as standalone files")
    export_parser.add_argument(
        "--output-dir", "-o",
        default=".",
        help="Directory to write prompt files (default: current directory)",
    )

    args = parser.parse_args()

    if args.command == "list":
        _cmd_list()
    elif args.command == "get":
        _cmd_get(args.key, getattr(args, "raw_args", None))
    elif args.command == "serve":
        _cmd_serve()
    elif args.command == "export":
        _cmd_export(args.output_dir)


if __name__ == "__main__":
    main()
