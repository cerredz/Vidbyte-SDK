LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the memory policy, failure classification, archive handling, and secret guards hold up under fuzzing and mutation testing, but a credential that is not ASCII crashes every JevAgent run, and the skills.sh resolver's cap and read-error guards can be deleted while the test pack stays green.

Reviewed: `git diff origin/main...97c67062` (S3_HEAD), full files for every changed module under `vidbyte/`, the whole test pack in `tests/features/jev_skills_preload/`, and `vidbyte/lib/http/transport.py`. Every probe ran from the scratchpad with `PYTHONPATH=<worktree>`. All network access was blocked by patching `httpx.AsyncClient.send`, or the HTTP fake in `conftest.py` answered it.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Memory and crash handling are correct.**
  - `SkillLoader.load` (`vidbyte/agents/skills/loader.py:57-73`) writes memory in exactly one place, after every group has returned.
  - A crash or a cancellation re-raises before anything is remembered.
  - `setdefault` makes the first remembered value win, and every load returns the remembered value. This satisfies INV-5 and INV-10.
  - The mutants `remember-transient`, `crash-remembers-siblings`, `loader-replaces-memory`, and `loader-returns-fresh` are all killed by the tests.
- **The vendor archive reader holds against fuzzing.** `vendor.py:_skill_markdown` checks the compression method, the encrypted flag, and the declared size before reading, and catches the D-20 exception list. My fuzz of 40,000 mutated stored, deflated, bzip2, and lzma archives produced 0 escaping exceptions.
- **Every credentialed path is guarded.**
  - The value is stripped first, then checked for `VIDBYTE_API_KEY_PREFIX`, and the stripped value is the one sent. This holds for the GitHub entry token, `GITHUB_TOKEN`, the vendor `api_key=`, and the vendor environment variables.
  - Secret fields are declared with `repr=False`.
  - Details never echo a response body.
  - Every request goes to a fixed host with `follow_redirects=False`.
- **The step deadline is implemented correctly.**
  - `SKILL_FETCH_DEADLINE_SECONDS` is read when the call runs (`fetch.py:51`).
  - A `TimeoutError` is classified as the step's own only when `deadline.expired()` is true (`fetch.py:67-72`).
  - The test pack is strong overall: 40 of 45 valid mutants were killed (see VERIFIED CLAIMS).

FINDINGS (ranked, most severe first, max 15)

R-E1 [Major] [failure-modes / INV-9] vidbyte/agents/skills/github.py:130-135,108 and vidbyte/agents/skills/vendor.py:111-122,84 — A token or API key that is not ASCII escapes the loader as `UnicodeEncodeError` and fails every run of the agent
  Evidence:
  - httpx encodes header values as ASCII inside `client.build_request` (`vidbyte/lib/http/transport.py:66`).
  - The transport catches only `httpx.RequestError` (`transport.py:55`), and `SkillFetch.get` catches only `ProviderRequestError` and `TimeoutError` (`fetch.py:64,67`).
  - Neither `_token` nor `_key` checks the value before it becomes a header.
  - Probe `probe_agent_nonascii.py` (scratchpad; a `JevAgent` with a `GitHubSkill` on a full-SHA ref plus an `InlineSkill`; `GITHUB_TOKEN="“ghp_0123456789abcdef”"`) printed:
    ```
    run 1: AgentExecutionError caused by UnicodeEncodeError: 'ascii' codec can't encode character '“' in position 7: ordinal not in range(128)
    run 2: AgentExecutionError caused by UnicodeEncodeError: 'ascii' codec can't encode character '“' in position 7: ordinal not in range(128)
    main model calls: 0 | remembered documents: (None, None)
    ```
  - Probe `probe_nonascii.py` showed the same at `SkillLoader.load`, both for that `GITHUB_TOKEN` and for `OpenAISkill(api_key="sk-café")`: `RAISED UnicodeEncodeError`.
  Failure:
  - Input: a credential pasted with curly quotes, an accented character, or a zero-width character (`str.strip()` removes none of these). The state is any agent that has a GitHub or vendor entry; the repository may even be public, so no token is needed at all.
  - Wrong outcome: every `arun` raises `AgentExecutionError`, the main model never runs, and nothing is remembered, not even the healthy inline sibling. This is fail-closed for the whole agent, which inverts G-2 and the fail-open rule.
  - Side effect: the exception chained as `__cause__` carries the full `Bearer <token>` header value in `UnicodeEncodeError.object`. The token is also in the `headers` locals of the frames, which error trackers that capture frame locals or exception attributes would record. This is INV-14 adjacent.
  - The test pack cannot see this failure, because the conftest fake replaces `_send_once` as a whole, including `build_request` (`conftest.py:100,269`).
  Smallest fix:
  - In `GitHubSkillResolver._token`'s caller (`resolve`, before line 108) and in `VendorSkillResolver._key` (after line 117), return `AUTH_FAILED` with no request when the stripped value is `not value.isascii() or not value.isprintable()`. Remember it like a missing key, and write a detail that names `GITHUB_TOKEN`/`token=` or `api_key=`/the variable, never the value.
  - Add one test that patches `httpx.AsyncClient.send`, not `_send_once`, so that the real `build_request` runs.
  Spec IDs: INV-9, G-2, FR-14, INV-14, EC-77/EC-78 (credential failure family); request.md §D "handing the edge cases/failure modes of each skill … all throughout the implementation"

