# Milestone 6 — Proactive Leadership Support

Milestone 6 completes the V1 milestone sequence with conservative, observable proactivity on the existing application-owned runtime.

## Implemented boundary

- Durable tenant/user-scoped daily and weekly schedules with timezone-aware next-run calculation.
- A deterministic scheduler endpoint that records its own agent run and trace, suitable for invocation by deployment cron.
- Traceable Daily Product Brief and Weekly Product Leadership Review artifacts.
- Decision-review and risk scans derived only from ProductOS records and accessible evidence.
- Stable semantic fingerprints for change detection and unique delivery keys for notification deduplication.
- In-app notification preferences with opt-in delivery, category controls, minimum significance, quiet hours, and a daily cap.
- A Home view for documented attention, evidenced wins, decision debt, unread notifications, and the latest brief.
- A 30-case proactive evaluation catalog with proactive noise rate as the critical metric.

## Notification gate

A notification is eligible only when all of the following are true:

1. The observed semantic state is new or materially changed.
2. Significance meets the configured threshold and is material.
3. Confidence is medium or high.
4. A concrete recommended next step exists.
5. User/category preferences permit delivery.
6. The event is outside quiet hours and below the daily cap.
7. The unique delivery fingerprint has not already been persisted.

Brief creation is intentionally separate from notification delivery. A scheduled brief can be created without sending a notification when no new event clears the gate.

## Operational model

The API does not run a hidden in-process polling loop. A deployment-owned cron invokes `POST /v1/proactive/run` with an explicit tenant and user scope. This keeps scheduling observable, restart-safe, testable, and horizontally deployable without duplicate background workers. All V1 delivery is in-app; email, Slack, calendar, and other external writes remain out of scope and would require explicit approval contracts.

## Known limitations

- Proactive state reflects only records stored in ProductOS and connected sources the user can access.
- Missing or unchanged records do not prove that nothing changed elsewhere.
- Rule-based materiality must be evaluated against representative production data before broad rollout.
- Change snapshots record active observed states; resolved-state celebration or escalation policies are not inferred.
- The scheduler endpoint needs deployment cron configuration in each environment.
