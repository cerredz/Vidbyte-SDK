# Design Doc: JevAgent Vidbyte Managed Gateway Credentials

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-29
**Last Updated:** 2026-09-29

---

## 1. Overview

Make JevAgent use Vidbyte's managed TypeSafe gateway, authenticating with `VIDBYTE_API_KEY` and the fixed Vidbyte gateway URL. Direct TypeSafe credentials remain available to standalone decision runners only; `JevRuntimeSettings` rejects direct mode. Managed credentials stay out of representations and gateway response bodies; missing or rejected managed credentials stop Jev-controlled features, while transient network and upstream service outages retain Jev's advisory behavior. The managed-only JevAgent boundary supersedes the earlier compatibility decision in this design; see `docs/design/jev-agent-managed-only-decisions.md`.

---

## 2. Goals & Non-Goals

### Goals

- Route JevAgent's default decision requests and model-list requests through the Vidbyte managed gateway.
- Resolve only `VIDBYTE_API_KEY` for managed mode, validate its live-key format, and never fall back to `TYPESAFE_API_KEY`.
- Pin managed calls to the product gateway endpoint and reject caller-supplied managed endpoints.
- Keep API keys out of configuration repr output and managed gateway error bodies/details.
- Fail closed in Jev decision call sites for missing/invalid managed credentials and HTTP 401, 402, 403, or 429; preserve fail-open behavior for transient failures.
- Preserve direct TypeSafe BYOK for standalone `DecisionModelRunner` use, but reject it from JevAgent settings.
- Update JevAgent usage guidance and add deterministic tests and a focused reporting script.

### Non-Goals

- Change Vidbyte backend gateway authentication, scopes, wallet checks, quotas, provider billing, or key lifecycle.
- Prevent a caller who modifies the SDK or makes unrelated direct provider calls from bypassing Vidbyte. The server remains authoritative for every request it receives.
- Route the generative model, Jev clarification agent, run-state writer, or handoff writer through the decision gateway; they remain configured by `JevAgentSettings`.
- Change retry counts, gateway idempotency, credit reservation, settlement durability, run closure, or backend metering.
- Add a staging/custom gateway URL or expose a managed endpoint override.

---

## 3. Background & Context

The Vidbyte product already exposes `POST /api/v1/models/typesafe/systemone` and `GET /api/v1/models/typesafe/models`. Both require a live `vb_live_` key with `models:invoke`; product responses use 401/402/403/429 for access, balance, scope, and quota rejection. The SDK's TypeSafe provider currently resolves only `TYPESAFE_API_KEY` and the TypeSafe URL. `JevRuntimeSettings` defaults to that direct-provider configuration, and the Jev gate, tool selector, and done checks treat all SDK errors as advisory and continue.

The managed mode is explicit in `DecisionModelConfig` and required by `JevRuntimeSettings`, while the general-purpose `DecisionModelConfig` stays direct TypeSafe by default for standalone runners. The Vidbyte API key authorizes only decision calls made through Vidbyte; it does not secure the rest of a client-side JevAgent or its generative provider.

Constraints: gateway endpoints and key formats must match the product contract; the SDK must not redirect a managed bearer credential to a custom host; and deterministic tests must never contact a live provider. Existing Jev behavior depends on advisory fail-open handling for transient provider failures, so only managed access/configuration failures become fatal.

---

## 4. Requirements

### Functional Requirements

1. `DecisionModelConfig` exposes a closed `DecisionModelMode` with direct TypeSafe and Vidbyte-managed values.
2. `JevRuntimeSettings()` creates a Vidbyte-managed decision config by default; standalone `DecisionModelConfig()` remains direct TypeSafe.
3. Managed mode resolves an explicit key first, otherwise only `VIDBYTE_API_KEY`; a missing or malformed live key raises a configuration error before any request.
4. Managed mode uses the fixed `https://api.vidbyte.pro/api/v1/models/typesafe` base URL for both System One and model listing and rejects any non-empty custom endpoint.
5. Managed mode sends `Authorization: Bearer <VIDBYTE_API_KEY>` and does not enable HTTP redirects.
6. `DecisionModelConfig.api_key`, its containing Jev runtime settings, and managed request headers do not reveal credentials through repr output.
7. Managed 401/402/403/429 responses and managed credential configuration errors propagate out of the gate, tool selector, and done-check decision request; they do not become an unavailable/advisory decision.
8. Managed timeout, connection, 5xx, and malformed-response failures retain the current fail-open behavior. Direct TypeSafe mode retains the current fail-open behavior for all `VidbyteSdkError`s.
9. `JevRuntimeSettings` rejects both implicit and explicit direct TypeSafe configs; direct runner tests stay independent of JevAgent.
10. Provider errors and formatted managed tracebacks identify Vidbyte, omit raw gateway response excerpts, and do not contain the configured key.
11. JevAgent guidance explains the managed decision requirement and required environment variable; standalone runner guidance may show direct TypeSafe mode.

