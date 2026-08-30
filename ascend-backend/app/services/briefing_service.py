"""Leadership "Briefings" executive-briefing composer service (see
`app/models/briefing.py` for the real vs fabricated breakdown).

`SECTION_CATALOG` maps each real section type to the real data it's built
from - every value listed is composed from services already built and
live-verified earlier in the Leadership workspace series
(`LeadershipAggregateService`, `OFTService`, real `AuditLog(threshold_
warning)` severity, real `LeadershipAnnotation` entries). `BRIEFING_
TEMPLATES` only ever references these real section types - screenshot
language with no real backing ("recovery signal", "FY-quarter comparison",
"next quarter") is never claimed.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.scoring import build_score_band
from app.core.security import utc_now
from app.models.audit_log import AuditLog
from app.models.briefing import Briefing
from app.models.leadership_annotation import LeadershipAnnotation
from app.models.user import User
from app.services.ai_insights_service import AIInsightsService
from app.services.audit_log_service import AuditLogService
from app.services.leadership_aggregate_service import LeadershipAggregateService
from app.services.oft_service import OFTService
from app.services.report_export_service import ReportExportService

SECTION_TITLES = {
    "mission_context": "Mission context",
    "composite_trend": "Composite OPS trend",
    "driver_snapshot": "Driver snapshot",
    "by_flight": "By-flight comparison",
    "oft_snapshot": "OFT readiness",
    "band_distribution": "Cohort band distribution",
    "risk_recommendations": "Risk & recommendations",
    "recovery_snapshot": "Recovery program snapshot",
}

# Real, all sections reference only the 8 real types above - no screenshot
# language with no real backing ("FY-quarter comparison", "next quarter")
# is claimed. `mission_readiness`'s 5 sections match the screenshot's own
# concrete Outline/Preview example exactly (which is itself explicitly
# labeled "Mission readiness") - not the Mission Readiness template card's
# abbreviated blurb text ("OFT pass rate"), which turned out to be
# non-exhaustive marketing copy that doesn't match the real worked example
# shown on the same screen. `oft_snapshot` stays a real, valid section
# type (usable via a custom outline) - it's just not part of any of the 3
# default templates.
#
# `recovery_snapshot` (added 2026-08-25, real new scope, explicit go-ahead)
# is the real replacement for what was previously an entirely fabricated
# "recovery signal" narrative with no data behind it at all - it's now
# `LeadershipAggregateService.get_recovery_program_summary()`'s real
# per-flight active-reconditioning caseload, not a before/after cohort
# comparison (no real data source for that exists anywhere, and none is
# invented here either).
BRIEFING_TEMPLATES = {
    "mission_readiness": {
        "title": "Mission Readiness",
        "sections": ["mission_context", "composite_trend", "driver_snapshot", "by_flight", "risk_recommendations"],
    },
    "recovery_rollout": {
        "title": "Recovery Rollout",
        "sections": ["mission_context", "recovery_snapshot", "by_flight", "risk_recommendations"],
    },
    "quarterly_wing_review": {
        "title": "Quarterly Wing Review",
        "sections": ["composite_trend", "band_distribution", "risk_recommendations"],
    },
}

RISK_WINDOW_DAYS = 30


class BriefingService:
    """Create, fetch (live-regenerating while draft), edit, and send real Leadership briefings."""

    def __init__(self) -> None:
        self.leadership_aggregate_service = LeadershipAggregateService()
        self.oft_service = OFTService()
        self.ai_insights_service = AIInsightsService()
        self.audit_log_service = AuditLogService()
        self.report_export_service = ReportExportService()

    async def create(
        self,
        admin: User,
        title: str,
        template_key: str | None = None,
        custom_outline: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a real draft briefing from a template or a custom outline."""
        if template_key is not None:
            template = BRIEFING_TEMPLATES.get(template_key)
            if template is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Unknown template_key.", "allowed": list(BRIEFING_TEMPLATES.keys())},
                )
            outline = [{"section_key": key, "title": SECTION_TITLES[key]} for key in template["sections"]]
        elif custom_outline:
            outline = [{"section_key": item["section_key"], "title": item["title"]} for item in custom_outline]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Provide either template_key or custom_outline."
            )

        record = Briefing(title=title, template_key=template_key, outline=outline, created_by=admin.id)
        await record.insert()
        return await self.get(str(record.id))

    async def list_all(self) -> dict[str, Any]:
        """Return every real briefing, newest first."""
        records = await Briefing.find().to_list()
        records.sort(key=lambda item: item.created_at, reverse=True)
        return {"briefings": [self._serialize_summary(r) for r in records]}

    async def get(self, briefing_id: str) -> dict[str, Any]:
        """Return a briefing. While `draft`, live-regenerates content from current real data."""
        record = await self._get_or_404(briefing_id)
        if record.status == "draft":
            record.generated_content = await self._generate_content(record.outline)
        return self._serialize(record)

    async def update_outline(self, briefing_id: str, admin: User, outline: list[dict[str, Any]]) -> dict[str, Any]:
        """Edit a draft briefing's outline. Draft-only."""
        record = await self._get_or_404(briefing_id)
        if record.status != "draft":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a draft briefing can be edited.")
        record.outline = [{"section_key": item["section_key"], "title": item["title"]} for item in outline]
        record.updated_at = utc_now()
        await record.save()
        return await self.get(briefing_id)

    async def send(self, briefing_id: str, admin: User) -> dict[str, Any]:
        """Freeze the briefing's content at its final real state and mark it sent. Audit logged."""
        record = await self._get_or_404(briefing_id)
        if record.status == "sent":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This briefing was already sent.")
        record.generated_content = await self._generate_content(record.outline)
        record.status = "sent"
        record.sent_at = utc_now()
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="briefing_sent",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="briefing",
            target_entity_id=str(record.id),
            summary_message=f"Sent briefing '{record.title}'.",
            metadata_payload={"template_key": record.template_key, "section_count": len(record.outline)},
        )
        return self._serialize(record)

    async def render_pdf(self, briefing_id: str) -> bytes:
        """Return real prose PDF bytes for a briefing's current content."""
        data = await self.get(briefing_id)
        sections = [
            {"title": item["title"], "body": data["generated_content"].get(item["section_key"], "")}
            for item in data["outline"]
        ]
        return self.report_export_service.render_prose_pdf(data["title"], f"Status: {data['status']}", sections)

    async def _generate_content(self, outline: list[dict[str, Any]]) -> dict[str, str]:
        """Real: resolve each section's real data, then generate real prose for it."""
        content: dict[str, str] = {}
        for item in outline:
            section_key = item["section_key"]
            section_data = await self._get_section_data(section_key)
            content[section_key] = await self.ai_insights_service.generate_briefing_section_narrative(
                section_key, section_data
            )
        return content

    async def _get_section_data(self, section_key: str) -> dict[str, Any]:
        """Real per-section data resolver - each branch calls an already-real, already-verified method."""
        if section_key == "mission_context":
            trend = await self.leadership_aggregate_service.get_period_trend("12mo")
            latest = trend["months"][-1] if trend.get("months") else None
            cohort_size = latest["cohort_size"] if latest else 0
            min_k = trend.get("min_cohort_size", 5)
            confidence = "High" if cohort_size >= min_k * 2 else "Medium" if cohort_size >= min_k else "Insufficient"
            return {"cohort_size": cohort_size, "period": "12-month", "confidence": confidence}

        if section_key == "composite_trend":
            trend = await self.leadership_aggregate_service.get_period_trend("12mo")
            latest = trend["months"][-1] if trend.get("months") else None
            average_ops_score = latest["average_ops_score"] if latest else None
            return {
                "average_ops_score": average_ops_score,
                "score_band": build_score_band(average_ops_score),
                "mom_delta": trend.get("mom_delta"),
                "pvp_delta": trend.get("pvp_delta"),
            }

        if section_key == "driver_snapshot":
            aggregate = await self.leadership_aggregate_service.get_aggregate_view()
            return {"drivers": aggregate["driver_trends"]}

        if section_key == "by_flight":
            return await self.leadership_aggregate_service.get_flight_comparison()

        if section_key == "oft_snapshot":
            metrics = await self.oft_service.get_leadership_metrics_report()
            return {"pass_rate_pct": metrics.get("pass_rate_pct"), "status_counts": metrics.get("status_counts")}

        if section_key == "band_distribution":
            return await self.leadership_aggregate_service.get_band_distribution_trend()

        if section_key == "risk_recommendations":
            return await self._get_risk_section_data()

        if section_key == "recovery_snapshot":
            return await self.leadership_aggregate_service.get_recovery_program_summary()

        return {}

    async def _get_risk_section_data(self) -> dict[str, Any]:
        """Real risk scan: max real threshold-warning severity + real annotation titles in the window."""
        window_start = date.today() - timedelta(days=RISK_WINDOW_DAYS)
        warnings = await AuditLog.find(AuditLog.event_type == "threshold_warning").to_list()
        recent_warnings = [w for w in warnings if w.created_at.date() >= window_start]
        severity_rank = {"L2": 1, "L3": 2, "L4": 3}
        max_severity = None
        for warning in recent_warnings:
            level = warning.metadata_payload.get("severity_level")
            if level and (max_severity is None or severity_rank.get(level, 0) > severity_rank.get(max_severity, 0)):
                max_severity = level

        annotations = await LeadershipAnnotation.find(LeadershipAnnotation.event_date >= window_start).to_list()

        return {
            "max_severity": max_severity,
            "warning_count": len(recent_warnings),
            "annotation_titles": [a.title for a in annotations],
        }

    async def _get_or_404(self, briefing_id: str) -> Briefing:
        record = await Briefing.get(briefing_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Briefing not found.")
        return record

    def _serialize(self, record: Briefing) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "title": record.title,
            "template_key": record.template_key,
            "outline": record.outline,
            "generated_content": record.generated_content,
            "status": record.status,
            "created_by": str(record.created_by),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "sent_at": record.sent_at.isoformat() if record.sent_at else None,
        }

    def _serialize_summary(self, record: Briefing) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "title": record.title,
            "template_key": record.template_key,
            "status": record.status,
            "section_count": len(record.outline),
            "created_at": record.created_at.isoformat(),
            "sent_at": record.sent_at.isoformat() if record.sent_at else None,
        }
