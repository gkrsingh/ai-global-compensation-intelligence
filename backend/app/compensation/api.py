from datetime import date

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import OptionalAuthResult, get_current_user_optional
from app.compensation.engine import run_calculation
from app.compensation.models import Calculation, CompensationComponent, CompensationInput
from app.compensation.schemas import CalculationOut, CompensationInputCreate
from app.compensation.services.currency import MissingExchangeRateError
from app.core.exceptions import AppError
from app.db.session import get_db
from app.reference_data.models import Country, Currency, EmploymentType, ExperienceLevel, JobFamily
from app.reference_data.queries import AmbiguousTaxRuleSetError

router = APIRouter()

# Set when a caller presented a bearer token that turned out to be
# invalid/expired - the calculation still succeeds anonymously (see
# get_current_user_optional's docstring for why), but the frontend can
# use this to tell the user their session lapsed rather than silently
# saying nothing about why the result didn't land in their history.
AUTH_WARNING_HEADER = "X-Auth-Warning"
INVALID_TOKEN_WARNING = "invalid_or_expired_token"


def _get_country(db: Session, code: str) -> Country:
    country = db.scalar(select(Country).where(Country.code == code.upper()))
    if country is None:
        raise AppError(f"Unknown country code: {code}", code="unknown_country", status_code=404)
    return country


def _get_currency(db: Session, code: str) -> Currency:
    currency = db.scalar(select(Currency).where(Currency.code == code.upper()))
    if currency is None:
        raise AppError(f"Unknown currency code: {code}", code="unknown_currency", status_code=404)
    return currency


def _check_reference_id(db: Session, model: type, id_: int | None, label: str) -> None:
    if id_ is None:
        return
    if db.get(model, id_) is None:
        raise AppError(f"Unknown {label} id: {id_}", code=f"unknown_{label}", status_code=404)


@router.post("/calculations", response_model=CalculationOut, status_code=status.HTTP_201_CREATED)
def create_calculation(
    payload: CompensationInputCreate,
    response: Response,
    db: Session = Depends(get_db),
    auth: OptionalAuthResult = Depends(get_current_user_optional),
) -> Calculation:
    country = _get_country(db, payload.country_code)
    target_currency = _get_currency(db, payload.target_currency_code)
    _check_reference_id(db, JobFamily, payload.job_family_id, "job_family")
    _check_reference_id(db, ExperienceLevel, payload.experience_level_id, "experience_level")
    _check_reference_id(db, EmploymentType, payload.employment_type_id, "employment_type")

    components = [
        CompensationComponent(
            component_type=c.component_type,
            amount=c.amount,
            currency_id=_get_currency(db, c.currency_code).id,
            description=c.description,
        )
        for c in payload.components
    ]

    comp_input = CompensationInput(
        country_id=country.id,
        target_currency_id=target_currency.id,
        job_family_id=payload.job_family_id,
        experience_level_id=payload.experience_level_id,
        employment_type_id=payload.employment_type_id,
        regime=payload.regime,
        filing_status=payload.filing_status,
        as_of_date=payload.as_of_date or date.today(),
    )
    comp_input.components = components
    db.add(comp_input)
    db.flush()

    try:
        calculation = run_calculation(db, comp_input)
    except MissingExchangeRateError as exc:
        raise AppError(
            f"No exchange rate available for {exc.from_currency} -> {exc.to_currency}",
            code="missing_exchange_rate",
            status_code=422,
        ) from exc
    except AmbiguousTaxRuleSetError as exc:
        raise AppError(str(exc), code="ambiguous_tax_rule_set", status_code=422) from exc

    if auth.user is not None:
        calculation.user_id = auth.user.id
    if auth.token_rejected:
        response.headers[AUTH_WARNING_HEADER] = INVALID_TOKEN_WARNING

    db.commit()
    db.refresh(calculation)
    return calculation
