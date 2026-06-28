# Description
The function is the agent's atomic unit of comprehension, naming, change, test, and reuse. A 200-line function blows past all five at once: it overflows a single read, cannot carry an honest name, localizes nothing, provides no clean test contract, and forces copy-paste reuse instead of recombination. The rule is not aesthetic. Each property below is a concrete reliability gain for an agent operating under limited context. The core pattern is to extract functions until every function does exactly one thing at one level of abstraction, and then to make that constraint enforceable by the linter so violations become loop feedback rather than style advice.

# Intent
The intent of function design for agent readability is to make every callable a clean interface that compresses behavior into a name, a signature, and a small body an agent can verify in one pass. Agents do not fail only because code is wrong; they fail because the unit they need to understand is too large, too entangled, or too implicit to fit cleanly into the current reasoning window.

Long functions are bad: they are not extensible and they are easy to break. A long function that does five things at once cannot be named honestly, cannot be tested in isolation, and forces any agent editing it to hold the entire body in context before making even a small change. Our philosophy on function design is simple — functions should be small and reusable. This is not a mechanical rule derived from a complexity formula; it is a taste and judgment call, a craft decision about what makes code understandable and maintainable over time. No exact line count or cyclomatic score makes a function correct — the goal is a body small enough to name cleanly, understand in one read, and swap in or out without side effects on the surrounding system.

# Function Requirements
* Functions do ONE thing AND ONE THING only. If you cannot describe the function's job in one sentence without a conjunction, split it. The honest-name test is absolute: a name that requires "and," "or," or "then" is a name for two functions, not one.
* Functions are ideally up to 30 lines of code. Thirty lines is not a hard ceiling — it is a strong signal. When a function body approaches or exceeds 30 lines, treat it as a prompt to audit whether it is doing more than one thing and extract accordingly.
* Functions are semantically named using underscore_naming. The name must describe what the function does at its level of abstraction, not how it does it. A name like `process_data` describes nothing; a name like `validate_subscription_address` is graspable without reading the body.
* Orchestrator / leaf split: public functions orchestrate and read like a table of contents, while private leaf functions do the actual work. An agent reading the orchestrator should be able to understand the entire flow without opening any leaf.
* Pure core, imperative shell: push side effects to the edges of the call graph and keep the middle pure. Deterministic computation that takes inputs and returns outputs is easy to test, reason about, and reuse without side effects leaking.
* Functions accept no more than three positional arguments. Beyond three, group excess parameters into a typed object so the call site is self-documenting and type checking can catch transpositions.
* Functions return at most one logical value. A function that returns a tuple of unrelated values is doing two jobs. If multiple values must be returned together, group them into a named dataclass or typed object.
* Functions stay at a single level of abstraction throughout their body. Mixing high-level orchestration logic with low-level implementation detail inside one body means the function is doing more than one thing at different altitudes.

# Things Not to Do
* Do not write a function whose name requires a conjunction ("and," "or," "then"). Split it at the conjunction.
* Do not write a function body longer than 30 lines without auditing whether it is doing more than one job.
* Do not use boolean or string flag arguments to switch between two behaviors inside one function. A flag argument is a hidden branch that forces the caller to remember what the flag means rather than naming the behavior directly.
* Do not write a function that both changes state and returns a meaningful value. Commands and queries must be separated so each is independently testable.
* Do not accept more than three positional arguments. A wide argument list is a sign that the function is doing too much or that its inputs need a typed container.
* Do not mix orchestration logic and implementation detail in the same function body. A function that both decides what to do and does the low-level work cannot be named at either altitude.
* Do not nest logic more than three levels deep inside a single function. Deep nesting is a sign that the inner logic should be extracted into a named helper.
* Do not rely only on code review to enforce decomposition. Decomposition is a design rule and belongs in the linter so it fires on every change automatically.
* Do not write functions that return different types depending on a runtime condition. A function that returns `str | None` based on a flag is two functions with an invisible branch.
* Do not use output parameters (mutating a passed-in container to "return" a second value) as a workaround for the single-return rule. Extract a named dataclass or typed tuple instead.
* Do not write functions that depend on shared mutable state across calls. State that accumulates across calls belongs in a class with an explicit lifecycle, not in a free function.
* Do not write a function that starts by validating its input and also does the core work. Validation and execution are two jobs; split them so each has a name.
* Do not accept **kwargs as the primary interface for a non-decorator function. Untyped keyword arguments hide the contract from both callers and type checkers.
* Do not leave dead code paths inside a function body. A branch that can never be reached is a hidden invariant waiting to mislead an agent.
* Do not write a function whose body requires reading three or more earlier functions to understand. If understanding the body requires deep context from elsewhere, the function is entangled and should be split or its dependencies made explicit in the signature.

