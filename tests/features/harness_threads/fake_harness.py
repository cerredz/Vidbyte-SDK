"""FILE: tests/features/harness_threads/fake_harness.py

PURPOSE: A standard-library stand-in for the three vendor CLIs the harness thread functions drive (`grok --single`, `opencode run --format json`, `muse exec --json` and batch `muse serve`) and for `wsl.exe`, scripted by a JSON scenario file and logging what each process received.
ROLE IN CODEBASE: Run as a real child process by the harness_threads tests and never imported. The tests hand it to the SDK through GrokThreadConfig.grok_command, OpencodeThreadConfig.opencode_command and MuseThreadConfig.muse_command (spec §13 "Real seams"), or put an `.exe`/script stand-in that runs it first on PATH.
ARCHITECTURE NOTE: argv[1] is the scenario path; everything after it is what the SDK appended. A stand-in built for `wsl.exe` inserts `--as-wsl` first, and the muse role then sees only the variables that WSLENV names, as the real wsl.exe forwards. Each process logs to its own JSONL file named after its launch number, so logs read back in launch order and never interleave. Credentials are logged as a SHA-256 digest and a length, never as values. Threads persist as files (Grok under GROK_HOME keyed by --cwd, as Grok does; opencode and Muse under the scenario's state folder), so continue and fork behave like the vendors.
FUNCTION INVENTORY: main dispatches on the scenario's program; run_grok, run_opencode, run_muse_exec, run_muse_serve and run_wsl play one program each; FakeLog writes the per-process log; start_record captures argv, cwd, stdin kind, credential digests, plain variables and skill folders; hold waits for the release file or the hold limit; flood writes past an output cap; echo_text builds the AC-4 secret echo.
COMMON MODIFICATION PATTERNS: Add a scenario field, read it here with .get and a default, and log anything a test must assert on.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte or anything outside the standard library. 2. Do not contact the network or run a real vendor CLI or the real wsl.exe. 3. Do not log a credential value; only echo_secrets mode prints one, on purpose, into the vendor's own error output. 4. Never use shell=True.
KNOWN EDGE CASES: A held process exits by itself after HOLD_LIMIT_SECONDS, so a broken stop cannot leak it for long; its grandchild sleeps GRANDCHILD_SECONDS. opencode reads stdin as bytes and decodes UTF-8 (the Windows console code page is not UTF-8). `muse exec --session-id <unknown>` silently starts a new thread, as Muse 1.0.1 does (spec §15, probe 9).
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §9.2, §13, §15
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HOLD_LIMIT_SECONDS = 30.0
GRANDCHILD_SECONDS = 30
POLL_SECONDS = 0.02
CHUNK_BYTES = 1 << 20
DEFAULT_FAIL_EXIT = 93
CREDENTIAL_NAMES = ("XAI_API_KEY", "GROK_CODE_XAI_API_KEY", "META_API_KEY", "DEEPSEEK_API_KEY", "ZAI_API_KEY", "OPENCODE_CONFIG_CONTENT")
PLAIN_NAMES = (
    "GROK_HOME", "GROK_DISABLE_AUTOUPDATER", "OPENCODE_DISABLE_AUTOUPDATE", "MUSE_NO_AUTO_UPDATE",
    "XDG_CONFIG_HOME", "MUSE_AUTH_PATH", "WSLENV", "VIDBYTE_PEER_MARK",
)
GROK_SWITCHES = ("--fork-session",)
OPENCODE_SWITCHES = ("--fork",)
MUSE_VALUED = ("--provider", "--workspace", "--session-id", "--model", "--reasoning-effort")
MUSE_SWITCHES = ("--json", "--user-input-auto-resolve")
SERVE_STATE = {"initialized": False}
UUID7_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
WSL_DISTRO_NOT_FOUND = "There is no distribution with the supplied name.\nError code: Wsl/Service/WSL_E_DISTRO_NOT_FOUND\n"
GROK_NOT_SIGNED_IN = "Not signed in. Run `grok login` or set XAI_API_KEY."
MUSE_KEY_REJECTED = "Error: failed to fetch model catalog: authentication failed: your API key from META_API_KEY was rejected\n"


def digest(value: str) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest(), "length": len(value)}


def claim_launch_number(log_dir: Path) -> int:
    # The lowest free number, claimed with an exclusive create (atomic on Windows and POSIX), so no clock is involved.
    number = 1
    while True:
        try:
            os.close(os.open(log_dir / f"launch-{number:06d}.claim", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return number
        except FileExistsError:
            number += 1


class FakeLog:
    """Appends one JSON record per line to this process's own log file."""

    def __init__(self, log_dir: str, role: str) -> None:
        folder = Path(log_dir)
        self.path = folder / f"{claim_launch_number(folder):06d}-{role}-{os.getpid()}.jsonl"
        self.sequence = 0

    def write(self, kind: str, **fields: Any) -> None:
        self.sequence += 1
        record = {"kind": kind, "pid": os.getpid(), "seq": self.sequence, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def stdin_kind() -> str:
    try:
        mode = os.fstat(0).st_mode
    except OSError:
        return "closed"
    if stat.S_ISFIFO(mode):
        return "pipe"
    if stat.S_ISCHR(mode):
        return "char"
    if stat.S_ISREG(mode):
        return "file"
    return "other"


def read_stdin_text() -> str:
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        return ""
    return stream.read().decode("utf-8", errors="replace")


def visible_environment(via_wsl: bool) -> dict[str, str]:
    # wsl.exe forwards into the distro only the variables WSLENV names.
    if not via_wsl:
        return dict(os.environ)
    names = [entry.split("/", 1)[0] for entry in os.environ.get("WSLENV", "").split(":") if entry]
    return {name: os.environ[name] for name in names if name in os.environ}


def host_path(value: str | None, via_wsl: bool) -> Path | None:
    # Inside WSL a Windows folder is seen as /mnt/<drive>/...; map it back so the fake can look at it.
    if value is None:
        return None
    if via_wsl:
        match = re.fullmatch(r"/mnt/([a-z])(/.*)?", value)
        if match is None:
            return None
        return Path(match.group(1).upper() + ":" + (match.group(2) or "/"))
    return Path(value)


def skill_listing(folder: Path | None) -> dict[str, Any] | None:
    if folder is None or not folder.is_dir():
        return None
    listing: dict[str, Any] = {}
    for child in sorted(folder.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            listing[child.name] = "not-a-folder"
            continue
        files: dict[str, str] = {}
        for path in sorted(child.rglob("*"), key=lambda path: path.as_posix()):
            relative = path.relative_to(child).as_posix()
            if path.is_symlink():
                files[relative] = "symlink"
            elif path.is_file():
                files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        listing[child.name] = files
    return listing


def sanitized_config(raw: str | None) -> Any:
    # OPENCODE_CONFIG_CONTENT with every apiKey replaced by its digest.
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return {"unparsed": digest(raw)}

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: (digest(value) if key == "apiKey" and isinstance(value, str) else walk(value)) for key, value in node.items()}
        if isinstance(node, list):
            return [walk(value) for value in node]
        return node

    return walk(data)


def start_record(log: FakeLog, role: str, args: list[str], env: dict[str, str], *, via_wsl: bool, skills_folder: Path | None, extra: dict[str, Any] | None = None) -> None:
    credentials = {name: (digest(env[name]) if name in env else None) for name in CREDENTIAL_NAMES}
    plain = {name: env.get(name) for name in PLAIN_NAMES}
    auth_path = host_path(env.get("MUSE_AUTH_PATH"), via_wsl)
    log.write(
        "start",
        role=role,
        argv=args,
        cwd=os.getcwd(),
        stdin_kind=stdin_kind(),
        credentials=credentials,
        plain=plain,
        raw_wslenv=os.environ.get("WSLENV"),
        opencode_config=sanitized_config(env.get("OPENCODE_CONFIG_CONTENT")),
        skills=skill_listing(skills_folder),
        muse_auth_file_exists=None if auth_path is None else auth_path.exists(),
        xdg_config_exists=None if host_path(env.get("XDG_CONFIG_HOME"), via_wsl) is None else host_path(env.get("XDG_CONFIG_HOME"), via_wsl).is_dir(),
        via_wsl=via_wsl,
        **(extra or {}),
    )


def hold(scenario: dict[str, Any]) -> str:
    release = scenario.get("release_file")
    deadline = time.monotonic() + HOLD_LIMIT_SECONDS
    while time.monotonic() < deadline:
        if release and os.path.exists(release):
            return "released"
        time.sleep(POLL_SECONDS)
    return "limit"


def start_grandchild(log: FakeLog) -> None:
    # A grandchild that inherits the pipes, so only a whole-tree stop ends it.
    child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({GRANDCHILD_SECONDS})"])
    log.write("grandchild", grandchild_pid=child.pid)


def write_out(text: str) -> None:
    try:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    except (OSError, ValueError):
        os._exit(0)


def write_err(text: str) -> None:
    try:
        sys.stderr.buffer.write(text.encode("utf-8"))
        sys.stderr.buffer.flush()
    except (OSError, ValueError):
        os._exit(0)


def flood(total_bytes: int) -> None:
    chunk = b"z" * CHUNK_BYTES
    written = 0
    try:
        while written < total_bytes:
            piece = chunk[: min(CHUNK_BYTES, total_bytes - written)]
            sys.stdout.buffer.write(piece)
            written += len(piece)
        sys.stdout.buffer.flush()
    except (OSError, ValueError):
        os._exit(0)


def echo_text(scenario: dict[str, Any], args: list[str], stdin_text: str, env: dict[str, str]) -> str:
    # AC-4: everything the child was given, credentials included, as one vendor error text. The first copy of the
    # key sits near the start; a run of back-to-back copies straddles the vendor-text cap, so capping before
    # scrubbing would leave a fragment of the key behind.
    key = scenario["echo_key"]
    cap = scenario.get("echo_cap", 1000)
    head = f"echo key {key} argv {' '.join(args)} stdin {stdin_text} env {' '.join(env.get(name, '') for name in CREDENTIAL_NAMES)} "
    filler = "x" * max(0, cap - 100 - len(head))
    return head + filler + key * 6


def parse_joined(args: list[str], switches: tuple[str, ...]) -> tuple[dict[str, str], list[str], list[str]]:
    options: dict[str, str] = {}
    present: list[str] = []
    stray: list[str] = []
    for element in args:
        if element.startswith("--") and "=" in element:
            flag, value = element.split("=", 1)
            options[flag] = value
        elif element in switches:
            present.append(element)
        else:
            stray.append(element)
    return options, present, stray


def new_id(prefix: str = "") -> str:
    return prefix + str(uuid.uuid4())


def run_grok(scenario: dict[str, Any], args: list[str]) -> None:
    env = dict(os.environ)
    options, switches, stray = parse_joined(args, GROK_SWITCHES)
    home = env.get("GROK_HOME")
    log = FakeLog(scenario["log_dir"], "grok")
    start_record(log, "grok", args, env, via_wsl=False, skills_folder=None if home is None else Path(home) / "skills", extra={"options": options, "switches": switches, "stray": stray})
    mode = scenario.get("mode", "ok")
    if scenario.get("grandchild"):
        start_grandchild(log)
    if stray or "--single" not in options:
        write_err(f"fake grok: unexpected arguments {stray!r}; a --single=<prompt> option is required\n")
        sys.exit(2)
    if home is None:
        write_out(json.dumps({"type": "error", "message": "fake grok: GROK_HOME is not set"}) + "\n")
        sys.exit(4)
    if mode == "hold":
        log.write("held", outcome=hold(scenario))
    if mode == "key_rejected" or "XAI_API_KEY" not in env:
        write_out(json.dumps({"type": "error", "message": GROK_NOT_SIGNED_IN}) + "\n")
        write_err("Error: " + GROK_NOT_SIGNED_IN + "\n")
        sys.exit(1)
    if mode == "flood":
        flood(scenario["flood_bytes"])
        sys.exit(0)
    if mode == "garbage":
        write_out("Grok Build finished, but this line is not JSON\n")
        sys.exit(0)
    if mode == "fail":
        write_out(json.dumps({"type": "error", "message": scenario["vendor_text"]}) + "\n")
        sys.exit(scenario.get("exit_code", DEFAULT_FAIL_EXIT))
    if mode == "stderr_exit":
        write_err(scenario["vendor_text"] + "\n")
        sys.exit(scenario.get("exit_code", DEFAULT_FAIL_EXIT))
    if mode == "echo_secrets":
        write_out(json.dumps({"type": "error", "message": echo_text(scenario, args, "", env)}) + "\n")
        sys.exit(1)
    prompt = options["--single"]
    cwd_value = options.get("--cwd", os.getcwd())
    store = Path(home) / "sessions" / hashlib.sha256(os.path.normcase(os.path.abspath(cwd_value)).encode("utf-8")).hexdigest()[:16]
    resume = options.get("--resume")
    forking = "--fork-session" in switches
    if resume is not None and not (store / f"{resume}.json").is_file():
        write_out(json.dumps({"type": "error", "message": f"Session {resume} does not exist"}) + "\n")
        sys.exit(1)
    if resume is not None and not forking:
        session = {"continue_other_id": new_id(), "continue_upper_id": resume.upper()}.get(mode, resume)
    elif resume is not None:
        session = resume if mode == "fork_returns_source" else new_id()
    else:
        session = new_id()
    log.write("session", session=session)
    store.mkdir(parents=True, exist_ok=True)
    (store / f"{session}.json").write_text(json.dumps({"cwd": cwd_value, "last_prompt": prompt}), encoding="utf-8")
    text = "g" * scenario["text_chars"] if mode == "long_text" else scenario.get("text", f"grok answer to: {prompt}")
    answer: dict[str, Any] = {"text": text, "sessionId": session, "stopReason": "end_turn", "requestId": "req-0001"}
    if mode == "missing_session":
        answer.pop("sessionId")
    log.write("answer", session=session, text_chars=len(text), resumed=resume, forked=forking)
    write_out(json.dumps(answer) + "\n")
    sys.exit(0)


def opencode_event(event_type: str, session: str, sequence: int, **fields: Any) -> str:
    return json.dumps({"type": event_type, "timestamp": 1_700_000_000_000 + sequence, "sessionID": session, **fields}) + "\n"


def opencode_text(session: str, sequence: int, message: str, text: str) -> str:
    part = {"id": f"prt_{sequence:04d}", "sessionID": session, "messageID": message, "type": "text", "text": text}
    return opencode_event("text", session, sequence, part=part)


def opencode_error(session: str, name: str, message: str, status: int | None) -> str:
    data: dict[str, Any] = {"message": message}
    if status is not None:
        data["statusCode"] = status
    return opencode_event("error", session, 99, error={"name": name, "data": data})


def run_opencode(scenario: dict[str, Any], args: list[str]) -> None:
    env = dict(os.environ)
    log = FakeLog(scenario["log_dir"], "opencode")
    kind = stdin_kind()
    stdin_text = read_stdin_text() if kind in ("pipe", "file") else ""
    options, switches, stray = parse_joined(args[1:], OPENCODE_SWITCHES)
    config = sanitized_config(env.get("OPENCODE_CONFIG_CONTENT"))
    skills_paths = (config or {}).get("skills", {}).get("paths", []) if isinstance(config, dict) else []
    start_record(log, "opencode", args, env, via_wsl=False, skills_folder=None, extra={"options": options, "switches": switches, "stray": stray, "stdin_text": stdin_text, "skill_paths_loadable": [Path(path).is_absolute() and (Path(path) / "SKILL.md").is_file() for path in skills_paths]})
    mode = scenario.get("mode", "ok")
    if scenario.get("grandchild"):
        start_grandchild(log)
    if args[:1] != ["run"] or stray:
        write_err(f"fake opencode: expected `run` and --flag=value options, got {args!r}\n")
        sys.exit(2)
    if not stdin_text.strip():
        write_err("Error: You must provide a message or a command\n")
        sys.exit(1)
    state = Path(scenario["state_dir"]) / "opencode"
    state.mkdir(parents=True, exist_ok=True)
    requested = options.get("--session")
    forking = "--fork" in switches
    if requested is not None and not (state / requested).is_file():
        write_err("Error: Session not found\n")
        sys.exit(1)
    if requested is not None and not forking:
        session = new_id("ses_") if mode == "continue_other_id" else requested
    elif requested is not None:
        session = requested if mode == "fork_returns_source" else new_id("ses_")
    else:
        session = new_id("ses_")
    (state / session).write_text(stdin_text, encoding="utf-8")
    log.write("session", session=session)
    provider = options.get("--model", "").split("/", 1)[0]
    bound = isinstance(config, dict) and isinstance(config.get("provider", {}).get(provider, {}).get("options", {}).get("apiKey"), dict)
    if mode in ("session_then_hold", "session_then_flood", "hold"):
        if mode != "hold":
            write_out(opencode_event("step_start", session, 1, part={"type": "step-start", "messageID": "msg_0001"}))
        if mode == "session_then_flood":
            flood(scenario["flood_bytes"])
            sys.exit(0)
        log.write("held", outcome=hold(scenario))
    if mode == "flood":
        flood(scenario["flood_bytes"])
        sys.exit(0)
    if mode == "garbage":
        write_out("opencode finished, but printed no events\n")
        sys.exit(0)
    if mode == "echo_secrets":
        write_out(opencode_error(session, "UnknownError", echo_text(scenario, args, stdin_text, env), None))
        sys.exit(1)
    if mode == "key_rejected" or not bound:
        write_out(opencode_error(session, "ProviderAuthError", f"The API key for provider {provider} was not accepted", None))
        sys.exit(1)
    if mode == "key_rejected_status":
        write_out(opencode_error(session, "APIError", "Unauthorized: the provider refused the credentials", 401))
        sys.exit(1)
    if mode == "fail":
        write_out(opencode_error(session, "UnknownError", scenario["vendor_text"], None))
        sys.exit(scenario.get("exit_code", DEFAULT_FAIL_EXIT))
    if mode == "stderr_exit":
        write_err(scenario["vendor_text"] + "\n")
        sys.exit(scenario.get("exit_code", DEFAULT_FAIL_EXIT))
    parts = ["o" * scenario["text_chars"]] if mode == "long_text" else scenario.get("final_parts", [f"opencode answer to: {stdin_text}"])
    write_out("opencode: loading plugins\n")
    write_out(opencode_event("step_start", session, 1, part={"type": "step-start", "messageID": "msg_0001"}))
    write_out(opencode_text(session, 2, "msg_0001", "Let me look at the files first."))
    write_out(opencode_event("tool_use", session, 3, part={"type": "tool", "messageID": "msg_0001", "tool": "read"}))
    write_out(opencode_event("step_start", session, 4, part={"type": "step-start", "messageID": "msg_0002"}))
    for index, part in enumerate(parts):
        write_out(opencode_text(session, 5 + index, "msg_0002", part))
    write_out(opencode_event("step_finish", session, 50, part={"type": "step-finish", "messageID": "msg_0002"}))
    log.write("answer", session=session, resumed=requested, forked=forking)
    sys.exit(0)


def muse_record(stream_kind: str, stream_id: str, payload_type: str, payload: dict[str, Any]) -> str:
    return json.dumps({"schema_version": 1, "id": new_id("rec-"), "stream": {"kind": stream_kind, "id": stream_id}, "payload_type": payload_type, "payload": payload}) + "\n"


def parse_muse_exec(args: list[str]) -> tuple[dict[str, str], list[str], list[str], str | None]:
    options: dict[str, str] = {}
    switches: list[str] = []
    operands: list[str] = []
    index = 0
    while index < len(args):
        element = args[index]
        if element == "--":
            operands = args[index + 1 :]
            break
        if element.startswith("-") and "=" in element:
            return options, switches, operands, f"error: unknown option {element}"
        if element in MUSE_VALUED and index + 1 < len(args):
            options[element] = args[index + 1]
            index += 2
            continue
        if element in MUSE_SWITCHES:
            switches.append(element)
            index += 1
            continue
        return options, switches, operands, f"error: unexpected argument {element!r}"
    if len(operands) != 1:
        return options, switches, operands, "error: exec takes exactly one prompt after --"
    return options, switches, operands, None


def register_mark(scenario: dict[str, Any], env: dict[str, str]) -> None:
    mark = env.get("VIDBYTE_PEER_MARK")
    if mark:
        folder = Path(scenario["state_dir"]) / "marks" / mark
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{os.getpid()}.pid").write_text(str(os.getpid()), encoding="utf-8")


def run_muse_exec(scenario: dict[str, Any], args: list[str], env: dict[str, str], via_wsl: bool, launcher_args: list[str]) -> None:
    options, switches, operands, problem = parse_muse_exec(args[1:])
    xdg = host_path(env.get("XDG_CONFIG_HOME"), via_wsl)
    log = FakeLog(scenario["log_dir"], "muse-exec")
    start_record(log, "muse-exec", args, env, via_wsl=via_wsl, skills_folder=None if xdg is None else xdg / "muse" / "skills", extra={"options": options, "switches": switches, "operands": operands, "launcher_args": launcher_args})
    mode = scenario.get("mode", "ok")
    if via_wsl:
        register_mark(scenario, env)
    if scenario.get("grandchild"):
        start_grandchild(log)
    if problem is not None:
        write_err(problem + "\n")
        sys.exit(2)
    state = Path(scenario["state_dir"]) / "muse"
    state.mkdir(parents=True, exist_ok=True)
    requested = options.get("--session-id")
    if requested is not None and (state / requested).is_file():
        session = new_id() if mode == "continue_other_id" else requested
    else:
        session = new_id()
        if requested is not None:
            log.write("silently_created", requested=requested, session=session)
    log.write("session", session=session)
    run_stream = new_id("run-")
    if mode in ("hold", "session_then_hold"):
        if mode == "session_then_hold":
            write_out(muse_record("run", run_stream, "run.started", {}))
            write_out(muse_record("session", session, "session.turn.started", {}))
        log.write("held", outcome=hold(scenario))
    if mode == "key_rejected" or "META_API_KEY" not in env:
        write_err(MUSE_KEY_REJECTED if mode == "key_rejected" else "Error: missing meta credentials; set META_API_KEY\n")
        sys.exit(1)
    if mode == "flood":
        write_out(muse_record("session", session, "session.turn.started", {}))
        flood(scenario["flood_bytes"])
        sys.exit(0)
    if mode == "garbage":
        write_out("Muse Code finished, but printed no records\n")
        sys.exit(0)
    if mode == "fail":
        write_err(scenario["vendor_text"] + "\n")
        sys.exit(scenario.get("exit_code", DEFAULT_FAIL_EXIT))
    if mode == "echo_secrets":
        write_err(echo_text(scenario, args, "", env) + "\n")
        sys.exit(1)
    (state / session).write_text(operands[0], encoding="utf-8")
    text = "m" * scenario["text_chars"] if mode == "long_text" else scenario.get("text", f"muse answer to: {operands[0]}")
    write_out("Muse Code 1.0.1 (headless)\n")
    write_out(muse_record("run", run_stream, "run.started", {"command_id": new_id()}))
    if mode != "no_session":
        write_out(muse_record("session", session, "session.turn.started", {}))
        write_out(muse_record("session", session, "task.lifecycle.failed", {"reason": "an optional subtask was skipped"}))
    if mode == "no_terminal":
        sys.exit(0)
    if mode == "terminal_failed":
        write_out(muse_record("session", session, "run.terminal.failed", {"kind": "run_terminal", "terminal": "failed", "text": None, "reason": scenario["vendor_text"], "run_stream": {"id": run_stream, "kind": "run"}}))
        sys.exit(scenario.get("exit_code", 1))
    stream_kind = "run" if mode == "no_session" else "session"
    stream_id = run_stream if mode == "no_session" else session
    write_out(muse_record(stream_kind, stream_id, "run.terminal.completed", {"kind": "run_terminal", "terminal": "completed", "text": text, "reason": None, "run_stream": {"id": run_stream, "kind": "run"}}))
    log.write("answer", session=session, resumed=requested)
    sys.exit(0)


def serve_answer(scenario: dict[str, Any], frame: dict[str, Any], state: Path, log: FakeLog) -> dict[str, Any] | None:
    method = frame.get("method")
    params = frame.get("params") or {}
    if "id" not in frame:
        return None
    reply: dict[str, Any] = {"jsonrpc": "2.0", "id": frame["id"]}
    if method == "initialize":
        client = params.get("clientInfo") or {}
        if not (isinstance(client.get("name"), str) and client["name"] and isinstance(client.get("version"), str) and client["version"]):
            reply["error"] = {"code": -32602, "message": "initialize needs clientInfo.name and clientInfo.version", "data": {"kind": "invalidParams"}}
            return reply
        reply["result"] = {"protocolVersion": "1.0.1", "serverInfo": {"name": "muse", "version": "1.0.1"}}
        return reply
    if not SERVE_STATE["initialized"]:
        reply["error"] = {"code": -32600, "message": "notInitialized", "data": {"kind": "notInitialized"}}
        return reply
    source = params.get("sessionId")
    if scenario.get("serve_mode") == "other_error":
        reply["error"] = {"code": -32603, "message": "internal: the session store is locked by another process", "data": {"kind": "internal"}}
        return reply
    if params.get("excludeItems") is not True or not isinstance(source, str):
        reply["error"] = {"code": -32602, "message": "sessionId and excludeItems are required", "data": {"kind": "invalidParams"}}
        return reply
    if not (state / source).is_file():
        reply["error"] = {"code": -32020, "message": f"session {source} not found", "data": {"kind": "sessionNotFound"}}
        return reply
    if method == "session/read":
        reply["result"] = {"session": {"sessionId": source, "status": "notLoaded"}}
        return reply
    if method == "session/fork":
        if not isinstance(params.get("commandId"), str) or UUID7_PATTERN.fullmatch(params["commandId"]) is None:
            reply["error"] = {"code": -32602, "message": "commandId must be a UUIDv7", "data": {"kind": "invalidParams"}}
            return reply
        forked = source if scenario.get("serve_mode") == "fork_returns_source" else new_id()
        (state / forked).write_text((state / source).read_text(encoding="utf-8"), encoding="utf-8")
        log.write("forked", source=source, session=forked)
        reply["result"] = {"session": {"sessionId": forked, "forkedFrom": source, "status": "notLoaded"}}
        return reply
    reply["error"] = {"code": -32601, "message": f"method {method} not found", "data": {"kind": "methodNotFound"}}
    return reply


def run_muse_serve(scenario: dict[str, Any], args: list[str], env: dict[str, str], via_wsl: bool, launcher_args: list[str]) -> None:
    log = FakeLog(scenario["log_dir"], "muse-serve")
    start_record(log, "muse-serve", args, env, via_wsl=via_wsl, skills_folder=None, extra={"launcher_args": launcher_args})
    if via_wsl:
        register_mark(scenario, env)
    serve_mode = scenario.get("serve_mode", "ok")
    if args != ["serve"]:
        write_err(f"fake muse: unexpected serve arguments {args!r}\n")
        sys.exit(2)
    state = Path(scenario["state_dir"]) / "muse"
    state.mkdir(parents=True, exist_ok=True)
    stream = getattr(sys.stdin, "buffer", None)
    lines = [] if stream is None else stream.read().decode("utf-8", errors="replace").splitlines()
    for line in lines:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            log.write("invalid_frame", line=line)
            continue
        log.write("frame", frame=frame)
        if frame.get("method") == "initialized" and "id" not in frame:
            SERVE_STATE["initialized"] = True
            continue
        if serve_mode in ("hold", "no_answer") and frame.get("method") != "initialize":
            continue
        reply = serve_answer(scenario, frame, state, log)
        if reply is not None:
            write_out(json.dumps(reply) + "\n")
    log.write("eof")
    if serve_mode == "hold":
        log.write("held", outcome=hold(scenario))
    sys.exit(0)


def run_muse(scenario: dict[str, Any], args: list[str], *, via_wsl: bool, launcher_args: list[str]) -> None:
    env = visible_environment(via_wsl)
    if args[:1] == ["exec"]:
        run_muse_exec(scenario, args, env, via_wsl, launcher_args)
    if args[:1] == ["serve"]:
        run_muse_serve(scenario, args, env, via_wsl, launcher_args)
    log = FakeLog(scenario["log_dir"], "muse-unknown")
    log.write("start", role="muse-unknown", argv=args)
    write_err(f"fake muse: unknown command {args!r}\n")
    sys.exit(2)


def reap(scenario: dict[str, Any], args: list[str]) -> None:
    # `wsl.exe -d <distro> -e sh -s <mark>` with the reap script on stdin: log it and end the processes carrying the mark.
    script = read_stdin_text()
    mark = args[1] if len(args) > 1 else None
    log = FakeLog(scenario["log_dir"], "wsl-reap")
    killed: list[int] = []
    folder = Path(scenario["state_dir"]) / "marks" / (mark or "-")
    for pid_file in sorted(folder.glob("*.pid")) if mark else []:
        try:
            os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGTERM)
            killed.append(int(pid_file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    log.write("start", role="wsl-reap", argv=args, mark=mark, script_chars=len(script), script_has_carriage_return="\r" in script, killed=killed, stdin_kind=stdin_kind())
    sys.exit(0)


def run_wsl(scenario: dict[str, Any], args: list[str]) -> None:
    wsl = scenario.get("wsl", {})
    if args[:2] == ["-l", "-q"]:
        log = FakeLog(scenario["log_dir"], "wsl-list")
        log.write("start", role="wsl-list", argv=args)
        try:
            sys.stdout.buffer.write(("\r\n".join(wsl.get("distros", [])) + "\r\n").encode("utf-16-le"))
            sys.stdout.buffer.flush()
        except (OSError, ValueError):
            os._exit(0)
        sys.exit(0)
    if len(args) < 4 or args[0] != "-d" or args[2] != "-e":
        log = FakeLog(scenario["log_dir"], "wsl-unknown")
        log.write("start", role="wsl-unknown", argv=args)
        write_err(f"fake wsl.exe: unexpected arguments {args!r}\n")
        sys.exit(2)
    distro, program, rest = args[1], args[3], args[4:]
    if distro not in wsl.get("distros", []):
        log = FakeLog(scenario["log_dir"], "wsl-missing-distro")
        log.write("start", role="wsl-missing-distro", argv=args)
        write_err(WSL_DISTRO_NOT_FOUND)
        sys.exit(1)
    if program == "sh" and rest[:1] == ["-s"]:
        reap(scenario, rest)
    if program != wsl.get("muse_path", "/usr/local/bin/muse"):
        log = FakeLog(scenario["log_dir"], "wsl-missing-muse")
        log.write("start", role="wsl-missing-muse", argv=args)
        write_err(f"<3>WSL (12) ERROR: CreateProcessCommon:559: execvpe({program}) failed: No such file or directory\n")
        sys.exit(1)
    run_muse(scenario, rest, via_wsl=True, launcher_args=args)


def main() -> None:
    scenario = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    args = sys.argv[2:]
    if args[:1] == ["--as-wsl"]:
        run_wsl(scenario, args[1:])
    program = scenario["program"]
    if program == "grok":
        run_grok(scenario, args)
    if program == "opencode":
        run_opencode(scenario, args)
    if program == "muse":
        run_muse(scenario, args, via_wsl=False, launcher_args=[])
    write_err(f"fake harness: unknown program {program!r}\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
