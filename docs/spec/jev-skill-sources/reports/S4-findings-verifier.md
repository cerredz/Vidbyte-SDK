# S4 findings verifier — jev-skill-sources

Inputs: the three S4 reviews (conformance, conventions, engineering), the orchestrator's remote CI result on `8eb304cc`, spec r4, test-plan, request.md, code-map, AGENTS.md, field guide `vidbyte-sdk/`, house-style. Diff `origin/main...97c67062` (54 files, +8,132/−87). Output: `docs/spec/jev-skill-sources/review.md`.

Worktree state, before and after: `git status --short` shows only the three untracked S4 review reports, plus the two files this stage writes (`review.md` and this report). Every probe ran from `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4d43667e-6c86-4da6-8d31-a29ffd6bcc34/scratchpad/s4-verify/` with `PYTHONDONTWRITEBYTECODE=1`, and the network was blocked: `httpx.AsyncClient.send` or `HttpTransport._send_once` was stubbed. Mutants and fix trials ran on scratch copies, which were deleted afterwards.

Baseline: `PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` → `373 passed, 1 skipped in 4.16s`. Versions: Python 3.11.0, httpx 0.28.1, PyYAML 6.0.2. `py -0` lists 3.13 and 3.11 but no 3.12.

## Merge map

| Original | Lens | Proposed | Merged | Final |
|---|---|---|---|---|
| CI `Source / Python 3.12` failure | orchestrator | — | R-1 | Blocker, CONFIRMED |
| R-C1 | conformance | Major | R-2 | Blocker (raised), CONFIRMED |
| R-E1 | engineering | Major | R-2 (same root cause: credential → header → `build_request`) | — |
| R-V1 | conventions | Blocker | R-3 | Blocker, CONFIRMED |
| R-C2 | conformance | Major | R-4 | Major, CONFIRMED |
| R-V2 | conventions | Major | R-5 | Major, CONFIRMED |
| R-E2 | engineering | Major | R-6 | Major, CONFIRMED (test-gap) |
| R-C3 | conformance | Minor | R-7 | Minor; proposed fix refuted, replaced |
| R-V3 | conventions | Minor | R-8 | Minor, trivial |
| R-V4 | conventions | Minor | R-9 | Minor, trivial |
| R-V5 | conventions | Minor | R-10 | Minor, follow-up |
| R-V6 | conventions | Minor | R-11 | Minor, follow-up |
| R-V7 | conventions | Minor | R-12 | Minor, trivial (enums part refuted) |
| R-V8 | conventions | Minor | R-13 | Minor, trivial |
| R-V9 | conventions | Minor | R-14 | Minor, trivial (spec-text) |
| R-V10 | conventions | Minor | R-15 | Minor, follow-up |
| R-E3 | engineering | Minor | R-16 | Minor, follow-up |
| R-E4 | engineering | Minor | R-17 | Minor, follow-up |
| R-E5 | engineering | Minor [scope-adding] | R-18 | Minor, not built |
| — | verifier | — | R-19 | Minor, follow-up |

Counts: 3 Blockers, 3 Majors, and 13 Minors are confirmed. No Blocker or Major was refuted or downgraded. Two Minor sub-claims were refuted (R-V7's enums part, and R-C3's proposed fix). One tier moved up (R-C1/R-E1 → Blocker).

## Verifications

### R-1 (CI, Blocker) — GitHub tree items that are not objects end NOT_FOUND, remembered

- **Code:** `github.py:168-177` parses the listing. It returns `FETCH_FAILED` only when the body is not JSON, raises `ValueError` or `RecursionError`, or has no `tree` list (line 173). Otherwise line 177 keeps only the items that are dicts with `type == "blob"` and a text `path`, and drops everything else silently. Empty paths then reach `_search` (line 188), which returns `NOT_FOUND`, a permanent reason that the loader remembers.
- **Mechanism, own evidence:**
  - `python -c json.loads(<test body>)` on 3.11.0 raises `2000-deep tree body: RecursionError`.
  - `py -3.13 -I -c json.loads(<test body>)` returns `3.13.1 PARSED; tree item type: list ; recursionlimit 1000`. The Python recursion limit is unchanged, so the C scanner no longer counts against it.
  - CI shows the same parse on 3.12 (`NOT_FOUND is FETCH_FAILED` assertion).
