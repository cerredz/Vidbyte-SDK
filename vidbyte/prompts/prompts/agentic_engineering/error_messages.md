# Goal
Your goal is to produce error messages that are complete self-contained diagnostic units. When an agent catches one of your errors, it should be able to identify the failure mode from the error type alone, understand the specific contract or invariant that was violated, inspect the state that triggered the failure, assess the blast radius of which files are affected, rank the likely causes by probability, and consult remediation patterns before making its first edit. The error object is the agent's primary bootstrap context. It must carry the signal density of a debugger session, a stack trace, a runbook, and a postmortem — all in one structured packet.

# Creating Custom Error Classes
The foundation of agentic error handling is the custom error class. You must define a specialized error class for every distinct failure mode in your codebase — one class per failure mode, never a single generic AppError. Each custom error class carries all the structured fields described in the next section, and every throw site in your code raises one of these classes with the fields fully populated.

Follow this two-step process for every error in your code. First, define the custom error class with a constructor that accepts and stores every field from the anatomy below — error_type, file, line, function, rich_message, violated_invariant, expected_vs_actual, current_state, call_trace, blast_radius, possible_causes, fix_approaches, doc_links, and test_files. Second, throughout your code, wrap every external boundary, pre-condition check, state transition, and integration seam in a try/catch block that raises the appropriate custom error class with all available context filled in at the throw site.

You should have a strong bias toward creating more custom error classes and more error throw sites than a regular developer would. Regular developers treat errors as exceptional and sparse. You treat errors as information-rich checkpoints that make the codebase self-diagnosing for agents. Agents can generate these error classes very easily because the pattern is mechanical and repeatable, and the cost of adding an error is paid once while the benefit accrues on every debugging cycle forever. When in doubt about whether a code path needs a custom error, add one. An over-instrumented codebase wastes a few kilobytes of source text. An under-instrumented codebase wastes agent-hours of context-window exploration on every failure.

# What Goes Inside Each Server-Side Error Message
* error_type — A unique descriptive error class name. Not "Error" or "AppError". Must be grepable by agents and matchable against known failure patterns. Examples: "SubscriptionCreationError", "PlanValidationError", "PaymentMethodDeclinedError". Specialized error classes let an agent recognize a failure mode from the type alone without parsing the message string.
* file, line, function — Exact coordinates of every throw site. Standard but non-negotiable. An error must always carry its own location so the agent never has to guess which file or line produced it.
* rich_message — Prose combining semantic meaning with mechanical detail. Not "Failed to save user" but "Failed to create subscription for user_id=abc123 — plan validation returned null for plan_id=xyz789 at billing/plans.store.ts:45." The message must contain both what happened and the concrete data that demonstrates it.
* violated_invariant — The specific contract, assumption, or precondition that was broken. "Invariant — subscription.plan must be non-null before billing.createSubscription(). This invariant is enforced at the boundary between api/subscriptions.route.ts and billing/subscription-manager.ts." Naming the invariant lets the agent understand whether the fix belongs in this file (we broke our own rule) or the caller (the caller violated the contract).
* expected_vs_actual — Explicit diff of what the code expected versus what it received. "Expected — user.address.zip of type string, non-empty. Actual — null. Caller — api/subscriptions.route.ts:120 (createHandler)." This is the single most actionable field for root-cause diagnosis.
* current_state — Snapshot of relevant local or object state at the crash point. Include the shape of the data that caused the failure, not just its value. "user.state = { id — abc123, email — user@example.com, address — null, subscriptionStatus — none }." The agent needs to see the data that triggered the path, not infer it from surrounding code.
* call_trace — Annotated call chain with role descriptions for each frame, not a raw stack trace. "api/subscriptions.route.ts:createHandler (entry) -> billing/subscription-manager.ts:createSubscription (orchestrator) -> billing/plans.store.ts:findActive (data access) -> FAIL at line 45." Role annotations tell the agent what each frame is responsible for so it can decide where to place the fix.
* blast_radius — References to files likely affected or worth inspecting. "Files likely affected — billing/invoice.generator.ts, users/entitlements.service.ts, events/billing-events.publisher.ts." This prevents the agent from fixing the symptom in one file while missing downstream breakage in related files.
* possible_causes — Ranked hypotheses with rough probability estimates. "70% probability — caller (api/subscriptions.route.ts:120) passed incomplete user object with missing address. 20% — data sync delay between user service and billing service. 10% — schema migration drift in billing database." Ranked hypotheses give the agent a triage order instead of a blank slate.
* fix_approaches — Patterns or strategies that have resolved similar failures before. "Typically fixed by re-fetching the full user object including address from the user service before calling createSubscription. See similar resolution pattern in PR #2841." Fix history turns the error from a mystery into a known recovery path.
* doc_links — References to ADRs, runbooks, or internal documentation. "ADR-014 — Subscription CQRS split. Runbook — docs/runbooks/subscription-failures.md." Links let the agent pull deeper context on demand without stuffing it into every error.
* test_files — Which test file or files cover this execution path. "Tests covering this path — src/billing/__tests__/subscription-manager.test.ts:20-85." The agent knows exactly what to re-run after applying a fix and can verify the fix against the existing test suite before declaring success.

