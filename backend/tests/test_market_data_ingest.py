"""Tests for the ingestion layer, driven by a stub MarketDataProvider -
never a live BLS call.

The properties worth pinning down are the ones that would corrupt the
data quietly: re-running must not duplicate rows, an occupation the
source publishes nothing for must be skipped rather than written as a row
of nulls, and the source-level provenance must actually be attached.
"""

from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.market_data.ingest import fetch_and_persist
from app.market_data.models import GeographicScope, MarketDataPoint
from app.market_data.providers.base import MarketDataProvider, OccupationWages


@pytest.fixture(autouse=True)
def _clear_market_data(db_session: Session) -> None:
    """These tests commit real rows to the shared test database, and
    several of them assert on the ABSENCE of a row - which a row left
    behind by an earlier test in the same session would silently break
    (it did, before this fixture existed). Clearing first makes each
    test's starting state explicit rather than order-dependent.
    """
    db_session.execute(delete(MarketDataPoint))
    db_session.commit()


class _StubProvider(MarketDataProvider):
    """Returns a fixed distribution for every code except those listed as
    empty, so tests can exercise both the normal and no-data paths.
    """

    def __init__(self, *, empty_codes: set[str] | None = None) -> None:
        self.empty_codes = empty_codes or set()
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "stub"

    @property
    def taxonomy(self) -> str:
        return "SOC-2018"

    def fetch_national_wages(self, external_code: str) -> OccupationWages:
        self.calls.append(external_code)
        if external_code in self.empty_codes:
            return OccupationWages(
                external_code=external_code, external_label=None, reference_year=2025
            )
        return OccupationWages(
            external_code=external_code,
            external_label=None,
            reference_year=2025,
            percentile_50=Decimal("123456"),
            mean_value=Decimal("130000"),
            employment_count=1000,
        )


def _points(db_session: Session) -> list[MarketDataPoint]:
    return list(
        db_session.scalars(
            select(MarketDataPoint).where(MarketDataPoint.taxonomy == "SOC-2018")
        ).all()
    )


def test_ingestion_attaches_source_provenance_and_the_variable_comp_caveat(
    db_session: Session,
) -> None:
    """The provider returns bare numbers; the citation, methodology and
    the equity/bonus exclusion are attached HERE. If this regressed, rows
    would persist as uncited figures, which the schema exists to forbid.
    """
    fetch_and_persist(db_session, _StubProvider())
    db_session.commit()

    point = db_session.scalar(
        select(MarketDataPoint).where(MarketDataPoint.external_code == "151252")
    )
    assert point is not None
    assert point.source_name.startswith("US Bureau of Labor Statistics")
    assert point.source_url
    assert "self-employed" in point.methodology_note.lower()
    assert point.excludes_variable_compensation is True
    assert "equity" in point.wage_definition_note.lower()
    assert point.geographic_scope == GeographicScope.NATIONAL
    assert point.reference_period_label == "May 2025"
    # Only vintages with a verified release date get one; never guessed.
    assert point.published_date is not None


def test_ingestion_uses_the_mapped_label_when_the_source_supplies_none(
    db_session: Session,
) -> None:
    """BLS v1 returns no occupation title in a plain data request. The
    row must still carry a real human label, taken from the verified
    mapping - not the bare numeric code, which is what this actually did
    before the bug was caught by running the real ingestion.
    """
    fetch_and_persist(db_session, _StubProvider())
    db_session.commit()

    point = db_session.scalar(
        select(MarketDataPoint).where(MarketDataPoint.external_code == "151252")
    )
    assert point is not None
    assert point.external_label == "Software Developers"


def test_reingesting_the_same_vintage_updates_in_place_rather_than_duplicating(
    db_session: Session,
) -> None:
    fetch_and_persist(db_session, _StubProvider())
    db_session.commit()
    first_count = len(_points(db_session))
    assert first_count > 0

    fetch_and_persist(db_session, _StubProvider())
    db_session.commit()

    assert len(_points(db_session)) == first_count


def test_an_occupation_with_no_published_data_is_skipped_not_written_as_nulls(
    db_session: Session,
) -> None:
    """Writing a row whose every figure is NULL would be a citation
    attached to nothing - and the schema's CHECK constraint would reject
    it anyway. Skipping is the correct behaviour, and the occupation is
    logged so a coverage gap is visible rather than silent.
    """
    provider = _StubProvider(empty_codes={"151252"})
    fetch_and_persist(db_session, provider)
    db_session.commit()

    assert "151252" in provider.calls  # it was attempted
    skipped = db_session.scalar(
        select(MarketDataPoint).where(MarketDataPoint.external_code == "151252")
    )
    assert skipped is None

    # Other occupations in the same run are unaffected.
    assert db_session.scalar(
        select(MarketDataPoint).where(MarketDataPoint.external_code == "152051")
    ) is not None


def test_only_mapped_occupations_are_fetched(db_session: Session) -> None:
    """There is no reason to pull all 1,104 SOC occupations when only the
    mapped ones are reachable from the UI.
    """
    provider = _StubProvider()
    fetch_and_persist(db_session, provider)
    db_session.commit()

    assert provider.calls
    # Every fetched code corresponds to a real seeded mapping.
    assert "151252" in provider.calls
    assert "999999" not in provider.calls
