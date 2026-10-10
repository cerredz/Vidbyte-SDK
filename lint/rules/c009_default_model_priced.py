"""FILE: lint/rules/c009_default_model_priced.py

PURPOSE: Detect a token-priced provider whose default model resolves to no rate in the built-in model pricebook.
ROLE IN CODEBASE: Enforces C009 so a run on any provider's default model reports a real cost instead of cost_complete=False.
ARCHITECTURE NOTE: Static cross-file AST parity over the ModelProvider enum, ProviderModelRegistry.DEFAULT_PROVIDER_MODELS and MODEL_ALIASES, the runner catalogs, and PROVIDER_PRICING. PricingLookup mirrors ModelPricingRegistry.resolve (exact, alias-normalized, then longest prefix) without importing it.
FUNCTION INVENTORY: RegistryLiterals reads literals; PricingLookup mirrors resolve; DefaultPricingAnalyzer coordinates; DefaultModelPricedRule reports and explains.
COMMON MODIFICATION PATTERNS: When ModelPricingRegistry.resolve or ProviderModelRegistry.normalize_model changes its matching, change PricingLookup in the same edit; declare a provider in _PRICED_PER_RESPONSE only with the vendor mechanism that reports its cost.
WHAT NOT TO DO: Do not import vidbyte, price runner-catalog siblings (unverifiable rates are deliberately omitted), or treat an empty provider table as a declaration.
KNOWN EDGE CASES: Lookup is case-sensitive, like resolve. Audio, image, video, and embedding defaults are out of scope because UsageTracker never prices them from PROVIDER_PRICING. A missing file, table, or enum fails closed instead of reporting zero.
RELATED DOCS: docs/design/lint-sdk-pricing-usage-contracts.md; docs/design/agent-usage-pricing.md (table population rule); field-guide/vidbyte-sdk/provider-api-contracts.md
TESTS: python lint/run.py --rule C009; fixture and mutation results are recorded in the S2 pull request body.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

ENUM_FILE = "vidbyte/lib/enums/model_provider.py"
REGISTRY_FILE = "vidbyte/lib/registries/models.py"
PRICING_FILE = "vidbyte/lib/registries/pricing.py"
RUNNER_FILE = "vidbyte/lib/constants/runners.py"
_TOKEN_PRICED_RUNNER_CONSTANTS = ("RUNNER_TYPE_TEXT", "RUNNER_TYPE_DECISION")
# A provider listed here bills each response with its own reported cost, so a table rate would be a guess.
_PRICED_PER_RESPONSE = {
    "OPENROUTER": "OpenRouter prices each generation in its marketplace and returns usage.cost; OpenRouterUsage (vidbyte/agents/pricing/openrouter.py) prefers that reported cost over table math, and PROVIDER_PRICING keeps ModelProvider.OPENROUTER empty on purpose (docs/design/agent-usage-pricing-expansion.md non-goals).",
}
_PROVIDER_ABSENT = "provider-absent"
_MODEL_UNRESOLVED = "model-unresolved"


@dataclass(frozen=True, slots=True)
class DefaultModel:
    """One provider's registered default model, with the source line that declares it."""

    member: str
    value: str
    model: str
    line: int
    runner_type: str

    def __post_init__(self) -> None:
        # The diagnostic quotes every field, so a blank one would render an unusable message.
        if not self.member or not self.value or not self.model or not self.runner_type:
            raise ValueError(f"DefaultModel needs a member, value, model, and runner type, got {self.member!r}/{self.value!r}/{self.model!r}/{self.runner_type!r}.")
        if self.line < 1:
            raise ValueError(f"DefaultModel.line must be positive, got {self.line}.")


@dataclass(frozen=True, slots=True)
class UnpricedDefault:
    """A default model the pricebook cannot price, plus the facts the repair needs."""

    default: DefaultModel
    kind: str
    table_line: int
    provider_line: int
    priced_models: tuple[str, ...]
    catalog_models: tuple[str, ...]

    def __post_init__(self) -> None:
        # The kind picks the repair text, and the table line anchors where the rates go.
        if self.kind not in {_PROVIDER_ABSENT, _MODEL_UNRESOLVED}:
            raise ValueError(f"UnpricedDefault.kind must be {_PROVIDER_ABSENT!r} or {_MODEL_UNRESOLVED!r}, got {self.kind!r}.")
        if self.table_line < 1:
            raise ValueError(f"UnpricedDefault.table_line must be positive, got {self.table_line}.")


