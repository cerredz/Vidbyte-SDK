# S1 spec review, round 2: byok-api-keys spec r2 (01b0bcf6)

Reviewer: S1 adversarial spec reviewer, round 2 (last allowed round). Worktree HEAD 7a13934c, base 52aab816. Scope: what r2 changed, and anything those changes broke.

## VERDICT

**SOUND WITH FIXES.** The matching design is deterministic and safe for roots built from a raw list. But the public `ProviderKeys` pass-through, AggregateAgent proposers, and restored children each get around it. Two claims (NFR-12 "mechanical", NFR-10 "0 wrong-vendor requests") are stronger than the design delivers. Every fix is a small spec edit.

## WHAT THE SPEC GETS RIGHT

- **One record, matched once, carried unchanged.** `ProviderKeys` is matched once at the root and passed unchanged to every agent-built child: fork, fallback, handoff, continual trace, aggregate proposer and aggregator, and Jev children (INV-15, D-13, rows 17–27). This removes the per-child re-matching hazard r1 found, and it also removes `_resolve_key_owner`, `_child_api_key` and `_inherited_api_key`.
- **Table F is prefix-only and fail-safe.** It holds only prefix rules, each with its source stated honestly. Because of the rule order and full-match, a proven key cannot fall under another provider's rule. The four format-bound providers never take an unproven key, so a wrong assumption about their formats refuses a real key (M-6) rather than sending it to another vendor.
- **D-21's import placement is sound.** The record sits beside `AgentRunnerConfig`, that module adds only enum and constants imports, and the matcher imports the record inside `match`. `python lint/run.py --rule A006` → `34 34 RATCHETED`, `SDK-LINT: PASS`.
- **The settled decisions are written as made.** These include INV-24/M-18 for the primary, unique assignment raising otherwise (M-6, M-19), D-25 (a Vidbyte entry is the Vidbyte key, and M-5 raises only on two different ones), the 422 remedy naming `DIRECT`, and the redactor tuple fix. M-15 and M-12 both name `DIRECT`, which closes Q-3 consistently with "streaming gap accepted".

## FINDINGS

### R-7 — Major [L7/L1] — A developer-built `ProviderKeys` bypasses every matching rule

- **Evidence.**
  - §9.2 lists `ProviderKeys` under "New public names", and `TextModelConfig.api_keys` "accepts a list or a `ProviderKeys`". Every agent kwarg takes the same type.
  - Matching step 1 (spec:706) returns a record unchanged and reconciles only the Vidbyte key.
  - §9.1 (spec:649-654) checks only that `providers` are distinct `ModelProvider` members and that each key is a "non-blank, stripped `str`". It runs no table F or table A check, no charset check, and no INV-24 check.
  - `vidbyte/lib/http/transport.py:69-70,86-87` wraps `httpx.RequestError` as `ProviderRequestError(..., response_excerpt=str(exc))`. h11 builds that error with the rejected value: `validate(_field_value_re, value, "Illegal header value {!r}", value)`. `httpx.LocalProtocolError` is a subclass of `httpx.RequestError` (checked on httpx 0.28.1).
- **Failure.**
  - `Agent(provider="openai", api_keys=ProviderKeys(providers=("openai",), keys=("sk-ant-…",)))` sends an Anthropic key to OpenAI. That breaks G-3, INV-3, and NFR-10's "0 requests carry a key matched to a different provider".
  - A record holding only an anthropic key on an openai agent skips INV-24 and silently goes Vidbyte-paid, which is the exact R-2 outcome D-5 calls unacceptable.
  - A key with an inner `\n` passes `strip()`. h11 then rejects the header, and the key text ends up in `ProviderRequestError.response_excerpt`, which breaks INV-4/G-3 (error text) and the M-6b guarantee.
  - It also reopens the per-provider key mapping that NG-19 rejects ("List only").
- **Smallest fix.** Keep the type public, since children need it, but give step 1 a pair check that never re-binds and never applies INV-24, so children are unaffected:
  - every key passes the `normalize` charset (M-6b);
  - a key whose `provider_of` is not `None` sits at that provider;
  - a `FORMAT_BOUND_PROVIDERS` entry holds a proven key;
  - an unproven openai key starts with `sk-`.

  Each failure raises `ConfigurationError` with the provider and index only. Also state in §9.1 that a hand-built record is treated like a child's record: it is not checked against INV-24. About 10 lines in the matcher; no new file or class.

