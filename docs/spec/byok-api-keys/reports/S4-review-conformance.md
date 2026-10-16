LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every path the user named relays the right key offline and all 41 §12.3 rows land within budget, but in a gateway mode `TextModelConfig` runs the key match before the INV-8 shape refusal. So an unserved provider or an endpoint, combined with another provider's key, gets M-18 with a remedy that cannot work, where INV-8 calls for `UnsupportedProviderError`/M-13 naming DIRECT.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The user's words hold on every path checked.**
  - Every agent entry point takes both `api_keys` and `vidbyte_api_key`: BaseAgent and its kwargs subclasses, AggregateAgent, JevAgentSettings, AgentRoleSettings, and Session.resume/fork_from. `MultiAgent` owns no model.
  - One lib class, `vidbyte/lib/registries/provider_keys.py:ProviderKeyMatcher`, matches each key to its provider.
  - In AUTO, the fallback, fork, aggregate children and resumed or forked sessions each relayed only their own provider's key in `X-Vidbyte-Provider-Key`. This is from an offline probe, not the pack.
- **The §4 snippet (AC-1) runs offline exactly as written.**
  - It made one gateway POST with Bearer V and the xAI key in the relay header, and printed the scripted answer.
  - On an xai 503 the Claude backup relayed the Anthropic key.
  - The DIRECT agent made one request to `https://api.x.ai/` with the xAI key. It never read `VIDBYTE_API_KEY` and never contacted the gateway.
- **"Extend the api_key functionality" is honoured.**
  - With no list, AUTO relays `XAI_API_KEY` from the environment.
  - VIDBYTE_MANAGED never relays (INV-5).
  - An image runner gets `api_key = key_for(openai)` from the list (row 11).
  - Restore re-matches against the stored names: EC-53 and EC-54 behave as specified.
- **Scope and budget are clean.**
  - The diff touches exactly the 49 §12.3 files plus the authorized S014 rule file.
  - One new file and three new classes (§8.4). `base.py` is +34/−8, net 26 ≤ 30.
  - `lint/baseline.json` only lowers A001 from 643 to 641.
  - Every `tests/` commit is a `test(sdk):` commit; c0ab2b0a was routed to S2 by the 0d0b484b ruling.
  - No text- or agent-level `api_key=` remains. The deleted symbols are gone from `vidbyte/`.

## FINDINGS

### R-C1 [Major] [invariant] `vidbyte/lib/dataclasses/model_configs.py:94-100` — A gateway-mode config matches keys (M-18) before the INV-8 shape check, so an unserved provider or endpoint plus another provider's key gets M-18, not M-12/M-13

- **Evidence** (`conformance/probe_inv8.py`, cleared `RecordingEnviron`):
  - `TextModelConfig(provider="mistral", model="mistral-large-latest", api_keys=[<xai key>])` in default AUTO raises `ConfigurationError`: "TextModelConfig.api_keys holds keys for xai but none for mistral … or pass no provider keys to use MISTRAL_API_KEY or Vidbyte's own mistral account."
  - The same config without keys raises `UnsupportedProviderError`: "The Vidbyte gateway serves only: … Use mode=TextModelMode.DIRECT …".
  - `TextModelConfig(provider="xai", …, api_keys=[<anthropic key>], endpoint="https://proxy.example/v1")` raises M-18 instead of M-13.
  - In both cases the environment reads are `[]` and no request is made, so this is not unsafe.
  - `__post_init__` calls `ProviderKeyMatcher.match` at :94 and `_require_gateway_shape` only at :99-100.
- **Failure:**
  - INV-8 says a non-DIRECT config with an unserved provider "raises `UnsupportedProviderError`", "before any key or environment is read", and that both messages name `TextModelMode.DIRECT`.
  - For this input the developer instead gets a different exception class, and a fix that cannot work: the gateway has no mistral account. Following it leads straight into M-12, a second round trip that NFR-8 and "dont want developers to have to worry" were meant to avoid.
  - AC-12's tests (`test_provider_keys_acceptance.py:222`, `test_provider_keys_modes.py:224`) build only keyless configs, so nothing catches this.
  - The cause is row 7's sentence order (match, then shape). INV-8 is the more specific ordering statement.
