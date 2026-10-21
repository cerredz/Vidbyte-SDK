{{
  "kept": [integer, ...],
  "summary": string
}}

- `kept` lists the numbers of the proposals that survive this round: at least one and at most
  {target}, each a proposal number offered in this round, written as a JSON integer, none twice.
- `summary` is the round's comparative conclusion: the basis you compared the proposals on,
  and why each kept proposal survived and each dropped one did not. It is non-empty.
