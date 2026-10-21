"""FILE: vidbyte/harnesses/native/compose/__init__.py

PURPOSE: The compose subpackage of the harness thread functions: five composites that run bound steps across Grok, opencode and Muse (chain_threads, verify_with, handoff_thread, run_staged_threads, run_ensemble), nine aliases generated from chain_threads and verify_with, and helpers that bind the nine thread functions into checked steps, capture the diff a block of work made, give a reader a disposable worktree, and ask a step for one validated JSON object; with the records, enums and error they use.
ROLE IN CODEBASE: The public entry point of vidbyte.harnesses.native.compose. Nothing here is re-exported from vidbyte.harnesses.native, vidbyte.harnesses or vidbyte, and `import vidbyte` never imports this package.
ARCHITECTURE NOTE: A package initializer that only imports, binds and re-exports. Each public function and alias is bound to the class attribute that holds it (ThreadBinder in steps.py, DiffCapture and DisposableWorktree in workspace.py, JsonAnswers in answers.py, ThreadChains and ThreadChainPairs in chain.py, ThreadVerifiers and ThreadVerifyTrios in verify.py, ThreadHandoffs in handoff.py, ThreadStages in stages.py, ThreadEnsembles in ensemble.py), as vidbyte/harnesses/native/grok/__init__.py binds its functions; each alias is a ThreadChainPair or ThreadVerifyTrio instance whose signature names its steps (spec INV-24); the records, enums and error are the very vidbyte.lib objects. Importing it starts no process, reads no prompt file and creates no folder; the prompt files load on first use.
FUNCTION INVENTORY: No functions of its own. bind_thread and bind_continue come from ThreadBinder, capture_diff from DiffCapture, in_worktree from DisposableWorktree, parse_json_answer from JsonAnswers, chain_threads from ThreadChains, verify_with from ThreadVerifiers, handoff_thread from ThreadHandoffs, run_staged_threads from ThreadStages and run_ensemble from ThreadEnsembles; the six run_<a>_then_<b> aliases are the ThreadChainPairs members and the three run_<w>_verify_with_<x>_and_<y> aliases the ThreadVerifyTrios members.
COMMON MODIFICATION PATTERNS: Bind each public function or alias to its class attribute and list it in the literal __all__; a new record, enum or error is imported from vidbyte.lib and listed too.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding git or loading a prompt file. 2. Do not export the compose classes (ThreadBinder, StepRoles, ComposeCalls, GrokWorkspaceLocks, ComposeTexts, PromptFitter, ComposeGit, ComposeFailures, DiffCapture, DisposableWorktree, JsonAnswers, AnswerDecoders, ThreadChains, ThreadChainPair, ThreadChainPairs, ThreadVerifiers, ThreadVerifyTrio, ThreadVerifyTrios, ThreadHandoffs, ThreadStages, ThreadEnsembles, EnsembleSelector); they are internal. 3. Do not hand-write an alias; add a ThreadChainPairs or ThreadVerifyTrios member and bind it.
KNOWN EDGE CASES: None; the module only binds and re-exports names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_compose/
"""

from __future__ import annotations

from vidbyte.harnesses.native.compose.answers import JsonAnswers
from vidbyte.harnesses.native.compose.chain import ThreadChainPairs, ThreadChains
from vidbyte.harnesses.native.compose.ensemble import ThreadEnsembles
from vidbyte.harnesses.native.compose.handoff import ThreadHandoffs
from vidbyte.harnesses.native.compose.stages import ThreadStages
from vidbyte.harnesses.native.compose.steps import ThreadBinder
from vidbyte.harnesses.native.compose.verify import ThreadVerifiers, ThreadVerifyTrios
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
chain_threads = ThreadChains.chain_threads
verify_with = ThreadVerifiers.verify_with
handoff_thread = ThreadHandoffs.handoff_thread
run_staged_threads = ThreadStages.run_staged_threads
run_ensemble = ThreadEnsembles.run_ensemble
run_grok_then_opencode = ThreadChainPairs.GROK_THEN_OPENCODE
run_grok_then_muse = ThreadChainPairs.GROK_THEN_MUSE
run_opencode_then_grok = ThreadChainPairs.OPENCODE_THEN_GROK
run_opencode_then_muse = ThreadChainPairs.OPENCODE_THEN_MUSE
run_muse_then_grok = ThreadChainPairs.MUSE_THEN_GROK
run_muse_then_opencode = ThreadChainPairs.MUSE_THEN_OPENCODE
run_grok_verify_with_opencode_and_muse = ThreadVerifyTrios.GROK_WRITES
run_opencode_verify_with_grok_and_muse = ThreadVerifyTrios.OPENCODE_WRITES
run_muse_verify_with_grok_and_opencode = ThreadVerifyTrios.MUSE_WRITES

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
    "chain_threads",
    "handoff_thread",
    "in_worktree",
    "parse_json_answer",
    "run_ensemble",
    "run_grok_then_muse",
    "run_grok_then_opencode",
    "run_grok_verify_with_opencode_and_muse",
    "run_muse_then_grok",
    "run_muse_then_opencode",
    "run_muse_verify_with_grok_and_opencode",
    "run_opencode_then_grok",
    "run_opencode_then_muse",
    "run_opencode_verify_with_grok_and_muse",
    "run_staged_threads",
    "verify_with",
]
