"""Context Protocol Header

Description:
    Defines LeanProofVerifier.
Purpose:
    Compiles a Lean4 proof file and gates on a clean compile with no 'sorry'
    placeholder. The first concrete VerifierKind.FORMAL_PROOF implementation
    this SDK ships.
Architecture:
    - LeanProofVerifier: Verifier subclass taking (params, config); resolves
      which .lean file to check, runs the configured Lean command against
      it, and gates on exit code plus its diagnostic output.
Relations:
    Consumes vidbyte.lib.dataclasses.verifier.LeanProofVerifierConfig.
    Consumed by vidbyte.agents.runtimes.verifier.collection.VerifierCollection.
Similar Files:
    - vidbyte/agents/runtimes/verifier/collection/test_suite.py: the sibling
      "shell out, gate on process output" concrete verifier.
"""

from __future__ import annotations

import asyncio
import subprocess
import time

from vidbyte.agents.runtimes.verifier.verifier import Verifier
from vidbyte.lib.dataclasses.verifier import LeanProofVerifierConfig, VerifierKind, VerifierParams, VerifierTarget, VerifierVerdict
from vidbyte.lib.errors import ConfigurationError

_SORRY_MARKER = "uses `sorry`"  # verified against Lean 4.33.1: `declaration uses \`sorry\`` (backtick-quoted, not straight quotes)
_WARNING_MARKER = "warning:"
_DIAGNOSTICS_CHAR_LIMIT = 1500


class LeanProofVerifier(Verifier):
    """Compiles a Lean4 proof file and gates on a clean compile with no 'sorry' placeholder."""

    def __init__(self, params: VerifierParams, config: LeanProofVerifierConfig) -> None:
        # Validates the verifier is declared as FORMAL_PROOF before storing its Lean-specific config.
        super().__init__(params)
        self._validate_kind()
        self._config = config

    def _validate_kind(self) -> None:
        # A misdeclared kind would report inaccurately to VerifierCollectionParams and downstream feedback.
        if self.params.kind is not VerifierKind.FORMAL_PROOF:
            raise ConfigurationError(f"LeanProofVerifier requires kind=VerifierKind.FORMAL_PROOF, got {self.params.kind!r}.")

    def applicable(self, target: VerifierTarget) -> bool:
        """Skips this verifier when no workspace and no resolvable .lean file are available."""
        return target.workspace_root is not None and self._resolve_file(target) is not None

    def _resolve_file(self, target: VerifierTarget) -> str | None:
        # Uses the explicit file_path override, or the first .lean file the target resolved.
        if self._config.file_path is not None:
            return self._config.file_path
        return next((path for path in target.file_paths if path.endswith(".lean")), None)

    async def check(self, target: VerifierTarget) -> VerifierVerdict:
        """Runs the configured Lean command against the resolved file and gates on its diagnostics."""
        started = time.monotonic()
        file_path = self._resolve_file(target)
        result = await self._run_lean(target.workspace_root, file_path)
        return self._to_verdict(result, duration_seconds=time.monotonic() - started)

    async def _run_lean(self, workspace_root: str, file_path: str) -> subprocess.CompletedProcess[str]:
        # Runs off the event loop; a non-zero exit means a compile error, not a crash, so check=False.
        command = (*self._config.lean_command, file_path)
        return await asyncio.to_thread(subprocess.run, command, cwd=workspace_root, capture_output=True, text=True, check=False)

    def _to_verdict(self, result: subprocess.CompletedProcess[str], *, duration_seconds: float) -> VerifierVerdict:
        # Combines compile success, the sorry gate, and the warnings gate into one pass/fail.
        output = result.stdout + result.stderr
        compiled_clean = result.returncode == 0
        sorry_found = _SORRY_MARKER in output
        has_warning = _WARNING_MARKER in output
        passed = (
            compiled_clean
            and (not sorry_found if self._config.forbid_sorry else True)
            and (not has_warning if self._config.treat_warnings_as_failure else True)
        )
        return VerifierVerdict(
            verifier_name=self.params.name,
            tier=self.params.tier,
            blocking=self.params.blocking,
            passed=passed,
            score=None,
            diagnostics=self._describe(compiled_clean, sorry_found, output),
            duration_seconds=duration_seconds,
        )

    def _describe(self, compiled_clean: bool, sorry_found: bool, output: str) -> str:
        # Truncates raw compiler output so one bad proof cannot flood downstream feedback.
        trimmed = output.strip()[:_DIAGNOSTICS_CHAR_LIMIT]
        if compiled_clean and not sorry_found:
            return "Compiled clean with no 'sorry'." if not trimmed else f"Compiled clean. Diagnostics: {trimmed}"
        reason = "did not compile" if not compiled_clean else "compiled but uses 'sorry'"
        return f"Proof {reason}. Output: {trimmed}"


__all__ = ["LeanProofVerifier"]
