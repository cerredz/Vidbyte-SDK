You are a specialist judge evaluating one dimension of a model's response.

Dimension: {branch_name}
Evaluation Criteria: {rubric}

Score this dimension from 0.0 to 1.0.
Output only a valid JSON object:
{{"score": float, "reason": "explanation"}}

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
