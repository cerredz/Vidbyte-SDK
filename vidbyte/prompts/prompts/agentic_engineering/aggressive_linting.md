# Description
Linting is static analysis: a program that reads your source code without running it and rejects code that violates a rule. A linter does not care whether the code works — it cares whether the code is *shaped* the way you decided code in this repository must be shaped. Out of the box, most linters ship a polite, permissive default: a handful of rules, most of them set to "warning," most of them about formatting. That default exists to avoid annoying human developers.

We are going to use linters because a linter is the only place in a codebase where a standard can be made *deterministic*. A code review is a hope. A system-prompt instruction is a hope. A comment that says "please use the repository layer" is a hope. A linter rule that makes the direct database call fail the build is a fact. The linter is the one mechanism that re-evaluates every standard from scratch, on every run, and refuses to forget — which makes it the natural home for any rule you actually want held.

But we are not going to use ordinary linters — we are going to write **aggressive** linters. An aggressive linter is one configured at maximum strictness, with every rule promoted from warning to error, every off-the-shelf escape hatch closed, and a growing folder of *custom* rules that encode the specific mistakes this codebase keeps making. Where an ordinary linter flags a yellow squiggle and lets the code through, an aggressive linter deletes the wrong move from the space of programs you are allowed to express. It is not a style checker bolted on at the end; it is a wall built before the first line of a module is written.

We are doing this because the primary author of the code is now an agent, and an agent is a different kind of author than a human. For a human team, an over-strict linter is a morale problem: developers argue about the rules, disable the checks, and burn out. An agent feels none of that friction — it does not resent a rule, does not argue, and will iterate against feedback all day. The entire human tradeoff between strictness and developer experience collapses, so you can crank strictness far past anything a human team would tolerate. More importantly, an agent's adherence to a prose instruction *decays* as its context window fills — the rule you wrote at token 2,000 is forgotten by token 200,000. A linter rule does not decay. Every standard you can express as a fail-closed check is a piece of your architecture that has been permanently removed from the jurisdiction of the context window. In short: an aggressive linter is a **strict, deterministic guardrail bolted onto an agent's ability to write code** — it constrains what the agent is even able to produce, so correctness stops depending on the agent remembering and starts depending on the build refusing.

Two consequences follow and they govern everything below. First, all rules must be errors, never warnings. A warning is invisible to an agent — there is no social pressure from a yellow squiggle, only a non-zero exit code changes behavior. Second, the error message is a prompt. When a lint failure is fed back into the agent's context window, it is not a diagnostic for a tired human — it is an instruction the model will act on next. Write every message as an imperative to the agent ("Handlers must call the repository layer, not the database directly") rather than a description of the symptom ("raw database access detected").

# Intent
The intent of aggressive linting for agent-native codebases is to make architectural standards, security invariants, and coding conventions hold *permanently* — not through repeated reminders that decay, but through mechanically enforced walls that make violations non-expressible. You are adding a strict, deterministic guardrail to an agent's ability to write code: an agent producing code should encounter your constraints the same way it encounters a type error — as an immediate, specific, actionable rejection that names exactly what to do instead. The guardrail is deterministic because the same input always produces the same verdict, and strict because there is no advisory middle ground for the agent to ignore.

This principle is trying to close the gap between what a system prompt instructs and what code actually gets produced after many iterations. Prose instructions degrade; linter rules do not. By encoding your conventions as fail-closed rules whose messages read as imperative instructions, you turn the linter from a style guide into a correction surface — one that compounds over time as you add codebase-specific rules for every recurring mistake the agent makes. The failure mode this specifically addresses is *silent drift*: an agent that started the session respecting your layering, your blessed wrappers, and your error-handling discipline, and then quietly abandoned all three somewhere in a long context window, with nothing in the build to catch it.

# Goal
You are going to use this skill file to actually **write the aggressive linters** — not to read about them in the abstract, and not to merely run a linter someone else configured. The goal is concrete authorship: given a repository (or a brand-new module inside one), you will produce the real configuration and the real custom rules that turn an ordinary, permissive toolchain into a fail-closed guardrail. That means writing the `pyproject.toml` `[tool.ruff]` and `[mypy]` blocks at maximum strictness, authoring the `.importlinter` contracts that encode the architecture, writing the custom Semgrep rules and standalone AST-based linters that ban this codebase's specific mistakes, and phrasing every message as an instruction the agent will obey on its next turn.

Everything that follows is in service of that authorship. The **Intuition** section frames how to read the menu — as a starting point you generalize from, not a checklist you exhaust. The **Generalized Principles** section gives you that menu of rules to write and the reasoning for each, with a final subsection of principles aimed specifically at very large, high-velocity repositories. The **Updating Linters** section tells you how to keep those rules alive as the codebase grows under you, and the **Code Examples** section gives you complete, copy-ready linters — including a full custom architecture linter you can adapt to a real system. When you finish, the repository should contain linters *you wrote*, and the wrong move should no longer compile.

# Intuition
The generalized principles below are a starting point, not a specification. Each one names a way to convert some standard you care about into a fail-closed, deterministic wall, but the list is deliberately a *minimal subset* of the walls you could build, not the complete set. Treat every principle as one worked example of a single underlying move: find a standard that currently lives in prose, in a reviewer's head, or in a convention nobody enforces, and relocate it into a rule the build re-checks from scratch on every run. The specific Ruff selectors, Semgrep patterns, and import-linter contracts shown are illustrations of that move, chosen because they are common — they are not the boundary of what you should write. When you read "ban `datetime.now()` in the domain layer," the lesson is not that `datetime.now()` is the thing to ban; the lesson is that *any* non-deterministic primitive sitting in a layer that must be testable is a wall waiting to be built. Your job is to generalize from each example to the class of standard it protects, and then ask what other members of that class exist in the repository in front of you. A skill file cannot enumerate your architecture's specific invariants — it can only teach you the shape of a wall so you recognize where one is missing.

So do not stop at the principles enumerated here, and do not treat them as a checklist to satisfy and then declare the linter done. The highest-value rules in any mature aggressive-linting setup are the ones no skill file could have predicted, because they encode a convention specific to this codebase — a naming scheme, a forbidden coupling between two internal services, a required call to an audit hook before every write, a serialization format that must never change. The principles teach you the *technique* — promote to error, phrase the message as an imperative, close the escape hatch, scope to the right paths — and you supply the *content* by studying the actual code, the actual review comments, and the actual mistakes the agent keeps making. Before you finish, deliberately spend effort generating walls that are not on this list: read the existing modules, ask what an experienced engineer on this team would reject in review, and encode each of those rejections as a rule. A useful test of whether you have internalized this section is simple — if your final config contains only rules that map one-to-one onto the principles below, you have under-applied the skill and almost certainly left real, codebase-specific invariants unguarded. Use the examples as the floor of your imagination here, not the ceiling, and always finish by adding at least a few walls that came from the codebase itself rather than from this file.

# Generalized Principles to Follow for Aggressive Linters
These are the principles to follow when writing aggressive linters. Each is a rule-authoring discipline, followed by a 2-3 sentence rationale and 5-6 concrete Python-ecosystem examples (Ruff config, mypy config, import-linter contracts, Semgrep rules scoped to `languages: [python]`, and `bandit` selectors). Treat the principles as the menu of walls to build; treat the examples as starting points you adapt to your repository's real layer names and module paths.

### 1. Promote Every Rule From Warning to Error
A warning is invisible to an agent: there is no social pressure from a yellow squiggle, and the run still exits 0, so the loop closes with the violation intact. Configure the toolchain so that any violation fails the run with a non-zero exit code, and never pass an advisory flag that downgrades a failure. The single most common reason an aggressive linter fails to change agent behavior is that it was left at warning level.
```toml
# pyproject.toml — Ruff has no "warning" tier; a selected rule fails the run.
[tool.ruff.lint]
select = ["E", "F", "W", "B", "S", "C90", "PL", "TRY", "BLE", "DTZ", "PGH"]
# Never set per-file ignores that silently downgrade a real rule to nothing.
```
```ini
# pyproject equivalent for mypy — any error is a non-zero exit; nothing is advisory.
[mypy]
strict = true
warn_return_any = true      # an implicit Any return is an error, not a note
```
```yaml
# Semgrep: severity is always ERROR for a wall. WARNING/INFO get ignored by agents.
rules:
  - id: example-wall
    severity: ERROR           # never WARNING, never INFO
```
```bash
# CI / pre-commit invocation: never neutralize the exit code.
ruff check .                  # good: fails the step on any finding
# ruff check . || true        # forbidden: swallows the exit code
# ruff check --exit-zero .    # forbidden: turns the wall into a no-op
```
```ini
# pylint, if used alongside Ruff: make any message fail the run.
[MASTER]
fail-on = all
fail-under = 10
```

### 2. Write Every Message as an Imperative to the Agent
A lint failure is injected back into the agent's context as the next instruction it will act on, so the message must read as a command, not as a description of the symptom. Name the blessed alternative, state where the correct code belongs, and explain the consequence of the violation. "Use parameterized queries; pass values as the second argument to execute()" produces a fix; "string SQL detected" produces a guess.
```yaml
# Good message: states the fix and the destination.
rules:
  - id: no-raw-db-in-handlers
    pattern: db.query(...)
    paths: { include: ['app/api/**'] }
    message: >
      Handlers must call the repository layer, not the database directly.
      Move this query into a method on the matching repository in app/repositories/
      and call that method from the handler.
    severity: ERROR
    languages: [python]
```
```yaml
# Good: name the wrapper to import instead.
  - id: use-http-wrapper
    pattern: requests.$METHOD(...)
    message: >
      Import app.lib.http and call its client instead of using requests directly.
      The wrapper enforces timeouts, retries, and structured logging.
    severity: ERROR
    languages: [python]
```
```yaml
# Good: explain the consequence so the agent understands the constraint.
  - id: inject-the-clock
    pattern: datetime.now(...)
    paths: { include: ['app/domain/**'] }
    message: >
      Inject a Clock dependency and call clock.now() instead of datetime.now().
      Domain code that reads the wall clock directly cannot be tested deterministically.
    severity: ERROR
    languages: [python]
```
```yaml
# Bad vs good, side by side — the bad message forces the agent to guess.
  - id: no-bare-except
    pattern: |
      try:
        ...
      except:
        ...
    # message: "bare except found"                          # BAD: a diagnostic
    message: >                                              # GOOD: an instruction
      Catch a specific exception type instead of a bare except.
      A bare except also swallows KeyboardInterrupt and SystemExit; name the
      exact exception this block is meant to handle.
    severity: ERROR
    languages: [python]
```
```yaml
# Good: tell the agent the exact replacement symbol.
  - id: no-print
    pattern: print(...)
    paths: { exclude: ['scripts/**', 'tests/**'] }
    message: >
      Replace print() with the structured logger: from app.lib.log import logger;
      logger.info(...). print() output is lost in production and is not structured.
    severity: ERROR
    languages: [python]
```

### 3. Close Every Escape Hatch You Open
A wall with an open bypass is decorative — agents reach for the suppression comment the instant a rule is inconvenient. Ban blanket, file-wide suppressions outright, and force every allowed suppression to name the specific rule it silences plus a reason, so a suppression is never wider than the single violation it covers. Closing escape hatches is the difference between a guardrail and a suggestion.
```toml
# Ruff: require codes on every suppression, ban blanket noqa and bare type: ignore.
[tool.ruff.lint]
extend-select = ["PGH003", "PGH004", "RUF100"]
# PGH003: bare `# type: ignore` (no error code) -> error
# PGH004: blanket `# noqa` (no rule code)      -> error
# RUF100: an unused `# noqa` (suppresses nothing) -> error
```
```ini
# mypy: a `# type: ignore` that silences nothing is itself an error.
[mypy]
warn_unused_ignores = true
disallow_any_explicit = true   # close the explicit `Any` cast that defeats a typed wall
```
```yaml
# Semgrep: ban the file-wide blanket disable that nukes every rule in a file.
rules:
  - id: no-blanket-ruff-noqa
    pattern-regex: '#\s*ruff:\s*noqa\s*$'
    message: >
      Do not disable Ruff for an entire file. Suppress a single line with
      `# noqa: <CODE>` naming the exact rule, and only with a justifying comment.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: ban the module-level flake8 blanket disable.
  - id: no-blanket-flake8-noqa
    pattern-regex: '#\s*flake8:\s*noqa'
    message: >
      Do not disable flake8 for an entire file. Use `# noqa: <CODE>` per line.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: require a reason next to any pragma the agent does keep.
  - id: type-ignore-needs-reason
    pattern-regex: '#\s*type:\s*ignore\[[A-Za-z0-9_-]+\](?!\s*#)'
    message: >
      A `# type: ignore[code]` must be followed by `# reason: <why>` on the same line.
      An unexplained suppression is indistinguishable from a hidden bug.
    severity: ERROR
    languages: [python]
