# S3 implementer report: jev-skill-sources

Spec: `docs/spec/jev-skill-sources/spec.md` r4 · Tests: S2 at `d01e0afa` (unchanged: `git diff d01e0afa..HEAD -- tests/` is empty) · Base of S3 work: `bd6d54d4` · Branch: `feat/jev-skill-sources` · Draft PR: https://github.com/cerredz/Vidbyte-SDK/pull/904 · Spec commits: `fae51bf9` (frontmatter), `d6fd75d0` (Proof cells, §17)

## Commits (oldest first)

| SHA | Row(s) | Message |
|---|---|---|
| `ae4d205a` | 1 | feat(enums): add skill source, unavailable reason, and fetch step enums [W-1, W-10; FR-2, FR-13, AC-17] |
| `bd7a3330` | 2 | feat(enums): export the skill source enums from vidbyte.lib.enums [W-11; FR-15, AC-17] |
| `760c0969` | 3 | feat(constants): add the skill-source constants module [W-9; INV-12, INV-19, NFR-1, NFR-4] |
| `7c3a8db4` | 4 | feat(dataclasses): add declarative skill entries and SkillResolution [W-1; FR-1, FR-2, FR-3, INV-2, INV-14, AC-11] |
| `a4cb8206` | 7 | feat(skills): add the agent-agnostic skill loading package marker [W-2; FR-5] |
| `b26cb365` | 9 | feat(skills): add the generic SkillResolver base [W-2; FR-5, INV-9, D-22] |
| `8b96b211` | 10 | feat(skills): add SkillFetch, the bounded GET every networked source uses [W-9; INV-14, INV-19, AC-24, D-9, D-27] |
| `b148ec21` | 11 | feat(skills): add SkillMarkdown, the shared SKILL.md parser [W-9; FR-12, INV-11, INV-18, AC-20, AC-23, D-12, D-13, D-29] |
| `65c2aa04` | 12 | feat(skills): add InlineSkillResolver [W-3; FR-6, AC-3, D-21] |
| `44667cce` | 13 | feat(skills): add LocalSkillResolver with the capped off-loop read [W-4; FR-7, AC-4, D-6, D-15, D-21, D-23] |
| `16559214` | 14 | feat(skills): add SkillsShSkillResolver with the lock source check [W-5; FR-8, AC-5, AC-6, D-16, D-17, D-21, D-29] |
| `e9ee12d3` | 15 | feat(skills): add GitHubSkillResolver with shared lookups and _GitHubAnswer [W-6; FR-9, NFR-3, AC-7, AC-13, AC-22, D-10, D-11, D-18, D-30, D-31] |
| `cfbdfc48` | 16 (+3) | feat(skills): add VendorSkillResolver, the shared Skills API base [W-7, W-8; FR-10, FR-11, INV-12, INV-15, D-10, D-11, D-19, D-20, D-29, D-30] |
| `73a268f2` | 17 | feat(skills): add AnthropicSkillResolver [W-7; FR-10, AC-8, D-19] |
| `442e3fd5` | 18 | feat(skills): add OpenAISkillResolver [W-8; FR-11, AC-9, D-19] |
| `181f6868` | 19 | feat(skills): add SkillLoader with per-agent memory and grouped resolution [W-2; FR-4, FR-5, INV-4 to INV-7, INV-9, INV-10, AC-10, AC-15, AC-18, AC-27] |
| `9c35c77d` | 8 | docs(skills): add the skill sources package README [W-12; FR-16] |
| `5438110e` | 20 | feat(jev): JevSkillResult carries reason and detail for unavailable skills [W-10; FR-13, INV-17, AC-17] |
| `b4164134` | 21 | feat(jev): JevAlignmentSettings.skills accepts skill entries beside documents and strings [W-1; FR-1, FR-3, INV-3, INV-20, AC-1] |
| `830f9860` | 22 | feat(jev): skill preload loads entries through SkillLoader and explains every unavailable skill [W-10; FR-13, FR-14, INV-16, INV-17, INV-22 to INV-26, AC-3, AC-14, AC-16] |
| `3a4cb929` | 5, 6, 23, 24, 25 | feat: export the skill entries and skill enums from the public package roots [W-11; FR-15, INV-21, AC-17] |
| `a66e7819` | 26 | chore(contracts): regenerate the public API contract with the nine skill names [W-11; FR-15, AC-17] |
| `2c19a646` | 27 | docs: map vidbyte/agents/skills/ and count it among the skills locations [W-12; FR-16] |
| `7db15ea0` | 30 | docs(agents): list the skills/ loader under Key Modules [W-12; FR-16] |
| `429c77e9` | 28 | chore(lint): lower the A001 baseline to 642 after the skills enum header upgrade [W-12; NFR-6] |

