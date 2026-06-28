# Description
Aggressive linting is the practice of configuring your static analysis toolchain at maximum strictness and treating every rule violation as an error — not a warning — so that bad code cannot be committed, not merely flagged. For human teams, an over-strict linter is a morale problem: developers argue about rules, disable checks, or quit. For agents, none of those costs exist. An agent feels no friction, does not resent a rule, and will iterate against feedback all day. The usual human tradeoff between strictness and developer experience collapses entirely when agents are the primary authors. You can crank strictness far past what any human team would accept, because the friction is paid by something that does not feel friction.

The deeper argument is about memory and decay. Instructions you encode in a system prompt degrade over a long context window — the model drifts from them as the conversation fills up. A linter rule is the opposite: deterministic, re-evaluated from scratch on every run, immune to context decay. The master move is to migrate correctness out of prose and into mechanism. Prose says "please use the repository layer"; a `no-restricted-imports` rule makes the direct database call not compile. The first is a hope. The second is a fact. Every rule you can express as a fail-closed check is a piece of your standards that has been permanently removed from the jurisdiction of the context window.

Two consequences follow. First, all rules must be errors, never warnings. A warning is invisible to an agent — the agent feels no social pressure from a yellow squiggle; only a non-zero exit code changes behavior. Second, the error message is a prompt. When a lint failure is injected back into the agent's context window, it is not a diagnostic for a tired human — it is an instruction the model will act on next. Write error messages as imperatives to the agent: "Handlers must call the repository layer, not the database directly" beats "raw database access detected." Your rules folder stops being a linter config and becomes the highest-signal, lowest-decay steering channel you have.

# Intent
The intent of aggressive linting for agent-native codebases is to make architectural standards, security invariants, and coding conventions hold permanently — not through repeated reminders that decay, but through mechanically enforced walls that make violations non-expressible. An agent writing code should encounter constraints the same way it encounters type errors: as immediate, specific, actionable rejections that describe exactly what to do instead.

This principle is trying to close the gap between what a system prompt instructs and what code actually gets produced after many iterations. Prose instructions degrade; linter rules do not. By encoding your conventions as fail-closed rules and feeding violations back into the agent's context as imperative instructions, you transform the linter from a style guide into a correction loop — one that compounds over time as you add codebase-specific rules for every recurring mistake your agent makes.

# The Three-Layer Enforcement Model
The same set of rules should be enforced in three places, each with a different speed-authority tradeoff.

**Layer 1 — Inside the agent loop (fastest).** Run the linter as a tool available to the harness. After the agent writes code, the harness calls the lint tool, parses the output, and injects failures into the next context turn as observations. The agent reads these as instructions and iterates. The loop cannot close until the linter exits 0. This is the layer that actually teaches the agent — it sees the failure and the correction in the same session.

**Layer 2 — Pre-commit hook (local safety net).** The same linter runs as a pre-commit hook before any commit is accepted. This catches anything that slipped through a manually invoked loop or was introduced by a human. Runs in seconds.

**Layer 3 — CI (the real wall).** The linter runs server-side on every push. This is the layer that actually protects main. A developer or agent cannot bypass it with `--no-verify` on their own machine and have the code still land. CI is the canonical source of truth; the other two layers are conveniences. All three layers run identical rules from the same config so there is no divergence between local and server behavior.

# Architecture and Dependency Walls
The core idea: declare your layer order once; enforce that lower layers cannot import higher ones; and make cycles mechanically impossible. Your architecture diagram becomes a rule the build enforces, not a convention a tired agent might violate.

**dependency-cruiser (JS/TS)** — `.dependency-cruiser.js`
```js
module.exports = {
  forbidden: [
    {
      name: 'domain-cant-reach-up',
      severity: 'error',
      from: { path: '^src/domain' },
      to:   { path: '^src/(api|services)' }
    },
    {
      name: 'no-cycles',
      severity: 'error',
      from: {},
      to: { circular: true }
    }
  ]
};
```
Principle: the cycle itself is the rejected state. An agent cannot route around a missing abstraction by reaching back.

