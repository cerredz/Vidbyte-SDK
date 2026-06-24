---
name: prompt-bucket
description: Capture this session's prompts into a named SQLite bucket and replay every prompt from a bucket on demand. Use when the user runs /create-bucket --key <key>, /load-bucket --key <key>, or asks to save/preload the prompts behind a topic.
---

# Prompt Bucket

Capture the **prompts** you send while building something — the thin artifacts that hold
your intent — into a named SQLite "bucket", then replay a whole bucket into a fresh session.
Code captures the result; your prompts capture the *why*. This skill makes that why a
replayable asset.

Two commands:

- `/create-bucket --key <key>` — create/activate a bucket; from now on every prompt this
  session is logged into it.
- `/load-bucket --key <key>` — print every prompt previously captured under that bucket, in
  order, as context to preload.

<!-- SETUP:START — INSTALLER ONLY. Perform these steps once, then DELETE this whole block (everything from SETUP:START to SETUP:END) from the installed SKILL.md. -->

## Installation (run once, then delete this SETUP block)

You are installing the `prompt-bucket` skill. The supporting files below must be written to
the **same folder** this skill lives in, so the skill is fully self-contained and
relocatable.

1. **Choose the skill folder for the current harness** and create `prompt-bucket/` in it:
   - Claude Code: `~/.claude/skills/prompt-bucket/`
   - Codex: `~/.codex/skills/prompt-bucket/`
   - Antigravity CLI: `~/.codeium/windsurf/skills/prompt-bucket/`
   - opencode: write the files to `~/.claude/skills/prompt-bucket/` (a folder-based home),
     then create `~/.config/opencode/commands/prompt-bucket.md` whose body is "Run the
     prompt-bucket skill at ~/.claude/skills/prompt-bucket/SKILL.md" so the single-file
     command delegates to the folder. (opencode commands are single files, not folders.)

   Use the folder of the harness you are running in. Call this folder `<SKILL_DIR>` below.

2. **Write `<SKILL_DIR>/schema.sql`** with exactly:

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

3. **Write `<SKILL_DIR>/bucket.py`** with exactly:

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
        header = "# Bucket keys\n\nKnown keys (source of truth = buckets.db):\n\n"
        KEYS_FILE.write_text(header + "\n".join(body) + "\n", encoding="utf-8")

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

4. **Write `<SKILL_DIR>/keys.md`** with exactly:

```markdown
# Bucket keys

Known keys (source of truth = buckets.db):

- _(none yet)_
```

5. **Save THIS file as `<SKILL_DIR>/SKILL.md`** (copy it verbatim).

6. **Initialize the database:** run `python <SKILL_DIR>/bucket.py init` (use `python3` if
   `python` is unavailable). Expect output `prompt-bucket initialized`.

7. **Strip setup:** in the just-saved `<SKILL_DIR>/SKILL.md`, delete this entire block —
   everything from the `SETUP:START` marker to the `SETUP:END` marker, inclusive. The
   installed `SKILL.md` must NOT contain the installation steps or the embedded source.

8. Confirm to the user: the folder used, the files created, and that init succeeded.

<!-- SETUP:END -->

## Commands

In all commands below, `<DIR>` is this skill's own folder (where this `SKILL.md` lives).

**Choosing the interpreter.** Use whatever Python 3 launcher works on this machine:
- macOS/Linux: `python3` (fall back to `python`).
- Windows: prefer `py -3`. A bare `python`/`python3` is often a non-functional Microsoft
  Store alias that prints "Python was not found" — if you see that, switch to `py -3`.

Pick a working launcher once, then use it for every `bucket.py` call below (shown as
`python` for brevity).

### `/create-bucket --key <key>`

1. Run: `python <DIR>/bucket.py create --key <key>`
2. Expect `bucket ready: <key>`. This is idempotent: it creates the bucket if new, and
   records `<key>` in `<DIR>/.active_bucket` as the most-recent/default bucket.
