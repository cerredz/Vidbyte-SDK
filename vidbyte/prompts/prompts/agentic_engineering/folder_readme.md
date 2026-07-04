# Description
Every folder in a codebase is a node an agent lands on when navigating, and a folder-level README is the comprehension cache pinned to that node. Source code can tell an agent what the code does, but it cannot reliably tell the agent why the folder exists, when to reach for it, or what has already been tried and failed here. Those three gaps are exactly what the README closes. The README contains three sections, each targeting a distinct agent failure mode: a folder description that fixes wrong-purpose inference, a file index that fixes traversal cost, and a log that fixes inter-session amnesia for negative knowledge. You should write a folder README for every directory that contains source files, treating it as a first-class deliverable in the same commit that creates the directory.

# Intent
The intent of folder-level READMEs is twofold: first, to compress the information of an entire directory into a single file that an agent can read to understand the folder before opening any source files inside it. A directory without a README forces the agent to survey every file in the folder to determine what belongs here, what the folder's job is, whether a new file should be added here or somewhere else, and what the canonical patterns are. The folder README eliminates this survey cost by providing a high-level description of the folder's purpose and a file index that summarizes every file with enough signal to decide whether to open it. An agent reading a README first can make a routing decision — "this is the right folder" or "this is the wrong folder" — in seconds rather than minutes. The information captured here cannot be recovered from source code alone: intent, ownership, non-goals, and the canonical file to copy from are all architectural facts that live nowhere in the code itself. The description must be written to intent and purpose, not to implementation detail, so it remains accurate through multiple refactors without needing an update.

The second intent is to provide a mini history of the things that have happened in this folder — the footguns that were stepped on, the approaches that were tried and failed, and the invariants that were discovered through debugging rather than design. Source code records only the current state; it permanently erases every wrong turn, every failed experiment, and every costly lesson about what not to do. The Logs section of a README is the persistent memory layer for this negative knowledge, written in a compact one-line format so that the accumulated history can be read in seconds rather than minutes. An agent that reads the Logs section before editing avoids rediscovering documented traps, can benefit from decisions made in previous sessions, and can recognize recurring problems that have already been escalated into code-level guards. Together, the directory description and the logs make the folder a durable knowledge artifact rather than an opaque collection of files — one that trains future agents on the history and intent of the code it contains.

# The Three Sections of Every Folder README

## Folder Description / Intent
* This section fixes the failure mode "can't infer purpose from mechanism." An agent reading raw source reconstructs a plausible purpose for the folder that is often subtly wrong, and then writes code aligned to the wrong purpose: misplacing a function, misreading an invariant, or adding to the wrong abstraction layer.
* Write 2-4 paragraphs covering the folder's job, why it was designed this way, what use cases it serves, and what goal it optimizes for. These paragraphs answer the question "should my new code even go in this folder?" - a question source code cannot answer.
* Anchor the description to stable intent, not implementation details. The "why" of a folder changes far less often than the "how." Write the description to remain true through several refactors without needing an update.
* Include what the folder is not for, naming at least one class of code that does not belong here and which folder owns it instead. Agents misfile code constantly. One redirect line prevents a whole class of wrong placements.

## File Index
* This section fixes traversal cost. Without it the agent opens many files or greps blindly just to learn what is where. The per-file blurb is the skip enabler: enough signal to decide whether to open a file without opening it.
* Write 3-4 sentences per file. The blurb's job is routing, not summarizing contents. It answers "should I open this file right now?" not "what is in this file?"
* Generate the file index mechanically from the directory listing when possible. CI should fail when a folder has source files but no README, or when the index names a file that no longer exists. The generated half is what stops the cache from rotting.

## Logs
* This section fixes "no memory between sessions," specifically for negative knowledge. This is the highest-value, lowest-density signal in the repo: "tried X, broke Y, the fix was Z." Source code records the current state but erases every wrong turn.
* Use the one-line schema: `<commit/date> - what changed - why it matters`. Optionally append `/ what not to repeat` when the entry documents a specific mistake; omit it when the log is recording a positive decision rather than a correctable error. The "why it matters" clause is the part future agents actually need.
* Logs are append-only but not infinite. Rotate stale entries when the context they describe has been superseded. When a logged footgun recurs, promote it into a code-level guard such as an assert, branded type, or lint rule, then delete the log line.

