# Design Doc: Prompt Bucket Skill

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-24
**Last Updated:** 2026-06-24

---

## 1. Overview

`prompt-bucket` is a self-contained, cross-harness coding-agent skill that captures the
user's *prompts* (not the resulting code) into named topic "buckets" backed by a local
SQLite database, and replays a whole bucket into a fresh session on demand. It ships as a
**single installer Markdown file** in the Vidbyte SDK repo that, when run by any coding
harness (Claude Code, Codex, opencode, Antigravity), expands into a multi-file skill
folder on disk and then strips its own setup instructions so the installed skill is lean.
Two commands drive it: `/create-bucket --key <key>` (start capturing this session's
prompts into a bucket) and `/load-bucket --key <key>` (preload every prompt previously
captured under that bucket).

The motivating insight: the prompts a user sends while building a feature are thin, dense
artifacts of *intent*. Code captures the result; prompts capture the why. A new session
sees the code but not the intent. This skill makes that intent a first-class, replayable
asset.

---

## 2. Goals & Non-Goals

### Goals
- One installer `.md` in `vidbyte/prompts/` that installs a **multi-file** skill but is
  invoked as if it were a single file ("install anywhere with one line").
- `/create-bucket --key <key>`: create/activate a bucket and capture each subsequent
  session prompt into it.
- `/load-bucket --key <key>`: query SQLite and return all captured prompts for a bucket,
  concatenated in capture order, as replay-ready context.
- A human/model-readable registry of all bucket keys so a slightly-wrong key still
  resolves (fuzzy match).
- Everything (SKILL.md, schema, script, keys registry, DB) lives in **one folder** so the
  skill is portable and location-independent.
- Work in any harness "by default, because it is just a prompt" — no hooks, no
  harness-specific APIs; capture is model-driven, persistence is a plain Python + SQLite
  CLI invoked through the terminal.
- Push model-driven capture as close to deterministic as possible without a hook.
- Installer strips its own `SETUP` section from the installed `SKILL.md` after scaffolding.

### Non-Goals
- **Automatic, lossless, hook-based capture.** A pure skill cannot intercept every turn;
  only a `UserPromptSubmit` hook can, and hooks are not portable across harnesses. We
  explicitly choose model-driven capture (see §13, Alternative 1) and mitigate its
  fidelity gap instead of eliminating it.
- No server, no network calls, no external dependencies beyond the Python 3 standard
  library (`sqlite3`, `difflib`, `hashlib`, `argparse`).
- No tests or verification scripts (per the `design-doc-no-tests` workflow).
- No change to the import-validated `vidbyte/prompts/prompts/` catalog or the `Prompt`
  enum (this artifact is a runbook/installer, not an SDK prompt string — see §5).
- Not solving multi-machine sync of the SQLite DB (single-machine, local file).

---

## 3. Background & Context

The Vidbyte SDK already ships a prompt catalog under `vidbyte/prompts/prompts/`, loaded by
`vidbyte/prompts/catalog.py` and keyed by the `Prompt` enum in
`vidbyte/lib/enums/prompts.py`. That catalog is **validated at import time**: every
`.json` record's prompt keys must map to an enum member, and every enum member must have a
backing asset, or the package fails to import. Those assets are *agent prompt strings*
consumed programmatically by agents and the MCP server.

The user also maintains a personal cross-platform `/vidbyte-prompts` skill whose source of
truth is the **Available Prompts** table in `vidbyte/prompts/README.md`. Asking that skill
to "download the vidbyte `<name>` prompt" makes it read the README, match a row, and save
that row's link into the user's collection.

This feature is a *different kind of artifact*: an installer/runbook prompt that scaffolds
an on-disk skill. Forcing it into the import-validated catalog would (a) require an enum
edit and (b) load a runbook as if it were an agent prompt string. So we place it under
`vidbyte/prompts/` but **outside** the scanned `vidbyte/prompts/prompts/` directory, and we
add a README catalog row so `/vidbyte-prompts` can still discover and "download" it.

The capture-mechanism constraint is the load-bearing design fact: a **skill is passive**.
It is context injected when invoked; it does not execute code on every user turn. Logging
"every prompt in the session" therefore depends on the model choosing to run a log command
each turn. We accept that and engineer around it (§6.4).

