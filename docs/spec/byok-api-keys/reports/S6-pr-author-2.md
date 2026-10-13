# S6 PR author report (relaunch): byok-api-keys (SDK)

**Status: DONE (draft PR).** I read the final diff first and the spec second. §5 matches the code, so I left it unchanged. I wrote `pr-body.md`, set the spec to `status: pr-open`, and added the §17 row. No file under `vidbyte/`, `tests/`, `lint/`, `scripts/`, or `.semgrep/` changed. I did not merge main again: `origin/main` is still `8387d666`, which is already merged at `0e04102d`. The PR stays a draft.

## 1. What the code does (read from the diff, `origin/main...d3066f84`)

- **Diff size.** 124 files across 128 commits: 50 source files (+1407 / −442), 50 test files, and 24 docs files. The test files are 13 new under `sdk_provider_keys`, 6 under `sdk_managed_text`, 2 under `sdk_model_usage`, and 29 module tests.
- **The matcher.** `ProviderKeyMatcher.match(api_keys, *, primary, others, vidbyte_api_key, field_name, require_primary_key)` (`vidbyte/lib/registries/provider_keys.py`, 299 lines) normalizes the list.
  - It refuses a string, bytes, a mapping, or a number, and any entry with a space, a line break, or a non-ASCII character.
  - It takes the Vidbyte key out as the bearer.
  - Table F prefixes prove a key's provider. Reserved prefixes (`sk-svcacct-`) only refuse.
  - An unproven key binds only by unique assignment under table A, or as the lone key to the agent's own provider (D-29). M-18 refuses a list that holds provider keys but none for the agent's own provider.
  - It returns `ProviderKeys`. A record passed in is checked key by key and passed through unchanged (M-20).
