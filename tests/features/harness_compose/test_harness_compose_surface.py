"""FILE: tests/features/harness_compose/test_harness_compose_surface.py

PURPOSE: The public surface of compose (AC-22, INV-1, INV-24, INV-27, INV-32, INV-33, §8.5): the literal 42-name `__all__`, re-exports that are the very `vidbyte.lib` objects, the seven enum exports and the other lib exports, the unchanged existing surfaces, the exact vocabularies and contract constants, every function's kind and parameters, the alias signatures, the ThreadComposeError packet, a side-effect-free import, the import layering, and no sleep in any compose module (INV-22).
ROLE IN CODEBASE: Start here when a public name, a signature, an enum member or a constant drifts from spec §8.5.
ARCHITECTURE NOTE: Expected names, values and parameters are written out here from the spec, never read from the code under test. The import probes run in a fresh interpreter with `-B`, so no bytecode write is mistaken for a file the import touched. The layering and sleep checks read the source with `ast` and never import it.
FUNCTION INVENTORY: compose_modules and imported_modules read the compose sources; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: When §8.5 adds or renames a public name, change the expected tables here in the same commit as the spec.
WHAT NOT TO DO IN THIS FILE: Do not read an expected value from the module under test; do not compare free text of likely causes or next steps.
KNOWN EDGE CASES: `inspect.iscoroutinefunction` is False for the callable alias instances themselves, so their coroutine nature is checked on `type(alias).__call__` and by calling one (spec §13 Python facts). Calling an alias without awaiting it binds nothing, so placeholder arguments are safe there.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-1, INV-22, INV-24, INV-27, INV-32, INV-33, §6.2 AC-22, §8.5, §9.2, §12.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_surface.py
"""

from __future__ import annotations

import ast
import enum
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

import pytest