### R-8 — Major [L1] — AggregateAgent proposers go Vidbyte-paid on every call with no error

- **Evidence.**
  - D-27 (spec:463) defines an AggregateAgent's primary as "the resolved aggregator's provider" and its configured providers as the spec-built proposers. INV-24 checks only the primary (spec:250), and EC-33 (spec:345) says "works".
  - Proposers are not fallbacks. `_build_proposer_agent` (`vidbyte/agents/aggregation.py:305-317`) builds one per spec, and every proposer runs on every call.
  - `AggregateAgent.__init__` calls `super().__init__` without a provider or keys (`aggregation.py:203`). `_build_aggregator` returns a prebuilt aggregator unchanged (`:321-322`), so D-27's "resolved aggregator's provider" is undefined for it.
- **Failure.**
  - `AggregateAgent(proposers=["openai/…", "deepseek/…"], aggregator="anthropic/…", api_keys=["sk-ant-…"])` passes INV-24, and both proposers then pay cost plus fee on every call. The ruling's text calls this the PRIMARY "(explicitly configured) provider/model", and proposers are explicitly configured, unlike a fallback child.
  - With a prebuilt aggregator, the implementer has to guess the primary.
  - AC-18's "an `AggregateAgent` is built with the same inputs" cannot be written as a test: an aggregate takes no `provider` or `fallback`, and its own `runner_config.api_keys` stays empty under row 21.
- **Smallest fix.**
  - In D-27 and INV-24: at an AggregateAgent root, every spec-built proposer's provider and the spec-built aggregator's provider count as primaries for INV-24. M-18 names the first one that has no key. Or, if the orchestrator rules otherwise, state in EC-33 that proposers without a key go Vidbyte-paid silently.
  - Define the primary as `None` when the aggregator is a prebuilt agent, since that agent keeps its own record.
  - Row 21 also passes `api_keys=self._api_keys` to `super().__init__`.
  - Rewrite AC-18's aggregate clause with explicit proposers and aggregator.

### R-9 — Major [L5/L7] — EC-52 and AC-19 are false for restored children: a resume re-matches against the child's providers

- **Evidence.**
  - EC-52 (spec:364) and AC-19 (spec:290) promise that re-matching the same raw list "gives the same `ProviderKeys` as the original".
  - Row 17's `restore(..., api_keys, vidbyte_api_key)` sends the raw list through `__init__`, which matches it against the *restored* agent's provider plus `runtime_config["fallback_models"]` (`vidbyte/agents/base.py:545`).
  - A provider-switching fork child is built with `AgentFallbackSettings(models=agent.fallback.models[1:])` (`vidbyte/agents/fork.py:132`). `Session` wraps any `BaseAgent`, and `_restore_agent` always calls `BaseAgent.restore`.
- **Failure.**
  - **Spurious refusal.** A root on `deepseek` with fallback `openai/…` and `api_keys=[K_ds, K_o]` (the AC-18 inputs) matches fine. Its fork child on `openai` has no fallback left. Resuming that child with the same list makes openai the only configured provider: `K_o` binds and `K_ds` has zero candidates, so M-6 fires.
  - **Wrong vendor.** A root on `deepseek` with `[K_ds]` forks a child onto `kimi`. Resuming that child with `[K_ds]` binds `K_ds` to kimi (table A: "any"), so a DeepSeek key goes to Moonshot. The root had bound it to deepseek (INV-3 "matched at its root"). base_commit did the same thing, but the spec claims it no longer happens.
- **Smallest fix.**
  - Persist the provider names the root matched against (no secrets) in `runtime_config`, for example `"key_providers": ["deepseek", "openai"]`. Have `restore` match the raw list against `primary=those[0]`, `others=those[1:]`, with INV-24 off when the restored agent's provider differs from `those[0]`. This is about 4 lines in base.py and fits the 30-line budget.
  - Or keep the behavior: rewrite EC-52 and AC-19 to say that a restored agent is matched as a root against its own provider and fallbacks, and add an edge case for a provider-switched child.

