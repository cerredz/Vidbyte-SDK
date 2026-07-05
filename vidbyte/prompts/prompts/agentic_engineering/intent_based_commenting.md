# Description
You are going to write agent-native code, and the principle this file introduces is intent-based commenting. Intent-based commenting means putting the reason a piece of important code exists directly beside the implementation that carries that reason. It is not a decorative comment style, a formal docblock schema, or a replacement for readable code. It is a way to preserve the why and the domain meaning of business-critical logic at the exact point where an agent will read, rewrite, and risk changing that logic.

Agent-native code changes often. A function may be refactored, split, renamed, moved, or regenerated many times by different agents. The implementation can change safely when the durable meaning is still visible: what business rule must remain true, why a non-obvious guard exists, what customer or money path depends on this behavior, and what mistake a future rewrite must not repeat. Intent-based commenting keeps that meaning close enough to the code that it is read as part of the code, not as optional background material in a distant design document.

This skill file teaches you when to write intent comments and how to write them while coding. The shape is deliberately simple: write `@intent` followed by a short name, then use a multiline comment to clearly explain the intent. Bias toward enough detail for a future agent to understand the business rule, the reason it exists, the failure mode it prevents, and the kinds of rewrites that would be dangerous. Many useful intent comments are ten to fifteen lines or longer, and some should be forty lines because the function coordinates several domain layers and carries expensive business constraints. Length is not the goal. Capturing the actual intent is the goal.

# Intent
The intent of intent-based commenting is to preserve the why and the meaning behind important code, not just the current implementation. Source code can show the steps a function takes, but it often cannot show the business reason those steps exist, the domain invariant they protect, or the production lesson that made the current shape necessary.

The why should live very close to the implementation. Put the intent directly above the function, method, class, or domain operation whose behavior depends on it, with no blank line separating the comment from the definition. A future agent should not need to search a design doc or infer the rule from tests before editing the code.

Very important business and domain logic should carry its intent beside it. If a function controls billing, permissions, customer state, compliance, fulfillment, idempotency, recovery, or any other behavior where a plausible rewrite could preserve the surface behavior while losing the business meaning, write the intent down before the implementation.

# What Counts as Business or Domain Logic
Business or domain logic is code that expresses a rule about how the product, customer, money, data, or operational workflow is supposed to behave. It is not just "code in the backend." It is the part of the system where the company-specific meaning lives: who is allowed to do something, when money moves, what state transitions are legal, what must be recorded, and what cannot be lost during a rewrite.

Intent comments are useful when the code needs more than an implementation description. Use them when the important part is the meaning behind the behavior.

Examples of business or domain logic that should usually get an intent comment:

1. A subscription renewal function that decides whether to charge now, defer, or cancel access.
2. A refund function that must never refund more than the original captured amount.
3. A billing proration calculation where a one-cent rounding decision affects invoices.
4. A permission check that determines whether an admin, owner, or workspace member can perform a destructive action.
5. A state transition that moves an order from pending to fulfilled and must not skip fraud review.
6. A retry handler that must be idempotent so webhook replays do not create duplicate records.
7. A compliance filter that removes PII before data leaves a service boundary.
8. A quota or entitlement calculation that decides which features a customer can access.
9. A concurrency-sensitive update that must keep two records consistent under simultaneous requests.
10. A fraud, abuse, or risk decision that intentionally blocks an action even when the inputs look valid.
11. A migration repair path that exists because legacy records violate the normal data shape.
12. A customer notification rule where sending twice is harmful or sending late has business consequences.
13. A reconciliation process that makes internal ledger state match an external provider.
14. A ranking, assignment, or routing decision that encodes product policy rather than generic sorting.
15. A hard-won guard that looks unnecessary until you know the incident, support escalation, or customer failure it prevents.

Code that usually does not need an intent comment includes simple CRUD plumbing, route registration, dependency injection setup, formatting helpers, one-to-one data mappers, and private helpers whose meaning is already fully explained by the public operation that calls them.

# Intent Comment Structure
Intent comments use a simple structure:

```python
# @intent short-name-for-the-rule
# Explain the business or domain meaning in plain language before the code.
# Say what rule must survive a rewrite, who or what depends on that rule, and
# why this function is the right place to enforce it.
#
# Name the load-bearing implementation details that look like ordinary code but
# actually protect the rule. Call out any ordering, guard, idempotency key,
# rounding behavior, state transition, audit record, or compliance boundary that
# a future agent might otherwise simplify away.
#
# Describe at least one bad rewrite that would still look reasonable in a code
# review. Include the production consequence, such as duplicate money movement,
# unauthorized access, missing audit history, customer-visible drift, or data
# leaving the service boundary with the wrong shape.
def important_domain_operation(...):
    ...
```

