from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compensation.models import Calculation, CompensationInput
from app.reference_data.models import Country


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
