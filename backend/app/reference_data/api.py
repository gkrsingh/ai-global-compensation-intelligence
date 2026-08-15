from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.reference_data.models import Country, TaxRuleSet
from app.reference_data.schemas import CountryOut, TaxRuleSetOut

router = APIRouter()


@router.get("/countries", response_model=list[CountryOut])
def list_countries(db: Session = Depends(get_db)) -> list[Country]:
    stmt = select(Country).options(selectinload(Country.default_currency)).order_by(Country.code)
    return list(db.scalars(stmt).all())


@router.get("/countries/{country_code}/tax-rule-sets", response_model=list[TaxRuleSetOut])
def list_tax_rule_sets(country_code: str, db: Session = Depends(get_db)) -> list[TaxRuleSet]:
    country = db.scalar(select(Country).where(Country.code == country_code.upper()))
    if country is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown country code: {country_code}",
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
