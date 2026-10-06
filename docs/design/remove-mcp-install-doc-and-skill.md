# Design Doc: Remove MCP Install Doc and Skill

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-05
**Last Updated:** 2026-07-05

---

## 1. Overview

Remove two obsolete MCP-related repository artifacts from `vidbyte-sdk`: the root-level `installing-vidbyte-sdk-as-mcp.md` guide and the Claude-specific `.claude/skills/add-mcp-preset` skill folder. Because `llms.txt` currently links to the root guide, update that generated/reference document to avoid retaining dead links after the deletion.

---

## 2. Goals & Non-Goals

### Goals

- Delete `installing-vidbyte-sdk-as-mcp.md` from the repository.
- Delete the `.claude/skills/add-mcp-preset` folder by removing its tracked `SKILL.md` file.
- Remove direct `llms.txt` references to `installing-vidbyte-sdk-as-mcp.md` so the repo does not keep stale documentation links.
- Keep existing runtime MCP server code, CLI entry points, tests, README MCP coverage, and MCP preset implementation intact.
- Keep the change documentation-only/repo-hygiene-only with no runtime behavior change.

### Non-Goals

- No changes to `vidbyte.mcp_server`, `vidbyte.tools.mcp`, MCP preset definitions, or MCP transport behavior.
- No removal of the `vidbyte-mcp-server` console script.
- No changes to package metadata except those already implied by deleting the requested docs/skill files.
- No regeneration of the full `llms.txt` corpus unless explicitly requested.
- No tests or verification scripts added for this request.
- No implementation of the incomplete trailing user request, quoted as: `and then also I want to make a`.

---

## 3. Background & Context

The repository is a Python SDK package named `vidbyte-sdk`, defined by `pyproject.toml`, requiring Python 3.11+ and depending on `pydantic` and `httpx`. The package exposes a `vidbyte-mcp-server` console entry point through `vidbyte.mcp_server.__main__:main`, and the README already contains current MCP Studio server guidance under its "MCP Servers" section.

The root file `installing-vidbyte-sdk-as-mcp.md` is a standalone guide for registering Vidbyte as an MCP server in external clients. The repository also contains `.claude/skills/add-mcp-preset/SKILL.md`, a Claude-specific workflow prompt for adding MCP preset definitions. The implementation request is to remove these artifacts from the repository, not to remove MCP support.

Audit notes:

- `installing-vidbyte-sdk-as-mcp.md` exists and is tracked.
- `.claude/skills/add-mcp-preset/SKILL.md` exists and is tracked. Git does not track directories directly, so deleting this file removes the folder from the committed tree.
- `llms.txt` references `installing-vidbyte-sdk-as-mcp.md` in its MCP primary references and Docs-to-MCP submission notes.
- README references MCP concepts and the `vidbyte-mcp-server` CLI, but does not link to `installing-vidbyte-sdk-as-mcp.md`; no README edit is required for this removal.
- Runtime MCP tests and source files reference `vidbyte-mcp-server` and `vidbyte-sdk-studio`; those references are valid runtime/API references and should remain unchanged.
- The current working tree is not clean before this design doc. It is on `feat/context-minimal-fanout-trace` with unrelated untracked files and local worktree directories. This workflow must not revert or clean unrelated user changes.

---

## 4. Requirements

### Functional Requirements

1. The repository must no longer contain `installing-vidbyte-sdk-as-mcp.md`.
2. The repository must no longer contain `.claude/skills/add-mcp-preset/SKILL.md`.
3. The committed tree must no longer contain the `.claude/skills/add-mcp-preset` folder after deleting its tracked file.
4. `llms.txt` must no longer link to or recommend indexing `installing-vidbyte-sdk-as-mcp.md`.
5. Existing MCP runtime support, MCP preset support, README MCP server documentation, and tests must remain untouched unless needed to remove a stale reference to the deleted artifacts.
6. The design doc must be committed first in the implementation worktree before any deletion or `llms.txt` edit.

### Non-Functional Requirements

- Performance: N/A - documentation and repository hygiene only.
- Scalability: N/A - no runtime behavior or data path changes.
- Security: Removing a local Claude skill reduces repository-specific prompt surface, but no security-sensitive runtime code changes are included.
- Observability: N/A - no logging, metrics, or tracing changes.
- Reliability: The change must not leave stale links to deleted files in `llms.txt`.
- Maintainability: MCP runtime documentation retained in README and `vidbyte/mcp_server/README.md` remains the source for supported MCP behavior.
- Compatibility: Public package imports, CLI entry points, and MCP behavior remain unchanged.

---

## 5. High-Level Design

The implementation is a small documentation cleanup performed in an isolated git worktree after approval. It deletes the requested root-level MCP installation guide and deletes the tracked skill file under `.claude/skills/add-mcp-preset`, causing that folder to disappear from the repository.

Because `llms.txt` currently contains direct references to the deleted root guide, the implementation also removes those references. The existing README and `vidbyte/mcp_server/README.md` remain as the durable MCP documentation locations.

```text
Repo docs/skill cleanup
  |
  +-- DELETE installing-vidbyte-sdk-as-mcp.md
  +-- DELETE .claude/skills/add-mcp-preset/SKILL.md
  +-- MODIFY llms.txt to remove links/recommendations for the deleted guide
```

No code paths, imports, package data, or APIs are changed.

---

## 6. Detailed Design

### 6.1 Design Doc

**File(s):** `docs/design/remove-mcp-install-doc-and-skill.md`
**Type:** New file

#### What it does

Records the approved scope, audit findings, file manifest, rollout, rollback, and open questions for the removal.

