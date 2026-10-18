LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — placement, prompts, headers and the lint loop are right, but seven convention Blockers each need a local, mechanical fix before the owner reviews the PR: hand-rolled record checks, positional prompt-segment tuples, one model-addressed sentence in Python, a key scrub written three times, literal validator floors, one two-level call chain, and 46 over-wide comment lines.

WHAT THE IMPLEMENTATION GETS RIGHT
- Placement and surface follow AGENTS.md exactly. Do not move any of this:
  - 7 `StrEnum`s live in `vidbyte/lib/enums/native_compose.py`, all exported from `vidbyte/lib/enums/__init__.py`.
  - 18 `@dataclass(frozen=True, slots=True)` records live in `vidbyte/lib/dataclasses/native_compose.py` and `native_ensemble.py`, and every value lives in `vidbyte/lib/constants/native_compose.py`.
  - `ThreadComposeError` copies `NativeThreadError`'s A003 packet: a literal `DIAGNOSTIC_FIELDS`, each field an attribute and in `details`, and `WorkspaceDiff` imported under `TYPE_CHECKING`.
  - Compose names are exported only from `vidbyte.harnesses.native.compose`; `native.__all__` is untouched.
- The 22 prompt files are clean:
  - A digit grep over all 22 finds no numeral in prose outside list markers.
  - Every number arrives through a placeholder: `{roles}`, `{target}`, `{minimum}`/`{maximum}` or `{omitted}`.
  - The `prompts/*.md` package-data glob ships them.
  - `ComposeTexts.load` reads them with `importlib.resources` and `asyncio.to_thread(resource.read_text, encoding=...)`, and checks each against `COMPOSE_PROMPT_FIELDS`.
- The agentic structure holds:
  - All 18 new modules carry a full A001 header. Each FUNCTION INVENTORY matches the defs, with one omission (R-V10), and all 16 TESTS paths exist.
  - The composites are narrated step by step.
  - `@intent` blocks sit on the load-bearing rules: `ThreadBinder.invoke`, `StepRoles.reader`, `StepRoles.fork_role`, `DisposableWorktree.backstop`, `PromptFitter.fit`, `JsonText.decode` and `GrokWorkspaceLocks.slot`.
  - There are no nested functions or lambdas, and the one-slot `asyncio.Semaphore` keeps S039 at 5.
- The gate and history are clean:
  - SDK-LINT passes with no ratchet raised, and ruff I001 (223) and TID251 (5) are at baseline.
  - The INV-15 static-policy test passes on all 13 compose modules, and the 276 compose tests pass.
  - 35 of the 55 commits each carry one item and cite their W-/FR-/AC- (or R-) IDs; the other 20 record pipeline state under `docs/spec`. All 55 carry a Co-Authored-By line, and none adds a cache, log, key or env file.

FINDINGS

