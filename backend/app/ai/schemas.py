from datetime import datetime

from pydantic import BaseModel, model_validator


class AIInsightCreate(BaseModel):
    calculation_id: int | None = None
    comparison_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "AIInsightCreate":
        if (self.calculation_id is None) == (self.comparison_id is None):
            raise ValueError("exactly one of calculation_id or comparison_id must be provided")
        return self


class AIInsightOut(BaseModel):
    id: int
    request_id: int
    calculation_id: int | None
    comparison_id: int | None
    provider: str
    model: str
    generated_text: str
    created_at: datetime
    # Whether this response came from an existing, already-passed result
    # rather than a fresh provider call this request - lets the frontend
    # (and anyone auditing behavior) tell the two apart without needing
    # to inspect timestamps.
    cached: bool
