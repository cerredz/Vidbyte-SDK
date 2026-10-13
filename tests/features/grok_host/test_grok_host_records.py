"""FILE: tests/features/grok_host/test_grok_host_records.py

PURPOSE: The record and validator contract for the Grok host and the shared native records: RecordFieldValidator's 13 checks (D-8), the shared native_hosts records (NativeTurnHandle, NativeTokenUsage, NativeApprovalDecision, NativeTurnResult, NativeInterruptResult), and the Grok request and settings records with their EC-23 and EC-33 rows.
ROLE IN CODEBASE: Start here when a bad value gets past a record, or a good one is refused. These are the INV-5 boundary checks that run before any process starts.
ARCHITECTURE NOTE: Each table row overrides one field of a known-good record, so a failure can only come from that field. Every rejection must be a ConfigurationError whose message names "<Record>.<field>" (spec §9.1 common rules).
FUNCTION INVENTORY: build_record constructs a record from base fields plus one override; expect_rejected asserts the ConfigurationError shape; the *_CASES tables hold the rows; the test_* functions run them.
COMMON MODIFICATION PATTERNS: Add a row to the matching table when spec §9.1 adds a check; keep one bad value per row.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert that a message quotes a value; the spec only says when it may not. 2. Do not test that a plain set or list is refused where §9.1 says it is converted.
KNOWN EDGE CASES: The spec says set fields are converted to frozenset but EC-23 also says allowed_tool_kinds must be a frozenset of AcpToolKind, so only a set or frozenset of plain value strings is used as the bad value. A long bad value must never be quoted in the message.
RELATED DOCS: tests/features/grok_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1, EC-23, EC-33, D-8
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host/test_grok_host_records.py
"""

from __future__ import annotations

import dataclasses
import importlib
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

TURN_ID = "0123456789abcdef0123456789abcdef"
SESSION = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b"
LONG_HIDDEN = "-" + "h" * 100


def validator() -> Any:
    return importlib.import_module("vidbyte.lib.dataclasses.validation").RecordFieldValidator


def records(module: str) -> Any:
    return importlib.import_module(f"vidbyte.lib.dataclasses.{module}")


def build_record(record_type: Any, base: dict[str, Any], overrides: dict[str, Any]) -> Any:
    return record_type(**{**base, **overrides})


def expect_rejected(grok_api: Any, record_name: str, field_name: str, build: Any) -> Any:
    with pytest.raises(grok_api.ConfigurationError) as caught:
        build()
    message = str(caught.value)
    assert f"{record_name}.{field_name}" in message, f"message must name {record_name}.{field_name}: {message!r}"
    return caught.value


# RecordFieldValidator: (method, args, kwargs) that must pass, and that must raise.
def validator_accepts(tmp_path: Path, enums: Any) -> list[tuple[str, tuple[Any, ...], dict[str, Any], Any]]:
    return [
        ("require_text", ("abc", "f"), {"max_chars": 3}, "abc"),
        ("require_text", ("grok-4", "f"), {"max_chars": 128, "pattern": r"^[^\s-][^\s]*$"}, "grok-4"),
        ("require_optional_text", (None, "f"), {"max_chars": 3}, None),
        ("require_number", (0.5, "f"), {"maximum": 1.0}, 0.5),
        ("require_number", (1, "f"), {"maximum": 1.0}, 1),
        ("require_int", (16, "f"), {"minimum": 1, "maximum": 16}, 16),
        ("require_optional_count", (0, "f"), {}, 0),
        ("require_optional_count", (None, "f"), {}, None),
        ("require_bool", (False, "f"), {}, False),
        ("require_enum", (enums.NativeHarness.GROK, enums.NativeHarness, "f"), {}, enums.NativeHarness.GROK),
        ("require_enum_set", (frozenset({enums.AcpToolKind.EDIT}), enums.AcpToolKind, "f"), {}, frozenset({enums.AcpToolKind.EDIT})),
        ("require_argv", (("grok", "--x"), "f"), {}, ("grok", "--x")),
        ("require_text_mapping", ({"A_1": "v"}, "f"), {"key_pattern": r"^[A-Z_0-9]+$", "max_items": 1}, None),
        ("require_uuid", (SESSION.upper(), "f"), {}, SESSION.upper()),
        ("require_directory", (tmp_path, "f"), {}, tmp_path),
        ("require_decimal", (Decimal("0"), "f"), {}, Decimal("0")),
    ]


