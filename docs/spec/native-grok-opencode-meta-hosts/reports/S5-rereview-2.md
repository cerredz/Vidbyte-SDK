LENS: conformance (post-repair re-review, round 2)
VERDICT: SOUND — R-16, R-17 and R-M11 each meet their spec rows on every path I traced or probed; the three commits break nothing, and the one new finding is a Minor wording error in one rewritten header.

Reviewed: `git diff b0e35a32..71be15fd -- vidbyte/`: 43 files, +129/−116. The code changes are 1768c3d5 (`hostkit/turns.py`), 1a9bc056 (`grok/turn.py`, `muse/turn.py`) and 45ad54ec (docstrings only). 45ad54ec..71be15fd touches only `docs/`. I read every hunk and opened `turns.py`, `grok/turn.py` and `muse/turn.py` in full, plus every turn-table call site in the three hosts. I checked all of this against spec r8: INV-6, INV-14, §8.5 `NativeTurnTable`, §9.1 `NativeApprovalDecision`, and the A001 rule.

FIXES CONFIRMED (one line each: ID — holds | does not hold — evidence)
- R-16 — holds:
  - **The key rule.** `_session_key` (`turns.py:114-122`) lower-cases ids only for GROK and MUSE and returns every other harness's id unchanged.
  - **One key everywhere.** `reserve` (:47-56), `bind_session` (:63), `release` (:80-82), `is_session_busy` (:94) and `_finish` (:107-109) all go through it. `_reserved` and the handle keep the raw spelling, and each removal recomputes the key from that same string. So adding and removing a session always use the same key.
  - **Probe** (`probe_table.py`), for Grok and Muse with vendor id `ABCDEF01-…`:
    - both spellings are busy;
    - `reserve(lower)` raises `<host>.session_busy`;
    - after the turn finishes, after a release following a bind, after a continue-style reserve and release, and after 67 turns that alternate spellings, the busy table is `{}`;
    - when two binds fold to one key, the table ends `{}` whichever turn finishes first;
    - the live-turn cap counts by turn id (`live_turns: '2'`);
    - `finished` is capped at 64, which is `NATIVE_FINISHED_TURN_LIMIT`.
  - **opencode stays exact.** With `ses_ABCdef0001` live, `is_session_busy('ses_abcdef0001')` is False, `reserve(lower)` is accepted, both keys coexist, and the table ends `{}` once both are freed. Every opencode path goes through the same table methods: `_reserve` (host.py:708), `bind_session` (:279), `release` (:308, :367), `activate`, and `_require_idle`'s `is_session_busy` (:717). The server-status match at :718 is also exact.
  - **Nothing on the wire changed.** The commit touches only `turns.py`. A spawn handle keeps the vendor's spelling, and continue returns the lower-cased argument, as R-8 already did.
  - **Tests.** The 8 R-16 cases and the 5 R-8 cases pass.
- R-17 — holds:
  - **Order.** `self._errors.scrub(title)[:NATIVE_APPROVAL_TITLE_MAX_CHARS]`, so scrub before the cap, at the only title-recording sites: `grok/turn.py:177`, `muse/turn.py:211` (shared by all four `_on_approval` appends) and `muse/turn.py:235`.
  - **Factory.** `_errors` is the host's own factory: `grok/host.py:557` and `muse/host.py:613` pass `errors=self._errors`. The expression is the same as opencode's at `opencode/turn.py:268`.
  - **Other decision fields.** The remaining sites record `title=""`: `grok/turn.py:185` and `opencode/turn.py:274`. §9.1 requires scrubbing only for `title`; `request_kind` is ≤ 128 characters and unscrubbed in all three hosts.
  - **Scrub probe.**
    - `Edit README.md`, `''` and `'   '` come back unchanged.
    - The `OPENAI_API_KEY=sk-proj-FAKE…` title becomes `…=<redacted> && make deploy`.
    - A registered value becomes `<redacted>`.
    - Scrub before the cap also means `<redacted>` can never push a title past the record's 200-character limit.
  - **Tests.** The 3 R-17 cases pass.
