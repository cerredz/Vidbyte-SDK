"""FILE: tests/features/muse_host/test_muse_host_records.py

PURPOSE: The Muse records of spec §9.1 (`vidbyte.lib.dataclasses.muse`): MuseTurnRequest's EC-106 checks and MuseHostSettings' checks, each raising ConfigurationError that names `<Record>.<field>`; their defaults; the field sets of all fifteen records; frozen and slotted records; and no request or settings field that could carry an approve-everything value (INV-9, AC-19).
ROLE IN CODEBASE: Proves INV-5's record half and the Muse part of AC-19. Construction happens before any host exists, so these tests start no process.
ARCHITECTURE NOTE: Each rejection case changes one field of a valid base record, so the failure can only come from that field. The record module is imported through the muse_api fixture so a missing module fails at setup.
FUNCTION INVENTORY: workspace_value turns a named workspace form into a bad value or a valid folder; expect_rejected asserts the ConfigurationError names `<Record>.<field>`; the test_* functions are one rule each.
COMMON MODIFICATION PATTERNS: A new §9.1 field adds a FIELD_SETS entry and, when validated, a case in REQUEST_REJECTS or SETTINGS_REJECTS.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert exact message wording beyond `<Record>.<field>`; spec §9.1 fixes only that. 2. Do not use a distro name that exists on a developer machine; these records are never used to start a process here.
KNOWN EDGE CASES: MuseReasoningEffort is a closed enum, so its value string "high" is rejected (require_enum takes members only). Both wsl_distro and muse_command set is one rejection; spec §9.1 does not say which field it names, so the test accepts either.
RELATED DOCS: tests/features/muse_host/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.5 EC-106, §9.1
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/muse_host/test_muse_host_records.py
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import Any

import pytest

PROMPT = "List the top-level folders."
FIELD_SETS = {
    "MuseHostSettings": {"workspace", "wsl_distro", "muse_path", "muse_command", "control_timeout_seconds", "max_live_turns"},
    "MuseTurnRequest": {"prompt", "model", "reasoning_effort", "max_turn_seconds"},
    "MuseReadiness": {"version", "schema_version", "signed_in", "launcher", "wsl_distro"},
    "MuseModel": {"model_id", "display_name"},
    "MuseModelCatalog": {"provider_id", "profile_id", "source", "models"},
    "MuseSession": {"session_id", "workspace_root", "status", "active_turn_id", "model_id", "provider_id", "forked_from", "turn_count", "created_at", "updated_at"},
    "MuseSessionPage": {"sessions", "next_cursor"},
    "MuseViewEvent": {"kind", "event_json", "truncated"},
    "MusePage": {"session_id", "events", "next_cursor"},
    "MuseApprovalChoice": {"choice_id", "decision", "scope"},
    "MuseApprovalRequest": {"session_id", "approval_id", "requirement_approval_id", "requirement_source_index", "choices", "turn_id", "tool_name"},
    "MuseUserInputRequest": {"session_id", "turn_id", "user_input_id", "tool_name"},
    "MuseTurnCompleted": {"session_id", "turn_id", "terminal", "error_kind", "error_message", "error_retryable", "usage"},
    "MuseTurnAck": {"command_id", "turn_id", "status", "disposition"},
    "MuseItemCompleted": {"session_id", "item_id", "kind", "turn_id", "text", "truncated"},
}
APPROVE_EVERYTHING_WORDS = ("approv", "permission", "yolo", "allow", "bypass", "skip")


def expect_rejected(api: Any, record_name: str, field_names: tuple[str, ...], build: Any) -> None:
    with pytest.raises(api.ConfigurationError) as caught:
        build()
    message = str(caught.value)
    assert any(f"{record_name}.{name}" in message for name in field_names), f"message must name {record_name}.{'/'.join(field_names)}: {message!r}"


REQUEST_REJECTS = [
    pytest.param("prompt", "", id="prompt-empty"),
    pytest.param("prompt", "   \n", id="prompt-blank"),
    pytest.param("prompt", "p" * 200_001, id="prompt-too-long"),
    pytest.param("prompt", True, id="prompt-bool"),
    pytest.param("model", "", id="model-empty"),
    pytest.param("model", "m" * 129, id="model-too-long"),
    pytest.param("model", "muse large", id="model-whitespace"),
    pytest.param("model", 7, id="model-type"),
    pytest.param("reasoning_effort", "high", id="effort-value-string"),
    pytest.param("reasoning_effort", "maximum", id="effort-unknown"),
    pytest.param("max_turn_seconds", 0, id="ceiling-zero"),
    pytest.param("max_turn_seconds", -1.0, id="ceiling-negative"),
    pytest.param("max_turn_seconds", math.nan, id="ceiling-nan"),
    pytest.param("max_turn_seconds", math.inf, id="ceiling-inf"),
    pytest.param("max_turn_seconds", True, id="ceiling-bool"),
    pytest.param("max_turn_seconds", 14_400.5, id="ceiling-over-max"),
    pytest.param("max_turn_seconds", "60", id="ceiling-string"),
]


@pytest.mark.parametrize(("field_name", "value"), REQUEST_REJECTS)
def test_turn_request_rejects_each_bad_field_by_name(field_name: str, value: Any, muse_api) -> None:
    # EC-106: ConfigurationError naming MuseTurnRequest.<field>, raised while the record is constructed.
    fields = {"prompt": PROMPT, field_name: value}
    expect_rejected(muse_api, "MuseTurnRequest", (field_name,), lambda: muse_api.MuseTurnRequest(**fields))


def test_turn_request_defaults_and_accepted_limits(muse_api) -> None:
    # §9.1: model and effort default to None; the ceiling defaults to NATIVE_TURN_DEFAULT_SECONDS and accepts the maximum.
    request = muse_api.MuseTurnRequest(prompt=PROMPT)
    assert (request.model, request.reasoning_effort) == (None, None)
    assert request.max_turn_seconds == muse_api.constants.NATIVE_TURN_DEFAULT_SECONDS == 1800.0
    widest = muse_api.MuseTurnRequest(prompt="p" * 200_000, model="m" * 128, reasoning_effort=muse_api.MuseReasoningEffort.ULTRA, max_turn_seconds=14_400.0)
    assert widest.reasoning_effort is muse_api.MuseReasoningEffort.ULTRA


WORKSPACE_FORMS = ("relative", "missing", "file", "str")
SETTINGS_REJECTS = [
    pytest.param({"workspace": "relative"}, ("workspace",), id="workspace-relative"),
    pytest.param({"workspace": "missing"}, ("workspace",), id="workspace-missing"),
    pytest.param({"workspace": "file"}, ("workspace",), id="workspace-file"),
    pytest.param({"workspace": "str"}, ("workspace",), id="workspace-str"),
    pytest.param({"wsl_distro": "Muse Ubuntu"}, ("wsl_distro",), id="distro-space"),
    pytest.param({"wsl_distro": ""}, ("wsl_distro",), id="distro-empty"),
    pytest.param({"wsl_distro": "d" * 65}, ("wsl_distro",), id="distro-too-long"),
    pytest.param({"wsl_distro": "a/b"}, ("wsl_distro",), id="distro-slash"),
    pytest.param({"muse_path": "usr/local/bin/muse"}, ("muse_path",), id="path-relative"),
    pytest.param({"muse_path": "/usr/local/bin/mu\x00se"}, ("muse_path",), id="path-nul"),
    pytest.param({"muse_path": "/usr/local/bin/muse\nserve"}, ("muse_path",), id="path-newline"),
    pytest.param({"muse_path": "/" + "p" * 4096}, ("muse_path",), id="path-too-long"),
    pytest.param({"muse_command": ()}, ("muse_command",), id="command-empty"),
    pytest.param({"muse_command": ("",)}, ("muse_command",), id="command-blank-item"),
    pytest.param({"muse_command": ["muse"]}, ("muse_command",), id="command-list"),
    pytest.param({"wsl_distro": "VidbyteFakeDistro", "muse_command": ("muse",)}, ("wsl_distro", "muse_command"), id="both-launchers"),
    pytest.param({"control_timeout_seconds": 0}, ("control_timeout_seconds",), id="timeout-zero"),
    pytest.param({"control_timeout_seconds": 600.5}, ("control_timeout_seconds",), id="timeout-over-max"),
    pytest.param({"control_timeout_seconds": True}, ("control_timeout_seconds",), id="timeout-bool"),
    pytest.param({"control_timeout_seconds": math.nan}, ("control_timeout_seconds",), id="timeout-nan"),
    pytest.param({"max_live_turns": 0}, ("max_live_turns",), id="turns-zero"),
    pytest.param({"max_live_turns": 17}, ("max_live_turns",), id="turns-over-limit"),
    pytest.param({"max_live_turns": True}, ("max_live_turns",), id="turns-bool"),
    pytest.param({"max_live_turns": 2.0}, ("max_live_turns",), id="turns-float"),
]


def workspace_value(form: Any, tmp_path: Path) -> Any:
    # Turns a workspace form name into a bad value; any other value is a valid directory.
    if form not in WORKSPACE_FORMS:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace
    a_file = tmp_path / "a-file.txt"
    a_file.write_text("x", encoding="utf-8")
    return {"relative": Path("relative-folder"), "missing": tmp_path / "missing", "file": a_file, "str": str(tmp_path)}[form]


@pytest.mark.parametrize(("overrides", "field_names"), SETTINGS_REJECTS)
def test_host_settings_reject_each_bad_field_by_name(overrides: dict[str, Any], field_names: tuple[str, ...], muse_api, tmp_path: Path) -> None:
    # §9.1 MuseHostSettings: every check raises ConfigurationError naming MuseHostSettings.<field>.
    fields = {**overrides, "workspace": workspace_value(overrides.get("workspace"), tmp_path)}
    expect_rejected(muse_api, "MuseHostSettings", field_names, lambda: muse_api.MuseHostSettings(**fields))


def test_host_settings_defaults(muse_api, tmp_path: Path) -> None:
    # §9.1 / §9.3: muse_path defaults to MUSE_DEFAULT_PATH; timeouts and turn cap default as for Grok.
    settings = muse_api.MuseHostSettings(workspace=tmp_path)
    assert settings.muse_path == muse_api.constants.MUSE_DEFAULT_PATH == "/usr/local/bin/muse"
    assert settings.wsl_distro is None and settings.muse_command is None
    assert settings.control_timeout_seconds == muse_api.constants.NATIVE_CONTROL_TIMEOUT_SECONDS == 30.0
    assert settings.max_live_turns == muse_api.constants.NATIVE_MAX_LIVE_TURNS_DEFAULT == 4
    widest = muse_api.MuseHostSettings(workspace=tmp_path, wsl_distro="d" * 64, control_timeout_seconds=600.0, max_live_turns=16)
    assert widest.wsl_distro == "d" * 64


@pytest.mark.parametrize("record_name", sorted(FIELD_SETS))
def test_each_muse_record_is_a_frozen_slotted_dataclass_with_the_listed_fields(record_name: str, muse_api) -> None:
    # §9.1: fifteen records, each @dataclass(frozen=True, slots=True) with exactly the listed fields.
    record_type = getattr(muse_api.records, record_name)
    assert dataclasses.is_dataclass(record_type)
    assert {item.name for item in dataclasses.fields(record_type)} == FIELD_SETS[record_name]
    assert record_type.__dataclass_params__.frozen is True
    assert "__slots__" in vars(record_type), f"{record_name} must use slots=True"


def test_records_are_immutable(muse_api, tmp_path: Path) -> None:
    # §9.1: a validated record cannot later be changed into an invalid one.
    request = muse_api.MuseTurnRequest(prompt=PROMPT)
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.prompt = ""
    settings = muse_api.MuseHostSettings(workspace=tmp_path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.muse_path = "/tmp/other"


def test_no_request_or_settings_field_can_carry_an_approve_everything_value(muse_api) -> None:
    # INV-9 / AC-19: no Muse request or settings field names an approval, permission or bypass setting.
    for record_name in ("MuseTurnRequest", "MuseHostSettings"):
        names = {item.name for item in dataclasses.fields(getattr(muse_api.records, record_name))}
        flagged = [name for name in names if any(word in name.lower() for word in APPROVE_EVERYTHING_WORDS)]
        assert flagged == [], f"{record_name} exposes {flagged}"


def test_muse_enums_are_the_closed_msp_sets(muse_api) -> None:
    # §9.1: MuseReasoningEffort mirrors MSP ReasoningEffort and MuseViewDirection mirrors ViewPageDirection.
    efforts = {member.name: member.value for member in muse_api.MuseReasoningEffort}
    assert efforts == {"NONE": "none", "MINIMAL": "minimal", "LOW": "low", "MEDIUM": "medium", "HIGH": "high", "XHIGH": "xhigh", "ULTRA": "ultra"}
    directions = {member.name: member.value for member in muse_api.MuseViewDirection}
    assert directions == {"FORWARD": "forward", "BACKWARD": "backward"}
    assert issubclass(muse_api.MuseReasoningEffort, str)