def validator_rejects(tmp_path: Path, enums: Any) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
    file_path = tmp_path / "a-file.txt"
    file_path.write_text("x", encoding="utf-8")
    return [
        ("require_text", ("", "f"), {"max_chars": 3}),
        ("require_text", ("   ", "f"), {"max_chars": 3}),
        ("require_text", ("abcd", "f"), {"max_chars": 3}),
        ("require_text", (True, "f"), {"max_chars": 3}),
        ("require_text", ("-x", "f"), {"max_chars": 128, "pattern": r"^[^\s-][^\s]*$"}),
        ("require_text", ("a b", "f"), {"max_chars": 128, "pattern": r"^[^\s-][^\s]*$"}),
        ("require_optional_text", ("", "f"), {"max_chars": 3}),
        ("require_number", (True, "f"), {"maximum": 10.0}),
        ("require_number", (math.nan, "f"), {"maximum": 10.0}),
        ("require_number", (math.inf, "f"), {"maximum": math.inf}),
        ("require_number", (-math.inf, "f"), {"maximum": 10.0}),
        ("require_number", (0, "f"), {"maximum": 10.0}),
        ("require_number", (-1.0, "f"), {"maximum": 10.0}),
        ("require_number", (10.5, "f"), {"maximum": 10.0}),
        ("require_number", ("1", "f"), {"maximum": 10.0}),
        ("require_int", (True, "f"), {"minimum": 0, "maximum": 2}),
        ("require_int", (1.0, "f"), {"minimum": 0, "maximum": 2}),
        ("require_int", (3, "f"), {"minimum": 0, "maximum": 2}),
        ("require_int", (-1, "f"), {"minimum": 0, "maximum": 2}),
        ("require_optional_count", (-1, "f"), {}),
        ("require_optional_count", (False, "f"), {}),
        ("require_bool", (1, "f"), {}),
        ("require_bool", ("true", "f"), {}),
        ("require_enum", ("grok", enums.NativeHarness, "f"), {}),
        ("require_enum_set", ({"edit"}, enums.AcpToolKind, "f"), {}),
        ("require_enum_set", (frozenset({"edit"}), enums.AcpToolKind, "f"), {}),
        ("require_argv", ((), "f"), {}),
        ("require_argv", (("",), "f"), {}),
        ("require_argv", (("a\x00b",), "f"), {}),
        ("require_argv", (["grok"], "f"), {}),
        ("require_text_mapping", ({"bad key": "v"}, "f"), {"key_pattern": r"^[A-Z_0-9]+$", "max_items": 4}),
        ("require_text_mapping", ({"A": 1}, "f"), {"key_pattern": r"^[A-Z_0-9]+$", "max_items": 4}),
        ("require_text_mapping", ({"A": "v", "B": "w"}, "f"), {"key_pattern": r"^[A-Z_0-9]+$", "max_items": 1}),
        ("require_uuid", ("not-a-uuid", "f"), {}),
        ("require_uuid", (SESSION + "0", "f"), {}),
        ("require_directory", (Path("relative/folder"), "f"), {}),
        ("require_directory", (tmp_path / "missing", "f"), {}),
        ("require_directory", (file_path, "f"), {}),
        ("require_directory", (str(tmp_path), "f"), {}),
        ("require_decimal", (Decimal("NaN"), "f"), {}),
        ("require_decimal", (Decimal("-0.01"), "f"), {}),
        ("require_decimal", (Decimal("Infinity"), "f"), {}),
        ("require_decimal", (1.5, "f"), {}),
    ]


def enums_module() -> Any:
    return importlib.import_module("vidbyte.lib.enums.native_hosts")


def test_validator_has_exactly_the_thirteen_static_methods() -> None:
    # D-8 / §9.1: one canonical validator, a class of @staticmethods.
    checker = validator()
    expected = {
        "require_text", "require_optional_text", "require_number", "require_int", "require_optional_count", "require_bool", "require_enum",
        "require_enum_set", "require_argv", "require_text_mapping", "require_uuid", "require_directory", "require_decimal",
    }
    public = {name for name in vars(checker) if not name.startswith("_")}
    assert public == expected
    assert all(isinstance(vars(checker)[name], staticmethod) for name in expected)


