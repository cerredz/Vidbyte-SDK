"""FILE: tests/features/harness_threads/test_harness_threads_claude_surface.py

PURPOSE: The public surface the Claude Code thread functions add and the removal of PR #1044's host stack (spec claude-thread-functions): the exports and identities of the eight new names and the `claude` subpackage's three functions (INV-1, AC-18; ClaudeThreadResult and ClaudePermissionDenial from the PR #1044 review), the new StrEnums and their vendor values (§8.5, INV-18) and, where Claude Code is installed, that each permission mode is a choice its --help lists, the contract constants and the Claude rows of every harness- or code-keyed table (§8.5, AC-18), ClaudeThreadConfig's fields, defaults and refusals (AC-18, INV-5 rule 4, D-13), NativeThreadRequest's Claude-only thread-id and stdin prompt rules (INV-5 rules 1-2, §9.1), the hostkit export (§12.3 row 22), and every #1044 name, module, file, extra and import gone, with the shared files restored to the merge base (INV-19, AC-20, D-17).
ROLE IN CODEBASE: Start here when a Claude export, enum value, constant or config rule changes, or when a piece of the rejected ClaudeHost design comes back.
ARCHITECTURE NOTE: Names are read through the lazy lib_api/api fixtures, so a missing name fails its own test. The git checks compare against `git merge-base origin/main HEAD` (so a newer main cannot fail them) and skip when origin/main is missing, as in a shallow CI clone; they diff the working tree, so uncommitted work counts. The pins that every harness shares (the native __all__, signatures, NativeHarness, NativeThreadOperation, NativeEnvironmentVariable and the FailureCode tail) live in test_harness_threads_surface.py.
FUNCTION INVENTORY: git runs one bounded read-only git command; merge_base returns the merge base or skips; importable says whether `from <module> import <name>` works; changed_lines lists the added and removed lines of one file's diff; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new Claude public name or constant is a spec change first (§8.5), then one entry in the matching table here. A new file this feature may change is a spec change first (§12.3), then one path in ALLOWED_CHANGED.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte at module level. 2. Do not write to the repository; the git commands only read.
KNOWN EDGE CASES: With core.autocrlf the working tree holds CRLF while blobs hold LF, so byte identity is checked through `git diff`, which normalises line endings. A deleted package can leave an untracked __pycache__ folder behind, so a deleted folder counts as gone when it holds no .py file.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-1, INV-5, INV-16, INV-18, INV-19, §6.2 AC-18, AC-20, §8.5, §9.1, §12.3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_surface.py
"""

from __future__ import annotations