- **Smallest fix:**
  - Move the `if self.mode is not TextModelMode.DIRECT: self._require_gateway_shape(self.normalized_provider())` block above the `ProviderKeyMatcher.match` call. It reads only provider, endpoint and mode.
  - Add one AC-12 subtest each for mistral with `api_keys=[<xai key>]` and for an endpoint with `api_keys=[<anthropic key>]`, asserting `UnsupportedProviderError` and M-13.
  - The Agent root keeps INV-24 as specified.
- **Spec IDs:** INV-8, EC-15, EC-16, AC-12, M-12, M-13, M-18, NFR-8, §12.3 row 7.

### R-C2 [Minor] [message] `vidbyte/lib/registries/provider_keys.py:293` — M-18 offers "Vidbyte's own {primary} account" where none exists

- **Evidence** (`probe_inv8.py`):
  - `TextModelConfig(provider="mistral", …, api_keys=[<xai key>], mode=DIRECT)` and `Agent(provider="mistral", …, api_keys=[<xai key>])` both say "or pass no provider keys to use MISTRAL_API_KEY or Vidbyte's own mistral account".
  - The gateway serves only anthropic, deepseek, gemini, kimi, openai and xai, and DIRECT never contacts Vidbyte.
- **Failure:** For glm, minimax, meta, mistral and openrouter in every mode, and for any provider in DIRECT, half the stated fix is impossible. NFR-8 requires every refusal to name the fix. The wording follows spec table M, which "should stay close"; the matcher does not know the mode.
- **Smallest fix:** Append the Vidbyte-account clause only when `missing in VIDBYTE_MANAGED_TEXT_PROVIDERS`. `vidbyte/lib/constants/jev.py` is already imported by this module. For example: "…to use {ENV}, or in AUTO Vidbyte's own {primary} account".
- **Spec IDs:** M-18, NFR-8, INV-24.

No further findings. Hunted and cleared:
- **The `arun` gateway branch.** It is keyed on `self._credentials.vidbyte_api_key is not None`, not `uses_gateway`. `TextCredentials.__post_init__` makes these equivalent: every gateway mode holds a Vidbyte key and DIRECT never does.
- **The `key_for(self.provider or "")` guard** in `utility.py:130`.
- **The `@intent` tag names kept in `session.py`.** Their text now says keys, plural.
- **`JevRunBriefSettings` has no `vidbyte_api_key`.** Row 24 by design: the writer borrows the settings' Vidbyte key.
- **The deviations.** All 21 S3 deviations are in §17 or `S3-implementer.md` §3, and each is minimal. I found no unreported deviation.

## VERIFIED CLAIMS

1. **AC-1 / §4 holds offline.** The snippet made exactly one POST to the gateway URL with Bearer V, `X-Vidbyte-Provider-Key` = xAI key, and envelope `("xai", "grok-4.5")`; `reply.content == "Hi"`. On an xai 503 the anthropic backup relayed the Anthropic key only. The DIRECT agent made one request to `https://api.x.ai/` with Bearer = xAI key and no relay header, and read no `VIDBYTE_API_KEY` (`probe_snippet.py`, all PASS).
2. **INV-15 holds on the child paths.** A fork to anthropic relays the Anthropic key. Handoff and continual-trace children carry the root's `ProviderKeys` and `model_mode` unchanged. In the aggregate (xai and anthropic proposers, openai aggregator), each child relays exactly its own key. `Session.resume(..., api_keys=[xai, anthropic])` and `session.fork()` relay the xAI key.
3. **INV-14 / D-30 / EC-53 / EC-54 hold.**
   - A fork child's export holds `key_providers={"primary": ["xai"], "others": ["anthropic"]}` and `model_mode="auto"`, and no key text.
   - The child restored with only the Anthropic key relays it. Restored with only the xAI key, it goes Vidbyte-paid (no header).
   - The root restored with only the Anthropic key raises M-18.
   - A pre-change child state (no `key_providers`) is matched as a root, and INV-24 applies (`probe_restore_env.py`).
