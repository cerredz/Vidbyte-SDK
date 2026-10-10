# contracts/ -- contract files this repository owns

## Responsibility

This folder holds machine-readable contracts that the Vidbyte SDK publishes for
other repositories to vendor byte for byte. Each file is generated from SDK
source by a script in `scripts/` and kept current by a lint rule, so a consumer
can diff its own code against a copy instead of importing the SDK.

## Non-Goals

- These files are not read by the installed package and are not shipped in the wheel.
- Never edit a contract by hand; regenerate it with its script.
- Contracts this repository consumes from other repositories live in `lint/contracts/`.

## File Index

- `.gitattributes` -- pins every contract to LF so a Windows checkout cannot change its bytes.
- `sdk-public-api.json` -- the SDK's public import surface: the sorted names of `vidbyte.__all__`, plus the
  distribution name and version from the project metadata, with the commit whose sources produced it. The
  generator script below writes it, lint rule C016 (`public-api-contract-current`) keeps it current, and
  vidbyte-cli vendors it under its own lint contracts folder.

## Regenerating

```bash
python scripts/generate-sdk-public-api.py --check   # exit 1 when the committed file is stale
python scripts/generate-sdk-public-api.py           # rewrite it after committing the source change
```

The generator records `HEAD` as `source.commit` and refuses to write while `vidbyte/__init__.py` or
`pyproject.toml` has uncommitted changes. It keeps the recorded commit when the derived data is
unchanged. When an export is removed or renamed, tell the vidbyte-cli owners so they refresh their copy.

## Change Log

- 2026-10-09: Created with `sdk-public-api.json` (schema_version 1) for the cross-repo lint contracts.
