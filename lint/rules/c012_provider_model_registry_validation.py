"""FILE: lint/rules/c012_provider_model_registry_validation.py

PURPOSE: Detect provider and model fields on configuration records that are never checked against ModelProvider or ProviderModelRegistry, and validated provider fields still typed as a bare str.
ROLE IN CODEBASE: Enforces C012 so a mistyped provider or an uncatalogued model fails when the configuration is built, not mid-run as a provider 400 or a cost of None.
ARCHITECTURE NOTE: Static AST over configuration owners (*Settings, *Config, *Configuration, *Spec, *Descriptor, *Options) and the records their fields embed. A field is proven by ModelProvider(f), a ProviderModelRegistry validation call, a catalog-membership test, or a hand-off to another configuration class or to a same-module helper that itself holds such a proof for its parameter.
FUNCTION INVENTORY: RegistryNames finds registry aliases; OwnerFinder selects owners; FieldCollector lists provider and model fields; ProofIndex records proofs; ValidatorHelpers learns same-module validating helpers; RegistryValidationAnalyzer coordinates; ProviderModelRegistryValidationRule reports.
COMMON MODIFICATION PATTERNS: When ProviderModelRegistry gains a validating method, add it to _PROVIDER_PROOF_METHODS or _MODEL_PROOF_METHODS. Add an _EXEMPT_FIELDS entry only for a field whose vocabulary is owned by another system, with that reason.
WHAT NOT TO DO: Do not import vidbyte, flag provider adapters, runners, usage records, or error packets (they are not configuration owners), accept a non-empty check or a bare isinstance branch as a proof, or exempt a whole module.
KNOWN EDGE CASES: A field typed exactly ModelProvider is trusted to its type and needs no runtime proof. `ModelProvider | str` fields are reported only when unvalidated; their typing belongs to C028. Pydantic, Enum, TypedDict, Protocol, and NamedTuple classes are skipped. A proof in any method counts, because __post_init__ often delegates to _validate helpers.
RELATED DOCS: docs/design/lint-sdk-pricing-usage-contracts.md; vidbyte/lib/registries/models.py (ProviderModelRegistry); AGENTS.md (closed-set fields use an enum).
TESTS: python lint/run.py --rule C012; fixture and mutation results are recorded in the S2 pull request body.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

_OWNER_SUFFIX = re.compile(r"(Settings|Config|Configuration|Spec|Descriptor|Options)$")
_SKIPPED_BASES = frozenset({"BaseModel", "Enum", "StrEnum", "IntEnum", "Flag", "IntFlag", "TypedDict", "Protocol", "NamedTuple"})
_PROVIDER_FIELD = re.compile(r"^(?:provider|.+_provider)$")
_MODEL_FIELD = re.compile(r"^(?:model|model_name|models|.+_model|.+_model_name)$")
_REGISTRY = "ProviderModelRegistry"
_ENUM = "ModelProvider"
_PROVIDER_PROOF_METHODS = frozenset({"validate_provider", "_require_provider", "resolve_provider", "is_valid_provider", "get_api_key_env_var", "get_default_endpoint", "resolve_api_key", "resolve_endpoint", "normalize_model", "is_supported_model", "validate_provider_models_map"})
_MODEL_PROOF_METHODS = frozenset({"validate_model", "validate_provider_model_pair", "is_supported_model", "validate_provider_models_map", "provider_for_model"})
_MODEL_CATALOGS = frozenset({"known_models", "models_for_provider", "get_supported_models"})
_EXEMPT_FIELDS = {
    ("vidbyte/lib/dataclasses/codex.py", "CodexThreadSettings", "model_provider"): "Codex CLI vocabulary: model_provider names an entry in the user's Codex config model_providers table (custom providers included), not an SDK ModelProvider (vidbyte/agents/codex/metrics.py records nothing for a custom one).",
    ("vidbyte/lib/dataclasses/codex.py", "CodexThreadSettings", "model"): "Codex CLI vocabulary: the Codex CLI resolves this model against the thread's model_provider, which may be a custom provider the SDK catalog cannot know.",
    ("vidbyte/lib/dataclasses/codex.py", "CodexTurnSettings", "model"): "Codex CLI vocabulary: a per-turn override passed through to the Codex CLI unchanged, resolved against the thread's model_provider.",
    ("vidbyte/lib/dataclasses/codex.py", "CodexSubagentSettings", "default_model"): "Codex CLI vocabulary: the agents.default_model key of the Codex config table, resolved by the Codex CLI.",
}
_UNVALIDATED_PROVIDER = "unvalidated-provider"
_UNVALIDATED_MODEL = "unvalidated-model"
_STRING_PROVIDER = "string-typed-provider"
_PROVIDER = "provider"
_MODEL = "model"


@dataclass(frozen=True, slots=True)
class IdentityField:
    """One provider or model field of a configuration owner."""

    source: SourceFile
    owner: ast.ClassDef
    name: str
    line: int
    role: str
    annotation: str
    shape: str

    def __post_init__(self) -> None:
        # The role picks the accepted proofs and the repair; the shape picks where the check goes.
        if self.role not in {_PROVIDER, _MODEL}:
            raise ValueError(f"IdentityField.role must be {_PROVIDER!r} or {_MODEL!r}, got {self.role!r}.")
        if self.shape not in {"dataclass", "init"}:
            raise ValueError(f"IdentityField.shape must be 'dataclass' or 'init', got {self.shape!r}.")
        if not self.name or self.line < 1 or not self.annotation:
            raise ValueError(f"IdentityField needs a name, a positive line, and an annotation, got {self.name!r}:{self.line}:{self.annotation!r}.")


@dataclass(frozen=True, slots=True)
class FieldGap:
    """A field that fails C012, plus the facts its repair needs."""

    field: IdentityField
    kind: str
    sibling_provider: str
    validator_home: str

    def __post_init__(self) -> None:
        # The kind selects the diagnostic; the validator home names where the check goes.
        if self.kind not in {_UNVALIDATED_PROVIDER, _UNVALIDATED_MODEL, _STRING_PROVIDER}:
            raise ValueError(f"FieldGap.kind {self.kind!r} is not a C012 kind.")
        if not self.validator_home:
            raise ValueError("FieldGap.validator_home must name the method that should hold the check.")


class RegistryNames:
    """Finds the local names one module uses for ProviderModelRegistry and ModelProvider."""

    @staticmethod
    def aliases(tree: ast.Module, canonical: str) -> frozenset[str]:
        # The canonical name plus `import ... as X` and module-level `X = canonical` rebindings.
        names = {canonical}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.update(alias.asname for alias in node.names if alias.name == canonical and alias.asname)
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id == canonical:
                names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        return frozenset(names)

    @staticmethod
    def last_name(node: ast.AST) -> str:
        # `a.b.c` -> "c"; `c` -> "c"; anything else -> "".
        if isinstance(node, ast.Attribute):
            return node.attr
        return node.id if isinstance(node, ast.Name) else ""


class OwnerFinder:
    """Selects configuration owners and the records their fields embed."""

    def find(self, files: list[SourceFile]) -> list[tuple[SourceFile, ast.ClassDef]]:
        # Start from classes named like configuration.
        classes = {node.name: (source, node) for source in files if source.tree is not None for node in ast.walk(source.tree) if isinstance(node, ast.ClassDef) and not self._skipped(node)}
        selected = {name for name in classes if _OWNER_SUFFIX.search(name)}

        # Follow their field and __init__ annotations to the in-repo records they embed (FallbackModel, ActorRuntime, ...).
        frontier = list(selected)
        while frontier:
            _source, node = classes[frontier.pop()]
            init = next((item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
            annotations = [item.annotation for item in node.body if isinstance(item, ast.AnnAssign)] + [argument.annotation for argument in ([*init.args.args, *init.args.kwonlyargs] if init is not None else []) if argument.annotation is not None]
            # A `type[X]` annotation holds a class to instantiate later, not an embedded record.
            classes_only = {id(part) for annotation in annotations for outer in ast.walk(annotation) if isinstance(outer, ast.Subscript) and RegistryNames.last_name(outer.value) in {"type", "Type"} for part in ast.walk(outer.slice)}
            embedded = {part.id for annotation in annotations for part in ast.walk(annotation) if isinstance(part, ast.Name) and id(part) not in classes_only and part.id in classes and self._is_record(classes[part.id][1])} - selected
            selected |= embedded
            frontier.extend(embedded)
        return sorted((classes[name] for name in selected), key=lambda pair: (pair[0].rel, pair[1].lineno))

    @staticmethod
    def _skipped(node: ast.ClassDef) -> bool:
        # Pydantic models, enums, and typing shells either validate themselves or hold no runtime value.
        return bool({RegistryNames.last_name(base.value if isinstance(base, ast.Subscript) else base) for base in node.bases} & _SKIPPED_BASES)

    @staticmethod
    def _is_record(node: ast.ClassDef) -> bool:
        # An embedded class is configuration when it is a dataclass or a plain class with no public behavior;
        # components a settings field merely references (BaseAgent, Tools, AgentMiddleware) are not.
        if any(RegistryNames.last_name(item.func if isinstance(item, ast.Call) else item) == "dataclass" for item in node.decorator_list):
            return True
        return not any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_") for item in node.body)


class FieldCollector:
    """Lists the provider and model fields one owner declares."""

    def collect(self, source: SourceFile, owner: ast.ClassDef) -> list[IdentityField]:
        # Dataclass fields, or the __init__ parameters of a plain class, whose name and type mark a provider or model identity.
        dataclass_shape = any(RegistryNames.last_name(item.func if isinstance(item, ast.Call) else item) == "dataclass" for item in owner.decorator_list)
        if dataclass_shape:
            candidates = [(item.target.id, item.annotation, item.lineno) for item in owner.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and "ClassVar" not in ast.unparse(item.annotation)]
        else:
            init = next((item for item in owner.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
            candidates = [(argument.arg, argument.annotation, argument.lineno) for argument in ([*init.args.args, *init.args.kwonlyargs] if init is not None else []) if argument.annotation is not None]
        fields: list[IdentityField] = []
        for name, annotation, line in candidates:
            role = self._role(name, ast.unparse(annotation))
            if role and (source.rel, owner.name, name) not in _EXEMPT_FIELDS:
                fields.append(IdentityField(source=source, owner=owner, name=name, line=line, role=role, annotation=ast.unparse(annotation), shape="dataclass" if dataclass_shape else "init"))
        return fields

    @staticmethod
    def _role(name: str, annotation: str) -> str:
        # A provider field holds a str or ModelProvider; a model field holds a str or a collection of str.
        text = annotation.replace(" ", "").strip("'\"")
        if _PROVIDER_FIELD.match(name) and re.search(r"\b(str|ModelProvider)\b", text):
            return _PROVIDER
        if _MODEL_FIELD.match(name) and re.search(r"\bstr\b", text) and not re.search(r"\b(dict|Mapping)\b", text):
            return _MODEL
        return ""


class ValidatorHelpers:
    """Learns same-module functions and methods that validate a provider or model parameter."""

    def learn(self, tree: ast.Module, registry: frozenset[str], enum: frozenset[str]) -> dict[str, frozenset[str]]:
        # Helper name -> the roles it proves for its own parameters.
        helpers: dict[str, frozenset[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parameters = {argument.arg for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)} - {"self", "cls"}
                roles = frozenset(role for role in (_PROVIDER, _MODEL) if ProofIndex.direct_proof(node, parameters, role, registry, enum))
                if roles:
                    helpers[node.name] = roles | helpers.get(node.name, frozenset())
        return helpers


class ProofIndex:
    """Decides whether one owner proves one field against ModelProvider or ProviderModelRegistry."""

    def __init__(self, registry: frozenset[str], enum: frozenset[str], helpers: dict[str, frozenset[str]]) -> None:
        # Binds the module's registry and enum aliases and its validating helpers.
        self.registry = registry
        self.enum = enum
        self.helpers = helpers

    def proven(self, field: IdentityField) -> bool:
        # Any method may hold the proof: a direct check, or a hand-off to a validating helper or another configuration class.
        names = self._names(field)
        for method in (item for item in field.owner.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))):
            scoped = names | self._method_aliases(method, field, names)
            if self.direct_proof(method, scoped, field.role, self.registry, self.enum) or self._handoff(method, scoped, field.role):
                return True
        return False

    @staticmethod
    def _names(field: IdentityField) -> set[str]:
        # A field is known as its bare name (an __init__ parameter) and as self.<name>.
        return {field.name, f"self.{field.name}"}

    @staticmethod
    def _method_aliases(method: ast.FunctionDef | ast.AsyncFunctionDef, field: IdentityField, names: set[str]) -> set[str]:
        # `value = self.provider`, a `for name in ("provider", ...)` sweep over getattr(self, name), and a pydantic-style validator's parameter.
        aliases: set[str] = set()
        for node in ast.walk(method):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and isinstance(node.iter, (ast.Tuple, ast.List, ast.Set)) and any(isinstance(item, ast.Constant) and item.value == field.name for item in node.iter.elts):
                aliases.add(f"getattr(self, {node.target.id})")
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and ast.unparse(node.value) in names | aliases:
                aliases.add(node.targets[0].id)
        for decorator in method.decorator_list:
            if isinstance(decorator, ast.Call) and RegistryNames.last_name(decorator.func) in {"field_validator", "validator"} and any(isinstance(item, ast.Constant) and item.value == field.name for item in decorator.args):
                aliases.update(argument.arg for argument in method.args.args[1:])
        return aliases | {f"getattr(self, {name!r})" for name in (field.name,)}

    @staticmethod
    def direct_proof(function: ast.FunctionDef | ast.AsyncFunctionDef, names: set[str], role: str, registry: frozenset[str], enum: frozenset[str]) -> bool:
        # ModelProvider(f) for providers; a registry validation call for either role; catalog membership for models.
        # isinstance(f, ModelProvider) alone is not a proof: it usually only picks a branch (BaseAgent uses it to read .value).
        methods = _PROVIDER_PROOF_METHODS if role == _PROVIDER else _MODEL_PROOF_METHODS
        for node in ast.walk(function):
            mentions = isinstance(node, (ast.Call, ast.Compare)) and any(ast.unparse(part) in names for part in ast.walk(node) if isinstance(part, (ast.Name, ast.Attribute, ast.Call)))
            if not mentions:
                continue
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and RegistryNames.last_name(node.func.value) in registry and node.func.attr in methods:
                return True
            if role == _PROVIDER and isinstance(node, ast.Call) and RegistryNames.last_name(node.func) in enum and node.args:
                return True
            if role == _MODEL and isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops) and any(isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute) and part.func.attr in _MODEL_CATALOGS and RegistryNames.last_name(part.func.value) in registry for comparator in node.comparators for part in ast.walk(comparator)):
                return True
        return False

    def _handoff(self, method: ast.FunctionDef | ast.AsyncFunctionDef, names: set[str], role: str) -> bool:
        # Passing the field to a validating helper of this module, or to another configuration class's constructor.
        for node in ast.walk(method):
            if not isinstance(node, ast.Call):
                continue
            callee = RegistryNames.last_name(node.func)
            validates = role in self.helpers.get(callee, frozenset()) or (bool(_OWNER_SUFFIX.search(callee)) and callee[:1].isupper())
            if validates and any(ast.unparse(part) in names for argument in (*node.args, *(keyword.value for keyword in node.keywords)) for part in ast.walk(argument)):
                return True
        return False


class RegistryValidationAnalyzer:
    """Finds every configuration provider or model field without a registry proof, and validated providers typed as str."""

    def analyze(self, files: list[SourceFile]) -> list[FieldGap]:
        # Select owners across the package, then judge each owner's identity fields with its module's proofs.
        owners = OwnerFinder().find(files)
        collector = FieldCollector()
        gaps: list[FieldGap] = []
        indexes: dict[str, ProofIndex] = {}
        for source, owner in owners:
            if source.rel not in indexes and source.tree is not None:
                registry, enum = RegistryNames.aliases(source.tree, _REGISTRY), RegistryNames.aliases(source.tree, _ENUM)
                indexes[source.rel] = ProofIndex(registry, enum, ValidatorHelpers().learn(source.tree, registry, enum))
            fields = collector.collect(source, owner)
            providers = [field.name for field in fields if field.role == _PROVIDER]
            for field in fields:
                # A field typed exactly ModelProvider is enforced by its type; every other identity field needs a runtime proof.
                if field.role == _PROVIDER and not re.search(r"\bstr\b", field.annotation):
                    continue
                proven = indexes[source.rel].proven(field)
                kind = self._kind(field, proven)
                if kind:
                    gaps.append(FieldGap(field=field, kind=kind, sibling_provider=providers[0] if providers and field.role == _MODEL else "", validator_home=self._home(owner, field)))
        return gaps

    @staticmethod
    def _kind(field: IdentityField, proven: bool) -> str:
        # Unproven fields are unvalidated; a proven provider still typed as a bare str should become ModelProvider.
        if not proven:
            return _UNVALIDATED_PROVIDER if field.role == _PROVIDER else _UNVALIDATED_MODEL
        bare = field.annotation.replace(" ", "") in {"str", "str|None", "None|str", "Optional[str]"}
        return _STRING_PROVIDER if field.role == _PROVIDER and bare else ""

    @staticmethod
    def _home(owner: ast.ClassDef, field: IdentityField) -> str:
        # The method that should hold the check: an existing __post_init__/_validate/__init__, else a new __post_init__ or __init__.
        methods = {item.name for item in owner.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ("__post_init__", "_validate", "validate", "__init__"):
            if name in methods:
                return f"{owner.name}.{name}"
        return f"{owner.name}.__post_init__" if field.shape == "dataclass" else f"{owner.name}.__init__"


class ProviderModelRegistryValidationRule(Rule):
    """Requires configuration provider and model fields to be validated against ModelProvider and ProviderModelRegistry."""

    id = "C012"
    name = "provider-model-registry-validation"
    severity = "blocking"
    summary = "A provider or model field on a configuration record (a *Settings, *Config, *Configuration, *Spec, *Descriptor, or *Options class, or a record one of them embeds) is checked when the record is built: a provider with ModelProvider(value) or ProviderModelRegistry.validate_provider, a model with ProviderModelRegistry.validate_model or validate_provider_model_pair, directly or through a validating helper or another configuration class. A provider that is validated but still typed as a bare str is typed ModelProvider instead. Fields whose vocabulary belongs to another system (the Codex CLI) are exempt by name."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # One finding per field, anchored at its declaration.
        return [self._finding(gap) for gap in RegistryValidationAnalyzer().analyze(list(catalog.python_files()))]

    def explain(self, finding: Finding) -> Diagnostic:
        # Unvalidated fields get the check; string-typed providers get the enum type.
        extra = finding.extra
        if extra["kind"] == _STRING_PROVIDER:
            return self._string_provider(finding)
        return Diagnostic(
            what_happened=self._what(finding),
            why_blocked="A provider or model string that is never checked lets a typo or an uncatalogued model pass construction and fail later: as a provider 400 in the middle of a run, as a silent fallback to another model, or as cost None because no rate matches. Review has asked for this check repeatedly: PR #339 comment 3847625074 (\"models should be validated against the models that we have offered\"), PR #308 comment 3642989701 (\"provider and model strings here have no validation\"), PR #299 comment 3635769007 (\"matches out model registry\"), and PR #348 comment 3849882841 (\"enums for providers/models\"). ProviderModelRegistry (vidbyte/lib/registries/models.py) exists so the check happens once, where the record is built.",
            how_to_fix=self._repair(extra),
            correct_examples=("vidbyte/lib/dataclasses/agent_descriptor.py AgentDescriptor._validate_provider_model - checks provider with ModelProvider(...) and model_name with ProviderModelRegistry.validate_model when the descriptor is built, naming the field in each error.", "vidbyte/context/algorithms/multi_provider_agentic_grader.py MultiProviderAgenticGraderAlgorithm.__post_init__ - validates grader_provider and grader_model with ProviderModelRegistry before any run starts.", "vidbyte/lib/registries/models.py ProviderModelRegistry.validate_provider_model_pair - one call that rejects an uncatalogued model and a model registered under a different provider."),
            will_not_work=("Checking only that the string is non-empty: an empty check accepts every typo.", "Validating at the first call site instead of in the record: every other construction path stays unchecked.", f"Adding the field to _EXEMPT_FIELDS in lint/rules/c012_provider_model_registry_validation.py: that table is only for vocabularies owned by another system, such as the Codex CLI.", "Raising C012's baseline in lint/baseline.json: each finding is a configuration field that accepts any string."),
            verify=f"{self.verify_command()} && python lint/run.py --rule S014",
        )

    @staticmethod
    def _finding(gap: FieldGap) -> Finding:
        # Stores every quoted fact so explain() never re-reads source.
        field = gap.field
        return Finding(rule_id=ProviderModelRegistryValidationRule.id, rel_path=field.source.rel, line=field.line, source_line=field.source.line_at(field.line), symbol=f"{field.owner.name}.{field.name}", extra={"kind": gap.kind, "owner": field.owner.name, "field": field.name, "role": field.role, "annotation": field.annotation, "shape": field.shape, "sibling_provider": gap.sibling_provider, "home": gap.validator_home})

    @staticmethod
    def _what(finding: Finding) -> str:
        # Names the field, its type, and the fact that no method checks it against the registry.
        extra = finding.extra
        kind = "provider" if extra["role"] == _PROVIDER else "model"
        where = "dataclass field" if extra["shape"] == "dataclass" else "__init__ parameter"
        return f"{finding.location()} `{extra['owner']}.{extra['field']}: {extra['annotation']}` is a {kind} {where}, but no method of {extra['owner']} checks it against {'ModelProvider or ProviderModelRegistry' if kind == 'provider' else 'the ProviderModelRegistry model catalog'}, so any string is accepted."

    @staticmethod
    def _repair(extra: dict[str, str]) -> str:
        # Puts the right check in the owner's validation method, naming the sibling provider when there is one.
        target = extra["field"] if extra["home"].endswith(".__init__") and extra["shape"] == "init" else f"self.{extra['field']}"
        collection = bool(re.search(r"\b(Sequence|tuple|list|set|frozenset|Iterable)\b", extra["annotation"]))
        value = "entry" if collection else target
        if extra["role"] == _PROVIDER:
            check = f"coerce it with `ModelProvider({target})` (store the enum, and raise ConfigurationError naming `{extra['field']}` and ProviderModelRegistry.get_supported_providers() when the ValueError fires), or call `ProviderModelRegistry.validate_provider({target})`"
            typing = f"\n3. Change the annotation `{extra['annotation']}` to `ModelProvider` (or `ModelProvider | None` if the field is optional) once the value is coerced, so readers no longer re-normalize the string."
        else:
            sibling = extra["sibling_provider"] if target == extra["field"] else f"self.{extra['sibling_provider']}"
            call = f"`ProviderModelRegistry.validate_provider_model_pair({sibling}, {value})`, which also rejects a model registered under a different provider" if extra["sibling_provider"] else f"`ProviderModelRegistry.validate_model({value})`"
            single = " (treat a bare string as a one-entry list)" if re.match(r"\s*str\s*\|", extra["annotation"]) else ""
            check = f"for each string `entry` in `{target}`{single}, call {call}" if collection else f"call {call}"
            typing = ""
        optional = " Skip the check only when the value is None or empty and the field's documented default means \"use the provider default\"."
        return f"1. In {extra['home']}, {check}.{optional}\n2. Add a test constructing {extra['owner']} with a misspelled value and asserting ConfigurationError names `{extra['field']}`.{typing}"

    @staticmethod
    def _string_provider(finding: Finding) -> Diagnostic:
        # The value is checked, but the str annotation still lets every reader treat it as free text.
        extra = finding.extra
        return Diagnostic(
            what_happened=f"{finding.location()} `{extra['owner']}.{extra['field']}: {extra['annotation']}` is validated against the provider registry, but it is still typed as a bare str.",
            why_blocked="AGENTS.md: \"Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain str.\" The provider set is the ModelProvider enum, and PR #348 comment 3849882841 asked for \"enums for providers/models\". A str-typed provider makes every reader re-normalize casing and whitespace, which is how a raw string silently misses a price lookup (ProviderModelRegistry.resolve_provider comment).",
            how_to_fix=f"1. Change the annotation to `ModelProvider` (or `ModelProvider | None`).\n2. In {extra['home']}, store the coerced enum (`ModelProvider(value)`, or `object.__setattr__(self, \"{extra['field']}\", ModelProvider(self.{extra['field']}))` in a frozen dataclass) instead of only checking the string.\n3. Update readers that call `.lower()` or compare `{extra['field']}` with string literals to compare with ModelProvider members.",
            correct_examples=("vidbyte/agents/jev/settings.py JevAgentSettings.__post_init__ - coerces provider once and stores the ModelProvider member with object.__setattr__, so every reader gets the enum.",),
            will_not_work=("Typing it `ModelProvider | str`: the union keeps the free-text reading and C028 flags undocumented unions.", "Raising C012's baseline in lint/baseline.json: each finding is a closed-set field still typed as free text."),
            verify=f"python lint/run.py --rule C012 && python lint/run.py --rule S014",
        )


RULE = ProviderModelRegistryValidationRule()
