"""Context Protocol Header

Description:
    Central name-to-class dispatch tables that map declarative HarnessSpec
    string names onto the concrete SDK middleware, tool, algorithm, and context
    primitive classes a resolver instantiates.
Purpose:
    Keeps the single source of truth for "which spec name builds which class"
    as static config data beside the SDK's other config constants, so both the
    HarnessSpec validators and the HarnessSpecResolver read one table and can
    never disagree about the allowed namespace.
Architecture:
    - VIDBYTE_MIDDLEWARE_TABLE / VIDBYTE_TOOL_TABLE / VIDBYTE_FILESYSTEM_TOOL_TABLE:
      spec name -> middleware / tool class.
    - VIDBYTE_ALGORITHM_SETTINGS_OWNERS / VIDBYTE_PRIMITIVE_TABLE: preset / kind -> class.
    - VIDBYTE_CONTEXT_MANAGER_TOOL_NAMES / VIDBYTE_PASSTHROUGH_ALGORITHM_PRESETS:
      companion name sets the validators and resolver branch on.
Relations:
    Consumed by vidbyte.environments.spec (validation) and
    vidbyte.environments.resolver (construction).
Similar Files:
    - vidbyte/lib/config/mcp_presets.py: Equivalent static config for MCP presets.

Maintenance note:
    These tables are hand-maintained subsets of the SDK builtins. When a new
    middleware / tool / context primitive / context algorithm becomes
    spec-selectable it must be registered here (and documented in
    skills/environments/SKILL.md). The keys MUST equal each object's runtime
    name (e.g. a tool's ToolSpec.name) so specs, permitted_tool_names, and
    model-facing schemas all share one namespace; never prefix or rename a key.
    A follow-up should derive these tables from the builtin registries so they
    cannot drift out of sync — see the resolver.py multi-agent note for the
    related HarnessSpec evolution plan.
"""

from __future__ import annotations