COMPOSE_FUNCTIONS = ("bind_thread", "bind_continue", "chain_threads", "verify_with", "handoff_thread", "run_staged_threads", "run_ensemble", "capture_diff", "in_worktree", "parse_json_answer")
PAIR_ALIASES = {
    "run_grok_then_opencode": ("grok", "opencode"),
    "run_grok_then_muse": ("grok", "muse"),
    "run_opencode_then_grok": ("opencode", "grok"),
    "run_opencode_then_muse": ("opencode", "muse"),
    "run_muse_then_grok": ("muse", "grok"),
    "run_muse_then_opencode": ("muse", "opencode"),
}
TRIO_ALIASES = {
    "run_grok_verify_with_opencode_and_muse": ("writer", "opencode", "muse"),
    "run_opencode_verify_with_grok_and_muse": ("writer", "grok", "muse"),
    "run_muse_verify_with_grok_and_opencode": ("writer", "grok", "opencode"),
}
COMPOSE_RECORDS = ("ThreadStep", "StepOutcome", "WorkspaceDiff", "JsonAnswer", "ThreadVerdict", "ChainResult", "VerifyResult", "HandoffResult", "StageSpec", "StageAttempt", "StageOutcome", "StagedResult")
ENSEMBLE_RECORDS = ("EnsembleRoster", "EnsembleRole", "EnsemblePlan", "EnsembleRound", "EnsembleSelection", "EnsembleResult")
COMPOSE_ENUMS = ("VerdictDecision", "StageDecision", "EnsembleStage", "ThreadComposeProblem")
LIB_ENUMS = ("ComposeField", "ComposePrompt", "EnsembleStage", "GitFlag", "StageDecision", "ThreadComposeProblem", "VerdictDecision")
NATIVE_ALL = (
    "GrokPermissionMode", "GrokReasoningEffort", "GrokThreadConfig", "MuseReasoningEffort", "MuseThreadConfig", "NativeThreadError", "NativeThreadResult",
    "OpencodeThreadConfig", "continue_grok_thread", "continue_muse_thread", "continue_opencode_thread", "fork_grok_thread", "fork_muse_thread",
    "fork_opencode_thread", "run_grok_thread", "run_muse_thread", "run_opencode_thread",
)
ENUM_VALUES = {
    "VerdictDecision": {"APPROVE": "approve", "REJECT": "reject"},
    "StageDecision": {"RETRY": "retry", "RAISE_EFFORT": "raise_effort", "ABORT": "abort"},
    "EnsembleStage": {"PLAN": "plan", "PROPOSE": "propose", "SELECT": "select", "IMPLEMENT": "implement"},
    "ThreadComposeProblem": {
        "NOT_A_GIT_REPOSITORY": "not_a_git_repository", "GIT_UNAVAILABLE": "git_unavailable", "GIT_FAILED": "git_failed",
        "WORKTREE_FAILED": "worktree_failed", "READER_CHANGED_WORKSPACE": "reader_changed_workspace",
    },
    "GitFlag": {
        "NO_OPTIONAL_LOCKS": "--no-optional-locks", "CONFIG": "-c", "SHOW_TOPLEVEL": "--show-toplevel", "VERIFY": "--verify", "QUIET": "--quiet",
        "ALL": "-A", "NAME_ONLY": "--name-only", "NUL_TERMINATED": "-z", "NO_RENAMES": "--no-renames", "NO_COLOR": "--no-color",
        "NO_EXT_DIFF": "--no-ext-diff", "NO_TEXTCONV": "--no-textconv", "DETACH": "--detach", "NO_CHECKOUT": "--no-checkout", "UPDATE": "-u",
        "RESET": "--reset", "FORCE": "--force",
    },
}
PROMPT_STEMS = (
    "planner_system", "planner_turn", "plan_schema", "role_system", "role_turn", "fork_turn", "selector_system", "selector_round_turn",
    "selector_final_turn", "round_schema", "selection_schema", "proposal_block", "implementer_system", "implementer_turn", "chain_turn",
    "verify_turn", "verdict_schema", "handoff_summary", "handoff_seed", "json_answer", "json_repair", "truncation_note",
)
FIELD_NAMES = (
    "roles", "task", "role_name", "identity", "personality", "expertise", "knowledge", "skills", "goal", "minimum", "maximum", "task_analysis",
    "roster_strategy", "coverage_summary", "instructions", "turn", "round", "surviving", "target", "candidates", "number", "text", "proposal",
    "approach", "rationale", "guidance", "prompt", "previous", "diff", "files", "summary", "schema", "problem", "omitted",
)
EMPTY = inspect.Parameter.empty
POSITIONAL = inspect.Parameter.POSITIONAL_OR_KEYWORD
KEYWORD = inspect.Parameter.KEYWORD_ONLY
PARAMETERS = {
    "bind_thread": [("function", POSITIONAL, EMPTY), ("api_key", KEYWORD, EMPTY), ("workspace", KEYWORD, EMPTY), ("model", KEYWORD, None), ("skills", KEYWORD, ()), ("config", KEYWORD, None)],
    "bind_continue": [("function", POSITIONAL, EMPTY), ("thread_id", POSITIONAL, EMPTY), ("api_key", KEYWORD, EMPTY), ("workspace", KEYWORD, EMPTY), ("model", KEYWORD, None), ("skills", KEYWORD, ()), ("config", KEYWORD, None)],
    "chain_threads": [("steps", POSITIONAL, EMPTY), ("template", POSITIONAL, None), ("prompt", KEYWORD, EMPTY)],
    "verify_with": [("writer", POSITIONAL, EMPTY), ("verifiers", POSITIONAL, EMPTY), ("prompt", KEYWORD, EMPTY)],
    "handoff_thread": [("from_thread", POSITIONAL, EMPTY), ("to_step", POSITIONAL, EMPTY)],
    "run_staged_threads": [("stages", POSITIONAL, EMPTY)],
    "run_ensemble": [("prompt", POSITIONAL, EMPTY), ("roster", POSITIONAL, EMPTY)],
    "capture_diff": [("workspace", POSITIONAL, EMPTY)],
    "in_worktree": [("workspace", POSITIONAL, EMPTY)],
    "parse_json_answer": [("step", POSITIONAL, EMPTY), ("prompt", POSITIONAL, EMPTY), ("schema", KEYWORD, EMPTY), ("parse", KEYWORD, EMPTY)],
}
COROUTINE_FUNCTIONS = ("chain_threads", "verify_with", "handoff_thread", "run_staged_threads", "run_ensemble", "parse_json_answer")
PLAIN_FUNCTIONS = ("bind_thread", "bind_continue", "capture_diff", "in_worktree")
PLUMBING_MODULES = ("steps", "calls", "texts", "git", "workspace", "answers")
COMPOSITE_MODULES = ("chain", "verify", "handoff", "stages", "ensemble", "selection")
FORBIDDEN_FOR_COMPOSE = ("vidbyte.harnesses.native.hostkit", "vidbyte.tools", "vidbyte.prompts")
NEW_LIB_MODULES = ("vidbyte/lib/enums/native_compose.py", "vidbyte/lib/constants/native_compose.py", "vidbyte/lib/dataclasses/native_compose.py", "vidbyte/lib/dataclasses/native_ensemble.py", "vidbyte/lib/util/json_text.py")
CLEARED_VARIABLES = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX", "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
}
SIDE_EFFECT_PROBE = """
import json, os, sys
import vidbyte.harnesses.native
compose_dir = os.path.normcase(os.path.join(os.path.dirname(vidbyte.harnesses.native.__file__), "compose"))
watched = {"subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn", "os.exec", "os.mkdir", "os.rmdir", "os.remove", "os.rename", "os.replace", "os.truncate", "os.chdir", "shutil.rmtree", "shutil.copyfile", "shutil.move", "tempfile.mkdtemp", "tempfile.mkstemp"}
events = []
write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
def hook(event, args):
    if event in watched:
        events.append([event, repr(args)[:300]])
    elif event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.normcase(os.fsdecode(args[0]))
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        writing = (isinstance(mode, str) and any(letter in mode for letter in "wax+")) or (mode is None and bool(flags & write_flags))
        if writing or (path.startswith(compose_dir) and not path.endswith((".py", ".pyc"))):
            events.append([event, path, repr(mode)])
sys.addaudithook(hook)
import vidbyte.harnesses.native.compose
print(json.dumps(events))
"""
ROOT_IMPORT_PROBE = "import json, sys\nimport vidbyte\nprint(json.dumps(sorted(name for name in sys.modules if name.startswith('vidbyte.harnesses.native'))))\n"


