LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, layering, exports, prompts, and READMEs follow the house rules, but the PR re-implements an existing `vidbyte/lib/` helper four times, adds one A002 finding (562 → 563) and leaves the stall-stop hook without `@intent`, and misses spec §12.4's own 72-column check on 57 added comment lines. Two headers are also out of date.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- Placement and layering are correct. The five enums are in `vidbyte/lib/enums/browser.py` and exported. Every record is in `vidbyte/lib/dataclasses/browser.py`, with `UsageRollup` imported only under `TYPE_CHECKING`. The settings are in `vidbyte/agents/browser/settings.py` (exception 1). The registry imports `BrowserAgentRuntime` lazily. No file under `vidbyte/tools`, `vidbyte/middleware` or `vidbyte/cli` changes. Lint A006, S015 and C016 show no new findings.
- Every new production module carries the full A001 header. Every comment line the PR adds under `vidbyte/agents/browser/` and `vidbyte/lib/*/browser.py` is ≤ 72 columns. The validation-bound constants (`BROWSER_FIRST_INDEX`, `BROWSER_MIN_COUNT`, and the caps) follow `strict-config-dataclasses.md`, which asks for "each validation comparison should reference the feature's constants module". Do not inline them back.
- The prompt family follows `prompt-families.md` and `model-facing-tool-contracts.md`: no digits in any leaf, tool and parameter descriptions of 4–5 sentences, and no `format(max_`. The header in `vidbyte/lib/enums/prompts.py` says "158 assets across 36 families", and the recount matches.
- The non-code actions of §12.5 are all done. The folder README has `## File Index`, which matches the 10 modules plus the README (S020), and `## Notes for agents`. The README sizes are 9,798 (browser), 31,986 (agents) and 33,924 (prompts) characters, all ≤ 40,000 (A009). The commits are conventional, each tagged with W-/FR-/AC- IDs and the Co-Authored-By trailer.

FINDINGS (ranked, most severe first, max 15)
R-V1 [Major] [AGENTS.md principle 5] vidbyte/agents/browser/goal.py:118 — BrowserAgent re-implements `OutputText.single_line` from `vidbyte/lib/` inline at four call sites
  Evidence: `vidbyte/lib/outputs/text.py:42-44` defines `def single_line(text: str, limit: int) -> str: """Collapse every run of whitespace, line breaks included, to one space, then cut to limit with no marker.""" return " ".join(text.split())[:limit]`. The PR writes the same expression inline at four sites:
    `goal.py:118   self._last_episode = " ".join(f"{result.index} {result.outcome.value}: {result.summary}".split())[:BROWSER_ITEM_MAX_CHARS]`
    `goal.py:140   gap = " ".join(payload.gap.split())[:BROWSER_ITEM_MAX_CHARS]`
    `goal.py:225   lines = (" ".join(item.split())[:BROWSER_ITEM_MAX_CHARS] for item in criteria)`
    `events.py:45  line = " ".join(detail.split())[:BROWSER_EVENT_DETAIL_MAX_CHARS]`
    A probe confirmed that `OutputText.single_line(s, n) == " ".join(s.split())[:n]` on 5,000 random whitespace-heavy strings.
  Failure: AGENTS.md principle 5 says: "Before you write logic like this, look in `vidbyte/lib/` for a helper that already does it … have every caller use that helper instead of re-implementing the job inline." Ten connectors already call this helper. A human reviewer would write: "We have `OutputText.single_line` for exactly this; please don't hand-roll it four times." I rate this Major, not Blocker, for one reason: the helper's header scopes it to connectors ("Add a helper here only when two or more connectors need the same text transform"), so the PR's author could reasonably have missed it.
  Smallest fix: Replace the four expressions with `OutputText.single_line(<text>, <cap>)`. The import from `vidbyte.lib.outputs.text` is a downward import. Widen the ROLE IN CODEBASE line of `vidbyte/lib/outputs/text.py` to name BrowserAgent as a caller.
  Spec IDs: FR-17, FR-12 (the card and event texts); n/a for the rule

