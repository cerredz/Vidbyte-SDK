# Description
Every server-side error you throw must function as a complete self-contained diagnostic unit that an agent can boot from cold. The error object is the primary bootstrap context for any agent that catches it — the agent should be able to identify the failure mode from the error type alone, understand the contract that was violated, inspect the runtime state that triggered the failure, assess which files are affected, rank the most likely causes by probability, and consult remediation patterns before making a single edit. You achieve this by defining one custom error class per distinct failure mode and encoding all static diagnostic information — the description, the expected versus actual contract, the blast radius, the documentation links, the test files, and the common fix strategies — as class-level defaults at definition time rather than at the raise site. This separation keeps the class definition information-rich and the raise sites minimal: when you raise an error, you pass only the dynamic fields that change per invocation, such as the specific entity IDs involved in the failure. An agent that catches a BillingSubscriptionCreationError immediately knows the failure domain, the boundary that was crossed, and the files to inspect — all from the type and the static class defaults, before reading a single line of the throw site. You should create far more custom error classes and throw sites than a regular developer would, because agents can generate them mechanically and the diagnostic benefit compounds on every future debugging cycle.

# Intent
The intent of agent-native error messages is to turn failure into a structured handoff rather than a dead end. When an agent encounters an exception, the error object should carry enough local truth for the next debugging action: what invariant failed, which runtime state mattered, what files are likely affected, and which repair paths are plausible. The error is not just a user-facing sentence or a logging string; it is a diagnostic interface.

This principle is trying to make backend failures self-localizing and self-explanatory. Agents are weakest when they must infer root cause from a vague message and an incomplete stack trace. Rich SDK-scoped error packets reduce that search space by encoding the failure mode, likely causes, blast radius, and test path in a stable place that travels with the exception.

# What Goes Inside Each Server-Side Error Message
* error_type — A unique descriptive error class name. Not "Error" or "AppError". Must be grepable by agents and matchable against known failure patterns. Examples: "SubscriptionCreationError", "PlanValidationError", "PaymentMethodDeclinedError". Specialized error classes let an agent recognize a failure mode from the type alone without parsing the message string.
* file, line, function — Exact coordinates of every throw site. Standard but non-negotiable. An error must always carry its own location so the agent never has to guess which file or line produced it.
* rich_message — Prose combining semantic meaning with mechanical detail. Not "Failed to save user" but "Failed to create subscription for user_id=abc123 — plan validation returned null for plan_id=xyz789 at billing/plans.store.ts:45." The message must contain both what happened and the concrete data that demonstrates it.
* description — A paragraph describing what this error class represents, why it is raised, what invariant or precondition it enforces, and where the root cause is most likely to live. This is distinct from the rich_message — description is a static class-level field that explains the failure mode in general terms, while rich_message is a dynamic raise-site field that describes the specific invocation that failed.
* expected_vs_actual — Two explicitly labelled sub-blocks: Expected (5-7 sentences describing the intended behavior and preconditions that must hold) and Actual (5-7 sentences describing what was observed and why the precondition failed). This is the single most actionable field for root-cause diagnosis.
* current_state — Snapshot of relevant local or object state at the crash point. Include the shape of the data that caused the failure, not just its value. The agent needs to see the data that triggered the path, not infer it from surrounding code.
* call_trace — Annotated call chain with role descriptions for each frame, not a raw stack trace. Role annotations tell the agent what each frame is responsible for so it can decide where to place the fix.
* blast_radius — References to files likely affected or worth inspecting, each entry 3-4 sentences describing what the file does, how it is affected by this error, and what to verify in it. This prevents the agent from fixing the symptom in one file while missing downstream breakage in related files.
* possible_causes — Ranked hypotheses with rough probability estimates. Ranked hypotheses give the agent a triage order instead of a blank slate.
* fix_approaches — A numbered list of 4 investigation and remediation strategies. Include both high-level investigation strategies (how to reproduce and trace the failure using logs, dev servers, and documentation) and specific code-level fixes (what to change and where). Fix history turns the error from a mystery into a known recovery path.
* doc_links — Full URLs to ADRs, runbooks, and internal documentation, each followed by 4-5 sentences describing what the document explains and when an agent should load it. Links let the agent pull deeper context on demand without stuffing it into every error.
* test_files — Which test file or files cover this execution path, with a 3-5 sentence explanation of what the tests validate, which line ranges cover the failure path, and what to run after applying a fix.

