import datetime as dt

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.urls import reverse

from careers.models import Company, Field, JobPosting, OutcomeStat, ProgramType, Skill, SkillDemandMonthly, Source, University

CAREERS_MODELS = [m for m in apps.get_app_config("careers").get_models() if m is not Source]


@pytest.fixture
def src(db):
    return Source.objects.create(name="Test source")


@pytest.fixture
def field(src):
    return Field.objects.create(name="Information and Communication Technologies", isced_code="06", source=src)


def rejected(model, **kwargs):
    """Assert the database refuses the row (constraint check), without breaking the test transaction."""
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.create(**kwargs)


@pytest.mark.parametrize("model", CAREERS_MODELS, ids=lambda m: m.__name__)
def test_every_data_table_requires_a_source(model):
    f = model._meta.get_field("source")
    assert f.related_model is Source and not f.null


@pytest.mark.django_db
def test_turkish_characters_round_trip(src):
    name = "İSTANBUL TEKNİK ÜNİVERSİTESİ ığüşöç ĞÜŞİÖÇ"
    University.objects.create(name="ITU", name_tr=name, source=src)
    assert University.objects.get(name="ITU").name_tr == name
    assert University.objects.filter(name_tr__icontains="ığüşöç").exists()


@pytest.mark.django_db
def test_outcome_needs_exactly_one_target(src, field):
    pt = ProgramType.objects.create(name="Computer Engineering", field=field, source=src)
    common = dict(metric="employment_rate", value=80.81, year=2025, source=src)
    OutcomeStat.objects.create(program_type=pt, **common)
    rejected(OutcomeStat, **common)
    rejected(OutcomeStat, program_type=pt, field=field, **common)


@pytest.mark.django_db
def test_outcome_unique_per_field_year_metric_source(src, field):
    common = dict(field=field, metric="months_to_first_job", value=11.4, year=2025, source=src)
    OutcomeStat.objects.create(**common)
    rejected(OutcomeStat, **common)  # program_type is NULL in both; nulls_distinct=False must still catch it


@pytest.mark.django_db
def test_company_ats_rules(src):
    Company.objects.create(name="No board", source=src)
    Company.objects.create(name="Trendyol", ats_provider="lever", ats_board_token="trendyol", source=src)
    rejected(Company, name="Provider without token", ats_provider="lever", source=src)
    rejected(Company, name="Same board twice", ats_provider="lever", ats_board_token="trendyol", source=src)


@pytest.mark.django_db
def test_posting_dates_and_uniqueness(src):
    c = Company.objects.create(name="Acme", source=src)
    d = dt.date(2026, 11, 1)
    base = dict(company=c, title="Backend Engineer", url="https://example.com/1", source=src)
    JobPosting.objects.create(external_id="1", first_seen=d, last_seen=d, **base)
    rejected(JobPosting, external_id="1", first_seen=d, last_seen=d, **base)
    rejected(JobPosting, external_id="2", first_seen=d, last_seen=d - dt.timedelta(days=1), **base)


@pytest.mark.django_db
def test_skill_demand_rules(src):
    s = Skill.objects.create(name="Python", source=src)
    SkillDemandMonthly.objects.create(skill=s, month=dt.date(2026, 11, 1), mentions=3, total_postings=10, source=src)
    rejected(SkillDemandMonthly, skill=s, month=dt.date(2026, 11, 1), mentions=1, total_postings=10, source=src)
    rejected(SkillDemandMonthly, skill=s, month=dt.date(2026, 10, 2), mentions=1, total_postings=10, source=src)
    rejected(SkillDemandMonthly, skill=s, month=dt.date(2026, 9, 1), mentions=11, total_postings=10, source=src)


@pytest.mark.parametrize("model", [Source, *CAREERS_MODELS], ids=lambda m: m.__name__)
def test_admin_pages_render(admin_client, model):
    opts = model._meta
    assert admin_client.get(reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")).status_code == 200
    assert admin_client.get(reverse(f"admin:{opts.app_label}_{opts.model_name}_add")).status_code == 200
