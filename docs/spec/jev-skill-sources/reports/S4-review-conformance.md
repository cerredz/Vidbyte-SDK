LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — the PR builds every §12.3 row, keeps every ID in spec r4, and runs the §4 snippet exactly. Two gaps remain against the user's "edge cases/failure modes … all throughout" request: a credential that cannot be encoded crashes every run instead of failing open, and EC-24's required "create a new agent" detail is missing.

WHAT THE IMPLEMENTATION GETS RIGHT (so nobody "fixes" what works)
- The user's shape is exact. Six frozen, slotted entry subclasses each have a read-only `type` (`init=False`, so passing `type=` raises `TypeError`). `GitHubSkill` and `SkillsShSkill` have no `text`, so `text=` raises `TypeError` (EC-1/EC-2). Each source has one resolver module under `vidbyte/agents/skills/`, and `SkillLoader` sits under the hood with no user-facing loader. The §4 snippet prints the five documented lines (AC-1 green). The acceptance test copies §4 verbatim except one marked runner-binding line.
- The error and memory contract matches r4. `SkillLoader.load` (loader.py:57-73), `JevSkillsPreload.run`, and `SkillFetch.get` add no broad `except`. `SkillFetch.get` catches only `ProviderRequestError` and a `TimeoutError` whose `deadline.expired()` is true. Memory is written in one place (loader.py:68-70) with `setdefault`, so nothing is replaced. The transient set is exactly `{RATE_LIMITED, FETCH_FAILED}` (constants/skills.py:45), which matches every §6.3 "Rem." cell I walked: GitHub 400/3xx-other/5xx/non-SHA/bad tree are `FETCH_FAILED`; vendor 3xx/5xx/529 are `FETCH_FAILED`; local `OSError` is `FETCH_FAILED`; everything else is remembered.
- The vendor fallback handles both open questions (A-1/A-4) as D-19/D-20 require. It reads a bare `SKILL.md` (with an optional BOM, capped) or a zip (vendor.py:192-210). It falls back `latest` → `latest_version` → `latest_version_id` only on 400/404/422 (vendor.py:133-138, 177-182), ints become decimal text, and a bool is never a version. It gives a distinct "exists … content route was not found" detail (vendor.py:154).
- The boundaries are clean:
  - 14 new files, 12 package classes, 9 classes in the dataclass module, 3 enums, 0 dependencies, exactly 9 new root exports.
  - No file is touched outside §12.3, and `tests/` is unchanged since `d01e0afa`.
  - `lint/baseline.json` changes only A001 (643 → 642).
  - Every pre-existing `@intent` in the preload is kept.
  - The internal names `SkillFetchStep`, `SkillResolution`, `SkillText`, and `SkillLoader` do not leak to the root.

FINDINGS (ranked, most severe first)

