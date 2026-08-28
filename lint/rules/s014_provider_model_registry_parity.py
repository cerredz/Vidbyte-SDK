"""FILE: lint/rules/s014_provider_model_registry_parity.py

PURPOSE: Keeps provider enums, configuration maps, and runner catalogs synchronized.
ROLE IN CODEBASE: Prevents accepted providers/models from failing only during dispatch.
ARCHITECTURE NOTE: Registry data is extracted statically; importing the SDK is forbidden.
FUNCTION INVENTORY: RegistryParityAnalyzer extracts named class/module dictionaries.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/declarative-config-resolution.md
TESTS: Exercised by python lint/run.py --rule S014.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

ENUM_FILE = "vidbyte/lib/enums/model_provider.py"
REGISTRY_FILE = "vidbyte/lib/registries/models.py"
RUNNER_FILE = "vidbyte/lib/constants/runners.py"
PARITY_MAPS = ("DEFAULT_PROVIDER_MODELS", "API_KEY_ENV_VARS", "DEFAULT_ENDPOINTS")


class RegistryParityAnalyzer:
    """Extracts declarative registry literals and reports cross-map drift."""

    def analyze(self, files: dict[str, SourceFile]) -> list[tuple[str, int, str, str]]:
        # Compares enum names/values, provider-keyed maps, defaults, and runner keys.
        enum_source = files[ENUM_FILE]
        registry_source = files[REGISTRY_FILE]
        runner_source = files[RUNNER_FILE]
        enum = self._enum_members(enum_source.tree)
        maps = {name: self._class_dict(registry_source.tree, "ProviderModelRegistry", name) for name in PARITY_MAPS}
        qualified = self._module_string_dict(runner_source.tree, "MODEL_PROVIDER_RUNNER_TYPE_MAP")
        bare = self._module_string_dict(runner_source.tree, "MODEL_RUNNER_TYPE_MAP")
        hits: list[tuple[str, int, str, str]] = []
        expected_names = set(enum)
        for name, values in maps.items():
            actual = set(values)
            for missing in sorted(expected_names - actual):
                hits.append((REGISTRY_FILE, values.get("__line__", 1), missing, f"{name} is missing ModelProvider.{missing}"))
            for extra in sorted(actual - expected_names - {"__line__"}):
                hits.append((REGISTRY_FILE, int(values.get("__line__", 1)), extra, f"{name} contains unknown provider {extra}"))
        defaults = maps["DEFAULT_PROVIDER_MODELS"]
        qualified_lower = {key.lower() for key in qualified if key != "__line__"}
        for member, model in defaults.items():
            if member == "__line__":
                continue
            provider = enum.get(member, "").lower()
            qualified_default = model.lower() if isinstance(model, str) and model.lower().startswith(f"{provider}/") else f"{provider}/{str(model).lower()}"
            if isinstance(model, str) and qualified_default not in qualified_lower:
                hits.append((REGISTRY_FILE, int(defaults.get("__line__", 1)), model, f"default {member} model is absent from qualified runner catalog"))
        provider_values = {value.lower() for value in enum.values()}
        for key in sorted(qualified_lower):
            provider, separator, model = key.partition("/")
            if not separator or provider not in provider_values:
                hits.append((RUNNER_FILE, int(qualified.get("__line__", 1)), key, "qualified runner key has unknown provider prefix"))
            if model and model != "auto" and model not in {item.lower() for item in bare if item != "__line__"}:
                hits.append((RUNNER_FILE, int(qualified.get("__line__", 1)), key, "qualified model is absent from bare runner catalog"))
        return hits

    def _enum_members(self, tree: ast.Module | None) -> dict[str, str]:
        # Extracts literal ModelProvider member names and string values.
        members: dict[str, str] = {}
        for node in tree.body if tree else ():
            if isinstance(node, ast.ClassDef) and node.name == "ModelProvider":
                for item in node.body:
                    if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                        members[item.targets[0].id] = item.value.value
        return members

    def _class_dict(self, tree: ast.Module | None, class_name: str, variable: str) -> dict[str, str | int]:
        # Extracts ModelProvider member keys and literal string values from a class map.
        for node in tree.body if tree else ():
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id == variable and isinstance(item.value, ast.Dict):
                    result: dict[str, str | int] = {"__line__": item.lineno}
                    for key, value in zip(item.value.keys, item.value.values, strict=True):
                        member = key.attr if isinstance(key, ast.Attribute) and isinstance(key.value, ast.Name) and key.value.id == "ModelProvider" else ""
                        if member:
                            result[member] = value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else ast.unparse(value)
                    return result
        return {"__line__": 1}

    def _module_string_dict(self, tree: ast.Module | None, variable: str) -> dict[str, str | int]:
        # Extracts string keys from one annotated module-level runner map.
        for item in tree.body if tree else ():
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id == variable and isinstance(item.value, ast.Dict):
                result: dict[str, str | int] = {"__line__": item.lineno}
                for key, value in zip(item.value.keys, item.value.values, strict=True):
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        result[key.value] = ast.unparse(value)
                return result
        return {"__line__": 1}


class ProviderModelRegistryParityRule(Rule):
    """Requires every declarative provider/model registry to remain in parity."""

    id = "S014"
    name = "provider-model-registry-parity"
    severity = "blocking"
    summary = "Provider enums, defaults, endpoints, credentials, and runner maps agree."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Loads required source records and reports a clear missing-file analyzer error.
        files = {source.rel: source for source in catalog.python_files()}
        missing = [path for path in (ENUM_FILE, REGISTRY_FILE, RUNNER_FILE) if path not in files]
        if missing:
            raise RuntimeError(f"Registry parity requires tracked files {missing}; restore them before linting.")
        return [Finding(rule_id=self.id, rel_path=path, line=line, source_line=files[path].line_at(line), symbol=symbol, extra={"reason": reason}) for path, line, symbol, reason in RegistryParityAnalyzer().analyze(files)]

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the exact parallel registry that drifted and the synchronized repair.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} registry item {finding.symbol} is inconsistent: {finding.extra.get('reason', 'registry drift')}.", why_blocked="Provider validation can accept a value that dispatch cannot run, or a configured default can have no endpoint/API key/runner. The user sees a late runtime failure instead of a configuration error.", how_to_fix="Update ModelProvider, DEFAULT_PROVIDER_MODELS, API_KEY_ENV_VARS, DEFAULT_ENDPOINTS, and both runner maps as one declarative change. Add aliases deliberately and preserve the documented bare auto exception.", correct_examples=("vidbyte/lib/registries/models.py - central provider configuration maps", "vidbyte/lib/constants/runners.py - qualified and bare runner catalogs"), will_not_work=("Adding a fallback branch in a caller or disabling strict validation.", "Updating only the default model without its provider-qualified runner key."), verify=self.verify_command())


RULE = ProviderModelRegistryParityRule()
