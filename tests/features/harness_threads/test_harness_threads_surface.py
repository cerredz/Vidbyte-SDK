"""FILE: tests/features/harness_threads/test_harness_threads_surface.py

PURPOSE: The public surface and the removal of the rejected design: the nine thread functions, the 47 thread helpers and skill functions of harness-thread-helpers-skills and their exports (INV-1, D-22; helpers spec INV-1: 68 names, subpackages 25/15/16), the signatures of the nine (§8.5), the StrEnum vocabularies and vendor values with the helpers spec's appended members and new enums (D-11, R-3; helpers spec §9.1), the FailureCode tail (INV-22, D-10; helpers spec INV-22: 28 + 4 codes), the contract constants (§8.5; helpers spec §9.3), the old names and files gone (AC-13, INV-19, INV-21) and a side-effect-free `import vidbyte` (INV-23).
ROLE IN CODEBASE: Start here when an import, an export list, a failure code or a constant changes. Nothing here starts a vendor stand-in.
ARCHITECTURE NOTE: The git checks compare against `git merge-base origin/main HEAD` (so a newer main cannot fail them) and skip when origin/main is missing, as in a shallow CI clone. The `import vidbyte` check runs in a fresh interpreter so this suite's own imports cannot hide a side effect.
FUNCTION INVENTORY: git runs one bounded git command; literal_all reads a module's literal __all__; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new public name is a spec change first (§8.5), then one entry in EXPECTED_EXPORTS.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte at module level. 2. Do not write to the repository; the git commands only read.
KNOWN EDGE CASES: With core.autocrlf the working tree holds CRLF while blobs hold LF, so byte identity is checked through `git diff`, which normalises line endings, not by reading files. A deleted package can leave an untracked __pycache__ folder behind, so a deleted folder counts as gone when it holds no .py file.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-1, INV-19 to INV-23, §6.2 AC-13, §8.5, §12.3; docs/spec/harness-thread-helpers-skills/spec.md §6.1 INV-1, INV-22, §6.2 AC-20, §9.1, §9.3, §12.3 row 35
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_surface.py
"""

from __future__ import annotations

