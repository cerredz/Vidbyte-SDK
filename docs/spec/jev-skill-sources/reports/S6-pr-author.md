# S6 PR author — jev-skill-sources

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-skill-sources`, branch `feat/jev-skill-sources`, started at `0cb790b5` (clean). PR https://github.com/cerredz/Vidbyte-SDK/pull/904. No source, test, `lint/`, or contract file was changed by this stage.

## What the code does (written from the diff, before reading the spec)

- **Entries.** `vidbyte/lib/dataclasses/skills.py` adds `SkillEntry` and six frozen, slotted subclasses: `InlineSkill(description, text)`, `LocalSkill(path)`, `SkillsShSkill(source, directory=".agents/skills")`, `GitHubSkill(repo, ref, path, token)`, `AnthropicSkill(skill_id, version="latest", api_key)`, and `OpenAISkill(...)` with the same fields. Each fixes a read-only `type` (`init=False`) and checks its own fields in `_validate_source`, which the base `__post_init__` calls after checking `name`. `LocalSkill.path` and `SkillsShSkill.directory` are pinned with `Path.absolute()`, which reads only the working folder name. Secrets are `repr=False`. `SkillResolution` holds a document, or a reason with a non-blank detail, and derives `transient`.
- **Settings.** `JevAlignmentSettings.skills` accepts entries, `SkillDocument`s, and strings in one tuple. Strings still become `inline_skill_<n>` documents, entries pass through unchanged, and names stay unique across all kinds.
- **Preload.** `JevSkillsPreload.__init__` builds one `SkillLoader` (no I/O). `run` calls `loader.load()` first. An entry with no document is seeded as `UNAVAILABLE` with the loader's reason and detail, and `description=None`, `source=None`. Loaded documents are batched as before. A loaded skill in no batch becomes `TOO_LARGE` (`_unbatched`); a batch whose Jev call raised `VidbyteSdkError`, or whose reply had no token counts, makes its skills `DECISION_FAILED` (`_failed_batch`); a missing answer is `DECISION_FAILED` (`_score_skill`). Selected texts come from the loader's documents.
- **Loader.** `SkillLoader.load` groups entries it has not remembered by `(entry.type, resolver.group_key(entry))`, runs one `resolve` per group with `asyncio.gather(..., return_exceptions=True)`, re-raises any exception before remembering anything, remembers non-transient resolutions with `setdefault`, and answers in settings order, preferring the remembered value. `SkillDocument` entries are remembered at construction.
- **Resolvers.**
  - Inline copies its fields (label `inline`).
  - Local reads `<path>/SKILL.md` in a worker thread with an `os.fstat`-capped read (1 MiB). No regular file is `NOT_FOUND` (remembered; the detail names the absolute path and says to create a new agent); any other `OSError` is `FETCH_FAILED`. Label `local:<folder name>`.
  - skills.sh reads `<directory>/<name>/SKILL.md` the same way (`NOT_INSTALLED` with the `npx skills add` command). In the default `<root>/.agents/skills` layout it reads `<root>/skills-lock.json`; any doubt about the lock means "absent", and a lock entry naming another source is `INVALID_SKILL`. Label `skills_sh:<source>/<name>[@<hash12>]`.
  - GitHub groups by `(repo, ref, token)`. It refuses a Vidbyte key or a token that is not printable ASCII before any request; looks up the commit SHA unless `ref` is a full SHA; lists the tree once only if some entry has no `path` (an unusable listing is `FETCH_FAILED`, a truncated one `INVALID_SKILL`); picks the shallowest `<name>/SKILL.md` (a tie is `INVALID_SKILL`); fetches every raw file at once. `_GitHubAnswer.failure` maps statuses (403 with rate-limit headers is `RATE_LIMITED`; 3xx is `NOT_FOUND` "moved"). Label `github:<owner>/<repo>@<sha12>/<folder>/SKILL.md`.
  - Anthropic and OpenAI share `VendorSkillResolver`: key from the entry or the provider variable via `ProviderModelRegistry.resolve_api_key`, the same two guards, a download of `/skills/{id}/versions/{v}/content`, and, when `latest` is refused with 400, 404, or 422, one read of the skill record (`latest_version`, else `latest_version_id`) and one download of that version. The body is a bare SKILL.md (starts with `---` after an optional BOM, capped) or a zip read in memory: exactly one SKILL.md (any case) at the root or one folder deep, not encrypted, stored or deflate only, declared size within the cap. Anthropic sends `x-api-key` with the version and beta headers; OpenAI uses `HttpResponseParser.bearer_headers`. Label `<vendor>:<skill_id>@<version>`.
- **Shared pieces.** `SkillFetch.get` is the one GET: `HttpTransport.request` with 10 s, 1 retry, 0.5 s backoff, a size cap, `follow_redirects=False`, inside `asyncio.timeout(25 s)`. Transport errors with no status are `FETCH_FAILED`; a 2xx over the cap is `TOO_LARGE`; the deadline is `FETCH_FAILED`; every HTTP answer goes back to the resolver. `SkillMarkdown.parse` decodes strict UTF-8 (one BOM removed), splits at `---` lines, reads YAML with `safe_load` (catching `YAMLError`, `ValueError`, `RecursionError`), requires non-blank `name` and `description`, and keeps the body exact; every failure is `INVALID_SKILL`.
- **Public surface.** Nine names reach `vidbyte`: `SkillEntry`, the six entries, `SkillSourceType`, `SkillUnavailableReason`. `SkillFetchStep` stops at `vidbyte.lib.enums`. The contract gains 9 names (615 exports). `lint/baseline.json` lowers A001 to 642.

Traced path: `JevAgent.arun` → `JevRuntime._arun_metered` (gate stop returns `response.stopped`; a specialist returns `_delegate`; neither reaches the preload) → `_preload_skills` → `JevSkillsPreload.run` → `SkillLoader.load` → resolvers → `SkillFetch.get` / `LocalSkillResolver.read_capped` → `SkillMarkdown.parse` → memory → batches → `DecisionModelHelper.arun` → `JevResponse.skills` → `_append_selected` → main loop.

## Snippet run

The §4 snippet as literally written needs real keys and network, so it was run under fakes only:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload/test_skill_sources_acceptance.py -q -p no:cacheprovider -rA` → `3 passed in 0.14s`. `test_developer_snippet_prints_the_documented_lines` asserts the five lines exactly.
- To see the printed lines, a scratch copy of that test and of `conftest.py` (in the session scratchpad, `s6accept/`, never in the worktree) printed the captured output through `capsys.disabled()`:

```text
--- snippet output (faked run) ---
house-review selected -
sql-migrations skipped -
react-best-practices unavailable not_installed
webapp-testing selected -
release-notes unavailable auth_failed
reply.content = completed
detail house-review | inline | None
detail sql-migrations | local:sql-migrations | None
detail react-best-practices | None | react-best-practices is not installed at C:\Users\422mi\AppData\Local\Temp\pytest-of-PC\pytest-1203\test_developer_snippet_prints_0\.agents\skills\react-best-practices: run `npx skills add vercel-labs/agent-skills --skill react-best-practices` in the project folder.
detail webapp-testing | github:anthropics/skills@0123456789ab/skills/webapp-testing/SKILL.md | None
detail release-notes | None | No API key for api.anthropic.com: pass api_key= on the entry or set ANTHROPIC_API_KEY.
```

The snippet runs as written (inside async code, because it uses top-level `await`); the only added line binds the offline main-model runner. AC-1 holds; no deviation.

## Deviations found (spec r5 against the code)

All are in the PR body's "Deviations from the spec":

1. `GITHUB_CREDENTIAL_ENV_VAR` instead of row 3's `GITHUB_TOKEN_ENV_VAR` (ruff S105 inside S054). S3 deviation 1.
2. The zip count check is a `match` with guarded cases (R-8, S024 depth). This supersedes S3 deviation 2: `SKILL_ARCHIVE_MARKDOWN_COUNT` no longer exists (`grep` finds it only under `docs/`).
3. `GitHubSkillResolver._raw_document` (one entry per call) instead of D-31/row 15's `_raw_documents`. S3 deviation 3.
4. `SkillText` helpers take `field_name`; R-5 added `require_version` and `require_folder`, beyond row 4's three helpers. S3 deviation 4 plus R-5.
5. `JevSkillsPreload._unbatched` and `_failed_batch`; a loaded skill is seeded with `_score_skill(index, document, {})`. S3 deviation 5 (and R-10).
6. Row 20 committed before rows 21–22; `tests/test_jev_skill_preload.py` is red at `5438110e` and `b4164134`. S3 deviation 6.
7. Only A001 lowered in the baseline. S3 deviation 7.
8. `SKILL_MARKDOWN_DELIMITER` (R-13) is a constant row 3 does not list.
9. R-RC1: a GitHub request with a token also sends `content-type: application/json` from `bearer_headers` (R-9); §9.2 (`spec.md` GitHub rows) lists only `accept` and `authorization`. §9.2 was not edited, as the briefing directs.