def test_validator_accepts_and_returns_good_values(tmp_path: Path) -> None:
    checker = validator()
    for method, args, kwargs, expected in validator_accepts(tmp_path, enums_module()):
        returned = getattr(checker, method)(*args, **kwargs)
        if expected is not None:
            assert returned == expected, (method, args)


def test_validator_rejects_each_bad_value_naming_the_field(grok_api, tmp_path: Path) -> None:
    checker = validator()
    for method, args, kwargs in validator_rejects(tmp_path, enums_module()):
        positional = list(args)
        name_index = 2 if method in ("require_enum", "require_enum_set") else 1
        positional[name_index] = "Probe.field_under_test"
        with pytest.raises(grok_api.ConfigurationError) as caught:
            getattr(checker, method)(*positional, **kwargs)
        assert "Probe.field_under_test" in str(caught.value), (method, args)


def handle_base(grok_api: Any) -> dict[str, Any]:
    return {"harness": grok_api.NativeHarness.GROK, "session_id": SESSION, "turn_id": TURN_ID}


HANDLE_CASES = [
    pytest.param("harness", "grok", id="harness-string"),
    pytest.param("session_id", "", id="session-empty"),
    pytest.param("session_id", "ses 1", id="session-whitespace"),
    pytest.param("session_id", "s" * 161, id="session-too-long"),
    pytest.param("turn_id", TURN_ID.upper(), id="turn-upper"),
    pytest.param("turn_id", TURN_ID[:31], id="turn-short"),
    pytest.param("turn_id", TURN_ID[:31] + "g", id="turn-not-hex"),
    pytest.param("turn_id", SESSION, id="turn-dashed-uuid"),
]


@pytest.mark.parametrize(("field_name", "bad"), HANDLE_CASES)
def test_native_turn_handle_rejects(field_name: str, bad: Any, grok_api) -> None:
    expect_rejected(grok_api, "NativeTurnHandle", field_name, lambda: build_record(grok_api.NativeTurnHandle, handle_base(grok_api), {field_name: bad}))


def test_native_turn_handle_accepts_a_160_char_session(grok_api) -> None:
    handle = grok_api.NativeTurnHandle(harness=grok_api.NativeHarness.OPENCODE, session_id="s" * 160, turn_id=TURN_ID)
    assert handle == grok_api.NativeTurnHandle(harness=grok_api.NativeHarness.OPENCODE, session_id="s" * 160, turn_id=TURN_ID)


USAGE_CASES = [
    pytest.param("input_tokens", True, id="bool"),
    pytest.param("output_tokens", -1, id="negative"),
    pytest.param("total_tokens", 1.5, id="float"),
    pytest.param("cost_usd", Decimal("NaN"), id="cost-nan"),
    pytest.param("cost_usd", Decimal("-1"), id="cost-negative"),
    pytest.param("cost_usd", 0.25, id="cost-float"),
]


@pytest.mark.parametrize(("field_name", "bad"), USAGE_CASES)
def test_native_token_usage_rejects(field_name: str, bad: Any, grok_api) -> None:
    usage_type = records("native_hosts").NativeTokenUsage
    expect_rejected(grok_api, "NativeTokenUsage", field_name, lambda: usage_type(**{field_name: bad}))


def test_native_token_usage_defaults_to_unknown_not_zero() -> None:
    # INV-15: unknown usage is None, never 0.
    usage = records("native_hosts").NativeTokenUsage()
    assert all(getattr(usage, field.name) is None for field in dataclasses.fields(usage))


def decision(grok_api: Any, **overrides: Any) -> Any:
    decision_type = records("native_hosts").NativeApprovalDecision
    return build_record(decision_type, {"request_kind": "acp.permission:edit", "title": "", "outcome": grok_api.ApprovalOutcome.REJECTED}, overrides)


