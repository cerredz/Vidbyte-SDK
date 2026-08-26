# Design Doc: SDK Lint Suite — Domain Contract Rules (C001–C005)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-26
**Last Updated:** 2026-08-26

---

## 1. Overview

Add five new lint rules to the `lint/` package introduced in PR #368
(`feat/sdk-lint-python-correctness`, open, green, not yet merged): five
static checks that enforce SDK-specific domain conventions already
established through PR review, not general Python style. Each rule was
independently verified against the live codebase before being scoped — one
(`C001`) finds a real, currently-existing violation; the rest are
regression guards for patterns the SDK has already paid for once (a rate
shipped 1000x too low twice, a session-usage duplicate path that turned out
to be legitimate on inspection, a duplicate-validation idiom named in two
separate accepted PR reviews).

This PR also generalizes `lint/core/rule.py`'s `LintRule` protocol: PR #368's
`S001` assumed every rule filters Ruff's own findings, but none of these five
rules map to a Ruff selector — each parses `vidbyte/**/*.py` itself. The
protocol changes from `collect(ruff_findings)` to one uniform
`find(files, ruff_findings)` that every rule implements, Ruff-backed or not.

---

## 2. Goals & Non-Goals

### Goals

- Generalize `LintRule` to a single `find(files, ruff_findings) ->
  tuple[Finding, ...]` method so Ruff-backed and pure-AST rules share one
  registry, one runner, one baseline file, and one diagnostic renderer.
- Add `C001`–`C005`, each independently verified against the current
  `vidbyte/` tree (not designed from field-guide prose alone) — see Section
  3 for what each verification found.
- Keep every new rule's diagnostic text exact: correct file paths, correct
  function/class names, and a repair that has actually been checked against
  the real code shape, not a guess at what the code probably looks like.
- Freeze real, currently-existing findings into `lint/baseline.json`, same
  ratchet discipline as `S001`.

### Non-Goals

- No `C006` for tool-schema description quality (the sixth candidate from
  the prior brainstorm). Verified too heuristic to gate safely without more
  design work on what "6–9 meaningful fields" and "4–5 sentences" mean
  mechanically; deferred to the brainstorm list in this PR's description
  rather than shipped half-confident.
- No attempt to mechanically verify the `OPERATION_PRICING` "Sources:"
  comment block lists every provider. That block is free-text prose above
  the dict, not structured data; parsing it reliably would be its own
  fragile sub-project. `C004` only enforces the numeric floor, which is
  fully AST-checkable, and its diagnostic tells the reader to check the
  Sources block by hand when correcting a flagged rate.
- No change to runtime behavior, public API, or `S001`'s own detection
  logic or baseline count.
- No fixing of the one real `C001` finding this PR discovers
  (`AgentFallbackSettings`) — it gets frozen into the baseline like `S001`'s
  55 findings did. Fixing it is a real refactor (moving five validation
  methods into a new frozen dataclass) that deserves its own reviewed PR,
  not a drive-by inside a lint-tooling change.

---

## 3. Background & Context — what each rule's grounding check found

**`C001` (settings classes must not raise `ConfigurationError` directly):**
the field guide's own cited example, `AgentFallbackConfig` in
`vidbyte/lib/dataclasses/agents.py`, **does not exist** — grepped the whole
package, zero hits. The fallback subsystem was rewritten twice after that
memory was written (`fallback-coordination.md` cites "replacement PR #355"
and "replacement PR #358"). The memory is stale on that one specific claim.
What's real: `vidbyte/agents/settings/fallback.py`'s `AgentFallbackSettings`
is a plain class (not a `@dataclass`) whose own header docstring says
"Plain class with `__init__`-level validation," and it currently raises
`ConfigurationError` directly in five places (`_validate_models_not_empty`,
`_validate_entry_types`, `_validate_error_types`, `_split_provider_prefix`,
`_inherited_provider`). `PauseDuration` in
`vidbyte/lib/dataclasses/agents.py:94` is a live, correct example of the
sanctioned shape: `@dataclass(frozen=True, slots=True)` with a
`__post_init__` that raises. The rule cites `PauseDuration`, not the
nonexistent `AgentFallbackConfig`.

