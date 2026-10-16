"""FILE: tests/features/harness_threads/fake_harness_helpers.py

PURPOSE: The vendor paths that the thread helpers and the skill functions reach, kept beside fake_harness.py so each file stays under 1,000 lines: grok `--output-format=streaming-json` runs with `--session-id`, `grok export` and `grok sessions delete` over the real Grok store layout; opencode `session list`, `db`, `export`, `session delete` and `run --command` over a SQLite file with opencode's `session` columns; muse serve `session/list` and `session/read` with items, `muse export --out` and `muse init`.
ROLE IN CODEBASE: Imported only by fake_harness.py, which hands itself in as `base` (its log, output, hold and flood helpers), so nothing is imported twice and no test imports this file. The tests seed vendor state with the same layouts (conftest.py store builders), so a helper reads exactly what a run wrote.
ARCHITECTURE NOTE: Each layout copies the vendor fact the spec records (spec §13): Grok keeps `<GROK_HOME>/sessions/<url-encoded cwd>/<id>/summary.json` beside `sessions/session_search.sqlite` and `<group>/.cwd`; opencode 1.18.31 lists roots only, with rows exactly {id, title, updated, created, projectId, directory}, stops at `--max-count` (default 100), answers `db --format=json <sql>` from its `session` table, records no parent on a fork and refuses an unknown `--command` with an error event; Muse lists at most 200 sessions newest first and carries `forkedFrom` as an object. Where a vendor's own order is unspecified the stand-in picks the order that differs from INV-7 (Muse ties ascending), so a helper that trusts the vendor's order fails.
FUNCTION INVENTORY: grok_find, grok_record, run_grok_stream, run_grok_store_command; opencode_store, opencode_project, opencode_record, opencode_command_refusal, run_opencode_helper; muse_meta_path, muse_load, muse_after_exec, muse_after_fork, muse_read, muse_list, run_muse_export, run_muse_init; helper_modes plays hold, flood and fail for any helper child; utc_now and epoch_ms give the vendor clocks.
COMMON MODIFICATION PATTERNS: Add a scenario field, read it here with .get and a default, and log anything a test must assert on. A vendor fact that changes is changed here and in the conftest.py builder that seeds the same layout.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte or anything outside the standard library. 2. Do not contact the network or run a real vendor CLI. 3. Do not log a credential value. 4. Do not make a stand-in lenient where the spec says the reader must be strict: Muse `forkedFrom` is an object, opencode list rows carry no parent.
KNOWN EDGE CASES: Grok's evidence paths use Windows backslashes on purpose, so a reader that does not fold backslash runs to `/` (spec §9.2) finds no evidence. `update_goal` appears only when GROK_WORKFLOWS is "0", as the in-turn goal driver does. `muse export --session` prefers an existing path in its working folder over a session id (EC-40); a seeded `<state>/muse/<id>.export` (or `<state>/opencode/<id>.export`) is exported byte for byte.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §9.1, §9.2, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import urllib.parse
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GROK_STREAMING = "streaming-json"
GROK_SESSIONS = "sessions"
GROK_SUMMARY = "summary.json"
GROK_TRANSCRIPT = "transcript.md"
GROK_INDEX = "session_search.sqlite"
GROK_CWD = ".cwd"
GROK_MODEL = "grok-build-fast-1"
GROK_AGENTS = ("plan", "explore", "general")
GROK_BUNDLED = "C:\\Users\\dev\\.grok\\bundled\\skills\\"
GROK_PERSONAS = {
    "implement": "shared\\personas\\implementer.md", "execute-plan": "shared\\personas\\implementer.md",
    "design": "shared\\personas\\design-doc-writer.md", "review": "shared\\personas\\reviewer.md",
    "resume-claude": "shared\\resume-session\\CORE.md", "resume-codex": "shared\\resume-session\\CORE.md", "resume-cursor": "shared\\resume-session\\CORE.md",
}
GROK_TOOLS = {"goal": "update_goal", "imagine": "image_gen", "imagine-video": "image_to_video"}
GROK_CODE_REVIEW_TEXT = "Code review skill: run a deep code quality audit of the current branch's changes, then report findings.\n\n"
GROK_SESSION_NOT_FOUND = "Session '{thread_id}' not found."
GROK_NOT_STARTED = "Couldn't start session: the session store is locked by another grok process"
OPENCODE_COMMANDS = ("init", "review")
OPENCODE_AGENTS = ("build", "plan", "general")
OPENCODE_DEFAULT_MAX = 100
OPENCODE_PROJECT = "global"
OPENCODE_DB = "opencode.db"
OPENCODE_SCHEMA = "CREATE TABLE IF NOT EXISTS session (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, parent_id TEXT, directory TEXT NOT NULL, title TEXT NOT NULL, version TEXT NOT NULL DEFAULT '1.18.31', time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL)"
MUSE_MODEL = "muse-coder-1"
MUSE_META = "muse-meta"
MUSE_SKILL_PATTERN = re.compile(r"Use the `([^`]+)` skill")
MUSE_LIST_MAX = 200
MUSE_LIST_DEFAULT = 50
MUSE_CONFIG = (".muse", "config.toml")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def epoch_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def helper_modes(base: Any, scenario: dict[str, Any], log: Any, field: str = "mode") -> None:
    # hold, flood and fail for one helper child (export, list, db,
    # delete, init); `field` names the scenario key that drives it.
    mode = scenario.get(field, "ok")
    if scenario.get("grandchild"):
        base.start_grandchild(log)
    base.early_stderr(scenario)
    if mode == "hold":
        log.write("held", outcome=base.hold(scenario))
    if mode == "flood":
        base.flood(scenario["flood_bytes"])
        sys.exit(0)
    if mode == "fail":
        base.write_err(scenario["vendor_text"] + "\n")
        sys.exit(scenario.get("exit_code", base.DEFAULT_FAIL_EXIT))


# ---- Grok -----------------------------------------------------------------


def grok_find(home: Path, thread_id: str) -> Path | None:
    sessions = home / GROK_SESSIONS
    if not sessions.is_dir():
        return None
    for group in sorted(sessions.iterdir(), key=lambda path: path.name):
        if group.is_dir() and (group / thread_id).is_dir():
            return group / thread_id
    return None


def grok_record(home: Path, cwd: str, session: str, scenario: dict[str, Any], *, line: str, text: str, model: str | None, parent: str | None, agent: str | None, expansion: str = "") -> None:
    # Grok's real store: sessions/<url-encoded cwd>/<id>/summary.json,
    # with the search index and the group's .cwd beside it (EC-66).
    sessions = home / GROK_SESSIONS
    group = sessions / urllib.parse.quote(cwd, safe="")
    folder = group / session
    folder.mkdir(parents=True, exist_ok=True)
    if not (sessions / GROK_INDEX).exists():
        (sessions / GROK_INDEX).write_bytes(b"SQLite format 3\x00")
    (group / GROK_CWD).write_text(cwd, encoding="utf-8")
    summary_path = folder / GROK_SUMMARY
    previous = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    now = utc_now()
    summary: dict[str, Any] = {
        "created_at": previous.get("created_at", now), "updated_at": now, "generated_title": previous.get("generated_title") or line[:60].strip() or None,
        "session_summary": f"Session about: {line[:200]}", "last_turn_summary": text[:200], "parent_session_id": previous.get("parent_session_id", parent),
        "current_model_id": model or GROK_MODEL,
    }
    if agent:
        summary["agent_name"] = agent
    for key, value in scenario.get("summary_fields", {}).items():
        if value is None:
            summary.pop(key, None)
        else:
            summary[key] = value
    transcript = folder / GROK_TRANSCRIPT
    with transcript.open("a", encoding="utf-8", newline="") as handle:
        if handle.tell() == 0:
            handle.write(f"# Grok session {session}\n\n")
        handle.write(f"## User\n\n{line}\n\n## Assistant\n\n{expansion}{text}\n\n")
    if scenario.get("summary_mode") != "absent":
        summary_path.write_text(json.dumps(summary), encoding="utf-8")


def grok_tools(scenario: dict[str, Any], line: str, env: dict[str, str], cwd: str) -> list[dict[str, Any]]:
    # What the bundled skill would call: the A-9 evidence for the slash
    # command, after one ordinary call; `tools` replaces the list and
    # `expand: false` plays a Grok that did not expand the command.
    if "tools" in scenario:
        return [{"toolName": name, "rawInput": raw} for name, raw in scenario["tools"]]
    calls: list[dict[str, Any]] = [{"toolName": "list_dir", "rawInput": {"path": cwd}}]
    if not line.startswith("/") or not scenario.get("expand", True):
        return calls
    command, _, rest = line[1:].partition(" ")
    if command in GROK_PERSONAS:
        calls.append({"toolName": "read_file", "rawInput": {"path": GROK_BUNDLED + GROK_PERSONAS[command]}})
    elif command == "goal" and env.get("GROK_WORKFLOWS") == "0":
        calls.append({"toolName": "update_goal", "rawInput": {"objective": rest}})
    elif command in ("imagine", "imagine-video"):
        calls.append({"toolName": GROK_TOOLS[command], "rawInput": {"prompt": rest}})
    return calls


def run_grok_stream(base: Any, scenario: dict[str, Any], options: dict[str, str], env: dict[str, str], log: Any, home: Path) -> None:
    # One `--output-format=streaming-json` run: text, tool_call and
    # tool_call_update events, then end {sessionId}.
    mode = scenario.get("mode", "ok")
    line = options["--single"]
    requested = options.get("--session-id")
    if requested is not None:
        try:
            valid = str(uuid.UUID(requested)) == requested.lower()
        except ValueError:
            valid = False
        if not valid or grok_find(home, requested) is not None:
            base.write_err(f"error: --session-id {requested!r} must be a new session UUID\n")
            sys.exit(2)
    agent = options.get("--agent")
    session = requested or str(uuid.uuid4())
    if agent is not None and agent not in GROK_AGENTS:
        base.write_out(json.dumps({"type": "error", "message": f"Unknown agent: {agent}"}) + "\n")
        sys.exit(1)
    if mode == "key_rejected" or "XAI_API_KEY" not in env:
        base.write_out(json.dumps({"type": "error", "message": base.GROK_NOT_SIGNED_IN}) + "\n")
        sys.exit(1)
    if mode == "not_started":
        base.write_out(json.dumps({"type": "error", "message": GROK_NOT_STARTED}) + "\n")
        sys.exit(1)
    if mode == "echo_secrets":
        base.write_out(json.dumps({"type": "error", "message": base.echo_text(scenario, list(options.values()), "", env)}) + "\n")
        sys.exit(1)
    log.write("session", session=session)
    cwd = options.get("--cwd", os.getcwd())
    calls = grok_tools(scenario, line, env, cwd)
    base.write_out(json.dumps({"type": "text", "data": "Working on it. "}) + "\n")
    if mode == "hold":
        log.write("held", outcome=base.hold(scenario))
    for index, call in enumerate(calls):
        base.write_out(json.dumps({"type": "tool_call", "toolCallId": f"call_{index:03d}", **call}) + "\n")
        base.write_out(json.dumps({"type": "tool_call_update", "toolCallId": f"call_{index:03d}", "status": "completed"}) + "\n")
    if mode == "flood":
        base.flood(scenario["flood_bytes"])
        sys.exit(0)
    if scenario.get("padding_bytes"):
        base.write_out(json.dumps({"type": "tool_call_update", "toolCallId": "call_pad", "status": "completed", "output": "p" * scenario["padding_bytes"]}) + "\n")
    if mode == "fail":
        base.write_out(json.dumps({"type": "error", "message": scenario["vendor_text"]}) + "\n")
        sys.exit(scenario.get("exit_code", base.DEFAULT_FAIL_EXIT))
    parts = scenario.get("final_parts", ["grok answer to: ", line])
    for part in parts:
        base.write_out(json.dumps({"type": "text", "data": part}) + "\n")
    command = line[1:].partition(" ")[0] if line.startswith("/") else ""
    expansion = GROK_CODE_REVIEW_TEXT if command == "code-review" and scenario.get("expand", True) else ""
    grok_record(home, cwd, session, scenario, line=line, text="".join(parts), model=options.get("--model"), parent=None, agent=agent, expansion=expansion)
    end: dict[str, Any] = {"type": "end", "sessionId": session, "stopReason": "end_turn"}
    if scenario.get("end_session") == "other":
        end["sessionId"] = str(uuid.uuid4())
    if scenario.get("end_session") == "missing":
        end.pop("sessionId")
    if scenario.get("end_session") != "none":
        base.write_out(json.dumps(end) + "\n")
    log.write("answer", session=session, line=line, agent=agent, tools=[call["toolName"] for call in calls], workflows=env.get("GROK_WORKFLOWS"))
    sys.exit(0)


def run_grok_store_command(base: Any, scenario: dict[str, Any], args: list[str]) -> None:
    # `grok export <id>` (Markdown on stdout) and `grok sessions delete
    # <id>`, both over GROK_HOME.
    env = dict(os.environ)
    role = "grok-export" if args[:1] == ["export"] else "grok-delete"
    log = base.FakeLog(scenario["log_dir"], role)
    base.start_record(log, role, args, env, via_wsl=False, skills_folder=None)
    expected = 2 if role == "grok-export" else 3
    home = env.get("GROK_HOME")
    if len(args) != expected or home is None:
        base.write_err(f"fake grok: unexpected {role} arguments {args!r} or no GROK_HOME\n")
        sys.exit(2)
    thread_id = args[-1]
    field = "export_mode" if role == "grok-export" else "delete_mode"
    helper_modes(base, scenario, log, field)
    folder = grok_find(Path(home), thread_id)
    if folder is None or scenario.get(field) == "not_found":
        base.write_err(GROK_SESSION_NOT_FOUND.format(thread_id=thread_id) + "\n")
        sys.exit(1)
    if role == "grok-export":
        transcript = folder / GROK_TRANSCRIPT
        data = transcript.read_bytes() if transcript.is_file() else f"# Grok session {thread_id}\n".encode("utf-8")
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        log.write("exported", session=thread_id, bytes=len(data))
        sys.exit(0)
    if scenario.get("delete_mode") != "leave":
        shutil.rmtree(folder)
    log.write("deleted", session=thread_id, left=folder.exists())
    base.write_out(f"Deleted session {thread_id}\n")
    sys.exit(0)


# ---- opencode -------------------------------------------------------------


def opencode_store(scenario: dict[str, Any]) -> sqlite3.Connection:
    folder = Path(scenario["state_dir"]) / "opencode"
    folder.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(folder / OPENCODE_DB)
    connection.execute(OPENCODE_SCHEMA)
    return connection


def opencode_project(scenario: dict[str, Any], directory: str) -> str:
    # opencode keys sessions by project; a folder outside any mapped
    # project is the "global" project (EC-28).
    for folder, project in scenario.get("projects", {}).items():
        if os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(directory)):
            return project
    return OPENCODE_PROJECT


def opencode_record(scenario: dict[str, Any], session: str, directory: str, title: str, *, new: bool) -> None:
    # Session.fork and run both create a root: no parent_id (EC-76).
    now = epoch_ms()
    with closing(opencode_store(scenario)) as connection:
        if new:
            connection.execute(
                "INSERT OR REPLACE INTO session (id, project_id, parent_id, directory, title, time_created, time_updated) VALUES (?, ?, NULL, ?, ?, ?, ?)",
                (session, opencode_project(scenario, directory), directory, title[:80] or "New session", now, now),
            )
        else:
            connection.execute("UPDATE session SET time_updated = ? WHERE id = ?", (now, session))
        connection.commit()


def opencode_command_refusal(base: Any, scenario: dict[str, Any], session: str, options: dict[str, str]) -> None:
    # 1.18.31: an unknown --command is an error event `Command not
    # found: "<name>". Available commands: ...`, then exit 1; an unknown
    # --agent is refused the same way.
    command = options.get("--command")
    commands = scenario.get("commands", list(OPENCODE_COMMANDS))
    if command is not None and command not in commands:
        text = f'Command not found: "{command}". Available commands: {", ".join(commands)}'
        if scenario.get("not_found_channel") == "stderr":
            base.write_err(text + "\n")
        else:
            base.write_out(base.opencode_error(session, "UnknownError", text, None))
        sys.exit(1)
    agent = options.get("--agent")
    if agent is not None and agent not in OPENCODE_AGENTS:
        base.write_out(base.opencode_error(session, "UnknownError", f'Agent not found: "{agent}". Available agents: {", ".join(OPENCODE_AGENTS)}', None))
        sys.exit(1)


def run_opencode_helper(base: Any, scenario: dict[str, Any], args: list[str]) -> None:
    # `session list`, `db`, `export` and `session delete`.
    env = dict(os.environ)
    words = 2 if args[0] == "session" else 1
    verb = args[words - 1]
    role = f"opencode-{verb}"
    log = base.FakeLog(scenario["log_dir"], role)
    options, _, stray = base.parse_joined(args[words:], ())
    base.start_record(log, role, args, env, via_wsl=False, skills_folder=None, extra={"options": options, "stray": stray})
    helper_modes(base, scenario, log)
    if verb == "list":
        opencode_list(base, scenario, options, stray, env, log)
    if verb == "db":
        opencode_db(base, scenario, options, stray, log)
    if len(stray) != 1 or options:
        base.write_err(f"fake opencode: {verb} takes exactly one session id, got {args!r}\n")
        sys.exit(2)
    thread_id = stray[0]
    with closing(opencode_store(scenario)) as connection:
        found = connection.execute("SELECT id, title, time_created, time_updated, directory FROM session WHERE id = ?", (thread_id,)).fetchone()
        if found is None:
            base.write_err(f"Session not found: {thread_id}\n")
            sys.exit(1)
        if verb == "delete":
            connection.execute("DELETE FROM session WHERE id = ?", (thread_id,))
            connection.commit()
    state = Path(scenario["state_dir"]) / "opencode"
    if verb == "delete":
        (state / thread_id).unlink(missing_ok=True)
        log.write("deleted", session=thread_id)
        base.write_out(f"Session {thread_id} deleted\n")
        sys.exit(0)
    seeded = state / f"{thread_id}.export"
    if seeded.is_file():
        data = seeded.read_bytes()
    else:
        prompt = (state / thread_id).read_text(encoding="utf-8") if (state / thread_id).is_file() else ""
        info = {"id": found[0], "title": found[1], "time": {"created": found[2], "updated": found[3]}, "directory": found[4]}
        data = json.dumps({"info": info, "messages": [{"info": {"role": "user"}, "parts": [{"type": "text", "text": prompt}]}]}, indent=2).encode("utf-8")
    base.write_err(f"Exporting session: {thread_id}\n")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    sys.exit(0)


def opencode_list(base: Any, scenario: dict[str, Any], options: dict[str, str], stray: list[str], env: dict[str, str], log: Any) -> None:
    # Roots only, in the project of PWD (else cwd), newest first, cut at
    # --max-count (default 100); rows carry no parent.
    if stray or options.get("--format") != "json" or set(options) - {"--format", "--max-count"}:
        base.write_err(f"fake opencode: session list takes --format=json and --max-count=<n>, got {options!r} {stray!r}\n")
        sys.exit(2)
    max_count = int(options.get("--max-count", OPENCODE_DEFAULT_MAX))
    project = opencode_project(scenario, env.get("PWD") or os.getcwd())
    log.write("listing", project=project, max_count=max_count)
    if "list_text" in scenario:
        base.write_out(scenario["list_text"])
        sys.exit(0)
    with closing(opencode_store(scenario)) as connection:
        rows = connection.execute(
            "SELECT id, title, time_updated, time_created, project_id, directory FROM session WHERE project_id = ? AND parent_id IS NULL ORDER BY time_updated DESC LIMIT ?",
            (project, max_count),
        ).fetchall()
    if not rows:
        base.write_out("" if scenario.get("empty_list", "blank") == "blank" else "[]\n")
        sys.exit(0)
    keys = ("id", "title", "updated", "created", "projectId", "directory")
    base.write_out(json.dumps([dict(zip(keys, row)) for row in rows], indent=2) + "\n")
    sys.exit(0)


def opencode_db(base: Any, scenario: dict[str, Any], options: dict[str, str], stray: list[str], log: Any) -> None:
    # `opencode db --format=json "<sql>"`: the query's rows as a JSON
    # array of objects ([] when none).
    if len(stray) != 1 or options != {"--format": "json"}:
        base.write_err(f"fake opencode: db takes one query and --format=json, got {options!r} {stray!r}\n")
        sys.exit(2)
    log.write("query", query=stray[0])
    if "db_text" in scenario:
        base.write_out(scenario["db_text"])
        sys.exit(0)
    with closing(opencode_store(scenario)) as connection:
        cursor = connection.execute(stray[0])
        names = [column[0] for column in cursor.description or ()]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    base.write_out(json.dumps(rows) + "\n")
    sys.exit(0)


# ---- Muse -----------------------------------------------------------------


def muse_meta_path(scenario: dict[str, Any], session: str) -> Path:
    return Path(scenario["state_dir"]) / MUSE_META / f"{session}.json"


def muse_load(scenario: dict[str, Any], session: str) -> dict[str, Any] | None:
    path = muse_meta_path(scenario, session)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def muse_save(scenario: dict[str, Any], session: str, meta: dict[str, Any]) -> None:
    path = muse_meta_path(scenario, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta), encoding="utf-8")


def muse_item(index: int, kind: str, **fields: Any) -> dict[str, Any]:
    return {"itemId": f"item-{index:04d}", "kind": kind, "revision": 1, "status": "completed", **fields}


def muse_items(scenario: dict[str, Any], prompt: str, text: str, start: int) -> list[dict[str, Any]]:
    # The items a turn folds into: the prompt, a `read_skill` call when
    # the prompt names a skill (unless `expand` is false), one ordinary
    # call, the answer. `exec_items` [[tool, args], ...] replaces the
    # calls.
    items = [muse_item(start, "userMessage", text=prompt)]
    if "exec_items" in scenario:
        calls = [(tool, args) for tool, args in scenario["exec_items"]]
    else:
        calls = [("list_dir", json.dumps({"path": "."}))]
        named = MUSE_SKILL_PATTERN.search(prompt)
        if named is not None and scenario.get("expand", True):
            calls.insert(0, ("read_skill", json.dumps({"id": named.group(1)})))
    for offset, (tool, args) in enumerate(calls, start=1):
        items.append(muse_item(start + offset, "toolCall", tool=tool, args=args))
    items.append(muse_item(start + len(calls) + 1, "agentMessage", text=text))
    return items


def muse_after_exec(scenario: dict[str, Any], options: dict[str, str], session: str, prompt: str, text: str) -> None:
    meta = muse_load(scenario, session)
    now = utc_now()
    if meta is None:
        meta = {"session": {
            "activeTurnId": None, "createdAt": now, "forkedFrom": None, "modelId": options.get("--model") or MUSE_MODEL, "path": f"/home/dev/.muse/sessions/{session}.jsonl",
            "providerId": "meta", "sessionId": session, "status": "notLoaded", "turnCount": 0, "updatedAt": now, "workspaceRoot": options.get("--workspace", ""),
        }, "items": []}
    meta["session"]["updatedAt"] = now
    meta["session"]["turnCount"] += 1
    meta["items"] += muse_items(scenario, prompt, text, len(meta["items"]) + 1)
    muse_save(scenario, session, meta)


def muse_after_fork(scenario: dict[str, Any], source: str, forked: str, command_id: str) -> None:
    # MSP ForkProvenance: forkedFrom is an object carrying sessionId.
    meta = muse_load(scenario, source)
    if meta is None:
        return
    now = utc_now()
    session = {**meta["session"], "sessionId": forked, "createdAt": now, "updatedAt": now, "path": f"/home/dev/.muse/sessions/{forked}.jsonl"}
    session["forkedFrom"] = {"commandId": command_id, "cutCursor": "cut-0001", "cutExplicit": False, "sessionId": source}
    muse_save(scenario, forked, {"session": session, "items": list(meta["items"])})


def muse_read(scenario: dict[str, Any], session: str, exclude: bool) -> dict[str, Any]:
    # session/read: the whole MSP Session, and the history in the mode
    # the scenario chooses (inline, snapshot, anchoredSnapshot, none).
    meta = muse_load(scenario, session)
    if meta is None:
        return {"session": {"sessionId": session, "status": "notLoaded"}}
    found = {**meta["session"], **scenario.get("session_fields", {})}
    mode = "none" if exclude else scenario.get("history_mode", "inline")
    items = meta["items"]
    history: dict[str, Any] = {"mode": mode, "items": None, "snapshot": None}
    if mode == "inline":
        history["items"] = items
    if mode == "snapshot":
        history["snapshot"] = {"schemaVersion": 1, "state": {"items": items}, "viewCursor": "view-0001"}
    if mode == "anchoredSnapshot":
        kept = [muse_item(1, "compaction", summary="Earlier turns were compacted.")] + [item for item in items if item.get("kind") != "toolCall" or item.get("tool") == "list_dir"]
        history["snapshot"] = {"anchor": {"boundaryCursor": "view-0000", "summarizedThrough": "anchor-0001"}, "schemaVersion": 1, "state": {"items": kept}, "viewCursor": "view-0001"}
    if mode == "none":
        history["noneReason"] = "excluded" if exclude else scenario.get("none_reason", "historyBudget")
    return {"history": history, "pendingRequests": [], "session": found, "viewCursor": "view-0001"}


def muse_list(scenario: dict[str, Any], params: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:
    # session/list: workspaceRoot and updatedAfter filters, at most 200,
    # newest first; ties come back in ascending sessionId order, which
    # is not INV-7's order.
    if scenario.get("serve_mode") == "no_list":
        reply["error"] = {"code": -32601, "message": "method session/list not found", "data": {"kind": "methodNotFound"}}
        return reply
    limit = params.get("limit", MUSE_LIST_DEFAULT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MUSE_LIST_MAX:
        reply["error"] = {"code": -32602, "message": "limit must be 1..200", "data": {"kind": "invalidParams"}}
        return reply
    if "list_result" in scenario:
        reply["result"] = scenario["list_result"]
        return reply
    root = params.get("workspaceRoot")
    after = params.get("updatedAfter")
    folder = Path(scenario["state_dir"]) / MUSE_META
    metas = [json.loads(path.read_text(encoding="utf-8"))["session"] for path in sorted(folder.glob("*.json"))] if folder.is_dir() else []
    if isinstance(root, str):
        metas = [meta for meta in metas if os.path.normcase(meta.get("workspaceRoot", "")) == os.path.normcase(root)]
    if isinstance(after, str):
        cutoff = datetime.fromisoformat(after.replace("Z", "+00:00"))
        metas = [meta for meta in metas if datetime.fromisoformat(meta["updatedAt"].replace("Z", "+00:00")) > cutoff]
    metas.sort(key=lambda meta: meta["sessionId"])
    metas.sort(key=lambda meta: datetime.fromisoformat(meta["updatedAt"].replace("Z", "+00:00")), reverse=True)
    reply["result"] = {"sessions": metas[:limit], "nextCursor": "page-0002" if len(metas) > limit else None}
    return reply


def muse_options(args: list[str], valued: tuple[str, ...], switches: tuple[str, ...]) -> tuple[dict[str, str], list[str], str | None]:
    options: dict[str, str] = {}
    present: list[str] = []
    index = 0
    while index < len(args):
        element = args[index]
        flag, joined, value = element.partition("=")
        if flag in valued and joined:
            options[flag] = value
        elif element in valued and index + 1 < len(args):
            options[element] = args[index + 1]
            index += 1
        elif element in switches:
            present.append(element)
        else:
            return options, present, f"error: unexpected argument {element!r}"
        index += 1
    return options, present, None


def run_muse_export(base: Any, scenario: dict[str, Any], args: list[str], env: dict[str, str], via_wsl: bool, launcher_args: list[str]) -> None:
    # `muse export --session <id|path> --out <file>`: an existing path
    # in the working folder wins over an id (EC-40); without --out it
    # writes into the working folder.
    options, _, problem = muse_options(args[1:], ("--session", "--out"), ())
    log = base.FakeLog(scenario["log_dir"], "muse-export")
    base.start_record(log, "muse-export", args, env, via_wsl=via_wsl, skills_folder=None, extra={"options": options, "launcher_args": launcher_args, "cwd_entries": sorted(os.listdir(os.getcwd()))})
    if via_wsl:
        base.register_mark(scenario, env)
    helper_modes(base, scenario, log, "export_mode")
    value = options.get("--session")
    if problem is not None or value is None:
        base.write_err((problem or "error: --session is required") + "\n")
        sys.exit(2)
    decoy = Path(os.getcwd()) / value
    meta = muse_load(scenario, value)
    seeded = Path(scenario["state_dir"]) / "muse" / f"{value}.export"
    if decoy.exists():
        data = decoy.read_bytes()
    elif meta is not None and seeded.is_file():
        data = seeded.read_bytes()
    elif meta is not None:
        dropped = set(scenario.get("export_drop_tools", []))
        items = [item for item in meta["items"] if item.get("tool") not in dropped]
        data = json.dumps({"session": meta["session"], "items": items}, indent=2).encode("utf-8")
    else:
        base.write_err(f"Error: session {value} not found\n")
        sys.exit(1)
    out = base.host_path(options.get("--out"), via_wsl) if "--out" in options else Path(os.getcwd()) / f"{value}.json"
    if out is None:
        base.write_err("error: --out is not a path this process can write\n")
        sys.exit(2)
    if scenario.get("export_mode") != "no_file":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        if scenario.get("export_mode") == "oversize":
            with out.open("r+b") as handle:
                handle.truncate(scenario["oversize_bytes"])
    log.write("exported", session=value, out=str(out), decoy=decoy.exists())
    base.write_out(f"Exported session {value} to {options.get('--out', out)}\n")
    sys.exit(0)


def run_muse_init(base: Any, scenario: dict[str, Any], args: list[str], env: dict[str, str], via_wsl: bool, launcher_args: list[str]) -> None:
    # `muse init [--dry-run]` in the working folder; it refuses when the
    # Muse config already exists (no --force here).
    _, switches, problem = muse_options(args[1:], (), ("--dry-run",))
    log = base.FakeLog(scenario["log_dir"], "muse-init")
    base.start_record(log, "muse-init", args, env, via_wsl=via_wsl, skills_folder=None, extra={"switches": switches, "launcher_args": launcher_args})
    if via_wsl:
        base.register_mark(scenario, env)
    helper_modes(base, scenario, log)
    if problem is not None:
        base.write_err(problem + "\n")
        sys.exit(2)
    target = Path(os.getcwd()).joinpath(*MUSE_CONFIG)
    if target.exists():
        base.write_err(f"Error: Muse is already initialized here ({target.parent.name}/{target.name} exists); pass --force to overwrite it\n")
        sys.exit(1)
    plan = f"{MUSE_CONFIG[0]}/{MUSE_CONFIG[1]}\n{MUSE_CONFIG[0]}/skills/\n"
    if "--dry-run" in switches:
        base.write_out("Would create:\n" + plan)
        sys.exit(0)
    (target.parent / "skills").mkdir(parents=True, exist_ok=True)
    target.write_text("[workspace]\nprovider = \"meta\"\n", encoding="utf-8")
    base.write_out("Created:\n" + plan)
    sys.exit(0)