```

### 4. Make the Type Checker the First Wall
A construct the type checker rejects never reaches the linter, never reaches CI, and never reaches a reviewer — every strict flag deletes an entire failure class at the language level, upstream of every other rule. Turn on the strictest available settings and ban the typing escape valves (`Any`, missing annotations, implicit `Optional`) in the same pass. Untyped code is an agent's preferred hiding place for drift, so make "no annotation" itself the error.
```ini
[mypy]
strict = true                    # the umbrella flag; turn it on first
disallow_untyped_defs = true     # every function must be annotated
disallow_incomplete_defs = true  # no half-annotated signatures
```
```ini
[mypy]
disallow_any_generics = true     # ban `list` / `dict` without parameters
no_implicit_optional = true      # `x: int = None` becomes an error
warn_unreachable = true          # code after a return is half-rewritten logic
```
```ini
[mypy]
ignore_missing_imports = false   # a missing module is an error, surfacing hallucinated imports
disallow_untyped_decorators = true
warn_redundant_casts = true
```
```toml
# pyright/basedpyright as the second type wall, in pyproject.
[tool.pyright]
typeCheckingMode = "strict"
reportUnknownMemberType = "error"
reportMissingTypeStubs = "error"
```
```toml
# Ruff's typing-adjacent rules close gaps the checker tolerates.
[tool.ruff.lint]
extend-select = ["ANN", "TCH", "FA"]
# ANN: missing type annotations; TCH: import-time typing hygiene; FA: future annotations
```
```toml
# Ban the typing module's own escape hatches via flake8-tidy-imports.
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"typing.Any".msg = "Model the real type or use a Protocol/TypeVar; Any disables checking."
"typing.cast".msg = "Avoid cast(); narrow with isinstance or fix the upstream type."
```

### 5. Ban Stub and Placeholder Code So "Looks Done" Fails the Build
Agents declare victory prematurely — it is their single most reliable failure mode — and leave `NotImplementedError`, lone `pass`, bare `...`, and `TODO` markers that make an unfinished task pass every test trivially. Make every placeholder a hard failure outside the few places it is legitimate (abstract base methods, `Protocol` bodies, typing stubs). A stub that fails the build cannot masquerade as a completed feature.
```toml
# Ruff: ban TODO/FIXME/HACK/XXX markers (flake8-fixme).
[tool.ruff.lint]
extend-select = ["FIX"]   # FIX001 TODO, FIX002 FIXME, FIX003 XXX, FIX004 HACK
```
```yaml
# Semgrep: ban NotImplementedError outside abstract bases.
rules:
  - id: no-not-implemented-stub
    patterns:
      - pattern: raise NotImplementedError(...)
      - pattern: raise NotImplementedError
    paths: { exclude: ['**/base.py', 'tests/**'] }
    message: >
      Implement this function. NotImplementedError in non-abstract code means the
      task is incomplete. If the method is genuinely abstract, move it to a base
      class and decorate it with @abstractmethod.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: ban a function body that is only `...` outside protocols/stubs.
  - id: no-ellipsis-body
    pattern: |
      def $F(...):
        ...
    paths: { exclude: ['**/*.pyi', '**/protocols.py'] }
    message: >
      Replace the `...` body with a real implementation. An ellipsis body is a stub
      that passes type checking while doing nothing.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: ban a function that only `pass`es (silent no-op).
  - id: no-pass-only-function
    pattern: |
      def $F(...):
        pass
    paths: { exclude: ['tests/**'] }
    message: >
      A function whose entire body is `pass` does nothing. Implement it or delete it.
    severity: ERROR
    languages: [python]
```
```bash
# Vulture: dead code from abandoned agent attempts, detected before it accumulates.
vulture app/ --min-confidence 80
```
```yaml
# Semgrep: ban the "return None # TODO" fake implementation.
  - id: no-todo-return
    pattern-regex: 'return\s+None\s*#\s*(TODO|FIXME|placeholder)'
    message: >
      This is a placeholder return. Implement the real return value before declaring done.
    severity: ERROR
    languages: [python]
```

### 6. Enforce Error-Handling Discipline
Agents hide failures instead of solving them: bare excepts, swallowed exceptions, empty handlers, and lost stack traces. Force every caught exception to name a specific type, force every handler to either handle or re-raise with context, and ban the silent `except: pass` that turns a real failure into a green build. Error handling is where drift is least visible, so it needs the strictest walls.
```toml
# Ruff: ban blind and bare excepts.
[tool.ruff.lint]
extend-select = ["BLE", "E722"]
# BLE001: blind `except Exception`; E722: bare `except:`
```
```toml
# Ruff: tryceratops rules for handler hygiene.
[tool.ruff.lint]
extend-select = ["TRY"]
# TRY002 raise vanilla Exception, TRY300 else-branch, TRY400 use logging.exception, TRY401
```
```toml
# Ruff: preserve the cause chain on re-raise (flake8-bugbear).
[tool.ruff.lint]
extend-select = ["B904"]   # `raise X` inside `except` must use `from err` or `from None`
```
```yaml
# Semgrep: ban the swallowed exception outright.
rules:
  - id: no-swallowed-exception
    pattern: |
      try:
        ...
      except $E:
        pass
    message: >
      Do not silently swallow an exception with `pass`. Either handle it (log and
      recover) or re-raise it. A silent except hides the failure from every caller.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: ban `except ...: return None`, the agent's favorite failure-hider.
  - id: no-except-return-none
    pattern: |
      try:
        ...
      except $E:
        return None
    message: >
      Returning None on exception hides the failure mode from the caller. Raise a
      specific exception or return an explicit Result/error object instead.
    severity: ERROR
    languages: [python]
```

### 7. Force Determinism in Core Layers
Non-deterministic calls — `datetime.now()`, `random`, `uuid4`, `time.time()`, environment reads — in domain and service code make tests non-reproducible and behavior unauditable. Ban them in the core layers so clocks, RNG, and configuration must be injected as dependencies, which makes the code both testable and honest about its I/O. Scope these rules to the core paths so the edges (where wall-clock access is legitimate) are unaffected.
```yaml
rules:
  - id: no-wallclock-in-domain
    patterns:
      - pattern: datetime.now(...)
      - pattern: datetime.utcnow()
    paths: { include: ['app/domain/**', 'app/services/**'] }
    message: >
      Inject a Clock and call clock.now(). Domain/service code must not read the
      wall clock directly or its tests cannot be made deterministic.
    severity: ERROR
    languages: [python]
```
```yaml
  - id: no-random-in-domain
    patterns:
      - pattern: random.random()
      - pattern: random.randint(...)
      - pattern: random.choice(...)
    paths: { include: ['app/domain/**', 'app/services/**'] }
    message: >
      Inject an RNG dependency instead of calling the random module directly.
    severity: ERROR
    languages: [python]
```
```yaml
  - id: no-uuid-in-domain
    pattern: uuid.uuid4()
    paths: { include: ['app/domain/**'] }
    message: >
      Inject an IdGenerator and call generator.new(). Calling uuid4() directly makes
      created entities impossible to assert against in a test.
    severity: ERROR
    languages: [python]
```
```yaml
  - id: no-time-in-domain
    patterns:
      - pattern: time.time()
      - pattern: time.monotonic()
    paths: { include: ['app/domain/**', 'app/services/**'] }
    message: >
      Inject a Clock. Direct time.time() reads make latency-sensitive logic untestable.
    severity: ERROR
    languages: [python]
```
```yaml
  - id: no-env-read-in-domain
    pattern: os.environ[...]
    paths: { include: ['app/domain/**'] }
    message: >
      Domain code must receive configuration as a typed argument, not read os.environ.
      Load config at the edge and pass it down.
    severity: ERROR
    languages: [python]
```
```toml
# Ruff: ban naive (timezone-less) datetimes everywhere (flake8-datetimez).
[tool.ruff.lint]
extend-select = ["DTZ"]   # DTZ001..DTZ012: naive datetime construction and parsing
```

### 8. Guard Against Hallucinated Imports and Names
Agents invent package names, module paths, and symbols from training data that simply do not exist in this repository. Wire checks that fail on any unresolved import, any reference to an undefined name, and any import of a package not declared in the manifest, so a hallucination is caught at lint time rather than at runtime. This is the wall that turns "the agent confidently imported a library that was never installed" into an immediate, specific failure.
```toml
# Ruff: undefined name and import hygiene from pyflakes.
[tool.ruff.lint]
extend-select = ["F821", "F401", "F811"]
# F821 undefined name, F401 unused import (leftover hallucinated import), F811 redefinition
```
```toml
# Ruff: wildcard imports hide where names came from and make agent edits untraceable.
[tool.ruff.lint]
extend-select = ["F403", "F405"]   # from x import * / name may be undefined from star import
```
```toml
# Ruff: unused locals and dead commented code are failed partial edits, not harmless noise.
[tool.ruff.lint]
extend-select = ["F841", "ARG", "ERA001"]   # unused variable, unused args, commented-out code
```
```bash
# deptry: fail on imports of packages not declared as dependencies.
deptry .
# DEP001 missing dependency, DEP003 transitive dependency used directly
```
```ini
# mypy: a module that cannot be resolved is an error, not a silent Any.
[mypy]
ignore_missing_imports = false
follow_imports = normal
```
```toml
# Ruff: ban relative imports that escape the package and hide bad paths.
[tool.ruff.lint]
extend-select = ["TID252"]   # ban relative imports above the current package
```
```yaml
# Semgrep: catch a hallucinated internal module the agent assumed exists.
rules:
  - id: no-unknown-internal-utils
    pattern: from app.utils.magic import $X
    message: >
      app.utils.magic does not exist. Import from app.lib (the real utilities package)
      or create the helper explicitly before importing it.
    severity: ERROR
    languages: [python]
```
```bash
# pip-audit doubles as a sanity check: a hallucinated package will not resolve.
pip-audit --strict
```

### 9. Encode Architecture and Layer Boundaries as Contracts
Declare the layer order once and make a lower layer importing a higher one fail the build, so the architecture diagram becomes a compile gate rather than a convention a tired agent violates. Make cycles mechanically impossible, and isolate sibling features so one feature's internals are unreachable from another even when the relative import is one `../` away. The architecture is the most expensive thing to get wrong and the cheapest thing to wall.
```ini
# .importlinter: a layered contract — higher layers may import lower, never the reverse.
[importlinter]
root_package = app

[importlinter:contract:layers]
name = Layered architecture
type = layers
layers =
    app.api
    app.services
    app.repositories
    app.db
```
```ini
# .importlinter: a forbidden contract — domain may never reach back up to api.
[importlinter:contract:domain-isolation]
name = Domain cannot import API
type = forbidden
source_modules = app.domain
forbidden_modules = app.api
```
```ini
# .importlinter: independence — sibling features cannot import each other.
[importlinter:contract:feature-isolation]
name = Features are independent
type = independence
modules =
    app.features.billing
    app.features.checkout
    app.features.catalog
```
```python
# grimp: no cyclic imports. A cycle means two modules secretly form one unit; merge
# them or split the shared abstraction, but never let the cycle land.
import grimp
graph = grimp.build_graph("app")
for module in graph.modules:
    if module in graph.find_downstream_modules(module):
        raise SystemExit(
            f"{module} participates in an import cycle. Break the cycle before merge."
        )