Every commit message ends with the `Co-Authored-By: Claude Opus 5.5` trailer.

## Data-flow build order

Bottom layer first, so each commit imports only what already existed:
enums (rows 1, 2) → constants (row 3; imports the reason enum) → entry records and `SkillResolution` (row 4) → package marker and generic resolver base (rows 7, 9) → the shared bounded GET and the shared `SKILL.md` parser (rows 10, 11) → the six resolvers (rows 12–18; local before skills.sh, the vendor base before Anthropic and OpenAI) → `SkillLoader` (row 19) → package README (row 8) → `JevSkillResult` (row 20) → settings (row 21) → preload (row 22) → five export roots in one commit (rows 5, 6, 23–25) → contract regenerated from the committed tree (row 26) → repo map, agents README, A001 ratchet (rows 27, 30, 28).

## §12.3 rows

- [x] 1 `vidbyte/lib/enums/skills.py` — three enums, A001 header (`ae4d205a`)
- [x] 2 `vidbyte/lib/enums/__init__.py` (`bd7a3330`)
- [x] 3 `vidbyte/lib/constants/skills.py` (`760c0969`, `cfbdfc48`) — see deviations 1 and 2
- [x] 4 `vidbyte/lib/dataclasses/skills.py` (`7c3a8db4`) — `SkillDocument` byte-for-byte unchanged
- [x] 5 `vidbyte/lib/dataclasses/__init__.py` (`3a4cb929`)
- [x] 6 `vidbyte/lib/__init__.py` (`3a4cb929`)
- [x] 7 `vidbyte/agents/skills/__init__.py` (`a4cb8206`)
- [x] 8 `vidbyte/agents/skills/README.md` (`9c35c77d`; 7,268 characters, no `## File Index`)
- [x] 9 `vidbyte/agents/skills/resolver.py` (`b26cb365`)
- [x] 10 `vidbyte/agents/skills/fetch.py` (`8b96b211`)
- [x] 11 `vidbyte/agents/skills/markdown.py` (`b148ec21`)
- [x] 12 `vidbyte/agents/skills/inline.py` (`65c2aa04`)
- [x] 13 `vidbyte/agents/skills/local.py` (`44667cce`)
- [x] 14 `vidbyte/agents/skills/skills_sh.py` (`16559214`)
- [x] 15 `vidbyte/agents/skills/github.py` (`e9ee12d3`) — see deviation 3
- [x] 16 `vidbyte/agents/skills/vendor.py` (`cfbdfc48`)
- [x] 17 `vidbyte/agents/skills/anthropic.py` (`73a268f2`)
- [x] 18 `vidbyte/agents/skills/openai.py` (`442e3fd5`)
- [x] 19 `vidbyte/agents/skills/loader.py` (`181f6868`)
- [x] 20 `vidbyte/lib/dataclasses/jev.py` (`5438110e`)
- [x] 21 `vidbyte/agents/jev/settings.py` (`b4164134`)
- [x] 22 `vidbyte/agents/jev/alignment/skills.py` (`830f9860`)
- [x] 23 `vidbyte/agents/jev/__init__.py` (`3a4cb929`)
- [x] 24 `vidbyte/agents/__init__.py` (`3a4cb929`)
- [x] 25 `vidbyte/__init__.py` (`3a4cb929`)
- [x] 26 `contracts/sdk-public-api.json` (`a66e7819`; 615 exports, nine added, none removed)
- [x] 27 `REPO_MAP.md` (`2c19a646`)
- [x] 28 `lint/baseline.json` — A001 643 → 642, no other key (`429c77e9`)
- [ ] 29 `tests/features/jev_skills_preload/FEATURE.md` — owned by S2, not touched
- [x] 30 `vidbyte/agents/README.md` (`7db15ea0`)

