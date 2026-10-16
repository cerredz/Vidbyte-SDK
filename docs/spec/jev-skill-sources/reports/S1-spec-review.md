VERDICT: SOUND WITH FIXES — The design fits the settled decisions and keeps every existing test green. One Blocker remains: third-party frontmatter can raise exceptions that the spec does not catch, which breaks fail-open, and the fix is a one-line widening of the catch. The Majors are corrections to the spec's contract, not redesigns.

## WHAT THE SPEC GETS RIGHT

- **Existing tests keep working.** D-8 keeps the preload's keyword constructor and lets `_build_batches` work before any run. It also builds the preload once in `JevAgent.__init__` while resolving lazily on the first `run()`. That matches how `tests/test_jev_skill_preload.py` calls `_build_batches("…")` with no run, monkeypatches `skill_preload.run` (an instance attribute, so the class must have no `__slots__`), and never constructs a `JevSkillResult` directly.
- **The entry hierarchy works as specified.** Probed on 3.11.0: the base has `type` with `init=False` and no default, and each subclass redeclares it with a default; `_validate_source()` is the hook. Field order is `name`, `type`, then the subclass fields, and positional construction works. `type=` and `text=` on `GitHubSkill` raise `TypeError`. `SkillEntry(name=…)` raises through the hook. The token stays out of `repr`, and entries pickle, hash and work as dict keys. Instances of different classes are never equal.
- **The failure maps are thorough (§9.2, §6.3).** It refuses redirects because httpx re-sends `x-api-key` across hosts (D-10). It never copies YAML error text, which can quote file lines (EC-29). It rejects one-segment names, including Windows drive-relative forms; the probe showed `PureWindowsPath(".agents/skills")/"C:x"` gives `C:x` (D-17).
- **Records, enums and constants go where AGENTS.md puts them**, and so do the exports. The constants module may import the reason enum, as `constants/codex.py`, `constants/jev.py` and `constants/cot_events.py` already do.

## FINDINGS

### R-1 [Blocker] [L5/L7] §9.2 "Expected exception classes", D-12, EC-29/EC-34, INV-9 — `yaml.safe_load` and `json.loads` raise exceptions outside their own error types, so a hostile or unlucky SKILL.md crashes every run

- **Evidence:** §9.2 catches only `yaml.YAMLError` in the parser. It lists `json.JSONDecodeError`/`ValueError` only "around decoding answers and files". INV-9 says that any exception not listed propagates out of `arun` as a programming error. Probes with PyYAML 6.0.2 on 3.11.0:
  - Frontmatter nested 500 levels deep (about 1 KB of `[`) raises `RecursionError`.
  - `description: 2024-13-45`, `name: 2024-02-30` and `!!timestamp 2024-01-01T25:00:00` each raise `ValueError` from the timestamp constructor. None of these is a `YAMLError`.
  - `json.loads` on deeply nested input raises `RecursionError`, not `JSONDecodeError`. That affects `skills-lock.json`, the GitHub tree listing, and vendor metadata.
- **Failure:** Any third-party skill (skills.sh, GitHub, vendor) whose frontmatter has an impossible date or deep nesting makes `JevAgent.arun` raise. Nothing is remembered when a resolve raises, so every later run fetches again and crashes again. One entry takes down the whole agent, the opposite of the settled fail-open decision. The same happens with a hand-edited `skills-lock.json` that nests too deeply.
- **Smallest fix:**
  - In `SkillMarkdown.parse`, wrap only the `yaml.safe_load` call in `except (yaml.YAMLError, ValueError, RecursionError)` and map it to `INVALID_SKILL` with the EC-29 detail.
  - Around the lock, tree and metadata `json.loads` calls, catch `RecursionError` beside `JSONDecodeError`/`ValueError`. A bad lock counts as absent (D-17); a bad tree or metadata response is `INVALID_SKILL`.
  - Add both classes to the §9.2 list, and add EC rows for "timestamp-like value" and "deeply nested frontmatter/JSON".

### R-2 [Major] [L5/L9] §7 NFR-1 vs EC-103, Q-2 and request.md §C — the "20.5 s per step / 61.5 s worst case" bound is false, and its retry never applies to timeouts