---

## 4. Requirements

### Functional Requirements
1. A single repo file `vidbyte/prompts/skills/prompt-bucket.md` contains the entire skill:
   the live `SKILL.md` body **plus** a `SETUP` block holding every supporting file's
   contents (schema, Python CLI, keys template) and the install steps.
2. Running the installer creates a folder containing: `SKILL.md`, `schema.sql`,
   `bucket.py`, `keys.md`, and (after init) `buckets.db`.
3. After scaffolding, the installer **removes** the `SETUP` block from the installed
   `SKILL.md`, leaving only command + behavior documentation.
4. `/create-bucket --key <key>` creates the bucket if absent, marks it the **active
   bucket** (a pointer file), and refreshes `keys.md`.
5. While a bucket is active, the skill instructs the model to log the user's verbatim
   prompt to that bucket at the start of every turn.
6. Logging is **idempotent**: re-logging an identical prompt to the same bucket is a no-op
   (so over-logging and reconciliation are safe).
7. `/load-bucket --key <key>` returns every prompt stored under the bucket, in capture
   order, as a single replay-ready block printed to stdout.
8. If `<key>` is not an exact match, the skill resolves it to the closest known key
   (fuzzy, cutoff-based); on no confident match it lists available keys.
9. `keys.md` always reflects the set of known keys (regenerated from the DB).
10. All paths are resolved relative to the script's own directory, so the folder works
    regardless of where it is installed.
11. The Python CLI reads prompt text from a **file or stdin**, never from a positional
    shell argument, so quotes/newlines/backticks in prompts cannot corrupt capture.
12. A README catalog row + description is added so `/vidbyte-prompts` can discover it.

### Non-Functional Requirements
- **Portability:** standard library only; runs under any Python 3.9+; no harness API.
- **Cross-shell safety:** correct under PowerShell, cmd, bash, zsh (file/stdin input;
  `Path(__file__)` resolution; UTF-8 everywhere).
- **Determinism (best-effort):** capture reliability maximized via state externalization,
  a strict first-action contract, idempotency, few-shot exemplars, and an optional
  load-time reconcile (§6.4).
- **Observability:** every CLI subcommand prints a one-line outcome (`logged`,
  `duplicate-skip`, `resolved 'x' -> 'y'`, etc.) so the model can confirm success.
- **Safety:** no secret scrubbing in v1 — documented as a known risk (§11) because buckets
  may capture tokens/paths verbatim.
- **Reliability:** `INSERT OR IGNORE` + unique constraints make repeated runs harmless.

---

## 5. High-Level Design

Three layers, deliberately decoupled:

```
ONE REPO FILE                         INSTALLED SKILL FOLDER (anywhere)
vidbyte/prompts/skills/               ~/.claude/skills/prompt-bucket/  (or codex/etc.)
  prompt-bucket.md   --- install -->    SKILL.md      (installer minus SETUP block)
   ├─ SKILL body                        schema.sql    (from SETUP)
   └─ SETUP block ──────────────────►   bucket.py     (from SETUP)
       (embedded files + steps,         keys.md       (generated)
        deleted after install)          buckets.db    (created by `bucket.py init`)
                                        .active_bucket (runtime pointer)

RUNTIME
  /create-bucket --key K  ->  python bucket.py create --key K   (+ writes .active_bucket)
  (each turn, model-driven) ->  python bucket.py log --key K --file <tmp>
  /load-bucket  --key K   ->  python bucket.py load --key K     (stdout = replay block)
```

**Key design decisions**

1. **Single-file install → multi-file skill.** The repo holds one `.md`. Its `SETUP` block
   embeds the contents of `schema.sql`, `bucket.py`, and the `keys.md` template inside
   fenced code blocks, plus ordered install steps. The model writes those files, runs
   `python bucket.py init`, then deletes the `SETUP` block from the now-installed
   `SKILL.md`. This satisfies "multiple files, installed as if one file" and "remove the
   setup context after setup."

2. **Persistence is a plain CLI, not harness magic.** A single `bucket.py` exposes
   `init | create | log | load | keys | resolve` subcommands over SQLite. Because it is
   invoked through the terminal, it is harness-agnostic by construction — any harness that
   can read a skill file and run a shell command can use it.