R-C1 [Major] [request-fidelity] vidbyte/agents/skills/github.py:105-108 and vidbyte/agents/skills/vendor.py:117-122 — A token or API key with a non-ASCII character (in the entry or the env fallback) crashes every run that reaches the preload, takes the healthy sibling skills down with it, and carries the token in the exception's repr.
  Evidence: The only credential guards are the Vidbyte-prefix checks, and nothing checks that a credential can be sent as an HTTP header:
    github.py:105 `if token is not None and token.startswith(VIDBYTE_API_KEY_PREFIX):` → github.py:108 `auth = {"authorization": f"Bearer {token}"} if token else {}`
    vendor.py:120 `if key.startswith(VIDBYTE_API_KEY_PREFIX):` → vendor.py:84 `headers = self._headers(key)`
    dataclasses/skills.py:178, 201, 219 validate `token`/`api_key` as non-blank text only.
  httpx encodes header values as ASCII inside `client.build_request` (transport.py:64). That call is outside every try, so `UnicodeEncodeError` (a `ValueError`) escapes `SkillFetch.get`, the resolver, and `SkillLoader.load`.
  Probes (scratchpad, network sends stubbed to raise):
    `GitHubSkill(..., token="ghp_abc\u2019")` → `RAISED: UnicodeEncodeError`
    `AnthropicSkill(..., api_key="sk-ant-\u200bx")` → `RAISED: UnicodeEncodeError`
    `GITHUB_TOKEN="ghp_\u00e9"` (env fallback, no entry token) → `RAISED: UnicodeEncodeError`
    `OPENAI_API_KEY="sk-\u2013proj"` (env fallback) → `RAISED: UnicodeEncodeError`
    loader `(InlineSkill, GitHubSkill(bad token))`: `load 1: RAISED UnicodeEncodeError; inline remembered: False` / `load 2: RAISED …` (it repeats on every load)
    `repr(exc)` → `UnicodeEncodeError('ascii', 'Bearer ghp_SECRETTOKEN1234\u2019', 26, 27, …)`, so `repr contains token: True`
  Failure: A developer pastes a token with a curly quote or zero-width space, or the deployment's `GITHUB_TOKEN`/`ANTHROPIC_API_KEY` has one. Every `arun` then raises `AgentExecutionError` (the AC-15 path), not `auth_failed` on that one skill, and the inline and local skills in the same run are lost. Nothing is remembered, so every run repeats the crash. The `__cause__` repr that error reporters print contains the full `Bearer <token>`.
  Prosecution versus defense: INV-9 literally classes any exception outside §9.2 as a programming error that should propagate, so the code obeys INV-9's letter. But the spec's TL;DR says "loading never fails a run — every way a source can go wrong ends as an UNAVAILABLE result", and G-2 says the run "continues with the remaining skills". request.md §C agreed "Fail-open at run time", and the user asked that "for each type of skill we are handing the edge cases/failure modes … all throughout the implementation". A malformed credential is a failure mode of all three credentialed types, and §6.3 has no row for it: a spec gap the implementation inherits. Tie goes to the prosecution. A verifier may weigh it as a Blocker under G-2 and G-4 ("Secrets never leak").
  Smallest fix: Where the prefix guard already runs (github.py:105, vendor.py:120), also return `AUTH_FAILED` with no request when the stripped credential is not ASCII (`not token.isascii()` / `not key.isascii()`). The detail names `token=`/`GITHUB_TOKEN` or `api_key=`/the env var and never echoes the value. Add one EC row to §6.3 and one test per source. This is not scope-adding: it maps an existing failure class to an existing reason, exactly as §C's fail-open decision requires.
  Spec IDs: G-2, G-4, FR-14, INV-8 (sibling results lost), INV-14/NFR-5 (token in exception repr), §9.2 "missing key / prefix → AUTH_FAILED, no request" row, request.md §C "Fail-open at run time"

R-C2 [Major] [ID-walk] vidbyte/agents/skills/local.py:58 — EC-24's required detail is missing: a remembered `not_found` never tells the developer that only a new agent picks up the fix.
  Evidence: spec §6.3 EC-24, "User sees" cell: "`not_found`, detail says to create a new agent after fixing". The code at local.py:58 is
    `detail=f"No {SKILL_MARKDOWN_FILE_NAME} file at {skill_file}; point path= at the folder that holds it."`
  `grep -rn -i "new agent\|restart\|create a new" vidbyte/agents/skills/` finds only a comment at local.py:47. Probe output: `NOT_FOUND No SKILL.md file at C:\…\missing\SKILL.md; point path= at t…`. The EC-24 test (test_skill_sources_local.py:146-155) checks only that the miss is remembered, so the gap is untested.
  Failure: The developer creates the folder the detail points to. The same long-lived agent keeps reporting `not_found` with the same instruction they just followed, because the miss is remembered (Q-1 default), and nothing says a new `JevAgent` is required.
  Smallest fix: Append a sentence such as "This agent remembers the miss; create a new JevAgent after fixing it." to the local `NOT_FOUND` detail (local.py:58). For consistency with Q-1, the same suffix is optional on the remembered skills.sh `NOT_INSTALLED` detail (skills_sh.py:53) and the missing-key `AUTH_FAILED` detail (vendor.py:119). Only local.py:58 is spec-mandated.
  Spec IDs: EC-24, INV-5, Q-1, FR-14 ("a detail that names the fix")