- **Evidence:**
  - NFR-1 (P0) promises 10 s per operation with 1 retry, "at most 20.5 s per step … 61.5 s worst case".
  - EC-103 accepts that a slow-drip upstream is unbounded, because the timeout is per network operation.
  - `HttpTransport.request` (`vidbyte/lib/http/transport.py:47-56`) retries only on `retry_status_codes` (408/409/425/429/5xx). `httpx.RequestError`, which includes every timeout and connection error, is re-raised immediately as `ProviderRequestError`, so `SKILL_FETCH_RETRY_COUNT` never applies to them.
  - request.md:155 lists timeouts and connection errors as the transient failures, and request.md:209 assumes "a hanging upstream adds up to timeout × attempts".
- **Failure:** The test author writes a P0 test for a bound that does not hold. The implementer assumes timeouts are retried when they are not, so a single connection blip reports `FETCH_FAILED` for that run. The spec contradicts itself (NFR-1 vs EC-103), and it silently breaks a request assumption without listing it as a correction.
- **Smallest fix:** Pick one of these.
  - (a) Reword NFR-1: "10 s per network operation; one retry, on 408/409/425/429/5xx only; timeouts and connection errors are not retried by the transport (they are transient, so the next run retries); no total bound (EC-103, Q-2)". Add a §15 note that request.md:209 is corrected.
  - (b) Answer Q-2 "yes" (not scope-adding: request.md:209 asks for a bound). Wrap each `SkillFetch.get` in `asyncio.timeout(SKILL_FETCH_TOTAL_SECONDS)`, following the precedent at `vidbyte/agents/multi/runner.py:51` and `harnesses/execution.py:210`, and map `TimeoutError` to `FETCH_FAILED`.

  Either way, NFR-1 must describe what the transport actually does.

### R-3 [Major] [L4] §8 D-22, §12.3 rows 9/15, §12.4 principle-1 checkbox — the spec exempts its own design from AGENTS.md principle 1

- **Evidence:**
  - D-22 has the base `resolve` gather `_resolve_one`, which then calls that subclass's own helpers. That is two levels of own-class calls, since the methods are inherited into one class.
  - §12.4 declares "the only sanctioned two-step is the base `resolve` fan-out". AGENTS.md principle 1 has no exception mechanism.
  - `GitHubSkillResolver` also overrides `resolve` (row 15) with grouping, commit lookup, tree listing and per-entry fetches. It becomes a second main whose helpers call helpers.
- **Failure:** House review or the `@claude` review flags both resolvers after implementation, and the fan-out has to be restructured late. The spec-level "sanction" carries no authority.
- **Smallest fix:** Move the fan-out up one layer, into the loader, a different class whose calls do not count against principle 1:
  - `SkillLoader.load` groups pending entries by `resolver.group_key(entry)`, which is `(repo, ref, token)` for GitHub and the entry itself everywhere else. It gathers one `resolver.resolve(group)` per group with `return_exceptions=True` and classifies against `BaseException`.
  - Each resolver then has one narrated main, `resolve(group)`, with flat helpers. GitHub needs no override and the base needs no generic fan-out.
  - D-22 and the §12.4 checkbox then cite no exception.

  This keeps every settled decision (plain entry array, lazy per-agent cache, fail-open).

### R-4 [Major] [L1/L7] §6.1 INV-15, EC-77, AC-12 — the Vidbyte-key guard omits GitHub

- **Evidence:**
  - The settled decision says the env fallback for `GITHUB_TOKEN`, `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` stays, "but a Vidbyte key is never sent to a vendor".
  - INV-15 reads "never sent to Anthropic or OpenAI". EC-77 and AC-12 cover only the vendor keys.
  - `GitHubSkill(token="vb_live_…")`, or a `GITHUB_TOKEN` holding one, is sent as a bearer token to api.github.com and raw.githubusercontent.com. `find_vidbyte_api_key` (`vidbyte/lib/registries/models.py`) already treats a `vb_live_` value in a provider variable as a managed key, so that misconfiguration exists in practice.
- **Failure:** A Vidbyte secret leaks to a third party, and GitHub's 401 response (EC-53) gives no hint why.
- **Smallest fix:**
  - Change INV-15 to "never sent to GitHub, Anthropic, or OpenAI".
  - Extend EC-77 to the `token` field and `GITHUB_TOKEN`: `AUTH_FAILED` with no request, using the same detail.
  - Add an AC row for the GitHub token, and use the same `VIDBYTE_API_KEY_PREFIX` check (C020).

### R-5 [Major] [L7] §10 T-4 — the env-key fallback gives tenant-supplied entries the operator's credentials, and T-4's control does not prevent it