R-V1 [Blocker] [field-guide: strict-config; lib validators] vidbyte/lib/dataclasses/native_compose.py:194 — The records and one harness helper hand-roll ten generic checks that RecordFieldConverter and RecordFieldValidator should own, while both record headers say every check goes through those validators
  Evidence:
  - Records in `native_compose.py`:
    - `:194-195` reads `if not turns:` / `raise ConfigurationError("JsonAnswer.turns must hold at least one turn.", ...)`. The same non-empty check sits at `:240-241` (ChainResult.outcomes) and `:360-361` (StagedResult.stages).
    - `:144-145` hand-checks blank `WorkspaceDiff.files`.
    - `:87-90` hand-check `callable(self.function)` and `callable(self.invoker)`.
  - Records in `native_ensemble.py`: `:51` `if len(proposers) < ENSEMBLE_MIN_PROPOSERS:`, `:94` `if not roles:`, and `:110` `if not kept or len(set(kept)) != len(kept) or min(kept) < 1:`.
  - Harness side:
    - `vidbyte/harnesses/native/compose/steps.py:141-145` defines `counted(values: object, argument: str, *, minimum: int, maximum: int)`. It calls `to_tuple(values, argument, item_type=object)`, then `if not minimum <= len(items) <= maximum: raise ConfigurationError(native_compose.COMPOSE_COUNT_RULE...)`.
    - `answers.py:55-56` re-checks `callable(parse)` with `COMPOSE_NOT_CALLABLE`. That is the same sentence `native_compose.py:88` writes as a literal f-string.
  - The canonical check for the callables already exists. `RecordFieldConverter.require_instance(value, field_name, expected, *, optional=False)` is called 15 times in these two records for other fields (`native_compose.py:124`, `:162-164`, `:258`, `:281-282`, `:304`, `:322`; `native_ensemble.py:49`, `:54-55`, `:143`, `:146-147`). In memory, `require_instance(3, "ThreadStep.function", collections.abc.Callable)` raised "ThreadStep.function must be Callable; got a value of type int." with `details={'field': 'ThreadStep.function'}`, and it accepted `len` and a `functools.partial`.
  - One rule now has six wordings:
    - "must hold at least one turn"
    - "must hold 1 to 10 steps; got N"
    - "must hold 1 to 10 roles; got none"
    - "must hold 1 to 10 different positive proposal numbers"
    - `COMPOSE_COUNT_RULE`: "must hold {minimum} to {maximum} items; got {count}"
    - `to_tuple`'s own "may hold at most {max_items} items; got N"
  - The headers disagree with the code:
    - `native_compose.py:5` and `native_ensemble.py:5` both say "Every check lives in __post_init__ and goes through RecordFieldValidator and RecordFieldConverter".
    - The `validation.py` header says "never copy a check into a record".
    - The PR did extend `validation.py` (`require_template`, `command_line_units`), so the pattern was in reach.
  Failure:
  - The rule is in `field-guide/vidbyte-sdk/strict-config-dataclasses.md`: "Validate record fields through RecordFieldValidator / RecordFieldConverter; add an option rather than a private field helper" ("When an option is missing ... add it as a keyword with a backward-compatible default").
  - Spec §9.1 says the same, as do two §12.4 lines: the dataclass line and the C008 line ("Validator helpers are added only in vidbyte/lib/dataclasses/validation.py").
  - C008 stays quiet only because its grammar matches primitive-validator names.
  - The owner would repeat the PR #1084 comment (4289880446, which asked that per-class helpers become canonical lib classes): give `to_tuple` a `min_items` option and use `require_instance`, instead of hand-rolling six count checks, three callable checks and a `counted()` helper with six wordings for one rule.
  Smallest fix:
  - Add `min_items: int | None = None` to `RecordFieldConverter.to_tuple`.
  - Use it for the six count checks, and call `to_tuple(..., min_items=..., max_items=...)` directly in place of `StepRoles.counted`.
  - Use the existing `RecordFieldConverter.require_instance(..., collections.abc.Callable)` for the three callable checks, with `optional=True` for `ThreadStep.invoker`. `isinstance(value, Callable)` tests the same `__call__` shape as `callable()`, so §9.1's note (the record checks the shape of a higher-layer object, not its type) still holds.
  - Refuse a blank `WorkspaceDiff.files` path through `RecordFieldValidator.require_text` on each item, which refuses blank text by default.
  - Keep the true cross-field rules inline: StepOutcome's exactly-one-of, StageSpec's run step, ThreadStep's continue-needs-thread_id, EnsemblePlan's unique names, and EnsembleRound's distinct kept numbers.
  - Correct both ARCHITECTURE NOTEs.
  - This is test-safe: the validation tests assert only `details["field"]` (`test_harness_compose_validation.py:198`; `:245` compares `details == {"field": "prompt"}`), which `to_tuple` and `require_instance` already set, and no test pins the count wording.
  Spec IDs: n/a (spec §9.1; §12.4 dataclass and C008 lines)