### R-10 — Major [L7/L1] — The unique-assignment wrong-vendor residual is unstated, and NFR-10, G-3 and T-1 overclaim

- **Evidence.**
  - Table A lets deepseek, kimi, glm, minimax, meta, mistral, elevenlabs, playai and typesafe take "any" unproven key.
  - NFR-10 (spec:410) claims "0 requests carry a key matched to a different provider". G-3 (spec:73) says a key "goes only to the provider it is matched to". T-1 (spec:821) says keys are "never [bound] on a guessed shape".
- **Failure.** `Agent(provider="deepseek", api_keys=[K])`, where `K` is really a legacy OpenAI key (`sk-…T3BlbkFJ…`), a Moonshot key, or a Mistral key, binds `K` to deepseek by unique assignment and sends it to DeepSeek in the relay header or in DIRECT. That is a credential disclosure to a third vendor.
  - It is the same as base_commit and inside the settled ruling, so this is not a request to reverse anything.
  - But NFR-10's measurable "0 requests" holds only in the sense of "matched", while T-1 and G-3 read as a guarantee that the key's real owner receives it. S2 will write tests for a property the design does not have.
- **Smallest fix.** Add one sentence to T-1 and NG-18, and narrow NFR-10's metric: an unproven key goes to the one configured provider that can take it, even when the key was issued by another vendor, as at base_commit; the SDK cannot tell; the zero-wrong-vendor metric covers proven keys only.
- **Q-6 `[scope-adding]` (optional, default "no").** Should a key containing OpenAI's legacy `T3BlbkFJ` marker (gitleaks `openai-api-key`) be refused for every provider except openai? This rule only refuses and never routes.

### R-11 — Major [L1] — NFR-12's "mechanical" migration is false when a fallback's provider could also take the key

- **Evidence.**
  - NFR-12 (spec:412) promises "`api_key=k` becomes `api_keys=[k]`".
  - Step 5 counts every configured provider that has no key yet and accepts the key as a candidate.
  - Table A: openai takes any `sk-` key; the nine unformatted providers take any key.
  - §9.4 item 8 (spec:812) shows only a single-provider example.
- **Failure.** `Agent(provider="deepseek", api_key=K_ds, fallback=["openai/gpt-5.5"])` works at base_commit. After the mechanical rename to `api_keys=[K_ds]`, both deepseek and openai take an `sk-` key, so the root raises M-19 and the remedy says to move the key into `DEEPSEEK_API_KEY`. The same happens for any unformatted primary with a fallback on another unformatted provider, such as mistral to kimi. vidbyte-cli is the user's named migration (Prompt 6) and will hit this wherever it configures cross-provider backups with one explicit key.
- **Smallest fix.** NFR-12 and §9.4 item 8 add this case and its migration: move the key into the provider's environment variable, or pass the fallback provider's key too, as long as each key is then the only one its provider can take.
- **Q-7 `[scope-adding]` (optional, default "no").** When a lone unproven key's candidates include the primary, and binding it anywhere else would raise M-18 anyway, should it bind to the primary? This is the only assignment INV-24 permits, so it stays deterministic.

### R-12 — Minor [L1] — Step 5 raises M-6 with a false message when the key's provider already holds a key

- **Evidence.** Step 5 (spec:713-715) takes candidates from the providers that "have no key yet", and an unproven key with zero candidates raises M-6. M-6 says "none of the providers configured here ({configured}) can take such a key". M-7 is meant for two keys for one provider.
- **Failure.** `TextModelConfig(provider="openai", api_keys=["sk-proj-…", "sk-…"])` raises M-6 ("openai cannot take such a key"). The real cause is two openai keys, which is M-7. With two same-provider unproven keys, which error fires depends on the order the implementer binds them in.
- **Smallest fix.** Raise M-6 only when no configured provider accepts the key (ignoring which are taken). When every accepting provider already holds a key, raise M-7 naming the lowest index of the earlier key and this one. Process keys in index order.

