"""OFT (Operational Fitness Test) schemas (DOCX section 8.2)."""

from datetime import date

from pydantic import BaseModel, Field


class OFTScheduleRequest(BaseModel):
    """Schedule an upcoming OFT test for a user."""

    test_date: date
    notes: str | None = Field(default=None, max_length=300)


class OFTRecordResultRequest(BaseModel):
    """Record a completed OFT test result for a user."""

    test_date: date
    status: str = Field(pattern="^(current|not_current|exempt)$")
    pass_fail: str = Field(pattern="^(pass|fail)$")
    items_passed: int | None = Field(default=None, ge=0)
    items_total: int | None = Field(default=None, ge=0)
    entered_into_government_system: bool = False
    notes: str | None = Field(default=None, max_length=300)


class OFTStatusResponse(BaseModel):
    """Current OFT status summary for a user."""

    current_status: str
    latest_pass_fail: str | None
    latest_test_date: str | None
    items_passed: int | None
    items_total: int | None
    next_scheduled_date: str | None
    next_scheduled_relative: str | None = None
    annual_test_count: int