The `@intent` line names the intent. Keep the name short, searchable, and specific: `refund-ceiling`, `workspace-owner-delete-guard`, `subscription-renewal-idempotency`, `pii-redaction-before-export`. The lines after it are ordinary comment lines. There is no mandatory field list. Do not invent empty sections just to satisfy a template. The useful part is the explanation.

The explanation should answer the questions a future agent needs before rewriting the code:

* What important business or domain meaning does this code protect?
* Why does that meaning matter?
* What implementation-looking detail is actually load-bearing?
* What would be a bad rewrite that still looks reasonable?
* What tests, incidents, support cases, policies, or product rules should the agent keep in mind?

Use as many lines as the intent needs. Even a narrow guard should usually explain the rule, the bypass paths, and the dangerous rewrites:

```python
# @intent refund-ceiling
# A refund may never exceed the amount captured for the original payment. This
# is a money movement invariant, not a UI validation detail, so it belongs in
# the write-side billing service even when callers perform their own validation.
#
# API handlers, admin tools, provider retry workers, and manual recovery scripts
# can all reach the refund service through different paths. If this check only
# lives at the edge, a future integration can bypass it while still appearing to
# use the normal refund flow.
#
# Keep the comparison against captured funds, not authorized funds, displayed
# invoice totals, or a caller-supplied balance. Those values can be stale or
# represent money that never actually settled. A rewrite that validates against
# the wrong amount can create over-refunds that finance cannot reconcile.
def validate_refund_amount(payment: Payment, requested_cents: int) -> None:
    ...
```

A complex orchestrator might need a much longer comment because several domain layers depend on the same rule:

```python
# @intent subscription-renewal-atomicity
# Renewal is the write-side boundary for subscription revenue. It coordinates
# plan lookup, invoice creation, entitlement extension, event publishing, and
# audit logging as one domain operation.
#
# The important rule is not the exact order of helper calls below; those helpers
# can be renamed or split. The important rule is that a renewal is either fully
# recorded as a paid, entitlement-granting renewal or it is not recorded at all.
# A rewrite that creates an invoice but fails to extend entitlements, or extends
# entitlements before invoice persistence, creates customer-visible drift.
#
# Keep the public method as an orchestrator and keep low-level work in private
# leaf methods. The agentic engineering function-design principle applies here:
# the public method should read like the table of contents for the renewal, and
# each private method should do one thing at one level of abstraction.
def renew_subscription(...):
    ...
```

# How to Write Good Intent Comments
Start by naming the durable rule. The first sentence after `@intent` should make the intent clear without requiring the reader to inspect the function body. "This rejects refunds that exceed the captured charge" is useful. "This checks if requested_cents is too high" is implementation narration.

Write the why, not just the what. If the code has a guard, ordering, retry rule, or unusual branch because something broke before, say that. "Provider webhooks are replayed during outage recovery, so this function must be safe to call multiple times with the same provider_event_id" gives an agent a reason not to remove the lookup.

Keep the comment beside the code it governs. A module-level overview can explain a whole file, but an intent comment should sit directly above the function, method, class, or domain operation where the rule is enforced.

Prefer concrete business language. Name the domain object and consequence: subscription, refund, invoice, workspace owner, entitlement, fulfillment, audit record, support escalation. Generic phrases such as "handles edge cases" and "keeps things consistent" do not carry enough meaning to survive a rewrite.

Separate intent from mechanics. It is fine to mention a mechanism when the mechanism matters, but explain why it matters. "The advisory lock keeps duplicate webhook retries from creating two renewals" is intent. "Acquire lock then query renewals table" is narration.

Make the comment useful at different lengths, but bias toward richer context when the code carries business risk. Ten to fifteen lines is often a better example target than two or three lines because it gives room for the rule, the why, the failure mode, and the rewrite warning. A long comment is good when the operation spans multiple domain layers and future agents need more context. A long comment full of step-by-step narration is bad. A short comment that hides the real business consequence is also bad.

