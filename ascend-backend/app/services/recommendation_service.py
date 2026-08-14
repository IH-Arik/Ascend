"""Recommendation engine service (DOCX section 4).

Evaluates today's component scores against yesterday's, applies the DOCX
trigger rules (<55 once = high severity, <70 repeated across two
consecutive check-ins = moderate severity), and surfaces one recommendation
at a time. A new recommendation is only created when none is active for the
same component/severity, or when severity has increased - matching the
DOCX rule to avoid repeating the same recommendation unless severity rises.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.recommendation_rules import COMPONENT_PRIORITY_ORDER
from app.core.recommendation_rules import HIGH_THRESHOLD
from app.core.recommendation_rules import MODERATE_THRESHOLD
from app.core.recommendation_rules import get_recommendation_rule
from app.core.roles import ROLE_PTIM, ROLE_SCS, SPECIALIST_ROLES
from app.core.security import utc_now

# Approximate mapping onto the DOCX's L0-L5 routing taxonomy
# (`app/core/routing_levels.py`) - see that module's docstring for why this
# is directional context, not a precise re-derivation of every L-level's
# multi-day pattern trigger.
SEVERITY_TO_ROUTE_LEVEL = {"moderate": "L2", "high": "L4"}
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.recommendation import AssignActionRequest
from app.services.audit_log_service import AuditLogService
from app.services.notification_service import NotificationService
from app.services.recommendation_threshold_config_service import (
    RecommendationThresholdConfigService,
)

SEVERITY_RANK = {"moderate": 1, "high": 2, "assigned": 3}


class RecommendationService:
    """Generate, list, dismiss, and complete readiness recommendations."""

    def __init__(self) -> None:
        self.notification_service = NotificationService()
        self.audit_log_service = AuditLogService()
        self.threshold_config_service = RecommendationThresholdConfigService()

    async def evaluate_and_generate(
        self,
        user: User,
        component_scores: dict[str, float | None],
        previous_component_scores: dict[str, float | None] | None,
    ) -> dict[str, Any] | None:
        """Evaluate today's scores and create a new recommendation if triggered."""
        previous_component_scores = previous_component_scores or {}
        active_thresholds = await self.threshold_config_service.get_active_thresholds()
        high_threshold, moderate_threshold = active_thresholds or (HIGH_THRESHOLD, MODERATE_THRESHOLD)
        candidate = self._pick_candidate(
            component_scores, previous_component_scores, high_threshold, moderate_threshold
        )
        if candidate is None:
            return None

        component, severity, score = candidate
        existing_active = await self._get_active(user)
        if existing_active is not None:
            same_trigger = (
                existing_active.readiness_component == component
                and existing_active.severity == severity
            )
            if same_trigger:
                return await self._serialize(existing_active)
            if SEVERITY_RANK[severity] <= SEVERITY_RANK[existing_active.severity]:
                # Keep showing the current (equal-or-worse) recommendation; one at a time.
                return await self._serialize(existing_active)
            existing_active.status = "superseded"
            existing_active.updated_at = utc_now()
            await existing_active.save()

        rule = get_recommendation_rule(component)
        if rule is None:
            return None
        copy = rule[severity]
        threshold_level = high_threshold if severity == "high" else moderate_threshold
        trigger_reason = (
            f"{component} score {score:.0f} is below {threshold_level:.0f}"
            + (" (repeated across two check-ins)." if severity == "moderate" else ".")
        )

        record = Recommendation(
            user_id=user.id,
            readiness_component=component,
            severity=severity,
            score_band=severity,
            threshold_level=threshold_level,
            source_component_score=score,
            trigger_reason=trigger_reason,
            signal_label=rule["signal_label"],
            title=copy["title"],
            body=copy["body"],
            provider_action_type=rule["provider_action_type"],
            specialist_route=rule.get("specialist_route"),
            route_level=SEVERITY_TO_ROUTE_LEVEL.get(severity),
            plan_link_category=(
                "user_only_recommendation"
                if not rule.get("specialist_route")
                else "scs_recommendation"
                if rule["provider_action_type"] == "scs_recommendation"
                else "specialist_routing_item"
            ),
            follow_up_timeline=rule["follow_up_timeline"],
        )
        await record.insert()
        await self.notification_service.notify(
            user.id,
            family="assigned_action_reminders",
            title=record.title,
            body=record.body,
            related_entity_type="recommendation",
            related_entity_id=str(record.id),
        )
        return await self._serialize(record)

    async def assign_action(
        self,
        user: User,
        payload: AssignActionRequest,
        assigned_by: Any,
        assigned_by_role: str = "",
    ) -> dict[str, Any]:
        """Assign a provider-authored action (the "Assigned action" screen)."""
        if payload.readiness_component not in COMPONENT_PRIORITY_ORDER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Unknown readiness component.",
                    "allowed": COMPONENT_PRIORITY_ORDER,
                },
            )
        existing_active = await self._get_active(user)
        if existing_active is not None:
            existing_active.status = "superseded"
            existing_active.updated_at = utc_now()
            await existing_active.save()

        if payload.is_joint_coordination:
            plan_link_category = "joint_coordination_item"
        elif payload.assigned_provider_role == ROLE_SCS:
            plan_link_category = "scs_recommendation"
        elif payload.assigned_provider_role == ROLE_PTIM:
            plan_link_category = "ptim_review_item"
        elif payload.assigned_provider_role in SPECIALIST_ROLES:
            plan_link_category = "specialist_routing_item"
        else:
            plan_link_category = "user_only_recommendation"

        record = Recommendation(
            user_id=user.id,
            readiness_component=payload.readiness_component,
            severity="assigned",
            score_band="assigned",
            threshold_level=0.0,
            trigger_reason=f"Assigned by {payload.assigned_provider_name} ({payload.assigned_provider_role})",
            signal_label=payload.readiness_component.replace(" Readiness", ""),
            title=payload.title,
            body=payload.instructions,
            provider_action_type="provider_assigned_plan_link",
            specialist_route=payload.assigned_provider_role,
            route_level=None,  # a human provider decided directly - not an automatic L-level
            plan_link_category=plan_link_category,
            follow_up_timeline=payload.follow_up_timeline,
            assigned_provider_name=payload.assigned_provider_name,
            assigned_provider_role=payload.assigned_provider_role,
            due_date=payload.due_date,
            instructions=payload.instructions,
            steps=[step.model_dump() for step in payload.steps],
            assigned_by=assigned_by,
        )
        await record.insert()
        await self.notification_service.notify(
            user.id,
            family="assigned_action_reminders",
            title=record.title,
            body=f"Assigned by {payload.assigned_provider_name} ({payload.assigned_provider_role})",
            related_entity_type="recommendation",
            related_entity_id=str(record.id),
        )
        # Closes a real, previously-unimplemented gap: `docs/AUDIT_LOG_RULES.md`
        # explicitly requires auditing "recommendation assignment or override".
        await self.audit_log_service.record(
            event_type="recommendation_assigned",
            actor_id=assigned_by,
            actor_role=assigned_by_role,
            target_entity_type="recommendation",
            target_entity_id=str(record.id),
            summary_message=f"Assigned action '{record.title}' to {user.email}.",
            metadata_payload={"readiness_component": payload.readiness_component},
        )
        return await self._serialize(record)

    async def get_by_id(self, user: User, recommendation_id: str) -> dict[str, Any]:
        """Return a single recommendation/assigned action by id (Assigned Action screen)."""
        record = await self._get_owned(user, recommendation_id)
        return await self._serialize(record)

    async def complete_step(
        self, user: User, recommendation_id: str, step_index: int
    ) -> dict[str, Any]:
        """Mark a single step of an assigned action as completed."""
        record = await self._get_owned(user, recommendation_id)
        if step_index < 0 or step_index >= len(record.steps):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Step not found.",
            )
        record.steps[step_index]["completed"] = True
        record.updated_at = utc_now()
        await record.save()
        return await self._serialize(record)

    async def get_active_for_user(self, user: User) -> dict[str, Any] | None:
        """Return the current active recommendation for a user, if any."""
        record = await self._get_active(user)
        if record is None:
            return None
        return await self._serialize(record)

    async def dismiss(self, user: User, recommendation_id: str) -> dict[str, Any]:
        """Dismiss an active recommendation."""
        record = await self._get_owned(user, recommendation_id)
        record.status = "dismissed"
        record.updated_at = utc_now()
        await record.save()
        await self.audit_log_service.record(
            event_type="recommendation_dismissed",
            actor_id=user.id,
            actor_role=user.role,
            target_entity_type="recommendation",
            target_entity_id=str(record.id),
            summary_message=f"Dismissed recommendation '{record.title}'.",
        )
        return await self._serialize(record)

    async def complete(self, user: User, recommendation_id: str) -> dict[str, Any]:
        """Mark a recommendation's action as completed."""
        record = await self._get_owned(user, recommendation_id)
        record.status = "completed"
        record.updated_at = utc_now()
        await record.save()
        await self.audit_log_service.record(
            event_type="recommendation_completed",
            actor_id=user.id,
            actor_role=user.role,
            target_entity_type="recommendation",
            target_entity_id=str(record.id),
            summary_message=f"Completed recommendation '{record.title}'.",
        )
        return await self._serialize(record)

    async def _get_owned(self, user: User, recommendation_id: str) -> Recommendation:
        """Return a recommendation owned by the user, or raise 404."""
        record = await Recommendation.get(recommendation_id)
        if record is None or record.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recommendation not found.",
            )
        return record

    async def _get_active(self, user: User) -> Recommendation | None:
        """Return the most recent active recommendation for a user."""
        records = await Recommendation.find(
            Recommendation.user_id == user.id, Recommendation.status == "active"
        ).to_list()
        if not records:
            return None
        return max(records, key=lambda item: item.created_at)

    def _pick_candidate(
        self,
        component_scores: dict[str, float | None],
        previous_component_scores: dict[str, float | None],
        high_threshold: float = HIGH_THRESHOLD,
        moderate_threshold: float = MODERATE_THRESHOLD,
    ) -> tuple[str, str, float] | None:
        """Return the single worst-triggering (component, severity, score) or None."""
        triggered: list[tuple[str, str, float]] = []
        for component in COMPONENT_PRIORITY_ORDER:
            score = component_scores.get(component)
            if score is None:
                continue
            if score < high_threshold:
                triggered.append((component, "high", score))
                continue
            previous_score = previous_component_scores.get(component)
            if score < moderate_threshold and previous_score is not None and previous_score < moderate_threshold:
                triggered.append((component, "moderate", score))

        if not triggered:
            return None

        triggered.sort(
            key=lambda item: (
                -SEVERITY_RANK[item[1]],
                COMPONENT_PRIORITY_ORDER.index(item[0]),
            )
        )
        return triggered[0]

    async def send_for_signoff(self, user: User, recommendation_id: str, actor: Any, actor_role: str) -> dict[str, Any]:
        """SCS, PT/IM, or Admin sends a joint-coordination recommendation for PT/IM signoff."""
        record = await self._get_owned(user, recommendation_id)
        if record.plan_link_category != "joint_coordination_item":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only a joint coordination item can be sent for signoff.",
            )
        record.coordination_signoff_status = "pending_signoff"
        record.updated_at = utc_now()
        await record.save()
        await self.audit_log_service.record(
            event_type="coordination_sent_for_signoff",
            actor_id=actor,
            actor_role=actor_role,
            target_entity_type="recommendation",
            target_entity_id=str(record.id),
            summary_message=f"Sent '{record.title}' for PT/IM signoff.",
        )
        return await self._serialize(record)

    async def sign_off(self, user: User, recommendation_id: str, actor: Any, actor_role: str) -> dict[str, Any]:
        """PT/IM (or Admin) signs off a coordination item previously sent for signoff."""
        record = await self._get_owned(user, recommendation_id)
        if record.coordination_signoff_status != "pending_signoff":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This item has not been sent for signoff.",
            )
        record.coordination_signoff_status = "signed_off"
        record.signed_off_by = actor
        record.signed_off_at = utc_now()
        record.updated_at = utc_now()
        await record.save()
        await self.audit_log_service.record(
            event_type="coordination_signed_off",
            actor_id=actor,
            actor_role=actor_role,
            target_entity_type="recommendation",
            target_entity_id=str(record.id),
            summary_message=f"Signed off '{record.title}'.",
        )
        return await self._serialize(record)

    async def _serialize(self, record: Recommendation) -> dict[str, Any]:
        """Convert a stored recommendation to a transport-safe dict."""
        signed_off_by_user = await User.get(record.signed_off_by) if record.signed_off_by else None
        return {
            "id": str(record.id),
            "readiness_component": record.readiness_component,
            "severity": record.severity,
            "signal_label": record.signal_label,
            "title": record.title,
            "body": record.body,
            "provider_action_type": record.provider_action_type,
            "specialist_route": record.specialist_route,
            "route_level": record.route_level,
            "plan_link_category": record.plan_link_category,
            "coordination_signoff_status": record.coordination_signoff_status,
            "signed_off_by_name": signed_off_by_user.full_name if signed_off_by_user else None,
            "signed_off_at": record.signed_off_at.isoformat() if record.signed_off_at else None,
            "follow_up_timeline": record.follow_up_timeline,
            "trigger_reason": record.trigger_reason,
            "status": record.status,
            "assigned_provider_name": record.assigned_provider_name,
            "assigned_provider_role": record.assigned_provider_role,
            "due_date": record.due_date.isoformat() if record.due_date else None,
            "instructions": record.instructions,
            "steps": record.steps,
            "created_at": record.created_at.isoformat(),
        }
