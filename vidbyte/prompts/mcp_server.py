"""MCP server that exposes Vidbyte SDK prompts as MCP prompts.

Provides `build_mcp_prompts()` to convert the SDK prompt catalog into MCP prompt
objects, `resolve_prompt()` to fetch and render prompt text with argument
substitution, and `serve()` to run the MCP stdio server loop.
"""

from __future__ import annotations

import asyncio
import re
import sys


PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _extract_arguments(text: str) -> list[dict[str, object]]:
    """Extract unique {placeholder} names from prompt text as MCP PromptArgument dicts."""
    seen: set[str] = set()
    args: list[dict[str, object]] = []
    for match in PLACEHOLDER_RE.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            args.append({"name": name, "description": f"Value for {name}", "required": True})
    return args


def build_mcp_prompts():
    """Return a list of Prompt dicts from the SDK prompt catalog.

    Each dict has keys: name, description, arguments (list of PromptArgument dicts).
    """
    from mcp.types import Prompt, PromptArgument

    from vidbyte.prompts.catalog import Prompts

    catalog = Prompts()
    result: list[Prompt] = []

    for key in sorted(catalog.keys(), key=lambda k: k.value):
        record = catalog._records[key]
        raw_args = _extract_arguments(record.text)
        arguments = (
            [PromptArgument(name=a["name"], description=str(a["description"]), required=bool(a["required"]))
             for a in raw_args]
            if raw_args
            else None
        )
        result.append(Prompt(
            name=key.value,
            description=record.description,
            arguments=arguments,
        ))

    return result


def resolve_prompt(name: str, arguments: dict[str, str] | None = None) -> str:
    """Resolve a prompt by its enum value name, substituting {placeholders} if given.

    Raises:
        ValueError: If the prompt name is not a valid Prompt enum member.
        KeyError: If a required placeholder is missing from *arguments*.
    """
    from vidbyte.lib.enums.prompts import Prompt as PromptKey
    from vidbyte.prompts.catalog import Prompts

    try:
        key = PromptKey(name)
    except ValueError:
        raise ValueError(f"Unknown prompt: {name}") from None

    text = Prompts().get(key)

    if arguments is not None:
        text = text.format(**arguments)

    return text


async def serve() -> None:
    """Run the MCP stdio server loop.

    Registers ``prompts/list`` and ``prompts/get`` handlers. Logs startup
    information to stderr (stdout is reserved for the MCP protocol).
    """
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import GetPromptResult, TextContent

    server = Server("vidbyte-prompts")

    @server.list_prompts()
    async def handle_list_prompts():
        prompts = build_mcp_prompts()
        print(f"[vidbyte-prompts] Serving {len(prompts)} prompts", file=sys.stderr)
        return prompts

    @server.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict[str, str] | None = None):
        text = resolve_prompt(name, arguments)
        return GetPromptResult(
            description=f"Prompt: {name}",
            messages=[
                TextContent(type="text", text=text),
            ],
        )

    async with stdio_server() as (read, write):
        await server.run(
            read,
            write,
            server.create_initialization_options(),
        )


def main() -> None:
    """CLI entry point for ``vidbyte-prompts serve``."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        print(
            "The 'mcp' package is required. Install with:\n"
            "    pip install vidbyte-sdk[mcp]",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(serve())


if __name__ == "__main__":
    main()
