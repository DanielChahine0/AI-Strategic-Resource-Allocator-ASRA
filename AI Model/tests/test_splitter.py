"""Splitter: turn multi-category applicants into per-category Applications."""

from __future__ import annotations

from asra_matcher import splitter
from asra_matcher.taxonomy import Category

from tests.conftest import make_applicant


def test_single_category_yields_one_application():
    app = make_applicant(purpose=[Category.D])
    applications = splitter.split(app)
    assert len(applications) == 1
    assert applications[0].category == Category.D


def test_FC_yields_two_applications():
    app = make_applicant(purpose=[Category.F, Category.C])
    applications = splitter.split(app)
    assert len(applications) == 2
    cats = {a.category for a in applications}
    assert cats == {Category.F, Category.C}


def test_empty_purpose_defaults_to_E():
    app = make_applicant(purpose=[])
    applications = splitter.split(app)
    assert len(applications) == 1
    assert applications[0].category == Category.E


def test_all_applications_share_applicant_id():
    app = make_applicant(applicant_id="multi-1", purpose=[Category.F, Category.C])
    applications = splitter.split(app)
    assert all(a.applicant_id == "multi-1" for a in applications)
