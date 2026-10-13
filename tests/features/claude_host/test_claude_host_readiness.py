"""FILE: tests/features/claude_host/test_claude_host_readiness.py

PURPOSE: Proves the readiness side of the host: with the claude extra missing every star function fails with claude.sdk_unavailable and readiness reports it, the initialize probe sends no prompt and closes before it returns, the version and auth-mode checks stop a turn before its first prompt, models keep only known effort levels, the CLI lookup prefers a native binary and never returns a batch script, and start failures point to check_claude_ready.
ROLE IN CODEBASE: Readiness layer of tests/features/claude_host/ (spec AC-2, AC-22, AC-34, AC-38, AC-39, A-7, D-5, D-6, EC-1 to EC-6, EC-57, INV-2, INV-10, INV-11). Exercises vidbyte/harnesses/native/claude/{sdk,probe,host}.py.
ARCHITECTURE NOTE: The missing-extra tests run the real ClaudeSdkLoader.load with claude_agent_sdk blocked in sys.modules, so they need every feature module imported before the block (mock.patch.dict drops modules first imported inside it). The lookup tests call ClaudeProbe.locate_cli directly with a temporary home folder and shutil.which patched where the probe module looks it up, so both rule sets run on any OS.
COMMON MODIFICATION PATTERNS: When CLAUDE_MIN_CLI_VERSION moves, update the version_ok table at its boundary. When the SDK changes its CLI lookup, update the locate_cli cases with the new order.
WHAT NOT TO DO IN THIS FILE: 1. Do not let the lookup tests read the real home folder or PATH; pass `home` and patch which. 2. Do not install or import claude_agent_sdk. 3. Do not import feature symbols at module level.
KNOWN EDGE CASES: The POSIX lookup list has one absolute entry, /usr/local/bin/claude, which the temporary home does not move; the windows=False cases expect it only when that file really exists on the machine. On Windows that entry resolves under the current drive.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.2, 8.1 (D-5, D-6), 12.3 rows 4 and 9, 13 and appendix A-7.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_readiness.py
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    DEFAULT_PROMPT,
    ERROR_MARKER,
    FAKE_CLI_PATH,
    FAKE_CLI_VERSION,
    HANG_GUARD_SECONDS,
    START_FAILURE_NEXT_STEP,
    WHICH_TARGET,
    ClaudeHostCase,
    CLIConnectionError,
    CLINotFoundError,
    ProcessError,
    api_key_account,
    eventually,
    initialize_response,
    passed_options,
    settle,
    star_calls,
)

# Every module INV-1 names, plus the feature modules a star call may touch, imported before claude_agent_sdk is blocked.
PRE_IMPORTED_MODULES = (
    "vidbyte",
    "vidbyte.tools.builtins",
    "vidbyte.tools.toolsets",
    "vidbyte.tools.toolsets.claude",
    "vidbyte.tools.builtins.claude",
    "vidbyte.harnesses.native",
    "vidbyte.harnesses.native.claude",
    "vidbyte.harnesses.native.claude.host",
    "vidbyte.harnesses.native.claude.sdk",
    "vidbyte.harnesses.native.claude.options",
    "vidbyte.harnesses.native.claude.failures",
    "vidbyte.harnesses.native.claude.session",
    "vidbyte.harnesses.native.claude.history",
    "vidbyte.harnesses.native.claude.probe",
    "vidbyte.harnesses.native.claude.tool_server",
    "vidbyte.lib.dataclasses.claude",
    "vidbyte.lib.dataclasses.claude_host",
    "vidbyte.lib.enums.claude",
    "vidbyte.lib.constants.claude",
    "vidbyte.lib.errors",
)

NOT_SIGNED_IN_ACCOUNT = {"apiProvider": "firstParty", "tokenSource": "none", "apiKeySource": "none"}


class ReadinessCase(ClaudeHostCase):
    """Adds a helper that returns the one probe client a readiness or models call constructed."""

    def probe_client(self) -> Any:
        self.assertEqual(len(self.fake.clients), 1, "expected exactly one probe client")
        return self.fake.clients[0]

    def assert_probe_sent_nothing(self, client: Any) -> None:
        self.assertEqual(client.queries, [])
        self.assertNotIn("query", client.calls)
        self.assertEqual(client.disconnect_calls, 1)
        self.assertEqual(self.fake.connected_now, 0)


class MissingExtraTests(ClaudeHostCase):
    """AC-2, EC-1 and INV-1: with claude_agent_sdk missing, every star function fails with claude.sdk_unavailable."""

    patch_sdk = False

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        # Import every feature module first: patch.dict restores sys.modules by clearing it, which drops new entries.
        for name in PRE_IMPORTED_MODULES:
            importlib.import_module(name)
        self.enterContext(mock.patch.dict(sys.modules, {"claude_agent_sdk": None}))

    def test_the_loader_raises_sdk_unavailable_from_the_import_error(self) -> None:
        from vidbyte.harnesses.native.claude.sdk import ClaudeSdkLoader
        from vidbyte.lib.enums.failure import FailureCode
        from vidbyte.lib.errors import ClaudeOperationError

        with self.assertRaises(ClaudeOperationError) as caught:
            ClaudeSdkLoader.load()
        error = caught.exception
        self.assertEqual(error.failure_code, FailureCode.CLAUDE_SDK_UNAVAILABLE.value)
        self.assertEqual(error.operation, "load_sdk")
        self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.sdk_unavailable"])
        self.assertTrue(error.reason)
        self.assertIsInstance(error.__cause__, ImportError)

    async def test_every_star_function_reports_sdk_unavailable(self) -> None:
        from vidbyte.lib.dataclasses.claude_host import ClaudeSessionHandle
        from vidbyte.lib.enums.failure import FailureCode

        host = await self.open_host()
        never_issued = ClaudeSessionHandle(handle_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()))
        for name, call in star_calls(host, never_issued):
            with self.subTest(function=name):
                if name == "check_claude_ready":
                    readiness = await asyncio.wait_for(call(), HANG_GUARD_SECONDS)
                    self.assertEqual(readiness.failure.code, FailureCode.CLAUDE_SDK_UNAVAILABLE)
                    self.assertEqual(readiness.failure.next_step, CLAUDE_NEXT_STEPS["claude.sdk_unavailable"])
                else:
                    error = await self.raises(call(), FailureCode.CLAUDE_SDK_UNAVAILABLE.value)
                    self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.sdk_unavailable"])
        self.assertEqual(self.fake.clients, [])


class ReadyProbeTests(ReadinessCase):
    """FR-2, NFR-2, D-5 and INV-8: one initialize probe with only cli_path, no prompt, closed before the call returns."""

    async def test_a_ready_cli_reports_path_version_and_login(self) -> None:
        host = await self.open_host()
        readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
        self.assertEqual(Path(readiness.cli_path), Path(FAKE_CLI_PATH))
        self.assertEqual((readiness.cli_version, readiness.signed_in, readiness.failure), (FAKE_CLI_VERSION, True, None))
        client = self.probe_client()
        self.assertEqual(list(passed_options(client.options)), ["cli_path"])
        self.assertEqual(Path(client.options.cli_path), Path(FAKE_CLI_PATH))
        self.assert_probe_sent_nothing(client)

    async def test_the_probe_returns_only_after_its_close_finishes(self) -> None:
        self.fake.disconnect_gate = asyncio.Event()
        host = await self.open_host()
        probe = asyncio.create_task(host.check_claude_ready())
        await eventually(lambda: bool(self.fake.clients) and self.fake.clients[0].disconnect_calls == 1, "the probe started its close")
        await settle()
        self.assertFalse(probe.done(), "readiness returned before the probe's close finished")
        self.fake.disconnect_gate.set()
        readiness = await asyncio.wait_for(probe, HANG_GUARD_SECONDS)
        self.assertIsNone(readiness.failure)
        self.assertTrue(self.fake.clients[0].disconnect_finished)

    async def test_a_cancelled_probe_finishes_its_close_then_re_raises(self) -> None:
        self.fake.disconnect_gate = asyncio.Event()
        host = await self.open_host()
        probe = asyncio.create_task(host.check_claude_ready())
        await eventually(lambda: bool(self.fake.clients) and self.fake.clients[0].disconnect_calls == 1, "the probe started its close")
        probe.cancel()
        await settle()
        client = self.fake.clients[0]
        self.assertFalse(probe.done(), "the cancellation cut the probe's close short")
        self.assertFalse(client.disconnect_cancelled)
        self.fake.disconnect_gate.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(probe, HANG_GUARD_SECONDS)
        self.assertTrue(client.disconnect_finished)
        self.assertFalse(client.disconnect_cancelled)
        self.assertEqual(client.disconnect_calls, 1)


class VersionAndAuthModeTests(ReadinessCase):
    """AC-22, D-6, EC-3, EC-5, EC-6 and INV-11: the checks after connect stop a turn before its first prompt."""

    async def test_an_old_or_unknown_cli_version_is_unsupported(self) -> None:
        for label, version in (("2.1.200", "2.1.200"), ("absent", None)):
            with self.subTest(version=label):
                self.fake.server_info = initialize_response(version=version)
                host = await self.open_host()
                readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
                self.assertEqual(readiness.failure.code.value, "claude.version_unsupported")
                self.assertEqual(readiness.failure.next_step, CLAUDE_NEXT_STEPS["claude.version_unsupported"])
                self.assertEqual(readiness.cli_version, version or "")
                handle = await self.spawn(host, f"Prompt on CLI {label}.")
                result = await self.finished(host, handle)
                self.assertEqual(result.status.value, "failed")
                self.assertEqual(result.failure.code.value, "claude.version_unsupported")
                self.assertEqual(result.failure.next_step, CLAUDE_NEXT_STEPS["claude.version_unsupported"])
                client = await self.client_for(handle)
                self.assertEqual(client.queries, [])
                self.assertEqual(client.disconnect_calls, 1)

    async def test_betas_or_bare_fail_without_an_api_key_login(self) -> None:
        from vidbyte.lib.enums.claude import ClaudeBeta

        host = await self.open_host()
        readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
        self.assertIsNone(readiness.failure)
        self.assertTrue(readiness.signed_in)
        for label, fields in (("betas", {"betas": (ClaudeBeta.CONTEXT_1M,)}), ("bare", {"bare": True})):
            with self.subTest(field=label):
                handle = await self.spawn(host, f"Prompt with {label}.", **fields)
                result = await self.finished(host, handle)
                self.assertEqual(result.status.value, "failed")
                self.assertEqual(result.failure.code.value, "claude.auth_mode_unsupported")
                self.assertEqual(result.failure.next_step, CLAUDE_NEXT_STEPS["claude.auth_mode_unsupported"])
                client = await self.client_for(handle)
                self.assertEqual(client.queries, [])
                self.assertEqual(client.disconnect_calls, 1)

    async def test_betas_and_bare_run_with_an_api_key_login(self) -> None:
        from vidbyte.lib.enums.claude import ClaudeBeta

        self.fake.server_info = initialize_response(account=api_key_account())
        host = await self.open_host()
        for label, fields in (("betas", {"betas": (ClaudeBeta.CONTEXT_1M,)}), ("bare", {"bare": True})):
            with self.subTest(field=label):
                handle = await self.spawn(host, f"Prompt with {label}.", **fields)
                result = await self.finished(host, handle)
                self.assertEqual(result.status.value, "completed")
                client = await self.client_for(handle)
                self.assertEqual(client.queries, [f"Prompt with {label}."])

    async def test_an_account_with_no_credential_source_is_not_signed_in(self) -> None:
        self.fake.server_info = initialize_response(account=NOT_SIGNED_IN_ACCOUNT)
        host = await self.open_host()
        readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
        self.assertFalse(readiness.signed_in)
        self.assertEqual(readiness.failure.code.value, "claude.not_signed_in")
        self.assertEqual(readiness.failure.next_step, CLAUDE_NEXT_STEPS["claude.not_signed_in"])
        self.assert_probe_sent_nothing(self.probe_client())

    async def test_a_third_party_provider_counts_as_signed_in(self) -> None:
        self.fake.server_info = initialize_response(account={"apiProvider": "bedrock"})
        host = await self.open_host()
        readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
        self.assertTrue(readiness.signed_in)
        self.assertIsNone(readiness.failure)


class ModelTests(ReadinessCase):
    """AC-34 and FR-3: models come from initialize, unknown effort levels are skipped, and the probe sends no prompt."""

    async def test_models_keep_known_effort_levels_and_skip_unknown_ones(self) -> None:
        from vidbyte.lib.dataclasses.claude_host import ClaudeModelInfo
        from vidbyte.lib.enums.claude import ClaudeEffort

        self.fake.server_info = initialize_response(
            models=[
                {
                    "value": "default",
                    "displayName": "Default (recommended)",
                    "description": "Opus with 1M context",
                    "resolvedModel": "claude-opus-4-7",
                    "supportsEffort": True,
                    "supportedEffortLevels": ["low", "high", "xhigh", "max"],
                    "supportsAdaptiveThinking": True,
                    "supportsFastMode": True,
                    "supportsAutoMode": False,
                },
                {"value": "sonnet", "displayName": "Sonnet", "description": "Everyday tasks", "supportsEffort": True, "supportedEffortLevels": ["medium", "ultra"]},
            ]
        )
        host = await self.open_host()
        models = await asyncio.wait_for(host.list_claude_models(), HANG_GUARD_SECONDS)
        expected = (
            ClaudeModelInfo(
                value="default",
                display_name="Default (recommended)",
                description="Opus with 1M context",
                resolved_model="claude-opus-4-7",
                supports_effort=True,
                supported_effort_levels=(ClaudeEffort.LOW, ClaudeEffort.HIGH, ClaudeEffort.XHIGH, ClaudeEffort.MAX),
                supports_adaptive_thinking=True,
                supports_fast_mode=True,
                supports_auto_mode=False,
            ),
            ClaudeModelInfo(
                value="sonnet",
                display_name="Sonnet",
                description="Everyday tasks",
                resolved_model="",
                supports_effort=True,
                supported_effort_levels=(ClaudeEffort.MEDIUM,),
                supports_adaptive_thinking=None,
                supports_fast_mode=None,
                supports_auto_mode=None,
            ),
        )
        self.assertEqual(models, expected)
        self.assert_probe_sent_nothing(self.probe_client())

    async def test_models_raise_the_readiness_codes(self) -> None:
        cases = (
            ("old CLI", initialize_response(version="2.1.200"), "claude.version_unsupported"),
            ("not signed in", initialize_response(account=NOT_SIGNED_IN_ACCOUNT), "claude.not_signed_in"),
        )
        for label, info, code in cases:
            with self.subTest(case=label):
                self.fake.server_info = info
                host = await self.open_host()
                error = await self.raises(host.list_claude_models(), code)
                self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS[code])
                self.assertEqual(self.fake.clients[-1].queries, [])
                self.assertEqual(self.fake.clients[-1].disconnect_calls, 1)


class StartFailureTests(ReadinessCase):
    """AC-39, EC-4 and EC-44: a probe whose connect fails reports the start-failure next step, and a missing binary reports not_installed."""

    async def test_readiness_reports_a_start_failure_with_the_start_next_step(self) -> None:
        cases = (
            ("ProcessError", lambda: ProcessError(f"Command failed {ERROR_MARKER}", exit_code=1, stderr=f"error: unknown option {ERROR_MARKER}")),
            ("CLIConnectionError", lambda: CLIConnectionError(f"Failed to start Claude Code: {ERROR_MARKER}")),
        )
        for label, factory in cases:
            with self.subTest(exception=label):
                self.fake.connect_error = factory
                host = await self.open_host()
                readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
                self.assertEqual(readiness.failure.code.value, "claude.process_exited")
                self.assertEqual(readiness.failure.next_step, START_FAILURE_NEXT_STEP)
                self.assertIn(label, readiness.failure.reason)
                self.assertNotIn(ERROR_MARKER, readiness.failure.reason)
                client = self.fake.clients[-1]
                self.assertEqual(client.queries, [])
                self.assertEqual(client.disconnect_calls, 1)

    async def test_readiness_reports_a_missing_binary_as_not_installed(self) -> None:
        self.fake.connect_error = lambda: CLINotFoundError("Claude Code not found", cli_path=FAKE_CLI_PATH)
        host = await self.open_host()
        readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
        self.assertEqual(readiness.failure.code.value, "claude.not_installed")
        self.assertEqual(readiness.failure.next_step, CLAUDE_NEXT_STEPS["claude.not_installed"])
        self.assertEqual(self.probe_client().disconnect_calls, 1)


class HostWithoutCliTests(ReadinessCase):
    """AC-38's last sentence, EC-2 and INV-10: entry resolves the CLI once, and an empty result is reported before any process starts."""

    async def test_a_host_that_found_no_cli_reports_not_installed(self) -> None:
        from vidbyte.harnesses.native.claude.probe import ClaudeProbe

        with mock.patch.object(ClaudeProbe, "locate_cli", return_value="") as locate:
            host = await self.open_host(cli_path="")
        self.assertEqual(locate.call_count, 1)
        args, kwargs = locate.call_args
        self.assertEqual(args[0] if args else kwargs["cli_path"], "")
        self.assertEqual(kwargs["windows"], sys.platform == "win32")
        self.assertEqual(Path(kwargs["home"]), Path.home())
        readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
        self.assertEqual(readiness.cli_path, "")
        self.assertEqual(readiness.failure.code.value, "claude.not_installed")
        self.assertEqual(readiness.failure.next_step, CLAUDE_NEXT_STEPS["claude.not_installed"])
        await self.raises(host.list_claude_models(), "claude.not_installed")
        await self.raises(self.spawn(host, DEFAULT_PROMPT), "claude.not_installed")
        self.assertEqual(self.fake.clients, [])

    async def test_entry_keeps_a_given_cli_path(self) -> None:
        host = await self.open_host(cli_path=FAKE_CLI_PATH)
        readiness = await asyncio.wait_for(host.check_claude_ready(), HANG_GUARD_SECONDS)
        self.assertEqual(Path(readiness.cli_path), Path(FAKE_CLI_PATH))