import dataclasses
import enum
import importlib
import importlib.util
import math
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FUNCTIONS = ["continue_claude_thread", "fork_claude_thread", "run_claude_thread"]
NEW_EXPORTS = ["ClaudePermissionDenial", "ClaudePermissionMode", "ClaudeReasoningEffort", "ClaudeThreadConfig", "ClaudeThreadResult", *FUNCTIONS]
INTERNAL_NAMES = ["ClaudeThreads", "ClaudeThreadRun", "ClaudeWire", "ClaudeFlag"]
CLAUDE_ENUMS = {
    "ClaudePermissionMode": [("DEFAULT", "manual"), ("ACCEPT_EDITS", "acceptEdits"), ("DONT_ASK", "dontAsk"), ("PLAN", "plan")],
    "ClaudeReasoningEffort": [("LOW", "low"), ("MEDIUM", "medium"), ("HIGH", "high"), ("XHIGH", "xhigh"), ("MAX", "max")],
    "ClaudeFlag": [
        ("PRINT", "--print"), ("OUTPUT_FORMAT", "--output-format"), ("SETTING_SOURCES", "--setting-sources"), ("PERMISSION_MODE", "--permission-mode"),
        ("MODEL", "--model"), ("EFFORT", "--effort"), ("MAX_TURNS", "--max-turns"), ("MAX_BUDGET_USD", "--max-budget-usd"), ("ALLOWED_TOOLS", "--allowedTools"),
        ("DISALLOWED_TOOLS", "--disallowedTools"), ("RESUME", "--resume"), ("FORK_SESSION", "--fork-session"), ("SESSION_ID", "--session-id"),
    ],
}
CLAUDE_CONSTANTS = {
    "CLAUDE_PROGRAM": "claude", "CLAUDE_INSTALL_FOLDERS": (".local", "bin"), "CLAUDE_PRIVATE_CONFIGS_PARTS": (".vidbyte", "claude-configs"),
    "CLAUDE_CONFIG_KEY_HEX_CHARS": 16, "CLAUDE_SKILLS_DIR": "skills", "CLAUDE_JSON_OUTPUT_FORMAT": "json", "CLAUDE_USER_SETTING_SOURCE": "user",
    "CLAUDE_INHERITED_ENVIRONMENT_PREFIXES": ("ANTHROPIC_", "CLAUDE"), "CLAUDE_INHERITED_ENVIRONMENT_KEPT": frozenset({"CLAUDE_CODE_GIT_BASH_PATH"}),
    "CLAUDE_INHERITED_ENVIRONMENT_DROPPED": frozenset({"API_TIMEOUT_MS", "BASH_DEFAULT_TIMEOUT_MS", "BASH_MAX_OUTPUT_LENGTH", "BASH_MAX_TIMEOUT_MS", "DISABLE_COMPACT", "ENABLE_TOOL_SEARCH", "MAX_THINKING_TOKENS", "MCP_TIMEOUT", "NODE_OPTIONS", "NODE_TLS_REJECT_UNAUTHORIZED"}),
    "CLAUDE_THREAD_ID_PATTERN": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    "CLAUDE_SESSION_FIELD": "session_id", "CLAUDE_RESULT_FIELD": "result", "CLAUDE_IS_ERROR_FIELD": "is_error", "CLAUDE_API_ERROR_STATUS_FIELD": "api_error_status",
    "CLAUDE_TERMINAL_REASON_FIELD": "terminal_reason", "CLAUDE_SUBTYPE_FIELD": "subtype", "CLAUDE_ERRORS_FIELD": "errors",
    "CLAUDE_SESSION_NOT_FOUND_MARKER": "No conversation found with session ID",
    "CLAUDE_REJECTED_OPTION_MARKERS": ("error: unknown option", "error: option '", "error: missing required argument"),
    "CLAUDE_KEY_REJECTED_STATUSES": frozenset({401, 403}), "CLAUDE_RETRYABLE_STATUSES": frozenset({408, 429, *range(500, 600)}),
    "CLAUDE_BUDGET_SUBTYPES": frozenset({"error_max_turns", "error_max_budget_usd"}), "CLAUDE_MAX_TURNS_LIMIT": 1000, "CLAUDE_MAX_TURNS_MIN": 1, "CLAUDE_MAX_BUDGET_USD_LIMIT": 1000.0,
    "CLAUDE_TOOL_RULES_MAX_ITEMS": 32, "CLAUDE_TOOL_RULE_MAX_CHARS": 256, "CLAUDE_SHELL_TOOL_NAMES": frozenset({"Bash", "PowerShell"}),
    "CLAUDE_TOOL_RULE_PATTERN": r"(?!(?:Read|Edit|Write|NotebookEdit)\(/(?!/))[A-Za-z][A-Za-z0-9_-]*(?:\([^()\x00-\x1f\x7f]+\))?",
    "CLAUDE_ERROR_TEXT": "{reason}: {message}", "CLAUDE_ERROR_STATUS_TEXT": "{reason} (status {status}): {message}", "CLAUDE_TESTED_VERSION": "2.1.302",
    "CLAUDE_CONFIG_FAILURE_DETAIL": "The private Claude Code config folder {home} could not be prepared ({error_type}: {reason}).",
    "CLAUDE_CONFIG_UNKNOWN_DETAIL": "The user home folder, where the private Claude Code config folder lives, could not be determined ({error_type}); set HOME (POSIX) or USERPROFILE (Windows) for this process.",
}
PROBLEMS = ["not_installed", "launcher_refused", "launch_failed", "key_rejected", "api_error", "budget_exhausted", "thread_not_found", "timed_out", "output_too_large", "protocol_mismatch", "run_failed"]
BAD_CONFIG_FIELDS = [
    ("permission_mode", "bypassPermissions"), ("permission_mode", "auto"), ("permission_mode", "default"), ("permission_mode", "yolo"),
    ("reasoning_effort", "turbo"), ("reasoning_effort", "none"), ("reasoning_effort", "minimal"), ("reasoning_effort", "ultra"),
    ("timeout_seconds", 0), ("timeout_seconds", -1.0), ("timeout_seconds", math.nan), ("timeout_seconds", math.inf), ("timeout_seconds", 14400.5),
    ("timeout_seconds", True), ("timeout_seconds", "60"), ("claude_command", ()), ("claude_command", ("",)), ("claude_command", "claude"),
    ("claude_command", ["claude"]), ("claude_command", ("cl\x00aude",)),
    # PR #1044 review (P0): anything after the executable reaches claude
    # ahead of the SDK's options, so each form is refused when built.
    ("claude_command", ("claude-bin", "--settings", '{"env":{"ANTHROPIC_BASE_URL":"http://127.0.0.1:18777"}}')),
    ("claude_command", ("claude-bin", "--dangerously-skip-permissions")), ("claude_command", ("claude-bin", "--permission-mode=bypassPermissions")),
    ("claude_command", ("claude-bin", "--mcp-config", "servers.json")), ("claude_command", ("claude-bin", "mcp")), ("claude_command", ("wsl.exe", "-e", "claude")),
    # PR #1044 review 4301898216: the turn and spending limits of a call.
    ("max_turns", 0), ("max_turns", 1001), ("max_turns", 2.0), ("max_turns", True), ("max_turns", "5"),
    ("max_budget_usd", 0), ("max_budget_usd", -1.0), ("max_budget_usd", math.nan), ("max_budget_usd", math.inf), ("max_budget_usd", 1000.5),
    ("max_budget_usd", True), ("max_budget_usd", "5"),
    # PR #1044 review 4301898216 (C2): each rule is one tool name with at
    # most one specifier, so it can never become an option or two rules,
    # and a path rule never starts with a single "/".
    ("allowed_tools", ["Edit"]), ("allowed_tools", "Edit"), ("allowed_tools", ("",)), ("allowed_tools", ("Read(/src/**)",)), ("allowed_tools", ("Edit(/x)",)),
    ("allowed_tools", ("--dangerously-skip-permissions",)), ("allowed_tools", ("Read Edit",)), ("allowed_tools", ("Bash,Edit",)),
    ("allowed_tools", ("Bash(git *)\nEdit",)), ("allowed_tools", ("Bash(a(b))",)), ("allowed_tools", ("Edit",) * 33), ("allowed_tools", ("Bash(" + "x" * 251 + ")",)),
    ("disallowed_tools", ("-x",)), ("disallowed_tools", ("WebFetch", 7)), ("disallowed_tools", ("Write(/etc/**)",)),
    # PR #1044 review 4301898216 (C15): auto memory is a plain switch.
    ("auto_memory", 1), ("auto_memory", "true"), ("auto_memory", None),
]
OLD_NAMES = [
    ("vidbyte.harnesses.native.claude", "ClaudeHost"), ("vidbyte.harnesses.native.claude", "ClaudeLiveSession"), ("vidbyte.harnesses.native", "ClaudeHost"),
    ("vidbyte.lib.errors", "ClaudeOperationError"), ("vidbyte.lib.enums", "ClaudeHostState"), ("vidbyte.tools.toolsets", "ClaudeTools"),
]
OLD_MODULES = [
    "vidbyte.lib.constants.claude", "vidbyte.lib.enums.claude", "vidbyte.lib.dataclasses.claude", "vidbyte.lib.dataclasses.claude_host",
    "vidbyte.tools.builtins.claude", "vidbyte.tools.toolsets.claude",
]
OLD_FOLDERS = ["docs/spec/claude-host", "tests/features/claude_host", "vidbyte/tools/builtins/claude"]
ALLOWED_CHANGED = {
    "vidbyte/lib/enums/__init__.py", "vidbyte/lib/enums/failure.py", "vidbyte/lib/enums/native_threads.py", "vidbyte/lib/constants/native_threads.py",
    "vidbyte/lib/dataclasses/native_threads.py", "vidbyte/lib/dataclasses/validation.py", "vidbyte/lib/errors/base.py", "vidbyte/lib/process/runner.py",
    "vidbyte/lib/process/argv.py", "vidbyte/harnesses/native/__init__.py", "vidbyte/harnesses/native/claude/__init__.py", "vidbyte/harnesses/native/claude/threads.py",
    "vidbyte/harnesses/native/claude/wire.py", "vidbyte/harnesses/native/hostkit/__init__.py", "vidbyte/harnesses/native/hostkit/errors.py",
    "vidbyte/harnesses/native/hostkit/launcher.py", "vidbyte/harnesses/native/hostkit/skills.py", "vidbyte/harnesses/native/hostkit/folders.py",
    "vidbyte/harnesses/native/grok/threads.py", "vidbyte/harnesses/README.md", "REPO_MAP.md",
}
ALLOWED_PREFIXES = ("docs/spec/claude-thread-functions/", "tests/")
RESTORED = ["pyproject.toml", "vidbyte/tools", "vidbyte/lib/errors/__init__.py", "lint/baseline.json"]


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60, stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, check=False)


