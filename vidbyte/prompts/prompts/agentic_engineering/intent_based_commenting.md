# Description
Every codebase has two layers that change at different rates. The intent layer is slow — it is the domain rule, the idempotency guarantee, the regulatory constraint, the hard-won fix that went into production and cost something to learn. The implementation layer is fast — under an agent it might be rewritten five times in a week, and each rewrite is a legitimate improvement. The problem with ordinary code is that these two layers are fused: the only record of what the code means is the code itself, so every rewrite puts the meaning at risk. A behavior-preserving refactor can pass every type check and every test and still silently destroy the understanding of why the function is built the way it is, what invariants it must maintain, and what went wrong the last time someone "simplified" it.

Intent-based commenting un-fuses the layers. You write the slow layer down explicitly, in a structured comment block anchored by `@intent`, and pin it physically adjacent to the function it governs. Because the comment sits three lines above the function body, it is co-retrieved with the code every time an agent reads or edits that function — it cannot be missed the way a design document can be missed. The `@intent` block is the regeneration prompt that travels with the code: when the agent rewrites the function body, the block is the specification it regenerates against. It functions not as documentation the agent might consult, but as an input the agent cannot avoid reading. This is the load-bearing property that makes proximity matter beyond the usual "docs drift from code" argument.

The `@intent` block also serves as the lowest-decay prompt in the system. Unlike a system-prompt instruction that gets diluted as the context window fills, a comment above a function is re-read fresh, in full, every single time the agent touches that function. Its content cannot drift over a long session for the same structural reason a linter rule cannot drift: it is re-evaluated from scratch on every encounter with the function.

# Intent
The intent of intent-based commenting is to make the meaning of critical business logic durable across the constant implementation churn that characterizes agent-driven development. An agent regenerating a function should always regenerate against an explicit, structured spec — not against its own inference of what the previous version was trying to do.

This principle is trying to close a specific failure mode: silent meaning destruction during behavior-preserving rewrites. An agent can produce code that compiles, passes types, and passes all tests, while violating a domain invariant, removing an idempotency guarantee, or simplifying away a hard-won fix — because none of those constraints were expressed anywhere mechanical. The `@intent` block is where you express the constraints that cannot be derived from code: the "at most once" guarantee, the "never exceed the original charge" rule, the "we tried the obvious version and it caused an incident" context. Encoding these in a structured comment next to the function means the agent cannot regenerate the function without reading its contract first.

# The Litmus Test: Would It Survive a Total Rewrite?
This is the single question that governs every decision in this principle. Before writing an `@intent` block — and before writing any field within one — ask: if you deleted the function body and regenerated it from scratch, would this statement still be true?

A **narration comment** describes the current implementation: `# loop through the items and sum them`. The moment the agent rewrites that loop as a reduce, the comment is stale. A stale comment is worse than no comment: it is a confident lie sitting in the context window the next agent reads, potentially causing it to write code that preserves the stale description rather than the actual intent. Narration comments rot under churn, which is exactly the condition agent-native code lives in permanently.

An **intent comment** describes the layer above the implementation — the why, the contract, the invariant, the rule. "At most one charge per order, even under concurrent retries" is true of the function whether it is implemented with a lock, a database constraint, or an idempotency key. It survives the rewrite because it was never about the implementation in the first place. The rule for writing intent is: pitch it at the level of abstraction where a correct reimplementation cannot make it false. If a statement could be made false by a refactor that preserves behavior, it is narration, and it does not belong in an `@intent` block.

Apply this test to every field you write. The `@summary` must survive a rewrite. The `@why` must survive a rewrite. The `@constraints` especially must survive: they are the rules that govern every possible correct implementation. If a `@constraints` entry can only be satisfied by one particular implementation, it is either a genuine single-valid-implementation constraint (which should be explicit) or it is accidentally describing the implementation rather than the rule.

# What Counts as Business Logic
The failure mode of over-application is as damaging as under-application. If every function gets an `@intent` block, the signal drowns in noise and the blocks themselves become maintenance burden. The principle applies to a specific, bounded subset of code.

