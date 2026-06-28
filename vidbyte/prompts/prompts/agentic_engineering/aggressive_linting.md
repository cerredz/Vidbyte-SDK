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

Everything that follows is in service of that authorship. The **Generalized Principles** section gives you the menu of rules to write and the reasoning for each, the **Updating Linters** section tells you how to keep those rules alive as the codebase grows under you, and the **Code Examples** section gives you complete, copy-ready linters — including a full custom architecture linter you can adapt to a real system. When you finish, the repository should contain linters *you wrote*, and the wrong move should no longer compile.

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
    app.domain
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
[tool.ruff.lint]
extend-select = ["PLR0911"]   # too-many-return-statements: a sign of tangled control flow
[tool.ruff.lint.pylint]
max-returns = 6
```
```toml
[tool.ruff.lint]
extend-select = ["PLR2004"]   # magic-value-comparison: name the constant
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

# Checklist
* Before writing the first function in a new module, write the strict config: set `[tool.ruff]` and `[mypy]` to maximum strictness, with caps for complexity, statements, arguments, branches, and returns. The cap is how you keep the god-function from being expressible.
* When writing a `banned-api` or `no-restricted-import` rule, put the blessed alternative directly in the message. An agent that reads "import app.lib.http instead" acts immediately; one that reads "requests import forbidden" must guess.
* When writing any Semgrep rule, phrase the message in the imperative: state what the agent must do and where the correct code belongs, not what it did wrong.
* When adding a new architecture layer, update the `.importlinter` `layers` contract (and any custom architecture linter's `LAYER_ORDER`) before writing code in the new layer.
* When introducing a new blessed wrapper, add the `banned-api` ban for the raw library it wraps — excepting only the wrapper file itself — in the same change.
* After writing any try/except block, verify the linter forbids bare `except:`, blind `except Exception`, swallowed exceptions, and re-raises that drop the cause chain (`BLE`, `E722`, `B904`, plus the swallowed-exception Semgrep rule).
* After adding any `# type: ignore` or `# noqa`, verify the suppression names a specific code and carries a reason, and that `PGH003`, `PGH004`, `RUF100`, and `warn_unused_ignores` are all on.
* Before declaring a module done, verify no stub survives: run the `NotImplementedError`, `...`-body, `pass`-only, and TODO/FIXME rules, plus `vulture` for dead code from abandoned attempts.
* When the same agent mistake appears for the second time, write a custom rule in `rules/` before fixing the instance, scoped to the right paths, then commit it with a message describing the mistake it prevents.
* After any structural refactor that moves files between packages, re-run the architecture contracts (`lint-imports`) and the custom architecture linter against the new layout before considering the refactor complete.
* Whenever you tighten or add a rule, run the full linter across the whole repository once to surface pre-existing violations, and decide explicitly whether to fix them now or record a ratcheted baseline.
* Verify the in-loop lint command, the pre-commit hook, and the CI step all run the identical config and `rules/` folder. Divergence between layers produces a green local run and a red CI run.

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
]

[tool.ruff.lint.mccabe]
max-complexity = 8

[tool.ruff.lint.pylint]
max-args = 5
max-branches = 10
max-returns = 6
max-statements = 40

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"requests".msg     = "Import app.lib.http instead; the wrapper enforces timeout and retry."
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

## Example 3: A complete custom architecture linter (standalone, no framework)
Off-the-shelf tools cover the common walls, but a real system has architecture-specific rules no packaged linter knows about. This is a single-file, dependency-free linter built on Python's `ast` module that enforces a layered architecture and a set of agent-native bans across the whole tree: layer-import direction, repository-only database access, determinism in the domain layer, banned raw libraries, no bare excepts, no stub bodies, and no `print`. It emits imperative findings and exits non-zero on any violation, so it drops straight into a pre-commit hook or CI step. Adapt the `LAYER_ORDER`, `LAYER_OF`, and the ban tables to a real codebase.