### Non-Functional Requirements

- Performance: add no network round trip and no measurable work beyond local config/key validation.
- Scalability: preserve existing request batching and retry behavior.
- Security: pin the managed host, reject custom endpoints, avoid credential-bearing repr output, and do not include raw managed gateway bodies in errors.
- Observability: preserve safe HTTP status and provider identity details; do not log or trace credential values.
- Reliability: managed authorization/balance/scope/quota failures stop Jev-controlled execution; transient infrastructure/provider failures preserve the existing advisory fallback.

---

## 5. High-Level Design

Add a `DecisionModelMode` enum and let `DecisionModelConfig` select either direct TypeSafe access or Vidbyte-managed access. The latter uses `VIDBYTE_API_KEY`, validates the product's live key shape, pins the configured endpoint to Vidbyte's gateway, and suppresses key repr output. `JevRuntimeSettings` uses the managed config as its default and rejects direct mode. Standalone `DecisionModelRunner` remains available for direct TypeSafe calls.

The existing provider adapter will resolve the mode-specific key and URL. Its managed error mapping will name Vidbyte and status, while dropping response excerpts that could reflect credentials. A shared Jev decision failure policy will distinguish managed authorization/configuration failures from transient failures. The three decision call sites (preflight gate, tool selector, and done-check decision) will rethrow only the former and keep their current advisory behavior for the latter.

```text
JevRuntimeSettings default
        |
        v
DecisionModelConfig(VIDBYTE_MANAGED) -- VIDBYTE_API_KEY --> fixed Vidbyte gateway
        |                                                     |
        +--> preflight / tool selector / done-check <--------+
                 | managed 401/402/403/429 or config failure: raise
                 | transient failure: existing advisory fallback

Standalone DecisionModelRunner(TYPESAFE) -- TYPESAFE_API_KEY --> TypeSafe API (outside JevAgent)
```

---

## 6. Detailed Design

### 6.1 Decision model mode

**File(s):** `vidbyte/lib/enums/decision_model.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/config/__init__.py`
**Type:** New file and modified exports

#### What it does

Defines and exports the closed mode values `TYPESAFE` and `VIDBYTE_MANAGED` so callers can choose the connection policy without stringly typed flags.

#### Interface / API

```python
class DecisionModelMode(str, Enum):
    TYPESAFE = "typesafe"
    VIDBYTE_MANAGED = "vidbyte_managed"
```

#### Logic / Algorithm

1. Define the enum in `vidbyte/lib/enums/decision_model.py`.
2. Re-export it from `vidbyte.lib.enums` and `vidbyte.lib.config`.
3. Keep the mode enum free of network behavior and import-time environment reads.

#### Edge Cases & Error Handling

- Only declared enum members are accepted by `DecisionModelConfig`; invalid values raise `ConfigurationError` during construction.
- Importing the enum does not inspect environment variables or contact a service.

### 6.2 Managed decision configuration

**File(s):** `vidbyte/lib/constants/jev.py`, `vidbyte/lib/dataclasses/model_configs.py`
**Type:** Modified

#### What it does

Adds a fixed Vidbyte gateway base URL and mode-aware credential/endpoint resolution to `DecisionModelConfig`.

#### Interface / API

```python
mode: DecisionModelMode = DecisionModelMode.TYPESAFE
api_key: str | None = field(default=None, repr=False)
DecisionModelConfig.vidbyte_managed() -> DecisionModelConfig
```

#### Logic / Algorithm

1. Keep the general config's default mode as direct TypeSafe for standalone runner compatibility.
2. In direct mode, preserve `TYPESAFE_API_KEY` and provider endpoint resolution for standalone runners.
3. In managed mode, resolve an explicit key or `VIDBYTE_API_KEY`; do not consult the TypeSafe key variable.
4. Trim the selected key and validate `^vb_live_[A-Za-z0-9_-]{32,}$`, matching the product perimeter.
5. Reject any supplied managed endpoint; resolve to the fixed Vidbyte gateway base URL.
6. Leave request redirects disabled through the existing `HttpTransport` default.

