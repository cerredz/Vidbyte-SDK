---
slug: meta-muse-managed-text
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-16 18:25
flags: none (Run B of two sequential spec-pipeline runs; Run A is cerredz/Vidbyte slug meta-muse-gateway, draft PR https://github.com/cerredz/Vidbyte/pull/710, which is this run's wire contract)
---

# Request: Let the SDK's gateway text modes (AUTO and VIDBYTE_MANAGED) use provider `meta`, so Muse calls go through the Vidbyte gateway and relay the user's Meta key

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (the invoking prompt; it lists several work items, and this run is the SDK half of item **#1** only):

````
launch a subagent with teh "spec-pipeline" skill for each of the following: 1. [ ] Launch Muse through the Vidbyte gateway, both Vidbyte-paid and with the user's own key — the gateway refuses meta today, so Muse users skip Vidbyte's 2% fee entirely. Builds on: agents can now pick a Meta key out of a mixed key list. First step: scope adding Meta to the backend's provider list and the price table. Want users to be able to use muse models with their meta/muse api keys: 7. [ ] Spin up a provider-onboarding agent — it researches a new vendor's key format, endpoint and prices from first-party sources, then opens the PR that adds them. Builds on: this session's source-backed, mutation-tested method. First step: turn this session's method into a skill. (ask Claude). Can you run number 7 as a continuous, 24/7 run that creates a new pr per provider that it adds?
````

Item #7 (the provider-onboarding agent) is a separate run and is **out of scope here**. The sentence "Want users to be able to use muse models with their meta/muse api keys" is the user's own added must-have and attaches to item #1.

Item #1 crosses a repo boundary, so it was split into two sequential runs. The coordinator's assignment for this run, verbatim:

````
- **Run B — `C:\Users\422mi\vidbyte-repos\vidbyte-sdk`** (GitHub `cerredz/Vidbyte-SDK`). Slug `meta-muse-managed-text`. Start it only after Run A reaches S6, and record Run A's PR URL in Run B's `request.md` as the wire contract.
  - The SDK must let `TextModelMode.AUTO` and `VIDBYTE_MANAGED` use provider `meta`, so a Muse agent goes through the gateway and relays the user's Meta key.
  - Run B's PR body must say it merges only after Run A is deployed.
````

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### Key decisions
- **The wire contract is Run A's backend PR:** https://github.com/cerredz/Vidbyte/pull/710 (draft; branch `feat/meta-muse-gateway`; spec `docs/spec/meta-muse-gateway/spec.md` r4). Its §9.2–§9.4 are copied verbatim into `context/wire-contract.md` beside this file. That copy is the authority for what the gateway accepts and answers for `provider: "meta"`. Do not design against any other reading of the backend.
- The BYOK relay for `meta` is **required**. It is the user's own added must-have. In `TextModelMode.AUTO`, a `meta` text call whose agent holds a matched Meta key goes through the Vidbyte gateway and relays that key in `X-Vidbyte-Provider-Key`. Meta bills the caller, and Vidbyte bills only its 2% fee (FEE_ONLY).
- The **Vidbyte-paid** path (`TextModelMode.VIDBYTE_MANAGED`, Vidbyte's own Meta key on the backend) is also in scope ("both Vidbyte-paid and with the user's own key").
- Reuse the existing relay header and wire contract from SDK PR #1027 (`X-Vidbyte-Provider-Key`). Do **not** invent a new header, field, or endpoint.
- One draft PR for this repo. It is never merged by the pipeline; the user merges.
- **The PR body must say it merges only after Run A (cerredz/Vidbyte#710) is deployed.** Run A's own deploy step also says ops must provision `META_API_KEY` on the backend service before any SDK release routes `meta` through the gateway (Run A spec A-7, §12.5). Without that key, a Vidbyte-paid `meta` call answers 502, while relay calls still work.
- No unrequested features (spec-pipeline rule 11): anything extra becomes an optional `Q-n` with default "no".
- Prices are **never invented**. The SDK owns model rates, and any Muse rate it holds must match Meta's first-party page https://dev.meta.ai/docs/pricing-rate-limits. Run A verified `muse-spark-1.1` there at $1.25 input / $4.25 output / $0.15 cached input per 1M tokens on 2026-10-15 and 2026-10-16.

### Rejected alternatives
- A new relay header or a new wire contract for Meta: rejected. The #1027 contract is reused.
- Changing the backend from this run: rejected. Run A owns the backend. Backend gaps found here become `Q-n` notes for Run A, not code in this PR.
- Backporting Muse prices into the backend's pinned SDK branch from this run: rejected. That is Run A's Q-1 follow-up (an SDK hotfix on `hotfix/v0.2.1-content-type` adding `muse-spark-1.2`/`1.3` Standard rows, plus a backend pin bump). It is a separate decision for the user, not part of this PR unless the user asks.

### Constraints and assumptions
- **SDK state verified earlier in the session** (re-verify each against SDK origin/main `845a4d9b`, the base of this run):
  - SDK PR #1027 merged 2026-10-15 (main `72a4ade1` then). Agents take `vidbyte_api_key` plus an unordered `api_keys` list. `ProviderKeyMatcher` (`vidbyte/lib/registries/provider_keys.py`) matches each key to its provider. In `TextModelMode.AUTO` a text call goes to the Vidbyte gateway and relays the matched provider key in `X-Vidbyte-Provider-Key`. The #1027 spec is `docs/spec/byok-api-keys/spec.md`, which may be read because the user named this work.
  - In #1027, `ProviderKeyMatcher` gained a Meta rule: keys look like `LLM|<numeric app id>|<secret>`, regex `LLM\|[0-9]+\|[A-Za-z0-9_-]+`; `meta` takes no unproven key.
  - The `|` characters are printable ASCII, so a Meta key passes the relay header pattern `VIDBYTE_PROVIDER_KEY_PATTERN = [!-~]+`, max 512 characters (`vidbyte/lib/constants/jev.py`). The backend accepts the same pattern (wire contract §9.2 "Relay header").
  - **The SDK refuses meta in gateway modes today.** `VIDBYTE_MANAGED_TEXT_PROVIDERS` in `vidbyte/lib/constants/jev.py` = {openai, anthropic, gemini, xai, deepseek, kimi}. `TextModelConfig(provider="meta", mode=AUTO)` raises `UnsupportedProviderError` at construction. `tests/features/sdk_provider_keys/test_provider_keys_modes.py::GatewayShapeTests` asserts that meta is unserved, so this run must move meta into the served set, and that assertion changes by design.
  - The SDK's meta wiring: `ProviderModelRegistry` default model `muse-spark-1.1`; endpoint `https://api.meta.ai/v1`; adapter `MetaProvider` in `vidbyte/providers/compatible.py` (chat-completions dialect, Bearer auth); env var `META_API_KEY`. Known models: `muse-spark-1.1`, `muse-spark-1.2`, `muse-spark-1.3`, `muse-spark-1.2-contributor`, `muse-spark-1.3-contributor` (`vidbyte/lib/constants/runners.py`).
- **What the gateway serves for meta (wire contract §9.2):** production serves only `muse-spark-1.1` and its dated-snapshot forms, because the backend's pinned SDK (`54a8e1a5`) prices only that id. Every other Muse id, including `muse-spark-1.3` (the id in Meta's own examples), answers 422 `model_gateway_unsupported_model` before any I/O, on both paths. SDK main may price more Muse ids than the backend pin. The scout must find the SDK's own Muse rows. The spec must decide what an SDK user who picks an unserved Muse id in a gateway mode sees, and must not hide or invent anything.
- **The gateway requires an output cap.** At least one of `max_tokens` or `max_completion_tokens` must be present, as an integer ≥ 1; otherwise the call answers 422 `model_gateway_unbillable_request` (`output_cap_missing`). The SDK's `MetaProvider` sends `max_tokens` only when `max_output_tokens` is configured. Run A's spec recommends that the SDK send the cap as `max_completion_tokens`, which Meta documents as counting visible output plus reasoning. This is a recommendation; this run decides how its gateway path guarantees a cap. The scout must find how the gateway path guarantees a cap for the six providers already served (DeepSeek, for example, requires `max_tokens`).
- **Error wording:** `vidbyte/lib/http/vidbyte_gateway.py` re-sends every 502 twice and words errors by status alone. Run A gave the "no Vidbyte key for this provider" 502 a new body copy (title "Vidbyte-paid access not configured", subtitle naming the `X-Vidbyte-Provider-Key` remedy) without changing the status or code. Appending a 502 body's `subtitle` to the SDK message is Run A's **recommendation only**, not an obligation. Under rule 11 it is an optional `Q-n` (default no) unless an existing SDK pattern already surfaces body text.
- Security: a provider key goes only to the vendor it was matched to; a Meta key is relayed only on a `provider: "meta"` call. Secrets and relayed keys are never logged, printed, put in exceptions, or put in traces.
- Billing: fail closed; never bill or quote a price that cannot be sourced.
- **Gates (SDK):** the full local gate is `py -3.11 scripts/run_ci.py`; `--stage package` runs packaging alone. Never export `PYTHONPATH` before a full `run_ci.py` (its clean-install step then skips the wheel, and the smoke step fails with "No module named 'vidbyte'"). `PYTHONPATH=$(pwd)` is fine for `--stage source` only. Field guide: `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/local-ci-verification.md`.
- **Known red on pristine SDK main, not this PR's fault** (confirm against a detached origin/main worktree before excusing anything; they may have been fixed since 2026-10-15):
  - `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`: deterministic 148 != 120, a merge-base artifact of #1036. PR #1147 rewrites it and may have merged.
  - `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`: timing-flaky on Windows.
  - Because a pytest failure stops `run_ci.py` before its package stage, run `run_ci.py --stage package` separately when the pytest stage is red only on these.
- **SDK CI on GitHub never attaches to PRs** (triggers are paused), so the PR shows 0 checks. The local gate is the proof.
- Environment: Windows 11, Git Bash. Bash heredocs collapse `\\` to `\`, so any script containing backslashes is written with the Write tool and run by path. Working copies use CRLF, so anchor text edits without a trailing `\n`. Use `py -3.11`; bare `python` lacks the test dependencies.

### Clarifications and answers
- None asked of the user. The coordinator restated the following during Run A, and they bind this run: "Draft PRs only, never merge. Never commit real key shapes; build fake keys by concatenation. Do not touch the main checkouts. No bare git stash. Use py -3.11, and write any script that contains backslashes with the Write tool."

### Terminology
- **Muse:** Meta's model family on the Meta developer API (`api.meta.ai`); model ids `muse-spark-*`.
- **provider `meta`:** the provider id the SDK and the backend use for Muse.
- **`TextModelMode.AUTO`:** the SDK's default text mode after #1027. A text call goes to the Vidbyte gateway, relaying the matched provider key when the agent holds one.
- **`TextModelMode.VIDBYTE_MANAGED`:** Vidbyte-paid. The gateway calls the provider with Vidbyte's own key and bills cost plus fee (TOTAL).
- **BYOK relay:** the caller's own key in `X-Vidbyte-Provider-Key`; the provider bills the caller; Vidbyte bills only its 200 bps fee (FEE_ONLY).
- **Vidbyte's 2% fee:** 200 basis points on provider cost, computed by the backend.
- **#1027:** the SDK PR that introduced `api_keys`, `ProviderKeyMatcher`, and the `X-Vidbyte-Provider-Key` relay.
- **Run A / #710:** the backend PR that adds `meta` to the gateway; this run's wire contract.

### Implementation hints
- Model the change on how the six providers already in `VIDBYTE_MANAGED_TEXT_PROVIDERS` are served in gateway modes; the scout confirms the nearest sibling (Kimi and DeepSeek were the most recent additions).
- Fake Meta keys in tests are built by concatenation (e.g. `"LLM" + "|" + "1"*15 + "|" + "m"*32`). Never commit a real key shape as a single literal.
- Do not touch the main checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` (it has untracked files). All work happens in the worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-meta-muse-managed-text`. Never use bare `git stash`.

### Open questions
- What exactly changes when `meta` joins `VIDBYTE_MANAGED_TEXT_PROVIDERS`: only the constant, or also a gateway-path model/endpoint map, a request builder, a cap rule, docs or READMEs, `llms.txt`, a provider table, or an export? (scout)
- How does the gateway path guarantee an output cap today for the served providers, and what must `meta` send so the gateway never answers `output_cap_missing`? (scout, then spec)
- Which Muse ids does the SDK itself price or list at main, and how should a gateway-mode call for an id the backend does not serve (`muse-spark-1.2`/`1.3`/contributor) behave? Does the SDK pre-check model ids for other gateway providers, or does it pass the backend's 422 through? (scout, then spec)
- Does any SDK path relay a key to the gateway for a provider other than the one it was matched to? Confirm that a Meta key reaches only `provider: "meta"` envelopes. (scout)
- What do the SDK's own docs and the #1027 spec say about which providers are gateway-served, and which must change? (scout)

## D. Weighted words

- "both Vidbyte-paid and with the user's own key" (Prompt 1, item 1)
- "Want users to be able to use muse models with their meta/muse api keys" (Prompt 1, the user's own added must-have)
- "the gateway refuses meta today, so Muse users skip Vidbyte's 2% fee entirely" (Prompt 1, item 1)
- "The SDK must let `TextModelMode.AUTO` and `VIDBYTE_MANAGED` use provider `meta`" (the coordinator's Run B assignment)
- "Run B's PR body must say it merges only after Run A is deployed" (the coordinator's Run B assignment)
- "Never invent a price." (session constraint)
- "a key goes only to the vendor it was matched to; secrets are never logged" (session constraint)
- "Never commit a real key shape as one literal." (session constraint)