- **Evidence:**
  - T-4's control is "keys are per entry or per process env".
  - With `GitHubSkill(repo="corp/private")` and no `token`, the resolver uses the process `GITHUB_TOKEN`. That is the operator's token, not the tenant's.
  - The same applies to `AnthropicSkill`/`OpenAISkill` and the process `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` (INV-1 confirms these are read at load).
  - The resolved text is appended to that tenant's agent instructions, where the tenant's own prompts can make the model repeat it.
- **Failure:** In a multi-tenant app that builds entries from user input, one tenant reads private repositories, or another org's vendor skills, through the host's credentials. §10 claims the threat is controlled when it is not.
- **Smallest fix (documentation only, within the settled fallback decision):**
  - Rewrite T-4's control: entries are trusted configuration, and the env fallback uses process credentials. Apps that build entries from untrusted input must pass an explicit `token=`/`api_key=` or unset the env variables.
  - Add one line to that effect in `vidbyte/agents/skills/README.md` (row 8) under its notes.

### R-6 [Major] [L10/L5] §15 A-1, A-2, A-4 — each vendor assumption handles only one outcome, and the failure branch is remembered with a misleading detail

- **Evidence:**
  - A-1 already concedes that the current Claude API notes say the Skills API is GA, that the beta header returns the old shapes, and that the notes "do not list the content route". The bundled claude-api reference lists only list/get/delete and version create/list/get/delete.
  - A-1's "if wrong" is "every `AnthropicSkill` reports `not_found`". Per §9.2, a 404 is remembered for the agent's lifetime with the detail "skill id and version".
  - A-2 hard-codes `latest_version`, while request.md recorded `latest_version_id`.
  - A-4 hard-codes "zip bytes".
- **Failure:** If A-1 is wrong, every Anthropic skill silently reports a permanent `NOT_FOUND` that tells the user to check their ID, so they debug the wrong thing. If A-2 is wrong, every `latest` entry fails. Each "if wrong" is a re-spec, not a handled outcome, and the real-key check that would decide them is still open.
- **Smallest fix (cheap dual handling, no new scope):**
  - (1) Read `latest_version`, falling back to `latest_version_id`.
  - (2) When the metadata GET returned 200 and the content route returns 404, use a distinct detail ("skill exists; the content route was not found"). Keep the reason `NOT_FOUND`.
  - (3) For A-4, treat a body starting with `---` (after an optional BOM) as a bare SKILL.md, otherwise as a zip.
  - (4) Mark A-1 and A-4 as items for the user's pending real-key QA, before S3 relies on them.

### R-7 [Minor] [L3/L10] §9.2 `DECISION_FAILED` — the detail text is unspecified for its most common cause

- **Evidence:** When `VIDBYTE_API_KEY` is missing or rejected, every batch raises `VidbyteSdkError` and every skill becomes `DECISION_FAILED`. The spec does not say what detail tells the developer which fix applies.
- **Failure:** The first-run experience for most new users is every skill unavailable with no actionable message.
- **Smallest fix:** Specify two detail texts: a failed batch ("Jev decision request failed: <error class>; check VIDBYTE_API_KEY"), and a batch that answered but left out this skill.

### R-8 [Minor] [L1] [scope-adding] §8 D-18, EC-73 — `GitHubSkill.path="."` for a repository-root SKILL.md was not discussed

- **Evidence:** D-18 introduces `"."` as the root marker and EC-73 tests it. request.md describes GitHub skills as folders inside a repository and never mentions a root SKILL.md.
- **Failure:** It adds behavior the user did not ask for (no-scope-additions rule).
- **Smallest fix:** Make it an optional Q-6: "Load a SKILL.md at the repository root via `path="."`?", default **not built**. With the default, `"."` is rejected at construction like any other path that is not a folder, and the limitation is documented in the README.

### R-9 [Minor] [L1] §6.3 EC-44, D-17 — "accepted per orchestrator decision" cites a decision that is not in the settled list

- **Evidence:** EC-44 accepts a skills.sh folder that is missing from an existing `skills-lock.json`. The settled list says only that skills.sh reads the installed copy plus the lock. request.md:227 lists "lock-file mismatch" as permanent, and a missing entry is arguably a mismatch.
- **Failure:** If a reviewer reads a missing entry as a mismatch, the behavior flips late in review.
- **Smallest fix:** Cite the user reply or request line that settles this. If none exists, make it a Q-n with today's behavior as the default.

