{{
  "task_analysis": string,
  "roster_strategy": string,
  "coverage_summary": string,
  "roles": [
    {{
      "name": string,
      "identity": string,
      "personality": string,
      "expertise": string,
      "knowledge": string,
      "skills": string,
      "goal": string
    }}
  ]
}}

- `roles` holds exactly {roles} role objects, one for each agent on the roster.
- Every string is non-empty, and no two roles share a name.