def merge_base() -> str:
    try:
        found = git("merge-base", "origin/main", "HEAD")
    except (OSError, subprocess.SubprocessError):
        found = None
    if found is None or found.returncode != 0 or not found.stdout.strip():
        pytest.skip("origin/main is not available in this checkout (a shallow CI clone has no main ref)")
    return found.stdout.strip()


def importable(module: str, name: str) -> bool:
    try:
        exec(f"from {module} import {name}", {})
    except ImportError:
        return False
    return True


def changed_lines(base: str, path: str) -> tuple[list[str], list[str]]:
    shown = git("diff", "-U0", "--no-color", base, "--", path)
    assert shown.returncode == 0, shown.stderr
    lines = shown.stdout.splitlines()
    removed = [line[1:] for line in lines if line.startswith("-") and not line.startswith("---")]
    added = [line[1:] for line in lines if line.startswith("+") and not line.startswith("+++")]
    return removed, added


def test_native_package_exports_the_claude_names_and_the_subpackage_its_three_functions(api) -> None:
    # INV-1 / AC-18 / §12.3 rows 18 and 21: the eight new names are the
    # records' and enums' own objects; the claude subpackage exports
    # exactly the three functions, the same objects; the flow, wire and
    # flag classes are exported from neither.
    native = api.native
    claude = importlib.import_module("vidbyte.harnesses.native.claude")
    assert set(NEW_EXPORTS) <= set(native.__all__)
    for name in ("ClaudeThreadConfig", "ClaudeThreadResult", "ClaudePermissionDenial"):
        assert getattr(native, name) is getattr(api.records, name), name
    for name in ("ClaudePermissionMode", "ClaudeReasoningEffort"):
        assert getattr(native, name) is getattr(api.enums, name) is getattr(api.enums_package, name), name
    assert sorted(claude.__all__) == FUNCTIONS and len(claude.__all__) == 3
    for name in FUNCTIONS:
        assert getattr(claude, name) is getattr(native, name), name
    leaked = [name for name in INTERNAL_NAMES if name in native.__all__ or name in claude.__all__]
    assert leaked == []