# Placement Strategy
* Wrap every external boundary — DB calls, API calls, file I/O, and message queue operations — with a try/catch that re-throws a custom packed error. Do this at the specific operation level, not just the top-level handler, so the error carries the exact operation that was being attempted.
* Pre-condition assertions become rich errors. Instead of 'if (!user) throw new Error("No user")', write 'if (!user) throw new NoUserError({ context: { sessionId, requestPath }, ... })'. Every invariant check that can fail should fail with a structured packet.
* Every state-transition boundary — any function that changes system state and can fail mid-transition — should capture before/after snapshots in the error if the transition fails partway through.
* Every integration seam — files bridging between subsystems such as auth to billing, API to worker, web to DB — is a natural error-wrapping point because these are where invariants cross boundaries and where failures are most expensive to diagnose.
* Custom error classes should proliferate. One error class per failure mode, not one generic AppError for everything. An agent that catches a SubscriptionCreationError immediately knows the failure domain. An agent that catches an AppError with message "creation failed" knows nothing.

# Things Not to Do
* Do not create frontend or client-side error messages with this level of internal detail. The rich context packet format — with file paths, state snapshots, call traces, and internal file references — is designed for server-side agents operating inside the runtime. Exposing these details to a browser or mobile client leaks implementation internals and creates a security risk.
* Do not fabricate any error message data. Every field in the error packet — violated_invariant, current_state, call_trace, possible_causes, fix_approaches — must reflect the actual runtime conditions at the throw site. Guessing or inventing values misdirects the agent and is worse than omitting the field.
* Do not point the agent in the wrong direction with fix_approaches or possible_causes. If you are not confident about the likely cause or remediation pattern, omit the field or mark the confidence as low. An incorrect hypothesis with high confidence wastes more agent time than no hypothesis at all.
* Do not log sensitive data in error fields that ship to production. PII, authentication tokens, API keys, and session secrets must be redacted from current_state, rich_message, and any other field before the error leaves the server. Use a dedicated redaction layer rather than relying on developers to remember per throw site.
* Do not use a single generic error class for multiple failure modes. An agent catching AppError with message "something went wrong" has zero diagnostic signal. Every distinct failure mode needs its own class so the agent can route its response from the type alone.

