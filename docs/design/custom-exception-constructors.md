<!-- Context Protocol Header

Description:
    Design document for fixing custom exception constructors in vidbyte-sdk.
Purpose:
    Ensures that custom exception subclasses implement their own constructors
    to avoid inheriting incompatible parameter signatures and violating architecture constraints.
Architecture:
    Outline of the refactoring strategy for ProviderConfigurationError and ProviderResponseError.
Relations:
    Related to vidbyte/lib/errors/base.py.
-->

# Design Doc: Custom Exception Constructors

**Status:** Draft
**Author:** Antigravity
**Created:** 2026-05-29
**Last Updated:** 2026-05-29

---

## 1. Overview

This design document proposes a solution to decouple `ProviderConfigurationError` and `ProviderResponseError` from `ProviderRequestError`'s custom constructor parameters. By giving each exception subclass its own constructor scoped to its failure context and updating inheritance hierarchies, we enforce clean parameter interfaces and satisfy the repository's constraint that custom exceptions implement their own constructors rather than silently inheriting incompatible parameter signatures.

---

## 2. Goals & Non-Goals

### Goals

- Fix the constructor signature pollution for `ProviderConfigurationError` and `ProviderResponseError`.
- Let `ProviderConfigurationError` inherit directly from `VidbyteSdkError` since configuration is not an HTTP request/response issue.
- Let `ProviderResponseError` inherit directly from `VidbyteSdkError` and accept only parameters relevant to response normalization errors.
- Ensure that the repository's hard constraints on custom exception class signatures and implementations are fully met.
- Provide comprehensive test verification for all changes.

### Non-Goals

- Refactoring other unrelated custom exceptions that do not violate the custom exception constructor rule (e.g. exceptions that only inherit generic signatures without specialized parameter pollution).
- Altering the core HTTP transport or parsing layer logic.

---

## 3. Background & Context

In the `vidbyte-sdk` repository, `ProviderRequestError` is a custom exception subclass of `VidbyteSdkError` representing a failed HTTP request to an AI provider. Its custom `__init__` signature demands keyword-only parameters: `provider`, `status_code`, and `response_excerpt`.

Both `ProviderConfigurationError` and `ProviderResponseError` subclass `ProviderRequestError` without implementing their own `__init__` constructor. This leads to several issues:
1. **Semantic mismatch**: A configuration error (e.g., a missing API key during setup/validation) occurs before any HTTP request is sent. Callers catch `ProviderConfigurationError` but are forced to pass `status_code=None` and `response_excerpt=None` to construct it, even though these fields are meaningless for configuration errors.
2. **Coupling**: Any future modifications to `ProviderRequestError.__init__`'s signature will silently break the constructors of its subclasses.
3. **Constraint violation**: The repository has a strict constraint: *"Custom exception classes should have their own parameters and implement their own constructor, they should not have dataclasses being imported into their own constructor."*

---

## 4. Requirements

### Functional Requirements

1. `ProviderConfigurationError` must inherit directly from `VidbyteSdkError` rather than `ProviderRequestError`.
2. `ProviderConfigurationError` must define its own `__init__` constructor with a signature accepting `message: str` and keyword-only parameter `provider: str`.
3. `ProviderConfigurationError` must store `self.provider = provider` and set `details={"provider": provider}` in the parent class `VidbyteSdkError`.
4. `ProviderResponseError` must inherit directly from `VidbyteSdkError` rather than `ProviderRequestError`.
5. `ProviderResponseError` must define its own `__init__` constructor accepting `message: str` and keyword-only parameters `provider: str`, optional `status_code: int`, and optional `response_excerpt: str`.
6. `ProviderResponseError` must store `self.provider = provider`, `self.status_code = status_code`, and `self.response_excerpt = response_excerpt`, and populate the base `details` mapping (truncating `response_excerpt` to at most 500 characters).
7. Ensure all existing code instantiations of `ProviderConfigurationError` and `ProviderResponseError` are compatible with the new scoped constructors.

### Non-Functional Requirements

- Maintain exact compatibility with the existing provider adapters (`anthropic.py`, `openai.py`, `gemini.py`, `xai.py`, `compatible.py`), none of which pass `status_code` or `response_excerpt` to `ProviderConfigurationError`.
- No regression in existing tests or test coverage.

---

