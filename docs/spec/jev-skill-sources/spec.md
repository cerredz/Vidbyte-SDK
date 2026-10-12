---
spec: jev-skill-sources
title: JevAgent skill sources — declarative skill entries resolved under the hood
status: approved
revision: 3
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-skill-sources
branch: feat/jev-skill-sources
base_commit: ba3e4ca51ad78c44026dfd296663ae7b092bce56
created: 2026-10-12
updated: 2026-10-12
pr:
---

# Spec: JevAgent skill sources — declarative skill entries resolved under the hood

> **TL;DR** — `JevAlignmentSettings.skills` now accepts six small declarative entries (`InlineSkill`, `LocalSkill`, `SkillsShSkill`, `GitHubSkill`, `AnthropicSkill`, `OpenAISkill`) next to today's strings and `SkillDocument`s. An internal `SkillLoader` in a new agent-agnostic `vidbyte.agents.skills` package resolves them lazily on the first run that reaches the skill preload, one resolver subclass per source, and remembers successes and permanent failures for the agent's lifetime. The decision that matters most: **loading never fails a run** — every way a source can go wrong ends as an `UNAVAILABLE` result carrying a new `SkillUnavailableReason` and a `detail` that names the fix, while cancellation and programming errors still propagate.

## §0 User prompts

### 0.1 Invoking request (verbatim)
great, you can implement the 3 skill sources we talked about AND the localskill, and OpenAISkill. Make sure that for each type of skill we are handing the edge cases/failure modes of each skill in the way that they could go wrong in the spec and all throughout the implementation. Try to decompose the files for the skills into subclasses for each of  the different skill types. (want the actual  core skills code logic to go  inside of vidbyte-sdk/vidbyte/agents/skills). and then attach it/load it onto the JevAgent

### 0.2 User replies during the run
_None yet. The orchestrator appends any reply the user sends during the run here verbatim, labeled with the revision it produced._

---

## Part A — Framing

## §1 Goal

Today a developer who wants JevAgent to choose among skills must read every skill's text into a `SkillDocument` (or a plain string) themselves; the shipped docs page says "Loading skills from other sources comes later … For now, load each skill's text yourself" (request.md, Prompt 1), and the feature pack says "network/source loaders and native provider skill references are deferred". The user asked for "simply an array of skills" where "under the hood we handle the actual SkillLoader class" (Prompt 2), for five sources plus inline text (Prompt 3), and for every failure mode of every type to be handled "in the spec and all throughout the implementation" (Prompt 3).

| ID | Goal (outcome) | How we will know | Source |
|---|---|---|---|
| G-1 | A developer attaches skills from inline text, a local folder, skills.sh, GitHub, Anthropic's Skills API, and OpenAI's Skills API by listing declarative entries, without constructing a loader or a `SkillDocument`. | The §4 snippet runs as written (AC-1); construction performs no I/O (AC-2). | Prompt 2, Prompt 3 |
| G-2 | Every way a source can fail ends as an explained, per-skill `UNAVAILABLE` result (reason + a detail that names the fix) and the run continues with the remaining skills. | Every §6.3 row is guarded; AC-6, AC-12, AC-14 hold. | Prompt 3 ("edge cases/failure modes of each skill"); request.md §C "Fail-open", "Every result explains itself" |
| G-3 | A long-lived agent pays each source once: after a success or a permanent failure, later runs make zero source calls; a transient failure is retried on the next run. | NFR-2, NFR-3; AC-7, AC-10. | request.md §C "What the cache remembers" |
| G-4 | Secrets never leak, untrusted archives cannot exhaust memory or touch disk, and the SDK never runs `npx` or follows a redirect with a key. | INV-11 to INV-14; AC-11, AC-12, AC-13. | request.md §C "Secrets", "Rejected alternatives" |

## §2 Objective

When this PR merges, `vidbyte` exports six frozen entry classes over one base `SkillEntry`, each with a read-only `type` (`SkillSourceType`), plus `SkillUnavailableReason`; `JevAlignmentSettings.skills` accepts them alongside plain strings and `SkillDocument` values and still rejects duplicate names at construction. A new package `vidbyte.agents.skills` holds the agent-agnostic loading logic: `SkillLoader` (groups entries that share lookups, resolves every group concurrently, remembers results per policy), a generic `SkillResolver` base with one resolver subclass per source in its own module (`InlineSkillResolver`, `LocalSkillResolver`, `SkillsShSkillResolver`, `GitHubSkillResolver`, `AnthropicSkillResolver`, `OpenAISkillResolver`, the last two over a shared `VendorSkillResolver`), a shared `SKILL.md` parser (`SkillMarkdown`), and a shared HTTP step (`SkillFetch`) over `HttpTransport`. `JevSkillsPreload` owns one `SkillLoader` for the agent's lifetime, loads on each run before batching, and reports every unusable skill with `JevSkillResult.reason` and `.detail`. Records live in the existing `skills` domain modules under `vidbyte.lib`, constants in a new `vidbyte.lib.constants.skills` module, the public API contract is regenerated, and the repo map and package README describe the new package. This is the whole feature; nothing is deferred to a later PR.

## §3 Non-goals

- **NG-1** — `WellKnownSkill`, `VidbyteSkill`, `PackageSkill`, GitLab or generic git URLs. — *Why not:* discussed as candidates, not chosen in Prompt 3 ("the 3 skill sources we talked about AND the localskill, and OpenAISkill").
- **NG-2** — Running `npx`, any subprocess, or calling the skills.sh REST API. — *Why not:* rejected in the conversation (Node runtime, network, telemetry, Vercel OIDC-only auth; "no CLI behaviour in the SDK").
- **NG-3** — Native provider attachment (Anthropic `container.skills`, OpenAI `skill_reference`). — *Why not:* works only when the main model is that vendor's code-execution model and bypasses Jev's selection.
- **NG-4** — Judging oversized skills on name and description only. — *Why not:* offered as Q3 in the conversation, not chosen; oversized skills stay `UNAVAILABLE` with `TOO_LARGE`.
- **NG-5** — Loading a skill's supporting files (`references/`, `scripts/`, assets). — *Why not:* agreed that `text` is the `SKILL.md` body only; skills that point to other files degrade (documented limitation).
- **NG-6** — Any `vidbyte-sdk` CLI command or flag. — *Why not:* standing owner rule; no SDK CLI commands, ever.
- **NG-7** — A refresh or invalidate API, a time-to-live, or a process-wide cache shared between agents. — *Why not:* not discussed; the agreed cache lifetime is the `JevAgent` instance. Re-creating the agent is the refresh.
- **NG-8** — GitHub Enterprise hosts, custom vendor base URLs, or proxies for skill fetches. — *Why not:* not discussed; each source talks to its one default host.
- **NG-9** — Changing Jev's skill question wording, the threshold, or the batching byte limits. — *Why not:* core preload behavior is out of scope; only the per-skill outcome gains a reason.
- **NG-10** — Making `SkillDocument` internal or removing any export. — *Why not:* orchestrator decision; it stays public and accepted (supersedes request.md's "becomes internal"), and the existing test asserts the root export.
- **NG-11** — Verifying the skills.sh `computedHash`, or listing an Anthropic or OpenAI workspace's skills. — *Why not:* not agreed; the hash only labels the result, and each vendor entry carries its own `skill_id`.
- **NG-12** — Updating the external docs site or the in-repo JevAgent skill guide. — *Why not:* the docs site lives in another repository; the in-repo guide never described the preload (see Q-4).
- **NG-13** — Loading a `SKILL.md` at a GitHub repository's root (`path="."`). — *Why not:* not discussed in the conversation; recorded as Q-6, default not built (r2, R-8).

## §4 Developer usage

```python
from vidbyte import (
    AnthropicSkill, GitHubSkill, InlineSkill, JevAgent, JevAgentSettings,
    JevAlignmentSettings, LocalSkill, SkillsShSkill,
)

skills = (
    InlineSkill(name="house-review", description="Our PR review checklist.", text="Read every edited function and its tests first."),
    LocalSkill(name="sql-migrations", path="skills/sql-migrations"),                # reads skills/sql-migrations/SKILL.md
    SkillsShSkill(name="react-best-practices", source="vercel-labs/agent-skills"),  # the copy `npx skills add` installed
    GitHubSkill(name="webapp-testing", repo="anthropics/skills", ref="v1.2.0"),
    AnthropicSkill(name="release-notes", skill_id="skill_01AbCd"),                 # key from ANTHROPIC_API_KEY
)
agent = JevAgent(JevAgentSettings(name="dev-assistant", system_prompt="You help engineers review and ship code.",
    provider="openai", model_name="gpt-4.1-mini", alignment=JevAlignmentSettings(skills=skills)))  # reads and fetches nothing

reply = await agent.arun("Review PR 182 and check it doesn't break the public API.")
for skill in agent.response.skills.results:
    print(skill.name, skill.status.value, skill.reason.value if skill.reason else "-")
# house-review selected -
# sql-migrations skipped -
# react-best-practices unavailable not_installed
# webapp-testing selected -
# release-notes unavailable auth_failed
```

The output shown is for a machine where `npx skills add` was never run and `ANTHROPIC_API_KEY` is unset; the `selected`/`skipped` lines depend on Jev. The developer no longer reads files, calls APIs, or builds `SkillDocument`s: they list where each skill lives, and each unusable skill's `detail` says exactly what to do (here, run `npx skills add vercel-labs/agent-skills --skill react-best-practices`, and set `ANTHROPIC_API_KEY`).

## §5 Flow diagram

```mermaid
flowchart TD
  A[JevAgent.__init__] -->|settings.alignment.skills| B[JevAlignmentSettings: validate entries, unique names]
  B -->|entries| C[JevSkillsPreload.__init__ builds SkillLoader once]
  R[JevAgent.arun] --> G{gate stop or specialist?}
  G -->|yes| X[return: no source contacted, results empty]
  G -->|no| P[JevRuntime._preload_skills]
  P --> L[JevSkillsPreload.run calls SkillLoader.load]
  L -->|pending entries grouped by type and group key| M[(remembered resolutions)]
  L -->|concurrently, one call per group| S1[InlineSkillResolver]
  L --> S2[LocalSkillResolver: disk in a worker thread]
  L --> S3[SkillsShSkillResolver: installed copy + skills-lock.json]
  L --> S4[GitHubSkillResolver: SHA, tree once, raw SKILL.md]
  L --> S5[Anthropic and OpenAI resolvers: version zip or bare SKILL.md in memory]
  S2 & S3 & S4 & S5 -->|raw SKILL.md bytes| MD[SkillMarkdown.parse]
  S1 & MD -->|SkillResolution per entry| L
  L -->|remember success + permanent failure| M
  L -->|resolutions in settings order| SEED[seed JevSkillResult per entry]
  SEED --> BB[_build_batches reads loader.documents]
  BB -->|JevSkillBatch| J[DecisionModelHelper.arun per batch]
  J -->|answers| SC[_score_skill]
  SC -->|JevSkillsOutcome| RESP[JevResponse.skills]
  SC -->|selected documents| AP[_append_selected: run context]
  AP --> MAIN[main agent loop]
```

```mermaid
sequenceDiagram
  participant L as SkillLoader
  participant G as GitHubSkillResolver
  participant H as api.github.com
  L->>G: resolve((webapp-testing, pdf, docx))  same repo, ref, token
  G->>H: GET /repos/o/r/commits/{ref}  Accept: vnd.github.sha
  H-->>G: 40-hex SHA
  G->>H: GET /repos/o/r/git/trees/{sha}?recursive=1  (only if an entry has no path)
  H-->>G: tree paths
  par one per entry
    G->>H: GET /repos/o/r/contents/{folder}/SKILL.md?ref={sha}  Accept: vnd.github.raw
  end
  G-->>L: three SkillResolution values, in order
```

Validation of every entry field happens once, at construction, in the records themselves; construction does no I/O. The loader groups the pending entries that share lookups (a single entry per group, except GitHub entries with the same repo, ref, and token) and calls each group's resolver once, all groups at the same time; each resolver's `resolve` is its one main function (D-22). State changes in exactly one place: `SkillLoader.load` writes the remembered resolutions after all resolvers return. Expected source failures are caught inside each resolver (or inside `SkillFetch` for transport errors and the per-step deadline) and become `SkillResolution` values with a reason; the loader and the preload never catch broad exceptions, so cancellation and programming errors leave `arun` unchanged. Jev failures are caught where they are today, per batch, and now carry `DECISION_FAILED`.

---

## Part B — Behavior (this is the spec; everything else is framing)

## §6 Behavior

### 6.1 Invariants

**Construction**
- **INV-1** — Constructing any entry, `JevAlignmentSettings`, `JevSkillsPreload`, `SkillLoader`, or `JevAgent` never reads a file, never makes a network request, and never reads a skill-source environment variable (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). Pinning a relative path to an absolute one uses the process working directory only (no filesystem access).
- **INV-2** — Every entry's fields are validated in `__post_init__`; an invalid field raises `ConfigurationError` naming the class and field. Passing `type=` or a field the class does not have (for example `text` on `GitHubSkill`) raises `TypeError`. `SkillEntry` itself cannot be constructed.
- **INV-3** — Every configured skill name is unique across entries, `SkillDocument` values, and normalized strings; a duplicate raises `ConfigurationError` with `details={"names": [...]}` at construction.

**Loading and memory**
- **INV-4** — Loading happens only inside a run that reaches the skill preload. A run stopped by the preflight gate or delegated to a specialist contacts no skill source.
- **INV-5** — After a load, an entry whose resolution is a document or a permanent failure (`NOT_INSTALLED`, `NOT_FOUND`, `AUTH_FAILED`, `INVALID_SKILL`, `TOO_LARGE`) is remembered for the agent's lifetime, is never loaded again, and is never replaced (r2, R-14); an entry whose resolution is transient (`RATE_LIMITED`, `FETCH_FAILED`) is never remembered and is loaded again on the next run that reaches the preload.
- **INV-6** — The memory is per `SkillLoader`, which lives exactly as long as its `JevAgent`; no module-level or process-wide cache exists, two agents never share resolutions, and the number of remembered entries never exceeds the number of configured entries.
- **INV-7** — Within one load, every group of pending entries resolves concurrently, where a group is the entries of one type that share `SkillResolver.group_key` (a single entry, except GitHub entries with the same `repo`, `ref`, and `token`); within one GitHub group the commit lookup happens at most once and the tree listing at most once.
- **INV-8** — A failure in one entry's own steps never changes another entry's resolution; entries in one GitHub group share only the group's commit lookup and tree listing, and a failure of a shared step applies to exactly the entries that needed it.
- **INV-9** — Loading never raises for an expected source failure (the classes and statuses in §9.2); the run continues. Cancellation (`asyncio.CancelledError`) and programming errors (any exception not listed in §9.2) propagate out of `arun` unchanged and are never turned into an `UNAVAILABLE` result.
- **INV-10** — After `SkillLoader.load()` returns resolutions `r`, `SkillLoader.documents()[i]` is `r[i].document` for every index `i`, also when two loads overlap: each load returns the remembered resolution where one exists (r3, R-20).

**Content**
- **INV-11** — A loaded skill's `text` is exactly the bytes of `SKILL.md` after the closing frontmatter line, decoded as strict UTF-8 with one leading byte-order mark removed; it is never trimmed, rewritten, truncated, or prefixed with frontmatter. The result's `name` is the entry's `name`; its `description` is the frontmatter `description`.
- **INV-12** — Nothing besides one `SKILL.md` is read from any source. No `SKILL.md` larger than `SKILL_MARKDOWN_MAX_BYTES` is loaded; no download (zip, tree listing, metadata) larger than `SKILL_DOWNLOAD_MAX_BYTES` is held in memory; zip members are never extracted to disk; the loader writes nothing to disk.
- **INV-13** — The SDK never runs `npx` or any subprocess, never calls the skills.sh API, and never executes, follows, or fetches anything a skill's text mentions.

**Secrets**
- **INV-14** — `GitHubSkill.token`, `AnthropicSkill.api_key`, `OpenAISkill.api_key`, and their environment fallbacks never appear in `repr` of an entry or settings object, in a source label, in a `detail`, in `JevAgent.response`, or in any message the loader writes. They are sent only as request headers to that source's fixed host, and no request follows a redirect.
- **INV-15** — A key or token beginning with `VIDBYTE_API_KEY_PREFIX` once surrounding whitespace is stripped (r3, R-18), whether an entry field or the `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` fallback, is never sent to GitHub, Anthropic, or OpenAI; the entry is `AUTH_FAILED` without a request (r2, R-4).

**Results**
- **INV-16** — Every run that reaches the preload records exactly one `JevSkillResult` per configured entry, in settings order, including when every source fails.
- **INV-17** — A result is `UNAVAILABLE` if and only if it carries a `reason`, and it carries a `reason` if and only if it carries a non-blank `detail`; `SELECTED` and `SKIPPED` results have neither. `description` is `None` only on an `UNAVAILABLE` result whose source never produced a document, and such a result's `source` is also `None` (a caller's `SkillDocument` without a source keeps `source=None` as today).
- **INV-18** — A `detail` or source label never contains skill text, a response body, a key, or a token, and a source label never contains a local machine path (r2, R-10). Local `not_found`/`not_installed` details do name the absolute path checked, as the conversation agreed.
- **INV-19** — Every outbound request goes through `HttpTransport` with `SKILL_FETCH_TIMEOUT_SECONDS`, `SKILL_FETCH_RETRY_COUNT`, `SKILL_FETCH_BACKOFF_SECONDS`, a `max_response_bytes` cap, and `follow_redirects=False`, and every fetch step, retries included, ends within `SKILL_FETCH_DEADLINE_SECONDS` (r2, R-2).

**Must not regress:**
- **INV-20** — Plain strings normalize to `SkillDocument(name=f"inline_skill_{position}", description="Caller-supplied inline skill text.", text=<exact>, source="inline")`, with position counted from 1 over the whole tuple (settings `JevAlignmentSettings._normalized_skills`).
- **INV-21** — `SkillDocument` stays the same object exported from `vidbyte`, `vidbyte.agents`, `vidbyte.agents.jev`, `vidbyte.lib`, and `vidbyte.lib.dataclasses`, and is accepted in `skills` unchanged; `JevSkillStatus` stays exported from `vidbyte`.
- **INV-22** — A skill too large to fit in a Jev batch on its own is `UNAVAILABLE` and never cut short (`JevSkillsPreload._build_batches`); it now carries reason `TOO_LARGE`.
- **INV-23** — A failed Jev batch, or a reply without token counts, leaves only that batch's skills unavailable; other batches' answers stand; usage totals only answered batches; a non-`VidbyteSdkError` from a batch propagates (`JevSkillsPreload.run`).
- **INV-24** — Selected texts are appended in settings order after `JEV_SKILLS_PROMPT_SECTION`, joined by `"\n\n---\n\n"`, to this run's context only; `JevAgent.response` never contains skill text (`JevSkillsPreload._append_selected`, `JevResponse.skills`).
- **INV-25** — With no skills, `JevAgent.skill_preload` is `None`; a preload built with `()` makes zero Jev calls, returns the same context object, and records `results == ()`.
- **INV-26** — `JevSkillsPreload(skills=<tuple of SkillDocument>, decision=..., threshold=..., response=...)` keeps its keyword signature and its `decision` attribute, and `_build_batches(message)` with one argument, called before any run, batches every document in settings order.
- **INV-27** — An explicit `options["system"]` is still the baseline that selected skills append to; a gate stop or specialist hand-off still records empty skill results (`JevRuntime._preload_skills`, `JevRuntime._arun_metered`).

### 6.2 Acceptance criteria

