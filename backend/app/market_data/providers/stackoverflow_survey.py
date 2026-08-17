"""Aggregates the Stack Overflow Annual Developer Survey microdata into
publishable wage distributions.

Everything here was verified against the real 2025 release (49,191
responses, 140MB, 172 columns) during Phase 11 research, not assumed:

- Licensed ODbL 1.0 (database) / DbCL 1.0 (contents), which genuinely
  permits redistribution and derived works. ODbL is copyleft: if this
  app is ever publicly deployed, the derived aggregates must be offered
  under ODbL too. Recorded in the README, not just here.
- ConvertedCompYearly is Stack Overflow's own USD normalisation, using
  "the exchange rate on June 25, 2025" per their published methodology.
  We do not re-convert; re-deriving currency ourselves would replace a
  documented figure with an undocumented one.
- The 2025 Employment column does NOT distinguish full- from part-time.
  An earlier attempt to filter on EmploymentAddl for "full-time" was
  wrong and was caught by measuring it: that column records ADDITIONAL
  activities, and "Attending school (full-time)" matched, silently
  selecting students and dragging the US median from $150,000 to
  $67,500. The filter below uses Employment == "Employed" instead.

This computes real percentiles from real individual responses, which is
ordinary statistics on reported data - not the fabrication this project
forbids. What it must never do is publish a cell too thin to mean
anything, which is what the thresholds in survey_base.py are for.
"""

import csv
import statistics
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import IO

from app.market_data.providers.survey_base import (
    MIN_SAMPLE_FOR_ANY_FIGURE,
    MIN_SAMPLE_FOR_TAIL_PERCENTILES,
    ExperienceBand,
    SurveyCell,
    SurveyDataProvider,
)

SOURCE_KEY = "stackoverflow_survey"
SOURCE_NAME = "Stack Overflow Annual Developer Survey 2025"
SOURCE_URL = "https://survey.stackoverflow.co/2025/"
TAXONOMY = "SO-DEVTYPE-2025"
REFERENCE_PERIOD_LABEL = "2025 survey"

# The pseudo-occupation for "every developer role pooled". Exists because
# role x experience cells collapse below the threshold in India and Spain,
# while the pooled experience breakdown stays comfortably above it - so
# this is what makes a seniority dimension available outside the US at
# all. Labelled explicitly so it can never read as a specific role.
ALL_ROLES_CODE = "ALL"
ALL_ROLES_LABEL = "All developer roles (pooled)"

# Survey country names -> ISO codes this project uses elsewhere.
_COUNTRY_BY_NAME = {
    "United States of America": "US",
    "India": "IN",
    "Spain": "ES",
}

# Both parts of the filter are disclosed in the persisted methodology
# note, because each one changes the published numbers:
#
# - Employment == "Employed" excludes students, the unemployed, the
#   retired, and independent contractors/freelancers, whose reported
#   annual figure is not a comparable salaried wage.
# - The floor removes obvious data-entry errors. The raw file really does
#   contain values of $1, and 1.3-3.8% of responses fall under $1,000/yr,
#   which is not a plausible annual full-time salary in any of these
#   three countries. Measured effect: medians barely move (US stayed at
#   $150,000) while contaminated tails clean up (US p10 $62,640 ->
#   $80,000), which is exactly the signature of removing junk rather than
#   reshaping the distribution.
_EMPLOYED_VALUE = "Employed"
MIN_PLAUSIBLE_ANNUAL_USD = Decimal(1000)

_BANDS: tuple[ExperienceBand, ...] = (
    ExperienceBand(label="0-2 yrs", min_years=0, max_years=2),
    ExperienceBand(label="3-5 yrs", min_years=3, max_years=5),
    ExperienceBand(label="6-10 yrs", min_years=6, max_years=10),
    ExperienceBand(label="11+ yrs", min_years=11, max_years=None),
)

# Free-text answers in this survey exceed Python's default 128KB field
# cap, which aborts the read partway through and would silently yield a
# truncated dataset.
_CSV_FIELD_LIMIT = 10_000_000


def _band_for(years: float) -> ExperienceBand | None:
    for band in _BANDS:
        if band.max_years is None:
            if years >= band.min_years:
                return band
        elif band.min_years <= years <= band.max_years:
            return band
    return None


def _percentile(sorted_values: list[Decimal], p: int) -> Decimal:
    """Linear-interpolation percentile over the sample.

    statistics.quantiles with method="inclusive" describes the sample
    itself rather than estimating a population quantile, which is what is
    wanted here: these figures are reported as "the middle of the
    responses we received", not as an inference about all developers.
    """
    cuts = statistics.quantiles(sorted_values, n=100, method="inclusive")
    return cuts[p - 1]


