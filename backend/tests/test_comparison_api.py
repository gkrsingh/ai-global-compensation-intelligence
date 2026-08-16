"""Integration tests for POST/GET /comparisons - the real HTTP stack
(request -> auth -> ownership check -> orchestration -> persistence ->
response), same style as test_calculation_api.py. Uses its own db_session
cleanup since client and db_session are independent sessions (see
conftest.py) - anything committed via client must be deleted explicitly.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.comparison.models import Comparison
from app.compensation.models import Calculation


def _register_and_login(client: TestClient, email: str) -> str:
    password = "correct horse battery staple"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    access_token: str = login.json()["access_token"]
    return access_token


def _create_calculation(
    client: TestClient,
    token: str,
    amount: str,
    currency: str = "USD",
    country: str = "US",
    regime: str | None = None,
) -> int:
    response = client.post(
        "/api/v1/calculations",
        json={
            "country_code": country,
            "filing_status": "single" if country == "US" else None,
            "regime": regime,
            "target_currency_code": currency,
            "components": [{"component_type": "base", "amount": amount, "currency_code": currency}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.json()
    calculation_id: int = response.json()["id"]
    return calculation_id


def _cleanup_calculations(db_session: Session, calculation_ids: list[int]) -> None:
    for calc_id in calculation_ids:
        calc = db_session.get(Calculation, calc_id)
        if calc is not None:
            comp_input = calc.compensation_input
            db_session.delete(calc)
            db_session.delete(comp_input)
    db_session.commit()


def _cleanup_comparison(db_session: Session, comparison_id: int) -> None:
    comparison = db_session.get(Comparison, comparison_id)
    if comparison is not None:
        db_session.delete(comparison)
        db_session.commit()


def _cleanup_user(db_session: Session, email: str) -> None:
    user = db_session.scalar(select(User).where(User.email == email))
    if user is not None:
        db_session.delete(user)
        db_session.commit()


def test_create_comparison_hand_verified_gap_analysis(
    client: TestClient, db_session: Session
) -> None:
    """Full-stack hand-check, same standard as every numeric feature
    before this: US $150,000 single filer (net $113,791.00, already
    hand-verified in test_calculation_engine.py) vs US $100,000 single
    filer.

    Hand math for the second calculation:
      standard_deduction = 16100.00; base = 100000 - 16100 = 83900.00
      income_tax: [0,12400)*.10=1240.00 + [12400,50400)*.12=4560.00
                  + (83900-50400)=33500 * .22 = 7370.00
                = 1240+4560+7370 = 13170.00
      social_security = 100000 * .062 = 6200.00
      medicare = 100000 * .0145 = 1450.00
      medicare_additional_surtax = 0.00 (under 200000)
      total_tax = 13170+6200+1450 = 20820.00
      net = 100000 - 20820 = 79180.00

    Same currency (USD) both sides, so no conversion - gap analysis is
    plain subtraction:
      gross gap: 150000 - 100000 = 50000.00; percent = 50000/100000*100 = 50.00
      net gap:   113791 - 79180  = 34611.00; percent = 34611/79180*100 = 43.71 (rounded)
    """
    email = "compare-hand-check@example.com"
    token = _register_and_login(client, email)
    calc_a = _create_calculation(client, token, "150000.00")
    calc_b = _create_calculation(client, token, "100000.00")

    response = client.post(
        "/api/v1/comparisons",
        json={
            "name": "US offers",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a, calc_b],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.json()
    body = response.json()

    entries_by_id = {e["calculation_id"]: e for e in body["entries"]}
    assert entries_by_id[calc_a]["gross_amount"] == "150000.00"
    assert entries_by_id[calc_a]["net_amount"] == "113791.00"
    assert entries_by_id[calc_b]["gross_amount"] == "100000.00"
    assert entries_by_id[calc_b]["net_amount"] == "79180.00"
    assert entries_by_id[calc_a]["rate_used"] is None

    gross_gap = body["gap_analysis"]["gross_amount"]
    assert gross_gap["leader_calculation_id"] == calc_a
    gross_by_id = {g["calculation_id"]: g for g in gross_gap["entries"]}
    assert gross_by_id[calc_b]["gap_absolute"] == "50000.00"
    assert gross_by_id[calc_b]["gap_percent"] == "50.00"

    net_gap = body["gap_analysis"]["net_amount"]
    assert net_gap["leader_calculation_id"] == calc_a
    net_by_id = {g["calculation_id"]: g for g in net_gap["entries"]}
    assert net_by_id[calc_b]["gap_absolute"] == "34611.00"
    assert net_by_id[calc_b]["gap_percent"] == "43.71"

    assert len(body["calculations"]) == 2
    assert {c["id"] for c in body["calculations"]} == {calc_a, calc_b}

    # Persisted for real, not just returned.
    persisted = db_session.get(Comparison, body["id"])
    assert persisted is not None
    assert persisted.result["gap_analysis"]["net_amount"]["leader_calculation_id"] == calc_a

    _cleanup_comparison(db_session, body["id"])
    _cleanup_calculations(db_session, [calc_a, calc_b])
    _cleanup_user(db_session, email)


def test_create_comparison_rejects_someone_elses_calculation_with_404(
    client: TestClient, db_session: Session
) -> None:
    """The cross-user ownership boundary this phase explicitly calls out
    as needing its own test, mirroring Phase 5's precedent
    (test_two_users_calculations_are_tagged_to_their_own_accounts_not_
    each_others): user A must not be able to build a comparison that
    references user B's calculation, even though the calculation_id is a
    perfectly valid id that exists in the database.
    """
    email_a = "compare-owner-a@example.com"
    email_b = "compare-owner-b@example.com"
    token_a = _register_and_login(client, email_a)
    token_b = _register_and_login(client, email_b)

    calc_a = _create_calculation(client, token_a, "150000.00")
    calc_b = _create_calculation(client, token_b, "100000.00")

    response = client.post(
        "/api/v1/comparisons",
        json={
            "name": "sneaky comparison",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a, calc_b],
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Uniform 404, not 403 - deliberately indistinguishable from a
    # calculation_id that doesn't exist at all (see
    # UnknownCalculationError's docstring).
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "comparison_not_found"

    # Nothing was persisted - the failed attempt left no partial rows.
    leftover = db_session.scalars(
        select(Comparison).where(Comparison.user_id.in_(
            select(User.id).where(User.email.in_([email_a, email_b]))
        ))
    ).all()
    assert leftover == []

    _cleanup_calculations(db_session, [calc_a, calc_b])
    _cleanup_user(db_session, email_a)
    _cleanup_user(db_session, email_b)


def test_create_comparison_with_nonexistent_calculation_id_returns_same_404(
    client: TestClient, db_session: Session
) -> None:
    """Same error code as the cross-user case above - a caller can't tell
    "doesn't exist" apart from "exists but isn't yours" from the outside,
    by design.
    """
    email = "compare-nonexistent@example.com"
    token = _register_and_login(client, email)
    calc_a = _create_calculation(client, token, "150000.00")

    response = client.post(
        "/api/v1/comparisons",
        json={
            "name": "comparison with a fake id",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a, 999999999],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "comparison_not_found"

    _cleanup_calculations(db_session, [calc_a])
    _cleanup_user(db_session, email)


def test_create_comparison_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/comparisons",
        json={
            "name": "no token",
            "comparison_currency_code": "USD",
            "calculation_ids": [1, 2],
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_create_comparison_requires_at_least_two_calculation_ids(
    client: TestClient, db_session: Session
) -> None:
    email = "compare-too-few@example.com"
    token = _register_and_login(client, email)
    calc_a = _create_calculation(client, token, "150000.00")

    response = client.post(
        "/api/v1/comparisons",
        json={
            "name": "just one",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422

    _cleanup_calculations(db_session, [calc_a])
    _cleanup_user(db_session, email)


def test_create_comparison_rejects_duplicate_calculation_ids(
    client: TestClient, db_session: Session
) -> None:
    email = "compare-dupes@example.com"
    token = _register_and_login(client, email)
    calc_a = _create_calculation(client, token, "150000.00")

    response = client.post(
        "/api/v1/comparisons",
        json={
            "name": "duplicated",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a, calc_a],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422

    _cleanup_calculations(db_session, [calc_a])
    _cleanup_user(db_session, email)


def test_create_comparison_unknown_currency_returns_404(
    client: TestClient, db_session: Session
) -> None:
    email = "compare-unknown-currency@example.com"
    token = _register_and_login(client, email)
    calc_a = _create_calculation(client, token, "150000.00")
    calc_b = _create_calculation(client, token, "100000.00")

    response = client.post(
        "/api/v1/comparisons",
        json={
            "name": "bad currency",
            "comparison_currency_code": "ZZZ",
            "calculation_ids": [calc_a, calc_b],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_currency"

    _cleanup_calculations(db_session, [calc_a, calc_b])
    _cleanup_user(db_session, email)


def test_create_comparison_missing_exchange_rate_returns_422(
    client: TestClient, db_session: Session
) -> None:
    """India INR calculation compared in EUR: no INR<->EUR rate exists in
    the test DB (only the fixtured USD-anchored rates used elsewhere),
    exactly the same honest-error requirement the phase text calls out
    explicitly, reusing the exact error code POST /calculations already
    uses for the identical underlying condition.
    """
    email = "compare-missing-rate@example.com"
    token = _register_and_login(client, email)
    calc_a = _create_calculation(client, token, "150000.00", currency="USD", country="US")
    calc_b = _create_calculation(
        client, token, "1500000.00", currency="INR", country="IN", regime="new"
    )

    response = client.post(
        "/api/v1/comparisons",
        json={
            "name": "impossible currency",
            "comparison_currency_code": "EUR",
            "calculation_ids": [calc_a, calc_b],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_exchange_rate"

    _cleanup_calculations(db_session, [calc_a, calc_b])
    _cleanup_user(db_session, email)


def test_get_comparison_returns_persisted_detail(client: TestClient, db_session: Session) -> None:
    email = "compare-get-detail@example.com"
    token = _register_and_login(client, email)
    calc_a = _create_calculation(client, token, "150000.00")
    calc_b = _create_calculation(client, token, "100000.00")

    created = client.post(
        "/api/v1/comparisons",
        json={
            "name": "get me later",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a, calc_b],
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    response = client.get(
        f"/api/v1/comparisons/{created['id']}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "get me later"
    assert body["id"] == created["id"]
    assert body["entries"] == created["entries"]
    assert body["gap_analysis"] == created["gap_analysis"]

    _cleanup_comparison(db_session, created["id"])
    _cleanup_calculations(db_session, [calc_a, calc_b])
    _cleanup_user(db_session, email)


def test_get_someone_elses_comparison_returns_404(client: TestClient, db_session: Session) -> None:
    email_a = "compare-get-owner-a@example.com"
    email_b = "compare-get-owner-b@example.com"
    token_a = _register_and_login(client, email_a)
    token_b = _register_and_login(client, email_b)

    calc_a1 = _create_calculation(client, token_a, "150000.00")
    calc_a2 = _create_calculation(client, token_a, "100000.00")
    created = client.post(
        "/api/v1/comparisons",
        json={
            "name": "user A's comparison",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a1, calc_a2],
        },
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()

    response = client.get(
        f"/api/v1/comparisons/{created['id']}", headers={"Authorization": f"Bearer {token_b}"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "comparison_not_found"

    _cleanup_comparison(db_session, created["id"])
    _cleanup_calculations(db_session, [calc_a1, calc_a2])
    _cleanup_user(db_session, email_a)
    _cleanup_user(db_session, email_b)


def test_get_nonexistent_comparison_returns_404(client: TestClient, db_session: Session) -> None:
    email = "compare-get-nonexistent@example.com"
    token = _register_and_login(client, email)

    response = client.get(
        "/api/v1/comparisons/999999999", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "comparison_not_found"

    _cleanup_user(db_session, email)


def test_list_my_comparisons_only_shows_own_comparisons_in_order(
    client: TestClient, db_session: Session
) -> None:
    email_a = "compare-list-a@example.com"
    email_b = "compare-list-b@example.com"
    token_a = _register_and_login(client, email_a)
    token_b = _register_and_login(client, email_b)

    calc_a1 = _create_calculation(client, token_a, "150000.00")
    calc_a2 = _create_calculation(client, token_a, "100000.00")
    calc_b1 = _create_calculation(client, token_b, "60000.00")
    calc_b2 = _create_calculation(client, token_b, "70000.00")

    comparison_a = client.post(
        "/api/v1/comparisons",
        json={
            "name": "A's comparison",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_a1, calc_a2],
        },
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()
    comparison_b = client.post(
        "/api/v1/comparisons",
        json={
            "name": "B's comparison",
            "comparison_currency_code": "USD",
            "calculation_ids": [calc_b1, calc_b2],
        },
        headers={"Authorization": f"Bearer {token_b}"},
    ).json()

    response = client.get(
        "/api/v1/comparisons/mine", headers={"Authorization": f"Bearer {token_a}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == comparison_a["id"]
    assert body["items"][0]["name"] == "A's comparison"
    assert body["items"][0]["calculation_count"] == 2

    _cleanup_comparison(db_session, comparison_a["id"])
    _cleanup_comparison(db_session, comparison_b["id"])
    _cleanup_calculations(db_session, [calc_a1, calc_a2, calc_b1, calc_b2])
    _cleanup_user(db_session, email_a)
    _cleanup_user(db_session, email_b)
