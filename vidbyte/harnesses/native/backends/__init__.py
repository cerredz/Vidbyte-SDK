"""FILE: vidbyte/harnesses/native/backends/__init__.py

PURPOSE: Exposes the six backend functions over the GLM and DeepSeek profiles as plain module functions: list_harness_backends, build_claude_backend_env, check_backend_ready, check_backend_compat, get_deepseek_balance and build_opencode_backend_provider.
ROLE IN CODEBASE: The public import path for the backend functions (from vidbyte.harnesses.native.backends import build_claude_backend_env); used by the backend tools in vidbyte/tools/builtins/harness_backends/ and by the opencode host. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: Each name is bound to the matching HarnessBackends static method, so the module function and the method are the same object and there is one implementation.
FUNCTION INVENTORY: No functions of its own. Re-exports HarnessBackends and its six static methods.
COMMON MODIFICATION PATTERNS: A new backend function is a static method on HarnessBackends plus one binding line here and one entry in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not wrap the methods in new functions; the bindings must stay the same objects. 2. Do not add import-time side effects such as reading a key.
KNOWN EDGE CASES: None; the module only binds names.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Backends), D-16
TESTS: tests/features/native_backends/test_native_backends_profiles.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.backends.profiles import HarnessBackends

list_harness_backends = HarnessBackends.list_harness_backends
build_claude_backend_env = HarnessBackends.build_claude_backend_env
check_backend_ready = HarnessBackends.check_backend_ready
check_backend_compat = HarnessBackends.check_backend_compat
get_deepseek_balance = HarnessBackends.get_deepseek_balance
build_opencode_backend_provider = HarnessBackends.build_opencode_backend_provider

__all__ = [
    "HarnessBackends",
    "build_claude_backend_env",
    "build_opencode_backend_provider",
    "check_backend_compat",
    "check_backend_ready",
    "get_deepseek_balance",
    "list_harness_backends",
]
