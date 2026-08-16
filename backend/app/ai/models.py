from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.comparison.models import Comparison
from app.compensation.models import Calculation
from app.db.base import Base


class AIAnalysisRequest(Base):
    """One ask for AI-generated insight on a specific, already-persisted
    Calculation or Comparison - never both, per the CHECK constraint
    below. Always tied to the requesting user (this feature requires
    auth, unlike POST /calculations - see the design discussion: a real
    per-call cost needs a real identity to attach accountability to).

    `context` is the exact, structured set of grounded facts (numeric
    figures and their labels/currency, plus whatever descriptive fields
    the prompt template needs) extracted from the Calculation/Comparison
    AT THE TIME of this request and stored verbatim - not re-derived from
    the FK at read time. This is what makes the audit trail meaningful:
    if the context-extraction logic changes later, an old request still
    shows exactly what was actually fed to the prompt back when it ran,
    the same immutable-snapshot reasoning already applied to
    Calculation.breakdown and Comparison.result. It also doubles as the
    consistency checker's source of truth for "real" numbers.
    """

    __tablename__ = "ai_analysis_requests"
    __table_args__ = (
        CheckConstraint(
            "(calculation_id IS NOT NULL AND comparison_id IS NULL) OR "
            "(calculation_id IS NULL AND comparison_id IS NOT NULL)",
            name="ck_ai_analysis_requests_exactly_one_target",
        ),
        Index("ix_ai_analysis_requests_user_calculation", "user_id", "calculation_id"),
        Index("ix_ai_analysis_requests_user_comparison", "user_id", "comparison_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    calculation_id: Mapped[int | None] = mapped_column(ForeignKey("calculations.id"))
    comparison_id: Mapped[int | None] = mapped_column(ForeignKey("comparisons.id"))
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
    calculation: Mapped[Calculation | None] = relationship()
    comparison: Mapped[Comparison | None] = relationship()
    results: Mapped[list["AIAnalysisResult"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="AIAnalysisResult.created_at",
    )


class AIAnalysisResult(Base):
    """One actual call attempt against an AIProvider for a given Request.

    Deliberately many-to-one with AIAnalysisRequest, not one-to-one: if
    the numeric-consistency check fails, the plan (finalized in step 5)
    is to regenerate rather than silently show untrustworthy text - each
    attempt gets its own row, including failed ones, so the audit trail
    shows every real call made, not just the one that happened to pass.
    `consistency_check_passed=False` rows are never shown to the user as
    the "the AI said" text; they exist purely for the audit trail this
    phase's entire safeguard depends on being real, not just logged as an
    afterthought.
    """

    __tablename__ = "ai_analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("ai_analysis_requests.id"))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    prompt_text: Mapped[str] = mapped_column(Text)
    generated_text: Mapped[str] = mapped_column(Text)
    consistency_check_passed: Mapped[bool] = mapped_column(Boolean)
    # Structured detail behind the pass/fail verdict - e.g. which numbers
    # were found in the generated text and which of those did/didn't
    # trace back to context. Built out for real in step 4; the column
    # exists now so the audit trail has somewhere to live from the start.
    consistency_check_details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    request: Mapped[AIAnalysisRequest] = relationship(back_populates="results")
