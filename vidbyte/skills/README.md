# Skills

`vidbyte.skills` is the registry for distributable Vidbyte skill file trees.
Skills are operating instructions that downstream developers can install into
external coding harnesses such as Claude Code, Codex, OpenCode, Cursor, and
Gemini CLI.

## Role In The SDK

The skills registry exposes packaged Markdown skill assets through enum keys.
It is the sibling of `vidbyte.prompts`: prompts are plain text templates, while
skills are file trees with install semantics. The registry lets developers list,
read, inspect, and materialize packaged skills from Python code.

## Design Philosophy

Skill assets should be repository-backed, packaged in the wheel, and validated
against a central manifest. The catalog validates enum sync, required files,
frontmatter, and folder sync before returning records. `materialize()` writes a
skill folder and declared references to a caller-provided directory without
network access or extra dependencies.

## Usage

```python
from vidbyte.skills import Skill, Skills

skills = Skills()
record = skills.get(Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT)
print(record.description)
print(skills.text(Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT))

skills.materialize(
    Skill.CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT,
    ".claude/skills",
)
```

Module CLI:

```bash
python -m vidbyte.skills list
python -m vidbyte.skills install context_minimal_fanout.decompose_fanout --dest .claude/skills
```

## Available Skills

This table is the human- and machine-readable index of distributable skills
shipped by the SDK.

| Skill | Key | Files | Link |
| --- | --- | --- | --- |
| Decompose Then Implement | `context_minimal_fanout.decompose_then_implement` | `decompose-then-implement/SKILL.md` | [SKILL.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/paradigms/context_minimal_fanout/skills/decompose-then-implement/SKILL.md) |
| Decompose, Design, Then Implement | `context_minimal_fanout.decompose_design_then_implement` | `decompose-design-then-implement/SKILL.md` | [SKILL.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/paradigms/context_minimal_fanout/skills/decompose-design-then-implement/SKILL.md) |
| Decompose, Design, Fanout | `context_minimal_fanout.decompose_design_fanout` | `decompose-design-fanout/SKILL.md`, `references/harness-commands.md` | [SKILL.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/paradigms/context_minimal_fanout/skills/decompose-design-fanout/SKILL.md) |
| Decompose Fanout | `context_minimal_fanout.decompose_fanout` | `decompose-fanout/SKILL.md`, `references/harness-commands.md` | [SKILL.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/paradigms/context_minimal_fanout/skills/decompose-fanout/SKILL.md) |

Shared command reference:
[`references/harness-commands.md`](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/paradigms/context_minimal_fanout/skills/references/harness-commands.md).

## Key Modules

- `catalog.py`: skill manifest loading, validation, file access, and
  materialization.
- `__init__.py`: public imports for `Skill`, `SkillRecord`, and `Skills`.
- `__main__.py`: small `python -m vidbyte.skills` wrapper for list and install.

## Adding Future Paradigm Skills

Each paradigm that ships skills should place a `skills/skills.json` manifest
inside an importable `vidbyte.paradigms.<family>` package. The catalog keeps its
public API stable while adding future families by appending their package names
to `Skills._manifest_packages`. Each manifest remains package-local so future
paradigms can add assets without changing existing skill keys or materialize
behavior.

## Related Layers

Skills currently ship from [`paradigms`](../paradigms/README.md). Existing
on-disk prompt helper skills under `vidbyte/prompts/skills/` remain outside this
registry and may be consolidated in a future change.
