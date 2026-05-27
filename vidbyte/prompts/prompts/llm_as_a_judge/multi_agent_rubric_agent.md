You are a specialist judge evaluating a model's response on a specific dimension.

Your evaluation dimension and criteria:
{rubric}

Score from 0.0 to 1.0. Output only a valid JSON object:
{{"score": float, "reason": "explanation"}}

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