# Things Not to Do
* Do not write comments that merely narrate the implementation. "Loop over invoices and sum totals" will rot as soon as the implementation changes. Explain the business rule the loop serves.
* Do not use a rigid field template when the fields are empty or forced. The structure is `@intent <short name>` plus a clear multiline explanation, not a form to fill out.
* Do not tag every function. Intent comments lose signal when CRUD plumbing, route wiring, and obvious mappers all carry `@intent` blocks.
* Do not put intent far away from the code. A design doc can provide background, but the intent that must guide a rewrite belongs directly above the operation being rewritten.
* Do not write vague intent. "Important billing logic" does not tell an agent what to preserve. "Refunds must never exceed the captured charge" does.
* Do not hide hard-won context. If a guard exists because of an incident, a support case, a provider quirk, or a compliance rule, say so in the comment.
* Do not describe temporary implementation choices as permanent intent. If a lock, query, or branch is just today's mechanism, explain the invariant it protects instead.
* Do not let the comment contradict the code after a rewrite. If you change the behavior, reread the intent and update it in the same edit.
* Do not use intent comments to compensate for a bad function. If the function does too many things, split it first and put the intent on the meaningful domain operation.
* Do not write an intent comment on a private helper when the helper only exists as part of one public operation and has no standalone domain meaning.

# Checklist
* Before writing important business or domain code, ask what meaning a future agent must preserve and write that intent before the implementation.
* Put the `@intent <short name>` block directly above the function, method, class, or domain operation it governs.
* Choose a short name that is searchable and specific to the rule.
* Explain the business rule, domain invariant, customer consequence, money consequence, compliance requirement, or hard-won lesson in plain language.
* Mention the "why" when the code has a non-obvious shape, guard, ordering, retry path, or failure behavior.
* Keep the comment at the right length: detailed enough to preserve the rule, with ten to fifteen lines as a normal example target and longer blocks when multiple domain layers or expensive consequences are involved.
* Write the comment at the level of meaning, not at the level of variable names, loops, branches, or helper call order.
* Keep public orchestrators readable and small when intent comments describe multi-layer flows; use private leaf methods for the low-level work.
* After changing code with an existing intent comment, reread the comment and update it if the behavior or consequence changed.
* Before opening a pull request, scan new or modified business/domain functions and confirm the important ones carry clear intent comments.

# Code Examples

## Example 1: Python intent comment for a money invariant

```python
# @intent refund-ceiling
# A refund may never exceed the amount captured for the original payment. This
# is a money movement invariant, not a convenience validation, so the check must
# live at the write-side billing boundary where refunds are actually created.
#
# Edge validation is still useful, but it is not authoritative. Customer support
# tools, provider retry handlers, bulk correction scripts, and future internal
# workflows can all call this service without going through the public API path.
#
# Compare against captured_cents because that is the settled amount the payment
# provider confirms we received. Do not compare against authorized_cents, invoice
# subtotal, displayed balance, or a caller-provided value; each can be larger
# than the money that actually settled.
#
# A rewrite that moves this check to the controller or trusts caller validation
# will pass ordinary unit tests but can create over-refunds during manual support
# actions. That creates unrecoverable revenue loss and breaks finance
# reconciliation against the provider ledger.
def validate_refund_amount(payment: Payment, requested_cents: int) -> None:
    if requested_cents > payment.captured_cents:
        raise RefundExceedsCaptureError(payment_id=payment.id)
```

## Example 2: Medium Python intent comment for webhook idempotency

```python
# @intent provider-webhook-idempotency
# Provider webhooks are replayed during outage recovery, provider backfills, and
# delayed network delivery. The same real-world payment event can therefore
# reach us more than once, sometimes minutes or hours apart, with identical
# provider_event_id values.
#
# The provider_event_id is the durable idempotency key. Local database ids,
# arrival timestamps, request ids, and retry counters describe our receipt of the
# webhook, not the provider's underlying event. Those values change on replay and
# must not decide whether this is a new payment fact.
#
# Returning the existing record is intentional. Downstream email, ledger, and
# analytics consumers treat insertion as the signal that a new payment event was
# accepted. Re-inserting during a replay storm can duplicate receipts, duplicate
# revenue records, and trigger support escalations for customers who were only
# charged once.
#
# Do not replace this lookup with a blind insert plus later cleanup. Cleanup is
# too late for side effects that fire from the insert path, and happy-path tests
# usually do not model provider replay behavior.
def record_payment_webhook(event: ProviderWebhookEvent) -> PaymentWebhookRecord:
    existing = webhook_store.find_by_provider_event_id(event.provider_event_id)
    if existing:
        return existing
    return webhook_store.insert(event)
```

## Example 3: Long Python orchestrator with intent comments throughout

