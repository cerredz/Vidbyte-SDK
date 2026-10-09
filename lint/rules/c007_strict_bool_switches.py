"""FILE: lint/rules/c007_strict_bool_switches.py

PURPOSE: Detect bool switches on configuration classes that are never proven to be real bools at construction.
ROLE IN CODEBASE: Enforces C007 so a configured "false" string, 0, or 1 can never flip a settings switch through truthiness.
ARCHITECTURE NOTE: Static AST over *Settings/*Config/*Configuration/*Policy/*Options classes, plus top-level classes of config.py/configs.py/settings.py modules whose constructor raises ConfigurationError. A switch is proven by isinstance(x, bool) or type(x) is bool in any method, a bool-validator call, or a hand-off to another configuration class.
FUNCTION INVENTORY: ConfigurationClassFinder selects owners; SwitchCollector lists bool members; StrictnessIndex records proofs; StrictBoolSwitchAnalyzer coordinates; StrictBoolSwitchesRule reports.
COMMON MODIFICATION PATTERNS: Widen the owner suffixes or the accepted proofs together with the diagnostic, then rerun C007 and its scratch fixtures.
WHAT NOT TO DO: Do not import SDK modules, accept bool(x) as a proof, or flag result records and component constructors outside the configuration suffixes and config modules.
KNOWN EDGE CASES: Pydantic, Enum, TypedDict, Protocol, and NamedTuple classes are skipped because they parse bools themselves or hold no runtime value. Unused plain __init__ switches are not reported. A class in a config.py/configs.py/settings.py module counts only when its own constructor raises ConfigurationError, so translators and loaders there stay out of scope. A hand-off to another configuration class trusts that class, which C007 checks separately.
RELATED DOCS: docs/design/lint-sdk-settings-validation.md; vidbyte/agents/settings/fallback.py (@intent fallback-enabled-is-not-truthiness)
TESTS: python lint/run.py --rule C007; fixture and mutation results are recorded in the S1 pull request body.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

_OWNER_SUFFIX = re.compile(r"(Settings|Config|Configuration|Policy|Options)$")
_CONFIG_MODULES = frozenset({"config.py", "configs.py", "settings.py"})
_CONSTRUCTORS = frozenset({"__init__", "__post_init__"})
_SKIPPED_BASES = frozenset({"BaseModel", "Enum", "StrEnum", "IntEnum", "Flag", "IntFlag", "TypedDict", "Protocol", "NamedTuple"})
_BOOL_ANNOTATIONS = frozenset({"bool", "bool|None", "None|bool", "Optional[bool]", "typing.Optional[bool]"})
_BOOL_VALIDATOR = re.compile(r"^_?(require|validate|validated|ensure|check|coerce|normalize|resolve|is)_(strict_)?(bool|boolean|flag|switch)(_|$)|^_?(strict_)?(bool|boolean)_(flag|switch|value)$")
_VALIDATION_METHODS = ("__post_init__", "_validate", "__init__")
_DEFAULT_ERROR = "ConfigurationError"
_DATACLASS = "dataclass"
_PLAIN = "plain"


@dataclass(frozen=True, slots=True)
class BoolSwitch:
    """One bool-annotated member of a configuration class: a dataclass field or a used plain __init__ parameter."""

    source: SourceFile
    owner: ast.ClassDef
    name: str
    line: int
    shape: str
    usage: str
    optional: bool

    def __post_init__(self) -> None:
        # The shape decides the repair text, and the usage is quoted in the diagnostic.
        if self.shape not in {_DATACLASS, _PLAIN}:
            raise ValueError(f"BoolSwitch.shape must be {_DATACLASS!r} or {_PLAIN!r}, got {self.shape!r}.")
        if not self.name or self.line < 1 or not self.usage:
            raise ValueError(f"BoolSwitch needs a name, a positive line, and a usage, got {self.name!r}:{self.line}:{self.usage!r}.")


class LiteralName:
    """Reads identifiers and literal string tuples without executing anything."""

    @staticmethod
    def of(node: ast.AST) -> str:
        # Returns the last name of a Name or Attribute, else an empty string.
        return node.attr if isinstance(node, ast.Attribute) else (node.id if isinstance(node, ast.Name) else "")

    @staticmethod
    def strings(node: ast.AST) -> tuple[str, ...]:
        # Returns the strings of a literal tuple/list/set of string constants, else an empty tuple.
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)) and node.elts and all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.elts):
            return tuple(item.value for item in node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str))
        return ()

    @classmethod
    def module_tuples(cls, tree: ast.Module) -> dict[str, tuple[str, ...]]:
        # Module-level NAME = ("a", "b") constants, which field sweeps iterate over.
        tuples: dict[str, tuple[str, ...]] = {}
        for node in tree.body:
            target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else (node.target if isinstance(node, ast.AnnAssign) else None)
            value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if isinstance(target, ast.Name) and value is not None and cls.strings(value):
                tuples[target.id] = cls.strings(value)
        return tuples


class ConfigurationClassFinder:
    """Selects the classes that hold configuration: by their name, or by their module and their constructor's error."""

    def find(self, source: SourceFile) -> list[ast.ClassDef]:
        # Owners end in Settings/Config/Configuration/Policy/Options, or sit at the top of a config/configs/settings module
        # and raise ConfigurationError from their constructor (ActorRuntime); models, enums, and typing shells are skipped.
        if source.tree is None:
            return []
        owners = [node for node in ast.walk(source.tree) if isinstance(node, ast.ClassDef) and _OWNER_SUFFIX.search(node.name) and not self._skipped(node)]
        if source.rel.rsplit("/", 1)[-1] in _CONFIG_MODULES:
            owners += [node for node in source.tree.body if isinstance(node, ast.ClassDef) and node not in owners and not self._skipped(node) and self._rejects_configuration(node)]
        return owners

    @staticmethod
    def _rejects_configuration(node: ast.ClassDef) -> bool:
        # A constructor that raises ConfigurationError declares its arguments configuration, whatever the class is called.
        constructors = [item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in _CONSTRUCTORS]
        return any(isinstance(item, ast.Raise) and item.exc is not None and LiteralName.of(item.exc.func if isinstance(item.exc, ast.Call) else item.exc) == _DEFAULT_ERROR for function in constructors for item in ast.walk(function))

    @staticmethod
    def _skipped(node: ast.ClassDef) -> bool:
        # Pydantic parses "false" correctly, and enums or typing shells hold no runtime value to check.
        return bool({LiteralName.of(base.value if isinstance(base, ast.Subscript) else base) for base in node.bases} & _SKIPPED_BASES)


