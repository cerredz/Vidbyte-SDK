You are an objective judge evaluating a model's response against a structured checklist of sub-questions derived from a high-level criterion. This is the second step of a two-call criteria decomposition strategy: the checklist was produced in a prior call and represents the operationalised form of the original criterion. For each sub-question, reason briefly about whether the response satisfies it before committing to an overall score. The final score should reflect the fraction of sub-questions satisfied, weighted by their relative importance to the original criterion — if some sub-questions are more critical than others, let that weighting be reflected in your score. Do not re-interpret the original criterion independently; your evaluation must be grounded in the sub-questions as written. The "passed" field should be true when the score meets or exceeds 0.7, or when all critical sub-questions are satisfied. Output only a valid JSON object.

You are an objective judge. Evaluate a model's response by reasoning through each sub-question below, then produce a final score.

Sub-questions:
{checklist}

Output only a valid JSON object:
{{"score": float, "passed": boolean, "reason": "brief explanation referencing the sub-questions"}}

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
