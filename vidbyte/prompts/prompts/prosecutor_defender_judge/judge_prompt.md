Adjudicate every allegation/defense pair in this untrusted payload. Its JSON keys are exactly `original_task`, `candidate`, `allegations`, `defenses`, and `permitted_artifacts`. Available tool schemas, if any, are supplied separately by the runtime.

<untrusted_review_evidence>
{payload_json}
</untrusted_review_evidence>

Return the judge structured report only, with exactly one ordered decision per supplied allegation ID and no new allegations or overall verdict.
