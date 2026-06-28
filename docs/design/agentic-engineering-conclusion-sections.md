# Design Doc: Agentic Engineering Conclusion Sections

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-28
**Last Updated:** 2026-06-28

---

## 1. Overview

Add a final conclusion section to every active Agentic Engineering Markdown file so each file closes by reinforcing the higher-order purpose of the skill instead of leaving the model focused only on exact rules, examples, or checklist mechanics. Each conclusion will be unique to the file, 7-9 sentences long, and written to steer the model toward intent-preserving judgment: use the details as tools, but optimize for the broader agentic engineering outcome.

---

## 2. Goals & Non-Goals

### Goals

- Append one final conclusion section to each active Agentic Engineering prompt-family Markdown file.
- Append one final conclusion section to the on-disk `agentic-engineering` meta-skill because the user explicitly requested reading that skill before implementation and it governs this prompt family.
- Keep each conclusion unique, purpose-specific, and 7-9 sentences long.
- Make each conclusion discourage over-indexing on exact wording, examples, or checklist items when the higher-order use case calls for judgment.
- Preserve the existing prompt-family catalog structure, enum values, README rows, and package data configuration.

### Non-Goals

- No new Agentic Engineering principle will be added.
- No prompt catalog keys, enum members, source URLs, or direct imports will change.
- No existing sections will be renamed, deleted, or reordered.
- No tests, runtime behavior, SDK APIs, or package metadata will change.
- No unrelated dirty worktree files, generated `.pyc` files, or existing untracked design docs will be cleaned up.

---

## 3. Background & Context

The Vidbyte SDK is a Python package (`pyproject.toml`, Python >=3.11) with prompt assets packaged through `tool.setuptools.package-data`. The Agentic Engineering prompt family lives under `vidbyte/prompts/prompts/agentic_engineering/` and is registered by `agentic_engineering.json` with five Markdown prompt assets: `system_prompt.md`, `error_messages.md`, `file_headers.md`, `folder_readme.md`, and `function_design.md`. The family is exposed through `Prompt.AGENTIC_ENGINEERING_*` enum members in `vidbyte/lib/enums/prompts.py`; since this change only edits Markdown text files, no enum or JSON registration change is needed.

The repository also has an on-disk meta-skill at `vidbyte/prompts/skills/agentic-engineering.md`. That file is not part of the import-validated prompt catalog, but `vidbyte/prompts/README.md` documents it as "Agentic Engineering Skill" and the user explicitly asked to read the agentic engineering skill file before implementation. Including it keeps the update aligned with the user's "all agentic engineering skill files" wording while leaving catalog behavior unchanged.

Current worktree status includes many modified generated `__pycache__/*.pyc` files and several unrelated untracked design docs. Those are pre-existing or generated artifacts and will not be modified, deleted, staged, or reverted as part of this task.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
2. `vidbyte/prompts/prompts/agentic_engineering/error_messages.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
3. `vidbyte/prompts/prompts/agentic_engineering/file_headers.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
4. `vidbyte/prompts/prompts/agentic_engineering/folder_readme.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
5. `vidbyte/prompts/prompts/agentic_engineering/function_design.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
6. `vidbyte/prompts/skills/agentic-engineering.md` must end with a new `<conclusion>` section containing exactly one paragraph of 7-9 sentences, matching that file's XML-like section convention.
7. Each conclusion must be different from the others and must be specific to the purpose of that file.
8. Each conclusion must explicitly or implicitly steer the model away from rigidly copying examples, field names, section counts, or checklist mechanics when those details conflict with the file's higher-order intent.
9. Each conclusion must preserve the file's existing style: direct, operational, no emoji, no markdown callouts, no YAML blocks, and no unrelated implementation examples.
10. The prompt catalog must continue to load the Agentic Engineering family with the same five sub-prompt keys after the Markdown edits.

### Non-Functional Requirements

- Performance targets: N/A - Markdown-only prompt content update.
- Scalability considerations: N/A - No runtime code path changes.
- Security requirements: Preserve existing warning boundaries; especially do not weaken `error_messages.md` guidance about not exposing internal server diagnostics to clients.
- Observability: N/A - No logging, metrics, or tracing changes.
- Reliability / error tolerance: Avoid malformed Markdown structure or accidental fenced-code continuation at EOF; ensure every appended conclusion is outside existing code fences.

