# Design Doc: Sandbox Environments

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-06
**Last Updated:** 2026-06-06

---

## 1. Overview

This feature adds **sandboxes** to the Vidbyte SDK: isolated, disposable execution
environments where an agent can run the *entire* agentic loop (Architecture B —
"remote brain") or where individual risky tools can execute (Architecture A —
"remote hands"). A sandbox is "a computer you don't care about destroying": the
agent may run arbitrary model-generated commands without touching the host. The SDK
already ships the *contract* for this (`SandboxTransport`, `SandboxRequest`,
`SandboxResult` in `lib/dataclasses/sandbox.py`) and a `Platform` enum
(`LOCAL`, `DOCKER`, `E2B`, `WASM`) but no concrete backend. This work fills that gap:
a pluggable provider layer (`vidbyte/providers/sandbox/`), a thin user-facing facade
(`vidbyte/sandbox/`) exposing `Sandbox.create(...)`, `Sandbox.put(agent, task)`,
`sandbox.exec(cmd)` plus multi-sandbox management, and an Architecture-B runner that
serializes an agent into the box and runs its loop there.

---

## 2. Goals & Non-Goals

### Goals
- A pluggable `SandboxProvider` layer, extensible per platform, with a `Platform`-keyed factory mirroring the existing `ModelProviders` pattern.
- Two fully-working providers: **Local** (subprocess, zero deps, the reference + test backend) and **Docker** (shells out to the `docker` CLI, no Python dependency).
- Lazy-import adapter scaffolds for **E2B, Modal, Daytona, Fly Machines** behind the same interface, raising a clear install/credentials error when their SDK is absent, declared as optional `pyproject` extras.
- A thin facade package `vidbyte/sandbox/` exposing a clean API: `Sandbox.create(...)`, `Sandbox.put(agent, task)`, instance `sandbox.exec/upload/download/destroy`, and a `SandboxManager` to create, list, view, and destroy more than one sandbox.
- **Direct parameter configuration** (no user-facing `SandboxSpec`): users pass `image=`, `repo=`, `branch=`, `commit=`, `seed_local=`, `setup=`, `env=`, `secrets=`, `cpu=`, `mem_mb=`, `timeout_s=`, `network_allow=`, `expose_ports=`, `workdir=`, `ttl_seconds=` directly to `create`/`put`.
- Deterministic provisioning ("settings → ordered exec/upload calls"): clone a GitHub repo, check out a branch/commit, seed a local folder, run setup commands — all before the agent starts, with credentials injected via the secret channel (never interpolated into logged command strings).
- An Architecture-B path: serialize an `Agent` to a manifest, ship it into the box, reconstruct it from the SDK's catalogs, and run the loop in-box via `python -m vidbyte.sandbox.run_agent`, streaming events back to the host.
- A `SandboxFileSystemBackend` so existing filesystem tools (Architecture A) can operate against a sandbox unchanged.
- Wire the feature into `VidbyteSDK` as `sdk.sandboxes` and export `Sandbox`/`SandboxManager` at the package root.

### Non-Goals
- Real isolation guarantees for the **Local** provider. It runs commands in an isolated temp working directory for development/testing/reference only; it is **not** a security boundary. Real isolation requires Docker/E2B/microVM backends.
- Fully wiring the E2B/Modal/Daytona/Fly SDKs (network calls, accounts). These ship as lazy scaffolds in this PR; concrete wiring is a follow-up per provider.
- WASM/Pyodide provider (the `Platform.WASM` value remains reserved; no backend yet).
- Snapshot/fork-based agent trajectory branching. The `Sandbox` protocol declares `snapshot()`, but tree-search over forked sandboxes is out of scope here.
- Replacing the existing simulated `CodeExecutionTool`. Routing it through a sandbox transport is noted as a follow-up, not done here.
- A hosted control plane / cost dashboard for managing sandboxes across processes. `SandboxManager` is in-process only.

---

## 3. Background & Context

The SDK is a harness for building agents (tools, context windows, middleware,
pipelines, multi-agent runtimes). Agents generate and run arbitrary code, which
cannot safely execute on a developer's machine or a production host. The current
`CodeExecutionTool` *simulates* execution with a string blacklist — security theater
that is trivially bypassed and cannot run real workloads. The repo already contains
the seam for real isolation (`SandboxTransport` Protocol + `SandboxRequest`/`Result`)
and a `Platform` enum, but no backend implements them.

The motivating user scenarios:
1. "Put my agent in a sandbox for the full loop" (Architecture B) — fire an agent at a task in a disposable cloud/Docker box and let it edit files, run tests, install packages.
2. "Create a sandbox with my GitHub repo / a branch / a local folder already on it" — deterministic provisioning.
3. "Manage and view more than one sandbox" — a manager over multiple live boxes.

Constraints:
- The package depends only on `pydantic` + `httpx`. Provider SDKs (e2b, modal) must be **optional** and lazy-loaded so the base install stays light and importable.
- Conventions to follow (from Phase 1 audit): "Context Protocol Header" docstrings on every module; frozen, slotted dataclasses for contracts in `lib/dataclasses/`; `Protocol`/ABC backends; vendor adapters under `vidbyte/providers/` with a factory class and a namespace `*Client`; errors extend `VidbyteSdkError(message, *, details=...)`; runners under `lib/runners/`; `unittest.IsolatedAsyncioTestCase` tests; one-line signatures each followed by a 1–2 line comment.

---

## 4. Requirements

