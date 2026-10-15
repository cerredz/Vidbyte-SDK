# S1 spec author report: public-skill-loader

Status: **DONE**. The spec is committed at `db1786a2` (`docs(spec): add public-skill-loader spec r1`) on `feat/public-skill-loader`. This report is not committed. The orchestrator's modified `pipeline.md` was left unstaged.

## 1. What I read

- **Doctrine.** In full: `house-style.md`, `spec-template.md`, and `vidbyte-gates.md`.
- **Request and recon.** In full: `request.md`, `context/code-map.md`, and `AGENTS.md`. `CLAUDE.md` is just `@AGENTS.md`.
- **Field guide.** The index, then these entries in full:
  - `local-ci-verification.md`
  - `blocking-lint-invariants.md`
  - `strict-config-dataclasses.md`
  - `comment-format.md`
  - `class-bound-helpers.md`
  - `review-scope.md`
  - `provider-api-contracts.md`
  - `prebuilt-agents.md`
  - `agents-md-map.md`
  - `declarative-config-resolution.md`
- **SDK source.**
  - Read in full: every file in `vidbyte/agents/skills/` (`loader.py`, `__init__.py`, `README.md`, `resolver.py`, `inline.py`, `local.py`, `markdown.py`, `github.py`, `vendor.py`, `fetch.py`, `skills_sh.py`, and `anthropic.py` from line 14 on), `vidbyte/lib/dataclasses/skills.py`, `vidbyte/lib/constants/skills.py`, `vidbyte/lib/enums/skills.py`, and `vidbyte/agents/jev/alignment/skills.py`.
  - Read in part: `vidbyte/agents/jev/settings.py:1-125`; `vidbyte/agents/jev/agent.py:75-95`; the import statements in `vidbyte/__init__.py` and the skill lines of its `__all__`; `vidbyte/lib/errors/base.py` (`VidbyteSdkError`, `ConfigurationError`); `vidbyte/lib/runners/text.py:88-102`; `vidbyte/agents/base.py:1050-1062`; `vidbyte/lib/http/transport.py` (one client per request); `vidbyte/lib/registries/models.py:168-177`; `vidbyte/lib/dataclasses/jev.py:3770-3790`; `vidbyte/lib/dataclasses/coding.py:145-156`.
- **Gate and contract tooling.**
  - Lint rules: the C011 header and suffix list, and the A009 header.
  - `scripts/generate-sdk-public-api.py`: the header and lines 60-130.
  - `scripts/run_ci.py:255-272`.
  - `contracts/README.md`, and the head, skill lines, and tail of `contracts/sdk-public-api.json`.
  - The baselines in `lint/baseline.json`, and `.github/workflows/static-policy.yml:20-32`.
- **Docs and maps.** `REPO_MAP.md:100-112` and `vidbyte/agents/README.md:290-300`.
- **Tests.**
  - `test_skill_sources_contract.py` in full.
  - The conftest header and its fixture list.
  - Every `SkillLoader(` and `JevSkillsPreload(` call site under `tests/`, read to confirm each passes a tuple with unique names.
  - The wording pins in `test_skill_sources_local.py:158-175` and `test_jev_skill_preload.py:155-196`.
- **Git history.** `git show --stat` of the 0.2.1 bump (`29fbfd28`), the 0.2.0 bump (`90f36272`), and the docs file list of #904. File names only; nothing under `docs/` was opened.
- **Consumer (read-only).** The vidbyte-cli S1 report in full; vidbyte-cli `code-map.md:400-430`; the CLI's `services/mcp/sdk.py` imports (how it reaches SDK errors).
- **Commands I ran.** All were read-only:
  - `git grep` for the version literals.
  - Python probes that only import from the worktree or run in my scratchpad: the vendor environment-variable names and endpoints, root `__all__` membership, the current loader's behavior on bad inputs, import order in fresh processes, and the §4 snippet's first two output lines.