def compose_modules(repo_root: Path) -> dict[str, Path]:
    folder = repo_root / "vidbyte" / "harnesses" / "native" / "compose"
    return {path.stem: path for path in sorted(folder.glob("*.py"))}


def imported_modules(path: Path, package: str) -> set[str]:
    # Every module an `import` or `from ... import` names, relative
    # imports resolved against package, TYPE_CHECKING blocks included.
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                prefix = ".".join(base)
                module = f"{prefix}.{node.module}" if node.module else prefix
            else:
                module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def run_probe(source: str, repo_root: Path) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONPATH": str(repo_root), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-B", "-c", source], cwd=str(repo_root), env=environment, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL, check=False)


def test_compose_exports_exactly_the_42_names_as_the_lib_objects(compose_api) -> None:
    # INV-1 / AC-22: a subpackage with a literal 42-name __all__; the
    # records, enums and error are the very vidbyte.lib objects.
    compose = compose_api.compose
    expected = [*COMPOSE_FUNCTIONS, *PAIR_ALIASES, *TRIO_ALIASES, *COMPOSE_RECORDS, *ENSEMBLE_RECORDS, *COMPOSE_ENUMS, "ThreadComposeError"]
    assert len(expected) == 42
    assert hasattr(compose, "__path__"), "compose is a subpackage"
    assert isinstance(compose.__all__, (list, tuple))
    assert len(compose.__all__) == len(set(compose.__all__)) == 42
    assert sorted(compose.__all__) == sorted(expected)
    for name in COMPOSE_RECORDS:
        assert getattr(compose, name) is getattr(compose_api.records, name), name
    for name in ENSEMBLE_RECORDS:
        assert getattr(compose, name) is getattr(compose_api.ensemble, name), name
    for name in COMPOSE_ENUMS:
        assert getattr(compose, name) is getattr(compose_api.enums, name), name
    assert compose.ThreadComposeError is compose_api.errors.ThreadComposeError
    assert compose_api.errors.ThreadComposeError is __import__("vidbyte.lib.errors.base", fromlist=["ThreadComposeError"]).ThreadComposeError