class SwitchCollector:
    """Lists the bool switches one configuration class declares, with how each is used."""

    def collect(self, source: SourceFile, owner: ast.ClassDef) -> list[BoolSwitch]:
        # Dataclasses declare switches as fields; plain classes take them as __init__ parameters.
        if self.is_dataclass(owner):
            return [BoolSwitch(source=source, owner=owner, name=item.target.id, line=item.lineno, shape=_DATACLASS, usage="declared as a dataclass field", optional=self._optional(item.annotation)) for item in owner.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and self._is_bool(item.annotation)]
        init = next((item for item in owner.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
        if init is None:
            return []
        switches: list[BoolSwitch] = []
        for argument in [*init.args.posonlyargs, *init.args.args, *init.args.kwonlyargs]:
            usage = self._usage(init, argument.arg) if self._is_bool(argument.annotation) else ""
            if usage:
                switches.append(BoolSwitch(source=source, owner=owner, name=argument.arg, line=argument.lineno, shape=_PLAIN, usage=usage, optional=self._optional(argument.annotation)))
        return switches

    @staticmethod
    def is_dataclass(owner: ast.ClassDef) -> bool:
        # Accepts @dataclass, @dataclass(...), and @dataclasses.dataclass(...).
        return any(LiteralName.of(item.func if isinstance(item, ast.Call) else item) == "dataclass" for item in owner.decorator_list)

    @staticmethod
    def _is_bool(annotation: ast.expr | None) -> bool:
        # bool, bool | None, and Optional[bool]; string annotations are unquoted first.
        if annotation is None:
            return False
        return ast.unparse(annotation).replace(" ", "").strip("'\"") in _BOOL_ANNOTATIONS

    @staticmethod
    def _optional(annotation: ast.expr | None) -> bool:
        # bool | None and Optional[bool] switches legitimately hold None, so their check must allow it.
        return annotation is not None and ("None" in ast.unparse(annotation) or "Optional" in ast.unparse(annotation))

    @staticmethod
    def _usage(init: ast.FunctionDef, name: str) -> str:
        # Describes the first truthiness-sensitive use: a raw store, a bool() coercion, or another read.
        for node in ast.walk(init):
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Attribute) for target in node.targets):
                if isinstance(node.value, ast.Name) and node.value.id == name:
                    return f"stored as given at line {node.lineno}: `{ast.unparse(node)}`"
                if isinstance(node.value, ast.Call) and LiteralName.of(node.value.func) == "bool" and node.value.args and isinstance(node.value.args[0], ast.Name) and node.value.args[0].id == name:
                    return f"coerced with bool() at line {node.lineno}: `{ast.unparse(node)}`, which turns \"false\" into True"
        reads = sorted(node.lineno for node in ast.walk(init) if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load))
        return f"read at line {reads[0]} without a type check" if reads else ""