class RegistryLiterals:
    """Reads the literal enum, dict, and string constants the pricing contract is declared with."""

    @staticmethod
    def enum_members(tree: ast.Module, class_name: str) -> dict[str, str]:
        # Member name -> string value for one str Enum class.
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return {item.targets[0].id: item.value.value for item in node.body if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)}
        return {}

    @staticmethod
    def assigned_value(body: list[ast.stmt], name: str) -> tuple[ast.expr, int] | None:
        # The value and line of `name = ...` or `name: T = ...` in one statement list.
        for node in body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
                return node.value, node.lineno
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return node.value, node.lineno
        return None

    @classmethod
    def class_assigned_value(cls, tree: ast.Module, class_name: str, name: str) -> tuple[ast.expr, int] | None:
        # Like assigned_value, but inside one class body.
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return cls.assigned_value(node.body, name)
        return None

    @staticmethod
    def provider_member(key: ast.expr | None) -> str:
        # `ModelProvider.MISTRAL` -> "MISTRAL"; any other key shape -> "".
        if isinstance(key, ast.Attribute) and isinstance(key.value, ast.Name) and key.value.id == "ModelProvider":
            return key.attr
        return ""

    @staticmethod
    def string(node: ast.expr | None) -> str | None:
        # A literal string value, else None.
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class RunnerCatalog:
    """Reads the runner-type constants and maps of vidbyte/lib/constants/runners.py."""

    def __init__(self, tree: ast.Module) -> None:
        # Binds the parsed runner module once for every lookup.
        self.tree = tree

    def constant(self, name: str) -> str:
        # A module-level `NAME = "literal"` value; fails closed when it is gone.
        found = RegistryLiterals.assigned_value(self.tree.body, name)
        value = RegistryLiterals.string(found[0]) if found else None
        if not value:
            raise RuntimeError(f"C009 could not read the string constant {name} in {RUNNER_FILE}; update the rule if the runner type constants moved.")
        return value

    def runner_types(self, name: str) -> dict[str, str]:
        # A runner map keyed in lowercase, the way the registries look qualified models up.
        return {key.lower(): kind for key, kind in self.entries(name).items()}

    def entries(self, name: str) -> dict[str, str]:
        # A runner map in its source spelling, with its RUNNER_TYPE_* constant values resolved to strings.
        found = RegistryLiterals.assigned_value(self.tree.body, name)
        if found is None or not isinstance(found[0], ast.Dict):
            raise RuntimeError(f"C009 could not read the literal {name} in {RUNNER_FILE}; update the rule if the runner catalog moved.")
        resolved: dict[str, str] = {}
        for key, value in zip(found[0].keys, found[0].values, strict=True):
            text = RegistryLiterals.string(key)
            kind = RegistryLiterals.string(value) or (self.constant(value.id) if isinstance(value, ast.Name) else "")
            if text is not None and kind:
                resolved[text] = kind
        return resolved


class PricingLookup:
    """Mirrors ModelPricingRegistry.resolve over the static pricebook, without importing it."""

    def __init__(self, table: dict[str, tuple[str, ...]], aliases: dict[str, dict[str, str]], values: dict[str, str]) -> None:
        # The table maps provider member -> priced model keys; aliases and enum values drive normalize_model.
        self.table = table
        self.aliases = aliases
        self.values = values

    def resolves(self, member: str, model: str) -> bool:
        # Exact key, then the alias-normalized name, then the longest priced prefix, exactly as resolve() does.
        keys = self.table.get(member, ())
        requested = model.strip()
        if not requested:
            return False
        if requested in keys:
            return True
        canonical = self._normalize(member, requested)
        if canonical in keys:
            return True
        return any(canonical.startswith(key) for key in keys)

    def _normalize(self, member: str, model: str) -> str:
        # ProviderModelRegistry.normalize_model: strip a `provider/` prefix for the alias lookup only; no alias returns the raw name.
        prefix = f"{self.values.get(member, '')}/"
        lookup = model[len(prefix):] if model.lower().startswith(prefix) else model
        return self.aliases.get(member, {}).get(lookup.lower(), model)