**Tag a function or class when a behavior-preserving rewrite could still be catastrophically wrong** — that is, where code that passes types and tests could still violate something not expressed anywhere mechanical. That is exactly the gap an `@intent` block fills: the constraints that are not derivable from the code itself.

## The Five Qualifying Categories

**1. Domain rules and invariants.** Rules that come from the business, not from the language. "A refund cannot exceed the original charge amount." "An account in frozen state rejects all writes, including those from background jobs." "A subscription must be created in a single atomic operation — partial subscriptions are not a valid state." These rules are not expressible as types, and a test suite that exercises the happy path will not catch a violation. The agent will write perfectly plausible code that violates them because it cannot know the rule exists unless the rule is stated.

**2. Correctness, safety, and money paths.** Any code path where silent wrongness costs real money, corrupts data, or destroys user trust. Payment processing, charge calculations, balance mutations, refund logic, entitlement grants. The common thread: the cost of a wrong rewrite is not caught by CI. The agent sees no signal that it violated the invariant until a customer complains or a reconciliation runs.

**3. Concurrency and idempotency guarantees.** "At most once." "Exactly once." "This operation is safe to retry because it is idempotent." "The lock must be held across both the read and the write." Agents default to the simplest concurrent code, which is almost always the racy version. The racy version looks cleaner, passes happy-path tests, and fails under load in production. If a function has a concurrency model, that model must be stated explicitly or it will be rewritten away.

**4. Hard-won fixes.** Code that exists in a non-obvious form because the obvious form was tried and broke something. The classic: a guard that looks like it could be removed, but was added after a production incident. Without the `@why` field explaining the incident, the next agent will remove the guard as dead code, regression tests will pass, and the incident will recur. Hard-won fixes are the highest-value category because the cost of losing them is paying the same learning price twice.

**5. Regulatory and compliance constraints.** "PII must be redacted before this data leaves the service boundary." "This operation must be logged with a user ID for the audit trail." "The retention period is 7 years." Invisible to types, invisible to most tests, and catastrophic to violate. Regulatory constraints are precisely the kind of rule that exists outside the code and that the agent cannot infer from the implementation.

## What Does Not Qualify

Do not tag: CRUD boilerplate (create, read, update, delete with no domain rules attached), framework plumbing (middleware wiring, route registration, dependency injection setup), glue code (translating one data format to another with no business semantics), and obvious transformations where the code is its own complete explanation.

The diagnostic question: what would a catastrophically wrong rewrite look like, and would it be caught before reaching production? If the answer is "it would fail a type check" or "it would fail an obvious unit test," the function does not need an `@intent` block. If the answer is "it would pass all checks and only show up in a production incident," it does.

# The @intent Comment Schema
Every `@intent` block uses a fixed set of named fields. The fields are consistently ordered so they are predictable to read and machine-parseable. Use the `@fieldname` prefix for every field. The entire block is a multi-line comment placed immediately before the function or class definition — no blank lines between the block and the `def` or `function` keyword.

```
# @intent [id]: [short-name]
# @summary: [1-2 sentences: what this code must do, not how it does it]
# @why: [why this approach / what went wrong with the obvious approach]
# @contract:
#   pre:  [conditions that must hold before entry]
#   post: [guarantees on exit, including on failure]
# @constraints: [non-obvious rules every correct implementation must satisfy]
# @survivors: [tests, ADRs, issues, or decisions that depend on this intent]
```

### @intent [id]: [short-name]
The identifier and name. The `id` is a stable slug that survives function renames, file moves, and reorganizations — it is the persistent anchor for cross-references. Choose a free-form slug that is descriptive and unique within the codebase: `charge-idempotency`, `refund-ceiling`, `frozen-account-write-guard`. The `short-name` is a human-readable label: `Idempotent charge per order`, `Refund cannot exceed original`, `Frozen account rejects all writes`.

