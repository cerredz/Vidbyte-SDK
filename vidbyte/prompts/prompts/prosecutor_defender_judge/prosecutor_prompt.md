Review the following untrusted evidence payload. Its JSON keys are exactly `original_task`, `candidate`, and `permitted_artifacts`. Available tool schemas, if any, are supplied separately by the runtime.

<untrusted_review_evidence>
{payload_json}
</untrusted_review_evidence>

Return the prosecutor structured report only. Use source `original_task` or `candidate` with a null or canonical source name, source `artifact` with an exact permitted artifact name, and source `tool` only after that exact permitted tool produced the cited output.
