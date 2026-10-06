# Design Doc: Model-Facing Description Depth Lint Rule (S025)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-27
**Last Updated:** 2026-08-27

---

## 1. Overview

Add a new rule, `S025`, to the SDK's existing agent-facing lint suite (`lint/`)
that enforces the SDK's documented "model-facing tool contract" convention:
every `ToolSpec.description` and every `ToolParameter.description` on a class
that (directly or transitively) subclasses `vidbyte.tools.base.BaseTool` must
read as a general, 4-5 sentence explanation of what that field is and why it
exists on the tool, rather than a one-line label. The rule statically resolves
literal, f-string, concatenated, and same-file/imported-constant description
values, counts sentences with a documented heuristic, and reports every
resolvable description under four sentences. It plugs into the existing
`Rule` contract, registry, and baseline-ratchet mechanism, so it becomes part
of `python lint/run.py` and `scripts/run_ci.py --stage source` without any
change to the runner, CLI, or reporting code.

---

## 2. Goals & Non-Goals

### Goals

- Add one new independently selectable rule, `S025`, following the exact
  `Rule` contract used by `S001`-`S024` (`lint/core/registry.py`).
- Check `ToolSpec.description` and every `ToolParameter.description` for every
  class in the repo-wide transitive closure of `BaseTool` subclasses that
  defines its own `spec()` method.
- Statically resolve description text through: string literals (including
  adjacent-literal concatenation, which Python already folds at parse time),
  f-strings (`JoinedStr`), `+` concatenation of resolvable parts, and `Name`
  references to a module-level constant defined in the same file or imported
  from another tracked file in the package.
- Count sentences with a documented, deterministic heuristic and flag any
  resolved description with fewer than 4 sentences.
- Write a diagnostic whose `how_to_fix` text explicitly instructs the reader
  (a coding agent) to rewrite the field as a general 4-5 sentence description
  of what the field is and why it is in the tool, per the project's existing
  request for this rule.
- Initialize `lint/baseline.json["S025"]` after reviewing representative
  findings, freezing existing debt exactly like every other rule.
- Add the rule to `lint/README.md`'s rule catalogue and "Adding a rule" is
  otherwise unchanged.

### Non-Goals

- No check of `ToolActivity.description` (the separate `with_activity()`
  annotation contract). It is structurally identical and would be a natural
  follow-up rule, but it was not part of the request and is left out to keep
  this change's scope and initial baseline reviewable.
- No semantic/quality scoring of description text (topic relevance, absence
  of concrete examples, tone). Sentence count is a deterministic proxy the
  suite can compute offline without a model call; the qualitative guidance
  ("general", "what the field is and why it is in the tool") is carried by
  the diagnostic message a human or agent reads when fixing a finding, not by
  the automated check itself.
- No resolution of descriptions built by a method call (e.g.
  `self._build_description(...)`) or by an attribute assigned from a
  non-literal expression (e.g. a constructor parameter). These are exempted
  as statically-indeterminate, consistent with how `S010`/`S013` already defer
  genuinely dynamic cases rather than importing/executing SDK code to resolve
  them.
- No rewriting of any existing tool or parameter description. This change
  only adds the check; the ~250+ pre-existing short descriptions it finds are
  frozen into `baseline.json`, not fixed, exactly like `S001`'s 55 and
  `S017`'s 79 pre-existing findings today.
- No new dependency, no change to `lint/run.py`, `lint/core/runner.py`,
  `lint/core/report.py`, `lint/core/baseline.py`, or the CLI surface.

---

## 3. Background & Context