---

## 5. High-Level Design

The implementation will append a final conclusion section to the six target Markdown files. The five prompt-family assets will use `# Conclusion` because they already use top-level Markdown headings for major sections. The meta-skill will use `<conclusion>` because its major sections use XML-like tags (`<identity>`, `<structure>`, `<criteria>`, and so on).

Each conclusion will act as an intent anchor. It will tell the model that the file's rules, examples, and checklists are operational scaffolding, not the final objective. The desired behavior is not to imitate a sample literally, but to preserve the agentic engineering value the file teaches: reducing context-window cost, improving navigation, making failures self-diagnosing, preserving folder intent, or keeping functions small enough to reason about.

No data flow, runtime loader flow, enum registration, or package layout changes are involved.

```text
Markdown prompt file -> append final conclusion section -> catalog still reads same file path

On-disk meta-skill -> append XML-style conclusion section -> documented skill behavior clarified
```

---

## 6. Detailed Design

### 6.1 Agentic Engineering System Prompt

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md`
**Type:** Modified

#### What it does

The system prompt is the routing entry point for the Agentic Engineering family. Its conclusion will reinforce that the model should use the system prompt to select and load relevant principles, but should keep the broader two-audience code-quality purpose in view.

#### Interface / API

```markdown
# Conclusion

<one 7-9 sentence paragraph>
```

#### Logic / Algorithm

1. Append the section after the final principle entry.
2. Write 7-9 sentences focused on routing, judgment, and the family-level purpose.
3. Mention that the principle list is a map, not a substitute for reading the deep-dive files.

#### Edge Cases & Error Handling

- If future principles are added before this change lands, keep the conclusion after the full principle list.
- Do not add checklist items or new principle entries.

### 6.2 Error Messages Principle

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/error_messages.md`
**Type:** Modified

#### What it does

This principle teaches server-side errors as self-contained diagnostic packets. Its conclusion will reinforce that the schema exists to make failures self-diagnosing for downstream agents, not to encourage fake completeness or rigid cargo-culting of sample fields.

#### Interface / API

```markdown
# Conclusion

<one 7-9 sentence paragraph>
```

#### Logic / Algorithm

1. Append the section after the final Python code fence.
2. Write 7-9 sentences focused on diagnostic usefulness, truthful context, and intent over mechanical field stuffing.
3. Preserve the server-side-only safety boundary.

#### Edge Cases & Error Handling

- Verify the conclusion is outside the final code fence.
- Avoid weakening required field guidance; the conclusion should explain how to apply it with judgment, not make it optional.

### 6.3 File Headers Principle

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/file_headers.md`
**Type:** Modified

#### What it does

This principle teaches structured file headers as navigational landmarks. Its conclusion will reinforce that the header's purpose is fast orientation and architectural contract preservation, not filling every possible section with brittle or low-signal prose.

#### Interface / API

```markdown
# Conclusion

<one 7-9 sentence paragraph>
```

#### Logic / Algorithm

1. Append the section after the `# Things Not to Do` section.
2. Write 7-9 sentences focused on orientation, durable intent, and stale-header prevention.
3. Emphasize that the header should help an agent decide whether and how to edit the file.

#### Edge Cases & Error Handling

- Do not contradict the file's current strong requirements for complete applicable sections.
- Avoid adding new header schema requirements.

### 6.4 Folder README Principle

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/folder_readme.md`
**Type:** Modified

#### What it does

This principle teaches folder READMEs as comprehension caches. Its conclusion will reinforce that the README is meant to preserve folder-level intent, routing signal, and negative knowledge, not to become an exhaustive duplicate of source files or sibling READMEs.

#### Interface / API

```markdown
# Conclusion

