# lint/contracts/ -- contracts this repository vendors from other repositories

## Responsibility

This folder holds byte-for-byte copies of machine-readable contracts that other
Vidbyte repositories generate, so SDK lint rules can check SDK code against them
without network access or a checkout of the producing repository.

## Non-Goals

- These copies are read only by `lint/core/`; the installed package never reads them.
- Never edit a vendored file by hand. Refresh it from the producing repository.
- Contracts this repository publishes for others live in the repository-root `contracts/` folder.

## File Index

- `.gitattributes` -- pins vendored JSON to LF so a Windows checkout cannot change its bytes.
- `vidbyte-platform-contract.json` -- the Vidbyte platform contract from cerredz/Vidbyte: backend routes
  (method, path, access class), x402 capabilities, error codes, the API-key prefix, and the public API hosts
  with their `live` or `planned` status. Read by lint/core/platform_contract.py for rules C017-C020.

## Provenance

| File | Source repository and path | Copied from | Blob | Contract `source.commit` |
|---|---|---|---|---|
| `vidbyte-platform-contract.json` | cerredz/Vidbyte `contracts/vidbyte-platform-contract.json` | `main` at `bbeef425a3af7e554d55a3016d73f0fa85976c76` (#648) | `0be92ffe2fa7a79ff3780be36b95962a0b56fac3` | `3b501a638cbea33b89ce4a6d9ae9527df7699b24` |

## Refreshing

Run these from this repository's root, with a cerredz/Vidbyte checkout at `../vidbyte`:

```bash
git -C ../vidbyte fetch origin
git -C ../vidbyte show origin/main:contracts/vidbyte-platform-contract.json > lint/contracts/vidbyte-platform-contract.json
git -C ../vidbyte rev-parse origin/main:contracts/vidbyte-platform-contract.json   # the producer's blob
git hash-object lint/contracts/vidbyte-platform-contract.json                       # must print the same blob
python lint/run.py --rule C017 && python lint/run.py --rule C018 && python lint/run.py --rule C019 && python lint/run.py --rule C020
```

Then update the Provenance row (commit, blob, and `source.commit`) in the same pull request. A refresh can
surface new findings: a removed route, a host that changed status, a dropped error code, or a new key prefix.
Fix the SDK code; do not raise a baseline to absorb a contract change. A copy with a different
`schema_version` makes C017-C020 stop with ERRORED until `lint/core/platform_contract.py` supports it.

## Change Log

- 2026-10-09: Created with `vidbyte-platform-contract.json` (schema_version 1) for the cross-repo lint contracts.