- **Reproduction of the 3.12 path on 3.11:** `probe_ci312.py` stubs `_send_once` and feeds the already-parsed shape:
  ```
  3.12 path (what json.loads returns there: a tree list whose item is a list):
    tree='{"sha": "x", "tree": [[[]]]}'
      load1: SkillUnavailableReason.NOT_FOUND | No pdf/SKILL.md folder in acme/skills@aaaaaaaaaaaa; pass path= with the skill's folder.
      load2: SkillUnavailableReason.NOT_FOUND | requests load1=2 load2=0
  ```
  `[1, "a", null]` and `[{"type": "blob"}]` give the same result. The real 2,000-deep body on 3.11 gives `FETCH_FAILED`, and load 2 sends again.
- **Spec reading:**
  - EC-68 says "tree listing body is not JSON or lacks a `tree` list → `fetch_failed`".
  - §9.2 says "200 with an unexpected body (… a tree that is not JSON or nests too deeply …) → FETCH_FAILED, not remembered".
  - NFR-8 says 3.11 and 3.12.
  - A listing whose items are not tree entries is an unexpected body. Making it `NOT_FOUND`, remembered for the agent's lifetime, turns a network or proxy fault into a permanent miss.
- **Other deep rows are portable:**
  - skills-lock `{"version": 1, "skills": [[…]]}`: `skills` is not a dict, so the lock is absent either way.
  - vendor `{"latest_version": [[…]]}`: the value is a list, so `INVALID_SKILL` either way. That is why CI failed only this row.
- **Fix trial (`try_fixes.py`, scratch copy):** extended line 173 with `or not all(isinstance(item, dict) and isinstance(item.get("path"), str) for item in tree)`.
  - The pack gave `353 passed, 1 skipped`.
  - The probe gave `FETCH_FAILED` for all four shapes, and load 2 re-sent 2 requests.
  - Every test tree (`tree_body`, acceptance, fetch) uses dict items with text paths (grep), so no row breaks.

### R-2 (R-C1 + R-E1, Blocker) — a credential httpx cannot encode crashes every run

- **Code path:**
  - github.py:104 `_token` strips the token. Line 105 checks only the Vidbyte prefix, and line 108 builds `{"authorization": f"Bearer {token}"}`.
  - vendor.py:117 `resolve_api_key` strips the key. Line 120 checks only the prefix, and line 84 `_headers(key)` builds the header.
  - transport.py:66 `client.build_request(...)` sits outside both `try` blocks in `_send_once` and `_send_bounded`. `HttpTransport.request` catches only `httpx.RequestError` (line 55), and `SkillFetch.get` catches only `ProviderRequestError` and the deadline's `TimeoutError`.
  - The entry records validate `token` and `api_key` as non-blank text only (dataclasses/skills.py:178, 201, 219).
- **Own probe (`probe_nonascii.py`, real `build_request`, `send` stubbed to raise `ConnectError`):**
  ```
  control ASCII entry token: SkillUnavailableReason.FETCH_FAILED sent=1
  entry token with U+2019: RAISED UnicodeEncodeError: 'ascii' codec can't encode character '\u2019' in position 14: ordinal not in range(128) | sent=0
  GITHUB_TOKEN env with e-acute: RAISED UnicodeEncodeError: … '\xe9' in position 11 … | sent=0
  AnthropicSkill api_key with ZWSP: RAISED UnicodeEncodeError: … '\u200b' in position 7 … | sent=0
  OPENAI_API_KEY env with en-dash: RAISED UnicodeEncodeError: … '\u2013' in position 10 … | sent=0
  loader load 1: RAISED UnicodeEncodeError; documents()=(None, None)
    'SECRETTOKEN1234' in repr(exc): True; in str(exc): False
  loader load 2: RAISED UnicodeEncodeError; documents()=(None, None)
  agent run 1: AgentExecutionError caused by UnicodeEncodeError
  agent run 2: AgentExecutionError caused by UnicodeEncodeError
  main model calls: 0
  ```
