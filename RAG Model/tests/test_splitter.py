"""Multi-category splitter tests."""
from __future__ import annotations

from asra_matcher.splitter import split
from asra_matcher.taxonomy import Category


def test_single_category_yields_one_application(make_applicant):
    apps = split(make_applicant(Category.B))
    assert len(apps) == 1
    assert apps[0].category == Category.B


def test_multi_category_yields_one_per_category(make_applicant):
    a = make_applicant(Category.F)
    # Hack: override purpose to include C alongside F.
    a.intake.purpose = [Category.F, Category.C]
    apps = split(a)
    assert {x.category for x in apps} == {Category.F, Category.C}


def test_splitter_preserves_applicant_metadata(make_applicant):
    a = make_applicant(Category.A2)
    a.intake.purpose = [Category.A2, Category.C]
    apps = split(a)
    for app in apps:
        assert app.applicant_id == a.id
        assert app.submitted_at == a.submitted_at
        assert app.intake.main_usage == a.intake.main_usage
