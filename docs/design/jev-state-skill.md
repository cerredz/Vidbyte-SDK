# Jev runtime state guidance

## Why

Future Jev capabilities will classify the agent's progress and actions during and after a run. The Jev view must fit a smaller context than the generative agent's context. Future implementers need a shared design that preserves decisive evidence, distinguishes observations from interpretations, and gives Jev only bounded recognition tasks.

## Change

Extend `skills/jev-agent/SKILL.md` with guidance for a proposed state architecture and its limits. Keep it distinguishable from the currently implemented scaffold and preflight behavior. No runtime API or behavior changes in this PR.

The proposed architecture builds a general structured task state once from the original request. Named settings add capability-specific sections; the first is a multi-part completion section. At a finish attempt, a second generative builder creates a matching handoff from the observed run. Jev receives the original request, initial state, and handoff and classifies each requested part. Runtime code validates matching sections and controls acceptance or continuation. Retained source evidence supports handoff review across context compaction; insufficient or oversized evidence remains explicit. Evaluation isolates errors in initial extraction, handoff reconstruction, Jev classification, and the resulting run behavior.

## Files

- Create `docs/design/jev-state-skill.md` for the scope and rationale.
- Modify `skills/jev-agent/SKILL.md` with the reusable guidance.

## Risks and open questions

A finite view cannot answer arbitrary future questions about an unbounded run. Initial extraction and final reconstruction can omit decisive details, especially when the full run exceeds the handoff model's context. The strict finish-attempt seam, source capture, and fallback behavior require implementation and empirical validation before controlling consequential behavior.

## Verification

Review the skill against the requested design conclusions, validate its frontmatter, and run the repository lint and full `scripts/run_ci.py` gate. The change is documentation only, so no new runtime tests are planned.
