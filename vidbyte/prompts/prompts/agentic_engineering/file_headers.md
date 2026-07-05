# Goal
Your goal is to produce file header comments that are complete enough to serve as a miniature architecture document, concise enough to be read in under five seconds, and structured enough to be parseable by agents. Every file you create must open with a header that covers the file's exact path, its purpose in depth, its role in the dependency graph expressed in plain English with connections to concepts outside the codebase, an inventory of every exported function with input-output contracts and test coverage, common modification patterns for typical tasks, a numbered list of things that must never be done in this file, known edge cases and legacy data patterns, and cross-references to related errors and documentation. The header must stay fresh. Describe what the file IS and WHY, not implementation details that change with every refactor. After writing the file body, you must re-read the header and update any section that the finished code contradicts, because the final header must describe the code that actually exists, not the code you planned to write.

# Intent
The intent of file header comments is to address a fundamental problem: there is not enough high-signal, aligned context in the code of a file itself to orient a cold agent quickly. Source code tells an agent what the code does, but it cannot reliably tell the agent why the file exists, where it sits in the larger architecture, what depends on it, what it must never do, and what is known to be tricky about it. This header comment serves four purposes: first, it relates the file to its job in the codebase so an agent can confirm in the first three lines whether this is the right file to edit; second, it provides a brief snapshot of the file's purpose and architecture so the agent can orient itself before reading implementation details; third, it informs the agent about the blast radius and similar files so it can predict what a change will affect before making it; and fourth — most importantly — it provides the agent with meaningful context about the file that exists nowhere else in the file itself. Without a structured header, an agent must reconstruct this context through imports, function names, and partial reads — a process that consumes significant context before any actual work begins.

Conceptually, you can think of a well-written file header as giving an agent the experience of having read six files worth of context and understood higher-order information, just through reading that one file. The header condenses the essential architecture of the surrounding system — the callers, the callees, the invariants, the modification patterns, the forbidden operations — into a stable, machine-readable block at the top of the file. This makes the file self-sufficient as a navigational artifact: an agent landing on it cold can answer all orientation questions without opening any other file. The header must describe what the file IS and WHY it exists, not implementation mechanics that change with every refactor, because the architectural contract is durable even when the code changes significantly. A header written to intent stays accurate through a rewrite; a header written to implementation must be updated with every refactor and will inevitably rot. This durability property makes the investment in writing a thorough header pay off repeatedly across every agent session that reads the file.

# Header Section Inventory
* FILE — The exact file path as it exists on disk. This section exists so that an agent scanning the header can confirm it has the right file open without checking the filesystem or matching against an import statement. It must be a literal path, not a description of the path.
* PURPOSE — A paragraph describing what this file does, what it owns, and what it is responsible for. The description must be concrete rather than abstract, naming the operations or data the file manages rather than describing its category. It should also state what this file must not be used for, so agents do not add functionality to the wrong place.
* ROLE IN CODEBASE — A description of the file's position in the dependency graph, listing which files call it, which files it calls, and which invariants it owns. This section saves agents from manually tracing imports to understand the file's neighborhood. It must name specific files rather than abstract layer names, and must describe what each relationship involves.
* ARCHITECTURE NOTE — A description of where this file sits in the system topology, including which boundaries it sits at, which architectural patterns it implements, and which design documents explain those decisions. This section orients an agent that knows the system's architecture but has not yet read this file, allowing it to place the file in context before reading the code.
* FUNCTION INVENTORY — A structured list of every exported function and class with signature, input types, output type, one-line description of behavior, error classes the function throws, and the test file and line range covering it. This section is the file's API contract: an agent navigating the codebase reads FUNCTION INVENTORY to decide whether a function in this file is what it needs, before opening the file body.
* COMMON MODIFICATION PATTERNS — Routing instructions for the most frequent tasks that touch this file, describing the sequence of changes required and which other files must be updated in the same operation. This section prevents an agent from making a partial change — modifying this file but forgetting the downstream files that must change in tandem.
* WHAT NOT TO DO IN THIS FILE — A numbered list of operations an agent might mistakenly attempt in this file but that are owned by other files. Each item must name the forbidden operation and the file that owns it. This section is the negative-space map: it prevents the most expensive mistake in codebase navigation, which is implementing functionality in the wrong file.
* KNOWN EDGE CASES — Documentation of weird states, legacy data patterns, and known bugs that affect this file. This section prevents agents from hitting the same traps that past developers hit. Each entry should describe the condition, the behavior it causes, and how the code currently handles it.
* RELATED DOCS — Full URLs to ADRs, runbooks, design documents, and relevant issues, each with a description of what the document explains and when an agent should load it. Links must be full URLs, not document titles, because an agent cannot fetch a title but can fetch a URL.
* AUTO-GENERATED FLAG — An unmissable warning if the file is generated by tooling rather than written by hand. Agents must never edit generated files, and this flag prevents wasted cycles on changes that will be overwritten on the next codegen run.
* TEST FILES — Which test files cover this source file and the coverage percentage. This section tells the agent what to run after making changes and whether the existing coverage is adequate to catch regressions in the modified path.
* CONCURRENCY MODEL — A description of any locks, queues, or race condition risks that apply to this file. Agents modifying concurrent code without understanding the locking model will introduce races. This section is required whenever the file uses advisory locks, optimistic locking, queues, or any other concurrency primitive.