### R-10 [Minor] [L7] §8 D-21, AC-4 — the `local:<absolute folder>` label leaks machine paths into Jev requests and results

- **Evidence:** D-21 builds the label from the `.absolute()` folder, for example `local:C:\Users\<os-user>\…`. The label is part of what the preload sends to Jev and is returned in `JevSkillResult.source`.
- **Failure:** The OS username and directory layout go to the managed gateway and into anything that logs results. INV-18 covers details but not labels.
- **Smallest fix:** Label local skills `local:<path as the caller wrote it>`, or `local:<name>`. Keep the absolute path internal for reading.

### R-11 [Minor] [L9] §12.6 — rows 5 and 6 are tagged P3 but missing from the phase lists and the dependency order

- **Evidence:** Rows 5 (`vidbyte/lib/dataclasses/__init__.py`) and 6 (`vidbyte/lib/__init__.py`) carry P3 in §12.3. P3 lists "rows 20–26", and the dependency chain never mentions 5 or 6.
- **Failure:** The implementer following §12.6 skips the public exports, and FR-15 fails at the end.
- **Smallest fix:** Change P3 to "rows 5, 6, 20–26" and add "row 4 → rows 5, 6" to the dependency order.

### R-12 [Minor] [L8/L11] §11 grounding, §12.3 — two pieces of repo context are missing

- **Evidence:** The spec never mentions `vidbyte/sources/`, the existing artifact fetch and cache layer (`fetches/http.py` HttpFetcher, `fetches/file.py`, `security.py` UrlAllowlist, `cache/memory.py`). `vidbyte/agents/README.md` "Key Modules" lists sibling packages, including `coding_context/`, but §12 has no row for adding `skills/`.
- **Failure:**
  - A reviewer asks why the spec builds a second fetch-and-cache path beside `vidbyte/sources/`, which touches AGENTS.md principle 5. That layer is a poor fit: it uses the sync `SyncHttpTransport`, which would block the event loop, its file reads are uncapped, and it raises on non-2xx. The spec should say so.
  - The agents README index goes stale.
- **Smallest fix:** Add one §11 sentence on why `vidbyte/sources/` is not reused. Add a §12.3 row that appends a `skills/` line to `vidbyte/agents/README.md` Key Modules, or record in §12.5 why not.

### R-13 [Minor] [L6] §7 NFR-4 — memory is capped per download but not in total, and the real peak is about 4× the cap

- **Evidence:**
  - NFR-4 caps each download at 32 MiB, and the loader resolves all entries concurrently.
  - `_send_bounded` (`transport.py:83-89`) builds a `bytearray`, then a `bytes` copy, and the response also decodes a replacement-character `str`. That is about three to four copies of the cap per in-flight download.
- **Failure:** With N vendor skills, the first run can transiently hold roughly N × 4 × 32 MiB. The NFR reads as a bound, but it is not one.
- **Smallest fix:** State the real per-download peak (about 4 × `SKILL_DOWNLOAD_MAX_BYTES`) and that there is no total bound, and accept that explicitly. A concurrency cap would be scope-adding, so leave it out.

### R-14 [Minor] [L9] §6.3 EC-95 — "the later write wins with an equal value" is not always true

- **Evidence:** EC-95 covers two concurrent first runs on one agent (D-24 allows this). A GitHub branch `ref` can move between the two commit lookups, giving different SHAs. A transient 404 can also race a success, and since a permanent 404 is remembered, the last writer's 404 can replace a success.
- **Failure:** The test author asserts equality that does not hold, and a remembered 404 can mask a skill that loaded.
- **Smallest fix:** Reword the outcome: "the later write wins; on a moving ref or a racing failure the remembered result may differ from the first run's". Alternatively, make the memory write only replace an entry that is not yet resolved.

### R-15 [Minor] [L8] §8 D-24 / §8.2 — the per-agent memory conflicts with the jev-agent skill's "Runtime state is run-local" invariant, and the spec does not say so

- **Evidence:** The Invariants section of `skills/jev-agent/SKILL.md` says: "Runtime state is run-local; reusable configuration is frozen and validated before execution". The settled decision caches resolved skills on the agent across runs. The spec cites neither the invariant nor an exception (Q-4 and NG-12 only discuss documenting the preload).
- **Failure:** Review applies the jev-agent skill to the change under `vidbyte/agents/jev/`, reads the loader memory as cross-run runtime state, and flags it.
- **Smallest fix (within the settled decision):** Add a D-row or §8.2 note. It should quote the invariant and say that the skill memory is resolved configuration, not run state. It is built from frozen entries, stays per agent (INV-6), and holds no run data. Record the same in the skills README notes.

