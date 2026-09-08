"""Chaplain / Purpose-pathway dashboard aggregate service.

Net-new (2026-09-07, explicit user go-ahead - not DOCX-sourced). The
Chaplain dashboard mock showed a caseload summary (opted-in count, active
reflections, consults today, first-time engagements), an anonymized-code
caseload table, and an opt-in confirmation audit trail. None of these
existed as a real aggregate anywhere - the underlying records
(`TeamAssignment`, `Reflection`, `SpecialistSession`) were already real,
just never rolled up for this view. Every airman here is shown only by
`anonymized_code` - never a real name or rank, matching the mock's own
"No rank, no PII" caseload note.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.core.anonymize import anonymized_code
from app.models.reflection import Reflection
from app.models.specialist_note import SpecialistNote
from app.models.specialist_session import SpecialistSession
from app.models.team_assignment import STATUS_ENABLED, TeamAssignment
from app.models.user import User

CHAPLAIN_PATHWAY_KEY = "Chaplain"
STATUS_LABELS = {"enabled": "Opted In", "disabled": "Consent Withdrawn", "locked_on": "Opted In"}
OPT_IN_METHOD_LABELS = {
    "app_self_service": "App self-service",
    "secure_form_signed": "Secure form - signed",
    "in_person_verbal": "In-person - verbal confirmation",
    "casual_contact_on_request": "Casual contact - on request",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChaplainDashboardService:
    """Real aggregates for the Chaplain / Purpose pathway dashboard."""

    async def _enabled_assignments(self, chaplain: User) -> list[TeamAssignment]:
        return await TeamAssignment.find(
            TeamAssignment.pathway_key == CHAPLAIN_PATHWAY_KEY,
            TeamAssignment.provider_user_id == chaplain.id,
            TeamAssignment.status == STATUS_ENABLED,
        ).to_list()

    async def get_caseload(self, chaplain: User) -> dict[str, Any]:
        """Real opted-in caseload - anonymized codes only, no name/rank."""
        assignments = await self._enabled_assignments(chaplain)
        if not assignments:
            return {"caseload": []}

        user_ids = [a.user_id for a in assignments]
        reflections, notes, sessions = await self._last_contact_sources(chaplain, user_ids)

        rows = []
        for assignment in assignments:
            last_reflection = reflections.get(assignment.user_id)
            last_note = notes.get(assignment.user_id)
            last_session = sessions.get(assignment.user_id)
            candidates = [
                ("Reflection", last_reflection) if last_reflection else None,
                ("Consult", last_note) if last_note else None,
                ("Consult", last_session) if last_session else None,
            ]
            candidates = [c for c in candidates if c is not None]
            last_contact = max(candidates, key=lambda c: c[1]) if candidates else None
            has_any_contact = last_contact is not None
            is_new = (_utc_now() - assignment.created_at).days <= 7 and not has_any_contact

            rows.append(
                {
                    "user_id": str(assignment.user_id),
                    "airman_code": anonymized_code(assignment.user_id),
                    "is_new": is_new,
                    "opt_in_date": assignment.created_at.date().isoformat(),
                    "reflection_cadence": assignment.reflection_cadence,
                    "last_contact_at": last_contact[1].isoformat() if last_contact else None,
                    "last_contact_type": last_contact[0] if last_contact else None,
                    "suggested_action": "welcome" if is_new else "message",
                }
            )
        rows.sort(key=lambda r: r["opt_in_date"], reverse=True)
        return {"caseload": rows}

    async def _last_contact_sources(
        self, chaplain: User, user_ids: list[Any]
    ) -> tuple[dict[Any, datetime], dict[Any, datetime], dict[Any, datetime]]:
        reflections = await Reflection.find({"user_id": {"$in": user_ids}}).to_list()
        notes = await SpecialistNote.find({"user_id": {"$in": user_ids}, "specialist_id": chaplain.id}).to_list()
        sessions = await SpecialistSession.find(
            {"attendee_user_ids": {"$in": user_ids}, "provider_id": chaplain.id}
        ).to_list()

        last_reflection: dict[Any, datetime] = {}
        for r in reflections:
            if r.user_id not in last_reflection or r.created_at > last_reflection[r.user_id]:
                last_reflection[r.user_id] = r.created_at

        last_note: dict[Any, datetime] = {}
        for n in notes:
            if n.user_id not in last_note or n.created_at > last_note[n.user_id]:
                last_note[n.user_id] = n.created_at

        last_session: dict[Any, datetime] = {}
        for s in sessions:
            session_dt = datetime.combine(s.session_date, datetime.min.time(), tzinfo=timezone.utc)
            for uid in s.attendee_user_ids:
                if uid not in last_session or session_dt > last_session[uid]:
                    last_session[uid] = session_dt

        return last_reflection, last_note, last_session

    async def get_dashboard_summary(self, chaplain: User) -> dict[str, Any]:
        """Real opted-in/active-reflection/consult/first-time counts for today's caseload summary."""
        assignments = await self._enabled_assignments(chaplain)
        user_ids = [a.user_id for a in assignments]
        now = _utc_now()
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        opted_in_count = len(assignments)
        opted_in_this_month = sum(1 for a in assignments if a.created_at >= month_start)

        active_reflections_count = 0
        if user_ids:
            active_reflections_count = await Reflection.find(
                {"user_id": {"$in": user_ids}, "created_at": {"$gte": month_start}}
            ).count()

        first_time_count = sum(1 for a in assignments if (now - a.created_at).days <= 7)

        today = date.today()
        consults_today = await SpecialistSession.find(
            SpecialistSession.provider_id == chaplain.id, SpecialistSession.session_date == today
        ).to_list()

        return {
            "opted_in_count": opted_in_count,
            "opted_in_count_delta_this_month": opted_in_this_month,
            "active_reflections_count": active_reflections_count,
            "consults_today_count": len(consults_today),
            "first_time_engagement_count": first_time_count,
        }

    async def get_todays_pastoral_care(self, chaplain: User) -> dict[str, Any]:
        """Real "Pastoral care today" schedule - each session's real planned time/
        duration/topic, plus a real-derived attendee category (first-time/returning/
        brief) instead of the raw scheduling status. Category is derived, not
        fabricated: "first_time" if the attendee has no earlier session with this
        chaplain, "brief" if the planned length is <=30 minutes, else "returning".
        """
        today = date.today()
        sessions = await SpecialistSession.find(
            SpecialistSession.provider_id == chaplain.id, SpecialistSession.session_date == today
        ).to_list()
        sessions.sort(key=lambda s: s.start_time)
        if not sessions:
            return {"sessions": []}

        all_attendee_ids = {uid for s in sessions for uid in s.attendee_user_ids}
        prior_sessions = await SpecialistSession.find(
            {
                "provider_id": chaplain.id,
                "attendee_user_ids": {"$in": list(all_attendee_ids)},
                "session_date": {"$lt": today},
            }
        ).to_list()
        attendees_with_history: set[Any] = set()
        for s in prior_sessions:
            attendees_with_history.update(s.attendee_user_ids)

        rows = []
        for s in sessions:
            attendee_id = s.attendee_user_ids[0] if s.attendee_user_ids else None
            if attendee_id is None:
                category = "group"
            elif attendee_id not in attendees_with_history:
                category = "first_time"
            elif s.planned_duration_minutes is not None and s.planned_duration_minutes <= 30:
                category = "brief"
            else:
                category = "returning"

            rows.append(
                {
                    "id": str(s.id),
                    "start_time": s.start_time,
                    "planned_duration_minutes": s.planned_duration_minutes,
                    "airman_code": anonymized_code(attendee_id) if attendee_id else None,
                    "group_label": s.group_label,
                    "topic": s.topic,
                    "category": category,
                    "status": s.status,
                }
            )
        return {"sessions": rows}

    async def get_opt_in_audit(self, chaplain: User) -> dict[str, Any]:
        """Real opt-in/opt-out audit trail - every assignment record regardless of
        current status (a withdrawn consent still shows its own row, per the mock's
        own "Consent Withdrawn" state).
        """
        assignments = await TeamAssignment.find(
            TeamAssignment.pathway_key == CHAPLAIN_PATHWAY_KEY,
            TeamAssignment.provider_user_id == chaplain.id,
        ).to_list()
        assignments.sort(key=lambda a: a.updated_at, reverse=True)

        witness_ids = [a.witnessed_by_id for a in assignments if a.witnessed_by_id]
        witnesses = await User.find({"_id": {"$in": witness_ids}}).to_list() if witness_ids else []
        witnesses_by_id = {w.id: w for w in witnesses}

        rows = []
        for a in assignments:
            witness = witnesses_by_id.get(a.witnessed_by_id) if a.witnessed_by_id else None
            rows.append(
                {
                    "user_id": str(a.user_id),
                    "airman_code": anonymized_code(a.user_id),
                    "status": a.status,
                    "status_label": STATUS_LABELS.get(a.status, a.status),
                    # Real, but only a proxy - the record's last-modified time,
                    # not a separate immutable per-event log (no such log
                    # exists for opt-in/opt-out transitions).
                    "recorded_at": a.updated_at.isoformat(),
                    "method": a.opt_in_method,
                    "method_label": OPT_IN_METHOD_LABELS.get(a.opt_in_method, a.opt_in_method) if a.opt_in_method else None,
                    "witness_name": witness.full_name if witness else None,
                }
            )
        return {"entries": rows}
