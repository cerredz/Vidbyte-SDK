VERDICT: SOUND WITH FIXES — r2 fully resolves round 1's Blocker, but four new problems remain. The fix for one-`/` model IDs admits IDs that send the new vendor's key to another provider. The known-red rule can hide the provider's own failing tests. A rate quote cannot tie a price to its model on real vendor pages. And the permission posture is not stated in terms a person can actually set.

WHAT THE SPEC GETS RIGHT (max 4 bullets, concrete, so the author does not "fix" what works)
- R-1's fix is complete. AC-10, AC-11, AC-12 and INV-23 to INV-26 are PR-time evidence, and §13 forbids any committed test that compares against `base_commit` or a merge-base. Read as a fresh test author, no remaining AC or INV invites such a test. The static ACs (AC-2 to AC-9, AC-13, AC-15) read only the two skill files and `REPO_MAP.md`, so they survive a later `main` and every provider branch. AC-4 checks symbols that provider PRs extend but never remove. The optional lasting guard is accurate: `.claude/ci-settings.json` denies `Bash(git push)` and `Bash(git push *)`.
- FR-11 checks (1) to (3) are deterministic, cheap and correct against the code. `vidbyte/lib/constants/jev.py` `PROVIDER_API_KEY_ENV_VARS` has one entry per line. So "exactly one added `ModelProvider.<E>:` line and no removed line" really does keep `VIDBYTE_MANAGED_TEXT_PROVIDERS` untouched. Check (4)'s strings are exact. `SDK-LINT: PASS` still appears when a known-red test is excepted, because `CiPipeline.run_source` runs `lint/run.py` before pytest.
- D-14's mechanism for one-`/` IDs is right. `lint/rules/s014_provider_model_registry_parity.py` splits each qualified key at the first `/` (`key.partition("/")`) and requires the rest, the full ID, in `MODEL_RUNNER_TYPE_MAP`. Strict `ProviderModelRegistry.validate_model` checks `_catalog_name(id)`, which is `split("/", 1)[1]`, against `known_models()`. So the full ID plus one bare twin is exactly what both need.
- D-2 and EC-58: making the Agent tool a preflight prerequisite gives a clean `STOP PREREQ_MISSING agent-tool` before any side effect. Preflight runs before the first `git worktree add`, and AC-5 keeps preflight free of writes. D-15's symmetric rerun handles both named known-red tests correctly:
  - The harness test fails the same way on both sides (same merge-base), so it is excluded.
  - It skips on a shallow clone on both sides alike.
  - The false-stop rate from the MCP flake drops from about 15% to about 0.7% (0.67 × 0.67³ × 0.33³).

FINDINGS (ranked, most severe first, max 15)

