"""Seeds the JobFamily -> SOC occupation mappings for the US.

Every mapping below was checked against the real SOC-2018 occupation list
(BLS's own oe.occupation file, 1,104 detailed occupations) during Phase
10 research - the codes and the labels are the source's, not invented.

The honest headline: mapping quality varies a lot, and that is recorded
per row rather than smoothed over. This project's internal JobFamily
taxonomy has five broad categories built for a compensation calculator;
SOC is a national statistical classification built for labour-market
measurement. They were never designed to line up, and for some families
(Product Management especially) there is simply no good match. Storing
match_quality and a required match_note - and surfacing both in the UI -
is the alternative to either faking precision or dropping the family
silently.

Idempotent, natural-key upsert, exactly like reference_data/seed.py.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market_data.models import JobFamilyOccupationMapping, MatchQuality
from app.reference_data.models import Country, JobFamily
from app.reference_data.upsert import upsert as _upsert

TAXONOMY_SOC_2018 = "SOC-2018"

# A shared caveat that is true of EVERY OEWS mapping, kept in one place
# rather than repeated into each note: OEWS publishes a wage distribution
# per occupation and nothing about seniority or specialisation.
_NO_SENIORITY = (
    "OEWS publishes a wage distribution per occupation, with no breakdown by "
    "seniority or specialisation - locate yourself in the distribution rather "
    "than reading any percentile as a level."
)

_US_MAPPINGS: list[dict[str, Any]] = [
    {
        "job_family": "Software Engineering",
        "external_code": "151252",
        "external_label": "Software Developers",
        "match_quality": MatchQuality.CLOSE,
        "match_note": (
            "The closest published match for software engineering roles. Treats all "
            "software developers as one bucket: backend, frontend, mobile, ML and "
            f"platform work are not distinguished. {_NO_SENIORITY}"
        ),
    },
    {
        "job_family": "Software Engineering",
        "external_code": "151253",
        "external_label": "Software Quality Assurance Analysts and Testers",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "A separate, generally lower-paid occupation than software developer. "
            "Relevant if your role is QA/test engineering; misleading as a reference "
            f"point for software engineering generally. {_NO_SENIORITY}"
        ),
    },
    {
        "job_family": "Data & Analytics",
        "external_code": "152051",
        "external_label": "Data Scientists",
        "match_quality": MatchQuality.CLOSE,
        "match_note": (
            "A good match for data science roles. Data analysts and analytics "
            "engineers are frequently classified elsewhere (and generally paid less), "
            f"so this skews toward the data-science end of the family. {_NO_SENIORITY}"
        ),
    },
    {
        "job_family": "Data & Analytics",
        "external_code": "152041",
        "external_label": "Statisticians",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "Overlaps the quantitative end of this family but is a distinct "
            "profession, concentrated in different industries (government, pharma, "
            f"insurance) than most analytics roles. {_NO_SENIORITY}"
        ),
    },
    {
        "job_family": "Design",
        "external_code": "151255",
        "external_label": "Web and Digital Interface Designers",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "The nearest published match for product/UX design, but the bucket mixes "
            "interface design with web development work, so it is not a clean "
            f"product-design reference. {_NO_SENIORITY}"
        ),
    },
    {
        "job_family": "Design",
        "external_code": "271024",
        "external_label": "Graphic Designers",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "Graphic design is a distinct discipline from product/UX design and is "
            "generally paid substantially less. Included for completeness of the "
            f"family, not as a product-design benchmark. {_NO_SENIORITY}"
        ),
    },
    {
        "job_family": "Product Management",
        "external_code": "131082",
        "external_label": "Project Management Specialists",
        "match_quality": MatchQuality.POOR,
        "match_note": (
            "SOC-2018 has no product management occupation at all. Project management "
            "is a genuinely different role with different responsibilities and pay, so "
            "this is a weak proxy that likely understates product management "
            f"compensation in technology. Treat with real caution. {_NO_SENIORITY}"
        ),
    },
    {
        "job_family": "Sales",
        "external_code": "413091",
        "external_label": (
            "Sales Representatives of Services, Except Advertising, Insurance, "
            "Financial Services, and Travel"
        ),
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "Spans an extremely wide range of services sales roles across all "
            "industries, so technology sales specifically is not distinguishable. "
            "Note OEWS wages include commissions but exclude non-production bonuses, "
            f"which matters unusually much for sales roles. {_NO_SENIORITY}"
        ),
    },
    {
        "job_family": "Sales",
        "external_code": "112022",
        "external_label": "Sales Managers",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "Management-level sales roles only, so it sits well above individual "
            "contributor sales compensation and is not comparable to an IC offer. "
            f"{_NO_SENIORITY}"
        ),
    },
]


def seed_us_occupation_mappings(session: Session) -> int:
    """Upserts the US SOC mappings. Returns how many rows were written.

    Skips silently if the US country row or a referenced JobFamily is
    absent rather than creating them: reference_data/seed.py owns those,
    and inventing them here would let a typo quietly create a second,
    parallel taxonomy.
    """
    country = session.scalar(select(Country).where(Country.code == "US"))
    if country is None:
        return 0

    families = {
        family.name: family
        for family in session.scalars(select(JobFamily)).all()
    }

    written = 0
    for data in _US_MAPPINGS:
        family = families.get(data["job_family"])
        if family is None:
            continue
        _upsert(
            session,
            JobFamilyOccupationMapping,
            {
                "job_family_id": family.id,
                "country_id": country.id,
                "taxonomy": TAXONOMY_SOC_2018,
                "external_code": data["external_code"],
            },
            {
                "external_label": data["external_label"],
                "match_quality": data["match_quality"],
                "match_note": data["match_note"],
            },
        )
        written += 1

    session.flush()
    return written