#### Edge Cases & Error Handling

- Missing `VIDBYTE_API_KEY` raises a configuration error that names the required variable and never mentions the key value.
- A test key, short suffix, empty string, whitespace-only key, or TypeSafe key is rejected in managed mode.
- Direct mode does not impose Vidbyte's key format on TypeSafe credentials.
- A caller-provided endpoint, including a same-host URL, is rejected in managed mode to keep request routing fixed.

### 6.3 Jev default and managed failure policy

**File(s):** `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/decision_failures.py`
**Type:** Modified and new file

#### What it does

Makes managed gateway mode JevAgent's default and centralizes which managed failures must propagate.

#### Interface / API

```python
class JevDecisionFailurePolicy:
    @staticmethod
    def should_fail_closed(error: VidbyteSdkError, config: DecisionModelConfig) -> bool: ...
```

#### Logic / Algorithm

1. Set `JevRuntimeSettings.decision` to a default factory returning `DecisionModelConfig.vidbyte_managed()`.
2. In the policy helper, return false for direct TypeSafe mode.
3. In managed mode, return true for configuration errors and provider request statuses 401, 402, 403, and 429.
4. Return false for network failures without a status, 408, 5xx, and response-normalization failures so existing advisory behavior remains.
5. Have each decision caller rethrow when the policy returns true; otherwise preserve its current `None`/unavailable fallback.

#### Edge Cases & Error Handling

- Managed configuration failures cannot silently disable a gate, tool selector, or done check.
- A transient gateway outage does not prevent the main generative agent from running, matching the existing resilience policy.
- Standalone direct TypeSafe provider behavior remains independent of Jev's failure policy.
- Jev done-check tests use managed config with scripted runners; direct TypeSafe config is rejected at the Jev settings boundary.

### 6.4 Managed provider errors

**File(s):** `vidbyte/providers/typesafe.py`
**Type:** Modified

#### What it does

Maps managed provider failures to Vidbyte-specific, credential-safe messages while retaining current TypeSafe messages for direct mode.

#### Interface / API

No public signature changes. `_TypeSafeFailures.transport_error` branches on the resolved config mode.

#### Logic / Algorithm

1. For direct mode, preserve existing status mapping and provider details.
2. For managed mode, use Vidbyte wording and actionable status-specific guidance.
3. Preserve the numeric status and provider identity, but omit the raw response excerpt and underlying gateway error message.
4. For unexpected managed exceptions, redact the exact resolved key from any formatted exception text before wrapping it.

#### Edge Cases & Error Handling

- A gateway error body that echoes the key is not copied into a managed exception or its `details`.
- A missing response has no status but keeps a safe network/timeout explanation and follows fail-open policy.
- HTTP status mapping does not lose status information needed by the shared failure policy.

### 6.5 Jev decision call sites

**File(s):** `vidbyte/agents/jev/gate/gate.py`, `vidbyte/agents/jev/preflight.py`, `vidbyte/agents/jev/done/run_state.py`
**Type:** Modified

#### What it does

Applies the shared failure policy only around actual `DecisionModelRunner` calls.

#### Interface / API

No public signature changes.

#### Logic / Algorithm

1. Catch `VidbyteSdkError` as a named exception at each existing fail-open decision boundary.
2. Rethrow managed configuration/access failures identified by `JevDecisionFailurePolicy`.
3. For other errors, preserve current unavailable state and return value.
4. Leave generative sub-agent catches and `JevRuntime` unchanged.

#### Edge Cases & Error Handling

- The gate, tool selector, and done checks all apply identical managed access semantics.
- An empty/disabled feature still makes no request and does not require a key.
- A malformed response remains advisory rather than being mistaken for an authorization denial.

### 6.6 JevAgent guidance and verification

**File(s):** `skills/jev-agent/SKILL.md`, `tests/test_jev_managed_gateway.py`, `scripts/test-jev-managed-gateway.py`
**Type:** Modified and new files

#### What it does

Documents the default and supplies offline, reproducible behavioral coverage.

#### Interface / API

