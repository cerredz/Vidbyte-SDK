VERDICT: SOUND WITH FIXES — The risky mechanics (the D-21 import cycle, C017 header tracing, the D-13 key-dropping deletion, the §13 test supersession) hold up against the repo, but the spec understates what users lose (explicit keys for seven providers, and the gateway's request rules on the old BYOK path), and it lets a wrong key silently bill cost plus fee.

Reviewed: spec.md revision 1 at HEAD 62be46c9 (base 52aab816). Severity counts: 0 Blocker, 6 Major, 0 Minor.

WHAT THE SPEC GETS RIGHT

- **D-21 and D-16 are correct as written. Do not restructure them.**
  - The cycle is real. `vidbyte/lib/registries/__init__.py` imports `registries.agents`, which imports `vidbyte.agents.types`, which runs `from vidbyte.lib.dataclasses.agents import AgentCard…` on a module that has only partly loaded.
  - Importing inside the function is already done elsewhere in `vidbyte/lib/dataclasses/config.py`.
  - A subscript store keyed by an imported constant gives C017 nothing to trace. `python lint/run.py --rule C017` prints `C017 platform-route-contract 0 0 CLEAN` and `SDK-LINT: PASS`.
- **D-13 is safe and complete.** Once a key's format decides its provider, the three per-provider key-dropping rules are redundant.
  - `vidbyte_key_follows_provider` has exactly two callers: `vidbyte/agents/fork.py:116` and `vidbyte/agents/settings/fallback.py:163`. Both are in the deletion rows.
  - `find_vidbyte_api_key`, `is_vidbyte_managed` and `resolved_vidbyte_api_key` are used only in `model_configs.py`, `runners/text.py`, `runners/streaming_text.py` and tests that §13 already lists.
- **D-18 / Q-5 (failing on the first run, not at construction) is the right default for a missing key.**
  - Agents read no environment at construction.
  - `BaseAgent._runner_for_model` (`vidbyte/agents/base.py:1555`) builds the runner lazily.
  - Runner errors are wrapped in `AgentExecutionError(... "failed to generate a reply") from exc` (`base.py:903-914`), so AC-26 is accurate.
- **§13 is complete, and its secret-scanner guidance is right.** Every test file that uses a bare `api_key` (49 files) appears in either the superseded list or the "not superseded" list. That includes every test that patches `HttpTransport.request` class-wide. The repo has no secret scanner of its own; only GitHub push protection checks keys, on the server. So building fake keys at runtime from parts is sufficient.

FINDINGS

R-1 [Major] [L1] §9.2 table F note, §9.4, G-5, EC-41 — Seven providers lose every way to pass an explicit key, but the spec says the old resolution "carries over" and that non-text runners work "as today"

  Evidence:
  - Table F note: "Glm, minimax, meta, mistral, elevenlabs, playai, and typesafe have no rule. Their keys go through their environment variables".
  - EC-5 refuses "a Mistral or GLM key".
  - G-5: "Today's resolution carries over: the explicit key first, then the provider's environment variable."
  - EC-41: "works as today".
  - §9.4 has no item for this loss.
  - In the repo, `vidbyte/lib/runners/utility.py` `Runner._config_options_for` sets `options["api_key"]` for every runner type today. So at base, an explicit key reaches Mistral, GLM, ElevenLabs and PlayAI configs.
  - The §13 row for `tests/test_output_schema_provider_dialect.py` says "Rename, `DIRECT`". But `:102` builds `MistralProvider(model="mistral-large-latest", api_key="k")`.

  Failure:
  - (a) A backend serves several tenants on Mistral or GLM in `DIRECT`, the G-4 unbilled path. It passes `api_keys=[tenant_key]` and gets M-6 at construction. The only route left is a process-wide environment variable. That is the T-4/EC-42 cross-tenant hazard, which the spec describes as unchanged ("as today").
  - (b) An agent whose model resolves to ElevenLabs or PlayAI is built with `api_keys=[K]`. It gets M-6, so EC-41 is false for those providers.
  - (c) A test author who follows §13 renames to `api_keys=["k"]` and gets M-6. No Mistral key can pass. The correct edit is to drop the key.
  - Q-1's default (refuse) is correct for a provider that has a rule. For these seven providers, refusal means a developer must keep track of which providers accept keys, which works against the user's "dont want developers to have to worry".

  Smallest fix:
  - Add §9.4 item 7: "glm, minimax, meta, mistral, elevenlabs, playai, typesafe: an explicit key is no longer accepted; set the provider's environment variable."
  - Qualify G-5 and EC-41 with "for providers in table F".
  - Change the §13 row to "drop the key; `mode=TextModelMode.DIRECT`".
  - Make Q-1 blocking, so the user sees the tradeoff.
  - Optional Q-6 [scope-adding]: bind an unrecognized entry to the config's provider only when that provider has no rule in table F and the list holds exactly one unrecognized entry. This stays deterministic, and a key never reaches a provider that has a rule.

R-2 [Major] [L1] §8.1 D-5, §15 Q-2, NFR-10 — A key for the wrong provider silently turns an intended relay into a cost-plus-fee call, the outcome D-20 rejects as unacceptable

  Evidence:
  - D-5: "In `AUTO`, a list that holds keys but none for the call's provider gives a Vidbyte-paid call, with no error."
  - D-20: "A silent drop would turn a relay into a Vidbyte-paid call, billing cost plus fee."
  - Table R, `AUTO` provider key: "list, then env, or `None` (D-5)".
  - NFR-10 quotes Prompt 5, "makes sure that the user is inputting the correct api key that matches the provider/model". But it measures only "0 requests carry a key whose classified provider differs from the call's provider".
  - Q-2 is marked "non-blocking" with the default "**No.**".

  Failure:
  - Consider `Agent(provider="openai", model_name="gpt-5.5", api_keys=[<an xAI key pasted by mistake>], vidbyte_api_key=V)` with no `OPENAI_API_KEY` set.
  - Every call is Vidbyte-paid: the provider's cost plus the fee comes out of the wallet.
  - There is no error, no warning, and no marker in the result.
  - The developer believes they are bringing their own key until the wallet drains.
  - Because Q-2 is non-blocking, the user never sees this tradeoff.

  Smallest fix:
  - Keep the settled per-call rule ("Vidbyte-paid otherwise").
  - Make Q-2 blocking, and put this example and the D-20 parallel in its text.
  - Rewrite NFR-10's measure so it no longer claims that classification alone meets Prompt 5.
  - Optional Q-7 [scope-adding]: in this case, emit one `warnings.warn` per runner. The case is a runner built in `AUTO` with a non-empty list and neither a list key nor an environment key for the call's provider. The warning names the provider and the providers the list holds, with no key text. `vidbyte/lib/jev/managed.py` already uses `warnings.warn`. The call stays Vidbyte-paid.

R-3 [Major] [L7] §9.2 table F rows 2, 4 and 5, §15 A-2/A-3, §10 T-1 — Unsourced exact-shape `sk-` rules decide which vendor receives a key, and a collision sends the key to the wrong vendor with no signal

  Evidence:
  - Table F: "| 4 | deepseek | `sk-[0-9a-f]{32}` | Third-party only (A-2) |" and "| 5 | kimi | `sk-[A-Za-z0-9]{48}` | Third-party only (A-3) |".
  - A-3: "If wrong: refused, or, if the shape collides with another rule, classified to it".
  - T-1 promises "The key goes only to its classified provider".
  - The gitleaks config the spec cites (`gitleaks.toml`) has rules for OpenAI, Anthropic and GCP keys only. It has none for deepseek, moonshot/kimi, xai or openrouter. The spec cites no URL for rows 2, 4 and 5.

  Failure:
  - The kimi rule is the legacy OpenAI key shape without the `T3BlbkFJ` marker. So any 48-alphanumeric `sk-` key from another OpenAI-compatible vendor classifies as kimi.
  - When an agent's model chain includes a kimi model, that key is sent to Moonshot in `X-Vidbyte-Provider-Key`. The credential is disclosed to a third vendor.
  - Meanwhile, the call the developer intended goes Vidbyte-paid with no error (R-2), so nothing reveals the misclassification.
  - D-5 says classification alone meets the "matches the provider" requirement. That holds only if these unverified shapes are right.

  Smallest fix:
  - Add a pre-merge obligation to §12.4. Confirm each "Third-party only" rule against the vendor's own documentation, or against the length and charset of one real key. Never record any key text.
  - Put the URL in the rule's source comment and in the registries README (row 35).
  - Drop any rule that cannot be confirmed. That provider then uses its environment variable, the EC-35 path.
  - Add the cross-vendor consequence to T-1.

R-4 [Major] [L5] §9.4 item 2, §9.2 table G (422) — Former default-mode BYOK callers now hit every gateway request rule, and the 422 message never names `DIRECT`

  Evidence:
  - request.md §C: "422 unbillable/unsupported request (dialect rules identical in both modes)".
  - `vidbyte/lib/http/vidbyte_gateway.py:104`: the 422 reason lists "a hosted (non-function) tool, a service tier, a previous-response or conversation reference, or a body field outside the gateway's allowed list, including Gemini snake_case keys" and gives no remedy.
  - Table G: "Rows not listed are unchanged from base_commit". The 422 row is not listed.
  - §9.4 item 2 says only that `AUTO` "now relays through the gateway and needs a Vidbyte key".

  Failure:
  - At base, a user runs `AUTO` with `OPENAI_API_KEY` and an OpenAI hosted tool, `service_tier`, or `previous_response_id`, all valid when calling the vendor directly.
  - The user upgrades and adds `VIDBYTE_API_KEY`, as M-9 says to.
  - Every run then fails with "Vidbyte gateway openai request failed: the gateway cannot manage this request (HTTP 422) …".
  - Nothing points to `TextModelMode.DIRECT`, the only fix. Table G's 413 row names `DIRECT`, but 422 covers more cases.

  Smallest fix:
  - Extend §9.4 item 2 with: "and inherits the gateway's request rules: the 2,000,000-byte limit, no hosted tools, service tier, previous-response or conversation references, only allowed body fields, and the 32,768 default output cap".
  - Add a 422 row to table G, the same in both modes, ending "; use TextModelMode.DIRECT to send it straight to the provider with your own key". Add `DIRECT` to the facts the tests check.

R-5 [Major] [L7] §12.3 row 15 — The harness redactor's new list alternative misses the tuple the SDK itself stores, so every key after the first survives redaction

  Evidence:
  - Row 15: "the value group gains a bracketed-list alternative `\[[^\]]*\]` before the bare-token alternative".
  - `vidbyte/harnesses/serialization.py:70`: the bare-token alternative is `[^\s,;]+`.
  - §8.5: `api_keys: tuple[str, ...]`. AC-18: `runner_config.api_keys == (K_ds, K_oa)`.

  Failure:
  - Captured text contains `api_keys=('xai-A…', 'sk-ant-B…')` or `{'api_keys': ('xai-A…', 'sk-ant-B…')}`, for example a user's own exception that formats its kwargs.
  - At `(`, neither the quoted alternatives nor the list alternative matches.
  - The bare token consumes `('xai-A…'` up to the comma.
  - The Anthropic key is written to the harness capture unredacted.

  Smallest fix: add a parenthesized alternative `\([^)]*\)` beside `\[[^\]]*\]`. Require a row-15 test with a two-key tuple in both the `=` and `:` forms.

R-6 [Major] [L9] §12.3 rows 16 and 24, §8.1 D-18 — Agents check every `api_keys` entry's format at construction, but accept any string as `vidbyte_api_key` until the first run

  Evidence:
  - Row 16: `AgentRunnerConfig.__post_init__` "normalizes `api_keys` … refuses a non-string `vidbyte_api_key` (M-11)".
  - M-10 (malformed Vidbyte key) is raised only inside `credentials()` (table R).
  - M-5 already refuses, at construction, a Vidbyte key placed in `api_keys`.
  - D-18 defers failure because a construction-time check "reads the environment at construction". A prefix check on an explicit value reads no environment.

  Failure:
  - `Agent(..., vidbyte_api_key=<OpenAI key>, api_keys=[<Vidbyte key>])` fails with M-5 at construction.
  - The same mistake made in one place only, `Agent(..., vidbyte_api_key=<OpenAI key>, api_keys=[<OpenAI key>])`, constructs successfully.
  - It fails on the first run, wrapped in `AgentExecutionError`, possibly inside a forked or restored child far from where the key was set.
  - This goes against AGENTS.md §4: "Invalid data then fails at the boundary where it enters".

  Smallest fix:
  - In rows 16 and 24, apply the M-10 prefix check at construction to an explicit, non-`None` `vidbyte_api_key` in `AgentRunnerConfig` and `JevAgentSettings`.
  - Keep the missing-key case at first run, so D-18 is unchanged.
  - Tests that pass a non-live Vidbyte key to an agent switch to the runtime-built `VIDBYTE_KEY`.

VERIFIED CLAIMS

| # | Claim | Result | Evidence |
|---|---|---|---|
| 1 | D-21 import cycle | Held | `vidbyte/lib/registries/__init__.py` → `registries.agents` → `vidbyte.agents.types` → `from vidbyte.lib.dataclasses.agents import AgentCard…`. Import order confirmed: `dataclasses.agents` loads first, through `dataclasses.context`. |
| 2 | D-21 precedent: "two function-local imports in `vidbyte.lib.dataclasses.config`" | Held, count understated | There are function-local imports in five functions: `:573`, `:610`, `:629`, `:673`, `:716-717`. |
| 3 | D-16 / C017: a subscript header store keyed by an imported constant gives the tracer nothing | Held | `lint/core/string_flow.py:658-750` and `lint/core/python_index.py` `_BodyReader`. `python lint/run.py --rule C017` → `C017 platform-route-contract 0 0 CLEAN`, `SDK-LINT: PASS`. |
| 4 | D-13 / row 5: the deletion covers every caller | Held | `vidbyte_key_follows_provider` is used only at `vidbyte/agents/fork.py:116` and `vidbyte/agents/settings/fallback.py:163`. The other removed methods are used only in `model_configs.py`, `runners/text.py`, `runners/streaming_text.py`, `tests/features/sdk_managed_text/test_managed_text_acceptance.py:134,140` and `test_managed_text_selection.py:115,262`. |
| 5 | A001 baseline 643, ratcheted | Held | — |
| 6 | Patch target `vidbyte.lib.runners.text.HttpTransport` | Held | — |
| 7 | AC-26 / D-18: runner errors are wrapped in `AgentExecutionError`, and the runner is built lazily | Held | `vidbyte/agents/base.py:903-914` and `:1555`. |
| 8 | Table F row 1: Anthropic first-party source | Held | The platform.claude.com authentication page documents `sk-ant-api…` keys. |
| 9 | Table F rows 3 and 7: gitleaks rule shapes | Held | openai `sk-(proj\|svcacct\|admin)-…T3BlbkFJ…` / `sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20}`; anthropic `sk-ant-api03-[a-zA-Z0-9_\-]{93}AA`; gcp `AIza[\w-]{35}`. gitleaks has no rule for xai, deepseek, moonshot/kimi or openrouter. |
| 10 | A-6: Google says AI Studio issues `AQ.` keys | Held as stated | The post says "AI Studio will now only generate Authentication Key (AQ) keys". It states no length or charset, and I did not confirm the poster's staff role. |
| 11 | A-2 / A-3: DeepSeek `sk-` + 32 hex, Kimi `sk-` + 48 alphanumerics | Not confirmed | No source found, and the spec cites none (R-3). |
| 12 | §13: the repo has no secret scanner of its own; build fakes at runtime | Held | No gitleaks or other scanner config in the repo. Only GitHub push protection applies. |
| 13 | §13 superseded-test list is complete | Held | All 49 test files with a bare `api_key` are listed (superseded or not superseded). Every `.api_key` attribute read is covered. Class-wide `HttpTransport.request` patchers are listed (`gemini_tool_wire_format`, `billed_unusable_replies`, `nested_usage_bill`). No omitted test that would fail was found. One row's fix instruction is wrong (R-1 (c)). |
| 14 | Secret guards: new names in `credential_keys.py` reach the YAML policy | Held | `vidbyte/lib/dataclasses/config.py` `_YamlSecretKeyPolicy` merges the parent's `_SECRET_KEYS` and `_SECRET_SUFFIXES` at class definition. The harness redactor regex does not cover tuples (R-5). |
| 15 | Row 28: `vidbyte/agents/codex/fallback.py` needs only comment edits | Held | `CodexFallbackCoordinator` overrides only the turn model (`settings_for`) and never builds a text runner, so it needs no key or mode plumbing. |
| 16 | Gateway headers are built in one place, and 422 has no remedy | Held | `vidbyte/lib/http/vidbyte_gateway.py`: `bearer_headers(self._api_key)` followed by the `Idempotency-Key` line. The 422 reason at `:104` has no remedy (R-4). request.md §C: "dialect rules identical in both modes". |
