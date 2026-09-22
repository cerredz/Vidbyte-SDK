# Jev sensitive data preflight

## Goal

Add an opt-in Jev security preflight for supplied text input. It classifies 20 distinct sensitive-data categories and exposes one boolean flag per category plus an `any_sensitive` aggregate in the run response. `Preset.Security(on_detected=...)` selects one of three actions: `BLOCK`, `PAUSE`, or `REPORT`.

## Behavior

The security preset asks 20 fixed, same-polarity NOUL questions in one TypeSafe decision request. Every question takes three sentences: a direct question, a scope rule for what counts, and a rule that excludes topic mentions or obvious placeholders. The questions inspect only the request text passed to the Jev runtime; attachments, prior turns, context items, tool results, and generated outputs are outside this first version.

### Fixed questions

Each question is evaluated independently against the supplied request text. `true` means that category is present.

1. **`passwords_pins`** — Does the request contain a real or plausibly real password, passphrase, or PIN? Count values that appear usable to sign in or unlock a private resource, even when they are embedded in a longer example. Do not count instructions that merely discuss passwords or clearly fake placeholders such as `YOUR_PASSWORD`.
2. **`api_service_secrets`** — Does the request contain an API key, service token, client secret, or database credential? Count values that could grant access to an account, service, or data store, including values labeled as examples when they look usable. Do not count variable names, instructions to create credentials, or obvious placeholder strings.
3. **`session_tokens`** — Does the request contain a session cookie, access token, refresh token, or authentication code? Count bearer values, cookie contents, and one-time codes that could authenticate a person or application. Do not count protocol descriptions or visibly fabricated token placeholders.
4. **`private_crypto_material`** — Does the request contain a private key, recovery phrase, seed phrase, signing secret, or equivalent cryptographic material? Count content that could decrypt, sign, or restore access to protected data or accounts. Do not count public keys, public wallet addresses, or general cryptography discussion.
5. **`personal_contact`** — Does the request identify a private person through their name together with an email address, phone number, or home address? Count contact details tied to a real or plausibly real individual, including details in pasted correspondence or records. Do not count public business contact pages or fictional examples clearly marked as such.
6. **`government_ids`** — Does the request contain a government-issued identity number or a readable image transcription of an identity document? Count passport, national identity, tax identity, or driver's license details tied to a person. Do not count instructions about these documents or a masked value that cannot identify or authenticate anyone.
7. **`payment_bank`** — Does the request contain payment card data, bank account details, or credentials for a payment account? Count full or partially exposed account details when they remain useful for identifying, accessing, or charging the account. Do not count general payment instructions or clearly fictional test values.
8. **`personal_finances`** — Does the request contain a person's nonpublic income, tax, credit, debt, or investment information? Count records or values tied to an identifiable or plausibly identifiable individual. Do not count public market data, generic financial examples, or business financials that do not identify a private person.
9. **`health`** — Does the request contain an identifiable person's medical history, diagnosis, treatment, prescription, or health record? Count information that connects a person to a health condition, care episode, or treatment. Do not count general health questions without private patient details.
10. **`biometric_genetic`** — Does the request contain biometric identifiers or genetic information about an identifiable person? Count face, voice, fingerprint, iris, DNA, or similar measurements when they could identify a person or reveal inherited traits. Do not count general discussion of biometric systems or non-identifying synthetic examples.
11. **`precise_location`** — Does the request reveal a person's precise current location, private travel plans, or location history? Count details that could locate or track a person beyond a broad public region. Do not count public venue addresses or general travel recommendations.
12. **`minors_students`** — Does the request contain identifiable information about a minor or a student's nonpublic education record? Count names or identifiers paired with school, grades, attendance, support plans, discipline, or other private student details. Do not count generic classroom examples or public school information without private student data.
13. **`sensitive_traits`** — Does the request reveal a private person's nonpublic religious, political, sexual, or similarly sensitive personal traits? Count the trait when it is linked to an identifiable or plausibly identifiable individual. Do not count public statements made in a public role or abstract discussion of these topics.
14. **`employment_hr`** — Does the request contain a private personnel record, performance review, salary, disciplinary matter, or hiring decision? Count nonpublic information linked to an employee, candidate, or identifiable worker. Do not count general HR templates or public job descriptions.
15. **`legal_matters`** — Does the request contain confidential legal advice, privileged communications, or private case information? Count nonpublic details tied to a client, party, witness, or active matter. Do not count public court filings or general legal questions without private case facts.
16. **`customer_client_records`** — Does the request contain nonpublic records about identifiable customers, clients, or patients? Count account, transaction, support, usage, or service details that can be tied to an individual or customer organization. Do not count aggregated statistics that do not reveal a specific record.
17. **`confidential_communications`** — Does the request contain private correspondence, a confidential agreement, or negotiation details? Count nonpublic messages or terms shared with an expectation of limited access, including quoted excerpts. Do not count published announcements or generic contract examples.
18. **`proprietary_work`** — Does the request contain nonpublic source code, research, designs, formulas, or other proprietary work product? Count material that appears owned by a person or organization and not intended for public release. Do not count public open-source code or general technical questions.
19. **`internal_business`** — Does the request contain nonpublic business plans, pricing, forecasts, financial results, or acquisition plans? Count material whose disclosure could reveal an organization's private commercial position. Do not count published investor information or generic planning templates.
20. **`security_system_details`** — Does the request contain private infrastructure details, vulnerability information, incident records, or security controls whose disclosure could expose a system? Count exploitable configurations, active weaknesses, or nonpublic incident facts. Do not count general defensive guidance or already-public advisories without private system details.

