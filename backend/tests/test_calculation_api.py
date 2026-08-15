from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.compensation.models import Calculation, CompensationInput
from app.reference_data.models import Country, EmploymentType, ExperienceLevel, JobFamily


def _register_and_login(client: TestClient, email: str) -> str:
    password = "correct horse battery staple"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    access_token: str = login.json()["access_token"]
    return access_token


_BASE_PAYLOAD = {
    "country_code": "US",
    "filing_status": "single",
    "target_currency_code": "USD",
    "components": [{"component_type": "base", "amount": "1000", "currency_code": "USD"}],
}


def test_create_calculation_us_single_filer(client: TestClient, db_session: Session) -> None:
    """Full HTTP-stack cross-check of the same $150,000 example verified
    directly against the engine in step 5/6: JSON request -> validation ->
    DB lookups -> engine -> persist -> JSON response, all working, not
    just the engine function called in isolation.
    """
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "US",
            "filing_status": "single",
            "target_currency_code": "USD",
            "components": [
                {"component_type": "base", "amount": "150000.00", "currency_code": "USD"}
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["gross_amount"] == "150000.00"
    assert body["total_tax_amount"] == "36209.00"
    assert body["net_amount"] == "113791.00"
    assert body["tax_rule_set_id"] is not None

    # Persisted for real, not just returned - verified via a direct query.
    persisted = db_session.get(Calculation, body["id"])
    assert persisted is not None
    assert persisted.gross_amount == Decimal("150000.00")

    db_session.delete(persisted)
    db_session.delete(persisted.compensation_input)
    db_session.commit()


def test_unknown_country_code_returns_404_with_error_envelope(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "ZZ",
            "target_currency_code": "USD",
            "components": [{"component_type": "base", "amount": "1000", "currency_code": "USD"}],
        },
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "unknown_country"
    assert "ZZ" in body["error"]["message"]


def test_unknown_target_currency_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "US",
            "target_currency_code": "ZZZ",
            "components": [{"component_type": "base", "amount": "1000", "currency_code": "USD"}],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_currency"


def test_unknown_component_currency_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "US",
            "target_currency_code": "USD",
            "components": [{"component_type": "base", "amount": "1000", "currency_code": "ZZZ"}],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_currency"


def test_unknown_experience_level_id_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "US",
            "target_currency_code": "USD",
            "experience_level_id": 999999,
            "components": [{"component_type": "base", "amount": "1000", "currency_code": "USD"}],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_experience_level"


def test_empty_components_list_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calculations",
        json={"country_code": "US", "target_currency_code": "USD", "components": []},
    )
    assert response.status_code == 422


def test_negative_amount_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "US",
            "target_currency_code": "USD",
            "components": [{"component_type": "base", "amount": "-100", "currency_code": "USD"}],
        },
    )
    assert response.status_code == 422


