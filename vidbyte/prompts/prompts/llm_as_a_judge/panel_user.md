You are an objective judge evaluating a model's response.

Score the response on a scale from 0.0 to 1.0 based on accuracy, completeness, and clarity.
Output only a valid JSON object:
{{"score": float, "passed": boolean, "reason": "explanation"}}

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
