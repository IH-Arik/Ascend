"""Account screen response schemas."""

from pydantic import BaseModel


class AccountProfileRead(BaseModel):
    """Top profile card payload."""

    name: str
    email: str
    age: int | None = None
    profile_image: str | None = None


class AccountOrganizationRead(BaseModel):
    """Organization block payload."""

    organization_name: str | None = None
    organization_code: str | None = None
    subtitle: str | None = None


class AccountPerformanceRead(BaseModel):
    """Performance profile block payload."""

    current_ops_score: float
    strongest_driver: str | None = None
    focus_driver: str | None = None


class SupportItemRead(BaseModel):
    """Settings and support row payload."""

    title: str
    key: str


class AccountSummaryRead(BaseModel):
    """Full account summary payload."""

    profile: AccountProfileRead
    organization: AccountOrganizationRead
    performance_profile: AccountPerformanceRead
    settings_support: list[SupportItemRead]
    app_version: str


class LegalContentRead(BaseModel):
    """Static legal or informational page content."""

    title: str
    items: list[str]


class FaqItemRead(BaseModel):
    """FAQ item payload."""

    question: str
    answer: str


class HelpCenterRead(BaseModel):
    """Help center payload."""

    title: str
    subtitle: str
    faqs: list[FaqItemRead]
    support_cta_title: str
    support_cta_description: str


class SupportRequestCreate(BaseModel):
    """Support request payload."""

    issue: str


class SupportRequestRead(BaseModel):
    """Support request response payload."""

    email: str
    issue: str
    estimated_response: str