§12.4 checklist: every item checked by lint, semgrep, the tests, or a grep over the diff (no `HTTPStatus(` call, no `vb_live_`, no `# noqa`, no `# type: ignore`, no TODO, no subprocess, no `asyncio.Lock`, no `TypedDict`, no `extractall`/`read_text(`/`read_bytes(`, `follow_redirects=False` only; no `vidbyte.lib` module imports `vidbyte.agents` outside the pre-existing `TYPE_CHECKING` block in `jev.py`; no `vidbyte/agents/skills/` module imports `vidbyte.agents.jev` or the `vidbyte.agents` root). Longest new or changed function: `JevSkillsPreload.run`, 47 lines. Largest new file: `vendor.py`, 213 lines.

§12.5: package README (row 8), agents README line (row 30), repo map (row 27), five export roots and contract (rows 2, 5, 6, 23–26), A001 ratchet (row 28), and the four module headers (`vidbyte/lib/enums/skills.py`, `vidbyte/lib/dataclasses/skills.py`, `vidbyte/agents/jev/alignment/skills.py`, `vidbyte/agents/jev/settings.py`) are done; row 29 is S2's.

## Deviations from the spec

1. **`GITHUB_CREDENTIAL_ENV_VAR` instead of `GITHUB_TOKEN_ENV_VAR`** (row 3, rows 15). The value is still `"GITHUB_TOKEN"`. Lint S054 includes ruff S105, which flags any name matching `(^|_)token($|_)` assigned a string literal as a hard-coded password. Renaming is the only fix that adds no suppression. No test imports the constant by name.
2. **Extra constant `SKILL_ARCHIVE_MARKDOWN_COUNT = 1`** (row 3, committed with row 16). The zip check "exactly one `SKILL.md`" sits inside a `with` block that also calls `archive.read`, so lint A007 flags a bare `1` there.
3. **`_raw_document` (one entry per call) instead of `_raw_documents`** (row 15). `resolve` gathers one `_raw_document` per entry, so the S063 gather and its `BaseException` re-raise live in the narrated main function, and the step leaf stays one level deep.
4. **`SkillText` parameter named `field_name`, not `field`** (row 4). The module imports `dataclasses.field`, and a parameter named `field` would shadow it.
5. **Row 20 is committed before row 22** (`5438110e`, then `b4164134`, then `830f9860`). At `5438110e` and `b4164134`, `tests/test_jev_skill_preload.py` is red, because the new INV-17 check rejects the preload's reason-less `UNAVAILABLE` results. It is green from `830f9860` on. §12.6 puts both rows in P3.
6. **Four `JevSkillsPreload` helpers.** `_unbatched(batches)` and `_failed_batch(batch, detail)` were added beside the existing helpers. They keep `run` at 47 lines and keep the four §9.2 detail strings inside methods, because JEV modules may not hold module-level constants. A loaded skill's starting result is `_score_skill(index, document, {})`, which is `DECISION_FAILED` with the missing-answer detail. Every path then replaces it, so the spec's four detail texts are the only ones a caller can see.
7. **Pre-existing IMPROVED lint counts left alone.** A002 (640 < 703) and A007 (254 < 255) already reported IMPROVED on the base. On this machine, C012, S001, S010, S025, and S051 also report IMPROVED. Row 28 allows only A001 to change, so none of these was lowered.

## Files outside §12.3

None. Every created or modified file is a §12.3 row. The only other committed files are this report and the spec's frontmatter, Proof cells, and §17, as Phases 6–7 require.

## Budget (§8.4)

| Item | Allowed | Used |
|---|---|---|
| New files | 14 | 14 (13 in `vidbyte/agents/skills/`, plus `vidbyte/lib/constants/skills.py`) |
| New public names | 9 | 9 (`SkillEntry`, `InlineSkill`, `LocalSkill`, `SkillsShSkill`, `GitHubSkill`, `AnthropicSkill`, `OpenAISkill`, `SkillSourceType`, `SkillUnavailableReason`) |
| New enums | 3 | 3 (`SkillSourceType`, `SkillUnavailableReason`, `SkillFetchStep`) |
| Classes in the new package | 12 | 12 |
| New dependencies | 0 | 0 |