def _quantize(value: Decimal) -> Decimal:
    # Whole units. The inputs are self-reported round-ish figures already
    # converted between currencies; cents would be invented precision.
    return value.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _summarize(values: list[Decimal]) -> dict[str, Decimal | None]:
    """Apply the two-tier suppression rule to one cell's responses."""
    n = len(values)
    if n < MIN_SAMPLE_FOR_ANY_FIGURE:
        # Nothing at all is publishable. The caller still emits the cell
        # so the shortfall is visible with its sample size attached.
        return {
            "percentile_10": None, "percentile_25": None, "percentile_50": None,
            "percentile_75": None, "percentile_90": None, "mean_value": None,
        }

    ordered = sorted(values)
    result: dict[str, Decimal | None] = {
        "percentile_25": _quantize(_percentile(ordered, 25)),
        "percentile_50": _quantize(_percentile(ordered, 50)),
        "percentile_75": _quantize(_percentile(ordered, 75)),
        "mean_value": _quantize(sum(ordered, Decimal(0)) / n),
        # Tails stay withheld until the sample can carry them.
        "percentile_10": None,
        "percentile_90": None,
    }
    if n >= MIN_SAMPLE_FOR_TAIL_PERCENTILES:
        result["percentile_10"] = _quantize(_percentile(ordered, 10))
        result["percentile_90"] = _quantize(_percentile(ordered, 90))
    return result


class StackOverflowSurveyProvider(SurveyDataProvider):
    """Reads the survey CSV once and serves aggregated cells per country.

    Takes a path or an open handle rather than downloading: the release is
    a ~140MB annual file, so fetching it is a deliberate operator step
    (see app/market_data/ingest_survey.py), never something that happens
    on a request. Tests pass a small in-memory handle, so the automated
    suite never touches the real file or the network.
    """

    def __init__(self, source: Path | str | IO[str]) -> None:
        self._by_country: dict[str, list[tuple[str, float | None, Decimal]]] = defaultdict(list)
        self._load(source)

    @property
    def name(self) -> str:
        return SOURCE_KEY

    @property
    def taxonomy(self) -> str:
        return TAXONOMY

    @property
    def reference_period_label(self) -> str:
        return REFERENCE_PERIOD_LABEL

    def _load(self, source: Path | str | IO[str]) -> None:
        csv.field_size_limit(_CSV_FIELD_LIMIT)
        if isinstance(source, (str, Path)):
            with open(source, newline="", encoding="utf-8-sig") as handle:
                self._consume(handle)
        else:
            self._consume(source)

    def _consume(self, handle: IO[str]) -> None:
        for row in csv.DictReader(handle):
            country = _COUNTRY_BY_NAME.get((row.get("Country") or "").strip())
            if country is None:
                continue
            if (row.get("Employment") or "").strip() != _EMPLOYED_VALUE:
                continue
            try:
                comp = Decimal((row.get("ConvertedCompYearly") or "").strip())
            except Exception:
                continue
            if comp < MIN_PLAUSIBLE_ANNUAL_USD:
                continue

            dev = (row.get("DevType") or "").strip()
            if not dev:
                continue
            try:
                years: float | None = float((row.get("WorkExp") or "").strip())
            except ValueError:
                # Keeps counting toward role-level figures; simply cannot
                # be placed in an experience band. Dropping the response
                # entirely would discard a real, usable data point.
                years = None
            self._by_country[country].append((dev, years, comp))

    def fetch_cells(self, country_code: str) -> list[SurveyCell]:
        responses = self._by_country.get(country_code.upper())
        if not responses:
            return []

        by_role: defaultdict[str, list[Decimal]] = defaultdict(list)
        by_role_band: defaultdict[tuple[str, str], list[Decimal]] = defaultdict(list)
        by_band: defaultdict[str, list[Decimal]] = defaultdict(list)

        for dev, years, comp in responses:
            by_role[dev].append(comp)
            if years is None:
                continue
            band = _band_for(years)
            if band is None:
                continue
            by_role_band[(dev, band.label)].append(comp)
            by_band[band.label].append(comp)

        bands_by_label = {b.label: b for b in _BANDS}
        cells: list[SurveyCell] = []

        for dev, values in by_role.items():
            cells.append(
                SurveyCell(
                    external_code=dev,
                    external_label=dev,
                    experience_band=None,
                    sample_size=len(values),
                    **_summarize(values),
                )
            )

        for (dev, band_label), values in by_role_band.items():
            cells.append(
                SurveyCell(
                    external_code=dev,
                    external_label=dev,
                    experience_band=bands_by_label[band_label],
                    sample_size=len(values),
                    **_summarize(values),
                )
            )

        # The pooled-across-roles experience breakdown, which is what
        # carries the seniority dimension in India and Spain.
        for band_label, values in by_band.items():
            cells.append(
                SurveyCell(
                    external_code=ALL_ROLES_CODE,
                    external_label=ALL_ROLES_LABEL,
                    experience_band=bands_by_label[band_label],
                    sample_size=len(values),
                    **_summarize(values),
                )
            )

        return cells
