from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.compensation.models import Calculation
from app.db.base import Base
from app.reference_data.models import Currency


class Comparison(Base):
    """A named, persisted grouping of 2+ of a user's own Calculations,
    normalized into one currency for a side-by-side view.

    Like Calculation, immutable after creation - `result` (the converted
    per-calculation figures plus gap analysis) is computed ONCE at
    creation time by app.comparison.orchestration.build_comparison and
    stored here, never recomputed on a later GET. This mirrors Calculation
    exactly and for the same reason: a comparison a user revisits next
    month must show the SAME numbers they saw when they made it, not a
    silently different one because exchange rates moved or a later fetch
    landed. `as_of_date` records which day's rates were used, so that
    choice stays auditable.

    Comparisons only ever belong to a logged-in user (user_id is NOT
    NULL, unlike Calculation.user_id) - unlike a calculation, there's no
    anonymous equivalent: a comparison inherently operates on saved
    history, which anonymous use doesn't have.
    """

    __tablename__ = "comparisons"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(256))
    comparison_currency_id: Mapped[int] = mapped_column(ForeignKey("currencies.id"))
    as_of_date: Mapped[date] = mapped_column(
        Date, comment="Date used for the comparison's exchange rate lookups."
    )
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
    comparison_currency: Mapped[Currency] = relationship()
    items: Mapped[list["ComparisonCalculation"]] = relationship(
        back_populates="comparison",
        cascade="all, delete-orphan",
        order_by="ComparisonCalculation.position",
    )


class ComparisonCalculation(Base):
    """The Comparison<->Calculation many-to-many association.

    A join table, not an array column on Comparison, for three concrete
    reasons an array column can't cover: a real FK to calculations.id (so
    the DB itself enforces the reference stays valid, not just app code),
    an index enabling "which comparisons include calculation X" lookups
    in the other direction, and a place to put `position` (preserves the
    order the user selected calculations in, so the comparison always
    renders in the same left-to-right order on every later visit).
    """

    __tablename__ = "comparison_calculations"
    __table_args__ = (
        UniqueConstraint("comparison_id", "calculation_id", name="uq_comparison_calculation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    comparison_id: Mapped[int] = mapped_column(ForeignKey("comparisons.id"))
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculations.id"))
    position: Mapped[int] = mapped_column(Integer)

    comparison: Mapped[Comparison] = relationship(back_populates="items")
    calculation: Mapped[Calculation] = relationship()