R-V2 [Blocker] [AGENTS.md principle 4] vidbyte/harnesses/native/compose/texts.py:49 — Prompt segments travel through seven modules as positional (text, bool) tuples, and the bool decides whether the D-28 key scrub runs
  Evidence:
  - Signatures:
    - `texts.py:49` `def render(template: str, values: Mapping[ComposeField, str | tuple[tuple[str, bool], ...]]) -> tuple[tuple[str, bool], ...]:`
    - `texts.py:102` `async def fit(frame: Sequence[tuple[str, bool]], step: ThreadStep, keys: Iterable[str]) -> str:`
    - `texts.py:115` `segments = [(PromptFitter._scrub(text, bound) if spliced else text, spliced) for text, spliced in frame]`
  - Fixed segments are built by hand at `chain.py:57` `((prompt, False),)`, `verify.py:68`, `answers.py:66` and `selection.py:137` `((system, False),)`.
  - A fixed-string grep finds 35 `tuple[str, bool]` annotations on 27 lines in 7 modules.
  - Other positional returns:
    - `answers.py:118` `AnswerDecoders.read(...) -> tuple[AnswerT | None, str | None]`, a public method.
    - `ensemble.py:124` `_roles(...) -> tuple[ThreadStep, tuple[ThreadStep, ...], ThreadStep, ThreadStep]`, built at `:147-148` and unpacked at `:53`, although `EnsembleRoster` already holds exactly those four fields.
  Failure:
  - The rule is AGENTS.md principle 4: "Functions that carry core business logic take a dataclass as input and return a dataclass as output, rather than loose dicts, tuples, or long lists of primitive arguments ... the rule is for the functions that hold a feature's real logic and for the data passed between layers." The house style adds "never loose dicts or positional tuples".
  - `PromptFitter.fit` is the INV-4/INV-18 scrub-and-cut logic, and the segment is the data every composite hands it.
  - Nothing in the type says which slot is which. A future site that writes `(answer, False)` instead of `ComposeTexts.spliced(answer)` would send model text unscrubbed and uncut.
  - A reviewer would write "make the segment a record".
  Smallest fix:
  - Add `PromptSegment(text: str, spliced: bool)` to `vidbyte/lib/dataclasses/native_compose.py`. Make it frozen and slotted, and check it with `require_text(..., allow_blank=True)` and `require_bool`.
  - Type frames as `tuple[PromptSegment, ...]`, and build fixed text through one `ComposeTexts.fixed(value)` beside `ComposeTexts.spliced`.
  - Return a small record from `AnswerDecoders.read`, and return the checked `EnsembleRoster` from `ThreadEnsembles._roles`.
  Spec IDs: n/a (INV-4, INV-18 and D-28 behavior unchanged)

R-V3 [Blocker] [weighted word: ledger 10] vidbyte/lib/constants/native_compose.py:277 — A sentence addressed to the model lives in Python
  Evidence:
  - `COMPOSE_TRUNCATED_PROBLEM = "The answer was cut at the length limit, so it was not read. Answer again with a shorter JSON object."`
  - `answers.py:124-125` returns it as the problem that `json_repair.md` splices after "Your last answer could not be used: {problem}".
  - `json_repair.md` already says "Reply again with exactly one JSON object ..." at `:4` and "fix what the problem names" at `:7`.
  - The `texts.py` header, WHAT NOT TO DO item 1, says "every sentence to a model comes from a prompt file (INV-20)".
  Failure:
  - request.md §D lists ledger 10 as a weighted word: "every sentence addressed to a model lives in a `prompts/*.md` file loaded by a small library module".
  - INV-20: "Every text compose sends to a model comes from the 22 Markdown files in the compose `prompts` folder." FR-16 says the same.
  - `field-guide/vidbyte-cli/agent-stage-prompts.md`: "No `.py` file in the service may contain a sentence addressed to a model."
  - The other five `*_PROBLEM` constants and JsonText's errors describe the answer, and the spec allows them as data (spec line 389). This constant alone gives the model an instruction.
  - A reviewer would write "prompt text in a .py file".
  Smallest fix:
  - Drop the second sentence, leaving "The answer was cut at the length limit, so it was not read." If the "shorter" cue matters, say it in `json_repair.md`.
  - This is test-safe: `test_harness_compose_answers.py:157` reads the constant through `pack.longest_literal`.
  Spec IDs: FR-16, INV-20