## 5. High-Level Design

The overall approach is to modify the exception definitions in `vidbyte/lib/errors/base.py`. We will change the base class of `ProviderConfigurationError` and `ProviderResponseError` to `VidbyteSdkError` and implement specialized `__init__` methods for each subclass.

```text
[VidbyteSdkError]
   ^         ^
   |         +-----------------------+
[ProviderRequestError]   [ProviderConfigurationError] (Custom __init__)
   ^
   |
[ProviderResponseError]  --> Decoupled to:

[VidbyteSdkError]
   ^         ^                            ^
   |         |                            |
[ProviderRequestError]  [ProviderConfigurationError]  [ProviderResponseError]
(Custom __init__)        (Custom __init__)             (Custom __init__)
```

By defining separate classes inheriting directly from `VidbyteSdkError`, each subclass defines only the attributes and constructor arguments that make sense for its domain.

---

## 6. Detailed Design

### 6.1 ProviderConfigurationError

**File(s):** `vidbyte/lib/errors/base.py`
**Type:** Modified

#### What it does

Represents validation and configuration errors for provider clients/adapters (e.g. missing credentials or incompatible config shapes).

#### Interface / API

```python
class ProviderConfigurationError(VidbyteSdkError):
    """Raised when a provider adapter is missing required configuration."""

    def __init__(self, message: str, *, provider: str) -> None:
        # Initializes the error with a message and the associated provider.
```

#### Logic / Algorithm

1. Invoke `super().__init__(message, details={"provider": provider})`.
2. Store `self.provider = provider`.

---

### 6.2 ProviderResponseError

**File(s):** `vidbyte/lib/errors/base.py`
**Type:** Modified

#### What it does

Represents failures when normalizing or parsing responses returned by provider endpoints.

#### Interface / API

```python
class ProviderResponseError(VidbyteSdkError):
    """Raised when a provider response cannot be normalized."""

    def __init__(self, message: str, *, provider: str, status_code: int | None = None, response_excerpt: str | None = None) -> None:
        # Initializes the error with response failure context, including status code and response body excerpt.
```

#### Logic / Algorithm

1. Construct a `details` dictionary containing `"provider": provider`.
2. If `status_code` is not `None`, add `"status_code"` to `details`.
3. If `response_excerpt` is provided and non-empty, truncate it to 500 characters and add `"response_excerpt"` to `details`.
4. Invoke `super().__init__(message, details=details)`.
5. Store `self.provider = provider`, `self.status_code = status_code`, and `self.response_excerpt = response_excerpt`.

---

## 7. Data Model Changes

N/A - This change only affects runtime exception classes and does not introduce database or persistent schema modifications.

---

## 8. API Changes

N/A - This change only affects the SDK's internal library exceptions and does not introduce new API endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/errors/base.py` | Declare new constructors and base classes for `ProviderConfigurationError` and `ProviderResponseError`. |

---

## 10. Testing Plan

### Unit Tests

We will write unit tests to explicitly verify all edge cases, hidden failure modes, silent failures, and hidden assumptions for the new exception structures.

#### Exception Instantiation Verification
- **[Edge Case] ProviderConfigurationError with custom details:**
  Verify that `ProviderConfigurationError("msg", provider="openai")` correctly raises the exception, populates `provider` property, and does not accept `status_code` or `response_excerpt`.
- **[Edge Case] ProviderResponseError response excerpt truncation:**
  Verify that passing a very long `response_excerpt` (greater than 500 characters) to `ProviderResponseError` truncates the value to exactly 500 characters in the `details` dictionary, but leaves `self.response_excerpt` intact (or truncates appropriately).
- **[Hidden Failure] Constructor parameter constraints:**
  Verify that attempting to construct `ProviderConfigurationError` with `status_code` or `response_excerpt` raises a `TypeError` (since they are no longer accepted parameters).
- **[Silent Failure] Detail dictionary isolation:**
  Verify that `details` populated inside `ProviderResponseError` is isolated and does not mutate or leak details across separate exception instances.
- **[Hidden Assumption] Subclass structure and inheritance:**
  Verify that `ProviderConfigurationError` is an instance of `VidbyteSdkError` but **not** an instance of `ProviderRequestError`.
  Verify that `ProviderResponseError` is an instance of `VidbyteSdkError` but **not** an instance of `ProviderRequestError`.

