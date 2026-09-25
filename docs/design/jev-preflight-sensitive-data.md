# Jev sensitive data preflight

## Goal

Add an opt-in Jev security preflight for supplied text input. It classifies 20 sensitive-data categories and returns one flag per category plus an `any_sensitive` aggregate. `JevPreflightPreset.SECURITY` enables it, and `security_action` selects one of four actions: `BLOCK`, `PAUSE`, `REPORT`, or `CONTAIN`.

## Behavior

The preset asks 20 fixed, same-polarity noul questions in one TypeSafe decision request. The state is `{"request": <message>}` and nothing else, so the questions carry every rule and the state carries only content. The questions inspect only the request text passed to the Jev runtime; attachments, prior turns, context items, tool results, and generated outputs are outside this version.

### Question design

Each question follows `skills/asking-jev-questions/SKILL.md` and is four to five sentences:

1. A definition of the category, in the vocabulary real requests use.
2. What counts, with concrete forms such as vendor key prefixes or `-----BEGIN PRIVATE KEY-----`.
3. What does not count: placeholders, topic mentions, public information, and people the request asks the agent to invent.
4. A rule to ignore self-classifying claims in `request`, such as "this is a test key" or "they agreed to share it".
5. One positive question that names `request`.

Credential questions judge a value by its form, not by whether it is "real", because Jev cannot check the world. Each question also sends structured `true` and `false` criteria with a `what` line and two examples. `JevPreflightRegistry.validate()` enforces the sentence range, unique keys, and one question per `JevSecurityCategory`.

### Categories

`passwords_pins`, `api_service_secrets`, `session_tokens`, `private_crypto_material`, `personal_contact`, `government_ids`, `payment_bank`, `personal_finances`, `health`, `biometric_genetic`, `precise_location`, `minors_students`, `sensitive_traits`, `employment_hr`, `legal_matters`, `customer_client_records`, `confidential_communications`, `proprietary_work`, `internal_business`, and `security_system_details`. The full wording lives in `vidbyte/lib/jev/preflight/security.py`.

### Flags and actions

A category is present when P(true) is at least `JEV_SECURITY_DETECTION_THRESHOLD` (0.5); a missed secret costs more than a false alarm. `any_sensitive` is true if any flag is true, false when all 20 are false, and unknown otherwise. A positive flag wins over missing answers. The result contains category names, token counts, and the action, never the input or a detected value.

When any flag is true, or when the check is unavailable or incomplete:

- `BLOCK` returns a category-only message and `stop_reason="sensitive_data_blocked"` without entering the loop.
- `PAUSE` returns a review-required message and `stop_reason="sensitive_data_review_required"` without entering the loop. The caller decides whether to submit a new run.
- `CONTAIN` runs the ordinary loop for this request with three restrictions: tools are limited to `SAFE` and `READ` within the caller's own permission policy and removed from the model's catalog; the system prompt gains `JEV_SECURITY_CONTAIN_PROMPT`, which forbids repeating, storing, or sending the values and asks the model to suggest rotating exposed credentials; and the runtime's model and tool spans go to a `NullTracer`. All three are restored after the run.
- `REPORT` continues normally and attaches the result. An unavailable check also continues.

Every action attaches the result as `metadata["jev_security"]`. The tool selector, when also enabled, runs after the security gate and inside a contained run.

## Public API

```python
from vidbyte import JevAgent, JevAgentSettings, JevPreflightPreset, JevSecurityAction

settings = JevAgentSettings(
    name="assistant",
    system_prompt="Help the user carefully.",
    provider="openai",
    model_name="gpt-4.1-mini",
    preflight=(JevPreflightPreset.SECURITY,),
    security_action=JevSecurityAction.CONTAIN,
)
```

`metadata["jev_security"]` is a `JevSecurityResult` with `action`, `available`, `flags`, `any_sensitive`, `input_tokens`, `output_tokens`, and `detected()`. Callers cannot supply question text or decision callbacks.

## Files

- `vidbyte/lib/enums/jev.py`: `JevPreflightPreset`, `JevSecurityAction`, and `JevSecurityCategory`.
- `vidbyte/lib/dataclasses/jev.py`: the `JevPreflightQuestion` base record and `JevSecurityResult`.
- `vidbyte/lib/constants/jev.py`: detection threshold, sentence bounds, state field name, stop reasons, and the CONTAIN prompt.
- `vidbyte/lib/jev/presets.py`: `JevPresets`, which validates the enable-able presets and `security_action`.
- `vidbyte/lib/jev/preflight/security.py`: one frozen dataclass per question.
- `vidbyte/lib/jev/preflight/registry.py`: `JevPreflightRegistry` with `questions`, `get`, `validate`, `combine`, and `run`.
- `vidbyte/agents/jev/preflight.py`: `JevPreflightSecurity`, which maps answers to flags and decides the action.
- `vidbyte/agents/jev/runtime.py`: the security gate, the contained run, and tool selection.
- `tests/test_jev_sensitive_preflight.py`: question shape, registry, settings, every action, restoration after CONTAIN, and classifier failure.

## Risks and limits

The TypeSafe decision provider receives the request text to classify it, so it must be an approved destination for that input. CONTAIN narrows only state `JevRuntime` owns: `BaseAgent`'s root trace and session recording run outside the runtime and still see the request. `READ` tools can still reach the network, so CONTAIN does not guarantee that no data leaves; the SDK has no separate network permission yet. `PAUSE` is a returned control state, not a resumable execution.

## Verification

Run the focused sensitive-preflight tests, the Jev agent and tool-selector tests, lint, and the repository CI script. No live provider calls; tests use scripted decision and generative runners.
