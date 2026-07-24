"""Context Protocol Header

Description:
    Hardening tests for McpStdioTransport concurrent demux, timeouts, stderr
    bounds, restricted env, process exit fan-out, and idempotent shutdown.
Purpose:
    Proves the transport contracts in docs/design/harden-mcp-stdio-transport.md
    without live third-party MCP servers.
Architecture:
    - Local Python child scripts over stdio act as deterministic MCP peers.
    - IsolatedAsyncioTestCase scenarios cover concurrent, hang, crash, malformed,
      notification, env, and close paths.
Relations:
    - vidbyte/tools/mcp/transport.py
    - docs/design/harden-mcp-stdio-transport.md
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
import unittest

from vidbyte.lib.errors import McpProtocolError
from vidbyte.tools.mcp.transport import McpStdioTransport, build_child_env


def _python_child(source: str) -> list[str]:
    """Build a command that runs an inline Python stdio MCP peer."""
    return [sys.executable, "-u", "-c", textwrap.dedent(source).strip()]


class McpStdioTransportHardeningTests(unittest.IsolatedAsyncioTestCase):
    """Covers demux, timeouts, crashes, malformed frames, env, and shutdown."""

    async def test_happy_path_request(self) -> None:
        """A single request receives the matching result object."""
        command = _python_child(
            """
            import json, sys
            for line in sys.stdin:
                msg = json.loads(line)
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"echo": msg["method"]},
                }) + "\\n")
                sys.stdout.flush()
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        try:
            result = await transport.request("initialize", {})
            self.assertEqual(result["echo"], "initialize")
        finally:
            await transport.close()

    async def test_concurrent_out_of_order_responses(self) -> None:
        """Concurrent callers receive results demultiplexed by response id."""
        command = _python_child(
            """
            import json, sys, time
            pending = []
            # Read two requests, reply second first with a short delay pattern.
            for _ in range(2):
                pending.append(json.loads(sys.stdin.readline()))
            # Reply in reverse order so demux is required.
            for msg in reversed(pending):
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"method": msg["method"], "id": msg["id"]},
                }) + "\\n")
                sys.stdout.flush()
            # Keep process alive until stdin closes / terminate.
            for line in sys.stdin:
                pass
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        try:
            first, second = await asyncio.gather(
                transport.request("alpha"),
                transport.request("beta"),
            )
            methods = {first["method"], second["method"]}
            self.assertEqual(methods, {"alpha", "beta"})
            self.assertEqual(first["method"], "alpha")
            self.assertEqual(second["method"], "beta")
        finally:
            await transport.close()

    async def test_request_timeout_on_hang(self) -> None:
        """A hung child surfaces a per-request timeout error."""
        command = _python_child(
            """
            import sys, time
            # Read one line then hang without replying.
            sys.stdin.readline()
            while True:
                time.sleep(60)
            """
        )
        transport = McpStdioTransport(command, request_timeout=0.3)
        try:
            with self.assertRaises(McpProtocolError) as ctx:
                await transport.request("tools/call", {"name": "x"})
            self.assertIn("timed out", str(ctx.exception).lower())
            self.assertEqual(ctx.exception.details.get("reason"), "timeout")
        finally:
            await transport.close()

    async def test_process_crash_fails_pending(self) -> None:
        """Child exit fails waiters that have not yet received a response."""
        command = _python_child(
            """
            import json, sys
            # Answer the first request, then exit without answering further.
            line = sys.stdin.readline()
            msg = json.loads(line)
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"ok": True},
            }) + "\\n")
            sys.stdout.flush()
            # Drain one more request then exit so a pending waiter fails.
            sys.stdin.readline()
            raise SystemExit(1)
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        try:
            ok = await transport.request("first")
            self.assertTrue(ok["ok"])
            with self.assertRaises(McpProtocolError) as ctx:
                await transport.request("second")
            self.assertIn(
                ctx.exception.details.get("reason"),
                {"process_exited", "closed", "stdin_write_failed"},
            )
        finally:
            await transport.close()

    async def test_malformed_then_valid_response(self) -> None:
        """Garbage lines are discarded; a later valid response still delivers."""
        command = _python_child(
            """
            import json, sys
            msg = json.loads(sys.stdin.readline())
            sys.stdout.write("not-json-at-all\\n")
            sys.stdout.flush()
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"ok": True},
            }) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                pass
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        try:
            result = await transport.request("tools/list")
            self.assertTrue(result["ok"])
        finally:
            await transport.close()

    async def test_notification_does_not_complete_waiter(self) -> None:
        """A notification (method, no id) does not complete a pending request."""
        command = _python_child(
            """
            import json, sys
            msg = json.loads(sys.stdin.readline())
            # Emit a notification first.
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": {"level": "info"},
            }) + "\\n")
            sys.stdout.flush()
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"done": True},
            }) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                pass
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        try:
            result = await transport.request("ping")
            self.assertTrue(result["done"])
        finally:
            await transport.close()

    async def test_unknown_and_duplicate_ids_are_ignored(self) -> None:
        """Unknown and duplicate response ids do not corrupt other waiters."""
        command = _python_child(
            """
            import json, sys
            msg = json.loads(sys.stdin.readline())
            # Unknown id.
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": 99999,
                "result": {"ghost": True},
            }) + "\\n")
            sys.stdout.flush()
            # Valid response.
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"ok": True},
            }) + "\\n")
            sys.stdout.flush()
            # Duplicate of the same id (should be ignored).
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"ok": False},
            }) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                pass
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        try:
            result = await transport.request("tools/list")
            self.assertTrue(result["ok"])
        finally:
            await transport.close()

    async def test_stderr_flood_is_bounded(self) -> None:
        """Stderr larger than the bound is truncated and does not hang the pipe."""
        command = _python_child(
            """
            import json, sys
            sys.stderr.write("x" * 200000)
            sys.stderr.flush()
            msg = json.loads(sys.stdin.readline())
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"ok": True},
            }) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                pass
            """
        )
        transport = McpStdioTransport(
            command,
            request_timeout=5.0,
            stderr_max_bytes=1024,
        )
        try:
            result = await transport.request("tools/list")
            self.assertTrue(result["ok"])
            # Allow the stderr reader a brief moment to consume the flood.
            for _ in range(50):
                if len(transport.stderr_snapshot()) >= 1024:
                    break
                await asyncio.sleep(0.02)
            snapshot = transport.stderr_snapshot()
            self.assertLessEqual(len(snapshot.encode("utf-8")), 1024)
            self.assertGreater(len(snapshot), 0)
        finally:
            await transport.close()

    async def test_close_is_idempotent_and_blocks_new_requests(self) -> None:
        """Double close is safe; request after close raises."""
        command = _python_child(
            """
            import json, sys
            for line in sys.stdin:
                msg = json.loads(line)
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"ok": True},
                }) + "\\n")
                sys.stdout.flush()
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        await transport.request("initialize")
        await transport.close()
        await transport.close()
        self.assertTrue(transport.closed)
        with self.assertRaises(McpProtocolError) as ctx:
            await transport.request("again")
        self.assertEqual(ctx.exception.details.get("reason"), "closed")

    async def test_close_fails_in_flight_request(self) -> None:
        """Closing while a request is pending fails that waiter."""
        command = _python_child(
            """
            import sys, time
            sys.stdin.readline()
            # Hang until killed.
            while True:
                time.sleep(60)
            """
        )
        transport = McpStdioTransport(command, request_timeout=30.0)
        task = asyncio.create_task(transport.request("hang"))
        await asyncio.sleep(0.1)
        await transport.close()
        with self.assertRaises(McpProtocolError) as ctx:
            await task
        self.assertIn(ctx.exception.details.get("reason"), {"closed", "process_exited"})

    async def test_restricted_env_excludes_parent_marker(self) -> None:
        """Non-allowlisted parent env vars are not inherited; env= overlays are."""
        marker = "VIDBYTE_MCP_TEST_MARKER_SHOULD_NOT_LEAK"
        os.environ[marker] = "leaked-value"
        try:
            command = _python_child(
                f"""
                import json, os, sys
                msg = json.loads(sys.stdin.readline())
                sys.stdout.write(json.dumps({{
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {{
                        "marker": os.environ.get({marker!r}),
                        "custom": os.environ.get("VIDBYTE_MCP_CUSTOM"),
                    }},
                }}) + "\\n")
                sys.stdout.flush()
                for line in sys.stdin:
                    pass
                """
            )
            transport = McpStdioTransport(
                command,
                env={"VIDBYTE_MCP_CUSTOM": "from-caller"},
                request_timeout=5.0,
            )
            try:
                result = await transport.request("env-check")
                self.assertIsNone(result["marker"])
                self.assertEqual(result["custom"], "from-caller")
            finally:
                await transport.close()
        finally:
            os.environ.pop(marker, None)

    async def test_cancelled_waiter_does_not_break_transport(self) -> None:
        """Cancelling one waiter leaves the transport usable for later calls."""
        command = _python_child(
            """
            import json, sys
            first = json.loads(sys.stdin.readline())
            # Ignore first; answer second.
            second = json.loads(sys.stdin.readline())
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": second["id"],
                "result": {"ok": True},
            }) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                pass
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        try:
            hanging = asyncio.create_task(transport.request("first"))
            await asyncio.sleep(0.05)
            hanging.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await hanging
            result = await transport.request("second")
            self.assertTrue(result["ok"])
        finally:
            await transport.close()

    async def test_remote_jsonrpc_error(self) -> None:
        """JSON-RPC error objects surface as McpProtocolError with details."""
        command = _python_child(
            """
            import json, sys
            msg = json.loads(sys.stdin.readline())
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32601, "message": "Method not found"},
            }) + "\\n")
            sys.stdout.flush()
            for line in sys.stdin:
                pass
            """
        )
        transport = McpStdioTransport(command, request_timeout=5.0)
        try:
            with self.assertRaises(McpProtocolError) as ctx:
                await transport.request("missing")
            self.assertIn("error", ctx.exception.details)
        finally:
            await transport.close()

    def test_build_child_env_allowlist(self) -> None:
        """build_child_env only keeps allowlisted keys plus overlays."""
        marker = "VIDBYTE_MCP_UNIT_ENV_MARKER"
        os.environ[marker] = "nope"
        try:
            child = build_child_env({"CUSTOM": "yes"})
            self.assertNotIn(marker, child)
            self.assertEqual(child["CUSTOM"], "yes")
            if sys.platform == "win32":
                self.assertIn("PATH", child)
            else:
                self.assertIn("PATH", child)
        finally:
            os.environ.pop(marker, None)

    def test_empty_command_rejected(self) -> None:
        """Empty command sequences raise ValueError at construction."""
        with self.assertRaises(ValueError):
            McpStdioTransport([])


if __name__ == "__main__":
    unittest.main()