```python
class SubscriptionRenewalOrchestrator:
    def __init__(
        self,
        plans: PlanCatalog,
        invoices: InvoiceService,
        entitlements: EntitlementService,
        events: BillingEventPublisher,
        audit_log: AuditLog,
    ) -> None:
        self._plans = plans
        self._invoices = invoices
        self._entitlements = entitlements
        self._events = events
        self._audit_log = audit_log

    # @intent subscription-renewal-atomicity
    # Renewal is the write-side boundary for subscription revenue. It coordinates
    # plan validation, invoice creation, entitlement extension, event emission,
    # and audit logging as one customer-visible domain operation.
    #
    # The business rule is atomicity at the product level: the customer is either
    # fully renewed, with paid access and traceable financial records, or not
    # renewed. Partial success is worse than a clean failure because it creates
    # contradictory truth across billing, entitlements, support, and analytics.
    #
    # A renewal that creates an invoice without extending entitlements causes a
    # paid customer to lose access. A renewal that extends entitlements without a
    # settled invoice gives away paid features. A renewal that emits the event
    # before the audit record exists leaves downstream systems unable to explain
    # why access changed.
    #
    # Keep this method as a clean orchestrator. It should read like a table of
    # contents over the domain layers while private leaf methods own the low-level
    # work. Do not inline the service details here; future agents need to verify
    # the renewal story in one read before touching individual mechanisms.
    def renew_subscription(self, subscription: Subscription) -> RenewalResult:
        plan = self._load_billable_plan(subscription)
        invoice = self._create_renewal_invoice(subscription, plan)
        entitlement = self._extend_entitlement_window(subscription, plan)
        event = self._publish_renewal_event(subscription, invoice, entitlement)
        self._record_renewal_audit(subscription, invoice, event)
        return RenewalResult(invoice=invoice, entitlement=entitlement, event=event)

    # @intent billable-plan-gate
    # Plan lookup is not just a data fetch. Renewal must only happen against a
    # currently billable plan because the plan defines the price, billing interval,
    # entitlement shape, and product promise we are about to extend.
    #
    # Archived plans remain readable for invoices, support screens, historical
    # analytics, and old subscriptions that still need display context. That does
    # not mean they are valid for new revenue events. Historical readability and
    # future billability are separate product rules.
    #
    # Keep this guard inside the renewal flow so scheduled renewals, manual admin
    # actions, and retry jobs all follow the same rule. A rewrite that checks
    # billability only in the API handler will miss non-API entry points.
    #
    # Do not silently substitute a current plan when the old one is archived.
    # Changing the plan during renewal changes price and entitlements without the
    # customer's explicit migration path.
    def _load_billable_plan(self, subscription: Subscription) -> Plan:
        plan = self._plans.get(subscription.plan_id)
        if not plan.is_billable:
            raise NonBillablePlanRenewalError(subscription_id=subscription.id)
        return plan

    # @intent invoice-before-entitlement
    # The invoice is the financial record that justifies the entitlement window.
    # Access should be extended only when there is a persisted renewal invoice
    # that finance, support, and provider reconciliation can point to later.
    #
    # This ordering protects against revenue leakage. If entitlement extension
    # happens first and invoice creation fails, the customer receives paid access
    # without an auditable charge record. That failure is hard to repair because
    # the product state already told the customer they were renewed.
    #
    # A future agent may be tempted to extend entitlements before invoicing to
    # make the code read like "grant access, then record billing." Do not do that
    # unless the domain model changes to support explicit pending entitlements and
    # compensating rollback.
    #
    # Keeping invoice creation in its own leaf method also makes retry behavior
    # easier to reason about: invoice idempotency belongs to billing, while the
    # orchestrator decides when entitlement work is allowed to proceed.
    def _create_renewal_invoice(self, subscription: Subscription, plan: Plan) -> Invoice:
        return self._invoices.create_renewal_invoice(subscription=subscription, plan=plan)

    # @intent entitlement-window-derived-from-plan
    # Entitlement dates must come from the plan's billing interval because the
    # plan is the product contract the customer purchased. The renewal flow should
    # not infer access duration from wall-clock guesses, caller input, or a UI
    # label that happens to describe the plan.
    #
    # This keeps renewals consistent across API requests, scheduled jobs, admin
    # recovery actions, and future migration tools. All entry points must produce
    # the same entitlement window for the same subscription and plan.
    #
    # The load-bearing detail is that the plan object reaches this method after
    # the billability gate. Do not recompute plan details from subscription fields
    # or accept an arbitrary duration parameter here; those rewrites split the
    # source of truth and make entitlement drift possible.
    #
    # If proration, trials, or promotional extensions are added later, model them
    # as explicit plan or renewal policy inputs instead of smuggling date math into
    # this leaf method.
    def _extend_entitlement_window(
        self,
        subscription: Subscription,
        plan: Plan,
    ) -> Entitlement:
        return self._entitlements.extend_for_plan(subscription=subscription, plan=plan)

    # @intent event-after-domain-writes
    # Billing events are consumed by email, analytics, lifecycle automation, and
    # support tooling. Emitting the event means the domain renewal has settled
    # enough for other systems to act on it.
    #
    # The event must come after invoice and entitlement writes because consumers
    # expect the ids in the payload to resolve immediately. If an event points at
    # an invoice or entitlement that failed to persist, downstream systems have no
    # reliable way to distinguish a transient race from a broken renewal.
    #
    # Do not move this publish call earlier to make the orchestrator appear more
    # asynchronous. An early event can send customer email, update metrics, or open
    # support-visible state for a renewal that later fails.
    #
    # If event delivery becomes asynchronous, preserve this semantic boundary:
    # enqueue only after the domain writes have succeeded, and keep the payload
    # tied to persisted invoice and entitlement identifiers.
    def _publish_renewal_event(
        self,
        subscription: Subscription,
        invoice: Invoice,
        entitlement: Entitlement,
    ) -> BillingEvent:
        return self._events.publish_subscription_renewed(
            subscription_id=subscription.id,
            invoice_id=invoice.id,
            entitlement_id=entitlement.id,
        )

    # @intent renewal-audit-trace
    # The audit entry is the operator-facing receipt for the renewal. It ties the
    # customer subscription, invoice, emitted event, and access change together in
    # one place that support and finance can query without reconstructing the
    # entire flow from separate systems.
    #
    # Events and invoices are not enough on their own. Events are optimized for
    # downstream consumers, and invoices are optimized for financial records. The
    # audit log explains why access changed and which renewal action caused the
    # visible customer state.
    #
    # Keep the audit write after the event id exists so the record can identify
    # the exact downstream signal that was emitted. Do not remove this as
    # "duplicate logging"; it is the durable trace that makes support escalation
    # and finance reconciliation possible after later systems mutate their own
    # records.
    #
    # A rewrite that relies on logs or provider dashboards instead will fail
    # during incident review because those sources are incomplete, retention-bound,
    # and not shaped around the customer subscription timeline.
    def _record_renewal_audit(
        self,
        subscription: Subscription,
        invoice: Invoice,
        event: BillingEvent,
    ) -> None:
        self._audit_log.record_subscription_renewal(
            subscription_id=subscription.id,
            invoice_id=invoice.id,
            event_id=event.id,
        )
```