# Checklist
* Define a custom error class for every distinct failure mode in the codebase. Each class must have a unique, descriptive, grepable name. This is the single most important practice: an agent that catches SubscriptionCreationError immediately knows the failure domain without parsing anything.
* Every error you throw must include the full set of fields described in the anatomy above whenever the information is available at the throw site. The complete packet turns the error from a dead-end message into a self-contained diagnostic unit that can shortcut multiple rounds of agent exploration.
* Place error throw sites at every external boundary — database queries, API calls, file reads and writes, and message queue operations. These are natural chokepoints where failures surface and where an agent needs maximum context to determine whether the fix is local or upstream.
* Place error throw sites at every pre-condition check and input validation point. When a function rejects its input due to a violated invariant, the error must name the invariant, show the expected and actual values, and capture the caller context so the agent knows whether the fix is in this function or its caller.
* Place error throw sites at every state transition that can fail partway through. If a function modifies system state and a failure occurs mid-transition, the error must include a before-snapshot of the state so the agent can reason about what was partially applied and what needs rollback.
* Place error throw sites at every integration seam between subsystems. When auth calls billing, or the API calls a worker, or the web layer calls the database — every cross-subsystem call should be wrapped in a try/catch that produces a rich error packet naming both sides of the seam.
* Er on the side of too many error classes and throw sites rather than too few. Agents can generate these mechanically, and the cost of adding an error is paid once while the diagnostic benefit accrues on every debugging cycle. An over-instrumented codebase is cheaper than an under-instrumented one.
* Every error must include a call_trace with role-annotated frames — not a raw stack trace but a human-readable chain where each frame carries a label describing its responsibility. Role annotations let the agent decide where to place the fix without interpreting raw stack addresses.
* Every error must include blast_radius references to files likely affected or worth inspecting. This prevents the most expensive failure mode: the agent fixes the symptom in the throw file while missing downstream breakage in related files it never opened.
* Tier your error payload depth between environments. Ship full rich packets in development and test where diagnostic signal is most valuable. In production, truncate or redact sensitive fields. Use a split object pattern — public_context for logs and monitoring, private_context for debug environments — rather than conditioning each field individually.
* Link chained errors by reference rather than accumulating nested payloads inline. When an error propagates through multiple layers and gets re-wrapped, the outermost error should carry the most actionable context, and inner errors should be linked by an error_id field rather than inlined.
* Every error must include a test_files reference pointing to which test suite covers the execution path that threw the error. This tells the agent exactly what to re-run after applying a fix, eliminating the guesswork of test discovery in an unfamiliar codebase.

# Code Examples
These Python snippets demonstrate the full agentic error pattern as described in the sections above. The error class is defined once in a dedicated errors file with all static boilerplate fields baked into the class as defaults — this keeps the class definition heavy and the raise sites light. Each raise site only passes the dynamic fields that change per invocation, and every raise cross-references the anatomy in the "What Goes Inside" section so the agent receiving the error can trace every field back to its documented purpose.

```python
# Example 1: Defining a custom error class with all static fields baked in.
# This class lives in a dedicated errors file (e.g., errors/billing.py) and
# serves as the single definition for this failure mode. Static fields —
# file, violated_invariant, expected_vs_actual, blast_radius, doc_links,
# test_files, and common fix_approaches — are set as class-level defaults
# because they are the same for every throw of this error. Dynamic fields
# — rich_message, current_state, call_trace, possible_causes — are passed
# at the raise site because they vary per invocation.
# See the "What Goes Inside Each Server-Side Error Message" section above
# for the full description of each field and what information it should carry.

class BillingSubscriptionCreationError(Exception):
    # Static defaults that apply to every throw of this error. These fields
    # describe the failure mode in general and do not change per invocation.
    _file = "billing/subscription-manager.py"
    _function = "create_subscription"
    _violated_invariant = (
        "Invariant: user.address must be non-null with a valid zip code "
        "before billing.create_subscription(). This invariant is enforced at "
        "the boundary between api/subscriptions.route.py and "
        "billing/subscription-manager.py."
    )
    _expected_vs_actual = (
        "Expected: user.address.zip of type str, non-empty, with a valid "
        "postal code format. The address must be verified by the address "
        "validation service before reaching this function."
    )
    _blast_radius = [
        "billing/plans.store.py — plan lookup may fail downstream if user is incomplete",
        "billing/invoice.generator.py — invoice requires valid billing address",
        "users/entitlements.service.py — entitlement grant depends on subscription creation",
        "events/billing-events.publisher.py — subscription.created event will not fire",
        "api/subscriptions.route.py — the caller that passed the incomplete user object",
    ]
    _doc_links = [
        "ADR-014: Subscription CQRS split — explains why subscription creation "
        "is a transactional boundary",
        "docs/runbooks/subscription-failures.md — runbook for diagnosing "
        "billing failures including missing address errors",
    ]
    _test_files = [
        "tests/billing/test_subscription_manager.py:20-85 — covers the "
        "create_subscription path including address validation",
    ]
    _common_fix_approaches = [
        "Re-fetch the full user object including address from the user service "
        "before calling create_subscription. The user object passed by the API "
        "layer may be a partial projection that omits the address field. See "
        "similar resolution pattern in PR #2841.",
        "Add an address validation step in the API handler "
        "(api/subscriptions.route.py) before delegating to the billing service. "
        "This catches the missing address earlier in the call chain and produces "
        "a more specific error at the correct boundary.",
    ]

    def __init__(self, *, line: int, rich_message: str, current_state: dict,
                 call_trace: str, possible_causes: list[str] | None = None):
        self.file = self._file
        self.line = line
        self.function = self._function
        self.rich_message = rich_message
        self.violated_invariant = self._violated_invariant
        self.expected_vs_actual = self._expected_vs_actual
        self.current_state = current_state
        self.call_trace = call_trace
        self.blast_radius = self._blast_radius
        self.possible_causes = possible_causes or []
        self.fix_approaches = self._common_fix_approaches
        self.doc_links = self._doc_links
        self.test_files = self._test_files
        super().__init__(rich_message)

    def to_context_packet(self) -> dict:
        # Serializes all fields into a structured dict for logging,
        # monitoring, or agent consumption. An agent that catches this
        # error can call to_context_packet() to get the full diagnostic
        # payload described in the "What Goes Inside" section above.
        return {
            "error_type": type(self).__name__,
            "file": self.file,
            "line": self.line,
            "function": self.function,
            "rich_message": self.rich_message,
            "violated_invariant": self.violated_invariant,
            "expected_vs_actual": self.expected_vs_actual,
            "current_state": self.current_state,
            "call_trace": self.call_trace,
            "blast_radius": self.blast_radius,
            "possible_causes": self.possible_causes,
            "fix_approaches": self.fix_approaches,
            "doc_links": self.doc_links,
            "test_files": self.test_files,
        }
```

