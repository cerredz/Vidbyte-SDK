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
        title="Goal",
        min_length=1,
        description=(
            "What the run is meant to produce, recorded to orient a reader of the artifact trace who needs to understand what deliverables the agent was expected to create. "
            "Write this as a clear statement of the intended output so a reviewer can judge whether the artifacts produced match the stated objective and whether the scope stayed on target. "
            "Keep this field stable unless the context redefines the deliverable, since the goal is the benchmark against which artifact completeness is measured across the entire run. "
            "A reviewer reading this field can immediately understand the purpose of every artifact in the log and assess whether the agent produced the right things rather than just any things. "
            "If the expected deliverable changed mid-run, note the change here so a reviewer understands why the artifact log may contain outputs that differ from the original scope."
        ),
    )
    artifacts: list[str] = Field(
        title="Artifacts",
        min_length=0,
        default_factory=list,
        description=(
            "Every concrete output the agent has produced during the run, including files, documents, data payloads, and answers, forming the running catalog of all deliverables created so far. "
            "Append each artifact as it is created, using a specific identifier such as a file path or a short name, so the catalog is both complete and navigable without scanning free-form text. "
            "This field is the master inventory of the run's outputs: every other artifact field categorizes or adds detail to entries that should first appear here. "
            "A reviewer reading this field can immediately see everything the agent produced, which is essential for assessing completeness and identifying outputs that were not requested. "
            "If an artifact was later superseded or deleted, leave its entry in place and note the change in the appropriate sub-field, since the production history is part of the audit trail."
        ),
    )
    files_created: list[str] = Field(
        title="Files Created",
        min_length=0,
        default_factory=list,
        description=(
            "Paths of files newly created by the agent during the run, each appended as the file appears so the creation log reflects the actual sequence of file production. "
            "Append each created file path as the write is confirmed, including both final deliverables and intermediate files that support the main output. "
            "A file path should be exact and absolute when possible so a reviewer or successor can locate the file without guessing at the directory structure. "
            "A reviewer reading this field can immediately inventory all new files the agent wrote, which is essential for auditing the run's file-system footprint and locating deliverables. "
            "If a file was created and later deleted in the same run, still record the creation here and note the deletion in files_deleted, since both events are part of the audit trail."
        ),
    )
    files_modified: list[str] = Field(
        title="Files Modified",
        min_length=0,
        default_factory=list,
        description=(
            "Paths of pre-existing files modified by the agent during the run, each appended as the modification is confirmed, with a path allowed to appear more than once if edited at multiple points. "
            "Append each modified path as the edit is made rather than batching at the end, so the log reflects the actual sequence of file modifications during execution. "
            "Distinguish between content updates, structural changes, and partial edits when possible, since the nature of the modification affects how a reviewer should assess the change. "
            "A reviewer reading this field can quickly see which pre-existing files the agent changed, which is critical for auditing the run's impact on shared or sensitive resources. "
            "If a modification was a direct consequence of a specific decision or tool call, cross-reference that event so the reviewer understands the causal chain behind the change."
        ),
    )
    files_deleted: list[str] = Field(
        title="Files Deleted",
        min_length=0,
        default_factory=list,
        description=(
            "Paths of files deleted by the agent during the run, each appended as the deletion is confirmed, and never removed from this list afterward since deletions are irreversible audit events. "
            "Note whether each deletion was intentional and sanctioned by the user's instructions, or whether it was an unintended side effect of another operation that may warrant review. "
            "A file deleted by the agent may be unrecoverable depending on the environment, so this field must be a complete and honest record even when deletions were accidental. "
            "A reviewer reading this field has an immediate inventory of all files removed by the agent, which is critical for security audits and for recovering from any unintended deletions. "
            "If the deleted file can be restored from version control or a backup, note that explicitly so a reviewer or successor knows whether the deletion is recoverable."
        ),
    )
    code_changes: list[str] = Field(
        title="Code Changes",
        min_length=0,
        default_factory=list,
        description=(
            "Summaries of code changes made during the run, each describing what was added, modified, or removed at a level of detail sufficient for a code reviewer to understand the scope without reading every diff. "
            "Append each meaningful change grouped by area or file when several changes form a coherent unit, so the log is readable without becoming a line-by-line transcript of the diffs. "
            "Focus on changes that affect behavior rather than purely cosmetic changes, since behavioral changes are what a reviewer needs to understand and verify most carefully. "
            "A successor reading this field can understand what code the original agent changed and decide whether any of those changes need to be revisited, extended, or rolled back. "
            "If a code change introduced a regression or a known issue, note that in tests_failing or quality_notes rather than here, keeping this field focused on describing what changed rather than evaluating it."
        ),
    )
    documents_produced: list[str] = Field(
        title="Documents Produced",
        min_length=0,
        default_factory=list,
        description=(
            "Documents, reports, or written content produced during the run, each recorded with an identifier and a brief description of its content so a reviewer can find and assess the output. "
            "Append each document as it is created, distinguishing written deliverables from code and data outputs so a reviewer can apply the appropriate review lens to each category. "
            "A document in this context includes any prose-heavy output: markdown files, reports, summaries, plans, specifications, and explanatory text that the user is meant to read. "
            "A reviewer reading this field can quickly identify all prose outputs the agent produced and assess whether they are accurate, complete, and appropriate for their intended audience. "
            "If a document was generated from a template or from structured data rather than written fresh, note the generation approach so a reviewer knows whether a manual review of the prose is still warranted."
        ),
    )
    data_outputs: list[str] = Field(
        title="Data Outputs",
        min_length=0,
        default_factory=list,
        description=(
            "Datasets, tables, or structured data the agent generated during the run, each recorded with an identifier and a brief description of the format and contents so a reviewer can locate and validate them. "
            "Append each data output as it is produced, distinguishing structured data from code and prose outputs so a reviewer can apply appropriate data validation rather than a generic review. "
            "A data output in this context includes any structured artifact: JSON files, CSV exports, database records, configuration payloads, and any other machine-readable structured content. "
            "A reviewer reading this field can quickly identify all structured data the agent produced and target validation efforts appropriately rather than treating all files as equivalent. "
            "If a data output contains sensitive information, note that explicitly so a reviewer knows to apply appropriate handling requirements before the artifact is shared or deployed."
        ),
    )
    descriptions: list[str] = Field(
        title="Descriptions",
        min_length=0,
        default_factory=list,
        description=(
            "A short description of what each significant artifact is and why it was produced, appended one per artifact in the order artifacts were created. "
            "Each description should explain the artifact's purpose and intended consumer, not just what it contains, so a reviewer understands the role of each output in the run's overall deliverable set. "
            "This field provides the narrative context that file paths and identifiers alone cannot convey, turning a list of outputs into an understandable picture of what the run accomplished. "
            "A successor reading this field can quickly orient to the artifact set and understand which outputs are most important without needing to open each file to assess its purpose. "
            "If an artifact's description changed as the run evolved, append the updated description rather than overwriting the original, so a reviewer can see how the artifact's role evolved."
        ),
    )
    artifact_status: dict[str, str] = Field(
        title="Artifact Status",
        default_factory=dict,
        description=(
            "A map from artifact name or path to its current status, such as draft, final, verified, or broken, providing a quick-reference view of the state of every tracked artifact. "
            "Provide only the keys that changed or were newly added in each update rather than the full map, since entries are deep-merged into the existing map rather than replacing it wholesale. "
            "Use consistent, machine-readable status values so a reviewer or tool consuming the trace can programmatically filter artifacts by status without needing to parse free-form text. "
            "This field gives a reviewer a snapshot of the artifact registry at a glance, allowing them to see what is done, what is in progress, and what is broken without reading through every list field. "
            "If an artifact transitions through multiple statuses in the same update, record the final current status rather than the intermediate ones, since this field reflects current state rather than transition history."
        ),
    )
    verification: list[str] = Field(
        title="Verification",
        min_length=0,
        default_factory=list,
        description=(
            "How each significant artifact was checked or validated during the run, including tests run, manual reviews performed, parity checks, and any other quality verification actions taken. "
            "Append each verification action as it is performed, noting the artifact it applies to and the outcome, so a reviewer can see which outputs have been confirmed and which are assumed good. "
            "This field is what distinguishes a proven output from an assumed-good one: a reviewer reading it can immediately identify artifacts that were rigorously verified versus those that were produced and left unchecked. "
            "A successor reading this field knows which artifacts still need verification and can prioritize that work before relying on unverified outputs in subsequent steps. "
            "If a verification step revealed a defect, cross-reference the corresponding entry in tests_failing or quality_notes so the full quality picture of each artifact is visible across fields."
        ),
    )
    tests_added: list[str] = Field(
        title="Tests Added",
        min_length=0,
        default_factory=list,
        description=(
            "Tests written during the run to cover the produced work, each recorded with the test name or path and a brief description of what it verifies. "
            "Append each test as it is written, including unit tests, integration tests, and any other automated checks created to validate the run's outputs. "
            "Recording tests as they are added provides a live view of the growing test coverage, allowing a reviewer to see whether the agent was building verification alongside the work rather than leaving testing for the end. "
            "A successor reading this field knows which tests were added for the current work and can run them directly to verify the state of the artifacts without needing to identify which tests are relevant from a larger suite. "
            "If a test was added but covers pre-existing functionality rather than the new work, note that so a reviewer can correctly assess the coverage added specifically for this run's outputs."
        ),
    )
    tests_passing: list[str] = Field(
        title="Tests Passing",
        min_length=0,
        default_factory=list,
        description=(
            "Tests currently confirmed as passing, each appended as its green status is verified, so a reviewer can see which parts of the artifact set are already confirmed working. "
            "Append tests as they are confirmed passing rather than pre-populating from the test plan, since only executed and confirmed tests belong in this field. "
            "A test may move from tests_failing to this field across updates when a fix is applied, and recording that movement shows the agent's progress in resolving quality issues. "
            "A reviewer reading this field can quickly assess how much of the run's output has been verified as working and how much still needs attention. "
            "If a test was previously passing but regressed, reflect that by adding it to tests_failing rather than removing it from here, keeping both fields as append-only logs."
        ),
    )
    tests_failing: list[str] = Field(
        title="Tests Failing",
        min_length=0,
        default_factory=list,
        description=(
            "Tests currently failing, each recorded with a short reason so a reviewer can understand what is broken without needing to run the tests themselves. "
            "Append each failing test as it is discovered, including both pre-existing failures and regressions introduced by the run's changes, so the full set of broken tests is visible. "
            "Reflect a fix by adding the test to tests_passing rather than removing it from here, so the history of which tests failed and were fixed is preserved rather than erased. "
            "A successor reading this field knows exactly what is broken as of the last update and can prioritize fixing the failing tests before producing additional artifacts. "
            "If a failing test is a pre-existing failure unrelated to the current run's changes, note that explicitly so a reviewer can distinguish new regressions from inherited technical debt."
        ),
    )
    dependencies_added: list[str] = Field(
        title="Dependencies Added",
        min_length=0,
        default_factory=list,
        description=(
            "New libraries, packages, or external dependencies introduced during the run, each recorded with the dependency name, version, and the reason it was added. "
            "Append each dependency as it is installed or declared, so the run's dependency footprint is fully visible without requiring a diff of the package manifest. "
            "Recording the reason a dependency was added is important for a reviewer assessing whether the dependency is justified, since many dependencies add significant size and security surface area. "
            "A successor reading this field knows exactly what new dependencies the original agent introduced and can verify they are still present and at the expected versions before relying on them. "
            "If a dependency was added as a development or test dependency rather than a production one, note that distinction so a reviewer can apply the appropriate level of scrutiny."
        ),
    )
    configuration_changes: list[str] = Field(
        title="Configuration Changes",
        min_length=0,
        default_factory=list,
        description=(
            "Changes to configuration files, environment variables, or settings made during the run, each recorded with enough detail to understand what changed and why. "
            "Append each configuration change as it is made, noting the specific file or setting and the before-and-after values when both are available. "
            "Configuration changes are often subtle and high-impact: a reviewer needs to see them explicitly rather than discovering them by diffing config files. "
            "A successor reading this field knows what configuration the original agent changed and can verify those settings are still in place before continuing work that depends on them. "
            "If a configuration change was temporary or environment-specific and should not be committed or deployed, note that explicitly so it is not accidentally treated as a permanent change."
        ),
    )
    side_effects: list[str] = Field(
        title="Side Effects",
        min_length=0,
        default_factory=list,
        description=(
            "Effects produced beyond the primary artifacts, such as cache entries written, services restarted, external records created, or shared state mutated, each recorded so the run's full footprint is visible. "
            "Append each side effect as it is produced, naming the affected system and the nature of the change, since side effects are often the hardest category of output to discover through normal review. "
            "This field is important for compliance and security reviews: a reviewer can see exactly what durable effects the agent produced outside its primary output files without re-running the agent. "
            "A successor reading this field knows what the original agent changed beyond its files and can decide whether those side effects need to be reversed, extended, or simply acknowledged before continuing. "
            "If a side effect is reversible and was only intended as temporary, note that so a reviewer or successor knows whether cleaning it up is part of the remaining work."
        ),
    )
    locations: list[str] = Field(
        title="Locations",
        min_length=0,
        default_factory=list,
        description=(
            "Where each significant artifact lives, expressed as file paths, URLs, or other identifiers that allow a reviewer or successor to locate the output without guessing. "
            "Append each location as it becomes known, noting the artifact it corresponds to so the mapping from artifact to location is explicit rather than requiring inference. "
            "A location entry is most valuable when the artifact is in a non-obvious place, such as a temporary directory, a remote store, or an auto-generated path. "
            "A successor reading this field can immediately find all the run's outputs without scanning the file system or running search commands, which is essential for a fast handoff. "
            "If an artifact moved between locations during the run, record both the original and final locations so a reviewer understands the full path the artifact took."
        ),
    )
    pending_artifacts: list[str] = Field(
        title="Pending Artifacts",
        min_length=0,
        default_factory=list,
        description=(
            "Outputs the agent still intends to produce but has not yet started or completed, each recorded with enough detail that a successor knows what to create without needing to re-derive the plan. "
            "Append each pending artifact as it enters the plan and reflect its completion by adding it to artifacts rather than removing it from here, so the full planned scope is always visible. "
            "This field is one of the most important for handoffs: a successor reading it knows exactly what deliverables remain and can prioritize them without first reverse-engineering the agent's original plan. "
            "Include an honest estimate of the effort required for each pending artifact when possible, since this helps a successor allocate its time appropriately across the remaining work. "
            "If a pending artifact was deprioritized or dropped, note that in a separate entry rather than removing the original, so the decision to not produce it is explicitly visible."
        ),
    )
    rework: list[str] = Field(
        title="Rework",
        min_length=0,
        default_factory=list,
        description=(
            "Artifacts that were redone or substantially revised after their initial production, each recorded with the artifact identifier, what was wrong with the original, and what changed in the revision. "
            "Append each rework event as it occurs so the churn in the artifact set is visible and quantifiable by a reviewer assessing the efficiency of the run. "
            "A high rework rate is a signal that the agent was not getting the work right the first time, which may indicate unclear requirements, poor validation, or a problematic approach. "
            "A reviewer reading this field can identify which artifacts required multiple attempts and investigate whether the root cause of the rework was preventable. "
            "If rework was driven by a change in requirements rather than a quality failure, note that so a reviewer can correctly attribute the revision to scope change rather than agent error."
        ),
    )
    quality_notes: list[str] = Field(
        title="Quality Notes",
        min_length=0,
        default_factory=list,
        description=(
            "Observations about the quality, completeness, or risk of the artifacts produced, each recorded as a specific note that a reviewer can act on rather than a vague concern. "
            "Append each quality observation as it arises, whether it is positive, negative, or a known limitation the agent is flagging for a reviewer's attention. "
            "Quality notes are the agent's honest assessment of its own outputs, and they are most valuable when they identify issues the agent could not resolve within the run's constraints. "
            "A reviewer reading this field can quickly identify areas where the artifacts may need additional scrutiny or follow-up work before they are considered production-ready. "
            "If a quality note describes a known defect, cross-reference the corresponding test_failing entry when one exists so the reviewer can see both the note and the automated evidence together."
        ),
    )
    final_deliverables: list[str] = Field(
        title="Final Deliverables",
        min_length=0,
        default_factory=list,
        description=(
            "The artifacts intended as the run's primary outputs to the user, each appended as it reaches final status to separate the headline deliverables from intermediate or supporting outputs. "
            "Only add an artifact to this field when it is genuinely complete and verified, not when the first draft is written, so a reviewer can rely on this field as a list of actually finished deliverables. "
            "This field is a curated subset of the artifacts field, containing only the outputs the user is directly expecting to receive from the run. "
            "A reviewer reading this field can immediately see the run's final deliverables without sifting through the full artifact catalog, which is the most important view for assessing whether the run succeeded. "
            "If a final deliverable has known limitations or caveats a user should be aware of, note those in quality_notes and cross-reference from here so a reviewer can find the caveats alongside the deliverable."
        ),
    )
    current_artifact: str = Field(
        title="Current Artifact",
        min_length=0,
        default="",
        description=(
            "The artifact the agent is actively working on right now, identified by path or name, so a reader can immediately understand what is being produced at the current moment. "
            "Overwrite this field with the single most-current artifact under active production on every update, keeping it synchronized with the agent's present focus. "
            "Leave this empty only when the agent is not currently producing or modifying any artifact, such as when planning or waiting for a tool result, so an empty value reliably signals an execution pause. "
            "A successor reading this field can immediately see where the original agent was focused at the moment of the last update, which is the most direct entry point for continuing the work. "
            "If the agent is working on multiple artifacts simultaneously, name the one receiving the most immediate attention and note the others in pending_artifacts."
        ),
    )
    artifact_count: int = Field(
        title="Artifact Count",
        default=0,
        description=(
            "The running total of all artifacts recorded in this trace, giving a quick measure of the run's overall production volume without requiring a reader to count entries manually. "
            "Overwrite this field with the latest count on every update, keeping it synchronized with the actual number of distinct entries across the artifact catalog. "
            "Use this count as a proxy for run scope: a very high artifact count relative to the goal may indicate over-production or scope creep, while a low count relative to a complex goal may signal incomplete work. "
            "A reviewer seeing an artifact count inconsistent with the stated goal can use it as a signal to investigate whether the agent stayed on scope or produced unintended outputs. "
            "If the exact count is uncertain due to overlap between artifact categories, provide the best available approximation with a note rather than leaving this at zero."
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
