{{
  "decision": "approve" or "reject",
  "summary": string,
  "findings": [string, ...]
}}

- `decision` is "approve" when the change accomplishes the task correctly and completely, and
  "reject" when it does not.
- `summary` gives the decisive reasons for your decision. It is non-empty.
- `findings` holds one string per concrete problem the change must fix, each naming the file
  and what is wrong; it is an empty list when you found none.