R-V4 [Blocker] [AGENTS.md principle 5] vidbyte/harnesses/native/compose/git.py:45 — The longest-first key scrub is written twice in compose and once in hostkit, instead of once in vidbyte/lib
  Evidence:
  - `git.py:45-48`:
    - `bound = sorted(set(keys), key=len, reverse=True)` feeds `ComposeFailures._replace`.
    - That loop, at `:72-76`, runs `text = text.replace(key, native_compose.COMPOSE_REDACTED_KEY)`.
    - The result then goes through `str(HarnessRedactor().redact(printed))[-native_compose.COMPOSE_GIT_MESSAGE_MAX_CHARS :]`.
  - `texts.py:114` repeats `sorted(set(keys), key=len, reverse=True)`, and `PromptFitter._scrub` (`:162-168`) runs the same loop.
  - The base `vidbyte/harnesses/native/hostkit/errors.py:58-61` runs `for secret in sorted(self._secrets, key=len, reverse=True): text = text.replace(secret, native_threads.NATIVE_REDACTED)`, then `str(self._redactor.redact(text))[-limit:]`. `ComposeFailures.error` repeats this algorithm line for line.
  - The two markers differ: `NATIVE_REDACTED` is "<redacted>" and `COMPOSE_REDACTED_KEY` is "[redacted]".
  Failure:
  - The rule is AGENTS.md principle 5: "Before you write logic like this, look in vidbyte/lib/ for a helper that already does it ... If none exists, create the helper in vidbyte/lib/ rather than inside the feature that first needs it ... whenever a canonical helper in vidbyte/lib/ would save writing the same logic a second time, build it that way."
  - INV-32 forbids compose from importing hostkit, which is exactly why the helper belongs in lib.
  - A reviewer would write "this is NativeErrorFactory.scrub again, twice".
  Smallest fix:
  - Add one static helper in `vidbyte/lib/util/`, beside `CredentialKeyPolicy`, for example `SecretText.replace_all(text, secrets, marker) -> str`.
  - Call it from `ComposeFailures.error` and `PromptFitter.fit`, and delete `_replace` and `_scrub`'s loop.
  - Moving hostkit onto the helper is a follow-up PR, because hostkit is untouched code here. D-28 is unchanged.
  Spec IDs: n/a

R-V5 [Blocker] [field-guide: blocking-lint-invariants A007] vidbyte/harnesses/native/compose/verify.py:104 — Validator floors and derived caps are written as literals beside named caps
  Evidence:
  - Literal floors:
    - `verify.py:104` `StepRoles.counted(verifiers, ..., minimum=1, maximum=native_compose.COMPOSE_MAX_VERIFIERS)`
    - `stages.py:96` `minimum=1, maximum=native_compose.COMPOSE_MAX_STAGES`
    - `native_ensemble.py:126` `require_int(self.proposal, ..., minimum=1, maximum=ENSEMBLE_MAX_PROPOSERS)`
    - `native_ensemble.py:110` `min(kept) < 1`
    - `native_compose.py:308` `minimum=0, maximum=STAGE_MAX_RETRIES`
    - `native_compose.py:321` `minimum=0, maximum=STAGE_MAX_LADDER`
  - `native_ensemble.py:95` has the message "must hold 1 to {ENSEMBLE_MAX_PROPOSERS}", although `ENSEMBLE_MIN_PROPOSERS` exists and `:51` uses it.
  - Literal derived caps: `native_compose.py:193` `max_items=1 + COMPOSE_JSON_REPAIR_TURNS` and `:334` `max_items=1 + STAGE_MAX_RETRIES`.
  - `COMPOSE_MIN_CHAIN_STEPS` and `ENSEMBLE_MIN_PROPOSERS` show the named pattern in this same PR.
  Failure:
  - The rule is the A007 entry in `field-guide/vidbyte-sdk/blocking-lint-invariants.md`: "For a validator, name the floor next to its cap in vidbyte/lib/constants/<domain>.py (CLAUDE_MAX_TURNS_MIN beside CLAUDE_MAX_TURNS_LIMIT), even when the floor is 1". It comes from the PR #1044 resolution of `minimum=1`.
  - Two §12.4 lines say "takes every bound from vidbyte/lib/constants/native_compose.py" and "Numbers are named constants — A007".
  - The A007 lint stays at 255 only because it matches whole words from a short list (`OPERATIONAL_TOKENS` in `lint/rules/a007_operational_constants.py`: `retry`, `attempt`, `limit`, `depth` and ten more), and these names say `retries`, `rung`, `proposal`, `verifiers`, `stages`, `turns` and `kept`.
  - The owner would repeat the #1044 comment.
  Smallest fix:
  - Add these to `vidbyte/lib/constants/native_compose.py` and use them:
    - `COMPOSE_MIN_VERIFIERS = 1`
    - `COMPOSE_MIN_STAGES = 1`
    - `STAGE_MIN_RETRIES = 0`
    - `STAGE_BASE_RUNG = 0`
    - `ENSEMBLE_MIN_PROPOSAL_NUMBER = 1`
    - `COMPOSE_JSON_MAX_TURNS = 1 + COMPOSE_JSON_REPAIR_TURNS`
    - `STAGE_MAX_ATTEMPTS = 1 + STAGE_MAX_RETRIES`
  - Use `ENSEMBLE_MIN_PROPOSERS` in EnsemblePlan's check and message.
  Spec IDs: n/a (§12.4)