**`C002` (duplicate inline `isinstance(x, bool)` validation for the same
parameter name across the codebase):** grepped `isinstance\(\w+, bool\)`
across the whole package — roughly 60 hits. Most use generic names
(`value`, `raw`, `data`) that are validating unrelated fields and would be
pure noise if matched by name alone. But `timeout_seconds` appears in this
exact idiom in both `vidbyte/workflows/validation.py:172` and
`vidbyte/workflows/contracts.py:149,176`, and `max_trace_iterations`
appears in both `vidbyte/lib/dataclasses/continual_trace_descriptor.py:86`
and `vidbyte/lib/dataclasses/trace.py:168` — real, current, near-identical
duplicated checks for meaningful, specific parameter names. The rule
excludes a short deny-list of generic single-word names and only flags a
name that recurs across 2+ distinct functions.

**`C003` (no dynamic import from non-literal data):** grepped
`import_module\(|__import__\(` across the whole package. One hit total,
inside a markdown prompt template (`prompts/prompts/agentic_engineering/
feature_test_packs.md`), not real source, and it already passes a string
literal. Zero current violations in `.py` source — this rule ships as a
pure regression guard for the threat model
`declarative-config-resolution.md` states outright: "no document text
reaching an import."

**`C004` (`OPERATION_PRICING` rate implausibility floor):** read
`vidbyte/lib/registries/operation_pricing.py` in full. The existing test
`OperationPricingTableTests.test_no_rate_is_implausibly_small` in
`tests/test_agent_pricing.py:146` already enforces this exact invariant at
`_MIN_PLAUSIBLE_RATE_USD = 1e-5` (`tests/test_agent_pricing.py:42`). This
rule promotes that runtime-test invariant into a static, edit-time
diagnostic over the same dict literal — same threshold, same table,
different enforcement point.

**`C005` (cost arithmetic confined to two known sites):** grepped for
`*price*`/`*rate*` multiplication across the package. Found it in exactly
three files: `vidbyte/agents/pricing/base.py:113,132` and
`vidbyte/agents/pricing/anthropic.py:66-69` (both under the
`vidbyte/agents/pricing/` package — provider-specific token-cost formulas,
the sanctioned live-run path per `runtime-boundaries.md`), and
`vidbyte/sessions/usage.py:90` (`cost=(tokens * price)`). Read
`SessionUsageBuilder` in full: it reconstructs a `UsageRollup` from a
persisted session's *stored message history*, using a caller-supplied price
table, for session replay after the fact — a deliberately separate,
correctly-scoped subsystem, not a bug. So the rule is not a ban; it is a
two-entry allowlist (`vidbyte/agents/pricing/**`, `vidbyte/sessions/
usage.py`) that fails only if a *third* independent site starts doing this
arithmetic.

---

## 4. Requirements

### Functional Requirements

1. `LintRule` protocol changes to: `rule_id`, `ruff_selectors` (empty tuple
   for a pure-AST rule), `diagnostic()`, and `find(files: tuple[Path, ...],
   ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]`. Each
   rule returns fully-formed `Finding` objects (its own `rule_id` and
   `code` already set) rather than the runner wrapping a shared shape.
2. `S001` moves its existing selector-filter logic into `find`, unchanged in
   behavior and baseline count (55).
3. `LintRunner` calls `RuffAdapter.run` only when the selected rules' unioned
   `ruff_selectors` is non-empty (running `--rule C001` alone must not shell
   out to Ruff with an empty `--select`).
4. `C001`–`C005` are new modules under `lint/rules/`, each registered in
   `lint/core/registry.py`, each with `ruff_selectors = ()`.
5. A new `lint/core/parsing.py` provides one shared `PythonSourceParser`
   used by every AST rule: reads a file as UTF-8 (BOM-tolerant) and returns
   its parsed `ast.Module`, or `None` on a syntax error (S001's `E9`
   selector already reports syntax errors; an AST rule silently skipping an
   unparsable file avoids a duplicate, less-informative report).
6. `lint/baseline.json` gains five new keys reflecting each rule's real,
   verified current count (Section 3).

### Non-Functional Requirements

- Every new rule's `diagnostic()` names the real file(s)/class(es)/function(s)
  the check is grounded in, not a generic description — matches
  `diagnostic-context.md`'s field-guide requirement and the user's explicit
  "very accurately explain the fix" instruction.