@pytest.mark.parametrize(("field_name", "bad"), [("request_kind", ""), ("request_kind", "k" * 129), ("title", "t" * 201), ("outcome", "rejected")])
def test_native_approval_decision_rejects(field_name: str, bad: Any, grok_api) -> None:
    expect_rejected(grok_api, "NativeApprovalDecision", field_name, lambda: decision(grok_api, **{field_name: bad}))


def result_base(grok_api: Any) -> dict[str, Any]:
    return {"handle": grok_api.NativeTurnHandle(**handle_base(grok_api)), "status": grok_api.NativeTurnStatus.COMPLETED}


def result_cases(grok_api: Any) -> list[tuple[str, str, dict[str, Any]]]:
    status = grok_api.NativeTurnStatus
    cap = grok_api.constants.NATIVE_MAX_RECORDED_DECISIONS
    return [
        ("status-running", "status", {"status": status.RUNNING}),
        ("status-failed", "status", {"status": status.FAILED}),
        ("interrupted-without-source", "interrupt_source", {"status": status.INTERRUPTED}),
        ("completed-with-source", "interrupt_source", {"interrupt_source": grok_api.InterruptSource.CALLER}),
        ("stop-reason-too-long", "stop_reason", {"stop_reason": "r" * 129}),
        ("text-over-cap", "text", {"text": "x" * (grok_api.constants.NATIVE_RESULT_TEXT_MAX_CHARS + 1)}),
        ("too-many-decisions", "decisions", {"decisions": tuple(decision(grok_api) for _ in range(cap + 1))}),
        ("dropped-negative", "decisions_dropped", {"decisions_dropped": -1}),
        ("truncated-not-bool", "text_truncated", {"text_truncated": 1}),
    ]


def test_native_turn_result_rejects_each_bad_field(grok_api) -> None:
    for label, field_name, overrides in result_cases(grok_api):
        error = expect_rejected(grok_api, "NativeTurnResult", field_name, lambda overrides=overrides: build_record(grok_api.NativeTurnResult, result_base(grok_api), overrides))
        assert error is not None, label


def test_native_turn_result_converts_decisions_to_a_tuple(grok_api) -> None:
    result = grok_api.NativeTurnResult(**result_base(grok_api), decisions=[decision(grok_api)])
    assert isinstance(result.decisions, tuple) and len(result.decisions) == 1
    assert result.usage is None and result.text == "" and result.decisions_dropped == 0


def test_native_interrupt_result_needs_a_real_bool(grok_api) -> None:
    interrupt_type = records("native_hosts").NativeInterruptResult
    handle = grok_api.NativeTurnHandle(**handle_base(grok_api))
    expect_rejected(grok_api, "NativeInterruptResult", "was_running", lambda: interrupt_type(handle=handle, was_running=0))


def settings_base(grok_api: Any, tmp_path: Path) -> dict[str, Any]:
    return {"workspace": tmp_path}


def settings_cases(tmp_path: Path) -> list[tuple[str, str, Any]]:
    a_file = tmp_path / "plain-file.txt"
    a_file.write_text("x", encoding="utf-8")
    return [
        ("workspace-relative", "workspace", Path("relative")),
        ("workspace-missing", "workspace", tmp_path / "missing"),
        ("workspace-file", "workspace", a_file),
        ("workspace-str", "workspace", str(tmp_path)),
        ("command-empty", "grok_command", ()),
        ("command-empty-item", "grok_command", ("",)),
        ("command-nul", "grok_command", ("gr\x00ok",)),
        ("control-bool", "control_timeout_seconds", True),
        ("control-nan", "control_timeout_seconds", math.nan),
        ("control-zero", "control_timeout_seconds", 0),
        ("control-over-cap", "control_timeout_seconds", 600.5),
        ("live-zero", "max_live_turns", 0),
        ("live-over-cap", "max_live_turns", 17),
        ("live-bool", "max_live_turns", True),
        ("live-float", "max_live_turns", 2.0),
    ]


def test_grok_host_settings_rejects_each_bad_field(grok_api, tmp_path: Path) -> None:
    for label, field_name, bad in settings_cases(tmp_path):
        error = expect_rejected(grok_api, "GrokHostSettings", field_name, lambda field_name=field_name, bad=bad: build_record(grok_api.GrokHostSettings, settings_base(grok_api, tmp_path), {field_name: bad}))
        assert error is not None, label