### Integration Tests

- Run the full existing `vidbyte-sdk` test suite (`pytest`) to ensure no regressions in existing provider adapter or agent workflows.

---

## 11. Dependencies & External Services

N/A - No new dependencies or external services are introduced.

---

## 12. Rollout & Deployment

- This is a minor breaking change to exception inheritance and constructor signature interfaces. Since it's an SDK, internal changes will be rolled out in the next package version.
- Rollback plan: Revert git commit and restore the original `ProviderRequestError` subclasses.

---

## 13. Open Questions

- None. The problem and proposed solution have been fully investigated and verified against the codebase.

---

## 14. Alternatives Considered

### Alternative 1: Keep original subclasses and add stub `__init__`
- Keep `ProviderConfigurationError` and `ProviderResponseError` inheriting from `ProviderRequestError` but override `__init__` with custom signatures.
- **Why rejected:** Configuration error is semantically not a request error, and maintaining the inheritance hierarchy would imply that a configuration error is a subtype of a request error, which violates proper OOP domain modeling. Overriding also risks type mismatches in static analysis tools when subclass constructors restrict/change parameter signatures from the parent class.

---

## 15. Responses to Follow-up Questions

### 15.1 Codebase scan for `ProviderConfigurationError`
*Question:* Scan the codebase for every site that constructs a `ProviderConfigurationError`. Do any of them pass `status_code` or `response_excerpt`? If not, what does that tell you about whether the inherited constructor fields are being used?

*Answer:*
A complete scan of the codebase shows that the following sites construct a `ProviderConfigurationError`:
- `vidbyte\providers\anthropic.py:30`
- `vidbyte\providers\compatible.py:32`
- `vidbyte\providers\gemini.py:32`
- `vidbyte\providers\openai.py:62`, `68`, `74`
- `vidbyte\providers\xai.py:30`

None of these locations pass `status_code` or `response_excerpt`. They only pass `provider=self.provider.value`.
This confirms that the inherited constructor parameters `status_code` and `response_excerpt` are completely unused and irrelevant for configuration failures. A configuration check occurs before an HTTP request is made, so no response metadata exists.

### 15.2 McpError vs ProviderRequestError Inheritance Case
*Question:* The hard constraint applies to custom exception classes generally. Are there other exception subclasses in `vidbyte/lib/errors/base.py` that do the same thing — subclass a custom exception without their own `__init__`? For example, `McpConnectionError`, `McpInitializeError`, `McpToolDiscoveryError`, `McpToolExecutionError` all extend `McpError` which extends `VidbyteSdkError`. Is this different from the `ProviderRequestError` inheritance case, and why?

*Answer:*
Yes, there are subclasses of `McpError` that do not define their own `__init__` (`McpConnectionError`, `McpInitializeError`, `McpToolDiscoveryError`, `McpToolExecutionError`).
However, this is fundamentally different from the `ProviderRequestError` inheritance case:
- `McpError` does **not** define a custom `__init__` constructor. It inherits the extremely generic constructor of `VidbyteSdkError.__init__(self, message: str, *, details: Mapping[str, Any] | None = None)`. This constructor is perfectly suited for any general error because it accepts an arbitrary message and optional details metadata. The subclasses inherit this same generic signature without having their parameters contaminated by specialized or irrelevant fields.
- On the other hand, `ProviderRequestError` defined a highly specialized constructor (`provider`, `status_code`, `response_excerpt`). When subclasses like `ProviderConfigurationError` inherited this constructor, they were polluted with parameters that were semantically meaningless for their specific failure domains.

### 15.3 Impact of changing `ProviderConfigurationError base class`
*Question:* If you changed `ProviderConfigurationError` to extend `VidbyteSdkError` directly rather than `ProviderRequestError`, which except blocks in the codebase would need to be updated to still catch configuration errors?

*Answer:*
There are **no** `except` blocks in the codebase that catch `ProviderRequestError` expecting to also catch `ProviderConfigurationError`. There are no `except ProviderConfigurationError` blocks either. Therefore, no `except` blocks in the production codebase will need to be updated.
Furthermore, the test suite asserts configuration errors using `assertRaises(ConfigurationError)` or does not assert `ProviderConfigurationError` explicitly in general. Decoupling the base class will not break any error-catching code in the SDK.