def test_claude_subpackage_holds_exactly_the_three_modules() -> None:
    # INV-19 / §12.3 rows 8, 18-20: #1044's nine host modules are gone;
    # the package mirrors the Grok sibling.
    folder = REPO_ROOT / "vidbyte" / "harnesses" / "native" / "claude"
    assert sorted(path.name for path in folder.glob("*.py")) == ["__init__.py", "threads.py", "wire.py"]


def test_hostkit_exports_the_private_folders_helper() -> None:
    # §12.3 row 22 / D-15: a literal sorted __all__ with the new helper.
    hostkit = importlib.import_module("vidbyte.harnesses.native.hostkit")
    assert hostkit.__all__ == ["NativeErrorFactory", "NativeLauncher", "NativePrivateFolders", "NativeSkillFolders"]
    folders = importlib.import_module("vidbyte.harnesses.native.hostkit.folders")
    assert hostkit.NativePrivateFolders is folders.NativePrivateFolders and folders.__all__ == ["NativePrivateFolders"]


def test_claude_vocabularies_are_str_enums_carrying_claude_codes_values(lib_api) -> None:
    # §8.5 / INV-18 / D-12: member names and values exactly, in order;
    # StrEnum; exported from vidbyte.lib.enums as the same class; no
    # approve-everything member.
    for name, members in CLAUDE_ENUMS.items():
        cls = getattr(lib_api.enums, name)
        assert issubclass(cls, enum.StrEnum), name
        assert [(member.name, member.value) for member in cls] == members, name
        assert all(str(member) == member.value for member in cls), name
        assert getattr(lib_api.enums_package, name) is cls, f"{name} is not exported from vidbyte.lib.enums"
    values = {member.value for member in lib_api.enums.ClaudePermissionMode}
    assert not values & {"bypassPermissions", "auto"}, "INV-18: no approve-everything permission mode"


