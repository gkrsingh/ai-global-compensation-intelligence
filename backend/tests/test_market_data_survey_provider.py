"""Tests for the survey aggregation, driven by small in-memory CSVs -
the automated suite never touches the real 140MB release or the network.

The behaviour worth pinning down is the part that protects the reader: a
cell too thin to mean anything must not be published, and the filter must
exclude the responses it claims to exclude.
"""

import io
from decimal import Decimal
from pathlib import Path

from app.market_data.providers.stackoverflow_survey import (
    ALL_ROLES_CODE,
    StackOverflowSurveyProvider,
)
from app.market_data.providers.survey_base import (
    MIN_SAMPLE_FOR_ANY_FIGURE,
    MIN_SAMPLE_FOR_TAIL_PERCENTILES,
    SurveyCell,
)

_HEADER = "Country,Employment,ConvertedCompYearly,DevType,WorkExp"


def _csv(rows: list[str]) -> io.StringIO:
    return io.StringIO("\n".join([_HEADER, *rows]) + "\n")


def _rows(
    n: int,
    *,
    country: str = "United States of America",
    employment: str = "Employed",
    comp: int = 100000,
    dev: str = "Developer, full-stack",
    years: int | None = 7,
    spread: int = 1000,
) -> list[str]:
    # DevType values legitimately contain commas ("Developer, full-stack"),
    # so the field must be quoted - exactly as the real file does it.
    # Values are spread slightly so percentiles are meaningfully ordered
    # rather than all identical; pass spread=0 when every row must sit at
    # exactly `comp` (e.g. testing the implausible-value floor).
    return [
        f'{country},{employment},{comp + i * spread},"{dev}",{"" if years is None else years}'
        for i in range(n)
    ]


def _provider(rows: list[str]) -> StackOverflowSurveyProvider:
    return StackOverflowSurveyProvider(_csv(rows))


def _cell(
    provider: StackOverflowSurveyProvider, country: str, code: str, band: str | None
) -> SurveyCell:
    return next(
        c
        for c in provider.fetch_cells(country)
        if c.external_code == code
        and (c.experience_band.label if c.experience_band else None) == band
    )


def test_a_cell_below_the_minimum_sample_publishes_nothing_but_still_exists() -> None:
    """The suppression rule, and the reason the cell is still returned:
    an invisible gap looks like no gap at all, so the count must survive
    even when the figures do not.
    """
    provider = _provider(_rows(MIN_SAMPLE_FOR_ANY_FIGURE - 1))

    cell = _cell(provider, "US", "Developer, full-stack", None)

    assert cell.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE - 1
    assert cell.is_suppressed is True
    assert cell.percentile_50 is None
    assert cell.percentile_25 is None
    # Withheld, never zeroed - a wage of zero is a claim nobody made.
    assert cell.mean_value is None


def test_a_mid_sized_cell_publishes_the_centre_but_withholds_the_tails() -> None:
    """Two tiers, because the tails need more data than the centre. At
    this size a 10th percentile would rest on about three observations.
    """
    n = (MIN_SAMPLE_FOR_ANY_FIGURE + MIN_SAMPLE_FOR_TAIL_PERCENTILES) // 2
    provider = _provider(_rows(n))

    cell = _cell(provider, "US", "Developer, full-stack", None)

    assert cell.is_suppressed is False
    assert cell.percentile_25 is not None
    assert cell.percentile_50 is not None
    assert cell.percentile_75 is not None
    assert cell.percentile_10 is None
    assert cell.percentile_90 is None


def test_a_large_cell_publishes_the_full_distribution() -> None:
    provider = _provider(_rows(MIN_SAMPLE_FOR_TAIL_PERCENTILES))

    cell = _cell(provider, "US", "Developer, full-stack", None)

    assert cell.percentile_10 is not None
    assert cell.percentile_50 is not None
    assert cell.percentile_90 is not None
    # Ordering is a real property of a distribution, worth asserting.
    assert cell.percentile_10 < cell.percentile_50 < cell.percentile_90


def test_non_employed_respondents_are_excluded() -> None:
    """Students, the unemployed and freelancers report figures that are
    not comparable salaried wages. Excluding them is disclosed in the
    persisted methodology note, so it must actually happen.
    """
    rows = _rows(MIN_SAMPLE_FOR_ANY_FIGURE, comp=100000)
    rows += _rows(50, employment="Student", comp=1_000_000)

    provider = _provider(rows)
    cell = _cell(provider, "US", "Developer, full-stack", None)

    assert cell.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE
    # The million-dollar student rows would have dragged this far up.
    assert cell.percentile_50 is not None
    assert cell.percentile_50 < Decimal(200000)


def test_implausibly_low_annual_figures_are_excluded() -> None:
    """The raw file really does contain values of $1. They are data-entry
    errors, not salaries, and they contaminate the lower tail.
    """
    rows = _rows(MIN_SAMPLE_FOR_ANY_FIGURE, comp=100000)
    rows += _rows(20, comp=1, spread=0)

    provider = _provider(rows)
    cell = _cell(provider, "US", "Developer, full-stack", None)

    assert cell.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE


def test_responses_are_banded_by_reported_years_of_experience() -> None:
    rows = _rows(MIN_SAMPLE_FOR_ANY_FIGURE, years=1)
    rows += _rows(MIN_SAMPLE_FOR_ANY_FIGURE, years=8, comp=200000)

    provider = _provider(rows)

    junior = _cell(provider, "US", "Developer, full-stack", "0-2 yrs")
    senior_years = _cell(provider, "US", "Developer, full-stack", "6-10 yrs")

    assert junior.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE
    assert senior_years.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE
    assert junior.percentile_50 is not None and senior_years.percentile_50 is not None
    assert senior_years.percentile_50 > junior.percentile_50
    # Bands describe years, never a seniority title.
    assert junior.experience_band is not None
    assert junior.experience_band.label == "0-2 yrs"
    assert junior.experience_band.min_years == 0
    assert junior.experience_band.max_years == 2


def test_the_open_ended_top_band_has_no_maximum() -> None:
    provider = _provider(_rows(MIN_SAMPLE_FOR_ANY_FIGURE, years=25))

    cell = _cell(provider, "US", "Developer, full-stack", "11+ yrs")

    assert cell.experience_band is not None
    assert cell.experience_band.min_years == 11
    assert cell.experience_band.max_years is None


def test_a_response_without_years_still_counts_toward_the_role_figure() -> None:
    """Dropping it entirely would discard a real, usable data point; it
    simply cannot be placed in a band.
    """
    rows = _rows(MIN_SAMPLE_FOR_ANY_FIGURE, years=8)
    rows += _rows(5, years=None, comp=500000)

    provider = _provider(rows)
    role_cell = _cell(provider, "US", "Developer, full-stack", None)
    banded = _cell(provider, "US", "Developer, full-stack", "6-10 yrs")

    # Counted at the role level, where years are irrelevant...
    assert role_cell.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE + 5
    # ...but absent from every experience band, since it cannot be placed.
    assert banded.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE


def test_the_pooled_all_roles_cell_aggregates_across_dev_types() -> None:
    """This is what carries the seniority dimension in India and Spain,
    where role-by-experience cells collapse below the threshold.
    """
    rows = _rows(20, dev="Developer, back-end", years=8)
    rows += _rows(20, dev="Data engineer", years=8)

    provider = _provider(rows)
    pooled = _cell(provider, "US", ALL_ROLES_CODE, "6-10 yrs")

    # Neither role alone would clear the threshold; pooled they do.
    assert pooled.sample_size == 40
    assert pooled.is_suppressed is False


def test_an_uncovered_country_returns_no_cells() -> None:
    provider = _provider(_rows(MIN_SAMPLE_FOR_TAIL_PERCENTILES))

    assert provider.fetch_cells("FR") == []


def test_countries_are_aggregated_independently() -> None:
    rows = _rows(MIN_SAMPLE_FOR_ANY_FIGURE, country="India", comp=20000)
    rows += _rows(MIN_SAMPLE_FOR_ANY_FIGURE, country="Spain", comp=60000)

    provider = _provider(rows)
    india = _cell(provider, "IN", "Developer, full-stack", None)
    spain = _cell(provider, "ES", "Developer, full-stack", None)

    assert india.percentile_50 is not None and spain.percentile_50 is not None
    assert india.percentile_50 < spain.percentile_50


def test_provider_identity_is_stable() -> None:
    provider = _provider([])

    assert provider.name == "stackoverflow_survey"
    assert provider.taxonomy == "SO-DEVTYPE-2025"
    assert provider.reference_period_label == "2025 survey"


def test_provider_can_read_from_a_file_path(tmp_path: Path) -> None:
    """Production passes a Path (the downloaded release); only tests pass
    an open handle. The path branch is the one that actually runs in
    anger, so it gets exercised rather than assumed.
    """
    csv_file = tmp_path / "results.csv"
    csv_file.write_text(
        "\n".join([_HEADER, *_rows(MIN_SAMPLE_FOR_ANY_FIGURE)]) + "\n",
        encoding="utf-8",
    )

    provider = StackOverflowSurveyProvider(csv_file)
    cell = _cell(provider, "US", "Developer, full-stack", None)

    assert cell.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE
    assert cell.is_suppressed is False


def test_a_row_with_an_unparseable_compensation_is_skipped() -> None:
    """The raw file contains blanks and non-numeric values; they are
    ordinary missing data, not a reason to abort the whole read.
    """
    rows = _rows(MIN_SAMPLE_FOR_ANY_FIGURE)
    rows += ['United States of America,Employed,,"Developer, full-stack",7']
    rows += ['United States of America,Employed,not-a-number,"Developer, full-stack",7']

    provider = _provider(rows)
    cell = _cell(provider, "US", "Developer, full-stack", None)

    assert cell.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE


def test_a_row_with_no_devtype_is_skipped() -> None:
    rows = _rows(MIN_SAMPLE_FOR_ANY_FIGURE)
    rows += ["United States of America,Employed,150000,,7"]

    provider = _provider(rows)
    cell = _cell(provider, "US", "Developer, full-stack", None)

    assert cell.sample_size == MIN_SAMPLE_FOR_ANY_FIGURE