### R-13 — Minor [(d)] — Table G's 422 reason omits the backend's header-validation cause

- **Evidence.**
  - The backend spec (byok-fee-relay) validates `X-Vidbyte-Provider-Key` against `^[!-~]+$`, with at most 512 characters. A bad header gets 422 `harness_validation_failed` with `"error": true` (`backend/lib/api/error_route.py`, `HarnessErrorRoute` → `public_payload()`). The SDK therefore takes the gateway-error branch (`vidbyte_gateway.py:88`).
  - The table G 422 row (spec:779) is base_commit's reason (stream, service tier, snake case; `vidbyte_gateway.py:104`) plus the `DIRECT` remedy.
  - `normalize` sets no length cap. Table R's environment fallback is only "stripped and non-blank".
- **Failure.** A list key over 512 characters, or a provider environment variable with an inner space, gets a 422 that blames the request body and recommends `DIRECT`. `DIRECT` then sends the same malformed key straight to the vendor.
- **Smallest fix.** Add "or the provider key is not 1–512 printable ASCII characters without spaces" to the relay 422 reason. Or, better, apply M-6b's charset and a 512-character cap to the resolved key in `credentials()` for `AUTO`.

### R-14 — Minor [L1] — Two D-27 roots match at run time, so "before any request" and R-6's construction-time check do not hold for them

- **Evidence.**
  - The `JevRunBriefSettings` writer matches in `brief/writer.py` (row 26). The writer is built by `JevRunBriefKeeper`, which is created in `vidbyte/agents/jev/compute/controller.py:44` during a run.
  - `AgentRoleSettings` roles are built in `vidbyte/paradigms/context_minimal_fanout/paradigm.py:79,143,168` during a run, and row 29 adds "no new validation".
  - INV-24, INV-25 and §5 (spec:194) say "before any request". INV-26 says the Vidbyte key format is checked "when the config, agent, or settings record is built".
- **Failure.** A Jev run whose brief list lacks the writer's key raises M-18 mid-run, after the main agent's calls were made and billed. A fanout role with a malformed `vidbyte_api_key` or an ambiguous list fails after earlier roles ran.
- **Smallest fix.** State in D-27 and INV-24 to INV-26 that these two roots are checked when their agent is built, which is before that root's own first request. Or have `JevAgentSettings.__post_init__` match `run_brief.api_keys` against the writer's provider, and have `AgentRoleSettings.__post_init__` run `normalize` plus the INV-26 format check.

### R-15 — Minor [L9/L8] — The §12.6 dependency order is circular, and row 3's export target is not a §12.3 row

- **Evidence.**
  - §12.6 (spec:1083-1084) says "Row 17 depends on 4, 11, and 19" and "Rows 18–32 depend on 3, 4, and 17". Rows 18 and 19 are inside 18–32, and row 17 also calls row 18's `AgentFallback.providers_in`.
  - Row 3 (spec:978) says "Export `ProviderKeys` wherever the module's exports are listed". `vidbyte/lib/dataclasses/agents.py` has no `__all__`; its re-export list is `vidbyte/lib/dataclasses/__init__.py:38`, which is not a §12.3 row. §14 says touching a file not in §12.3 means BLOCKED. §9.2 still lists `ProviderKeys` as a new public name.
- **Failure.** The implementer either hits a cycle in the build order or stops BLOCKED on the export.
- **Smallest fix.**
  - Change §12.6 to: "Rows 18 and 19 depend on 3 and 4; row 17 depends on 4, 11, 18, and 19; rows 20–32 depend on 3, 4, and 17".
  - Row 3 names `vidbyte/lib/dataclasses/__init__.py` (add `ProviderKeys` to the `from vidbyte.lib.dataclasses.agents import (...)` block) as a row, or says "no package re-export".

## VERIFIED CLAIMS

**Round-1 findings**