- No rule imports or executes `vidbyte` package code; each reads and parses
  source text only (unchanged suite-wide invariant from PR #368).
- `python lint/run.py` (all rules) still completes in a few seconds on a
  warm checkout.

---

## 5. High-Level Design

```
tracked vidbyte/**/*.py --> SourceCatalog.python_files()
                                   |
                    +--------------+---------------+
                    |                               |
            (only if any rule                (every selected rule,
             declares selectors)              regardless of kind)
                    v                               v
          RuffAdapter.run(union)  ---------->  rule.find(files, ruff_findings)
                                                      |
                                                      v
                                        tuple[Finding, ...] per rule
                                                      |
                                                      v
                              BaselineStore.evaluate (unchanged) --> RunReport
```

`S001.find` ignores `files` and filters `ruff_findings` by selector prefix,
exactly as `collect` did. `C001`–`C005.find` ignore `ruff_findings`, call
`PythonSourceParser.parse` over `files` (each filtering to the paths it
actually cares about — `C004` to the one pricing-table file, the rest to the
whole tree), and walk the resulting ASTs directly.

---

## 6. Detailed Design

### 6.1 `lint/core/rule.py` — modified

**Type:** Modified

`LintRule.collect` is replaced by:

```python
@staticmethod
def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]: ...
```

`Finding` and `RuffFinding` both need importing here for the Protocol's type
hints; both already exist in `lint/core/diagnostic.py` and `lint/core/ruff.py`
respectively, imported under `TYPE_CHECKING` as `RuffFinding` already is.

### 6.2 `lint/core/parsing.py` — new

**File(s):** `lint/core/parsing.py` (new)
**Type:** New file

#### What it does
Gives every AST-based rule one shared, safe way to turn a file path into a
parsed module, so five rule modules don't each reimplement
read-encode-parse-and-swallow-syntax-errors.

#### Interface / API
```python
class PythonSourceParser:
    @staticmethod
    def parse(path: Path) -> ast.Module | None: ...
```

#### Logic / Algorithm
Reads `path` as UTF-8 with BOM tolerance (`encoding="utf-8-sig"`); calls
`ast.parse(text, filename=str(path))`; returns `None` on `SyntaxError` or
`UnicodeDecodeError` rather than raising, since a file that fails to parse
is already `S001`'s `E9` finding — an AST rule does not need to re-report it
and must not crash the whole run over one bad file.

### 6.3 `lint/rules/s001_python_correctness_foundation.py` — modified

**Type:** Modified

`collect(findings)` is renamed `find(files, ruff_findings)`; body becomes:
filter `ruff_findings` by selector prefix (unchanged), then wrap each match
into a `Finding(rule_id="S001", code=f.code, file=f.file, line=f.line,
column=f.column, message=f.message)` — this wrapping moves here from
`LintRunner._evaluate_rule`, which no longer needs to know anything
rule-kind-specific.

### 6.4 `lint/rules/c001_settings_class_configuration_error_placement.py` — new

**File(s):** new
**Type:** New file

#### What it does
Flags a `raise ConfigurationError(...)` found inside a method of a class
whose name ends in `"Settings"` and which is not itself a `@dataclass`.

#### Interface / API
```python
class SettingsClassConfigurationErrorPlacementRule:
    rule_id: ClassVar[str] = "C001"
    ruff_selectors: ClassVar[tuple[str, ...]] = ()

    @staticmethod
    def diagnostic() -> RuleDiagnostic: ...
    @staticmethod
    def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]: ...
```

#### Logic / Algorithm
1. Parse every file via `PythonSourceParser.parse`.
2. Walk top-level and nested `ast.ClassDef` nodes; skip a class whose
   `decorator_list` contains a `dataclass` decorator (bare `Name(id=
   "dataclass")` or `Call(func=Name(id="dataclass"))`).
3. Skip a class whose name does not end with `"Settings"`.
4. Walk every `ast.Raise` inside the surviving class's body (all nested
   function/method bodies included) and match one whose `exc` is a `Call`
   (or bare `Name`) resolving to the literal identifier `ConfigurationError`.
5. Emit one `Finding` per match, `code="C001"`.

#### Edge Cases & Error Handling
- A class decorated with a *different* decorator that happens to be named
  `dataclass` from an unrelated import is a false-negative risk the design
  accepts — this codebase has exactly one `dataclass` in scope
  (`dataclasses.dataclass`), verified by grep.
- Nested classes (a `Settings` class defined inside a function) are matched
  the same way; none currently exist, but excluding them would require
  extra logic for no observed benefit.

### 6.5 `lint/rules/c002_duplicate_inline_bool_guard_validation.py` — new

**Type:** New file

#### What it does
Flags a validated-parameter name that appears in the `isinstance(<name>,
bool)` idiom in two or more distinct functions anywhere in the tree.

