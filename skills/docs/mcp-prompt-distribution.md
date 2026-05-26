# Design Doc: MCP Prompt Distribution

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-25
**Last Updated:** 2026-05-25

---

## 1. Overview

Expose Vidbyte SDK prompts as MCP prompts so any MCP-compatible harness (Claude Desktop, Continue, Cursor, OpenCode, etc.) can discover, inspect, and retrieve them without installing the full Python SDK. This includes: an MCP server in `vidbyte-sdk` that reads from the existing prompt catalog, a CLI export command that writes standalone prompt files for zero-dependency distribution, and companion skills in `vidbyte-cli` that teach AI harnesses how to install, configure, create, and export prompts via MCP.

---

## 2. Goals & Non-Goals

### Goals

- Add an MCP stdio server (`vidbyte-prompts serve`) that exposes all 42 SDK prompts as MCP prompts with argument extraction from `{placeholder}` patterns
- Add a CLI export command (`vidbyte-prompts export`) that writes each prompt as a standalone, self-contained JSON file suitable for zero-dependency consumption
- Add an optional `mcp` dependency group so the core SDK does not require the MCP package
- Register `vidbyte-prompts` as a console_script entry point in `pyproject.toml`
- Create 3 MCP skills in `vidbyte-cli/skills/`: `mcp-setup`, `mcp-create-prompt`, `mcp-export-prompts`
- Register new skills in `vidbyte-cli/skills-manifest.json`
- Write unit tests for the MCP server, export command, and argument extraction

### Non-Goals

- Do NOT build a standalone MCP server binary or npm package — the MCP server lives inside the Python SDK
- Do NOT change the existing prompt JSON schema, `Prompt` enum, or `Prompts` catalog class
- Do NOT add true MCP "tools" (executable functions) — only MCP "prompts" (templates)
- Do NOT modify any existing strategy classes or prompt consumption patterns
- Do NOT create a separate prompts-only repo at this stage — that is a future follow-up
- Do NOT add TypeScript/JavaScript MCP server variants — Python-only for now

---

## 3. Background & Context

### Current State

The SDK has 42 prompts across 17 families, stored as JSON files in `vidbyte/prompts/prompts/`. They are accessed via `Prompts.get()`, `Prompts.all()`, `Prompts.family()`, and direct module-level imports. The SDK already has an MCP *client* subsystem (`vidbyte/tools/mcp/`) that connects to external MCP servers as tools — but no MCP *server* that exposes SDK resources.

### Problem

Prompts are locked inside the Python SDK. Non-Python harnesses cannot access them. Python devs must install the full SDK just to use prompt text. There is no portable export format, no discoverability mechanism outside Python imports, and no standard protocol surface for cross-platform prompt consumption.

### Why MCP

MCP (Model Context Protocol) has a first-class `prompts/list` and `prompts/get` capability. This maps directly onto the SDK's prompt architecture: each `Prompt` enum member becomes an MCP prompt, with `{placeholder}` values exposed as prompt arguments. Harnesses that support MCP (Claude Desktop, Continue, Cursor, OpenCode, Zed, etc.) get automatic prompt discovery without platform-specific adapters.

### Constraints

- Python >= 3.11 (existing SDK constraint)
- `mcp` package must be optional — core SDK stays pydantic-only
- Testing must use `unittest` (existing convention)
- CLI must be a single entry point (`vidbyte-prompts`) with subcommands (`serve`, `export`)
- vidbyte-cli skills follow the existing YAML frontmatter + Markdown body format
- vidbyte-cli skills must be registered in `skills-manifest.json` under the `utility` category

---

## 4. Requirements

### Functional Requirements