| ID | Given | When | Then | Priority | Proof |
|---|---|---|---|---|---|
| AC-1 | a clean checkout of this branch; no `.agents/skills` folder; `ANTHROPIC_API_KEY` unset; `skills/sql-migrations/SKILL.md` present with valid frontmatter; GitHub answered at the transport seam with a valid `SKILL.md` for `skills/webapp-testing`; Jev answering 0.9 for house-review and webapp-testing and 0.1 for sql-migrations | the §4 snippet runs | it prints exactly the five shown lines | P0 | `test_skill_sources_acceptance.py::test_developer_snippet_prints_the_documented_lines` |
| AC-2 | entries of all six types pointing at missing folders and unreachable hosts, and env vars unset | a `JevAgent` is constructed with them | construction succeeds with zero file reads, zero HTTP requests, and zero reads of the three env vars | P0 | `test_skill_sources_acceptance.py::test_construction_reads_no_file_sends_no_request_and_reads_no_key` |
| AC-3 | `InlineSkill(name, description, text)` whose text has leading spaces and a trailing newline | a run selects it | the appended text equals the field byte for byte and its result `source` is `"inline"` | P0 | `test_skill_sources_jev_wiring.py::test_inline_text_is_appended_byte_for_byte` |
| AC-4 | a `LocalSkill` folder whose `SKILL.md` has a BOM, CRLF line endings, YAML frontmatter with a folded description, and a body | a run loads it | the document's text is the exact body after the closing line, the description is the YAML value, the name is the entry name, and the source is `local:<folder name>` | P0 | `test_skill_sources_local.py::test_local_skill_loads_the_exact_body_under_its_folder_name` |
| AC-5 | a `SkillsShSkill` installed under `<root>/.agents/skills/<name>/` and a `<root>/skills-lock.json` whose entry's `source` equals the entry's `source` | a run loads it | it loads, and the source label is `skills_sh:<source>/<name>@<first 12 chars of computedHash>` | P0 | `test_skill_sources_skills_sh.py::test_installed_skill_loads_with_the_lock_hash_in_its_label` |
| AC-6 | a `SkillsShSkill` that is not installed | a run reaches the preload | the result is `UNAVAILABLE`, reason `NOT_INSTALLED`, and the detail contains `npx skills add <source> --skill <name>` and the absolute path checked | P0 | `test_skill_sources_skills_sh.py::test_missing_install_is_not_installed_with_the_install_command_and_path` |
| AC-7 | three `GitHubSkill` entries for one repo and ref, no `path`, no token | the first run loads them | exactly one commit lookup, one tree listing, and three raw fetches are made; each label contains the first 12 characters of the SHA | P0 | `test_skill_sources_github.py::test_one_repo_and_ref_share_one_commit_lookup_and_one_tree_listing` |
| AC-8 | an `AnthropicSkill` with an `api_key`, and the content download answering a zip holding `<folder>/SKILL.md` | a run loads it | the document is the body of that `SKILL.md`; the request carried `x-api-key`, `anthropic-version`, and `anthropic-beta` headers and no `authorization` header | P0 | `test_skill_sources_vendor.py::test_anthropic_archive_loads_only_its_skill_md_with_vendor_headers` |
| AC-9 | an `OpenAISkill` with an `api_key`, and the content download answering a zip holding `skill.md` at the archive root | a run loads it | it loads; the request carried `authorization: Bearer <key>` | P0 | `test_skill_sources_vendor.py::test_openai_archive_with_a_root_skill_md_loads_with_a_bearer_key` |
| AC-10 | one entry each that succeeds, fails permanently (404), and fails transiently (503 twice) on run 1 | run 2 and run 3 happen with the transient source now healthy | run 2 sends requests only for the transient entry; run 3 sends none | P0 | `test_skill_sources_memory.py::test_remembered_entries_cost_nothing_and_transient_ones_retry` |
| AC-11 | entries and settings holding a token and API keys, and a run where every source fails | `repr` of entries, settings, `agent.response`, and every result field are inspected | no key or token string appears anywhere | P0 | `test_skill_sources_security.py::test_secrets_never_leave_their_own_request_header`, `::test_settings_repr_hides_secrets_before_any_run` |
| AC-12 | `OPENAI_API_KEY` holding a `vb_live_` key and an `OpenAISkill` without `api_key` | a run reaches the preload | the result is `AUTH_FAILED` and zero requests reach OpenAI | P0 | `test_skill_sources_security.py::test_vidbyte_key_never_reaches_a_vendor` |
| AC-13 | a source answering HTTP 302 with a `location` header | a run loads that entry | exactly one request is made for that step and the result is the mapped failure from §9.2 | P0 | `test_skill_sources_security.py::test_redirect_is_never_followed` |
| AC-14 | one skill too large for a Jev batch, one in a batch whose Jev call raises a `VidbyteSdkError`, one whose answer is missing | a run completes | their reasons are `TOO_LARGE`, `DECISION_FAILED`, `DECISION_FAILED`, each with a non-blank detail; the failed batch's detail names the error class and `VIDBYTE_API_KEY` (§9.2) | P0 | `test_skill_sources_jev_wiring.py::test_every_unavailable_result_explains_why` |
| AC-15 | a resolver step raising `RuntimeError`, or the run task being cancelled during loading | the run executes | the `RuntimeError` or `CancelledError` propagates out of `arun`, and nothing from that load is remembered | P0 | `test_skill_sources_memory.py::test_a_crash_while_loading_propagates_and_remembers_nothing`, `::test_cancellation_while_loading_propagates_and_remembers_nothing` |
| AC-16 | the unchanged existing skill-preload test module (§13) | the suite runs | every existing test passes | P0 | `tests/test_jev_skill_preload.py` (unchanged, 20 tests) |
| AC-17 | this branch | `from vidbyte import SkillEntry, InlineSkill, LocalSkill, SkillsShSkill, GitHubSkill, AnthropicSkill, OpenAISkill, SkillSourceType, SkillUnavailableReason` runs and the contract check runs | the imports succeed and the public API contract matches the generator | P0 | `test_skill_sources_contract.py::test_public_names_are_one_object_across_every_export_path`; contract JSON: `python scripts/generate-sdk-public-api.py --check` (no pytest test) |
| AC-18 | a remote entry and a run stopped by the preflight gate, then a run delegated to a specialist | both runs complete | no source request is made and skill results are empty | P1 | `test_skill_sources_acceptance.py::test_gate_stop_and_specialist_contact_no_skill_source` |
| AC-19 | an `AnthropicSkill` with `version="latest"` whose content download answers 404, whose skill metadata names version `"1759178010641129"` | a run loads it | the resolver downloads that version and the label is `anthropic:<skill_id>@1759178010641129` | P1 | `test_skill_sources_vendor.py::test_latest_refused_downloads_the_version_the_skill_record_names` |
| AC-20 | a `GitHubSkill` and an `AnthropicSkill` that keep failing with 503 | ten runs happen | each run makes at most `SKILL_FETCH_RETRY_COUNT + 1` attempts per step and every run continues with the other skills | P1 | `test_skill_sources_fetch.py::test_a_source_that_keeps_failing_costs_each_run_one_retried_pair` |
| AC-21 | this branch with every §12.3 row done | the lint runner (§11) runs and a reviewer reads the repo map | lint exits 0 with A001 at 642 and no rule REGRESSED; the repo map has an entry for the new package and names four skills locations | P1 | no pytest test: `python lint/run.py` and the reviewer (test-plan.md) |
| AC-22 | `GITHUB_TOKEN` holding a `vb_live_` key, the same key with a leading space, or `GitHubSkill(token="vb_live_…")` | a run reaches the preload | the result is `AUTH_FAILED` and zero requests reach GitHub | P0 | `test_skill_sources_security.py::test_vidbyte_key_never_reaches_github` |
| AC-23 | a skills.sh `SKILL.md` whose frontmatter has `description: 2024-13-45`, another whose frontmatter nests 500 levels deep, and a `skills-lock.json` nested 2,000 levels deep | a run reaches the preload | both skills are `INVALID_SKILL`, the lock is treated as absent, and `arun` returns normally | P0 | `test_skill_sources_skills_sh.py::test_hostile_files_end_as_data_and_the_run_returns` |
| AC-24 | a source that accepts the connection and then sends one byte every few seconds | a run loads that entry | the step ends within `SKILL_FETCH_DEADLINE_SECONDS` with `FETCH_FAILED`, which is not remembered | P1 | `test_skill_sources_fetch.py::test_step_that_never_finishes_ends_at_the_deadline` |
| AC-25 | an `AnthropicSkill` with `version="latest"` whose content download answers 404, whose metadata answers 200 with only `latest_version_id`, and whose download of that version answers 404 | a run loads it | the resolver reads `latest_version_id`, and the result is `NOT_FOUND` with a detail saying the skill exists but its content route was not found | P1 | `test_skill_sources_vendor.py::test_named_version_missing_says_the_content_route_was_not_found` |
| AC-26 | an `OpenAISkill` whose content download answers 200 with a body that starts with a byte-order mark and `---` | a run loads it | the body is parsed as a bare `SKILL.md` and loads | P1 | `test_skill_sources_vendor.py::test_bare_skill_md_body_loads` |
| AC-27 | an entry already remembered as loaded | a later load (a concurrent first run finishing late) produces a different resolution for it | the remembered resolution is unchanged, that later load returns it, and `documents()` agrees with the returned tuple (INV-10) | P2 | `test_skill_sources_memory.py::test_overlapping_loads_agree_on_the_first_remembered_resolution` |
| AC-28 | three `AnthropicSkill` archives: one whose `SKILL.md` member is bzip2-compressed, one whose member name sets the UTF-8 flag over invalid bytes, and one with byte flips that make `zipfile` raise `ValueError` | a run reaches the preload | all three are `INVALID_SKILL` and remembered, and `arun` returns normally | P0 | `test_skill_sources_vendor.py::test_corrupt_archives_never_escape_a_run` |
| AC-29 | an `OpenAISkill` whose content answer is a bare `SKILL.md` of `SKILL_MARKDOWN_MAX_BYTES` + 1 bytes | a run loads it | `TOO_LARGE`, remembered, with a detail naming the `SKILL.md` cap | P1 | `test_skill_sources_vendor.py::test_bare_skill_md_cap_is_inclusive` |

### 6.3 Edge cases and failure modes

Reasons are written in lowercase as `result.reason.value`; "remembered" means INV-5 applies. Every row names the input, the state, and the wrong output that would occur without its guard.