class LocateCliTests(unittest.TestCase):
    """AC-38, D-5 and EC-57: ClaudeProbe.locate_cli prefers a native binary, never returns a batch script, and keeps a given path."""

    def setUp(self) -> None:
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def touch(self, *parts: str) -> Path:
        path = self.home.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def locate(self, cli_path: str, *, windows: bool, hits: dict[str, str]) -> str:
        from vidbyte.harnesses.native.claude.probe import ClaudeProbe

        with mock.patch(WHICH_TARGET, side_effect=lambda name, *args, **kwargs: hits.get(name)):
            return ClaudeProbe.locate_cli(cli_path, windows=windows, home=self.home)

    def test_windows_prefers_a_native_binary_over_the_npm_shim(self) -> None:
        # (a) which("claude") finds the shim and which("claude.exe") finds the native binary.
        found = self.locate("", windows=True, hits={"claude": "C:/npm/claude.cmd", "claude.exe": "C:/native/claude.exe"})
        self.assertEqual(Path(found), Path("C:/native/claude.exe"))

    def test_windows_falls_back_to_the_home_install(self) -> None:
        # (b) which finds nothing and the native installer's binary sits in ~/.local/bin.
        installed = self.touch(".local", "bin", "claude.exe")
        self.assertEqual(Path(self.locate("", windows=True, hits={})), installed)

    def test_windows_never_returns_a_batch_script(self) -> None:
        # (c) only the npm shim exists.
        self.assertEqual(self.locate("", windows=True, hits={"claude": "C:/npm/claude.cmd"}), "")
        # (d) a given path naming a batch script, in any case and with trailing dots or spaces.
        for given in ("C:/tools/CLAUDE.CMD", "C:/tools/claude.bat", "C:/tools/claude.cmd. ", "C:/tools/claude.Bat.."):
            with self.subTest(cli_path=given):
                self.assertEqual(self.locate(given, windows=True, hits={"claude.exe": "C:/native/claude.exe"}), "")

    def test_windows_accepts_a_native_which_hit_in_any_case(self) -> None:
        for hit in ("C:/bin/claude.EXE", "C:/bin/claude.com"):
            with self.subTest(hit=hit):
                self.assertEqual(Path(self.locate("", windows=True, hits={"claude": hit})), Path(hit))

    def test_a_given_path_comes_back_unchanged(self) -> None:
        for windows in (True, False):
            for given in ("C:/tools/claude.exe", "C:/tools/claude"):
                with self.subTest(windows=windows, cli_path=given):
                    self.assertEqual(self.locate(given, windows=windows, hits={"claude": "C:/other/claude.exe"}), given)
        # Batch screening is a Windows rule; elsewhere the given path is kept as is.
        self.assertEqual(self.locate("/opt/tools/claude.cmd", windows=False, hits={}), "/opt/tools/claude.cmd")

    def test_posix_uses_which_then_the_sdk_locations(self) -> None:
        self.assertEqual(self.locate("", windows=False, hits={"claude": "/opt/bin/claude"}), "/opt/bin/claude")
        # The one absolute entry, /usr/local/bin/claude, comes before ~/.local/bin/claude in the SDK's order.
        absolute = self.home / "/usr/local/bin/claude"
        self.assertEqual(self.locate("", windows=False, hits={}), str(absolute) if absolute.is_file() else "")
        installed = self.touch(".local", "bin", "claude")
        found = self.locate("", windows=False, hits={})
        self.assertEqual(Path(found), absolute if absolute.is_file() else installed)