class DefaultPricingAnalyzer:
    """Finds every token-priced provider whose default model the pricebook cannot price."""

    def analyze(self, files: dict[str, SourceFile]) -> list[UnpricedDefault]:
        # Read the provider vocabulary and each provider's registered default model.
        literals = RegistryLiterals()
        members = literals.enum_members(self._tree(files, ENUM_FILE), "ModelProvider")
        if not members:
            raise RuntimeError(f"C009 could not find the ModelProvider enum members in {ENUM_FILE}; update ENUM_FILE if the enum moved.")
        registry_tree = self._tree(files, REGISTRY_FILE)
        defaults_node = literals.class_assigned_value(registry_tree, "ProviderModelRegistry", "DEFAULT_PROVIDER_MODELS")
        aliases_node = literals.class_assigned_value(registry_tree, "ProviderModelRegistry", "MODEL_ALIASES")

        # Read the pricebook and the runner catalogs that say which defaults are billed from token rates.
        pricing_tree = self._tree(files, PRICING_FILE)
        table_node = literals.assigned_value(pricing_tree.body, "PROVIDER_PRICING")
        runners = RunnerCatalog(self._tree(files, RUNNER_FILE))
        if defaults_node is None or not isinstance(defaults_node[0], ast.Dict) or table_node is None or not isinstance(table_node[0], ast.Dict):
            raise RuntimeError(f"C009 needs literal ProviderModelRegistry.DEFAULT_PROVIDER_MODELS in {REGISTRY_FILE} and PROVIDER_PRICING in {PRICING_FILE}; update the rule if either moved.")
        table, provider_lines = self._pricebook(table_node[0])
        lookup = PricingLookup(table, self._aliases(aliases_node[0] if aliases_node else None), members)
        defaults = self._defaults(defaults_node[0], members, runners)

        # Keep the defaults that are token-priced, not declared priced-per-response, and that resolve to no rate.
        unpriced: list[UnpricedDefault] = []
        for default in defaults:
            if default.member in _PRICED_PER_RESPONSE or lookup.resolves(default.member, default.model):
                continue
            kind = _MODEL_UNRESOLVED if default.member in table else _PROVIDER_ABSENT
            unpriced.append(UnpricedDefault(default=default, kind=kind, table_line=table_node[1], provider_line=provider_lines.get(default.member, table_node[1]), priced_models=table.get(default.member, ()), catalog_models=self._catalog_models(runners, default, lookup)))
        return unpriced

    @staticmethod
    def _tree(files: dict[str, SourceFile], path: str) -> ast.Module:
        # Fails closed: a missing or unparsable contract file is an analyzer error, never zero findings.
        source = files.get(path)
        if source is None or source.tree is None:
            raise RuntimeError(f"C009 requires the tracked, parsable file {path}; restore it or update the rule's path constants.")
        return source.tree

    @staticmethod
    def _pricebook(table: ast.Dict) -> tuple[dict[str, tuple[str, ...]], dict[str, int]]:
        # Provider member -> priced model keys, plus each provider block's line.
        priced: dict[str, tuple[str, ...]] = {}
        lines: dict[str, int] = {}
        for key, value in zip(table.keys, table.values, strict=True):
            member = RegistryLiterals.provider_member(key)
            if member and isinstance(value, ast.Dict):
                priced[member] = tuple(item for item in (RegistryLiterals.string(model_key) for model_key in value.keys) if item is not None)
                lines[member] = key.lineno if key is not None else table.lineno
        return priced, lines

    @staticmethod
    def _aliases(node: ast.expr | None) -> dict[str, dict[str, str]]:
        # Provider member -> {lowercase alias: canonical model}.
        aliases: dict[str, dict[str, str]] = {}
        if not isinstance(node, ast.Dict):
            return aliases
        for key, value in zip(node.keys, node.values, strict=True):
            member = RegistryLiterals.provider_member(key)
            if member and isinstance(value, ast.Dict):
                aliases[member] = {alias: target for alias, target in ((RegistryLiterals.string(item_key), RegistryLiterals.string(item_value)) for item_key, item_value in zip(value.keys, value.values, strict=True)) if alias is not None and target is not None}
        return aliases

    @staticmethod
    def _defaults(node: ast.Dict, members: dict[str, str], runners: RunnerCatalog) -> list[DefaultModel]:
        # Each default model with its runner type; only text and decision defaults are priced from PROVIDER_PRICING.
        priced_types = {runners.constant(name) for name in _TOKEN_PRICED_RUNNER_CONSTANTS}
        qualified = runners.runner_types("MODEL_PROVIDER_RUNNER_TYPE_MAP")
        by_provider = runners.runner_types("PROVIDER_DEFAULT_RUNNER_TYPE_MAP")
        defaults: list[DefaultModel] = []
        for key, value in zip(node.keys, node.values, strict=True):
            member, model = RegistryLiterals.provider_member(key), RegistryLiterals.string(value)
            if not member or model is None or member not in members:
                continue
            runner_type = qualified.get(f"{members[member]}/{model.lower()}") or by_provider.get(members[member], "")
            if runner_type in priced_types:
                defaults.append(DefaultModel(member=member, value=members[member], model=model, line=key.lineno if key is not None else node.lineno, runner_type=runner_type))
        return defaults

    @staticmethod
    def _catalog_models(runners: RunnerCatalog, default: DefaultModel, lookup: PricingLookup) -> tuple[str, ...]:
        # The provider's other catalogued text models that also resolve to no rate, so the repair prices them in the same edit.
        text = runners.constant("RUNNER_TYPE_TEXT")
        prefix = f"{default.value}/"
        models = (key[len(prefix):] for key, kind in runners.entries("MODEL_PROVIDER_RUNNER_TYPE_MAP").items() if key.lower().startswith(prefix) and kind == text)
        return tuple(sorted(model for model in models if model.lower() != default.model.lower() and not lookup.resolves(default.member, model)))