Write the id as a slug you would be comfortable searching for in a codebase-wide grep. Avoid generic ids like `business-rule-1` that require reading the rest of the block to understand what they anchor.

### @summary
One or two sentences describing what this code must do. This is the field the agent reads when it has no other context — make it answer "what is the contract of this function?" in one scan.

Pitch it above the implementation: describe the outcome, not the mechanism. "Ensures at most one charge is created per order identifier, even when called concurrently from multiple processes" — not "acquires a lock, checks for existing charge, creates charge if none found." The second version narrates the implementation; the first states the contract. A correct reimplementation using a database unique constraint instead of a lock would still satisfy the first; it would not match the second.

### @why
The rationale field. This is where you record why this approach was chosen, what the alternative approaches were, and — most importantly — what went wrong the last time someone used a different approach. This is the highest-value field for hard-won fixes.

Write this field in plain past tense: "We tried optimistic locking in 2025-Q3 and got double-charges under the load spike described in incident INC-441. Advisory locks solved it. Do not revert to optimistic locking without re-reading INC-441." An agent reading this cannot simplify away the advisory lock without seeing the incident reference, which it can look up before making the change.

Leave this field empty only when the approach is the obvious first choice with no alternative history and no production incident behind it. If you are tempted to write "N/A" or "standard approach," ask whether a junior engineer reading this at 2am during an incident would benefit from even a single sentence of context. Usually the answer is yes.

### @contract
The semantic pre- and post-conditions — not the type signature, which is already in the code. Pre-conditions describe what must be true before the function is called. Post-conditions describe what is guaranteed to be true after the function returns, including on failure paths.

Write preconditions that are not enforced by types: "caller must hold the subscription write lock," "user must be in active or past_due state," "idempotency_key must be globally unique for this order." Write postconditions that describe what the function guarantees about the world state, not just the return value: "on success, exactly one charge record exists in the database for this order," "on failure, no charge has been created and the order state is unchanged."

### @constraints
The non-obvious rules that every correct implementation must satisfy, regardless of how it is implemented. This is the field that most directly prevents silent meaning destruction. Constraints are permanent properties of the function's contract — they are true of the advisory-lock implementation, the database-constraint implementation, and any future implementation.

Write each constraint as a statement that could be independently tested: "at most one charge is created per order_id even when called 100 times concurrently," "the audit log entry is written in the same database transaction as the charge record," "PII fields are redacted before the log line is emitted." A constraint that could only be satisfied by one specific implementation is either a genuine uniqueness constraint (state it clearly) or is accidentally describing the implementation (rewrite it at a higher level).

### @survivors
Cross-references to artifacts whose correctness depends on this intent being preserved. This field closes the loop between the intent comment and the test suite, ADR log, and incident history.

List: test files and line ranges that verify the constraints, ADRs that document the design decisions behind the intent, incident tickets that motivated a hard-won fix, and any other code that cross-references this intent by its id slug. Format as a bulleted list. When the agent modifies this function, it reads `@survivors` to know which tests to run, which documents to re-read, and which cross-references will break if the intent changes.

# How to Write Each Field at the Right Abstraction Level
The single most common mistake is writing at the wrong level of abstraction — either too high (vague platitudes) or too low (implementation narration). Here are the calibration heuristics.

**Too high / platitude:** `@summary: Handles charge creation.` This could describe any payment function in any codebase. It gives an agent no meaningful constraint to regenerate against.

**Too low / narration:** `@summary: Acquires advisory lock on order_id, queries charges table for existing record, creates new charge if not found.` This describes the current implementation. An agent rewriting this with a database unique constraint would see that its implementation does not match the summary and would either change the implementation unnecessarily or mark the comment as stale.

**Correct level:** `@summary: Ensures at most one charge is created per order_id across all concurrent callers and all retry attempts.` This is a property of the contract, not a description of the mechanism. A reimplementation using any concurrency strategy that satisfies this property is correct.

