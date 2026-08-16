"""Pure currency normalization and gap analysis for comparing already-
computed Calculations - no database access, mirroring the compensation/
services split (math here, I/O in orchestration.py). Crucially, this
module never touches tax or gross/net math itself: each Calculation's
figures are treated as fixed, already-correct inputs (Phase 3's engine
already computed them once, immutably) and are only ever CONVERTED here,
via the same convert_amount() used everywhere else in this project - not
recomputed, not re-derived.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.compensation.services.currency import convert_amount
from app.compensation.services.money import quantize_amount

# Ranked highest-value-wins. total_tax_amount is deliberately excluded:
# it's still shown per-entry, but "ahead" for tax means LOWEST, the
# opposite polarity of the other three - folding it into the same
# leader-takes-the-max logic here would silently mislabel the offer that
# pays the least tax as "behind". A genuine "lowest wins" ranking mode
# would need to be its own explicit thing, not implied by reusing this one.
GAP_METRICS: tuple[str, ...] = ("gross_amount", "total_compensation_amount", "net_amount")

# Matches fetch_exchange_rates.py's own _RATE_DECIMAL_PLACES - rate_used
# is either a rate straight from that table or its reciprocal, so display
# precision should match what's actually stored, not be arbitrarily
# shorter (losing precision) or longer (implying precision that isn't
# there).
_RATE_DECIMAL_PLACES = 8


@dataclass(frozen=True)
class CalculationSnapshot:
    """The subset of an already-persisted Calculation this module needs -
    built by the orchestration layer from real rows, never invented here."""

    calculation_id: int
    source_currency: str
    gross_amount: Decimal
    total_compensation_amount: Decimal
    total_tax_amount: Decimal | None
    net_amount: Decimal | None


@dataclass(frozen=True)
class ComparisonEntry:
    calculation_id: int
    source_currency: str
    # None when source_currency already equals the comparison currency -
    # no conversion happened, so there's no rate to report.
    rate_used: Decimal | None
    gross_amount: Decimal
    total_compensation_amount: Decimal
    total_tax_amount: Decimal | None
    net_amount: Decimal | None


@dataclass(frozen=True)
class GapEntry:
    calculation_id: int
    gap_absolute: Decimal
    # None when the leader's own amount is 0 - "the leader is X% ahead of
    # a $0 offer" is undefined, not 0% or infinite%.
    gap_percent: Decimal | None


@dataclass(frozen=True)
class MetricGapAnalysis:
    leader_calculation_id: int
    entries: list[GapEntry]


@dataclass(frozen=True)
class ComparisonResult:
    comparison_currency: str
    entries: list[ComparisonEntry]
    # Keyed by GAP_METRICS. A metric's value is None only when at least
    # one compared calculation has no figure for it at all (net_amount is
    # nullable - no matching tax rule set) - ranking a real number against
    # "unknown" would be a guess, not an honest comparison.
    gap_analysis: dict[str, MetricGapAnalysis | None]


def _display_rate(
    rates: dict[tuple[str, str], Decimal], from_currency: str, to_currency: str
) -> Decimal | None:
    """The rate actually applied, expressed as "1 from_currency =
    <rate> to_currency" regardless of which direction convert_amount found
    it in - for the entry's own `rate_used` field, so a reader never has
    to mentally invert a reciprocal to understand what was applied.
    """
    if from_currency == to_currency:
        return None
    direct = rates.get((from_currency, to_currency))
    if direct is not None:
        return direct
    inverse = rates.get((to_currency, from_currency))
    if inverse is not None:
        return quantize_amount(Decimal(1) / inverse, _RATE_DECIMAL_PLACES)
    return None


def _convert_optional(
    amount: Decimal | None,
    from_currency: str,
    to_currency: str,
    rates: dict[tuple[str, str], Decimal],
) -> Decimal | None:
    if amount is None:
        return None
    return convert_amount(amount, from_currency, to_currency, rates)


def _compute_gap(entries: list[ComparisonEntry], metric: str) -> MetricGapAnalysis | None:
    values: list[tuple[int, Decimal | None]] = [
        (e.calculation_id, getattr(e, metric)) for e in entries
    ]
    if any(value is None for _, value in values):
        return None

    non_null_values = [(calc_id, value) for calc_id, value in values if value is not None]
    leader_id, leader_value = max(non_null_values, key=lambda pair: pair[1])

    gaps = []
    for calc_id, value in non_null_values:
        gap_absolute = leader_value - value
        # Quantized to 2 places like every other displayed figure in this
        # project (ROUND_HALF_UP, not raw Decimal division's ~28
        # significant digits) - a percent gap of 43.71% is a display
        # figure just like a money amount, not a scientific ratio.
        gap_percent = (
            quantize_amount(gap_absolute / value * 100, 2) if value != 0 else None
        )
        gaps.append(
            GapEntry(calculation_id=calc_id, gap_absolute=gap_absolute, gap_percent=gap_percent)
        )

    return MetricGapAnalysis(leader_calculation_id=leader_id, entries=gaps)


def normalize_and_compare(
    snapshots: list[CalculationSnapshot],
    comparison_currency: str,
    rates: dict[tuple[str, str], Decimal],
) -> ComparisonResult:
    """Converts each snapshot's figures into `comparison_currency` (via
    convert_amount - raises MissingExchangeRateError, same as everywhere
    else, if a required pair genuinely isn't available) and computes gap
    analysis per GAP_METRICS. Order of `entries` matches the order of
    `snapshots` - the caller controls display order, this doesn't re-sort.
    """
    entries = [
        ComparisonEntry(
            calculation_id=s.calculation_id,
            source_currency=s.source_currency,
            rate_used=_display_rate(rates, s.source_currency, comparison_currency),
            gross_amount=convert_amount(
                s.gross_amount, s.source_currency, comparison_currency, rates
            ),
            total_compensation_amount=convert_amount(
                s.total_compensation_amount, s.source_currency, comparison_currency, rates
            ),
            total_tax_amount=_convert_optional(
                s.total_tax_amount, s.source_currency, comparison_currency, rates
            ),
            net_amount=_convert_optional(
                s.net_amount, s.source_currency, comparison_currency, rates
            ),
        )
        for s in snapshots
    ]

    gap_analysis = {metric: _compute_gap(entries, metric) for metric in GAP_METRICS}

    return ComparisonResult(
        comparison_currency=comparison_currency, entries=entries, gap_analysis=gap_analysis
    )
