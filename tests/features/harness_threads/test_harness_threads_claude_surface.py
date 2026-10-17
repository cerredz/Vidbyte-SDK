"""FILE: tests/features/harness_threads/test_harness_threads_claude_surface.py

PURPOSE: The public surface the Claude Code thread functions add and the removal of PR #1044's host stack (spec claude-thread-functions): the exports and identities of the six new names and the `claude` subpackage's three functions (INV-1, AC-18), the new StrEnums and their vendor values (§8.5, INV-18), the contract constants and the Claude rows of every harness- or code-keyed table (§8.5, AC-18), ClaudeThreadConfig's fields, defaults and refusals (AC-18, INV-5 rule 4, D-13), NativeThreadRequest's Claude-only thread-id and stdin prompt rules (INV-5 rules 1-2, §9.1), the hostkit export (§12.3 row 22), and every #1044 name, module, file, extra and import gone, with the shared files restored to the merge base (INV-19, AC-20, D-17).
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
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FUNCTIONS = ["continue_claude_thread", "fork_claude_thread", "run_claude_thread"]
NEW_EXPORTS = ["ClaudePermissionMode", "ClaudeReasoningEffort", "ClaudeThreadConfig", *FUNCTIONS]
INTERNAL_NAMES = ["ClaudeThreads", "ClaudeThreadRun", "ClaudeWire", "ClaudeFlag"]
CLAUDE_ENUMS = {
    "ClaudePermissionMode": [("DEFAULT", "default"), ("ACCEPT_EDITS", "acceptEdits"), ("DONT_ASK", "dontAsk"), ("PLAN", "plan")],
    "ClaudeReasoningEffort": [("LOW", "low"), ("MEDIUM", "medium"), ("HIGH", "high"), ("XHIGH", "xhigh"), ("MAX", "max")],
    "ClaudeFlag": [
        ("PRINT", "--print"), ("OUTPUT_FORMAT", "--output-format"), ("SETTING_SOURCES", "--setting-sources"), ("PERMISSION_MODE", "--permission-mode"),
        ("MODEL", "--model"), ("EFFORT", "--effort"), ("RESUME", "--resume"), ("FORK_SESSION", "--fork-session"),
    ],
}
CLAUDE_CONSTANTS = {
    "CLAUDE_PROGRAM": "claude", "CLAUDE_INSTALL_FOLDERS": (".local", "bin"), "CLAUDE_PRIVATE_CONFIGS_PARTS": (".vidbyte", "claude-configs"),
    "CLAUDE_CONFIG_KEY_HEX_CHARS": 16, "CLAUDE_SKILLS_DIR": "skills", "CLAUDE_JSON_OUTPUT_FORMAT": "json", "CLAUDE_USER_SETTING_SOURCE": "user",
    "CLAUDE_INHERITED_ENVIRONMENT_PREFIXES": ("ANTHROPIC_", "CLAUDE"), "CLAUDE_INHERITED_ENVIRONMENT_KEPT": frozenset({"CLAUDE_CODE_GIT_BASH_PATH"}),
    "CLAUDE_THREAD_ID_PATTERN": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    "CLAUDE_SESSION_FIELD": "session_id", "CLAUDE_RESULT_FIELD": "result", "CLAUDE_IS_ERROR_FIELD": "is_error", "CLAUDE_API_ERROR_STATUS_FIELD": "api_error_status",
    "CLAUDE_TERMINAL_REASON_FIELD": "terminal_reason", "CLAUDE_SUBTYPE_FIELD": "subtype", "CLAUDE_ERRORS_FIELD": "errors",
    "CLAUDE_SESSION_NOT_FOUND_MARKER": "No conversation found with session ID", "CLAUDE_KEY_REJECTED_STATUSES": frozenset({401, 403}),
    "CLAUDE_ERROR_TEXT": "{reason}: {message}", "CLAUDE_ERROR_STATUS_TEXT": "{reason} (status {status}): {message}", "CLAUDE_TESTED_VERSION": "2.1.301",
    "CLAUDE_CONFIG_FAILURE_DETAIL": "The private Claude Code config folder {home} could not be prepared ({error_type}: {reason}).",
    "CLAUDE_CONFIG_UNKNOWN_DETAIL": "The user home folder, where the private Claude Code config folder lives, could not be determined ({error_type}); set HOME (POSIX) or USERPROFILE (Windows) for this process.",
}
PROBLEMS = ["not_installed", "launcher_refused", "launch_failed", "key_rejected", "thread_not_found", "timed_out", "output_too_large", "protocol_mismatch", "run_failed"]
BAD_CONFIG_FIELDS = [
    ("permission_mode", "bypassPermissions"), ("permission_mode", "auto"), ("permission_mode", "manual"), ("permission_mode", "yolo"),
    ("reasoning_effort", "turbo"), ("reasoning_effort", "none"), ("reasoning_effort", "minimal"), ("reasoning_effort", "ultra"),
    ("timeout_seconds", 0), ("timeout_seconds", -1.0), ("timeout_seconds", math.nan), ("timeout_seconds", math.inf), ("timeout_seconds", 14400.5),
    ("timeout_seconds", True), ("timeout_seconds", "60"), ("claude_command", ()), ("claude_command", ("",)), ("claude_command", "claude"),
    ("claude_command", ["claude"]), ("claude_command", ("cl\x00aude",)),
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
    # INV-1 / AC-18 / §12.3 rows 18 and 21: the six new names are the
    # records' and enums' own objects; the claude subpackage exports
    # exactly the three functions, the same objects; the flow, wire and
    # flag classes are exported from neither.
    native = api.native
    claude = importlib.import_module("vidbyte.harnesses.native.claude")
    assert set(NEW_EXPORTS) <= set(native.__all__)
    assert native.ClaudeThreadConfig is api.records.ClaudeThreadConfig
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


def test_claude_contract_constants_hold_the_spec_values(lib_api) -> None:
    # §8.5: every new constant, exactly.
    wrong = {name: getattr(lib_api.constants, name, "<missing>") for name, value in CLAUDE_CONSTANTS.items() if getattr(lib_api.constants, name, "<missing>") != value}
    assert wrong == {}


def test_every_harness_and_code_table_has_its_claude_rows(lib_api) -> None:
    # AC-18 / INV-6 / INV-7: the label, the tested version, the nine
    # failure codes by problem (and no WSL row), a text per code, and
    # Claude among the stdin-prompt harnesses.
    constants, enums, codes = lib_api.constants, lib_api.enums, lib_api.FailureCode
    claude = enums.NativeHarness.CLAUDE
    assert constants.NATIVE_HARNESS_LABELS[claude] == "Claude Code"
    assert constants.NATIVE_TESTED_VERSIONS[claude] == constants.CLAUDE_TESTED_VERSION == "2.1.301"
    rows = {problem.value: code for (harness, problem), code in constants.NATIVE_THREAD_FAILURE_CODES.items() if harness is claude}
    assert rows == {problem: codes(f"claude.{problem}") for problem in PROBLEMS}
    for code in rows.values():
        assert constants.NATIVE_THREAD_LIKELY_CAUSES[code].strip() and constants.NATIVE_THREAD_NEXT_STEPS[code].strip(), code
    assert constants.NATIVE_STDIN_PROMPT_HARNESSES == frozenset({enums.NativeHarness.OPENCODE, claude})


def test_claude_thread_config_has_the_spec_fields_and_defaults(lib_api) -> None:
    # AC-18 / D-13 / §9.1: frozen and slotted; exactly four fields and
    # no model; defaults (None, DEFAULT, 1800.0, None); a member or its
    # exact value is accepted; the timeout bound is inclusive.
    cls, enums = lib_api.ClaudeThreadConfig, lib_api.enums
    assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen and "__slots__" in vars(cls)
    assert [field.name for field in dataclasses.fields(cls)] == ["reasoning_effort", "permission_mode", "timeout_seconds", "claude_command"]
    default = cls()
    assert (default.reasoning_effort, default.permission_mode, default.timeout_seconds, default.claude_command) == (None, enums.ClaudePermissionMode.DEFAULT, 1800.0, None)
    assert default.permission_mode is enums.ClaudePermissionMode.DEFAULT and default.timeout_seconds == lib_api.constants.NATIVE_THREAD_DEFAULT_SECONDS
    built = cls(reasoning_effort="xhigh", permission_mode="acceptEdits", timeout_seconds=14400, claude_command=("claude-bin", "--debug"))
    assert built.reasoning_effort is enums.ClaudeReasoningEffort.XHIGH and built.permission_mode is enums.ClaudePermissionMode.ACCEPT_EDITS
    assert built.timeout_seconds == 14400 and built.claude_command == ("claude-bin", "--debug")
    with pytest.raises(TypeError):
        cls(model="sonnet")


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
    # INV-19 / AC-20 / NG-3: `git grep claude_agent_sdk -- vidbyte` is
    # empty.
    found = git("grep", "-n", "claude_agent_sdk", "--", "vidbyte")
    assert found.returncode in (0, 1), found.stderr
    assert found.stdout.strip() == ""


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


def test_errors_base_differs_from_the_merge_base_in_one_docstring_line_only() -> None:
    # AC-20 / §12.3 rows 5 and 28: ClaudeOperationError is gone and the
    # NativeThreadError line names Claude Code.
    removed, added = changed_lines(merge_base(), "vidbyte/lib/errors/base.py")
    assert len(removed) == 1 and len(added) == 1, f"removed {removed!r}, added {added!r}"
    assert "NativeThreadError" in removed[0] and "Grok, opencode and Muse thread functions" in removed[0]
    assert "NativeThreadError" in added[0] and "Grok, opencode, Muse and Claude Code thread functions" in added[0]
