# CLI

`vidbyte.cli` is the unified console command surface for the Vidbyte SDK.

## Role In The SDK

The CLI gives terminal users a small entry point into packaged SDK developer
surfaces. Its first command group is `skills`, which wraps `vidbyte.skills` so a
developer can list, inspect, and install distributable skill files without
writing Python code.

## Design Philosophy

The CLI stays dependency-free and explicit. Each subcommand group registers
itself through a `register(subparsers)` function, while domain behavior remains
in the package it wraps. Help output is intentionally lazy: commands do not
instantiate catalogs until a handler runs.

## Usage

```bash
vidbyte --version
vidbyte skills list
vidbyte skills show decompose-fanout
vidbyte skills install decompose-fanout --dest .claude/skills
```

Equivalent module command:

```bash
python -m vidbyte.cli skills list
```

## Key Modules

- `__init__.py`: root parser, version flag, subcommand registration, and
  process-compatible `main(argv) -> int`.
- `skills.py`: `skills list`, `skills show`, and `skills install` handlers.
- `__main__.py`: module bridge for `python -m vidbyte.cli`.

## Related Layers

The current command group wraps [`vidbyte.skills`](../skills/README.md). Future
backend, auth, prompt, or MCP command groups should add one module with a
`register(subparsers)` function and one explicit call from the root CLI.
