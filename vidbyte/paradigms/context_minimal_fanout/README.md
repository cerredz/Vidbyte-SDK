# Context Minimal Fanout

`context_minimal_fanout` is the paradigm family for reducing implementation
agent context load by decomposing one broad request into smaller ownership
areas. On this branch, the package ships distributable external-harness skills;
runnable Python harness implementations can be added separately.

## Role In The SDK

This package is an importable asset package so the SDK wheel can include
context-minimal fanout skill files. The files are consumed by
`vidbyte.skills.Skills` through `importlib.resources`.

## Design Philosophy

Skills are adapters and operating instructions for external coding harnesses.
They are not the canonical SDK implementation of a paradigm. The skill files
teach a harness how to gather context, decompose work, persist plans, enforce
ownership boundaries, and optionally fan out to subagents.

## Usage

```python
from vidbyte.skills import ContextMinimalFanoutSkill, Skills

skills = Skills()
skills.materialize(
    ContextMinimalFanoutSkill.DECOMPOSE_FANOUT,
    ".claude/skills",
)
```

## Skills

- `decompose-then-implement/`: gather context, write a subtask plan, and solve
  subtasks sequentially.
- `decompose-design-then-implement/`: gather context, write a design doc per
  subtask, and implement designs sequentially.
- `decompose-design-fanout/`: write design docs, launch one subagent per design
  doc, then merge and report.
- `decompose-fanout/`: write a non-overlapping split plan, launch one subagent
  per subtask, then merge and report.
- `references/harness-commands.md`: shared command examples for Claude Code,
  Codex CLI, OpenCode, Cursor CLI, Gemini CLI, and unknown platforms.

## Key Modules

- `skills/skills.json`: package-local manifest consumed by `vidbyte.skills`.
- `skills/*/SKILL.md`: distributable skill instructions.
- `skills/references/harness-commands.md`: shared fanout command reference.

## Related Layers

See [`vidbyte.skills`](../../skills/README.md) for the registry and
[`vidbyte.paradigms`](../README.md) for the broader paradigm namespace.