## 2. Approaches weighed

1. **Root-export only** (the smallest). Add `SkillLoader` and `SkillResolution` to the root, bump the version, and change nothing else. **Rejected.** I ran the current loader on bad inputs:
   - A generator silently gives `()`.
   - A str gives `KeyError: 'a'` from `load()`.
   - `None` gives `KeyError`; a dict gives `TypeError`.
   - The same `LocalSkill` twice gives `ValueError: too many values to unpack`, which aborts every entry.

   A public door cannot crash on its own argument. That violates the settled "not as a crash" and AGENTS.md §4 ("fails at the boundary where it enters").
2. **Expose the existing loader and validate at the boundary** (**chosen**). Root-export `SkillLoader`, `SkillResolution`, and `ConfigurationError`. Add one frozen record, `SkillEntries`, in `vidbyte/lib/dataclasses/skills.py`, built as the first step of `SkillLoader.__init__`; the signature is unchanged. Bump to 0.2.2 and update the four texts that say JevAgent is the only consumer.
   - **Budget:** 0 new files and 1 new class; 14 files modified, one of them the regenerated contract.
   - **Why:** request.md §C says "prefer exposing the loader that already exists". AGENTS.md §4 and the Placement Rules put validation in a dataclass's `__post_init__`. Two precedents fit: `CodingAgent.__init__` builds `CodingAgentSettings` (`coding.py:74`, with its tuple check at `lib/dataclasses/coding.py:152-153`), and `JevSkillsOutcome` checks a tuple of records.
3. **A public facade** (**runner-up**): `SkillSources.resolve(entries)`, which builds a fresh loader per call.
   - **For:** it keeps `memory`, `resolvers`, and `documents()` off the public surface.
   - **Against:** it is a layer that only forwards, and it drops memory.
   - **Flips if:** the owner wants the loader's internals private, or wants to restructure the loader in a patch release.

I also decided against these, each recorded as an optional `Q-n` with default no:
- a sync twin (D-2, Q-2);
- a caller byte limit (D-7, Q-3);
- a source-string parser (D-9, Q-4);
- a release-note doc (D-10, Q-5);
- a loader-level credential (D-8, Q-6);
- rewording the pinned agent-centric details (D-11, Q-7).

## 3. Where I disagreed with the scout, the request, or the briefing (with evidence)