**eslint-plugin-import (JS/TS)** — layer boundaries without a dedicated tool
```js
'import/no-restricted-paths': ['error', { zones: [
  { target: 'src/domain', from: 'src/api' },
  { target: 'src/domain', from: 'src/services' }
]}],
'import/no-cycle': 'error',
```
Principle: you often already have the wall installed — `eslint-plugin-import` handles both layering and cycle-breaking before you reach for a dedicated tool.

**import-linter (Python)** — `.importlinter`
```ini
[importlinter:contract:layers]
name = Layered architecture
type = layers
layers =
    myproject.api
    myproject.services
    myproject.domain
```
Principle: declare the order once. The arrow becomes a compile-gate, not a convention.

**@nx/enforce-module-boundaries (Nx monorepo)** — tag-based isolation
```json
"@nx/enforce-module-boundaries": ["error", {
  "depConstraints": [
    { "sourceTag": "scope:checkout", "onlyDependOnLibsWithTags": ["scope:shared"] }
  ]
}]
```
Principle: isolate features by tag, not by folder path — a sibling feature's internals are unreachable even when the relative import is one `../` away.

# Type System as Wall
The type checker is the wall that sits above the linter. A thing the compiler rejects never reaches the linter, never reaches CI, never reaches a reviewer. Every strict flag you flip deletes an entire failure class from the expressible space.

**tsconfig.json strict flags** — the cheapest walls you will ever flip
```json
{
  "strict": true,
  "noUncheckedIndexedAccess": true,
  "exactOptionalPropertyTypes": true
}
```
Principle: one config line closes the entire "I'll just optimistically index it" failure class at the language level, upstream of every other check.

**@typescript-eslint/switch-exhaustiveness-check + assertNever**
```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}
// .eslintrc:
'@typescript-eslint/switch-exhaustiveness-check': 'error'
```
Principle: add a union variant anywhere and every unhandled switch breaks at compile time, three files from where the agent was editing.

**Branded types + no-explicit-any**
```ts
type UserId = string & { readonly __brand: 'UserId' };
// no-explicit-any: 'error'  ← closes the cast that defeats the brand
```
Principle: a wall with an open `any` cast is decorative. Ban the bypass in the same breath as building the wall.

**mypy --strict (Python)**
```ini
[mypy]
strict = true
disallow_untyped_defs = true
warn_return_any = true
```
Principle: untyped code is the agent's preferred hiding place for drift. Strict mode makes "no annotation" itself the error.

# Security Walls
The shared principle: make the dangerous form of a construct not exist as an expressible option, so the agent can only ship the safe version.

**Semgrep — ban a dangerous pattern outright** — `rules/no-string-sql.yaml`
```yaml
rules:
  - id: no-string-sql
    patterns:
      - pattern: $CUR.execute("..." % ...)
      - pattern: $CUR.execute("..." + ...)
    message: >
      Use parameterized queries. Pass values as the second argument to execute().
      String-interpolated SQL is the root cause of SQL injection vulnerabilities.
    severity: ERROR
    languages: [python]
```
Principle: the unsafe construction does not exist in the expressible-program space. The agent can only ship the parameterized form.

