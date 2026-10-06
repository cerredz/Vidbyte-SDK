# Design Doc: Session String Discovery Helpers

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

Add developer-facing string aliases and discovery helpers directly on `Session` for the string-backed constructor options it already accepts. Today `Session(policy=...)`, `Session.resume(policy=...)`, and `Session(..., trace=...)` accept raw strings through `CheckpointPolicy` and `TraceCapture`, but developers have to know or find those strings elsewhere. This change makes the hard strings discoverable with helpers such as `Session.policy_options()` and usable directly as constants such as `Session.PER_TURN_POLICY`.

---

## 2. Goals & Non-Goals

### Goals

- Expose every hard string setting currently accepted by the `Session` public API for `policy` and `trace`.
- Add class-level string constants on `Session`, including `Session.PER_TURN_POLICY`, so callers can pass constants instead of memorized strings.
- Add helper methods inside `Session` for discovering supported string options by parameter family.
- Preserve existing enum exports: `CheckpointPolicy` and `TraceCapture` remain the canonical typed contracts.
- Update SDK docs so examples show both enum and `Session.<CONSTANT>` usage.

### Non-Goals

- No new checkpoint policies, trace modes, store behavior, persistence behavior, or session lifecycle behavior.
- No migration from enums to strings; constants are ergonomic aliases only.
- No changes to `SessionStore`, serializer payloads, checkpoint schema, portable bundles, or provider stores.
- No test files in this no-tests workflow; implementation validation will use lightweight import/compile checks.

---

## 3. Background & Context

`vidbyte-sdk` is a Python 3.11+ SDK packaged with setuptools and Pydantic/httpx dependencies. The relevant session package exists on `main` under `vidbyte/sessions/`, even though the current checkout branch `feat/context-minimal-fanout-trace` does not contain it in the active working tree. The implementation target should therefore be a fresh worktree from `main`, where `vidbyte/sessions/session.py`, `vidbyte/lib/dataclasses/sessions.py`, `skills/sessions.md`, `README.md`, and `llms.txt` are present.

The session constructor currently accepts two families of hard string options:

- `policy: CheckpointPolicy | str`, with values `per_turn`, `per_step`, and `manual`.
- `trace: TraceCapture | str`, with values `off`, `auto`, `artifact`, and `full`.

Those values are defined in `vidbyte/lib/dataclasses/sessions.py` as `CheckpointPolicy` and `TraceCapture`, then re-exported through `vidbyte.sessions.contracts`, `vidbyte.sessions`, and root `vidbyte`. This is type-safe for developers who import the enums, but it does not satisfy the discoverability need in the request: a developer looking only at the `Session` class cannot see which string values are accepted, and raw strings are easy to mistype.

---

## 4. Requirements

### Functional Requirements

1. `Session` must expose class-level string constants for every `CheckpointPolicy` option:
   - `Session.PER_TURN_POLICY == "per_turn"`
   - `Session.PER_STEP_POLICY == "per_step"`
   - `Session.MANUAL_POLICY == "manual"`
2. `Session` must expose class-level string constants for every `TraceCapture` option:
   - `Session.OFF_TRACE == "off"`
   - `Session.AUTO_TRACE == "auto"`
   - `Session.ARTIFACT_TRACE == "artifact"`
   - `Session.FULL_TRACE == "full"`
3. `Session.policy_options()` must return all supported policy strings in stable declaration order.
4. `Session.trace_options()` must return all supported trace strings in stable declaration order.
5. `Session.string_options()` must return a mapping from parameter names to option tuples, at minimum `{"policy": (...), "trace": (...)}`.
6. `Session.describe_string_options()` must return a compact, developer-readable mapping that lets callers inspect the hard strings without reading source.
7. `Session.__init__`, `Session.resume`, and `Session.fork_from` must continue accepting existing enum instances and raw string values unchanged.
8. Invalid strings must continue failing through existing enum coercion, with no new validation path or changed exception behavior.
9. Existing public import paths must remain unchanged; callers can use `from vidbyte import Session` and then `Session.PER_TURN_POLICY`.
10. Documentation must show at least one constructor example using `Session.PER_TURN_POLICY` for `policy=`.

### Non-Functional Requirements

- **Performance:** helpers are constant-time class-level lookups over tiny enum sets.
- **Scalability:** N/A - no storage, network, or data volume behavior changes.
- **Security:** no new persisted data and no new secret surface.
- **Observability:** N/A - this is public API discoverability, not runtime telemetry.
- **Reliability:** constants must derive from enum `.value` fields so they cannot drift from accepted runtime values.