Each answer maps directly to a named flag. `any_sensitive` is true if any flag is true, false when all 20 are false, and unknown when the decision request is unavailable or incomplete and no positive flag is known. A positive flag wins over missing answers. The response contains category names and decision evidence, never a copy of the input or the detected values.

When any flag is true, `BLOCK` returns a safe summary naming the detected categories and does not enter the generative loop. `PAUSE` returns a review-required result with the same category summary and does not enter the loop; the caller can decide whether to submit a new run. `REPORT` continues into the ordinary loop and attaches the security result to response metadata. For `BLOCK` and `PAUSE`, a failed or incomplete classifier also stops the run; `REPORT` records an unavailable result and continues. Error messages do not include input text, TypeSafe response bodies, or detected values.

The preset is opt-in through Jev settings. Public configuration stays named and closed: `Preset.Security` owns `on_detected`; callers cannot supply question text or custom decision callbacks. Existing runs with no security preset make no decision-model request.

## Public API

```python
from vidbyte import JevAgent, JevAgentSettings, Preset, SecurityAction

settings = JevAgentSettings(
    name="assistant",
    system_prompt="Help the user carefully.",
    provider="openai",
    model_name="gpt-4.1-mini",
    preflight=(Preset.Security(on_detected=SecurityAction.BLOCK),),
)
```

`JevResponse.results["security"]` exposes `available`, `flags`, and `any_sensitive`. Blocked and paused responses also carry a stable stop reason and category-only message. `REPORT` returns the usual agent output and includes the same result in its metadata.

## Files

- `vidbyte/agents/jev/presets.py`: fixed questions, `Preset.Security`, action enum, and registry definition.
- `vidbyte/agents/jev/response.py`: typed security result and run response.
- `vidbyte/agents/jev/settings.py`, `runtime.py`, and package exports: validate and execute the opt-in policy.
- `tests/test_jev_sensitive_preflight.py`: question shape, settings validation, each action, aggregate flags, and classifier failure behavior.
- `README.md` and `skills/jev-agent/SKILL.md`: document the public API and its limits.

## Risks and limits

The TypeSafe decision provider receives the supplied request text to classify it. Users must treat that provider as an approved destination for the input. This preflight does not yet classify attachments, context, outputs, or tool data, and its flags do not yet alter external tracing sinks or tool policies. `PAUSE` is a returned control state, not an interactive wait or resumable execution.

## Verification

Run the focused sensitive-preflight unit tests, the Jev agent tests, lint, source checks, and the repository CI script. Add no live provider calls; use a scripted decision runner.