R-V2 [Major] [A002 / spec §12.4] vidbyte/agents/browser/agent.py:91 — the PR raises A002 from 562 to 563, and the stall-rule hook has no `@intent`
  Evidence: The lint run shows that A002 is the only rule whose count changes against the merge base. The new finding is `{"path": "vidbyte/agents/browser/agent.py", "line": 91, "symbol": "_runtime_extension_kwargs", "extra": {"categories": "external boundaries"}}`. The method opens with `# Hands the settings, the role map, the live servers, the` (agent.py:92) and has no `# @intent` marker. Separately, `runtime.py:179 def _budget_stop(...)` holds the stall stop (`if self.goal.stalled(): … stop_reason=AgentStopReason.GOAL_STALLED`), and its comment at :180-182 is a plain comment with no `# @intent`. A002's vocabulary does not match `_budget_stop`, so lint misses it, but §12.4 requires the marker.
  Failure: Spec §12.4 (spec.md:1029) says: "Every function that handles keys, a refusal, a cap, the stall rule, … has a `# @intent <name>` comment within 20 lines of its `def`. — *source:* A002". The lens counts a worsened rule as a finding even when the gate passes. A reviewer would write: "New A002 debt in a brand-new file, and the stall stop, the one policy that ends a run early, has no intent block."
  Smallest fix: Open agent.py:92 with `# @intent live-servers-are-handed-to-each-run`, keeping the existing lines. Open runtime.py:180 with `# @intent a-stalled-run-stops-before-its-next-model-call`, keeping the existing three lines. A002 should then read 562 again.
  Spec IDs: FR-14, AC-15, D-14

R-V3 [Major] [field guide comment-format.md / spec §12.4] vidbyte/agents/base.py:81 — 57 comment lines the PR adds are wider than 72 columns, so the §12.4 check fails on the touched files
  Evidence: I ran `git diff -U0 08f67e7f 3f9e63c9 -- '*.py'` through an awk filter that counts added `#` lines over 72 columns. The counts by file are: 16 in browser_agent_fixtures.py, 11 in test_browser_agent_episode.py, 7 in test_browser_agent_settings.py, 6 in test_browser_agent_contract.py, 5 in test_browser_agent_goal.py, 4 in test_browser_agent_observability.py, 3 in test_browser_agent_rebuild.py, 1 in test_browser_agent_acceptance.py, and 2 in `vidbyte/agents/base.py`. Line 81 of base.py is 95 columns (`# fallback, and session-failure wiring. JEV is the opinionated JevAgent's linear-loop subclass,`) and line 82 is 74. One test example is `browser_agent_fixtures.py: 118: # What every fake reply reports as its model: priced, so the agent's fail-closed usage set…`. The S3 report (S3-implementer.md:56) says "No comment line is over 72 columns". That holds only for `vidbyte/agents/browser/`.
  Failure: comment-format.md's Check says "`awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched". Spec §12.4 repeats that line verbatim as a checklist item. The entry records the owner rejecting wide blocks: "stop writing comments like this". A reviewer would point at the base.py edit and the test pack. I rate this Major, not Blocker, because the entry says "Not a lint rule", and the prior Infinite test pack also has 65 wide comment lines.
  Smallest fix: Rewrap the three-line block at base.py:80-82, which the PR rewrote, to 72 columns. Rewrap the 55 added test comment lines. The `# ---- section` rulers can simply be shortened.
  Spec IDs: n/a (§12.4 checklist)

R-V4 [Minor] [agentic-engineering: headers accurate] vidbyte/agents/browser/settings.py:6 — two module headers describe code that is not there
  Evidence: settings.py:6 says `FUNCTION INVENTORY: BrowserServerSettings.__post_init__ and BrowserAgentSettings.__post_init__ are narrated main functions with no private helpers.`, but settings.py:237-238 defines `@staticmethod def _require_distinct_servers(roles: Mapping[str, tuple[BrowserServerSettings, ...]]) -> None:`. Separately, `vidbyte/lib/dataclasses/browser.py:5` says "only the progress total is checked here by hand", but :66-67 also hand-raises `if not self.done_when: raise ConfigurationError("BrowserGoalCard.done_when must hold at least one criterion; …")`.
  Failure: A001 headers are what the next agent reads first. AGENTS.md says the map "answers *where do I look next*". A false "no private helpers" sends a maintainer to the wrong place for the duplicate-server rule. A reviewer would write: "Header says no helpers; there is one."
  Smallest fix: settings.py:6 should name `_require_distinct_servers` as BrowserAgentSettings' one helper. dataclasses/browser.py:5 should read "only the done_when minimum and the progress total are checked here by hand".
  Spec IDs: n/a (§12.4 A001 item)

