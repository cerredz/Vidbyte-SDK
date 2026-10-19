"""FILE: tests/features/codex_host/test_codex_host_feature_structure.py

PURPOSE: Proves the shape the first-class-features spec gives the code: the twenty-five new methods are inherited by CodexHost from four SDK-free mixins over CodexHostCore with the section 8.5 signatures, importing the host loads no openai-codex and none of the three SDK-loading collaborators, the five SDK-free modules import openai-codex only under TYPE_CHECKING, the collaborators carry the section 8.5 interface names, and every touched or new file stays within its INV-47 ceiling while the two files the spec freezes keep their bytes.
ROLE IN CODEBASE: Structure layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md D-1, D-2, D-10, FR-34, INV-45, INV-47, INV-50, INV-54, NFR-1, NFR-2, AC-38, AC-40). The import probe and the source scans run on CI; the collaborator interface class needs openai-codex.
ARCHITECTURE NOTE: Import safety is checked in a fresh `python -I` interpreter with openai_codex blocked by a None entry in sys.modules, as test_codex_host_packaging.py does, because this process may already have loaded the SDK. Source files are read with CRLF turned into LF, which equals the committed blob on a core.autocrlf checkout and on Linux alike.
COMMON MODIFICATION PATTERNS: When section 8.5 changes a method signature, change HOST_SIGNATURES; when INV-47 changes a ceiling, change LINE_CEILINGS.
KNOWN EDGE CASES: The line counts are counted as wc -l does (newline characters), after CRLF is turned into LF. vidbyte/lib/dataclasses/codex.py and vidbyte/agents/codex/config.py are compared by their LF SHA-256 at the slice's base commit a7730107.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 6.1 (INV-45 to INV-54), 8.1, 8.5 and 12.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_feature_structure.py
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
import os
import subprocess
import sys
import unittest
from typing import Any

from tests.features.codex_host.codex_host_feature_support import FEATURE_METHODS
from tests.features.codex_host.codex_host_support import requires_sdk

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
NATIVE_PACKAGE = "vidbyte.harnesses.native.codex"
# INV-45: the five SDK-free modules, and the three that load openai-codex and are imported only from CodexHost._open.
SDK_FREE_MODULES = ("host_core", "settings_methods", "stream_methods", "thread_methods", "goal_methods")
SDK_MODULES = ("turn_starts", "feature_wire", "turn_stream")
# D-1 and section 8.5: which mixin defines which method, in the module named.
MIXINS = {
    ("settings_methods", "CodexSettingsMethods"): (
        "update_codex_thread_settings",
        "list_codex_collaboration_modes",
        "run_codex_plan",
        "list_codex_mcp_servers",
        "update_codex_turn_settings",
        "set_codex_thread_memory_mode",
        "get_codex_memory_status",
        "reset_codex_memories",
    ),
    ("stream_methods", "CodexStreamMethods"): ("stream_codex_turn", "wait_codex_turns"),
    ("thread_methods", "CodexThreadMethods"): (
        "start_codex_side_chat",
        "create_codex_worktree",
        "archive_codex_thread",
        "unarchive_codex_thread",
        "revert_codex_thread",
        "rename_codex_thread",
        "inject_codex_items",
        "list_codex_background_terminals",
        "clean_codex_background_terminals",
        "search_codex_thread_content",
        "list_codex_child_threads",
    ),
    ("goal_methods", "CodexGoalMethods"): ("pause_codex_goal", "resume_codex_goal", "edit_codex_goal", "clear_codex_goal"),
}
_REQUIRED = inspect.Parameter.empty
# Section 8.5: (parameter, default) after self; an "enum:" default names an enum member, resolved inside the test.
HOST_SIGNATURES: dict[str, tuple[tuple[str, Any], ...]] = {
    "update_codex_thread_settings": (("thread_id", _REQUIRED), ("settings", _REQUIRED)),
    "list_codex_collaboration_modes": (),
    "run_codex_plan": (("prompt", _REQUIRED), ("request", None)),
    "stream_codex_turn": (("handle", _REQUIRED),),
    "wait_codex_turns": (("handles", _REQUIRED), ("return_when", "enum:CodexTurnWaitMode.FIRST_COMPLETED"), ("timeout_seconds", None)),
    "list_codex_mcp_servers": (("thread_id", ""), ("server_name", ""), ("detail", "enum:CodexMcpServerDetail.FULL"), ("cursor", ""), ("limit", None)),
    "update_codex_turn_settings": (
        ("handle", _REQUIRED),
        ("model", ""),
        ("effort", "enum:CodexReasoningEffort.PROVIDER_DEFAULT"),
        ("summary", "enum:CodexReasoningSummary.PROVIDER_DEFAULT"),
        ("service_tier", ""),
        ("clear_service_tier", False),
        ("approvals_reviewer", "enum:CodexApprovalsReviewer.PROVIDER_DEFAULT"),
    ),
    "set_codex_thread_memory_mode": (("thread_id", _REQUIRED), ("mode", _REQUIRED)),
    "get_codex_memory_status": (("min_consolidated_threads", None),),
    "reset_codex_memories": (),
    "start_codex_side_chat": (("thread_id", _REQUIRED), ("prompt", _REQUIRED), ("request", None)),
    "create_codex_worktree": (("repository", _REQUIRED), ("branch", _REQUIRED), ("base_ref", "")),
    "pause_codex_goal": (("thread_id", _REQUIRED),),
    "resume_codex_goal": (("thread_id", _REQUIRED), ("request", None)),
    "edit_codex_goal": (("thread_id", _REQUIRED), ("objective", ""), ("token_budget", None), ("clear_token_budget", False)),
    "clear_codex_goal": (("thread_id", _REQUIRED),),
    "archive_codex_thread": (("thread_id", _REQUIRED),),
    "unarchive_codex_thread": (("thread_id", _REQUIRED),),
    "revert_codex_thread": (("thread_id", _REQUIRED), ("before_turn_id", _REQUIRED)),
    "rename_codex_thread": (("thread_id", _REQUIRED), ("name", _REQUIRED)),
    "inject_codex_items": (("thread_id", _REQUIRED), ("items", _REQUIRED)),
    "list_codex_background_terminals": (("thread_id", _REQUIRED), ("cursor", ""), ("limit", None)),
    "clean_codex_background_terminals": (("thread_id", _REQUIRED),),
    "search_codex_thread_content": (("query", _REQUIRED), ("archived", False), ("cursor", ""), ("limit", None)),
    "list_codex_child_threads": (("thread_id", _REQUIRED), ("descendants", False), ("cursor", ""), ("limit", None)),
}
# INV-47 and NFR-1: (path parts, the most lines the file may have).
LINE_CEILINGS = (
    (("vidbyte", "harnesses", "native", "codex", "host.py"), 900),
    (("vidbyte", "harnesses", "native", "codex", "wire.py"), 840),
    (("vidbyte", "lib", "dataclasses", "codex_host.py"), 900),
    (("vidbyte", "lib", "dataclasses", "codex_host_inputs.py"), 899),
    *((("vidbyte", "harnesses", "native", "codex", f"{name}.py"), 599) for name in (*SDK_FREE_MODULES, *SDK_MODULES)),
    (("vidbyte", "lib", "dataclasses", "codex_host_modes.py"), 599),
    (("vidbyte", "lib", "dataclasses", "codex_host_features.py"), 599),
    (("vidbyte", "lib", "process", "git_worktree.py"), 599),
    (("vidbyte", "tools", "builtins", "codex", "controls.py"), 599),
    (("vidbyte", "tools", "builtins", "codex", "thread_actions.py"), 599),
)
# INV-47 (slice-1 D-17, D-5 here) and INV-54: these two files keep their bytes from the base commit a7730107.
FROZEN_FILES = {
    ("vidbyte", "lib", "dataclasses", "codex.py"): "7fb12084291096e4fc7f6670b090413a4c6df4364885a966b869c1a0973382a8",
    ("vidbyte", "agents", "codex", "config.py"): "00fa03754b8a85eb67eb3c748987a63183935e2703d2ee07fe595ce8a5fd1d71",
}

STRUCTURE_PROBE = r"""
import importlib
import json
import sys