class StrictnessIndex:
    """Records which switches of one class are proven to be real bools."""

    def __init__(self, module_tuples: dict[str, tuple[str, ...]]) -> None:
        # Module-level field-name tuples let a `for name in _BOOL_FIELDS` sweep count as a proof.
        self.module_tuples = module_tuples

    def proven(self, owner: ast.ClassDef, switch: BoolSwitch) -> bool:
        # Any method may hold the proof, because __post_init__ and __init__ often delegate to _validate helpers.
        names = self._names_for(owner, switch)
        for method in (item for item in owner.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))):
            aliases = names | self._aliases(method, names)
            for node in ast.walk(method):
                if isinstance(node, ast.Call) and (self._is_bool_isinstance(node, aliases) or self._is_handoff(node, aliases)):
                    return True
                if isinstance(node, ast.Compare) and self._is_exact_type(node, aliases):
                    return True
        return False

    @staticmethod
    def _names_for(owner: ast.ClassDef, switch: BoolSwitch) -> set[str]:
        # A plain switch is known by its parameter name and every self attribute it is stored under.
        names = {switch.name, f"self.{switch.name}"}
        init = next((item for item in owner.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"), None)
        for node in ast.walk(init) if init is not None and switch.shape == _PLAIN else ():
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id == switch.name:
                names.update(ast.unparse(target) for target in node.targets if isinstance(target, ast.Attribute))
        return names

    def _aliases(self, method: ast.FunctionDef | ast.AsyncFunctionDef, names: set[str]) -> set[str]:
        # Follows `value = self.flag` and `for name in ("flag", ...): value = getattr(self, name)` sweeps.
        aliases: set[str] = set()
        fields = {name.removeprefix("self.") for name in names}
        for node in ast.walk(method):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                swept = LiteralName.strings(node.iter) or (self.module_tuples.get(node.iter.id, ()) if isinstance(node.iter, ast.Name) else ())
                if fields & set(swept):
                    aliases.add(f"getattr(self, {node.target.id})")
        for node in sorted((item for item in ast.walk(method) if isinstance(item, ast.Assign)), key=lambda item: item.lineno):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and ast.unparse(node.value) in names | aliases:
                aliases.add(node.targets[0].id)
        return aliases

    @staticmethod
    def _is_bool_isinstance(node: ast.Call, names: set[str]) -> bool:
        # isinstance(<switch>, bool) is the type check that rejects "false", 0, and 1.
        return LiteralName.of(node.func) == "isinstance" and len(node.args) == 2 and ast.unparse(node.args[0]) in names and isinstance(node.args[1], ast.Name) and node.args[1].id == "bool"

    @staticmethod
    def _is_exact_type(node: ast.Compare, names: set[str]) -> bool:
        # type(<switch>) is bool / is not bool / == bool / != bool is an equally strict proof.
        left = node.left
        is_type_call = isinstance(left, ast.Call) and LiteralName.of(left.func) == "type" and len(left.args) == 1 and ast.unparse(left.args[0]) in names
        return is_type_call and len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot, ast.Eq, ast.NotEq)) and isinstance(node.comparators[0], ast.Name) and node.comparators[0].id == "bool"

    @staticmethod
    def _is_handoff(node: ast.Call, names: set[str]) -> bool:
        # A bool-validator call, or construction of another configuration class, owns the check for its arguments.
        callee = LiteralName.of(node.func)
        if not (_BOOL_VALIDATOR.match(callee) or _OWNER_SUFFIX.search(callee)):
            return False
        return any(ast.unparse(item) in names for item in [*node.args, *(keyword.value for keyword in node.keywords)])


