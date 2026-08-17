"""Integration tests for GET /market-context.

The behaviour most worth pinning down here is not the happy path but the
ABSENCE path: this project's whole stance on market data is that "we have
nothing citable for this" must be said out loud, with a reason, rather
than returned as an empty list the UI could quietly render as nothing.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market_data.models import (
    GeographicScope,
    JobFamilyOccupationMapping,
    MarketDataPoint,
    MatchQuality,
)
from app.market_data.seed import TAXONOMY_SOC_2018
from app.reference_data.models import Country, Currency, JobFamily


@pytest.fixture()
def software_family(db_session: Session) -> JobFamily:
    family = db_session.scalar(select(JobFamily).where(JobFamily.name == "Software Engineering"))
    assert family is not None, "reference data seed must provide Software Engineering"
    return family


def _get(
    client: TestClient, job_family_id: int, country_code: str = "US"
) -> dict[str, Any]:
    response = client.get(
        "/api/v1/market-context",
        params={"job_family_id": job_family_id, "country_code": country_code},
    )
    return {"status": response.status_code, "body": response.json()}


def test_returns_the_distribution_with_provenance_for_a_mapped_family(
    client: TestClient, db_session: Session, software_family: JobFamily, ingested_market_data: None
) -> None:
    result = _get(client, software_family.id)

    assert result["status"] == 200, result["body"]
    body = result["body"]
    assert body["available"] is True
    assert body["unavailable_reason"] is None
    assert body["occupations"], "seeded mappings + ingested data should yield occupations"

    top = body["occupations"][0]
    # Best-quality match leads, so the most defensible figure is first.
    assert top["match_quality"] == "close"
    assert top["external_code"] == "151252"
    assert top["external_label"] == "Software Developers"

    # A distribution, never a single number.
    distribution = top["distribution"]
    assert distribution["percentile_50"] is not None
    assert distribution["percentile_10"] is not None
    assert distribution["percentile_90"] is not None

    # Provenance and caveats travel WITH the figures, in the same object.
    assert top["source_name"]
    assert top["source_url"]
    assert top["methodology_note"]
    assert top["reference_period_label"].startswith("May ")
    assert top["excludes_variable_compensation"] is True
    assert "equity" in top["wage_definition_note"].lower()
    assert top["match_note"]


def test_a_poorly_matched_family_is_returned_but_labeled_poor(
    client: TestClient, db_session: Session, ingested_market_data: None
) -> None:
    """Product Management has no SOC-2018 equivalent at all. The mapping
    is deliberately kept and labeled rather than dropped - but it must
    never arrive looking as trustworthy as a close match.
    """
    family = db_session.scalar(select(JobFamily).where(JobFamily.name == "Product Management"))
    assert family is not None

    result = _get(client, family.id)

    assert result["status"] == 200
    occupations = result["body"]["occupations"]
    assert occupations
    assert all(o["match_quality"] == "poor" for o in occupations)
    assert "no product management occupation" in occupations[0]["match_note"].lower()


def test_a_country_with_no_coverage_says_so_explicitly(
    client: TestClient, software_family: JobFamily
) -> None:
    """India is genuinely unsupported (see README). The API must state
    that with a reason rather than returning an empty list, which a UI
    could render as blank space indistinguishable from a loading bug.
    """
    result = _get(client, software_family.id, country_code="IN")

    assert result["status"] == 200
    body = result["body"]
    assert body["available"] is False
    assert body["occupations"] == []
    assert body["unavailable_reason"]
    assert "no market compensation data" in body["unavailable_reason"].lower()


def test_unknown_country_is_a_404_not_an_availability_answer(
    client: TestClient, software_family: JobFamily
) -> None:
    """A coverage gap and a caller error are different things: 'we have
    no data for India' is a real answer, 'ZZ is not a country' is a bad
    request.
    """
    result = _get(client, software_family.id, country_code="ZZ")

    assert result["status"] == 404
    assert result["body"]["error"]["code"] == "unknown_country"


def test_unknown_job_family_is_a_404(client: TestClient) -> None:
    result = _get(client, 999999)

    assert result["status"] == 404
    assert result["body"]["error"]["code"] == "unknown_job_family"


def test_a_family_mapped_but_with_no_ingested_data_says_so_distinctly(
    client: TestClient, db_session: Session
) -> None:
    """Third distinct absence case: the family IS mapped, but nothing has
    been ingested for it. Must not be conflated with 'this country is
    unsupported', which would misdescribe a purely operational gap as a
    permanent one.
    """
    country = db_session.scalar(select(Country).where(Country.code == "US"))
    family = db_session.scalar(select(JobFamily).where(JobFamily.name == "Design"))
    assert country is not None and family is not None

    mapping = JobFamilyOccupationMapping(
        job_family_id=family.id,
        country_id=country.id,
        taxonomy=TAXONOMY_SOC_2018,
        external_code="999998",
        external_label="Fictional Uningested Occupation",
        match_quality=MatchQuality.BROAD,
        match_note="Test-only mapping with deliberately no ingested data.",
    )
    # Remove the real Design mappings for the duration of this test so the
    # only mapping left is the uningested one.
    real_design = list(
        db_session.scalars(
            select(JobFamilyOccupationMapping).where(
                JobFamilyOccupationMapping.job_family_id == family.id,
                JobFamilyOccupationMapping.country_id == country.id,
            )
        ).all()
    )
    saved = [
        {
            "external_code": m.external_code,
            "external_label": m.external_label,
            "match_quality": m.match_quality,
            "match_note": m.match_note,
        }
        for m in real_design
    ]
    for m in real_design:
        db_session.delete(m)
    db_session.add(mapping)
    db_session.commit()

    try:
        result = _get(client, family.id)
        assert result["status"] == 200
        body = result["body"]
        assert body["available"] is False
        assert "no wage data has been ingested" in body["unavailable_reason"].lower()
    finally:
        db_session.delete(mapping)
        for data in saved:
            db_session.add(
                JobFamilyOccupationMapping(
                    job_family_id=family.id, country_id=country.id,
                    taxonomy=TAXONOMY_SOC_2018, **data
                )
            )
        db_session.commit()


def test_a_percentile_the_source_suppressed_stays_null_in_the_response(
    client: TestClient, db_session: Session
) -> None:
    """A figure the source never published must reach the client as null,
    not 0 - the API contract equivalent of the provider-level guarantee.
    """
    country = db_session.scalar(select(Country).where(Country.code == "US"))
    currency = db_session.scalar(select(Currency).where(Currency.code == "USD"))
    family = db_session.scalar(select(JobFamily).where(JobFamily.name == "Sales"))
    assert country is not None and currency is not None and family is not None

    mapping = JobFamilyOccupationMapping(
        job_family_id=family.id,
        country_id=country.id,
        taxonomy=TAXONOMY_SOC_2018,
        external_code="999997",
        external_label="Occupation With Suppressed Percentiles",
        match_quality=MatchQuality.BROAD,
        match_note="Test-only mapping exercising suppressed percentiles.",
    )
    point = MarketDataPoint(
        country_id=country.id,
        currency_id=currency.id,
        taxonomy=TAXONOMY_SOC_2018,
        external_code="999997",
        external_label="Occupation With Suppressed Percentiles",
        geographic_scope=GeographicScope.NATIONAL,
        area_code="0000000",
        area_name="National",
        percentile_10=None,
        percentile_25=None,
        percentile_50=Decimal("100000.00"),
        percentile_75=None,
        percentile_90=None,
        mean_value=None,
        employment_count=None,
        reference_period=date(2025, 5, 1),
        reference_period_label="May 2025",
        published_date=date(2026, 5, 15),
        source_name="Test Source",
        source_url="https://example.invalid/",
        methodology_note="Test methodology note.",
        excludes_variable_compensation=True,
        wage_definition_note="Test wage definition, excludes equity.",
    )
    db_session.add_all([mapping, point])
    db_session.commit()

    try:
        result = _get(client, family.id)
        assert result["status"] == 200
        match = next(
            o for o in result["body"]["occupations"] if o["external_code"] == "999997"
        )
        assert match["distribution"]["percentile_50"] == "100000.00"
        assert match["distribution"]["percentile_10"] is None
        assert match["distribution"]["percentile_90"] is None
        assert match["distribution"]["mean_value"] is None
    finally:
        db_session.delete(point)
        db_session.delete(mapping)
        db_session.commit()