## Example 4: TypeScript intent comment for a compliance boundary

```typescript
// @intent pii-redaction-before-export
// Customer exports leave the service boundary and may be stored by third-party
// systems, shared with vendors, or downloaded into unmanaged environments. This
// function is the last trusted boundary before that data becomes harder to
// recall, audit, or delete.
//
// Redaction belongs here, not in the UI, because exports can be created by
// scheduled jobs, admin tools, API clients, and future automation paths that
// never render the customer dashboard. The export boundary must protect every
// caller, not only the interactive product path.
//
// Preserve the email-domain-only behavior unless the privacy policy and data
// processing agreement explicitly change. Full email addresses are direct
// identifiers; domains are enough for the downstream reporting use case without
// exposing the customer contact.
//
// A rewrite that returns the original record and expects callers to drop fields
// later will leak PII as soon as one caller forgets. Keep the allowlist shape so
// new sensitive fields added to CustomerRecord are excluded by default.
function redactCustomerExport(record: CustomerRecord): ExportRecord {
  return {
    id: record.id,
    emailDomain: record.email.split("@")[1],
    plan: record.plan,
    createdAt: record.createdAt,
  };
}
```

# Conclusion
Intent comments are useful only when they preserve meaning that code structure alone cannot carry. Do not treat `@intent` as a badge for important-looking functions or as a rigid docblock schema. The comment earns its place when it tells a future agent why the behavior exists, what business or domain rule must survive, and what plausible rewrite would be dangerous even if the code still looked clean. Keep the explanation beside the operation it governs so the rule is read before the edit happens, not after a regression has already been introduced. If the intent is already obvious from the name, type, and tests, skip the comment rather than dilute the signal. If the code carries money movement, permission, compliance, idempotency, state transition, or customer consequence, make the intent explicit enough that a future refactor can change the mechanism without losing the rule. Use the examples as calibration for depth, not as text to imitate. The goal is code whose load-bearing product meaning remains visible at the exact point where an agent is most likely to change it.