# Placement Strategy
* Wrap every external boundary — DB calls, API calls, file I/O, and message queue operations — with a try/catch that re-throws a custom packed error. Do this at the specific operation level, not just the top-level handler, so the error carries the exact operation that was being attempted.
* Pre-condition assertions become rich errors. Instead of 'if (!user) throw new Error("No user")', write 'if (!user) throw new NoUserError({ context: { sessionId, requestPath }, ... })'. Every invariant check that can fail should fail with a structured packet.
* Every state-transition boundary — any function that changes system state and can fail mid-transition — should capture before/after snapshots in the error if the transition fails partway through.
* Every integration seam — files bridging between subsystems such as auth to billing, API to worker, web to DB — is a natural error-wrapping point because these are where invariants cross boundaries and where failures are most expensive to diagnose.
* Custom error classes should proliferate. One error class per failure mode, not one generic AppError for everything. An agent that catches a SubscriptionCreationError immediately knows the failure domain. An agent that catches an AppError with message "creation failed" knows nothing.

# Things Not to Do
* Do not create frontend or client-side error messages with this level of internal detail. The rich context packet format — with file paths, state snapshots, call traces, and internal file references — is designed for server-side agents operating inside the runtime. Exposing these details to a browser or mobile client leaks implementation internals and creates a security risk.
* Do not fabricate any error message data. Every field in the error packet — description, current_state, call_trace, possible_causes, fix_approaches — must reflect the actual runtime conditions at the throw site. Guessing or inventing values misdirects the agent and is worse than omitting the field.
* Do not point the agent in the wrong direction with fix_approaches or possible_causes. If you are not confident about the likely cause or remediation pattern, omit the field or mark the confidence as low. An incorrect hypothesis with high confidence wastes more agent time than no hypothesis at all.
* Do not log sensitive data in error fields that ship to production. PII, authentication tokens, API keys, and session secrets must be redacted from current_state, rich_message, and any other field before the error leaves the server. Use a dedicated redaction layer rather than relying on developers to remember per throw site.
* Do not use a single generic error class for multiple failure modes. An agent catching AppError with message "something went wrong" has zero diagnostic signal. Every distinct failure mode needs its own class so the agent can route its response from the type alone.

# Checklist
* Before writing any error class, audit every function in the file for distinct failure modes and list them all. Define one error class per failure mode before writing any raise sites — discovering failure modes as you go leads to generic classes that bundle multiple modes into one uninformative type.
* After defining an error class, cross-reference each field in the class against the field anatomy in the "What Goes Inside Each Server-Side Error Message" section above. Every field that is knowable at definition time must be set as a static class-level default — if you are populating a field at the raise site that never changes per invocation, move it into the class definition.
* Before writing each raise site, explicitly decide which fields are dynamic (change per invocation, such as entity IDs and runtime state) and which are static (the same for every throw of this error). The raise site must only pass dynamic fields — everything else belongs in the class.
* After completing a function, walk every code path and verify each potential failure point has a throw site. Uncovered failure paths are the most common source of uninformative errors — a bare Exception or a silent return is as bad as no error handling at all.
* When writing fix_approaches, ensure at least one item is a high-level investigation strategy (how to reproduce and trace the failure using a dev server, logs, or documentation) and at least one is a specific code change (what to modify and where). A list of only code-level fixes leaves the agent without a starting point; a list of only investigation steps leaves the agent without a resolution path.
* When writing doc_links, include the full fetchable URL, not just the document name. Verify each URL is reachable and points to content specifically relevant to this failure mode. An agent that sees only a title cannot fetch the document.
* After writing test_files, verify that the referenced line ranges actually cover the failure path that raises this error. A reference pointing at an unrelated test gives the agent false confidence that the failure path is tested.
* When writing blast_radius, trace the dependency graph for the failing file and include every downstream file that is affected by a failure to complete the operation this error prevents. An agent that fixes the throw site but misses a downstream consumer may leave broken state in related files.
* When writing expected_vs_actual, write two explicitly labelled sub-blocks: "Expected:" followed by 5-7 sentences on the intended behavior and preconditions, then "Actual:" followed by 5-7 sentences on what was observed and why the precondition failed. The split forces precision and prevents the field from collapsing into a vague one-liner.
* After defining all error classes in a file, run a self-review: catch each error in a toy script, call to_context_packet(), and verify the output contains enough information to diagnose the failure without opening any other file. If the context packet is insufficient, the class definition is incomplete.

