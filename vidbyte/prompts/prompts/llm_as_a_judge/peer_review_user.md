You are a peer reviewer evaluating a model's response. Provide your verdict AND your confidence in that verdict.

Score from 0.0 to 1.0. Confidence from 0.0 to 1.0 (0=completely uncertain, 1=fully certain).
Output only a valid JSON object:
{{"score": float, "passed": boolean, "confidence": float, "reason": "explanation"}}

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
