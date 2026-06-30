---
name: context-minimal-fanout
description: Split one large coding request into multiple non-overlapping prompts, write the split plan to Markdown, and run each prompt in isolated subagents so each branch uses a smaller context window.
---

# Context Minimal Fanout

<identity>
You are using the context-minimal fanout paradigm. Your job is to reduce context
load by turning one large implementation request into multiple independent
implementation prompts, then running each prompt in a fresh subagent context.
</identity>

<intent>
Use this when a request is broad enough that one agent would fill too much of
the context window with unrelated files, history, or reasoning. The goal is not
to split work arbitrarily. The goal is to create independent ownership areas so
each subagent can focus on a smaller prompt without conflicting with the others.
</intent>

<workflow>
1. Read all repository context needed to understand the request before splitting.
2. Identify separable ownership areas: files, public contracts, tests, docs,
   configs, migrations, verification commands, or user-visible surfaces.
3. Write a Markdown split plan before running subagents.
4. Ensure no two prompts overlap in owned files, owned contracts, test files,
   migrations, generated artifacts, or verification obligations.
5. Run each implementation prompt in a subagent for the current run.
6. Collect every subagent output and report conflicts, blockers, verification,
   and remaining integration work.
</workflow>

<markdown_plan>
Write the split plan to a `.md` file with this structure:

```markdown
# Context Minimal Fanout Split Plan

## Goal
...

## Instructions
...

## Non-Overlap Requirements
- ...

## Implementation Prompts

### <id>: <title>

#### Prompt
...

#### Owned Paths
- ...

#### Read-Only Paths
- ...

#### Commands
- ...

#### Notes
- ...
```
</markdown_plan>

<non_overlap>
Prompts are non-overlapping only when each has a distinct ownership boundary.
Two prompts must not both own the same file path, public API contract, test
file, migration, generated artifact, or verification responsibility. Shared
context goes under read-only paths. If two prompts must edit the same ownership
area, merge them into one prompt.
</non_overlap>

<subagent_prompt>
Each subagent prompt must include:

- The global goal.
- The global instructions.
- The branch-specific prompt.
- Owned paths.
- Read-only paths.
- Commands or verification requirements.
- A reminder not to cross another branch's ownership boundary.
</subagent_prompt>

<rules>
- Do not run subagents before writing the Markdown split plan.
- Do not split work before reading enough repo context to understand ownership.
- Do not use vague prompts such as "handle backend" or "fix tests"; specify
  ownership and outputs.
- Do not assign the same mutable file or contract to multiple prompts.
- Do not hide conflicts. If a clean split is impossible, say so and merge the
  coupled work into one prompt.
- Do not treat the split plan as final truth if subagents report conflicts;
  surface those conflicts in the final response.
</rules>
