"""Mental Performance dashboard aggregate service.

Net-new (2026-09-08, explicit user go-ahead - not DOCX-sourced). Same
pattern as `chaplain_service.py`: the MP dashboard mock showed a caseload
summary (active caseload with an individual/group split, referrals this
week by source, sessions today, follow-ups due), an anonymized-code
caseload queue, and a k-gated cohort driver panel (already real via
`get_mental_driver_scores`). Every airman here is shown only by
`anonymized_code`.

"Referrals this week by source" is a real, not-fabricated derivation:
- self: the operator's own `SupportRequest` (always self-initiated - no
  staff-on-behalf-of submission path exists anywhere in this backend).
- scs / pt_im: a `Recommendation` routed to Mental Performance
  (`specialist_route`) whose `assigned_provider_role` names the referring
  role - real fields, just never rolled up into a "referral source" count
  before.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.anonymize import anonymized_code
from app.core.roles import ROLE_MENTAL_PERFORMANCE, ROLE_PTIM, ROLE_SCS
from app.models.recommendation import Recommendation
from app.models.specialist_note import SpecialistNote
from app.models.specialist_session import SpecialistSession
from app.models.support_request import SupportRequest
from app.models.team_assignment import STATUS_ENABLED, TeamAssignment
from app.models.user import User

MP_PATHWAY_KEY = ROLE_MENTAL_PERFORMANCE


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


class MpDashboardService:
    """Real aggregates for the Mental Performance dashboard."""

    async def _enabled_assignments(self, mp: User) -> list[TeamAssignment]:
        return await TeamAssignment.find(
            TeamAssignment.pathway_key == MP_PATHWAY_KEY,
            TeamAssignment.provider_user_id == mp.id,
            TeamAssignment.status == STATUS_ENABLED,
        ).to_list()

    async def get_dashboard_summary(self, mp: User) -> dict[str, Any]:
        assignments = await self._enabled_assignments(mp)
        user_ids = [a.user_id for a in assignments]
        today = date.today()
        week_start = _week_start(today)
        week_start_dt = datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc)

        active_caseload_count = len(assignments)

        individual_count = 0
        group_count = 0
        if user_ids:
            sessions = await SpecialistSession.find({"provider_id": mp.id, "attendee_user_ids": {"$in": user_ids}}).to_list()
            latest_type_by_user: dict[Any, tuple[date, str]] = {}
            for s in sessions:
                for uid in s.attendee_user_ids:
                    if uid not in user_ids:
                        continue
                    current = latest_type_by_user.get(uid)
                    if current is None or s.session_date > current[0]:
                        latest_type_by_user[uid] = (s.session_date, s.session_type)
            for _, session_type in latest_type_by_user.values():
                if session_type == "group":
                    group_count += 1
                else:
                    individual_count += 1

        self_referrals = 0
        scs_referrals = 0
        pt_im_referrals = 0
        if user_ids:
            requests_this_week = await SupportRequest.find(
                {"user_id": {"$in": user_ids}, "pathway_key": MP_PATHWAY_KEY, "created_at": {"$gte": week_start_dt}}
            ).to_list()
            self_referrals = len(requests_this_week)

            recs_this_week = await Recommendation.find(
                {
                    "user_id": {"$in": user_ids},
                    "specialist_route": MP_PATHWAY_KEY,
                    "assigned_provider_role": {"$in": [ROLE_SCS, ROLE_PTIM]},
                    "created_at": {"$gte": week_start_dt},
                }
            ).to_list()
            scs_referrals = sum(1 for r in recs_this_week if r.assigned_provider_role == ROLE_SCS)
            pt_im_referrals = sum(1 for r in recs_this_week if r.assigned_provider_role == ROLE_PTIM)

        sessions_today = await SpecialistSession.find(
            SpecialistSession.provider_id == mp.id, SpecialistSession.session_date == today
        ).to_list()

        follow_ups_due_today = 0
        follow_ups_due_this_week = 0
        if user_ids:
            week_end = week_start + timedelta(days=6)
            due_notes = await SpecialistNote.find(
                {
                    "user_id": {"$in": user_ids},
                    "specialist_id": mp.id,
                    "follow_up_needed": True,
                    "status": "open",
                    "follow_up_due_date": {"$ne": None},
                }
            ).to_list()
            for note in due_notes:
                if note.follow_up_due_date == today:
                    follow_ups_due_today += 1
                if week_start <= note.follow_up_due_date <= week_end:
                    follow_ups_due_this_week += 1

        return {
            "active_caseload_count": active_caseload_count,
            "individual_count": individual_count,
            "group_count": group_count,
            "referrals_this_week_count": self_referrals + scs_referrals + pt_im_referrals,
            "self_referrals_this_week": self_referrals,
            "scs_referrals_this_week": scs_referrals,
            "pt_im_referrals_this_week": pt_im_referrals,
            "sessions_today_count": len(sessions_today),
            "next_session_time": min((s.start_time for s in sessions_today), default=None),
            "next_session_airman_code": (
                anonymized_code(sessions_today[0].attendee_user_ids[0])
                if sessions_today and sessions_today[0].attendee_user_ids
                else None
            ),
            "follow_ups_due_today_count": follow_ups_due_today,
            "follow_ups_due_this_week_count": follow_ups_due_this_week,
        }

    async def get_caseload(self, mp: User) -> dict[str, Any]:
        assignments = await self._enabled_assignments(mp)
        if not assignments:
            return {"caseload": []}
        user_ids = [a.user_id for a in assignments]
        today = date.today()

        requests = await SupportRequest.find(
            {"user_id": {"$in": user_ids}, "pathway_key": MP_PATHWAY_KEY}
        ).to_list()
        latest_request_by_user: dict[Any, SupportRequest] = {}
        for r in requests:
            current = latest_request_by_user.get(r.user_id)
            if current is None or r.created_at > current.created_at:
                latest_request_by_user[r.user_id] = r

        sessions = await SpecialistSession.find(
            {"provider_id": mp.id, "attendee_user_ids": {"$in": user_ids}}
        ).to_list()
        last_session_by_user: dict[Any, date] = {}
        next_session_by_user: dict[Any, date] = {}
        for s in sessions:
            for uid in s.attendee_user_ids:
                if uid not in user_ids:
                    continue
                if s.session_date <= today:
                    if uid not in last_session_by_user or s.session_date > last_session_by_user[uid]:
                        last_session_by_user[uid] = s.session_date
                else:
                    if uid not in next_session_by_user or s.session_date < next_session_by_user[uid]:
                        next_session_by_user[uid] = s.session_date

        notes = await SpecialistNote.find(
            {"user_id": {"$in": user_ids}, "specialist_id": mp.id, "follow_up_needed": True, "status": "open"}
        ).to_list()
        follow_up_users = {n.user_id for n in notes}

        rows = []
        for assignment in assignments:
            uid = assignment.user_id
            request = latest_request_by_user.get(uid)
            has_contact = uid in last_session_by_user or uid in latest_request_by_user
            is_new = (_utc_now() - assignment.created_at).days <= 7 and not has_contact

            if is_new:
                queue_status = "new"
            elif uid in follow_up_users:
                queue_status = "follow_up"
            elif uid in next_session_by_user:
                queue_status = "scheduled"
            else:
                queue_status = "active"

            rows.append(
                {
                    "user_id": str(uid),
                    "airman_code": anonymized_code(uid),
                    "referral_reason": request.reason_category if request else None,
                    "last_session_date": last_session_by_user.get(uid).isoformat() if uid in last_session_by_user else None,
                    "next_session_date": next_session_by_user.get(uid).isoformat() if uid in next_session_by_user else None,
                    "queue_status": queue_status,
                }
            )
        rows.sort(key=lambda r: r["next_session_date"] or "9999-99-99")
        return {"caseload": rows}