R-C3 [Minor] [ID-walk] vidbyte/lib/dataclasses/skills.py:134 and :154 — `Path("")` passes the EC-13 guard, which rejects only the `str` `""`, so the entry silently means the working folder.
  Evidence: `if not isinstance(self.path, (str, Path)) or self.path == "":` (`Path("") == ""` is False). Probe: `ACCEPTED Path(''): LocalSkill C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-jev-skill-sources`. `SkillsShSkill(directory=Path(""))` is accepted the same way. `LocalSkill(path="")` is rejected (`str '' rejected: ConfigurationError`).
  Failure: `LocalSkill(name="x", path=Path(os.environ.get("SKILL_DIR", "")))` with the variable unset reads `./SKILL.md` from wherever the process started. EC-13's stated rationale is to stop exactly that ("`Path("")` would silently mean the working folder").
  Smallest fix: Also reject `str(self.path) == ""` before pinning, or document that `Path("")` is treated as `"."`. `Path("")` and `Path(".")` cannot be told apart after construction, so the check must look at the raw `str`/`Path` value. The literal §9.1 cell ("not `""`") is met, so this is Minor.
  Spec IDs: EC-13, INV-2, FR-3, D-15

VERIFIED CLAIMS
1. S3 "373 passed, 1 skipped": HELD (rerun, `373 passed, 1 skipped in 4.21s`; the skip is the Windows case-insensitive row).
2. S3 "full suite 3747 passed": HELD (`3747 passed, 14 skipped in 29.78s`).
3. S3 "lint SDK-LINT: PASS, A001 at 642, no REGRESSED": HELD (A001 642/642 RATCHETED; `grep -c REGRESSED` = 0). The NFR-6 rules (S011, S012, S047, S061, S063, S064, C016, C020) are at baseline, and `--rule X --all` lists no finding in a changed file. The only S009 hit in a changed file (alignment/skills.py:202, `answer.noul` union-attr) predates this PR (origin/main line 146).
4. S3 "tests unchanged since d01e0afa": HELD (`git diff d01e0afa..97c67062 -- tests/ | wc -l` = 0). `tests/test_jev_skill_preload.py` is not in the PR diff at all.
5. "baseline only A001 lowered": HELD (the only hunk is `"A001": 643` → `642`).
6. "contract regenerated, 9 added, none removed": HELD (`--check`: current at 3a4cb929, 615 exports; the contract diff has exactly 9 `+` names and 0 `-` names).
7. "§8.4 budget used exactly": HELD (14 new files; 12 package classes including `_GitHubAnswer`; 9 dataclass-module classes; 3 enums; 0 dependencies; 1 new env var).
8. "no files outside §12.3": HELD (every changed path maps to rows 1–30; other changes are only `docs/spec/jev-skill-sources/`).
9. Deviation 1 (`GITHUB_CREDENTIAL_ENV_VAR`) is necessary: HELD. `ruff --isolated --select S105` flags `GITHUB_TOKEN_ENV_VAR = "GITHUB_TOKEN"` and not the new name, and S054's code set includes S105 (lint/rules/s054_bandit_security_subset.py:27). The only fix that adds no suppression is the rename. It is minimal and recorded.
10. Deviations 2–7 are necessary, minimal, and recorded in §17: HELD.
    - The `_unbatched`/`_failed_batch` start-state claim was checked by reading `run`: the loaded seed `_score_skill(i, doc, {})` is replaced on every path (unbatched → TOO_LARGE; VidbyteSdkError or no usage → `_failed_batch`; answered → scored; anything else → raise).
    - `run` is about 47 lines.
    - Unreported deviations: none found.
    - Every public name in §8.5/§9.2 matches the code (nine root names, `JevSkillResult.reason/detail`, `SkillLoader.load/documents`, `SkillFetch.get`, `SkillMarkdown.parse`, `read_capped`, `_GitHubAnswer.failure`). The only differences are recorded ones: `field_name` and `_raw_document`.
