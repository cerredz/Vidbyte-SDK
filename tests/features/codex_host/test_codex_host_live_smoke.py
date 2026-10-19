"""FILE: tests/features/codex_host/test_codex_host_live_smoke.py

PURPOSE: The opt-in smoke test of CodexHost against a real, signed-in codex app-server. It opens a host and calls only reads that never spend: readiness, rate limits, the model list, one page of one thread, and the skill list. A spy on the SDK's writer proves no other request was sent. It never prints account fields.
ROLE IN CODEBASE: Live layer of tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-35, FR-17, EC-45, D-28, X9). The live class runs only when VIDBYTE_CODEX_LIVE_TESTS is "1", openai-codex is installed and codex is on PATH; otherwise it is skipped with a reason. The gate class runs everywhere, CI included.
ARCHITECTURE NOTE: Nothing is mocked on the live path. The spy wraps CodexClient._write_message to record each outgoing request's method and then writes it unchanged, so a request outside ALLOWED_METHODS fails the test after it ran; the method set is what spec section 13 allows, and FORBIDDEN_METHODS names the spending calls AC-35 lists so a regression is reported by name.
COMMON MODIFICATION PATTERNS: A new non-spending read joins ALLOWED_METHODS only when spec section 13 allows it; never add a spending method.
KNOWN EDGE CASES: The real account/read answer carries the account email, so no value read here is printed or put in an assertion message. The gate reads the environment at import time for the skip decorator and again in live_gate, which the gate tests call with a patched environment.
RELATED DOCS: tests/features/codex_host/FEATURE.md; tests/features/codex_host/README.md; docs/spec/codex-host-hardening/spec.md sections 6.2 (AC-35) and 13.
TESTS: VIDBYTE_CODEX_LIVE_TESTS=1 PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_live_smoke.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import unittest
from typing import Any
from unittest import mock

LIVE_ENV = "VIDBYTE_CODEX_LIVE_TESTS"
LIVE_BOUND_SECONDS = 120.0
# Spec section 13: the only requests the live module may cause.
ALLOWED_METHODS = frozenset({"initialize", "account/read", "account/rateLimits/read", "windowsSandbox/readiness", "model/list", "thread/list", "skills/list"})
# AC-35: the spending or state-changing requests it must never send.
FORBIDDEN_METHODS = frozenset({"thread/start", "thread/resume", "turn/start", "review/start", "thread/goal/set", "thread/compact/start", "thread/delete"})


def live_gate() -> tuple[bool, str]:
    """Whether the live test may run, and the skip reason when it may not (D-28, EC-45)."""
    if os.environ.get(LIVE_ENV) != "1":
        return False, f"set {LIVE_ENV}=1 to run the live CodexHost smoke test against a signed-in codex on PATH"
    if importlib.util.find_spec("openai_codex") is None:
        return False, 'the live CodexHost smoke test needs the codex extra: pip install "vidbyte-sdk[codex]"'
    if shutil.which("codex") is None:
        return False, "the live CodexHost smoke test needs the codex CLI on PATH"
    return True, ""


LIVE_ENABLED, LIVE_SKIP_REASON = live_gate()


class CodexLiveGateTests(unittest.TestCase):
    """AC-35 and EC-45: unset, or set without the SDK or the CLI, the live test skips with a reason."""

    def test_the_gate_is_closed_unless_the_variable_is_exactly_1(self) -> None:
        for value in (None, "", "0", "true", "yes"):
            with self.subTest(value=value):
                environment = {key: item for key, item in os.environ.items() if key != LIVE_ENV}
                if value is not None:
                    environment[LIVE_ENV] = value
                with mock.patch.dict(os.environ, environment, clear=True):
                    enabled, reason = live_gate()
                self.assertIs(enabled, False)
                self.assertIn(LIVE_ENV, reason)

    def test_an_enabled_gate_still_skips_without_the_cli_or_the_sdk(self) -> None:
        with mock.patch.dict(os.environ, {LIVE_ENV: "1"}), mock.patch("shutil.which", return_value=None), mock.patch("importlib.util.find_spec", return_value=object()):
            enabled, reason = live_gate()
        self.assertEqual((enabled, "codex CLI on PATH" in reason), (False, True))
        with mock.patch.dict(os.environ, {LIVE_ENV: "1"}), mock.patch("importlib.util.find_spec", return_value=None):
            enabled, reason = live_gate()
        self.assertEqual((enabled, "codex extra" in reason), (False, True))


@unittest.skipUnless(LIVE_ENABLED, LIVE_SKIP_REASON)
class CodexLiveSmokeTests(unittest.IsolatedAsyncioTestCase):
    """AC-35 and FR-17: a real host answers the non-spending reads, and nothing else is sent."""

    async def test_a_real_host_answers_the_non_spending_reads_and_sends_nothing_else(self) -> None:
        from openai_codex.client import CodexClient

        from vidbyte.harnesses.native.codex import CodexHost

        sent: list[str] = []
        write = CodexClient._write_message

        def spy(client: Any, payload: Any) -> None:
            # Record each request's method, never its params, then write it unchanged.
            if isinstance(payload, dict) and "id" in payload and isinstance(payload.get("method"), str):
                sent.append(payload["method"])
            write(client, payload)

        with mock.patch.object(CodexClient, "_write_message", spy):
            async with CodexHost() as host:
                readiness = await asyncio.wait_for(host.check_codex_ready(), LIVE_BOUND_SECONDS)
                await asyncio.wait_for(host.get_codex_rate_limits(), LIVE_BOUND_SECONDS)
                models = await asyncio.wait_for(host.list_codex_models(), LIVE_BOUND_SECONDS)
                page = await asyncio.wait_for(host.list_codex_threads(limit=1), LIVE_BOUND_SECONDS)
                skills = await asyncio.wait_for(host.list_codex_skills(), LIVE_BOUND_SECONDS)
        # Only shapes are checked, so no account value appears in a failure message.
        self.assertTrue(readiness.version, "the live codex app-server reported no version")
        self.assertTrue(models, "the live model list is empty")
        self.assertLessEqual(len(page.threads), 1)
        self.assertIsInstance(skills, tuple)
        self.assertEqual(sorted(set(sent) & FORBIDDEN_METHODS), [])
        self.assertEqual(sorted(set(sent) - ALLOWED_METHODS), [])
        self.assertIn("initialize", sent)


if __name__ == "__main__":
    unittest.main()