- R-M11 — holds, with one inaccurate rewrite (R-RR2-1):
  - **Code unchanged.** My AST check with docstrings blanked gives `files=43 code-differs=0 changed-docstrings=45` (1a9bc056 → 45ad54ec).
  - **No spec ids left.** No added non-comment line outside RELATED DOCS or TESTS cites a spec id.
  - **Lint.** A001 is 643/643.
  - **Rewrites checked against the code** (both tool docstrings are model-facing only through explicit descriptions):
    - the opencode client's five codes, plus the 404/409 meanings the caller passes in (`client.py:122-166`);
    - the Muse wire's code list, which matches `_CODE_PROBLEMS` and `vendor_failure` exactly (`wire.py:71-81, 214-240`);
    - "18 public methods in all" (counted: 18, plus the `mcp_servers` property);
    - the server argv (`_SERVE_ARGUMENTS`, `server.py:30`);
    - `_count_failure` "in a row" (the reset at `turn.py:138`);
    - the missing-name MCP status → `opencode.mcp_server_failed` (`host.py:672-673`);
    - a second `__aenter__` → `invalid_argument` (all three hosts);
    - the toolsets' grouping text, which matches the inline grouping comments.

FINDINGS (ranked, most severe first, max 10)
R-RR2-1 [Minor] [conformance / A001 accuracy] vidbyte/harnesses/native/grok/wire.py:3 — The rewritten PURPOSE says GrokWire maps JSON-RPC errors only to `grok.*` codes, but it also returns `configuration.invalid_argument`
  Evidence: 45ad54ec changed "…to the grok.* rows of spec §6.3." to "…maps JSON-RPC error codes and CLI failures to grok.* failure codes." The old wording covered EC-41, which is a GrokHost row with a configuration code. The new wording does not. `grep -n invalid_argument grok/wire.py` → `245: return self._errors.invalid_argument("cursor", "Grok Build refused the cursor; …"`. That is the -32602-with-cursor mapping (EC-41). The Muse wire's rewrite names its `configuration.invalid_argument` cases explicitly.
  Failure: A reader who trusts the header and handles only `grok.*` codes from `vendor_error` misses the stale-cursor refusal. This is a wording problem only; the behavior is correct and tested.
  Smallest fix: Append ", or configuration.invalid_argument for a stale cursor" to the PURPOSE sentence.
  Spec IDs: EC-41; A001 (§11, header kept true)

VERIFIED CLAIMS:
- Verify-log iteration 4, "packs 1649 passed, 19 skipped": held. My run gave `1649 passed, 19 skipped in 147.43s`.
- "Docstring-only, files=43 code-differs=0 changed-docstrings=45": held exactly (my own AST script).
- "Spec ids in headers: 0 (was 103)": held. Added non-comment lines citing ids outside RELATED DOCS or TESTS: 0. Added `#` lines citing ids: 0. Added `#` lines over 72 columns: 0.
- "A001 643/643, A002 577/703, SDK-LINT: PASS": held (`python lint/run.py`, tree clean before and after).
- "opencode probed exact; Grok and Muse freed after the driver finishes and after release": held, and extended to eviction, the cap, and folded-key overwrites (see R-16 above).
- "`scrub` leaves `Edit README.md`, `''` and `'   '` unchanged": held.
- "Remote CI 38432650695 and static policy 38432655274 green at 45ad54ec": held. `gh run view` shows `success` for Source 3.11, Source 3.12 and Package, and `success` for static policy, both at headSha 45ad54ec.
- "tests/, lint/, pyproject.toml, failure.py and spec.md unchanged since f9d062e6": held (empty diff). 45ad54ec..71be15fd changes docs only.
- Budget and boundaries:
  - the `lint/` diff against origin/main is empty;
  - `git diff 5ce6e85d 71be15fd -- tests/` is empty;
  - INV-19's sha256 is `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`;
  - the INV-22 paths (`vidbyte/__init__.py`, `contracts/sdk-public-api.json`, `tools/builtins/__init__.py`, `pyproject.toml`, `lint/`, `vidbyte/mcp_server/`) have an empty diff;
  - `failure.py` is append-only (+53) and unchanged since b0e35a32;
  - origin/main 8387d666 is an ancestor of HEAD.
