import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Currency(Base):
    __tablename__ = "currencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(3), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(8))
    decimal_places: Mapped[int] = mapped_column(default=2)


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(2), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    default_currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"))

    default_currency: Mapped[Currency] = relationship()
    tax_rule_sets: Mapped[list["TaxRuleSet"]] = relationship(
        back_populates="country", order_by="TaxRuleSet.effective_date"
    )


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("base_currency_id", "quote_currency_id", "as_of_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"))
    quote_currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    as_of_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(64))

    base_currency: Mapped[Currency] = relationship(foreign_keys=[base_currency_id])
    quote_currency: Mapped[Currency] = relationship(foreign_keys=[quote_currency_id])


class JobFamily(Base):
    __tablename__ = "job_families"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class ExperienceLevel(Base):
    __tablename__ = "experience_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    rank: Mapped[int] = mapped_column(unique=True)


class EmploymentType(Base):
    __tablename__ = "employment_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))


class TaxComponent(enum.StrEnum):
    """What a TaxBracket row represents. Deliberately generic — new
    components (a future country's own named levy) extend this enum rather
    than requiring new tables or country-specific code paths.
    """

    INCOME_TAX = "income_tax"
    SOCIAL_SECURITY = "social_security"
    MEDICARE = "medicare"
    MEDICARE_ADDITIONAL_SURTAX = "medicare_additional_surtax"


class TaxRuleSet(Base):
    """A versioned, country-scoped set of tax rules effective from a date.

    `regime` and `filing_status` make known simplifications (e.g. India's
    old/new regime choice, US single-filer-only scope) explicit, queryable
    facts rather than assumptions buried in code or comments.
    """

    __tablename__ = "tax_rule_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"))
    currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"))
    name: Mapped[str] = mapped_column(String(128))
    regime: Mapped[str | None] = mapped_column(String(32))
    filing_status: Mapped[str | None] = mapped_column(String(32))
    standard_deduction: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    effective_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(
        Date, comment="NULL means this rule set has no known end date (still current)."
    )
    source_url: Mapped[str | None] = mapped_column(String(512))
    source_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    country: Mapped[Country] = relationship(back_populates="tax_rule_sets")
    currency: Mapped[Currency] = relationship()
    tax_brackets: Mapped[list["TaxBracket"]] = relationship(
        back_populates="tax_rule_set",
        cascade="all, delete-orphan",
        order_by="TaxBracket.lower_bound",
    )


class TaxBracket(Base):
    """One marginal bracket of one component (income tax, social security,
    ...) within a TaxRuleSet. The calculation engine (Phase 3) iterates over
    these generically — it never branches on which country or component it's
    looking at.
    """

    __tablename__ = "tax_brackets"
    __table_args__ = (
        # Catches the most likely real mistake (an accidental duplicate row
        # during seeding) essentially for free. Does NOT catch overlapping-
        # but-different-lower_bound ranges — true range-overlap prevention
        # needs a Postgres EXCLUDE constraint (btree_gist + a range column),
        # deliberately deferred to Phase 3 when the calculation engine
        # becomes a real consumer whose correctness depends on it.
        UniqueConstraint(
            "tax_rule_set_id",
            "component",
            "lower_bound",
            name="uq_tax_brackets_rule_set_component_lower_bound",
        ),
        CheckConstraint(
            "upper_bound IS NULL OR upper_bound > lower_bound",
            name="ck_tax_brackets_upper_gt_lower",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tax_rule_set_id: Mapped[int] = mapped_column(ForeignKey("tax_rule_sets.id"))
    component: Mapped[TaxComponent] = mapped_column(Enum(TaxComponent, name="tax_component"))
    lower_bound: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), comment="Inclusive lower bound of this bracket, in the rule set's currency."
    )
    upper_bound: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        comment="Exclusive upper bound, in the rule set's currency. NULL = unbounded top bracket.",
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 5))

    tax_rule_set: Mapped[TaxRuleSet] = relationship(back_populates="tax_brackets")
