"""FILE: tests/features/native_backends/test_native_backends_records.py

PURPOSE: Construction checks for the seven vidbyte.lib.dataclasses.harness_backends records (§9.1): every bad field raises ConfigurationError naming `<Record>.<field>` (INV-5, EC-134), secret fields never reach a message or repr (INV-6), and collection fields are frozen copies.
ROLE IN CODEBASE: Start here when a backend record accepts a value it should refuse, or a profile with a secret in claude_env slips through. The validator itself (RecordFieldValidator) is tested in tests/features/grok_host/; these tests prove each record applies it to each field.
ARCHITECTURE NOTE: Bad records are built with dataclasses.replace from a valid one, so exactly one field is wrong per case and the message must name that field.
FUNCTION INVENTORY: valid_* build one valid record each; BAD_FIELDS lists one bad value per checked field; the test_* functions run them.
COMMON MODIFICATION PATTERNS: A new field on a §9.1 backend record is one more BAD_FIELDS entry.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert the full message text; the spec fixes only `<Record>.<field>`. 2. Do not add a case the spec does not state.
KNOWN EDGE CASES: §9.1's common rule converts set fields to frozenset, while EC-134 refuses BackendCompatRequest.features that is not a frozenset; the cases here use a list of strings, which both readings refuse (see the test plan's spec notes).
RELATED DOCS: tests/features/native_backends/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1, EC-134, INV-5, INV-6
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/native_backends/test_native_backends_records.py
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from types import MappingProxyType, SimpleNamespace
from typing import Any

import pytest

SECRET_TEXT = "fake-secret-value-not-a-key-0009"


def valid_backend(api: SimpleNamespace) -> Any:
    return api.HarnessBackend(
        name=api.HarnessBackendName.GLM,
        anthropic_base_url="https://api.z.ai/api/anthropic",
        auth_env_var="GLM_API_KEY",
        claude_models=("glm-5.3[1m]",),
        claude_env={"API_TIMEOUT_MS": "3000000"},
        unsupported_features=frozenset(),
        allowed_harnesses=frozenset({api.NativeHarness.CLAUDE_CODE}),
        opencode_provider_id="zai-coding-plan",
        opencode_key_env_var="ZHIPU_API_KEY",
        opencode_models=("glm-5.3",),
        balance_url=None,
    )


def valid_entry(api: SimpleNamespace) -> Any:
    return api.DeepseekBalanceEntry(currency="CNY", total_balance=Decimal("1.00"), granted_balance=Decimal("0"), topped_up_balance=Decimal("1.00"))


def valid_records(api: SimpleNamespace) -> dict[str, Any]:
    return {
        "HarnessBackend": valid_backend(api),
        "ClaudeBackendEnv": api.ClaudeBackendEnv(backend=api.HarnessBackendName.GLM, model="glm-5.3[1m]", public_env={"ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic"}, auth_token=SECRET_TEXT),
        "OpencodeBackendProvider": api.OpencodeBackendProvider(backend=api.HarnessBackendName.GLM, provider_id="zai-coding-plan", source_env_var="GLM_API_KEY", child_env_var="ZHIPU_API_KEY", model_ids=("glm-5.3",)),
        "BackendCompatRequest": api.BackendCompatRequest(harness=api.NativeHarness.CLAUDE_CODE),
        "DeepseekBalanceEntry": valid_entry(api),
        "DeepseekBalance": api.DeepseekBalance(is_available=True, balances=(valid_entry(api),)),
        "BackendReadiness": api.BackendReadiness(backend=api.HarnessBackendName.GLM, remote_verified=False),
    }


BAD_FIELDS = [
    # HarnessBackend: enums and sets, https URLs, env-var names, non-empty model tuples, no secret in claude_env.
    ("HarnessBackend", "name", "glm"),
    ("HarnessBackend", "anthropic_base_url", "http://api.z.ai/api/anthropic"),
    ("HarnessBackend", "auth_env_var", "glm_api_key"),
    ("HarnessBackend", "auth_env_var", "GLM API KEY"),
    ("HarnessBackend", "claude_models", ()),
    ("HarnessBackend", "claude_env", {"ANTHROPIC_AUTH_TOKEN": SECRET_TEXT}),
    ("HarnessBackend", "unsupported_features", ["mcp_servers"]),
    ("HarnessBackend", "allowed_harnesses", ["claude_code"]),
    ("HarnessBackend", "opencode_key_env_var", "1ZHIPU"),
    ("HarnessBackend", "opencode_models", ()),
    ("HarnessBackend", "balance_url", "http://api.deepseek.com/user/balance"),
    # The other records: types and closed sets.
    ("ClaudeBackendEnv", "backend", "glm"),
    ("OpencodeBackendProvider", "backend", "glm"),
    ("BackendCompatRequest", "harness", "grok"),
    ("BackendCompatRequest", "features", ["mcp_servers"]),
    ("BackendCompatRequest", "features", frozenset({"mcp_servers"})),
    ("DeepseekBalanceEntry", "total_balance", 1.5),
    ("DeepseekBalance", "is_available", "true"),
    ("BackendReadiness", "backend", "deepseek"),
    ("BackendReadiness", "remote_verified", 1),
]


@pytest.mark.parametrize(("record", "field_name", "value"), BAD_FIELDS, ids=[f"{record}.{name}-{index}" for index, (record, name, _) in enumerate(BAD_FIELDS)])
def test_bad_field_raises_configuration_error_naming_the_field(record: str, field_name: str, value: Any, backends_api) -> None:
    # §9.1 / INV-5 / EC-134: a failure raises ConfigurationError whose message names <Record>.<field>.
    valid = valid_records(backends_api)[record]
    with pytest.raises(backends_api.ConfigurationError) as caught:
        dataclasses.replace(valid, **{field_name: value})
    assert f"{record}.{field_name}" in str(caught.value), str(caught.value)
    assert SECRET_TEXT not in str(caught.value), "INV-6: a secret value is never quoted in a message"


def test_valid_records_build_and_are_frozen(backends_api) -> None:
    # §9.1: every record is @dataclass(frozen=True, slots=True).
    for name, record in valid_records(backends_api).items():
        assert dataclasses.is_dataclass(record), name
        assert not hasattr(record, "__dict__"), f"{name} is slots=True"
        first_field = dataclasses.fields(record)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(record, first_field, getattr(record, first_field))


def test_claude_backend_env_never_shows_its_token(backends_api) -> None:
    # §9.1 / INV-6: auth_token is repr=False; repr and str never show it; as_environ() adds it as ANTHROPIC_AUTH_TOKEN.
    env = valid_records(backends_api)["ClaudeBackendEnv"]
    assert SECRET_TEXT not in repr(env) and SECRET_TEXT not in str(env)
    assert env.as_environ() == {"ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic", "ANTHROPIC_AUTH_TOKEN": SECRET_TEXT}


def test_claude_backend_env_rejects_a_non_text_token_without_quoting_it(backends_api) -> None:
    # INV-6: a bad secret field is named, never quoted.
    env = valid_records(backends_api)["ClaudeBackendEnv"]
    with pytest.raises(backends_api.ConfigurationError) as caught:
        dataclasses.replace(env, auth_token=SECRET_TEXT.encode("utf-8"))
    assert "ClaudeBackendEnv.auth_token" in str(caught.value)
    assert SECRET_TEXT not in str(caught.value)


def test_collection_fields_are_frozen_copies(backends_api) -> None:
    # §9.1 common rules: tuples become tuple, mappings a read-only MappingProxyType copy.
    source_env = {"API_TIMEOUT_MS": "3000000"}
    backend = dataclasses.replace(valid_backend(backends_api), claude_models=["glm-5.3[1m]"], claude_env=source_env)
    source_env["API_TIMEOUT_MS"] = "1"
    assert backend.claude_models == ("glm-5.3[1m]",)
    assert isinstance(backend.claude_env, MappingProxyType)
    assert backend.claude_env["API_TIMEOUT_MS"] == "3000000", "the record keeps its own copy"
    balance = backends_api.DeepseekBalance(is_available=True, balances=[valid_entry(backends_api)])
    assert isinstance(balance.balances, tuple)


def test_compat_request_defaults_to_no_features(backends_api) -> None:
    # §9.1: features defaults to an empty frozenset.
    request = backends_api.BackendCompatRequest(harness=backends_api.NativeHarness.GROK)
    assert request.features == frozenset()
    assert isinstance(request.features, frozenset)


def test_readiness_balance_is_optional_and_typed(backends_api) -> None:
    # §9.1: BackendReadiness.balance is an optional DeepseekBalance.
    readiness = valid_records(backends_api)["BackendReadiness"]
    assert readiness.balance is None
    with pytest.raises(backends_api.ConfigurationError) as caught:
        dataclasses.replace(readiness, balance={"is_available": True})
    assert "BackendReadiness.balance" in str(caught.value)
