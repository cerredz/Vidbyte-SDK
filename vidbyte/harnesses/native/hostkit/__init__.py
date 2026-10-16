"""FILE: vidbyte/harnesses/native/hostkit/__init__.py

PURPOSE: Exposes the plumbing the Grok, opencode, Muse and Claude Code thread functions share: NativeErrorFactory (builds every detailed, scrubbed NativeThreadError), NativeLauncher (finds the program to start and refuses Windows batch launchers), NativePrivateFolders (prepares the SDK-owned private folder of one workspace) and NativeSkillFolders (keeps an SDK-owned skills folder holding exactly the caller's skills).
ROLE IN CODEBASE: Imported by vidbyte.harnesses.native.grok, .opencode, .muse and .claude only; NativePrivateFolders is used by .grok (the private Grok home) and .claude (the private Claude Code config folder). It is internal: nothing here is re-exported from vidbyte.harnesses.native or the root package.
ARCHITECTURE NOTE: Lives under harnesses/native rather than vidbyte.lib because scrubbing uses HarnessRedactor from vidbyte.harnesses.serialization and lib may not import upward.
FUNCTION INVENTORY: No functions. Re-exports NativeErrorFactory, NativeLauncher, NativePrivateFolders and NativeSkillFolders.
COMMON MODIFICATION PATTERNS: Plumbing that a second harness needs goes here, in its own module, and is exported from this literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not import a harness subpackage here; harness subpackages import hostkit, never the reverse. 2. Do not add import-time side effects.
KNOWN EDGE CASES: None; the module only re-exports.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.harnesses.native.hostkit.folders import NativePrivateFolders
from vidbyte.harnesses.native.hostkit.launcher import NativeLauncher
from vidbyte.harnesses.native.hostkit.skills import NativeSkillFolders

__all__ = ["NativeErrorFactory", "NativeLauncher", "NativePrivateFolders", "NativeSkillFolders"]
