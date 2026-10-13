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
