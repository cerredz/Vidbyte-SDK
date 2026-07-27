# Priced operation tools

## Folder Description / Intent

This folder owns model-callable search and fetch tool contracts whose provider
operations are priced by the SDK runtime. It defines stable tool schemas and
authoritative usage metadata while allowing applications to inject the real
provider execution boundary.

Provider authentication, HTTP clients, response DTOs, and product-specific
mapping do not belong here. Applications own those concerns and supply a narrow
async executor when constructing a tool.

## Blast Radius

These tools are exported through `vidbyte.tools.builtins.operations` and are
recognized by the agent runtime as `PricedOperationTool` instances. Changes can
affect model-facing schemas, tool results, and operation usage accounting.

## Non-Goals

- Do not store provider credentials here; applications own secret configuration.
- Do not add application-domain DTOs; this package exposes SDK tool contracts.
- Do not perform product persistence; tools return bounded `ToolResult` values.
- Do not let executors choose operation or provider pricing identity.
- Do not place generic tool execution policy here; `vidbyte/tools/executor.py` owns it.
- Do not add model usage pricing; `vidbyte/agents/pricing` owns model rates.
- Do not parse application configuration; `vidbyte/config` owns YAML loading.

## File Index

- `base.py` defines `PricedOperationTool`, executor delegation, and authoritative
  operation-usage metadata. Open it when changing the shared application seam or
  pricing annotation contract. Keep the class stateless across calls.
- `search.py` declares provider-specific model-facing search schemas and billing
  units. Open it when adding a search operation or changing its public arguments.
  Provider HTTP behavior must enter through the base executor seam.
- `fetch.py` declares provider-specific fetch schemas and billing modes. Open it
  when changing page-count semantics or adding a fetch operation. Direct HTTP is
  the only built-in implementation that performs network I/O itself.
- `__init__.py` exposes the public priced operation vocabulary. Update it whenever
  a new operation tool becomes publicly supported.

## Logs

- 2026-07-27 - Added executor delegation to priced tools - applications no longer need subclasses that duplicate SDK billing contracts.
