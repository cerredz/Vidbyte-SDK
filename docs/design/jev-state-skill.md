# Jev runtime state guidance

## Why

Future Jev capabilities will classify the agent's progress and actions during and after a run. The Jev view must fit a smaller context than the generative agent's context. Future implementers need a shared design that preserves decisive evidence, distinguishes observations from interpretations, and gives Jev only bounded recognition tasks.

## Change

Extend `skills/jev-agent/SKILL.md` with guidance for a proposed state architecture and its limits. Keep it distinguishable from the currently implemented scaffold and preflight behavior. No runtime API or behavior changes in this PR.

The proposed architecture keeps recoverable source evidence, incrementally updated structured state, and a decision-specific Jev view. Each capability specifies the evidence it needs, freshness rules, a budget, and fallback behavior. Code records execution facts and deterministic comparisons; the generative model interprets ambiguous meaning and changes to plans; Jev classifies prepared evidence. Evaluation must isolate errors in view construction from errors in Jev classification and measure end-to-end benefit.

## Files

- Create `docs/design/jev-state-skill.md` for the scope and rationale.
- Modify `skills/jev-agent/SKILL.md` with the reusable guidance.

## Risks and open questions

A finite view cannot answer arbitrary future questions about an unbounded run. Extraction, retrieval, and dependency tracking can miss a decisive detail even when a view appears complete. The eventual storage interface, update channel, and decision contracts require implementation and empirical validation before controlling consequential behavior.

## Verification

Review the skill against the requested design conclusions, validate its frontmatter, and run the repository lint and full `scripts/run_ci.py` gate. The change is documentation only, so no new runtime tests are planned.