- §4 / AC-1: held. I ran the snippet as the spec writes it, with PATH set to Python and System32, an empty USERPROFILE/HOME, `which grok` → None, and the worktree's `turns.py` imported. It printed exactly `grok.not_installed -> Install Grok Build 1.0.13 or newer, or set GrokHostSettings.grok_command.` and exited 0.
- Regressions in "What the implementation gets right" and round 1's confirmed fixes that these commits could reach:
  - R-8: `require_uuid(...).lower()` and the fork checks are unchanged, and the R-8 tests pass;
  - R-9: one 200-character title cap;
  - R-12: `_session_key` is a leaf, so the call depth stays at one;
  - R-13: it carries an `@intent` block, and A002 is unchanged at 577;
  - R-14 and R-15: covered by the comment checks above;
  - the FIFO finished table and the live-turn cap (INV-16) still hold, per the probe.
- Considered and not raised:
  - **T-6 versus the code.** T-6 (spec.md:1650) says vendor text in tool output is "scrubbed of the host's secrets" by `NativeResultEncoder`. But §8.5 (spec.md:1303) defines that encoder as static (record → JSON, clipped) with no factory, and no turn text is scrubbed (`opencode/turn.py:350`).
  - **Why it is not a finding here.** It is pre-existing since S3 and untouched by the three commits. The spec contradicts itself on it, and Grok and Muse register no secrets.
  - **Who is exposed.** It bears only on opencode reply text that echoes the server password or an MCP or backend value.
  - **What to do.** Record it as a follow-up, not a regression.
- Test-plan Addendum 2's open item "no test pins opencode's exact comparison" is still open. My probe proves the code is exact today, but a fold-everything refactor would still pass all four packs.

COMMANDS RUN:
- Inspection:
  - `git log --oneline -8`: HEAD 71be15fd, tree clean;
  - `git diff --stat b0e35a32..71be15fd -- vidbyte/`: 43 files, +129/−116;
  - `git show 1768c3d5 1a9bc056 -- vidbyte/`;
  - `git show 45ad54ec --word-diff`: all 146 changed header and docstring lines read.
- Boundaries:
  - the `lint/` and `tests/` diffs: empty;
  - `git show 71be15fd:vidbyte/harnesses/native/__init__.py | sha256sum` → `0374a2c8…f497a`;
  - the INV-22 diff: empty;
  - `git diff --name-only 45ad54ec 71be15fd` → 3 docs files.
- `PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends` → `1649 passed, 19 skipped in 147.43s (0:02:27)`.
- `pytest -rA` on the R-16, R-17 and R-8 cases → `17 passed, 28 deselected in 2.92s`.
- `scratchpad/s5-rereview-2/probe_table.py` (NativeTurnTable × GROK, MUSE, OPENCODE):
  - Grok and Muse: `busy(a) True busy(b) True`, `reserve(b): <host>.session_busy`, every end state `{}`;
  - opencode: `busy(b) False`, `reserve(b): ok`, end `{}`;
  - eviction: `finished 64 limit 64 busy {}`.
- `scratchpad/s5-rereview-2/ast_check.py . 1a9bc056 45ad54ec` → `files=43 code-differs=0 changed-docstrings=45`.
- Spec-id and width scans over `git diff origin/main...71be15fd -- 'vidbyte/*.py'` → `0`, `0`, `0`.
- The scrub probe gave the results listed under R-17, with no leak.
- `PYTHONDONTWRITEBYTECODE=1 python lint/run.py` → `A001 643 643 RATCHETED`, `A002 577 703 IMPROVED`, `SDK-LINT: PASS`.
- The §4 snippet (restricted PATH, empty home) → `grok.not_installed -> Install Grok Build 1.0.13 or newer, or set GrokHostSettings.grok_command.`, exit 0.
- `gh run view 38432650695` → `success` (3.11, 3.12, Package), headSha 45ad54ec; `gh run view 38432655274` → `success`.
- Host method count: OpencodeHost 18 plus the `mcp_servers` property, GrokHost 10, MuseHost 12.
- Never done: commits, `git add`, stash or installs. The real `grok`, `opencode`, `muse` and `wsl.exe` were never launched. All scratch files are under `scratchpad/s5-rereview-2/`.
