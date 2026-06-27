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

# Error Chaining
When errors propagate and get re-wrapped at higher layers, the outermost error should carry the most actionable context. Inner errors should be linked by reference — an error_id or preceding_error field — rather than accumulated inline. Accumulation preserves debugging info but explodes verbosity. Linking by reference keeps each layer's packet compact while preserving the full chain for debug environments.

# Sensitive Data and Tiering
Full error packets should ship in development and test environments where maximum diagnostic signal is valuable and data sensitivity is low. In production, truncate or redact fields that may contain PII, tokens, or secrets — particularly current_state and input. Consider splitting the error object into a public_context block safe for logs and monitoring, and a private_context block restricted to debug environments. For high-throughput services, sample rich error packets at a configurable rate rather than paying the storage cost on every occurrence.

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
These Python snippets demonstrate the full pattern: defining a custom error class with all fields, raising it at a throw site with context populated, and wrapping an external boundary with the pattern.

```python
# Example 1: Defining a custom error class with the complete field anatomy.
# This class serves as the template for every failure mode in the codebase.
# Every field is optional in the constructor — populate only what is available.
# The error_type is the class name itself, automatically captured.

class SubscriptionCreationError(Exception):
    def __init__(
        self,
        *,
        file: str = "",
        line: int = 0,
        function: str = "",
        rich_message: str = "",
        violated_invariant: str = "",
        expected_vs_actual: str = "",
        current_state: dict | None = None,
        call_trace: str = "",
        blast_radius: list[str] | None = None,
        possible_causes: list[str] | None = None,
        fix_approaches: list[str] | None = None,
        doc_links: list[str] | None = None,
        test_files: list[str] | None = None,
    ):
        self.file = file
        self.line = line
        self.function = function
        self.rich_message = rich_message
        self.violated_invariant = violated_invariant
        self.expected_vs_actual = expected_vs_actual
        self.current_state = current_state or {}
        self.call_trace = call_trace
        self.blast_radius = blast_radius or []
        self.possible_causes = possible_causes or []
        self.fix_approaches = fix_approaches or []
        self.doc_links = doc_links or []
        self.test_files = test_files or []
        # Build the exception message from the most critical fields so
        # that even a raw print or log line carries diagnostic signal.
        super().__init__(rich_message)

    def to_context_packet(self) -> dict:
        # Serializes all fields into a structured dict for logging,
        # monitoring, or agent consumption.
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
# Example 2: Raising the custom error at a pre-condition check inside
# a service function. Note how every field available at the throw site
# is populated — the agent receiving this error can see the user state,
# the violated invariant, the expected vs actual values, and the call
# trace with role annotations.

def create_subscription(plan_id: str, user: dict, payment_method_id: str) -> dict:
    # Pre-condition: the user must have a valid address before billing.
    if not user.get("address") or not user["address"].get("zip"):
        raise SubscriptionCreationError(
            file="billing/subscription-manager.py",
            line=45,
            function="create_subscription",
            rich_message=(
                f"Failed to create subscription for user_id={user.get('id')} — "
                f"user address is missing or incomplete. Cannot proceed with billing."
            ),
            violated_invariant=(
                "Invariant: user.address must be non-null with a valid zip code "
                "before billing.create_subscription(). This invariant is enforced "
                "at the boundary between api/subscriptions.route.py and "
                "billing/subscription-manager.py."
            ),
            expected_vs_actual=(
                "Expected: user.address.zip of type str, non-empty. "
                f"Actual: {user.get('address')}. "
                "Caller: api/subscriptions.route.py:120 (create_handler)."
            ),
            current_state={
                "user": {
                    "id": user.get("id"),
                    "email": user.get("email"),
                    "address": user.get("address"),
                    "subscription_status": user.get("subscription_status"),
                },
                "plan_id": plan_id,
                "payment_method_id": payment_method_id,
            },
            call_trace=(
                "api/subscriptions.route.py:create_handler (entry) -> "
                "billing/subscription-manager.py:create_subscription (orchestrator) -> "
                "FAIL at pre-condition check (line 45)."
            ),
            blast_radius=[
                "billing/plans.store.py",
                "billing/invoice.generator.py",
                "users/entitlements.service.py",
            ],
            possible_causes=[
                "70% probability: caller (api/subscriptions.route.py:120) passed "
                "an incomplete user object with address missing.",
                "20% probability: data sync delay between user service and billing "
                "service — user was created but address not yet propagated.",
                "10% probability: user record is from pre-migration era before "
                "address was a required field.",
            ],
            fix_approaches=[
                "Typically fixed by re-fetching the full user object including "
                "address from the user service before calling create_subscription. "
                "See similar resolution pattern in PR #2841.",
            ],
            doc_links=[
                "ADR-014: Subscription CQRS split",
                "docs/runbooks/subscription-failures.md",
            ],
            test_files=[
                "tests/billing/test_subscription_manager.py:20-85",
            ],
        )
```