3. **The DB and all state live in the skill folder**, resolved via `Path(__file__).parent`.
   The folder is therefore relocatable and the bucket store is global across sessions and
   projects (which is exactly what cross-session intent recall needs).

4. **Capture is model-driven but hardened.** §6.4 specifies the reliability stack that
   makes "the model logs every prompt" close to deterministic without a hook.

5. **Fuzzy key resolution** lives in code (`difflib.get_close_matches`) and is mirrored to
   `keys.md` so the model can also eyeball the correct key cheaply.

---

## 6. Detailed Design

### 6.1 `schema.sql` (New file)

**File(s):** `<skill-dir>/schema.sql`
**Type:** New file (embedded in installer SETUP block)

#### What it does
Defines the two-table store: `buckets` (one row per key) and `prompts` (append-only,
ordered, idempotent per bucket).

#### Contents
```sql
CREATE TABLE IF NOT EXISTS buckets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id   INTEGER NOT NULL REFERENCES buckets(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    text        TEXT NOT NULL,
    hash        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE(bucket_id, hash)
);

CREATE INDEX IF NOT EXISTS idx_prompts_bucket_seq ON prompts(bucket_id, seq);
```

#### Edge cases & error handling
- `UNIQUE(bucket_id, hash)` makes duplicate logging a no-op via `INSERT OR IGNORE`.
- Trade-off: a genuinely repeated identical prompt is captured once (accepted; identical
  repeats carry no new intent — see §11).

---

### 6.2 `bucket.py` (New file)

**File(s):** `<skill-dir>/bucket.py`
**Type:** New file (embedded in installer SETUP block)

#### What it does
The whole persistence layer and CLI. `BucketStore` owns all SQLite access; `BucketCli`
maps subcommands onto it. Paths resolve from the script's own directory.

