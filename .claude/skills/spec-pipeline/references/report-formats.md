# Artifact and report formats

Everything that moves between stages is a file in the worktree under `docs/spec/<slug>/`. Subagents never share context; they share these files. The orchestrator keeps its own context lean by reading only the headers and summaries defined here, never whole artifacts.

```
docs/spec/<slug>/
  request.md                 S0  the conversation, captured by the orchestrator (verbatim prompts + notes)
  pipeline.md                S0→S6  state machine, counters, decisions, gate answers (orchestrator-owned)
  context/
    code-map.md              S0  scout: AGENTS.md rules and commands; every file the change touches, read in full; tests; notes
  spec.md                    S1  the spec (template in references/spec-template.md)
  test-plan.md               S2  test author: what each test proves, what it would catch, what was deliberately omitted
  review.md                  S4  merged + verified adversarial findings with dispositions (updated through S5)
  verify-log.md              S5  one entry per repair iteration: defects in, what was tried, gate matrix out
  pr-body.md                 S6  the final PR title + body
  reports/
    S0-scout.md        S1-spec-author.md  S1-spec-review.md
    S2-test-author.md  S3-implementer.md  S4-review-<lens>.md  S4-findings-verifier.md
    S5-repair-<n>.md   S5-rereview.md     S6-pr-author.md
```

Every subagent writes its full report to its `reports/` file **and** returns a short final message (≤ 60 lines) in the `STATUS` block format below. The long version is on disk; the short version is what enters the orchestrator's context.

---

## `STATUS` block (every subagent's final message)

```
STATUS: DONE | BLOCKED | FAILED
STAGE: S<n> <agent name>
REPORT: <absolute path to reports/S<n>-….md>
PRODUCED: <files created/modified, one per line, absolute paths>
HEAD: <short SHA after your last commit, or "no commits">
SUMMARY (≤ 10 lines): <what you did, what you found, what the next stage must know>
NICHE FACTS FOR THE NEXT AGENT (≤ 8 bullets): <things a fresh agent would get wrong in this repo for this feature: a placement rule, a fixture quirk, a lint rule that fired, a command that needs a flag here, a name that must not change>
OPEN ITEMS: <anything you could not finish or verify, with evidence; or "none">
```

For `BLOCKED`, add before `SUMMARY`:

```
BLOCKED AT: <step>
DONE SO FAR: <completed work, all committed; in-progress work reverted to clean>
QUESTION: <one precise question>
OPTIONS:
1. <option> — <consequence>
2. <option> — <consequence>
RECOMMENDATION: <option and why>
EVIDENCE: <spec section, file:line, or command output that forced the stop>
```

For `FAILED`, give the exact command, the relevant output, what you tried (at least three structurally different approaches), and what the user would need to do.

A subagent that claims a command passed must include that command's final 3–5 output lines in its report file. The orchestrator spot-checks.

---

## `request.md` (written by the orchestrator at S0)

````markdown
---
slug: <slug>
repo: <absolute path>
invoked: <YYYY-MM-DD HH:MM>
flags: <parsed flags, or "none">
---

# Request: <title>

## A. Every user prompt in this conversation, verbatim and in order
_Copy each prompt exactly as written: typos, pasted blocks, code fences. Wrap in a fence of four or more backticks when a prompt contains fences. No cleanup, no summary. If the pipeline was invoked cold with only an argument string, there is exactly one prompt here._

**Prompt 1** (<when, relative to the conversation>):
<verbatim>

**Prompt 2** …

## B. Handoff block and decision ledger (verbatim, if present)
_If the conversation contains a `## HANDOFF — …` block (from /talk) or a Re-entry card with a `Decided:` ledger, paste both verbatim here. Otherwise "none"._

## C. Structured conversation notes
_The payload for every downstream agent. Over-capture. Drop a heading only if it is truly empty._

### Key decisions
- <decision> — <the reasoning behind it>
### Rejected alternatives
- <alternative> — <why it was ruled out>
### Constraints and assumptions
- <hard constraint or assumption treated as true>
### Clarifications and answers
- Q: <question asked in the conversation> — A: <the user's answer, verbatim where possible>
### Terminology
- <term> — <exactly what it means in this context>
### Implementation hints
- <existing files, patterns to imitate, seams, names to reuse, things NOT to touch, gotchas>
### Open questions
- <unresolved items the spec author must resolve as A-/Q-items>

