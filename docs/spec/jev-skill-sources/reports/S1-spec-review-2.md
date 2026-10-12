VERDICT: SOUND WITH FIXES — All 15 round-1 findings landed as §16 claims, and none of the r2 restructures (loader-level grouping, step deadline, parse catches, GitHub key guard) breaks a settled decision or an existing test. Two Blockers remain, and both are mechanical spec edits: the zip read still lets corrupt archives crash every run (the R-1 failure class on a path D-29 did not reach), and `SkillFetch.get(step: str)` types a closed set as a string, against AGENTS.md.

## WHAT THE SPEC GETS RIGHT

- **The R-3 restructure works as designed, and it is not an empty layer.** I ran a faithful probe through mypy 2.3.1 with the repo's own `lint/mypy.ini` (which sets `disallow_any_generics`). The probe covered `SkillResolver(ABC, Generic[SkillEntryT])`, `VendorSkillResolver(SkillResolver[VendorSkillT])` with `VendorSkillT` constrained to the two vendor entries, the two concrete vendor subclasses, and a `dict[SkillSourceType, SkillResolver[Any]]` dispatch. It reported 0 errors. At run time, grouping by `(type, group_key)` produced `[a] [b,c] [d] [e] [f]`: GitHub entries share a group only when repo, ref and token all match, and every other type gets a group of one. The base has six implementations and one hook override, so it does real work rather than just passing calls through.
- **The step deadline (D-27) is correct on the repo's Python.**
  - On 3.11.0, `asyncio.timeout.__aexit__` turns only its own expiry into `TimeoutError`, and only when `uncancel() == 0`. A caller's own cancellation therefore propagates, which keeps INV-9.
  - The deadline maps to `FETCH_FAILED`, which is transient and never remembered (§9.2).
  - NFR-1's "3 sequential steps × 25 s" matches both chains: GitHub runs commit, tree, raw; the vendors run content, metadata, content.
  - No r2 signature has a parameter named `timeout`, so S045 (ASYNC109) does not fire, and no new code has a retry loop of its own, so S064 does not apply.
- **D-29's catch sets are complete for YAML and JSON.** Each probe below raised an error that `(yaml.YAMLError, ValueError, RecursionError)` or `(ValueError, RecursionError)` caught:
  - impossible timestamps;
  - `!!int abc` and `!!float abc`;
  - a 5,000-digit integer (the 3.11 digit limit raises `ValueError`);
  - unhashable keys and bad merge keys (`ConstructorError`);
  - deep nesting in YAML and in JSON.
- **The round-1 cleanup is complete.**
  - Nothing is left of `GITHUB_ROOT_PATH`, the `path="."` behavior, `local:<absolute folder>`, or the "sanctioned two-step"; `_resolve_one` appears only as D-22's rejected runner-up and in the §16 log.
  - §12.3 has exactly 14 CREATE rows (3 and 7–19), matching §8.4.
  - Rows 5 and 6 are in P3 and in the dependency order.
  - Row 30's target, the `coding_context/` line under `## Key Modules`, exists in `vidbyte/agents/README.md`.

## FINDINGS

R-16 [Blocker] [L5/L7] §8.1 D-20, §9.2 "Expected exception classes", §6.3 EC-85 — Corrupt vendor archives still crash every run: the zip catch list misses exception types the stdlib raises
  Evidence:
  - D-20 and §9.2 say to "catch `BadZipFile`, `zlib.error`, `EOFError`, `NotImplementedError` around the zip read only".
  - EC-85 promises that a "corrupt or truncated archive, a bad CRC, an unsupported compression method" becomes `invalid_skill`.
  - INV-9 says any exception not listed in §9.2 propagates out of `arun`.
  - Probes on Python 3.11.0 (`-I`, in a scratch directory):
    - a corrupt BZIP2 `SKILL.md` member raises `OSError: Invalid data stream`;
    - a corrupt LZMA member raises `_lzma.LZMAError`;
    - a member name with the UTF-8 flag set and invalid bytes raises `UnicodeDecodeError` from `ZipFile(...)` itself;
    - in 40,000 ordinary STORED/DEFLATED two-member archives with 1–6 random byte flips, 598 raised `ValueError: negative seek value …`, 24 raised `UnicodeDecodeError`, and 1 raised `OSError`. None of these is in the four-class list.
  Failure: Take an `AnthropicSkill` or `OpenAISkill` whose served archive is corrupt in any of these ways. `arun` raises on every run, because nothing is remembered when a resolve raises. One entry takes the whole agent down. That breaks the settled fail-open decision, and it makes EC-85 false as written. This is the same failure R-1 was rated a Blocker for; D-29 fixed it for YAML and JSON but not for the zip read.
  Smallest fix: Change D-20, row 16, §9.2 and EC-85 as follows.
  - (a) Read the `SKILL.md` member only if its `compress_type` is `ZIP_STORED` or `ZIP_DEFLATED`. Any other method is `INVALID_SKILL`, checked beside the encrypted-flag check.
  - (b) Wrap the `ZipFile(...)` construction and the member read in `except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, ValueError)`. `ValueError` also covers `UnicodeDecodeError`.

  I verified this: 60,000 mutated STORED, DEFLATED, BZIP2 and LZMA archives gave zero escapes. An equivalent without (a) catches `(…, ValueError, OSError, lzma.LZMAError)`; that also gave zero escapes over 60,000 cases. Also extend the D-29 line in §12.4 to cover the zip read.

