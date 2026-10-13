"""FILE: vidbyte/harnesses/native/grok/__init__.py

PURPOSE: Exports the Grok host's public API: GrokHost, the async context manager over the user's Grok Build CLI, and run_grok_once, the module function that runs one headless prompt in a host of its own.
ROLE IN CODEBASE: The public import path (from vidbyte.harnesses.native.grok import GrokHost); used by the Grok tools in vidbyte/tools/builtins/grok/. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only re-exports; the host lives in host.py, its argv in cli.py, its codec in wire.py and its turn driver in turn.py. Importing it starts no process.
FUNCTION INVENTORY: No functions of its own. Re-exports GrokHost and run_grok_once.
COMMON MODIFICATION PATTERNS: A new public Grok name is added to the import and the literal __all__; internal classes (GrokCli, GrokWire, GrokTurnDriver) stay importable from their modules only.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the grok executable. 2. Do not export the records; they live in vidbyte.lib.dataclasses.grok.
KNOWN EDGE CASES: None; the module only re-exports.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Grok host), FR-17, D-15
TESTS: tests/features/grok_host/test_grok_host_acceptance.py, tests/features/grok_host/test_grok_host_shared_contract.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.grok.host import GrokHost, run_grok_once

__all__ = ["GrokHost", "run_grok_once"]