# Checklist
* Before writing a function, decide what its one job is and name it without "and," "or," or "then."
* After writing a non-trivial public function, check whether it is actually an orchestrator that should delegate to named private leaf functions.
* Before writing a function with a boolean or string flag argument, split it into explicitly named functions.
* After writing a function that takes more than three positional arguments, group the excess into a typed parameter object.
* After writing a function body that exceeds 25 lines, audit whether it is doing more than one thing and extract accordingly.
* After completing a module, verify that every public function reads like an English sentence at the call site — if it does not, the name or the decomposition needs revision.
* Before opening a pull request, scan every new or modified function and verify it has one honest name with no conjunction.

# Examples

## Example 1: Validate a subscription address

```python
def validate_subscription_address(address: Address) -> None:
    if not address:
        raise MissingAddressError(address=address)
    if not address.zip_code:
        raise MissingZipCodeError(address=address)
    if not address.country_code:
        raise MissingCountryCodeError(address=address)
    if len(address.zip_code) < 4:
        raise InvalidZipCodeError(address=address)
    if address.country_code not in SUPPORTED_BILLING_COUNTRIES:
        raise UnsupportedCountryError(address=address)
```

## Example 2: Build an invoice email message

```python
def build_invoice_email(invoice: Invoice, user: User) -> EmailMessage:
    subject = f"Your invoice for {invoice.period_label}"
    body_lines = [
        f"Hi {user.first_name},",
        f"Invoice #{invoice.id} for {format_currency(invoice.total_cents)} is ready.",
        f"Due date: {invoice.due_date.strftime('%B %d, %Y')}",
        f"View your invoice: {invoice.portal_url}",
    ]
    return EmailMessage(
        to=user.email,
        subject=subject,
        body="\n\n".join(body_lines),
    )
```

## Example 3: Compute a prorated charge amount

```python
def compute_prorated_cents(
    plan_cents: int,
    days_remaining: int,
    days_in_period: int,
) -> int:
    if days_in_period <= 0:
        raise InvalidBillingPeriodError(days_in_period=days_in_period)
    if days_remaining < 0 or days_remaining > days_in_period:
        raise InvalidDaysRemainingError(days_remaining=days_remaining)
    ratio = days_remaining / days_in_period
    raw = plan_cents * ratio
    return round(raw)
```

## Example 4: Check whether a plan is available to a user

```python
def is_plan_available_for_user(plan: Plan, user: User) -> bool:
    if plan.status != PlanStatus.ACTIVE:
        return False
    if plan.region_restriction and user.region not in plan.allowed_regions:
        return False
    if plan.beta_only and not user.is_beta_participant:
        return False
    if plan.requires_verified_email and not user.email_verified:
        return False
    return True
```

## Example 5: Parse a raw webhook payload into a typed event

```python
def parse_stripe_checkout_event(raw_payload: dict) -> CheckoutEvent:
    event_type = raw_payload.get("type", "")
    if not event_type.startswith("checkout.session"):
        raise UnexpectedEventTypeError(event_type=event_type)
    data = raw_payload.get("data", {}).get("object", {})
    return CheckoutEvent(
        session_id=data["id"],
        customer_id=data.get("customer"),
        amount_total=data.get("amount_total", 0),
        currency=data.get("currency", "usd"),
        metadata=data.get("metadata", {}),
    )
```

## Example 6: A class with seven small single-purpose methods

```python
class SubscriptionManager:
    def __init__(self, db: Database, events: EventPublisher) -> None:
        self._db = db
        self._events = events

    def create_subscription(self, plan: Plan, user: User) -> Subscription:
        self._assert_plan_is_active(plan)
        self._assert_user_has_payment_method(user)
        record = self._build_subscription_record(plan, user)
        saved = self._db.subscriptions.insert(record)
        self._events.publish(SubscriptionCreatedEvent(subscription_id=saved.id))
        return saved

    def _assert_plan_is_active(self, plan: Plan) -> None:
        if plan.status != PlanStatus.ACTIVE:
            raise InactivePlanError(plan_id=plan.id)

    def _assert_user_has_payment_method(self, user: User) -> None:
        if not user.default_payment_method_id:
            raise MissingPaymentMethodError(user_id=user.id)

    def _build_subscription_record(self, plan: Plan, user: User) -> SubscriptionRecord:
        now = utcnow()
        return SubscriptionRecord(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=advance_by_interval(now, plan.billing_interval),
        )

    def cancel_subscription(self, subscription_id: str) -> None:
        sub = self._db.subscriptions.get(subscription_id)
        self._assert_subscription_is_cancelable(sub)
        self._db.subscriptions.set_cancel_at_period_end(subscription_id, True)
        self._events.publish(SubscriptionCancellationScheduledEvent(subscription_id=sub.id))

    def _assert_subscription_is_cancelable(self, sub: Subscription) -> None:
        if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
            raise SubscriptionNotCancelableError(subscription_id=sub.id, status=sub.status)

    def get_active_subscriptions_for_user(self, user_id: str) -> list[Subscription]:
        return self._db.subscriptions.find_by_user_and_status(
            user_id=user_id,
            status=SubscriptionStatus.ACTIVE,
        )
```