- **Existing guard?** None. The prefix guards check one property only. No record, transport, or fetch layer checks that a header value can be encoded.
- **Adjudication, scope:** This is not scope-adding.
  - INV-9 sends "programming errors (any exception not listed in §9.2)" to `arun`. The spec's own examples of that class are SDK bugs: EC-97 is a resolver `TypeError`, and EC-9 is an unsupported subclass.
  - A token the user typed, or the deployment's env var, is user input. That makes it an expected failure under FR-14 ("every expected failure becomes `UNAVAILABLE` with a reason and a detail that names the fix"), G-2, and request.md §C "Fail-open at run time".
  - The fix adds no field, knob, or reason. It extends the existing pre-request credential check (§9.2's "missing key; key or token with `VIDBYTE_API_KEY_PREFIX` → `AUTH_FAILED`, no request" row) to one more property of the same value.
  - The spec's silence is a gap, as conformance said, not a decision. It needs one §6.3 EC row for traceability, so the fix type includes spec-text.
- **Adjudication, severity:** both reviewers proposed Major. I raised it to Blocker under step 4:
  - The result is broken for the whole agent, not one skill: every `arun` raises, the main model never runs, and nothing is remembered, so the crash repeats.
  - It violates the user's weighted words ("handing the edge cases/failure modes of each skill … all throughout the implementation") for three of the six source types.
  - The full `Bearer <token>` sits in `UnicodeEncodeError.object` and therefore in the repr of the chained `__cause__`, against G-4 "Secrets never leak". Conformance explicitly invited this weighing.
- **Fix trial (`try_fixes.py`):**
  - In github.py, before line 108, insert `if token is not None and not (token.isascii() and token.isprintable()): return (AUTH_FAILED,) * len(entries)`, with a detail naming `token=`/`GITHUB_TOKEN`.
  - In vendor.py `_key`, before the prefix check, insert `if not (key.isascii() and key.isprintable()): return AUTH_FAILED`, with a detail naming `api_key=`/the env var.
  - Result: the four cases end `AUTH_FAILED sent=0`, the loader returns, the main model runs (2 calls), and the pack gives `353 passed, 1 skipped`.
  - The `UsageAccountingError` that followed in the agent probe is an artifact of my runner stand-in. An inline-only agent on the unmodified tree raises the same error with no credential involved.
- **Why `isprintable()`:** h11 refuses an internal newline in a header value. `h11.Request(..., headers=[("authorization", "Bearer a\nb")])` → `LocalProtocolError`. httpx maps that to `httpx.LocalProtocolError`, which is an `httpx.RequestError` (verified with `issubclass` → `True`). So today such a token ends `FETCH_FAILED` "could not reach host" and is retried forever. It does not crash, but the reason is wrong. The same check gives it the right reason at no extra cost.
- **Test routing:** no existing test exercises `build_request`, because the `conftest.py` fake replaces `_send_once` as a whole. A regression test with the existing fake still fails before the fix: the old code sends a request, and the fake answers or asserts. So per source, assert `AUTH_FAILED`, `fake_http.sent == []`, and the value absent from the detail. Optionally, patch `httpx.AsyncClient.send` in one row, so the real header encoding is pinned. Fix type: source + test-gap + spec-text.

### R-3 (R-V1, Blocker) — 60 PR-authored comment lines over 72 columns

- **Field-guide entry:** it exists. `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/comment-format.md` is listed in `init.md` as "Read before writing or editing any multi-line `#` comment".
  - Rule: "Wrap every comment line at 72 columns, counting the indent … A single-line comment that would pass 72 columns becomes a wrapped block too."
  - Evidence it cites: the owner's PR #690 comment r4239871810.
  - Scope: "Not a lint rule … leave untouched files alone", so only PR-authored lines count. It applies to SDK code, and spec §12.4 lists it.
- **Own count with the entry's quick check:**
  - `awk 'length($0) > 72' <file> | grep -cE '^\s*#'` over the 13 new modules gives 50.
  - Per file: vendor 13, fetch 8, github 8, markdown 6, loader 4, local 4, skills_sh 4, anthropic 1, resolver 1, constants/skills 1, and `__init__`, inline, openai 0.
- **Python character count over the added lines of `git diff origin/main...97c67062 -U0 -- vidbyte/`:** 60 lines in total.
  - The 50 above, plus `jev/alignment/skills.py` 6, `lib/dataclasses/jev.py` 2, `jev/settings.py` 1, and `lib/dataclasses/skills.py` 1.
  - Worst: alignment/skills.py:67 (140), settings.py:90 (99), resolver.py:29 (88), dataclasses/skills.py:119 (77), vendor.py:191 (76).
  - This matches the reviewer's 53 + 9 once the 2 pre-existing lines are removed.
- **Severity:** step 4 lists "contradicts … a field-guide lesson" as a Blocker. The lesson is the owner's own review comment, so this review comment will recur.
- **A002 interaction checked:** `lint/rules/a002_intent_comments.py:79-81` looks for the marker in `[def − 4, def + 20)`. Every `@intent` in the new modules and in alignment/skills.py is on line `def + 1`. Wrapping a block only adds lines below the marker, so the window is safe.

### R-4 (R-C2, Major) — EC-24 detail missing

- **Spec:** EC-24's "User sees" cell says "`not_found`, detail says to create a new agent after fixing".
- **Code:** local.py:58 says "No SKILL.md file at {skill_file}; point path= at the folder that holds it."
- **Probe (`probe_misc.py`):** load 1 gives `not_found`. After the file is created, load 2 gives `not_found`, and "mentions a new agent: False".
- **Severity:** a spec-mandated user-facing text is missing. It is Major, not Blocker, because there is no wrong status and no crash.
- **Wording:** the package is agent-agnostic (spec row 7, D-2), so the added sentence should say "agent", not "JevAgent".

### R-5 (R-V2, Major) — duplicated validation, hidden from C002

- **Duplication:** `diff <(sed -n 195,201p … | sed 's/AnthropicSkill/X/g') <(sed -n 213,219p … | sed 's/OpenAISkill/X/g')` prints nothing (IDENTICAL). The folder guard at :134-138 and :154-156 has the same shape.
- **C002 matching:** I called the rule's `_bool_guard_identity` on parsed snippets:
  - `isinstance(self.version, bool)` → `'version'`
  - `type(self.version) is int` → `None`
  - `type(version) is bool` → `None`
  - `isinstance(value, bool)` → `'value'`, which is in `_GENERIC_IDENTITIES`
- **Current lint:** `lint/run.py --rule C002` gives `RATCHETED: 9 known finding(s)`, with baseline `"C002": 9`.
- **S3's own words:** S3-implementer.md:160 records the change as the C002 fix.
- **Adjudication:** `type(x) is int` is itself a fine expression, so the defect is not the syntax. The defect is that the rule C002 found duplicated still has two owners. The strict-config-dataclasses lesson ("Two independent inline copies of the same rule drift silently") applies.
- **Severity:** Major, not Blocker:
  - Both copies sit inside their own records' validation hooks. The lesson's literal case is a raw parameter checked outside its owning dataclass.
  - No behavior is wrong today.
  - Nothing was suppressed, and no baseline was raised.
- **Fix:** `SkillText` is the spec's named shared validation owner (§8.4), so adding two static methods there keeps the class budget.

### R-6 (R-E2, Major, test-gap) — skills.sh guards that tests cannot catch

My own mutation run (`mutate.py`) copies `vidbyte/`, the pack, `tests/__init__.py`, `tests/agent_test_support.py`, and `pyproject.toml` into a fresh scratch tree per mutant:

```
baseline                       BASELINE | 353 passed, 1 skipped in 4.07s
skillssh-too-large-removed     SURVIVED | 353 passed, 1 skipped in 4.14s
skillssh-cap-off-by-one        SURVIVED | 353 passed, 1 skipped in 4.11s
skillssh-oserror-remembered    SURVIVED | 353 passed, 1 skipped in 4.03s
lock-oserror-propagates        SURVIVED | 353 passed, 1 skipped in 4.08s
markdown-strip-delimiter       SURVIVED | 353 passed, 1 skipped in 4.11s
local-cap-off-by-one           KILLED | 1 failed, 153 passed, 1 skipped in 1.51s
local-oserror-remembered       KILLED | 1 failed, 152 passed, 1 skipped in 1.50s
```

- **Spec coverage:** §9.2's "Local and skills.sh mapping" row specifies both the cap and the `OSError` mapping for skills.sh, and EC-43 specifies "unreadable" locks. The test plan claimed the `PermissionError` coverage for local only.
- **Severity:** Major. This is a real gap a reviewer would raise, under the user's request to handle failure modes "all throughout the implementation". It is not a test that cannot fail: the tests are simply missing.
- **Routing:** test author, not the repair agent.

### Minors (pass-through, de-duplicated, with my checks)

- **R-7 (R-C3):** `probe_misc.py` prints `str(Path('')) = '.'`, `Path('') == Path('.'): True`, `LocalSkill(path=WindowsPath('.')) accepted`, and `SkillsShSkill(directory=Path('')) accepted`, while `LocalSkill(path='')` is rejected.
  - The reviewer's first fix (check the raw value) cannot work, because the value is already `Path('.')` when the dataclass sees it.
  - The finding stays Minor, with a documentation fix. Rejecting `"."` would be a behavior change nobody asked for.
- **R-8 (R-V3):** confirmed by reading vendor.py:201-203 and :209.
- **R-9 (R-V4):** `HttpResponseParser().bearer_headers("tok")` returns `{'authorization': 'Bearer tok', 'content-type': 'application/json'}`. No GitHub test asserts the full header dict: it reads only `.get("accept")` and `.get("authorization")`, at github tests :83, :87, :282, :298, :300. The swap is safe.
- **R-10 (R-V5):** confirmed at alignment/skills.py:84-91.
- **R-11 (R-V6):** confirmed by reading. I kept the reviewer's Minor tier, even though AGENTS.md principle 4 says "names the field and the bad value". Spec INV-2 (approved) pins the message contract as class plus field, INV-14 and EC-48 forbid echoing secrets, and `SkillDocument`, kept byte-for-byte, follows the same grain. The value type in `details` is the safe follow-up.
- **R-12 (R-V7):**
  - jev/__init__.py:3 PURPOSE was checked, and it omits the entries and enums.
  - vendor.py:52 `TypeVar("VendorSkillT", AnthropicSkill, OpenAISkill)` is constrained. The README "Adding a source" steps 1-6 and vendor.py:7 never mention widening it.
  - The enums/skills.py:8 part is refuted, because request.md §C states the "saved settings" reason.
- **R-13 (R-V8):** confirmed: markdown.py:21 and vendor.py:192.
- **R-14 (R-V9):** spec-text only. Upgrading the four root headers would break NFR-6's "A001 lowered by exactly one".
- **R-15 (R-V10):** follow-up, because the spec chose these homes (D-12, rows 13-14).
- **R-16 (R-E3):** `probe_misc.py` with the real URL builder:
  - `GitHubSkill ref='..'` sends `https://api.github.com/repos/acme/skills`.
  - `AnthropicSkill skill_id='..'` sends `https://api.anthropic.com/v1/versions/1/content`.
  - `OpenAISkill version='..'` sends `https://api.openai.com/v1/skills/skill_x/content`.
  - `version='.'` sends `…/skill_x/versions/content`.
  - The host never changes, so it stays Minor.
- **R-17 (R-E4):** I timed `SkillMarkdown.parse` on a 1,048,576-byte flow-list frontmatter: `parse 6.51s on the calling thread, result: document`.
  - It stays Minor, because it needs a hostile or pathological `SKILL.md` from a source the developer configured, and it is paid once per agent (a success is remembered). The reviewer's Minor tier stands.
- **R-18 (R-E5):** [scope-adding]. No spec or request text asks for logging.
- **R-19 [verifier]:**
  - `issubclass(httpx.InvalidURL, httpx.RequestError)` → `False`.
  - A probe with a 70,000-character `ref` gives `RAISED InvalidURL | sent 0`.
  - Same escape route as R-2, but it needs absurd input. A bound would be a new limit ([scope-adding]), so this is a follow-up.

## Blind-spot pass (step 6)

- **Between lenses:**
  - Conventions' R-V4 fix (`bearer_headers`) does not interact with R-2's guard, which runs before the header is built.
  - Conventions' R-V2 fix must keep `<Class>.<field>` in messages, because `test_skill_sources_entries.py` asserts it on 41 rows.
  - Conformance R-C2's added sentence must keep the absolute path (EC-16/AC-6-style keyword checks).
  - R-3's re-wrap must come last, or the other fixes add new long comments.
- **Version portability (NFR-8):**
  - Only one test failed on 3.12 (3,742 passed), and the other two 2,000-deep rows end the same either way.
  - `asyncio.timeout`, `deadline.expired()`, `Path.is_file()` (which returns `False` for `ValueError`), and the slotted-dataclass hierarchy ran green on 3.12 in CI.
  - Residual: the 40,000-case zip fuzz ran only on 3.11. The pack's 240 seeded fuzz rows passed on 3.12.
- **Other user input that httpx refuses before sending:**
  - Non-ASCII text in the URL is percent-encoded by `quote`, so it is safe.
  - Header values were probed in R-2.
  - Over-long URLs are R-19.
  - Header-value control characters are covered by R-2's `isprintable()`.
- **Remote CI after repair:** `Package` was skipped on `8eb304cc`, so it has never run green on this branch. Re-dispatch `ci.yml` after S5; per memory, the SDK's CI runs only on dispatch.

## Disagreements adjudicated

1. **R-C1 vs R-E1 severity and scope.** The two lenses agreed on Major. I raised the merged finding to Blocker (reasons above). Conformance flagged that INV-9's letter permits the crash; engineering treated it as an INV-9 violation. Ruling: INV-9's "programming error" means SDK bugs, and user-typed credentials are expected input under FR-14 and G-2. The code obeys INV-9's letter, but the spec has a gap there. Fix: source plus one new EC row.
2. **R-V1 Blocker vs the other lenses' silence.** Conformance and engineering did not check comment width. The field-guide entry exists, applies, and is the owner's recorded comment, so the rubric makes it a Blocker.
3. **R-C3's fix.** The reviewer's primary fix is unimplementable (see R-7), so I replaced it with the documentation alternative the reviewer also offered.
4. **R-V7's "saved settings".** The reviewer said nothing persists settings. request.md §C states that reason for the `type` field, so that sub-claim is refuted.
5. **R-V6 vs AGENTS.md principle 4.** I kept it Minor. The approved spec (INV-2) and the secret rules define the message contract, and the sibling grain matches.

## Commands run (final lines)

- `git log --oneline -3` → `8eb304cc … pipeline state`, `97c67062 …`, `d6fd75d0 …`; `git status --short` → only the three untracked S4 reviews.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` → `373 passed, 1 skipped in 4.16s`
- `python probe_ci312.py` → see R-1; `py -3.13 -I -c <json.loads>` → `3.13.1 PARSED; tree item type: list ; recursionlimit 1000`
- `python probe_nonascii.py` → see R-2
- `python probe_misc.py` → see R-4, R-7, R-9, R-16
- awk quick check and the Python diff count → `PR-added # lines over 72 chars: 60`
- C002 identity probe and `python lint/run.py --rule C002` → `C002 RATCHETED: 9 known finding(s)` … `SDK-LINT: PASS`
- `python -I mutate.py <worktree>` → see R-6
- `python -I try_fixes.py <worktree>` → `pack with fixes: 353 passed, 1 skipped in 3.99s`, and both probes flip (see R-1 and R-2)
- Inline: `issubclass(httpx.InvalidURL, httpx.RequestError)` → `False`; h11 newline → `LocalProtocolError`; 70,000-character `ref` → `RAISED InvalidURL | sent 0`; YAML timing → `parse 6.51s`