## D. Weighted words
_Every "always", "never", "every", "must", "exactly", "fast", "secure", "simple" in the user's prompts, quoted with its sentence. The spec turns each into a testable invariant or a measurable target._

- "<quote>" — Prompt <n>
````

---

## `pipeline.md` (owned by the orchestrator; updated at every stage boundary; committed)

````markdown
---
slug: <slug>
repo: <absolute path>
worktree: <absolute path>
branch: <branch>
base_commit: <SHA>
pr: <url or empty>
until: none | S<n>
started: <YYYY-MM-DD HH:MM>
---

# Pipeline: <title>

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | pending / running / done / blocked | | | reports/S0-… | base_commit |
| S1 spec + review | | | | | spec r<N>, verdict |
| S2 tests | | | | | <n> tests, red confirmed |
| S3 implement | | | | | HEAD, draft PR url |
| S4 adversarial review | | | | | <n> confirmed findings |
| S5 repair loop | | | | | iterations <k>/<cap>, gates green |
| S5 re-review | | | | | verdict |
| S6 PR | | | | | PR url, checks |

## Counters and caps
- S1 review rounds: <k>/2 · S5 repair iterations: <k>/8 · S5 re-review rounds: <k>/2

## Decisions the orchestrator made
- <date time> — <decision> — <why> (e.g. "rejected finding R-4 as refuted by verifier evidence")

## User replies (verbatim)
- <date time> — "<reply>"

## Niche facts accumulated (carried into every later briefing)
- <fact> — *source:* <stage/report>
````

---

## `test-plan.md` (S2)

````markdown
# Test plan: <title>

Spec: `docs/spec/<slug>/spec.md` r<N> · Framework: <name + version> · Prior art copied: `<path>`

## Coverage map
| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | | acceptance | | |
| INV-1 | | unit / integration / e2e / contract / property / concurrency / security | | |

## Tests deliberately NOT written
| Candidate | Why it would not earn its keep |
|---|---|

## Red run (before implementation)
Bootstrap: <install commands run in this worktree, or "none needed">
<command> → <final lines showing the new tests fail or error, confined to the new files>

## Notes for the implementer
- <names the tests bind to; fixtures they rely on; anything the implementer must not change>
````

---

## `review.md` (S4, maintained through S5)

````markdown
# Adversarial review: <title>

Diff reviewed: `origin/main..<HEAD SHA>` · Lenses: conformance, conventions, engineering · Verifier: reports/S4-findings-verifier.md

## Verdict
<one of: MERGEABLE AFTER FIXES | NEEDS REWORK | SOUND> — <one sentence>

## Confirmed findings (must fix) — <n>
| ID | Severity | Lens | Where (path:line) | Finding (claim) | Evidence | Smallest fix | Status |
|---|---|---|---|---|---|---|---|
| R-1 | Blocker / Major | | | | | | open / fixed @<sha> / waived (<reason>) |

## Refuted or downgraded by the verifier — <n>
| ID | Original severity | Why refuted / downgraded (evidence) |
|---|---|---|

## Minor findings (fix if trivial, otherwise follow-ups)
| ID | Where | Finding | Status |
|---|---|---|---|

## What the implementation gets right (so nobody "fixes" it)
- …
````

---

## `verify-log.md` (S5)

````markdown
# Verification log: <title>

Gate set (from context/code-map.md §1): <list of gates with commands; mark local-only and remote-only>

## Iteration <k> — <date time> — agent report: reports/S5-repair-<k>.md
**Defects in:** <R-ids and failing gates handed to this iteration>
**Hypotheses and attempts:** <what was tried, in order; what did not work and why — so the next fresh agent does not repeat it>
**Changes:** <commits with SHAs>
**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | | PASS / FAIL (<n> failing) | |
| full local gate | | | |
| remote checks | `gh pr checks` | | |
**Still open:** <R-ids / gates>
````