| ID | Trigger (input + state) | System behavior | User sees | Guarded by (INV-/D-) |
|---|---|---|---|---|
| **Construction (all types)** | | | | |
| EC-1 | `GitHubSkill(name="x", repo="o/r", text="...")` or `SkillsShSkill(..., description=...)` | `TypeError` at construction (the class has no such field); without per-source classes the text would be silently ignored | `TypeError: unexpected keyword argument 'text'` | INV-2, D-3 |
| EC-2 | any entry given `type=SkillSourceType.GITHUB` | `TypeError` (`type` is `init=False`); without it an `InlineSkill` could claim to be GitHub and reach the wrong resolver | `TypeError` | INV-2, D-3 |
| EC-3 | `SkillEntry(name="x")` | `ConfigurationError` naming the six concrete classes; without it a typeless entry would hit no resolver mid-run | `ConfigurationError` | INV-2, D-3 |
| EC-4 | `name=""`, `"   "`, or a non-string on any entry | `ConfigurationError` naming `<Class>.name` | `ConfigurationError` at construction | INV-2 |
| EC-5 | `LocalSkill(name="a", ...)` and `GitHubSkill(name="a", ...)`, or an entry named `inline_skill_2` beside two strings | `ConfigurationError` with `details={"names": ["a"]}`; without it two results would be indistinguishable | `ConfigurationError` at agent construction | INV-3 |
| EC-6 | `skills="pdf"` or `skills=b"pdf"` | `ConfigurationError` (unchanged) instead of three one-letter skills | `ConfigurationError` | INV-20 |
| EC-7 | `skills=[InlineSkill(...)]` (a list) | normalized to a tuple (unchanged) | works | INV-20 |
| EC-8 | a `dict`, `Path`, or `SkillResolution` inside `skills` | `ConfigurationError` listing the accepted types | `ConfigurationError` | INV-2, D-4 |
| EC-9 | a caller-defined subclass of `SkillEntry` that overrides `_validate_source` | accepted at construction; its `type` reaches no resolver, so the resulting `KeyError` or `AttributeError` propagates from `arun` | the programming error | INV-9, D-26 (accepted: `_validate_source` is private; subclassing is unsupported) |
| **InlineSkill** | | | | |
| EC-10 | `InlineSkill(description="", ...)` or `text="  "` | `ConfigurationError` naming the field | `ConfigurationError` | INV-2 |
| EC-11 | `text` with leading spaces, tabs, code fences, or a trailing newline | stored and appended byte-exact; without INV-11 trimming would change indentation-sensitive guidance | exact text in the run's instructions | INV-11 |
| EC-12 | `text` longer than a Jev batch can carry with this request | `UNAVAILABLE`, `too_large`, recomputed every run (the limit depends on the request) | `too_large`, detail names the Jev request limit | INV-22 |
| **LocalSkill** | | | | |
| EC-13 | `path=""` | `ConfigurationError` (`Path("")` would silently mean the working folder) | `ConfigurationError` | INV-2, D-15 |
| EC-14 | `path="skills/pdf/SKILL.md"` (names the file) | `ConfigurationError` asking for the folder; without it the loader would look for `SKILL.md/SKILL.md` and report a confusing `not_found` | `ConfigurationError` | INV-2 |
| EC-15 | relative `path`, and the process changes its working folder after constructing the agent | the folder pinned at construction is read | loads from the original folder | D-15 |
| EC-16 | folder missing | `not_found`, remembered | detail: no readable `SKILL.md` at `<absolute path>` | INV-5, D-6 |
| EC-17 | folder present, `SKILL.md` missing, a dangling symlink, a directory, or only `skill.md` on a case-sensitive filesystem | `not_found`, remembered | detail names the absolute path and the exact file name `SKILL.md` | INV-5, D-6 |
| EC-18 | `path` names a regular file (not a folder) | `not_found` (no `SKILL.md` under it), remembered | detail names the path | INV-5 |
| EC-19 | permission denied, an I/O error, or a symlink loop while reading `SKILL.md` | `fetch_failed`, not remembered (a local retry is one cheap read) | detail names the path and the error class | INV-5, D-6 |
| EC-20 | `SKILL.md` larger than `SKILL_MARKDOWN_MAX_BYTES` | `too_large` after reading at most the cap (size from `fstat`), remembered | detail names the file size and the cap | INV-12 |
| EC-21 | `SKILL.md` of 20 KB (loads, but too large for Jev) | loaded, then `too_large` at batching on every run | `too_large`, detail names the Jev limit | INV-22 |
| EC-22 | the folder or `SKILL.md` is a symlink (npx link mode, shared skill folders) | followed | loads | D-15 |
| EC-23 | the folder is on a network mount that hangs | the read blocks one worker thread and the run waits | a slow run | accepted: no OS-level read timeout exists; documented limitation |
| EC-24 | a skill folder is installed after a `not_found` was remembered | still `not_found` until a new agent is created | `not_found`, detail says to create a new agent after fixing | INV-5 (accepted; Q-1 defaults to no) |
| **SKILL.md parsing (Local, skills.sh, GitHub, Anthropic, OpenAI)** | | | | |
| EC-25 | empty file, or first line is not `---` | `invalid_skill`, remembered | detail: must start with a `---` frontmatter line | D-12 |
| EC-26 | UTF-8 byte-order mark before `---` | stripped; parses (without it the opening line would not match) | loads | INV-11, D-13 |
| EC-27 | CRLF line endings, or trailing spaces after `---` | delimiters recognized; body keeps its CRLF bytes | loads, text exact | INV-11, D-12 |
| EC-28 | opening `---` with no closing `---` line | `invalid_skill` (without it the whole file would become YAML or text) | detail: frontmatter is not closed | D-12 |
| EC-29 | frontmatter that is not YAML, or YAML that is a list or scalar | `invalid_skill`; the YAML error text is not copied (it can quote file lines) | detail: frontmatter is not valid YAML / not a mapping | INV-18, D-12, D-29 |
| EC-30 | `name` or `description` missing, blank, or not a string (`description: 42`) | `invalid_skill` naming the field | detail names the field | D-12 |
| EC-31 | folded or literal multi-line `description: >` | parsed by YAML; the value is kept as YAML returns it | loads | D-12 |
| EC-32 | frontmatter only, or a whitespace-only body | `invalid_skill` (a blank body would select nothing useful) | detail: `SKILL.md` has no body | INV-11 |
| EC-33 | invalid UTF-8 bytes | `invalid_skill`; without strict decoding replacement characters would silently change instructions | detail: not valid UTF-8 | D-13 |
| EC-34 | YAML tag such as `!!python/object/apply` | `invalid_skill`; `safe_load` constructs no objects | detail: not valid YAML | INV-13, D-12 |
| EC-35 | frontmatter `name` differs from the entry `name` | loads; the result is named by the entry | entry name in results | D-14 |
| EC-36 | the body tells the agent to read `references/x.md` or run `scripts/x.py` | only the body is loaded; nothing it mentions is fetched or run | the agent may lack the referenced file | INV-12, INV-13 (accepted: NG-5) |
| EC-109 | a frontmatter value YAML reads as an impossible timestamp (`description: 2024-13-45`, `name: 2024-02-30`, `!!timestamp 2024-01-01T25:00:00`) | `yaml.safe_load` raises `ValueError`, caught around the parse call: `invalid_skill`, remembered; without the catch every run would crash and nothing would be remembered | detail: frontmatter is not valid YAML | INV-9, D-29 |
| EC-110 | frontmatter nested about 500 levels deep (about 1 KB of `[`) | `RecursionError`, caught around the parse call: `invalid_skill`, remembered | detail: frontmatter is not valid YAML | INV-9, D-29 |
| **SkillsShSkill** | | | | |
| EC-37 | `name` containing `/`, `\`, `:` (Windows `C:x` would replace the folder), NUL, or equal to `.` or `..` | `ConfigurationError`; without it `../../x` reads outside the skills folder | `ConfigurationError` | INV-2, D-17 |
| EC-38 | `source=""` | `ConfigurationError` | `ConfigurationError` | INV-2 |
| EC-39 | `<directory>/<name>/SKILL.md` missing (never installed, or an interrupted install) | `not_installed`, remembered | detail contains `npx skills add <source> --skill <name>` and the absolute path checked | INV-5, D-17 |
| EC-40 | the process runs from another folder than the project (systemd, Docker `WORKDIR`, a test runner) | `not_installed` | detail's absolute path shows where it looked | D-15, D-17 |
| EC-41 | `skills-lock.json` lists `<name>` with a different `source` (a same-named skill from a fork) | `invalid_skill`, remembered; without the check the fork's text loads under the trusted name | detail names both sources | D-17 |
| EC-42 | no `skills-lock.json` | loads without the source check | loads | D-17 (accepted: a committed skills folder without its lock is legitimate) |
| EC-43 | lock is unparsable (merge-conflict markers), `version` below 1, `skills` missing or not an object, larger than `SKILL_MARKDOWN_MAX_BYTES`, or unreadable | treated as absent, as `npx skills` does; loads without the check | loads | D-17 (accepted: whoever can corrupt the lock can edit `SKILL.md` directly) |
| EC-44 | lock has no entry for `<name>` (copied in by hand) | loads without the check | loads | D-17 (accepted: S1's choice, since a hand-copied skill has no lock entry; Q-7 asks whether to reject it) |
| EC-45 | `directory` is not `<root>/.agents/skills` (for example `vendor/skills`) | no lock lookup | loads | D-17 |
| EC-46 | the lock entry has no string `computedHash` | label without `@hash` | `skills_sh:<source>/<name>` | D-21 |
| EC-47 | `SKILL.md` edited after install, or `npx skills update` run while the agent lives | the remembered text stays until a new agent; the label shows the lock's hash, which is not verified | old text, stale hash | INV-5 (accepted: NG-11, deliberate stable prompt) |
| EC-111 | `skills-lock.json` nested deeply enough that `json.loads` raises `RecursionError` | treated as absent | loads without the check | D-17, D-29 |
| **GitHubSkill** | | | | |
| EC-48 | `repo="https://github.com/o/r"`, `"o"`, `"o/r/x"`, `"o/.."`, or containing `@` or `:` | `ConfigurationError` asking for `owner/repo`; also stops a token pasted into a URL | `ConfigurationError` | INV-2, INV-14 |
| EC-49 | `path` equal to `.`, or with a `.` or `..` segment, an empty segment, a leading `/`, a backslash, or ending in `SKILL.md` | `ConfigurationError` | `ConfigurationError` | INV-2, D-18 |
| EC-50 | `ref=""` or `token=""` | `ConfigurationError` | `ConfigurationError` | INV-2 |
| EC-51 | `name` that is not a single path segment (same rule as EC-37) | `ConfigurationError` (the name is matched as a folder) | `ConfigurationError` | INV-2, D-18 |
| EC-52 | private repo with no token, or a token that cannot see it (404) | `not_found`, remembered | detail: not found or private; set `GITHUB_TOKEN` or pass `token=` | INV-5, D-11 |
| EC-53 | invalid or expired token (401) | `auth_failed`, remembered | detail names `GITHUB_TOKEN` / `token=` | INV-5, D-11 |
| EC-54 | unauthenticated limit exhausted: 403 with `x-ratelimit-remaining: 0` | `rate_limited`, not remembered | detail suggests a token | INV-5, D-11 |
| EC-55 | secondary rate limit: 403 or 429 with `retry-after` | `rate_limited`, not remembered (429 is retried once by the transport first) | `rate_limited` | INV-5, D-11 |
| EC-56 | 403 without rate-limit headers (SSO enforcement, blocked token) | `auth_failed`, remembered | `auth_failed` | D-11 |
| EC-57 | unknown branch or tag (422 or 404 from the commit lookup) | `not_found` for every entry in the group, remembered | detail names the ref | INV-8, D-11 |
| EC-58 | `ref` is a moving branch that advances while the agent lives | the SHA resolved on first success stays; the label shows it | stable text, visible SHA | INV-5, D-18 |
| EC-59 | `ref` is a 40-character lowercase hex SHA | no commit lookup | one fewer request | D-18 |
| EC-60 | `ref="release/v1"` | percent-encoded as one path segment | loads | D-18, A-6 |
| EC-61 | entries for the same repo and ref but different tokens | separate groups, separate lookups; without it one token's visibility would leak to the other entry | correct per-token results | INV-7, D-18 |
| EC-62 | no `path`, and the tree has no `<name>/SKILL.md` | `not_found`, remembered | detail names repo, SHA prefix, and suggests `path=` | D-18 |
| EC-63 | no `path`, two matches at the same shallowest depth | `invalid_skill`, remembered | detail lists both paths and asks for `path=` | D-18 |
| EC-64 | no `path`, matches at different depths | the shallowest wins (the `npx skills` shadowing rule) | loads | D-18 |
| EC-65 | tree listing answers `truncated: true` | `invalid_skill` for the entries without `path`; entries with `path` are unaffected | detail asks for `path=` | INV-8, D-18 |
| EC-66 | commit lookup times out, the connection fails, or it answers 5xx | `fetch_failed` for every entry in the group, not remembered (500/502/503/504 are retried once by the transport; timeouts and connection errors are not) | `fetch_failed` | INV-5, INV-8, D-9 |
| EC-67 | commit lookup answers 200 with a body that is not a 40-hex SHA (a proxy page) | `fetch_failed`, not remembered | detail: unexpected answer | D-11 |
| EC-68 | tree listing body is not JSON or lacks a `tree` list | `fetch_failed`, not remembered | detail: unexpected answer | D-11 |
| EC-112 | tree listing or vendor metadata nested deeply enough that `json.loads` raises `RecursionError` | tree: `fetch_failed`, not remembered; metadata: `invalid_skill`, remembered | detail: unexpected answer | INV-9, D-29 |
| EC-69 | raw fetch 404 at an explicit `path` | `not_found`, remembered | detail names the path | D-11 |
| EC-70 | raw `SKILL.md` larger than `SKILL_MARKDOWN_MAX_BYTES` | streaming stops at the cap; `too_large`, remembered | `too_large` | INV-12 |
| EC-71 | repository renamed or transferred (301) | `not_found`, remembered; the redirect is not followed | detail: the repository may have moved; use its current `owner/repo` | INV-14, D-10 |
| EC-72 | `SKILL.md` is a Git LFS pointer or a symlink blob | its content has no frontmatter: `invalid_skill` | `invalid_skill` | D-12 |
| EC-73 | a single-skill repository with `SKILL.md` at its root (changed r2, R-8) | not supported: with no `path`, the tree search finds no `<name>/SKILL.md`, so `not_found` (detail suggests `path=`); `path="."` is rejected at construction | `not_found` or `ConfigurationError` | D-18 (accepted limitation, documented in the package README; Q-6 default: not built) |
| EC-74 | 50 entries from one repository | one lookup, one tree listing, 50 concurrent raw fetches | loads; may hit GitHub's secondary limit (EC-55) | INV-7 (accepted: bounded by configured entries) |
| **AnthropicSkill and OpenAISkill** | | | | |
| EC-75 | `skill_id=""`, `version=""`, `version=2` (an int), or `api_key=""` | `ConfigurationError`; the int case says to pass text such as `"2"` | `ConfigurationError` | INV-2 |
| EC-76 | no `api_key` and the env var unset or blank | `auth_failed` with no request, remembered | detail: pass `api_key=` or set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | INV-5, D-19 |
| EC-77 | the key or token begins with `vb_live_`, with or without surrounding whitespace: `AnthropicSkill.api_key`, `OpenAISkill.api_key`, `GitHubSkill.token`, or the `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN` fallback (extended r2, R-4; padding r3, R-18) | `auth_failed` with no request, remembered; the Vidbyte key never reaches GitHub or a vendor | detail: a Vidbyte key cannot read GitHub or vendor skills; pass that source's own key or token | INV-15, D-30 |
| EC-78 | 401 or 403 | `auth_failed`, remembered | detail names the key source to fix | D-11 |
| EC-79 | explicit version and 400, 404, or 422 | `not_found`, remembered | detail names the skill id and version; for 404 it also says the vendor's content route may be the cause (A-1; r3, R-19) | D-11, A-1 |
| EC-80 | `version="latest"` refused with 400, 404, or 422 | one metadata request, then one download of the named version; the version comes from `latest_version`, else `latest_version_id` (r2, R-6); metadata 404 is `not_found`; a missing, blank, or non-text-non-integer version is `invalid_skill`, and a `bool` (JSON `true`) is not an integer version (r3, R-19); a 404 for the named version is `not_found` with a detail saying the skill exists but its content route was not found | loads, or the mapped failure | D-19, A-1, A-2 |
| EC-81 | 429 | retried once by the transport, then `rate_limited`, not remembered | `rate_limited` | INV-5 |
| EC-82 | 5xx (including Anthropic 529), a timeout, or a connection reset | `fetch_failed`, not remembered; 500/502/503/504 are retried once by the transport, while 529, timeouts, and connection errors are not | `fetch_failed` | INV-5, D-9 |
| EC-83 | 200 with a body that is neither a zip nor a bare `SKILL.md` (JSON, HTML) | a body starting with `---` after an optional byte-order mark is parsed as a bare `SKILL.md` (r2, R-6), and is `too_large`, remembered, when over `SKILL_MARKDOWN_MAX_BYTES` (r3, R-19); anything else without the zip magic is `invalid_skill`, remembered | detail: the vendor returned neither a zip archive nor a `SKILL.md`; or the `SKILL.md` cap | INV-12, D-20, A-4 |
| EC-84 | archive larger than `SKILL_DOWNLOAD_MAX_BYTES` | streaming stops at the cap; `too_large`, remembered | `too_large` | INV-12 |
| EC-85 | corrupt or truncated archive, a bad CRC, impossible offsets, a member name that sets the UTF-8 flag over invalid bytes, or a `SKILL.md` member compressed with anything but stored or deflate | the method is checked before reading (bzip2, lzma, and others are `invalid_skill`); `ZipFile(...)` construction and the member read are wrapped in `except (BadZipFile, zlib.error, EOFError, NotImplementedError, ValueError)`, where `ValueError` covers `UnicodeDecodeError` and negative seeks: `invalid_skill`, remembered (r3, R-16) | `invalid_skill` | INV-9, D-20 |
| EC-86 | no `SKILL.md` (case-insensitive) at the root or one folder deep, or more than one | `invalid_skill`, remembered | detail says how many were found | D-20 |
| EC-87 | `SKILL.md` member declares more than `SKILL_MARKDOWN_MAX_BYTES` (a zip bomb) | `too_large` before reading; a member that lies about its size fails its CRC check: `invalid_skill` | `too_large` / `invalid_skill` | INV-12, D-20, A-10 |
| EC-88 | the member is encrypted | `invalid_skill`; without the flag check the stdlib raises `RuntimeError`, which would crash the run | `invalid_skill` | INV-9, D-20 |
| EC-89 | member names containing `../` | irrelevant: nothing is extracted to disk | loads if `SKILL.md` is valid | INV-12 |
| EC-90 | an archive with hundreds of thousands of tiny members within the cap | the central directory is parsed in memory | slow load | accepted: vendor-bounded uploads (OpenAI: 500 files) and the download cap |
| EC-91 | the content endpoint redirects (3xx) | not followed (httpx keeps `x-api-key` across origins); `fetch_failed`, not remembered | `fetch_failed`, detail names the status | INV-14, D-10, A-3 |
| EC-92 | an Anthropic prebuilt skill (`pdf`, `docx`, `pptx`, `xlsx`) | loads (if the API serves it) but tells a non-Claude agent to run scripts it lacks | degraded guidance | accepted: documented; the same skills load via `GitHubSkill(repo="anthropics/skills")` |
| EC-93 | `skill_id` containing `/` or spaces | percent-encoded as one segment; the vendor answers 404: `not_found` | `not_found` | D-19 |
| **Loader and memory** | | | | |
| EC-94 | the first run is stopped by the gate or delegated | nothing loads; the first run that reaches the preload loads | no request on the stopped run | INV-4 |
| EC-95 | two concurrent first runs on one agent | both load and requests are duplicated; the first resolution remembered wins and is never replaced (r2, R-14); each load returns the remembered resolution where one exists, so its results and `documents()` agree (r3, R-20) | correct, consistent results per run; extra requests | INV-5, INV-10, D-24, A-8 |
| EC-96 | the run is cancelled while loading | `CancelledError` propagates; nothing from that load is remembered; the next run loads again | cancellation | INV-9 |
| EC-97 | a resolver bug raises `TypeError` | propagates from `arun`; no `UNAVAILABLE` result hides it | the exception | INV-9 |
| EC-98 | transient failure on run 1, success on run 2 | run 2 loads and remembers; run 3 sends nothing | `fetch_failed`, then loaded | INV-5 |
| EC-99 | every remote source is down | every remote skill `UNAVAILABLE` with its reason; inline and local skills still judged; the agent runs | per-skill reasons | INV-9, INV-16 |
| EC-100 | an agent serving 10,000 runs | zero source calls after every entry is remembered; memory constant | no extra latency | INV-5, INV-6 |
| EC-101 | two agents in one process with different keys | separate loaders and memories | each sees only its own sources | INV-6 |
| EC-102 | a key is added to the environment after `auth_failed` was remembered | still `auth_failed` until a new agent | `auth_failed` | INV-5 (accepted: Q-1) |
| EC-103 | a hung upstream that drips bytes slower than the per-operation timeout | the step ends at `SKILL_FETCH_DEADLINE_SECONDS` (r2, R-2): `fetch_failed`, not remembered; the run continues | each run that retries the entry is slower by at most one deadline per step (r3, R-22) | INV-19, D-27 |
| EC-113 | ten vendor skills downloading on the first run | each in-flight download may briefly hold about 4 × `SKILL_DOWNLOAD_MAX_BYTES` (the transport's buffer, its byte copy, and a decoded string); there is no total bound | a memory spike on the first run | NFR-4 (accepted r2, R-13: a concurrency cap was not agreed) |
| EC-114 | a multi-tenant app builds entries from a tenant's input and passes no `token`/`api_key` | the process's `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` is used, so the tenant can load what the operator's credentials can read | the operator's private skills in that tenant's run | T-4 (accepted r2, R-5: entries are trusted configuration; documented in the package README) |
| EC-115 | random byte corruption of a stored or deflated archive (the round-2 reviewer's fuzz: r2's four-class list let through 598 `ValueError`, 24 `UnicodeDecodeError`, and 1 `OSError` in 40,000 cases) | caught by D-20's method check and catch list; the reviewer measured zero escapes over 60,000 mutated stored, deflated, bzip2, and lzma archives | `invalid_skill` | INV-9, D-20, AC-28 |
| EC-116 | a host whose egress to `api.github.com` or a vendor is silently dropped | every run that reaches the preload retries each pending remote entry, paying up to `SKILL_FETCH_TIMEOUT_SECONDS` per attempt and at most `SKILL_FETCH_DEADLINE_SECONDS` per step; `fetch_failed`, never remembered | each run slower by up to one deadline per step for as long as the block lasts | NFR-1 (accepted r3, R-22: transient failures retry on every run, as agreed; documented in the package README) |
| EC-117 | a large repository's tree listing that keeps hitting the timeout or deadline on a slow link | `fetch_failed` on each run, not remembered | detail names the host, step, and deadline and says that `path=` skips the tree listing (r3, R-22) | D-18, §9.2 |
| **Preload integration** | | | | |
| EC-104 | a loaded skill that fits no Jev batch with this request | `too_large`, recomputed per run | detail names the Jev request limit | INV-22 |
| EC-105 | one Jev batch fails (most often a missing or rejected `VIDBYTE_API_KEY`) | its skills `decision_failed`; other batches stand | detail names the error class and `VIDBYTE_API_KEY` (r2, R-7) | INV-23, §9.2 |
| EC-106 | Jev's answer for one skill is missing or malformed | that skill `decision_failed` only | per-skill result | INV-23 |
| EC-107 | every entry fails to load | zero Jev requests; every result `UNAVAILABLE` with its load reason; the context object is returned unchanged | base instructions only | INV-16, INV-25 |
| EC-108 | an explicit `options["system"]` | unchanged: it is the baseline that selected skills append to | unchanged | INV-27 |

**Rollback of the user action:** Removing an entry from `skills` and creating a new agent removes its text from future runs; nothing persists outside the process (no disk writes, no global cache), so dropping the agent drops every loaded skill. To pick up a fixed source, a new key, or an updated skill, create a new `JevAgent`. Reverting the PR restores the `SkillDocument`-or-string API; code that used the six entries stops importing.

## §7 Requirements

**Functional**
| ID | Requirement | Priority | Source (request.md / G-) |
|---|---|---|---|
| FR-1 | `JevAlignmentSettings.skills` accepts a flat tuple (or iterable) mixing the six entry classes, `SkillDocument`, and `str`; strings still become inline `SkillDocument`s. Users never construct a loader. (→ INV-20, INV-21, AC-1, AC-16) | P0 | Prompt 2 "simply an array … I dont want them to have to put in skill loadres"; G-1 |
| FR-2 | Each entry class subclasses `SkillEntry` and has a read-only `type: SkillSourceType`; GitHub and skills.sh entries have no `text`. (→ INV-2, AC-17) | P0 | Prompt 2 "a type and text option … no text"; Prompt 3 "subclasses" |
| FR-3 | Every entry validates its fields at construction per §9.1. (→ INV-2, INV-3, EC-1 to EC-14, EC-37, EC-38, EC-48 to EC-51, EC-75) | P0 | request.md §C; G-2 |
| FR-4 | `SkillLoader` resolves entries lazily inside the preload on each run, remembering per INV-5, for the agent's lifetime. (→ INV-4 to INV-6, INV-10, AC-10, AC-18) | P0 | Prompt 2 "under the hood … SkillLoader"; request.md §C |
| FR-5 | One resolver subclass per source type, in its own module; the loader hands each resolver the pending entries that share its lookups (a single entry, or every GitHub entry with the same repo, ref, and token) and resolves every group concurrently. (→ INV-7, AC-7) | P0 | Prompt 3 "decompose … subclasses"; request.md §C "Loader interface" (refined r2, D-22) |
| FR-6 | `InlineSkill` resolves to its exact fields with source `"inline"`. (→ AC-3) | P0 | request.md §C per-source |
| FR-7 | `LocalSkill` reads `<path>/SKILL.md` from disk. (→ AC-4, EC-13 to EC-24) | P0 | Prompt 3 "the localskill" |
| FR-8 | `SkillsShSkill` reads the installed copy and checks `skills-lock.json`, with no network. (→ AC-5, AC-6, EC-37 to EC-47, EC-111) | P0 | request.md §C per-source |
| FR-9 | `GitHubSkill` resolves a commit SHA, lists the tree at most once per group, and fetches raw `SKILL.md` files. (→ AC-7, AC-22, EC-48 to EC-74, EC-112) | P0 | request.md §C per-source |
| FR-10 | `AnthropicSkill` downloads the version zip and reads only `SKILL.md`, in memory. (→ AC-8, AC-19, AC-25, AC-28, EC-75 to EC-93, EC-115) | P0 | request.md §C per-source |
| FR-11 | `OpenAISkill` does the same against OpenAI. (→ AC-9, AC-12, AC-26, AC-29) | P0 | Prompt 3 "OpenAISkill" |
| FR-12 | One shared `SKILL.md` parser: strict UTF-8 with BOM removal, YAML frontmatter via `safe_load`, required `name` and `description`, untrimmed body. (→ INV-11, AC-4, AC-23, EC-25 to EC-36, EC-109, EC-110) | P0 | request.md §C "Shared SKILL.md parser" |
| FR-13 | `JevSkillResult` gains `reason: SkillUnavailableReason | None` and `detail: str | None`; `description` becomes `str | None`. (→ INV-17, AC-14) | P0 | request.md §C "Every result explains itself" |
| FR-14 | Loading is fail-open: every expected failure becomes `UNAVAILABLE` with a reason and a detail that names the fix; the run continues. (→ INV-9, INV-15 to INV-18, AC-6, AC-14, AC-15, AC-22, AC-24, AC-27) | P0 | Prompt 3 "edge cases/failure modes … all throughout the implementation"; G-2 |
| FR-15 | The nine new public names are exported from `vidbyte` and the public API contract is regenerated; `SkillDocument` stays exported. (→ INV-21, AC-17) | P0 | orchestrator decision; G-1 |
| FR-16 | The new package has a README with `## Notes for agents`; the repo map has an entry for it; headers of every touched module describe the new behavior. (→ AC-21) | P1 | AGENTS.md (repo map, folder READMEs) |

**Non-functional**
| ID | Requirement | Priority | Target |
|---|---|---|---|
| NFR-1 | Bounded cost per step, on every run that loads a pending entry (transient failures are retried on every run, r3, R-22) | P0 | each network operation times out after `SKILL_FETCH_TIMEOUT_SECONDS` = 10 s; HTTP 408, 409, 425, 429, 500, 502, 503, 504 answers are retried once after 0.5 s; timeouts and connection errors are not retried within the run (they are transient, so the next run retries); every step, retries included, ends within `SKILL_FETCH_DEADLINE_SECONDS` = 25 s; at most 3 sequential steps per entry (75 s worst case), all groups concurrent (corrected r2, R-2) |
| NFR-2 | Remembered entries cost nothing | P0 | zero requests and zero file reads for remembered entries on every later run |
| NFR-3 | GitHub request count | P0 | per group: at most 1 commit lookup + at most 1 tree listing + 1 raw fetch per entry (5 skills from one repo = 7 requests, within the 60/hour unauthenticated limit) |
| NFR-4 | Memory bounds | P0 | per download at most 32 MiB of body (`SKILL_DOWNLOAD_MAX_BYTES`), with a transient peak of about 4× that per in-flight download; per `SKILL.md` at most 1 MiB (`SKILL_MARKDOWN_MAX_BYTES`); remembered entries at most the configured count; no bound on the total across concurrent downloads (EC-113, accepted r2, R-13) |
| NFR-5 | Secrets | P0 | INV-14 and INV-15 hold for every path in §6.3 |
| NFR-6 | Lint ratchet | P0 | the lint runner (§11) exits 0; no rule REGRESSED; A001 lowered by exactly one after the header upgrade; zero new S011, S012, S047, S061, S063, S064, C016, C020 findings |
| NFR-7 | Code shape | P1 | every new file well under 1,000 lines; functions about 50 lines or fewer; main functions narrated |
| NFR-8 | Python support | P0 | works on 3.11 and 3.12 (CI matrix) |

---

## Part C — Design

## §8 Architecture and decisions

