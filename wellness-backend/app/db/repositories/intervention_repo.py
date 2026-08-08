"""Repository for intervention memory document operations."""

from datetime import datetime

from beanie import PydanticObjectId

from app.models.intervention_memory import CompletionStatus, InterventionMemory


class InterventionMemoryRepository:
    """Data-access helpers for the intervention_memories collection."""

    async def get_by_user_id(
        self,
        user_id: PydanticObjectId,
    ) -> InterventionMemory | None:
        """Return the memory document for a user, or None if not yet created."""
        return await InterventionMemory.find_one(
            InterventionMemory.user_id == user_id
        )

    async def get_or_create(
        self,
        user_id: PydanticObjectId,
    ) -> InterventionMemory:
        """Return existing memory or create a fresh blank document."""
        existing = await self.get_by_user_id(user_id)
        if existing is not None:
            return existing
        memory = InterventionMemory(user_id=user_id)
        await memory.insert()
        return memory

    async def save_issued(
        self,
        memory: InterventionMemory,
        category: str,
        recommendation: str,
        reason_line: str,
    ) -> InterventionMemory:
        """Record a newly issued recommendation and update memory state."""
        from datetime import date

        # Update last-3 recommendation texts (newest first, cap at 3)
        memory.last_3_recommendations = (
            [recommendation] + memory.last_3_recommendations
        )[:3]

        # Update category tracking
        memory.last_category = category

        # Cache today's output so same-day calls return immediately
        memory.last_issued_date = date.today()
        memory.cached_category = category
        memory.cached_recommendation = recommendation
        memory.cached_reason_line = reason_line

        memory.updated_at = datetime.utcnow()
        await memory.save()
        return memory

    async def record_completion(
        self,
        memory: InterventionMemory,
        status: CompletionStatus,
        category: str,
    ) -> InterventionMemory:
        """Append a completion status and apply escalation to the level map."""
        # Shift completion history (newest first, cap at 3)
        memory.last_3_completions = (
            [status] + memory.last_3_completions
        )[:3]

        # Escalation rules
        current_level = memory.current_levels.get(category, 1)
        if status == "completed":
            # Stay at same level or rotate — no change needed
            pass
        elif status == "partial":
            # Same category, different recommendation — level unchanged
            pass
        elif status == "not_completed":
            # Escalate 1 level (max 3)
            memory.current_levels[category] = min(current_level + 1, 3)
        elif status == "no_response":
            # Fallback — reset to L1 for that category
            memory.current_levels[category] = 1

        # Extra rule: escalate after 2 consecutive failures
        recent = memory.last_3_completions[:2]
        if len(recent) == 2 and all(
            s in ("not_completed", "no_response") for s in recent
        ):
            for cat in memory.current_levels:
                memory.current_levels[cat] = min(
                    memory.current_levels.get(cat, 1) + 1, 3
                )

        memory.updated_at = datetime.utcnow()
        await memory.save()
        return memory