**gitleaks — secret detection at commit time and CI**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```
Run it both places. `git commit --no-verify` buys nothing if CI re-checks server-side.

**OSV-Scanner / npm audit — CVE gate on the dependency graph**
```bash
osv-scanner --recursive .
# or:
npm audit --audit-level=high
```
Principle: adding a dependency with a known vulnerability is a build failure, not a dismissible warning.

# Test Integrity Gates
These exist specifically because agents find the cheapest way to make a failing test suite appear green. Each rule closes a specific cheat.

**eslint-plugin-jest / eslint-plugin-no-only-tests** — ban the test-skip escape
```js
'jest/no-focused-tests': 'error',   // bans .only
'jest/no-disabled-tests': 'error',  // bans .skip / xit
```
Principle: the cheapest way to "fix" a red suite is to disable the failing assertion. This bans that exit.

**jest/expect-expect (or vitest/expect-expect)** — every test must assert
```js
'jest/expect-expect': 'error'
```
Principle: catches the test that calls your code and asserts nothing — it passes trivially and proves nothing.

**diff-cover — coverage on the diff, not the repo**
```bash
diff-cover coverage.xml --compare-branch origin/main --fail-under 90
```
Principle: an agent cannot hide an untested change inside a well-covered file. Only new lines are judged.

**betterer — the ratchet** — `.betterer.ts`
```ts
import { regexp } from '@betterer/regexp';
export default {
  'no new console.log': () => regexp(/console\.log/).include('src/**/*.ts'),
};
```
Principle: freeze today's count of a smell; old debt is grandfathered, but the agent cannot add instance N+1. This is the right pattern for codebases where you cannot fix all existing violations immediately.

# API and Contract Enforcement
**API Extractor (Microsoft)** — snapshot the exported surface
```bash
# CI: fail if regen of the .api.md snapshot produces a diff
api-extractor run --local
git diff --exit-code
```
Principle: internals refactor freely; the public surface cannot widen or break without a deliberate, reviewed change to the snapshot.

**oasdiff (OpenAPI) / buf breaking (protobuf)** — detect breaking changes as an exit code
```bash
oasdiff breaking base.yaml head.yaml --fail-on ERR
buf breaking --against '.git#branch=main'
```
Principle: "did I break my API?" is no longer a careful human review — it is an exit code.

**Runtime validators (Zod / Pydantic / OpenAPI middleware)** — validate at the boundary while running
```ts
app.use(OpenApiValidator.middleware({
  apiSpec: './openapi.yaml',
  validateRequests: true,
  validateResponses: true
}));
```
Principle: even if a handler drifts from the spec, the boundary rejects the malformed shape at runtime. The wall holds when build-time checks miss something.

# Infra-as-Code Policy
**Conftest / OPA (Rego)** — fail the plan, not the deploy
```rego
deny[msg] {
  input.resource.aws_s3_bucket[name].acl == "public-read"
  msg := sprintf("Public S3 bucket not allowed: %s. Set acl to private.", [name])
}
```
Principle: a violating manifest fails `plan`, so it never reaches a cluster regardless of who or what wrote it.

**Checkov / Trivy** — hundreds of misconfig rules out-of-the-box
```bash
checkov -d . --hard-fail-on HIGH
trivy config .
```
Principle: no-public-buckets, no-root-containers, mandatory resource limits — without authoring Rego for each.

# Agent-Native Walls
This is the category most specific to harness work. These rules directly target the failure modes agents exhibit reliably.

## Stub and Dead-Code Detection — make "looks done, isn't done" fail the build

**no-warning-comments / Semgrep TODO ban**
```js
'no-warning-comments': ['error', { terms: ['TODO', 'FIXME', 'HACK', 'XXX'] }]
```
Principle: agents leave a `TODO` as a way to "finish" without finishing. Ban the marker, ban the incomplete work.

**Semgrep — ban the literal stub pattern** — `rules/no-stubs.yaml`
```yaml
rules:
  - id: no-not-implemented
    patterns:
      - pattern: raise NotImplementedError(...)
      - pattern: raise NotImplementedError
    paths:
      exclude: ['tests/**', 'vidbyte/tools/builtins/base.py']
    message: >
      Remove the NotImplementedError stub and implement the function.
      Stub implementations in non-test code mean the task is incomplete.
    severity: ERROR
    languages: [python]
