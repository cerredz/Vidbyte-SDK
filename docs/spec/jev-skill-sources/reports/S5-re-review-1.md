LENS: conformance (post-repair re-review)
VERDICT: SOUND — every repaired finding is fixed at its root cause, EC-118 and EC-119 hold on all six credential paths, the main merge leaves skill fetches unchanged, and the only new finding is one Minor spec-text drift caused by R-9.

Reviewed: `git diff origin/main...3ce9de96` (merge base `d172c6ef`) and the repair delta `git diff 97c67062..d0d28c3d -- vidbyte/` (commits 879a4b16, 556b84fc, 757a0464, ca340b36, dde94f83, 9567cd4a, 4079d101, 472c7b1a, 75c5f459), plus the merge `4f956afc`. Spec r5, review.md, S5-repair-1.md, verify-log.md, AGENTS.md, and field-guide `comment-format.md` were read in full.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The credential guards are complete.** The header-safe guard sits in the same two places as the Vidbyte-prefix guard: `github.py:112` and `vendor.py:126`. Both run on the stripped value and before any request is built.
  - An entry value never falls back to the environment. `GitHubSkill.token` and the vendor `api_key` reject whitespace-only text at construction (`SkillText.require_optional`). `_token` (`github.py:141`) and `resolve_api_key` (`registries/models.py:169`) then prefer any non-blank entry value.
  - A probe ran 36 extra cases: 3 sources, entry or env, and 6 characters the tests do not use (NBSP, NEL, CR, NUL, ideographic space, BOM). Every case ended `auth_failed` with `sent=0`, was remembered on the second load, and had a detail naming both the field and the env var.
- **R-8 behaves exactly as before.** A differential probe compared HEAD's `match` against the pre-R-8 count-and-unpack body. It covered 16 crafted bodies: zero, one, and two members; too deep; stored, bzip2, and lzma; the encrypted flag; a declared oversize; encrypted plus oversize; bare, BOM, and over-cap bodies; neither; and a truncated zip. All 16 were identical. Over 5,000 fuzzed archives there were 0 differences. S024 stays at 25/25.
- **R-3 changed comments only.** `git diff 472c7b1a..75c5f459 -- vidbyte/` has no non-comment `+`/`-` line. The removed and added comment words match as one sequence (1161 = 1161, `cmp` identical). PR-added `#` lines over 72 columns in `vidbyte/`: 0. Every `# @intent` line still stands alone.
- **The main merge does not reach skill fetches.** Main's `_json_request_headers` (`lib/http/transport.py:33`, #888) runs only when `json_body is not None`. `SkillFetch.get` (`fetch.py:56-65`) never passes a body. Main's changes to `registries/models.py`, `agents/base.py`, and `constants/jev.py` do not touch `resolve_api_key`, `get_default_endpoint`, or `get_api_key_env_var`.
  - The merge's combined diff resolves only `lib/enums/__init__.py` (it keeps `ShellKind` and the three skills enums).
  - `lint/baseline.json` keeps A001 at 642 and takes main's C009 and C018 values.

## FIX CONFIRMATIONS

- **R-1 — confirmed.** `github.py:183` now sends a listing whose items are not all dicts with a text `path` to the existing `FETCH_FAILED` "unexpected answer". `probe_ci312.py` gives `FETCH_FAILED` for all four shapes, and load 2 sends 2 requests again (not remembered). On the Python 3.13.1 venv the 2,000-deep body parses, and the 14 `unusable` rows pass. Mutant `r1-drop-item-check`: KILLED (5 failed).
- **R-2 — confirmed.** The guard is at `github.py:110-114` and `vendor.py:126-127`. `probe_nonascii.py` gives `AUTH_FAILED sent=0` for all four cases, and the loader returns on loads 1 and 2. At agent level, the main model now runs: `main model calls: 2`. Before the fix it was 0.
  - Mutants KILLED: guard removed, isascii-only, and isprintable-only, for GitHub and for the vendors (6 mutants), plus detail-echoes-value for each (2 mutants).
