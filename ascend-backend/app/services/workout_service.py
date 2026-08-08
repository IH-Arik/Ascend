"""Workout/activity logging service (DOCX section 9).

`recent_adherence_label`/`current_streak_weeks` are computed from real
logged sessions only - the DOCX explicitly warns against overbuilding a
fitness programming platform here, so there is no "planned workout"
schedule to compare against ("5 of 6 planned workouts" is not derivable);
this instead reports how many of the last 6 *logged* sessions were marked
completed, and how many consecutive weeks (ending this week) have at least
one logged session.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.support_pathways import get_support_pathway
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.schemas.workout import LIMITATION_TERMS, WorkoutLogCreate
from app.services.notification_service import NotificationService

DEFAULT_SUMMARY_DAYS = 30
RECENT_SESSIONS_FOR_ADHERENCE = 6


class WorkoutService:
    """Log and summarize workout/activity sessions."""

    def __init__(self) -> None:
        self.notification_service = NotificationService()

    async def log_workout(self, user: User, payload: WorkoutLogCreate) -> dict[str, Any]:
        """Persist a single workout/activity log entry."""
        reported_limitation = self._scan_for_limitation(payload.notes)
        record = WorkoutLog(
            user_id=user.id,
            activity_date=payload.activity_date,
            activity_type=payload.activity_type,
            custom_title=payload.custom_title,
            duration_minutes=payload.duration_minutes,
            intensity=payload.intensity,
            completion_status=payload.completion_status,
            notes=payload.notes,
            reported_limitation=reported_limitation,
            session_rating=payload.session_rating,
        )
        await record.insert()

        if reported_limitation:
            await self._notify_assigned_scs(user, record)

        return self._serialize(record)

    async def list_for_user(self, user: User, days: int = DEFAULT_SUMMARY_DAYS) -> dict[str, Any]:
        """Return recent workout logs for a user, newest first."""
        cutoff = date.today() - timedelta(days=days)
        records = await WorkoutLog.find(
            WorkoutLog.user_id == user.id, WorkoutLog.activity_date >= cutoff
        ).to_list()
        records.sort(key=lambda item: item.activity_date, reverse=True)
        return {"workouts": [self._serialize(item) for item in records]}

    async def get_summary(self, user: User, days: int = DEFAULT_SUMMARY_DAYS) -> dict[str, Any]:
        """Return an aggregate workout summary over the last N days."""
        cutoff = date.today() - timedelta(days=days)
        records = await WorkoutLog.find(
            WorkoutLog.user_id == user.id, WorkoutLog.activity_date >= cutoff
        ).to_list()

        by_type: dict[str, int] = {}
        for record in records:
            by_type[record.activity_type] = by_type.get(record.activity_type, 0) + 1

        all_records = await WorkoutLog.find(WorkoutLog.user_id == user.id).to_list()
        all_records.sort(key=lambda item: (item.activity_date, item.created_at), reverse=True)
        recent = all_records[:RECENT_SESSIONS_FOR_ADHERENCE]
        recent_completed = sum(1 for r in recent if r.completion_status == "completed")

        return {
            "range_days": days,
            "total_sessions": len(records),
            "completed_sessions": sum(1 for r in records if r.completion_status == "completed"),
            "missed_sessions": sum(1 for r in records if r.completion_status == "missed"),
            "by_activity_type": by_type,
            "total_duration_minutes": sum(r.duration_minutes for r in records),
            "recent_adherence_label": f"{recent_completed} of last {len(recent)} logged sessions completed",
            "current_streak_weeks": self._current_streak_weeks(all_records),
        }

    def _scan_for_limitation(self, notes: str | None) -> bool:
        """Return True if workout notes mention a pain/injury/limitation term."""
        if not notes:
            return False
        lowered = notes.lower()
        return any(term in lowered for term in LIMITATION_TERMS)

    async def _notify_assigned_scs(self, user: User, record: WorkoutLog) -> None:
        """Notify the user's assigned SCS that a workout note reported a limitation."""
        pathway = get_support_pathway("SCS")
        if pathway is None or pathway["role"] is None:
            return
        assignment = await TeamAssignment.find_one(
            TeamAssignment.user_id == user.id, TeamAssignment.pathway_key == "SCS"
        )
        if assignment is None or assignment.provider_user_id is None:
            return
        await self.notification_service.notify(
            assignment.provider_user_id,
            family="provider_follow_up_reminders",
            title=f"Limitation reported in a workout log ({user.full_name or user.email})",
            body=(record.notes or "")[:140],
            related_entity_type="workout_log",
            related_entity_id=str(record.id),
        )

    def _current_streak_weeks(self, records_desc: list[WorkoutLog]) -> int:
        """Return the number of consecutive weeks (ending this week) with >=1 logged session."""
        if not records_desc:
            return 0
        weeks_with_sessions = {r.activity_date.isocalendar()[:2] for r in records_desc}
        streak = 0
        cursor = date.today()
        while cursor.isocalendar()[:2] in weeks_with_sessions:
            streak += 1
            cursor -= timedelta(weeks=1)
        return streak

    def _serialize(self, record: WorkoutLog) -> dict[str, Any]:
        """Convert a stored workout log to a transport-safe dict."""
        return {
            "id": str(record.id),
            "activity_date": record.activity_date.isoformat(),
            "activity_type": record.activity_type,
            "custom_title": record.custom_title,
            "duration_minutes": record.duration_minutes,
            "intensity": record.intensity,
            "completion_status": record.completion_status,
            "notes": record.notes,
            "reported_limitation": record.reported_limitation,
            "session_rating": record.session_rating,
        }
