LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — The routing, billing and secret-handling code held against every adversarial probe and 47 of 54 mutations, but four mutations that bring back wrong-vendor routing, a Vidbyte key sent to a vendor, or a silent cost-plus-fee call pass the full suite of 4101 tests, so those guards rest on untested lines.

WHAT THE IMPLEMENTATION GETS RIGHT
- **Matching is strict and gives nothing away.** `ProviderKeyMatcher` (vidbyte/lib/registries/provider_keys.py) refuses every near miss: `AIza` with 34 or 36 characters, `xai-client-secret.`, `sk-ant` with a dot, and `sk-svcacct-` anywhere but openai. Unique assignment does not depend on key order (`[U1,U2]` and `[U2,U1]` both give M-19). CR, LF, NUL, tab and non-ASCII inside a key raise M-6b before the key can reach a header. No M-n message or `details` contains key text. Mutations a, j, k, dd, hh, ii, jj, ll and nn are killed.
- **The billing route is correct on every mode path.** `X-Vidbyte-Provider-Key` is sent only when a key is relayed (mutations b and ap killed). VIDBYTE_MANAGED never sends a provider key. DIRECT never reads the Vidbyte key (ff killed). AUTO without a Vidbyte key raises; it does not quietly go DIRECT (d killed). `TextModelRunner` pins its credentials at init (g killed). The output cap and the 630 s floor apply only on gateway calls (h killed). Each call builds its own gateway transport, and no runner is shared.
- **The record and the mode reach every child.** These children were each checked by mutation: fork, session fork, fork recovery, handoff, continual trace, the Jev clone, the brief writer, aggregate children and the runner (mutations c1, c2, p, pp, qq, rr, ss, tt, u and w killed). Restore re-matches against the stored `key_providers`, with the INV-24 switch set correctly (e1, e2 and v killed).
- **No secret appears in any repr or state.** The reprs of all 12 key-holding objects show no key: ProviderKeys, AgentRunnerConfig, TextModelConfig, TextCredentials, the Jev settings, AgentRoleSettings, AgentFallback, the agent, the runner and VidbyteGatewayTransport. `export_state` and `SessionSerializer._safe` write only `key_providers {'primary': ['xai'], 'others': ['anthropic']}` (q killed). The key is never in the gateway envelope (yy killed).

FINDINGS (ranked, most severe first, max 15)