§5 drift: the r5 flowchart was correct but left out the gate method, `SkillFetch.get`, the credential guards, `_unbatched`, and `_failed_batch`. It is replaced with the PR's flowchart and noted in §17. The §5 sequence diagram and prose still match the code and are unchanged.

## Gate outputs (local, at `0cb790b5`, Windows, Python 3.11.0)

Outputs are saved in the session scratchpad under `s6gates/`.

| Gate | Command | Final lines |
|---|---|---|
| Feature tests | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` | `426 passed, 1 skipped in 4.47s` |
| Feature tests plus `tests/test_http_transport_content_type.py` (the briefing's 434) | same, with that file added | `434 passed, 1 skipped in 4.55s` |
| Lint (inside the source stage) | `PYTHONPATH=$(pwd) python lint/run.py` | `A001 ... 642 642 RATCHETED`; `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`; 0 `REGRESSED` |
| Source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | `====================== 4219 passed, 14 skipped in 35.28s ======================` / `CI passed.` |
| Package stage | `python scripts/run_ci.py --stage package` (no `PYTHONPATH`) | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Contract | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | `contracts/sdk-public-api.json is current at 3a4cb9292f62e40afa39478fdea5cf53fd758065 (vidbyte-sdk 0.2.1, 615 exports).` |
| Semgrep | rule test and scan (1.170.1, scratch `semgrep-venv`) | `1/1: ✓ All tests passed` / `Ran 1 rule on 905 files: 0 findings.` |

`git status --short` was empty after every gate.

Semgrep note: the first semgrep attempt failed with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` because the venv's `semgrep.exe` re-launched `pysemgrep` from the system Python, which has mcp 2.x. A Git Bash `PATH` entry written as `C:/...` is split at the drive colon; prepending the venv's `Scripts` folder with `cygpath -u` fixed it.

## Remote checks and PR state

Filled in after the push and the dispatch; see the section "Final PR state" below.

## Candidate field-guide lessons (not written to the field guide)

Shape: `## title` · When · Do · Because · Check · Evidence, as in `vidbyte-sdk/comment-format.md`.

### `blocking-lint-invariants.md`: C002 is satisfied by one owner, not by a different guard spelling
- **When:** C002 fires on a bool or type guard that two records repeat (for example `isinstance(self.version, bool)` in two entry classes).
- **Do:** Move the check into one helper on the existing static helper class of that dataclass module (here `SkillText.require_version(value, field_name)`) and call it from both records. Do not rewrite the guard as `type(x) is int`, which C002's matcher does not see.
- **Because:** The rule exists because "two independent inline copies of the same rule drift silently"; the reviewer caught the spelling change as a dodge (R-5), and the fix kept C002 at its baseline with one owner.
- **Check:** `python lint/run.py --rule C002` stays at the baseline, and `git grep -n "type(self\.[a-z_]*) is int" vidbyte/lib/dataclasses/` shows no copies.
- **Evidence:** PR #904, review R-5, fix `ca340b36`.

