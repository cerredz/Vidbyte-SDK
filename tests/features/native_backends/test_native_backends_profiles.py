"""FILE: tests/features/native_backends/test_native_backends_profiles.py

PURPOSE: The declared GLM and DeepSeek profiles and the four functions that make no network call: HARNESS_BACKENDS field by field (§9.1), list_harness_backends, build_claude_backend_env with its exact key set and hidden token (AC-13), check_backend_compat (AC-14, EC-135, EC-136) and build_opencode_backend_provider (D-16).
ROLE IN CODEBASE: Start here when Claude Code or opencode is pointed at the wrong endpoint, model or key, or when a compatibility check passes a request the backend would silently mangle. Covers vidbyte.lib.configs.harness_backends and vidbyte.harnesses.native.backends.profiles.HarnessBackends.
ARCHITECTURE NOTE: The key variables come from monkeypatch only (autouse isolation in conftest.py), and the autouse fake endpoint records any HTTP request, so "no I/O" is asserted as an empty request log and no client built.
FUNCTION INVENTORY: EXPECTED_PROFILES is the §9.1 profile table as data; the test_* functions each pin one promise; the two exhaustive tests walk every BackendFeature subset and every declared model.
COMMON MODIFICATION PATTERNS: If §9.1's profile table changes (A-13 model names), update EXPECTED_PROFILES and EXPECTED_ENV_KEYS with it, and nothing else.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare as_environ() with a subset check; AC-13 says "exactly the §9.1 keys". 2. Do not put a real key in any fixture; the fake values are not keys.
KNOWN EDGE CASES: GLM declares no unsupported feature and DeepSeek allows every harness, so no declared profile shows that check_backend_compat checks the harness before the features.
RELATED DOCS: tests/features/native_backends/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.2 AC-13/AC-14, §6.3.6, §8.5, §9.1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/native_backends/test_native_backends_profiles.py
"""

from __future__ import annotations

import itertools
from types import MappingProxyType
from typing import Any

import pytest

FAKE_GLM_VALUE = "fake-glm-value-not-a-key-0001"
FAKE_DEEPSEEK_VALUE = "fake-deepseek-value-not-a-key-0002"
SECOND_DEEPSEEK_VALUE = "fake-deepseek-value-not-a-key-0003"
ALL_FEATURES = (
    "mcp_servers", "cache_control", "container", "top_k", "service_tier", "anthropic_beta", "disable_parallel_tool_use",
    "thinking_budget_tokens", "tool_result_is_error", "document_blocks", "search_result_blocks",
)
EXPECTED_PROFILES: dict[str, dict[str, Any]] = {
    "glm": {
        "anthropic_base_url": "https://api.z.ai/api/anthropic",
        "auth_env_var": "GLM_API_KEY",
        "claude_models": ("glm-5.3[1m]", "glm-5.3-flash[1m]"),
        "claude_env": {
            "API_TIMEOUT_MS": "3000000",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3-flash[1m]",
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        },
        "unsupported_features": frozenset(),
        "allowed_harnesses": frozenset({"claude_code", "codex", "opencode"}),
        "opencode_provider_id": "zai-coding-plan",
        "opencode_key_env_var": "ZHIPU_API_KEY",
        "opencode_models": ("glm-5.3", "glm-5.3-flash"),
        "balance_url": None,
        "model_slots": ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"),
    },
    "deepseek": {
        "anthropic_base_url": "https://api.deepseek.com/anthropic",
        "auth_env_var": "DEEPSEEK_API_KEY",
        "claude_models": ("deepseek-flash[1m]", "deepseek-v4-pro"),
        "claude_env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "786432"},
        "unsupported_features": frozenset(ALL_FEATURES),
        "allowed_harnesses": frozenset({"claude_code", "codex", "opencode", "grok", "muse"}),
        "opencode_provider_id": "deepseek",
        "opencode_key_env_var": "DEEPSEEK_API_KEY",
        "opencode_models": ("deepseek-flash", "deepseek-v4-pro"),
        "balance_url": "https://api.deepseek.com/user/balance",
        "model_slots": ("ANTHROPIC_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL"),
    },
}