R-V5 [Minor] [scope-adding] [field guide strict-config-dataclasses.md] vidbyte/lib/dataclasses/browser.py:79 — two hand-written checks stand where the field guide says to add a validator option
  Evidence: Lines 79-81 read `total = sum(len(item) for item in self.progress)` / `if total > BROWSER_PROGRESS_MAX_CHARS: raise ConfigurationError(...)`. Lines 66-67 read `if not self.done_when: raise ConfigurationError(...)`. `validation.py:65` shows that `require_text_items(value, field_name, *, max_items=None, max_chars=None, pattern=None, one_line=False)` has no minimum-items option and no total-size option. The header admits "because the validators have no total-size option".
  Failure: strict-config-dataclasses.md:61-63 says: "Validate record fields through RecordFieldValidator / RecordFieldConverter; add an option rather than a private field helper … When an option is missing …, add it as a keyword with a backward-compatible default." The checks are inline rather than in a private helper, and the Infinite records carry the same `done_when` precedent, so this is Minor. The fix also touches `validation.py`, which §12.3 does not list, so it is scope-adding.
  Smallest fix: Add `min_items: int | None = None` and `max_total_chars: int | None = None` to `require_text_items`, after checking the callers in `vidbyte/harnesses/native/*`. Replace the two hand-written blocks with those options, keeping both field names in the messages so AC-32's `progress_full` mapping still applies.
  Spec IDs: AC-32, EC-37

R-V6 [Minor] [§12.5 REPO_MAP row] REPO_MAP.md:87 — the new `vidbyte/agents/browser/` entry breaks the alphabetical order of its siblings
  Evidence: `git show 3f9e63c9:REPO_MAP.md | grep -n "^##### vidbyte/agents/"` prints algorithms :75, contracts :79, infinite :83, browser :87, jev :91, multi :95, output :99, pricing :103, runtimes :107, settings :111, skills :115. Every other entry is alphabetical.
  Failure: AGENTS.md says to read REPO_MAP before placing code. An agent that scans an alphabetical list for `browser` finds it out of position. A reviewer would ask for it to be moved.
  Smallest fix: Move the four-line `##### vidbyte/agents/browser/` block to sit between `algorithms` (:75) and `contracts` (:79).
  Spec IDs: n/a (§12.5)

R-V7 [Minor] [house style] vidbyte/agents/browser/goal.py:99 — `patch` dispatches on BrowserGoalSection with an if/elif ladder whose bare `else` falls through to BLOCKERS
  Evidence: `if chosen is BrowserGoalSection.PROGRESS: … elif chosen is BrowserGoalSection.PLAN: … else: card = replace(self._card, blockers=text)` (goal.py:99-105).
  Failure: Today the enum has exactly three members, so behavior is correct. The house idiom for closed-enum dispatch is a `match` with one `case` per member (AGENTS.md: "one case in the `match` in `JevPreflightGate.pass_()`"). Under the current ladder, a fourth section member would silently overwrite the blockers. A reviewer would ask for `match chosen:` with explicit cases.
  Smallest fix: Replace the ladder with `match chosen:` and cases for `PROGRESS`, `PLAN` and `BLOCKERS`. Behavior does not change.
  Spec IDs: FR-10

