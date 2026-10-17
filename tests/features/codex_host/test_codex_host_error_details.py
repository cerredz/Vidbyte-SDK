"""FILE: tests/features/codex_host/test_codex_host_error_details.py

PURPOSE: Proves the PR #1055 review rule for CodexHost error messages: every CodexAgentError the mapper builds reads like the lib error packets (the function and code, what happened, the thread, the code's likely cause, then its next step) and fills the packet's diagnostic fields with that cause, the failed method, the exception's type name, the host's docs and its tests; a rebuilt error keeps all of them; and a tool states the next step once.
ROLE IN CODEBASE: Error-detail layer of tests/features/codex_host/. The builder, table and tool checks need no host and no openai-codex, so CI runs them; the exception-mapping class needs the optional extra.
ARCHITECTURE NOTE: Expected messages are written out here from the review's format, never built from the production templates. Only the per-code likely causes are read from vidbyte/lib/constants/codex_host.py, because their wording is data the test cannot restate on its own; their keys are checked against the spec's next-step table instead.
COMMON MODIFICATION PATTERNS: A new failure code needs a row in CODEX_HOST_LIKELY_CAUSES and in NEXT_STEPS; a new mapper builder gets one row in BUILDER_ROWS.
KNOWN EDGE CASES: missing_sdk names the Python extra in its cause and next step instead of the CLI's. A CodexAgentError built without the new keywords keeps its old packet, which test_codex_host_records.py pins.
RELATED DOCS: tests/features/codex_host/FEATURE.md; vidbyte/harnesses/native/codex/errors.py; vidbyte/lib/errors/base.py
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_error_details.py
"""

from __future__ import annotations

import unittest
from collections.abc import Callable
from typing import Any

from tests.features.codex_host.codex_host_support import NEXT_STEPS, PIP_INSTALL_FRAGMENT, STDERR_SECRET, changed_error_fields, requires_sdk
from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.lib.constants.codex_host import CODEX_HOST_LIKELY_CAUSES
from vidbyte.lib.enums.codex import CodexHostOperation as Op
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.tools.builtins.codex._base import _CodexHostTool

# The cause every CodexAgentError carried before the review, which a
# mapped error must now replace with its code's own.
GENERIC_CAUSE = "The Codex SDK rejected input, failed a lifecycle operation, or returned an invalid result."
HOST_DOCS = ("vidbyte/harnesses/README.md", "docs/spec/codex-host/spec.md", "https://developers.openai.com/codex/app-server")

# (builder, operation, code, thread id): one row per CodexErrorMapper builder.
BUILDER_ROWS: tuple[tuple[Callable[[], Any], str, str, str], ...] = (
    (lambda: CodexErrorMapper.not_installed("codex"), "open_host", "codex.not_installed", ""),
    (lambda: CodexErrorMapper.version_unsupported("0.1.0"), "open_host", "codex.version_unsupported", ""),
    (lambda: CodexErrorMapper.reviewer_refusal(Op.SPAWN_CODEX_THREAD, "thr-4"), "spawn_codex_thread", "configuration.unsupported_combination", "thr-4"),
    (lambda: CodexErrorMapper.process_exited(Op.WAIT_CODEX_TURN), "wait_codex_turn", "codex.process_exited", ""),
    (lambda: CodexErrorMapper.process_exited(Op.STEER_CODEX_TURN, "thr-5"), "steer_codex_turn", "codex.process_exited", "thr-5"),
)


def expected_tail(code: str) -> str:
    """The two sentences every mapped message ends with: the code's likely cause, then its next step."""
    return f" Likely cause: {CODEX_HOST_LIKELY_CAUSES[code]} Next step: {NEXT_STEPS[code]}"


