"""Provider coverage-hours log service - feeds the PRS/QCP Support Report."""

from __future__ import annotations

from datetime import date
from typing import Any

from beanie import PydanticObjectId

from app.core.roles import ROLE_PTIM, ROLE_SCS
from app.models.coverage_log import CoverageLog
from app.models.org_unit import OrgUnit
from app.models.reconditioning_plan import ReconditioningPlan
from app.models.user import User
from app.schemas.coverage_log import CoverageLogCreate
from app.services.role_admin_service import RoleAdminService

PRS_EVIDENCE_ROLES = (ROLE_SCS, ROLE_PTIM)


def _as_object_id(provider_id: Any) -> PydanticObjectId:
    """Coerce a route-supplied string id to a real `PydanticObjectId`.

    Bug fix (found live-verifying Part LL, pre-existing/not introduced this
    pass): `CoverageLog.provider_id` is stored as a real `PydanticObjectId`,
    but `list_coverage_logs` (`app/modules/admin/routes.py`) passed the raw
    path-param string straight through to `CoverageLog.provider_id ==
    provider_id`. Beanie's `==` does not coerce the RHS to the field's
    type, so MongoDB compared a string against a BSON ObjectId and silently
    matched nothing - `GET /admin/coverage-logs/{provider_id}` always
    returned an empty log, for every provider, since this endpoint existed.
    """
    return provider_id if isinstance(provider_id, PydanticObjectId) else PydanticObjectId(provider_id)