R-E2 [Major] [test-quality] vidbyte/agents/skills/skills_sh.py:49-51,55-56,60-63 — Three of the skills.sh resolver's failure guards can be removed or broken while all 374 cases stay green; removing the cap check would silently load a truncated SKILL.md
  Evidence: `mutate.py` runs against a scratch copy of the package, with the test pack run from a scratch copy of `tests/`:
  ```
  skillssh-too-large-removed: SURVIVED | 373 passed, 1 skipped   (cap check at :55 replaced by `if False:`)
  skillssh-cap-off-by-one:    SURVIVED | 373 passed, 1 skipped   (`>` -> `>=` at :55)
  skillssh-oserror-remembered: SURVIVED | 373 passed, 1 skipped  (OSError at :50 mapped to NOT_INSTALLED)
  lock-oserror-propagates:    SURVIVED | 373 passed, 1 skipped   (`except OSError` at :62 -> `except KeyError`)
  ```
  For comparison, the same mutations in `local.py` are killed: `local-cap-off-by-one: KILLED`, `local-oserror-remembered: KILLED`.
  Failure: each of these is a plausible regression that no test would catch.
  - (a) Without the cap check, a 1.5 MiB installed `SKILL.md` is read to the 1 MiB cap by `read_capped`, parsed, and loaded cut short. That breaks INV-12 and INV-22 ("never cut short").
  - (b) A `PermissionError` on an installed `SKILL.md` is remembered as `not_installed` for the agent's lifetime, when it should be `fetch_failed` and read again next run.
  - (c) A `PermissionError` on `skills-lock.json` propagates, and every run fails (INV-9).
  Smallest fix:
  - Add these cases to `test_skill_sources_skills_sh.py`:
    - an installed `SKILL.md` of exactly `SKILL_MARKDOWN_MAX_BYTES`, which loads;
    - one of cap + 1, which is `TOO_LARGE` and remembered;
    - `read_capped` patched to raise `PermissionError` for `SKILL.md`, which is `FETCH_FAILED` and read again on the next load;
    - `read_capped` patched to raise `PermissionError` only for the lock path, where the skill loads without the source check.
  - Also add a `" ---"` (leading space) row to the markdown malformed table. The mutant `markdown-strip-delimiter` (`rstrip` -> `strip` at `markdown.py:71`) also survived.
  Spec IDs: §9.2 "Local and skills.sh mapping" (OSError → FETCH_FAILED; size above cap → TOO_LARGE), EC-43 ("unreadable" lock is absent), INV-9, INV-12, INV-22, EC-25

R-E3 [Minor] [security] vidbyte/agents/skills/github.py:145, vidbyte/agents/skills/vendor.py:126,130,181-182 — `quote(..., safe="")` leaves `.` and `..` unencoded and httpx removes dot segments, so a `ref`, `skill_id`, or `version` of `.` or `..` sends the credential to a different endpoint on the same host
  Evidence: probe `probe_dot_segments.py`, with httpx's real `build_request` running and `send` patched:
  ```
  SENT https://api.github.com/repos/acme/skills                 (GitHubSkill ref="..")
  SENT https://api.anthropic.com/v1/versions/1/content          (AnthropicSkill skill_id="..")
  SENT https://api.openai.com/v1/skills/skill_x/content         (OpenAISkill version="..")
  ```
  Failure:
  - `OpenAISkill(skill_id="skill_x", version="..")` requests the skill's default-content route. It can load a version the entry never named, and labels it `openai:skill_x@..`.
  - `GitHubSkill(ref="..")` hits the repository endpoint. On the real API that likely answers 200 with JSON that is not a SHA, which gives `fetch_failed` on every run, forever.
  - A vendor record that names `latest_version: ".."` would be followed the same way.
  - The host never changes, so no key leaves its own host. That is why this is Minor.
  - The conftest fake compares raw URL strings, so no test can observe the normalization.
  Smallest fix:
  - Reject values in `SKILL_PATH_SPECIAL_SEGMENTS` for `GitHubSkill.ref`, `AnthropicSkill/OpenAISkill.skill_id`, and `.version` in `_validate_source`.
  - In `_record_version`, treat such a record version as `INVALID_SKILL`.
  Spec IDs: D-19 ("the id and version are each one encoded path segment"), EC-60, EC-93, §9.2 URL table