<one 7-9 sentence paragraph>
```

#### Logic / Algorithm

1. Append the section after the example README code fence.
2. Write 7-9 sentences focused on folder-level routing and durable memory.
3. Warn against over-indexing on the example's exact folder, bullets, or wording.

#### Edge Cases & Error Handling

- Verify the conclusion is outside the example code fence.
- Preserve the existing generated-versus-authored split.

### 6.5 Function Design Principle

**File(s):** `vidbyte/prompts/prompts/agentic_engineering/function_design.md`
**Type:** Modified

#### What it does

This principle teaches functions as small, named units of comprehension and change. Its conclusion will reinforce that line counts, naming tests, and argument limits exist to preserve readable units of behavior, not to reward arbitrary fragmentation or mechanical extraction.

#### Interface / API

```markdown
# Conclusion

<one 7-9 sentence paragraph>
```

#### Logic / Algorithm

1. Append the section after the final example code fence.
2. Write 7-9 sentences focused on one-function-one-purpose judgment.
3. Clarify that decomposition should preserve semantic clarity and avoid useless indirection.

#### Edge Cases & Error Handling

- Verify the conclusion is outside the final code fence.
- Do not relax the existing function requirements; frame them as signals for judgment.

### 6.6 Agentic Engineering Meta-Skill

**File(s):** `vidbyte/prompts/skills/agentic-engineering.md`
**Type:** Modified

#### What it does

The meta-skill teaches models how to add new principles to the Agentic Engineering prompt family. Its conclusion will reinforce that the procedure is meant to protect family cohesion and agent-facing utility, not to turn every interesting coding idea into a new principle.

#### Interface / API

```markdown
<conclusion>
<one 7-9 sentence paragraph>
</conclusion>
```

#### Logic / Algorithm

1. Append the section after `</rules>`.
2. Write 7-9 sentences focused on qualification judgment, cohesion, and not over-indexing on the current file list or examples.
3. Preserve the instruction that weak principles should not be added.

#### Edge Cases & Error Handling

- Do not update stale count text in the meta-skill's identity section unless explicitly approved as part of implementation; this task is scoped to adding conclusions.
- Do not alter the procedure or catalog integration rules.

---

## 7. Data Model Changes

N/A - No schema, type, database, JSON descriptor, or enum data model changes.

---

## 8. API Changes

N/A - No public SDK APIs, HTTP endpoints, MCP methods, prompt keys, enum values, or direct import names change.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agentic-engineering-conclusion-sections.md` | Design doc for the requested Markdown prompt updates |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Add family-level conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/error_messages.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/file_headers.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/folder_readme.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/function_design.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/skills/agentic-engineering.md` | Add meta-skill conclusion paragraph |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| N/A | N/A | No new dependencies or external services | N/A |

---

## 11. Rollout & Deployment

- Feature flags: N/A - Markdown-only content update.
- Breaking change: No. Existing prompt keys and imports remain stable.
- Deployment order: Merge the Markdown updates with the design doc in one PR.
- Rollback procedure: Revert the commit that appends the conclusion sections and removes this design doc, or manually delete the appended `# Conclusion` / `<conclusion>` sections.

---

## 12. Open Questions

- [ ] Confirm whether `vidbyte/prompts/skills/agentic-engineering.md` should receive a conclusion too. This design includes it because the user explicitly referenced the skill file and asked for all Agentic Engineering skill files, but it is not part of the `agentic_engineering` prompt-family catalog.
- [ ] Confirm whether unrelated stale wording in `vidbyte/prompts/skills/agentic-engineering.md` ("currently has two principles") should remain untouched. This design keeps it unchanged to avoid scope creep.

---

## 13. Alternatives Considered

### Alternative 1: Update Only The Five Prompt-Family Files

- What: Append conclusions only to `vidbyte/prompts/prompts/agentic_engineering/*.md`.
- Why rejected: The user specifically said to read the Agentic Engineering skill file before implementation and referred to "skill files"; excluding the on-disk meta-skill could miss the most literal interpretation.

### Alternative 2: Add A Shared Generic Conclusion To Every File

- What: Use one reusable conclusion paragraph across all files.
- Why rejected: The user explicitly requested each conclusion be different for each skill file. A shared paragraph would satisfy the section shape but not the task intent.

### Alternative 3: Add The Conclusion Text To The JSON Description Or README

- What: Update `agentic_engineering.json` and `vidbyte/prompts/README.md` descriptions instead of each Markdown file.
- Why rejected: The user asked for a paragraph at the end of each file. Catalog descriptions and README entries are indexes, not the per-file prompt text the model reads during use.