### 8.1 Decisions
| ID | Decision | Deciding reason | Runner-up | Flips if |
|---|---|---|---|---|
| D-1 | Entry records and `SkillResolution` go in the existing `skills` dataclass domain module; `SkillSourceType` and `SkillUnavailableReason` in the existing `skills` enum domain module; constants in a new `skills` constants module. | AGENTS.md placement rules: add to the existing domain module; the loader is not JEV code, so the JEV modules are wrong homes. | Put everything in the JEV record, enum, and constant modules. | Reviewers rule skill sources are JEV code; the move is mechanical. |
| D-2 | Loading logic lives in `vidbyte.agents.skills`; it imports only `vidbyte.lib` and its own sibling modules. The Jev wiring (owning a loader, mapping resolutions to results) stays in the JEV alignment module. | User directive (Prompt 3) and the orchestrator's N1 reconciliation. It reconciles with AGENTS.md "A new JevAgent capability … Its questions and actions stay inside" the JEV packages: resolving a source asks Jev nothing and acts on no Jev state; the Jev capability (selection) is unchanged and stays in the JEV package. | A `sources/` subpackage under the JEV alignment package. | The placement workflow moves it; no public name depends on the package. |
| D-3 | One frozen, slotted subclass per source over `SkillEntry`. The base declares `type: SkillSourceType = field(init=False)` with no default; each subclass redeclares it with `init=False` and its member as default. The base `__post_init__` checks `name`, then calls the subclass hook `_validate_source()`; the base hook raises. | User chose subclasses. `super().__post_init__()` raises `TypeError` in slotted dataclass subclasses on 3.11 and 3.13 (verified), so a template hook replaces it; `init=False` makes `type` read-only and rejects `type=`. | One `Skill(type=..., ...)` class with every field (rejected by the user). | Python adds a slotted-safe `super()` path; no behavior change either way. |
| D-4 | `SkillDocument` stays public and accepted as an already-resolved entry; strings still normalize to `SkillDocument`. Accepted types are exactly `SkillEntry` instances, `SkillDocument`, and `str`. | Orchestrator decision; the existing test asserts the root export and the inline normalization (`item.source == "inline"`). | Make it internal (request.md). | Never in this PR. |
| D-5 | Resolution is lazy, inside `JevSkillsPreload.run`, through a `SkillLoader` built once in `JevSkillsPreload.__init__`. | `JevAgent` builds the preload once in `__init__` while `BaseAgent._runtime()` builds a new runtime each run (verified), so the preload's loader lives exactly as long as the agent; no I/O at construction. | Resolve at construction. | Never: construction must not do I/O (INV-1). |
| D-6 | Transient reasons are exactly `RATE_LIMITED` and `FETCH_FAILED` (`SKILL_TRANSIENT_REASONS`); all other loader reasons are remembered. Local read errors other than "no file" are `FETCH_FAILED`. | Agreed cache policy; a local re-read is one cheap syscall, so permission fixes take effect without restart. | Remember every failure. | Q-1 is answered yes (re-check local misses every run). |
| D-7 | The reason enum is `SkillUnavailableReason` in the skills enum domain, holding all eight agreed values (`DECISION_FAILED` and the batching `TOO_LARGE` are set only by the Jev preload). | The agent-agnostic loader produces six of the eight; one enum keeps `JevSkillResult.reason` single-typed. | `JevSkillUnavailableReason` in the JEV enum module (request.md's proposed name). | Reviewers treat it as JEV-only; rename and move. |
| D-8 | The preload keeps its keyword signature, stores `skills` (the entries) and `loader`, seeds results from `loader.load()`, and `_build_batches(message)` reads `loader.documents()`. | Keeps the one-argument `_build_batches` the existing test calls before any run; `SkillDocument` entries are pre-remembered so that call batches them. | A per-run mutable `self.documents`, or a `documents` parameter on `_build_batches`. | The existing test contract changes. |
| D-9 | Every request goes through `HttpTransport.request` via one small `SkillFetch` step that fixes timeout, retry, backoff, `follow_redirects=False`, and the size cap, runs the whole step inside `asyncio.timeout(SKILL_FETCH_DEADLINE_SECONDS)` (D-27), and maps transport exceptions and the deadline to resolutions once. The transport retries only on status codes; timeouts and connection errors are not retried within a run. | AGENTS.md principle 5; two resolver families need the same exception mapping. | Each resolver calls the transport and maps exceptions itself. | A third family appears with different transport needs. |
| D-10 | Never follow redirects. A GitHub 3xx is `NOT_FOUND` (moved, permanent); a vendor 3xx is `FETCH_FAILED`. | httpx strips `Authorization` on cross-origin redirects but keeps `x-api-key`; GitHub answers a renamed repository with 301. | Follow redirects. | A vendor content endpoint is proven to redirect (A-3); then a re-spec adds a same-step follow that drops credentials. |
| D-11 | Each source maps statuses with a dict keyed by `http.HTTPStatus` members and an explicit default (§9.2); lookups use the integer status (`status in reasons`), never `HTTPStatus(status)`, which raises `ValueError` for 529 (r3); details name the fix and never echo a body. | Repo precedent (`_GatewayAnswer.gateway_reason`); A007 bans bare status literals. | if/else ladders. | — |
| D-12 | A new `SkillMarkdown` parser (static helper class) using `yaml.safe_load`; the packaged catalog's line-based parser is not reused or changed. The parse call alone is wrapped in `except (yaml.YAMLError, ValueError, RecursionError)` (D-29). | The catalog parser rejects folded YAML, requires `name` to equal the folder, and returns no body. | Extend the catalog parser (would change packaged-skill behavior). | A second package outside `vidbyte.agents.skills` needs it; then it moves to `vidbyte.lib`. |
| D-13 | Decode strictly; invalid UTF-8 is `INVALID_SKILL`. | Replacement characters would silently alter agent instructions. | `errors="replace"` (the coding-context loader's choice for display text). | — |
| D-14 | Result `name` = entry `name`; frontmatter `name` must be non-blank text but is not compared; `description` comes from frontmatter. | `npx skills` sanitizes folder names, so equality would fail valid installs; the entry name is what the user wrote and what duplicate checks used. | Require equality. | — |
| D-15 | `LocalSkill.path` and `SkillsShSkill.directory` are typed `str | Path` and stored as `Path(value).absolute()` at construction (no filesystem access, no existence check). | The conversation's default (process working folder), pinned so a later `chdir` does not move skills. `CodingAgentSettings.root_dir` is only a partial precedent: it is also resolved and checked for existence, which would be I/O here (INV-1). | Resolve against the working folder at load time. | — |
| D-16 | `SkillsShSkill` keeps the field name `source` (`owner/repo`); `GitHubSkill` uses `repo`. | The user approved the sketch with `source=`; it is the key the lock check compares and the argument of `npx skills add <source>`. The label is a different string on a different record. | Rename to `repo`. | The user prefers symmetry (Q-3). |
| D-17 | skills.sh: read `<directory>/<name>/SKILL.md`; consult `<root>/skills-lock.json` only when `directory` is `<root>/.agents/skills`; a lock that is missing, unreadable, over the cap, unparsable (including `RecursionError`), `version` below 1, or lacking a `skills` object is treated as absent; a lock without an entry for the skill is accepted (S1's choice; Q-7); a different `source` is `INVALID_SKILL`. `name` must be one path segment. | Mirrors `npx skills` lock semantics; request.md §C requires the source check when the lock lists the skill and says nothing about an unlisted one; the segment rule stops traversal (including Windows drive-relative names). | Treat a missing entry as a mismatch. | The user answers Q-7 yes. |
| D-18 | GitHub: `group_key` is `(repo, ref, token)`; a 40-char lowercase hex `ref` skips the commit lookup; the tree is listed once per group only when some entry lacks `path`; the shallowest `.../<name>/SKILL.md` blob wins; a tie or `truncated` is `INVALID_SKILL`. `path` must name a folder below the repository root, so `"."` is rejected (r2, R-8: a root `SKILL.md` is Q-6, not built). | Shares calls (NFR-3) without mixing token visibility. | One API call chain per entry; the tarball endpoint. | Many skills load without a token (tarball becomes cheaper); Q-6 is answered yes. |
| D-19 | Vendors: download `skills/{id}/versions/{version}/content`; when `version == "latest"` and the answer is 400, 404, or 422, read the newest version from the skill record (`latest_version`, else `latest_version_id`) and download that version once; a 404 for that version keeps `NOT_FOUND` with a detail saying the skill exists but its content route was not found. Anthropic sends `x-api-key`, `anthropic-version: 2023-06-01`, `anthropic-beta: skills-2025-10-02`; OpenAI sends `authorization: Bearer`. Keys: the entry's, else `ProviderModelRegistry.resolve_api_key`. `OpenAISkill.version` defaults to `"latest"`. | Handles both answers to the open "latest" question and both recorded field names, and makes a wrong content-route assumption (A-1) visible instead of reading as a bad id (r2, R-6). The beta header yields the response shapes the conversation read (the API is now GA and still honors the header with the old shapes). | Always read metadata first (one extra call per run for every vendor skill). | Anthropic retires the beta header (A-1). |
| D-20 | Vendor body reading in memory: a body starting with `---` after an optional UTF-8 byte-order mark is a bare `SKILL.md` (r2, R-6, A-4) and is `TOO_LARGE` when over `SKILL_MARKDOWN_MAX_BYTES` (r3, R-19); otherwise require the `PK\x03\x04` magic, exactly one member named `SKILL.md` case-insensitively at the root or one folder deep, no encrypted flag, a `compress_type` of `ZIP_STORED` or `ZIP_DEFLATED`, and a declared size within `SKILL_MARKDOWN_MAX_BYTES` before reading; wrap the `ZipFile(...)` construction and the member read in `except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, ValueError)` (r3, R-16). | The round-2 reviewer fuzzed this exact shape: 60,000 mutated stored, deflated, bzip2, and lzma archives, zero escapes; r2's four-class list let `ValueError`, `UnicodeDecodeError`, `OSError`, and `LZMAError` through (§11). The flag check prevents a `RuntimeError`; the method check keeps the bzip2 and lzma decoders away from untrusted bytes; the bare-file branch covers the unverified OpenAI format. | Extract to a temp folder; catch `OSError` and `lzma.LZMAError` instead of checking the method (also zero escapes in the fuzz, but leaves two more decoders reachable). | Vendors start serving bzip2 or lzma archives. |
| D-21 | Labels use `SkillSourceType.value` as prefix: `inline`; `local:<folder name>` (r2, R-10: no machine path); `skills_sh:<source>/<name>[@<hash12>]`; `github:<owner>/<repo>@<sha12>/<folder>/SKILL.md`; `anthropic:<skill_id>@<version>`; `openai:<skill_id>@<version>`, where `<version>` is the version actually downloaded. | One readable, secret-free provenance per result that Jev may see; the SHA makes a moved branch visible. | `skills.sh:` (request.md's sketch); `local:<absolute folder>` (sends the OS user name and folder layout to Jev and to anything that logs results). | — |
| D-22 | `SkillResolver` is generic over its entry type, with one abstract main, `resolve(entries)`, and a `group_key(entry)` that defaults to the entry itself (GitHub: `(repo, ref, token)`). `SkillLoader.load` groups pending entries by `(entry.type, group_key)`, gathers one `resolve(group)` per group with `return_exceptions=True`, and classifies results against `BaseException`. Each resolver's `resolve` is its one narrated main and calls only leaf helpers and other classes (r2, R-3). | Keeps AGENTS.md principle 1 with no exception, keeps concurrency within a source, and keeps the conversation's reason for grouping (GitHub shares one commit lookup and tree per repo and ref); it refines request.md's "each resolver gets all entries of its type at once". Generics keep mypy (S009) free of override errors. | r1's base fan-out into a per-entry `_resolve_one` (two levels of own-class calls). | — |
| D-23 | Blocking disk work (`LocalSkillResolver.read_capped`, the lock read) runs through `asyncio.to_thread`. | Repo precedent; ASYNC230 (S047) bans `open()` in async functions. | Synchronous reads on the event loop. | — |
| D-24 | No lock around a load; concurrent first runs on one agent may duplicate requests; the first remembered resolution wins and is never replaced (r2, R-14); each load returns the remembered resolution where one exists, and its own otherwise (r3, R-20). | `asyncio.Lock` is banned (TID251) and agents run one request at a time (A-8); returning the remembered value keeps INV-10 true without a lock. | An SDK concurrency primitive. | Concurrent runs on one agent become supported. |
| D-25 | No new error classes; expected failures become `SkillResolution` values, and settings errors stay `ConfigurationError`. | Avoids A003 packets and keeps "failure is data" for the fail-open path. | A private exception carrying a reason. | — |
| D-26 | Subclassing `SkillEntry` outside the SDK is unsupported and not guarded. | `_validate_source` is private; guarding needs a registry for a case no caller has. | A closed set check in settings. | Users ask for custom sources. |
| D-27 | Each `SkillFetch.get` call, retries included, runs inside `asyncio.timeout(SKILL_FETCH_DEADLINE_SECONDS)` (25 s, above one retried pair of 10 s attempts plus backoff); the deadline maps to `FETCH_FAILED`. This resolves Q-2 (r2, R-2). | request.md §C assumes "a hanging upstream adds up to timeout × attempts to that run"; the transport's timeout is per network operation, so a server that drips bytes was otherwise unbounded. The repo already bounds whole steps with `asyncio.timeout` (multi-agent runner, harness executor). | Leave the step unbounded and document it. | — |
| D-28 | The loader's memory is resolved configuration, not run state. The jev-agent skill's invariant reads "Runtime state is run-local; reusable configuration is frozen and validated before execution". The memory is built only from the frozen, validated entries, holds no run data (no message, answers, or usage), and lives per agent (INV-6), so the invariant holds (r2, R-15). | The conversation decided to remember resolutions on the agent; this records why that does not break the JEV invariant. | Re-resolve every run (fails INV-5, NFR-2). | Reviewers read the invariant as forbidding any cross-run cache. |
| D-29 | Parsing third-party YAML or JSON catches `ValueError` and `RecursionError` beside the parser's own error, around the single parse call only: YAML frontmatter → `INVALID_SKILL`; `skills-lock.json` → absent; GitHub tree → `FETCH_FAILED`; vendor metadata → `INVALID_SKILL` (r2, R-1). | PyYAML raises `ValueError` for impossible timestamps and `RecursionError` for deep nesting, and `json.loads` raises `RecursionError` for deep nesting (probed by the S1 reviewer on 3.11.0 with PyYAML 6.0.2); uncaught, one hostile `SKILL.md` would crash every run. | Catch `Exception` (would hide programming errors, INV-9). | — |
| D-30 | The Vidbyte-key guard covers all three credentialed sources: a `GitHubSkill.token`, `AnthropicSkill.api_key`, `OpenAISkill.api_key`, or env fallback that begins with `VIDBYTE_API_KEY_PREFIX` is `AUTH_FAILED` with no request (r2, R-4). The entry value and the env value are stripped first, and the stripped value is the one checked and sent (r3, R-18). | Orchestrator decision N12: the env fallback stays, but a Vidbyte key is never sent to a vendor; `find_vidbyte_api_key` shows such values do appear in provider variables, and `resolve_api_key` and `find_vidbyte_api_key` both strip before checking. | Guard the vendors only (r1); check the unstripped value (r2: `" vb_live_…"` passed the check). | — |
| D-31 | `GitHubSkillResolver.resolve` stays one narrated main whose step leaves (`_commit_sha`, `_tree_paths`, `_raw_documents`) each call `SkillFetch.get` and then the private `_GitHubAnswer.failure(response, step=..., target=...)`, a static status classifier in the github module that holds the D-11 map and the 403 rate-limit header rule (r3, R-21). | Principle 1 lets a leaf call another class but not a sibling leaf, and three GitHub steps share one status map; without the class the main grows to 70–100 lines or calls go two levels deep. Precedent: `_GatewayAnswer` in the Vidbyte gateway client. Restores r1's allowance for one private GitHub helper class. | Classify inline in a 60-line main after each fetch. | — |

### 8.2 Patterns inherited
- **Base class with thin per-variant subclasses and a hook that raises by default** — one resolver per source; the entry base's `_validate_source` hook raises unless a subclass overrides it — `vidbyte/agents/coding_context/root_file.py:RootFileLoader._enabled`.
- **Package that exports nothing from `__init__`** — callers import modules directly, so adding a source never edits the package root — `vidbyte/agents/coding_context/__init__.py`.
- **Capped file read sized with `os.fstat`** — read at most the cap and learn the true size without an A007 `read(CAP + 1)` probe — `vidbyte/agents/coding_context/root_file.py:RootFileLoader._read_capped`.
- **Status to remedy by dict dispatch over `HTTPStatus`, never echoing a body** — `vidbyte/lib/http/vidbyte_gateway.py:_GatewayAnswer.gateway_reason`, `_GatewayAnswer.failure_reason`.
- **Concurrent fan-out classified against `BaseException`** — `vidbyte/agents/jev/alignment/skills.py:JevSkillsPreload.run` (S063).
- **Canonical HTTP helper with timeout, bounded retry, and size cap** — `vidbyte/lib/http/transport.py:HttpTransport.request`; per-vendor client headers — `vidbyte/tools/builtins/operations/clients/_base.py:WebOperationClient.request_json`; bearer headers — `vidbyte/lib/http/parser.py:HttpResponseParser.bearer_headers`.
- **Explicit key, else environment variable** — `vidbyte/lib/registries/models.py:ProviderModelRegistry.resolve_api_key`.
- **Secret fields `repr=False`** — `vidbyte/agents/jev/settings.py:JevAgentSettings.api_key`.
- **Path stored absolute at construction, typed `Path | str`** — `vidbyte/lib/dataclasses/coding.py:CodingAgentSettings.root_dir`.
- **Static helper class inside a dataclass domain module** — `vidbyte/lib/dataclasses/jev.py:JevText`.
- **Blocking I/O off the event loop** — `vidbyte/harnesses/stores/file.py` (`asyncio.to_thread`).
- **In-memory zip** — `vidbyte/sessions/portable.py` (`zipfile.ZipFile(io.BytesIO(...))`, `zipfile.BadZipFile`).
- **Module-level `TypeVar`** — `vidbyte/agents/mixins.py:ResultT`.
- **Per-vendor modules named after the vendor** — `vidbyte/agents/pricing/anthropic.py`, `vidbyte/agents/pricing/openai.py`.
- **Read-only `type` field via `init=False` with a default** — `vidbyte/lib/dataclasses/codex.py:CodexSkillInput`.
- **A whole-step deadline with `asyncio.timeout`** — `vidbyte/agents/multi/runner.py` (line 51), `vidbyte/harnesses/execution.py` (line 210).

### 8.3 Smaller design rejected
The smallest design is no loader memory: `JevSkillsPreload.run` re-resolves every entry on every run, with one resolver function per source in a single module. It fails **INV-5** and **NFR-2/NFR-3**: five skills from one GitHub repository cost seven requests per run, so an unauthenticated agent exhausts GitHub's 60-requests-per-hour limit in nine runs and every later run reports `rate_limited`; it also re-downloads vendor zips each run. A single module with a `match` on type also fails the user's directive and **FR-5** ("decompose … into subclasses for each of the different skill types"). Resolving at construction (even smaller: no laziness) fails **INV-1**.

### 8.4 Complexity budget
| Item | Count | Justification for each |
|---|---|---|
| New files | 14 | the skills constants module (none exists today); in the `vidbyte.agents.skills` package: the package marker, its README, `resolver` (base), `fetch` (shared HTTP step), `markdown` (shared parser), `loader` (coordinator), and one module per source: `inline`, `local`, `skills_sh`, `github`, `vendor` (shared zip-vendor base), `anthropic`, `openai` (§12.3 rows 3 and 7–19) |
| New classes/modules | 3 enums (`SkillFetchStep` is internal: exported from `vidbyte.lib.enums` only, not from `vidbyte`; r3, R-17); 9 classes in the skills dataclass module (`SkillEntry`, six entries, `SkillResolution`, the `SkillText` validation helper); 11 classes in the package (`SkillResolver`, `SkillFetch`, `SkillMarkdown`, `SkillLoader`, `InlineSkillResolver`, `LocalSkillResolver`, `SkillsShSkillResolver`, `GitHubSkillResolver`, `VendorSkillResolver`, `AnthropicSkillResolver`, `OpenAISkillResolver`) plus the private `_GitHubAnswer` status classifier (D-31), 12 in all | each class owns one job named in §8.5 |
| New dependencies | 0 | `httpx`, `PyYAML`, `zipfile`, `zlib` already available |
| New config keys | 1 environment variable read: `GITHUB_TOKEN` (new to the SDK); `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` already exist in the provider registry | agreed fallbacks |
| New collections/tables | 0 | in-memory per-agent dict bounded by configured entries |
| New public endpoints/commands | 0 commands; 9 new public names (`SkillEntry`, six entries, `SkillSourceType`, `SkillUnavailableReason`) | the entries are the feature; the enums are read on entries and results |

_The implementer may not exceed this budget without stopping and reporting BLOCKED._

### 8.5 Key interfaces

```python
# --- skills enum domain (vidbyte.lib.enums.skills) ---
class SkillSourceType(str, Enum):
    INLINE = "inline"; LOCAL = "local"; SKILLS_SH = "skills_sh"
    GITHUB = "github"; ANTHROPIC = "anthropic"; OPENAI = "openai"

class SkillUnavailableReason(str, Enum):
    NOT_INSTALLED = "not_installed"; NOT_FOUND = "not_found"; AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"; FETCH_FAILED = "fetch_failed"; INVALID_SKILL = "invalid_skill"
    TOO_LARGE = "too_large"; DECISION_FAILED = "decision_failed"

class SkillFetchStep(str, Enum):    # internal (r3, R-17): names the step in details; not a root export
    GITHUB_COMMIT = "github_commit"; GITHUB_TREE = "github_tree"; GITHUB_FILE = "github_file"
    VENDOR_CONTENT = "vendor_content"; VENDOR_METADATA = "vendor_metadata"

# --- skills dataclass domain (vidbyte.lib.dataclasses.skills); all @dataclass(frozen=True, slots=True) ---
class SkillEntry:
    name: str
    type: SkillSourceType = field(init=False)            # no default here; each subclass fixes it
    def __post_init__(self) -> None: ...                 # validates name, then self._validate_source()
    def _validate_source(self) -> None: ...              # base raises ConfigurationError

class InlineSkill(SkillEntry):      # type = INLINE
    description: str
    text: str
class LocalSkill(SkillEntry):       # type = LOCAL; stored as Path(path).absolute()
    path: str | Path
class SkillsShSkill(SkillEntry):    # type = SKILLS_SH; directory stored absolute
    source: str
    directory: str | Path = SKILLS_SH_DEFAULT_DIRECTORY  # ".agents/skills"
class GitHubSkill(SkillEntry):      # type = GITHUB
    repo: str                                            # "owner/repo"
    ref: str | None = None                               # None -> HEAD
    path: str | None = None                              # skill folder below the repo root; None -> search the tree
    token: str | None = field(default=None, repr=False)  # None -> GITHUB_TOKEN
class AnthropicSkill(SkillEntry):   # type = ANTHROPIC
    skill_id: str
    version: str = "latest"
    api_key: str | None = field(default=None, repr=False)  # None -> ANTHROPIC_API_KEY
class OpenAISkill(SkillEntry):      # type = OPENAI
    skill_id: str
    version: str = "latest"
    api_key: str | None = field(default=None, repr=False)  # None -> OPENAI_API_KEY

class SkillResolution:              # exactly one of: document, or (reason and non-blank detail)
    document: SkillDocument | None = None
    reason: SkillUnavailableReason | None = None
    detail: str | None = None
    @property
    def transient(self) -> bool: ...                     # reason in SKILL_TRANSIENT_REASONS

# --- JEV record (vidbyte.lib.dataclasses.jev) ---
class JevSkillResult:
    name: str
    description: str | None          # None only when status is UNAVAILABLE
    source: str | None
    status: JevSkillStatus
    probability: float | None = None
    reason: SkillUnavailableReason | None = None   # set iff status is UNAVAILABLE
    detail: str | None = None                      # non-blank iff reason is set

# --- vidbyte.agents.skills (internal; no-argument constructors except SkillLoader) ---
SkillEntryT = TypeVar("SkillEntryT", bound=SkillEntry)
class SkillResolver(ABC, Generic[SkillEntryT]):
    def group_key(self, entry: SkillEntryT) -> Hashable: ...  # equal keys share lookups; default: the entry itself
    @abstractmethod
    async def resolve(self, entries: tuple[SkillEntryT, ...]) -> tuple[SkillResolution, ...]: ...
    # entries share one group_key (exactly one entry except for GitHub); one result per entry, in order

class InlineSkillResolver(SkillResolver[InlineSkill]): ...
class LocalSkillResolver(SkillResolver[LocalSkill]):
    @staticmethod
    def read_capped(path: Path) -> tuple[bytes, int] | None: ...  # None: no regular file at path; raises OSError
class SkillsShSkillResolver(SkillResolver[SkillsShSkill]): ...
class GitHubSkillResolver(SkillResolver[GitHubSkill]): ...      # group_key = (repo, ref, token)
class _GitHubAnswer:                                             # private, github module (D-31)
    @staticmethod
    def failure(response: HttpResponse, *, step: SkillFetchStep, target: str) -> SkillResolution | None: ...  # None for 2xx
class VendorSkillResolver(SkillResolver[VendorSkillT]): ...     # VendorSkillT: AnthropicSkill or OpenAISkill
class AnthropicSkillResolver(VendorSkillResolver[AnthropicSkill]): ...
class OpenAISkillResolver(VendorSkillResolver[OpenAISkill]): ...

class SkillFetch:
    async def get(self, *, url: str, headers: Mapping[str, str], max_bytes: int, step: SkillFetchStep) -> HttpResponse | SkillResolution: ...
    # HttpResponse for every HTTP answer (any status); SkillResolution only when no usable answer arrived
    # the whole call, retries included, runs inside asyncio.timeout(SKILL_FETCH_DEADLINE_SECONDS)

class SkillMarkdown:
    @staticmethod
    def parse(raw: bytes, *, name: str, source: str) -> SkillResolution: ...  # document, or INVALID_SKILL

class SkillLoader:
    def __init__(self, entries: tuple[SkillEntry | SkillDocument, ...]) -> None: ...  # no I/O; SkillDocument pre-remembered
    async def load(self) -> tuple[SkillResolution, ...]: ...                          # groups by (type, group_key); one per entry, in order
    def documents(self) -> tuple[SkillDocument | None, ...]: ...                      # remembered documents, in order

# --- Jev wiring (signatures kept, types widened) ---
class JevAlignmentSettings:
    skills: tuple[SkillEntry | SkillDocument | str, ...] = ()   # normalized to tuple[SkillEntry | SkillDocument, ...]
class JevSkillsPreload(JevPreload):
    def __init__(self, *, skills: tuple[SkillEntry | SkillDocument, ...], decision: DecisionModelConfig,
                 threshold: float, response: JevResponse) -> None: ...
    skills: tuple[SkillEntry | SkillDocument, ...]
    loader: SkillLoader
    def _build_batches(self, message: str) -> tuple[JevSkillBatch, ...]: ...  # reads self.loader.documents()
```

## §9 Data, API, configuration, migration

### 9.1 Data model

**Entries** (all frozen, slotted, hashable, equal by value; secrets take part in equality and hashing but never in `repr`).

| Class | Field | Required | Default | Validation at construction |
|---|---|---|---|---|
| all | `name` | yes | — | non-blank `str`, kept exact |
| all | `type` | no (not settable) | the class's `SkillSourceType` | `init=False` |
| `InlineSkill` | `description`, `text` | yes | — | non-blank `str`, kept exact |
| `LocalSkill` | `path` | yes | — | `str` or `Path`; not `""`; final component not `SKILL.md` (case-insensitive); stored `Path(path).absolute()` |
| `SkillsShSkill` | `name` | yes | — | additionally one path segment: no `/`, `\`, `:`, NUL; not `.` or `..` |
| `SkillsShSkill` | `source` | yes | — | non-blank `str` |
| `SkillsShSkill` | `directory` | no | `".agents/skills"` | `str` or `Path`; not `""`; stored absolute |
| `GitHubSkill` | `name` | yes | — | one path segment (as above) |
| `GitHubSkill` | `repo` | yes | — | matches `GITHUB_REPO_PATTERN` (`owner/repo`, letters, digits, `-`, and for the repo also `.` and `_`); repo segment not `.` or `..` |
| `GitHubSkill` | `ref` | no | `None` (→ `HEAD`) | `None` or non-blank `str` |
| `GitHubSkill` | `path` | no | `None` (→ tree search) | `None`, or `/`-separated non-empty segments naming a folder below the root, none `.` or `..` (so `"."` is rejected, Q-6), no leading `/`, no `\`, last segment not `SKILL.md` |
| `GitHubSkill` | `token` | no | `None` (→ `GITHUB_TOKEN`) | `None` or non-blank `str`; `repr=False` |
| `AnthropicSkill`, `OpenAISkill` | `skill_id` | yes | — | non-blank `str` |
| `AnthropicSkill`, `OpenAISkill` | `version` | no | `"latest"` | non-blank `str` (an `int` is rejected with a hint to pass `"2"`) |
| `AnthropicSkill`, `OpenAISkill` | `api_key` | no | `None` (→ env var) | `None` or non-blank `str`; `repr=False` |

**`SkillResolution`**: `document: SkillDocument | None`, `reason: SkillUnavailableReason | None`, `detail: str | None`; valid iff (`document` set, `reason` and `detail` `None`) or (`document` `None`, `reason` set, `detail` non-blank). `transient` is derived, never stored (C002).

**`JevSkillResult`** gains `reason` and `detail` (defaults `None`) and relaxes `description` to `str | None`; its `__post_init__` enforces INV-17 at the record level (reason set iff `UNAVAILABLE`; detail non-blank iff reason set; `description` `None` only when `UNAVAILABLE`).

**Loader memory** (the only state): `dict[SkillEntry | SkillDocument, SkillResolution]` keyed by the entry (hashable). Natural key: the entry value; names are unique, so no two keys collide. Volume: at most the configured entry count, today and in 12 months. Lifecycle per entry: `absent → remembered` (document or permanent reason) on the first load that produces one; `absent → absent` on a transient reason; `remembered` is terminal for the agent's lifetime and is never replaced (r2, R-14). `SkillDocument` entries start `remembered`.

### 9.2 API and interface surface

**Public library surface.** The nine names in §8.5's enum and entry blocks, exported from `vidbyte`, `vidbyte.agents`, `vidbyte.agents.jev` (entries and enums), `vidbyte.lib` and `vidbyte.lib.dataclasses` (entries), and `vidbyte.lib.enums` (enums). Validation happens at construction (§9.1) and raises `ConfigurationError` or `TypeError`; nothing raises at run time for an expected source failure. `JevSkillResult` gains two fields. No CLI.

**Outbound requests** (all `GET`, through `SkillFetch`, `follow_redirects=False`, timeout 10 s per network operation, 1 retry on the transport's default retry status codes, 0.5 s backoff, each step bounded by `SKILL_FETCH_DEADLINE_SECONDS`):

| Source and step | URL | Headers (besides httpx defaults) | `max_response_bytes` |
|---|---|---|---|
| GitHub commit lookup (skipped for a full SHA) | `https://api.github.com/repos/{owner}/{repo}/commits/{quote(ref or "HEAD", safe="")}` | `accept: application/vnd.github.sha`; `authorization: Bearer <token>` when a token exists | `SKILL_DOWNLOAD_MAX_BYTES` |
| GitHub tree listing (only if an entry lacks `path`) | `https://api.github.com/repos/{owner}/{repo}/git/trees/{sha}?recursive=1` | `accept: application/vnd.github+json`; token as above | `SKILL_DOWNLOAD_MAX_BYTES` |
| GitHub raw file | `https://api.github.com/repos/{owner}/{repo}/contents/{quote(folder + "/SKILL.md", safe="/")}?ref={sha}` | `accept: application/vnd.github.raw`; token as above | `SKILL_MARKDOWN_MAX_BYTES` |
| Anthropic content | `{anthropic default endpoint}/skills/{quote(id, safe="")}/versions/{quote(version, safe="")}/content` | `x-api-key`, `anthropic-version: 2023-06-01`, `anthropic-beta: skills-2025-10-02` | `SKILL_DOWNLOAD_MAX_BYTES` |
| Anthropic metadata (latest fallback only) | `{anthropic default endpoint}/skills/{quote(id, safe="")}` | same | `SKILL_DOWNLOAD_MAX_BYTES` |
| OpenAI content / metadata | same paths on `{openai default endpoint}` | `HttpResponseParser.bearer_headers(key)` | same |

**Failure mapping.** `SkillFetch` maps transport exceptions; each resolver maps HTTP statuses. "Rem." = remembered.

| Condition | GitHub | Anthropic / OpenAI | Rem. | Detail must name |
|---|---|---|---|---|
| `ProviderRequestError`, `status_code` None (connection error, timeout; not retried by the transport) | `FETCH_FAILED` | `FETCH_FAILED` | no | the host and step; "retried on the next run"; for the GitHub tree listing, that `path=` skips it (r3, R-22) |
| the step exceeds `SKILL_FETCH_DEADLINE_SECONDS` (`TimeoutError` from `asyncio.timeout`, confirmed with `deadline.expired()`) | `FETCH_FAILED` | `FETCH_FAILED` | no | the host, the step, and the deadline; for the GitHub tree listing, that `path=` skips it (r3, R-22) |
| `ProviderRequestError`, 2xx `status_code` (body over the cap) | `TOO_LARGE` | `TOO_LARGE` | yes | the step and the cap |
| `ProviderRequestError`, other `status_code` (oversized error body) | `FETCH_FAILED` | `FETCH_FAILED` | no | the status |
| 301, 302, 307, 308 | `NOT_FOUND` ("may have moved") | `FETCH_FAILED` | GH yes / vendor no | the status; for GitHub, "use the current owner/repo" |
| 400 | `FETCH_FAILED` | `NOT_FOUND` (after the latest fallback, if any) | GH no / vendor yes | skill id and version |
| 401 | `AUTH_FAILED` | `AUTH_FAILED` | yes | which key or token to fix (env var name) |
| 403 with `x-ratelimit-remaining: 0` or a `retry-after` header | `RATE_LIMITED` | `AUTH_FAILED` | GH no / vendor yes | GitHub: "set GITHUB_TOKEN for a higher limit" |
| 403 otherwise | `AUTH_FAILED` | `AUTH_FAILED` | yes | which key or token to fix |
| 404 | `NOT_FOUND` ("not found, or private: set GITHUB_TOKEN or pass token=") | `NOT_FOUND` (after the latest fallback, if any) | yes | repo/ref/path, or skill id and version; for an explicit vendor version, also that the content route may be the cause (A-1; r3, R-19) |
| 404 for the version named by the skill record (latest fallback) | — | `NOT_FOUND` | yes | that the skill exists but its content route was not found (A-1) |
| 422 | `NOT_FOUND` (unknown ref) | `NOT_FOUND` (after the latest fallback, if any) | yes | the ref, or skill id and version |
| 429 | `RATE_LIMITED` | `RATE_LIMITED` | no | "retried on the next run" |
| any other status (5xx including 529, other 3xx and 4xx) | `FETCH_FAILED` | `FETCH_FAILED` | no | the status |
| 200 with an unexpected body (a non-SHA commit answer, a tree that is not JSON or nests too deeply, metadata without a usable `latest_version`/`latest_version_id`) | `FETCH_FAILED` | `INVALID_SKILL` (metadata) | GH no / vendor yes | "unexpected answer" |
| 200 body neither a bare `SKILL.md` nor a zip, a bad zip, an encrypted member, a member compressed with anything but stored or deflate, a `SKILL.md` count other than one | — | `INVALID_SKILL` | yes | what was wrong |
| 200 bare `SKILL.md` body over `SKILL_MARKDOWN_MAX_BYTES` (r3, R-19) | — | `TOO_LARGE` | yes | the `SKILL.md` cap |
| missing key; key or token with `VIDBYTE_API_KEY_PREFIX` | a token with the prefix: `AUTH_FAILED`, no request (no token is allowed: unauthenticated) | `AUTH_FAILED`, no request | yes | `api_key=`/`token=` or the env var; that a Vidbyte key cannot be used |

**Local and skills.sh mapping:** `read_capped` returns `None` → `NOT_FOUND` (local) / `NOT_INSTALLED` (skills.sh), with the absolute path in the detail; `OSError` → `FETCH_FAILED`; total size above `SKILL_MARKDOWN_MAX_BYTES` → `TOO_LARGE`; lock `source` mismatch → `INVALID_SKILL`. **Parser:** every failure → `INVALID_SKILL` with an SDK-written message (§6.3 EC-25 to EC-35, EC-109, EC-110). **Jev preload** (detail texts r2, R-7): a loaded document in no batch → `TOO_LARGE`, detail "too large to send to Jev with this request: a batch holding only this skill must fit `JEV_SKILLS_MAX_REQUEST_JSON_BYTES` request bytes and `JEV_SKILLS_MAX_STATE_AND_QUESTION_JSON_BYTES` state-and-question bytes; shorten SKILL.md or the request"; a batch whose Jev call raised a `VidbyteSdkError` → `DECISION_FAILED`, detail "Jev decision request failed (<error class name>); check VIDBYTE_API_KEY and the Jev decision settings; the run continued without this skill"; a reply without token counts → `DECISION_FAILED`, detail "Jev's reply had no token counts, so its answers were not used"; a missing or malformed answer → `DECISION_FAILED`, detail "Jev answered this batch but gave no usable answer for this skill".

**Expected exception classes caught** (nothing else is caught): `ProviderRequestError` and the deadline's `TimeoutError` (in `SkillFetch`); `OSError` (around local reads); `ConfigurationError` (from `resolve_api_key` only); `UnicodeDecodeError` (around decoding files and answers); `yaml.YAMLError`, `ValueError`, `RecursionError` (around `yaml.safe_load` only); `ValueError` (which includes `json.JSONDecodeError`) and `RecursionError` (around each `json.loads` only); `zipfile.BadZipFile`, `zlib.error`, `EOFError`, `NotImplementedError`, `ValueError` (around `ZipFile(...)` construction and the member read only; `ValueError` includes `UnicodeDecodeError`; r3, R-16); `VidbyteSdkError` from Jev (unchanged).

### 9.3 Configuration and flags
| Variable / key | Required | Default | Purpose | Lives in |
|---|---|---|---|---|
| `GITHUB_TOKEN` (env) | no | unset (unauthenticated, 60 requests/hour) | token for `GitHubSkill` entries without `token=` | read at load time by the GitHub resolver; name in the skills constants module |
| `ANTHROPIC_API_KEY` (env) | only for `AnthropicSkill` without `api_key=` | unset → `AUTH_FAILED` | Anthropic Skills API key | `ProviderModelRegistry.API_KEY_ENV_VARS` (existing) |
| `OPENAI_API_KEY` (env) | only for `OpenAISkill` without `api_key=` | unset → `AUTH_FAILED` | OpenAI Skills API key | `ProviderModelRegistry.API_KEY_ENV_VARS` (existing) |
| `SKILL_MARKDOWN_MAX_BYTES` | constant | `1_048_576` | cap per `SKILL.md` (about 10× the largest measured community `SKILL.md`, 105,146 bytes) | skills constants module |
| `SKILL_DOWNLOAD_MAX_BYTES` | constant | `33_554_432` | cap per zip, tree, or metadata body (above Anthropic's 30 MB and OpenAI's 25 MB upload limits and GitHub's 7 MB tree limit) | skills constants module |
| `SKILL_FETCH_TIMEOUT_SECONDS` / `SKILL_FETCH_RETRY_COUNT` / `SKILL_FETCH_BACKOFF_SECONDS` | constant | `10.0` / `1` / `0.5` | NFR-1 | skills constants module |
| `SKILL_FETCH_DEADLINE_SECONDS` | constant | `25.0` | whole-step deadline, retries included (D-27) | skills constants module |
| `SKILL_TRANSIENT_REASONS` | constant | `frozenset({RATE_LIMITED, FETCH_FAILED})` | INV-5 | skills constants module |

No new settings fields, flags, or knobs beyond the agreed entry fields.

### 9.4 Migrations and compatibility
No stored data. Public contract changes, all additive except one tightening: `JevSkillResult` now requires `reason` and `detail` on `UNAVAILABLE` and accepts `description=None`; a caller constructing `JevSkillResult(status=UNAVAILABLE)` without a reason now raises. This is acceptable without a deprecation path because skill preloading is on SDK main only (not in PyPI 0.2.1). `JevAlignmentSettings.skills` and `JevSkillsPreload(skills=...)` accept a superset of today's values. `SkillDocument` keeps every export. The contract file gains nine names and loses none, so the vidbyte-cli notice (required only on removal or rename) does not apply. The external docs page that says other sources "come later" becomes stale; updating it is outside this repository (NG-12).

## §10 Security and tenancy
| ID | Attacker | Shortest path to harm | Control | Where the control sits |
|---|---|---|---|---|
| T-1 | Careless user | Prints settings or results, pastes a token into `repo="https://x:TOKEN@github.com/o/r"`, or keeps a Vidbyte key in `OPENAI_API_KEY` or `GITHUB_TOKEN`. | `repr=False` on secrets; secrets never in labels, details, or responses (INV-14); `repo` must match `owner/repo` (EC-48); a `vb_live_` key is never sent to GitHub or a vendor (INV-15, D-30). | entry records; resolvers |
| T-2 | Hostile skill author (third-party repo, fork, vendor archive) | Ships prompt-injection text; a same-named fork installed via skills.sh; a zip bomb or huge file; YAML that constructs objects; a name like `../../x` to read other files. | Text is only ever appended after Jev selects it and is never executed or followed (INV-13, existing preload rule); the lock-source check (EC-41); size caps and declared-size checks (INV-12); `yaml.safe_load` (EC-34); one-segment names (EC-37, EC-51); the SHA in the label for audit; docs advise trusted skills only. | parser, resolvers, records |
| T-3 | Compromised teammate / leaked credential | Pushes new text to a branch an agent tracks; captures a key via a redirect or a log. | Resolved text is remembered for the agent's lifetime (no mid-process change); pinning `ref` to a SHA or tag is available and the label shows the SHA; no redirect is followed, so `x-api-key` cannot reach another origin; keys go only to fixed default hosts (no configurable base URL). | GitHub and vendor resolvers, `SkillFetch` |
| T-4 | Another tenant | In a multi-tenant process, (a) one tenant's agent reuses another's resolved private skill text, or (b) an app builds entries from tenant input with no `token`/`api_key`, so the resolver uses the operator's `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` to read private repositories or vendor skills into that tenant's instructions. | (a) Memory is per agent, never module-level (INV-6); GitHub groups include the token (EC-61). (b) Not prevented by the SDK: entries are trusted configuration and the agreed env fallback uses process credentials; the package README tells apps that build entries from untrusted input to pass an explicit `token=`/`api_key=` or unset those variables (EC-114; r2, R-5). | `SkillLoader`, `GitHubSkillResolver`; package README |

Auth on every outbound call is the source's own (GitHub token, vendor key) and is enforced server-side by those vendors; the SDK adds no endpoint or command of its own. Secrets follow the repo's existing conventions: `field(repr=False)` like `JevAgentSettings.api_key`, the provider registry's env-var names, and `VIDBYTE_API_KEY_PREFIX` as the only spelling of the Vidbyte prefix (C020). Local labels carry only the folder name (D-21), so no machine path reaches Jev; local `not_found` details name the absolute path, as agreed in the conversation, and appear only in the caller's own results.

## §11 Codebase grounding

- **Rules read:** `AGENTS.md` (principles 1–5; placement rules for dataclasses, enums, and new JEV code; "docs/ is opaque"; full gate); `REPO_MAP.md` (File Index entries for `vidbyte/agents/*`, the three similarly-named skills locations, the JEV table); folder READMEs `vidbyte/agents/coding_context/README.md`, `vidbyte/agents/jev/README.md`, `vidbyte/skills/README.md`, `lint/README.md`, `contracts/README.md` (via `context/code-map.md` §1–§2); file headers of every file in §12.3; `skills/jev-agent/SKILL.md` Invariants (line 109, read in r2).
- **Field-guide entries applied** (all under `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`, via code-map §1):
  - `jev-capability-layout.md` — JEV capability modules hold no module-level constants; outcomes go through `JevResponse`; usage only via `JevUsage.from_decision`/`total`. (Its "one request per candidate" line is out of date: the code batches.)
  - `blocking-lint-invariants.md` — A006 counts function-local imports; S012 flags any helper named `request`; A007: size a capped read with `os.fstat`; C002: derive bools.
  - `local-ci-verification.md` — run the source stage with `PYTHONPATH` and the package stage without; `git add` new files before lint and semgrep; check S051 over the whole tree.
  - `comment-format.md` — 72-column `#` blocks above the line, `# @intent <name>` on the first line.
  - `strict-config-dataclasses.md` — key fields `repr=False`; avoid unions unless structurally required; reusable bounds in `vidbyte/lib/constants/`; local size caps generous and derived from vendor limits.
  - `provider-api-contracts.md` — mirror the vendor reference; one guarded call per step with a documented status map; never catch `BaseException`.
  - `class-bound-helpers.md` — prefer a `@staticmethod` helper class to loose module functions (`SkillMarkdown`, `SkillText`).
  - `prebuilt-agents.md` — never add a `vidbyte-sdk` CLI command.
  - `cli-backed-source-integrations.md` — authentication and command failures stay failures rather than switching transports.
- **Stack (from manifests):** Python `>=3.11` (local 3.11.0; CI 3.11 and 3.12); `httpx>=0.27` (0.28.1 installed); `PyYAML>=6,<7` (6.0.2); dev: `pytest==8.3.5`, `pytest-asyncio==1.3.0`, `mypy==2.3.1`, `ruff==0.16.4`; no database.
- **Commands (exact, from `context/code-map.md` §1 / §3 and AGENTS.md):**
  - Install: none in AGENTS.md; CI uses `pip install -e ".[dev]"`. In this worktree prefer `PYTHONPATH=$(pwd)`.
  - Lint: `python lint/run.py` (`--rule <ID>`, `--format json`); imports: `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` (filter to changed paths).
  - Typecheck: mypy runs inside lint as rule S009 (baseline 350).
  - Test (focused): `PYTHONPATH=$(pwd) python -m pytest tests/test_jev_skill_preload.py -q`; `python scripts/test-jev-skills-preload.py`.
  - Test (full): `PYTHONPATH=$(pwd) python -m pytest`.
  - Full local gate: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` (no `PYTHONPATH`); `python scripts/run_ci.py` is the canonical whole gate.
  - Contract: commit `vidbyte/__init__.py` first, then `python scripts/generate-sdk-public-api.py`; check with `python scripts/generate-sdk-public-api.py --check`.
  - Remote-only checks: semgrep (`.github/workflows/static-policy.yml`, dispatch-only, `semgrep==1.170.1` in its own venv); `ci.yml` is dispatch-only.
- **Baseline on clean `origin/main`:** the full gate was not run by S0 or S1. S1 ran `python lint/run.py --rule A001` at base: `RATCHETED`, 643/643; one of the 643 is `vidbyte/lib/enums/skills.py` (old "Context Protocol Header"). Other baselines from `lint/baseline.json`: A002 703, A006 34, A007 255, S009 350, S011 0, S012 0, S015 13, S020 1, S024 25, S047 0, S061 6, S063 4, S064 4, C016 0.
- **Directory layout relevant to this change:**
  ```
  vidbyte/
    agents/
      coding_context/        # sibling pattern (README, empty __init__, base + subclasses)
      jev/alignment/skills.py  # JevSkillsPreload (modified)
      jev/settings.py        # JevAlignmentSettings (modified)
      skills/                # NEW: loader, resolvers, parser, fetch step
    lib/
      constants/skills.py    # NEW
      dataclasses/skills.py  # SkillDocument + entries + SkillResolution
      dataclasses/jev.py     # JevSkillResult (modified)
      enums/skills.py        # + SkillSourceType, SkillUnavailableReason
      http/transport.py      # HttpTransport (used, unchanged)
      registries/models.py   # ProviderModelRegistry (used, unchanged)
    skills/                  # packaged skill catalog (different concept; untouched)
  ```
- **Nearest sibling feature (the template to copy):** `vidbyte/agents/coding_context/` (`README.md`, `__init__.py`, `root_file.py`, `agents_md.py`, `map_md.py`) — copy the empty `__init__`, the A001 headers with FUNCTION INVENTORY and WHAT NOT TO DO, the base class with thin subclasses and a raising hook, the narrated main function, the `fstat` capped read, and the short README ending in `## Notes for agents`.
- **Reusable pieces:**
  - `vidbyte/lib/http/transport.py:HttpTransport.request` — every request; non-2xx is returned, connection errors raise `ProviderRequestError(status_code=None)`, an oversized body raises `ProviderRequestError(status_code=<status>)`, `raw_bytes` is set only when `max_response_bytes` is passed, headers are a dict with lowercase keys, a new `httpx.AsyncClient` per call (default `user-agent: python-httpx/<v>`, which GitHub requires).
  - `vidbyte/lib/http/parser.py:HttpResponseParser.bearer_headers` — OpenAI auth header.
  - `vidbyte/lib/registries/models.py:ProviderModelRegistry.resolve_api_key`, `.get_default_endpoint` — vendor keys and base URLs.
  - `vidbyte/lib/constants/jev.py:VIDBYTE_API_KEY_PREFIX` — the only allowed spelling of `vb_live_` (C020).
  - `vidbyte/lib/dataclasses/skills.py:SkillDocument` — the resolved record (unchanged).
  - `vidbyte/lib/errors/base.py:ConfigurationError`, `ProviderRequestError` (`.status_code`).
  - `vidbyte/agents/jev/alignment/skills.py:JevSkillsPreload` — batching, scoring, appending (kept).
- **Considered and not reused:** `vidbyte/sources/`, the artifact fetch and cache layer. `fetches/http.py:HttpFetcher` wraps the blocking `SyncHttpTransport.request_bytes`, which would block the event loop inside `arun`. It raises `SourceFetchError` carrying a response excerpt on non-2xx, while skill loading needs a reason per status and never echoes bodies. `fetches/file.py` reads files whole with `path.read_bytes()`, with no cap (r2, R-12).
- **Implementer facts verified in review round 2** (binding; r3):
  - `vidbyte/lib/registries/models.py:ProviderModelRegistry.resolve_api_key` and `find_vidbyte_api_key` (lines 162–190) strip the explicit and env values before checking or returning them; GitHub tokens are stripped the same way before the prefix check (D-30).
  - C020 scans production literals only: any detail that mentions the Vidbyte prefix builds it from `VIDBYTE_API_KEY_PREFIX`; tests may spell `vb_live_`.
  - A002 matches names and attribute names split on `_` and `.`, so a function that references `SkillUnavailableReason.FETCH_FAILED` counts as "fetch" and needs an `@intent` block (rows 10, 13–16); the inline, anthropic, and openai modules need none unless they reference such a name.
  - `HTTPStatus(529)` raises `ValueError`; look status maps up with the integer, as `vidbyte/lib/http/vidbyte_gateway.py` does at lines 98–106 (`if status in reasons`) (D-11).
  - `vidbyte/harnesses/execution.py:_invoke_with_timeout` (lines 205–219) checks `deadline.expired()` before treating a `TimeoutError` as its own deadline; `SkillFetch.get` copies that.
  - `tests/test_jev_skill_preload.py` (lines 415–424) assigns `agent.skill_preload.run = preload` on the instance, so `JevSkillsPreload` stays a plain class with no `__slots__` and no dataclass decorator.
  - `zipfile` on Python 3.11 raises `ValueError` (negative seek), `UnicodeDecodeError` (UTF-8-flagged names), `OSError` and `LZMAError` (corrupt bzip2 and lzma members) besides the r2 list; D-20's method check plus catch list let none escape in the reviewer's 60,000-case fuzz.
- **Code-style exemplar** (`vidbyte/agents/coding_context/root_file.py`):
  ```python
      @classmethod
      def _read_capped(cls, path: Path) -> tuple[bytes, int]:
          """Return at most MAX_BYTES of path's bytes and the file's total size, or raise naming path."""
          # @intent present-but-broken-root-file-fails-construction
          # A directory, a dangling link, or an unreadable file under the
          # name is there but broken; skipping it would hide that.
          if not path.is_file():
              raise ConfigurationError(f"CodingAgent found {path}, but it is not a readable regular file.", details={"path": str(path)})
          try:
              with path.open("rb") as handle:
                  total_bytes = os.fstat(handle.fileno()).st_size
                  return handle.read(cls.MAX_BYTES), total_bytes
          except OSError as exc:
              raise ConfigurationError(f"CodingAgent could not read {path}.", details={"path": str(path), "error": type(exc).__name__}) from exc
  ```
- **Verified by experiment (S1, local only):** frozen slotted dataclass inheritance with a base `type = field(init=False)` and per-subclass defaults works on 3.11.0 and 3.13.1, rejects `type=`, keeps repr order, and pickles; `super().__post_init__()` raises `TypeError` in slotted subclasses; `dict(httpx_response.headers)` keys are lowercase; `yaml.safe_load` parses folded `>` descriptions; a corrupt deflate member raises `zlib.error`, a truncated archive `BadZipFile`, a member lying about its size `BadZipFile` (bad CRC) with output bounded by the declared size; `PureWindowsPath(".agents/skills") / "C:x"` is `C:x`; `quote("release/v1", safe="")` is `release%2Fv1`.
- **Domain glossary:** *entry* — a user-facing `SkillEntry` subclass saying where a skill lives; *resolve/load* — turn an entry into a `SkillResolution`; *document* — `SkillDocument`, the resolved record Jev judges; *label* — the `source` string on a document and result; *remembered* — kept in the loader's memory for the agent's lifetime; *transient* — `RATE_LIMITED` or `FETCH_FAILED`; *Jev* — the decision model behind `DecisionModelHelper`; *skills.sh* — Vercel's agent-skills directory, `npx skills` its CLI.
- **Prior specs / design docs / ADRs that constrain this:** none named by the orchestrator; `docs/design/jev-skills-preload.md` exists and was deliberately not read.
- **Conflicts between house style and AGENTS.md:** none material. The house style's function length (~40–50 lines) matches; the house-style README "file index" is not adopted because `## File Index` headings trigger S020 parity and the sibling README has none (repo wins).

## §12 Work breakdown — everything this PR has to do

### 12.1 Feature list
| ID | Feature (capability this PR adds) | Serves | Visible to |
|---|---|---|---|
| W-1 | Declarative skill entries: `SkillEntry`, six subclasses, `SkillSourceType`, construction validation | FR-1, FR-2, FR-3, AC-2, AC-11, AC-17 | developer |
| W-2 | `SkillLoader`: lazy, per-agent memory, grouping, concurrency | FR-4, FR-5, AC-10, AC-15, AC-18, AC-27 | developer (via results) |
| W-3 | Inline source | FR-6, AC-3 | developer |
| W-4 | Local source | FR-7, AC-4 | developer |
| W-5 | skills.sh source with lock check | FR-8, AC-5, AC-6 | developer |
| W-6 | GitHub source with shared lookups | FR-9, AC-7, AC-13, AC-22 | developer |
| W-7 | Anthropic source (zip, latest fallback) | FR-10, AC-8, AC-19, AC-25, AC-28 | developer |
| W-8 | OpenAI source | FR-11, AC-9, AC-12, AC-26, AC-29 | developer |
| W-9 | Shared `SKILL.md` parser and shared HTTP step | FR-12, INV-19, AC-20, AC-23, AC-24 | developer (indirect) |
| W-10 | Explained results and Jev wiring (`reason`, `detail`, `TOO_LARGE`, `DECISION_FAILED`) | FR-13, FR-14, AC-1, AC-14, AC-16 | developer, end user |
| W-11 | Public exports and API contract | FR-15, AC-17 | developer |
| W-12 | Package README, repo map, headers, feature pack, lint ratchet | FR-16, NFR-6, AC-21 | operator / future agents |

### 12.2 Folder and module map
| Folder | Kind of code (per repo rules) | New? | README / header obligation | May import from |
|---|---|---|---|---|
| `vidbyte/lib/enums/` | every enum (placement rule) | no | A001 header on `skills.py` (upgrade from the old style) | stdlib only |
| `vidbyte/lib/constants/` | reusable bounds and names | no (new module) | A001 header; `__all__` | `vidbyte.lib.enums` |
| `vidbyte/lib/dataclasses/` | every dataclass (placement rule) | no | A001 header on `skills.py` rewritten | `vidbyte.lib.*` only (never upward) |
| `vidbyte/agents/skills/` | agent-agnostic skill loading (user directive, D-2) | **yes** | `README.md` with `## Notes for agents` (≤ 40,000 chars, no `## File Index`); A001 header on every module; `REPO_MAP.md` entry | `vidbyte.lib.*` and its own sibling modules; never `vidbyte.agents.jev` or any `from vidbyte.agents import …` |
| `vidbyte/agents/jev/` | JevAgent capability wiring | no | headers of `settings.py` and `alignment/skills.py` updated | `vidbyte.lib.*`, `vidbyte.agents.skills.loader` |
| `vidbyte/`, `vidbyte/agents/`, `vidbyte/lib/` package roots | public re-exports | no | — | as today |
| `contracts/` | generated public API contract | no | regenerate, never hand-edit | — |

### 12.3 File-by-file actions
| # | Action | Path | Kind of code | What exactly changes (symbols, signatures, exports, registrations) | Governing standard (AGENTS.md § / placement rule / field-guide file / lint rule ID) | Serves | Phase |
|---|---|---|---|---|---|---|---|
| 1 | MODIFY | `vidbyte/lib/enums/skills.py` | enum | Add `SkillSourceType(str, Enum)` (6 members), `SkillUnavailableReason(str, Enum)` (8 members), and `SkillFetchStep(str, Enum)` (5 members; r3, R-17) with the values in §8.5; add all three to `__all__`; replace the "Context Protocol Header" with an A001 header (PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, FUNCTION INVENTORY, COMMON MODIFICATION PATTERNS, WHAT NOT TO DO, KNOWN EDGE CASES, RELATED DOCS, TESTS) covering both the catalog enums and the new ones; leave existing symbols untouched | Placement: enums; A001; AGENTS.md principle 4 (closed sets are enums) | W-1, W-10, FR-2, FR-13 | P1 |
| 2 | MODIFY | `vidbyte/lib/enums/__init__.py` | export | Import and add `SkillSourceType`, `SkillUnavailableReason`, `SkillFetchStep` to `__all__` beside the existing `skills` imports (`SkillFetchStep` goes no further: not in `vidbyte` or `vidbyte.agents.jev`) | Placement: "every public enum is added to the export list" | FR-15 | P1 |
| 3 | CREATE | `vidbyte/lib/constants/skills.py` | constants | A001 header; `SKILL_MARKDOWN_FILE_NAME="SKILL.md"`, `SKILL_MARKDOWN_MAX_BYTES=1_048_576`, `SKILL_DOWNLOAD_MAX_BYTES=33_554_432`, `SKILL_FETCH_TIMEOUT_SECONDS=10.0`, `SKILL_FETCH_RETRY_COUNT=1`, `SKILL_FETCH_BACKOFF_SECONDS=0.5`, `SKILL_FETCH_DEADLINE_SECONDS=25.0`, `SKILL_TRANSIENT_REASONS`, `SKILL_LABEL_HASH_CHARS=12`, `SKILL_NAME_FORBIDDEN_CHARACTERS` (`/`, `\`, `:`, NUL), `SKILL_PATH_SPECIAL_SEGMENTS` (`.`, `..`), `SKILLS_SH_DEFAULT_DIRECTORY=".agents/skills"`, `SKILLS_SH_AGENTS_FOLDER=".agents"`, `SKILLS_SH_SKILLS_FOLDER="skills"`, `SKILLS_SH_LOCK_FILE_NAME="skills-lock.json"`, `SKILLS_SH_LOCK_MIN_VERSION=1`, `GITHUB_API_BASE_URL`, `GITHUB_TOKEN_ENV_VAR="GITHUB_TOKEN"`, `GITHUB_ACCEPT_SHA`, `GITHUB_ACCEPT_JSON`, `GITHUB_ACCEPT_RAW`, `GITHUB_DEFAULT_REF="HEAD"`, `GITHUB_REPO_PATTERN`, `GITHUB_COMMIT_SHA_PATTERN`, `GITHUB_RATE_LIMIT_REMAINING_HEADER`, `GITHUB_RATE_LIMIT_EXHAUSTED="0"`, `HTTP_RETRY_AFTER_HEADER="retry-after"`, `ANTHROPIC_SKILLS_API_VERSION="2023-06-01"`, `ANTHROPIC_SKILLS_BETA="skills-2025-10-02"`, `SKILL_VENDOR_LATEST_VERSION="latest"`, `SKILL_VENDOR_LATEST_VERSION_FIELDS=("latest_version", "latest_version_id")`, `SKILL_ARCHIVE_MAGIC=b"PK\x03\x04"`, `SKILL_ARCHIVE_ENCRYPTED_FLAG=0x1`, `SKILL_ARCHIVE_MAX_DEPTH=1`; `__all__` | AGENTS.md principle 5 / strict-config-dataclasses (bounds in `vidbyte/lib/constants/`); A007; C020 (do not spell `vb_live_` here); A001 | INV-12, INV-19, NFR-1, NFR-4 | P1 |
| 4 | MODIFY | `vidbyte/lib/dataclasses/skills.py` | dataclass | Keep `SkillDocument` byte-for-byte. Add `SkillText` (static helper class: `require(value, field)`, `require_optional(value, field)`, `require_segment(value, field)`), `SkillEntry` (base, D-3), `InlineSkill`, `LocalSkill`, `SkillsShSkill`, `GitHubSkill`, `AnthropicSkill`, `OpenAISkill` (fields and checks per §9.1; each overrides `_validate_source`; `LocalSkill`/`SkillsShSkill` pin paths with `object.__setattr__`), `SkillResolution` (+ `transient` property); extend `__all__`; rewrite the header (it currently says source adapters are follow-on work) with FUNCTION INVENTORY and KNOWN EDGE CASES covering the template hook and slotted `super()` | Placement: dataclasses (existing domain module); AGENTS.md principle 4; strict-config-dataclasses (`repr=False`, `Path | str` precedent); C002 (derive `transient`); class-bound-helpers; A001; A006 (imports `vidbyte.lib` only) | W-1, FR-1 to FR-3, INV-2, INV-14 | P1 |
| 5 | MODIFY | `vidbyte/lib/dataclasses/__init__.py` | export | Import and add `SkillEntry`, `InlineSkill`, `LocalSkill`, `SkillsShSkill`, `GitHubSkill`, `AnthropicSkill`, `OpenAISkill` beside `SkillDocument` (not `SkillResolution` or `SkillText`) | Placement: dataclasses re-export | FR-15 | P3 |
| 6 | MODIFY | `vidbyte/lib/__init__.py` | export | Same seven names beside `SkillDocument`, in imports and `__all__` | mirror `SkillDocument` (INV-21) | FR-15 | P3 |
| 7 | CREATE | `vidbyte/agents/skills/__init__.py` | package marker | A001 header; `__all__: list[str] = []`; no imports | sibling `coding_context/__init__.py`; A001 | W-2 | P2 |
| 8 | CREATE | `vidbyte/agents/skills/README.md` | doc | Intent (agent-agnostic loading of skill entries into `SkillDocument`s), the contract (one resolver per type; fail-open with reasons; memory policy; no I/O at construction), adding a source in steps (enum member, entry class, resolver module, loader map, exports, contract), non-goals, and `## Notes for agents` (no `npx`, no redirects, no secrets in labels or details, never import `vidbyte.agents.jev`, this is the fourth "skills" location in the tree and is not the packaged catalog; entries are trusted configuration and the env fallbacks use process credentials, so apps that build entries from untrusted input pass an explicit `token=`/`api_key=` or unset those variables (T-4); a host whose egress to GitHub or a vendor is blocked pays up to one deadline per step on every run, because transient failures are never remembered (EC-116); the memory is resolved configuration, not run state (D-28); a `SKILL.md` at a GitHub repository root is not supported (Q-6)) | AGENTS.md "Folder READMEs"; A009 (≤ 40,000 chars); S020 (no `## File Index`); C015 (not package data) | FR-16, W-12 | P2 |
| 9 | CREATE | `vidbyte/agents/skills/resolver.py` | service (base) | `SkillEntryT = TypeVar("SkillEntryT", bound=SkillEntry)`; `SkillResolver(ABC, Generic[SkillEntryT])`: `group_key(entry) -> Hashable` returns the entry itself (GitHub overrides it); abstract `async resolve(entries) -> tuple[SkillResolution, ...]` (entries share one group key; one result per entry, in order) | D-22; S009 (generic signatures); AGENTS.md principles 1–3; A001 | W-2, FR-5, INV-9 | P2 |
| 10 | CREATE | `vidbyte/agents/skills/fetch.py` | service | `SkillFetch` with one `HttpTransport()`; `async get(*, url, headers, max_bytes, step: SkillFetchStep)` calls `request(method="GET", …, timeout_seconds=SKILL_FETCH_TIMEOUT_SECONDS, retry_count=SKILL_FETCH_RETRY_COUNT, backoff_seconds=SKILL_FETCH_BACKOFF_SECONDS, max_response_bytes=max_bytes, follow_redirects=False)` inside `asyncio.timeout(SKILL_FETCH_DEADLINE_SECONDS)`, reading the constant as the module global when the call runs (never a default argument or `ClassVar`, so tests can patch it; r3, R-23) and treating a `TimeoutError` as the deadline's only when `deadline.expired()`; maps `ProviderRequestError` per §9.2 (None → `FETCH_FAILED`; 2xx → `TOO_LARGE`; other → `FETCH_FAILED`) and the deadline's `TimeoutError` to `FETCH_FAILED`; returns the response for any HTTP status; detail names host and step, never the exception excerpt | AGENTS.md principle 5; S011, S012 (`timeout_seconds=` passed; never name a helper `request`); S064 (no own retry loop); A002 `@intent`; A007; D-9, D-10, D-27 | W-9, INV-14, INV-19 | P2 |
| 11 | CREATE | `vidbyte/agents/skills/markdown.py` | service (static helper class) | `SkillMarkdown.parse(raw, *, name, source) -> SkillResolution`: strict `utf-8-sig` decode; first line `---` (ignoring line ending and trailing spaces); closing `---` line; `yaml.safe_load` → mapping (the call alone wrapped in `except (yaml.YAMLError, ValueError, RecursionError)`, D-29); non-blank `name` and `description` strings; body = exact text after the closing line, non-blank; returns `SkillResolution(document=SkillDocument(name=name, description=..., text=body, source=source))` or `INVALID_SKILL` with SDK-written details (never YAML error text) | D-12, D-13, D-14, D-29; S049 (safe load only); class-bound-helpers; principle 1 (parse calls only leaf helpers); A001 | W-9, FR-12, INV-11, INV-18 | P2 |
| 12 | CREATE | `vidbyte/agents/skills/inline.py` | service | `InlineSkillResolver.resolve((entry,))` → one document with label `SkillSourceType.INLINE.value`; no I/O | D-21; A001 | W-3, FR-6 | P2 |
| 13 | CREATE | `vidbyte/agents/skills/local.py` | service | `LocalSkillResolver.read_capped(path)` (static, sync: `None` when no regular file; `fstat` + `read(SKILL_MARKDOWN_MAX_BYTES)`; raises `OSError`); `resolve((entry,))` runs it with `asyncio.to_thread`, maps per §9.2 (details name the absolute path), labels `local:<folder name>`, parses | D-6, D-15, D-21, D-23; S047; S061 (`path.open("rb")`, no positional non-literal path); A007 (fstat, no `CAP + 1`); A002; A001 | W-4, FR-7 | P2 |
| 14 | CREATE | `vidbyte/agents/skills/skills_sh.py` | service | `SkillsShSkillResolver.resolve((entry,))`: `<directory>/<name>/SKILL.md` via `LocalSkillResolver.read_capped` in a thread (`None` → `NOT_INSTALLED` with `npx skills add <source> --skill <name>` and the absolute path); lock lookup in a thread only for `<root>/.agents/skills` (absent on any lock problem, including `ValueError`/`RecursionError` from `json.loads`, D-17, D-29); `source` mismatch → `INVALID_SKILL` naming both; label per D-21; parse | D-16, D-17, D-21, D-23; INV-13 (no subprocess); semgrep typed-mapping rule (JSON shape checks on locals, never a helper taking `object` that returns a fallback); A002; A001 | W-5, FR-8 | P2 |
| 15 | CREATE | `vidbyte/agents/skills/github.py` | service | `GitHubSkillResolver.group_key(entry)` → `(repo, ref, token)`; `resolve(group)` (narrated main): token = the entry token, else `os.environ.get(GITHUB_TOKEN_ENV_VAR)`, stripped, and the stripped value is the one sent (blank = none; a token starting with `VIDBYTE_API_KEY_PREFIX` → `AUTH_FAILED` for the group with no request; D-30, r3 R-18); one commit lookup unless `ref` is a full SHA; one tree listing only if some entry lacks `path` (`json.loads` failures, `RecursionError` included → `FETCH_FAILED`, D-29); locate folders (shallowest wins; tie or truncated → `INVALID_SKILL`; none → `NOT_FOUND`); concurrent raw fetches via `SkillFetch.get`; parse; each step leaf (`_commit_sha`, `_tree_paths`, `_raw_documents`) calls `SkillFetch.get` and then `_GitHubAnswer.failure(response, step=…, target=…)`, the private status classifier holding the §9.2 GitHub map (403 inspects `x-ratelimit-remaining` and `retry-after`; D-31, r3 R-21); the tree step's timeout and deadline details say that `path=` skips it (r3, R-22); results in input order | D-10, D-11, D-18, D-21, D-22, D-29, D-30, D-31; INV-7, INV-8, INV-15; S063 (gather of raw fetches); S024 (nesting ≤ 3); A007 (`HTTPStatus` members, constants); C020; A002; A001 | W-6, FR-9, NFR-3 | P2 |
| 16 | CREATE | `vidbyte/agents/skills/vendor.py` | service (base) | `VendorSkillT` constrained to `AnthropicSkill`, `OpenAISkill`; `VendorSkillResolver(SkillResolver[VendorSkillT])` with class attributes `PROVIDER: ClassVar[ModelProvider]`, `SOURCE_TYPE: ClassVar[SkillSourceType]` and abstract-by-raise `_headers(key) -> dict[str, str]`; `resolve((entry,))` (narrated main): key = `ProviderModelRegistry.resolve_api_key(PROVIDER, entry.api_key)`, which strips the entry and env values (missing → `ConfigurationError` → `AUTH_FAILED`); the stripped key `startswith(VIDBYTE_API_KEY_PREFIX)` → `AUTH_FAILED`, no request (D-30, r3 R-18) → content download → latest fallback reading `latest_version`, else `latest_version_id`, where a `bool` is not an integer version (D-19; metadata `json.loads` failures → `INVALID_SKILL`, D-29) → a 404 for the named version keeps `NOT_FOUND` with the "skill exists; content route not found" detail → a 404 for an explicit version names the content route as a possible cause (A-1) → body: a bare `SKILL.md` if it starts with `---` after an optional BOM (over `SKILL_MARKDOWN_MAX_BYTES` → `TOO_LARGE`), else a zip read per D-20 (method check; `ZipFile(...)` and the member read inside D-20's catch list; r3, R-16, R-19) → parse; status map per §9.2; label per D-21 | D-10, D-11, D-19, D-20, D-21, D-29, D-30; INV-12, INV-14, INV-15; C020; A002; A007; A001 | W-7, W-8, FR-10, FR-11 | P2 |
| 17 | CREATE | `vidbyte/agents/skills/anthropic.py` | service | `AnthropicSkillResolver(VendorSkillResolver[AnthropicSkill])`: `PROVIDER=ModelProvider.ANTHROPIC`, `SOURCE_TYPE=ANTHROPIC`, `_headers` → `x-api-key`, `anthropic-version`, `anthropic-beta` | D-19; provider-api-contracts; A001 | W-7, AC-8 | P2 |
| 18 | CREATE | `vidbyte/agents/skills/openai.py` | service | `OpenAISkillResolver(VendorSkillResolver[OpenAISkill])`: `PROVIDER=ModelProvider.OPENAI`, `SOURCE_TYPE=OPENAI`, `_headers` → `HttpResponseParser().bearer_headers(key)` | D-19; AGENTS.md principle 5 (reuse bearer helper); A001 | W-8, AC-9 | P2 |
| 19 | CREATE | `vidbyte/agents/skills/loader.py` | service (coordinator) | `SkillLoader(entries)`: stores entries; pre-remembers each `SkillDocument` as resolved; builds a `dict[SkillSourceType, SkillResolver[Any]]` of the six resolvers (dict dispatch). `async load()`: pending = entries not remembered; group pending entries by `(entry.type, resolver.group_key(entry))`; `asyncio.gather` one `resolve(group)` per group with `return_exceptions=True`, re-raising any `BaseException`; `zip(..., strict=True)`; remember non-transient resolutions only for entries not yet remembered (never replace); then return, per entry in order, the remembered resolution where one exists and this load's own otherwise, so `documents()` always agrees with the returned tuple (INV-10; r3, R-20). `documents()`: remembered documents in order. Narrated `load` | D-5, D-6, D-22, D-24; INV-4 to INV-10; S063; TID251 (no `asyncio.Lock`); principles 1 and 2; A002; A001 | W-2, FR-4, FR-5 | P2 |
| 20 | MODIFY | `vidbyte/lib/dataclasses/jev.py` | dataclass | `JevSkillResult`: `description: str | None`; add `reason: SkillUnavailableReason | None = None`, `detail: str | None = None`; `__post_init__` enforces INV-17 (reason type; reason set iff `UNAVAILABLE`; detail non-blank iff reason set; description non-blank unless `None` on `UNAVAILABLE`); import the enum from the skills enum module | Placement: JEV records in `jev.py`; AGENTS.md principle 4; A006 (lib-only import) | W-10, FR-13, INV-17 | P3 |
| 21 | MODIFY | `vidbyte/agents/jev/settings.py` | settings | `JevAlignmentSettings.skills: tuple[SkillEntry | SkillDocument | str, ...]`; `_normalized_skills() -> tuple[SkillEntry | SkillDocument, ...]` accepts `SkillEntry` instances unchanged, keeps the string normalization and duplicate check exactly, updates the three error messages to list the accepted types; update the header's KNOWN EDGE CASES | Placement exception: agent settings in the agent's `settings.py`; INV-3, INV-20 | W-1, FR-1, FR-3 | P3 |
| 22 | MODIFY | `vidbyte/agents/jev/alignment/skills.py` | service | `JevSkillsPreload` stays a plain class (no `__slots__`, not a dataclass), because the existing test assigns `run` on the instance (r3, R-23). `__init__`: widen `skills`, keep `self.skills`, add `self.loader = SkillLoader(skills)`. `run`: load first (`await self.loader.load()`), seed each result from its resolution (unloaded → `UNAVAILABLE` with the loader's reason and detail, `description=None`, `source=None`; loaded → `UNAVAILABLE`/`DECISION_FAILED` until Jev answers), build batches, mark loaded-but-unbatched as `TOO_LARGE`, then the existing gather, usage, and scoring; selected documents come from `self.loader.documents()`. `_build_batches(message)` iterates `self.loader.documents()` and skips `None`; `_build_batch` reads documents; `_score_skill` gives `DECISION_FAILED` with the missing-answer detail; a failed batch's skills get the failed-batch detail naming the error class and `VIDBYTE_API_KEY`, and a reply without token counts gets its own detail (§9.2; r2, R-7). Keep every existing `@intent`; update narration and header (the "keep source resolution outside" note becomes "resolution is delegated to `SkillLoader`") | D-8; INV-16, INV-17, INV-22 to INV-26; jev-capability-layout (no module-level constants; outcomes via `JevResponse`); S063; principle 2; A001 | W-10, FR-13, FR-14, AC-14, AC-16 | P3 |
| 23 | MODIFY | `vidbyte/agents/jev/__init__.py` | export | Import the seven entry names from the skills dataclass module and the two public enums (`SkillSourceType`, `SkillUnavailableReason`; not `SkillFetchStep`) from the skills enum module; add to `__all__` | public package boundary (header) | FR-15 | P3 |
| 24 | MODIFY | `vidbyte/agents/__init__.py` | export | Re-export the nine names from `vidbyte.agents.jev`; add to `__all__` | mirrors `SkillDocument`, `JevSkillStatus` | FR-15 | P3 |
| 25 | MODIFY | `vidbyte/__init__.py` | export | Import the nine names from `vidbyte.agents`; add to `__all__` | S015 (`__all__` integrity) | FR-15, AC-17 | P3 |
| 26 | MODIFY | `contracts/sdk-public-api.json` | generated contract | Regenerate after committing row 25 (adds nine names) | C016; contracts/README | FR-15, AC-17 | P3 |
| 27 | MODIFY | `REPO_MAP.md` | doc | Add `##### \`vidbyte/agents/skills/\`` after the `settings/` entry: 4–5 intent sentences (what it is for, that it is agent-agnostic and imports only `vidbyte.lib`, that JevAgent's preload is its consumer, that it is unrelated to the packaged skill catalog); no file names or commands; extend the "similarly-named skills locations" warning from three to four | AGENTS.md "Repository Map"; agents-md-map field-guide style | FR-16 | P4 |
| 28 | MODIFY | `lint/baseline.json` | config | After row 1 makes A001 report IMPROVED (642), run `python lint/run.py --rule A001 --update-baseline` so A001 is 642; change no other key | lint/README "Baseline ratchet" (lower after a real improvement; never raise) | NFR-6 | P4 |
| 29 | MODIFY | `tests/features/jev_skills_preload/FEATURE.md` | test-pack doc | Replace "network/source loaders … are deferred" with the source contract (six entries, reasons, memory policy) and list any new test modules — **owned by the S2 test author**, not the implementer | feature test packs (house style) | FR-16 | S2 |
| 30 | MODIFY | `vidbyte/agents/README.md` | doc | Add one `skills/` line under `## Key Modules`, after the `coding_context/` line: the agent-agnostic loader that turns skill entries into documents for JevAgent's preload (r2, R-12) | AGENTS.md "Folder READMEs"; A009 | FR-16 | P4 |

### 12.4 Standards checklist for this change

- [ ] Every new dataclass is in `vidbyte/lib/dataclasses/skills.py` or `jev.py`; no `types.py`, `records.py`, `models.py`, or `schemas.py` anywhere — *source:* AGENTS.md Placement Rules
- [ ] All three new enums (`SkillSourceType`, `SkillUnavailableReason`, `SkillFetchStep`) are in `vidbyte/lib/enums/skills.py` and exported from `vidbyte/lib/enums/__init__.py`; every `step` parameter is a `SkillFetchStep`, never a `str` — *source:* AGENTS.md Placement Rules; R-17
- [ ] No module in `vidbyte/lib/` imports from `vidbyte.agents` (including function-local imports) — *source:* AGENTS.md principle 3; A006
- [ ] No module in `vidbyte/agents/skills/` imports `vidbyte.agents.jev` or uses `from vidbyte.agents import …` (the package root is partially initialized while JEV imports the loader) — *source:* A006; code-map G7
- [ ] Every new or modified `.py` file has an A001 header with all required fields; `vidbyte/lib/enums/skills.py` is upgraded — *source:* lint A001
- [ ] Every function whose name or body mentions request, fetch, retry, secret, provider, transport, send, or fallback has a `# @intent <name>` block within the A002 window — *source:* lint A002
- [ ] Multi-line comments are 72-column `#` blocks above the line, `# @intent` first — *source:* field guide `comment-format.md`
- [ ] Main functions (`SkillLoader.load`, each resolver's `resolve`, `SkillMarkdown.parse`, `SkillFetch.get`, `JevSkillsPreload.run`) are narrated in plain English — *source:* AGENTS.md principle 2
- [ ] Own-helper calls stay one level deep: each resolver's `resolve`, `SkillLoader.load`, `SkillMarkdown.parse`, and `SkillFetch.get` call only leaf helpers or other classes (the GitHub step leaves call `SkillFetch.get` and `_GitHubAnswer.failure`); no nested functions — *source:* AGENTS.md principle 1; D-22, D-31
- [ ] Functions about 50 lines or fewer; every file well under 1,000 lines; nesting depth ≤ 3 — *source:* AGENTS.md principle 3; house style; S024
- [ ] Every HTTP call goes through `HttpTransport.request` with `timeout_seconds=` and `max_response_bytes=`; no raw `httpx` or `urllib`; no helper named `request` — *source:* AGENTS.md principle 5; S011; S012
- [ ] No retry loops; retries only via `retry_count` — *source:* S064
- [ ] Every `asyncio.gather` uses `return_exceptions=True` and classifies results against `BaseException`, re-raising them — *source:* S063
- [ ] No `open()` inside an async function; disk work runs through `asyncio.to_thread` — *source:* S047 (ASYNC230); D-23
- [ ] Capped reads use the `os.fstat` pattern, never `read(CAP + 1)`; every status, byte, timeout, and retry value is a named constant or an `HTTPStatus` member — *source:* A007; field guide `blocking-lint-invariants.md`
- [ ] No `open(<variable>)`, `.read_text(<arg>)`, `.read_bytes(<arg>)`, or `extractall(...)` — *source:* S061
- [ ] YAML only through `yaml.safe_load` — *source:* S049
- [ ] `vb_live_` is never spelled in production code outside `VIDBYTE_API_KEY_PREFIX`; details that mention it build it from the constant (tests may spell it) — *source:* C020
- [ ] Every third-party parse (`yaml.safe_load`, `json.loads`) catches `ValueError` and `RecursionError` beside its own error, around that call only; the zip read checks the compression method and wraps `ZipFile(...)` and the member read in D-20's catch list — *source:* D-29, D-20
- [ ] Every `SkillFetch.get` body runs inside `asyncio.timeout(SKILL_FETCH_DEADLINE_SECONDS)` — *source:* D-27; INV-19
- [ ] The `VIDBYTE_API_KEY_PREFIX` check runs before any request in the GitHub and vendor resolvers — *source:* D-30; INV-15
- [ ] Keys and tokens are stripped before the prefix check, and the stripped value is sent — *source:* D-30; `resolve_api_key`
- [ ] Status maps are looked up with the integer status; never `HTTPStatus(status)` — *source:* D-11
- [ ] `SKILL_FETCH_DEADLINE_SECONDS` is read as a module global at call time, and a `TimeoutError` counts as the deadline's only when `deadline.expired()` — *source:* D-27; R-23
- [ ] `JevSkillsPreload` stays a plain class (no `__slots__`, no dataclass) — *source:* existing test; R-23
- [ ] No `asyncio.Lock`, no `typing.TypedDict` — *source:* lint/ruff.toml TID251
- [ ] Status flags are derived (`SkillResolution.transient`), never stored beside the field they mirror — *source:* C002
- [ ] Secret fields are `field(default=None, repr=False)`; secrets never in labels, details, responses, or messages — *source:* field guide `strict-config-dataclasses.md`; INV-14
- [ ] No helper takes `object`/`Any` and returns a fallback after an `isinstance(..., Mapping|dict)` check — *source:* `.semgrep/typed-mapping-boundary-policy.yml`
- [ ] Status maps are dicts with an explicit default, not if/else ladders of three or more — *source:* house style; D-11
- [ ] No new `*Error` classes — *source:* A003; D-25
- [ ] `vidbyte/__init__.py` imports and `__all__` agree; contract regenerated after committing the root change — *source:* S015; C016; contracts/README
- [ ] Imports sorted — *source:* S051 (`ruff --select I001`)
- [ ] New files are `git add`-ed before lint and semgrep — *source:* field guide `local-ci-verification.md`
- [ ] No SDK CLI command, no subprocess, no `npx` — *source:* field guide `prebuilt-agents.md`; NG-2, NG-6
- [ ] The new README has no `## File Index` heading and stays under 40,000 characters — *source:* S020; A009

### 12.5 Non-code actions

- Package README with `## Notes for agents` — `vidbyte/agents/skills/README.md` — *AGENTS.md "Folder READMEs"* (row 8)
- Agents folder README `## Key Modules` line — `vidbyte/agents/README.md` — *AGENTS.md "Folder READMEs"* (row 30)
- Repo map entry and the "skills locations" warning — `REPO_MAP.md` — *AGENTS.md "Repository Map"* (row 27)
- Public exports in five package roots and the regenerated contract — rows 2, 5, 6, 23–26 — *S015, C016*
- Lint baseline lowered for A001 only — `lint/baseline.json` — *lint/README "Baseline ratchet"* (row 28)
- Headers of modified modules updated so none describes removed behavior: `vidbyte/lib/dataclasses/skills.py`, `vidbyte/agents/jev/alignment/skills.py`, `vidbyte/agents/jev/settings.py`, `vidbyte/lib/enums/skills.py` — *A001; AGENTS.md principle 2 ("never describe behavior that is gone")*
- Feature pack update — `tests/features/jev_skills_preload/FEATURE.md` — *house-style feature test packs*; owned by S2 (row 29)
- Not done, with reason: `vidbyte/agents/jev/README.md` and the REPO_MAP JEV table never described the preload, and `skills/jev-agent/SKILL.md` never mentioned it (Q-4); `llms.txt` and `artifacts/file_index.md` have no update rule that this change triggers; no `.env.example` exists for the SDK.

### 12.6 Phases and dependency order

**P1 — Records, enums, constants** (ships: the six entries are constructible and validated; nothing is wired; existing tests pass): rows 1, 2, 3, 4.
**P2 — Loading package** (ships: `SkillLoader` resolves all six types standalone; existing tests pass): rows 7–19.
**P3 — Jev wiring and public surface** (ships: the feature end to end, the §4 snippet works): rows 5, 6, 20–26 (`JevSkillResult` changes here, with the preload, because its new invariant rejects today's reason-less `UNAVAILABLE` results).
**P4 — Maps and ratchet** (ships: docs and lint baseline consistent): rows 27, 28, 30. Row 29 is done by S2.

**Dependency order:** row 1 → row 3 (constants import the reason enum) → row 4 → rows 5, 6 (exported in P3) and rows 9–11 → rows 12–18 (any order; 17 and 18 after 16; 14 after 13) → row 19 → rows 20–22 → 23 → 24 → 25 → commit → 26. **Independent:** rows 12, 13, 15, 16 of each other; row 8 at any time in P2; rows 27 and 30 at any time; row 28 after row 1.

## §13 Test seams (facts for the test author — no tests here)

- **Framework:** `pytest==8.3.5` with `pytest-asyncio==1.3.0`; `asyncio_mode` is not `auto`, so async tests need `@pytest.mark.asyncio` or `unittest.IsolatedAsyncioTestCase`; `addopts` has `--strict-config --strict-markers`; unittest classes run under pytest.
- **Layout and naming:** flat `tests/test_<area>.py` modules plus feature packs under `tests/features/<name>/` (FEATURE.md, test modules, optional `conftest.py`). `tests/features/jev_skills_preload/` holds only `FEATURE.md`. Every test file needs an A001 header (lint scans tracked tests). `scripts/test-jev-skills-preload.py` runs `tests.test_jev_skill_preload` through unittest.
- **Prior art to copy:** `tests/test_jev_skill_preload.py` (Jev fakes: patch `vidbyte.agents.jev.alignment.skills.DecisionModelHelper` with `_helper_class(ScriptedDecisionRunner(...))`; `_preloader(...)`; `bind_test_runner` from `tests/agent_test_support.py`); `tests/features/coding_agent/conftest.py:76-88` (`fake_provider_http` monkeypatches `HttpTransport._send_once`); `tests/test_web_operation_client_retry.py:27-40` (patch `vidbyte.lib.http.transport.asyncio.sleep` to skip backoff); `tests/features/coding_agent/test_coding_agent_web_fetch.py:58-74` (env via `monkeypatch.setenv`, sockets and subprocess blocked).
- **Fixtures / factories:** `tests/agent_test_support.py` (`bind_test_runner`); no skill-source fixtures exist yet.
- **Transport facts a fake must honor:** `SkillFetch` always passes `max_response_bytes`, so code reads `HttpResponse.raw_bytes`; a `_send_once` fake receives `max_response_bytes` and must set `raw_bytes` itself. Header keys in real responses are lowercase (`x-ratelimit-remaining`, `retry-after`), so fakes should use lowercase keys. The oversized-body path lives in `_send_bounded`, which a `_send_once` fake bypasses: to exercise it, the fake raises `ProviderRequestError(..., provider="http", status_code=200)`. With `SKILL_FETCH_RETRY_COUNT=1`, a 408, 409, 425, 429, 500, 502, 503, or 504 answer causes exactly one retry after one `asyncio.sleep`. `request` builds an `httpx.AsyncClient` before calling `_send_once`; that is offline.
- **Resolver calls:** `resolve(entries)` expects entries that share one `group_key`: exactly one entry for every source except GitHub, whose entries share `(repo, ref, token)`. `SkillLoader` forms these groups. The default key is the entry itself, which keeps non-GitHub groups single because names are unique (INV-3) and entries are frozen, hashable dataclasses.
- **Timeouts and the deadline:** the transport never retries a timeout or a connection error (only the status codes above). Every `SkillFetch.get` is bounded by `SKILL_FETCH_DEADLINE_SECONDS`, imported by name into the fetch module, so a test shortens it by patching `vidbyte.agents.skills.fetch.SKILL_FETCH_DEADLINE_SECONDS`.
- **Environment facts:** developer machines may have `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` set; tests that expect "no key" must `monkeypatch.delenv(..., raising=False)`. Env vars are read at load time, never at construction.
- **Filesystem facts:** relative `LocalSkill.path` and `SkillsShSkill.directory` are pinned against the working folder at construction (`monkeypatch.chdir(tmp_path)` before constructing). Symlink creation on Windows may need privileges. Disk reads run in worker threads via `asyncio.to_thread`.
- **Archives:** build zips in memory with `zipfile`; the encrypted flag can be set on a `ZipInfo` (`flag_bits |= 0x1`); a lying `file_size` produces a CRC failure on read.
- **Corrupt archives (AC-28):** set `ZipInfo.compress_type = zipfile.ZIP_BZIP2` for the bzip2 case; set flag bit `0x800` on a member whose name bytes are not valid UTF-8; flip bytes in a stored or deflated archive until `zipfile` raises `ValueError`. Each must end `INVALID_SKILL` without escaping `arun`.
- **Keys in tests:** C020 does not scan tests, so AC-12 and AC-22 may spell `vb_live_`; include a padded `" vb_live_…"` case (EC-77).
- **Seams to patch, if a test needs them:** `vidbyte.lib.http.transport.HttpTransport._send_once` (all HTTP); the resolver classes' `resolve` methods (to isolate `SkillLoader`); `vidbyte.agents.jev.alignment.skills.DecisionModelHelper` (Jev).
- **Real seams (do not mock):** `SkillMarkdown.parse`, the entry records' validation, `JevAlignmentSettings`, `SkillLoader`'s memory, `zipfile`, `yaml`, the filesystem under `tmp_path`.
- **Existing tests are a contract:** `tests/test_jev_skill_preload.py` must pass unchanged (AC-16); it calls `preload._build_batches("…")` with one argument before any run, reads `preload.decision.model`, and assigns `agent.skill_preload.run` on the instance (so the preload must stay a plain class).
- **Per-area config:** none beyond `[tool.pytest.ini_options]` in `pyproject.toml`.
- **Run one file:** `PYTHONPATH=$(pwd) python -m pytest tests/<file>.py -q` · **Run all:** `PYTHONPATH=$(pwd) python -m pytest`; whole gate `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` then `python scripts/run_ci.py --stage package`.

## §14 Agent boundaries
- **Always:** keep edits inside this worktree and inside §12.3; `git add` new files before linting; run the focused tests after each phase and the full local gate (source stage with `PYTHONPATH`, package stage without) before pushing; cite W-, FR-, AC-, D- IDs in commit messages; read each folder's README to the end before editing inside it.
- **Ask first (stop and report BLOCKED):** any new dependency; exceeding the §8.4 budget; touching a file outside §12.3; changing a public name or signature in §8.5; any export removal or rename; modifying any test file (including the existing skill-preload test module); changing Jev question wording, thresholds, or batching limits; making a network call to GitHub, Anthropic, OpenAI, or skills.sh outside tests' fakes.
- **Never:** commit secrets, tokens, or real keys; spell `vb_live_` in production code; call `HTTPStatus(status)` on an upstream status; turn `JevSkillsPreload` into a slotted or frozen dataclass; run `npx` or add subprocess calls; add an SDK CLI command; follow redirects in skill fetches; raise any lint baseline or add a suppression; delete, skip, or weaken a failing test; implement WellKnownSkill, VidbyteSkill, PackageSkill, GitLab, refresh APIs, or anything else in §3; push to `main`.

## §15 Assumptions and open questions
**Assumptions** (stand unless the user corrects them):
- **A-1** — Anthropic serves `GET /v1/skills/{id}/versions/{version}/content` as a zip, and keeps honoring `anthropic-beta: skills-2025-10-02` with the beta response shapes. The conversation read the beta reference; Claude's current API notes say the Skills API is GA, that the beta header still works with the old shapes, and do not list the content route. **Pending the user's real-key QA; check before S3 relies on it.** — *If wrong:* `latest` entries report `not_found` with the "skill exists; content route not found" detail (D-19), so the cause is visible; fix the route, headers, or reading in the Anthropic resolver only.
- **A-2** — When a vendor's content route refuses `latest`, it answers 400, 404, or 422, and the skill record names its newest version in `latest_version` or `latest_version_id` (both are read, D-19). — *If wrong:* `latest` entries report `invalid_skill` or `not_found`; adjust the trigger statuses or `SKILL_VENDOR_LATEST_VERSION_FIELDS`.
- **A-3** — Neither vendor's content route redirects. — *If wrong:* every vendor skill reports `fetch_failed`; a re-spec adds a credential-dropping redirect step (D-10).
- **A-4** — OpenAI's version-content route returns zip bytes or a bare `SKILL.md` (both handled, D-20), and accepts `latest` or answers per A-2. **Pending the user's real-key QA; check before S3 relies on it.** — *If wrong* (for example a JSON body): every `OpenAISkill` reports `invalid_skill`; adapt the OpenAI resolver's reading.
- **A-5** — OpenAI's bundle has exactly one `SKILL.md`/`skill.md` under one top-level folder (request.md §C), which D-20's rule accepts.
- **A-6** — GitHub accepts a `%2F`-encoded ref in `/commits/{ref}`, answers 422 or 404 for an unknown ref, 404 for missing or private repositories, 403 with `x-ratelimit-remaining: 0` for the primary limit, and `retry-after` for secondary limits. — *If wrong:* the affected entries get a different reason; adjust the GitHub status map.
- **A-7** — The `skills-lock.json` layout and lock semantics are as read from `vercel-labs/skills` in the conversation (`{version, skills: {<name>: {source, computedHash, …}}}` at the project root), and `npx skills` names the installed folder after the skill's name.
- **A-8** — A `JevAgent` serves one run at a time (D-24). — *If wrong:* concurrent first runs duplicate requests, nothing worse.
- **A-9** — Python 3.12 handles the slotted entry hierarchy like 3.11.0 and 3.13.1 (3.12 is not installed locally; CI covers it).
- **A-10** — The stdlib zip reader never yields more than a member's declared size (verified on 3.11.0: a lying size fails its CRC check).
- **A-11** — Relative entry paths resolve against the working folder at construction (the conversation's default was the process working folder; `CodingAgentSettings.root_dir` is a partial precedent, D-15).
- **A-12** — Correction to request.md §C ("a hanging upstream adds up to timeout × attempts"): the transport retries only on HTTP status codes, so a timeout or connection error costs one attempt in this run and is retried on the next run; a slow upstream is bounded by `SKILL_FETCH_DEADLINE_SECONDS` per step (D-27).

**Open questions** (max 5 blocking):
| ID | Question | Blocking? | Default if unanswered |
|---|---|---|---|
| Q-1 | Re-check local `not_found`, `not_installed`, and missing-key `auth_failed` on every run instead of remembering them? | non-blocking | no |
| ~~Q-2~~ | ~~Add a total wall-clock deadline per skill fetch?~~ Resolved r2 (R-2): built as D-27, because request.md §C assumes a bounded hang. | — | — |
| Q-3 | Rename `SkillsShSkill.source` to `repo` for symmetry with `GitHubSkill`? | non-blocking | no (keep `source`, D-16) |
| Q-4 | Document the preload and the new sources in the in-repo JevAgent skill guide (§12.5)? | non-blocking | no |
| Q-5 | Verify the skills.sh `computedHash` against the installed files? | non-blocking | no |
| Q-6 | Load a `SKILL.md` at a GitHub repository root via `path="."`? (r2, R-8) | non-blocking | not built: `"."` is rejected at construction; a root `SKILL.md` is a documented limitation |
| Q-7 | Reject a skills.sh install whose `skills-lock.json` exists but has no entry for the skill (treat it as a mismatch)? (r2, R-9) | non-blocking | no: accepted, and it loads without the source check (D-17) |

## §16 Review log
| Round | ID | Severity | Section | Finding (one line) | Disposition | Change made / reason |
|---|---|---|---|---|---|---|
| r1-1 | R-1 | Blocker | §9.2, D-12, INV-9 | `yaml.safe_load`/`json.loads` raise `ValueError`/`RecursionError` outside their error types, crashing every run | accepted | D-29; each parse call catches `ValueError` and `RecursionError`; EC-109 to EC-112; AC-23; §9.2 list; rows 11, 14, 15, 16 |
| r1-2 | R-2 | Major | NFR-1, EC-103 | the 20.5 s / 61.5 s bound is false and timeouts are not retried | accepted (option b) | D-27 per-step deadline of 25 s; NFR-1 reworded; EC-66, EC-82, EC-103; A-12 corrects request.md; Q-2 resolved; AC-24; row 10 |
| r1-3 | R-3 | Major | D-22, rows 9/15, §12.4 | base fan-out into `_resolve_one` breaks principle 1 | accepted | the loader groups by `(type, group_key)`; one `resolve` main per resolver; `_resolve_one` removed; §5, §8.5, rows 9, 12–16, 19, §12.4 |
| r1-4 | R-4 | Major | INV-15, EC-77, AC-12 | the Vidbyte-key guard omits GitHub | accepted | INV-15, EC-77, D-30, AC-22, §9.2, row 15 |
| r1-5 | R-5 | Major | §10 T-4 | the env fallback gives tenant-built entries the operator's credentials | accepted (documentation) | T-4 rewritten; EC-114; README note (row 8) |
| r1-6 | R-6 | Major | A-1, A-2, A-4 | vendor assumptions handle one outcome; a wrong route reads as a bad id | accepted | D-19 reads both fields and gives a distinct detail; D-20 bare `SKILL.md` branch; A-1/A-4 marked for real-key QA; AC-25, AC-26 |
| r1-7 | R-7 | Minor | §9.2 | `DECISION_FAILED` detail unspecified | accepted | three detail texts in §9.2; EC-105; AC-14; row 22 |
| r1-8 | R-8 | Minor | D-18, EC-73 | `path="."` was not discussed | → Q-6 (scope-adding; not built) | removed from D-18, D-21, §8.5, §9.1, §9.2, row 3; `"."` rejected (EC-49); EC-73 now a documented limitation; NG-13 |
| r1-9 | R-9 | Minor | EC-44, D-17 | cites an orchestrator decision that does not exist | accepted → Q-7 | EC-44 and D-17 cite S1's own choice; Q-7 (default: accept) |
| r1-10 | R-10 | Minor | D-21, AC-4 | the local label leaks a machine path | accepted | label `local:<folder name>`; INV-18 covers labels; AC-4; §10 note; row 13 |
| r1-11 | R-11 | Minor | §12.6 | rows 5 and 6 missing from phases | accepted | P3 lists rows 5, 6; dependency row 4 → rows 5, 6 |
| r1-12 | R-12 | Minor | §11, §12 | the `vidbyte.sources` fetch layer not discussed; agents README index stale | accepted | §11 "Considered and not reused"; row 30 |
| r1-13 | R-13 | Minor | NFR-4 | per-download peak is about 4× the cap and there is no total | accepted (stated limitation) | NFR-4 reworded; EC-113 |
| r1-14 | R-14 | Minor | EC-95 | "later write wins with an equal value" is false | accepted | a remembered resolution is never replaced (INV-5, D-24, row 19); EC-95 reworded; AC-27 |
| r1-15 | R-15 | Minor | D-24, §8.2 | per-agent memory vs the jev-agent "run-local" invariant | accepted | D-28; README note (row 8); §11 rules read |
| r2-1 | R-16 | Blocker | D-20, §9.2, EC-85 | the zip catch list misses `ValueError`, `UnicodeDecodeError`, `OSError`, `LZMAError` | accepted | D-20 method check (`ZIP_STORED`/`ZIP_DEFLATED`) plus `ValueError` in the catch around `ZipFile(...)` and the read; EC-85, EC-115; AC-28; §9.2; row 16; §12.4; §11 facts |
| r2-2 | R-17 | Blocker | §8.5, rows 1, 2, 10, §8.4 | `step: str` types a closed set as a string | accepted | `SkillFetchStep` (5 members) in the skills enum module, exported from `vidbyte.lib.enums` only; §8.4 3 enums; §8.5; rows 1, 2, 10; §12.4 |
| r2-3 | R-18 | Minor | D-30, rows 15–16, INV-15 | the prefix check runs on the unstripped value | accepted | strip first, send the stripped value; INV-15, D-30, EC-77, AC-22, rows 15–16, §12.4 |
| r2-4 | R-19 | Minor | D-19/D-20, row 16, EC-79/80/83 | bare body uncapped; explicit-version 404 detail; `bool` version | accepted | D-20 and EC-83 cap → `TOO_LARGE`; EC-79 and §9.2 detail names the route; EC-80 rejects `bool`; AC-29; row 16 |
| r2-5 | R-20 | Minor | row 19, INV-10, AC-27, EC-95 | "never replace" breaks INV-10 when loads overlap | accepted | each load returns the remembered resolution where one exists (row 19, INV-10, D-24, EC-95, AC-27); no lock |
| r2-6 | R-21 | Minor | §8.4, row 15, D-22 | GitHub's single main cannot hold the whole flow within principle 1 | accepted (option 1) | D-31 private `_GitHubAnswer` status classifier; §8.4 12 package classes; §8.5; row 15; §12.4 |
| r2-7 | R-22 | Minor | EC-103, NFR-1 | the hang cost recurs on every run, not only the first | accepted | NFR-1 and EC-103 reworded; EC-116 (egress blocked) and EC-117 (`path=` hint); README note (row 8); §9.2 details |
| r2-8 | R-23 | Minor | §13, rows 10 and 22 | two test-contract facts unstated | accepted | row 22 plain class; row 10 reads the deadline at call time; §13; §14; §11 facts |

## §17 Revision history
| Revision | Date | Stage | Summary |
|---|---|---|---|
| r1 | 2026-10-12 | S1 spec | Initial spec |
| r2 | 2026-10-12 | S1 revision | Round-1 review (1 Blocker, 5 Major, 9 Minor): parse-exception catches (D-29), per-step deadline (D-27), loader-level grouping with one `resolve` main per resolver (D-22), GitHub Vidbyte-key guard (D-30), vendor dual handling, local labels without paths; R-8 → Q-6 (not built), R-9 → Q-7. Self-check: AC-1, AC-11, AC-20 mapped to W-10, W-1, W-9 (unmapped in r1) |
| r3 | 2026-10-12 | S1 revision (final) | Round-2 review (2 Blocker, 6 Minor), all accepted: zip method check and `ValueError` catch (D-20), `SkillFetchStep` enum, stripped-key guard (D-30), bare-body cap and vendor detail fixes, loads return the remembered resolution (INV-10), `_GitHubAnswer` classifier (D-31), every-run cost wording, test-contract facts; implementer facts in §11/§13/§14; status approved |
