import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from productos.application.ports import TraceRepository
from productos.application.repositories import (
    AgentRunRepository,
    ArtifactRepository,
    ProactiveRepository,
)
from productos.config import Settings
from productos.domain.agent import AgentState, RunStatus
from productos.domain.management import (
    ConfidenceLevel,
    ManagementSignal,
    SignalStatus,
    SignalType,
    Significance,
)
from productos.domain.proactive import (
    ChangeEvent,
    ChangeSnapshot,
    DailyProductBrief,
    NotificationPatch,
    NotificationPreferences,
    NotificationPreferencesPatch,
    NotificationStatus,
    ProactiveNotification,
    ProactiveSchedule,
    ScheduleCreate,
    ScheduleFrequency,
    ScheduleKind,
    SchedulePatch,
    SchedulerRunResult,
)
from productos.domain.trace import TraceEvent, TraceEventType
from productos.domain.workflow import Artifact, ArtifactType, WorkflowName
from productos.management import ManagementService

LEVEL_ORDER = {
    Significance.LOW: 0,
    Significance.MEDIUM: 1,
    Significance.HIGH: 2,
    Significance.CRITICAL: 3,
}


class ProactiveLeadershipService:
    def __init__(
        self,
        repository: ProactiveRepository,
        management: ManagementService,
        artifacts: ArtifactRepository,
        runs: AgentRunRepository,
        traces: TraceRepository,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._management = management
        self._artifacts = artifacts
        self._runs = runs
        self._traces = traces
        self._settings = settings

    async def preferences(self, tenant_id: UUID, user_id: UUID) -> NotificationPreferences:
        stored = await self._repository.get_preferences(tenant_id, user_id)
        if stored:
            return stored
        return NotificationPreferences(tenant_id=tenant_id, user_id=user_id)

    async def patch_preferences(
        self,
        patch: NotificationPreferencesPatch,
        tenant_id: UUID,
        user_id: UUID,
    ) -> NotificationPreferences:
        current = await self.preferences(tenant_id, user_id)
        for field in patch.model_fields_set:
            value = getattr(patch, field)
            if value is not None:
                setattr(current, field, value)
        self._validate_timezone(current.timezone)
        current.updated_at = datetime.now(UTC)
        return await self._repository.save_preferences(current)

    async def create_schedule(
        self, request: ScheduleCreate, tenant_id: UUID, user_id: UUID
    ) -> ProactiveSchedule:
        self._validate_timezone(request.timezone)
        existing = await self._repository.list_schedules(tenant_id, user_id)
        if any(item.kind == request.kind for item in existing):
            raise ValueError(f"A {request.kind} schedule already exists for this scope")
        schedule = ProactiveSchedule(
            **request.model_dump(exclude={"tenant_id", "user_id"}),
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return await self._repository.create_schedule(schedule)

    async def patch_schedule(
        self,
        schedule_id: UUID,
        request: SchedulePatch,
        tenant_id: UUID,
        user_id: UUID,
    ) -> ProactiveSchedule | None:
        schedule = await self._repository.get_schedule(schedule_id, tenant_id, user_id)
        if not schedule:
            return None
        for field in request.model_fields_set:
            value = getattr(request, field)
            if value is not None:
                setattr(schedule, field, value)
        self._validate_timezone(schedule.timezone)
        if schedule.frequency == ScheduleFrequency.WEEKLY and schedule.weekday is None:
            raise ValueError("weekday is required for a weekly schedule")
        schedule.updated_at = datetime.now(UTC)
        return await self._repository.update_schedule(schedule)

    async def run(
        self,
        tenant_id: UUID,
        user_id: UUID,
        now: datetime | None = None,
        force_kinds: list[ScheduleKind] | None = None,
    ) -> SchedulerRunResult:
        started = self._aware(now or datetime.now(UTC))
        state = await self._start_run(
            tenant_id, user_id, "Evaluate due proactive schedules", "scheduler.v1"
        )
        schedules = await self._repository.list_schedules(tenant_id, user_id)
        forced = set(force_kinds or [])
        due = [
            item
            for item in schedules
            if (item.enabled and self._aware(item.next_run_at) <= started) or item.kind in forced
        ]
        artifacts: list[UUID] = []
        notifications: list[UUID] = []
        suppressed: list[str] = []
        for schedule in due:
            created_artifacts, created_notifications, reasons = await self._run_kind(
                schedule.kind, tenant_id, user_id, started
            )
            artifacts.extend(created_artifacts)
            notifications.extend(created_notifications)
            suppressed.extend(reasons)
            schedule.last_run_at = started
            schedule.next_run_at = self._next_run(schedule, started)
            schedule.updated_at = datetime.now(UTC)
            await self._repository.update_schedule(schedule)
        result = SchedulerRunResult(
            run_id=state.run_id,
            started_at=started,
            completed_at=datetime.now(UTC),
            schedules_evaluated=len(schedules),
            schedules_run=len(due),
            artifacts_created=artifacts,
            notifications_created=notifications,
            suppressed=suppressed,
        )
        await self._finish_run(state, result.model_dump(mode="json"))
        return result

    async def daily_brief(
        self, tenant_id: UUID, user_id: UUID, now: datetime | None = None
    ) -> tuple[DailyProductBrief, Artifact, list[ChangeEvent]]:
        observed_at = self._aware(now or datetime.now(UTC))
        signals, _ = await self._management.refresh_intelligence(tenant_id, user_id)
        active = [item for item in signals if item.status == SignalStatus.ACTIVE]
        debt = await self._management.decision_debt(user_id)
        changes = await self._detect_changes(active, debt, tenant_id, user_id, observed_at)
        attention = [
            item
            for item in active
            if item.significance in {Significance.HIGH, Significance.CRITICAL}
        ]
        brief = DailyProductBrief(
            generated_at=observed_at,
            things_needing_attention=[
                item.derived_signal or item.observation for item in attention
            ],
            recent_wins=[
                item.observation for item in active if item.signal_type == SignalType.STRENGTH
            ],
            upcoming_decisions=[f"{item.title}: {item.next_review_action}" for item in debt],
            material_changes=[item for item in changes if item.material],
            evidence_ids=sorted(
                {evidence for item in active for evidence in item.evidence_ids}
                | {evidence for item in debt for evidence in item.evidence_ids}
            ),
            evidence_limitations=[
                "This brief includes only ProductOS records and connected accessible sources.",
                (
                    "No change means no new documented state; it does not prove nothing "
                    "changed elsewhere."
                ),
            ],
        )
        artifact = await self._artifact(
            WorkflowName.DAILY_PRODUCT_BRIEF,
            "Daily Product Brief",
            brief.model_dump(mode="json"),
            tenant_id,
            user_id,
        )
        return brief, artifact, changes

    async def scan(
        self,
        tenant_id: UUID,
        user_id: UUID,
        now: datetime | None = None,
        kind: ScheduleKind | None = None,
    ) -> tuple[list[ChangeEvent], list[ProactiveNotification], list[str]]:
        observed_at = self._aware(now or datetime.now(UTC))
        signals, _ = await self._management.refresh_intelligence(tenant_id, user_id)
        debt = await self._management.decision_debt(user_id)
        changes = await self._detect_changes(
            [item for item in signals if item.status == SignalStatus.ACTIVE],
            debt,
            tenant_id,
            user_id,
            observed_at,
            kind,
        )
        return await self._notify(changes, tenant_id, user_id, observed_at)

    async def notifications(self, tenant_id: UUID, user_id: UUID) -> list[ProactiveNotification]:
        return await self._repository.list_notifications(tenant_id, user_id)

    async def patch_notification(
        self,
        notification_id: UUID,
        patch: NotificationPatch,
        tenant_id: UUID,
        user_id: UUID,
    ) -> ProactiveNotification | None:
        item = await self._repository.get_notification(notification_id, tenant_id, user_id)
        if not item:
            return None
        item.status = patch.status
        item.read_at = datetime.now(UTC) if patch.status == NotificationStatus.READ else None
        return await self._repository.update_notification(item)

    async def home(self, tenant_id: UUID, user_id: UUID) -> dict[str, object]:
        signals, _ = await self._management.refresh_intelligence(tenant_id, user_id)
        active = [item for item in signals if item.status == SignalStatus.ACTIVE]
        debt = await self._management.decision_debt(user_id)
        notifications = await self.notifications(tenant_id, user_id)
        artifacts = await self._artifacts.list(tenant_id, user_id, ArtifactType.PRODUCT_BRIEF)
        return {
            "things_needing_attention": [
                item
                for item in active
                if item.significance in {Significance.HIGH, Significance.CRITICAL}
            ],
            "recent_wins": [item for item in active if item.signal_type == SignalType.STRENGTH],
            "upcoming_decisions": debt,
            "notifications": [
                item for item in notifications if item.status == NotificationStatus.UNREAD
            ],
            "latest_brief": artifacts[0] if artifacts else None,
            "limitations": [
                "Home reflects documented ProductOS evidence, not all company activity."
            ],
        }

    async def _run_kind(
        self,
        kind: ScheduleKind,
        tenant_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> tuple[list[UUID], list[UUID], list[str]]:
        preferences = await self.preferences(tenant_id, user_id)
        if kind == ScheduleKind.DAILY_PRODUCT_BRIEF:
            if not preferences.daily_brief_enabled:
                return [], [], ["daily brief disabled by user preference"]
            _, artifact, changes = await self.daily_brief(tenant_id, user_id, now)
            _, notifications, reasons = await self._notify(
                changes, tenant_id, user_id, now, artifact.id
            )
            return [artifact.id], [item.id for item in notifications], reasons
        if kind == ScheduleKind.WEEKLY_LEADERSHIP_BRIEF:
            if not preferences.weekly_brief_enabled:
                return [], [], ["weekly brief disabled by user preference"]
            _, artifact = await self._management.weekly_review(
                tenant_id,
                user_id,
                now - timedelta(days=7),
                WorkflowName.WEEKLY_PRODUCT_LEADERSHIP_BRIEF,
                "Weekly Product Leadership Brief",
            )
            changes, notifications, reasons = await self.scan(tenant_id, user_id, now)
            if not changes:
                reasons.append(
                    "weekly brief created without a notification: no novel material change"
                )
            return [artifact.id], [item.id for item in notifications], reasons
        changes, notifications, reasons = await self.scan(tenant_id, user_id, now, kind)
        return [], [item.id for item in notifications], reasons

    async def _detect_changes(
        self,
        signals: list[ManagementSignal],
        debt: list[Any],
        tenant_id: UUID,
        user_id: UUID,
        now: datetime,
        kind: ScheduleKind | None = None,
    ) -> list[ChangeEvent]:
        candidates: list[tuple[str, str, dict[str, object], ChangeEvent]] = []
        selected_signals = [] if kind == ScheduleKind.DECISION_REVIEW_SCAN else signals
        selected_debt = [] if kind == ScheduleKind.RISK_SCAN else debt
        for signal in selected_signals:
            stable_id = f"{signal.signal_type}:{signal.subject_type}:{signal.subject_id}"
            state = {
                "observation": signal.observation,
                "evidence_ids": sorted(signal.evidence_ids),
                "confidence": signal.confidence,
                "significance": signal.significance,
                "recommendation": signal.recommendation,
            }
            candidates.append(
                (
                    "management_signal",
                    stable_id,
                    state,
                    ChangeEvent(
                        subject_type=signal.subject_type,
                        subject_id=signal.subject_id,
                        change_type=str(signal.signal_type),
                        summary=signal.derived_signal or signal.observation,
                        evidence_ids=signal.evidence_ids,
                        confidence=signal.confidence,
                        level=signal.significance,
                        actionable=bool(signal.recommendation),
                        material=signal.significance in {Significance.HIGH, Significance.CRITICAL},
                        limitations=signal.limitations,
                        recommended_next_step=signal.recommendation,
                    ),
                )
            )
        for item in selected_debt:
            stable_id = f"{item.decision_id}:{item.debt_type}"
            state = {
                "debt_type": item.debt_type,
                "severity": item.severity,
                "evidence_ids": sorted(item.evidence_ids),
            }
            candidates.append(
                (
                    "decision_debt",
                    stable_id,
                    state,
                    ChangeEvent(
                        subject_type="decision",
                        subject_id=str(item.decision_id),
                        change_type=item.debt_type,
                        summary=f"Decision review needed: {item.title}",
                        evidence_ids=item.evidence_ids,
                        confidence=ConfidenceLevel.HIGH,
                        level=item.severity,
                        actionable=True,
                        material=item.severity in {Significance.HIGH, Significance.CRITICAL},
                        limitations=[
                            item.limitation
                            or "Reminder is based on the documented decision record."
                        ],
                        recommended_next_step=item.next_review_action,
                    ),
                )
            )
        changes = []
        for subject_type, subject_id, state, event in candidates:
            fingerprint = self._fingerprint(state)
            previous = await self._repository.get_snapshot(
                tenant_id, user_id, subject_type, subject_id
            )
            if not previous or previous.fingerprint != fingerprint:
                changes.append(event)
            await self._repository.save_snapshot(
                ChangeSnapshot(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    fingerprint=fingerprint,
                    state=state,
                    observed_at=now,
                )
            )
        return changes

    async def _notify(
        self,
        changes: list[ChangeEvent],
        tenant_id: UUID,
        user_id: UUID,
        now: datetime,
        artifact_id: UUID | None = None,
    ) -> tuple[list[ChangeEvent], list[ProactiveNotification], list[str]]:
        preferences = await self.preferences(tenant_id, user_id)
        created: list[ProactiveNotification] = []
        suppressed: list[str] = []
        if not preferences.enabled or not preferences.in_app_enabled:
            return changes, created, ["notifications disabled by user preference"]
        if self._in_quiet_hours(preferences, now):
            return changes, created, ["notification suppressed during quiet hours"]
        zone = ZoneInfo(preferences.timezone)
        local_day = now.astimezone(zone).date()
        today_count = len(
            [
                item
                for item in await self.notifications(tenant_id, user_id)
                if self._aware(item.created_at).astimezone(zone).date() == local_day
            ]
        )
        for change in changes:
            if change.subject_type == "decision" and not preferences.decision_reminders_enabled:
                suppressed.append(f"{change.change_type}: decision reminders disabled")
                continue
            if change.subject_type != "decision" and not preferences.risk_alerts_enabled:
                suppressed.append(f"{change.change_type}: risk alerts disabled")
                continue
            if not change.material:
                suppressed.append(f"{change.change_type}: not material")
                continue
            if change.confidence not in {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM}:
                suppressed.append(f"{change.change_type}: insufficient confidence")
                continue
            if not change.actionable or not change.recommended_next_step:
                suppressed.append(f"{change.change_type}: not actionable")
                continue
            if LEVEL_ORDER[change.level] < LEVEL_ORDER[preferences.minimum_level]:
                suppressed.append(f"{change.change_type}: below preferred severity")
                continue
            if today_count + len(created) >= preferences.maximum_per_day:
                suppressed.append(f"{change.change_type}: daily notification limit reached")
                continue
            dedupe_key = self._fingerprint(
                {
                    "subject_type": change.subject_type,
                    "subject_id": change.subject_id,
                    "change_type": change.change_type,
                    "summary": change.summary,
                    "evidence_ids": sorted(change.evidence_ids),
                }
            )
            notification = ProactiveNotification(
                tenant_id=tenant_id,
                user_id=user_id,
                dedupe_key=dedupe_key,
                category=change.change_type,
                title=change.summary,
                body="A novel, material, actionable change met your notification threshold.",
                level=change.level,
                evidence_ids=change.evidence_ids,
                confidence=change.confidence,
                limitations=change.limitations,
                recommended_next_step=change.recommended_next_step,
                related_artifact_id=artifact_id,
                created_at=now,
            )
            stored = await self._repository.create_notification(notification)
            if stored:
                created.append(stored)
            else:
                suppressed.append(f"{change.change_type}: duplicate notification")
        return changes, created, suppressed

    async def _artifact(
        self,
        workflow: WorkflowName,
        title: str,
        data: dict[str, Any],
        tenant_id: UUID,
        user_id: UUID,
    ) -> Artifact:
        state = await self._start_run(tenant_id, user_id, title, f"{workflow}.v1")
        await self._trace(
            state.run_id,
            TraceEventType.WORKFLOW_SELECTED,
            workflow=workflow,
            version="1.0.0",
        )
        rendered = self._render(title, data)
        artifact = Artifact(
            tenant_id=tenant_id,
            user_id=user_id,
            artifact_type=ArtifactType.PRODUCT_BRIEF,
            title=title,
            structured_data=data,
            rendered_content=rendered,
            workflow_id=state.session_id,
            workflow_name=workflow,
            workflow_version="1.0.0",
            agent_run_id=state.run_id,
            source_ids=list(data.get("evidence_ids", [])),
            model_metadata={"generator": "deterministic-proactive"},
        )
        await self._artifacts.create(artifact)
        await self._trace(
            state.run_id,
            TraceEventType.ARTIFACT_CREATED,
            artifact_id=str(artifact.id),
            artifact_type=artifact.artifact_type,
        )
        await self._finish_run(state, rendered)
        return artifact

    async def _start_run(
        self, tenant_id: UUID, user_id: UUID, request: str, prompt_version: str
    ) -> AgentState:
        state = AgentState(
            user_id=user_id,
            tenant_id=tenant_id,
            request=request,
            status=RunStatus.RUNNING,
            mode="proactive",
        )
        await self._runs.start(
            state,
            prompt_version,
            "deterministic-proactive",
            self._settings.runtime_version,
            self._settings.constitution_version,
            self._settings.memory_policy_version,
            self._settings.retrieval_policy_version,
            self._settings.tool_contract_version,
            self._settings.mcp_adapter_version,
            "1.0.0",
            {"proactive": "deterministic.v1"},
        )
        await self._trace(state.run_id, TraceEventType.RUN_STARTED, mode="proactive")
        return state

    async def _finish_run(self, state: AgentState, response: object) -> None:
        state.status = RunStatus.COMPLETED
        state.response = (
            json.dumps(response, default=str) if not isinstance(response, str) else response
        )
        await self._trace(state.run_id, TraceEventType.RUN_COMPLETED, status=state.status)
        await self._runs.complete(state)

    @staticmethod
    def _render(title: str, data: dict[str, Any]) -> str:
        lines = [f"# {title}", "", "Evidence-backed · In-app draft", ""]
        for key, value in data.items():
            lines.extend([f"## {key.replace('_', ' ').title()}", ""])
            if isinstance(value, list):
                lines.extend([f"- {item}" for item in value] or ["- No new documented item."])
            else:
                lines.append(str(value))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _fingerprint(value: dict[str, object]) -> str:
        encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _validate_timezone(value: str) -> None:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc

    @staticmethod
    def _next_run(schedule: ProactiveSchedule, now: datetime) -> datetime:
        zone = ZoneInfo(schedule.timezone)
        local_now = now.astimezone(zone)
        candidate = local_now.replace(
            hour=schedule.local_time.hour,
            minute=schedule.local_time.minute,
            second=schedule.local_time.second,
            microsecond=0,
        )
        if schedule.frequency == ScheduleFrequency.DAILY:
            if candidate <= local_now:
                candidate += timedelta(days=1)
        else:
            days = (int(schedule.weekday or 0) - local_now.weekday()) % 7
            candidate += timedelta(days=days)
            if candidate <= local_now:
                candidate += timedelta(days=7)
        return candidate.astimezone(UTC)

    @staticmethod
    def _in_quiet_hours(preferences: NotificationPreferences, now: datetime) -> bool:
        if preferences.quiet_hours_start is None or preferences.quiet_hours_end is None:
            return False
        local_time = now.astimezone(ZoneInfo(preferences.timezone)).time().replace(tzinfo=None)
        start = preferences.quiet_hours_start
        end = preferences.quiet_hours_end
        if start <= end:
            return start <= local_time < end
        return local_time >= start or local_time < end

    async def _trace(self, run_id: UUID, event_type: TraceEventType, **attributes: Any) -> None:
        await self._traces.append(
            TraceEvent(run_id=run_id, event_type=event_type, attributes=attributes)
        )