import ast
import enum
import importlib
import inspect
import json
import os
import subprocess
import sys
import textwrap
from datetime import timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FUNCTIONS = tuple(f"{verb}_{harness}_thread" for harness in ("grok", "opencode", "muse") for verb in ("run", "continue", "fork"))
GROK_HELPERS = ["list_grok_threads", "list_recent_grok_threads", "list_grok_threads_since", "get_grok_thread", "read_grok_thread", "get_grok_thread_lineage", "search_grok_threads", "delete_grok_thread"]
OPENCODE_HELPERS = [name.replace("grok", "opencode") for name in GROK_HELPERS]
MUSE_HELPERS = ["list_muse_threads", "list_recent_muse_threads", "list_muse_threads_since", "get_muse_thread", "read_muse_thread", "get_muse_thread_lineage"]
GROK_COMMANDS = [
    "run_grok_command", "run_grok_goal", "run_grok_implement", "run_grok_design", "run_grok_execute_plan", "run_grok_review", "run_grok_code_review",
    "run_grok_resume_claude", "run_grok_resume_codex", "run_grok_resume_cursor", "run_grok_imagine", "run_grok_imagine_video", "run_grok_plan", "run_grok_explore",
]
OPENCODE_COMMANDS = ["run_opencode_command", "run_opencode_review", "run_opencode_init", "run_opencode_plan"]
MUSE_FUNCTIONS = ["run_muse_skill", "run_muse_goal", "run_muse_plan", "run_muse_import", "run_muse_scaffold", "run_muse_browser_app", "init_muse_workspace"]
NEW_FUNCTIONS = [*GROK_HELPERS, *OPENCODE_HELPERS, *MUSE_HELPERS, *GROK_COMMANDS, *OPENCODE_COMMANDS, *MUSE_FUNCTIONS]
SUBPACKAGE_EXPORTS = {
    harness: [*(f"{verb}_{harness}_thread" for verb in ("run", "continue", "fork")), *(name for name in NEW_FUNCTIONS if f"_{harness}_" in f"_{name}_")]
    for harness in ("grok", "opencode", "muse")
}
EXPECTED_EXPORTS = {
    *FUNCTIONS, "NativeThreadResult", "GrokThreadConfig", "OpencodeThreadConfig", "MuseThreadConfig",
    "NativeThreadError", "GrokPermissionMode", "GrokReasoningEffort", "MuseReasoningEffort",
    *NEW_FUNCTIONS, "NativeThreadSummary", "NativeCommandOutput", "GrokThreadScope", "GrokCommand",
}
EXPECTED_ENUMS = {
    "NativeHarness": ["grok", "opencode", "muse"],
    "NativeThreadVerb": ["run", "continue", "fork"],
    "NativeThreadOperation": [*FUNCTIONS, *NEW_FUNCTIONS],
    "NativeThreadProblem": ["not_installed", "launcher_refused", "launch_failed", "key_rejected", "thread_not_found", "timed_out", "output_too_large", "protocol_mismatch", "run_failed", "wsl_unavailable", "command_not_run", "store_unreadable"],
    "GrokPermissionMode": ["default", "acceptEdits", "dontAsk", "plan"],
    "GrokReasoningEffort": ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
    "MuseReasoningEffort": ["none", "minimal", "low", "medium", "high", "xhigh", "ultra"],
    "GrokFlag": ["--single", "--output-format", "--cwd", "--permission-mode", "--model", "--reasoning-effort", "--resume", "--fork-session", "--agent", "--session-id"],
    "OpencodeFlag": ["--format", "--dir", "--model", "--agent", "--variant", "--session", "--fork", "--command", "--max-count"],
    "MuseFlag": ["--json", "--provider", "--workspace", "--session-id", "--model", "--reasoning-effort", "--user-input-auto-resolve", "--", "--session", "--out", "--dry-run"],
    "WslFlag": ["-d", "-e", "-l", "-q"],
    "NativeEnvironmentVariable": ["XAI_API_KEY", "GROK_CODE_XAI_API_KEY", "GROK_HOME", "GROK_DISABLE_AUTOUPDATER", "OPENCODE_CONFIG_CONTENT", "OPENCODE_DISABLE_AUTOUPDATE", "META_API_KEY", "MUSE_NO_AUTO_UPDATE", "MUSE_AUTH_PATH", "XDG_CONFIG_HOME", "WSLENV", "VIDBYTE_PEER_MARK", "GROK_WORKFLOWS", "PWD"],
    "MuseMethod": ["initialize", "initialized", "session/read", "session/fork", "session/list"],
    "OpencodeEventType": ["text", "error"],
    "GrokThreadScope": ["sdk", "user"],
    "GrokCommand": ["goal", "implement", "design", "execute-plan", "review", "code-review", "resume-claude", "resume-codex", "resume-cursor", "imagine", "imagine-video"],
    "GrokAgent": ["plan", "explore"],
    "GrokCommandFlag": ["--budget", "--effort", "--concurrency", "--dry-run", "--auto-pr", "--local", "--branch", "--pr"],
    "GrokEventType": ["text", "tool_call", "tool_call_update", "end", "error"],
    "MuseSkill": ["bundled:plan", "bundled:import", "bundled:greenfield-project-scaffolding", "bundled:browser-app-delivery"],
}
PROBLEMS = ["not_installed", "launcher_refused", "launch_failed", "key_rejected", "thread_not_found", "timed_out", "output_too_large", "protocol_mismatch", "run_failed"]
NEW_FAILURE_CODES = [f"{harness}.{problem}" for harness in ("grok", "opencode", "muse") for problem in PROBLEMS] + ["muse.wsl_unavailable"] + [
    "grok.command_not_run", "opencode.command_not_run", "muse.command_not_run", "grok.store_unreadable",
]
CONTRACT_CONSTANTS = {
    "NATIVE_THREAD_DEFAULT_SECONDS": 1800.0, "NATIVE_THREAD_MAX_SECONDS": 14400.0, "NATIVE_CONTROL_TIMEOUT_SECONDS": 30.0,
    "NATIVE_KILL_WAIT_SECONDS": 1.0, "MUSE_REAP_TIMEOUT_SECONDS": 10.0, "NATIVE_ARGV_PROMPT_MAX_CHARS": 24000,
    "NATIVE_PROMPT_MAX_CHARS": 200000, "NATIVE_API_KEY_MAX_CHARS": 4096, "NATIVE_API_KEY_PATTERN": r"^[!-z|~]+$",
    "NATIVE_THREAD_MAX_SKILLS": 32, "NATIVE_RESULT_TEXT_MAX_CHARS": 100000, "NATIVE_VENDOR_MESSAGE_MAX_CHARS": 1000,
    "GROK_CLI_MAX_OUTPUT_BYTES": 4194304, "NATIVE_PROCESS_MAX_OUTPUT_BYTES": 67108864, "GROK_PRIVATE_HOMES_PARTS": (".vidbyte", "grok-homes"),
    "GROK_HOME_KEY_HEX_CHARS": 16, "MUSE_DEFAULT_PATH": "/usr/local/bin/muse", "NATIVE_REDACTED": "<redacted>",
    # harness-thread-helpers-skills §9.3 and §12.3 row 4.
    "NATIVE_LIST_DEFAULT_LIMIT": 20, "NATIVE_RECENT_DEFAULT_LIMIT": 10, "NATIVE_LIST_MAX_LIMIT": 200, "NATIVE_SINCE_MAX": timedelta(days=3650),
    "NATIVE_QUERY_MAX_CHARS": 1000, "NATIVE_TITLE_MAX_CHARS": 4096, "NATIVE_TOOL_NAME_MAX_CHARS": 256, "NATIVE_COMMAND_MAX_CHARS": 128,
    "NATIVE_LINEAGE_MAX_DEPTH": 64, "GROK_SUMMARY_MAX_BYTES": 1048576, "GROK_CWD_MAX_BYTES": 65536, "GROK_SUMMARY_GRACE_SECONDS": 60,
    "GROK_CODE_REVIEW_FRAGMENT": "deep code quality audit of the current branch's changes", "GROK_IMAGE_TO_VIDEO_TOOL": "image_to_video",
    "NATIVE_COMMAND_RESERVED_CHARS": 1024, "NATIVE_COMMAND_TEXT_MAX_CHARS": 22976, "GROK_GOAL_MAX_BUDGET_TOKENS": 100000000,
    "GROK_IMPLEMENT_MAX_EFFORT": 5, "GROK_EXECUTE_PLAN_MAX_EFFORT": 2, "GROK_EXECUTE_PLAN_MAX_CONCURRENCY": 8, "GROK_BRANCH_MAX_CHARS": 255,
    "GROK_PR_MAX_CHARS": 2048, "GROK_PR_MAX_NUMBER": 999999999, "NATIVE_OPENCODE_SCAN_MAX": 10000,
    "OPENCODE_SESSION_QUERY": "SELECT id, title, time_created, time_updated, parent_id, directory FROM session WHERE id = '{thread_id}'",
    "OPENCODE_COMMAND_NOT_FOUND_TEXT": 'Command not found: "{command}"', "GROK_SESSION_NOT_FOUND_TEXT": "Session '{thread_id}' not found.",
    "GROK_STREAMING_OUTPUT_FORMAT": "streaming-json", "GROK_WORKFLOWS_OFF": "0", "MUSE_EXPORT_PARTS": ("export", "thread.json"),
    "MUSE_SKILL_PROMPT_TEMPLATE": "Use the `{skill}` skill.\n\n{prompt}", "MUSE_METHOD_NOT_FOUND_CODE": -32601,
    "NATIVE_COMMAND_PATTERN": r"^[A-Za-z0-9][A-Za-z0-9._/:-]*$", "GROK_PR_PATTERN": r"^([1-9][0-9]*|https://\S+)$",
}
OLD_NAMES = [
    ("vidbyte.harnesses.native", "GrokHost"), ("vidbyte.harnesses.native.grok", "GrokHost"),
    ("vidbyte.harnesses.native", "run_grok_once"), ("vidbyte.harnesses.native.grok", "run_grok_once"),
    ("vidbyte.harnesses.native", "OpencodeHost"), ("vidbyte.harnesses.native.opencode", "OpencodeHost"),
    ("vidbyte.harnesses.native", "MuseHost"), ("vidbyte.harnesses.native.muse", "MuseHost"),
    ("vidbyte.lib.errors", "NativeHostError"),
    ("vidbyte.tools.toolsets", "GrokTools"), ("vidbyte.tools.toolsets", "OpencodeTools"),
    ("vidbyte.tools.toolsets", "MuseTools"), ("vidbyte.tools.toolsets", "HarnessBackendTools"),
    ("vidbyte.harnesses.native", "list_harness_backends"), ("vidbyte.harnesses.native.backends", "list_harness_backends"),
    ("vidbyte.harnesses.native", "get_deepseek_balance"), ("vidbyte.harnesses.native.backends", "get_deepseek_balance"),
    ("vidbyte.lib.process", "ManagedProcess"),
]
DELETED_FILES = [
    "vidbyte/tools/builtins/native_host_tool.py", "vidbyte/tools/toolsets/grok.py", "vidbyte/tools/toolsets/opencode.py",
    "vidbyte/tools/toolsets/muse.py", "vidbyte/tools/toolsets/harness_backends.py", "vidbyte/lib/configs/harness_backends.py",
    "vidbyte/lib/dataclasses/harness_backends.py", "vidbyte/lib/enums/harness_backends.py", "vidbyte/harnesses/native/grok/host.py",
    "vidbyte/harnesses/native/grok/turn.py", "vidbyte/harnesses/native/grok/cli.py", "vidbyte/harnesses/native/opencode/client.py",
    "vidbyte/harnesses/native/opencode/host.py", "vidbyte/harnesses/native/opencode/server.py", "vidbyte/harnesses/native/opencode/turn.py",
    "vidbyte/harnesses/native/muse/host.py", "vidbyte/harnesses/native/muse/turn.py", "vidbyte/harnesses/native/hostkit/peers.py",
    "vidbyte/harnesses/native/hostkit/turns.py", "vidbyte/lib/process/managed.py", "vidbyte/lib/dataclasses/grok.py",
    "vidbyte/lib/dataclasses/opencode.py", "vidbyte/lib/dataclasses/muse.py", "vidbyte/lib/enums/native_hosts.py",
    "vidbyte/lib/constants/native_hosts.py", "vidbyte/lib/dataclasses/native_hosts.py",
]
DELETED_PACKAGES = ["vidbyte/tools/builtins/grok", "vidbyte/tools/builtins/opencode", "vidbyte/tools/builtins/muse", "vidbyte/tools/builtins/harness_backends", "vidbyte/harnesses/native/backends"]
OLD_SPEC_FOLDER = "docs/spec/native-grok-opencode-meta-hosts"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, check=False)