# Disciplines That Keep the README Alive
* Generated versus authored split: the file index is mechanical; generate it and CI-enforce its freshness. The description and logs are hand-authored because they carry intent and history the code cannot express.
* Keep the log schema thin and skimmable. A polluted log with prose paragraphs costs more context than it saves and defeats its own purpose.
* Prune aggressively and graduate. The ledger is not a permanent record. It is a staging area for learnings that should eventually be hardened into the codebase.

# Non-Goals Section

## What It Is
Every folder README must contain a Non-Goals section that tells an agent what must not be done inside the folder. The non-goals are derived from the rest of the codebase — specifically from every other folder README — so the information is grounded in the actual boundaries and responsibilities of other parts of the system rather than invented in isolation.

The purpose of the Non-Goals section is to give agents concrete prohibitions backed by cross-folder context. When an agent is deciding where to place new code, it is not enough to know what this folder does — it must also know what this folder must never do, so that it routes code to the right folder on the first attempt rather than discovering the misfiling through a code review or a test failure. Without a Non-Goals section, an agent that is uncertain about ownership may place code in the first folder that seems plausible, which is often wrong.

## How to Generate the Non-Goals Section
When the agent is creating or updating a folder README, it must execute the following steps:
1. Use a recursive search (e.g., `grep -r "# " --include="README.md" -l .`) to find every README.md in the repository.
2. Read every discovered README into the context window, focusing on the Folder Description / Intent section and the Non-Goals section of each.
3. From the descriptions and non-goals of all sibling and related folders, identify the responsibilities that belong exclusively to those other folders and not to the folder being documented.
4. Write a Non-Goals section for the current folder that explicitly names those responsibilities and, where possible, names the folder that owns them instead.
5. Add 7-9 concrete bullet points covering the most likely classes of code an agent might incorrectly place here, each redirecting to the correct folder.
6. Verify that each bullet is grounded in something found in another folder's README or description — do not invent prohibitions that have no basis in the actual codebase structure.

# Things Not to Do
* Do not be vague in the Folder Description / Intent section. Vague descriptions like "this folder handles utilities" provide no routing signal. Name the specific job the folder owns, the specific use cases it serves, and the specific goal it optimizes for.
* Do not contain information about other folders or subfolders in a folder's README. Each subfolder will have its own README. A parent README that describes what its children do forces the agent to hold a stale copy of information that lives more authoritatively one level down.
* Do not describe implementation details in the Folder Description / Intent section. A sentence like "this folder uses the repository pattern with a base class in base.py" describes the how. The section must describe the why: what the folder's job is and why it is structured as a separate folder.
* Do not write prose paragraphs in the Logs section. Every log entry must be exactly one line in the schema. A polluted log with full sentences and explanatory prose costs more context than it saves and defeats its own purpose.
* Do not let the file index fall out of sync with the directory. A stale README is actively harmful because the agent must reconcile the discrepancy before it can trust the folder.
* Do not skip the "does not belong here" clause in the Folder Description / Intent section. Stating what the folder is not for is at least as useful as stating what it is for.
* Do not treat the Logs section as a permanent record. It is a staging area for knowledge that should eventually be hardened into the codebase as asserts, lint rules, or branded types. Rotate entries when the context they describe has been superseded.

# Checklist
* Before writing code in a new directory, write the Folder Description / Intent section first, anchored to stable design intent: job, rationale, use cases, and goal.
* After drafting the description, reread it and remove any sentence that describes implementation details rather than intent.
* After completing the initial set of files in a directory, generate the File Index from the directory listing and write the routing blurb for each file.
* When adding or deleting a file in a directory that has a README, regenerate the File Index section in the same commit.
* When you discover a footgun, non-obvious invariant, or failed approach while working in a directory, add a one-line log entry before committing.
* Before appending a log entry, verify it follows the one-line schema. If it needs a second sentence, collapse it or escalate the knowledge into a code-level guard.
* When a logged footgun recurs a second time, escalate immediately: add an assert, branded type, or lint rule that makes the mistake impossible, then delete the log entry.
* When generating the Non-Goals section, read every other README in the repository first so the prohibitions are grounded in actual sibling folder boundaries rather than invented in isolation.
* Before opening a pull request, read the README for every folder you touched and verify that nothing in the description, index, or log contradicts the code you shipped.