#### Interface / API

```text
N/A - Markdown design document only.
```

#### Logic / Algorithm

1. Create the design doc from the required template.
2. Commit it first in the implementation worktree after explicit approval.

#### Edge Cases & Error Handling

- If the implementation worktree cannot be created from `main`, stop and report the blocker.
- If the file already exists on the implementation branch, reconcile it carefully instead of overwriting unrelated user work.

---

### 6.2 Root MCP Installation Guide

**File(s):** `installing-vidbyte-sdk-as-mcp.md`
**Type:** Deleted

#### What it does

Currently provides a standalone guide for registering Vidbyte SDK as an MCP server in external clients.

#### Interface / API

```text
N/A - Deleted Markdown file.
```

#### Logic / Algorithm

1. Delete the tracked Markdown file.
2. Verify `git status --short` reports the file as deleted in the implementation worktree.

#### Edge Cases & Error Handling

- If the file is absent on fresh `main`, record the deletion as already satisfied and verify no stale references remain.
- If another branch has modified the file, do not preserve it because the approved requirement is removal.

---

### 6.3 Claude Add MCP Preset Skill

**File(s):** `.claude/skills/add-mcp-preset/SKILL.md`
**Type:** Deleted

#### What it does

Currently provides a Claude-specific prompt workflow for adding built-in MCP server presets to the SDK.

#### Interface / API

```text
N/A - Deleted local skill prompt file.
```

#### Logic / Algorithm

1. Delete `.claude/skills/add-mcp-preset/SKILL.md`.
2. Confirm `.claude/skills/add-mcp-preset` no longer appears in the committed tree.

#### Edge Cases & Error Handling

- Git tracks files rather than empty directories, so removing `SKILL.md` removes the folder from repository history unless untracked local files remain inside it.
- If untracked files exist inside the folder in the implementation worktree, stop and report them instead of deleting unrelated local content.

---

### 6.4 LLM Reference Corpus Cleanup

**File(s):** `llms.txt`
**Type:** Modified

#### What it does

Provides aggregated repository documentation and MCP reference notes for LLM consumption.

#### Interface / API

```text
N/A - Plain text documentation reference file.
```

#### Logic / Algorithm

1. Remove the primary-reference bullet linking to `installing-vidbyte-sdk-as-mcp.md`.
2. Remove the Docs-to-MCP indexing recommendation for `installing-vidbyte-sdk-as-mcp.md`.
3. Leave valid `vidbyte-mcp-server`, `vidbyte-sdk-studio`, README, MCP server skill, and runtime source references unchanged.

#### Edge Cases & Error Handling

- Do not broadly delete MCP content from `llms.txt`; only remove references to the deleted root guide.
- If `llms.txt` has changed on fresh `main`, apply the smallest equivalent cleanup against the current text.

---

## 7. Data Model Changes

N/A - No schemas, persisted data, migrations, or typed runtime models change.

---

## 8. API Changes

N/A - No public Python APIs, CLI entry points, MCP tools, JSON-RPC handlers, or package exports change.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/remove-mcp-install-doc-and-skill.md` | Required design document for this workflow |
| MODIFY | `llms.txt` | Remove references to the deleted root MCP installation guide |
| DELETE | `installing-vidbyte-sdk-as-mcp.md` | User requested removal from the repository |
| DELETE | `.claude/skills/add-mcp-preset/SKILL.md` | User requested removal of `.claude/skills/add-mcp-preset`; deleting the tracked file removes the folder from the committed tree |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Git | Local repository | Create isolated worktree, commit design doc first, commit cleanup, and open PR | Existing dirty/untracked state or branch divergence may block worktree setup |
| GitHub CLI | `gh` authenticated locally | Create draft PR after implementation | PR creation may be blocked if `gh` is unavailable or unauthenticated |

---

## 11. Rollout & Deployment

- Feature flags: N/A - repository content cleanup only.
- Breaking change: No runtime/API breaking change. Documentation consumers that relied on the deleted root guide URL will need to use README or `vidbyte/mcp_server/README.md`.
- Deployment order: Commit design doc first, then commit deletions and `llms.txt` cleanup.
- Verification: Use `git status --short`, `git ls-files`, and `rg` to confirm deleted files are absent from tracked files and stale references are removed.
- Rollback procedure: Revert the cleanup commit to restore the deleted files and `llms.txt` references. Revert the design-doc commit only if the design record itself should be removed.

---

## 12. Open Questions

- [ ] The original user prompt ended with an incomplete clause: `and then also I want to make a`. Should any additional change be included before implementation, or should this design proceed with only the confirmed removal scope above?
- [ ] Should `llms.txt` be manually patched only as described, or regenerated by whatever upstream documentation-generation process produced it? This design chooses the smallest manual patch because no generator command was identified during audit.

---

## 13. Alternatives Considered

### Alternative 1: Delete only the requested file and folder

- What: Remove `installing-vidbyte-sdk-as-mcp.md` and `.claude/skills/add-mcp-preset/SKILL.md` without touching any other files.
- Why rejected: `llms.txt` contains direct references to the deleted Markdown file, so deleting only the file would leave stale links in repository documentation.

### Alternative 2: Remove all MCP documentation

- What: Delete or rewrite all README, `llms.txt`, and source README references to MCP.
- Why rejected: The user requested removal of one standalone guide and one Claude skill folder, not removal of MCP support or current MCP documentation. Runtime MCP support and README coverage are still valid.

### Alternative 3: Move the files instead of deleting them

- What: Relocate the guide or skill into another docs/skills location.
- Why rejected: The explicit requirement is to remove these artifacts from the repository.