R-E4 [Minor] [scale / security] vidbyte/agents/skills/markdown.py:85 (called on the event loop from local.py:65, skills_sh.py:74, github.py:209, vendor.py:109) — `yaml.safe_load` on up to 1 MiB of third-party frontmatter runs on the event loop thread; a hostile SKILL.md stalls the host app for seconds
  Evidence: scratchpad timing with `SkillMarkdown.parse`:
  - 990,044-byte flow-list frontmatter `k: [a, a, …]`: 4.29 s, and the skill loads.
  - 1,000,015 bytes of plain `kNNN: value` keys: 0.98 s.
  - Both ran on the calling thread. D-23 moved only disk reads off the loop.
  Failure:
  - A T-2 hostile skill author publishes a `SKILL.md` with about 1 MiB of flow-list frontmatter on GitHub, skills.sh, or a vendor workspace.
  - The first run of every agent that lists it blocks the whole event loop for about 4 s per such skill, stalling every other coroutine in the process.
  - Apps that build a JevAgent per request pay this cost on every request, because memory is per agent (NG-7).
  Smallest fix:
  - Call `SkillMarkdown.parse` through `asyncio.to_thread` in the four resolvers. The loop then stays responsive between GIL switches.
  - A frontmatter byte bound would also work, but it is a new limit and so `[scope-adding]`.
  Spec IDs: T-2, D-23