from vidbyte.context.algorithms import (
    ErrorCorrectionAlgorithm,
    MultiProviderAgenticGraderAlgorithm,
    ProblemSpaceSearchAlgorithm,
    ReflexionAlgorithm,
    TrajectoryCheckpointAlgorithm,
)
from vidbyte.context.primitives import (
    ArtifactContextItem,
    DocumentContextItem,
    EnvironmentContextItem,
    FileContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.middleware.builtins import (
    AuditLogMiddleware,
    CanaryTripwireMiddleware,
    CircuitBreakerMiddleware,
    ConfusedDeputyGuardMiddleware,
    CostBudgetMiddleware,
    ExponentialBackoffRetryMiddleware,
    HoneypotToolMiddleware,
    LoopDetectionMiddleware,
    MessageHistoryCompactionMiddleware,
    ModelRetryMiddleware,
    RuntimeLimitMiddleware,
    SummaryCompactionMiddleware,
    TokenBudgetMiddleware,
    TokenRateLimitMiddleware,
    ToolPolicyMiddleware,
    ToolResultCompactionMiddleware,
    TraceReplacementCompactionMiddleware,
    TraceSummaryTailCompactionMiddleware,
)
from vidbyte.tools.builtins import (
    AttachMcpServerTool,
    CodeExecutionTool,
    ContextListTool,
    ContextRemoveTool,
    ContextUpsertTool,
    CreateHandoffTool,
    GlobTool,
    GrepTool,
    PatchTool,
    ReflexionTool,
    SearchMcpServersTool,
    SemanticSearchTool,
    TrajectoryCheckpointTool,
)
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
from vidbyte.tools.filesystem import (
    AppendTool,
    ChecksumTool,
    CopyTool,
    DeleteTool,
    DiffTool,
    ExistsTool,
    FindTool,
    ListDirTool,
    MakeDirTool,
    MoveTool,
    ReadBinaryTool,
    ReadLinesTool,
    ReadTextTool,
    ReplaceTextTool,
    StatTool,
    TouchTool,
    TreeTool,
    UnzipTool,
    WriteTextTool,
    ZipTool,
)

VIDBYTE_MIDDLEWARE_TABLE: dict[str, type] = {
    "audit_log": AuditLogMiddleware,
    "canary_tripwire": CanaryTripwireMiddleware,
    "circuit_breaker": CircuitBreakerMiddleware,
    "confused_deputy_guard": ConfusedDeputyGuardMiddleware,
    "cost_budget": CostBudgetMiddleware,
    "exponential_backoff_retry": ExponentialBackoffRetryMiddleware,
    "honeypot_tool": HoneypotToolMiddleware,
    "loop_detection": LoopDetectionMiddleware,
    "message_history_compaction": MessageHistoryCompactionMiddleware,
    "model_retry": ModelRetryMiddleware,
    "runtime_limits": RuntimeLimitMiddleware,
    "summary_compaction": SummaryCompactionMiddleware,
    "token_budget": TokenBudgetMiddleware,
    "token_rate_limit": TokenRateLimitMiddleware,
    "tool_policy": ToolPolicyMiddleware,
    "tool_result_compaction": ToolResultCompactionMiddleware,
    "trace_replacement_compaction": TraceReplacementCompactionMiddleware,
    "trace_summary_tail_compaction": TraceSummaryTailCompactionMiddleware,
}

# Tools whose constructor requires the resolved ContextManager instead of settings-only kwargs.
VIDBYTE_CONTEXT_MANAGER_TOOL_NAMES: frozenset[str] = frozenset(
    {"reflexion", "trajectory_checkpoint", "context_upsert", "context_list", "context_remove"}
)

# Filesystem tools take a FileSystemToolConfig; the resolver defaults root to the workspace.
# Keys equal each tool's runtime ToolSpec name so specs, permitted_tool_names, and
# model-facing schemas all share one namespace.
VIDBYTE_FILESYSTEM_TOOL_TABLE: dict[str, type] = {
    "append_text": AppendTool,
    "checksum": ChecksumTool,
    "copy": CopyTool,
    "delete": DeleteTool,
    "diff": DiffTool,
    "exists": ExistsTool,
    "find": FindTool,
    "list_dir": ListDirTool,
    "make_dir": MakeDirTool,
    "move": MoveTool,
    "read_binary": ReadBinaryTool,
    "read_lines": ReadLinesTool,
    "read_text": ReadTextTool,
    "replace_text": ReplaceTextTool,
    "stat": StatTool,
    "touch": TouchTool,
    "tree": TreeTool,
    "unzip": UnzipTool,
    "write_text": WriteTextTool,
    "zip": ZipTool,
}

VIDBYTE_TOOL_TABLE: dict[str, type] = {
    "attach_mcp_server": AttachMcpServerTool,
    "calculator": CalculatorTool,
    "code_execution": CodeExecutionTool,
    "context_list": ContextListTool,
    "context_remove": ContextRemoveTool,
    "context_upsert": ContextUpsertTool,
    "create_handoff": CreateHandoffTool,
    "document_retrieval": DocumentRetrievalTool,
    "glob": GlobTool,
    "grep": GrepTool,
    "patch_file": PatchTool,
    "reflexion": ReflexionTool,
    "search_mcp_servers": SearchMcpServersTool,
    "semantic_search": SemanticSearchTool,
    "trajectory_checkpoint": TrajectoryCheckpointTool,
    **VIDBYTE_FILESYSTEM_TOOL_TABLE,
}

VIDBYTE_ALGORITHM_SETTINGS_OWNERS: dict[str, type] = {
    "error_correction": ErrorCorrectionAlgorithm,
    "multi_provider_agentic_grader": MultiProviderAgenticGraderAlgorithm,
    "problem_space_search": ProblemSpaceSearchAlgorithm,
    "reflexion": ReflexionAlgorithm,
    "trajectory_checkpoints": TrajectoryCheckpointAlgorithm,
}

# Preset names that carry no settings-bearing algorithm dataclass.
VIDBYTE_PASSTHROUGH_ALGORITHM_PRESETS: frozenset[str] = frozenset(
    {"default", "raw_tool_outputs", "compact_tool_outputs", "hide_tool_outputs", "no_raw_tool_outputs"}
)

VIDBYTE_PRIMITIVE_TABLE: dict[str, type] = {
    "artifact": ArtifactContextItem,
    "document": DocumentContextItem,
    "environment": EnvironmentContextItem,
    "file": FileContextItem,
    "git_diff": GitDiffContextItem,
    "memory": MemoryContextItem,
    "plan": PlanContextItem,
    "progress": ProgressContextItem,
    "response": ResponseContextItem,
    "task": TaskContextItem,
    "text": TextContextItem,
    "tool_call": ToolCallContextItem,
}


__all__ = [
    "VIDBYTE_ALGORITHM_SETTINGS_OWNERS",
    "VIDBYTE_CONTEXT_MANAGER_TOOL_NAMES",
    "VIDBYTE_FILESYSTEM_TOOL_TABLE",
    "VIDBYTE_MIDDLEWARE_TABLE",
    "VIDBYTE_PASSTHROUGH_ALGORITHM_PRESETS",
    "VIDBYTE_PRIMITIVE_TABLE",
    "VIDBYTE_TOOL_TABLE",
]
