"""FILE: vidbyte/harnesses/native/hostkit/__init__.py

PURPOSE: Exposes the plumbing the Grok, opencode and Muse thread functions, thread helpers and command functions share: NativeErrorFactory (builds every detailed, scrubbed NativeThreadError), NativeLauncher (finds the program to start and refuses Windows batch launchers), NativeSkillFolders (keeps an SDK-owned skills folder holding exactly the caller's skills), NativeThreadListing (the since window, order, limit, search match and lineage step every list helper shares) and NativeCommandEvidence (the check that a command run really ran the command).
ROLE IN CODEBASE: Imported by vidbyte.harnesses.native.grok, .opencode and .muse only. It is internal: nothing here is re-exported from vidbyte.harnesses.native or the root package.
ARCHITECTURE NOTE: Lives under harnesses/native rather than vidbyte.lib because scrubbing uses HarnessRedactor from vidbyte.harnesses.serialization and lib may not import upward.
FUNCTION INVENTORY: No functions. Re-exports NativeCommandEvidence, NativeErrorFactory, NativeLauncher, NativeSkillFolders and NativeThreadListing.
COMMON MODIFICATION PATTERNS: Plumbing that a second harness needs goes here, in its own module, and is exported from this literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not import a harness subpackage here; harness subpackages import hostkit, never the reverse. 2. Do not add import-time side effects.
KNOWN EDGE CASES: None; the module only re-exports.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.harnesses.native.hostkit.evidence import NativeCommandEvidence
from vidbyte.harnesses.native.hostkit.launcher import NativeLauncher
from vidbyte.harnesses.native.hostkit.listing import NativeThreadListing
from vidbyte.harnesses.native.hostkit.skills import NativeSkillFolders

__all__ = ["NativeCommandEvidence", "NativeErrorFactory", "NativeLauncher", "NativeSkillFolders", "NativeThreadListing"]