R-E1 [Major] [test quality] vidbyte/lib/runners/utility.py:130, vidbyte/lib/agents/modality_detector.py:226 — No test proves that an image, audio or other non-text config gets its own provider's key from a list that holds more than one, so a wrong-vendor bug in that path goes undetected.
  Evidence: Mutation `o_runner_nontext_first_key` changes `self.api_keys.key_for(self.provider or "")` to `self.api_keys.keys[0]`. It SURVIVES the full suite: `4101 passed, 13 skipped`. Mutation `an_detector_nontext_first_key` makes the same change to `ProviderKeyMatcher.match(api_keys, primary=provider).key_for(provider)` in `ModalityDetector._config_options`, and it also SURVIVES (`4101 passed, 13 skipped`). The AC-23 test (`tests/features/sdk_provider_keys/test_provider_keys_agents.py:421-436`) only builds single-key lists: `api_keys=[K_OPENAI]` and `api_keys=[K_UNPROVEN]`. `probe_gaps.py` shows the effect, with the record order `['xai', 'openai']`:
    - worktree: `image agent image config.api_key -> K_OPENAI` and `detector image config.api_key -> K_OPENAI`;
    - under mutation o: `image agent image config.api_key -> K_XAI`;
    - under mutation an: `detector image config.api_key -> K_XAI`.
  Failure: `Agent(provider="openai", model_name="gpt-image-1", api_keys=[K_xai, K_openai])` is built and its runner is created. With an index-or-first-key bug, the xAI key is sent to OpenAI's image endpoint. That is the wrong-vendor send NFR-10 counts as zero, and the suite stays green.
  Smallest fix: In the AC-23 test, add `api_keys=[K_XAI, K_OPENAI]` (the other provider's key first) for both `Agent(...)._runner_for_model()` and `ModalityDetector.create_runner("image", ...)`, and assert `config.api_key == K_OPENAI`. Add one case where the list holds only another provider's key (`api_keys=[K_XAI]` and `others` naming xai), and assert `config.api_key is None`.
  Spec IDs: AC-23, FR-12, INV-19, NFR-10, W-9

R-E2 [Major] [test quality] vidbyte/lib/registries/provider_keys.py:204 — Nothing tests the record check that stops a Vidbyte key from being filed as a provider key. If that check is dropped, DIRECT sends the Vidbyte key to the vendor.
  Evidence: Line 204 reads `sendable = re.fullmatch(VIDBYTE_PROVIDER_KEY_PATTERN, key) is not None and not key.startswith(VIDBYTE_API_KEY_PREFIX)`. This is the implementer's spec §17 deviation ("`_check_record` also refuses a Vidbyte-prefixed key held as a provider key (INV-13)"). Mutation `kk_record_vidbyte_entry_allowed` removes the `not key.startswith(...)` clause and SURVIVES the full suite: `4101 passed, 13 skipped`. The M-20 test table (`tests/features/sdk_provider_keys/test_provider_keys_matching.py:364-372`) has rows for an anthropic key at openai, a line break, an unproven key at anthropic, and a non-sk key at openai. It has no row with a Vidbyte key. `probe_record_vb.py` shows the effect:
    - worktree: `ConfigurationError TextModelConfig.api_keys is a ProviderKeys record whose key 0 does not fit deepseek`;
    - under mutation kk: `DIRECT provider key is the Vidbyte key: True`.
  Failure: `TextModelConfig(provider="deepseek", api_keys=ProviderKeys(providers=(DEEPSEEK,), keys=(<vb_live_ key>,)), mode=DIRECT)` sends the Vidbyte key to DeepSeek. The M-14 guard in `find_provider_api_key` covers only environment values, so nothing else stops it.
  Smallest fix: Add the row `("vidbyte key at deepseek", ProviderKeys(providers=(ModelProvider.DEEPSEEK,), keys=(VIDBYTE_KEY,)), "deepseek", VIDBYTE_KEY)` to the table at `test_provider_keys_matching.py:368-372`.
  Spec IDs: INV-13, T-6, M-20, AC-39, §17

R-E3 [Major] [test quality] tests/features/sdk_provider_keys/test_provider_keys_acceptance.py:257-270 (code: vidbyte/lib/dataclasses/model_configs.py:137-141) — The AC-13 check that the provider variable is never read cannot detect the most likely regression, and that regression breaks VIDBYTE_MANAGED for users with the old habit.
  Evidence: The test passes `api_keys=[K_OPENAI]`. `find_provider_api_key` returns the record's key before it looks at the environment, so `self.assertNotIn("OPENAI_API_KEY", environment.reads)` passes even when VIDBYTE_MANAGED resolves the provider key. Mutation `ad_managed_reads_provider_env` adds `ProviderModelRegistry.find_provider_api_key(provider, self.api_keys)` to the VIDBYTE_MANAGED branch, and it SURVIVES the full suite: `4101 passed, 13 skipped`. (An earlier full run showed one failure in `tests/test_mcp_stdio_transport.py::...test_cancelled_waiter_does_not_break_transport`. That test is flaky: it gave `1 failed, 21 passed`, then `22 passed` and `22 passed` on the unmutated tree.) `probe_gaps.py` shows the effect:
    - worktree: `managed + Vidbyte key in OPENAI_API_KEY: vidbyte_managed provider key: None`;
    - under mutation ad: `ConfigurationError: OPENAI_API_KEY holds a Vidbyte API key; set it as VIDBYTE_API_KEY ...`.
  Failure: A developer explicitly selects `mode=VIDBYTE_MANAGED`, has no `api_keys`, and still has the old managed switch (a `vb_live_` value in `OPENAI_API_KEY`, as EC-13 describes). That developer is refused with M-14, in the one mode that INV-5 says never reads the variable. The suite stays green.
  Smallest fix: Add a second case to the AC-13 test with no `api_keys` and `OPENAI_API_KEY` set. Assert that `"OPENAI_API_KEY" not in environment.reads` and that the call succeeds with no provider-key header. A value built from `VIDBYTE_API_KEY_PREFIX` also covers the M-14 regression.
  Spec IDs: INV-5, AC-13, EC-18, EC-13

R-E4 [Major] [test quality] vidbyte/agents/aggregation.py:219-220 — No test checks that the default aggregator counts as a primary. If those two lines go, the R-8 bug returns: the aggregator call becomes a silent Vidbyte-paid call.
  Evidence: Lines 219-220 read `elif aggregator is None and provider and model_name: primaries.append(provider)`. Mutation `vv_default_aggregator_not_primary` deletes both lines and SURVIVES the full suite: `4101 passed, 13 skipped`. The AC-37 test (`test_provider_keys_agents.py:272`) always passes an explicit `aggregator=` spec or a prebuilt agent. `probe_agg.py` shows the effect for `AggregateAgent(proposers=[("openai","gpt-5.5")], provider="anthropic", model_name="claude-sonnet-5", api_keys=[K_OPENAI])`:
    - worktree: `ConfigurationError api_keys holds keys for openai but none for anthropic ...`;
    - under mutation vv: `BUILT (default aggregator would go Vidbyte-paid silently)`.
  Failure: The aggregate is built with no M-18 error. Every synthesis call then runs on Anthropic at cost plus fee, even though the developer supplied provider keys. D-27 and NFR-10 forbid exactly this.
  Smallest fix: Add the case above to the AC-37 test (`aggregator` omitted, `provider` and `model_name` given, the list holding only a proposer's key), and assert M-18 naming `anthropic`.
  Spec IDs: AC-37, D-27, INV-24, NFR-10, EC-57

R-E5 [Minor] [security] vidbyte/harnesses/serialization.py:74, vidbyte/lib/util/credential_keys.py:55-76 — The harness redactor and the credential-key policy do not recognize the new header name, so a dump of the gateway headers keeps the provider key in clear text while the bearer token beside it is scrubbed.
  Evidence: `probe_secrets.py` shows:
    - `LEAK redactor header dump -> ['xai-...']` for `{'X-Vidbyte-Provider-Key': '<key>', 'authorization': 'Bearer <vb key>'}`; the Vidbyte bearer is scrubbed;
    - `LEAK redactor header dump raw` for `X-Vidbyte-Provider-Key: <key>`;
    - `is_secret_key('X-Vidbyte-Provider-Key') = False`.
  `_ERROR_ASSIGNMENT` recognizes `api[_-]?keys?|...|authorization` but not `provider-key`. `_SECRET_SUFFIXES` has no suffix that matches `x_vidbyte_provider_key`. The diff added `api_keys` and `_api_keys` but not the header introduced by the same diff.
  Failure: A trajectory capture or exception text that includes the transport's header mapping reaches a `TrajectorySink` with the developer's provider key intact. NFR-1 requires zero occurrences in any trace. No current path dumps headers, so this is defense in depth.
  Smallest fix: Add `"_provider_key"` to `CredentialKeyPolicy._SECRET_SUFFIXES`, and add `provider[_-]?key` to the `_ERROR_ASSIGNMENT` alternation.
  Spec IDs: NFR-1, INV-3, INV-4

R-E6 [Minor] [failure messages] vidbyte/lib/http/vidbyte_gateway.py:111 — In VIDBYTE_MANAGED, a gateway 402 tells the developer to add a provider key to `api_keys`, but that mode ignores the list.
  Evidence: The Vidbyte-paid 402 text is chosen whenever `relays` is False: "top up the wallet, or add your own provider key for {provider.value} to api_keys so the wallet pays only Vidbyte's fee". `gateway_reason` receives only `relays`, never the mode. VIDBYTE_MANAGED never reads `api_keys` (model_configs.py:137-141, INV-5).
  Failure: A developer in VIDBYTE_MANAGED gets a 402, adds the key as told, and gets the same 402 on the next call. D-15: "Wrong advice … is a bug." Table G has only paid and relay columns, so this is a gap in the spec, not a departure from it.
  Smallest fix: Pass the mode, or a `can_relay` flag that is True only for AUTO, from `TextModelRunner` into `gateway_reason`. For VIDBYTE_MANAGED, word the remedy as "top up the wallet, or use TextModelMode.AUTO with your own {provider} key in api_keys".
  Spec IDs: D-15, AC-15, table G

R-E7 [Minor] [security] vidbyte/paradigms/context_minimal_fanout/types.py:444 — AgentRoleSettings refuses a padded Vidbyte key that Agent accepts, and its message says the key is in the wrong format.
  Evidence: The diff adds `ProviderKeys(vidbyte_api_key=self.vidbyte_api_key)` with no strip. The probe gives, for `"  " + VB + "\n"`:
    - `role padded ConfigurationError The managed Vidbyte API key must be a live key in the vb_live_ format.`
    - `agent padded accepted`
  Failure: A fanout role whose Vidbyte key was read from a file with a trailing newline fails at settings time. The message says the key is not a `vb_live_` key, although it is one, and it names no field. The same key works on every other root.
  Smallest fix: Validate and store the stripped value: `object.__setattr__(self, "vidbyte_api_key", (self.vidbyte_api_key or "").strip() or None)` before the `ProviderKeys(...)` check. Alternatively, run it through `ProviderKeyMatcher.match((), vidbyte_api_key=..., field_name="AgentRoleSettings.vidbyte_api_key")`.
  Spec IDs: FR-1, M-4 consistency across roots

R-E8 [Minor] [security] [scope-adding] vidbyte/lib/registries/provider_keys.py:64, 82 — Vidbyte test keys (`vb_test_`) are not reserved, so they bind as an unproven provider key.
  Evidence: `probe_match.py` gives, for `vb_test_` with primary deepseek and openai among the others: `map={'deepseek': 23}`. `accepts_unproven` is True for deepseek, glm, minimax, kimi, meta, mistral, elevenlabs, playai and typesafe. The backend issues this namespace: `backend/lib/enums/api_keys.py:8 API_KEY_TEST_PREFIX = "vb_test_"`. Its docstring says it is admitted only on "controlled development and direct tooling paths".
  Failure: A developer on an internal or test backend puts a `vb_test_` key in `api_keys` with a DeepSeek model. AUTO relays it to DeepSeek; DIRECT sends it there directly. Table F defines the Vidbyte key as `vb_live_` only, so this widens INV-13 beyond the spec.
  Smallest fix: Add a `VIDBYTE_TEST_KEY_PREFIX` constant, and refuse any entry that starts with it, next to the `VIDBYTE_API_KEY_PREFIX` checks at lines 137 and 204. This is a follow-up for the user.
  Spec IDs: INV-13, T-6 (hardening beyond table F)

VERIFIED CLAIMS
- **Holds.** Pack `117 passed`; managed-text pack `39 passed`; together `156 passed in 1.83s`. `tests/features/sdk_managed_text/test_managed_text_failures.py` is unchanged against origin/main.
- **Holds.** Full suite on an archived copy of 8bd1963d: `4101 passed, 13 skipped` (the S3 gate).
- **Holds.** "`ProviderKeys` repr shows provider names only." All 12 reprs probed are clean. `vars()` exposes keys only on `VidbyteGatewayTransport`, which is by design.
- **Holds.** "`export_state` writes names only as `key_providers`." Mutation q (exporting keys) is killed, and serializer output shows names only.
- **Holds.** "The header is sent only when a provider key is set." Mutations b and ap are killed. VIDBYTE_MANAGED sends exactly the headers {authorization, content-type, idempotency-key}.
- **Holds.** "`TextModelRunner` pins credentials at init, and the cap and floor apply only on gateway calls." Mutations g and h are killed.
- **Holds.** "Streaming refuses non-DIRECT before `validate()`." Mutations x and ae are killed.
- **Holds.** "Relay wording follows table G." Mutations i, n, oo and ao are killed.
- **Holds.** "provider_keys.py is 296 lines (NFR-4 ≤ 300)."
- **Holds, with a caveat.** "Fallback carries DIRECT." Mutation t is killed only incidentally, by `tests/features/sdk_model_usage/test_billed_unusable_replies.py::test_billed_refusal_then_fallback_bills_both_calls`. No sdk_provider_keys test checks it, and it is not raised as a finding.
- **Does not hold as a coverage claim.** "AC-23 covered by `test_image_and_audio_runners_get_their_providers_matched_key_or_none`": the test passes, but it cannot tell `key_for(provider)` from "first key" (R-E1).
- **Does not hold as a coverage claim.** "AC-13 proves INV-5 never reads the variable": see R-E3.
- **Does not hold as a coverage claim.** "AC-37 covers every spec-built aggregator": see R-E4.
- **Not raised.** `key_for` is case-sensitive, but no wrong result was found. `ModalityDetector` raises "Unsupported model provider" for `"OpenAI"` before any key is sent, and `Agent` normalizes the provider first.

COMMANDS RUN (all from the worktree root, or from my scratch copy `tree/`, with `env -u DEEPSEEK_API_KEY PYTHONPATH=<root> PYTHONIOENCODING=utf-8`; scratch = C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/5bfc4a32-d2a9-4a4d-a6e5-3f472a0fe403/scratchpad/s4-sdk/engineering)
- `python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → `...worktrees\vidbyte-sdk-byok-api-keys\vidbyte\__init__.py`
- `python -m pytest tests/features/sdk_provider_keys tests/features/sdk_managed_text -q -p no:cacheprovider` → `156 passed in 1.83s`
- `git archive 8bd1963d | tar -x -C <scratch>/tree`, then `python -m pytest -q -p no:cacheprovider` there → `4101 passed, 13 skipped`
- `python <scratch>/mutate.py <name>` (the pack) and `--full <name>` (whole suite) for 54 single-string mutations, each restored after its run → 47 killed. 7 survived the pack, and 5 of those still survive the full suite:
    - o: `4101 passed, 13 skipped`
    - an: `4101 passed, 13 skipped in 35.30s`
    - kk: `4101 passed, 13 skipped`
    - vv: `4101 passed, 13 skipped in 34.81s`
    - ad: `4101 passed, 13 skipped in 34.91s`
  The other two pack survivors are killed by the full suite: a2 by `tests/test_aggregate_agent.py::...test_key_without_provider_is_refused_when_providers_are_mixed`, and t by the billed-fallback test named above.
- `python -m pytest -q -p no:cacheprovider tests/test_mcp_stdio_transport.py`, three times on the unmutated tree → `1 failed, 21 passed` / `22 passed` / `22 passed` (flaky, unrelated)
- `python <scratch>/probe_match.py` → every near-miss is refused. Its only acceptance is `vb_test_` (R-E8). Every M-n error is free of key text.
- `python <scratch>/probe_secrets.py` → all reprs, export_state and serializer output are clean. Redactor LEAK lines: header dump and raw header (R-E5). Three other LEAK lines are not raised because they are unreachable: comma-separated `OPENAI_API_KEYS`, a set literal, and `keys=(...)` text.
- `python <scratch>/probe_gaps.py` on the worktree and under mutations o, an, kk and ad, via `apply_one.py` → outputs quoted in R-E1, R-E2 and R-E3.
- `python <scratch>/probe_record_vb.py` (worktree and kk) and `python <scratch>/probe_agg.py` (worktree and vv) → outputs quoted in R-E2 and R-E4.
