# SourceContext

## Intent

This package turns one validated pull-request source into bounded
`DocumentContextItem` values for an agent.

## Index

- `context.py` — public `SourceContext` load and budget pipeline.
- Parent `providers.py` — provider selection and retrieval.

## Non-goals

This package does not own provider routes, subprocess execution, credential
storage, or repository tools.

## Change log

- Added as the separated source-context surface for PR #431.
