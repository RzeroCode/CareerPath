"""The engine on a made-up health and law dataset: nothing here is engineering data (plan Step 2, done-when)."""
import datetime as dt
import itertools
from types import SimpleNamespace

import pytest

from careers.engine import Profile, ProfileError, recommend
from careers.models import Company, Field, JobPosting, OutcomeStat, Program, ProgramType, Skill, Source, University

TODAY = dt.date(2026, 12, 1)
FETCHED = TODAY - dt.timedelta(days=3)
_ids = itertools.count()


def at(day):
    return dt.datetime.combine(day, dt.time(), tzinfo=dt.timezone.utc)


@pytest.fixture
def w(db):
    src = Source.objects.create(name="Test data", fetched_at=at(dt.date(2026, 11, 20)))
    n = SimpleNamespace(src=src)
    n.health = Field.objects.create(name="Health", isced_code="09", source=src)
    n.law_f = Field.objects.create(name="Law and order", isced_code="04", source=src)
    n.med = ProgramType.objects.create(name="Medicine", name_tr="Tıp", field=n.health, source=src)
    n.nur = ProgramType.objects.create(name="Nursing", field=n.health, source=src)
    n.law = ProgramType.objects.create(name="Law", field=n.law_f, source=src)
    n.orphan = ProgramType.objects.create(name="Orphan Studies", source=src)
    unis = {"ankara": "Ankara", "cide": "Cide", "canakkale": "Çanakkale", "isparta": "Isparta", "izmir": "İzmir", "empty": "Boş"}
    for key, name in unis.items():
        setattr(n, key, University.objects.create(name=name, source=src))
    for uni, pt in [(n.ankara, n.med), (n.cide, n.med), (n.cide, n.med), (n.cide, n.nur), (n.canakkale, n.med),
                    (n.isparta, n.law), (n.izmir, n.law)]:
        Program.objects.create(university=uni, program_type=pt, name_tr=f"{pt.name} {next(_ids)}", source=src)
    for key in ["alpha", "beta", "gamma", "delta"]:
        setattr(n, key, Company.objects.create(name=key.title(), last_fetched=FETCHED, source=src))
    n.zeta = Company.objects.create(name="Zeta", source=src)  # never fetched
    for key in ["triage", "charting", "litigation", "anatomy", "bandaging", "dosing", "suturing"]:
        setattr(n, key, Skill.objects.create(name=key.title(), source=src))
    return n


def post(w, company, types=(), skills=(), country="TR", last_seen=FETCHED):
    p = JobPosting.objects.create(company=company, external_id=str(next(_ids)), title="Job", url="https://example.org",
                                  country=country, first_seen=last_seen, last_seen=last_seen, source=w.src)
    p.program_types.set(types)
    p.skills.set(skills)
    return p


def run(**profile):
    return recommend(Profile(**profile), today=TODAY)


def names(items, key):
    return [i[key]["name"] for i in items]


# --- scope ---------------------------------------------------------------------------------------

def test_scope_from_type_field_and_university(w):
    assert names(run(field=w.health.pk)["sections"]["outcomes"]["items"], "program_type") == ["Medicine", "Nursing"]
    assert names(run(university=w.cide.pk)["sections"]["outcomes"]["items"], "program_type") == ["Medicine", "Nursing"]
    both = run(university=w.cide.pk, program_type=w.nur.pk, field=w.health.pk)
    assert names(both["sections"]["outcomes"]["items"], "program_type") == ["Nursing"] and both["notes"] == []


@pytest.mark.parametrize("profile", [{"university": "isparta", "field": "health"}, {"university": "empty"}])
def test_empty_scope_is_a_note_not_everything(w, profile):
    post(w, w.alpha, [w.med])
    result = run(**{k: getattr(w, v).pk for k, v in profile.items()})
    assert result["notes"] and result["sections"]["outcomes"]["items"] == []
    assert result["sections"]["companies_hiring"]["items"] == []


def test_without_education_there_is_no_program_filter(w):
    post(w, w.alpha, [], [w.triage])  # unlinked
    post(w, w.beta, [w.med])
    result = run(skills=[w.triage.pk])
    assert names(result["sections"]["companies_hiring"]["items"], "company") == ["Alpha"]
    assert set(result["sections"]) == {"companies_hiring", "programs_asked_for"}
    assert names(run(company=w.alpha.pk)["sections"]["companies_hiring"]["items"], "company") == ["Alpha"]


