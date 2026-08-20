# Proactive scheduler operations

Apply `deploy/kubernetes/proactive-cronjob.yaml` only after creating the tenant/user schedules and configuring workload authentication.

The job runs every five minutes with `concurrencyPolicy: Forbid`. It invokes one explicit tenant/user scope and relies on persisted due times, change snapshots, and notification dedupe keys. Retrying after an ambiguous network failure is safe: completed schedules have already advanced, and duplicate notification keys are rejected.

Create one scoped CronJob per ProductOS leadership workspace. The token must be short-lived, include matching `productos_user_id` and `productos_tenant_id` claims, use audience `productos-api`, and include `productos:scheduler`. Populate the mounted token through an approved workload-identity broker or external-secrets CSI integration. The example manifest intentionally contains no Secret object or credential value.

Alert on failed jobs, authentication failures, and persistent `schedules_run=0` when enabled due schedules exist. Do not log the bearer token. Pin the API image to an immutable digest before production deployment.