```python
# Example 3: Wrapping an external boundary (database call) with a try/catch
# that produces a rich error packet. The database error is caught, and the
# agentic error is raised with all available context including the query
# that was attempted, the parameters, and the raw database error.

def find_active_plan(plan_id: str) -> dict:
    try:
        result = db.query(
            "SELECT * FROM plans WHERE id = %s AND status = 'active'",
            [plan_id],
        )
        if not result:
            raise PlanValidationError(
                file="billing/plans.store.py",
                line=52,
                function="find_active_plan",
                rich_message=(
                    f"Plan validation failed: no active plan found for "
                    f"plan_id={plan_id}. The plan either does not exist or "
                    f"has been deactivated."
                ),
                violated_invariant=(
                    "Invariant: Every subscription must reference an active plan. "
                    "The plan_id passed by the caller must resolve to a plan with "
                    "status='active' in the plans table."
                ),
                expected_vs_actual=(
                    f"Expected: plan with id={plan_id} and status='active'. "
                    f"Actual: no matching row returned from plans table. "
                    "Caller: billing/subscription-manager.py:45 (create_subscription)."
                ),
                current_state={
                    "plan_id": plan_id,
                    "query_result": None,
                },
                call_trace=(
                    "api/subscriptions.route.py:create_handler (entry) -> "
                    "billing/subscription-manager.py:create_subscription (orchestrator) -> "
                    "billing/plans.store.py:find_active_plan (data access) -> "
                    "FAIL at line 52 (query returned empty)."
                ),
                blast_radius=[
                    "billing/subscription-manager.py",
                    "billing/invoice.generator.py",
                    "api/subscriptions.route.py",
                ],
                possible_causes=[
                    "60% probability: plan_id is mistyped or references "
                    "a plan that was deleted.",
                    "30% probability: plan was deactivated (status changed "
                    "to 'inactive') but subscription creation was still attempted.",
                    "10% probability: database replication lag — plan exists "
                    "on primary but not yet visible on read replica.",
                ],
                fix_approaches=[
                    "Verify plan_id against the plans table before calling "
                    "create_subscription. Validate that status='active' at the "
                    "API layer before entering the billing service.",
                ],
                doc_links=[
                    "ADR-014: Subscription CQRS split",
                ],
                test_files=[
                    "tests/billing/test_plans_store.py:30-60",
                ],
            )
        return result
    except PlanValidationError:
        raise
    except Exception as db_error:
        raise PlanValidationError(
            file="billing/plans.store.py",
            line=52,
            function="find_active_plan",
            rich_message=(
                f"Database error while querying active plan for plan_id={plan_id}: "
                f"{db_error}. The query may have failed due to connection issues, "
                f"timeout, or schema mismatch."
            ),
            violated_invariant=(
                "Invariant: Plan queries must succeed. Database connectivity "
                "is required for all subscription operations."
            ),
            expected_vs_actual=(
                f"Expected: successful database query for plan_id={plan_id}. "
                f"Actual: database raised {type(db_error).__name__}: {db_error}."
            ),
            current_state={
                "plan_id": plan_id,
                "db_error": str(db_error),
                "db_error_type": type(db_error).__name__,
            },
            call_trace=(
                "api/subscriptions.route.py:create_handler (entry) -> "
                "billing/subscription-manager.py:create_subscription (orchestrator) -> "
                "billing/plans.store.py:find_active_plan (data access) -> "
                "FAIL at line 52 (database exception)."
            ),
            blast_radius=[
                "billing/subscription-manager.py",
                "api/subscriptions.route.py",
            ],
            possible_causes=[
                "50% probability: database connection pool exhausted or "
                "connection timed out.",
                "30% probability: schema mismatch between code and database "
                "— column name or type changed in migration.",
                "20% probability: database server under load or experiencing "
                "a transient failure.",
            ],
            fix_approaches=[
                "Check database connectivity and connection pool health. "
                "Verify that the plans table schema matches the query. "
                "If transient, the caller should retry with exponential backoff.",
            ],
            doc_links=[
                "docs/runbooks/database-connectivity.md",
            ],
            test_files=[
                "tests/billing/test_plans_store.py:30-60",
            ],
        )
```
