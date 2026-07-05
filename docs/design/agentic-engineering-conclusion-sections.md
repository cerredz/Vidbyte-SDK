# Design Doc: Agentic Engineering Conclusion Sections

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-28
**Last Updated:** 2026-07-04

---

## 1. Overview

Add a final conclusion section to every active Agentic Engineering Markdown file so each file closes by reinforcing the higher-order purpose of the skill instead of leaving the model focused only on exact rules, examples, or checklist mechanics. Each conclusion is unique to the file, 7-9 sentences long, and written to steer the model toward intent-preserving judgment: use the details as tools, but optimize for the broader agentic engineering outcome.

---

## 2. Goals & Non-Goals

### Goals

- Append one final conclusion section to each active Agentic Engineering prompt-family Markdown file.
- Include the two prompt-family files added after the original PR: `intent_based_commenting.md` and `feature_test_packs.md`.
- Append one final conclusion section to the on-disk `agentic-engineering` meta-skill because it governs this prompt family.
- Keep each conclusion unique, purpose-specific, and 7-9 sentences long.
- Preserve the existing prompt-family catalog structure, enum values, README rows, and package data configuration.

### Non-Goals

- No new Agentic Engineering principle will be added.
- No prompt catalog keys, enum members, source URLs, or direct imports will change.
- No existing sections will be renamed, deleted, or reordered.
- No tests, runtime behavior, SDK APIs, or package metadata will change.

---

## 3. Background & Context

The Vidbyte SDK ships static prompt assets under `vidbyte/prompts/prompts/`. The Agentic Engineering family is registered by `agentic_engineering.json` and currently contains seven Markdown prompt assets: `system_prompt.md`, `error_messages.md`, `file_headers.md`, `folder_readme.md`, `function_design.md`, `intent_based_commenting.md`, and `feature_test_packs.md`. The original PR covered the first five prompt assets and the meta-skill, but review noted that more Agentic Engineering skills had been pushed and needed the same conclusion treatment.

The repository also has an on-disk meta-skill at `vidbyte/prompts/skills/agentic-engineering.md`. That file is not part of the import-validated prompt catalog, but `vidbyte/prompts/README.md` documents it as "Agentic Engineering Skill" and it defines how the prompt family grows.

---

## 4. Requirements

1. `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
2. `vidbyte/prompts/prompts/agentic_engineering/error_messages.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
3. `vidbyte/prompts/prompts/agentic_engineering/file_headers.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
4. `vidbyte/prompts/prompts/agentic_engineering/folder_readme.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
5. `vidbyte/prompts/prompts/agentic_engineering/function_design.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
6. `vidbyte/prompts/prompts/agentic_engineering/intent_based_commenting.md` must end with a new `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
7. `vidbyte/prompts/prompts/agentic_engineering/feature_test_packs.md` must end with a `# Conclusion` section containing exactly one paragraph of 7-9 sentences.
8. `vidbyte/prompts/skills/agentic-engineering.md` must end with a new `<conclusion>` section containing exactly one paragraph of 7-9 sentences, matching that file's XML-like section convention.
9. Each conclusion must be different from the others and specific to the purpose of that file.
10. The prompt catalog must continue to load the Agentic Engineering family with the same seven sub-prompt keys after the Markdown edits.

---

## 5. High-Level Design

The implementation appends a final conclusion section to the current Agentic Engineering prompt files. The prompt-family assets use `# Conclusion` because they use Markdown headings for major sections. The meta-skill uses `<conclusion>` because its major sections use XML-like tags.

Each conclusion acts as an intent anchor. It tells the model that the file's rules, examples, and checklists are operational scaffolding, not the final objective. The desired behavior is not to imitate a sample literally, but to preserve the agentic engineering value the file teaches: reducing context-window cost, improving navigation, making failures self-diagnosing, preserving folder intent, keeping functions small enough to reason about, preserving domain meaning, or turning tests into executable feature intent.

No data flow, runtime loader flow, enum registration, or package layout changes are involved.

---

## 6. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agentic-engineering-conclusion-sections.md` | Design doc for the requested Markdown prompt updates |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/system_prompt.md` | Add family-level conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/error_messages.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/file_headers.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/folder_readme.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/function_design.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/intent_based_commenting.md` | Add principle-specific conclusion paragraph |
| MODIFY | `vidbyte/prompts/prompts/agentic_engineering/feature_test_packs.md` | Expand the existing conclusion to the required length and specificity |
| MODIFY | `vidbyte/prompts/skills/agentic-engineering.md` | Add meta-skill conclusion paragraph |

---

## 7. Verification

Run the SDK prompt verification commands after implementation:

```bash
python -m compileall vidbyte
python -c "from vidbyte.prompts import Prompts; p = Prompts(); print(p.family('agentic_engineering').keys())"
```

The expected result is that the SDK compiles and the Agentic Engineering family still returns the seven registered sub-prompts.