1. **FR1:** `vidbyte-prompts serve` starts an MCP stdio server that responds to `prompts/list` with all 42 SDK prompts
2. **FR2:** Each MCP prompt includes: `name` (enum value, e.g. `chain_of_thought.reason_prompt`), `description` (from JSON asset), and `arguments` (extracted from `{placeholder}` patterns in prompt text)
3. **FR3:** `vidbyte-prompts serve` responds to `prompts/get` with the rendered prompt text, substituting provided arguments into `{placeholder}` slots
4. **FR4:** `vidbyte-prompts export --output-dir <dir>` writes one standalone JSON file per prompt leaf, with fields: `name`, `description`, `key`, `family`, `text`, `arguments`, `version`, `source_url`
5. **FR5:** CLI gracefully handles missing `mcp` package with a clear error message referencing `pip install vidbyte-sdk[mcp]`
6. **FR6:** vidbyte-cli skill `mcp-setup` instructs the AI harness on installing vidbyte-prompts as an MCP server for Claude Desktop, Continue, Cursor, and OpenCode
7. **FR7:** vidbyte-cli skill `mcp-create-prompt` instructs the AI harness on creating a new prompt JSON asset, registering the enum member, and running validation
8. **FR8:** vidbyte-cli skill `mcp-export-prompts` instructs the AI harness on using `vidbyte-prompts export` to produce standalone prompt files

### Non-Functional Requirements

- **Performance:** MCP server startup (loading all JSON assets) should complete in <500ms
- **Zero core dependency impact:** `pip install vidbyte-sdk` must not install `mcp`
- **Observability:** MCP server logs to stderr (stdio protocol) with prompt count on startup
- **Error handling:** Unknown prompt names in `prompts/get` return descriptive MCP errors

---

## 5. High-Level Design

Three components span two repos:

### Component 1: `vidbyte-sdk` — MCP Server

A new module `vidbyte/prompts/mcp_server.py` builds MCP prompt objects from the existing `Prompts` catalog. It uses the `mcp` Python SDK (`Server`, `stdio_server`, `Prompt`, `PromptArgument`, `GetPromptResult`). A regex extracts `{placeholder}` patterns from prompt text to declare MCP `arguments`. The server runs over stdio and registers `list_prompts` and `get_prompt` handlers.

### Component 2: `vidbyte-sdk` — CLI Export

A new module `vidbyte/prompts/cli.py` provides the `vidbyte-prompts` entry point with `serve` and `export` subcommands. The `export` subcommand calls `Prompts().all()`, flattens each leaf into the standalone JSON format, and writes files to the output directory.

### Component 3: `vidbyte-cli` — MCP Skills

Three new skill directories in `vidbyte-cli/skills/` (`mcp-setup`, `mcp-create-prompt`, `mcp-export-prompts`), each with a `SKILL.md` following the existing YAML frontmatter + Markdown body convention. Registered in `skills-manifest.json` under `utility`.

### Architecture Diagram

```text
┌──────────────────────────────────────────────────────────┐
│  vidbyte-sdk                                             │
│                                                          │
│  vidbyte/prompts/prompts/*.json  (existing, unchanged)   │
│         │                                                │
│         ▼                                                │
│  vidbyte/prompts/catalog.py      (existing, unchanged)   │
│         │                                                │
│         ├─────────────────────────────────────┐          │
│         ▼                                     ▼          │
│  vidbyte/prompts/mcp_server.py  [NEW]    cli.py [NEW]    │
│  - build_mcp_prompts()                   - serve         │
│  - serve()                               - export        │
│         │                                     │          │
│         ▼                                     ▼          │
│  MCP stdio (prompts/list,        Standalone JSON files   │
│  prompts/get)                    on disk                 │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  vidbyte-cli                                             │
│                                                          │
│  skills/mcp-setup/SKILL.md         [NEW]                 │
│  skills/mcp-create-prompt/SKILL.md [NEW]                 │
│  skills/mcp-export-prompts/SKILL.md[NEW]                 │
│  skills-manifest.json              [MODIFY]              │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Detailed Design

### 6.1 MCP Server Module

**File(s):** `vidbyte/prompts/mcp_server.py`
**Type:** New file

#### What it does

Provides `build_mcp_prompts()` that reads all prompts from the `Prompts` catalog and converts them into `mcp.types.Prompt` objects. Provides `serve()` that runs the MCP stdio server loop. Provides `main()` as the CLI entry point.

#### Interface / API

```python
# vidbyte/prompts/mcp_server.py

import asyncio
import re
import sys