R-17 [Blocker] [L4] §8.5 `SkillFetch.get`, §12.3 rows 1 and 10, §8.4 — `step: str` types a closed set as a plain string, which AGENTS.md forbids
  Evidence:
  - §8.5 declares `async def get(self, *, url: str, headers: Mapping[str, str], max_bytes: int, step: str)`.
  - r2's deadline row in §9.2 and D-27 require details to name "the host, the step, and the deadline".
  - Exactly five values exist: GitHub commit lookup, tree listing, and raw file; vendor content download and metadata.
  - AGENTS.md Placement Rules (binding, and enforced on every PR) say: "Any field, parameter, or registry key whose value comes from a small, closed set is typed with an enum from this folder, not a plain `str`."
  Failure: An implementer who builds §8.5 as written writes `step: str`. The placement workflow or a reviewer flags it. Meanwhile the five call sites, spread over three resolver modules, can drift in how they spell the step names that users read in details.
  Smallest fix:
  - Add `SkillFetchStep(str, Enum)` with five members to `vidbyte/lib/enums/skills.py` (row 1). List it in that module's `__all__` and in `vidbyte/lib/enums/__init__.py` (row 2), but not among the nine root exports.
  - Type the parameter as `step: SkillFetchStep` in §8.5 and row 10.
  - Change §8.4 from 2 enums to 3.

  This changes no behavior.

R-18 [Minor] [L7] §8.1 D-30, §12.3 rows 15–16, INV-15 — The Vidbyte-key check runs on the unstripped value, so a key with leading whitespace gets past it
  Evidence:
  - Row 15 says: "token = entry token, else `os.environ.get(GITHUB_TOKEN_ENV_VAR)` (blank = none; a token starting with `VIDBYTE_API_KEY_PREFIX` → `AUTH_FAILED`)".
  - Row 16 uses "key (entry, else `ProviderModelRegistry.resolve_api_key` …; `startswith(VIDBYTE_API_KEY_PREFIX)` → `AUTH_FAILED`)". §9.1 keeps the `token` and `api_key` fields exactly as given.
  - Probe: `" vb_live_abc".startswith("vb_live_")` is False. httpx then sends `authorization: 'Bearer  vb_live_abc'`, and h11 accepts that header on the wire.
  - The repo's precedent strips the value before checking: `resolve_api_key` and `find_vidbyte_api_key` (`vidbyte/lib/registries/models.py:162-190`).
  Failure: `GITHUB_TOKEN=" vb_live_…"`, `GitHubSkill(token=" vb_live_…")` or `OpenAISkill(api_key=" vb_live_…")` sends the Vidbyte key to GitHub or OpenAI. That breaks INV-15 (P0) and NFR-5's claim that it holds "for every path in §6.3".
  Smallest fix: In D-30 and rows 15–16, strip the entry value and the environment value before the prefix check, and send the stripped value, as `resolve_api_key` does. Add the padded case to EC-77.

