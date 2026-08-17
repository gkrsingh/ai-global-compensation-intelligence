"""Integration tests for GET /market-context.

Two behaviours matter most here, and neither is the happy path.

The ABSENCE path: this project's stance is that "we have nothing citable
for this" must be said out loud, with a reason, rather than returned as an
empty list a UI could quietly render as blank space.

The MULTI-SOURCE path (Phase 11): two sources now cover the same US roles
and genuinely disagree, because they measure different things. They must
arrive separately, each with its own provenance, and must never be merged
or averaged into a figure neither source reported.
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


def _source(body: dict[str, Any], source_key: str) -> dict[str, Any] | None:
    return next((s for s in body["sources"] if s["source_key"] == source_key), None)


def test_returns_the_distribution_with_provenance_for_a_mapped_family(
    client: TestClient, software_family: JobFamily, ingested_market_data: None
) -> None:
    result = _get(client, software_family.id)

    assert result["status"] == 200, result["body"]
    body = result["body"]
    assert body["available"] is True
    assert body["unavailable_reason"] is None

    bls = _source(body, "bls_oews")
    assert bls is not None
    # Provenance lives on the source that WRAPS the occupations, so a
    # client cannot reach a figure without passing through it.
    assert bls["source_name"]
    assert bls["source_url"]
    assert bls["methodology_note"]
    assert bls["reference_period_label"].startswith("May ")
    assert bls["excludes_variable_compensation"] is True
    assert "equity" in bls["wage_definition_note"].lower()

    top = bls["occupations"][0]
    assert top["match_quality"] == "close"
    assert top["external_code"] == "151252"
    assert top["external_label"] == "Software Developers"
    assert top["match_note"]

    entry = top["entries"][0]
    assert entry["distribution"]["percentile_50"] is not None
    assert entry["distribution"]["percentile_10"] is not None
    # BLS publishes finished estimates, not microdata: it has an
    # employment estimate and no sample count, and the two are never
    # conflated.
    assert entry["sample_size"] is None
    assert entry["employment_count"] is not None
    assert entry["suppressed"] is False


def test_two_sources_for_the_same_role_arrive_separately_and_are_never_merged(
    client: TestClient,
    software_family: JobFamily,
    ingested_market_data: None,
    ingested_survey_data: None,
) -> None:
    """The core Phase 11 guarantee. BLS and the survey disagree because
    they measure different things (employer-reported base pay vs
    self-reported total compensation). Both must be present, attributed,
    and unreconciled - an average of the two would be a number neither
    source reported.
    """
    body = _get(client, software_family.id)["body"]

    assert len(body["sources"]) == 2
    bls = _source(body, "bls_oews")
    survey = _source(body, "stackoverflow_survey")
    assert bls is not None and survey is not None

    bls_median = Decimal(bls["occupations"][0]["entries"][0]["distribution"]["percentile_50"])
    survey_occ = next(
        o for o in survey["occupations"] if o["external_code"] == "Developer, full-stack"
    )
    survey_median = Decimal(survey_occ["entries"][0]["distribution"]["percentile_50"])

    # They really do differ - if they ever became equal this test would
    # stop proving anything, so assert the premise too.
    assert bls_median != survey_median

    # Each source carries its own methodology, and they say different
    # things about what counts as pay.
    assert bls["excludes_variable_compensation"] is True
    assert survey["excludes_variable_compensation"] is False
    assert bls["methodology_note"] != survey["methodology_note"]

    # Official statistics are presented first. Presentation order only -
    # not a claim that either source is more correct.
    assert body["sources"][0]["source_key"] == "bls_oews"


def test_india_now_has_survey_market_data(
    client: TestClient, software_family: JobFamily, ingested_survey_data: None
) -> None:
    """The gap Phase 11 exists to close. India had no market data at all
    after Phase 10; it now has real survey-derived figures, and they
    arrive with the representativeness caveat attached.
    """
    result = _get(client, software_family.id, country_code="IN")

    assert result["status"] == 200
    body = result["body"]
    assert body["available"] is True

    survey = _source(body, "stackoverflow_survey")
    assert survey is not None
    assert survey["occupations"]

    # The caveat the user specifically asked to be prominent: India's
    # sample skews toward product-company developers and reads high.
    assert survey["representativeness_note"] is not None
    assert "not representative" in survey["representativeness_note"].lower()


def test_experience_bands_are_reported_as_years_never_as_seniority_titles(
    client: TestClient, software_family: JobFamily, ingested_survey_data: None
) -> None:
    """No source publishes a years-to-title mapping, so the API must not
    imply one. Bands are years in, years out.
    """
    body = _get(client, software_family.id, country_code="IN")["body"]
    survey = _source(body, "stackoverflow_survey")
    assert survey is not None

    pooled = next(o for o in survey["occupations"] if o["external_code"] == "ALL")
    banded = [e for e in pooled["entries"] if e["experience_band_label"] is not None]
    assert banded, "pooled experience breakdown should be present"

    entry = banded[0]
    assert entry["experience_band_label"] == "6-10 yrs"
    assert entry["experience_min_years"] == 6
    assert entry["experience_max_years"] == 10
    # Not a level, and never described as one.
    serialized = str(body).lower()
    assert "senior" not in serialized
    assert "junior" not in serialized


def test_a_thin_cell_is_returned_as_suppressed_rather_than_omitted(
    client: TestClient, software_family: JobFamily, ingested_survey_data: None
) -> None:
    """Below-threshold cells must remain VISIBLE with their sample size.
    Dropping them would make a gap in the data indistinguishable from no
    gap at all.
    """
    body = _get(client, software_family.id, country_code="ES")["body"]
    survey = _source(body, "stackoverflow_survey")
    assert survey is not None

    thin = next(
        o for o in survey["occupations"] if o["external_code"] == "Developer, front-end"
    )
    entry = thin["entries"][0]
    assert entry["suppressed"] is True
    assert entry["sample_size"] == 12
    # Withheld, never zeroed.
    assert entry["distribution"]["percentile_50"] is None
    assert entry["distribution"]["percentile_10"] is None


def test_unknown_country_is_a_404_not_an_availability_answer(
    client: TestClient, software_family: JobFamily
) -> None:
    """A coverage gap and a caller error are different things."""
    result = _get(client, software_family.id, country_code="ZZ")

    assert result["status"] == 404
    assert result["body"]["error"]["code"] == "unknown_country"


def test_unknown_job_family_is_a_404(client: TestClient) -> None:
    result = _get(client, 999999)

    assert result["status"] == 404
    assert result["body"]["error"]["code"] == "unknown_job_family"


def test_a_family_with_no_mapping_says_so_distinctly(
    client: TestClient, db_session: Session, ingested_market_data: None
) -> None:
    """Sales has no counterpart in either taxonomy - SOC covers it but
    this project maps no sales occupations for it in every country, and a
    developer survey has none at all. The response must name that
    specific situation rather than implying the country is unsupported.
    """
    family = db_session.scalar(select(JobFamily).where(JobFamily.name == "Sales"))
    assert family is not None

    result = _get(client, family.id, country_code="ES")

    assert result["status"] == 200
    body = result["body"]
    assert body["available"] is False
    assert body["sources"] == []
    assert body["unavailable_reason"]


def test_a_family_mapped_but_with_no_ingested_data_says_so_distinctly(
    client: TestClient, db_session: Session
) -> None:
    """The family IS mapped, but nothing has been ingested for it. Must
    not be conflated with 'this country is unsupported', which would
    misdescribe an operational gap as a permanent one.
    """
    country = db_session.scalar(select(Country).where(Country.code == "US"))
    family = db_session.scalar(select(JobFamily).where(JobFamily.name == "Design"))
    assert country is not None and family is not None

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
            "taxonomy": m.taxonomy,
            "external_code": m.external_code,
            "external_label": m.external_label,
            "match_quality": m.match_quality,
            "match_note": m.match_note,
        }
        for m in real_design
    ]
    for m in real_design:
        db_session.delete(m)
    mapping = JobFamilyOccupationMapping(
        job_family_id=family.id,
        country_id=country.id,
        taxonomy=TAXONOMY_SOC_2018,
        external_code="999998",
        external_label="Fictional Uningested Occupation",
        match_quality=MatchQuality.BROAD,
        match_note="Test-only mapping with deliberately no ingested data.",
    )
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
                    job_family_id=family.id, country_id=country.id, **data
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
        sample_size=None,
        experience_band_label=None,
        experience_min_years=None,
        experience_max_years=None,
        reference_period=date(2025, 5, 1),
        reference_period_label="May 2025",
        published_date=date(2026, 5, 15),
        source_key="bls_oews",
        source_name="Test Source",
        source_url="https://example.invalid/",
        methodology_note="Test methodology note.",
        excludes_variable_compensation=True,
        wage_definition_note="Test wage definition, excludes equity.",
        representativeness_note=None,
    )
    db_session.add_all([mapping, point])
    db_session.commit()

    try:
        body = _get(client, family.id)["body"]
        source = _source(body, "bls_oews")
        assert source is not None
        match = next(o for o in source["occupations"] if o["external_code"] == "999997")
        distribution = match["entries"][0]["distribution"]
        assert distribution["percentile_50"] == "100000.00"
        assert distribution["percentile_10"] is None
        assert distribution["percentile_90"] is None
        assert distribution["mean_value"] is None
    finally:
        db_session.delete(point)
        db_session.delete(mapping)
        db_session.commit()