### Functional Requirements
1. `Sandbox.create(platform="local", **params)` returns a live `Sandbox` handle whose environment has been provisioned per the passed params.
2. `sandbox.exec(command, *, timeout=...)` runs a command in the box and returns a `SandboxResult` (exit_code, stdout, stderr, timed_out).
3. `sandbox.upload(local_path, remote_path)` / `sandbox.download(remote_path, local_path)` / `sandbox.write_file(remote_path, content)` / `sandbox.read_file(remote_path)` move bytes in/out.
4. Provisioning, run in fixed order before the agent: inject secrets → clone `repo` (+ `branch`/`commit`) → seed `seed_local` folder → run `setup` commands. Each step lowers to `exec`/`upload` calls.
5. Credentials passed via `secrets=` are injected into the box environment and referenced by name (`${VAR}`); the literal value never appears in a command string, log, or trace.
6. `Sandbox.put(agent, task, platform=..., **params)` creates a box, provisions it, ships the agent in, runs the full loop in-box, streams events back, and returns an `AgentResult` plus the live handle. Instance `sandbox.put(agent, task)` runs the agent in an existing box.
7. The agent is reconstructed in-box from a manifest by resolving tool/middleware/runtime **names** against the SDK catalogs/registries; custom code must be importable in the box (documented contract).
8. `SandboxManager` supports `create`, `get(id)`, `list()`, `view(id)` (returns `SandboxInfo`), `destroy(id)`, `destroy_all()`. `Sandbox.list()/get(id)` delegate to a process-default manager.
9. `SandboxProviders.create(platform, config)` resolves the provider for a `Platform`; unknown/unsupported platforms raise `SandboxProviderError`. A `register_provider(platform, cls)` hook allows third-party extension.
10. Local and Docker providers are functional. E2B/Modal/Daytona/Fly providers raise `SandboxProviderError` with an install hint (e.g. `pip install vidbyte-sdk[e2b]`) when their SDK or credentials are missing.
11. `SandboxFileSystemBackend` implements `BaseFileSystemBackend` against a `Sandbox`, so existing filesystem tools operate in-box unchanged.
12. `sandbox.destroy()` tears down the box and is idempotent. `SandboxManager` reaps boxes past `ttl_seconds` on access.

### Non-Functional Requirements
- **Performance:** Local provider command latency dominated by subprocess spawn (~ms). Provisioning is one-time; results may later be snapshotted (out of scope). No added latency to non-sandbox agent paths.
- **Scalability:** `SandboxManager` holds N concurrent handles in-process; concurrency cap configurable (default unbounded, documented).
- **Security:** secrets injected via env channel only; never logged. Local provider explicitly documented as *not* a security boundary. Provisioning commands that reference secrets use `sh -c` with `${VAR}` expansion inside the box.
- **Observability:** every `exec` returns a structured `SandboxResult`; the Architecture-B runner emits JSONL events (one per agent iteration / tool call) consumable by the host. Hooks left for the existing tracing providers.
- **Reliability:** provider errors normalized to the `SandboxError` hierarchy; partial provisioning failure destroys the half-built box and raises `SandboxProvisionError`; `destroy` is idempotent and safe to call after errors.

---

## 5. High-Level Design

The feature is sliced across the repo's existing **layers**, unified by a thin
facade — not bundled into one monolithic package (which would fight the repo's
layer-based structure).

```
                       vidbyte/sandbox/  (THIN FACADE)
        Sandbox.create / Sandbox.put / sandbox.exec / SandboxManager / SandboxClient
                 |                                   |
                 v                                   v
   vidbyte/providers/sandbox/            vidbyte/lib/runners/sandbox.py
   SandboxProviders factory  ----------> SandboxAgentRunner (Architecture B)
   BaseSandboxProvider                      serialize Agent -> AgentManifest
   SandboxProvisioner (lowering)            ship in -> reconstruct -> run loop
   Local / Docker (real)                    stream JSONL events back
   E2B / Modal / Daytona / Fly (lazy)          ^
                 |                              |
                 v                              |  runs in-box
   Sandbox / SandboxProvider Protocols   python -m vidbyte.sandbox.run_agent
   (lib/dataclasses/sandbox.py)          (rebuild Agent from manifest + catalogs)
                 |
                 v
   vidbyte/lib/tools/filesystem/backends/sandbox.py
   SandboxFileSystemBackend  (Architecture A: existing FS tools, remote backend)
```

**End-to-end data flow (`Sandbox.put(agent, task, platform="docker", repo=...)`):**
1. Facade builds an internal `SandboxConfig` from the direct kwargs.
2. `SandboxProviders.create(Platform.DOCKER, config)` boots a box → `Sandbox` handle.
3. `SandboxProvisioner.provision(sandbox, config)` injects secrets, clones repo/branch/commit, seeds local folder, runs setup — in fixed order, via `exec`/`upload`.
4. `SandboxAgentRunner.run(agent, task, sandbox)` serializes the agent to an `AgentManifest`, uploads it, and `exec`s `python -m vidbyte.sandbox.run_agent --manifest ... --task ...`.
5. In-box: `run_agent` loads the manifest, rebuilds the `Agent` by resolving names against `Tools`/registries, runs the loop, emits JSONL events on stdout.
6. Host streams those events, assembles an `AgentResult`, registers the handle with the `SandboxManager`, and returns `(result, sandbox)`.

**Key design decisions:**
- **Direct params, internal config object.** Users never construct a spec; the facade accepts kwargs and bundles them into a private `SandboxConfig` purely to pass to providers cleanly. This honors "pass params directly" at the API surface while keeping the provider interface tidy.
- **Provisioning is shared, not per-provider.** A single `SandboxProvisioner` lowers config → ordered `exec`/`upload` against any `Sandbox` handle, so every provider gets identical, deterministic repo/branch/local-folder/setup behavior for free.
- **Providers are vendor adapters in `providers/sandbox/`**, mirroring `providers/tracing/`. Extensibility via a `Platform`-keyed factory + `register_provider`.
- **Architecture B is a runner** (`lib/runners/sandbox.py`), alongside the other loop-owning runners; Architecture A is a tool **backend** (`filesystem/backends/sandbox.py`). Two seams, two homes.

