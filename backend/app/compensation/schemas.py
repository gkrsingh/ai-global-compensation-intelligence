from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.compensation.models import ComponentType


class CompensationComponentIn(BaseModel):
    component_type: ComponentType
    amount: Decimal = Field(ge=0)
    currency_code: str
    description: str | None = None


class CompensationInputCreate(BaseModel):
    country_code: str
    job_family_id: int | None = None
    experience_level_id: int | None = None
    employment_type_id: int | None = None
    regime: str | None = None
    filing_status: str | None = None
    target_currency_code: str
    as_of_date: date | None = None
    components: list[CompensationComponentIn] = Field(min_length=1)


class CalculationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    compensation_input_id: int
    user_id: int | None
    engine_version: str
    gross_amount: Decimal
    total_compensation_amount: Decimal
    tax_rule_set_id: int | None
    total_tax_amount: Decimal | None
    net_amount: Decimal | None
    breakdown: dict[str, Any]
    created_at: datetime

    # Added in Phase 10: a calculation result did not previously say what
    # country or role it was FOR, so a consumer holding only a
    # CalculationOut could not ask for the matching market context.
    # Both are plain read-through properties on the Calculation ORM model
    # (see app/compensation/models.py) sourced from the CompensationInput
    # it already owns - nothing new is persisted, and from_attributes
    # picks them up at every existing CalculationOut.model_validate call
    # site without any of them changing.
    #
    # job_family_id is genuinely optional: the calculator does not require
    # a job family, and market context is simply unavailable without one.
    country_code: str
    job_family_id: int | None


class PaginatedCalculationsOut(BaseModel):
    items: list[CalculationOut]
    total: int
    limit: int
    offset: int
