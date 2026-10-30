"""FILE: tests/features/claude_code_agent/fake_claude.py

PURPOSE: A stand-in for Claude Code's `claude` executable in print mode, so ClaudeCodeHarnessAgent can be tested offline. It parses the joined `--flag=value` argv the agent builds, reads the one stream-json user message on stdin, keeps a session store keyed by working folder exactly as Claude Code does (a resume from another folder is "No conversation found"), logs what it received, and prints the stream-json events Claude Code 2.1.314 printed in the live probes (docs/design/claude-code-harness-agent.md section 4), or the failure a scenario asks for.
ROLE IN CODEBASE: Started by the `claude` stand-in conftest.py builds (claude.exe through pip's console-script launcher on Windows, a script on POSIX) on a PATH that holds only the test's bin folder. Its state folder comes from FAKE_CLAUDE_HOME, which the stand-in sets before running this file.
ARCHITECTURE NOTE: Standard library only, one file, no import of vidbyte, so it behaves like an outside program. Each run appends one JSON record to <home>/log.jsonl: argv, cwd, the files in cwd, the stdin message, the instructions file text and folder, which watched environment variables it saw, and its pid. The scenario is <home>/scenario.json, a list consumed one entry per run (the last entry repeats), so a test can script a first and a second run differently.
COMMON MODIFICATION PATTERNS: A new Claude Code behavior is one more `mode` in run_scenario, shaped from a real observation; record the observation in the design doc first.
KNOWN EDGE CASES: The sleep mode writes its log record before sleeping, so a timeout test can read the pid of the process it expects to be stopped. Costs follow Claude Code's observed rules: total_cost_usd and modelUsage are cumulative over the session, model_usage_since_last_result is this run alone, and usage is this run alone.
RELATED DOCS: tests/features/claude_code_agent/FEATURE.md
TESTS: Used by every test in tests/features/claude_code_agent/ except test_claude_code_live.py.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

WATCHED_VARIABLES = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_EFFORT",
    "CLAUDE_PID",
    "CLAUDE_CONFIG_DIR",
    "ANTHROPIC_API_KEY",
)
DEFAULT_MODEL = "claude-fake-default"
RUN_COST = 0.00025
SWITCHES = {"--print", "--verbose", "--safe-mode", "--strict-mcp-config", "--disable-slash-commands"}


def parse_argv(argv: list[str]) -> dict[str, object]:
    # Joined options become name -> value; switches become name -> True.
    options: dict[str, object] = {}
    unknown: list[str] = []
    for element in argv:
        if element in SWITCHES:
            options[element] = True
        elif element.startswith("--") and "=" in element:
            name, value = element.split("=", 1)
            options[name] = value
        else:
            unknown.append(element)
    options["__unknown__"] = unknown
    return options


def next_scenario(home: Path) -> dict[str, object]:
    # Consume the first scenario entry; the last one repeats.
    path = home / "scenario.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else [{}]
    current = entries[0]
    if len(entries) > 1:
        path.write_text(json.dumps(entries[1:]), encoding="utf-8")
    return current


def emit(event: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")


def main() -> int:
    home = Path(os.environ["FAKE_CLAUDE_HOME"])
    options = parse_argv(sys.argv[1:])
    scenario = next_scenario(home)
    stdin_text = sys.stdin.buffer.read().decode("utf-8")
    message = json.loads(stdin_text.splitlines()[0]) if stdin_text.strip() else {}
    instructions_path = Path(str(options.get("--system-prompt-file", "")))
    cwd = Path.cwd()
    record = {
        "argv": sys.argv[1:],
        "options": {key: value for key, value in options.items() if key != "__unknown__"},
        "unknown": options["__unknown__"],
        "cwd": str(cwd),
        "cwd_files": sorted(item.name for item in cwd.iterdir()),
        "stdin": stdin_text,
        "message": message,
        "instructions": instructions_path.read_text(encoding="utf-8") if instructions_path.is_file() else None,
        "instructions_folder": str(instructions_path.parent),
        "variables": sorted(name for name in WATCHED_VARIABLES if name in os.environ),
        "pid": os.getpid(),
        "started": time.time(),
        "mode": scenario.get("mode", "success"),
    }
    with (home / "log.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\n")
    return run_scenario(home, options, scenario, message, cwd)


def run_scenario(home: Path, options: dict[str, object], scenario: dict[str, object], message: dict[str, object], cwd: Path) -> int:
    mode = scenario.get("mode", "success")
    if mode == "sleep":
        time.sleep(float(scenario.get("seconds", 60)))
        return 0
    if mode == "unknown_option":
        sys.stderr.write("error: unknown option '--safe-mode'\n")
        return 1
    if mode == "garbage":
        sys.stdout.write("this is not json\n")
        return 0
    if mode == "crash":
        sys.stderr.write(str(scenario.get("stderr", "API Error: 529 overloaded")) + "\n")
        return int(scenario.get("exit", 1))

    # Sessions: a new id must be unused; a resume must exist in this folder.
    sessions = home / "sessions"
    sessions.mkdir(exist_ok=True)
    new_id = options.get("--session-id")
    resume_id = options.get("--resume")
    session_id = str(new_id or resume_id)
    store = sessions / f"{session_id}.json"
    if new_id is not None and store.exists():
        sys.stderr.write(f"Error: Session ID {session_id} is already in use.\n")
        return 1
    if resume_id is not None:
        state = json.loads(store.read_text(encoding="utf-8")) if store.exists() else None
        if state is None or state["cwd"] != str(cwd):
            sys.stderr.write(f"No conversation found with session ID: {session_id}\n")
            return 1
    else:
        state = {"cwd": str(cwd), "prompts": [], "total_cost": 0.0, "output_tokens": 0}

    model = str(options.get("--model") or DEFAULT_MODEL)
    tools_value = str(options.get("--tools", "default"))
    tools = [] if tools_value == "" else ["Bash", "Read", "Edit"] if tools_value == "default" else tools_value.split(",")
    if "--json-schema" in options:
        tools.append("StructuredOutput")
    tools.extend(scenario.get("extra_tools", []))
    emit({"type": "system", "subtype": "init", "session_id": session_id, "cwd": str(cwd), "tools": tools, "mcp_servers": scenario.get("mcp_servers", []), "model": model, "apiKeySource": "none", "plugins": []})

    if mode == "auth_failure":
        emit({"type": "result", "subtype": "success", "is_error": True, "result": scenario.get("text", "Not logged in · Please run /login"), "session_id": session_id, "total_cost_usd": 0, "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}, "modelUsage": {}, "terminal_reason": "api_error", "api_error_status": scenario.get("status")})
        return int(scenario.get("exit", 1))
    if mode == "error_result":
        emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": scenario.get("text", "API Error: 500 internal"), "session_id": session_id, "total_cost_usd": 0, "usage": {}, "modelUsage": {}})
        return int(scenario.get("exit", 1))
    if mode == "no_result":
        return 0

    # A turn: optionally wait, remember the prompt, then answer with the observed result shape.
    time.sleep(float(scenario.get("delay", 0)))
    content = message.get("message", {}).get("content", []) if isinstance(message.get("message"), dict) else []
    prompt = next((block.get("text", "") for block in content if block.get("type") == "text"), "")
    state["prompts"].append(prompt)
    run_cost = float(scenario.get("cost", RUN_COST))
    output_tokens = int(scenario.get("output_tokens", 53))
    state["total_cost"] += run_cost
    state["output_tokens"] += output_tokens
    store.write_text(json.dumps(state), encoding="utf-8")

    structured = scenario.get("structured")
    if structured is None and "--json-schema" in options and mode != "no_structured_output":
        structured = {"answer": f"turn {len(state['prompts'])}", "first_prompt": state["prompts"][0]}
    text = json.dumps(structured, separators=(",", ":")) if structured is not None else str(scenario.get("text", f"turn {len(state['prompts'])}: {prompt}"))
    emit({"type": "assistant", "message": {"model": model, "role": "assistant", "content": [{"type": "text", "text": text}]}, "session_id": session_id})
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 1126, "cache_read_input_tokens": 40 * (len(state["prompts"]) - 1), "output_tokens": output_tokens, "service_tier": "standard", "iterations": []}
    cumulative = {model: {"inputTokens": 2 * len(state["prompts"]), "outputTokens": state["output_tokens"], "costUSD": state["total_cost"]}}
    result: dict[str, object] = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": text,
        "session_id": str(scenario.get("answer_session", session_id)),
        "total_cost_usd": state["total_cost"],
        "num_turns": 2 if structured is not None else 1,
        "duration_ms": 975,
        "stop_reason": "tool_use" if structured is not None else "end_turn",
        "terminal_reason": "completed",
        "usage": usage,
        "modelUsage": cumulative,
    }
    if structured is not None:
        result["structured_output"] = structured
    if not scenario.get("omit_run_usage"):
        result["model_usage_since_last_result"] = scenario.get("run_usage", {model: {"inputTokens": 2, "outputTokens": output_tokens, "costUSD": run_cost}})
    if mode == "huge":
        sys.stdout.write("x" * int(scenario.get("bytes", 0)) + "\n")
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