R-19 [Minor] [L3/L9] §8.1 D-19/D-20, §12.3 row 16, §6.3 EC-79/EC-80/EC-83/EC-87 — Three loose ends in the R-6 fix
  Evidence:
  - (1) INV-12 says "No `SKILL.md` larger than `SKILL_MARKDOWN_MAX_BYTES` is loaded". The bare-`SKILL.md` branch that r2 added (D-20, row 16, EC-83) has no size check. EC-87's declared-size check covers zip members only, and the vendor download cap is `SKILL_DOWNLOAD_MAX_BYTES` (32 MiB).
  - (2) R-6's separate "content route not found" detail covers only the `latest` fallback. With an explicit `version`, if A-1 is wrong, a 404 is still remembered as `NOT_FOUND` with the "skill id and version" detail (EC-79). That is the misleading detail R-6 was meant to remove.
  - (3) EC-80 accepts an integer version from the skill record. JSON `true` decodes to `True`, which is a Python `int`, so the download goes to `/versions/True/content`.
  Failure:
  - (1) A 5 MB bare body is parsed and held in memory, then reported `TOO_LARGE` with the Jev-limit detail rather than the cap detail. A test author's INV-12 test on the bare path fails against an implementer who follows row 16.
  - (2) Users with pinned versions debug their skill id when the route is the problem.
  - (3) One wasted request, then a confusing `not_found`.
  Smallest fix:
  - (1) In D-20, row 16 and EC-83: a bare body over `SKILL_MARKDOWN_MAX_BYTES` is `TOO_LARGE` and remembered.
  - (2) In EC-79 and §9.2: the explicit-version 404 detail also names the content route as a possible cause (A-1).
  - (3) In EC-80: a `bool` is not an integer version.

R-20 [Minor] [L9/L5] §12.3 row 19, INV-10, AC-27, EC-95 — "Never replace" (the R-14 fix) makes INV-10 false when two loads overlap, and the preload then reports the wrong reason
  Evidence:
  - Row 19 says to remember resolutions "only for entries not yet remembered (never replace); return one resolution per entry in order".
  - INV-10 says "`SkillLoader.documents()[i]` is `r[i].document` for every index `i`".
  - Row 22 seeds results from `r`, batches from `loader.documents()`, then "mark[s] loaded-but-unbatched as `TOO_LARGE`".
  Failure: Two first runs overlap (EC-95; AC-27 tests this). Run A remembers a permanent 404 for an entry, while run B resolved the same entry to a document. B's `load()` returns B's document, but `documents()` holds None. B's preload therefore marks a loaded skill `TOO_LARGE`, which is the wrong reason. In the reverse race, B seeds a load failure, and then Jev judges, and may select, A's document.
  Smallest fix: In row 19, after writing, return for each entry the remembered resolution if one exists, and this load's own resolution otherwise. INV-10 then holds even when loads overlap.

R-21 [Minor] [L8/L2] §8.4, §12.3 row 15, D-22 — r2 dropped r1's allowance for a GitHub helper class, yet GitHub's single `resolve` main now carries the whole group flow
  Evidence:
  - r1's §8.4 allowed "at most one private per-group helper class in the `github` module if the one-level rule needs it". r2's §8.4 lists exactly 11 package classes, and going over budget means reporting BLOCKED.
  - Row 15's one main must:
    - choose the token and check its prefix;
    - do the commit lookup and the tree listing;
    - locate each entry's folder (shallowest wins; a tie, a truncated tree, or no match each have their own outcome);
    - run the raw fetches concurrently, then parse;
    - apply a shared step's failure only to the entries that needed that step (INV-8).
  - It must also classify the status after three different fetches, including the 403 rate-limit header logic.
  - Under principle 1, a step leaf such as `_commit_sha`, `_tree_paths` or `_raw_document` cannot call a shared `_status_failure` leaf. Under NFR-7 (about 50 lines) and S024 (nesting ≤ 3), the main cannot inline all of that either.
  Failure: The implementer reports BLOCKED on the budget, or writes a 70–100-line main or two-level calls. That draws the same convention comment R-3 was meant to remove.
  Smallest fix: Do one of two things:
  - restore r1's allowance (one private GitHub status or step helper class, taking §8.4 to 12 classes); or
  - spell out row 15's shape: the main calls `_status_failure(answer, step)` right after each `SkillFetch.get`, the step leaves accept only 2xx answers, and NFR-7 allows about 60 lines for this one main.

