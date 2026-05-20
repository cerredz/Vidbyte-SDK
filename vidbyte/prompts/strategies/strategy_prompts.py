from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class _PromptBundle:
    prompts: Mapping[str, str]

    def export(self) -> dict[str, str]:
        # Return a caller-owned copy so prompt templates can be inspected safely.
        return dict(self.prompts)


class ContextEngineeringPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define the reusable prompt-writing contract from Vidbyte context engineering practice.
        super().__init__({"guideline_prompt": "Write prompts as dense operational context: role, objective, constraints, inputs, procedure, output contract, and quality bar. Avoid vague encouragement; encode the actual work policy."})


class ChainOfThoughtPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define sequential reasoning prompts as inspectable SDK assets.
        super().__init__({"reason_prompt": "Solve the task carefully. Reason step by step before giving the final answer. End with a section labeled 'Final answer:'."})


class StepBackPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define abstraction-first prompts as inspectable SDK assets.
        super().__init__({"principle_prompt": "Step back from the specific task. Identify the general principles, abstractions, or concepts needed. Do not solve the original task yet.", "answer_prompt": "Use these general principles to solve the original task. End with 'Final answer:'."})


class ChainOfDraftPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define terse-draft reasoning prompts as inspectable SDK assets.
        super().__init__({"draft_prompt": "Solve the task using concise draft reasoning. Each intermediate reasoning step must be at most {max_words_per_step} words. After the terse draft, provide a clear final answer."})


class SkeletonOfThoughtPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define skeleton-first and expansion prompts as inspectable SDK assets.
        super().__init__({"skeleton_prompt": "Create a concise numbered skeleton for answering the task. Use no more than {max_points} points. Do not fill in the details yet.", "expand_prompt": "Complete this one skeleton point for the original task."})


class SelfConsistencyPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define independent sampling prompts as inspectable SDK assets.
        super().__init__({"sample_prompt": "Solve independently. End with 'Final answer:'. Sample {index} of {samples}."})


class BudgetForcingPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define continuation prompts for prompt-level budget forcing.
        super().__init__({"initial_prompt": "Solve the task carefully. If the answer seems premature, continue checking before finalizing. End with 'Final answer:'.", "continue_prompt": "Continue from the previous attempt. Double-check assumptions, fix mistakes, and provide a final answer."})


class AnswerConvergencePrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define repeated independent answer prompts for convergence checks.
        super().__init__({"attempt_prompt": "Solve independently and end with 'Final answer:'. Attempt {index}."})


class PlanAndExecutePrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define plan, execution, and synthesis prompts as distinct prompt assets.
        super().__init__({"plan_prompt": "Create a concise numbered plan for solving the task. Do not execute the plan yet.", "execute_prompt": "Execute this plan step for the original task.", "final_prompt": "Synthesize the executed steps into a final answer."})


class ParadigmRouterPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define select-then-solve routing prompts as inspectable SDK assets.
        super().__init__({"route_prompt": "Select the best reasoning strategy for this task. Available strategies: {options}. Return only the exact strategy name."})


class TreeOfThoughtsPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define branching thought generation, evaluation, and finalization prompts.
        super().__init__({"branch_prompt": "Generate {branches} diverse candidate reasoning branches for the task. Number each branch.", "evaluate_prompt": "Score each candidate branch from 1-10 for correctness, feasibility, and completeness. Return the best branch number and rationale.", "final_prompt": "Use the best evaluated branch to produce the final answer."})


class MultiAgentReflexionPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define structured disagreement prompts for multi-agent reflexion.
        super().__init__({"draft_prompt": "Produce an initial answer to the task.", "critic_prompt": "Review the draft from the perspective of {critic_role}. Identify concrete weaknesses and corrections.", "final_prompt": "Revise the draft using the structured critique. End with 'Final answer:'."})


class AgenticRagPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define retrieval-decision and grounded-answer prompts for agentic RAG.
        super().__init__({"retrieve_prompt": "Decide what information must be retrieved before answering. Return concise retrieval queries.", "answer_prompt": "Answer using the retrieved context. If context is insufficient, state the gap explicitly."})


class ExpertPromptingPrompts(_PromptBundle):
    def __init__(self) -> None:
        # Define expert-activation prompts for eliciting field-specific knowledge.
        super().__init__({"expert_prompt": "Answer as a domain expert in {domain}. Use expert-level concepts, constraints, and edge cases. Avoid generic explanation. End with 'Final answer:'."})

