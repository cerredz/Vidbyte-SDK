# Design Doc: Require Vidbyte-Managed Decisions in JevAgent

**Status:** Draft  
**Author:** Codex  
**Created:** 2026-09-29  
**Last Updated:** 2026-09-29

---

## 1. Overview

Close the supported direct-provider escape hatch on the `JevAgent` configuration surface. `JevRuntimeSettings` will accept only `DecisionModelMode.VIDBYTE_MANAGED`; passing a direct TypeSafe `DecisionModelConfig` will fail during settings construction, before any Jev policy or agent run starts. The general-purpose `DecisionModelConfig` and `DecisionModelRunner` retain direct TypeSafe BYOK for standalone decision-model use.

This hardening follow-up narrows the original managed-gateway change after a final audit found that its explicit direct mode made the ordinary `JevAgent` API easy to route around. It does not claim that a package installed on a caller-controlled machine can prevent that caller from editing code or making unrelated outbound HTTP requests.

---

## 2. Goals & Non-Goals

### Goals

- Make Vidbyte-managed mode the only supported decision mode accepted by `JevRuntimeSettings`.
- Reject both implicit direct configuration (`DecisionModelConfig()`) and explicit `DecisionModelMode.TYPESAFE` configuration at settings construction.
- Keep the rejection local, deterministic, and free of credential resolution or network calls.
- Preserve direct TypeSafe access for standalone `DecisionModelRunner` consumers that are not using `JevAgent`.
- Update SDK examples and public Jev guidance so they do not show direct TypeSafe mode as a supported `JevAgent` configuration.
- Add a focused test and verification command for the managed-only runtime invariant.

### Non-Goals

- Remove the TypeSafe provider, `DecisionModelMode.TYPESAFE`, or standalone `DecisionModelRunner` BYOK behavior.
- Prevent a developer who owns an application from modifying the SDK, implementing another runtime, or calling TypeSafe directly outside `JevAgent`.
- Change System 1 generative providers, tool permissions, feature flags, or whether individual Jev policies are enabled for a run.
- Change the existing fail-open behavior for transient managed gateway/service failures. Managed credentials and gateway access denials remain fail-closed as implemented in the gateway PR.
- Change Vidbyte API authentication, billing, scopes, quotas, or lifecycle rules.

---

## 3. Background & Context

The managed-gateway SDK change makes `JevRuntimeSettings()` use a pinned Vidbyte endpoint and `VIDBYTE_API_KEY`. It also keeps `DecisionModelConfig()` defaulted to direct TypeSafe so standalone decision runners retain their current behavior. However, `JevRuntimeSettings` exposes a public `decision` field, and any caller can currently pass `DecisionModelConfig()` or an explicit `DecisionModelMode.TYPESAFE` to send Jev decisions directly to TypeSafe.

That path is useful for a standalone decision runner, but it conflicts with the product requirement that supported `JevAgent` decisions authenticate and bill through Vidbyte. A default alone is not enough when the SDK exposes a one-line configuration override for direct Jev execution.

The right boundary is the `JevRuntimeSettings` constructor. It already validates the decision config and feature settings before `JevAgent` builds its runtime collaborators. Enforcing the mode there blocks both accidental and intentional use of a direct config through the supported JevAgent API without changing the standalone runner.

---

## 4. Requirements

### Functional Requirements

1. `JevRuntimeSettings()` continues to construct with the Vidbyte-managed decision config.
2. `JevRuntimeSettings(decision=DecisionModelConfig())` raises `ConfigurationError` because the standalone config defaults to direct TypeSafe mode.
3. `JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.TYPESAFE))` raises the same actionable `ConfigurationError`.
4. A Vidbyte-managed config, whether defaulted or explicitly supplied, remains accepted.
5. Rejection occurs before credential lookup, runner construction, or outbound traffic.
6. `DecisionModelConfig()` and `DecisionModelRunner(DecisionModelConfig())` remain direct TypeSafe for standalone consumers.
7. JevAgent examples and skills show managed configuration only; direct BYOK documentation identifies `DecisionModelRunner` as a separate primitive.
8. The policy does not claim that modified local client code or unrelated direct provider calls can be blocked by the package.

### Non-Functional Requirements

- Security: no supported direct-provider override remains on JevAgent's public settings path.
- Compatibility: only JevAgent callers that explicitly selected direct TypeSafe mode are affected; standalone direct runner behavior remains unchanged.
- Reliability: mode rejection is immediate and deterministic, independent of environment variables or gateway availability.
- Performance: one enum identity check during settings construction; no network or credential work is added.
- Diagnostics: the error names the required mode and states that direct BYOK is available only through the standalone runner.