## VERIFIED CLAIMS

- **Held:** The preload is built once in `JevAgent.__init__` from `settings.alignment.skills`, and is None when there are none (`vidbyte/agents/jev/agent.py:80-89`). `_runtime()` builds a new runtime on every call (`vidbyte/agents/base.py:1285`, called by `arun` at :1265), so per-agent memory must live on the preload or loader, not the runtime.
- **Held:** `fork` goes through `AgentForker` and builds a plain `BaseAgent`, so a fork never shares the preload or its memory.
- **Held:** `JevSkillsPreload.run` seeds UNAVAILABLE results, then `_build_batches`, then `gather(return_exceptions=True)`. It continues on `VidbyteSdkError` and re-raises any other `BaseException` (`vidbyte/agents/jev/alignment/skills.py`). The header already says "Keep source resolution outside this core contract".
- **Held:** `JevSkillResult(name, description, source, status, probability=None)` requires a non-blank description (`vidbyte/lib/dataclasses/jev.py:3727-3751`). Only the preload constructs it, and no test does, so the P3 invariant change is safe.
- **Held:** `JevAlignmentSettings._normalized_skills` (`vidbyte/agents/jev/settings.py:77-118`):
  - rejects str/bytes;
  - normalizes strings to `inline_skill_{n}` with source `inline`;
  - raises on non-SkillDocument values;
  - raises `ConfigurationError(details={"names": sorted})` on duplicate names.

  Existing tests assert all of this, and the spec keeps it.
- **Held:** The entry hierarchy behaves as described (see "What the spec gets right" above).
- **Partly refuted (R-2):** `HttpTransport.request` signature and defaults are as cited; retries happen only on status codes; `raw_bytes` is set only on the bounded path; an oversized body raises `ProviderRequestError(status_code=…)` (`transport.py:40-57, 83-92`). However, timeouts and connection errors are not retried, which refutes NFR-1's retry claim.
- **Held:** `HttpResponseParser.bearer_headers` is an instance method and adds `content-type: application/json`. `resolve_api_key` strips the key and raises `ConfigurationError("Missing API key…")`. DEFAULT_ENDPOINTS: anthropic `https://api.anthropic.com/v1`, openai `https://api.openai.com/v1`.
- **Held:** `VIDBYTE_API_KEY_PREFIX = "vb_live_"` at `vidbyte/lib/constants/jev.py:62`.
- **Held:** The A001 baseline is 643, and `--rule A001 --update-baseline` rewrites only that rule. An IMPROVED result does not fail. TID251 bans only `asyncio.Lock`, `TypedDict` and `assert_never`, so `asyncio.timeout` and `to_thread` are allowed.
- **Held:** The precedents exist: `RootFileLoader._enabled` and `_read_capped` with fstat (`vidbyte/agents/coding_context/root_file.py`), the empty `__init__` with `__all__: list[str] = []`, the README `## Notes for agents`, `to_thread` in `harnesses/stores/file.py`, and in-memory zip in `portable.py`. The `init=False` type-field pattern also exists at `vidbyte/lib/dataclasses/codex.py:450` (CodexSkillInput), but the spec does not cite it.
- **Held:** `CodingAgentSettings.root_dir` resolves the path and checks it exists, so it is only a partial precedent for `.absolute()` with no I/O (A-11).
- **Held:** There is no existing `vidbyte.agents.skills` module, so the name is free. REPO_MAP lacks `coding_context`, and its three-skills-locations warning is at :265 and :287-289. Nothing gates `llms.txt` or `artifacts/file_index.md`.
- **Refuted for edge inputs (R-1):** `yaml.safe_load` only raises `YAMLError`. It also raises `RecursionError` and `ValueError` (probed above). With duplicate YAML keys the last one wins, and date or bool values give non-str fields; the spec's non-blank-str check catches the latter.
- **Held:** On Windows, joining a drive-relative or UNC segment escapes the base: `PureWindowsPath("C:/proj/.agents/skills") / "\\\\server\\share"` gives `C:\server\share`. The D-17 one-segment rule is required.