R-1 [Blocker] [L7/L1] §8.1 D-14 (c), §6.3 EC-60, EC-28 — A one-`/` model ID whose first segment names another provider sends the new vendor's key to that provider when the caller omits `provider=`. The spec's own example of an excluded ID is in fact admitted.
  Evidence:
  - D-14 (c) says: "At most one `/` in the ID, and if there is one, its first segment is not the vendor's own slug." EC-60 calls the other-provider case an "Accepted limitation, not a qualification check".
  - EC-28 says: "DeepInfra's `deepseek/deepseek-chat`, which equals an existing qualified key".
  - `vidbyte/lib/runners/utility.py` `Runner._normalize_provider_and_model(None, m)` makes a first segment that is a `ModelProvider` value into the provider.
  - `vidbyte/agents/base.py` `BaseAgent.__init__` matches `api_keys` against that provider (`primary_provider = Runner._normalize_provider_and_model(provider, model_name)[0]`).
  - `ProviderKeyMatcher.accepts_unproven` returns True for every provider outside `FORMAT_BOUND_PROVIDERS` except openai. openai takes any key that starts with `sk-` or `eyJ`.
  - A read-only probe at HEAD (`PYTHONPATH=<worktree> py -3.11`, scratchpad `r2_leak_probe.py`) returned:
    - `ProviderModelRegistry.provider_for_model("deepseek/deepseek-chat")` is None. Main has only the bare `deepseek-chat` and the qualified `deepseek/deepseek-v4-*` and `deepseek/deepseek-flash`.
    - An unprefixed key with an undeclared `deepseek/deepseek-chat` is bound to `deepseek`.
    - An `eyJ…` key with an undeclared `openai/gpt-oss-120b` is bound to `openai`.
    - A `gsk_…` key with an undeclared `openai/gpt-oss-120b` raises `ConfigurationError`.
  Failure: Groq itself is safe. Its keys start with `gsk_`, which openai's table A refuses, so an undeclared call fails loudly and no key moves. But the rule as written admits two kinds of leaking ID:
  - a DeepInfra-style `deepseek/<x>` ID (the spec's own EC-28 example);
  - any `openai/gpt-oss-*` ID from a vendor whose keys begin with `sk-` or `eyJ`. D-13 explicitly sends such vendors to "any".

  Example: a developer copies the model ID from the vendor's docs and writes `Agent(model_name="deepseek/<x>", api_keys=[os.environ["DEEPINFRA_API_KEY"]])`. The SDK binds the DeepInfra key to DeepSeek and sends it to `api.deepseek.com` in DIRECT mode. S014, the gate, the self-check (which declares `provider=s`) and the C6 swap cases (which configure the new vendor) all pass. The PR ships exactly the cross-vendor key leak that the parent session's method exists to catch.
  Smallest fix:
  - Add to D-14 (c): "If the first segment is another provider's value P, the ID is eligible only when this PR gives the vendor a prefix rule, so its keys are reserved from P. The rule is a table F rule (first-party) or a `RESERVED_PREFIXES` entry (secondary source allowed, D-13). Otherwise the ID is ineligible."
  - Add to C6 one case per such ID: the vendor's fake key alone, matched for the provider that `Runner._normalize_provider_and_model(None, <id>)` yields, is refused and never bound to P.
  - Restate EC-60 as the remaining misroute (a loud error; no key moves), and correct EC-28's example.
  - Consequence for Groq: it stays eligible if a `gsk_` rule is sourced. Otherwise its `openai/` IDs end `no-usable-model-id`. gitleaks has no Groq rule, so GitHub's secret-scanning list is the only other allowed source.

R-2 [Major] [L5/L10] §8.1 D-15, §6.3 EC-39 and EC-43, §6.1 INV-15, §6.2 AC-8 — The known-red exclusion can hide the provider's own failing tests, and no step requires the new tests to pass.
  Evidence:
  - D-15 says: "run the test up to 3 times there with `PYTHONPATH=<worktree>-main`; any failure means pre-existing, excluded with both outputs."
  - The tests a provider PR adds or edits sit in files that exist on main, but their nodes are new (C6, C9) or different (C5, C10, B4). On main, `pytest <file>::<new node>` exits 4 with "ERROR: not found".
  - The D-15 order is red-first, self-check, commit, mutation checks, source stage, re-confirmation, package. No step checks that the tests the branch adds or edits pass. EC-43 names a `wire-test` stop, but no step raises it.
  - `<worktree>-main` is created from `origin/main`, a ref that the person's own `git fetch` can move during a run. The brief's `base` SHA is not used.
  - INV-15 and AC-8 count a mutation check as passed when "at least one test outside the table-pinning contract test fail[s]". There is no baseline run on the unmutated tip.
  Failure: A wiring bug leaves the C9 DIRECT wire test red. Then:
  1. The source stage fails, and three reruns on the branch fail.
  2. On `<worktree>-main` the node is "not found" (exit 4), which reads as "any failure".
  3. The test is excluded as pre-existing.
  4. FR-11 check (4) finds `SDK-LINT: PASS` and the smoke line.
  5. A PR whose DIRECT wire test fails is opened and recorded as `PR_OPENED`.

  The same path also excludes a contract test the branch edited (C5) whenever it fails on main for an unrelated reason. And any failure already present in the pack satisfies every mutation check without proving anything.
  Smallest fix:
  - In D-15, exclude a failing test only when two things hold. Its file is byte-identical between `<base>` and `branch_tip` (`git diff --quiet <base> <branch_tip> -- <file>`). And pytest on `<worktree>-main` reports that node as failed, not "not found" and not a collection error.
  - Create `<worktree>-main` from `<base>`, not from `origin/main`.
  - Add one step before the source stage: every test the branch adds or edits passes on the branch. Otherwise the run stops with `PROOF_FAILED wire-test` (for C9) or `gate-source`.
  - In AC-8 and INV-15, run the pack once on the committed tip first. A mutation counts only if a test that passed there fails after the revert.

R-3 [Major] [L3/L1] §6.1 INV-9 (r2 quote cap), §8.1 D-19, §9.1 Groq row — On real vendor pages, a raw-HTML quote of at most 200 characters cannot tie a rate to its model ID, and the natural quote is not in the raw page at all.
  Evidence:
  - INV-9 says: "a verbatim quote that `grep -F` finds in the raw page… In a PR body, each quote is at most 200 characters, contains the fact's value".
  - The §9.1 Groq row says: "in raw HTML on 2026-10-16, `openai/gpt-oss-120b` at "$0.15 input" / "$0.60 output"".
  - Today's raw `curl -sSL` of https://console.groq.com/docs/models returned status 200 and 374,362 bytes. In that file:
    - the ID and its rate are about 1,300 characters apart;
    - the rate appears as `$0.15<!-- --> <span…`, so "$0.15 input" is not in the raw page;
    - `$0.15` occurs twice and `$0.075` occurs four times;
    - the column header is `PRICE PER\n1M TOKENS`, with an escaped newline in the middle.
  - With tags and comments stripped, the same row reads `openai/gpt-oss-120b 500 $0.15 input $0.60 output` (52 characters).
  - Cerebras' raw quote, `` pricing:{inputPrice:`$0.35 / M tokens`,outputPrice:`$0.75 / M tokens`} ``, contains backticks, which break single-backtick inline code (EC-59).
  - The field guide `operation-pricebook-rates.md` warns that a wrong rate that is present is silent, and worse than None.
  Failure: Either outcome is bad:
  - A strict subagent cannot `grep -F` the quote it actually reads, so it ends Groq with `no-first-party-price`. That contradicts the spec's "Expected: eligible".
  - A lenient subagent quotes `$0.15<!-- -->`. That proves only that the number appears somewhere on the page. A rate swapped between rows, or between input and output, passes every check. The PR body cannot show the reviewer which model the rate belongs to, and C009 and B5 then carry the wrong rate.
  Smallest fix:
  - In D-19 and INV-9, also save a text form of each raw page, made by one fixed, recorded command (tags and comments removed, whitespace collapsed; for example a `<py>` one-liner using the standard library's `html.parser`). `grep -F` may check a quote against either the raw page or that text.
  - Require each rate's quote to contain the model ID (or the display name a first-party quote links to it), the rate, and its direction or column header.
  - In the PR body, wrap each quote in a run of backticks longer than any backtick run inside it, and escape `|` in table cells.
  - Correct the Groq row's "raw HTML" wording.

R-4 [Major] [L1/L5] §9.3, §8.1 D-27, §6.3 EC-57, §1 G-3 — The permission posture is not stated in terms a person can set, and the allowlist option cannot work for this procedure.
  Evidence:
  - §9.3 says: "a permission mode or an allowlist … Default: Claude Code's default mode, which prompts". D-27 names only `git`, `gh`, `curl` and the interpreter.
  - Claude Code's first-party docs (code.claude.com/docs/en/permission-modes and /permissions, opened 2026-10-16) say:
    - From v2.1.283, auto mode "is the built-in starting permission mode for interactive terminal and VS Code sessions".
    - `acceptEdits` auto-approves edits only "for paths in the working directory or `additionalDirectories`". The working directories are extended with `--add-dir`, `/add-dir` or `additionalDirectories`.
    - For Bash allow rules, "An allow rule won't match past an assignment of any other variable" than certain known-safe ones.
    - "`cd` with `git`: prompts when the `cd` changes into a different directory".
    - The auto-mode classifier treats PR bodies sent to a public repository as outbound content and blocks "internal file paths".
    - `bypassPermissions` is "Only [for] isolated environments like containers or VMs".
  - The procedure has these properties:
    - Every provider edit lands in `<checkout>-onboard-<slug>`, a sibling directory outside the launch directory.
    - The evidence directory comes from `mktemp -d`.
    - The source stage runs as `PYTHONPATH=<worktree> <py> …`.
    - D-16's proof records carry gate command lines, and a failing stage's last line ends `(cwd=C:\Users\…)` (scratchpad `ci3.log`, `ci4.log`).
  Failure: Two runs show the gap:
  - A person follows the spec, sets `permissions.allow` for `Bash(git *)`, `Bash(gh *)`, `Bash(curl *)` and `Bash(py *)`, and walks away. The subagent's first Edit in the sibling worktree prompts, because it is outside the working directories. `PYTHONPATH=… py scripts/run_ci.py` also prompts, because allow rules do not match past `PYTHONPATH=`. The run waits at the first vendor.
  - A person on the default auto mode gets further, but at publish the classifier can refuse a body that contains `C:/Users/<name>/…` paths on this public repo. The result is `PUBLISH_FAILED pr` after the branch is already pushed.
  Smallest fix: Documentation only, with no new control.
  - In SKILL.md `## Prerequisites and preflight`, and in §9.3, D-27 and EC-57, say:
    - Start `claude` in the checkout with `--add-dir <the checkout's parent directory>` (or `permissions.additionalDirectories`), so the sibling worktrees and their `-main` twins are working directories.
    - Run in auto mode (`--permission-mode auto`, the starting mode from v2.1.283) or in `bypassPermissions` (`--permission-mode bypassPermissions`, which the docs reserve for isolated containers or VMs; T-3's limits apply).
    - An allowlist with `acceptEdits` is not enough, for the two reasons above.
  - Put the evidence directory at a sibling path such as `<worktree>-evidence` instead of `mktemp -d`, or state that writes there may prompt.
  - D-16: the PR body holds no absolute local path and no user name. Write `<worktree>` and `<evidence>` instead.
  - Row 1: git commands use `git -C <worktree>`, not `cd … && git`.
  - Replace EC-57's premise ("default mode prompts") with the current default.

R-5 [Major] [L10/L9] §6.2 AC-1, AC-5, AC-8 versus §8.1 D-20, §6.3 EC-3, §9.2 — Three static criteria contradict the interpreter probe and the install remedy, so a blind test author writes tests that the implementer cannot all satisfy.
  Evidence:
  - AC-8 says: "Every interpreter command in both skill files is spelled with `<py>`, never a bare `python`".
  - D-20 says: "probe `python`, then `python3`, then `py -3.11` … `PREREQ_MISSING python-dev-extras` names `python -m pip install -e ".[dev]"`".
  - AC-5 says `## Prerequisites and preflight` contains "no write command …: no `pip install`". §12.3 row 2 puts the D-20 probe in exactly that section.
  - EC-3 says the STOP comes "with the install command", but the §9.2 form, `STOP PREREQ_MISSING <name>; opened 0 this session`, has no place for it.
  - AC-1 requires SKILL.md to state "the invocation exactly as §4 shows it", and the §4 block contains `python -m pip install -e ".[dev]"`.
  Failure: The S2 author writes:
  - AC-8 as "no command spelled `python` or `python3`";
  - AC-5 as "no `pip install` in the preflight section";
  - AC-1 and §9.2 as exact line forms.

  No placement of the probe and the remedy passes all of these. §14 forbids editing S2's tests, so the implementer stops BLOCKED.
  Smallest fix:
  - AC-8 exempts the three D-20 probe candidates, written once, in one probe line.
  - The remedy is written as `<python 3.11+> -m pip install -e ".[dev]"` and printed on the line after the STOP line. Say this in §9.2 and EC-3.
  - AC-5's scan covers command lines in code blocks only, not the remedy text.
  - AC-1's "invocation" means the single line `/onboard-model-provider`.

R-6 [Minor] [L9/L3] §7 FR-11 check (2), §12.3 row 2, NFR-2 — The orchestrator must compare the diff against the checklist paths, but the spec never says where SKILL.md gets that list.
  Evidence:
  - FR-11 (2) requires that the diff "lists only §12.3 wiring-checklist paths".
  - NFR-2 says the orchestrator "never reads … the per-provider reference itself".
  - Row 2's `## Verifying a result` lists only "the four FR-11 checks and the `<what>` names".
  - The paths exist only in provider-run.md's wiring table, which AC-4 checks.
  Failure: The implementer copies about 17 paths into SKILL.md by hand, and no AC compares that copy with the wiring table. When a row is later added to the wiring table, either every PR that touches the new path stops `RESULT_UNVERIFIED diff-paths`, or the copy silently falls behind.
  Smallest fix: State that SKILL.md builds the path set with one fixed command over the wiring table in `${CLAUDE_SKILL_DIR}/references/provider-run.md`. The command extracts the backticked Path cell of rows `A1` to `D2` and prints only the paths. Add to AC-5 that SKILL.md holds no second copy of the checklist paths.

R-7 [Minor] [L7] §8.1 D-28, §10 T-2 — FR-11 check (4) proves only that the PR body reports the gate, but D-28 claims more.
  Evidence:
  - D-28 says: "Without them, a derailed subagent's PR that breaks INV-14 or skipped the proof would count as verified."
  - Check (4) searches the body for `SDK-LINT: PASS` and `passed smoke checks.`. The subagent writes that body itself, and D-16's template contains both lines.
  - T-2 records prompt injection on Groq's page.
  Failure: A subagent derailed by a vendor page fills in the template without running the gate, and check (4) passes. PRs get no CI, so the person reads a forged gate record before an `--admin` merge.
  Smallest fix: Reword D-28 and T-2. Check (4) catches a body that omits the gate record, not one that fakes it, and the person's review is the control for a faked record. Optional Q-8 [scope-adding]: should the orchestrator re-run the focused provider tests at `branch_tip` itself? The command would be `PYTHONPATH=<worktree> <py> -m pytest tests/features/sdk_provider_keys tests/features/sdk_model_catalog tests/test_agent_pricing.py -q`; it takes about 5 s and keeps one line. Default: not built.

VERIFIED CLAIMS:
- **D-14, the two `MODEL_RUNNER_TYPE_MAP` entries: held.** S014 `RegistryParityAnalyzer.analyze` uses `key.partition("/")` and requires the remainder (the full ID) in the bare map. `ProviderModelRegistry.validate_model` checks `_catalog_name(model)` (`split("/", 1)[1]`) against `known_models()`. `ProviderModelRegistry.provider_for_model("openai/gpt-oss-120b")` is None on HEAD, so Groq's IDs pass (d).
- **EC-60, the routing claim: held, but understated (R-1).** `Runner._normalize_provider_and_model(None, "openai/gpt-oss-120b")` returns `("openai", "gpt-oss-120b", …)`. With `provider="groq"` the ID is unchanged. The key-binding probe shows a leak for `eyJ` keys and unprefixed keys, and a refusal for `gsk_` keys.
- **EC-28's example ("`deepseek/deepseek-chat` equals an existing qualified key"): false.** `provider_for_model` returns None. `vidbyte/lib/constants/runners.py` has the bare key `deepseek-chat` and the qualified keys `deepseek/deepseek-v4-pro`, `-v4-flash` and `deepseek-flash` only.
- **FR-11 / D-28 strings: held exactly.**
  - `lint/core/report.py` prints `SDK-LINT: PASS`.
  - `scripts/run_ci.py` `_smoke_program` prints `Installed vidbyte-sdk {version} passed smoke checks.`
  - `main` prints `CI passed.`, or `CI failed: …` on stderr.
  - `run_source` runs lint first, then compileall, three scripts, and pytest last.
  - Earlier gate logs show pytest takes 1 to 2.5 minutes, well inside the Bash tool's 10-minute limit.
- **§8.5 pass-top commands: held.** I ran each read-only against `origin/main` and live GitHub:
  - the vintage is `2026-10-11`;
  - the members are 14 values, `openai` to `typesafe`;
  - `git ls-remote --exit-code` exits 2 for `feat/provider-cerebras`;
  - the per-slug and open-PR `gh api` queries exit 0 with no rows.
- **§13 optional guard and §12.5 indexes: held.** `.claude/ci-settings.json` `permissions.deny` holds `Bash(git push)` and `Bash(git push *)`. `llms.txt` lists `.claude/` under "Recommended exclusions" near line 1198, and `artifacts/file_index.md` line 6 omits `.claude`. So the `REPO_MAP.md` `.claude/` entry is the only index to change, and the REPO_MAP `skills/` entry needs no change.
- **D-24: held.** The providers README is 40,944 characters (40,954 bytes as a blob; 41,573 bytes in the CRLF working copy). `lint/rules/a009*` `LEGACY_CEILINGS` gives it 55,000.
- **Author's checkers: reproduced after reading them.**
  - `check_checklist_r2.py` gives `rows=33 problems=0`. It checks the cell grammar and that each token appears as a substring at HEAD.
  - `check_ids.py` finds no undefined or duplicate IDs. Withdrawn: AC-14, EC-1, FR-14, A-10.
  - No stale `NO_SUBAGENTS` or inline-fallback text remains.
- **Wiring anchors: held.** `UniqueAssignmentTests.test_an_openai_access_token_beside_a_deepseek_key_is_refused_not_swapped` is in `test_provider_keys_matching.py`. `UnsendableKeyTests.test_a_meta_key_from_a_mixed_list_reaches_meta_unchanged_in_direct` is in `test_provider_keys_modes.py`. The `GatewayShapeTests` tuple form is `("mistral", "mistral-large-latest")`. The README bullets `**Prefixes:**` and `**Other keys:**` are present on `origin/main`.
- **`origin/main` is now `77efd25a`, 18 commits past the base, not `0f779195`/13.** The five newer commits touch:
  - `README.md` (a Working Principles section);
  - `REPO_MAP.md` (the JEV table only);
  - `jev.py` (`JEV_READ_ONLY_THRESHOLD`);
  - `models.py` (`resolve_active` signature);
  - `test_provider_keys_contract.py` (a field layout).

  None touches a checklist symbol or the `.claude/` entry.
- **Seed spot checks (raw `curl`, 2026-10-16):**
  - Groq: the IDs and the rates `$0.15`, `$0.60`, `$0.075` and `$0.30` are present, and the Llama rows carry "Sales". The binding problem is R-3.
  - Cerebras: `inputPrice:` `$0.35 / M tokens` and `outputPrice:` `$0.75 / M tokens` are present, along with a "Tool Calling" heading. Held.
  - gitleaks has a rule for Cohere (unprefixed, 40 characters), but none for Groq or any other seed vendor.
- **Environment: no finding.** The `tests/features/sdk_provider_keys` pack gives `129 passed` both with and without `DEEPSEEK_API_KEY`, which is set in this shell. FEATURE.md's "unset" note is not load-bearing today.
- **Round-1 dispositions:**
  - **R-1:** resolved.
  - **R-2:** partly resolved; the posture is still imprecise (R-4).
  - **R-3:** checks (1) to (3) resolved; gaps remain in the path source (R-6) and in what check (4) proves (R-7).
  - **R-4:** resolved for the named flake; new exclusion holes (R-2).
  - **R-5:** resolved. INV-20, EC-21 and EC-56 agree, and the optional rule's rejection is reasonable.
  - **R-6:** resolved for table F. But R-9's fix opened R-1.
  - **R-7:** resolved, except for the probe and remedy conflict (R-5).
  - **R-8:** resolved. Headings, headers and cell grammar are fixed, and the checker reproduces them.
  - **R-9:** the mechanism holds, but the fix introduced R-1.
  - **R-10:** resolved.
  - **R-11:** resolved, except that `<worktree>-main` should start from `<base>` (R-2).
  - **R-12:** correctly carried as Q-6.
  - **R-13:** resolved in intent, but the cap interacts badly with raw HTML (R-3).