def test_missing_exchange_rate_returns_422_not_500(client: TestClient, db_session: Session) -> None:
    """INR-sourced income normalized to EUR: no seeded path exists. Must
    surface as a clean 422 with our error envelope, not a raw 500 or an
    unhandled exception.
    """
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "IN",
            "target_currency_code": "EUR",
            "components": [
                {"component_type": "base", "amount": "100000.00", "currency_code": "INR"}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_exchange_rate"

    # The CompensationInput was flushed before the engine raised - confirm
    # it did NOT get committed (get_db's session.close() on the way out
    # rolls back the uncommitted transaction).
    india = db_session.scalar(select(Country).where(Country.code == "IN"))
    assert india is not None
    leftover = db_session.scalars(
        select(CompensationInput).where(CompensationInput.country_id == india.id)
    ).all()
    assert leftover == []


def test_ambiguous_tax_rule_set_returns_422_not_500(
    client: TestClient, db_session: Session
) -> None:
    """India has both an old- and a new-regime TaxRuleSet effective today;
    submitting without a regime must surface as a clean 422 with our error
    envelope, not an unhandled 500 (sqlalchemy.exc.MultipleResultsFound
    leaking out of get_effective_tax_rule_set - the real bug this guards,
    caught via real browser testing in Phase 4, not invented for the test).
    """
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "IN",
            "target_currency_code": "INR",
            "components": [
                {"component_type": "base", "amount": "1500000.00", "currency_code": "INR"}
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ambiguous_tax_rule_set"

    india = db_session.scalar(select(Country).where(Country.code == "IN"))
    assert india is not None
    leftover = db_session.scalars(
        select(CompensationInput).where(CompensationInput.country_id == india.id)
    ).all()
    assert leftover == []


def test_as_of_date_defaults_to_today_when_omitted(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "IN",
            "regime": "new",
            "target_currency_code": "INR",
            "components": [
                {"component_type": "base", "amount": "500000.00", "currency_code": "INR"}
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["breakdown"]["as_of_date"] == date.today().isoformat()

    persisted = db_session.get(Calculation, body["id"])
    assert persisted is not None
    db_session.delete(persisted)
    db_session.delete(persisted.compensation_input)
    db_session.commit()


def test_invalid_component_type_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "US",
            "target_currency_code": "USD",
            "components": [{"component_type": "salary", "amount": "1000", "currency_code": "USD"}],
        },
    )
    assert response.status_code == 422


def test_create_calculation_with_full_optional_metadata(
    client: TestClient, db_session: Session
) -> None:
    """Unlike test_unknown_experience_level_id_returns_404 (which only
    proves the rejection path), this proves the happy path: valid
    job_family/experience_level/employment_type ids actually persist.
    """
    job_family = db_session.scalar(
        select(JobFamily).where(JobFamily.name == "Software Engineering")
    )
    experience_level = db_session.scalar(
        select(ExperienceLevel).where(ExperienceLevel.name == "Senior")
    )
    employment_type = db_session.scalar(
        select(EmploymentType).where(EmploymentType.code == "FULL_TIME")
    )
    assert job_family is not None
    assert experience_level is not None
    assert employment_type is not None

    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": "US",
            "filing_status": "single",
            "target_currency_code": "USD",
            "job_family_id": job_family.id,
            "experience_level_id": experience_level.id,
            "employment_type_id": employment_type.id,
            "components": [
                {"component_type": "base", "amount": "100000.00", "currency_code": "USD"}
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()

    persisted = db_session.get(Calculation, body["id"])
    assert persisted is not None
    assert persisted.compensation_input.job_family_id == job_family.id
    assert persisted.compensation_input.experience_level_id == experience_level.id
    assert persisted.compensation_input.employment_type_id == employment_type.id

    db_session.delete(persisted)
    db_session.delete(persisted.compensation_input)
    db_session.commit()


def test_anonymous_calculation_has_no_user_id(client: TestClient, db_session: Session) -> None:
    """Phase 4's core flow, unaffected by auth existing now: no
    Authorization header at all is the ordinary, unremarkable case.
    """
    response = client.post("/api/v1/calculations", json=_BASE_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["user_id"] is None
    assert "X-Auth-Warning" not in response.headers

    persisted = db_session.get(Calculation, response.json()["id"])
    assert persisted is not None
    assert persisted.user_id is None

    db_session.delete(persisted)
    db_session.delete(persisted.compensation_input)
    db_session.commit()


def test_authenticated_calculation_is_tagged_with_the_user(
    client: TestClient, db_session: Session
) -> None:
    access_token = _register_and_login(client, "calc-auth-tag-test@example.com")

    response = client.post(
        "/api/v1/calculations",
        json=_BASE_PAYLOAD,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] is not None
    assert "X-Auth-Warning" not in response.headers

    user = db_session.scalar(select(User).where(User.email == "calc-auth-tag-test@example.com"))
    assert user is not None
    assert body["user_id"] == user.id

    persisted = db_session.get(Calculation, body["id"])
    assert persisted is not None
    assert persisted.user_id == user.id

    db_session.delete(persisted)
    db_session.delete(persisted.compensation_input)
    db_session.delete(user)
    db_session.commit()


def test_calculation_with_an_invalid_token_still_succeeds_anonymously_with_a_warning(
    client: TestClient, db_session: Session
) -> None:
    """The regression test for the step-3 correction: a stale/expired
    access token must not block this endpoint - it falls back to
    anonymous (still 201, still computes correctly) and surfaces the fact
    via a response header instead of a 401.
    """
    response = client.post(
        "/api/v1/calculations",
        json=_BASE_PAYLOAD,
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 201
    assert response.json()["user_id"] is None
    assert response.headers["X-Auth-Warning"] == "invalid_or_expired_token"

    persisted = db_session.get(Calculation, response.json()["id"])
    assert persisted is not None
    assert persisted.user_id is None

    db_session.delete(persisted)
    db_session.delete(persisted.compensation_input)
    db_session.commit()


def test_two_users_calculations_are_tagged_to_their_own_accounts_not_each_others(
    client: TestClient, db_session: Session
) -> None:
    token_a = _register_and_login(client, "calc-user-a-test@example.com")
    token_b = _register_and_login(client, "calc-user-b-test@example.com")

    response_a = client.post(
        "/api/v1/calculations", json=_BASE_PAYLOAD, headers={"Authorization": f"Bearer {token_a}"}
    )
    response_b = client.post(
        "/api/v1/calculations", json=_BASE_PAYLOAD, headers={"Authorization": f"Bearer {token_b}"}
    )

    user_id_a = response_a.json()["user_id"]
    user_id_b = response_b.json()["user_id"]
    assert user_id_a is not None
    assert user_id_b is not None
    assert user_id_a != user_id_b

    persisted_a = db_session.get(Calculation, response_a.json()["id"])
    persisted_b = db_session.get(Calculation, response_b.json()["id"])
    assert persisted_a is not None
    assert persisted_b is not None
    assert persisted_a.user_id == user_id_a
    assert persisted_b.user_id == user_id_b

    user_a = db_session.scalar(select(User).where(User.email == "calc-user-a-test@example.com"))
    user_b = db_session.scalar(select(User).where(User.email == "calc-user-b-test@example.com"))
    db_session.delete(persisted_a)
    db_session.delete(persisted_a.compensation_input)
    db_session.delete(persisted_b)
    db_session.delete(persisted_b.compensation_input)
    assert user_a is not None
    assert user_b is not None
    db_session.delete(user_a)
    db_session.delete(user_b)
    db_session.commit()