def expected_environ(name: str, model: str, key_value: str) -> dict[str, str]:
    # §9.1: ANTHROPIC_BASE_URL, the profile's claude_env pairs, the model slots, and ANTHROPIC_AUTH_TOKEN.
    profile = EXPECTED_PROFILES[name]
    environ = {"ANTHROPIC_BASE_URL": profile["anthropic_base_url"], **profile["claude_env"]}
    environ.update({slot: model for slot in profile["model_slots"]})
    environ["ANTHROPIC_AUTH_TOKEN"] = key_value
    return environ


def assert_no_http(endpoint: Any) -> None:
    assert endpoint.requests == [] and endpoint.client_options == [], "this function makes no I/O"


@pytest.mark.parametrize("name", ["glm", "deepseek"])
def test_declared_profile_matches_the_spec_table(name: str, backends_api) -> None:
    # §9.1 "The two declared profiles", field by field.
    profiles = {profile.name.value: profile for profile in backends_api.HARNESS_BACKENDS}
    profile = profiles[name]
    expected = EXPECTED_PROFILES[name]
    assert profile.name is backends_api.HarnessBackendName(name)
    assert profile.anthropic_base_url == expected["anthropic_base_url"]
    assert profile.auth_env_var == expected["auth_env_var"]
    assert profile.claude_models == expected["claude_models"]
    assert dict(profile.claude_env) == expected["claude_env"]
    assert {feature.value for feature in profile.unsupported_features} == expected["unsupported_features"]
    assert {harness.value for harness in profile.allowed_harnesses} == expected["allowed_harnesses"]
    assert profile.opencode_provider_id == expected["opencode_provider_id"]
    assert profile.opencode_key_env_var == expected["opencode_key_env_var"]
    assert profile.opencode_models == expected["opencode_models"]
    assert profile.balance_url == expected["balance_url"]


def test_harness_backends_is_declared_in_name_order_and_exported(backends_api) -> None:
    # §9.1 and §12.3 rows 14-15: HARNESS_BACKENDS in HarnessBackendName order, re-exported from vidbyte.lib.configs.
    import vidbyte.lib.configs as configs

    assert isinstance(backends_api.HARNESS_BACKENDS, tuple)
    assert [profile.name for profile in backends_api.HARNESS_BACKENDS] == list(backends_api.HarnessBackendName)
    assert configs.HARNESS_BACKENDS is backends_api.HARNESS_BACKENDS
    assert "HARNESS_BACKENDS" in configs.__all__


def test_module_functions_are_the_harness_backends_static_methods(backends_api) -> None:
    # D-16 and §12.3 row 45: six module-level functions bound to HarnessBackends, with a literal __all__.
    names = ("list_harness_backends", "build_claude_backend_env", "check_backend_ready", "check_backend_compat", "get_deepseek_balance", "build_opencode_backend_provider")
    for name in names:
        assert getattr(backends_api.module, name) is getattr(backends_api.HarnessBackends, name), name
        assert name in backends_api.module.__all__, name


def test_list_harness_backends_returns_both_profiles_without_keys_or_io(backends_api, deepseek_endpoint) -> None:
    # §6.3.6: no I/O, only EC-5 applies (so no key is needed), backends in HarnessBackendName order.
    backends = backends_api.list_harness_backends()
    assert isinstance(backends, tuple)
    assert backends == backends_api.HARNESS_BACKENDS
    assert [backend.name.value for backend in backends] == ["glm", "deepseek"]
    assert_no_http(deepseek_endpoint)


def test_deepseek_env_has_exactly_the_spec_keys_and_hides_the_value(backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch, check_native_error) -> None:
    # AC-13, first half: DEEPSEEK_API_KEY set -> a ClaudeBackendEnv whose as_environ() has exactly the §9.1 keys.
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    env = backends_api.build_claude_backend_env(backends_api.HarnessBackendName.DEEPSEEK)
    assert isinstance(env, backends_api.ClaudeBackendEnv)
    assert env.backend is backends_api.HarnessBackendName.DEEPSEEK
    assert env.model == "deepseek-flash[1m]", "the first claude_models entry is the default"
    assert env.as_environ() == expected_environ("deepseek", "deepseek-flash[1m]", FAKE_DEEPSEEK_VALUE)
    assert "ANTHROPIC_AUTH_TOKEN" not in env.public_env and FAKE_DEEPSEEK_VALUE not in env.public_env.values()
    assert FAKE_DEEPSEEK_VALUE not in repr(env) and FAKE_DEEPSEEK_VALUE not in str(env), "INV-6: the key is repr=False"
    assert_no_http(deepseek_endpoint)
    # AC-13, second half: the same call with the variable unset raises backend.not_signed_in naming the variable.
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    with pytest.raises(backends_api.NativeHostError) as caught:
        backends_api.build_claude_backend_env(backends_api.HarnessBackendName.DEEPSEEK)
    check_native_error(caught.value, code="backend.not_signed_in", token="DEEPSEEK_API_KEY", operation="build_claude_backend_env")
    assert "DEEPSEEK_API_KEY" in str(caught.value)


