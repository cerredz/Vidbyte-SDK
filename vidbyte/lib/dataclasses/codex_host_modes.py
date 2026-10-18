"""FILE: vidbyte/lib/dataclasses/codex_host_modes.py

PURPOSE: Defines the two validated collaboration-mode records of CodexHost: CodexCollaborationMode, the plan or default mode a caller sends with a turn or a settings update, which builds itself from one of Codex's presets and refuses a model or effort that conflicts with its owner's, and CodexCollaborationModePreset, one preset as collaborationMode/list reports it.
ROLE IN CODEBASE: A leaf of the CodexHost data layer. vidbyte/lib/dataclasses/codex_host.py imports CodexCollaborationMode for CodexSpawnRequest.collaboration_mode, codex_host_features.py imports it for CodexThreadSettingsUpdate, and CodexFeatureResponseTranslator under vidbyte/harnesses/native/codex/ builds the presets.
ARCHITECTURE NOTE: The module imports only lib constants, enums, errors, the shared validators and CodexTurnSettings, so codex_host can import it without a cycle (first-class D-5). Both records are frozen with slots and check themselves in __post_init__ through RecordFieldValidator, naming the field as "collaboration_mode <field>". A preset keeps reasoning_effort as open text, because Codex owns that set and may list an effort newer than CodexReasoningEffort.
COMMON MODIFICATION PATTERNS: A new mode field adds its check to CodexCollaborationMode.__post_init__ and its wire key in CodexParamsTranslator.turn_start and CodexFeatureParamsTranslator.thread_settings. A new owner of a mode calls reject_conflict with its own name, model and effort.
KNOWN EDGE CASES: CodexCollaborationModeKind.NONE stands only for Codex's null in a preset, so a mode built with it is refused. from_preset takes the preset's model only when the turn names none, and the preset's effort only when the turn sets none and the effort is a CodexReasoningEffort value, so its result never conflicts with that turn (first-class INV-16, EC-12, EC-13). reject_conflict treats an empty model and PROVIDER_DEFAULT as unset, so a value set in one place only never conflicts.
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.5 and 9.1, INV-14, INV-16, D-5); vidbyte/lib/dataclasses/validation.py
TESTS: tests/features/codex_host/test_codex_host_feature_records.py
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_MODE_CONFLICT_MESSAGE,
    CODEX_HOST_MODE_KIND_MESSAGE,
)
from vidbyte.lib.dataclasses.codex import CodexTurnSettings
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.codex import CodexCollaborationModeKind, CodexReasoningEffort
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class CodexCollaborationMode:
    """A Codex collaboration mode sent with a turn or a settings update: plan or default, with an optional model and effort.

    An empty ``model`` means the turn's model, or else the thread's, and
    ``PROVIDER_DEFAULT`` means the mode's own effort. Codex lets the
    collaboration mode take precedence over the turn's model and effort,
    so a model or effort set both here and on the owner must agree.
    """

    mode: CodexCollaborationModeKind
    model: str = ""
    reasoning_effort: CodexReasoningEffort = CodexReasoningEffort.PROVIDER_DEFAULT

    def __post_init__(self) -> None:
        # @intent a-sent-mode-is-plan-or-default
        # NONE stands only for Codex's null in a listed preset, so a
        # caller can never send it (first-class AC-6).
        RecordFieldValidator.require_enum(self.mode, CodexCollaborationModeKind, "collaboration_mode mode")
        if self.mode is CodexCollaborationModeKind.NONE:
            raise ConfigurationError(CODEX_HOST_MODE_KIND_MESSAGE, details={"field": "collaboration_mode mode"})
        RecordFieldValidator.require_text(self.model, "collaboration_mode model", allow_blank=True, one_line=True)
        RecordFieldValidator.require_enum(self.reasoning_effort, CodexReasoningEffort, "collaboration_mode reasoning_effort")

    @classmethod
    def from_preset(cls, preset: CodexCollaborationModePreset, turn: CodexTurnSettings) -> CodexCollaborationMode:
        # @intent a-preset-mode-never-conflicts-with-its-turn
        # The turn's own model and effort win, so the mode takes the
        # preset's only where the turn sets none; an effort the enum
        # does not know falls back to the provider default (first-class
        # INV-16, EC-12).
        model = "" if turn.model else preset.model
        efforts = {member.value: member for member in CodexReasoningEffort}
        unset = CodexReasoningEffort.PROVIDER_DEFAULT
        effort = unset if turn.effort is not unset else efforts.get(preset.reasoning_effort, unset)
        return cls(mode=preset.mode, model=model, reasoning_effort=effort)

    def reject_conflict(self, owner: str, model: str, effort: CodexReasoningEffort) -> None:
        # @intent a-mode-and-its-owner-agree-on-model-and-effort
        # A model or effort set in both places must be equal, because
        # Codex would silently apply the mode's (first-class INV-14).
        field_name = f"{owner} collaboration_mode"
        if self.model and model and self.model != model:
            raise ConfigurationError(CODEX_HOST_MODE_CONFLICT_MESSAGE.format(owner=owner, name="model"), details={"field": field_name})
        unset = CodexReasoningEffort.PROVIDER_DEFAULT
        if self.reasoning_effort is not unset and effort is not unset and self.reasoning_effort is not effort:
            raise ConfigurationError(CODEX_HOST_MODE_CONFLICT_MESSAGE.format(owner=owner, name="reasoning_effort"), details={"field": field_name})


@dataclass(frozen=True, slots=True)
class CodexCollaborationModePreset:
    """One collaboration mode preset as Codex lists it: its name, its mode (NONE for Codex's null), model and effort."""

    name: str
    mode: CodexCollaborationModeKind
    model: str = ""
    reasoning_effort: str = ""

    def __post_init__(self) -> None:
        # The effort stays open text, because Codex owns the set and
        # may list an effort newer than CodexReasoningEffort.
        RecordFieldValidator.require_text(self.name, "collaboration_mode name", one_line=True)
        RecordFieldValidator.require_enum(self.mode, CodexCollaborationModeKind, "collaboration_mode mode")
        RecordFieldValidator.require_text(self.model, "collaboration_mode model", allow_blank=True, one_line=True)
        RecordFieldValidator.require_text(self.reasoning_effort, "collaboration_mode reasoning_effort", allow_blank=True, one_line=True)


__all__ = ["CodexCollaborationMode", "CodexCollaborationModePreset"]