- **R-3 — confirmed.** The awk check reports 0 for every new `vidbyte/` module. The non-zero counts are in `alignment/skills.py` (15), `jev/settings.py` (18), `dataclasses/jev.py` (115), and `dataclasses/skills.py` (2). All of them are pre-existing lines: the PR-added-line check over `git diff -U0 origin/main...3ce9de96 -- 'vidbyte/*.py'` prints nothing.
- **R-4 — confirmed.** `local.py:59` keeps the absolute path (EC-16) and appends "This agent remembers the miss, so create a new agent after fixing it." (EC-24). This is the only local `NOT_FOUND` site. Mutant `r4-sentence-removed`: KILLED.
- **R-5 — confirmed.** `SkillText.require_version` and `require_folder` (`dataclasses/skills.py:90-104`) are the only owners of these checks. Calls stay one level deep (`require_version` → `require`, a leaf). Every message still holds `<Class>.<field>`, and no test asserts the old wording. C002 9/9 and C008 45/45 are ratcheted. Mutants `r5-folder-not-absolute` and `r5-version-int-hint-removed`: KILLED.
- **R-6 — confirmed.** The four S4 survivors were re-run at HEAD (`markdown-strip-delimiter` re-anchored for R-13): `skillssh-too-large-removed`, `skillssh-cap-off-by-one`, `skillssh-oserror-remembered`, `lock-oserror-propagates`, and `r13-markdown-strip-delimiter` are all KILLED.
- **R-8 — confirmed.** The differential probe gives 16/16 identical and 0/5000 fuzz differences. `SKILL_ARCHIVE_MARKDOWN_COUNT` has no reference outside `docs/`. Mutants `many-members-read-first`, `encryption-guard-removed`, and `size-guard-removed`: KILLED.
- **R-9 — confirmed, with a spec drift.** `github.py:115` uses `HttpResponseParser().bearer_headers(token)`. The helper's `content-type` now goes on the wire; see R-RC1.
- **R-12 — confirmed.** The jev `PURPOSE` at `agents/jev/__init__.py:3` names the 7 entries and 2 enums, and `__all__` exports them (lines 264-273). `vendor.py:7` and README step 3 name the constrained `VendorSkillT` and S009.
- **R-13 — confirmed.** `SKILL_MARKDOWN_DELIMITER` is defined at `lib/constants/skills.py:26` and listed in `__all__`. It is used at `markdown.py:70,73` and `vendor.py:201`, and no `_DELIMITER` or `b"---"` copy remains.
- **R-14 — confirmed.** The §12.4 A001 item covers new files plus `vidbyte/lib/enums/skills.py`, and the four package roots stay old-style (spec.md:822). A001 is 642/642.

## FINDINGS

R-RC1 [Minor] [spec-text drift] `vidbyte/agents/skills/github.py:115` against `docs/spec/jev-skill-sources/spec.md:611-613` — With a token, the GitHub requests now carry `content-type: application/json`, which §9.2 does not list
  Evidence:
  - `probe_headers.py` patches `httpx.AsyncClient.send` and records the headers after `build_request`.
  - GitHub commit lookup and raw file with a token: `('accept', …), ('authorization', <redacted>), ('content-type', 'application/json')`, with `body=b''`.
  - The same request without a token has no `content-type`.
  - §9.2 lists the GitHub headers "besides httpx defaults" as only `accept` and `authorization: Bearer <token>`. The OpenAI row (spec.md:616) names `HttpResponseParser.bearer_headers(key)` and so covers the extra header; the GitHub rows do not.
  - review.md R-9 already called the extra header "harmless on a GET", but the spec was not amended.
  Failure: A reader, or a later test author pinning the exact header set from §9.2, expects two headers but sees three when a token is set and two when it is not. The behavior is harmless: GitHub ignores a request content type on a GET.
  Smallest fix: Spec text only. In spec.md:611, replace "`authorization: Bearer <token>` when a token exists" with "`HttpResponseParser.bearer_headers(token)` when a token exists (`authorization: Bearer <token>` plus an unused `content-type: application/json`)". Rows 612-613 already say "token as above". No code change.
  Spec IDs: §9.2 outbound-request table; D-10; R-9.

No other new finding. No Blocker or Major.

## VERIFIED CLAIMS

- **EC-118 and EC-119 hold on every path.** The paths are the GitHub entry token and `GITHUB_TOKEN`, and the Anthropic and OpenAI `api_key` plus their env vars.
  - The value is stripped first (`github.py:142`; `resolve_api_key` strips).
  - It is refused unless `isascii() and isprintable()`.
  - The result is `AUTH_FAILED` with no request. It is remembered, because `AUTH_FAILED` is not in `SKILL_TRANSIENT_REASONS`, and load 2 also shows `sent=0`.
  - The GitHub detail names `token=` and `GITHUB_TOKEN`. The vendor detail names `api_key=` and `self.env_var`. Neither formats the value: the GitHub detail is a plain literal, and the vendor detail interpolates only `self.host` and `self.env_var`.
  - An unsafe entry value with a usable env value set is still refused (test rows `where=entry`, and my probe).
  - When the stripped env value is blank (`"   "`), GitHub goes unauthenticated (1 request), per row 15 "blank = none". The vendor gets "No API key", per §9.2.