def test_filtered_postings_count_once_and_need_a_link(w):
    post(w, w.alpha, [w.med, w.nur])
    post(w, w.beta, [w.law])
    post(w, w.gamma, [])
    items = run(field=w.health.pk)["sections"]["companies_hiring"]["items"]
    assert [(i["company"]["name"], i["open_postings"]) for i in items] == [("Alpha", 1)]


# --- outcomes ------------------------------------------------------------------------------------

def test_outcomes_latest_type_figure_then_field_figure(w):
    older = Source.objects.create(name="Older bulletin", fetched_at=at(dt.date(2026, 1, 1)))
    newer = Source.objects.create(name="Newer bulletin", fetched_at=at(dt.date(2026, 7, 1)))
    M = OutcomeStat.Metric
    for target, metric, value, year, src, sample in [
        ({"program_type": w.med}, M.EMPLOYMENT_RATE, 80, 2024, older, 100),
        ({"program_type": w.med}, M.EMPLOYMENT_RATE, 85, 2025, older, 120),
        ({"field": w.health}, M.EMPLOYMENT_RATE, 70, 2026, newer, 500),  # newer, but a type figure exists
        ({"field": w.health}, M.MONTHS_TO_FIRST_JOB, 12, 2025, older, 400),
        ({"field": w.health}, M.FIELD_MATCH_RATE, 55, 2025, newer, None),  # same year: fetched last wins,
        ({"field": w.health}, M.FIELD_MATCH_RATE, 50, 2025, older, None),  # even when saved first
    ]:
        OutcomeStat.objects.create(**target, metric=metric, value=value, year=year, source=src, sample_size=sample)
    section = run(program_type=w.med.pk)["sections"]["outcomes"]
    figures = {f["metric"]: f for f in section["items"][0]["figures"]}
    assert (figures["employment_rate"]["value"], figures["employment_rate"]["level"]) == (85, "program_type")
    assert (figures["months_to_first_job"]["value"], figures["months_to_first_job"]["level"]) == (12, "field")
    match = figures["field_match_rate"]
    assert (match["value"], match["level"], match["source"], match["sample_size"], match["sample_size_note"]) == \
        (55, "field", "Newer bulletin", None, "not published")
    assert section["evidence"]["sources"] == ["Newer bulletin", "Older bulletin"]
    assert section["evidence"]["as_of"] == dt.date(2026, 1, 1)


def test_outcomes_absent_or_empty_without_crashing(w):
    assert "outcomes" not in run(company=w.alpha.pk)["sections"]
    assert run(program_type=w.orphan.pk)["sections"]["outcomes"]["items"][0]["figures"] == []


# --- companies hiring now ------------------------------------------------------------------------

def test_companies_hiring_open_turkish_postings_only(w):
    for company, n in [(w.alpha, 2), (w.gamma, 1), (w.beta, 1)]:
        for _ in range(n):
            post(w, company, [w.med])
    post(w, w.delta, [w.med], last_seen=FETCHED - dt.timedelta(days=1))  # closed
    post(w, w.delta, [w.med], country="DE")
    post(w, w.delta, [w.med], country="")
    post(w, w.zeta, [w.med])  # never fetched: closed
    section = run(field=w.health.pk)["sections"]["companies_hiring"]
    assert [(i["company"]["name"], i["open_postings"]) for i in section["items"]] == [("Alpha", 2), ("Beta", 1), ("Gamma", 1)]
    assert section["companies_tracked"] == 4
    assert section["evidence"] == {"sources": ["Test data"], "as_of": FETCHED, "sample_size": 4}


def test_companies_hiring_narrowed_by_company_and_any_skill(w):
    post(w, w.alpha, [w.med], [w.triage, w.charting])  # names both: counted once
    post(w, w.alpha, [w.med], [w.charting])
    post(w, w.beta, [w.med], [w.litigation])
    items = lambda **p: [(i["company"]["name"], i["open_postings"]) for i in run(**p)["sections"]["companies_hiring"]["items"]]  # noqa: E731
    assert items(skills=[w.triage.pk, w.charting.pk]) == [("Alpha", 2)]
    assert items(company=w.beta.pk) == [("Beta", 1)]
    assert items(company=w.alpha.pk, skills=[w.litigation.pk]) == []
    assert items(field=w.law_f.pk) == []
    assert run(field=w.law_f.pk)["sections"]["companies_hiring"]["companies_tracked"] == 4


