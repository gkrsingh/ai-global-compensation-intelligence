from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.compensation.models import Calculation, CompensationInput

_PAYLOAD_TEMPLATE = {
    "country_code": "US",
    "filing_status": "single",
    "target_currency_code": "USD",
}


def _register_and_login(client: TestClient, email: str) -> str:
    password = "correct horse battery staple"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    access_token: str = login.json()["access_token"]
    return access_token


def _submit_calculation(
    client: TestClient, amount: str = "1000", access_token: str | None = None
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    response = client.post(
        "/api/v1/calculations",
        json={
            **_PAYLOAD_TEMPLATE,
            "components": [{"component_type": "base", "amount": amount, "currency_code": "USD"}],
        },
        headers=headers,
    )
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def _delete_calculation(db_session: Session, calc_id: int) -> None:
    calc = db_session.get(Calculation, calc_id)
    if calc is None:
        return
    comp_input_id = calc.compensation_input_id
    db_session.delete(calc)
    db_session.flush()
    comp_input = db_session.get(CompensationInput, comp_input_id)
    if comp_input is not None:
        db_session.delete(comp_input)
    db_session.commit()


def _delete_user_and_their_calculations(db_session: Session, email: str) -> None:
    user = db_session.scalar(select(User).where(User.email == email))
    if user is None:
        return
    calc_ids = list(
        db_session.scalars(select(Calculation.id).where(Calculation.user_id == user.id)).all()
    )
    for calc_id in calc_ids:
        _delete_calculation(db_session, calc_id)
    db_session.delete(user)
    db_session.commit()


def test_mine_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/calculations/mine")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_mine_returns_empty_for_a_user_with_no_calculations(
    client: TestClient, db_session: Session
) -> None:
    token = _register_and_login(client, "mine-empty-test@example.com")

    response = client.get("/api/v1/calculations/mine", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0

    _delete_user_and_their_calculations(db_session, "mine-empty-test@example.com")


def test_mine_returns_only_the_callers_own_calculations_most_recent_first(
    client: TestClient, db_session: Session
) -> None:
    token = _register_and_login(client, "mine-order-test@example.com")
    first = _submit_calculation(client, "1000", token)
    second = _submit_calculation(client, "2000", token)
    third = _submit_calculation(client, "3000", token)

    response = client.get("/api/v1/calculations/mine", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    returned_ids = [item["id"] for item in body["items"]]
    assert returned_ids == [third["id"], second["id"], first["id"]]

    _delete_user_and_their_calculations(db_session, "mine-order-test@example.com")


def test_mine_paginates_with_limit_and_offset(client: TestClient, db_session: Session) -> None:
    token = _register_and_login(client, "mine-page-test@example.com")
    submitted_ids = [_submit_calculation(client, str(1000 + i), token)["id"] for i in range(3)]

    first_page = client.get(
        "/api/v1/calculations/mine", params={"limit": 2, "offset": 0},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    second_page = client.get(
        "/api/v1/calculations/mine", params={"limit": 2, "offset": 2},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    assert first_page["total"] == 3
    assert second_page["total"] == 3
    assert len(first_page["items"]) == 2
    assert len(second_page["items"]) == 1
    returned_ids = [i["id"] for i in first_page["items"]] + [i["id"] for i in second_page["items"]]
    assert sorted(returned_ids) == sorted(submitted_ids)

    _delete_user_and_their_calculations(db_session, "mine-page-test@example.com")


def test_mine_never_includes_another_users_calculations(
    client: TestClient, db_session: Session
) -> None:
    """The explicit cross-user isolation test this feature needs - not
    just an assumption that the WHERE clause is obviously correct.
    """
    token_a = _register_and_login(client, "mine-cross-a-test@example.com")
    token_b = _register_and_login(client, "mine-cross-b-test@example.com")

    calc_a = _submit_calculation(client, "1000", token_a)
    calc_b = _submit_calculation(client, "2000", token_b)

    response_a = client.get(
        "/api/v1/calculations/mine", headers={"Authorization": f"Bearer {token_a}"}
    )
    response_b = client.get(
        "/api/v1/calculations/mine", headers={"Authorization": f"Bearer {token_b}"}
    )

    ids_a = [item["id"] for item in response_a.json()["items"]]
    ids_b = [item["id"] for item in response_b.json()["items"]]

    assert calc_a["id"] in ids_a
    assert calc_a["id"] not in ids_b
    assert calc_b["id"] in ids_b
    assert calc_b["id"] not in ids_a

    _delete_user_and_their_calculations(db_session, "mine-cross-a-test@example.com")
    _delete_user_and_their_calculations(db_session, "mine-cross-b-test@example.com")


def test_mine_never_includes_anonymous_calculations(
    client: TestClient, db_session: Session
) -> None:
    token = _register_and_login(client, "mine-anon-exclude-test@example.com")
    anonymous_calc = _submit_calculation(client, "999")
    own_calc = _submit_calculation(client, "1000", token)

    response = client.get("/api/v1/calculations/mine", headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == own_calc["id"]

    _delete_user_and_their_calculations(db_session, "mine-anon-exclude-test@example.com")
    _delete_calculation(db_session, anonymous_calc["id"])
