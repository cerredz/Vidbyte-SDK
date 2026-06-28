# Description
You are going to write agent-native code, and the principle this file introduces is intent-based commenting. Intent-based commenting means putting the reason a piece of important code exists directly beside the implementation that carries that reason. It is not a decorative comment style, a formal docblock schema, or a replacement for readable code. It is a way to preserve the why and the domain meaning of business-critical logic at the exact point where an agent will read, rewrite, and risk changing that logic.

Agent-native code changes often. A function may be refactored, split, renamed, moved, or regenerated many times by different agents. The implementation can change safely when the durable meaning is still visible: what business rule must remain true, why a non-obvious guard exists, what customer or money path depends on this behavior, and what mistake a future rewrite must not repeat. Intent-based commenting keeps that meaning close enough to the code that it is read as part of the code, not as optional background material in a distant design document.

This skill file teaches you when to write intent comments and how to write them while coding. The shape is deliberately simple: write `@intent` followed by a short name, then use a multiline comment to clearly explain the intent. Some intent comments should be four lines because the rule is simple. Some should be forty lines because the function coordinates several domain layers and carries expensive business constraints. Length is not the goal. Capturing the actual intent is the goal.

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
# Explain the meaning of this code in plain language. Say what business or
# domain rule must survive a rewrite, why the rule matters, and what a future
# agent must not accidentally remove.
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

Use as many lines as the intent needs. A short guard might need four lines:

```python
# @intent refund-ceiling
# Refunds may never exceed the amount captured for the original payment. This
# is a money movement invariant, not a UI validation detail; keep it here even
# if callers also validate refund amounts before reaching this service.
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

Make the comment useful at different lengths. A four-line intent comment is good when it captures the whole rule. A long comment is good when the operation spans multiple domain layers and future agents need more context. A long comment full of step-by-step narration is bad. A short comment that hides the real business consequence is also bad.

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
* Keep the comment at the right length: short for simple intent, longer when multiple domain layers or expensive consequences are involved.
* Write the comment at the level of meaning, not at the level of variable names, loops, branches, or helper call order.
* Keep public orchestrators readable and small when intent comments describe multi-layer flows; use private leaf methods for the low-level work.
* After changing code with an existing intent comment, reread the comment and update it if the behavior or consequence changed.
* Before opening a pull request, scan new or modified business/domain functions and confirm the important ones carry clear intent comments.

# Code Examples

## Example 1: Short Python intent comment for a money invariant

```python
# @intent refund-ceiling
# A refund may never exceed the amount captured for the original payment. Keep
# this check in the write-side billing service even if API callers validate the
# amount earlier, because provider retries and admin tools can bypass the API.
def validate_refund_amount(payment: Payment, requested_cents: int) -> None:
    if requested_cents > payment.captured_cents:
        raise RefundExceedsCaptureError(payment_id=payment.id)
```

## Example 2: Medium Python intent comment for webhook idempotency

```python
# @intent provider-webhook-idempotency
# Provider webhooks are replayed during outage recovery and can arrive more than
# once with the same provider_event_id. This function must treat the provider
# event id as the idempotency key, not the local database id or arrival time.
# A rewrite that simply inserts on every received webhook will pass normal happy
# path tests but will duplicate charges and emails during replay storms.
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
    # Renewal is the write-side boundary for subscription revenue. It combines
    # plan validation, invoice creation, entitlement extension, event emission,
    # and audit logging into one domain operation.
    #
    # The important rule is that the customer must never land in a half-renewed
    # state. A renewal that creates an invoice without extending entitlements is
    # a support incident. A renewal that extends entitlements without a settled
    # invoice is revenue leakage. A renewal that emits an event before the audit
    # record exists leaves downstream systems with no reliable trace.
    #
    # Keep this method as a clean orchestrator. It should read like a table of
    # contents over the domain layers and delegate implementation details to
    # private leaf methods. That shape is intentional: future agents can verify
    # the business flow in one read without opening every service class.
    def renew_subscription(self, subscription: Subscription) -> RenewalResult:
        plan = self._load_billable_plan(subscription)
        invoice = self._create_renewal_invoice(subscription, plan)
        entitlement = self._extend_entitlement_window(subscription, plan)
        event = self._publish_renewal_event(subscription, invoice, entitlement)
        self._record_renewal_audit(subscription, invoice, event)
        return RenewalResult(invoice=invoice, entitlement=entitlement, event=event)

    # @intent billable-plan-gate
    # Plan lookup is not just a data fetch. A subscription can only renew against
    # a currently billable plan; archived plans are allowed for historical reads
    # but not for new revenue events. Keep this guard here so batch renewals and
    # admin-triggered renewals follow the same product rule.
    def _load_billable_plan(self, subscription: Subscription) -> Plan:
        plan = self._plans.get(subscription.plan_id)
        if not plan.is_billable:
            raise NonBillablePlanRenewalError(subscription_id=subscription.id)
        return plan

    # @intent invoice-before-entitlement
    # The invoice is the financial record that justifies the entitlement window.
    # Create it before extending access so a failed payment or invoice write
    # cannot leave the customer with paid features that finance cannot reconcile.
    def _create_renewal_invoice(self, subscription: Subscription, plan: Plan) -> Invoice:
        return self._invoices.create_renewal_invoice(subscription=subscription, plan=plan)

    # @intent entitlement-window-derived-from-plan
    # Entitlement dates must come from the plan's billing interval, not from the
    # caller or wall-clock guesses. This keeps renewal behavior consistent across
    # API requests, scheduled jobs, and manual recovery tools.
    def _extend_entitlement_window(
        self,
        subscription: Subscription,
        plan: Plan,
    ) -> Entitlement:
        return self._entitlements.extend_for_plan(subscription=subscription, plan=plan)

    # @intent event-after-domain-writes
    # Billing events are consumed by email, analytics, and support tooling. Emit
    # only after invoice and entitlement writes succeed so every consumer sees a
    # settled renewal instead of a speculative attempt.
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
    # The audit entry is the cross-system receipt for the renewal. Support and
    # finance use it to answer why access changed, which invoice paid for it,
    # and which downstream event was emitted. Do not remove this because events
    # and invoices are not enough on their own to reconstruct the operator view.
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
// systems. Redaction happens here, not in the UI, because exports can be created
// by scheduled jobs and admin tooling that never render the customer dashboard.
function redactCustomerExport(record: CustomerRecord): ExportRecord {
  return {
    id: record.id,
    emailDomain: record.email.split("@")[1],
    plan: record.plan,
    createdAt: record.createdAt,
  };
}
```
