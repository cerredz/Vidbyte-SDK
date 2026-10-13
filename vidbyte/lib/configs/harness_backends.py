"""FILE: vidbyte/lib/configs/harness_backends.py

PURPOSE: Declares HARNESS_BACKENDS, the two fixed Anthropic-compatible backend profiles (GLM through Z.ai, and DeepSeek): endpoint, key variable, Claude models, fixed public Claude Code environment, ignored features, allowed harnesses, opencode provider wiring and the DeepSeek balance URL.
ROLE IN CODEBASE: Read by HarnessBackends in vidbyte/harnesses/native/backends/profiles.py (and through it by list_harness_backends and the backend tools) and by OpencodeServer when an opencode host adds backends. Re-exported from vidbyte/lib/configs/__init__.py.
ARCHITECTURE NOTE: A fixed capability table in the dependency-light configs package, declared in HarnessBackendName order. Each HarnessBackend validates itself when this module is imported, so a bad edit fails at import, never at a call.
FUNCTION INVENTORY: No functions. HARNESS_BACKENDS is a tuple of two HarnessBackend records.
COMMON MODIFICATION PATTERNS: A provider change to a URL, model or variable updates the matching profile here and the spec's profile table together; a new backend adds a HarnessBackendName member first.
WHAT NOT TO DO IN THIS FILE: 1. Do not put a key value or a credential-named variable in claude_env; HarnessBackend refuses one. 2. Do not reorder the tuple; list_harness_backends returns it as declared. 3. Do not read the environment here.
KNOWN EDGE CASES: GLM's Coding Plan terms allow only Claude Code, Codex and opencode, so Grok and Muse are left out of its allowed harnesses. DeepSeek's Anthropic endpoint silently ignores all eleven BackendFeature members.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1 (The two declared profiles), D-16, D-17
TESTS: tests/features/native_backends/test_native_backends_profiles.py
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.harness_backends import HarnessBackend
from vidbyte.lib.enums.harness_backends import BackendFeature, HarnessBackendName
from vidbyte.lib.enums.native_hosts import NativeHarness

HARNESS_BACKENDS: tuple[HarnessBackend, ...] = (
    HarnessBackend(
        name=HarnessBackendName.GLM,
        anthropic_base_url="https://api.z.ai/api/anthropic",
        auth_env_var="GLM_API_KEY",
        claude_models=("glm-5.3[1m]", "glm-5.3-flash[1m]"),
        claude_env={
            "API_TIMEOUT_MS": "3000000",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3-flash[1m]",
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        },
        unsupported_features=frozenset(),
        allowed_harnesses=frozenset({NativeHarness.CLAUDE_CODE, NativeHarness.CODEX, NativeHarness.OPENCODE}),
        opencode_provider_id="zai-coding-plan",
        opencode_key_env_var="ZHIPU_API_KEY",
        opencode_models=("glm-5.3", "glm-5.3-flash"),
        balance_url=None,
    ),
    HarnessBackend(
        name=HarnessBackendName.DEEPSEEK,
        anthropic_base_url="https://api.deepseek.com/anthropic",
        auth_env_var="DEEPSEEK_API_KEY",
        claude_models=("deepseek-flash[1m]", "deepseek-v4-pro"),
        claude_env={"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "786432"},
        unsupported_features=frozenset(BackendFeature),
        allowed_harnesses=frozenset(NativeHarness),
        opencode_provider_id="deepseek",
        opencode_key_env_var="DEEPSEEK_API_KEY",
        opencode_models=("deepseek-flash", "deepseek-v4-pro"),
        balance_url="https://api.deepseek.com/user/balance",
    ),
)

__all__ = ["HARNESS_BACKENDS"]
