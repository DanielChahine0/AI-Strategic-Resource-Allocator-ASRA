"""Multi-category applicants are split into one Application per category."""
from __future__ import annotations

from .models import Applicant, Application


def split(applicant: Applicant) -> list[Application]:
    """One Application per declared purpose category.

    Per spec: run the engine independently on each Application, then keep only
    the strongest top match across them.
    """
    out: list[Application] = []
    for cat in applicant.intake.purpose:
        out.append(
            Application(
                applicant_id=applicant.id,
                submitted_at=applicant.submitted_at,
                category=cat,
                intake=applicant.intake,
            )
        )
    return out
