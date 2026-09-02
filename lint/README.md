# lint/ -- SDK agent-facing static analysis

This folder turns Vidbyte SDK architecture and correctness contracts into one
blocking, count-ratcheted command. Its diagnostics assume the reader is a coding
agent with no additional context, so each failure explains the consequence,
repair, local precedent, rejected shortcuts, and focused verification command.

## Responsibilities

- Run pinned Ruff once and expose the independently baselined analyzer policies,
  including 33 Ruff policies.
- Enforce five SDK domain-contract policies (C001-C005) over the same source
  catalogue.
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
- `ruff.toml` -- explicit Ruff policy and repository-owned banned APIs.

Nested folders:

- `core/` -- source discovery, analyzers, rule contracts, baselines, and reports.
- `rules/` -- one independently selectable module per S, A, or C rule.

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
| S026 | pairwise-zip | Paired iteration states unequal-length behavior |
| S027 | mutable-dataclass-default | Dataclass fields do not share mutable defaults |
| S028 | dataclass-default-call | Dataclass defaults do not eagerly call functions |
| S029 | unnecessary-first-element-allocation | First-item access avoids full temporary materialization |
| S030 | quadratic-list-summation | List aggregation stays linear rather than repeatedly copying |
| S031 | assignment-in-assert | Production assignments do not disappear with optimized asserts |
| S032 | unnecessary-key-check | Mapping access states missing-key behavior without duplicate lookup |
| S033 | mutable-dict-fromkeys | Mapping keys do not share unintended mutable values |
| S034 | ambiguous-pytest-raises-match | Exception tests use precise message patterns |
| S035 | unused-noqa | Suppressions remain attached to active findings |
| S036 | invalid-pyproject | Build and tooling metadata remains valid |
| S037 | blanket-type-ignore | Type ignores name the exact diagnostic they suppress |
| S038 | blanket-noqa | Ruff suppressions name the exact diagnostic they suppress |
| S039 | banned-api-policy | SDK imports respect the repository-owned banned API table |
| S040 | relative-imports | Package dependencies use explicit absolute imports |
| S041 | unspecified-encoding | Text file operations declare their encoding |
| S042 | raise-vanilla-class | Runtime boundaries raise intentional typed errors |
| S043 | verbose-log-message | Exception logs avoid redundant raw exception text |
| S044 | logging-f-string | Logs use parameterized messages |
| S045 | async-function-with-timeout | Async timeout parameters are connected to deadline behavior |
| S046 | blocking-http-call-in-async-function | Async code avoids synchronous HTTP waits |
| S047 | blocking-open-in-async-function | Async code avoids blocking file opens |
| S048 | blocking-sleep-in-async-function | Async backoff yields to the event loop |
| S049 | unsafe-yaml-load | YAML parsing uses safe construction boundaries |
| S050 | insecure-hash | Hash primitives match the operation's security property |

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

### SDK domain-contract rules

| ID | Rule | Protected contract |
|---|---|---|
| C001 | settings-class-configuration-error-placement | Settings validation is dataclass-owned |
| C002 | duplicate-inline-bool-guard-validation | Meaningful bool guards have one validation owner |
| C003 | no-dynamic-import-from-data | Runtime data cannot choose imported modules |
| C004 | operation-pricing-rate-floor | Pricebook rates clear the plausibility floor |
| C005 | cost-arithmetic-site-parity | Cost arithmetic stays in reviewed pricing owners |

## Adding a rule

1. Add one `lint/rules/{s,a,c}NNN_name.py` module exporting `RULE`.
2. Register its number/name pair in `lint/core/registry.py`.
3. Run the focused rule with JSON, inspect representative true positives and
   plausible counterexamples, then initialize its count explicitly.
4. Add the rule to this catalogue and the design document.
5. Run the complete source and package CI gates.

Suppressions and path exceptions are policy changes. Put narrow, named boundary
constants in the owning rule and explain why the boundary is safe; do not scatter
inline ignores through production source.