#### Logic / Algorithm
1. Parse every file.
2. Walk every `ast.Call` matching `isinstance(<first arg>, bool)` where the
   first argument is an `ast.Name` (identity = `.id`) or `ast.Attribute`
   (identity = `.attr`, so `self.seconds` groups under `"seconds"`).
3. Skip an identity in the deny-list `{"value", "raw", "data", "entry",
   "item", "obj", "setting", "x", "v", "val", "flag"}` — generic names reused
   across unrelated fields (verified: matching on these produced ~40 of the
   ~60 raw hits, all unrelated to each other).
4. Group every surviving match by `(identity, containing file, containing
   function qualname)`; dedupe exact repeats within one function (a
   parameter checked twice in the same function is one occurrence, not two).
5. Group occurrences by identity across the whole tree; for any identity
   with 2+ distinct occurrences, emit one `Finding` per occurrence,
   `code="C002"`, whose message names every other file/function sharing
   that identity so a reader sees the full duplication at any one site.

#### Edge Cases & Error Handling
- The deny-list is a precision/recall tradeoff stated openly in the rule's
  own diagnostic text, not hidden: a real duplicate using a denied generic
  name is a false negative this rule accepts in exchange for not drowning
  every run in unrelated `value`/`raw` noise.

### 6.6 `lint/rules/c003_no_dynamic_import_from_data.py` — new

**Type:** New file

#### What it does
Flags `importlib.import_module(...)` or `__import__(...)` whose first
argument is not a string literal.

#### Logic / Algorithm
1. Parse every file.
2. Walk every `ast.Call` whose `func` is `Attribute(attr="import_module")`
   or `Name(id="__import__")`.
3. If the call has a first argument and it is not `ast.Constant` with a
   `str` value, emit a `Finding`, `code="C003"`.

#### Edge Cases & Error Handling
- A call with zero positional args (invalid Python, would fail at runtime
  regardless) is skipped rather than crashing the rule.

### 6.7 `lint/rules/c004_operation_pricing_rate_floor.py` — new

**Type:** New file

#### What it does
Re-implements `OperationPricingTableTests.test_no_rate_is_implausibly_small`
as a static check over the `OPERATION_PRICING` dict literal.

#### Logic / Algorithm
1. Filter `files` to the one path ending in
   `vidbyte/lib/registries/operation_pricing.py`.
2. Parse it; find the module-level `ast.AnnAssign` (or `ast.Assign`) whose
   target is `OPERATION_PRICING`.
3. For each `ast.Dict` key/value pair, the value is a `Call` to
   `OperationPricing(...)`; read its `usd_fixed` and `usd_per_unit` keyword
   arguments when present and numeric (`ast.Constant`, `int`/`float`).
4. For each such value that is nonzero and `abs(value) < 1e-5`
   (`_MIN_PLAUSIBLE_RATE_USD`, matching `tests/test_agent_pricing.py:42`
   exactly — duplicated here deliberately, since this is a static check
   mirroring a runtime test, not shared application config), emit a
   `Finding` naming the dict key `(operation, provider, mode)` and the
   offending field, `code="C004"`.

#### Edge Cases & Error Handling
- The file not existing or the dict literal not being found produces zero
  findings, not an error — the rule degrades to a no-op rather than failing
  the whole suite if this one file is ever renamed; `S001`'s general
  correctness selectors would independently catch a broken import of it
  elsewhere.

### 6.8 `lint/rules/c005_cost_arithmetic_site_parity.py` — new

**Type:** New file

#### What it does
Flags a `<name> * <name>` multiplication where either operand's identity
contains `"price"` or `"rate"` (case-insensitive), outside the two known
sanctioned locations.

#### Logic / Algorithm
1. Parse every file, skipping any path under `vidbyte/agents/pricing/` or
   equal to `vidbyte/sessions/usage.py`.
2. Walk every `ast.BinOp` with `op` being `ast.Mult`; take the identity of
   each `Name`/`Attribute` operand (as in `C002`); if either identity
   contains `"price"` or `"rate"` case-insensitively, emit a `Finding`,
   `code="C005"`.

#### Edge Cases & Error Handling
- A unit-conversion multiplication that happens to involve a variable named
  e.g. `rate_limit` would false-positive on the substring match; accepted
  as a rare, cheaply-reviewable cost given zero such names exist today
  (verified by the grounding grep in Section 3).

### 6.9 `lint/core/runner.py` — modified

