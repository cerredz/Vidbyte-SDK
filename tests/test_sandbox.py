"""Context Protocol Header

Description:
    Unit tests for the sandbox-environments feature against the Local provider.
Purpose:
    Verifies provider exec/file behavior, deterministic provisioning, the factory,
    multi-sandbox management, manifest reconstruction, and the param-direct facade.
Architecture:
    - LocalSandboxTests / ProvisionerTests / FactoryTests / ManagerTests /
      ManifestTests / FacadeTests: IsolatedAsyncioTestCase suites.
Relations:
    Related to vidbyte.providers.sandbox, vidbyte.sandbox, and
    vidbyte.lib.runners.sandbox.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.sandbox import AgentManifest, SandboxConfig
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import SandboxExecutionError, SandboxNotFoundError, SandboxProviderError, SandboxProvisionError
from vidbyte.lib.registries.tools import ToolRegistry
from vidbyte.providers.sandbox import LocalSandboxProvider, SandboxProviders
from vidbyte.sandbox import Sandbox, SandboxManager
from vidbyte.sandbox.run_agent import AgentManifestLoader
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec


class EchoTool(BaseTool):
    """Trivial custom tool used for manifest reconstruction tests."""

    def spec(self) -> ToolSpec:
        """Return a tool spec named 'echo'."""
        return ToolSpec(name="echo", description="Echo.")

    async def execute(self, call: ToolCall) -> ToolResult:
        """Return a success result."""
        del call
        return ToolResult.success(self.name, "ok")


class LocalSandboxTests(unittest.IsolatedAsyncioTestCase):
    """Verifies LocalSandbox exec, file I/O, and lifecycle behavior."""

    async def test_exec_returns_stdout_and_exit_zero(self) -> None:
        """A simple echo returns its output and a zero exit code."""
        box = await LocalSandboxProvider().create(SandboxConfig())
        result = await box.exec(["sh", "-c", "echo hello"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.strip(), "hello")
        await box.destroy()

    async def test_exec_captures_nonzero_exit(self) -> None:
        """A failing command surfaces its exit code and stderr."""
        box = await LocalSandboxProvider().create(SandboxConfig())
        result = await box.exec(["sh", "-c", "echo bad 1>&2; exit 4"])
        self.assertEqual(result.exit_code, 4)
        self.assertIn("bad", result.stderr)
        await box.destroy()

    async def test_exec_timeout_sets_flag_without_raising(self) -> None:
        """A command exceeding its timeout is flagged, not raised."""
        box = await LocalSandboxProvider().create(SandboxConfig())
        result = await box.exec(["sh", "-c", "sleep 5"], timeout=0.3)
        self.assertTrue(result.timed_out)
        await box.destroy()

    async def test_empty_command_raises(self) -> None:
        """An empty command sequence raises SandboxExecutionError."""
        box = await LocalSandboxProvider().create(SandboxConfig())
        with self.assertRaises(SandboxExecutionError):
            await box.exec([])
        await box.destroy()

    async def test_write_read_round_trip_special_chars(self) -> None:
        """Special characters survive a write/read round trip exactly."""
        box = await LocalSandboxProvider().create(SandboxConfig())
        payload = "weird:\n\t\"q\" 'a' ünïcödé"
        await box.write_file("r.txt", payload)
        self.assertEqual(await box.read_file("r.txt"), payload)
        await box.destroy()

    async def test_path_escape_raises(self) -> None:
        """A traversal path outside the working dir is rejected."""
        box = await LocalSandboxProvider().create(SandboxConfig())
        with self.assertRaises(SandboxExecutionError):
            await box.read_file("../escape.txt")
        await box.destroy()

    async def test_destroy_is_idempotent_and_blocks_exec(self) -> None:
        """Destroy is safe to repeat and a destroyed box rejects exec."""
        box = await LocalSandboxProvider().create(SandboxConfig())
        await box.destroy()
        await box.destroy()
        with self.assertRaises(SandboxExecutionError):
            await box.exec(["sh", "-c", "echo x"])


class ProvisionerTests(unittest.IsolatedAsyncioTestCase):
    """Verifies deterministic provisioning behavior."""

    async def test_setup_runs_in_order(self) -> None:
        """Setup commands execute in their listed order."""
        box = await LocalSandboxProvider().create(SandboxConfig(setup=("echo one > log.txt", "echo two >> log.txt")))
        self.assertEqual((await box.read_file("log.txt")).splitlines(), ["one", "two"])
        await box.destroy()

    async def test_failing_setup_raises_provision_error(self) -> None:
        """A failing setup command raises SandboxProvisionError."""
        with self.assertRaises(SandboxProvisionError):
            await LocalSandboxProvider().create(SandboxConfig(setup=("exit 9",)))

    async def test_secret_value_not_leaked_in_error(self) -> None:
        """A secret value never appears in a provision error's details."""
        try:
            await LocalSandboxProvider().create(SandboxConfig(secrets={"GIT_TOKEN": "supersecret"}, setup=("echo $GIT_TOKEN; exit 1",)))
            self.fail("expected SandboxProvisionError")
        except SandboxProvisionError as exc:
            self.assertNotIn("supersecret", str(exc.details))

    async def test_seed_local_lands_files(self) -> None:
        """A seeded host folder's files appear in the box workdir."""
        source = Path(tempfile.mkdtemp(prefix="seed-"))
        (source / "x.txt").write_text("data", encoding="utf-8")
        box = await LocalSandboxProvider().create(SandboxConfig(seed_local=str(source)))
        self.assertEqual((await box.read_file("x.txt")), "data")
        await box.destroy()

    async def test_seed_local_missing_path_raises(self) -> None:
        """Seeding a nonexistent host path raises before mutating the box."""
        missing = str(Path(tempfile.gettempdir()) / "missing-seed-xyz-123")
        with self.assertRaises(SandboxProvisionError):
            await LocalSandboxProvider().create(SandboxConfig(seed_local=missing))


