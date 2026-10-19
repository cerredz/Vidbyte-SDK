# S1 spec review: meta-muse-managed-text r2 (round 2, scoped)

Reviewer: S1 spec reviewer (adversarial), round 2 of 2. This is a read-only review of `spec.md` r2 at worktree HEAD `746b6d4c`. The worktree is clean, and its `vidbyte/`, `tests/`, and `README.md` are byte-identical to `845a4d9b`.

**Scope.** I reviewed only the sections that round 1 changed, plus the sections that depend on them:
- §9.4;
- EC-3, EC-11, and EC-16;
- INV-3, INV-4, INV-5, and INV-9;
- AC-1 and AC-15;
- FR-8;
- §12.3 rows 1(b) and 2(c);
- §12.5;
- the §13 seams;
- A-2 and Q-6;
- §16.

**Probes.** Every probe fakes only the inner HTTP transport and `os.environ`, and widens `VIDBYTE_MANAGED_TEXT_PROVIDERS` in memory. All of them are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/974874d5-52be-49ef-bbf6-f27795eaf01b/scratchpad/`:
- `s1_grader_probe.py` (re-run);
- `s1r2_critic_probe.py` (new);
- `s1r2_env_read_probe.py` (new).

The two new scripts are the only files I wrote besides this report. Both are in the scratchpad, not in the repo.

VERDICT: SOUND WITH FIXES — All six round-1 fixes landed, and the design is still one constant with 0 new files. Two things still need fixing. First, the merge prerequisites now differ between sections. Second, the EC-16 billing disclosure is presented as a complete list, but it misses at least three more fail-open paths and undercounts the billed calls.

## WHAT THE SPEC GETS RIGHT

- **Every round-1 fix landed, and the design did not grow.** Only one production file changes (§12.4). §8.4 still budgets 0 new files, classes, constants, and names. R-4 and R-6 are clean:
  - the Prefixes bullet is at `README.md:290-293`;
  - no test binds that bullet, and only two tests read the root README;
  - A009 exempts `README.md` (`EXEMPT_READMES`);
  - the new comment lines measure 67, 67, 69, and 42 columns;
  - `c395349bd` is on `origin/feat/meta-muse-gateway`, whose remote head is `da96273c0`;
  - §9.2-§9.4 hash the same at both commits.
- **The narrowed invariants can be tested at real seams.**
  - *INV-3 and AC-4:* the probe saw 0 reads of `META_API_KEY` in `VIDBYTE_MANAGED`, on both the runner route and the Agent route. Each request had 3 headers and no Meta key.
  - *INV-5:* its `extra_body` exception matches `compatible.py:131-134`. No agent-layer module has an output-cap setting (grep for `max_output_tokens` in `vidbyte/agents`, `paradigms`, `pipelines`, and `context`: none).
  - *INV-9:* the log seam is real (`test_provider_keys_security.py:50-60`, `:106-121`), and the gateway path has no logger. The trace carve-out also holds: `HarnessRedactor` scrubs a full `LLM|…|…` key, pipes included, in all four forms I tried.
- **The cap citations are accurate (settled; I only checked them).** `VIDBYTE_MANAGED_DEFAULT_MAX_OUTPUT_TOKENS` is at `jev.py:84`, and `text.py:57-62` applies it whenever `credentials.uses_gateway` is true. The grader probe, re-run, again forwarded `max_tokens` 32,768 on the `meta` trial.
- **The R-3 mapping is right, and the live check is reported honestly.**
  - The five template sections in §12.5 match `.github/pull_request_template.md`.
  - The CONTRIBUTING items map onto them: problem to Motivation, compatibility to Compatibility, commands to Verification, docs to Changes, and deferred work to Follow-ups.
  - The live check says "Quote only its status", names whose keys it uses, and says it is listed "as an open merge prerequisite" until someone runs it. So the PR cannot honestly claim the check ran.

## FINDINGS

R-1 [Major] [L9] TL;DR, §2, §9.4, FR-8, AC-15, §12.5, A-3 — The spec gives three different lists of merge prerequisites, and AC-15 (P0) contradicts §12.5

  Evidence. Each section names a different set of conditions:
  - *TL;DR:* "This PR merges only after cerredz/Vidbyte#710 is deployed, and after a live check by the user or ops returns 2xx". The backend key is not mentioned.
  - *§9.4:* "Release ordering: merge after #710 is deployed (EC-15) and after ops provisions the backend's `META_API_KEY` (EC-2)". The live check is not mentioned.
  - *AC-15:* "It states first that it merges only after cerredz/Vidbyte#710 is deployed and after ops provisions the backend's `META_API_KEY`." This makes the backend key a merge gate.
  - *§2, FR-8, the §12.5 ops bullet, and A-3:* "ops must provision the backend's `META_API_KEY` before any SDK release that contains this change". This makes the key a release gate. The §12.5 merge-order bullet names only #710.
  - *Run A's A-7:* "Ops provisions `META_API_KEY` on the backend service after merge and before any SDK release routes `meta`".
  - *The repo:* `.github/workflows/publish.yml` is `workflow_dispatch` plus tag validation, so merging and releasing are separate events.

  Failure. The PR author must write a single "merges only after …" sentence and has three versions to choose from:
  - If they follow §12.5 (#710 to merge, the key before release), the S6 verifier checking AC-15 literally finds no "after ops provisions" merge condition, and AC-15 (P0) fails.
  - If they follow the TL;DR, the backend key is dropped from the merge condition.
  - If they follow AC-15, the live check is missing from the "states first" sentence.

  The user then cannot tell whether they may merge before ops acts.

  Smallest fix. Define one canonical list in a §12.5 "Merge prerequisites" bullet, and have the TL;DR, §2, §9.4, FR-8, AC-15, and A-3 repeat it word for word. I recommend AC-15's stricter form:
  1. #710 is deployed.
  2. Ops has provisioned the backend's `META_API_KEY`.
  3. The pre-merge live check returned 2xx.

  The reason for item 2: publishing is a manual, tag-based dispatch from main. After this PR merges, any release cut from main routes `meta`, so merge is the last point this PR can enforce Run A's A-7 order. If the author prefers to keep the backend key as a release-only gate, change AC-15 and §9.4 to match instead. Either choice works if every section says the same thing.

R-2 [Major] [L5/L1] EC-16, §9.4, §12.5 behavior-change bullet — The billing disclosure is a closed list that misses at least three fail-open paths, says "one more billed Muse call" when a member is a whole agent loop, and misstates who pays for forks and handoffs

  Evidence. Five problems:

  1. **The closed list misses three fail-open paths.** EC-16's trigger is a composition that "runs members concurrently and silently drops a member that raises". §12.5 tells the PR author: "These are the multi-provider grader …, plus aggregate proposers and fanout members that name Muse." I traced every place the SDK builds a runner and found three more paths. At `base_commit` each one silently drops a Muse member in a gateway mode, and after this change each one bills:
     - *Independent critic,* with `reviewer_provider="meta"` and `failure_policy=RETURN_CANDIDATE`. The reviewer runner is built inside the try at `independent_critic.py:79-85` and `:211`.
       - Probe `s1r2_critic_probe.py`, base: 1 `anthropic` request, and the metadata says `review_failed`.
       - Widened: the same 1 `anthropic` request, plus **4** `meta` requests that relay `META_API_KEY` with `max_tokens` 32,768.
     - *Prosecutor/defender/judge,* with a stage `provider="meta"` and `failure_policy=RETURN_CANDIDATE`. The stage runner is built in preflight (`prosecutor_defender_judge.py:250`, `:494-496`), and the failure is caught as a stage failure and returned as the candidate (`:457-466`, `:539-541`).
     - *Jev run-brief writer,* with `JevRunBriefSettings(provider="meta")`. `JevRunBriefWriter.write` catches `VidbyteSdkError` and returns `None` (`vidbyte/agents/jev/brief/writer.py:146`, `:160`). `UnsupportedProviderError` and `AgentExecutionError` are both `VidbyteSdkError` subclasses (checked).

     The critic and judge run their stages one after another, so EC-16's word "concurrently" excludes them.
  2. **"One more billed Muse call" undercounts.** EC-16 promises "one more billed Muse call per grader run", and §9.4 says "makes a billed call". But a grader trial, a proposer, a fanout branch, and a critic reviewer each run a full agent loop (`runtime._arun_once`, `multi_provider_agentic_grader.py:96`). The critic probe made 4 billed `meta` calls for one member.
  3. **The PR bullet leaves out the paid case.** It says the grader "relays that key", and nothing more. EC-16 itself says that in `VIDBYTE_MANAGED` the member is Vidbyte-paid (TOTAL), which costs the user more.
  4. **The PR bullet misstates who pays for forks and handoffs.** It says a fork or handoff whose parent holds no Meta key "goes Vidbyte-paid". EC-11 says the child "relays `META_API_KEY` if it is set, and otherwise is Vidbyte-paid".
  5. **The opt-out is only the grader's.** The PR bullet offers "set `provider_models`, or use `DIRECT`". It does not tell aggregate, fanout, critic, judge, or brief users to remove Muse from their member settings.

  Failure. Take a user whose independent critic or judge names a Muse reviewer under `RETURN_CANDIDATE`, or whose JevAgent's brief writer names Muse, in `AUTO` with `META_API_KEY` set. Today their runs quietly skip the review or the brief. After this change, every run makes several billed Muse calls: Meta bills the tokens, and Vidbyte bills its fee. The PR's Compatibility section, which the author was told to fill from a closed list, never mentions this. A grader user is told "one more call" and finds several.

  Smallest fix. This changes text only, and no settled decision.
  - Restate EC-16's trigger as "a gateway-mode composition that tolerates a failed member or stage". Add the three paths above to its examples, and cite `s1r2_critic_probe.py`.
  - Replace "one more billed Muse call" with "one more Muse member run, which is an agent loop of one or more billed calls" in EC-16, §9.4, and §12.5.
  - In the §12.5 bullet:
    - write "for example" before the list;
    - add "in `VIDBYTE_MANAGED`, Vidbyte-paid (TOTAL)";
    - make the fork and handoff text match EC-11: it relays `META_API_KEY` when that is set, and is Vidbyte-paid otherwise;
    - give the general opt-out: leave Muse out of member and stage settings, set `provider_models`, or use `DIRECT`.

  Q-6 can stay as it is.

R-3 [Minor] [L10/L11] §12.5 pre-merge live check, A-2, EC-3 — The check's failure rule cannot be applied with what the SDK shows, and the spec does not say where to run the check or what it may leave behind

  Evidence. §12.5 says: "A 400 that names the output limit flips D-3 before merge." But for a relayed 400, the SDK reports only "meta returned HTTP 400 through the Vidbyte gateway; the provider's message is withheld, … check your own meta key in api_keys or META_API_KEY" (`vidbyte_gateway.py:100-104`; INV-8, AC-9). So the person running the check cannot see whether the 400 "names the output limit".

  The spec also leaves out three things:
  - The check must run on this branch's code. The released `vidbyte-sdk` 0.3.0 refuses `meta` in `AUTO` when the config is built.
  - The check commits nothing and writes no file. The briefing asked for this to be stated.
  - It does not say who records the result in the PR.

  A D-3 flip adds a constant in `jev.py` and edits `text.py`. §14 puts both under "Ask first", and both exceed §8.4, so a flip cannot happen inside this PR as approved.

  Failure. The check returns 400. The person running it cannot apply the rule as written, and the "check your own meta key" hint points them at the wrong cause. Or they run the example from the PyPI release, get `UnsupportedProviderError`, and record a false failure.

  Smallest fix:
  - Run the check from a checkout of this PR's branch. It commits nothing and writes no file.
  - Make two calls with the same keys: the capless call (`max_tokens` 32,768) and a control call with `max_output_tokens=1024`.
  - Pass: the capless call returns. A-2 is false when the capless call raises `ProviderRequestError` with `status_code` 400 while the control call returns.
  - Any other status (422, 401, 402, or 502) is a setup problem, not a verdict on A-2.
  - Whoever runs the check posts both statuses in the PR's Verification section.
  - A false A-2 keeps the PR unmerged. The D-3 flip then needs the user's approval and a spec revision.

R-4 [Minor] [L8] §12.5 PR-template mapping — "Tick the template's checklist only for what was run" lets the author tick a box that is false

  Evidence. The template's first checklist item is "Existing repository checks pass." But NFR-5 and §12.4 expect one pre-existing red test (`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`). CONTRIBUTING.md:72 also says "A change is not ready for review while any local gate … is red."

  Three §12.5 PR-body bullets have no template section: "served Muse ids", "cap evidence", and "pre-existing red".

  Failure. The author runs the gate, which fails on the known test, and ticks "Existing repository checks pass" because that check "was run". A reviewer flags it.

  Smallest fix:
  - Change "only for what was run" to "only for what holds". Leave the first item unticked and name the known red test beside it. Mark the wheel item N/A, because no package asset changes.
  - Map the three bullets: served Muse ids to Compatibility, cap evidence to Changes, and pre-existing red to Verification.

R-5 [Minor] [L10] §6.1 INV-4 — "whatever it holds is relayed" is broader than the code, so a property test can fail on a correct build

  Evidence. INV-4's exception reads: "`META_API_KEY` is trusted by its name, so whatever it holds is relayed on `meta` calls". But `find_provider_api_key` (`models.py:172-194`) refuses some values before any request:
  - a `vb_live_` value (M-14, EC-9);
  - a value that cannot be sent in a header (M-21, EC-10). A value longer than 512 characters is refused the same way (M-21, EC-10).

  Failure. A blind test author writes a property test over arbitrary `META_API_KEY` values from INV-4 alone. It goes red on a correct build.

  Smallest fix. Append to INV-4's exception: "except a Vidbyte key (M-14) or a value that cannot be sent or exceeds 512 characters (M-21), which are refused before any request (EC-9, EC-10)."

## VERIFIED CLAIMS

**The EC-16 search, `resolve_active` and `return_exceptions=True`.**
- *`resolve_active`:* only the grader calls it (`multi_provider_agentic_grader.py:61`).
- *Environment resolution:* `_resolve_from_environment` (`models.py:418-428`) adds every text provider whose key variable is set. META resolves to `muse-spark-1.1` (`models.py:82`). It ignores the mode, so in `VIDBYTE_MANAGED` it still reads `META_API_KEY` to choose members, which matches INV-3's parenthetical. It is the only path that resolves members from the environment.
- *Model-calling gather sites:* the grader (`:87`), `aggregation.py:97`, and fanout (`types.py:486`, `paradigm.py:147`).
- *Other `return_exceptions=True` sites:* MCP, the skills loader, GitHub skills, the output dispatcher, `multi/cleanup`, and `jev/alignment/skills.py`. The last one uses the TypeSafe decision model, not Muse.
- *Every runner-construction site* (critic `:211`, judge `:250`, grader `:93` and `:147`, `base.py:1663`, `fallback.py:205`, `router.py:39`): only the critic, the judge, and the Jev brief writer add fail-open paths that EC-16 does not list. **Partly held** (R-2).

**Grader probe, re-run.** Base: 2 `anthropic` requests. Widened: `anthropic`, then `meta` relaying `META_API_KEY` with `max_tokens` 32,768, then `anthropic`. **Held.**

**Critic probe.** Base: 1 request, and the critic reported `review_failed`. Widened: 4 more `meta` requests, each relaying `META_API_KEY` with `max_tokens` 32,768. This is **new evidence for R-2.**

**INV-3 and AC-4** (`s1r2_env_read_probe.py`, with the repo's `RecordingEnviron`). In `VIDBYTE_MANAGED`, on both the `TextModelRunner` route and the `Agent` route, `META_API_KEY` was read 0 times. The only variables read were `VIDBYTE_API_KEY` and `PYTHONASYNCIODEBUG`. Each request had 3 headers and no Meta key. **Held.**

**The §13 seams.** **All held.**
- `RUNNER_TRANSPORT_TARGET = "vidbyte.lib.runners.text.HttpTransport"` (`managed_text_fixtures.py:37`), the name `text.py` uses.
- `RecordingHandler` (`test_provider_keys_security.py:50-60`), `LeakScenarioTests` (`:103`), and `run_scenario` (`:106-121`).
- The relay-header redactor test at `:236`.
- `RecordingEnviron` records `get`, `[]`, and `in` (`provider_keys_fixtures.py:124`).
- `K_META` is built by concatenation (`:39`), and `VENDOR_BASES` maps `api.meta.ai` (`:60`).
- No SDK logger sits on the gateway path, and no module sets `propagate = False`.
- `ModalityDetector.create_runner` builds a `TextModelRunner` (`modality_detector.py:147`).

**INV-9.** **Held.**
- `ProviderRequestError` is raised outside any `except` (`vidbyte_gateway.py:217-218`), and `_send` keeps only the exception type. So `__cause__` and `__context__` are both None.
- The `HarnessRedactor` value pattern `[^\s,;]+` includes `|`, so a fake Meta key is fully scrubbed under the header name, under `api_key=`, in a dict, and in a headers line.

**INV-5, D-3, and EC-3.** **Held.**
- `BaseAgent.__init__` (`base.py:91-129`) has no cap parameter, and `_runner_for_model` passes only `timeout_seconds` (`base.py:1662`).
- `max_tokens` is the loop budget (`base.py:317-321`).
- `compatible.py:86-87` writes the cap, and `:131-134` merges `extra_body` last.

**Row 1(b).**
- **Held:** the four lines measure 67, 67, 69, and 42 columns.
- **Held:** `comment-format.md` (72 columns) is a field-guide rule, not a lint rule, and `lint/ruff.toml` selects only TID251.
- **Held:** `c395349bd` is in `origin/feat/meta-muse-gateway`, whose remote head is `da96273c0`, and §9.2-§9.4 are identical at both commits (sha256 `3588bd54…`).
- **Held:** the `jev.py:6` COMMON MODIFICATION PATTERNS names the README section and both packs. The header has no provider count to update. `jev.py:72-81`, `:80` (KIMI), `:84`, and `:113` are correct.

**Row 2(c) and the README.** **Held.**
- The section heading is at `:236`. The Prefixes bullet is at `:290-293`, the Providers bullet at `:337-339`, and the cap sentence at `:343-345`.
- These three bullets plus "Other keys" are the section's only provider lists.
- Only `test_managed_text_acceptance.py` and `test_provider_keys_acceptance.py` read the root README, and neither binds the Prefixes bullet.
- A009 exempts `README.md`, and the file is 88,603 characters.
- `git grep` outside `docs/` and `tests/` finds no other list of gateway-served providers.

**The PR template.** **Held.**
- The template sections are Motivation, Changes, Compatibility, Verification (4 checklist items), and Follow-ups.
- `CONTRIBUTING.md:75-83` says "Use the pull-request template and include: …".
- `publish.yml` is `workflow_dispatch` plus tag validation, so merge and release are separate events. This bears on R-1.

**Run A A-7.** It reads "after merge and before any SDK release routes `meta`" (Run A spec §15). This makes the backend key a release gate, which supports R-1.

**EC-11.** **Held.**
- `fork.py:68` and `handoff.py:68` pass the parent's `runner_config.api_keys`.
- `provider_keys.py:128-136` returns a `ProviderKeys` record after a per-key check, with no M-18 check.

**The two tests that flip.** **Held.**
- `test_provider_keys_modes.py:47` (`SERVED`) and `:218`; its `meta` row is `:223`.
- `test_managed_text_selection.py:245`.
- The comment at `test_provider_keys_modes.py:379`.

**The relayed-400 wording.** It withholds the provider's message (`vidbyte_gateway.py:100-104`). **Held,** and it is the basis of R-3.