@dataclass(frozen=True, slots=True)
class UncheckedSwitch:
    """A switch with no proof, plus the facts the repair needs about its class."""

    switch: BoolSwitch
    siblings: tuple[str, ...]
    optional: tuple[str, ...]
    home: str
    home_exists: bool
    error: str

    def __post_init__(self) -> None:
        # The repair names the validating method and the exception type, so both must be known.
        if not self.home or not self.error:
            raise ValueError(f"UncheckedSwitch needs a home method and an error type, got {self.home!r} and {self.error!r}.")
        if self.switch.name in self.siblings:
            raise ValueError(f"UncheckedSwitch.siblings must not repeat the switch itself ({self.switch.name!r}).")


class StrictBoolSwitchAnalyzer:
    """Finds every configuration switch that is never proven to be a real bool."""

    def analyze(self, catalog: SourceCatalog) -> list[UncheckedSwitch]:
        # Select configuration classes, list their bool switches, and keep the ones with no proof.
        finder = ConfigurationClassFinder()
        collector = SwitchCollector()
        unchecked: list[UncheckedSwitch] = []
        for source in catalog.python_files():
            if source.tree is None:
                continue
            strictness = StrictnessIndex(LiteralName.module_tuples(source.tree))
            for owner in finder.find(source):
                unproven = [switch for switch in collector.collect(source, owner) if not strictness.proven(owner, switch)]
                home, home_exists = self._home(owner)
                optional = tuple(item.name for item in unproven if item.optional)
                unchecked.extend(UncheckedSwitch(switch=switch, siblings=tuple(item.name for item in unproven if item is not switch), optional=optional, home=home, home_exists=home_exists, error=self._error(owner)) for switch in unproven)
        return unchecked

    @staticmethod
    def _home(owner: ast.ClassDef) -> tuple[str, bool]:
        # The method that already validates construction input is where the check belongs; a dataclass without one gets __post_init__.
        methods = {item.name for item in owner.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
        existing = next((name for name in _VALIDATION_METHODS if name in methods), "")
        if existing:
            return existing, True
        return ("__post_init__" if SwitchCollector.is_dataclass(owner) else "__init__"), False

    @staticmethod
    def _error(owner: ast.ClassDef) -> str:
        # Reuses the exception type the class already raises for invalid input, so callers keep one except clause.
        for method in (item for item in owner.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in _VALIDATION_METHODS):
            for node in ast.walk(method):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and LiteralName.of(node.exc.func):
                    return LiteralName.of(node.exc.func)
        return _DEFAULT_ERROR


class StrictBoolSwitchesRule(Rule):
    """Requires every bool switch on a configuration class to be checked with isinstance(x, bool) at construction."""

    id = "C007"
    name = "strict-bool-switches"
    severity = "blocking"
    summary = "A bool field or __init__ switch on a *Settings/*Config/*Configuration/*Policy/*Options class, or on a config-module class whose constructor raises ConfigurationError, must be checked with isinstance(value, bool) when the object is built. Without that check, the string \"false\" is truthy and turns the switch on, and 0 or 1 are kept as ints. The finding names the class, the switch, and every other unchecked switch on the same class."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # One finding per unchecked switch, anchored at its declaration.
        return [self._finding(item) for item in StrictBoolSwitchAnalyzer().analyze(catalog)]

    def explain(self, finding: Finding) -> Diagnostic:
        # Spell out the truthiness failure, the class-specific repair, and why coercion is not a fix.
        extra = finding.extra
        owner, switch = extra["owner"], extra["switch"]
        siblings = [item for item in extra["siblings"].split(", ") if item]
        sibling_text = f" The same class has {len(siblings)} other unchecked switch{'es' if len(siblings) > 1 else ''}: {', '.join(f'`{item}`' for item in siblings)}; fix them in the same change." if siblings else ""
        return Diagnostic(
            what_happened=f"{finding.location()} `{owner}.{switch}` is a bool switch on the configuration class `{owner}` ({extra['usage']}), but no method of `{owner}` checks `isinstance(..., bool)` on it, and it is not handed to a bool validator or to another configuration class. `{owner}(..., {switch}=\"false\")` builds without error, and because \"false\" is truthy, every `if settings.{switch}:` check treats the switch as on; 0 and 1 are kept as ints.{sibling_text}",
            why_blocked="Settings values arrive from YAML, JSON, environment variables, CLI flags, and model-written tool arguments, where \"false\" and \"0\" are ordinary strings. A switch that accepts them silently does the opposite of what the caller configured; for a switch such as FileSystemToolConfig.allow_write, that is a permission change. PR #529 fixed exactly this for AgentFallbackSettings.enabled (`@intent fallback-enabled-is-not-truthiness` in vidbyte/agents/settings/fallback.py), and AGENTS.md (Use Validated Dataclasses) requires records to validate types when they are created.",
            how_to_fix=self._repair(finding, siblings),
            correct_examples=("vidbyte/workflows/contracts.py:179 - StateMachineSettings.__post_init__ raises TypeError unless record_state_snapshots is a bool.", "vidbyte/agents/settings/fallback.py:35 - _require_boolean_enabled rejects every non-bool `enabled` before it is stored (PR #529).", "vidbyte/agents/multi/transfer.py:118 - AgentTransfer._validate_reset_policy keeps replan reset 'explicit rather than truthy/falsy configuration'."),
            will_not_work=("Coercing with `bool(value)` or `object.__setattr__(self, name, bool(value))`: bool(\"false\") is True, so the coercion makes the bug permanent instead of rejecting it.", "Relying on the `bool` annotation: neither dataclasses nor plain __init__ methods check annotations at run time.", "Checking `value is True` or `value == True` at each read site: every reader must remember it, `1 == True` still passes, and construction still accepts the bad value.", "Parsing \"true\"/\"false\" strings inside the settings class: that creates a second parsing contract. Parse at the boundary that reads the text (CLI, YAML, or tool arguments) and hand the class a real bool.", "Raising C007's baseline in lint/baseline.json: each finding is a switch that accepts the opposite of what a caller configured."),
            verify=f"{self.verify_command()} && python lint/run.py --rule C002 && python -m pytest tests/features -q",
        )

    @staticmethod
    def _finding(item: UncheckedSwitch) -> Finding:
        # Stores every fact the diagnostic quotes, so explain() never re-reads source.
        switch = item.switch
        return Finding(rule_id=StrictBoolSwitchesRule.id, rel_path=switch.source.rel, line=switch.line, source_line=switch.source.line_at(switch.line), symbol=f"{switch.owner.name}.{switch.name}", extra={"owner": switch.owner.name, "switch": switch.name, "shape": switch.shape, "usage": switch.usage, "siblings": ", ".join(item.siblings), "optional": ", ".join(item.optional), "home": item.home, "home_exists": "yes" if item.home_exists else "no", "error": item.error})

    @staticmethod
    def _repair(finding: Finding, siblings: list[str]) -> str:
        # One inline check for a lone switch; a sweep with the generic name `value` when the class has several.
        extra = finding.extra
        owner, switch, error, home = extra["owner"], extra["switch"], extra["error"], extra["home"]
        optional = [item for item in extra["optional"].split(", ") if item]
        where = f"`{owner}.{home}`" if extra["home_exists"] == "yes" else f"a new `{owner}.{home}` (the class does not define one yet)"
        target = switch if extra["shape"] == _PLAIN and home == "__init__" else f"self.{switch}"
        if siblings:
            fields = ", ".join(f'"{item}"' for item in [switch, *siblings])
            step_one = f"1. In {where}, check every switch in one loop: `for name in ({fields}): value = getattr(self, name)` followed by `if not isinstance(value, bool): raise {error}(f\"{owner}.{{name}} must be True or False, got {{value!r}}.\")`. The generic name `value` keeps C002 (duplicate inline bool guards) quiet."
        else:
            step_one = f"1. In {where}, before the switch is used, add `if not isinstance({target}, bool): raise {error}(\"{owner}.{switch} must be True or False.\")`. If C002 then reports the same field name checked in another class, assign it to a local named `value` first, or call the shared validator from step 3."
        if optional:
            step_one += f" {', '.join(f'`{item}`' for item in optional)} may be None by annotation, so {'its' if len(optional) == 1 else 'their'} test is `value is not None and not isinstance(value, bool)`."
        placement = "Put the check in `__post_init__`, which runs for every construction path, including `dataclasses.replace`." if extra["shape"] == _DATACLASS else "Run the check during construction (in `__init__` or the `_validate` it calls), so a bad value fails the constructor instead of reaching a reader."
        return "\n".join((
            step_one,
            f"2. {placement} Keep `{error}` so callers keep a single except clause, and make sure the message names the field.",
            "3. If several modules need the same check, use one shared bool validator in vidbyte/lib/dataclasses/validation.py (C008 names the copies to merge) instead of another module-local `_require_bool`.",
            f"4. Add a contract test that constructs `{owner}` with `{switch}=\"false\"`, `{switch}=0`, and `{switch}=1`, asserts each raises `{error}`, and asserts True and False still build.",
        ))


RULE = StrictBoolSwitchesRule()
