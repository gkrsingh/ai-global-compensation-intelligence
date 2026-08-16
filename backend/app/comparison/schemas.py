from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.compensation.schemas import CalculationOut


class ComparisonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    comparison_currency_code: str
    # min_length=2 mirrors CompensationInputCreate.components's
    # Field(min_length=1) precedent - "at least 2" is enforced here at
    # the schema boundary rather than as a DB constraint, same reasoning:
    # counting rows for a CHECK constraint needs a trigger, and this is
    # simpler and just as effective for a create-time-only invariant.
    calculation_ids: list[int] = Field(min_length=2)
    as_of_date: date | None = None

    @field_validator("calculation_ids")
    @classmethod
    def _no_duplicate_ids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("calculation_ids must not contain duplicates")
        return value


class ComparisonEntryOut(BaseModel):
    calculation_id: int
    source_currency: str
    rate_used: Decimal | None
    gross_amount: Decimal
    total_compensation_amount: Decimal
    total_tax_amount: Decimal | None
    net_amount: Decimal | None


class MetricGapEntryOut(BaseModel):
    calculation_id: int
    gap_absolute: Decimal
    gap_percent: Decimal | None


class MetricGapAnalysisOut(BaseModel):
    leader_calculation_id: int
    entries: list[MetricGapEntryOut]


class ComparisonDetailOut(BaseModel):
    id: int
    name: str
    comparison_currency: str
    as_of_date: date
    created_at: datetime
    entries: list[ComparisonEntryOut]
    # Keyed by "gross_amount" / "total_compensation_amount" / "net_amount"
    # (app.comparison.services.normalize.GAP_METRICS) - a metric maps to
    # None when at least one compared calculation has no figure for it.
    gap_analysis: dict[str, MetricGapAnalysisOut | None]
    # Full original breakdowns (per-offer detail: tax brackets, converted
    # components, everything ResultsView already knows how to render) for
    # each underlying calculation, in the same order as `entries` - lets
    # the frontend reuse the existing per-calculation breakdown view
    # rather than this feature inventing a second one.
    calculations: list[CalculationOut]


class ComparisonSummaryOut(BaseModel):
    id: int
    name: str
    comparison_currency: str
    as_of_date: date
    created_at: datetime
    calculation_count: int


class PaginatedComparisonsOut(BaseModel):
    items: list[ComparisonSummaryOut]
    total: int
    limit: int
    offset: int
