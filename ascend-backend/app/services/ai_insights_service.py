"""AI insight generation and persistence service."""

from __future__ import annotations

import json
import logging
from typing import Any

from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.core.security import utc_now
from app.models.ai_insight import AIInsight
from app.models.user import User

logger = logging.getLogger(__name__)


class AIInsightsService:
    """Build and persist AI-ready onboarding summary logs."""

    async def generate_onboarding_summary(
        self,
        *,
        user: User,
        ai_payload: dict[str, Any],
        baseline_ops_score: float | None,
        baseline_band: str,
        confidence: str,
        provider_flags: list[dict[str, Any]],
        follow_ups: list[dict[str, Any]],
        insight_type: str = "onboarding_baseline",
        title_subject: str = "Onboarding baseline",
        score_subject: str = "Baseline OPS",
        reuse_existing: bool = True,
    ) -> dict[str, Any]:
        """Create a readiness summary via Claude, with a safe fallback.

        Shared by onboarding baseline completion and daily check-in submission;
        `insight_type`/`title_subject`/`score_subject` distinguish the two flows.
        `reuse_existing` caches the result once generated - correct for onboarding
        (a one-time event) but must be False for recurring flows like daily
        check-in, which need a fresh Claude call and a new record every day.
        """
        existing_record = (
            await self._get_latest_document(user, insight_type=insight_type)
            if reuse_existing
            else None
        )
        if existing_record is not None and existing_record.status != "stub_ready":
            return self._serialize(existing_record)
        settings = get_settings()
        if existing_record is not None and not settings.ai_provider_api_key:
            return self._serialize(existing_record)

        signals = self._derive_signals(provider_flags, follow_ups, baseline_band, confidence)
        action_items = self._derive_actions(signals)
        claude_result = await self._call_claude(
            ai_payload=ai_payload,
            baseline_ops_score=baseline_ops_score,
            baseline_band=baseline_band,
            confidence=confidence,
            signals=signals,
            action_items=action_items,
            title_subject=title_subject,
            score_subject=score_subject,
        )

        title = claude_result.get("title") or self._build_title(
            baseline_band, confidence, subject=title_subject
        )
        summary = claude_result.get("summary") or self._build_summary(
            baseline_ops_score=baseline_ops_score,
            baseline_band=baseline_band,
            confidence=confidence,
            signals=signals,
            action_items=action_items,
            subject=score_subject,
        )
        signals = claude_result.get("signals") or signals
        action_items = claude_result.get("action_items") or action_items
        status = claude_result.get("status", "generated")
        model_name = claude_result.get("model_name", "claude")

        if existing_record is None:
            record = AIInsight(
                user_id=user.id,
                trace_id=ai_payload["trace_id"],
                insight_type=insight_type,
                source_flow=ai_payload["flow"],
                model_name=model_name,
                status=status,
                title=title,
                summary=summary,
                payload=ai_payload,
                signals=signals,
                action_items=action_items,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            await record.insert()
            return self._serialize(record)

        existing_record.trace_id = ai_payload["trace_id"]
        existing_record.source_flow = ai_payload["flow"]
        existing_record.model_name = model_name
        existing_record.status = status
        existing_record.title = title
        existing_record.summary = summary
        existing_record.payload = ai_payload
        existing_record.signals = signals
        existing_record.action_items = action_items
        existing_record.updated_at = utc_now()
        await existing_record.save()
        return self._serialize(existing_record)

    async def get_latest_for_user(
        self,
        user: User,
        insight_type: str = "onboarding_baseline",
    ) -> dict[str, Any] | None:
        """Return the latest saved insight for a user."""
        record = await self._get_latest_document(user, insight_type=insight_type)
        if record is None:
            return None
        return self._serialize(record)

    async def _get_latest_document(
        self,
        user: User,
        insight_type: str = "onboarding_baseline",
    ) -> AIInsight | None:
        """Return the latest AI insight document for a user."""
        records = await AIInsight.find(AIInsight.user_id == user.id).to_list()
        filtered = [item for item in records if item.insight_type == insight_type]
        if not filtered:
            return None
        return max(filtered, key=lambda item: item.created_at)

    def _derive_signals(
        self,
        provider_flags: list[dict[str, Any]],
        follow_ups: list[dict[str, Any]],
        baseline_band: str,
        confidence: str,
    ) -> list[str]:
        """Convert onboarding data into compact AI-facing signals."""
        signals: list[str] = [f"baseline_band:{baseline_band}", f"confidence:{confidence}"]
        if any(flag.get("provider_route") == "PT/IM" for flag in provider_flags):
            signals.append("ptim_review")
        if any(item.get("follow_up_type") == "role_sheet" for item in follow_ups):
            signals.append("support_pathways_selected")
        if any(item.get("follow_up_type") == "text_sheet" for item in follow_ups):
            signals.append("goal_capture_present")
        if any(item.get("follow_up_type") == "severity_sheet" for item in follow_ups):
            signals.append("severity_followup_present")
        return list(dict.fromkeys(signals))

    def _derive_actions(self, signals: list[str]) -> list[str]:
        """Turn signals into a small set of next-step actions."""
        actions = ["Review onboarding baseline with assigned providers"]
        if "ptim_review" in signals:
            actions.append("Prioritize PT/IM follow-up")
        if "support_pathways_selected" in signals:
            actions.append("Confirm support pathway preferences")
        if "goal_capture_present" in signals:
            actions.append("Track top readiness goal in dashboard")
        return actions

    def _build_title(
        self, baseline_band: str, confidence: str, *, subject: str = "Onboarding baseline"
    ) -> str:
        """Build a short dashboard-ready title."""
        return f"{subject} is {baseline_band.replace('_', ' ')} ({confidence} confidence)"

    def _build_summary(
        self,
        *,
        baseline_ops_score: float | None,
        baseline_band: str,
        confidence: str,
        signals: list[str],
        action_items: list[str],
        subject: str = "Baseline OPS",
    ) -> str:
        """Build a deterministic summary stub for dashboard/provider views."""
        score_text = "unavailable" if baseline_ops_score is None else f"{baseline_ops_score:.2f}"
        return (
            f"{subject} {score_text} with {confidence} confidence. "
            f"Primary band: {baseline_band.replace('_', ' ')}. "
            f"Signals: {', '.join(signals) or 'none'}. "
            f"Actions: {', '.join(action_items) or 'none'}."
        )

    async def _call_claude(
        self,
        *,
        ai_payload: dict[str, Any],
        baseline_ops_score: float | None,
        baseline_band: str,
        confidence: str,
        signals: list[str],
        action_items: list[str],
        title_subject: str = "Onboarding baseline",
        score_subject: str = "Baseline OPS",
    ) -> dict[str, Any]:
        """Call Claude for a structured readiness summary, with fallback safety."""
        settings = get_settings()
        if not settings.ai_provider_api_key:
            return {
                "status": "stub_ready",
                "model_name": "stub-summary-v1",
                "title": self._build_title(baseline_band, confidence, subject=title_subject),
                "summary": self._build_summary(
                    baseline_ops_score=baseline_ops_score,
                    baseline_band=baseline_band,
                    confidence=confidence,
                    signals=signals,
                    action_items=action_items,
                    subject=score_subject,
                ),
                "signals": signals,
                "action_items": action_items,
            }

        client = AsyncAnthropic(api_key=settings.ai_provider_api_key)
        prompt = self._build_claude_prompt(
            ai_payload=ai_payload,
            baseline_ops_score=baseline_ops_score,
            baseline_band=baseline_band,
            confidence=confidence,
            signals=signals,
            action_items=action_items,
        )
        try:
            response = await client.messages.create(
                model=settings.anthropic_model,
                max_tokens=700,
                temperature=0,
                system=(
                    "You are an Ascend readiness summarizer. "
                    "Return only valid JSON with exactly these keys: title, summary, signals, action_items. "
                    "Keep the summary short, factual, and provider-safe."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ).strip()
            parsed = json.loads(self._strip_json_code_fence(text))
            if not isinstance(parsed, dict):
                raise ValueError("Claude response was not a JSON object.")
            # status/model_name are internal bookkeeping, not model output - set them
            # unconditionally rather than setdefault, since Claude sometimes fills
            # these keys with unrelated content (e.g. echoing the readiness band).
            parsed["status"] = "generated"
            parsed["model_name"] = settings.anthropic_model
            parsed.setdefault("signals", signals)
            parsed.setdefault("action_items", action_items)
            return parsed
        except Exception:
            logger.warning("Claude summary call failed; falling back to stub summary.", exc_info=True)
            return {
                "status": "stub_ready",
                "model_name": "stub-summary-v1",
                "title": self._build_title(baseline_band, confidence, subject=title_subject),
                "summary": self._build_summary(
                    baseline_ops_score=baseline_ops_score,
                    baseline_band=baseline_band,
                    confidence=confidence,
                    signals=signals,
                    action_items=action_items,
                    subject=score_subject,
                ),
                "signals": signals,
                "action_items": action_items,
            }

    def _strip_json_code_fence(self, text: str) -> str:
        """Strip a ```json ... ``` (or bare ``` ... ```) fence Claude commonly wraps JSON in.

        `json.loads` has no tolerance for this, so without stripping it every
        real Claude call fails to parse and silently falls back to the stub -
        the exact bug found in production testing (2026-08-06).
        """
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped[3:]
            if stripped.startswith("json"):
                stripped = stripped[4:]
            if stripped.endswith("```"):
                stripped = stripped[:-3]
            stripped = stripped.strip()
        return stripped

    def _build_claude_prompt(
        self,
        *,
        ai_payload: dict[str, Any],
        baseline_ops_score: float | None,
        baseline_band: str,
        confidence: str,
        signals: list[str],
        action_items: list[str],
    ) -> str:
        """Build a compact prompt for Claude summary generation."""
        return json.dumps(
            {
                "flow": ai_payload.get("flow"),
                "trace_id": ai_payload.get("trace_id"),
                "baseline_ops_score": baseline_ops_score,
                "baseline_band": baseline_band,
                "confidence": confidence,
                "signals": signals,
                "action_items": action_items,
                "component_scores": ai_payload.get("component_scores", {}),
                "flags": ai_payload.get("flags", []),
                "follow_ups": ai_payload.get("follow_ups", []),
            },
            ensure_ascii=True,
        )

    def _serialize(self, record: AIInsight) -> dict[str, Any]:
        """Convert a stored insight to a transport-safe dict."""
        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "trace_id": record.trace_id,
            "insight_type": record.insight_type,
            "source_flow": record.source_flow,
            "model_name": record.model_name,
            "status": record.status,
            "title": record.title,
            "summary": record.summary,
            "signals": record.signals,
            "action_items": record.action_items,
            "payload": record.payload,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