def test_lib_packages_export_the_new_enums_error_and_decoder(compose_api) -> None:
    # INV-1 / AC-22: seven enums from vidbyte.lib.enums, the error from
    # vidbyte.lib.errors, JsonText from vidbyte.lib.util.
    for name in LIB_ENUMS:
        assert name in compose_api.enums_package.__all__, name
        assert getattr(compose_api.enums_package, name) is getattr(compose_api.enums, name), name
    assert "ThreadComposeError" in compose_api.errors.__all__
    assert "JsonText" in compose_api.util.__all__
    assert compose_api.util.JsonText is compose_api.JsonText
    assert issubclass(compose_api.ThreadComposeError, compose_api.AgentExecutionError)


def test_existing_public_surfaces_are_unchanged(compose_api) -> None:
    # INV-27 / INV-33: native keeps its 17 names and gains no compose
    # name; each harness subpackage keeps its three; the root package
    # exports no compose name; the process package is untouched.
    native = compose_api.native
    assert sorted(native.__all__) == sorted(NATIVE_ALL)
    compose_names = set(compose_api.compose.__all__)
    assert not compose_names & set(native.__all__)
    for harness in ("grok", "opencode", "muse"):
        subpackage = __import__(f"vidbyte.harnesses.native.{harness}", fromlist=["__all__"])
        assert sorted(subpackage.__all__) == sorted(f"{verb}_{harness}_thread" for verb in ("run", "continue", "fork"))
    root = __import__("vidbyte")
    assert not compose_names & set(getattr(root, "__all__", ()))
    assert __import__("vidbyte.lib.process", fromlist=["__all__"]).__all__ == ["CliArgv", "CliRunner", "ProcessStopper"]


def test_vocabularies_are_exactly_the_spec_members(compose_api) -> None:
    # §8.5 / §9.2: every new enum is a
    # StrEnum with exactly its members.
    enums = compose_api.enums
    for name in LIB_ENUMS:
        assert issubclass(getattr(enums, name), enum.StrEnum), name
    for name, members in ENUM_VALUES.items():
        assert {member.name: member.value for member in getattr(enums, name)} == members, name
    assert sorted(member.value for member in enums.ComposePrompt) == sorted(PROMPT_STEMS)
    assert len(enums.ComposePrompt) == 22
    assert sorted(member.value for member in enums.ComposeField) == sorted(FIELD_NAMES)
    assert len(enums.ComposeField) == 34