```python
#!/usr/bin/env python3
"""arch_lint.py — a custom aggressive linter for a layered Python service.

Enforces, across the entire `app/` tree:
  * layer-import direction (api -> services -> domain; never the reverse)
  * database access only from the repository layer
  * determinism in the domain layer (no wall clock, no RNG)
  * banned raw libraries in favor of blessed wrappers
  * no bare/blind excepts, no stub bodies, no leftover print()

Run: python arch_lint.py app/    (exits 1 on any finding)
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# --- Architecture definition (adapt to the real system) ----------------------

# Lower index = lower layer. A module may import only its own layer or lower.
LAYER_ORDER: list[str] = ["domain", "services", "api"]


def layer_of(module_path: str) -> str | None:
    """Map a dotted module path (e.g. 'app.api.handlers') to its layer name."""
    parts = module_path.split(".")
    for part in parts:
        if part in LAYER_ORDER:
            return part
    return None


# Raw libraries that must be reached only through a blessed wrapper.
BANNED_IMPORTS: dict[str, str] = {
    "requests": "Import app.lib.http instead; the wrapper enforces timeout and retry.",
    "urllib": "Import app.lib.http instead of urllib.",
    "psycopg2": "Import app.lib.db instead; direct clients bypass the pool and logging.",
    "boto3": "Import app.lib.aws instead; the wrapper injects credentials and retries.",
}

# Calls that must never appear in the domain layer (non-deterministic I/O).
NONDETERMINISTIC_CALLS: set[str] = {
    "datetime.now",
    "datetime.utcnow",
    "time.time",
    "random.random",
    "random.randint",
    "uuid.uuid4",
}

# Only these layers/dirs may touch the database engine directly.
DB_ALLOWED_LAYERS: set[str] = {"repositories"}


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        # Imperative, agent-facing format: file:line — [rule] then the instruction.
        return f"{self.file}:{self.line} — [{self.rule}]\n    {self.message}"


def _dotted_name(node: ast.expr) -> str:
    """Best-effort reconstruction of a dotted call/attribute name."""
    parts: list[str] = []
    cur: ast.expr | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


class ArchChecker(ast.NodeVisitor):
    """Walks one module's AST and collects architecture/agent-native findings."""

    def __init__(self, file_path: str, module_path: str) -> None:
        self.file = file_path
        self.module = module_path
        self.layer = layer_of(module_path)
        self.findings: list[Finding] = []

    def _add(self, line: int, rule: str, message: str) -> None:
        self.findings.append(Finding(self.file, line, rule, message))

    # --- Import rules --------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(node.lineno, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._check_import(node.lineno, node.module)
        self.generic_visit(node)

    def _check_import(self, line: int, imported: str) -> None:
        top = imported.split(".")[0]
        # Rule 1: banned raw library (skip the wrapper files themselves).
        if top in BANNED_IMPORTS and "lib" not in self.module:
            self._add(line, "banned-import", BANNED_IMPORTS[top])
        # Rule 2: layer-import direction.
        target_layer = layer_of(imported)
        if self.layer and target_layer and target_layer != self.layer:
            if LAYER_ORDER.index(target_layer) > LAYER_ORDER.index(self.layer):
                self._add(
                    line,
                    "layer-violation",
                    f"{self.layer} must not import from the higher layer "
                    f"'{target_layer}'. Invert the dependency: have {target_layer} "
                    f"depend on {self.layer}, or move the shared code down into domain.",
                )
        # Rule 3: database engine reachable only from the repository layer.
        if imported.endswith("db.engine") and self.layer not in DB_ALLOWED_LAYERS:
            self._add(
                line,
                "db-access-violation",
                "Only the repository layer may import app.db.engine. Call a "
                "repository method from this layer instead of touching the engine.",
            )

    # --- Call rules ----------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted_name(node.func)
        # Rule 4: determinism in the domain layer.
        if self.layer == "domain" and name in NONDETERMINISTIC_CALLS:
            self._add(
                node.lineno,
                "nondeterminism-in-domain",
                f"Do not call {name}() in the domain layer. Inject a Clock/RNG/Id "
                f"dependency and call it, so this code stays deterministic and testable.",
            )
        # Rule 5: no leftover debug print().
        if name == "print":
            self._add(
                node.lineno,
                "no-print",
                "Replace print() with the structured logger: "
                "from app.lib.log import logger; logger.info(...).",
            )
        self.generic_visit(node)

    # --- Exception-handling rules -------------------------------------------

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # Rule 6: no bare/blind except.
        is_bare = node.type is None
        is_blind = isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
        if is_bare or is_blind:
            self._add(
                node.lineno,
                "broad-except",
                "Catch a specific exception type instead of a bare/blind except. "
                "A broad except hides the failure mode and swallows KeyboardInterrupt.",
            )
        # Rule 7: no silently swallowed exception.
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self._add(
                node.lineno,
                "swallowed-exception",
                "Do not swallow an exception with `pass`. Log and recover, or re-raise.",
            )
        self.generic_visit(node)

    # --- Stub-body rules -----------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_stub(node)
        self.generic_visit(node)

    def _check_stub(self, node: ast.FunctionDef) -> None:
        decorators = {_dotted_name(d) for d in node.decorator_list}
        if "abstractmethod" in decorators or "abc.abstractmethod" in decorators:
            return  # abstract methods are allowed to be empty
        body = [s for s in node.body if not isinstance(s, ast.Expr) or not _is_docstring(s)]
        if len(body) == 1:
            only = body[0]
            if isinstance(only, ast.Pass) or (
                isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant)
                and only.value.value is Ellipsis
            ):
                self._add(
                    node.lineno,
                    "stub-body",
                    f"Implement {node.name}(); a `pass`/`...` body is a stub that fakes "
                    f"completion. If it is genuinely abstract, mark it @abstractmethod.",
                )
            if isinstance(only, ast.Raise) and _raises_not_implemented(only):
                self._add(
                    node.lineno,
                    "stub-body",
                    f"Implement {node.name}(); NotImplementedError means the task is "
                    f"incomplete. If abstract, move it to a base class and mark it abstract.",
                )


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _raises_not_implemented(node: ast.Raise) -> bool:
    exc = node.exc
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id == "NotImplementedError"
    return False


def module_path_for(path: Path, root: Path) -> str:
    rel = path.relative_to(root.parent).with_suffix("")
    return ".".join(rel.parts)


def lint_path(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for py_file in sorted(root.rglob("*.py")):
        if any(part in {"tests", "migrations", "__pycache__"} for part in py_file.parts):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError as err:
            findings.append(
                Finding(str(py_file), err.lineno or 0, "syntax-error",
                        f"File does not parse: {err.msg}. Fix the syntax before linting.")
            )
            continue
        checker = ArchChecker(str(py_file), module_path_for(py_file, root))
        checker.visit(tree)
        findings.extend(checker.findings)
    return findings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python arch_lint.py <source-dir>", file=sys.stderr)
        return 2
    findings = lint_path(Path(argv[1]))
    for f in findings:
        print(f.render())
    if findings:
        print(f"\narch_lint: {len(findings)} violation(s). The build cannot close until "
              f"every one is fixed — each message above is an instruction, not a note.")
        return 1
    print("arch_lint: clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```
