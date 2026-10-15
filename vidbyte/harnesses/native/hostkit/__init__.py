"""FILE: vidbyte/harnesses/native/hostkit/__init__.py

PURPOSE: The plumbing the Grok, opencode and Muse thread functions share; it will export NativeErrorFactory, NativeLauncher and NativeSkillFolders once they land.
ROLE IN CODEBASE: Imported by vidbyte.harnesses.native.grok, .opencode and .muse only. It is internal: nothing here is re-exported from vidbyte.harnesses or the root package.
ARCHITECTURE NOTE: Lives under harnesses/native rather than vidbyte.lib because scrubbing uses HarnessRedactor from vidbyte.harnesses.serialization and lib may not import upward.
FUNCTION INVENTORY: No functions. Exports nothing yet.
COMMON MODIFICATION PATTERNS: Plumbing that a second harness needs goes here, in its own module, and is exported from this literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not import a harness subpackage here; harness subpackages import hostkit, never the reverse. 2. Do not add import-time side effects.
KNOWN EDGE CASES: None; the module defines no names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

__all__: list[str] = []
