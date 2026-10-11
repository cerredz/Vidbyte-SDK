# MCP Studio Server: Windows Stdin, Built-in Prompts, Ping, Tool Schemas

## Summary

Four small, confirmed bugs keep `vidbyte-mcp-server` from working with real MCP hosts:

1. **Windows stdin.** `_connect_stdin` attaches `sys.stdin.buffer` with
   `loop.connect_read_pipe`. The Windows `ProactorEventLoop` cannot register an anonymous
   pipe with IOCP, so the first read fails ("Fatal read error on pipe transport",
   `WinError 6`) and no request is answered. MCP hosts launch stdio servers through exactly
   such a pipe. Fix: on Windows, read lines in a worker thread.
2. **Built-in prompts never exposed.** `__init__` reads `Prompts()._data`, which no longer
   exists; the `AttributeError` is swallowed, so `studio.prompts.list` returns `{}` and the
   SDK's prompts are missing from `studio.prompts.get` and `prompts/list`. Fix: build both
   maps from the public `Prompts().all()`, with caller `prompt_content` winning per key.
3. **No `ping`.** The MCP base protocol requires an empty `{}` result for `ping`; the server
   returned `-32601 Method not found`. Fix: add a `PingHandler`.
4. **Studio tools advertise no arguments.** Every studio `ToolSpec` declared
   `parameters=()`, so `tools/list` showed an empty `inputSchema` while `execute` required
   keys such as `agent_name` and `prompt`. Fix: declare the keys each `execute` already reads.

## Flow chart

```mermaid
flowchart TD
    A[run] --> B[_connect_stdin]
    B -->|sys.platform == win32| C[_ThreadLineReader: asyncio.to_thread stdin.readline]
    B -->|other platforms| D[StreamReader via connect_read_pipe]
    C --> E[_read_input: reader.readline]
    D --> E
    E -->|b''| F[_EOF: loop ends]
    E -->|blank / bad JSON| G[_SKIP]
    E -->|request dict| H[_dispatch]
    H -->|ping| I[PingHandler: result {}]
    H -->|tools/list| J[studio tool specs with declared parameters]
    H -->|prompts/* or studio.prompts.*| K[built-in prompts + caller prompt_content]
```

## Usage example

```python
import asyncio
from vidbyte.mcp_server import McpStudioServer

# Launched by an MCP host with stdin as a pipe; now works on Windows too.
server = McpStudioServer(prompt_content={"my_prompt": "Custom text"})
asyncio.run(server.run())

# Host -> {"jsonrpc":"2.0","id":1,"method":"ping"}
# Server <- {"jsonrpc":"2.0","id":1,"result":{}}
# tools/list now advertises studio.agents.run with required ["agent_name", "prompt"].
```

## How it works

- `core.py`: a private `_ThreadLineReader` whose `async readline()` is
  `await asyncio.to_thread(stream.readline)`; `_connect_stdin` returns it on `win32`,
  otherwise the existing `StreamReader`. `_read_input` is unchanged, so EOF (`b""`) and
  skip semantics are identical. `_write_response` writes synchronously to
  `sys.stdout.buffer` (no pipe transport), so it is unaffected.
- `core.py`: prompts map = `{key.value: text for key, text in Prompts().all().items()}`,
  then `update(prompt_content)`; family `"strategy"` lists the built-in keys.
- `server/handlers/ping.py`: `PingHandler` returns `mcp_result_response(id, {})`;
  registered as `"ping"` in `_handler_map`.
- `handlers.py`: `ToolParameter` declarations — `studio.agents.list` (`filter_name`,
  optional), `studio.agents.run` (`agent_name`, `prompt`, required),
  `studio.strategies.run` (`strategy_name` required, `prompt` optional),
  `studio.prompts.list` (`family`, optional), `studio.prompts.get` (`name`, required).
  Argument names and `execute` behavior are unchanged.

## Files

- `vidbyte/mcp_server/server/core.py`
- `vidbyte/mcp_server/server/handlers/ping.py` (new)
- `vidbyte/mcp_server/handlers.py`
- `tests/test_mcp_studio_server.py`
- `artifacts/file_index.md` (lists the `ping` handler)

## Risks

- A thread blocked in `readline()` cannot be interrupted; if a host never closes stdin,
  interpreter shutdown waits for it. Hosts close stdin on exit, which yields `b""`.
- `prompts/list` now returns the built-in prompts (about 76) where it returned only caller
  prompts before; that is the intended behavior.

## Verification

- Tests in `tests/test_mcp_studio_server.py`: the thread-reader path (platform patched to
  `win32`, `BytesIO` stdin) answers `initialize` and ends on EOF; `ping` returns `{}`;
  `studio.prompts.list` is non-empty and `studio.prompts.get` finds a built-in key; caller
  `prompt_content` overrides a built-in key; advertised `inputSchema`s match what each
  `execute` reads.
- Manual Windows repro: piping an `initialize` line into `python -m vidbyte.mcp_server`
  prints a JSON-RPC result instead of a pipe-transport traceback.
- `python scripts/run_ci.py`, `python lint/run.py`, and the CI workflows.