def test_contract_constants_hold_the_spec_values(compose_api) -> None:
    # §8.5 constants block: counts, caps, texts, prefixes and the
    # variables removed from every git child (§9.3).
    constants, enums, threads = compose_api.constants, compose_api.enums, compose_api.threads_constants
    expected = {
        "COMPOSE_MIN_CHAIN_STEPS": 2, "COMPOSE_MAX_STEPS": 25, "COMPOSE_MAX_VERIFIERS": 10, "COMPOSE_MAX_STAGES": 25,
        "STAGE_DEFAULT_RETRIES": 1, "STAGE_MAX_RETRIES": 3, "STAGE_MAX_LADDER": 4,
        "ENSEMBLE_MIN_PROPOSERS": 1, "ENSEMBLE_MAX_PROPOSERS": 10, "ENSEMBLE_NARROWING_FACTOR": 5, "ENSEMBLE_MIN_APPROACHES": 2, "ENSEMBLE_MAX_APPROACHES": 5,
        "ENSEMBLE_ROLE_NAME_MAX_CHARS": threads.NATIVE_NAME_MAX_CHARS, "COMPOSE_ANSWER_TEXT_MAX_CHARS": threads.NATIVE_RESULT_TEXT_MAX_CHARS,
        "COMPOSE_VERDICT_MAX_FINDINGS": 50, "COMPOSE_JSON_REPAIR_TURNS": 2, "COMPOSE_PROBLEM_MAX_CHARS": 2000,
        "COMPOSE_DIFF_MAX_CHARS": threads.NATIVE_RESULT_TEXT_MAX_CHARS, "COMPOSE_DIFF_MAX_FILES": 2000, "COMPOSE_GIT_TIMEOUT_SECONDS": 120.0,
        "COMPOSE_GIT_MAX_OUTPUT_BYTES": 16_777_216, "COMPOSE_GIT_MESSAGE_MAX_CHARS": 2000, "COMPOSE_MESSAGE_MAX_FILES": 10,
        "COMPOSE_PROMPTS_FOLDER": "prompts", "COMPOSE_PROMPT_SUFFIX": ".md", "COMPOSE_PROMPT_ENCODING": "utf-8", "COMPOSE_PROMPT_SEPARATOR": "\n\n",
        "COMPOSE_REDACTED_KEY": "[redacted]", "COMPOSE_GIT_PROGRAM": "git", "COMPOSE_GIT_SETTINGS": ("core.fsmonitor=false", "core.safecrlf=false"),
        "COMPOSE_GIT_HEAD": "HEAD", "COMPOSE_GIT_UNBORN_EXIT_CODE": 1, "COMPOSE_GIT_INDEX_VARIABLE": "GIT_INDEX_FILE", "COMPOSE_GIT_INDEX_FILE_NAME": "index",
        "COMPOSE_WORKTREE_PREFIX": "vidbyte-compose-worktree-", "COMPOSE_INDEX_PREFIX": "vidbyte-compose-index-", "COMPOSE_NUL": "\x00",
        "COMPOSE_PROMPT_PARAMETER": "prompt", "COMPOSE_WRITER_PARAMETER": "writer",
        "COMPOSE_GIT_REV_PARSE": "rev-parse", "COMPOSE_GIT_READ_TREE": "read-tree", "COMPOSE_GIT_ADD": "add", "COMPOSE_GIT_WRITE_TREE": "write-tree",
        "COMPOSE_GIT_DIFF": "diff", "COMPOSE_GIT_WORKTREE": "worktree", "COMPOSE_GIT_WORKTREE_ADD": "add", "COMPOSE_GIT_WORKTREE_REMOVE": "remove",
    }
    for name, value in expected.items():
        assert getattr(constants, name) == value, f"{name} = {getattr(constants, name)!r}, spec says {value!r}"
    assert set(constants.COMPOSE_GIT_CLEARED_VARIABLES) == CLEARED_VARIABLES and len(constants.COMPOSE_GIT_CLEARED_VARIABLES) == 15
    assert constants.STAGE_UNCLASSIFIED_DECISION is enums.StageDecision.ABORT
    assert set(constants.COMPOSE_READER_GROK_MODES) == {compose_api.GrokPermissionMode.PLAN, compose_api.GrokPermissionMode.DEFAULT}
    field = enums.ComposeField
    assert set(constants.CHAIN_TEMPLATE_FIELDS) == {field.PROMPT, field.PREVIOUS, field.DIFF}
    assert set(constants.CHAIN_REQUIRED_FIELDS) == {field.PREVIOUS}
    assert set(constants.STAGE_TEMPLATE_FIELDS) == {field.PREVIOUS}
    assert isinstance(constants.STAGE_DECISIONS, MappingProxyType) and isinstance(constants.COMPOSE_PROMPT_FIELDS, MappingProxyType)
    for table in (constants.THREAD_COMPOSE_SUMMARIES, constants.THREAD_COMPOSE_LIKELY_CAUSES, constants.THREAD_COMPOSE_NEXT_STEPS):
        assert set(table) == set(enums.ThreadComposeProblem)
        assert all(isinstance(text, str) and text.strip() for text in table.values())
    problem = enums.ThreadComposeProblem.GIT_FAILED
    assert constants.THREAD_COMPOSE_ADD_LIKELY_CAUSE.strip() and constants.THREAD_COMPOSE_ADD_LIKELY_CAUSE != constants.THREAD_COMPOSE_LIKELY_CAUSES[problem]
    assert constants.THREAD_COMPOSE_ADD_NEXT_STEP.strip() and constants.THREAD_COMPOSE_ADD_NEXT_STEP != constants.THREAD_COMPOSE_NEXT_STEPS[problem]