```
```ini
# import-linter: force public-API-only imports. Outside code imports app.billing,
# never app.billing.internal.helper or any other private implementation file.
[importlinter:contract:billing-public-api-only]
name = Billing internals are private
type = forbidden
source_modules = app.*
forbidden_modules =
    app.billing.internal.*
    app.billing._*
```
```toml
# Ruff: ban the raw db client outside the repository layer (banned-api).
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"app.db.engine".msg = "Only app.repositories may import the engine. Handlers call repositories."
```
```yaml
# Semgrep: ban returning ORM models across a layer boundary.
rules:
  - id: no-orm-models-from-handlers
    pattern: return $MODEL.query...
    paths: { include: ['app/api/**'] }
    message: >
      Handlers must return DTOs, not ORM model instances. Map the model to a
      response schema in app/api/schemas before returning it.
    severity: ERROR
    languages: [python]
```
```bash
# Run the contracts as a build step.
lint-imports   # exits non-zero on any contract violation
```

### 10. Force the Blessed Wrapper, Ban the Raw Library
Agents reach for the raw library they learned from training data — `requests`, `psycopg2`, `boto3`, `logging` — instead of the internal wrapper that enforces retries, pooling, timeouts, and structured logging. Ban the raw import everywhere except inside the wrapper itself, and put the name of the blessed alternative directly in the message. This is one of the highest-leverage agent walls because it redirects the path of least resistance.
```toml
# Ruff: ban raw HTTP libraries in favor of the internal client.
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"requests".msg = "Import app.lib.http instead. The wrapper enforces timeout and retry."
"urllib.request".msg = "Import app.lib.http instead of urllib."
"httpx".msg = "Import app.lib.http instead of raw httpx. The wrapper owns auth, timeout, and retry."
```
```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"psycopg2".msg = "Import app.lib.db instead. Direct clients bypass the pool and query logging."
"asyncpg".msg = "Import app.lib.db instead of asyncpg."
```
```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"boto3".msg = "Import app.lib.aws instead. The wrapper injects credentials and retries."
```
```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"logging.getLogger".msg = "Import the configured logger: from app.lib.log import logger."
"os.getenv".msg = "Read config from app.config.settings, not os.getenv, so types are validated."
```
```yaml
# Semgrep enforces the same wrapper rule with a path exception for the wrapper itself.
rules:
  - id: only-wrapper-imports-requests
    pattern: import requests
    paths: { exclude: ['app/lib/http.py'] }
    message: >
      Only app/lib/http.py may import requests. Everywhere else, import app.lib.http.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: ban the raw file open for config; force the typed loader.
  - id: no-raw-config-open
    pattern: open($PATH)
    paths: { include: ['app/config/**'] }
    message: >
      Use app.config.settings (a validated, typed model) instead of open()-ing a file.
    severity: ERROR
    languages: [python]
```

### 11. Cap Complexity and Size, and Treat a Violation as a Design Signal
A function over the complexity or length cap is not a style nit — it is a signal that the function is doing more than one thing and must be decomposed. Set the caps low, and when a cap fires, redesign the function rather than bumping the cap. The cap is the trigger; the decomposition is the fix, and an agent that never feels friction will happily write the 300-line god-function unless the build refuses it.
```toml
# Ruff: cyclomatic complexity cap (mccabe).
[tool.ruff.lint.mccabe]
max-complexity = 8
```
```toml
[tool.ruff.lint]
extend-select = ["PLR0913"]   # too-many-arguments: a long signature is a missing object
[tool.ruff.lint.pylint]
max-args = 5
```
```toml
[tool.ruff.lint]
extend-select = ["PLR0915"]   # too-many-statements: the function does too much
[tool.ruff.lint.pylint]
max-statements = 40
```
```toml
[tool.ruff.lint]
extend-select = ["PLR0912"]   # too-many-branches: collapse with polymorphism or a table
[tool.ruff.lint.pylint]
max-branches = 10
```
```toml
# Ruff/pylint: a branch condition with too many boolean operators needs a name.
[tool.ruff.lint]
extend-select = ["PLR0916"]   # too-many-boolean-expressions
[tool.ruff.lint.pylint]
max-bool-expr = 4
```
```toml
[tool.ruff.lint]
extend-select = ["PLR0911"]   # too-many-return-statements: a sign of tangled control flow
[tool.ruff.lint.pylint]
max-returns = 6
```
```toml
[tool.ruff.lint]
extend-select = ["PLR2004"]   # magic-value-comparison: name the constant
```
```python
# Custom AST check: max nesting depth. More than three nested if/for/while/try
# blocks is pyramid code; use early returns and extracted functions instead.
import ast

NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)
MAX_DEPTH = 3

class NestingDepthVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        is_nested = isinstance(node, NESTING_NODES)
        if is_nested:
            self.stack.append(node)
            if len(self.stack) > MAX_DEPTH:
                raise SystemExit(
                    f"{node.lineno}: Extract a function or return early; nesting depth exceeds {MAX_DEPTH}."
                )
        super().generic_visit(node)
        if is_nested:
            self.stack.pop()
```
```yaml
# Semgrep: force complex boolean conditions to be named before branching.
rules:
  - id: name-complex-condition
    pattern: |
      if $A and $B or $C:
          ...
    message: >
      Move this compound condition into a named boolean such as user_is_eligible.
      A branch with mixed and/or logic hides the rule the code is enforcing.
    severity: ERROR
    languages: [python]
```

### 12. Ban Dangerous and Non-Auditable Constructs
Some constructs are security holes or make code impossible for an agent to reason about statically: `eval`, `exec`, untrusted `pickle`, `shell=True`, string-built SQL, and weak crypto. Ban them outright so the unsafe form is not even expressible, and the agent can only ship the safe variant. These are the walls where a single missed case is a vulnerability, so there is no advisory tier.
```toml
# Ruff: the bandit security ruleset, surfaced as lint errors.
[tool.ruff.lint]
extend-select = ["S"]   # flake8-bandit
```
```toml
# Specific high-value bans, made explicit so they are never accidentally ignored.
[tool.ruff.lint]
extend-select = ["S102", "S307"]   # exec / eval of dynamic input
```
```toml
[tool.ruff.lint]
extend-select = ["S301", "S302"]   # pickle / marshal loads of untrusted data
```
```toml
[tool.ruff.lint]
extend-select = ["S602", "S605"]   # subprocess / os.system with shell=True
```
```toml
[tool.ruff.lint]
extend-select = ["S324"]           # weak hash (md5, sha1) used as if secure
```
```toml
# Ruff: no print()/pprint() statements in application code. Use the structured logger.
[tool.ruff.lint]
extend-select = ["T20"]
```
```yaml
# Semgrep: ban string-interpolated SQL, the root of injection.
rules:
  - id: no-string-built-sql
    patterns:
      - pattern: $CUR.execute("..." % ...)
      - pattern: $CUR.execute("..." + ...)
      - pattern: $CUR.execute(f"...")
    message: >
      Use parameterized queries: pass values as the second argument to execute().
      String-built SQL is the root cause of SQL injection.
    severity: ERROR
    languages: [python]
```

### 13. Gate Test Integrity
Agents find the cheapest way to make a red suite look green: skip the failing test, focus a passing subset, assert nothing, or mock the very thing under test. Ban each cheat with a rule, and judge coverage on the *diff* rather than the whole repo so a new untested change cannot hide inside a well-covered file. A test suite the agent can trivially defeat provides no signal at all.
```yaml
# Semgrep: ban skip/xfail added to silence a failing test.
rules:
  - id: no-skipped-tests
    patterns:
      - pattern: "@pytest.mark.skip"
      - pattern: "@pytest.mark.xfail"
    paths: { include: ['tests/**'] }
    message: >
      Do not skip or xfail a test to make the suite pass. Fix the code under test,
      or delete the test if the behavior is genuinely gone.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: a test that asserts nothing passes trivially and proves nothing.
  - id: test-must-assert
    patterns:
      - pattern: |
          def test_$NAME(...):
            ...
      - pattern-not: |
          def test_$NAME(...):
            ...
            assert ...
      - pattern-not-inside: |
          def test_$NAME(...):
            ...
            with pytest.raises(...): ...
    paths: { include: ['tests/**'] }
    message: >
      Every test must assert something or use pytest.raises. A test with no
      assertion only proves the code did not crash.
    severity: ERROR
    languages: [python]
```
```toml
# Ruff: pytest-style integrity rules.
[tool.ruff.lint]
extend-select = ["PT"]   # flake8-pytest-style: fixtures, parametrize, raises hygiene
```
```toml
# Ruff: ban `assert False` and always-false asserts that fake a failing guard.
[tool.ruff.lint]
extend-select = ["B011", "PT015"]
```
```bash
# diff-cover: coverage judged on changed lines only, regardless of repo coverage.
diff-cover coverage.xml --compare-branch origin/main --fail-under 90
```
```bash
# Coverage ratchet: record today's coverage as the floor. Future PRs may raise the
# floor, but a drop fails the build even when the absolute number still looks high.
test -f .coverage-floor || python -m coverage report --format=total > .coverage-floor
test "$(python -m coverage report --format=total)" -ge "$(cat .coverage-floor)" \
  || { echo "Coverage dropped below the recorded floor; add tests or raise coverage."; exit 1; }
```
```bash
# mutmut: a mutation-testing floor — a suite that survives mutations is not testing.
mutmut run && mutmut results
```

### 14. Encode Every Recurring Mistake as a Checked-In Custom Rule
This is the one wall with no off-the-shelf equivalent and the one that compounds the most: every time the agent repeats a codebase-specific mistake, write a single Semgrep rule (or AST check) that bans exactly that pattern and commit it. A growing `rules/` folder becomes a codebase-specific immune system that a competitor cannot copy off the shelf and that decays far slower than a system-prompt reminder. Write the rule on the *second* occurrence — one occurrence is noise, two is a pattern.
```yaml
# rules/no-raw-db-in-handlers.yaml — the canonical recurring-mistake rule.
rules:
  - id: no-raw-db-in-handlers
    pattern: db.query(...)
    paths: { include: ['app/api/**'] }
    message: >
      Handlers must call the repository layer, not the database directly.
      Move this query to a repository in app/repositories/.
    severity: ERROR
    languages: [python]
```
```yaml
# rules/no-private-cross-module.yaml — ban reaching into another module's privates.
  - id: no-cross-module-private-access
    pattern: $MOD._$NAME(...)
    message: >
      Do not call another module's underscore-prefixed (private) function. Add a
      public function to that module's interface and call it instead.
    severity: ERROR
    languages: [python]
```
```yaml
# rules/no-assert-for-validation.yaml — asserts vanish under python -O.
  - id: no-assert-for-runtime-validation
    pattern: assert $COND, $MSG
    paths: { include: ['app/api/**', 'app/services/**'] }
    message: >
      Do not use assert for runtime validation; it is stripped under python -O.
      Raise a specific exception (e.g. ValidationError) instead.
    severity: ERROR
    languages: [python]
```
```yaml
# rules/no-mutable-default-arg.yaml — a classic Python footgun agents reproduce.
  - id: no-mutable-default-arg
    patterns:
      - pattern: def $F(..., $ARG=[], ...): ...
      - pattern: def $F(..., $ARG={}, ...): ...
    message: >
      Do not use a mutable default argument; it is shared across calls. Default to
      None and create the list/dict inside the function body.
    severity: ERROR
    languages: [python]
```
```toml
# Ruff/bugbear: catch the common mutable-default and call-in-default footguns before
# writing a custom rule. The Semgrep rule above stays as a codebase-owned backstop.
[tool.ruff.lint]
extend-select = ["B006", "B008"]
```
```yaml
# rules/no-broad-pydantic-any.yaml — codebase rule learned from a real drift.
  - id: no-any-in-pydantic-models
    pattern: |
      class $M(BaseModel):
        ...
        $FIELD: Any
    message: >
      Model the real field type. An `Any` field in a Pydantic model disables the
      validation the model exists to provide.
    severity: ERROR
    languages: [python]
```
```text
rules/
  no-raw-db-in-handlers.yaml
  no-private-cross-module.yaml
  no-assert-for-validation.yaml
  no-mutable-default-arg.yaml
  no-any-in-pydantic-models.yaml