sys.path.insert(0, sys.argv[1])
sys.modules["openai_codex"] = None
import vidbyte.harnesses.native.codex
from vidbyte.harnesses.native.codex import CodexHost

failed = {}
for name in sys.argv[2].split(","):
    try:
        importlib.import_module("vidbyte.harnesses.native.codex." + name)
    except BaseException as exc:
        failed[name] = type(exc).__name__ + ": " + str(exc)[:200]
loaded = sorted(name for name, module in sys.modules.items() if module is not None and (name == "openai_codex" or name.startswith("openai_codex.")))
collaborators = sorted(name for name in sys.argv[3].split(",") if "vidbyte.harnesses.native.codex." + name in sys.modules)
print(json.dumps({"loaded": loaded, "failed": failed, "collaborators": collaborators}))
"""


def _read_lf(*parts: str) -> bytes:
    with open(os.path.join(REPO_ROOT, *parts), "rb") as handle:
        return handle.read().replace(b"\r\n", b"\n")


def _module_tree(name: str) -> ast.Module:
    return ast.parse(_read_lf("vidbyte", "harnesses", "native", "codex", f"{name}.py").decode("utf-8"))


def _sdk_imports_outside_type_checking(tree: ast.Module) -> list[int]:
    """The line of each module-level openai-codex import that is not under `if TYPE_CHECKING:`."""
    lines: list[int] = []
    for node in tree.body:
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.ImportFrom) and (inner.module or "").split(".")[0] == "openai_codex":
                lines.append(inner.lineno)
            if isinstance(inner, ast.Import) and any(alias.name.split(".")[0] == "openai_codex" for alias in inner.names):
                lines.append(inner.lineno)
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                break
    return lines


def _resolve_default(default: Any) -> Any:
    if isinstance(default, str) and default.startswith("enum:"):
        enum_name, member = default[len("enum:") :].split(".")
        return getattr(getattr(importlib.import_module("vidbyte.lib.enums.codex"), enum_name), member)
    return default


class CodexFeatureImportSafetyTests(unittest.TestCase):
    """INV-45, NFR-2 and AC-38."""

    def test_importing_the_host_and_each_mixin_loads_no_sdk_and_no_sdk_collaborator(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", STRUCTURE_PROBE, REPO_ROOT, ",".join(SDK_FREE_MODULES), ",".join(SDK_MODULES)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(f"the structure probe failed ({completed.returncode}):\n{completed.stderr[-4000:]}")
        outcome = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(outcome["failed"], {})
        self.assertEqual(outcome["loaded"], [])
        self.assertEqual(outcome["collaborators"], [])

    def test_the_five_sdk_free_modules_import_openai_codex_only_under_type_checking(self) -> None:
        for name in SDK_FREE_MODULES:
            with self.subTest(module=name):
                self.assertEqual(_sdk_imports_outside_type_checking(_module_tree(name)), [])

    def test_the_host_module_imports_no_sdk_collaborator_at_module_level(self) -> None:
        # INV-45: turn_starts, feature_wire and turn_stream are imported inside CodexHost._open.
        for name in ("host", *SDK_FREE_MODULES):
            with self.subTest(module=name):
                top_level = [node for node in _module_tree(name).body if isinstance(node, (ast.Import, ast.ImportFrom))]
                imported = {(node.module or "").rsplit(".", 1)[-1] for node in top_level if isinstance(node, ast.ImportFrom)}
                imported |= {alias.name.rsplit(".", 1)[-1] for node in top_level if isinstance(node, ast.Import) for alias in node.names}
                self.assertEqual(sorted(imported & set(SDK_MODULES)), [])


class CodexFeatureMixinTests(unittest.TestCase):
    """D-1, D-10, FR-34, INV-50 and the section 8.5 signatures."""

    def test_codex_host_inherits_the_four_mixins_over_the_host_core(self) -> None:
        from vidbyte.harnesses.native.codex import CodexHost

        core = importlib.import_module(f"{NATIVE_PACKAGE}.host_core").CodexHostCore
        for (module, class_name), methods in MIXINS.items():
            with self.subTest(mixin=class_name):
                mixin = getattr(importlib.import_module(f"{NATIVE_PACKAGE}.{module}"), class_name)
                self.assertTrue(issubclass(mixin, core))
                self.assertTrue(issubclass(CodexHost, mixin))
                self.assertEqual(sorted(name for name in methods if name not in vars(mixin)), [])
        self.assertEqual(sorted(name for mixin_methods in MIXINS.values() for name in mixin_methods), sorted(FEATURE_METHODS))
        self.assertIn("_guard", vars(core))
        self.assertIn("_owned", vars(core))

    def test_no_new_method_is_defined_on_codex_host_itself(self) -> None:
        # INV-50: the methods are inherited, so vars(CodexHost) and its pinned helper order do not change.
        from vidbyte.harnesses.native.codex import CodexHost

        self.assertEqual([name for name in FEATURE_METHODS if name in vars(CodexHost)], [])
        self.assertEqual([name for name in FEATURE_METHODS if not callable(getattr(CodexHost, name, None))], [])

    def test_every_new_method_has_the_section_8_5_signature_and_kind(self) -> None:
        from vidbyte.harnesses.native.codex import CodexHost

        self.assertEqual(tuple(HOST_SIGNATURES), FEATURE_METHODS)
        for name, expected in HOST_SIGNATURES.items():
            with self.subTest(method=name):
                method = getattr(CodexHost, name)
                parameters = list(inspect.signature(method).parameters.values())[1:]
                self.assertEqual([(parameter.name, parameter.default) for parameter in parameters], [(parameter, _resolve_default(default)) for parameter, default in expected])
                # D-10: stream_codex_turn is a plain def that returns the iterator; every other method is a coroutine function.
                self.assertEqual(inspect.iscoroutinefunction(method), name != "stream_codex_turn")
                self.assertFalse(inspect.isasyncgenfunction(method))
                self.assertTrue((method.__doc__ or "").strip(), f"{name} needs a docstring that names its limitations (FR-33)")


@requires_sdk
class CodexFeatureCollaboratorTests(unittest.TestCase):
    """D-2, D-3, D-9, D-36, D-39 and section 8.5 "collaborators" and "changed signatures"."""

    def _keywords(self, function: Any) -> list[str]:
        return [parameter.name for parameter in inspect.signature(function).parameters.values() if parameter.name != "self"]

    def test_the_new_collaborators_carry_the_section_8_5_method_names(self) -> None:
        expected = {
            ("turn_starts", "CodexTurnStarts"): ("start_turn", "start_goal", "resume_goal", "accept", "release_tools"),
            ("feature_wire", "CodexFeatureParamsTranslator"): ("thread_settings", "turn_settings", "mcp_servers", "memory_mode", "memory_status", "goal_change", "goal_clear", "revert", "inject", "side_chat_boundary", "side_chat_views", "terminals", "search", "child_threads"),
            ("feature_wire", "CodexFeatureResponseTranslator"): ("modes", "mcp_page", "turn_settings_status", "memory_status", "terminals", "search", "goal", "cleared", "reverted", "empty"),
            ("turn_stream", "CodexTurnEventLog"): ("attach", "record", "close", "subscribe"),
            ("turn_stream", "CodexTurnEventTranslator"): ("event",),
            ("connection", "CodexJsonObjectResponse"): ("model_validate",),
        }
        for (module, class_name), methods in expected.items():
            with self.subTest(collaborator=class_name):
                owner = getattr(importlib.import_module(f"{NATIVE_PACKAGE}.{module}"), class_name)
                self.assertEqual([name for name in methods if not callable(getattr(owner, name, None))], [])

    def test_the_changed_signatures_take_the_new_parameters(self) -> None:
        connection = importlib.import_module(f"{NATIVE_PACKAGE}.connection")
        preflight = importlib.import_module(f"{NATIVE_PACKAGE}.preflight")
        helpers = importlib.import_module(f"{NATIVE_PACKAGE}.thread_helpers")
        wire = importlib.import_module(f"{NATIVE_PACKAGE}.wire")
        turns = importlib.import_module(f"{NATIVE_PACKAGE}.turns")
        skills = importlib.import_module(f"{NATIVE_PACKAGE}.skill_functions")
        self.assertEqual(self._keywords(connection.CodexConnection.raw), ["method", "params", "parse"])
        self.assertIsNone(inspect.signature(connection.CodexConnection.raw).parameters["parse"].default)
        self.assertEqual(self._keywords(preflight.CodexPreflight.require_experimental_api), ["operation", "feature", "used"])
        self.assertIs(inspect.signature(preflight.CodexPreflight.__init__).parameters["experimental_api"].default, True)
        self.assertEqual(self._keywords(preflight.CodexPreflight.reject_routed_reviewer), ["operation", "thread_id", "routed"])
        self.assertEqual(self._keywords(helpers.CodexThreadHelpers.status), ["operation", "thread_id"])
        self.assertEqual(self._keywords(helpers.CodexThreadHelpers.idle_status), ["operation", "thread_id"])
        self.assertEqual(self._keywords(helpers.CodexThreadHelpers.load), ["operation", "thread_id", "status"])
        fork = inspect.signature(helpers.CodexThreadHelpers.fork).parameters["starts_turn"]
        self.assertEqual((fork.kind, fork.default), (inspect.Parameter.KEYWORD_ONLY, False))
        self.assertEqual(self._keywords(turns.CodexTurnRegistry.charge_stream), ["chars", "events"])
        self.assertEqual(self._keywords(turns.CodexLiveTurn.over_cap), ["delta"])
        self.assertEqual(inspect.signature(wire.CodexParamsTranslator.turn_start).parameters["resolved_model"].default, "")
        self.assertIsInstance(inspect.getattr_static(wire.CodexParamsTranslator, "sandbox_policy"), staticmethod)
        self.assertIsInstance(inspect.getattr_static(wire.CodexParamsTranslator, "turn_model"), staticmethod)
        self.assertEqual(self._keywords(skills.CodexSkillFunctions.run_plan), ["plan_run"])
        self.assertTrue(callable(getattr(skills.CodexSkillHost, "list_codex_collaboration_modes", None)))


class CodexFeatureFileSizeTests(unittest.TestCase):
    """INV-47, NFR-1 and AC-40: the ceilings, and the two files the spec freezes."""

    def test_every_touched_or_new_file_stays_within_its_ceiling(self) -> None:
        for parts, ceiling in LINE_CEILINGS:
            with self.subTest(path="/".join(parts)):
                self.assertLessEqual(_read_lf(*parts).count(b"\n"), ceiling)

    def test_the_shared_codex_records_and_the_codex_agent_config_keep_their_bytes(self) -> None:
        for parts, digest in FROZEN_FILES.items():
            with self.subTest(path="/".join(parts)):
                self.assertEqual(hashlib.sha256(_read_lf(*parts)).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
