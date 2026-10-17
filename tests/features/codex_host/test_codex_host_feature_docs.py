"""FILE: tests/features/codex_host/test_codex_host_feature_docs.py

PURPOSE: Proves the docstrings of the new CodexHost methods carry the limits the spec says a developer must read there: how to leave plan mode and who answers plan questions, that a side chat's Vidbyte tools run outside the sandbox and that a goal may continue on the fork, that a revert leaves files alone, that a stream is closed with contextlib.aclosing and needs a running loop, and that a settings change does not re-price a turn already running.
ROLE IN CODEBASE: Documentation layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md FR-33, D-22, NG-12, NG-16, EC-3, EC-6, EC-15, EC-16, EC-17, EC-23, EC-61, T-1). It imports only the package, so CI runs it without openai-codex.
ARCHITECTURE NOTE: The spec fixes what each docstring must say, not its words, so each row checks a few words that no faithful wording can avoid (an identifier the developer has to type, or the one noun the limit is about), case-insensitively. Section 12.3 keeps openai-codex out of the host's import, so reading the docstrings loads no SDK.
COMMON MODIFICATION PATTERNS: When the spec adds a documented limit to a method, add a row with the identifier or noun the limit cannot be stated without.
KNOWN EDGE CASES: inspect.getdoc follows the method resolution order, so a docstring on the mixin method counts, which is where section 8.5 puts the methods.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 3 (NG-12, NG-16), 6.3 and 8.1 (D-22).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_feature_docs.py
"""

from __future__ import annotations

import inspect
import unittest

# (method, words its docstring must hold, the spec item that asks for them)
DOCUMENTED_LIMITS = (
    ("run_codex_plan", ("CodexCollaborationMode", "DEFAULT"), "EC-15: pass CodexCollaborationMode(mode=DEFAULT) to leave plan mode"),
    ("run_codex_plan", ("approval_handler",), "EC-16: plan questions go to the approval_handler"),
    ("start_codex_side_chat", ("tool", "sandbox"), "D-22: the parent's Vidbyte tools stay callable and run outside Codex's sandbox"),
    ("start_codex_side_chat", ("goal",), "EC-61: the fork may carry an active goal"),
    ("revert_codex_thread", ("file",), "NG-16: only the history changes, never local files"),
    ("stream_codex_turn", ("aclosing",), "EC-17: close an early exit with contextlib.aclosing"),
    ("stream_codex_turn", ("loop",), "EC-3: the method needs a running event loop"),
    ("update_codex_turn_settings", ("pric",), "EC-23, NG-12: the turn stays priced as its start model"),
    ("update_codex_thread_settings", ("pric",), "EC-6, NG-12: a running turn keeps its price"),
    # T-1: each developer-only destructive function names what it loses.
    ("revert_codex_thread", ("history",), "T-1: the reverted turns leave the stored history"),
    ("clear_codex_goal", ("goal",), "T-1: the stored goal is gone"),
    ("clean_codex_background_terminals", ("process",), "T-1: the thread's background processes are stopped"),
    ("reset_codex_memories", ("memor",), "T-1: every stored memory is gone"),
)


class CodexFeatureDocstringTests(unittest.TestCase):
    """FR-33: each new method documents the limits the spec names."""

    def test_each_documented_limit_is_in_its_methods_docstring(self) -> None:
        from vidbyte.harnesses.native.codex import CodexHost

        for method, words, reason in DOCUMENTED_LIMITS:
            doc = (inspect.getdoc(getattr(CodexHost, method)) or "").casefold()
            for word in words:
                with self.subTest(method=method, word=word):
                    self.assertIn(word.casefold(), doc, reason)


if __name__ == "__main__":
    unittest.main()
