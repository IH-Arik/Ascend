"""IDMT documentation handoff service (DOCX Section 8.5).

Real prepared -> approved -> transmitted -> acknowledged lifecycle. Approval
reuses the existing `PendingConfirmation`/`AdminConfirmationService`
two-person-rule queue (a 4th `action_type`, `"idmt_handoff"`) rather than a
parallel approval mechanism - matching the DOCX's "never auto-transmit raw
medical records without an approved recipient role/purpose/audit log."

The handoff's content is always a real, structured summary built from
already-real data (`ReconditioningPlan`, `MedicalRecord` document-type
counts, OFT status) - never raw file bytes or `storage_path`. IDMT is a
summary recipient, never a raw-record viewer.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.roles import ROLE_IDMT
from app.core.security import utc_now
from app.models.idmt_handoff import EXPORT_TYPES, IdmtHandoff
from app.models.medical_record import MedicalRecord
from app.models.pending_confirmation import PendingConfirmation
from app.models.user import User
from app.services.audit_log_service import AuditLogService
from app.services.oft_service import OFTService
from app.services.reconditioning_service import ReconditioningService
from app.services.report_export_service import ReportExportService


class IdmtHandoffService:
    """Prepare, transmit, acknowledge, and render IDMT documentation handoffs."""

    def __init__(self) -> None:
        self.reconditioning_service = ReconditioningService()
        self.oft_service = OFTService()
        self.report_export_service = ReportExportService()
        self.audit_log_service = AuditLogService()

    async def prepare(
        self, preparer: User, target_user_id: str, export_type: str, export_format: str
    ) -> dict[str, Any]:
        """Create a real handoff + pending second-reviewer confirmation. Never applied immediately."""
        target = await User.get(target_user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if export_type not in EXPORT_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown export type.")

        content_category = {
            "injury_summary": "reconditioning",
            "reconditioning_summary": "reconditioning",
            "medical_record_summary": "medical_records",
        }[export_type]

        handoff = IdmtHandoff(
            user_id=target.id,
            export_type=export_type,
            content_category=content_category,
            export_format=export_format,
            prepared_by=preparer.id,
            recipient_role=ROLE_IDMT,
        )
        await handoff.insert()

        confirmation = PendingConfirmation(
            action_type="idmt_handoff",
            requested_by=preparer.id,
            target_entity_type="idmt_handoff",
            target_entity_id=str(handoff.id),
            target_summary=f"{export_type} for {target.full_name or target.email}",
            consequence_summary=f"Documentation summary released to {ROLE_IDMT}",
            scope_summary=f"{content_category} - {target.role}",
            payload={"export_type": export_type, "export_format": export_format},
        )
        await confirmation.insert()

        await self.audit_log_service.record(
            event_type="idmt_handoff_prepared",
            actor_id=preparer.id,
            actor_role=preparer.role,
            target_entity_type="idmt_handoff",
            target_entity_id=str(handoff.id),
            summary_message=f"Prepared {export_type} handoff for {target.email}.",
            metadata_payload={"confirmation_id": str(confirmation.id)},
        )
        return {
            "handoff_id": str(handoff.id),
            "confirmation_id": str(confirmation.id),
            "status": handoff.status,
        }

    async def transmit(self, actor: User, handoff_id: str) -> dict[str, Any]:
        """Mark an approved handoff transmitted - a real, distinct state from 'approved'."""
        handoff = await self._get(handoff_id)
        if handoff.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only an approved handoff can be transmitted.",
            )
        handoff.status = "transmitted"
        handoff.transmitted_date = utc_now()
        await handoff.save()
        await self.audit_log_service.record(
            event_type="idmt_handoff_transmitted",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="idmt_handoff",
            target_entity_id=str(handoff.id),
            summary_message="Transmitted IDMT documentation handoff.",
        )
        return await self._serialize(handoff)

    async def acknowledge(self, idmt_user: User, handoff_id: str) -> dict[str, Any]:
        """IDMT acknowledges receipt of a transmitted handoff. Idempotent."""
        handoff = await self._get(handoff_id)
        if handoff.status != "transmitted":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only a transmitted handoff can be acknowledged.",
            )
        handoff.status = "acknowledged"
        handoff.acknowledgement_status = "acknowledged"
        handoff.acknowledged_by = idmt_user.id
        handoff.acknowledged_at = utc_now()
        await handoff.save()
        await self.audit_log_service.record(
            event_type="idmt_handoff_acknowledged",
            actor_id=idmt_user.id,
            actor_role=idmt_user.role,
            target_entity_type="idmt_handoff",
            target_entity_id=str(handoff.id),
            summary_message="IDMT acknowledged receipt of a documentation handoff.",
        )
        return await self._serialize(handoff)

    async def list_for_idmt(self) -> dict[str, Any]:
        """Real handoffs visible to IDMT - only transmitted or acknowledged, never earlier states."""
        # Filtered in Python, not a multi-value Mongo query - same
        # documented preference used elsewhere in this codebase.
        all_handoffs = await IdmtHandoff.find(IdmtHandoff.recipient_role == ROLE_IDMT).to_list()
        handoffs = [h for h in all_handoffs if h.status in ("transmitted", "acknowledged")]
        handoffs.sort(key=lambda h: h.prepared_date, reverse=True)
        return {"handoffs": [await self._serialize(h) for h in handoffs]}

    async def list_all(self) -> dict[str, Any]:
        """Admin view - every handoff regardless of status."""
        handoffs = await IdmtHandoff.find().to_list()
        handoffs.sort(key=lambda h: h.prepared_date, reverse=True)
        return {"handoffs": [await self._serialize(h) for h in handoffs]}

    async def download(self, viewer: User, handoff_id: str) -> tuple[bytes, str]:
        """Render the real summary content - never raw MedicalRecord bytes."""
        handoff = await self._get(handoff_id)
        if handoff.status not in ("transmitted", "acknowledged"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This handoff has not been transmitted yet.",
            )
        target = await User.get(handoff.user_id)
        content = await self._build_summary_content(handoff, target)

        if handoff.export_format == "csv":
            content_bytes, filename = self.report_export_service.render_csv(
                "idmt_handoff", {}, rows=[content["flat_row"]]
            )
        else:
            pdf_bytes = self.report_export_service.render_prose_pdf(
                title=content["title"], subtitle=content["subtitle"], sections=content["sections"]
            )
            content_bytes, filename = pdf_bytes, f"idmt_handoff_{handoff.id}.pdf"

        await self.audit_log_service.record(
            event_type="idmt_handoff_downloaded",
            actor_id=viewer.id,
            actor_role=viewer.role,
            target_entity_type="idmt_handoff",
            target_entity_id=str(handoff.id),
            summary_message="Downloaded an IDMT documentation handoff summary.",
        )
        return content_bytes, filename

    async def _build_summary_content(self, handoff: IdmtHandoff, target: User | None) -> dict[str, Any]:
        """Real, structured summary - never raw file content. See module docstring."""
        user_name = target.full_name if target else "Unknown operator"
        reconditioning = await self.reconditioning_service.get_for_user(handoff.user_id)
        oft_status = await self.oft_service.get_status_for_user(target) if target else {}

        record_counts: dict[str, int] = {}
        for record in await MedicalRecord.find(MedicalRecord.user_id == handoff.user_id).to_list():
            record_counts[record.document_type] = record_counts.get(record.document_type, 0) + 1

        if reconditioning.get("available"):
            reconditioning_text = (
                f"Phase: {reconditioning.get('phase_label')}. "
                f"RTP status: {reconditioning.get('ptim_clearance_label')}. "
                f"Severity: {reconditioning.get('severity_level') or 'not set'}. "
                f"Days out: {reconditioning.get('days_out') if reconditioning.get('days_out') is not None else 'n/a'}. "
                f"SCS coordination: {reconditioning.get('scs_coordination_label')}."
            )
        else:
            reconditioning_text = "No active reconditioning plan on file."

        records_text = (
            ", ".join(f"{count} {doc_type}" for doc_type, count in sorted(record_counts.items())) or "none on file"
        )
        oft_text = f"Status: {oft_status.get('current_status', 'unknown')}" if oft_status else "No OFT record."

        sections = [
            {"title": "Reconditioning / Injury Status", "body": reconditioning_text},
            {"title": "Medical Record Categories On File", "body": f"Record counts by category: {records_text}."},
            {"title": "OFT Status", "body": oft_text},
        ]
        return {
            "title": f"IDMT Documentation Handoff - {user_name}",
            "subtitle": f"{handoff.export_type.replace('_', ' ').title()} - prepared {handoff.prepared_date.date().isoformat()}",
            "sections": sections,
            "flat_row": {
                "operator_name": user_name,
                "export_type": handoff.export_type,
                "content_category": handoff.content_category,
                "reconditioning_summary": reconditioning_text,
                "medical_record_categories": records_text,
                "oft_status": oft_text,
                "prepared_date": handoff.prepared_date.isoformat(),
            },
        }

    async def _get(self, handoff_id: str) -> IdmtHandoff:
        handoff = await IdmtHandoff.get(handoff_id)
        if handoff is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found.")
        return handoff

    async def _serialize(self, handoff: IdmtHandoff) -> dict[str, Any]:
        target = await User.get(handoff.user_id)
        preparer = await User.get(handoff.prepared_by)
        acknowledger = await User.get(handoff.acknowledged_by) if handoff.acknowledged_by else None
        return {
            "id": str(handoff.id),
            "user_id": str(handoff.user_id),
            "user_name": target.full_name if target else None,
            "export_type": handoff.export_type,
            "content_category": handoff.content_category,
            "export_format": handoff.export_format,
            "prepared_by_name": preparer.full_name if preparer else None,
            "recipient_role": handoff.recipient_role,
            "status": handoff.status,
            "prepared_date": handoff.prepared_date.isoformat(),
            "transmitted_date": handoff.transmitted_date.isoformat() if handoff.transmitted_date else None,
            "acknowledgement_status": handoff.acknowledgement_status,
            "acknowledged_by_name": acknowledger.full_name if acknowledger else None,
            "acknowledged_at": handoff.acknowledged_at.isoformat() if handoff.acknowledged_at else None,
        }
