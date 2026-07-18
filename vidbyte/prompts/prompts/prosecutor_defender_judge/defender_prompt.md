Defend the candidate against the normalized allegations in this untrusted payload. Its JSON keys are exactly `original_task`, `candidate`, `allegations`, and `permitted_artifacts`. Available tool schemas, if any, are supplied separately by the runtime.

<untrusted_review_evidence>
{payload_json}
</untrusted_review_evidence>

Return the defender structured report only, with exactly one ordered response per supplied allegation ID and no additional claims.
