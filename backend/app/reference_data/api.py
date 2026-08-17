from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError
from app.db.session import get_db
from app.reference_data.models import Country, JobFamily, TaxRuleSet
from app.reference_data.schemas import CountryOut, JobFamilyOut, TaxRuleSetOut

router = APIRouter()


@router.get("/countries", response_model=list[CountryOut])
def list_countries(db: Session = Depends(get_db)) -> list[Country]:
    stmt = select(Country).options(selectinload(Country.default_currency)).order_by(Country.code)
    return list(db.scalars(stmt).all())


@router.get("/job-families", response_model=list[JobFamilyOut])
def list_job_families(db: Session = Depends(get_db)) -> list[JobFamily]:
    """Added in Phase 10. The job_families table has existed since Phase
    2 and CompensationInput has always accepted a job_family_id, but
    nothing ever exposed the list - so the calculator form could not
    offer it, every calculation stored NULL, and market context (which
    needs a family to map onto a published occupation) would have been
    unreachable for every real user. Found by opening the running app
    rather than by reading the code.
    """
    return list(db.scalars(select(JobFamily).order_by(JobFamily.name)).all())


@router.get("/countries/{country_code}/tax-rule-sets", response_model=list[TaxRuleSetOut])
def list_tax_rule_sets(country_code: str, db: Session = Depends(get_db)) -> list[TaxRuleSet]:
    country = db.scalar(select(Country).where(Country.code == country_code.upper()))
    if country is None:
        # Matches compensation/api.py's _get_country exactly (same code,
        # same message format) - this endpoint predates AppError (Phase 2,
        # before Phase 3 introduced the {"error": {...}} envelope) and had
        # drifted onto FastAPI's raw {"detail": ...} shape instead. Found
        # while building the Phase 4 regime selector, which calls this
        # endpoint and needs one consistent error contract across the API.
        raise AppError(
            f"Unknown country code: {country_code}", code="unknown_country", status_code=404
        )

    stmt = (
        select(TaxRuleSet)
        .where(TaxRuleSet.country_id == country.id)
        .options(
            selectinload(TaxRuleSet.tax_brackets),
            selectinload(TaxRuleSet.currency),
        )
        .order_by(TaxRuleSet.effective_date, TaxRuleSet.regime)
    )
    return list(db.scalars(stmt).all())