The focused script runs every test in `tests/test_jev_managed_gateway.py`, prints PASS/FAIL for each case, prints `X/Y tests passed`, and exits non-zero on any failure.

#### Logic / Algorithm

1. Document `VIDBYTE_API_KEY` and the required managed Jev gateway; document direct TypeSafe only for standalone runners.
2. Test configs, URL/header construction, endpoint pinning, provider error mapping, policy classification, and all three Jev decision callers using scripted transports/fakes.
3. Do not make live network calls.

#### Edge Cases & Error Handling

- The script includes assertion failures and unexpected exceptions in its final failure count.
- All test credentials are synthetic and are asserted absent from repr and error output.

---

## 7. Data Model Changes

### 7.1 DecisionModelConfig

**Change type:** Modified

```python
mode: DecisionModelMode = DecisionModelMode.TYPESAFE
api_key: str | None = field(default=None, repr=False)
```

**Migration strategy:** No persistence or database migration. Existing direct configs retain direct mode for standalone `DecisionModelRunner`. JevAgent requires `VIDBYTE_MANAGED`; applications that previously passed direct configs to `JevRuntimeSettings` must configure Vidbyte-managed access.

---

## 8. API Changes

N/A - No HTTP endpoint changes. `DecisionModelConfig` gains `mode` and `vidbyte_managed()`. `JevRuntimeSettings()` changes its decision default to the Vidbyte-managed gateway.

---

## 9. File Change Manifest

Complete list of every file expected to be created or modified:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-managed-gateway-credentials.md` | Record the feature design before implementation. |
| CREATE | `vidbyte/lib/enums/decision_model.py` | Define the closed connection mode enum. |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export the new enum. |
| MODIFY | `vidbyte/lib/config/__init__.py` | Make the mode available in the stable config namespace. |
| MODIFY | `vidbyte/lib/constants/jev.py` | Define the fixed Vidbyte gateway endpoint. |
| MODIFY | `vidbyte/lib/dataclasses/model_configs.py` | Resolve managed keys/endpoints and redact key repr. |
| MODIFY | `vidbyte/agents/jev/settings.py` | Default JevAgent decisions to managed mode. |
| CREATE | `vidbyte/agents/jev/decision_failures.py` | Centralize fail-closed managed access classification. |
| MODIFY | `vidbyte/providers/typesafe.py` | Produce safe, mode-specific provider errors. |
| MODIFY | `vidbyte/agents/jev/gate/gate.py` | Propagate managed access/configuration failures. |
| MODIFY | `vidbyte/agents/jev/preflight.py` | Propagate managed access/configuration failures. |
| MODIFY | `vidbyte/agents/jev/done/run_state.py` | Propagate managed access/configuration failures. |
| MODIFY | `skills/jev-agent/SKILL.md` | Require managed Jev decisions and explain standalone TypeSafe use. |
| CREATE | `tests/test_jev_managed_gateway.py` | Cover managed config, transport, errors, and failure policy. |
| MODIFY | `tests/test_jev_done.py` | Exercise managed Jev behavior and reject direct runtime settings. |
| CREATE | `scripts/test-jev-managed-gateway.py` | Provide focused PASS/FAIL verification. |

No files are deleted.

---

## 10. Testing Plan

### Unit Tests

- `DecisionModelConfig` defaults to direct TypeSafe; `JevRuntimeSettings` defaults to managed Vidbyte. [Silent Failure]
- Managed mode uses `VIDBYTE_API_KEY` when set and never falls back to `TYPESAFE_API_KEY`. [Hidden Assumption]
- Managed mode accepts a product-format `vb_live_` key and rejects missing, whitespace, short, `vb_test_`, provider, and non-string keys. [Edge Case]
- Managed mode rejects custom endpoint overrides and resolves the exact fixed gateway URL. [Hidden Assumption]
- Direct mode continues to resolve `TYPESAFE_API_KEY` and a compatible custom endpoint. [Hidden Failure]
- API keys are absent from config/settings/request-call repr output. [Silent Failure]
- Managed POST and GET calls use the product's System One and model-list paths and bearer header; direct mode keeps the TypeSafe host. [Silent Failure]
- Managed 401/402/403/429 classify as fail-closed; 408/5xx/no-status/provider-response errors classify as advisory. Direct provider tests run through the standalone runner. [Edge Case]
- Managed error mapping and formatted tracebacks preserve status/provider but omit a synthetic key echoed in the upstream message/body/cause. [Hidden Failure]
- Missing managed credentials are propagated from the gate, tool selector, and done-check decision boundary; transient failures remain fail-open at all three boundaries. [Hidden Failure]
- Disabled features with no decision call do not resolve a managed key. [Hidden Assumption]
- Direct TypeSafe authorization failures retain prior fail-open Jev behavior. [Hidden Failure]
- Jev runtime settings reject both implicit and explicit direct TypeSafe configuration. [Hidden Assumption]

### Integration Tests

- Use the SDK's scripted transport to run one System One request through the fixed managed gateway URL with a synthetic Vidbyte bearer key and normalize its response. [Silent Failure]
- Use a scripted transport for managed model listing and verify the result path and key header. [Edge Case]
- Exercise gate, selector, and done-check behavior with fake runners/transports for one access denial and one transient error each; no live external dependency is used. [Hidden Failure]
- Confirm HTTP redirects remain disabled on managed calls through the existing transport default. [Hidden Assumption]

### Manual / QA Test Cases

1. [Hidden Assumption] Set `VIDBYTE_API_KEY` to a valid development credential, configure a JevAgent with an enabled decision feature, and confirm the request targets `https://api.vidbyte.pro/api/v1/models/typesafe/systemone`.
2. [Hidden Assumption] Remove `VIDBYTE_API_KEY` while leaving `TYPESAFE_API_KEY` set; confirm the decision feature raises a configuration error and sends no request.
3. [Edge Case] Configure a managed endpoint override; confirm construction fails before any request is sent.
4. [Hidden Failure] Configure a standalone direct TypeSafe runner; confirm the request still targets the TypeSafe endpoint.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Vidbyte Model Gateway | `https://api.vidbyte.pro/api/v1/models/typesafe` | Managed Jev decision and model-list requests | Product endpoint, scope, key format, or status contract could change; keep SDK tests aligned with `vidbyte/backend`. |
| Python `httpx` transport | Existing pinned/ranged project dependency | Async bounded HTTP requests with redirects disabled by default | Transport default must remain redirect-disabled for credential safety. |
| TypeSafe System One | Existing direct endpoint and wire contract | Standalone runner BYOK path | Provider response/schema behavior remains independently managed. |

