"""Context Protocol Header

FILE:
    vidbyte/tools/builtins/adversarial.py declares pending adversarial launch tools.
PURPOSE:
    Reserves stable model-facing names and review-subject schemas for sixteen
    adversarial topologies while the topology-aware AdversarialAgent API is unfinished.
    This file must fail closed; it does not own agent construction or orchestration.
ROLE IN CODEBASE:
    Re-exported by vidbyte.tools.builtins and consumed by agent-local Tools catalogs,
    ToolExecutor, and provider schema formatters. It calls only BaseTool and shared
    tool dataclasses; it never imports vidbyte.agents or adversarial settings.
ARCHITECTURE NOTE:
    Public classes are distinct topology entry points. _AdversarialLaunchTool is
    private implementation reuse, not a public strategy abstraction. Model arguments
    carry review subjects only; developers retain control of topology policy.
PUBLIC CONTRACT INVENTORY (reviewed 2026-07-16):
    Sixteen zero-argument BaseTool subclasses expose fixed names, schemas, EXECUTE
    permission, TODO metadata, and deterministic adversarial_agent_unavailable errors.
COMMON MODIFICATION PATTERNS:
    Add or rename a scaffold only with the approved design, both __all__ lists, and
    vidbyte/tools/README.md. Implement execution only after a topology-aware agent
    contract defines isolation, recursion, permissions, and nested usage budgets.
WHAT NOT TO DO IN THIS FILE:
    1. Do not import or construct AdversarialAgent; vidbyte/agents owns agents.
    2. Do not accept model-controlled providers, counts, specialties, or permissions.
    3. Do not echo candidate, evidence, or mutation bodies in errors or metadata.
    4. Do not add runtime placement policies such as live, periodic, terminal, or shadow gates.
KNOWN EDGE CASES:
    ToolExecutor validates required fields from ToolParameter before execute(). Array
    cardinality is declared in input_schema for providers; executable validation is
    deferred because every scaffold currently returns the same unavailable error.
COMMON ERRORS RETURNED BY THIS FILE:
    adversarial_agent_unavailable is returned as ToolResult.error for every valid call.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/feat/adversarial-review-tools/docs/design/adversarial-review-tools.md
    https://github.com/cerredz/Vidbyte-SDK/pull/275
    https://github.com/cerredz/Vidbyte-SDK/pull/277
TESTS:
    No feature tests by approved no-tests design; use compile, import, schema,
    ToolExecutor, provider-format, and wheel-content smoke commands from the design.
CONCURRENCY:
    Scaffolds hold no mutable state and launch no tasks, models, or child agents.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, ClassVar

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

_CATEGORY = "adversarial_review"
_IMPLEMENTATION_STATUS = "todo"
_REQUIRES = "AdversarialAgent"
_UNAVAILABLE_ERROR = "adversarial_agent_unavailable"

_CANDIDATE_REVIEW_PARAMETERS = (
    ToolParameter(
        name="original_request",
        type="string",
        description="The original task, question, or requirements the candidate attempted to satisfy.",
        required=True,
    ),
    ToolParameter(
        name="candidate",
        type="string",
        description="The proposed answer, implementation, plan, or artifact to review adversarially.",
        required=True,
    ),
    ToolParameter(
        name="focus",
        type="string",
        description="Optional review emphasis that does not alter developer-owned review policy.",
        required=False,
        default=None,
    ),
)

_CANDIDATE_SET_PARAMETERS = (
    ToolParameter(
        name="original_request",
        type="string",
        description="The original task, question, or requirements the candidates attempted to satisfy.",
        required=True,
    ),
    ToolParameter(
        name="candidates",
        type="array",
        description="At least two proposed answers or artifacts to compare in the tournament.",
        required=True,
    ),
    ToolParameter(
        name="focus",
        type="string",
        description="Optional comparison emphasis that does not alter developer-owned review policy.",
        required=False,
        default=None,
    ),
)

_REQUEST_PARAMETERS = (
    ToolParameter(
        name="original_request",
        type="string",
        description="The task or question for which diverse candidates should be generated and selected.",
        required=True,
    ),
    ToolParameter(
        name="focus",
        type="string",
        description="Optional selection emphasis that does not alter developer-owned sampling policy.",
        required=False,
        default=None,
    ),
)

_MUTATION_PARAMETERS = (
    ToolParameter(
        name="original_request",
        type="string",
        description="The original task, question, or requirements the candidate attempted to satisfy.",
        required=True,
    ),
    ToolParameter(
        name="candidate",
        type="string",
        description="The proposed answer or artifact to challenge with mutation and fuzz review.",
        required=True,
    ),
    ToolParameter(
        name="mutation_inputs",
        type="array",
        description="Optional inputs, contexts, tool results, or artifact descriptions to mutate.",
        required=False,
        default=None,
    ),
    ToolParameter(
        name="focus",
        type="string",
        description="Optional mutation emphasis that does not alter developer-owned review policy.",
        required=False,
        default=None,
    ),
)

_TOOL_VERIFICATION_PARAMETERS = (
    ToolParameter(
        name="original_request",
        type="string",
        description="The original task, question, or requirements the candidate attempted to satisfy.",
        required=True,
    ),
    ToolParameter(
        name="candidate",
        type="string",
        description="The proposed answer or artifact to verify with developer-configured tools.",
        required=True,
    ),
    ToolParameter(
        name="verification_requirements",
        type="string",
        description="Optional verification goals; available tools and permissions remain developer controlled.",
        required=False,
        default=None,
    ),
    ToolParameter(
        name="focus",
        type="string",
        description="Optional verification emphasis that does not alter developer-owned review policy.",
        required=False,
        default=None,
    ),
)

_EVIDENCE_PARAMETERS = (
    ToolParameter(
        name="original_request",
        type="string",
        description="The original task, question, or requirements the candidate attempted to satisfy.",
        required=True,
    ),
    ToolParameter(
        name="candidate",
        type="string",
        description="The proposed answer whose material claims must be checked against evidence.",
        required=True,
    ),
    ToolParameter(
        name="evidence",
        type="array",
        description="One or more supplied evidence items that may support material claims.",
        required=True,
    ),
    ToolParameter(
        name="focus",
        type="string",
        description="Optional evidence-review emphasis that does not alter developer-owned policy.",
        required=False,
        default=None,
    ),
)

_CANDIDATE_REVIEW_SCHEMA = {
    "type": "object",
    "required": ["original_request", "candidate"],
    "additionalProperties": False,
    "properties": {
        "original_request": {"type": "string", "description": _CANDIDATE_REVIEW_PARAMETERS[0].description},
        "candidate": {"type": "string", "description": _CANDIDATE_REVIEW_PARAMETERS[1].description},
        "focus": {"type": "string", "description": _CANDIDATE_REVIEW_PARAMETERS[2].description},
    },
}

_CANDIDATE_SET_SCHEMA = {
    "type": "object",
    "required": ["original_request", "candidates"],
    "additionalProperties": False,
    "properties": {
        "original_request": {"type": "string", "description": _CANDIDATE_SET_PARAMETERS[0].description},
        "candidates": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "description": _CANDIDATE_SET_PARAMETERS[1].description,
        },
        "focus": {"type": "string", "description": _CANDIDATE_SET_PARAMETERS[2].description},
    },
}

_REQUEST_SCHEMA = {
    "type": "object",
    "required": ["original_request"],
    "additionalProperties": False,
    "properties": {
        "original_request": {"type": "string", "description": _REQUEST_PARAMETERS[0].description},
        "focus": {"type": "string", "description": _REQUEST_PARAMETERS[1].description},
    },
}

_MUTATION_SCHEMA = {
    "type": "object",
    "required": ["original_request", "candidate"],
    "additionalProperties": False,
    "properties": {
        "original_request": {"type": "string", "description": _MUTATION_PARAMETERS[0].description},
        "candidate": {"type": "string", "description": _MUTATION_PARAMETERS[1].description},
        "mutation_inputs": {
            "type": "array",
            "items": {"type": "string"},
            "description": _MUTATION_PARAMETERS[2].description,
        },
        "focus": {"type": "string", "description": _MUTATION_PARAMETERS[3].description},
    },
}

_TOOL_VERIFICATION_SCHEMA = {
    "type": "object",
    "required": ["original_request", "candidate"],
    "additionalProperties": False,
    "properties": {
        "original_request": {"type": "string", "description": _TOOL_VERIFICATION_PARAMETERS[0].description},
        "candidate": {"type": "string", "description": _TOOL_VERIFICATION_PARAMETERS[1].description},
        "verification_requirements": {"type": "string", "description": _TOOL_VERIFICATION_PARAMETERS[2].description},
        "focus": {"type": "string", "description": _TOOL_VERIFICATION_PARAMETERS[3].description},
    },
}

_EVIDENCE_SCHEMA = {
    "type": "object",
    "required": ["original_request", "candidate", "evidence"],
    "additionalProperties": False,
    "properties": {
        "original_request": {"type": "string", "description": _EVIDENCE_PARAMETERS[0].description},
        "candidate": {"type": "string", "description": _EVIDENCE_PARAMETERS[1].description},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": _EVIDENCE_PARAMETERS[2].description,
        },
        "focus": {"type": "string", "description": _EVIDENCE_PARAMETERS[3].description},
    },
}


class _AdversarialLaunchTool(BaseTool):
    """Private shared scaffold behavior for fixed adversarial review topologies."""

    tool_name: ClassVar[str]
    topology: ClassVar[str]
    summary: ClassVar[str]
    parameters: ClassVar[tuple[ToolParameter, ...]]
    input_schema: ClassVar[Mapping[str, Any]]

    def spec(self) -> ToolSpec:
        # Builds the fixed model-facing scaffold declaration for this topology.
        return ToolSpec(
            name=self.tool_name,
            description=(
                f"Scaffold only: {self.summary} "
                "This tool does not launch an agent yet; execution is reserved for "
                "the pending AdversarialAgent integration."
            ),
            parameters=self.parameters,
            permission=ToolPermission.EXECUTE,
            metadata={
                "category": _CATEGORY,
                "topology": self.topology,
                "implementation_status": _IMPLEMENTATION_STATUS,
                "requires": _REQUIRES,
            },
            input_schema=deepcopy(self.input_schema),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Returns a stable unavailable result until AdversarialAgent can launch this topology.
        del call
        return ToolResult.error(
            self.name,
            (
                f"{self.name} is an adversarial review scaffold and cannot launch "
                "review agents until the AdversarialAgent review/topology API is available."
            ),
            metadata={
                "error": _UNAVAILABLE_ERROR,
                "category": _CATEGORY,
                "topology": self.topology,
                "implementation_status": _IMPLEMENTATION_STATUS,
            },
        )


class LaunchSelfReflectionAgentTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for isolated self-reflection."""

    # TODO(adversarial-agent): Launch an isolated producer fork with recursion guards and return bounded self-critique once the topology-aware review API exists.
    tool_name = "launch_self_reflection_agent"
    topology = "self_reflection"
    summary = "Review one candidate through an isolated self-reflection agent."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchIndependentCriticAgentTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for one independent critic."""

    # TODO(adversarial-agent): Launch one critic without producer scratch history and return bounded findings once the topology-aware review API exists.
    tool_name = "launch_independent_critic_agent"
    topology = "independent_critic"
    summary = "Review one candidate with an independent critic isolated from producer scratch history."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchParallelPanelTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for a parallel review panel."""

    # TODO(adversarial-agent): Launch independent reviewers against one immutable snapshot and aggregate bounded findings once the topology-aware review API exists.
    tool_name = "launch_parallel_panel"
    topology = "parallel_panel"
    summary = "Review one immutable candidate snapshot with multiple independent reviewers."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchSpecialistPanelTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for a specialist adversarial panel."""

    # TODO(adversarial-agent): Launch isolated developer-configured specialists and synthesize bounded findings once the topology-aware review API exists.
    tool_name = "launch_specialist_panel"
    topology = "specialist_panel"
    summary = "Review one candidate with a developer-configured panel of independent specialists."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchCrossProviderPanelTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for a cross-provider review panel."""

    # TODO(adversarial-agent): Launch developer-configured provider and model families against one snapshot once the topology-aware review API exists.
    tool_name = "launch_cross_provider_panel"
    topology = "cross_provider_panel"
    summary = "Review one candidate across developer-configured provider and model families."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchCritiqueReviseAgentTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for critique followed by revision."""

    # TODO(adversarial-agent): Launch a critic and send verified findings to an authoritative producer revision once the topology-aware review API exists.
    tool_name = "launch_critique_revise_agent"
    topology = "critique_and_revise"
    summary = "Review one candidate and route findings to an authoritative producer revision."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchCritiqueAdjudicateReviseAgentTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for adjudicated critique and revision."""

    # TODO(adversarial-agent): Filter invalid or duplicate critiques through an adjudicator before authoritative revision once the topology-aware review API exists.
    tool_name = "launch_critique_adjudicate_revise_agent"
    topology = "critique_adjudicate_and_revise"
    summary = "Review one candidate, adjudicate findings, and route valid findings to revision."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchProsecutorDefenderJudgeTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for prosecutor, defender, and judge roles."""

    # TODO(adversarial-agent): Launch attack, defense, and judgment roles with bounded role visibility once the topology-aware review API exists.
    tool_name = "launch_prosecutor_defender_judge"
    topology = "prosecutor_defender_judge"
    summary = "Review one candidate through prosecutor, defender, and judge roles."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchAdversarialDebateTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for bounded adversarial debate."""

    # TODO(adversarial-agent): Launch bounded reviewer cross-examination and return an adjudicated verdict once the topology-aware review API exists.
    tool_name = "launch_adversarial_debate"
    topology = "adversarial_debate"
    summary = "Review one candidate through bounded reviewer debate and cross-examination."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchDelphiReviewTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for Delphi review."""

    # TODO(adversarial-agent): Launch blind reviews, anonymized synthesis, and a second independent round once the topology-aware review API exists.
    tool_name = "launch_delphi_review"
    topology = "delphi_review"
    summary = "Review one candidate through blind reviews, anonymized synthesis, and reconsideration."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchCandidateTournamentTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for a pairwise candidate tournament."""

    # TODO(adversarial-agent): Compare at least two candidates pairwise until one survives once the topology-aware review API exists.
    tool_name = "launch_candidate_tournament"
    topology = "candidate_tournament"
    summary = "Compare at least two supplied candidates in a pairwise adversarial tournament."
    parameters = _CANDIDATE_SET_PARAMETERS
    input_schema = _CANDIDATE_SET_SCHEMA


class LaunchAdversarialSelectorTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for N-sample adversarial selection."""

    # TODO(adversarial-agent): Generate developer-configured diverse samples and select by counterexample resistance once the topology-aware review API exists.
    tool_name = "launch_adversarial_selector"
    topology = "n_sample_adversarial_selector"
    summary = "Generate diverse candidates and select the one most resistant to counterexamples."
    parameters = _REQUEST_PARAMETERS
    input_schema = _REQUEST_SCHEMA


class LaunchCounterexampleSearchTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for counterexample search."""

    # TODO(adversarial-agent): Search for concrete inputs or situations that break the candidate once the topology-aware review API exists.
    tool_name = "launch_counterexample_search"
    topology = "counterexample_search"
    summary = "Search for concrete inputs or situations that break one candidate."
    parameters = _CANDIDATE_REVIEW_PARAMETERS
    input_schema = _CANDIDATE_REVIEW_SCHEMA


class LaunchMutationReviewTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for mutation and fuzz review."""

    # TODO(adversarial-agent): Mutate configured inputs, contexts, tool results, or artifacts and report retest outcomes once the topology-aware review API exists.
    tool_name = "launch_mutation_review"
    topology = "mutation_fuzz_review"
    summary = "Challenge one candidate by mutating inputs, context, tool results, or artifacts."
    parameters = _MUTATION_PARAMETERS
    input_schema = _MUTATION_SCHEMA


class LaunchToolBackedVerifierTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for tool-backed verification."""

    # TODO(adversarial-agent): Require configured verification tools, strip launch tools from children, and return evidence once the topology-aware review API exists.
    tool_name = "launch_tool_backed_verifier"
    topology = "tool_backed_verifier"
    summary = "Verify one candidate with developer-configured tests, schemas, lookup, or analysis tools."
    parameters = _TOOL_VERIFICATION_PARAMETERS
    input_schema = _TOOL_VERIFICATION_SCHEMA


