from fastapi.testclient import TestClient


def test_list_countries(client: TestClient) -> None:
    response = client.get("/api/v1/countries")

    assert response.status_code == 200
    countries = {c["code"]: c for c in response.json()}
    assert countries.keys() >= {"IN", "US", "ES"}
    assert countries["IN"]["default_currency"]["code"] == "INR"
    assert countries["US"]["default_currency"]["code"] == "USD"
    assert countries["ES"]["default_currency"]["code"] == "EUR"


def test_list_tax_rule_sets_for_india_includes_both_regimes_and_years(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/countries/IN/tax-rule-sets")

    assert response.status_code == 200
    rule_sets = response.json()
    regimes_and_years = {(rs["regime"], rs["effective_date"]) for rs in rule_sets}
    assert ("new", "2025-04-01") in regimes_and_years
    assert ("old", "2025-04-01") in regimes_and_years
    assert ("new", "2026-04-01") in regimes_and_years
    assert ("old", "2026-04-01") in regimes_and_years


def test_list_tax_rule_sets_includes_full_bracket_data(client: TestClient) -> None:
    response = client.get("/api/v1/countries/US/tax-rule-sets")

    assert response.status_code == 200
    rule_sets = response.json()
    assert len(rule_sets) == 1
    brackets = rule_sets[0]["tax_brackets"]

    top_income_bracket = next(
        b
        for b in brackets
        if b["component"] == "income_tax" and b["upper_bound"] is None
    )
    assert top_income_bracket["rate"] == "0.37000"

    social_security = next(b for b in brackets if b["component"] == "social_security")
    assert social_security["upper_bound"] == "184500.00"


def test_list_tax_rule_sets_lowercases_country_code(client: TestClient) -> None:
    response = client.get("/api/v1/countries/es/tax-rule-sets")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_tax_rule_sets_404s_for_unknown_country(client: TestClient) -> None:
    response = client.get("/api/v1/countries/ZZ/tax-rule-sets")
    assert response.status_code == 404