# Example Folder README

```markdown
# `vidbyte/tools/builtins/code_search`

## Folder Description / Intent
This folder contains the built-in read-only code search tools that Vidbyte agents can use to inspect a repository without mutating it. The folder exists to provide safe discovery primitives - globbing, literal text search, and semantic search - that can be attached to an agent as tools. It optimizes for predictable inspection, bounded output, and permission clarity so an agent can search a workspace without accidentally changing files.

This folder is not for editing tools, filesystem write operations, patch application, or any operation that changes the state of the workspace. Mutating tools belong in `vidbyte/tools/builtins/editing`, which is the dedicated owner of all tools that write, move, rename, or delete files. Shared tool dataclasses and base result types that are used across both read and write tools belong in `vidbyte/lib/dataclasses/tools.py`, not here. Do not add provider-specific search logic to this folder; provider adapters belong in `vidbyte/tools/providers/`. Any tool that requires authentication, API keys, or network access to an external search service does not belong here unless it falls back gracefully to local filesystem search when those credentials are absent.

## Blast Radius
This folder is imported by `vidbyte.tools.builtins`, `vidbyte.tools.client`, and user code that directly imports built-in search tools. Changes can affect agent tool schemas, MCP Studio tool listings, and tests that assert provider-native tool formatting.

## Non-Goals
* Do not add tools that write, move, rename, delete, or otherwise mutate any file or directory — those belong in `vidbyte/tools/builtins/editing`.
* Do not add tools that make network calls to external search APIs as their primary mechanism — network-backed tools belong in `vidbyte/tools/providers/`.
* Do not add provider-specific formatting or authentication logic — keep all tools in this folder dependency-light and runnable offline.
* Do not define shared result types or base classes used across multiple tool packages — shared contracts belong in `vidbyte/lib/dataclasses/tools.py`.
* Do not add execution or runtime tools (code runners, shell executors, process launchers) — those belong in `vidbyte/tools/builtins/execution`.
* Do not add tools that persist state, write cache files, or maintain indexes on disk between calls — read-only means stateless with respect to the workspace.
* Do not add tools that require elevated permissions (sudo, admin, system-level) — all tools in this folder must operate under the same permission level as the agent process itself.
* Do not add UI or display tools that render results in a specific frontend format — rendering belongs in the client layer, not the tool definition.

## File Index
* `__init__.py` - Re-exports the public code search tools. Open this when adding a new tool class that should be importable from `vidbyte.tools.builtins.code_search`. Keep `__all__` aligned with the exported classes so direct imports remain stable.
* `base.py` - Defines shared search result types and helper behavior for read-only code search tools. Open this before changing output shape or result truncation behavior. Do not add provider-specific logic here; this file is the local contract shared by all search tools.
* `glob.py` - Implements path-pattern discovery for agents that need to find candidate files before reading content. Open this when changing include/exclude semantics. It should remain read-only and should never inspect file contents.
* `grep.py` - Implements literal text search over workspace files. Open this when changing match formatting, context lines, or result limits. It is the canonical example for a safe read-only search tool.
* `semantic.py` - Implements embedding-backed or heuristic semantic lookup when available. Open this when changing the high-level search contract. Keep optional provider behavior isolated so the rest of the search tools remain dependency-light.

## Logs
* 2026-06-27 - Kept mutation tools out of code_search - prevents agents from confusing read-only discovery with patch application.
* 2026-06-27 - Made grep.py the canonical example - avoids future tools copying older result formatting patterns.
```

# Conclusion
A folder README exists to make a directory legible before an agent spends context opening the files inside it. The example shape is useful, but the point is not to reproduce the sample folder or force every directory into identical prose. The point is to capture the folder's stable job, the boundaries that keep code from being misplaced, the file-level routing map, and the negative knowledge that would otherwise disappear between sessions. If a README becomes an exhaustive duplicate of source code, it has stopped being a cache and started becoming stale documentation. If it says only what an agent could infer from filenames, it has not earned its place. Write the authored parts to answer decisions that source code cannot answer, and generate the mechanical parts so they stay fresh. The Logs section should preserve lessons only until they can be graduated into stronger guards. Use this principle to make folders navigable as architectural neighborhoods, not just as filesystem containers.