# --- skills --------------------------------------------------------------------------------------

def lift_world(w, scope_n=20, companies=3):
    """20 in-scope postings (Medicine) and 20 others; 40 in all. Some are closed or abroad: they still count."""
    owners = [w.alpha, w.beta, w.gamma][:companies]
    scope = [post(w, owners[i % companies], [w.med], country="DE" if i in (1, 2) else "TR",
                  last_seen=FETCHED - dt.timedelta(days=5) if i in (3, 4) else FETCHED) for i in range(scope_n)]
    other = [post(w, w.delta, [w.law] if i % 2 else [], country="DE" if i < 3 else "TR",
                  last_seen=FETCHED - dt.timedelta(days=9) if i in (5, 6) else FETCHED) for i in range(20)]
    for skill, in_scope, outside in [
        (w.triage, range(0, 6), range(0, 4)),        # 6/20 vs 10/40 -> 1.2
        (w.anatomy, range(6, 12), range(4, 8)),      # 1.2, 6 mentions: tie with Triage, Anatomy first by name
        (w.bandaging, range(0, 9), range(8, 14)),    # 9/20 vs 15/40 -> 1.2, 9 mentions: before the 6s
        (w.dosing, range(12, 17), range(14, 15)),    # 5/20 vs 6/40 -> 1.67
        (w.charting, range(0, 5), range(15, 20)),    # 5/20 vs 10/40 -> 1.0: hidden
        (w.suturing, [17, 18, 19, 0], []),           # 4 mentions: hidden
    ]:
        skill.postings.add(*[scope[i] for i in in_scope if i < scope_n], *[other[i] for i in outside])


def test_skills_ranked_by_lift(w):
    lift_world(w)
    Skill.objects.filter(pk=w.dosing.pk).update(onet_hot=True)
    section = run(program_type=w.med.pk, skills=[w.triage.pk])["sections"]["skills"]
    assert section["enough_data"] and (section["scope_postings"], section["scope_companies"]) == (20, 3)
    assert [(i["skill"]["name"], i["lift"], i["mentions"]) for i in section["items"]] == [
        ("Dosing", 1.67, 5), ("Bandaging", 1.2, 9), ("Anatomy", 1.2, 6), ("Triage", 1.2, 6)]
    assert [i["held"] for i in section["items"]] == [False, False, False, True]
    assert [i["onet_hot"] for i in section["items"]] == [True, False, False, False]
    assert section["evidence"]["sample_size"] == {"scope_postings": 20, "all_postings": 40}
    assert "rising" not in str(section)
    plain = run(program_type=w.med.pk)["sections"]["skills"]["items"]
    with_company = run(program_type=w.med.pk, company=w.delta.pk)["sections"]["skills"]["items"]
    strip = lambda items: [(i["skill"]["name"], i["lift"], i["mentions"]) for i in items]  # noqa: E731
    assert strip(plain) == strip(with_company) == strip(section["items"])


@pytest.mark.parametrize("scope_n, companies", [(19, 3), (20, 2)])
def test_skills_need_enough_postings_and_companies(w, scope_n, companies):
    lift_world(w, scope_n, companies)
    section = run(program_type=w.med.pk)["sections"]["skills"]
    assert not section["enough_data"] and section["items"] == []
    assert (section["scope_postings"], section["scope_companies"]) == (scope_n, companies)


def test_skills_with_enough_postings_but_no_qualifying_skill(w):
    for i in range(20):
        post(w, [w.alpha, w.beta, w.gamma][i % 3], [w.med])
    section = run(program_type=w.med.pk)["sections"]["skills"]
    assert section["enough_data"] and section["items"] == []
    assert "skills" not in run(company=w.alpha.pk)["sections"]


# --- programs asked for, universities ------------------------------------------------------------