class LaunchEvidenceVerifierTool(_AdversarialLaunchTool):
    """Declares the model-facing launcher for evidence verification."""

    # TODO(adversarial-agent): Map every material claim to bounded supplied evidence or reject it once the topology-aware review API exists.
    tool_name = "launch_evidence_verifier"
    topology = "evidence_verifier"
    summary = "Verify every material candidate claim against one or more supplied evidence items."
    parameters = _EVIDENCE_PARAMETERS
    input_schema = _EVIDENCE_SCHEMA


__all__ = [
    "LaunchAdversarialDebateTool",
    "LaunchAdversarialSelectorTool",
    "LaunchCandidateTournamentTool",
    "LaunchCounterexampleSearchTool",
    "LaunchCritiqueAdjudicateReviseAgentTool",
    "LaunchCritiqueReviseAgentTool",
    "LaunchCrossProviderPanelTool",
    "LaunchDelphiReviewTool",
    "LaunchEvidenceVerifierTool",
    "LaunchIndependentCriticAgentTool",
    "LaunchMutationReviewTool",
    "LaunchParallelPanelTool",
    "LaunchProsecutorDefenderJudgeTool",
    "LaunchSelfReflectionAgentTool",
    "LaunchSpecialistPanelTool",
    "LaunchToolBackedVerifierTool",
]