---

## 5. High-Level Design

Add a mode check to `JevRuntimeSettings.__post_init__` immediately after verifying that `decision` is a `DecisionModelConfig`. If the mode is not `VIDBYTE_MANAGED`, raise `ConfigurationError`. Leave `DecisionModelConfig` resolution rules untouched so standalone use remains compatible.

```text
JevAgent(..., JevRuntimeSettings())
                    |
                    v
       VIDBYTE_MANAGED decision config
                    |
                    v
             Vidbyte gateway

JevAgent(..., JevRuntimeSettings(decision=DecisionModelConfig()))
                    |
                    v
       ConfigurationError at construction

DecisionModelRunner(DecisionModelConfig())
                    |
                    v
          Direct TypeSafe BYOK remains
```

The policy check does not inspect or resolve API-key values. For managed settings, `VIDBYTE_API_KEY` is still resolved only when an enabled policy invokes the decision runner.

---

## 6. Detailed Design

### 6.1 Runtime settings validation

**File:** `vidbyte/agents/jev/settings.py`  
**Type:** Modified

After validating the `DecisionModelConfig` type, check its `mode` by enum identity. Accept only `DecisionModelMode.VIDBYTE_MANAGED`. Raise an error similar to:

```text
JevRuntimeSettings requires VIDBYTE_MANAGED decision mode. Direct TypeSafe mode is available only through DecisionModelRunner.
```

The message must not suggest that setting `TYPESAFE_API_KEY` can satisfy JevAgent. It must not include any key value. Keep the standalone config's default as `DecisionModelMode.TYPESAFE`.

### 6.2 Credential and failure behavior

The construction-time mode check is distinct from runtime credential checks:

- Direct mode supplied to JevAgent: reject immediately with `ConfigurationError`.
- Managed mode with a missing or malformed Vidbyte key: keep the existing typed configuration failure and fail-closed Jev policy behavior.
- Managed gateway 401/402/403/429: keep the existing fail-closed behavior.
- Managed timeouts, connection errors, provider 5xx, and malformed decision responses: retain current advisory/fail-open behavior for Jev features.
- Standalone direct `DecisionModelRunner`: retain current TypeSafe key, endpoint, and error behavior.

This follow-up closes a selectable provider route. It does not turn advisory Jev capabilities into security authorization or make the installed SDK tamper-proof.

### 6.3 Tests and examples

Add a test that constructs the two direct config forms and asserts the same construction-time rejection. Add a positive assertion that managed mode remains accepted. Preserve existing standalone direct provider tests. Migrate JevAgent tests that currently use direct-mode configs to explicit synthetic managed configs with fake decision runners; tests that directly instantiate `JevRunState` or `JevPreflightTools` may continue to exercise lower-level direct behavior where that is the subject under test.

Update `skills/jev-agent/SKILL.md` to remove instructions for configuring a direct TypeSafe decision on `JevRuntimeSettings`. Keep one clear boundary note: direct BYOK remains available through standalone `DecisionModelRunner`, which does not construct or run `JevAgent`.

---

## 7. Data Model Changes

No new types or persistent fields. The closed `DecisionModelMode` enum and standalone `DecisionModelConfig` remain unchanged. `JevRuntimeSettings` narrows the accepted value of its existing `decision` field to `VIDBYTE_MANAGED`.

---

## 8. API Changes

`JevRuntimeSettings` now rejects direct TypeSafe configurations. Example rejected forms:

```python
JevRuntimeSettings(decision=DecisionModelConfig())
JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.TYPESAFE))
```

Managed Jev configuration remains:

```python
JevRuntimeSettings(preflight=(JevPreflightPreset.CLARITY,))
```

Standalone direct configuration remains:

```python
DecisionModelRunner(DecisionModelConfig())
```

### Migration