#### Interface / API
```python
#!/usr/bin/env python3
"""prompt-bucket — SQLite-backed store for topic buckets of session prompts."""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DB_FILE = SKILL_DIR / "buckets.db"
SCHEMA_FILE = SKILL_DIR / "schema.sql"
KEYS_FILE = SKILL_DIR / "keys.md"
ACTIVE_FILE = SKILL_DIR / ".active_bucket"


class BucketStore:
    """SQLite-backed CRUD for prompt buckets and their captured prompts."""

    def __init__(self, db_path: Path = DB_FILE) -> None:
        # Opens (and lazily creates) the SQLite database file at db_path.
        self._connection = sqlite3.connect(db_path)
        self._connection.execute("PRAGMA foreign_keys = ON;")
        self._connection.execute("PRAGMA busy_timeout = 5000;")

    def initialize(self) -> None:
        # Creates all tables by executing the bundled schema.sql DDL script.
        self._connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        self._connection.commit()

    def create_bucket(self, key: str) -> None:
        # Registers a bucket key (no-op if it exists) and refreshes keys.md.
        self._connection.execute("INSERT OR IGNORE INTO buckets(key, created_at) VALUES(?, ?)", (key, self._now()))
        self._connection.commit()
        self.sync_keys_file()

    def log_prompt(self, key: str, text: str) -> bool:
        # Appends one prompt to a bucket idempotently; True only on a fresh insert.
        bucket_id = self._bucket_id(key)
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO prompts(bucket_id, seq, text, hash, created_at) VALUES(?, ?, ?, ?, ?)",
            (bucket_id, self._next_seq(bucket_id), text, self._hash(text), self._now()),
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def load_prompts(self, key: str) -> list[str]:
        # Returns every prompt stored under a bucket, in capture order.
        bucket_id = self._bucket_id(key)
        rows = self._connection.execute("SELECT text FROM prompts WHERE bucket_id=? ORDER BY seq", (bucket_id,)).fetchall()
        return [row[0] for row in rows]

    def list_keys(self) -> list[str]:
        # Returns all known bucket keys sorted alphabetically.
        rows = self._connection.execute("SELECT key FROM buckets ORDER BY key").fetchall()
        return [row[0] for row in rows]

    def resolve_key(self, key: str) -> str | None:
        # Returns the exact key, else the closest fuzzy match above threshold, else None.
        keys = self.list_keys()
        if key in keys:
            return key
        matches = get_close_matches(key, keys, n=1, cutoff=0.6)
        return matches[0] if matches else None

    def sync_keys_file(self) -> None:
        # Rewrites keys.md from the database so the model can fuzzy-match offline.
        body = [f"- `{key}`" for key in self.list_keys()] or ["- _(none yet)_"]
        KEYS_FILE.write_text("# Bucket keys\n\nKnown keys (source of truth = buckets.db):\n\n" + "\n".join(body) + "\n", encoding="utf-8")

    def _bucket_id(self, key: str) -> int:
        # Looks up a bucket's row id, raising KeyError when the bucket is unknown.
        row = self._connection.execute("SELECT id FROM buckets WHERE key=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return int(row[0])

    def _next_seq(self, bucket_id: int) -> int:
        # Computes the next 1-based capture sequence number for a bucket.
        row = self._connection.execute("SELECT COALESCE(MAX(seq), 0) FROM prompts WHERE bucket_id=?", (bucket_id,)).fetchone()
        return int(row[0]) + 1

    @staticmethod
    def _hash(text: str) -> str:
        # Returns a stable SHA-256 hex digest of the prompt for idempotent de-duplication.
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> str:
        # Returns the current UTC time as an ISO-8601 string.
        return datetime.now(timezone.utc).isoformat()


class BucketCli:
    """Maps command-line subcommands onto a BucketStore instance."""

    def __init__(self, store: BucketStore) -> None:
        # Stores the BucketStore that subcommand handlers operate against.
        self._store = store

    def run(self, argv: list[str]) -> int:
        # Parses argv, dispatches to the selected handler, and returns an exit code.
        args = self._build_parser().parse_args(argv)
        return args.handler(args)

    def _build_parser(self) -> argparse.ArgumentParser:
        # Declares every subcommand and binds each to its handler method.
        parser = argparse.ArgumentParser(prog="bucket")
        sub = parser.add_subparsers(required=True)
        self._add(sub, "init", self._init)
        self._add(sub, "create", self._create, key=True)
        self._add(sub, "log", self._log, key=True, io=True)
        self._add(sub, "load", self._load, key=True)
        self._add(sub, "keys", self._keys)
        self._add(sub, "resolve", self._resolve, key=True)
        return parser

    def _add(self, sub: argparse._SubParsersAction, name: str, handler, key: bool = False, io: bool = False) -> None:
        # Registers one subcommand with the optional --key and input flags it needs.
        spec = sub.add_parser(name)
        if key:
            spec.add_argument("--key", required=True)
        if io:
            spec.add_argument("--file")
            spec.add_argument("--stdin", action="store_true")
        spec.set_defaults(handler=handler)

    def _init(self, args: argparse.Namespace) -> int:
        # Creates the schema and an empty keys.md, then reports readiness.
        self._store.initialize()
        self._store.sync_keys_file()
        print("prompt-bucket initialized")
        return 0

    def _create(self, args: argparse.Namespace) -> int:
        # Creates/activates a bucket and records it as the active bucket.
        self._store.create_bucket(args.key)
        ACTIVE_FILE.write_text(args.key, encoding="utf-8")
        print(f"bucket ready: {args.key}")
        return 0

    def _log(self, args: argparse.Namespace) -> int:
        # Logs one prompt (read from --file or stdin) into the bucket idempotently.
        inserted = self._store.log_prompt(args.key, self._read_text(args))
        print("logged" if inserted else "duplicate-skip")
        return 0

    def _load(self, args: argparse.Namespace) -> int:
        # Resolves the key, prints the bucket's prompts, or lists keys on a miss.
        resolved = self._store.resolve_key(args.key)
        if resolved is None:
            print("NO_MATCH; available keys: " + ", ".join(self._store.list_keys()), file=sys.stderr)
            return 1
        if resolved != args.key:
            print(f"# resolved '{args.key}' -> '{resolved}'", file=sys.stderr)
        print(self._format(self._store.load_prompts(resolved)))
        return 0

    def _keys(self, args: argparse.Namespace) -> int:
        # Refreshes keys.md and prints all known keys.
        self._store.sync_keys_file()
        print("\n".join(self._store.list_keys()))
        return 0

    def _resolve(self, args: argparse.Namespace) -> int:
        # Prints the resolved key for a possibly-misspelled input, or NO_MATCH.
        print(self._store.resolve_key(args.key) or "NO_MATCH")
        return 0

    def _read_text(self, args: argparse.Namespace) -> str:
        # Reads prompt text from --file or stdin to avoid shell-quoting corruption.
        if args.file:
            return Path(args.file).read_text(encoding="utf-8")
        return sys.stdin.read()

    @staticmethod
    def _format(prompts: list[str]) -> str:
        # Renders stored prompts as a numbered, replay-ready transcript block.
        blocks = [f"### Prompt {index}\n{text}" for index, text in enumerate(prompts, start=1)]
        return "\n\n".join(blocks) if blocks else "(bucket is empty)"


def main() -> int:
    # Program entry point: wires a BucketStore into the CLI and runs it.
    return BucketCli(BucketStore()).run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
```

