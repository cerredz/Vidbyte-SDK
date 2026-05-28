# Add MCP Preset — Skill Prompt

This skill walks through every step required to add a new built-in MCP server preset to the Vidbyte SDK. Follow it exactly; each step is load-bearing.

---

## Overview of the Architecture

All preset data lives in one place:

```
vidbyte/lib/config/mcp_presets.py   ← canonical preset definitions (McpPresetDefinition constants)
vidbyte/tools/mcp/presets.py        ← McpPresetRegistry class with ClassVar attributes
vidbyte/tools/mcp/__init__.py       ← public re-exports for user-facing imports
```

Users access presets in two ways after your addition:
1. **Direct import**: `from vidbyte.tools.mcp import BraveSearchMCP`
2. **Registry attribute**: `McpPresetRegistry.BraveSearch`

---

## Step 1 — Choose a Preset Name and Python Identifier

Pick a kebab-case `name` string that is unique in the catalog.

Derive the Python identifier from it:
- Split on `-`
- Capitalize each segment
- Join → **PascalCase**

Examples:
| Kebab name          | PascalCase       | Import constant        | Registry attr      |
|---------------------|------------------|------------------------|--------------------|
| `brave-search`      | `BraveSearch`    | `BraveSearchMCP`       | `BraveSearch`      |
| `aws-s3`            | `AwsS3`          | `AwsS3MCP`             | `AwsS3`            |
| `pdf-parser`        | `PdfParser`      | `PdfParserMCP`         | `PdfParser`        |
| `sequential-thinking` | `SequentialThinking` | `SequentialThinkingMCP` | `SequentialThinking` |

---

## Step 2 — Gather the Preset Metadata

You need:

| Field          | Type                  | Notes |
|----------------|-----------------------|-------|
| `name`         | `str`                 | Unique kebab-case key used in `McpPresetRegistry.get("name")` |
| `category`     | `str`                 | Must match one of the existing category strings exactly (see catalog) |
| `description`  | `str`                 | One sentence explaining what the server does for an agent |
| `command`      | `tuple[str, ...]`     | Full subprocess argv, e.g. `("npx", "-y", "@scope/pkg")` or `("python", "-m", "module")` |
| `required_env` | `tuple[str, ...]`     | Env vars the user *must* supply; leave empty `()` if none |
| `optional_env` | `tuple[str, ...]`     | Env vars the user *may* supply (default `()`) |
| `default_env`  | `Mapping[str,str]\|None` | Hard-coded env defaults baked into every invocation (default `None`) |
| `docs_url`     | `str \| None`         | Link to official docs (default `None`) |

Existing categories (copy exactly):
- `"Search & Web Research"`
- `"Version Control, Development & Task Tracking"`
- `"Databases & Cache"`
- `"Productivity, Office & CRM"`
- `"Document Parsers & Media Utilities"`
- `"Communication & Chat"`
- `"Cloud Platforms, Hosting & Infrastructure"`
- `"AI Platforms & Creative APIs"`
- `"Reference & Academic"`
- `"Native System & Utilities"`

If the new preset belongs to a genuinely new category, add the category string and a new section header comment in `mcp_presets.py`.

---

## Step 3 — Add the Constant to `vidbyte/lib/config/mcp_presets.py`

Open `vidbyte/lib/config/mcp_presets.py`.

1. Find the section comment for the correct category (e.g. `# ─── Databases & Cache ───`).
2. Append the new constant **at the end of that section**, before the next section comment.

```python
MyNewServerMCP = McpPresetDefinition(
    name="my-new-server",
    category="Databases & Cache",
    description="One sentence describing what the agent can do with this server.",
    command=("npx", "-y", "@scope/mcp-server-my-new"),
    required_env=("MY_NEW_API_KEY",),
)
```

3. Add `MyNewServerMCP` to the `ALL_PRESETS` list in the correct category group at the bottom of the file.

4. Add `"MyNewServerMCP"` to `__all__` in the correct category group.

---

## Step 4 — Add the Class Attribute to `vidbyte/tools/mcp/presets.py`

Open `vidbyte/tools/mcp/presets.py`.

1. Add `MyNewServerMCP` to the import block at the top (inside the `from vidbyte.lib.config.mcp_presets import (...)` statement), in the correct category comment group.

2. Find the correct category section in the `McpPresetRegistry` class body and append:

```python
MyNewServer: ClassVar[McpPresetDefinition] = MyNewServerMCP
```

3. Add `"MyNewServerMCP"` to `__all__` in the correct category group at the bottom.

---

## Step 5 — Re-export from `vidbyte/tools/mcp/__init__.py`

Open `vidbyte/tools/mcp/__init__.py`.

1. Add `MyNewServerMCP` to the `from vidbyte.tools.mcp.presets import (...)` block, in the correct category comment group.

2. Add `"MyNewServerMCP"` to `__all__` in the correct category group.

---

## Step 6 — Verify

Run the import smoke-test from the repo root:

```bash
python -c "
from vidbyte.tools.mcp import MyNewServerMCP, McpPresetRegistry
assert McpPresetRegistry.get('my-new-server') is MyNewServerMCP
assert McpPresetRegistry.MyNewServer is MyNewServerMCP
print('OK')
"
```

Run the existing preset test suite to confirm no regressions:

```bash
python scripts/test-preset-mcp-servers.py
```

---

## Step 7 — Checklist Before Committing

- [ ] `McpPresetDefinition` constant defined in `vidbyte/lib/config/mcp_presets.py`
- [ ] Added to `ALL_PRESETS` list in `mcp_presets.py`
- [ ] Added to `__all__` in `mcp_presets.py`
- [ ] Imported and assigned as `ClassVar` in `McpPresetRegistry` in `presets.py`
- [ ] Added to `__all__` in `presets.py`
- [ ] Imported and re-exported in `vidbyte/tools/mcp/__init__.py`
- [ ] Added to `__all__` in `__init__.py`
- [ ] Smoke-test passes (`python -c "..."` above)
- [ ] `python scripts/test-preset-mcp-servers.py` passes

---

## Naming Convention Summary

| Layer                        | Pattern                  | Example               |
|------------------------------|--------------------------|-----------------------|
| Config constant              | `{PascalCase}MCP`        | `BraveSearchMCP`      |
| Registry class attribute     | `{PascalCase}` (no suffix) | `McpPresetRegistry.BraveSearch` |
| Kebab name (runtime key)     | `{kebab-case}`           | `"brave-search"`      |
| User import                  | `from vidbyte.tools.mcp import {PascalCase}MCP` | `BraveSearchMCP` |