11. S3 "spec text unchanged except frontmatter, AC-17/AC-21 Proof cells, §17": HELD (`git diff bd6d54d4..97c67062 -- spec.md` touches only those lines).
12. Internal names stay internal: HELD (`hasattr(vidbyte, 'SkillFetchStep'/'SkillResolution'/'SkillLoader')` all False; `SkillResolution` and `SkillText` are not in `vidbyte.lib.dataclasses`).
13. No `vidbyte/agents/skills/` module imports `vidbyte.agents.jev` or the `vidbyte.agents` root, and no new `vidbyte.lib` code imports `vidbyte.agents`: HELD (grep).
14. Forbidden patterns (`noqa`, `type: ignore`, `HTTPStatus(`, `vb_live_`, subprocess, `asyncio.Lock`, `TypedDict`, `extractall`, `read_text(`/`read_bytes(`, `follow_redirects=True`, `except Exception`/`BaseException`): HELD. Every grep hit in the added lines is a comment or a docstring.
15. AC-1 acceptance test is faithful to §4: HELD. The skill tuple, the agent construction, `arun`, and the print loop are verbatim, with one marked `bind_main_runner(agent)` line. The expected stdout is the five §4 lines exactly. Its preconditions (no `.agents/skills`, `ANTHROPIC_API_KEY` removed, the local `SKILL.md` written, GitHub faked at `_send_once`, Jev 0.9/0.9/0.1) match the AC-1 Given.
16. §5 diagram versus the call path: no material divergence.
    - `JevAgent.__init__` → `JevSkillsPreload.__init__` builds one `SkillLoader` (alignment/skills.py:74).
    - `run` → `load()` → seed results → `_build_batches` reads `loader.documents()` → Jev gather → score → `_append_selected`.
    - Local and skills.sh read in `asyncio.to_thread`.
    - The one step the diagram leaves out is `_unbatched` (TOO_LARGE marking), which row 22 specifies.

ID walk (prosecution versus defense, each checked against code or a passing test):
- FR-1 to FR-16:
  - FR-1, FR-2, FR-4 to FR-13, FR-15, and FR-16 held.
  - FR-3 held except R-C3.
  - FR-14 held except R-C1 and R-C2.
- NFR-1 to NFR-8 held. NFR-8 (Python 3.12) cannot be checked locally; it is CI-only.
- INV-1 to INV-27 held.
  - INV-1: AC-2 is green, and the vendor `__init__` reads only registry constants (`DEFAULT_ENDPOINTS`, `API_KEY_ENV_VARS`), with no env read.
  - INV-9 is held to its letter (no broad `except`; `raise answer` re-raises the original object); see R-C1 for its spirit.
  - INV-10: there is no `await` between `load()` and `_build_batches`/`_unbatched`, and remembered documents never change.
  - INV-12: its "nothing besides one SKILL.md is read" wording conflicts with D-17's lock read and the GitHub and vendor metadata steps. That is internal to the spec, and the implementation follows D-17.
- AC-1 to AC-29:
  - All pytest-backed ACs are green.
  - AC-17 contract half: `--check` passes.
  - AC-21: lint passes, the REPO_MAP entry follows `settings/`, and REPO_MAP names four skills locations.
- EC-1 to EC-117: every row was walked against the code.
  - Rows the test plan left unwritten were checked by reading:
    - EC-9: `KeyError` in `_pending_groups` propagates.
    - EC-17 (loop): `is_file()` is False, so NOT_FOUND.
    - EC-19: `OSError` gives FETCH_FAILED with the path and error class.
    - EC-23, EC-47, EC-58, EC-90, EC-92, EC-100, EC-113, and EC-114 are accepted rows; EC-114 is documented in the README.
    - S2-5 lock without a version: `not isinstance(version, (int, float)) or type(version) is bool` makes the lock absent.
  - Every "User sees" detail requirement matches the code except EC-24 (R-C2).
