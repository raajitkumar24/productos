# Representative-data evaluation operations

The checked-in milestone catalogs are synthetic regression definitions. They are not representative production data and ProductOS does not report their validation as an agent quality pass rate.

To create a measured quality run:

1. Build an approved, redacted dataset derived from representative workflows. Preserve an immutable dataset name and version outside ProductOS.
2. Review access, retention, and employee-data implications. Do not include credentials, unnecessary personal information, or unrestricted company content.
3. Configure a production subject model and, preferably, a separate judge model.
4. Obtain a short-lived token with `productos:evaluator` and the intended user/tenant claims.
5. Submit batches of up to 20 cases to `POST /v1/evaluations/run` using the schema in `evals/representative/dataset.example.json`. The conservative synchronous bound avoids an implicit job-queue dependency; use immutable batch identifiers for larger datasets.
6. Inspect the persisted run and case results in the Evaluations UI or `GET /v1/evaluations/{id}`.

Each case executes the full ProductOS chat runtime—including scoped memory retrieval, evidence retrieval, tool policy, tracing, and answer synthesis—without persisting an evaluation conversation or memory candidate. Each run stores the dataset identity, subject model, judge model, runtime version, metrics version, actual output, structured judge result, errors, and an explicit generalization limitation. A case passes only with score 4 or 5 and no critical failure. Provider errors count against the total through the conservative pass-rate denominator.

LLM-as-Judge output is measurement evidence, not ground truth. Review failures manually, monitor judge drift, use fixed judge settings, and rerun a frozen calibration set before changing judge model or prompt.