R-22 [Minor] [L5] §6.3 EC-103, §7 NFR-1 — The hang cost recurs on every run while a source stays unreachable, not only on the first run
  Evidence: EC-103 says "a first run slower by at most one deadline per step", and NFR-1 is titled "Bounded first-run cost per step". But `FETCH_FAILED` is transient and never remembered (INV-5), so every run that reaches the preload retries it (AC-20).
  Failure:
  - On a production host whose egress to api.github.com or a vendor is silently dropped, every run pays the 10 s connect timeout (up to the 25 s deadline per step), with no end, for every pending remote entry.
  - On a slow link, a large monorepo's tree listing that keeps hitting the deadline never loads. Its detail names the host, step and deadline but never suggests `path=`, which skips the tree step.
  Smallest fix (inside the settled retry policy): Reword EC-103 and NFR-1 to "per run that retries a pending entry". Add the egress-blocked case to the package README notes (row 8). Make the tree-listing timeout and deadline detail suggest `path=`.

R-23 [Minor] [L10] §13, §12.3 rows 10 and 22 — Two test-contract facts are not stated where the implementer will read them
  Evidence:
  - `tests/test_jev_skill_preload.py:415-424` assigns `agent.skill_preload.run = preload` on the instance. §13 mentions only the one-argument `_build_batches` call and `preload.decision.model`.
  - §13 says tests shorten the deadline by patching `vidbyte.agents.skills.fetch.SKILL_FETCH_DEADLINE_SECONDS`, but row 10 does not require reading that name when the call runs.
  Failure:
  - An implementer applying principle 4 ("prefer `@dataclass(frozen=True, slots=True)`") to `JevSkillsPreload` breaks that existing test (AC-16).
  - An implementer who binds the deadline as a default argument or a `ClassVar` makes the patch useless, so AC-24's test waits the full 25 s or fails.
  Smallest fix:
  - Row 22: "`JevSkillsPreload` stays a plain class (no `__slots__`, not frozen), because the existing test patches `run` on the instance".
  - Row 10: "refer to `SKILL_FETCH_DEADLINE_SECONDS` by its imported module name when the call runs".

## VERIFIED CLAIMS

**Round-1 dispositions, checked against r2's text and the repo**

- **R-1: resolved for YAML and JSON, but the same class of failure is still open on the zip read (R-16).** The fix appears in D-29, EC-109 to EC-112, AC-23, the §9.2 list, rows 11, 14, 15 and 16, and the §12.4 line. Each catch sits around one parse call, not around `Exception`. My probes are listed above; every one was caught.
- **R-2: resolved; one wording issue remains (R-22).**
  - NFR-1 now matches `vidbyte/lib/http/transport.py:47-56`: retries happen only on `retry_status_codes` (408/409/425/429/500/502/503/504), and an `httpx.RequestError` is raised immediately as `ProviderRequestError`.
  - The deadline is transient and unremembered (§9.2).
  - A-12 corrects request.md correctly.
  - Q-2 is struck through with a reason.
- **R-3: resolved.** The mypy probe passes, and grouping is correct. Keeping GitHub's main within principle 1 is tight (R-21).
- **R-4: resolved, and consistent everywhere it appears:** INV-15, EC-77, D-30, AC-22, the last row of the §9.2 table, row 15, and §12.4. The stripping gap is R-18.
- **R-5: resolved** (T-4(b), EC-114, row 8). Row 8 leaves out T-4's "or unset those variables", which is trivial.
- **R-6: resolved, with loose ends (R-19).**
  - D-19 reads `latest_version`, then `latest_version_id`.
  - It gives a separate detail when the content route answers 404.
  - D-20 handles a bare `SKILL.md`.
  - A-1 and A-4 are marked for the user's real-key QA.
  - AC-25 and AC-26 exist.
  - `SKILL_VENDOR_LATEST_VERSION_FIELDS` is spelled the same in row 3 and A-2.