```

**knip (JS/TS) / Vulture (Python)** — dead export and unused code detection
```bash
knip                    # fails if there are unused exports or files
vulture src/ --min-confidence 80
```
Principle: agents leave orphaned functions from abandoned attempts. Dead code detected at CI is removed before it accumulates.

**no-unreachable** — code after a return is a classic sign of half-rewritten logic
```js
'no-unreachable': 'error'
```

**no-empty** — empty `{}` blocks, including the empty catch that silently eats errors
```js
'no-empty': ['error', { allowEmptyCatch: false }]
```

## Error-Handling Discipline — agents hide problems instead of solving them

**Ruff BLE001 / flake8-blind-except** — ban bare `except:`
```toml
[tool.ruff.lint]
select = ["BLE"]   # BLE001: blind exception catch
```
Principle: a bare `except:` catches `SystemExit` and `KeyboardInterrupt` and tells the agent nothing about the failure mode. Force a specific exception type.

**@typescript-eslint/ban-ts-comment** — no `@ts-ignore` without a reason
```js
'@typescript-eslint/ban-ts-comment': ['error', {
  'ts-ignore': 'allow-with-description',
  minimumDescriptionLength: 10
}]
```
Principle: `@ts-ignore` is the agent's first move when a type error is hard to fix. Closing this escape hatch forces the actual fix.

**Ruff PGH003** — ban `# type: ignore` without an error code
```toml
select = ["PGH003"]   # type: ignore without specific error code
```

**eslint-comments/no-unlimited-disable + no-unused-disable** — close the linter's own escape hatch
```js
'eslint-comments/no-unlimited-disable': 'error',
'eslint-comments/no-unused-disable': 'error'
```
Principle: a blanket `// eslint-disable` at the top of a file disables every rule in the file. This closes that bypass. No escape hatch should be wider than the specific violation it suppresses.

**@typescript-eslint/no-floating-promises** — catch the dropped await
```js
'@typescript-eslint/no-floating-promises': 'error'
```
Principle: agents drop `await` constantly, creating silent races. This turns every un-awaited promise into a build error.

## Hallucination Guards — agents invent things that do not exist

**import/no-unresolved** — fails on an import that resolves to nothing
```js
'import/no-unresolved': 'error'
```
Principle: catches hallucinated package names before they reach CI.

**import/no-extraneous-dependencies** — cannot import a package not in the manifest
```js
'import/no-extraneous-dependencies': 'error'
```
Principle: catches the phantom dependency the agent assumed was installed.

**Ruff F821** — reference to an undefined name
```toml
select = ["F821"]   # undefined name
```
Principle: catches calls to functions the agent thinks exist but does not.

## Determinism — agents write code that cannot be tested

**Semgrep — ban non-deterministic primitives in core layers** — `rules/no-nondeterminism.yaml`
```yaml
rules:
  - id: no-random-in-core
    patterns:
      - pattern: random.random()
      - pattern: random.randint(...)
      - pattern: datetime.now()
      - pattern: time.time()
    paths:
      include: ['src/domain/**', 'src/services/**']
    message: >
      Inject clocks and RNG as dependencies rather than calling them directly.
      Functions in domain and service layers must be deterministic and testable.
    severity: ERROR
    languages: [python]
```
Principle: non-deterministic calls in core logic make tests non-reproducible. Forcing them to be injected as dependencies makes the code both testable and honest about its I/O.

**no-console / Ruff T201** — no debug output left in committed code
```js
'no-console': 'error'
```
```toml
select = ["T201"]   # print statements
```

## Convention Lock-In — fight drift over long context windows
This category is the most agent-specific. An agent's adherence to your conventions degrades as its context window fills. A rule evaluates fresh on every run and never drifts.

**no-restricted-imports** — force the blessed wrapper, ban the raw library
```js
'no-restricted-imports': ['error', {
  patterns: [
    {
      group: ['axios', 'node-fetch'],
      message: 'Import from @/lib/http instead. The internal wrapper enforces retry and timeout behavior.'
    },
    {
      group: ['pg', 'mysql2'],
      message: 'Import from @/lib/db instead. Direct database client imports bypass the connection pool and query logging.'
    }
  ]
}]
```
Principle: this is one of the highest-leverage agent walls. It forces the agent down your blessed path instead of reaching for the raw library it knows from training data.