```python
# Example 2: Raising the custom error at a pre-condition check inside a
# service function. Note how short the raise site is compared to the
# class definition — only the dynamic fields are passed. The static fields
# (violated_invariant, expected_vs_actual, blast_radius, doc_links,
# test_files, fix_approaches) are all inherited from the class defaults.
# See the "What Goes Inside Each Server-Side Error Message" section above
# for the field anatomy, and "Creating Custom Error Classes" above for
# the process of defining and raising these errors.

def create_subscription(plan_id: str, user: dict, payment_method_id: str) -> dict:
    # Pre-condition: the user must have a valid address before billing.
    # The BillingSubscriptionCreationError class carries the static invariant
    # description, expected vs actual contract, blast radius, documentation
    # links, test file references, and common fix approaches. The raise site
    # only provides the per-invocation details — what line failed, what the
    # current state looked like, what the call trace was, and what specific
    # causes are most likely for this particular failure instance.
    if not user.get("address") or not user["address"].get("zip"):
        raise BillingSubscriptionCreationError(
            line=45,
            rich_message=(
                f"Failed to create subscription for user_id={user.get('id')} — "
                f"user address is missing or incomplete. The user record passed "
                f"to create_subscription has address={user.get('address')}, which "
                f"is null or missing the required zip code field. Cannot proceed "
                f"with billing because a valid billing address is required to "
                f"generate invoices and process payments. This failure occurred "
                f"before any database writes or external calls were made, so no "
                f"state was modified and no cleanup is needed."
            ),
            current_state={
                "user_id": user.get("id"),
                "user_email": user.get("email"),
                "user_address": user.get("address"),
                "user_subscription_status": user.get("subscription_status"),
                "plan_id": plan_id,
                "payment_method_id": payment_method_id,
                "request_path": "api/subscriptions.route.py:120",
                "request_method": "POST",
            },
            call_trace=(
                "api/subscriptions.route.py:create_handler (entry) -> "
                "billing/subscription-manager.py:create_subscription (orchestrator) -> "
                "FAIL at pre-condition check for user address validation (line 45). "
                "The API handler passed a user object without a verified address. "
                "The billing service rejected the request before any state mutation."
            ),
            possible_causes=[
                "70% probability: the API handler (api/subscriptions.route.py) "
                "queried a partial user projection that did not include the "
                "address field. The user service query should be updated to "
                "include the address relation.",
                "20% probability: data sync delay between the user service and "
                "the billing service. The user was created in the user service "
                "and the address was set, but the replication lag meant the "
                "billing service saw a stale record without an address.",
                "10% probability: the user record is from the pre-2024 migration "
                "era before address was a required field on user creation. These "
                "legacy users may legitimately lack an address and need to be "
                "prompted to add one before subscribing.",
            ],
        )
```

