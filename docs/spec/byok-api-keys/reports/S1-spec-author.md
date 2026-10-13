# S1 spec author report — byok-api-keys

Spec: `docs/spec/byok-api-keys/spec.md`, revision r1, committed as e201a52b ("docs(spec): add byok-api-keys spec r1") on `feat/byok-api-keys`. The base is 52aab816. This report itself is not committed, because the briefing's commit command adds only spec.md.

## What I read

**Under docs/**

- `request.md`, in full.
- `context/code-map.md`, in full.
- I did not open any other `docs/` file, `reports/S0-scout.md`, or `pipeline.md`.

**Rules**

- AGENTS.md
- The REPO_MAP entries for lib.
- The `vidbyte/lib/util/__init__.py` header.
- `vidbyte/lib/registries/README.md`.
- The field-guide entries named in spec §11.
- The spec template.
- The house style and vidbyte-gates references.

**Source, in full or at the cited ranges**

- Text-model layer:
  - `vidbyte/lib/dataclasses/model_configs.py`
  - `vidbyte/lib/registries/{models.py, __init__.py, pricing.py header}`
  - `vidbyte/lib/http/vidbyte_gateway.py` (in full)
  - `vidbyte/lib/runners/{text.py, streaming_text.py, utility.py}`
  - `vidbyte/lib/agents/modality_detector.py`
  - `vidbyte/lib/constants/jev.py`
  - `vidbyte/lib/enums/text_model.py`
  - `vidbyte/lib/errors/base.py`
- Agents:
  - `vidbyte/lib/dataclasses/agents.py`
  - `vidbyte/agents/{base.py, fallback.py, settings/fallback.py, fork.py, aggregation.py, handoff.py, continual_trace.py}`
  - every Jev call site that passes `api_key`
- Paradigm, sessions, and harness:
  - `vidbyte/paradigms/context_minimal_fanout/{types.py, paradigm.py}`
  - `vidbyte/sessions/{session.py, serialization.py, failure/recovery/fork_recovery.py}`
  - `vidbyte/harnesses/serialization.py`
- Credential guards:
  - `vidbyte/lib/util/credential_keys.py`
  - `vidbyte/lib/dataclasses/{config.py, agent_descriptor.py}`
- Elsewhere:
  - the `xai-` regex in `vidbyte/providers/tracing/langsmith.py`
  - the README managed section (`:214-300`)
  - every test file listed in spec §13, at the cited lines
  - the three manual scripts

**Commands I ran (read-only)**

- `python lint/run.py`, which ends with `SDK-LINT: PASS`.
- `python lint/run.py --rule C017`, which reports CLEAN.
- An import-order trace in scratch, outside the repo. It proved that `vidbyte.lib.dataclasses.agents` loads before the registries package, and that the registries `__init__` reaches back into it through `vidbyte.agents.types`. This is the basis for D-21.

**External sources for key formats (D-19)**

- Anthropic, first-party:
  - platform.claude.com `manage-claude/authentication` (`sk-ant-api…`, example `sk-ant-api03-`)
  - `api/administration-api` (`sk-ant-admin`)
- OpenAI and the Gemini `AIza` form: gitleaks `config/gitleaks.toml`, a third-party source.
- Gemini `AQ.`: a Google staff post on discuss.ai.google.dev, which says that AI Studio now issues only `AQ.` keys.
- No first-party format page was found for DeepSeek, Kimi, OpenRouter, or xAI.

## Approaches weighed

1. **Chosen: a lib classifier plus resolved credentials.** `ProviderKeyMatcher` binds each key to a provider by its format alone, using an ordered table with a full match. `TextModelConfig.credentials()` returns one `TextCredentials` record that owns every precedence rule. Every child carries the whole list. This is one new file and two new classes. The deciding property is that a key's provider is a fact about the key, never about where it is used. That fact is what makes "children carry the full list" safe (INV-3), and it lets three separate per-provider key-dropping rules be deleted (D-13).
2. **Smaller, rejected: keep the single `api_key` and add only `vidbyte_api_key`.** It fails the user's "List only" choice and the rename (FR-15). It also leaves a cross-provider fallback with no key of its own.
3. **Prefix map, rejected: `sk-` to anthropic, as Prompt 5 sketched.** Five providers issue `sk-` keys, so this map would send OpenAI, DeepSeek, Kimi, and OpenRouter keys to Anthropic.
4. **Pricebook matching, rejected.** The pricebook holds no key formats, and the pricing registry already imports the models registry.
5. **Placement runner-up: the classifier in `vidbyte/lib/util/`.** It would avoid the import cycle. It was rejected because the util package's own rule admits only code with no SDK dependencies, and the classifier needs `ModelProvider`. The cycle is solved instead by a function-local import in `vidbyte.lib.dataclasses.agents` only, which the repo already does in `config.py`.

## Where I disagreed with the request or the handoffs

- **request.md §C open question 1, the unclassifiable key.** Its default was to raise with a provider guess and a redacted fingerprint, "unless the configured provider set makes the assignment unique".
  - I refuse unconditionally, and the error gives only the index and the length (D-2, D-17).
  - Binding by use would send one unknown key to every provider in a fallback chain, which breaks INV-3.
  - A fingerprint gives the developer no more help than the index of their own list.
  - Q-1 keeps the option open, with default **no**.
- **request.md §C open question 3, a list holding no key for the call's provider.** The note leans toward raising. I kept the briefing's settled rule instead: Vidbyte-paid, with no error (D-5).
  - "Makes sure … matches" is met by classification, because a key can only ever go to its own provider.
  - Raising would break a legitimate mixed chain, where Vidbyte pays for the primary and the developer's own key covers a backup.
  - Q-2 carries the stricter option, with default **no**.
- **§B.2 and §B.4 B4 back-compat ("a vb_live_ value in api_key stays Vidbyte-paid").** §C says Prompt 6 superseded this. The spec refuses a Vidbyte key inside `api_keys` or inside a provider environment variable (INV-13, EC-8, EC-13), so a Vidbyte key can never reach a vendor.
- **§B.4 B5 ("`resolve_vidbyte_api_key` and `vidbyte_key_follows_provider` stay").** I delete `vidbyte_key_follows_provider` and `find_vidbyte_api_key`. Once a list carries keys, they no longer have a job.
- **§B.4 B8 (fallback looks up "that provider's own key").** The spec does this through the full list, not through the old per-provider inheritance rule (D-13).
- **§B.4 B1 and B10 (re-vendor the contract; bump the version and publish).** The briefing settles that there is no re-vendor (NG-8). A version bump is NG-16, because releases are separate.
- **§B.4 "every existing test" does not change.** This is impossible once the user asked for the rename. Spec §13 lists every superseded test, with the spec ID that supersedes it.

## Assumptions I am least sure of

- **A-6, Gemini `AQ.` keys.** No source states their length or charset. The pattern is permissive: `AQ\.[A-Za-z0-9_.-]+`.
- **A-2 and A-3, DeepSeek and Kimi formats.** Both come from third-party sources only. A real key in another shape is refused, and the developer falls back to `DEEPSEEK_API_KEY` or `MOONSHOT_API_KEY`.
- **A-1, OpenAI formats.** I found no first-party OpenAI page. The rule follows gitleaks.
- **A-7, the backend contract.** It assumes the companion backend relays the provider's 401, 402, and 403 with the provider's own body, not the gateway's `"error": true` shape. The relay wording in table G depends on this.
- **D-10, streaming.** Default-mode streaming now breaks, and the caller must set `DIRECT`. This follows from "AUTO always uses the gateway", but users will notice it most.
- **NG-11 and EC-40, the algorithm helpers.** These are the context-window helpers: critic, grader, and prosecutor/defender/judge. They build runners with no key or mode, so in `AUTO` they now need `VIDBYTE_API_KEY` and cannot choose `DIRECT`.

## Notes for downstream agents

- **Test fixtures.** Today's fake keys ("test-key", "sk-mock", "main-key", and the like) are refused by the classifier. Fake keys must be built at runtime in shapes that classify but avoid secret-scanner patterns. Spec §13 lists the shapes.
- **origin/main has moved.** It was at 3ed3c627 when I checked, past base_commit. Rebasing is S6's job.

## Addendum r2 (2026-10-12): revision after the S1 review

Spec r2 is committed at 01b0bcf6. The frontmatter keeps `status: draft` for a scoped round-2 review. All six Major findings (R-1 to R-6) were accepted. Four of them follow the orchestrator's rulings (§0.2, §16).

**What changed in the design:**

- **Matching is two-tier.**
  - A proven key goes to its provider. Table F holds only five sourced prefix rules: anthropic, openrouter, openai (`sk-proj/svcacct/admin`), xai, and gemini.
  - Every other key is unproven. It is bound by unique assignment against the root's configured providers (primary plus named fallbacks or proposers), using the table A compatibility rules: anthropic, xai, gemini, and openrouter never take an unproven key; openai takes only `sk-…`; the rest take any. If one key could belong to more than one provider, the root raises M-19. If no provider could take it, it raises M-6. No length or charset shape decides a vendor (NG-18), so the DeepSeek, Kimi, and legacy-OpenAI rules are gone.
- **The result is carried, not re-matched.** It is a new record, `ProviderKeys`, defined in the agents dataclass module. Every child carries it unchanged and never re-matches the list (D-13). This is the third new class in the §8.4 budget, and there is still one new file. `FallbackModel` loses its key field (D-26).
- **The configured model must have its key (INV-24 / M-18).** A non-empty list that holds no key for the primary provider raises at construction. Children for other providers still relay or go Vidbyte-paid with no error.
- **A Vidbyte entry in the list is the Vidbyte key (D-25).** This follows orchestrator ruling (a).
- **The three smaller fixes.** R-4: the 422 remedy names DIRECT. R-5: the redactor covers tuples. R-6: the explicit Vidbyte key is format-checked at construction, inside `ProviderKeys`.

**Correction to the note above.** "test-key" and "main-key" are still refused for anthropic, xai, gemini, and openrouter, which take only proven keys. They now work for any provider without a prefix rule when that provider is the only configured one. "sk-mock" now works for an openai-only config. The fake-key guidance is in §13.

**Verified this round.**

- `vidbyte.lib.constants` and `vidbyte.lib.enums` import only enums, so `ProviderKeys`'s new module-level imports cannot close the D-21 cycle.
- In r1, row 16 was `lib/dataclasses/agents.py`. It is now row 3, and r1 rows 3–15 shift down by one.

The ID self-check is clean: no undefined references, no gaps except struck IDs, every EC guarded, and one CREATE row against a budget of one new file.

## Addendum r3 (2026-10-12): revision after the round-2 review

Spec r3 is committed at 74f0b83d with `status: approved`. All nine round-2 findings (R-7 to R-15) were applied as the orchestrator ruled, plus ruling 10 on prefix sources.

**What changed in the design:**

- **R-7: a record passed in is checked, not re-bound.** Step 1 checks each key against its provider (D-31, M-20). It never applies INV-24. Docs show developers only the list form.
- **R-8: every model an aggregate runs on is a primary.** Every spec-built proposer and the spec-built aggregator count as primaries for INV-24. `match` takes `primary` as a tuple for this. Prebuilt children add no primary.
- **R-9: restore matches the way the root did.** `ProviderKeys` carries `matched_primary` and `matched_others`. Checkpoints store them as `runtime_config["key_providers"]` (names only). `restore` re-matches against them, with `require_primary_key=False` when the restored agent's provider differs from the stored primary (D-30). A checkpoint from before this change matches as a root (EC-53). `BaseAgent` growth stays within the 30-line cap.
- **R-11: Q-7 = yes.** A lone unproven key binds to the one keyless primary that accepts it (D-29).
- **R-12: M-6 and M-7 split.** M-6 fires only when no configured provider accepts the key. M-7 fires when every provider that accepts it already holds a key. Keys are taken in index order.
- **R-13: provider keys must be sendable.** Two new constants (`VIDBYTE_PROVIDER_KEY_PATTERN`, `VIDBYTE_PROVIDER_KEY_MAX_LENGTH = 512`) and M-21 (D-32).
- **R-10 and R-15: wording and order.** R-10 states the wrong-vendor residual for unproven keys and adds Q-6 (default no). R-15 fixes the §12.6 order and adds row 41, the dataclasses package export.
- **Ruling 10: routing rules need first-party sources.** These now have them: `sk-ant-` (platform.claude.com), `sk-or-` (openrouter.ai docs), `sk-admin-` (OpenAI's API reference), `sk-proj-` (OpenAI's GitHub organization), `xai-` (docs.x.ai), and `AIza` + 35 (Google's example on cloud.google.com).
  - `sk-svcacct-` and `AQ.` stop routing.
  - A new refuse-only list, `RESERVED_PREFIXES`, stops either from being bound to another vendor by unique assignment. Without it, removing them would have opened a new path for a key to reach the wrong vendor.
  - `AQ.` keys in the list are refused (A-11), but `GEMINI_API_KEY` still works.

**R-14 evidence.** The Jev run-brief writer is built inside `JevAgent.__init__`, through the compute controller and the brief keeper (agent.py:51, keeper.py:31), so its match already runs before any request. The ruling's suggested `JevAgentSettings.__post_init__` check could not see the brief, because the brief lives in `JevRuntimeSettings.compute.brief`. `AgentRoleSettings` gained the two-line construction check.

**Other facts checked.**

- `SessionSerializer` drops a name only if it contains `API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, or `AUTH`, so `key_providers` survives a checkpoint.
- AC-32 was rewritten, because under D-29 a deepseek agent with a lone unproven key and a kimi fallback now binds the key to deepseek.

**Self-check.** No undefined IDs. No gaps except the struck NG-13, A-2, A-3, Q-1, Q-2, and Q-7. Every EC is guarded, and table columns are consistent. There is one CREATE row against a budget of one new file. New names appear in both §8.5 and §12.3.

## Addendum r4 (2026-10-12): the orchestrator's rulings on the r3 open items

Spec r4 keeps `status: approved`. It applies two orchestrator rulings and nothing else.

- **Ruling r4-1: `AQ.` routes to gemini.** Table F row 5 is now `(?:AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_-]+)`.
  - Sources: the `google-gemini` cookbook (tools/README.md, "legacy `AIza...` and new `AQ.Ab8...` formats"), plus two Google staff replies on discuss.ai.google.dev (threads 171575 and 170415: "AI Studio will now only generate Authentication Key (AQ) keys"). S1 re-read all three on 2026-10-12.
  - No source shows the characters after `AQ.`. The rule takes the same URL-safe set as the other rows. A key with any other character stays reserved to gemini and is refused, never sent elsewhere (A-11).
  - A-13 records the 401 `ACCESS_TOKEN_TYPE_UNSUPPORTED` reports and cites thread 179102. In that thread, Google staff say the failures are not due to the `AQ.` format. The 179102 citation is S1's own find; neither ruling-cited thread mentions that error code.
  - Updated: AC-29 (the `AQ.` sample now expects gemini), D-19, A-1, A-6, A-11, NFR-12, and §13 (`AQ.` fakes are built at run time). §9.4 item 10 is withdrawn.
- **Ruling r4-2: `RESERVED_PREFIXES` holds only `sk-svcacct-`.** D-28 says it is a refuse-only guard that closes a wrong-vendor path.
  - In r3 the list also held every table F prefix, which reserved a near-miss key: one that starts with a table F prefix but does not fully match the rule.
  - Dropping that guard would let unique assignment bind, for example, a dotted `xai-` token to deepseek. So it now comes from `KEY_FORMATS`, whose rows list their literal prefixes.
  - No new name is added. `KEY_FORMATS`'s element type gains the prefixes, in §8.5 and row 4.
  - AC-29 gains a dotted `xai-` sample. NFR-3 now counts 8 prefix checks.

**Self-check.** No undefined IDs. No gaps, except the struck NG-13, A-2, A-3, Q-1, Q-2, and Q-7. A now runs 1 to 13. Table columns are consistent. File paths appear only where the template allows them; the only other paths sit inside §0's verbatim text, lint commands, and URLs.