# The folder is the codebase's accumulated, permanent memory of every repeated mistake.
```

### 15. Make Coverage Fail-Closed — Default-Deny the Ungoverned Gaps
A wall only protects the surface it is pointed at; everything the linter cannot see or does not recognize passes by default, and that ungoverned surface is exactly where an agent's drift hides. Invert the default so anything the linter cannot analyze — an unparseable file, a new top-level package with no contract, a file type no rule covers, a stray module outside the known roots — fails the build instead of slipping through silently. The discipline is to make every gap in coverage a loud failure, so new surface area can never become a quiet exemption.
```toml
# Ruff: force-exclude means an excluded path can never be silently re-included by
# an editor integration or a stray per-file flag — exemptions are deliberate, narrow.
[tool.ruff]
force-exclude = true
extend-exclude = ["generated/"]   # the ONLY exempt dir; everything else is linted
```
```bash
# Fail-closed on unparseable input: a file that does not parse is a violation, not a
# file to skip. Ruff exits non-zero on a syntax error (E999) — never downgrade it.
ruff check .
```
```python
# CI guard: every top-level package must be governed by an architecture contract.
# A package added without one fails the build before any code lands inside it.
import pathlib
contracts = pathlib.Path(".importlinter").read_text()
packages = {p.name for p in pathlib.Path("app").iterdir() if (p / "__init__.py").exists()}
ungoverned = {p for p in packages if p not in contracts}
assert not ungoverned, (
    f"Ungoverned packages: {sorted(ungoverned)}. Add an import-linter contract "
    f"for each before writing code in it."
)
```
```yaml
# Semgrep: a whole-file `# type: ignore` opt-out is a coverage hole, not a suppression.
rules:
  - id: no-file-level-type-ignore
    pattern-regex: '^#\s*type:\s*ignore\s*$'
    message: >
      Do not opt an entire file out of type checking. Remove this and fix the types,
      or suppress one line with `# type: ignore[code]  # reason: ...`.
    severity: ERROR
    languages: [python]
```
```ini
# mypy: an unresolved module must be an error, not a silent Any that hides a whole
# unchecked file from the type wall.
[mypy]
ignore_missing_imports = false
follow_imports = normal
disallow_untyped_calls = true   # calling into an ungoverned, untyped module fails
```
```bash
# Fail if any source file lives outside the known, allow-listed package roots — new
# code must land in a governed location, not a stray top-level file.
git ls-files 'app/*.py' | grep -vE '^app/(api|services|domain|lib|repositories)/' \
  && { echo "Source outside a governed package root — move it into one."; exit 1; } || true
```

### 16. Pin the Toolchain So the Verdict Is Reproducible
The entire value proposition is determinism — the same input always producing the same verdict — and a floating linter version silently breaks it: identical code passes today and fails next week when the tool auto-updates, or a rule the agent relied on quietly disappears. Pin every tool, plugin, and rule pack to an exact version so the wall is a fixed function of the code, not of whatever happened to be on `PATH` that day. An agent that gets a different verdict on unchanged code learns the linter is noise and stops running it.
```toml
# Ruff: pin the exact version the config was written against; a different Ruff is a
# different ruleset. required-version fails the run on a mismatch.
[tool.ruff]
required-version = "0.6.9"
```
```yaml
# pre-commit: pin every `rev` to an exact tag, never a moving branch. Bump deliberately.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks: [{ id: ruff }, { id: ruff-format }]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks: [{ id: mypy }]
```
```toml
# Lock the linters as version-pinned dev dependencies, never "latest".
[project.optional-dependencies]
lint = ["ruff==0.6.9", "mypy==1.11.2", "import-linter==2.1", "semgrep==1.86.0"]
```
```bash
# CI installs from the lockfile, so the agent's local verdict equals CI's verdict.
uv sync --frozen --only-group lint     # never `pip install -U ruff mypy`
```
```bash
# Vendor third-party Semgrep rules at a pinned commit instead of `--config=auto`
# (which changes under you). The rule pack becomes an artifact you version and diff.
semgrep --config rules/ --error        # local rules only; nothing fetched at runtime
```
```ini
# Pin plugin versions too — a plugin bump silently changes inference. (requirements-lint.txt)
mypy==1.11.2
pydantic==2.8.2          # the mypy plugin's behavior is tied to this exact version
```

### 17. Ratchet the Standard; Never Loosen It
You will almost never get to switch a strict rule on against a clean repository — the realistic move is to adopt the rule with a recorded baseline of existing violations and then forbid the count from ever growing. New code is held to the strict standard while legacy debt is grandfathered, and every decomposition lets you tighten a cap one notch, a ratchet that only ever moves toward stricter. The rule you can never adopt because "it lights up 4,000 existing lines" is exactly the rule a baseline lets you adopt today.
```bash
# Record a baseline count; CI fails if violations grow. Legacy debt is grandfathered,
# new debt is blocked, and the number only ever shrinks.
count=$(ruff check app/ --statistics --output-format=concise | awk '{s+=$1} END{print s+0}')
test "$count" -le "$(cat .lint-baseline)" || { echo "New lint debt — fix it or decompose."; exit 1; }
```
```bash
# In the loop, lint only the changed lines; the merge gate still runs the whole suite.
ruff check $(git diff --name-only --diff-filter=ACM origin/main -- '*.py')
```
```bash
# Coverage judged on the diff, not the repo — a new untested change cannot hide inside
# a well-covered legacy file.
diff-cover coverage.xml --compare-branch origin/main --fail-under 90
```
```ini
# mypy: grandfather a legacy package with a per-module override, then delete the
# override (not weaken the global) as the package is cleaned. The list only shrinks.
[mypy]
strict = true
[mypy-app.legacy.billing.*]
disallow_untyped_defs = false   # TODO(remove): tracked debt; never add new entries
```
```toml
# Caps are a one-way ratchet: after a hotspot is decomposed, lower the cap so the
# build holds the new baseline and the god-function cannot return.
[tool.ruff.lint.mccabe]
max-complexity = 6      # was 8; lowered after app/services was decomposed
```
```python
# Path-aware ratchet: newly added files must pass the full ruleset with zero
# exceptions, even where legacy files are grandfathered by the baseline.
import subprocess, sys
added = subprocess.run(["git", "diff", "--name-only", "--diff-filter=A", "origin/main"],
                       capture_output=True, text=True).stdout.split()
py = [f for f in added if f.endswith(".py")]
if py and subprocess.run(["ruff", "check", *py]).returncode:
    sys.exit("New files must pass the full ruleset with no grandfathering.")
```

### 18. Prefer Deterministic Autofix Over Agent Feedback
Some violation classes have exactly one correct resolution — import order, formatting, trivially-safe modernizations — and routing those through the agent's context window wastes tokens and invites a "creative" choice where none exists. Apply every deterministic fix mechanically before the agent ever sees a diagnostic, so the agent's limited attention is spent only on rules that require judgment. The fix it cannot get wrong should never become feedback it has to act on.
```toml
# Ruff: apply deterministic fixes automatically; only un-fixable findings become
# feedback the agent must reason about.
[tool.ruff]
fix = true
[tool.ruff.lint]
extend-select = ["I", "UP"]          # import-sort + safe modernizations are never agent decisions
```
```bash
# Run the mechanical pass FIRST, then lint. The agent only ever sees the residue
# that actually needs judgment.
ruff format .            # formatting is settled, never a diff the agent argues about
ruff check --fix .       # safe autofixes applied
ruff check .             # what remains is the real work
```
```toml
# Keep autofix to *safe* fixes; a fix that can change behavior still goes to the agent.
[tool.ruff.lint]
extend-safe-fixes = ["I", "UP"]
unfixable = ["ERA001"]   # do not silently delete commented-out code — make the agent decide
```
```yaml
# pre-commit: order the auto-fixing hooks before the judgment hooks, so a commit is
# auto-normalized and only real violations block.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff-format
      - id: ruff
        args: [--fix]
```
```toml
# The formatter config is itself a wall: pin one style so two agents never produce
# two different formattings of the same code and thrash the diff.
[tool.ruff.format]
quote-style = "double"
line-ending = "lf"
```
```bash
# In the agent loop, a changed file re-enters already normalized, so no turn is spent
# on whitespace or import order.
ruff format "$CHANGED" && ruff check --fix "$CHANGED"
```

### 19. Ban Import-Time Side Effects
Agents routinely put real work — network calls, file reads, database connections, environment lookups — at module top level or in `__init__`, which runs at import time and makes startup order load-bearing, tests non-isolable, and behavior non-deterministic. Force all such work into functions that run when called, so importing a module is always free and side-effect-free. This is the determinism principle (#7) applied to *when* code runs, not *what* it computes.
```python
# Custom AST check: a module-level expression statement that is a Call is import-time
# work. Allowed at module scope: imports, assignments, defs, classes, docstrings.
import ast, pathlib
def check(path: str) -> list[int]:
    tree = ast.parse(pathlib.Path(path).read_text())
    bad = [s.lineno for s in tree.body
           if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)]
    for ln in bad:
        print(f"{path}:{ln} — [import-time-call] Move this call into a function. "
              f"Module-level calls run at import and break test isolation.")
    return bad
```
```yaml
# Semgrep: ban I/O executed at module load.
rules:
  - id: no-io-at-import
    patterns:
      - pattern-either:
          - pattern: requests.$M(...)
          - pattern: open(...)
          - pattern: $DB.connect(...)
      - pattern-not-inside: "def $F(...): ..."
      - pattern-not-inside: "class $C: ..."
    message: >
      Do not perform I/O at import time. Move this into a function or a lazily called
      factory; importing a module must have no side effects.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: __init__.py should re-export, not execute. A call there runs on import.
  - id: no-call-in-package-init
    pattern-regex: '^\s*[a-zA-Z_][\w.]*\([^)]*\)\s*$'
    paths: { include: ['**/__init__.py'] }
    message: >
      __init__.py must only re-export, not run setup. Move work into an explicit
      init() the application calls, so importing the package is free.
    severity: ERROR
    languages: [python]
```
```text
# The canonical anti-pattern an agent reproduces (engine opened at import):
#   BAD:  engine = create_engine(DATABASE_URL)            # runs the moment you import
#   GOOD: def get_engine() -> Engine:                     # runs only when called
#             return create_engine(settings.database_url)
```
```toml
# Ruff: forbid stray top-level expressions and global-statement misuse that smuggle
# in import-time state.
[tool.ruff.lint]
extend-select = ["B018", "PLW0603"]   # useless top-level expression; global misuse
```
```yaml
# Semgrep: ban a network/DB client constructed at module scope.
  - id: no-client-at-module-scope
    patterns:
      - pattern: $X = $CLIENT(...)
      - pattern-not-inside: "def $F(...): ..."
      - metavariable-regex: { metavariable: $CLIENT, regex: '.*(Client|Engine|Session|Connection)$' }
    message: >
      Construct clients inside a function or dependency provider, not at import time.
      A module-scope connection opens a socket the instant the module is imported.
    severity: ERROR
    languages: [python]