#### Edge cases & error handling
- `load`/`log` against an unknown key raise `KeyError`; `load` pre-resolves and reports
  `NO_MATCH` + available keys with exit 1, so the model can recover.
- `--file` is preferred over `--stdin`; the few-shot tells the model to write the verbatim
  prompt to a temp file with its native file-write tool, sidestepping all shell escaping.
- UTF-8 is forced on every read/write for cross-platform correctness.

---

### 6.3 `keys.md` (New file, generated)

**File(s):** `<skill-dir>/keys.md`
**Type:** New file (template embedded in SETUP; thereafter regenerated by `bucket.py`)

#### What it does
A regenerated, model-facing list of every known bucket key. Lets the model fuzzy-match a
mistyped `--key` by glancing at the file, complementing the programmatic `resolve`.
Source of truth remains `buckets.db`; `keys.md` is a derived view kept in sync by
`create`/`keys`.

---

### 6.4 `SKILL.md` behavior + the determinism stack (New file)

**File(s):** `<skill-dir>/SKILL.md` (== installer `.md` minus the SETUP block)
**Type:** New file

#### What it does
Frontmatter (`name: prompt-bucket`, `description`) plus the command contract and the
capture behavior. This is the *only* part that survives install.

#### Command contract
- **`/create-bucket --key <key>`** → run `python bucket.py create --key <key>`; confirm
  `bucket ready: <key>`; from now on, this is the active bucket.
- **`/load-bucket --key <key>`** → run `python bucket.py load --key <key>`; treat stdout as
  injected intent context for the rest of the session; if stderr shows a `resolved` line,
  tell the user which key was used.

#### The determinism stack (answer to "how do we make model-driven capture reliable?")
Model-driven capture is non-deterministic in principle. We narrow the gap with five
mutually reinforcing mechanisms, in priority order:

0. **Per-conversation arming (correctness guard).** Capture is armed only when the user ran
   `/create-bucket` *in the current conversation*. The `.active_bucket` file records the
   most-recent key but is NOT, by itself, consent to capture — otherwise a stale pointer from
   a prior session would silently log unrelated prompts into an old bucket. Re-running
   `/create-bucket --key <key>` re-arms (and is idempotent). This scopes "every prompt in the
   session" to the session the user actually intended.

1. **State externalization — `.active_bucket` pointer.** `create` writes the active key to
   disk so, once armed, the model never has to remember or re-ask which bucket is live.
   Removes the most common failure (lost key across turns).

2. **A strict first-action contract, placed at the top of the behavior section.** Strong,
   imperative, unambiguous wording, e.g.:
   > While capture is armed, the **FIRST** action in **EVERY** response — before reading
   > files, before answering — MUST be to log the user's verbatim message: write it to a temp
   > file, then run `python <skill-dir>/bucket.py log --key <active> --file <tmp>`.
   > This is non-negotiable and idempotent; never skip it, never batch it.

   Placement (top) and absolute phrasing ("FIRST", "EVERY", "MUST", "never") materially
   raise compliance.

3. **One idempotent, low-friction command.** A single `log` call per turn, safe to repeat
   (`INSERT OR IGNORE` on a content hash). Low friction → higher compliance; idempotency →
   over-logging and reconciliation never corrupt the bucket.

