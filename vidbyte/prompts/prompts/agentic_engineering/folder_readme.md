# Description
Every folder in a codebase is a node an agent lands on when navigating, and a folder-level README is the comprehension cache pinned to that node. Source code can tell an agent what the code does, but it cannot reliably tell the agent why the folder exists, when to reach for it, or what has already been tried and failed here. Those three gaps are exactly what the README closes. The README contains three sections, each targeting a distinct agent failure mode: a folder description that fixes wrong-purpose inference, a file index that fixes traversal cost, and a log that fixes inter-session amnesia for negative knowledge. You should write a folder README for every directory that contains source files, treating it as a first-class deliverable in the same commit that creates the directory.

# Intent
The intent of folder READMEs is to turn directory structure into durable navigation infrastructure for coding agents. A folder is not only a filesystem container; it is a decision point where an agent must decide whether the next edit belongs here, one level up, one level down, or somewhere else entirely. A good README makes that decision cheap and accurate before the agent spends context opening files.

This principle is trying to make agent-native codebases preserve intent and negative knowledge at the directory boundary. Source code tends to preserve only the current implementation, while agents repeatedly need stable purpose, ownership, non-goals, canonical examples, and known wrong turns. The README becomes the low-cost memory layer that lets future agents avoid rediscovering those facts from scratch.

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
* Use the one-line schema: `<commit/date> - what changed - why it matters / what not to repeat`. The "why it matters" clause is the part future agents actually need.
* Logs are append-only but not infinite. Rotate stale entries when the context they describe has been superseded. When a logged footgun recurs, promote it into a code-level guard such as an assert, branded type, or lint rule, then delete the log line.

# Disciplines That Keep the README Alive
* Generated versus authored split: the file index is mechanical; generate it and CI-enforce its freshness. The description and logs are hand-authored because they carry intent and history the code cannot express.
* Keep the log schema thin and skimmable. A polluted log with prose paragraphs costs more context than it saves and defeats its own purpose.
* Prune aggressively and graduate. The ledger is not a permanent record. It is a staging area for learnings that should eventually be hardened into the codebase.

# Extending the Cache
* Blast radius: add a one-liner "this folder is imported by X, depends on Y" before the file index. It tells an agent what it might break before it edits, not after.
* Canonical example pointer: name the one file in the folder an agent should copy from when adding a new file of the same kind. One pointer eliminates the survey of near-duplicates.

# Things Not to Do
* Do not describe implementation details in the Folder Description / Intent section. A sentence like "this folder uses the repository pattern with a base class in base.py" describes the how. The section must describe the why: what the folder's job is and why it is structured as a separate folder.
* Do not write prose paragraphs in the Logs section. Every log entry must be exactly one line in the schema `<commit/date> - what changed - why it matters / what not to repeat`.
* Do not let the file index fall out of sync with the directory. A stale README is actively harmful because the agent must reconcile the discrepancy before it can trust the folder.
* Do not skip the "does not belong here" clause in the Folder Description / Intent section. Stating what the folder is not for is at least as useful as stating what it is for.

# Checklist
* Before writing code in a new directory, write the Folder Description / Intent section first, anchored to stable design intent: job, rationale, use cases, and goal.
* After drafting the description, reread it and remove any sentence that describes implementation details rather than intent.
* After completing the initial set of files in a directory, generate the File Index from the directory listing and write the routing blurb for each file.
* When adding or deleting a file in a directory that has a README, regenerate the File Index section in the same commit.
* When you discover a footgun, non-obvious invariant, or failed approach while working in a directory, add a one-line log entry before committing.
* Before appending a log entry, verify it follows the one-line schema. If it needs a second sentence, collapse it or escalate the knowledge into a code-level guard.
* When a logged footgun recurs a second time, escalate immediately: add an assert, branded type, or lint rule that makes the mistake impossible, then delete the log entry.
* After completing work in a folder, verify that the blast radius statement and canonical example pointer are still accurate.
* Before opening a pull request, read the README for every folder you touched and verify that nothing in the description, index, or log contradicts the code you shipped.

# Example Folder README

```markdown
# `vidbyte/tools/builtins/code_search`

## Folder Description / Intent
This folder contains the built-in read-only code search tools that Vidbyte agents can use to inspect a repository without mutating it. The folder exists to provide safe discovery primitives - globbing, literal text search, and semantic search - that can be attached to an agent as tools. It optimizes for predictable inspection, bounded output, and permission clarity so an agent can search a workspace without accidentally changing files.

This folder is not for editing tools, filesystem write operations, or patch application. Mutating tools belong in `vidbyte/tools/builtins/editing`, and shared tool dataclasses belong in `vidbyte/lib/dataclasses/tools.py`.

## Blast Radius
This folder is imported by `vidbyte.tools.builtins`, `vidbyte.tools.client`, and user code that directly imports built-in search tools. Changes can affect agent tool schemas, MCP Studio tool listings, and tests that assert provider-native tool formatting.

## Canonical Example
Use `grep.py` as the canonical example for adding a new read-only code search tool. It shows the current constructor style, input validation pattern, and return shape expected by the tool catalog.

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