def test_glm_env_fills_every_model_slot_with_the_chosen_model(backends_api, monkeypatch: pytest.MonkeyPatch) -> None:
    # §9.1: GLM's three model slots take the chosen model; the haiku slot stays the fixed public pair.
    monkeypatch.setenv("GLM_API_KEY", FAKE_GLM_VALUE)
    env = backends_api.build_claude_backend_env("glm", model="glm-5.3-flash[1m]")
    assert env.backend is backends_api.HarnessBackendName.GLM, "a value string is accepted like the member"
    assert env.model == "glm-5.3-flash[1m]"
    assert env.as_environ() == expected_environ("glm", "glm-5.3-flash[1m]", FAKE_GLM_VALUE)


def test_every_declared_model_builds_the_exact_environment(backends_api, monkeypatch: pytest.MonkeyPatch) -> None:
    # Exhaustive over the declared profiles: each backend and model gives exactly its own keys, never the other's.
    monkeypatch.setenv("GLM_API_KEY", FAKE_GLM_VALUE)
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    values = {"glm": FAKE_GLM_VALUE, "deepseek": FAKE_DEEPSEEK_VALUE}
    for name, profile in EXPECTED_PROFILES.items():
        for model in profile["claude_models"]:
            environ = backends_api.build_claude_backend_env(backends_api.HarnessBackendName(name), model=model).as_environ()
            assert environ == expected_environ(name, model, values[name]), (name, model)


def test_env_reads_the_key_variable_on_every_call(backends_api, monkeypatch: pytest.MonkeyPatch) -> None:
    # Spec §13: the key is read from os.environ on each call, never cached from an earlier one.
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    first = backends_api.build_claude_backend_env(backends_api.HarnessBackendName.DEEPSEEK)
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECOND_DEEPSEEK_VALUE)
    second = backends_api.build_claude_backend_env(backends_api.HarnessBackendName.DEEPSEEK)
    assert first.as_environ()["ANTHROPIC_AUTH_TOKEN"] == FAKE_DEEPSEEK_VALUE
    assert second.as_environ()["ANTHROPIC_AUTH_TOKEN"] == SECOND_DEEPSEEK_VALUE


