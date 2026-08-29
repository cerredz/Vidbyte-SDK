# MCP Tools

Client-side Model Context Protocol support: discover tools on an external MCP server and expose them
as native Vidbyte tools an agent can call.

## Role In The SDK

```
attach.py    -- attaches an MCP server's tools to an agent
presets.py   -- named server configurations
client.py    -- MCP session: initialize, list tools, call tools
bridge.py    -- wraps a discovered MCP tool as a Vidbyte ToolSpec
transport.py -- McpTransport protocol + hardened stdio JSON-RPC implementation
types.py     -- shared payload dataclasses
```

`transport.py` carries the hard part. Its header describes the guarantees:

> Newline-delimited JSON-RPC over subprocess stdio with ID demultiplexing, background stdout/stderr
> readers, per-request deadlines, restricted child environment, and idempotent bounded close.

The design reasoning lives in `docs/design/harden-mcp-stdio-transport.md`. This README covers the
*protocol* those mechanics implement.

---

# External Contract

> **sources:** the first-party links in the MCP reference table below
> **upstream_version:** MCP specification revision **2026-07-28** (latest at retrieval)
> **retrieved:** 2026-08-29
> **verified_by:** `vidbyte/tools/mcp/transport.py`, `vidbyte/tools/mcp/client.py`,
> `vidbyte/tools/mcp/bridge.py`
> **scope:** Client-side `tools` capability and the stdio transport. Excludes resources, prompts,
> sampling, and elicitation.
>
> Written in our own words: `vidbyte-sdk` is MIT-licensed and published to PyPI, and the
> specification text is not MIT-licensed.

## Official MCP Documentation