4. **Few-shot exemplars.** Two or three worked turns embedded in `SKILL.md` showing the
   exact structure: *user message → write temp file → `bucket.py log` → then normal work*.
   Concrete exemplars condition the behavior far better than instructions alone.

5. **Load-time reconcile (optional hardening, the near-deterministic guarantee).** Because
   every harness already persists prompts to a session transcript, `/load-bucket` can
   *also* be told to scan the current session's not-yet-logged prompts and insert them
   before reading back — converting "lossy live capture" into "eventually complete." This
   is harness-specific (transcript paths differ) so it is documented as an opt-in step for
   Claude Code first, not part of the portable core (§12 open question).

> Honest framing for the user: items 1–4 make capture *reliable*, not *guaranteed*. The
> only true guarantee of "every prompt" is a hook or transcript reconcile (item 5). The
> chosen design trades that guarantee for portability and zero install footprint.

---

### 6.5 `prompt-bucket.md` installer (New file, the single repo artifact)

**File(s):** `vidbyte/prompts/skills/prompt-bucket.md`
**Type:** New file

#### Structure
```markdown
---
name: prompt-bucket
description: Capture this session's prompts into a named SQLite bucket and replay them later.
---

# Prompt Bucket

<!-- SETUP:START — remove this entire block after installing -->
## Installation (run once, then delete this SETUP block)
1. Pick the skills dir for the current harness and create `prompt-bucket/` inside it:
   - Claude Code:     ~/.claude/skills/prompt-bucket/
   - Codex:           ~/.codex/skills/prompt-bucket/
   - Antigravity CLI: ~/.codeium/windsurf/skills/prompt-bucket/
   - opencode:        place files in ~/.claude/skills/prompt-bucket/ and create
                      ~/.config/opencode/commands/prompt-bucket.md delegating to it
2. Write `schema.sql` with the SQL below.            ```sql ... ```
3. Write `bucket.py` with the Python below.          ```python ... ```
4. Write `keys.md` with the template below.          ```markdown ... ```
5. Save THIS file as `SKILL.md` in that folder.
6. Run: `python prompt-bucket/bucket.py init`
7. Delete everything between SETUP:START and SETUP:END from the installed SKILL.md.
<!-- SETUP:END -->

## Commands           (survives as the live SKILL.md)
### /create-bucket --key <key> ...
### /load-bucket  --key <key> ...

## Capture behavior   (the determinism stack from §6.4 + few-shot)
...
```

The full code in steps 2–3 is exactly §6.1 and §6.2. After step 7, the installed
`SKILL.md` contains only the Commands + Capture-behavior sections.

---

### 6.6 `vidbyte/prompts/README.md` (Modified)

Add one Quick-reference row and one Descriptions entry so `/vidbyte-prompts` can discover
and "download" the installer:

```
| Prompt Bucket | `prompt_bucket` | installer | [skills/prompt-bucket.md](https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/skills/prompt-bucket.md) |
```
Description: a self-contained installer skill that captures session prompts into named
SQLite buckets and replays them on demand. Note in the description that it installs an
on-disk skill (it is not an SDK prompt string) and is **not** part of the import-validated
catalog.

---

## 7. Data Model Changes

### 7.1 SQLite `buckets` (New)
**Change type:** New (local file `buckets.db`, created at install via `bucket.py init`)
```sql
buckets(id PK, key TEXT UNIQUE, created_at TEXT)
```

### 7.2 SQLite `prompts` (New)
**Change type:** New
```sql
prompts(id PK, bucket_id FK->buckets, seq INT, text TEXT, hash TEXT, created_at TEXT,
        UNIQUE(bucket_id, hash))
```
**Migration strategy:** N/A — created fresh on install; `CREATE TABLE IF NOT EXISTS` makes
re-init idempotent. No changes to any SDK Python data model or the `Prompt` enum.

---

## 8. API Changes

