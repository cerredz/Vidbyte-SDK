# Release 0.2.0

## What and why

PyPI's only `vidbyte-sdk` release, 0.1.0, predates the Codex integration (`vidbyte.agents.codex`
and the `codex` extra). `vidbyte-cli` needs that integration and pins it through a
`git+https://...` direct reference, which PyPI refuses to accept in an uploaded distribution.
So the CLI cannot be published until an SDK release that contains the integration exists on
PyPI. This change bumps the package to 0.2.0 so the tag-triggered `publish.yml` can release it.
0.2.0 rather than 0.1.1, because `main` adds public API (the Codex agent, Jev, the decision
provider) and the README says minor versions carry API changes while in alpha.

## How it works

Every literal `0.1.0` that names this package's own version becomes `0.2.0`:

- `pyproject.toml` `version`: the release source of truth, which `publish.yml` checks the tag against.
- `vidbyte/__init__.py` `__version__`: `scripts/run_ci.py` asserts it equals the built distribution's version.
- `vidbyte/cli/__init__.py`: the source-checkout fallback for `--version`.
- `vidbyte/mcp_server/server/core.py`: the default server version the MCP server advertises.
- `vidbyte/tools/mcp/client.py`: the `clientInfo.version` sent to every MCP server.
- `README.md`, `llms.txt`, and the bug-report template placeholder, so user-facing text matches.

`artifacts/file_index.md` also mentions 0.1.0, but it is generated and gets regenerated rather
than hand-edited, so it is left alone. Collapsing the five code literals into one source is a
worthwhile follow-up. It is out of scope here because the lower layers cannot import the
package root without risking an import cycle.

## Release steps after merge

1. `git tag v0.2.0 <merge commit> && git push origin v0.2.0`.
2. `publish.yml` validates the tag against `pyproject.toml`, reruns CI, and then waits on the
   `pypi` environment's required reviewer. Publishing happens only after that approval.

## Files

`pyproject.toml`, `vidbyte/__init__.py`, `vidbyte/cli/__init__.py`,
`vidbyte/mcp_server/server/core.py`, `vidbyte/tools/mcp/client.py`, `README.md`, `llms.txt`,
`.github/ISSUE_TEMPLATE/bug_report.yml`

## Risks

- A PyPI version can never be reused. If 0.2.0 ships broken, the fix is 0.2.1.
- The release includes six commits made after the revision the CLI currently pins. They are
  additive: the Codex agent code is unchanged apart from its README. Before tagging, the CLI's
  full gate runs against the locally built 0.2.0 wheel.

## Verification

- `python scripts/run_ci.py` (full local gate, including the version-equality assertion).
- The CLI's `scripts/run_ci.py` with `vidbyte-sdk[codex]>=0.2.0`, resolved from the locally built wheel.
- `git grep '"0.1.0"' -- vidbyte pyproject.toml` returns nothing.