# Complete Example
The following is a complete annotated file header for a hypothetical subscription manager. Use this as a template when authoring file headers. The section ordering is deliberate — identification and purpose come first, navigation and ownership in the middle, edge cases and references last.

/**
 * FILE: src/billing/subscription-manager.ts
 *
 * PURPOSE: Orchestrates the full subscription lifecycle — creation, renewal,
 *          cancellation, and proration — and serves as the single entry point
 *          for all subscription state changes in the billing system.
 *          This file owns the transactional integrity of every subscription
 *          mutation: if a subscription state change succeeds in this file, it
 *          has been validated against the plan catalog, invoiced correctly, and
 *          persisted atomically. If it fails, the error packet tells the caller
 *          exactly which stage failed and what state was left behind.
 *          Conceptually, this file is the cash register of the business — every
 *          dollar that flows through the subscription system passes through a
 *          function in this file, and the business's revenue recognition depends
 *          on the correctness of the state transitions enforced here.
 *          Do NOT modify subscriptions directly through the database, and do
 *          NOT send subscription events from outside this file — bypassing this
 *          orchestrator produces inconsistent billing state that is extremely
 *          expensive to detect and repair.
 *
 * FILE DEPENDENCIES:
 *   This file is called by the following files. Each caller passes a specific
 *   subset of subscription data and expects a specific result back.
 *   - api/subscriptions.route.ts: The external API surface. Routes HTTP requests
 *     into subscription operations. Validates auth and request shape before
 *     delegating to this file. If a request fails validation at the API layer,
 *     it never reaches this file — this file only sees well-formed requests.
 *   - webhooks/stripe.handler.ts: The Stripe webhook receiver. Processes events
 *     from Stripe's payment processing system — successful charges, failed
 *     payments, subscription cancellations initiated from the Stripe dashboard,
 *     and payment method updates. Translates Stripe's event model into our
 *     internal subscription model.
 *
 *   This file calls into the following files. Each callee provides a specific
 *   capability that this file orchestrates.
 *   - billing/plans.store.ts: Lookup and validation of subscription plans.
 *     Returns plan metadata including price, billing interval, and feature
 *     flags. Throws PlanValidationError if the plan ID is unrecognized.
 *   - billing/invoice.generator.ts: Creates invoice records for subscription
 *     charges. Called on creation and renewal. Does not send invoices to
 *     customers — that is handled by the billing events publisher.
 *   - users/entitlements.service.ts: Manages what features a user has access to
 *     based on their active subscriptions. Updated after every subscription
 *     state change. Must be called in the same transaction as the subscription
 *     mutation to prevent entitlement drift.
 *   - events/billing-events.publisher.ts: Dispatches billing events to the
 *     message queue for downstream consumers — email notifications, analytics
 *     pipelines, audit logs, and third-party integrations. Events are fired
 *     after the subscription mutation is committed so that consumers always
 *     see the settled state.
 *
 *   This file owns one critical invariant: subscription.state transitions must
 *   follow the finite state machine defined in billing/subscription-states.ts.
 *   No code inside or outside this file may transition a subscription directly
 *   without going through the state transition guards enforced here.
 *
 * ARCHITECTURE NOTE:
 *   This file sits at the most important boundary in the billing system — the
 *   boundary between the outside world (API requests, Stripe webhooks) and the
 *   internal billing engine (plans, invoices, entitlements). It is the
 *   transaction coordinator for all subscription writes. Every subscription
 *   mutation that changes revenue-recognized state flows through this file.
 *   The read side of subscriptions — querying current state, listing active
 *   subscriptions, computing aggregates — lives in a separate file at
 *   billing/subscription-read-model.ts following the CQRS pattern. This split
 *   means the write path can optimize for transactional integrity while the
 *   read path can optimize for query performance, and the two can scale
 *   independently. The split was introduced in ADR-014 and is load-bearing:
 *   adding a read query to this file or a write mutation to the read model
 *   breaks the architectural contract. In the broader business context, this
 *   file is the system of record for revenue events — the finance team's
 *   monthly reconciliation reports depend on the accuracy of every state
 *   transition recorded here.
 *
 * FUNCTION INVENTORY:
 *   createSubscription(plan, user, paymentMethod) -> Subscription
 *     Inputs: plan (Plan object with id, price, interval), user (User object
 *       with id, email, address), paymentMethod (PaymentMethod object with
 *       id, type, last_four).
 *     Outputs: Subscription object with id, status='active', current_period_start,
 *       current_period_end, plan_id, user_id.
 *     Creates a new subscription with initial billing cycle. Validates plan
 *     availability and payment method before creating. Emits
 *     subscription.created event. Fails with SubscriptionCreationError if any
 *     pre-condition check fails. The returned Subscription is the persisted
 *     record, not a projection.
 *     Tests: subscription-manager.test.ts:20-85.
 *
 *   renewSubscription(subscriptionId) -> Subscription
 *     Inputs: subscriptionId (UUID of an active subscription).
 *     Outputs: Subscription object with updated current_period_start and
 *       current_period_end advanced by the plan's billing interval.
 *     Advances subscription to next billing period. Handles proration if plan
 *     changed mid-cycle by computing the difference between old and new plan
 *     prices and issuing a prorated charge or credit. Idempotent — safe to
 *     call multiple times within the same billing window because the function
 *     checks whether the subscription has already been renewed for this period.
 *     Tests: subscription-manager.test.ts:90-140.
 *
 *   cancelSubscription(subscriptionId, reason) -> void
 *     Inputs: subscriptionId (UUID of an active subscription), reason (str
 *       describing why cancellation was requested, stored for analytics).
 *     Outputs: None. Side effect: sets cancelAtPeriodEnd flag on the
 *       subscription and emits subscription.cancellation-scheduled event.
 *     Initiates cancellation. Does NOT immediately terminate the subscription
 *     — the customer retains access until the end of the current billing period.
 *     This behavior is required by ADR-022 (soft-delete policy for billing
 *     entities) which mandates that billing records are never hard-deleted.
 *     Tests: subscription-manager.test.ts:145-190.
 *
 * COMMON MODIFICATION PATTERNS:
 *   Adding a new subscription state: add to subscription-states.ts first,
 *     then add transition guards here, then update subscription-read-model.ts.
 *     The state machine definition is the source of truth — this file only
 *     enforces transitions, it does not define them.
 *   Adding a new billing event: emit in the relevant function here, then
 *     handle in events/billing-events.handler.ts. Events fire after the
 *     mutation is committed so consumers see settled state.
 *   Changing proration logic: isolated to renewSubscription(), unlikely to
 *     have blast radius beyond this file. The proration calculation is a
 *     pure function of old plan, new plan, and billing cycle dates.
 *   Adding a new external integration (e.g., a new payment processor):
 *     the integration's webhook handler lives in webhooks/ — add it there,
 *     have it call the relevant function in this file, and add the caller
 *     to FILE DEPENDENCIES above.
 *
 * WHAT NOT TO DO IN THIS FILE:
 *   1. Do not create, modify, or delete invoices. Invoice generation is
 *      owned by billing/invoice.generator.ts. This file orchestrates the
 *      call to generate invoices but must never contain invoice construction
 *      logic.
 *   2. Do not compute user entitlements or run permission checks.
 *      Entitlement logic is owned by users/entitlements.service.ts. This
 *      file delegates to that service but never decides what features a
 *      user should have.
 *   3. Do not send customer-facing emails or push notifications. All
 *      outbound communication is dispatched by events/billing-events.publisher.ts
 *      after the mutation is committed.
 *   4. Do not query subscription aggregates or analytics directly. Read
 *      queries go through billing/subscription-read-model.ts. This file
 *      is the write side only.
 *   5. Do not define new subscription states or modify the state machine.
 *      The FSM is defined in billing/subscription-states.ts. This file
 *      only enforces transitions — the state definitions live elsewhere.
 *   6. Do not handle Stripe webhook signature verification. Webhook
 *      verification and parsing belongs to webhooks/stripe.handler.ts.
 *      This file receives already-verified events.
 *   7. Do not run database migrations or alter subscription table schemas.
 *      Schema changes are managed through the migrations/ directory and
 *      must never be embedded in application code.
 *
 * KNOWN EDGE CASES:
 *   - Subscriptions with trial_end=null and payment_method=null are zombie
 *     subscriptions from the pre-2024 data migration where trial subscriptions
 *     were not properly normalized. Handled by zombieSubscriptionCleanup()
 *     which archives these records during the nightly batch job.
 *   - Proration calculation breaks when plan changes happen within one minute
 *     of the billing cycle boundary due to floating-point rounding in the
 *     proration formula. The rounding error produces a fractional cent that
 *     causes invoice total mismatches. See issue #1427 for the full
 *     reproduction case.
 *   - If a user has exactly zero payment methods on file and their subscription
 *     enters past_due status, the renewal path must handle the case where
 *     the payment method lookup returns an empty list — not null, not an error,
 *     but a valid empty collection. Handled by the guard clause at line 112.
 *   - Concurrent renewal requests for the same subscription can race. The
 *     advisory lock on subscription:{id} prevents double-billing, but the
 *     lock timeout is 5 seconds — if the database is under heavy load and
 *     the lock acquisition takes longer, the second renewal request will
 *     fail with a LockAcquisitionError rather than silently skipping.
 *   - Subscriptions created during the Stripe billing window transition
 *     (the 3-hour period when Stripe migrates billing anchors) may have
 *     a null current_period_start. These are valid subscriptions but must
 *     be handled by the period-repair job before the next billing cycle.
 *   - Plan objects may reference feature flags that no longer exist in the
 *     feature flag service. When loading a plan, validate that every flag
 *     reference resolves — if a flag is missing, log a warning and treat
 *     the flag as false rather than failing the subscription creation.
 *   - The cancelSubscription function is called from the API, the webhook
 *     handler, AND the internal batch cleanup job. Each caller may pass a
 *     different reason format. The function must accept any string and must
 *     not validate the reason field against an enum.
 *
 * COMMON ERRORS RAISED BY THIS FILE:
 *   SubscriptionCreationError (errors/subscription.ts:30) — plan validation
 *     fails or payment method is invalid. Fix typically in caller by ensuring
 *     the plan ID and payment method are validated before entering this file.
 *   ProrationBoundaryError (errors/subscription.ts:58) — plan changed too
 *     close to billing boundary. Fix in renewSubscription() by adjusting the
 *     proration cut-off window.
 *   LockAcquisitionError (errors/concurrency.ts:15) — advisory lock on
 *     subscription:{id} could not be acquired within the timeout. Indicates
 *     either a concurrent renewal race or database load. Fix by increasing
 *     the lock timeout or investigating database performance.
 *
 * RELATED DOCS:
 *   ADR-014: Subscription CQRS split — explains why subscriptions are split
 *     into separate read and write models. Load this before adding any query
 *     logic to this file or any write logic to the read model.
 *     https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/adr/014-subscription-cqrs.md
 *   ADR-022: Soft-delete policy for billing entities — explains why billing
 *     records are never hard-deleted. Load this before implementing any
 *     deletion or archival logic for subscriptions.
 *     https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/adr/022-soft-delete-billing.md
 *   docs/billing/subscription-lifecycle.md — end-to-end walkthrough of every
 *     state a subscription can occupy and how it transitions between states.
 *     Load this before modifying any state transition logic.
 *     https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/billing/subscription-lifecycle.md
 *   docs/runbooks/subscription-failures.md — runbook for diagnosing and
 *     recovering from common subscription failures. Load this when a
 *     subscription is stuck in an unexpected state or when a customer reports
 *     a billing issue.
 *     https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/runbooks/subscription-failures.md
 *
 * TESTS:
 *   src/billing/__tests__/subscription-manager.test.ts (coverage: 94%)
 *
 * CONCURRENCY:
 *   Uses advisory lock subscription:{id} to prevent duplicate billing.
 *   Do not remove without an alternative concurrency control.
 */