---

## 5. High-Level Design

Modify only the public `Session` facade and documentation. `CheckpointPolicy` and `TraceCapture` remain the source of truth. `Session` gains class variables whose values are assigned from the enum values, plus classmethod helpers that return immutable tuples or simple dictionaries of those values.

This keeps the change low-risk: constructor coercion remains exactly where it is today (`CheckpointPolicy(policy)` and `TraceCapture(trace)`), and the new constants do not introduce new accepted states. The helpers sit where the developer expects to discover them: inside the `Session` class itself.

```text
Developer
  |
  | uses policy=Session.PER_TURN_POLICY
  v
Session class constants  ->  CheckpointPolicy.PER_TURN.value
  |
  | existing __init__ coercion
  v
CheckpointPolicy(policy) -> existing runtime behavior
```

Docs will be updated in `skills/sessions.md`, `README.md`, and `llms.txt` to advertise the discoverability helpers without changing the existing enum-first guidance.

---

## 6. Detailed Design

### 6.1 `Session` Constants and Helpers

**File(s):** `vidbyte/sessions/session.py`
**Type:** Modified

#### What it does

Adds discoverable public aliases and helper classmethods to the existing `Session` class. The class remains the durable wrapper; these additions are API ergonomics only.

#### Interface / API

```python
class Session:
    PER_TURN_POLICY: ClassVar[str] = CheckpointPolicy.PER_TURN.value
    PER_STEP_POLICY: ClassVar[str] = CheckpointPolicy.PER_STEP.value
    MANUAL_POLICY: ClassVar[str] = CheckpointPolicy.MANUAL.value

    OFF_TRACE: ClassVar[str] = TraceCapture.OFF.value
    AUTO_TRACE: ClassVar[str] = TraceCapture.AUTO.value
    ARTIFACT_TRACE: ClassVar[str] = TraceCapture.ARTIFACT.value
    FULL_TRACE: ClassVar[str] = TraceCapture.FULL.value

    @classmethod
    def policy_options(cls) -> tuple[str, ...]:
        # Return accepted strings for the policy= parameter.

    @classmethod
    def trace_options(cls) -> tuple[str, ...]:
        # Return accepted strings for the trace= parameter.

    @classmethod
    def string_options(cls) -> dict[str, tuple[str, ...]]:
        # Return accepted string options grouped by Session parameter name.

    @classmethod
    def describe_string_options(cls) -> dict[str, dict[str, str]]:
        # Return named Session string constants grouped by parameter name.
```

Example usage:

```python
session = Session(agent, policy=Session.PER_TURN_POLICY, trace=Session.AUTO_TRACE)

print(Session.policy_options())
print(Session.string_options()["trace"])
```

#### Logic / Algorithm

1. Import `ClassVar` from `typing`.
2. Define the constants near the top of the `Session` class, before `__init__`.
3. Assign every constant from the corresponding enum `.value`.
4. Implement `policy_options()` by returning `(cls.PER_TURN_POLICY, cls.PER_STEP_POLICY, cls.MANUAL_POLICY)`.
5. Implement `trace_options()` by returning `(cls.OFF_TRACE, cls.AUTO_TRACE, cls.ARTIFACT_TRACE, cls.FULL_TRACE)`.
6. Implement `string_options()` as a parameter-name map over the two helper methods.
7. Implement `describe_string_options()` as a grouped mapping from constant names to string values, for easy introspection in notebooks, shells, docs generators, and agents.

#### Edge Cases & Error Handling

- If enum values ever change, constants follow because they are assigned from enum values.
- Invalid caller input still fails in the existing `CheckpointPolicy(policy)` / `TraceCapture(trace)` coercion path.
- The helper methods return new tuples/dicts so callers cannot mutate shared class state.

### 6.2 Sessions Skill Documentation

**File(s):** `skills/sessions.md`
**Type:** Modified

#### What it does

Documents the new constants and helper methods where SDK agents and developers already read durable session guidance.

#### Interface / API

```markdown
session = Session(agent, policy=Session.PER_TURN_POLICY, trace=Session.AUTO_TRACE)
Session.policy_options()
Session.trace_options()
Session.string_options()
Session.describe_string_options()
```

#### Logic / Algorithm

1. Add a short section after the attach or verbs section.
2. Show constants for `policy`.
3. Show helpers for discovering supported values.
4. Keep existing enum examples valid.

#### Edge Cases & Error Handling

