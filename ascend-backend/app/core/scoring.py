"""Scoring helpers for Ascend onboarding and readiness flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

READINESS_COMPONENT_WEIGHTS: dict[str, float] = {
    "Physical Readiness": 0.25,
    "Sleep Readiness": 0.20,
    "Mental Readiness": 0.20,
    "Nutritional Readiness": 0.20,
    "Spiritual Readiness": 0.15,
}


@dataclass(slots=True)
class QuestionScore:
    """Normalized score for a single answer."""

    raw_score_1_to_4: int | None
    numeric_score_100: float | None
    reverse_scored: bool
    scoreable: bool


def score_ordered_answer(
    answer_index: int,
    option_count: int,
    *,
    reverse_scored: bool = False,
    scoreable: bool = True,
) -> QuestionScore:
    """Convert an ordered answer selection into a 1-4 / 25-100 score."""
    if not scoreable:
        return QuestionScore(None, None, reverse_scored, False)

    if option_count < 2:
        raise ValueError("Scoreable questions require at least two options.")

    if option_count == 4:
        raw_score = answer_index + 1
        if reverse_scored:
            raw_score = 4 - answer_index
        numeric_score = float(raw_score * 25)
        return QuestionScore(raw_score, numeric_score, reverse_scored, True)

    raw_score = answer_index + 1
    if reverse_scored:
        raw_score = option_count - answer_index
    numeric_score = round((raw_score / option_count) * 100, 2)
    return QuestionScore(raw_score, numeric_score, reverse_scored, True)


def calculate_component_score(scores_100: list[float]) -> float | None:
    """Return the component average on the 100-point scale."""
    if not scores_100:
        return None
    return round(sum(scores_100) / len(scores_100), 2)


def calculate_ops(
    component_scores: dict[str, float], weights: dict[str, float] | None = None
) -> float | None:
    """Calculate the weighted onboarding or readiness OPS.

    `weights` defaults to the DOCX baseline (`READINESS_COMPONENT_WEIGHTS`)
    but can be overridden with an admin-configured `ScoringConfig`
    (`app/services/scoring_config_service.py`) without changing this
    function's math.
    """
    weights = weights or READINESS_COMPONENT_WEIGHTS
    required_components = [key for key in weights if key in component_scores]
    if len(required_components) < 3:
        return None

    total = 0.0
    for component, weight in weights.items():
        score = component_scores.get(component)
        if score is None:
            continue
        total += score * weight
    return round(total, 2)


def calculate_confidence(
    component_scores: dict[str, float | None],
    stale_flags: dict[str, bool] | None = None,
) -> str:
    """Derive a simple confidence label for OPS display."""
    stale_flags = stale_flags or {}
    valid_components = sum(1 for score in component_scores.values() if score is not None)
    stale_count = sum(1 for value in stale_flags.values() if value)
    if valid_components >= 5 and stale_count == 0:
        return "high"
    if valid_components >= 3 and stale_count <= 1:
        return "medium"
    return "low"


DEFAULT_BAND_THRESHOLDS: dict[str, float] = {
    "Ready": 85.0,
    "Monitor": 70.0,
    "Caution": 55.0,
    "Action Needed": 40.0,
}


def build_score_band(score_100: float | None, thresholds: dict[str, float] | None = None) -> str:
    """Convert an OPS score into the DOCX-defined user-facing readiness band.

    Ranges and labels come from the DOCX "Readiness Bands and User-Facing
    Labels" table: 85-100 Ready, 70-84 Monitor, 55-69 Caution, 40-54 Action
    Needed, below 40 High Priority. `thresholds` can be overridden with an
    admin-configured `ScoringConfig`.
    """
    if score_100 is None:
        return "Unavailable"
    thresholds = thresholds or DEFAULT_BAND_THRESHOLDS
    if score_100 >= thresholds["Ready"]:
        return "Ready"
    if score_100 >= thresholds["Monitor"]:
        return "Monitor"
    if score_100 >= thresholds["Caution"]:
        return "Caution"
    if score_100 >= thresholds["Action Needed"]:
        return "Action Needed"
    return "High Priority"


BAND_MEANINGS: dict[str, str] = {
    "Ready": "You appear ready to train or perform as planned.",
    "Monitor": "You are generally ready, but one area may need attention.",
    "Caution": "A readiness area is limiting performance or recovery.",
    "Action Needed": "Support may be needed to protect readiness and progress.",
    "High Priority": "A significant readiness concern is present.",
    "Unavailable": "Not enough data yet to show a readiness band.",
}


def get_band_meaning(band: str) -> str:
    """Return the DOCX-defined user-facing meaning text for a readiness band."""
    return BAND_MEANINGS.get(band, "")


def normalize_component_name(category: str) -> str:
    """Map question categories to readiness components."""
    mapping = {
        "PHYSICAL": "Physical Readiness",
        "NUTRITIONAL": "Nutritional Readiness",
        "MENTAL": "Mental Readiness",
        "SPIRITUAL": "Spiritual Readiness",
        "SLEEP": "Sleep Readiness",
    }
    return mapping.get(category.strip().upper(), category)


def build_ai_payload(
    *,
    trace_id: str,
    user_id: str,
    answers: list[dict[str, Any]],
    component_scores: dict[str, float | None],
    ops_score: float | None,
    confidence: str,
    flags: list[dict[str, Any]],
    follow_ups: list[dict[str, Any]],
    flow: str = "onboarding_baseline",
) -> dict[str, Any]:
    """Build a structured AI payload for later summarization/routing."""
    return {
        "trace_id": trace_id,
        "user_id": user_id,
        "flow": flow,
        "component_scores": component_scores,
        "ops_score": ops_score,
        "confidence": confidence,
        "answers": answers,
        "flags": flags,
        "follow_ups": follow_ups,
    }
