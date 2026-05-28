"""Context Protocol Header

Description:
    Default prompt templates for all 19 LLM-as-a-judge strategy graders.
Purpose:
    Centralises every inline _DEFAULT_*_TEMPLATE string so they are discoverable,
    auditable, and overridable via TemplatesRegistry without touching judge files.
Architecture:
    - JUDGE_TEMPLATES: flat dict keyed by "<judge_name>.<slot>" mapping to template str.
Relations:
    Consumed by vidbyte.lib.eval.template_registry.TemplatesRegistry on instantiation.
"""

from __future__ import annotations

JUDGE_TEMPLATES: dict[str, str] = {
    # --- chain_of_thought ---
    "chain_of_thought.user": (
        "You are an objective judge evaluating a model's response.\n\n"
        "Think through your evaluation step by step ({cot_budget}). "
        "Consider accuracy, completeness, and clarity.\n\n"
        "After your reasoning, output your final score on the last line in this exact format:\n"
        "Score: X.XX\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- binary ---
    "binary.user": (
        "You are an objective judge answering a single yes/no question about a model's response.\n\n"
        "Criterion: {criterion}\n\n"
        "Answer with a JSON object only:\n"
        "{{\"passed\": true or false, \"reason\": \"one sentence explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- few_shot ---
    "few_shot.user": (
        "You are an objective judge evaluating model responses. Study the examples below to calibrate your scoring scale, "
        "then evaluate the final response.\n\n"
        "--- CALIBRATION EXAMPLES ---\n{examples_block}\n--- END EXAMPLES ---\n\n"
        "Now evaluate the following response on a scale from 0.0 to 1.0.\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- pairwise ---
    "pairwise.user": (
        "You are an objective judge comparing two responses to the same prompt. Decide which response is better.\n\n"
        "Output only a valid JSON object:\n"
        "{{\"winner\": \"A\" or \"B\" or \"Tie\", \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Response A:\n{response_a}\n\n"
        "Response B:\n{response_b}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- self_reference ---
    "self_reference.generation": (
        "Answer the following question or task as completely and accurately as you can.\n\n"
        "Task:\n{prompt}"
    ),
    "self_reference.eval": (
        "You are an objective judge comparing a model's response to a reference answer.\n\n"
        "Score the model's response on a scale from 0.0 to 1.0 based on how well it matches the reference.\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Reference Answer:\n{reference}\n\n"
        "Model Response:\n{actual}"
    ),
    # --- self_eval ---
    "self_eval.user": (
        "You are an objective judge evaluating {framing_header}.\n\n"
        "Score the response on a scale from 0.0 to 1.0 based on accuracy, completeness, and clarity.\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Response to evaluate:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- criteria_decomposition ---
    "criteria_decomposition.decompose": (
        "You are a careful evaluator. Break the following evaluation criterion into exactly "
        "{num_sub_criteria} specific, non-overlapping sub-questions that can each be answered yes or no.\n\n"
        "Criterion: {criterion}\n\n"
        "Output a numbered list of sub-questions only. No other text."
    ),
    "criteria_decomposition.eval": (
        "You are an objective judge. Evaluate a model's response by reasoning through each "
        "sub-question below, then produce a final score.\n\n"
        "Sub-questions:\n{checklist}\n\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"passed\": boolean, \"reason\": \"brief explanation referencing the sub-questions\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- chain_of_aspects ---
    "chain_of_aspects.user": (
        "You are an objective judge. Evaluate the model's response aspect by aspect, then produce an overall score.\n\n"
        "{aspects_instructions}\n\n"
        "Finally, provide an overall score from 0.0 to 1.0.\n\n"
        "Output only a valid JSON object:\n"
        "{{\"scores\": {{\"aspect_name\": float}}, \"reasons\": {{\"aspect_name\": \"explanation\"}}, \"overall\": float}}\n\n"
        "Evaluate each aspect independently — do not let one aspect influence another.\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- branch_solve_merge ---
    "branch_solve_merge.branch": (
        "You are a specialist judge evaluating one dimension of a model's response.\n\n"
        "Dimension: {branch_name}\nEvaluation Criteria: {rubric}\n\n"
        "Score this dimension from 0.0 to 1.0.\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    "branch_solve_merge.merge": (
        "You are a senior judge synthesising multiple specialist evaluations into a single final score.\n\n"
        "Specialist evaluations:\n{branch_results}\n\n"
        "Produce a final overall score from 0.0 to 1.0, weighing the evaluations appropriately.\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"reason\": \"synthesis of the evaluations\"}}"
    ),
    # --- llm_rubric ---
    "llm_rubric.generate": (
        "You are an expert evaluator. Create a detailed scoring rubric for evaluating responses "
        "to the following type of task.\n\n"
        "Task type: {task_description}\n\n"
        "Write a rubric with {rubric_scale} levels (1 through {rubric_scale}), where 1 is the lowest "
        "quality and {rubric_scale} is the highest. For each level, write a one-sentence description "
        "of what a response at that level looks like.\n\n"
        "Output a plain-text rubric only. No JSON, no headers."
    ),
    "llm_rubric.eval": (
        "You are an objective judge. Use the rubric below to evaluate the model's response.\n\n"
        "Rubric:\n{rubric}\n\n"
        "Score the response according to the rubric, then normalise your score to a 0.0-1.0 scale.\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"passed\": boolean, \"reason\": \"which rubric level best matches and why\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- structured_rubric ---
    "structured_rubric.user": (
        "You are an objective judge. Evaluate the model's response across multiple dimensions using the rubric below.\n\n"
        "{rubric_block}\n\n"
        "Score each dimension using the level numbers defined in the rubric.\n"
        "Output only a valid JSON object:\n"
        "{{\"scores\": {{\"dimension_name\": integer_level}}, \"reasons\": {{\"dimension_name\": \"explanation\"}}}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- atomic_claims ---
    "atomic_claims.decompose": (
        "You are a careful fact-checker. Extract every distinct factual claim made in the response below. "
        "Each claim should be a single declarative sentence that can be independently verified.\n\n"
        "Response:\n{actual}\n\n"
        "Output only a valid JSON object:\n"
        "{{\"claims\": [\"claim 1\", \"claim 2\", ...]}}\n\n"
        "If there are no factual claims, return {{\"claims\": []}}"
    ),
    "atomic_claims.verify": (
        "You are a fact-checker. Determine whether the following claim is true based on your knowledge.\n\n"
        "Claim: {claim}\n\n"
        "Output only a valid JSON object:\n"
        "{{\"verified\": true or false, \"reason\": \"one sentence explanation\"}}"
    ),
    # --- constitutional ---
    "constitutional.check": (
        "You are a compliance judge. Determine whether the response below violates the following principle.\n\n"
        "Principle: {principle}\n\n"
        "Output only a valid JSON object:\n"
        "{{\"violated\": true or false, \"reason\": \"one sentence explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}"
    ),
    # --- panel ---
    "panel.user": (
        "You are an objective judge evaluating a model's response.\n\n"
        "Score the response on a scale from 0.0 to 1.0 based on accuracy, completeness, and clarity.\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- multi_agent_rubric ---
    "multi_agent_rubric.agent": (
        "You are a specialist judge evaluating a model's response on a specific dimension.\n\n"
        "Your evaluation dimension and criteria:\n{rubric}\n\n"
        "Score from 0.0 to 1.0. Output only a valid JSON object:\n"
        "{{\"score\": float, \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    "multi_agent_rubric.merge": (
        "You are a senior judge. Synthesise the following specialist evaluations into a single final score.\n\n"
        "Evaluations:\n{agent_results}\n\n"
        "Produce a final score from 0.0 to 1.0.\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"reason\": \"synthesis\"}}"
    ),
    # --- multi_agent_debate ---
    "multi_agent_debate.initial": (
        "You are an objective judge. Evaluate the model's response and produce your initial verdict.\n\n"
        "Score from 0.0 to 1.0. Output only a valid JSON object:\n"
        "{{\"score\": float, \"passed\": boolean, \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    "multi_agent_debate.round": (
        "You are a judge in a panel. Below are the verdicts from other judges on the same response. "
        "Review them and decide whether to maintain or revise your position. You may disagree if you have good reason.\n\n"
        "Other judges' verdicts:\n{prior_verdicts}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}\n\n"
        "Output only a valid JSON object with your (possibly revised) verdict:\n"
        "{{\"score\": float, \"passed\": boolean, \"reason\": \"your reasoning, including whether you changed your position and why\"}}"
    ),
    # --- meta_judge ---
    "meta_judge.user": (
        "You are a meta-judge evaluating the quality of another judge's evaluation. Check whether the verdict below "
        "is coherent, whether the reason is consistent with the score, and whether important criteria were missed.\n\n"
        "Primary Judge's Verdict:\nScore: {primary_score}\nReason: {primary_reason}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}\n\n"
        "Output only a valid JSON object:\n"
        "{{\"quality_ok\": true or false, \"quality_reason\": \"explanation of why the verdict is or is not high quality\"}}"
    ),
    # --- peer_review ---
    "peer_review.user": (
        "You are a peer reviewer evaluating a model's response. "
        "Provide your verdict AND your confidence in that verdict.\n\n"
        "Score from 0.0 to 1.0. Confidence from 0.0 to 1.0 (0=completely uncertain, 1=fully certain).\n"
        "Output only a valid JSON object:\n"
        "{{\"score\": float, \"passed\": boolean, \"confidence\": float, \"reason\": \"explanation\"}}\n\n"
        "Task Prompt:\n{prompt}\n\n"
        "Model Response:\n{actual}\n\n"
        "Expected Output:\n{expected}"
    ),
    # --- mixture_of_prompts ---
    "mixture_of_prompts.router": (
        "You are a task classifier. Given a prompt, identify which task type it belongs to from the list below.\n\n"
        "Available task types:\n{task_types}\n\n"
        "Output only the exact task type name that best matches. No explanation, no punctuation — just the name.\n\n"
        "Prompt to classify:\n{prompt}"
    ),
}

__all__ = ["JUDGE_TEMPLATES"]