- **R-1 resolved.** Table A lets the nine unformatted providers take any key. §9.4 item 8, G-5 and EC-41 now state exactly what changes.
- **R-2 resolved for single-model roots** (INV-24, M-18, D-5, step 6 after binding). Not resolved for AggregateAgent proposers (R-8).
- **R-3 resolved.** Table F is prefix-only, the deepseek, kimi and `T3BlbkFJ` rules are gone, and NG-18 is in place. The unstated residual is R-10.
- **R-4 resolved.** The table G 422 row names `DIRECT` in both modes (FR-7, D-15, AC-15, EC-50). The header cause is new (R-13).
- **R-5 resolved.** Row 16 adds `\([^)]*\)` beside `\[[^\]]*\]` in `_ERROR_ASSIGNMENT` (`vidbyte/harnesses/serialization.py:70`), which covers tuples in both the `=` and `:` forms.
- **R-6 resolved** for `TextModelConfig`, agents and `JevAgentSettings` (INV-26, M-10 and M-11 at construction, without the environment). `AgentRoleSettings` and the brief writer are checked at run time (R-14).

**Determinism**

- Matching is deterministic at roots built from a raw list. Children never re-match: fork (`fork.py`), fallback (`AgentFallback.build_runner`), handoff, continual trace and Jev children all take the record.
- The remaining holes are restore (R-9), aggregate (R-8), and the two run-time roots (R-14).
- Binding a key that has exactly one candidate does not depend on order. Error indexes are pinned to the lowest index.

**Prefix sources**

- Anthropic `sk-ant-` is first-party. The rest are third-party, as the spec itself says: OpenAI comes from gitleaks (the first-party admin-keys page returned 403 to the reviewer), OpenRouter and xAI from third parties or the repo's own `xai-` regex, and `AIza` from gitleaks.
- `AQ.`: discuss.ai.google.dev/t/171575 (2026-06-17) states it, but no staff badge was visible, so "a Google staff post" is unconfirmed. Google's own Gemini key page confirms the service-account-bound key change of 2026-05-28 but does not print the prefix.
- Because gemini is format-bound, a wrong prefix assumption refuses a key rather than misrouting it.

**Vidbyte key in `api_keys`**

- D-25 is recognized by `VIDBYTE_API_KEY_PREFIX` (`vidbyte/lib/constants/jev.py:64`) before table F.
- M-5 fires only for two different Vidbyte keys. Identical repeats collapse.
- Repr is hidden. Messages must build from the constant, because C020 flags `vb_live_` literals.

**Import cycle and lint**

- `vidbyte/lib/dataclasses/agents.py` imports only stdlib and `vidbyte.lib.errors` today.
- `vidbyte/lib/constants/jev.py` imports only `re` and `enums.model_provider`.
- The new edges point within or down `lib/`, so A006 stays at its 34 baseline.
- The `config.py` precedent (`:573,:610,:629,:673,:716`) exists, though some of those imports go upward and should not be copied for direction.

**Budget**

- base.py at +30 net lines is credible; the reviewer estimates 15–20.
- pipeline.md's niche fact "at most 25 net lines" is stale: r2 says 30.

**INV-24 blast radius**

- No in-repo agent, prebuilt agent or Jev role breaks: there are no default cross-provider fallbacks, Jev has no fallback chain, and Codex is not a `BaseAgent`.
- `Runner._normalize_provider_and_model` only splits a `provider/` prefix, so the primary is exactly what the developer configured.

**Streaming (Q-3)**

- M-15 fires right after `validate()` in `StreamingTextModelRunner` and names `DIRECT`.
- In `AUTO`, an unserved provider hits M-12 in `__post_init__` first, which also names `DIRECT`.
- `StreamingTextModelRunner` is not used by agents.

**Table G against the backend**

- These match: relayed provider 401/402/403 carry the provider's body without `"error": true` and take the relay branch; gateway 401, 402, 413 and 429 (no daily hold under relay) and 5xx; and no relay streaming.
- `credential_mismatch` is backend-internal (backend D-10) and correctly absent from the SDK spec.
- The only gap is R-13.

**Tests and lint obligations**

- `test_managed_text_failures.py:126-146` stays green: its `ManagedCall` uses only `VIDBYTE_API_KEY` from the environment (Vidbyte-paid), and table G keeps every base fact.
- S020 imposes no per-file entry for `provider_keys.py`: the registries README has no "## File Index".
- C016 covers only `vidbyte/__init__.py`'s `__all__`.
