"""The 9 required contract reports (DOCX Table 26: "Report | Required
Sections | Primary Users").

Real, DOCX-verbatim - not the Figma "Exports" screen's invention. Found
2026-08-23 checking whether that screen's "9 required contract reports"
panel had any backing: it does, exactly - DOCX Table 26 lists exactly 9
named reports with required sections and primary users, and `docx_name`/
`required_sections`/`primary_users` below are transcribed directly from
it. `report_type` maps each to the real backend key that builds it
(`REPORT_BUILDERS` in `app/modules/admin/routes.py` and
`app/services/scheduled_export_service.py` - both dicts, kept in sync).

The mock's other columns (PERIOD/DUE DATE/APPROVAL/SENSITIVITY-as-"CUI")
are NOT reproduced here - no real compliance-due-date registry or named-
approver-per-report system exists in this backend, and inventing one
would repeat the same mistake this file exists to fix elsewhere in this
session. `ContractReportsService.get_status` (in
`app/services/reports_service.py`) reports only what is real: whether
each report has ever been generated, and when.
"""

from typing import Final

REQUIRED_CONTRACT_REPORTS: Final[list[dict[str, str]]] = [
    {
        "report_type": "oft_metrics",
        "docx_name": "Monthly OFT Metrics Report",
        "required_sections": (
            "Date range; operator current/not current/exempt count; tests conducted; "
            "pass/fail count; failed OFT list if authorized; reconditioning status; "
            "issues requiring leadership attention."
        ),
        "primary_users": "SCS, Leadership/HPO Manager, Admin",
    },
    {
        "report_type": "utilization",
        "docx_name": "Quarterly Utilization Report",
        "required_sections": (
            "Training opportunities vs actual use; education opportunities vs actual use; "
            "feedback sessions offered/completed; app engagement; messaging/support "
            "utilization; recommendations to optimize services."
        ),
        "primary_users": "Leadership/HPO Manager, KO/COR if directed, Admin",
    },
    {
        "report_type": "injury",
        "docx_name": "Quarterly Injury/Recovery Report",
        "required_sections": (
            "Individual operator injuries and rehab strategy summaries only for authorized "
            "recipients; return-to-performance status; PT/IM follow-up; SCS coordination; "
            "unresolved issues."
        ),
        "primary_users": "PT/IM, SCS, approved Government recipients",
    },
    {
        "report_type": "assessment_completion",
        "docx_name": "Assessment Completion Report",
        "required_sections": (
            "Eligible operators; initial assessment status; 50%/six-month progress; "
            "90%/12-month progress; follow-on assessment due/completed; feedback sessions."
        ),
        "primary_users": "SCS, PT/IM, HPO Manager, Admin",
    },
    {
        "report_type": "prs_qcp",
        "docx_name": "PRS/QCP Support Report",
        "required_sections": (
            "SCS/PT coverage hours; missed coverage flags; assessment compliance; "
            "corrective actions; issue categories; prevention actions; closure status."
        ),
        "primary_users": "DWS Contract Manager, KO/COR if authorized",
    },
    {
        "report_type": "leadership_aggregate_readiness",
        "docx_name": "Leadership Aggregate Readiness Report",
        "required_sections": (
            "Aggregate OPS, readiness component trends, HPO/H2F component trends, support "
            "category usage, reconditioning status, utilization summary, equipment gaps, "
            "recommendations."
        ),
        "primary_users": "Leadership/HPO Manager",
    },
    {
        "report_type": "idmt_handoff_summary",
        "docx_name": "IDMT Documentation Handoff Summary",
        "required_sections": (
            "Operator identifier as approved; export type; prepared by; recipient role; "
            "date prepared/transmitted; acknowledgement status; content category."
        ),
        "primary_users": "PT/IM/SCS/Admin/IDMT as approved",
    },
    {
        "report_type": "medical_records_audit",
        "docx_name": "Medical Records Upload and Access Audit Report",
        "required_sections": (
            "Date range; documents uploaded; document types; review status; access events; "
            "exports/downloads; recipient roles; unresolved review items; retention/"
            "disposition status; anomalies or unauthorized-access flags."
        ),
        "primary_users": "PT/IM, DWS Admin, Contract Manager, approved Government recipients only",
    },
    {
        "report_type": "performance_summary_export",
        "docx_name": "Medical History Performance Summary Export",
        "required_sections": (
            "Minimum-necessary performance implications from uploaded medical history; "
            "approved limitations; return-to-performance considerations; reconditioning "
            "considerations; specialist visibility level; reviewer name/role; review date."
        ),
        "primary_users": "PT/IM, SCS, authorized specialists, IDMT or Government recipient as approved",
    },
]
