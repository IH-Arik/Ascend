"""Records home aggregator + Data-use summary (plain-language policy page).

`get_home` pulls a one-line status per category from each real module -
never fabricates a count/date for a category with no data yet, it just
reports "No records yet" / "Not available" honestly.

`get_data_use_summary` is static structured content, not computed data -
adapted from the docx's own module list and access/audit rules, with one
correction applied consistently across this project: this system has no
CAC/PKI integration, so identity is described as coming from the Ascend
account (email/password), not "CAC-sourced." Every "what we audit" line
below names something this backend actually does today - no aspirational
claims for audit categories that aren't wired up yet.
"""

from __future__ import annotations

from typing import Any

from app.models.assessment import Assessment
from app.models.medical_record import MedicalRecord
from app.models.oft_record import OFTRecord
from app.models.workout_log import WorkoutLog
from app.services.oft_service import OFTService
from app.services.reconditioning_service import ReconditioningService
from app.models.user import User


class RecordsService:
    """Build the Records home and Data-use summary payloads."""

    def __init__(self) -> None:
        self.oft_service = OFTService()
        self.reconditioning_service = ReconditioningService()

    async def get_home(self, user: User) -> dict[str, Any]:
        """Return the 6-category Records home summary."""
        uploads = await MedicalRecord.find(MedicalRecord.user_id == user.id).to_list()
        workouts = await WorkoutLog.find(WorkoutLog.user_id == user.id).to_list()
        oft_status = await self.oft_service.get_status_for_user(user)
        reconditioning = await self.reconditioning_service.get_for_user(user.id)
        assessments = await Assessment.find(
            Assessment.user_id == user.id, Assessment.status == "completed"
        ).to_list()

        latest_upload = max(uploads, key=lambda r: r.uploaded_at) if uploads else None
        latest_workout = max(workouts, key=lambda r: r.activity_date) if workouts else None

        return {
            "categories": [
                {
                    "key": "my_uploads",
                    "label": "My Uploads",
                    "subtitle": (
                        f"Medical record history - last {latest_upload.uploaded_at.date().isoformat()}"
                        if latest_upload
                        else "No records yet"
                    ),
                },
                {
                    "key": "workouts_log",
                    "label": "Workouts Log",
                    "subtitle": (
                        f"Recent activity - {latest_workout.activity_type} - "
                        f"{latest_workout.activity_date.isoformat()}"
                        if latest_workout
                        else "No workouts logged yet"
                    ),
                },
                {
                    "key": "oft_status",
                    "label": "OFT Status",
                    "subtitle": f"Current test cycle - {oft_status['current_status']}",
                },
                {
                    "key": "reconditioning_plan",
                    "label": "Reconditioning Plan",
                    "subtitle": (
                        f"{reconditioning['phase_label']} - {reconditioning['ptim_clearance_label']}"
                        if reconditioning["available"]
                        else "Not available - no active plan"
                    ),
                },
                {
                    "key": "assessments",
                    "label": "Assessments",
                    "subtitle": (
                        f"{len(assessments)} completed" if assessments else "Initial status - not yet complete"
                    ),
                },
                {
                    "key": "fly_away_kit",
                    "label": "Fly Away Kit",
                    "subtitle": "Read-only preview",
                },
            ]
        }

    def get_data_use_summary(self) -> dict[str, Any]:
        """Return the static Data-use summary policy content."""
        return {
            "system_of_record_boundary": (
                "Ascend is not OMPF/iPERMS, MHS GENESIS, or AHLTA. Medical records you "
                "upload into Ascend are controlled copies used for performance support - "
                "they are not authoritative records."
            ),
            "what_ascend_stores": [
                {
                    "title": "Identity",
                    "detail": "Name, rank/grade, unit, role - set at registration and by admin provisioning.",
                },
                {"title": "Onboarding baseline", "detail": "20 readiness questions answered once - used only to compute your starting OPS band."},
                {
                    "title": "Daily / weekly / monthly check-ins",
                    "detail": "OPS scores are computed by cadence - never the raw answers - on leadership surfaces.",
                },
                {"title": "Workouts", "detail": "Logged from My Support Team - Strength - cardio - mobility - RPE."},
                {"title": "OFT currency", "detail": "Operational Fitness Test events and component status. Updated from your last OFT."},
                {
                    "title": "Medical records you upload",
                    "detail": "PDF, image, DICOM - up to 50 MB - behind an access-reason gate. Controlled copies, not authoritative.",
                },
            ],
            "what_ascend_does_not_store": [
                {"title": "OMPF / iPERMS records", "detail": "Your personnel file lives in the official system. Ascend does not mirror it."},
                {"title": "MHS GENESIS / AHLTA records", "detail": "Official medical-record systems. Ascend is downstream of either, not a substitute."},
                {"title": "Aggregate leadership views of you by name", "detail": "OPS bands only - never raw answers, never your name in a chart."},
            ],
            "who_can_see_your_data": [
                {"title": "You (the operator)", "detail": "Own data - full read. No write to other people's data."},
                {"title": "SCS (your assigned)", "detail": "Workouts, OFT, reconditioning, summary medical guidance. No raw medical record."},
                {"title": "PT/IM (your assigned)", "detail": "Full medical-record access for assigned users + rehab / return-to-performance planning."},
                {"title": "Nutrition / Mental Perf / Purpose", "detail": "Only authorized, minimum-necessary context they see what their specialty requires."},
                {"title": "Leadership / HPO", "detail": "Aggregate only by default. Cells below k=5 render 'data unavailable'."},
                {"title": "DWS Admin", "detail": "Audit + RBAC. Sees clinical content only when flagged for audit."},
            ],
            "what_we_audit": [
                {"title": "Every medical-record access event", "detail": "Actor, role, action, record id, timestamp - written to an append-only log."},
                {"title": "Every support-pathway toggle", "detail": "Enable/disable of an optional pathway is audit logged."},
                {"title": "Every message send", "detail": "Sender/recipient role scope and OPSEC scan result are audit logged."},
                {"title": "Every login attempt", "detail": "Success and failure, with IP address and device (User-Agent) - audit logged."},
                {"title": "OPSEC keyword scan", "detail": "Every message, support request, and record access-reason is scanned; a Level 5 safety-boundary match is separately flagged for priority human review."},
            ],
            "your_controls": [
                {"title": "Consent toggles", "detail": "Set during onboarding. Data-use consent + recommendation opt-in. Updated through Profile settings."},
                {"title": "Deactivate your account", "detail": "Routes an audit-trailed request to the DWS Admin queue. No data deletion occurs from this surface."},
            ],
        }
