"""FILE: tests/features/codex_host/test_codex_host_packaging.py

PURPOSE: Proves the packaging promises of the CodexHost change: importing the package and the tools never loads openai-codex, entering a host without the SDK reports the pip extra even when codex is missing too, the shared native marker has request.md's exact bytes, every export list and docstring bullet lands where section 12.3 puts it, and the repo map and harnesses README carry the fixed texts.
ROLE IN CODEBASE: Packaging layer of tests/features/codex_host/ (spec AC-2, AC-36, INV-1, INV-3, INV-42, EC-1, FR-30; section 12.3 rows 2, 3, 6, 8, 9, 23, 24, 26, 27, 28). CI runs it: the SDK-blocked check needs no extra, and the one check that needs the installed SDK is gated.
ARCHITECTURE NOTE: Import safety is checked in a fresh `python -I` interpreter, because earlier tests in this process may already have imported openai-codex; the child puts the worktree on sys.path itself, blocks openai_codex with a None entry in sys.modules when asked, and replaces shutil.which so no binary is ever resolved or run. Text files are compared after CRLF is turned into LF, which equals the committed LF blob on a core.autocrlf checkout and on Linux alike.
COMMON MODIFICATION PATTERNS: The fixed texts below are copied from request.md section C through spec section 12.5; if request.md changes them, change them here, never by reading the files under test.
KNOWN EDGE CASES: The marker's SHA-256 is of its 911 LF bytes; the CRLF working copy hashes differently, so the bytes are normalized first. The enums and builtins export lists are not globally sorted, so only the spec's own ordering rules are asserted.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 6.1 (INV-1, INV-42), 12.3 and 12.5; request.md section C.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_packaging.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest

from tests.features.codex_host.codex_host_support import PIP_INSTALL_FRAGMENT, SDK_AVAILABLE, TOOL_TABLE

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# request.md section C: the SHA-256 of the native marker's 911 LF bytes.
NATIVE_INIT_SHA256 = "0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a"

NATIVE_CODEX_EXPORTS = ["CodexHost", "check_codex_ready", "fork_codex_thread", "get_codex_rate_limits", "list_codex_models", "list_codex_threads", "read_codex_thread"]

RECORD_EXPORTS = [
    "CodexGoal",
    "CodexModelInfo",
    "CodexProblem",
    "CodexRateLimitWindow",
    "CodexRateLimits",
    "CodexReadiness",
    "CodexReviewTarget",
    "CodexSpawnRequest",
    "CodexThreadInfo",
    "CodexThreadPage",
    "CodexThreadUsage",
    "CodexTurnHandle",
    "CodexTurnSnapshot",
    "CodexTurnSummary",
    "CodexTurnUsage",
]

NEW_ENUMS = (
    "CodexAccountKind",
    "CodexApprovalPolicy",
    "CodexApprovalsReviewer",
    "CodexGoalStatus",
    "CodexHostOperation",
    "CodexReviewDelivery",
    "CodexReviewTargetKind",
    "CodexSandboxReadiness",
    "CodexSortDirection",
    "CodexThreadSortKey",
    "CodexThreadSourceKind",
    "CodexThreadStatus",
    "CodexTurnStatus",
)

# Spec section 12.3 row 3, verbatim: the Codex* order in vidbyte.lib.enums.__all__.
ENUMS_CODEX_ORDER = [
    "CodexAccountKind",
    "CodexApprovalMode",
    "CodexApprovalPolicy",
    "CodexApprovalsReviewer",
    "CodexContextAnchor",
    "CodexGoalStatus",
    "CodexHostOperation",
    "CodexInputType",
    "CodexPersonality",
    "CodexReasoningEffort",
    "CodexReasoningSummary",
    "CodexReviewDelivery",
    "CodexReviewTargetKind",
    "CodexSandbox",
    "CodexSandboxReadiness",
    "CodexSortDirection",
    "CodexThreadSortKey",
    "CodexThreadSource",
    "CodexThreadSourceKind",
    "CodexThreadStartSource",
    "CodexThreadStatus",
    "CodexTurnStatus",
]

# request.md section C, through spec section 12.5: the repo-map section and the README bullet.
REPO_MAP_SECTION = "##### `vidbyte/harnesses/native/`\n\nHosts for the coding agents that vendors ship as their own executables, kept apart from the trajectory envelope above even though both use the word harness. Each coding harness gets its own host class, which owns the live processes it starts and wraps the vendor's official SDK in small, atomic functions such as starting, continuing, forking, steering and waiting on a session. Every failure comes back as a semantic error code that names the problem and the next step to take, so an agent that calls these functions as tools can recover without reading a stack trace. Importing the package never requires a vendor SDK: each host loads its SDK only when it is first used, and that SDK comes from the harness's own optional extra."
README_BULLET = "- `native/`: hosts for native coding-harness executables, one subpackage per harness, each wrapping that harness's official SDK in small, atomic functions on a host class; unrelated to the `Harness` envelope above."
SERIALIZATION_BULLET = "- `serialization.py`: the single redaction pass and shared secret-key policy."

# Runs in a fresh `python -I` child: argv[1] is the worktree, argv[2] is "blocked" or "installed".
IMPORT_PROBE = r'''
import asyncio
import json
import shutil
import sys
import types

sys.path.insert(0, sys.argv[1])
if sys.argv[2] == "blocked":
    sys.modules["openai_codex"] = None
# Codex is missing too, so a host that resolved the binary before loading the SDK would report the CLI instead.
shutil.which = lambda *args, **kwargs: None

import vidbyte
import vidbyte.harnesses.native
import vidbyte.harnesses.native.codex
import vidbyte.tools.builtins
import vidbyte.tools.builtins.codex
import vidbyte.tools.toolsets
from vidbyte.harnesses.native.codex import CodexHost
from vidbyte.tools.toolsets import CodexHostTools

tools = CodexHostTools(types.SimpleNamespace(), max_live_turns=2)
loaded = sorted(name for name, module in sys.modules.items() if module is not None and (name == "openai_codex" or name.startswith("openai_codex.")))
outcome = {"loaded": loaded, "tools": len(tools), "first": tools.names()[0]}


async def enter():
    async with CodexHost():
        pass


if sys.argv[2] == "blocked":
    try:
        asyncio.run(enter())
        outcome["error"] = None
    except Exception as exc:
        outcome["error"] = type(exc).__name__
        outcome["code"] = str(getattr(exc, "failure_code", ""))
        outcome["next_step"] = str(getattr(exc, "next_step", ""))
print(json.dumps(outcome))
'''


def _run_import_probe(mode: str) -> dict:
    completed = subprocess.run(
        [sys.executable, "-I", "-c", IMPORT_PROBE, REPO_ROOT, mode],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"the import probe failed ({completed.returncode}):\n{completed.stderr[-4000:]}")
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _read_lf(*parts: str) -> str:
    with open(os.path.join(REPO_ROOT, *parts), "rb") as handle:
        return handle.read().replace(b"\r\n", b"\n").decode("utf-8")


class CodexHostImportSafetyTests(unittest.TestCase):
    """INV-1 and AC-2: the package and the tools import without openai-codex."""

    # AC-2, EC-1, INV-3: the SDK is loaded before the binary is resolved.
    def test_imports_never_load_the_sdk_and_entering_reports_the_pip_extra(self) -> None:
        outcome = _run_import_probe("blocked")
        self.assertEqual(outcome["loaded"], [])
        self.assertEqual((outcome["tools"], outcome["first"]), (15, "check_codex_ready"))
        self.assertEqual(outcome["error"], "CodexAgentError")
        self.assertEqual(outcome["code"], "codex.not_installed")
        self.assertIn(PIP_INSTALL_FRAGMENT, outcome["next_step"])

    # INV-1: an installed SDK stays unloaded until a host is entered.
    @unittest.skipUnless(SDK_AVAILABLE, "requires the optional openai-codex extra")
    def test_imports_leave_an_installed_sdk_unloaded(self) -> None:
        outcome = _run_import_probe("installed")
        self.assertEqual(outcome["loaded"], [])


class CodexHostFixedBytesTests(unittest.TestCase):
    """AC-36, INV-42 and FR-30: the shared files carry request.md's fixed bytes and texts."""

    def test_native_package_marker_has_the_fixed_bytes(self) -> None:
        with open(os.path.join(REPO_ROOT, "vidbyte", "harnesses", "native", "__init__.py"), "rb") as handle:
            data = handle.read().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(data).hexdigest(), NATIVE_INIT_SHA256)

    def test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores(self) -> None:
        text = _read_lf("REPO_MAP.md")
        heading = "#### `vidbyte/harnesses/`\n\n"
        start = text.index(heading) + len(heading)
        end = text.index("##### `vidbyte/harnesses/stores/`", start)
        paragraph, _, inserted = text[start:end].partition("\n\n")
        self.assertTrue(paragraph.startswith("The base abstraction for wrapping an existing agent workflow"))
        self.assertEqual(inserted, REPO_MAP_SECTION + "\n\n")

    def test_harnesses_readme_bullet_follows_the_serialization_bullet(self) -> None:
        lines = _read_lf("vidbyte", "harnesses", "README.md").split("\n")
        index = lines.index(SERIALIZATION_BULLET)
        self.assertEqual(lines[index + 1 : index + 3], [README_BULLET, ""])


