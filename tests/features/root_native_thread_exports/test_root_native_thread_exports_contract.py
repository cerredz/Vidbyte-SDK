"""FILE: tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py

PURPOSE: Contract tests for importing the native harness thread surface from the root `vidbyte` package: every name in vidbyte.harnesses.native.__all__ is in vidbyte.__all__ and is the very same object, the nine thread functions load lazily so a plain `import vidbyte` (and any attribute miss) still leaves vidbyte.harnesses.native unloaded, a misspelled name is still an AttributeError or ImportError, and contracts/sdk-public-api.json lists the names at the package version that vidbyte-cli pins.
ROLE IN CODEBASE: The executable form of tests/features/root_native_thread_exports/FEATURE.md. vidbyte-cli may import only names listed in the vendored public-API contract, which is vidbyte.__all__, so these tests are what keeps the thread functions reachable from there.
ARCHITECTURE NOTE: The import-time checks run in a fresh interpreter with PYTHONPATH set to this checkout, because this test process has usually imported vidbyte.harnesses.native already. The contract check reads the committed JSON and pyproject.toml directly, as the CLI's lint does.
FUNCTION INVENTORY: fresh_interpreter runs one probe script and returns its last JSON line; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new name in vidbyte.harnesses.native.__all__ needs no change here; the tests read that list. Add it to vidbyte/__init__.py and regenerate the contract instead. FLOOR_NAMES only grows.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte.harnesses.native inside a fresh-interpreter probe before the step that checks it is unloaded. 2. Do not start a vendor CLI; nothing here calls a thread function.
KNOWN EDGE CASES: hasattr() on a module calls its __getattr__ for a missing name, so a hook that imported the native package before deciding would break the unloaded promise on every probe of a missing attribute.
RELATED DOCS: tests/features/root_native_thread_exports/FEATURE.md; contracts/README.md; tests/features/harness_threads/test_harness_threads_surface.py (INV-23).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/root_native_thread_exports
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "contracts" / "sdk-public-api.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
THREAD_FUNCTIONS = tuple(f"{verb}_{harness}_thread" for harness in ("grok", "opencode", "muse") for verb in ("run", "continue", "fork"))
# The names the 0.3.1 release first exported from the root. vidbyte-cli
# imports them, so the root may never drop one, even together with a
# matching removal from vidbyte.harnesses.native.
FLOOR_NAMES = frozenset(
    {
        *THREAD_FUNCTIONS,
        "NativeThreadResult",
        "NativeThreadError",
        "GrokThreadConfig",
        "OpencodeThreadConfig",
        "MuseThreadConfig",
        "GrokPermissionMode",
        "GrokReasoningEffort",
        "MuseReasoningEffort",
    }
)
ADD_TO_ROOT_HINT = "add it to vidbyte/__init__.py (a function goes in _LAZY_NATIVE_THREAD_EXPORTS, a record, enum or error in the vidbyte.lib imports) and to its __all__, then run scripts/generate-sdk-public-api.py"


def fresh_interpreter(probe: str) -> dict[str, object]:
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    finished = subprocess.run([sys.executable, "-c", textwrap.dedent(probe)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL, env=environment, check=False)
    assert finished.returncode == 0, finished.stderr[-2000:]
    return json.loads(finished.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def native_names() -> list[str]:
    return list(importlib.import_module("vidbyte.harnesses.native").__all__)


def test_the_native_package_still_exports_every_floor_name(native_names: list[str]) -> None:
    # The floor is meaningful only while the native package itself
    # still offers these names; a rename there must be a visible break.
    assert sorted(FLOOR_NAMES - set(native_names)) == []


def test_every_native_export_is_listed_in_the_root_all(native_names: list[str]) -> None:
    import vidbyte

    missing = [name for name in sorted(set(native_names) | FLOOR_NAMES) if name not in vidbyte.__all__]
    assert missing == [], f"vidbyte.harnesses.native exports {missing} but the root vidbyte package does not; {ADD_TO_ROOT_HINT}"


def test_each_root_name_is_the_native_object_itself(native_names: list[str]) -> None:
    # A wrapper or a second copy would break isinstance checks on
    # NativeThreadError and identity checks callers make on the records.
    import vidbyte

    native = importlib.import_module("vidbyte.harnesses.native")
    different = [name for name in native_names if getattr(vidbyte, name) is not getattr(native, name)]
    assert different == []
    namespace: dict[str, object] = {}
    exec(f"from vidbyte import {', '.join(native_names)}", namespace)
    assert [name for name in native_names if namespace[name] is not getattr(native, name)] == []


def test_import_vidbyte_leaves_the_native_package_unloaded_until_a_function_is_named() -> None:
    report = fresh_interpreter(
        """
        import json, sys
        import vidbyte
        loaded = lambda: "vidbyte.harnesses.native" in sys.modules
        after_import = loaded()
        listed = sorted(name for name in dir(vidbyte) if name.endswith("_thread"))
        probes = [hasattr(vidbyte, "__wrapped__"), hasattr(vidbyte, "run_claude_threads")]
        after_misses = loaded()
        config = vidbyte.GrokThreadConfig(permission_mode=vidbyte.GrokPermissionMode.ACCEPT_EDITS)
        after_records = loaded()
        from vidbyte import run_opencode_thread
        native = sys.modules["vidbyte.harnesses.native"]
        print(json.dumps({"after_import": after_import, "listed": listed, "probes": probes, "after_misses": after_misses, "mode": str(config.permission_mode), "after_records": after_records, "after_function": loaded(), "same": run_opencode_thread is native.run_opencode_thread}))
        """
    )
    assert report["after_import"] is False
    assert report["listed"] == sorted(THREAD_FUNCTIONS), "dir(vidbyte) must list the lazy thread functions before their first use"
    assert report["probes"] == [False, False] and report["after_misses"] is False, "an attribute miss must not import vidbyte.harnesses.native"
    assert report["mode"] == "acceptEdits" and report["after_records"] is False
    assert report["after_function"] is True and report["same"] is True


def test_star_import_from_vidbyte_binds_every_thread_function() -> None:
    report = fresh_interpreter(
        """
        import json
        namespace = {}
        exec("from vidbyte import *", namespace)
        print(json.dumps(sorted(name for name in namespace if name.endswith("_thread"))))
        """
    )
    assert report == sorted(THREAD_FUNCTIONS)


def test_a_misspelled_root_name_is_still_an_attribute_or_import_error() -> None:
    import vidbyte

    with pytest.raises(AttributeError, match=r"module 'vidbyte' has no attribute 'run_grok_threads'"):
        getattr(vidbyte, "run_grok_threads")
    with pytest.raises(ImportError, match=r"cannot import name 'fork_muse_threads' from 'vidbyte'"):
        exec("from vidbyte import fork_muse_threads", {})


def test_the_public_api_contract_lists_every_root_native_name_at_the_package_version(native_names: list[str]) -> None:
    # vidbyte-cli vendors this file: its C028 lint admits only the
    # listed names, and its C029 lint makes every vidbyte-sdk pin admit
    # the recorded version, so both must describe what this tree ships.
    import vidbyte

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    project_version = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))["project"]["version"]
    assert sorted((set(native_names) | FLOOR_NAMES) - set(contract["exports"])) == [], "run scripts/generate-sdk-public-api.py after committing the root export"
    assert contract["version"] == project_version == vidbyte.__version__
