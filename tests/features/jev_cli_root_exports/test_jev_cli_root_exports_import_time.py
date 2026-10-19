"""FILE: tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py

PURPOSE: Import-time tests for the JevAgent setting root exports, each in a fresh interpreter: a plain `import vidbyte` already holds AgentLoopSettings, PermissionPolicy, TextModelMode and JevDynamicComputeOption in the root module (eager, not through __getattr__), starts no process, and leaves vidbyte.harnesses.native unloaded; the near-miss names vidbyte.PermissionPolicies and `from vidbyte import TextModelModes` still fail without loading it; and `from vidbyte import *` binds every root name, the four included, as the root's own objects.
ROLE IN CODEBASE: Covers spec jev-cli-root-exports AC-3, AC-7, AC-10, INV-1 (bound at import time), INV-5, INV-9, INV-11, D-1, NG-9, EC-1 and EC-15 for vidbyte/__init__.py. tests/features/harness_threads/test_harness_threads_surface.py also probes INV-23, but its last clause compares root __all__ with the merge base, so it is red locally on any branch that adds a root export; this file carries the permanent half.
ARCHITECTURE NOTE: Each probe runs in a child interpreter started with sys.executable and PYTHONPATH set to this checkout, because this test process has usually imported vidbyte.harnesses.native already. Process starts are seen through a sys.addaudithook hook installed before `import vidbyte`, which also catches os.system and the Windows CreateProcess call under subprocess. The probe prints one JSON line and the test reads the last line of stdout.
FUNCTION INVENTORY: fresh_interpreter runs one probe with the four names as arguments and returns its JSON report; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A further root setting name joins SETTING_NAMES. A new process-start audit event in a later Python joins PROCESS_EVENTS inside the probe.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte.harnesses.native, or name a thread function, inside a probe before the step that checks it is unloaded. 2. Do not compare the module set or root __all__ with the merge base, and do not pin a module count or hash (spec NG-13, INV-16). 3. Do not move these probes into this test process.
KNOWN EDGE CASES: hasattr() and a missed `from vidbyte import X` both call the root __getattr__, so a hook that imported the native package before checking the name would load it on a miss. A name served lazily is absent from vars(vidbyte) until first use, which is how the eager check tells the two apart.
RELATED DOCS: tests/features/jev_cli_root_exports/FEATURE.md; tests/features/root_native_thread_exports/FEATURE.md; docs/spec/jev-cli-root-exports/spec.md (sections 6.1 INV-1, INV-5, INV-9, INV-11, 6.2 AC-3, AC-7, AC-10, 8.1 D-1)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_cli_root_exports/test_jev_cli_root_exports_import_time.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SETTING_NAMES = (
    "AgentLoopSettings",
    "PermissionPolicy",
    "TextModelMode",
    "JevDynamicComputeOption",
)
ALL_FOUR = dict.fromkeys(SETTING_NAMES, True)


def fresh_interpreter(probe: str) -> dict[str, object]:
    # The four names reach the probe as sys.argv[1:].
    environment = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    finished = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(probe), *SETTING_NAMES],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        stdin=subprocess.DEVNULL,
        env=environment,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr[-2000:]
    return json.loads(finished.stdout.strip().splitlines()[-1])


def test_fresh_import_binds_the_four_eagerly_without_loading_native_or_starting_a_process() -> (
    None
):
    # AC-7, INV-1, INV-5, D-1, NG-9: a lazy hook would hide the names
    # from type checkers while S015 still accepts it, and a heavier
    # import would break harness thread INV-23 for every SDK user.
    report = fresh_interpreter(
        """
        import json, sys
        PROCESS_EVENTS = {
            "subprocess.Popen", "os.system", "os.spawn", "os.posix_spawn",
            "os.exec", "os.fork", "os.forkpty", "os.startfile",
            "os.startfile/2", "_winapi.CreateProcess",
        }
        started = []
        def record(event, args):
            if event in PROCESS_EVENTS:
                started.append(event)
        sys.addaudithook(record)
        import vidbyte
        native = "vidbyte.harnesses.native"
        eager = {name: name in vars(vidbyte) for name in sys.argv[1:]}
        after_import = native in sys.modules
        misses = []
        try:
            vidbyte.PermissionPolicies
        except AttributeError as error:
            misses.append(type(error).__name__)
        try:
            exec("from vidbyte import TextModelModes", {})
        except ImportError as error:
            misses.append(type(error).__name__)
        print(json.dumps({
            "eager": eager, "after_import": after_import, "misses": misses,
            "after_misses": native in sys.modules, "started": started,
        }))
        """
    )
    assert report["eager"] == ALL_FOUR, (
        "bind the four with ordinary imports in vidbyte/__init__.py, not through __getattr__ or a lazy mapping"
    )
    assert report["after_import"] is False, "import vidbyte loaded native"
    assert report["started"] == [], "import vidbyte started a process"
    # AC-10, INV-11, EC-15: near misses still fail and load nothing.
    assert report["misses"] == ["AttributeError", "ImportError"]
    assert report["after_misses"] is False


def test_star_import_binds_every_root_name_and_the_four_as_the_root_objects() -> None:
    # AC-3, INV-9, EC-1: a name listed in __all__ but never imported
    # makes every `from vidbyte import *` raise AttributeError.
    report = fresh_interpreter(
        """
        import json, sys
        namespace = {}
        exec("from vidbyte import *", namespace)
        root = sys.modules["vidbyte"]
        print(json.dumps({
            "unbound": sorted(set(root.__all__) - set(namespace)),
            "foreign": sorted(
                name for name in root.__all__
                if name in namespace and namespace[name] is not getattr(root, name)
            ),
            "four": {
                name: name in namespace and namespace[name] is getattr(root, name)
                for name in sys.argv[1:]
            },
        }))
        """
    )
    assert report["unbound"] == [] and report["foreign"] == []
    assert report["four"] == ALL_FOUR