- **"No caller can pass a credential today"** (briefing item 3's wording). This is wrong. Credentials are per entry (`GitHubSkill.token`, `AnthropicSkill.api_key`, `OpenAISkill.api_key`), and those classes are already root exports. What is missing is only a loader-level credential parameter, which is the scout's actual claim. The scout is right that the loader reads `GITHUB_TOKEN` (`github.py:141`, with `os.environ.get`, so unset means anonymous) and the vendor keys (`vendor.py:121` through `ProviderModelRegistry.resolve_api_key`) itself, and only inside `load()`.
- **`ConfigurationError` is not a root export** (checked: `'ConfigurationError' in vidbyte.__all__` is `False`), and neither is `VidbyteSdkError`. Neither the scout nor the briefing raised this. Every #904 entry constructor raises it for invalid input. The CLI reaches SDK errors today only through a deep dynamic import (`vidbyte-cli: src/vidbyte_cli/services/mcp/sdk.py:31,71`), and its C028 counts that against its baseline. Under consumer item 6 ("every name the CLI needs"), I added it as FR-3 (D-5). I also carry it as Q-1 (non-blocking, default **built**) so the user can veto it.
- **Duplicate names.** The scout recorded "two equal entries share one result". That is true only after the result is remembered. On a fresh loader, two equal single-entry-source entries crash `load()` (EC-4, observed). The spec therefore rejects repeated names, the same rule the Jev door already enforces (D-4).
- **The field guide's `AgentFallbackConfig` precedent** (`strict-config-dataclasses.md`) no longer exists in `vidbyte/lib/dataclasses/` (a grep finds nothing). I cited `CodingAgentSettings` instead.
- **Release-note doc.** Both the 0.2.0 and the 0.2.1 bumps added `docs/design/release-0-2-X.md`, by the `--stat` file names. No AGENTS.md rule requires one, request.md §C's list of literals omits it, and copying its form would mean reading `docs/design/`, which AGENTS.md forbids. Not built (D-10), with Q-5 asking.
- **The "1 MiB SKILL.md" in consumer item 4** measures the whole file, frontmatter included, before decoding. `SkillDocument.text` is the body only, and `InlineSkill.text` has no cap at all. The spec states this exactly (§9.2 row 4).

## 4. Assumptions I am least sure of

- **Q-1 / D-5, exporting `ConfigurationError`.** It is in scope only because I read consumer item 6 as covering the error raised by the public door and by the entry constructors. A strict reading of the scope rule could call it an addition. It is easy to remove: FR-3, row 3(d), and its mentions in §4 and §9.2.
- **D-4, rejecting different entries that share a name.** If the CLI wants two same-named skills from different sources, relax the check to reject only equal entries.
- **D-3, a one-field record versus an inline check.** A reviewer could call the record overbuilt. I chose it because AGENTS.md §4 and the field guide put boundary validation in a dataclass's `__post_init__`.
- **A-5, the baseline.** The S0 briefing reports the gate at 5,173 passed and 14 skipped. S1 did not re-run it.
- **Strict tuple only (EC-6).** A list is rejected. Every in-repo caller passes a tuple, but the CLI must write `tuple(...)`.

## 5. Notes

- Partway through Stage B the C: drive reported 0 bytes free ("No space left on device"). It recovered to about 1.3 GB before I wrote the spec, and no data was lost. If later stages fail on writes, check free disk space first.

## Answers to consumer requirements

These are the answers the vidbyte-cli pipeline (`agent-skill-sources`) should resume from. The full table is spec §9.2, "Consumer contract".

1. **The callable and the result shape.**
   - Build `SkillLoader(entries)`, where `entries` is a **tuple** of entry objects (and/or `SkillDocument`s) with unique names. Construction validates the tuple, does no I/O, and raises `ConfigurationError` on a bad argument.
   - Then call `await loader.load()`. It returns `tuple[SkillResolution, ...]`, one result per entry, in input order, so pair them with `zip(entries, results, strict=True)`. No agent is constructed.
   - **Success:** `result.document` is a `SkillDocument`, and the text to append is `result.document.text`. Also available: `.name`, `.description`, and `.source`, a label such as `github:owner/repo@sha12/skills/pdf/SKILL.md`.
   - **Failure:** `result.document is None`. `result.reason` is a `SkillUnavailableReason`: `not_installed`, `not_found`, `auth_failed`, `rate_limited`, `fetch_failed`, `invalid_skill`, or `too_large` (never `decision_failed`). `result.detail` is a non-blank, SDK-written explanation that names the fix and never contains a secret or file text.
   - `result.transient` is `True` for `rate_limited` and `fetch_failed`, which a later `load()` on the same loader retries.
   - Expected failures never raise. Only a programming error or cancellation propagates.
2. **Async.** `load()` is `async`. Inside a running event loop, use `await loader.load()`. From synchronous command setup, use `asyncio.run(loader.load())`; calling that inside a running loop raises asyncio's own `RuntimeError`.
   - **Why no sync twin:** the loader runs concurrent I/O on asyncio. The SDK's sync-twin pattern (`TextModelRunner.run`, `vidbyte/lib/runners/text.py:93-100`) raises inside a running loop, so a twin would add nothing.
   - **Lint:** in the SDK, C011 is the sync-twin rule, and it covers only `*Agent`, `*Runner`, `*Harness`, `*Session`, and `*Machine` classes with `arun()`, not `SkillLoader.load()`. (The CLI's own C011 is a different rule.)
   - **Reuse:** a loader can be loaded again on a new event loop.
3. **Credentials.** Pass them per entry:
   - `GitHubSkill(..., token=...)`
   - `AnthropicSkill(..., api_key=...)`
   - `OpenAISkill(..., api_key=...)`

   **The loader reads the environment itself**, only inside `load()` and only when the entry's field is `None`:
   - `GITHUB_TOKEN` is read with `os.environ.get` and stripped; unset or blank means an anonymous request.
   - `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are read through the SDK's provider registry and stripped; missing means `auth_failed` with no request.

   There is no loader-level credential parameter. To use the CLI's keyring token, pass it as `token=` on each `GitHubSkill`; to keep the environment out of vendor reads, pass `api_key=`. `token=""` is rejected when the entry is built, so to force anonymous GitHub reads while `GITHUB_TOKEN` is set, unset the variable.

   Credentials are sent only to `api.github.com` or the vendor's fixed endpoint, never follow redirects, and never appear in details, labels, URLs, or reprs. A Vidbyte API key is refused with `auth_failed` before any request.
4. **Size.**
   - **The SDK's limits.** `SKILL_MARKDOWN_MAX_BYTES = 1_048_576` is inclusive and counts the **whole SKILL.md file in bytes, frontmatter included**, for local, skills.sh, GitHub, and vendor files. `SKILL_DOWNLOAD_MAX_BYTES = 33_554_432` bounds other downloads (GitHub commit and tree answers, vendor zips and records). Inline text and caller documents have no SDK cap.
   - **What the text is.** `document.text` is the body after the frontmatter, so it is smaller than the file.
   - **Oversize.** It comes back as `reason=too_large` with a detail giving the size and the cap. It is never truncated and never raised, and it is remembered by that loader.
   - **No caller byte limit.** The CLI enforces its 20,000-byte budget itself: measure `len(result.document.text.encode("utf-8"))`, sum it across everything you append, and turn an over-budget skill into your own structured failure. Because `SkillResolution` is now public and validates itself, you can build `SkillResolution(reason=SkillUnavailableReason.TOO_LARGE, detail="...")` and get the same vocabulary. Never truncate.
   - **Why the budget stays on the CLI side.** The budget is a total across all instructions, which no per-entry SDK limit can enforce. A per-call limit would also clash with the loader's memory. JevAgent applies its own budget the same way.
   - **Trade-off.** A skill of up to 1 MiB is downloaded before you can measure it.
5. **Parser: none.** The CLI parses `github:owner/repo/path`, `skills.sh:<id>`, and local paths itself, and builds entry objects. The constructors validate every field and raise `ConfigurationError`, which the CLI can catch by its root name. The SDK parser is optional Q-4, default not built.
6. **Root names** (exactly as they appear in `vidbyte.__all__` and `contracts/sdk-public-api.json`):
   - **New in 0.2.2:** `ConfigurationError`, `SkillLoader`, `SkillResolution`.
   - **Already root:** `AnthropicSkill`, `GitHubSkill`, `InlineSkill`, `LocalSkill`, `OpenAISkill`, `SkillDocument`, `SkillEntry`, `SkillSourceType`, `SkillUnavailableReason`, `SkillsShSkill`.
   - **Not root, and not needed by the CLI:** `SkillEntries` (internal validation record) and `SkillFetchStep`.
7. **Version.** `0.2.2` appears in `pyproject.toml`, `vidbyte/__init__.py` (`__version__`), `vidbyte/cli/__init__.py`, `vidbyte/mcp_server/server/core.py`, `vidbyte/tools/mcp/client.py`, `README.md`, `llms.txt`, `.github/ISSUE_TEMPLATE/bug_report.yml`, and the regenerated contract (`"version": "0.2.2"`). The contract is regenerated in its own commit after the source commit, so its `source.commit` names this PR's source commit. Publishing to PyPI is the user's call after review.