Applications that pass a direct TypeSafe config into JevAgent must create a Vidbyte live API key with `models:invoke`, fund its owner wallet as needed, and configure `VIDBYTE_API_KEY`. Applications that only use `DecisionModelRunner` directly require no change.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-agent-managed-only-decisions.md` | Record the strict runtime policy before implementation. |
| MODIFY | `docs/design/jev-managed-gateway-credentials.md` | Link the follow-up as the final JevAgent mode policy. |
| MODIFY | `vidbyte/agents/jev/settings.py` | Reject direct decision configs for JevAgent. |
| MODIFY | `tests/test_jev_managed_gateway.py` | Cover rejected direct configs and accepted managed config. |
| MODIFY | `tests/test_jev_agent.py` | Assert settings construction enforces the managed-only mode. |
| MODIFY | `tests/test_jev_preflight.py` | Use managed fake configs for JevAgent integration cases. |
| MODIFY | `tests/test_jev_done.py` | Replace direct-mode JevAgent fixtures with managed fake configs; retain standalone direct tests. |
| MODIFY | `skills/jev-agent/SKILL.md` | Remove the supported direct TypeSafe JevAgent setup. |
| CREATE | `scripts/test-jev-agent-managed-only.py` | Provide focused verification of the new invariant. |

---

## 10. Testing Plan

### Unit Tests

- Default `JevRuntimeSettings()` accepts managed mode. [Edge Case]
- Passing implicit direct mode is rejected. [Hidden Failure]
- Passing explicit TypeSafe mode is rejected. [Hidden Assumption]
- Standalone `DecisionModelConfig()` remains direct. [Compatibility]
- Standalone direct `DecisionModelRunner` tests continue to pass. [Compatibility]
- Rejection does not resolve `VIDBYTE_API_KEY` or `TYPESAFE_API_KEY` and does not make network calls. [Silent Failure]
- Error text names the supported Jev mode without including key values. [Sensitive Data]

### Integration Tests

- Construct JevAgent with managed defaults and exercise existing fake-runtime Jev tests.
- Assert direct configs cannot be passed to either enabled or empty-policy JevAgent settings.
- Keep transport tests that prove managed calls target Vidbyte and standalone direct calls target TypeSafe.

### Focused Verification

`python scripts/test-jev-agent-managed-only.py` runs the new rejection/acceptance contract, prints PASS/FAIL, prints a final `X/Y tests passed`, and exits non-zero on collection, skip, or assertion failure.

### Full SDK Verification

Run `python scripts/run_ci.py --stage all`, `python lint/run.py`, and the typed boundary Semgrep check before merging. No live API key is needed; all credentials in tests are synthetic.

---

## 11. Dependencies & External Services

| Dependency | Purpose | Risk |
|------------|---------|------|
| Managed-gateway SDK change in PR #481 | Provides the pinned endpoint and managed decision mode. | This change should be reviewed with, or after, the gateway change because its enum is introduced there. |
| `DecisionModelMode` | Closed mode selector for standalone and managed decision configs. | Mode names must remain enum values; no string-only bypass is allowed. |
| No external service | Construction validation only. | Tests remain deterministic and network-free. |

---

## 12. Rollout & Deployment

- This is an SDK configuration restriction; there is no backend migration or feature flag.
- Keep the change in the same draft SDK PR as managed gateway mode, then publish both together.
- Update public product documentation to state that JevAgent accepts only managed mode and that standalone DecisionModelRunner retains direct BYOK.
- Existing JevAgent direct-BYOK callers must migrate before upgrading; construction errors provide the required mode in the message.
- Rollback is an SDK revert; the Vidbyte API remains the authority for requests it receives.

---

## 13. Open Questions

- [ ] Confirm the exact migration guidance and wording with the API key settings UI's `models:invoke` label before publishing the package.
- [ ] Decide whether a future major version should remove the public `decision` field from `JevRuntimeSettings` entirely; this change retains it for managed key injection and testability.

---

## 14. Alternatives Considered

### Alternative 1: Keep direct TypeSafe as an explicit JevAgent override

- What: Preserve `JevRuntimeSettings(decision=DecisionModelConfig(mode=TYPESAFE))`.
- Why rejected: It leaves a first-party, one-line supported bypass of Vidbyte authentication and billing, contrary to the hardening requirement.

### Alternative 2: Change all `DecisionModelConfig` instances to managed by default

- What: Change the general config default to Vidbyte-managed.
- Why rejected: It would break standalone `DecisionModelRunner` consumers and unrelated low-level integrations. The restriction belongs at the JevAgent settings boundary.

### Alternative 3: Remove standalone direct TypeSafe support entirely

- What: Delete direct TypeSafe mode and the direct provider runner.
- Why rejected: The requirement targets JevAgent's supported decision route. Standalone BYOK remains a separate library use case and does not make JevAgent's own decision path direct.

### Alternative 4: Claim the SDK can prevent all direct provider calls

- What: Treat the mode check as a boundary against arbitrary code running on the customer's machine.
- Why rejected: Client-side package code can be modified or bypassed. This change closes the supported JevAgent configuration path and relies on the Vidbyte backend for every request that reaches Vidbyte.