When editing or updating this file, whenever you make a change you must also cross-reference the file header comment and update any information that is no longer accurate. The header describes the architectural contract of the file, and after a modification the contract may have shifted — you might have added a function that is now missing from FUNCTION INVENTORY, changed a dependency that makes ROLE IN CODEBASE stale, or introduced a new edge case that should be recorded in KNOWN EDGE CASES. Treat the header as living documentation that evolves with the code: every commit that changes the file body is a commit that potentially invalidates part of the header, and it is your responsibility to reconcile the two before declaring the change complete. This cross-reference step prevents the most common cause of header staleness — a developer making a quick bug fix, forgetting to update the header, and leaving an inaccurate contract for the next agent that opens the file.

# Adversarial Review
Many times a model will generate the header first and then the code, but the finished code will deviate from what the header described — new functions were added that do not appear in FUNCTION INVENTORY, a helper was extracted that changes the dependency list, or an edge case was discovered during implementation that needs to go into KNOWN EDGE CASES. To prevent header drift, follow this adversarial review workflow on every file you create or modify.
* Step 1 — Write the header first. Before writing any code, write the complete structured file header as described in this prompt. The header captures the architectural contract you intend to implement. Do not proceed until the header is complete.
* Step 2 — Implement the code. Write the full file body against the contract defined in the header. If you discover during implementation that the contract is wrong — a function you planned to write is not needed, a dependency is different than expected, or an edge case materializes — continue coding the correct solution, but keep a mental note of what changed.
* Step 3 — Cross-reference code against header. After the code is complete, re-read the header section by section. For each section, verify that it still accurately describes the code that exists in the file body. Pay special attention to FUNCTION INVENTORY — every exported function in the code must appear in the inventory with the correct signature and description. Check ROLE IN CODEBASE — every import and every caller relationship must be current. Check WHAT NOT TO DO IN THIS FILE — if you added a responsibility during implementation, make sure the "not to do" list still redirects correctly.
* Step 4 — Update the header. Fix every section that the code contradicts. Add any new functions to FUNCTION INVENTORY. Remove any planned functions you did not write. Update ROLE IN CODEBASE with the actual imports and callers. Add any edge cases discovered during implementation to KNOWN EDGE CASES. Add any new errors thrown to COMMON ERRORS RAISED BY THIS FILE. The final header must describe the code that actually exists — not the code you planned to write in Step 1.
* Step 5 — Verify completeness. Confirm that every required section that is applicable to this file is present and non-empty. If the file is called by other files, ROLE IN CODEBASE must list them. If the file throws errors, COMMON ERRORS RAISED BY THIS FILE must enumerate them. Delete any section that has no content rather than leaving it as a placeholder.

