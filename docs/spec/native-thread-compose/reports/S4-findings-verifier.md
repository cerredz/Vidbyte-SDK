# S4 findings verifier: native-thread-compose

**Stage and status:** S4 findings verifier, DONE.

**Commits:** none. The worktree HEAD is `0f9e66d1`, code-identical to the reviewed `e1bf20d8`.

**Inputs:** the diff `origin/feat/native-grok-opencode-meta-hosts...e1bf20d8`, and the three reviews:
- `reports/S4-review-conformance.md` (R-C1 to R-C6)
- `reports/S4-review-conventions.md` (R-V1 to R-V12)
- `reports/S4-review-engineering.md` (R-E1 to R-E8)

**Outputs:**
- `docs/spec/native-thread-compose/review.md`
- this report

## 0. Result

**Verdict: MERGEABLE AFTER FIXES.**

| Tier | Total | Repairable | Test-pack |
|---|---|---|---|
| Blocker | 11 | 10 | 1 |
| Major | 6 | 4 | 2 |
| Minor | 14 | – | – |

- **Refuted:** 2. R-C4's behavior claim, and R-V5's derived caps.
- **Downgraded to Minor:** 3. R-V1's callable checks, R-V2's `read`/`_roles`, and R-E4's blank path.
- **Tier moves with stated reasons:** 2. R-C2 goes from Blocker to Major; R-C3/R-E6 goes from Major to Blocker.
- **[verifier] additions:** 3, each merged into a confirmed row.
  - `bind_continue` thread id leaking the key (in R-3).
  - The EC-19 add-path orphan (in R-10).
  - A lone surrogate in the caller's prompt (in R-12).
- **Candidate fixes validated in scratch** (§6), each loaded as a plugin:
  - the fixes for R-10, R-12, R-13 and R-14 cleared their reproducers;
  - each kept the frozen pack at 276 passed, as did the three cleanup plugins loaded together;
  - R-3, R-8 and R-15 were not monkeypatched, and §6 says why.

## 1. Method

### Sources read
- The three reviews, in full.
- The spec r4 clauses each finding cites, in the spec's own words (quoted below).
- request.md §B (the ledger) and §D (the weighted words).
- The test plan's "not written" rows, and S3's open items.
- AGENTS.md.
- The field-guide entries the conventions review cites: `strict-config-dataclasses.md`, `blocking-lint-invariants.md` (A007) and `comment-format.md`.

### Reproduce first
Every Blocker and Major has a reproducer I ran myself. All of them run on win32 under Python 3.11.0, against the real git.
- **Scratch pytest probes:** `$S/test_s4v_probes.py`. They use the pack's own conftest fixtures: real git, sandboxed TMP and HOME, and stand-ins on PATH.
- **A throwaway-repository script:** `$S/probe_locked.py`.
- **Mutation plugins:** `$S/s4v_mut_gather.py` and `$S/s4v_mut_nocancel.py`.
- **An AST call-chain check:** `$S/chain_check.py`.
- **Lint, ruff, and grep.**