from vidbyte.prompts.catalog import Prompts
from vidbyte.lib.enums.prompts import Prompt as PromptKey

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

def _extract_arguments(text: str) -> list:
    """Extract unique {placeholder} names from prompt text."""
    ...

def build_mcp_prompts() -> list:
    """Return list of mcp.types.Prompt objects from the SDK catalog."""
    ...

def resolve_prompt(name: str, arguments: dict[str, str] | None = None) -> str:
    """Resolve prompt by enum name, substituting {placeholders}."""
    ...

async def serve() -> None:
    """Run the MCP stdio server loop."""
    ...

def main() -> None:
    """CLI entry point for 'vidbyte-prompts serve'."""
    ...
```

#### Logic / Algorithm

1. **`build_mcp_prompts()`:**
   a. Call `Prompts()` to trigger lazy loading (cached)
   b. Iterate `Prompts().keys()` (returns `tuple[Prompt, ...]`)
   c. For each key, get the `PromptRecord` from `Prompts()._records`
   d. Extract `{placeholder}` names using `PLACEHOLDER_RE.findall(text)`, deduplicate
   e. Build `mcp.types.PromptArgument` list from unique placeholder names
   f. Build `mcp.types.Prompt(name=key.value, description=record.description, arguments=args or None)`
   g. Return sorted list

2. **`resolve_prompt()`:**
   a. Look up `PromptKey(name)` — raises `ValueError` if unknown
   b. Get text via `Prompts().get(key)`
   c. If arguments provided, call `text.format(**arguments)`
   d. Return rendered text

3. **`serve()`:**
   a. Create `Server("vidbyte-prompts")`
   b. Register `@server.list_prompts()` → calls `build_mcp_prompts()`
   c. Register `@server.get_prompt()` → calls `resolve_prompt()`, wraps in `GetPromptResult`
   d. Log prompt count to stderr
   e. Open `stdio_server()`, run server

4. **`main()`:**
   a. Wrap `asyncio.run(serve())`

#### Edge Cases & Error Handling

- **Missing `mcp` package:** CLI catches `ImportError` at startup, prints "Install with: pip install vidbyte-sdk[mcp]", exits with code 1
- **Unknown prompt name in `prompts/get`:** Return MCP error response with message "Unknown prompt: {name}"
- **`{placeholder}` in prompt but missing from arguments:** `str.format()` raises `KeyError` — catch and return error listing missing keys
- **Empty prompt catalog:** `build_mcp_prompts()` returns empty list — server starts but lists zero prompts
- **External markdown references** (goals, mimic_behavior): Already resolved by `Prompts._load()`, no special handling needed

### 6.2 CLI Module

**File(s):** `vidbyte/prompts/cli.py`
**Type:** New file

#### What it does

Provides the `vidbyte-prompts` console_script entry point with `serve` and `export` subcommands. Delegates to `mcp_server.main()` for serve and handles export logic inline.

#### Interface / API

```python
# vidbyte/prompts/cli.py

import argparse
import sys

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vidbyte-prompts",
        description="Vidbyte prompt distribution — MCP server and export tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start MCP prompt server over stdio")

    export_parser = subparsers.add_parser("export", help="Export prompts as standalone files")
    export_parser.add_argument(
        "--output-dir", "-o", default=".",
        help="Directory to write prompt files (default: current directory)",
    )

    args = parser.parse_args()

    if args.command == "serve":
        _cmd_serve()
    elif args.command == "export":
        _cmd_export(args.output_dir)
```

#### Logic / Algorithm (export)

1. Call `Prompts().all()` to get `dict[Prompt, str]`
2. For each `(key, text)`:
   a. Extract `{placeholder}` names from text
   b. Build standalone dict: `{name, description, key, family, text, arguments, version, source_url}`
   c. Write to `{output_dir}/{key.value.replace('.', '-')}.json` with `indent=2`
3. Print summary: "Exported N prompts to {output_dir}"

#### Edge Cases & Error Handling

- **Output directory doesn't exist:** Create it with `os.makedirs(exist_ok=True)`
- **Output directory is a file:** Raise `argparse` error or `FileExistsError`
- **Permission denied writing files:** Let the `OSError` propagate with message

### 6.3 pyproject.toml Changes

**File(s):** `pyproject.toml`
**Type:** Modified

Add optional dependency group and console_scripts entry point:

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0"]

[project.scripts]
vidbyte-prompts = "vidbyte.prompts.cli:main"
```