class DefaultModelPricedRule(Rule):
    """Requires every token-priced provider's default model to resolve in the built-in model pricebook."""

    id = "C009"
    name = "default-model-priced"
    severity = "blocking"
    summary = "Every provider whose default model is billed from token rates (text and decision runners) must have that default resolve in PROVIDER_PRICING, through the same exact, alias, and longest-prefix lookup ModelPricingRegistry.resolve uses. A provider that bills each response with its own reported cost is declared in this rule with that mechanism instead. Otherwise a run on the provider's default model records cost None and the run's usage reports cost_complete=False."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # One finding per unpriced default, anchored at its DEFAULT_PROVIDER_MODELS entry.
        files = {source.rel: source for source in catalog.python_files()}
        return [self._finding(item, files[REGISTRY_FILE]) for item in DefaultPricingAnalyzer().analyze(files)]

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the default, the missing table entry, and the exact pricebook edit plus the vintage bump it requires.
        extra = finding.extra
        member, model, value = extra["member"], extra["model"], extra["value"]
        return Diagnostic(
            what_happened=self._what(finding),
            why_blocked=f"UsageTracker prices every {extra['runner_type']} call with ModelPricingRegistry.resolve(provider, model); for `{value}/{model}` that returns None, so each call on the provider's default model records cost_usd=None and the run's UsageRollup reports cost_complete=False. CostBudgetMiddleware users and the Vidbyte backend wallet, which trusts SDK rates (field-guide vidbyte research-usage-tracking.md: the SDK owns every model rate), then cannot price a run that changed nothing but the provider. The pricing design's table population rule is that every TEXT model in ProviderModelRegistry.DEFAULT_PROVIDER_MODELS is priced (docs/design/agent-usage-pricing.md:149), and the provider-API field guide requires `ModelPricingRegistry.default().resolve(provider, \"<versioned id>\")` to be not None (provider-api-contracts.md, PR #437 comment 4068164391).",
            how_to_fix="\n".join((
                f"1. Open the vendor's own pricing page for `{model}` (not a blog or an aggregator) and read the column headers: input, output, and cached-input rates in USD per 1M tokens, plus any long-context threshold.",
                f"2. In {PRICING_FILE}, {self._placement(extra)} `\"{model}\": ModelPricing(input_per_million=..., output_per_million=..., cache_read_per_million=...)` with a comment line above it giving that pricing-page URL and the date you read it.{self._siblings(extra)}",
                "3. Set PRICING_AS_OF in the same file to that verification date (YYYY-MM-DD), then refresh the vintage lock with `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock`; C010 fails until both are done.",
                f"4. Add a test in tests/test_agent_pricing.py asserting `ModelPricingRegistry.default().resolve(ModelProvider.{member}, \"{model}\")` is not None.",
                f"5. Only if {value} bills each response with a vendor-reported cost (as OpenRouter's usage.cost does), declare it in `_PRICED_PER_RESPONSE` in lint/rules/c009_default_model_priced.py with the parser that reads that cost, instead of steps 1-4.",
            )),
            correct_examples=(f"{PRICING_FILE} ModelProvider.META block - the Meta default muse-spark-1.1 was priced in the same change that added the provider (docs/design/agent-usage-pricing-expansion.md Track B).", f"{PRICING_FILE} ModelProvider.TYPESAFE block - cites the vendor page above the entry and prices the versioned and alias model IDs (PR #437 review).", f"{PRICING_FILE} ModelProvider.MINIMAX block - prices the default MiniMax-M3 with its long-context tier."),
            will_not_work=(f"Adding an empty `ModelProvider.{member}: {{}}` block: an empty table still resolves to None.", "Guessing a rate or copying a similar provider's numbers: a wrong but present rate keeps cost_complete true and is silent (field-guide operation-pricebook-rates.md).", f"Changing DEFAULT_PROVIDER_MODELS[ModelProvider.{member}] to a different model to dodge the finding: it changes which model every caller runs.", "Raising C009's baseline in lint/baseline.json: each finding is a default model whose runs cannot be billed."),
            verify=f"{self.verify_command()} && python lint/run.py --rule C010 && python -m pytest tests/test_agent_pricing.py -q",
        )

    @staticmethod
    def _finding(item: UnpricedDefault, source: SourceFile) -> Finding:
        # Stores every quoted fact, so explain() never re-reads source.
        default = item.default
        return Finding(rule_id=DefaultModelPricedRule.id, rel_path=REGISTRY_FILE, line=default.line, source_line=source.line_at(default.line), symbol=f"{default.member}/{default.model}", extra={"member": default.member, "value": default.value, "model": default.model, "runner_type": default.runner_type, "kind": item.kind, "table_line": str(item.table_line), "provider_line": str(item.provider_line), "priced": ", ".join(item.priced_models), "catalog": ", ".join(f"`{model}`" for model in item.catalog_models)})

    @staticmethod
    def _what(finding: Finding) -> str:
        # Distinguishes a provider with no pricebook block from one whose block misses the default.
        extra = finding.extra
        head = f"{finding.location()} registers `{extra['model']}` as the default {extra['runner_type']} model of ModelProvider.{extra['member']}, but it resolves to no rate."
        if extra["kind"] == _PROVIDER_ABSENT:
            return f"{head} PROVIDER_PRICING ({PRICING_FILE}:{extra['table_line']}) has no ModelProvider.{extra['member']} block at all."
        if not extra["priced"]:
            return f"{head} The ModelProvider.{extra['member']} block ({PRICING_FILE}:{extra['provider_line']}) is empty, and an empty block resolves every model to no rate."
        return f"{head} The ModelProvider.{extra['member']} block ({PRICING_FILE}:{extra['provider_line']}) prices only {extra['priced']}, and neither an exact key, the alias-normalized name, nor a key that is a prefix of `{extra['model']}` matches."

    @staticmethod
    def _siblings(extra: dict[str, str]) -> str:
        # Names the provider's other catalogued text models only when there are some.
        if not extra["catalog"]:
            return ""
        return f" In the same block, also price the provider's other catalogued text models that still resolve to no rate and that page lists ({extra['catalog']}), so callers who pick them are billed too."

    @staticmethod
    def _placement(extra: dict[str, str]) -> str:
        # A missing provider needs a new block; an existing block needs one more key.
        if extra["kind"] == _PROVIDER_ABSENT:
            return f"add a `ModelProvider.{extra['member']}: {{...}}` block to PROVIDER_PRICING (line {extra['table_line']}) containing"
        return f"add to the existing `ModelProvider.{extra['member']}` block (line {extra['provider_line']})"


RULE = DefaultModelPricedRule()