# Maintenance and Staleness
File headers rot faster than the code they describe. After the third refactor, function descriptions and last-modified dates will be wrong. Defend against staleness with these strategies.
* Intent-only headers — Describe what the file IS and WHY it exists, not implementation details that change with every refactor. The PURPOSE and ROLE sections are durable. The FUNCTION INVENTORY section is volatile and should carry a last-reviewed date.
* Auto-generated dependency sections — Use dependency analysis tooling such as depcruise or madge to inject the ROLE IN CODEBASE section automatically on commit. This keeps the caller-callee graph fresh without manual maintenance.
* CI lint rule — Add a lint check that warns when a file header's last-reviewed date exceeds a threshold, such as ninety days. The warning does not block the build but nudges developers to refresh headers.
* Cross-file consistency — If file A header says "called by file B", file B header should say "calls file A". This bidirectional cross-reference is high-maintenance but immensely valuable. Tooling can enforce it — a CI check that parses headers and verifies the caller-callee graph is consistent.
* Re-run adversarial review on every significant change — Any change that adds or removes a function, alters the dependency graph, or introduces a new edge case must trigger a Step 3 cross-reference pass to keep the header accurate.

# Checklist
* Every source file must open with a structured header comment using the section conventions defined in this prompt. An agent encountering the file for the first time should be able to answer what this file does, what it touches, and whether this is the right file to modify — all from the header alone, without scanning the code body.
* The first three lines of every header must convey what the file does, what it touches, and whether the reader should keep looking. These three lines are the rejection filter: if an agent is searching for where invoice logic lives, the header must signal within three lines that this file is or is not the right place.
* Every exported function must appear in the FUNCTION INVENTORY with a one-line description and test coverage reference. If a function exists in the code but not in the header, the header is stale and agents will miss its existence when scanning. The adversarial review pass catches this.
* Every file header must include a ROLE IN CODEBASE section listing callers and callees. This is the file's position on the dependency map, and without it an agent must trace imports manually to understand the neighborhood. The cost of missing this section is repeated context-window waste.
* Every file header must include COMMON MODIFICATION PATTERNS describing how to perform typical tasks that touch this file. This section saves the agent from trial-and-error exploration, which is the most expensive form of learning in a context-window-constrained environment.
* Every file header must include a WHAT NOT TO DO IN THIS FILE section listing operations the agent should never attempt here, each redirecting to the file that owns that responsibility. This section is the negative-space map — it prevents the agent from implementing a feature in the wrong file, which is one of the hardest bugs to detect and fix.
* Every file header must include KNOWN EDGE CASES documenting legacy data patterns and known bugs. Without this section, an agent hits the same trap the last developer hit, wasting an entire debugging cycle on a documented problem it could have been warned about.
* Every file header must include a TESTS section pointing at the test file and coverage percentage. After making changes, the agent must know which test suite to run and whether existing coverage is adequate to catch regressions in the modified code path.
* Cross-reference errors and headers — file headers should list COMMON ERRORS RAISED BY THIS FILE and where each is typically resolved. If an error is thrown from this file but the header does not mention it, an agent that catches that error will have no navigational signal pointing it back to the source.
* Run the adversarial review workflow after every file creation or modification — header first, code second, cross-reference third, update header fourth, verify fifth. The header must describe the code that exists, not the code that was planned.
* Before writing any error classes for this file, audit every function for distinct failure modes and list them all. Define one error class per failure mode before writing any raise sites — discovering failure modes as you go leads to generic classes that bundle multiple modes and lose diagnostic signal.
* After defining each error class for this file, cross-reference every field in the class against the field anatomy in the error messages prompt. Every field that is knowable at definition time — description, expected_vs_actual, blast_radius, doc_links, test_files, fix_approaches — must be baked into the class as a static default. Raise sites must only pass the dynamic fields that change per invocation.
* When writing RELATED DOCS, include full URLs, not document names. An agent cannot fetch a title but can fetch a URL. After writing each link, verify it is reachable and points to content specifically relevant to this file's failure modes.
* After finishing all error classes for this file, run a self-review: catch each error in a toy script, call to_context_packet(), and verify the output contains enough information to diagnose the failure without opening any other file. If the context packet is insufficient, the class definition is incomplete.
* When writing fix_approaches for any error class defined in this file, include at least one high-level investigation strategy (how to reproduce and trace the failure using a dev server, logs, or documentation) and at least one specific code-level fix (what to change and where). A list of only investigation steps leaves the agent without a resolution path; a list of only code fixes leaves it without a starting point.