R-V6 [Blocker] [AGENTS.md principle 1] vidbyte/harnesses/native/compose/git.py:175 — add_worktree calls remove_worktree, which calls _run, _delete and _failure: a two-level chain inside ComposeGit
  Evidence:
  - At `git.py:170-175`, `except BaseException:` leads to `await asyncio.shield(asyncio.ensure_future(self.remove_worktree(folder)))`.
  - At `:185-193`, `remove_worktree` calls `self._run(...)`, `self._delete(folder)` and `self._failure(...)`.
  - The chain detector prints `ComposeGit.add_worktree -> remove_worktree -> ['_delete', '_failure', '_run']`. That is its only hit across the 13 compose modules and the 3 lib modules.
  Failure:
  - The rule is AGENTS.md principle 1: "a function may call another of its own functions, but that second function should not call a third ... lift that call up into the main function".
  - §12.4 says "Call chains are one level deep".
  - A reviewer would write "flatten this".
  Smallest fix:
  - Make `DisposableWorktree.__aenter__` the one place that cleans up; its `except BaseException` block already runs `remove_worktree`.
  - Have `__aenter__` make the folder (expose `_folder` as `make_folder`), then call `add_worktree(folder)` and a new `fill_worktree(folder, tree)` (the `read-tree -u --reset` step) inside that block.
  - `add_worktree` then needs no `except` path of its own.
  Spec IDs: n/a (§12.4 call-chain line)

R-V7 [Blocker] [field-guide: comment-format] vidbyte/harnesses/native/compose/selection.py:73 — 24 comment lines in six compose modules run past 72 columns, plus 22 lines in the new tests
  Evidence:
  - Compose modules, from the comment-width check:
    - chain.py: 4 lines (69, 101, 102, 110)
    - ensemble.py: 6 lines (58, 101, 125, 127, 165, 243)
    - selection.py: 4 lines (72, 73, 74, 88); line 73 is 77 columns
    - stages.py: 4 lines (64, 67, 112, 113)
    - texts.py: 1 line (105)
    - verify.py: 5 lines (56, 65, 74, 117, 127)
  - Tests: conftest.py has 6 lines (up to 86 columns), test_harness_compose_answers.py has 4 (up to 95 columns), and 8 more files have 12 between them.
  Failure:
  - The rule is in `field-guide/vidbyte-sdk/comment-format.md`: "Wrap every comment line at 72 columns, counting the indent". Its Check is that the awk/grep width test prints nothing for the files you touched.
  - §12.4 says "Comment blocks are at most 72 columns".
  - The owner wrote this lesson after rejecting wide comment blocks ("stop writing comments like this").
  Smallest fix: Rewrap the 46 lines, most of which are one word over, and rerun the check until it prints nothing.
  Spec IDs: n/a (§12.4 narration line)

