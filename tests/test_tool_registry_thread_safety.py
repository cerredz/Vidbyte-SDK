"""FILE: tests/test_tool_registry_thread_safety.py

PURPOSE: Regression tests that ToolRegistry readers never see a half-registered tool.
ROLE IN CODEBASE: Guards ToolRegistry.subset() and add() against reading the tool tuple and the name index out of step while register() runs on another thread.
ARCHITECTURE NOTE: A writer thread holds the registry lock between the two index assignments, coordinated with threading.Event, so the interleaving is deterministic with no stress loop.
COMMON MODIFICATION PATTERNS: Add a case here when ToolRegistry gains another inherited reader that consults both _tools and _by_name.
KNOWN EDGE CASES: Single-attribute readers such as names() and get() read one immutable snapshot and need no lock, so they are not tested here.
RELATED DOCS: vidbyte/lib/registries/README.md.
TESTS: python -m pytest tests/test_tool_registry_thread_safety.py.
"""

from __future__ import annotations

import threading
import unittest
from typing import Any

from vidbyte.tools import ToolRegistry, vidbyte_tool


@vidbyte_tool(name="A")
def tool_a() -> str:
    return "a"


@vidbyte_tool(name="B")
def tool_b() -> str:
    return "b"


@vidbyte_tool(name="C")
def tool_c() -> str:
    return "c"


class ToolRegistryHalfRegisteredReadTests(unittest.TestCase):
    """Readers that consult both indexes must wait for an in-progress register()."""

    def _read_during_half_registration(self, read: Any) -> dict[str, Any]:
        registry = ToolRegistry([tool_a])
        half_registered = threading.Event()
        finish_registration = threading.Event()
        outcome: dict[str, Any] = {}

        def writer() -> None:
            # Simulate register() between its two assignments: the tuple holds B,
            # the name index does not yet.
            with registry._lock:
                registry._tools = (tool_a, tool_b)
                half_registered.set()
                finish_registration.wait(timeout=5)
                registry._by_name = {"A": tool_a, "B": tool_b}

        def reader() -> None:
            half_registered.wait(timeout=5)
            try:
                outcome["result"] = read(registry)
            except Exception as exc:  # noqa: BLE001 - recorded for the assertion
                outcome["error"] = exc

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)
        writer_thread.start()
        reader_thread.start()
        self.assertTrue(half_registered.wait(timeout=5))
        reader_thread.join(timeout=0.1)
        outcome["blocked"] = reader_thread.is_alive()
        finish_registration.set()
        writer_thread.join(timeout=5)
        reader_thread.join(timeout=5)
        return outcome

    def test_subset_waits_for_register_to_finish(self) -> None:
        outcome = self._read_during_half_registration(lambda registry: registry.subset(["B"]))

        self.assertNotIn("error", outcome)
        self.assertTrue(outcome["blocked"])
        self.assertEqual(outcome["result"].names(), ("B",))

    def test_add_waits_for_register_to_finish(self) -> None:
        outcome = self._read_during_half_registration(lambda registry: registry.add(tool_c))

        self.assertNotIn("error", outcome)
        self.assertTrue(outcome["blocked"])
        self.assertEqual(outcome["result"].names(), ("A", "B", "C"))


if __name__ == "__main__":
    unittest.main()