- **The record and the mode.** `ProviderKeys` (`vidbyte/lib/dataclasses/agents.py`) hides its keys from repr. The record and `model_mode` ride on `AgentRunnerConfig` to every fallback, fork, handoff, continual-trace, aggregate, Jev, and session child.
- **Credentials.** `TextModelConfig.credentials()` is the one place that reads the environment (the provider's variable and `VIDBYTE_API_KEY`). It returns `TextCredentials(mode, provider_api_key, vidbyte_api_key)`, through a `match` on mode with a raising `case _`.
  - In every non-DIRECT mode, `__post_init__` runs `_require_gateway_shape` before matching. That shape check refuses an unserved provider (M-12) and a custom endpoint (M-13).
- **The runner and transport.** `TextModelRunner` pins the credentials when it is built. Gateway modes get the 32,768 output cap and a 630 s timeout floor.
  - `VidbyteGatewayTransport` sends `X-Vidbyte-Provider-Key` only when the call relays. Its failures read "Vidbyte gateway {provider} request failed:" and are worded per table G for relay calls and paid calls.
  - `StreamingTextModelRunner` refuses both gateway modes before reading a key.
- **Non-text runners.** These get `ProviderKeys.key_for(provider)` and call the vendor directly, as before.
- **Save and restore.** `export_state` records `model_mode` and the matched provider names, never a key. `restore`, `Session.resume`, and `Session.fork_from` re-match the caller's list against those names.
- **Size caps.** `vidbyte/agents/base.py` is +34 / −8, a net +26 against the cap of 30. `provider_keys.py` is 299 lines, under NFR-4's 300.

## 2. Deviations from the spec

The deviations are all recorded in spec §17. I added none.

- The env-var table moved to `vidbyte/lib/constants/jev.py`, and S014 reads it only through a bare-name alias.
- M-17 sits in `ModalityDetector._config_options`.
- The shape check runs before the match (R-6). This overrides row 7 and INV-24's "every mode".
- M-18's "Vidbyte's own account" clause is offered only for served providers. In DIRECT the clause remains, which is an accepted limitation.
- The public annotations were widened (R-10).
- The paid 402 offers `api_keys` advice only for AUTO (R-17).
- A relayed 400 adds the own-key clause (LE-1).
- `CredentialKeyPolicy` gained `provider_key` and `_provider_key`.
- The row 16 regex leaves out `(?:\w+_)?`.
- The row 35 `sk-admin-` source changed.
- Two message constants were added (R-16).

The PR body lists the same items under "Deviations from the spec".

## 3. Snippet and breaking-change checks (offline, fake keys built by concatenation, non-loopback sockets blocked)

I ran spec §4's snippet, unchanged, with `HttpTransport` replaced by a scripted 200 answer:

```text
--- snippet stdout ---
Hi
--- end snippet stdout ---
requests sent: 1
request 0: url_is_gateway=True envelope_provider='xai' envelope_model='grok-4.5' bearer_is_vidbyte_key=True relay_header_sent=True relay_header_is_xai_key=True anthropic_key_anywhere=False idempotency_key_sent=True
offline.model_mode: direct | offline holds a Vidbyte key: False
```

Breaking-change checks, run on `d3066f84`:

- **`api_key=` raises `TypeError`** on `Agent`, `TextModelConfig`, `FallbackModel`, `AgentRunnerConfig`, `JevAgentSettings`, `JevRunBriefSettings`, `AgentRoleSettings`, and `AggregateAgent`.
- **`create_runner_for_modality(api_key=)`** raises `ConfigurationError: create_runner takes api_keys, a list of provider keys, for a text model; api_key is not accepted.`
- **A raw list in `AgentRunnerConfig(api_keys=[...])`** raises `ConfigurationError: AgentRunnerConfig.api_keys must be a ProviderKeys record; BaseAgent matches the developer's list first.`
- **Session and restore signatures.** `Session.resume`, `Session.fork_from`, and `BaseAgent.restore` each show `api_key=False api_keys=True vidbyte_api_key=True`.
- **Removed helpers.** All four report `still present = False`.
- **AUTO with an xAI key and no Vidbyte key.**
  - `Agent(...)` builds.
  - `agent.run` raises `AgentExecutionError: Agent 'a' failed to generate a reply.`, and its `__cause__` is `ConfigurationError: Missing Vidbyte API key. Pass vidbyte_api_key or set VIDBYTE_API_KEY, or use mode=TextModelMode.DIRECT to call the provider with your own key and no Vidbyte fee.`
  - A bare `TextModelRunner` raises that `ConfigurationError` directly.
- **AUTO streaming** raises `UnsupportedProviderError: StreamingTextModelRunner streams only straight from the provider, and this config's mode is TextModelMode.AUTO. Set mode=TextModelMode.DIRECT …`. DIRECT streaming builds.
- **A Grok key on an openai agent** raises M-18.
- **A scripted gateway 401 on a relay call** gives `ProviderRequestError: Vidbyte gateway xai request failed: Vidbyte rejected the Vidbyte API key (HTTP 401); check VIDBYTE_API_KEY or vidbyte_api_key.` The message has the new prefix and does not contain "Vidbyte managed".
- **Probes.**
  - In AUTO, a mistral `TextModelConfig` raises M-12, and a custom endpoint raises M-13. Both name DIRECT.
  - A mistral `Agent` in AUTO builds, and its first run raises `AgentExecutionError` whose cause is `UnsupportedProviderError`.
  - `resolved_api_key()` returns the placeholder in AUTO and the key in DIRECT.
- **AC proof names.** A script checked spec §6.2's Proof column against the branch: 67 found, 0 missing.
- **Feature packs.** `tests/features/sdk_provider_keys` plus `tests/features/sdk_managed_text`: `165 passed in 2.00s`.

## 4. Gates

These are the orchestrator's gate numbers on `d3066f84`. I re-ran lint on this docs commit, and nothing else in the gate inputs changed.

| Gate | Result |
|---|---|
| Lint (`PYTHONIOENCODING=utf-8 python lint/run.py`) | `SDK-LINT: PASS`, C017 `CLEAN` (re-run on the docs commit) |
| `run_ci.py --stage source` | `4141 passed, 13 skipped` · `SDK-LINT: PASS` · `CI passed.` |
| `run_ci.py --stage package` | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` · `CI passed.` |
| Semgrep test / scan | `1/1: ✓ All tests passed` · `Ran 1 rule on 894 files: 0 findings.` |
| Remote, code head `d3066f84` | CI 38477180582 success · Static policy 38477183555 success |

## 5. PR, push, and checks

This section is filled in after the push, in the follow-up docs commit.

## 6. Candidate field-guide lessons (conventions lens)

I did not write these to the field guide. Each one is from PR https://github.com/cerredz/Vidbyte-SDK/pull/1027.

1. **Call depth counts through every entry point (R-1).**
   - Trigger: a helper that you call from `validate()` or another public method calls helpers of its own.
   - Preferred action: inline the leaf steps into the `case` arms of the main function, so it calls only leaf helpers.
   - Reason: AGENTS.md §1. Two callers of `credentials()` turned three of its helpers into six two-level chains.
   - Quick check: an AST call-depth scan of the class, comparing base to head, should find 0 new chains.
2. **Mode dispatch is a `match` with a raising `case _` (R-7).**
   - Trigger: an `if`/`elif`/`else` on an enum whose `else` silently means one member.
   - Preferred action: `match` with one `case` per member and `case _: raise ConfigurationError(...)`.
   - Reason: a future `TextModelMode` member would otherwise inherit AUTO's key rule without anyone noticing.
   - Quick check: grep the diff for `elif self.mode` or `else:` beside enum comparisons.
3. **Diff the A002 finding set, not the count (R-8).**
   - Trigger: a business-rule function that is new or moved.
   - Preferred action: put an `@intent` within 20 lines of its `def`, then compare `lint/run.py --rule A002 --all --format json` at base and head, set against set.
   - Reason: lint passed while A002 rose from 584 to 585. Neighbouring `@intent` blocks also hid gaps that moved when code moved.
   - Quick check: the set difference of A002 findings, head minus base, should be empty.
4. **A loosened lint rule needs a mutation matrix (R-9).**
   - Trigger: editing a lint rule so it reads a value from a new place.
   - Preferred action: mutate the guarded table (`{}`, deletion, another name), run the rule at base and head, and expect the same REGRESSED counts.
   - Reason: S014 passed CLEAN on every mutation after its alias change. The ruling had required "equally strict".
   - Quick check: on the mutated table, the rule gives the same `found N` at base and at head.
5. **Public annotations accept the documented input form (R-10).**
   - Trigger: a public field whose docs and examples pass a list, but whose annotation is a record or a tuple.
   - Preferred action: annotate the input union (`ProviderKeys | Iterable[str | None] | None`), and narrow it at the read sites.
   - Reason: mypy and IDEs flagged every documented call, while `Agent` itself was clean.
   - Quick check: run mypy with `lint/mypy.ini` on a probe that uses the README's call forms.
6. **Touched comments stay within 72 columns, and headers match the code (R-11, R-12).**
   - Trigger: editing a comment, an `@intent` line, or a file header's ROLE/TESTS lines.
   - Preferred action: re-wrap to 72 columns, and re-list every caller and test folder that the header names.
   - Reason: comment-format.md. Stale headers misdirect the next reader.
   - Quick check: `awk 'length > 72'` over the touched comment lines, then grep the callers of each function the header names.
7. **One message, one constant (R-16).**
   - Trigger: the same error text, or the same f-string, in two modules.
   - Preferred action: a single constant beside the pattern or rule it describes.
   - Reason: two copies of the Vidbyte-key format message had already started to differ in wording.
   - Quick check: grep for a distinctive phrase of each new message, and expect one definition.
8. **Read a size cap literally (R-C1).**
   - Trigger: a spec cap phrased as "under N lines".
   - Preferred action: treat N as excluded, and stop at N−1.
   - Reason: `provider_keys.py` reached exactly 300 against "under 300", a Major finding in re-review.
   - Quick check: `wc -l` on the file should give less than N.
9. **A new secret name goes into every guard, in every spelling (R-D2, deferred).**
   - Trigger: adding a credential field or header name.
   - Preferred action: add the bare name, the plural, and the run-on spelling to both `CredentialKeyPolicy` and the harness redactor.
   - Reason: the two guards still disagree on `providerkey` and `provider_keys`.
   - Quick check: probe `is_secret_key` and the free-text redactor with each spelling.

## 7. Things that looked wrong

- **Live-run spend figure.** The briefing says the live calls cost "about $0.0004 at xAI". The settlement row says `provider_cost_nanousd` 1,723,700, which is about $0.0017. I cannot check either figure offline. The PR body quotes only the settlement figures, which are cost about $0.0017, fee 34,474 nUSD, and `billed_cents` 1.
- **One-shot proposer iterables** (`vidbyte/agents/aggregation.py:215` vs `:226`). `primaries` reads `proposers` through `map(self._coerce_spec, proposers)` before `self._proposer_inputs = tuple(proposers)`, so a generator is used up by the first read. Probe: `AggregateAgent(proposers=<generator>)` fails with "MultiProviderAggregator requires at least one proposer.", and a list works. The parameter is annotated as a `Sequence`, so this is outside the contract. It is listed as a follow-up and was not fixed (no source changes).
- **`mode=` vs `model_mode=`** (`vidbyte/lib/dataclasses/model_configs.py:51`, `TEXT_REMEDY`). The message tells an `Agent` caller to "use mode=TextModelMode.DIRECT", but `Agent`'s argument is `model_mode=`. The streaming refusal and the M-12 and M-13 refusals use the same wording. This is listed as a follow-up.
- **R-D1, stale test row** (`tests/features/sdk_provider_keys/test_provider_keys_failures.py:183`). `test_another_relayed_provider_status_keeps_its_unchanged_wording` still names 400 as table G's last row. After LE-1, a relayed 400 has its own row. This is deferred.
- **R-D2** (`vidbyte/lib/util/credential_keys.py:55-80`). The policy misses `providerkey` and `provider_keys`. This is deferred.
- **The AUTO no-Vidbyte-key failure is later than some docs imply.** It raises at the first `run()`, wrapped in `AgentExecutionError`, not at `Agent(...)`. The PR body's Breaking changes section says this explicitly. The spec's Q-5 default is "no" (do not fail at build), so this behaviour is intended.