class SignInAndVersionRuleTests(unittest.TestCase):
    """A-7 and D-6: the sign-in rule and the numeric minimum-version comparison, as exhaustive tables."""

    def test_signed_in_follows_a7(self) -> None:
        from vidbyte.harnesses.native.claude.probe import ClaudeProbe

        cases = (
            ({}, False),
            ({"apiProvider": "firstParty"}, False),
            (NOT_SIGNED_IN_ACCOUNT, False),
            ({"tokenSource": None, "apiKeySource": None}, False),
            ({"tokenSource": "claude.ai"}, True),
            ({"apiKeySource": "ANTHROPIC_API_KEY"}, True),
            ({"tokenSource": "none", "apiKeySource": "apiKeyHelper"}, True),
            ({"apiProvider": "bedrock"}, True),
            ({"apiProvider": "vertex", "tokenSource": "none", "apiKeySource": "none"}, True),
        )
        for account, expected in cases:
            with self.subTest(account=account):
                self.assertIs(ClaudeProbe.signed_in(account), expected)

    def test_version_ok_compares_dotted_numbers(self) -> None:
        from vidbyte.harnesses.native.claude.probe import ClaudeProbe

        cases = (
            ("2.1.296", True),
            ("2.1.297", True),
            ("2.1.1000", True),
            ("2.2.0", True),
            ("3.0.0", True),
            ("2.1.295", False),
            ("2.1.29", False),
            ("2.0.999", False),
            ("1.9.999", False),
            ("", False),
            ("not-a-version", False),
        )
        for text, expected in cases:
            with self.subTest(version=text):
                self.assertIs(ClaudeProbe.version_ok(text), expected)


if __name__ == "__main__":
    unittest.main()
