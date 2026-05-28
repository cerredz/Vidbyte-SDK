"""Verification script for the MCP preset expansion (100 new presets).

Runs every structural test case from the design doc and prints PASS/FAIL per test.
Exits with code 1 if any test fails.
"""

from __future__ import annotations

import sys

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, str]] = []


def check(name: str, condition: bool) -> None:
    # Records a single test result.
    label = PASS if condition else FAIL
    results.append((name, label))
    print(f"  [{label}] {name}")


def run_tests() -> None:
    # Executes all structural invariant checks against the expanded preset catalog.
    from vidbyte.lib.config.mcp_presets import ALL_PRESETS, McpPresetDefinition
    from vidbyte.tools.mcp.presets import McpPresetRegistry, McpPresetNotFoundError

    print("\n=== MCP Preset Expansion — Verification Suite ===\n")

    # ── Catalog count ─────────────────────────────────────────────────────────
    check("ALL_PRESETS has exactly 201 entries after expansion", len(ALL_PRESETS) == 201)

    # ── Name uniqueness ───────────────────────────────────────────────────────
    names = [p.name for p in ALL_PRESETS]
    dupes = [n for n in set(names) if names.count(n) > 1]
    check("ALL_PRESETS contains no duplicate name values", len(dupes) == 0)

    # ── Registry parity ───────────────────────────────────────────────────────
    registry_list = McpPresetRegistry.list_presets()
    check("McpPresetRegistry registers all 201 presets", len(registry_list) == 201)

    # ── Unknown preset raises correct error ───────────────────────────────────
    raised = False
    try:
        McpPresetRegistry.get("__does_not_exist__")
    except McpPresetNotFoundError:
        raised = True
    check("McpPresetRegistry.get raises McpPresetNotFoundError for unknown preset", raised)

    # ── Every preset has non-empty name and non-empty command ─────────────────
    all_have_name = all(bool(p.name) for p in ALL_PRESETS)
    check("Every preset has a non-empty name", all_have_name)

    all_have_cmd = all(len(p.command) >= 1 for p in ALL_PRESETS)
    check("Every preset command tuple has at least one element", all_have_cmd)

    # ── Every preset has a non-empty description ──────────────────────────────
    all_have_desc = all(bool(p.description) for p in ALL_PRESETS)
    check("Every preset has a non-empty description", all_have_desc)

    # ── Every preset has a non-empty category ─────────────────────────────────
    all_have_cat = all(bool(p.category) for p in ALL_PRESETS)
    check("Every preset has a non-empty category", all_have_cat)

    # ── New categories are present ────────────────────────────────────────────
    categories = {p.category for p in ALL_PRESETS}
    check("'E-Commerce & Payments' category exists", "E-Commerce & Payments" in categories)
    check("'Automation & Workflow' category exists", "Automation & Workflow" in categories)

    # ── Spot-check: specific new presets are reachable by name ────────────────
    spot_checks = [
        "stripe", "shopify", "zapier", "n8n",
        "perplexity", "serper", "elasticsearch", "zendesk",
        "stability-ai", "mistral", "pubmed", "git",
        "digitalocean", "fly-io", "resend", "langsmith",
    ]
    for preset_name in spot_checks:
        try:
            preset = McpPresetRegistry.get(preset_name)
            ok = preset.name == preset_name
        except Exception:
            ok = False
        check(f"Preset '{preset_name}' is registered and retrievable", ok)

    # ── Category filter returns correct subset ────────────────────────────────
    ecom = McpPresetRegistry.list_presets(category="E-Commerce & Payments")
    check("list_presets(category='E-Commerce & Payments') returns 5 items", len(ecom) == 5)

    automation = McpPresetRegistry.list_presets(category="Automation & Workflow")
    check("list_presets(category='Automation & Workflow') returns 2 items", len(automation) == 2)

    # ── Registry class attributes are accessible ──────────────────────────────
    check("McpPresetRegistry.Stripe class attr is StripeMCP", McpPresetRegistry.Stripe.name == "stripe")
    check("McpPresetRegistry.Elasticsearch class attr is ElasticsearchMCP", McpPresetRegistry.Elasticsearch.name == "elasticsearch")
    check("McpPresetRegistry.Git class attr is GitMCP", McpPresetRegistry.Git.name == "git")

    # ── ALL_PRESETS __all__ sync: all exported names are importable ────────────
    import vidbyte.lib.config.mcp_presets as catalog_mod
    exported = catalog_mod.__all__
    for export_name in exported:
        has_attr = hasattr(catalog_mod, export_name)
        check(f"mcp_presets.__all__ export '{export_name}' is importable", has_attr)
        if not has_attr:
            break  # stop after first missing to keep output readable

    # ── No preset's required_env contains an empty string ─────────────────────
    no_empty_env = all(all(v for v in p.required_env) for p in ALL_PRESETS)
    check("No preset required_env contains an empty string", no_empty_env)

    # ── Print summary ─────────────────────────────────────────────────────────
    total = len(results)
    passed = sum(1 for _, label in results if label == PASS)
    failed = total - passed
    print(f"\n{'=' * 50}")
    print(f"{passed}/{total} tests passed" + (f"  ({failed} FAILED)" if failed else ""))
    print('=' * 50)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
