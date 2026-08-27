"""Context Protocol Header

Description:
    Defines VerifierTargetResolver.
Purpose:
    Decides what object gets handed to the verifiers, and optionally attaches
    the agent's accumulated context-window primitives to that object.
Architecture:
    - VerifierTargetResolver: dispatches to a per-mode private resolver, then
      attaches selected context primitives to every VerifierTarget it builds.
      Every mode except CUSTOM also carries context.workspace_root onto the
      VerifierTarget it returns, since any execution-based verifier (a test
      suite, a Lean proof) needs a directory to run in.
    ContextPrimitiveSelectorParams and VerifierTargetResolverParams (both
    validated dataclasses) live in vidbyte.lib.dataclasses.verifier, not
    here, per review feedback on PR #349.
Relations:
    Produces vidbyte.agents.runtimes.verifier.types.VerifierTarget, consumed
    by VerifierCollection.run(). Reads vidbyte.context.manager.ContextManager.
Similar Files:
    - vidbyte/context/manager.py: ContextManager, the source this resolver
      reads from for the context-primitive port-in.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
from collections.abc import Mapping
from typing import Any

from vidbyte.agents.runtimes.verifier.types import ResolutionContext, TargetResolutionMode, VerifierTarget
from vidbyte.context.primitives import ContextItem
from vidbyte.lib.dataclasses.verifier import ContextPrimitiveSelectorParams, VerifierTargetResolverParams


class VerifierTargetResolver:
    """Builds the VerifierTarget handed to every verifier for one finalization attempt."""

    def __init__(self, params: VerifierTargetResolverParams) -> None:
        # Stores the already-validated configuration for this resolver instance.
        self.params = params

    def resolve(self, context: ResolutionContext) -> VerifierTarget:
        """Builds a VerifierTarget from context, including any selected context-window primitives."""
        base = self._resolve_by_mode(context)
        primitives = self._resolve_context_primitives(context)
        if not primitives:
            return base
        return VerifierTarget(
            mode=base.mode,
            text=base.text,
            file_paths=base.file_paths,
            diff=base.diff,
            submission=base.submission,
            context_primitives=primitives,
            workspace_root=base.workspace_root,
        )

    def _resolve_by_mode(self, context: ResolutionContext) -> VerifierTarget:
        # Single dispatch point over the five TargetResolutionMode values.
        if self.params.mode is TargetResolutionMode.FINAL_OUTPUT_TEXT:
            return self._resolve_final_output_text(context)
        if self.params.mode is TargetResolutionMode.WORKSPACE_FILES:
            return self._resolve_workspace_files(context)
        if self.params.mode is TargetResolutionMode.WORKSPACE_DIFF:
            return self._resolve_workspace_diff(context)
        if self.params.mode is TargetResolutionMode.STRUCTURED_SUBMISSION:
            return self._resolve_structured_submission(context)
        return self.params.custom_resolver(context)

    def _resolve_final_output_text(self, context: ResolutionContext) -> VerifierTarget:
        # The simplest mode: whatever the model's candidate final text currently is.
        return VerifierTarget(mode=TargetResolutionMode.FINAL_OUTPUT_TEXT, text=context.candidate_output, workspace_root=context.workspace_root)

    def _resolve_workspace_files(self, context: ResolutionContext) -> VerifierTarget:
        # Collects file paths matching include_patterns under the workspace root; contents are not read here.
        if context.workspace_root is None or not self.params.include_patterns:
            return VerifierTarget(mode=TargetResolutionMode.WORKSPACE_FILES, file_paths=(), workspace_root=context.workspace_root)
        matches: list[str] = []
        for pattern in self.params.include_patterns:
            matches.extend(glob.glob(os.path.join(context.workspace_root, pattern), recursive=True))
        return VerifierTarget(mode=TargetResolutionMode.WORKSPACE_FILES, file_paths=tuple(sorted(set(matches))), workspace_root=context.workspace_root)

    def _resolve_workspace_diff(self, context: ResolutionContext) -> VerifierTarget:
        # Shells out to `git diff`; a missing workspace or a non-git directory yields an empty diff, not an error.
        if context.workspace_root is None:
            return VerifierTarget(mode=TargetResolutionMode.WORKSPACE_DIFF, diff="", workspace_root=None)
        diff = self._git_diff(context.workspace_root)
        return VerifierTarget(mode=TargetResolutionMode.WORKSPACE_DIFF, diff=diff, workspace_root=context.workspace_root)

    @staticmethod
    def _git_diff(workspace_root: str) -> str:
        # Best-effort git diff read; any failure (no git, no repo) degrades to an empty string.
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=workspace_root,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return result.stdout if result.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    def _resolve_structured_submission(self, context: ResolutionContext) -> VerifierTarget:
        # Scans the transcript backward for the most recent call to submission_tool_name.
        submission = self._latest_submission(context.messages)
        return VerifierTarget(mode=TargetResolutionMode.STRUCTURED_SUBMISSION, submission=submission, workspace_root=context.workspace_root)

    def _latest_submission(self, messages: Any) -> Mapping[str, Any] | None:
        # Returns None (not an error) when the submission tool has not been called yet this run.
        for message in reversed(list(messages)):
            name = message.get("name") or message.get("tool_name")
            if message.get("role") == "tool" and name == self.params.submission_tool_name:
                return self._parse_submission_content(message.get("content"))
        return None

    @staticmethod
    def _parse_submission_content(content: Any) -> Mapping[str, Any]:
        # Prefers a JSON object; falls back to wrapping unparseable content rather than raising.
        if isinstance(content, Mapping):
            return dict(content)
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, Mapping):
                    return dict(parsed)
            except json.JSONDecodeError:
                pass
            return {"raw": content}
        return {"raw": content}

    def _resolve_context_primitives(self, context: ResolutionContext) -> tuple[ContextItem, ...]:
        # Returns () whenever the agent has no attached ContextManager or no selector was configured.
        selector = self.params.context_primitives
        if selector is None or context.context_manager is None:
            return ()
        pool = (*context.context_manager.items(), *(item for _, item in context.context_manager.registry_items()))
        if selector.include_all:
            return tuple(pool)
        selected = [
            item
            for item in pool
            if item.kind in selector.include_kinds or getattr(item, "primitive_id", None) in selector.include_managed_ids
        ]
        return tuple(selected)


__all__ = ["ContextPrimitiveSelectorParams", "VerifierTargetResolver", "VerifierTargetResolverParams"]
