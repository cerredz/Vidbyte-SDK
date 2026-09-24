## `deliverables`

Return exactly one `deliverables` entry for every `multi_part.deliverables` item in the initial state, using each exact `id`. Do not omit an item because it was not worked on, and do not invent extra items. For each entry:

- Set `status` to `complete` only when the snapshot contains direct evidence that the requested output is present; use `incomplete` when work is explicitly missing; use `unclear` when the snapshot does not establish either condition.
- Put source-linked excerpts in `evidence`.
- Put the remaining requirement or uncertainty in `remaining`. Use `none` only when the deliverable is complete and the evidence supports that claim.
- Keep statements scoped to this deliverable. Do not treat one implementation, file, example, or use case as evidence for broader requested coverage unless the snapshot shows that broader coverage.