def test_claude_permission_modes_are_choices_the_installed_claude_lists(lib_api, tmp_path) -> None:
    # PR #1044 review 4301626295: every mode the SDK sends is one of the
    # --permission-mode choices a real claude lists in --help, so a
    # vendor rename fails here instead of in a caller's run. It runs
    # only where Claude Code is installed (PATH or ~/.local/bin), with
    # every ANTHROPIC_*/CLAUDE* variable dropped and a scratch config
    # folder, so it never reads the developer's key or session.
    constants = lib_api.constants
    native = Path.home().joinpath(*constants.CLAUDE_INSTALL_FOLDERS, constants.CLAUDE_PROGRAM + (".exe" if sys.platform == "win32" else ""))
    program = shutil.which(constants.CLAUDE_PROGRAM) or (str(native) if native.is_file() else None)
    if program is None:
        pytest.skip("Claude Code is not installed here, so there is no --help to read")
    environment = {name: value for name, value in os.environ.items() if not name.upper().startswith(constants.CLAUDE_INHERITED_ENVIRONMENT_PREFIXES)}
    environment.update(CLAUDE_CONFIG_DIR=str(tmp_path), DISABLE_AUTOUPDATER="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
    shown = subprocess.run([program, "--help"], cwd=tmp_path, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, stdin=subprocess.DEVNULL, check=False)
    listed = re.search(r"--permission-mode\s+<\w+>.*?\(choices:([^)]*)\)", shown.stdout, re.DOTALL)
    assert shown.returncode == 0 and listed is not None, (shown.stdout + shown.stderr)[-3000:]
    choices = set(re.findall(r'"([^"]+)"', listed.group(1)))
    assert {mode.value for mode in lib_api.enums.ClaudePermissionMode} <= choices, sorted(choices)


def test_claude_contract_constants_hold_the_spec_values(lib_api) -> None:
    # §8.5: every new constant, exactly.
    wrong = {name: getattr(lib_api.constants, name, "<missing>") for name, value in CLAUDE_CONSTANTS.items() if getattr(lib_api.constants, name, "<missing>") != value}
    assert wrong == {}


def test_every_harness_and_code_table_has_its_claude_rows(lib_api) -> None:
    # AC-18 / INV-6 / INV-7: the label, the tested version, the eleven
    # failure codes by problem (and no WSL row; api_error and
    # budget_exhausted from the PR #1044 review), a text per code, only
    # claude.api_error retryable, and Claude among the stdin-prompt
    # harnesses.
    constants, enums, codes = lib_api.constants, lib_api.enums, lib_api.FailureCode
    claude = enums.NativeHarness.CLAUDE
    assert constants.NATIVE_HARNESS_LABELS[claude] == "Claude Code"
    assert constants.NATIVE_TESTED_VERSIONS[claude] == constants.CLAUDE_TESTED_VERSION == "2.1.302"
    rows = {problem.value: code for (harness, problem), code in constants.NATIVE_THREAD_FAILURE_CODES.items() if harness is claude}
    assert rows == {problem: codes(f"claude.{problem}") for problem in PROBLEMS}
    for code in rows.values():
        assert constants.NATIVE_THREAD_LIKELY_CAUSES[code].strip() and constants.NATIVE_THREAD_NEXT_STEPS[code].strip(), code
    assert constants.NATIVE_RETRYABLE_CODES == frozenset({codes("claude.api_error")})
    assert constants.NATIVE_STDIN_PROMPT_HARNESSES == frozenset({enums.NativeHarness.OPENCODE, claude})


def test_claude_thread_config_has_the_spec_fields_and_defaults(lib_api) -> None:
    # AC-18 / D-13 / §9.1: frozen and slotted; exactly nine fields (the
    # turn and spending limits, the tool rules and the auto memory switch
    # from the PR #1044 review) and no model; defaults (None, DEFAULT,
    # 1800.0, None, None, None, (), (), False); a member or its exact
    # value is accepted; the timeout, turn, budget and rule bounds are
    # inclusive.
    cls, enums = lib_api.ClaudeThreadConfig, lib_api.enums
    assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen and "__slots__" in vars(cls)
    assert [field.name for field in dataclasses.fields(cls)] == ["reasoning_effort", "permission_mode", "timeout_seconds", "claude_command", "max_turns", "max_budget_usd", "allowed_tools", "disallowed_tools", "auto_memory"]
    default = cls()
    assert (default.reasoning_effort, default.permission_mode, default.timeout_seconds, default.claude_command, default.max_turns, default.max_budget_usd) == (None, enums.ClaudePermissionMode.DEFAULT, 1800.0, None, None, None)
    assert (default.allowed_tools, default.disallowed_tools, default.subprocess_scrub, default.auto_memory) == ((), (), False, False)
    assert default.permission_mode is enums.ClaudePermissionMode.DEFAULT and default.timeout_seconds == lib_api.constants.NATIVE_THREAD_DEFAULT_SECONDS
    built = cls(reasoning_effort="xhigh", permission_mode="acceptEdits", timeout_seconds=14400, claude_command=("claude-bin",), max_turns=1000, max_budget_usd=1000.0)
    assert built.reasoning_effort is enums.ClaudeReasoningEffort.XHIGH and built.permission_mode is enums.ClaudePermissionMode.ACCEPT_EDITS
    assert built.timeout_seconds == 14400 and built.claude_command == ("claude-bin",) and built.max_turns == 1000 and built.max_budget_usd == 1000.0
    longest = "Read(//" + "x" * 248 + ")"
    rules = cls(allowed_tools=("Edit",) * 32, disallowed_tools=(longest, "Bash(git push *)", "mcp__github__create_issue", "WebFetch(domain:example.com)"))
    assert rules.allowed_tools == ("Edit",) * 32 and rules.disallowed_tools[0] == longest and len(longest) == 256
    with pytest.raises(TypeError):
        cls(model="sonnet")


def test_claude_thread_result_extends_the_shared_result_with_checked_reports(lib_api) -> None:
    # PR #1044 review 4301626286 / 4301898218: a frozen, slotted subclass
    # of NativeThreadResult adding num_turns, terminal_reason and the
    # denied tool calls by name and tool-use id only; a list of denials is
    # stored as a tuple, and a bad value is refused when built.
    cls, denial = lib_api.ClaudeThreadResult, lib_api.ClaudePermissionDenial
    assert issubclass(cls, lib_api.NativeThreadResult) and cls.__dataclass_params__.frozen and "__slots__" in vars(cls)
    assert [field.name for field in dataclasses.fields(cls)] == ["harness", "thread_id", "text", "text_truncated", "num_turns", "terminal_reason", "permission_denials"]
    assert [field.name for field in dataclasses.fields(denial)] == ["tool_name", "tool_use_id"]
    shared = {"harness": "claude", "thread_id": "c3f73f50-b50c-4f3a-8369-f97267313173", "text": "done", "text_truncated": False}
    built = cls(**shared, num_turns=2, terminal_reason="completed", permission_denials=[denial("Bash", "toolu_01")])
    assert built.permission_denials == (denial("Bash", "toolu_01"),) and built.harness is lib_api.enums.NativeHarness.CLAUDE
    assert (cls(**shared).num_turns, cls(**shared).terminal_reason, cls(**shared).permission_denials) == (0, None, ())
    for field, bad in (("num_turns", -1), ("num_turns", True), ("terminal_reason", 5), ("terminal_reason", "x" * 257), ("permission_denials", ({"tool_name": "Bash"},)), ("thread_id", "")):
        with pytest.raises(lib_api.ConfigurationError) as caught:
            cls(**{**shared, field: bad})
        assert f"ClaudeThreadResult.{field}" in str(caught.value) or f"NativeThreadResult.{field}" in str(caught.value), (field, str(caught.value))
    for name, use_id in (("", "toolu_01"), ("Bash", ""), ("Bash", 7)):
        with pytest.raises(lib_api.ConfigurationError):
            denial(name, use_id)


@pytest.mark.parametrize("mode", ["acceptEdits", "dontAsk", "plan"])
def test_claude_thread_config_refuses_a_shell_rule_beside_a_mode_claude_would_force_away(lib_api, mode) -> None:
    # PR #1044 review 4301898216 (C4): an allowed Bash or PowerShell rule
    # turns on CLAUDE_CODE_SUBPROCESS_ENV_SCRUB, and Claude Code 2.1.302
    # then prints "Permission mode forced to default" and drops any other
    # mode (checked by hand), so the record refuses the pair, naming
    # permission_mode; a denied shell or a tool that only reads a shell's
    # output turns nothing on.
    cls = lib_api.ClaudeThreadConfig
    for shell in ("Bash(git *)", "PowerShell"):
        with pytest.raises(lib_api.ConfigurationError) as caught:
            cls(allowed_tools=(shell,), permission_mode=mode)
        assert caught.value.details["field"] == "ClaudeThreadConfig.permission_mode"
    assert cls(allowed_tools=("Bash(git *)",)).subprocess_scrub is True
    assert cls(allowed_tools=("Edit", "BashOutput"), disallowed_tools=("Bash",), permission_mode=mode).subprocess_scrub is False


@pytest.mark.parametrize(("field", "bad"), BAD_CONFIG_FIELDS, ids=[f"{field}={bad!r}"[:50] for field, bad in BAD_CONFIG_FIELDS])
def test_claude_thread_config_refuses_a_bad_field_naming_it(lib_api, field, bad) -> None:
    # AC-18 / INV-5 rule 4 / INV-18: refused when built, with a
    # ConfigurationError naming ClaudeThreadConfig.<field>.
    with pytest.raises(lib_api.ConfigurationError) as caught:
        lib_api.ClaudeThreadConfig(**{field: bad})
    assert f"ClaudeThreadConfig.{field}" in str(caught.value), str(caught.value)


def test_request_applies_the_claude_rules_only_to_claude(lib_api, sandbox, pack) -> None:
    # INV-5 rules 1-2 / §9.1 / INV-20: Claude ids must be lowercase
    # UUIDs and Claude prompts may reach 200,000 characters; the other
    # harnesses keep their own rules (opencode still requires its
    # provider/model).
    enums = lib_api.enums
    fields = {"prompt": "Explain.", "api_key": "sk-ant-key", "workspace": sandbox.workspace}
    uuid_id = "c3f73f50-b50c-4f3a-8369-f97267313173"
    request = lib_api.NativeThreadRequest(harness=enums.NativeHarness.CLAUDE, verb=enums.NativeThreadVerb.CONTINUE, thread_id=uuid_id, **fields)
    assert request.thread_id == uuid_id and request.harness is enums.NativeHarness.CLAUDE
    for bad in ("fix-login", uuid_id.upper(), "-x"):
        with pytest.raises(lib_api.ConfigurationError) as caught:
            lib_api.NativeThreadRequest(harness=enums.NativeHarness.CLAUDE, verb=enums.NativeThreadVerb.FORK, thread_id=bad, **fields)
        assert "thread_id" in str(caught.value), bad
    for harness in (enums.NativeHarness.GROK, enums.NativeHarness.OPENCODE, enums.NativeHarness.MUSE):
        model = {"model": pack.OPENCODE_MODEL} if harness is enums.NativeHarness.OPENCODE else {}
        assert lib_api.NativeThreadRequest(harness=harness, verb=enums.NativeThreadVerb.CONTINUE, thread_id="fix-login", **fields, **model).thread_id == "fix-login"
    long_prompt = {**fields, "prompt": "p" * lib_api.constants.NATIVE_PROMPT_MAX_CHARS}
    assert len(lib_api.NativeThreadRequest(harness=enums.NativeHarness.CLAUDE, verb=enums.NativeThreadVerb.RUN, **long_prompt).prompt) == 200000
    with pytest.raises(lib_api.ConfigurationError):
        lib_api.NativeThreadRequest(harness=enums.NativeHarness.CLAUDE, verb=enums.NativeThreadVerb.RUN, **{**fields, "prompt": "p" * 200001})
    with pytest.raises(lib_api.ConfigurationError):
        lib_api.NativeThreadRequest(harness=enums.NativeHarness.GROK, verb=enums.NativeThreadVerb.RUN, **{**fields, "prompt": "p" * 24001})
    assert lib_api.NativeThreadRequest(harness=enums.NativeHarness.CLAUDE, verb=enums.NativeThreadVerb.RUN, **{**fields, "prompt": '"' * 20000}).prompt == '"' * 20000


def test_hosts_errors_tools_and_records_of_the_rejected_design_are_gone() -> None:
    # INV-19 / AC-20 / §12.3 rows 1-12: no ClaudeHost, ClaudeLiveSession,
    # ClaudeOperationError, Claude tools or toolset, #1044 modules,
    # folders or `claude` extra.
    still_there = [f"{module}.{name}" for module, name in OLD_NAMES if importable(module, name)]
    still_there += [module for module in OLD_MODULES if importlib.util.find_spec(module) is not None]
    still_there += [folder for folder in OLD_FOLDERS if any((REPO_ROOT / folder).rglob("*.py")) or any(path.is_file() and path.suffix == ".md" for path in (REPO_ROOT / folder).rglob("*"))]
    still_there += [path for path in ("vidbyte/tools/toolsets/claude.py", "vidbyte/lib/constants/claude.py", "vidbyte/lib/enums/claude.py", "vidbyte/lib/dataclasses/claude.py", "vidbyte/lib/dataclasses/claude_host.py") if (REPO_ROOT / path).exists()]
    extras = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")).get("project", {}).get("optional-dependencies", {})
    still_there += ["pyproject extra `claude`"] if "claude" in extras else []
    assert still_there == []


def test_no_module_under_vidbyte_imports_claude_agent_sdk() -> None:
    # INV-19 / AC-20 / NG-3: no file under vidbyte/ names
    # claude_agent_sdk. The package folder is walked rather than `git
    # grep`ped, so the check also runs outside a git checkout, such as an
    # sdist (PR #1044 review L15).
    package = REPO_ROOT / "vidbyte"
    found = [path.relative_to(REPO_ROOT).as_posix() for path in sorted(package.rglob("*")) if path.is_file() and "__pycache__" not in path.parts and b"claude_agent_sdk" in path.read_bytes()]
    assert found == [], f"INV-19: these files name claude_agent_sdk: {found}"


def test_branch_changes_only_the_files_the_spec_lists() -> None:
    # INV-19 / AC-20 / D-17: every path outside the spec record and the
    # tests that §12.3 does not list equals the merge base, and the
    # restored files (pyproject, tools, errors __init__, lint baseline)
    # are byte-identical to it.
    base = merge_base()
    changed = git("diff", "--name-only", "--no-renames", base)
    assert changed.returncode == 0, changed.stderr
    untracked = git("ls-files", "--others", "--exclude-standard", "--", "vidbyte", "lint", "scripts", "contracts", "pyproject.toml", "REPO_MAP.md")
    paths = sorted(set(changed.stdout.split()) | set(untracked.stdout.split()))
    unexpected = [path for path in paths if path not in ALLOWED_CHANGED and not path.startswith(ALLOWED_PREFIXES)]
    assert unexpected == [], f"INV-19: changed against the merge base but not listed in §12.3: {unexpected}"
    restored = git("diff", "--name-only", base, "--", *RESTORED)
    assert restored.stdout.split() == [], f"D-17: not byte-identical to the merge base: {restored.stdout.split()}"


def test_errors_base_differs_from_the_merge_base_in_one_docstring_line_and_the_retry_fields() -> None:
    # AC-20 / §12.3 rows 5 and 28: ClaudeOperationError is gone and the
    # NativeThreadError line names Claude Code. PR #1044 review
    # 4301898270 adds only NativeThreadError's retryable and api_status,
    # stored and shown in safe_runtime_details.
    removed, added = changed_lines(merge_base(), "vidbyte/lib/errors/base.py")
    assert len(removed) == 1, f"removed {removed!r}"
    assert "NativeThreadError" in removed[0] and "Grok, opencode and Muse thread functions" in removed[0]
    assert "NativeThreadError" in added[0] and "Grok, opencode, Muse and Claude Code thread functions" in added[0]
    assert [line.strip() for line in added[1:]] == [
        "retryable: bool = False,", "api_status: int | None = None,", "self.retryable = retryable", "self.api_status = api_status",
        '"retryable": str(retryable).lower(),', '"api_status": "" if api_status is None else str(api_status),',
    ]