**no-restricted-syntax** — ban a whole construct
```js
'no-restricted-syntax': ['error',
  { selector: 'TSEnumDeclaration', message: 'Use union types instead of enums. Enums are not tree-shakable and do not narrow correctly.' },
  { selector: 'ExportDefaultDeclaration', message: 'Use named exports. Default exports are not greppable and break rename refactors.' }
]
```

**@typescript-eslint/naming-convention** — enforce casing mechanically
```js
'@typescript-eslint/naming-convention': ['error',
  { selector: 'interface', format: ['PascalCase'], prefix: ['I'] },
  { selector: 'typeAlias', format: ['PascalCase'] },
  { selector: 'variable', format: ['camelCase', 'UPPER_CASE'] }
]
```

## The Failure-Mode-to-Rule Pipeline
This is the one wall with no off-the-shelf equivalent. Every time your agent makes the same codebase-specific mistake twice, write one Semgrep rule banning exactly that pattern and commit it. A growing `rules/` folder accumulates codebase-specific lessons — cheaper and more durable than stuffing reminders into a system prompt, which the model drifts away from over a long context.

```yaml
# rules/no-raw-db-in-handlers.yaml
rules:
  - id: no-raw-db-in-handlers
    pattern: db.query(...)
    paths:
      include: ['src/api/**']
    message: >
      Handlers must call the repository layer, not the database directly.
      Move this query to the appropriate repository in src/repositories/.
    severity: ERROR
    languages: [python]
```

The rule folder compounds. Each new rule is a lesson that is permanently encoded in the codebase — not a comment that will be ignored, not a system-prompt instruction that will decay. Over time, the rules folder becomes a codebase-specific immune system that a competitor cannot copy off the shelf.

# The Operational Harness Loop
The mechanism is a generate → verify → repair loop. The linter is the verify step. Here is the complete wiring.

**Step 1: Machine-readable output from a single command.** Configure the linter to emit structured JSON or SARIF — not human-formatted terminal text. Agents parse structured records reliably; they scrape prose unreliably.
```bash
eslint --format json src/             # JSON output
ruff check --output-format json src/  # JSON output
semgrep --sarif rules/ src/           # SARIF output
```

**Step 2: Expose it as a harness tool.** In your harness, define a `lint` tool. When the agent calls `lint`, the harness runs the command, captures stdout/stderr and the exit code, parses the output, and returns structured findings.

**Step 3: Inject findings into the context window as observations.** This is the crux. After each edit the agent makes, the harness runs the linter and injects parsed failures back as a tool result, each formatted as an imperative instruction:
```
src/api/handlers.py:42 — [no-raw-db-in-handlers]
Handlers must call the repository layer, not the database directly.
Move this query to the appropriate repository in src/repositories/.
```
The agent reads this on its next turn exactly as it reads any other instruction, and acts on it.

**Step 4: Tie completion to the exit code, not the agent's self-report.** Agents declare victory prematurely — this is their single most reliable failure mode. The loop may not terminate until the linter exits 0. The agent's claim that it is finished is a hypothesis; the exit code is the verdict.

**Step 5: Scope findings to the diff.** A large repo can throw hundreds of pre-existing findings and blow the context budget. Lint only the files the agent touched:
```bash
eslint $(git diff --name-only HEAD)
ruff check --diff   # only new violations relative to baseline
```
Surface the top N errors; fix the first batch; re-run. Fixing the first batch often clears cascading downstream violations.