class CoverageService:
    """Log and list provider coverage-hours entries."""

    def __init__(self) -> None:
        self.role_admin_service = RoleAdminService()

    async def create(self, logged_by: Any, payload: CoverageLogCreate) -> dict[str, Any]:
        """Log a block of coverage hours for a provider."""
        record = CoverageLog(
            provider_id=payload.provider_id,
            role=payload.role,
            hours=payload.hours,
            coverage_date=payload.coverage_date,
            is_weekend_rsd=payload.is_weekend_rsd,
            notes=payload.notes,
            scheduled_hours=payload.scheduled_hours,
            missed_reason=payload.missed_reason,
            logged_by=logged_by,
        )
        await record.insert()
        return await self._serialize(record)

    async def list_for_provider(self, provider_id: Any, year: int | None = None) -> dict[str, Any]:
        """Return a provider's coverage log, optionally filtered to one calendar year."""
        records = await CoverageLog.find(CoverageLog.provider_id == _as_object_id(provider_id)).to_list()
        if year:
            records = [r for r in records if r.coverage_date.year == year]
        records.sort(key=lambda item: item.coverage_date, reverse=True)
        return {"entries": [await self._serialize(r) for r in records]}

    async def total_hours_for_provider(self, provider_id: Any, year: int) -> float:
        """Return a provider's total logged coverage hours for one calendar year."""
        records = await CoverageLog.find(CoverageLog.provider_id == _as_object_id(provider_id)).to_list()
        return sum(r.hours for r in records if r.coverage_date.year == year)

    async def total_rsd_hours_for_provider(self, provider_id: Any, year: int) -> float:
        """Return a provider's real RSD (weekend support) hours for one calendar year.

        DOCX line 239: "Track RSD weekend support coverage separately from
        normal operating hours." `is_weekend_rsd` has been captured on
        every `CoverageLog` entry since the model was built, but was never
        aggregated separately until now.
        """
        records = await CoverageLog.find(CoverageLog.provider_id == _as_object_id(provider_id)).to_list()
        return sum(r.hours for r in records if r.coverage_date.year == year and r.is_weekend_rsd)

    async def get_rsd_summary(self, year: int) -> dict[str, Any]:
        """Return real RSD coverage hours across every provider, for one calendar year."""
        all_logs = await CoverageLog.find().to_list()
        rsd_logs = [r for r in all_logs if r.coverage_date.year == year and r.is_weekend_rsd]
        total_rsd_hours = sum(r.hours for r in rsd_logs)
        session_count = len(rsd_logs)
        return {
            "year": year,
            "total_rsd_hours": total_rsd_hours,
            "session_count": session_count,
        }

    async def get_schedule_vs_worked_summary(self, role: str, year: int) -> dict[str, Any]:
        """Return real scheduled-vs-worked hours for a role, for one calendar year.

        Only entries that were logged with a real `scheduled_hours` value
        contribute - entries from before this field existed (`None`) are
        excluded rather than assumed to mean "worked == scheduled", so this
        summary never fabricates a schedule that was never actually logged.
        """
        records = await CoverageLog.find(CoverageLog.role == role).to_list()
        records = [r for r in records if r.coverage_date.year == year and r.scheduled_hours is not None]

        total_scheduled_hours = sum(r.scheduled_hours for r in records if r.scheduled_hours is not None)
        total_worked_hours = sum(r.hours for r in records)
        missed_entries = [r for r in records if r.hours < (r.scheduled_hours or 0)]

        missed_by_reason: dict[str, int] = {}
        for record in missed_entries:
            reason = record.missed_reason or "unspecified"
            missed_by_reason[reason] = missed_by_reason.get(reason, 0) + 1

        return {
            "role": role,
            "year": year,
            "entries_with_schedule": len(records),
            "total_scheduled_hours": total_scheduled_hours,
            "total_worked_hours": total_worked_hours,
            "worked_pct_of_scheduled": (
                round(total_worked_hours / total_scheduled_hours * 100, 1) if total_scheduled_hours else None
            ),
            "missed_count": len(missed_entries),
            "missed_by_reason": missed_by_reason,
        }

    async def get_reconditioning_load_by_flight(self) -> dict[str, Any]:
        """Real per-flight reconditioning/rehab caseload, k-gated - never a per-operator list.

        Not DOCX-sourced - the ascend-admin frontend's SCS "Workload by
        flight" table also shows "PT/OFT lanes" and "Capacity" columns with
        no real data source anywhere (no lane taxonomy, no capacity number
        tracked for any flight/provider) - those are deliberately not
        built. This surfaces only the real, honestly-derivable slice: how
        many of a flight's real members currently have an active
        `ReconditioningPlan`, and that count as a real percentage of the
        flight's real cohort size. Same k-gated flight-grouping shape as
        `LeadershipAggregateService.get_flight_comparison`.
        """
        scope_config = await self.role_admin_service.get_scope_config(ROLE_SCS)
        cohort_k = scope_config["cohort_k"]
        flights = await OrgUnit.find(OrgUnit.unit_type == "flight").to_list()
        active_plans = await ReconditioningPlan.find(ReconditioningPlan.phase != "completed").to_list()
        active_user_ids = {p.user_id for p in active_plans}

        rows: list[dict[str, Any]] = []
        for flight in flights:
            members = await User.find(User.unit_id == str(flight.id)).to_list()
            cohort_size = len(members)
            if cohort_size < cohort_k:
                continue
            active_count = sum(1 for m in members if m.id in active_user_ids)
            rows.append(
                {
                    "flight_id": str(flight.id),
                    "flight_name": flight.name,
                    "cohort_size": cohort_size,
                    "active_reconditioning_count": active_count,
                    "load_pct": round(active_count / cohort_size * 100, 1),
                }
            )

        rows.sort(key=lambda item: item["flight_name"])
        return {
            "min_cohort_size": cohort_k,
            "total_flights": len(flights),
            "flights_meeting_cohort_minimum": len(rows),
            "flights": rows,
        }

    async def export_prs_evidence(self, year: int) -> list[dict[str, Any]]:
        """Return real per-entry `CoverageLog` rows for every SCS/PT-IM provider for one year.

        The actual evidence artifact backing `meets_95pct_evidence` in the
        PRS/QCP report (`ReportsService.get_prs_qcp_report`) - not a new
        tracking system, just a flat, exportable rendering of coverage logs
        that already exist.
        """
        providers = await User.find().to_list()
        providers = [u for u in providers if u.role in PRS_EVIDENCE_ROLES]

        rows: list[dict[str, Any]] = []
        for provider in providers:
            records = await CoverageLog.find(CoverageLog.provider_id == provider.id).to_list()
            records = [r for r in records if r.coverage_date.year == year]
            records.sort(key=lambda item: item.coverage_date)
            for record in records:
                rows.append(
                    {
                        "provider_id": str(provider.id),
                        "provider_name": provider.full_name,
                        "role": provider.role,
                        "coverage_date": record.coverage_date.isoformat(),
                        "hours": record.hours,
                        "is_weekend_rsd": record.is_weekend_rsd,
                        "notes": record.notes or "",
                    }
                )
        return rows

    async def _serialize(self, record: CoverageLog) -> dict[str, Any]:
        """Convert a stored coverage entry to a transport-safe dict."""
        provider = await User.get(record.provider_id)
        return {
            "id": str(record.id),
            "provider_id": str(record.provider_id),
            "provider_name": provider.full_name if provider else None,
            "role": record.role,
            "hours": record.hours,
            "coverage_date": record.coverage_date.isoformat(),
            "is_weekend_rsd": record.is_weekend_rsd,
            "notes": record.notes,
            "scheduled_hours": record.scheduled_hours,
            "missed_reason": record.missed_reason,
        }