## Gates (final lines)

All run on `429c77e9` (the code HEAD; later commits touch only `docs/spec/`).

S2 pack plus the existing preload module: `PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider -rs`
```
=========================== short test summary info ===========================
SKIPPED [1] testseatures\jev_skills_preload	est_skill_sources_local.py:115: this filesystem is case-insensitive, so skill.md is SKILL.md here
373 passed, 1 skipped in 4.19s
```
The one skip is the expected Windows case-insensitive case. `tests/test_jev_skill_preload.py` (AC-16) passes unchanged.

Full lint: `PYTHONPATH=$(pwd) python lint/run.py` (no `REGRESSED` line; A001 at 642)
```
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

S051 and import sort: `PYTHONPATH=$(pwd) python lint/run.py --rule S051` and `python -m ruff check <changed .py files> --config lint/ruff.toml --select I001 --no-cache`
```
SDK-LINT: PASS
All checks passed!
```

Source stage: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` (exit 0; its lint step printed `SDK-LINT: PASS`)
```
tests	est_workflow_agent_forks.py ......                                [100%]

====================== 3747 passed, 14 skipped in 29.18s ======================
CI passed.
```

Package stage: `python scripts/run_ci.py --stage package` with PYTHONPATH unset (exit 0)
```
No broken requirements found.
> ...env\Scripts\python.exe -c from importlib.metadata import entry_points, version; import vidbyte; ...
Installed vidbyte-sdk 0.2.1 passed smoke checks.
CI passed.
```

Contract: `python scripts/generate-sdk-public-api.py --check`
```
contracts/sdk-public-api.json is current at 3a4cb9292f62e40afa39478fdea5cf53fd758065 (vidbyte-sdk 0.2.1, 615 exports).
```

Semgrep, in a scratch venv (`semgrep==1.170.1`, never the system Python): `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` and `semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`
```
1/1: ✓ All tests passed
Ran 1 rule on 900 files: 0 findings.
```

Tests untouched: `git diff d01e0afa..HEAD -- tests/ | wc -l` → `0`.

## Tricky parts

- **Slotted dataclass subclasses cannot call `super().__post_init__()`** (no `__class__` cell with `slots=True`). The base `__post_init__` checks `name` and then calls the `_validate_source` template hook. Each subclass overrides that hook and redeclares `type` with `init=False` and its own default.
- **C002 duplicated-guard rule.** `isinstance(self.version, bool)` in the vendor entries tripped C002, because the variable name `version` appears elsewhere in the tree. `type(self.version) is int` expresses "an int but not a bool" without that pattern.
- **A007 is context-sensitive.** A numeric literal counts as an operational constant when the AST within 7 parent levels holds tokens such as byte, status, depth, or read, or calls such as `read`. Whole enclosing `with`/`try` statements count. The fixes were a named constant, using `PurePosixPath(...).parent.parts`, and unpacking `raw, total_bytes = read` in the skills.sh lock check.
- **The editable install points at the main checkout.** Every Python run needs `PYTHONPATH=$(pwd)`. A two-entry PYTHONPATH on Windows needs `;` and Windows paths.
- **mypy narrowing in the preload.** `SkillLoader.documents()` yields `SkillDocument | None`. `run` builds `loaded = {index: document …}` once after `load()`, so scoring and selection index a `dict[int, SkillDocument]`.
- **S062 (implicit string concatenation)** fired on a parenthesized two-part detail string. The too-large detail is one literal.
- **Semgrep on this machine.** A system-wide `pysemgrep` with mcp 2.x is on PATH. In Git Bash, the scratch venv only wins when PATH uses `/c/...` form, because a `C:/...` entry splits at the colon.

## Open items

- Remote CI was not dispatched, as the brief requires. SDK CI is manual-dispatch only; S6 or the orchestrator dispatches `ci.yml` and `static-policy.yml` for PR #904.
- Spec choices I would revisit, built as decided: none. Q-1, Q-3 to Q-7 defaults are implemented as stated (local misses remembered, `source` kept, no guide update, no hash verification, `path="."` rejected, a lock without an entry loads without the check).
- The pre-existing IMPROVED lint counts (deviation 7) could be lowered in a separate change.
