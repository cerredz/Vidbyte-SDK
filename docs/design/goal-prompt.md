# Design Doc: Goal and Mimic Behavior Prompt Assets

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-23
**Last Updated:** 2026-05-25

## 1. Overview

Add two long-form prompt families to the Vidbyte SDK:

- `goals.goal_prompt`: a system prompt that mimics Codex-style goal behavior without telling the model that it is operating inside Codex or has access to the native `/goal` tool.
- `mimic_behavior.mimic_prompt`: a system prompt that turns uploaded source material into an immensely detailed prompt optimized to mimic the source material's observable behavior.

Both prompt bodies live in Markdown files. Their JSON descriptors stay in `vidbyte/prompts/prompts/` and reference the GitHub URL for each Markdown file.

## 2. Goals

- Add folder-based prompt assets under `vidbyte/prompts/prompts/goals/` and `vidbyte/prompts/prompts/mimic_behavior/`.
- Load Markdown prompt text through the existing `Prompts` and `Prompt` APIs.
- Preserve compatibility with existing root-level JSON prompt assets.
- Expose direct imports: `goals_goal_prompt` and `mimic_behavior_mimic_prompt`.
- Update the add-prompt skill guide so future prompt assets use JSON descriptors plus Markdown prompt files.

## 3. Non-Goals

- Do not add runtime prompt overrides.
- Do not fetch prompt text from GitHub at runtime.
- Do not claim that non-Codex models have native `/goal` lifecycle commands.
- Do not migrate every existing prompt family in this change.

## 4. Asset Format

New long-form prompt families use this structure:

```text
vidbyte/prompts/prompts/goals/
|-- goals.json
`-- goal_prompt.md

vidbyte/prompts/prompts/mimic_behavior/
|-- mimic_behavior.json
`-- mimic_prompt.md
```

JSON descriptor example:

```json
{
  "name": "Goal Behavior",
  "description": "A prompt family description.",
  "key": "goals",
  "prompts": {
    "goal_prompt": {
      "path": "goal_prompt.md",
      "source_url": "https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/goals/goal_prompt.md"
    }
  }
}
```

The catalog reads `path` locally and treats `source_url` as reviewable metadata. This avoids network access during imports and keeps installed package behavior deterministic.

## 5. Catalog Changes

`vidbyte/prompts/catalog.py` continues to load root-level `*.json` files. It also discovers one-level nested JSON descriptors and supports two prompt value forms:

- `str`: legacy inline prompt text.
- `{ "path": "<prompt>.md", "source_url": "<github url>" }`: Markdown-backed prompt text.

The public API remains unchanged:

```python
from vidbyte.prompts import Prompts, goals_goal_prompt, mimic_behavior_mimic_prompt
from vidbyte.lib.enums.prompts import Prompt

prompts = Prompts()
assert prompts.get(Prompt.GOALS_GOAL_PROMPT) == goals_goal_prompt
assert prompts.get(Prompt.MIMIC_BEHAVIOR_MIMIC_PROMPT) == mimic_behavior_mimic_prompt
```

## 6. Prompt Behavior

The goals prompt teaches a model to emulate a goal-driven work loop: preserve an objective, audit against evidence, continue while useful work remains, and stop only on completion, blocker, budget limit, or user direction. It explicitly avoids claiming native Codex tool access.

The mimic behavior prompt instructs a model to inspect uploaded source material and produce a standalone prompt that mimics observable behavior: structure, method, tone, evidence habits, decision rules, format, constraints, and quality bar. It emphasizes behavior over verbatim copying.

## 7. Testing

Verification should cover:

- `python -m compileall vidbyte`
- `python -m unittest discover -s tests`
- `Prompts().get(Prompt.GOALS_GOAL_PROMPT)` returns Markdown text.
- `Prompts().get(Prompt.MIMIC_BEHAVIOR_MIMIC_PROMPT)` returns Markdown text.
- Direct imports match enum lookups.

## 8. Rollback

Remove the two prompt folders, remove the two enum members, revert the catalog Markdown-loading changes, remove the package-data globs, and revert the tests and add-prompt guide updates.
