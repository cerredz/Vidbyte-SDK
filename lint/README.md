# lint/ -- SDK agent-facing static analysis

This folder turns Vidbyte SDK architecture and correctness contracts into one
blocking, count-ratcheted command. Its diagnostics assume the reader is a coding
agent with no additional context, so each failure explains the consequence,
repair, local precedent, rejected shortcuts, and focused verification command.

## Responsibilities

- Run pinned Ruff once and expose eight independently baselined policies.
- Run pinned mypy once and ratchet every package type-contract error.
- Scan transport, registry, export, boundary-error, pricing, cancellation,
  documentation, and helper-ownership contracts without importing the SDK.
- Fail closed when an analyzer, source read, parser, registry, or baseline fails.
- Freeze existing debt while failing any count increase and preserving reductions.

## Non-Goals

- This folder does not format or rewrite source.
- It does not ban `Any`, every broad exception, long signatures, or exact headers.
- It does not import providers, contact external services, or require credentials.
- It does not replace the zero-tolerance Semgrep typed-Mapping policy or the
  existing context write-path checker.
- It does not index folders whose README has no `## File Index` section.

## Running the suite

```bash
python lint/run.py
python lint/run.py --rule S010
python lint/run.py --rule S010 --all
python lint/run.py --format json
```

`scripts/run_ci.py --stage source` invokes the complete suite. In an isolated
worktree, make the worktree source authoritative before CI:

```powershell
$env:PYTHONPATH=(Get-Location).Path
python scripts/run_ci.py --stage source
```

Exit 0 means every rule is CLEAN, RATCHETED, or IMPROVED. REGRESSED and ERRORED
fail. A missing/stale baseline key also fails; registered rules cannot silently
escape enforcement.

## Baseline ratchet

`baseline.json` maps each rule ID to the number of violations that predated its
gate. Existing allowances may never be raised to make a regression pass. After
a real source improvement, lower the focused allowance:

```bash
python lint/run.py --rule S017 --update-baseline
```

New rules are initialized only after representative findings and counterexamples
have been reviewed. Analyzer failures are never recorded as zero.

## File Index

- `__init__.py` -- marks the repository-local lint package.
- `run.py` -- stable CLI and application orchestration.
- `baseline.json` -- sorted per-rule debt ceilings.
- `mypy.ini` -- pinned staged package type-check policy.

Nested folders:

- `core/` -- source discovery, analyzers, rule contracts, baselines, and reports.
- `rules/` -- one independently selectable module per S-rule.

## Rule catalogue

| ID | Rule | Protected contract |
|---|---|---|
| S001 | python-correctness-foundation | Defined names, valid imports, syntax/layout |
| S002 | exception-cause-chaining | Error provenance through translations |
| S003 | strict-zip | Explicit paired-iteration length behavior |
| S004 | timezone-aware-datetime | Aware timestamps across runtime boundaries |
| S005 | immutable-class-defaults | No accidental shared mutable instance state |
| S006 | async-task-ownership | Durable task lifetime and exception ownership |
| S007 | public-function-annotations | Typed public parameters and returns |
| S008 | bounded-function-complexity | Reviewable branches/statements/complexity |
| S009 | staged-mypy-contracts | Package type errors may only decrease |
| S010 | transport-parity | Async and sync transports match their callers |
| S011 | raw-http-client-ownership | HTTP clients stay in transport adapters |
| S012 | explicit-outbound-timeout | Every outbound call declares a timeout |
| S013 | bounded-untrusted-responses | Ingestion bodies have byte ceilings |
| S014 | provider-model-registry-parity | Enums/config/runner catalogs agree |
| S015 | public-export-integrity | `__all__` is unique, bound, and complete |
| S016 | typed-boundary-errors | External seams raise SDK error types |
| S017 | no-raw-exception-disclosure | Public text excludes raw caught exceptions |
| S018 | priced-operation-attempts | Usage results retain retry attempts |
| S019 | cancellation-propagation | Async cancellation is never swallowed |
| S020 | readme-file-index-parity | Opt-in folder maps match tracked files |
| S021 | class-bound-registry-helpers | Registry behavior stays on owning classes |
| S024 | maximum-control-flow-nesting | Control-flow depth stays within three levels |
| S025 | model-facing-description-depth | ToolSpec/ToolParameter descriptions read as general 4-5 sentence context |

### Agent-native rules

| ID | Rule | Protected contract |
|---|---|---|
| A001 | agent-readable-file-headers | Tracked Python files expose purpose and maintenance context |
| A002 | intent-comments | Load-bearing policy logic explains its invariant nearby |
| A003 | context-rich-error-packets | Boundary errors expose stable repair context |
| A005 | typed-dependency-seams | Injected infrastructure uses concrete interfaces or Protocols |
| A006 | directed-dependency-graph | Concrete imports obey cycles and documented layer boundaries |
| A007 | operational-constants | Runtime policy values have named ownership |
| A008 | library-stdout-boundary | Importable SDK code does not write unstructured stdout |

## Adding a rule

1. Add one `lint/rules/sNNN_name.py` module exporting `RULE`.
2. Register its number/name pair in `lint/core/registry.py`.
3. Run the focused rule with JSON, inspect representative true positives and
   plausible counterexamples, then initialize its count explicitly.
4. Add the rule to this catalogue and the design document.
5. Run the complete source and package CI gates.

Suppressions and path exceptions are policy changes. Put narrow, named boundary
constants in the owning rule and explain why the boundary is safe; do not scatter
inline ignores through production source.
