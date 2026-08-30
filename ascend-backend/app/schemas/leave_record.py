"""Provider leave/TDY schemas."""

from datetime import date

from pydantic import BaseModel, Field, model_validator

LEAVE_TYPES = ("leave", "tdy", "training", "medical")
LEAVE_TYPE_LABELS: dict[str, str] = {
    "leave": "Leave",
    "tdy": "TDY",
    "training": "Training",
    "medical": "Medical",
}


class LeaveRecordCreate(BaseModel):
    """Log a real block of provider leave/TDY/training/medical absence."""

    user_id: str | None = Field(default=None, description="Defaults to the creating provider.")
    leave_type: str = Field(pattern="^(" + "|".join(LEAVE_TYPES) + ")$")
    start_date: date
    end_date: date
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_date_order(self) -> "LeaveRecordCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date.")
        return self


class LeaveRecordResponse(BaseModel):
    """A single logged leave/TDY/training/medical record."""

    id: str
    user_id: str
    user_name: str | None
    leave_type: str
    leave_type_label: str
    start_date: str
    end_date: str
    note: str | None
    created_at: str