@pytest.mark.parametrize("name", COMPOSE_FUNCTIONS)
def test_each_function_has_its_kind_and_exact_parameters(compose_api, tmp_path, name) -> None:
    # INV-1 / §8.5: composites and parse_json_answer are coroutine
    # functions; the binders are plain; capture_diff and in_worktree are
    # plain functions returning async context managers.
    function = getattr(compose_api.compose, name)
    parameters = [(parameter.name, parameter.kind, parameter.default) for parameter in inspect.signature(function).parameters.values()]
    assert parameters == PARAMETERS[name], f"{name}{inspect.signature(function)}"
    assert inspect.iscoroutinefunction(function) is (name in COROUTINE_FUNCTIONS), name
    assert not inspect.isasyncgenfunction(function)
    if name in ("capture_diff", "in_worktree"):
        manager = function(tmp_path)
        assert hasattr(manager, "__aenter__") and hasattr(manager, "__aexit__"), name
        assert not inspect.iscoroutine(manager)


@pytest.mark.parametrize("name", [*PAIR_ALIASES, *TRIO_ALIASES])
def test_each_alias_has_its_exact_signature_and_returns_a_coroutine(compose_api, name) -> None:
    # INV-24 / AC-2: pairs are (prompt, *, <a>, <b>), trios
    # (prompt, *, writer, <x>, <y>); calling one returns a coroutine.
    alias = getattr(compose_api.compose, name)
    names = PAIR_ALIASES.get(name) or TRIO_ALIASES[name]
    parameters = [(parameter.name, parameter.kind, parameter.default) for parameter in inspect.signature(alias).parameters.values()]
    assert parameters == [("prompt", POSITIONAL, EMPTY), *[(step, KEYWORD, EMPTY) for step in names]], f"{name}{inspect.signature(alias)}"
    assert callable(alias) and not inspect.isfunction(alias), "aliases are callable instances generated from the composites"
    assert inspect.iscoroutinefunction(type(alias).__call__)
    pending = alias("Do the work.", **{step: None for step in names})
    try:
        assert inspect.iscoroutine(pending)
    finally:
        pending.close()


def test_thread_compose_error_carries_the_a003_packet(compose_api) -> None:
    # §8.5 / §12.3 row 9: error_kind is the problem value; details
    # holds the eight A003 fields and never the diff text or the result;
    # safe_runtime_details holds problem, workspace and git_message.
    api = compose_api
    marker = "DIFF-TEXT-MARKER-5b1f"
    diff = api.records.WorkspaceDiff(files=("a.txt",), text=marker, truncated=False)
    result = object()
    error = api.ThreadComposeError("The snapshot failed.", problem=api.enums.ThreadComposeProblem.GIT_FAILED, workspace="C:/code/ws", likely_cause="A cause.", next_step="A step.", git_message="fatal: boom", diff=diff, result=result)
    assert str(error) == "The snapshot failed."
    assert error.problem is api.enums.ThreadComposeProblem.GIT_FAILED
    assert (error.workspace, error.likely_cause, error.next_step, error.git_message) == ("C:/code/ws", "A cause.", "A step.", "fatal: boom")
    assert error.diff is diff and error.result is result
    assert error.error_kind == "git_failed"
    assert tuple(api.ThreadComposeError.DIAGNOSTIC_FIELDS) == ("error_kind", "expected", "actual", "safe_runtime_details", "likely_causes", "repair_approaches", "related_docs", "relevant_tests")
    assert set(error.details) == set(api.ThreadComposeError.DIAGNOSTIC_FIELDS)
    assert error.related_docs == ("vidbyte/harnesses/README.md",)
    assert error.relevant_tests == ("tests/features/harness_compose",)
    assert "A cause." in error.likely_causes and "A step." in error.repair_approaches
    assert error.safe_runtime_details["problem"] == "git_failed"
    assert error.safe_runtime_details["workspace"] == "C:/code/ws"
    assert error.safe_runtime_details["git_message"] == "fatal: boom"
    assert marker not in repr(error.details) and marker not in repr(error.safe_runtime_details)
    plain = api.ThreadComposeError("No diff.", problem=api.enums.ThreadComposeProblem.WORKTREE_FAILED, workspace="C:/code/ws", likely_cause="A cause.", next_step="A step.")
    assert plain.git_message is None and plain.diff is None and plain.result is None


