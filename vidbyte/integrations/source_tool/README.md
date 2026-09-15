# SourceTool

## Intent

This package builds repository-scoped provider tools synchronously from one
validated source mapping.

## Index

- `builder.py` — public `SourceTool` composition and output bound.
- Parent `providers.py` — provider selection.

## Non-goals

This package does not execute requests during `build()` and does not accept
model-provided hosts, repositories, routes, executables, or shell commands.

## Change log

- Added as the separated source-tool surface for PR #431.
