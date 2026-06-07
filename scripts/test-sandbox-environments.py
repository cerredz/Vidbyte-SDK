"""Context Protocol Header

Description:
    Standalone verification script for the sandbox-environments feature.
Purpose:
    Runs every Section 10 test case against the Local provider and prints a
    PASS/FAIL line per case plus a final summary, exiting non-zero on any failure.
Architecture:
    - SandboxVerification: Async + sync checks grouped by component.
Relations:
    Verifies vidbyte.sandbox, vidbyte.providers.sandbox, vidbyte.lib.runners.sandbox,
    and vidbyte.lib.tools.filesystem.backends.sandbox.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.sandbox import AgentManifest, SandboxConfig
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.errors import (
    SandboxExecutionError,
    SandboxNotFoundError,
    SandboxProviderError,
    SandboxProvisionError,
    ToolExecutionError,
)
from vidbyte.lib.registries.tools import ToolRegistry
from vidbyte.providers.sandbox import LocalSandboxProvider, SandboxProviders
from vidbyte.providers.sandbox.local import LocalSandbox
from vidbyte.sandbox import Sandbox, SandboxManager
from vidbyte.sandbox.run_agent import AgentManifestLoader
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec

PASSED = 0
FAILED = 0


def record(name: str, ok: bool, detail: str = "") -> None:
    # Print a PASS/FAIL line and update the running totals.
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"PASS  {name}")
    else:
        FAILED += 1
        print(f"FAIL  {name}  {detail}")


async def expect_raises(name: str, exc: type[Exception], coro) -> None:
    # Assert that awaiting a coroutine raises the expected exception type.
    try:
        await coro
        record(name, False, "no exception raised")
    except exc:
        record(name, True)
    except Exception as other:  # noqa: BLE001
        record(name, False, f"raised {type(other).__name__}")


class EchoTool(BaseTool):
    """Minimal custom tool used to verify manifest reconstruction."""

    def spec(self) -> ToolSpec:
        # Return a trivial tool spec named 'echo'.
        return ToolSpec(name="echo", description="Echo.")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the input unchanged.
        return ToolResult.success(self.name, "ok")


async def run_local_provider_checks() -> None:
    # Exercise LocalSandbox exec/file/lifecycle behaviors.
    sbx = await LocalSandboxProvider().create(SandboxConfig())
    echo = await sbx.exec(["sh", "-c", "echo hello"])
    record("exec returns stdout and exit 0 [happy]", echo.exit_code == 0 and echo.stdout.strip() == "hello")
    fail = await sbx.exec(["sh", "-c", "echo oops 1>&2; exit 3"])
    record("exec captures non-zero exit and stderr [Edge]", fail.exit_code == 3 and "oops" in fail.stderr)
    slow = await sbx.exec(["sh", "-c", "sleep 5"], timeout=0.3)
    record("exec marks timed_out and does not raise [Hidden Failure]", slow.timed_out is True)
    await expect_raises("exec empty command raises [Edge]", SandboxExecutionError, sbx.exec([]))
    await sbx.write_file("round.txt", "weird:\n\t\"quotes\" 'and' ünïcödé")
    back = await sbx.read_file("round.txt")
    record("write_file/read_file round-trips special chars [Silent]", back == "weird:\n\t\"quotes\" 'and' ünïcödé")
    await expect_raises("path escape via .. raises [Hidden Assumption]", SandboxExecutionError, sbx.read_file("../escape.txt"))
    await sbx.destroy()
    await sbx.destroy()
    record("destroy is idempotent [Edge]", True)
    await expect_raises("exec after destroy raises [Hidden Assumption]", SandboxExecutionError, sbx.exec(["sh", "-c", "echo x"]))


async def run_provisioner_checks() -> None:
    # Exercise deterministic provisioning: setup order, failures, secrets, seeding.
    ordered = await LocalSandboxProvider().create(SandboxConfig(setup=("echo one > log.txt", "echo two >> log.txt")))
    log = await ordered.read_file("log.txt")
    record("setup commands run in listed order [Silent]", log.splitlines() == ["one", "two"])
    await ordered.destroy()
    await expect_raises("failing setup raises SandboxProvisionError [Hidden Failure]", SandboxProvisionError, LocalSandboxProvider().create(SandboxConfig(setup=("exit 7",))))
    try:
        await LocalSandboxProvider().create(SandboxConfig(secrets={"GIT_TOKEN": "supersecret"}, setup=("echo $GIT_TOKEN; exit 1",)))
        record("secret value absent from provision error [Silent]", False, "no error")
    except SandboxProvisionError as exc:
        record("secret value absent from provision error [Silent]", "supersecret" not in str(exc.details))
    await run_seed_checks()
    bare = await LocalSandboxProvider().create(SandboxConfig())
    record("empty setup/env/secrets provisions bare box [Edge]", (await bare.exec(["sh", "-c", "echo ok"])).stdout.strip() == "ok")
    await bare.destroy()


async def run_seed_checks() -> None:
    # Seed 0, 1, and N files from a host directory into the box.
    for count in (0, 1, 3):
        source = Path(tempfile.mkdtemp(prefix="seed-src-"))
        for index in range(count):
            (source / f"file{index}.txt").write_text(f"content {index}", encoding="utf-8")
        box = await LocalSandboxProvider().create(SandboxConfig(seed_local=str(source)))
        listing = await box.exec(["sh", "-c", "ls -1 | grep -c file || true"])
        seeded = int(listing.stdout.strip() or 0)
        record(f"seed_local with {count} file(s) lands them [Edge]", seeded == count)
        await box.destroy()
    await expect_raises("seed_local nonexistent path raises [Hidden Assumption]", SandboxProvisionError, LocalSandboxProvider().create(SandboxConfig(seed_local=str(Path(tempfile.gettempdir()) / "definitely-missing-xyz"))))


async def run_factory_checks() -> None:
    # Exercise the provider factory and registry extension hook.
    record("create_provider('local') returns LocalSandboxProvider", isinstance(SandboxProviders.create_provider("local"), LocalSandboxProvider))
    try:
        SandboxProviders.create_provider("nope")
        record("unknown platform raises SandboxProviderError [Edge]", False)
    except SandboxProviderError:
        record("unknown platform raises SandboxProviderError [Edge]", True)
    for platform in ("e2b", "modal", "daytona", "fly"):
        await expect_raises(f"{platform} create raises without SDK/creds [Hidden Assumption]", SandboxProviderError, SandboxProviders.create_provider(platform).create(SandboxConfig(platform=Platform(platform))))
    SandboxProviders.register_provider(Platform.WASM, LocalSandboxProvider)
    record("register_provider adds a resolvable platform", isinstance(SandboxProviders.create_provider(Platform.WASM), LocalSandboxProvider))


async def run_manager_checks() -> None:
    # Exercise multi-sandbox tracking, view, destroy, and TTL reaping.
    manager = SandboxManager()
    record("list() is empty initially [Edge]", manager.list() == ())
    handle = await manager.create(SandboxConfig())
    record("list() has 1 after create [Edge]", len(manager.list()) == 1)
    await manager.create(SandboxConfig())
    record("list() has N after more creates [Edge]", len(manager.list()) == 2)
    await expect_raises("view unknown id raises [Edge]", SandboxNotFoundError, manager.view("missing"))
    info = await manager.view(handle.sandbox_id)
    record("view returns SandboxInfo for known id", info.sandbox_id == handle.sandbox_id)
    await manager.destroy(handle.sandbox_id)
    record("destroy removes from list", all(rec.sandbox_id != handle.sandbox_id for rec in manager.list()))
    await manager.destroy_all()
    record("destroy_all empties the manager", manager.list() == ())
    ttl_manager = SandboxManager()
    expiring = await ttl_manager.create(SandboxConfig(ttl_seconds=0.0))
    await asyncio.sleep(0.05)
    await ttl_manager.reap_expired()
    record("TTL-expired sandbox is reaped on access [Hidden Failure]", all(rec.sandbox_id != expiring.sandbox_id for rec in ttl_manager.list()))


async def run_manifest_checks() -> None:
    # Exercise manifest serialize->rebuild fidelity and unknown-name handling.
    registry = ToolRegistry()
    registry.register(EchoTool())
    agent = BaseAgent(name="rebuilt", system_prompt="prompt", tools=(EchoTool(),))
    manifest = AgentManifest(name=agent.name, system_prompt=agent.system_prompt, runtime="linear", tools=tuple(agent.tools.names()))
    rebuilt = AgentManifestLoader(registry).rebuild(manifest)
    record("serialize->rebuild preserves tool names [Silent]", tuple(rebuilt.tools.names()) == manifest.tools and rebuilt.name == "rebuilt")
    bogus = AgentManifest(name="x", system_prompt="p", runtime="linear", tools=("does_not_exist",))
    try:
        AgentManifestLoader(ToolRegistry()).rebuild(bogus)
        record("rebuild unknown tool name raises clearly [Hidden Assumption]", False)
    except ValueError as exc:
        record("rebuild unknown tool name raises clearly [Hidden Assumption]", "does_not_exist" in str(exc))


async def run_facade_checks() -> None:
    # Exercise the param-direct facade and Architecture-B dry run.
    manager = SandboxManager()
    box = await Sandbox.create(platform="local", setup=["echo built > b.txt"], manager=manager)
    built = await box.read_file("b.txt")
    record("Sandbox.create builds from direct params (no spec) [API]", built.strip() == "built")
    await box.destroy()
    agent = BaseAgent(name="demo", system_prompt="You are demo.", tools=())
    result, ran_box = await Sandbox.put(agent, "do a thing", platform="local", dry_run=True, python_executable=sys.executable, manager=manager)
    record("Sandbox.put returns (AgentResult, Sandbox) [Arch B]", result.strategy_name == "sandbox" and ran_box.sandbox_id is not None)
    record("Arch B dry-run streamed ready+result events [Arch B]", [event.get("event") for event in result.metadata.get("events", [])] == ["ready", "result"])
    await ran_box.destroy()


def run_backend_checks() -> None:
    # Exercise the sync SandboxFileSystemBackend over a local box (no running loop).
    from vidbyte.lib.tools.filesystem.backends.sandbox import SandboxFileSystemBackend

    box = asyncio.run(LocalSandboxProvider().create(SandboxConfig()))
    backend = SandboxFileSystemBackend(box)
    backend.write_text(Path("note.txt"), "backend-roundtrip", encoding="utf-8", create_parents=True)
    value = backend.read_text(Path("note.txt"), encoding="utf-8")
    record("SandboxFileSystemBackend write/read round-trips [Silent]", value == "backend-roundtrip")
    try:
        backend.list_dir(Path("nope-missing-dir"))
        record("backend surfaces command failure as ToolExecutionError [Hidden Failure]", False)
    except ToolExecutionError:
        record("backend surfaces command failure as ToolExecutionError [Hidden Failure]", True)
    asyncio.run(box.destroy())


async def amain() -> None:
    # Run every async check group in sequence.
    await run_local_provider_checks()
    await run_provisioner_checks()
    await run_factory_checks()
    await run_manager_checks()
    await run_manifest_checks()
    await run_facade_checks()


def main() -> int:
    # Run all checks, print a summary, and return a process exit code.
    asyncio.run(amain())
    run_backend_checks()
    total = PASSED + FAILED
    print(f"\n{PASSED}/{total} tests passed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
