# Codex live observation

Opted-in native turns deliver ordered, awaited, reviewed observations and existing
Vidbyte tracer spans. Tests use actual pinned SDK models and fake only the native
stream transport. Required failures include mismatched identities, absent terminal
events, failed turns, observer errors, and cancellation. Provider tracing is optional;
private reasoning never reaches observers. No test asserts control of hidden model
iterations. Offline acceptance, integration, and regression checks are selected;
browser, performance, and live billing tests do not establish this contract.