### `blocking-lint-invariants.md`: do not invent a constant only to quiet A007
- **When:** A007 flags a literal whose only valid value is fixed by the code's shape (for example "exactly one member" before `(member,) = members`).
- **Do:** Change the shape so no literal is needed: `match members: case [member] if ...: return ...; case [member]: ...; case _: ...`. Use guarded cases with a single return each, because a `match` inside `try` and `with` already sits at depth 3, and S024 allows no more.
- **Because:** A constant such as `SKILL_ARCHIVE_MARKDOWN_COUNT = 1` that breaks the unpack for any other value is a knob with no valid setting (R-8); the review's literal shape (`if`s inside `case [member]:`) would have raised S024 from 25.
- **Check:** `python lint/run.py --rule A007 --rule S024` stays at the baseline, and the new constant has no reader except one line.
- **Evidence:** PR #904, review R-8, fix `dde94f83`.

### `strict-config-dataclasses.md` or `blocking-lint-invariants.md`: a `*_TOKEN_*` constant name trips S054
- **When:** Naming a constant that holds an environment-variable name for a token, such as `GITHUB_TOKEN`.
- **Do:** Name it without `_TOKEN_` (here `GITHUB_CREDENTIAL_ENV_VAR = "GITHUB_TOKEN"`) and say why in a comment above it.
- **Because:** lint S054 runs ruff S105, which reads any `*_TOKEN_*` name bound to a string as a hard-coded password; renaming is the only fix without a suppression, and suppressions are not allowed.
- **Check:** `python lint/run.py --rule S054` passes.
- **Evidence:** PR #904, S3 deviation 1 (`vidbyte/lib/constants/skills.py`), accepted by the S4 review.

### `provider-api-contracts.md`: refuse a credential an HTTP header cannot carry before building the request
- **When:** Sending a user-supplied token or API key (entry field or environment variable) in a header through `HttpTransport`.
- **Do:** After stripping, refuse the value unless `value.isascii() and value.isprintable()`, and map it to the source's auth failure with no request. Never format the value into the message.
- **Because:** httpx raises `UnicodeEncodeError` in `build_request`, which is not an `httpx.RequestError`, so it escapes `HttpTransport`'s `ProviderRequestError` mapping and every catch around it; the exception repr carries `Bearer <token>`. An internal newline instead fails at send and looks like a network error retried forever (R-2). `httpx.InvalidURL` for an over-long URL escapes the same way (R-19).
- **Check:** A test that patches `httpx.AsyncClient.send` (not `_send_once`) so the real header encoding runs, with a curly quote in the token, ends in the auth failure with zero sends.
- **Evidence:** PR #904, review R-2, fix `556b84fc`, tests `f90b0680` (`test_unencodable_credential_is_auth_failed_through_real_header_encoding`).

### `provider-api-contracts.md`: on Python 3.12, deep JSON parses instead of raising `RecursionError`
- **When:** Reading a third-party JSON body whose items you then filter (a tree listing, a list of records).
- **Do:** Validate the shape of every item you rely on (`all(isinstance(item, dict) and isinstance(item.get("path"), str) ...)`) and treat a bad shape as the same failure as a parse error. Do not count on `RecursionError` to reject deep nesting.
- **Because:** Python 3.12's C JSON scanner no longer follows `sys.getrecursionlimit()`, so a 2,000-level body that raises on 3.11 parses on 3.12 into `[[[]]]`; filtering it silently gave "no match", which was remembered as `not_found`, and only the 3.12 CI job was red (R-1). Local runs are 3.11.
- **Check:** Include a row such as `{"tree": [[[]]]}` in the unusable-body tests so the rule is pinned on every Python version; dispatch `ci.yml` to see 3.12.
- **Evidence:** PR #904, review R-1, fix `879a4b16`.

