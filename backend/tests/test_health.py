from fastapi.testclient import TestClient


def test_health_returns_ok_when_database_reachable(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["api"] == "ok"
    assert body["checks"]["database"] == "ok"


def test_health_reports_degraded_when_database_unreachable(
    unreachable_db_client: TestClient,
) -> None:
    response = unreachable_db_client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["api"] == "ok"
    assert body["checks"]["database"] == "error"