The `[project.scripts]` section generates a platform-appropriate executable script on `pip install`. No other sections need changes.

### 6.4 vidbyte-cli Skill: mcp-setup

**File(s):** `skills/mcp-setup/SKILL.md`
**Type:** New file

#### What it does

A prompt-type skill that teaches AI harnesses how to install and configure the Vidbyte prompts MCP server. Covers installation, configuration for 4 major platforms (Claude Desktop, Continue, Cursor, OpenCode), and verification.

#### Skill metadata

```yaml
name: mcp-setup
description: Use when the user wants to install or configure the Vidbyte MCP prompt server. Covers pip install, harness configuration, and verification.
```

#### Content outline

1. Identity: MCP setup guide persona
2. Goal: Walk user through installing vidbyte-prompts MCP server
3. Instructions:
   - Step 1: Install SDK with MCP extras (`pip install vidbyte-sdk[mcp]`)
   - Step 2: Verify (`vidbyte-prompts serve --help`)
   - Step 3: Configure harness (platform-specific config snippets for Claude Desktop, Continue, Cursor, OpenCode)
   - Step 4: Verify connectivity (restart harness, check MCP server status)
4. Troubleshooting: missing pip, Python version, permission errors

### 6.5 vidbyte-cli Skill: mcp-create-prompt

**File(s):** `skills/mcp-create-prompt/SKILL.md`
**Type:** New file

#### What it does

A prompt-type skill that teaches AI harnesses how to create a new prompt in the SDK (JSON asset, enum member, validation). Follows the existing `skills/vidbyte-sdk/adding-prompts.md` conventions from the SDK.

#### Skill metadata

```yaml
name: mcp-create-prompt
description: Use when the user wants to create a new prompt in the Vidbyte SDK that will be available via MCP. Covers JSON schema, enum registration, and validation.
```

#### Content outline

1. Identity: Prompt creation guide
2. Goal: Create a new prompt that appears in both the SDK and MCP server
3. Instructions:
   - Step 1: Create JSON asset file following schema: `{name, description, key, prompts: {leaf: text|{path}}}`
   - Step 2: Add `Prompt` enum member in `vidbyte/lib/enums/prompts.py` following `{family_key}.{leaf_name}` convention
   - Step 3: Run validation: `python -m unittest discover -s tests -p "test_prompt*"`
   - Step 4: Add bundle class in `vidbyte/prompts/strategies/strategy_prompts.py`
   - Step 5: Restart MCP server to see new prompt

### 6.6 vidbyte-cli Skill: mcp-export-prompts

**File(s):** `skills/mcp-export-prompts/SKILL.md`
**Type:** New file

#### What it does

A prompt-type skill that teaches AI harnesses how to export prompts as standalone JSON files for zero-dependency distribution.

#### Skill metadata

```yaml
name: mcp-export-prompts
description: Use when the user wants to export Vidbyte SDK prompts as standalone JSON files for use outside the SDK or for distribution.
```

#### Content outline

1. Identity: Prompt export guide
2. Goal: Export standalone prompt files
3. Instructions:
   - Step 1: Run `vidbyte-prompts export --output-dir <dir>`
   - Step 2: Describe the standalone JSON format (fields, argument extraction)
   - Step 3: Show how to use exported files with `vidbyte-prompts serve --prompts-dir <dir>` (future feature) or in custom tooling
4. Standalone format reference

### 6.7 Skills Manifest Update

**File(s):** `skills-manifest.json`
**Type:** Modified

Add three entries to the `utility` array:

```json
"utility": [
  "docs-tldr",
  "unit",
  "mcp-setup",
  "mcp-create-prompt",
  "mcp-export-prompts"
]
```

---

## 7. Data Model Changes

### 7.1 Standalone Prompt File Schema

**Change type:** New (not a database model — a file format)