| Surface | First-party reference | Why it matters here |
| --- | --- | --- |
| Specification | [MCP 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28/) | Current protocol revision |
| Tools | [Tools capability](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | Discovery and invocation payloads |
| Transports | [Transport specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) | stdio and Streamable HTTP behavior |
| Python SDK | [Official Python SDK](https://github.com/modelcontextprotocol/python-sdk) | Reference implementation and typed protocol surface |

## Expanded MCP Reading Map

The implementation currently targets the client-side `tools` capability and
stdio transport. The wider map is kept here because protocol negotiation,
transport changes, content blocks, and authorization are the likely insertion
points when the client grows. **Retrieved:** 2026-08-29.

- [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28/)
- [Specification versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
- [Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture)
- [Lifecycle](https://modelcontextprotocol.io/specification/2026-07-28/basic/lifecycle)
- [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- [Transports overview](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [Stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports#stdio)
- [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- [Server overview](https://modelcontextprotocol.io/specification/2026-07-28/server)
- [Server initialization](https://modelcontextprotocol.io/specification/2026-07-28/basic/lifecycle#initialization)
- [Tools capability](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [Resources capability](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)
- [Resource links](https://modelcontextprotocol.io/specification/2026-07-28/server/resources#resource-links)
- [Prompts capability](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts)
- [Completions capability](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/completion)
- [Logging capability](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/logging)
- [Ping](https://modelcontextprotocol.io/specification/2026-07-28/basic/utilities/ping)
- [Client roots](https://modelcontextprotocol.io/specification/2026-07-28/client/roots)
- [Client sampling](https://modelcontextprotocol.io/specification/2026-07-28/client/sampling)
- [Client elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)
- [Schema reference](https://modelcontextprotocol.io/specification/2026-07-28/schema)
- [Security best practices](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices)
- [Official Python SDK repository](https://github.com/modelcontextprotocol/python-sdk)
- [Python SDK documentation](https://modelcontextprotocol.github.io/python-sdk/)
- [Python SDK PyPI package](https://pypi.org/project/mcp/)
- [Official TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Official MCP Inspector](https://github.com/modelcontextprotocol/inspector)
- [Official MCP servers](https://github.com/modelcontextprotocol/servers)
- [MCP documentation index](https://modelcontextprotocol.io/llms.txt)

## Wire Format — stdio

MCP over stdio is JSON-RPC 2.0, one message per line, newline-delimited, over the child process's
stdin and stdout. Three properties drive `transport.py`'s design:

- **Responses are correlated by `id`, not by order.** A server may answer concurrent requests in any
  order, which is why the transport demultiplexes by ID rather than reading a reply per write.
- **stdout is protocol, stderr is diagnostics.** Anything a server writes to stdout that is not a
  JSON-RPC message corrupts the stream. stderr must be drained continuously or a chatty server fills
  its pipe buffer and blocks — this is the single most common way an MCP integration hangs.
- **The child is a process, not a connection.** It can exit at any point, and every in-flight request
  must be failed rather than left awaiting. `transport.py` fans process exit out to pending waiters
  for this reason.

## Tool Discovery And Invocation

Two methods matter to this package:

| Method | Purpose | Result shape |
| --- | --- | --- |
| `tools/list` | Enumerate available tools | `tools[]`, each with `name`, `description`, `inputSchema`; optional `nextCursor` |
| `tools/call` | Invoke a tool | `content[]` blocks plus an `isError` flag |

`tools/list` supports cursor pagination. A client that reads only the first page silently sees a
subset of a large server's tools.

### Tool definition fields

- `name` — unique per server. The recommended character set is ASCII letters, digits, underscore,
  hyphen, and dot, with a length of 1–128. Names are case-sensitive.
- `description` — human-readable; this is what the model reads when deciding to call the tool.
- `inputSchema` — a JSON Schema object, defaulting to draft 2020-12. It must be a valid schema
  object and never `null`. A parameter-less tool uses `{"type": "object", "additionalProperties":
  false}`.
- `outputSchema` — optional; when present, results should be validated against it.
- `title`, `icons`, `annotations` — optional display metadata. Annotations from an untrusted server
  must be treated as untrusted input.

**Name collisions are the caller's problem.** Tool-name uniqueness is scoped to a single server, so
attaching two servers that both expose `search` produces a collision. `attach.py` is where a
disambiguation strategy (such as prefixing with a server identifier) belongs. The server's own
`name` from `serverInfo` is not guaranteed unique and must not be relied on for this.

### Result handling — the two error mechanisms

MCP separates failures into two categories, and conflating them degrades agent behavior:

1. **Protocol errors** — unknown tool, malformed request, server error. Delivered as a JSON-RPC
   `error` object with a numeric code. These indicate the request itself was wrong; a model is
   unlikely to recover by retrying.
2. **Tool execution errors** — API failure, input validation, business-logic rejection. Delivered as
   a *successful* JSON-RPC result whose body sets `isError: true` and whose `content` explains what
   went wrong. These are actionable: the model can read the message and retry with corrected
   arguments.

`bridge.py` must preserve this distinction when converting to `ToolResult`. Collapsing both into one
error type removes the model's ability to self-correct on the recoverable category; treating an
`isError: true` result as a success feeds the model a failure message it will read as output.

### Content blocks

A result's `content` is an array of typed blocks: `text`, `image` (base64 `data` + `mimeType`),
`audio`, `resource_link` (a URI reference), and `resource` (an embedded resource). A tool may also
return `structuredContent` — a JSON value conforming to its `outputSchema` — and when it does, it
should also return the serialized JSON as a text block for compatibility. A bridge that reads only
text blocks silently drops image, audio, and structured results.

## Transport Invariants

1. **stderr is drained continuously**, never read only on failure.
2. **Every request has a deadline.** A server that never answers must not hang the agent loop.
3. **Close is idempotent and bounded.** Shutdown cannot block indefinitely on a wedged child.
4. **The child environment is restricted.** Do not widen it to pass the parent's full environment —
   an MCP server is third-party code running locally with the agent's privileges.
5. **Process exit fails all pending requests.** Never leave a waiter unresolved.
6. **Non-JSON stdout lines are a protocol violation**, and must not crash the reader.

## Adding A Transport

1. Implement the `McpTransport` protocol in `transport.py`.
2. Preserve every invariant above; they are transport-independent except where noted.
3. For the Streamable HTTP transport, note that revision 2026-07-28 removed protocol-level sessions
   and the standalone GET stream, and requires an `MCP-Protocol-Version` header on every POST whose
   value matches the request body's protocol-version metadata. Record the revision targeted here.
