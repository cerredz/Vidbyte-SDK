# Release 0.4.3: the Vidbyte gateways move to api.vidbyte.pro

`vidbyte-sdk` 0.4.2, the latest release on PyPI, sends Jev and generative-gateway calls to `https://vidbyte-backend.onrender.com`. That Render service is suspended: the Vidbyte backend now runs on Vercel and answers at `https://api.vidbyte.pro`, which the platform contract marks `live`. Every 0.4.2 install therefore fails on those calls. This release changes only the two gateway endpoint constants and the vendored platform contract (PR #1212), so it is a patch release: no export is added, removed, or renamed, and no default other than the two URLs changes.

## What 0.4.3 changes

- `vidbyte/lib/constants/jev.py`: `VIDBYTE_JEV_GATEWAY_ENDPOINT` and `VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT` point at `https://api.vidbyte.pro`.
- `lint/contracts/vidbyte-platform-contract.json`: re-vendored from cerredz/Vidbyte with `https://api.vidbyte.pro` live, which clears rule C018 for the new host.
- Every literal that names the version moves from 0.4.2 to 0.4.3, as in the 0.4.2 release: `pyproject.toml`, `vidbyte/__init__.py`, the CLI fallback, the MCP server default, the MCP `clientInfo`, `README.md`, `llms.txt`, the bug template, and the regenerated `contracts/sdk-public-api.json`.

## Release steps

Merge, push the tag `v0.4.3` on the merge commit, and dispatch `publish.yml` on that tag. The workflow reruns CI and waits for approval on the `pypi` environment before uploading through trusted publishing.

## Downstream

vidbyte-cli 0.3.5 raises its floor to `vidbyte-sdk[codex]>=0.4.3,<0.5`, because a CLI on an installed 0.4.2 would still call the suspended host through these constants. Users on 0.4.2 must upgrade; there is no server-side redirect from the old host.