---

## 6. Detailed Design

### 6.1 Sandbox contracts

**File(s):** `vidbyte/lib/dataclasses/sandbox.py` — **Modified**

#### What it does
Extends the existing sandbox contracts with the configuration object, status/info
value types, the live `Sandbox` handle Protocol, the `SandboxProvider` Protocol, and
the `AgentManifest` used by Architecture B. Existing `SandboxRequest`/`SandboxResult`/
`SandboxTransport` are preserved for back-compat.

#### Interface / API
```python
class SandboxStatus(str, Enum):
    CREATING = "creating"; READY = "ready"; RUNNING = "running"
    STOPPED = "stopped"; DESTROYED = "destroyed"; ERROR = "error"

@dataclass(frozen=True, slots=True)
class SandboxConfig:
    # Internal transport from facade -> provider; users never build this directly.
    platform: Platform = Platform.LOCAL
    image: str = "python:3.12-slim"
    repo: str | None = None
    branch: str | None = None
    commit: str | None = None
    seed_local: str | None = None          # host path to copy in
    workdir: str = "/workspace"
    setup: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    secrets: Mapping[str, str] = field(default_factory=dict)   # name -> value, injected not logged
    cpu: float | None = None
    mem_mb: int | None = None
    disk_mb: int | None = None
    timeout_seconds: float = 60.0
    network_allow: tuple[str, ...] = ()
    expose_ports: tuple[int, ...] = ()
    ttl_seconds: float | None = None
    labels: Mapping[str, str] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class SandboxInfo:
    # Read-only snapshot for list()/view().
    sandbox_id: str; platform: Platform; status: SandboxStatus
    workdir: str; created_at: float
    exposed_urls: Mapping[int, str] = field(default_factory=dict)
    labels: Mapping[str, str] = field(default_factory=dict)

class Sandbox(Protocol):
    sandbox_id: str
    async def exec(self, command: Sequence[str], *, timeout: float | None = None) -> SandboxResult: ...
    async def upload(self, local_path: str, remote_path: str) -> None: ...
    async def download(self, remote_path: str, local_path: str) -> None: ...
    async def write_file(self, remote_path: str, content: str) -> None: ...
    async def read_file(self, remote_path: str) -> str: ...
    async def expose_port(self, port: int) -> str: ...
    async def snapshot(self) -> str: ...
    async def info(self) -> SandboxInfo: ...
    async def destroy(self) -> None: ...

class SandboxProvider(Protocol):
    platform: Platform
    async def create(self, config: SandboxConfig) -> Sandbox: ...

@dataclass(frozen=True, slots=True)
class AgentManifest:
    # Serializable agent config; NAMES code, does not serialize behavior.
    name: str; system_prompt: str; runtime: str
    model: str | None; provider: str | None
    params: Mapping[str, Any]
    tools: tuple[str, ...]
    middleware: tuple[Mapping[str, Any], ...]
    context_window: Mapping[str, Any] | None = None
```

#### Logic / Algorithm
1. Pure data declarations; no behavior. `SandboxConfig` carries all provisioning knobs.
2. `Sandbox`/`SandboxProvider` are `Protocol`s (matches the existing `SandboxTransport` precedent) so providers need not inherit.
3. `AgentManifest` is consumed by the runner (host) and `run_agent` (in-box).

#### Edge Cases & Error Handling
- `secrets` is a `Mapping[str,str]`; the provisioner reads it but no `__repr__` ever prints values (dataclass repr will — so providers must avoid logging the config object directly; documented + enforced by passing only `secrets.keys()` to any log).
- Empty `setup`/`env`/`secrets`/`expose_ports` are valid (no-op provisioning steps).

---

### 6.2 Provider base + provisioning lowering

**File(s):** `vidbyte/providers/sandbox/base.py` — **New**

#### What it does
Defines `BaseSandboxProvider` (shared helpers) and `SandboxProvisioner` — the class
that lowers a `SandboxConfig` into a deterministic, ordered sequence of `exec`/`upload`
calls against a freshly created `Sandbox` handle.

#### Interface / API
```python
class SandboxProvisioner:
    def __init__(self, sandbox: Sandbox, config: SandboxConfig) -> None: ...
    async def provision(self) -> None:
        # Runs all provisioning steps in fixed deterministic order.
        await self._inject_secrets()
        await self._seed_repo()
        await self._seed_local_folder()
        await self._run_setup()
    async def _inject_secrets(self) -> None: ...      # env channel, never logged
    async def _seed_repo(self) -> None: ...           # git clone + branch/commit
    async def _seed_local_folder(self) -> None: ...   # tar host dir -> upload -> extract
    async def _run_setup(self) -> None: ...           # ordered setup commands
```

#### Logic / Algorithm
1. `_inject_secrets`: hand `config.secrets` to the sandbox's env mechanism (provider-specific; the handle exposes a private `_set_env`). No interpolation into commands.
2. `_seed_repo`: if `config.repo`, build `git clone` using `https://x-access-token:${GIT_TOKEN}@host/repo` form run via `sh -c` so the token expands *in-box*; then `git checkout <commit|branch>` if set. Clone target = `config.workdir`.
3. `_seed_local_folder`: if `config.seed_local`, tar the host dir (respect `.gitignore` via `git ls-files` when available, else skip common ignores), `upload` the tarball, `exec` `tar -x` into `workdir`.
4. `_run_setup`: for each command in `config.setup`, `exec(["sh","-c",cmd])`; abort on first non-zero exit, raising `SandboxProvisionError` with the failing command + stderr.

