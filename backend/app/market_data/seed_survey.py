"""Seeds the JobFamily -> Stack Overflow DevType mappings (Phase 11).

The survey's DevType is its own role taxonomy, not SOC/CNO/NCO - which is
exactly what Phase 10's `taxonomy` column was built to accommodate, so
this needed no new mechanism, only new rows.

Better than SOC in one place: SOC-2018 has no product management
occupation at all, so Phase 10 had to settle for a POOR match against
Project Management Specialists; the survey asks respondents directly
whether they are a product manager, which is a genuine CLOSE match.
Worse in another: the survey only covers developer-adjacent roles, so
Sales has no counterpart here and deliberately gets no rows - an absent
mapping is the honest outcome, not an oversight.

The same mappings apply to all three covered countries, because DevType
is a global survey field rather than a national classification. Rows are
still written per country to match the country-scoped table, so a country
could diverge later without a schema change.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market_data.models import JobFamilyOccupationMapping, MatchQuality
from app.market_data.providers.stackoverflow_survey import (
    ALL_ROLES_CODE,
    ALL_ROLES_LABEL,
    TAXONOMY,
)
from app.reference_data.models import Country, JobFamily
from app.reference_data.upsert import upsert as _upsert

SURVEY_COUNTRIES = ("US", "IN", "ES")

_SELF_REPORTED = (
    "Self-reported by survey respondents rather than employer-reported, and drawn "
    "from people who read Stack Overflow - a narrower, more engaged population than "
    "the workforce as a whole."
)

_MAPPINGS: list[dict[str, Any]] = [
    {
        "job_family": "Software Engineering",
        "external_code": "Developer, full-stack",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as full-stack developers. {_SELF_REPORTED}",
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Developer, back-end",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as back-end developers. {_SELF_REPORTED}",
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Developer, front-end",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as front-end developers. {_SELF_REPORTED}",
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Developer, mobile",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as mobile developers. {_SELF_REPORTED}",
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Developer, embedded applications or devices",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as embedded developers. {_SELF_REPORTED}",
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Developer, desktop or enterprise applications",
        "match_quality": MatchQuality.CLOSE,
        "match_note": (
            f"Respondents who identify as desktop/enterprise developers. {_SELF_REPORTED}"
        ),
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Developer, QA or test",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "QA and test engineering is a distinct specialisation, generally paid "
            f"differently from application development. {_SELF_REPORTED}"
        ),
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Architect, software or solutions",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "Architecture roles typically sit above individual-contributor development in "
            f"both scope and pay, so this reads high for an IC offer. {_SELF_REPORTED}"
        ),
    },
    {
        "job_family": "Software Engineering",
        "external_code": "DevOps engineer or professional",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "Overlaps software engineering but is a distinct discipline with its own "
            f"market. {_SELF_REPORTED}"
        ),
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Cloud infrastructure engineer",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            f"Infrastructure specialisation rather than application development. "
            f"{_SELF_REPORTED}"
        ),
    },
    {
        "job_family": "Software Engineering",
        "external_code": "Engineering manager",
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "People management, not an individual-contributor role - not comparable to an "
            f"IC engineering offer. {_SELF_REPORTED}"
        ),
    },
    {
        "job_family": "Software Engineering",
        "external_code": ALL_ROLES_CODE,
        "match_quality": MatchQuality.BROAD,
        "match_note": (
            "Every developer role in the survey pooled together, not specific to any "
            "specialisation. Included because it is the only breakdown with enough "
            "responses to show a years-of-experience distribution outside the US. "
            f"{_SELF_REPORTED}"
        ),
    },
    {
        "job_family": "Data & Analytics",
        "external_code": "Data scientist",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as data scientists. {_SELF_REPORTED}",
    },
    {
        "job_family": "Data & Analytics",
        "external_code": "Data engineer",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as data engineers. {_SELF_REPORTED}",
    },
    {
        "job_family": "Data & Analytics",
        "external_code": "AI/ML engineer",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as AI/ML engineers. {_SELF_REPORTED}",
    },
    {
        "job_family": "Data & Analytics",
        "external_code": "Data or business analyst",
        "match_quality": MatchQuality.CLOSE,
        "match_note": f"Respondents who identify as data/business analysts. {_SELF_REPORTED}",
    },
    {
        "job_family": "Product Management",
        "external_code": "Product manager",
        "match_quality": MatchQuality.CLOSE,
        "match_note": (
            "A genuine product management match, which SOC-2018 does not offer at all - "
            "the survey asks respondents directly rather than inferring from a "
            f"project-management occupation. {_SELF_REPORTED}"
        ),
    },
    {
        "job_family": "Design",
        "external_code": "UX, Research Ops or UI design professional",
        "match_quality": MatchQuality.CLOSE,
        "match_note": (
            "Product/UX design respondents. This is a developer survey, so designers are a "
            f"small minority of it and samples are correspondingly thin. {_SELF_REPORTED}"
        ),
    },
]


def seed_survey_occupation_mappings(session: Session) -> int:
    """Upserts the DevType mappings for every covered country. Returns how
    many rows were written.
    """
    families = {family.name: family for family in session.scalars(select(JobFamily)).all()}

    written = 0
    for code in SURVEY_COUNTRIES:
        country = session.scalar(select(Country).where(Country.code == code))
        if country is None:
            continue
        for data in _MAPPINGS:
            family = families.get(data["job_family"])
            if family is None:
                continue
            label = (
                ALL_ROLES_LABEL
                if data["external_code"] == ALL_ROLES_CODE
                else data["external_code"]
            )
            _upsert(
                session,
                JobFamilyOccupationMapping,
                {
                    "job_family_id": family.id,
                    "country_id": country.id,
                    "taxonomy": TAXONOMY,
                    "external_code": data["external_code"],
                },
                {
                    "external_label": label,
                    "match_quality": data["match_quality"],
                    "match_note": data["match_note"],
                },
            )
            written += 1

    session.flush()
    return written
