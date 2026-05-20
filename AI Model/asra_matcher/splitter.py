"""Split multi-category applicants into per-category Applications.

An applicant tagged `[F, C]` becomes two Applications, scored independently.
The engine keeps only the one with the strongest top match — the rest are
reported as `discarded_applications` for the human reviewer.
"""

from __future__ import annotations

from asra_matcher.models import Applicant, Application
from asra_matcher.taxonomy import Category


def split(applicant: Applicant) -> list[Application]:
    """Return one Application per category on the applicant.

    Empty `purpose` is treated as Category.E (personal browsing) to keep the
    engine deterministic when intake parsing fails or returns nothing.
    """
    purposes = applicant.intake.purpose
    if not purposes:
        purposes = [Category.E]

    return [
        Application(
            applicant_id=applicant.applicant_id,
            category=category,
            intake=applicant.intake,
        )
        for category in purposes
    ]