- Docs must not imply that constants are required; raw strings and enums remain accepted.
- Docs must not introduce new strings beyond the enum values currently accepted.

### 6.3 README Durable Sessions Section

**File(s):** `README.md`
**Type:** Modified

#### What it does

Updates public README examples so package users can discover the new `Session` class constants.

#### Interface / API

```python
session = Session(agent, store=store, policy=Session.PER_TURN_POLICY)
```

#### Logic / Algorithm

1. Add one sentence to the Durable Sessions section explaining `Session.policy_options()` and `Session.trace_options()`.
2. Update or add one example using `Session.PER_TURN_POLICY`.

#### Edge Cases & Error Handling

- Keep README concise; do not duplicate the full skill documentation table.
- Preserve the existing explanation that `CheckpointPolicy` and `TraceCapture` are still available.

### 6.4 LLM-Facing SDK Summary

**File(s):** `llms.txt`
**Type:** Modified

#### What it does

Updates the compact SDK summary so models and generated assistants know the hard strings are discoverable from `Session`.

#### Interface / API

```text
Use Session.PER_TURN_POLICY or Session.policy_options() for durable-session policy strings.
Use Session.AUTO_TRACE or Session.trace_options() for trace capture strings.
```

#### Logic / Algorithm

1. Edit the Durable Sessions subsection.
2. Mention both constant and helper forms.
3. Keep wording short and aligned with the file's summary style.

#### Edge Cases & Error Handling

- Avoid making `llms.txt` the source of truth; it should point to the class helpers and enums.

---

## 7. Data Model Changes

N/A - this change adds public class constants and helper methods only. No dataclasses, schemas, checkpoint payloads, metadata, store rows, portable bundles, or migrations change.

---

## 8. API Changes

### 8.1 `Session` Python Class API

**Change type:** Modified

**Request:**

```python
Session(agent, policy=Session.PER_TURN_POLICY, trace=Session.AUTO_TRACE)
Session.policy_options()
Session.trace_options()
Session.string_options()
Session.describe_string_options()
```

**Response:**

```python
("per_turn", "per_step", "manual")
("off", "auto", "artifact", "full")
{"policy": ("per_turn", "per_step", "manual"), "trace": ("off", "auto", "artifact", "full")}
{
    "policy": {"PER_TURN_POLICY": "per_turn", "PER_STEP_POLICY": "per_step", "MANUAL_POLICY": "manual"},
    "trace": {"OFF_TRACE": "off", "AUTO_TRACE": "auto", "ARTIFACT_TRACE": "artifact", "FULL_TRACE": "full"},
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid strings continue to raise through existing enum coercion. |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/session-string-discovery.md` | Approval-gated design doc for this change. |
| MODIFY | `vidbyte/sessions/session.py` | Add `Session` class constants and discovery helpers. |
| MODIFY | `skills/sessions.md` | Document constants and helper methods for durable-session users. |
| MODIFY | `README.md` | Add public README mention and example. |
| MODIFY | `llms.txt` | Update LLM-facing SDK summary with discoverability surface. |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| N/A | N/A | No new dependency or external service. | N/A |

---

## 11. Rollout & Deployment

- No feature flag is needed.
- This is additive and backward-compatible.
- Package rollout follows the normal SDK release flow.
- Rollback is a small revert of the constants/helpers and doc updates; no stored data is affected.

---

## 12. Open Questions

- [ ] Should trace constants use the shorter names in this doc (`AUTO_TRACE`) or more explicit names such as `AUTO_TRACE_CAPTURE`? Recommendation: use `AUTO_TRACE` for concise parity with `trace=`.
- [ ] Should `describe_string_options()` return a dict, as designed, or a formatted string? Recommendation: return a dict because it is programmatically inspectable and easy to print.

---

## 13. Alternatives Considered

### Alternative 1: Only Document The Existing Enums

- What: Tell users to import `CheckpointPolicy` and `TraceCapture`.
- Why rejected: The request specifically asks for helper functions inside `Session` and constants such as `Session.PER_TURN_POLICY`.

### Alternative 2: Move The Strings Into New Session-Specific Enums

- What: Create new enums or constants separate from `CheckpointPolicy` and `TraceCapture`.
- Why rejected: It would duplicate the current source of truth and create drift risk. Assigning constants from existing enum values is simpler and safer.

### Alternative 3: Accept Only Constants And Deprecate Raw Strings

- What: Tighten the API so callers must pass enum members or new constants.
- Why rejected: It would be a breaking change with no runtime benefit. The current string acceptance is useful and should remain.