def test_programs_asked_for(w):
    post(w, w.alpha, [w.med, w.nur])
    post(w, w.alpha, [w.nur])
    post(w, w.alpha, [w.law], last_seen=FETCHED - dt.timedelta(days=1))  # closed
    post(w, w.alpha, [w.law], country="DE")
    section = run(company=w.alpha.pk)["sections"]["programs_asked_for"]
    assert [(i["program_type"]["name"], i["open_postings"]) for i in section["items"]] == [("Nursing", 2), ("Medicine", 1)]
    assert section["evidence"]["sample_size"] == 2
    only = run(company=w.alpha.pk, program_type=w.med.pk)["sections"]["programs_asked_for"]["items"]
    assert [i["program_type"]["name"] for i in only] == ["Medicine"]
    assert "programs_asked_for" not in run(program_type=w.med.pk)["sections"]


def test_universities_offering_the_scope_in_turkish_order(w):
    section = run(program_type=w.med.pk)["sections"]["universities"]
    assert [u["name"] for u in section["items"]] == ["Ankara", "Cide", "Çanakkale"]
    assert section["evidence"] == {"sources": ["Test data"], "as_of": dt.date(2026, 11, 20), "sample_size": 3}
    assert [u["name"] for u in run(field=w.law_f.pk)["sections"]["universities"]["items"]] == ["Isparta", "İzmir"]
    assert "universities" not in run(university=w.cide.pk, program_type=w.med.pk)["sections"]
    assert "universities" not in run(company=w.alpha.pk)["sections"]


# --- evidence and input --------------------------------------------------------------------------

def test_every_section_says_where_its_numbers_come_from(w):
    lift_world(w)
    OutcomeStat.objects.create(program_type=w.med, metric="employment_rate", value=90, year=2025, source=w.src)
    sections = run(program_type=w.med.pk, company=w.alpha.pk, skills=[w.triage.pk])["sections"]
    assert set(sections) == {"outcomes", "companies_hiring", "skills", "programs_asked_for", "universities"}
    for section in sections.values():
        assert set(section["evidence"]) == {"sources", "as_of", "sample_size"} and section["evidence"]["sources"]
    for figure in sections["outcomes"]["items"][0]["figures"]:
        assert {"source", "year", "sample_size"} <= set(figure)


@pytest.mark.parametrize("profile, field", [
    ({}, None), ({"skills": []}, None),
    ({"university": 0}, "university"), ({"program_type": 0}, "program_type"), ({"field": 0}, "field"),
    ({"company": 0}, "company"), ({"skills": "bad"}, "skills"),
])
def test_bad_profiles(w, profile, field):
    if profile.get("skills") == "bad":
        profile = {"skills": [w.triage.pk, 0]}
    with pytest.raises(ProfileError) as e:
        run(**profile)
    assert e.value.field == field


def test_stale_companies_are_not_tracked_and_two_type_postings_count_once(w):
    Company.objects.filter(pk=w.gamma.pk).update(last_fetched=TODAY - dt.timedelta(days=29))
    Company.objects.filter(pk=w.delta.pk).update(last_fetched=TODAY - dt.timedelta(days=28))
    post(w, w.gamma, [w.med])  # its fetch is too old: closed
    for i in range(20):
        post(w, [w.alpha, w.beta, w.delta][i % 3], [w.med, w.nur])
    result = run(field=w.health.pk)["sections"]
    assert result["companies_hiring"]["companies_tracked"] == 3
    assert "Gamma" not in [i["company"]["name"] for i in result["companies_hiring"]["items"]]
    assert result["skills"]["scope_postings"] == 21


def test_programs_asked_for_counts_only_linked_postings(w):
    post(w, w.alpha, [w.med])
    post(w, w.alpha, [])  # names no program
    post(w, w.alpha, [w.law])  # outside the scope below
    section = run(company=w.alpha.pk, field=w.health.pk)["sections"]["programs_asked_for"]
    assert section["evidence"]["sample_size"] == 1


def test_outcome_queries_do_not_grow_with_the_number_of_programs(w):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    def queries():
        with CaptureQueriesContext(connection) as ctx:
            run(field=w.health.pk)
        return len(ctx)

    before = queries()
    for i in range(10):
        pt = ProgramType.objects.create(name=f"Health {i}", field=w.health, source=w.src)
        OutcomeStat.objects.create(program_type=pt, metric="employment_rate", value=70, year=2025, source=w.src)
    assert queries() == before
