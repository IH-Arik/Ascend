"""Question response schemas."""

from pydantic import BaseModel




class QuestionRead(BaseModel):
    """Serialized question payload."""

    id: str
    text: str
    driver: str
    response_type: str
    options: list[str]
    weight: float
    order: int
    step: int


class PaginatedQuestions(BaseModel):
    """Paginated collection of questions."""

    total: int
    page: int
    size: int
    total_pages: int
    questions: list[QuestionRead]
