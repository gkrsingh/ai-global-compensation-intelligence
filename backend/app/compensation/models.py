import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.db.base import Base
from app.reference_data.models import (
    Country,
    Currency,
    EmploymentType,
    ExperienceLevel,
    JobFamily,
    TaxRuleSet,
)


class ComponentType(enum.StrEnum):
    """A typed compensation line item. Composable rather than fixed columns
    (base_salary, bonus, ...) — what counts as compensation varies by
    country and employment type (13th-month pay, RSUs, housing allowances),
    and retrofitting fixed columns later would be a real rewrite.
    """

    BASE = "base"
    BONUS = "bonus"
    EQUITY = "equity"
    BENEFIT = "benefit"
    ALLOWANCE = "allowance"


class CompensationInput(Base):
    """The structured, immutable request for a calculation.

    Immutability is enforced by omission, not a DB trigger: no update
    endpoint exists in the API, so there is no code path that mutates a row
    after creation. `target_currency` and `as_of_date` live here (not on
    Calculation) because they're request parameters, not engine output —
    Calculation reaches them via the FK rather than duplicating them.
    """

    __tablename__ = "compensation_inputs"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"))
    job_family_id: Mapped[int | None] = mapped_column(ForeignKey("job_families.id"))
    experience_level_id: Mapped[int | None] = mapped_column(ForeignKey("experience_levels.id"))
    employment_type_id: Mapped[int | None] = mapped_column(ForeignKey("employment_types.id"))
    regime: Mapped[str | None] = mapped_column(String(32))
    filing_status: Mapped[str | None] = mapped_column(String(32))
    target_currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"))
    as_of_date: Mapped[date] = mapped_column(
        Date, comment="Date used for tax rule set and exchange rate lookups."
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    country: Mapped[Country] = relationship()
    job_family: Mapped[JobFamily | None] = relationship()
    experience_level: Mapped[ExperienceLevel | None] = relationship()
    employment_type: Mapped[EmploymentType | None] = relationship()
    target_currency: Mapped[Currency] = relationship()
    components: Mapped[list["CompensationComponent"]] = relationship(
        back_populates="compensation_input", cascade="all, delete-orphan"
    )
    calculations: Mapped[list["Calculation"]] = relationship(back_populates="compensation_input")


class CompensationComponent(Base):
    __tablename__ = "compensation_components"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_compensation_components_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    compensation_input_id: Mapped[int] = mapped_column(ForeignKey("compensation_inputs.id"))
    component_type: Mapped[ComponentType] = mapped_column(
        Enum(ComponentType, name="component_type")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"))
    description: Mapped[str | None] = mapped_column(String(256))

    compensation_input: Mapped[CompensationInput] = relationship(back_populates="components")
    currency: Mapped[Currency] = relationship()


class Calculation(Base):
    """An immutable, persisted snapshot of one engine run against one
    CompensationInput. Never edited after creation — if calculation logic
    changes, a new row (new engine_version) is created rather than this one
    being updated, so old results never silently change.

    `breakdown` carries the full audit detail (per-component converted
    amounts, per-bracket tax contributions, exchange rates used) as JSONB
    rather than a normalized table — it's inherently nested, variable-length,
    and only ever read alongside its one parent row.

    `user_id` is nullable so anonymous calculations (Phase 4's core flow,
    still fully supported) keep working exactly as before — a calculation
    is only tagged to a user if one was authenticated at submission time,
    set by the API layer (not the engine, which stays auth-agnostic).
    """

    __tablename__ = "calculations"
    __table_args__ = (
        CheckConstraint("gross_amount >= 0", name="ck_calculations_gross_non_negative"),
        CheckConstraint(
            "total_compensation_amount >= 0", name="ck_calculations_total_comp_non_negative"
        ),
        CheckConstraint(
            "total_tax_amount IS NULL OR total_tax_amount >= 0",
            name="ck_calculations_total_tax_non_negative",
        ),
        CheckConstraint(
            "net_amount IS NULL OR net_amount >= 0", name="ck_calculations_net_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    compensation_input_id: Mapped[int] = mapped_column(ForeignKey("compensation_inputs.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    engine_version: Mapped[str] = mapped_column(String(32))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_compensation_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    tax_rule_set_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rule_sets.id"))
    total_tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    compensation_input: Mapped[CompensationInput] = relationship(back_populates="calculations")
    tax_rule_set: Mapped[TaxRuleSet | None] = relationship()
    user: Mapped[User | None] = relationship()
