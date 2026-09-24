## Section `required_sequence`
Fill `sections.required_sequence.stages` with exactly one entry for every stage in the run state's `sections.required_sequence.stages`. Use the same `stage_id` values, in the same order. Include every stage, even one with no work.

Decide which events belong to a stage by comparing them with that stage's `name`, `source_text`, and `completion_criterion`. An event belongs to the stage whose work it performs. When the agent went back to an earlier stage later in the run, for example by editing the draft after the review had begun, those later events still belong to the earlier stage.

For each stage:
- `stage_id`: the stage's ID from the run state.
- `observed_work`: each piece of work the log shows for this stage, as `{"description": "...", "event_ids": ["E4", "E5"]}`.
- `outputs_produced`: what this stage produced, as the log shows it, such as file names, notes, or results. Use an empty list when it produced nothing.
- `inputs_used`: what this stage worked from, as the log shows it. Name earlier outputs when the stage used them, for example "notes.md from the Research stage". Use an empty list when it used nothing.
- `first_event_id`: the ID of the first event that performs this stage's work. Use an empty string when no event does.
- `last_work_event_id`: the ID of the last event that performs this stage's work, including any return to this stage later in the run. Use an empty string when no event does.
- `failures`: failed or abandoned attempts at this stage's work, in the same shape as `observed_work`.
- `missing_or_uncertain`: the parts of the stage's `completion_criterion` that the log does not show or cannot show. Use an empty list when there are none.

Do not decide whether a stage is complete. Report what the log shows and what it does not.