def test_grok_host_settings_defaults_and_no_model_field(grok_api, tmp_path: Path) -> None:
    # §9.1 defaults; C012: no model field on a *Settings class.
    settings = grok_api.GrokHostSettings(workspace=tmp_path)
    assert settings.grok_command is None
    assert settings.control_timeout_seconds == grok_api.constants.NATIVE_CONTROL_TIMEOUT_SECONDS == 30.0
    assert settings.max_live_turns == grok_api.constants.NATIVE_MAX_LIVE_TURNS_DEFAULT == 4
    assert "model" not in {field.name for field in dataclasses.fields(settings)}
    edge = grok_api.GrokHostSettings(workspace=tmp_path, grok_command=("grok",), control_timeout_seconds=600.0, max_live_turns=16)
    assert edge.max_live_turns == 16


def turn_request_cases(grok_api: Any) -> list[tuple[str, str, Any]]:
    long_prompt = "p" * (grok_api.constants.NATIVE_PROMPT_MAX_CHARS + 1)
    rows: list[tuple[str, str, Any]] = [
        ("prompt-empty", "prompt", ""),
        ("prompt-blank", "prompt", " \n\t"),
        ("prompt-too-long", "prompt", long_prompt),
        ("prompt-not-str", "prompt", 7),
    ]
    for field_name in ("model", "reasoning_effort"):
        rows += [
            (f"{field_name}-empty", field_name, ""),
            (f"{field_name}-too-long", field_name, "m" * 129),
            (f"{field_name}-whitespace", field_name, "grok 4"),
            (f"{field_name}-dash", field_name, "--always-approve"),
        ]
    rows += [
        ("seconds-bool", "max_turn_seconds", True),
        ("seconds-nan", "max_turn_seconds", math.nan),
        ("seconds-inf", "max_turn_seconds", math.inf),
        ("seconds-minus-inf", "max_turn_seconds", -math.inf),
        ("seconds-zero", "max_turn_seconds", 0),
        ("seconds-negative", "max_turn_seconds", -5),
        ("seconds-over-cap", "max_turn_seconds", grok_api.constants.NATIVE_TURN_MAX_SECONDS + 1),
        ("kinds-strings", "allowed_tool_kinds", frozenset({"edit"})),
        ("kinds-other-enum", "allowed_tool_kinds", frozenset({grok_api.NativeHarness.GROK})),
    ]
    return rows


def test_grok_turn_request_rejects_each_ec23_value(grok_api) -> None:
    # EC-23: ConfigurationError names the field; no host call is involved.
    for label, field_name, bad in turn_request_cases(grok_api):
        error = expect_rejected(grok_api, "GrokTurnRequest", field_name, lambda field_name=field_name, bad=bad: build_record(grok_api.GrokTurnRequest, {"prompt": "hello"}, {field_name: bad}))
        assert error is not None, label


def test_grok_turn_request_defaults_and_edges(grok_api) -> None:
    request = grok_api.GrokTurnRequest(prompt="hello")
    assert request.allowed_tool_kinds == frozenset() and request.model is None and request.reasoning_effort is None
    assert request.max_turn_seconds == grok_api.constants.NATIVE_TURN_DEFAULT_SECONDS == 1800.0
    edge = grok_api.GrokTurnRequest(prompt="p" * grok_api.constants.NATIVE_PROMPT_MAX_CHARS, model="m" * 128, max_turn_seconds=grok_api.constants.NATIVE_TURN_MAX_SECONDS)
    assert len(edge.prompt) == 200000


def oneshot_cases(grok_api: Any) -> list[tuple[str, str, Any]]:
    argv_cap = grok_api.constants.GROK_ARGV_PROMPT_MAX_CHARS
    return [
        ("prompt-empty", "prompt", ""),
        ("prompt-over-argv-cap", "prompt", "p" * (argv_cap + 1)),
        ("allow-empty-rule", "allow_rules", ("",)),
        ("allow-long-rule", "allow_rules", ("r" * 201,)),
        ("allow-control-char", "allow_rules", ("Read(*)\n--yolo",)),
        ("allow-dash", "allow_rules", ("--always-approve",)),
        ("deny-dash", "deny_rules", ("-x",)),
        ("deny-tab", "deny_rules", ("Bash(\trm)",)),
        ("max-turns-bool", "max_turns", True),
        ("max-turns-zero", "max_turns", 0),
        ("max-turns-over", "max_turns", 201),
        ("permission-string", "permission_mode", "acceptEdits"),
        ("model-dash", "model", "-m"),
        ("effort-space", "reasoning_effort", "very high"),
        ("seconds-nan", "max_turn_seconds", math.nan),
    ]


