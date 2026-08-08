"""Scoring service implementation."""

from app.models.assessment import Answer
from app.models.score import DimensionScore


class ScoringService:
    """Service for wellness and performance scoring."""

    DAILY_PURPOSE_CAP_FACTOR = 0.70
    MONTHLY_PHYSICAL_CAP_FACTOR = 0.65
    WEEKLY_MORALE_CAP_FACTOR = 0.80

    GLOBAL_DRIVER_WEIGHTS = {
        "RC": 0.30,
        "MR": 0.25,
        "PC": 0.20,
        "PA": 0.15,
        "MC": 0.10,
    }
    ASSESSMENT_DRIVER_WEIGHTS = {
        "daily": {"RC": 0.40, "MR": 0.25, "PC": 0.20, "PA": 0.10, "MC": 0.00},
        "weekly": {"RC": 0.20, "MR": 0.25, "PC": 0.25, "PA": 0.20, "MC": 0.10},
        "monthly": {"RC": 0.20, "MR": 0.25, "PC": 0.15, "PA": 0.20, "MC": 0.20},
        "onboarding": {"RC": 0.25, "MR": 0.25, "PC": 0.20, "PA": 0.15, "MC": 0.15},
    }
    DIMENSIONS = ("PC", "MR", "MC", "PA", "RC")

    async def calculate_dimension_scores(self, answers: list[Answer]) -> DimensionScore:
        """Calculate dimension scores from weighted answer rules."""
        if not answers:
            return DimensionScore(PC=0.0, MR=0.0, MC=0.0, PA=0.0, RC=0.0)

        question_ids = {str(answer.question_id) for answer in answers}
        if all(question_id.startswith("dc_") for question_id in question_ids):
            return self._calculate_daily_scores(answers)
        if all(question_id.startswith("wc_") for question_id in question_ids):
            return self._calculate_weekly_scores(answers)
        if all(question_id.startswith("mc_") for question_id in question_ids):
            return self._calculate_monthly_scores(answers)
        return self._calculate_onboarding_scores(answers)

    async def calculate_overall_score(
        self,
        dimension_scores: DimensionScore,
        assessment_kind: str = "global",
    ) -> float:
        """Calculate an overall score from normalized dimension scores."""
        weights = self.ASSESSMENT_DRIVER_WEIGHTS.get(
            assessment_kind,
            self.GLOBAL_DRIVER_WEIGHTS,
        )
        return round(
            (dimension_scores.RC * weights["RC"])
            + (dimension_scores.MR * weights["MR"])
            + (dimension_scores.PC * weights["PC"])
            + (dimension_scores.PA * weights["PA"])
            + (dimension_scores.MC * weights["MC"]),
            2,
        )

    def map_option_to_score(
        self,
        option_index: int,
        option_count: int,
        reverse_scored: bool = False,
    ) -> float:
        """Convert an ordered option index into a 0-100 score."""
        if option_count <= 1:
            return 100.0
        score = round((option_index / (option_count - 1)) * 100, 2)
        return round(100.0 - score, 2) if reverse_scored else score

    async def classify_condition(self, overall_score: float) -> str:
        """Classify the user's condition from the overall score."""
        if overall_score >= 85:
            return "Optimal"
        if overall_score >= 70:
            return "Stable"
        if overall_score >= 55:
            return "Strained"
        if overall_score >= 40:
            return "High Risk"
        return "Critical"

    def apply_baseline_decay(self, score: float, days_since_onboarding: int) -> float:
        """Apply onboarding decay toward neutral as the baseline ages."""
        if days_since_onboarding <= 14:
            decay = 0.10
        elif days_since_onboarding <= 30:
            decay = 0.07
        elif days_since_onboarding <= 60:
            decay = 0.04
        else:
            decay = 0.02
        return round(50.0 + ((score - 50.0) * (1.0 - decay)), 2)

    def _calculate_daily_scores(self, answers: list[Answer]) -> DimensionScore:
        answer_map = self._by_id(answers)
        recovery_raw = self._weighted_average(
            answer_map,
            {"dc_1": 40, "dc_5": 35, "dc_6": 25},
        )
        stress_raw = answer_map.get("dc_3")
        moderated_stress = (
            self._clamp((0.80 * stress_raw) + (0.20 * recovery_raw))
            if stress_raw is not None
            else None
        )
        mental_score = self._weighted_values(
            [
                (answer_map.get("dc_2"), 45),
                (moderated_stress, 55),
            ]
        )
        purpose_raw = answer_map.get("dc_4", 0.0)
        physical_score = self._weighted_average(
            answer_map,
            {"dc_8": 55, "dc_7": 45},
        )
        return DimensionScore(
            PC=round(physical_score, 2),
            MR=round(mental_score, 2),
            MC=0.0,
            PA=round(self._apply_centered_cap(purpose_raw, self.DAILY_PURPOSE_CAP_FACTOR), 2),
            RC=round(recovery_raw, 2),
        )

    def _calculate_weekly_scores(self, answers: list[Answer]) -> DimensionScore:
        answer_map = self._by_id(answers)
        stress_raw = answer_map.get("wc_3")
        recovery_score = answer_map.get("wc_6", 0.0)
        moderated_stress = (
            self._apply_buffered_stress_adjustment(
                stress_raw,
                [answer_map.get("wc_1"), answer_map.get("wc_2")],
                [recovery_score],
            )
            if stress_raw is not None
            else None
        )
        mental_score = self._weighted_values(
            [
                (answer_map.get("wc_1"), 35),
                (answer_map.get("wc_2"), 35),
                (moderated_stress, 30),
            ]
        )
        purpose_score = self._weighted_average(
            answer_map,
            {"wc_4": 50, "wc_8": 50},
        )
        physical_score = self._weighted_average(
            answer_map,
            {"wc_5": 30, "wc_6": 30, "wc_10": 25, "wc_7": 15},
        )
        morale_raw = answer_map.get("wc_9", 0.0)
        morale_score = self._apply_centered_cap(morale_raw, self.WEEKLY_MORALE_CAP_FACTOR)
        return DimensionScore(
            PC=round(physical_score, 2),
            MR=round(mental_score, 2),
            MC=round(morale_score, 2),
            PA=round(purpose_score, 2),
            RC=round(recovery_score, 2),
        )

    def _calculate_monthly_scores(self, answers: list[Answer]) -> DimensionScore:
        answer_map = self._by_id(answers)
        recovery_score = self._weighted_average(
            answer_map,
            {"mc_1": 35, "mc_2": 35, "mc_4": 30},
        )
        mental_score = self._weighted_average(
            answer_map,
            {"mc_5": 40, "mc_6": 30, "mc_7": 30},
        )
        purpose_score = self._weighted_average(
            answer_map,
            {"mc_8": 35, "mc_9": 35, "mc_10": 30},
        )
        physical_raw = answer_map.get("mc_3", 0.0)
        morale_score = self._weighted_average(
            answer_map,
            {"mc_11": 50, "mc_12": 50},
        )
        return DimensionScore(
            PC=round(self._apply_centered_cap(physical_raw, self.MONTHLY_PHYSICAL_CAP_FACTOR), 2),
            MR=round(mental_score, 2),
            MC=round(morale_score, 2),
            PA=round(purpose_score, 2),
            RC=round(recovery_score, 2),
        )

    def _calculate_onboarding_scores(self, answers: list[Answer]) -> DimensionScore:
        text_map = self._by_text(answers)
        stress_raw = text_map.get("How frequently do you experience high stress?")
        moderated_stress = (
            self._apply_buffered_stress_adjustment(
                stress_raw,
                [
                    text_map.get("How stable are your emotions during pressure or challenges?"),
                    text_map.get("How confident are you in handling unexpected problems?"),
                    text_map.get("How well do you recover mentally after stressful situations?"),
                    text_map.get("How often do you practice stress management (meditation, breathing, etc.)?"),
                ],
                [
                    text_map.get("How would you describe your energy on most days?"),
                    text_map.get("How rested do you usually feel after sleep?"),
                    text_map.get("How many hours do you usually sleep on weeknights?"),
                    text_map.get("How fatigued do you feel after a typical workday?"),
                ],
            )
            if stress_raw is not None
            else None
        )
        recovery_score = self._weighted_values(
            [
                (text_map.get("How would you describe your energy on most days?"), 20),
                (text_map.get("How rested do you usually feel after sleep?"), 20),
                (text_map.get("How many hours do you usually sleep on weeknights?"), 20),
                (text_map.get("How consistent is your sleep schedule?"), 20),
                (text_map.get("How fatigued do you feel after a typical workday?"), 20),
            ]
        )
        mental_score = self._weighted_values(
            [
                (text_map.get("How well can you stay focused during your workday?"), 15),
                (moderated_stress, 20),
                (text_map.get("How stable are your emotions during pressure or challenges?"), 20),
                (text_map.get("How confident are you in handling unexpected problems?"), 15),
                (text_map.get("How well do you recover mentally after stressful situations?"), 15),
                (text_map.get("How often do you practice stress management (meditation, breathing, etc.)?"), 15),
            ]
        )
        purpose_score = self._weighted_values(
            [
                (text_map.get("How motivated do you feel toward your daily responsibilities?"), 40),
                (text_map.get("How aligned do you feel with your priorities and direction?"), 35),
                (text_map.get("How manageable is your current workload?"), 25),
            ]
        )
        physical_score = self._weighted_values(
            [
                (text_map.get("How would you rate your overall health?"), 15),
                (text_map.get("How consistent is your physical activity?"), 20),
                (text_map.get("How often do you eat balanced meals?"), 15),
                (text_map.get("How often do you eat processed or fast foods?"), 15),
                (text_map.get("How often do you eat fruits and vegetables?"), 15),
                (text_map.get("How well do you stay hydrated during the day?"), 10),
                (text_map.get("How often do you take breaks during long work periods?"), 10),
            ]
        )
        morale_score = self._weighted_values(
            [
                (text_map.get("How supported and connected do you feel in your work environment?"), 40),
                (text_map.get("How often do you receive recognition for your work?"), 25),
                (text_map.get("How connected do you feel with your team or peers?"), 25),
                (text_map.get("How much outside stress affects your daily life?"), 10),
            ]
        )
        return DimensionScore(
            PC=round(physical_score, 2),
            MR=round(mental_score, 2),
            MC=round(morale_score, 2),
            PA=round(purpose_score, 2),
            RC=round(recovery_score, 2),
        )

    def _apply_centered_cap(self, raw_score: float, factor: float) -> float:
        if raw_score <= 25.0:
            return round(raw_score, 2)
        return round(50.0 + ((raw_score - 50.0) * factor), 2)

    def _apply_buffered_stress_adjustment(
        self,
        stress_score: float | None,
        coping_values: list[float | None],
        recovery_values: list[float | None],
    ) -> float:
        if stress_score is None:
            return 50.0
        coping = self._average([value for value in coping_values if value is not None]) or 0.0
        recovery = self._average([value for value in recovery_values if value is not None]) or 0.0
        coping_buffer = coping / 100.0
        recovery_buffer = recovery / 100.0
        modifier = 0.60 + (0.20 * coping_buffer) + (0.20 * recovery_buffer)
        burden = 100.0 - stress_score
        adjusted_burden = burden * modifier
        adjusted_stress = 100.0 - adjusted_burden
        return round(self._clamp(adjusted_stress), 2)

    def _weighted_average(
        self,
        answer_map: dict[str, float],
        weights: dict[str, int],
    ) -> float:
        return self._weighted_values([(answer_map.get(key), weight) for key, weight in weights.items()])

    def _weighted_values(
        self,
        values: list[tuple[float | None, int]],
    ) -> float:
        available = [(value, weight) for value, weight in values if value is not None]
        if not available:
            return 0.0
        total_weight = sum(weight for _, weight in available)
        weighted_sum = sum(value * weight for value, weight in available)
        return weighted_sum / total_weight

    def _by_id(self, answers: list[Answer]) -> dict[str, float]:
        return {str(answer.question_id): answer.numeric_value for answer in answers}

    def _by_text(self, answers: list[Answer]) -> dict[str, float]:
        return {
            (answer.question_text or "").strip(): answer.numeric_value
            for answer in answers
            if answer.question_text
        }

    def _average(self, values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def _clamp(self, value: float) -> float:
        return max(0.0, min(100.0, value))