def test_importing_compose_starts_no_process_reads_no_file_and_touches_no_folder(compose_api, pack) -> None:
    # INV-1: the import itself has no side effects; prompts load later,
    # off the event loop.
    finished = run_probe(SIDE_EFFECT_PROBE, pack.REPO_ROOT)
    assert finished.returncode == 0, finished.stderr[-3000:]
    assert json.loads(finished.stdout.strip().splitlines()[-1]) == []


def test_import_vidbyte_loads_neither_native_nor_compose(compose_api, pack) -> None:
    # INV-27: the root package stays free of the native harnesses.
    finished = run_probe(ROOT_IMPORT_PROBE, pack.REPO_ROOT)
    assert finished.returncode == 0, finished.stderr[-3000:]
    assert json.loads(finished.stdout.strip().splitlines()[-1]) == []


def test_compose_and_new_lib_modules_respect_the_layers(compose_api, pack) -> None:
    # INV-32 / NFR-3: compose never imports hostkit, vidbyte.tools,
    # vidbyte.prompts or the root package; plumbing never imports a
    # composite; the new lib modules import nothing above vidbyte.lib,
    # and json_text nothing from vidbyte at all.
    modules = compose_modules(pack.REPO_ROOT)
    assert set(PLUMBING_MODULES) | set(COMPOSITE_MODULES) | {"__init__"} <= set(modules), sorted(modules)
    package = "vidbyte.harnesses.native.compose"
    for stem, path in modules.items():
        imported = imported_modules(path, package)
        assert "vidbyte" not in imported, f"{stem} imports the root vidbyte package"
        for forbidden in FORBIDDEN_FOR_COMPOSE:
            assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported), f"{stem} imports {forbidden}"
        if stem in PLUMBING_MODULES:
            composites = {f"{package}.{name}" for name in COMPOSITE_MODULES}
            assert not any(name in composites or any(name.startswith(item + ".") for item in composites) for name in imported), f"plumbing module {stem} imports a composite"
    for relative in NEW_LIB_MODULES:
        path = pack.REPO_ROOT / relative
        package_name = ".".join(Path(relative).with_suffix("").parts[:-1])
        imported = {name for name in imported_modules(path, package_name) if name == "vidbyte" or name.startswith("vidbyte.")}
        assert all(name.startswith("vidbyte.lib.") for name in imported), f"{relative} imports above vidbyte.lib: {sorted(imported)}"
        if relative.endswith("json_text.py"):
            assert imported == set(), f"json_text imports SDK modules: {sorted(imported)}"


def test_no_compose_module_sleeps(compose_api, pack) -> None:
    # INV-21 / INV-22: no sleep and no backoff anywhere in compose.
    for stem, path in compose_modules(pack.REPO_ROOT).items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("asyncio", "time"):
                assert all(alias.name != "sleep" for alias in node.names), f"{stem} imports sleep"
            if isinstance(node, ast.Call):
                target = node.func
                name = target.attr if isinstance(target, ast.Attribute) else target.id if isinstance(target, ast.Name) else ""
                assert name != "sleep", f"{stem} line {node.lineno} calls sleep"
