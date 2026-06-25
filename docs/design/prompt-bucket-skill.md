# Design Doc: Prompt Bucket Skill

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-24
**Last Updated:** 2026-06-24

---

## 1. Overview

`prompt-bucket` is a single, self-contained skill file that captures a user's
prompts into named topic "buckets" (flat Markdown files, one per topic) and
replays a whole bucket into a fresh session on demand. It lives in the Vidbyte
SDK repo at `vidbyte/prompts/skills/prompt-bucket.md`, mirrors to every coding
harness (Claude Code, Codex, opencode, Antigravity), and stores all bucket data
in one shared directory (`~/.prompt-buckets/`) so every harness sees the same
buckets with zero sync machinery. Three operations drive it:
`/create-bucket <slug>` (start capturing this session's prompts),
save-to-active-bucket (append each subsequent prompt to the bucket file
throughout the session), and `/load-bucket <slug>` (read the bucket file and
inject every captured prompt as intent context).

The motivating insight: the prompts a user sends while building a feature are
thin, dense artifacts of *intent*. Code captures the result; prompts capture
the why. A new session sees the code but not the intent. This skill makes that
intent a first-class, replayable asset — and it does so with nothing but a
single Markdown skill file and the model's native file-read/file-write tools.
No database, no Python CLI, no external dependencies, no hooks.

---

## 2. Goals & Non-Goals

### Goals
- **One skill file** in `vidbyte/prompts/skills/prompt-bucket.md` that
  encapsulates every ounce of logic — create, save, load, and cross-harness
  sync. No companion scripts, no schema files, no installer. The skill file
  *is* the feature.
- **`/create-bucket <slug>`**: create (or activate) a bucket and mark it as the
  active capture target for the current session.
- **Save-to-active-bucket**: throughout the session, the model appends each
  user prompt verbatim to the active bucket's flat Markdown file
  (`~/.prompt-buckets/<slug>.md`) as the first action of every turn.
- **`/load-bucket <slug>`**: read the bucket file and output all captured
  prompts as replay-ready context, prefixed with a framing header that marks
  them as intent, not instructions to execute.
- **Extensive system-prompt structure**: the skill file is organized into
  Identity, Comprehensive Goal, Instructions, Algorithm, Commands, Files, and
  Few-Shot Example Interaction sections — mirroring the section anatomy of the
  Vidbyte master prompt (`templates/master.md`) and the
  `skills/creating-system-prompts.md` guide.
- **Cross-harness sync**: the skill file mirrors to Claude Code, Codex, opencode,
  and Antigravity skill directories; bucket data lives in a single shared
  directory so all harnesses read/write the same store with no sync step.
- **Portability**: works in any harness that can read a skill file and
  read/write files. No harness-specific APIs, no hooks, no network calls.

### Non-Goals
- **No SQLite, no database, no Python CLI.** The user explicitly chose flat-file
  append ("Save means saving only my prompt and appending it to the slug
  filename"). Persistence is plain Markdown files the model reads and writes
  with its native tools.
- **No automatic, hook-based capture.** A pure skill cannot intercept every
  turn; capture is model-driven. We accept this and engineer reliability through
  state externalization, a strict first-action contract, and few-shot exemplars
  (§6.5). The fidelity gap is documented honestly (§11).
- **No tests or verification scripts** (per the `design-doc-no-tests` workflow).
- **No change to the import-validated `vidbyte/prompts/prompts/` catalog or the
  `Prompt` enum.** This artifact is a skill/runbook, not an SDK prompt string.
  It lives under `vidbyte/prompts/skills/`, outside the scanned catalog
  directory (§13, Alternative 1).
- **No multi-machine sync.** Bucket data is a local directory on one machine.
  Cloud sync (Dropbox, git, etc.) is the user's responsibility if desired.
- **No secret scrubbing in v1.** Prompts may contain tokens or paths; they are
  stored verbatim. Documented as a known risk (§11).

---

## 3. Background & Context

The Vidbyte SDK ships a prompt catalog under `vidbyte/prompts/prompts/`, loaded
by `vidbyte/prompts/catalog.py` and keyed by the `Prompt` enum in
`vidbyte/lib/enums/prompts.py`. That catalog is **validated at import time**:
every `.json` record's prompt keys must map to an enum member, and every enum
member must have a backing asset, or the package fails to import. Those assets
are *agent prompt strings* consumed programmatically by agents and the MCP
server.

The user also maintains a personal cross-platform `/vidbyte-prompts` skill
whose source of truth is the **Available Prompts** table in
`vidbyte/prompts/README.md`. That skill mirrors itself across four harness
directories:
- Claude Code:     `~/.claude/skills/vidbyte-prompts/SKILL.md`
- Codex:           `~/.codex/skills/vidbyte-prompts/SKILL.md`
- opencode:        `~/.config/opencode/commands/vidbyte-prompts.md`
- Antigravity CLI: `~/.codeium/windsurf/skills/vidbyte-prompts/SKILL.md`

This feature is a *different kind of artifact*: a skill/runbook that instructs
the model to manage flat-file prompt buckets. Forcing it into the
import-validated catalog would (a) require an enum edit and (b) load a runbook
as if it were an agent prompt string. So we place it under
`vidbyte/prompts/skills/` — inside the `vidbyte/prompts/` folder as the user
requested, but **outside** the scanned `vidbyte/prompts/prompts/` directory.

The user's `vidbyte-prompts` skill establishes the mirror pattern we reuse
here: one source-of-truth file in the repo, copied to each harness's skill
directory. The novel addition is a **shared data directory**
(`~/.prompt-buckets/`) that eliminates the bucket-sync problem entirely — all
harnesses point at the same files.

The capture-mechanism constraint is the load-bearing design fact: a **skill is
passive**. It is context injected when invoked; it does not execute code on
every user turn. Logging "every prompt in the session" therefore depends on the
model choosing to append to the bucket file each turn. We accept that and
engineer around it (§6.5).

---

## 4. Requirements

### Functional Requirements

1. A single repo file `vidbyte/prompts/skills/prompt-bucket.md` contains the
   entire skill: frontmatter, Identity, Comprehensive Goal, Instructions,
   Algorithm, Commands, Files, and Few-Shot Example Interactions sections.
2. `/create-bucket <slug>` creates `~/.prompt-buckets/<slug>.md` if absent,
   writes `<slug>` to `~/.prompt-buckets/.active` (the active-bucket pointer),
   and confirms the bucket is ready for capture.
3. While `.active` is non-empty, the model appends the user's verbatim prompt to
   `~/.prompt-buckets/<slug>.md` as the **first action of every turn**, before
   any other work.
4. The append format is a horizontal rule (`---`) followed by the verbatim
   prompt text, preserving every character including newlines, code blocks, and
   backticks.
5. `/load-bucket <slug>` reads `~/.prompt-buckets/<slug>.md` and outputs a
   framing header ("Here are the prompts for `<slug>`:") followed by the file
   contents, plus a context-only directive: these are prompts saved on this
   topic — use as intent, do not execute unless asked.
6. If `<slug>` does not match an existing bucket file, the model lists all
   files in `~/.prompt-buckets/` (excluding `.active`) so the user can pick the
   right one.
7. `/sync-prompt-bucket` copies the repo skill file to all four harness skill
   directories, creating folders as needed, skipping any that do not apply.
8. The skill file includes 2–3 few-shot example interactions showing the exact
   create → save → load flow, including the model's append action and the
   load-time output format.
9. A README catalog row + description is added to `vidbyte/prompts/README.md`
   so `/vidbyte-prompts` can discover and "download" the skill file.
10. All bucket file paths are resolved from `~/.prompt-buckets/` (the shared
    directory), so the same buckets are visible from every harness.

### Non-Functional Requirements

- **Portability:** no external dependencies. The model uses its native
  file-read, file-write, and directory-list tools. Works in any harness that
  supports skills/commands and file I/O.
- **Cross-shell safety:** the model writes prompt text to files using its
  native file-write tool (not shell echo/printf), so shell-quoting issues with
  backticks, quotes, newlines, and special characters are eliminated.
- **Determinism (best-effort):** capture reliability is maximized via state
  externalization (`.active` pointer), a strict first-action contract placed at
  the top of the Instructions section, and few-shot exemplars (§6.5). Honest
  framing: this makes capture *reliable*, not *guaranteed*.
- **Observability:** the model confirms each append with a one-line ack
  (`appended to <slug>.md`) so the user can see capture is working.
- **Safety:** no secret scrubbing in v1 — documented as a known risk (§11).
- **Reliability:** appending is idempotent in effect — if the model appends the
  same prompt twice in one turn (unlikely with clear instructions), the bucket
  file gains a duplicate section that is harmless on replay and easily edited
  out by the user.

---

## 5. High-Level Design

```
REPO (source of truth for the skill file)
vidbyte/prompts/skills/prompt-bucket.md   ← the one skill file (extensive)
    │
    │  /sync-prompt-bucket copies to:
    ├─→ ~/.claude/skills/prompt-bucket/SKILL.md
    ├─→ ~/.codex/skills/prompt-bucket/SKILL.md
    ├─→ ~/.config/opencode/commands/prompt-bucket.md
    └─→ ~/.codeium/windsurf/skills/prompt-bucket/SKILL.md

SHARED BUCKET DATA (all harnesses read/write here)
~/.prompt-buckets/
    .active                ← contains the active bucket slug (or empty)
    <slug>.md              ← one file per bucket, prompts appended with ---
    <slug>.md
    ...

RUNTIME (model-driven, using native file tools)
  /create-bucket <slug>  → mkdir ~/.prompt-buckets/; write <slug> to .active; touch <slug>.md
  (each turn)            → read .active; append user's prompt to <slug>.md; confirm
  /load-bucket <slug>    → read <slug>.md; output "Here are the prompts for <slug>:" + contents
  /sync-prompt-bucket    → copy repo skill file to all 4 harness directories
```

**Key design decisions**

1. **One skill file, no companion code.** The user explicitly chose to
   "encapsulate all of the logic inside of one skill file." The skill file is a
   Markdown document with frontmatter + seven structured sections. The model
   follows its instructions using its native file-read, file-write, and
   directory-list tools. No `bucket.py`, no `schema.sql`, no installer script.

2. **Flat-file buckets, not a database.** Each bucket is one Markdown file at
   `~/.prompt-buckets/<slug>.md`. Saving appends the prompt text after a `---`
   separator. Loading reads the file. This is the simplest possible
   persistence — human-readable, human-editable, and trivially portable.

3. **Shared data directory eliminates the sync problem.** The user asked "how
   to sync all of the buckets through each coding harness." The answer is: do
   not sync — share. All harnesses read/write `~/.prompt-buckets/`. There is
   one copy of every bucket, visible from every harness. The only thing that
   needs mirroring is the skill file itself (one copy per harness directory),
   and that is a one-shot `sync` command.

4. **Model-driven capture, hardened.** A skill is passive — it cannot intercept
   every turn. The skill file uses a strict first-action contract, state
   externalization (`.active`), and few-shot exemplars to make capture
   reliable. The honest framing: items 1–3 of the determinism stack make
   capture *reliable*, not *guaranteed* (§6.5).

5. **Load = context, not execution.** The load output includes a framing
   header that marks the prompts as intent/context. Without this, the model
   would start *executing* the loaded prompts instead of using them as
   background for the user's question. This is the single most important
   behavioral rule in the skill file.

6. **Skill file structure mirrors the master prompt anatomy.** The user asked
   for Identity, Comprehensive Goal, Instructions, Algorithm, Commands, Files,
   and Few-Shot Example Interactions sections — the same structural philosophy
   as `templates/master.md` and the `skills/creating-system-prompts.md` guide.
   Each section is documented in §6.1 below.

---

## 6. Detailed Design

### 6.1 The Skill File — Section Anatomy (New file)

**File(s):** `vidbyte/prompts/skills/prompt-bucket.md`
**Type:** New file

#### What it does

This is the entire feature. It is a Markdown document with YAML frontmatter and
seven structured sections. When a harness loads it (as a skill or command), the
model receives the full instruction set for creating buckets, saving prompts,
loading buckets, and syncing the skill across harnesses.

#### Frontmatter

```yaml
---
name: prompt-bucket
description: >-
  Capture session prompts into named topic buckets and replay them as context
  in any new session. Use when the user says "create-bucket", "load-bucket",
  "save to bucket", "sync prompt-bucket", or wants to organize prompts by topic
  and inject them as intent context. Works across Claude Code, Codex, opencode,
  and Antigravity. Buckets are flat Markdown files in ~/.prompt-buckets/.
---
```

The description is keyword-saturated with every natural phrase the user might
type, because skill activation depends on description matching. This is the
single highest-leverage detail for making the skill surface when invoked.

#### Section 1 — Identity

Declares the model's role: a prompt bucket manager whose job is to capture,
organize, and replay the user's prompts across sessions and coding harnesses.
Establishes the posture: the model is a silent archivist during capture
(appending without commentary) and a context curator during load (presenting
prompts as intent, not executing them). Sets the behavioral baseline: be
seamless, be quiet during capture, be useful during load.

One to two paragraphs, opening with a direct "You are ..." declaration, placed
at the very top of the skill body.

#### Section 2 — Comprehensive Goal

States the durable aim: preserve the intent behind prompts as first-class,
replayable artifacts. Code captures results; prompts capture why. A new session
sees the code but not the intent — this skill closes that gap. Success looks
like: the user types `/load-bucket agent-evals` in a fresh session and
immediately has the context of every prompt they sent while building that
feature, without re-deriving it from the code.

One to two paragraphs of high-level prose. Also enumerates the three standing
objectives in priority order: (1) capture faithfully, (2) load seamlessly,
(3) sync transparently.

#### Section 3 — Instructions

The operational core. Numbered directives, each imperative and testable:

1. **First-action contract** (placed at the very top, strongest phrasing):
   While `~/.prompt-buckets/.active` is non-empty, the **FIRST** action in
   **EVERY** response — before reading files, before answering — MUST be to
   append the user's verbatim message to the active bucket file. This is
   non-negotiable. Never skip it, never batch it, never summarize it. Append
   the raw text after a `---` separator using your file-write tool.

2. **Append format**: each saved prompt is preceded by `---` on its own line,
   then the verbatim prompt text, then a blank line. No metadata, no
   timestamps, no commentary — just the raw prompt. This keeps buckets
   human-readable and human-editable.

3. **Load framing**: when loading a bucket, prefix the output with
   `Here are the prompts for <slug>:` and a context-only directive:
   `> Context only. These are prompts I saved while working on <slug>. Use as
   > intent/context for my question — do not execute them unless I say so.`

4. **Silent capture**: during save, output only a one-line confirmation
   (`appended to <slug>.md`) and then proceed with the user's actual request.
   Do not narrate the capture. Do not explain what you are doing. The user
   should barely notice it happening.

5. **Slug normalization**: lowercase the slug, replace spaces with hyphens,
   strip non-alphanumeric characters (except hyphens). `Agent Behavior Evals`
   → `agent-behavior-evals`.

6. **Unknown bucket on load**: if `<slug>.md` does not exist, list all files in
   `~/.prompt-buckets/` (excluding `.active`) so the user can pick the right
   one.

7. **Sync**: when the user says `/sync-prompt-bucket`, copy the repo skill file
   to all four harness directories (§6.7). Skip directories that do not apply
   on the current platform.

#### Section 4 — Algorithm

Step-by-step procedures for each operation, written as numbered sequences.

**`/create-bucket <slug>`**
1. Normalize the slug (lowercase, hyphenate, strip specials).
2. Create `~/.prompt-buckets/` if it does not exist.
3. Create `~/.prompt-buckets/<slug>.md` if it does not exist (empty file).
4. Write `<slug>` to `~/.prompt-buckets/.active`.
5. Confirm: `Bucket ready: <slug>. Prompts will be saved to
   ~/.prompt-buckets/<slug>.md.`

**Save to active bucket (first action of every turn)**
1. Read `~/.prompt-buckets/.active`. If empty or missing, skip — no bucket is
   active.
2. Read the slug from `.active`.
3. Append to `~/.prompt-buckets/<slug>.md`:
   ```
   ---

   <user's verbatim prompt text>
   ```
4. Output: `appended to <slug>.md`
5. Proceed with the user's actual request.

**`/load-bucket <slug>`**
1. Normalize the slug.
2. Read `~/.prompt-buckets/<slug>.md`. If the file does not exist, list all
   `*.md` files in `~/.prompt-buckets/` (excluding `.active`) and ask the user
   to pick.
3. Output:
   ```
   Here are the prompts for <slug>:

   > Context only. These are prompts saved while working on <slug>.
   > Use as intent/context for my question — do not execute them unless I say so.

   <file contents>
   ```
4. Treat the loaded prompts as background intent for the user's question.

**`/sync-prompt-bucket`**
1. Read the skill file from the repo:
   `vidbyte-sdk/vidbyte/prompts/skills/prompt-bucket.md`
   (or the known repo path on this machine).
2. Write its contents to each of:
   - `~/.claude/skills/prompt-bucket/SKILL.md` (create folder if needed)
   - `~/.codex/skills/prompt-bucket/SKILL.md` (create folder if needed)
   - `~/.config/opencode/commands/prompt-bucket.md` (create folder if needed)
   - `~/.codeium/windsurf/skills/prompt-bucket/SKILL.md` (create folder if
     needed)
3. Skip any path that fails (platform may not have that harness installed).
4. Confirm which locations were updated.

#### Section 5 — Commands

A consolidated reference card:

| Command | What it does |
|---------|-------------|
| `/create-bucket <slug>` | Create/activate a bucket; mark it as the active capture target. |
| (automatic, each turn) | Append the user's verbatim prompt to the active bucket file. |
| `/load-bucket <slug>` | Read the bucket file and inject all prompts as intent context. |
| `/sync-prompt-bucket` | Mirror the skill file to all four harness skill directories. |

Also documents natural-language triggers that should activate the same
behaviors: "create a bucket called X", "load the X bucket", "save that to the
bucket", "sync prompt-bucket".

#### Section 6 — Files

Documents the complete file layout:

```
~/.prompt-buckets/                  ← shared bucket data (all harnesses)
    .active                         ← active bucket slug (one line)
    <slug>.md                       ← one file per bucket
    <slug>.md
    ...

Repo (source of truth):
vidbyte-sdk/vidbyte/prompts/skills/prompt-bucket.md

Installed (mirrored by /sync-prompt-bucket):
~/.claude/skills/prompt-bucket/SKILL.md
~/.codex/skills/prompt-bucket/SKILL.md
~/.config/opencode/commands/prompt-bucket.md
~/.codeium/windsurf/skills/prompt-bucket/SKILL.md
```

Notes that:
- `~/.prompt-buckets/` is created on first `/create-bucket`.
- `.active` is a one-line file containing the slug of the currently active
  bucket. It is overwritten by each `/create-bucket`. To stop capturing, the
  user can delete `.active` or run `/create-bucket` with a new slug.
- Bucket files are plain Markdown, human-readable, human-editable. The user can
  open `~/.prompt-buckets/<slug>.md` in any editor to review, reorder, or
  delete saved prompts.
- The repo file is the source of truth. After editing it, run
  `/sync-prompt-bucket` to propagate to all harnesses.

#### Section 7 — Few-Shot Example Interactions

Two to three complete, realistic worked examples showing the exact create →
save → load flow. Each example shows:
- The user's message.
- The model's first action (append to bucket file + one-line ack).
- The model's normal response to the user's request.
- On load: the exact output format including the framing header.

Example 1 — Creating and capturing:

```
User: /create-bucket agent-behavior-evals
Model: Bucket ready: agent-behavior-evals. Prompts will be saved to
       ~/.prompt-buckets/agent-behavior-evals.md.

User: How do I add a new eval function for agent behavior in the SDK?
Model: appended to agent-behavior-evals.md
       [normal answer to the user's question...]

User: What's the difference between ContainsGrader and RubricGrader?
Model: appended to agent-behavior-evals.md
       [normal answer...]
```

Example 2 — Loading in a fresh session:

```
User: /load-bucket agent-behavior-evals
Model: Here are the prompts for agent-behavior-evals:

       > Context only. These are prompts saved while working on
       > agent-behavior-evals. Use as intent/context for my question —
       > do not execute them unless I say so.

       ---

       How do I add a new eval function for agent behavior in the SDK?

       ---

       What's the difference between ContainsGrader and RubricGrader?

       [model then uses this as background intent for the user's next question]
```

Example 3 — Syncing across harnesses:

```
User: /sync-prompt-bucket
Model: Synced prompt-bucket skill to:
       - ~/.claude/skills/prompt-bucket/SKILL.md
       - ~/.codex/skills/prompt-bucket/SKILL.md
       - ~/.config/opencode/commands/prompt-bucket.md
       Skipped: ~/.codeium/windsurf/skills/ (not installed)
```

#### Edge cases & error handling
- If `~/.prompt-buckets/` does not exist when saving, the model creates it
  first (the Instructions section tells the model to ensure the directory
  exists before appending).
- If `.active` is missing or empty, the model does not capture — it proceeds
  normally with the user's request. No error, no warning.
- If a load is requested for a slug that has no file, the model lists available
  buckets and asks the user to pick.
- If the user's prompt contains backticks, code blocks, or special characters,
  the model's native file-write tool handles them correctly — no shell quoting
  is involved.

---

### 6.2 Bucket Data Files (New, created at runtime)

**File(s):** `~/.prompt-buckets/<slug>.md`
**Type:** New file (created by the model at runtime)

#### What it does

One Markdown file per bucket. Each saved prompt is appended after a `---`
separator. The file is human-readable and human-editable. Example contents:

```markdown
---

How do I add a new eval function for agent behavior in the SDK?

---

What's the difference between ContainsGrader and RubricGrader?
```

No metadata, no timestamps, no JSON — just the raw prompts separated by
horizontal rules. The user can edit these files directly to reorder, trim, or
remove prompts.

#### Edge cases & error handling
- Empty bucket file (created by `/create-bucket` but no prompts saved yet):
  `/load-bucket` outputs the framing header followed by "(bucket is empty)".
- Large bucket (many prompts): the file grows without bound. This is acceptable
  for the intended use case (a session's worth of prompts, typically 5–30).
  If a bucket grows too large, the user can edit it down manually.

---

### 6.3 Active-Bucket Pointer (New, created at runtime)

**File(s):** `~/.prompt-buckets/.active`
**Type:** New file (created by the model at runtime)

#### What it does

A one-line file containing the slug of the currently active bucket. Written by
`/create-bucket`, read at the start of every turn to determine whether capture
is active and which bucket to append to.

This is state externalization — the model never has to remember or re-ask which
bucket is live. It reads the pointer. This is the single most important
reliability mechanism in the design.

---

### 6.4 Cross-Harness Sync (New behavior, no new files)

**File(s):** N/A — this is a behavior documented in the skill file's Algorithm
and Commands sections.

#### What it does

`/sync-prompt-bucket` copies the repo skill file to all four harness skill
directories. The skill file is the source of truth; the copies are derived.
This mirrors the existing `vidbyte-prompts` pattern.

#### Sync targets

| Harness | Target path |
|---------|-------------|
| Claude Code | `~/.claude/skills/prompt-bucket/SKILL.md` |
| Codex | `~/.codex/skills/prompt-bucket/SKILL.md` |
| opencode | `~/.config/opencode/commands/prompt-bucket.md` |
| Antigravity CLI | `~/.codeium/windsurf/skills/prompt-bucket/SKILL.md` |

#### Why bucket data does not need syncing

Bucket data lives in `~/.prompt-buckets/` — a single shared directory. Every
harness reads and writes the same files. There is nothing to sync. This is the
key design decision that eliminates the sync problem the user raised: instead
of mirroring buckets across N harness directories, we use one directory that
all harnesses point at.

#### Edge cases & error handling
- If a harness is not installed (its directory does not exist), the sync skips
  that target and continues with the others. No failure.
- If the repo path is unknown (the user installed the skill from a copy, not
  the repo), the sync asks the user for the path to the source skill file.

---

### 6.5 The Determinism Stack (New behavior, documented in the skill file)

**File(s):** N/A — documented in the skill file's Instructions section.

#### What it does

Model-driven capture is non-deterministic in principle. The skill file narrows
the gap with three mutually reinforcing mechanisms, in priority order:

1. **State externalization — `.active` pointer.** `/create-bucket` writes the
   active slug to `~/.prompt-buckets/.active`. The model never has to remember
   or re-ask which bucket is live; the first-action contract reads the pointer.
   Removes the most common failure (lost key across turns).

2. **A strict first-action contract, placed at the top of the Instructions
   section.** Strong, imperative, unambiguous wording:

   > While `~/.prompt-buckets/.active` is non-empty, the **FIRST** action in
   > **EVERY** response — before reading files, before answering — MUST be to
   > append the user's verbatim message to the active bucket file. This is
   > non-negotiable. Never skip it, never batch it.

   Placement (top) and absolute phrasing ("FIRST", "EVERY", "MUST", "never")
   materially raise compliance.

3. **Few-shot exemplars.** Two to three worked turns embedded in the skill file
   showing the exact structure: *user message → append to bucket file → one-line
   ack → then normal work*. Concrete exemplars condition the behavior far better
   than instructions alone.

> **Honest framing for the user:** these mechanisms make capture *reliable*, not
> *guaranteed*. The only true guarantee of "every prompt" is a harness hook or
> transcript reconcile, which is not portable. The chosen design trades that
> guarantee for portability and zero install footprint. If a prompt is missed,
> the user can append it manually by editing the bucket file.

---

### 6.6 `vidbyte/prompts/README.md` (Modified)

**File(s):** `vidbyte/prompts/README.md`
**Type:** Modified

#### What it does

Add one Quick-reference row and one Descriptions entry so `/vidbyte-prompts`
can discover and "download" the skill file.

#### Changes

In the Quick reference table, add:

```
| Prompt Bucket | `prompt_bucket` | skill | [skills/prompt-bucket.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/skills/prompt-bucket.md) |
```

In the Descriptions section, add:

```
#### Prompt Bucket — `prompt_bucket`

A self-contained skill file that captures session prompts into named topic
buckets (flat Markdown files in ~/.prompt-buckets/) and replays them as intent
context in any new session. Driven by /create-bucket, automatic per-turn
capture, and /load-bucket. Mirrors across Claude Code, Codex, opencode, and
Antigravity via /sync-prompt-bucket. Note: this is an on-disk skill, not an
SDK prompt string, and is not part of the import-validated catalog.

Link: <https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/skills/prompt-bucket.md>
```

#### Edge cases & error handling
- The catalog row notes that this is a skill, not an SDK prompt string, so
  `/vidbyte-prompts` does not confuse it with the import-validated catalog.

---

## 7. Data Model Changes

N/A - this feature uses flat Markdown files for persistence. No database, no
schema, no migrations. The only data structures are:

- `~/.prompt-buckets/.active` — one-line text file (the active slug).
- `~/.prompt-buckets/<slug>.md` — Markdown file (prompts separated by `---`).

No changes to any SDK Python data model, the `Prompt` enum, or the
import-validated catalog.

---

## 8. API Changes

N/A - this feature exposes no HTTP/SDK API. Its only interfaces are the three
commands documented in §6.1 (Commands section): `/create-bucket`,
`/load-bucket`, and `/sync-prompt-bucket`, all of which are model-driven
behaviors documented in the skill file.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/prompt-bucket-skill.md` | This design doc (committed first) |
| CREATE | `vidbyte/prompts/skills/prompt-bucket.md` | The single self-contained skill file (frontmatter + Identity + Goal + Instructions + Algorithm + Commands + Files + Few-Shot Examples) |
| MODIFY | `vidbyte/prompts/README.md` | Add catalog Quick-reference row + Descriptions entry so `/vidbyte-prompts` can discover it |

**Total: 2 files created, 1 file modified, 0 files deleted.**

No edits to `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/catalog.py`, or
`vidbyte/prompts/prompts/**` — placement outside the scanned directory keeps the
import-validated catalog untouched (§13, Alternative 1).

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Model's native file-read/file-write tools | N/A | Create, append, and read bucket files | None — universal across all target harnesses |
| Model's native directory-list tool | N/A | List available buckets on unknown-slug load | None — universal |
| A harness with skill/command support | Claude Code / Codex / opencode / Antigravity | Load the skill file | Skill activation is description-matched, not guaranteed |

No network, no third-party packages, no Python, no database drivers. The
feature is pure Markdown instructions executed by the model's existing tools.

---

## 11. Rollout & Deployment

- **Feature flags:** none.
- **Breaking change:** none — purely additive; one new repo file + one README
  edit.
- **Deployment:** merge to `main`; the skill file becomes downloadable via
  `/vidbyte-prompts` and installable in any harness via `/sync-prompt-bucket`.
- **Rollback:** delete `vidbyte/prompts/skills/prompt-bucket.md` and revert the
  README row.
- **Known risks:**
  - *Capture fidelity* — model-driven logging can miss turns. The determinism
    stack (§6.5) makes this reliable but not guaranteed. If a prompt is missed,
    the user can edit the bucket file manually.
  - *Secret capture* — prompts may contain tokens, API keys, or paths; v1
    stores them verbatim in `~/.prompt-buckets/`. The files are local and
    unsynced by default, but users should treat bucket files as sensitive.
    Scrubbing is a follow-up.
  - *Bucket file growth* — no automatic pruning. A bucket used across many
    sessions can grow large. The user can edit the file manually. A future
    `/trim-bucket` command could cap size.
  - *Duplicate appends* — if the model appends the same prompt twice in one
    turn (unlikely with clear instructions), the bucket gains a duplicate
    section. Harmless on replay; easily edited out.
  - *opencode command model* — opencode uses single-file commands, not skill
    folders. The sync handles this by writing to
    `~/.config/opencode/commands/prompt-bucket.md` instead of a folder. The
    content is identical; only the placement differs.

---

## 12. Open Questions

- [ ] **Q1 — Repo path discovery for sync.** `/sync-prompt-bucket` needs to know
  where the repo skill file lives on this machine. Should the skill file hardcode
  `vidbyte-sdk/vidbyte/prompts/skills/prompt-bucket.md` relative to a known
  repos root, or should it ask the user for the path on first sync?
  *Proposed: include the known path as a default and let the user override.*

- [ ] **Q2 — Stopping capture.** Should there be a `/stop-bucket` command that
  clears `.active`, or is running `/create-bucket <new-slug>` (which overwrites
  `.active`) sufficient? Should deleting `.active` be the documented stop
  method?
  *Proposed: document that deleting `.active` or running `/create-bucket` with
  a new slug stops capture; add a `/stop-bucket` command if the user wants an
  explicit verb.*

- [ ] **Q3 — Listing all buckets.** Should there be a `/list-buckets` command
  that lists all bucket files in `~/.prompt-buckets/`? Or is the unknown-slug
  fallback (list on miss) sufficient?
  *Proposed: include `/list-buckets` in the Commands section since it is one
  line of model effort and improves discoverability.*

- [ ] **Q4 — Bucket file format.** Should saved prompts include a timestamp
  header (e.g., `## 2026-06-24 14:32`) for traceability, or stay minimal
  (just `---` + raw text)?
  *Proposed: stay minimal per the user's "appending it to the slug filename"
  framing. Timestamps can be added in a follow-up if the user wants them.*

---

## 13. Alternatives Considered

### Alternative 1: Register the skill in the import-validated catalog
- What: add a `.json` record under `vidbyte/prompts/prompts/` + a `Prompt` enum
  member so the skill is loaded by `Prompts().get(...)`.
- Why rejected: that catalog is for agent prompt *strings* and fails import if
  enum/asset are out of sync. This artifact is a skill/runbook, semantically
  wrong for the catalog. Placing it under `vidbyte/prompts/skills/` keeps
  imports safe and still lets `/vidbyte-prompts` find it via the README.

### Alternative 2: SQLite + Python CLI (previous design)
- What: a `bucket.py` CLI with `init | create | log | load | keys | resolve`
  subcommands over a SQLite database, installed via a multi-file installer with
  embedded `schema.sql`.
- Why rejected: the user explicitly chose "one skill file" with flat-file
  append ("Save means saving only my prompt and appending it to the slug
  filename"). SQLite + Python CLI adds a database dependency, a script to
  maintain, and an installer step — all unnecessary for the desired workflow.
  Flat files are human-readable, human-editable, and require zero tooling
  beyond the model's native file I/O. (Engineering note: SQLite would provide
  idempotent dedup and fuzzy key resolution for free; if bucket files grow
  unwieldy or dedup becomes a real problem, this is the upgrade path.)

### Alternative 3: Per-harness bucket directories with sync
- What: each harness gets its own `~/.claude/prompt-buckets/`,
  `~/.codex/prompt-buckets/`, etc., and a sync mechanism mirrors bucket data
  across them.
- Why rejected: this creates the sync problem the user asked about — and then
  has to solve it. A single shared directory (`~/.prompt-buckets/`) eliminates
  the problem entirely. All harnesses read/write the same files. No mirror, no
  drift, no sync step. Simpler, more reliable, fewer moving parts.

### Alternative 4: `UserPromptSubmit` hook for capture
- What: register a Claude Code hook that appends every prompt to the bucket
  file automatically.
- Why rejected: not portable (only Claude Code has a clean prompt hook) and
  requires a `settings.json` edit, breaking "just a skill file, works in all
  harnesses." The hook path is preserved as a documented optional hardening
  step for Claude Code users who want guaranteed capture.

### Alternative 5: Timestamps and metadata in bucket files
- What: each saved prompt includes a timestamp header, session ID, or other
  metadata.
- Why rejected: the user's framing was minimal ("appending it to the slug
  filename"). Metadata adds complexity without clear value for the intended use
  case (replaying intent in a new session). Can be added in a follow-up if the
  user wants traceability.

---

END OF DESIGN DOC