# Things Not to Do
* Do not use warnings. An agent does not respond to a yellow squiggle. Set every rule that matters to `error`. A warning is a suggestion the agent will never act on.
* Do not lint only at CI. CI is the wall, but the agent cannot repair while CI is running. The in-loop lint tool is what makes the repair cycle fast. Run the same rules in all three layers.
* Do not write error messages as diagnostics for a human. Write them as imperatives to the agent. "raw db access detected" is a description. "Handlers must call the repository layer, not the database directly. Move this query to src/repositories/" is an instruction.
* Do not leave escape hatches open. A `// eslint-disable-file` blanket comment, a bare `# type: ignore`, an `@ts-ignore` without a reason, and an `any` cast are all bypass lanes. Each bypass makes the corresponding wall decorative. Close the escape hatch in the same PR that builds the wall.
* Do not configure linters to check only formatting. Formatting rules are the least valuable wall. Architecture boundaries, type integrity, security patterns, and test honesty are the walls that compound. Formatting is table stakes.
* Do not wait until after implementation to configure linting. Configure linter caps before writing the first line of a new module. A violation discovered after 400 lines are written is a design problem the agent must undo; a violation caught after 30 lines is a cheap course correction.
* Do not treat a lint cap violation as a style inconvenience. A function that exceeds the complexity cap is not a linting problem — it is a design signal that the function is doing more than one thing and needs to be decomposed. The cap is the trigger; the design is the fix.
* Do not write a Semgrep rule for a pattern that only occurred once. The failure-mode-to-rule pipeline pays off when the same mistake recurs. One occurrence is noise; two occurrences is a pattern worth encoding.

# Checklist
* Before writing the first function in a new module, configure the linter with caps for cyclomatic complexity, function line count, nesting depth, and positional argument count. The cap is not optional; it is how you prevent the god-function from being expressible.
* When writing a `no-restricted-imports` rule, include the blessed alternative in the error message. An agent that sees "use @/lib/http instead" can act immediately; one that sees "axios import forbidden" must guess.
* When adding a Semgrep rule, write the message in the imperative: describe what the agent must do, not what it did wrong.
* After completing any module, run `knip` or `vulture` to verify there are no unused exports. Dead code from abandoned agent attempts accumulates silently.
* After writing any async function, verify `@typescript-eslint/no-floating-promises` is configured and clean. Every un-awaited promise is a silent race.
* After writing any try/except or try/catch block, verify no bare `except:` or empty `catch {}` was introduced. Every caught exception must be specific.
* After adding any `@ts-ignore`, `# type: ignore`, or `// eslint-disable` comment, verify the suppression names a specific rule and an explanation. A blanket suppression closes the wall it suppresses.
* When the same agent mistake appears for the second time, write a Semgrep rule before fixing the instance. The rule prevents the third occurrence.
* Before opening a pull request, verify the linter exits 0 on the diff — not just on the files you remember touching, but on every file changed according to `git diff`.
* When writing the harness lint tool, verify it returns both exit code and structured findings. The exit code is the completion gate; the findings are the repair instructions.
* When configuring CI, verify the lint step runs the same command with the same config as the in-loop tool and the pre-commit hook. Divergence between layers produces false negatives.

# Code Examples

## Example 1: ESLint config enforcing agent-native walls
A single `.eslintrc.js` that encodes architecture boundaries, escape-hatch closure, and convention lock-in. Every rule is set to `error`, never `warn`.

```js
// .eslintrc.js
module.exports = {
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint', 'import', 'eslint-comments', 'jest'],
  rules: {
    // Architecture walls
    'import/no-cycle': 'error',
    'import/no-restricted-paths': ['error', { zones: [
      { target: 'src/domain', from: 'src/api' },
      { target: 'src/domain', from: 'src/services' }
    ]}],
    'no-restricted-imports': ['error', { patterns: [
      { group: ['axios'], message: 'Import from @/lib/http. The wrapper enforces retry and timeout.' },
      { group: ['pg', 'mysql2'], message: 'Import from @/lib/db. Direct imports bypass the connection pool.' }
    ]}],

    // Escape-hatch closure
    '@typescript-eslint/ban-ts-comment': ['error', {
      'ts-ignore': 'allow-with-description',
      minimumDescriptionLength: 10
    }],
    'eslint-comments/no-unlimited-disable': 'error',
    'eslint-comments/no-unused-disable': 'error',
    '@typescript-eslint/no-explicit-any': 'error',

    // Async discipline
    '@typescript-eslint/no-floating-promises': 'error',

    // Stub detection
    'no-warning-comments': ['error', { terms: ['TODO', 'FIXME', 'HACK'] }],
    'no-unreachable': 'error',
    'no-empty': ['error', { allowEmptyCatch: false }],

    // Test integrity
    'jest/no-focused-tests': 'error',
    'jest/no-disabled-tests': 'error',
    'jest/expect-expect': 'error',

    // Convention
    'import/no-default-export': 'error',
    'no-console': 'error',
  }
};
```