R-V8 [Minor] [naming] vidbyte/harnesses/native/compose/stages.py:69 — The attempt list is named `tried` to dodge A007, although the natural name `attempts` also passes
  Evidence:
  - `stages.py:69` `tried: list[StageAttempt] = []` and `:79` `StageOutcome(attempts=tuple(tried))`.
  - The S3 report, line 302, says "A007 forbids literals near names such as `attempt`, so stage attempts are named `tried`."
  - Running the A007 analyzer on in-memory renames gives 0 findings for `tried`, 0 for `attempts` and 4 for `attempt`.
  Failure:
  - A007's own will_not_work list includes "Renaming the local variable while leaving a numeric literal at the boundary".
  - The house style asks for "names that say what things mean". The record field is `StageOutcome.attempts`, so a reviewer would ask why the local name differs.
  Smallest fix: Rename `tried` to `attempts`, which gives 0 A007 findings.
  Spec IDs: n/a

R-V9 [Minor] [docs] REPO_MAP.md:161 — The new map sentence says the other steps "only read", which D-27 contradicts for chains, handoffs and stages, and its "It" reads as the hostkit subfolder
  Evidence:
  - The sentence follows "...lives once in a `hostkit` subfolder." It reads: "It also holds composites that chain, verify, hand off, stage and ensemble these thread calls, with exactly one step writing to the workspace at a time while the others only read."
  - D-27 says "`chain_threads`, `handoff_thread` and `run_staged_threads` are sequential pipelines in which each step may write".
  - Two other docs already say it correctly: the README bullet ("One step writes at a time.") and the `native/__init__.py` header ("with one writing step at a time").
  Failure:
  - AGENTS.md › Repository Map says a wrong map entry is regenerated from the tree, and the §12.4 REPO_MAP line allows one general sentence. This sentence has the right form but is wrong on two counts.
  - As written, the sentence tells a reader that compose sits in hostkit and that chain steps are readers.
  Smallest fix: Replace it with "The folder also holds composites that chain, verify, hand off, stage and ensemble these thread calls, and never let two steps write to the workspace at once."
  Spec IDs: n/a (§12.5 row 27; D-27)

R-V10 [Minor] [A001 headers / narration] vidbyte/harnesses/native/compose/git.py:6 — Three small slips in headers and narration
  Evidence:
  - The FUNCTION INVENTORY at `git.py:6` names every ComposeFailures and ComposeGit method except `_replace`. Across 16 files, the inventory check prints only "NOT IN INVENTORY: vidbyte/harnesses/native/compose/git.py :: _replace".
  - At `compose/__init__.py:8`, WHAT NOT TO DO item 2 names 19 internal classes and omits JsonAnswers, DiffCapture and DisposableWorktree.
  - At `workspace.py:49-63`, `DiffCapture.__aenter__` and `__aexit__` have no step comments. §12.4 names "the enter and exit of DiffCapture and DisposableWorktree" as main functions to narrate; DisposableWorktree's are narrated.
  Failure:
  - The agentic-engineering file-header obligation requires headers that describe the file accurately.
  - §12.4 applies AGENTS.md principle 2 to these methods.
  - A reviewer would point at each slip.
  Smallest fix:
  - Add `_replace` to git.py's inventory.
  - Complete the class list, or write "every class in this package".
  - Add a one-line step comment to each step of the two DiffCapture methods.
  Spec IDs: n/a (§12.4 A001 and narration lines)

R-V11 [Minor] [prompts] vidbyte/harnesses/native/compose/prompts/verdict_schema.md:10 — The verdict schema never says `findings` has a limit, so a verifier learns about the cap only from a failed turn
  Evidence:
  - `verdict_schema.md:10` says "`findings` holds one string per concrete problem the change must fix ... it is an empty list when you found none."
  - `native_compose.py:226` calls `to_tuple(self.findings, ..., max_items=COMPOSE_VERDICT_MAX_FINDINGS)`, and the cap is 50.
  - The round and plan schemas state their counts through `{target}` and `{roles}`.
  Failure:
  - §12.4's prompt line cites `field-guide/vidbyte-sdk/prompt-families.md`, which says "Put no numeric limits in prose; say they are enforced and that a refusal names them".
  - `vidbyte-cli/agent-stage-prompts.md` says "For each schema field with a count bound, the prompt says the number too".
  - This is only Minor because the prompt-families entry's "When" names `vidbyte/prompts/prompts/`.
  Smallest fix: Add one sentence to `verdict_schema.md`, with no number, saying that the number of findings is limited and that an answer over the limit is refused with the limit named.
  Spec IDs: n/a (§12.4 prompt line)

