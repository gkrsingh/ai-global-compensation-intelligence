from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.reference_data.models import TaxComponent


class CurrencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    symbol: str


class CountryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    default_currency: CurrencyOut


class TaxBracketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    component: TaxComponent
    lower_bound: Decimal
    upper_bound: Decimal | None
    rate: Decimal


class TaxRuleSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    regime: str | None
    filing_status: str | None
    standard_deduction: Decimal | None
    effective_date: date
    end_date: date | None
    source_url: str | None
    currency: CurrencyOut
    tax_brackets: list[TaxBracketOut]


class JobFamilyOut(BaseModel):
    """Exposed in Phase 10: the calculator form had no way to send a job
    family (nothing ever fetched the list), so job_family_id was always
    null and market context - which needs a family to map onto a
    published occupation - could never appear for any real user.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