```

### 20. Enforce Async and Concurrency Correctness
Agents write `async def` and then call blocking I/O inside it, forget to `await` a coroutine, or omit timeouts entirely — each produces code that type-checks and then stalls the event loop or hangs a worker under load. Turn on the async ruleset and add custom rules for the blocking calls and missing timeouts specific to your stack, so concurrency bugs fail at lint time instead of in production. This is a failure class the type checker mostly cannot see and no human reviewer reliably catches.
```toml
# Ruff: the flake8-async ruleset catches the most common async footguns.
[tool.ruff.lint]
extend-select = ["ASYNC"]
# ASYNC100 blocking sleep in async, ASYNC210 blocking HTTP call, ASYNC230 blocking open()
```
```toml
# Ruff: an async function that never awaits is almost certainly wrong, and a created
# task with no kept reference can be garbage-collected mid-flight.
[tool.ruff.lint]
extend-select = ["RUF029", "RUF006"]   # unused-async; un-stored asyncio.create_task
```
```yaml
# Semgrep: ban a blocking call inside an async function (event-loop stall).
rules:
  - id: no-blocking-call-in-async
    patterns:
      - pattern-inside: "async def $F(...): ..."
      - pattern-either:
          - pattern: time.sleep(...)
          - pattern: requests.$M(...)
    message: >
      Do not call a blocking function inside an async coroutine; it stalls the event
      loop. Use asyncio.sleep / the async client (app.lib.http.aclient).
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: every outbound request must carry an explicit timeout.
  - id: require-timeout
    patterns:
      - pattern: httpx.$M(...)
      - pattern-not: httpx.$M(..., timeout=...)
    message: >
      Pass an explicit timeout= to every outbound request. A timeout-less call can
      hang a worker indefinitely under load.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: ban fire-and-forget tasks that drop their reference.
  - id: no-fire-and-forget-task
    patterns:
      - pattern: asyncio.create_task(...)
      - pattern-not-inside: "$VAR = asyncio.create_task(...)"
    message: >
      Keep a reference to the created task (assign it or add it to a task set); a
      fire-and-forget task can be garbage-collected before it completes.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: ban shared mutable module-level state touched from async code (a race).
  - id: no-global-mutation-in-async
    patterns:
      - pattern-inside: "async def $F(...): ..."
      - pattern: global $G
    message: >
      Do not mutate module-level globals from a coroutine; concurrent tasks race on
      it. Pass state explicitly or guard it with an asyncio.Lock.
    severity: ERROR
    languages: [python]
```

### 21. Ban Hardcoded Secrets and Inlined Configuration
Agents inline API keys, tokens, connection strings, and magic endpoints copied straight from documentation examples, baking credentials and environment-specific values into source where they leak and cannot be rotated. Ban string literals that look like secrets and force every credential and endpoint through typed configuration, so a hardcoded key fails the build rather than reaching a commit. This is distinct from the dangerous-construct bans (#12): the construct is harmless, the embedded value is the hazard.
```toml
# Ruff (flake8-bandit): hardcoded password/secret as a string, an argument, or a default.
[tool.ruff.lint]
extend-select = ["S105", "S106", "S107"]
```
```yaml
# pre-commit: an entropy/secret scanner as a second, content-based wall.
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks: [{ id: gitleaks }]
```
```yaml
# Semgrep: ban credential-shaped literals (AWS keys, bearer tokens, URLs with creds).
rules:
  - id: no-hardcoded-credentials
    pattern-regex: '(AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._-]{20,}|://[^:@/\s]+:[^@/\s]+@)'
    message: >
      Do not hardcode credentials. Load this from app.config.settings (a typed,
      env-backed model) so it can be rotated and never lands in git history.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: force endpoints through config instead of inline literals.
  - id: no-inline-endpoint
    pattern-regex: '"https?://(?!localhost|127\.0\.0\.1)[^"]+"'
    paths: { exclude: ['tests/**', 'docs/**'] }
    message: >
      Move this URL into app.config.settings. Inlined endpoints cannot be pointed at
      staging vs prod and become load-bearing magic strings.
    severity: ERROR
    languages: [python]
```
```toml
# Ruff: config must be one typed model, not os.getenv scattered through the code.
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"os.getenv".msg  = "Read app.config.settings instead; raw getenv skips type validation."
"os.environ".msg = "Read app.config.settings instead of os.environ."
```
```yaml
# Semgrep: a high-entropy value assigned to a credential-shaped name is a leak.
  - id: no-secret-assigned-to-suspicious-name
    pattern-regex: '(?i)(api_?key|secret|token|password)\s*=\s*["''][^"'']{12,}["'']'
    message: >
      This looks like a hardcoded secret. Move it to app.config.settings and read it
      from the environment; never commit a literal credential.
    severity: ERROR
    languages: [python]
```

## Principles for Very Large, High-Velocity Repositories
The principles above hold at any size, but a very large repository under a fast agent changes the failure modes enough to need their own walls. When an agent can add thousands of lines across dozens of packages in a single session, the binding constraints stop being "is there a rule for this mistake" and become "does the linter still run inside the agent's loop, did a new import quietly couple two subsystems, and is the package graph still acyclic after a hundred fast edits." The walls below keep a giant, rapidly-growing codebase governable: they treat lint latency as a correctness property, the dependency graph as a first-class artifact to constrain, and growth itself as something to budget. Author them when the repository is large or you expect it to become large — they compound hardest exactly where a human team would have lost the thread, and Example 3 below implements most of them in one standalone linter.

### 22. Lint the Diff in the Loop, Gate the Whole at Merge
At scale you cannot re-lint millions of lines on every agent turn — it is too slow to stay in the loop, and the agent routes around a linter that makes it wait — but you also cannot let the merge gate check only the diff, because one file's change can break an invariant in another. Split it: the inner loop lints the changed surface for fast, local feedback, and the merge gate runs the entire suite, including the whole-graph contracts, before anything lands. The agent gets sub-second correction while it works, and the repository-wide invariants are still proven before merge.
```bash
# Inner loop: lint only what changed, for fast feedback during generation.
files=$(git diff --name-only --diff-filter=ACM origin/main -- '*.py')
ruff check $files && mypy $files
```
```bash
# Merge gate: the whole suite, including cross-file contracts, must pass.
ruff check . && mypy app/ && lint-imports && semgrep --config rules/ --error
```
```bash
# Architecture contracts are inherently whole-graph; never scope them to the diff.
# A diff that looks clean can still introduce a cycle two packages away.
lint-imports                      # full-graph; merge gate only
```
```yaml
# pre-commit runs hooks on staged files (the fast path); CI runs the same hooks with
# --all-files (the full-tree gate). One config, two scopes.
default_stages: [pre-commit]
```
```bash
# Make the loop fast by targeting the package that changed, not the whole monorepo.
pkg=$(git diff --name-only origin/main | grep -oE '^app/[^/]+' | sort -u)
ruff check $pkg && mypy $pkg
```
```bash
# Both paths invoke the SAME entrypoint so they can never diverge — a green loop and
# a red merge would teach the agent to distrust the linter.
make lint-fast    # ruff/mypy on the changed files
make lint-all     # ruff/mypy/import-linter/semgrep on the whole tree, same config
```

### 23. Make the Linter Fast Enough to Stay in the Loop — Cache, Parallelize, Shard
On a large tree, lint latency is not a convenience issue but a correctness one: a suite that takes ten minutes gets skipped, and a wall nobody runs is not a wall. Treat speed as a hard requirement — cache results by file content hash, parallelize across cores, and shard the ruleset by path so each file runs only the checks that apply — so the full linter finishes inside the agent's iteration budget. The fastest linter that actually runs every loop beats the thorough one that gets disabled.
```bash
# Ruff is Rust-fast and caches by default; persist the cache so only changed files
# are re-analyzed across runs and in CI.
export RUFF_CACHE_DIR=.ruff_cache
ruff check .
```
```ini
# mypy: use the daemon (dmypy) in the loop for near-instant incremental re-checks,
# and keep the on-disk cache between runs.
[mypy]
incremental = true
sqlite_cache = true
cache_fine_grained = true
```
```bash
# Parallelize the slow checkers across cores.
semgrep --config rules/ --jobs 8 --error
pytest -n auto                          # pytest-xdist for the test-integrity gate
```
```python
# Content-hash cache for a custom linter: skip files whose (hash + ruleset version)
# is unchanged since the last clean run. On a big tree a full pass becomes near-no-op.
import hashlib, json, pathlib
RULESET_VERSION = "7"
cache = json.loads(pathlib.Path(".archlint_cache").read_text() or "{}")
def unchanged(p: pathlib.Path) -> bool:
    key = hashlib.sha256(p.read_bytes()).hexdigest() + ":" + RULESET_VERSION
    return cache.get(str(p)) == key
```
```toml
# Shard rules by path so a file runs only the walls that apply to its area; Ruff
# resolves the nearest config. (app/domain/ruff.toml)
extend = "../../pyproject.toml"
[lint]
extend-select = ["DTZ"]     # determinism walls only matter in the core layers
```
```bash
# Set a hard time budget; blowing it means shard/cache harder, never disable. A
# linter outside the loop budget is a linter that gets turned off.
timeout 120 make lint-all || { echo "lint exceeded budget — shard or cache, do not skip"; exit 1; }
```

### 24. Enforce Package Encapsulation with a Declared Dependency Graph
In a repository of hundreds of packages, layers are not enough — what keeps the graph from collapsing into a big ball of mud is that each package exposes a small public surface and may depend only on packages it has explicitly declared. Force every cross-package import through the target's public interface, never its internals, and make any dependency edge not in the declared manifest fail the build. The agent, which cannot hold the whole graph in context, is then physically unable to wire the coupling a human would have caught in review.
```toml
# tach: declare each package's public interface and allowed dependencies; an
# undeclared edge or a reach into internals fails. Built for Python monorepos. (tach.toml)
[[modules]]
path = "app.billing"
depends_on = ["app.payments", "app.shared"]
strict = true            # only app/billing/__init__ exports are importable from outside
```
```ini
# import-linter: other packages may use the public api module only, never internals.
[importlinter:contract:billing-encapsulation]
name = Billing internals are private
type = forbidden
source_modules = app.*
forbidden_modules = app.billing.internal.*
```
```ini
# import-linter: independence scales to "these subsystems never import each other."
[importlinter:contract:subsystem-independence]
name = Subsystems are independent
type = independence
modules =
    app.billing
    app.search
    app.messaging
    app.identity
```
```python
# CI: assert the package graph is acyclic with grimp (import-linter's engine). One
# agent-added back-edge two packages away is invisible in a diff but fatal.
import grimp
graph = grimp.build_graph("app")
for module in graph.modules:
    if module in graph.find_downstream_modules(module):
        raise SystemExit(f"{module} is part of an import cycle. Break it before merge.")
