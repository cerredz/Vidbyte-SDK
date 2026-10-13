"""FILE: vidbyte/harnesses/native/__init__.py

PURPOSE: Marks vidbyte/harnesses/native as the package of native coding-harness hosts: one subpackage per coding harness, each wrapping that harness's official SDK in small, atomic functions on a host class.
ROLE IN CODEBASE: A parent package only. Callers import a host from its own subpackage, never from this module, so this module imports nothing and names no harness.
ARCHITECTURE NOTE: Each harness subpackage owns its host class, its vendor SDK import, and its errors. Nothing here imports a vendor SDK, so importing this package never requires an optional extra.
COMMON MODIFICATION PATTERNS: A new harness adds its own subpackage beside the existing ones and leaves this module unchanged.
KNOWN EDGE CASES: None; the module defines no names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: None of its own; each harness subpackage has its own tests.
"""