N/A — this feature exposes no HTTP/SDK API. Its only interface is the `bucket.py` CLI
(`init | create | log | load | keys | resolve`) documented in §6.2.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/prompt-bucket-skill.md` | This design doc (committed first) |
| CREATE | `vidbyte/prompts/skills/prompt-bucket.md` | The single self-contained installer (embeds schema.sql, bucket.py, keys.md template, SETUP steps, SKILL body) |
| MODIFY | `vidbyte/prompts/README.md` | Add catalog Quick-reference row + Descriptions entry so `/vidbyte-prompts` can discover it |

No edits to `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/catalog.py`, or
`vidbyte/prompts/prompts/**` — placement outside the scanned dir keeps the import-validated
catalog untouched (see §13, Alternative 3).

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python 3 stdlib (`sqlite3`, `difflib`, `hashlib`, `argparse`, `pathlib`) | ≥ 3.9 | Persistence + CLI + fuzzy match | None — ubiquitous |
| A harness with file-write + shell tools | Claude Code / Codex / opencode / Antigravity | Install + per-turn logging | Capture fidelity depends on the model honoring the contract (§6.4) |

No network, no third-party packages.

---

## 11. Rollout & Deployment

- **Feature flags:** none.
- **Breaking change:** none — purely additive; one new repo file + one README edit.
- **Deployment:** merge to `main`; the installer becomes downloadable via `/vidbyte-prompts`
  and runnable in any harness.
- **Rollback:** delete `vidbyte/prompts/skills/prompt-bucket.md` and revert the README row.
- **Known risks:**
  - *Secret capture* — prompts may contain tokens/paths; v1 stores them verbatim. The DB is
    local and unsynced, but users should treat `buckets.db` as sensitive. Scrubbing is a
    follow-up.
  - *Capture fidelity* — model-driven logging can miss turns (§6.4 mitigations; §12 Q1).
  - *Identical-prompt dedup* — exact repeats are stored once by design.
  - *opencode single-file commands* — its command model isn't folder-based; handled by a
    delegating command file (§12 Q2).

---

## 12. Open Questions

- [ ] **Q1 — Load-time reconcile in v1?** Ship the optional transcript-reconcile (§6.4 item
  5) for Claude Code now (closes the fidelity gap), or defer to a follow-up to keep v1
  strictly portable? *Proposed: defer; document the hook/reconcile path in SKILL.md.*
- [ ] **Q2 — opencode entry point.** Confirm the delegating `commands/prompt-bucket.md`
  approach (files live in a folder; the command calls them by absolute path) vs. declaring
  opencode out of scope for v1. *Proposed: document the delegating command; folder-based
  harnesses are the primary target.*
- [ ] **Q3 — Install destination selection.** Should the installer auto-detect the running
  harness's skills dir, or always install to `~/.claude/skills/` and list alternates?
  *Proposed: default to the running harness's dir; fall back to Claude Code path.*
- [ ] **Q4 — DB location.** Keep `buckets.db` inside the skill folder (per your "all in one
  folder" requirement) vs. a fixed `~/.prompt-bucket/` so every harness shares one store.
  *Proposed: in-folder per your stated preference; note the shared-store alternative.*

---

## 13. Alternatives Considered

### Alternative 1: `UserPromptSubmit` hook for capture
- What: register a Claude Code hook that appends every prompt to SQLite automatically.
- Why rejected: not portable (only Claude Code has a clean prompt hook) and requires a
  `settings.json` edit, breaking "just a prompt, works in all harnesses." You explicitly
  chose model-driven capture; the hook path is preserved as optional hardening (§6.4-5).

### Alternative 2: Ship a real multi-file skill folder + copy-install
- What: commit the actual folder to the repo; installer copies it.
- Why rejected: you chose the single-file installer that expands on disk. (Engineering
  note: copy-install gives testable, lint-able files and deterministic installs; if file
  fidelity ever becomes a pain point, this is the upgrade path.)

### Alternative 3: Register the prompt in the import-validated catalog
- What: add a `.json` record under `vidbyte/prompts/prompts/` + a `Prompt` enum member.
- Why rejected: that catalog is for agent prompt *strings* and fails import if enum/asset
  are out of sync. This artifact is an installer/runbook, semantically wrong for the
  catalog. Placing it under `vidbyte/prompts/skills/` keeps imports safe and still lets
  `/vidbyte-prompts` find it via the README.

### Alternative 4: One Python file with the schema inlined (no schema.sql)
- What: embed DDL as a string constant; drop `schema.sql`.
- Why rejected: you asked specifically for the SQL to live at a file location; a separate
  `schema.sql` honors that and keeps DDL inspectable.

---

END OF DESIGN DOC