```
```bash
# tach enforces every boundary as a single fast command across the whole monorepo.
tach check
```
```toml
# Ruff: ban relative imports that escape the package — the syntactic form of a
# boundary violation — so internals stay reachable only by their public path.
[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"
```

### 25. Cap Fan-Out and Forbid New Cross-Subsystem Edges
An agent generating code quickly reaches for whatever import satisfies the immediate need, and at scale that reflex steadily increases coupling — a module that imports forty others, or a brand-new edge between two subsystems that were independent yesterday. Put metrics on the import graph as walls: cap how many modules one module may depend on, and fail any dependency edge that was not in the baseline unless it is explicitly allow-listed. This bounds the blast radius of any single change and keeps the coupling an agent can introduce per turn finite.
```python
# Cap fan-out: a module importing more than N internal modules is doing too much.
import grimp
graph = grimp.build_graph("app")
CAP = 15
for m in graph.modules:
    internal = {d for d in graph.find_modules_directly_imported_by(m) if d.startswith("app.")}
    if len(internal) > CAP:
        raise SystemExit(
            f"{m} imports {len(internal)} internal modules (cap {CAP}). "
            f"Split it or hide dependencies behind a facade."
        )
```
```python
# Freeze the edge set: any cross-subsystem import not in the recorded allow-list
# fails. New coupling must be a deliberate, reviewed addition to the manifest.
import json, grimp
allowed = {tuple(e) for e in json.load(open("allowed_edges.json"))}
graph = grimp.build_graph("app")
for src in graph.modules:
    for tgt in graph.find_modules_directly_imported_by(src):
        edge = (src.split(".")[1], tgt.split(".")[1])
        if tgt.startswith("app.") and edge[0] != edge[1] and edge not in allowed:
            raise SystemExit(f"New cross-subsystem edge {edge}. Add it to allowed_edges.json "
                             f"with a reason, or remove the import.")
```
```ini
# import-linter: lock independence so a new edge between two subsystems is a hard
# fail, not a metric to eyeball.
[importlinter:contract:no-new-coupling]
name = Payments and Search never couple
type = independence
modules =
    app.payments
    app.search
```
```python
# Detect a god module by fan-in: if everything imports it, a change has unbounded
# blast radius. Flag it for decomposition.
import grimp
graph = grimp.build_graph("app")
for m in graph.modules:
    if len(graph.find_modules_that_directly_import(m)) > 40:
        raise SystemExit(
            f"{m} is imported by 40+ modules. Split this god module before a change "
            f"here becomes repo-wide blast radius."
        )
```
```bash
# Ratchet a package's fan-out: the dependency count may only shrink.
test "$(python -c 'import grimp;g=grimp.build_graph("app");print(len(g.find_modules_directly_imported_by("app.billing")))')" \
  -le "$(cat .billing-fanout-baseline)"
```
```toml
# Ruff: cap argument/positional fan-in at the function level too — a long signature
# is a missing object.
[tool.ruff.lint]
extend-select = ["PLR0913", "PLR0917"]   # too-many-arguments / too-many-positional
[tool.ruff.lint.pylint]
max-args = 5
```

### 26. Treat Volume as a Violation — Budget Size and Dependencies
A fast agent's natural failure mode is bloat: 1,500-line modules, classes with sixty methods, functions that accumulate every special case, and a dependency list that grows every time a new library is momentarily convenient. Put hard budgets on size and dependency surface — module length, class size, public-symbol count, third-party dependency count — and treat exceeding them as a build failure that triggers decomposition, not a number to bump. Unchallenged growth is how a large repository becomes unmaintainable one reasonable-looking commit at a time.
```ini
# pylint: hard caps on module and class size; over the cap means decompose.
[DESIGN]
max-module-lines = 500
max-public-methods = 20
max-attributes = 12
max-parents = 4
```
```python
# Custom AST check: cap total methods per class, not just public methods. A class
# with thirty methods is a subsystem pretending to be one object.
import ast, pathlib
MAX_METHODS = 20
for path in pathlib.Path("app").rglob("*.py"):
    tree = ast.parse(path.read_text())
    for node in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if len(methods) > MAX_METHODS:
            raise SystemExit(
                f"{path}:{node.lineno} {node.name} has {len(methods)} methods "
                f"(cap {MAX_METHODS}). Split responsibilities into smaller classes."
            )
```
```toml
# Ruff: function-level size caps — a long function is a missing decomposition.
[tool.ruff.lint]
extend-select = ["PLR0915", "PLR0912"]   # too-many-statements / too-many-branches
[tool.ruff.lint.pylint]
max-statements = 40
max-branches = 10
```
```bash
# deptry: fail on unused, missing, or transitively-used dependencies — the dependency
# surface is budgeted, not append-only.
deptry .
```
```bash
# Cap the third-party dependency count itself; a new runtime dep must be deliberate.
test "$(python -c 'import tomllib;print(len(tomllib.load(open("pyproject.toml","rb"))["project"]["dependencies"]))')" \
  -le "$(cat .dep-budget)" || { echo "Dependency budget exceeded — justify and raise it, or drop the dep."; exit 1; }
```
```python
# Budget package size by file count; a package sprawling past the cap is split into
# sub-packages with their own boundaries.
import pathlib
for pkg in pathlib.Path("app").iterdir():
    n = len(list(pkg.rglob("*.py"))) if pkg.is_dir() else 0
    if n > 60:
        print(f"{pkg} has {n} modules (cap 60). Split it into sub-packages with their own contracts.")
```
```bash
# Track total LOC as a budget signal (scc/tokei are fast on huge trees).
scc --no-cocomo app/    # compare the Python line count against a recorded ceiling
```
```bash
# PR volume budget: too many new files or lines in one change is itself review risk.
added_files=$(git diff --name-only --diff-filter=A origin/main -- 'app/**/*.py' | wc -l)
added_lines=$(git diff --numstat origin/main -- 'app/**/*.py' | awk '{s+=$1} END{print s+0}')
test "$added_files" -le 12 -a "$added_lines" -le 800 \
  || { echo "This PR adds too much surface area; split it before merge."; exit 1; }
```

### 27. Block Reinvention — Lint for Duplicates and Redirect to Existing Utilities
The defining constraint of a large repo under an agent is that the agent cannot see the whole codebase, so it re-implements helpers, validators, and clients that already exist — quietly forking behavior and multiplying maintenance. Run duplication and similarity detection as a gate, and turn the highest-value repeated utilities into banned-api rules that name the canonical implementation, so "write it again" becomes "import the one that exists." This is the recurring-mistake pipeline (#14) aimed at reinvention rather than misuse.
```toml
# pylint: fail on duplicated blocks across the repo (the similarity checker).
[SIMILARITIES]
min-similarity-lines = 8
ignore-imports = yes
# run: pylint --disable=all --enable=duplicate-code app/
```
```bash
# jscpd: a language-aware copy-paste detector as a CI gate on the whole tree.
jscpd app/ --min-lines 10 --threshold 0   # non-zero exit on any clone over threshold
```
```toml
# Once a canonical utility exists, ban the raw re-implementation by name and point
# at it — reinvention becomes an import.
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"hashlib.sha256".msg = "Use app.lib.hashing.stable_hash; it pins the salt and encoding the codebase standardized on."
```
```yaml
# Semgrep: detect a re-implemented helper by shape and redirect to the blessed one.
rules:
  - id: use-existing-retry
    pattern: |
      for $I in range($N):
          try:
              ...
          except $E:
              ...
    message: >
      Do not hand-roll a retry loop. Use app.lib.retry.with_retry(...), the canonical
      implementation with backoff, jitter, and structured logging.
    severity: ERROR
    languages: [python]
```
```yaml
# Semgrep: ban a second email/URL regex when a validated helper already exists.
  - id: use-existing-validators
    pattern-regex: 're\.(compile|match|fullmatch)\(["''][^"'']*@[^"'']*["'']'
    message: >
      Do not write another email regex. Use app.lib.validate.email(); the repo has
      one validated implementation and must not fork it.
    severity: ERROR
    languages: [python]
```
```bash
# Surface near-duplicate function names across packages as a reinvention signal for
# the agent to consolidate before adding more.
git grep -hoE 'def [a-z_]+' app/ | sort | uniq -c | sort -rn | awk '$1 > 3'
```

### 28. Distribute One Versioned Config; Shard Rules by Path
Across hundreds of packages, copy-pasted lint config is the root of divergence — each copy drifts, and the agent gets a green verdict in one package and a red one in another for the same code. Publish the linter configuration as a single versioned artifact every package extends, and layer per-area rule sets on top by path so each subsystem adds the walls it needs without forking the base. One source of truth, composed locally, never duplicated — the monorepo-scale form of the single-source-of-truth discipline.
```toml
# Each package extends one shared base, so the core ruleset is defined once.
# (app/billing/ruff.toml)
extend = "//config/ruff_base.toml"     # the single source of truth, versioned in-repo
[lint]
extend-select = ["DTZ"]                # billing-specific additions layered on top
```
```toml
# Publish the base as an installable internal package so every repo pins the same
# version, and a bump is a deliberate, reviewed dependency change.
[project.optional-dependencies]
lint = ["acme-lint-config==3.4.0", "ruff==0.6.9"]
```
```yaml
# pre-commit: reference the shared hook repo at one pinned rev across all packages.
repos:
  - repo: https://github.com/acme/lint-hooks
    rev: v3.4.0
    hooks: [{ id: acme-ruff }, { id: acme-mypy }, { id: acme-import-linter }]
```
```ini
# Architecture contracts live in one root .importlinter for the whole graph; packages
# do not each keep their own divergent copy.
[importlinter]
root_packages =
    app
    services
    platform
```
```bash
# Generated and vendored code is excluded in exactly one place; everything else stays
# fail-closed (Principle 15). Lint the schema inputs, not the generated output.
# config/ruff_base.toml: extend-exclude = ["**/generated/**", "**/_pb2.py"]
buf lint proto/        # lint the .proto inputs; the generated *_pb2.py is walled off
```
```python
# CI assert: no package has forked the base config (drift detection).
import pathlib
for cfg in pathlib.Path("app").rglob("ruff.toml"):
    if b'extend = "//config/ruff_base.toml"' not in cfg.read_bytes():
        raise SystemExit(f"{cfg} does not extend the shared base — config drift. "
                         f"Extend it, do not fork it.")
```

# Updating Linters as the Codebase Grows
An aggressive linter is not a one-time configuration — it is a living artifact that must grow with the code the agent writes under it. As the agent adds files, folders, layers, and wrappers, the rules must be extended in lockstep, or the walls quietly stop covering the new surface area. Follow these steps whenever the codebase changes shape.

1. **When you add a new top-level layer or package, update the architecture contract before writing code in it.** Add the new module to the `layers` list in `.importlinter` (in the correct position in the order) and to the `LAYER_ORDER` of any custom architecture linter. Do this first so the very first file written in the new layer is already governed.
2. **When you add a new blessed wrapper, add the matching ban for the raw library it wraps.** A new `app/lib/cache.py` wrapping Redis should arrive together with a `banned-api` entry for `redis` (excepting the wrapper file itself). A wrapper with no ban on the thing it wraps is a wrapper the agent will route around.
3. **When the agent repeats a codebase-specific mistake for the second time, add a custom rule before fixing the instance.** Write one Semgrep rule (or extend the AST linter) that bans exactly that pattern, scope it to the right paths, phrase the message as an imperative, and commit it to `rules/`. The rule prevents the third occurrence; fixing only the instance does not.
4. **When you add a directory that is legitimately exempt, narrow the rule's `paths`, do not weaken the rule.** Generated code, migrations, and test fixtures often need an exception. Add the path to that single rule's `exclude` (or `include`) list rather than lowering the severity or deleting the rule globally — the exemption must be as narrow as the legitimate need.
5. **After adding or tightening any rule, run it across the whole repository once to surface pre-existing violations.** A new rule almost always finds old debt. Decide deliberately: fix it now, or record a baseline/ratchet (e.g. a `# noqa: <CODE>` with a tracking reason, or a recorded violation-count snapshot you only ever allow to shrink) that grandfathers existing instances while blocking new ones. Never let pre-existing debt become a reason to leave the rule at warning.
6. **Keep one source of truth and never let layers diverge.** The in-loop lint command, the pre-commit hook, and the CI step must all run the same `pyproject.toml`, the same `.importlinter`, and the same `rules/` folder. When you update a rule, you update it in one place; if the configs diverge, the agent gets a green local run and a red CI run and learns to distrust the linter.
7. **Tighten the caps as the codebase matures.** Once a hotspot is decomposed, lower the `max-complexity` or `max-args` cap so the build holds the new, better baseline. Caps are a ratchet that only ever moves toward stricter.
8. **When you delete a wrapper, layer, or pattern, delete its rules in the same change.** A rule that references a module that no longer exists, or bans a pattern that is now the blessed path, produces confusing failures and teaches the agent that the linter is unreliable. Dead rules are as harmful as dead code.
9. **Re-run the architecture linter after any structural refactor.** Moving files between packages changes their layer membership, which can silently create a new boundary violation or invalidate an old exemption. A refactor is not complete until the contracts pass against the new file layout.
10. **Treat each new rule as a permanent, versioned lesson.** Commit rules with a message describing the mistake they prevent, so the `rules/` folder reads as a changelog of the codebase's hard-won conventions. The folder's value is cumulative: it is the one part of your standards that never decays and never has to be re-explained to the agent.

# Things Not to Do
* Do not use warnings. An agent does not respond to a yellow squiggle; only a non-zero exit code changes behavior. Set every rule that matters to error. A warning is a suggestion the agent will never act on.
* Do not write linter messages as diagnostics for a human. Write them as imperatives to the agent. "blind except detected" is a description; "Catch a specific exception type; a bare except also swallows KeyboardInterrupt and SystemExit" is an instruction the agent can act on.
* Do not leave escape hatches open. A file-wide `# ruff: noqa`, a bare `# type: ignore`, a `# noqa` with no rule code, and an explicit `Any` cast are all bypass lanes. Each open bypass makes the corresponding wall decorative. Close the escape hatch in the same change that builds the wall.
* Do not configure linters to check only formatting. Formatting rules are the least valuable wall. Architecture boundaries, type integrity, security patterns, error-handling discipline, and test honesty are the walls that compound. Formatting is table stakes.
* Do not wait until after implementation to write the linter. Author the strict config and the architecture contract before the first function of a new module is written. A violation discovered after 400 lines is a design problem the agent must undo; a violation caught after 30 lines is a cheap course correction.
* Do not treat a complexity-cap violation as a style inconvenience to be silenced by raising the cap. A function over the cap is a design signal that it does more than one thing and needs decomposition. The cap is the trigger; the redesign is the fix.
* Do not write a custom Semgrep rule for a pattern that has only occurred once. The recurring-mistake pipeline pays off when the same mistake repeats. One occurrence is noise; the second occurrence is the trigger to encode the rule.
* Do not let the in-loop, pre-commit, and CI configurations diverge. The moment local lint and CI lint run different rules, the agent gets contradictory verdicts and stops trusting the linter. Keep a single source of truth and update it in one place.
* Do not write a rule whose suppression is wider than the violation it covers. A suppression must name the single rule it silences and carry a reason; a blanket suppression silences walls you never meant to lower.
* Do not let coverage default to "allow." A file the linter cannot parse, a new package with no contract, or a stray module outside the known roots must fail the build, not pass silently. Ungoverned surface is where drift hides — make every gap a loud failure.
* Do not float linter versions. A moving Ruff, mypy, or rule-pack version silently changes the verdict on unchanged code and teaches the agent the linter is noise. Pin every tool, plugin, and hook to an exact version and bump it deliberately.
* Do not stop at the principles in this file. They are a starting menu, not a ceiling; finish every linter by adding walls that came from this codebase's own conventions and review comments, not just from the list above.
* Do not re-lint the whole repository on every agent turn in a large codebase. Lint the changed surface in the loop for fast feedback and run the full suite — including the whole-graph contracts — at the merge gate. A linter slow enough to skip is not a wall.
* Do not copy-paste lint config across packages in a monorepo. Each forked copy drifts and produces contradictory verdicts; publish one versioned base config every package extends, and shard rules by path on top of it.

# Checklist
* Before writing the first function in a new module, write the strict config: set `[tool.ruff]` and `[mypy]` to maximum strictness, with caps for complexity, statements, arguments, branches, returns, boolean expressions, nesting depth, class method count, and magic values. The cap is how you keep the god-function from being expressible.
* When writing a `banned-api` or `no-restricted-import` rule, put the blessed alternative directly in the message. An agent that reads "import app.lib.http instead" acts immediately; one that reads "requests import forbidden" must guess.
* When writing any Semgrep rule, phrase the message in the imperative: state what the agent must do and where the correct code belongs, not what it did wrong.
* When adding a new architecture layer, update the `.importlinter` `layers` contract (and any custom architecture linter's `LAYER_ORDER`) before writing code in the new layer, then re-run cycle detection, public-API-only import checks, sibling independence contracts, and fan-in/fan-out caps.
* When introducing a new blessed wrapper, add the `banned-api` ban for the raw library it wraps — excepting only the wrapper file itself — in the same change.
* After writing any try/except block, verify the linter forbids bare `except:`, blind `except Exception`, swallowed exceptions, and re-raises that drop the cause chain (`BLE`, `E722`, `B904`, plus the swallowed-exception Semgrep rule).
* After adding any `# type: ignore` or `# noqa`, verify the suppression names a specific code and carries a reason, and that `PGH003`, `PGH004`, `RUF100`, and `warn_unused_ignores` are all on.
* Before declaring a module done, verify no stub or stray edit survives: run the `NotImplementedError`, `...`-body, `pass`-only, TODO/FIXME/HACK, wildcard import, unused import, unused variable, dead-code, mutable-default, `print()`, and runtime-`assert` rules.
* When the same agent mistake appears for the second time, write a custom rule in `rules/` before fixing the instance, scoped to the right paths, then commit it with a message describing the mistake it prevents.
* After any structural refactor that moves files between packages, re-run the architecture contracts (`lint-imports`) and the custom architecture linter against the new layout before considering the refactor complete.
* Whenever you tighten or add a rule, run the full linter across the whole repository once to surface pre-existing violations, and decide explicitly whether to fix them now or record a ratcheted baseline.
* Verify the in-loop lint command, the pre-commit hook, and the CI step all run the identical config and `rules/` folder. Divergence between layers produces a green local run and a red CI run.
* After excluding any path, verify `force-exclude` is on and the exclusion is as narrow as the legitimate need, and that unparseable files and ungoverned new packages still fail the build (fail-closed coverage).
* Pin every tool, plugin, and rule pack to an exact version — `required-version` in Ruff, exact `rev`s in pre-commit, pinned linters in the lockfile — so the same code always produces the same verdict.
* When adopting a strict rule on a non-clean repository, record a baseline and a check that the violation count only ever shrinks, so legacy debt is grandfathered while new debt is blocked. Do the same for coverage: record the current coverage floor and fail any future PR that drops below it.
* When writing async code, verify the `ASYNC` ruleset is on plus rules for blocking calls inside coroutines, missing request timeouts, and fire-and-forget tasks; and verify hardcoded-secret rules (`S105`–`S107` plus a secret scanner) are active.
* In a large repository, verify the loop lints the diff while the merge gate runs the whole-graph contracts (cycles, fan-out caps, undeclared cross-subsystem edges, package encapsulation), and that one versioned base config is shared across packages.
* Before declaring the linter done, add at least a few walls derived from this specific codebase — a forbidden internal coupling, a required pre-write hook, a naming or serialization invariant — that no generic principle in this file would have produced.

# Code Examples

## Example 1: A comprehensive Ruff + mypy + import-linter config
A single `pyproject.toml` plus `.importlinter` that encodes the whole menu of walls — error-only severity, strict typing, complexity caps, security, error-handling discipline, determinism, stub bans, hallucination guards, blessed-wrapper enforcement, and escape-hatch closure. Every rule fails the run; nothing is advisory.

```toml
# pyproject.toml
[tool.ruff]
target-version = "py312"

[tool.ruff.lint]
# One broad, strict selection. Ruff has no "warning" tier — any finding fails the run.
select = [
    "E", "F", "W",        # pyflakes + pycodestyle core (F821 undefined name lives here)
    "B",                  # flake8-bugbear (B904 raise-from, B011 assert-false)
    "S",                  # flake8-bandit (security)
    "C90",                # mccabe complexity
    "PL",                 # pylint (PLR0911..PLR0915 caps, PLR2004 magic values)
    "TRY",                # tryceratops (error-handling hygiene)
    "BLE",                # blind-except
    "DTZ",                # naive datetimes
    "PGH",                # blanket-suppression bans (PGH003/PGH004)
    "RUF100",             # unused noqa
    "ANN",                # missing type annotations
    "PT",                 # pytest-style
    "FIX",                # TODO/FIXME/HACK/XXX markers
    "TID",                # banned-api + relative-import control
    "T20",                # print / pprint left in code
    "ARG",                # unused function arguments
    "ERA",                # commented-out dead code
]

[tool.ruff.lint.mccabe]
max-complexity = 8

[tool.ruff.lint.pylint]
max-args = 5
max-branches = 10
max-bool-expr = 4
max-returns = 6
max-statements = 40

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"requests".msg     = "Import app.lib.http instead; the wrapper enforces timeout and retry."
"urllib.request".msg = "Import app.lib.http instead of urllib."
"httpx".msg        = "Import app.lib.http instead of raw httpx; the wrapper owns timeout and retry."
"psycopg2".msg     = "Import app.lib.db instead; direct clients bypass the pool and logging."
"boto3".msg        = "Import app.lib.aws instead; the wrapper injects credentials and retries."
"os.getenv".msg    = "Read app.config.settings instead; raw getenv skips type validation."
"typing.Any".msg   = "Model the real type or use a Protocol/TypeVar; Any disables checking."
"app.db.engine".msg = "Only app.repositories may import the engine; handlers call repositories."

[mypy]
strict = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
disallow_any_generics = true
disallow_any_explicit = true
no_implicit_optional = true
warn_unreachable = true
warn_unused_ignores = true
warn_return_any = true
ignore_missing_imports = false
```

```ini
# .importlinter
[importlinter]
root_package = app

[importlinter:contract:layers]
name = Layered architecture
type = layers
layers =
    app.api
    app.services
    app.domain

[importlinter:contract:feature-isolation]
name = Features are independent
type = independence
modules =
    app.features.billing
    app.features.checkout
    app.features.catalog
```

## Example 2: A codebase-specific Semgrep rule pack — the failure-mode-to-rule pipeline
When the same mistake appears twice, encode it as a rule and commit it to `rules/`. This pack bans the three most common agent drifts in a layered Python service: raw database access in handlers, placeholder stubs that fake completion, and `assert` used for runtime validation (which vanishes under `python -O`). Each message is an imperative that names the fix.

```yaml
# rules/agent-native.yaml
rules:
  - id: no-raw-db-in-handlers
    pattern: db.query(...)
    paths:
      include: ['app/api/**']
      exclude: ['app/api/**/tests/**']
    message: >
      Handlers must call the repository layer, not the database directly.
      Move this query into a method on the matching repository in app/repositories/
      and call that method from the handler. Direct calls bypass query logging,
      retry logic, and the transaction boundary the repository enforces.
    severity: ERROR
    languages: [python]

  - id: no-placeholder-implementations
    patterns:
      - pattern: raise NotImplementedError(...)
      - pattern: raise NotImplementedError
    paths:
      exclude: ['tests/**', '**/base.py']
    message: >
      Implement this function. NotImplementedError in non-abstract code means the
      task is incomplete. If the method is genuinely abstract, move it to a base
      class and decorate it with @abstractmethod.
    severity: ERROR
    languages: [python]

  - id: no-assert-for-runtime-validation
    pattern: assert $COND, $MSG
    paths:
      include: ['app/api/**', 'app/services/**']
    message: >
      Do not use assert for runtime validation; it is stripped under python -O.
      Raise a specific exception such as ValidationError instead.
    severity: ERROR
    languages: [python]
```

## Example 3: A whole-graph architecture linter for a large repo (standalone, no framework)
Off-the-shelf tools cover the common per-file walls, but a large codebase under a fast agent needs three things they do not do together: per-file rules, **whole-graph** rules that only emerge across the tree (import cycles, fan-out, undeclared cross-subsystem edges, package encapsulation), and the **scale ergonomics** that keep the linter usable at size — parallel execution, a content-hash skip, and a committed **baseline** so the linter can be adopted on a dirty tree by failing only on *new* violations (the ratchet from Principle 17). This single dependency-free file (stdlib `ast` only) does all three. It is config-driven through one `ArchConfig`, emits imperative findings as `file:line — [rule] instruction`, and exits non-zero on any non-baselined finding, so it drops straight into the inner loop (Principle 22) or the merge gate. Adapt `ArchConfig` — the layer order, the allowed subsystem edges, the ban tables, the caps — to a real system.

```python
#!/usr/bin/env python3
"""arch_lint.py — an aggressive architecture linter for a large, fast-moving repo.

A single-file, dependency-free linter (stdlib `ast` only) for a big codebase an agent
edits at high velocity. It does three things a packaged tool will not do together:

  1. Per-file walls   — layer-import direction, repository-only DB access, domain
     determinism, banned raw libraries, broad excepts, swallowed exceptions, stub
     bodies, import-time side effects, hardcoded secrets, and leftover print().
  2. Whole-graph walls — it builds the project import graph and fails on import
     cycles, fan-out over a cap, undeclared cross-subsystem edges, and deep imports
     into another package's internals (encapsulation).
  3. Scale ergonomics — it runs the per-file pass in parallel, and supports a
     committed baseline so it can be adopted on a dirty tree: only *new* findings
     fail the build (the ratchet).

Every finding is phrased as an imperative and prints as `file:line — [rule] message`.

Usage:
    python arch_lint.py app/                     # lint; fail on any new finding
    python arch_lint.py app/ --write-baseline    # snapshot current debt as grandfathered
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


# --- Architecture definition (the single place you adapt to a real system) -------

@dataclass(frozen=True)
class ArchConfig:
    # Lower index = lower layer; a module may import only its own layer or lower.
    layer_order: tuple[str, ...] = ("domain", "services", "api")
    # Only these path segments may import the raw DB engine.
    db_allowed_layers: frozenset[str] = frozenset({"repositories"})
    # Raw libraries reachable only through a blessed wrapper.
    banned_imports: dict[str, str] = field(default_factory=lambda: {
        "requests": "Import app.lib.http instead; the wrapper enforces timeout and retry.",
        "urllib": "Import app.lib.http instead of urllib.",
        "psycopg2": "Import app.lib.db instead; direct clients bypass the pool and logging.",
        "boto3": "Import app.lib.aws instead; the wrapper injects credentials and retries.",
    })
    # Non-deterministic calls forbidden in the domain layer.
    nondeterministic_calls: frozenset[str] = frozenset({
        "datetime.now", "datetime.utcnow", "time.time",
        "random.random", "random.randint", "uuid.uuid4",
    })
    # Subsystem-level edges that are allowed; any other cross-subsystem edge is new
    # coupling and fails. Subsystem = the path segment after the root package.
    allowed_edges: frozenset[tuple[str, str]] = frozenset({
        ("api", "services"), ("api", "domain"), ("services", "domain"),
        ("services", "repositories"), ("repositories", "domain"),
    })
    max_fan_out: int = 15          # internal modules one module may import
    secret_patterns: tuple[str, ...] = (
        r"AKIA[0-9A-Z]{16}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"://[^:@/\s]+:[^@/\s]+@",                       # creds embedded in a URL
    )


ARCH = ArchConfig()
SKIP_DIRS = frozenset({"tests", "migrations", "__pycache__", "generated"})


# --- Finding model ----------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    message: str

    def fingerprint(self) -> str:
        # Identity is (file, rule, message), not line — stable as code moves around,
        # so the baseline does not churn on every edit above a grandfathered finding.
        return hashlib.sha1(f"{self.file}|{self.rule}|{self.message}".encode()).hexdigest()

    def render(self) -> str:
        return f"{self.file}:{self.line} — [{self.rule}]\n    {self.message}"


# --- Helpers ----------------------------------------------------------------------

def dotted_name(node: ast.expr) -> str:
    parts: list[str] = []
    cur: ast.expr | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def module_path_for(path: Path, root: Path) -> str:
    rel = path.relative_to(root.parent).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()             # a package __init__.py is the package itself, app.billing
    return ".".join(parts)


def layer_of(module_path: str) -> str | None:
    for part in module_path.split("."):
        if part in ARCH.layer_order:
            return part
    return None


def subsystem_of(module_path: str) -> str | None:
    # app.billing.service -> "billing"
    parts = module_path.split(".")
    return parts[1] if len(parts) > 1 else None


def is_docstring(stmt: ast.stmt) -> bool:
    return (isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str))


def raises_not_implemented(node: ast.Raise) -> bool:
    exc = node.exc
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id == "NotImplementedError"
    return False


# --- Per-file checker -------------------------------------------------------------

class FileChecker(ast.NodeVisitor):
    """Walks one module's AST, collecting per-file findings and its import edges."""

    def __init__(self, file_path: str, module_path: str) -> None:
        self.file = file_path
        self.module = module_path
        self.layer = layer_of(module_path)
        self.findings: list[Finding] = []
        self.imports: set[str] = set()

    def add(self, line: int, rule: str, message: str) -> None:
        self.findings.append(Finding(self.file, line, rule, message))

    # imports -------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(node.lineno, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._check_import(node.lineno, node.module)
            # `from app.domain import b` may import the submodule app.domain.b; record
            # both so the graph resolver can match a sibling module, not just the package.
            for alias in node.names:
                self.imports.add(f"{node.module}.{alias.name}")
        self.generic_visit(node)

    def _check_import(self, line: int, imported: str) -> None:
        self.imports.add(imported)
        top = imported.split(".")[0]
        if top in ARCH.banned_imports and "lib" not in self.module:
            self.add(line, "banned-import", ARCH.banned_imports[top])
        target_layer = layer_of(imported)
        if self.layer and target_layer and target_layer != self.layer:
            if ARCH.layer_order.index(target_layer) > ARCH.layer_order.index(self.layer):
                self.add(line, "layer-violation",
                         f"{self.layer} must not import the higher layer '{target_layer}'. "
                         f"Invert the dependency, or move the shared code down into domain.")
        if imported.endswith("db.engine") and self.layer not in ARCH.db_allowed_layers:
            self.add(line, "db-access-violation",
                     "Only the repository layer may import app.db.engine. Call a repository "
                     "method from this layer instead of touching the engine.")
        if ".internal." in imported or imported.endswith(".internal"):
            my_sub, tgt_sub = subsystem_of(self.module), subsystem_of(imported)
            if my_sub and tgt_sub and my_sub != tgt_sub:
                self.add(line, "encapsulation-violation",
                         f"Do not import {tgt_sub}'s internals. Import only its public "
                         f"interface (app.{tgt_sub}); a package's internals are private.")

    # calls ---------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        name = dotted_name(node.func)
        if self.layer == "domain" and name in ARCH.nondeterministic_calls:
            self.add(node.lineno, "nondeterminism-in-domain",
                     f"Do not call {name}() in the domain layer. Inject a Clock/RNG/Id "
                     f"dependency and call it, so this code stays deterministic and testable.")
        if name == "print":
            self.add(node.lineno, "no-print",
                     "Replace print() with the structured logger: "
                     "from app.lib.log import logger; logger.info(...).")
        self.generic_visit(node)

    # module-level side effects -------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                    and not is_docstring(stmt)):
                self.add(stmt.lineno, "import-time-side-effect",
                         "Move this call into a function. Module-level calls run at import "
                         "time and break test isolation and startup ordering.")
        self.generic_visit(node)

    # exceptions ----------------------------------------------------------------

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        is_bare = node.type is None
        is_blind = (isinstance(node.type, ast.Name)
                    and node.type.id in {"Exception", "BaseException"})
        if is_bare or is_blind:
            self.add(node.lineno, "broad-except",
                     "Catch a specific exception type instead of a bare/blind except. A broad "
                     "except hides the failure mode and swallows KeyboardInterrupt.")
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.add(node.lineno, "swallowed-exception",
                     "Do not swallow an exception with `pass`. Log and recover, or re-raise.")
        self.generic_visit(node)

    # stub bodies ---------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_stub(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_stub(node)
        self.generic_visit(node)

    def _check_stub(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        decorators = {dotted_name(d) for d in node.decorator_list}
        if decorators & {"abstractmethod", "abc.abstractmethod"}:
            return  # abstract methods are allowed to be empty
        body = [s for s in node.body if not is_docstring(s)]
        if len(body) != 1:
            return
        only = body[0]
        is_ellipsis = (isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant)
                       and only.value.value is Ellipsis)
        if isinstance(only, ast.Pass) or is_ellipsis:
            self.add(node.lineno, "stub-body",
                     f"Implement {node.name}(); a `pass`/`...` body is a stub that fakes "
                     f"completion. If it is genuinely abstract, mark it @abstractmethod.")
        elif isinstance(only, ast.Raise) and raises_not_implemented(only):
            self.add(node.lineno, "stub-body",
                     f"Implement {node.name}(); NotImplementedError means the task is "
                     f"incomplete. If abstract, move it to a base class and mark it abstract.")


def check_secrets(file_path: str, source: str) -> list[Finding]:
    # Regex over raw text catches literals the AST would split across nodes.
    out: list[Finding] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if any(re.search(pat, line) for pat in ARCH.secret_patterns):
            out.append(Finding(file_path, lineno, "hardcoded-secret",
                               "This looks like a hardcoded credential. Move it to "
                               "app.config.settings and read it from the environment."))
    return out


# --- One file's full analysis (runs in a worker process) --------------------------

@dataclass
class FileResult:
    module: str
    findings: list[Finding]
    imports: set[str]


def analyze_file(args: tuple[str, str]) -> FileResult:
    file_path, root_str = args
    path, root = Path(file_path), Path(root_str)
    source = path.read_text(encoding="utf-8")
    module = module_path_for(path, root)
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as err:
        # Fail closed: an unparseable file is a violation, not a file to skip silently.
        return FileResult(module, [Finding(file_path, err.lineno or 0, "syntax-error",
                          f"File does not parse: {err.msg}. Fix the syntax before linting.")], set())
    checker = FileChecker(file_path, module)
    checker.visit(tree)
    return FileResult(module, checker.findings + check_secrets(file_path, source), checker.imports)


# --- Whole-graph checks (the rules that only exist across the tree) ---------------

def graph_findings(results: list[FileResult]) -> list[Finding]:
    out: list[Finding] = []
    modules = {r.module for r in results}
    edges: dict[str, set[str]] = defaultdict(set)
    for r in results:
        for imported in r.imports:
            target = _resolve_internal(imported, modules)
            if target and target != r.module:
                edges[r.module].add(target)

    for mod, deps in edges.items():
        loc = mod.replace(".", "/") + ".py"
        if len(deps) > ARCH.max_fan_out:
            out.append(Finding(loc, 1, "fan-out-cap",
                       f"{mod} imports {len(deps)} internal modules (cap {ARCH.max_fan_out}). "
                       f"Split it or hide dependencies behind a facade."))
        src_sub = subsystem_of(mod)
        for dep in deps:
            tgt_sub = subsystem_of(dep)
            if src_sub and tgt_sub and src_sub != tgt_sub and (src_sub, tgt_sub) not in ARCH.allowed_edges:
                out.append(Finding(loc, 1, "undeclared-edge",
                           f"New cross-subsystem dependency {src_sub} -> {tgt_sub}. Add it to "
                           f"ARCH.allowed_edges with a reason, or remove the import."))

    for cycle in _find_cycles(edges):
        head = cycle[0].replace(".", "/") + ".py"
        out.append(Finding(head, 1, "import-cycle",
                   "Import cycle: " + " -> ".join(cycle + [cycle[0]]) +
                   ". Break it by extracting the shared code into a lower layer."))
    return out


def _resolve_internal(imported: str, modules: set[str]) -> str | None:
    # Map a dotted import down to the longest known internal module (handles
    # `from app.api.handlers import x`, which imports the module app.api.handlers).
    parts = imported.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
        parts.pop()
    return None


def _find_cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)
    stack: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        color[node] = GREY
        stack.append(node)
        for nxt in sorted(edges.get(node, set())):
            if color[nxt] == GREY:
                cycles.append(stack[stack.index(nxt):])
            elif color[nxt] == WHITE:
                dfs(nxt)
        stack.pop()
        color[node] = BLACK

    for node in sorted(edges):
        if color[node] == WHITE:
            dfs(node)
    return cycles


# --- Baseline / ratchet + entry point --------------------------------------------

def collect_py_files(root: Path) -> list[str]:
    return [str(p) for p in sorted(root.rglob("*.py")) if not (set(p.parts) & SKIP_DIRS)]


def run(root: Path, workers: int) -> list[Finding]:
    work = [(f, str(root)) for f in collect_py_files(root)]
    if workers > 1 and len(work) > 1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(analyze_file, work))
    else:
        results = [analyze_file(w) for w in work]
    findings = [f for r in results for f in r.findings]
    findings.extend(graph_findings(results))
    return list(dict.fromkeys(findings))   # de-duplicate identical findings, keep order


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Aggressive architecture linter.")
    parser.add_argument("root", help="source package directory, e.g. app/")
    parser.add_argument("--baseline", default=".archlint-baseline.json")
    parser.add_argument("--write-baseline", action="store_true",
                        help="snapshot current findings as the grandfathered baseline")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv[1:])

    root = Path(args.root)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    findings = run(root, args.workers)
    baseline_path = Path(args.baseline)

    if args.write_baseline:
        baseline_path.write_text(json.dumps(sorted(f.fingerprint() for f in findings), indent=2))
        print(f"arch_lint: wrote baseline with {len(findings)} grandfathered finding(s).")
        return 0

    baseline = set(json.loads(baseline_path.read_text())) if baseline_path.exists() else set()
    new = [f for f in findings if f.fingerprint() not in baseline]
    for f in sorted(new, key=lambda f: (f.file, f.line)):
        print(f.render())

    grandfathered = len(findings) - len(new)
    if new:
        print(f"\narch_lint: {len(new)} new violation(s) ({grandfathered} grandfathered "
              f"by baseline). The build cannot close until every new finding is fixed — "
              f"each message above is an instruction, not a note.")
        return 1
    print(f"arch_lint: clean ({grandfathered} grandfathered, 0 new).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```
