"""FILE: vidbyte/agents/codex/fallback.py

PURPOSE: Walks a Vidbyte model fallback chain across Codex turn boundaries.
ROLE IN CODEBASE: agent.py asks this whether to try another model after a failed turn.
    AgentFallback owns the switch policy; this module supplies the Codex primary and
    the per-attempt turn override, and adds no second copy of that policy.
ARCHITECTURE NOTE: AgentFallback.is_model_error/advance take no runner and no provider
    client, so they are reused unchanged. Only AgentFallback.from_spec is coupled to the
    direct runtime's AgentRunnerConfig, which a Codex agent does not have.
FUNCTION INVENTORY: build(settings) resolves the chain; next_index(decision) asks whether
    to advance; settings_for(codex, index) overrides only the turn model; attempt() records
    one credential-free try; model_name(index) names the answering model, empty without a
    chain; primary_model(codex) derives chain index 0.
COMMON MODIFICATION PATTERNS: Add a gate to build(); leave the advance decision to
    AgentFallback so the two callers of that policy cannot drift apart.
WHAT NOT TO DO IN THIS FILE: Do not reimplement is_model_error/advance, do not copy a
    FallbackModel.api_key into an override or an attempt record, and do not switch models
    mid-turn: a running native turn may already have edited files.
KNOWN EDGE CASES: A chain entry naming another provider is rejected at build, because a
    Codex thread cannot resume on a provider that has never seen it. FallbackModel
    temperature has no Codex counterpart and is ignored.
RELATED DOCS: docs/design/codex-failure-recovery.md
TESTS: tests/test_codex_failure_recovery.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.agents.fallback import AgentFallback
from vidbyte.lib.constants.codex import CODEX_USAGE_PROVIDER
from vidbyte.lib.dataclasses.agents import FallbackModel
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexFallbackAttempt,
    CodexFallbackDecision,
    CodexHarnessAgentSettings,
)
from vidbyte.lib.enums.codex import CodexFailureClass
from vidbyte.lib.errors import ConfigurationError


class CodexFallbackCoordinator:
    """Walks a Vidbyte fallback chain across Codex turn boundaries."""

    def __init__(self, chain: AgentFallback | None) -> None:
        # A None chain is the ordinary case; it makes every accessor a cheap no-op.
        self._chain = chain

    @classmethod
    def build(cls, settings: CodexHarnessAgentSettings) -> CodexFallbackCoordinator:
        # @intent reject-an-unreachable-chain-at-construction
        # A chain naming another provider, or naming no primary to fall back from,
        # must fail when declared rather than at the first failure it cannot handle.
        if settings.fallback is None:
            return cls(None)
        primary = cls.primary_model(settings.codex)
        chain = settings.fallback.to_fallback(primary=primary)
        if chain is None:
            return cls(None)
        cls._require_reachable_providers(chain, primary)
        return cls(chain)

    @property
    def enabled(self) -> bool:
        """Return whether this agent has a resolved fallback chain."""
        return self._chain is not None

    def next_index(self, decision: CodexFallbackDecision) -> int | None:
        """Return the next chain index to try, or None when this failure ends the turn."""
        # @intent require-both-judgments-to-agree
        # A fallback attempt costs a whole extra native turn, so the Codex code
        # classification and the caller's own exception filter must both accept it.
        if self._chain is None:
            return None
        if decision.record.failure_class is not CodexFailureClass.MODEL_RETRYABLE:
            return None
        return self._chain.advance(decision.error, decision.index)

    def settings_for(self, codex: CodexAgentSettings, index: int) -> CodexAgentSettings:
        """Return the provider settings for one attempt, overriding only the turn model."""
        # Sandbox, approval mode, and every thread setting stay exactly as configured;
        # a fallback that widened the sandbox would be a silent security regression.
        if self._chain is None or index == 0:
            return codex
        return replace(
            codex, turn=replace(codex.turn, model=self._chain.models[index].model)
        )

    def attempt(self, index: int, failure_code: str = "") -> CodexFallbackAttempt:
        """Record one credential-free attempt: which model ran and how it ended."""
        # @intent attempt-records-never-carry-credentials
        # FallbackModel may hold an api_key; an attempt record names only the
        # provider and model, because these records reach metadata and logs.
        model = self._model_at(index)
        return CodexFallbackAttempt(
            index=index,
            provider=model.provider,
            model=model.model,
            failure_code=failure_code,
        )

    def model_name(self, index: int) -> str:
        """Return the model that answered at one chain index, or empty without a chain."""
        # @intent absent-means-no-chain-not-first-entry
        # Empty rather than the configured model, so a caller can tell "no fallback
        # chain" from "the chain answered on its first entry".
        return self._model_at(index).model if self._chain is not None else ""

    @staticmethod
    def primary_model(codex: CodexAgentSettings) -> FallbackModel:
        """Derive chain index 0 from Codex settings: the model a chain falls back from."""
        # @intent one-provider-answer-across-surfaces
        # Provider resolution matches the merged usage record's, so the two surfaces
        # cannot disagree about which provider a Codex turn actually ran against.
        model = codex.turn.model or codex.thread.model
        if not model:
            raise ConfigurationError(
                "Codex harness agent declares a fallback chain but names no model at "
                "turn.model or thread.model to fall back from."
            )
        return FallbackModel(
            provider=codex.thread.model_provider or CODEX_USAGE_PROVIDER, model=model
        )

    @staticmethod
    def _require_reachable_providers(
        chain: AgentFallback, primary: FallbackModel
    ) -> None:
        # @intent reject-a-provider-the-thread-cannot-resume-on
        # A Codex thread cannot move to another provider: the conversation, the cached
        # prefixes, and the thread id all belong to the one that created it.
        for index, entry in enumerate(chain.models):
            if entry.provider == primary.provider:
                continue
            raise ConfigurationError(
                f"Codex cannot reach fallback chain entry {index} provider "
                f"{entry.provider!r}; a Codex thread resumes only on "
                f"{primary.provider!r}. Remove the entry or run it as a separate agent."
            )

    def _model_at(self, index: int) -> FallbackModel:
        # Guards a report against an index the chain never produced.
        if self._chain is None or index >= len(self._chain.models):
            raise ConfigurationError(
                f"Codex fallback chain has no entry at index {index}."
            )
        return self._chain.models[index]


__all__ = ["CodexFallbackCoordinator"]