def test_grok_one_shot_request_rejects_each_ec33_value(grok_api) -> None:
    for label, field_name, bad in oneshot_cases(grok_api):
        error = expect_rejected(grok_api, "GrokOneShotRequest", field_name, lambda field_name=field_name, bad=bad: build_record(grok_api.GrokOneShotRequest, {"prompt": "hello"}, {field_name: bad}))
        assert error is not None, label


def test_grok_one_shot_request_caps_the_total_rule_count(grok_api) -> None:
    # EC-33: at most GROK_MAX_RULES rules in total, counting allow and deny together.
    limit = grok_api.constants.GROK_MAX_RULES
    at_limit = grok_api.GrokOneShotRequest(prompt="hello", allow_rules=tuple(f"Read(a{i})" for i in range(limit - 1)), deny_rules=("Bash(rm)",))
    assert len(at_limit.allow_rules) + len(at_limit.deny_rules) == 32
    with pytest.raises(grok_api.ConfigurationError) as caught:
        grok_api.GrokOneShotRequest(prompt="hello", allow_rules=tuple(f"Read(a{i})" for i in range(limit)), deny_rules=("Bash(rm)",))
    assert "GrokOneShotRequest." in str(caught.value)


def test_grok_one_shot_request_defaults_and_tuple_conversion(grok_api) -> None:
    request = grok_api.GrokOneShotRequest(prompt="hello", allow_rules=["Read(*)"])
    assert request.allow_rules == ("Read(*)",) and isinstance(request.allow_rules, tuple)
    assert request.deny_rules == () and request.max_turns is None
    assert request.permission_mode is grok_api.GrokPermissionMode.DEFAULT
    assert request.max_turn_seconds == 1800.0


def test_a_long_bad_value_is_never_quoted(grok_api) -> None:
    # §9.1: the message quotes a value only when it is at most 80 characters.
    with pytest.raises(grok_api.ConfigurationError) as caught:
        grok_api.GrokTurnRequest(prompt="hello", model=LONG_HIDDEN)
    assert LONG_HIDDEN not in str(caught.value)
    assert "GrokTurnRequest.model" in str(caught.value)


RECORD_NAMES = {
    "native_hosts": ("NativeTurnHandle", "NativeTokenUsage", "NativeApprovalDecision", "NativeTurnResult", "NativeInterruptResult", "NativeSteerResult", "NativeMessageUsage", "NativeSessionUsage"),
    "grok": (
        "GrokHostSettings", "GrokTurnRequest", "GrokOneShotRequest", "GrokOneShotResult", "GrokReadiness", "GrokModel", "GrokModelCatalog", "GrokSession",
        "GrokSessionPage", "GrokSessionSearch", "GrokPermissionOption", "GrokPermissionRequest", "GrokSessionUpdate", "GrokPromptResult",
    ),
    "process": ("CliInvocation", "CliOutcome", "ProcessStartOutcome"),
}


@pytest.mark.parametrize("module_name", sorted(RECORD_NAMES))
def test_every_record_is_a_frozen_slotted_dataclass(module_name: str) -> None:
    # §9.1 common rules / §12.4: @dataclass(frozen=True, slots=True) in the named module.
    module = records(module_name)
    for name in RECORD_NAMES[module_name]:
        record_type = getattr(module, name)
        assert dataclasses.is_dataclass(record_type), name
        assert record_type.__dataclass_params__.frozen, name
        assert "__slots__" in vars(record_type), name
        assert record_type.__module__ == module.__name__, f"{name} must be defined in {module.__name__}"


def test_a_built_record_cannot_be_changed(grok_api) -> None:
    request = grok_api.GrokTurnRequest(prompt="hello")
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.prompt = "changed"