R-E5 [Minor] [observability] [scope-adding] vidbyte/agents/skills/loader.py:57-73 — No log line or metric records a load failure, so an operator cannot see why runs got slow
  Evidence: the package has no `logging` import (`grep -n "logging" vidbyte/agents/skills/*.py` finds nothing). Failures surface only in `agent.response.skills.results[i].reason/detail`.
  Failure:
  - A host whose egress to GitHub or a vendor is blocked pays up to 3 sequential 25 s steps (75 s) on every run (EC-116).
  - Nothing in the application's logs says this, unless the app inspects each response's skill results.
  Smallest fix: follow-up for the user, not for the repair loop. Add one `logger.warning` per transient resolution, naming the entry name, reason, and step (never the detail's credential context).
  Spec IDs: n/a (EC-116 accepted the latency; logging was never agreed)

VERIFIED CLAIMS:
- **S3: "373 passed, 1 skipped".** HELD: my run gave `373 passed, 1 skipped in 4.12s`. The skip is the expected Windows `skill.md` row.
- **S3: tests untouched since `d01e0afa`.** HELD: `git diff d01e0afa..97c67062 -- tests/ | wc -l` gave `0`.
- **S3: "no `HTTPStatus(` call, no `vb_live_`, no subprocess, no `asyncio.Lock`, no `TypedDict`, no `extractall`, no `# noqa` / `# type: ignore`".** HELD: the grep of the added lines under `vidbyte/` hits only comments and docstrings.
- **S3: contract current.** HELD: `generate-sdk-public-api.py --check` reports current at `3a4cb929`, 615 exports.
- **S3: `JevSkillsPreload.run` is 47 lines and `vendor.py` (213 lines) is the largest new file.** HELD.
- **AC-16: the existing 20 tests pass unchanged.** HELD: 20 passed, and the file has no diff.
- **Spec EC-115 / D-20: zero escapes from the zip reader.** HELD: 40,000 mutated archives gave `ESCAPES {}`.
- **Spec D-27 / R-23: the deadline is read at call time and only an expired deadline is classified.** HELD: the code is at `fetch.py:51,67-72`; the mutants `deadline-at-import` and `deadline-swallows-any-timeout` are KILLED.
- **Spec INV-5 / AC-10, INV-10 / AC-27.** HELD: the mutants `remember-transient`, `loader-replaces-memory`, and `loader-returns-fresh` are KILLED.
- **Briefing: the Windows dot-only name is not a traversal.** HELD: `SkillsShSkill(name="...")`, with `<dir>/SKILL.md` present, gives `NOT_INSTALLED`, and `"...."`, `"a."`, and `"x "` behave the same.
- **Test plan: EC-16–EC-22 "`PermissionError` covers the OSError → FETCH_FAILED mapping".** HELD for local, NOT HELD for skills.sh (R-E2).
- **Spec INV-9: "loading never raises for an expected source failure".** NOT HELD for credentials that are not ASCII (R-E1).
- **Spec D-19 / EC-93: "percent-encoded as one segment".** NOT HELD for `.` and `..` (R-E3).
- **Three or more plausible bugs, tested by mutation (45 valid mutants: 40 killed, 5 survived).**
  - Byte-cap off-by-one: caught for local, GitHub raw, and the vendor bare file and archive; missed for skills.sh.
  - A transient failure remembered: caught for the loader, GitHub 403 rate limit, vendor 429, a commit answer that is not a SHA, a tree that is not JSON, and a local OSError; missed for a skills.sh OSError.
  - The key or token not stripped before the prefix check: caught (`gh-token-unstripped`, plus the padded vendor rows).
  - A `latest` fallback that reads only `latest_version`: caught.
  - A token on the wrong host: caught by the `sent_to` mapping in `test_secrets_never_leave_their_own_request_header`.
  - Results out of order: caught (the grouping test asserts names in settings order).
  - Also killed: `group-key-drops-token`, `fallback-on-any-failure`, `zip-no-method-check`, `zip-no-valueerror`, `zip-declared-size-unchecked`, `encrypted-unchecked`, `zip-depth-unbounded`, `tree-truncated-ignored`, `search-deepest`, `raw-uses-ref-not-sha`, `lock-check-skipped`, `lock-version-unchecked`, `lock-cap-ignored`, `yaml-no-valueerror`, `vendor-guard-removed`, `vendor-missing-key-transient`, `inline-label`, `bare-body-no-bom-strip`.
  - One mutant was discarded as invalid because it raised a `NameError`.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider -rs` → `373 passed, 1 skipped in 4.12s`
- `PYTHONPATH=$(pwd) python -m pytest tests/test_jev_skill_preload.py -q -p no:cacheprovider` → `20 passed in 0.85s`
- `git diff d01e0afa..97c67062 -- tests/ | wc -l` → `0`
- `git diff origin/main...97c67062 -- vidbyte | grep "^+" | grep -nE "HTTPStatus\(|vb_live_|subprocess|asyncio\.Lock|TypedDict|extractall|except Exception|except BaseException|# noqa|type: ignore"` → only comment and docstring lines (195, 365, 416, 605, 942, 1051, 1187)
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 3a4cb929… (vidbyte-sdk 0.2.1, 615 exports).`
- `python -I probe_httpx.py` (scratchpad) → `…/versions/../content -> …/skills/abc/content`; `header raised (UnicodeEncodeError, UnicodeError, ValueError)`; httpx `0.28.1`
- `PYTHONPATH=<wt> python probe_nonascii.py` → `GITHUB_TOKEN env with smart quote -> RAISED UnicodeEncodeError …`; `OpenAISkill api_key with accent -> RAISED UnicodeEncodeError …`
- `PYTHONPATH=<wt> python probe_agent_nonascii.py` → `run 1: AgentExecutionError caused by UnicodeEncodeError …`; `run 2: …same…`; `main model calls: 0 | remembered documents: (None, None)`
- `PYTHONPATH=<wt> python probe_dot_segments.py` → the three `SENT` lines quoted in R-E3
- `PYTHONPATH=<wt> python fuzz_zip.py 7 40000` → `outcomes {'invalid_skill': 37256, 'doc': 2569, 'too_large': 175}`; `ESCAPES {}`
- `PYTHONPATH=<wt> python probe_paths_yaml.py` → `'...' -> NOT_INSTALLED None` (and the same for `....`, `a.`, `x `); `1 MiB frontmatter … parse took 0.98s`
- Inline timing (`SkillMarkdown.parse`, hostile shapes) → `flow list of 1-char items: 990044 bytes, 4.29s, reason=None`
- `python -I mutate.py` (scratch copy of `vidbyte/` + `tests/` + `pyproject.toml`; the worktree is untouched) → 39 mutants, 37 KILLED, `skillssh-cap-off-by-one` and `skillssh-oserror-remembered` SURVIVED
- `python -I mutate.py skillssh-too-large-removed lock-oserror-propagates lock-cap-ignored markdown-strip-delimiter vendor-missing-key-transient gh-vidbyte-guard-env-only inline-label` → SURVIVED: `skillssh-too-large-removed`, `lock-oserror-propagates`, `markdown-strip-delimiter`; the rest KILLED (`gh-vidbyte-guard-env-only` was invalid: it raised a NameError)
- `git status --short` → only the other two S4 reviewers' untracked reports; this review wrote nothing to the worktree except this file
