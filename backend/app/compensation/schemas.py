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
    engine_version: str
    gross_amount: Decimal
    total_compensation_amount: Decimal
    tax_rule_set_id: int | None
    total_tax_amount: Decimal | None
    net_amount: Decimal | None
    breakdown: dict[str, Any]
    created_at: datetime