The calibration test: read the field you just wrote and ask whether it would still be true of any correct reimplementation. If yes, it is at the right level. If a specific implementation detail would make it false, rewrite it one level up.

For `@why` specifically, the calibration is different: concreteness is the goal. A vague `@why` ("this approach was chosen for performance reasons") is nearly useless. A concrete `@why` ("optimistic locking produced double-charges under concurrent retries in incident INC-441; advisory locks solved it; do not revert without re-reading that incident") is exactly right. `@why` is the one field where you want to name specific incidents, experiments, and timestamps.

# Linter Enforcement
The failure mode of under-coverage — writing `@intent` blocks for some business-logic functions but not others — is silent. There is no compile error, no test failure. Over time, the uncovered functions are precisely the ones the agent will rewrite most aggressively, because they lack the constraint that would slow it down.

Enforce coverage with a Semgrep rule that detects functions in business-logic paths that lack an `@intent` block. The rule works by matching function definitions in your domain and service layers and checking whether the line immediately before the function contains `@intent`.

```yaml
# rules/require-intent-comment.yaml
rules:
  - id: require-intent-comment-billing
    pattern: |
      def $FUNC(...):
          ...
    paths:
      include:
        - 'src/billing/**'
        - 'src/domain/**'
        - 'src/payments/**'
    message: >
      Business-logic functions in billing, domain, and payment layers require an
      @intent block immediately above the def statement. Add a comment block with
      @intent, @summary, @why, @contract, @constraints, and @survivors before
      this function. See the intent_based_commenting principle for the full schema.
    severity: ERROR
    languages: [python]
```

For TypeScript, match `function` declarations and class method definitions in the equivalent layers. The Semgrep pattern for checking that the preceding comment contains `@intent` uses a `pattern-not` clause:

```yaml
  - id: require-intent-comment-ts
    patterns:
      - pattern: |
          $MODIFIER $FUNC(...): $RETURN {
            ...
          }
      - pattern-not-inside: |
          // @intent ...
          $MODIFIER $FUNC(...): $RETURN {
            ...
          }
    paths:
      include:
        - 'src/domain/**'
        - 'src/services/**'
    message: >
      Functions in domain and service layers require an @intent block.
      Add a // @intent block immediately before this function definition.
    severity: ERROR
    languages: [typescript, javascript]
```

Run this rule in the same three-layer enforcement model as all other linters: inside the agent loop as a tool (so the agent sees the failure and repairs it in the same session), as a pre-commit hook (local safety net), and in CI (the wall that protects main). The error message is written as an imperative to the agent because that is exactly what it is — an instruction the agent reads and acts on.

# Things Not to Do
* Do not write narration. A comment that describes the current implementation — what variables are set, which branches are taken, what the loop does — is narration. Narration rots under churn. Every line of narration you write is a confident lie waiting to happen the next time the agent rewrites the function. If a comment would become false after a behavior-preserving refactor, delete it.
* Do not over-tag. CRUD functions, framework glue, format converters, and obvious utility code do not need `@intent` blocks. Over-tagging dilutes the signal: when every function has a block, no function's block is a reliable indicator that the function carries non-obvious constraints. Reserve `@intent` for code where the litmus test answer is "yes, a wrong rewrite could be catastrophic and would pass all tests."
* Do not leave `@why` empty for non-obvious code. If a function has an unusual structure, an extra guard, or a non-obvious ordering, and `@why` is blank, the next agent will simplify it. The `@why` field is specifically the guard against "simplifications" that reintroduce production incidents. Empty `@why` on non-obvious code is equivalent to no `@intent` block.
* Do not let `@contract` drift from the actual function signature over time. `@contract` describes semantic pre- and post-conditions that the type system cannot express — but if the function signature changes and the pre-conditions described in `@contract` are no longer valid, the block becomes misleading. After every modification to the function, re-read `@contract` and update it.
* Do not write `@constraints` that describe the implementation. A constraint that is only satisfiable by the current implementation is either a genuine constraint that deserves explicit statement ("only the advisory-lock approach satisfies the latency budget") or it is accidentally narrating. Apply the litmus test to every `@constraints` entry: would every correct reimplementation still satisfy this?
* Do not delete an `@intent` block when rewriting a function. Rewriting the body is the exact scenario the block exists for. After the rewrite, re-read each field, update any field that the new implementation changes the answer to (primarily `@why` and `@contract`), and verify `@survivors` still reference valid artifacts. Delete the block only if the function no longer qualifies as business logic at all.
* Do not put `@intent` blocks on private helpers. The principle applies at the level of meaningful callable units that can be regenerated independently — public functions and classes that represent business operations. A private helper that is called from one place and is only meaningful in that context is covered by the block on the calling function.