---

## 12. Rollout & Deployment

- No feature flag or backend migration is required.
- This changes the default Jev decision provider route. Deploy the SDK after confirming the production gateway is available and `models:invoke` keys are enabled.
- Standalone applications that intentionally use TypeSafe directly may use `DecisionModelMode.TYPESAFE` with `DecisionModelRunner`.
- Rollback: revert the SDK change; the backend gateway is unchanged.
- No secrets are embedded in package defaults or test artifacts.

---

## 13. Open Questions

- [ ] Confirm the production key-creation flow grants `models:invoke` to keys intended for JevAgent's new default.
- [ ] Confirm whether the product's model-list endpoint requires the same wallet admission floor as System One; SDK changes only route the request and do not alter server policy.

---

## 14. Alternatives Considered

### Alternative 1: Keep TypeSafe as JevAgent's default and document managed mode as opt-in

- What: Add a managed config factory but leave `JevRuntimeSettings()` pointed directly at TypeSafe.
- Why rejected: The requested SDK-to-product linkage would remain opt-in and ordinary JevAgent construction would continue bypassing Vidbyte's API key and gateway.

### Alternative 2: Permit arbitrary endpoint overrides in managed mode

- What: Allow staging proxies or custom hosts while using `VIDBYTE_API_KEY`.
- Why rejected: A typo or untrusted config could send the Vidbyte bearer credential to an unrelated host. Testing can use the injected transport without changing the target URL.

### Alternative 3: Fail closed for every managed service error

- What: Stop JevAgent on every timeout, malformed response, provider 5xx, or authorization error.
- Why rejected: Existing Jev capabilities are advisory during transient outages. This change makes access/configuration denials explicit while preserving resilience during infrastructure failures.

### Alternative 4: Keep direct TypeSafe mode configurable through JevAgent

- What: Continue accepting a direct TypeSafe `DecisionModelConfig` in `JevRuntimeSettings`.
- Why rejected: This leaves an ordinary supported JevAgent configuration that bypasses Vidbyte API-key authorization and wallet billing. Direct runner BYOK remains available outside JevAgent, while server-side authorization stays authoritative for calls that reach Vidbyte.
