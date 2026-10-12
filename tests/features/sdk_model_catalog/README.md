# Model catalog and pricebook probes

## Folder Description / Intent

This folder pins the model catalog and the first-party pricebook. An added model must validate under its own provider and price at the rate its provider publishes, never at a sibling's rate picked up by prefix lookup. The catalog lives in `vidbyte/lib/constants/runners.py` and the rates in `vidbyte/lib/registries/pricing.py`, not in these tests.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` defines catalog acceptance, exact first-party rates, routed names and tier boundaries.
- `test_catalog_pricing_contract.py` checks every added model through the real registries, usage parsers and usage tracker.

## Logs

- 2026-10-11 - Catalogued and priced the models released since July 2026; Claude Haiku 5.5's 100K tier now counts cache reads and writes.
- 2026-10-12 - Anthropic 1-hour cache writes, named by the usage's `cache_creation` breakdown, now bill at 2x the active input rate instead of the 5-minute cache-write rate.