#### Edge Cases & Error Handling
- Missing `GIT_TOKEN`/credentials for a private repo → clone exits non-zero → `SandboxProvisionError` (token value never surfaced).
- `seed_local` path does not exist on host → `SandboxProvisionError` before any box mutation.
- A failing setup command destroys the half-provisioned box (caller's responsibility via try/except in the facade) and re-raises.
- Determinism caveat documented: `branch` moves over time; `commit` is the reproducible pin.

---

### 6.3 Local provider (reference + test backend)

**File(s):** `vidbyte/providers/sandbox/local.py` — **New**

#### What it does
`LocalSandboxProvider` + `LocalSandbox`: runs commands via `asyncio.create_subprocess_exec`
in a dedicated temp working directory. Zero dependencies. The reference implementation
and the backend the test suite runs against. **Not a security boundary** (documented).

#### Interface / API
```python
class LocalSandboxProvider:
    platform = Platform.LOCAL
    async def create(self, config: SandboxConfig) -> LocalSandbox: ...

class LocalSandbox:
    def __init__(self, sandbox_id: str, root: Path, config: SandboxConfig) -> None: ...
    async def exec(self, command, *, timeout=None) -> SandboxResult: ...
    async def upload(self, local_path, remote_path) -> None: ...
    # ... full Sandbox protocol ...
    async def destroy(self) -> None: ...   # shutil.rmtree(root); idempotent
```

#### Logic / Algorithm
1. `create`: make a temp dir (`tempfile.mkdtemp`) as `workdir`, build env = base env + `config.env` + `config.secrets`, construct `LocalSandbox`, run `SandboxProvisioner`, return it.
2. `exec`: spawn subprocess with cwd=root, the merged env, capture stdout/stderr, enforce timeout via `asyncio.wait_for` → on timeout kill and return `SandboxResult(timed_out=True)`.
3. `upload`/`download`/`write_file`/`read_file`: resolve `remote_path` *inside* root (reject `..` escapes), copy/read.
4. `expose_port`: returns `http://127.0.0.1:<port>` (best-effort; no real proxy).
5. `snapshot`: copy root to a sibling temp dir, return its id (degenerate snapshot).
6. `destroy`: `rmtree` root if present; safe to call twice.

#### Edge Cases & Error Handling
- Path escape (`remote_path` containing `..` resolving outside root) → `SandboxExecutionError`.
- Subprocess timeout → killed, `timed_out=True`, no exception.
- `destroy` after `destroy` → no-op (idempotent).
- Documented loudly: provides isolation of *working directory*, not of process/network/host — dev/test only.

---

### 6.4 Docker provider

**File(s):** `vidbyte/providers/sandbox/docker.py` — **New**

#### What it does
`DockerSandboxProvider` + `DockerSandbox`: shells out to the `docker` CLI (no Python
docker dependency). Real OS-level isolation when a Docker daemon is available.

#### Interface / API
```python
class DockerSandboxProvider:
    platform = Platform.DOCKER
    async def create(self, config: SandboxConfig) -> DockerSandbox: ...
class DockerSandbox:
    # exec -> docker exec; upload/download -> docker cp; destroy -> docker rm -f
    ...
```

#### Logic / Algorithm
1. `create`: verify `docker` on PATH (else `SandboxProviderError` with install hint); `docker run -d` the `config.image` with resource flags (`--cpus`, `--memory`), env (`-e`), workdir, optional `--network none` unless `network_allow` set, published `expose_ports`. Capture container id = sandbox_id. Run `SandboxProvisioner`.
2. `exec`: `docker exec <id> sh -c <cmd>` with timeout; map exit code/stdout/stderr to `SandboxResult`.
3. `upload`/`download`: `docker cp`. `write_file`: pipe content via `docker exec ... sh -c 'cat > path'`.
4. `expose_port`: read the published host port via `docker port <id> <port>`.
5. `destroy`: `docker rm -f <id>`; idempotent (ignore "no such container").

#### Edge Cases & Error Handling
- Docker not installed/daemon down → `SandboxProviderError` (clear, actionable).
- Image pull failure → `SandboxProvisionError`.
- Secrets passed as `-e` env vars, never embedded in the `docker run` argv that gets logged (values pulled from config at spawn time; argv logging redacts env values).

---

### 6.5 Lazy provider scaffolds (E2B, Modal, Daytona, Fly)

**File(s):** `vidbyte/providers/sandbox/{e2b,modal,daytona,fly}.py` — **New**

#### What it does
Adapter scaffolds implementing `SandboxProvider`. Each attempts a lazy import of its
vendor SDK inside `create()`; if the import or required credentials are missing, raises
`SandboxProviderError` with an install/setup hint. Structured so concrete wiring is a
focused follow-up that fills in `exec/upload/...`.

#### Interface / API
```python
class E2BSandboxProvider:
    platform = Platform.E2B
    async def create(self, config: SandboxConfig) -> Sandbox:
        # Lazy-imports e2b; raises SandboxProviderError("pip install vidbyte-sdk[e2b]") if absent.
        ...
```

#### Logic / Algorithm
1. `create`: `try: import <sdk>` → on `ImportError` raise `SandboxProviderError(install_hint)`.
2. If SDK present but credentials env var missing → `SandboxProviderError(setup_hint)`.
3. (Follow-up) construct the vendor sandbox, wrap it to satisfy the `Sandbox` protocol, run `SandboxProvisioner`.

#### Edge Cases & Error Handling
- Import error vs missing-credentials error are distinct messages.
- Until wired, `create` never returns a partial handle — it raises, so callers can fall back or surface a clear message.

---

### 6.6 Provider factory + registry

**File(s):** `vidbyte/providers/sandbox/__init__.py` — **New**

#### What it does
`SandboxProviders` — a `Platform`-keyed factory mirroring `ModelProviders`, plus a
`register_provider(platform, cls)` extension hook.

#### Interface / API
```python
class SandboxProviders:
    @staticmethod
    def create_provider(platform: Platform | str) -> SandboxProvider: ...
    @staticmethod
    def register_provider(platform: Platform, provider_cls: type[SandboxProvider]) -> None: ...
    @staticmethod
    async def create(platform: Platform | str, config: SandboxConfig) -> Sandbox: ...
```

#### Logic / Algorithm
1. Internal registry dict maps `Platform → provider class` (Local, Docker, E2B, Modal, Daytona, Fly built in).
2. `create_provider`: normalize string → `Platform`; look up; unknown → `SandboxProviderError`.
3. `create`: resolve provider, call `provider.create(config)`.
4. `register_provider`: allow third parties to add/override a platform (extensibility).

#### Edge Cases & Error Handling
- Unknown platform string → `SandboxProviderError` listing supported platforms.
- Re-registering a platform overrides (documented).

---

### 6.7 SandboxFileSystemBackend (Architecture A)

**File(s):** `vidbyte/lib/tools/filesystem/backends/sandbox.py` — **New**

#### What it does
Implements `BaseFileSystemBackend` against a `Sandbox`, so existing filesystem tools
read/write/list/etc. inside the box without changing the tools.

#### Interface / API
```python
class SandboxFileSystemBackend(BaseFileSystemBackend):
    def __init__(self, sandbox: Sandbox, *, loop=None) -> None: ...
    def read_text(self, path, *, encoding) -> str: ...   # -> sandbox.read_file
    def write_text(self, path, content, *, encoding, create_parents) -> None: ...
    # ... full BaseFileSystemBackend surface mapped to exec/upload/download ...
```

#### Logic / Algorithm
1. The base backend interface is sync; `Sandbox` is async. Bridge by running coroutines on a provided/owned event loop (documented; matches how sync runner wrappers in the repo bridge async).
2. `list_dir` → `exec(["ls","-1A",path])`; `find` → `exec(["sh","-c","find ..."])`; `diff_text` → read then `difflib`; `zip/unzip` → `exec` zip/unzip.

#### Edge Cases & Error Handling
- Command failure → `ToolExecutionError` (matches `LocalFileSystemBackend` error type) with stderr.
- Called from inside a running loop → raise a clear error (cannot block); recommend the async path.

---

### 6.8 SandboxAgentRunner (Architecture B)

**File(s):** `vidbyte/lib/runners/sandbox.py` — **New**

#### What it does
Owns the "run the whole agent loop in the box" flow: serialize agent → manifest, ship
in, launch the in-box entrypoint, stream JSONL events, assemble an `AgentResult`.

#### Interface / API
```python
class SandboxAgentRunner:
    def __init__(self, sandbox: Sandbox) -> None: ...
    async def run(self, agent: BaseAgent, task: str) -> AgentResult:
        # Ships the agent into the box, runs its loop there, returns the result.
        manifest = self._serialize_agent(agent)
        await self._upload_manifest(manifest, task)
        events = await self._launch_and_stream()
        return self._assemble_result(events)
    def _serialize_agent(self, agent: BaseAgent) -> AgentManifest: ...
    async def _upload_manifest(self, manifest, task) -> None: ...
    async def _launch_and_stream(self) -> list[Mapping[str, Any]]: ...
    def _assemble_result(self, events) -> AgentResult: ...
```

#### Logic / Algorithm
1. `_serialize_agent`: read agent name, system prompt, runtime, model/provider, params, tool **names** (from its `Tools`), middleware config, context-window choice → `AgentManifest`.
2. `_upload_manifest`: write `agent.json` + `task.txt` into the box.
3. `_launch_and_stream`: `exec(["python","-m","vidbyte.sandbox.run_agent","--manifest","/workspace/agent.json","--task-file","/workspace/task.txt"])`; parse stdout as JSONL events (one per iteration/tool call/final).
4. `_assemble_result`: fold events into an `AgentResult`.

#### Edge Cases & Error Handling
- Tool name in manifest not resolvable in-box → in-box entrypoint emits an `error` event; runner raises `AgentExecutionError` with the missing name.
- Non-zero exit from the entrypoint with no final event → `AgentExecutionError` including captured stderr.
- Model API key must be present in-box as a secret; if absent, the in-box loop errors and streams it back.

---

### 6.9 In-box entrypoint

**File(s):** `vidbyte/sandbox/run_agent.py` — **New** (run via `python -m vidbyte.sandbox.run_agent`)

#### What it does
The process that runs *inside* the box. Loads the manifest, rebuilds the `Agent` from
the SDK catalogs/registries, runs the loop locally (in-box), emits JSONL events.

#### Interface / API
```python
def main(argv: Sequence[str] | None = None) -> int:
    # CLI entrypoint: parse args, rebuild agent, run loop, stream events, return exit code.
class AgentManifestLoader:
    def rebuild(self, manifest: AgentManifest) -> BaseAgent: ...   # names -> catalog lookups
```

#### Logic / Algorithm
1. Parse `--manifest` / `--task-file`.
2. `AgentManifestLoader.rebuild`: resolve tool names against `Tools`/`ToolRegistry`, middleware against the middleware builtins, runtime against runtime configs, build `BaseAgent`.
3. Run the agent on the task; for each iteration/tool call, print a JSON line to stdout; print a final `result` line.
4. Return 0 on success, non-zero on failure (after emitting an `error` event).

#### Edge Cases & Error Handling
- Unknown tool/middleware/runtime name → emit `error` event, exit non-zero.
- Exceptions during the loop → caught, emitted as `error` event with message, exit non-zero (never crash silently).

---

### 6.10 Facade: `Sandbox` + `SandboxManager` + `SandboxClient`

**File(s):** `vidbyte/sandbox/facade.py`, `vidbyte/sandbox/manager.py`, `vidbyte/sandbox/client.py`, `vidbyte/sandbox/__init__.py` — **New**

#### What it does
The thin, clean user surface. `Sandbox` wraps a provider handle with ergonomic
methods and direct-param creation. `SandboxManager` tracks multiple live sandboxes.
`SandboxClient` is the namespace client mounted at `sdk.sandboxes`.

#### Interface / API
```python
class Sandbox:
    def __init__(self, handle: ProviderSandbox, manager: SandboxManager) -> None: ...
    @classmethod
    async def create(cls, *, platform="local", image="python:3.12-slim", repo=None,
                     branch=None, commit=None, seed_local=None, setup=(), env=None,
                     secrets=None, cpu=None, mem_mb=None, timeout_s=60.0,
                     network_allow=(), expose_ports=(), workdir="/workspace",
                     ttl_seconds=None, labels=None) -> "Sandbox":
        # Build SandboxConfig from direct params, create + provision a box, register it.
        ...
    @classmethod
    async def put(cls, agent, task, *, platform="local", **params) -> tuple[AgentResult, "Sandbox"]:
        # Convenience: create a box (via create) then run the agent's full loop in it.
        ...
    async def exec(self, command, *, timeout=None) -> SandboxResult: ...
    async def upload(self, local_path, remote_path) -> None: ...
    async def run_agent(self, agent, task) -> AgentResult:   # instance-level "put into THIS box"
        ...
    async def destroy(self) -> None: ...
    @classmethod
    def list(cls) -> tuple[SandboxInfo, ...]: ...   # delegate to default manager
    @classmethod
    async def get(cls, sandbox_id) -> "Sandbox": ...

class SandboxManager:
    def __init__(self) -> None: ...
    async def create(self, config: SandboxConfig) -> Sandbox: ...
    def get(self, sandbox_id: str) -> Sandbox: ...
    def list(self) -> tuple[SandboxInfo, ...]: ...
    async def view(self, sandbox_id: str) -> SandboxInfo: ...
    async def destroy(self, sandbox_id: str) -> None: ...
    async def destroy_all(self) -> None: ...

class SandboxClient:
    """Namespace client for sdk.sandboxes."""
```

#### Logic / Algorithm
1. `Sandbox.create`: assemble `SandboxConfig` from kwargs (sync→tuple/dict coercion), delegate to the default `SandboxManager.create`, which calls `SandboxProviders.create` + provisions, wraps in `Sandbox`, registers it, returns it.
2. `Sandbox.put` (classmethod): `create` then `run_agent`; returns `(result, sandbox)`.
3. `Sandbox.run_agent` (instance): construct `SandboxAgentRunner(self._handle).run(agent, task)`.
4. `SandboxManager`: dict `id → Sandbox`; `view`/`list` return `SandboxInfo`; `destroy` removes + tears down; TTL reaping on access.
5. A module-level default manager backs `Sandbox.list/get` for the "manage many" convenience.

#### Edge Cases & Error Handling
- `get`/`view` unknown id → `SandboxNotFoundError`.
- `destroy_all` continues past individual failures, aggregating errors.
- `seed_local`/`secrets`/`env` defaulting `None → empty` to keep frozen-config construction clean.

---

### 6.11 Errors, enum, wiring

**File(s):**
- `vidbyte/lib/errors/base.py` — **Modified**: add `SandboxError(VidbyteSdkError)`, `SandboxProviderError`, `SandboxProvisionError`, `SandboxExecutionError`, `SandboxNotFoundError`.
- `vidbyte/lib/errors/__init__.py` — **Modified**: export them.
- `vidbyte/lib/enums/platform.py` — **Modified**: add `MODAL`, `DAYTONA`, `FLY`.
- `vidbyte/lib/dataclasses/__init__.py` — **Modified**: export `SandboxConfig`, `SandboxStatus`, `SandboxInfo`, `Sandbox`, `SandboxProvider`, `AgentManifest`.
- `vidbyte/client.py` — **Modified**: `self.sandboxes = SandboxClient()`.
- `vidbyte/__init__.py` — **Modified**: export `Sandbox`, `SandboxManager`.
- `vidbyte/tools/security/sandbox.py` — **Modified**: extend the compat shim to also re-export the new `Sandbox`/`SandboxProvider`/`SandboxConfig` names.
- `pyproject.toml` — **Modified**: add `[project.optional-dependencies]` `e2b`, `modal`, `daytona`, `fly`, `all`.

#### Logic / Algorithm
Straightforward additions following existing export/wiring patterns. All new errors
extend `VidbyteSdkError` and accept `details=`.

#### Edge Cases & Error Handling
N/A — declarative wiring.

---

## 7. Data Model Changes

### 7.1 New dataclasses / types (in `lib/dataclasses/sandbox.py`)
**Change type:** New
- `SandboxStatus` (Enum), `SandboxConfig`, `SandboxInfo`, `AgentManifest` (frozen, slotted dataclasses); `Sandbox` and `SandboxProvider` (`Protocol`s).

**Migration strategy:** N/A — additive. Existing `SandboxRequest`/`SandboxResult`/`SandboxTransport` unchanged.

### 7.2 `Platform` enum
**Change type:** Modified — add `MODAL = "modal"`, `DAYTONA = "daytona"`, `FLY = "fly"`. Additive; no removals.

---

## 8. API Changes

N/A (no HTTP endpoints) — this is a library/SDK surface. The public Python API additions are covered in §6.10. Summary of the new public surface:
- `vidbyte.Sandbox` (`create`, `put`, `exec`, `upload`, `download`, `run_agent`, `destroy`, `list`, `get`)
- `vidbyte.SandboxManager`
- `sdk.sandboxes` (`SandboxClient`)
- `vidbyte.providers.sandbox.SandboxProviders` (`create`, `create_provider`, `register_provider`)
- CLI: `python -m vidbyte.sandbox.run_agent` (in-box only)

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/providers/sandbox/__init__.py` | `SandboxProviders` factory + registry |
| CREATE | `vidbyte/providers/sandbox/base.py` | `BaseSandboxProvider`, `SandboxProvisioner` (lowering) |
| CREATE | `vidbyte/providers/sandbox/local.py` | Local subprocess provider (reference + test) |
| CREATE | `vidbyte/providers/sandbox/docker.py` | Docker CLI provider |
| CREATE | `vidbyte/providers/sandbox/e2b.py` | Lazy E2B adapter scaffold |
| CREATE | `vidbyte/providers/sandbox/modal.py` | Lazy Modal adapter scaffold |
| CREATE | `vidbyte/providers/sandbox/daytona.py` | Lazy Daytona adapter scaffold |
| CREATE | `vidbyte/providers/sandbox/fly.py` | Lazy Fly Machines adapter scaffold |
| CREATE | `vidbyte/sandbox/__init__.py` | Thin facade exports |
| CREATE | `vidbyte/sandbox/facade.py` | `Sandbox` user-facing class |
| CREATE | `vidbyte/sandbox/manager.py` | `SandboxManager` (multi-sandbox) |
| CREATE | `vidbyte/sandbox/client.py` | `SandboxClient` namespace client |
| CREATE | `vidbyte/sandbox/run_agent.py` | In-box Architecture-B entrypoint |
| CREATE | `vidbyte/lib/runners/sandbox.py` | `SandboxAgentRunner` (Architecture B) |
| CREATE | `vidbyte/lib/tools/filesystem/backends/sandbox.py` | `SandboxFileSystemBackend` (Architecture A) |
| CREATE | `tests/test_sandbox.py` | Unit tests |
| CREATE | `scripts/test-sandbox-environments.py` | Phase-5 verification script |
| MODIFY | `vidbyte/lib/dataclasses/sandbox.py` | Add config/status/info/protocols/manifest |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export new contracts |
| MODIFY | `vidbyte/lib/enums/platform.py` | Add `MODAL`, `DAYTONA`, `FLY` |
| MODIFY | `vidbyte/lib/errors/base.py` | Add sandbox error hierarchy |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export sandbox errors |
| MODIFY | `vidbyte/client.py` | Mount `sdk.sandboxes` |
| MODIFY | `vidbyte/__init__.py` | Export `Sandbox`, `SandboxManager` |
| MODIFY | `vidbyte/tools/security/sandbox.py` | Extend compat shim re-exports |
| MODIFY | `pyproject.toml` | Optional extras for e2b/modal/daytona/fly |

**Totals:** 17 created, 8 modified, 0 deleted.

---

## 10. Testing Plan

All tests run against the **Local** provider (zero deps, deterministic). Docker tests
are skipped when `docker` is absent.

### Unit Tests
- `SandboxLocalTests` → `it('exec returns stdout and exit 0 for a simple echo')` — happy path baseline.
- `it('exec captures non-zero exit code and stderr')` — [Edge Case]
- `it('exec marks timed_out=True and does not raise when command exceeds timeout')` — [Hidden Failure]
- `it('exec on an empty command sequence raises SandboxExecutionError')` — [Edge Case]
- `it('upload then read_file round-trips identical bytes')` — [Silent Failure] (truncation/encoding)
- `it('write_file with special characters and newlines is read back exactly')` — [Silent Failure]
- `it('remote_path containing .. that escapes workdir raises SandboxExecutionError')` — [Hidden Assumption] (paths are confined)
- `it('destroy is idempotent — second call does not raise')` — [Edge Case]
- `it('exec after destroy raises SandboxExecutionError')` — [Hidden Assumption] (handle still usable)
- `ProvisionerTests` → `it('setup commands run in listed order')` — [Silent Failure] (wrong order)
- `it('a failing setup command raises SandboxProvisionError with the command and stderr')` — [Hidden Failure]
- `it('secret values never appear in the raised provision error message')` — [Silent Failure] (secret leak)
- `it('seed_local with 0 files, 1 file, and N files all land in workdir')` — [Edge Case]
- `it('seed_local pointing at a nonexistent host path raises before mutating the box')` — [Hidden Assumption]
- `it('empty setup/env/secrets/expose_ports provisions a bare box with no error')` — [Edge Case]
- `SandboxProvidersTests` → `it('create_provider("local") returns LocalSandboxProvider')` — happy path.
- `it('create_provider for an unknown platform raises SandboxProviderError listing supported platforms')` — [Edge Case]
- `it('e2b/modal/daytona/fly create() raises SandboxProviderError with an install hint when SDK is absent')` — [Hidden Assumption] (optional dep)
- `it('register_provider adds a custom platform resolvable by create_provider')` — extensibility.
- `SandboxManagerTests` → `it('list() returns 0, 1, and N SandboxInfo entries as boxes are created')` — [Edge Case]
- `it('get()/view() unknown id raises SandboxNotFoundError')` — [Edge Case]
- `it('destroy(id) removes it from list() and tears down the box')` — happy path.
- `it('destroy_all continues past a failing destroy and tears down the rest')` — [Hidden Failure]
- `it('TTL-expired sandbox is reaped on next manager access')` — [Hidden Failure]
- `ManifestTests` → `it('serialize→rebuild yields identical tool names, middleware, runtime, params')` — [Silent Failure] (lossy round-trip)
- `it('rebuild with an unknown tool name emits/raises a clear error naming the tool')` — [Hidden Assumption] (custom code must exist in box)
- `FacadeTests` → `it('Sandbox.create builds config from direct params (no Spec object required)')` — confirms the param-direct API.
- `it('Sandbox.put creates a box and returns (AgentResult, Sandbox)')` — Architecture-B happy path on Local.
- `SandboxFileSystemBackendTests` → `it('write_text then read_text via the backend round-trips through the sandbox')` — [Silent Failure]
- `it('backend command failure surfaces as ToolExecutionError with stderr')` — [Hidden Failure]

### Integration Tests
- **End-to-end Architecture B on Local:** build a trivial `BaseAgent` with one built-in tool, `Sandbox.put(agent, task)`, assert an `AgentResult` comes back and JSONL events were streamed. Mock the model provider HTTP call (no network) so the in-box loop is deterministic. Silent-failure focus: assert the event stream is non-empty and the final result is not an empty/default object masking a crash.
- **Provisioning with a local folder:** seed a temp host dir with known files, create a Local sandbox, assert the files exist in `workdir` via `exec(["ls"])`. Hidden-assumption focus: `.gitignore`'d files are excluded.
- **Secret non-leakage across the integrated flow:** provision with a fake secret, force a setup failure, assert the secret value appears in **no** captured log/trace/error string anywhere in the flow.
- Mock vs real: model provider HTTP mocked; subprocess real (Local); Docker daemon real-or-skipped.

### Manual / QA Test Cases
1. Given Docker installed, when `Sandbox.create(platform="docker", image="python:3.12-slim", setup=["pip install requests"])`, then `exec(["python","-c","import requests"])` exits 0 — [happy + Hidden Assumption: deps installed].
2. Given a private GitHub repo and a `GIT_TOKEN` secret, when `create(repo=..., branch=...)`, then the repo is in `workdir` and the token is absent from the audit/trace output — [Silent Failure: secret leak].
3. Given no Docker daemon, when `create(platform="docker")`, then a clear `SandboxProviderError` is raised (not a stack trace) — [Edge Case].
4. Given `Sandbox.put(agent, task, platform="local")` with an agent referencing a tool not present in-box, then a clear error naming the missing tool — [Hidden Assumption].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `docker` CLI | host-installed | Docker provider isolation | Optional; absence → clear error + skipped tests |
| `e2b` (extra) | `vidbyte-sdk[e2b]` | E2B microVM sandboxes | Optional, lazy; not wired this PR |
| `modal` (extra) | `vidbyte-sdk[modal]` | Modal sandboxes | Optional, lazy; not wired this PR |
| `daytona-sdk` (extra) | `vidbyte-sdk[daytona]` | Daytona sandboxes | Optional, lazy; not wired this PR |
| `fly` API (extra) | `vidbyte-sdk[fly]` | Fly Machines | Optional, lazy; not wired this PR |
| stdlib `asyncio`/`subprocess`/`tempfile`/`tarfile` | 3.11+ | Local provider | None |

No new **base** dependencies (package still installs with only `pydantic` + `httpx`).

---

## 12. Rollout & Deployment

- **Feature flags:** none. Purely additive public surface; nothing changes for existing users until they import `vidbyte.Sandbox`.
- **Breaking changes:** none. `SandboxRequest`/`SandboxResult`/`SandboxTransport` preserved; `Platform` only gains members.
- **Deployment order:** single PR; no service coordination.
- **Rollback:** revert the PR; no data/schema migrations.
- **In-box requirement (Architecture B):** the box image must have `vidbyte` (and any custom user tool packages) installed for `run_agent` to reconstruct the agent. Documented in the facade docstring and design doc; default Docker image guidance: `pip install vidbyte-sdk` in the image or via `setup=`.

---

## 13. Open Questions

- [ ] Event protocol for Architecture B: JSONL on stdout (proposed) vs a structured webhook back to the host. JSONL is simplest and provider-agnostic; webhook scales better for long runs. Proposing JSONL now.
- [ ] Should `SandboxManager` be process-global (a module singleton) or always explicitly constructed? Proposing a module-default manager backing `Sandbox.list/get`, with explicit construction also allowed.
- [ ] Sync bridging in `SandboxFileSystemBackend` (async sandbox behind a sync `BaseFileSystemBackend`): own a private loop vs require an injected one. Proposing injected-or-owned with a clear error when called inside a running loop.
- [ ] How much of `network_allow` can the Docker provider realistically enforce without a custom network/proxy? Proposing `--network none` by default and best-effort published ports; full egress allowlists deferred.

---

## 14. Alternatives Considered

### Alternative 1: One monolithic `vidbyte/sandbox/` package holding everything
- What: contracts + providers + runner + backend all under `vidbyte/sandbox/`.
- Why rejected: the repo organizes by **layer** (providers/, runners/, lib/dataclasses/, tools/backends/), not by feature. A monolith would split vendor adapters, loop-owners, and contracts away from their established homes, creating a parallel structure maintainers must special-case. The thin facade gives the single front door without the inconsistency.

### Alternative 2: User-facing `SandboxSpec` dataclass for configuration
- What: users build `SandboxSpec(...)` and pass it to `create`.
- Why rejected: the user explicitly requested direct params. We keep an *internal* `SandboxConfig` purely as facade→provider transport, so the ergonomics stay param-direct while the provider interface stays clean.

### Alternative 3: Put providers in `vidbyte/lib/providers/sandbox/` (as originally phrased)
- What: a new `lib/providers/` root.
- Why rejected: no `lib/providers/` exists; all vendor adapters live in `vidbyte/providers/` with the `providers/tracing/` subpackage precedent. Confirmed with the user to use `vidbyte/providers/sandbox/`.

### Alternative 4: Architecture A only (rebind tool backends; loop stays on host)
- What: ship only `SandboxFileSystemBackend` + sandboxed code-exec.
- Why rejected: the user's goal is the full loop in the box (Architecture B). We still include the `SandboxFileSystemBackend` for the A use case, but B is the headline.

### Alternative 5: Fully wire E2B/Modal now
- What: real vendor SDK integration in this PR.
- Why rejected: heavy optional deps + unverifiable in this environment (no accounts/Docker guaranteed). Lazy scaffolds keep the package light and the feature extensible; concrete wiring is a focused follow-up per provider.

---

END OF DESIGN DOC
