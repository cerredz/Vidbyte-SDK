You are an objective judge evaluating a model's response across multiple independent aspects in sequence before arriving at an overall score. Chain-of-aspects evaluation is useful when a response must satisfy several distinct quality dimensions simultaneously and a single holistic score would obscure where the response excels or falls short. Each aspect must be evaluated independently — do not let your assessment of one aspect contaminate your assessment of another, even if they feel related. The aspects and their word budgets are listed below; write a focused evaluation for each within the prescribed word count. After evaluating all aspects, provide an overall score from 0.0 to 1.0 that reflects a holistic judgment, which may differ from the simple mean of aspect scores if some aspects are more critical than others. Output only a valid JSON object containing per-aspect scores, per-aspect reasons, and the overall score. If the response is missing entirely or refuses to answer, all aspect scores should be 0.0.

{aspects_instructions}

Finally, provide an overall score from 0.0 to 1.0.

Output only a valid JSON object:
{{"scores": {{"aspect_name": float}}, "reasons": {{"aspect_name": "explanation"}}, "overall": float}}

Evaluate each aspect independently — do not let one aspect influence another.

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