R-V8 [Minor] [principle 2 readability] vidbyte/agents/browser/episode.py:176 — dense one-line comprehensions, and the same filter written twice
  Evidence: :176 reads `facts, urls, evidence = (tuple(item for item in (value.strip()[:BROWSER_ITEM_MAX_CHARS] for value in values) if item)[:BROWSER_MAX_ITEMS] for values in (payload.facts, payload.urls, payload.evidence))`. :177 and :200 repeat `[context for context in reply.metadata.get("tool_calls", ()) if context.tool_name != IS_DONE_TOOL_NAME]`. The same style appears in tools.py:38-39 and :47, and settings.py:251 (`key, label = (("preset", preset), preset) if preset else (("command", server.command), cast("tuple[str, ...]", server.command)[0])`).
  Failure: AGENTS.md principle 2 says "a reader should be able to follow the whole feature by reading only the comments" and should not have to decode nested generators. The repeated filter is the action count that the episode cap and the stuck card both rely on, so the two copies can drift apart.
  Smallest fix: In `execute` (the main function), compute the non-`isDone` calls once and pass them to the card builder and to `_stuck`. Calling a shared helper from both would break principle 1. Split :176 into a short loop over the three fields.
  Spec IDs: FR-7, FR-16, AC-9

VERIFIED CLAIMS:
- The S3 report claims "No comment line is over 72 columns". This holds for `vidbyte/agents/browser/` and `vidbyte/lib/*/browser.py`. It does not hold for the touched files: 55 test lines and 2 in base.py (R-V3).
- The lint gate passes, with exit 0 on both the branch and the merge base. Only A002 changes, from 562 to 563. S051 stays at 259: the `runtimes.py:33` I001 finding was present at base, on the infinite import. This held.
- An A007 probe that swapped `BROWSER_FIRST_INDEX` and `BROWSER_MIN_COUNT` for literals adds no A007 findings. The constants are therefore not needed for A007, but they are justified by the constants rule in strict-config-dataclasses.md. This is not a finding.
- `vidbyte/lib/enums/prompts.py` says "158 assets across 36 families", and the recount matches. This held.
- The README sizes are browser 9,798, agents 31,986 and prompts 33,924, all ≤ 40,000. The browser File Index matches the folder's files. This held.
- `ruff check` with `lint/ruff.toml` on the new modules prints "All checks passed!". `ruff format --check` would reformat `browser/settings.py`, but it would also reformat `infinite/settings.py` and `jev/settings.py`. Formatting is not a repo gate, so this is not a finding.
- The browser test pack passes: 106 passed.
- §12.4 says "no `try` inside a `for` in a main function". This held. The one awk hit, at settings.py:114, is after the loop ends at :111.
- `OutputText.single_line` equals the inline idiom on 5,000 random inputs (R-V1).
- `vidbyte` resolves to the worktree: `inspect.getfile(vidbyte)` points to `…\worktrees\vidbyte-sdk-browser-agent\vidbyte\__init__.py`. This held.

COMMANDS RUN: (all from the worktree root; provider keys unset; `PYTHONPATH=$(pwd)`)
- `python -m pytest tests/features/browser_agent -q -p no:cacheprovider` → `106 passed in 1.58s`
- `python -m ruff check vidbyte/agents/browser vidbyte/lib/constants/browser.py vidbyte/lib/dataclasses/browser.py vidbyte/lib/enums/browser.py --config lint/ruff.toml --no-cache` → `All checks passed!`
- `python -m ruff format --check vidbyte/agents/infinite/settings.py vidbyte/agents/jev/settings.py --config lint/ruff.toml` → `2 files would be reformatted` (shows that formatting is not a gate)
- `python lint/run.py --all --json` on the branch, and a scratch `git archive 08f67e7f` copy linted via `run_base_lint.py` (tracked-path list from `git ls-tree`) → exit 0 on both. A002 562 → 563 (`vidbyte/agents/browser/agent.py:91 _runtime_extension_kwargs`). No other rule count changed.
- `a007_probe.py` (literal substitution in events.py, runtime.py, tools.py and dataclasses/browser.py) → no new A007 findings
- `git diff -U0 08f67e7f 3f9e63c9 -- '*.py' | awk '<added # lines over 72>'` → 57 lines across 8 test files and base.py (counts in R-V3)
- `git show 3f9e63c9:REPO_MAP.md | grep -n "^##### vidbyte/agents/"` → browser at :87, between infinite and jev
- `python -c "OutputText.single_line vs ' '.join(s.split())[:n] on 5000 cases"` → `equivalent on 5000 random cases`
- `git log --format='%h %s' 08f67e7f..3f9e63c9` → 41 commits: 23 code and README commits, each tagged with spec IDs (17 feat, 3 test, 1 chore, 2 docs), plus 18 pipeline `docs(spec)` commits