# Checklist
* Before writing any function in a domain, service, billing, or payment layer, apply the litmus test: could a behavior-preserving rewrite be catastrophically wrong and pass all tests? If yes, the function qualifies for an `@intent` block.
* Write the `@intent` block before writing the function body. The block is the specification you are implementing against. Writing it first forces you to articulate the contract before you are anchored to any particular implementation.
* For every field in the block, apply the litmus test: would this statement still be true if the function body were deleted and regenerated from scratch? If no, rewrite the field at a higher level of abstraction.
* For `@why`, be concrete rather than vague. Name incidents, experiments, or decisions by identifier. A vague rationale does not constrain the agent.
* For `@constraints`, write each entry as a statement that could be independently tested. If a constraint can only be verified by reading the implementation, it is either too implementation-specific or needs a dedicated test.
* After writing a function body, re-read the `@intent` block and verify that the implementation actually satisfies every `@contract` pre-condition and post-condition and every `@constraints` entry. The block is the specification; the implementation must satisfy it, not the other way around.
* After modifying any function that has an `@intent` block, re-read every field and update any that the modification makes inaccurate. This is the adversarial review step for intent comments.
* Verify `@survivors` references are still valid: test files exist, ADRs are still accessible, incident tickets are reachable. A `@survivors` reference to a deleted test is a broken link in the safety net.
* After completing a module in a business-logic layer, audit every function: does each one that qualifies by the litmus test have a block? Run the Semgrep enforcement rule as a self-check before opening a pull request.
* When a function lacks an `@intent` block and you are not the author of that function, add the block as a separate commit before modifying the function body. This ensures the intent is captured before churn begins.

# Code Examples

## Example 1: Python — billing function with idempotency and hard-won fix context
This example shows a charge creation function in a billing service. The `@why` field records a production incident. The `@constraints` field states the idempotency guarantee at a level that survives any correct reimplementation.

```python
# @intent charge-idempotency: Idempotent charge creation per order
# @summary: Creates exactly one charge record per order_id regardless of how
#   many times this function is called concurrently or in sequence. The charge
#   amount and currency are fixed at the time of the first successful call;
#   subsequent calls with the same order_id return the existing charge.
# @why: Optimistic locking (check-then-insert) produced double-charges under
#   concurrent retry storms in incident INC-441 (2025-09-12). Advisory lock on
#   order_id serializes all callers for the same order. Do not revert to
#   optimistic locking without reading INC-441 and load-testing at 10x normal
#   retry volume.
# @contract:
#   pre:  order_id is non-empty and globally unique per billing period.
#         amount_cents is positive. currency is a valid ISO 4217 code.
#         Caller does not hold any other database locks (advisory lock is acquired here).
#   post: On success, exactly one charge record with this order_id exists in the
#         database and the returned Charge object reflects that record.
#         On failure, no charge record was created or modified for this order_id.
# @constraints: At most one charge record per order_id exists at any point,
#   even under 100 concurrent callers retrying the same order.
#   The audit log entry is written in the same database transaction as the
#   charge record — they are never out of sync.
#   amount_cents is never modified after the first successful charge creation,
#   even if the caller passes a different amount on a retry.
# @survivors:
#   - tests/billing/test_charge_service.py:45-110 (idempotency and concurrency tests)
#   - docs/adr/031-charge-idempotency.md (advisory lock decision)
#   - INC-441 (incident that motivated this design)
def create_charge(order_id: str, amount_cents: int, currency: str) -> Charge:
    with advisory_lock(f"charge:{order_id}"):
        existing = db.charges.find_by_order_id(order_id)
        if existing:
            return existing
        charge = db.charges.insert(
            order_id=order_id,
            amount_cents=amount_cents,
            currency=currency,
        )
        audit_log.write(event="charge.created", charge_id=charge.id, order_id=order_id)
        return charge
```

