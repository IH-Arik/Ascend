"""Report export service (DOCX section 12: "Reports should be exportable as
PDF and CSV where practical. Each report export must create an export
log entry.").

CSV and PDF (via `fpdf2`, pure-Python, no system libraries needed) - PDF
was previously not implemented ("no PDF library added"); now real, not a
CSV relabel.

Every export writes a `ReportExport` log entry first (export_type, date
range, who generated it, recipient role, format, sensitivity level) per the
DOCX's own data dictionary for this exact concept - matching the "Report
control and OPSEC/CUI audit" use case named there.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from beanie import PydanticObjectId
from fpdf import FPDF

from app.models.org_unit import OrgUnit
from app.models.report_export import LIFECYCLE_STATUSES, ReportExport
from app.models.user import User

REPORT_ROW_KEYS = {
    "injury": "operators",
    "assessment_completion": None,
    "utilization": "events",
    "prs_qcp": "providers",
    "audit_log": "entries",
    "oft_metrics": None,
    "wing_weekly_ops": None,
    "monthly_cohort_review": None,
    "annual_wing_readiness": None,
    "leadership_aggregate_readiness": None,
    "idmt_handoff_summary": "handoffs",
    "medical_records_audit": None,
    "performance_summary_export": "summaries",
}

# Not DOCX-sourced (see `app/models/pending_confirmation.py`) - "restricted"
# reports carry per-Airman identifiable rows (injury's rows are tied to
# individual health/limitation data) and are gated through the
# second-reviewer confirmation queue; "aggregate" reports (cohort
# completion rates, event counts, per-provider coverage hours - never
# per-Airman rows) keep exporting immediately, unchanged. `audit_log` is
# `"restricted"` too - the audit trail itself is sensitive - reusing the
# exact same gate rather than a separate export-approval mechanism.
REPORT_SENSITIVITY = {
    "injury": "restricted",
    "assessment_completion": "aggregate",
    "utilization": "aggregate",
    "prs_qcp": "aggregate",
    "audit_log": "restricted",
    "oft_metrics": "aggregate",
    "wing_weekly_ops": "aggregate",
    "monthly_cohort_review": "aggregate",
    "annual_wing_readiness": "aggregate",
    "leadership_aggregate_readiness": "aggregate",
    # All 3 restricted - each carries per-Airman identifiable data (a real
    # recipient/prepared-by/reviewer role plus a specific operator's
    # record), same reasoning as "injury" above.
    "idmt_handoff_summary": "restricted",
    "medical_records_audit": "restricted",
    "performance_summary_export": "restricted",
}

# Real, minimal template registry (2026-08-10, Leadership "Reports" pass) -
# not DOCX-sourced. A "Use" action creates a real `ScheduledExport` from
# these defaults (`app/modules/dashboard/routes.py`) - not a separate
# report-generation path of its own.
REPORT_TEMPLATES = {
    "wing_weekly": {
        "title": "Wing Weekly",
        "report_type": "wing_weekly_ops",
        "cadence": "weekly",
        "export_format": "csv",
    },
    "monthly_cohort": {
        "title": "Monthly Cohort",
        "report_type": "monthly_cohort_review",
        "cadence": "monthly",
        "export_format": "csv",
    },
    "quarterly_oft": {
        "title": "Quarterly OFT",
        "report_type": "oft_metrics",
        "cadence": "quarterly",
        "export_format": "csv",
    },
    "annual_wing": {
        "title": "Annual Wing",
        "report_type": "annual_wing_readiness",
        "cadence": "annual",
        "export_format": "csv",
    },
}

# Not DOCX-sourced (an Exports admin screen showed export "risk" labels
# reusing the L1/L3/L4 prefix from the DOCX's own, differently-meaning
# L0-L5 readiness-escalation catalog - app/core/routing_levels.py). This is
# a real, distinctly-named tier instead, derived from the same real
# sensitivity_level + row-count data already tracked, deliberately never
# `L`-prefixed so the two concepts can't be confused.
HIGH_RISK_ROW_THRESHOLD = 10


def compute_risk_tier(sensitivity_level: str, record_count: int) -> str:
    """Return a real, non-`L`-prefixed export risk tier."""
    if sensitivity_level != "restricted":
        return "low"
    return "high" if record_count >= HIGH_RISK_ROW_THRESHOLD else "elevated"


def report_rows(report_type: str, report_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the tabular rows a report's CSV/PDF/row-count is built from."""
    rows_key = REPORT_ROW_KEYS.get(report_type)
    rows = report_data.get(rows_key, []) if rows_key else [report_data]
    return rows or []