# Code Examples
These Python snippets demonstrate the full agentic error pattern. The error class is defined once in a dedicated errors file with all static fields baked in as class-level defaults — this keeps the class definition information-rich and the raise sites minimal. Each raise site passes only the dynamic fields that change per invocation.

```python
# Example 1: Defining a custom error class with all static fields baked in as
# class-level defaults. This class lives in a dedicated errors file
# (e.g., errors/billing.py). Static fields — description, expected_vs_actual,
# blast_radius, doc_links, test_files, and fix_approaches — are set at the
# class level because they describe the failure mode in general and do not
# change per invocation. The raise site (Example 2) passes only the dynamic
# fields: user_id and address, which are the entity-specific inputs that
# triggered the failure.

class BillingSubscriptionCreationError(Exception):
    _description = (
        "BillingSubscriptionCreationError is raised when the subscription creation "
        "pipeline fails at the user address validation boundary before any database "
        "writes or external API calls have been made. "
        "This error signals that the user object passed into the billing service by "
        "the API layer is incomplete — specifically that user.address is null, "
        "missing a zip code, or in a shape that cannot be used to generate a billing "
        "invoice. "
        "The error is not caused by a defect in the billing service itself: the "
        "billing service is behaving correctly by refusing to proceed without a "
        "valid billing address. "
        "The root cause is almost always in the calling layer — the API handler that "
        "queried a partial user projection and forwarded an incomplete object without "
        "validating the address field first. "
        "Because no state mutations have occurred at the time this error is raised, "
        "there is no partial state to clean up or roll back: the error is safe to "
        "catch and retry after the caller corrects the user object. "
        "An agent that catches this error should first inspect the user_id and address "
        "attributes to see the exact input that was passed, then trace the API handler "
        "that queried and forwarded it to find the incomplete query or missing validation "
        "guard. "
        "The fix is almost always upstream of the billing service, not inside it."
    )
    _expected_vs_actual = (
        "Expected: The user object passed to billing.create_subscription must have a "
        "non-null address field with a valid zip code before any billing work begins. "
        "The address is required because the invoice generator uses it as the billing "
        "address for the subscription invoice, the payment processor requires it for "
        "fraud detection and address verification, and tax computation depends on the "
        "billing address to determine the correct jurisdiction. "
        "The address must be a complete object with at minimum a zip code string that "
        "is non-empty and matches a known postal code format. "
        "The address validation service is expected to have already verified the address "
        "before the user object reaches this function, so the billing service trusts that "
        "any non-null address with a non-null zip code is a valid billing address. "
        "In summary, the pre-condition at the boundary between the API layer and the "
        "billing service is: user.address is not None and user.address.zip is not None "
        "and len(user.address.zip) > 0.\n\n"
        "Actual: The user object received by create_subscription has address=None or "
        "has address.zip=None, which means the user record was queried or forwarded "
        "without the address relation being fetched or the address having been set. "
        "The billing service cannot proceed to create an invoice, charge the payment "
        "method, or grant entitlements because the billing address is missing — any "
        "of these downstream operations would either fail on a null pointer or produce "
        "a billing record with no address on file. "
        "The partial user object was most likely produced by an API handler that queried "
        "a projection of the user table that excludes the address relation, or by a data "
        "sync path where the user was created before the address was attached. "
        "Because this function is the first place in the pipeline to assert the address "
        "pre-condition, the failure surfaces here even though the root cause is in the "
        "calling layer. "
        "No state was modified and no external call was attempted before this error "
        "was raised."
    )
    _blast_radius = [
        "billing/subscription-manager.py — The orchestrating function that raised this "
        "error cannot complete subscription creation without a valid billing address. "
        "All downstream operations in this file — invoice creation, payment processing, "
        "and entitlement assignment — are blocked until the address precondition is "
        "satisfied. If this file is modified to skip the address check, it will produce "
        "subscriptions with no billing address on file, causing silent invoice failures "
        "downstream.",

        "billing/invoice.generator.py — Invoice generation requires a valid billing "
        "address to populate the invoice record in the database and to pass to the "
        "payment processor. If create_subscription were to proceed without an address, "
        "this file would receive a null billing_address parameter and either raise its "
        "own error or create an invoice with no address, which would fail at payment "
        "time. Verify after any fix that the invoice creation path still receives a "
        "complete address object.",

        "billing/plans.store.py — Plan validation runs inside create_subscription "
        "before the address check, so if this error is raised it means the plan has "
        "already been validated and the plan_id is known good. However, if the fix "
        "involves changing what is fetched from the plans store, verify that the plan "
        "object still has the fields billing/invoice.generator.py expects. Inspect "
        "find_active_plan for any join that might affect the user data pipeline.",

        "users/entitlements.service.py — Entitlement assignment is the final step of "
        "subscription creation and is completely blocked by this error. The entitlements "
        "service never receives the call to grant the user access to subscription "
        "features. If a user reports being charged but having no access, and this error "
        "was previously raised and silently swallowed, inspect the entitlements table "
        "to confirm no partial entitlement was granted.",

        "events/billing-events.publisher.py — The subscription.created event is "
        "dispatched by this publisher after a successful subscription creation and will "
        "never fire if this error is raised. Downstream consumers — email notification "
        "services, analytics pipelines, and third-party integrations — will not receive "
        "the subscription created signal. If a downstream consumer reports missing "
        "events for a user, check whether this error was silently swallowed during "
        "the subscription creation attempt.",

        "api/subscriptions.route.py — This is the most likely location of the root "
        "cause. The API handler is responsible for fetching the user object and passing "
        "it to the billing service, and if the user object is missing an address, the "
        "handler either queried a partial projection or forwarded an incomplete object "
        "without validation. The fix almost always belongs here: update the user query "
        "to include the address relation, add an explicit address validation check "
        "before delegating to the billing service, and return a 400 error if the "
        "address is missing rather than allowing the incomplete request to reach the "
        "billing layer.",

        "users/user.service.py — The user service is the authoritative source of user "
        "records including addresses. If the address is missing from the user object, "
        "the user service query in the API handler may be selecting only a subset of "
        "user fields or querying a cache that does not include the address. Inspect the "
        "query that the API handler uses to fetch the user and verify it fetches the "
        "address relation. Also check whether the address was set during user creation "
        "or whether it is a separate update that may not have been applied yet.",

        "tests/billing/test_subscription_manager.py — The test file covering "
        "create_subscription includes tests for the address validation precondition. "
        "If the fix changes how the address check is performed or adds a new validation "
        "layer, these tests must be updated to reflect the new behavior. Run this file "
        "after the fix to verify the address validation logic is correct and the error "
        "is raised with the expected fields under the expected conditions.",
    ]
    _doc_links = [
        "https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/adr/014-subscription-cqrs.md "
        "— ADR-014 documents the architectural decision to split subscription handling "
        "into separate read and write models following the CQRS pattern. This ADR "
        "explains why all subscription mutations flow exclusively through "
        "billing/subscription-manager.py and why read queries are handled by a separate "
        "read model. Load this document before adding any query logic to the write path "
        "or any write logic to the read model, because the CQRS split is a load-bearing "
        "architectural constraint that must not be violated. The ADR also defines the "
        "transactional boundary that this error enforces: subscription creation is an "
        "all-or-nothing operation, and any failure before commit must leave no partial "
        "state.",

        "https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/runbooks/subscription-failures.md "
        "— The subscription failures runbook contains step-by-step diagnostic procedures "
        "for every failure mode in the subscription creation pipeline, including missing "
        "address errors. Section 3 covers the specific case where create_subscription "
        "raises BillingSubscriptionCreationError due to a missing user address, with "
        "detailed steps for tracing the user object back to its source query and "
        "identifying whether the address is missing from the database or from the query "
        "projection. The runbook also includes a list of known incidents where this "
        "error was silently swallowed by an API handler and the resulting data "
        "inconsistencies that were discovered during reconciliation. Load this when an "
        "agent encounters a BillingSubscriptionCreationError in production logs and "
        "needs a triage procedure rather than a code-reading strategy.",

        "https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/billing/subscription-lifecycle.md "
        "— This document describes the full state machine for a subscription from "
        "creation through cancellation, including all the pre-condition checks that "
        "must pass at each transition point. The address validation that triggers this "
        "error is documented in the Creation phase of the lifecycle, along with the "
        "specific fields the billing service requires from the user object. Load this "
        "document when the fix involves changing or relaxing the address validation "
        "pre-condition, because the downstream states (active, past_due, canceled) all "
        "assume the subscription was created with a valid billing address on file.",
    ]
    _test_files = [
        "tests/billing/test_subscription_manager.py:20-85 — This test module covers "
        "the create_subscription function in billing/subscription-manager.py. "
        "Lines 20-40 test the happy path where a complete user object with a valid "
        "address passes through and a subscription is created successfully. "
        "Lines 41-60 cover pre-condition failures including the address validation "
        "that raises BillingSubscriptionCreationError — these tests verify that the "
        "error is raised with the correct class name, that the context packet contains "
        "non-empty description, expected_vs_actual, blast_radius, and fix_approaches "
        "fields, and that the rich_message includes the user_id and address shape that "
        "triggered the failure. "
        "Lines 61-85 cover integration seam failures where the database call succeeds "
        "but downstream steps fail, verifying that the error packet in those cases "
        "identifies the correct boundary and blast radius. "
        "Run this file after any change to the address validation logic, the error "
        "class definition, or the __init__ parameter list to confirm the error packet "
        "is still correctly populated.",
    ]
    _fix_approaches = [
        "1. Reproduce and trace locally: Start the local development server, send a "
        "POST request to the subscription creation endpoint with a user account that "
        "has no address on file, and capture the full error packet that is logged. "
        "Read the user_id and address attributes on the raised error to see the exact "
        "shape of the user object that was passed to create_subscription. Then trace "
        "backwards through the call chain to find the API handler function that queried "
        "and forwarded the incomplete user object, and open that function to identify "
        "the database query or cache lookup that produced the partial user projection.",

        "2. Cross-reference documentation with implementation: Use web fetch to retrieve "
        "the subscription-lifecycle.md document linked in _doc_links and read the address "
        "validation requirements documented in the Creation phase. Then open "
        "api/subscriptions.route.py and compare the user object query in the create "
        "handler against what the lifecycle document requires. If the query is fetching "
        "a projection that excludes the address field, the fix is to update the query "
        "to include the address relation before passing the user object to the billing "
        "service.",

        "3. Check prior resolution patterns: Inspect PR #2841 in the repository history "
        "to see how a similar missing-address error was resolved in a previous incident. "
        "The PR diff will show whether the fix was to update the user query in the API "
        "handler, to add an address validation guard at the API layer boundary, or to "
        "update the user service to always include the address in its default projection. "
        "Apply the same resolution pattern here, adjusting for any differences in the "
        "current API handler structure.",

        "4. Apply the code fix: Update the user lookup in api/subscriptions.route.py to "
        "fetch the complete user object including the address relation — change the "
        "SELECT projection or ORM query to include the address join. Add an explicit "
        "address validation check in the handler before delegating to the billing "
        "service: if address is missing or address.zip is missing, return a 400 error "
        "to the client with a clear message rather than forwarding the incomplete object. "
        "After the fix, add a test in tests/billing/test_subscription_manager.py that "
        "passes a partial user object and verifies that BillingSubscriptionCreationError "
        "is raised with the expected fields populated.",
    ]

    def __init__(self, *, user_id: str = "", address: object = None):
        self.user_id = user_id
        self.address = address
        self.description = self._description
        self.expected_vs_actual = self._expected_vs_actual
        self.blast_radius = self._blast_radius
        self.doc_links = self._doc_links
        self.test_files = self._test_files
        self.fix_approaches = self._fix_approaches
        rich_message = (
            f"BillingSubscriptionCreationError: user_id={user_id} — "
            f"user.address={address}. "
            f"Address is null or missing zip code. See _description for full context."
        )
        super().__init__(rich_message)

    def to_context_packet(self) -> dict:
        return {
            "error_type": type(self).__name__,
            "user_id": self.user_id,
            "address": self.address,
            "description": self.description,
            "expected_vs_actual": self.expected_vs_actual,
            "blast_radius": self.blast_radius,
            "doc_links": self.doc_links,
            "test_files": self.test_files,
            "fix_approaches": self.fix_approaches,
        }
```