## Example 2: The failure-mode-to-rule pipeline — a codebase-specific Semgrep rule
When the same mistake appears twice, encode it as a rule. This example bans direct database calls in API handlers, which is a mistake that agents make because the path of least resistance is to reach for the database client directly.

```yaml
# rules/no-raw-db-in-handlers.yaml
rules:
  - id: no-raw-db-in-handlers
    pattern: db.query(...)
    paths:
      include: ['src/api/**']
      exclude: ['src/api/**/__tests__/**']
    message: >
      Handlers must call the repository layer, not the database directly.
      Move this query to the appropriate repository in src/repositories/
      and call the repository method from the handler.
      Direct database calls in handlers bypass query logging, retry logic,
      and the transaction boundary enforced by the repository layer.
    severity: ERROR
    languages: [python]

  - id: no-placeholder-implementations
    patterns:
      - pattern: raise NotImplementedError(...)
      - pattern: raise NotImplementedError
    paths:
      exclude: ['tests/**', 'src/base/**']
    message: >
      Remove the NotImplementedError stub and implement the function.
      Placeholder implementations mean the task is incomplete.
      If the function is intentionally abstract, move it to the base class.
    severity: ERROR
    languages: [python]
```

## Example 3: The harness lint tool — the generate→verify→repair loop
This Python snippet shows how a harness exposes linting as a tool and feeds violations back into the agent's context as imperative observations. The key details are: (1) JSON output for reliable parsing, (2) scoping to the diff to manage context budget, (3) formatting violations as agent instructions, and (4) tying loop completion to exit code rather than agent self-report.

```python
import subprocess
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class LintFinding:
    file: str
    line: int
    rule: str
    message: str

    def to_observation(self) -> str:
        # Format as an imperative instruction, not a diagnostic description.
        return f"{self.file}:{self.line} — [{self.rule}]\n{self.message}"


class LintTool:
    def __init__(self, max_findings: int = 20):
        # Cap findings to avoid blowing the context budget on a large repo.
        self._max_findings = max_findings

    def run(self, changed_files: list[str] | None = None) -> dict[str, Any]:
        # Scope to changed files when provided; otherwise lint the whole src tree.
        targets = changed_files or ["src/"]
        result = subprocess.run(
            ["ruff", "check", "--output-format", "json", *targets],
            capture_output=True,
            text=True,
        )
        exit_code = result.returncode
        findings = self._parse(result.stdout)
        return {
            "exit_code": exit_code,
            "passed": exit_code == 0,
            "findings": [f.to_observation() for f in findings[: self._max_findings]],
            "total_findings": len(findings),
            "truncated": len(findings) > self._max_findings,
        }

    def _parse(self, raw: str) -> list[LintFinding]:
        # Parse Ruff JSON output into structured findings.
        try:
            items = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            return []
        return [
            LintFinding(
                file=item.get("filename", ""),
                line=item.get("location", {}).get("row", 0),
                rule=item.get("code", ""),
                message=item.get("message", ""),
            )
            for item in items
        ]


# In the harness loop:
#
# lint_tool = LintTool()
# while True:
#     agent_response = agent.step(context)
#     if is_done_claim(agent_response):
#         lint_result = lint_tool.run(changed_files=get_diff_files())
#         if lint_result["passed"]:
#             break  # exit code 0 — loop closes
#         # Inject findings as the next context turn, not as agent instructions.
#         context.append({"role": "tool", "content": format_findings(lint_result)})
#         # Agent reads findings on next step and repairs.
```