### `strict-config-dataclasses.md`: a header recipe that adds a subclass must name every type it must also widen
- **When:** A module header's COMMON MODIFICATION PATTERNS or a folder README tells the next agent how to add a variant (a new vendor, source, or backend), and the base is generic over a constrained `TypeVar`.
- **Do:** List the `TypeVar` constraint in the recipe ("add the entry class to `VendorSkillT`, or mypy (S009) rejects the subclass"), and list the new exports in the package `__init__` PURPOSE.
- **Because:** Following the recipe as first written failed S009 (R-12); headers are what the next agent reads first.
- **Check:** Walk the recipe once against the code: every name the recipe touches exists, and every name a new variant must touch is in the recipe.
- **Evidence:** PR #904, review R-12, fix `472c7b1a`.

### `comment-format.md` (addition): wrap after every repair, and check only PR-added lines
- **When:** A repair pass edits or adds comments in files that already had wide pre-existing comments.
- **Do:** Re-wrap last, after every other fix, and check only the lines the PR added: `git diff -U0 origin/main...HEAD -- 'vidbyte/*.py'` filtered to added `#` lines over 72 columns.
- **Because:** The awk check over whole files reports pre-existing lines too (115 in `lib/dataclasses/jev.py`), which the guide says to leave alone; R-3 found 60 PR-authored lines over the limit after S3 had reported the checklist done.
- **Check:** The diff filter prints nothing.
- **Evidence:** PR #904, review R-3, fix `75c5f459`.

### `local-ci-verification.md` (addition): Semgrep from the scratch venv needs that venv first on `PATH`
- **When:** Running semgrep from a scratch venv on Windows with Git Bash.
- **Do:** `export PATH="$(cygpath -u <venv>/Scripts):$PATH"` before `semgrep`, and leave `PYTHONPATH` unset.
- **Because:** `semgrep.exe` re-launches `pysemgrep` from `PATH`; without the venv first it runs the system Python, whose mcp 2.x breaks semgrep's import. A `C:/...` entry in a Git Bash `PATH` is split at the colon.
- **Check:** `which pysemgrep` prints the venv path.
- **Evidence:** PR #904 S6 gate run.

## Things that looked odd while reading (no source change made)

None is a defect that needs a repair; listed so a reader does not rediscover them.

- `vidbyte/agents/skills/skills_sh.py:99-105` — Python's `json.loads` accepts `NaN` and `Infinity`, which JavaScript's `JSON.parse` (used by npx skills) rejects. A lock with `"version": NaN` passes the version check (`NaN < 1` is false), so its source check applies where npx skills would treat the lock as absent. The difference only ever refuses a source mismatch, the safer direction.
- `vidbyte/agents/skills/vendor.py:209` — a zip directory entry named `skill.md/` counts as a SKILL.md member, because `PurePosixPath` drops the trailing slash. The worst case is `INVALID_SKILL` (two members, or an empty body that fails the parser).
- `vidbyte/agents/skills/vendor.py:91-100` — if a skill record names `"latest"` as its own latest version, the resolver downloads `latest` a second time and the detail reads like an explicit-version miss. Harmless.
- `vidbyte/agents/jev/alignment/skills.py:91` — the seed detail "Jev answered this batch …" before Jev is asked is review R-10, already a follow-up.
- The branch is 3 commits behind `origin/main` (#910, #911, #912: evals and sessions only). `git merge-tree --write-tree HEAD origin/main` is clean. Catching up is the orchestrator's call (merge, never rebase).

## Final PR state

(Filled in below after the push and the CI dispatch.)
