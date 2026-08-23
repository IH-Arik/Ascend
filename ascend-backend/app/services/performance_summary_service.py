"""Medical History Performance Summary service (DOCX data dictionary + Table 23).

The entity exists to translate uploaded medical history into performance
guidance "without exposing unnecessary raw medical details", so the
per-role field scoping below is the feature, not a wrapper around it.
`ROLE_VISIBLE_FIELDS` encodes DOCX Table 23's row for this data type
literally - each role's cell is quoted above its entry.

Reuses the established viewer-aware serialization pattern from
`MedicalRecordService` (a `_serialize` that takes the viewer's role and
returns only what that role may see) rather than returning everything and
filtering client-side.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.roles import (
    ADMIN_ROLES,
    ROLE_CHAPLAIN,
    ROLE_LEADERSHIP,
    ROLE_MENTAL_PERFORMANCE,
    ROLE_NUTRITIONIST,
    ROLE_PTIM,
    ROLE_SCS,
)
from app.core.security import utc_now
from app.models.performance_summary import (
    REVIEW_DUE_DEFAULT_DAYS,
    VISIBILITY_LEVELS,
    PerformanceSummary,
)
from app.models.user import User
from app.schemas.performance_summary import PerformanceSummaryCreate, PerformanceSummaryUpdate
from app.services.audit_log_service import AuditLogService

# Every content field on the entity, in DOCX data-dictionary order.
CONTENT_FIELDS: tuple[str, ...] = (
    "injury_history_summary",
    "limitations_summary",
    "return_to_performance_considerations",
    "nutrition_considerations",
    "sleep_recovery_considerations",
    "medication_allergy_considerations_if_authorized",
)

# DOCX Table 23, "Medical history performance summary" row - each role's
# cell text quoted verbatim above the fields it resolves to.
ROLE_VISIBLE_FIELDS: dict[str, tuple[str, ...]] = {
    # "Yes" - the authoring clinical role sees the whole summary.
    ROLE_PTIM: CONTENT_FIELDS,
    # "Approved limits + RTP guidance"
    ROLE_SCS: ("limitations_summary", "return_to_performance_considerations"),
    # "Relevant nutrition/recovery only"
    ROLE_NUTRITIONIST: ("nutrition_considerations", "sleep_recovery_considerations"),
    # "Relevant stress/sleep/recovery only"
    ROLE_MENTAL_PERFORMANCE: ("sleep_recovery_considerations",),
    # "Only user-selected + approved" - the Purpose/Chaplain pathway is
    # opt-in and carries no clinical remit, so no medical-history content
    # field resolves to it. Metadata only.
    ROLE_CHAPLAIN: (),
    # "Aggregate only" - no individual content, ever.
    ROLE_LEADERSHIP: (),
}

# "Metadata; content only if approved" - Admin/Superadmin.
ADMIN_VISIBLE_FIELDS: tuple[str, ...] = CONTENT_FIELDS

# The DOCX field name itself says "_if_authorized": it is the one field held
# back until the summary reaches the highest real visibility level, even for
# a role whose Table 23 cell would otherwise include it.
MEDICAL_GATED_FIELD = "medication_allergy_considerations_if_authorized"

AUTHORING_ROLES: tuple[str, ...] = (ROLE_PTIM, *ADMIN_ROLES)


class PerformanceSummaryService:
    """Create, update, and role-scope Medical History Performance Summaries."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(
        self, author: User, target_user_id: str, payload: PerformanceSummaryCreate
    ) -> dict[str, Any]:
        """PT/IM (or Admin) authors a summary for an operator. Audit logged."""
        target = await User.get(target_user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        record = PerformanceSummary(
            user_id=target.id,
            created_by=author.id,
            reviewer_role=author.role,
            injury_history_summary=payload.injury_history_summary,
            limitations_summary=payload.limitations_summary,
            return_to_performance_considerations=payload.return_to_performance_considerations,
            nutrition_considerations=payload.nutrition_considerations,
            sleep_recovery_considerations=payload.sleep_recovery_considerations,
            medication_allergy_considerations_if_authorized=(
                payload.medication_allergy_considerations_if_authorized
            ),
            specialist_notes_link=[PydanticObjectId(n) for n in payload.specialist_notes_link],
            expiration_or_review_due_date=(
                payload.expiration_or_review_due_date
                or date.today() + timedelta(days=REVIEW_DUE_DEFAULT_DAYS)
            ),
        )
        await record.insert()

        await self.audit_log_service.record(
            event_type="performance_summary_created",
            actor_id=author.id,
            actor_role=author.role,
            target_entity_type="performance_summary",
            target_entity_id=str(record.id),
            summary_message=f"{author.role} authored a performance summary for {target.email}.",
        )
        return self._serialize(record, viewer=author, is_owner=author.id == target.id)

    async def set_visibility(
        self, actor: User, summary_id: str, payload: PerformanceSummaryUpdate
    ) -> dict[str, Any]:
        """Move a summary's real `approved_visibility_level`. Audit logged."""
        record = await self._get(summary_id)
        if payload.approved_visibility_level not in VISIBILITY_LEVELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Unsupported visibility level.", "allowed": list(VISIBILITY_LEVELS)},
            )

        previous = record.approved_visibility_level
        record.approved_visibility_level = payload.approved_visibility_level
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="performance_summary_visibility_changed",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="performance_summary",
            target_entity_id=str(record.id),
            summary_message=(
                f"Visibility changed from {previous} to {payload.approved_visibility_level}."
            ),
            metadata_payload={
                "previous": previous,
                "new": payload.approved_visibility_level,
            },
        )
        return self._serialize(record, viewer=actor, is_owner=actor.id == record.user_id)

    async def list_for_user(self, viewer: User, target_user_id: str) -> dict[str, Any]:
        """Return an operator's summaries, each scoped to what the viewer may see.

        `target_user_id` may be a route-supplied string - coerced to a real
        `PydanticObjectId` first (Beanie's `==` does not coerce, a bug this
        project has hit three times before).
        """
        if not isinstance(target_user_id, PydanticObjectId):
            target_user_id = PydanticObjectId(target_user_id)

        is_owner = viewer.id == target_user_id
        if not is_owner and not self._may_view(viewer.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role is not authorized to view performance summaries.",
            )

        records = await PerformanceSummary.find(
            PerformanceSummary.user_id == target_user_id
        ).to_list()
        records.sort(key=lambda r: r.review_date, reverse=True)
        return {
            "summaries": [self._serialize(r, viewer=viewer, is_owner=is_owner) for r in records]
        }

    def _may_view(self, role: str) -> bool:
        """Every role with a real Table 23 cell may reach the entity at all."""
        return role in ADMIN_ROLES or role in ROLE_VISIBLE_FIELDS

    async def _get(self, summary_id: str) -> PerformanceSummary:
        record = await PerformanceSummary.get(summary_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Performance summary not found."
            )
        return record

    def _visible_fields(self, viewer_role: str, is_owner: bool) -> tuple[str, ...]:
        """Resolve DOCX Table 23's cell for this viewer into real field names."""
        if is_owner:
            # "Own summary/status" - the operator sees their own guidance,
            # but not the authorized-only medication/allergy content.
            return tuple(f for f in CONTENT_FIELDS if f != MEDICAL_GATED_FIELD)
        if viewer_role in ADMIN_ROLES:
            return ADMIN_VISIBLE_FIELDS
        return ROLE_VISIBLE_FIELDS.get(viewer_role, ())

    def _serialize(
        self, record: PerformanceSummary, *, viewer: User, is_owner: bool
    ) -> dict[str, Any]:
        """Return only the fields DOCX Table 23 grants this viewer.

        Metadata is always present (Table 23's Admin cell is explicitly
        "Metadata; content only if approved", and every other role needs to
        know a summary exists and when it is due for review). Content fields
        are released only once the summary is actually approved - a draft
        exposes nothing to anyone but its author role and Admin.
        """
        approved = record.approved_visibility_level != "draft"
        allowed = set(self._visible_fields(viewer.role, is_owner))

        # An unapproved draft stays with the clinical role authoring it.
        # Admin is deliberately included in this restriction, not exempt
        # from it - DOCX Table 23's Admin cell is literally "Metadata;
        # content only if approved", so oversight access does not mean
        # early access to an unreviewed clinical draft.
        if not approved and viewer.role != ROLE_PTIM:
            allowed = set()

        # The "_if_authorized" field needs the highest level regardless of role.
        if record.approved_visibility_level != "approved_with_medical":
            allowed.discard(MEDICAL_GATED_FIELD)

        payload: dict[str, Any] = {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "created_by": str(record.created_by),
            "reviewer_role": record.reviewer_role,
            "review_date": record.review_date.isoformat(),
            "approved_visibility_level": record.approved_visibility_level,
            "expiration_or_review_due_date": (
                record.expiration_or_review_due_date.isoformat()
                if record.expiration_or_review_due_date
                else None
            ),
            "specialist_notes_link": [str(n) for n in record.specialist_notes_link],
            "created_at": record.created_at.isoformat(),
        }
        for field in CONTENT_FIELDS:
            payload[field] = getattr(record, field) if field in allowed else None
        # Honest, explicit signal that content was withheld rather than absent.
        payload["withheld_fields"] = [f for f in CONTENT_FIELDS if f not in allowed]
        return payload
