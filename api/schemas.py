from pydantic import BaseModel
from typing import Optional

class ResearchRequest(BaseModel):
    question: str
    output_format: Optional[str] = "markdown"

class ResearchResponse(BaseModel):
    review: str
    total_time_seconds: float
    total_tokens: Optional[int] = None
