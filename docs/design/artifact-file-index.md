# Design Doc: Repository Artifact — `file_index.md`

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

This feature adds the first entry in a new `artifacts/` directory at the root of the
`vidbyte-sdk` repo: `artifacts/file_index.md`. It is a compressed, prose-first,
code-free companion to the existing `llms.txt`. Where `llms.txt` bundles full docs
and code snippets for LLM ingestion, `file_index.md` gives a human or agent a fast
structural map of the repository — a thick multi-paragraph description of what the
SDK is, a recursive folder-by-folder index with a short responsibility blurb per
directory, and a short statement of the design principles the SDK is built around.

---

## 2. Goals & Non-Goals

### Goals
- Create a new `artifacts/` directory (the repo's first artifact folder).
- Create `artifacts/file_index.md` containing exactly three sections:
  1. **Overview** — several thick paragraphs describing what the Vidbyte SDK actually is.
  2. **File Index** — a recursive list of every folder in the repo, each with its path and a 3–4 sentence description of its role.
  3. **General Principles** — the four stated SDK principles, written out.
- Keep the file **code-free** (no code fences / snippets) — it is a compressed structural map, not a tutorial.
- Cover folders recursively, including subfolders, for the meaningful source tree.

### Non-Goals
- Not replacing or editing `llms.txt`, `README.md`, or any existing doc.
- Not documenting individual files (the index is folder-level, not file-level).
- Not indexing generated / vendored / ephemeral dirs (`.git`, `__pycache__`, `.pytest_cache`, `*.egg-info`, nested `worktree-*` checkouts inside the repo).
- No tests or verification scripts (this is a docs-only artifact; `/design-doc-no-tests`).

---

## 3. Background & Context

The repo already ships `llms.txt` (~37 KB): a rich, code-heavy documentation bundle
aimed at LLM retrieval and Context7-style indexing. It is excellent for "how do I use
feature X" but poor as a **map** — a reader cannot glance at it and understand the
folder topology. The user wants a lighter artifact that answers "what is this repo and
where does everything live" in one screenful of scanning. This is the seed of a broader
`artifacts/` concept for the repo, so the structure should be clean and repeatable.

Constraints:
- Content must be derivable from the current tree and the existing README/`llms.txt` — no invented APIs.
- The active branch is `feat/context-minimal-fanout-trace`; per the skill, implementation happens on a fresh `feat/` worktree branched from `main`.

---

## 4. Requirements

### Functional Requirements
1. A new directory `artifacts/` MUST exist at the repo root.
2. A file `artifacts/file_index.md` MUST exist with a top-level title and three sections in this order: Overview, File Index, General Principles.
3. The Overview section MUST be multiple thick paragraphs (not bullets) describing what the SDK is, its mental model, and its public boundary.
4. The File Index section MUST include a short lead-in description, then list **every** meaningful folder in the repo recursively.
5. Each folder entry MUST include its repo-relative path and 3–4 sentences describing what it does.
6. The General Principles section MUST contain the four stated principles: (a) ship all primitives a harness needs out of the box, (b) bring unique first-party abstractions, (c) be highly extensible/customizable, (d) be easy for the developer to use.
7. The file MUST contain no code blocks or code snippets.

### Non-Functional Requirements
- **Accuracy:** every listed path must exist in the tree; every blurb must reflect actual folder contents.
- **Scannability:** consistent formatting per entry (path as heading/inline code, then prose).
- **Maintainability:** ordering follows the physical tree so future folders slot in obviously.
- **Observability / Security / Performance:** N/A — static markdown artifact.

---

## 5. High-Level Design

One new file is authored by hand from the audited tree. The folder inventory is taken
from a recursive directory walk of `vidbyte/`, `skills/`, `docs/`, `scripts/`, and
`tests/`, excluding vendored/generated/worktree noise. Each folder's blurb is written
from its actual file contents and the descriptions already established in `README.md`
and `llms.txt`, so the artifact stays consistent with existing docs.

The document is organized top-down: a title, an Overview built from the README's
opening and the `llms.txt` "core mental model", the recursive File Index grouped by the
top-level package/dir it lives under, and the Principles section. Nesting is expressed
by path depth in each entry's heading, so `vidbyte/tools/builtins/code_search` reads as
a clear descendant of `vidbyte/tools`.

```
artifacts/
`-- file_index.md      # Overview + recursive File Index + General Principles
```

No code, config, or existing docs are modified.

---

## 6. Detailed Design

### 6.1 `artifacts/file_index.md`

**File(s):** `artifacts/file_index.md`
**Type:** New file

#### What it does
A single Markdown artifact: the compressed, code-free structural map of the repository.

#### Interface / API
N/A — static Markdown. Section contract:
- `# Vidbyte SDK — File Index` (title + one-line framing)
- `## Overview` — 3–5 thick paragraphs.
- `## File Index` — lead-in paragraph, then recursive folder entries.
- `## General Principles` — the four principles.

#### Logic / Algorithm (authoring plan)
1. Write the Overview from the README intro + `llms.txt` mental model, kept prose-only.
2. Walk the audited tree and, for each folder below, write an inline-code path label plus 3–4 sentences.
3. Group entries by top-level area; indent meaning via path depth, physical-tree order.
4. Append the four principles as a short subsectioned list with a sentence each.
5. Proofread for any code fences and remove them.

#### Folder inventory to be described (recursive)
Root-level dirs: `vidbyte/`, `skills/`, `docs/`, `scripts/`, `tests/`, `artifacts/` (self).

`vidbyte/` package tree:
- `vidbyte/agents`, `vidbyte/agents/algorithms`, `vidbyte/agents/runtimes`, `vidbyte/agents/runtimes/actor`, `vidbyte/agents/settings`
- `vidbyte/context`, `vidbyte/context/algorithms`, `vidbyte/context/handoff`, `vidbyte/context/primitives`, `vidbyte/context/templates`
- `vidbyte/evals`, `vidbyte/evals/behavior`, `vidbyte/evals/graders`, `vidbyte/evals/templates`
- `vidbyte/harnesses`
- `vidbyte/lib`, `vidbyte/lib/agents`, `vidbyte/lib/config`, `vidbyte/lib/dataclasses`, `vidbyte/lib/enums`, `vidbyte/lib/errors`, `vidbyte/lib/http`, `vidbyte/lib/models`, `vidbyte/lib/registries`, `vidbyte/lib/runners`, `vidbyte/lib/templates`, `vidbyte/lib/tools`, `vidbyte/lib/tools/filesystem`, `vidbyte/lib/tools/filesystem/backends`, `vidbyte/lib/tracing`
- `vidbyte/mcp_server`, `vidbyte/mcp_server/server`, `vidbyte/mcp_server/server/handlers`
- `vidbyte/middleware`, `vidbyte/middleware/builtins`, `vidbyte/middleware/compaction`
- `vidbyte/paradigms`, `vidbyte/paradigms/context_minimal_fanout`, `vidbyte/paradigms/context_minimal_fanout/multiple_prompts`
- `vidbyte/pipelines`
- `vidbyte/prompts`, `vidbyte/prompts/prompts` (+ its 13 prompt-family subfolders), `vidbyte/prompts/skills`
- `vidbyte/providers`, `vidbyte/providers/tracing`
- `vidbyte/shared`
- `vidbyte/tools`, `vidbyte/tools/builtins` (+ `code_search`, `context`, `context_primitives`, `editing`, `handoff`, `mcp`, `memory`), `vidbyte/tools/filesystem`, `vidbyte/tools/mcp`, `vidbyte/tools/security`
- `vidbyte/trace`, `vidbyte/trace/continual`

Repo tooling dirs: `skills/` (+ its 10 skill subfolders), `docs/` (`design`, `pre-design`), `scripts/`, `tests/`.

#### Edge Cases & Error Handling
- **Asset-only folders** (e.g. `vidbyte/prompts/prompts/*`, `skills/*`) have no `.py`; described by their assets/role, not code.
- **Deeply nested prompt families**: summarized collectively under `vidbyte/prompts/prompts` with the family list rather than 13 near-identical entries, to keep the index scannable (still names each family).
- **Excluded dirs**: `.git`, `.claude`, `.github`, `__pycache__`, `.pytest_cache`, `*.egg-info`, and any `worktree-*` checkouts nested in the repo are intentionally omitted; noted in the lead-in.

---

## 7. Data Model Changes

N/A — no schema, types, or persisted data.

---

## 8. API Changes

N/A — no runtime API surface.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `artifacts/file_index.md` | The compressed, code-free repo file index artifact |
| CREATE | `docs/design/artifact-file-index.md` | This design doc (committed first) |

(`artifacts/` is created implicitly by writing the file into it.)

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| N/A | — | Pure static Markdown; no deps | None |

---

## 11. Rollout & Deployment

- No feature flags, not a breaking change, nothing to deploy.
- Rollout = merge the PR. Rollback = delete `artifacts/file_index.md`.
- Deployment order: N/A.

---

## 12. Open Questions

- [ ] Should the 13 prompt families under `vidbyte/prompts/prompts` each get their own 3–4 sentence entry, or be summarized in one entry that names them? Plan: **summarize + name** for scannability (see 6.1 edge cases). Confirm if you want one entry per family.
- [ ] Should `skills/`, `docs/`, `scripts/`, `tests/` be included, or should the index be limited to the shippable `vidbyte/` package only? Plan: **include them** briefly, since the request said "all folders in the repo."
- [ ] Preferred entry format: path as a `###` heading vs. inline-code bullet? Plan: `###` path headings grouped under top-level `##` areas.

---

## 13. Alternatives Considered

### Alternative 1: Auto-generate the index from a directory walk
- What: a script that emits the folder list with stub descriptions.
- Why rejected: descriptions need human/semantic judgment to be 3–4 accurate sentences; a generator would produce empty or wrong blurbs, and the user asked for a curated artifact, not tooling.

### Alternative 2: Extend `llms.txt` instead of a new file
- What: add a "file index" section to the existing bundle.
- Why rejected: the user explicitly wants a separate, compressed, code-free artifact under a new `artifacts/` folder; mixing it into the code-heavy `llms.txt` defeats the "compressed map" purpose.

### Alternative 3: One entry per file
- What: file-level index.
- Why rejected: the request is folder-level; file-level would be enormous and duplicate `llms.txt`.

---

END OF DESIGN DOC