# Things Not to Do
* Do not write a header without a code body. The header exists to describe real code, and a header without code is an untethered architectural daydream that will mislead any agent that reads it.
* Do not copy a header verbatim from another file. Header content is file-specific — the FILE, PURPOSE, ROLE IN CODEBASE, FUNCTION INVENTORY, and WHAT NOT TO DO must all be written fresh for each file.
* Do not leave placeholder text in any header section. If a section does not apply to this file — for example, CONCURRENCY MODEL for a file with no locking — omit the section entirely rather than writing "TBD" or "N/A".
* Do not describe implementation mechanics in the header. The header describes architectural facts — what the file is, what it owns, and what it connects to. Code-level details like variable names, loop structures, and internal helper functions belong in inline comments near the code they describe, not in the header.
* Do not skip the adversarial review pass on a file you modify. If you added a function, the header's FUNCTION INVENTORY must list it. If you changed a dependency, ROLE IN CODEBASE must reflect it. A header that describes last week's version of the file is worse than no header at all.
* Do not use the header as a substitute for inline comments on complex logic. The header provides navigational and architectural context. Code that is subtle, non-obvious, or reliant on external invariants still needs inline comments at the point of complexity.
* Do not omit sections to save time or space. The cost of a missing WHAT NOT TO DO IN THIS FILE is not the bytes saved — it is the agent-hours wasted implementing functionality in the wrong file. Every section exists because its absence causes a specific, measurable failure mode.

# Conclusion
A file header is not a decorative preface or a checklist trophy. It is the first routing interface a cold agent uses to decide whether this file is relevant, what responsibility it owns, and what damage a change here might cause. The exact section inventory matters because each section prevents a known navigation failure, but the higher-order goal is orientation, not bulk. Do not copy the example into every file as if length alone creates signal. A good header is specific, current, and written to durable architectural intent rather than transient implementation detail. If a section would become filler, sharpen it until it answers a real agent question or omit it when the prompt allows omission. The adversarial review step is the safeguard that keeps the header aligned with the code that actually shipped. Leave this file thinking less about formatting a comment and more about making each source file self-locating, self-describing, and hard to misuse.
