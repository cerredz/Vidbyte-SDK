# Point the managed Jev gateway at the live backend host

## Problem

`VIDBYTE_JEV_GATEWAY_ENDPOINT` in `vidbyte/lib/constants/jev.py` was
`https://api.vidbyte.pro/api/v1/models/typesafe`. `DecisionModelConfig.resolved_endpoint()` returns it for every
`VIDBYTE_MANAGED` config, which is JevAgent's default decision mode. Every managed decision, model listing, and run
close went to that host.

`api.vidbyte.pro` has no DNS record. It returned NXDOMAIN on 2026-10-09 and again on 2026-10-11. The vendored platform
contract (`lint/contracts/vidbyte-platform-contract.json`) lists it as `planned`. Lint rule C018 already reported the
literal, and its one finding was frozen in `lint/baseline.json`.

A live JevAgent run on Grok (2026-10-11) showed the effect. The agent answered, but every Jev check failed with a
connection error. The checks were reported as unavailable and passed open, so the agent ran with no Jev checks at
all.

The CLI and the website already use `https://vidbyte-backend.onrender.com`, which the contract lists as `live`.

## Change

- `VIDBYTE_JEV_GATEWAY_ENDPOINT` is now `https://vidbyte-backend.onrender.com/api/v1/models/typesafe`. The path is
  unchanged.
- The managed endpoint is still a fixed constant. A caller still cannot redirect the `vb_live_` bearer key
  (`@intent managed-key-stays-on-vidbyte-host`).
- The C018 baseline drops from 1 to 0, so the next planned host spelled in SDK code fails lint.
- The vendored contract is unchanged. It already lists the onrender host as `live`, and `api.vidbyte.pro` stays
  `planned` until DNS exists.

## Still blocked after this change

On 2026-10-11, the gateway on the onrender host answered, but returned 502 with `reason: credential_missing`. The
backend has no `TYPESAFE_API_KEY` set on Render. This change makes managed Jev calls reach the backend. The checks
will only return answers after that key is configured, and configuring it is a separate step for the platform owner.

## Alternatives not taken

- **Keep `api.vidbyte.pro` and add DNS.** This needs a DNS record and a Render custom domain. The SDK would stay
  broken until both exist. When the domain goes live, the contract flips the host to `live`, and this constant can
  move back in one line.
- **A configurable managed base URL.** C018's repair note allows one only if overrides are validated against the
  contract's live hosts. That is more surface than a broken constant needs.

## Tests

`tests/test_jev_managed_gateway.py`:

- The existing endpoint, `systemone`, and `models` URL assertions now expect the onrender host. The rejected-endpoint
  case uses a different path on the live host, so same-host redirection stays rejected.
- `test_managed_endpoint_origin_is_a_live_platform_host` reads the vendored contract and requires the constant's origin
  to be listed as `live`. Against the old constant it fails with
  `'https://api.vidbyte.pro' not found in {'https://vidbyte-backend.onrender.com'}`.