- **R-7: resolved.** There are four detail texts in §9.2, and row 22, AC-14 and EC-105 agree with them.
- **R-8: resolved.** `"."` is rejected in §9.1, EC-49 and D-18. EC-73 is a documented limitation, with Q-6 and NG-13. `GITHUB_ROOT_PATH` appears nowhere.
- **R-9: resolved** (D-17 and EC-44 cite S1's own choice; Q-7 defaults to accept).
- **R-10: resolved** (`local:<folder name>` in D-21, INV-18, AC-4 and row 13).
- **R-11: resolved** (P3 lists rows 5 and 6, and the dependency order runs row 4 → rows 5, 6).
- **R-12: resolved** (§11 "Considered and not reused"; row 30 checked against `vidbyte/agents/README.md` `## Key Modules`).
- **R-13: resolved** (NFR-4, EC-113).
- **R-14: resolved as worded, but introduces R-20.**
- **R-15: resolved.** D-28 quotes `skills/jev-agent/SKILL.md:109` word for word.

**Repo claims**

- **Held:**
  - `HttpTransport.request` keeps one `httpx.AsyncClient(follow_redirects=…)` per call.
  - `_send_bounded` raises `ProviderRequestError(status_code=<status>)` when the body exceeds the cap, for any status, and sets `raw_bytes` only on this bounded path (`transport.py:79-95`).
  - 403 is not in the default retry codes.
- **Held:** `asyncio.timeout` precedents exist at `vidbyte/agents/multi/runner.py:51` and `vidbyte/harnesses/execution.py:210`. The harness precedent also checks `deadline.expired()` before treating a `TimeoutError` as its own, a refinement `SkillFetch` may copy.
- **Held:** On local 3.11.0, `Timeout.__aexit__` converts only on `uncancel() == 0`. Each `SkillFetch.get` runs inside a task that `gather` created (one per group, one per raw fetch), so cancel counts stay isolated per task. anyio is 4.14.1 locally.
- **Held:** S045 is ruff ASYNC109, which flags async parameters named `timeout`. S064 flags only loops that retry and sleep with no deadline. No r2 signature triggers either rule.
- **Held:** The mypy settings are `python_version = 3.11`, `disallow_any_generics`, and `check_untyped_defs`, and the probe's design passes cleanly under them.
- **Held:**
  - The existing tests pass `SkillDocument` tuples to `_preloader`.
  - They call `_build_batches("…")` before any run.
  - They patch `agent.skill_preload.run` on the instance.
  - The settings tests use `assertRaises(ConfigurationError)` without matching the message, so row 21's new error messages are safe.
  - No test constructs `JevSkillResult`.
  - The only code that constructs it in `vidbyte/` is `alignment/skills.py`.
- **Held:** The fresh-continuation factory builds a plain `BaseAgent` with no skills, so no second loader exists per agent (`vidbyte/agents/jev/agent.py:62-76`).
- **Held:** `resolve_api_key` strips both the explicit key and the environment value; `find_vidbyte_api_key` strips before calling `startswith`. This is the basis for R-18.
- **Held:**
  - REPO_MAP has its `vidbyte/agents/settings/` entry at :99 and the three-locations warnings at :265 and :289.
  - `CodexSkillInput` uses `field(default=..., init=False)` at `vidbyte/lib/dataclasses/codex.py:455`.
  - `vidbyte/agents/coding_context/__init__.py` has `__all__: list[str] = []`.
  - TID251 bans `asyncio.Lock`.
  - `HttpResponseParser` is exported from `vidbyte.lib.http`.
  - No lint rule, script or workflow gates `llms.txt` or `artifacts/file_index.md`.
- **Held:** These baselines match §11: A001 643, A002 703, A006 34, A007 255, S009 350, S024 25, S045 2, S047 0, S061 6, S063 4, S064 4, C016 0, S011 0, S012 0. C020 is 2.
- **Held:** C020 scans production literals only. Its header says "tests are out of scope", so tests for AC-12 and AC-22 may spell `vb_live_`, but production detail strings must build the prefix from `VIDBYTE_API_KEY_PREFIX`.
- **Held:** A002 matches only names and attribute names, split on `_` and `.`. Referencing `SkillUnavailableReason.FETCH_FAILED` counts as "fetch", so rows 13–16 correctly cite A002. The rows for inline, anthropic and openai need no `@intent`.
- **Held:** On 3.11.0, calling `super().__post_init__()` in a slotted dataclass subclass raises `TypeError`, which justifies D-3's hook. `object.__setattr__(self, "path", Path(p).absolute())` works in a frozen slotted subclass, and the result still hashes by value.
- **Note for the implementer:** `HTTPStatus(529)` raises `ValueError` (EC-82 lists 529). Look up D-11's status maps with the integer (`status in reasons`), as `vidbyte/lib/http/vidbyte_gateway.py:98-106` does; never call `HTTPStatus(response.status_code)`.
- **Refuted (R-16):** D-20's claim that "each zip failure is a verified stdlib mode". The four-class list is incomplete.