## Example 2: TypeScript — domain class method with regulatory constraint and frozen-state guard
This example shows a class method on an Account domain object. The `@constraints` field states a regulatory requirement that is invisible to the type system. The hard-won fix in `@why` explains a guard that would otherwise look like defensive paranoia.

```typescript
// @intent frozen-account-write-guard: Frozen accounts reject all mutations
// @summary: Applies a credit to the account balance and records the transaction.
//   Raises FrozenAccountError before any database write if the account is in
//   frozen state, regardless of the credit source or caller identity.
// @why: Background jobs (automated credits, promotional grants) bypass the
//   API-layer auth checks that normally prevent writes to frozen accounts.
//   Enforcement must live here, at the domain boundary, not at the API layer.
//   In 2026-Q1 a promotional job credited $200 to frozen accounts under legal
//   hold, triggering a compliance review (ticket LEGAL-88). The guard was moved
//   here after that incident.
// @contract:
//   pre:  account is loaded from the database and reflects current state.
//         amount is positive and in the account's currency.
//   post: On success, account.balance has increased by amount and exactly one
//         transaction record exists in the database for this credit.
//         On FrozenAccountError, balance is unchanged and no transaction was written.
// @constraints: Frozen accounts (status === 'frozen') must reject ALL write
//   operations including credits, regardless of caller identity, API key scope,
//   or job priority. This is a regulatory requirement for accounts under legal hold.
//   The credit amount must be recorded in the transaction log before the balance
//   is updated, so the log is always at least as current as the balance.
// @survivors:
//   - src/billing/__tests__/account.test.ts:200-260 (frozen state rejection tests)
//   - docs/adr/047-account-write-guard.md
//   - LEGAL-88 (compliance incident)
applyCredit(amount: number, source: CreditSource): Transaction {
  if (this.status === 'frozen') {
    throw new FrozenAccountError({ accountId: this.id, attemptedCredit: amount });
  }
  const transaction = this.db.transactions.insert({
    accountId: this.id,
    amount,
    source,
    type: 'credit',
  });
  this.db.accounts.updateBalance(this.id, this.balance + amount);
  return transaction;
}
```

## Example 3: Semgrep rule enforcing @intent coverage in business-logic layers
This rule detects Python functions in domain, billing, and payment layers that are missing an `@intent` block immediately before the `def` statement. The error message is written as an imperative directed at the agent.

```yaml
# rules/require-intent-comment.yaml
rules:
  - id: require-intent-comment
    patterns:
      - pattern: |
          def $FUNC(...):
              ...
      - pattern-not: |
          # @intent ...
          def $FUNC(...):
              ...
    paths:
      include:
        - 'src/billing/**'
        - 'src/domain/**'
        - 'src/payments/**'
        - 'src/subscriptions/**'
      exclude:
        - 'tests/**'
        - '**/__init__.py'
        - '**/migrations/**'
    message: >
      Add an @intent block immediately before this function definition.
      Business-logic functions in billing, domain, payment, and subscription
      layers must document their contract using the @intent schema:
        # @intent [id]: [short-name]
        # @summary: what this must do (not how)
        # @why: rationale / hard-won fix context
        # @contract: pre: [...] post: [...]
        # @constraints: rules every correct implementation must satisfy
        # @survivors: tests, ADRs, incidents
      See the intent_based_commenting agentic engineering principle for the
      full field guide and examples.
    severity: ERROR
    languages: [python]
```
