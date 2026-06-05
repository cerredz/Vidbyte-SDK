"""Context Protocol Header

Description:
    Defines the artifact-oriented continual trace schema (output/artifact lens).
Purpose:
    Gives developers a ready-made typed schema for recording the concrete things an
    agent produces: files, code, documents, data, and their verification state.
Architecture:
    Pydantic model declaring typed, described fields, converted to a module-level
    TraceSchema constant via TraceSchema.from_model.
Relations:
    Re-exported by vidbyte.trace.continual.prebuilt and vidbyte.trace.continual.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vidbyte.lib.dataclasses.trace import TraceSchema


class ArtifactTraceModel(BaseModel):
    """Artifact-oriented continual trace: what the run produced and its verification state."""

    goal: str = Field(
        description=(
            "What the run is meant to produce. Capture the intended deliverable so a reader knows what the "
            "artifacts are for. Keep this stable unless the context redefines it."
        ),
    )
    artifacts: list[str] = Field(
        default_factory=list,
        description=(
            "Every concrete output the agent has produced (files, documents, data, answers). Append each "
            "artifact as it is created; this is the running catalog of outputs."
        ),
    )
    files_created: list[str] = Field(
        default_factory=list,
        description=(
            "Paths of files newly created. Append each created file as it appears."
        ),
    )
    files_modified: list[str] = Field(
        default_factory=list,
        description=(
            "Paths of files modified. Append each modified file; a path may recur if edited multiple times."
        ),
    )
    files_deleted: list[str] = Field(
        default_factory=list,
        description=(
            "Paths of files deleted. Append each deleted file as it appears."
        ),
    )
    code_changes: list[str] = Field(
        default_factory=list,
        description=(
            "Summaries of code changes made (functions added, logic changed), grouped by area when useful. "
            "Append each meaningful change."
        ),
    )
    documents_produced: list[str] = Field(
        default_factory=list,
        description=(
            "Documents, reports, or written content produced. Append each document as it is created."
        ),
    )
    data_outputs: list[str] = Field(
        default_factory=list,
        description=(
            "Datasets, tables, or structured data the agent generated. Append each data output as it is "
            "produced."
        ),
    )
    descriptions: list[str] = Field(
        default_factory=list,
        description=(
            "A short description of what each artifact is and why it was produced. Append one description "
            "per significant artifact."
        ),
    )
    artifact_status: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "A map from artifact name to its status (for example draft, final, verified, broken). Provide "
            "only the keys that changed; entries are deep-merged into the existing map rather than replacing "
            "it wholesale."
        ),
    )
    verification: list[str] = Field(
        default_factory=list,
        description=(
            "How each artifact was checked or validated (tests run, manual review, parity checks). Append "
            "each verification action; this distinguishes proven outputs from assumed-good ones."
        ),
    )
    tests_added: list[str] = Field(
        default_factory=list,
        description=(
            "Tests written to cover the produced work. Append each test as it is added."
        ),
    )
    tests_passing: list[str] = Field(
        default_factory=list,
        description=(
            "Tests currently passing. Append tests as they are confirmed green; a test may move from "
            "failing to passing across updates."
        ),
    )
    tests_failing: list[str] = Field(
        default_factory=list,
        description=(
            "Tests currently failing, with a short reason. Append failing tests; reflect fixes by adding to "
            "tests_passing rather than deleting here."
        ),
    )
    dependencies_added: list[str] = Field(
        default_factory=list,
        description=(
            "New libraries, packages, or dependencies introduced. Append each dependency added during the "
            "run."
        ),
    )
    configuration_changes: list[str] = Field(
        default_factory=list,
        description=(
            "Changes to configuration, environment, or settings. Append each configuration change as it is "
            "made."
        ),
    )
    side_effects: list[str] = Field(
        default_factory=list,
        description=(
            "Effects beyond the primary artifacts (caches written, services restarted, external records "
            "created). Append each side effect so the full footprint is visible."
        ),
    )
    locations: list[str] = Field(
        default_factory=list,
        description=(
            "Where each artifact lives (paths, URLs, identifiers). Append each location so a successor can "
            "find the outputs."
        ),
    )
    pending_artifacts: list[str] = Field(
        default_factory=list,
        description=(
            "Outputs the agent still intends to produce but has not yet. Append each pending artifact; an "
            "item may later move into artifacts once created."
        ),
    )
    rework: list[str] = Field(
        default_factory=list,
        description=(
            "Artifacts that were redone or substantially revised, with the reason. Append each rework event "
            "so churn is visible."
        ),
    )
    quality_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Observations about the quality, completeness, or risk of the artifacts. Append each note as it "
            "arises."
        ),
    )
    final_deliverables: list[str] = Field(
        default_factory=list,
        description=(
            "The artifacts intended as the run's final deliverables. Append each as it is finalized; this "
            "separates the headline outputs from intermediate ones."
        ),
    )
    current_artifact: str = Field(
        default="",
        description=(
            "The artifact the agent is actively working on right now. Overwrite with the single "
            "most-current artifact in progress."
        ),
    )
    artifact_count: int = Field(
        default=0,
        description=(
            "The running total of artifacts produced. Overwrite with the latest count."
        ),
    )


ArtifactTrace = TraceSchema.from_model(
    ArtifactTraceModel,
    name="artifact_trace",
    description="Tracks the concrete artifacts the agent produces and their verification state.",
)

__all__ = [
    "ArtifactTrace",
    "ArtifactTraceModel",
]