```python
# Example 2: Raising the custom error at a pre-condition check inside a service
# function. The raise site is intentionally minimal — it passes only the dynamic
# fields that change per invocation (user_id and address). All static diagnostic
# information (description, expected_vs_actual, blast_radius, doc_links,
# test_files, fix_approaches) is baked into the class definition above and does
# not need to be repeated here.

def create_subscription(plan_id: str, user: dict, payment_method_id: str) -> dict:
    if not user.get("address") or not user["address"].get("zip"):
        raise BillingSubscriptionCreationError(
            user_id=user.get("id"),
            address=user.get("address"),
        )
```

```python
# Example 3: A second error class — PlanValidationError — following the same
# pattern. All static fields are baked into the class definition. The raise
# site (Example 4 below) passes only plan_id, which is the single dynamic
# field that identifies which entity triggered the failure.

class PlanValidationError(Exception):
    _description = (
        "PlanValidationError is raised when the billing service cannot resolve the "
        "provided plan_id to an active, non-deleted record in the plans database table "
        "during subscription creation. "
        "The error fires at the data access boundary inside billing/plans.store.py "
        "after plan lookup fails — either because the plan does not exist, has been "
        "deactivated, was soft-deleted, or because a database replication lag is "
        "causing the read replica to return stale results. "
        "This error is specifically a data-layer failure: the code is behaving "
        "correctly, but the data it was given does not satisfy the invariant that "
        "every subscription must reference an active plan. "
        "Because this error is raised before any invoice, entitlement, or event "
        "records are created, no rollback or cleanup is required when it is caught. "
        "An agent that catches this error should first check the plans admin panel to "
        "verify the status of the plan_id, then inspect the source of the plan_id in "
        "the call chain to understand whether it is coming from user input, a Stripe "
        "event, a partner integration, or hardcoded configuration. "
        "The fix is usually a data correction — reactivating a plan, updating an ID "
        "mapping, or correcting a migration — rather than a code change in the billing "
        "service itself."
    )
    _expected_vs_actual = (
        "Expected: The plans database table must contain a row with id equal to "
        "plan_id and status equal to 'active', with non-null values for the price, "
        "billing_interval, and feature_flags columns. "
        "The plan record must not be soft-deleted (the deleted_at column must be null). "
        "The query 'SELECT * FROM plans WHERE id = plan_id AND status = active' must "
        "return at least one row for the subscription creation pipeline to proceed. "
        "Plan validation is a mandatory step that occurs before any invoice record is "
        "created — a subscription must always reference an active plan so that billing "
        "interval, price, and feature flags can be computed correctly for the invoice "
        "and entitlement steps.\n\n"
        "Actual: The query 'SELECT * FROM plans WHERE id = plan_id AND status = active' "
        "returned zero rows for the provided plan_id. "
        "This means the plan either does not exist in the database, has been deactivated "
        "by setting status to 'inactive', was soft-deleted by an admin, or exists with "
        "a different status value than 'active'. "
        "The plan_id was passed to find_active_plan by billing/subscription-manager.py "
        "which received it from the API layer — the API layer does not validate plan IDs "
        "before forwarding them to the billing service, so any invalid, deactivated, or "
        "misformatted plan_id will produce this error at this boundary. "
        "Because no state mutations have occurred at the time this error is raised, "
        "there is no partial state to clean up. "
        "The subscription creation pipeline is fully blocked until a valid active "
        "plan_id is provided."
    )
    _blast_radius = [
        "billing/subscription-manager.py — Subscription creation is completely blocked "
        "by this error because plan metadata is required for every downstream step. "
        "The invoice generator needs the plan price and billing interval, the "
        "entitlements service needs the plan's feature flags, and the events publisher "
        "embeds the plan_id in the subscription.created event payload. If this error "
        "occurs, none of those steps execute and the user is not subscribed.",

        "billing/invoice.generator.py — This file depends on plan metadata (price, "
        "billing_interval, currency) to construct the invoice record for the "
        "subscription. If PlanValidationError is raised during plan lookup, this file "
        "is never called and no invoice is created. If the fix involves changing how "
        "plans are fetched, verify that invoice.generator.py still receives the "
        "complete plan object it expects, particularly the billing_interval and "
        "currency fields.",

        "api/subscriptions.route.py — This is the immediate caller that provided the "
        "plan_id to the billing service. If the plan_id is invalid, the API handler "
        "either accepted bad input from the client, is using a stale ID from its own "
        "configuration, or is translating from an external ID format incorrectly. "
        "Inspect the handler to see where the plan_id originates and add plan_id "
        "validation at the API layer to catch invalid IDs before they reach the billing "
        "service.",

        "users/entitlements.service.py — The entitlement assignment step that runs "
        "after invoice creation is completely blocked by this error. The user will not "
        "receive the subscription features they are attempting to unlock. If a user "
        "reports that they paid but have no access, check whether PlanValidationError "
        "was raised and silently swallowed at any point during their subscription "
        "creation attempt.",

        "events/billing-events.publisher.py — The subscription.created event will not "
        "fire because subscription creation never completes. Downstream analytics "
        "pipelines, notification services, and third-party integrations that rely on "
        "this event will miss the subscription signal for this user. If downstream "
        "services report missing subscription events, cross-reference their missing "
        "records against the billing error logs for PlanValidationError occurrences.",

        "webhooks/stripe.handler.py — If the plan_id came from a Stripe webhook event "
        "(for example, a price ID from a checkout.session.completed event), the "
        "Stripe-to-internal plan ID mapping in this file may be the source of the "
        "invalid ID. Check whether the Stripe product or price referenced in the "
        "webhook has a corresponding active plan in the internal plans table. If a "
        "Stripe price was updated or archived without updating the internal plan, "
        "this handler will forward a plan_id that no longer resolves.",

        "billing/plans.store.py — This is the throw site for PlanValidationError. "
        "If the fix involves changing the plan lookup query — for example, to follow "
        "a soft-delete pattern or to include plans with a different status value — "
        "verify that the change does not inadvertently return deactivated or archived "
        "plans as valid. The invariant that every subscription references an active "
        "plan is enforced here, and any relaxation of this check must be intentional "
        "and documented.",

        "tests/billing/test_plans_store.py — The test file covering find_active_plan "
        "includes tests for the PlanValidationError case. Lines 30-60 test the scenario "
        "where no active plan is found and verify that the error is raised with the "
        "correct class name and that the context packet includes the plan_id, "
        "description, blast_radius, and fix_approaches fields. Run this file after any "
        "change to the plan lookup logic or the PlanValidationError class definition to "
        "confirm the error is raised under the correct conditions.",
    ]
    _doc_links = [
        "https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/adr/014-subscription-cqrs.md "
        "— ADR-014 documents the CQRS split for subscription handling and explains why "
        "plan validation is a discrete, mandatory step in the write pipeline rather "
        "than being inlined in the orchestrator. This ADR defines the transactional "
        "boundary that PlanValidationError enforces: plan validation must succeed before "
        "any invoice or entitlement work begins, because a subscription created against "
        "an invalid plan would produce billing records that cannot be reconciled. Load "
        "this document before making any changes to the plan validation step or the "
        "order of operations in subscription creation.",

        "https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/billing/plan-lifecycle.md "
        "— This document describes the full lifecycle of a plan from creation through "
        "activation, deactivation, and archival, including the status values a plan "
        "can have and the transitions between them. Load this when debugging a "
        "PlanValidationError to understand whether the plan_id referenced a plan that "
        "was intentionally deactivated (in which case the fix is to use a different "
        "plan) or deactivated by accident (in which case the fix is to reactivate it). "
        "The document also explains which automated lifecycle processes can change a "
        "plan's status, which is important when the deactivation was unexpected.",

        "https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/runbooks/subscription-failures.md "
        "— Section 4 of this runbook covers PlanValidationError specifically, with a "
        "step-by-step diagnostic procedure for identifying why plan lookup failed. "
        "The procedure includes SQL queries to run against the plans table to check the "
        "plan's status and soft-delete state, instructions for checking the Stripe "
        "product mapping if the plan_id originated from a webhook, and escalation steps "
        "if the plan_id is valid but the error is being raised due to replication lag. "
        "Load this when encountering a PlanValidationError in production and follow the "
        "runbook procedure before making any code changes.",
    ]
    _test_files = [
        "tests/billing/test_plans_store.py:30-60 — This test module covers "
        "find_active_plan in billing/plans.store.py. "
        "Lines 30-45 test the happy path where a valid active plan_id resolves "
        "successfully and the plan object is returned with all required fields. "
        "Lines 46-60 test the failure path where no active plan is found: these tests "
        "verify that PlanValidationError is raised with the correct class, that the "
        "plan_id is accessible on the raised error, and that the description, "
        "blast_radius, doc_links, and fix_approaches fields are all populated from the "
        "class-level static defaults. "
        "Run these tests after any change to find_active_plan or to the "
        "PlanValidationError class definition to confirm the error packet is correct "
        "and the happy path still resolves plans correctly.",
    ]
    _fix_approaches = [
        "1. Check the data before touching the code: Open the plans admin panel and "
        "look up the plan_id from the raised error. Check its current status — if it "
        "is 'inactive' or soft-deleted, confirm with the product team whether the "
        "deactivation was intentional. If the plan was deactivated by mistake, "
        "reactivate it directly in the admin panel and re-run the subscription "
        "creation. In most cases, this is the entire fix — the code is working "
        "correctly and the data needs to be corrected.",

        "2. Trace the plan_id back to its source: Inspect the call chain to see which "
        "layer provided the plan_id. If the plan_id came from a Stripe webhook, use "
        "web fetch to retrieve the Stripe API documentation for "
        "checkout.session.completed events and verify that the price_id in the webhook "
        "maps to an active internal plan. If the plan_id came from the API request "
        "body, trace it back to the frontend or integration partner that sent it to "
        "see whether they are using a stale or deprecated ID.",

        "3. Cross-reference with the plan lifecycle document: Use web fetch to retrieve "
        "docs/billing/plan-lifecycle.md linked in _doc_links. Compare the status "
        "transition rules documented there against the current status of the failing "
        "plan_id. If the plan was deactivated by an automated lifecycle process "
        "(end-of-life, pricing update, compliance removal) and the API layer was not "
        "updated to use the new plan_id, the fix is to update the API layer or the "
        "external integration to use the current active plan_id.",

        "4. Add upstream validation if the source is external: If the plan_id is "
        "coming from an external system (Stripe, a partner API, or user-submitted "
        "input) and is not validated before reaching the billing service, add plan_id "
        "validation at the API boundary in api/subscriptions.route.py. A validation "
        "step that checks whether the plan_id exists and is active before calling the "
        "billing service produces a 400 error with a clear message to the caller "
        "rather than propagating the failure deep into the billing pipeline. After "
        "adding the validation, add a test in tests/billing/test_plans_store.py that "
        "passes an inactive plan_id and verifies that PlanValidationError is raised "
        "with the correct fields.",
    ]

    def __init__(self, *, plan_id: str = ""):
        self.plan_id = plan_id
        self.description = self._description
        self.expected_vs_actual = self._expected_vs_actual
        self.blast_radius = self._blast_radius
        self.doc_links = self._doc_links
        self.test_files = self._test_files
        self.fix_approaches = self._fix_approaches
        rich_message = (
            f"PlanValidationError: plan_id={plan_id} — no active plan found. "
            f"See _description for full context."
        )
        super().__init__(rich_message)

    def to_context_packet(self) -> dict:
        return {
            "error_type": type(self).__name__,
            "plan_id": self.plan_id,
            "description": self.description,
            "expected_vs_actual": self.expected_vs_actual,
            "blast_radius": self.blast_radius,
            "doc_links": self.doc_links,
            "test_files": self.test_files,
            "fix_approaches": self.fix_approaches,
        }
```

```python
# Example 4: Raising PlanValidationError at a data access boundary. The raise
# site passes only plan_id — the single dynamic field that identifies which
# entity triggered the failure. All other diagnostic fields are baked into the
# class definition in Example 3.

def find_active_plan(plan_id: str) -> dict:
    try:
        result = db.query(
            "SELECT * FROM plans WHERE id = %s AND status = 'active'",
            [plan_id],
        )
        if not result:
            raise PlanValidationError(plan_id=plan_id)
        return result
    except PlanValidationError:
        raise
    except Exception as db_error:
        raise PlanValidationError(plan_id=plan_id) from db_error
```