R-V12 [Minor] [duplication] vidbyte/harnesses/native/compose/steps.py:193 — Three one-line rules are written out again where a helper already exists
  Evidence:
  - The workspace check `os.path.normcase(str(...workspace))` appears at `steps.py:193`, `steps.py:206`, `chain.py:133`, `chain.py:138` and `calls.py:43`.
  - The unanchored-fork test `verb is NativeThreadVerb.FORK and thread_id is None` appears at `steps.py:93` and `:161`, and inverted at `:191`. `StepRoles.unanchored` sits right beside them at `:167`.
  - The template field-name set `{name for _literal, name, _spec, _conversion in string.Formatter().parse(...)}` appears at `chain.py:128` and `stages.py:104`, although `validation.py`'s `require_template` already computes it.
  Failure:
  - The house style is to write shared logic once.
  - These are one-liners inside one feature, so this is consistency only. Still, changing how a workspace is identified (for example, resolving it first) would take five edits.
  Smallest fix:
  - Call `StepRoles.unanchored` in `invoke`, `anchored` and `fork_role`.
  - Add one helper that returns the normalized workspace key, `os.path.normcase(str(workspace))`, and use it at all five sites. `fork_role` and `same_workspace` compare two keys, while `ThreadChains._gits` and `GrokWorkspaceLocks.slot` index by one.
  - Expose `RecordFieldValidator.template_fields(value)` and use it in chain.py and stages.py.
  Spec IDs: n/a

VERIFIED CLAIMS:
- S3 "SDK-LINT PASS": held. `py -3.11 lint/run.py` exits 0 with "SDK-LINT: PASS".
- S3 "TID251 5, I001 223": held.
- S3 "276 compose tests pass": held. 276 were collected, and 279 passed together with the static-policy file.
- S3 "13 compose modules total 2,218 lines, largest ensemble.py 260": held. Every module is under NFR-4's 500-line cap (base NFR-2).
- S3 report line 302, "A007 forbids literals near names such as `attempt`, so stage attempts are named `tried`": half held. The singular `attempt` gives 4 findings, but the plural `attempts` gives 0, so the rename was unnecessary (R-V8).
- `native_compose.py:5` and `native_ensemble.py:5`, "Every check ... goes through RecordFieldValidator and RecordFieldConverter": did not hold (R-V1).
- `texts.py` header, WHAT NOT TO DO item 1, "every sentence to a model comes from a prompt file (INV-20)": did not hold (R-V3).
- §12.4 "Comment blocks are at most 72 columns": did not hold (R-V7).
- §12.4 "Call chains are one level deep, and there are no nested functions": half held. An AST walk finds no nested function or lambda, but there is one two-level chain (R-V6).
- §12.4 "no number written into prose ... Every number arrives through a placeholder": held for all 22 files.
- `git.py` ARCHITECTURE NOTE, "the 15 repository-location variables removed": held (`len(COMPOSE_GIT_CLEARED_VARIABLES) == 15`).
- The TESTS line in `vidbyte/lib/util/__init__.py`, "test_harness_compose_answers.py covers JsonText": held (5 references).
- Every A001 TESTS path exists, and every FUNCTION INVENTORY names every def: held, except for `_replace` in `git.py` (R-V10).
- §12.4 A003 line for ThreadComposeError: held. `DIAGNOSTIC_FIELDS` is a literal of 8 names, and each field is an attribute and in `details`.
- §12.4 limit of 40,000 characters for the README: held (14,848 characters; A009 CLEAN).
- The fake_harness.py edit is allowed: held. Spec §13 says the stand-in may be "extended if needed", with scenario fields read through `.get` and a default. Its header and the README log were updated.
- Commit hygiene: held. All 55 commits carry Co-Authored-By. Every feat, fix, test and docs(harnesses) commit cites its W-/FR-/AC- IDs, and the 20 commits with no ID are all docs(spec) pipeline-state records. No committed path matches a cache, log, key or env pattern.