def optional_merge_base() -> str | None:
    try:
        found = git("merge-base", "origin/main", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return None
    return found.stdout.strip() if found.returncode == 0 and found.stdout.strip() else None


def merge_base() -> str:
    base = optional_merge_base()
    if base is None:
        pytest.skip("origin/main is not available in this checkout (a shallow CI clone has no main ref)")
    return base


def literal_all(source: str) -> list[str]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            return list(ast.literal_eval(node.value))
    raise AssertionError("no literal __all__")


def importable(module: str, name: str) -> bool:
    try:
        exec(f"from {module} import {name}", {})
    except ImportError:
        return False
    return True


def test_native_package_exports_exactly_the_thread_functions_helpers_skills_and_their_records(api) -> None:
    # INV-1 / D-22, amended by the helpers spec INV-1: one literal
    # __all__ with the nine functions, the 47 helpers and skill
    # functions, the records, error and config enums (68 names); the
    # subpackages export their own functions (25 / 15 / 16).
    native = api.native
    assert sorted(native.__all__) == sorted(EXPECTED_EXPORTS) and len(native.__all__) == len(EXPECTED_EXPORTS)
    assert native.NativeThreadResult is api.NativeThreadResult
    assert (native.GrokThreadConfig, native.OpencodeThreadConfig, native.MuseThreadConfig) == (api.GrokThreadConfig, api.OpencodeThreadConfig, api.MuseThreadConfig)
    assert native.NativeThreadError is api.NativeThreadError
    assert (native.GrokPermissionMode, native.GrokReasoningEffort, native.MuseReasoningEffort) == (api.enums.GrokPermissionMode, api.enums.GrokReasoningEffort, api.enums.MuseReasoningEffort)
    assert len(EXPECTED_EXPORTS) == 68 and len(native.__all__) == 68
    for harness in ("grok", "opencode", "muse"):
        subpackage = importlib.import_module(f"vidbyte.harnesses.native.{harness}")
        names = SUBPACKAGE_EXPORTS[harness]
        assert sorted(subpackage.__all__) == sorted(names) and len(subpackage.__all__) == len(names), harness
        for name in names:
            assert getattr(subpackage, name) is getattr(native, name), name


def test_thread_functions_are_coroutines_with_the_contract_signature(api) -> None:
    # §8.5: prompt (after thread_id for continue and fork), then
    # keyword-only api_key, workspace, model, skills, config.
    positional = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    for name in FUNCTIONS:
        function = getattr(api.native, name)
        assert inspect.iscoroutinefunction(function), name
        parameters = list(inspect.signature(function).parameters.values())
        leading = ["prompt"] if name.startswith("run_") else ["thread_id", "prompt"]
        assert [parameter.name for parameter in parameters] == [*leading, "api_key", "workspace", "model", "skills", "config"], name
        assert all(parameter.kind in positional and parameter.default is inspect.Parameter.empty for parameter in parameters[: len(leading)]), name
        keywords = {parameter.name: parameter for parameter in parameters[len(leading) :]}
        assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in keywords.values()), name
        assert keywords["api_key"].default is inspect.Parameter.empty and keywords["workspace"].default is inspect.Parameter.empty, name
        if "opencode" in name:
            assert keywords["model"].default is inspect.Parameter.empty, f"{name}: opencode requires model (FR-8)"
        else:
            assert keywords["model"].default is None, name
        assert tuple(keywords["skills"].default) == () and keywords["config"].default is None, name