The SDK's field guide already documents this convention
(`field-guide/vidbyte-sdk/model-facing-tool-contracts.md`, "Make tool schemas
teach the model the complete event contract"): *"give the tool and every
parameter a consistent 4-5 sentence general description ... shallow fields ...
narrow behavior and hide the event's intended dimensions."* That entry traces
to PR #337 review comments and was resolved for one family of tools in PR
#356. It has never been enforced automatically, so it depends on reviewers
remembering to ask for it on every new tool.

An audit of `origin/main` (this repo's local `vidbyte-sdk/` checkout is 25
commits behind `origin/main` and was not used for source-of-truth counts)
confirms the gap is real and current:

- **`ToolSpec.description`**: 116 `ToolSpec(...)` constructions across 72
  files. 84 use a plain string literal; of those, only 22 already read as 4+
  sentences (chiefly `vidbyte/tools/builtins/memory/{supermemory,mem0,cognee,zep}.py`,
  which already follow the convention). The other 62 are one-liners, e.g.
  `vidbyte/tools/builtins/code_search/grep.py:30`: `"Search files for a
  literal string or regular expression."` The remaining 32 are built
  dynamically (f-strings, `+` concatenation of shared constants such as
  `vidbyte/tools/builtins/providers/_descriptions.py:STORE_BOUND_DESCRIPTION`,
  `self._description` attributes, or a method call).
- **`ToolParameter.description`**: 240 `ToolParameter(...)` constructions
  across 56 files. 210 use a plain string literal; only 14 already read as 4+
  sentences. The remaining 196 are short, e.g. `"The page URL to fetch."`

The existing `lint/` suite (added by a prior, already-merged change; its own
design doc was never committed to `origin/main`, only `lint/README.md` and the
rule modules themselves survive as living documentation) already provides
everything a new rule needs: `SourceCatalog.python_files()` returns every
tracked `vidbyte/**/*.py` file with a cached `ast.Module`, the `Rule` /
`Finding` / `Diagnostic` contracts are stable, and `baseline.json` freezes
existing debt per rule. No new infrastructure is required.

---

## 4. Requirements

### Functional Requirements

1. `S025` is registered in `lint/core/registry.py`'s `RULE_MODULES` tuple and
   is independently selectable via `python lint/run.py --rule S025`.
2. The rule builds a repo-wide class-inheritance graph from
   `catalog.python_files()` by recording, for every `class X(Base1, Base2):`
   in tracked `vidbyte/**/*.py` source, the base identifiers as written.
3. The rule computes the transitive closure of classes reachable from
   `BaseTool` (seed: the class literally named `BaseTool`) by following that
   graph. A class is "in scope" if it is in this closure and it defines its
   own `spec` method (classes that only inherit `spec()` from a scoped-in
   parent, such as an abstract intermediate with no `spec()` of its own, are
   not separately checked because they contribute no findings).
4. For every in-scope class's `spec` method body, the rule locates every
   `ToolSpec(...)` call and, within it, every `ToolParameter(...)` call
   reachable from the `parameters=` argument or from a local variable used to
   build it.
5. For each such call, the rule extracts the `description` argument (keyword
   `description=`, or positional index 1 for `ToolSpec` / index 2 for
   `ToolParameter`, matching each dataclass's field order) and attempts to
   statically resolve it to a string via the algorithm in Section 6.2.
6. When resolution succeeds, the rule counts sentences via the algorithm in
   Section 6.3. A count below 4 is one `Finding`.
7. When resolution fails (the expression is not reducible by the algorithm in
   Section 6.2 — e.g. it calls a method, or reads a constructor parameter),
   the rule emits no finding for that description; it is exempted, not
   assumed compliant or non-compliant.
8. `Rule.explain()` returns a `Diagnostic` whose `how_to_fix` text explicitly
   asks for a general 4-5 sentence description of what the field is and why
   it is present on the tool, and whose `correct_examples` cite at least one
   already-compliant tool description and the field guide entry.
9. `lint/baseline.json` gains one new sorted key, `"S025"`, initialized only
   after representative findings and plausible resolver counterexamples have
   been reviewed by hand, per the existing suite's convention.
10. `lint/README.md`'s "Rule catalogue" table gains one new row for `S025`.

### Non-Functional Requirements

- The rule must not import or execute any `vidbyte` module; it reads source
  text and `ast.Module` trees only, matching every existing rule's stated
  non-goal.
- Cross-file constant resolution (Section 6.2) must be bounded (a fixed hop
  limit) and must not loop on circular imports, so the rule terminates on any
  input and stays within the suite's existing sub-30-second full-run target.
- Output ordering must be stable (rule, path, line, column), matching
  `lint/core/report.py`'s existing contract; the rule does not need to
  implement this itself, only to return `Finding`s in a deterministic order
  from `check()`.
- The rule must work identically on Windows and POSIX checkouts (no
  shell-specific paths); module-to-file resolution uses `pathlib`, not string
  splitting on a hardcoded separator.
- Every finding's diagnostic must be self-contained for a coding agent with no
  other context, per the suite's existing diagnostic bar: consequence, repair
  shape, a local compliant example, a rejected shortcut, and the focused
  verify command.

---

## 5. High-Level Design

```text
catalog.python_files()  (already cached vidbyte/**/*.py ASTs)
        |
        v
ClassHierarchyIndex  --- builds { class_name: (bases, defining_file, ast.ClassDef) }
        |
        v
BaseToolClosure  --- BFS from "BaseTool" over the hierarchy index
        |
        v
ToolSpecCallFinder  --- walks each in-scope class's spec() body for
        |                ToolSpec(...) and nested ToolParameter(...) calls
        v
DescriptionResolver  --- resolves each description expression to text,
        |                or reports it as unresolved (Section 6.2)
        v
SentenceCounter  --- counts sentences in resolved text (Section 6.3)
        |
        v
S025 Rule.check()  --- one Finding per resolved description with <4 sentences
        |
        v
existing baseline / report / exit-code machinery (unchanged)
```

The rule is one new file, `lint/rules/s025_model_facing_description_depth.py`,
implementing the same shape as `S014` (`ProviderModelRegistryParityRule` /
`RegistryParityAnalyzer`): a small analyzer class the `Rule` subclass delegates
to, so `check()` stays a thin adapter and the analysis logic stays unit-testable
in isolation by focused lint runs.

---

## 6. Detailed Design

### 6.1 `lint/rules/s025_model_facing_description_depth.py` (New)

**File(s):** `lint/rules/s025_model_facing_description_depth.py`
**Type:** New file

#### What it does

Implements the `Rule` contract for `S025`: finds every `BaseTool`-derived
class's `spec()` method, extracts every `ToolSpec`/`ToolParameter`
`description` argument it can statically resolve, and reports the ones under
4 sentences.

#### Interface / API

```python
class ClassHierarchyIndex:
    def build(self, files: tuple[SourceFile, ...]) -> dict[str, "ClassRecord"]: ...

class ClassRecord:
    name: str
    bases: tuple[str, ...]
    file: SourceFile
    node: ast.ClassDef

class BaseToolClosure:
    def in_scope_classes(self, index: dict[str, ClassRecord]) -> tuple[ClassRecord, ...]: ...

class DescriptionResolver:
    def resolve(self, expr: ast.expr, owner: ClassRecord, files_by_rel: dict[str, SourceFile]) -> str | None: ...

class SentenceCounter:
    def count(self, text: str) -> int: ...

class ModelFacingDescriptionDepthAnalyzer:
    def analyze(self, catalog: SourceCatalog) -> list[Finding]: ...

class ModelFacingDescriptionDepthRule(Rule):
    id = "S025"
    name = "model-facing-description-depth"
    def check(self, catalog: SourceCatalog) -> list[Finding]: ...
    def explain(self, finding: Finding) -> Diagnostic: ...

RULE = ModelFacingDescriptionDepthRule()
```

#### Logic / Algorithm

1. `ClassHierarchyIndex.build` walks every `SourceFile.tree` from
   `catalog.python_files()`; for each top-level or nested `ast.ClassDef`, it
   records `name -> ClassRecord(bases=<base id/attr names as written>, file,
   node)`. Base identifiers are taken from `ast.Name.id` or, for a dotted base
   such as `abc.ABC`, from `ast.Attribute.attr` (matching how `BaseTool`
   itself is always referenced as the bare name `BaseTool` after its normal
   `from vidbyte.tools.base import BaseTool` import throughout the package).
2. `BaseToolClosure.in_scope_classes` starts from the literal name `"BaseTool"`
   and does a fixed-point closure: a class is in scope if any of its `bases`
   names is `"BaseTool"` or is itself already in scope. This requires no
   import resolution because every tool subclass in the audited codebase
   references its base by bare name.
3. For each in-scope `ClassRecord` whose own `ast.ClassDef.body` contains a
   `def spec(self) -> ToolSpec:` (or async — none exist today, but the check
   is on the name `spec`, not on `async`), walk that method's body with
   `ast.walk` and collect every `ast.Call` whose callee resolves to `ToolSpec`
   or `ToolParameter` (by `Name.id` or `Attribute.attr`, matching the existing
   `S014`-style callee check).
4. For a `ToolSpec` call, take `keywords` matching `description`, else
   `args[1]`. For a `ToolParameter` call, take `keywords` matching
   `description`, else `args[2]`.
5. `DescriptionResolver.resolve` handles, recursively:
   - `ast.Constant` with a `str` value: return it directly. (Adjacent plain
     string literals such as `("a " "b " "c")` are already folded into one
     `Constant` by the Python parser, so no special case is needed for the
     common multi-line description block seen throughout
     `vidbyte/tools/builtins/memory/*.py` and `.../providers/mongodb.py`.)
   - `ast.JoinedStr` (an f-string, or an f-string adjacent to plain literals,
     e.g. `vidbyte/tools/builtins/pause.py`): concatenate the `.value` of
     every `ast.Constant` child in `.values`; for every `ast.FormattedValue`
     child, splice in a single neutral placeholder character (`"0"`) instead
     of the real interpolated value, so an embedded number or name cannot
     accidentally create or hide a sentence boundary.
   - `ast.BinOp` with `op` an `ast.Add`: resolve `left` and `right`
     recursively; if both resolve, return the concatenation, else unresolved.
     This is required for `vidbyte/tools/builtins/providers/mongodb.py`'s
     `"..." + STORE_BOUND_DESCRIPTION` pattern.
   - `ast.Name`: look up an assignment to that name, in order: (a) a
     module-level `ast.Assign`/`ast.AnnAssign` in the same file, (b) if not
     found, check the same file's `ast.ImportFrom` nodes for one that imports
     that name; resolve the module path to a tracked file via
     `ModuleResolver` (Section 6.2 note below) and repeat the lookup there.
     Bound to 3 hops to guarantee termination on any accidental import cycle.
     If the found assignment's value is itself an expression, resolve it
     recursively through the same rules.
   - `ast.Attribute` of the shape `self.<name>`: look inside the owning
     class's `__init__` (if present) for a simple `self.<name> = <expr>`
     assignment and resolve `<expr>` recursively. If no such assignment
     exists, or `<expr>` references anything other than a literal/resolvable
     name (e.g. it reads a constructor parameter, as no current example does
     but a future tool could), the description is unresolved.
   - Anything else (`ast.Call`, `ast.IfExp`, subscripts, f-strings with a
     non-constant, non-formatted-value child, etc.): unresolved. This is the
     exemption path exercised today by
     `vidbyte/tools/builtins/handoff/create.py`'s
     `self._build_description(...)` and
     `vidbyte/tools/builtins/context_primitives/create.py`'s
     `self._definition....` chain.
6. `SentenceCounter.count` scans the resolved text for `.`, `!`, `?`
   characters followed by whitespace or end-of-string, and counts one
   sentence per match, except a match is *not* counted when either:
   - the character immediately before and after the `.` are both digits
     (a decimal number, e.g. "3.5"), or
   - the word immediately preceding the punctuation, lowercased, is one of a
     fixed allow-list of abbreviations: `e.g`, `i.e`, `etc`, `vs`, `approx`.
   A description with zero matching terminators but non-trivial length (e.g.
   a single clause with no final period) counts as 1 sentence, not 0, so a
   short unpunctuated label is still correctly flagged rather than silently
   skipped for having "no sentences to count."
7. `ModelFacingDescriptionDepthAnalyzer.analyze` assembles one `Finding` per
   resolved description whose sentence count is below 4:
   - For a `ToolSpec.description` finding: `symbol` is the class's own
     `name=` literal from the same `ToolSpec(...)` call when it resolves as a
     plain string, else the class name.
   - For a `ToolParameter.description` finding: `symbol` is
     `f"{tool_symbol}.{parameter_name}"`, where `parameter_name` is that same
     call's `name=`/`args[0]` literal when resolvable, else `"<parameter>"`.
   - `extra` carries `{"sentence_count": str(n), "kind": "tool" | "parameter"}`
     so `explain()` can quote the exact count.

#### Edge Cases & Error Handling

- A `spec()` method that builds `ToolSpec` via a local variable
  (`spec = ToolSpec(...); return spec`) is still found, because the call
  finder walks the whole method body with `ast.walk`, not only `return`
  statements.
- A class appearing twice under different names in two files (unexpected, but
  possible with a copy-paste) is handled independently per `ClassRecord`;
  there is no dedup, matching how every other structural rule in this suite
  treats each source location independently.
- A parse error recorded on a `SourceFile` (`parse_error is not None`) causes
  that file to be skipped for hierarchy-building and call-scanning, exactly
  like every existing AST-based rule; it is not a separate lint failure for
  `S025` specifically since no other rule treats broken parses that way
  either, and `S001`/Ruff already fails closed on syntax errors repo-wide.
- If the same shared constant used across multiple tools (e.g.
  `STORE_BOUND_DESCRIPTION`) is itself too short, every tool composing it
  will be reported once per composing call site, not once for the shared
  constant. This mirrors the finding granularity of every other structural
  rule in the suite (one finding per call site, not per shared symbol) and
  keeps `explain()` pointing at the exact tool whose model-facing text is
  short.

---

## 7. Data Model Changes

N/A - no runtime data model changes. `lint/baseline.json` gains one new
integer key (`"S025"`), which is tooling metadata, not a persisted data
model, matching Section 7 of the existing lint suite's own design doc.

---

## 8. API Changes

N/A - no runtime or public SDK API change. The repository-local
`python lint/run.py --rule S025` command follows the existing CLI contract
with no new flags.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/sdk-tool-description-depth-lint-rule.md` | This design doc. |
| CREATE | `lint/rules/s025_model_facing_description_depth.py` | New rule implementation (Section 6.1). |
| MODIFY | `lint/core/registry.py` | Add `"lint.rules.s025_model_facing_description_depth"` to `RULE_MODULES`, keeping the tuple in the existing sorted order. |
| MODIFY | `lint/baseline.json` | Add the sorted `"S025"` key via `python lint/run.py --rule S025 --update-baseline` after manual review of representative findings. |
| MODIFY | `lint/README.md` | Add one row for `S025` to the "Rule catalogue" table, per the folder's own "Adding a rule" step 4. |

### Files to Delete (0)

None.

---

## 10. Dependencies & External Services

None. No new package, no pin change to `pyproject.toml`; the rule uses only
`ast` and `re` from the standard library, exactly like the other AST-based
`S`-series rules.

---

## 11. Rollout & Deployment

- No feature flag; this is a developer-facing static-analysis gate, not
  runtime behavior. It affects only `python lint/run.py` and
  `scripts/run_ci.py --stage source`.
- Not a breaking change to any consumer. It is additive to CI: once
  `lint/baseline.json["S025"]` is initialized, any *new* tool or parameter
  description under 4 resolvable sentences fails CI; every existing short
  description found during implementation is frozen into that count and
  keeps building.
- Deployment order: implement the rule, run it once with
  `--format json` to inspect every finding and every resolver "unresolved"
  case for false negatives (a description the resolver should have reached
  but silently treated as dynamic), initialize the baseline, then run the
  full `python lint/run.py` and `python scripts/run_ci.py` gates before
  opening the PR.
- Rollback is a revert of the two implementation commits (new rule file, plus
  the two one-line catalogue/registry edits) and the baseline addition; no
  data or runtime rollback is required.

---

## 12. Open Questions

- [ ] Whether a future `S026` should extend the same resolver/counter to
  `ToolActivity.description` (explicitly out of scope here per Section 2).
- [ ] Whether the initial `S025` baseline count (expected in the
  250-300 range across both `ToolSpec` and `ToolParameter` findings, per the
  Section 3 audit) should be called out to reviewers in the PR description so
  it is not mistaken for a regression introduced by this change.

---

## 13. Alternatives Considered

### Score description quality with a heuristic beyond sentence count

Rejected because judging whether a description is truly "general" or free of
concrete examples requires semantic understanding, not deterministic AST/text
analysis, and the suite's stated architecture is explicitly offline and
side-effect-free (no model calls). Sentence count is a proxy the suite can
compute cheaply and deterministically; the qualitative bar is carried by the
diagnostic's `how_to_fix` text instead, matching how `S002`-`S021`'s
diagnostics already carry qualitative repair guidance beyond what their
detection logic mechanically checks.

### Flag every dynamically-built description as a violation rather than exempting it

Rejected because it would require importing/executing SDK code (forbidden by
the suite's own non-goals) to see the real rendered text, or would produce
false positives on legitimately dynamic-but-long descriptions (e.g. a bound
duration range spliced into an otherwise long f-string). Resolving what is
statically reachable and exempting the rest matches the precedent already set
by `S010` ("unknown dynamic receivers become mypy's responsibility") and
`S013` ("local fixture/file reads are excluded").

### Scope the rule to `ToolSpec.description` only

This was the literal first reading of the request. Rejected in favor of also
covering `ToolParameter.description` after confirming with the user, because
the field guide's own documented convention already names both, and the
audit shows parameter descriptions are, if anything, shorter and more
one-line-labeled today (196 of 210 literal parameter descriptions are under 4
sentences) than tool descriptions.