def test_env_public_mapping_is_read_only_and_as_environ_is_a_fresh_copy(backends_api, monkeypatch: pytest.MonkeyPatch) -> None:
    # §9.1 common rules: mapping fields are a read-only MappingProxyType copy; as_environ() returns a new dict.
    monkeypatch.setenv("GLM_API_KEY", FAKE_GLM_VALUE)
    env = backends_api.build_claude_backend_env(backends_api.HarnessBackendName.GLM)
    assert isinstance(env.public_env, MappingProxyType)
    with pytest.raises(TypeError):
        env.public_env["ANTHROPIC_BASE_URL"] = "https://elsewhere.invalid"
    environ = env.as_environ()
    environ["ANTHROPIC_BASE_URL"] = "https://elsewhere.invalid"
    assert env.as_environ()["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"


def test_check_backend_compat_accepts_requests_the_backend_honours(backends_api, deepseek_endpoint) -> None:
    # §6.3.6: allowed harness and no unsupported feature returns None, with no key and no I/O.
    request = backends_api.BackendCompatRequest
    harness = backends_api.NativeHarness
    every_feature = frozenset(backends_api.BackendFeature)
    assert backends_api.check_backend_compat(backends_api.HarnessBackendName.GLM, request(harness=harness.CLAUDE_CODE, features=every_feature)) is None
    assert backends_api.check_backend_compat("glm", request(harness=harness.OPENCODE)) is None
    assert backends_api.check_backend_compat(backends_api.HarnessBackendName.DEEPSEEK, request(harness=harness.GROK)) is None
    assert_no_http(deepseek_endpoint)


def test_compat_refuses_unsupported_features_then_disallowed_harness_without_network(backends_api, deepseek_endpoint, check_native_error) -> None:
    # AC-14: DeepSeek with MCP_SERVERS -> feature_unsupported; GLM with GROK -> harness_not_allowed; no network call.
    request = backends_api.BackendCompatRequest
    with pytest.raises(backends_api.NativeHostError) as first:
        backends_api.check_backend_compat(backends_api.HarnessBackendName.DEEPSEEK, request(harness=backends_api.NativeHarness.CLAUDE_CODE, features=frozenset({backends_api.BackendFeature.MCP_SERVERS})))
    check_native_error(first.value, code="backend.feature_unsupported", token="features", operation="check_backend_compat")
    with pytest.raises(backends_api.NativeHostError) as second:
        backends_api.check_backend_compat(backends_api.HarnessBackendName.GLM, request(harness=backends_api.NativeHarness.GROK))
    check_native_error(second.value, code="backend.harness_not_allowed", token="allowed_harnesses", operation="check_backend_compat")
    assert_no_http(deepseek_endpoint)


def test_compat_lists_every_offending_feature_sorted_for_every_subset(backends_api) -> None:
    # EC-136 as a property: for each of the 2,048 feature subsets, DeepSeek refuses exactly the non-empty ones,
    # and context["features"] names every offending value in sorted order.
    request = backends_api.BackendCompatRequest
    deepseek = backends_api.HarnessBackendName.DEEPSEEK
    members = list(backends_api.BackendFeature)
    for size in range(len(members) + 1):
        for subset in itertools.combinations(members, size):
            compat = request(harness=backends_api.NativeHarness.CLAUDE_CODE, features=frozenset(subset))
            if not subset:
                assert backends_api.check_backend_compat(deepseek, compat) is None
                continue
            with pytest.raises(backends_api.NativeHostError) as caught:
                backends_api.check_backend_compat(deepseek, compat)
            assert caught.value.failure_code is backends_api.FailureCode.BACKEND_FEATURE_UNSUPPORTED
            listed = caught.value.context["features"]
            positions = [listed.index(value) for value in sorted(feature.value for feature in subset)]
            assert positions == sorted(positions), f"features must be listed sorted: {listed!r}"


def test_compat_refuses_every_harness_glm_does_not_allow_whatever_the_features(backends_api) -> None:
    # EC-135 as a property: GLM refuses GROK and MUSE with or without features, and allows the other three.
    request = backends_api.BackendCompatRequest
    glm = backends_api.HarnessBackendName.GLM
    for harness in backends_api.NativeHarness:
        for features in (frozenset(), frozenset(backends_api.BackendFeature)):
            compat = request(harness=harness, features=features)
            if harness.value in EXPECTED_PROFILES["glm"]["allowed_harnesses"]:
                assert backends_api.check_backend_compat(glm, compat) is None
                continue
            with pytest.raises(backends_api.NativeHostError) as caught:
                backends_api.check_backend_compat(glm, compat)
            assert caught.value.failure_code is backends_api.FailureCode.BACKEND_HARNESS_NOT_ALLOWED, harness


@pytest.mark.parametrize(("name", "provider_id", "source", "child", "models"), [
    ("glm", "zai-coding-plan", "GLM_API_KEY", "ZHIPU_API_KEY", ("glm-5.3", "glm-5.3-flash")),
    ("deepseek", "deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY", ("deepseek-flash", "deepseek-v4-pro")),
])
def test_opencode_provider_names_the_built_in_provider_without_a_key(name: str, provider_id: str, source: str, child: str, models: tuple[str, ...], backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    # D-16 / §6.3.6: no I/O and no key check; the record holds names only, never a key value.
    provider = backends_api.build_opencode_backend_provider(name)
    assert isinstance(provider, backends_api.OpencodeBackendProvider)
    assert provider.backend is backends_api.HarnessBackendName(name)
    assert (provider.provider_id, provider.source_env_var, provider.child_env_var, provider.model_ids) == (provider_id, source, child, models)
    monkeypatch.setenv(source, FAKE_DEEPSEEK_VALUE)
    with_key = backends_api.build_opencode_backend_provider(backends_api.HarnessBackendName(name))
    assert with_key == provider, "the key's presence changes nothing"
    assert FAKE_DEEPSEEK_VALUE not in repr(with_key)
    assert_no_http(deepseek_endpoint)