def test_vocabularies_are_str_enums_carrying_the_vendor_values(lib_api) -> None:
    # D-11 / R-3: every enum is a StrEnum exported from
    # vidbyte.lib.enums, and its values match the CLIs exactly.
    for name, values in EXPECTED_ENUMS.items():
        cls = getattr(lib_api.enums, name)
        assert issubclass(cls, enum.StrEnum), f"{name} must be a StrEnum (Python 3.11 formats a (str, Enum) member as Class.MEMBER)"
        assert [member.value for member in cls] == values, name
        assert all(str(member) == member.value and f"{member}" == member.value for member in cls), name
        assert getattr(lib_api.enums_package, name) is cls, f"{name} is not exported from vidbyte.lib.enums"
    assert [member.name for member in lib_api.enums.NativeEnvironmentVariable] == EXPECTED_ENUMS["NativeEnvironmentVariable"]
    for cls, values in ((lib_api.CliOptionStyle, ["joined", "separate"]), (lib_api.ProcessLaunchFailure, ["not_found", "permission_denied", "os_error"])):
        assert issubclass(cls, enum.StrEnum) and [member.value for member in cls] == values
        assert getattr(lib_api.enums_package, cls.__name__) is cls


def test_failure_codes_keep_main_and_append_exactly_the_32_harness_codes(lib_api) -> None:
    # INV-22 / D-10 and the helpers spec INV-22: main's members
    # unchanged in name, value and order; the harness tail is GROK_,
    # OPENCODE_, MUSE_ x 9 problems, MUSE_WSL_UNAVAILABLE, then the
    # three COMMAND_NOT_RUN codes and GROK_STORE_UNREADABLE.
    members = list(lib_api.FailureCode)
    names = [member.name for member in members]
    tail = members[names.index("RULE_EVALUATION_FAILED") + 1 :]
    assert [member.value for member in tail] == NEW_FAILURE_CODES
    assert [member.name for member in tail] == [code.upper().replace(".", "_") for code in NEW_FAILURE_CODES]
    base = optional_merge_base()
    if base is None:
        return
    shown = git("show", f"{base}:vidbyte/lib/enums/failure.py")
    assert shown.returncode == 0, shown.stderr
    tree = ast.parse(shown.stdout)
    enum_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FailureCode")
    main_members = [(node.targets[0].id, node.value.value) for node in enum_class.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
    assert [(member.name, member.value) for member in members[: len(main_members)]] == main_members
    # Post-merge invariant (helpers spec §12.3 row 35): no main count is
    # hardcoded; the branch appends exactly the harness codes main does
    # not hold yet, in NEW_FAILURE_CODES order.
    main_values = {value for _, value in main_members}
    assert [member.value for member in members[len(main_members) :]] == [code for code in NEW_FAILURE_CODES if code not in main_values]


def test_contract_constants_hold_the_spec_values(lib_api) -> None:
    # §8.5: the constants the spec names as contract, which tests read
    # or monkeypatch.
    for name, value in CONTRACT_CONSTANTS.items():
        assert getattr(lib_api.constants, name) == value, name
    assert lib_api.GrokThreadConfig().timeout_seconds == lib_api.constants.NATIVE_THREAD_DEFAULT_SECONDS
    assert lib_api.MuseThreadConfig().muse_path == lib_api.constants.MUSE_DEFAULT_PATH


def test_old_public_names_no_longer_import(lib_api) -> None:
    # AC-13 / INV-19: the hosts, tools, backends, the old error and the
    # managed process are gone.
    still_there = [f"{module}.{name}" for module, name in OLD_NAMES if importable(module, name)]
    assert still_there == []
    assert sorted(lib_api.process.__all__) == ["CliArgv", "CliRunner", "ProcessStopper"]


def test_rejected_design_files_are_deleted() -> None:
    # AC-13 / §12.3 rows 1-6, 9, 11-19, 23, 28, 36: the files of the
    # rejected design are gone from the tree.
    left = [path for path in DELETED_FILES if (REPO_ROOT / path).exists()]
    left += [path for path in DELETED_PACKAGES if any((REPO_ROOT / path).rglob("*.py"))]
    left += [OLD_SPEC_FOLDER] if any(path.is_file() for path in (REPO_ROOT / OLD_SPEC_FOLDER).rglob("*")) else []
    assert left == []


def test_branch_leaves_the_tools_and_configs_packages_as_main_has_them() -> None:
    # AC-13 / INV-21: no file of vidbyte.tools or vidbyte.lib.configs,
    # and nothing of the old spec folder, differs from main.
    base = merge_base()
    scoped = ("vidbyte/tools", "vidbyte/lib/configs", OLD_SPEC_FOLDER)
    changed = git("diff", "--name-only", base, "--", *scoped)
    assert changed.returncode == 0, changed.stderr
    untracked = git("ls-files", "--others", "--exclude-standard", "--", *scoped)
    assert changed.stdout.split() == [] and untracked.stdout.split() == []


def test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded() -> None:
    # INV-23: a fresh `import vidbyte` starts nothing, does not import
    # vidbyte.harnesses.native, and keeps main's root __all__.
    probe = textwrap.dedent(
        """
        import json, subprocess, sys
        started = []
        original = subprocess.Popen.__init__
        def record(self, *args, **kwargs):
            started.append(repr(args[:1]))
            return original(self, *args, **kwargs)
        subprocess.Popen.__init__ = record
        import vidbyte
        print(json.dumps({"native": "vidbyte.harnesses.native" in sys.modules, "started": started, "all": list(vidbyte.__all__)}))
        """
    )
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    finished = subprocess.run([sys.executable, "-c", probe], cwd=REPO_ROOT, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL, env=environment, check=False)
    assert finished.returncode == 0, finished.stderr[-2000:]
    report = json.loads(finished.stdout.strip().splitlines()[-1])
    assert report["started"] == [] and report["native"] is False
    base = optional_merge_base()
    if base is not None:
        assert report["all"] == literal_all(git("show", f"{base}:vidbyte/__init__.py").stdout)