**Type:** Modified

`_evaluate_rule` calls `rule.find(files, all_findings)` directly instead of
`rule.collect(all_findings)` plus a separate wrapping step; the wrapping
code that constructed `Finding` from `RuffFinding` moves into `S001` itself
(Section 6.3). `_union_selectors` and the Ruff invocation in `run()` gain an
`if selectors:` guard so a run selecting only AST rules never shells out to
Ruff with an empty selector set.

### 6.10 `lint/core/registry.py` — modified

**Type:** Modified

`_RULES` becomes a six-entry tuple; five new imports.

---

## 7. Data Model Changes

None. `lint/baseline.json` gains five new sorted keys with real counts
established by actually running the rules (Section 3's grounding already
gives close estimates; the committed baseline reflects the tool's real
output, not the estimate).

---

## 8. API Changes

None. Same as PR #368: developer-only tooling, no `vidbyte` runtime or
packaging change.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/sdk-lint-contract-rules.md` | This design |
| CREATE | `lint/core/parsing.py` | Shared safe AST parse helper |
| CREATE | `lint/rules/c001_settings_class_configuration_error_placement.py` | C001 |
| CREATE | `lint/rules/c002_duplicate_inline_bool_guard_validation.py` | C002 |
| CREATE | `lint/rules/c003_no_dynamic_import_from_data.py` | C003 |
| CREATE | `lint/rules/c004_operation_pricing_rate_floor.py` | C004 |
| CREATE | `lint/rules/c005_cost_arithmetic_site_parity.py` | C005 |
| MODIFY | `lint/core/rule.py` | `collect` → `find` protocol change |
| MODIFY | `lint/rules/s001_python_correctness_foundation.py` | Adopt `find`, absorb wrapping |
| MODIFY | `lint/core/runner.py` | Call `find` uniformly; guard empty-selector Ruff call |
| MODIFY | `lint/core/registry.py` | Register five new rules |
| MODIFY | `lint/baseline.json` | Five new real counts |
| MODIFY | `lint/README.md` | Rule catalogue gains six rows |

---

## 10. Dependencies & External Services

None new.

---

## 11. Rollout & Deployment

This branch is stacked on the still-open `feat/sdk-lint-python-correctness`
(PR #368) at the user's explicit choice, because rebuilding S001 from
scratch here would duplicate unreviewed work. The PR opened from this
branch targets `main` directly (not `feat/sdk-lint-python-correctness`),
consistent with this repo's own always-target-main practice; until #368
merges, this PR's diff will show both change sets, and it will shrink to
just this PR's own commits once #368 merges. No action needed if #368 merges
first; if #368's branch needs to change before merging, this branch should
be rebased onto its update rather than left pointing at a stale commit.

Rollback is reverting the implementation commits; `lint/baseline.json`'s
five new keys and the registry entries disappear together.

---

## 12. Open Questions

- [ ] None blocking. The one substantive judgment call (whether to gate on
      the tool-schema-quality idea) is resolved as a Non-Goal in Section 2.

---

## 13. Alternatives Considered

### Number these rules S002–S006, continuing PR #368's sequence

Rejected because PR #368's own design doc already flagged that "S002" is
claimed by a separate, broader, unimplemented draft
(`docs/design/sdk-agent-facing-lint-suite.md`) for an unrelated rule
(exception-cause chaining, Ruff's `B904`). Reusing that number for a
different rule here would collide if that draft is ever implemented. A
distinct `C` ("contract") prefix avoids the collision and is arguably more
honest: these are domain-contract checks with bespoke AST logic, not thin
Ruff-selector wrappers like the `S` family.

### Keep `LintRule.collect(ruff_findings)` and give AST rules an empty selector plus a separate ad hoc code path in the runner

Rejected because it would require `LintRunner` to branch on rule kind
(`if rule.ruff_selectors: collect(...) else: <something else>`), which is
exactly the kind of special-casing the registry/runner split exists to
avoid. One `find(files, ruff_findings)` method keeps every rule
interchangeable to the runner regardless of how it produces findings.

### Mechanically verify the `OPERATION_PRICING` "Sources:" comment block

Rejected (see Section 2 Non-Goals) — the block is prose above the dict, not
structured data tied to individual entries; a text-parsing rule here would
be fragile relative to the value it adds over the AST-checkable numeric
floor, which is the part that has actually caused a real, repeated
incident (PR #325 reverted, wrong rate shipped twice).