class CodexHostExportTests(unittest.TestCase):
    """Section 8.5 and 12.3: each export list names exactly what the spec lists, where the spec puts it."""

    def test_new_packages_export_exactly_their_spec_lists(self) -> None:
        import vidbyte.harnesses.native.codex as native_codex
        import vidbyte.tools.builtins.codex as builtin_codex
        from vidbyte.lib.dataclasses import codex_host

        self.assertEqual(native_codex.__all__, NATIVE_CODEX_EXPORTS)
        self.assertEqual(codex_host.__all__, RECORD_EXPORTS)
        tool_classes = [row[1] for row in TOOL_TABLE]
        self.assertIsInstance(builtin_codex.__all__, list)
        self.assertEqual(sorted(builtin_codex.__all__), sorted([*tool_classes, "CodexToolScope"]))
        for name in native_codex.__all__:
            self.assertTrue(callable(getattr(native_codex, name)), name)

    def test_existing_export_lists_gain_only_the_new_names_in_place(self) -> None:
        import vidbyte.lib.enums as enums
        import vidbyte.lib.enums.codex as codex_enums
        import vidbyte.tools.builtins as builtins
        import vidbyte.tools.builtins.codex as builtin_codex
        import vidbyte.tools.toolsets as toolsets

        # Row 3: the Codex* entries of vidbyte.lib.enums, in the spec's order.
        self.assertEqual([name for name in enums.__all__ if name.startswith("Codex")], ENUMS_CODEX_ORDER)
        for name in NEW_ENUMS:
            self.assertIs(getattr(enums, name), getattr(codex_enums, name))
        # Row 2: CodexFailureClass stays first, and the rest of the list stays alphabetical.
        self.assertEqual(codex_enums.__all__[0], "CodexFailureClass")
        self.assertEqual(codex_enums.__all__[1:], sorted(codex_enums.__all__[1:]))
        self.assertTrue(set(NEW_ENUMS) <= set(codex_enums.__all__))
        # Row 24: the fifteen tools are re-exported, with the docstring bullet after the code_search one.
        for row in TOOL_TABLE:
            self.assertIn(row[1], builtins.__all__)
            self.assertIs(getattr(builtins, row[1]), getattr(builtin_codex, row[1]))
        builtin_lines = [line.strip() for line in (builtins.__doc__ or "").splitlines()]
        code_search = builtin_lines.index("- Code search tools from builtins.code_search.")
        self.assertEqual(builtin_lines[code_search + 1], "- Codex host tools from builtins.codex.")
        # Row 26: CodexHostTools sorts before CodingAgentTools, and its bullet ends the Architecture list.
        self.assertEqual(toolsets.__all__, ["CodexHostTools", "CodingAgentTools", "ParadigmMinimalToolset"])
        toolset_lines = [line.strip() for line in (toolsets.__doc__ or "").splitlines()]
        coding = toolset_lines.index("- CodingAgentTools: The seven tools a CodingAgent starts with over one root folder.")
        self.assertEqual(toolset_lines[coding + 1], "- CodexHostTools: One tool per CodexHost function over one host.")


if __name__ == "__main__":
    unittest.main()
