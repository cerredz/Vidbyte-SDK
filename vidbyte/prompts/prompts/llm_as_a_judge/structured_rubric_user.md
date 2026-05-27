You are an objective judge. Evaluate the model's response across multiple dimensions using the rubric below.

{rubric_block}

Score each dimension using the level numbers defined in the rubric.
Output only a valid JSON object:
{{"scores": {{"dimension_name": integer_level}}, "reasons": {{"dimension_name": "explanation"}}}}

Task Prompt:
{prompt}

Model Response:
{actual}

Expected Output:
{expected}