```json
{
  "name": "Chain of Thought - Reason",
  "description": "Chain of Thought is a foundational reasoning strategy that instructs the model to work through a problem step by step before giving a final answer.",
  "key": "chain_of_thought.reason_prompt",
  "family": "chain_of_thought",
  "text": "Solve the task carefully by reasoning step by step...",
  "arguments": [],
  "version": "0.1.0",
  "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/chain_of_thought.json"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Human-readable display name (family name + leaf name) |
| `description` | string | yes | What this prompt does |
| `key` | string | yes | Canonical key matching `Prompt` enum value |
| `family` | string | yes | Family key (the prefix before the dot) |
| `text` | string | yes | The actual prompt text |
| `arguments` | string[] | yes | Extracted `{placeholder}` names (empty list if none) |
| `version` | string | yes | SDK version at time of export |
| `source_url` | string | no | URL to the source JSON in the SDK repo |

**Migration strategy:** N/A — this is a generated output format, not a persisted schema. No backwards compatibility concerns.

---

## 8. API Changes

### 8.1 MCP Protocol Endpoints (via stdio)

These are MCP protocol methods, not HTTP endpoints.

#### `prompts/list`

**Request:** Standard MCP `prompts/list` request (no parameters)
**Response:** `list[Prompt]` where each Prompt has:
```json
{
  "name": "chain_of_thought.reason_prompt",
  "description": "Chain of Thought is a foundational reasoning strategy...",
  "arguments": [
    {"name": "task", "description": "Value for task", "required": true}
  ]
}
```

#### `prompts/get`

**Request:**
```json
{
  "name": "chain_of_thought.reason_prompt",
  "arguments": {"task": "Explain quantum computing"}
}
```
**Response:**
```json
{
  "description": "Prompt: chain_of_thought.reason_prompt",
  "messages": [
    {
      "role": "user",
      "content": {
        "type": "text",
        "text": "Solve the task carefully by reasoning step by step.\n\nTask: Explain quantum computing"
      }
    }
  ]
}
```

**Error cases:**

| Condition | MCP error |
|-----------|-----------|
| Unknown prompt name | `{"code": -32602, "message": "Unknown prompt: {name}"}` |
| Missing required argument | `{"code": -32602, "message": "Missing argument 'task' for prompt..."}` |

---

## 9. File Change Manifest

### vidbyte-sdk

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/prompts/mcp_server.py` | MCP server implementation |
| CREATE | `vidbyte/prompts/cli.py` | CLI entry point with serve/export subcommands |
| CREATE | `tests/test_mcp_server.py` | Unit tests for MCP server and export |
| MODIFY | `pyproject.toml` | Add optional `mcp` dependency and `console_scripts` |

### vidbyte-cli

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `skills/mcp-setup/SKILL.md` | Skill for installing/configuring MCP server |
| CREATE | `skills/mcp-create-prompt/SKILL.md` | Skill for creating new prompts |
| CREATE | `skills/mcp-export-prompts/SKILL.md` | Skill for exporting prompts |
| MODIFY | `skills-manifest.json` | Register new skills under utility |

**Summary:** 7 files created, 2 files modified, 0 files deleted

---

## 10. Testing Plan

### Unit Tests (vidbyte-sdk)

Tests follow existing `unittest` conventions. New file: `tests/test_mcp_server.py`.

**`TestArgumentExtraction`:**
- `test_no_placeholders` — text with no `{...}` returns empty list
- `test_single_placeholder` — extracts one argument
- `test_multiple_placeholders` — extracts all unique names, deduplicates
- `test_nested_braces_ignored` — `{{literal}}` not treated as placeholder (if applicable)

**`TestBuildMcpPrompts`:**
- `test_returns_all_prompts` — `build_mcp_prompts()` returns 42 prompt objects
- `test_prompt_has_name` — each prompt has non-empty name matching enum convention
- `test_prompt_has_description` — each prompt has non-empty description
- `test_arguments_extracted` — VMAO prompts have arguments for `{prompt}`, `{context}`
- `test_arguments_none_when_empty` — prompts without placeholders have `arguments=None` (or empty list, per mcp SDK)