class FactoryTests(unittest.IsolatedAsyncioTestCase):
    """Verifies provider factory resolution and extension."""

    def test_resolves_local_provider(self) -> None:
        """The local platform resolves to LocalSandboxProvider."""
        self.assertIsInstance(SandboxProviders.create_provider("local"), LocalSandboxProvider)

    def test_unknown_platform_raises(self) -> None:
        """An unknown platform string raises SandboxProviderError."""
        with self.assertRaises(SandboxProviderError):
            SandboxProviders.create_provider("nope")

    async def test_lazy_providers_raise_without_sdk(self) -> None:
        """Vendor providers raise a clear error when their SDK is absent."""
        for platform in ("e2b", "modal", "daytona", "fly"):
            with self.assertRaises(SandboxProviderError):
                await SandboxProviders.create_provider(platform).create(SandboxConfig(platform=Platform(platform)))

    def test_register_provider_extends_registry(self) -> None:
        """A registered provider becomes resolvable by platform."""
        SandboxProviders.register_provider(Platform.WASM, LocalSandboxProvider)
        self.assertIsInstance(SandboxProviders.create_provider(Platform.WASM), LocalSandboxProvider)


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    """Verifies multi-sandbox tracking and teardown."""

    async def test_list_grows_and_shrinks(self) -> None:
        """list() reflects creates and destroys."""
        manager = SandboxManager()
        self.assertEqual(manager.list(), ())
        handle = await manager.create(SandboxConfig())
        self.assertEqual(len(manager.list()), 1)
        await manager.destroy(handle.sandbox_id)
        self.assertEqual(manager.list(), ())

    async def test_unknown_id_raises(self) -> None:
        """Viewing an unknown id raises SandboxNotFoundError."""
        manager = SandboxManager()
        with self.assertRaises(SandboxNotFoundError):
            await manager.view("missing")

    async def test_ttl_expired_is_reaped(self) -> None:
        """A box past its ttl is reaped on the next access."""
        manager = SandboxManager()
        handle = await manager.create(SandboxConfig(ttl_seconds=0.0))
        await manager.reap_expired()
        self.assertTrue(all(record.sandbox_id != handle.sandbox_id for record in manager.list()))


class ManifestTests(unittest.IsolatedAsyncioTestCase):
    """Verifies agent manifest serialization and reconstruction."""

    def test_round_trip_preserves_tool_names(self) -> None:
        """Rebuilding from a manifest preserves the tool names and identity."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        manifest = AgentManifest(name="rebuilt", system_prompt="p", runtime="linear", tools=("echo",))
        rebuilt = AgentManifestLoader(registry).rebuild(manifest)
        self.assertEqual(tuple(rebuilt.tools.names()), ("echo",))
        self.assertEqual(rebuilt.name, "rebuilt")

    def test_unknown_tool_name_raises(self) -> None:
        """An unresolvable tool name raises a clear error naming the tool."""
        manifest = AgentManifest(name="x", system_prompt="p", runtime="linear", tools=("ghost",))
        with self.assertRaises(ValueError) as ctx:
            AgentManifestLoader(ToolRegistry()).rebuild(manifest)
        self.assertIn("ghost", str(ctx.exception))


class FacadeTests(unittest.IsolatedAsyncioTestCase):
    """Verifies the param-direct facade and Architecture-B dry run."""

    async def test_create_from_direct_params(self) -> None:
        """Sandbox.create builds a box from direct params without a spec object."""
        manager = SandboxManager()
        box = await Sandbox.create(platform="local", setup=["echo built > b.txt"], manager=manager)
        self.assertEqual((await box.read_file("b.txt")).strip(), "built")
        await box.destroy()

    async def test_put_runs_agent_dry_run(self) -> None:
        """Sandbox.put ships an agent into a box and returns its result."""
        manager = SandboxManager()
        agent = BaseAgent(name="demo", system_prompt="You are demo.", tools=())
        result, box = await Sandbox.put(agent, "do a thing", platform="local", dry_run=True, python_executable=sys.executable, manager=manager)
        self.assertEqual(result.strategy_name, "sandbox")
        self.assertEqual([event.get("event") for event in result.metadata.get("events", [])], ["ready", "result"])
        await box.destroy()


if __name__ == "__main__":
    unittest.main()