Path variables used below:
- `S` is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s4-verifier`.
- `E` is the sibling `s4-engineering` folder.

The probe command, run from the worktree root, is:

```
PYTHONPATH="$(pwd);$S" python -m pytest -q -s -p no:cacheprovider -W ignore::pytest.PytestDeprecationWarning -p tests.features.harness_compose.conftest "$S/test_s4v_probes.py" -k <selection>
```

Below, `probe -k X` stands for that command.

"CALL n" names the numbered command in `$S/transcript-commands-full.txt`. That file holds every command this stage ran, with its full output, extracted from the session transcript by `$S/extract_outputs.py`. Every fenced output block below is copied from it or from a saved log. `$S/check_quotes.py` checks this mechanically: every fenced line, and every quoted pytest tally, must appear verbatim in those records (§10).

### Reviewers' reproducers
I re-ran these myself and quote my own output:
- engineering `-k anyio_cancel_scope_planner`;
- engineering `-k blank_path`;
- engineering's `fix_settle` and `fix_planner_isolated`, loaded only as `-p` plugins.

### Fixes never touch the worktree
Every candidate fix was loaded only as a scratch `-p` plugin, or through `patch()` from a scratch probe.

### Calibration rule
A finding is a **Blocker** when any of these holds:
- (a) **The effect is unsafe** on a path the spec anticipates (an EC row, an INV, or the documented API). Unsafe means:
  - a secret reaches a message;
  - paid-for answers or thread ids are lost;
  - folders or processes outlive the call.
- (b) **A request.md §D weighted word is broken as written** on such a path.
- (c) **AGENTS.md or a field-guide lesson is contradicted as written**, rather than under a reviewer's broader reading.
- (d) **A test cannot fail.**

A finding is a **Major** when it is a real gap with a contained effect and either:
- its trigger lies outside the spec's anticipated inputs, or
- it needs a narrow timing window.

A missing test is also a Major.

A finding is a **Minor** when it is about clarity or consistency, or needs a spec ruling before any repair.

Spec text such as INV-18's "never" is binding, but it is not a §D weighted word. Where a reviewer tagged spec text as a weighted word, I corrected the tag.

## 2. Merge map

| Original | Lens | Original severity | Merged into | Final | Disposition |
|---|---|---|---|---|---|
| R-C1 | conformance | Blocker | R-8 | Blocker | Confirmed; merged with R-E7 (same root: verify.py:141-143 and the fan_out discard) |
| R-C2 | conformance | Blocker | R-13 | Major | Confirmed; tier lowered (§5) |
| R-C3 | conformance | Major | R-3 (source), R-17 (test-pack) | Blocker / Major | Confirmed; merged with R-E6; tier raised; split into source and test halves |
| R-C4 | conformance | Minor | R-18 | Minor (trivial) | Behavior claim refuted by the spec text; the header wording passes through |
| R-C5 | conformance | Minor | R-1 | Blocker | Confirmed; merged with R-V3, keeping the highest proposed severity |
| R-C6 | conformance | Minor | R-19 | Minor (trivial) | Passed through |
| R-V1 | conventions | Blocker | R-7, R-27 | Blocker / Minor | Counts, `counted` and blank items confirmed; callable checks downgraded |
| R-V2 | conventions | Blocker | R-9, R-28 | Blocker / Minor | Segment frames confirmed; `read` and `_roles` downgraded |
| R-V3 | conventions | Blocker | R-1 | Blocker | Confirmed (merged with R-C5) |
| R-V4 | conventions | Blocker | R-5 | Blocker | Confirmed |
| R-V5 | conventions | Blocker | R-2 | Blocker | Floors confirmed; derived caps refuted |
| R-V6 | conventions | Blocker | R-4 | Blocker | Confirmed |
| R-V7 | conventions | Blocker | R-6 (source), R-11 (test-pack) | Blocker | Confirmed; split into source and test halves |
| R-V8 | conventions | Minor | R-20 | Minor (trivial) | Passed through |
| R-V9 | conventions | Minor | R-21 | Minor (trivial) | Passed through |
| R-V10 | conventions | Minor | R-22 | Minor (trivial) | Passed through |
| R-V11 | conventions | Minor | R-23 | Minor (trivial) | Passed through |
| R-V12 | conventions | Minor | R-24 | Minor (follow-up) | Passed through |
| R-E1 | engineering | Blocker | R-10 | Blocker | Confirmed; [verifier] add-path orphan merged in |
| R-E2 | engineering | Major | R-14 | Major | Confirmed; the reviewer's fix replaced, because it breaks a frozen test |
| R-E3 | engineering | Major | R-12 | Major | Confirmed; [verifier] caller-prompt variant merged in |
| R-E4 | engineering | Major | R-15, R-26 | Major / Minor | Skills half confirmed; blank-path half downgraded (needs a spec ruling) |
| R-E5 | engineering | Major | R-16 | Major (test-pack) | Confirmed |
| R-E6 | engineering | Major | R-3 | Blocker | Confirmed; merged with R-C3; tier raised |
| R-E7 | engineering | Major | R-8 | Blocker | Confirmed; merged with R-C1, keeping the highest proposed severity |
| R-E8 | engineering | Minor [scope-adding] | R-25 | Minor (follow-up) | Passed through; not built |
| base follow-ups noted by R-C3, R-E3 and R-E1 | – | – | R-29, R-30, R-31 | Minor (follow-up) | Outside this diff (NG-1, spec §14) |
| [verifier] steps.py:82 key quote | – | – | R-3 | Blocker | Added |
| [verifier] EC-19 add-path orphan | – | – | R-10 | Blocker | Added |
| [verifier] lone surrogate in the caller's prompt | – | – | R-12 | Major | Added |

## 3. Verification of every Blocker and Major

### R-1: a model-addressed sentence in Python (R-C5 + R-V3). CONFIRMED, Blocker.

**Rule.** Ledger 10 is a §D weighted word: "every sentence addressed to a model lives in a `prompts/*.md` file loaded by a small library module". INV-20 says: "Every text compose sends to a model comes from the 22 Markdown files in the compose `prompts` folder."

**Code.** `vidbyte/lib/constants/native_compose.py:277` reads:

```
COMPOSE_TRUNCATED_PROBLEM = "The answer was cut at the length limit, so it was not read. Answer again with a shorter JSON object."
```

`vidbyte/harnesses/native/compose/answers.py:125` (`return None, native_compose.COMPOSE_TRUNCATED_PROBLEM`) returns it as the problem. `json_repair.md` then sends it to the model as `{problem}`.

**Guard check.**
- No other `*_PROBLEM` constant gives an instruction.
- `test_harness_compose_answers.py:157` reads the constant through `pack.longest_literal`, so the fix is test-safe.

**Tier.** Conformance rated it Minor and conventions rated it Blocker. The merge keeps Blocker, and so does my own rule: (b) and (c) apply.

### R-2: literal validator floors (R-V5, floors only). CONFIRMED, Blocker.

**Rule as written.** `field-guide/vidbyte-sdk/blocking-lint-invariants.md`, entry "A007 flags `read(CAP + 1)` and literal validator bounds; … name every bound":

> For a validator, name the floor next to its cap in `vidbyte/lib/constants/<domain>.py` (`CLAUDE_MAX_TURNS_MIN` beside `CLAUDE_MAX_TURNS_LIMIT`), even when the floor is `1`.

The diff contradicts the rule as written.

**Sites** (grep output):
- `verify.py:104` `StepRoles.counted(verifiers, …, minimum=1, maximum=native_compose.COMPOSE_MAX_VERIFIERS)`
- `stages.py:96` `minimum=1, maximum=native_compose.COMPOSE_MAX_STAGES`
- `native_ensemble.py:110` `min(kept) < 1`
- `native_ensemble.py:126` `require_int(self.proposal, …, minimum=1, maximum=ENSEMBLE_MAX_PROPOSERS)`
- `native_compose.py:308` `minimum=0, maximum=STAGE_MAX_RETRIES`
- `native_compose.py:321` `minimum=0, maximum=STAGE_MAX_LADDER`
- `native_ensemble.py:95`, whose message reads "must hold 1 to {ENSEMBLE_MAX_PROPOSERS}" although `ENSEMBLE_MIN_PROPOSERS = 1` exists at `constants/native_compose.py:39`

**Why lint is silent.** The lint run reports `A007   operational-constants   255   255 RATCHETED`, because `OPERATIONAL_TOKENS` (`lint/rules/a007_operational_constants.py:23-38`) holds only `timeout, retry, attempt, backoff, delay, token, char, byte, truncate, limit, budget, status, depth, interval`.

**Static policy.** The INV-15 static policy (`tests/features/harness_threads/test_harness_threads_static_policy.py:24`, `ALLOWED_VALUES = ("", 0, 1)`) allows `0` and `1` under `vidbyte/harnesses/native/` but does not require them. Named floors satisfy both rules; the policy passes today (`3 passed in 0.19s`).

**Refuted part.** The derived caps (`native_compose.py:193` `max_items=1 + COMPOSE_JSON_REPAIR_TURNS`, `:334` `1 + STAGE_MAX_RETRIES`) are the spec's own definitions:
- §9.1: "`turns` holds 1 to 1 + `COMPOSE_JSON_REPAIR_TURNS` outcomes" and "at most 1 + `STAGE_MAX_RETRIES` attempts".
- A-7: "every bound on turns derives from that one constant".

Treating the derived caps as a violation is a broader reading than the lesson's text.

### R-3: a key quoted in compose's own ConfigurationError (R-C3 + R-E6 + [verifier]). CONFIRMED, Blocker (raised from Major).

**Spec.**
- INV-4: "It never appears in any text compose itself produces: … any `ConfigurationError` compose raises".
- INV-5 (spec.md:269): "A refusal is a `ConfigurationError` whose `details["field"]` names the argument path and whose message never quotes a key."
- Ledger 3, a §D weighted word: "The key is still passed only to the nine functions and still never reaches argv, files, `os.environ`, error messages or logs."
- T-3 lists "error text" as a threat.

**Mechanism.** `RecordFieldValidator._received` (`validation.py:159-167`) quotes any `str` whose repr is at most `NATIVE_QUOTED_VALUE_MAX_CHARS` (80), unless the field name reads as a credential. The compose call sites are `answers.py:57`, `answers.py:58`, `chain.py:46`, `chain.py:106`, `ensemble.py:54`, `stages.py:103`, `steps.py:82` and `verify.py:51`. A grep of every `require_text(` in compose lists exactly these 8.

**Reproduction.** `probe -k "blank or key_in"` (CALL 111). These are the key lines, verbatim; the BLANK lines of the same run are quoted under R-13. The keys are test dummies: a 49-character Zhipu-shaped key and a 12-character key.

```
KEY[49] chain prompt: ConfigurationError key-in-message=True key-in-details=False | "prompt must match [^\\x00]+; got 'use 0123456789abcdef0123456789abcdef.AbCdEfGhIjKlMnOp\\x00'."
KEY[49] chain template: ConfigurationError key-in-message=True key-in-details=False | "template must match [^\\x00]+; got '{previous} 0123456789abcdef0123456789abcdef.AbCdEfGhIjKlMnOp\\x00'."
KEY[49] verify prompt: ConfigurationError key-in-message=True key-in-details=False | "prompt must match [^\\x00]+; got 'use 0123456789abcdef0123456789abcdef.AbCdEfGhIjKlMnOp\\x00'."
KEY[49] staged template: ConfigurationError key-in-message=True key-in-details=False | "stages[0].template must match [^\\x00]+; got 'use 0123456789abcdef0123456789abcdef.AbCdEfGhIjKlMnOp\\x00'."
KEY[49] ensemble task: ConfigurationError key-in-message=True key-in-details=False | "prompt must match [^\\x00]+; got 'use 0123456789abcdef0123456789abcdef.AbCdEfGhIjKlMnOp\\x00'."
KEY[49] parse_json_answer prompt: ConfigurationError key-in-message=True key-in-details=False | "prompt must match [^\\x00]+; got 'use 0123456789abcdef0123456789abcdef.AbCdEfGhIjKlMnOp\\x00'."
KEY[49] launches=0
KEY[49] BASE run_opencode_thread: NativeThreadError key-in-message=True
KEY[12] chain prompt: ConfigurationError key-in-message=True key-in-details=False | "prompt must match [^\\x00]+; got 'use vbk-s4v-7a1c\\x00'."
KEY[12] chain template: ConfigurationError key-in-message=True key-in-details=False | "template must match [^\\x00]+; got '{previous} vbk-s4v-7a1c\\x00'."
KEY[12] verify prompt: ConfigurationError key-in-message=True key-in-details=False | "prompt must match [^\\x00]+; got 'use vbk-s4v-7a1c\\x00'."
KEY[12] staged template: ConfigurationError key-in-message=True key-in-details=False | "stages[0].template must match [^\\x00]+; got 'use vbk-s4v-7a1c\\x00'."
KEY[12] ensemble task: ConfigurationError key-in-message=True key-in-details=False | "prompt must match [^\\x00]+; got 'use vbk-s4v-7a1c\\x00'."
KEY[12] parse_json_answer prompt: ConfigurationError key-in-message=True key-in-details=False | "prompt must match [^\\x00]+; got 'use vbk-s4v-7a1c\\x00'."
KEY[12] launches=0
KEY[12] BASE run_opencode_thread: NativeThreadError key-in-message=True
4 passed, 14 deselected in 14.08s
```

**[verifier] addition.** `probe -k bind_refusals` (CALL 150):

```
BIND bind_thread model: accepted
BIND bind_continue thread_id: ConfigurationError key-in-message=True | "thread_id must match ^[A-Za-z0-9][A-Za-z0-9_-]*$; got '0123456789abcdef0123456789abcdef.AbCdEfGhIjKlMnOp\\x00'."
BIND bind_thread workspace: ConfigurationError key-in-message=False | 'workspace must be an absolute path to an existing directory; got a value of type WindowsPath that is not one.'
1 passed, 22 deselected in 13.98s
```

**Reachability.** The key reaches the message only through the caller's own invalid text, and only when the repr is at most 80 characters. That is true of Zhipu-shaped keys (49 characters), and of any short dummy key used with a local opencode provider. A typical xAI key is too long to be quoted.

**Scope (INV-4 r3).** The `ConfigurationError` is text compose itself produces, so it is in scope. The base functions quote keys the same way (the `BASE` line above), but that is outside this PR: Minor R-29, follow-up.

**Test pins.** A grep of `tests/` for `must match`, `got '` or `got "` finds nothing. The only exact validator message any test pins is the units message at `test_harness_compose_validation.py:244-245`, which this fix does not touch. So neither fix below breaks a test, and neither changes what the base functions raise:
- `quote: bool = True` on `require_text`, with `quote=False` at the 8 sites (the default keeps every other caller's message as it is);
- or `accepts_text` plus a compose-owned refusal.

**Why the tier is raised.** Both reviewers kept it at Major, citing narrowness and base parity. I reject base parity as a reason: the orchestrator's INV-4 r3 scope includes every `ConfigurationError` compose raises, and the base is out of scope. Ledger 3 is the owner's weighted word, and the effect is a credential in an exception message, which may be logged. Rules (a) and (b) both apply.

### R-4: a two-level call chain in ComposeGit (R-V6). CONFIRMED, Blocker.

**Rule as written.** AGENTS.md principle 1:

> Inside a class, or a module of plain functions, a function may call another of its own functions, but that second function should not call a third. … When a helper starts to need another helper, lift that call up into the main function … Calls out to another class, a lower layer, or the standard library do not count toward this limit.

The diff contradicts the rule as written.

**Evidence.** `python $S/chain_check.py vidbyte/harnesses/native/compose/*.py vidbyte/lib/dataclasses/native_compose.py vidbyte/lib/dataclasses/native_ensemble.py vidbyte/lib/util/json_text.py vidbyte/lib/dataclasses/validation.py` prints:

```
vidbyte/harnesses/native/compose/git.py: ComposeGit.add_worktree -> remove_worktree -> ['_delete', '_failure', '_run']
checked 17 files
```

At `git.py:170-175` the except path runs `await asyncio.shield(asyncio.ensure_future(self.remove_worktree(folder)))`. `remove_worktree` (`:185-193`) calls `self._run`, `self._delete` and `self._failure`. The only caller of `add_worktree` is `workspace.py:113`, so lifting the cleanup into `DisposableWorktree.__aenter__` (another class) is local.

### R-5: the key scrub written three times (R-V4). CONFIRMED, Blocker.

**Rule as written.** AGENTS.md principle 5:

> Before you write logic like this, look in `vidbyte/lib/` for a helper that already does it … If none exists, create the helper in `vidbyte/lib/` rather than inside the feature that first needs it … whenever a canonical helper in `vidbyte/lib/` would save writing the same logic a second time, build it that way.

The diff contradicts the rule as written.

**Evidence.** The grep finds:

```
vidbyte/harnesses/native/compose/git.py:45:        bound = sorted(set(keys), key=len, reverse=True)
vidbyte/harnesses/native/compose/git.py:75:            text = text.replace(key, native_compose.COMPOSE_REDACTED_KEY)
vidbyte/harnesses/native/compose/texts.py:114:        bound = sorted(set(keys), key=len, reverse=True)
vidbyte/harnesses/native/compose/texts.py:167:            text = text.replace(key, native_compose.COMPOSE_REDACTED_KEY)
vidbyte/harnesses/native/hostkit/errors.py:59:        for secret in sorted(self._secrets, key=len, reverse=True):
vidbyte/harnesses/native/hostkit/errors.py:60:            text = text.replace(secret, native_threads.NATIVE_REDACTED)
```

The same grep over the rest of `vidbyte/` finds nothing else, so no lib helper exists. The nearest existing helper does a different job. `HarnessRedactor` (`vidbyte/harnesses/serialization.py:65`) rewrites credential-shaped assignments by regex, not given key values, and texts.py's own header bars it: "Do not scrub with HarnessRedactor; it rewrites credential-like lines inside diffs, so keys are replaced as exact text (D-28)." The hostkit copy is private to `NativeErrorFactory`, and INV-32 says "Compose imports nothing from … `vidbyte.harnesses.native.hostkit`". An exact-text replacement needs nothing from above lib, so the helper belongs in lib, as principle 5 says.

**Budget caveat (§4.9).** A new lib file or class is a spec §14 "Ask first" item.

### R-6 and R-11: comment lines over 72 columns (R-V7). CONFIRMED, Blocker. R-6 is the source half; R-11 is the test-pack half.

**Rule as written.** `field-guide/vidbyte-sdk/comment-format.md`:

> Wrap every comment line at 72 columns, counting the indent … A single-line comment that would pass 72 columns becomes a wrapped block too.

Its Check is: "`awk 'length($0) > 72' <file> | grep -E '^\s*#'` prints nothing for the files you touched."

The diff contradicts the rule as written.

**Evidence.** The command:

```
for f in vidbyte/harnesses/native/compose/*.py vidbyte/lib/dataclasses/native_compose.py vidbyte/lib/dataclasses/native_ensemble.py vidbyte/lib/constants/native_compose.py vidbyte/lib/enums/native_compose.py vidbyte/lib/util/json_text.py; do n=$(awk 'length($0) > 72' "$f" | grep -cE '^[[:space:]]*#'); [ "$n" != "0" ] && echo "$f: $n"; done
```

Source output:

```
vidbyte/harnesses/native/compose/chain.py: 4
vidbyte/harnesses/native/compose/ensemble.py: 6
vidbyte/harnesses/native/compose/selection.py: 4
vidbyte/harnesses/native/compose/stages.py: 4
vidbyte/harnesses/native/compose/texts.py: 1
vidbyte/harnesses/native/compose/verify.py: 5
```

Tests output:

```
tests/features/harness_compose/conftest.py: 6
tests/features/harness_compose/test_harness_compose_answers.py: 4
tests/features/harness_compose/test_harness_compose_chain.py: 2
tests/features/harness_compose/test_harness_compose_git.py: 1
tests/features/harness_compose/test_harness_compose_handoff.py: 1
tests/features/harness_compose/test_harness_compose_prompts.py: 1
tests/features/harness_compose/test_harness_compose_stages.py: 1
tests/features/harness_compose/test_harness_compose_surface.py: 2
tests/features/harness_compose/test_harness_compose_validation.py: 3
tests/features/harness_compose/test_harness_compose_verify.py: 1
```

CALL 135 ran the same width check over only the added lines (`git diff -U0` per added or modified `.py` file, `+` lines only) and printed the files with a non-zero count. Only the new (`A`) files above appeared. No modified (`M`) file adds an over-wide comment line. The test half is in the frozen tree, so it is labeled `test-pack`.

### R-7: hand-written record checks (R-V1, counts and blank items). CONFIRMED, Blocker.

**Rule as written.** `field-guide/vidbyte-sdk/strict-config-dataclasses.md`, entry "Validate record fields through RecordFieldValidator / RecordFieldConverter; add an option rather than a private field helper":
- When: "A lib record's or settings object's `__post_init__` checks text, ints, enums, paths, or tuples, or a module grows `_text_field` / `_count_field`-style helpers."
- Do: "When an option is missing (no cap, one line, tuple items, folder resolution), add it as a keyword with a backward-compatible default."

**Evidence.** `grep -n "if not all(item.strip()\|if not turns:\|if not outcomes:\|if not stages:" vidbyte/lib/dataclasses/native_compose.py` and `grep -n "len(proposers) < ENSEMBLE_MIN_PROPOSERS\|if not roles:\|if not kept or" vidbyte/lib/dataclasses/native_ensemble.py` print:

```
144:        if not all(item.strip() for item in files):
194:        if not turns:
240:        if not outcomes:
360:        if not stages:
51:        if len(proposers) < ENSEMBLE_MIN_PROPOSERS:
94:        if not roles:
110:        if not kept or len(set(kept)) != len(kept) or min(kept) < 1:
```

`sed -n 141,146p vidbyte/harnesses/native/compose/steps.py` shows the private count helper:

```
    def counted(values: object, argument: str, *, minimum: int, maximum: int) -> tuple[object, ...]:
        """values as a tuple when it is a list or tuple of minimum to maximum items; refuse it naming argument otherwise."""
        items = RecordFieldConverter.to_tuple(values, argument, item_type=object)
        if not minimum <= len(items) <= maximum:
            raise ConfigurationError(native_compose.COMPOSE_COUNT_RULE.format(argument=argument, minimum=minimum, maximum=maximum, count=len(items)), details={native_threads.NATIVE_FIELD_DETAIL_KEY: argument})
        return items
```

`to_tuple` (`validation.py:174-182`) has `max_items` but no `min_items`. The header at `native_compose.py:5` claims: "Every check lives in __post_init__ and goes through RecordFieldValidator and RecordFieldConverter".

**What breaks the rule as written:**
- the tuple-count checks, because the option is missing and was not added;
- `counted`, a `_count_field`-style helper;
- the blank-text check on tuple items.

**Not covered by the rule as written:** the callable checks (`native_compose.py:87-90`). The rule lists "text, ints, enums, paths, or tuples", and spec §9.1 says "`function` is callable". `answers.py:55-56` checks a function argument, not a record field. These are downgraded to Minor R-27.

**Test pins.** No test pins the count wording; the validation tests assert `details["field"]`.

### R-8: EC-16 drops finished reader answers (R-C1 + R-E7). CONFIRMED, Blocker.

**Spec.**
- EC-16 expects `ThreadComposeError(WORKTREE_FAILED)` naming the folder, with "its `result` holds the record so far".
- D-26: "and then always with the record so far".
- Ledger 7, a §D weighted word: "Every composite result record carries every step's `NativeThreadResult` or its `NativeThreadError`, every thread id, and which step failed."
- The §17 deviation (spec.md:1586): "Several readers running at once (verifiers, proposers) give the record from before their stage, because the first failure cancels the others (D-17)."

**Code.** `verify.py:142-143` is `async with DisposableWorktree.from_tree(git, after, before) as folder: return await JsonAnswers.ask(...)`. The answer is lost when `__aexit__` raises. `fan_out` (`calls.py:81-90`) gathers its children and raises the failure, discarding the values of finished children. `verify.py:89-93` then attaches `record`, which is only `VerifyResult(writer=…)`.

**Reproduction.** `probe -k ec16` (CALL 110). A file is held open in the reader's worktree, against the real git:

```
EC16-1 problem=worktree_failed record=VerifyResult writer.ok=True verdicts=0
EC16-1 verifier answered=True session=ses_5ec8bf44-b5ed-4b57-bb8b-78bccbc1e570 session-in-record=False
EC16-1 message head: 'Compose failed with worktree_failed. Compose could not add, fill or remove the disposable worktree a reader runs in. The workspace was C:\\Users\\422mi\\'
EC16-2 fast finished first=True problem=worktree_failed verdicts=0 answered={'v-fast': True, 'v-slow': True}
EC16-2 sessions in record: {'v-fast': False, 'v-slow': False}
EC16-P problem=worktree_failed plan-kept=True proposals=0
EC16-P sessions in record: {'p-grok': False, 'p-oc': False}
3 passed, 15 deselected in 16.59s
```

**Why the §17 deviation does not cover this.** Its reason is that "the first failure cancels the others". In all three reproductions, no sibling was cancelled:
- the single-verifier case has no sibling;
- in EC16-2 both verifiers had answered;
- in EC16-P the Grok proposer had answered.

**Guard check.** The planner and selector already attach their answers (`ensemble.py:204-206`, `selection.py:93-98`), so the fix pattern exists in the diff. The fix is mirrored for readers. When a sibling really was cancelled before answering, positional `verdicts` cannot hold the gap, and a partial shape would be scope-adding, so the §17 behavior is kept for that case only.

### R-9: positional prompt-segment tuples (R-V2, segment frames). CONFIRMED, Blocker.

**Rule as written.** AGENTS.md principle 4:

> Functions that carry core business logic take a dataclass as input and return a dataclass as output, rather than loose dicts, tuples, or long lists of primitive arguments. … Small private helpers do not need dataclasses of their own; the rule is for the functions that hold a feature's real logic and for the data passed between layers.

`texts.py:102` is `async def fit(frame: Sequence[tuple[str, bool]], step: ThreadStep, keys: Iterable[str]) -> str:`. That is the INV-4/INV-18 scrub-and-cut logic, so the diff contradicts the rule as written.

**Evidence.**
- `grep -F -o 'tuple[str, bool]' vidbyte/harnesses/native/compose/*.py | wc -l` gives 35.
- The same grep with `-l` gives 7 files.
- Summing `-c` gives 27 lines.

**Downgraded part.** `AnswerDecoders.read` (`answers.py:118`) and `ThreadEnsembles._roles` (`ensemble.py:124`) are single-use helpers; principle 4 exempts small helpers (Minor R-28).

**Constraint on the fix.** `PromptSegment.text` must be type-checked only (§4.9).

### R-10: cleanup survives only one cancel (R-E1 + [verifier]). CONFIRMED, Blocker.

**Spec.**
- INV-14: "When the caller cancels, every running child is cancelled, the nine functions stop its process tree, its worktree is removed … No task outlives the composite call."
- INV-14, second bullet: "Compose waits until each sibling has stopped and removed its worktree, then that one exception propagates".
- EC-17: "No leftover registration or folder".

**Reproduction 1.** `probe -k "double_cancel or anyio"` (CALL 116), complete output. `gap=None` is the single-cancel control; `gap=0.05` sends a second cancel 50 ms after the first, three times:

```
R-E1 gap=None at return: worktrees=1 leftovers=0 pending=0 live_leaders=0 live_grandchildren=0
R-E1 gap=None after 6 s: worktrees=1 leftovers=0 pending=0 live_leaders=0 live_grandchildren=0
R-E1 gap=None killed survivors: []
R-E1 gap=0.05 at return: worktrees=1 leftovers=2 pending=0 live_leaders=0 live_grandchildren=2
R-E1 gap=0.05 after 6 s: worktrees=1 leftovers=2 pending=0 live_leaders=0 live_grandchildren=2
R-E1 gap=0.05 killed survivors: [5176, 6780]
R-E1 gap=0.05 at return: worktrees=1 leftovers=2 pending=0 live_leaders=0 live_grandchildren=2
R-E1 gap=0.05 after 6 s: worktrees=1 leftovers=2 pending=0 live_leaders=0 live_grandchildren=2
R-E1 gap=0.05 killed survivors: [28380, 1360]
R-E1 gap=0.05 at return: worktrees=1 leftovers=2 pending=0 live_leaders=0 live_grandchildren=2
R-E1 gap=0.05 after 6 s: worktrees=1 leftovers=2 pending=0 live_leaders=0 live_grandchildren=2
R-E1 gap=0.05 killed survivors: [33420, 31268]
R-E1 anyio caught=True at return: worktrees=3 leftovers=2 pending=4 live_leaders=0 live_grandchildren=2
R-E1 anyio after 6 s: worktrees=1 leftovers=2 pending=0 live_leaders=0 live_grandchildren=2
R-E1 anyio killed survivors: [19136, 32512]
5 passed, 13 deselected in 47.48s
```

**Reproduction 2.** Engineering's planner probe, re-run by me (CALL 225): `PYTHONPATH="$(pwd);$E" python -m pytest -q -s -p no:cacheprovider -W ignore::pytest.PytestDeprecationWarning -W ignore::pytest.PytestUnraisableExceptionWarning -p tests.features.harness_compose.conftest "$E/test_s4_probes.py" -k "anyio_cancel_scope_planner or blank_path"`, then `python $S/procs.py --kill`. The output was saved to `$S/planner-blank-unpatched.txt`:

```
blank path: RAISED ConfigurationError | WorkspaceDiff.files must hold non-blank paths.
.PLANNER: scope cancelled; at return: worktrees=2 leftovers=['vidbyte-compose-worktree-ksl6i6c2'] pending tasks=2 live leaders=0 live grandchildren=1
PLANNER: after everything settled: worktrees=1 leftovers=['vidbyte-compose-worktree-ksl6i6c2'] live=1
2 passed, 12 deselected in 21.18s
stand-in or grandchild processes: [24228] (killed)
```

**[verifier] addition: one cancel is enough on the add/enter failure path.** `await asyncio.shield(task)` protects the task but stops waiting when the awaiting code is cancelled. The except paths at `git.py:173-175` and `workspace.py:122-125` do not wait again, unlike `__aexit__` (`workspace.py:139-142`). When one sibling's worktree add fails (EC-19), `fan_out` cancels the other, which is inside its own shielded removal.

The `two_failing` probe was run twice unpatched: in CALL 120 (`-k "seam_grok or two_failing or orphan"`) and in the unpatched half of CALL 201 (`-k "two_failing or seam_grok"`). Both runs printed exactly:

```
TWO-ADDS at raise: worktrees=1 leftovers=[] pending=['CliRunner._drain', 'CliRunner._drain', 'ComposeGit.remove_worktree']
TWO-ADDS after 3 s: worktrees=1 leftovers=[] pending=[]
```

`probe -k orphan_removal` ran three times in a loop (CALL 126). Each run printed this line, followed by `1 passed, 21 deselected` (in 14.07 s, 14.03 s and 14.10 s):

```
SHUTDOWN pending at raise=['CliRunner._drain', 'CliRunner._drain', 'ComposeGit.remove_worktree'] -> after cancel: worktrees=1 leftovers=[] admin=[]
```

So 5 of 5 unpatched runs raised with the removal still pending.

So the composite raises while its removal still runs, which breaks INV-14's "No task outlives the composite call". On this setup the effect is contained: the orphan finishes on its own, or cleans up when the loop shuts down. Same root and same fix, so it is merged here.

**Validated fix.** See §6.
- Unpatched control: single cancel is clean.
- Patched with `fix_settle` (E), `fix_planner_isolated` (E) and `s4v_fix_add_settle` (S): every probe is clean and the pack stays at 276.

### R-12: lone surrogates (R-E3 + [verifier]). CONFIRMED, Major (kept).

**Invariants violated** (the orchestrator asked me to name them):
- **INV-15**, first sentence: "A composite returns its record whenever it got past validation and the git checks without a compose-owned failure, however many steps failed." With Grok or Muse next, the composite raises and the record of the steps that ran is lost; ledger 7 is lost with it. INV-15's raise list does include "a defect", so the crash is an allowed class of raise, but it is a defect in compose-owned code that loses a record INV-15 promises.
- **INV-18**, closing sentence ("A step therefore never fails … because of a spliced value"), and **INV-29** ("never sends a step a prompt the step would refuse"). With opencode next, the step fails with `runtime.error` because of a spliced value.
- **INV-5** ("A refusal is a `ConfigurationError`"), for the caller-prompt variant. The orphaned opencode process comes from the base runner (R-30); INV-30 covers only timeout and cancel.

**Reproduction.** `probe -k "lone_surrogate_next_step or orphan or caller_prompt"`, run unpatched (the first half of CALL 244; its second half loaded `-p s4v_fix_surrogate`, below):

```
R-E3 next=grok platform=win32: RAISED UnicodeEncodeError has-record=False | "'utf-16-le' codec can't encode character '\\ud83d' in position 136: surrogates not allowed"
R-E3 next=muse platform=win32: RAISED UnicodeEncodeError has-record=False | "'utf-16-le' codec can't encode character '\\ud83d' in position 136: surrogates not allowed"
R-E3 next=opencode platform=win32: RETURNED failed_step=1 second error=FailureCode.RUNTIME_ERROR
ORPHAN chain failed_step=1 code=FailureCode.RUNTIME_ERROR | 'run_opencode_thread failed with runtime.error. The SDK failed while driving opencode. The '
ORPHAN second-step processes right after return: [1228]
ORPHAN 2 s later: [1228] killed=[1228]
CALLER-LONE chain(grok first) on win32: UnicodeEncodeError | launches=0 | "'utf-16-le' codec can't encode character '\\ud83d' in position 8: surrogates not allowed"
6 passed, 18 deselected in 25.06s
```

Earlier runs gave the same: the three R-E3 lines in CALL 117 (`-k "lone or skill or hook"`), and the ORPHAN lines in CALL 120, with the orphan at pid 31188. In every run the orphaned opencode process was still alive 2 s after the composite returned, until the probe killed it.

**Why it stays Major.** No EC row anticipates lone surrogates; S3 open item 4 says "Whether a vendor CLI accepts them in argv is untested". POSIX behavior was not probed: engineering's `os.fsencode` claim comes from reading the CPython source.

**Validated fix.** In memory:
- `'answer \ud83d end'` becomes `'answer \ufffd end'` (12 characters before and after);
- `'\ud83d\ude00'` becomes `'\U0001f600'` (2 characters before, 1 after, equal to U+1F600).

End to end with `-p s4v_fix_surrogate` (the second half of CALL 244):

```
R-E3 next=grok platform=win32: RETURNED failed_step=None second error=None
R-E3 next=muse platform=win32: RETURNED failed_step=None second error=None
R-E3 next=opencode platform=win32: RETURNED failed_step=None second error=None
CALLER-LONE chain(grok first) on win32: UnicodeEncodeError | launches=0 | "'utf-16-le' codec can't encode character '\\ud83d' in position 8: surrogates not allowed"
>       print(f"\nORPHAN chain failed_step={result.failed_step} code={error.failure_code} | {str(error)[:90]!r}")
1 failed, 5 passed, 18 deselected in 21.11s
```

The one failure is in my probe's own print. Under the fix the opencode step succeeds, so `error` is `None` and `error.failure_code` raises. CALL 245 corrected the print with `$S/fix_orphan_print.py` and re-ran `-k orphan` under the fix:

```
ORPHAN chain failed_step=None code=None | 'None' | second ok=True
ORPHAN second-step processes right after return: []
ORPHAN 2 s later: [] killed=[]
2 passed, 22 deselected in 19.56s
```

The frozen pack under the fix gives `276 passed in 50.64s`. The caller-prompt variant (CALLER-LONE) still raises under the fix, as expected. It needs the separate refusal in `check`, because the scrub must not touch caller text (INV-4).

### R-13: a placeholder-only template yields a blank prompt (R-C2). CONFIRMED, Major (lowered from Blocker).

**Spec.**
- INV-18: "no NUL character, and not blank", and "A step therefore never fails with `configuration.invalid_argument` because of a spliced value".
- INV-29: "never sends a step a prompt the step would refuse".
- EC-37: "A spliced value contains NUL | The NUL characters are removed before sending … | The step runs".

**Reproduction.** These are the BLANK lines of `probe -k "blank or key_in"` (CALL 111); `-k blank_previous` selects this probe alone. The template is `"{previous}"`, and the first step answers three spaces, then two NULs:

```
BLANK chain answer='   ' first.ok=True first.text='   ' failed_step=1
BLANK chain second error=FailureCode.CONFIGURATION_INVALID_ARGUMENT | 'run_grok_thread failed with configuration.invalid_argument. The SDK refused an argument before starting Grok Build. The ' | second launched=0
BLANK staged failed_stage=1 last error=FailureCode.CONFIGURATION_INVALID_ARGUMENT | s-second launched=0
BLANK chain answer='\x00\x00' first.ok=True first.text='\x00\x00' failed_step=1
BLANK chain second error=FailureCode.CONFIGURATION_INVALID_ARGUMENT | 'run_grok_thread failed with configuration.invalid_argument. The SDK refused an argument before starting Grok Build. The ' | second launched=0
BLANK staged failed_stage=1 last error=FailureCode.CONFIGURATION_INVALID_ARGUMENT | s-second launched=0
```

**Code.** `PromptFitter.check` (`texts.py:88-99`) renders only `longest if spliced else text`. `fit` returns the share-0 `best` even when no candidate fits (`texts.py:131-140`). `chain.py:9` admits the gap.

**Guard check.** No frozen test uses a placeholder-only template that passes `require_template`. Every template the tests pass is listed by `grep -o "template=[^,)]*"` plus the chain calls. The only placeholder-only ones are `{previous!r}` and `{previous:>5}`, which `require_template` refuses first.

**Why the tier is lowered.**
- The failure is truthful, typed and recorded, and nothing is lost.
- INV-18, INV-29 and EC-37 are binding spec text, but not §D weighted words.
- The trigger needs a template made only of placeholders, which the caller chose; the default `chain_turn` template is unaffected.

It is still a real gap (Major), and the fix is local.

**Validated fix.** CALL 248 ran `probe -k blank_previous` with `-p s4v_fix_blank`. Both probe cases now stop with the refusal, raised from the wrapped `PromptFitter.check`:

```
E           vidbyte.lib.errors.base.ConfigurationError: template must hold text besides its placeholders, or steps[1] can be sent a blank prompt.
2 failed, 22 deselected in 13.43s
```

The "failed" is the intended outcome. The probe expects `chain_threads` to return, and under the fix it raises instead. `chain_threads` calls `_fit`, and so `check`, before `_gits` and before the first step (`chain.py:42-48`), so the refusal comes before any git process or step starts. The frozen pack under the fix gives `276 passed in 52.07s`.

### R-14: a cancel during `worktree add` leaves a locked registration (R-E2). CONFIRMED, Major (kept).

**Reproduction.** `PYTHONPATH=$(pwd) python -W ignore $S/probe_locked.py $S` builds a throwaway repository under the scratch folder. Its `reference-transaction` hook sleeps 3 s, which widens git's own window. The probe cancels `ComposeGit.add_worktree` while the hook runs. CALL 130 output, complete, with the scratch prefix written as `$S`:

```
git program: C:\Program Files\Git\mingw64\bin\git.EXE
[window] hook ran inside `worktree add`; lock files it saw: $S/s4v-locked-862vp6sl/repo/.git/worktrees/vidbyte-compose-worktree-im_exns5/locked: initializing
[cancel] add_worktree raised CancelledError (its own removal error, if any, was suppressed)
[after] admin entries (name, lock reason): [('vidbyte-compose-worktree-im_exns5', 'initializing')]
[after] worktree list: worktree $S/s4v-locked-862vp6sl/repo | worktree $S/s4v-locked-862vp6sl/tmp/vidbyte-compose-worktree-im_exns5 | locked initializing
[after] leftover folders in TMP: []
[prune -v] exit 0 out: (nothing pruned)
[after prune] admin entries: [('vidbyte-compose-worktree-im_exns5', 'initializing')]
[remove --force] 128 fatal: cannot remove a locked working tree, lock reason: initializing
use 'remove -f -f' to override or unlock first
[remove --force --force] 0 
[after -f -f] admin entries: []
[unlock] 128 fatal: 'C:\Users\422mi\AppData\Local\Temp\claude\C--Users-422mi-vidbyte-repos\d2d5110d-c484-4b56-acef-651ebe9a78a5\scrat
[unlock + prune] 0  | admin entries: []
stand-in or grandchild processes: []
```

Today's rerun (CALL 200) gave the same result for `vidbyte-compose-worktree-n0xeu7rh`. It was saved to `$S/probe-locked-unpatched.txt` through `cut -c1-260`, without the `[unlock` lines, so two long lines there are cut short. The lines that matter:

```
[after] admin entries (name, lock reason): [('vidbyte-compose-worktree-n0xeu7rh', 'initializing')]
[after] leftover folders in TMP: []
[prune -v] exit 0 out: (nothing pruned)
[after prune] admin entries: [('vidbyte-compose-worktree-n0xeu7rh', 'initializing')]
[remove --force] 128 fatal: cannot remove a locked working tree, lock reason: initializing
use 'remove -f -f' to override or unlock first
[remove --force --force] 0 
[after -f -f] admin entries: []
```

**Patched with `s4v_fix_add_settle`** (`S4V_PATCH=1`), saved to `$S/probe-locked-patched.txt`:

```
patched: s4v_fix_add_settle
[cancel] add_worktree raised CancelledError (its own removal error, if any, was suppressed)
[after] admin entries (name, lock reason): []
[after] leftover folders in TMP: []
[prune -v] exit 0 out: (nothing pruned)
[after prune] admin entries: []
```

**Spec: inside the failure model.**
- EC-17: "Cancellation while a worktree is being added or filled | The removal runs as a shielded task, then `CancelledError` propagates | No leftover registration or folder".
- The rollback note (spec.md:591): "A leftover worktree. This happens only after a crash, or after a `WORKTREE_FAILED` on removal. Clear it with `git worktree prune` …".
- EC-59 and T-6 accept that a `reference-transaction` hook runs during `worktree add`; they accept the hook running, not a lock left behind.
- EC-20 and EC-21 (cross-process Grok serialization) and A-1 (Grok PLAN mode) are unrelated.
- No A- assumption covers it.
- INV-30 bounds the fix's wait by `COMPOSE_GIT_TIMEOUT_SECONDS`.

**Why it stays Major.** The window is narrow (Windows only, since `taskkill /F` skips git's junk handler while POSIX sends SIGTERM first). The worktree folder itself is removed; only a stale admin entry remains.

**The reviewer's fix fails the frozen test.** `test_harness_compose_git.py:52` classifies `worktree remove` only as `len(words) == 4 and words[:3] == ["worktree", "remove", "--force"]`, and `:156` asserts `kind is not None, f"a git command §9.2 does not list: {words}"`. So `--force --force` would fail the hygiene test, and it would also change §9.2 and INV-9.

**Residual.** A hook that hangs past the 120-second git bound is still killed by the timeout.

### R-15: derived steps re-validated after I/O (R-E4, skills half). CONFIRMED, Major (kept).

**Reproduction.** These are the R-E4 lines and the tally of `probe -k "lone or skill or hook"` (CALL 117); `-k writer_deletes_reader_skill` selects this probe alone. The run's one warning is covered in §8:

```
R-E4 opencode verifier: RAISED ConfigurationError record=n/a | 'skills[0] must be an absolute path to an existing directory; got a value of type WindowsPath that is not one.'
R-E4 opencode: writer launched=1 worktrees=1 leftovers=0
R-E4 grok verifier: RETURNED writer.ok=True failed_verifiers=(0,) error=FailureCode.CONFIGURATION_INVALID_ARGUMENT
R-E4 grok: writer launched=1 worktrees=1 leftovers=0
6 passed, 12 deselected, 1 warning in 21.43s
```

**Code.** `steps.py:112-124`: `anchor`, `relocate` and `rung` each call `replace(...)`, which re-runs the NativeThreadRequest probe at `native_compose.py:102-113`.

**Spec.** INV-15: "`ConfigurationError`, before any I/O". Here the writer ran first (`writer launched=1`).

**Why it stays Major.** No EC row anticipates the trigger (a writer that deletes a reader's skill folder). The effect is a typed but record-less error.

**Downgraded half.** The blank-path half is downgraded. Engineering's `-k blank_path`, re-run by me, gives `blank path: RAISED ConfigurationError | WorkspaceDiff.files must hold non-blank paths.` But spec §9.1 requires non-blank `WorkspaceDiff` files, so changing the rule needs an owner ruling (Minor R-26).

### R-16: no test can fail for the sibling-cancel rule (R-E5). CONFIRMED, Major, test-pack.

**Mutation survives.** `PYTHONPATH="$(pwd);$S" python -m pytest -q -p no:cacheprovider -p s4v_mut_gather tests/features/harness_compose` gives `276 passed in 43.48s`.

**The test plan's "not written" row says:** "No seam the repo mocks can make exactly one child raise a defect … failing one sibling's worktree needs a git hook (T-6 accepts hooks)".

**A real seam exists.** `probe -k seam_grok`:

```
SEAM raised=worktree_failed | 'nsaction: No such file or directory\nfatal: ref updates aborted by hook'
SEAM at raise: worktrees=1 leftovers=0 pending=0 live_leaders=0 live_grandchildren=0 pending=[] launched=['writer', 'g-hold']
```

That output (CALL 120) is from the correct code. I ran the same probe unpatched five more times:
- four runs (CALL 204) printed the same `SEAM at raise` line;
- one run (the unpatched half of CALL 201) printed `live_grandchildren=1` with otherwise the same line (§8).

CALL 123 ran the probe under each mutation, complete output:

```
== s4v_mut_gather
SEAM raised=worktree_failed | 'nsaction: No such file or directory\nfatal: ref updates aborted by hook'
SEAM at raise: worktrees=1 leftovers=0 pending=3 live_leaders=0 live_grandchildren=0 pending=['CliRunner._drain', 'CliRunner._drain', 'ThreadVerifiers._review'] launched=['writer']
SEAM killed survivors: []
1 passed, 20 deselected in 13.60s
== s4v_mut_nocancel
SEAM raised=worktree_failed | 'nsaction: No such file or directory\nfatal: ref updates aborted by hook'
SEAM at raise: worktrees=1 leftovers=0 pending=0 live_leaders=0 live_grandchildren=0 pending=[] launched=['writer', 'g-hold']
SEAM killed survivors: []
1 passed, 20 deselected in 43.29s
```

Under plain gather, the composite raises with three tasks still pending: two `CliRunner._drain` and `ThreadVerifiers._review`. Under gather without cancel, it raises only when the held Grok verifier ends by itself, at the stand-in's `HOLD_LIMIT_SECONDS = 30.0` (`fake_harness.py:29`), which is why that run takes 43 s against 13 s.

**How the seam fails the add.** On this win32 sandbox git cannot spawn the `sh` hook, and that fails the add with "fatal: ref updates aborted by hook". On POSIX the same hook exits 1. Either way the add fails cleanly and leaves nothing behind.

**Test-author note.** Use a Grok verifier held in place plus a failing opencode add. A variant with two opencode verifiers runs into R-10's add-path orphan. On today's code its "no pending task at raise" assertion would fail until R-10 is fixed. My first seam probe was that variant (`test_ec19_hook_fails_second_worktree_add`, CALL 117):

```
R-E5 seam at raise: worktrees=1 leftovers=0 pending=3 live_leaders=0 live_grandchildren=0 launched=['writer']
```

### R-17: the key test overclaims (R-C3, test half). CONFIRMED, Major, test-pack.

`test_harness_compose_keys.py:111-112` says "a ConfigurationError never quotes a key a caller put in a bad template". But line 139 drives only `f"Use {key_w} then {{nope}} and {{previous}}"`, and `require_template` (`chain.py:105`) refuses that before the quoting `require_text` (`chain.py:106`) runs.

`fresh_key` (`conftest.py:116-120`) returns `f"vbk-{label[:6]}-{uuid.uuid4().hex}{uuid.uuid4().hex}"`, up to 75 characters long (4 + 6 + 1 + 64), so any template holding it has a repr over 80 characters and is never quoted.

The missing assertion and the seam are given in review.md R-17.

## 4. Orchestrator adjudications

### 4.1 Test-pack rows

The frozen tree is `tests/features/harness_compose/`, `tests/features/harness_threads/fake_harness.py` and `tests/features/harness_threads/README.md` (S2_HEAD `2ef11f3a`).

| Row | Severity | What is wrong | Missing assertion or surviving mutation | Real-seam reproducer |
|---|---|---|---|---|
| R-11 | Blocker | 22 test comment lines over 72 columns (the test half of R-V7) | None: there is no behavior gap and no mutation; the awk check is the reproducer | n/a |
| R-16 | Major | Rewriting fan_out as a plain gather passes all 276 tests (R-E5) | Surviving mutations: plain gather (276 passed) and gather without cancel. Missing assertion: at the raise, no pending task, no live stand-in pid, `worktrees()==1`, `leftovers()==[]`, and a raise well within the hold limit | Yes: `probe -k seam_grok`, using a `reference-transaction` hook that fails the add |
| R-17 | Major | The key test cannot reach the quoting path (the test half of R-C3) | Missing assertion: a short key (at most about 60 characters) in `"{previous} " + key + "\x00"`, and at the other seven sites, raises a `ConfigurationError` with no key fragment in its message or details | Yes, and it needs no mocks |

R-6 and R-3 keep their source halves as separate, repairable rows. Test-pack rows are not counted in the repair list.

### 4.2 Conventions Blockers against the rule as written

| Finding | Rule (exact) | Contradicts the rule as written? |
|---|---|---|
| R-V1 | strict-config-dataclasses.md: "When an option is missing (no cap, one line, tuple items, folder resolution), add it as a keyword with a backward-compatible default"; When: "checks text, ints, enums, paths, or tuples, or a module grows `_text_field` / `_count_field`-style helpers" | **Yes** for the count checks, `counted` and the blank items (R-7). **No** for the callable checks, which the rule's list does not cover (R-27) |
| R-V2 | AGENTS.md principle 4: "Functions that carry core business logic take a dataclass as input … rather than loose dicts, tuples"; "Small private helpers do not need dataclasses of their own" | **Yes** for the `fit`/`check`/`render` frames (R-9). **No** for `read` and `_roles`, which are exempt small helpers (R-28) |
| R-V3 | Ledger 10 (§D weighted word): "every sentence addressed to a model lives in a `prompts/*.md` file"; INV-20 | **Yes** (R-1) |
| R-V4 | AGENTS.md principle 5: "whenever a canonical helper in vidbyte/lib/ would save writing the same logic a second time, build it that way" | **Yes** (R-5). The fix needs a §14 budget ruling (§4.9) |
| R-V5 | blocking-lint-invariants.md (A007): "For a validator, name the floor next to its cap … even when the floor is `1`" | **Yes** for the floors (R-2). **No** for the derived caps, which are the spec's own `1 + constant` definitions (refuted). The INV-15 static policy allows `0` and `1` under native/ but does not require literals, so the two rules are compatible |
| R-V6 | AGENTS.md principle 1: "a function may call another of its own functions, but that second function should not call a third"; "Calls out to another class … do not count" | **Yes** (R-4). It is the only chain in 17 files |
| R-V7 | comment-format.md: "Wrap every comment line at 72 columns, counting the indent"; Check: the awk test "prints nothing for the files you touched" | **Yes** (R-6 source, R-11 test-pack). The lesson's own note ("leave untouched files alone") does not apply, because these files are new |

### 4.3 R-C4 (backstop after `WORKTREE_FAILED`): the spec answers it, and the behavior claim is refuted

INV-11's early-stop list is "a failed plan, no successful proposal, a failed round or selection". These are step failures only. It then says "It does not run after a cancellation or a defect."

INV-14 says: "Any other exception from a child, such as a `ThreadComposeError` from its worktree or a defect, cancels every sibling. Compose waits until each sibling has stopped and removed its worktree, then that one exception propagates". EC-19 repeats: "Then that one exception propagates."

So a reader's `WORKTREE_FAILED` propagates as that one exception, and the backstop does not run. That is what the code does (`verify.py:88-94`). The composite still fails loudly, which satisfies ledger 4's "fail loudly". The only defect is the header wording at `verify.py:8` ("skip it only on a cancellation or a defect") and the matching text at `ensemble.py:8`; that is Minor R-18. **No open item.**

### 4.4 R-C3/R-E6 scope

- **Reachable with a key as input:** yes, at 8 sites, with 49- and 12-character keys (§3, R-3).
- **Within INV-4 r3:** the message is text compose itself raises. Raw step output and `WorkspaceDiff.text` are out of scope (EC-71) and are not involved.
- **Base behavior:** a direct call quotes the same way (`BASE run_opencode_thread: NativeThreadError key-in-message=True`). It is left alone (R-29).
- **Preferred fix:** `require_text(..., quote=False)`. It has a backward-compatible default, so the base functions raise exactly what they raise today.
- **Test pins:** no base or surface test pins `_received` wording. The grep is in §3, R-3.

### 4.5 Interacting fixes: order and guards

1. **Cleanup group, landed as one change: R-10, then R-4, then R-14.** These touch `calls.py`, `workspace.py` and `git.py`, plus the planner and selector call sites.
   - R-10 adds the settle helper, uses it in fan_out, in `__aexit__` and in the enter failure path, and wraps the planner and selector as one-child fan-outs.
   - R-4 moves the add-path cleanup into `DisposableWorktree.__aenter__`.
   - R-14 waits out a `worktree add` child that has started.
   - Guards:
     - `tests/features/harness_compose/test_harness_compose_concurrency.py` (AC-10, AC-11, INV-13, INV-14, EC-17).
     - `test_harness_compose_git.py`, whose argv pins at `:52` and `:156` must stay green.
     - `test_harness_compose_workspace.py`, `test_harness_compose_verify.py` and `test_harness_compose_ensemble.py`.
     - The probes `probe -k "double_cancel or anyio or two_failing or orphan_removal or seam_grok"`, engineering's `-k anyio_cancel_scope_planner`, and `S4V_PATCH`-free `probe_locked.py`, which must now show `admin entries: []`.
2. **R-8 (EC-16), on top of the new fan_out.** It touches `_review`, `_propose` and the except blocks in `verify_with` and `run_ensemble`. Guards: `probe -k ec16`, plus the verify and ensemble tests.
3. **R-15 (`steps.py` derivation).** Guards: `probe -k writer_deletes`, the validation tests (EC-78 invoker cases), and the chain and stages tests (anchor and rung).
4. **Validation group: R-2, then R-7, then R-3.** These touch the constants, `to_tuple(min_items=)` and `require_text(quote=)`, all in `validation.py`, the records and the compose call sites.
   - R-7 consumes R-2's named floors.
   - R-3 and R-7 both edit `validation.py`.
   - Guards: `test_harness_compose_validation.py`, which asserts `details["field"]` and the exact units message at `:244-245`; the `harness_threads` record tests; the keys tests; and `probe -k "key_in or bind_refus"`.
5. **Texts group: R-9, then R-5, then R-12, then R-13.** All four touch `texts.py`'s `render`, `check`, `fit` and `_scrub`.
   - Guards:
     - the keys tests, which engineering showed kill both scrub mutations: m6 (texts scrub; "3 failed, 1 passed") and m7 (git scrub; "1 failed, 3 passed"). R-5 replaces both scrubs, so both must stay killed.
     - the prompts, chain, stages and answers tests;
     - `probe -k "lone or opencode_orphan or caller_prompt or blank_previous"`.
6. **R-1, then R-6 (comment rewrap) last**, because every earlier fix moves comments.

### 4.6 R-E3

Covered in §3, R-12: INV-15's record promise (with ledger 7), INV-18's closing sentence and INV-29, and INV-5 for caller text.

### 4.7 R-E2

Covered in §3, R-14: it is inside the failure model (EC-17 and spec.md:591), and no accepted limitation covers it.

### 4.8 Scope-adding

R-E8 (a stat-seeded temporary index) stays Minor follow-up R-25 and is not built. R-8's partial-record shape for cancelled siblings would also be scope-adding, and is not proposed.

### 4.9 [verifier] blind spots and fix interactions

1. **Spec §14 "Ask first" (spec.md:1458-1466) gates several fixes.** The rules are: "Touching a file not in §12.3"; "Exceeding the §8.4 budget: … any class, record, enum, constant group or public name that §8.5 does not list"; and "Adding a dependency, a parameter, a config field, a control or a public name not in §8.5".
   - **R-9** needs a 19th record (`PromptSegment`); §8.4 counts 18.
   - **R-5** needs a new lib file or class.
   - Under a strict reading of "parameter" and "constant group", **R-7** (`to_tuple(min_items=)`), **R-3** (`require_text(quote=)`) and **R-2** (five constants) are also gated.
   - **R-10's settle helper** stays in budget if it is a static method on an existing §12.3 class such as `ComposeCalls`. S3 itself added unlisted helper methods (`StepRoles.counted`), so a helper method on an existing class is precedented.

   The orchestrator should rule before S5 starts. Otherwise S5 must stop BLOCKED on these rows.
2. **R-14's reviewer fix breaks a frozen test** (`test_harness_compose_git.py:52`, `:156`). The validated alternative keeps the §9.2 argv.
3. **R-9's fix must not cap or pattern-check `PromptSegment.text`.**
   - A spliced value can be 100,000 characters (`COMPOSE_ANSWER_TEXT_MAX_CHARS` and `COMPOSE_DIFF_MAX_CHARS`). A `require_text` cap below that, or a NUL pattern, would turn a long or NUL-holding value into a post-I/O `ConfigurationError` (INV-15, EC-37).
   - A fixed segment holds caller template text, which may reach `NATIVE_PROMPT_MAX_CHARS` (200,000).
   - A short, invalid value holding a key would also be quoted.
   - So check the type only: `RecordFieldValidator.require_instance(self.text, "PromptSegment.text", str)` and `RecordFieldValidator.require_bool(self.spliced, "PromptSegment.spliced")`.
4. **R-7 versus R-E4's blank-path proposal.** Move the non-blank check into `require_text` per item; do not delete it, because spec §9.1 requires it. Pass `quote=False`, because a writer can put a key in a file name; this is defensive, since a blank value holds no key. R-26 is the open spec question.
5. **R-10 must re-raise the caught `CancelledError` object.** Engineering observed a fresh `CancelledError()` escaping anyio's scope. The fix must also add no `asyncio.Lock` (TID251 at `lint/ruff.toml:8`, S039 ratchet 5).
6. **R-13's blank check must run after `require_template`**, so that the `{previous!r}` and `{previous:>5}` validation cases keep their current refusal and field.

## 5. Reviewer disagreements adjudicated

- **R-C1 (Blocker) versus R-E7 (Major), the same root.** Merged as Blocker (R-8): a §D weighted word (ledger 7) broken on an EC row (EC-16), with paid-for answers and thread ids lost. Engineering's "a partial-result shape … [scope-adding]" is accepted only for cancelled siblings.
- **R-C5 (Minor) versus R-V3 (Blocker).** Blocker (R-1). Ledger 10 is a §D weighted word, and the sentence is sent to the model.
- **R-C3 and R-E6 (both Major) versus the weighted word.** Raised to Blocker (R-3). Engineering itself wrote "Under the weighted-word rule it could be promoted to Blocker". Base parity is out of scope under INV-4 r3.
- **R-C2 (conformance Blocker) versus engineering's "spec-level gap, left to the conformance lens".** Confirmed, at Major (R-13), for the reasons in §3.
- **R-E4's blank-path fix versus R-V1's fix versus spec §9.1.** Follow §9.1: move the check (R-7). Weakening the rule needs an owner ruling (R-26).
- **R-E2's `-f -f` versus the frozen hygiene test.** Replaced by the wait-out fix (R-14).
- **R-V2's suggested `require_text(..., allow_blank=True)` on `PromptSegment.text` versus INV-15/EC-37.** Narrowed to a type-only check (§4.9).

## 6. Candidate fixes validated in scratch

None of these was applied to the worktree. Each was loaded with `-p` or `patch()`.

| Plugin | Fixes | Probe result | Frozen pack |
|---|---|---|---|
| `$E/fix_settle.py` | R-10 (fan_out settle only) | CALL 152, `-k "double_cancel or anyio or two_failing"`: every R-E1 line is `worktrees=1 leftovers=0 pending=0 live_leaders=0 live_grandchildren=0`. TWO-ADDS is still `pending=['CliRunner._drain', 'CliRunner._drain', 'ComposeGit.remove_worktree']`, because this half does not touch the add path. `6 passed, 17 deselected in 49.49s` | `276 passed in 46.33s` |
| `$E/fix_settle.py` + `$E/fix_planner_isolated.py` | R-10 (planner) | CALL 225: `PLANNER: scope cancelled; at return: worktrees=1 leftovers=[] pending tasks=0 live leaders=0 live grandchildren=0`; `1 passed, 13 deselected in 13.43s` | (next rows) |
| `$E/fix_settle.py` + `$S/s4v_fix_add_settle.py` | R-10 (fan-out and add path) and R-14 | CALL 206, `-k "double_cancel or anyio or two_failing or seam_grok"`: every R-E1 line all zeros; SEAM clean; `TWO-ADDS at raise: worktrees=1 leftovers=[] pending=[]`; `7 passed, 17 deselected in 51.56s` | `276 passed in 45.19s` |
| all three: `fix_settle` + `fix_planner_isolated` + `s4v_fix_add_settle` | R-10 complete and R-14 | CALL 338, `-k "double_cancel or anyio or two_failing or seam_grok or orphan_removal"`: every R-E1 line all zeros; SEAM clean; `TWO-ADDS at raise: worktrees=1 leftovers=[] pending=[]`; `SHUTDOWN pending at raise=[] -> after cancel: worktrees=1 leftovers=[] admin=[]`; `8 passed, 16 deselected in 50.08s`. Then CALL 339, `-k anyio_cancel_scope_planner`: `PLANNER: scope cancelled; at return: worktrees=1 leftovers=[] pending tasks=0 live leaders=0 live grandchildren=0`; `1 passed, 13 deselected in 13.74s`. Log: `$S/fix-all-cleanup-probes.txt` | `276 passed in 51.09s` (`$S/fix-all-cleanup-pack.txt`) |
| `$S/s4v_fix_add_settle.py` via `S4V_PATCH=1 probe_locked.py` | R-14 | CALL 200: `[after] admin entries (name, lock reason): []` and `[after prune] admin entries: []` | (rows above) |
| `$S/s4v_fix_surrogate.py` | R-12 (spliced values) | CALL 244 and CALL 245: Grok, Muse and opencode next give `RETURNED failed_step=None second error=None`; `ORPHAN chain failed_step=None code=None \| 'None' \| second ok=True`; `ORPHAN second-step processes right after return: []` | `276 passed in 50.64s` |
| `$S/s4v_fix_blank.py` | R-13 | CALL 248: `vidbyte.lib.errors.base.ConfigurationError: template must hold text besides its placeholders, or steps[1] can be sent a blank prompt.`, raised from `check` before any git process or step | `276 passed in 52.07s` |

Not monkeypatched:
- **R-8's deposit fix:** it restructures `verify_with` and `run_ensemble`. `_plan` already shows the pattern.
- **R-3's `quote=` option:** it means call-site edits, and a grep shows no pinned wording.
- **R-15's derivation fix:** it changes how `steps.py` builds relocated, anchored and rung steps from an already-validated step. The reproducer (`-k writer_deletes_reader_skill`) is the check S5 should run once it is written.
- The conventions refactors (R-2, R-4, R-5, R-6, R-7, R-9).

## 7. Commands claimed to pass: final lines

Every command ran from the worktree root. Commands are shown without:
- the leading `cd <worktree> &&`;
- the `S=`/`E=` assignments;
- the `timeout 900` wrapper;
- the trailing `| tail -N > log` or `| tee log` that saved the output.

The saved log is named where one exists. `git status --short` was checked after the fix-plugin runs and at the end (§10).

**Baseline compose pack** (CALL 46; log `$S/baseline-compose.txt`): `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_compose`

```
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 45.57s
```

**Lint** (CALL 131, repeated in CALL 133; log `$S/lint-run.txt`): `(PYTHONPATH=$(pwd) python lint/run.py > $S/lint-run.txt 2>&1; echo "exit=$?" >> $S/lint-run.txt)`

```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
exit=0
```

Its ratchet table holds every count at its baseline. A001 (agent-readable-file-headers) is at 642 of 642, A007 (operational-constants) at 255 of 255, C008 (shared-validator-owner) at 45 of 45 and S039 (banned-api-policy) at 5 of 5, all `RATCHETED`.

**Ruff count checks** (CALL 132, repeated in CALL 134 and CALL 254). These count findings, so a non-zero count is expected; it is compared with the baseline:
- I001: `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache --statistics 2>&1 | tail -2`;
- TID251: `python -m ruff check pyproject.toml vidbyte --config lint/ruff.toml --select TID251 --no-cache --statistics 2>&1 | tail -2`.

The two tails, in that order:

```
Found 223 errors.
[*] 223 fixable with the `--fix` option.
5	TID251	banned-api
Found 5 errors.
```

S039 is ruff's TID251 (`lint/rules/s039_banned_api_policy.py`: `codes = frozenset({"TID251"})`). The TID251 count of 5 equals S039's ratchet of 5, and `git diff --stat` shows the diff does not touch `lint/`. So the diff adds no banned API, such as `asyncio.Lock` (`lint/ruff.toml:8`).

**INV-15 static policy** (CALL 162): `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/test_harness_threads_static_policy.py`

```
...                                                                      [100%]
3 passed in 0.19s
```

**Mutation `s4v_mut_gather`** (evidence for R-16; CALL 122; log `$S/mut-gather-pack.txt`): `PYTHONPATH="$(pwd);$S" python -m pytest -q -p no:cacheprovider -p s4v_mut_gather tests/features/harness_compose`

```
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 43.48s
```

**`fix_settle` pack** (CALL 154; log `$S/fix-settle-pack.txt`, saved through `tail -2`): `PYTHONPATH="$(pwd);$E" python -m pytest -q -p no:cacheprovider -p fix_settle tests/features/harness_compose`

```
............................................................             [100%]
276 passed in 46.33s
```

**`fix_settle` + `s4v_fix_add_settle` pack** (CALL 205; log `$S/fix-combined-pack.txt`): `PYTHONPATH="$(pwd);$S;$E" python -m pytest -q -p no:cacheprovider -p fix_settle -p s4v_fix_add_settle tests/features/harness_compose`

```
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 45.19s
```

**All three cleanup plugins pack** (CALL 337; log `$S/fix-all-cleanup-pack.txt`): `PYTHONPATH="$(pwd);$S;$E" python -m pytest -q -p no:cacheprovider -p fix_settle -p fix_planner_isolated -p s4v_fix_add_settle tests/features/harness_compose`

```
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 51.09s
```

**`s4v_fix_surrogate` pack** (CALL 247; log `$S/fix-surrogate-pack.txt`): `PYTHONPATH="$(pwd);$S" python -m pytest -q -p no:cacheprovider -p s4v_fix_surrogate tests/features/harness_compose`

```
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 50.64s
```

**`s4v_fix_blank` pack** (CALL 250; log `$S/fix-blank-pack.txt`): `PYTHONPATH="$(pwd);$S" python -m pytest -q -p no:cacheprovider -p s4v_fix_blank tests/features/harness_compose`

```
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 52.07s
```

**Probe runs.** The probe tests print rather than assert, so "passed" only means the probe ran to its print. Their result lines are quoted in §3 and §6. Each tally below is the run's final line:

| Call | Plugins | Selection | Final line |
|---|---|---|---|
| CALL 110 | none | `-k "ec16"` | `3 passed, 15 deselected in 16.59s` |
| CALL 111 | none | `-k "blank or key_in"` | `4 passed, 14 deselected in 14.08s` |
| CALL 116 | none | `-k "double_cancel or anyio"` | `5 passed, 13 deselected in 47.48s` |
| CALL 117 | none | `-k "lone or skill or hook"` | `6 passed, 12 deselected, 1 warning in 21.43s` |
| CALL 120 | none | `-k "seam_grok or two_failing or orphan"` | `3 passed, 18 deselected in 22.23s` |
| CALL 123 | `s4v_mut_gather`, then `s4v_mut_nocancel` | `-k seam_grok` | `1 passed, 20 deselected in 13.60s`; `1 passed, 20 deselected in 43.29s` |
| CALL 126 | none, three runs | `-k "orphan_removal"` | `1 passed, 21 deselected in 14.07s`, `in 14.03s`, `in 14.10s` |
| CALL 150 | none | `-k "bind_refusals"` | `1 passed, 22 deselected in 13.98s` |
| CALL 152 | `fix_settle` | `-k "double_cancel or anyio or two_failing"` | `6 passed, 17 deselected in 49.49s` |
| CALL 156 | none | `-k "caller_prompt"` | `1 passed, 23 deselected in 14.16s` |
| CALL 201 | none, then `s4v_fix_add_settle` | `-k "two_failing or seam_grok"` | `2 passed, 22 deselected in 17.34s`; `2 passed, 22 deselected in 16.90s` |
| CALL 206 | `fix_settle`, `s4v_fix_add_settle` | `-k "double_cancel or anyio or two_failing or seam_grok"` | `7 passed, 17 deselected in 51.56s` |
| CALL 225 | none, then `fix_settle`, `fix_planner_isolated` (engineering's probe file) | `-k "anyio_cancel_scope_planner or blank_path"`, then `-k anyio_cancel_scope_planner` | `2 passed, 12 deselected in 21.18s`; `1 passed, 13 deselected in 13.43s` |
| CALL 244 | none, then `s4v_fix_surrogate` | `-k "lone_surrogate_next_step or orphan or caller_prompt"` | `6 passed, 18 deselected in 25.06s`; `1 failed, 5 passed, 18 deselected in 21.11s` (the failure is the probe's own print, explained under R-12) |
| CALL 245 | `s4v_fix_surrogate` | `-k "orphan"` | `2 passed, 22 deselected in 19.56s` |
| CALL 248 | `s4v_fix_blank` | `-k "blank_previous"` | `2 failed, 22 deselected in 13.43s` (the intended up-front refusal, explained under R-13) |
| CALL 338, CALL 339 | all three cleanup plugins | `-k "double_cancel or anyio or two_failing or seam_grok or orphan_removal"` (CALL 338), then engineering's `-k anyio_cancel_scope_planner` (CALL 339) | `8 passed, 16 deselected in 50.08s`; `1 passed, 13 deselected in 13.74s`. CALL 338's planner half printed nothing: I left `$S` off its `PYTHONPATH`, so `-p s4v_fix_add_settle` could not load. CALL 339 re-ran it with `$S` on the path |

## 8. Observations not raised as findings

- **A transient grandchild in one seam run.** There were six unpatched `seam_grok` runs: CALL 120, the unpatched half of CALL 201, and four in CALL 204. In one of them (CALL 201), one grandchild of the held Grok stand-in was still alive at the instant of the raise. The other five showed 0, and `procs.py` found no process afterwards. The process stop belongs to the base `CliRunner`, and Windows `taskkill` can return a moment before the process is gone, so this fits base timing. It is not evidence of a compose defect.
- **One unclosed-transport warning.** The `lone or skill or hook` run (CALL 117) reported one `PytestUnraisableExceptionWarning`, in `test_writer_deletes_reader_skill[grok]`: `Exception ignored in: <function _ProactorBasePipeTransport.__del__ …>`, with `ValueError: I/O operation on closed pipe` raised while formatting the `unclosed transport` warning. It appeared in no other run. Every compose child process, git included, goes through the base `CliRunner` (`git.py:31`, `:206`), so this is base or CPython proactor behavior at garbage collection, not a compose finding.
- **EC-56 is not affected by R-15's mechanism.** `MUSE_WSL_WORKSPACE_RULE` is enforced in `vidbyte/harnesses/native/muse/launcher.py:50` at run time, not in the ThreadStep probe, so a relocated Muse reader still records it, as EC-56 says.
- **`fresh_key` length.** `fresh_key` keys are 75 characters, so the pack can never exercise `_received`'s quote path (see R-17).
- **POSIX behavior was not probed** for R-12 and R-14. Both findings stand on their win32 reproductions.

## 9. Scratch files (all under `$S`)

- **Brief:** `brief.txt`.
- **Probes:** `test_s4v_probes.py`, `probe_locked.py` (accepts `S4V_PATCH=1`), and `chain_check.py`.
- **Process check:** `procs.py`, which lists or kills stand-in and grandchild processes.
- **Mutation plugins:** `s4v_mut_gather.py` and `s4v_mut_nocancel.py`.
- **Candidate-fix plugins:** `s4v_fix_add_settle.py`, `s4v_fix_surrogate.py` and `s4v_fix_blank.py`.
- **Logs:** `baseline-compose.txt`, `lint-run.txt`, `mut-gather-pack.txt`, `fix-settle-pack.txt`, `fix-combined-pack.txt`, `fix-combined-probes.txt`, `fix-all-cleanup-pack.txt`, `fix-all-cleanup-probes.txt`, `fix-surrogate-pack.txt`, `fix-blank-pack.txt`, `probe-locked-unpatched.txt`, `probe-locked-patched.txt`, `planner-blank-unpatched.txt` and `planner-patched.txt`.
- **Command record:**
  - `transcript-commands-full.txt` holds every command this stage ran, numbered CALL 0 onward, with its full output.
  - `extract_outputs.py` writes it from the session transcript.
  - `transcript-commands.txt` is an earlier, shorter extraction.
- **Evidence checks:**
  - `check_tables.py` counts the cells of each markdown table row.
  - `check_quotes.py` traces every fenced output line, and every quoted pytest tally, in the report to the command record and the logs.
  - `check_spans.py` traces every inline quoted span in review.md to the command record, the source, the spec, the reviews or the field guide.
  - `corpus-files.txt` lists the files `check_spans.py` searched.
- **Other helpers:** `fix_orphan_print.py`.
- **Throwaway repositories:** `s4v-locked-*` folders.

## 10. Cleanup and worktree state

- **No leftover processes.** `python $S/procs.py` printed `stand-in or grandchild processes: []` after the last probe. The probe survivors were killed as they occurred, by the probes themselves or by `procs.py --kill`:
  - the R-10 grandchildren;
  - the R-12 orphans (pids 31188 and 1228);
  - pid 24228 from the planner probe.
- **Throwaway repositories** live only under `$S` (`s4v-locked-*`). The worktree's own `.git` was never probed.
- **Worktree state.** `git log --oneline -1` is `0f9e66d1 docs(spec): add the three S4 reviews for native-thread-compose`. `git status --short` shows only this stage's two files:
  - `?? docs/spec/native-thread-compose/reports/S4-findings-verifier.md`
  - `?? docs/spec/native-thread-compose/review.md`
- **Evidence checks on the final files:**
  - `check_tables.py`: 0 bad rows in review.md (44 rows) and in this report.
  - `check_quotes.py` on this report, against a command record with every call that displays either output file removed, plus the logs and the cited source files: every fenced line and every quoted tally is found verbatim, except the one probe-command template in §1, which holds a `<selection>` placeholder.
  - `check_spans.py` on review.md: every inline span of 20 or more characters is traced, except three grep patterns. Those are shown without the file arguments they ran with; their results were re-run and match.
- **Nothing else was done:**
  - no commits, staging, stash, checkout, reset or push;
  - no pip install;
  - no edits to code, tests, spec or the three reviews.