- §12.3 rows 1–30:
  - Rows 1–28 and 30 are done as specified, with the recorded deviations. Row 29 belongs to S2.
  - The README notes required by row 8 are all present (no npx, no redirects, no secrets, no jev import, fourth skills location, T-4, EC-116, D-28, Q-6).
- request.md §A weighted words:
  - Held: an "array" of entries with "type and text"; "no text" for GitHub and skills.sh; "no loaders or dataclasses" for users (they build no `SkillDocument`); "SkillLoader under the hood"; "subclasses for each type" (one module per source, with vendor as the shared base); "inside vidbyte/agents/skills"; "attach … onto the JevAgent".
  - "Edge cases/failure modes … all throughout": partial (R-C1, R-C2).
  - No scope creep found: nothing beyond the spec, and no WellKnownSkill, refresh API, CLI, or subprocess.
  - §C decisions changed only through recorded spec decisions: NG-10, D-7, D-21, D-22, D-15.

COMMANDS RUN
- `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → `…\worktrees\vidbyte-sdk-jev-skill-sources\vidbyte\__init__.py`
- `git diff --stat 97c67062 8eb304cc` → `docs/spec/jev-skill-sources/pipeline.md | 7 +++++--` (HEAD differs from the code under review only in docs)
- `git diff origin/main...97c67062 --stat` → `54 files changed, 8132 insertions(+), 87 deletions(-)`; `git merge-base origin/main 97c67062` → `ba3e4ca5…`
- `git diff d01e0afa..97c67062 -- tests/ | wc -l` → `0`
- `git diff origin/main...97c67062 -- lint/baseline.json` → only `-  "A001": 643,` / `+  "A001": 642,`
- `PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider` → `373 passed, 1 skipped in 4.21s`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` → `3747 passed, 14 skipped in 29.78s`
- `PYTHONPATH=$(pwd) python lint/run.py` → `A001 … 642 642 RATCHETED` … `SDK-LINT: PASS`, `exit=0`, 0 REGRESSED
- `PYTHONPATH=$(pwd) python lint/run.py --rule {S063,S061,S024,C020,S049,S054,A006,S015,C002,A003,S009} --all | grep <changed files>` → no hits, except the pre-existing S009 `alignment/skills.py:202 … "noul"`
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 3a4cb929… (vidbyte-sdk 0.2.1, 615 exports).`
- `python -m ruff check --isolated --select S105 --no-cache <scratch s105.py>` → flags line 1 (`GITHUB_TOKEN_ENV_VAR = "GITHUB_TOKEN"`) only; `Found 1 error.`
- `git diff bd6d54d4..97c67062 -- docs/spec/jev-skill-sources/spec.md` → frontmatter, AC-17/AC-21 Proof cells, and §17 only
- Scratchpad probes `probe1.py`/`probe2.py`/`probe3.py`, run with `PYTHONPATH=$(pwd)`, `httpx.AsyncClient.send` stubbed to raise, and no network:
  - `ACCEPTED Path(''): LocalSkill …` / `ACCEPTED Path(''): SkillsShSkill …` / `str '' rejected: ConfigurationError`
  - `RAISED: UnicodeEncodeError` for an entry token, an entry api_key, `GITHUB_TOKEN` env, and `OPENAI_API_KEY` env
  - `load 1: RAISED UnicodeEncodeError; inline remembered: False` / `load 2: RAISED UnicodeEncodeError; inline remembered: False`
  - `repr contains token: True` / `str contains token: False`
  - `EC-24 local detail: … NOT_FOUND No SKILL.md file at …\missing\SKILL.md; point path= at t…`
- `git status --short` → empty (worktree clean; only this report was written)