3. **This command ARMS capture for the current conversation.** From now until this
   conversation ends, follow the capture contract below. Tell the user capture is on for
   this session and which bucket prompts will land in.
4. To capture into an existing bucket in a *new* session later, just run this command again
   with the same `--key` — it re-arms capture and won't duplicate the bucket.

### `/load-bucket --key <key>`

1. Run: `python <DIR>/bucket.py load --key <key>`
2. **stdout** is the replay block — every captured prompt for that bucket, in order. Read it
   as preloaded intent context for the rest of the session.
3. If **stderr** shows `# resolved 'x' -> 'y'`, the key was fuzzy-matched; tell the user
   which bucket you actually loaded.
4. If the command exits non-zero with `NO_MATCH`, show the user the available keys (the
   stderr line lists them, or run `python <DIR>/bucket.py keys`) and ask which they meant.

## Capture behavior (read this every turn)

This is the core of the skill. Capture is driven by you, the model — there is no background
hook — so the rules below are mandatory, not optional.

**WHEN CAPTURE IS ARMED.** Capture is armed for a conversation only if the user ran
`/create-bucket --key <key>` *earlier in this same conversation*. The `.active_bucket` file
merely records the most-recent key; it is **not** by itself permission to capture. Do NOT
auto-log in a conversation where the user never ran `/create-bucket` here — otherwise a
stale pointer from a previous session would silently capture unrelated prompts. (If the user
wants to resume an old bucket, they re-run `/create-bucket --key <key>`, which re-arms.)

**FIRST-ACTION CONTRACT.** While capture is armed, the **FIRST** action of **EVERY** one of
your responses — before reading files, before answering, before any other tool call — MUST
be to log the user's current verbatim message to the active bucket. Never skip a turn. Never
batch. It is idempotent, so logging is always safe.

**How to log (quote-safe).** Do not pass the prompt as a shell argument (quotes, newlines,
and backticks will corrupt it). Instead:

1. Read the active key from `<DIR>/.active_bucket`.
2. Write the user's message **verbatim** to a temporary file using your file-write tool
   (e.g. a scratch path like `<tmp>/prompt.txt`).
3. Run: `python <DIR>/bucket.py log --key <active-key> --file <tmp>/prompt.txt`
4. Expect `logged` (new) or `duplicate-skip` (already captured). Either is success.

Then proceed with the user's actual request as normal.

**Stopping capture.** Capture ends automatically when the conversation ends (arming does not
carry into the next session). To stop mid-conversation, the user says so — stop logging and
optionally clear `<DIR>/.active_bucket`. Running `/create-bucket` with a different key
redirects capture to that key for the rest of the conversation.

### Few-shot — what a captured turn looks like

> **User:** Let's add retry-with-backoff to the eval runner.
>
> **You (first, silently):**
> - read `.active_bucket` → `agent-behavior`
> - write "Let's add retry-with-backoff to the eval runner." to `<tmp>/prompt.txt`
> - run `python <DIR>/bucket.py log --key agent-behavior --file <tmp>/prompt.txt` → `logged`
> - *then* help with the retry logic as usual.

> **User:** Actually make the backoff jittered, not fixed.
>
> **You (first, silently):** log this verbatim message to `agent-behavior` exactly as above
> (→ `logged`), then implement jittered backoff.

> **User (new session, days later):** `/load-bucket --key agent-behaviour`
>
> **You:** run `python <DIR>/bucket.py load --key agent-behaviour`. stderr says
> `# resolved 'agent-behaviour' -> 'agent-behavior'`; stdout returns both prompts above.
> Tell the user you loaded `agent-behavior` and now have the intent behind that work.

## Notes

- All state — `buckets.db`, `keys.md`, `.active_bucket` — lives in this skill's folder, so
  buckets persist across sessions and projects and the folder can be moved anywhere.
- `keys.md` mirrors the known keys for quick eyeballing; `buckets.db` is the source of truth.
- Prompts are stored verbatim, including any secrets/paths they contain. Treat `buckets.db`
  as sensitive.
