"""Idempotent reference/taxonomy data seeding.

Run via `python -m app.reference_data.seed`. Every entity is upserted by
its natural business key (not blindly inserted), so this is safe to re-run
after a data correction — never duplicates, updates in place if the seed
data changed since the last run.

Seeds currencies, countries, job families, experience levels, and
employment types — static reference data with no research/citation
needed and no reason to change day to day. TaxRuleSet/TaxBracket seeding
(the real, cited India/US/Spain tax figures) is added on top of this
same mechanism separately, since that data does need citation and is
easy to get wrong.

Exchange rates are deliberately NOT seeded here (they were in Phase 2,
as two hardcoded illustrative rows - see Phase 6 for why that changed).
Unlike the entities above, a rate is inherently time-varying, sourced
data, not a static fact about the world - it belongs to
fetch_exchange_rates.py, which gets it from a real provider, not to a
committed seed file pretending to know today's USD/INR rate in advance.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.reference_data.models import (
    Country,
    Currency,
    EmploymentType,
    ExperienceLevel,
    JobFamily,
    TaxBracket,
    TaxComponent,
    TaxRuleSet,
)
from app.reference_data.upsert import upsert as _upsert

_CURRENCIES: list[dict[str, Any]] = [
    {"code": "INR", "name": "Indian Rupee", "symbol": "₹", "decimal_places": 2},
    {"code": "USD", "name": "US Dollar", "symbol": "$", "decimal_places": 2},
    {"code": "EUR", "name": "Euro", "symbol": "€", "decimal_places": 2},
]

_COUNTRIES: list[dict[str, Any]] = [
    {"code": "IN", "name": "India", "default_currency_code": "INR"},
    {"code": "US", "name": "United States", "default_currency_code": "USD"},
    {"code": "ES", "name": "Spain", "default_currency_code": "EUR"},
]

_JOB_FAMILIES: list[str] = [
    "Software Engineering",
    "Product Management",
    "Data & Analytics",
    "Design",
    "Sales",
]

_EXPERIENCE_LEVELS: list[dict[str, Any]] = [
    {"name": "Junior", "rank": 1},
    {"name": "Mid", "rank": 2},
    {"name": "Senior", "rank": 3},
    {"name": "Staff", "rank": 4},
    {"name": "Principal", "rank": 5},
]

_EMPLOYMENT_TYPES: list[dict[str, str]] = [
    {"code": "FULL_TIME", "name": "Full-time"},
    {"code": "CONTRACT", "name": "Contract"},
    {"code": "PART_TIME", "name": "Part-time"},
]

# Real, cited tax figures. Every source_note explicitly flags known
# simplifications rather than letting them look like oversights — see the
# Phase 2 research discussion for the full reasoning behind each one.
_TAX_RULE_SETS: list[dict[str, Any]] = [
    {
        "country_code": "US",
        "currency_code": "USD",
        "name": "US Federal Income Tax — Single Filer (TY2026)",
        "regime": None,
        "filing_status": "single",
        "standard_deduction": Decimal("16100.00"),
        "effective_date": date(2026, 1, 1),
        "end_date": None,
        "source_url": (
            "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-"
            "for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill"
        ),
        "source_note": (
            "Tax year 2026, not 2025: as of seeding (Aug 2026), 2025 is already "
            "a closed tax year, so 2026 is what actually governs current "
            "paychecks. Single filer only - other filing statuses (married "
            "filing jointly, head of household, etc.) not modeled. FICA "
            "(Social Security, Medicare, Additional Medicare surtax) seeded "
            "as separate components below; wage base and rates confirmed via "
            "https://www.irs.gov/taxtopics/tc751. The standard deduction "
            "reflects the 'One Big Beautiful Bill Act', which legislatively "
            "raised the 2025 figure mid-year from an originally-published "
            "$15,000 (Rev. Proc. 2024-40) to $15,750 - the 2026 figure of "
            "$16,100 (Rev. Proc. 2025-32) already incorporates this."
        ),
        "brackets": [
            (TaxComponent.INCOME_TAX, Decimal("0"), Decimal("12400"), Decimal("0.10000")),
            (TaxComponent.INCOME_TAX, Decimal("12400"), Decimal("50400"), Decimal("0.12000")),
            (TaxComponent.INCOME_TAX, Decimal("50400"), Decimal("105700"), Decimal("0.22000")),
            (TaxComponent.INCOME_TAX, Decimal("105700"), Decimal("201775"), Decimal("0.24000")),
            (TaxComponent.INCOME_TAX, Decimal("201775"), Decimal("256225"), Decimal("0.32000")),
            (TaxComponent.INCOME_TAX, Decimal("256225"), Decimal("640600"), Decimal("0.35000")),
            (TaxComponent.INCOME_TAX, Decimal("640600"), None, Decimal("0.37000")),
            (TaxComponent.SOCIAL_SECURITY, Decimal("0"), Decimal("184500"), Decimal("0.06200")),
            (TaxComponent.MEDICARE, Decimal("0"), None, Decimal("0.01450")),
            (TaxComponent.MEDICARE_ADDITIONAL_SURTAX, Decimal("200000"), None, Decimal("0.00900")),
        ],
    },
    {
        "country_code": "IN",
        "currency_code": "INR",
        "name": "India Income Tax — New Regime (FY 2025-26)",
        "regime": "new",
        "filing_status": None,
        "standard_deduction": Decimal("75000.00"),
        "effective_date": date(2025, 4, 1),
        "end_date": date(2026, 3, 31),
        "source_url": "https://www.incometaxindia.gov.in/w/tax-rates%E2%80%8B",
        "source_note": (
            "Primary source (incometaxindia.gov.in) returned HTTP 403 to "
            "automated fetch - unlike the US and Spain rule sets, this rests "
            "on cross-source convergence (Axis Max Life, Bajaj Finserv, "
            "ClearTax, Tax2win, plus one .gov.in source, newsonair.gov.in), "
            "not a direct primary-source read. Flagged as the "
            "least-directly-confirmed of the three countries seeded - to be "
            "personally verified against the official source. For "
            "individuals under 60 (senior/super-senior citizens have higher "
            "exemption thresholds, not modeled). Section 87A rebate (zeroes "
            "out liability below ~Rs12L total income) not modeled - it's a "
            "credit mechanism, structurally different from a slab or "
            "deduction."
        ),
        "brackets": [
            (TaxComponent.INCOME_TAX, Decimal("0"), Decimal("400000"), Decimal("0.00000")),
            (TaxComponent.INCOME_TAX, Decimal("400000"), Decimal("800000"), Decimal("0.05000")),
            (TaxComponent.INCOME_TAX, Decimal("800000"), Decimal("1200000"), Decimal("0.10000")),
            (TaxComponent.INCOME_TAX, Decimal("1200000"), Decimal("1600000"), Decimal("0.15000")),
            (TaxComponent.INCOME_TAX, Decimal("1600000"), Decimal("2000000"), Decimal("0.20000")),
            (TaxComponent.INCOME_TAX, Decimal("2000000"), Decimal("2400000"), Decimal("0.25000")),
            (TaxComponent.INCOME_TAX, Decimal("2400000"), None, Decimal("0.30000")),
        ],
    },
    {
        "country_code": "IN",
        "currency_code": "INR",
        "name": "India Income Tax — Old Regime (FY 2025-26)",
        "regime": "old",
        "filing_status": None,
        "standard_deduction": Decimal("50000.00"),
        "effective_date": date(2025, 4, 1),
        "end_date": date(2026, 3, 31),
        "source_url": "https://www.incometaxindia.gov.in/w/tax-rates%E2%80%8B",
        "source_note": (
            "Same sourcing caveat as the new regime rule set above (primary "
            "source blocked, cross-source verified - to be personally "
            "verified). For individuals under 60. Only the standard "
            "deduction is modeled - old regime's other deductions (80C, "
            "80D, HRA, LTA, etc.) are not; that's a materially larger "
            "scope. Section 87A rebate (zeroes out liability below ~Rs5L "
            "total income under this regime) not modeled, same reasoning "
            "as the new regime."
        ),
        "brackets": [
            (TaxComponent.INCOME_TAX, Decimal("0"), Decimal("250000"), Decimal("0.00000")),
            (TaxComponent.INCOME_TAX, Decimal("250000"), Decimal("500000"), Decimal("0.05000")),
            (TaxComponent.INCOME_TAX, Decimal("500000"), Decimal("1000000"), Decimal("0.20000")),
            (TaxComponent.INCOME_TAX, Decimal("1000000"), None, Decimal("0.30000")),
        ],
    },
    {
        "country_code": "IN",
        "currency_code": "INR",
        "name": "India Income Tax — New Regime (FY 2026-27)",
        "regime": "new",
        "filing_status": None,
        "standard_deduction": Decimal("75000.00"),
        "effective_date": date(2026, 4, 1),
        "end_date": date(2027, 3, 31),
        "source_url": "https://www.axismaxlife.com/blog/tax-savings/income-tax-slab-2026-27",
        "source_note": (
            "FY 2025-26's rule set above ended 2026-03-31; as of seeding "
            "(Aug 2026) FY 2026-27 is the currently-active fiscal year, so "
            "a distinct rule set is needed rather than silently extending "
            "the old one's end_date - each fiscal year is its own "
            "confirmed legal fact, even when unchanged. Union Budget 2026 "
            "explicitly confirmed no change to new regime slabs or the "
            "standard deduction vs FY 2025-26 (checked, not assumed - same "
            "discipline as the Spain 2025-vs-2026 check). Same sourcing "
            "caveat as the FY 2025-26 rule set: incometaxindia.gov.in "
            "blocked automated fetch, cross-source verified only - to be "
            "personally verified. Same Section 87A rebate and age-under-60 "
            "scope caveats as FY 2025-26 apply here too."
        ),
        "brackets": [
            (TaxComponent.INCOME_TAX, Decimal("0"), Decimal("400000"), Decimal("0.00000")),
            (TaxComponent.INCOME_TAX, Decimal("400000"), Decimal("800000"), Decimal("0.05000")),
            (TaxComponent.INCOME_TAX, Decimal("800000"), Decimal("1200000"), Decimal("0.10000")),
            (TaxComponent.INCOME_TAX, Decimal("1200000"), Decimal("1600000"), Decimal("0.15000")),
            (TaxComponent.INCOME_TAX, Decimal("1600000"), Decimal("2000000"), Decimal("0.20000")),
            (TaxComponent.INCOME_TAX, Decimal("2000000"), Decimal("2400000"), Decimal("0.25000")),
            (TaxComponent.INCOME_TAX, Decimal("2400000"), None, Decimal("0.30000")),
        ],
    },
    {
        "country_code": "IN",
        "currency_code": "INR",
        "name": "India Income Tax — Old Regime (FY 2026-27)",
        "regime": "old",
        "filing_status": None,
        "standard_deduction": Decimal("50000.00"),
        "effective_date": date(2026, 4, 1),
        "end_date": date(2027, 3, 31),
        "source_url": "https://www.axismaxlife.com/blog/tax-savings/income-tax-slab-2026-27",
        "source_note": (
            "Same FY 2026-27 currency reasoning as the new regime FY "
            "2026-27 rule set above. Union Budget 2026 confirmed no change "
            "to old regime slabs vs FY 2025-26. Same sourcing caveat "
            "(primary source blocked, cross-source verified - to be "
            "personally verified), same deductions-not-modeled and "
            "Section 87A caveats as FY 2025-26's old regime rule set."
        ),
        "brackets": [
            (TaxComponent.INCOME_TAX, Decimal("0"), Decimal("250000"), Decimal("0.00000")),
            (TaxComponent.INCOME_TAX, Decimal("250000"), Decimal("500000"), Decimal("0.05000")),
            (TaxComponent.INCOME_TAX, Decimal("500000"), Decimal("1000000"), Decimal("0.20000")),
            (TaxComponent.INCOME_TAX, Decimal("1000000"), None, Decimal("0.30000")),
        ],
    },
    {
        "country_code": "ES",
        "currency_code": "EUR",
        "name": "Spain IRPF (State Scale) + Seguridad Social (2026)",
        "regime": None,
        "filing_status": None,
        "standard_deduction": None,
        "effective_date": date(2026, 1, 1),
        "end_date": None,
        "source_url": (
            "https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-"
            "folletos/manuales-practicos/irpf-2025/c15-calculo-impuesto-"
            "determinacion-cuotas-integras/gravamen-base-liquidable-general/"
            "gravamen-estatal.html"
        ),
        "source_note": (
            "IRPF brackets are the STATE (national) scale only - Spain "
            "splits total IRPF liability between this state scale and a "
            "separate scale set independently by each of Spain's 17 "
            "autonomous communities; actual total liability depends on "
            "region of residence and is not modeled here, same reasoning as "
            "excluding US state tax. State scale confirmed unchanged for "
            "2026 vs 2025 (stable since a 2021 reform) - explicitly checked "
            "rather than assumed - so the 2025 practical-manual figures are "
            "cited as accurate for 2026 too. "
            "Seguridad Social: contingencias comunes (4.70%) and MEI (0.15% "
            "for 2026, up from 0.13% in 2025 per its legislated phase-in) "
            "combined into a single social_security rate of 4.85% - both "
            "share the same contribution base cap and nothing currently "
            "consumes them separately. Base cap is the 2026 figure "
            "(EUR 5,101.20/month = EUR 61,214.40/year, up from EUR 4,909.50/month "
            "in 2025, confirmed via Orden PJC/297/2026). Not modeled: "
            "unemployment insurance and vocational training contributions "
            "(additional, smaller employee-side percentages); the "
            "new-for-2026 tiered 'solidarity contribution' "
            "(1.15%/1.25%/1.46%) on earnings above the base cap; and the "
            "'minimo personal y familiar' personal/family exemption, which "
            "doesn't map onto a flat standard deduction (Spain applies the "
            "same progressive scale to the exemption amount separately and "
            "subtracts the result, mathematically different from a simple "
            "subtraction)."
        ),
        "brackets": [
            (TaxComponent.INCOME_TAX, Decimal("0"), Decimal("12450"), Decimal("0.09500")),
            (TaxComponent.INCOME_TAX, Decimal("12450"), Decimal("20200"), Decimal("0.12000")),
            (TaxComponent.INCOME_TAX, Decimal("20200"), Decimal("35200"), Decimal("0.15000")),
            (TaxComponent.INCOME_TAX, Decimal("35200"), Decimal("60000"), Decimal("0.18500")),
            (TaxComponent.INCOME_TAX, Decimal("60000"), Decimal("300000"), Decimal("0.22500")),
            (TaxComponent.INCOME_TAX, Decimal("300000"), None, Decimal("0.24500")),
            (TaxComponent.SOCIAL_SECURITY, Decimal("0"), Decimal("61214.40"), Decimal("0.04850")),
        ],
    },
]


def seed_currencies(session: Session) -> dict[str, Currency]:
    result: dict[str, Currency] = {}
    for data in _CURRENCIES:
        code = data["code"]
        values = {k: v for k, v in data.items() if k != "code"}
        result[code] = _upsert(session, Currency, {"code": code}, values)
    session.flush()
    return result


def seed_countries(session: Session, currencies: dict[str, Currency]) -> dict[str, Country]:
    result: dict[str, Country] = {}
    for data in _COUNTRIES:
        code = data["code"]
        currency = currencies[data["default_currency_code"]]
        values = {"name": data["name"], "default_currency_id": currency.id}
        result[code] = _upsert(session, Country, {"code": code}, values)
    session.flush()
    return result


def seed_job_families(session: Session) -> None:
    for name in _JOB_FAMILIES:
        _upsert(session, JobFamily, {"name": name}, {})
    session.flush()


def seed_experience_levels(session: Session) -> None:
    for data in _EXPERIENCE_LEVELS:
        _upsert(session, ExperienceLevel, {"name": data["name"]}, {"rank": data["rank"]})
    session.flush()


def seed_employment_types(session: Session) -> None:
    for data in _EMPLOYMENT_TYPES:
        _upsert(session, EmploymentType, {"code": data["code"]}, {"name": data["name"]})
    session.flush()


def seed_tax_rule_sets(
    session: Session, countries: dict[str, Country], currencies: dict[str, Currency]
) -> None:
    for data in _TAX_RULE_SETS:
        country = countries[data["country_code"]]
        currency = currencies[data["currency_code"]]
        natural_key = {
            "country_id": country.id,
            "regime": data["regime"],
            "filing_status": data["filing_status"],
            "effective_date": data["effective_date"],
        }
        values = {
            "currency_id": currency.id,
            "name": data["name"],
            "standard_deduction": data["standard_deduction"],
            "end_date": data["end_date"],
            "source_url": data["source_url"],
            "source_note": data["source_note"],
        }
        rule_set = _upsert(session, TaxRuleSet, natural_key, values)
        session.flush()

        for component, lower_bound, upper_bound, rate in data["brackets"]:
            bracket_key = {
                "tax_rule_set_id": rule_set.id,
                "component": component,
                "lower_bound": lower_bound,
            }
            bracket_values = {"upper_bound": upper_bound, "rate": rate}
            _upsert(session, TaxBracket, bracket_key, bracket_values)
    session.flush()


def seed_all(session: Session) -> None:
    currencies = seed_currencies(session)
    countries = seed_countries(session, currencies)
    seed_job_families(session)
    seed_experience_levels(session)
    seed_employment_types(session)
    seed_tax_rule_sets(session, countries, currencies)
    session.commit()


def main() -> None:
    with SessionLocal() as session:
        seed_all(session)


if __name__ == "__main__":
    main()