- **The tests can fail.** All 21 delta mutants were killed. One first-pass mutant was a non-mutant, because the GitHub detail is not an f-string; it was re-run in a corrected form and KILLED.
- **R-5 changes no tested message.** The tests check only `<Class>.<field>` and `"2"` (`test_skill_sources_entries.py:146,157-158`). The one semantic difference is that the `SKILL.md` name check now runs on the absolute path. It differs only for `LocalSkill(path=".")` inside a working folder that is itself named `skill.md`, which is not a real case.
- **AGENTS.md principles 1 and 5 hold for the delta.** No new nested function. No new helper chain deeper than one level. The bearer header comes from the canonical helper.
- **§8.4 budget holds.** No new file, class, dependency, or public name. One constant was added (`SKILL_MARKDOWN_DELIMITER`) and one removed. The contract is current at 615 exports.
- **Expected skip.** The one skip is the expected Windows row for lowercase `skill.md`.
- **Scope note (not a finding):** the PR's test files carry `#` lines over 72 columns (for example 30 in `test_skill_sources_vendor.py`). R-3 and the S4 review were scoped to `vidbyte/`, the field guide says "in SDK code", and the test tree has been frozen since `578cd064` (§14). I did not file it.
- **Probe note:** `probe_nonascii.py`'s agent block now ends in `UsageAccountingError` (`agents/jev/usage.py:49`, fail-closed ledger from #519). The probe's fake runner reports unpriced usage. The same error appears with `skills=()` (`probe_agent_usage.py`), so it is not caused by this feature.

## COMMANDS RUN

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` → `426 passed, 1 skipped in 4.53s`
- The same plus `tests/test_http_transport_content_type.py` → `434 passed, 1 skipped in 4.75s`; the transport test alone → `8 passed in 0.70s`
- `PYTHONPATH=$(pwd) python lint/run.py` → `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`
  - Rows: A001 642/642; A002 632/703 IMPROVED; A007 254/255 IMPROVED; A009 0/0; C002 9/9; C008 45/45; C016 0/0; S009 349/350 IMPROVED; S024 25/25; S063 4/4.
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 3a4cb929… (vidbyte-sdk 0.2.1, 615 exports).`
- `python <scratch>/s4-verify/probe_ci312.py` → all four tree shapes `FETCH_FAILED`, `requests load1=2 load2=2`
- `python <scratch>/s4-verify/probe_nonascii.py` → `control ASCII entry token: FETCH_FAILED sent=1`; the four unsafe cases `AUTH_FAILED sent=0`; `loader load 1: returned` / `loader load 2: returned`; `main model calls: 2`
- `py313-venv python -m pytest tests/features/jev_skills_preload/test_skill_sources_github.py -k unusable` → `14 passed, 34 deselected in 5.38s`; `3.13.1` / `2000-deep PARSED`
- `awk 'length($0) > 72' <file> | grep -cE '^\s*#'` over every PR `.py` file → 0 for all new `vidbyte/` modules. The non-zero `vidbyte/` files are pre-existing lines.
- `git diff -U0 origin/main...3ce9de96 -- 'vidbyte/*.py'` filtered to added `#` lines over 72 columns → no output
- `git diff 4079d101..75c5f459 -- vidbyte/ | grep '^[-+]' | grep -v '^[-+]\s*#' | grep -v '^[-+][-+]'` → only R-12's three docstring/README lines. The same check over `472c7b1a..75c5f459` (R-3 alone) → no output.
- Word-sequence check of R-3 (`old_words.txt` vs `new_words.txt`) → `1161 1161`, `WORD SEQUENCES IDENTICAL`
- `python -I <scratch>/s5-rereview/mutate2.py <worktree>` → `baseline 406 passed, 1 skipped`; every mutant KILLED (r1 ×1, r2 ×8, r4, r5 ×2, r8 ×3, r13, r6 ×4)
- `<scratch>/s5-rereview/probe_r8_diff.py` → `crafted: 16/16 identical; fuzz 5000 mutated archives: 0 differences`
- `<scratch>/s5-rereview/probe_ec118_extra.py` → 36/36 `auth_failed sent=0 load2=auth_failed names_field=True names_env=True`; `blank-after-strip env github: fetch_failed sent=1`; `blank-after-strip env anthropic: auth_failed sent=0`
- `<scratch>/s5-rereview/probe_headers.py` → GitHub with a token has `content-type count=1 body=b''`; GitHub without a token has `content-type count=0`; Anthropic has 0; OpenAI has 1.
- `git show --cc 4f956afc` → only `vidbyte/lib/enums/__init__.py` needed resolution (`ShellKind` plus the three skills enums)
- `git diff --stat 578cd064..93e1041f -- tests/ lint/ contracts/` → empty
- `git status --short` → clean (no file written except this report)
