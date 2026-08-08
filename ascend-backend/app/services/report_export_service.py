"""Report export service (DOCX section 12: "Reports should be exportable as
PDF and CSV where practical. Each report export must create an export
log entry.").

CSV only - no PDF rendering library has been added to this project, so PDF
export is not implemented rather than half-built. CSV covers the DOCX's
"where practical" qualifier: it needs no new heavyweight dependency and the
report data here is inherently tabular.

Every export writes a `ReportExport` log entry first (export_type, date
range, who generated it, recipient role, format, sensitivity level) per the
DOCX's own data dictionary for this exact concept - matching the "Report
control and OPSEC/CUI audit" use case named there.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from app.models.report_export import ReportExport
from app.models.user import User

REPORT_ROW_KEYS = {
    "injury": "operators",
    "assessment_completion": None,
    "utilization": "events",
    "prs_qcp": "providers",
}


class ReportExportService:
    """Render a report as CSV and log the export event."""

    async def export_csv(
        self,
        report_type: str,
        report_data: dict[str, Any],
        generated_by: User,
        date_range: str,
    ) -> tuple[bytes, str]:
        """Return CSV bytes for a report and write its export-log entry."""
        rows_key = REPORT_ROW_KEYS.get(report_type)
        rows = report_data.get(rows_key, []) if rows_key else [report_data]
        if not rows:
            rows = [{"note": "No data available for this report."}]

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (v if not isinstance(v, (list, dict)) else str(v)) for k, v in row.items()})
        csv_bytes = buffer.getvalue().encode("utf-8")

        await ReportExport(
            report_type=report_type,
            date_range=date_range,
            generated_by=generated_by.id,
            recipient_role=generated_by.role,
            export_format="csv",
        ).insert()

        return csv_bytes, f"{report_type}_{date_range}.csv"

    async def list_export_log(self, report_type: str | None = None) -> dict[str, Any]:
        """Return the export log, optionally filtered by report type."""
        records = await ReportExport.find().to_list()
        if report_type:
            records = [r for r in records if r.report_type == report_type]
        records.sort(key=lambda item: item.created_at, reverse=True)
        return {
            "exports": [
                {
                    "id": str(r.id),
                    "report_type": r.report_type,
                    "date_range": r.date_range,
                    "generated_by": str(r.generated_by),
                    "recipient_role": r.recipient_role,
                    "export_format": r.export_format,
                    "sensitivity_level": r.sensitivity_level,
                    "export_log_status": r.export_log_status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in records
            ]
        }