```python
# Example 3: Wrapping an external boundary (database call) with a try/catch
# that produces a rich error packet. The PlanValidationError class is defined
# in its own errors file (errors/billing.py) with static defaults for file,
# violated_invariant, expected_vs_actual, blast_radius, doc_links, test_files,
# and common fix_approaches. The raise site only passes dynamic fields.
# See the "What Goes Inside Each Server-Side Error Message" and "Placement
# Strategy" sections above for guidance on where to place these error sites.

# -- In errors/billing.py: the static error class definition --
class PlanValidationError(Exception):
    _file = "billing/plans.store.py"
    _function = "find_active_plan"
    _violated_invariant = (
        "Invariant: Every subscription must reference an active plan in the "
        "plans table. The plan_id passed by the caller must resolve to a plan "
        "with status='active' and must not be soft-deleted. Plan validation "
        "happens at the data access boundary between the billing orchestration "
        "layer and the plans data store."
    )
    _expected_vs_actual = (
        "Expected: a plans table row with the given plan_id and status='active'. "
        "The row must have non-null price, billing_interval, and feature_flags "
        "columns. Actual: the query returned no rows. The plan either does not "
        "exist, has been deactivated (status changed to 'inactive'), or was "
        "soft-deleted."
    )
    _blast_radius = [
        "billing/subscription-manager.py — subscription creation depends on "
        "plan validation and cannot proceed without a valid plan",
        "billing/invoice.generator.py — invoice generation requires plan "
        "metadata (price, interval) that cannot be loaded",
        "api/subscriptions.route.py — the caller that provided the invalid plan_id",
        "webhooks/stripe.handler.ts — if this was triggered by a Stripe webhook, "
        "the plan_id may have come from a stale Stripe product mapping",
    ]
    _doc_links = [
        "ADR-014: Subscription CQRS split — explains why plan validation "
        "is a distinct step in the write pipeline",
        "docs/billing/plan-lifecycle.md — documents how plans are created, "
        "activated, deactivated, and archived",
    ]
    _test_files = [
        "tests/billing/test_plans_store.py:30-60 — covers find_active_plan "
        "including the case where no active plan is found",
    ]
    _common_fix_approaches = [
        "Verify the plan_id against the plans table admin panel before "
        "investigating the code. If the plan was deactivated by an admin, "
        "the fix is to reactivate it, not to change the validation logic.",
        "If plan_id is coming from an external system (Stripe, a partner API), "
        "check the plan ID mapping in the external integration layer — the "
        "external system may be sending an ID format that does not match our "
        "internal plan catalog.",
        "Add plan_id validation at the API layer (api/subscriptions.route.py) "
        "before entering the billing service so the error is caught earlier "
        "with a more detailed message about which plan was requested.",
    ]

    def __init__(self, *, line: int, rich_message: str, current_state: dict,
                 call_trace: str, possible_causes: list[str] | None = None):
        self.file = self._file
        self.line = line
        self.function = self._function
        self.rich_message = rich_message
        self.violated_invariant = self._violated_invariant
        self.expected_vs_actual = self._expected_vs_actual
        self.current_state = current_state
        self.call_trace = call_trace
        self.blast_radius = self._blast_radius
        self.possible_causes = possible_causes or []
        self.fix_approaches = self._common_fix_approaches
        self.doc_links = self._doc_links
        self.test_files = self._test_files
        super().__init__(rich_message)

    def to_context_packet(self) -> dict:
        return {
            "error_type": type(self).__name__,
            "file": self.file,
            "line": self.line,
            "function": self.function,
            "rich_message": self.rich_message,
            "violated_invariant": self.violated_invariant,
            "expected_vs_actual": self.expected_vs_actual,
            "current_state": self.current_state,
            "call_trace": self.call_trace,
            "blast_radius": self.blast_radius,
            "possible_causes": self.possible_causes,
            "fix_approaches": self.fix_approaches,
            "doc_links": self.doc_links,
            "test_files": self.test_files,
        }

# -- In billing/plans.store.py: raising the error at the data access boundary --

def find_active_plan(plan_id: str) -> dict:
    try:
        result = db.query(
            "SELECT * FROM plans WHERE id = %s AND status = 'active'",
            [plan_id],
        )
        if not result:
            raise PlanValidationError(
                line=52,
                rich_message=(
                    f"Plan validation failed at billing/plans.store.py:52 — "
                    f"no active plan found for plan_id={plan_id}. The query "
                    f"'SELECT * FROM plans WHERE id={plan_id} AND status=active' "
                    f"returned zero rows. This means the plan either does not "
                    f"exist in the database, has been deactivated (status changed "
                    f"from 'active' to 'inactive' by an admin or an automated "
                    f"lifecycle process), or was soft-deleted. The subscription "
                    f"creation pipeline cannot proceed without a valid active "
                    f"plan because plan metadata (price, billing interval, "
                    f"feature flags) is required for invoice generation and "
                    f"entitlement computation."
                ),
                current_state={
                    "queried_plan_id": plan_id,
                    "query": "SELECT * FROM plans WHERE id = %s AND status = 'active'",
                    "query_params": [plan_id],
                    "result_row_count": 0,
                    "caller": "billing/subscription-manager.py:45 (create_subscription)",
                },
                call_trace=(
                    "api/subscriptions.route.py:create_handler (entry) -> "
                    "billing/subscription-manager.py:create_subscription (orchestrator) -> "
                    "billing/plans.store.py:find_active_plan (data access) -> "
                    "FAIL at line 52 (query returned empty result set). "
                    "The caller passed plan_id={plan_id} which did not match "
                    "any active plan in the database."
                ),
                possible_causes=[
                    "50% probability: the plan_id is mistyped or references a "
                    "plan that was deactivated or deleted by an admin. Check the "
                    "plans admin panel to see the current status of this plan_id.",
                    "30% probability: the plan was deactivated via an automated "
                    "lifecycle process (plan end-of-life, pricing update, or "
                    "compliance removal) but the API or webhook layer was not "
                    "updated to stop sending this plan_id.",
                    "15% probability: database replication lag — the plan exists "
                    "and is active on the primary database but the read replica "
                    "handling this query has not yet received the latest state.",
                    "5% probability: a database migration altered the plans table "
                    "schema and the status column now uses a different enum value "
                    "than 'active', causing the query to miss the row even though "
                    "the plan is valid in the new schema.",
                ],
            )
        return result
    except PlanValidationError:
        raise
    except Exception as db_error:
        raise PlanValidationError(
            line=52,
            rich_message=(
                f"Database error while querying active plan for plan_id={plan_id} "
                f"at billing/plans.store.py:52. The database raised "
                f"{type(db_error).__name__}: {db_error}. This is a connectivity "
                f"or infrastructure failure, not a data validation failure — the "
                f"query could not be executed at all. The plan_id={plan_id} may "
                f"or may not be valid; we cannot determine that because we never "
                f"reached the database. The subscription creation pipeline is "
                f"blocked until database connectivity is restored."
            ),
            current_state={
                "plan_id": plan_id,
                "db_error_message": str(db_error),
                "db_error_type": type(db_error).__name__,
                "query": "SELECT * FROM plans WHERE id = %s AND status = 'active'",
                "caller": "billing/subscription-manager.py:45 (create_subscription)",
            },
            call_trace=(
                "api/subscriptions.route.py:create_handler (entry) -> "
                "billing/subscription-manager.py:create_subscription (orchestrator) -> "
                "billing/plans.store.py:find_active_plan (data access) -> "
                "FAIL at line 52 (database exception — query could not execute). "
                "The database connection was established but the query failed "
                "with a {db_error_type} error."
            ),
            possible_causes=[
                "40% probability: database connection pool is exhausted. The "
                "application has reached its maximum number of concurrent "
                "database connections and this request could not acquire one "
                "within the connection timeout.",
                "30% probability: transient network interruption between the "
                "application server and the database. The connection was "
                "established but was dropped mid-query.",
                "20% probability: database server is under heavy load and "
                "the query timed out waiting for a lock or resource.",
                "10% probability: a recent database migration changed the "
                "plans table schema in a way that is incompatible with this "
                "query (e.g., column renamed, type changed). The query syntax "
                "is valid but the schema no longer matches.",
            ],
        )
```
