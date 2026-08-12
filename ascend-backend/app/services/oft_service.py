"""OFT (Operational Fitness Test) tracking service (DOCX section 8.2).

Scheduling and result recording are SCS/Admin actions (no automated
scheduler exists). Per-user status tracking, plus a real cross-user
monthly leadership metrics aggregate (`get_leadership_metrics_report`) -
it does not implement reconditioning plan assignment, which is separate
provider-facing work.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.cadence import phrase_relative_date
from app.core.notification_rules import OFT_DUE_REMINDERS
from app.core.roles import ROLE_AIRMAN, ROLE_LEADERSHIP
from app.models.oft_record import OFTRecord
from app.models.org_unit import OrgUnit
from app.models.user import User
from app.schemas.oft import OFTRecordResultRequest
from app.schemas.oft import OFTScheduleRequest
from app.services.notification_service import NotificationService
from app.services.role_admin_service import RoleAdminService

COMPLETED_STATUSES = {"current", "not_current", "exempt"}
DUE_SOON_DAYS = 7


class OFTService:
    """Track OFT scheduling, results, and status for users."""

    def __init__(self) -> None:
        self.notification_service = NotificationService()
        self.role_admin_service = RoleAdminService()

    async def remind_due_soon(self) -> int:
        """Send an "OFT coming up" reminder for every scheduled test within DUE_SOON_DAYS.

        Deduped per record (not per day) via a stable `related_entity_id`, so
        this is safe to call from a daily scheduled job without re-notifying.
        Returns the number of reminders actually sent.
        """
        today = date.today()
        cutoff = today + timedelta(days=DUE_SOON_DAYS)
        upcoming = await OFTRecord.find(
            OFTRecord.status == "scheduled",
            OFTRecord.test_date >= today,
            OFTRecord.test_date <= cutoff,
        ).to_list()

        sent = 0
        for record in upcoming:
            already_sent = await self.notification_service.exists_since(
                record.user_id,
                family=OFT_DUE_REMINDERS,
                related_entity_type="oft_due_soon",
                related_entity_id=str(record.id),
            )
            if already_sent:
                continue
            relative = phrase_relative_date(record.test_date, today)
            await self.notification_service.notify(
                record.user_id,
                family=OFT_DUE_REMINDERS,
                title="OFT coming up",
                body=f"Your OFT is scheduled {relative}.",
                related_entity_type="oft_due_soon",
                related_entity_id=str(record.id),
            )
            sent += 1
        return sent

    async def schedule(
        self,
        user: User,
        payload: OFTScheduleRequest,
        recorded_by: Any,
    ) -> dict[str, Any]:
        """Schedule an upcoming OFT test."""
        record = OFTRecord(
            user_id=user.id,
            test_date=payload.test_date,
            status="scheduled",
            notes=payload.notes,
            recorded_by=recorded_by,
        )
        await record.insert()
        relative = phrase_relative_date(payload.test_date, date.today())
        await self.notification_service.notify(
            user.id,
            family=OFT_DUE_REMINDERS,
            title="OFT scheduled",
            body=f"Your OFT is scheduled for {relative}.",
            related_entity_type="oft_record",
            related_entity_id=str(record.id),
        )
        return await self.get_status_for_user(user)

    async def record_result(
        self,
        user: User,
        payload: OFTRecordResultRequest,
        recorded_by: Any,
    ) -> dict[str, Any]:
        """Record a completed OFT test result."""
        record = OFTRecord(
            user_id=user.id,
            test_date=payload.test_date,
            status=payload.status,
            pass_fail=payload.pass_fail,
            items_passed=payload.items_passed,
            items_total=payload.items_total,
            entered_into_government_system=payload.entered_into_government_system,
            notes=payload.notes,
            recorded_by=recorded_by,
        )
        await record.insert()
        return await self.get_status_for_user(user)

    async def get_status_for_user(self, user: User) -> dict[str, Any]:
        """Return the current OFT status summary for a user."""
        records = await OFTRecord.find(OFTRecord.user_id == user.id).to_list()
        today = date.today()

        completed = sorted(
            (r for r in records if r.status in COMPLETED_STATUSES),
            key=lambda item: item.test_date,
            reverse=True,
        )
        upcoming = sorted(
            (r for r in records if r.status == "scheduled" and r.test_date >= today),
            key=lambda item: item.test_date,
        )
        latest = completed[0] if completed else None
        year_cutoff = today - timedelta(days=365)
        annual_test_count = sum(1 for r in completed if r.test_date >= year_cutoff)

        current_status = latest.status if latest else ("scheduled" if upcoming else "no_record")
        next_scheduled_date = upcoming[0].test_date if upcoming else None
        return {
            "current_status": current_status,
            "latest_pass_fail": latest.pass_fail if latest else None,
            "latest_test_date": latest.test_date.isoformat() if latest else None,
            "items_passed": latest.items_passed if latest else None,
            "items_total": latest.items_total if latest else None,
            "next_scheduled_date": next_scheduled_date.isoformat() if next_scheduled_date else None,
            "next_scheduled_relative": (
                f"in {(next_scheduled_date - today).days} days" if next_scheduled_date else None
            ),
            "annual_test_count": annual_test_count,
        }

    async def get_leadership_metrics_report(self, month: str | None = None) -> dict[str, Any]:
        """Real cross-user OFT aggregate for the monthly leadership metrics report.

        `month` (optional, "YYYY-MM") scopes pass/fail/status counts to
        records tested in that month; omitted, every record is included.
        The annual per-user test-count distribution always looks at the
        real rolling 365-day window (same definition as
        `get_status_for_user`'s `annual_test_count`), independent of the
        `month` filter, since "annual" is a fixed real lookback, not the
        report's display month.
        """
        all_records = await OFTRecord.find().to_list()
        records = all_records
        if month:
            year_str, month_str = month.split("-")
            year, month_num = int(year_str), int(month_str)
            records = [r for r in all_records if r.test_date.year == year and r.test_date.month == month_num]

        completed = [r for r in records if r.status in COMPLETED_STATUSES]
        status_counts = {"current": 0, "not_current": 0, "exempt": 0, "scheduled": 0}
        for record in records:
            if record.status in status_counts:
                status_counts[record.status] += 1

        pass_count = sum(1 for r in completed if r.pass_fail == "pass")
        fail_count = sum(1 for r in completed if r.pass_fail == "fail")

        items_passed_values = [r.items_passed for r in completed if r.items_passed is not None]
        items_total_values = [r.items_total for r in completed if r.items_total is not None]
        avg_items_passed = (
            round(sum(items_passed_values) / len(items_passed_values), 1) if items_passed_values else None
        )
        avg_items_total = round(sum(items_total_values) / len(items_total_values), 1) if items_total_values else None

        entered_count = sum(1 for r in completed if r.entered_into_government_system)
        government_entry_compliance_pct = (
            round(entered_count / len(completed) * 100, 1) if completed else None
        )

        today = date.today()
        year_cutoff = today - timedelta(days=365)
        per_user_annual_count: dict[str, int] = {}
        for record in all_records:
            if record.status in COMPLETED_STATUSES and record.test_date >= year_cutoff:
                key = str(record.user_id)
                per_user_annual_count[key] = per_user_annual_count.get(key, 0) + 1
        annual_test_count_distribution: dict[str, int] = {}
        for count in per_user_annual_count.values():
            bucket = str(count)
            annual_test_count_distribution[bucket] = annual_test_count_distribution.get(bucket, 0) + 1

        by_flight = await self.get_by_flight_metrics()

        return {
            "month": month,
            "status_counts": status_counts,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_rate_pct": round(pass_count / len(completed) * 100, 1) if completed else None,
            "avg_items_passed": avg_items_passed,
            "avg_items_total": avg_items_total,
            "government_entry_compliance_pct": government_entry_compliance_pct,
            "annual_test_count_distribution": annual_test_count_distribution,
            "by_flight": by_flight,
            "total_records_in_scope": len(records),
        }

    async def get_by_flight_metrics(self) -> dict[str, Any]:
        """Real per-flight OFT pass-rate breakdown, k-gated - reuses the exact real
        flight-cohort resolution/k-gating `LeadershipAggregateService` already uses.

        Not DOCX-sourced (a Figma Leadership "Reports" screen's "Quarterly OFT
        ... by-flight aggregate" template description triggered this).
        """
        scope_config = await self.role_admin_service.get_scope_config(ROLE_LEADERSHIP)
        cohort_k = scope_config["cohort_k"]
        flights = await OrgUnit.find(OrgUnit.unit_type == "flight").to_list()
        all_records = await OFTRecord.find().to_list()

        rows: list[dict[str, Any]] = []
        for flight in flights:
            members = await User.find(User.unit_id == str(flight.id)).to_list()
            if len(members) < cohort_k:
                continue
            member_ids = {m.id for m in members}
            flight_records = [r for r in all_records if r.user_id in member_ids and r.status in COMPLETED_STATUSES]

            pass_count = sum(1 for r in flight_records if r.pass_fail == "pass")
            fail_count = sum(1 for r in flight_records if r.pass_fail == "fail")
            completed = pass_count + fail_count

            rows.append(
                {
                    "flight_id": str(flight.id),
                    "flight_name": flight.name,
                    "cohort_size": len(members),
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                    "pass_rate_pct": round(pass_count / completed * 100, 1) if completed else None,
                }
            )

        rows.sort(key=lambda item: item["flight_name"])
        return {"min_cohort_size": cohort_k, "flights": rows}

    async def get_due_soon_count(self, days: int = 30) -> int:
        """Return the real count of Airmen whose annual OFT is due within `days`.

        Not DOCX-sourced (a Figma Leadership "Aggregate readiness" screen
        triggered this). "Due soon" is defined against the same real
        rolling-365-day annual cycle `get_status_for_user`'s
        `annual_test_count` already uses: a user's most recent completed
        test is due-soon if it's at least `365 - days` days old. `exempt`
        is a real permanent state, never "due". A user with zero completed
        tests ever also counts as due now, matching
        `get_status_for_user`'s existing `"no_record"` treatment.
        """
        today = date.today()
        due_cutoff = today - timedelta(days=365 - days)

        airmen = await User.find(User.role == ROLE_AIRMAN).to_list()
        all_records = await OFTRecord.find().to_list()
        records_by_user: dict[str, list[OFTRecord]] = {}
        for record in all_records:
            if record.status in COMPLETED_STATUSES:
                records_by_user.setdefault(str(record.user_id), []).append(record)

        due_soon_count = 0
        for airman in airmen:
            user_records = records_by_user.get(str(airman.id))
            if not user_records:
                due_soon_count += 1
                continue
            latest = max(user_records, key=lambda item: item.test_date)
            if latest.status == "exempt":
                continue
            if latest.test_date <= due_cutoff:
                due_soon_count += 1
        return due_soon_count
