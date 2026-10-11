# CLI

`vidbyte.cli` is the unified console command surface for the Vidbyte SDK.

## Role In The SDK

The CLI gives terminal users a small entry point into packaged SDK developer
surfaces. Its `skills` group wraps `vidbyte.skills` so a developer can list,
inspect, and install distributable skill files without writing Python code. Its
`coding` group runs one task with a `CodingAgent` over a folder and prints the
agent's final reply.

## Design Philosophy

The CLI stays dependency-free and explicit. Each subcommand group registers
itself through a `register(subparsers)` function, while domain behavior remains
in the package it wraps. Help output is intentionally lazy: commands do not
instantiate catalogs until a handler runs.

## Usage

```bash
vidbyte-sdk --version
vidbyte-sdk skills list
vidbyte-sdk skills show decompose-fanout
vidbyte-sdk skills install decompose-fanout --dest .claude/skills
vidbyte-sdk coding run --root-dir my-project --provider openai --model gpt-4.1 "Fix the failing test."
vidbyte-sdk coding run --firecrawl-key-env FIRECRAWL_API_KEY "Read the install guide and follow it."
```

`coding run` never takes a key as a flag value, because flag values land in
shell history and process lists. A `--<provider>-key-env` flag names the
environment variable that holds the key instead.

Equivalent module command:

```bash
python -m vidbyte.cli skills list
```

## Key Modules

- `__init__.py`: root parser, version flag, subcommand registration, and
  process-compatible `main(argv) -> int`.
- `skills.py`: `skills list`, `skills show`, and `skills install` handlers.
- `coding.py`: `coding run`, which builds a `CodingAgent` from flags, runs one
  task, and prints the final reply.
- `__main__.py`: module bridge for `python -m vidbyte.cli`.

## Related Layers

The command groups wrap [`vidbyte.skills`](../skills/README.md) and
[`vidbyte.agents`](../agents/README.md) (`CodingAgent`). Future
backend, auth, prompt, or MCP command groups should add one module with a
`register(subparsers)` function and one explicit call from the root CLI.