class CodexErrorMessageTests(unittest.TestCase):
    """CodexErrorMapper messages and packets read like the lib error packets."""

    def test_a_mapped_error_reads_head_summary_thread_cause_and_next_step(self) -> None:
        error = CodexErrorMapper.error(FailureCode.CODEX_SESSION_BUSY, "The thread already has a running turn on this host.", Op.CONTINUE_CODEX_THREAD, "thr-9")
        cause = CODEX_HOST_LIKELY_CAUSES["codex.session_busy"]
        expected = "continue_codex_thread failed with codex.session_busy. The thread already has a running turn on this host. The thread id was thr-9." + expected_tail("codex.session_busy")
        self.assertEqual(error.message, expected)
        self.assertEqual((error.failure_code, error.operation, error.thread_id), ("codex.session_busy", "continue_codex_thread", "thr-9"))
        self.assertEqual(error.likely_causes, (cause,))
        self.assertEqual(error.repair_approaches, (NEXT_STEPS["codex.session_busy"],))
        self.assertEqual(error.related_docs, HOST_DOCS)
        self.assertEqual(error.relevant_tests, ("tests/features/codex_host",))
        self.assertEqual(error.details["likely_causes"], (cause,))
        self.assertEqual(error.details["related_docs"], HOST_DOCS)

    def test_a_threadless_error_has_no_thread_sentence(self) -> None:
        error = CodexErrorMapper.error(FailureCode.CODEX_MODEL_UNKNOWN, "Codex lists no model named gpt-x.", Op.SPAWN_CODEX_THREAD)
        self.assertEqual(error.message, "spawn_codex_thread failed with codex.model_unknown. Codex lists no model named gpt-x." + expected_tail("codex.model_unknown"))
        self.assertNotIn("thread id", error.message)

    def test_every_code_has_its_own_likely_cause(self) -> None:
        # Each code the host reports has exactly one cause, written for
        # that code, never the generic one every error used to carry.
        self.assertEqual(set(CODEX_HOST_LIKELY_CAUSES), set(NEXT_STEPS))
        causes = list(CODEX_HOST_LIKELY_CAUSES.values())
        self.assertEqual(len(set(causes)), len(causes))
        for code, cause in CODEX_HOST_LIKELY_CAUSES.items():
            with self.subTest(code=code):
                self.assertTrue(cause.strip())
                self.assertTrue(cause.endswith("."), cause)
                self.assertNotEqual(cause, GENERIC_CAUSE)

    def test_each_builder_names_its_operation_code_cause_and_next_step(self) -> None:
        for builder, operation, code, thread_id in BUILDER_ROWS:
            with self.subTest(operation=operation, code=code):
                error = builder()
                self.assertTrue(error.message.startswith(f"{operation} failed with {code}. "), error.message)
                self.assertTrue(error.message.endswith(expected_tail(code)), error.message)
                self.assertEqual(f"The thread id was {thread_id}." in error.message, bool(thread_id))
                self.assertEqual(error.likely_causes, (CODEX_HOST_LIKELY_CAUSES[code],))

    def test_missing_sdk_names_the_python_extra_as_cause_and_next_step(self) -> None:
        error = CodexErrorMapper.missing_sdk()
        self.assertTrue(error.message.startswith("open_host failed with codex.not_installed. "), error.message)
        self.assertIn(PIP_INSTALL_FRAGMENT, error.next_step)
        self.assertTrue(error.message.endswith(f"Next step: {error.next_step}"), error.message)
        self.assertIn("openai-codex", error.likely_causes[0])
        self.assertNotEqual(error.likely_causes[0], CODEX_HOST_LIKELY_CAUSES["codex.not_installed"])

    def test_a_sentence_added_later_keeps_every_field(self) -> None:
        original = CodexErrorMapper.error(FailureCode.CODEX_API_ERROR, "Codex did not answer turn/start within 30 seconds.", Op.LAUNCH_CODEX_SUBAGENTS, "thr-2", method="turn/start", error_type="TimeoutError")
        sentence = " 2 turns were started before this failure and were interrupted."
        rebuilt = original.with_sentence(sentence)
        self.assertEqual(rebuilt.message, original.message + sentence)
        self.assertEqual(changed_error_fields(rebuilt, original), {})
        self.assertEqual((rebuilt.method, rebuilt.likely_cause), ("turn/start", original.likely_cause))

    def test_a_tool_states_the_next_step_once(self) -> None:
        # A mapped message already ends with its next step, so the tool
        # does not repeat it; an older message without one still gets
        # it appended.
        error = CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, "This host registered no turn turn-1 on thread thr-1.", Op.WAIT_CODEX_TURN)
        mapped = _CodexHostTool._failure("wait_codex_turn", error.failure_code, error.message, error.next_step)
        self.assertEqual(mapped.output, f"codex.session_not_found: {error.message}")
        self.assertEqual(mapped.output.count("Next step:"), 1)
        plain = _CodexHostTool._failure("wait_codex_turn", "codex.api_error", "Codex refused the call.", NEXT_STEPS["codex.api_error"])
        self.assertEqual(plain.output, f"codex.api_error: Codex refused the call. Next step: {NEXT_STEPS['codex.api_error']}")


@requires_sdk
class CodexExceptionDetailTests(unittest.TestCase):
    """Errors mapped from openai-codex exceptions carry the method and type, never the exception's text."""

    def test_an_rpc_error_quotes_codex_and_names_the_method_and_type(self) -> None:
        from openai_codex import errors as sdk

        error = CodexErrorMapper.from_exception(sdk.JsonRpcError(-32603, "history read failed"), Op.LIST_CODEX_TURNS, "thread/turns/list", dead=False, bound_seconds=30.0, thread_id="thr-3")
        summary = "Codex answered thread/turns/list with JSON-RPC error -32603: 'history read failed'. The thread id was thr-3."
        self.assertEqual(error.message, f"list_codex_turns failed with codex.api_error. {summary}" + expected_tail("codex.api_error"))
        self.assertEqual(error.method, "thread/turns/list")
        self.assertEqual(error.safe_runtime_details, {"operation": "list_codex_turns", "error_type": "JsonRpcError", "method": "thread/turns/list"})

    def test_a_timeout_and_a_local_failure_show_only_the_method_bound_and_type(self) -> None:
        timed_out = CodexErrorMapper.from_exception(TimeoutError(STDERR_SECRET), Op.READ_CODEX_THREAD, "thread/read", dead=False, bound_seconds=30.0)
        self.assertIn("Codex did not answer thread/read within 30 seconds.", timed_out.message)
        self.assertEqual(timed_out.safe_runtime_details["error_type"], "TimeoutError")
        local = CodexErrorMapper.from_exception(RuntimeError(STDERR_SECRET), Op.READ_CODEX_THREAD, "thread/read", dead=False, bound_seconds=30.0)
        self.assertIn("thread/read failed with RuntimeError.", local.message)
        for error in (timed_out, local):
            self.assertNotIn(STDERR_SECRET, error.message)
            self.assertNotIn(STDERR_SECRET, str(error.details))

    def test_a_dead_process_names_the_method_it_died_during(self) -> None:
        from openai_codex import errors as sdk

        error = CodexErrorMapper.from_exception(sdk.TransportClosedError(STDERR_SECRET), Op.STEER_CODEX_TURN, "turn/steer", dead=False, bound_seconds=30.0, thread_id="thr-6")
        self.assertEqual(error.message, "steer_codex_turn failed with codex.process_exited. The Codex app-server exited during turn/steer. The thread id was thr-6." + expected_tail("codex.process_exited"))
        self.assertEqual(error.safe_runtime_details["error_type"], "TransportClosedError")


if __name__ == "__main__":
    unittest.main()
