"""Context Protocol Header

Description:
    Defines the Handoff context primitive and its prebuilt off-the-shelf variants.
Purpose:
    Gives developers a single object that is simultaneously a context primitive
    (droppable into another agent's context_items), the spec describing a handoff
    document's structure, and the produced, filled handoff document.
Architecture:
    - Handoff: Base sectioned-document primitive implementing the ContextItem protocol.
    - EngineeringHandoff / ResearchHandoff / MinimalHandoff: Prebuilt subclasses that
      preset a curated section mapping of titles to guidance descriptions.
Relations:
    Implements the ContextItem protocol from vidbyte.context.primitives, is consumed by
    vidbyte.agents.handoff.HandoffAgent, and is accepted by BaseAgent(handoff=...) and
    ContextManager. Re-exported through vidbyte.context and the root vidbyte namespace.
Similar Files:
    - vidbyte/context/primitives.py: The other standard context item primitives.
    - vidbyte/agents/handoff.py: The agent that fills a Handoff spec from a run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class Handoff:
    """Sectioned handoff document that doubles as a ContextItem primitive and a HandoffAgent spec."""

    DEFAULT_TITLE: str = "Handoff"
    DEFAULT_INSTRUCTIONS: str = ""

    def __init__(self, *, sections: Mapping[str, str] | None = None, title: str | None = None, instructions: str | None = None, metadata: Mapping[str, Any] | None = None, primitive_id: str | None = None, primitive_frozen: bool = False) -> None:
        # Resolve section map, title, and instructions from arguments or subclass defaults.
        self.sections: dict[str, str] = dict(sections) if sections is not None else self.default_sections()
        self.title: str = title if title is not None else self.DEFAULT_TITLE
        self.instructions: str = instructions if instructions is not None else self.DEFAULT_INSTRUCTIONS
        self.kind: str = "handoff"
        self.metadata: dict[str, Any] = dict(metadata or {})
        self.primitive_id: str | None = primitive_id
        self.primitive_frozen: bool = primitive_frozen

    def default_sections(self) -> dict[str, str]:
        # Return the prebuilt section mapping for this variant; base Handoff has none.
        return {}

    def to_context_text(self) -> str:
        # Render the handoff as a titled, instruction-led, sectioned markdown block for context injection.
        head = self.title if not self.instructions else f"{self.title}\n{self.instructions}"
        if not self.sections:
            return head
        body = "\n\n".join(f"## {title}\n{self._coerce(value)}" for title, value in self.sections.items())
        return f"{head}\n\n{body}"

    def render_section_brief(self) -> str:
        # Render "- Title: description" lines used to instruct the generating model.
        return "\n".join(f"- {title}: {self._coerce(value)}" for title, value in self.sections.items())

    def fill(self, sections: Mapping[str, str]) -> "Handoff":
        # Return a produced copy of the same concrete subclass with content sections and filled metadata.
        return type(self)(
            sections=dict(sections),
            title=self.title,
            instructions=self.instructions,
            metadata={**self.metadata, "filled": True},
            primitive_id=self.primitive_id,
            primitive_frozen=self.primitive_frozen,
        )

    @property
    def is_filled(self) -> bool:
        # Report whether this handoff carries produced content rather than template descriptions.
        return bool(self.metadata.get("filled", False))

    def section_titles(self) -> tuple[str, ...]:
        # Return the ordered section titles for this handoff.
        return tuple(self.sections.keys())

    @staticmethod
    def _coerce(value: Any) -> str:
        # Coerce any section value to a string so rendering never raises on non-string content.
        return value if isinstance(value, str) else str(value)


class EngineeringHandoff(Handoff):
    """Prebuilt handoff for continuing software-engineering work."""

    DEFAULT_TITLE = "Engineering Handoff"

    def default_sections(self) -> dict[str, str]:
        # Sections tuned for a coding agent's work so the next engineer can continue cold.
        return {
            "Objective": "The original goal and what success looks like.",
            "Changes Made": "Files touched and what changed in each, with the reasoning behind the approach.",
            "Verification Status": "What was actually tested or proven versus what is still assumed to work.",
            "Open Threads": "Unfinished work and decisions still in flight.",
            "Risks & Gotchas": "Landmines, fragile areas, and non-obvious constraints for whoever continues.",
            "Next Steps": "Ordered, concrete actions to take next.",
        }


class ResearchHandoff(Handoff):
    """Prebuilt handoff for continuing a research or investigation task."""

    DEFAULT_TITLE = "Research Handoff"

    def default_sections(self) -> dict[str, str]:
        # Sections tuned for an investigative agent so findings and gaps transfer cleanly.
        return {
            "Question": "The question or objective the research set out to answer.",
            "Findings": "The substantive conclusions reached so far, with supporting detail.",
            "Sources": "Where each key finding came from, so it can be re-verified.",
            "Confidence & Gaps": "How sure each finding is and what is still unknown or unverified.",
            "Recommended Next Queries": "The most valuable next questions or searches to pursue.",
        }


class MinimalHandoff(Handoff):
    """Prebuilt minimal handoff; the default spec when none is provided."""

    DEFAULT_TITLE = "Handoff"

    def default_sections(self) -> dict[str, str]:
        # The smallest useful handoff: what happened and what to do next.
        return {
            "Summary": "What was accomplished, in a few sentences.",
            "Next Steps": "Concrete actions for whoever continues the work.",
        }


class TreeSearchHandoff(Handoff):
    """Prebuilt handoff for branching exploration with pruning (search-frontier shape)."""

    DEFAULT_TITLE = "Tree Search Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the open frontier and what was pruned, so search is not repeated.
        return {
            "Search Goal": (
                "Describe the objective the search is trying to reach and what a valid solution looks like in concrete terms. "
                "Specify any constraints or criteria a solution must satisfy to be considered complete or acceptable. "
                "Include the problem domain, the input space being explored, and any formal or informal success conditions. "
                "If there is a target score, threshold, or terminal state, state it explicitly so the next agent can recognize when to stop. "
                "Aim for enough detail that someone unfamiliar with the task can reconstruct the search objective from this section alone."
            ),
            "Algorithm & Heuristics": (
                "Describe the search algorithm being used (e.g., BFS, DFS, A*, MCTS, beam search) and the branching factor at each node. "
                "Explain each heuristic or scoring function in use: what it measures, why it was chosen, and how it ranks candidate branches. "
                "Note any algorithm parameters that were tuned mid-run (beam width, exploration constant, depth limit) and the rationale for each adjustment. "
                "If multiple heuristics are combined, describe the weighting or selection logic so the next agent can reproduce the same evaluation. "
                "Include known weaknesses of the chosen heuristic and any situations where it has been observed to mislead the search."
            ),
            "Frontier": (
                "List every open branch currently worth expanding, ordered from most to least promising according to the current heuristic score. "
                "For each frontier node, include its path from the root, its evaluated score, the reason it has not been expanded yet, and the estimated cost to reach a solution from it. "
                "Flag any frontier nodes that are near a pruning threshold or that depend on resources (time, budget, API calls) that may be exhausted soon. "
                "Be exhaustive: omitting a frontier node forces the next agent to re-derive it from scratch, duplicating work. "
                "If the frontier is large, group nodes by tier or score range and call out the top three candidates in detail."
            ),
            "Explored Branches": (
                "Document every path already expanded, including the sequence of choices made, the states visited, and the score or outcome at the leaf. "
                "For each explored branch, note whether it reached a terminal state, hit a depth limit, or was cut off mid-expansion, and what the final evaluation was. "
                "Include enough path detail that the next agent can confirm a branch was fully explored and skip re-expanding it. "
                "If branches share prefixes, group them to reduce repetition, but ensure the divergence point and each distinct outcome are explicit. "
                "Aim for a complete audit trail so no work is accidentally duplicated."
            ),
            "Pruned / Dead Branches": (
                "List every branch that was abandoned before reaching a terminal state, including the node at which it was pruned and the specific reason for pruning. "
                "Common reasons include: score fell below the pruning threshold, the path violated a hard constraint, a cycle was detected, or a resource cap was reached — name the exact cause for each. "
                "Do not omit pruned branches even if they seem obviously bad: the next agent must be able to confirm they were already considered. "
                "If a pruned branch might become viable under different heuristic weights or relaxed constraints, note that explicitly so the next agent can reconsider it intentionally. "
                "Include the depth and score at the pruning point so the next agent can assess how much exploration was abandoned."
            ),
            "Best So Far": (
                "Describe the strongest complete or partial solution found to date, including the full path from root to leaf and its evaluated score or outcome metric. "
                "If the solution is partial, specify exactly what is missing and how far it is from a complete solution. "
                "Compare this candidate against the success criteria defined in Search Goal and note any gaps or shortcomings. "
                "If multiple candidates are tied or nearly tied, list them all with their distinguishing characteristics. "
                "This section is the most important recovery artifact: write it as if someone will use it directly as the starting point for the next expansion."
            ),
            "Search Metrics": (
                "Report quantitative statistics about the search so far: total nodes expanded, total nodes generated, current frontier size, maximum depth reached, and elapsed wall-clock time or token budget consumed. "
                "Include the ratio of pruned nodes to expanded nodes as an indicator of how aggressive the pruning is. "
                "If the search has made progress toward a stopping criterion (e.g., a target score threshold), report how close it is. "
                "Note any trend: is the heuristic improving the search rate, plateauing, or degrading as the search goes deeper? "
                "These metrics let the next agent calibrate how much budget remains and whether the current algorithm is worth continuing or should be replaced."
            ),
            "Termination Condition": (
                "State precisely when the search should stop: the target score, the maximum number of expansions, the time or token budget, or any other halting criterion. "
                "Explain whether the search should stop at the first acceptable solution or continue to find the global optimum, and why. "
                "If the termination condition has been revised during the run (e.g., the budget was extended or the target relaxed), document the revision and the reason. "
                "Note what the next agent should do if the termination condition cannot be met within the remaining budget: fall back to best-so-far, request more resources, or report failure. "
                "Include any soft stopping conditions (e.g., stop if no improvement after N expansions) that should also be respected."
            ),
            "Next Expansion": (
                "Identify the specific frontier node to expand next, including its full path from the root and its current score, and give a clear rationale for why it is the highest priority. "
                "Describe the children that are expected to be generated from this node and any early termination conditions that would apply during their evaluation. "
                "If there is uncertainty about which node to expand next, list the top two or three candidates with the decision criteria that would differentiate them. "
                "Include any preconditions the next agent must satisfy before expanding (e.g., re-evaluating the heuristic, fetching external data, or checking a constraint). "
                "End with a concrete action the next agent should execute first so there is no ambiguity about how to resume."
            ),
        }


class DecompositionHandoff(Handoff):
    """Prebuilt handoff for divide-and-conquer work (subproblem-tree shape)."""

    DEFAULT_TITLE = "Decomposition Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the subproblem tree and the pending composition step.
        return {
            "Top-Level Problem": (
                "State the overall problem being decomposed in enough detail that someone unfamiliar with the task can understand the full scope and goal. "
                "Include the inputs available, the expected output or deliverable, and any hard constraints that apply to the solution as a whole. "
                "Note any ambiguities in the problem statement that were resolved during decomposition, and how they were resolved. "
                "Describe the scale and complexity of the problem so the next agent can calibrate how much work remains. "
                "This section should stand on its own: a reader should be able to re-derive the decomposition strategy from this description if needed."
            ),
            "Decomposition Strategy": (
                "Explain the principle used to split the top-level problem into subproblems: functional decomposition, data partitioning, temporal sequencing, domain partitioning, or another strategy. "
                "Justify why this strategy was chosen over alternatives and what properties of the problem made it appropriate. "
                "Describe any assumptions made during decomposition that affect the validity of the split (e.g., independence of subproblems, uniform complexity across partitions). "
                "Note if the decomposition is exhaustive (every part of the top-level problem is covered by exactly one subproblem) or approximate (some overlap or gap exists). "
                "If the decomposition was revised during the run, describe the original plan, what changed, and why."
            ),
            "Decomposition": (
                "Provide the full subproblem tree: each node is a subproblem, its parent is the problem it decomposes, and its children are any further sub-decompositions. "
                "For each leaf subproblem, describe its inputs, expected outputs, and any constraints specific to it. "
                "For non-leaf nodes, explain how the subproblem was further split and why that level of granularity was chosen. "
                "Include the estimated complexity or effort for each open subproblem so the next agent can prioritize work efficiently. "
                "Use a structured format (indented list, tree diagram, or table) so the hierarchy is visually clear."
            ),
            "Interface Contracts": (
                "For every pair of subproblems that share data, specify the exact interface: what the producing subproblem outputs, what format it uses, and what the consuming subproblem expects as input. "
                "Flag any interface that is not yet defined or that was assumed rather than verified, as these are the most common source of composition failures. "
                "If a subproblem's output feeds more than one downstream consumer, list all consumers and any ordering constraints between them. "
                "Note any type mismatches, schema differences, or unit/encoding discrepancies that were discovered and how they were resolved. "
                "This section is the primary guide for the composition step: it should contain enough detail to wire the solved subproblems together without re-reading their implementations."
            ),
            "Solved Subproblems": (
                "List every subproblem that has been fully resolved, including the result or output it produced and a confidence assessment of that result. "
                "For each solved subproblem, note whether the result was verified (tested, checked against a ground truth, or reviewed) or is accepted on faith. "
                "If any solved subproblem's result is approximate, partial, or conditional on an assumption that may not hold, flag it explicitly. "
                "Include the time or resource cost of solving each subproblem so the next agent can estimate remaining effort more accurately. "
                "Do not summarize or compress: the exact output of each solved subproblem should be reproducible from this section."
            ),
            "Open Subproblems": (
                "List every subproblem that has not yet been solved, including its current status (not started, in progress, blocked) and its dependencies on other subproblems. "
                "For each blocked subproblem, identify the specific dependency that is blocking it and what would need to be true to unblock it. "
                "Estimate the complexity and expected resource cost of each open subproblem so the next agent can plan its work. "
                "Note any ordering constraints: which open subproblems must be resolved before others can start. "
                "Flag any open subproblem that is on the critical path to composition so the next agent knows where to focus first."
            ),
            "Composition Status": (
                "Describe how the solved subproblem outputs are being combined into the final solution and what the current state of that combination is. "
                "Identify any composition steps that have already been performed, what they produced, and whether the combined result has been validated. "
                "List every blocker preventing final assembly: unsolved subproblems, interface mismatches, ordering constraints, or missing glue logic. "
                "Note any partial compositions that are already available and can be used immediately by the next agent. "
                "If the composition strategy itself needs to be revised based on what was learned from solving subproblems, describe the revision and the reason."
            ),
            "Next Steps": (
                "Specify the next concrete action the next agent should take: the subproblem to solve, the composition step to attempt, or the interface contract to define. "
                "Order the actions by dependency and priority so the next agent can start immediately without further planning. "
                "For the first action, include enough detail (inputs, expected outputs, approach) that the next agent can execute it without re-reading the full handoff. "
                "Note any preconditions that must be verified before starting (e.g., confirming a solved subproblem's output is in the expected format). "
                "End with a clear stopping condition: how will the next agent know when to hand off again?"
            ),
        }


class RefinementLoopHandoff(Handoff):
    """Prebuilt handoff for draft-critique-revise work (iteration-journal shape)."""

    DEFAULT_TITLE = "Refinement Loop Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the iteration history and whether the work is converging.
        return {
            "Objective": (
                "State what the work product needs to achieve in concrete, measurable terms so the next agent can evaluate the artifact against a clear standard. "
                "Include any non-negotiable requirements (correctness, format, length, tone, coverage) that must be satisfied before the refinement loop can close. "
                "Describe the intended audience or use case so the next agent can apply appropriate judgment when critiquing the draft. "
                "If the objective was clarified or narrowed during the refinement process, document the original objective and the revision so the next agent understands the context. "
                "Note any constraints that bound the space of valid revisions (e.g., the artifact must not exceed a certain length, or must preserve specific sections unchanged)."
            ),
            "Quality Criteria": (
                "List every criterion used to evaluate draft quality, in order of priority, with a clear description of what 'passing' looks like for each. "
                "Distinguish between hard criteria (the draft fails if these are not met) and soft criteria (improvements are desirable but not blocking). "
                "For each criterion, include an example of a draft element that satisfies it and one that violates it, so the next agent can calibrate its critique consistently. "
                "Note any criteria that have been added or modified since the first iteration, and the reason for the change. "
                "If the criteria conflict with one another (e.g., brevity vs. completeness), state the resolution rule so the next agent does not oscillate between them."
            ),
            "Current Draft State": (
                "Provide the current version of the artifact in full, or a precise pointer to where it can be retrieved, so the next agent does not need to reconstruct it from the iteration log. "
                "Summarize the most significant ways this draft differs from the first draft and from the previous draft, so the next agent can track how the artifact has evolved. "
                "Note any sections or elements of the draft that are considered stable and should not be changed in the next revision. "
                "Flag any sections that are placeholders, incomplete, or known to be below acceptable quality so the next agent knows where to focus its critique. "
                "Include any metadata about the draft (word count, structure, version number) that is relevant to evaluating it against the quality criteria."
            ),
            "Iteration Log": (
                "Document every refinement pass in reverse-chronological order (most recent first), with each entry containing: the iteration number, the critique applied, the specific changes made, and the quality score or assessment before and after. "
                "For each critique, describe not just what was wrong but why it was wrong (the underlying cause) so the next agent can avoid re-introducing the same problem. "
                "Note any revisions that were attempted but then reverted, and the reason they were rolled back. "
                "If a revision improved one quality criterion but degraded another, record both effects so the trade-off is visible. "
                "Include enough detail in each entry that the next agent can reconstruct the reasoning behind the current draft state."
            ),
            "Reference Artifacts": (
                "List any external examples, templates, benchmarks, or reference documents that were used to calibrate quality during the refinement process. "
                "For each reference, describe which quality criteria it informs and how the current draft compares to it on those criteria. "
                "Note any references that were consulted but ultimately judged inapplicable, and why, so the next agent does not re-consult them. "
                "If the objective or quality criteria were derived from a reference artifact, include it here even if it was not used for direct comparison. "
                "Provide enough context about each reference that the next agent can use it without fetching additional background."
            ),
            "Open Critiques": (
                "List every known problem with the current draft that has not yet been addressed, in priority order, with a clear description of the problem and why it matters. "
                "For each open critique, estimate the effort required to address it and note any dependencies (e.g., one critique cannot be addressed until another is resolved first). "
                "Distinguish between critiques that will definitely be addressed in the next revision and those that are deferred or under debate. "
                "Note any critiques that were discovered late in the process and may require revisiting earlier sections of the artifact. "
                "If an open critique is ambiguous or contested, describe the disagreement and what information would resolve it."
            ),
            "Convergence Status": (
                "Assess whether the artifact's quality is improving, plateauing, or oscillating across recent iterations, with specific evidence from the iteration log to support the assessment. "
                "Report the quality score or assessment for the last three iterations (if available) so the trend is visible. "
                "Identify the specific bottleneck preventing convergence, if any: a recurring critique that resists resolution, a conflict between quality criteria, or a gap in the reference artifacts. "
                "Estimate how many more iterations are needed to reach acceptable quality, given the current trend and the remaining open critiques. "
                "Note any risk of over-refinement: areas where continued revision is likely to degrade quality rather than improve it."
            ),
            "Next Revision": (
                "Specify the exact change to make to the draft in the next revision: which section, what the problem is, and what the corrected version should look like or achieve. "
                "Explain why this change is the highest priority among all open critiques and how it is expected to affect the overall quality score. "
                "If the revision requires new information or external input (e.g., a fact check, a stakeholder decision), state what is needed and how to obtain it. "
                "Describe any side effects the revision may have on other sections and how to mitigate regression. "
                "End with a clear acceptance test: how will the next agent know the revision was successful before recording it in the iteration log?"
            ),
        }


class ConstraintSatisfactionHandoff(Handoff):
    """Prebuilt handoff for satisfying a requirement set (constraint-ledger shape)."""

    DEFAULT_TITLE = "Constraint Satisfaction Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the constraint ledger and the conflicts between constraints.
        return {
            "Objective": (
                "Describe the goal the solution must achieve, including the domain, the decision variables, and the shape of a valid solution. "
                "State the problem in enough detail that the next agent can independently verify whether a candidate satisfies it without re-reading any external specification. "
                "Include any implicit requirements that were discovered during solving and are not in the original problem statement. "
                "Note the scale of the problem: how many variables, how many constraints, and how large the candidate space is. "
                "If the objective was revised or narrowed during solving, document the revision so the next agent understands the current scope."
            ),
            "Constraint Hierarchy": (
                "Classify every constraint as hard (must be satisfied for the solution to be valid) or soft (desirable but not mandatory), and within soft constraints, assign a priority or weight. "
                "Explain the source of each constraint: requirement document, stakeholder input, physical limit, inferred dependency, or design choice — so the next agent knows which constraints can be negotiated. "
                "Note any constraints that were added or strengthened after solving began, and the reason for the change. "
                "If two constraints are logically equivalent or one implies the other, note the relationship to avoid redundant checking. "
                "Flag any constraint whose source is uncertain or whose interpretation is ambiguous, as these are the most likely causes of wasted effort."
            ),
            "Constraints": (
                "List every constraint in the problem, each with its type (hard or soft), its current status (satisfied, violated, or unknown), and the evidence supporting that status. "
                "For each violated or unknown constraint, describe what specific property of the current candidate causes the violation or uncertainty. "
                "Group constraints by the variable or system component they govern so the next agent can quickly locate which part of the candidate to adjust. "
                "Include any derived constraints that were not explicit in the original problem but were inferred during solving. "
                "Be exhaustive: every constraint the next agent will need to check should appear here, so it does not need to re-derive the constraint set."
            ),
            "Current Candidate": (
                "Provide the full specification of the current working solution under evaluation, including all variable assignments, parameter values, and structural choices. "
                "Summarize which constraints this candidate satisfies, which it violates, and which have not been checked yet. "
                "Describe how this candidate was generated: by construction, by search, by modification of a previous candidate, or by relaxation of a stricter requirement. "
                "Note any properties of this candidate that are considered stable and should be preserved in subsequent adjustments. "
                "Include a quality score or ranking relative to previous candidates if one is available, so the next agent can assess whether this candidate is an improvement."
            ),
            "Search Strategy": (
                "Describe the approach used to generate and evaluate candidates: systematic enumeration, local search, constraint propagation, backtracking, relaxation, or a hybrid. "
                "Explain any pruning or propagation rules applied to reduce the candidate space, and how effective they have been so far. "
                "Note which parts of the search space have been exhausted and which remain unexplored, so the next agent can resume without re-doing covered ground. "
                "If the search strategy was changed during solving (e.g., switching from systematic search to heuristic local search after a timeout), document the transition and the reason. "
                "Include any domain-specific insights that guided the search and should guide future candidates."
            ),
            "Conflicts & Tensions": (
                "Identify every pair or group of constraints that pull against one another, with a concrete description of why satisfying one makes it harder to satisfy the other. "
                "For each conflict, note whether it is a fundamental tension (the constraints cannot all be fully satisfied simultaneously) or a contingent tension (the current candidate happens to violate both, but another candidate might satisfy both). "
                "Rank the conflicts by severity and impact on solution quality, so the next agent knows which tensions to resolve first. "
                "Describe any partial resolutions attempted: relaxations, prioritizations, or workarounds that reduced the tension without fully eliminating it. "
                "Note any constraints that were identified as impossible to satisfy jointly and the decision made about how to handle that infeasibility."
            ),
            "Trade-offs Made": (
                "List every case where a constraint was relaxed, softened, or deprioritized, including which constraint was affected, what relaxation was applied, and the justification. "
                "For each trade-off, describe what was gained (which other constraints became easier to satisfy) and what was lost (how far the solution deviates from the original requirement). "
                "Note whether each trade-off was approved by a stakeholder or made autonomously, so the next agent knows which decisions can be revisited. "
                "If a trade-off introduced a new risk or downstream dependency, describe it explicitly. "
                "Include any trade-offs that were considered but rejected, with the reason they were not taken, to prevent the next agent from re-exploring the same dead end."
            ),
            "Feasibility Assessment": (
                "Provide an overall assessment of whether the constraint set is feasible, partially feasible, or infeasible given the current problem formulation. "
                "If the problem is infeasible, describe the minimal set of constraints that would need to be relaxed to restore feasibility. "
                "If feasibility is unknown, identify the specific constraints whose satisfiability is uncertain and what would be needed to resolve the uncertainty. "
                "Note any partial feasibility results: subsets of constraints that can be jointly satisfied even if the full set cannot. "
                "Estimate the probability of finding a fully satisfying candidate within the remaining search budget, based on the current search trajectory."
            ),
            "Next Steps": (
                "Specify the exact adjustments to make to the current candidate to address the highest-priority violated constraint, with a clear description of the change and the expected effect on constraint satisfaction. "
                "Order the remaining adjustments by their dependency and expected impact, so the next agent can work through them without re-planning. "
                "Note any adjustments that are risky (they might fix one constraint but break another) and how to detect and handle that regression. "
                "If the search strategy should be changed (e.g., because local search has stalled), describe the new strategy and the reason for the switch. "
                "End with a clear stopping condition: when should the next agent consider the constraint satisfaction problem solved, and what should it do if the budget runs out first?"
            ),
        }


class BacktrackingHandoff(Handoff):
    """Prebuilt handoff for commit-and-rollback work (decision-stack shape)."""

    DEFAULT_TITLE = "Backtracking Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the decision stack and safe points to revert to.
        return {
            "Objective": (
                "Describe the goal being pursued through a sequence of choices, including what a successful final state looks like and how it will be recognized. "
                "Identify the decision variables: the choices that must be made, the order in which they must be made, and the domain of valid values for each. "
                "State any hard constraints that a valid solution must satisfy, so the next agent can determine when a partial assignment is already infeasible. "
                "Note the scale of the problem: how many decisions remain, how large each decision domain is, and how deep the search tree is expected to be. "
                "Include any domain knowledge that should inform the choice ordering or value selection heuristic."
            ),
            "Decision Stack": (
                "List every committed choice in the order it was made, from the first decision to the most recent, forming the path from the root to the current state. "
                "For each choice, include the decision variable, the value assigned, the reason that value was selected over alternatives, and any constraints it activated or satisfied. "
                "Note the depth of the stack so the next agent knows how far into the search tree the current state is. "
                "Flag any choices that were made tentatively and later confirmed, so the distinction between firm and provisional decisions is clear. "
                "This section is the canonical record of how the current state was reached: it must be complete enough that the next agent could replay all decisions and arrive at the same state."
            ),
            "Choice Ordering & Heuristics": (
                "Describe the strategy used to select which variable to assign next (variable ordering) and which value to try first (value ordering), including any heuristics applied such as MRV, degree, or LCV. "
                "Explain how effective the current ordering strategy has been: has it led to early failure detection, or has it caused the search to waste time on unpromising branches? "
                "Note any dynamic changes to the ordering strategy made during the search and the reason for each change. "
                "If the problem has known structure (e.g., a chain of dependent decisions, a hierarchy, or independent subproblems), describe how that structure informs the ordering. "
                "Include any domain-specific insights that should guide future variable or value selection."
            ),
            "Tentative Choices": (
                "List every decision that has been made but not yet confirmed as part of a complete solution, including the variable, the value, and the conditions under which it would be rolled back. "
                "For each tentative choice, note which constraints it satisfies, which it leaves undetermined, and whether any forward-checking or constraint propagation has been applied. "
                "Describe any evidence that the current tentative choices are on a promising path (e.g., no constraint violations yet, few remaining domains are still large). "
                "Note any tentative choices that are at high risk of causing a failure further down the stack and that should be watched carefully. "
                "If a tentative choice depends on an assumption that has not been verified, state the assumption explicitly."
            ),
            "Backtrack Points": (
                "List every safe point in the decision stack where the search can revert to a known-good state, including the depth, the committed decisions at that point, and the alternative values not yet tried. "
                "For each backtrack point, note how many alternative values remain untried for the decision variable at that depth, so the next agent can estimate the remaining search space. "
                "Flag the most recent backtrack point as the default rollback target if the current path fails. "
                "Note any backtrack points that have been invalidated by constraint propagation (all remaining alternatives are known to be infeasible) so the next agent skips them. "
                "Describe any learned clauses or no-goods recorded during previous backtracks that can prune future search from these points."
            ),
            "Conflict Analysis": (
                "For every backtrack performed so far, document the conflict that triggered it: which constraint was violated, which committed choices caused the violation, and what the earliest point in the stack is that could have prevented it. "
                "If conflict-driven clause learning (CDCL) or a similar technique is being used, list the no-goods or learned constraints that have been recorded. "
                "Describe any patterns in the conflicts: are the same variables or constraints causing repeated failures, suggesting they should be prioritized earlier? "
                "Note any conflicts that were near-misses (the constraint was satisfied by a narrow margin) and that should be treated as warnings in future assignments. "
                "Use this analysis to guide both the choice ordering and the backtrack target: jump to the decision that caused the conflict, not just the most recent choice."
            ),
            "Abandoned Paths": (
                "List every path that was fully explored and found to lead to a dead end, including the sequence of choices that defined it and the specific constraint that caused the failure. "
                "For each abandoned path, note the depth at which the failure was detected and any constraints that were propagated as a result. "
                "Include paths that were abandoned due to resource exhaustion (time, token budget) rather than infeasibility, so the next agent knows they may still be viable. "
                "Do not omit abandoned paths even if they seem clearly bad: the next agent must be able to confirm they were already explored before moving on. "
                "Summarize the overall coverage of the search space: what fraction of the decision tree has been explored so far?"
            ),
            "State Invariants": (
                "List the invariants that must hold at every point in the decision stack — properties of the partial assignment that, if violated, indicate a bug in the search logic rather than a normal backtrack. "
                "For each invariant, describe what it means and how to check it given the current decision stack and constraint set. "
                "Note any invariants that were observed to be violated during the run and how they were diagnosed and corrected. "
                "Include any integrity constraints on the state representation itself (e.g., the decision stack must not contain duplicate variable assignments). "
                "These invariants serve as a sanity check: the next agent should verify them before making any new committed choices."
            ),
            "Next Steps": (
                "Specify the next action: either commit a new value for the next variable in the ordering or backtrack to a specified point and try the next alternative value. "
                "If committing, identify the variable, the value to try, the reason it is the best first choice, and any constraint propagation to apply immediately after. "
                "If backtracking, identify the target backtrack point, the reason for the jump (not just the most recent decision), and the alternative value to try at that point. "
                "Note any preconditions the next agent must verify before acting (e.g., confirm the constraint set is consistent at the current state). "
                "End with a stopping condition: when should the next agent consider the search complete or exhausted?"
            ),
        }


class TradeoffHandoff(Handoff):
    """Prebuilt handoff for balancing competing objectives (Pareto-frontier shape)."""

    DEFAULT_TITLE = "Trade-off Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the objectives and the non-dominated option frontier.
        return {
            "Decision to Make": (
                "Describe the decision that requires balancing competing objectives, including the context in which it arises and why it cannot be resolved by optimizing a single criterion. "
                "State the deadline or forcing function for the decision: when must it be committed, and what is the cost of deferral? "
                "Identify who has authority to make the final call and whether the next agent is expected to recommend, decide, or implement. "
                "Note any previous attempts to resolve this decision and why they did not reach a conclusion. "
                "Include any constraints that are non-negotiable and must be preserved regardless of which option is chosen."
            ),
            "Stakeholder Context": (
                "Identify every stakeholder affected by this decision, their role, their priorities, and any hard requirements or veto rights they hold. "
                "Note any stakeholder preferences that have already been communicated and whether they are binding or advisory. "
                "Describe any stakeholder conflicts: cases where two stakeholders have incompatible requirements, and how those conflicts are expected to be resolved. "
                "Document any stakeholder feedback received during the analysis so far, and how it has shaped the options under consideration. "
                "Flag any stakeholders who have not yet been consulted but whose input could materially change the analysis."
            ),
            "Objectives & Priorities": (
                "List every objective the decision is trying to satisfy, in priority order, with a clear definition of what 'satisfying' each objective means in measurable terms. "
                "Assign a relative weight or priority ranking to each objective so that options can be compared on a consistent scale. "
                "Distinguish between objectives that are fundamental (the decision exists to serve them) and constraints that are threshold requirements (must be met but not maximized). "
                "Note any objectives that are in direct tension with one another, and the current policy for resolving that tension. "
                "If the priority ranking was set by a stakeholder, attribute it so the next agent knows whether it can be adjusted."
            ),
            "Evaluation Criteria": (
                "Define the scoring rubric used to evaluate each option against each objective: the metric, the measurement method, and the scale (e.g., 1–5, normalized 0–1, or pass/fail). "
                "Note any criteria that are qualitative rather than quantitative, and describe the judgment process used to score them. "
                "Include any criteria that were considered and rejected from the scoring rubric, and the reason they were excluded. "
                "Describe the aggregation method used to combine per-objective scores into an overall ranking (weighted sum, lexicographic ordering, satisficing threshold, etc.). "
                "Note any criteria where the measurement is uncertain or where scores are estimates rather than measurements."
            ),
            "Options Evaluated": (
                "For each candidate option, provide a full description of what it entails and then score it against every objective using the evaluation criteria defined above. "
                "Include any option that was considered seriously, even if it was ruled out early, so the next agent does not re-propose it. "
                "Note the assumptions made in scoring each option: if an assumption is wrong, the score may change significantly. "
                "For each option, describe its implementation cost, reversibility, and any downstream effects that are not captured in the objective scores. "
                "Flag any option that scores well on all objectives but has a known disqualifying flaw (e.g., violates a stakeholder veto) so it is not inadvertently resurrected."
            ),
            "Frontier": (
                "List the non-dominated options: those for which no other evaluated option is strictly better on all objectives simultaneously. "
                "For each frontier option, describe the objective trade-off it represents: which objectives it optimizes at the expense of which others. "
                "Note any options that were on the frontier until a new option was proposed, and why they were superseded. "
                "If the frontier has only one option, explain why the other options are all dominated and confirm the frontier is correct. "
                "The frontier is the narrowed choice set: the next agent should focus its analysis on these options and not revisit dominated ones."
            ),
            "Leaning / Chosen": (
                "State the current preferred option among the frontier candidates, including the primary reason it is preferred and which objective it best serves relative to the alternatives. "
                "Describe any conditions under which this preference would change: new information, a revised priority ranking, or a stakeholder constraint that was not previously known. "
                "If the decision has already been made and committed, state so clearly and describe the implementation plan. "
                "If the decision is still provisional, describe what would be needed to confirm it: a missing data point, stakeholder approval, or resolution of an open question. "
                "Note any dissenting views on this preference and the strongest counter-argument in their favor."
            ),
            "Time Sensitivity": (
                "State when the decision must be finalized, the consequences of missing the deadline, and any intermediate milestones that must be met before then. "
                "Note any information that is expected to arrive before the deadline and could change the analysis (e.g., a benchmark result, a stakeholder reply, a market event). "
                "If the decision can be staged (commit to a reversible first step now, defer the irreversible commitment), describe the staging plan and its trade-offs. "
                "Note any actions that will become more costly or impossible after a certain point, creating pressure to decide sooner. "
                "If the deadline has already passed or is imminent, escalate that fact clearly so the next agent can prioritize accordingly."
            ),
            "Open Questions": (
                "List every question that remains unresolved before the decision can be confidently committed, with an owner and a target resolution date for each. "
                "For each open question, describe how much it affects the decision: would resolving it change the preferred option, or only confirm the current leaning? "
                "Note any questions that cannot be resolved before the deadline and describe how the decision should proceed despite the uncertainty. "
                "Flag any question whose answer is expected to arrive soon and that the next agent should wait for before taking action. "
                "End with a clear statement of the minimum information set needed to make a defensible final decision."
            ),
        }


class GoalStackHandoff(Handoff):
    """Prebuilt handoff for hierarchical goals (goal-hierarchy shape)."""

    DEFAULT_TITLE = "Goal Stack Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the nested goal hierarchy and the currently active path.
        return {
            "Root Goal": (
                "State the top-level goal that everything else in this task serves, in concrete terms that make it possible to verify when the goal has been achieved. "
                "Include the motivation behind the root goal — the need or opportunity it addresses — so the next agent can make good judgment calls when subgoals conflict. "
                "Note any constraints on the root goal itself: budget, deadline, quality threshold, or stakeholder requirement. "
                "Describe what a failed outcome looks like, not just a successful one, so the next agent can recognize when to escalate rather than continue. "
                "If the root goal was revised during the task, document the original goal and the revision so the hierarchy can be re-evaluated accordingly."
            ),
            "Goal Hierarchy": (
                "Provide the full tree of goals and subgoals: each node is a goal, its parent is the goal it serves, and its children are the subgoals that together achieve it. "
                "For each node, state the goal in one or two sentences, note its type (achievement goal vs. maintenance goal vs. query goal), and describe how it contributes to its parent. "
                "For leaf goals (no further decomposition), describe the concrete action or output required to satisfy the goal. "
                "For non-leaf goals, explain the decomposition logic: why these subgoals jointly achieve the parent, and whether they are sequential, parallel, or disjunctive. "
                "Use a structured format (indented list or tree diagram) so the hierarchy is visually navigable."
            ),
            "Success Conditions": (
                "For every goal in the hierarchy, state the specific, observable condition that must be true for the goal to be marked satisfied. "
                "Distinguish between conditions that are verifiable now versus conditions that can only be verified after the full task is complete. "
                "Note any goals whose success condition is ambiguous or subjective, and describe the judgment rule used to evaluate them. "
                "Include any acceptance tests, metrics, or review steps required to confirm satisfaction of each goal. "
                "Flag any goal whose success condition depends on external validation (a stakeholder sign-off, a test result, a user interaction) so the next agent knows to wait before marking it done."
            ),
            "Active Path": (
                "Trace the current chain from the root goal to the leaf goal currently being worked, listing each node in order and noting how far along each goal's progress is. "
                "Explain why this particular path through the hierarchy was prioritized over others, including any ordering constraints or dependencies that dictated the sequence. "
                "Note any goals on the active path that are partially complete, and describe exactly where the work is at in each. "
                "Identify any risks on the active path that could force a detour: a goal that may be harder than expected, a dependency that is not yet ready, or a resource that is running low. "
                "The active path is the next agent's entry point: it should be able to resume work at the current leaf goal without re-reading the entire hierarchy."
            ),
            "Resource Allocation": (
                "Describe how the available budget (time, tokens, API calls, or other resources) is distributed across the goal hierarchy, noting which goals have been allocated more resources and why. "
                "Report actual resource consumption so far: total used, breakdown by goal, and comparison to the original allocation. "
                "Flag any goal that has consumed significantly more or fewer resources than expected, as this may signal a planning error or an unexpected difficulty. "
                "Note any resource constraints that are now binding: a goal that is at risk of running out of budget before completion. "
                "Describe the reallocation policy: if a goal runs over budget, what should be cut or deferred to compensate?"
            ),
            "Satisfied Goals": (
                "List every goal that has been fully satisfied, including the specific output or artifact produced, the verification performed, and the resource cost. "
                "For each satisfied goal, note whether its output has been used by a parent or sibling goal yet, so the next agent knows what is already available. "
                "Flag any satisfied goal whose result may need to be revisited (e.g., because a sibling goal produced a conflicting output, or because the root goal was revised). "
                "Include the completion timestamp or sequence number for each satisfied goal so the next agent can reconstruct the order of progress. "
                "Do not remove satisfied goals from the hierarchy: they provide the context needed to understand how the current state was reached."
            ),
            "Suspended Goals": (
                "List every goal that was started but paused, including the reason for suspension (awaiting a prerequisite, resource exhaustion, blocked on external input) and the condition that would reactivate it. "
                "For each suspended goal, note the progress made before suspension so the next agent can resume without restarting. "
                "Identify any suspended goal on the critical path: one whose delay is blocking other goals from starting or completing. "
                "Note any suspended goals whose suspension window has expired or is about to expire, signaling that they need attention soon. "
                "Describe what the next agent must do to reactivate each suspended goal: fulfill the prerequisite, obtain the missing input, or make a decision that was deferred."
            ),
            "Failure Modes": (
                "For each unsatisfied goal in the hierarchy, describe the most likely ways it could fail: a subgoal that cannot be achieved, a dependency that cannot be met, or a success condition that cannot be verified. "
                "Note any failure that has already been observed and how it was handled (recovery, workaround, escalation, or goal revision). "
                "Describe the recovery plan for each critical failure: what the next agent should do if a key goal cannot be completed as planned. "
                "Flag any failure mode that would cascade upward through the hierarchy and invalidate parent goals. "
                "Note any goals whose failure mode is acceptable (the parent goal can still be satisfied even if this subgoal fails) so the next agent knows not to block on them."
            ),
            "Next Steps": (
                "Specify the next subgoal to pursue, including its position in the hierarchy, its success condition, and the concrete first action required to make progress on it. "
                "Note any prerequisites that must be confirmed before starting, and how to verify each one quickly. "
                "If the next step is a composition or integration of already-satisfied subgoals rather than new work, describe the integration task in enough detail to execute it. "
                "Include a time estimate or budget allocation for the next step so the next agent can plan its resource usage. "
                "End with a handoff trigger: the condition under which the next agent should stop and produce a new handoff rather than continuing."
            ),
        }


class CoverageHandoff(Handoff):
    """Prebuilt handoff for exhaustively sweeping a space (coverage-map shape)."""

    DEFAULT_TITLE = "Coverage Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the coverage map of done, pending, and skipped regions.
        return {
            "Objective & Scope": (
                "Define the space that must be fully covered: the set of items, regions, scenarios, inputs, or states that the task must visit or evaluate. "
                "Specify the boundary conditions: what is in scope (must be covered), what is explicitly out of scope (must not be covered), and any borderline cases whose inclusion is a judgment call. "
                "State the completion criterion: how will the next agent know when coverage is exhaustive, and what evidence is required to certify that a region was covered? "
                "Note any dynamic aspects of the scope: can new items be discovered during coverage that expand the space, and if so, how should they be handled? "
                "Include any ordering or partitioning strategy that was applied to the scope to make coverage systematic rather than ad hoc."
            ),
            "Prioritization Logic": (
                "Explain the order in which regions are being covered and the rationale: risk-based ordering, dependency ordering, alphabetical, random sampling, or some other scheme. "
                "Note any regions that were elevated in priority (covered earlier than their natural position in the ordering) and the reason for the elevation. "
                "Describe any regions that were deprioritized or deferred, and the condition under which they will be re-prioritized. "
                "If the prioritization logic changed during coverage (e.g., because a high-risk area was discovered), document the change and the trigger. "
                "Include the current position in the priority ordering so the next agent can resume without re-deriving the queue."
            ),
            "Coverage Map": (
                "Provide a comprehensive map of the entire scope, with each item or region labeled as one of: done (fully covered and verified), in-progress (partially covered), pending (not yet started), or skipped (intentionally excluded). "
                "Organize the map in the same structure as the scope definition so regions can be cross-referenced easily. "
                "For done items, include a pointer to the result or evidence of coverage so the next agent can verify it without re-doing the work. "
                "For in-progress items, describe exactly how far along they are and what remains. "
                "For pending items, note any known preconditions or dependencies that must be satisfied before they can be covered."
            ),
            "Coverage Depth": (
                "For each completed region, describe how thoroughly it was covered: surface-level (one pass, no verification), moderate (multiple approaches, spot-checked), or exhaustive (all sub-cases explored, results verified). "
                "Note any regions where coverage was intentionally shallow and the reason (time pressure, low risk, diminishing returns). "
                "Flag any regions that appeared fully covered but were later found to have gaps when a downstream task relied on them. "
                "Describe the verification method used to confirm each region was covered: automated testing, manual review, cross-reference against a checklist, or another approach. "
                "Include a per-region confidence level so the next agent knows where to focus additional scrutiny."
            ),
            "Completed": (
                "List every item or region that has been fully covered, including the method used, the result or finding for each, and any anomalies observed during coverage. "
                "For each completed item, note whether the result was as expected or surprising, and if surprising, what was discovered. "
                "Include any items that were covered but whose results are still pending verification, marked clearly as unverified. "
                "Note the resource cost (time, tokens, calls) of covering each item so the next agent can estimate the remaining coverage cost. "
                "Do not summarize clusters of similar items as one entry unless they are truly identical in outcome; preserve individual results."
            ),
            "Edge Cases Encountered": (
                "Document every edge case, anomaly, or unexpected behavior discovered during coverage, including the region in which it was found and its impact on the coverage result. "
                "For each edge case, note whether it was handled, deferred, or escalated, and whether it revealed a gap in the scope definition. "
                "Describe any edge cases that suggest the scope is larger than originally defined and that additional coverage may be needed. "
                "Note any edge cases that are pending further investigation and what that investigation requires. "
                "Include edge cases even if they turned out to be false alarms, so the next agent does not re-investigate them."
            ),
            "Gaps & Skipped": (
                "List every item or region that has not been covered, distinguishing between intentionally skipped (with a documented reason) and unintentionally missed (discovered after the fact). "
                "For each gap, assess its risk: how likely is it to matter, and what is the consequence of leaving it uncovered? "
                "For skipped items, state the condition under which they would be included (a stakeholder decision, a resource increase, a change in scope). "
                "Note any gaps that were discovered through downstream failures rather than through the coverage process itself, as these indicate a weakness in the coverage methodology. "
                "Prioritize the gaps by risk so the next agent knows which uncovered regions to address first if time permits."
            ),
            "Systematic Next": (
                "Identify the next region to cover based on the current prioritization logic, and explain why it is next in the queue. "
                "Describe the coverage method to use for this region: what to look for, how to verify it, and what a successful coverage result looks like. "
                "Note any preconditions that must be satisfied before this region can be covered, and how to confirm they are met. "
                "Estimate the resource cost of covering this region so the next agent can check it against the remaining budget. "
                "End with a fallback plan: if this region cannot be covered within the remaining budget, which region should be covered instead?"
            ),
        }


class BudgetBoundedHandoff(Handoff):
    """Prebuilt handoff for progress under a fixed budget (budget-curve shape)."""

    DEFAULT_TITLE = "Budget-Bounded Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on budget consumed versus remaining and the cut line.
        return {
            "Objective": (
                "Describe the goal being pursued under a fixed budget, including what a successful outcome looks like and what the minimum viable outcome is if the full goal cannot be reached. "
                "State the budget type and total: tokens, wall-clock time, API calls, monetary cost, or a combination, along with any hard caps that cannot be exceeded. "
                "Explain the priority ordering for the work: if the budget runs out before everything is done, what must have been completed for the task to be considered a partial success? "
                "Note any constraints on how the budget can be used: reserved amounts, rate limits, per-subtask caps, or restrictions on certain resource types. "
                "Include any flexibility in the budget: conditions under which it could be extended, and by how much."
            ),
            "Budget Allocation": (
                "Describe how the total budget was originally allocated across subtasks or work streams, including the rationale for each allocation. "
                "Note any reallocations made during the run — which subtask received more or less than originally planned, and why. "
                "Flag any subtask whose original allocation is now known to be insufficient based on actual consumption rates. "
                "Describe the policy for unspent budget: does it carry over to the next subtask, return to a central pool, or expire? "
                "Include a diagram or table of the allocation versus actual consumption so the next agent can see the budget picture at a glance."
            ),
            "Budget Status": (
                "Report the current state of every budget dimension: how much was available at the start, how much has been consumed, and how much remains. "
                "Break down consumption by subtask or work stream so the next agent can see where the budget was spent. "
                "Compute the burn rate: resources consumed per unit of work, and compare it to the planned burn rate to identify over- or under-spending. "
                "Project remaining capacity: given the current burn rate and the remaining work, estimate whether the budget will be sufficient. "
                "Flag any budget dimension that is at risk of exhaustion before the task is complete, and note how many units of work can still be done before hitting the cap."
            ),
            "Burn Rate & Forecast": (
                "Report the observed burn rate for each budget dimension across recent work units, and identify any trend: is the rate stable, increasing, or decreasing? "
                "Extrapolate the current burn rate to estimate when the budget will be exhausted if the current pace continues. "
                "Identify the cause of any significant burn rate changes: a more expensive subtask, a larger input, or a change in approach. "
                "If the burn rate can be reduced without sacrificing outcome quality, describe the specific optimizations available. "
                "Use the forecast to update the cut line and remaining work prioritization in the sections below."
            ),
            "Value Delivered": (
                "List every completed work item, ranked by its contribution to the overall objective, and assess the quality or completeness of each deliverable. "
                "For each completed item, note the budget it consumed and compute its value-per-resource ratio. "
                "Identify any work items that were completed but whose value has not yet been realized (e.g., they are dependencies for future work that has not started). "
                "Note any work items whose value turned out to be lower than expected, and the reason — this informs future prioritization. "
                "Summarize the total value delivered as a fraction of the full objective, so the next agent has a clear picture of progress."
            ),
            "Remaining Work": (
                "List every work item that has not yet been started or completed, ordered by value per unit of remaining cost (highest first). "
                "For each remaining item, estimate its resource cost based on the burn rate observed for similar completed items. "
                "Note any dependencies between remaining items: which must be completed before others can start. "
                "Flag any remaining item that is on the critical path to the minimum viable outcome, so the next agent knows not to skip it. "
                "Include any work items that are partially complete and estimate the remaining cost to finish each."
            ),
            "Risk Assessment": (
                "Identify every risk that could cause the task to fail or over-run its budget, including the likelihood of each risk and its potential impact. "
                "For each risk, describe a mitigation strategy that can be applied proactively and a contingency response if the risk materializes. "
                "Note any risks that have already materialized during the task, how they affected the budget, and what mitigation was applied. "
                "Flag any risk that is both high-likelihood and high-impact as a priority for the next agent to address. "
                "Include any risks that are budget-specific: scenarios where the remaining budget is insufficient to complete even the minimum viable outcome."
            ),
            "Cut Line": (
                "List the work items that will be dropped first if the budget runs out, in order from least to most valuable, with a clear rationale for each item's position. "
                "For each item below the cut line, describe the consequence of dropping it: what capability or quality is lost and who is affected. "
                "Note any items that appear low-value in isolation but are prerequisites for high-value items above the cut line, making their inclusion non-negotiable. "
                "Describe the process the next agent should follow to revise the cut line if the burn rate changes significantly. "
                "Include the current budget trigger point: the remaining balance at which the next agent should stop new work and finalize whatever is in progress."
            ),
            "Next Steps": (
                "Identify the next work item to start, selected from the remaining work list based on value per unit cost and dependency order. "
                "Include a concrete plan for that item: the approach, the expected resource cost, and the definition of done. "
                "Note any budget check the next agent should perform before starting: confirm that the estimated cost of the next item fits within the remaining budget. "
                "Describe the escalation path if the next item turns out to cost significantly more than estimated: pause and re-plan, or continue and accept a reduced cut line. "
                "End with the conditions under which the next agent should stop working and finalize the handoff, even if the task is not fully complete."
            ),
        }


class MigrationHandoff(Handoff):
    """Prebuilt handoff for moving a system from one state to another (state-delta shape)."""

    DEFAULT_TITLE = "Migration Handoff"

    def default_sections(self) -> dict[str, str]:
        # Structure centered on the delta between the current and target states.
        return {
            "Target State": (
                "Describe the end-state the system is being migrated toward in enough detail that the next agent can verify when the migration is complete. "
                "Include every component of the target state: schema, configuration, data, dependencies, interfaces, and behavior — not just the headline change. "
                "State the acceptance criteria for the target state: what tests, checks, or validations must pass before the migration is considered successful. "
                "Note any aspects of the target state that are still under definition or subject to change, so the next agent knows which parts of the migration plan may shift. "
                "If the target state was revised during the migration (e.g., requirements changed mid-execution), document both the original and revised targets and the reason for the change."
            ),
            "Migration Strategy": (
                "Describe the overall approach used to move from the current state to the target state: big-bang cutover, incremental migration, parallel-run with switchover, feature-flag rollout, or another pattern. "
                "Explain why this strategy was chosen over alternatives, including the trade-offs in risk, reversibility, downtime, and complexity. "
                "Note any phasing of the migration: which components are being migrated in which order, and what the rationale for that ordering is. "
                "Describe any coordination requirements: external dependencies (other teams, systems, or services) that must be aligned before or during the migration. "
                "If the strategy was revised during execution, document the original plan and the change so the next agent can understand why the current approach differs from what was originally planned."
            ),
            "Current State": (
                "Provide a precise snapshot of where the system is now, mid-transition: which components are in the target state, which are still in the source state, and which are in an intermediate state. "
                "Include all relevant metrics: schema version, data completeness, configuration flags active, service health, and any consistency checks that have been performed. "
                "Note any temporary scaffolding (backward-compatibility shims, dual-write logic, shadow tables) that is currently in place and will need to be removed later. "
                "Flag any inconsistency between components: cases where part of the system is operating in the target state and another part is still in the source state, creating a mixed-mode risk. "
                "Include the timestamp or sequence number of the last successfully applied migration step so the next agent can confirm it has the right starting point."
            ),
            "Validation Checkpoints": (
                "List every checkpoint that was planned to verify correctness during the migration, and for each, report whether it passed, failed, was skipped, or is pending. "
                "For each checkpoint that passed, describe what was verified and the evidence (test output, metric reading, review sign-off). "
                "For each checkpoint that failed, describe what was wrong, how it was resolved, and whether the resolution was verified. "
                "Note any checkpoints that were skipped and the reason — skipped checkpoints are a risk surface and should be documented explicitly. "
                "Include any checkpoints that are scheduled for the remaining migration steps, so the next agent knows what validation to perform after each step."
            ),
            "Completed Migrations": (
                "List every migration step that has been successfully applied, in the order applied, including the component affected, the change made, and the validation that confirmed success. "
                "For each completed step, note whether it is fully reversible, partially reversible, or irreversible, and describe the rollback procedure if one exists. "
                "Include any steps that were partially applied and then completed in a subsequent attempt, noting any complications encountered. "
                "Flag any completed steps that had side effects not anticipated in the migration plan, so the next agent can account for them. "
                "The completed migration log is the authoritative record of what has been applied: it must be accurate enough that a new agent could re-derive the current state from the source state plus this log."
            ),
            "Side Effects & Dependencies": (
                "Document every side effect observed during completed migration steps: data transformations with unexpected outputs, performance changes, dependency breakages, or behavioral changes in adjacent systems. "
                "Identify every external system or service that is affected by the migration, noting whether they have been notified, are actively coordinating, or are unaware. "
                "Describe any cascading changes triggered by completed steps that are not part of the original migration plan but must be tracked. "
                "Note any side effects that are temporary (will resolve once migration is complete) versus permanent (require additional remediation work). "
                "Flag any dependency that must be updated or notified before the next migration step can proceed safely."
            ),
            "Remaining Delta": (
                "Describe the complete gap between the current state and the target state, organized as a list of migration steps not yet applied. "
                "For each remaining step, estimate its complexity, expected resource cost, and risk level (likelihood of failure or unexpected side effects). "
                "Note any remaining steps that are blocked by an unresolved dependency, a pending decision, or a failed validation checkpoint. "
                "Order the remaining steps by the migration strategy's sequence, and flag any steps that must be executed in a specific order versus those that can be parallelized. "
                "Include an overall estimate of the remaining effort so the next agent can assess whether the migration will complete within the available budget."
            ),
            "Reversibility": (
                "For every completed migration step, state whether it is fully reversible (rollback procedure exists and has been verified), partially reversible (some data or state changes are permanent), or irreversible (cannot be undone). "
                "Identify the point of no return: the migration step after which a full rollback to the source state is no longer possible, and note whether that point has been passed. "
                "Describe the rollback procedure for the current state: what steps must be executed in what order to revert to a known-good state, and what data may be lost. "
                "Note any time-sensitive reversibility windows: steps that are reversible only within a certain time period or before subsequent steps are applied. "
                "Include a recommendation on when the next agent should abort and roll back rather than continuing to push forward, and what criteria should trigger that decision."
            ),
            "Next Steps": (
                "Specify the next migration step to apply, including the exact operation to perform, the component affected, and the validation checkpoint to run immediately after. "
                "Describe any preconditions that must be verified before starting the next step: a health check, a dependency confirmation, a stakeholder sign-off, or a data consistency check. "
                "Note the estimated resource cost of the next step and confirm it fits within the remaining budget. "
                "Describe the rollback plan specific to the next step: what to do if it fails partway through execution. "
                "End with a handoff trigger: the condition under which the next agent should stop and produce a new handoff rather than continuing to the step after."
            ),
        }


__all__ = [
    "Handoff",
    "EngineeringHandoff",
    "ResearchHandoff",
    "MinimalHandoff",
    "TreeSearchHandoff",
    "DecompositionHandoff",
    "RefinementLoopHandoff",
    "ConstraintSatisfactionHandoff",
    "BacktrackingHandoff",
    "TradeoffHandoff",
    "GoalStackHandoff",
    "CoverageHandoff",
    "BudgetBoundedHandoff",
    "MigrationHandoff",
]