**`TestResolvePrompt`:**
- `test_resolve_known_prompt` — returns correct text
- `test_resolve_with_arguments` — substitutes `{placeholder}` values
- `test_resolve_unknown_prompt` — raises `ValueError`
- `test_resolve_missing_argument` — raises `KeyError`

**`TestExportPrompts`** (integration-style with temp dir):
- `test_export_creates_files` — exports all prompts, verifies file count
- `test_export_file_format` — reads a file, verifies JSON schema fields
- `test_export_arguments_field` — exported file includes correct arguments list
- `test_export_empty_dir` — works with empty output directory

### Integration Tests

- `vidbyte-prompts serve` starts without error (manual verification, no test harness for MCP stdio in unittest)
- `vidbyte-prompts export -o /tmp/test-prompts` writes files

### Manual Test Cases (vidbyte-cli skills)

1. **mcp-setup:** Given a fresh environment, when following the skill instructions, then `vidbyte-prompts serve --help` succeeds
2. **mcp-create-prompt:** Given skill instructions, when the AI creates a prompt JSON + enum + bundle, then `python -m unittest discover -s tests -p "test_prompt*"` passes
3. **mcp-export-prompts:** Given skill instructions, when the AI runs `vidbyte-prompts export`, then standalone JSON files are written

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| `mcp` (PyPI) | >=1.0 | MCP Python SDK for server implementation | Low — well-maintained, standard protocol library |
| `argparse` | stdlib | CLI argument parsing | None — stdlib |
| `asyncio` | stdlib | Async server loop | None — stdlib |
| `re` | stdlib | Placeholder pattern extraction | None — stdlib |

---

## 12. Rollout & Deployment

- **No feature flags** — this is an additive change with no impact on existing SDK behavior
- **No breaking changes** — existing `Prompts`, `Prompt`, strategies, and tests are untouched
- **Deployment:** `pip install vidbyte-sdk[mcp]` installs the new dependency and registers the CLI script
- **Rollback:** Remove the `[project.optional-dependencies]` and `[project.scripts]` sections from `pyproject.toml` and delete the two new Python files
- **vidbyte-cli skills** are versioned through the existing `skills-manifest.json` and installer pipeline — no additional rollout steps needed

---

## 13. Open Questions

- [ ] Should `vidbyte-prompts serve` also support `--prompts-dir <dir>` to load standalone files (in addition to the SDK catalog)? Deferred to follow-up PR.
- [ ] Should MCP prompt names use dots or slashes? (`chain_of_thought.reason_prompt` vs `chain_of_thought/reason_prompt`). Decision: use dots to match `Prompt` enum values exactly. MCP allows any string as prompt name.
- [ ] Should we add an MCP "resource" that exposes the full prompt catalog as a single JSON blob? Deferred to follow-up — likely useful for browse/discovery but not MVP.
- [ ] Should the `mcp-server` and `mcp-export` skills be "prompt" type or "learning" type? Decision: "prompt" type — they are slash-command-driven and produce direct responses/artifacts without CLI submission.

---

## 14. Alternatives Considered

### Alternative 1: Standalone prompts-only repo with GitHub Releases

- **What:** Create a separate `vidbyte-prompts` repo, auto-publish standalone JSON files on every SDK release
- **Why rejected for now:** Adds repository maintenance overhead before proving demand. Can layer on top of the export command later. The MCP server gives immediate utility without a separate repo.

### Alternative 2: MCP server in vidbyte-cli (Node.js)

- **What:** Build the MCP server in TypeScript/JavaScript as part of vidbyte-cli
- **Why rejected:** Would require duplicating or re-implementing the prompt catalog logic in another language. The Python SDK already has authoritative prompt data. Building the server where the data lives avoids sync issues.

### Alternative 3: Prompts as MCP "tools" instead of MCP "prompts"

- **What:** Expose each prompt as an executable MCP tool that takes a task string and returns rendered text
- **Why rejected:** MCP has a dedicated `prompts/` capability designed for exactly this use case (template discovery + argument-based rendering). Using tools would lose the MCP client's built-in prompt browser/selector UX.