4. **Table R / INV-5 hold.**
   - AUTO with no list and `XAI_API_KEY` set relays the environment key.
   - VIDBYTE_MANAGED with `api_keys=[xai]` sends no relay header.
   - INV-23: building every probed agent read no environment variable (`env.reads == []`).
5. **Row 11 / INV-19 hold.** `Runner(provider="openai", model_name="gpt-image-1", api_keys=[anthropic, openai])` resolves type `image`, and its config options are exactly `{"api_key": <openai key>}`. The scripts' only remaining `api_key=` uses are Image, Video and Audio configs. All 20 script `TextModelConfig(` lines use `api_keys=[…]` with `mode=TextModelMode.DIRECT` (row 39).
6. **§12.3 coverage holds.** `git diff --name-status` lists 49 files outside `docs/spec` and `tests`. They are exactly rows 1–41 plus `lint/rules/s014_provider_model_registry_parity.py`, authorized by 0d0b484b. There are 3 new classes (`ProviderKeys`, `TextCredentials`, `ProviderKeyMatcher`), 1 new file and 0 new dependencies (§8.4). `base.py` numstat is 34/8.
7. **Docs rows 33–38 and 41 match.**
   - The registries README carries the table F, table A and reserved-prefix sources, each marked first-party, secondary or refuse-only.
   - The `sk-admin-` replacement `raw.githubusercontent.com/openai/openai-openapi/...` is OpenAI's own GitHub organization.
   - The agents README paragraph and the `FallbackModel` example both match.
   - llms.txt `:1113` and skills/sessions.md `:174` both name `api_keys`. Row 36's conditional sentence is correctly omitted: the section lists no agent parameters.
   - `ProviderKeys` is exported from `vidbyte.lib.dataclasses`.
8. **Gates pass.** The full suite gives `4101 passed, 13 skipped`. `python lint/run.py` prints `SDK-LINT: PASS`. The worktree stayed clean at HEAD `8bd1963d`.

## COMMANDS RUN

- `env -u DEEPSEEK_API_KEY PYTHONPATH=<worktree> PYTHONIOENCODING=utf-8 python -m pytest -q tests/features/sdk_provider_keys` → 117 passed.
- `... python <scratch>/conformance/probe_snippet.py` → all PASS (AC-1, §4 fallback and DIRECT, fork, handoff, continual trace, aggregate, Session.resume, Session.fork).
- `... python <scratch>/conformance/probe_inv8.py` → evidence for R-C1 and R-C2; FallbackModel and disabled-chain `others`; `env.reads == []`.
- `... python <scratch>/conformance/probe_restore_env.py` → EC-53, EC-54, environment relay, VIDBYTE_MANAGED, image runner key.
- `... python -m pytest -q -x -p no:cacheprovider tests` → 4101 passed, 13 skipped in 36.33s.
- `... PYTHONDONTWRITEBYTECODE=1 python lint/run.py` → SDK-LINT: PASS.
- `git log --format='%h %an %s' origin/main..8bd1963d -- tests`, plus the full log.
- `git diff --numstat origin/main...8bd1963d -- vidbyte/agents/base.py`.
- `git diff --name-status` and `--stat origin/main...8bd1963d`.
- `git diff origin/main...8bd1963d -- lint/baseline.json README.md vidbyte/agents/README.md vidbyte/lib/registries/README.md llms.txt skills/ vidbyte/lib/dataclasses/__init__.py vidbyte/agents/base.py vidbyte/lib/runners/text.py`.
- `git show 0d0b484b`, `git show c0ab2b0a`.
- Greps for deleted symbols, leftover `api_key=`, `find_provider_api_key`/`os.environ` callers and `VIDBYTE_MANAGED_TEXT_PROVIDERS`, plus the scripts' `TextModelConfig(` lines.