class ReportExportService:
    """Render a report as CSV or PDF and log the export event."""

    def render_csv(
        self, report_type: str, report_data: dict[str, Any], rows: list[dict[str, Any]] | None = None
    ) -> tuple[bytes, str]:
        """Return CSV bytes for a report. Does not write an export-log entry.

        `rows`, if given, is used directly instead of extracting rows from
        `report_data` via `REPORT_ROW_KEYS` - lets a caller (e.g. PRS
        evidence export) render pre-built rows that don't fit the normal
        `REPORT_BUILDERS` shape.
        """
        rows = rows if rows is not None else report_rows(report_type, report_data)
        rows = rows or [{"note": "No data available for this report."}]

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (v if not isinstance(v, (list, dict)) else str(v)) for k, v in row.items()})
        csv_bytes = buffer.getvalue().encode("utf-8")
        return csv_bytes, f"{report_type}.csv"

    def render_pdf(
        self, report_type: str, report_data: dict[str, Any], rows: list[dict[str, Any]] | None = None
    ) -> tuple[bytes, str]:
        """Return real PDF bytes for a report - simple tabular layout. Does not write an export-log entry.

        `rows` behaves the same as in `render_csv`.
        """
        rows = rows if rows is not None else report_rows(report_type, report_data)
        rows = rows or [{"note": "No data available for this report."}]
        columns = list(rows[0].keys())

        pdf = FPDF(orientation="landscape")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"{report_type.replace('_', ' ').title()} Report", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=8)

        col_width = pdf.epw / max(len(columns), 1)
        pdf.set_font("Helvetica", "B", 8)
        for col in columns:
            pdf.cell(col_width, 8, str(col)[:30], border=1)
        pdf.ln(8)

        pdf.set_font("Helvetica", size=8)
        for row in rows:
            for col in columns:
                value = row.get(col)
                text = str(value) if not isinstance(value, (list, dict)) else str(value)
                pdf.cell(col_width, 8, text[:40], border=1)
            pdf.ln(8)

        pdf_bytes = bytes(pdf.output())
        return pdf_bytes, f"{report_type}.pdf"

    def render_prose_pdf(self, title: str, subtitle: str, sections: list[dict[str, str]]) -> bytes:
        """Return real prose PDF bytes for a narrative document (e.g. a Leadership briefing).

        Unlike `render_pdf` (strictly tabular - fixed-width cells), this
        renders a title/subtitle header plus a heading + word-wrapped
        paragraph per section, via `multi_cell` - a genuinely different
        rendering path for prose content, not a reuse of the tabular one.

        Every `multi_cell` call passes `new_x="LMARGIN", new_y="NEXT"`
        explicitly - fpdf2's default leaves the cursor at the right edge of
        the text just drawn (not a new line at the left margin), so the
        *next* call renders into whatever sliver of width remains and
        raises `FPDFException: Not enough horizontal space to render a
        single character`. Found live-verifying this method; the existing
        tabular `render_pdf` above already handles this same real gotcha on
        its title `cell()` call, just never applied here.
        """
        pdf = FPDF(orientation="portrait")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 18)
        pdf.multi_cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "I", 10)
        pdf.multi_cell(0, 8, subtitle, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        for section in sections:
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 8, section.get("title", ""), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=10)
            pdf.multi_cell(
                0, 6, section.get("body") or "No content generated for this section.", new_x="LMARGIN", new_y="NEXT"
            )
            pdf.ln(4)

        return bytes(pdf.output())

    def render(
        self,
        report_type: str,
        report_data: dict[str, Any],
        export_format: str,
        rows: list[dict[str, Any]] | None = None,
    ) -> tuple[bytes, str]:
        """Render a report in the requested real format ("csv" or "pdf")."""
        if export_format == "pdf":
            return self.render_pdf(report_type, report_data, rows)
        return self.render_csv(report_type, report_data, rows)

    async def export_report(
        self,
        report_type: str,
        report_data: dict[str, Any],
        generated_by: User,
        date_range: str,
        export_format: str = "csv",
        title: str | None = None,
        flight_id: str | None = None,
        recipient_role: str | None = None,
    ) -> tuple[bytes, str]:
        """Render a non-restricted report in the requested format and write its export-log entry.

        `title` falls back to a titleized `report_type` when not given, so
        every `ReportExport` row always has something real to search
        against (`search()` below) - never a blank field. `recipient_role`
        defaults to the generating admin's own role (the original
        behavior) unless a real one is supplied - a recurring
        `ScheduledExport` passes its own admin-configured recipient_role.
        """
        content_bytes, _ = self.render(report_type, report_data, export_format)
        file_name = f"{report_type}_{date_range}.{export_format}"

        await ReportExport(
            report_type=report_type,
            date_range=date_range,
            generated_by=generated_by.id,
            recipient_role=recipient_role or generated_by.role,
            export_format=export_format,
            sensitivity_level=REPORT_SENSITIVITY.get(report_type, "controlled"),
            title=title or report_type.replace("_", " ").title(),
            flight_id=flight_id,
            file_size_bytes=len(content_bytes),
        ).insert()

        return content_bytes, file_name

    async def set_lifecycle_status(self, export_id: str, new_status: str) -> dict[str, Any]:
        """Explicitly transition a real export's Leadership-facing lifecycle status.

        The only way to reach "sent"/"archived"/"draft" - "in_review"/"ready"
        are set automatically alongside the second-reviewer gate
        (`admin_confirmation_service.py`).
        """
        record = await ReportExport.get(export_id)
        if record is None:
            raise ValueError("Export not found.")
        if new_status not in LIFECYCLE_STATUSES:
            raise ValueError(f"Unknown lifecycle status. Allowed: {list(LIFECYCLE_STATUSES)}")
        record.lifecycle_status = new_status
        await record.save()
        return self._serialize_export(record)

    async def search(self, query: str) -> dict[str, Any]:
        """Real case-insensitive substring search over title, resolved flight name, and report_type."""
        records = await ReportExport.find().to_list()
        needle = query.lower()

        flight_ids = {r.flight_id for r in records if r.flight_id}
        flights = await OrgUnit.find({"_id": {"$in": [PydanticObjectId(fid) for fid in flight_ids]}}).to_list()
        flight_names = {str(f.id): f.name for f in flights}

        matches = []
        for record in records:
            haystack = " ".join(
                filter(
                    None,
                    [record.title, record.report_type, flight_names.get(record.flight_id or "")],
                )
            ).lower()
            if needle in haystack:
                matches.append(record)

        matches.sort(key=lambda item: item.created_at, reverse=True)
        return {"exports": [self._serialize_export(r) for r in matches]}

    async def list_export_log(self, report_type: str | None = None) -> dict[str, Any]:
        """Return the export log, optionally filtered by report type."""
        records = await ReportExport.find().to_list()
        if report_type:
            records = [r for r in records if r.report_type == report_type]
        records.sort(key=lambda item: item.created_at, reverse=True)
        return {"exports": [self._serialize_export(r) for r in records]}

    def _serialize_export(self, r: ReportExport) -> dict[str, Any]:
        """Convert a stored export-log entry to a transport-safe dict."""
        return {
            "id": str(r.id),
            "report_type": r.report_type,
            "date_range": r.date_range,
            "generated_by": str(r.generated_by),
            "recipient_role": r.recipient_role,
            "export_format": r.export_format,
            "sensitivity_level": r.sensitivity_level,
            "export_log_status": r.export_log_status,
            "lifecycle_status": r.lifecycle_status,
            "title": r.title,
            "flight_id": r.flight_id,
            "file_size_bytes": r.file_size_bytes,
            "created_at": r.created_at.isoformat(),
        }
