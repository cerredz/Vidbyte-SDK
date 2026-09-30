# Cumulative Obligations Done Check

## Change

Add an opt-in `CUMULATIVE_OBLIGATIONS` Jev done check. It identifies each user obligation represented in the current request and caller-supplied prior user messages, including requirements added or clarified in later turns. It also asks one inventory-fidelity question per supplied user turn, comparing the original message against all generated obligation entries so an omitted requirement remains detectable. A requirement stays active unless a supplied user turn explicitly cancels or replaces it. Merely omitting an earlier requirement from a later turn does not cancel it. Jev checks each obligation against evidence from the completed run; an unfulfilled active obligation or an incomplete per-turn inventory sends the main agent back to focused work in the same loop.

## Design

Use the existing request-derived run-state section and handoff evidence section. Store obligation id, source/order context, links to clarifying or status-changing turns, active status, and a user-grounded completion signal in frozen typed records. The handoff compiles evidence for every obligation, including the cancellation wording for entries marked inactive. Batch one recognition question per obligation and one inventory-fidelity question per supplied user turn with the other enabled done checks. Each turn question compares the actual message against all generated obligations and their source/clarification/cancellation links; Jev recognizes omissions but does not generate its own obligation list. Apply a named threshold and veto across both question kinds. An empty obligation list passes only when each turn confirms it contains no unrepresented active requirement. Continuation feedback names incomplete obligations and, for an inventory failure, asks the main agent to reconstruct that turn without inventing an unspecified item. Explicit cancellation or replacement is represented as inactive in the run state; the questions also verify that supplied user turns justify that status. Pass prior caller-supplied user messages from `BaseAgentContext.history` into run-state generation, filtering out the agent's own messages, and append the current run request as the latest user turn.

`JevRuntime.arun` receives one current message plus `BaseAgentContext.history`. `BaseAgent.generate_reply` builds that history from the caller's explicit `history` argument and the agent's own prior replies. The runtime must pass only history entries whose sender is `user`, since agent replies are not user obligations. The check can preserve earlier turns when callers provide them through the established history parameter; it cannot recover user turns omitted from both that history and the current message, and must not claim hidden persistent conversation history.

## Files

- Add enums, payloads, frozen records, field constants, threshold, fixed question, and registry entry.
- Extend run-state and handoff schemas, record conversion, per-check state/question construction, scoring, and continuation explanation; pass user history from JevRuntime to the run-state generator.
- Export public result records and update relevant folder/module documentation.
- Add this design document before implementation.

## Risks and decisions

- Incorrectly treating omission as cancellation recreates the failure this check is meant to catch; the question must require explicit cancellation or an explicit replacement that conflicts with the prior obligation.
- This check is distinct from ordinary input-set coverage: it judges whether obligations remain active across additions, clarifications, cancellations, and replacements in the supplied user-turn history.
- The generative run-state and handoff agents can misextract or omit content. The check remains advisory and follows the existing fail-open behavior when either generation or Jev is unavailable.
- The per-turn handoff evidence is a generative summary and can itself omit observations; the inventory question can only judge the material that summary reports. It keeps this evidence separate from the handoff's per-obligation `missing` judgment and is refreshed for each finish attempt.
- Requests without supplied history support only obligations visible in the current request string.

## Verification

Do not add or run local tests. Structural verification may include syntax compilation, diff checks, and repository lint rules; automatic pull-request CI provides the broader validation. Inspect CI results and repair implementation failures before reporting completion.
