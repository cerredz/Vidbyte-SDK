"""FILE: vidbyte/harnesses/native/compose/__init__.py

PURPOSE: The compose subpackage of the harness thread functions: helpers that bind the nine thread functions into checked steps, capture the diff a block of work made, give a reader a disposable worktree, and ask a step for one validated JSON object; with the records, enums and error they use.
ROLE IN CODEBASE: The public entry point of vidbyte.harnesses.native.compose. Nothing here is re-exported from vidbyte.harnesses.native, vidbyte.harnesses or vidbyte, and `import vidbyte` never imports this package.
ARCHITECTURE NOTE: A package initializer that only imports, binds and re-exports. Each public function is bound to the class attribute that holds it (ThreadBinder in steps.py, DiffCapture and DisposableWorktree in workspace.py, JsonAnswers in answers.py), as vidbyte/harnesses/native/grok/__init__.py binds its functions; the records, enums and error are the very vidbyte.lib objects. Importing it starts no process, reads no prompt file and creates no folder; the prompt files load on first use.
FUNCTION INVENTORY: No functions of its own. bind_thread and bind_continue come from ThreadBinder, capture_diff from DiffCapture, in_worktree from DisposableWorktree, and parse_json_answer from JsonAnswers.
COMMON MODIFICATION PATTERNS: Bind each public function or alias to its class attribute and list it in the literal __all__; a new record, enum or error is imported from vidbyte.lib and listed too.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding git or loading a prompt file. 2. Do not export the plumbing classes (ThreadBinder, StepRoles, ComposeCalls, GrokWorkspaceLocks, ComposeTexts, PromptFitter, ComposeGit, ComposeFailures, AnswerDecoders); they are internal.
KNOWN EDGE CASES: None; the module only binds and re-exports names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/
"""

from __future__ import annotations

from vidbyte.harnesses.native.compose.answers import JsonAnswers
from vidbyte.harnesses.native.compose.steps import ThreadBinder
from vidbyte.harnesses.native.compose.workspace import DiffCapture, DisposableWorktree
from vidbyte.lib.dataclasses.native_compose import (
    ChainResult,
    HandoffResult,
    JsonAnswer,
    StageAttempt,
    StagedResult,
    StageOutcome,
    StageSpec,
    StepOutcome,
    ThreadStep,
    ThreadVerdict,
    VerifyResult,
    WorkspaceDiff,
)
from vidbyte.lib.dataclasses.native_ensemble import (
    EnsemblePlan,
    EnsembleResult,
    EnsembleRole,
    EnsembleRoster,
    EnsembleRound,
    EnsembleSelection,
)
from vidbyte.lib.enums.native_compose import (
    EnsembleStage,
    StageDecision,
    ThreadComposeProblem,
    VerdictDecision,
)
from vidbyte.lib.errors import ThreadComposeError

bind_thread = ThreadBinder.bind_thread
bind_continue = ThreadBinder.bind_continue
capture_diff = DiffCapture.capture_diff
in_worktree = DisposableWorktree.in_worktree
parse_json_answer = JsonAnswers.parse_json_answer

__all__ = [
    "ChainResult",
    "EnsemblePlan",
    "EnsembleResult",
    "EnsembleRole",
    "EnsembleRoster",
    "EnsembleRound",
    "EnsembleSelection",
    "EnsembleStage",
    "HandoffResult",
    "JsonAnswer",
    "StageAttempt",
    "StageDecision",
    "StageOutcome",
    "StageSpec",
    "StagedResult",
    "StepOutcome",
    "ThreadComposeError",
    "ThreadComposeProblem",
    "ThreadStep",
    "ThreadVerdict",
    "VerdictDecision",
    "VerifyResult",
    "WorkspaceDiff",
    "bind_continue",
    "bind_thread",
    "capture_diff",
    "in_worktree",
    "parse_json_answer",
]