COMMANDS RUN:
- `py -3.11 lint/run.py` → exit 0.
  - Final lines: "S063 IMPROVED 4 -> 3 ...", "S064 RATCHETED: 4 known finding(s) ...", "SDK-LINT: PASS".
  - RATCHETED at baseline: A001 642/642, A003 36/36, A006 34/34, A007 255/255 and C008 45/45. A009 is CLEAN.
  - Every IMPROVED row (A002, C011, S001, S010, S025, S061, S063) predates this PR.
- `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache --statistics` → "223 I001 [*] unsorted-imports" / "Found 223 errors."
- `py -3.11 -m ruff check pyproject.toml vidbyte --config lint/ruff.toml --select TID251 --no-cache --statistics` → "5 TID251 banned-api" / "Found 5 errors."
- `py -3.11 -m ruff check vidbyte/harnesses/native/compose <the 5 new lib modules> --config lint/ruff.toml --select I001,TID251 --no-cache` → "All checks passed!"
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/harness_compose tests/features/harness_threads/test_harness_threads_static_policy.py` → "279 passed in 44.76s"
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider --co tests/features/harness_compose` → "276 tests collected in 0.08s"
- `for f in <13 compose + 6 lib modules>; do awk 'length($0) > 72' $f | grep -E '^[[:space:]]*#'; done | wc -l` → "src total: 24". The same loop over `tests/features/harness_compose/*.py` and `fake_harness.py` → "tests total: 22".
- `py -3.11 C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s4conv/a007_probe.py <worktree>` → "list named 'tried': 0 A007 finding(s)" / "list named 'attempts': 0 A007 finding(s)" / "list named 'attempt': 4 A007 finding(s)"
- `py -3.11 C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d2d5110d-c484-4b56-acef-651ebe9a78a5/scratchpad/s4conv/chains.py <worktree>` → "vidbyte/harnesses/native/compose/git.py: ComposeGit.add_worktree -> remove_worktree -> ['_delete', '_failure', '_run']". This was the only line; the tool prints the path with Windows separators.
- AST walk of the 16 new modules for nested FunctionDef, AsyncFunctionDef or Lambda → "done" (no hits).
- FUNCTION INVENTORY check over 16 files → "NOT IN INVENTORY: vidbyte/harnesses/native/compose/git.py :: _replace" (the only line). TESTS path check → 16 "ok" and 0 "MISSING".
- `grep -F -o 'tuple[str, bool]' vidbyte/harnesses/native/compose/*.py | wc -l` → 35. With `-l` → 7 files. Summed `-c` → 27 lines.
- Digit grep over the 22 prompt files (`git show e1bf20d8:<file>`), ignoring numbered-list markers → no output. `git ls-tree` → 22 files.
- `py -3.11 -c "... len(native_compose.COMPOSE_GIT_CLEARED_VARIABLES) ..."` → "cleared vars 15", "prompts fields 22".
- `wc -l vidbyte/harnesses/native/compose/*.py` → "2218 total"; the largest is "260 vidbyte/harnesses/native/compose/ensemble.py". `wc -c vidbyte/harnesses/README.md` → 14848.
- `git log --format='%h %an <%ae> | %s' origin/feat/native-grok-opencode-meta-hosts..e1bf20d8` → 55 commits. A grep of the commit bodies for Co-Authored-By → 55.
- A grep of each commit body in `origin/feat/native-grok-opencode-meta-hosts..e1bf20d8` for a W-, FR-, AC-, INV-, EC-, T-, NFR-, D- or R- ID → 35 commits match. The 20 that do not are all docs(spec) pipeline-state commits, such as "docs(spec): log native-thread-compose S2 rate-limit interruption 8". A grep of `git diff --name-only` for cache, log, key, pem and env patterns → none.
- `PYTHONPATH=$(pwd) py -3.11 -I -c "<RecordFieldConverter.require_instance with collections.abc.Callable on len, a functools.partial and 3>"` → "function ok: True", "partial ok: True", "refusal: ThreadStep.function must be Callable; got a value of type int. {'field': 'ThreadStep.function'}".
- `git status --porcelain` after the runs → only the untracked S4 report files (`?? docs/spec/native-thread-compose/reports/S4-review-*.md`), so the runs wrote nothing else in the worktree.
